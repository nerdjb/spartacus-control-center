"""End-to-end pipeline → LCD binding tests: the 'never render bad data' gate."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "gui"))

from core.lcd.bindings import BindingResolver
from core.telemetry.pipeline import TelemetryPipeline


class TestBindings(unittest.TestCase):
    def setUp(self):
        self.p = TelemetryPipeline.default()
        self.r = BindingResolver(self.p)

    def test_template_with_good_values(self):
        self.p.ingest({"cpu_temp": 47.0, "gpu_usage": 63.0}, now_ms=1000)
        self.assertEqual(self.r.resolve("CPU: {cpu_temp}°C"), "CPU: 47°C")
        self.assertEqual(self.r.resolve("GPU {gpu_usage:.1f}%"), "GPU 63.0%")

    def test_stale_renders_placeholder_not_last_value(self):
        self.p.ingest({"cpu_temp": 47.0}, now_ms=1000)
        self.p.poll(now_ms=2500)  # goes STALE
        self.assertEqual(self.r.resolve("CPU: {cpu_temp}°C"), "CPU: --°C")

    def test_invalid_never_becomes_zero(self):
        self.p.ingest({"cpu_temp": float("nan")}, now_ms=1000)
        self.assertIn("--", self.r.resolve("{cpu_temp:.0f} °C"))
        self.assertNotIn("0", self.r.resolve("{cpu_temp:.0f} °C").replace("°C", ""))

    def test_ring_fraction_neutral_when_non_good(self):
        self.assertIsNone(self.r.fraction("cpu_temp"))

    def test_ring_fraction_clamped(self):
        self.p.ingest({"cpu_usage": 150.0}, now_ms=1000)  # INVALID (bounds)
        self.assertIsNone(self.r.fraction("cpu_usage"))
        self.p.ingest({"cpu_usage": 40.0}, now_ms=2000)
        self.assertAlmostEqual(self.r.fraction("cpu_usage"), 0.4)

    def test_bound_keys_extraction(self):
        keys = BindingResolver.bound_keys("CPU {cpu_temp} / GPU {gpu_usage}%")
        self.assertEqual(keys, {"cpu_temp", "gpu_usage"})


if __name__ == "__main__":
    unittest.main()
