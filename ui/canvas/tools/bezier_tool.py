from __future__ import annotations

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPen, QColor, QBrush, QPainterPath

from core.document import Shape
from core.path_model import Path
from core.constants import PIXELS_PER_MM
from core.theme import get_theme
from ui.canvas.tools.draw_tool import DrawTool

CLOSE_HIT_RADIUS_PX = 10.0
DRAG_THRESHOLD_PX   = 4.0
HANDLE_NODE_PX       = 6.0


class BezierTool(DrawTool):
    """
    CorelDRAW/Illustrator-style pen tool: click places a corner anchor,
    click-and-drag places an anchor with a symmetric curve handle (the drag
    direction becomes the outgoing handle; its mirror becomes the incoming
    handle for the next segment). Enter finishes an open path; clicking back
    on the first anchor closes it. Escape cancels.
    """

    def __init__(self, canvas):
        super().__init__(canvas)
        self._points: list[dict] = []          # {"pos": QPointF, "handle_out": QPointF|None}
        self._drag_start: QPointF | None = None
        self._drag_start_vp: QPointF | None = None
        self._pending_handle: QPointF | None = None

    def deactivate(self):
        self._cancel()
        self._canvas.viewport().setCursor(Qt.CursorShape.ArrowCursor)

    def _cancel(self):
        self._points = []
        self._drag_start = None
        self._drag_start_vp = None
        self._pending_handle = None
        self._remove_preview()
        self._canvas.viewport().update()

    # ── Mouse ─────────────────────────────────────────────────────────────────

    def handle_press(self, scene_pos: QPointF, modifiers, button):
        if button != Qt.MouseButton.LeftButton:
            return
        if len(self._points) >= 2 and self._near_start(scene_pos):
            self._finalize(closed=True)
            return
        self._drag_start    = scene_pos
        self._drag_start_vp = self._canvas.mapFromScene(scene_pos)
        self._pending_handle = None

    def handle_move(self, scene_pos: QPointF, modifiers):
        if self._drag_start is not None:
            vp   = self._canvas.mapFromScene(scene_pos)
            dist = (vp - self._drag_start_vp).manhattanLength()
            self._pending_handle = scene_pos if dist > DRAG_THRESHOLD_PX else None
        self._canvas.viewport().update()

    def handle_release(self, scene_pos: QPointF, modifiers, button):
        if button != Qt.MouseButton.LeftButton or self._drag_start is None:
            return
        self._points.append({"pos": self._drag_start, "handle_out": self._pending_handle})
        self._drag_start     = None
        self._pending_handle = None
        self._canvas.viewport().update()

    def handle_key(self, event) -> bool:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if len(self._points) >= 2:
                self._finalize(closed=False)
            return True
        return super().handle_key(event)

    def _near_start(self, scene_pos: QPointF) -> bool:
        radius = CLOSE_HIT_RADIUS_PX / self._canvas.zoom
        return (scene_pos - self._points[0]["pos"]).manhattanLength() <= radius

    # ── Finalize ──────────────────────────────────────────────────────────────

    def _finalize(self, closed: bool):
        self._remove_preview()
        pts = self._points
        self._points = []
        self._drag_start = None
        self._pending_handle = None
        if len(pts) < 2:
            self._canvas.viewport().update()
            return

        def to_mm(p: QPointF) -> tuple[float, float]:
            return (p.x() / PIXELS_PER_MM, p.y() / PIXELS_PER_MM)

        mm_pts = [
            {"pos": to_mm(p["pos"]), "handle_out": to_mm(p["handle_out"]) if p["handle_out"] else None}
            for p in pts
        ]
        path = _build_bezier_path(mm_pts, closed)
        self._canvas.shape_drawn.emit(Shape(path=path), get_theme().draw_color)
        self._canvas.viewport().update()

    # ── Overlay (live preview) ────────────────────────────────────────────────

    def draw_overlay(self, painter):
        if not self._points and self._drag_start is None:
            return
        t = get_theme()

        qp = QPainterPath()
        if self._points:
            qp.moveTo(self._points[0]["pos"])
            prev = self._points[0]
            for p in self._points[1:]:
                c1 = prev["handle_out"] if prev["handle_out"] else prev["pos"]
                c2 = _mirror(p["handle_out"], p["pos"]) if p["handle_out"] else p["pos"]
                qp.cubicTo(c1, c2, p["pos"])
                prev = p
            # rubber-band from the last placed anchor to the anchor being placed now
            if self._drag_start is not None:
                c1 = prev["handle_out"] if prev["handle_out"] else prev["pos"]
                c2 = _mirror(self._pending_handle, self._drag_start) if self._pending_handle else self._drag_start
                qp.cubicTo(c1, c2, self._drag_start)
        elif self._drag_start is not None:
            qp.moveTo(self._drag_start)

        pen = QPen(QColor(t.preview), 0.8)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(qp)

        # anchor + handle markers
        for p in self._points:
            self._draw_anchor(painter, p["pos"])
            if p["handle_out"]:
                self._draw_handle(painter, p["pos"], p["handle_out"])
        if self._drag_start is not None:
            self._draw_anchor(painter, self._drag_start)
            if self._pending_handle:
                self._draw_handle(painter, self._drag_start, self._pending_handle)
                self._draw_handle(painter, self._drag_start, _mirror(self._pending_handle, self._drag_start))

    def _draw_anchor(self, painter, pos: QPointF):
        t = get_theme()
        s = HANDLE_NODE_PX / self._canvas.zoom
        painter.setPen(QPen(QColor(t.accent), 1))
        painter.setBrush(QBrush(QColor(t.work_area)))
        painter.drawRect(pos.x() - s/2, pos.y() - s/2, s, s)

    def _draw_handle(self, painter, anchor: QPointF, handle: QPointF):
        t = get_theme()
        s = HANDLE_NODE_PX / self._canvas.zoom
        line_pen = QPen(QColor(t.text_secondary), 0)
        line_pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(line_pen)
        painter.drawLine(anchor, handle)
        painter.setPen(QPen(QColor(t.text_secondary), 1))
        painter.setBrush(QBrush(QColor(t.canvas_bg)))
        painter.drawEllipse(handle.x() - s/2, handle.y() - s/2, s, s)


def _mirror(handle: QPointF, anchor: QPointF) -> QPointF:
    return QPointF(2 * anchor.x() - handle.x(), 2 * anchor.y() - handle.y())


def _build_bezier_path(points: list[dict], closed: bool) -> Path:
    path = Path()
    path.move_to(*points[0]["pos"])
    n = len(points)
    sequence = list(range(1, n)) + ([0] if closed else [])
    prev = points[0]
    for idx in sequence:
        cur = points[idx]
        c1 = prev["handle_out"] if prev["handle_out"] else prev["pos"]
        c2 = _mirror_mm(cur["handle_out"], cur["pos"]) if cur["handle_out"] else cur["pos"]
        if c1 == prev["pos"] and c2 == cur["pos"]:
            path.line_to(*cur["pos"])
        else:
            path.cubic_to(c1[0], c1[1], c2[0], c2[1], cur["pos"][0], cur["pos"][1])
        prev = cur
    if closed:
        path.close()
    return path


def _mirror_mm(handle: tuple[float, float], anchor: tuple[float, float]) -> tuple[float, float]:
    return (2 * anchor[0] - handle[0], 2 * anchor[1] - handle[1])
