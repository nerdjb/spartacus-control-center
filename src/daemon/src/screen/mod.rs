// Screen theme engine: loads fonts, snapshots metrics, renders themed frames.

pub mod draw;
pub mod helpers;
pub mod themes;
pub mod themes_cards;
pub mod themes_fx;

use anyhow::Result;
use chrono::Local;
use fontdue::Font;
use std::path::PathBuf;

/// Snapshot of everything the themes draw.
#[derive(Debug, Clone)]
pub struct Metrics {
    pub time: String,
    pub date: String,
    pub cpu_usage: f32,
    pub cpu_temp: f32,
    pub cpu_freq_ghz: f32,
    pub gpu_usage: f32,
    pub gpu_temp: f32,
    pub ram_used_gb: f32,
    pub ram_total_gb: f32,
    pub disk_used_gb: f32,
    pub disk_total_gb: f32,
    pub net_up_kbps: f32,
    pub net_down_kbps: f32,
    pub pump_rpm: u16,
    pub fan_rpm: u16,
}

impl Metrics {
    pub fn cpu_pct(&self) -> f32 {
        self.cpu_usage.clamp(0.0, 100.0)
    }
    pub fn gpu_pct(&self) -> f32 {
        self.gpu_usage.clamp(0.0, 100.0)
    }
    pub fn ram_pct(&self) -> f32 {
        if self.ram_total_gb > 0.0 {
            (self.ram_used_gb / self.ram_total_gb * 100.0).clamp(0.0, 100.0)
        } else {
            0.0
        }
    }
    pub fn disk_pct(&self) -> f32 {
        if self.disk_total_gb > 0.0 {
            (self.disk_used_gb / self.disk_total_gb * 100.0).clamp(0.0, 100.0)
        } else {
            0.0
        }
    }
    /// Pump duty approximation for gauges (3500 RPM = 100%).
    pub fn pump_pct(&self) -> f32 {
        (self.pump_rpm.min(3500) as f32 / 3500.0 * 100.0).clamp(0.0, 100.0)
    }
}

pub struct ScreenRenderer {
    font: Font,
    theme: String,
}

impl ScreenRenderer {
    /// Load a bold system sans font and select the initial theme.
    pub fn new(theme: &str) -> Result<Self> {
        let bytes = load_font_bytes()?;
        let settings = fontdue::FontSettings {
            collection_index: 0,
            scale: 40.0,
            ..Default::default()
        };
        let font =
            Font::from_bytes(bytes, settings).map_err(|e| anyhow::anyhow!("font parse: {e}"))?;
        log::info!("Screen renderer ready (theme: {theme})");
        Ok(Self {
            font,
            theme: theme.to_string(),
        })
    }

    pub fn set_theme(&mut self, theme: &str) {
        self.theme = theme.to_string();
    }

    /// Render the configured theme into an RGB888 480x480 frame.
    pub fn render(&self, m: &Metrics) -> Vec<u8> {
        let mut canvas = draw::Canvas::new(480, 480);
        match self.theme.as_str() {
            "colorful" => themes::colorful(&mut canvas, m, &self.font),
            "cards-light" => themes::cards_light(&mut canvas, m, &self.font),
            "rings" => themes::rings(&mut canvas, m, &self.font),
            _ => themes::cards(&mut canvas, m, &self.font),
        }
        canvas.px
    }
}

/// Search common Linux font locations for a bold sans TTF.
fn load_font_bytes() -> Result<Vec<u8>> {
    let candidates = [
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/noto/NotoSans-Bold.ttf",
        "/usr/share/fonts/TTF/NotoSans-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        "/usr/share/fonts/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/cantarell/Cantarell-Bold.otf",
    ];
    for path in candidates {
        if let Ok(bytes) = std::fs::read(path) {
            return Ok(bytes);
        }
    }

    // Last resort: recursive scan for any Bold ttf/otf
    if let Some(hit) = scan_dir(PathBuf::from("/usr/share/fonts"), 4) {
        return Ok(std::fs::read(hit)?);
    }
    Err(anyhow::anyhow!("no suitable bold TTF font found"))
}

fn scan_dir(dir: PathBuf, depth: u8) -> Option<PathBuf> {
    if depth == 0 {
        return None;
    }
    if let Ok(entries) = std::fs::read_dir(&dir) {
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_file() {
                let name = path.file_name()?.to_string_lossy().to_lowercase();
                if name.ends_with(".ttf") && name.contains("bold") {
                    return Some(path);
                }
            } else if path.is_dir() {
                if let Some(found) = scan_dir(path, depth - 1) {
                    return Some(found);
                }
            }
        }
    }
    None
}

/// Build a metrics snapshot from daemon state + wall clock.
pub fn snapshot(state: &crate::DaemonState) -> Metrics {
    let now = Local::now();
    Metrics {
        time: now.format("%H:%M:%S").to_string(),
        date: now.format("%Y-%m-%d").to_string(),
        cpu_usage: state.cpu_usage,
        cpu_temp: state.cpu_temp,
        cpu_freq_ghz: state.cpu_freq_ghz,
        gpu_usage: state.gpu_usage,
        gpu_temp: state.gpu_temp,
        ram_used_gb: state.ram_used_gb,
        ram_total_gb: state.ram_total_gb,
        disk_used_gb: state.disk_used_gb,
        disk_total_gb: state.disk_total_gb,
        net_up_kbps: state.net_up_kbps,
        net_down_kbps: state.net_down_kbps,
        pump_rpm: state.pump_rpm,
        fan_rpm: state.fan_rpm[0],
    }
}
