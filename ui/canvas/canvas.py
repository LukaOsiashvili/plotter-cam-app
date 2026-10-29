from __future__ import annotations
import math

from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsRectItem
from PySide6.QtGui import (QPen, QBrush, QColor, QWheelEvent,
                            QPainter, QPainterPath)
from PySide6.QtCore import Qt, Signal, QRectF, QPointF

HANDLE_SIZE_PX      = 7.0    # constant on-screen size, independent of zoom
CENTER_MARK_SIZE_PX = 10.0   # click target for the move-from-center cross

from core.constants import PIXELS_PER_MM, WORK_W_MM, WORK_H_MM
from core.document import Layer, Shape
from core.path_model import (PathSegment, MoveTo, LineTo, CubicTo,
                              QuadTo, ArcTo, ClosePath)
from core.theme import get_theme
from ui.canvas.tools.base_tool import BaseTool

ZOOM_MIN = 0.15
ZOOM_MAX = 6.0


class CAMCanvas(QGraphicsView):

    transform_changed = Signal(float, float, float, float)  # ox, oy, sx, sy
    selection_changed = Signal(list)                         # list[shape_id]
    shape_drawn       = Signal(object, str)                  # (Shape, color_hex)
    cursor_moved      = Signal(float, float)                 # x_mm, y_mm
    shapes_moved      = Signal(list, float, float)            # shape_ids, dx_mm, dy_mm
    shapes_resized    = Signal(list, float, float, float, float)  # shape_ids, sx, sy, anchor_x_mm, anchor_y_mm
    shape_path_edited = Signal(int, object)                       # shape_id, new Path (node/point editing)
    shape_text_edited = Signal(object, object, object)             # shape_id|None (None = new), new Path, new TextData
    shape_double_clicked = Signal(int)                             # shape_id - SelectTool: double-click to edit text

    def __init__(self):
        super().__init__()
        self.scene              = QGraphicsScene()
        self._zoom              = 1.0
        self._auto_fit          = True   # keep the page fitted on resize until the user zooms
        self._active_tool: BaseTool | None = None
        self.selected_ids: set[int] = set()
        self._selection_order: list[int] = []   # tracks insertion order for align
        self._work_rect         = None
        self._origin_lines      = []
        self._work_w_mm         = WORK_W_MM
        self._work_h_mm         = WORK_H_MM
        self._cursor_scene_pos: QPointF | None = None

        self.setScene(self.scene)
        self._setup_view()
        self._draw_work_area()

    def _setup_view(self):
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setBackgroundBrush(QBrush(QColor(get_theme().canvas_bg)))
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _draw_work_area(self):
        t = get_theme()
        w = self._work_w_mm * PIXELS_PER_MM
        h = self._work_h_mm * PIXELS_PER_MM
        self._work_rect = QGraphicsRectItem(0, 0, w, h)
        self._work_rect.setBrush(QBrush(QColor(t.work_area)))
        self._work_rect.setPen(QPen(QColor(t.border), 1))
        self._work_rect.setZValue(-10)
        self.scene.addItem(self._work_rect)
        pen = QPen(QColor(t.origin_cross), 1)
        self._origin_lines = [
            self.scene.addLine(-8, 0, 8, 0, pen),
            self.scene.addLine(0, -8, 0, 8, pen),
        ]
        self.scene.setSceneRect(-20, -20, w + 40, h + 40)

    def set_work_area(self, w_mm: float, h_mm: float):
        """Resize the drawn work area to match the document's stored bed size."""
        self._work_w_mm = w_mm
        self._work_h_mm = h_mm
        self.scene.removeItem(self._work_rect)
        for line in self._origin_lines:
            self.scene.removeItem(line)
        self._draw_work_area()

    def apply_theme(self):
        """Update all theme-dependent colors without clearing shapes."""
        t = get_theme()
        self.setBackgroundBrush(QBrush(QColor(t.canvas_bg)))
        if self._work_rect:
            self._work_rect.setBrush(QBrush(QColor(t.work_area)))
            self._work_rect.setPen(QPen(QColor(t.border), 1))
        pen = QPen(QColor(t.origin_cross), 1)
        for line in self._origin_lines:
            line.setPen(pen)
        self.viewport().update()

    # ── Tool API ──────────────────────────────────────────────────────────────

    @property
    def zoom(self) -> float:
        return self._zoom

    def set_tool(self, tool: BaseTool):
        if self._active_tool:
            self._active_tool.deactivate()
        self._active_tool = tool
        if tool:
            tool.activate()

    # ── Mouse events - delegated to active tool ───────────────────────────────

    def mousePressEvent(self, event):
        if self._active_tool:
            scene_pos = self.mapToScene(event.pos())
            self._active_tool.handle_press(scene_pos, event.modifiers(), event.button())
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        scene_pos = self.mapToScene(event.pos())
        self._cursor_scene_pos = scene_pos
        self.viewport().update()
        self.cursor_moved.emit(scene_pos.x() / PIXELS_PER_MM,
                               scene_pos.y() / PIXELS_PER_MM)
        if self._active_tool:
            self._active_tool.handle_move(scene_pos, event.modifiers())
        else:
            super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._cursor_scene_pos = None
        self.viewport().update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._active_tool:
            scene_pos = self.mapToScene(event.pos())
            self._active_tool.handle_release(scene_pos, event.modifiers(), event.button())
        else:
            super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self._active_tool:
            scene_pos = self.mapToScene(event.pos())
            self._active_tool.handle_double_click(scene_pos, event.modifiers(), event.button())
        else:
            super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        if self._active_tool and self._active_tool.handle_key(event):
            return
        super().keyPressEvent(event)

    # ── Selection API (used by SelectTool and external callers) ───────────────

    @property
    def selection_order(self) -> list[int]:
        """Shape IDs in the order they were selected - used for align reference."""
        return list(self._selection_order)

    def add_to_selection(self, shape_id: int):
        self.selected_ids.add(shape_id)
        if shape_id not in self._selection_order:
            self._selection_order.append(shape_id)
        for item in self.scene.items():
            if item.data(0) == shape_id:
                item.setPen(QPen(QColor(get_theme().selection), 1.5))
        self.selection_changed.emit(list(self.selected_ids))

    def deselect_one(self, shape_id: int):
        self.selected_ids.discard(shape_id)
        if shape_id in self._selection_order:
            self._selection_order.remove(shape_id)
        for item in self.scene.items():
            if item.data(0) == shape_id:
                original = item.data(2)
                if original:
                    item.setPen(QPen(QColor(original), 0.5))
        self.selection_changed.emit(list(self.selected_ids))

    def deselect_all(self):
        for sid in list(self.selected_ids):
            for item in self.scene.items():
                if item.data(0) == sid:
                    original = item.data(2)
                    if original:
                        item.setPen(QPen(QColor(original), 0.5))
        self.selected_ids.clear()
        self._selection_order.clear()
        self.selection_changed.emit([])

    def select_shape(self, shape_id: int, additive: bool = False):
        if not additive:
            self.deselect_all()
        self.add_to_selection(shape_id)

    def select_all(self):
        ids = {item.data(0) for item in self.scene.items() if item.data(0) is not None}
        self.deselect_all()
        for sid in ids:
            self.add_to_selection(sid)

    # ── Selection bounds / resize handles ─────────────────────────────────────

    def selection_bounds_scene(self) -> QRectF | None:
        """Union of the current selection's on-screen (scene) bounding rects, or None."""
        if not self.selected_ids:
            return None
        rect = None
        for item in self.scene.items():
            if item.data(0) in self.selected_ids:
                r = item.mapToScene(item.path().boundingRect()).boundingRect()
                rect = r if rect is None else rect.united(r)
        return rect

    def _handle_rects(self) -> dict[str, QRectF]:
        bounds = self.selection_bounds_scene()
        if bounds is None:
            return {}
        s = HANDLE_SIZE_PX / self._zoom
        cx, cy = bounds.center().x(), bounds.center().y()
        points = {
            "nw": (bounds.left(),  bounds.top()),
            "n":  (cx,             bounds.top()),
            "ne": (bounds.right(), bounds.top()),
            "e":  (bounds.right(), cy),
            "se": (bounds.right(), bounds.bottom()),
            "s":  (cx,             bounds.bottom()),
            "sw": (bounds.left(),  bounds.bottom()),
            "w":  (bounds.left(),  cy),
        }
        return {
            name: QRectF(x - s / 2, y - s / 2, s, s)
            for name, (x, y) in points.items()
        }

    def hit_test_handle(self, scene_pos: QPointF) -> str | None:
        for name, rect in self._handle_rects().items():
            if rect.contains(scene_pos):
                return name
        return None

    def center_mark_rect(self) -> QRectF | None:
        bounds = self.selection_bounds_scene()
        if bounds is None:
            return None
        s = CENTER_MARK_SIZE_PX / self._zoom
        c = bounds.center()
        return QRectF(c.x() - s / 2, c.y() - s / 2, s, s)

    def hit_test_center(self, scene_pos: QPointF) -> bool:
        rect = self.center_mark_rect()
        return rect is not None and rect.contains(scene_pos)

    def shape_items(self, shape_ids) -> list:
        ids = set(shape_ids)
        return [item for item in self.scene.items() if item.data(0) in ids]

    # ── Draw / clear shapes ───────────────────────────────────────────────────

    def draw_shape(self, shape: Shape, color: str):
        if shape.path.is_empty():
            return
        pen  = QPen(QColor(color), 0.5)
        item = self.scene.addPath(path_to_qpainter(shape.path, PIXELS_PER_MM), pen)
        item.setData(0, shape.id)
        item.setData(2, color)

    def draw_layer(self, layer: Layer):
        for shape in layer.shapes:
            self.draw_shape(shape, layer.color)

    def clear_shape(self, shape_id: int):
        self.selected_ids.discard(shape_id)
        if shape_id in self._selection_order:
            self._selection_order.remove(shape_id)
        for item in [i for i in self.scene.items() if i.data(0) == shape_id]:
            self.scene.removeItem(item)

    def clear_layer(self, layer: Layer):
        for shape in layer.shapes:
            self.clear_shape(shape.id)

    def redraw_shape(self, shape: Shape, new_color: str):
        """Redraw a shape's graphics without disturbing selection state or order."""
        sid          = shape.id
        was_selected = sid in self.selected_ids
        for item in [i for i in self.scene.items() if i.data(0) == sid]:
            self.scene.removeItem(item)
        self.draw_shape(shape, new_color)
        if was_selected:
            for item in self.scene.items():
                if item.data(0) == sid:
                    item.setPen(QPen(QColor(get_theme().selection), 1.5))

    def set_shape_item_visible(self, shape_id: int, visible: bool):
        """Hide/show a shape's graphics item - used while its text overlay editor is open."""
        for item in self.scene.items():
            if item.data(0) == shape_id:
                item.setVisible(visible)

    def set_shape_preview_path(self, shape_id: int, path):
        """Update a shape's on-screen geometry only, without touching the document - used
        while dragging a node so the drag can be cancelled/undone without side effects."""
        qpp = path_to_qpainter(path, PIXELS_PER_MM)
        for item in self.scene.items():
            if item.data(0) == shape_id:
                item.setPath(qpp)

    def rebuild(self, layers: list[Layer]):
        """Clear all shapes and redraw from a list of layers."""
        self.scene.clear()
        self._draw_work_area()
        self.selected_ids.clear()
        for layer in layers:
            if layer.visible:
                self.draw_layer(layer)

    # ── Crosshair overlay ─────────────────────────────────────────────────────

    def drawForeground(self, painter: QPainter, rect):
        super().drawForeground(painter, rect)
        if getattr(self._active_tool, "SHOWS_HANDLES", False):
            self._draw_selection_handles(painter)
        if self._active_tool:
            self._active_tool.draw_overlay(painter)
        if self._cursor_scene_pos is None:
            return
        painter.setOpacity(0.45)
        pen = QPen(QColor(get_theme().text_secondary), 0)
        pen.setStyle(Qt.PenStyle.SolidLine)
        painter.setPen(pen)
        x = self._cursor_scene_pos.x()
        y = self._cursor_scene_pos.y()
        painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
        painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
        painter.setOpacity(1.0)

    def _draw_selection_handles(self, painter: QPainter):
        rects = self._handle_rects()
        if not rects:
            return
        t = get_theme()
        bounds = self.selection_bounds_scene()
        outline_pen = QPen(QColor(t.accent), 0)
        outline_pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(outline_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(bounds)
        painter.setPen(QPen(QColor(t.accent), 1))
        painter.setBrush(QBrush(QColor(t.work_area)))
        for handle_rect in rects.values():
            painter.drawRect(handle_rect)

        center_rect = self.center_mark_rect()
        if center_rect is not None:
            painter.setPen(QPen(QColor(t.accent), 1.5))
            painter.drawLine(center_rect.topLeft(), center_rect.bottomRight())
            painter.drawLine(center_rect.topRight(), center_rect.bottomLeft())

    # ── Zoom / pan ────────────────────────────────────────────────────────────

    def wheelEvent(self, event: QWheelEvent):
        factor   = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        new_zoom = self._zoom * factor
        if ZOOM_MIN <= new_zoom <= ZOOM_MAX:
            self._auto_fit = False
            self._zoom = new_zoom
            self.scale(factor, factor)
            self._emit_transform()

    def scrollContentsBy(self, dx, dy):
        super().scrollContentsBy(dx, dy)
        self._emit_transform()

    def _emit_transform(self):
        t      = self.transform()
        origin = self.mapFromScene(0, 0)
        self.transform_changed.emit(origin.x(), origin.y(), t.m11(), t.m22())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._auto_fit:
            self.fit_view()

    def fit_view(self):
        self._auto_fit = True
        self.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self._zoom = self.transform().m11()
        self._emit_transform()

    def reset_zoom(self):
        self._auto_fit = False
        self.resetTransform()
        self._zoom = 1.0
        self._emit_transform()

    # ── Unit helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def mm_to_px(mm: float) -> float:
        return mm * PIXELS_PER_MM

    @staticmethod
    def px_to_mm(px: float) -> float:
        return px / PIXELS_PER_MM


# ── Path conversion ───────────────────────────────────────────────────────────

def path_to_qpainter(path, ppm: float) -> QPainterPath:
    """Convert our Path model to QPainterPath, scaling mm → pixels."""
    qp = QPainterPath()
    cur_x = cur_y = 0.0

    for seg in path.segments:
        if isinstance(seg, MoveTo):
            qp.moveTo(seg.x * ppm, seg.y * ppm)
            cur_x, cur_y = seg.x, seg.y

        elif isinstance(seg, LineTo):
            qp.lineTo(seg.x * ppm, seg.y * ppm)
            cur_x, cur_y = seg.x, seg.y

        elif isinstance(seg, CubicTo):
            qp.cubicTo(seg.cx1*ppm, seg.cy1*ppm,
                       seg.cx2*ppm, seg.cy2*ppm,
                       seg.x*ppm,   seg.y*ppm)
            cur_x, cur_y = seg.x, seg.y

        elif isinstance(seg, QuadTo):
            qp.quadTo(seg.cx*ppm, seg.cy*ppm,
                      seg.x*ppm,  seg.y*ppm)
            cur_x, cur_y = seg.x, seg.y

        elif isinstance(seg, ArcTo):
            _append_svg_arc(qp, cur_x*ppm, cur_y*ppm,
                            seg.rx*ppm, seg.ry*ppm,
                            seg.x_rotation, seg.large_arc, seg.sweep,
                            seg.x*ppm, seg.y*ppm)
            cur_x, cur_y = seg.x, seg.y

        elif isinstance(seg, ClosePath):
            qp.closeSubpath()

    return qp


def _append_svg_arc(qp: QPainterPath,
                    x0: float, y0: float,
                    rx: float, ry: float,
                    phi_deg: float, large_arc: bool, sweep: bool,
                    x: float, y: float):
    """Convert SVG arc endpoint parameterization → QPainterPath.arcTo()."""
    if x0 == x and y0 == y:
        return
    if rx == 0 or ry == 0:
        qp.lineTo(x, y)
        return

    # For rotated ellipses (phi != 0), approximate with a line for now
    # Most real-world arcs have phi=0
    if phi_deg != 0:
        qp.lineTo(x, y)
        return

    rx = abs(rx)
    ry = abs(ry)

    # Clamp radii
    lam = ((x0 - x) / (2 * rx)) ** 2 + ((y0 - y) / (2 * ry)) ** 2
    if lam > 1:
        s  = math.sqrt(lam)
        rx *= s
        ry *= s

    # Midpoint parameterization → center
    dx   = (x0 - x) / 2
    dy   = (y0 - y) / 2
    x1p  = dx
    y1p  = dy

    num = max(0.0, (rx*ry)**2 - (rx*y1p)**2 - (ry*x1p)**2)
    den = (rx*y1p)**2 + (ry*x1p)**2
    sq  = math.sqrt(num / den) if den > 0 else 0.0
    if large_arc == sweep:
        sq = -sq

    cxp = sq *  rx * y1p / ry
    cyp = sq * -ry * x1p / rx
    cx  = cxp + (x0 + x) / 2
    cy  = cyp + (y0 + y) / 2

    def _angle(ux, uy, vx, vy):
        n = math.sqrt(ux*ux + uy*uy) * math.sqrt(vx*vx + vy*vy)
        if n == 0:
            return 0.0
        a = math.degrees(math.acos(max(-1.0, min(1.0, (ux*vx + uy*vy) / n))))
        return -a if ux*vy - uy*vx < 0 else a

    theta1 = _angle(1, 0, (x1p - cxp)/rx, (y1p - cyp)/ry)
    dtheta = _angle((x1p - cxp)/rx, (y1p - cyp)/ry,
                    (-x1p - cxp)/rx, (-y1p - cyp)/ry)

    if not sweep and dtheta > 0:
        dtheta -= 360
    elif sweep and dtheta < 0:
        dtheta += 360

    # Qt uses Y-down, angles clockwise → negate
    rect = QRectF(cx - rx, cy - ry, 2*rx, 2*ry)
    qp.arcTo(rect, -theta1, -dtheta)
