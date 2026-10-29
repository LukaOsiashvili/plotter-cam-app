from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QFrame, QListWidget, QListWidgetItem,
    QAbstractItemView, QToolButton, QScrollArea, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QSize

from core.document import Layer, Shape
from core.theme import get_theme
from ui.widgets.icons import make_icon, ICON_EYE, ICON_EYE_OFF, ICON_LOCK, ICON_UNLOCK

_ICON_SIZE = 14
_BTN_SIZE  = 24


class LayerCard(QFrame):
    """One layer - header always visible, shape list toggleable via chevron."""

    shape_clicked      = Signal(int)
    settings_opened    = Signal(object)
    visibility_toggled = Signal(object, bool)
    lock_toggled       = Signal(object, bool)

    def __init__(self, layer: Layer, parent=None):
        super().__init__(parent)
        self.layer = layer
        self._expanded = False
        self._shape_rows: dict[int, QListWidgetItem] = {}
        self.setObjectName("LayerCard")
        self._build()

    # ── Construction ──────────────────────────────────────────────────────────

    def _build(self):
        t     = get_theme()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Header row ────────────────────────────────────────────────────────
        self._header = QWidget()
        self._header.setFixedHeight(48)
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header.setObjectName("CardHeader")
        self._header.mouseDoubleClickEvent = lambda _e: self.settings_opened.emit(self.layer)

        h = QHBoxLayout(self._header)
        h.setContentsMargins(0, 0, 8, 0)
        h.setSpacing(0)

        # Left color bar
        self._swatch = QFrame()
        self._swatch.setFixedWidth(5)
        self._swatch.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        h.addWidget(self._swatch)
        h.addSpacing(10)

        # Name + sub-label
        text_w  = QWidget()
        text_l  = QVBoxLayout(text_w)
        text_l.setContentsMargins(0, 6, 0, 6)
        text_l.setSpacing(2)

        self._lbl_name = QLabel()
        self._lbl_name.setStyleSheet("font-weight: 600; background: transparent;")

        self._lbl_sub = QLabel()
        self._lbl_sub.setStyleSheet(
            f"color: {t.text_secondary}; font-size: 8pt; background: transparent;"
        )

        text_l.addWidget(self._lbl_name)
        text_l.addWidget(self._lbl_sub)
        h.addWidget(text_w, stretch=1)

        # Eye / lock / chevron
        self._eye  = self._icon_btn(ICON_EYE,  ICON_EYE_OFF, self.layer.visible)
        self._lock = self._icon_btn(ICON_LOCK, ICON_UNLOCK,   self.layer.locked)
        self._eye.toggled.connect(lambda v: self.visibility_toggled.emit(self.layer, v))
        self._lock.toggled.connect(lambda v: self.lock_toggled.emit(self.layer, v))

        self._chevron = QToolButton()
        self._chevron.setCheckable(True)
        self._chevron.setText("▶")
        self._chevron.setFixedSize(_BTN_SIZE, _BTN_SIZE)
        self._chevron.setStyleSheet(
            f"QToolButton {{ background: transparent; border: none; "
            f"color: {t.text_secondary}; font-size: 9px; padding: 0; }}"
        )
        self._chevron.toggled.connect(self._on_toggle)

        h.addWidget(self._eye)
        h.addWidget(self._lock)
        h.addSpacing(4)
        h.addWidget(self._chevron)
        outer.addWidget(self._header)

        # ── Shape list (collapsed by default) ─────────────────────────────────
        self._list = QListWidget()
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.setFrameShape(QFrame.Shape.NoFrame)
        self._list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._list.setMaximumHeight(0)
        self._list.setVisible(False)
        self._list.setStyleSheet(f"""
            QListWidget {{
                background-color: {t.app_bg};
                border-top: 1px solid {t.border_subtle};
                padding: 2px 0;
            }}
            QListWidget::item {{
                padding: 3px 8px 3px 20px;
                color: {t.text_secondary};
                border-radius: 3px;
            }}
            QListWidget::item:hover    {{ color: {t.text_primary}; background: {t.surface}; }}
            QListWidget::item:selected {{ color: {t.text_primary}; background: {t.active};  }}
        """)
        self._list.itemClicked.connect(
            lambda item: self.shape_clicked.emit(item.data(Qt.ItemDataRole.UserRole))
        )
        outer.addWidget(self._list)

        self.update_header()
        self._apply_card_style()

    def _icon_btn(self, on_svg: str, off_svg: str, checked: bool) -> QToolButton:
        btn = QToolButton()
        btn.setCheckable(True)
        btn.setChecked(checked)
        btn.setFixedSize(_BTN_SIZE, _BTN_SIZE)
        btn.setIconSize(QSize(_ICON_SIZE, _ICON_SIZE))
        btn.setStyleSheet("QToolButton { background: transparent; border: none; }")
        btn.setIcon(make_icon(on_svg if checked else off_svg, get_theme().text_secondary, _ICON_SIZE))
        btn.toggled.connect(
            lambda v, b=btn, on=on_svg, off=off_svg:
            b.setIcon(make_icon(on if v else off, get_theme().text_secondary, _ICON_SIZE))
        )
        return btn

    def _apply_card_style(self):
        t = get_theme()
        self.setStyleSheet(f"""
            #LayerCard {{
                background-color: transparent;
                border: none;
                border-bottom: 1px solid {t.border_subtle};
            }}
            #CardHeader {{ background: transparent; }}
            #CardHeader:hover {{ background-color: {t.surface}; }}
        """)

    # ── Expand / collapse ─────────────────────────────────────────────────────

    def _on_toggle(self, expanded: bool):
        self._expanded = expanded
        self._chevron.setText("▾" if expanded else "▶")
        count = self._list.count()
        if expanded and count:
            row_h = max(self._list.sizeHintForRow(0), 24)
            self._list.setMaximumHeight(row_h * count + 8)
            self._list.setVisible(True)
        else:
            self._list.setMaximumHeight(0)
            self._list.setVisible(False)

    def _recalc_list_height(self):
        if self._expanded:
            self._on_toggle(True)

    # ── Public API ────────────────────────────────────────────────────────────

    def add_shape(self, shape: Shape):
        prefix = "● " if shape.path.is_closed else "○ "
        item   = QListWidgetItem(prefix + (shape.source or f"Shape {shape.id}"))
        item.setData(Qt.ItemDataRole.UserRole, shape.id)
        self._list.addItem(item)
        self._shape_rows[shape.id] = item
        self._recalc_list_height()

    def remove_shape(self, shape_id: int):
        item = self._shape_rows.pop(shape_id, None)
        if item:
            self._list.takeItem(self._list.row(item))
        self._recalc_list_height()

    def sync_selection(self, shape_ids: set[int]):
        self._list.clearSelection()
        for sid in shape_ids:
            item = self._shape_rows.get(sid)
            if item and self._expanded:
                item.setSelected(True)

    def selected_shape_ids(self) -> list[int]:
        return [
            item.data(Qt.ItemDataRole.UserRole)
            for item in self._list.selectedItems()
        ]

    def shape_count(self) -> int:
        return self._list.count()

    def update_header(self):
        passes = f" ×{self.layer.pass_count}" if self.layer.pass_count > 1 else ""
        speed  = f"{int(self.layer.speed)} mm/min"
        self._lbl_name.setText(self.layer.name)
        self._lbl_sub.setText(f"{self.layer.operation}{passes}  ·  {speed}")
        self._swatch.setStyleSheet(
            f"background-color: {self.layer.color}; border-radius: 2px;"
        )


