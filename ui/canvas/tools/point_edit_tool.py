from __future__ import annotations
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPen, QColor, QBrush

from core.constants import PIXELS_PER_MM
from core.path_model import Path, MoveTo, LineTo, CubicTo, QuadTo, ArcTo, ClosePath
from core.theme import get_theme
from ui.canvas.tools.base_tool import BaseTool

if TYPE_CHECKING:
    from ui.canvas.canvas import CAMCanvas
    from core.document import Document

NODE_SIZE_PX  = 7.0
HIT_RADIUS_PX = 9.0


class PointEditTool(BaseTool):
    """
    Drag individual path nodes (segment anchors + bezier control points) of the
    single selected shape. Only meaningful with exactly one shape selected -
    the tool panel disables this mode otherwise.
    """

    def __init__(self, canvas: CAMCanvas, document: Document):
        super().__init__(canvas)
        self._document = document
        self._shape_id: int | None = None
        self._working_path: Path | None = None
        self._drag: tuple[int, str] | None = None   # (segment_index, kind)
        self._selected_seg: int | None = None       # anchor segment_index - bezier handles show only for this one

    def activate(self):
        self._canvas.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        ids = self._canvas.selected_ids
        self._shape_id = next(iter(ids)) if len(ids) == 1 else None
        self._working_path = None
        self._drag = None
        self._selected_seg = None
        self._canvas.viewport().update()

    def deactivate(self):
        self._shape_id      = None
        self._working_path  = None
        self._drag          = None
        self._selected_seg  = None

    # ── Node model ────────────────────────────────────────────────────────────

    def _current_path(self) -> Path | None:
        if self._working_path is not None:
            return self._working_path
        if self._shape_id is None:
            return None
        _, shape = self._document.find_shape(self._shape_id)
        return shape.path if shape else None

    def _all_nodes(self) -> list[tuple[int, str, float, float]]:
        """[(segment_index, kind, x_mm, y_mm)] - kind: anchor | c1 | c2 | q"""
        path = self._current_path()
        if path is None:
            return []
        nodes: list[tuple[int, str, float, float]] = []
        for i, seg in enumerate(path.segments):
            if isinstance(seg, (MoveTo, LineTo, ArcTo)):
                nodes.append((i, "anchor", seg.x, seg.y))
            elif isinstance(seg, CubicTo):
                nodes.append((i, "c1", seg.cx1, seg.cy1))
                nodes.append((i, "c2", seg.cx2, seg.cy2))
                nodes.append((i, "anchor", seg.x, seg.y))
            elif isinstance(seg, QuadTo):
                nodes.append((i, "q", seg.cx, seg.cy))
                nodes.append((i, "anchor", seg.x, seg.y))
        return nodes

    def _visible_nodes(self) -> list[tuple[int, str, float, float]]:
        """Anchors are always shown; a segment's bezier handle(s) only show
        while the anchor they're attached to (incoming or outgoing) is selected -
        keeps dense bezier shapes readable instead of showing every handle at once."""
        sel = self._selected_seg
        result = []
        for seg_i, kind, x_mm, y_mm in self._all_nodes():
            if kind == "anchor":
                result.append((seg_i, kind, x_mm, y_mm))
            elif sel is not None and seg_i == sel and kind in ("c2", "q"):
                result.append((seg_i, kind, x_mm, y_mm))       # incoming handle of selected anchor
            elif sel is not None and seg_i == sel + 1 and kind in ("c1", "q"):
                result.append((seg_i, kind, x_mm, y_mm))       # outgoing handle of selected anchor
        return result

    @staticmethod
    def _scene_pos(x_mm: float, y_mm: float) -> QPointF:
        return QPointF(x_mm * PIXELS_PER_MM, y_mm * PIXELS_PER_MM)

    # ── Mouse ─────────────────────────────────────────────────────────────────

    def handle_press(self, scene_pos: QPointF, modifiers, button):
        if button != Qt.MouseButton.LeftButton or self._shape_id is None:
            return
        radius = HIT_RADIUS_PX / self._canvas.zoom
        best: tuple[int, str] | None = None
        best_dist = radius
        for seg_i, kind, x_mm, y_mm in self._visible_nodes():
            dist = (self._scene_pos(x_mm, y_mm) - scene_pos).manhattanLength()
            if dist <= best_dist:
                best = (seg_i, kind)
                best_dist = dist
        if best is not None:
            seg_i, kind = best
            if kind == "anchor":
                self._selected_seg = seg_i   # single-select - picking a new anchor swaps the shown handles
            self._drag = best
            self._working_path = self._clone_path()
        else:
            self._selected_seg = None
        self._canvas.viewport().update()

    def handle_move(self, scene_pos: QPointF, modifiers):
        if self._drag is None or self._working_path is None:
            return
        seg_i, kind = self._drag
        x_mm = scene_pos.x() / PIXELS_PER_MM
        y_mm = scene_pos.y() / PIXELS_PER_MM
        seg  = self._working_path.segments[seg_i]
        if kind == "anchor":
            seg.x, seg.y = x_mm, y_mm
        elif kind == "c1":
            seg.cx1, seg.cy1 = x_mm, y_mm
        elif kind == "c2":
            seg.cx2, seg.cy2 = x_mm, y_mm
        elif kind == "q":
            seg.cx, seg.cy = x_mm, y_mm
        self._canvas.set_shape_preview_path(self._shape_id, self._working_path)
        self._canvas.viewport().update()

    def handle_release(self, scene_pos: QPointF, modifiers, button):
        if button != Qt.MouseButton.LeftButton or self._drag is None:
            return
        self._drag = None
        if self._working_path is not None and self._shape_id is not None:
            self._canvas.shape_path_edited.emit(self._shape_id, self._working_path)
        self._working_path = None

    # ── Overlay ───────────────────────────────────────────────────────────────

    def draw_overlay(self, painter):
        if self._shape_id is None:
            return
        t = get_theme()
        s = NODE_SIZE_PX / self._canvas.zoom
        nodes = self._visible_nodes()

        # anchor endpoints double as the handle-line anchor point for their own
        # segment's incoming handle (seg_i) and the next segment's outgoing handle
        anchor_pos = {seg_i: self._scene_pos(x, y) for seg_i, kind, x, y in nodes if kind == "anchor"}

        handle_pen = QPen(QColor(t.accent), 0)
        handle_pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(handle_pen)
        for seg_i, kind, x_mm, y_mm in nodes:
            if kind == "anchor":
                continue
            owner = seg_i if kind in ("c2",) else seg_i - 1
            if kind == "q":
                owner = seg_i if seg_i == self._selected_seg else seg_i - 1
            anchor = anchor_pos.get(owner)
            if anchor is not None:
                painter.drawLine(anchor, self._scene_pos(x_mm, y_mm))

        for seg_i, kind, x_mm, y_mm in nodes:
            p    = self._scene_pos(x_mm, y_mm)
            rect = QRectF(p.x() - s / 2, p.y() - s / 2, s, s)
            if kind == "anchor":
                selected = seg_i == self._selected_seg
                painter.setPen(QPen(QColor(t.accent), 1.5 if selected else 1))
                painter.setBrush(QBrush(QColor(t.accent if selected else t.work_area)))
                painter.drawRect(rect)
            else:
                painter.setPen(QPen(QColor(t.text_secondary), 1))
                painter.setBrush(QBrush(QColor(t.canvas_bg)))
                painter.drawEllipse(rect)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _clone_path(self) -> Path:
        path = self._current_path()
        segs = []
        for seg in path.segments:
            if isinstance(seg, MoveTo):
                segs.append(MoveTo(seg.x, seg.y))
            elif isinstance(seg, LineTo):
                segs.append(LineTo(seg.x, seg.y))
            elif isinstance(seg, CubicTo):
                segs.append(CubicTo(seg.cx1, seg.cy1, seg.cx2, seg.cy2, seg.x, seg.y))
            elif isinstance(seg, QuadTo):
                segs.append(QuadTo(seg.cx, seg.cy, seg.x, seg.y))
            elif isinstance(seg, ArcTo):
                segs.append(ArcTo(seg.rx, seg.ry, seg.x_rotation, seg.large_arc, seg.sweep, seg.x, seg.y))
            else:
                segs.append(ClosePath())
        return Path(segments=segs)
