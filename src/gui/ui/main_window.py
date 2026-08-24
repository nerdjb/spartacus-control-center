"""SPARTACUS Control Center v2 application shell and functional pages."""

from __future__ import annotations

import re
import shutil
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QSize, pyqtSignal
from PyQt6.QtGui import QColor, QKeySequence, QShortcut, QImage
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QScrollArea, QSlider, QSpinBox, QStackedWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from core.hardware.curves import apply_pump_floor, default_curve, sanitize_points
from core.ipc.client import DaemonClient, TelemetryWorker
from PIL import Image
from core.theme.preview import SpecRenderer, widget_at
from core.theme.spec import BINDINGS, WIDGET_KINDS, ThemeSpec, Widget, builtin_specs
from core.telemetry.diagnostics import collect_rows
from core.telemetry.model import TelemetryModel
from core.telemetry.pipeline import TelemetryPipeline
from ui.widgets.fan_curve_editor import FanCurveEditor

BINDABLE_KEYS = [
    "cpu_temp", "cpu_usage", "cpu_freq_ghz", "gpu_temp", "gpu_usage",
    "pump_rpm", "aio_rpm", "ext1_rpm", "ext2_rpm",
    "ram_used_gb", "ram_total_gb", "net_down_kbps", "net_up_kbps",
]


# --------------------------------------------------------------------------- overview


class MetricCard(QFrame):
    def __init__(self, title: str, key: str, model: TelemetryModel, parent=None):
        super().__init__(parent)
        self.setProperty("card", True)
        self.key, self.model = key, model
        layout = QVBoxLayout(self)
        title_label = QLabel(title.upper())
        title_label.setObjectName("CardTitle")
        layout.addWidget(title_label)
        self.value = QLabel("--")
        self.value.setObjectName("MetricValue")
        layout.addWidget(self.value)
        self.quality = QLabel("● UNAVAILABLE")
        self.quality.setProperty("quality", "UNAVAILABLE")
        layout.addWidget(self.quality)
        model.metric_changed.connect(self.refresh)
        model.quality_changed.connect(lambda key, _quality: self.refresh(key))
        self.refresh(key)

    def refresh(self, key: str):
        if key != self.key:
            return
        self.value.setText(self.model.text(self.key))
        quality = self.model.quality(self.key)
        self.quality.setText(f"● {quality.value}  {self.model.latency_ms(self.key):.0f} ms")
        self.quality.setProperty("quality", quality.value)
        self.quality.style().unpolish(self.quality)
        self.quality.style().polish(self.quality)


