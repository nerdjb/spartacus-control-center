"""Interactive editor for 480x480 Spartacus LCD themes."""

from pathlib import Path

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QColorDialog, QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSpinBox,
    QVBoxLayout, QWidget,
)

from models.presets import ThemePresets
from models.renderer import ThemeRenderer
from models.theme import Color, GaugeElement, Position, TextElement, Theme


class LCDCanvas(QWidget):
    """Preview canvas whose selected text and gauge elements can be dragged."""

    element_moved = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.theme = None
        self.renderer = None
        self.preview = None
        self.telemetry = {"cpu_temp": 52.5, "gpu_temp": 48.0, "pump_rpm": 2450}
        self.selected_index = -1
        self.drag_offset = QPoint()
        self.setFixedSize(480, 480)

    def set_theme(self, theme: Theme):
        self.theme = theme
        self.renderer = ThemeRenderer(theme)
        self.update_preview()

    def set_selected_index(self, index: int):
        self.selected_index = index
        self.update()

    def update_telemetry(self, data: dict):
        self.telemetry.update(data)
        self.update_preview()

    def update_preview(self):
        if not self.renderer:
            return
        self.renderer.set_telemetry(self.telemetry)
        image = self.renderer.render()
        self.preview = QPixmap.fromImage(QImage(
            image.tobytes("raw", "RGB"), 480, 480, 480 * 3,
            QImage.Format.Format_RGB888,
        ).copy())
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        if self.preview:
            painter.drawPixmap(0, 0, self.preview)
        if self.theme and 0 <= self.selected_index < len(self.theme.elements):
            element = self.theme.elements[self.selected_index]
            if getattr(element, "position", None):
                position = element.position
                painter.setPen(QColor(255, 255, 255))
                painter.drawRect(position.x - 6, position.y - 6, 12, 12)

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or not self.theme:
            return
        point = event.position().toPoint()
        candidates = []
        for index, element in enumerate(self.theme.elements):
            position = getattr(element, "position", None)
            if position:
                distance = (position.x - point.x()) ** 2 + (position.y - point.y()) ** 2
                candidates.append((distance, index, position))
        if candidates:
            distance, index, position = min(candidates)
            if distance <= 50 ** 2:
                self.selected_index = index
                self.drag_offset = point - QPoint(position.x, position.y)
                self.element_moved.emit(index)

    def mouseMoveEvent(self, event):
        if not self.theme or self.selected_index < 0:
            return
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        element = self.theme.elements[self.selected_index]
        if not getattr(element, "position", None):
            return
        point = event.position().toPoint() - self.drag_offset
        element.position.x = max(0, min(480, point.x()))
        element.position.y = max(0, min(480, point.y()))
        self.update_preview()
        self.element_moved.emit(self.selected_index)


