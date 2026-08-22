// Themes "colorful" (rainbow multi-panel) and "rings" (pastel ring gauges).

use super::draw::{lerp, Align, Canvas, Color};
use super::helpers::*;
use super::Metrics;
use fontdue::Font;

const DARK: Color = [0x2a, 0x2a, 0x32];

pub fn colorful(c: &mut Canvas, m: &Metrics, font: &Font) {
    rainbow_bg(c);
    // Header band
    c.rect(0, 0, 480, 46, [0x28, 0x28, 0x38]);
    c.text(font, 16, 32, 22.0, [0xff; 3], "SystemTime", Align::Left);
    c.text(font, 464, 34, 26.0, [0xff; 3], &m.time, Align::Right);

    let row1_y = 58i32;
    let row2_y = 250i32;
    let ph = 182u32;
    let xs = [14i32, 166i32, 318i32];
    let ws = [140u32, 140u32, 148u32];
    let col_r1 = xs[0] + ws[0] as i32 - 36;
    let col_r2 = xs[0] + ws[0] as i32 - 36;

    // Row 1: CPU / DISK / MEMORY
    panel_shell(c, xs[0], row1_y, ws[0], ph, [0x2f, 0x8a, 0xff]);
    ring_pct(c, font, xs[0] + 42, row1_y + 64, 33.0, 10.0, m.cpu_pct(), [0xd9, 0xe6, 0xff], [0x2f, 0x8a, 0xff], 17.0);
    c.text(font, xs[0] + 42, row1_y + 118, 12.0, [0x8a, 0x8a, 0x92], "LOAD", Align::Center);
    stat_col(c, font, col_r1, row1_y, "FREQ", &format!("{:.2}G", m.cpu_freq_ghz), "GHz");
    stat_col_temp(c, font, col_r1, row1_y, "TEMP", &format!("{:.0}C", m.cpu_temp), [0xf2, 0x6a, 0x00]);

    panel_shell(c, xs[1], row1_y, ws[1], ph, [0x2f, 0xc8, 0x66]);
    ring_pct(c, font, xs[1] + 70, row1_y + 70, 44.0, 12.0, m.disk_pct(), [0xdc, 0xf2, 0xe2], [0x2f, 0xc8, 0x66], 23.0);
    c.text(font, xs[1] + 70, row1_y + 132, 12.0, [0x8a, 0x8a, 0x92], "DISK", Align::Center);
    c.text(font, xs[1] + 70, row1_y + 156, 15.0, DARK, &fmt_gb_short(m.disk_used_gb), Align::Center);

    panel_shell(c, xs[2], row1_y, ws[2], ph, [0xa4, 0x4a, 0xd8]);
    ring_pct(c, font, xs[2] + 74, row1_y + 70, 44.0, 12.0, m.ram_pct(), [0xea, 0xdd, 0xfa], [0xa4, 0x4a, 0xd8], 23.0);
    c.text(font, xs[2] + 74, row1_y + 132, 12.0, [0x8a, 0x8a, 0x92], "MEMORY FREE", Align::Center);
    c.text(font, xs[2] + 74, row1_y + 156, 15.0, DARK, &fmt_gb_short(m.ram_total_gb - m.ram_used_gb), Align::Center);

    // Row 2: GPU / NETWORK / FANS
    panel_shell(c, xs[0], row2_y, ws[0], ph, [0xf3, 0x44, 0x5c]);
    ring_pct(c, font, xs[0] + 42, row2_y + 64, 33.0, 10.0, m.gpu_pct().max(2.0), [0xfa, 0xdb, 0xdf], [0xf3, 0x44, 0x5c], 17.0);
    c.text(font, xs[0] + 42, row2_y + 118, 12.0, [0x8a, 0x8a, 0x92], "LOAD", Align::Center);
    stat_col_temp(c, font, col_r2, row2_y, "TEMP", &format!("{:.0}C", m.gpu_temp), [0xf2, 0x6a, 0x00]);
    c.text(font, col_r2, row2_y + 100, 11.0, [0x8a, 0x8a, 0x92], "LOAD", Align::Center);
    c.text(font, col_r2, row2_y + 128, 19.0, DARK, &format!("{:.0}%", m.gpu_pct()), Align::Center);

    panel_shell(c, xs[1], row2_y, ws[1], ph, [0x00, 0xb4, 0xff]);
    c.text(font, xs[1] + 70, row2_y + 48, 15.0, [0x8a, 0x8a, 0x92], "UPLOAD", Align::Center);
    c.text(font, xs[1] + 70, row2_y + 80, 19.0, [0x00, 0x88, 0xcc], &fmt_kbps(m.net_up_kbps), Align::Center);
    c.text(font, xs[1] + 70, row2_y + 122, 15.0, [0x8a, 0x8a, 0x92], "DOWNLOAD", Align::Center);
    c.text(font, xs[1] + 70, row2_y + 154, 19.0, [0x00, 0x88, 0xcc], &fmt_kbps(m.net_down_kbps), Align::Center);

    panel_shell(c, xs[2], row2_y, ws[2], ph, [0xf2, 0x8c, 0x28]);
    c.text(font, xs[2] + 74, row2_y + 56, 15.0, [0x8a, 0x8a, 0x92], "PUMP FAN", Align::Center);
    c.text(font, xs[2] + 74, row2_y + 90, 23.0, DARK, &format!("{} RPM", m.pump_rpm), Align::Center);
    c.text(font, xs[2] + 74, row2_y + 128, 15.0, [0x8a, 0x8a, 0x92], "SYS FAN", Align::Center);
    c.text(font, xs[2] + 74, row2_y + 162, 23.0, DARK, &format!("{} RPM", m.fan_rpm), Align::Center);

    // Footer band
    c.rect(0, 442, 480, 38, [0x30, 0x30, 0x42]);
    c.text(font, 14, 467, 15.0, [0xd8, 0xd8, 0xe2], &m.date, Align::Left);
    c.text(font, 320, 467, 14.0, [0xd8, 0xd8, 0xe2], "Monitored Control System", Align::Center);
}