# ─────────────────────────────────────────────────────────────────────────────

class LayerPanel(QWidget):

    shapes_removed           = Signal(list)
    layer_removed            = Signal(object)
    layer_settings           = Signal(object)
    shape_clicked            = Signal(int)
    layer_visibility_toggled = Signal(object, bool)
    layer_lock_toggled       = Signal(object, bool)

    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._cards: list[LayerCard] = []
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        hdr = QHBoxLayout()
        lbl = QLabel("Layers")
        lbl.setStyleSheet("font-weight: bold; font-size: 11px;")
        hdr.addWidget(lbl)
        hdr.addStretch()
        root.addLayout(hdr)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll.viewport().setStyleSheet("background: transparent;")

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        inner.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self._cards_layout = QVBoxLayout(inner)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(0)
        scroll.setWidget(inner)
        root.addWidget(scroll, stretch=1)

        self.btn_remove = QPushButton("− Remove Selected Shapes")
        self.btn_remove.clicked.connect(self._on_remove)
        root.addWidget(self.btn_remove)

    # ── Public API ─────────────────────────────────────────────────────────────

    def add_shape(self, layer: Layer, shape: Shape):
        card = self._find_card(layer)
        if card is None:
            card = self._create_card(layer)
        card.add_shape(shape)

    def sync_selection(self, shape_ids: list):
        ids = set(shape_ids)
        for card in self._cards:
            card.sync_selection(ids)

    def update_layer_node_label(self, layer: Layer):
        card = self._find_card(layer)
        if card:
            card.update_header()

    def clear(self):
        for card in self._cards:
            card.setParent(None)
            card.deleteLater()
        self._cards.clear()

    def remove_selected(self):
        self._on_remove()

    # ── Private ────────────────────────────────────────────────────────────────

    def _find_card(self, layer: Layer) -> LayerCard | None:
        for c in self._cards:
            if c.layer is layer:
                return c
        return None

    def _create_card(self, layer: Layer) -> LayerCard:
        card = LayerCard(layer)
        card.shape_clicked.connect(self.shape_clicked)
        card.settings_opened.connect(self.layer_settings)
        card.visibility_toggled.connect(self.layer_visibility_toggled)
        card.lock_toggled.connect(self.layer_lock_toggled)
        self._cards.append(card)
        self._cards_layout.addWidget(card)
        return card

    def _on_remove(self):
        ids = []
        for card in self._cards:
            ids.extend(card.selected_shape_ids())
        if ids:
            self.shapes_removed.emit(ids)
