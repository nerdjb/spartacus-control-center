"""Signal-conditioning filters.

The outlier guard is a sliding **median**: a lone spike (45 → 150 → 46 °C) is
discarded because the median ignores it, while a legitimate steep thermal ramp
keeps passing because every new sample drags the median with it. This satisfies
the "no dampening of real transients" requirement that a plain EMA violates.
"""

from __future__ import annotations

from collections import deque
from statistics import median


class SlidingMedianFilter:
    """Median of the last *window* accepted samples.

    ``reject(value)`` returns True when the value deviates from the running
    median by more than ``max_jump`` while the median itself is stable. Once
    enough consecutive outlying samples arrive (>= half the window) the filter
    re-centers on them and they start passing — that is what lets real fast
    ramps through instead of latching on an old level forever.
    """

    __slots__ = ("window", "max_jump", "_samples", "_consecutive_rejects")

    def __init__(self, window: int = 5, max_jump: float | None = None):
        if window < 1:
            raise ValueError("window must be >= 1")
        self.window = window
        self.max_jump = max_jump
        self._samples: deque[float] = deque(maxlen=window)
        self._consecutive_rejects = 0

    def reset(self) -> None:
        self._samples.clear()
        self._consecutive_rejects = 0

    @property
    def filled(self) -> bool:
        return len(self._samples) >= min(2, self.window)

    def current_median(self) -> float | None:
        return median(self._samples) if self._samples else None

    def reject(self, value: float) -> bool:
        """True ⇒ treat *value* as an outlier relative to recent history."""
        if self.max_jump is None or len(self._samples) < 2:
            self.accept(value)
            return False

        med = median(self._samples)

        # Median travelling fast across the window ⇒ genuine regime change
        # (load burst), not a glitch; accept and let the median shift.
        if abs(med - self._samples[0]) > self.max_jump:
            self.accept(value)
            return False

        if abs(value - med) > self.max_jump:
            self._consecutive_rejects += 1
            # Sustained new level: stop rejecting, adopt it as the baseline.
            if self._consecutive_rejects >= max(2, self.window // 2):
                self.reset()
                self.accept(value)
                return False
            return True

        self.accept(value)
        return False

    def accept(self, value: float) -> None:
        """Feed an already-validated value into the history window."""
        self._samples.append(value)
        self._consecutive_rejects = 0
