// Telemetry subsystem module
// Collects system metrics: CPU temp, GPU temp, utilization, etc.

pub mod collector;
pub mod sysfs;

pub use collector::TelemetryCollector;

#[derive(Debug, Clone)]
pub struct TelemetryData {
    pub cpu_temp: f32,
    pub gpu_temp: f32,
    pub cpu_usage: f32,
    pub gpu_usage: f32,
    pub memory_used: u64,
    pub memory_total: u64,
}

impl Default for TelemetryData {
    fn default() -> Self {
        Self {
            cpu_temp: 0.0,
            gpu_temp: 0.0,
            cpu_usage: 0.0,
            gpu_usage: 0.0,
            memory_used: 0,
            memory_total: 0,
        }
    }
}
