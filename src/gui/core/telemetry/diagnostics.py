"""Row models for the Telemetry Diagnostics page."""

from __future__ import annotations

from dataclasses import dataclass

from core.telemetry.pipeline import TelemetryPipeline
from core.telemetry.specs import METRIC_SPECS


@dataclass(frozen=True)
class SensorRow:
    """One diagnostics table row: sensor identity + validation counters."""

    key: str
    unit: str
    raw_value: str          # as received (may be NaN/inf) or "--"
    validated_value: str    # display value or "--"
    quality: str
    latency_ms: float
    samples_total: int
    rejected_total: int
    outlier_total: int
    last_reason: str


def collect_rows(pipeline: TelemetryPipeline, raw_snapshot: dict | None = None) -> list[SensorRow]:
    """Build diagnostics rows from the pipeline's current state."""
    latest = pipeline.latest()
    rows: list[SensorRow] = []
    for key, spec in METRIC_SPECS.items():
        stats = pipeline.stats[key]
        validated = latest.get(key)
        raw = raw_snapshot.get(key) if raw_snapshot else None
        if raw is None:
            raw_text = "--"
        else:
            try:
                raw_text = f"{float(raw):g}"
            except (TypeError, ValueError):
                raw_text = str(raw)
        rows.append(SensorRow(
            key=key,
            unit=spec.unit,
            raw_value=raw_text,
            validated_value=f"{validated.value:g}" if validated and validated.displayable else "--",
            quality=validated.quality.value if validated else "UNAVAILABLE",
            latency_ms=validated.latency_ms if validated else 0.0,
            samples_total=stats.samples_total,
            rejected_total=stats.rejected_total,
            outlier_total=stats.outlier_total,
            last_reason=stats.last_reason,
        ))
    return rows
