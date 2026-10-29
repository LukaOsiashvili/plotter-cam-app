"""Union / Subtract / Intersect on shapes, via Shapely. Curves are flattened
only for the duration of the operation (see core/geometry.py); the result
comes back as ordinary polyline Path objects - booleans always produce
polygon edges, so there's no curve fidelity to preserve here.

Known limitation: a shape with multiple subpaths (e.g. an imported donut
with a hole) is unioned across its own rings rather than treated as
exterior+hole - fine for the single-ring shapes the drawing tools produce,
imperfect for compound imports.
"""
from __future__ import annotations
from shapely.geometry import Polygon
from shapely.ops import unary_union

from core.document import Shape
from core.path_model import Path
from core.geometry import flatten_path, DEFAULT_TOLERANCE_MM


def _shape_to_polygon(shape: Shape, tolerance_mm: float = DEFAULT_TOLERANCE_MM):
    rings = [r for r in flatten_path(shape.path, tolerance_mm) if len(r) >= 4]
    if not rings:
        return None
    polys = []
    for r in rings:
        p = Polygon(r)
        if not p.is_valid:
            p = p.buffer(0)
        if not p.is_empty:
            polys.append(p)
    if not polys:
        return None
    return unary_union(polys)


def _geom_to_paths(geom) -> list[Path]:
    if geom is None or geom.is_empty:
        return []
    polys = list(geom.geoms) if hasattr(geom, "geoms") else [geom]
    paths = []
    for poly in polys:
        if poly.is_empty:
            continue
        path = Path()
        for ring in [poly.exterior, *poly.interiors]:
            coords = list(ring.coords)
            path.move_to(*coords[0])
            for pt in coords[1:]:
                path.line_to(*pt)
            path.close()
        paths.append(path)
    return paths


def union(shapes: list[Shape]) -> list[Path]:
    polys = [g for g in (_shape_to_polygon(s) for s in shapes) if g is not None]
    if not polys:
        return []
    return _geom_to_paths(unary_union(polys))


def subtract(shapes: list[Shape]) -> list[Path]:
    """shapes[0] minus every other shape."""
    if not shapes:
        return []
    result = _shape_to_polygon(shapes[0])
    if result is None:
        return []
    for s in shapes[1:]:
        other = _shape_to_polygon(s)
        if other is not None:
            result = result.difference(other)
    return _geom_to_paths(result)


def intersect(shapes: list[Shape]) -> list[Path]:
    polys = [g for g in (_shape_to_polygon(s) for s in shapes) if g is not None]
    if len(polys) < 2:
        return []
    result = polys[0]
    for p in polys[1:]:
        result = result.intersection(p)
    return _geom_to_paths(result)
