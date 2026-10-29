from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QToolButton, QFrame, QLabel, QDoubleSpinBox, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QSize

from core.theme import get_theme
from ui.widgets.icons import (
    make_icon,
    ICON_MIRROR_X, ICON_MIRROR_Y, ICON_ROTATE, ICON_ARRAY,
    ICON_ALIGN_LEFT, ICON_ALIGN_RIGHT, ICON_ALIGN_TOP,
    ICON_ALIGN_BOTTOM, ICON_ALIGN_CENTER_H, ICON_ALIGN_CENTER_V,
    ICON_UNDO, ICON_REDO, ICON_LOCK, ICON_UNLOCK,
    ICON_UNION, ICON_SUBTRACT, ICON_INTERSECT,
)


class OperationsBar(QWidget):
    """Full-width strip above the canvas: transform/utility operations that act on the current selection."""

    mirror_x_triggered = Signal()
    mirror_y_triggered = Signal()
    rotate_triggered    = Signal()
    array_triggered     = Signal()
    align_triggered     = Signal(str)   # mode: left/right/top/bottom/center_h/center_v
    union_triggered     = Signal()
    subtract_triggered  = Signal()
    intersect_triggered = Signal()
    undo_triggered      = Signal()
    redo_triggered      = Signal()
    size_changed        = Signal(float, float)   # w_mm, h_mm - requested by the user

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._align_btns: list[QToolButton] = []
        self._aspect_ratio = 1.0
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._build_ui()

    def _build_ui(self):
        t = get_theme()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.btn_undo = self._action_btn(ICON_UNDO, "Undo (Ctrl+Z)", self.undo_triggered.emit)
        self.btn_redo = self._action_btn(ICON_REDO, "Redo (Ctrl+Y)", self.redo_triggered.emit)
        layout.addWidget(self.btn_undo)
        layout.addWidget(self.btn_redo)
        layout.addWidget(self._divider())

        self.btn_mirror_x = self._action_btn(ICON_MIRROR_X, "Mirror on X axis",   self.mirror_x_triggered.emit)
        self.btn_mirror_y = self._action_btn(ICON_MIRROR_Y, "Mirror on Y axis",   self.mirror_y_triggered.emit)
        self.btn_rotate   = self._action_btn(ICON_ROTATE,   "Rotate selected...", self.rotate_triggered.emit)
        self.btn_array    = self._action_btn(ICON_ARRAY,    "Array / Duplicate",  self.array_triggered.emit)
        layout.addWidget(self.btn_mirror_x)
        layout.addWidget(self.btn_mirror_y)
        layout.addWidget(self.btn_rotate)
        layout.addWidget(self.btn_array)
        layout.addWidget(self._divider())

        self.btn_union     = self._action_btn(ICON_UNION,     "Union (2+ shapes)",     self.union_triggered.emit)
        self.btn_subtract  = self._action_btn(ICON_SUBTRACT,  "Subtract (2+ shapes, last selected = base)", self.subtract_triggered.emit)
        self.btn_intersect = self._action_btn(ICON_INTERSECT, "Intersect (2+ shapes)", self.intersect_triggered.emit)
        self._boolean_btns = [self.btn_union, self.btn_subtract, self.btn_intersect]
        layout.addWidget(self.btn_union)
        layout.addWidget(self.btn_subtract)
        layout.addWidget(self.btn_intersect)
        layout.addWidget(self._divider())

        align_lbl = QLabel("Align")
        align_lbl.setStyleSheet(f"color: {t.text_secondary}; font-size: 8pt; padding: 0 4px;")
        layout.addWidget(align_lbl)

        _ab = self._align_btn
        layout.addWidget(_ab(ICON_ALIGN_LEFT,     "Align left edges",         "left"))
        layout.addWidget(_ab(ICON_ALIGN_RIGHT,    "Align right edges",        "right"))
        layout.addWidget(_ab(ICON_ALIGN_TOP,      "Align top edges",          "top"))
        layout.addWidget(_ab(ICON_ALIGN_BOTTOM,   "Align bottom edges",       "bottom"))
        layout.addWidget(_ab(ICON_ALIGN_CENTER_H, "Align horizontal centres", "center_h"))
        layout.addWidget(_ab(ICON_ALIGN_CENTER_V, "Align vertical centres",   "center_v"))
        layout.addWidget(self._divider())

        size_lbl = QLabel("Size")
        size_lbl.setStyleSheet(f"color: {t.text_secondary}; font-size: 8pt; padding: 0 4px;")
        layout.addWidget(size_lbl)

        self.spin_w = self._size_spin("Width")
        self.spin_h = self._size_spin("Height")
        self.btn_lock_aspect = QToolButton()
        self.btn_lock_aspect.setCheckable(True)
        self.btn_lock_aspect.setIcon(make_icon(ICON_UNLOCK, t.text_secondary, t.icon_size))
        self.btn_lock_aspect.setIconSize(QSize(t.icon_size, t.icon_size))
        self.btn_lock_aspect.setFixedSize(t.tool_btn_size, t.tool_btn_size)
        self.btn_lock_aspect.setToolTip("Lock aspect ratio")
        self.btn_lock_aspect.toggled.connect(self._on_lock_toggled)

        layout.addWidget(QLabel("W:"))
        layout.addWidget(self.spin_w)
        layout.addWidget(self.btn_lock_aspect)
        layout.addWidget(QLabel("H:"))
        layout.addWidget(self.spin_h)

        layout.addStretch()

        self.spin_w.editingFinished.connect(self._on_w_finished)
        self.spin_h.editingFinished.connect(self._on_h_finished)

    def _size_spin(self, tooltip: str) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(0.01, 10000.0)
        spin.setDecimals(2)
        spin.setSuffix(" mm")
        spin.setFixedWidth(90)
        spin.setToolTip(tooltip)
        spin.setEnabled(False)
        return spin

    def _action_btn(self, svg, tooltip, slot) -> QToolButton:
        t   = get_theme()
        btn = QToolButton()
        btn.setIcon(make_icon(svg, t.text_secondary, t.icon_size))
        btn.setIconSize(QSize(t.icon_size, t.icon_size))
        btn.setFixedSize(t.tool_btn_size, t.tool_btn_size)
        btn.setToolTip(tooltip)
        btn.clicked.connect(slot)
        return btn

    def _align_btn(self, svg: str, tooltip: str, mode: str) -> QToolButton:
        t   = get_theme()
        btn = QToolButton()
        btn.setIcon(make_icon(svg, t.text_secondary, t.icon_size))
        btn.setIconSize(QSize(t.icon_size, t.icon_size))
        btn.setFixedSize(t.tool_btn_size, t.tool_btn_size)
        btn.setToolTip(tooltip)
        btn.clicked.connect(lambda _checked=False, m=mode: self.align_triggered.emit(m))
        self._align_btns.append(btn)
        return btn

    def _divider(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setFixedWidth(1)
        return line

    def _on_lock_toggled(self, checked: bool):
        t = get_theme()
        self.btn_lock_aspect.setIcon(
            make_icon(ICON_LOCK if checked else ICON_UNLOCK, t.text_secondary, t.icon_size)
        )
        if checked and self.spin_h.value() > 1e-6:
            self._aspect_ratio = self.spin_w.value() / self.spin_h.value()

    def _on_w_finished(self):
        w = self.spin_w.value()
        h = self.spin_h.value()
        if self.btn_lock_aspect.isChecked() and self._aspect_ratio > 1e-9:
            h = w / self._aspect_ratio
            self.spin_h.blockSignals(True)
            self.spin_h.setValue(h)
            self.spin_h.blockSignals(False)
        self.size_changed.emit(w, h)

    def _on_h_finished(self):
        w = self.spin_w.value()
        h = self.spin_h.value()
        if self.btn_lock_aspect.isChecked() and self._aspect_ratio > 1e-9:
            w = h * self._aspect_ratio
            self.spin_w.blockSignals(True)
            self.spin_w.setValue(w)
            self.spin_w.blockSignals(False)
        self.size_changed.emit(w, h)

    def set_size(self, w_mm: float, h_mm: float, enabled: bool):
        """Sync the W/H fields from the current selection without emitting size_changed."""
        self.spin_w.blockSignals(True)
        self.spin_h.blockSignals(True)
        self.spin_w.setValue(max(w_mm, 0.01))
        self.spin_h.setValue(max(h_mm, 0.01))
        self.spin_w.blockSignals(False)
        self.spin_h.blockSignals(False)
        self.spin_w.setEnabled(enabled)
        self.spin_h.setEnabled(enabled)
        self.btn_lock_aspect.setEnabled(enabled)
        if enabled and h_mm > 1e-9:
            self._aspect_ratio = w_mm / h_mm

    def set_util_enabled(self, enabled: bool):
        self.btn_mirror_x.setEnabled(enabled)
        self.btn_mirror_y.setEnabled(enabled)
        self.btn_rotate.setEnabled(enabled)
        self.btn_array.setEnabled(enabled)
        for btn in self._align_btns:
            btn.setEnabled(enabled)

    def set_boolean_enabled(self, enabled: bool):
        for btn in self._boolean_btns:
            btn.setEnabled(enabled)
