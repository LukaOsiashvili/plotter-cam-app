from PySide6.QtWidgets import QWidget, QGridLayout
from PySide6.QtCore import Qt

from core.theme import get_theme
from ui.canvas.canvas import CAMCanvas
from ui.canvas.rulers import RulerWidget


class CAMCanvasWithRulers(QWidget):
    """Wraps CAMCanvas with horizontal and vertical mm rulers."""

    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.canvas  = CAMCanvas()
        self.h_ruler = RulerWidget("horizontal")
        self.v_ruler = RulerWidget("vertical")

        t = get_theme()
        rs = t.ruler_size
        corner = QWidget()
        corner.setFixedSize(rs, rs)
        corner.setStyleSheet(f"background-color: {t.ruler_bg};")

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(corner,       0, 0)
        layout.addWidget(self.h_ruler, 0, 1)
        layout.addWidget(self.v_ruler, 1, 0)
        layout.addWidget(self.canvas,  1, 1)

        self.canvas.transform_changed.connect(self._on_transform)

        # Expose canvas signals and methods at this level
        self.selection_changed = self.canvas.selection_changed
        self.shape_drawn       = self.canvas.shape_drawn
        self.cursor_moved      = self.canvas.cursor_moved
        self.transform_changed = self.canvas.transform_changed
        self.shapes_moved      = self.canvas.shapes_moved
        self.shapes_resized    = self.canvas.shapes_resized
        self.shape_path_edited = self.canvas.shape_path_edited
        self.shape_text_edited = self.canvas.shape_text_edited
        self.shape_double_clicked = self.canvas.shape_double_clicked
        self.draw_shape        = self.canvas.draw_shape
        self.draw_layer        = self.canvas.draw_layer
        self.clear_shape       = self.canvas.clear_shape
        self.clear_layer       = self.canvas.clear_layer
        self.redraw_shape      = self.canvas.redraw_shape
        self.rebuild           = self.canvas.rebuild
        self.deselect_all      = self.canvas.deselect_all
        self.select_shape      = self.canvas.select_shape
        self.select_all        = self.canvas.select_all
        self.fit_view          = self.canvas.fit_view
        self.reset_zoom        = self.canvas.reset_zoom
        self.set_tool          = self.canvas.set_tool
        self.set_work_area     = self.canvas.set_work_area

    @property
    def selection_order(self) -> list[int]:
        return self.canvas.selection_order

    def _on_transform(self, ox: float, oy: float, sx: float, sy: float):
        self.h_ruler.update_from_transform(ox, sx)
        self.v_ruler.update_from_transform(oy, sy)

    def showEvent(self, event):
        super().showEvent(event)
        self.canvas._emit_transform()