/// Right-hand stat column: caption, value, optional unit line.
fn stat_col(c: &mut Canvas, font: &Font, cx: i32, y_top: i32, cap: &str, val: &str, unit: &str) {
    c.text(font, cx, y_top + 40, 12.0, [0x8a, 0x8a, 0x92], cap, Align::Center);
    c.text(font, cx, y_top + 68, 19.0, DARK, val, Align::Center);
    if !unit.is_empty() {
        c.text(font, cx, y_top + 92, 13.0, [0x8a, 0x8a, 0x92], unit, Align::Center);
    }
}

fn stat_col_temp(c: &mut Canvas, font: &Font, cx: i32, y_top: i32, cap: &str, val: &str, color: Color) {
    c.text(font, cx, y_top + 124, 12.0, [0x8a, 0x8a, 0x92], cap, Align::Center);
    c.text(font, cx, y_top + 158, 24.0, color, val, Align::Center);
}

pub fn rings(c: &mut Canvas, m: &Metrics, font: &Font) {
    pastel_bg(c);

    // Big clock
    c.text(font, 240, 58, 52.0, [0x3a, 0x3a, 0x55], &m.time, Align::Center);
    c.text(font, 240, 96, 21.0, [0x8a, 0x80, 0xa8], &m.date, Align::Center);

    // SSD top-left (cyan)
    ring_pct(c, font, 86, 172, 50.0, 13.0, m.disk_pct(), [0xd8, 0xec, 0xf6], [0x2f, 0xb4, 0xd8], 26.0);
    c.text(font, 86, 240, 14.0, [0x77, 0x77, 0x82], "SSD", Align::Center);
    // PUMP top-right (pink)
    ring_pct(c, font, 394, 172, 50.0, 13.0, m.pump_pct(), [0xfa, 0xde, 0xe9], [0xe8, 0x4a, 0x8a], 26.0);
    c.text(font, 394, 240, 14.0, [0x77, 0x77, 0x82], "PUMP", Align::Center);
    // GPU mid-left (orange): temp + load inside
    dual_ring(c, font, 168, 296, m.gpu_temp, m.gpu_pct(), [0xfd, 0xe4, 0xd4], [0xf2, 0x7a, 0x1e], "GPU");
    // CPU mid-right (green)
    dual_ring(c, font, 312, 296, m.cpu_temp, m.cpu_pct(), [0xdc, 0xf2, 0xdf], [0x2f, 0xc8, 0x66], "CPU");
    // RAM bottom-center (orange)
    ring_pct(c, font, 240, 396, 52.0, 14.0, m.ram_pct(), [0xfa, 0xe6, 0xd2], [0xf2, 0x8c, 0x28], 20.0);
    c.text(font, 240, 452, 13.0, [0x77, 0x77, 0x82], "RAM", Align::Center);

    // Bottom corners: network arrows
    net_box(c, font, 20, 440, 170, true, m.net_up_kbps);
    net_box(c, font, 290, 440, 170, false, m.net_down_kbps);
}

