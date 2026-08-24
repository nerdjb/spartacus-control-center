"""IPC round-trip integration tests against a mock JSON-RPC daemon."""

import json
import os
import socket
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "gui"))

from core.ipc.client import DaemonClient


class MockDaemon:
    """Minimal newline-delimited JSON-RPC server on a private UNIX socket."""

    def __init__(self, path: str):
        self.path = path
        self.received_frames: list[bytes] = []
        self.received_curves: list[dict] = []
        self.received_commands: list[dict] = []
        if os.path.exists(path):
            os.unlink(path)
        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server.bind(path)
        self._server.listen(4)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self):
        while not self._stop.is_set():
            try:
                conn, _ = self._server.accept()
            except OSError:
                return
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn):
        buffer = b""
        while not self._stop.is_set():
            chunk = conn.recv(65536)
            if not chunk:
                break
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                request = json.loads(line)
                result = self._route(request)
                conn.sendall((json.dumps({
                    "jsonrpc": "2.0", "result": result,
                    "error": None, "id": request["id"],
                }) + "\n").encode())

    def _route(self, request: dict):
        method, params = request["method"], request.get("params", {})
        if method == "GetTelemetry":
            return {"cpu_temp": 47.5, "cpu_usage": 12.0, "gpu_temp": 44.0,
                    "gpu_usage": 5.0, "pump_rpm": 2450, "aio_rpm": 980,
                    "ext1_rpm": 740, "ext2_rpm": 0}
        if method == "GetStatus":
            return {"usb_connected": True, "cpu_temp": 47.5, "gpu_temp": 44.0,
                    "pump_rpm": 2450, "fan_rpm": [980, 740, 0, 0, 0, 0]}
        if method == "SendLcdFrame":
            from core.ipc.protocol import decode_frame

            self.received_frames.append(decode_frame(params["jpeg_b64"]))
            return {"accepted": True}
        if method == "SetFanCurve":
            self.received_curves.append(params)
            return {"success": True, "channel": params.get("channel"),
                    "mode": "auto", "points": params.get("points")}
        if method in ("SetFans", "SetFanSpeed", "SetPumpSpeed", "SetRGBMode",
                      "SetLighting", "SetMotherboardSync", "LcdKeepalive",
                      "LcdSetConfig", "SetTheme"):
            self.received_commands.append({"method": method, "params": params})
            payload = {"success": True}
            if method == "SetFans":
                payload["mode"] = "manual"
            if method == "LcdKeepalive":
                payload["ok"] = True
            return payload
        return {}

    def commands_for(self, method: str) -> list[dict]:
        return [c for c in self.received_commands if c["method"] == method]

    def close(self):
        self._stop.set()
        self._server.close()
        if os.path.exists(self.path):
            os.unlink(self.path)


class TestIpcRoundTrip(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.daemon = MockDaemon("/tmp/opencode/spartacus-test.sock")

    @classmethod
    def tearDownClass(cls):
        cls.daemon.close()

    def setUp(self):
        self.client = DaemonClient(socket_path=self.daemon.path, timeout=2.0)

    def tearDown(self):
        self.client.close()

    def test_get_telemetry(self):
        status = self.client.get_telemetry()
        self.assertIsNotNone(status)
        self.assertEqual(status["pump_rpm"], 2450)

    def test_send_lcd_frame_delivers_jpeg(self):
        jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 64 + b"\xff\xd9"
        self.assertTrue(self.client.send_lcd_frame(jpeg))
        self.assertEqual(self.daemon.received_frames[-1], jpeg)

    def test_set_fan_curve_payload(self):
        points = [{"t": 30, "pwm": 40}, {"t": 70, "pwm": 100}]
        result = self.client.set_fan_curve("pump", points)
        self.assertIsNotNone(result)
        self.assertTrue(result["success"])
        sent = self.daemon.received_curves[-1]
        self.assertEqual(sent["channel"], "pump")
        self.assertEqual(sent["points"], points)

    def test_lighting_and_keepalive(self):
        self.assertIsNotNone(self.client.set_lighting("Rainbow", (255, 0, 255), 80, 10))
        self.assertTrue(self.client.lcd_keepalive())


if __name__ == "__main__":
    unittest.main()
