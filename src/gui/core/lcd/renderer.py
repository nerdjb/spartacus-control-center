"""Validated 480x480 LCD renderer.

The renderer accepts a TelemetryPipeline, never a raw daemon dictionary. A
missing or non-GOOD binding produces a neutral track / ``--`` placeholder.
Text, image and shape layers honor ``rotation_deg`` and ``opacity``.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageFont

from core.lcd.bindings import BindingResolver
from core.lcd.model import (
    GradientKind,
    ImageElement,
    LcdLayout,
    RingElement,
    ShapeElement,
    ShapeKind,
    TextElement,
)
from core.telemetry.pipeline import TelemetryPipeline


CANVAS_SIZE = (480, 480)
_ANCHORS = {"left": "lm", "right": "rm", "center": "mm"}


class LcdRenderer:
    """Render an editable layout to an exact RGB 480x480 frame."""

    def __init__(self, layout: LcdLayout, pipeline: TelemetryPipeline):
        if (layout.width, layout.height) != CANVAS_SIZE:
            raise ValueError("LCD layouts must be exactly 480x480")
        self.layout = layout
        self.pipeline = pipeline
        self.bindings = BindingResolver(pipeline)

    def render(self, *, mask: bool | None = None, realistic: bool = False) -> Image.Image:
        image = Image.new("RGBA", CANVAS_SIZE, (18, 20, 23, 255))
        draw = ImageDraw.Draw(image)
        self._background(image, draw)
        for element in self.layout.elements:
            if not element.visible:
                continue
            if isinstance(element, TextElement):
                self._composite_text(image, element)
            elif isinstance(element, RingElement):
                self._ring(draw, element)
            elif isinstance(element, ImageElement):
                self._composite_image(image, element)
            elif isinstance(element, ShapeElement):
                self._composite_shape(image, element)
        effective_mask = self.layout.round_mask if mask is None else mask
        if effective_mask:
            alpha = Image.new("L", CANVAS_SIZE, 0)
            ImageDraw.Draw(alpha).ellipse((0, 0, 479, 479), fill=255)
            image.putalpha(alpha)
        if realistic:
            image = self._pump_frame(image)
        return image.convert("RGB")

    def render_jpeg(self, quality: int = 90) -> bytes:
        import io

        output = io.BytesIO()
        self.render().save(output, format="JPEG", quality=max(1, min(95, quality)),
                           subsampling=0, optimize=False, progressive=False)
        return output.getvalue()

    # -- background -----------------------------------------------------------

    def _background(self, image, draw) -> None:
        gradient = self.layout.background.gradient
        if gradient.kind is GradientKind.NONE:
            draw.rectangle((0, 0, 479, 479), fill=_color(gradient.color_from))
        else:
            start = ImageColor.getrgb(gradient.color_from)
            end = ImageColor.getrgb(gradient.color_to)
            vertical = gradient.angle_deg % 180 != 0
            limit = 480
            for step in range(limit):
                factor = step / (limit - 1)
                color = tuple(int(start[i] + (end[i] - start[i]) * factor) for i in range(3))
                if vertical:
                    draw.line((0, step, 479, step), fill=color)
                else:
                    draw.line((step, 0, step, 479), fill=color)
        if self.layout.background.image_path:
            path = Path(self.layout.background.image_path)
            if path.exists():
                bg = Image.open(path).convert("RGBA").resize(CANVAS_SIZE)
                image.alpha_composite(bg)

    # -- composited layers (text / image / shape share rotation+opacity) -------

    def _composite_text(self, image: Image.Image, element: TextElement) -> None:
        text = self.bindings.resolve(element.text)
        font = _font(element.font_family, element.font_size, element.bold)
        spacing = max(0, int(element.letter_spacing))
        if spacing:
            text = _spaced(text, spacing)
        size = font.getbbox(text or " ")
        width = max(2, size[2] - size[0] + 4 + spacing * len(text))
        height = max(2, size[3] - size[1] + 8)
        layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        ImageDraw.Draw(layer).text((2 - size[0], 4 - size[1]), text,
                                   font=font, fill=_color(element.color))
        self._finish_layer(image, layer, element.x, element.y,
                           element.rotation_deg, element.opacity)

    def _composite_image(self, image: Image.Image, element: ImageElement) -> None:
        path = Path(element.asset_path)
        if not path.exists():
            return
        try:
            source = Image.open(path).convert("RGBA")
        except Exception:
            # Unrasterizable asset (e.g. raw SVG): draw a placeholder frame
            # rather than killing the whole render pass.
            source = Image.new("RGBA", (64, 64), (138, 43, 226, 90))
        if element.crop:
            l, t, r, b = element.crop
            box = (int(l * source.width), int(t * source.height),
                   int(r * source.width), int(b * source.height))
            source = source.crop(box)
        target = (max(1, int(element.width)), max(1, int(element.height)))
        if element.keep_aspect:
            source.thumbnail(target)
        else:
            source = source.resize(target)
        self._finish_layer(image, source, element.x + source.width / 2,
                           element.y + source.height / 2,
                           element.rotation_deg, element.opacity)

    def _composite_shape(self, image: Image.Image, element: ShapeElement) -> None:
        width = max(4, int(abs(element.width)) + int(element.stroke_width) * 2 + 4)
        height = max(4, int(abs(element.height)) + int(element.stroke_width) * 2 + 4)
        layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        pen = _color(element.stroke_color)
        fill = _color(element.fill_color)
        inset = int(element.stroke_width) + 1
        box = (inset, inset, width - inset, height - inset)
        line_w = max(1, int(element.stroke_width))
        if element.shape is ShapeKind.LINE:
            draw.line((box[0], height / 2, box[2], height / 2), fill=pen, width=line_w)
        elif element.shape is ShapeKind.CIRCLE:
            draw.ellipse(box, outline=pen, fill=fill, width=line_w)
        elif element.shape is ShapeKind.ARC:
            draw.arc(box, element.start_angle_deg, element.end_angle_deg,
                     fill=pen, width=line_w)
        elif element.shape is ShapeKind.ROUNDED_RECTANGLE:
            draw.rounded_rectangle(box, radius=max(0, element.corner_radius),
                                   outline=pen, fill=fill, width=line_w)
        else:
            draw.rectangle(box, outline=pen, fill=fill, width=line_w)
        cx = element.x + element.width / 2
        cy = element.y + element.height / 2
        self._finish_layer(image, layer, cx, cy, element.rotation_deg, element.opacity)

    @staticmethod
    def _finish_layer(canvas: Image.Image, layer: Image.Image,
                      cx: float, cy: float, rotation_deg: float, opacity: float) -> None:
        if opacity < 1.0:
            alpha = layer.getchannel("A").point(
                lambda a: int(a * max(0.0, min(1.0, opacity))))
            layer.putalpha(alpha)
        if rotation_deg % 360:
            layer = layer.rotate(-rotation_deg, expand=True, resample=Image.BICUBIC)
        canvas.alpha_composite(layer, (int(cx - layer.width / 2), int(cy - layer.height / 2)))

    # -- direct-drawn ring gauge -------------------------------------------------

    def _ring(self, draw, element: RingElement) -> None:
        box = (element.x - element.radius, element.y - element.radius,
               element.x + element.radius, element.y + element.radius)
        thickness = max(1, int(element.thickness))
        draw.arc(box, element.start_angle_deg, element.end_angle_deg,
                 fill=_color(element.track_color), width=thickness)
        fraction = (self.bindings.fraction(element.binding_key, element.min_value,
                                           element.max_value)
                    if element.binding_key else 0.0)
        if fraction is not None and fraction > 0:
            span = element.end_angle_deg - element.start_angle_deg
            draw.arc(box, element.start_angle_deg,
                     element.start_angle_deg + span * fraction,
                     fill=_color(element.active_color), width=thickness)

    @staticmethod
    def _pump_frame(image: Image.Image) -> Image.Image:
        frame = Image.new("RGB", CANVAS_SIZE, (8, 9, 11))
        draw = ImageDraw.Draw(frame)
        draw.rounded_rectangle((4, 4, 475, 475), radius=28, outline=(42, 46, 53), width=3)
        inset = image.resize((444, 444))
        frame.paste(inset, (18, 18))
        return frame


def _spaced(text: str, spacing: int) -> str:
    gap = " " * max(1, spacing // 6)
    return gap.join(list(text))


def _color(value: str):
    try:
        return ImageColor.getcolor(value, "RGBA")
    except ValueError:
        return (255, 255, 255, 255)


def _font(family: str, size: int, bold: bool):
    style = "-Bold" if bold else ""
    candidates = [
        f"/usr/share/fonts/truetype/dejavu/DejaVuSans{style}.ttf",
        f"/usr/share/fonts/dejavu/DejaVuSans{style}.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, max(1, int(size)))
    return ImageFont.load_default()
