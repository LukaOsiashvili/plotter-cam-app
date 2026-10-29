"""Toolpath simulation - Phase 4. A dedicated window (not a canvas overlay)
that animates core/toolpath.py's SimSegment list: pen-down strokes drawn
solid in the layer's color, pen-up travel drawn dashed, played back against
real (speed/rapid_speed-derived) timing so the elapsed/total clock is an
honest dry-run estimate, not just a progress bar."""
from __future__ import annotations
import bisect
from dataclasses import dataclass

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QPushButton,
    QSlider, QComboBox, QLabel, QSizePolicy
)
from PySide6.QtGui import QPainter, QPen, QColor, QBrush
from PySide6.QtCore import Qt, QTimer

from core.document import Document
from core.toolpath import SimSegment
from core.exporters.gcode import generate_gcode
from core.gcode_parser import parse_gcode
from core.theme import get_theme

_SPEED_OPTIONS = [1, 2, 5, 10, 20, 50, 100]
_TICK_MS = 33


def _format_time(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m:02}m {s:02}s" if h else f"{m}m {s:02}s"


def _partial_points(points: list[tuple[float, float]], fraction: float) -> list[tuple[float, float]]:
    """Points array truncated to `fraction` of the polyline's total length,
    with the cut point interpolated (constant speed along the stroke)."""
    if fraction <= 0 or len(points) < 2:
        return points[:1]
    if fraction >= 1:
        return points

    total = sum(
        ((points[i+1][0]-points[i][0])**2 + (points[i+1][1]-points[i][1])**2) ** 0.5
        for i in range(len(points) - 1)
    )
    target = total * fraction
    acc = 0.0
    out = [points[0]]
    for i in range(len(points) - 1):
        x0, y0 = points[i]
        x1, y1 = points[i + 1]
        seg_len = ((x1-x0)**2 + (y1-y0)**2) ** 0.5
        if acc + seg_len >= target or seg_len == 0:
            t = 0 if seg_len == 0 else (target - acc) / seg_len
            out.append((x0 + (x1-x0)*t, y0 + (y1-y0)*t))
            return out
        acc += seg_len
        out.append((x1, y1))
    return out


class _SimCanvas(QWidget):
    def __init__(self, work_w_mm: float, work_h_mm: float, segments: list[SimSegment], parent=None):
        super().__init__(parent)
        self.work_w_mm = work_w_mm
        self.work_h_mm = work_h_mm
        self.segments = segments
        self._cum_end = []
        acc = 0.0
        for seg in segments:
            acc += seg.duration_s
            self._cum_end.append(acc)
        self.total_duration = acc
        self._elapsed = 0.0
        self.setMinimumSize(300, 300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_elapsed(self, t: float):
        self._elapsed = max(0.0, min(t, self.total_duration))
        self.update()

    def _transform(self):
        t = get_theme()
        margin = 16
        avail_w = max(self.width() - 2 * margin, 1)
        avail_h = max(self.height() - 2 * margin, 1)
        scale = min(avail_w / max(self.work_w_mm, 1e-6), avail_h / max(self.work_h_mm, 1e-6))
        ox = (self.width() - self.work_w_mm * scale) / 2
        oy = (self.height() - self.work_h_mm * scale) / 2
        return scale, ox, oy

    def paintEvent(self, event):
        theme = get_theme()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(theme.canvas_bg))

        scale, ox, oy = self._transform()

        def to_px(pt):
            return (ox + pt[0] * scale, oy + pt[1] * scale)

        painter.setPen(QPen(QColor(theme.border), 1))
        painter.setBrush(QBrush(QColor(theme.work_area)))
        painter.drawRect(int(ox), int(oy), int(self.work_w_mm * scale), int(self.work_h_mm * scale))

        if not self.segments:
            painter.end()
            return

        idx = bisect.bisect_left(self._cum_end, self._elapsed)
        idx = min(idx, len(self.segments) - 1)
        prev_end = self._cum_end[idx - 1] if idx > 0 else 0.0

        travel_pen = QPen(QColor(theme.preview), 1, Qt.PenStyle.DashLine)
        head_pos = None

        for i, seg in enumerate(self.segments):
            if i > idx:
                break
            if i < idx:
                pts = seg.points
            else:
                seg_frac = 0.0
                if seg.duration_s > 1e-9:
                    seg_frac = (self._elapsed - prev_end) / seg.duration_s
                pts = _partial_points(seg.points, seg_frac)

            if len(pts) >= 2:
                if seg.pen_down:
                    painter.setPen(QPen(QColor(seg.color or theme.draw_color), 2))
                else:
                    painter.setPen(travel_pen)
                px_pts = [to_px(p) for p in pts]
                for a, b in zip(px_pts, px_pts[1:]):
                    painter.drawLine(a[0], a[1], b[0], b[1])

            if pts:
                head_pos = pts[-1]

        if head_pos is not None:
            hx, hy = to_px(head_pos)
            pen_down = self.segments[idx].pen_down
            painter.setPen(QPen(QColor(theme.accent), 1.5))
            painter.setBrush(QBrush(QColor(theme.accent) if pen_down else Qt.BrushStyle.NoBrush))
            painter.drawEllipse(hx - 4, hy - 4, 8, 8)

        painter.end()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update()