/// Ring showing temperature (big) + load below.
fn dual_ring(
    c: &mut Canvas,
    font: &Font,
    cx: i32,
    cy: i32,
    temp: f32,
    pct: f32,
    track: Color,
    fill: Color,
    label: &str,
) {
    c.ring_gauge(cx, cy, 48.0, 12.0, pct.clamp(1.0, 100.0), track, fill);
    c.text(font, cx - 8, cy + 6, 23.0, fill, &format!("{:.0}", temp), Align::Center);
    c.text(font, cx + 24, cy + 6, 13.0, [0xf2, 0x6a, 0x00], "C", Align::Left);
    c.text(font, cx, cy + 30, 13.0, [0x77, 0x77, 0x82], &format!("{:.0}%", pct), Align::Center);
    c.text(font, cx, cy + 78, 14.0, [0x77, 0x77, 0x82], label, Align::Center);
}

/// Small rounded box with arrow + rate text.
fn net_box(c: &mut Canvas, font: &Font, x: i32, y: i32, w: i32, up: bool, kbps: f32) {
    c.round_rect(x, y, w as u32, 30, 15, [0xf2, 0xf0, 0xf6]);
    let arrow = if up { "^" } else { "v" };
    let color: Color = if up { [0x00, 0xa8, 0xe8] } else { [0x2f, 0xc8, 0x66] };
    c.text(font, x + 22, y + 21, 16.0, color, arrow, Align::Center);
    c.text(font, x + 40, y + 21, 15.0, DARK, &fmt_kbps(kbps), Align::Left);
}

fn rainbow_bg(c: &mut Canvas) {
    let stops: [Color; 5] = [
        [0xe8, 0x3a, 0xc8],
        [0x8a, 0x4a, 0xf2],
        [0x2f, 0xb4, 0xe8],
        [0x2f, 0xd8, 0x98],
        [0xf2, 0xd4, 0x3c],
    ];
    let seg = 96;
    for (i, pair) in stops.windows(2).enumerate() {
        let y0 = i * seg;
        for dy in 0..seg {
            let t = dy as f32 / seg as f32;
            let col = lerp(pair[0], pair[1], t);
            c.rect(0, (y0 + dy) as i32, 480, 1, col);
        }
    }
}

fn pastel_bg(c: &mut Canvas) {
    let stops: [Color; 4] = [
        [0xfc, 0xd9, 0xe8],
        [0xe4, 0xd4, 0xf6],
        [0xd2, 0xdc, 0xf8],
        [0xcf, 0xee, 0xf6],
    ];
    let seg = 160;
    for (i, pair) in stops.windows(2).enumerate() {
        let y0 = i * seg;
        for dy in 0..seg {
            let t = dy as f32 / seg as f32;
            let col = lerp(pair[0], pair[1], t);
            c.rect(0, (y0 + dy) as i32, 480, 1, col);
        }
    }
}

/// Panel with colored glow outline.
fn panel_shell(c: &mut Canvas, x: i32, y: i32, w: u32, h: u32, accent: Color) {
    c.round_rect(x - 2, y - 2, w + 4, h + 4, 18, accent);
    c.round_rect(x, y, w, h, 16, [0xf7, 0xf5, 0xfb]);
}
