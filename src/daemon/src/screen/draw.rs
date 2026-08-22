// Canvas drawing primitives for the LCD themes.
// RGB888 buffer with rect/rounded-rect/gradient/ring-gauge/text operations.

use fontdue::Font;

pub type Color = [u8; 3];

pub struct Canvas {
    pub w: usize,
    pub h: usize,
    pub px: Vec<u8>,
}

#[derive(Clone, Copy)]
pub enum Align {
    Left,
    Center,
    Right,
}

impl Canvas {
    pub fn new(w: usize, h: usize) -> Self {
        Self {
            w,
            h,
            px: vec![0u8; w * h * 3],
        }
    }

    pub fn gradient_v(&mut self, y0: usize, y1: usize, top: Color, bottom: Color) {
        let span = (y1.saturating_sub(y0)).max(1);
        for y in y0..y1.min(self.h) {
            let t = (y - y0) as f32 / span as f32;
            let c = lerp(top, bottom, t);
            self.rect(0, y as i32, self.w as u32, 1, c);
        }
    }

    pub fn gradient_h(&mut self, x0: usize, x1: usize, left: Color, right: Color) {
        let span = (x1.saturating_sub(x0)).max(1);
        for x in x0..x1.min(self.w) {
            let t = (x - x0) as f32 / span as f32;
            let c = lerp(left, right, t);
            self.rect(x as i32, 0, 1, self.h as u32, c);
        }
    }

    pub fn rect(&mut self, x: i32, y: i32, w: u32, h: u32, color: Color) {
        for py in y.max(0) as usize..((y + h as i32).min(self.h as i32)).max(0) as usize {
            for px in x.max(0) as usize..((x + w as i32).min(self.w as i32)).max(0) as usize {
                let idx = (py * self.w + px) * 3;
                self.px[idx] = color[0];
                self.px[idx + 1] = color[1];
                self.px[idx + 2] = color[2];
            }
        }
    }

    /// Filled rounded rectangle.
    pub fn round_rect(&mut self, x: i32, y: i32, w: u32, h: u32, r: u32, color: Color) {
        let r = r.min(w / 2).min(h / 2) as i32;
        // Center body
        self.rect(x, y + r, w, h - 2 * r as u32, color);
        // Side flanks
        self.rect(x + r, y, (w as i32 - 2 * r).max(0) as u32, h, color);
        // Corner circles
        self.fill_circle(x + r, y + r, r as f32, color);
        self.fill_circle(x + w as i32 - r - 1, y + r, r as f32, color);
        self.fill_circle(x + r, y + h as i32 - r - 1, r as f32, color);
        self.fill_circle(x + w as i32 - r - 1, y + h as i32 - r - 1, r as f32, color);
    }

    /// Rounded rectangle outline.
    pub fn round_rect_outline(
        &mut self,
        x: i32,
        y: i32,
        w: u32,
        h: u32,
        r: u32,
        thickness: f32,
        color: Color,
    ) {
        let r = r.min(w / 2).min(h / 2) as i32;
        let t = thickness;
        self.rect(x, y + r, w, t as u32, color);
        self.rect(x, y + h as i32 - r, w, t as u32, color);
        self.rect(x, y + r, t as u32, h - 2 * r as u32, color);
        self.rect(x + w as i32 - t as i32, y + r, t as u32, h - 2 * r as u32, color);
        self.arc(x + r, y + r, r as f32 - t / 2.0, t, 180.0, 90.0, color);
        self.arc(
            x + w as i32 - r,
            y + r,
            r as f32 - t / 2.0,
            t,
            270.0,
            90.0,
            color,
        );
        self.arc(
            x + r,
            y + h as i32 - r,
            r as f32 - t / 2.0,
            t,
            90.0,
            90.0,
            color,
        );
        self.arc(
            x + w as i32 - r,
            y + h as i32 - r,
            r as f32 - t / 2.0,
            t,
            0.0,
            90.0,
            color,
        );
    }

    pub fn fill_circle(&mut self, cx: i32, cy: i32, radius: f32, color: Color) {
        let r2 = radius * radius;
        for py in (cy - radius as i32).max(0)..=(cy + radius as i32).min(self.h as i32 - 1) {
            for pxc in (cx - radius as i32).max(0)..=(cx + radius as i32)
                .min(self.w as i32 - 1)
            {
                let dx = (pxc - cx) as f32;
                let dy = (py - cy) as f32;
                if dx * dx + dy * dy <= r2 {
                    let idx = (py as usize * self.w + pxc as usize) * 3;
                    self.px[idx] = color[0];
                    self.px[idx + 1] = color[1];
                    self.px[idx + 2] = color[2];
                }
            }
        }
    }

