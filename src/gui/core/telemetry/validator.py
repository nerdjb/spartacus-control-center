"""Per-metric validator: raw daemon sample → ValidatedValue."""

from __future__ import annotations

import math
from dataclasses import dataclass

from core.telemetry.filters import SlidingMedianFilter
from core.telemetry.quality import MetricQuality
from core.telemetry.specs import MetricSpec


@dataclass(frozen=True)
class ValidatedValue:
    """Immutable, display-ready result of the validation pipeline.

    ``value`` is None for every quality except GOOD. Consumers must never fall
    back to a previous good value on their own — the pipeline decides.
    """

    key: str
    value: float | None
    quality: MetricQuality
    timestamp_ms: int          # host clock of last accepted (GOOD) sample; 0 if none
    age_ms: int                # now - timestamp_ms (now for first sample)
    latency_ms: float          # inter-arrival time of the last two GOOD samples
    reason: str = ""

    @property
    def displayable(self) -> bool:
        return self.quality is MetricQuality.GOOD and self.value is not None


class MetricValidator:
    """Validates one metric's sample stream against its :class:`MetricSpec`.

    Order of checks (first match wins):
      1. NaN / Infinity                     → INVALID "non-finite"
      2. physical bounds                    → INVALID "out of range"
      3. sliding-median spike guard         → OUTLIER
      4. otherwise                          → GOOD
    Staleness is time-based and evaluated lazily by :meth:`assess_staleness`,
    because it depends on *now*, not on an arriving sample.
    """

    __slots__ = ("spec", "_filter", "_last_good_ms", "_last_value", "_latency_ms")

    def __init__(self, spec: MetricSpec):
        self.spec = spec
        self._filter = SlidingMedianFilter(spec.median_window, spec.max_jump)
        self._last_good_ms: int | None = None
        self._last_value: float | None = None
        self._latency_ms: float = 0.0

    # -- ingest ------------------------------------------------------------

    def ingest(self, value: float, now_ms: int) -> ValidatedValue:
        """Validate one raw sample stamped with the host monotonic-ish clock."""
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return self._invalid(now_ms, "non-numeric")

        fval = float(value)
        if math.isnan(fval) or math.isinf(fval):
            return self._invalid(now_ms, "non-finite")

        lo, hi = self.spec.minimum, self.spec.maximum
        if fval < lo or fval > hi:
            return self._invalid(
                now_ms, f"out of range ({fval:g} not in [{lo:g}, {hi:g}])"
            )

        if self._filter.reject(fval):
            return ValidatedValue(
                key=self.spec.key, value=None, quality=MetricQuality.OUTLIER,
                timestamp_ms=self._last_good_ms or 0, age_ms=0,
                latency_ms=self._latency_ms,
                reason=f"spike {self._last_value if self._last_value is not None else '?':g}"
                       f"→{fval:g} rejected",
            )

        if self._last_good_ms is not None:
            self._latency_ms = max(0.0, float(now_ms - self._last_good_ms))
        self._last_good_ms = now_ms
        self._last_value = fval

        return ValidatedValue(
            key=self.spec.key, value=fval, quality=MetricQuality.GOOD,
            timestamp_ms=now_ms, age_ms=0, latency_ms=self._latency_ms,
        )

    def mark_unavailable(self, now_ms: int, reason: str = "sensor missing") -> ValidatedValue:
        return ValidatedValue(
            key=self.spec.key, value=None, quality=MetricQuality.UNAVAILABLE,
            timestamp_ms=self._last_good_ms or 0, age_ms=0,
            latency_ms=self._latency_ms, reason=reason,
        )

    # -- staleness ----------------------------------------------------------

    def assess_staleness(self, now_ms: int) -> ValidatedValue:
        """Re-evaluate the metric against the clock without a new sample."""
        if self._last_good_ms is None:
            return ValidatedValue(
                key=self.spec.key, value=None, quality=MetricQuality.UNAVAILABLE,
                timestamp_ms=0, age_ms=0, latency_ms=0.0, reason="no samples",
            )
        age = now_ms - self._last_good_ms
        if age > self.spec.stale_after_ms:
            return ValidatedValue(
                key=self.spec.key, value=None, quality=MetricQuality.STALE,
                timestamp_ms=self._last_good_ms, age_ms=age,
                latency_ms=self._latency_ms,
                reason=f"no update for {age} ms (> {self.spec.stale_after_ms} ms)",
            )
        return ValidatedValue(
            key=self.spec.key, value=self._last_value, quality=MetricQuality.GOOD,
            timestamp_ms=self._last_good_ms, age_ms=age,
            latency_ms=self._latency_ms,
        )

    # -- helpers -------------------------------------------------------------

    def _invalid(self, now_ms: int, reason: str) -> ValidatedValue:
        return ValidatedValue(
            key=self.spec.key, value=None, quality=MetricQuality.INVALID,
            timestamp_ms=self._last_good_ms or 0, age_ms=0,
            latency_ms=self._latency_ms, reason=reason,
        )
