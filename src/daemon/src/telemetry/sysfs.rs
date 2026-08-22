// System metric readers: /proc, /sys, statvfs.
// Pure functions; no shared state.

use anyhow::Result;
use tokio::fs;

/// CPU temperature from hwmon (prefers k10temp/coretemp/cpu_thermal),
/// falls back to thermal zones. Returns degrees C.
pub async fn cpu_temp() -> Result<f32> {
    const PREFERRED: [&str; 4] = ["k10temp", "coretemp", "cpu_thermal", "zenpower"];

    if let Ok(mut entries) = fs::read_dir("/sys/class/hwmon").await {
        while let Ok(Some(entry)) = entries.next_entry().await {
            let name = fs::read_to_string(entry.path().join("name"))
                .await
                .unwrap_or_default();
            if !PREFERRED.iter().any(|p| name.trim().eq_ignore_ascii_case(p)) {
                continue;
            }
            for input in ["temp1_input", "temp2_input", "temp3_input"] {
                if let Some(t) = read_milli_degrees(&entry.path().join(input).to_string_lossy()).await {
                    return Ok(t);
                }
            }
        }
    }

    for zone in [
        "/sys/class/thermal/thermal_zone0/temp",
        "/sys/devices/virtual/thermal/thermal_zone0/temp",
    ] {
        if let Some(t) = read_milli_degrees(zone).await {
            return Ok(t);
        }
    }
    Err(anyhow::anyhow!("no CPU temperature source found"))
}

async fn read_milli_degrees(path: &str) -> Option<f32> {
    let content = fs::read_to_string(path).await.ok()?;
    content.trim().parse::<f32>().ok().map(|raw| raw / 1000.0)
}

/// Current CPU frequency in GHz from cpufreq.
pub async fn cpu_freq_ghz() -> Result<f32> {
    let content =
        fs::read_to_string("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq").await?;
    let khz: f32 = content.trim().parse()?;
    Ok(khz / 1_000_000.0)
}

/// First line of /proc/stat parsed as (idle, total) jiffies.
pub async fn cpu_times() -> Result<(u64, u64)> {
    let content = fs::read_to_string("/proc/stat").await?;
    let line = content.lines().next().ok_or_else(|| anyhow::anyhow!("empty"))?;
    let vals: Vec<u64> = line
        .split_whitespace()
        .skip(1)
        .filter_map(|v| v.parse().ok())
        .collect();
    if vals.len() < 5 {
        return Err(anyhow::anyhow!("unexpected /proc/stat layout"));
    }
    let idle = vals[3] + vals[4];
    let total: u64 = vals.iter().sum();
    Ok((idle, total))
}

/// GPU (temperature C, usage %): amdgpu sysfs first, nvidia-smi fallback.
pub async fn gpu_telemetry() -> Option<(f32, f32)> {
    if let Ok(mut entries) = fs::read_dir("/sys/class/hwmon").await {
        while let Ok(Some(entry)) = entries.next_entry().await {
            let name = fs::read_to_string(entry.path().join("name"))
                .await
                .unwrap_or_default();
            if !name.trim().eq_ignore_ascii_case("amdgpu") {
                continue;
            }
            if let Some(temp) = read_milli_degrees(&entry.path().join("temp1_input").to_string_lossy()).await {
                let usage = fs::read_to_string("/sys/class/drm/card0/device/gpu_busy_percent")
                    .await
                    .ok()
                    .and_then(|c| c.trim().parse::<f32>().ok());
                return Some((temp, usage.unwrap_or(0.0)));
            }
        }
    }

    let output = tokio::process::Command::new("nvidia-smi")
        .args([
            "--query-gpu=temperature.gpu,utilization.gpu",
            "--format=csv,noheader,nounits",
        ])
        .output()
        .await
        .ok()?;
    let stdout = String::from_utf8(output.stdout).ok()?;
    let parts: Vec<&str> = stdout.trim().split(',').map(str::trim).collect();
    if parts.len() >= 2 {
        return Some((parts[0].parse().ok()?, parts[1].parse().ok()?));
    }
    None
}

/// RAM (used GB, total GB) from /proc/meminfo.
pub async fn ram_gb() -> Result<(f32, f32)> {
    let content = fs::read_to_string("/proc/meminfo").await?;
    let get = |key: &str| -> Option<f32> {
        content.lines().find_map(|l| {
            if !l.starts_with(key) {
                return None;
            }
            l.split_whitespace().nth(1)?.parse::<f32>().ok()
        })
    };
    let total_kb = get("MemTotal:").ok_or_else(|| anyhow::anyhow!("no MemTotal"))?;
    let avail_kb = get("MemAvailable:").unwrap_or(total_kb);
    Ok(((total_kb - avail_kb) / 1024.0 / 1024.0, total_kb / 1024.0 / 1024.0))
}

/// Root filesystem (used GB, total GB) via statvfs.
pub fn disk_gb() -> Result<(f32, f32)> {
    use std::os::unix::ffi::OsStrExt;
    let path = std::ffi::CString::new("/").map_err(|e| anyhow::anyhow!("{e}"))?;
    let mut vfs: libc::statvfs = unsafe { std::mem::zeroed() };
    let rc = unsafe { libc::statvfs(path.as_ptr(), &mut vfs) };
    if rc != 0 {
        return Err(anyhow::anyhow!("statvfs failed"));
    }
    let block = vfs.f_frsize as u64;
    let total = block * vfs.f_blocks;
    let free = block * vfs.f_bfree;
    let used = total.saturating_sub(free);
    Ok((
        used as f32 / 1024.0 / 1024.0 / 1024.0,
        total as f32 / 1024.0 / 1024.0 / 1024.0,
    ))
}

/// Total network bytes across all interfaces except lo: (rx, tx).
pub async fn net_bytes() -> Result<(u64, u64)> {
    let content = fs::read_to_string("/proc/net/dev").await?;
    let mut rx_total = 0u64;
    let mut tx_total = 0u64;
    for line in content.lines().skip(2) {
        let Some((iface, data)) = line.split_once(':') else { continue };
        if iface.trim() == "lo" {
            continue;
        }
        let vals: Vec<u64> = data
            .split_whitespace()
            .filter_map(|v| v.parse().ok())
            .collect();
        if vals.len() >= 9 {
            rx_total += vals[0];
            tx_total += vals[8];
        }
    }
    Ok((rx_total, tx_total))
}
