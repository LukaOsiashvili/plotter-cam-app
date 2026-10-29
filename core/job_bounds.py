"""Bounding box of a G-code job, sent to the firmware as a "$JOB" pre-flight line.

Works on the job's own lines (freshly exported or loaded from a file) rather than the
Document, so it checks exactly what will be streamed. Coordinates are mm in the
firmware's work space: G90 values as written, G91 values relative to the job's start.

  $JOB ABS <minX> <minY> <maxX> <maxY>   - box in absolute work coordinates
  $JOB REL <minX> <minY> <maxX> <maxY>   - box relative to where the job starts

The firmware adds its work offset (ABS) or current position (REL) and answers
"ok" or "error:limit" before anything moves.
"""
from __future__ import annotations
import math
import re

_WORD = re.compile(r"([A-Za-z])\s*([-+]?(?:\d+\.?\d*|\.\d+))")
_COMMENT = re.compile(r"\([^)]*\)")
_TWO_PI = 2 * math.pi


def job_header(lines: list[str]) -> str | None:
    """The "$JOB ..." line for these G-code lines, or None if nothing moves."""
    box = job_box(lines)
    if box is None:
        return None
    mode, (min_x, min_y, max_x, max_y) = box
    return f"$JOB {mode} {min_x:.3f} {min_y:.3f} {max_x:.3f} {max_y:.3f}"


def job_box(lines: list[str]) -> tuple[str, tuple[float, float, float, float]] | None:
    absolute = True
    motion = 0
    mode: str | None = None
    x = y = 0.0
    xs: list[float] = []
    ys: list[float] = []

    for raw in lines:
        line = _COMMENT.sub("", raw.split(";")[0])
        words = [(letter.upper(), float(value)) for letter, value in _WORD.findall(line)]
        if not words:
            continue
        values = {letter: value for letter, value in words if letter != "G"}
        home = False
        for letter, value in words:
            if letter != "G":
                continue
            code = round(value * 10)
            if code in (0, 10, 20, 30):
                motion = code // 10
            elif code == 900:
                absolute = True
            elif code == 910:
                absolute = False
            elif code == 280:
                home = True
        if home:
            continue   # G28 always goes to the parking corner, which is in bounds

        is_arc = motion >= 2 and ("I" in values or "J" in values)
        if "X" not in values and "Y" not in values and not is_arc:
            continue

        if mode is None:
            mode = "ABS" if absolute else "REL"
            if mode == "REL":
                xs.append(0.0)
                ys.append(0.0)

        tx = (values["X"] if absolute else x + values["X"]) if "X" in values else x
        ty = (values["Y"] if absolute else y + values["Y"]) if "Y" in values else y
        if is_arc:
            for px, py in _arc_extremes(x, y, tx, ty, x + values.get("I", 0.0),
                                        y + values.get("J", 0.0), clockwise=motion == 2):
                xs.append(px)
                ys.append(py)
        xs.append(tx)
        ys.append(ty)
        x, y = tx, ty

    if mode is None:
        return None
    return mode, (min(xs), min(ys), max(xs), max(ys))


def _arc_extremes(sx, sy, ex, ey, cx, cy, clockwise: bool) -> list[tuple[float, float]]:
    """Axis-crossing points the arc actually passes through. Same convention as the
    firmware: G2 (clockwise) = decreasing angle in coordinate numbers; start == end
    is a full circle."""
    radius = math.hypot(sx - cx, sy - cy)
    start = math.atan2(sy - cy, sx - cx)
    sweep = math.atan2(ey - cy, ex - cx) - start
    if clockwise:
        if sweep >= 0:
            sweep -= _TWO_PI
    elif sweep <= 0:
        sweep += _TWO_PI

    points = []
    for k in range(4):
        angle = k * math.pi / 2
        offset = (angle - start) if sweep > 0 else (start - angle)
        if offset % _TWO_PI <= abs(sweep):
            points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    return points
