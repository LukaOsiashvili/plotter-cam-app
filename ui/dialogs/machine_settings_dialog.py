from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QGroupBox, QDoubleSpinBox, QSpinBox, QLabel,
    QPushButton, QDialogButtonBox, QMessageBox
)

from core.theme import get_theme

# name -> (label, unit, minimum, maximum, decimals, step); ranges match the firmware's
# Settings.cpp, which rejects anything outside them with "error:setting".
_FIELDS = {
    "steps_x":    ("X steps per mm", "", 10.0, 1000.0, 3, 0.1),
    "steps_y":    ("Y steps per mm", "", 10.0, 1000.0, 3, 0.1),
    "speed_x":    ("X top speed", "mm/s", 0.5, 30.0, 2, 0.5),
    "speed_y":    ("Y top speed", "mm/s", 0.5, 30.0, 2, 0.5),
    "accel_x":    ("X acceleration", "mm/s²", 0.5, 100.0, 2, 0.5),
    "accel_y":    ("Y acceleration", "mm/s²", 0.5, 100.0, 2, 0.5),
    "backlash_x": ("X backlash", "mm", 0.0, 10.0, 3, 0.05),
    "backlash_y": ("Y backlash", "mm", 0.0, 10.0, 3, 0.05),
    "junction":   ("Corner deviation", "mm", 0.001, 1.0, 3, 0.005),
    "max_x":      ("Work area width (X)", "mm", 1.0, 500.0, 1, 1.0),
    "max_y":      ("Work area height (Y)", "mm", 1.0, 500.0, 1, 1.0),
    "pen_up":     ("Pen up angle", "°", 0, 180, 0, 1),
    "pen_down":   ("Pen down angle", "°", 0, 180, 0, 1),
}

_GROUPS = (
    ("Motion", ("steps_x", "steps_y", "speed_x", "speed_y", "accel_x", "accel_y")),
    ("Accuracy", ("backlash_x", "backlash_y", "junction")),
    ("Work area (soft limits)", ("max_x", "max_y")),
    ("Pen", ("pen_up", "pen_down")),
)

_HINTS = {
    "junction": "How far the pen may cut a corner at speed: larger = faster corners, "
                "slightly rounder.",
    "max_x": "The machine refuses any move outside 0..width / 0..height.",
}


class MachineSettingsDialog(QDialog):
    """Edit the settings stored on the plotter (EEPROM). Values come from the firmware's
    "$$" reply; on Save only the changed ones are sent back as "$S name=value"."""

    RESET = 2   # result code: user asked to restore the firmware defaults ("$RST")

    def __init__(self, values: dict[str, float], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Machine Settings")
        self.setMinimumWidth(360)
        self._original = dict(values)
        self._spins: dict[str, QDoubleSpinBox | QSpinBox] = {}
        t = get_theme()

        layout = QVBoxLayout(self)
        note = QLabel("Stored on the plotter itself - kept after power-off.")
        note.setStyleSheet(f"color: {t.text_secondary}; font-size: 8pt;")
        layout.addWidget(note)

        for title, names in _GROUPS:
            box = QGroupBox(title)
            form = QFormLayout(box)
            for name in names:
                spin = self._make_spin(name, values.get(name))
                self._spins[name] = spin
                form.addRow(_FIELDS[name][0] + ":", spin)
                if name in _HINTS:
                    hint = QLabel(_HINTS[name])
                    hint.setWordWrap(True)
                    hint.setStyleSheet(f"color: {t.text_secondary}; font-size: 8pt;")
                    form.addRow(hint)
            layout.addWidget(box)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save
                                   | QDialogButtonBox.StandardButton.Cancel)
        btn_reset = QPushButton("Reset to Defaults")
        buttons.addButton(btn_reset, QDialogButtonBox.ButtonRole.ResetRole)
        btn_reset.clicked.connect(self._on_reset)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _make_spin(self, name: str, value: float | None):
        _label, unit, lo, hi, decimals, step = _FIELDS[name]
        if decimals == 0:
            spin = QSpinBox()
            spin.setRange(int(lo), int(hi))
        else:
            spin = QDoubleSpinBox()
            spin.setRange(lo, hi)
            spin.setDecimals(decimals)
        spin.setSingleStep(step)
        if unit:
            spin.setSuffix(f" {unit}")
        if value is not None:
            spin.setValue(int(round(value)) if decimals == 0 else value)
        return spin

    def changed_commands(self) -> list[str]:
        """'$S name=value' for every field that differs from what the plotter reported."""
        commands = []
        for name, spin in self._spins.items():
            decimals = _FIELDS[name][4]
            new = spin.value()
            old = self._original.get(name)
            if old is None or abs(new - old) > 0.5 * 10 ** -max(decimals, 0):
                commands.append(f"$S {name}={new:.{decimals}f}")
        return commands

    def _on_reset(self):
        answer = QMessageBox.question(
            self, "Reset to Defaults",
            "Restore all plotter settings to the firmware defaults?")
        if answer == QMessageBox.StandardButton.Yes:
            self.done(self.RESET)


def parse_settings_line(line: str) -> dict[str, float] | None:
    """'[SET steps_x=108.500 ... pen_down=0]' -> {'steps_x': 108.5, ...}."""
    if not line.startswith("[SET"):
        return None
    values = {}
    for token in line.strip("[]").split()[1:]:
        name, _, value = token.partition("=")
        try:
            values[name] = float(value)
        except ValueError:
            pass
    return values
