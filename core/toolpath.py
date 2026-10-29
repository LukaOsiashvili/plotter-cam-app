"""Toolpath generation - the bridge between drawn geometry (Shape.path,
Beziers/arcs meant for editing) and an ordered, flattened sequence of
pen-down strokes a machine can actually execute. Framework-free (no Qt),
consumed by core/exporters/gcode.py (Phase 3) and later the simulation
preview (Phase 4). Never stored on the data model - always regenerated
from Document on demand, same convention as flatten_path in geometry.py.
"""
from __future__ import annotations
from dataclasses import dataclass, field, replace
import math

from shapely.geometry import LineString

from core.document import Document, Layer, Shape
from core.path_model import PathSegment, LineTo, CubicTo, QuadTo, ArcTo, MoveTo, ClosePath
from core.geometry import (
    flatten_path, shape_fill_polygon, combined_fill_polygon, DEFAULT_TOLERANCE_MM,
    _sample_cubic, _sample_quad,
)

_HORIZONTAL_ANGLES = ("Horizontal",)


@dataclass
class PenStroke:
    """One continuous pen-down move: a polyline in mm, used for distance/
    ordering math. `segments` (when present) is the higher-fidelity original
    geometry - LineTo/ArcTo preserved as-is, CubicTo/QuadTo pre-flattened to
    LineTo chains - one entry per consecutive pair of `points`, so G-code
    export can emit true G2/G3 arcs instead of tiny G1 chords. Empty for
    hatch-fill strokes, which are plain scanline segments anyway.
    Pen-up travel between strokes is implicit - whatever the consumer
    (G-code export, sim preview) draws to get from one stroke's end to the
    next one's start."""
    points:     list[tuple[float, float]] = field(default_factory=list)
    segments:   list[PathSegment]         = field(default_factory=list)
    shape_id:   int = 0
    layer_name: str = ""
    pass_index: int = 0


# ── Per-shape stroke generation ─────────────────────────────────────────────

def generate_outline_strokes(shape: Shape, tolerance_mm: float = DEFAULT_TOLERANCE_MM) -> list[PenStroke]:
    """Trace the shape's own subpaths. Lines and arcs are kept as native
    LineTo/ArcTo segments (see PenStroke.segments); only CubicTo/QuadTo
    curves get flattened, since G-code has no native Bezier motion."""
    strokes: list[PenStroke] = []
    points: list[tuple[float, float]] = []
    segments: list[PathSegment] = []
    cur = start = (0.0, 0.0)

    def flush():
        if len(points) >= 2:
            strokes.append(PenStroke(points=list(points), segments=list(segments), shape_id=shape.id))

    for seg in shape.path.segments:
        if isinstance(seg, MoveTo):
            flush()
            points, segments = [(seg.x, seg.y)], []
            cur = start = (seg.x, seg.y)

        elif isinstance(seg, LineTo):
            segments.append(seg)
            points.append((seg.x, seg.y))
            cur = (seg.x, seg.y)

        elif isinstance(seg, ArcTo):
            segments.append(seg)
            points.append((seg.x, seg.y))
            cur = (seg.x, seg.y)

        elif isinstance(seg, CubicTo):
            for x, y in _sample_cubic(cur, (seg.cx1, seg.cy1), (seg.cx2, seg.cy2), (seg.x, seg.y), tolerance_mm):
                segments.append(LineTo(x, y))
                points.append((x, y))
            cur = (seg.x, seg.y)

        elif isinstance(seg, QuadTo):
            for x, y in _sample_quad(cur, (seg.cx, seg.cy), (seg.x, seg.y), tolerance_mm):
                segments.append(LineTo(x, y))
                points.append((x, y))
            cur = (seg.x, seg.y)

        elif isinstance(seg, ClosePath):
            if points and cur != start:
                segments.append(LineTo(start[0], start[1]))
                points.append(start)
                cur = start
            flush()
            points, segments = [], []

    flush()
    return strokes


def _reverse_stroke(stroke: PenStroke) -> PenStroke:
    """Reverse a stroke's direction, keeping segment fidelity: each ArcTo's
    sweep flag inverts (SVG-arc reversal), LineTo/flattened points just walk
    backward."""
    if not stroke.segments:
        return replace(stroke, points=list(reversed(stroke.points)))

    new_segments: list[PathSegment] = []
    for i in range(len(stroke.segments) - 1, -1, -1):
        seg = stroke.segments[i]
        tx, ty = stroke.points[i]   # segment now ends where it used to start
        if isinstance(seg, ArcTo):
            new_segments.append(ArcTo(seg.rx, seg.ry, seg.x_rotation, seg.large_arc, not seg.sweep, tx, ty))
        else:
            new_segments.append(LineTo(tx, ty))

    return replace(stroke, points=list(reversed(stroke.points)), segments=new_segments)


