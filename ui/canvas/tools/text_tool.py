from __future__ import annotations
from dataclasses import replace
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPen, QColor, QBrush, QFont, QTextBlockFormat, QTextCursor, QTextCharFormat
from PySide6.QtWidgets import QTextEdit

from core.document import Shape, TextData
from core.constants import PIXELS_PER_MM
from core.theme import get_theme
from ui.canvas.tools.base_tool import BaseTool
from ui.text_engine import compile_text_path

if TYPE_CHECKING:
    from ui.canvas.canvas import CAMCanvas
    from core.document import Document

DRAG_THRESHOLD_PX  = 8.0
RESIZE_HANDLE_PX   = 10.0


class TextTool(BaseTool):
    """
    Click places artistic text (grows freely); click-and-drag places a
    paragraph text box (wraps to width). An overlay QTextEdit handles the
    actual typing - WYSIWYG-ish (matching font/size/style), styled and
    positioned to sit over the text's real location. Committing (clicking
    elsewhere, switching tool, or a style change while creating new text)
    compiles the real glyph-outline Path via ui/text_engine and emits it;
    Escape cancels without creating/changing anything.

    Activating this tool with a single text shape already selected re-opens
    its editor in place - the CorelDRAW convention for re-editing live text.
    """

    def __init__(self, canvas: CAMCanvas, document: Document, on_finished_editing_existing=None):
        super().__init__(canvas)
        self._document = document
        self._on_finished_editing_existing = on_finished_editing_existing
        self._defaults = TextData()
        self._editor: QTextEdit | None = None
        self._editing_shape: Shape | None = None
        self._current_text: TextData | None = None

        self._drag_start: QPointF | None = None
        self._drag_start_vp = None
        self._live_pos: QPointF | None = None
        self._suppress_notify = False
        self._resizing_box = False   # dragging the paragraph box's resize handle while editing

    def activate(self):
        self._canvas.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        ids = self._canvas.selected_ids
        if len(ids) == 1:
            _, shape = self._document.find_shape(next(iter(ids)))
            if shape is not None and shape.text is not None:
                self._open_editor(shape.text, existing_shape=shape)

    def deactivate(self):
        self._suppress_notify = True   # being switched away from deliberately - don't fight it by requesting Select
        self._commit()
        self._suppress_notify = False
        self._canvas.viewport().setCursor(Qt.CursorShape.ArrowCursor)

    def handle_key(self, event) -> bool:
        if event.key() == Qt.Key.Key_Escape and self._editor is not None:
            self._cancel()
            return True
        return False

    # ── Placement (new text only - re-edit skips straight to _open_editor) ────

    def handle_press(self, scene_pos: QPointF, modifiers, button):
        if button != Qt.MouseButton.LeftButton:
            return
        if self._editor is not None:
            handle = self._resize_handle_rect()
            if handle is not None and handle.contains(scene_pos):
                self._resizing_box = True
                self._canvas.viewport().setCursor(Qt.CursorShape.SizeFDiagCursor)
                return
            self._commit()
            return
        self._drag_start    = scene_pos
        self._drag_start_vp = self._canvas.mapFromScene(scene_pos)

    def handle_move(self, scene_pos: QPointF, modifiers):
        if self._resizing_box and self._current_text is not None:
            t = self._current_text
            new_w = max(10.0, scene_pos.x() / PIXELS_PER_MM - t.x_mm)
            new_h = max(10.0, scene_pos.y() / PIXELS_PER_MM - t.y_mm)
            self._current_text = replace(t, box_w_mm=new_w, box_h_mm=new_h)
            self._position_editor()
            self._canvas.viewport().update()
            return
        if self._drag_start is not None:
            self._live_pos = scene_pos
            self._canvas.viewport().update()

    def handle_release(self, scene_pos: QPointF, modifiers, button):
        if self._resizing_box:
            self._resizing_box = False
            self._canvas.viewport().setCursor(Qt.CursorShape.IBeamCursor)
            return
        if button != Qt.MouseButton.LeftButton or self._drag_start is None:
            return
        vp2  = self._canvas.mapFromScene(scene_pos)
        dist = (vp2 - self._drag_start_vp).manhattanLength()
        is_paragraph = dist > DRAG_THRESHOLD_PX

        x0 = min(self._drag_start.x(), scene_pos.x()) / PIXELS_PER_MM
        y0 = min(self._drag_start.y(), scene_pos.y()) / PIXELS_PER_MM
        w  = abs(scene_pos.x() - self._drag_start.x()) / PIXELS_PER_MM
        h  = abs(scene_pos.y() - self._drag_start.y()) / PIXELS_PER_MM

        self._drag_start = None
        self._live_pos    = None

        text = replace(self._defaults, content="", is_paragraph=is_paragraph,
                       x_mm=x0, y_mm=y0,
                       box_w_mm=(w if is_paragraph else self._defaults.box_w_mm),
                       box_h_mm=(h if is_paragraph else self._defaults.box_h_mm))
        self._open_editor(text, existing_shape=None)

    def draw_overlay(self, painter):
        if self._drag_start is not None and self._live_pos is not None:
            rect = QRectF(self._drag_start, self._live_pos).normalized()
            pen  = QPen(QColor(get_theme().preview), 0.8)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)

        handle = self._resize_handle_rect()
        if handle is not None:
            t = get_theme()
            painter.setPen(QPen(QColor(t.accent), 1))
            painter.setBrush(QBrush(QColor(t.work_area)))
            painter.drawRect(handle)

    def _box_rect_scene(self) -> QRectF | None:
        t = self._current_text
        if t is None or not t.is_paragraph:
            return None
        return QRectF(t.x_mm * PIXELS_PER_MM, t.y_mm * PIXELS_PER_MM,
                      t.box_w_mm * PIXELS_PER_MM, t.box_h_mm * PIXELS_PER_MM)

    def _resize_handle_rect(self) -> QRectF | None:
        """Bottom-right drag handle for the paragraph box - only while editing."""
        if self._editor is None:
            return None
        box = self._box_rect_scene()
        if box is None:
            return None
        s = RESIZE_HANDLE_PX / self._canvas.zoom
        return QRectF(box.right() - s / 2, box.bottom() - s / 2, s, s)

    # ── Overlay editor ────────────────────────────────────────────────────────

    def _open_editor(self, text: TextData, existing_shape: Shape | None):
        self._editing_shape = existing_shape
        self._current_text  = text
        if existing_shape is not None:
            self._canvas.set_shape_item_visible(existing_shape.id, False)

        self._editor = QTextEdit(self._canvas.viewport())
        self._editor.setPlainText(text.content)
        self._editor.setFrameStyle(0)
        self._editor.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._editor.viewport().setAutoFillBackground(False)
        self._editor.setCursorWidth(2)   # a plain 1px caret nearly disappears against dashed borders/small fonts
        self._restyle_editor()
        self._position_editor()
        self._editor.show()
        self._editor.setFocus()
        cursor = self._editor.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self._editor.setTextCursor(cursor)

    def _restyle_editor(self):
        if self._editor is None or self._current_text is None:
            return
        t = self._current_text
        px_per_mm = PIXELS_PER_MM * self._canvas.zoom
        font_size_px = max(6.0, t.font_size_mm * px_per_mm)

        font = QFont(t.font_family)
        font.setBold(t.bold)
        font.setItalic(t.italic)
        font.setPointSizeF(font_size_px)
        # Approximate live preview only - Qt's own letter/word spacing doesn't
        # exactly match the compiled engine's "spaces excluded" rule; exact
        # spacing is only guaranteed once committed to a real glyph outline.
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, t.letter_spacing_mm * px_per_mm)
        font.setWordSpacing(t.word_spacing_mm * px_per_mm)

        # The app's global stylesheet sets a font-family/size on every widget,
        # which silently overrides QTextEdit.setFont() - so the requested font
        # never showed while typing. Fixing that needs the font pinned in this
        # widget's OWN stylesheet (same-widget QSS wins over the app-wide rule),
        # not just the QFont object.
        theme = get_theme()
        self._editor.setStyleSheet(
            f"QTextEdit {{ background: transparent; border: 1px dashed {theme.accent}; "
            f"color: {theme.draw_color}; font-family: '{t.font_family}'; "
            f"font-size: {font_size_px:.1f}px; "
            f"font-weight: {'bold' if t.bold else 'normal'}; "
            f"font-style: {'italic' if t.italic else 'normal'}; }}"
        )

        # Retroactively restyle everything already typed, AND set the format
        # new keystrokes will use - setFont() alone only did the latter, and
        # even that got beaten by the stylesheet above.
        doc_cursor = QTextCursor(self._editor.document())
        doc_cursor.select(QTextCursor.SelectionType.Document)
        char_fmt = QTextCharFormat()
        char_fmt.setFont(font)
        doc_cursor.mergeCharFormat(char_fmt)
        self._editor.setCurrentCharFormat(char_fmt)

        align = {
            "left": Qt.AlignmentFlag.AlignLeft, "center": Qt.AlignmentFlag.AlignHCenter,
            "right": Qt.AlignmentFlag.AlignRight, "justify": Qt.AlignmentFlag.AlignJustify,
        }[t.align]
        self._editor.setAlignment(align)
        self._editor.setLineWrapMode(
            QTextEdit.LineWrapMode.WidgetWidth if t.is_paragraph else QTextEdit.LineWrapMode.NoWrap
        )

        block_fmt = QTextBlockFormat()
        block_fmt.setLineHeight(max(t.line_spacing, 0.01) * 100,
                                 QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
        doc_cursor.mergeBlockFormat(block_fmt)

    def _position_editor(self):
        if self._editor is None or self._current_text is None:
            return
        t = self._current_text
        top_left = self._canvas.mapFromScene(QPointF(t.x_mm * PIXELS_PER_MM, t.y_mm * PIXELS_PER_MM))
        if t.is_paragraph:
            bottom_right = self._canvas.mapFromScene(
                QPointF((t.x_mm + t.box_w_mm) * PIXELS_PER_MM, (t.y_mm + t.box_h_mm) * PIXELS_PER_MM)
            )
            w = max(60, bottom_right.x() - top_left.x())
            h = max(30, bottom_right.y() - top_left.y())
        else:
            w, h = 500, 120
        self._editor.setGeometry(top_left.x(), top_left.y(), w, h)

    @property
    def current_text(self) -> TextData:
        return self._current_text if self._current_text is not None else self._defaults

    # ── Style changes from the text toolbar while creating/editing ──────────

    def apply_style_change(self, **kwargs) -> bool:
        """Always absorbs the change while this tool is active - updates the
        defaults used for the next new text object, and the live editor's
        style too if one is currently open. Returns True so MainWindow knows
        not to also apply the change to some unrelated previously-selected shape."""
        self._defaults = replace(self._defaults, **kwargs)
        if self._current_text is None:
            return True
        self._current_text = replace(self._current_text, **kwargs)
        self._restyle_editor()
        self._position_editor()
        return True

    # ── Commit / cancel ───────────────────────────────────────────────────────

    def _commit(self):
        if self._editor is None or self._current_text is None:
            return
        content = self._editor.toPlainText()
        text = replace(self._current_text, content=content)
        shape = self._editing_shape
        self._remove_editor()

        if not content.strip():
            if shape is not None:
                self._canvas.set_shape_item_visible(shape.id, True)
                self._notify_finished_existing()
            return

        path = compile_text_path(text)
        self._defaults = replace(text, content="")
        shape_id = shape.id if shape is not None else None
        self._canvas.shape_text_edited.emit(shape_id, path, text)
        if shape is not None:
            self._notify_finished_existing()

    def _cancel(self):
        shape = self._editing_shape
        self._remove_editor()
        if shape is not None:
            self._canvas.set_shape_item_visible(shape.id, True)
            self._notify_finished_existing()

    def _notify_finished_existing(self):
        """Editing an existing shape (selected, not freshly placed) was a
        one-off session - hand control back to Select so the object can be
        moved/transformed normally. Deferred by the caller (QTimer.singleShot)
        to avoid switching tools re-entrantly mid-callback."""
        if self._suppress_notify:
            return
        if self._on_finished_editing_existing:
            self._on_finished_editing_existing()

    def _remove_editor(self):
        if self._editor is not None:
            self._editor.deleteLater()
        self._editor = None
        self._editing_shape = None
        self._current_text = None
