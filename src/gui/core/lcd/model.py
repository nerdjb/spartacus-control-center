"""Native LCD Studio layout model (480×480 canvas).

Dataclass-based, JSON-serializable (``.slayout.json``). The Qt scene
(``core/lcd/scene.py``) and QPainter renderer (``core/lcd/renderer.py``)
operate on these structures; QDT import converts into them.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class ElementType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    RING = "ring"
    SHAPE = "shape"
    GROUP = "group"


class ShapeKind(str, Enum):
    RECTANGLE = "rectangle"
    ROUNDED_RECTANGLE = "rounded_rectangle"
    CIRCLE = "circle"
    LINE = "line"
    ARC = "arc"


class GradientKind(str, Enum):
    NONE = "none"
    LINEAR = "linear"
    RADIAL = "radial"


@dataclass
class Gradient:
    kind: GradientKind = GradientKind.NONE
    color_from: str = "#000000"
    color_to: str = "#FFFFFF"
    angle_deg: float = 90.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["kind"] = self.kind.value
        return d

    @staticmethod
    def from_dict(d: dict) -> "Gradient":
        return Gradient(
            kind=GradientKind(d.get("kind", "none")),
            color_from=d.get("color_from", "#000000"),
            color_to=d.get("color_to", "#FFFFFF"),
            angle_deg=float(d.get("angle_deg", 90.0)),
        )


@dataclass
class BaseElement:
    id: str
    name: str
    x: float = 0.0
    y: float = 0.0
    rotation_deg: float = 0.0
    opacity: float = 1.0
    visible: bool = True
    locked: bool = False

    @property
    def element_type(self) -> ElementType:
        raise NotImplementedError


@dataclass
class TextElement(BaseElement):
    text: str = "TEXT"                       # may contain {cpu_temp} bindings
    font_family: str = "DejaVu Sans"
    font_size: int = 24
    bold: bool = False
    alignment: str = "center"                # left | center | right
    letter_spacing: float = 0.0
    color: str = "#FFFFFF"

    @property
    def element_type(self) -> ElementType:
        return ElementType.TEXT


@dataclass
class ImageElement(BaseElement):
    asset_path: str = ""
    width: float = 100.0
    height: float = 100.0
    keep_aspect: bool = True
    crop: Optional[tuple[float, float, float, float]] = None  # l,t,r,b fractions

    @property
    def element_type(self) -> ElementType:
        return ElementType.IMAGE


@dataclass
class RingElement(BaseElement):
    """Custom ring / gauge with telemetry binding and smooth interpolation."""

    radius: float = 160.0
    thickness: float = 14.0
    start_angle_deg: float = 0.0
    end_angle_deg: float = 360.0
    track_color: str = "#2A2E35"
    active_color: str = "#00F0FF"
    gradient: Optional[Gradient] = None
    binding_key: str = ""                    # canonical metric key, "" = static
    min_value: float = 0.0
    max_value: float = 100.0
    smoothing_s: float = 0.4                 # value interpolation time constant

    @property
    def element_type(self) -> ElementType:
        return ElementType.RING


@dataclass
class ShapeElement(BaseElement):
    shape: ShapeKind = ShapeKind.RECTANGLE
    width: float = 100.0
    height: float = 100.0
    stroke_color: str = "#00F0FF"
    fill_color: str = "#00000000"            # RGBA hex; alpha 00 = no fill
    stroke_width: float = 2.0
    corner_radius: float = 8.0
    start_angle_deg: float = 0.0             # arc only
    end_angle_deg: float = 180.0

    @property
    def element_type(self) -> ElementType:
        return ElementType.SHAPE


@dataclass
class GroupElement(BaseElement):
    member_ids: list[str] = field(default_factory=list)

    @property
    def element_type(self) -> ElementType:
        return ElementType.GROUP


@dataclass
class Background:
    gradient: Gradient = field(default_factory=lambda: Gradient(GradientKind.LINEAR,
                                                                "#121417", "#1B1E23"))
    image_path: str = ""

    def to_dict(self) -> dict:
        return {"gradient": self.gradient.to_dict(), "image_path": self.image_path}

    @staticmethod
    def from_dict(d: dict) -> "Background":
        g = Gradient.from_dict(d.get("gradient") or {})
        return Background(gradient=g, image_path=d.get("image_path", ""))


_ELEMENT_TYPES: dict = {}


def _register(cls):
    _ELEMENT_TYPES[cls.__name__] = cls
    return cls


for _cls in (TextElement, ImageElement, RingElement, ShapeElement, GroupElement):
    _register(_cls)


@dataclass
class LcdLayout:
    """A complete editable LCD screen definition."""

    name: str = "Untitled"
    width: int = 480
    height: int = 480
    round_mask: bool = True
    background: Background = field(default_factory=Background)
    elements: list = field(default_factory=list)   # z-ordered back → front
    version: str = "2.0"

    # -- element management ---------------------------------------------------

    def add(self, element, *, to_front: bool = True) -> None:
        if to_front:
            self.elements.append(element)
        else:
            self.elements.insert(0, element)

    def remove(self, element_id: str) -> bool:
        before = len(self.elements)
        self.elements = [e for e in self.elements if e.id != element_id]
        return len(self.elements) != before

    def get(self, element_id: str):
        for e in self.elements:
            if e.id == element_id:
                return e
        return None

    def reorder(self, element_id: str, mode: str) -> None:
        """mode: front | back | forward | backward"""
        idx = next((i for i, e in enumerate(self.elements) if e.id == element_id), -1)
        if idx < 0:
            return
        el = self.elements.pop(idx)
        if mode == "front":
            self.elements.append(el)
        elif mode == "back":
            self.elements.insert(0, el)
        elif mode == "forward":
            self.elements.insert(min(idx + 1, len(self.elements)), el)
        elif mode == "backward":
            self.elements.insert(max(idx - 1, 0), el)

    def duplicate(self, element_id: str):
        import copy

        src = self.get(element_id)
        if src is None:
            return None
        clone = copy.deepcopy(src)
        clone.id = new_id(src.element_type.value)
        clone.name = f"{src.name} copy"
        clone.x += 12
        clone.y += 12
        idx = self.elements.index(src)
        self.elements.insert(idx + 1, clone)
        return clone

    # -- persistence -------------------------------------------------------------

    def to_dict(self) -> dict:
        elements = []
        for e in self.elements:
            d = asdict(e)
            d["__class"] = type(e).__name__
            if isinstance(getattr(e, "crop", None), tuple):
                d["crop"] = list(e.crop)
            if getattr(e, "gradient", None) is not None:
                d["gradient"] = e.gradient.to_dict()
            elements.append(d)
        return {
            "version": self.version,
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "round_mask": self.round_mask,
            "background": self.background.to_dict(),
            "elements": elements,
        }

    @staticmethod
    def from_dict(data: dict) -> "LcdLayout":
        layout = LcdLayout(
            name=data.get("name", "Untitled"),
            width=int(data.get("width", 480)),
            height=int(data.get("height", 480)),
            round_mask=bool(data.get("round_mask", True)),
            background=Background.from_dict(data.get("background") or {}),
        )
        for edata in data.get("elements", []):
            cls = _ELEMENT_TYPES.get(edata.get("__class", ""))
            if cls is None:
                continue
            kwargs = {k: v for k, v in edata.items()
                      if k in cls.__dataclass_fields__ and k not in ("gradient",)}
            if "gradient" in edata and "gradient" in cls.__dataclass_fields__ \
                    and edata["gradient"] is not None:
                kwargs["gradient"] = Gradient.from_dict(edata["gradient"])
            if "crop" in kwargs and isinstance(kwargs["crop"], list):
                kwargs["crop"] = tuple(kwargs["crop"])
            layout.elements.append(cls(**kwargs))
        return layout

    def save(self, path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2))

    @staticmethod
    def load(path) -> "LcdLayout":
        return LcdLayout.from_dict(json.loads(Path(path).read_text()))
