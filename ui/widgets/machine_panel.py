from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QComboBox,
    QSizePolicy, QProgressBar, QPlainTextEdit, QTabWidget, QFrame, QButtonGroup
)
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtCore import Qt, Signal

from core.theme import get_theme

_MOTION_MODE_LABELS = {"absolute": "Absolute (G90)", "incremental": "Incremental (G91)"}
_LOG_MAX_LINES = 200
_JOG_STEPS_MM = (0.1, 1.0, 10.0)
_DEFAULT_JOG_STEP_MM = 1.0
_JOG_BTN_W, _JOG_BTN_H = 56, 30
_MOTOR_POWER_MIN_V = 3.5   # same threshold as the firmware's Power.cpp (716 / 1023 * 5 V)

# Arrow key -> jog direction. Machine Y=0 is the far (gantry) end, drawn at the top
# of the canvas, so "up" means toward Y=0.
_JOG_KEYS = {
    Qt.Key.Key_Up:    (0, -1),
    Qt.Key.Key_Down:  (0, 1),
    Qt.Key.Key_Left:  (-1, 0),
    Qt.Key.Key_Right: (1, 0),
}


class MachinePanel(QWidget):
    """Plotter connection, job controls and streaming status (Job tab), plus manual
    jog / position readout (Control tab)."""

    connect_triggered      = Signal()
    disconnect_triggered   = Signal()
    send_triggered          = Signal()
    pause_triggered         = Signal()
    resume_triggered        = Signal()
    stop_triggered           = Signal()
    cancel_triggered        = Signal()
    motion_mode_changed     = Signal(str)   # "absolute" | "incremental"
    estimate_requested      = Signal()
    simulate_requested      = Signal()
    jog_requested           = Signal(float, float)   # relative dx, dy in mm
    set_zero_requested      = Signal()
    go_home_requested       = Signal()   # machine parking corner (G28)
    go_zero_requested       = Signal()   # work zero set by "Set Zero Here"
    pen_requested           = Signal(bool)   # True = lower the pen
    settings_requested      = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._paused = False
        self._connected = False
        self._job_active = False
        self._jog_step_mm = _DEFAULT_JOG_STEP_MM
        self._pen_down = False
        self._motor_power_ok = True
        self._jog_widgets: list[QWidget] = []
        self._build_ui()
        self.set_connected(False)
        self.set_job_active(False)

    def _build_ui(self):
        t = get_theme()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        title = QLabel("Machine")
        title.setStyleSheet(f"font-weight: 600; color: {t.text_primary};")
        layout.addWidget(title)

        self.status_label = QLabel("Not connected")
        self.status_label.setStyleSheet(f"color: {t.text_secondary}; font-size: 8pt;")
        layout.addWidget(self.status_label)

        self.btn_connect = QPushButton("Connect to Plotter...")
        self.btn_connect.clicked.connect(self._on_connect_clicked)
        layout.addWidget(self.btn_connect)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_job_tab(t), "Job")
        self.tabs.addTab(self._build_control_tab(t), "Control")
        self.tabs.setTabToolTip(1, "Manual control. Arrow keys jog one step while this tab is focused.")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.tabs)

    def _build_job_tab(self, t) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(8)

        self.btn_simulate = QPushButton("Simulate Toolpath...")
        self.btn_simulate.clicked.connect(self.simulate_requested.emit)
        layout.addWidget(self.btn_simulate)

        self.btn_send = QPushButton("Send Job")
        self.btn_send.clicked.connect(self.send_triggered.emit)
        layout.addWidget(self.btn_send)

        job_row = QHBoxLayout()
        self.btn_pause = QPushButton("Pause")
        self.btn_pause.clicked.connect(self._on_pause_clicked)
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setToolTip("Emergency stop: stops instantly, lifts the pen, stays where it is")
        self.btn_stop.clicked.connect(self.stop_triggered.emit)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setToolTip("Cancel the job: stops, lifts the pen and returns to the start (0,0)")
        self.btn_cancel.clicked.connect(self.cancel_triggered.emit)
        job_row.addWidget(self.btn_pause)
        job_row.addWidget(self.btn_stop)
        job_row.addWidget(self.btn_cancel)
        layout.addLayout(job_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

        motion_row = QHBoxLayout()
        motion_lbl = QLabel("Motion:")
        motion_lbl.setStyleSheet(f"color: {t.text_secondary}; font-size: 8pt;")
        self.combo_motion = QComboBox()
        for mode, label in _MOTION_MODE_LABELS.items():
            self.combo_motion.addItem(label, mode)
        self.combo_motion.currentIndexChanged.connect(self._on_motion_changed)
        motion_row.addWidget(motion_lbl)
        motion_row.addWidget(self.combo_motion, 1)
        layout.addLayout(motion_row)

        time_row = QHBoxLayout()
        self.lbl_time = QLabel("Est. time: -")
        self.lbl_time.setStyleSheet(f"color: {t.text_secondary}; font-size: 8pt;")
        self.btn_estimate = QPushButton("Estimate")
        self.btn_estimate.clicked.connect(self.estimate_requested.emit)
        time_row.addWidget(self.lbl_time, 1)
        time_row.addWidget(self.btn_estimate)
        layout.addLayout(time_row)

        self.lbl_job = QLabel("No job loaded")
        self.lbl_job.setStyleSheet(f"color: {t.text_disabled}; font-size: 8pt;")
        self.lbl_job.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_job)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(_LOG_MAX_LINES)
        self.log_view.setFixedHeight(90)
        self.log_view.setStyleSheet(f"font-size: 8pt; color: {t.text_secondary};")
        layout.addWidget(self.log_view)
        return tab

    def _build_control_tab(self, t) -> QWidget:
        tab = QWidget()
        tab.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._control_tab = tab
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(8)

        layout.addWidget(self._build_position_card(t))

        pad = QGridLayout()
        pad.setSpacing(4)
        for label, (dx, dy), row, col in (
            ("Y−", (0, -1), 0, 1),
            ("X−", (-1, 0), 1, 0),
            ("X+", (1, 0), 1, 2),
            ("Y+", (0, 1), 2, 1),
        ):
            btn = self._jog_button(label)
            btn.clicked.connect(lambda _=False, dx=dx, dy=dy: self._jog(dx, dy))
            pad.addWidget(btn, row, col)
        btn_home = self._jog_button("Home")
        btn_home.setToolTip("Pen up, then go to the machine's parking corner (G28)")
        btn_home.clicked.connect(self.go_home_requested.emit)
        pad.addWidget(btn_home, 1, 1)
        pad_row = QHBoxLayout()
        pad_row.addStretch(1)
        pad_row.addLayout(pad)
        pad_row.addStretch(1)
        layout.addLayout(pad_row)

        step_row = QHBoxLayout()
        step_row.setSpacing(4)
        step_lbl = QLabel("Step")
        step_lbl.setStyleSheet(f"color: {t.text_secondary}; font-size: 8pt;")
        step_row.addWidget(step_lbl)
        step_row.addSpacing(6)
        self._step_group = QButtonGroup(self)
        self._step_group.setExclusive(True)
        for mm in _JOG_STEPS_MM:
            btn = QPushButton(f"{mm:g} mm")
            btn.setCheckable(True)
            btn.setChecked(mm == _DEFAULT_JOG_STEP_MM)
            btn.clicked.connect(lambda _=False, mm=mm: self._set_jog_step(mm))
            self._step_group.addButton(btn)
            self._jog_widgets.append(btn)
            step_row.addWidget(btn, 1)
        layout.addLayout(step_row)

        action_row = QHBoxLayout()
        btn_zero = QPushButton("Set Zero")
        btn_zero.setToolTip("Make the current position the work zero (G92). "
                            "The machine limits don't move with it.")
        btn_zero.clicked.connect(self.set_zero_requested.emit)
        self._jog_widgets.append(btn_zero)
        btn_go_zero = QPushButton("Go to Zero")
        btn_go_zero.setToolTip("Go to the work zero (G90 G0 X0 Y0)")
        btn_go_zero.clicked.connect(self.go_zero_requested.emit)
        self._jog_widgets.append(btn_go_zero)
        self.btn_pen = QPushButton("Lower Pen")
        self.btn_pen.setToolTip("Lower or raise the pen (M3 / M5), e.g. for focusing")
        self.btn_pen.clicked.connect(lambda: self.pen_requested.emit(not self._pen_down))
        self._jog_widgets.append(self.btn_pen)
        action_row.addWidget(btn_zero, 1)
        action_row.addWidget(btn_go_zero, 1)
        action_row.addWidget(self.btn_pen, 1)
        layout.addLayout(action_row)

        btn_settings = QPushButton("Machine Settings...")
        btn_settings.setToolTip("Speeds, steps/mm, backlash, work area and pen angles "
                                "stored on the plotter")
        btn_settings.clicked.connect(self.settings_requested.emit)
        self._jog_widgets.append(btn_settings)
        layout.addWidget(btn_settings)
        layout.addStretch(1)

        for key, (dx, dy) in _JOG_KEYS.items():
            shortcut = QShortcut(QKeySequence(key), tab)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.setAutoRepeat(False)
            shortcut.activated.connect(lambda dx=dx, dy=dy: self._jog(dx, dy))
        return tab

    def _build_position_card(self, t) -> QFrame:
        # Position comes only from the firmware's status reports - never computed here.
        card = QFrame()
        card.setObjectName("positionCard")
        grid = QGridLayout(card)
        grid.setContentsMargins(12, 8, 12, 8)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(2)

        caption = QLabel("Work position")
        caption.setStyleSheet(f"color: {t.text_secondary}; font-size: 8pt;")
        self.lbl_state = QLabel()
        self.lbl_state.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(caption, 0, 0)
        # spans the value and unit columns, so a long state text can't widen the unit
        # column and push the position digits to the left
        grid.addWidget(self.lbl_state, 0, 1, 1, 2)

        self._axis_values: dict[str, QLabel] = {}
        for row, axis in enumerate(("x", "y"), start=1):
            name = QLabel(axis)
            name.setStyleSheet(f"color: {t.text_secondary}; font-weight: 600;")
            value = QLabel()
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            value.setStyleSheet(f'font-family: "{t.font_mono}"; font-size: 15pt; font-weight: 600;')
            unit = QLabel("mm")
            unit.setStyleSheet(f"color: {t.text_secondary}; font-size: 8pt;")
            grid.addWidget(name, row, 0)
            grid.addWidget(value, row, 1)
            grid.addWidget(unit, row, 2)
            self._axis_values[axis] = value

        self.lbl_machine = QLabel()
        self.lbl_machine.setToolTip("Machine position: physical, from the parking corner. "
                                    "The soft limits apply here.")
        self.lbl_machine.setStyleSheet(f'color: {t.text_secondary}; font-family: "{t.font_mono}"; '
                                       f"font-size: 8pt;")
        grid.addWidget(self.lbl_machine, 3, 0, 1, 3)
        grid.setColumnStretch(1, 1)
        return card

    def _jog_button(self, label: str) -> QPushButton:
        btn = QPushButton(label)
        btn.setFixedSize(_JOG_BTN_W, _JOG_BTN_H)
        btn.setStyleSheet("padding: 0px;")   # the theme's 14 px side padding clips "Home"
        self._jog_widgets.append(btn)
        return btn

    # ── State-driven UI updates (main_window owns actual connection state) ──

    def set_connected(self, connected: bool, machine_name: str = ""):
        self._connected = connected
        self.btn_connect.setText("Disconnect" if connected else "Connect to Plotter...")
        self.btn_send.setEnabled(connected)
        if connected:
            self.status_label.setText(f"Connected - {machine_name}" if machine_name else "Connected")
            self._show_position("Waiting...", None, None)
        else:
            self.status_label.setText("Not connected")
            self._show_position("Offline", None, None)
            self.set_job_active(False)
        self._update_control_enabled()

    def set_job_active(self, active: bool):
        self._job_active = active
        self.btn_send.setVisible(not active)
        self.btn_pause.setVisible(active)
        self.btn_stop.setVisible(active)
        self.btn_cancel.setVisible(active)
        self.progress_bar.setVisible(active)
        if not active:
            self._paused = False
            self.btn_pause.setText("Pause")
            self.progress_bar.setValue(0)
        self._update_control_enabled()

    def set_position(self, state: str, machine_x: float, machine_y: float,
                     work_x: float, work_y: float, pen_down: bool):
        self._pen_down = pen_down
        self.btn_pen.setText("Raise Pen" if pen_down else "Lower Pen")
        text = f"{state} · pen {'down' if pen_down else 'up'}"
        if not self._motor_power_ok:
            text += " · no motor power"
        self._show_position(text, (work_x, work_y), (machine_x, machine_y),
                            state if self._motor_power_ok else "NoPower")

    def set_motor_power(self, volts: float):
        self._motor_power_ok = volts >= _MOTOR_POWER_MIN_V

    def set_progress(self, done: int, total: int):
        pct = int(done * 100 / total) if total else 0
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(pct)
        self.progress_bar.setFormat(f"{done}/{total} lines (%p%)")

    def append_log(self, text: str):
        self.log_view.appendPlainText(text)

    def set_status(self, text: str):
        self.status_label.setText(text)

    def set_motion_mode(self, mode: str):
        idx = self.combo_motion.findData(mode)
        if idx >= 0:
            self.combo_motion.blockSignals(True)
            self.combo_motion.setCurrentIndex(idx)
            self.combo_motion.blockSignals(False)

    def set_time_estimate(self, text: str):
        self.lbl_time.setText(f"Est. time: {text}")

    def set_loaded_job(self, text: str):
        self.lbl_job.setText(text)

    def _show_position(self, text: str, work: tuple[float, float] | None,
                       machine: tuple[float, float] | None, state: str = ""):
        t = get_theme()
        color = {"Run": t.accent, "Hold": t.accent_alt, "NoPower": t.accent_alt}.get(
            state, t.text_secondary)
        self.lbl_state.setText(text)
        self.lbl_state.setStyleSheet(f"color: {color}; font-size: 8pt; font-weight: 600;")
        for axis, value in zip(("x", "y"), work or (None, None)):
            self._axis_values[axis].setText("-" if value is None else f"{value:.3f}")
        self.lbl_machine.setText("Machine   X -   Y -" if machine is None
                                 else f"Machine   X {machine[0]:.3f}   Y {machine[1]:.3f}")

    def _update_control_enabled(self):
        enabled = self._connected and not self._job_active
        for widget in self._jog_widgets:
            widget.setEnabled(enabled)

    def _set_jog_step(self, mm: float):
        self._jog_step_mm = mm

    def _jog(self, dx: int, dy: int):
        if not (self._connected and not self._job_active):
            return
        self.jog_requested.emit(dx * self._jog_step_mm, dy * self._jog_step_mm)

    def _on_tab_changed(self, index: int):
        if self.tabs.widget(index) is self._control_tab:
            self._control_tab.setFocus()   # so the arrow keys jog straight away

    def _on_connect_clicked(self):
        if self.btn_connect.text() == "Disconnect":
            self.disconnect_triggered.emit()
        else:
            self.connect_triggered.emit()

    def _on_pause_clicked(self):
        self._paused = not self._paused
        self.btn_pause.setText("Resume" if self._paused else "Pause")
        (self.pause_triggered if self._paused else self.resume_triggered).emit()

    def _on_motion_changed(self, _index: int):
        self.motion_mode_changed.emit(self.combo_motion.currentData())
