"""QdtParser: normalized theme model from extracted .qdt content.

Produces a :class:`QdtTheme` — screen geometry/mask, a z-ordered widget list,
and an asset table. Widget descriptors are read from whatever layout files the
container carried (JSON / XML / INI). Anything unparseable is preserved as an
``unresolved`` note so LCD Studio can offer manual binding instead of failing.
"""

from __future__ import annotations

import configparser
import json
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from core.lcd.qdt.container import ExtractedContainer, screen_shape_from_filename

log = logging.getLogger(__name__)

_WIDGET_KINDS = {
    # normalized -> aliases seen in vendor descriptors
    "text": ("text", "label", "txt", "string", "static"),
    "ring": ("ring", "gauge", "circle", "dial", "arc", "progress_circle"),
    "image": ("image", "img", "picture", "bitmap", "sprite", "icon"),
    "bar": ("bar", "progress", "progressbar", "slider"),
}
_KIND_LOOKUP = {
    alias: kind for kind, aliases in _WIDGET_KINDS.items() for alias in aliases
}


@dataclass
class QdtWidget:
    """One normalized widget from a .qdt descriptor."""

    kind: str                       # text | ring | image | bar | unknown
    name: str
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0
    z: int = 0
    variable: str = ""              # bound metric variable, unmapped yet
    asset: str = ""                 # image member name if any
    color: str = ""                 # "#RRGGBB" or "R,G,B"
    color2: str = ""                # gradient end / track color
    min_value: float = 0.0
    max_value: float = 100.0
    start_angle: float = 0.0
    end_angle: float = 360.0
    thickness: float = 8.0
    font_size: int = 16
    text_format: str = "{value}"
    extra: dict = field(default_factory=dict)


@dataclass
class QdtTheme:
    source_name: str
    width: int = 480
    height: int = 480
    round_screen: bool = True
    widgets: list[QdtWidget] = field(default_factory=list)
    assets: dict[str, bytes] = field(default_factory=dict)
    unresolved: list[str] = field(default_factory=list)

    def summary(self) -> str:
        kinds = [w.kind for w in self.widgets]
        return (
            f"QdtTheme({self.source_name!r} {self.width}x{self.height} "
            f"round={self.round_screen} widgets={len(self.widgets)} "
            f"assets={len(self.assets)} unresolved={len(self.unresolved)})"
        )


