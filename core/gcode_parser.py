"""Parses this project's own G-code dialect (core/exporters/gcode.py) back
into core/toolpath.py's SimSegment list, so Toolpath Simulation animates
exactly what the exported file will do rather than an independent
derivation from Document (see CLAUDE.md Phase 4 notes on why the two had
drifted apart before). Geometry, motion order, and pen state come entirely
from the G-code text; only per-move timing needs a side lookup into
Document.layers[].speed/rapid_speed, since this dialect deliberately
carries no F-word (see gcode.py header)."""
from __future__ import annotations
import math
import re

from core.document import Document
from core.geometry import DEFAULT_TOLERANCE_MM
from core.toolpath import SimSegment

_LAYER_COMMENT_RE = re.compile(r"^;\s*layer:\s*(.+?)\s+pass\s+\d+\s*$")
_CODE_RE = re.compile(r"^([A-Za-z]\d+)")
_WORD_RE = re.compile(r"([A-Za-z])(-?\d+\.?\d*)")


def parse_gcode(document: Document, text: str, tolerance_mm: float = DEFAULT_TOLERANCE_MM) -> list[SimSegment]:
    layer_lookup = {layer.name: layer for layer in document.layers}
    default_layer = document.layers[0] if document.layers else None

    mode = "absolute"
    cur = (0.0, 0.0)
    layer_name = ""
    segments: list[SimSegment] = []

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(";"):
            m = _LAYER_COMMENT_RE.match(line)
            if m:
                layer_name = m.group(1)
            continue

        code_m = _CODE_RE.match(line)
        if not code_m:
            continue
        code = code_m.group(1).upper()

        if code == "G90":
            mode = "absolute"
        elif code == "G91":
            mode = "incremental"
        elif code == "M2":
            break
        elif code in ("G0", "G1", "G2", "G3"):
            words = {w[0].upper(): float(w[1]) for w in _WORD_RE.findall(line)}
            layer = layer_lookup.get(layer_name, default_layer)
            speed_mm_s = max(layer.speed, 1e-6) / 60.0 if layer else 1.0
            rapid_mm_s = max(layer.rapid_speed, 1e-6) / 60.0 if layer else 1.0
            color = layer.color if layer else ""

            dx, dy = words.get("X", 0.0), words.get("Y", 0.0)
            target = (cur[0] + dx, cur[1] + dy) if mode == "incremental" else (dx, dy)

            if code == "G0":
                if math.dist(cur, target) > 1e-9:
                    segments.append(SimSegment(points=[cur, target], pen_down=False,
                                                duration_s=math.dist(cur, target) / rapid_mm_s,
                                                layer_name=layer_name, color=""))
            elif code == "G1":
                if math.dist(cur, target) > 1e-9:
                    segments.append(SimSegment(points=[cur, target], pen_down=True,
                                                duration_s=math.dist(cur, target) / speed_mm_s,
                                                layer_name=layer_name, color=color))
            else:  # G2 / G3 - center-parameterized arc, distinct from geometry.py's SVG-endpoint form
                center = (cur[0] + words.get("I", 0.0), cur[1] + words.get("J", 0.0))
                pts = _sample_arc_center(cur, target, center, clockwise=(code == "G2"),
                                          tolerance_mm=tolerance_mm)
                length = sum(math.dist(pts[k], pts[k + 1]) for k in range(len(pts) - 1))
                segments.append(SimSegment(points=pts, pen_down=True,
                                            duration_s=length / speed_mm_s,
                                            layer_name=layer_name, color=color))

            cur = target

    return segments


def _sample_arc_center(
    start: tuple[float, float],
    end: tuple[float, float],
    center: tuple[float, float],
    clockwise: bool,
    tolerance_mm: float,
) -> list[tuple[float, float]]:
    cx, cy = center
    r = math.dist(start, center)
    a0 = math.atan2(start[1] - cy, start[0] - cx)
    a1 = math.atan2(end[1] - cy, end[0] - cx)

    if clockwise:
        if a1 >= a0:
            a1 -= 2 * math.pi
    else:
        if a1 <= a0:
            a1 += 2 * math.pi

    sweep = abs(a1 - a0)
    if sweep < 1e-9:
        sweep = 2 * math.pi   # full circle: start == end, I/J still define the center

    steps = max(2, int(sweep * max(r, 1e-6) / max(tolerance_mm, 1e-3)) + 1)
    return [
        (cx + r * math.cos(a0 + (a1 - a0) * k / steps), cy + r * math.sin(a0 + (a1 - a0) * k / steps))
        for k in range(steps + 1)
    ]
