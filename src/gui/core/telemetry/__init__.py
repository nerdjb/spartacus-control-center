"""Validated telemetry pipeline.

Hardware Sensor -> Daemon -> TelemetryValidator -> TelemetryModel
    -> (Overview UI / Graphs / LCD Editor Preview / Physical LCD)

Nothing in the GUI may render a raw daemon sample; everything consumes
:class:`ValidatedValue` produced here. This package is stdlib-only so it can be
unit-tested headlessly and reused by tools.
"""

from core.telemetry.quality import MetricQuality, QUALITY_COLORS
from core.telemetry.specs import MetricSpec, METRIC_SPECS, spec_for
from core.telemetry.filters import SlidingMedianFilter
from core.telemetry.validator import MetricValidator, ValidatedValue
from core.telemetry.pipeline import TelemetryPipeline

__all__ = [
    "MetricQuality",
    "QUALITY_COLORS",
    "MetricSpec",
    "METRIC_SPECS",
    "spec_for",
    "SlidingMedianFilter",
    "MetricValidator",
    "ValidatedValue",
    "TelemetryPipeline",
]
