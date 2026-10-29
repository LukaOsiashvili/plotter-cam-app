"""Background serial worker - one persistent QThread per connection, owning
the serial port for its whole lifetime so job streaming and (future) one-off
commands like manual jog share the same open connection instead of fighting
over it. Never touches Document - send_job() is handed an already-generated
list of G-code lines and streams exactly that, so further edits to the
drawing while a job is in flight can't affect it (same decoupling principle
as core/exporters/gcode.py).

── Protocol v0 ──────────────────────────────────────────────────────────────
Firmware is currently just a test/echo sketch (../firmware/, built together
once real hardware is in hand) - not the real GRBL-like parser yet. Expand
this alongside the real firmware as motion support lands.

Handshake:
    The port is opened with DTR and RTS off, so the Uno is NOT reset and keeps
    its position across reconnects. The PC then sends a bare newline (flushes a
    stray byte the port open can leave behind), discards the replies, and sends
    the hello line "$I". The firmware answers with exactly one line (instead of
    "ok"):  "READY name=<NoSpaces> buffer=<N> line=<max> reset=0"
    If the Uno did reset anyway (other drivers/OSes), it ignores everything
    during its ~1.5 s bootloader and then prints the same line by itself with
    reset=1 - the PC waits for that, and asks once more if needed.
    reset=1 = nothing has moved since power-up: position is the boot default 0,0,
              so the carriage must be parked at the corner;
    reset=0 = it has moved since power-up and still knows where it is.
    An unexpected READY at any later time means the Uno restarted (power dip,
    reset button): the PC stops the job and warns that the position is lost.
    name must not contain spaces (breaks key=value parsing - use
    underscores). buffer=<N> is the firmware's serial RX ring buffer size in
    bytes; that single number is all the PC needs for flow control (the
    firmware's separate motion-planner queue is purely internal - if it
    fills up, firmware just stops draining the RX buffer, which the PC
    already sees as slowing acks against its own byte-count ceiling; no
    second number needs to cross the wire for that to work).

Streaming (character-counting, GRBL-style - NOT one-line-then-wait):
    Job lines are framed as "N<n> <gcode>*<CRC16-4hex>\n" (n = 1, 2, ...,
    restarted by every $JOB header; the checksum covers the N word too).
    CRC-16/CCITT-FALSE, exactly 4 uppercase-or-lowercase hex digits.
    One-off commands and the header go unnumbered: "<gcode>*<checksum>\n".
    The PC tracks bytes sent-but-not-yet-acked and keeps topping up the
    firmware's RX buffer up to `buffer` bytes, never waiting for one ack
    before sending the next line - so firmware can start physically moving
    on the first couple of lines while more are still arriving, and neither
    side ever needs the whole job in memory at once.

    Firmware replies exactly one line per line received, in order:
      "ok N<n>" / "ok"  - accepted into the planner (NOT "move finished" - that's
                           what makes streaming async). A duplicate (n below the
                           expected number) is acked but not executed again.
      "resend N<k>"     - numbered line lost or corrupted: the firmware expected
                           line k and executes nothing else until it arrives.
                           Every line still in flight gets its own "resend" reply,
                           which the PC drops; it streams again from line k (up to
                           3 attempts per line before aborting the job)
      "error:checksum"  - corrupted unnumbered line (one-off command or header);
                           the PC resends it
      "error:<reason>"  - anything else (bad command, unsupported, …) is not
                           retried - resending an unparseable line forever
                           can't help; the job aborts

Job bounds header (first line of every job, see core/job_bounds.py):
    "$JOB ABS|REL <minX> <minY> <maxX> <maxY>"  - the drawing's box in mm, work
    coordinates (REL = relative to where the job starts). The firmware checks it
    against the machine's soft limits: "ok", or "error:limit" before anything
    moves. It also remembers the start position, which ^C returns to.
    "$JOB NONE" for jobs that don't move. Either form restarts line numbering at N1;
    the PC sends it alone and waits for "ok" before streaming the job.

Coordinates:
    Machine position (MPos) is the physical position from the parking corner;
    soft limits always apply to it. Work position (WPos) = MPos - work offset;
    all G-code coordinates are work coordinates. G92 moves the work zero, G92.1
    clears it, G28 always goes to the machine's parking corner.

One-off commands (manual control panel, outside a job):
    "$J X<dx> Y<dy>"  - relative jog in mm; doesn't touch the job's G90/G91 state
    "G92 X0 Y0"       - make the current position the work zero
    "G90 G0 X0 Y0"    - go to the work zero
    "G28"             - pen up, then go to the machine's parking corner (MPos 0,0)
    "$$"              - reply is ONE line instead of ok: "[SET steps_x=108.500 ...]"
                         (settings stored in the plotter's EEPROM)
    "$S name=value"   - change and store one setting; error:setting (unknown /
                         out of range), error:busy (machine moving)
    "$RST"            - restore the firmware's default settings
    "M3" / "M5"       - pen down / pen up (e.g. for focusing)
    Same framing and ok/error replies as job lines, sent one at a time.
    Motion (jobs, jog, go-to) needs motor power: without it the firmware answers
    "error:power", and if the supply drops mid-job it stops at once, so the rest
    of the job is refused with error:power (position may then be wrong).

Status reports (firmware → PC, never an ack):
    Any line starting with '<' is a status report, e.g.
    "<Idle|MPos:12.345,6.789|WPos:2.345,6.789|Pen:up|Rx:57|Pwr:4.9|Free:211|Plan:5168>"
    (state Idle / Run / Hold; Rx = last job line received; Pwr = motor supply in
    volts, measured on A5 - below 3.5 V the firmware treats the motors as unpowered;
    Free/Plan are firmware diagnostics). Positions are the firmware's own step counter, never computed on
    the PC. Sent in reply to the real-time byte '?', which the PC polls ~5x/s while
    connected.

Real-time control (out-of-band, single reserved bytes - NOT queued lines):
    Sent immediately over the wire the moment the user asks, bypassing the
    line queue entirely, so firmware's own low-level serial read can act on
    them instantly regardless of what's still buffered - same idea as
    GRBL's '!'/'~'/soft-reset bytes:
      0x21 '!'  - pause (feed hold): firmware stops advancing its planner
      0x7E '~'  - resume (cycle start)
      0x18 ^X   - emergency stop: motors stop instantly, pen up, machine stays
                  where it is. PC also abandons its own remaining queued lines
                  and drains whatever stray replies trickle in afterward
      0x03 ^C   - cancel job: same as ^X, then the firmware drives back to the
                  job's start position (from the last $JOB header)
      0x3F '?'  - status report request (reply: one '<...>' line)
"""
from __future__ import annotations
import queue
import threading
import time
from collections import OrderedDict

