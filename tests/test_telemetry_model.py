"""Qt adapter tests for TelemetryModel (signals + display text)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "gui"))

from PyQt6.QtCore import QCoreApplication

from core.telemetry.model import TelemetryModel
from core.telemetry.pipeline import TelemetryPipeline
from core.telemetry.quality import MetricQuality

_app = None


def setUpModule():
    global _app
    _app = QCoreApplication.instance() or QCoreApplication([])


class TestTelemetryModel(unittest.TestCase):
    def setUp(self):
        self.model = TelemetryModel(pipeline=TelemetryPipeline.default())

    def test_text_placeholder_when_no_data(self):
        self.assertEqual(self.model.text("cpu_temp"), "--")
        self.assertIs(self.model.quality("cpu_temp"), MetricQuality.UNAVAILABLE)

    def test_good_value_formats(self):
        self.model.ingest_snapshot({"cpu_temp": 47.4}, now_ms=1000)
        self.assertEqual(self.model.text("cpu_temp", "{:.0f}"), "47")
        badge = self.model.badge_text("cpu_temp", "°C")
        self.assertIn("47.4°C", badge)
        self.assertIn("GOOD", badge)

    def test_stale_shows_placeholder_and_quality_signal(self):
        qualities = []
        self.model.quality_changed.connect(
            lambda key, q: qualities.append((key, q))
        )
        self.model.ingest_snapshot({"cpu_temp": 47.0}, now_ms=1000)
        self.model.tick(now_ms=2500)
        self.assertEqual(self.model.text("cpu_temp"), "--")
        self.assertEqual(qualities[-1], ("cpu_temp", MetricQuality.STALE))

    def test_metric_changed_emitted_on_new_values(self):
        changes = []
        self.model.metric_changed.connect(changes.append)
        self.model.ingest_snapshot({"cpu_temp": 40.0}, now_ms=1000)
        self.model.ingest_snapshot({"cpu_temp": 41.5}, now_ms=2000)
        self.assertGreaterEqual(changes.count("cpu_temp"), 2)

    def test_pipeline_live_flag_transitions(self):
        states = []
        self.model.pipeline_state_changed.connect(states.append)
        self.model.tick(now_ms=1000)
        self.assertFalse(self.model.is_live())
        self.model.ingest_snapshot({"cpu_temp": 50.0}, now_ms=1100)
        self.assertTrue(self.model.is_live())
        self.model.tick(now_ms=5000)   # everything stale
        self.assertFalse(self.model.is_live())
        self.assertIn(True, states)
        self.assertIn(False, states)


if __name__ == "__main__":
    unittest.main()
