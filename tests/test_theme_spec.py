"""Theme spec template formatting + spec model round-trip tests."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "gui"))

from core.theme.preview import format_template
from core.theme.spec import ThemeSpec, Widget

METRICS = {
    "time": "22:26:51", "date": "2026-04-29",
    "cpu_temp": 63.0, "cpu_usage": 37.0, "cpu_freq": 3.77,
    "ram_used": 14.1, "ram_total": 16.0, "ram_pct": 88.1,
    "pump_rpm": 2380,
}


class TestTemplateFormatting(unittest.TestCase):
    def test_plain_literal_passthrough(self):
        self.assertEqual(format_template("CPU", METRICS), "CPU")

    def test_binding_substitution(self):
        self.assertEqual(format_template("{cpu_temp}C", METRICS), "63C")

    def test_precision_spec(self):
        self.assertEqual(format_template("{cpu_freq:.2}GHz", METRICS), "3.77GHz")
        self.assertEqual(format_template("{cpu_temp:.1}", METRICS), "63.0")

    def test_default_trims_floats(self):
        self.assertEqual(format_template("{cpu_usage}%", METRICS), "37%")
        self.assertEqual(format_template("{ram_used}G", METRICS), "14.1G")

    def test_unknown_binding_renders_placeholder(self):
        self.assertEqual(format_template("{liquid_temp}", METRICS), "--")

    def test_multiple_placeholders(self):
        self.assertEqual(
            format_template("{ram_used:.1}/{ram_total:.0} GB", METRICS),
            "14.1/16 GB")

    def test_unclosed_brace_is_literal(self):
        self.assertEqual(format_template("50 {oops", METRICS), "50 {oops")

    def test_string_bindings_pass_through(self):
        self.assertEqual(format_template("{time}", METRICS), "22:26:51")


class TestSpecModel(unittest.TestCase):
    def test_widget_roundtrip_keeps_known_fields(self):
        widget = Widget(kind="ring", cx=240, cy=240, r=90, thickness=12,
                        binding="cpu_temp", center_text="{cpu_temp:.0}")
        data = widget.to_dict()
        clone = Widget.from_dict(data)
        self.assertEqual(clone.kind, "ring")
        self.assertEqual(clone.binding, "cpu_temp")
        self.assertEqual(clone.center_size, 24.0)

    def test_unknown_fields_are_dropped(self):
        clone = Widget.from_dict({"kind": "text", "text": "A", "bogus_field": 1})
        self.assertEqual(clone.text, "A")
        self.assertFalse(hasattr(clone, "bogus_field"))

    def test_spec_save_load_roundtrip(self, tmp_path=None):
        spec = ThemeSpec(name="t", widgets=[Widget(kind="bar", x=1, y=2)])
        path = Path("/tmp/opencode/spec_roundtrip.json")
        spec.save(path)
        loaded = ThemeSpec.load(path)
        self.assertEqual(loaded.name, "t")
        self.assertEqual(loaded.widgets[0].x, 1.0)
        path.unlink()

    def test_duplicate_inserts_after(self):
        spec = ThemeSpec(widgets=[Widget(kind="rect", x=0), Widget(kind="rect", x=10)])
        index = spec.duplicate(0)
        self.assertEqual(index, 1)
        self.assertEqual(spec.widgets[1].x, 12.0)
        self.assertEqual(len(spec.widgets), 3)


if __name__ == "__main__":
    unittest.main()
