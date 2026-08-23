"""Live Mode: stream validated telemetry frames to the LCD at a set FPS.

Rendering + JPEG encode + IPC send run in a QThreadPool worker so the GUI
thread never blocks; only one frame is ever in flight (busy flag drops ticks
rather than queueing, which keeps latency bounded at the chosen FPS).
"""

from __future__ import annotations

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, QTimer, pyqtSignal

from core.ipc.client import DaemonClient
from core.lcd.model import LcdLayout
from core.lcd.renderer import LcdRenderer
from core.telemetry.pipeline import TelemetryPipeline


class _FrameTask(QRunnable):
    def __init__(self, controller: "LiveModeController", snapshot_time_ms: int):
        super().__init__()
        self.controller = controller
        self.snapshot_time_ms = snapshot_time_ms

    def run(self) -> None:
        controller = self.controller
        try:
            renderer = LcdRenderer(controller.layout, controller.pipeline)
            jpeg = renderer.render_jpeg(controller.quality)
            accepted = controller.client.send_lcd_frame(jpeg)
            controller._report(accepted, len(jpeg))
        except Exception as exc:  # keep live mode alive through transient errors
            controller._report(False, 0, str(exc))
        finally:
            controller._busy = False


class LiveModeController(QObject):
    """Owns the frame timer; construct on the GUI thread."""

    stats_changed = pyqtSignal(int, int, str)  # sent, dropped, last_error

    def __init__(self, client: DaemonClient, layout: LcdLayout,
                 pipeline: TelemetryPipeline, parent=None):
        super().__init__(parent)
        self.client = client
        self.layout = layout
        self.pipeline = pipeline
        self.fps = 30
        self.quality = 90
        self.sent = 0
        self.dropped = 0
        self.last_error = ""
        self._busy = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._pool = QThreadPool.globalInstance()

    def start(self) -> None:
        interval = max(16, int(round(1000 / max(1, self.fps))))
        self._timer.start(interval)

    def stop(self) -> None:
        self._timer.stop()
        self.sent = 0
        self.dropped = 0
        self.last_error = ""

    @property
    def running(self) -> bool:
        return self._timer.isActive()

    def _tick(self) -> None:
        if self._busy:
            self.dropped += 1
            self.stats_changed.emit(self.sent, self.dropped, self.last_error)
            return
        if not any(v.quality.value == "GOOD" for v in self.pipeline.latest().values()):
            # Nothing validated to draw — keepalive instead of a full frame.
            ok = self.client.lcd_keepalive()
            self._report(bool(ok), 0)
            return
        self._busy = True
        self._pool.start(_FrameTask(self, self.pipeline.now_ms()))

    def _report(self, accepted: bool, size: int, error: str = "") -> None:
        if accepted:
            self.sent += 1
            self.last_error = ""
        else:
            self.dropped += 1
            self.last_error = error or "frame rejected"
        self.stats_changed.emit(self.sent, self.dropped, self.last_error)
