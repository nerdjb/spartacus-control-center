// DeepCool Spartacus Control Daemon
// Main entry point for USB communication, telemetry, and IPC server

mod config;
mod cooling;
mod ipc;
mod telemetry;
mod usb;

use anyhow::Result;
use log::{error, info, Level, Log, Metadata, Record};
use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};
use tokio::sync::RwLock;

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
    pub pump_curve: Vec<(u8, u8)>, // (Temp%, RPM%)
    pub fan_curves: Vec<Vec<(u8, u8)>>,
    pub rgb_enabled: bool,
    pub rgb_mode: u8,
}

impl Default for DaemonState {
    fn default() -> Self {
        Self {
            usb_connected: false,
            pump_rpm: 0,
            fan_rpm: [0; 6],
            cpu_temp: 0.0,
            gpu_temp: 0.0,
            pump_curve: vec![(30, 30), (50, 60), (70, 100)],
            fan_curves: vec![vec![(30, 30), (50, 60), (70, 100)]; 6],
            rgb_enabled: true,
            rgb_mode: 0,
        }
    }
}

#[tokio::main]
async fn main() -> Result<()> {
    // Initialize logging
    init_logger();

    info!("╔═══════════════════════════════════════════════════╗");
    info!("║  DeepCool Spartacus Control Center - Daemon v0.1  ║");
    info!("║  USB Device Monitor & Cooling Controller          ║");
    info!("╚═══════════════════════════════════════════════════╝");

    // Load configuration
    let config = config::load_config().await?;
    info!("Configuration loaded: {:?}", config);

    // Initialize shared daemon state
    let state = Arc::new(RwLock::new(DaemonState::default()));

    // Start IPC server (UNIX Domain Socket)
    let ipc_server = ipc::server::IPCServer::new(state.clone());
    let ipc_handle = tokio::spawn(async move {
        if let Err(e) = ipc_server.run().await {
            error!("IPC server error: {}", e);
        }
    });

    // Start USB monitor (LCD Display + Controller)
    let usb_monitor = usb::monitor::USBMonitor::new(state.clone());
    let usb_handle = tokio::spawn(async move {
        if let Err(e) = usb_monitor.run().await {
            error!("USB monitor error: {}", e);
        }
    });

    // Start telemetry collector (CPU, GPU temps, etc.)
    let telemetry_collector = telemetry::collector::TelemetryCollector::new(state.clone());
    let telemetry_handle = tokio::spawn(async move {
        if let Err(e) = telemetry_collector.run().await {
            error!("Telemetry collector error: {}", e);
        }
    });

    // Start cooling logic (apply fan curves based on temps)
    let cooler = cooling::controller::CoolingController::new(state.clone());
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
