from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor
from PySide6.QtCore import Qt, QByteArray
from PySide6.QtSvg import QSvgRenderer


def make_icon(svg_str: str, color: str = "#CCCCCC", size: int = 22) -> QIcon:
    colored_svg = svg_str.replace("currentColor", color)
    data = QByteArray(colored_svg.encode("utf-8"))
    renderer = QSvgRenderer(data)

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()

    return QIcon(pixmap)


# ── Mode tools ────────────────────────────────────────────────────────────────

ICON_SELECT = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">
  <path d="M5 3 L5 19 L9 15 L12.5 22 L14.5 21 L11 14 L17 14 Z"
        fill="currentColor"/>
</svg>"""

ICON_POINT_EDIT = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">
  <path d="M4 20 L10 10 L14 15 L17 8 L20 4"
        stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
  <rect x="2.5" y="18.5" width="3" height="3" rx="0.5" fill="currentColor"/>
  <rect x="8.5"  y="8.5"  width="3" height="3" rx="0.5" fill="currentColor"/>
  <rect x="12.5" y="13.5" width="3" height="3" rx="0.5" fill="currentColor"/>
  <rect x="15.5" y="6.5"  width="3" height="3" rx="0.5" fill="currentColor"/>
  <rect x="18.5" y="2.5"  width="3" height="3" rx="0.5" fill="currentColor"/>
</svg>"""

# ── Draw tools ────────────────────────────────────────────────────────────────

ICON_LINE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">
  <line x1="4" y1="20" x2="20" y2="4"
        stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
  <circle cx="4"  cy="20" r="2" fill="currentColor"/>
  <circle cx="20" cy="4"  r="2" fill="currentColor"/>
</svg>"""

ICON_POLYLINE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">
  <polyline points="3,20 8,10 13,15 18,6 21,8"
            stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
  <circle cx="3"  cy="20" r="1.8" fill="currentColor"/>
  <circle cx="8"  cy="10" r="1.8" fill="currentColor"/>
  <circle cx="13" cy="15" r="1.8" fill="currentColor"/>
  <circle cx="18" cy="6"  r="1.8" fill="currentColor"/>
  <circle cx="21" cy="8"  r="1.8" fill="currentColor"/>
</svg>"""

ICON_RECT = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">
  <rect x="3" y="6" width="18" height="12" rx="1"
        stroke="currentColor" stroke-width="2" fill="none"/>
</svg>"""

ICON_NGON = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">
  <polygon points="12,3 20.5,7.5 20.5,16.5 12,21 3.5,16.5 3.5,7.5"
           stroke="currentColor" stroke-width="2" fill="none" stroke-linejoin="round"/>
</svg>"""

ICON_CIRCLE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">
  <circle cx="12" cy="12" r="9"
          stroke="currentColor" stroke-width="2" fill="none"/>
</svg>"""

ICON_BEZIER = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">
  <path d="M4 19 C4 10, 20 14, 20 5"
        stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/>
  <line x1="4" y1="19" x2="9" y2="8" stroke="currentColor" stroke-width="1" stroke-dasharray="1.5,1.5"/>
  <line x1="20" y1="5" x2="15" y2="16" stroke="currentColor" stroke-width="1" stroke-dasharray="1.5,1.5"/>
  <circle cx="4"  cy="19" r="2" fill="currentColor"/>
  <circle cx="20" cy="5"  r="2" fill="currentColor"/>
  <circle cx="9"  cy="8"  r="1.5" fill="currentColor" opacity="0.6"/>
  <circle cx="15" cy="16" r="1.5" fill="currentColor" opacity="0.6"/>
</svg>"""

ICON_TEXT = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">
  <path d="M4 5 H20 M12 5 V19" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
  <path d="M8 19 H16" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
</svg>"""

# ── Layer panel ───────────────────────────────────────────────────────────────

ICON_EYE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">
  <path d="M2 12 C5 6, 19 6, 22 12 C19 18, 5 18, 2 12 Z"
        stroke="currentColor" stroke-width="1.8" fill="none" stroke-linejoin="round"/>
  <circle cx="12" cy="12" r="2.8" fill="currentColor"/>
</svg>"""

