// Linker Controller Device Handler
// DeepCool SPARTACUS Linker (USB 3633:002D) - pump/fan control, ARGB, tachometry.
//
// Wire protocol (reverse engineered, see reference libspartacus spec):
//   One 64-byte HID report (report id 0x10) carries the complete control state
//   in both directions. Host -> device on interrupt EP 0x01, device -> host on
//   interrupt EP 0x81. The report is stateless per transfer: every field must
//   be populated on every transmission.
//
//   [0]      report id 0x10
//   [1:6]    header 68 05 02 20 08
//   [6]      effect mode: 01 motherboard, 02 breathing, 03 rainbow, 04 always-on
//   [7]      breathing speed          [8:11]  breathing RGB
//   [11]     rainbow speed            [12]    rainbow saturation
//   [13:16]  always-on RGB
//   [16]     fan sync flag: 01 software, 00 motherboard
//   [17:29]  channel controls: 4 x (speed %, ramp, source)
//   [29:37]  tachometers, big-endian: pump, aio, ext1, ext2
//   [37]     sum8 over bytes [1:37]
//   [38]     marker 0x16
//
// Safety notes:
//   - The pump cools the CPU: treat duty below ~40% as unsafe.
//   - Reading status requires sending a report; a poll solicited with the
//     retained report re-sends the state we already own (no-op), while a
//     neutralized poll hands everything to the motherboard — only correct
//     before we have taken control.

use anyhow::{anyhow, Result};
use log::{debug, info, warn};
use rusb::{Context, DeviceHandle, UsbContext};
use std::time::Duration;

use super::{
    sum8, CONTROLLER_PRODUCT_ID, LINKER_EP_CONTROL_OUT, LINKER_EP_STATUS_IN, USB_TIMEOUT_MS,
};

const REPORT_LEN: usize = 64;
const REPORT_ID: u8 = 0x10;
const HEADER: [u8; 5] = [0x68, 0x05, 0x02, 0x20, 0x08];
const MARKER: u8 = 0x16;

pub const EFFECT_MOTHERBOARD: u8 = 0x01;
pub const EFFECT_BREATHING: u8 = 0x02;
pub const EFFECT_RAINBOW: u8 = 0x03;
pub const EFFECT_ALWAYS_ON: u8 = 0x04;

const SOURCE_SOFTWARE: u8 = 0x01;
const SOURCE_MOTHERBOARD: u8 = 0x00;

/// Complete retained control state of the Linker.
#[derive(Debug, Clone)]
pub struct LinkerReport {
    pub effect: u8,
    pub breathing_speed: u8,
    pub breathing_color: [u8; 3],
    pub rainbow_speed: u8,
    pub rainbow_saturation: u8,
    pub always_on_color: [u8; 3],
    pub fan_sync: u8,
    /// Per-channel [speed %, ramp, source]; 0=pump, 1=aio, 2=ext1, 3=ext2.
    pub channels: [[u8; 3]; 4],
}

impl Default for LinkerReport {
    fn default() -> Self {
        // Matches the reference library defaults / golden vector:
        // rainbow effect, pump 55%, fans 32%, all channels software-driven.
        Self {
            effect: EFFECT_RAINBOW,
            breathing_speed: 0x0A,
            breathing_color: [0xFF, 0x00, 0xFF],
            rainbow_speed: 0xFA,
            rainbow_saturation: 0x0A,
            always_on_color: [0x00, 0x00, 0xFF],
            fan_sync: SOURCE_SOFTWARE,
            channels: [
                [55, 0, SOURCE_SOFTWARE],
                [32, 0, SOURCE_SOFTWARE],
                [32, 0, SOURCE_SOFTWARE],
                [32, 0, SOURCE_SOFTWARE],
            ],
        }
    }
}

impl LinkerReport {
    /// Encode into the wire format. `rpm` values are placeholders on TX.
    pub fn encode(&self, rpm: [u16; 4]) -> [u8; REPORT_LEN] {
        let mut buf = [0u8; REPORT_LEN];
        buf[0] = REPORT_ID;
        buf[1..6].copy_from_slice(&HEADER);
        buf[6] = self.effect;
        buf[7] = self.breathing_speed;
        buf[8..11].copy_from_slice(&self.breathing_color);
        buf[11] = self.rainbow_speed;
        buf[12] = self.rainbow_saturation;
        buf[13..16].copy_from_slice(&self.always_on_color);
        buf[16] = self.fan_sync;
        for (index, channel) in self.channels.iter().enumerate() {
            let base = 17 + index * 3;
            buf[base..base + 3].copy_from_slice(channel);
        }
        for (index, value) in rpm.iter().enumerate() {
            let base = 29 + index * 2;
            buf[base..base + 2].copy_from_slice(&value.to_be_bytes());
        }
        buf[37] = sum8(&buf[1..37]);
        buf[38] = MARKER;
        buf
    }

