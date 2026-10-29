from __future__ import annotations
import math
import ezdxf
import ezdxf.colors

from core.document import Document, Shape, _normalize_color
from core.path_model import Path
from core.constants import WORK_W_MM, WORK_H_MM

DEFAULT_COLOR = "#000000"

INSUNITS_TO_MM = {
    0: None, 1: 25.4, 2: 304.8, 4: 1.0, 5: 10.0,
    6: 1000.0, 8: 25.4/1000,
}


def _aci_to_hex(aci: int) -> str:
    if aci in (0, 7, 256) or aci is None:
        return DEFAULT_COLOR
    try:
        r, g, b = ezdxf.colors.aci2rgb(aci)
        return f"#{r:02X}{g:02X}{b:02X}"
    except Exception:
        return DEFAULT_COLOR


def _get_entity_color(entity, layer_color: int) -> str:
    try:
        aci = entity.dxf.color
    except Exception:
        aci = 256
    if aci == 256:
        aci = layer_color
    return _normalize_color(_aci_to_hex(aci))


def _get_units_scale(doc) -> float | None:
    try:
        return INSUNITS_TO_MM.get(doc.header.get("$INSUNITS", 0), None)
    except Exception:
        return None


def _entity_to_path(entity) -> Path | None:
    t = entity.dxftype()
    if t == "LINE":      return _line(entity)
    if t == "CIRCLE":    return _circle(entity)
    if t == "ARC":       return _arc(entity)
    if t in ("LWPOLYLINE", "POLYLINE"): return _polyline(entity)
    if t == "SPLINE":    return _spline(entity)
    return None


def _line(entity) -> Path:
    s, e = entity.dxf.start, entity.dxf.end
    return Path().move_to(s.x, s.y).line_to(e.x, e.y)


def _circle(entity) -> Path:
    cx, cy, r = entity.dxf.center.x, entity.dxf.center.y, entity.dxf.radius
    # Full circle as two 180° SVG arcs
    p = Path()
    p.move_to(cx + r, cy)
    p.arc_to(r, r, 0, False, True, cx - r, cy)
    p.arc_to(r, r, 0, False, True, cx + r, cy)
    p.close()
    return p


def _arc(entity) -> Path:
    cx, cy, r = entity.dxf.center.x, entity.dxf.center.y, entity.dxf.radius
    start_a = entity.dxf.start_angle
    end_a   = entity.dxf.end_angle
    if end_a <= start_a:
        end_a += 360
    span        = end_a - start_a
    large_arc   = span > 180
    sx = cx + r * math.cos(math.radians(start_a))
    sy = cy + r * math.sin(math.radians(start_a))
    ex = cx + r * math.cos(math.radians(end_a))
    ey = cy + r * math.sin(math.radians(end_a))
    p = Path()
    p.move_to(sx, sy)
    p.arc_to(r, r, 0, large_arc, True, ex, ey)
    return p


def _polyline(entity) -> Path | None:
    if entity.dxftype() == "LWPOLYLINE":
        pts    = [(v[0], v[1]) for v in entity.vertices()]
        closed = bool(entity.dxf.flags & 1)
    else:
        pts    = [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices]
        closed = bool(entity.dxf.flags & 1)
    if len(pts) < 2:
        return None
    return Path.from_points(pts, closed=closed)


def _spline(entity) -> Path | None:
    pts = [(p.x, p.y) for p in entity.flattening(0.05)]
    if len(pts) < 2:
        return None
    closed = bool(entity.dxf.flags & 1)
    return Path.from_points(pts, closed=closed)


def _flip_y(path: Path, min_y: float, max_y: float) -> Path:
    from core.path_model import MoveTo, LineTo, CubicTo, QuadTo, ArcTo, ClosePath
    out = Path()
    flip = lambda y: max_y + min_y - y
    for seg in path.segments:
        if isinstance(seg, MoveTo):
            out.move_to(seg.x, flip(seg.y))
        elif isinstance(seg, LineTo):
            out.line_to(seg.x, flip(seg.y))
        elif isinstance(seg, CubicTo):
            out.cubic_to(seg.cx1, flip(seg.cy1), seg.cx2, flip(seg.cy2),
                         seg.x, flip(seg.y))
        elif isinstance(seg, QuadTo):
            out.quad_to(seg.cx, flip(seg.cy), seg.x, flip(seg.y))
        elif isinstance(seg, ArcTo):
            out.arc_to(seg.rx, seg.ry, seg.x_rotation,
                       seg.large_arc, not seg.sweep,  # flip sweep with y
                       seg.x, flip(seg.y))
        elif isinstance(seg, ClosePath):
            out.close()
    return out


