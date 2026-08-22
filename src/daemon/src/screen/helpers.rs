// Theme helpers shared by all layouts.

use super::draw::{Align, Canvas, Color};
use super::Metrics;
use fontdue::Font;

pub fn fmt_pct(v: f32) -> String {
    format!("{:.0}", v)
}

pub fn fmt_gb(v: f32) -> String {
    if v >= 100.0 {
        format!("{:.0} GB", v)
    } else {
        format!("{:.1} GB", v)
    }
}

pub fn fmt_gb_short(v: f32) -> String {
    if v >= 100.0 {
        format!("{:.0}G", v)
    } else {
        format!("{:.1}G", v)
    }
}

pub fn fmt_kbps(v: f32) -> String {
    if v >= 1024.0 {
        format!("{:.2} MB/s", v / 1024.0)
    } else {
        format!("{:.2} kB/s", v)
    }
}

#[allow(clippy::too_many_arguments)]
pub fn stat_card(
    c: &mut Canvas,
    font: &Font,
    x: i32,
    y: i32,
    w: u32,
    h: u32,
    label: &str,
    value: &str,
    pct: f32,
    accent: Color,
    sub_left: (&str, &str),
    sub_right: (&str, &str),
) {
    c.round_rect(x, y, w, h, 14, [0xff; 3]);
    // Label
    c.text(
        font,
        x + w as i32 / 2,
        y + 26,
        17.0,
        [0x8a, 0x8a, 0x92],
        label,
        Align::Center,
    );
    // Big value
    c.text(
        font,
        x + w as i32 / 2,
        y + 72,
        36.0,
        [0x20, 0x20, 0x26],
        value,
        Align::Center,
    );
    // Progress bar
    let pad = 12i32;
    c.progress_bar(x + pad, y + 88, w - 2 * pad as u32, 9, pct, [0xf0, 0xe2, 0xe6], accent);
    // Sub stats: two centered columns
    let col_l = x + (w as i32) / 4;
    let col_r = x + (w as i32) * 3 / 4;
    c.text(font, col_l, y + h as i32 - 34, 11.0, [0x9a, 0x9a, 0xa2], sub_left.0, Align::Center);
    c.text(font, col_l, y + h as i32 - 15, 14.0, [0x35, 0x35, 0x40], sub_left.1, Align::Center);
    c.text(font, col_r, y + h as i32 - 34, 11.0, [0x9a, 0x9a, 0xa2], sub_right.0, Align::Center);
    c.text(font, col_r, y + h as i32 - 15, 14.0, [0x35, 0x35, 0x40], sub_right.1, Align::Center);
}

/// Ring gauge with a percentage drawn in its center.
#[allow(clippy::too_many_arguments)]
pub fn ring_pct(
    c: &mut Canvas,
    font: &Font,
    cx: i32,
    cy: i32,
    radius: f32,
    thickness: f32,
    pct: f32,
    track: Color,
    fill: Color,
    pct_size: f32,
) {
    c.ring_gauge(cx, cy, radius, thickness, pct, track, fill);
    c.text(
        font,
        cx,
        cy + pct_size as i32 * 2 / 7,
        pct_size,
        fill,
        &format!("{:.0}%", pct),
        Align::Center,
    );
}

/// Ring gauge card with centered % text and small caption.
#[allow(clippy::too_many_arguments)]
pub fn ring_card(
    c: &mut Canvas,
    font: &Font,
    cx: i32,
    cy: i32,
    radius: f32,
    thickness: f32,
    pct: f32,
    track: Color,
    fill: Color,
    center_big: &str,
    center_small: &str,
    big_size: f32,
) {
    c.ring_gauge(cx, cy, radius, thickness, pct, track, fill);
    c.text(font, cx, cy + 8, big_size, fill, center_big, Align::Center);
    c.text(
        font,
        cx,
        cy + radius as i32 + 18,
        15.0,
        [0x77, 0x77, 0x82],
        center_small,
        Align::Center,
    );
}

pub fn cpu_metrics(m: &Metrics) -> (&'static str, String, String, String) {
    (
        "CPU",
        format!("{:.0}%", m.cpu_pct()),
        format!("{:.2}G", m.cpu_freq_ghz),
        format!("{:.0}C", m.cpu_temp),
    )
}
