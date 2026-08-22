// USB Monitor - Main orchestrator for LCD Display and Linker Controller
//
// Responsibilities:
//   - Connect/reconnect both USB devices (LCD 3633:0027, Linker 3633:002D)
//   - Poll Linker tachometry passively (~2 Hz) into shared daemon state
//   - Render a status frame to the LCD every SCREEN_INTERVAL_SECS; this also
//     acts as the keepalive against the panel's ~15 s logo watchdog

use crate::DaemonState;
use anyhow::Result;
use log::{error, info, warn};
use std::sync::Arc;
use tokio::sync::RwLock;
use tokio::time::{interval, Duration};

use super::controller::ControllerDevice;
use super::lcd::LCDDevice;

const SCREEN_INTERVAL_SECS: u64 = 10;
const FRAME_QUALITY: u8 = 85;

pub struct USBMonitor {
    state: Arc<RwLock<DaemonState>>,
    lcd: LCDDevice,
    controller: ControllerDevice,
}

impl USBMonitor {
    pub fn new(state: Arc<RwLock<DaemonState>>) -> Self {
        Self {
            state,
            lcd: LCDDevice::new(),
            controller: ControllerDevice::new(),
        }
    }

    pub async fn run(mut self) -> Result<()> {
        info!("USB Monitor starting...");

        let mut connect_interval = interval(Duration::from_secs(2));
        let mut rpm_interval = interval(Duration::from_millis(500));
        let mut screen_interval = interval(Duration::from_secs(SCREEN_INTERVAL_SECS));

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
                    if let Err(e) = self.push_status_frame(FRAME_QUALITY).await {
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
                    // Push an initial frame right away so the panel leaves its logo.
                    if let Err(e) = self.push_status_frame(FRAME_QUALITY).await {
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

    /// Render the current daemon state into an RGB frame and stream it to the LCD.
    async fn push_status_frame(&mut self, quality: u8) -> Result<()> {
        let (cpu_temp, pump_rpm, fan_rpm) = {
            let state = self.state.read().await;
            (state.cpu_temp, state.pump_rpm, state.fan_rpm[0])
        };
        let frame = render_status_frame(cpu_temp, pump_rpm, fan_rpm);
        self.lcd.send_rgb_frame(&frame, quality).await?;
        debug_frame_push(cpu_temp);
        Ok(())
    }

    async fn set_usb_connected(&self, connected: bool) {
        let mut state = self.state.write().await;
        state.usb_connected = connected;
    }
}

fn debug_frame_push(cpu_temp: f32) {
    log::debug!("Status frame pushed (cpu_temp={})", cpu_temp);
}

/// Draw a 480x480 RGB888 status frame without any font dependency:
/// dark background, temperature bar (blue->red), and RPM activity bars.
fn render_status_frame(cpu_temp: f32, pump_rpm: u16, fan_rpm: u16) -> Vec<u8> {
    let w = super::LCD_WIDTH as usize;
    let h = super::LCD_HEIGHT as usize;
    let mut rgb = vec![0u8; w * h * 3];

    // Background: subtle vertical gradient 18..30
    for y in 0..h {
        let shade = (18 + (30 - 18) * y / h) as u8;
        for x in 0..w {
            let idx = (y * w + x) * 3;
            rgb[idx] = shade / 3;
            rgb[idx + 1] = shade / 2;
            rgb[idx + 2] = shade;
        }
    }

    let temp_clamped = cpu_temp.clamp(20.0, 90.0);

    // Temperature bar: horizontal, upper half
    draw_bar(
        &mut rgb,
        w,
        h,
        40,
        120,
        400,
        80,
        temp_clamped as u32,
        70,
        &temp_color(temp_clamped),
    );

    // Pump RPM bar: lower half, normalized to 3500 RPM
    let pump_pct = (pump_rpm.min(3500) as u32 * 100 / 3500).max(1);
    draw_bar(
        &mut rgb, w, h, 40, 260, 400, 60, pump_pct, 100, &[40, 200, 120],
    );

    // Fan RPM bar: below pump bar
    let fan_pct = (fan_rpm.min(2500) as u32 * 100 / 2500).max(1);
    draw_bar(
        &mut rgb, w, h, 40, 360, 400, 60, fan_pct, 100, &[230, 160, 40],
    );

    rgb
}

fn temp_color(temp: f32) -> [u8; 3] {
    // 20C blue -> 55C green -> 90C red
    let (r, g, b) = if temp < 55.0 {
        let t = ((temp - 20.0) / 35.0).clamp(0.0, 1.0);
        (t * 40.0, 80.0 + t * 140.0, 220.0 - t * 180.0)
    } else {
        let t = ((temp - 55.0) / 35.0).clamp(0.0, 1.0);
        (40.0 + t * 215.0, 220.0 - t * 180.0, 40.0)
    };
    [r as u8, g as u8, b as u8]
}

#[allow(clippy::too_many_arguments)]
fn draw_bar(
    rgb: &mut [u8],
    w: usize,
    _h: usize,
    x0: usize,
    y0: usize,
    bar_w: usize,
    bar_h: usize,
    pct: u32,
    scale_max_pct: u32,
    color: &[u8; 3],
) {
    let fill_w = bar_w * pct.min(scale_max_pct) as usize / scale_max_pct.max(1) as usize;

    for y in y0..(y0 + bar_h).min(_h) {
        for x in x0..(x0 + bar_w).min(w) {
            let idx = (y * w + x) * 3;
            let filled = x < x0 + fill_w;
            let border_y = y == y0 || y == y0 + bar_h - 1;
            let border_x = x == x0 || x == x0 + bar_w - 1;
            if border_x || border_y {
                rgb[idx] = 90;
                rgb[idx + 1] = 90;
                rgb[idx + 2] = 100;
            } else if filled {
                rgb[idx] = color[0];
                rgb[idx + 1] = color[1];
                rgb[idx + 2] = color[2];
            }
        }
    }
}
