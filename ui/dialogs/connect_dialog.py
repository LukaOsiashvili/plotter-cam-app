"""Port + baud picker. Lists ports from OS-reported metadata only (pyserial's
list_ports.comports(), no VID/PID filtering) - deliberately does NOT open
each port to probe for a firmware handshake before showing the list: that
would reset every connected board just from opening this dialog, is slow
with several machines attached, and touching hardware you haven't chosen
yet is an unnecessary risk. The real machine name (from the firmware's
READY handshake) only becomes known after the user picks a port and
SerialWorker actually connects to it."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QComboBox, QPushButton, QLabel, QDialogButtonBox
)
from serial.tools import list_ports

from core.serial_link import DEFAULT_BAUD

_BAUD_OPTIONS = [9600, 19200, 38400, 57600, 115200]


class ConnectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Connect to Plotter")
        self.setMinimumWidth(340)
        layout = QVBoxLayout(self)

        port_row = QHBoxLayout()
        port_row.addWidget(QLabel("Port:"))
        self.combo_port = QComboBox()
        port_row.addWidget(self.combo_port, 1)
        btn_refresh = QPushButton("Refresh")
        btn_refresh.clicked.connect(self._refresh_ports)
        port_row.addWidget(btn_refresh)
        layout.addLayout(port_row)

        baud_row = QHBoxLayout()
        baud_row.addWidget(QLabel("Baud:"))
        self.combo_baud = QComboBox()
        for b in _BAUD_OPTIONS:
            self.combo_baud.addItem(str(b), b)
        self.combo_baud.setCurrentIndex(_BAUD_OPTIONS.index(DEFAULT_BAUD))
        baud_row.addWidget(self.combo_baud, 1)
        layout.addLayout(baud_row)

        self._refresh_ports()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _refresh_ports(self):
        self.combo_port.clear()
        ports = list_ports.comports()
        if not ports:
            self.combo_port.addItem("No ports found", "")
            return
        for p in ports:
            label = f"{p.device} - {p.description}" if p.description else p.device
            self.combo_port.addItem(label, p.device)

    def selected_port(self) -> str:
        return self.combo_port.currentData() or ""

    def selected_baud(self) -> int:
        return self.combo_baud.currentData()
