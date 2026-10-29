"""Curve/arc flattening - framework-free (no Qt), used by boolean ops and
anywhere else that needs a polyline approximation of a Path. Approximation
only ever happens here at consumption time; the data model itself never
stores flattened points (see CLAUDE.md conventions)."""
from __future__ import annotations
import math
from core.path_model import Path, MoveTo, LineTo, CubicTo, QuadTo, ArcTo, ClosePath

DEFAULT_TOLERANCE_MM = 0.1


def flatten_path(path: Path, tolerance_mm: float = DEFAULT_TOLERANCE_MM) -> list[list[tuple[float, float]]]:
    """Flatten a Path into a list of polylines (one per subpath), in mm."""
    subpaths: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    cur = (0.0, 0.0)
    start = (0.0, 0.0)

    for seg in path.segments:
        if isinstance(seg, MoveTo):
            if current:
                subpaths.append(current)
            current = [(seg.x, seg.y)]
            cur = start = (seg.x, seg.y)

        elif isinstance(seg, LineTo):
            current.append((seg.x, seg.y))
            cur = (seg.x, seg.y)

        elif isinstance(seg, CubicTo):
            current.extend(_sample_cubic(cur, (seg.cx1, seg.cy1), (seg.cx2, seg.cy2),
                                          (seg.x, seg.y), tolerance_mm))
            cur = (seg.x, seg.y)

        elif isinstance(seg, QuadTo):
            current.extend(_sample_quad(cur, (seg.cx, seg.cy), (seg.x, seg.y), tolerance_mm))
            cur = (seg.x, seg.y)

        elif isinstance(seg, ArcTo):
            current.extend(_sample_arc(cur, seg, tolerance_mm))
            cur = (seg.x, seg.y)

        elif isinstance(seg, ClosePath):
            if current:
                current.append(start)
                subpaths.append(current)
            current = []

    if current:
        subpaths.append(current)
    return subpaths


def _chord_count(*points: tuple[float, float], tolerance_mm: float) -> int:
    length = sum(math.dist(points[i], points[i + 1]) for i in range(len(points) - 1))
    return max(4, min(200, int(length / max(tolerance_mm, 0.01)) + 1))


def _sample_cubic(p0, c1, c2, p1, tolerance_mm: float) -> list[tuple[float, float]]:
    n = _chord_count(p0, c1, c2, p1, tolerance_mm=tolerance_mm)
    pts = []
    for i in range(1, n + 1):
        t = i / n
        mt = 1 - t
        x = mt**3*p0[0] + 3*mt**2*t*c1[0] + 3*mt*t**2*c2[0] + t**3*p1[0]
        y = mt**3*p0[1] + 3*mt**2*t*c1[1] + 3*mt*t**2*c2[1] + t**3*p1[1]
        pts.append((x, y))
    return pts


def _sample_quad(p0, c, p1, tolerance_mm: float) -> list[tuple[float, float]]:
    n = _chord_count(p0, c, p1, tolerance_mm=tolerance_mm)
    pts = []
    for i in range(1, n + 1):
        t = i / n
        mt = 1 - t
        x = mt**2*p0[0] + 2*mt*t*c[0] + t**2*p1[0]
        y = mt**2*p0[1] + 2*mt*t*c[1] + t**2*p1[1]
        pts.append((x, y))
    return pts


