"""Geometric transforms on Path objects - all return new Path instances."""
from __future__ import annotations
import math
from core.path_model import (
    Path, MoveTo, LineTo, CubicTo, QuadTo, ArcTo, ClosePath
)


def bounding_box(path: Path) -> tuple[float, float, float, float]:
    """(min_x, min_y, max_x, max_y) from all coordinate points (control-point hull)."""
    xs: list[float] = []
    ys: list[float] = []
    for seg in path.segments:
        if isinstance(seg, (MoveTo, LineTo)):
            xs.append(seg.x); ys.append(seg.y)
        elif isinstance(seg, CubicTo):
            xs += [seg.cx1, seg.cx2, seg.x]
            ys += [seg.cy1, seg.cy2, seg.y]
        elif isinstance(seg, QuadTo):
            xs += [seg.cx, seg.x]; ys += [seg.cy, seg.y]
        elif isinstance(seg, ArcTo):
            xs.append(seg.x); ys.append(seg.y)
    if not xs:
        return 0.0, 0.0, 0.0, 0.0
    return min(xs), min(ys), max(xs), max(ys)


def translate(path: Path, dx: float, dy: float) -> Path:
    segs = []
    for seg in path.segments:
        if isinstance(seg, MoveTo):
            segs.append(MoveTo(seg.x + dx, seg.y + dy))
        elif isinstance(seg, LineTo):
            segs.append(LineTo(seg.x + dx, seg.y + dy))
        elif isinstance(seg, CubicTo):
            segs.append(CubicTo(seg.cx1 + dx, seg.cy1 + dy,
                                 seg.cx2 + dx, seg.cy2 + dy,
                                 seg.x   + dx, seg.y   + dy))
        elif isinstance(seg, QuadTo):
            segs.append(QuadTo(seg.cx + dx, seg.cy + dy,
                                seg.x  + dx, seg.y  + dy))
        elif isinstance(seg, ArcTo):
            segs.append(ArcTo(seg.rx, seg.ry, seg.x_rotation,
                               seg.large_arc, seg.sweep,
                               seg.x + dx, seg.y + dy))
        else:
            segs.append(seg)
    return Path(segments=segs)


def mirror_x(path: Path, cx: float | None = None) -> Path:
    """Flip around a vertical axis at cx - defaults to the shape's own centre."""
    if cx is None:
        min_x, _, max_x, _ = bounding_box(path)
        cx = (min_x + max_x) / 2

    def mx(x: float) -> float:
        return 2.0 * cx - x

    segs = []
    for seg in path.segments:
        if isinstance(seg, MoveTo):
            segs.append(MoveTo(mx(seg.x), seg.y))
        elif isinstance(seg, LineTo):
            segs.append(LineTo(mx(seg.x), seg.y))
        elif isinstance(seg, CubicTo):
            segs.append(CubicTo(mx(seg.cx1), seg.cy1,
                                 mx(seg.cx2), seg.cy2,
                                 mx(seg.x),   seg.y))
        elif isinstance(seg, QuadTo):
            segs.append(QuadTo(mx(seg.cx), seg.cy, mx(seg.x), seg.y))
        elif isinstance(seg, ArcTo):
            # Horizontal flip: x endpoint flips, sweep inverts, x_rotation negates
            segs.append(ArcTo(seg.rx, seg.ry, -seg.x_rotation,
                               seg.large_arc, not seg.sweep,
                               mx(seg.x), seg.y))
        else:
            segs.append(seg)
    return Path(segments=segs)


def mirror_y(path: Path, cy: float | None = None) -> Path:
    """Flip around a horizontal axis at cy - defaults to the shape's own centre."""
    if cy is None:
        _, min_y, _, max_y = bounding_box(path)
        cy = (min_y + max_y) / 2

    def my(y: float) -> float:
        return 2.0 * cy - y

    segs = []
    for seg in path.segments:
        if isinstance(seg, MoveTo):
            segs.append(MoveTo(seg.x, my(seg.y)))
        elif isinstance(seg, LineTo):
            segs.append(LineTo(seg.x, my(seg.y)))
        elif isinstance(seg, CubicTo):
            segs.append(CubicTo(seg.cx1, my(seg.cy1),
                                 seg.cx2, my(seg.cy2),
                                 seg.x,   my(seg.y)))
        elif isinstance(seg, QuadTo):
            segs.append(QuadTo(seg.cx, my(seg.cy), seg.x, my(seg.y)))
        elif isinstance(seg, ArcTo):
            # Vertical flip: y endpoint flips, sweep inverts, x_rotation negates
            segs.append(ArcTo(seg.rx, seg.ry, -seg.x_rotation,
                               seg.large_arc, not seg.sweep,
                               seg.x, my(seg.y)))
        else:
            segs.append(seg)
    return Path(segments=segs)


