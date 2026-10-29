from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QToolButton, QFrame, QLabel,
    QFontComboBox, QDoubleSpinBox, QButtonGroup, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QFont

from core.theme import get_theme
from ui.widgets.icons import (
    make_icon,
    ICON_BOLD, ICON_ITALIC,
    ICON_TEXT_ALIGN_LEFT, ICON_TEXT_ALIGN_CENTER, ICON_TEXT_ALIGN_RIGHT, ICON_TEXT_ALIGN_JUSTIFY,
)

_ALIGN_ICONS = {
    "left": ICON_TEXT_ALIGN_LEFT, "center": ICON_TEXT_ALIGN_CENTER,
    "right": ICON_TEXT_ALIGN_RIGHT, "justify": ICON_TEXT_ALIGN_JUSTIFY,
}


class TextToolbar(QWidget):
    """Font/alignment/spacing controls - CorelDRAW-style text property bar.
    Shown only while the Text tool is active or a text shape is selected."""

    style_changed = Signal(dict)   # partial TextData field updates, e.g. {"bold": True}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._align_btns: dict[str, QToolButton] = {}
        self._build_ui()

    def _build_ui(self):
        t = get_theme()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.font_combo = QFontComboBox()
        self.font_combo.setFixedWidth(150)
        self.font_combo.currentFontChanged.connect(
            lambda f: self.style_changed.emit({"font_family": f.family()})
        )
        layout.addWidget(self.font_combo)

        self.size_spin = QDoubleSpinBox()
        self.size_spin.setRange(1.0, 500.0)
        self.size_spin.setSuffix(" mm")
        self.size_spin.setDecimals(1)
        self.size_spin.setFixedWidth(80)
        self.size_spin.valueChanged.connect(lambda v: self.style_changed.emit({"font_size_mm": v}))
        layout.addWidget(self.size_spin)

        self.btn_bold   = self._toggle_btn(ICON_BOLD,   "Bold",   lambda v: self.style_changed.emit({"bold": v}))
        self.btn_italic = self._toggle_btn(ICON_ITALIC, "Italic", lambda v: self.style_changed.emit({"italic": v}))
        layout.addWidget(self.btn_bold)
        layout.addWidget(self.btn_italic)
        layout.addWidget(self._divider())

        align_group = QButtonGroup(self)
        align_group.setExclusive(True)
        for mode in ("left", "center", "right", "justify"):
            btn = QToolButton()
            btn.setCheckable(True)
            btn.setChecked(mode == "left")
            btn.setIcon(make_icon(_ALIGN_ICONS[mode], t.text_secondary, t.icon_size))
            btn.setIconSize(QSize(t.icon_size, t.icon_size))
            btn.setFixedSize(t.tool_btn_size, t.tool_btn_size)
            btn.setToolTip(f"Align {mode}" + ("  (paragraph text only)" if mode == "justify" else ""))
            btn.clicked.connect(lambda _checked=False, m=mode: self.style_changed.emit({"align": m}))
            align_group.addButton(btn)
            self._align_btns[mode] = btn
            layout.addWidget(btn)
        layout.addWidget(self._divider())

        self.line_spacing_spin = self._spacing_spin("Line spacing", suffix="x", minimum=0.5, maximum=5.0,
                                                      step=0.05, field="line_spacing")
        self.word_spacing_spin = self._spacing_spin("Word spacing (extra)", suffix=" mm", minimum=-5.0, maximum=50.0,
                                                      step=0.1, field="word_spacing_mm")
        self.letter_spacing_spin = self._spacing_spin("Letter spacing (extra, spaces excluded)", suffix=" mm",
                                                        minimum=-5.0, maximum=50.0, step=0.1, field="letter_spacing_mm")
        layout.addWidget(QLabel("Line:"))
        layout.addWidget(self.line_spacing_spin)
        layout.addWidget(QLabel("Word:"))
        layout.addWidget(self.word_spacing_spin)
        layout.addWidget(QLabel("Letter:"))
        layout.addWidget(self.letter_spacing_spin)

        layout.addStretch()

    def _spacing_spin(self, tooltip, suffix, minimum, maximum, step, field) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setSingleStep(step)
        spin.setSuffix(suffix)
        spin.setDecimals(2)
        spin.setFixedWidth(80)
        spin.setToolTip(tooltip)
        spin.valueChanged.connect(lambda v, f=field: self.style_changed.emit({f: v}))
        return spin

    def _toggle_btn(self, svg, tooltip, on_toggled) -> QToolButton:
        t   = get_theme()
        btn = QToolButton()
        btn.setCheckable(True)
        btn.setIcon(make_icon(svg, t.text_secondary, t.icon_size))
        btn.setIconSize(QSize(t.icon_size, t.icon_size))
        btn.setFixedSize(t.tool_btn_size, t.tool_btn_size)
        btn.setToolTip(tooltip)
        btn.toggled.connect(on_toggled)
        return btn

    def _divider(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setFixedWidth(1)
        return line

    # ── Sync from the current text object without re-emitting style_changed ──

    def set_values(self, text):
        widgets = [self.font_combo, self.size_spin, self.btn_bold, self.btn_italic,
                   self.line_spacing_spin, self.word_spacing_spin, self.letter_spacing_spin,
                   *self._align_btns.values()]
        for w in widgets:
            w.blockSignals(True)
        self.font_combo.setCurrentFont(QFont(text.font_family))
        self.size_spin.setValue(text.font_size_mm)
        self.btn_bold.setChecked(text.bold)
        self.btn_italic.setChecked(text.italic)
        self.line_spacing_spin.setValue(text.line_spacing)
        self.word_spacing_spin.setValue(text.word_spacing_mm)
        self.letter_spacing_spin.setValue(text.letter_spacing_mm)
        for mode, btn in self._align_btns.items():
            btn.setChecked(mode == text.align)
        self._align_btns["justify"].setEnabled(text.is_paragraph)
        for w in widgets:
            w.blockSignals(False)