    /// Thick arc. Angles in degrees, 0 = right (+x), increasing clockwise
    /// (screen coords where +y is down).
    pub fn arc(
        &mut self,
        cx: i32,
        cy: i32,
        radius: f32,
        thickness: f32,
        start_deg: f32,
        sweep_deg: f32,
        color: Color,
    ) {
        if sweep_deg <= 0.0 {
            return;
        }
        let steps = ((sweep_deg.abs() / 360.0) * std::f32::consts::TAU * radius * 1.5)
            .ceil()
            .max(8.0) as i32;
        for i in 0..=steps {
            let a = (start_deg + sweep_deg * i as f32 / steps as f32).to_radians();
            let px = cx as f32 + a.cos() * radius;
            let py = cy as f32 + a.sin() * radius;
            self.fill_circle(px.round() as i32, py.round() as i32, thickness / 2.0, color);
        }
    }

    /// Ring gauge: track circle plus proportional value arc starting at top.
    pub fn ring_gauge(
        &mut self,
        cx: i32,
        cy: i32,
        radius: f32,
        thickness: f32,
        pct: f32,
        track: Color,
        fill: Color,
    ) {
        self.arc(cx, cy, radius, thickness, 0.0, 360.0, track);
        let sweep = pct.clamp(0.0, 100.0) / 100.0 * 360.0;
        self.arc(cx, cy, radius, thickness, -90.0, sweep, fill);
    }

    /// Horizontal progress bar with rounded ends.
    pub fn progress_bar(
        &mut self,
        x: i32,
        y: i32,
        w: u32,
        h: u32,
        pct: f32,
        track: Color,
        fill: Color,
    ) {
        self.round_rect(x, y, w, h, h / 2, track);
        let fw = ((w as f32) * pct.clamp(0.0, 100.0) / 100.0) as u32;
        if fw > 0 {
            let fr = (h / 2).min(fw / 2);
            self.round_rect(x, y, fw, h, fr, fill);
        }
    }

    /// Draw text with the given font. Returns advance width.
    pub fn text(
        &mut self,
        font: &Font,
        mut x: i32,
        y_baseline: i32,
        size: f32,
        color: Color,
        s: &str,
        align: Align,
    ) -> i32 {
        let total_w: i32 = s
            .chars()
            .filter_map(|ch| {
                let gi = font.lookup_glyph_index(ch);
                (gi != 0).then(|| font.metrics_indexed(gi, size).advance_width.ceil() as i32)
            })
            .sum();
        match align {
            Align::Left => {}
            Align::Center => x -= total_w / 2,
            Align::Right => x -= total_w,
        }

        for ch in s.chars() {
            let gi = font.lookup_glyph_index(ch);
            if gi == 0 && !ch.is_whitespace() {
                continue;
            }
            let hm = font.metrics_indexed(gi, size);
            let (metrics, bitmap) = font.rasterize_indexed(gi, size);
            // fontdue bitmap coords are Y-up from the baseline:
            // top edge on screen = baseline - (ymin + height).
            self.blit_bitmap(
                x + metrics.xmin,
                y_baseline - metrics.ymin - metrics.height as i32,
                metrics.width,
                metrics.height,
                color,
                &bitmap,
            );
            x += hm.advance_width.ceil() as i32;
        }
        total_w
    }

    fn blit_bitmap(
        &mut self,
        x: i32,
        y_top: i32,
        w: usize,
        _h: usize,
        color: Color,
        bitmap: &[u8],
    ) {
        for by in 0.._h {
            for bx in 0..w {
                let alpha = bitmap[by * w + bx];
                if alpha == 0 {
                    continue;
                }
                let px = x + bx as i32;
                let py = y_top + by as i32;
                if px < 0 || py < 0 || px >= self.w as i32 || py >= self.h as i32 {
                    continue;
                }
                let idx = (py as usize * self.w + px as usize) * 3;
                blend_pixel(&mut self.px[idx..idx + 3], color, alpha);
            }
        }
    }
}

fn blend_pixel(dst: &mut [u8], src: Color, alpha: u8) {
    if alpha == 255 {
        dst[0] = src[0];
        dst[1] = src[1];
        dst[2] = src[2];
        return;
    }
    let a = alpha as u32;
    let inv = 255 - a;
    dst[0] = ((src[0] as u32 * a + dst[0] as u32 * inv) / 255) as u8;
    dst[1] = ((src[1] as u32 * a + dst[1] as u32 * inv) / 255) as u8;
    dst[2] = ((src[2] as u32 * a + dst[2] as u32 * inv) / 255) as u8;
}

pub fn lerp(a: Color, b: Color, t: f32) -> Color {
    [
        (a[0] as f32 + (b[0] - a[0]) as f32 * t) as u8,
        (a[1] as f32 + (b[1] - a[1]) as f32 * t) as u8,
        (a[2] as f32 + (b[2] - a[2]) as f32 * t) as u8,
    ]
}
