"""Convert a parsed :class:`QdtTheme` into a native, fully editable LcdLayout."""

from __future__ import annotations

import logging
import re
from pathlib import Path

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
from core.lcd.qdt.mapper import TelemetryMapper
from core.lcd.qdt.parser import QdtTheme, QdtWidget

log = logging.getLogger(__name__)


def parse_color(value: str, fallback: str = "#FFFFFF") -> str:
    """Normalize '#RRGGBB', 'R,G,B' or '0xRRGGBB' to '#RRGGBB'."""
    if not value:
        return fallback
    v = value.strip().lstrip("#")
    if v.lower().startswith("0x"):
        v = v[2:]
    parts = v.split(",")
    if len(parts) == 3:
        try:
            return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, int(p))) for p in parts))
        except ValueError:
            return fallback
    if re.fullmatch(r"[0-9a-fA-F]{6}", v):
        return f"#{v.lower()}"
    return fallback


def qdt_to_layout(
    theme: QdtTheme,
    asset_paths: dict[str, Path] | None = None,
    mapper: TelemetryMapper | None = None,
) -> tuple[LcdLayout, list[str]]:
    """Build an editable :class:`LcdLayout` from *theme*.

    Returns ``(layout, notes)`` where notes describe every lossy/ambiguous
    conversion so LCD Studio can surface them to the user.
    """
    mapper = mapper or TelemetryMapper()
    asset_paths = asset_paths or {}
    layout = LcdLayout(
        name=Path(theme.source_name).stem or "QDT Theme",
        width=theme.width,
        height=theme.height,
        round_mask=theme.round_screen,
        background=Background(
            gradient=Gradient(GradientKind.LINEAR, "#000000", "#101318", 90.0)
        ),
    )
    notes: list[str] = []
    cx, cy = theme.width / 2.0, theme.height / 2.0

    for widget in sorted(theme.widgets, key=lambda w: w.z):
        key = mapper.map_variable(widget.variable)

        if widget.kind == "ring":
            layout.add(_convert_ring(widget, cx, cy, key))
        elif widget.kind == "bar":
            layout.add(_convert_ring(widget, cx, cy, key))
            notes.append(f"'{widget.name}': bar rendered as arc ring (native form)")
        elif widget.kind == "image":
            layout.add(_convert_image(widget, asset_paths.get(widget.asset, "")))
            if widget.asset and widget.asset not in asset_paths:
                notes.append(f"'{widget.name}': image '{widget.asset}' missing from package")
        elif widget.kind == "text":
            layout.add(_convert_text(widget, key, cx, cy))
        else:
            # Unknown descriptor widget with geometry — keep as placeholder shape.
            if widget.width > 0 and widget.height > 0:
                layout.add(ShapeElement(
                    id=new_id("shape"),
                    name=widget.name or "imported",
                    x=widget.x, y=widget.y,
                    shape=ShapeKind.RECTANGLE,
                    width=widget.width, height=widget.height,
                    stroke_color="#8A2BE2",
                    fill_color="#00000000",
                ))
                notes.append(
                    f"'{widget.name}' (kind={widget.kind}) imported as placeholder rectangle"
                )
            else:
                notes.append(f"'{widget.name}' (kind={widget.kind}) skipped: no geometry")

    for name in sorted(mapper.unresolved):
        notes.append(f"variable '{name}' unmapped — bind manually in LCD Studio")

    return layout, notes


def _position(widget: QdtWidget, cx: float, cy: float) -> tuple[float, float]:
    """QDT positions are absolute; fall back to canvas center when unset."""
    return (widget.x if widget.x else cx, widget.y if widget.y else cy)


def _convert_ring(
    widget: QdtWidget, cx: float, cy: float, binding_key: str | None
) -> RingElement:
    if widget.width and widget.height:
        radius = max(4.0, min(widget.width, widget.height) / 2.0)
    else:
        radius = max(40.0, min(cx, cy) * 0.7)
    x, y = _position(widget, cx, cy)
    end_angle = widget.end_angle if widget.end_angle > widget.start_angle else 360.0
    return RingElement(
        id=new_id("ring"),
        name=widget.name or "ring",
        x=x, y=y,
        radius=radius,
        thickness=max(2.0, widget.thickness),
        start_angle_deg=widget.start_angle,
        end_angle_deg=end_angle,
        track_color=parse_color(widget.color2, "#2A2E35"),
        active_color=parse_color(widget.color, "#00F0FF"),
        gradient=None,
        binding_key=binding_key or "",
        min_value=widget.min_value,
        max_value=widget.max_value,
    )


_VALUE_PLACEHOLDER = re.compile(r"\{value(:[^}]*)?\}")


def _convert_text(
    widget: QdtWidget, binding_key: str | None, cx: float, cy: float
) -> TextElement:
    template = widget.text_format or "{value}"
    literal = str(widget.extra.get("inner_text") or widget.extra.get("text") or "TEXT")
    if binding_key:
        # 'CPU {value:.0f}°C' templates keep their literal decoration and any
        # format spec; only the placeholder name is rebound.
        rebound = _VALUE_PLACEHOLDER.sub(
            lambda m: "{" + binding_key + (m.group(1) or "") + "}", template
        )
        text = rebound if rebound != template else f"{literal} {{{binding_key}}}"
    else:
        text = literal
    x, y = _position(widget, cx, cy)
    return TextElement(
        id=new_id("text"),
        name=widget.name or "text",
        x=x, y=y,
        text=text,
        font_size=max(6, widget.font_size),
        color=parse_color(widget.color, "#FFFFFF"),
    )


def _convert_image(widget: QdtWidget, asset_path: str = "") -> ImageElement:
    return ImageElement(
        id=new_id("image"),
        name=widget.name or "image",
        x=widget.x, y=widget.y,
        width=widget.width or 100.0,
        height=widget.height or 100.0,
        asset_path=asset_path if asset_path else "",
        keep_aspect=True,
    )
