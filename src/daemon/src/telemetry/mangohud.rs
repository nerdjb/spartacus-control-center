// MangoHud CSV log tailing: turns in-game FPS/frametime into panel metrics.
//
// MangoHud (preinstalled on Steam Deck / widely packaged) writes a CSV per
// game session when logging is enabled. Point its `output_folder` at
// ~/.config/spartacus/mangohud (see README) and this sampler picks up
// `fps` and `frametime` from the newest log. No game running -> None,
// which renders as "--" on the panel (never fake zeros).

use anyhow::Result;
use std::fs;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

/// Candidate MangoHud log folders: GOverlay's default output, our own
/// documented folder, and MangoHud's plain default.
pub fn log_dirs() -> Vec<PathBuf> {
    let home = std::env::var("HOME").unwrap_or_default();
    vec![
        PathBuf::from(format!("{}/.local/share/goverlay", home)),
        PathBuf::from(format!("{}/.config/spartacus/mangohud", home)),
        PathBuf::from(format!("{}/mangohud_logs", home)),
    ]
}

pub fn latest_sample_from_dirs() -> Option<(f32, f32)> {
    log_dirs().iter().find_map(|d| latest_sample(d))
}

/// (fps, frametime_ms) from the freshest MangoHud CSV, if it is current.
pub fn latest_sample(dir: &Path) -> Option<(f32, f32)> {
    let csv = newest_csv(dir)?;
    let age = fs::metadata(&csv).ok()?.modified().ok()?.elapsed().ok()?;
    if age.as_secs() > 3 {
        return None; // game closed or logging stopped
    }
    parse_last_row(&csv).ok()
}

fn newest_csv(dir: &Path) -> Option<PathBuf> {
    let mut best: Option<(SystemTime, PathBuf)> = None;
    for entry in fs::read_dir(dir).ok()?.flatten() {
        let path = entry.path();
        if path.extension()?.to_str()? != "csv" {
            continue;
        }
        let modified = entry.metadata().ok()?.modified().ok()?;
        if best.as_ref().map(|(t, _)| modified > *t).unwrap_or(true) {
            best = Some((modified, path));
        }
    }
    best.map(|(_, p)| p)
}

fn parse_last_row(path: &Path) -> Result<(f32, f32)> {
    let content = fs::read_to_string(path)?;
    let mut lines = content.lines().filter(|l| !l.trim().is_empty());
    let header = lines.next().ok_or_else(|| anyhow::anyhow!("empty log"))?;
    let cols: Vec<String> = header.split(',').map(|c| c.trim().to_lowercase()).collect();
    let fps_i = cols.iter().position(|c| c == "fps").ok_or_else(|| anyhow::anyhow!("no fps column"))?;
    let ft_i = cols
        .iter()
        .position(|c| c == "frametime" || c == "frame_time")
        .unwrap_or(fps_i);
    let last = lines.last().ok_or_else(|| anyhow::anyhow!("no rows"))?;
    let cells: Vec<&str> = last.split(',').collect();
    let fps = cells.get(fps_i).and_then(|v| v.trim().parse().ok()).unwrap_or(0.0);
    let frametime = cells.get(ft_i).and_then(|v| v.trim().parse().ok()).unwrap_or(0.0);
    Ok((fps, frametime))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_mangohud_row() {
        let dir = std::env::temp_dir().join("spartacus-mangohud-test");
        let _ = fs::remove_dir_all(&dir);
        fs::create_dir_all(&dir).unwrap();
        let file = dir.join("game_2026-01-01_00-00-00.csv");
        fs::write(
            &file,
            "lap,cpu,gpu_load,fps,frametime,elapsed\n1,12,40,143.2,6.98,0.1\n2,12,41,141.9,7.05,0.2\n",
        )
        .unwrap();
        let (fps, frametime) = latest_sample(&dir).unwrap();
        assert!((fps - 141.9).abs() < 0.01);
        assert!((frametime - 7.05).abs() < 0.01);
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn missing_dir_is_none() {
        assert!(latest_sample(Path::new("/nonexistent-dir-xyz")).is_none());
    }
}
