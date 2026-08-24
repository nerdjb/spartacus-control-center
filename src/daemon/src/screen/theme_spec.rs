// Data-driven theme specs: JSON designs rendered with the same Canvas
// primitives as the built-in themes (cards-quality output).
//
// A spec is a JSON document:
//   {
//     "name": "my-theme",
//     "background": {"kind": "gradient", "top": "#0B0E1A", "bottom": "#101528"},
//     "widgets": [
//        {"kind": "panel", "x":14, "y":66, "w":222, "h":148, "r":14,
//         "fill":"#161B29", "stroke":"#232B40", "stroke_w":2},
//        {"kind": "text", "x":240, "y":42, "size":34, "color":"#FFFFFF",
//         "align":"center", "text":"{time}"},
//        {"kind": "ring", "cx":240, "cy":240, "radius":120, "thickness":14,
//         "track":"#1E2438", "fill":"#00E5FF", "binding":"cpu_temp",
//         "min":0, "max":100, "start":-90, "sweep":360,
//         "center_text":"{cpu_temp:.0}°", "center_size":40},
//        {"kind": "bar", "x":30, "y":200, "w":200, "h":10, "track":"#1E2438",
//         "fill":"#7CFFB2", "binding":"cpu_usage", "min":0, "max":100},
//        {"kind": "rect", "x":0, "y":0, "w":480, "h":56, "fill":"#000000"},
//        {"kind": "circle", "cx":240, "cy":240, "r":50, "fill":"#101528"}
//     ]
//   }
//
// Text content supports {binding} and {binding:.N} placeholders resolved from
// live metrics; everything outside braces is literal.

use super::draw::{Align, Canvas, Color};
use super::helpers;
use super::Metrics;
use fontdue::Font;
use serde::Deserialize;
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::Arc;

// ---------------------------------------------------------------- spec model

#[derive(Debug, Clone, Deserialize)]
pub struct ThemeSpec {
    #[serde(default)]
    pub name: String,
    /// Directory the spec JSON lives in; relative image paths resolve here.
    #[serde(skip)]
    #[serde(default)]
    pub base_dir: PathBuf,
    #[serde(default)]
    pub background: BackgroundSpec,
    #[serde(default)]
    pub widgets: Vec<WidgetSpec>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct BackgroundSpec {
    #[serde(default = "default_bg_kind")]
    pub kind: String, // "gradient" | "solid"
    #[serde(default = "default_bg_top")]
    pub top: String,
    #[serde(default = "default_bg_bottom")]
    pub bottom: String,
}

impl Default for BackgroundSpec {
    fn default() -> Self {
        Self {
            kind: default_bg_kind(),
            top: default_bg_top(),
            bottom: default_bg_bottom(),
        }
    }
}

fn default_bg_kind() -> String {
    "gradient".into()
}
fn default_bg_top() -> String {
    "#0B0E1A".into()
}
fn default_bg_bottom() -> String {
    "#101528".into()
}

#[derive(Debug, Clone, Deserialize)]
pub struct WidgetSpec {
    pub kind: String,
    #[serde(default)]
    pub x: f32,
    #[serde(default)]
    pub y: f32,
    #[serde(default)]
    pub w: f32,
    #[serde(default)]
    pub h: f32,
    #[serde(default)]
    pub cx: f32,
    #[serde(default)]
    pub cy: f32,
    /// corner radius (panel/bar) or circle radius
    #[serde(default)]
    pub r: f32,
    #[serde(default)]
    pub fill: Option<String>,
    #[serde(default)]
    pub stroke: Option<String>,
    #[serde(default)]
    pub stroke_w: f32,
    #[serde(default)]
    pub text: Option<String>,
    #[serde(default)]
    pub size: f32,
    #[serde(default = "default_align")]
    pub align: String,
    #[serde(default)]
    pub thickness: f32,
    #[serde(default)]
    pub track: Option<String>,
    #[serde(default)]
    pub binding: Option<String>,
    #[serde(default)]
    pub min: f32,
    #[serde(default = "default_max")]
    pub max: f32,
    /// ring arc start in degrees (PIL/screen convention: 0 = +x, clockwise, -90 = top)
    #[serde(default = "default_start")]
    pub start: f32,
    #[serde(default = "default_sweep")]
    pub sweep: f32,
    #[serde(default)]
    pub center_text: Option<String>,
    #[serde(default = "default_center_size")]
    pub center_size: f32,
    /// Image file (PNG/JPEG), relative to the theme JSON's directory.
    #[serde(default)]
    pub path: Option<String>,
}

// ---------------------------------------------------------------- image cache

pub struct ImageData {
    pub w: u32,
    pub h: u32,
    pub rgba: Vec<u8>,
}

/// Decodes spec images once and caches them: the theme stream re-renders
/// every refresh interval, so PNG/JPEG decoding must not run per frame.
#[derive(Default)]
pub struct ImageCache {
    map: HashMap<PathBuf, Option<Arc<ImageData>>>,
}

impl ImageCache {
    pub fn get(&mut self, path: &Path) -> Option<Arc<ImageData>> {
        if let Some(hit) = self.map.get(path) {
            return hit.clone();
        }
        let decoded = self.decode(path);
        self.map.insert(path.to_path_buf(), decoded.clone());
        decoded
    }

