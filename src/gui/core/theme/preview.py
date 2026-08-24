"""Python preview renderer for theme specs — mirrors the daemon's Rust
`screen/draw.rs` techniques (stamped-circle arcs, rounded panels, baseline
text) at 2x supersampling so the Studio preview matches panel output.
"""

from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from core.theme.spec import ThemeSpec, Widget

CANVAS = 480
_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
)

DEMO_METRICS = {
    "time": datetime.now().strftime("%H:%M:%S"),
    "date": datetime.now().strftime("%Y-%m-%d"),
    "cpu_temp": 63.0, "cpu_usage": 37.0, "cpu_freq": 3.77,
    "gpu_temp": 45.0, "gpu_usage": 22.0,
    "ram_used": 14.1, "ram_total": 16.0, "ram_free": 1.9, "ram_pct": 88.0,
    "disk_used": 192.0, "disk_total": 240.0, "disk_free": 48.0, "disk_pct": 80.0,
    "net_up": 220.4, "net_down": 1400.0,
    "pump_rpm": 2380, "fan_rpm": 1240, "pump_pct": 68.0,
    "cpu_watts": 88.0, "gpu_watts": 220.0,
}

_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def _font(size_px: int) -> ImageFont.FreeTypeFont:
    size_px = max(6, int(size_px))
    key = ("default", size_px)
    if key not in _font_cache:
        path = next((p for p in _FONT_CANDIDATES if Path(p).exists()), None)
        _font_cache[key] = ImageFont.truetype(path, size_px) if path \
            else ImageFont.load_default()
    return _font_cache[key]


def _color(value: str, fallback=(255, 0, 255, 255)):
    try:
        v = value.strip().lstrip("#")
        if len(v) == 6:
            r, g, b = int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)
            return (r, g, b, 255)
        if len(v) == 8:
            return (int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16), int(v[6:8], 16))
    except (ValueError, AttributeError):
        pass
    return fallback


def format_template(template: str, m: dict) -> str:
    out, rest = [], template
    while "{" in rest:
        head, _, rest2 = rest.partition("{")
        out.append(head)
        inner, sep, rest = rest2.partition("}")
        if not sep:
            out.append("{")
            rest = rest2
            break
        key, _, spec = inner.partition(":")
        value = m.get(key, None)
        if value is None:
            out.append("--")
        elif isinstance(value, str):
            out.append(value)
        else:
            if spec.startswith("."):
                try:
                    out.append(f"{value:.{int(spec[1:])}f}")
                    continue
                except (ValueError, OverflowError):
                    pass
            s = f"{value:.2f}".rstrip("0").rstrip(".")
            out.append(s if s else "0")
    out.append(rest)
    return "".join(out)