class OverviewPage(QWidget):
    def __init__(self, model: TelemetryModel, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        heading = QLabel("Overview")
        heading.setObjectName("BrandTitle")
        root.addWidget(heading)
        grid = QGridLayout()
        cards = [
            ("CPU Temperature", "cpu_temp"), ("CPU Usage", "cpu_usage"),
            ("CPU Frequency", "cpu_freq_ghz"), ("GPU Temperature", "gpu_temp"),
            ("GPU Usage", "gpu_usage"), ("Pump", "pump_rpm"),
            ("AIO Fan", "aio_rpm"), ("EXT1", "ext1_rpm"),
            ("EXT2", "ext2_rpm"), ("RAM Used", "ram_used_gb"),
            ("Network Down", "net_down_kbps"), ("Network Up", "net_up_kbps"),
        ]
        for index, (title, key) in enumerate(cards):
            grid.addWidget(MetricCard(title, key, model), index // 4, index % 4)
        root.addLayout(grid)
        note = QLabel("Only GOOD samples render as live telemetry. STALE / INVALID / "
                      "OUTLIER / UNAVAILABLE values display as --.")
        note.setWordWrap(True)
        root.addWidget(note)
        root.addStretch()


# --------------------------------------------------------------------------- cooling


class ChannelSlidersPage(QWidget):
    """Shared implementation for the Cooling and Fans pages.

    Cooling = live duty sliders; Fans = interactive curve editor. Both enforce
    the daemon's pump floor client-side and rely on daemon re-validation.
    """

    def __init__(self, client: DaemonClient, model: TelemetryModel,
                 title: str, mode: str, parent=None):
        super().__init__(parent)
        self.client, self.model, self.mode = client, model, mode
        root = QVBoxLayout(self)
        heading = QLabel(title)
        heading.setObjectName("BrandTitle")
        root.addWidget(heading)

        if mode == "sliders":
            self.mb_sync = QCheckBox("Motherboard sync (fans + AIO follow motherboard)")
            self.mb_sync.toggled.connect(self.send_mb_sync)
            root.addWidget(self.mb_sync)
            form = QFormLayout()
            self.sliders = {}
            for name, minimum in (("Pump", 40), ("AIO", 0), ("EXT1", 0), ("EXT2", 0)):
                slider = QSlider(Qt.Orientation.Horizontal)
                slider.setRange(minimum, 100)
                slider.setValue(max(minimum, 55))
                label = QLabel(f"{slider.value()}%")
                slider.valueChanged.connect(lambda value, label=label: label.setText(f"{value}%"))
                slider.sliderReleased.connect(self.send_fans)
                row = QWidget()
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.addWidget(slider)
                row_layout.addWidget(label)
                form.addRow(name, row)
                self.sliders[name.lower()] = slider
            root.addLayout(form)
            self.profiles = QComboBox()
            self.profiles.addItems(["Silent", "Balanced", "Performance"])
            self.profiles.currentTextChanged.connect(self.apply_profile)
            root.addWidget(QLabel("Profile"))
            root.addWidget(self.profiles)
        else:
            controls = QHBoxLayout()
            controls.addWidget(QLabel("Channel"))
            self.channel_combo = QComboBox()
            self.channel_combo.addItems(["pump", "aio", "ext1", "ext2"])
            controls.addWidget(self.channel_combo)
            apply_button = QPushButton("Apply curve to daemon")
            apply_button.setProperty("accent", "primary")
            apply_button.clicked.connect(self.send_curve)
            reset_button = QPushButton("Reset")
            reset_button.clicked.connect(self.reset_channel)
            controls.addWidget(apply_button)
            controls.addWidget(reset_button)
            controls.addStretch()
            root.addLayout(controls)
            self.editor = FanCurveEditor("pump", self)
            self.curve_edited_once = False
            self.editor.curve_edited.connect(self.on_curve_edited)
            self.channel_combo.currentTextChanged.connect(self.switch_channel)
            root.addWidget(self.editor, 1)
            self.curves: dict[str, list[tuple[int, int]]] = {
                key: default_curve() for key in ("pump", "aio", "ext1", "ext2")
            }
            self.editor.set_points(self.curves["pump"])
            self.model.metric_changed.connect(self.on_metric)

        self.status = QLabel("Daemon safety limits are enforced on every write.")
        root.addWidget(self.status)
        root.addStretch()

    # sliders ---------------------------------------------------------------

    def send_mb_sync(self, enabled: bool):
        result = self.client.set_motherboard_sync(enabled)
        if result is not None:
            self.mb_sync.setText("Motherboard sync ON — daemon is hands-off"
                                 if enabled else "Motherboard sync (fans + AIO follow motherboard)")
            for slider in getattr(self, "sliders", {}).values():
                slider.setEnabled(not enabled)
        else:
            self.mb_sync.blockSignals(True)
            self.mb_sync.setChecked(False)
            self.mb_sync.blockSignals(False)
            QMessageBox.warning(self, "Daemon unreachable",
                                "Could not apply motherboard sync.")

    def send_fans(self):
        result = self.client.set_fans(
            self.sliders["pump"].value(), self.sliders["aio"].value(),
            self.sliders["ext1"].value(), self.sliders["ext2"].value())
        if result:
            self.status.setText("Manual duties applied — automatic curve control paused "
                                "(apply a curve on the Fans page to resume).")
        else:
            self.status.setText("Fan command unavailable (daemon offline?).")

    def apply_profile(self, name: str):
        values = {"Silent": (40, 30, 30, 30),
                  "Balanced": (55, 50, 50, 50),
                  "Performance": (75, 75, 75, 75)}.get(name)
        if values:
            for key, value in zip(("pump", "aio", "ext1", "ext2"), values):
                self.sliders[key].setValue(value)

    # curves ------------------------------------------------------------------

    def switch_channel(self, channel: str):
        self.editor.set_channel(channel, self.curves[channel])

    def on_curve_edited(self, points: list):
        channel = self.channel_combo.currentText()
        points = [(int(t), int(d)) for t, d in points]
        if channel == "pump":
            points = apply_pump_floor(points)
            self.editor.set_points(points)   # snap visual above the floor
        self.curves[channel] = points
        duty = self.editor.target_duty()
        temp = self.editor.current_temp
        self.status.setText(
            f"{channel}: target {duty:.0f}% at {temp:.0f}°C — press Apply to send."
            if duty is not None and temp is not None else f"{channel}: {len(points)} points")

    def on_metric(self, key: str):
        if key in ("cpu_temp", "gpu_temp"):
            value = self.model.value("cpu_temp" if key == "cpu_temp" else "gpu_temp")
            self.editor.set_live_temperature(value)

    def send_curve(self):
        channel = self.channel_combo.currentText()
        points = sanitize_points(self.curves[channel])
        if channel == "pump":
            points = apply_pump_floor(points)
        payload = [{"t": t, "pwm": d} for t, d in points]
        result = self.client.set_fan_curve(channel, payload)
        if result:
            self.status.setText(f"Curve for {channel} stored and active — "
                                f"automatic control resumed ({len(points)} points).")
        else:
            self.status.setText("Curve rejected or daemon offline.")

    def reset_channel(self):
        channel = self.channel_combo.currentText()
        self.curves[channel] = default_curve()
        self.editor.set_points(self.curves[channel])


# --------------------------------------------------------------------------- lighting


class LightingPage(QWidget):
    MODES = ["Off", "Static", "Rainbow", "Breathing", "Temperature Reactive"]

    def __init__(self, client: DaemonClient, parent=None):
        super().__init__(parent)
        self.client = client
        self.rgb = (0, 240, 255)
        root = QVBoxLayout(self)
        heading = QLabel("Lighting")
        heading.setObjectName("BrandTitle")
        root.addWidget(heading)
        form = QFormLayout()
        self.mode = QComboBox()
        self.mode.addItems(self.MODES)
        form.addRow("Mode", self.mode)
        self.speed = QSlider(Qt.Orientation.Horizontal)
        self.speed.setRange(0, 255)
        self.speed.setValue(80)
        form.addRow("Speed", self.speed)
        self.saturation = QSlider(Qt.Orientation.Horizontal)
        self.saturation.setRange(0, 255)
        self.saturation.setValue(180)
        form.addRow("Saturation", self.saturation)
        self.color_button = QPushButton("#00F0FF")
        self.color_button.clicked.connect(self.choose_color)
        form.addRow("Color", self.color_button)
        self.sync = QCheckBox("Motherboard ARGB synchronization")
        self.sync.toggled.connect(self.send_sync)
        root.addLayout(form)
        root.addWidget(self.sync)
        apply = QPushButton("Apply lighting")
        apply.setProperty("accent", "primary")
        apply.clicked.connect(self.send)
        root.addWidget(apply)
        self.status = QLabel()
        root.addWidget(self.status)
        root.addStretch()

    def choose_color(self):
        from PyQt6.QtWidgets import QColorDialog

        color = QColorDialog.getColor(QColor("#00F0FF"), self)
        if color.isValid():
            self.rgb = (color.red(), color.green(), color.blue())
            self.color_button.setText(color.name())

    def send(self):
        mode = self.mode.currentText()
        static_modes = {"Off": (0, 0, 0)}
        color = static_modes.get(mode, self.rgb)
        result = self.client.set_lighting(mode, color,
                                          self.speed.value(), self.saturation.value())
        self.status.setText("Lighting command accepted." if result
                            else "Lighting command unavailable.")

    def send_sync(self, enabled: bool):
        result = self.client.set_motherboard_sync(enabled)
        if result:
            self.status.setText("Motherboard sync applied.")


# --------------------------------------------------------------------------- LCD Studio


class ThemeStudioPage(QWidget):
    """Design 480x480 panel themes with the same primitives the daemon's Rust
    renderer draws natively — what you design is exactly what ships."""

    def __init__(self, client: DaemonClient, model: TelemetryModel, parent=None):
        super().__init__(parent)
        self.client, self.model = client, model
        self.spec = ThemeSpec(name="my-theme")
        self.selected = -1
        self.undo_stack: list[dict] = []
        self.redo_stack: list[dict] = []
        self._drag_offset = (0.0, 0.0)
        self._dragging = False
        self._build_ui()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_live)
        self.timer.start(1000)

        shortcuts = {
            "Ctrl+Z": self.undo, "Ctrl+Y": self.redo, "Ctrl+Shift+Z": self.redo,
            "Delete": self.delete_widget,
        }
        for sequence, handler in shortcuts.items():
            QShortcut(QKeySequence(sequence), self).activated.connect(handler)

        presets = builtin_specs()
        self.load_preset("cards" if "cards" in presets else next(iter(presets), ""))

    # -- UI construction ------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        brand = QLabel("THEME STUDIO")
        brand.setObjectName("CardTitle")
        toolbar.addWidget(brand)
        edit_button = QPushButton("✏  Edit Theme")
        edit_button.setProperty("accent", "primary")
        edit_button.clicked.connect(self.pick_theme_edit)
        create_button = QPushButton("＋  Create Theme")
        create_button.clicked.connect(self.pick_theme_create)
        toolbar.addWidget(edit_button)
        toolbar.addWidget(create_button)
        open_button = QPushButton("Open JSON")
        open_button.clicked.connect(self.open_json)
        save_button = QPushButton("Save JSON")
        save_button.clicked.connect(self.save_json)
        png_button = QPushButton("Export PNG")
        png_button.clicked.connect(self.export_png)
        apply_button = QPushButton("APPLY TO DAEMON")
        apply_button.setProperty("accent", "primary")
        apply_button.clicked.connect(self.apply_to_daemon)
        for widget in (open_button, save_button, png_button, apply_button):
            toolbar.addWidget(widget)
        toolbar.addStretch()
        root.addLayout(toolbar)

        body = QHBoxLayout()
        left = QVBoxLayout()

        add_row = QHBoxLayout()
        for kind in WIDGET_KINDS:
            button = QPushButton(f"+ {kind.title()}")
            button.clicked.connect(lambda _, k=kind: self.add_widget(k))
            add_row.addWidget(button)
        left.addLayout(add_row)

        edit_row = QHBoxLayout()
        for label, handler in (("Dup", self.duplicate_widget), ("Del", self.delete_widget),
                               ("Up", lambda: self.move_widget(-1)),
                               ("Down", lambda: self.move_widget(1))):
            button = QPushButton(label)
            button.clicked.connect(handler)
            edit_row.addWidget(button)
        left.addLayout(edit_row)

        self.widget_list = QListWidget()
        self.widget_list.currentRowChanged.connect(self.on_list_select)
        left.addWidget(self.widget_list, 1)

        undo_row = QHBoxLayout()
        undo_button = QPushButton("Undo")
        undo_button.clicked.connect(self.undo)
        redo_button = QPushButton("Redo")
        redo_button.clicked.connect(self.redo)
        undo_row.addWidget(undo_button)
        undo_row.addWidget(redo_button)
        undo_row.addStretch()
        left.addLayout(undo_row)

        left_panel = QWidget()
        left_panel.setLayout(left)
        left_panel.setFixedWidth(250)

        self.canvas = ThemeCanvas(self)
        self.canvas.setFixedSize(484, 484)
        self.canvas.widget_selected.connect(self.on_canvas_select)
        self.canvas.widget_moved.connect(self.on_canvas_moved)
        self.canvas.edit_committed.connect(self.push_undo)
        self.status = QLabel("Pick a preset, edit, then APPLY TO DAEMON — "
                             "the daemon renders it natively at cards quality.")
        self.status.setWordWrap(True)

        center = QVBoxLayout()
        center.addWidget(self.canvas, 0, Qt.AlignmentFlag.AlignCenter)
        center.addWidget(self.status)
        center_widget = QWidget()
        center_widget.setLayout(center)

        self.inspector = QFormLayout()
        right_panel = QWidget()
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        inner = QWidget()
        inner.setLayout(self.inspector)
        right_scroll.setWidget(inner)
        right_scroll.setMinimumWidth(280)
        right_layout = QVBoxLayout(right_panel)
        right_layout.addWidget(right_scroll)

        body.addWidget(left_panel)
        body.addWidget(center_widget, 1)
        body.addWidget(right_panel)
        root.addLayout(body, 1)

    # -- state helpers ----------------------------------------------------------

    def push_undo(self) -> None:
        self.undo_stack.append(deepcopy(self.spec.to_dict()))
        self.undo_stack = self.undo_stack[-100:]
        self.redo_stack.clear()

    def undo(self) -> None:
        if not self.undo_stack:
            return
        self.redo_stack.append(deepcopy(self.spec.to_dict()))
        self.spec = ThemeSpec.from_dict(self.undo_stack.pop())
        self.selected = -1
        self.refresh_all()

    def redo(self) -> None:
        if not self.redo_stack:
            return
        self.undo_stack.append(deepcopy(self.spec.to_dict()))
        self.spec = ThemeSpec.from_dict(self.redo_stack.pop())
        self.selected = -1
        self.refresh_all()

    def live_metrics(self) -> dict:
        metrics: dict = {}
        try:
            latest = self.model.pipeline.latest()
        except Exception:
            latest = {}
        key_map = {"cpu_freq": "cpu_freq_ghz", "ram_used": "ram_used_gb",
                   "ram_total": "ram_total_gb", "net_up": "net_up_kbps",
                   "net_down": "net_down_kbps", "fan_rpm": "aio_rpm",
                   "pump_rpm": "pump_rpm"}
        for binding, source in key_map.items():
            validated = latest.get(source)
            if validated is not None and getattr(validated, "quality", None) is not None:
                if str(validated.quality.value) == "GOOD":
                    metrics[binding] = validated.value
        if "pump_rpm" in metrics:
            metrics["pump_pct"] = min(metrics["pump_rpm"], 3500) / 3500.0 * 100.0
        if "ram_used" in metrics and metrics.get("ram_total"):
            metrics["ram_pct"] = metrics["ram_used"] / metrics["ram_total"] * 100.0
        now = datetime.now()
        metrics["time"] = now.strftime("%H:%M:%S")
        metrics["date"] = now.strftime("%Y-%m-%d")
        return metrics

    # -- actions -----------------------------------------------------------------

    def pick_theme_edit(self) -> None:
        name = self._theme_gallery("Edit which theme?")
        if name:
            self.load_preset(name)
            self.status.setText(f"Editing '{name}' — change anything, then APPLY TO DAEMON.")

    def pick_theme_create(self) -> None:
        name = self._theme_gallery("Create — pick a starting style:", allow_blank=True)
        if not name:
            return
        self.push_undo()
        if name == "__blank__":
            self.spec = ThemeSpec(name="my-theme")
        else:
            self.spec = deepcopy(builtin_specs()[name])
            self.spec.name = "my-theme"
        self.selected = -1
        self.refresh_all()
        self.status.setText("New theme created — rename it (top-right name field "
                            "in Save), design, then APPLY TO DAEMON.")

    def _theme_gallery(self, title: str, allow_blank: bool = False) -> str | None:
        """Visual theme picker: rendered thumbnails, click to choose."""
        from PyQt6.QtWidgets import QDialog, QListWidget, QListWidgetItem, QVBoxLayout, QDialogButtonBox

        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        layout = QVBoxLayout(dialog)
        listing = QListWidget()
        listing.setIconSize(QSize(120, 120))
        listing.setViewMode(QListWidget.ViewMode.IconMode)
        listing.setResizeMode(QListWidget.ResizeMode.Adjust)
        listing.setSpacing(12)

        themes = dict(builtin_specs())
        if allow_blank:
            blank = QListWidgetItem("Blank")
            blank.setIcon(self._thumbnail(ThemeSpec(name="blank")))
            blank.setData(Qt.ItemDataRole.UserRole, "__blank__")
            listing.addItem(blank)
        for name, spec in themes.items():
            item = QListWidgetItem(name)
            item.setIcon(self._thumbnail(spec))
            item.setData(Qt.ItemDataRole.UserRole, name)
            listing.addItem(item)
        layout.addWidget(listing)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        listing.itemDoubleClicked.connect(lambda _: dialog.accept())
        listing.setCurrentRow(0)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        selected = listing.currentItem()
        return selected.data(Qt.ItemDataRole.UserRole) if selected else None

    _thumb_cache: dict = {}

    def _thumbnail(self, spec):
        from PyQt6.QtGui import QIcon, QPixmap, QImage

        key = spec.name
        if key in self._thumb_cache:
            return self._thumb_cache[key]
        try:
            image = SpecRenderer(spec).render(supersample=1)
        except Exception:
            image = Image.new("RGB", (480, 480), (20, 24, 32))
        data = image.tobytes()
        qimg = QImage(data, 480, 480, 480 * 3, QImage.Format.Format_RGB888)
        icon = QIcon(QPixmap.fromImage(qimg).scaled(
            120, 120, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))
        self._thumb_cache[key] = icon
        return icon

    def load_preset(self, name: str) -> None:
        specs = builtin_specs()
        if name not in specs:
            return
        self.push_undo()
        self.spec = deepcopy(specs[name])
        self.spec.name = name
        self.selected = -1
        self.refresh_all()
        self.status.setText(f"Preset '{name}' loaded — edit freely.")

    def open_json(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open theme", "",
                                              "Theme (*.json)")
        if not path:
            return
        try:
            self.push_undo()
            self.spec = ThemeSpec.load(path)
            self.selected = -1
            self.refresh_all()
            self.status.setText(f"Loaded {Path(path).name}")
        except Exception as exc:
            QMessageBox.critical(self, "Open failed", str(exc))

    def save_json(self) -> None:
        target_dir = Path.home() / ".config" / "spartacus" / "themes"
        target_dir.mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(
            self, "Save theme", str(target_dir / f"{self.spec.name or 'theme'}.json"),
            "Theme (*.json)")
        if not path:
            return
        try:
            self.spec.save(path)
            self.status.setText(f"Saved {Path(path).name}")
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))

    def export_png(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export PNG",
                                              f"{self.spec.name or 'theme'}.png",
                                              "PNG (*.png)")
        if not path:
            return
        SpecRenderer(self.spec, self.live_metrics()).render().save(path)
        self.status.setText(f"Exported {Path(path).name}")

    def apply_to_daemon(self) -> None:
        if not self.spec.name or not all(c.isalnum() or c in "-_" for c in self.spec.name):
            QMessageBox.warning(self, "Invalid name",
                                "Theme name must be letters, digits, '-' or '_'.")
            return
        try:
            target_dir = Path.home() / ".config" / "spartacus" / "themes"
            target_dir.mkdir(parents=True, exist_ok=True)
            self.spec.save(target_dir / f"{self.spec.name}.json")
            for widget in self.spec.widgets:
                if widget.kind == "image" and widget.path:
                    src = Path(widget.path)
                    if not src.is_absolute() and self.spec.source_dir:
                        src = Path(self.spec.source_dir) / widget.path
                    if src.is_file():
                        dst = target_dir / widget.path
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src, dst)
            result = self.client.try_call("SetTheme", {"name": self.spec.name})
            if result is not None:
                self.status.setText(f"Daemon now renders '{self.spec.name}' natively. "
                                    "It stays on the panel — no streaming needed.")
            else:
                self.status.setText("Saved theme, but daemon unreachable "
                                    "(is spartacus-daemon running?)")
        except Exception as exc:
            QMessageBox.critical(self, "Apply failed", str(exc))

    def add_widget(self, kind: str) -> None:
        self.push_undo()
        defaults = {
            "panel": Widget(kind="panel", x=140, y=200, w=200, h=100, r=14,
                            fill="#232833"),
            "text": Widget(kind="text", x=240, y=240, size=24, align="center",
                           fill="#FFFFFF", text="CPU {cpu_temp:.0}°C"),
            "ring": Widget(kind="ring", cx=240, cy=240, r=90, thickness=12,
                           track="#313949", fill="#00E5FF", binding="cpu_temp",
                           min=0, max=100, center_text="{cpu_temp:.0}°",
                           center_size=32),
            "bar": Widget(kind="bar", x=120, y=240, w=240, h=10,
                          track="#313949", fill="#00E5FF", binding="cpu_usage"),
            "rect": Widget(kind="rect", x=140, y=220, w=200, h=40, fill="#10141F"),
            "circle": Widget(kind="circle", cx=240, cy=240, r=40, fill="#10141F"),
        }[kind]
        self.spec.add(defaults)
        self.selected = len(self.spec.widgets) - 1
        self.refresh_all()

    def duplicate_widget(self) -> None:
        if self.selected < 0:
            return
        self.push_undo()
        index = self.spec.duplicate(self.selected)
        if index is not None:
            self.selected = index
        self.refresh_all()

    def delete_widget(self) -> None:
        if self.selected < 0:
            return
        self.push_undo()
        self.spec.remove(self.selected)
        self.selected = -1
        self.refresh_all()

    def move_widget(self, delta: int) -> None:
        index = self.selected
        if index < 0:
            return
        target = index + delta
        if not (0 <= target < len(self.spec.widgets)):
            return
        self.push_undo()
        widgets = self.spec.widgets
        widgets[index], widgets[target] = widgets[target], widgets[index]
        self.selected = target
        self.refresh_all()

    # -- selection / refresh -------------------------------------------------------

    def on_list_select(self, row: int) -> None:
        self.selected = row if 0 <= row < len(self.spec.widgets) else -1
        self.canvas.selected = self.selected
        self.canvas.update()
        self.build_inspector()

    def on_canvas_select(self, index: int) -> None:
        self.selected = index
        self.widget_list.blockSignals(True)
        self.widget_list.setCurrentRow(index)
        self.widget_list.blockSignals(False)
        self.build_inspector()

    def on_canvas_moved(self) -> None:
        self.build_inspector()
        self.canvas.update()

    def refresh_all(self) -> None:
        self.widget_list.blockSignals(True)
        self.widget_list.clear()
        for widget in self.spec.widgets:
            self.widget_list.addItem(widget.name)
        if self.selected >= len(self.spec.widgets):
            self.selected = -1
        self.widget_list.setCurrentRow(self.selected)
        self.widget_list.blockSignals(False)
        self.canvas.spec = self.spec
        self.canvas.selected = self.selected
        self.canvas.invalidate()
        self.canvas.update()
        self.build_inspector()

    def refresh_live(self) -> None:
        """Re-render with fresh telemetry values (no undo, no selection loss)."""
        self.canvas.invalidate()
        self.canvas.update()

    # -- inspector -------------------------------------------------------------------

    def build_inspector(self) -> None:
        while self.inspector.count():
            item = self.inspector.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        bg_title = QLabel("Background")
        bg_title.setObjectName("CardTitle")
        self.inspector.addRow(bg_title)
        bg = self.spec.background
        kind_combo = QComboBox()
        kind_combo.addItems(["gradient", "solid"])
        kind_combo.setCurrentText(bg.get("kind", "gradient"))
        kind_combo.currentTextChanged.connect(self.set_bg_kind)
        self.inspector.addRow("Kind", kind_combo)
        top_edit = QLineEditSafe(bg.get("top", "#0B0E1A"))
        top_edit.editingFinished.connect(lambda: self.set_bg_color("top", top_edit.text()))
        self.inspector.addRow("Top/Solid", top_edit)
        if bg.get("kind") != "solid":
            bottom_edit = QLineEditSafe(bg.get("bottom", "#101528"))
            bottom_edit.editingFinished.connect(
                lambda: self.set_bg_color("bottom", bottom_edit.text()))
            self.inspector.addRow("Bottom", bottom_edit)

        if self.selected < 0 or self.selected >= len(self.spec.widgets):
            hint = QLabel("Select a widget to edit its properties.")
            hint.setWordWrap(True)
            self.inspector.addRow(hint)
            return

        widget = self.spec.widgets[self.selected]
        title = QLabel(f"Widget · {widget.kind}")
        title.setObjectName("CardTitle")
        self.inspector.addRow(title)

        numeric = {
            "panel": ["x", "y", "w", "h", "r", "stroke_w"],
            "rect": ["x", "y", "w", "h"],
            "circle": ["cx", "cy", "r"],
            "text": ["x", "y", "size"],
            "ring": ["cx", "cy", "r", "thickness", "min", "max", "start", "sweep",
                     "center_size"],
            "bar": ["x", "y", "w", "h", "r", "min", "max"],
        }.get(widget.kind, [])
        colors = {
            "panel": ["fill", "stroke"],
            "rect": ["fill"],
            "circle": ["fill"],
            "text": ["fill"],
            "ring": ["track", "fill"],
            "bar": ["track", "fill"],
        }.get(widget.kind, [])

        for field_name in numeric:
            spin = QDoubleSpinBox()
            spin.setRange(-2000, 2000)
            spin.setDecimals(1)
            spin.setValue(float(getattr(widget, field_name)))
            spin.valueChanged.connect(
                lambda value, f=field_name: self.set_widget_prop(f, value))
            self.inspector.addRow(field_name, spin)

        for field_name in colors:
            edit = QLineEditSafe(str(getattr(widget, field_name)))
            edit.editingFinished.connect(
                lambda f=field_name, e=edit: self.set_widget_prop(f, e.text()))
            self.inspector.addRow(field_name, edit)

        if widget.kind == "text":
            text_edit = QLineEditSafe(widget.text)
            text_edit.editingFinished.connect(
                lambda: self.set_widget_prop("text", text_edit.text()))
            self.inspector.addRow("text", text_edit)
            align_combo = QComboBox()
            align_combo.addItems(["left", "center", "right"])
            align_combo.setCurrentText(widget.align)
            align_combo.currentTextChanged.connect(
                lambda value: self.set_widget_prop("align", value))
            self.inspector.addRow("align", align_combo)
            bind_combo = self._binding_combo(widget.text)
            bind_combo.currentTextChanged.connect(self.insert_binding)
            self.inspector.addRow("insert binding", bind_combo)

        if widget.kind in ("ring", "bar"):
            bind_combo = self._binding_combo(widget.binding, allow_empty=True)
            bind_combo.currentTextChanged.connect(
                lambda value: self.set_widget_prop("binding", value))
            self.inspector.addRow("binding", bind_combo)

        if widget.kind == "ring":
            center_edit = QLineEditSafe(widget.center_text)
            center_edit.editingFinished.connect(
                lambda: self.set_widget_prop("center_text", center_edit.text()))
            self.inspector.addRow("center_text", center_edit)

    def _binding_combo(self, current: str, allow_empty: bool = False) -> QComboBox:
        combo = QComboBox()
        items = list(BINDINGS)
        if allow_empty:
            items.insert(0, "")
        combo.addItems(items)
        match = re.match(r"\{([a-z_]+)", current or "")
        if match and match.group(1) in items:
            combo.setCurrentText(match.group(1))
        return combo

    def insert_binding(self, key: str) -> None:
        if self.selected < 0 or not key:
            return
        widget = self.spec.widgets[self.selected]
        widget.text = f"{widget.text} {{{key}}}".strip()
        self.push_undo()
        self.refresh_all()

    def set_bg_kind(self, kind: str) -> None:
        self.spec.background["kind"] = kind
        self.canvas.invalidate()
        self.canvas.update()
        self.build_inspector()

    def set_bg_color(self, key: str, value: str) -> None:
        self.spec.background[key] = value
        self.canvas.invalidate()
        self.canvas.update()

    def set_widget_prop(self, name: str, value) -> None:
        if self.selected < 0:
            return
        widget = self.spec.widgets[self.selected]
        if not hasattr(widget, name):
            return
        current = getattr(widget, name)
        if isinstance(current, float):
            value = float(value)
        elif isinstance(current, int):
            value = int(float(value))
        else:
            value = str(value)
        setattr(widget, name, value)
        row = self.widget_list.currentItem()
        if row is not None:
            row.setText(widget.name)
        self.canvas.invalidate()
        self.canvas.update()