class SimulationWindow(QDialog):
    """Standalone dry-run preview of a document's toolpath. Not modal to the
    canvas - you can leave it open while continuing to edit, since it never
    holds a live reference back into Document (matches the toolpath/G-code
    decoupling convention elsewhere).

    Animates the actual generated G-code (core/exporters/gcode.py, parsed
    back via core/gcode_parser.py) rather than an independent walk of
    Document - so this is provably what the exported file will do, not a
    second derivation that can silently drift out of sync with it. Only
    per-move timing still needs a Document lookup (speed/rapid_speed by
    layer name), since the G-code dialect itself carries no feedrate."""

    def __init__(self, document: Document, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Toolpath Simulation")
        self.resize(720, 640)

        gcode_text = generate_gcode(document)
        segments = parse_gcode(document, gcode_text)
        self.canvas = _SimCanvas(document.work_w_mm, document.work_h_mm, segments)

        self._timer = QTimer(self)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._on_tick)
        self._playing = False

        self._build_ui()
        self._update_time_labels()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(self.canvas, 1)

        controls = QHBoxLayout()

        self.btn_play = QPushButton("Play")
        self.btn_play.clicked.connect(self._toggle_play)
        controls.addWidget(self.btn_play)

        self.btn_stop = QPushButton("Stop")
        self.btn_stop.clicked.connect(self._stop)
        controls.addWidget(self.btn_stop)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, int(self.canvas.total_duration * 1000))
        self.slider.sliderMoved.connect(self._on_slider_moved)
        controls.addWidget(self.slider, 1)

        self.lbl_time = QLabel()
        controls.addWidget(self.lbl_time)

        controls.addWidget(QLabel("Speed:"))
        self.combo_speed = QComboBox()
        for m in _SPEED_OPTIONS:
            self.combo_speed.addItem(f"{m}x", m)
        default_idx = len(_SPEED_OPTIONS) - 1
        for i, m in enumerate(_SPEED_OPTIONS):
            if self.canvas.total_duration / m <= 20:
                default_idx = i
                break
        self.combo_speed.setCurrentIndex(default_idx)
        controls.addWidget(self.combo_speed)

        layout.addLayout(controls)

    def _toggle_play(self):
        if self.canvas.total_duration <= 0:
            return
        if self._elapsed_is_finished():
            self.canvas.set_elapsed(0.0)
        self._playing = not self._playing
        self.btn_play.setText("Pause" if self._playing else "Play")
        if self._playing:
            self._timer.start()
        else:
            self._timer.stop()

    def _stop(self):
        self._playing = False
        self._timer.stop()
        self.btn_play.setText("Play")
        self.canvas.set_elapsed(0.0)
        self.slider.setValue(0)
        self._update_time_labels()

    def _elapsed_is_finished(self) -> bool:
        return self.canvas._elapsed >= self.canvas.total_duration - 1e-6

    def _on_tick(self):
        speed = self.combo_speed.currentData()
        elapsed = self.canvas._elapsed + (_TICK_MS / 1000.0) * speed
        self.canvas.set_elapsed(elapsed)
        self.slider.setValue(int(self.canvas._elapsed * 1000))
        self._update_time_labels()
        if self._elapsed_is_finished():
            self._playing = False
            self._timer.stop()
            self.btn_play.setText("Play")

    def _on_slider_moved(self, value: int):
        self.canvas.set_elapsed(value / 1000.0)
        self._update_time_labels()

    def _update_time_labels(self):
        self.lbl_time.setText(
            f"{_format_time(self.canvas._elapsed)} / {_format_time(self.canvas.total_duration)}"
        )
