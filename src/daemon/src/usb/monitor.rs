// USB Monitor - Main orchestrator for LCD Display and Linker Controller
//
// Responsibilities:
//   - Connect/reconnect both USB devices (LCD 3633:0027, Linker 3633:002d)
//   - Poll Linker tachometry passively (~2 Hz) into shared daemon state
//   - Render the configured screen theme every refresh interval and stream it;
//     this also acts as the keepalive against the panel's ~15 s logo watchdog

use crate::screen::{self, ScreenRenderer};
use crate::DaemonState;
use anyhow::Result;
use log::{info, warn};
use std::sync::Arc;
use tokio::sync::RwLock;
use tokio::sync::mpsc::Receiver;
use tokio::time::{interval, Duration};

use super::controller::ControllerDevice;
use super::lcd::LCDDevice;
use crate::ipc::DaemonCommand;

const FRAME_QUALITY: u8 = 88;

/// Pure gate for the theme stream, unit-testable:
/// override active and unexpired ⇒ hold; expired ⇒ clear and resume.
fn should_push_theme(override_active: bool, until_ms: u64, now_ms: u64) -> bool {
    if !override_active {
        return true;
    }
    now_ms >= until_ms
}

fn now_epoch_ms() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0)
}

pub struct USBMonitor {
    state: Arc<RwLock<DaemonState>>,
    lcd: LCDDevice,
    controller: ControllerDevice,
    renderer: ScreenRenderer,
    refresh_ms: u64,
    commands: Receiver<DaemonCommand>,
}

impl USBMonitor {
    pub fn new(
        state: Arc<RwLock<DaemonState>>,
        theme: &str,
        refresh_ms: u64,
        commands: Receiver<DaemonCommand>,
    ) -> Result<Self> {
        Ok(Self {
            state,
            lcd: LCDDevice::new(),
            controller: ControllerDevice::new(),
            renderer: ScreenRenderer::new(theme)?,
            refresh_ms,
            commands,
        })
    }

    pub async fn run(mut self) -> Result<()> {
        info!("USB Monitor starting...");

        let mut connect_interval = interval(Duration::from_secs(2));
        let mut rpm_interval = interval(Duration::from_millis(500));
        let mut screen_interval = interval(Duration::from_millis(self.refresh_ms.max(250)));

        loop {
            tokio::select! {
                _ = connect_interval.tick() => {
                    self.try_connect().await;
                }

                _ = rpm_interval.tick(), if self.controller.connected => {
                    if let Err(e) = self.update_rpm_telemetry().await {
                        warn!("Failed to poll tachometry: {}", e);
                    }
                }

                _ = screen_interval.tick(), if self.lcd.connected => {
                    if let Err(e) = self.push_theme_frame().await {
                        warn!("Screen refresh failed: {}", e);
                    }
                }

                Some(command) = self.commands.recv() => {
                    self.handle_command(command).await;
                }
            }
        }
    }

    async fn handle_command(&mut self, command: DaemonCommand) {
        match command {
            DaemonCommand::SendLcdFrame { jpeg, reply } => {
                let result = self.lcd.send_jpeg_frame(&jpeg).await.map_err(|e| e.to_string());
                let _ = reply.send(result);
            }
            DaemonCommand::LcdKeepalive { reply } => {
                let result = self.lcd.keepalive().await.map_err(|e| e.to_string());
                let _ = reply.send(result);
            }
            DaemonCommand::LcdSetConfig { orientation, brightness, reply } => {
                let result = self.lcd.set_display(orientation, brightness).await.map_err(|e| e.to_string());
                let _ = reply.send(result);
            }
            DaemonCommand::SetFans { pump, aio, ext1, ext2, ramp, reply } => {
                let result = self.controller.set_fans(pump, aio, ext1, ext2, ramp).await.map_err(|e| e.to_string());
                let _ = reply.send(result);
            }
            DaemonCommand::SetFanSpeed { channel, speed, reply } => {
                let result = self.controller.set_channel_speed(channel, speed).await.map_err(|e| e.to_string());
                let _ = reply.send(result);
            }
            DaemonCommand::SetLighting { mode, color, speed, saturation, reply } => {
                let result = match mode.to_lowercase().as_str() {
                    "rainbow" => self.controller.set_rainbow(speed, saturation).await,
                    "breathing" | "temperature reactive" => self.controller.set_breathing(color, speed).await,
                    "off" => self.controller.set_always_on([0, 0, 0]).await,
                    _ => self.controller.set_always_on(color).await,
                }.map_err(|e| e.to_string());
                let _ = reply.send(result);
            }
            DaemonCommand::SetMotherboardSync { enable, reply } => {
                let result = self.controller.motherboard_sync(enable).await.map_err(|e| e.to_string());
                let _ = reply.send(result);
            }
        }
    }

    async fn try_connect(&mut self) {
        if !self.lcd.connected {
            match self.lcd.connect().await {
                Ok(_) => {
                    self.set_usb_connected(true).await;
                    if let Err(e) = self.push_theme_frame().await {
                        warn!("Initial frame push failed: {}", e);
                    }
                }
                Err(e) => {
                    warn!("LCD connection failed: {}", e);
                }
            }
        }

        if !self.controller.connected {
            match self.controller.connect().await {
                Ok(_) => {
                    self.set_usb_connected(true).await;
                    // Do NOT seize fan/pump control on connect: monitoring stays
                    // passive until the user (via GUI/IPC) explicitly takes over.
                }
                Err(e) => {
                    warn!("Controller connection failed: {}", e);
                }
            }
        }
    }

    async fn update_rpm_telemetry(&mut self) -> Result<()> {
        let rpm_data = self.controller.read_rpm_passive().await?;

        let mut state = self.state.write().await;
        state.pump_rpm = rpm_data.pump_rpm;
        state.fan_rpm = rpm_data.fan_rpm;

        Ok(())
    }

    /// Snapshot daemon state into themed metrics and stream the frame.
    /// Suspended while GUI-sent content (Studio send / Live Mode) is fresh.
    async fn push_theme_frame(&mut self) -> Result<()> {
        if !self.theme_stream_allowed() {
            return Ok(());
        }
        let metrics = {
            let state = self.state.read().await;
            screen::snapshot(&state)
        };
        let frame = self.renderer.render(&metrics);
        self.lcd.send_rgb_frame(&frame, FRAME_QUALITY).await?;
        Ok(())
    }

    /// Pure decision helper: may the built-in theme stream push right now?
    fn theme_stream_allowed(&self) -> bool {
        let state = {
            // Use try_read so a blocked writer never stalls the USB loop.
            match self.state.try_read() {
                Ok(state) => state,
                Err(_) => return true,
            }
        };
        should_push_theme(
            state.lcd_gui_override,
            state.lcd_gui_override_until_ms,
            now_epoch_ms(),
        )
    }

    async fn set_usb_connected(&self, connected: bool) {
        let mut state = self.state.write().await;
        state.usb_connected = connected;
    }
}

#[cfg(test)]
mod tests {
    use super::should_push_theme;

    #[test]
    fn theme_pushes_when_no_override() {
        assert!(should_push_theme(false, 0, 1_000));
    }

    #[test]
    fn override_holds_fresh_gui_frames() {
        assert!(!should_push_theme(true, 21_000, 5_000));
        assert!(!should_push_theme(true, 21_000, 20_999));
    }

    #[test]
    fn override_expires_and_theme_resumes() {
        assert!(should_push_theme(true, 21_000, 21_000));
    }
}