class SpecRenderer:
    """Render a ThemeSpec to a smooth 480x480 RGB image."""

    def __init__(self, spec: ThemeSpec, metrics: dict | None = None):
        self.spec = spec
        self.m = dict(DEMO_METRICS)
        if metrics:
            self.m.update({k: v for k, v in metrics.items() if v is not None})

    # -- public ------------------------------------------------------------

    def render(self, supersample: int = 2) -> Image.Image:
        S = max(1, supersample)
        size = CANVAS * S
        image = Image.new("RGBA", (size, size))
        draw = ImageDraw.Draw(image)
        bg = self.spec.background
        if bg.get("kind") == "image" and bg.get("path"):
            path = Path(bg["path"])
            if not path.is_absolute() and self.spec.source_dir:
                path = Path(self.spec.source_dir) / path
            if path.is_file():
                try:
                    gif = Image.open(path)
                    import time as _time
                    idx = int(_time.time() * 1000) % 100
                    total = 0
                    delays = []
                    for i in range(getattr(gif, "n_frames", 1)):
                        gif.seek(i)
                        delays.append(max(20, gif.info.get("duration", 70)))
                        total += delays[-1]
                    at = (int(_time.time() * 1000) % total) if total else 0
                    acc = 0
                    frame_i = 0
                    for i, dl in enumerate(delays):
                        if at < acc + dl:
                            frame_i = i
                            break
                        acc += dl
                    gif.seek(frame_i)
                    frame = gif.convert("RGBA").resize((size, size))
                    image.alpha_composite(frame)
                except Exception:
                    pass
            else:
                draw.rectangle((0, 0, size, size), fill=(10, 12, 20, 255))
        elif bg.get("kind") == "solid":
            draw.rectangle((0, 0, size, size), fill=_color(bg.get("top", "#0B0E1A")))
        else:
            top, bottom = _color(bg.get("top", "#0B0E1A")), _color(bg.get("bottom", "#101528"))
            for y in range(size):
                t = y / (size - 1)
                row = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
                draw.line((0, y, size, y), fill=row + (255,))
        for w in self.spec.widgets:
            self._draw_widget(draw, image, w, S)
        return image.resize((CANVAS, CANVAS), Image.LANCZOS).convert("RGB")

    # -- widgets -----------------------------------------------------------

    def _draw_widget(self, draw: ImageDraw.ImageDraw, image: Image.Image,
                     w: Widget, S: int) -> None:
        kind = w.kind
        if kind == "panel":
            box = self._box(w.x, w.y, w.w, w.h, S)
            r = int(w.r * S)
            if str(w.fill).lower() in ("", "none", "transparent"):
                fill = None
            else:
                fill = _color(w.fill, (35, 40, 51, 255))
            if fill is not None:
                draw.rounded_rectangle(box, radius=min(r, (box[2] - box[0]) // 2,
                                                       (box[3] - box[1]) // 2), fill=fill)
            if w.stroke_w > 0 and w.stroke:
                draw.rounded_rectangle(box, radius=r,
                                       outline=_color(w.stroke), width=max(1, int(w.stroke_w * S)))
        elif kind == "rect":
            draw.rectangle(self._box(w.x, w.y, w.w, w.h, S), fill=_color(w.fill))
        elif kind == "circle":
            r = w.r * S
            cx, cy = w.cx * S, w.cy * S
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=_color(w.fill))
        elif kind == "text":
            content = format_template(w.text, self.m)
            self._draw_text(draw, content, w, S)
        elif kind == "ring":
            self._draw_ring(draw, w, S)
        elif kind == "bar":
            self._draw_bar(draw, w, S)
        elif kind == "image":
            self._draw_image(image, w, S)

    def _draw_image(self, image: Image.Image, w: Widget, S: int) -> None:
        if not w.path:
            return
        path = Path(w.path)
        if not path.is_absolute() and self.spec.source_dir:
            path = Path(self.spec.source_dir) / path
        if not path.is_file():
            return
        try:
            src = Image.open(path)
            if getattr(src, "n_frames", 1) > 1:
                import time as _time
                total = 0
                delays = []
                for i in range(src.n_frames):
                    src.seek(i)
                    delays.append(max(20, src.info.get("duration", 70)))
                    total += delays[-1]
                at = int(_time.time() * 1000) % total
                acc = 0
                frame_i = 0
                for i, dl in enumerate(delays):
                    if at < acc + dl:
                        frame_i = i
                        break
                    acc += dl
                src.seek(frame_i)
            src = src.convert("RGBA")
        except Exception:
            return
        size = (max(1, int(w.w * S)), max(1, int(w.h * S)))
        image.alpha_composite(src.resize(size), (int(w.x * S), int(w.y * S)))

    @staticmethod
    def _box(x, y, w, h, S):
        return (int(x * S), int(y * S), int((x + max(w, 1)) * S), int((y + max(h, 1)) * S))

    def _draw_text(self, draw: ImageDraw.ImageDraw, content: str,
                   w: Widget, S: int) -> None:
        font = _font(w.size * S)
        anchor = {"left": "ls", "center": "ms", "right": "rs"}.get(w.align, "ls")
        draw.text((w.x * S, w.y * S), content, font=font,
                  fill=_color(w.fill), anchor=anchor)

    def _draw_ring(self, draw: ImageDraw.ImageDraw, w: Widget, S: int) -> None:
        cx, cy = w.cx * S, w.cy * S
        radius = max(4.0, w.r) * S
        thickness = max(1.0, w.thickness) * S
        track = _color(w.track, (30, 36, 56, 255))
        fill = _color(w.fill, (0, 229, 255, 255))
        pct = self._pct(w)
        self._stamped_arc(draw, cx, cy, radius, thickness, w.start, w.sweep, track)
        if pct > 0:
            self._stamped_arc(draw, cx, cy, radius, thickness,
                              w.start, w.sweep * pct / 100.0, fill)
        if w.center_text:
            content = format_template(w.center_text, self.m)
            font = _font(w.center_size * S)
            baseline = cy + int(w.center_size * S) * 2 // 7
            draw.text((cx, baseline), content, font=font, fill=fill, anchor="ms")

    def _draw_bar(self, draw: ImageDraw.ImageDraw, w: Widget, S: int) -> None:
        x, y = int(w.x * S), int(w.y * S)
        bw, bh = int(max(1.0, w.w) * S), int(max(2.0, w.h) * S)
        rad = int((w.r * S) if w.r > 0 else bh // 2)
        rad = max(0, min(rad, bh // 2))
        draw.rounded_rectangle((x, y, x + bw, y + bh), radius=rad,
                               fill=_color(w.track, (30, 36, 56, 255)))
        fw = int(bw * self._pct(w) / 100.0)
        if fw > 0:
            draw.rounded_rectangle((x, y, x + fw, y + bh),
                                   radius=max(0, min(rad, fw // 2)),
                                   fill=_color(w.fill, (0, 229, 255, 255)))

    # -- helpers -----------------------------------------------------------

    def _pct(self, w: Widget) -> float:
        value = self.m.get(w.binding) if w.binding else None
        if value is None or isinstance(value, str):
            value = w.min
        span = max(0.001, w.max - w.min)
        return max(0.0, min(100.0, (float(value) - w.min) / span * 100.0))

    @staticmethod
    def _stamped_arc(draw: ImageDraw.ImageDraw, cx: float, cy: float,
                     radius: float, thickness: float,
                     start_deg: float, sweep_deg: float, color) -> None:
        """Thick arc drawn as a chain of filled circles — the draw.rs technique;
        naturally round-capped and smooth."""
        if sweep_deg <= 0:
            return
        r = thickness / 2.0
        steps = max(8, math.ceil(math.radians(abs(sweep_deg)) * radius * 1.5))
        for i in range(steps + 1):
            a = math.radians(start_deg + sweep_deg * i / steps)
            px = cx + math.cos(a) * radius
            py = cy + math.sin(a) * radius
            draw.ellipse((px - r, py - r, px + r, py + r), fill=color)


# -- hit testing for the Studio canvas ---------------------------------------

def widget_bbox(w: Widget) -> tuple[float, float, float, float]:
    """Approximate (x1, y1, x2, y2) in canvas units for hit testing."""
    if w.kind in ("ring", "circle"):
        r = max(w.r, w.thickness) + 2
        return (w.cx - r, w.cy - r, w.cx + r, w.cy + r)
    if w.kind == "text":
        width = max(30.0, len(w.text) * w.size * 0.62)
        return (w.x - 4, w.y - w.size, w.x + width, w.y + 6)
    return (w.x, w.y, w.x + max(w.w, 4), w.y + max(w.h, 4))


def widget_at(spec: ThemeSpec, x: float, y: float) -> int | None:
    for i in reversed(range(len(spec.widgets))):
        x1, y1, x2, y2 = widget_bbox(spec.widgets[i])
        if x1 <= x <= x2 and y1 <= y <= y2:
            return i
    return None
