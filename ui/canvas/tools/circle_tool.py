from PySide6.QtCore import Qt, QPointF
from ui.canvas.tools.draw_tool import DrawTool


class CircleTool(DrawTool):
    """Click center, click edge. Shift = perfect circle; no shift = ellipse."""

    def handle_press(self, scene_pos: QPointF, modifiers, button):
        if button != Qt.MouseButton.LeftButton:
            return
        shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        self._points.append(scene_pos)

        if len(self._points) == 2:
            center, edge = self._points
            pts = self.ellipse_pts(center, edge, circle=shift)
            if pts:
                self._finalize_pts(pts, closed=True)
            else:
                self._cancel()

    def handle_move(self, scene_pos: QPointF, modifiers):
        if len(self._points) == 1:
            shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
            pts = self.ellipse_pts(self._points[0], scene_pos, circle=shift)
            if pts:
                self._show_preview(pts, closed=True)