def rotate(path: Path, angle_deg: float, center: tuple[float, float] | None = None) -> Path:
    """
    Rotate clockwise on screen (Y-down) around `center`, or the path's own
    bounding-box centre if not given. Positive angle = CW, negative = CCW.
    """
    if center is None:
        min_x, min_y, max_x, max_y = bounding_box(path)
        cx = (min_x + max_x) / 2
        cy = (min_y + max_y) / 2
    else:
        cx, cy = center
    a  = math.radians(angle_deg)
    ca, sa = math.cos(a), math.sin(a)

    def rot(x: float, y: float) -> tuple[float, float]:
        dx, dy = x - cx, y - cy
        return cx + dx * ca - dy * sa, cy + dx * sa + dy * ca

    segs = []
    for seg in path.segments:
        if isinstance(seg, MoveTo):
            nx, ny = rot(seg.x, seg.y)
            segs.append(MoveTo(nx, ny))
        elif isinstance(seg, LineTo):
            nx, ny = rot(seg.x, seg.y)
            segs.append(LineTo(nx, ny))
        elif isinstance(seg, CubicTo):
            cx1, cy1 = rot(seg.cx1, seg.cy1)
            cx2, cy2 = rot(seg.cx2, seg.cy2)
            x,   y   = rot(seg.x,   seg.y)
            segs.append(CubicTo(cx1, cy1, cx2, cy2, x, y))
        elif isinstance(seg, QuadTo):
            qcx, qcy = rot(seg.cx, seg.cy)
            x,   y   = rot(seg.x,  seg.y)
            segs.append(QuadTo(qcx, qcy, x, y))
        elif isinstance(seg, ArcTo):
            x, y = rot(seg.x, seg.y)
            new_xr = (seg.x_rotation + angle_deg) % 360
            segs.append(ArcTo(seg.rx, seg.ry, new_xr,
                               seg.large_arc, seg.sweep, x, y))
        else:
            segs.append(seg)
    return Path(segments=segs)


def scale(path: Path, sx: float, sy: float, ox: float, oy: float) -> Path:
    """Scale around anchor point (ox, oy) - the point that stays fixed."""
    def sc(x: float, y: float) -> tuple[float, float]:
        return ox + (x - ox) * sx, oy + (y - oy) * sy

    segs = []
    for seg in path.segments:
        if isinstance(seg, MoveTo):
            x, y = sc(seg.x, seg.y)
            segs.append(MoveTo(x, y))
        elif isinstance(seg, LineTo):
            x, y = sc(seg.x, seg.y)
            segs.append(LineTo(x, y))
        elif isinstance(seg, CubicTo):
            cx1, cy1 = sc(seg.cx1, seg.cy1)
            cx2, cy2 = sc(seg.cx2, seg.cy2)
            x,   y   = sc(seg.x,   seg.y)
            segs.append(CubicTo(cx1, cy1, cx2, cy2, x, y))
        elif isinstance(seg, QuadTo):
            qcx, qcy = sc(seg.cx, seg.cy)
            x,   y   = sc(seg.x,  seg.y)
            segs.append(QuadTo(qcx, qcy, x, y))
        elif isinstance(seg, ArcTo):
            x, y = sc(seg.x, seg.y)
            # Non-uniform scale on a rotated ellipse isn't a true ellipse anymore -
            # approximate by scaling the radii directly (fine for axis-aligned arcs).
            segs.append(ArcTo(seg.rx * abs(sx), seg.ry * abs(sy), seg.x_rotation,
                               seg.large_arc, seg.sweep, x, y))
        else:
            segs.append(seg)
    return Path(segments=segs)


def align(target: Path, reference: Path, mode: str) -> Path:
    """
    Translate *target* so it aligns with *reference*.
    mode: "left" | "right" | "top" | "bottom" | "center_h" | "center_v"
    center_h = same horizontal (X) centre; center_v = same vertical (Y) centre.
    """
    t = bounding_box(target)
    r = bounding_box(reference)
    dx = dy = 0.0

    if   mode == "left":     dx = r[0] - t[0]
    elif mode == "right":    dx = r[2] - t[2]
    elif mode == "top":      dy = r[1] - t[1]
    elif mode == "bottom":   dy = r[3] - t[3]
    elif mode == "center_h": dx = (r[0] + r[2]) / 2 - (t[0] + t[2]) / 2
    elif mode == "center_v": dy = (r[1] + r[3]) / 2 - (t[1] + t[3]) / 2

    return translate(target, dx, dy)