    /// Neutral variant used for passive status polls: hands lighting and all
    /// outputs to the motherboard (except EXT fan 2 which stays software per
    /// the protocol's asymmetric motherboard-sync table) without touching
    /// retained duties.
    pub fn neutralized(&self) -> Self {
        let mut neutral = self.clone();
        neutral.effect = EFFECT_MOTHERBOARD;
        neutral.fan_sync = SOURCE_MOTHERBOARD;
        neutral.channels[0][2] = SOURCE_MOTHERBOARD;
        neutral.channels[1][2] = SOURCE_MOTHERBOARD;
        neutral.channels[2][2] = SOURCE_MOTHERBOARD;
        neutral.channels[3][2] = SOURCE_SOFTWARE;
        neutral
    }
}

pub struct ControllerDevice {
    pub vendor_id: u16,
    pub product_id: u16,
    pub path: String,
    pub connected: bool,
    report: LinkerReport,
    handle: Option<DeviceHandle<Context>>,
    /// True once we deliberately wrote a control report (fan takeover or
    /// motherboard hand-over). Governs how tachometry polls are solicited.
    owns_control: bool,
    /// Encoded form of the last transmitted control report; lets us skip
    /// redundant writes (the curve loop re-applies every second).
    last_transmitted: Option<[u8; REPORT_LEN]>,
}

impl ControllerDevice {
    pub fn new() -> Self {
        Self {
            vendor_id: super::DEEPCOOL_VENDOR_ID,
            product_id: CONTROLLER_PRODUCT_ID,
            path: String::new(),
            connected: false,
            report: LinkerReport::default(),
            handle: None,
            owns_control: false,
            last_transmitted: None,
        }
    }

    pub async fn connect(&mut self) -> Result<()> {
        info!(
            "Attempting to connect to Linker Controller ({:04x}:{:04x})",
            self.vendor_id, self.product_id
        );

        let (address, handle) = open_linker_device(self.vendor_id, self.product_id)?;

        self.path = format!("usb-address-{}", address);
        self.handle = Some(handle);
        self.connected = true;
        info!("Linker Controller connected at {}", self.path);
        Ok(())
    }

    pub async fn disconnect(&mut self) -> Result<()> {
        if !self.connected {
            return Ok(());
        }

        info!("Disconnecting Linker Controller");
        if let Some(handle) = self.handle.take() {
            let _ = handle.release_interface(0);
        }
        self.connected = false;
        self.owns_control = false;
        self.last_transmitted = None;
        Ok(())
    }

    /// Poll tachometry without disturbing the current control state.
    ///
    /// Every poll IS a full control write (the device only replies when
    /// solicited), so the report used to solicit matters:
    ///  - once we own control, solicit with the **retained** report — it is a
    ///    no-op re-send and cannot flip anything;
    ///  - before any takeover, solicit with the neutralized variant — the
    ///    documented safe monitoring posture (everything to motherboard).
    /// Soliciting neutralized while also driving fans would hand lighting back
    /// to the motherboard between our own writes, visibly toggling ARGB.
    pub async fn read_rpm_passive(&mut self) -> Result<RPMData> {
        let solicited = poll_report(&self.report, self.owns_control);
        debug!(
            "RPM poll solicit: owned={} effect={:#04x} fan_sync={:#04x}",
            self.owns_control,
            solicited[6],
            solicited[16]
        );
        let status = self.transfer(&solicited).await?;
        Ok(decode_status(&status))
    }

    /// Send the retained control report (software takeover).
    /// Returns Ok(true) when a transfer happened, Ok(false) when skipped as
    /// a no-op (device already holds exactly this state).
    pub async fn apply_control(&mut self) -> Result<bool> {
        let encoded = self.report.encode([0; 4]);
        if self.owns_control && self.last_transmitted == Some(encoded) {
            debug!("Skipping no-op Linker control write");
            return Ok(false);
        }
        self.transfer(&encoded).await?;
        self.owns_control = true;
        self.last_transmitted = Some(encoded);
        Ok(true)
    }

