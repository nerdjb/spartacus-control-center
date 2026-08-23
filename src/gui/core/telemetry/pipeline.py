"""TelemetryPipeline: the single entry point every GUI consumer must use.

    snapshot (dict) ──► TelemetryPipeline.ingest()  ──► {key: ValidatedValue}
                              ▲
    clock tick      ───────────┘  poll() re-evaluates STALE / UNAVAILABLE

Pure Python, no Qt: deterministic and unit-testable. The Qt adapter lives in
:mod:`core.telemetry.model`.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field

from core.telemetry.quality import MetricQuality
from core.telemetry.specs import METRIC_SPECS, MetricSpec, spec_for
from core.telemetry.validator import MetricValidator, ValidatedValue

_HISTORY_LEN = 120  # ~2 min at 1 Hz — sparkline buffer


@dataclass
class SensorStats:
    """Per-metric counters for the Telemetry Diagnostics view."""

    samples_total: int = 0
    good_total: int = 0
    rejected_total: int = 0
    outlier_total: int = 0
    stale_events: int = 0
    last_reason: str = ""
    history: deque[float] = field(default_factory=lambda: deque(maxlen=_HISTORY_LEN))

    def as_dict(self) -> dict:
        return {
            "samples_total": self.samples_total,
            "good_total": self.good_total,
            "rejected_total": self.rejected_total,
            "outlier_total": self.outlier_total,
            "stale_events": self.stale_events,
            "last_reason": self.last_reason,
        }


class TelemetryPipeline:
    """Validates daemon snapshots into displayable :class:`ValidatedValue`s.

    - Metrics absent from a snapshot become UNAVAILABLE (never silently kept).
    - ``poll(now_ms)`` ages metrics out to STALE between snapshots.
    - Rejection log keeps the last *log_size* reasons for Diagnostics.
    """

    def __init__(
        self,
        specs: dict[str, MetricSpec] | None = None,
        log_size: int = 256,
        clock=None,
    ):
        # clock() -> ms; injectable for tests, defaults to a monotonic clock.
        self._clock = clock or (lambda: time.monotonic_ns() // 1_000_000)
        self.specs = dict(specs) if specs is not None else dict(METRIC_SPECS)
        self._validators: dict[str, MetricValidator] = {
            key: MetricValidator(spec) for key, spec in self.specs.items()
        }
        self._latest: dict[str, ValidatedValue] = {}
        self.stats: dict[str, SensorStats] = {
            key: SensorStats() for key in self.specs
        }
        self.rejection_log: deque[tuple[int, str, str]] = deque(
            maxlen=log_size
        )  # (now_ms, key, reason)

    # -- construction helpers --------------------------------------------------

    @classmethod
    def default(cls) -> "TelemetryPipeline":
        """Pipeline over the canonical metric table with the monotonic clock."""
        return cls()

    def now_ms(self) -> int:
        """Current pipeline clock in ms (monotonic; injectable in tests)."""
        return self._clock()

    # -- ingestion -----------------------------------------------------------

    def ingest(
        self,
        snapshot: dict[str, float],
        now_ms: int | None = None,
        source_ts_ms: int | None = None,
    ) -> dict[str, ValidatedValue]:
        """Validate one daemon snapshot; returns the full validated view.

        Keys present but unknown to the spec table are ignored (logged once by
        the caller if desired); known keys absent from the snapshot flip to
        UNAVAILABLE so the UI can never mistake silence for data.
        """
        now = now_ms if now_ms is not None else self._clock()

        results: dict[str, ValidatedValue] = {}
        seen = set()
        for raw_key, raw_value in snapshot.items():
            spec = spec_for(raw_key) if raw_key not in self.specs else self.specs[raw_key]
            if spec is None or spec.key not in self._validators:
                continue  # not a contract metric
            validator = self._validators[spec.key]
            stats = self.stats[spec.key]
            stats.samples_total += 1
            seen.add(spec.key)

            validated = validator.ingest(float(raw_value), now)
            if validated.quality is MetricQuality.GOOD:
                stats.good_total += 1
                stats.history.append(validated.value)
            elif validated.quality is MetricQuality.OUTLIER:
                stats.outlier_total += 1
                stats.rejected_total += 1
                stats.last_reason = validated.reason
                self._log_rejection(now, spec.key, validated.reason)
            else:  # INVALID
                stats.rejected_total += 1
                stats.last_reason = validated.reason
                self._log_rejection(now, spec.key, validated.reason)
            results[spec.key] = validated

        for key, validator in self._validators.items():
            if key not in seen:
                results[key] = validator.mark_unavailable(
                    now, reason="absent from daemon snapshot"
                )

        self._latest.update(results)
        return results

    def poll(self, now_ms: int | None = None) -> dict[str, ValidatedValue]:
        """Re-assess every metric against the wall clock (staleness pass)."""
        now = now_ms if now_ms is not None else self._clock()
        for key, validator in self._validators.items():
            previous = self._latest.get(key)
            assessed = validator.assess_staleness(now)
            entered_stale = (
                assessed.quality is MetricQuality.STALE
                and (previous is None or previous.quality is not MetricQuality.STALE)
            )
            if entered_stale:
                self.stats[key].stale_events += 1
                self.stats[key].last_reason = assessed.reason
                self._log_rejection(now, key, assessed.reason)
            self._latest[key] = assessed
        return dict(self._latest)

    # -- accessors -----------------------------------------------------------

    def latest(self) -> dict[str, ValidatedValue]:
        return dict(self._latest)

    def value(self, key: str) -> float | None:
        v = self._latest.get(key)
        return v.value if v and v.displayable else None

    def history(self, key: str) -> tuple[float, ...]:
        return tuple(self.stats[key].history)

    def totals(self) -> dict[str, int]:
        samples = sum(s.samples_total for s in self.stats.values())
        rejected = sum(s.rejected_total for s in self.stats.values())
        outliers = sum(s.outlier_total for s in self.stats.values())
        stale = sum(s.stale_events for s in self.stats.values())
        return {
            "samples": samples,
            "rejected": rejected,
            "outliers": outliers,
            "stale_events": stale,
        }

    def _log_rejection(self, now_ms: int, key: str, reason: str) -> None:
        self.rejection_log.append((now_ms, key, reason))
