"""SPARTACUS Control Center v2 application shell and functional pages."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QSlider, QSpinBox, QStackedWidget, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from core.hardware.curves import apply_pump_floor, default_curve, sanitize_points
from core.ipc.client import DaemonClient, TelemetryWorker
from core.lcd.exporter import LcdExporter
from core.lcd.live import LiveModeController
from core.lcd.model import ImageElement, LcdLayout, RingElement, ShapeElement, TextElement
from core.lcd.qdt.container import extract
from core.lcd.qdt.conversion import qdt_to_layout
from core.lcd.qdt.parser import QdtParser
from core.lcd.renderer import LcdRenderer
from core.lcd.scene import LcdCanvas
from core.lcd.templates import get_all
from core.lcd.undo import UndoStack
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


class LcdStudioPage(QWidget):
    ZOOMS = ["25%", "50%", "75%", "100%", "150%", "200%"]
    FPS_OPTIONS = [15, 30, 60]

    def __init__(self, client: DaemonClient, model: TelemetryModel, parent=None):
        super().__init__(parent)
        self.client, self.model = client, model
        self.layout_model = next(iter(get_all().values()))
        self.undo_stack = UndoStack()
        self.canvas = LcdCanvas(self.layout_model, model.pipeline, self)
        self.live = LiveModeController(client, self.layout_model, model.pipeline, self)
        self._build_ui()

        shortcuts = {
            "Ctrl+Z": self.undo, "Ctrl+Y": self.redo, "Ctrl+Shift+Z": self.redo,
            "Ctrl+A": self.canvas.select_all,
        }
        for sequence, handler in shortcuts.items():
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(handler)

        self.canvas.edit_committed.connect(self.undo_stack.push)
        self.canvas.selection_changed.connect(self.on_selection_changed)
        self.refresh_layers()
        self.build_inspector([])

    # -- UI construction ------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        brand = QLabel("LCD STUDIO")
        brand.setObjectName("CardTitle")
        toolbar.addWidget(brand)
        self.preset_combo = QComboBox()
        self.preset_combo.addItems([name.replace("_", " ").title() for name in get_all()])
        self.preset_combo.currentTextChanged.connect(self.load_preset)
        toolbar.addWidget(self.preset_combo)
        self.zoom_combo = QComboBox()
        self.zoom_combo.addItems(self.ZOOMS)
        self.zoom_combo.setCurrentText("100%")
        self.zoom_combo.currentTextChanged.connect(self.set_zoom)
        toolbar.addWidget(self.zoom_combo)
        self.mask_check = QCheckBox("Circular mask")
        self.mask_check.setChecked(True)
        self.mask_check.toggled.connect(self.toggle_mask)
        self.grid_check = QCheckBox("Grid")
        self.grid_check.toggled.connect(self.toggle_grid)
        self.snap_check = QCheckBox("Snap")
        self.snap_check.toggled.connect(lambda value: setattr(self.canvas, "snap_grid", value))
        group_button = QPushButton("Group")
        group_button.clicked.connect(self.commit_then(self.canvas.group_selection))
        ungroup_button = QPushButton("Ungroup")
        ungroup_button.clicked.connect(self.commit_then(self.canvas.ungroup_selection))
        for widget in (self.mask_check, self.grid_check, self.snap_check,
                       group_button, ungroup_button):
            toolbar.addWidget(widget)
        toolbar.addStretch()
        self.fps_combo = QComboBox()
        self.fps_combo.addItems([f"{fps} FPS" for fps in self.FPS_OPTIONS])
        self.fps_combo.setCurrentText("30 FPS")
        self.fps_combo.currentTextChanged.connect(self.change_fps)
        self.live_button = QPushButton("START LIVE")
        self.live_button.clicked.connect(self.toggle_live)
        self.live_stats = QLabel("live: idle")
        toolbar.addWidget(self.fps_combo)
        toolbar.addWidget(self.live_button)
        toolbar.addWidget(self.live_stats)
        preview_button = QPushButton("Realistic Preview")
        preview_button.clicked.connect(self.realistic_preview)
        send_button = QPushButton("SEND TO LCD")
        send_button.setProperty("accent", "primary")
        send_button.clicked.connect(self.send_to_lcd)
        toolbar.addWidget(preview_button)
        toolbar.addWidget(send_button)
        root.addLayout(toolbar)

        body = QHBoxLayout()
        body.addWidget(self.canvas, 1)

        panel = QVBoxLayout()
        panel.addWidget(QLabel("Layers"))
        self.layer_list = QListWidget()
        self.layer_list.currentRowChanged.connect(self.on_layer_row)
        panel.addWidget(self.layer_list, 1)

        layer_buttons = QGridLayout()
        actions = [
            ("+ Text", self.push_undo_and(self.add_text)),
            ("+ Ring", self.push_undo_and(self.add_ring)),
            ("Delete", self.push_undo_and(self.delete_selected)),
            ("Dup", self.push_undo_and(self.duplicate_selected)),
            ("Front", lambda: self.reorder_selected("front")),
            ("Back", lambda: self.reorder_selected("back")),
        ]
        for index, (label, handler) in enumerate(actions):
            button = QPushButton(label)
            button.clicked.connect(handler)
            layer_buttons.addWidget(button, index // 3, index % 3)
        panel.addLayout(layer_buttons)

        inspector_title = QLabel("Inspector")
        inspector_title.setObjectName("CardTitle")
        panel.addWidget(inspector_title)
        self.inspector_form = QFormLayout()
        self.inspector_form.setVerticalSpacing(4)
        panel.addLayout(self.inspector_form)
        save_button = QPushButton("Save layout")
        save_button.clicked.connect(self.save_layout)
        load_button = QPushButton("Load .qdt / layout")
        load_button.clicked.connect(self.load_layout)
        panel.addWidget(save_button)
        panel.addWidget(load_button)
        self.status = QLabel("Editor mode · 480×480 · Ctrl+Z/Y undo/redo")
        self.status.setWordWrap(True)
        panel.addWidget(self.status)
        body.addLayout(panel)
        root.addLayout(body)

    # -- helpers ------------------------------------------------------------

    def push_undo_and(self, handler):
        def wrapped():
            self.undo_stack.push(deepcopy(self.layout_model.to_dict()))
            handler()
        return wrapped

    def commit_then(self, handler):
        def wrapped():
            snapshot = deepcopy(self.layout_model.to_dict())
            handler()
            self.undo_stack.push(snapshot)
            self.refresh_layers()
        return wrapped

    def undo(self):
        restored = self.undo_stack.undo(deepcopy(self.layout_model.to_dict()))
        if restored:
            self.layout_model = LcdLayout.from_dict(restored)
            self.canvas.layout = self.layout_model
            self.live.layout = self.layout_model
            self.canvas.clear_selection()
            self.canvas.refresh()
            self.refresh_layers()

    def redo(self):
        restored = self.undo_stack.redo(deepcopy(self.layout_model.to_dict()))
        if restored:
            self.layout_model = LcdLayout.from_dict(restored)
            self.canvas.layout = self.layout_model
            self.live.layout = self.layout_model
            self.canvas.clear_selection()
            self.canvas.refresh()
            self.refresh_layers()

    # -- canvas interactions ---------------------------------------------------

    def set_zoom(self, text):
        factor = int(text[:-1]) / 100
        self.canvas.resetTransform()
        self.canvas.scale(factor, factor)

    def toggle_mask(self, value):
        self.canvas.mask_enabled = value
        self.canvas.refresh()

    def toggle_grid(self, value):
        self.canvas.show_grid = value
        self.canvas.refresh()

    def refresh_layers(self):
        self.layer_list.blockSignals(True)
        self.layer_list.clear()
        for element in reversed(self.layout_model.elements):   # top layer first
            state = "" if element.visible else "  (hidden)"
            lock = " 🔒" if getattr(element, "locked", False) else ""
            item = QListWidgetItem(f"{element.name} [{element.element_type.value}]{state}{lock}")
            item.setData(Qt.ItemDataRole.UserRole, element.id)
            self.layer_list.addItem(item)
        self.layer_list.blockSignals(False)

    def on_layer_row(self, row):
        if row < 0:
            return
        element = list(reversed(self.layout_model.elements))[row]
        self.canvas.set_selection([element.id])

    def on_selection_changed(self, ids: list):
        self.undo_stack_for_selection = deepcopy(self.layout_model.to_dict())
        self.build_inspector(ids)
        self.refresh_layers()

    def selected_element(self):
        ids = self.canvas.selection
        return self.layout_model.get(ids[0]) if len(ids) == 1 else None

    # -- inspector ---------------------------------------------------------------

    def build_inspector(self, ids: list):
        while self.inspector_form.rowCount():
            self.inspector_form.removeRow(0)
        if len(ids) > 1:
            label = QLabel(f"{len(ids)} elements selected")
            self.inspector_form.addRow(label)
            return
        element = self.selected_element()
        if element is None:
            self.inspector_form.addRow(QLabel("No selection"))
            return

        def spin(attr, low, high, step=1, is_float=False):
            if is_float:
                box = QDoubleSpinBox()
                box.setDecimals(1)
                box.setSingleStep(0.5)
            else:
                box = QSpinBox()
            box.setRange(low, high)
            raw = float(getattr(element, attr))
            try:
                box.setValue(raw)
            except TypeError:
                box.setValue(int(round(raw)))
            box.valueChanged.connect(lambda v, a=attr: self.apply_property(a, v))
            return box

        form = self.inspector_form
        name_box = QLineEditSafe(str(element.name))
        name_box.editingFinished.connect(
            lambda: self.apply_property("name", name_box.text()))
        form.addRow("Name", name_box)
        form.addRow("X", spin("x", -40, 520, is_float=True))
        form.addRow("Y", spin("y", -40, 520, is_float=True))
        form.addRow("Rotation°", spin("rotation_deg", -180, 180, is_float=True))
        form.addRow("Opacity", spin("opacity", 0.0, 1.0, is_float=True))

        if isinstance(element, TextElement):
            text_box = QLineEditSafe(element.text)
            text_box.editingFinished.connect(
                lambda: self.apply_property("text", text_box.text()))
            form.addRow("Content", text_box)
            form.addRow("Font size", spin("font_size", 4, 200))
            bold = QCheckBox()
            bold.setChecked(element.bold)
            bold.toggled.connect(lambda v: self.apply_property("bold", bool(v)))
            form.addRow("Bold", bold)
            hint = QLabel("Bindings: {" + "} {".join(BINDABLE_KEYS[:5]) + "} …")
            hint.setWordWrap(True)
            form.addRow(hint)
        elif isinstance(element, RingElement):
            binding = QComboBox()
            binding.addItem("")     # static track only
            binding.addItems(BINDABLE_KEYS)
            binding.setCurrentText(element.binding_key)
            binding.currentTextChanged.connect(
                lambda v: self.apply_property("binding_key", str(v)))
            form.addRow("Binding", binding)
            form.addRow("Min", spin("min_value", -1000, 100000, is_float=True))
            form.addRow("Max", spin("max_value", -999, 100001, is_float=True))
            form.addRow("Radius", spin("radius", 10, 400, is_float=True))
            form.addRow("Thickness", spin("thickness", 1, 80, is_float=True))
        elif isinstance(element, ImageElement):
            path_box = QLineEditSafe(element.asset_path)
            path_box.editingFinished.connect(
                lambda: self.apply_property("asset_path", path_box.text()))
            form.addRow("Image path", path_box)
            browse = QPushButton("Browse…")
            browse.clicked.connect(self.browse_image)
            form.addRow("", browse)
            keep = QCheckBox()
            keep.setChecked(element.keep_aspect)
            keep.toggled.connect(lambda v: self.apply_property("keep_aspect", bool(v)))
            form.addRow("Keep aspect", keep)
        elif isinstance(element, ShapeElement):
            form.addRow("Width", spin("width", 2, 480, is_float=True))
            form.addRow("Height", spin("height", 2, 480, is_float=True))

    def apply_property(self, attr, value):
        element = self.selected_element()
        if element is None:
            return
        setattr(element, attr, value)
        self.canvas.refresh()

    def browse_image(self):
        element = self.selected_element()
        if not isinstance(element, ImageElement):
            return
        path, _ = QFileDialog.getOpenFileName(self, "Import image", "",
                                              "Images (*.png *.jpg *.jpeg *.bmp *.svg)")
        if path:
            element.asset_path = path
            self.canvas.refresh()
            self.build_inspector(self.canvas.selection)

    # -- element ops -------------------------------------------------------------

    def add_text(self):
        self.layout_model.add(TextElement(id=f"text_{len(self.layout_model.elements)}",
                                          name="CPU telemetry", x=240, y=240,
                                          text="CPU {cpu_temp}°C", font_size=28))
        self.after_mutation()

    def add_ring(self):
        self.layout_model.add(RingElement(id=f"ring_{len(self.layout_model.elements)}",
                                          name="CPU ring", x=240, y=240,
                                          binding_key="cpu_temp",
                                          min_value=20, max_value=95))
        self.after_mutation()

    def delete_selected(self):
        for element_id in list(self.canvas.selection):
            self.layout_model.remove(element_id)
        self.canvas.clear_selection()
        self.after_mutation()

    def duplicate_selected(self):
        for element_id in list(self.canvas.selection):
            self.layout_model.duplicate(element_id)
        self.after_mutation()

    def reorder_selected(self, mode: str):
        for element_id in list(self.canvas.selection):
            self.layout_model.reorder(element_id, mode)
        self.after_mutation()

    def after_mutation(self):
        self.canvas.refresh()
        self.refresh_layers()

    # -- persistence / presets ------------------------------------------------------

    def load_preset(self, name):
        key = name.lower().replace(" ", "_")
        layouts = get_all()
        if key in layouts and key + "_x" != self.layout_model.name.lower().replace(" ", "_") + "_x":
            self.undo_stack.push(deepcopy(self.layout_model.to_dict()))
            self.layout_model = layouts[key]
            self.canvas.layout = self.layout_model
            self.live.layout = self.layout_model
            self.canvas.clear_selection()
            self.canvas.refresh()
            self.refresh_layers()

    def save_layout(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save layout", "",
                                              "SPARTACUS Layout (*.slayout.json)")
        if path:
            self.layout_model.save(path)
            self.status.setText(f"Saved {Path(path).name}")

    def load_layout(self):
        path, selected = QFileDialog.getOpenFileName(
            self, "Load layout or QDT theme", "", "Layouts/QDT (*.json *.qdt)")
        if not path:
            return
        try:
            self.undo_stack.push(deepcopy(self.layout_model.to_dict()))
            notes: list[str] = []
            if path.lower().endswith(".qdt"):
                parser = QdtParser(Path.home() / ".cache" / "spartacus" / "qdt")
                theme = parser.parse(extract(Path(path).read_bytes()), Path(path).name)
                asset_paths = parser.export_assets(theme)
                self.layout_model, notes = qdt_to_layout(theme, asset_paths)
            else:
                self.layout_model = LcdLayout.load(path)
            self.canvas.layout = self.layout_model
            self.live.layout = self.layout_model
            self.canvas.clear_selection()
            self.canvas.refresh()
            self.refresh_layers()
            self.status.setText("QDT imported · " + f"{len(notes)} notes"
                                if notes else "Layout loaded")
            if notes:
                QMessageBox.information(self, "QDT import notes", "\n".join(notes[:12]))
        except Exception as exc:
            QMessageBox.critical(self, "Load failed", str(exc))

    # -- live mode / send -------------------------------------------------------------

    def change_fps(self, text):
        self.live.fps = int(text.split()[0])
        if self.live.running:
            self.live.stop()
            self.live.start()

    def toggle_live(self):
        if self.live.running:
            self.live.stop()
            self.live_button.setText("START LIVE")
        else:
            self.live.start()
            self.live_button.setText("STOP LIVE")
        self.live.stats_changed.connect(
            lambda sent, dropped, error:
            self.live_stats.setText(f"live: {sent} sent · {dropped} dropped"
                                    + (f" · {error}" if error else "")))

    def realistic_preview(self):
        renderer = LcdRenderer(self.layout_model, self.model.pipeline)
        image = renderer.render(realistic=True, mask=False)
        import io

        from PyQt6.QtGui import QPixmap

        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        pixmap = QPixmap()
        pixmap.loadFromData(buffer.getvalue())
        self.canvas.scene.clear()
        self.canvas.scene.addPixmap(pixmap)
        self.status.setText("Realistic preview rendered")

    def send_to_lcd(self):
        renderer = LcdRenderer(self.layout_model, self.model.pipeline)
        result = LcdExporter(self.client).render_and_send(renderer)
        if result.accepted:
            self.status.setText(f"LCD accepted frame ({result.jpeg_bytes} B, "
                                f"sum16={result.checksum16:#06x})")
        else:
            self.status.setText(f"LCD send failed: {result.error}")


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
        self.send_lcd = QPushButton("SEND TO LCD")
        self.send_lcd.setProperty("accent", "primary")
        self.send_lcd.clicked.connect(self.send_current_lcd)
        top_layout.addWidget(self.device)
        top_layout.addStretch()
        top_layout.addWidget(self.connection)
        top_layout.addWidget(self.daemon_pill)
        top_layout.addWidget(self.pipeline_status)
        top_layout.addWidget(self.send_lcd)
        content.addWidget(top)

        studio_page = LcdStudioPage(self.ipc_client, self.telemetry)
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

    def send_current_lcd(self):
        self.nav.setCurrentRow(self.page_names.index("LCD Studio"))
        self.studio.send_to_lcd()

    def update_status(self, status: dict):
        self.on_status(status)

    def shutdown(self):
        self.telemetry_timer.stop()
        self.studio.live.stop()
        self.worker.stop()
        self.ipc_client.close()

    def closeEvent(self, event):
        self.shutdown()
        event.accept()
