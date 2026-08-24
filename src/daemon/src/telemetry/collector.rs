// Telemetry Collector
// Samples CPU/GPU temps + usage, CPU frequency, RAM, disk usage, and network
// rates once per second into shared DaemonState.

use crate::DaemonState;
use log::debug;
use std::sync::Arc;
use tokio::sync::RwLock;
use tokio::time::{interval, Duration};

use super::{mangohud, sysfs};

pub struct TelemetryCollector {
    state: Arc<RwLock<DaemonState>>,
    prev_cpu_times: Option<(u64, u64)>, // (idle, total)
    prev_net_bytes: Option<(u64, u64)>, // (rx, tx)
    prev_pkg_energy: Option<(std::time::Instant, f64)>, // RAPL/MSR joules
}

impl TelemetryCollector {
    pub fn new(state: Arc<RwLock<DaemonState>>) -> Self {
        Self {
            state,
            prev_cpu_times: None,
            prev_net_bytes: None,
            prev_pkg_energy: None,
        }
    }

    pub async fn run(mut self) {
        log::info!("Telemetry Collector starting...");
        let mut tick = interval(Duration::from_millis(1000));

        loop {
            tick.tick().await;
            self.update_all().await;
        }
    }

    async fn update_all(&mut self) {
        let cpu_temp = sysfs::cpu_temp().await.unwrap_or(0.0);
        let cpu_freq = sysfs::cpu_freq_ghz().await.unwrap_or(0.0);
        let cpu_usage = self.cpu_usage().await;
        let gpu = sysfs::gpu_telemetry().await;
        let ram = sysfs::ram_gb().await.ok();
        let disk = sysfs::disk_gb().ok();
        let net = self.net_rates().await;
        let cpu_watts = sysfs::cpu_power_watts(&mut self.prev_pkg_energy).await;
        let gpu_watts = sysfs::gpu_power_watts().await;

        {
            let mut state = self.state.write().await;
            state.cpu_temp = cpu_temp;
            state.cpu_usage = cpu_usage;
            state.cpu_freq_ghz = cpu_freq;
            if let Some((temp, usage)) = gpu {
                state.gpu_temp = temp;
                state.gpu_usage = usage;
            }
            if let Some((used, total)) = ram {
                state.ram_used_gb = used;
                state.ram_total_gb = total;
            }
            if let Some((used, total)) = disk {
                state.disk_used_gb = used;
                state.disk_total_gb = total;
            }
            state.net_down_kbps = net.0;
            state.net_up_kbps = net.1;
            if let Some(w) = cpu_watts {
                state.cpu_watts = w;
            }
            if let Some(w) = gpu_watts {
                state.gpu_watts = w;
            }
            if let Some((fps, frametime)) = mangohud::latest_sample_from_dirs() {
                state.fps = fps;
                state.frametime_ms = frametime;
            } else {
                state.fps = 0.0;
                state.frametime_ms = 0.0;
            }
        }

        debug!(
            "CPU {}% {:.2}GHz {:.0}C | GPU {:.0}% | RAM {:.1}/{:.1}GB | NET d{:.0} u{:.0} kB/s",
            cpu_usage as u8,
            cpu_freq,
            cpu_temp,
            gpu.map(|g| g.1).unwrap_or(0.0),
            ram.map(|r| r.0).unwrap_or(0.0),
            ram.map(|r| r.1).unwrap_or(0.0),
            net.0,
            net.1
        );
    }

    /// CPU usage % from /proc/stat deltas between ticks.
    async fn cpu_usage(&mut self) -> f32 {
        let Ok((idle, total)) = sysfs::cpu_times().await else {
            return 0.0;
        };
        let usage = match self.prev_cpu_times {
            Some((pidle, ptotal)) => {
                let dt = total.saturating_sub(ptotal);
                let di = idle.saturating_sub(pidle);
                if dt > 0 {
                    ((dt - di) as f32 / dt as f32 * 100.0).clamp(0.0, 100.0)
                } else {
                    0.0
                }
            }
            None => 0.0,
        };
        self.prev_cpu_times = Some((idle, total));
        usage
    }

    /// Network rates in kB/s from cumulative byte counters.
    async fn net_rates(&mut self) -> (f32, f32) {
        let Ok((rx, tx)) = sysfs::net_bytes().await else {
            return (0.0, 0.0);
        };
        let rates = match self.prev_net_bytes {
            Some((prx, ptx)) => (
                rx.saturating_sub(prx) as f32 / 1024.0,
                tx.saturating_sub(ptx) as f32 / 1024.0,
            ),
            None => (0.0, 0.0),
        };
        self.prev_net_bytes = Some((rx, tx));
        rates
    }
}
