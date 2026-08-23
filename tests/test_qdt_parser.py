"""QDT import tests: container sniffing, parsing, mapping, conversion."""

import gzip
import io
import json
import struct
import sys
import unittest
import zipfile
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "gui"))

from core.lcd.qdt.container import (
    ContainerKind,
    extract,
    screen_shape_from_filename,
    sniff_container,
)
from core.lcd.qdt.parser import QdtParser
from core.lcd.qdt.mapper import TelemetryMapper
from core.lcd.qdt.conversion import parse_color, qdt_to_layout
from core.lcd.model import ElementType, LcdLayout


def make_png(width=4, height=4, color=(255, 0, 0)) -> bytes:
    def chunk(typ: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + typ + data
            + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    row = b"\x00" + bytes(color) * width
    idat = zlib.compress(row * height)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", idat)
        + chunk(b"IEND", b"")
    )


JSON_LAYOUT = {
    "screen": {"width": 480, "height": 480},
    "widgets": [
        {"name": "cpu_text", "type": "label", "x": 240, "y": 100,
         "variable": "CPU_Temp", "format": "CPU {value:.0f} C",
         "font_size": 40, "color": "#FFFFFF"},
        {"name": "fan_ring", "type": "ring", "x": 240, "y": 260,
         "width": 360, "height": 360, "thickness": 14,
         "variable": "fanSpeed1", "start_angle": 135, "end_angle": 405},
        {"name": "logo", "type": "image", "x": 10, "y": 10,
         "width": 80, "height": 80, "image": "logo.png"},
    ],
}

INI_LAYOUT = """
[Ring1]
type = gauge
x = 240
y = 240
width = 380
height = 380
variable = GPU_Load
color = 0,240,255
color2 = 42,46,53
min = 0
max = 100

[Text1]
type = label
x = 240
y = 120
font_size = 48
variable = CPU_Temp
format = CPU {value} C
"""


def build_zip_qdt() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("layout.json", json.dumps(JSON_LAYOUT))
        zf.writestr("theme.ini", INI_LAYOUT)
        zf.writestr("logo.png", make_png())
    return buf.getvalue()


class TestContainer(unittest.TestCase):
    def test_screen_shape_from_round_filename(self):
        for name in ("480X480-1.qdt", "480x480-7.qdt"):
            self.assertEqual(screen_shape_from_filename(name), (480, 480, True))
        self.assertIsNone(screen_shape_from_filename("some_theme.qdt"))

    def test_sniff_zip(self):
        self.assertIs(sniff_container(build_zip_qdt()), ContainerKind.ZIP)

    def test_extract_zip(self):
        out = extract(build_zip_qdt())
        self.assertEqual(out.kind, ContainerKind.ZIP)
        self.assertIn("layout.json", out.descriptors)
        self.assertIn("theme.ini", out.descriptors)
        self.assertIn("logo.png", out.images)

    def test_extract_gzipped_zip(self):
        out = extract(gzip.compress(build_zip_qdt()))
        self.assertIn("layout.json", out.descriptors)
        self.assertIn("logo.png", out.images)

    def test_bare_ini(self):
        self.assertIs(sniff_container(INI_LAYOUT.encode()), ContainerKind.DESCRIPTOR_TEXT)
        out = extract(INI_LAYOUT.encode())
        self.assertIn("theme.qdt.txt", out.descriptors)

    def test_binary_carve_recovers_png(self):
        png = make_png()
        blob = b"\x00" * 97 + png + b"\xff" * 31
        out = extract(blob)
        self.assertIs(out.kind, ContainerKind.BINARY_CARVE)
        carved = list(out.images.values())
        self.assertEqual(len(carved), 1)
        self.assertEqual(carved[0], png)


class TestParser(unittest.TestCase):
    def test_parse_zip_theme(self):
        theme = QdtParser().parse(extract(build_zip_qdt()), source_name="480X480-3.qdt")
        self.assertEqual((theme.width, theme.height), (480, 480))
        self.assertTrue(theme.round_screen)
        kinds = sorted(w.kind for w in theme.widgets)
        # JSON + INI descriptors both parsed.
        self.assertEqual(kinds.count("ring"), 2)
        self.assertEqual(kinds.count("text"), 2)
        self.assertEqual(kinds.count("image"), 1)
        ring = next(w for w in theme.widgets if w.name == "fan_ring")
        self.assertEqual(ring.variable, "fanSpeed1")
        self.assertEqual(ring.thickness, 14.0)

    def test_parse_xml_descriptor(self):
        xml = (
            "<layout><ring name='r1' x='240' y='240' variable='CPU_Temp' "
            "thickness='12'/><text name='t1' x='10' y='20'>HELLO</text></layout>"
        )
        theme = QdtParser().parse(extract(xml.encode()), source_name="theme.qdt")
        kinds = {w.kind for w in theme.widgets}
        self.assertEqual(kinds, {"ring", "text"})
        t1 = next(w for w in theme.widgets if w.kind == "text")
        self.assertEqual(t1.extra.get("inner_text"), "HELLO")


