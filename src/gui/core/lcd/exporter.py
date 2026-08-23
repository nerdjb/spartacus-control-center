"""LCD frame validation and daemon hand-off."""

from __future__ import annotations

from dataclasses import dataclass

from core.ipc.client import DaemonClient
from core.lcd.renderer import LcdRenderer


@dataclass(frozen=True)
class FrameResult:
    accepted: bool
    jpeg_bytes: int
    checksum16: int
    error: str = ""


class LcdExporter:
    """Render and send exactly one validated frame through daemon IPC."""

    def __init__(self, client: DaemonClient):
        self.client = client

    def render_and_send(self, renderer: LcdRenderer, quality: int = 90) -> FrameResult:
        try:
            jpeg = renderer.render_jpeg(quality)
            if not jpeg.startswith(b"\xff\xd8") or b"\xff\xda" not in jpeg:
                raise ValueError("renderer did not produce a baseline JPEG")
            checksum = sum(jpeg) & 0xFFFF
            accepted = self.client.send_lcd_frame(jpeg)
            return FrameResult(accepted, len(jpeg), checksum,
                               "" if accepted else "daemon rejected frame")
        except Exception as exc:
            return FrameResult(False, 0, 0, str(exc))
