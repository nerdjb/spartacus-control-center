// Fan Curve Implementation
// Multi-point temperature-to-RPM curves with hysteresis and smoothing

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FanCurve {
    pub points: Vec<(u8, u8)>, // (Temp°C, RPM%)
    pub hysteresis: u8,         // Temperature hysteresis in °C
    pub smoothing: bool,        // Enable exponential smoothing
    pub min_rpm: u16,
    pub max_rpm: u16,
}

impl FanCurve {
    pub fn new(min_rpm: u16, max_rpm: u16) -> Self {
        Self {
            points: vec![(30, 30), (50, 60), (70, 100)],
            hysteresis: 5,
            smoothing: true,
            min_rpm,
            max_rpm,
        }
    }

    /// Build a curve from user-supplied (temp, duty%) points.
    pub fn from_points(points: Vec<(u8, u8)>, hysteresis: u8, smoothing: bool) -> Self {
        let mut curve = Self::new(1000, 3000);
        if points.len() >= 2 {
            let mut sorted = points;
            sorted.sort_by_key(|(t, _)| *t);
            curve.points = sorted;
        }
        curve.hysteresis = hysteresis;
        curve.smoothing = smoothing;
        curve
    }

    /// Calculate target RPM% based on current temperature
    pub fn calculate_speed(&self, current_temp: u8, last_rpm_percent: u8) -> u8 {
        if self.points.is_empty() {
            return 50;
        }

        // Find surrounding points
        let mut target_rpm = self.points[0].1;

        for window in self.points.windows(2) {
            let (temp1, rpm1) = window[0];
            let (temp2, rpm2) = window[1];

            if current_temp >= temp1 && current_temp <= temp2 {
                // Linear interpolation between two points
                let temp_range = (temp2 - temp1) as f32;
                let rpm_range = (rpm2 - rpm1) as f32;
                let temp_diff = (current_temp - temp1) as f32;

                target_rpm = (rpm1 as f32 + (rpm_range * temp_diff / temp_range)) as u8;
                break;
            } else if current_temp > temp2 {
                target_rpm = rpm2;
            }
        }

        // Apply hysteresis (prevent rapid fluctuations)
        if self.hysteresis > 0 {
            let diff = (target_rpm as i16 - last_rpm_percent as i16).abs() as u8;
            if diff < self.hysteresis {
                return last_rpm_percent;
            }
        }

        // Apply smoothing (exponential moving average)
        if self.smoothing {
            let alpha = 0.7; // Smoothing factor (0-1)
            let smoothed = (alpha * target_rpm as f32 + (1.0 - alpha) * last_rpm_percent as f32) as u8;
            return smoothed;
        }

        target_rpm
    }

    /// Clamp RPM% to valid range
    pub fn clamp_speed(speed_percent: u8) -> u8 {
        std::cmp::min(speed_percent, 100)
    }
}

impl Default for FanCurve {
    fn default() -> Self {
        Self::new(1000, 3000)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_fan_curve_interpolation() {
        let curve = FanCurve::new(1000, 3000);
        assert_eq!(curve.calculate_speed(30, 30), 30);
        assert_eq!(curve.calculate_speed(70, 100), 100);
    }
}
