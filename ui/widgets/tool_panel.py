from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QToolButton, QButtonGroup,
    QFrame, QMenu, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QAction

from core.theme import get_theme
from ui.canvas.tools.base_tool import ToolMode
from ui.widgets.icons import (
    make_icon,
    ICON_SELECT, ICON_POINT_EDIT,
    ICON_LINE, ICON_POLYLINE, ICON_RECT, ICON_NGON, ICON_CIRCLE, ICON_BEZIER, ICON_TEXT,
)

NGON_PRESETS = {
    "Triangle": 3, "Pentagon": 5, "Hexagon": 6,
    "Heptagon": 7, "Octagon": 8,
}


class ToolPanel(QWidget):
    """Vertical strip of tool buttons fixed to the left of the canvas."""

    tool_changed        = Signal(str)
    ngon_sides_changed  = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._current_tool = ToolMode.SELECT
        self._ngon_sides   = 6
        self._mode_group   = QButtonGroup(self)
        self._mode_group.setExclusive(True)
        self._build_ui()
        self._apply_styles()

    def _build_ui(self):
        t = get_theme()
        self.setFixedWidth(t.tool_btn_size + 12)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 8, 6, 8)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.btn_select     = self._mode_btn(ICON_SELECT,     "Select (Space)",  ToolMode.SELECT,    checked=True)
        self.btn_point_edit = self._mode_btn(ICON_POINT_EDIT, "Edit Points",     ToolMode.POINT_EDIT)
        layout.addWidget(self.btn_select)
        layout.addWidget(self.btn_point_edit)
        layout.addWidget(self._divider())

        self.btn_line     = self._mode_btn(ICON_LINE,     "Draw Line (L)",          ToolMode.LINE)
        self.btn_polyline = self._mode_btn(ICON_POLYLINE, "Draw Polyline (P)",      ToolMode.POLYLINE)
        self.btn_rect     = self._mode_btn(ICON_RECT,     "Draw Rectangle (Q)",     ToolMode.RECT)
        self.btn_ngon     = self._ngon_btn()
        self.btn_circle   = self._mode_btn(ICON_CIRCLE,   "Draw Circle/Ellipse (O)", ToolMode.CIRCLE)
        self.btn_bezier   = self._mode_btn(ICON_BEZIER,   "Bezier Pen - click for a corner, drag for a curve handle", ToolMode.BEZIER)
        self.btn_text     = self._mode_btn(ICON_TEXT,     "Text - click for artistic text, drag for a paragraph box", ToolMode.TEXT)
        layout.addWidget(self.btn_line)
        layout.addWidget(self.btn_polyline)
        layout.addWidget(self.btn_rect)
        layout.addWidget(self.btn_ngon)
        layout.addWidget(self.btn_circle)
        layout.addWidget(self.btn_bezier)
        layout.addWidget(self.btn_text)
        layout.addStretch()

        self._mode_group.buttonClicked.connect(self._on_mode_btn_clicked)

    def _mode_btn(self, svg, tooltip, mode, checked=False) -> QToolButton:
        t   = get_theme()
        btn = QToolButton()
        btn.setCheckable(True)
        btn.setChecked(checked)
        btn.setIcon(make_icon(svg, t.text_primary if checked else t.text_secondary, t.icon_size))
        btn.setIconSize(QSize(t.icon_size, t.icon_size))
        btn.setFixedSize(t.tool_btn_size, t.tool_btn_size)
        btn.setToolTip(tooltip)
        btn.setProperty("mode", mode)
        btn.setProperty("svg", svg)
        self._mode_group.addButton(btn)
        return btn

    def _ngon_btn(self) -> QToolButton:
        t   = get_theme()
        btn = QToolButton()
        btn.setCheckable(True)
        btn.setIcon(make_icon(ICON_NGON, t.text_secondary, t.icon_size))
        btn.setIconSize(QSize(t.icon_size, t.icon_size))
        btn.setFixedSize(t.tool_btn_size, t.tool_btn_size)
        btn.setToolTip("Draw Polygon (right-click to choose shape)")
        btn.setProperty("mode", ToolMode.NGON)
        btn.setProperty("svg", ICON_NGON)
        btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        btn.customContextMenuRequested.connect(self._show_ngon_menu)
        self._mode_group.addButton(btn)
        return btn

    def _divider(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFixedHeight(1)
        return line

    def _on_mode_btn_clicked(self, btn: QToolButton):
        t    = get_theme()
        mode = btn.property("mode")
        self._current_tool = mode
        for b in self._mode_group.buttons():
            b.setIcon(make_icon(b.property("svg"),
                                t.text_primary if b.isChecked() else t.text_secondary,
                                t.icon_size))
        self.tool_changed.emit(mode)

    def _show_ngon_menu(self, pos):
        menu = QMenu(self)
        for name, sides in NGON_PRESETS.items():
            action = QAction(name, self)
            action.setData(sides)
            menu.addAction(action)
        chosen = menu.exec(self.btn_ngon.mapToGlobal(pos))
        if chosen:
            sides = chosen.data()
            self._ngon_sides = sides
            self.btn_ngon.setToolTip(f"Draw {chosen.text()}  (right-click to change)")
            if not self.btn_ngon.isChecked():
                self.btn_ngon.setChecked(True)
                self._on_mode_btn_clicked(self.btn_ngon)
            self.ngon_sides_changed.emit(sides)

    # ── Public API ─────────────────────────────────────────────────────────────

    def set_tool(self, mode: str):
        for btn in self._mode_group.buttons():
            if btn.property("mode") == mode:
                btn.setChecked(True)
                self._on_mode_btn_clicked(btn)
                break

    def set_point_edit_enabled(self, enabled: bool):
        t = get_theme()
        self.btn_point_edit.setEnabled(enabled)
        color = t.text_secondary if enabled else t.text_disabled
        self.btn_point_edit.setIcon(make_icon(
            ICON_POINT_EDIT,
            t.text_primary if self.btn_point_edit.isChecked() else color,
            t.icon_size
        ))

    def current_tool(self) -> str:
        return self._current_tool

    def current_ngon_sides(self) -> int:
        return self._ngon_sides

    def _apply_styles(self):
        pass  # handled by global QSS from theme