    /// Set all four duties (0..100%) at once. Refuses pump duty < 40%.
    pub async fn set_fans(
        &mut self,
        pump: u8,
        aio: u8,
        ext1: u8,
        ext2: u8,
        ramp: u8,
    ) -> Result<()> {
        if pump < 40 {
            return Err(anyhow!(
                "Refusing pump duty {pump}% (< 40%); the pump cools the CPU"
            ));
        }
        self.report.fan_sync = SOURCE_SOFTWARE;
        for (channel, speed) in self.report.channels.iter_mut().zip([pump, aio, ext1, ext2]) {
            channel[0] = speed.min(100);
            channel[1] = ramp;
            channel[2] = SOURCE_SOFTWARE;
        }
        let applied = self.apply_control().await?;
        if applied {
            info!("Fan duties set: pump={pump}% aio={aio}% ext1={ext1}% ext2={ext2}% ramp={ramp}");
        }
        Ok(())
    }

    /// Set pump target RPM percentage (0-100).
    pub async fn set_pump_speed(&mut self, speed_percent: u8) -> Result<()> {
        let [_, aio, ext1, ext2] = self.duties();
        self.set_fans(speed_percent.min(100), aio, ext1, ext2, 0)
            .await
    }

    /// Set individual channel speed: 0=pump, 1=aio, 2=ext1, 3=ext2.
    pub async fn set_channel_speed(&mut self, channel_index: usize, speed_percent: u8) -> Result<()> {
        if channel_index >= 4 {
            return Err(anyhow!("Invalid channel index: {channel_index}"));
        }
        if channel_index == 0 && speed_percent < 40 {
            return Err(anyhow!(
                "Refusing pump duty {speed_percent}% (< 40%); the pump cools the CPU"
            ));
        }
        self.report.fan_sync = SOURCE_SOFTWARE;
        let channel = &mut self.report.channels[channel_index];
        channel[0] = speed_percent.min(100);
        channel[2] = SOURCE_SOFTWARE;
        self.apply_control().await?;
        debug!("Channel {channel_index} duty set to {}%", speed_percent);
        Ok(())
    }

    pub async fn set_rainbow(&mut self, speed: u8, saturation: u8) -> Result<()> {
        self.report.effect = EFFECT_RAINBOW;
        self.report.rainbow_speed = speed;
        self.report.rainbow_saturation = saturation;
        self.apply_control().await?;
        info!("ARGB effect set to rainbow (speed={speed:#04x} sat={saturation:#04x})");
        Ok(())
    }

    pub async fn set_breathing(&mut self, color: [u8; 3], speed: u8) -> Result<()> {
        self.report.effect = EFFECT_BREATHING;
        self.report.breathing_color = color;
        self.report.breathing_speed = speed;
        self.apply_control().await?;
        info!("ARGB effect set to breathing {:?}", color);
        Ok(())
    }

    pub async fn set_always_on(&mut self, color: [u8; 3]) -> Result<()> {
        self.report.effect = EFFECT_ALWAYS_ON;
        self.report.always_on_color = color;
        self.apply_control().await?;
        info!("ARGB effect set to always-on {:?}", color);
        Ok(())
    }

    /// Hand fans and lighting to the motherboard (true) or reclaim them (false).
    pub async fn motherboard_sync(&mut self, enable: bool) -> Result<()> {
        if enable {
            self.report = self.report.neutralized();
        } else {
            self.report.effect = EFFECT_RAINBOW;
            self.report.fan_sync = SOURCE_SOFTWARE;
            for channel in self.report.channels.iter_mut() {
                channel[2] = SOURCE_SOFTWARE;
            }
        }
        self.apply_control().await?;
        info!("Motherboard sync {}", if enable { "enabled" } else { "disabled" });
        Ok(())
    }

    pub fn current_report(&self) -> &LinkerReport {
        &self.report
    }

    pub fn duties(&self) -> [u8; 4] {
        [
            self.report.channels[0][0],
            self.report.channels[1][0],
            self.report.channels[2][0],
            self.report.channels[3][0],
        ]
    }

    /// Write a 64-byte report then read back the 64-byte status report.
    async fn transfer(&mut self, report: &[u8; REPORT_LEN]) -> Result<[u8; REPORT_LEN]> {
        if !self.connected {
            return Err(anyhow!("Controller device not connected"));
        }
        let handle = self
            .handle
            .as_ref()
            .ok_or_else(|| anyhow!("Controller device not connected"))?;

        let timeout = Duration::from_millis(USB_TIMEOUT_MS);
        let written = handle.write_interrupt(LINKER_EP_CONTROL_OUT, report, timeout)?;
        if written != REPORT_LEN {
            return Err(anyhow!("Short Linker write: {written} of {REPORT_LEN}"));
        }

        let mut status = [0u8; REPORT_LEN];
        let read = handle.read_interrupt(LINKER_EP_STATUS_IN, &mut status, timeout)?;
        if read != REPORT_LEN {
            return Err(anyhow!("Short Linker read: {read} of {REPORT_LEN}"));
        }
        validate_checksum(&status)?;
        Ok(status)
    }
}