class ThemeCanvas(QWidget):
    """Paints the theme spec preview; click selects, drag moves widgets."""

    widget_selected = pyqtSignal(int)
    widget_moved = pyqtSignal()
    edit_committed = pyqtSignal()

    def __init__(self, owner: ThemeStudioPage, parent=None):
        super().__init__(parent)
        self.owner = owner
        self.spec = owner.spec
        self.selected = -1
        self._cache: Image.Image | None = None
        self._drag_index = -1
        self._grab = (0.0, 0.0)

    def invalidate(self) -> None:
        self._cache = None

    def paintEvent(self, event) -> None:
        from PyQt6.QtGui import QPixmap, QPainter

        painter = QPainter(self)
        if self._cache is None:
            self._cache = SpecRenderer(self.spec, self.owner.live_metrics()).render()
        data = self._cache.tobytes()
        image = QImage(data, 480, 480, 480 * 3, QImage.Format.Format_RGB888)
        painter.drawImage(2, 2, image)
        if 0 <= self.selected < len(self.spec.widgets):
            from core.theme.preview import widget_bbox

            x1, y1, x2, y2 = widget_bbox(self.spec.widgets[self.selected])
            pen = QPen(QColor("#00F0FF"))
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawRect(int(x1) + 2, int(y1) + 2,
                             int(x2 - x1), int(y2 - y1))
        painter.end()

    def _canvas_pos(self, event) -> tuple[float, float]:
        pos = event.position()
        return (pos.x() - 2.0, pos.y() - 2.0)

    def mousePressEvent(self, event) -> None:
        from PyQt6.QtCore import QPointF

        x, y = self._canvas_pos(event)
        index = widget_at(self.spec, x, y)
        self._drag_index = index if index is not None else -1
        if index is not None:
            widget = self.spec.widgets[index]
            self._grab = (x - widget.x if widget.kind not in ("ring", "circle") else x - widget.cx,
                          y - widget.y if widget.kind not in ("ring", "circle") else y - widget.cy)
            self.widget_selected.emit(index)
        else:
            self.widget_selected.emit(-1)
        self.update()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_index < 0 or not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        x, y = self._canvas_pos(event)
        widget = self.spec.widgets[self._drag_index]
        if widget.kind in ("ring", "circle"):
            widget.cx = max(-200.0, min(680.0, x - self._grab[0]))
            widget.cy = max(-200.0, min(680.0, y - self._grab[1]))
        else:
            widget.x = max(-200.0, min(680.0, x - self._grab[0]))
            widget.y = max(-200.0, min(680.0, y - self._grab[1]))
        self.invalidate()
        self.widget_moved.emit()

    def mouseReleaseEvent(self, event) -> None:
        if self._drag_index >= 0:
            self.edit_committed.emit()
        self._drag_index = -1


