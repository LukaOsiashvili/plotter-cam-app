from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout,
    QSpinBox, QDoubleSpinBox, QDialogButtonBox
)


class ArrayDialog(QDialog):
    """Array / Duplicate - grid of copies offset by a fixed X/Y spacing."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Array / Duplicate")
        self.setFixedWidth(260)

        self._count_x = QSpinBox()
        self._count_x.setRange(1, 500)
        self._count_x.setValue(2)

        self._count_y = QSpinBox()
        self._count_y.setRange(1, 500)
        self._count_y.setValue(1)

        self._spacing_x = QDoubleSpinBox()
        self._spacing_x.setRange(-10000.0, 10000.0)
        self._spacing_x.setDecimals(2)
        self._spacing_x.setSuffix(" mm")
        self._spacing_x.setValue(10.0)

        self._spacing_y = QDoubleSpinBox()
        self._spacing_y.setRange(-10000.0, 10000.0)
        self._spacing_y.setDecimals(2)
        self._spacing_y.setSuffix(" mm")
        self._spacing_y.setValue(10.0)

        form = QFormLayout()
        form.addRow("Copies X:",  self._count_x)
        form.addRow("Copies Y:",  self._count_y)
        form.addRow("Spacing X:", self._spacing_x)
        form.addRow("Spacing Y:", self._spacing_y)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def values(self) -> tuple[int, int, float, float]:
        return (self._count_x.value(), self._count_y.value(),
                self._spacing_x.value(), self._spacing_y.value())
