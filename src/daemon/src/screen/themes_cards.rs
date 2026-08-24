// Themes "cards" (dark purple) and "cards-light" (lavender):
// white stat cards with big percentages, progress bars, network + fan panel,
// pump ring gauge — recreated from the reference screenshots.

use super::draw::{Align, Canvas, Color};
use super::helpers::*;
use super::Metrics;
use fontdue::Font;

const RED: Color = [0xf3, 0x44, 0x5c];
const PINK: Color = [0xf2, 0x6a, 0xa0];
const MAGENTA: Color = [0xd4, 0x3c, 0xb8];
const PURPLE_TXT: Color = [0x6a, 0x3d, 0xc8];

pub fn cards(c: &mut Canvas, m: &Metrics, font: &Font) {
    // Background: deep purple gradient
    c.gradient_v(0, 480, [0x33, 0x1b, 0x55], [0x18, 0x0c, 0x2e]);
    // Header
    c.rect(0, 0, 480, 56, [0x00, 0x00, 0x00]);
    c.rect(0, 0, 480, 56, blend([0x4a, 0x2a, 0x78], 200));
    c.text(font, 16, 36, 19.0, [0xc8, 0xbc, 0xe0], &m.date, Align::Left);
    c.text(font, 240, 42, 34.0, [0xff; 3], &m.time, Align::Center);
    c.text(
        font,
        464,
        36,
        19.0,
        [0xc8, 0xbc, 0xe0],
        &format!("GPU {:.0}C", m.gpu_temp),
        Align::Right,
    );

    let margin = 14i32;
    let gap = 10i32;
    let card_w = ((480 - 2 * margin - 3 * gap) / 4) as u32;
    let card_h = 190u32;

    // Row 1: CPU / GPU / RAM / SSD cards
    let y = 66;
    for i in 0..4 {
        let x = margin + i * (card_w as i32 + gap);
        match i {
            0 => {
                let (_, val, freq, temp) = cpu_metrics(m);
                stat_card(
                    c,
                    font,
                    x,
                    y,
                    card_w,
                    card_h,
                    "CPU",
                    &val,
                    m.cpu_pct(),
                    RED,
                    ("Freq", &freq),
                    ("Temp", &temp),
                );
            }
            1 => {
                let val = format!("{:.0}%", m.gpu_pct());
                stat_card(
                    c,
                    font,
                    x,
                    y,
                    card_w,
                    card_h,
                    "GPU",
                    &val,
                    m.gpu_pct(),
                    PINK,
                    ("Load", &format!("{:.0}", m.gpu_pct())),
                    ("Temp", &format!("{:.0}C", m.gpu_temp)),
                );
            }
            2 => {
                stat_card(
                    c,
                    font,
                    x,
                    y,
                    card_w,
                    card_h,
                    "RAM",
                    &format!("{:.0}%", m.ram_pct()),
                    m.ram_pct(),
                    MAGENTA,
                    ("Used", &fmt_gb_short(m.ram_used_gb)),
                    ("Free", &fmt_gb_short(m.ram_total_gb - m.ram_used_gb)),
                );
            }
            _ => {
                stat_card(
                    c,
                    font,
                    x,
                    y,
                    card_w,
                    card_h,
                    "SSD",
                    &format!("{:.0}%", m.disk_pct()),
                    m.disk_pct(),
                    [0x8a, 0x4a, 0xd8],
                    ("Used", &fmt_gb_short(m.disk_used_gb)),
                    ("Free", &fmt_gb_short(m.disk_total_gb - m.disk_used_gb)),
                );
            }
        }
    }

    // Row 2: Network card, Fans card, Pump ring
    let y2 = 268;
    let h2 = 150u32;

    // Network card
    let net_x = margin;
    let net_w = (190) as u32;
    c.round_rect(net_x, y2, net_w, h2, 14, [0xff; 3]);
    c.text(font, net_x + 16, y2 + 34, 17.0, [0x9a, 0x9a, 0xa2], "Upload", Align::Left);
    c.text(
        font,
        net_x + 16,
        y2 + 62,
        21.0,
        [0x20, 0x20, 0x26],
        &fmt_kbps(m.net_up_kbps),
        Align::Left,
    );
    c.text(font, net_x + 16, y2 + 100, 17.0, [0x9a, 0x9a, 0xa2], "Download", Align::Left);
    c.text(
        font,
        net_x + 16,
        y2 + 128,
        21.0,
        [0x20, 0x20, 0x26],
        &fmt_kbps(m.net_down_kbps),
        Align::Left,
    );

    // Fans card
    let fan_x = margin + net_w as i32 + gap;
    let fan_w = 152u32;
    c.round_rect(fan_x, y2, fan_w, h2, 14, [0xff; 3]);
    c.text(font, fan_x + 16, y2 + 34, 15.0, [0x9a, 0x9a, 0xa2], "PUMP FAN", Align::Left);
    c.text(
        font,
        fan_x + 16,
        y2 + 62,
        22.0,
        [0x20, 0x20, 0x26],
        &format!("{} RPM", m.pump_rpm),
        Align::Left,
    );
    c.text(font, fan_x + 16, y2 + 100, 15.0, [0x9a, 0x9a, 0xa2], "SYS FAN", Align::Left);
    c.text(
        font,
        fan_x + 16,
        y2 + 128,
        22.0,
        [0x20, 0x20, 0x26],
        &format!("{} RPM", m.fan_rpm),
        Align::Left,
    );

    // Pump ring card
    let ring_x = fan_x + fan_w as i32 + gap;
    let ring_w = 480 - margin - ring_x;
    c.round_rect(ring_x, y2, ring_w as u32, h2, 14, [0xff; 3]);
    let cx = ring_x + ring_w / 2;
    let cy = y2 + h2 as i32 / 2;
    ring_pct(c, font, cx, cy - 12, 42.0, 11.0, m.pump_pct(), [0xf6, 0xdf, 0xea], PINK, 22.0);
    c.text(font, cx, cy + 44, 14.0, [0x77, 0x77, 0x82], "PUMP", Align::Center);

    // Footer: live gaming stats when a MangoHud session is active
    let footer = if m.fps > 1.0 {
        format!("FPS {:.0}  \u{b7}  {:.1} MS", m.fps, m.frametime_ms)
    } else {
        "SPARTACUS CONTROL".to_string()
    };
    c.text(
        font,
        240,
        456,
        15.0,
        if m.fps > 1.0 { [0xf2, 0x6a, 0xa0] } else { [0x7a, 0x68, 0x9a] },
        &footer,
        Align::Center,
    );
}

