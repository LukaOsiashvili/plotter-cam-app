from __future__ import annotations
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Theme:
    # ── Meta ──────────────────────────────────────────────────────────────────
    name:    str = "Midnight CAM"
    author:  str = "Built-in"
    version: str = "1.0"

    # ── Application shell ──────────────────────────────────────────────────────
    app_bg:        str = "#111318"
    panel_bg:      str = "#1A1D24"
    surface:       str = "#22262F"
    surface_hover: str = "#2A3040"
    active:        str = "#1D3461"
    accent:        str = "#4CC9F0"
    accent_alt:    str = "#F72585"

    # ── Text ──────────────────────────────────────────────────────────────────
    text_primary:   str = "#E8EAF0"
    text_secondary: str = "#8890A0"
    text_disabled:  str = "#444A58"

    # ── Borders ───────────────────────────────────────────────────────────────
    border_subtle: str = "#2A2E38"
    border:        str = "#383D4A"

    # ── Canvas ────────────────────────────────────────────────────────────────
    canvas_bg:    str = "#1A1D24"
    work_area:    str = "#FAFAFA"
    selection:    str = "#4CC9F0"
    preview:      str = "#6C7A9C"
    draw_color:   str = "#000000"
    origin_cross: str = "#F72585"

    # ── Ruler ─────────────────────────────────────────────────────────────────
    ruler_bg:         str = "#1E2128"
    ruler_text:       str = "#8890A0"
    ruler_tick_major: str = "#8890A0"
    ruler_tick_minor: str = "#444A58"

    # ── Fonts ─────────────────────────────────────────────────────────────────
    font_ui:      str = "Segoe UI"
    font_ui_size: int = 9
    font_mono:    str = "Courier New"

    # ── Sizes ─────────────────────────────────────────────────────────────────
    tool_btn_size: int = 40
    icon_size:     int = 22
    ruler_size:    int = 20

    # ── Load / save ───────────────────────────────────────────────────────────

    @classmethod
    def load(cls, path: str | Path) -> Theme:
        with open(path, "rb") as f:
            data = tomllib.load(f)

        t = cls()
        meta = data.get("meta", {})
        t.name    = meta.get("name",    t.name)
        t.author  = meta.get("author",  t.author)
        t.version = meta.get("version", t.version)

        for key, val in data.get("colors", {}).items():
            if hasattr(t, key):
                setattr(t, key, val)

        fonts = data.get("fonts", {})
        if "ui" in fonts:
            ui = fonts["ui"]
            t.font_ui, t.font_ui_size = (ui[0], ui[1]) if isinstance(ui, list) else (ui, t.font_ui_size)
        if "mono" in fonts:
            mono = fonts["mono"]
            t.font_mono = mono[0] if isinstance(mono, list) else mono

        _size_map = {"tool_btn": "tool_btn_size", "icon": "icon_size", "ruler": "ruler_size"}
        for key, val in data.get("sizes", {}).items():
            attr = _size_map.get(key, key)
            if hasattr(t, attr):
                setattr(t, attr, int(val))

        return t

    # ── QSS generation ────────────────────────────────────────────────────────

    def to_qss(self) -> str:
        c = self
        fs    = c.font_ui_size
        fs_sm = max(fs - 1, 7)
        return f"""
/* ── Global ──────────────────────────────────────────────────────────────── */
QWidget {{
    background-color: {c.app_bg};
    color: {c.text_primary};
    font-family: "{c.font_ui}";
    font-size: {fs}pt;
    border: none;
    outline: none;
}}

/* ── Menu bar ────────────────────────────────────────────────────────────── */
QMenuBar {{
    background-color: {c.panel_bg};
    color: {c.text_primary};
    border-bottom: 1px solid {c.border_subtle};
    padding: 2px 4px;
}}
QMenuBar::item {{
    padding: 4px 10px;
    border-radius: 4px;
    background: transparent;
}}
QMenuBar::item:selected, QMenuBar::item:pressed {{
    background-color: {c.surface};
}}
QMenu {{
    background-color: {c.panel_bg};
    border: 1px solid {c.border};
    border-radius: 6px;
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 24px 6px 12px;
    border-radius: 4px;
}}
QMenu::item:selected {{
    background-color: {c.active};
    color: {c.text_primary};
}}
QMenu::separator {{
    height: 1px;
    background: {c.border_subtle};
    margin: 4px 8px;
}}

/* ── Toolbar ─────────────────────────────────────────────────────────────── */
QToolBar {{
    background-color: {c.panel_bg};
    border-bottom: 1px solid {c.border_subtle};
    padding: 2px 6px;
    spacing: 2px;
}}
QToolBar::separator {{
    background: {c.border_subtle};
    width: 1px;
    margin: 4px 4px;
}}
QToolBar QToolButton {{
    background-color: transparent;
    color: {c.text_primary};
    border: none;
    border-radius: 4px;
    padding: 4px 10px;
}}
QToolBar QToolButton:hover   {{ background-color: {c.surface}; }}
QToolBar QToolButton:pressed {{ background-color: {c.active}; }}

/* ── Status bar ──────────────────────────────────────────────────────────── */
QStatusBar {{
    background-color: {c.active};
    color: {c.text_primary};
    border-top: 1px solid {c.border_subtle};
    font-size: {fs_sm}pt;
    padding: 0 6px;
}}

/* ── Scroll bars ─────────────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background: {c.panel_bg};
    width: 8px;
    margin: 0;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: {c.border};
    border-radius: 4px;
    min-height: 20px;
}}
QScrollBar::handle:vertical:hover    {{ background: {c.text_secondary}; }}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical        {{ height: 0; }}
QScrollBar:horizontal {{
    background: {c.panel_bg};
    height: 8px;
    margin: 0;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal {{
    background: {c.border};
    border-radius: 4px;
    min-width: 20px;
}}
QScrollBar::handle:horizontal:hover  {{ background: {c.text_secondary}; }}
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal      {{ width: 0; }}

/* ── Tree widget ─────────────────────────────────────────────────────────── */
QTreeWidget {{
    background-color: {c.panel_bg};
    border: 1px solid {c.border_subtle};
    border-radius: 6px;
    outline: none;
}}
QTreeWidget::item {{
    padding: 3px 4px;
    border-radius: 3px;
}}
QTreeWidget::item:hover    {{ background-color: {c.surface}; }}
QTreeWidget::item:selected {{ background-color: {c.active}; color: {c.text_primary}; }}
QTreeWidget::branch        {{ background: {c.panel_bg}; }}

/* ── Inputs ──────────────────────────────────────────────────────────────── */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background-color: {c.surface};
    color: {c.text_primary};
    border: 1px solid {c.border};
    border-radius: 4px;
    padding: 4px 8px;
    selection-background-color: {c.active};
}}
QLineEdit:focus, QComboBox:focus,
QSpinBox:focus, QDoubleSpinBox:focus {{ border: 1px solid {c.accent}; }}
QLineEdit:disabled, QComboBox:disabled,
QSpinBox:disabled, QDoubleSpinBox:disabled {{
    color: {c.text_disabled};
    border-color: {c.border_subtle};
}}
QComboBox::drop-down   {{ border: none; width: 20px; }}
QComboBox::down-arrow  {{ width: 10px; height: 10px; }}
QComboBox QAbstractItemView {{
    background-color: {c.panel_bg};
    border: 1px solid {c.border};
    border-radius: 4px;
    selection-background-color: {c.active};
    outline: none;
}}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    background: {c.surface};
    border: none;
    width: 16px;
    border-radius: 2px;
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background: {c.active};
}}

/* ── Buttons ─────────────────────────────────────────────────────────────── */
QPushButton {{
    background-color: {c.surface};
    color: {c.text_primary};
    border: 1px solid {c.border};
    border-radius: 4px;
    padding: 5px 14px;
    font-weight: 500;
}}
QPushButton:hover   {{ background-color: {c.surface_hover}; border-color: {c.accent}; }}
QPushButton:pressed {{ background-color: {c.active}; }}
QPushButton:disabled {{ color: {c.text_disabled}; border-color: {c.border_subtle}; }}
QPushButton:checked {{ background-color: {c.active}; border-color: {c.accent}; }}

/* ── Tabs (text tabs with an accent underline) ───────────────────────────── */
QTabWidget::pane {{
    border: none;
    border-top: 1px solid {c.border_subtle};
    top: -1px;
    background: transparent;
}}
QTabWidget QStackedWidget, QTabWidget QStackedWidget > QWidget {{ background: transparent; }}
QTabBar {{ background: transparent; qproperty-drawBase: 0; }}
QTabBar::tab {{
    background: transparent;
    color: {c.text_secondary};
    border: none;
    border-bottom: 2px solid transparent;
    padding: 6px 14px;
    margin-right: 2px;
}}
QTabBar::tab:hover    {{ color: {c.text_primary}; }}
QTabBar::tab:selected {{ color: {c.text_primary}; border-bottom-color: {c.accent}; }}

/* ── Group boxes (settings dialogs) ─────────────────────────────────────── */
QGroupBox {{
    border: 1px solid {c.border_subtle};
    border-radius: 6px;
    margin-top: 16px;
    padding: 10px 8px 6px 8px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {c.text_secondary};
}}

/* ── Plain text views (logs) ─────────────────────────────────────────────── */
QPlainTextEdit {{
    background-color: {c.surface};
    border: 1px solid {c.border_subtle};
    border-radius: 4px;
    padding: 2px 4px;
}}

/* ── Machine panel: position readout card ────────────────────────────────── */
MachinePanel QFrame#positionCard {{
    background-color: {c.surface};
    border: 1px solid {c.border_subtle};
    border-radius: 6px;
}}

/* ── Dialog ──────────────────────────────────────────────────────────────── */
QDialog {{ background-color: {c.app_bg}; }}

/* ── Label ───────────────────────────────────────────────────────────────── */
QLabel {{ color: {c.text_primary}; background: transparent; }}

/* ── Frames / separators ─────────────────────────────────────────────────── */
QFrame[frameShape="4"], QFrame[frameShape="5"] {{
    color: {c.border_subtle};
    background: {c.border_subtle};
}}

/* ── Floating card panels (JetBrains-style tool windows) ────────────────────── */
ToolPanel, LayerPanel, CAMCanvasWithRulers, OperationsBar, MachinePanel {{
    background-color: {c.panel_bg};
    border: 1px solid {c.border_subtle};
    border-radius: 8px;
}}

/* ── Tool panel buttons ──────────────────────────────────────────────────── */
ToolPanel QToolButton {{
    background-color: transparent;
    border: none;
    border-left: 3px solid transparent;
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
    border-top-left-radius: 0px;
    border-bottom-left-radius: 0px;
    padding: 0px;
}}
ToolPanel QToolButton:hover    {{ background-color: {c.surface}; border-left-color: {c.border}; }}
ToolPanel QToolButton:checked  {{ background-color: {c.surface}; border-left-color: {c.accent}; }}
ToolPanel QToolButton:pressed  {{ background-color: {c.active}; }}
ToolPanel QToolButton:disabled {{ color: {c.text_disabled}; }}

/* ── Status bar permanent widgets ────────────────────────────────────────── */
QStatusBar QLabel {{
    background: transparent;
    color: {c.text_secondary};
    font-size: {fs_sm}pt;
    padding: 0 8px;
}}
QStatusBar QFrame[frameShape="5"] {{
    color: {c.border_subtle};
    background: {c.border_subtle};
    max-height: 14px;
    margin: 0 2px;
}}
"""


# ── Global theme accessor ─────────────────────────────────────────────────────

def get_theme() -> Theme:
    return _current


def set_theme(theme: Theme):
    global _current
    _current = theme


def builtin_themes_dir() -> Path:
    return Path(__file__).parent.parent / "themes"


def load_builtin(name: str) -> Theme:
    """Load one of the bundled themes by filename stem (e.g. 'midnight')."""
    path = builtin_themes_dir() / f"{name}.camtheme"
    return Theme.load(path)


DEFAULT_THEME = "jetbrains_dark"
_current: Theme = load_builtin(DEFAULT_THEME)
