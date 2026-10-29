"""Compiles TextData -> Path (glyph outlines, real cubic curves - never flattened
polylines). Lives outside core/ because it's the one place that must depend on
Qt: font rasterization has no pure-Python equivalent in this stack.

Glyphs are built at a large fixed virtual point size (hinting disabled) and the
resulting path is scaled down to font_size_mm afterward - Qt's outline scaling
is non-linear at small point sizes (grid-fitting artifacts), but stable at
large ones, so this keeps glyph shapes faithful regardless of font_size_mm.
"""
from __future__ import annotations

from PySide6.QtGui import QFont, QFontMetricsF, QPainterPath

from core.document import TextData
from core.path_model import Path

VIRTUAL_PT        = 1000.0
LINE_HEIGHT_RATIO = 1.15   # nominal single-line height as a multiple of point size


def compile_text_path(text: TextData) -> Path:
    """One combined Path for the whole text block - used while text stays live."""
    if not text.content:
        return Path()
    scale = text.font_size_mm / VIRTUAL_PT
    qpp = QPainterPath()
    for ch, x, y, font in _iter_glyphs(text):
        qpp.addText(x, y, font, ch)
    return _qpainterpath_to_path(qpp, scale)


def compile_text_glyphs(text: TextData) -> list[Path]:
    """One Path per subpath/contour - used by Convert to Curves. A glyph is
    not one shape: 'O' has an outer ring and an inner hole as two separate
    contours, 'i' has a dot and a stem - each becomes its own independently
    selectable/editable shape, matching normal CAD/CAM part-selection."""
    if not text.content:
        return []
    scale = text.font_size_mm / VIRTUAL_PT
    paths = []
    for ch, x, y, font in _iter_glyphs(text):
        qpp = QPainterPath()
        qpp.addText(x, y, font, ch)
        paths.extend(_qpainterpath_to_split_paths(qpp, scale))
    return paths


# ── Shared layout ────────────────────────────────────────────────────────────────

def _make_font(text: TextData) -> QFont:
    font = QFont(text.font_family)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    font.setBold(text.bold)
    font.setItalic(text.italic)
    font.setPointSizeF(VIRTUAL_PT)
    return font


def _iter_glyphs(text: TextData):
    """Yields (char, x, baseline_y, font) for every non-space glyph, in virtual
    (pre-scale) units - the single source of layout truth for both compilers."""
    font  = _make_font(text)
    fm    = QFontMetricsF(font)
    scale = text.font_size_mm / VIRTUAL_PT

    def to_units(mm: float) -> float:
        return mm / scale

    letter_sp = to_units(text.letter_spacing_mm)
    word_sp   = to_units(text.word_spacing_mm)
    line_h    = VIRTUAL_PT * LINE_HEIGHT_RATIO * max(text.line_spacing, 0.01)
    x0        = to_units(text.x_mm)
    y0        = to_units(text.y_mm)
    ascent    = fm.ascent()

    if text.is_paragraph:
        box_w = to_units(text.box_w_mm)
        lines = _wrap_paragraph(text.content, fm, box_w, letter_sp, word_sp)
        ref_w = box_w
    else:
        lines = [(_line_width(ln, fm, letter_sp, word_sp), ln) for ln in text.content.split("\n")]
        ref_w = max((w for w, _ in lines), default=0.0)

    for li, (line_w, line_text) in enumerate(lines):
        justify = text.is_paragraph and text.align == "justify" and li < len(lines) - 1
        extra_word_sp = 0.0
        if justify and line_text.strip():
            spaces = line_text.count(" ")
            if spaces > 0:
                extra_word_sp = max(0.0, (ref_w - line_w) / spaces)

        if text.align == "center":
            line_x = x0 + (ref_w - line_w) / 2
        elif text.align == "right":
            line_x = x0 + (ref_w - line_w)
        else:
            line_x = x0

        baseline_y = y0 + ascent + li * line_h
        cursor = line_x
        n = len(line_text)
        eff_word_sp = word_sp + extra_word_sp
        for i, ch in enumerate(line_text):
            if ch != " ":
                yield ch, cursor, baseline_y, font
            cursor += fm.horizontalAdvance(ch)
            if i < n - 1:
                cursor += eff_word_sp if ch == " " else letter_sp


def _line_width(line: str, fm: QFontMetricsF, letter_sp: float, word_sp: float) -> float:
    w = 0.0
    n = len(line)
    for i, ch in enumerate(line):
        w += fm.horizontalAdvance(ch)
        if i < n - 1:
            w += word_sp if ch == " " else letter_sp
    return w


def _wrap_paragraph(content: str, fm: QFontMetricsF, box_w: float,
                     letter_sp: float, word_sp: float) -> list[tuple[float, str]]:
    lines: list[tuple[float, str]] = []
    for para in content.split("\n"):
        words = para.split(" ")
        current = ""
        for word in words:
            candidate = f"{current} {word}" if current else word
            if current and _line_width(candidate, fm, letter_sp, word_sp) > box_w:
                lines.append((_line_width(current, fm, letter_sp, word_sp), current))
                current = word
            else:
                current = candidate
        lines.append((_line_width(current, fm, letter_sp, word_sp), current))
    return lines


# ── QPainterPath -> our Path model (preserves real cubic curves) ────────────────

def _qpainterpath_to_path(qpp: QPainterPath, scale: float) -> Path:
    path = Path()
    n = qpp.elementCount()
    i = 0
    started = False
    while i < n:
        el = qpp.elementAt(i)
        t  = el.type
        if t == QPainterPath.ElementType.MoveToElement:
            if started:
                path.close()
            path.move_to(el.x * scale, el.y * scale)
            started = True
            i += 1
        elif t == QPainterPath.ElementType.LineToElement:
            path.line_to(el.x * scale, el.y * scale)
            i += 1
        elif t == QPainterPath.ElementType.CurveToElement:
            c1  = el
            c2  = qpp.elementAt(i + 1)
            end = qpp.elementAt(i + 2)
            path.cubic_to(c1.x * scale, c1.y * scale, c2.x * scale, c2.y * scale, end.x * scale, end.y * scale)
            i += 3
        else:
            i += 1
    if started:
        path.close()
    return path


def _qpainterpath_to_split_paths(qpp: QPainterPath, scale: float) -> list[Path]:
    """Like _qpainterpath_to_path, but each subpath (MoveTo boundary) becomes
    its own separate Path instead of being merged into one."""
    paths: list[Path] = []
    current: Path | None = None
    n = qpp.elementCount()
    i = 0
    while i < n:
        el = qpp.elementAt(i)
        t  = el.type
        if t == QPainterPath.ElementType.MoveToElement:
            if current is not None:
                current.close()
                paths.append(current)
            current = Path()
            current.move_to(el.x * scale, el.y * scale)
            i += 1
        elif t == QPainterPath.ElementType.LineToElement:
            current.line_to(el.x * scale, el.y * scale)
            i += 1
        elif t == QPainterPath.ElementType.CurveToElement:
            c1  = el
            c2  = qpp.elementAt(i + 1)
            end = qpp.elementAt(i + 2)
            current.cubic_to(c1.x * scale, c1.y * scale, c2.x * scale, c2.y * scale, end.x * scale, end.y * scale)
            i += 3
        else:
            i += 1
    if current is not None:
        current.close()
        paths.append(current)
    return paths
