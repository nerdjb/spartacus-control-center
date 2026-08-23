"""Data-quality states for every telemetry metric."""

from __future__ import annotations

from enum import Enum


class MetricQuality(str, Enum):
    """Lifecycle state of one metric sample as rendered anywhere in the GUI.

    GOOD        fresh sample, within physical boundaries
    STALE       no accepted update within the metric's staleness window (>1000 ms)
    INVALID     NaN/Infinity, out-of-bounds, negative RPM, sensor disconnect
    OUTLIER     rejected transient spike (sliding-median guard)
    UNAVAILABLE sensor missing from the daemon snapshot / hardware disconnected
    """

    GOOD = "GOOD"
    STALE = "STALE"
    INVALID = "INVALID"
    OUTLIER = "OUTLIER"
    UNAVAILABLE = "UNAVAILABLE"


QUALITY_COLORS: dict[MetricQuality, str] = {
    MetricQuality.GOOD: "#00FF66",
    MetricQuality.STALE: "#FFB454",
    MetricQuality.INVALID: "#FF4D5E",
    MetricQuality.OUTLIER: "#B26BFF",
    MetricQuality.UNAVAILABLE: "#5C6470",
}

# Qualities whose numeric value may be displayed/rendered. Only GOOD qualifies:
# the spec forbids displaying stale or unvalidated data as live.
DISPLAYABLE = frozenset({MetricQuality.GOOD})
