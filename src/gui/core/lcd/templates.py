"""Built-in editable LCD Studio templates.

Each preset is a native :class:`LcdLayout` generated programmatically (no
third-party assets), styled after popular QDT theme families: Apple Style,
MSI Style, Black Tech, Minimal Cyber, Dual Ring, Triple Ring.
"""

from __future__ import annotations

from core.lcd.model import (
    Background,
    Gradient,
    GradientKind,
    ImageElement,
    LcdLayout,
    RingElement,
    ShapeElement,
    ShapeKind,
    TextElement,
    new_id,
)

CYAN = "#00F0FF"
BLUE = "#0066FF"
PURPLE = "#8A2BE2"
GREEN = "#00FF66"
TRACK = "#2A2E35"


def _text(name, x, y, text, size, color="#FFFFFF", bold=True, spacing=0.0):
    return TextElement(
        id=new_id("text"), name=name, x=x, y=y, text=text,
        font_size=size, bold=bold, color=color, letter_spacing=spacing,
        alignment="center",
    )


def _ring(name, radius, thickness, key, active, start=135.0, end=405.0,
          mn=0.0, mx=100.0):
    return RingElement(
        id=new_id("ring"), name=name, x=240.0, y=240.0,
        radius=radius, thickness=thickness,
        start_angle_deg=start, end_angle_deg=end,
        track_color=TRACK, active_color=active,
        binding_key=key, min_value=mn, max_value=mx,
    )


def apple_style() -> LcdLayout:
    layout = LcdLayout(name="Apple Style", round_mask=True)
    layout.background = Background(Gradient(GradientKind.LINEAR, "#1C1C1E", "#000000"))
    layout.add(_text("clock", 240, 150, "{cpu_temp}", 72, "#FFFFFF"))
    layout.add(_text("unit", 240, 205, "°C  CPU", 22, "#98989D", bold=False))
    layout.add(_ring("usage_ring", 170, 10, "cpu_usage", "#FFFFFF", 90.0, 450.0))
    layout.add(_text("usage", 240, 330, "{cpu_usage}%", 30, "#FFFFFF"))
    return layout


def msi_style() -> LcdLayout:
    layout = LcdLayout(name="MSI Style", round_mask=True)
    layout.background = Background(Gradient(GradientKind.LINEAR, "#0B0B0D", "#17171C"))
    layout.add(ImageElement(
        id=new_id("image"), name="logo_bg", x=140, y=140,
        width=200, height=200, keep_aspect=True,
    ))
    layout.add(_ring("cpu_ring", 190, 16, "cpu_temp", "#D5001F", 135.0, 405.0, 0, 100))
    layout.add(_text("cpu_label", 240, 120, "CPU {cpu_temp}°C", 26, "#FFFFFF"))
    layout.add(_ring("gpu_ring", 150, 12, "gpu_temp", BLUE, 135.0, 405.0, 0, 100))
    layout.add(_text("gpu_label", 240, 340, "GPU {gpu_temp}°C", 24, "#FFFFFF"))
    return layout


def black_tech() -> LcdLayout:
    layout = LcdLayout(name="Black Tech", round_mask=True)
    layout.background = Background(Gradient(GradientKind.RADIAL, "#101418", "#000000"))
    layout.add(ShapeElement(
        id=new_id("shape"), name="crosshair_h", x=60, y=239,
        shape=ShapeKind.LINE, width=360, height=2,
        stroke_color=TRACK, stroke_width=2,
    ))
    layout.add(_ring("outer", 210, 6, "pump_rpm", PURPLE, 0, 360, 0, 6000))
    layout.add(_text("rpm", 240, 240, "{pump_rpm}", 44, CYAN))
    layout.add(_text("rpm_unit", 240, 275, "PUMP RPM", 14, "#5C6470", bold=False, spacing=3.0))
    layout.add(_text("liquid", 240, 380, "{liquid_temp}°C LIQUID", 18, GREEN))
    return layout


def minimal_cyber() -> LcdLayout:
    layout = LcdLayout(name="Minimal Cyber", round_mask=True)
    layout.background = Background(Gradient(GradientKind.LINEAR, "#05070A", "#0C1015"))
    layout.add(_ring("temp_arc", 180, 20, "cpu_temp", CYAN, 135.0, 405.0, 20, 95))
    layout.add(_text("temp", 240, 225, "{cpu_temp}", 64, "#FFFFFF"))
    layout.add(_text("deg", 240, 268, "°C", 22, CYAN))
    layout.add(_text("load", 240, 400, "LOAD {cpu_usage}%", 18, "#5C6470", bold=False))
    return layout


def dual_ring() -> LcdLayout:
    layout = LcdLayout(name="Dual Ring", round_mask=True)
    layout.background = Background(Gradient(GradientKind.LINEAR, "#0A0C10", "#12151B"))
    layout.add(_ring("cpu_outer", 205, 14, "cpu_usage", CYAN, 120.0, 420.0))
    layout.add(_ring("gpu_inner", 165, 14, "gpu_usage", BLUE, 120.0, 420.0))
    layout.add(_text("cpu_txt", 240, 215, "CPU {cpu_usage}%", 24, "#FFFFFF"))
    layout.add(_text("gpu_txt", 240, 265, "GPU {gpu_usage}%", 24, "#9FB4C7"))
    return layout


def triple_ring() -> LcdLayout:
    layout = LcdLayout(name="Triple Ring", round_mask=True)
    layout.background = Background(Gradient(GradientKind.LINEAR, "#07080B", "#141821"))
    layout.add(_ring("ring_cpu", 215, 10, "cpu_temp", GREEN, 150.0, 390.0, 20, 95))
    layout.add(_ring("ring_gpu", 185, 10, "gpu_temp", CYAN, 150.0, 390.0, 20, 95))
    layout.add(_ring("ring_pump", 155, 10, "aio_rpm", PURPLE, 150.0, 390.0, 0, 2500))
    layout.add(_text("center", 240, 235, "{cpu_temp}°C", 34, "#FFFFFF"))
    layout.add(_text("sub", 240, 280, "{gpu_temp}°C GPU", 16, "#5C6470", bold=False))
    return layout


BUILDERS = {
    "apple_style": apple_style,
    "msi_style": msi_style,
    "black_tech": black_tech,
    "minimal_cyber": minimal_cyber,
    "dual_ring": dual_ring,
    "triple_ring": triple_ring,
}


def get_all() -> dict[str, LcdLayout]:
    """Fresh instances of every built-in template."""
    return {name: builder() for name, builder in BUILDERS.items()}
