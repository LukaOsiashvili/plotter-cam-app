from PySide6.QtCore import Qt, QPointF
from ui.canvas.tools.draw_tool import DrawTool


class NgonTool(DrawTool):
    """Click center, click edge. Shift = equilateral; no shift = stretched."""

    def __init__(self, canvas, sides: int = 6):
        super().__init__(canvas)
        self.sides = sides

    def handle_press(self, scene_pos: QPointF, modifiers, button):
        if button != Qt.MouseButton.LeftButton:
            return
        shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        self._points.append(scene_pos)

        if len(self._points) == 2:
            center, edge = self._points
            pts = self.ngon_pts(center, edge, self.sides, equilateral=shift)
            self._finalize_pts(pts, closed=True)

    def handle_move(self, scene_pos: QPointF, modifiers):
        if len(self._points) == 1:
            shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
            pts = self.ngon_pts(self._points[0], scene_pos, self.sides, equilateral=shift)
            self._show_preview(pts, closed=True)