/// Discover, open, and bring up the Linker device.
///
/// Kept sync + non-async so the non-Send `DeviceList` is guaranteed to be
/// dropped before any await point in the caller.
fn open_linker_device(vendor_id: u16, product_id: u16) -> Result<(u8, DeviceHandle<Context>)> {
    let context = Context::new()?;
    let devices = context.devices()?;
    let device = devices
        .iter()
        .find(|device| {
            device
                .device_descriptor()
                .map(|descriptor| {
                    descriptor.vendor_id() == vendor_id && descriptor.product_id() == product_id
                })
                .unwrap_or(false)
        })
        .ok_or_else(|| anyhow!("Linker device {vendor_id:04x}:{product_id:04x} not found"))?;

    let address = device.address();
    let handle = device.open()?;

    // Bring-up per spec: detach kernel HID driver, SET_CONFIGURATION(1),
    // claim interface 0. rusb auto-detach covers the usbhid binding that
    // would otherwise hold the interrupt endpoints.
    let _ = handle.set_auto_detach_kernel_driver(true);
    let _ = handle.set_active_configuration(1);
    handle.claim_interface(0)?;

    Ok((address, handle))
}

/// Validate sum8 over [1:37] against byte 37 and the fixed header/marker.
fn validate_checksum(status: &[u8; REPORT_LEN]) -> Result<()> {
    if status[1..6] != HEADER {
        return Err(anyhow!(
            "Linker status has unexpected header {:02x?}",
            &status[1..6]
        ));
    }
    let expected = sum8(&status[1..37]);
    if expected != status[37] {
        warn!(
            "Linker status checksum mismatch: computed {expected:#04x}, got {:#04x}",
            status[37]
        );
    }
    Ok(())
}

/// Decode big-endian tachometers from a status report.
fn decode_status(status: &[u8; REPORT_LEN]) -> RPMData {
    let be = |offset: usize| u16::from_be_bytes([status[offset], status[offset + 1]]);
    let pump = be(29);
    let aio = be(31);
    let ext1 = be(33);
    let ext2 = be(35);
    debug!("Tachometry: pump={pump} aio={aio} ext1={ext1} ext2={ext2}");
    RPMData {
        pump_rpm: pump,
        fan_rpm: [aio, ext1, ext2, 0, 0, 0],
    }
}

#[derive(Debug, Clone)]
pub struct RPMData {
    pub pump_rpm: u16,
    pub fan_rpm: [u16; 6],
}

impl Default for ControllerDevice {
    fn default() -> Self {
        Self::new()
    }
}

/// Which report a tachometry poll should be solicited with.
/// Pure so the ownership rule stays unit-testable without hardware.
fn poll_report(report: &LinkerReport, owns_control: bool) -> [u8; REPORT_LEN] {
    if owns_control {
        report.encode([0; 4])
    } else {
        report.neutralized().encode([0; 4])
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unowned_poll_solicits_neutral_motherboard_state() {
        let report = LinkerReport::default();
        let pkt = poll_report(&report, false);
        assert_eq!(pkt[6], EFFECT_MOTHERBOARD); // lighting → motherboard
        assert_eq!(pkt[16], SOURCE_MOTHERBOARD); // fan sync flag
        for ch in 0..3 {
            assert_eq!(pkt[17 + ch * 3 + 2], SOURCE_MOTHERBOARD);
        }
        // Asymmetric table: EXT2 keeps software source (spec §5.4)
        assert_eq!(pkt[17 + 3 * 3 + 2], SOURCE_SOFTWARE);
        assert_eq!(pkt[37], sum8(&pkt[1..37]));
    }

    #[test]
    fn owned_poll_solicits_retained_state_unchanged() {
        let mut report = LinkerReport::default();
        report.channels[0][0] = 64;
        report.effect = EFFECT_ALWAYS_ON;
        let pkt = poll_report(&report, true);
        assert_eq!(pkt, report.encode([0; 4])); // identical re-send: no flip
    }

    #[test]
    fn owned_and_unowned_polls_differ_in_effect_byte() {
        let report = LinkerReport::default();
        assert_ne!(
            poll_report(&report, true)[6],
            poll_report(&report, false)[6]
        );
    }
}
