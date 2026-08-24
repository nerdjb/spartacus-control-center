"""Metric specification table: physical bounds and validation windows.

One :class:`MetricSpec` per canonical metric key. Keys are the contract between
the daemon snapshot (`GetStatus` / `GetTelemetry`), this pipeline, LCD template
strings (``CPU: {cpu_temp}°C``).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MetricSpec:
    key: str
    unit: str
    minimum: float
    maximum: float
    stale_after_ms: int = 1000
    # Largest plausible single-step change; larger jumps are outliers *unless*
    # the median itself moves (sustained ramps stay legitimate).
    max_jump: float | None = None
    median_window: int = 5
    aliases: tuple[str, ...] = field(default=())


def _spec(
    key: str,
    unit: str,
    lo: float,
    hi: float,
    stale_ms: int = 1000,
    jump: float | None = None,
    window: int = 5,
    aliases: tuple[str, ...] = (),
) -> MetricSpec:
    return MetricSpec(
        key=key, unit=unit, minimum=lo, maximum=hi,
        stale_after_ms=stale_ms, max_jump=jump, median_window=window,
        aliases=aliases,
    )


#: Canonical metrics. Bounds follow sane desktop-hardware physics.
METRIC_SPECS: dict[str, MetricSpec] = {s.key: s for s in (
    # Temperatures — k10temp/coretemp/amdgpu never read < -20 or > 120 °C.
    _spec("cpu_temp", "°C", -20.0, 120.0, jump=25.0),
    _spec("gpu_temp", "°C", -20.0, 120.0, jump=25.0),
    _spec("liquid_temp", "°C", 0.0, 100.0, jump=15.0),
    # Usage percentages.
    _spec("cpu_usage", "%", 0.0, 100.0, jump=85.0),
    _spec("gpu_usage", "%", 0.0, 100.0, jump=85.0),
    _spec("ram_usage", "%", 0.0, 100.0, jump=None),
    _spec("disk_usage", "%", 0.0, 100.0, jump=None),
    # Clocks.
    _spec("cpu_freq_ghz", "GHz", 0.2, 6.5, jump=3.0),
    _spec("gpu_freq_mhz", "MHz", 0.0, 3500.0, jump=2500.0),
    _spec("gpu_vram_gb", "GB", 0.0, 64.0, jump=None),
    # Memory / disk capacity.
    _spec("ram_used_gb", "GB", 0.0, 1024.0, jump=None),
    _spec("ram_total_gb", "GB", 0.5, 4096.0, jump=None),
    _spec("disk_used_gb", "GB", 0.0, 65536.0, jump=None),
    _spec("disk_total_gb", "GB", 1.0, 131072.0, jump=None),
    # Network rates (kB/s). Ceiling ≈ 20 Gbit/s; rollover/reset shows up as an
    # absurd spike and is rejected here even though the daemon saturates too.
    _spec("net_down_kbps", "kB/s", 0.0, 2_500_000.0, stale_ms=1500, jump=None),
    _spec("net_up_kbps", "kB/s", 0.0, 2_500_000.0, stale_ms=1500, jump=None),
    # Tachometry — negative RPM is impossible; 0 means "no fan" on EXT headers
    # and stays GOOD (protocol §7 troubleshooting), the UI labels it "—".
    _spec("pump_rpm", "RPM", 0.0, 6000.0, stale_ms=1500, jump=2500.0),
    _spec("fps", "FPS", 1.0, 1200.0, stale_ms=3000, jump=None),
    _spec("cpu_watts", "W", 1.0, 500.0, stale_ms=4000, jump=None),
    _spec("gpu_watts", "W", 1.0, 1000.0, stale_ms=4000, jump=None),
    _spec("frametime_ms", "ms", 1.0, 200.0, stale_ms=3000, jump=None),
    _spec("aio_rpm", "RPM", 0.0, 4000.0, stale_ms=1500, jump=2000.0),
    _spec("ext1_rpm", "RPM", 0.0, 4000.0, stale_ms=1500, jump=2000.0),
    _spec("ext2_rpm", "RPM", 0.0, 4000.0, stale_ms=1500, jump=2000.0),
)}

_ALIASES: dict[str, str] = {}
for _spec_obj in METRIC_SPECS.values():
    _ALIASES[_spec_obj.key.lower()] = _spec_obj.key
    for _alias in _spec_obj.aliases:
        _ALIASES[_alias.lower()] = _spec_obj.key


def spec_for(key: str) -> MetricSpec | None:
    """Look up a spec by canonical key or alias (case-insensitive)."""
    return METRIC_SPECS.get(_ALIASES.get(key.lower(), key))


def fmt_metric_value(value: float) -> str:
    """Compact numeric rendering: 47.0 → '47', 47.4 → '47.4'."""
    if abs(value - round(value)) < 1e-9:
        return f"{value:.0f}"
    if abs(value) >= 100:
        return f"{value:.0f}"
    return f"{value:.1f}"
