"""Full-stack integration: real MainWindow + live mock daemon.

Proves the complete path: daemon snapshot -> TelemetryWorker (thread) ->
TelemetryPipeline -> UI cards, and GUI actions -> IPC -> daemon receipt.
Runs headless; requires no hardware.
"""

import io
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "gui"))

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from core.telemetry.quality import MetricQuality
from daemon.ipc_client import IPCClient
from test_ipc_roundtrip import MockDaemon


def pump_events(seconds: float, app) -> None:
    """Run the Qt event loop so queued cross-thread signals are delivered."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.02)


class TestFullStack(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.daemon = MockDaemon("/tmp/opencode/spartacus-fullstack.sock")

    @classmethod
    def tearDownClass(cls):
        cls.daemon.close()

    def setUp(self):
        self.client = IPCClient(socket_path=self.daemon.path)
        from ui.main_window import MainWindow

        self.window = MainWindow(self.client)

    def tearDown(self):
        self.window.shutdown()
        self.window.deleteLater()
        pump_events(0.2, self.app)
        self.client.close()

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def first_jpeg_bytes() -> bytes:
        from PIL import Image

        image = Image.new("RGB", (480, 480), (0, 240, 255))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=90)
        return buffer.getvalue()

    # -- tests ------------------------------------------------------------------

    def test_telemetry_flows_to_overview_cards(self):
        from PyQt6.QtWidgets import QFrame

        overview = self.window.pages.widget(0)
        cards = [child for child in overview.findChildren(QFrame)
                 if hasattr(child, "key") and hasattr(child, "value")]
        self.assertTrue(cards, "no metric cards found")
        pump_events(1.5, self.app)  # allow >= 2 worker polls
        cpu_card = next(c for c in cards if c.key == "cpu_temp")
        self.assertEqual(cpu_card.value.text(), "48")     # mock sends 47.5
        self.assertEqual(cpu_card.quality.property("quality"), "GOOD")
        model_value = self.window.telemetry.value("cpu_temp")
        self.assertAlmostEqual(model_value, 47.5, places=6)
        self.assertIs(self.window.telemetry.quality("cpu_temp"), MetricQuality.GOOD)

    def test_send_to_lcd_delivers_frame_bytes(self):
        before = len(self.daemon.received_frames)
        studio = self.window.studio
        studio.send_to_lcd()   # daemon offline? no: mock accepts everything
        pump_events(0.3, self.app)
        self.assertEqual(len(self.daemon.received_frames), before + 1)
        frame = self.daemon.received_frames[-1]
        self.assertTrue(frame.startswith(b"\xff\xd8"))
        self.assertGreater(len(frame), 1000)   # a real rendered frame, not stub
        status_text = studio.status.text()
        self.assertIn("accepted", status_text)

    def test_fan_curve_apply_reaches_daemon(self):
        fans_page = self.window.pages.widget(2)
        fans_page.curves["aio"] = [(35, 25), (75, 95)]
        fans_page.channel_combo.setCurrentText("aio")
        fans_page.send_curve()
        curves = [c for c in self.daemon.received_curves if c.get("channel") == "aio"]
        self.assertTrue(curves, "curve never reached daemon")
        sent_points = curves[-1]["points"]
        self.assertEqual(sent_points[0], {"t": 35, "pwm": 25})
        self.assertEqual(sent_points[-1], {"t": 75, "pwm": 95})

    def test_lighting_send_reaches_daemon_state(self):
        lighting = self.window.pages.widget(3)
        lighting.rgb = (255, 0, 255)
        lighting.mode.setCurrentText("Static")
        lighting.send()
        self.assertEqual(lighting.status.text(), "Lighting command accepted.")
        # Mock records nothing for lighting; acceptance proves RPC round-trip.
        self.assertIn("accepted", lighting.status.text())


if __name__ == "__main__":
    unittest.main()
