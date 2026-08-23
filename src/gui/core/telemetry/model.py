"""Qt adapter over the telemetry pipeline.

TelemetryModel is the ONLY object UI pages and the LCD renderer subscribe to.
It converts :class:`ValidatedValue`s into display text (``--`` for non-GOOD),
keeps sparkline history, and emits fine-grained signals so pages can animate
state transitions (fade/pulse) without polling.
"""

from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal

from core.telemetry.pipeline import TelemetryPipeline
from core.telemetry.quality import MetricQuality, QUALITY_COLORS
from core.telemetry.specs import fmt_metric_value
from core.telemetry.validator import ValidatedValue

_PLACEHOLDER = "--"


class TelemetryModel(QObject):
    """Observable validated-telemetry model."""

    metric_changed = pyqtSignal(str)                 # key
    quality_changed = pyqtSignal(str, object)        # key, MetricQuality
    pipeline_state_changed = pyqtSignal(bool)        # True ⇒ Pipeline LIVE
    snapshot_applied = pyqtSignal()                  # after each ingest/poll batch

    def __init__(self, pipeline: TelemetryPipeline | None = None, parent=None):
        super().__init__(parent)
        self.pipeline = pipeline or TelemetryPipeline.default()
        self._values: dict[str, ValidatedValue] = {}
        self._pipeline_live: bool = False
        self._now_ms: int | None = None

    # -- ingestion -----------------------------------------------------------

    def ingest_snapshot(self, status: dict, now_ms: int | None = None) -> None:
        """Feed one daemon status/telemetry dict through the pipeline."""
        self._now_ms = self._resolve_now(now_ms)
        self._apply(self.pipeline.ingest(status, now_ms=self._now_ms))

    def tick(self, now_ms: int | None = None) -> None:
        """Staleness pass; call from a QTimer between daemon snapshots."""
        self._now_ms = self._resolve_now(now_ms)
        self._apply(self.pipeline.poll(now_ms=self._now_ms))

    def _resolve_now(self, now_ms: int | None) -> int:
        return now_ms if now_ms is not None else self.pipeline.now_ms()

    def _apply(self, values: dict[str, ValidatedValue]) -> None:
        for key, new in values.items():
            old = self._values.get(key)
            self._values[key] = new
            if old is None or old.value != new.value:
                self.metric_changed.emit(key)
            if old is None or old.quality is not new.quality:
                self.quality_changed.emit(key, new.quality)

        live = self.is_live()
        if live != self._pipeline_live:
            self._pipeline_live = live
            self.pipeline_state_changed.emit(live)
        self.snapshot_applied.emit()

    # -- accessors -------------------------------------------------------------

    def value(self, key: str) -> float | None:
        v = self._values.get(key)
        return v.value if v else None

    def quality(self, key: str) -> MetricQuality:
        v = self._values.get(key)
        return v.quality if v else MetricQuality.UNAVAILABLE

    def latency_ms(self, key: str) -> float:
        v = self._values.get(key)
        return v.latency_ms if v else 0.0

    def quality_color(self, key: str) -> str:
        return QUALITY_COLORS[self.quality(key)]

    def text(self, key: str, fmt: str = "{:.0f}") -> str:
        """Formatted display text; ``--`` unless the sample is GOOD."""
        v = self._values.get(key)
        if v is None or not v.displayable:
            return _PLACEHOLDER
        return fmt.format(v.value)

    def badge_text(self, key: str, unit: str = "") -> str:
        """e.g. ``47°C ● GOOD (83 ms)`` or ``-- ● STALE (1.2 s)``."""
        v = self._values.get(key)
        if v is None:
            return f"{_PLACEHOLDER} ● UNAVAILABLE"
        if v.displayable and v.value is not None:
            body = f"{fmt_metric_value(v.value)}{unit}"
        else:
            body = _PLACEHOLDER
        detail = (
            f"{v.latency_ms:.0f} ms" if v.displayable
            else f"{v.age_ms / 1000:.1f} s" if v.age_ms else (v.reason or "no data")
        )
        return f"{body} ● {v.quality.value} ({detail})"

    def history(self, key: str) -> tuple[float, ...]:
        return self.pipeline.history(key)

    def is_live(self) -> bool:
        """Pipeline LIVE ⇔ at least one GOOD metric within 2 s of model time."""
        if self._now_ms is None:
            return False
        for v in self._values.values():
            if (
                v.quality is MetricQuality.GOOD
                and self._now_ms - v.timestamp_ms <= 2000
            ):
                return True
        return False
