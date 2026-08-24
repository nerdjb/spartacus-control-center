"""Pre-made component cards for Theme Studio — drag onto the canvas,
then restyle (color / ring style / font size) from the card inspector.
"""

from __future__ import annotations

from core.theme.spec import Widget

PANEL_FILL = "#161D31"
TEXT_FILL = "#F2F4F8"
MUTED = "#8A93A6"
TRACK = "#26304A"


def _panel(x, y, w, h):
    return Widget(kind="panel", x=x, y=y, w=w, h=h, r=12, fill=PANEL_FILL)


def _ring(cx, cy, binding, accent, center, max_value=100, size=40):
    return Widget(kind="ring", cx=cx, cy=cy, r=40, thickness=9,
                  track=TRACK, fill=accent, binding=binding,
                  min=0, max=max_value, start=-90, sweep=360,
                  center_text=center, center_size=size)


def fps_card(x, y, c):
    return [
        _panel(x, y, 200, 112),
        Widget(kind="text", x=x + 14, y=y + 24, size=13, fill=c, text="FPS"),
        Widget(kind="text", x=x + 100, y=y + 60, size=40, fill=TEXT_FILL,
               align="center", text="{fps:.0}"),
        Widget(kind="text", x=x + 100, y=y + 88, size=12, fill=MUTED,
               align="center", text="{frametime:.1} ms"),
        Widget(kind="bar", x=x + 14, y=y + 98, w=172, h=6, track=TRACK,
               fill=c, binding="fps", min=0, max=240),
    ]


def _soc_card(x, y, c, label, temp_b, watts_b, ring_b, ring_center, freq_line):
    return [
        _panel(x, y, 200, 150),
        _ring(x + 45, y + 75, ring_b, c, ring_center),
        Widget(kind="text", x=x + 95, y=y + 30, size=15, fill=c, text=label),
        Widget(kind="text", x=x + 95, y=y + 58, size=24, fill=TEXT_FILL, text=temp_b),
        Widget(kind="text", x=x + 95, y=y + 86, size=16, fill=c, text=watts_b),
        Widget(kind="text", x=x + 95, y=y + 114, size=12, fill=MUTED, text=freq_line),
    ]


def cpu_card(x, y, c):
    return _soc_card(x, y, c, "CPU", "{cpu_temp:.0}°C", "{cpu_watts:.0} W",
                     "cpu_usage", "{cpu_usage:.0}%",
                     "{cpu_freq:.2}GHz · {cpu_usage:.0}%")


def gpu_card(x, y, c):
    return _soc_card(x, y, c, "GPU", "{gpu_temp:.0}°C", "{gpu_watts:.0} W",
                     "gpu_usage", "{gpu_usage:.0}%",
                     "{gpu_usage:.0}% · {frametime:.1} ms")


def ram_card(x, y, c):
    return [
        _panel(x, y, 200, 150),
        _ring(x + 45, y + 75, "ram_pct", c, "{ram_pct:.0}%"),
        Widget(kind="text", x=x + 95, y=y + 30, size=15, fill=c, text="RAM"),
        Widget(kind="text", x=x + 95, y=y + 58, size=20, fill=TEXT_FILL,
               text="{ram_used:.1}/{ram_total:.0} GB"),
        Widget(kind="text", x=x + 95, y=y + 90, size=13, fill=MUTED,
               text="Free {ram_free:.1} GB"),
    ]


def ssd_card(x, y, c):
    return [
        _panel(x, y, 200, 150),
        _ring(x + 45, y + 75, "disk_pct", c, "{disk_pct:.0}%"),
        Widget(kind="text", x=x + 95, y=y + 30, size=15, fill=c, text="SSD"),
        Widget(kind="text", x=x + 95, y=y + 58, size=20, fill=TEXT_FILL,
               text="{disk_used:.0}/{disk_total:.0} GB"),
        Widget(kind="text", x=x + 95, y=y + 90, size=13, fill=MUTED,
               text="Free {disk_free:.0} GB"),
    ]


def pump_card(x, y, c):
    return [
        _panel(x, y, 200, 150),
        _ring(x + 45, y + 75, "pump_pct", c, "{pump_pct:.0}%"),
        Widget(kind="text", x=x + 95, y=y + 30, size=15, fill=c, text="PUMP"),
        Widget(kind="text", x=x + 95, y=y + 58, size=22, fill=TEXT_FILL,
               text="{pump_rpm:.0} RPM"),
        Widget(kind="text", x=x + 95, y=y + 90, size=13, fill=MUTED,
               text="FANS {fan_rpm:.0} RPM"),
    ]


def clock_card(x, y, c):
    return [
        _panel(x, y, 200, 74),
        Widget(kind="text", x=x + 100, y=y + 42, size=30, fill=TEXT_FILL,
               align="center", text="{time}"),
        Widget(kind="text", x=x + 100, y=y + 62, size=11, fill=MUTED,
               align="center", text="{date}"),
    ]


def net_card(x, y, c):
    return [
        _panel(x, y, 200, 78),
        Widget(kind="text", x=x + 14, y=y + 32, size=13, fill="#3DDC97",
               text="↓ {net_down:.0} kB/s"),
        Widget(kind="text", x=x + 14, y=y + 58, size=13, fill="#FF7EB3",
               text="↑ {net_up:.0} kB/s"),
    ]


COMPONENTS = {
    "FPS": fps_card,
    "CPU": cpu_card,
    "GPU": gpu_card,
    "RAM": ram_card,
    "SSD": ssd_card,
    "Pump": pump_card,
    "Clock": clock_card,
    "Net": net_card,
}
