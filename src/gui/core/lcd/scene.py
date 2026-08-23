"""Interactive 480x480 LCD Studio canvas.

Selection model: click selects, Shift+click toggles membership, drag on empty
space rubber-band-selects. Ctrl+G groups the selection (moves together),
Ctrl+Shift+U ungroups. While dragging, element centers snap to the canvas
center lines with visible guides.
"""

from __future__ import annotations

import io

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsView, QRubberBand

from core.lcd.model import GroupElement, LcdLayout
from core.lcd.renderer import LcdRenderer
from core.telemetry.pipeline import TelemetryPipeline

_CENTER_SNAP_PX = 5.0


class LcdCanvas(QGraphicsView):
    layout_changed = pyqtSignal()
    selection_changed = pyqtSignal(list)
    edit_committed = pyqtSignal(dict)  # pre-mutation snapshot for the undo stack

    def __init__(self, layout: LcdLayout, pipeline: TelemetryPipeline, parent=None):
        self.scene = QGraphicsScene(0, 0, 480, 480)
        super().__init__(self.scene, parent)
        self.layout = layout
        self.pipeline = pipeline
        self.show_grid = False
        self.snap_grid = False
        self.mask_enabled = layout.round_mask
        self.selection: list[str] = []
        self._dragging_ids: list[str] = []
        self._drag_origin: QPointF | None = None
        self._drag_start_positions: dict[str, tuple[float, float]] = {}
        self._guides_x: list[float] = []
        self._guides_y: list[float] = []
        self._rubber: QRubberBand | None = None
        self._rubber_origin: QPointF | None = None
        self._pre_drag_snapshot: dict | None = None
        self.setSceneRect(0, 0, 480, 480)
        self.setMinimumSize(500, 500)
        self.setRenderHints(QPainter.RenderHint.Antialiasing)
        self.setBackgroundBrush(QBrush(QColor("#0B0D10")))
        self.refresh()

    # -- rendering -------------------------------------------------------------

    def refresh(self) -> None:
        self.scene.clear()
        renderer = LcdRenderer(self.layout, self.pipeline)
        image = renderer.render(mask=self.mask_enabled)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        pixmap = QPixmap()
        pixmap.loadFromData(buffer.getvalue())
        background = self.scene.addPixmap(pixmap)
        background.setZValue(-1000)
        if self.show_grid:
            pen = QPen(QColor(42, 46, 53, 160), 0.5)
            for pos in range(0, 481, 16):
                self.scene.addLine(pos, 0, pos, 480, pen).setZValue(-500)
                self.scene.addLine(0, pos, 480, pos, pen).setZValue(-500)
        for element_id in self.selection:
            element = self.layout.get(element_id)
            if element is not None:
                box = self._element_bounds(element)
                self.scene.addRect(box, QPen(QColor("#8A2BE2"), 1,
                                             Qt.PenStyle.DashLine)).setZValue(900)
        for guide_x in self._guides_x:
            pen = QPen(QColor("#00F0FF"), 1, Qt.PenStyle.DotLine)
            self.scene.addLine(guide_x, 0, guide_x, 480, pen).setZValue(950)
        for guide_y in self._guides_y:
            pen = QPen(QColor("#00F0FF"), 1, Qt.PenStyle.DotLine)
            self.scene.addLine(0, guide_y, 480, guide_y, pen).setZValue(950)
        self.scene.addRect(0, 0, 480, 480, QPen(QColor("#00F0FF"), 1)).setZValue(800)
        if self.mask_enabled:
            self.scene.addEllipse(0, 0, 480, 480, QPen(QColor("#8A2BE2"), 1)).setZValue(801)
        self.layout_changed.emit()

    @staticmethod
    def _element_bounds(element) -> QRectF:
        width = getattr(element, "width", 60.0) or 60.0
        height = getattr(element, "height", 30.0) or 30.0
        radius = getattr(element, "radius", None)
        if radius:
            return QRectF(element.x - radius, element.y - radius, radius * 2, radius * 2)
        return QRectF(element.x - width / 2, element.y - height / 2, width, height)

    # -- selection ------------------------------------------------------------------

    def set_selection(self, ids: list[str]) -> None:
        self.selection = [i for i in ids if self.layout.get(i) is not None]
        self.refresh()
        self.selection_changed.emit(list(self.selection))

    def select_all(self) -> None:
        self.set_selection([e.id for e in self.layout.elements if not e.locked])

    def clear_selection(self) -> None:
        self.set_selection([])

    # -- grouping ---------------------------------------------------------------------

    def group_selection(self) -> None:
        members = [i for i in self.selection]
        if len(members) < 2:
            return
        group = GroupElement(id=f"group_{len(self.layout.elements)}",
                             name=f"Group {len(self.layout.elements)}",
                             member_ids=members)
        for member_id in members:
            element = self.layout.get(member_id)
            if element is not None:
                element.locked = True  # members move via the group handle only
        self.layout.add(group, to_front=False)
        self.set_selection([group.id])

    def ungroup_selection(self) -> None:
        for element_id in list(self.selection):
            element = self.layout.get(element_id)
            if isinstance(element, GroupElement):
                for member_id in element.member_ids:
                    member = self.layout.get(member_id)
                    if member is not None:
                        member.locked = False
                self.layout.remove(element.id)
        self.clear_selection()

    def _expand_groups(self, ids: list[str]) -> list[str]:
        expanded: list[str] = []
        for element_id in ids:
            element = self.layout.get(element_id)
            if isinstance(element, GroupElement):
                expanded.extend(m for m in element.member_ids if m not in expanded)
            else:
                expanded.append(element_id)
        return expanded

    def move_selection(self, dx: float, dy: float) -> None:
        for element_id in self._expand_groups(self.selection):
            element = self.layout.get(element_id)
            if element is not None and not element.locked:
                element.x += dx
                element.y += dy

    # -- mouse interaction ---------------------------------------------------------------

    def mousePressEvent(self, event):
        position = self.mapToScene(event.position().toPoint())
        if event.button() == Qt.MouseButton.LeftButton:
            hit = self._hit(position)
            if hit is not None:
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    if hit.id in self.selection:
                        self.selection.remove(hit.id)
                    else:
                        self.selection.append(hit.id)
                    self.set_selection(list(self.selection))
                elif hit.id not in self.selection:
                    self.set_selection([hit.id])
                group_target = hit.id
                targets = self.selection if group_target in self.selection else [group_target]
                self._dragging_ids = self._expand_groups(targets)
                self._drag_origin = position
                self._drag_start_positions = {
                    e.id: (e.x, e.y)
                    for e in (self.layout.get(i) for i in self._dragging_ids)
                    if e is not None
                }
                self._pre_drag_snapshot = self.layout.to_dict()
            else:
                self._rubber_origin = position
                if self._rubber is None:
                    self._rubber = QRubberBand(QRubberBand.Shape.Rectangle, self)
                self._rubber.setGeometry(self.mapFromScene(QRectF(position, position)).boundingRect())
                self._rubber.show()
                if not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                    self.clear_selection()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        position = self.mapToScene(event.position().toPoint())
        if self._dragging_ids and (event.buttons() & Qt.MouseButton.LeftButton) \
                and self._drag_origin is not None:
            dx = position.x() - self._drag_origin.x()
            dy = position.y() - self._drag_origin.y()
            for element_id in self._dragging_ids:
                element = self.layout.get(element_id)
                if element is None or element.locked:
                    continue
                start_x, start_y = self._drag_start_positions[element.id]
                new_x, new_y = max(0, min(480, start_x + dx)), max(0, min(480, start_y + dy))
                if self.snap_grid:
                    new_x, new_y = round(new_x / 8) * 8, round(new_y / 8) * 8
                element.x, element.y = new_x, new_y
            self._apply_center_snap()
            self.refresh()
        elif self._rubber is not None and self._rubber_origin is not None \
                and (event.buttons() & Qt.MouseButton.LeftButton):
            rect = QRectF(self._rubber_origin, position).normalized()
            self._rubber.setGeometry(self.mapFromScene(rect).boundingRect())
            inside = [
                element.id for element in self.layout.elements
                if not element.locked and rect.intersects(self._element_bounds(element))
            ]
            self.selection = inside
            self.refresh()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._rubber is not None:
            self._rubber.hide()
            self._rubber_origin = None
            self.selection_changed.emit(list(self.selection))
        if self._dragging_ids:
            self._dragging_ids = []
            self._drag_origin = None
            self._guides_x = []
            self._guides_y = []
            self.refresh()
            if self._pre_drag_snapshot is not None:
                self.edit_committed.emit(self._pre_drag_snapshot)
                self._pre_drag_snapshot = None
        super().mouseReleaseEvent(event)

    def _apply_center_snap(self) -> None:
        """Snap dragged elements to the canvas center and to sibling centers."""
        self._guides_x = [240.0]
        self._guides_y = [240.0]

        # Alignment targets: canvas center + centers of visible siblings.
        target_xs = [240.0]
        target_ys = [240.0]
        for sibling in self.layout.elements:
            if sibling.id in self._dragging_ids or not sibling.visible:
                continue
            bounds = self._element_bounds(sibling)
            center = bounds.center()
            target_xs.append(center.x())
            target_ys.append(center.y())

        for element_id in self._dragging_ids:
            element = self.layout.get(element_id)
            if element is None or element.locked:
                continue
            nearest_x = min(target_xs, key=lambda tx: abs(tx - element.x))
            if abs(nearest_x - element.x) <= _CENTER_SNAP_PX:
                self._shift_element(element, nearest_x - element.x, 0.0)
            nearest_y = min(target_ys, key=lambda ty: abs(ty - element.y))
            if abs(nearest_y - element.y) <= _CENTER_SNAP_PX:
                self._shift_element(element, 0.0, nearest_y - element.y)

    @staticmethod
    def _shift_element(element, dx: float, dy: float) -> None:
        element.x += dx
        element.y += dy

    def keyPressEvent(self, event):
        key = event.key()
        if event.matches(GROUP_KEYS):
            self.group_selection()
        elif event.matches(UNGROUP_KEYS):
            self.ungroup_selection()
        elif key == Qt.Key.Key_Left:
            self.move_selection(-1, 0); self.refresh()
        elif key == Qt.Key.Key_Right:
            self.move_selection(1, 0); self.refresh()
        elif key == Qt.Key.Key_Up:
            self.move_selection(0, -1); self.refresh()
        elif key == Qt.Key.Key_Down:
            self.move_selection(0, 1); self.refresh()
        else:
            super().keyPressEvent(event)

    def _hit(self, pos: QPointF):
        candidates = []
        for element in reversed(self.layout.elements):
            if element.locked and not isinstance(element, GroupElement):
                continue
            if not element.visible:
                continue
            bounds = self._element_bounds(element)
            if bounds.adjusted(-12, -12, 12, 12).contains(pos):
                center = bounds.center()
                candidates.append(((center - pos).manhattanLength(), element))
        return min(candidates, default=(None, None))[1]


from PyQt6.QtGui import QKeySequence

GROUP_KEYS = QKeySequence("Ctrl+G")
UNGROUP_KEYS = QKeySequence("Ctrl+Shift+U")
