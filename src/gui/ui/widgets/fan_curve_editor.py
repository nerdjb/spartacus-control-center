"""Interactive fan curve editor: temperature (x) -> PWM % (y).

Drag points to reshape the curve; the pump channel shows the daemon-enforced
40% floor as a shaded forbidden band. The live temperature cursor previews the
duty the daemon's interpolation will command right now.
"""

from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from core.hardware.curves import PUMP_DUTY_FLOOR, evaluate_curve

TEMP_MIN, TEMP_MAX = 20, 95


class FanCurveEditor(QWidget):
    curve_edited = pyqtSignal(list)          # sanitized [(temp, duty), ...]
    points_dragged = pyqtSignal()            # during drag (no commit yet)

    def __init__(self, channel: str = "pump", parent=None):
        super().__init__(parent)
        self.channel = channel
        self.points: list[tuple[float, float]] = [(30, 30), (50, 60), (70, 100)]
        self.current_temp: float | None = None
        self._drag_index: int | None = None
        self.setMinimumSize(420, 300)
        self.setMouseTracking(True)

    # -- data ------------------------------------------------------------------

    def set_channel(self, channel: str, points: list[tuple[float, float]]) -> None:
        self.channel = channel
        self.points = sorted(points)
        self.current_temp = None
        self.update()

    def set_points(self, points: list[tuple[float, float]]) -> None:
        self.points = sorted(points)
        self.update()

    def set_live_temperature(self, temp: float | None) -> None:
        if temp != self.current_temp:
            self.current_temp = temp
            self.update()

    def target_duty(self) -> float | None:
        if self.current_temp is None:
            return None
        return evaluate_curve(self.points, self.current_temp)

    # -- coordinate mapping -------------------------------------------------------

    def _plot_rect(self):
        margin_left, margin_right, margin_top, margin_bottom = 44, 16, 14, 30
        return (margin_left, margin_top,
                self.width() - margin_right - margin_left,
                self.height() - margin_top - margin_bottom)

    def _to_screen(self, temp: float, duty: float) -> QPointF:
        x0, y0, w, h = self._plot_rect()
        fx = (temp - TEMP_MIN) / (TEMP_MAX - TEMP_MIN)
        fy = duty / 100.0
        return QPointF(x0 + fx * w, y0 + (1.0 - fy) * h)

    def _to_curve(self, x: float, y: float) -> tuple[float, float]:
        x0, y0, w, h = self._plot_rect()
        fx = max(0.0, min(1.0, (x - x0) / max(1.0, w)))
        fy = 1.0 - max(0.0, min(1.0, (y - y0) / max(1.0, h)))
        return TEMP_MIN + fx * (TEMP_MAX - TEMP_MIN), fy * 100.0

    # -- painting ---------------------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#16191E"))
        painter.setRenderHints(QPainter.RenderHint.Antialiasing)
        x0, y0, w, h = self._plot_rect()

        floor = PUMP_DUTY_FLOOR if self.channel == "pump" else 0
        if floor:
            top = self._to_screen(TEMP_MIN, 100).y()
            bottom = self._to_screen(TEMP_MIN, floor).y()
            painter.fillRect(int(x0), int(top), int(w), int(bottom - top),
                             QColor(255, 77, 94, 26))
            painter.setPen(QPen(QColor("#FF4D5E"), 1, Qt.PenStyle.DashLine))
            painter.drawLine(int(x0), int(bottom), int(x0 + w), int(bottom))
            painter.setPen(QColor("#FF4D5E"))
            painter.drawText(int(x0) + 4, int(bottom) - 5,
                             f"daemon-enforced {floor}% floor")

        painter.setPen(QPen(QColor("#2A2E35"), 1))
        for duty in range(0, 101, 25):
            point = self._to_screen(TEMP_MIN, duty)
            painter.drawLine(int(x0), int(point.y()), int(x0 + w), int(point.y()))
            painter.setPen(QColor("#5C6470"))
            painter.drawText(4, int(point.y()) + 4, f"{duty}%")
            painter.setPen(QPen(QColor("#2A2E35"), 1))
        for temp in range(TEMP_MIN, TEMP_MAX + 1, 15):
            point = self._to_screen(temp, 0)
            painter.drawLine(int(point.x()), int(y0), int(point.x()), int(y0 + h))
            painter.drawText(int(point.x()) - 10, int(y0 + h + 18), f"{temp}°C")

        pen_color = {"pump": "#00F0FF", "aio": "#0066FF",
                     "ext1": "#8A2BE2", "ext2": "#00FF66"}.get(self.channel, "#FFFFFF")
        painter.setPen(QPen(QColor(pen_color), 2))
        screen_points = [self._to_screen(t, d) for t, d in sorted(self.points)]
        for (t0, d0), (t1, d1) in zip(sorted(self.points), sorted(self.points)[1:]):
            p0, p1 = self._to_screen(t0, d0), self._to_screen(t1, d1)
            painter.drawLine(p0, p1)
        for index, point in enumerate(screen_points):
            dragging = index == self._drag_index
            radius = 7 if dragging else 5
            painter.setBrush(QColor(pen_color))
            painter.drawEllipse(point, radius, radius)

        if self.current_temp is not None:
            cursor_x = self._to_screen(self.current_temp, 0).x()
            painter.setPen(QPen(QColor("#FFB454"), 1, Qt.PenStyle.DotLine))
            painter.drawLine(int(cursor_x), int(y0), int(cursor_x), int(y0 + h))
            duty = self.target_duty()
            if duty is not None:
                dot = self._to_screen(self.current_temp, duty)
                painter.setBrush(QColor("#FFB454"))
                painter.drawEllipse(dot, 4, 4)
                painter.setPen(QColor("#FFB454"))
                painter.drawText(int(dot.x()) + 8, int(dot.y()) - 8,
                                 f"{self.current_temp:.0f}°C → {duty:.0f}%")

    # -- interaction ----------------------------------------------------------------------

    def _hit_index(self, pos: QPointF) -> int | None:
        for index, (temp, duty) in enumerate(self.points):
            point = self._to_screen(temp, duty)
            if math.hypot(point.x() - pos.x(), point.y() - pos.y()) <= 12:
                return index
        return None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_index = self._hit_index(event.position())
        elif event.button() == Qt.MouseButton.RightButton and len(self.points) > 2:
            index = self._hit_index(event.position())
            if index is not None:
                self.points.pop(index)
                self._commit()

    def mouseDoubleClickEvent(self, event):
        temp, duty = self._to_curve(event.position().x(), event.position().y())
        self.points.append((round(temp), round(duty)))
        self.points.sort()
        self._commit()

    def mouseMoveEvent(self, event):
        if self._drag_index is None or not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        temp, duty = self._to_curve(event.position().x(), event.position().y())
        self.points[self._drag_index] = (round(temp), round(max(0.0, min(100.0, duty))))
        self.points.sort()
        self._drag_index = self.points.index(
            next(p for p in self.points if abs(p[0] - round(temp)) < 1e-9))
        self.update()
        self.points_dragged.emit()

    def mouseReleaseEvent(self, event):
        if self._drag_index is not None:
            self._drag_index = None
            self._commit()

    def _commit(self) -> None:
        self.points.sort()
        self.update()
        self.curve_edited.emit([(int(t), int(d)) for t, d in self.points])