class QLineEditSafe(QLineEdit):
    """QLineEdit that commits on Enter/focus-loss (editingFinished)."""


# --------------------------------------------------------------------------- diagnostics


class DiagnosticsPage(QWidget):
    def __init__(self, model: TelemetryModel, parent=None):
        super().__init__(parent)
        self.model = model
        root = QVBoxLayout(self)
        heading = QLabel("Telemetry Diagnostics")
        heading.setObjectName("BrandTitle")
        root.addWidget(heading)
        controls = QHBoxLayout()
        controls.addStretch()
        export_button = QPushButton("Export diagnostics JSON")
        export_button.clicked.connect(self.export_json)
        controls.addWidget(export_button)
        root.addLayout(controls)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["Metric", "Raw", "Validated", "Quality", "Latency",
             "Samples", "Rejected", "Last reason"])
        self.table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.table, 1)
        model.snapshot_applied.connect(self.refresh)
        self.refresh()

    def refresh(self):
        rows = collect_rows(self.model.pipeline)
        self.table.setRowCount(len(rows))
        for row, item in enumerate(rows):
            values = [item.key, item.raw_value, item.validated_value, item.quality,
                      f"{item.latency_ms:.0f} ms", str(item.samples_total),
                      str(item.rejected_total), item.last_reason]
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))

    def export_json(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export diagnostics",
                                              "spartacus-diagnostics.json",
                                              "JSON (*.json)")
        if not path:
            return
        import json

        rows = [vars(item) for item in collect_rows(self.model.pipeline)]
        rejections = [
            {"timestamp_ms": ts, "key": key, "reason": reason}
            for ts, key, reason in self.model.pipeline.rejection_log
        ]
        Path(path).write_text(json.dumps({
            "sensors": rows,
            "rejection_log": rejections,
            "totals": self.model.pipeline.totals(),
        }, indent=2))



