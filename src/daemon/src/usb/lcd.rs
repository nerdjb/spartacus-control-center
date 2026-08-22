// LCD Display Device Handler
// DeepCool SPARTACUS LCD (USB 3633:0027) - 480x480 panel.
//
// Wire protocol (reverse engineered, see reference libspartacus spec):
//   Control channel - bulk EP 0x04, fixed 46-byte packets:
//     [0:2]   signature AA 2E
//     [2]     command (0x05 session, 0x04 config, 0x01 telemetry)
//     [3:44]  parameters (command specific)
//     [44:46] sum16 of bytes [0:44], little-endian
//   Image channel - bulk EP 0x02, exactly-512-byte packets, baseline JPEG only:
//     START : "Start"      + type(0x01) + len u32le + sum16 u16le + chunk_count u16le
//     DATA xN: "trans"     + seq u16le (1-based) + payload (505 B at offset 7)
//     FINISH: "DCLdfinish"
//
// Safety notes:
//   - Orientation/brightness live in panel NVM: send config only when values change.
//   - Brightness range is 0..100; upright orientation is 0x01.
//   - Panel reverts to its logo after ~15 s without data; caller must refresh.

use anyhow::{anyhow, Result};
use jpeg_encoder::{ColorType, Encoder};
use log::{debug, info};
use rusb::{Context, DeviceHandle, UsbContext};
use std::time::Duration;

use super::{
    sum16, LCD_EP_CONTROL_OUT, LCD_EP_IMAGE_OUT, LCD_HEIGHT, LCD_PRODUCT_ID, LCD_WIDTH,
    USB_TIMEOUT_MS,
};

const CONTROL_PACKET_LEN: usize = 46;
const IMAGE_PACKET_LEN: usize = 512;
const IMAGE_DATA_PAYLOAD: usize = 505;

pub struct LCDDevice {
    pub vendor_id: u16,
    pub product_id: u16,
    pub path: String,
    pub connected: bool,
    handle: Option<DeviceHandle<Context>>,
    /// Last applied (orientation, brightness); config writes persist in NVM,
    /// so no-op writes are skipped to avoid needless wear.
    applied_config: Option<(u8, u8)>,
}

impl LCDDevice {
    pub fn new() -> Self {
        Self {
            vendor_id: super::DEEPCOOL_VENDOR_ID,
            product_id: LCD_PRODUCT_ID,
            path: String::new(),
            connected: false,
            handle: None,
            applied_config: None,
        }
    }

    pub async fn connect(&mut self) -> Result<()> {
        info!(
            "Attempting to connect to LCD Display ({:04x}:{:04x})",
            self.vendor_id, self.product_id
        );

        let (address, handle) = open_lcd_device(self.vendor_id, self.product_id)?;

        self.path = format!("usb-address-{}", address);
        self.handle = Some(handle);
        self.connected = true;
        info!("LCD Display connected at {}", self.path);

        self.session_start().await?;
        Ok(())
    }

    pub async fn disconnect(&mut self) -> Result<()> {
        if !self.connected {
            return Ok(());
        }

        info!("Disconnecting LCD Display");
        if let Some(handle) = self.handle.take() {
            let _ = self.session_stop_inner(&handle);
            let _ = handle.release_interface(0);
        }
        self.connected = false;
        self.applied_config = None;
        Ok(())
    }

    /// Enable the image stream (cmd 0x05, param 0x01).
    pub async fn session_start(&mut self) -> Result<()> {
        self.ensure_connected()?;
        let handle = self.handle.as_ref().unwrap();
        let pkt = control_packet(0x05, &[0x01]);
        write_control(handle, &pkt)?;
        debug!("LCD session started");
        Ok(())
    }

    /// Stop the image stream (switches panel to native telemetry mode).
    pub async fn session_stop(&mut self) -> Result<()> {
        self.ensure_connected()?;
        let handle = self.handle.as_ref().unwrap();
        let pkt = control_packet(0x05, &[0x00]);
        write_control(handle, &pkt)?;
        debug!("LCD session stopped");
        Ok(())
    }

    fn session_stop_inner(&self, handle: &DeviceHandle<Context>) -> Result<()> {
        let pkt = control_packet(0x05, &[0x00]);
        write_control(handle, &pkt)
    }

