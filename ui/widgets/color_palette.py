from PySide6.QtWidgets import QWidget, QSizePolicy
from PySide6.QtGui import QColor, QPainter, QPen, QBrush
from PySide6.QtCore import Qt, Signal, QRect

from core.theme import get_theme

PALETTE_COLORS = [
    "#000000", "#FF0000", "#FF6600", "#FFFF00", "#00FF00", "#008000",
    "#00FFFF", "#0000FF", "#8000FF", "#FF00FF", "#FF0080", "#804000",
    "#808000", "#008080", "#000080", "#800080", "#808080", "#C0C0C0",
    "#FFFFFF", "#FF8080",
]

SWATCH_SIZE   = 24
SWATCH_MARGIN = 3
PALETTE_HEIGHT = SWATCH_SIZE + SWATCH_MARGIN * 2


class ColorPaletteWidget(QWidget):
    """
    Horizontal strip of color swatches at the bottom of the canvas.
    Emits color_picked(color_hex) when clicked with shapes selected.
    """

    color_picked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._has_selection = False
        self._hovered_color = None
        self.setFixedHeight(PALETTE_HEIGHT)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setToolTip("Select shapes first, then click a color to reassign")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def set_has_selection(self, has_selection: bool):
        self._has_selection = has_selection
        self.update()

    def paintEvent(self, event):
        t = get_theme()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(t.border_subtle), 1))
        painter.setBrush(QBrush(QColor(t.panel_bg)))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 8, 8)

        painter.setPen(QPen(QColor(t.text_secondary)))
        painter.drawText(8, SWATCH_MARGIN + SWATCH_SIZE // 2 + 4, "Color:")

        for i, color in enumerate(PALETTE_COLORS):
            rect = self._swatch_rect(i)
            qc = QColor(color)
            if not self._has_selection:
                qc.setAlpha(80)
            is_hovered = (color == self._hovered_color and self._has_selection)
            painter.setBrush(QBrush(qc))
            if is_hovered:
                painter.setPen(QPen(QColor("#FFFFFF"), 2))
                painter.drawRoundedRect(rect.adjusted(-2, -2, 2, 2), 3, 3)
            else:
                painter.setPen(QPen(QColor("#555555"), 1))
                painter.drawRoundedRect(rect, 2, 2)
        painter.end()

    def mouseMoveEvent(self, event):
        color = self._color_at(event.pos().x(), event.pos().y())
        if color != self._hovered_color:
            self._hovered_color = color
            self.update()

    def leaveEvent(self, event):
        self._hovered_color = None
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._has_selection:
            color = self._color_at(event.pos().x(), event.pos().y())
            if color:
                self.color_picked.emit(color)

    def _swatch_rect(self, index: int) -> QRect:
        x = 52 + index * (SWATCH_SIZE + SWATCH_MARGIN)
        return QRect(x, SWATCH_MARGIN, SWATCH_SIZE, SWATCH_SIZE)

    def _color_at(self, x: int, y: int) -> str | None:
        for i, color in enumerate(PALETTE_COLORS):
            if self._swatch_rect(i).contains(x, y):
                return color
        return None