ICON_EYE_OFF = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">
  <path d="M2 12 C5 6, 19 6, 22 12"
        stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round"/>
  <line x1="4" y1="20" x2="20" y2="4"
        stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
</svg>"""

ICON_LOCK = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">
  <rect x="5" y="11" width="14" height="9" rx="2" fill="currentColor" opacity="0.85"/>
  <path d="M8 11 V8 A4 4 0 0 1 16 8 V11"
        stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/>
</svg>"""

ICON_UNLOCK = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">
  <rect x="5" y="11" width="14" height="9" rx="2" fill="currentColor" opacity="0.35"/>
  <path d="M8 11 V8 A4 4 0 0 1 16 8"
        stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/>
</svg>"""

# ── Util tools ────────────────────────────────────────────────────────────────

ICON_MIRROR_X = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">
  <line x1="12" y1="2" x2="12" y2="22"
        stroke="currentColor" stroke-width="1.5" stroke-dasharray="2,2"/>
  <path d="M12 6 L5 12 L12 18" fill="currentColor" opacity="1"/>
  <path d="M12 6 L19 12 L12 18" fill="currentColor" opacity="0.4"/>
</svg>"""

ICON_MIRROR_Y = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">
  <line x1="2" y1="12" x2="22" y2="12"
        stroke="currentColor" stroke-width="1.5" stroke-dasharray="2,2"/>
  <path d="M6 12 L12 5 L18 12" fill="currentColor" opacity="1"/>
  <path d="M6 12 L12 19 L18 12" fill="currentColor" opacity="0.4"/>
</svg>"""

ICON_ARRAY = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">
  <rect x="3"  y="3"  width="5" height="5" rx="1" fill="currentColor"/>
  <rect x="10" y="3"  width="5" height="5" rx="1" fill="currentColor" opacity="0.6"/>
  <rect x="17" y="3"  width="5" height="5" rx="1" fill="currentColor" opacity="0.35"/>
  <rect x="3"  y="10" width="5" height="5" rx="1" fill="currentColor" opacity="0.6"/>
  <rect x="10" y="10" width="5" height="5" rx="1" fill="currentColor" opacity="0.35"/>
  <rect x="3"  y="17" width="5" height="5" rx="1" fill="currentColor" opacity="0.35"/>
</svg>"""

ICON_ROTATE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">
  <path d="M12 3 A9 9 0 1 1 21 12"
        stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/>
  <polyline points="18,9 21,12 24,9"
        stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
</svg>"""

# ── Undo / Redo ───────────────────────────────────────────────────────────────

ICON_UNDO = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">
  <path d="M6 8 H15 A6 6 0 1 1 15 20 H11"
        stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/>
  <polyline points="9,4 5,8 9,12"
        stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
</svg>"""

ICON_REDO = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">
  <path d="M18 8 H9 A6 6 0 1 0 9 20 H13"
        stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/>
  <polyline points="15,4 19,8 15,12"
        stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
</svg>"""

# ── Align ─────────────────────────────────────────────────────────────────────

ICON_ALIGN_LEFT = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">
  <line x1="4" y1="2" x2="4" y2="22" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"/>
  <rect x="4" y="5"  width="13" height="5" rx="1" fill="currentColor"/>
  <rect x="4" y="14" width="9"  height="5" rx="1" fill="currentColor" opacity="0.55"/>
</svg>"""

ICON_ALIGN_RIGHT = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">
  <line x1="20" y1="2" x2="20" y2="22" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"/>
  <rect x="7"  y="5"  width="13" height="5" rx="1" fill="currentColor"/>
  <rect x="11" y="14" width="9"  height="5" rx="1" fill="currentColor" opacity="0.55"/>
</svg>"""

ICON_ALIGN_TOP = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">
  <line x1="2" y1="4" x2="22" y2="4" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"/>
  <rect x="5"  y="4" width="5" height="13" rx="1" fill="currentColor"/>
  <rect x="14" y="4" width="5" height="9"  rx="1" fill="currentColor" opacity="0.55"/>
</svg>"""