from PySide6.QtCore import QThread, Signal
import serial

from core.job_bounds import job_header

DEFAULT_BAUD       = 115200
_HELLO_TIMEOUT_S    = 1.0     # reply to "$I" from a running Uno
_BOOT_TIMEOUT_S     = 3.0     # spontaneous READY if the Uno reset after all
_FLUSH_SETTLE_S     = 0.15
_FALLBACK_BUFFER_CAP = 32     # used only if a READY line is missing buffer=
_READ_POLL_TIMEOUT_S = 0.2    # how often blocking reads recheck abort flags
_CHECKSUM_RETRY_LIMIT = 3
_DRAIN_AFTER_STOP_S  = 0.3
_IDLE_POLL_S         = 0.05   # how often the idle loop drains status reports
_COMMAND_TIMEOUT_S   = 2.0
_IDLE_TRUST_DELAY_S  = 0.3    # ignore Idle reports that may predate the job's last ack
_RESEND_QUIET_S      = 0.3    # after a resend: no reply this long = all echoes are in
_LOST_LINE_PROBE_S   = 1.0    # no reply this long with lines in flight: ask the firmware

_CTRL_PAUSE  = b"\x21"   # '!'
_CTRL_RESUME = b"\x7E"   # '~'
_CTRL_STOP   = b"\x18"   # Ctrl-X
_CTRL_CANCEL = b"\x03"   # Ctrl-C
_CTRL_STATUS = b"\x3F"   # '?'


def _checksum(line: str) -> int:
    """CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF), same as the firmware's
    computeCrc16. Check value: "123456789" -> 0x29B1."""
    crc = 0xFFFF
    for byte in line.encode("ascii"):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return crc


def _frame_line(line: str) -> bytes:
    return f"{line}*{_checksum(line):04X}\n".encode("ascii")