    /// Set orientation and brightness together (cmd 0x04).
    ///
    /// Orientation: 0x01 upright, 0x02 90 deg CCW, 0x03 180 deg, 0x00 270 deg.
    /// Brightness: 0..100 percentage (persisted in panel NVM along with orientation).
    /// No-ops when both values already match what the panel has.
    pub async fn set_display(&mut self, orientation: u8, brightness: u8) -> Result<()> {
        self.ensure_connected()?;
        let orientation = match orientation {
            0..=3 => orientation,
            _ => return Err(anyhow!("Invalid orientation {orientation}, expected 0..3")),
        };
        let brightness = brightness.min(100);

        let cfg = (orientation, brightness);
        if self.applied_config == Some(cfg) {
            debug!("Skipping no-op display config {:?}", cfg);
            return Ok(());
        }

        let mut params = vec![orientation, brightness];
        params.resize(CONTROL_PACKET_LEN - 6, 0);
        let pkt = control_packet(0x04, &params);
        let handle = self.handle.as_ref().unwrap();
        write_control(handle, &pkt)?;
        self.applied_config = Some(cfg);
        info!("LCD config set: orientation={orientation:#04x} brightness={brightness}");
        Ok(())
    }

    pub async fn set_brightness(&mut self, brightness: u8) -> Result<()> {
        let (orientation, _) = self.applied_config.unwrap_or((0x01, 80));
        self.set_display(orientation, brightness).await
    }

    /// Push native CPU temperature/usage readout (~1 Hz while in telemetry mode).
    pub async fn push_telemetry(&mut self, temp_c: u8, usage_pct: u8) -> Result<()> {
        self.ensure_connected()?;
        let pkt = telemetry_packet(temp_c, usage_pct.min(100));
        let handle = self.handle.as_ref().unwrap();
        write_control(handle, &pkt)
    }

    /// Stream a ready-made 480x480 **baseline** JPEG frame.
    pub async fn send_jpeg_frame(&mut self, jpeg_data: &[u8]) -> Result<()> {
        self.ensure_connected()?;
        if jpeg_data.is_empty() {
            return Err(anyhow!("JPEG frame is empty"));
        }
        let handle = self.handle.as_ref().unwrap();
        stream_jpeg(handle, jpeg_data)
    }

    /// Encode an RGB888 480x480 frame to baseline JPEG and stream it.
    pub async fn send_rgb_frame(&mut self, rgb: &[u8], quality: u8) -> Result<()> {
        self.ensure_connected()?;
        if rgb.len() != super::LCD_FRAME_SIZE {
            return Err(anyhow!(
                "Invalid RGB frame size: expected {}, got {}",
                super::LCD_FRAME_SIZE,
                rgb.len()
            ));
        }
        let jpeg = encode_baseline_jpeg(rgb, quality)?;
        self.send_jpeg_frame(&jpeg).await
    }

    /// Lightweight keepalive against the ~15 s logo watchdog: a Session Start
    /// re-shows the retained frame without re-sending the whole image.
    pub async fn keepalive(&mut self) -> Result<()> {
        self.session_start().await
    }

    /// Get current display status
    pub async fn get_status(&self) -> Result<LCDStatus> {
        Ok(LCDStatus {
            connected: self.connected,
            brightness: self.applied_config.map(|c| c.1).unwrap_or(255),
            refresh_rate: 30,
        })
    }

    fn ensure_connected(&self) -> Result<()> {
        if !self.connected {
            return Err(anyhow!("LCD device not connected"));
        }
        Ok(())
    }
}

/// Discover, open, and bring up the LCD device.
///
/// Kept sync + non-async so the non-Send `DeviceList` is guaranteed to be
/// dropped before any await point in the caller.
fn open_lcd_device(vendor_id: u16, product_id: u16) -> Result<(u8, DeviceHandle<Context>)> {
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
        .ok_or_else(|| anyhow!("LCD device {vendor_id:04x}:{product_id:04x} not found"))?;

    let address = device.address();
    let handle = device.open()?;

    // Reference bring-up: detach kernel driver (auto), SET_CONFIGURATION(1),
    // claim interface 0.
    let _ = handle.set_auto_detach_kernel_driver(true);
    let _ = handle.set_active_configuration(1);
    handle.claim_interface(0)?;

    Ok((address, handle))
}

/// Build a 46-byte display control packet with sum16 trailer.
fn control_packet(cmd: u8, params: &[u8]) -> [u8; CONTROL_PACKET_LEN] {
    let mut pkt = [0u8; CONTROL_PACKET_LEN];
    pkt[0] = 0xAA;
    pkt[1] = 0x2E;
    pkt[2] = cmd;
    let body = &mut pkt[3..44];
    let n = body.len().min(params.len());
    body[..n].copy_from_slice(&params[..n]);
    let sum = sum16(&pkt[0..44]);
    pkt[44] = (sum & 0xFF) as u8;
    pkt[45] = (sum >> 8) as u8;
    pkt
}

