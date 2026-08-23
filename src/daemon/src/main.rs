// DeepCool Spartacus Control Daemon
// Main entry point for USB communication, telemetry, and IPC server

mod config;
mod cooling;
mod ipc;
mod screen;
mod telemetry;
mod usb;

use anyhow::Result;
use log::{error, info, Level, Log, Metadata, Record};
use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};
use tokio::sync::RwLock;
use tokio::sync::mpsc;

/// Minimal built-in logger (avoids env_logger's jiff dependency chain).
struct SimpleLogger {
    level: Level,
}

impl Log for SimpleLogger {
    fn enabled(&self, metadata: &Metadata) -> bool {
        metadata.level() <= self.level
    }

    fn log(&self, record: &Record) {
        if !self.enabled(record.metadata()) {
            return;
        }
        let secs = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|d| d.as_secs())
            .unwrap_or(0);
        println!(
            "{:02}:{:02}:{:02} [{:<5}] {}",
            (secs / 3600) % 24,
            (secs / 60) % 60,
            secs % 60,
            record.level(),
            record.args()
        );
    }

    fn flush(&self) {}
}

fn init_logger() {
    let level = std::env::var("SPARTACUS_LOG")
        .ok()
        .and_then(|s| s.parse().ok())
        .unwrap_or(Level::Info);
    let _ = log::set_boxed_logger(Box::new(SimpleLogger { level }));
    log::set_max_level(level.to_level_filter());
}

#[derive(Debug, Clone)]
pub struct DaemonState {
    pub usb_connected: bool,
    pub pump_rpm: u16,
    pub fan_rpm: [u16; 6],
    pub cpu_temp: f32,
    pub gpu_temp: f32,
    pub cpu_usage: f32,
    pub cpu_freq_ghz: f32,
    pub gpu_usage: f32,
    pub ram_used_gb: f32,
    pub ram_total_gb: f32,
    pub disk_used_gb: f32,
    pub disk_total_gb: f32,
    pub net_up_kbps: f32,
    pub net_down_kbps: f32,
    pub pump_curve: Vec<(u8, u8)>, // (Temp%, RPM%)
    pub fan_curves: Vec<Vec<(u8, u8)>>,
    pub rgb_enabled: bool,
    pub rgb_mode: u8,
    /// GUI LCD takeover: while active (until epoch-ms deadline) the monitor
    /// suspends its built-in theme stream so Studio/Live frames stay visible.
    pub lcd_gui_override: bool,
    pub lcd_gui_override_until_ms: u64,
    /// Fan control arbitration: true = automatic (curve loop owns duties),
    /// false = manual (GUI sliders/pump writes own them until a curve apply).
    pub fan_control_auto: bool,
}

impl Default for DaemonState {
    fn default() -> Self {
        Self {
            usb_connected: false,
            pump_rpm: 0,
            fan_rpm: [0; 6],
            cpu_temp: 0.0,
            gpu_temp: 0.0,
            cpu_usage: 0.0,
            cpu_freq_ghz: 0.0,
            gpu_usage: 0.0,
            ram_used_gb: 0.0,
            ram_total_gb: 0.0,
            disk_used_gb: 0.0,
            disk_total_gb: 0.0,
            net_up_kbps: 0.0,
            net_down_kbps: 0.0,
            pump_curve: vec![(30, 30), (50, 60), (70, 100)],
            fan_curves: vec![vec![(30, 30), (50, 60), (70, 100)]; 6],
            rgb_enabled: true,
            rgb_mode: 0,
            lcd_gui_override: false,
            lcd_gui_override_until_ms: 0,
            fan_control_auto: true,
        }
    }
}

#[tokio::main]
async fn main() -> Result<()> {
    // Initialize logging
    init_logger();

    // Offline theme preview: --render-theme <name> <out.raw>
    let args: Vec<String> = std::env::args().collect();
    if args.len() >= 4 && args[1] == "--render-theme" {
        let m = screen::Metrics {
            time: "22:26:51".into(),
            date: "2026-04-29".into(),
            cpu_usage: 11.0,
            cpu_temp: 63.0,
            cpu_freq_ghz: 3.77,
            gpu_usage: 8.0,
            gpu_temp: 45.0,
            ram_used_gb: 14.1,
            ram_total_gb: 16.0,
            disk_used_gb: 192.4,
            disk_total_gb: 240.0,
            net_up_kbps: 0.0,
            net_down_kbps: 0.0,
            pump_rpm: 1785,
            fan_rpm: 1300,
        };
        let r = screen::ScreenRenderer::new(&args[2])?;
        let frame = r.render(&m);
        std::fs::write(&args[3], &frame)?;
        info!("Rendered theme {} -> {}", args[2], args[3]);
        return Ok(());
    }

    info!("╔═══════════════════════════════════════════════════╗");
    info!("║  DeepCool Spartacus Control Center - Daemon v0.1  ║");
    info!("║  USB Device Monitor & Cooling Controller          ║");
    info!("╚═══════════════════════════════════════════════════╝");

    // Load configuration
    let config = config::load_config().await?;
    info!("Configuration loaded: {:?}", config);

    // Initialize shared daemon state
    let state = Arc::new(RwLock::new(DaemonState::default()));
    let (command_tx, command_rx) = mpsc::channel(32);
    let command_tx_for_cooling = command_tx.clone();

    // Restore persisted fan curves edited through the GUI.
    {
        let curves = config::load_curves();
        let mut state = state.write().await;
        if curves.pump.len() >= 2 {
            state.pump_curve = curves.pump;
        }
        for (index, points) in curves.fans.into_iter().enumerate().take(6) {
            if points.len() >= 2 {
                state.fan_curves[index] = points;
            }
        }
    }

    // Start IPC server (UNIX Domain Socket)
    let ipc_server = ipc::server::IPCServer::new(state.clone(), command_tx);
    let ipc_handle = tokio::spawn(async move {
        if let Err(e) = ipc_server.run().await {
            error!("IPC server error: {}", e);
        }
    });

    // Start USB monitor (LCD Display + Controller)
    let theme = config.screen.theme.clone();
    let refresh_ms = config.screen.refresh_ms;
    let usb_monitor = usb::monitor::USBMonitor::new(state.clone(), &theme, refresh_ms, command_rx);
    let usb_handle = tokio::spawn(async move {
        match usb_monitor {
            Ok(mut monitor) => {
                if let Err(e) = monitor.run().await {
                    error!("USB monitor error: {}", e);
                }
            }
            Err(e) => {
                error!("USB monitor init failed: {}", e);
            }
        }
    });

    // Start telemetry collector (CPU, GPU temps, etc.)
    let telemetry_collector = telemetry::collector::TelemetryCollector::new(state.clone());
    let telemetry_handle = tokio::spawn(async move {
        telemetry_collector.run().await;
    });

    // Start cooling logic (apply fan curves based on temps)
    let cooler = cooling::controller::CoolingController::new(state.clone(), command_tx_for_cooling);
    let cooling_handle = tokio::spawn(async move {
        if let Err(e) = cooler.run().await {
            error!("Cooling controller error: {}", e);
        }
    });

    info!("✓ All subsystems initialized and running");
    info!("✓ IPC Server listening on /run/user/$UID/spartacus.sock");

    // Handle graceful shutdown
    tokio::signal::ctrl_c().await?;
    info!("Shutdown signal received...");

    // Abort all tasks
    ipc_handle.abort();
    usb_handle.abort();
    telemetry_handle.abort();
    cooling_handle.abort();

    info!("✓ Daemon shutdown complete");
    Ok(())
}
