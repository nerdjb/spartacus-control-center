import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "gui"))

from core.lcd.model import LcdLayout, RingElement, TextElement
from core.lcd.renderer import LcdRenderer
from core.telemetry.pipeline import TelemetryPipeline


class TestLcdRenderer(unittest.TestCase):
    def test_exact_rgb_frame_and_jpeg(self):
        pipeline = TelemetryPipeline.default()
        pipeline.ingest({"cpu_temp": 47.0}, now_ms=1000)
        layout = LcdLayout(name="test")
        layout.add(TextElement(id="text", name="cpu", x=240, y=120, text="CPU {cpu_temp}C"))
        layout.add(RingElement(id="ring", name="cpu", x=240, y=240, binding_key="cpu_temp", min_value=20, max_value=95))
        renderer = LcdRenderer(layout, pipeline)
        image = renderer.render()
        self.assertEqual(image.size, (480, 480))
        self.assertEqual(image.mode, "RGB")
        jpeg = renderer.render_jpeg()
        self.assertTrue(jpeg.startswith(b"\xff\xd8"))
        self.assertIn(b"\xff\xda", jpeg)

    def test_stale_binding_renders_without_numeric_value(self):
        pipeline = TelemetryPipeline.default()
        pipeline.ingest({"cpu_temp": 47.0}, now_ms=1000)
        pipeline.poll(now_ms=2500)
        layout = LcdLayout(name="stale")
        layout.add(TextElement(id="text", name="cpu", x=240, y=120, text="{cpu_temp}C"))
        image = LcdRenderer(layout, pipeline).render()
        self.assertEqual(image.size, (480, 480))

    def test_rotation_and_opacity_render_without_error(self):
        from core.lcd.model import ShapeElement, ShapeKind

        pipeline = TelemetryPipeline.default()
        pipeline.ingest({"cpu_temp": 60.0}, now_ms=1000)
        layout = LcdLayout(name="fx")
        layout.add(TextElement(id="t", name="rot", x=240, y=240,
                               text="{cpu_temp}C", font_size=40,
                               rotation_deg=35, opacity=0.5))
        layout.add(ShapeElement(id="s", name="box", x=100, y=100, width=80,
                                height=50, shape=ShapeKind.ROUNDED_RECTANGLE,
                                rotation_deg=-15, opacity=0.75))
        image = LcdRenderer(layout, pipeline).render()
        self.assertEqual(image.size, (480, 480))
        jpeg = LcdRenderer(layout, pipeline).render_jpeg()
        self.assertTrue(jpeg.startswith(b"\xff\xd8"))


if __name__ == "__main__":
    unittest.main()