def generate_hatch_strokes(
    shape: Shape,
    line_spacing: float,
    line_angle: str,
    tolerance_mm: float = DEFAULT_TOLERANCE_MM,
    cross_hatch: bool = False,
) -> list[PenStroke]:
    """Parallel scanlines filling a single shape's interior, clipped against
    its filled area (even-odd rule, so donut-style holes are respected).
    See generate_layer_hatch_strokes for the multi-shape (whole-layer) case -
    this is just that with a one-shape list."""
    return generate_layer_hatch_strokes([shape], line_spacing, line_angle, tolerance_mm, cross_hatch)


def generate_layer_hatch_strokes(
    shapes: list[Shape],
    line_spacing: float,
    line_angle: str,
    tolerance_mm: float = DEFAULT_TOLERANCE_MM,
    cross_hatch: bool = False,
) -> list[PenStroke]:
    """Parallel scanlines filling the even-odd combined interior of ALL given
    shapes at once (core.geometry.combined_fill_polygon) - so overlapping or
    nested engrave shapes (e.g. a letter "O" as two separate circle Shapes)
    correctly cancel out in their shared area instead of each being hatched
    independently and double-filling it."""
    poly = combined_fill_polygon(shapes, tolerance_mm)
    if poly is None or poly.is_empty:
        return []

    horizontal = line_angle in _HORIZONTAL_ANGLES
    strokes = _scanlines(poly, line_spacing, horizontal, shape_id=0)
    if cross_hatch:
        strokes += _scanlines(poly, line_spacing, not horizontal, shape_id=0)
    return strokes


def _scanlines(poly, spacing: float, horizontal: bool, shape_id: int) -> list[PenStroke]:
    spacing = max(spacing, 1e-3)
    minx, miny, maxx, maxy = poly.bounds
    pad = 1.0  # mm, so scanlines fully cross the polygon's bounding box
    strokes: list[PenStroke] = []

    if horizontal:
        y = miny + spacing / 2
        while y <= maxy:
            strokes += _clip_scanline(LineString([(minx - pad, y), (maxx + pad, y)]), poly, shape_id)
            y += spacing
    else:
        x = minx + spacing / 2
        while x <= maxx:
            strokes += _clip_scanline(LineString([(x, miny - pad), (x, maxy + pad)]), poly, shape_id)
            x += spacing

    return strokes


def _clip_scanline(line: LineString, poly, shape_id: int) -> list[PenStroke]:
    inter = line.intersection(poly)
    if inter.is_empty:
        return []
    geoms = list(inter.geoms) if hasattr(inter, "geoms") else [inter]
    return [
        PenStroke(points=list(g.coords), shape_id=shape_id)
        for g in geoms
        if g.geom_type == "LineString" and g.length > 1e-6
    ]


def _with_passes(base: list[PenStroke], layer: Layer) -> list[PenStroke]:
    passes = max(1, layer.pass_count)
    return [
        replace(stroke, layer_name=layer.name, pass_index=p)
        for p in range(passes)
        for stroke in base
    ]


def generate_shape_strokes(shape: Shape, layer: Layer, tolerance_mm: float = DEFAULT_TOLERANCE_MM) -> list[PenStroke]:
    """Outline ("Line Draw") strokes for one shape, repeated for layer.pass_count.
    Engrave is handled at the whole-layer level instead (generate_layer_toolpath)
    - hatch fill has to see every shape in the layer at once so overlapping/nested
    engrave shapes cancel out correctly (core.geometry.combined_fill_polygon)."""
    return _with_passes(generate_outline_strokes(shape, tolerance_mm), layer)


# ── Ordering ─────────────────────────────────────────────────────────────────

def order_strokes(strokes: list[PenStroke], start: tuple[float, float] = (0.0, 0.0)) -> list[PenStroke]:
    """Greedy nearest-neighbor ordering to cut pen-up travel: repeatedly pick
    whichever remaining stroke has an endpoint (start or end) closest to the
    current position, reversing it if its end is the closer one."""
    remaining = list(strokes)
    ordered: list[PenStroke] = []
    cur = start

    while remaining:
        best_i, best_dist, best_reversed = None, None, False
        for i, s in enumerate(remaining):
            if not s.points:
                continue
            d_start = math.dist(cur, s.points[0])
            d_end   = math.dist(cur, s.points[-1])
            if best_dist is None or d_start < best_dist:
                best_i, best_dist, best_reversed = i, d_start, False
            if d_end < best_dist:
                best_i, best_dist, best_reversed = i, d_end, True

        chosen = remaining.pop(best_i)
        if best_reversed:
            chosen = _reverse_stroke(chosen)
        ordered.append(chosen)
        cur = chosen.points[-1]

    return ordered


