from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPen, QColor, QPainter, QFont
from PySide6.QtCore import Qt

from core.constants import PIXELS_PER_MM
from core.theme import get_theme


class RulerWidget(QWidget):
    """Mm-calibrated ruler that syncs to canvas zoom/pan via update_from_transform()."""

    @property
    def RULER_SIZE(self) -> int:
        return get_theme().ruler_size

    def __init__(self, orientation: str, parent=None):
        super().__init__(parent)
        self.orientation = orientation
        self._offset = 0.0
        self._scale  = 1.0
        self._apply_size()

    def _apply_size(self):
        if self.orientation == "horizontal":
            self.setFixedHeight(self.RULER_SIZE)
        else:
            self.setFixedWidth(self.RULER_SIZE)

    def update_from_transform(self, offset: float, scale: float):
        self._offset = offset
        self._scale  = scale
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        t    = get_theme()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        size = self.width() if self.orientation == "horizontal" else self.height()
        painter.fillRect(self.rect(), QColor(t.ruler_bg))

        ppm               = PIXELS_PER_MM * self._scale
        major_mm, minor_mm = _choose_tick_spacing(ppm)
        pen_major  = QPen(QColor(t.ruler_tick_major), 1)
        pen_minor  = QPen(QColor(t.ruler_tick_minor), 1)
        pen_text   = QPen(QColor(t.ruler_text), 1)

        painter.setFont(QFont("Helvetica", 7))

        start_mm   = -self._offset / ppm
        end_mm     = start_mm + size / ppm
        tick       = int(start_mm / minor_mm) * minor_mm

        while tick <= end_mm + minor_mm:
            pos      = self._offset + tick * ppm
            is_major = abs(round(tick / major_mm) * major_mm - tick) < 1e-6

            if self.orientation == "horizontal":
                tick_h = 12 if is_major else 6
                painter.setPen(pen_major if is_major else pen_minor)
                painter.drawLine(int(pos), self.RULER_SIZE - tick_h, int(pos), self.RULER_SIZE)
                if is_major and 0 <= pos <= size:
                    painter.setPen(pen_text)
                    painter.drawText(int(pos) + 2, self.RULER_SIZE - 10, f"{round(tick)}")
            else:
                tick_h = 12 if is_major else 6
                painter.setPen(pen_major if is_major else pen_minor)
                painter.drawLine(self.RULER_SIZE - tick_h, int(pos), self.RULER_SIZE, int(pos))
                if is_major and 0 <= pos <= size:
                    painter.setPen(pen_text)
                    painter.save()
                    painter.translate(self.RULER_SIZE - 10, int(pos) - 2)
                    painter.rotate(-90)
                    painter.drawText(0, 0, f"{round(tick)}")
                    painter.restore()

            tick = round(tick + minor_mm, 6)

        painter.setPen(QPen(QColor(t.border_subtle), 1))
        if self.orientation == "horizontal":
            painter.drawLine(0, self.RULER_SIZE - 1, self.width(), self.RULER_SIZE - 1)
        else:
            painter.drawLine(self.RULER_SIZE - 1, 0, self.RULER_SIZE - 1, self.height())
        painter.end()


# ── Tick spacing ──────────────────────────────────────────────────────────────

_MAJOR_STEPS = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000]
_MINOR_OF    = {1: 0.5, 2: 1, 5: 1, 10: 5, 20: 10,
                50: 10, 100: 50, 200: 100, 500: 100, 1000: 500}

MIN_MAJOR_PX = 50   # minimum pixels between major ticks


def _choose_tick_spacing(ppm: float) -> tuple[float, float]:
    """
    Pick major and minor tick intervals (mm) so that major ticks are
    at least MIN_MAJOR_PX pixels apart at the current zoom level.
    """
    min_major_mm = MIN_MAJOR_PX / ppm if ppm > 0 else _MAJOR_STEPS[-1]
    major_mm = _MAJOR_STEPS[-1]
    for step in _MAJOR_STEPS:
        if step >= min_major_mm:
            major_mm = step
            break
    return major_mm, _MINOR_OF[major_mm]