def _scale_path(path: Path, sx: float, sy: float, ox: float, oy: float) -> Path:
    from core.path_model import MoveTo, LineTo, CubicTo, QuadTo, ArcTo, ClosePath
    out = Path()
    for seg in path.segments:
        if isinstance(seg, MoveTo):
            out.move_to(seg.x*sx+ox, seg.y*sy+oy)
        elif isinstance(seg, LineTo):
            out.line_to(seg.x*sx+ox, seg.y*sy+oy)
        elif isinstance(seg, CubicTo):
            out.cubic_to(seg.cx1*sx+ox, seg.cy1*sy+oy,
                         seg.cx2*sx+ox, seg.cy2*sy+oy,
                         seg.x*sx+ox,   seg.y*sy+oy)
        elif isinstance(seg, QuadTo):
            out.quad_to(seg.cx*sx+ox, seg.cy*sy+oy, seg.x*sx+ox, seg.y*sy+oy)
        elif isinstance(seg, ArcTo):
            out.arc_to(seg.rx*sx, seg.ry*sy, seg.x_rotation,
                       seg.large_arc, seg.sweep, seg.x*sx+ox, seg.y*sy+oy)
        elif isinstance(seg, ClosePath):
            out.close()
    return out


def _compute_transform(all_pts: list, units_scale: float | None,
                        work_w=WORK_W_MM, work_h=WORK_H_MM) -> dict:
    if not all_pts:
        return {"sx": 1, "sy": 1, "ox": 0, "oy": 0}
    xs = [p[0] for p in all_pts]
    ys = [p[1] for p in all_pts]
    gw = max(xs) - min(xs)
    gh = max(ys) - min(ys)
    if gw == 0 or gh == 0:
        return {"sx": 1, "sy": 1, "ox": 0, "oy": 0}
    margin = 10
    if units_scale is not None:
        rw, rh = gw * units_scale, gh * units_scale
        if rw <= work_w and rh <= work_h:
            return {"sx": units_scale, "sy": units_scale,
                    "ox": -min(xs)*units_scale+margin, "oy": -min(ys)*units_scale+margin}
        scale = min((work_w-2*margin)/rw, (work_h-2*margin)/rh) * units_scale
    else:
        scale = min((work_w-2*margin)/gw, (work_h-2*margin)/gh)
    return {"sx": scale, "sy": scale,
            "ox": -min(xs)*scale+margin, "oy": -min(ys)*scale+margin}


def import_dxf(filepath: str, document: Document) -> list:
    """Parse a DXF file. Returns list of Layers that received shapes."""
    doc         = ezdxf.readfile(filepath)
    msp         = doc.modelspace()
    units_scale = _get_units_scale(doc)
    source      = filepath.replace("\\", "/").split("/")[-1]

    layer_colors: dict = {}
    for lyr in doc.layers:
        try:
            layer_colors[lyr.dxf.name] = lyr.dxf.color
        except Exception:
            layer_colors[lyr.dxf.name] = 7

    raw: list[tuple[str, Path]] = []
    all_pts: list[tuple[float, float]] = []

    for entity in msp:
        dxf_layer   = entity.dxf.layer if entity.dxf.hasattr("layer") else "0"
        layer_color = layer_colors.get(dxf_layer, 7)
        color       = _get_entity_color(entity, layer_color)
        path        = _entity_to_path(entity)
        if path is None:
            continue
        from core.path_model import MoveTo, LineTo, ArcTo
        for seg in path.segments:
            if isinstance(seg, (MoveTo, LineTo, ArcTo)):
                all_pts.append((seg.x, seg.y))
        raw.append((color, path))

    if not all_pts:
        return []

    min_y = min(p[1] for p in all_pts)
    max_y = max(p[1] for p in all_pts)
    t     = _compute_transform([(x, max_y+min_y-y) for (x,y) in all_pts], units_scale,
                               document.work_w_mm, document.work_h_mm)

    affected = []
    for color, path in raw:
        flipped     = _flip_y(path, min_y, max_y)
        transformed = _scale_path(flipped, t["sx"], t["sy"], t["ox"], t["oy"])
        shape       = Shape(path=transformed, source=source)
        layer       = document.get_or_create_layer_by_color(color)
        layer.shapes.append(shape)
        if layer not in affected:
            affected.append(layer)

    return affected
