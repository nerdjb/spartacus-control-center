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
use tokio::time::{interval, Duration};

use super::controller::ControllerDevice;
use super::lcd::LCDDevice;

const FRAME_QUALITY: u8 = 88;

pub struct USBMonitor {
    state: Arc<RwLock<DaemonState>>,
    lcd: LCDDevice,
    controller: ControllerDevice,
    renderer: ScreenRenderer,
    refresh_ms: u64,
}

impl USBMonitor {
    pub fn new(
        state: Arc<RwLock<DaemonState>>,
        theme: &str,
        refresh_ms: u64,
    ) -> Result<Self> {
        Ok(Self {
            state,
            lcd: LCDDevice::new(),
            controller: ControllerDevice::new(),
            renderer: ScreenRenderer::new(theme)?,
            refresh_ms,
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
    async fn push_theme_frame(&mut self) -> Result<()> {
        let metrics = {
            let state = self.state.read().await;
            screen::snapshot(&state)
        };
        let frame = self.renderer.render(&metrics);
        self.lcd.send_rgb_frame(&frame, FRAME_QUALITY).await?;
        Ok(())
    }

    async fn set_usb_connected(&self, connected: bool) {
        let mut state = self.state.write().await;
        state.usb_connected = connected;
    }
}
