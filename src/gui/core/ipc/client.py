"""Daemon IPC client.

``DaemonClient`` performs synchronous JSON-RPC calls with a short socket
timeout — call it from worker threads (``TelemetryWorker``), never from slots
that own the GUI. ``TelemetryWorker`` is the single polling loop feeding the
validated telemetry pipeline; pages subscribe to :class:`TelemetryModel`
signals instead of talking to the daemon themselves.
"""

from __future__ import annotations

import json
import os
import socket
import threading
from typing import Any, Optional

from PyQt6.QtCore import QThread, pyqtSignal

from core.ipc import protocol as rpc


def default_socket_path() -> str:
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    return f"{runtime_dir}/spartacus.sock"


class DaemonClient:
    """Thread-safe JSON-RPC client for one daemon connection."""

    def __init__(self, socket_path: str | None = None, timeout: float = 2.0):
        self.socket_path = socket_path or default_socket_path()
        self.timeout = timeout
        self._sock: socket.socket | None = None
        self._lock = threading.Lock()
        self._request_id = 0

    # -- connection ----------------------------------------------------------

    def connect(self) -> bool:
        with self._lock:
            self._close_locked()
            try:
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.settimeout(self.timeout)
                sock.connect(self.socket_path)
            except OSError:
                self._sock = None
                return False
            self._sock = sock
            return True

    def is_connected(self) -> bool:
        return self._sock is not None

    def close(self) -> None:
        with self._lock:
            self._close_locked()

    def _close_locked(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    # -- core request ------------------------------------------------------------

    def call(self, method: str, params: dict | None = None) -> Any:
        """Execute one RPC; returns the result value or raises RpcError/OSError."""
        if self._sock is None and not self.connect():
            raise ConnectionError(f"daemon unreachable at {self.socket_path}")
        with self._lock:
            assert self._sock is not None
            self._request_id += 1
            request = {
                "jsonrpc": "2.0",
                "method": method,
                "params": params or {},
                "id": self._request_id,
            }
            try:
                self._sock.sendall(
                    (json.dumps(request) + "\n").encode("utf-8")
                )
                response = self._readline(self._sock)
            except OSError:
                self._close_locked()
                raise
        if not response:
            raise ConnectionError("daemon closed the connection")
        message = json.loads(response)
        if "error" in message and message["error"] is not None:
            raise rpc.RpcError(message["error"].get("code", -1),
                               message["error"].get("message", "unknown"))
        return message.get("result")

    @staticmethod
    def _readline(sock: socket.socket, max_bytes: int = 4 * 1024 * 1024) -> str:
        chunks: list[bytes] = []
        total = 0
        while total < max_bytes:
            chunk = sock.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if b"\n" in chunk:
                break
        return b"".join(chunks).decode("utf-8", errors="replace").strip()

    def try_call(self, method: str, params: dict | None = None,
                 default: Any = None) -> Any:
        """Error-swallowing variant for fire-and-forget UI actions."""
        try:
            return self.call(method, params)
        except (ConnectionError, OSError, rpc.RpcError, json.JSONDecodeError):
            return default

    # -- typed facade (legacy names preserved) ---------------------------------

    def get_status(self) -> Optional[dict]:
        return self.try_call(rpc.GET_STATUS)

    def get_telemetry(self) -> Optional[dict]:
        return self.try_call(rpc.GET_TELEMETRY)

    def set_pump_speed(self, speed: int) -> bool:
        result = self.try_call(
            rpc.SET_PUMP_SPEED, {"speed": rpc.clamp(speed, rpc.PUMP_DUTY_FLOOR, 100)}
        )
        return bool(result and result.get("success"))

    def set_fan_speed(self, fan_index: int, speed: int) -> bool:
        result = self.try_call(
            rpc.SET_FAN_SPEED, {"fan": fan_index, "speed": rpc.clamp(speed, 0, 100)}
        )
        return bool(result and result.get("success"))

    def set_fans(self, pump: int, aio: int, ext1: int, ext2: int,
                 ramp: int = 0) -> Optional[dict]:
        return self.try_call(rpc.SET_FANS, {
            "pump": rpc.clamp(pump, rpc.PUMP_DUTY_FLOOR, 100),
            "aio": rpc.clamp(aio, 0, 100),
            "ext1": rpc.clamp(ext1, 0, 100),
            "ext2": rpc.clamp(ext2, 0, 100),
            "ramp": rpc.clamp(ramp, 0, 30),
        })

    def set_fan_curve(self, channel: str, points: list[dict],
                      hysteresis: float = 2.0) -> Optional[dict]:
        clean = [{"t": float(p["t"]), "pwm": rpc.clamp(int(p["pwm"]), 0, 100)}
                 for p in points]
        return self.try_call(
            rpc.SET_FAN_CURVE,
            {"channel": channel, "points": clean, "hysteresis": hysteresis},
        )

    def set_rgb_mode(self, mode: str, speed: int = 50,
                     brightness: int = 255) -> bool:
        result = self.try_call(
            rpc.SET_RGB_MODE,
            {"mode": mode, "speed": speed, "brightness": brightness},
        )
        return bool(result and result.get("success"))

    def set_lighting(self, mode: str, color: tuple[int, int, int] | None = None,
                     speed: int | None = None,
                     saturation: int | None = None) -> Optional[dict]:
        params: dict[str, Any] = {"mode": mode}
        if color is not None:
            params["color"] = {"r": color[0], "g": color[1], "b": color[2]}
        if speed is not None:
            params["speed"] = rpc.clamp(speed, 0, 255)
        if saturation is not None:
            params["saturation"] = rpc.clamp(saturation, 0, 255)
        return self.try_call(rpc.SET_LIGHTING, params)

    def set_motherboard_sync(self, enable: bool) -> Optional[dict]:
        return self.try_call(rpc.SET_MOTHERBOARD_SYNC, {"enable": bool(enable)})

    # -- LCD ----------------------------------------------------------------------

    def send_lcd_frame(self, jpeg_bytes: bytes) -> bool:
        result = self.try_call(rpc.SEND_LCD_FRAME, rpc.encode_frame(jpeg_bytes))
        return bool(result and result.get("accepted"))

    def lcd_keepalive(self) -> bool:
        result = self.try_call(rpc.LCD_KEEPALIVE)
        return bool(result and result.get("ok"))

    def lcd_set_config(self, orientation: int | None = None,
                       brightness: int | None = None) -> Optional[dict]:
        params: dict[str, Any] = {}
        if orientation is not None:
            params["orientation"] = rpc.clamp(orientation, 0, 3)
        if brightness is not None:
            params["brightness"] = rpc.clamp(brightness, 0, 100)
        return self.try_call(rpc.LCD_SET_CONFIG, params)

    def get_diagnostics(self) -> Optional[dict]:
        return self.try_call(rpc.GET_DIAGNOSTICS)


class TelemetryWorker(QThread):
    """Polls the daemon off the GUI thread; feeds TelemetryModel.ingest_snapshot."""

    snapshot_ready = pyqtSignal(dict)
    connection_changed = pyqtSignal(bool)

    def __init__(self, client: DaemonClient, interval_ms: int = 500, parent=None):
        super().__init__(parent)
        self.client = client
        self.interval_ms = interval_ms
        self._running = False
        self._last_connected = False

    def run(self) -> None:
        self._running = True
        while self._running:
            status = self.client.get_telemetry() or self.client.get_status() or {}
            connected = bool(status)
            if connected != self._last_connected:
                self._last_connected = connected
                self.connection_changed.emit(connected)
            if status:
                self.snapshot_ready.emit(status)
            self.msleep(self.interval_ms)

    def stop(self) -> None:
        self._running = False
        self.wait(max(2000, self.interval_ms * 3))
