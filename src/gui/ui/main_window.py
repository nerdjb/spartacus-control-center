"""
Main Window Widget - Dashboard and control interface
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QLabel, 
    QSlider, QPushButton, QSpinBox, QComboBox, QGroupBox, QScrollArea, QDialog
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QSettings
from PyQt6.QtGui import QFont, QPixmap
from pathlib import Path

from daemon.ipc_client import IPCClient
from models.presets import ThemePresets
from models.renderer import ThemeManager
from ui.theme_designer import ThemeDesignerWidget


class MainWindow(QWidget):
    """Main control center dashboard"""

    status_changed = pyqtSignal(dict)

    def __init__(self, ipc_client: IPCClient):
        super().__init__()
        self.ipc_client = ipc_client
        
        # Initialize theme system
        self.theme_manager = ThemeManager()
        self.current_telemetry = {
            "cpu_temp": 0.0,
            "gpu_temp": 0.0,
            "pump_rpm": 0,
            "fan_0_rpm": 0, "fan_1_rpm": 0, "fan_2_rpm": 0,
            "fan_3_rpm": 0, "fan_4_rpm": 0, "fan_5_rpm": 0,
        }
        
        # Load preset themes
        self.presets = ThemePresets.get_all_themes()
        for name, theme in self.presets.items():
            self.theme_manager.register_theme(name, theme)
        
        # Set default theme (minimal)
        self.theme_manager.switch_theme("minimal")
        
        self.setup_ui()
        self.theme_settings = QSettings("Spartacus", "ControlCenter")
        saved_theme = self.theme_settings.value("theme", "Minimal")
        saved_index = self.theme_combo.findText(saved_theme)
        if saved_index >= 0:
            self.theme_combo.setCurrentIndex(saved_index)

    def setup_ui(self):
        """Setup the main UI layout"""
        main_layout = QVBoxLayout()

        # Title
        title = QLabel("SPARTACUS CONTROL CENTER")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        main_layout.addWidget(title)

        # Status display
        status_layout = QHBoxLayout()
        self.status_label = QLabel("Status: Connecting...")
        status_layout.addWidget(self.status_label)
        main_layout.addLayout(status_layout)

        # Tabs
        tabs = QTabWidget()
        tabs.addTab(self.create_dashboard_tab(), "Dashboard")
        tabs.addTab(self.create_cooling_tab(), "Cooling")
        tabs.addTab(self.create_rgb_tab(), "RGB Control")
        tabs.addTab(self.create_themes_tab(), "Themes")
        tabs.addTab(self.create_settings_tab(), "Settings")

        main_layout.addWidget(tabs)
        self.setLayout(main_layout)

    def create_dashboard_tab(self) -> QWidget:
        """Create dashboard tab with telemetry display"""
        widget = QWidget()
        layout = QVBoxLayout()

        # Temperature display
        temps_group = QGroupBox("Temperature")
        temps_layout = QVBoxLayout()

        self.cpu_temp_label = QLabel("CPU: -- °C")
        cpu_font = QFont()
        cpu_font.setPointSize(14)
        cpu_font.setBold(True)
        self.cpu_temp_label.setFont(cpu_font)
        temps_layout.addWidget(self.cpu_temp_label)

        self.gpu_temp_label = QLabel("GPU: -- °C")
        gpu_font = QFont()
        gpu_font.setPointSize(14)
        gpu_font.setBold(True)
        self.gpu_temp_label.setFont(gpu_font)
        temps_layout.addWidget(self.gpu_temp_label)

        temps_group.setLayout(temps_layout)
        layout.addWidget(temps_group)

        # Fan/Pump RPM display
        rpm_group = QGroupBox("Performance")
        rpm_layout = QVBoxLayout()

        self.pump_rpm_label = QLabel("Pump RPM: -- ")
        rpm_layout.addWidget(self.pump_rpm_label)

        for i in range(6):
            label = QLabel(f"Fan {i+1} RPM: -- ")
            setattr(self, f"fan_{i}_rpm_label", label)
            rpm_layout.addWidget(label)

        rpm_group.setLayout(rpm_layout)
        layout.addWidget(rpm_group)

        widget.setLayout(layout)
        return widget

    def create_cooling_tab(self) -> QWidget:
        """Create cooling control tab"""
        widget = QWidget()
        layout = QVBoxLayout()

        # Pump control
        pump_group = QGroupBox("Pump Control")
        pump_layout = QVBoxLayout()

        pump_layout.addWidget(QLabel("Pump Speed: "))
        pump_slider = QSlider(Qt.Orientation.Horizontal)
        pump_slider.setMinimum(0)
        pump_slider.setMaximum(100)
        pump_slider.setValue(50)
        pump_slider.valueChanged.connect(lambda v: self.on_pump_changed(v))
        pump_layout.addWidget(pump_slider)

        self.pump_speed_label = QLabel("50%")
        pump_layout.addWidget(self.pump_speed_label)

        pump_group.setLayout(pump_layout)
        layout.addWidget(pump_group)

        # Fan control
        fan_group = QGroupBox("Radiator Fans")
        fan_layout = QVBoxLayout()

        for i in range(6):
            fan_h_layout = QHBoxLayout()
            fan_h_layout.addWidget(QLabel(f"Fan {i+1}: "))

            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setMinimum(0)
            slider.setMaximum(100)
            slider.setValue(50)
            slider.valueChanged.connect(lambda v, idx=i: self.on_fan_changed(idx, v))
            fan_h_layout.addWidget(slider)

            speed_label = QLabel("50%")
            fan_h_layout.addWidget(speed_label)
            setattr(self, f"fan_{i}_speed_label", speed_label)

            fan_layout.addLayout(fan_h_layout)

        fan_group.setLayout(fan_layout)
        layout.addWidget(fan_group)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def create_rgb_tab(self) -> QWidget:
        """Create RGB/ARGB control tab"""
        widget = QWidget()
        layout = QVBoxLayout()

        layout.addWidget(QLabel("LED Control"))

        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("Mode: "))
        mode_combo = QComboBox()
        mode_combo.addItems(["Static", "Rainbow", "Wave", "Breathing", "CPU Temp", "GPU Temp"])
        mode_combo.currentTextChanged.connect(self.on_rgb_mode_changed)
        mode_layout.addWidget(mode_combo)
        layout.addLayout(mode_layout)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def create_themes_tab(self) -> QWidget:
        """Create LCD display themes tab with preview"""
        widget = QWidget()
        layout = QVBoxLayout()

        # Title
        title = QLabel("LCD Display Themes")
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        # Theme selection
        theme_layout = QHBoxLayout()
        theme_layout.addWidget(QLabel("Preset: "))
        
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Minimal", "Gaming", "Cyberpunk", "Dashboard", "Media"])
        self.theme_combo.currentTextChanged.connect(self.on_theme_selected)
        theme_layout.addWidget(self.theme_combo)
        
        theme_layout.addStretch()
        layout.addLayout(theme_layout)

        # Theme preview (480×480 canvas area)
        preview_group = QGroupBox("Live Preview")
        preview_layout = QVBoxLayout()
        
        self.theme_preview_label = QLabel()
        self.theme_preview_label.setMinimumSize(480, 480)
        self.theme_preview_label.setMaximumSize(480, 480)
        self.theme_preview_label.setStyleSheet(
            "border: 2px solid #0084FF; "
            "border-radius: 20px; "
            "background-color: #000;"
        )
        preview_layout.addWidget(self.theme_preview_label)
        preview_group.setLayout(preview_layout)
        layout.addWidget(preview_group)

        # Theme designer button
        design_btn = QPushButton("Open Theme Designer")
        design_btn.setMinimumHeight(40)
        design_btn.clicked.connect(self.open_theme_designer)
        layout.addWidget(design_btn)

        # Auto-update preview timer
        self.preview_timer = QTimer()
        self.preview_timer.timeout.connect(self.update_theme_preview)
        self.preview_timer.start(1000)  # Update every 1 second

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def create_settings_tab(self) -> QWidget:
        """Create settings tab"""
        widget = QWidget()
        layout = QVBoxLayout()

        layout.addWidget(QLabel("Settings"))
        layout.addWidget(QPushButton("Preferences"))
        layout.addWidget(QPushButton("About"))
        layout.addStretch()

        widget.setLayout(layout)
        return widget

    def update_status(self, status: dict):
        """Update display with daemon status"""
        try:
            self.status_label.setText("Status: Connected ✓")

            # Update temperatures
            self.cpu_temp_label.setText(f"CPU: {status.get('cpu_temp', 0):.1f} °C")
            self.gpu_temp_label.setText(f"GPU: {status.get('gpu_temp', 0):.1f} °C")

            # Update RPM
            self.pump_rpm_label.setText(f"Pump RPM: {status.get('pump_rpm', 0)}")

            fan_rpm = status.get('fan_rpm', [0] * 6)
            for i, rpm in enumerate(fan_rpm):
                label = getattr(self, f"fan_{i}_rpm_label", None)
                if label:
                    label.setText(f"Fan {i+1} RPM: {rpm}")
            
            # Update current telemetry for theme rendering
            self.current_telemetry["cpu_temp"] = status.get('cpu_temp', 0)
            self.current_telemetry["gpu_temp"] = status.get('gpu_temp', 0)
            self.current_telemetry["pump_rpm"] = status.get('pump_rpm', 0)
            if fan_rpm:
                for i, rpm in enumerate(fan_rpm):
                    self.current_telemetry[f"fan_{i}_rpm"] = rpm
            if getattr(self, "designer_widget", None):
                self.designer_widget.update_telemetry(self.current_telemetry)

        except Exception as e:
            self.status_label.setText(f"Status: Error ({e})")
    
    def on_theme_selected(self, theme_name: str):
        """Handle theme selection from dropdown"""
        theme_key = theme_name.lower()
        
        if self.theme_manager.switch_theme(theme_key):
            self.theme_settings.setValue("theme", theme_name)
            self.update_theme_preview()
    
    def update_theme_preview(self):
        """Update theme preview image"""
        try:
            # Render current theme with live telemetry
            preview_image = self.theme_manager.get_preview(self.current_telemetry)
            
            # Convert PIL to QPixmap
            import io
            buffer = io.BytesIO()
            preview_image.save(buffer, format='PPM')
            buffer.seek(0)
            
            pixmap = QPixmap()
            pixmap.loadFromData(buffer.getvalue())
            
            self.theme_preview_label.setPixmap(pixmap.scaledToWidth(480))
        except Exception as e:
            self.theme_preview_label.setText(f"Preview Error: {e}")
    
    def open_theme_designer(self):
        """Open theme designer dialog"""
        designer_dialog = QDialog(self)
        designer_dialog.setWindowTitle("Theme Designer")
        designer_dialog.setGeometry(100, 100, 1200, 600)
        
        designer_layout = QVBoxLayout()
        self.designer_widget = ThemeDesignerWidget(self.ipc_client, designer_dialog)
        self.designer_widget.update_telemetry(self.current_telemetry)
        self.designer_widget.theme_changed.connect(self.on_designer_theme_changed)
        designer_layout.addWidget(self.designer_widget)
        
        designer_dialog.setLayout(designer_layout)
        designer_dialog.exec()
        self.designer_widget = None

    def on_designer_theme_changed(self, theme):
        """Use a designer-loaded theme for the main preview."""
        self.theme_manager.load_theme(theme)
        self.update_theme_preview()

    def on_pump_changed(self, value: int):
        """Handle pump speed change"""
        self.pump_speed_label.setText(f"{value}%")
        self.ipc_client.set_pump_speed(value)

    def on_fan_changed(self, fan_index: int, value: int):
        """Handle fan speed change"""
        label = getattr(self, f"fan_{fan_index}_speed_label", None)
        if label:
            label.setText(f"{value}%")
        self.ipc_client.set_fan_speed(fan_index, value)

    def on_rgb_mode_changed(self, mode: str):
        """Handle RGB mode change"""
        self.ipc_client.set_rgb_mode(mode.lower())
