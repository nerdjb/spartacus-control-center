// System metric readers: /proc, /sys, statvfs.
// Pure functions; no shared state.

use anyhow::Result;
use std::path::PathBuf;
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

// ---------------------------------------------------------------- power

/// GPU power draw in watts: amdgpu exposes `power1_average` (microwatts).
/// Fallback: NVIDIA `nvidia-smi --query-gpu=power.draw`.
pub async fn gpu_power_watts() -> Option<f32> {
    if let Ok(mut entries) = fs::read_dir("/sys/class/hwmon").await {
        while let Ok(Some(entry)) = entries.next_entry().await {
            let name = fs::read_to_string(entry.path().join("name"))
                .await
                .unwrap_or_default();
            if name.contains("amdgpu") || name.contains("nouveau") {
                for file in ["power1_average", "power1_input"] {
                    if let Ok(raw) = fs::read_to_string(entry.path().join(file)).await {
                        if let Ok(microwatts) = raw.trim().parse::<f32>() {
                            if microwatts > 0.0 {
                                return Some(microwatts / 1_000_000.0);
                            }
                        }
                    }
                }
            }
        }
    }
    let out = tokio::process::Command::new("nvidia-smi")
        .args(["--query-gpu=power.draw", "--format=csv,noheader,nounits"])
        .output()
        .await
        .ok()?;
    let text = String::from_utf8_lossy(&out.stdout);
    text.split('\n').next()?.trim().parse::<f32>().ok()
}

/// CPU package power in watts.
/// 1. Intel RAPL `energy_uj` when world-readable.
/// 2. AMD Zen RAPL MSR 0xc001029b via /dev/cpu/0/msr (needs the msr udev
///    rule from packaging/99-spartacus.rules). Energy counter is
///    monotonically increasing in ~15.3 µJ units on Zen; power = delta/dt.
/// Returns None when no source is accessible — callers render "--".
pub async fn cpu_power_watts(prev: &mut Option<(std::time::Instant, f64)>) -> Option<f32> {
    // -- Intel RAPL sysfs
    if let Ok(mut entries) = fs::read_dir("/sys/class/powercap").await {
        let mut total: Option<f64> = None;
        let mut dirs: Vec<PathBuf> = Vec::new();
        while let Ok(Some(entry)) = entries.next_entry().await {
            let name = entry.file_name().to_string_lossy().to_string();
            // top-level packages only (intel-rapl:0, amd-rapl:0), not subdomains
            if name.contains("rapl") && name.matches(':').count() == 1 {
                dirs.push(entry.path());
            }
        }
        dirs.sort();
        for dir in dirs {
            if let Ok(raw) = fs::read_to_string(dir.join("energy_uj")).await {
                if let Ok(uj) = raw.trim().parse::<f64>() {
                    *total.get_or_insert(0.0) += uj;
                }
            }
        }
        if let Some(energy_uj) = total {
            return delta_watts(prev, energy_uj * 1e-6);
        }
    }

    // -- AMD Zen RAPL MSR (std fs: tiny reads on a char device)
    let msr_open = std::fs::File::open("/dev/cpu/0/msr");
    if let Ok(mut file) = msr_open {
        use std::io::Read;
        let unit = msr_u64(&mut file, 0xc0010299).unwrap_or(0); // RAPL power unit
        // Zen encodes energy units in bits 12:8 of RAPL_POWER_UNIT
        // (1/2^unit * 1e6 J per bit observed 15.3 µJ on Zen2-5); fall back
        // to the documented constant when the register reads 0.
        let energy_unit = if unit != 0 {
            1.0 / (1u64 << ((unit >> 8) & 0x1f)) as f64 * 1e-6
        } else {
            15.3e-6
        };
        if let Some(raw) = msr_u64(&mut file, 0xc001029b) {
            return delta_watts(prev, raw as f64 * energy_unit);
        }
    }
    None
}

fn msr_u64(file: &mut std::fs::File, reg: u32) -> Option<u64> {
    use std::os::unix::fs::FileExt;
    let mut buf = [0u8; 8];
    file.read_exact_at(&mut buf, reg as u64).ok()?;
    Some(u64::from_le_bytes(buf))
}

fn delta_watts(prev: &mut Option<(std::time::Instant, f64)>, energy_j: f64) -> Option<f32> {
    let now = std::time::Instant::now();
    let watts = match *prev {
        Some((t0, e0)) if now.duration_since(t0).as_secs_f64() > 0.2 && energy_j >= e0 => {
            Some(((energy_j - e0) / now.duration_since(t0).as_secs_f64()) as f32)
        }
        _ => None,
    };
    *prev = Some((now, energy_j));
    watts.filter(|w| *w >= 0.0 && *w < 1000.0)
}
