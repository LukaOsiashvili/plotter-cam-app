from __future__ import annotations
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QKeyEvent, QMouseEvent

if TYPE_CHECKING:
    from ui.canvas.canvas import CAMCanvas


class ToolMode:
    SELECT     = "select"
    POINT_EDIT = "point_edit"
    LINE       = "line"
    POLYLINE   = "polyline"
    RECT       = "rect"
    NGON       = "ngon"
    CIRCLE     = "circle"
    BEZIER     = "bezier"
    TEXT       = "text"


class BaseTool:
    """
    Strategy base for all canvas tools.
    Tools are created by MainWindow and passed to CAMCanvas.set_tool().
    """

    SHOWS_HANDLES = False   # draw selection resize handles on the canvas while this tool is active

    def __init__(self, canvas: CAMCanvas):
        self._canvas = canvas

    def activate(self):
        """Called when this tool becomes active."""

    def deactivate(self):
        """Called when switching away from this tool. Clean up any state."""

    def handle_press(self, scene_pos: QPointF, modifiers: Qt.KeyboardModifier,
                     button: Qt.MouseButton):
        """Left/right mouse button pressed."""

    def handle_move(self, scene_pos: QPointF, modifiers: Qt.KeyboardModifier):
        """Mouse moved (button may or may not be held)."""

    def handle_release(self, scene_pos: QPointF, modifiers: Qt.KeyboardModifier,
                       button: Qt.MouseButton):
        """Mouse button released."""

    def handle_double_click(self, scene_pos: QPointF, modifiers: Qt.KeyboardModifier,
                            button: Qt.MouseButton):
        """Mouse double-clicked."""

    def handle_key(self, event: QKeyEvent) -> bool:
        """Return True if the key was consumed, False to propagate."""
        return False

    def draw_overlay(self, painter):
        """Called every repaint after shapes are drawn - custom per-tool overlay (e.g. node handles)."""