ICON_ALIGN_BOTTOM = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">
  <line x1="2" y1="20" x2="22" y2="20" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"/>
  <rect x="5"  y="7"  width="5" height="13" rx="1" fill="currentColor"/>
  <rect x="14" y="11" width="5" height="9"  rx="1" fill="currentColor" opacity="0.55"/>
</svg>"""

ICON_ALIGN_CENTER_H = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">
  <line x1="12" y1="2" x2="12" y2="22" stroke="currentColor" stroke-width="1.5" stroke-dasharray="2.5,2"/>
  <rect x="6"  y="5"  width="12" height="5" rx="1" fill="currentColor"/>
  <rect x="8"  y="14" width="8"  height="5" rx="1" fill="currentColor" opacity="0.55"/>
</svg>"""

ICON_ALIGN_CENTER_V = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">
  <line x1="2" y1="12" x2="22" y2="12" stroke="currentColor" stroke-width="1.5" stroke-dasharray="2.5,2"/>
  <rect x="5"  y="6"  width="5" height="12" rx="1" fill="currentColor"/>
  <rect x="14" y="8"  width="5" height="8"  rx="1" fill="currentColor" opacity="0.55"/>
</svg>"""

# ── Boolean ops ───────────────────────────────────────────────────────────────

ICON_UNION = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">
  <circle cx="9"  cy="12" r="7" fill="currentColor"/>
  <circle cx="15" cy="12" r="7" fill="currentColor" opacity="0.75"/>
</svg>"""

ICON_SUBTRACT = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">
  <path d="M16,12 A7,7 0 1,1 2,12 A7,7 0 1,1 16,12 Z
           M22,12 A7,7 0 1,1 8,12 A7,7 0 1,1 22,12 Z"
        fill="currentColor" fill-rule="evenodd"/>
</svg>"""

ICON_INTERSECT = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">
  <defs><clipPath id="clip-intersect"><circle cx="9" cy="12" r="7"/></clipPath></defs>
  <circle cx="9"  cy="12" r="7" stroke="currentColor" stroke-width="1.5" fill="none"/>
  <circle cx="15" cy="12" r="7" stroke="currentColor" stroke-width="1.5" fill="none"/>
  <circle cx="15" cy="12" r="7" fill="currentColor" clip-path="url(#clip-intersect)"/>
</svg>"""

# ── Text alignment ────────────────────────────────────────────────────────────

ICON_TEXT_ALIGN_LEFT = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">
  <rect x="3" y="5"  width="18" height="2" rx="1" fill="currentColor"/>
  <rect x="3" y="11" width="12" height="2" rx="1" fill="currentColor"/>
  <rect x="3" y="17" width="15" height="2" rx="1" fill="currentColor"/>
</svg>"""

ICON_TEXT_ALIGN_CENTER = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">
  <rect x="3" y="5"  width="18" height="2" rx="1" fill="currentColor"/>
  <rect x="6" y="11" width="12" height="2" rx="1" fill="currentColor"/>
  <rect x="4.5" y="17" width="15" height="2" rx="1" fill="currentColor"/>
</svg>"""

ICON_TEXT_ALIGN_RIGHT = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">
  <rect x="3" y="5"  width="18" height="2" rx="1" fill="currentColor"/>
  <rect x="9" y="11" width="12" height="2" rx="1" fill="currentColor"/>
  <rect x="6" y="17" width="15" height="2" rx="1" fill="currentColor"/>
</svg>"""

ICON_TEXT_ALIGN_JUSTIFY = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">
  <rect x="3" y="5"  width="18" height="2" rx="1" fill="currentColor"/>
  <rect x="3" y="11" width="18" height="2" rx="1" fill="currentColor"/>
  <rect x="3" y="17" width="18" height="2" rx="1" fill="currentColor"/>
</svg>"""

# ── Bold / Italic ─────────────────────────────────────────────────────────────

ICON_BOLD = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">
  <path d="M7 4 H14 A4 4 0 0 1 14 12 H7 Z M7 12 H15 A4.2 4.2 0 0 1 15 20 H7 Z"
        fill="currentColor"/>
</svg>"""

ICON_ITALIC = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">
  <path d="M11 4 H18 M6 20 H13 M14.5 4 L9.5 20"
        stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
</svg>"""
