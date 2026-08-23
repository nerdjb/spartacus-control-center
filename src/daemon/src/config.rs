// Configuration module for daemon settings

use anyhow::Result;
use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use tokio::fs;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Config {
    pub usb: USBConfig,
    pub cooling: CoolingConfig,
    pub telemetry: TelemetryConfig,
    pub ipc: IPCConfig,
    #[serde(default)]
    pub screen: ScreenConfig,
}

/// LCD theme selection.
/// Available themes: "cards", "cards-light", "colorful", "rings"
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScreenConfig {
    #[serde(default = "default_theme")]
    pub theme: String,
    /// Refresh interval for streamed frames (ms). Designs show a clock with
    /// seconds, so 1000 keeps them ticking; raise to lower USB traffic.
    #[serde(default = "default_refresh_ms")]
    pub refresh_ms: u64,
}

fn default_theme() -> String {
    "cards".to_string()
}

fn default_refresh_ms() -> u64 {
    1000
}

impl Default for ScreenConfig {
    fn default() -> Self {
        Self {
            theme: default_theme(),
            refresh_ms: default_refresh_ms(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct USBConfig {
    pub lcd_vendor_id: u16,
    pub lcd_product_id: u16,
    pub controller_vendor_id: u16,
    pub controller_product_id: u16,
    pub usb_timeout_ms: u64,
    pub frame_rate: u32, // Hz
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CoolingConfig {
    pub pump_min_rpm: u16,
    pub pump_max_rpm: u16,
    pub fan_min_rpm: u16,
    pub fan_max_rpm: u16,
    pub hysteresis: u8,
    pub update_interval_ms: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TelemetryConfig {
    pub hwmon_update_ms: u64,
    pub gpu_update_ms: u64,
    pub cpu_update_ms: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IPCConfig {
    pub socket_path: String,
    pub max_connections: u32,
    pub request_timeout_ms: u64,
}

impl Default for Config {
    fn default() -> Self {
        let runtime_dir = std::env::var("XDG_RUNTIME_DIR")
            .unwrap_or_else(|_| format!("/run/user/{}", unsafe { libc::getuid() }));

        Self {
            usb: USBConfig {
                lcd_vendor_id: 0x3633,
                lcd_product_id: 0x0027,
                controller_vendor_id: 0x3633,
                controller_product_id: 0x002D,
                usb_timeout_ms: 5000,
                frame_rate: 30,
            },
            cooling: CoolingConfig {
                pump_min_rpm: 1500,
                pump_max_rpm: 3000,
                fan_min_rpm: 1000,
                fan_max_rpm: 3000,
                hysteresis: 5,
                update_interval_ms: 1000,
            },
            telemetry: TelemetryConfig {
                hwmon_update_ms: 1000,
                gpu_update_ms: 2000,
                cpu_update_ms: 1000,
            },
            ipc: IPCConfig {
                socket_path: format!("{}/spartacus.sock", runtime_dir),
                max_connections: 10,
                request_timeout_ms: 5000,
            },
            screen: ScreenConfig::default(),
        }
    }
}

pub async fn load_config() -> Result<Config> {
    let config_paths = vec![
        PathBuf::from("/etc/spartacus/config.toml"),
        PathBuf::from(format!(
            "{}/.config/spartacus/config.toml",
            std::env::var("HOME").unwrap_or_default()
        )),
    ];

    for path in config_paths {
        if let Ok(contents) = fs::read_to_string(&path).await {
            if let Ok(config) = toml::from_str(&contents) {
                log::info!("Loaded config from: {:?}", path);
                return Ok(config);
            }
        }
    }

    log::info!("No config file found, using defaults");
    Ok(Config::default())
}

// -- persisted fan curves -------------------------------------------------------
//
// Fan curves edited in the GUI are stored separately from the static daemon
// config so IPC writes never rewrite /etc-managed settings.

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct CurvesFile {
    #[serde(default)]
    pub pump: Vec<(u8, u8)>,
    #[serde(default)]
    pub fans: Vec<Vec<(u8, u8)>>,
}

fn curves_path() -> PathBuf {
    PathBuf::from(format!(
        "{}/.config/spartacus/curves.toml",
        std::env::var("HOME").unwrap_or_default()
    ))
}

/// Blocking read of a tiny TOML file at startup.
pub fn load_curves() -> CurvesFile {
    let path = curves_path();
    match std::fs::read_to_string(&path) {
        Ok(contents) => match toml::from_str(&contents) {
            Ok(curves) => curves,
            Err(e) => {
                log::warn!("Invalid curves file {:?}: {}", path, e);
                CurvesFile::default()
            }
        },
        Err(_) => CurvesFile::default(),
    }
}

pub async fn save_curves(pump: Vec<(u8, u8)>, fans: Vec<Vec<(u8, u8)>>) -> Result<()> {
    let path = curves_path();
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).await?;
    }
    let curves = CurvesFile { pump, fans };
    let contents = toml::to_string_pretty(&curves)?;
    fs::write(&path, contents).await?;
    log::info!("Saved fan curves to {:?}", path);
    Ok(())
}