/// Native telemetry template: temp at [3], usage at [6], fixed layout elsewhere.
pub(crate) fn telemetry_packet(temp_c: u8, usage_pct: u8) -> [u8; CONTROL_PACKET_LEN] {
    let mut pkt = [0u8; CONTROL_PACKET_LEN];
    pkt[0] = 0xAA;
    pkt[1] = 0x2E;
    pkt[2] = 0x01;
    pkt[3] = temp_c;
    pkt[6] = usage_pct;
    const FIXED: [u8; 16] = [
        0x00, 0x08, 0x00, 0xD7, 0x03, 0x00, 0x1E, 0x05, 0x00, 0x07, 0x0C, 0x00, 0x02, 0x04, 0x00,
        0x3E,
    ];
    pkt[7..23].copy_from_slice(&FIXED);
    let sum = sum16(&pkt[0..44]);
    pkt[44] = (sum & 0xFF) as u8;
    pkt[45] = (sum >> 8) as u8;
    pkt
}

/// Stream a baseline JPEG as START / DATA xN / FINISH packets on the image endpoint.
fn stream_jpeg(handle: &DeviceHandle<Context>, jpeg: &[u8]) -> Result<()> {
    let timeout = Duration::from_millis(USB_TIMEOUT_MS);
    let chunks = jpeg.len().div_ceil(IMAGE_DATA_PAYLOAD);
    if chunks > u16::MAX as usize {
        return Err(anyhow!("JPEG too large for one frame: {} bytes", jpeg.len()));
    }

    // START packet
    let mut start = [0u8; IMAGE_PACKET_LEN];
    start[0..5].copy_from_slice(b"Start");
    start[5] = 0x01; // frame type: all content
    start[6..10].copy_from_slice(&(jpeg.len() as u32).to_le_bytes());
    let sum = sum16(jpeg);
    start[10..12].copy_from_slice(&sum.to_le_bytes());
    start[12..14].copy_from_slice(&(chunks as u16).to_le_bytes());
    write_bulk_exact(handle, LCD_EP_IMAGE_OUT, &start, timeout)?;

    // DATA packets, sequence numbers are 1-based; payload begins at offset 7
    for (index, payload) in jpeg.chunks(IMAGE_DATA_PAYLOAD).enumerate() {
        let mut data = [0u8; IMAGE_PACKET_LEN];
        data[0..5].copy_from_slice(b"trans");
        data[5..7].copy_from_slice(&((index + 1) as u16).to_le_bytes());
        data[7..7 + payload.len()].copy_from_slice(payload);
        write_bulk_exact(handle, LCD_EP_IMAGE_OUT, &data, timeout)?;
    }

    // FINISH packet
    let mut finish = [0u8; IMAGE_PACKET_LEN];
    finish[0..10].copy_from_slice(b"DCLdfinish");
    write_bulk_exact(handle, LCD_EP_IMAGE_OUT, &finish, timeout)?;

    debug!(
        "Streamed {} byte JPEG ({} packets) to LCD",
        jpeg.len(),
        chunks + 2
    );
    Ok(())
}

fn write_bulk_exact(
    handle: &DeviceHandle<Context>,
    endpoint: u8,
    data: &[u8],
    timeout: Duration,
) -> Result<()> {
    let written = handle.write_bulk(endpoint, data, timeout)?;
    if written != data.len() {
        return Err(anyhow!(
            "Short bulk write on EP {endpoint:#04x}: {} of {} bytes",
            written,
            data.len()
        ));
    }
    Ok(())
}

fn write_control(handle: &DeviceHandle<Context>, pkt: &[u8; CONTROL_PACKET_LEN]) -> Result<()> {
    let timeout = Duration::from_millis(USB_TIMEOUT_MS);
    write_bulk_exact(handle, LCD_EP_CONTROL_OUT, pkt, timeout)
}

/// Encode RGB888 pixels as a 480x480 baseline (sequential) JPEG.
fn encode_baseline_jpeg(rgb: &[u8], quality: u8) -> Result<Vec<u8>> {
    let mut jpeg = Vec::with_capacity(256 * 1024);
    let encoder = Encoder::new(&mut jpeg, quality.clamp(1, 100));
    encoder
        .encode(rgb, LCD_WIDTH, LCD_HEIGHT, ColorType::Rgb)
        .map_err(|e| anyhow!("JPEG encode failed: {e}"))?;
    Ok(jpeg)
}

#[derive(Debug, Clone)]
pub struct LCDStatus {
    pub connected: bool,
    pub brightness: u8,
    pub refresh_rate: u32,
}

impl Default for LCDDevice {
    fn default() -> Self {
        Self::new()
    }
}