pub fn cards_light(c: &mut Canvas, m: &Metrics, font: &Font) {
    // Background: light lavender gradient
    c.gradient_v(0, 480, [0xd8, 0xcc, 0xf4], [0xb2, 0x9e, 0xe4]);

    // Header: date left purple, time right big purple
    c.text(font, 20, 40, 22.0, PURPLE_TXT, &m.date, Align::Left);
    c.text(font, 460, 46, 38.0, PURPLE_TXT, &m.time, Align::Right);

    let card_h = 148u32;
    let w_half = 222u32;
    let positions = [
        (14i32, 66i32),
        (480 - 14 - w_half as i32, 66),
        (14, 66 + card_h as i32 + 10),
        (480 - 14 - w_half as i32, 66 + card_h as i32 + 10),
    ];

    let (cpu_label, cpu_val, cpu_freq, cpu_temp) = cpu_metrics(m);
    let data = [
        (
            cpu_label,
            cpu_val,
            m.cpu_pct(),
            RED,
            ("Speed".to_string(), cpu_freq),
            ("Temp".to_string(), cpu_temp),
        ),
        (
            "GPU",
            format!("{:.0}%", m.gpu_pct()),
            m.gpu_pct(),
            PINK,
            ("Load".to_string(), format!("{:.0}", m.gpu_pct())),
            ("Temp".to_string(), format!("{:.0} C", m.gpu_temp)),
        ),
        (
            "RAM",
            format!("{:.0}%", m.ram_pct()),
            m.ram_pct(),
            MAGENTA,
            ("Total".to_string(), fmt_gb_short(m.ram_total_gb)),
            ("Used".to_string(), fmt_gb_short(m.ram_used_gb)),
        ),
        (
            "SSD",
            format!("{:.0}%", m.disk_pct()),
            m.disk_pct(),
            [0x8a, 0x4a, 0xd8],
            ("Total".to_string(), fmt_gb_short(m.disk_total_gb)),
            ("Free".to_string(), fmt_gb_short(m.disk_total_gb - m.disk_used_gb)),
        ),
    ];
    for (i, (label, value, pct, accent, sl, sr)) in data.iter().enumerate() {
        let (x, y) = positions[i];
        stat_card(
            c,
            font,
            x,
            y,
            w_half,
            card_h,
            label,
            value,
            *pct,
            *accent,
            (&sl.0, &sl.1),
            (&sr.0, &sr.1),
        );
    }

    // Bottom row: network card, fans card, pump ring
    let y3 = 66 + 2 * (card_h as i32) + 20;
    let h3 = 480 - y3 - 14;

    let net_x = 14i32;
    let net_w = 186u32;
    c.round_rect(net_x, y3, net_w, h3 as u32, 14, [0xff; 3]);
    c.text(font, net_x + 16, y3 + 26, 13.0, [0x9a, 0x9a, 0xa2], "Upload", Align::Left);
    c.text(font, net_x + 90, y3 + 27, 15.0, [0x20, 0x20, 0x26], &fmt_kbps(m.net_up_kbps), Align::Left);
    c.text(font, net_x + 16, y3 + 58, 13.0, [0x9a, 0x9a, 0xa2], "Download", Align::Left);
    c.text(font, net_x + 90, y3 + 59, 15.0, [0x20, 0x20, 0x26], &fmt_kbps(m.net_down_kbps), Align::Left);

    let fan_x = 210i32;
    let fan_w = 122u32;
    c.round_rect(fan_x, y3, fan_w, h3 as u32, 14, [0xff; 3]);
    c.text(font, fan_x + 12, y3 + 26, 12.0, [0x9a, 0x9a, 0xa2], "PUMP FAN", Align::Left);
    c.text(font, fan_x + 12, y3 + 45, 15.0, [0x20, 0x20, 0x26], &format!("{} RPM", m.pump_rpm), Align::Left);
    c.text(font, fan_x + 12, y3 + 60, 12.0, [0x9a, 0x9a, 0xa2], "SYS FAN", Align::Left);
    c.text(font, fan_x + 12, y3 + 79, 15.0, [0x20, 0x20, 0x26], &format!("{} RPM", m.fan_rpm), Align::Left);

    let rx = 342i32;
    let rw = 480 - rx - 14;
    c.round_rect(rx, y3, rw as u32, h3 as u32, 14, [0xff; 3]);
    let cx = rx + rw / 2;
    let cy = y3 + h3 / 2 - 6;
    ring_pct(c, font, cx, cy, 27.0, 8.0, m.pump_pct(), [0xf6, 0xdf, 0xea], PINK, 14.0);
    c.text(font, cx, y3 + h3 - 8, 12.0, [0x77, 0x77, 0x82], "PUMP", Align::Center);
}

/// Blend color with alpha over transparent (helper for translucent overlays).
fn blend(c: Color, alpha: u8) -> Color {
    // Approximate overlay on dark background by scaling brightness.
    let a = alpha as u32;
    [
        (c[0] as u32 * a / 255).min(255) as u8,
        (c[1] as u32 * a / 255).min(255) as u8,
        (c[2] as u32 * a / 255).min(255) as u8,
    ]
}