# --------------------------------------------------------------------------- settings


class SettingsPage(QWidget):
    def __init__(self, client: DaemonClient, parent=None):
        super().__init__(parent)
        self.client = client
        root = QVBoxLayout(self)
        heading = QLabel("Settings")
        heading.setObjectName("BrandTitle")
        root.addWidget(heading)
        form = QFormLayout()
        self.brightness = QSpinBox()
        self.brightness.setRange(0, 100)
        self.brightness.setValue(80)
        self.orientation = QComboBox()
        self.orientation.addItems(["Upright 0°", "90° CCW", "180°", "270°"])
        form.addRow("LCD brightness (NVM — applied on change)", self.brightness)
        form.addRow("LCD orientation (NVM)", self.orientation)
        root.addLayout(form)
        apply_button = QPushButton("Apply display settings")
        apply_button.setProperty("accent", "primary")
        apply_button.clicked.connect(self.apply)
        root.addWidget(apply_button)
        self.status = QLabel()
        root.addWidget(self.status)
        root.addStretch()

    def apply(self):
        result = self.client.lcd_set_config(self.orientation.currentIndex(),
                                            self.brightness.value())
        self.status.setText("Display settings accepted by daemon." if result
                            else "Display settings unavailable.")


# --------------------------------------------------------------------------- shell


