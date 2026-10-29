from __future__ import annotations
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPen, QColor, QPainterPath, QPainterPathStroker, QTransform
from PySide6.QtWidgets import QGraphicsView, QGraphicsRectItem

from core.constants import PIXELS_PER_MM
from core.theme import get_theme
from ui.canvas.tools.base_tool import BaseTool

if TYPE_CHECKING:
    from ui.canvas.canvas import CAMCanvas

_HANDLE_CURSORS = {
    "n": Qt.CursorShape.SizeVerCursor,  "s": Qt.CursorShape.SizeVerCursor,
    "e": Qt.CursorShape.SizeHorCursor,  "w": Qt.CursorShape.SizeHorCursor,
    "ne": Qt.CursorShape.SizeBDiagCursor, "sw": Qt.CursorShape.SizeBDiagCursor,
    "nw": Qt.CursorShape.SizeFDiagCursor, "se": Qt.CursorShape.SizeFDiagCursor,
}


class SelectTool(BaseTool):

    SHOWS_HANDLES = True

    def __init__(self, canvas: CAMCanvas):
        super().__init__(canvas)
        self._drag_start: QPointF | None   = None
        self._drag_start_vp               = None
        self._rubber_item: QGraphicsRectItem | None = None
        self._hit_on_press: int | None    = None
        self._pending_single_select: int | None = None
        self._center_hit  = False

        self._is_moving   = False
        self._move_items: list = []

        self._resizing      = False
        self._resize_handle: str | None = None
        self._resize_bounds: QRectF | None = None
        self._resize_items: list = []
        self._resize_sx = 1.0
        self._resize_sy = 1.0
        self._resize_anchor = QPointF(0, 0)

    def activate(self):
        self._canvas.setDragMode(QGraphicsView.DragMode.NoDrag)
        self._canvas.viewport().setCursor(Qt.CursorShape.ArrowCursor)

    def deactivate(self):
        self._remove_rubber()
        self._reset_drag_state()

    # ── Press ─────────────────────────────────────────────────────────────────

    def handle_press(self, scene_pos: QPointF, modifiers, button):
        if button != Qt.MouseButton.LeftButton:
            return
        shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        self._drag_start    = scene_pos
        self._drag_start_vp = self._canvas.mapFromScene(scene_pos)

        handle = self._canvas.hit_test_handle(scene_pos) if self._canvas.selected_ids else None
        if handle:
            self._start_resize(handle)
            return

        if self._canvas.selected_ids and self._canvas.hit_test_center(scene_pos):
            self._center_hit = True
            self._move_items = self._canvas.shape_items(self._canvas.selected_ids)
            return

        hit_id = self._hit_test(scene_pos)
        self._hit_on_press = hit_id
        self._pending_single_select = None

        if hit_id is not None:
            if shift:
                if hit_id in self._canvas.selected_ids:
                    self._canvas.deselect_one(hit_id)
                else:
                    self._canvas.add_to_selection(hit_id)
            elif hit_id in self._canvas.selected_ids:
                self._pending_single_select = hit_id   # collapse to this shape only if it's a click, not a drag
            else:
                self._canvas.deselect_all()
                self._canvas.add_to_selection(hit_id)

            if not shift and self._canvas.selected_ids:
                self._move_items = self._canvas.shape_items(self._canvas.selected_ids)
        else:
            if not shift:
                self._canvas.deselect_all()

    # ── Move ──────────────────────────────────────────────────────────────────

    def handle_move(self, scene_pos: QPointF, modifiers):
        if self._resizing:
            self._update_resize(scene_pos, modifiers)
            return

        if self._drag_start is None:
            self._update_hover_cursor(scene_pos)
            return

        vp_pos = self._canvas.mapFromScene(scene_pos)
        dist   = (vp_pos - self._drag_start_vp).manhattanLength()

        if self._move_items:
            if dist > 4:
                self._is_moving = True
                delta = scene_pos - self._drag_start
                for item in self._move_items:
                    item.setPos(delta)
                self._canvas.viewport().update()
        elif dist > 4:
            self._update_rubber(self._drag_start, scene_pos)

    def _update_hover_cursor(self, scene_pos: QPointF):
        handle = self._canvas.hit_test_handle(scene_pos) if self._canvas.selected_ids else None
        if handle:
            self._canvas.viewport().setCursor(_HANDLE_CURSORS[handle])
        elif self._canvas.selected_ids and self._canvas.hit_test_center(scene_pos):
            self._canvas.viewport().setCursor(Qt.CursorShape.SizeAllCursor)
        elif self._hit_test(scene_pos) is not None:
            self._canvas.viewport().setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self._canvas.viewport().setCursor(Qt.CursorShape.ArrowCursor)

    # ── Release ───────────────────────────────────────────────────────────────

    def handle_release(self, scene_pos: QPointF, modifiers, button):
        if button != Qt.MouseButton.LeftButton:
            return

        if self._resizing:
            self._finish_resize()
            return

        if self._drag_start is None:
            return

        shift  = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        vp_pos = self._canvas.mapFromScene(scene_pos)
        dist   = (vp_pos - self._drag_start_vp).manhattanLength()

        if self._is_moving:
            delta = scene_pos - self._drag_start
            dx_mm = delta.x() / PIXELS_PER_MM
            dy_mm = delta.y() / PIXELS_PER_MM
            for item in self._move_items:
                item.setPos(0, 0)
            if dx_mm or dy_mm:
                self._canvas.shapes_moved.emit(list(self._canvas.selected_ids), dx_mm, dy_mm)
        elif dist > 4 and self._hit_on_press is None and not self._center_hit:
            self._rubber_select(self._drag_start, scene_pos, shift)
        elif self._pending_single_select is not None:
            self._canvas.deselect_all()
            self._canvas.add_to_selection(self._pending_single_select)

        self._reset_drag_state()
        self._remove_rubber()

    def _reset_drag_state(self):
        self._drag_start    = None
        self._hit_on_press  = None
        self._pending_single_select = None
        self._center_hit    = False
        self._is_moving     = False
        self._move_items    = []

    # ── Resize ────────────────────────────────────────────────────────────────

    def _start_resize(self, handle: str):
        self._resizing      = True
        self._resize_handle = handle
        self._resize_bounds = self._canvas.selection_bounds_scene()
        self._resize_items  = self._canvas.shape_items(self._canvas.selected_ids)
        self._resize_sx = 1.0
        self._resize_sy = 1.0
        self._resize_anchor = self._resize_bounds.center() if self._resize_bounds else QPointF(0, 0)

    def _update_resize(self, scene_pos: QPointF, modifiers):
        if self._resize_bounds is None:
            return
        symmetric = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        orig = self._resize_bounds
        handle = self._resize_handle
        cx, cy = orig.center().x(), orig.center().y()

        sx = sy = 1.0
        anchor_x, anchor_y = cx, cy

        if "w" in handle:
            anchor_x = cx if symmetric else orig.right()
            width = 2 * abs(cx - scene_pos.x()) if symmetric else (orig.right() - scene_pos.x())
            sx = width / orig.width() if orig.width() else 1.0
        elif "e" in handle:
            anchor_x = cx if symmetric else orig.left()
            width = 2 * abs(scene_pos.x() - cx) if symmetric else (scene_pos.x() - orig.left())
            sx = width / orig.width() if orig.width() else 1.0

        if "n" in handle:
            anchor_y = cy if symmetric else orig.bottom()
            height = 2 * abs(cy - scene_pos.y()) if symmetric else (orig.bottom() - scene_pos.y())
            sy = height / orig.height() if orig.height() else 1.0
        elif "s" in handle:
            anchor_y = cy if symmetric else orig.top()
            height = 2 * abs(scene_pos.y() - cy) if symmetric else (scene_pos.y() - orig.top())
            sy = height / orig.height() if orig.height() else 1.0

        MIN_SCALE = 0.02
        if abs(sx) < MIN_SCALE:
            sx = MIN_SCALE if sx >= 0 else -MIN_SCALE
        if abs(sy) < MIN_SCALE:
            sy = MIN_SCALE if sy >= 0 else -MIN_SCALE

        self._resize_sx = sx
        self._resize_sy = sy
        self._resize_anchor = QPointF(anchor_x, anchor_y)

        t = QTransform()
        t.translate(anchor_x, anchor_y)
        t.scale(sx, sy)
        t.translate(-anchor_x, -anchor_y)
        for item in self._resize_items:
            item.setTransform(t)
        self._canvas.viewport().update()

    def _finish_resize(self):
        sx, sy = self._resize_sx, self._resize_sy
        anchor_x_mm = self._resize_anchor.x() / PIXELS_PER_MM
        anchor_y_mm = self._resize_anchor.y() / PIXELS_PER_MM
        for item in self._resize_items:
            item.setTransform(QTransform())
        if abs(sx - 1.0) > 1e-6 or abs(sy - 1.0) > 1e-6:
            self._canvas.shapes_resized.emit(
                list(self._canvas.selected_ids), sx, sy, anchor_x_mm, anchor_y_mm
            )
        self._resizing      = False
        self._resize_handle = None
        self._resize_bounds = None
        self._resize_items  = []
        self._drag_start    = None

    def handle_double_click(self, scene_pos: QPointF, modifiers, button):
        if button != Qt.MouseButton.LeftButton:
            return
        hit_id = self._hit_test(scene_pos)
        if hit_id is not None:
            self._canvas.shape_double_clicked.emit(hit_id)

    # ── Hit testing ───────────────────────────────────────────────────────────

    def _hit_test(self, scene_pos: QPointF) -> int | None:
        stroker = QPainterPathStroker()
        stroker.setWidth(16.0 / self._canvas.zoom)

        for item in self._canvas.scene.items(scene_pos):
            if item.data(0) is None:
                continue
            stroke = stroker.createStroke(item.path())
            if stroke.contains(scene_pos):
                return item.data(0)
        return None

    def _rubber_select(self, p1: QPointF, p2: QPointF, additive: bool):
        rect = QRectF(p1, p2).normalized()
        if not additive:
            self._canvas.deselect_all()

        stroker = QPainterPathStroker()
        stroker.setWidth(16.0 / self._canvas.zoom)
        rect_path = QPainterPath()
        rect_path.addRect(rect)

        for item in self._canvas.scene.items(rect, Qt.ItemSelectionMode.IntersectsItemShape):
            if item.data(0) is None:
                continue
            stroke = stroker.createStroke(item.path())
            if stroke.intersects(rect_path):
                self._canvas.add_to_selection(item.data(0))

    # ── Rubber band visual ────────────────────────────────────────────────────

    def _update_rubber(self, p1: QPointF, p2: QPointF):
        rect  = QRectF(p1, p2).normalized()
        color = get_theme().accent
        if self._rubber_item is None:
            pen = QPen(QColor(color), 0.5)
            pen.setStyle(Qt.PenStyle.DashLine)
            self._rubber_item = QGraphicsRectItem(rect)
            self._rubber_item.setPen(pen)
            self._rubber_item.setBrush(QColor(color + "22"))
            self._rubber_item.setZValue(1000)
            self._canvas.scene.addItem(self._rubber_item)
        else:
            self._rubber_item.setRect(rect)

    def _remove_rubber(self):
        if self._rubber_item is not None:
            self._canvas.scene.removeItem(self._rubber_item)
            self._rubber_item = None
