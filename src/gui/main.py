#!/usr/bin/env python3
"""
Spartacus Control Center - Main GUI Application
PyQt6-based desktop application for DeepCool Spartacus control

Usage:
    python3 main.py
"""

import sys
import json
import asyncio
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QMainWindow, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QAction, QPixmap
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QThread

from ui.main_window import MainWindow
from daemon.ipc_client import IPCClient


class DaemonSignals(QObject):
    """Signal emitter for daemon events (must be QObject to use pyqtSignal)"""
    status_updated = pyqtSignal(dict)
    daemon_connected = pyqtSignal()
    daemon_disconnected = pyqtSignal()


class SpartacusControlCenter(QMainWindow):
    """Main application window with system tray integration"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Spartacus Control Center")
        self.setWindowIcon(self.load_icon())
        self.setGeometry(100, 100, 1200, 800)

        # Initialize daemon communication
        self.ipc_client = IPCClient()
        self.daemon_signals = DaemonSignals()
        self.daemon_signals.daemon_connected.connect(self.on_daemon_connected)
        self.daemon_signals.daemon_disconnected.connect(self.on_daemon_disconnected)

        # Initialize main widget
        self.central_widget = MainWindow(self.ipc_client)
        self.setCentralWidget(self.central_widget)

        # Setup system tray
        self.setup_tray()

        # Telemetry update timer
        self.telemetry_timer = QTimer()
        self.telemetry_timer.timeout.connect(self.update_telemetry)
        self.telemetry_timer.start(1000)  # Update every 1 second

        # Daemon connection checker timer
        self.connection_timer = QTimer()
        self.connection_timer.timeout.connect(self.check_daemon_connection)
        self.connection_timer.start(5000)  # Check every 5 seconds

        self.show()

    def load_icon(self) -> QIcon:
        """Load application icon"""
        icon_paths = [
            Path(__file__).parent / "resources" / "icons" / "128x128" / "spartacus-control.png",
            Path("/usr/share/icons/hicolor/128x128/apps/spartacus-control.png"),
            Path.home() / ".local/share/icons/hicolor/128x128/apps/spartacus-control.png",
        ]

        for icon_path in icon_paths:
            if icon_path.exists():
                return QIcon(str(icon_path))

        # Fallback to generic icon
        return QIcon.fromTheme("application-x-executable")

    def setup_tray(self):
        """Setup system tray icon and context menu"""
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self.load_icon())

        # Tray context menu
        tray_menu = QMenu()

        show_action = QAction("Show", self)
        show_action.triggered.connect(self.show_window)
        tray_menu.addAction(show_action)

        tray_menu.addSeparator()

        # Profile quick actions
        silent_action = QAction("Silent Profile", self)
        silent_action.triggered.connect(lambda: self.apply_profile("silent"))
        tray_menu.addAction(silent_action)

        balanced_action = QAction("Balanced Profile", self)
        balanced_action.triggered.connect(lambda: self.apply_profile("balanced"))
        tray_menu.addAction(balanced_action)

        performance_action = QAction("Performance Profile", self)
        performance_action.triggered.connect(lambda: self.apply_profile("performance"))
        tray_menu.addAction(performance_action)

        gaming_action = QAction("Gaming Profile", self)
        gaming_action.triggered.connect(lambda: self.apply_profile("gaming"))
        tray_menu.addAction(gaming_action)

        tray_menu.addSeparator()

        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.exit_app)
        tray_menu.addAction(exit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.toggle_window)
        self.tray_icon.show()

    def show_window(self):
        """Show main window"""
        self.showNormal()
        self.activateWindow()

    def toggle_window(self, reason):
        """Toggle window visibility on tray click"""
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self.show_window()

    def apply_profile(self, profile: str):
        """Apply preset cooling profile"""
        profiles = {
            "silent": {"pump": 40, "fans": [30, 35, 30, 35, 30, 35]},
            "balanced": {"pump": 60, "fans": [50, 50, 50, 50, 50, 50]},
            "performance": {"pump": 80, "fans": [70, 75, 70, 75, 70, 75]},
            "gaming": {"pump": 100, "fans": [100, 100, 100, 100, 100, 100]},
        }

        if profile in profiles:
            settings = profiles[profile]
            # TODO: Send to daemon via IPC

    def check_daemon_connection(self):
        """Check if daemon is reachable"""
        if self.ipc_client.is_connected():
            if not hasattr(self, '_daemon_was_connected'):
                self._daemon_was_connected = True
                self.daemon_signals.daemon_connected.emit()
        else:
            if hasattr(self, '_daemon_was_connected') and self._daemon_was_connected:
                self._daemon_was_connected = False
                self.daemon_signals.daemon_disconnected.emit()

    def update_telemetry(self):
        """Update telemetry from daemon"""
        try:
            status = self.ipc_client.get_status()
            if status:
                self.central_widget.update_status(status)
                self.daemon_signals.status_updated.emit(status)
        except Exception as e:
            pass  # Daemon not connected yet

    def on_daemon_connected(self):
        """Handle daemon connection"""
        self.statusBar().showMessage("✓ Daemon connected")

    def on_daemon_disconnected(self):
        """Handle daemon disconnection"""
        self.statusBar().showMessage("✗ Daemon disconnected - Start daemon with: systemctl --user start spartacus-daemon")

    def closeEvent(self, event):
        """Handle window close - minimize to tray instead of quitting"""
        if self.tray_icon.isVisible():
            self.hide()
            event.ignore()
        else:
            event.accept()

    def exit_app(self):
        """Exit application"""
        self.ipc_client.close()
        self.telemetry_timer.stop()
        self.connection_timer.stop()
        QApplication.quit()


def main():
    app = QApplication(sys.argv)
    window = SpartacusControlCenter()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
