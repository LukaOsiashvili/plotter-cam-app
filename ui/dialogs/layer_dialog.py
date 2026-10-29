from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox,
    QPushButton, QWidget, QFrame, QCheckBox
)
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt

from core.document import Layer
from core.theme import get_theme


class LayerDialog(QDialog):
    """Settings dialog for a Layer - opened by double-clicking a layer node."""

    def __init__(self, layer: Layer, parent=None):
        super().__init__(parent)
        self.layer = layer
        self.setWindowTitle("Layer Settings")
        self.setMinimumWidth(360)
        self.setModal(True)
        self._build_ui()
        self._load_values()
        self._on_operation_changed()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # Colored header
        color = self.layer.color
        qc    = QColor(color)
        lum   = 0.299*qc.red() + 0.587*qc.green() + 0.114*qc.blue()
        text  = "#000000" if lum > 140 else "#FFFFFF"

        header = QWidget()
        header.setFixedHeight(52)
        header.setStyleSheet(f"background-color: {color};")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(16, 0, 16, 0)
        swatch = QLabel("●")
        swatch.setStyleSheet(f"color: {text}; font-size: 22px;")
        h_layout.addWidget(swatch)
        title = QLabel(color.upper())
        title.setStyleSheet(f"color: {text}; font-size: 15px; font-weight: bold; font-family: 'Courier New';")
        h_layout.addWidget(title)
        layout.addWidget(header)

        accent = QFrame()
        accent.setFixedHeight(3)
        accent.setStyleSheet(f"background-color: {self._darken(color)};")
        layout.addWidget(accent)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(16, 16, 16, 8)
        body_layout.setSpacing(12)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(8)

        self.edit_name = QLineEdit()
        form.addRow("Name:", self.edit_name)

        form.addRow(self._separator())

        self.combo_operation = QComboBox()
        self.combo_operation.addItems(["Line Draw", "Engrave"])
        self.combo_operation.currentTextChanged.connect(self._on_operation_changed)
        form.addRow("Operation:", self.combo_operation)

        form.addRow(self._separator())

        self.spin_feed = QDoubleSpinBox()
        self.spin_feed.setRange(1, 10000)
        self.spin_feed.setSuffix(" mm/min")
        self.spin_feed.setDecimals(0)
        form.addRow("Feed Rate:", self.spin_feed)

        self.spin_rapid = QDoubleSpinBox()
        self.spin_rapid.setRange(1, 10000)
        self.spin_rapid.setSuffix(" mm/min")
        self.spin_rapid.setDecimals(0)
        form.addRow("Rapid Rate:", self.spin_rapid)

        self.spin_passes = QSpinBox()
        self.spin_passes.setRange(1, 20)
        form.addRow("Passes:", self.spin_passes)

        self.sep_engrave = self._separator()
        form.addRow(self.sep_engrave)

        self.label_spacing = QLabel("Line Spacing:")
        self.spin_spacing  = QDoubleSpinBox()
        self.spin_spacing.setRange(0.1, 20)
        self.spin_spacing.setSuffix(" mm")
        self.spin_spacing.setDecimals(2)
        self.spin_spacing.setSingleStep(0.1)
        form.addRow(self.label_spacing, self.spin_spacing)

        self.label_angle = QLabel("Line Angle:")
        self.combo_angle = QComboBox()
        self.combo_angle.addItems(["Horizontal", "Vertical"])
        form.addRow(self.label_angle, self.combo_angle)

        self.label_cross = QLabel("Cross-Hatch:")
        self.check_cross = QCheckBox()
        form.addRow(self.label_cross, self.check_cross)

        body_layout.addLayout(form)
        layout.addWidget(body)

        btn_bar = QWidget()
        btn_layout = QHBoxLayout(btn_bar)
        btn_layout.setContentsMargins(16, 10, 16, 10)
        btn_layout.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setFixedWidth(90)
        btn_cancel.clicked.connect(self.reject)

        btn_ok = QPushButton("OK")
        btn_ok.setStyleSheet(self._accent_btn_style(color))
        btn_ok.clicked.connect(self._on_accept)
        btn_ok.setDefault(True)

        btn_layout.addWidget(btn_cancel)
        btn_layout.addSpacing(8)
        btn_layout.addWidget(btn_ok)
        layout.addWidget(btn_bar)

    def _load_values(self):
        self.edit_name.setText(self.layer.name)
        idx = self.combo_operation.findText(self.layer.operation)
        if idx >= 0:
            self.combo_operation.setCurrentIndex(idx)
        self.spin_feed.setValue(self.layer.speed)
        self.spin_rapid.setValue(self.layer.rapid_speed)
        self.spin_passes.setValue(self.layer.pass_count)
        self.spin_spacing.setValue(self.layer.line_spacing)
        idx2 = self.combo_angle.findText(self.layer.line_angle)
        if idx2 >= 0:
            self.combo_angle.setCurrentIndex(idx2)
        self.check_cross.setChecked(self.layer.cross_hatch)

    def _on_operation_changed(self):
        is_engrave = self.combo_operation.currentText() == "Engrave"
        self.sep_engrave.setVisible(is_engrave)
        self.label_spacing.setVisible(is_engrave)
        self.spin_spacing.setVisible(is_engrave)
        self.label_angle.setVisible(is_engrave)
        self.combo_angle.setVisible(is_engrave)
        self.label_cross.setVisible(is_engrave)
        self.check_cross.setVisible(is_engrave)
        self.adjustSize()

    def _on_accept(self):
        self.layer.name        = self.edit_name.text().strip() or self.layer.color
        self.layer.operation   = self.combo_operation.currentText()
        self.layer.speed       = self.spin_feed.value()
        self.layer.rapid_speed = self.spin_rapid.value()
        self.layer.pass_count  = self.spin_passes.value()
        self.layer.line_spacing = self.spin_spacing.value()
        self.layer.line_angle  = self.combo_angle.currentText()
        self.layer.cross_hatch = self.check_cross.isChecked()
        self.accept()

    # ── Style helpers ─────────────────────────────────────────────────────────

    def _darken(self, hex_color: str, factor: float = 0.75) -> str:
        c = QColor(hex_color)
        return QColor(int(c.red()*factor), int(c.green()*factor),
                      int(c.blue()*factor)).name()

    def _separator(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #CCCCCC; margin: 2px 0;")
        return line

    def _accent_btn_style(self, color: str) -> str:
        txt  = "#000" if QColor(color).lightness() > 140 else "#fff"
        dark = self._darken(color, 0.85)
        return f"""
            QPushButton {{ background-color: {color}; color: {txt};
                           border: none; border-radius: 4px;
                           padding: 6px; font-weight: bold; }}
            QPushButton:hover {{ background-color: {dark}; }}
        """
