"""Hardware control math shared by GUI previews and daemon parity checks.

Pure functions only: the daemon remains authoritative for enforcement, these
mirror its rules so the curve editor can display exactly what will be applied.
"""

from __future__ import annotations

PUMP_DUTY_FLOOR = 40


def evaluate_curve(points: list[tuple[float, float]], temp: float) -> float:
    """Piecewise-linear temperature → duty %, matching cooling::curves semantics.

    Points may arrive unsorted; temps are clamped to the outer segments.
    """
    if not points:
        return 50.0
    pts = sorted(points)
    if len(pts) == 1:
        return float(pts[0][1])
    if temp <= pts[0][0]:
        return float(pts[0][1])
    if temp >= pts[-1][0]:
        return float(pts[-1][1])
    for (t0, d0), (t1, d1) in zip(pts, pts[1:]):
        if t0 <= temp <= t1:
            if t1 == t0:
                return float(d1)
            span = d1 - d0
            return float(d0 + span * ((temp - t0) / (t1 - t0)))
    return float(pts[-1][1])


def sanitize_points(points: list[tuple[float, float]]) -> list[tuple[int, int]]:
    """Validate a user curve into daemon-ready integer points.

    - temps sorted strictly increasing (duplicates nudged by +1 °C)
    - duties clamped to [0, 100]
    - at least two points returned
    """
    cleaned: list[tuple[int, int]] = []
    for temp, duty in sorted(points):
        t = max(0, min(120, int(round(temp))))
        d = max(0, min(100, int(round(duty))))
        if cleaned and t <= cleaned[-1][0]:
            t = cleaned[-1][0] + 1
        cleaned.append((t, d))
    if len(cleaned) < 2:
        base = cleaned[0] if cleaned else (40, 50)
        cleaned = [base, (base[0] + 20, base[1])]
    return cleaned


def apply_pump_floor(points: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Raise every duty of a pump curve to at least PUMP_DUTY_FLOOR."""
    return [(t, max(PUMP_DUTY_FLOOR, d)) for t, d in points]


def default_curve() -> list[tuple[int, int]]:
    return [(30, 30), (50, 60), (70, 100)]