class QdtParser:
    """Parses :class:`ExtractedContainer` content into a :class:`QdtTheme`."""

    def __init__(self, cache_dir: Path | None = None):
        self.cache_dir = cache_dir

    def parse(self, container: ExtractedContainer, source_name: str = "theme.qdt") -> QdtTheme:
        shape = screen_shape_from_filename(source_name)
        theme = QdtTheme(
            source_name=source_name,
            width=shape[0] if shape else 480,
            height=shape[1] if shape else 480,
            round_screen=bool(shape and shape[2]),
        )
        theme.assets = dict(container.images)
        theme.unresolved.extend(container.warnings)

        for desc_name, text in sorted(container.descriptors.items()):
            parsed_any = False
            stripped = text.lstrip()
            try:
                if stripped.startswith("<"):  # XML documents only; '[' is ambiguous
                    parsed_any = self._parse_xml(text, theme)
                elif stripped.startswith(("{", "[")):
                    # '[' prefixes both JSON arrays and INI sections: try JSON,
                    # fall back to INI on failure.
                    try:
                        parsed_any = self._parse_json(text, theme)
                    except (ValueError, TypeError):
                        parsed_any = self._parse_ini(text, theme)
                else:
                    parsed_any = self._parse_ini(text, theme)
            except Exception as exc:
                log.warning("qdt: failed to parse %s: %s", desc_name, exc)
                theme.unresolved.append(f"{desc_name}: {exc}")
            if not parsed_any:
                # Descriptor existed but matched nothing; keep evidence around.
                if f"{desc_name}" not in theme.unresolved:
                    theme.unresolved.append(f"{desc_name}: no recognizable widgets")
        return theme

    def export_assets(self, theme: QdtTheme) -> dict[str, Path]:
        """Write extracted images to the cache dir; returns name -> path."""
        written: dict[str, Path] = {}
        if self.cache_dir is None or not theme.assets:
            return written
        import hashlib

        target = self.cache_dir / hashlib.sha1(
            (theme.source_name + str(len(theme.assets))).encode()
        ).hexdigest()[:12]
        target.mkdir(parents=True, exist_ok=True)
        for name, blob in theme.assets.items():
            safe = re.sub(r"[^A-Za-z0-9_.-]", "_", name)
            path = target / safe
            path.write_bytes(blob)
            written[name] = path
        return written

    # -- JSON -----------------------------------------------------------------

    def _parse_json(self, text: str, theme: QdtTheme) -> bool:
        data = json.loads(text)
        found = False
        if isinstance(data, dict):
            size = data.get("screen") or data.get("resolution") or {}
            if isinstance(size, dict):
                w, h = size.get("width"), size.get("height")
                if isinstance(w, int) and isinstance(h, int):
                    theme.width, theme.height = w, h
                    found = True
            entries = (
                data.get("widgets") or data.get("elements")
                or data.get("items") or []
            )
            for i, entry in enumerate(entries or []):
                if isinstance(entry, dict):
                    theme.widgets.append(self._widget_from_mapping(entry, index=i))
                    found = True
        elif isinstance(data, list):
            for i, entry in enumerate(data):
                if isinstance(entry, dict):
                    theme.widgets.append(self._widget_from_mapping(entry, index=i))
                    found = True
        return found

    # -- XML ------------------------------------------------------------------

    def _parse_xml(self, text: str, theme: QdtTheme) -> bool:
        root = ET.fromstring(text)
        found = False
        for i, node in enumerate(root.iter()):
            tag = node.tag.lower().rsplit("}", 1)[-1]
            kind = _KIND_LOOKUP.get(tag)
            if kind is None:
                continue
            widget = self._widget_from_mapping(dict(node.attrib), index=i)
            widget.kind = kind
            widget.extra["inner_text"] = (node.text or "").strip()
            theme.widgets.append(widget)
            found = True
        return found

    # -- INI / key=value --------------------------------------------------------

    def _parse_ini(self, text: str, theme: QdtTheme) -> bool:
        parser = configparser.ConfigParser(strict=False, interpolation=None)
        parser.read_string(text)
        found = False
        index = 0
        for section in parser.sections():
            low = section.lower()
            kind = _KIND_LOOKUP.get(low.split("_", 1)[0]) or _KIND_LOOKUP.get(
                low.rsplit("_", 1)[0]
            ) or _KIND_LOOKUP.get(low)
            items = dict(parser.items(section))
            if kind is None:
                # Sections like [Widget1]: infer from keys inside.
                type_hint = str(items.get("type", "")).lower()
                kind = _KIND_LOOKUP.get(type_hint)
                if kind is None:
                    theme.unresolved.append(f"[{section}] ignored (keys: {sorted(items)})")
                    continue
            widget = self._widget_from_mapping(items, index=index)
            widget.kind = kind
            widget.name = section
            theme.widgets.append(widget)
            index += 1
            found = True
        return found

    # -- mapping helpers ----------------------------------------------------------

    _NUM_KEYS_X = ("x", "left", "pos_x", "posx")
    _NUM_KEYS_Y = ("y", "top", "pos_y", "posy")
    _VAR_KEYS = ("variable", "var", "data", "source", "bind", "binding", "metric")

    @classmethod
    def _first_num(cls, items: dict, keys: tuple[str, ...], default: float = 0.0) -> float:
        low = {k.lower(): v for k, v in items.items()}
        for key in keys:
            if key in low:
                try:
                    return float(low[key])
                except (TypeError, ValueError):
                    pass
        return default

    @classmethod
    def _first_str(cls, items: dict, keys: tuple[str, ...]) -> str:
        low = {k.lower(): v for k, v in items.items()}
        for key in keys:
            if key in low and low[key]:
                return str(low[key])
        return ""

    def _widget_from_mapping(self, entry: dict, index: int) -> QdtWidget:
        low = {k.lower(): v for k, v in entry.items()}
        type_hint = str(low.get("type", "")).lower()
        kind = _KIND_LOOKUP.get(type_hint, "unknown")

        rect = entry.get("rect") or entry.get("geometry")
        x = y = w = h = 0.0
        if isinstance(rect, str):
            nums = re.findall(r"-?\d+(?:\.\d+)?", rect)
            if len(nums) >= 4:
                x, y, w, h = (float(n) for n in nums[:4])
        elif isinstance(rect, (list, tuple)) and len(rect) >= 4:
            x, y, w, h = (float(v) for v in rect[:4])

        return QdtWidget(
            kind=kind,
            name=str(entry.get("name") or entry.get("id") or f"widget_{index}"),
            x=self._first_num(entry, self._NUM_KEYS_X, x),
            y=self._first_num(entry, self._NUM_KEYS_Y, y),
            width=self._first_num(entry, ("width", "w"), w),
            height=self._first_num(entry, ("height", "h"), h),
            z=int(self._first_num(entry, ("z", "zorder", "z_order", "layer"), index)),
            variable=self._first_str(entry, self._VAR_KEYS),
            asset=str(low.get("image", low.get("src", low.get("asset", "")))),
            color=str(low.get("color", low.get("active_color", low.get("fg", "")))),
            color2=str(low.get("color2", low.get("track_color", low.get("bg", "")))),
            min_value=self._first_num(entry, ("min", "min_value", "minimum"), 0.0),
            max_value=self._first_num(entry, ("max", "max_value", "maximum"), 100.0),
            start_angle=self._first_num(entry, ("start_angle", "angle_start"), 0.0),
            end_angle=self._first_num(entry, ("end_angle", "angle_end"), 360.0),
            thickness=self._first_num(entry, ("thickness", "width_ring", "line_width"), 8.0),
            font_size=int(self._first_num(entry, ("font_size", "fontsize", "size")), ),
            text_format=str(low.get("format", low.get("format_string", "{value}"))),
            extra=dict(entry),
        )
