from PySide6.QtCore import Qt, QPointF
from ui.canvas.tools.draw_tool import DrawTool


class RectTool(DrawTool):

    def handle_press(self, scene_pos: QPointF, modifiers, button):
        if button != Qt.MouseButton.LeftButton:
            return
        shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        self._points.append(scene_pos)

        if len(self._points) == 2:
            p1, p2 = self._points
            if shift:
                p2 = self.constrain_square(p1, p2)
            self._finalize_pts(self.rect_corners(p1, p2), closed=True)

    def handle_move(self, scene_pos: QPointF, modifiers):
        if len(self._points) == 1:
            shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
            p2 = self.constrain_square(self._points[0], scene_pos) if shift else scene_pos
            self._show_preview(self.rect_corners(self._points[0], p2), closed=True)
