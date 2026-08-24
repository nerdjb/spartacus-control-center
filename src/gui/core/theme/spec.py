"""Theme spec model — mirrors the daemon's Rust theme_spec.rs exactly.

A spec is a JSON document describing a 480x480 panel design built from the
same primitives the Rust renderer draws (panel/rect/circle/text/ring/bar).
The daemon renders these natively at cards quality; this module is the
portable model used by LCD Studio.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

BINDINGS = [
    "time", "date",
    "cpu_temp", "cpu_usage", "cpu_freq",
    "gpu_temp", "gpu_usage",
    "ram_used", "ram_total", "ram_free", "ram_pct",
    "disk_used", "disk_total", "disk_free", "disk_pct",
    "net_up", "net_down",
    "pump_rpm", "fan_rpm", "pump_pct",
]

WIDGET_KINDS = ["panel", "text", "ring", "bar", "rect", "circle"]


@dataclass
class Widget:
    kind: str = "panel"
    x: float = 0.0
    y: float = 0.0
    w: float = 100.0
    h: float = 60.0
    cx: float = 240.0
    cy: float = 240.0
    r: float = 14.0            # corner radius (panel/bar) or circle radius
    fill: str = "#232833"
    stroke: str = ""
    stroke_w: float = 0.0
    text: str = "TEXT"         # may contain {binding} / {binding:.N}
    size: float = 16.0
    align: str = "left"        # left | center | right
    thickness: float = 8.0     # ring
    track: str = "#313949"
    binding: str = ""
    min: float = 0.0
    max: float = 100.0
    start: float = -90.0
    sweep: float = 360.0
    center_text: str = ""
    center_size: float = 24.0

    @property
    def name(self) -> str:
        label = (self.text or "").replace("{", "").replace("}", "")[:18].strip()
        return f"{self.kind}: {label}" if label else self.kind

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items()}

    @staticmethod
    def from_dict(d: dict) -> "Widget":
        base = Widget()
        kwargs = {k: v for k, v in d.items() if k in base.__dataclass_fields__}
        return Widget(**kwargs)


@dataclass
class ThemeSpec:
    name: str = "my-theme"
    background: dict = field(default_factory=lambda: {
        "kind": "gradient", "top": "#14171C", "bottom": "#1D222B"})
    widgets: list[Widget] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "background": self.background,
            "widgets": [w.to_dict() for w in self.widgets],
        }

    def save(self, path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False))

    @staticmethod
    def load(path) -> "ThemeSpec":
        data = json.loads(Path(path).read_text())
        return ThemeSpec.from_dict(data)

    @staticmethod
    def from_dict(data: dict) -> "ThemeSpec":
        return ThemeSpec(
            name=data.get("name", "theme"),
            background=data.get("background") or {
                "kind": "gradient", "top": "#0B0E1A", "bottom": "#101528"},
            widgets=[Widget.from_dict(w) for w in data.get("widgets", [])],
        )

    def add(self, widget: Widget) -> None:
        self.widgets.append(widget)

    def remove(self, index: int) -> None:
        if 0 <= index < len(self.widgets):
            self.widgets.pop(index)

    def duplicate(self, index: int) -> int | None:
        if 0 <= index < len(self.widgets):
            clone = Widget.from_dict(self.widgets[index].to_dict())
            clone.x += 12
            clone.y += 12
            clone.cx += 12
            clone.cy += 12
            self.widgets.insert(index + 1, clone)
            return index + 1
        return None


def builtin_specs() -> dict[str, ThemeSpec]:
    """The daemon's embedded spec themes, as editable starting points."""
    root = Path(__file__).resolve().parent / "themes"
    out: dict[str, ThemeSpec] = {}
    for name in ("cards", "cards-light", "neon", "aurora", "slate", "aorus-rose"):
        path = root / f"{name}.json"
        if path.exists():
            try:
                out[name] = ThemeSpec.load(path)
            except Exception:
                pass
    return out