class ThemeDesignerWidget(QWidget):
    """Theme editor with preset selection, persistence, and drag placement."""

    theme_changed = pyqtSignal(Theme)

    def __init__(self, ipc_client=None, parent=None):
        super().__init__(parent)
        self.ipc_client = ipc_client
        self.themes = ThemePresets.get_all_themes()
        self.current_theme = None
        self.build_ui()
        self.theme_combo.setCurrentIndex(0)
        self.select_theme(self.theme_combo.currentText())

    def build_ui(self):
        layout = QHBoxLayout(self)
        self.canvas = LCDCanvas()
        layout.addWidget(self.canvas)

        controls = QVBoxLayout()
        self.theme_combo = QComboBox()
        self.theme_combo.addItems([name.title() for name in self.themes])
        self.theme_combo.currentTextChanged.connect(self.select_theme)
        controls.addWidget(QLabel("Preset"))
        controls.addWidget(self.theme_combo)

        self.element_list = QListWidget()
        self.element_list.currentRowChanged.connect(self.select_element)
        controls.addWidget(QLabel("Elements"))
        controls.addWidget(self.element_list)

        form = QFormLayout()
        self.x_spin = QSpinBox(); self.x_spin.setRange(0, 480)
        self.y_spin = QSpinBox(); self.y_spin.setRange(0, 480)
        self.font_spin = QSpinBox(); self.font_spin.setRange(6, 96)
        for control in (self.x_spin, self.y_spin, self.font_spin):
            control.valueChanged.connect(self.update_element)
        form.addRow("X", self.x_spin); form.addRow("Y", self.y_spin)
        form.addRow("Font", self.font_spin)
        controls.addLayout(form)

        color_button = QPushButton("Element color")
        color_button.clicked.connect(self.choose_color)
        controls.addWidget(color_button)

        buttons = QHBoxLayout()
        save_button = QPushButton("Save")
        save_button.clicked.connect(self.save_theme)
        load_button = QPushButton("Load")
        load_button.clicked.connect(self.load_theme)
        buttons.addWidget(save_button); buttons.addWidget(load_button)
        controls.addLayout(buttons)
        controls.addStretch()
        layout.addLayout(controls)
        self.canvas.element_moved.connect(self.select_element)

    def select_theme(self, display_name: str):
        key = display_name.lower().replace(" ", "_")
        if key not in self.themes:
            return
        self.current_theme = self.themes[key]
        self.canvas.set_theme(self.current_theme)
        self.populate_elements()
        self.theme_changed.emit(self.current_theme)

    def populate_elements(self):
        self.element_list.clear()
        for element in self.current_theme.elements:
            self.element_list.addItem(QListWidgetItem(element.element_id))
        if self.current_theme.elements:
            self.element_list.setCurrentRow(0)

    def select_element(self, index: int):
        if not self.current_theme or not 0 <= index < len(self.current_theme.elements):
            return
        self.element_list.blockSignals(True)
        self.element_list.setCurrentRow(index)
        self.element_list.blockSignals(False)
        element = self.current_theme.elements[index]
        if getattr(element, "position", None):
            self.x_spin.setValue(element.position.x); self.y_spin.setValue(element.position.y)
        if isinstance(element, TextElement):
            self.font_spin.setValue(element.font_size)
        self.canvas.set_selected_index(index)

    def update_element(self):
        index = self.element_list.currentRow()
        if not self.current_theme or not 0 <= index < len(self.current_theme.elements):
            return
        element = self.current_theme.elements[index]
        if getattr(element, "position", None):
            element.position = Position(self.x_spin.value(), self.y_spin.value())
        if isinstance(element, TextElement):
            element.font_size = self.font_spin.value()
        self.canvas.update_preview()

    def choose_color(self):
        index = self.element_list.currentRow()
        if not self.current_theme or not 0 <= index < len(self.current_theme.elements):
            return
        color = QColorDialog.getColor()
        if not color.isValid():
            return
        element = self.current_theme.elements[index]
        if isinstance(element, TextElement):
            element.color = Color(color.red(), color.green(), color.blue())
        elif isinstance(element, GaugeElement):
            element.color_max = Color(color.red(), color.green(), color.blue())
        self.canvas.update_preview()

    def save_theme(self):
        if not self.current_theme:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save theme", "", "Theme JSON (*.json)")
        if path:
            self.current_theme.save(Path(path))

    def load_theme(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load theme", "", "Theme JSON (*.json)")
        if not path:
            return
        try:
            self.current_theme = Theme.load(Path(path))
            self.canvas.set_theme(self.current_theme)
            self.populate_elements()
            self.theme_changed.emit(self.current_theme)
        except (OSError, ValueError, TypeError) as error:
            QMessageBox.critical(self, "Theme error", str(error))

    def update_telemetry(self, telemetry: dict):
        self.canvas.update_telemetry(telemetry)


class ThemeDesigner(ThemeDesignerWidget):
    """Compatibility alias for existing imports."""


class CurveEditor(QWidget):
    """Compatibility widget reserved for fan curve editing."""


class TrayIcon(QWidget):
    """Compatibility widget reserved for tray integration."""