def arc_params(p0: tuple[float, float], seg: ArcTo):
    """SVG endpoint-parameterized arc → center-parameterization (cx, cy, rx, ry,
    theta1_deg, dtheta_deg), or None if unsupported (rotated ellipse, zero
    radius, or coincident endpoints) - callers fall back to a straight line
    in that case, matching canvas rendering.
    theta1 is the start angle, dtheta the signed sweep (matches SVG's `sweep`
    flag: positive/CCW-in-math-convention for sweep=True)."""
    x0, y0 = p0
    x, y = seg.x, seg.y
    if x0 == x and y0 == y:
        return None
    rx, ry = abs(seg.rx), abs(seg.ry)
    if rx == 0 or ry == 0 or seg.x_rotation != 0:
        return None

    lam = ((x0 - x) / (2 * rx)) ** 2 + ((y0 - y) / (2 * ry)) ** 2
    if lam > 1:
        s = math.sqrt(lam)
        rx *= s
        ry *= s

    dx, dy = (x0 - x) / 2, (y0 - y) / 2
    x1p, y1p = dx, dy

    num = max(0.0, (rx*ry)**2 - (rx*y1p)**2 - (ry*x1p)**2)
    den = (rx*y1p)**2 + (ry*x1p)**2
    sq  = math.sqrt(num / den) if den > 0 else 0.0
    if seg.large_arc == seg.sweep:
        sq = -sq

    cxp = sq *  rx * y1p / ry
    cyp = sq * -ry * x1p / rx
    cx  = cxp + (x0 + x) / 2
    cy  = cyp + (y0 + y) / 2

    def _angle(ux, uy, vx, vy):
        n = math.sqrt(ux*ux + uy*uy) * math.sqrt(vx*vx + vy*vy)
        if n == 0:
            return 0.0
        a = math.degrees(math.acos(max(-1.0, min(1.0, (ux*vx + uy*vy) / n))))
        return -a if ux*vy - uy*vx < 0 else a

    theta1 = _angle(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dtheta = _angle((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)

    if not seg.sweep and dtheta > 0:
        dtheta -= 360
    elif seg.sweep and dtheta < 0:
        dtheta += 360

    return (cx, cy, rx, ry, theta1, dtheta)


def _sample_arc(p0: tuple[float, float], seg: ArcTo, tolerance_mm: float) -> list[tuple[float, float]]:
    """SVG endpoint-parameterized arc → sampled points (center-parameterization math)."""
    params = arc_params(p0, seg)
    if params is None:
        if p0 == (seg.x, seg.y):
            return []
        return [(seg.x, seg.y)]   # rotated ellipses unsupported - straight-line fallback

    cx, cy, rx, ry, theta1, dtheta = params
    arc_len = math.radians(abs(dtheta)) * max(rx, ry)
    n = max(4, min(200, int(arc_len / max(tolerance_mm, 0.01)) + 1))

    pts = []
    for i in range(1, n + 1):
        t = theta1 + dtheta * (i / n)
        rad = math.radians(t)
        pts.append((cx + rx * math.cos(rad), cy + ry * math.sin(rad)))
    return pts


def shape_fill_polygon(shape, tolerance_mm: float = DEFAULT_TOLERANCE_MM):
    """Build a single shape's filled area as a Shapely (Multi)Polygon, honoring
    the even-odd fill rule across its own subpaths (rings) - see
    combined_fill_polygon for the general (multi-shape) case this delegates to."""
    return combined_fill_polygon([shape], tolerance_mm)


def combined_fill_polygon(shapes, tolerance_mm: float = DEFAULT_TOLERANCE_MM):
    """Build the even-odd filled area across *all* given shapes' rings at
    once - not shape-by-shape unioned together. This means a smaller shape
    fully nested in a bigger one (e.g. a letter "O" drawn as two separate
    circle Shapes rather than one Shape with a hole subpath) punches a hole
    exactly like a hole subpath would, and two overlapping engrave shapes
    leave their shared (odd-count-covered... even-count-covered, i.e.
    2-times-covered) area blank rather than double-filled - matches how a
    laser/vinyl cutter's overlapping-fill behavior is normally expected to
    work. boolean_ops._shape_to_polygon unions instead (no holes, no
    XOR-cancellation) - not reusable for this."""
    from shapely.geometry import Polygon

    result = None
    for shape in shapes:
        for r in flatten_path(shape.path, tolerance_mm):
            if len(r) < 4:
                continue
            poly = Polygon(r)
            if not poly.is_valid:
                poly = poly.buffer(0)
            if poly.is_empty:
                continue
            result = poly if result is None else result.symmetric_difference(poly)

    if result is None or result.is_empty:
        return None
    return result
