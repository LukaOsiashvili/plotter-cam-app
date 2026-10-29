from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QDoubleSpinBox, QRadioButton,
    QDialogButtonBox, QButtonGroup
)


class RotateDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Rotate")
        self.setFixedWidth(240)

        self._spin = QDoubleSpinBox()
        self._spin.setRange(0.0, 360.0)
        self._spin.setValue(90.0)
        self._spin.setDecimals(1)
        self._spin.setSuffix("°")
        self._spin.setSingleStep(15.0)

        self._cw  = QRadioButton("Clockwise")
        self._ccw = QRadioButton("Counter-clockwise")
        self._cw.setChecked(True)
        dir_group = QButtonGroup(self)
        dir_group.addButton(self._cw)
        dir_group.addButton(self._ccw)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        angle_row = QHBoxLayout()
        angle_row.addWidget(QLabel("Angle:"))
        angle_row.addWidget(self._spin)
        layout.addLayout(angle_row)
        layout.addWidget(self._cw)
        layout.addWidget(self._ccw)
        layout.addWidget(buttons)

    def angle(self) -> float:
        """Positive = CW on screen (Y-down). Negative = CCW."""
        val = self._spin.value()
        return val if self._cw.isChecked() else -val