class MainWindow(QWidget):
    """Modern shell retained under the existing main.py entry point."""

    status_changed = pyqtSignal(dict)

    def __init__(self, ipc_client: DaemonClient):
        super().__init__()
        self.ipc_client = ipc_client
        self.pipeline = TelemetryPipeline.default()
        self.telemetry = TelemetryModel(self.pipeline, self)
        self.worker = TelemetryWorker(ipc_client, 500, self)
        self.worker.snapshot_ready.connect(self.on_status)
        self.worker.connection_changed.connect(self.on_connection)
        self.worker.start()
        self.pages = QStackedWidget()
        self.page_names = ["Overview", "Cooling", "Fans", "Lighting",
                           "LCD Studio", "Telemetry Diagnostics", "Settings"]
        self.build_ui()
        self.telemetry_timer = QTimer(self)
        self.telemetry_timer.timeout.connect(self.telemetry.tick)
        self.telemetry_timer.start(250)

    def build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(210)
        side = QVBoxLayout(sidebar)
        logo = QLabel("SPARTACUS\nCONTROL CENTER")
        logo.setObjectName("BrandTitle")
        side.addWidget(logo)
        self.nav = QListWidget()
        self.nav.setObjectName("Navigation")
        for name in self.page_names:
            self.nav.addItem(name)
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.nav.setCurrentRow(0)
        side.addWidget(self.nav, 1)
        self.footer = QLabel("")
        self.footer.setObjectName("DeviceName")
        side.addWidget(self.footer)
        root.addWidget(sidebar)

        content = QVBoxLayout()
        top = QFrame()
        top.setObjectName("TopBar")
        top_layout = QHBoxLayout(top)
        self.device = QLabel("SPARTACUS · Active Device")
        self.device.setObjectName("DeviceName")
        self.connection = QLabel("● Disconnected")
        self.connection.setProperty("pill", "disconnected")
        self.daemon_pill = QLabel("Daemon Active")
        self.daemon_pill.setProperty("pill", "connected")
        self.pipeline_status = QLabel("Pipeline STALE")
        top_layout.addWidget(self.device)
        top_layout.addStretch()
        top_layout.addWidget(self.connection)
        top_layout.addWidget(self.daemon_pill)
        top_layout.addWidget(self.pipeline_status)
        content.addWidget(top)

        studio_page = ThemeStudioPage(self.ipc_client, self.telemetry)
        pages = [
            OverviewPage(self.telemetry),
            ChannelSlidersPage(self.ipc_client, self.telemetry, "Cooling", mode="sliders"),
            ChannelSlidersPage(self.ipc_client, self.telemetry, "Fans", mode="curves"),
            LightingPage(self.ipc_client),
            studio_page,
            DiagnosticsPage(self.telemetry),
            SettingsPage(self.ipc_client),
        ]
        for page in pages:
            self.pages.addWidget(page)
        self.studio = studio_page
        content.addWidget(self.pages, 1)
        root.addLayout(content, 1)

        extra_style = """
        QListWidget#Navigation { border: none; background: transparent; }
        QListWidget#Navigation::item { padding: 12px 14px; color: #9AA3AD; }
        QListWidget#Navigation::item:selected { color: #00F0FF;
            border-left: 3px solid #00F0FF; background: #1B1E23; }
        """
        existing = self.styleSheet()
        self.setStyleSheet(existing + extra_style)

    def on_status(self, status: dict):
        self.telemetry.ingest_snapshot(status)
        self.status_changed.emit(status)
        live = self.telemetry.is_live()
        self.pipeline_status.setText("Pipeline LIVE" if live else "Pipeline STALE")
        self.pipeline_status.setProperty(
            "pill", "connected" if live else "disconnected")
        self.pipeline_status.style().unpolish(self.pipeline_status)
        self.pipeline_status.style().polish(self.pipeline_status)
        device = status.get("device_name") or "SPARTACUS"
        self.device.setText(f"SPARTACUS · {device}")

    def on_connection(self, connected: bool):
        text = "● Connected" if connected else "● Disconnected"
        state = "connected" if connected else "disconnected"
        self.connection.setText(text)
        self.connection.setProperty("pill", state)
        self.connection.style().unpolish(self.connection)
        self.connection.style().polish(self.connection)
        if not connected:
            self.pipeline_status.setText("Pipeline STALE")

    def update_status(self, status: dict):
        self.on_status(status)

    def shutdown(self):
        self.telemetry_timer.stop()
        self.worker.stop()
        self.ipc_client.close()

    def closeEvent(self, event):
        self.shutdown()
        event.accept()