class TestMapper(unittest.TestCase):
    def test_alias_mapping(self):
        m = TelemetryMapper()
        self.assertEqual(m.map_variable("CPU_Temp"), "cpu_temp")
        self.assertEqual(m.map_variable("gpu_load"), "gpu_usage")
        self.assertEqual(m.map_variable("pumpRPM"), "pump_rpm")
        self.assertEqual(m.map_variable("fanSpeed1"), "ext1_rpm")

    def test_canonical_passthrough_and_unresolved(self):
        m = TelemetryMapper()
        self.assertEqual(m.map_variable("cpu_temp"), "cpu_temp")
        self.assertIsNone(m.map_variable("mystery_sensor"))
        self.assertIn("mystery_sensor", m.unresolved)

    def test_overrides(self):
        m = TelemetryMapper(overrides={"mystery_sensor": "cpu_temp"})
        self.assertEqual(m.map_variable("mystery_sensor"), "cpu_temp")


class TestConversion(unittest.TestCase):
    def setUp(self):
        self.theme = QdtParser().parse(
            extract(build_zip_qdt()), source_name="480X480-3.qdt"
        )
        self.layout, self.notes = qdt_to_layout(self.theme)

    def test_converts_all_widgets(self):
        types = {e.element_type for e in self.layout.elements}
        self.assertIn(ElementType.RING, types)
        self.assertIn(ElementType.TEXT, types)
        self.assertIn(ElementType.IMAGE, types)

    def test_bindings_mapped_to_canonical_keys(self):
        texts = [e for e in self.layout.elements if e.element_type is ElementType.TEXT]
        rings = [e for e in self.layout.elements if e.element_type is ElementType.RING]
        # INI label 'CPU {value} C' rebound to the canonical key.
        self.assertTrue(any(t.text.startswith("CPU {cpu_temp}") for t in texts))
        # JSON ring bound via 'fanSpeed1' alias; INI gauge via 'GPU_Load'.
        self.assertTrue(any(r.binding_key == "ext1_rpm" for r in rings))
        self.assertTrue(any(r.binding_key == "gpu_usage" for r in rings))

    def test_ring_geometry_from_rect(self):
        ring = next(
            e for e in self.layout.elements
            if e.element_type is ElementType.RING and e.name == "fan_ring"
        )
        self.assertAlmostEqual(ring.radius, 180.0)
        self.assertEqual(ring.binding_key, "ext1_rpm")
        self.assertEqual(ring.active_color.lower(), "#00f0ff")

    def test_color_parsing(self):
        self.assertEqual(parse_color("0,240,255"), "#00f0ff")
        self.assertEqual(parse_color("#00F0FF"), "#00f0ff")
        self.assertEqual(parse_color("junk", "#112233"), "#112233")

    def test_notes_report_unmapped_variables(self):
        theme = QdtParser().parse(extract(build_zip_qdt()), source_name="480X480-3.qdt")
        # Inject a descriptor widget with an unknown metric.
        from core.lcd.qdt.parser import QdtWidget

        theme.widgets.append(
            QdtWidget(kind="ring", name="mystery", variable="flux_capacitance")
        )
        _, notes = qdt_to_layout(theme)
        joined = "\n".join(notes)
        self.assertIn("flux_capacitance", joined)
        self.assertIn("bind manually", joined)


class TestLayoutRoundtrip(unittest.TestCase):
    def test_save_load_preserves_elements(self):
        layout, _ = qdt_to_layout(
            QdtParser().parse(extract(build_zip_qdt()), source_name="480X480-1.qdt")
        )
        path = Path("/tmp/opencode/test_layout.slayout.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        layout.save(path)
        loaded = LcdLayout.load(path)
        self.assertEqual(len(loaded.elements), len(layout.elements))
        self.assertTrue(loaded.round_mask)
        original = {e.id: e.element_type for e in layout.elements}
        restored = {e.id: e.element_type for e in loaded.elements}
        self.assertEqual(original, restored)


if __name__ == "__main__":
    unittest.main()
