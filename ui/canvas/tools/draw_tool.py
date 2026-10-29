from __future__ import annotations
import math
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPen, QColor, QPainterPath
from PySide6.QtWidgets import QGraphicsPathItem

from core.document import Shape
from core.path_model import Path
from core.constants import PIXELS_PER_MM
from core.theme import get_theme
from ui.canvas.tools.base_tool import BaseTool

if TYPE_CHECKING:
    from ui.canvas.canvas import CAMCanvas


class DrawTool(BaseTool):
    """Shared base for all drawing tools - manages preview items and point lists."""

    def __init__(self, canvas: CAMCanvas):
        super().__init__(canvas)
        self._points: list[QPointF] = []
        self._preview: QGraphicsPathItem | None = None

    def activate(self):
        self._canvas.viewport().setCursor(Qt.CursorShape.CrossCursor)
        self._canvas.setDragMode(self._canvas.DragMode.NoDrag)

    def deactivate(self):
        self._cancel()
        self._canvas.viewport().setCursor(Qt.CursorShape.ArrowCursor)

    def handle_key(self, event) -> bool:
        if event.key() == Qt.Key.Key_Escape:
            self._cancel()
            return True
        return False

    # ── Preview management ────────────────────────────────────────────────────

    def _show_preview(self, pts: list[QPointF], closed: bool = False):
        self._remove_preview()
        if len(pts) < 2:
            return
        pen = QPen(QColor(get_theme().preview), 0.8)
        pen.setStyle(Qt.PenStyle.DashLine)
        self._preview = self._canvas.scene.addPath(
            _pts_to_qpath(pts, closed), pen
        )

    def _remove_preview(self):
        if self._preview is not None:
            self._canvas.scene.removeItem(self._preview)
            self._preview = None

    def _cancel(self):
        self._points.clear()
        self._remove_preview()

    # ── Shape finalization ────────────────────────────────────────────────────

    def _finalize_pts(self, pts: list[QPointF], closed: bool = False):
        """Convert pixel points → mm Path, emit shape_drawn."""
        self._remove_preview()
        self._points.clear()
        mm = [(px_to_mm(p.x()), px_to_mm(p.y())) for p in pts]
        path = Path.from_points(mm, closed=closed)
        self._canvas.shape_drawn.emit(Shape(path=path), get_theme().draw_color)

    # ── Geometry helpers ──────────────────────────────────────────────────────

    @staticmethod
    def constrain_axis(p1: QPointF, p2: QPointF) -> QPointF:
        """Snap p2 to the horizontal or vertical axis from p1."""
        dx = abs(p2.x() - p1.x())
        dy = abs(p2.y() - p1.y())
        return QPointF(p2.x(), p1.y()) if dx >= dy else QPointF(p1.x(), p2.y())

    @staticmethod
    def constrain_square(p1: QPointF, p2: QPointF) -> QPointF:
        dx   = p2.x() - p1.x()
        dy   = p2.y() - p1.y()
        side = max(abs(dx), abs(dy))
        return QPointF(p1.x() + math.copysign(side, dx),
                       p1.y() + math.copysign(side, dy))

    @staticmethod
    def rect_corners(p1: QPointF, p2: QPointF) -> list[QPointF]:
        return [
            QPointF(p1.x(), p1.y()), QPointF(p2.x(), p1.y()),
            QPointF(p2.x(), p2.y()), QPointF(p1.x(), p2.y()),
        ]

    @staticmethod
    def ellipse_pts(center: QPointF, edge: QPointF,
                    circle: bool, samples: int = 72) -> list[QPointF]:
        dx = abs(edge.x() - center.x())
        dy = abs(edge.y() - center.y())
        rx, ry = (max(dx, dy), max(dx, dy)) if circle else (dx, dy)
        if rx == 0 or ry == 0:
            return []
        return [
            QPointF(center.x() + rx * math.cos(math.radians(i * 360 / samples)),
                    center.y() + ry * math.sin(math.radians(i * 360 / samples)))
            for i in range(samples)
        ]

    @staticmethod
    def ngon_pts(center: QPointF, edge: QPointF,
                 sides: int, equilateral: bool) -> list[QPointF]:
        start = -math.pi / 2
        if equilateral:
            r = math.hypot(edge.x() - center.x(), edge.y() - center.y())
            rx = ry = r
        else:
            rx = abs(edge.x() - center.x())
            ry = abs(edge.y() - center.y())
        return [
            QPointF(center.x() + rx * math.cos(start + 2*math.pi*i/sides),
                    center.y() + ry * math.sin(start + 2*math.pi*i/sides))
            for i in range(sides)
        ]


# ── Module-level helpers ──────────────────────────────────────────────────────

def px_to_mm(px: float) -> float:
    return px / PIXELS_PER_MM


def _pts_to_qpath(pts: list[QPointF], closed: bool) -> QPainterPath:
    path = QPainterPath()
    path.moveTo(pts[0])
    for p in pts[1:]:
        path.lineTo(p)
    if closed:
        path.closeSubpath()
    return path
