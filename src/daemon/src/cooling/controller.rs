// Cooling Controller Implementation
// Applies fan curves and sends commands to hardware

use crate::DaemonState;
use anyhow::Result;
use log::{debug, info};
use std::sync::Arc;
use tokio::sync::RwLock;
use tokio::sync::mpsc::Sender;
use tokio::sync::oneshot;
use tokio::time::{interval, Duration};

use super::curves::FanCurve;

pub struct CoolingController {
    state: Arc<RwLock<DaemonState>>,
    pump_curve: FanCurve,
    fan_curves: Vec<FanCurve>,
    last_pump_speed: u8,
    last_fan_speeds: [u8; 6],
    commands: Sender<crate::ipc::DaemonCommand>,
}

impl CoolingController {
    pub fn new(state: Arc<RwLock<DaemonState>>, commands: Sender<crate::ipc::DaemonCommand>) -> Self {
        let pump_curve = FanCurve::new(1500, 3000);
        let fan_curves = vec![FanCurve::new(1000, 3000); 6];

        Self {
            state,
            pump_curve,
            fan_curves,
            last_pump_speed: 50,
            last_fan_speeds: [50; 6],
            commands,
        }
    }

    pub async fn run(mut self) -> Result<()> {
        info!("Cooling Controller starting...");

        let mut control_interval = interval(Duration::from_millis(1000));

        loop {
            control_interval.tick().await;

            // In manual mode (GUI slider/pump writes) the automatic loop stays
            // hands-off; a SetFanCurve apply flips back to auto.
            if !self.state.read().await.fan_control_auto {
                continue;
            }

            // Curves live in DaemonState so IPC SetFanCurve edits take effect
            // on the next tick without restarting the controller.
            let (pump_points, fan_points) = {
                let state = self.state.read().await;
                (
                    state.pump_curve.clone(),
                    [
                        state.fan_curves[0].clone(),
                        state.fan_curves[1].clone(),
                        state.fan_curves[2].clone(),
                    ],
                )
            };
            let pump_curve = FanCurve::from_points(pump_points, 2, true);
            let fan_curves: Vec<FanCurve> = fan_points
                .into_iter()
                .map(|points| FanCurve::from_points(points, 3, true))
                .collect();

            let cpu_temp = self.state.read().await.cpu_temp as u8;
            let gpu_temp = self.state.read().await.gpu_temp as u8;

            // Calculate target pump speed based on CPU temp
            let target_pump_speed = pump_curve.calculate_speed(cpu_temp, self.last_pump_speed);

            // Calculate target fan speeds: CPU-driven for aio, GPU for ext1/ext2.
            let mut target_fan_speeds = [0u8; 6];
            for i in 0..6 {
                let temp = if i == 0 { cpu_temp } else { gpu_temp };
                target_fan_speeds[i] =
                    fan_curves[i.min(fan_curves.len() - 1)].calculate_speed(temp, self.last_fan_speeds[i]);
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

            // Push evaluated duties through the monitor's USB command channel,
            // exactly like manual GUI writes; the controller enforces the
            // 40% pump floor again at the hardware layer.
            let (reply, response) = oneshot::channel();
            if self
                .commands
                .send(crate::ipc::DaemonCommand::SetFans {
                    pump: target_pump_speed.max(40),
                    aio: target_fan_speeds[0],
                    ext1: target_fan_speeds[1],
                    ext2: target_fan_speeds[2],
                    ramp: 0,
                    reply,
                })
                .await
                .is_ok()
            {
                let _ = response.await;
            }
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