    fn decode(&self, path: &Path) -> Option<Arc<ImageData>> {
        let bytes = std::fs::read(path).ok()?;
        let img = image::load_from_memory(&bytes).ok()?;
        let rgba = img.to_rgba8();
        Some(Arc::new(ImageData {
            w: rgba.width(),
            h: rgba.height(),
            rgba: rgba.into_raw(),
        }))
    }
}

fn default_align() -> String {
    "left".into()
}
fn default_max() -> f32 {
    100.0
}
fn default_start() -> f32 {
    -90.0
}
fn default_sweep() -> f32 {
    360.0
}
fn default_center_size() -> f32 {
    24.0
}

// ---------------------------------------------------------------- colors

pub fn parse_color(s: &str) -> Color {
    let v = s.trim().trim_start_matches('#');
    if v.len() >= 6 {
        if let (Ok(r), Ok(g), Ok(b)) = (
            u8::from_str_radix(&v[0..2], 16),
            u8::from_str_radix(&v[2..4], 16),
            u8::from_str_radix(&v[4..6], 16),
        ) {
            return [r, g, b];
        }
    }
    [0xff, 0x00, 0xff] // loud magenta = spec error you can see
}

fn opt_color(s: &Option<String>) -> Option<Color> {
    s.as_ref().map(|c| parse_color(c))
}

// ---------------------------------------------------------------- bindings

enum Val {
    Text(String),
    Num(f32),
}

fn binding_value(m: &Metrics, key: &str) -> Option<Val> {
    let v = match key {
        "time" => Val::Text(m.time.clone()),
        "date" => Val::Text(m.date.clone()),
        "cpu_temp" => Val::Num(m.cpu_temp),
        "cpu_usage" => Val::Num(m.cpu_pct()),
        "cpu_freq" => Val::Num(m.cpu_freq_ghz),
        "gpu_temp" => Val::Num(m.gpu_temp),
        "gpu_usage" => Val::Num(m.gpu_pct()),
        "ram_used" => Val::Num(m.ram_used_gb),
        "ram_total" => Val::Num(m.ram_total_gb),
        "ram_free" => Val::Num((m.ram_total_gb - m.ram_used_gb).max(0.0)),
        "ram_pct" => Val::Num(m.ram_pct()),
        "disk_used" => Val::Num(m.disk_used_gb),
        "disk_total" => Val::Num(m.disk_total_gb),
        "disk_free" => Val::Num((m.disk_total_gb - m.disk_used_gb).max(0.0)),
        "disk_pct" => Val::Num(m.disk_pct()),
        "net_up" => Val::Num(m.net_up_kbps),
        "net_down" => Val::Num(m.net_down_kbps),
        "pump_rpm" => Val::Num(m.pump_rpm as f32),
        "fan_rpm" => Val::Num(m.fan_rpm as f32),
        "pump_pct" => Val::Num(m.pump_pct()),
        "cpu_watts" if m.cpu_watts > 0.5 => Val::Num(m.cpu_watts),
        "gpu_watts" if m.gpu_watts > 0.5 => Val::Num(m.gpu_watts),
        "cpu_watts" | "gpu_watts" => return None,
        "fps" => Val::Num(m.fps),
        "frametime" => Val::Num(m.frametime_ms),
        _ => return None,
    };
    Some(v)
}

fn fmt_num(v: f32, spec: Option<&str>) -> String {
    // spec like ".0" / ".1" / ".2"; default trims to a tidy representation
    if let Some(s) = spec {
        if let Ok(p) = s.trim_start_matches('.').parse::<usize>() {
            return format!("{:.*}", p.min(6), v);
        }
    }
    if (v - v.round()).abs() < 0.005 {
        format!("{:.0}", v)
    } else {
        let s = format!("{:.2}", v);
        s.trim_end_matches('0').trim_end_matches('.').to_string()
    }
}

/// Resolve `{key}` / `{key:.N}` placeholders; unknown keys render as "--".
pub fn format_template(template: &str, m: &Metrics) -> String {
    let mut out = String::with_capacity(template.len() + 16);
    let mut rest = template;
    while let Some(start) = rest.find('{') {
        out.push_str(&rest[..start]);
        let tail = &rest[start + 1..];
        match tail.find('}') {
            Some(end) => {
                let inner = &tail[..end];
                let (key, spec) = match inner.find(':') {
                    Some(i) => (&inner[..i], Some(&inner[i + 1..])),
                    None => (inner, None),
                };
                match binding_value(m, key) {
                    Some(Val::Text(s)) => out.push_str(&s),
                    Some(Val::Num(v)) => out.push_str(&fmt_num(v, spec)),
                    None => out.push_str("--"),
                }
                rest = &tail[end + 1..];
            }
            None => {
                out.push('{');
                rest = tail;
            }
        }
    }
    out.push_str(rest);
    out
}

fn binding_pct(m: &Metrics, w: &WidgetSpec) -> f32 {
    let raw = w
        .binding
        .as_deref()
        .and_then(|k| binding_value(m, k))
        .and_then(|v| match v {
            Val::Num(n) => Some(n),
            Val::Text(s) => s.parse::<f32>().ok(),
        });
    let v = raw.unwrap_or(w.min);
    let span = (w.max - w.min).max(0.001);
    ((v - w.min) / span * 100.0).clamp(0.0, 100.0)
}

// ---------------------------------------------------------------- rendering

fn align_of(s: &str) -> Align {
    match s {
        "center" => Align::Center,
        "right" => Align::Right,
        _ => Align::Left,
    }
}

/// Render a theme spec onto the canvas.
pub fn render(
    c: &mut Canvas,
    spec: &ThemeSpec,
    m: &Metrics,
    font: &Font,
    images: &mut ImageCache,
) {
    match spec.background.kind.as_str() {
        "solid" => c.rect(0, 0, 480, 480, parse_color(&spec.background.top)),
        _ => c.gradient_v(
            0,
            480,
            parse_color(&spec.background.top),
            parse_color(&spec.background.bottom),
        ),
    }
    for w in &spec.widgets {
        draw_widget(c, w, m, font, spec, images);
    }
}

fn draw_widget(
    c: &mut Canvas,
    w: &WidgetSpec,
    m: &Metrics,
    font: &Font,
    spec: &ThemeSpec,
    images: &mut ImageCache,
) {
    match w.kind.as_str() {
        "panel" => {
            c.round_rect(
                w.x as i32,
                w.y as i32,
                w.w.max(1.0) as u32,
                w.h.max(1.0) as u32,
                w.r as u32,
                opt_color(&w.fill).unwrap_or([0x16, 0x1b, 0x29]),
            );
            if w.stroke_w > 0.0 {
                if let Some(stroke) = opt_color(&w.stroke) {
                    c.round_rect_outline(
                        w.x as i32,
                        w.y as i32,
                        w.w.max(1.0) as u32,
                        w.h.max(1.0) as u32,
                        w.r as u32,
                        w.stroke_w,
                        stroke,
                    );
                }
            }
        }
        "rect" => {
            c.rect(
                w.x as i32,
                w.y as i32,
                w.w.max(1.0) as u32,
                w.h.max(1.0) as u32,
                opt_color(&w.fill).unwrap_or([0x10, 0x14, 0x20]),
            );
        }
        "circle" => {
            c.fill_circle(
                w.cx as i32,
                w.cy as i32,
                w.r.max(1.0),
                opt_color(&w.fill).unwrap_or([0x10, 0x14, 0x20]),
            );
        }
        "text" => {
            let content = format_template(w.text.as_deref().unwrap_or(""), m);
            c.text(
                font,
                w.x as i32,
                w.y as i32,
                w.size.max(6.0),
                opt_color(&w.fill).unwrap_or([0xff; 3]),
                &content,
                align_of(&w.align),
            );
        }
        "ring" => {
            let cx = w.cx as i32;
            let cy = w.cy as i32;
            let radius = w.r.max(4.0);
            let thickness = w.thickness.max(1.0);
            let track = opt_color(&w.track).unwrap_or([0x1e, 0x24, 0x38]);
            let fill = opt_color(&w.fill).unwrap_or([0x00, 0xe5, 0xff]);
            let pct = binding_pct(m, w);
            let start = w.start;
            let sweep = w.sweep;
            c.arc(cx, cy, radius, thickness, start, sweep, track);
            if pct > 0.0 {
                c.arc(cx, cy, radius, thickness, start, sweep * pct / 100.0, fill);
            }
            if let Some(t) = &w.center_text {
                let content = format_template(t, m);
                c.text(
                    font,
                    cx,
                    cy + (w.center_size as i32) * 2 / 7,
                    w.center_size.max(6.0),
                    fill,
                    &content,
                    Align::Center,
                );
            }
        }
        "bar" => {
            let x = w.x as i32;
            let y = w.y as i32;
            let bw = w.w.max(1.0) as u32;
            let bh = w.h.max(2.0) as u32;
            let rad = if w.r > 0.0 { w.r as u32 } else { bh / 2 };
            let track = opt_color(&w.track).unwrap_or([0x1e, 0x24, 0x38]);
            let fill = opt_color(&w.fill).unwrap_or([0x00, 0xe5, 0xff]);
            c.round_rect(x, y, bw, bh, rad.min(bh / 2), track);
            let pct = binding_pct(m, w);
            let fw = (bw as f32 * pct / 100.0) as u32;
            if fw > 0 {
                c.round_rect(x, y, fw, bh, rad.min(fw / 2).min(bh / 2), fill);
            }
        }
        "image" => {
            if let Some(rel) = &w.path {
                let path = if rel.starts_with('/') {
                    PathBuf::from(rel)
                } else {
                    spec.base_dir.join(rel)
                };
                if let Some(img) = images.get(&path) {
                    c.blit(
                        w.x as i32,
                        w.y as i32,
                        w.w.max(1.0) as u32,
                        w.h.max(1.0) as u32,
                        img.w,
                        img.h,
                        &img.rgba,
                    );
                }
            }
        }
        _ => {}
    }
}

// ---------------------------------------------------------------- built-ins

pub const AURORA_JSON: &str = include_str!("themes/aurora.json");

/// Parse a spec from JSON text.
pub fn parse_spec(json: &str) -> Result<ThemeSpec, String> {
    serde_json::from_str(json).map_err(|e| e.to_string())
}

/// Parse a spec from a file and remember its directory for relative assets.
pub fn parse_spec_file(path: &Path) -> Result<ThemeSpec, String> {
    let json = std::fs::read_to_string(path).map_err(|e| e.to_string())?;
    let mut spec = parse_spec(&json)?;
    spec.base_dir = path.parent().unwrap_or(Path::new(".")).to_path_buf();
    Ok(spec)
}

/// Look for a user/system theme file by name.
pub fn find_spec_file(name: &str) -> Option<PathBuf> {
    let mut dirs = Vec::new();
    if let Some(home) = std::env::var_os("HOME") {
        dirs.push(PathBuf::from(home).join(".config/spartacus/themes"));
    }
    dirs.push(PathBuf::from("/etc/spartacus/themes"));
    dirs.push(PathBuf::from("/usr/share/spartacus/themes"));
    for dir in dirs {
        let candidate = dir.join(format!("{name}.json"));
        if candidate.is_file() {
            return Some(candidate);
        }
    }
    None
}

