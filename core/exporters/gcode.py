"""G-code export - turns a Document's toolpath (core/toolpath.py) into plain
text for the custom GRBL-like Arduino firmware. No reference back to
Document once generated (see CLAUDE.md) - a background streaming worker can
send the text while editing continues live.

Dialect actually emitted: G21, G17, G90/G91, G0, G1, G2/G3, M3/M5, G28, M2.
Deliberately no F or S words - this machine has no spindle, and feed control
is handled by the (future) machine-control panel rather than baked into the
file. No G54-59 work offsets, no canned cycles, no tool change - none of
that applies to a 2-axis plotter with a pen-lift Z.
"""
from __future__ import annotations
import math
from datetime import datetime

from core.document import Document, MOTION_MODES
from core.path_model import ArcTo
from core.geometry import arc_params, _sample_arc, DEFAULT_TOLERANCE_MM
from core.toolpath import generate_document_toolpath, PenStroke

_COORD_FMT = "{:.3f}"


def export_gcode(document: Document, filepath: str, tolerance_mm: float = DEFAULT_TOLERANCE_MM) -> None:
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(generate_gcode(document, tolerance_mm))


def generate_gcode(document: Document, tolerance_mm: float = DEFAULT_TOLERANCE_MM) -> str:
    mode = document.motion_mode if document.motion_mode in MOTION_MODES else "absolute"
    flip_x, flip_y = _corner_flips(document.origin_corner)
    swap_arc = flip_x != flip_y   # exactly one axis mirrored ⇒ arc handedness reverses

    def to_machine(pt: tuple[float, float]) -> tuple[float, float]:
        x, y = pt
        return (
            document.work_w_mm - x if flip_x else x,
            document.work_h_mm - y if flip_y else y,
        )

    lines: list[str] = [
        "; DIY CAM Software -- generated G-code",
        f"; generated {datetime.now().isoformat(timespec='seconds')}",
        f"; motion mode: {mode}   origin corner: {document.origin_corner}",
        "G21",
        "G17",
        "G90" if mode == "absolute" else "G91",
    ]

    strokes = generate_document_toolpath(document, tolerance_mm)

    if mode == "absolute":
        cur = [0.0, 0.0]   # machine-space; job assumed to start at machine (0,0)
    else:
        # Incremental mode has no absolute reference, and the operator is
        # expected to jog/home the pen to the drawing's own start point by
        # hand before running the job - so the file must not encode any
        # travel distance from a document-space "home" (top-left etc.) to
        # the artwork; that offset doesn't exist for the machine. Instead,
        # wherever the toolpath's first point is IS the assumed starting
        # position: the first move comes out as a zero delta (and gets
        # skipped below, same as any other zero-length travel), and
        # drawing begins immediately.
        cur = list(to_machine(strokes[0].points[0])) if strokes else [0.0, 0.0]

    def emit(code: str, target: tuple[float, float], extra: str = ""):
        tx, ty = target
        if mode == "absolute":
            lines.append(f"{code} X{_COORD_FMT.format(tx)} Y{_COORD_FMT.format(ty)}{extra}")
        else:
            lines.append(f"{code} X{_COORD_FMT.format(tx - cur[0])} Y{_COORD_FMT.format(ty - cur[1])}{extra}")
        cur[0], cur[1] = tx, ty

    last_layer = None

    for stroke in strokes:
        if not stroke.points:
            continue
        if (stroke.layer_name, stroke.pass_index) != last_layer:
            lines.append(f"; layer: {stroke.layer_name}  pass {stroke.pass_index + 1}")
            last_layer = (stroke.layer_name, stroke.pass_index)

        start_m = to_machine(stroke.points[0])
        if math.dist(start_m, cur) > 1e-6:
            emit("G0", start_m)
        lines.append("M3")
        _emit_stroke_motion(stroke, cur, emit, to_machine, swap_arc, tolerance_mm)
        lines.append("M5")

    lines.append("M5")
    lines.append("G28")
    lines.append("M2")
    return "\n".join(lines) + "\n"


def _emit_stroke_motion(stroke: PenStroke, cur, emit, to_machine, swap_arc: bool, tolerance_mm: float):
    if not stroke.segments:
        for pt in stroke.points[1:]:
            emit("G1", to_machine(pt))
        return

    for i, seg in enumerate(stroke.segments):
        p0 = stroke.points[i]
        target_m = to_machine(stroke.points[i + 1])

        if isinstance(seg, ArcTo):
            params = arc_params(p0, seg)
            circular = params is not None and math.isclose(params[2], params[3], rel_tol=1e-6)
            if circular:
                cx, cy, rx, ry, theta1, dtheta = params
                center_m = to_machine((cx, cy))
                i_off = center_m[0] - cur[0]
                j_off = center_m[1] - cur[1]
                clockwise = dtheta < 0
                if swap_arc:
                    clockwise = not clockwise
                code = "G2" if clockwise else "G3"
                emit(code, target_m, extra=f" I{_COORD_FMT.format(i_off)} J{_COORD_FMT.format(j_off)}")
            else:
                # Rotated or non-circular ellipse - G-code arcs can't represent
                # it exactly; flatten just this one segment (matches the
                # canvas/geometry.py fallback for the same unsupported case).
                for px, py in _sample_arc(p0, seg, tolerance_mm):
                    emit("G1", to_machine((px, py)))
        else:
            emit("G1", target_m)


def _corner_flips(origin_corner: str) -> tuple[bool, bool]:
    flip_x = origin_corner in ("top-right", "bottom-right")
    flip_y = origin_corner in ("bottom-left", "bottom-right")
    return flip_x, flip_y
