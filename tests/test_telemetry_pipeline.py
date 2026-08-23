"""Unit tests for the validated telemetry pipeline."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "gui"))

from core.telemetry.pipeline import TelemetryPipeline
from core.telemetry.quality import MetricQuality
from core.telemetry.specs import METRIC_SPECS


def make_pipeline() -> TelemetryPipeline:
    return TelemetryPipeline.default()


class TestValidation(unittest.TestCase):
    def setUp(self):
        self.p = make_pipeline()

    def validate(self, snapshot, now):
        return self.p.ingest(snapshot, now_ms=now)[snapshot_key(snapshot)]

    def test_good_sample_passes(self):
        vals = self.p.ingest({"cpu_temp": 47.0, "pump_rpm": 2450}, now_ms=1000)
        v = vals["cpu_temp"]
        self.assertIs(v.quality, MetricQuality.GOOD)
        self.assertEqual(v.value, 47.0)
        self.assertTrue(v.displayable)

    def test_nan_and_inf_invalid(self):
        v = self.p.ingest({"cpu_temp": float("nan")}, now_ms=100)["cpu_temp"]
        self.assertIs(v.quality, MetricQuality.INVALID)
        self.assertIn("non-finite", v.reason)
        v = self.p.ingest({"cpu_temp": float("inf")}, now_ms=200)["cpu_temp"]
        self.assertIs(v.quality, MetricQuality.INVALID)

    def test_out_of_range_invalid(self):
        v = self.p.ingest({"cpu_temp": 200.0}, now_ms=100)["cpu_temp"]
        self.assertIs(v.quality, MetricQuality.INVALID)
        self.assertIn("out of range", v.reason)

    def test_negative_rpm_invalid(self):
        v = self.p.ingest({"pump_rpm": -50}, now_ms=100)["pump_rpm"]
        self.assertIs(v.quality, MetricQuality.INVALID)

    def test_zero_rpm_is_valid_no_fan(self):
        # EXT headers read 0 when no fan is connected — GOOD, UI shows "—".
        v = self.p.ingest({"ext2_rpm": 0}, now_ms=100)["ext2_rpm"]
        self.assertIs(v.quality, MetricQuality.GOOD)

    def test_absent_metric_unavailable(self):
        vals = self.p.ingest({"cpu_temp": 47.0}, now_ms=100)
        gpu = vals["gpu_temp"]
        self.assertIs(gpu.quality, MetricQuality.UNAVAILABLE)
        self.assertIn("absent", gpu.reason)

    def test_network_rate_ceiling(self):
        v = self.p.ingest({"net_down_kbps": 9_999_999.0}, now_ms=100)["net_down_kbps"]
        self.assertIs(v.quality, MetricQuality.INVALID)


class TestOutlierFilter(unittest.TestCase):
    def setUp(self):
        self.p = make_pipeline()

    def feed_cpu(self, values, start_ms=1000, step=1000):
        out = []
        for i, val in enumerate(values):
            out.append(
                self.p.ingest({"cpu_temp": val}, now_ms=start_ms + i * step)["cpu_temp"]
            )
        return out

    def test_single_spike_rejected_as_outlier(self):
        # 95 °C is physically in-bounds (< 120) but implausible next to 46 —
        # exactly the case the median filter exists for.
        seq = self.feed_cpu([45.0, 45.5, 46.0, 95.0, 46.0])
        self.assertTrue(all(v.quality is MetricQuality.GOOD for v in seq[:3]))
        self.assertIs(seq[3].quality, MetricQuality.OUTLIER)
        self.assertIsNone(seq[3].value)
        # The following legitimate sample still passes.
        self.assertIs(seq[4].quality, MetricQuality.GOOD)
        self.assertEqual(seq[4].value, 46.0)

    def test_out_of_bounds_spike_is_invalid_not_outlier(self):
        # Bounds take precedence: an impossible temperature never reaches the
        # outlier filter at all.
        seq = self.feed_cpu([45.0, 45.5, 150.0])
        self.assertIs(seq[2].quality, MetricQuality.INVALID)

    def test_outlier_never_enters_history(self):
        self.feed_cpu([45.0, 45.5, 95.0])
        hist = self.p.history("cpu_temp")
        self.assertNotIn(95.0, hist)
        self.assertIn(45.5, hist)

    def test_steep_legitimate_ramp_not_dampened(self):
        # 45 -> 90 over nine seconds at 5 °C/s: a genuine fast ramp must pass.
        ramp = [45.0 + 5.0 * i for i in range(10)]
        seq = self.feed_cpu(ramp)
        self.assertTrue(
            all(v.quality is MetricQuality.GOOD for v in seq),
            msg=[v.quality.value for v in seq],
        )
        self.assertEqual(seq[-1].value, 90.0)

    def test_sustained_new_level_adopted(self):
        seq = self.feed_cpu([45.0, 45.5, 46.0, 95.0, 95.0, 95.5])
        self.assertIs(seq[3].quality, MetricQuality.OUTLIER)
        # After repeated confirmations the filter re-centers: ~95 is the truth.
        self.assertIs(seq[5].quality, MetricQuality.GOOD)
        self.assertEqual(seq[5].value, 95.5)


class TestStaleness(unittest.TestCase):
    def setUp(self):
        self.p = make_pipeline()

    def test_stale_after_window(self):
        self.p.ingest({"cpu_temp": 47.0}, now_ms=1000)
        vals = self.p.poll(now_ms=2500)  # > 1000 ms stale window
        v = vals["cpu_temp"]
        self.assertIs(v.quality, MetricQuality.STALE)
        self.assertIsNone(v.value)
        self.assertEqual(v.age_ms, 1500)

    def test_fresh_poll_stays_good(self):
        self.p.ingest({"cpu_temp": 47.0}, now_ms=1000)
        vals = self.p.poll(now_ms=1600)
        self.assertIs(vals["cpu_temp"].quality, MetricQuality.GOOD)
        self.assertEqual(vals["cpu_temp"].value, 47.0)

    def test_stale_event_counted_once(self):
        self.p.ingest({"cpu_temp": 47.0}, now_ms=1000)
        self.p.poll(now_ms=2500)
        self.p.poll(now_ms=3000)
        self.assertEqual(self.p.stats["cpu_temp"].stale_events, 1)

    def test_recovery_from_stale(self):
        self.p.ingest({"cpu_temp": 47.0}, now_ms=1000)
        self.p.poll(now_ms=3000)
        v = self.p.ingest({"cpu_temp": 52.0}, now_ms=3200)["cpu_temp"]
        self.assertIs(v.quality, MetricQuality.GOOD)


class TestStatsAndLog(unittest.TestCase):
    def setUp(self):
        self.p = make_pipeline()

    def test_counters_and_log(self):
        self.p.ingest({"cpu_temp": 47.0, "gpu_temp": 55.0}, now_ms=1000)
        self.p.ingest({"cpu_temp": float("nan"), "gpu_temp": 56.0}, now_ms=2000)
        self.p.ingest({"cpu_temp": 48.0, "gpu_temp": 999.0}, now_ms=3000)
        totals = self.p.totals()
        self.assertEqual(totals["samples"], 6)
        self.assertGreaterEqual(totals["rejected"], 2)
        log_entries = list(self.p.rejection_log)
        reasons = {entry[1]: entry[2] for entry in log_entries}
        self.assertIn("non-finite", reasons.get("cpu_temp", ""))
        self.assertIn("out of range", reasons.get("gpu_temp", ""))

    def test_latency_measured_between_good_samples(self):
        self.p.ingest({"cpu_temp": 47.0}, now_ms=1000)
        v = self.p.ingest({"cpu_temp": 48.0}, now_ms=1083)["cpu_temp"]
        self.assertAlmostEqual(v.latency_ms, 83.0)


def snapshot_key(snapshot):
    return next(iter(snapshot))


if __name__ == "__main__":
    unittest.main()
