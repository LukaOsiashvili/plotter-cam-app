from __future__ import annotations
from dataclasses import dataclass
from typing import Union


@dataclass
class MoveTo:
    x: float
    y: float


@dataclass
class LineTo:
    x: float
    y: float


@dataclass
class CubicTo:
    cx1: float
    cy1: float
    cx2: float
    cy2: float
    x: float
    y: float


@dataclass
class QuadTo:
    cx: float
    cy: float
    x: float
    y: float


@dataclass
class ArcTo:
    rx: float
    ry: float
    x_rotation: float  # degrees
    large_arc: bool
    sweep: bool        # True = clockwise in SVG convention
    x: float
    y: float


@dataclass
class ClosePath:
    pass


PathSegment = Union[MoveTo, LineTo, CubicTo, QuadTo, ArcTo, ClosePath]


class Path:
    """Ordered list of path segments - the canonical geometry representation."""

    def __init__(self, segments: list[PathSegment] | None = None):
        self.segments: list[PathSegment] = segments or []

    # ── Builder API ───────────────────────────────────────────────────────────

    def move_to(self, x: float, y: float) -> Path:
        self.segments.append(MoveTo(x, y))
        return self

    def line_to(self, x: float, y: float) -> Path:
        self.segments.append(LineTo(x, y))
        return self

    def cubic_to(self, cx1: float, cy1: float,
                 cx2: float, cy2: float,
                 x: float,   y: float) -> Path:
        self.segments.append(CubicTo(cx1, cy1, cx2, cy2, x, y))
        return self

    def quad_to(self, cx: float, cy: float, x: float, y: float) -> Path:
        self.segments.append(QuadTo(cx, cy, x, y))
        return self

    def arc_to(self, rx: float, ry: float, x_rotation: float,
               large_arc: bool, sweep: bool,
               x: float, y: float) -> Path:
        self.segments.append(ArcTo(rx, ry, x_rotation, large_arc, sweep, x, y))
        return self

    def close(self) -> Path:
        self.segments.append(ClosePath())
        return self

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def is_closed(self) -> bool:
        return bool(self.segments) and isinstance(self.segments[-1], ClosePath)

    def start_point(self) -> tuple[float, float] | None:
        for seg in self.segments:
            if isinstance(seg, MoveTo):
                return (seg.x, seg.y)
        return None

    def end_point(self) -> tuple[float, float] | None:
        for seg in reversed(self.segments):
            if isinstance(seg, (MoveTo, LineTo, CubicTo, QuadTo, ArcTo)):
                return (seg.x, seg.y)
        return None

    def is_empty(self) -> bool:
        return len(self.segments) == 0

    # ── Factory helpers ───────────────────────────────────────────────────────

    @classmethod
    def from_points(cls, points: list[tuple[float, float]], closed: bool = False) -> Path:
        """Build a polyline Path from a list of (x, y) mm points."""
        p = cls()
        if not points:
            return p
        p.move_to(*points[0])
        for pt in points[1:]:
            p.line_to(*pt)
        if closed:
            p.close()
        return p
