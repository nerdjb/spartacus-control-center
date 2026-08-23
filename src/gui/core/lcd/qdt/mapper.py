"""TelemetryMapper: QDT variable names -> canonical SPARTACUS metric keys.

Vendor descriptors name metrics inconsistently (``CPU_Temp``, ``cpuTemp``,
``fanSpeed1``, ``GPU_Load``…). Mapping is alias-table first, regex fallback
second; anything unmapped is reported so LCD Studio can prompt the user.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from core.telemetry.specs import METRIC_SPECS

# Explicit aliases harvested from common QScreen/LCD-Wiki descriptors.
_ALIAS_TABLE: dict[str, str] = {
    "cputemp": "cpu_temp", "cputemperature": "cpu_temp", "temp_cpu": "cpu_temp",
    "cpu": "cpu_temp", "coretemp": "cpu_temp", "k10temp": "cpu_temp",
    "cput": "cpu_temp", "temperature1": "cpu_temp", "temp1": "cpu_temp",
    "gputemp": "gpu_temp", "gputemperature": "gpu_temp", "temp_gpu": "gpu_temp",
    "gpu": "gpu_temp", "temperature2": "gpu_temp", "temp2": "gpu_temp",
    "liquidtemp": "liquid_temp", "coolanttemp": "liquid_temp", "water_temp": "liquid_temp",
    "cpuusage": "cpu_usage", "cpuload": "cpu_usage", "load_cpu": "cpu_usage",
    "cpuutilization": "cpu_usage", "gpuload": "gpu_usage", "gpuusage": "gpu_usage",
    "load_gpu": "gpu_usage", "vram": "gpu_vram_gb", "vramusage": "gpu_vram_gb",
    "gpuclock": "gpu_freq_mhz", "gpufrequency": "gpu_freq_mhz", "coreclock": "gpu_freq_mhz",
    "cpuclock": "cpu_freq_ghz", "cpufrequency": "cpu_freq_ghz", "cpufreq": "cpu_freq_ghz",
    "ramused": "ram_used_gb", "memused": "ram_used_gb", "memoryused": "ram_used_gb",
    "ramtotal": "ram_total_gb", "memtotal": "ram_total_gb",
    "pumprpm": "pump_rpm", "pumpspeed": "pump_rpm", "pump": "pump_rpm",
    "fanrpm": "aio_rpm", "fanspeed": "aio_rpm", "fan1speed": "ext1_rpm",
    "fan2speed": "ext2_rpm", "fan1rpm": "ext1_rpm", "fan2rpm": "ext2_rpm",
    "fana": "ext1_rpm", "fanb": "ext2_rpm",
    "netdown": "net_down_kbps", "download": "net_down_kbps",
    "netup": "net_up_kbps", "upload": "net_up_kbps",
}

# Regex fallbacks, first match wins. Order matters (most specific first).
_REGEX_RULES: tuple[tuple[str, str], ...] = (
    (r"pump", "pump_rpm"),
    (r"fan.*(1|a|ext1)", "ext1_rpm"),
    (r"fan.*(2|b|ext2)", "ext2_rpm"),
    (r"fan|rpm", "aio_rpm"),
    (r"cpu.*(freq|clock|ghz)", "cpu_freq_ghz"),
    (r"gpu.*(freq|clock|mhz)", "gpu_freq_mhz"),
    (r"(vram|memory).*(used|usage)|mem.*used", "ram_used_gb"),
    (r"vram", "gpu_vram_gb"),
    (r"cpu.*(temp|°?c$)", "cpu_temp"),
    (r"gpu.*(temp|°?c$)", "gpu_temp"),
    (r"(water|liquid|coolant).*temp", "liquid_temp"),
    (r"cpu.*(load|usage|util)", "cpu_usage"),
    (r"gpu.*(load|usage|util)", "gpu_usage"),
    (r"(ram|mem).*(total)", "ram_total_gb"),
    (r"net.*(up|send)|upload", "net_up_kbps"),
    (r"net.*(down|recv)|download", "net_down_kbps"),
)


@dataclass
class TelemetryMapper:
    """Stateless mapper with an optional user-supplied override table."""

    overrides: dict[str, str] = field(default_factory=dict)
    unresolved: set[str] = field(default_factory=set)

    def map_variable(self, name: str) -> str | None:
        """Return the canonical metric key for a QDT variable, or None.

        Canonical keys pass through unchanged; unknown names are remembered in
        ``unresolved`` so the UI can offer one-click manual binding.
        """
        if not name:
            return None
        if name in self.overrides:
            key = self.overrides[name]
        else:
            norm = re.sub(r"[^a-z0-9]+", "", name.lower())
            if norm in METRIC_SPECS or name in METRIC_SPECS:
                key = name if name in METRIC_SPECS else norm
            elif norm in _ALIAS_TABLE:
                key = _ALIAS_TABLE[norm]
            else:
                key = self._regex_match(norm)
        if key and (key in METRIC_SPECS):
            return key
        if name:
            self.unresolved.add(name)
        return None

    def map_theme(self, variable_names) -> dict[str, str]:
        """Map many names at once; returns {qdt_name: canonical_key}."""
        out: dict[str, str] = {}
        for name in variable_names:
            key = self.map_variable(name)
            if key:
                out[name] = key
        return out

    @staticmethod
    def _regex_match(norm: str) -> str | None:
        for pattern, key in _REGEX_RULES:
            if re.search(pattern, norm):
                return key
        return None
