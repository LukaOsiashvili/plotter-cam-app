from PySide6.QtCore import Qt, QPointF
from ui.canvas.tools.draw_tool import DrawTool


class PolylineTool(DrawTool):

    def handle_press(self, scene_pos: QPointF, modifiers, button):
        if button != Qt.MouseButton.LeftButton:
            return
        shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        if self._points and shift:
            scene_pos = self.constrain_axis(self._points[-1], scene_pos)
        self._points.append(scene_pos)

    def handle_move(self, scene_pos: QPointF, modifiers):
        if not self._points:
            return
        shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        p2 = self.constrain_axis(self._points[-1], scene_pos) if shift else scene_pos
        self._show_preview(self._points + [p2])

    def handle_key(self, event) -> bool:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if len(self._points) >= 2:
                self._finalize_pts(self._points, closed=False)
            return True
        return super().handle_key(event)