class SerialWorker(QThread):
    connected      = Signal(str)          # firmware-reported machine name
    disconnected   = Signal(str)          # reason; "" for a clean user-requested disconnect
    job_progress   = Signal(int, int)     # lines acked, total
    job_finished   = Signal(bool)         # True on success, False on abort/error
    log            = Signal(str)
    machine_reset  = Signal()             # unexpected READY: the Uno restarted, position lost
    # state, machine X/Y mm, work x/y mm, pen down - all reported by the firmware
    status         = Signal(str, float, float, float, float, bool)
    settings_received = Signal(str)       # the firmware's "[SET name=value ...]" line
    motor_power    = Signal(float)        # motor supply volts from each status report
    # error:power - True: the supply dropped during a job (position may be wrong);
    # False: it was already off when the job or command was sent (nothing moved)
    motor_power_problem = Signal(bool)

    def __init__(self, port: str, baud: int = DEFAULT_BAUD, parent=None):
        super().__init__(parent)
        self.port = port
        self.baud = baud
        self._ser: serial.Serial | None = None
        self._rx_buf = bytearray()   # partial incoming line, kept across _read_line calls
        self._last_state = ""        # state field of the most recent status report
        self._last_state_time = 0.0
        self._last_received_line: int | None = None   # "Rx" field of the latest status report
        self._pushback: str | None = None   # a reply read early, returned by the next _read_line
        self._write_lock = threading.Lock()
        self._job_queue: "queue.Queue[tuple[str, object] | None]" = queue.Queue()
        self._buffer_cap = _FALLBACK_BUFFER_CAP
        self._paused = False
        self._stop_evt = threading.Event()    # abort the in-progress job
        self._close_evt = threading.Event()   # tear down the connection entirely
        self._reset_evt = threading.Event()   # set when an unexpected READY arrives
        self._handshaking = False             # READY is expected only during the handshake

    # ── Public control (safe to call from the GUI thread) ──────────────────

    def send_job(self, lines: list[str]):
        self._stop_evt.clear()
        if self._paused:
            self._paused = False
            self._write(_CTRL_RESUME)   # never start a job with the firmware still held
        self._job_queue.put(("job", lines))

    def request_settings(self):
        """Ask for the plotter's stored settings; the reply arrives as settings_received."""
        self._job_queue.put(("settings", None))

    def send_command(self, line: str):
        """One-off line outside a job (jog, set zero, home)."""
        self._stop_evt.clear()
        self._job_queue.put(("cmd", line))

    def request_status(self):
        self._write(_CTRL_STATUS)

    def request_pause(self):
        self._paused = True
        self._write(_CTRL_PAUSE)

    def request_resume(self):
        self._paused = False
        self._write(_CTRL_RESUME)

    def request_stop(self):
        self._paused = False
        self._stop_evt.set()
        self._write(_CTRL_STOP)

    def request_cancel(self):
        self._paused = False
        self._stop_evt.set()
        self._write(_CTRL_CANCEL)

    def disconnect(self):
        self._close_evt.set()
        self._stop_evt.set()
        self._job_queue.put(None)   # unblock queue.get() if idle

    # ── Thread body ──────────────────────────────────────────────────────

    def run(self):
        try:
            self._ser = serial.Serial()
            self._ser.port = self.port
            self._ser.baudrate = self.baud
            self._ser.timeout = _READ_POLL_TIMEOUT_S
            self._ser.dtr = False   # must be set before open(): a DTR pulse resets the Uno
            self._ser.rts = False
            self._ser.open()
        except serial.SerialException as e:
            self.disconnected.emit(str(e))
            return

        try:
            name = self._handshake()
            if name is None:
                self.disconnected.emit("No response from firmware (no READY within timeout)")
                self._safe_close()
                return
            self.connected.emit(name)

            while not self._close_evt.is_set():
                try:
                    item = self._job_queue.get(timeout=_IDLE_POLL_S)
                except queue.Empty:
                    self._drain_idle_input()
                    continue
                if item is None:
                    break
                kind, payload = item
                if kind == "job":
                    self._run_job(payload)
                elif kind == "settings":
                    self._run_settings_query()
                else:
                    self._run_command(payload)

        except serial.SerialException as e:
            self.disconnected.emit(str(e))
            self._safe_close()
            return

        self._safe_close()
        self.disconnected.emit("")

    def _handshake(self) -> str | None:
        self._handshaking = True
        try:
            self._write(b"\n")
            self.msleep(int(_FLUSH_SETTLE_S * 1000))
            self._ser.reset_input_buffer()
            self._rx_buf.clear()
            for _attempt in range(2):
                self._write(_frame_line("$I"))
                line = self._wait_for_ready(_HELLO_TIMEOUT_S) or self._wait_for_ready(_BOOT_TIMEOUT_S)
                if line:
                    return self._apply_ready(line)
            return None
        finally:
            self._handshaking = False

    def _wait_for_ready(self, timeout_s: float) -> str | None:
        deadline = time.monotonic() + timeout_s
        while True:
            line = self._read_line(deadline=deadline)
            if line is None:
                return None
            if "READY " in line:
                return line[line.index("READY "):]

    def _apply_ready(self, line: str) -> str:
        kv = {}
        for tok in line.split()[1:]:
            if "=" in tok:
                k, v = tok.split("=", 1)
                kv[k] = v
        name = kv.get("name", "Unknown machine")
        try:
            self._buffer_cap = max(16, int(kv.get("buffer", _FALLBACK_BUFFER_CAP)))
        except ValueError:
            self._buffer_cap = _FALLBACK_BUFFER_CAP
        if kv.get("reset", "1") == "1":
            self.log.emit("Machine freshly started (nothing moved yet) - make sure the "
                          "carriage is parked at the corner (0,0)")
        else:
            self.log.emit("Machine was already running - position kept from before")
        return name

    def _on_unexpected_ready(self):
        self._reset_evt.set()
        self.log.emit("The machine restarted - its position is lost")
        self.machine_reset.emit()

    def _run_job(self, lines: list[str]):
        sendable = [ln.strip() for ln in lines]
        sendable = [ln for ln in sendable if ln and not ln.startswith(";")]
        total = len(sendable)
        if total == 0:
            self.job_finished.emit(True)
            return
        self._reset_evt.clear()

        # The bounds header goes out alone and must be accepted before any job line is
        # sent: with byte-count streaming, lines sent behind a rejected header would
        # already sit in the firmware's buffer and get executed. It also restarts the
        # firmware's line numbering at N1.
        if not self._send_header(job_header(sendable) or "$JOB NONE"):
            self.job_finished.emit(False)
            return

        # Job lines go out as "N<n> <gcode>" (n = index + 1). Replies are matched by
        # number, not by order, because a line lost on the wire gets no reply at all:
        #   "ok N<n>"     - line n (and every older one still listed) is accepted.
        #   "resend N<k>" - line k was lost or corrupted. Recovery: stop sending, absorb
        #                   the "resend" echoes of lines already on their way (the
        #                   firmware answers those at once, even with a full planner),
        #                   and once the line has been quiet for a moment, treat the rest
        #                   as lost and stream again from line k.
        frames = [_frame_line(f"N{i + 1} {ln}") for i, ln in enumerate(sendable)]
        next_idx = 0
        in_flight: "OrderedDict[int, int]" = OrderedDict()   # line number -> frame length
        in_flight_bytes = 0
        acked = 0
        resend_counts: dict[int, int] = {}
        recovering_from = 0   # line number being recovered, 0 = streaming normally

        while acked < total:
            if self._stop_evt.is_set() or self._close_evt.is_set():
                self._drain_stray_input(_DRAIN_AFTER_STOP_S)
                self.job_finished.emit(False)
                return

            while self._paused and not self._stop_evt.is_set() and not self._close_evt.is_set():
                self.msleep(50)
            if self._stop_evt.is_set() or self._close_evt.is_set():
                continue

            while (not recovering_from and next_idx < total
                   and in_flight_bytes + len(frames[next_idx]) <= self._buffer_cap):
                frame = frames[next_idx]
                self._write(frame)
                in_flight[next_idx + 1] = len(frame)
                in_flight_bytes += len(frame)
                next_idx += 1

            if not in_flight and not recovering_from:
                continue   # nothing dispatched yet (paused/buffer momentarily full); recheck

            # While recovering, a quiet line means every echo that is coming has arrived.
            # Otherwise silence is normal (the firmware holds the next line back while its
            # planner is full), but a line lost with nothing sent after it would never be
            # answered - so after a quiet spell, ask which line the firmware last received.
            wait_s = _RESEND_QUIET_S if recovering_from else _LOST_LINE_PROBE_S
            reply = self._read_line(deadline=time.monotonic() + wait_s)
            if reply is None:
                if self._stop_evt.is_set() or self._close_evt.is_set():
                    continue
                if not recovering_from:
                    received = self._probe_received_line()
                    if received is None or not in_flight or received != acked \
                            or received >= next(iter(in_flight)):
                        continue   # the next line is there, just waiting for planner room
                    line_no = received + 1
                    attempts = resend_counts.get(line_no, 0) + 1
                    resend_counts[line_no] = attempts
                    if attempts > _CHECKSUM_RETRY_LIMIT:
                        self.log.emit(f"Line {line_no}/{total}: resent {attempts - 1}x without success - aborting job")
                        self._abort_firmware_job()
                        self.job_finished.emit(False)
                        return
                    self.log.emit(f"Line {line_no}/{total}: never arrived, resending from there (attempt {attempts})")
                    recovering_from = line_no
                in_flight.clear()
                in_flight_bytes = 0
                next_idx = recovering_from - 1
                recovering_from = 0
                continue

            if reply == "READY":
                # The Uno rebooted: its buffer, planner and position are gone, so
                # there is nothing left to stop - just end the job here.
                self.log.emit(f"Job stopped after line {acked}/{total}: the machine restarted")
                self.job_finished.emit(False)
                return

            if reply.startswith("ok N"):
                try:
                    number = int(reply[len("ok N"):])
                except ValueError:
                    continue
                while in_flight and next(iter(in_flight)) <= number:
                    _, length = in_flight.popitem(last=False)
                    in_flight_bytes -= length
                if number > acked:
                    acked = number
                    self.job_progress.emit(acked, total)
                    # verbose by design right now (early hardware bring-up) - worth
                    # gating behind a toggle once jobs get big enough for this to flood
                    self.log.emit(f"[{number}/{total}] sent: {sendable[number - 1]}  ->  ok")

            elif reply.startswith("resend N"):
                try:
                    line_no = int(reply[len("resend N"):])
                except ValueError:
                    continue
                if in_flight:
                    # one echo per line that reached the firmware: free its bytes
                    _, length = in_flight.popitem(last=False)
                    in_flight_bytes -= length
                if recovering_from == line_no:
                    continue
                attempts = resend_counts.get(line_no, 0) + 1
                resend_counts[line_no] = attempts
                if attempts > _CHECKSUM_RETRY_LIMIT:
                    self.log.emit(f"Line {line_no}/{total}: resent {attempts - 1}x without success - aborting job")
                    self._abort_firmware_job()
                    self.job_finished.emit(False)
                    return
                self.log.emit(f"Line {line_no}/{total}: lost or corrupted, resending from there (attempt {attempts})")
                recovering_from = line_no
                acked = min(acked, line_no - 1)

            else:
                if reply == "error:power":
                    self.log.emit(f"Motor power lost during the job (after line {acked}/{total})")
                    self.motor_power_problem.emit(True)
                else:
                    self.log.emit(f"Line {acked + 1}/{total}: firmware rejected - {reply}")
                self._abort_firmware_job()
                self.job_finished.emit(False)
                return

        # "ok" only means "queued" - the machine may still have a full planner of moves
        # left. The job isn't over (and Pause/Stop/Cancel must stay usable) until the
        # firmware itself reports Idle.
        self.log.emit("All lines sent - waiting for the machine to finish...")
        if not self._wait_until_idle():
            self._drain_stray_input(_DRAIN_AFTER_STOP_S)
            self.job_finished.emit(False)
            return
        self.job_finished.emit(True)

    def _probe_received_line(self) -> int | None:
        """Asks for a status report and returns its Rx field: the last line number the
        firmware has received (including one held back for planner room)."""
        self._last_received_line = None
        self._write(_CTRL_STATUS)
        deadline = time.monotonic() + _COMMAND_TIMEOUT_S
        while self._last_received_line is None and time.monotonic() < deadline:
            line = self._read_line(deadline=time.monotonic() + _READ_POLL_TIMEOUT_S)
            if line is not None:
                self._pushback = line   # a real reply arrived meanwhile - keep it for the caller
                return None
        return self._last_received_line

    def _send_header(self, header: str) -> bool:
        """Sends the $JOB line on its own and waits for the verdict."""
        frame = _frame_line(header)
        for attempt in range(1, _CHECKSUM_RETRY_LIMIT + 2):
            self._write(frame)
            reply = self._read_line(deadline=time.monotonic() + _COMMAND_TIMEOUT_S)
            if reply == "ok":
                self.log.emit(f"{header}  ->  ok")
                return True
            if reply != "error:checksum":
                break
        if reply == "error:limit":
            self.log.emit(f"The drawing doesn't fit the machine's work area - nothing was "
                          f"drawn ({header} -> error:limit)")
        elif reply == "error:power":
            self.log.emit("Motor power is off - switch on the power module (nothing was drawn)")
            self.motor_power_problem.emit(False)
        else:
            self.log.emit(f"{header}  ->  {reply or 'no reply'} - job not started")
        return False

    def _abort_firmware_job(self):
        """The job is over on this side, but lines already streamed sit in the
        firmware's buffer and planner; ^X discards them, stops and lifts the pen."""
        self._write(_CTRL_STOP)
        self._drain_stray_input(_DRAIN_AFTER_STOP_S)

    def _wait_until_idle(self) -> bool:
        """Polls status until an Idle report arrives that was requested after the
        last ack. Returns False if the job was stopped/closed meanwhile."""
        trust_after = time.monotonic() + _IDLE_TRUST_DELAY_S
        while not (self._stop_evt.is_set() or self._close_evt.is_set() or self._reset_evt.is_set()):
            self._write(_CTRL_STATUS)
            self._read_line(deadline=time.monotonic() + _READ_POLL_TIMEOUT_S)
            if self._last_state == "Idle" and self._last_state_time >= trust_after:
                return True
        return False

    def _run_settings_query(self):
        self._write(_frame_line("$$"))
        reply = self._read_line(deadline=time.monotonic() + _COMMAND_TIMEOUT_S)
        if reply and reply.startswith("[SET"):
            self.settings_received.emit(reply)
        else:
            self.log.emit(f"$$  ->  {reply or 'no reply'} - could not read the machine settings")

    def _run_command(self, line: str):
        self._write(_frame_line(line))
        reply = self._read_line(deadline=time.monotonic() + _COMMAND_TIMEOUT_S)
        if reply == "error:power":
            self.log.emit(f"{line}  ->  not moved: motor power is off - switch on the power module")
        elif reply != "ok":
            self.log.emit(f"{line}  ->  {reply or 'no reply'}")

    def _drain_idle_input(self):
        """Outside a job only status reports are expected; _read_line handles them."""
        self._stop_evt.clear()   # a stop only ever applies to the job it interrupted
        while self._ser.in_waiting:
            if self._read_line(deadline=time.monotonic() + _READ_POLL_TIMEOUT_S) is None:
                break

    def _emit_status(self, line: str):
        fields = line.strip("<>").split("|")
        values = dict(f.split(":", 1) for f in fields[1:] if ":" in f)
        self._last_state = fields[0]
        self._last_state_time = time.monotonic()
        try:
            self._last_received_line = int(values["Rx"])
        except (KeyError, ValueError):
            pass
        try:
            mx, my = (float(v) for v in values["MPos"].split(","))
            wx, wy = (float(v) for v in values["WPos"].split(","))
            if "Pwr" in values:
                self.motor_power.emit(float(values["Pwr"]))
            self.status.emit(fields[0], mx, my, wx, wy, values.get("Pen") == "down")
        except (KeyError, ValueError):
            pass

    # ── Low-level I/O ────────────────────────────────────────────────────

    def _write(self, data: bytes):
        if not self._ser or not self._ser.is_open:
            return
        with self._write_lock:
            try:
                self._ser.write(data)
            except serial.SerialException:
                pass   # the read side will discover and report the disconnect

    def _read_line(self, deadline: float | None) -> str | None:
        """Reads one newline-terminated reply. With deadline=None this can
        block indefinitely (a real move may legitimately take seconds) but
        stays responsive to stop/close, rechecking them every byte-read
        timeout tick rather than blocking on a single long readline()."""
        # The partial line lives in self._rx_buf, not a local: giving up at a deadline
        # must never discard bytes already read (that once cut the '<' off a status
        # report, which then got mistaken for an ack).
        if self._pushback is not None:
            line, self._pushback = self._pushback, None
            return line
        buf = self._rx_buf
        while True:
            if self._stop_evt.is_set() or self._close_evt.is_set():
                return None
            if deadline is not None and time.monotonic() >= deadline:
                return None
            b = self._ser.read(1)
            if b:
                if b == b"\n":
                    line = buf.decode("ascii", errors="replace").strip()
                    buf.clear()
                    if line.startswith("<"):
                        self._emit_status(line)   # status report, never an ack
                        continue
                    if not self._handshaking and "READY " in line:
                        self._on_unexpected_ready()
                        return "READY"
                    return line
                buf += b

    def _drain_stray_input(self, duration_s: float):
        try:
            self._ser.reset_input_buffer()
            self.msleep(int(duration_s * 1000))
            self._ser.reset_input_buffer()
            self._rx_buf.clear()
        except serial.SerialException:
            pass

    def _safe_close(self):
        try:
            if self._ser and self._ser.is_open:
                self._ser.close()
        except serial.SerialException:
            pass
