"""Template-string bindings between validated telemetry and LCD elements.

``"CPU: {cpu_temp}°C"`` / ``"{gpu_usage}%"`` are resolved here — and *only*
here — so the physical LCD can never display a raw, stale or invalid sample:
non-GOOD metrics render as ``--`` (text) or ``None`` (ring fraction ⇒
track-only neutral state), exactly matching the Overview page fallbacks.
"""

from __future__ import annotations

import re

from core.telemetry.pipeline import TelemetryPipeline
from core.telemetry.quality import MetricQuality
from core.telemetry.specs import fmt_metric_value

_PLACEHOLDER = re.compile(r"\{([a-z_][a-z0-9_]*)(?::([^{}]*))?\}")
_TEXT_FALLBACK = "--"


class BindingResolver:
    """Resolves layout templates against the validated pipeline (Qt-free)."""

    def __init__(self, pipeline: TelemetryPipeline):
        self.pipeline = pipeline

    # -- text -----------------------------------------------------------------

    def resolve(self, template: str) -> str:
        """Substitute every ``{key[:spec]}`` placeholder in *template*."""
        return _PLACEHOLDER.sub(self._substitute, template)

    def _substitute(self, match: re.Match) -> str:
        key, spec = match.group(1), match.group(2)
        validated = self.pipeline.latest().get(key)
        if validated is None or validated.quality is not MetricQuality.GOOD:
            return _TEXT_FALLBACK
        if not spec:
            return fmt_metric_value(validated.value)
        fmt = "{:" + spec + "}"
        try:
            return fmt.format(validated.value)
        except (ValueError, IndexError):
            return _TEXT_FALLBACK

    @staticmethod
    def bound_keys(template: str) -> set[str]:
        """Keys referenced by a template (for Studio binding inspectors)."""
        return {m.group(1) for m in _PLACEHOLDER.finditer(template)}

    # -- gauges ------------------------------------------------------------------

    def fraction(self, key: str, minimum: float = 0.0,
                 maximum: float = 100.0) -> float | None:
        """Normalized 0..1 ring progress, or None when unavailable.

        The renderer draws a neutral track-only arc for None — never zero
        progress masquerading as a reading.
        """
        validated = self.pipeline.latest().get(key)
        if validated is None or validated.quality is not MetricQuality.GOOD:
            return None
        value = validated.value
        span = maximum - minimum
        if span <= 0:
            return None
        return max(0.0, min(1.0, (value - minimum) / span))
