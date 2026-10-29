from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout,
    QDoubleSpinBox, QComboBox, QDialogButtonBox
)

from core.document import ORIGIN_CORNERS

_CORNER_LABELS = {
    "bottom-left":  "Bottom-left",
    "bottom-right": "Bottom-right",
    "top-left":     "Top-left",
    "top-right":    "Top-right",
}


class WorkAreaDialog(QDialog):
    """Edit the document's bed size (mm) and machine (0,0) origin corner."""

    def __init__(self, width_mm: float, height_mm: float, origin_corner: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Work Area Settings")
        self.setFixedWidth(280)

        self._spin_w = self._size_spin(width_mm)
        self._spin_h = self._size_spin(height_mm)

        self._combo_origin = QComboBox()
        for corner in ORIGIN_CORNERS:
            self._combo_origin.addItem(_CORNER_LABELS[corner], corner)
        idx = self._combo_origin.findData(origin_corner)
        self._combo_origin.setCurrentIndex(max(idx, 0))

        form = QFormLayout()
        form.addRow("Width:", self._spin_w)
        form.addRow("Height:", self._spin_h)
        form.addRow("Machine origin:", self._combo_origin)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _size_spin(self, value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(1.0, 10000.0)
        spin.setDecimals(1)
        spin.setSuffix(" mm")
        spin.setValue(value)
        return spin

    def values(self) -> tuple[float, float, str]:
        return (self._spin_w.value(), self._spin_h.value(), self._combo_origin.currentData())