# ── Document-level assembly ──────────────────────────────────────────────────

def generate_layer_toolpath(
    layer: Layer,
    tolerance_mm: float = DEFAULT_TOLERANCE_MM,
    start: tuple[float, float] = (0.0, 0.0),
) -> list[PenStroke]:
    if not layer.visible:
        return []

    if layer.operation == "Engrave":
        base = generate_layer_hatch_strokes(layer.shapes, layer.line_spacing, layer.line_angle,
                                             tolerance_mm, layer.cross_hatch)
        strokes = _with_passes(base, layer)
    else:  # "Line Draw"
        strokes = [
            stroke
            for shape in layer.shapes
            for stroke in generate_shape_strokes(shape, layer, tolerance_mm)
        ]

    return order_strokes(strokes, start=start)


def generate_document_toolpath(document: Document, tolerance_mm: float = DEFAULT_TOLERANCE_MM) -> list[PenStroke]:
    """Layer stack order is authoritative; within a layer, strokes are
    nearest-neighbor ordered, continuing from wherever the previous layer's
    toolpath left off."""
    strokes: list[PenStroke] = []
    cur = (0.0, 0.0)
    for layer in document.layers:
        layer_strokes = generate_layer_toolpath(layer, tolerance_mm, start=cur)
        strokes.extend(layer_strokes)
        if layer_strokes:
            cur = layer_strokes[-1].points[-1]
    return strokes


# ── Job time estimate / simulation ──────────────────────────────────────────

def _polyline_length(points: list[tuple[float, float]]) -> float:
    return sum(math.dist(points[i], points[i + 1]) for i in range(len(points) - 1))


@dataclass
class SimSegment:
    """One leg of the animated simulation: either pen-up travel (a straight
    line to the next stroke's start) or a pen-down stroke (its full
    polyline). Framework-free - the sim window (Phase 4 UI) just walks this
    list against elapsed time; core/exporters/gcode.py doesn't use it."""
    points:      list[tuple[float, float]]
    pen_down:    bool
    duration_s:  float
    layer_name:  str
    color:       str   # hex, "" for pen-up travel


def build_simulation_segments(document: Document, tolerance_mm: float = DEFAULT_TOLERANCE_MM) -> list[SimSegment]:
    """Layer stack order, matching generate_document_toolpath exactly (same
    per-layer ordering, same running position) - this is that same walk,
    just also splitting out the pen-up travel legs and timing each one.

    In incremental mode, matches gcode.py's start-of-job handling: there's no
    document-space "home" to travel from (the operator jogs the pen to the
    drawing's own start point by hand), so the very first pen-up leg of the
    whole job - travel from (0,0) to the first stroke - is dropped rather
    than shown/timed, same as it's a skipped zero-length move in the G-code."""
    segments: list[SimSegment] = []
    cur = (0.0, 0.0)

    for layer in document.layers:
        strokes = generate_layer_toolpath(layer, tolerance_mm, start=cur)
        if not strokes:
            continue
        speed_mm_s = max(layer.speed, 1e-6) / 60.0
        rapid_mm_s = max(layer.rapid_speed, 1e-6) / 60.0

        for stroke in strokes:
            travel = math.dist(cur, stroke.points[0])
            if travel > 1e-9:
                segments.append(SimSegment(points=[cur, stroke.points[0]], pen_down=False,
                                            duration_s=travel / rapid_mm_s,
                                            layer_name=layer.name, color=""))
            cut_len = _polyline_length(stroke.points)
            segments.append(SimSegment(points=list(stroke.points), pen_down=True,
                                        duration_s=cut_len / speed_mm_s,
                                        layer_name=layer.name, color=layer.color))
            cur = stroke.points[-1]

    if document.motion_mode == "incremental" and segments and not segments[0].pen_down:
        segments = segments[1:]

    return segments


def estimate_job_time_seconds(document: Document, tolerance_mm: float = DEFAULT_TOLERANCE_MM) -> float:
    """Total pen-down + pen-up time, mm/min feed rates converted to seconds.
    G-code itself carries no feedrate (see core/exporters/gcode.py) - this
    is purely a planning estimate shown before sending a job."""
    return sum(seg.duration_s for seg in build_simulation_segments(document, tolerance_mm))
