// Telemetry Collector Implementation
// Reads CPU temp from hwmon, GPU temp from nvidia-smi/amdgpu, and system stats

use crate::DaemonState;
use anyhow::Result;
use log::{debug, error, warn};
use std::sync::Arc;
use tokio::fs;
use tokio::sync::RwLock;
use tokio::time::{interval, Duration};

pub struct TelemetryCollector {
    state: Arc<RwLock<DaemonState>>,
}

impl TelemetryCollector {
    pub fn new(state: Arc<RwLock<DaemonState>>) -> Self {
        Self { state }
    }

    pub async fn run(self) -> Result<()> {
        log::info!("Telemetry Collector starting...");

        let mut cpu_interval = interval(Duration::from_millis(1000));
        let mut gpu_interval = interval(Duration::from_millis(2000));

        loop {
            tokio::select! {
                _ = cpu_interval.tick() => {
                    if let Err(e) = self.update_cpu_telemetry().await {
                        warn!("Failed to read CPU telemetry: {}", e);
                    }
                }

                _ = gpu_interval.tick() => {
                    if let Err(e) = self.update_gpu_telemetry().await {
                        debug!("GPU telemetry unavailable: {}", e);
                    }
                }
            }
        }
    }

    /// Read CPU temperature from hwmon (Linux native)
    async fn update_cpu_telemetry(&self) -> Result<()> {
        // Common hwmon paths for CPU temperature
        let hwmon_paths = vec![
            "/sys/class/hwmon/hwmon0/temp1_input",
            "/sys/class/thermal/thermal_zone0/temp",
            "/sys/devices/virtual/thermal/thermal_zone0/temp",
        ];

        for path in hwmon_paths {
            if let Ok(content) = fs::read_to_string(path).await {
                if let Ok(temp_raw) = content.trim().parse::<f32>() {
                    let temp_c = temp_raw / 1000.0; // hwmon uses millidegrees
                    let mut state = self.state.write().await;
                    state.cpu_temp = temp_c;
                    debug!("CPU Temp: {:.1}°C", temp_c);
                    return Ok(());
                }
            }
        }

        Err(anyhow::anyhow!("No hwmon CPU temperature source found"))
    }

    /// Read GPU temperature (NVIDIA or AMD)
    async fn update_gpu_telemetry(&self) -> Result<()> {
        // Try NVIDIA GPU first
        if let Ok(temp) = self.read_nvidia_gpu_temp().await {
            let mut state = self.state.write().await;
            state.gpu_temp = temp;
            debug!("GPU Temp (NVIDIA): {:.1}°C", temp);
            return Ok(());
        }

        // Try AMD GPU
        if let Ok(temp) = self.read_amd_gpu_temp().await {
            let mut state = self.state.write().await;
            state.gpu_temp = temp;
            debug!("GPU Temp (AMD): {:.1}°C", temp);
            return Ok(());
        }

        Err(anyhow::anyhow!("No GPU temperature source found"))
    }

    /// Read NVIDIA GPU temperature using nvidia-smi
    async fn read_nvidia_gpu_temp(&self) -> Result<f32> {
        let output = tokio::process::Command::new("nvidia-smi")
            .args(&["--query-gpu=temperature.gpu", "--format=csv,noheader"])
            .output()
            .await?;

        let stdout = String::from_utf8(output.stdout)?;
        let temp_str = stdout.trim().split_whitespace().next().unwrap_or("0");
        let temp = temp_str.parse::<f32>()?;

        Ok(temp)
    }

    /// Read AMD GPU temperature from amdgpu sysfs
    async fn read_amd_gpu_temp(&self) -> Result<f32> {
        // Common AMD GPU hwmon paths
        let amd_paths = vec![
            "/sys/class/hwmon/hwmon*/temp2_input", // GPU die temp
            "/sys/devices/pci0000:00/*/hwmon/hwmon*/temp2_input",
        ];

        for path_pattern in amd_paths {
            if path_pattern.contains('*') {
                // Handle glob pattern
                if let Ok(content) = fs::read_to_string(path_pattern).await {
                    if let Ok(temp_raw) = content.trim().parse::<f32>() {
                        return Ok(temp_raw / 1000.0);
                    }
                }
            }
        }

        Err(anyhow::anyhow!("AMD GPU temperature not found"))
    }
}
