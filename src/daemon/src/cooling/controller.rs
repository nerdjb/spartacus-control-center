// Cooling Controller Implementation
// Applies fan curves and sends commands to hardware

use crate::DaemonState;
use anyhow::Result;
use log::{debug, info};
use std::sync::Arc;
use tokio::sync::RwLock;
use tokio::time::{interval, Duration};

use super::curves::FanCurve;

pub struct CoolingController {
    state: Arc<RwLock<DaemonState>>,
    pump_curve: FanCurve,
    fan_curves: Vec<FanCurve>,
    last_pump_speed: u8,
    last_fan_speeds: [u8; 6],
}

impl CoolingController {
    pub fn new(state: Arc<RwLock<DaemonState>>) -> Self {
        let pump_curve = FanCurve::new(1500, 3000);
        let fan_curves = vec![FanCurve::new(1000, 3000); 6];

        Self {
            state,
            pump_curve,
            fan_curves,
            last_pump_speed: 50,
            last_fan_speeds: [50; 6],
        }
    }

    pub async fn run(mut self) -> Result<()> {
        info!("Cooling Controller starting...");

        let mut control_interval = interval(Duration::from_millis(1000));

        loop {
            control_interval.tick().await;

            let state = self.state.read().await;

            // Calculate target pump speed based on CPU temp
            let cpu_temp = state.cpu_temp as u8;
            let target_pump_speed = self.pump_curve.calculate_speed(cpu_temp, self.last_pump_speed);

            // Calculate target fan speeds
            // Use CPU temp for most fans, GPU temp for some
            let gpu_temp = state.gpu_temp as u8;

            let mut target_fan_speeds = [0u8; 6];
            for i in 0..6 {
                let temp = if i < 3 { cpu_temp } else { gpu_temp };
                target_fan_speeds[i] = self.fan_curves[i].calculate_speed(temp, self.last_fan_speeds[i]);
            }

            // Only log if speeds changed significantly
            if target_pump_speed != self.last_pump_speed {
                debug!(
                    "Pump speed: {}% → {}% (CPU: {}°C)",
                    self.last_pump_speed, target_pump_speed, cpu_temp
                );
            }

            self.last_pump_speed = target_pump_speed;
            self.last_fan_speeds = target_fan_speeds;
        }
    }

    /// Load custom fan curve from file
    pub fn load_curve(&mut self, data: Vec<(u8, u8)>) -> Result<()> {
        if data.len() < 2 {
            return Err(anyhow::anyhow!("Fan curve must have at least 2 points"));
        }

        let mut curve = self.pump_curve.clone();
        curve.points = data;
        self.pump_curve = curve;

        Ok(())
    }
}
