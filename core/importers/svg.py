from __future__ import annotations
import re
import xml.etree.ElementTree as ET

from svgpathtools import svg2paths, Line, QuadraticBezier, CubicBezier, Arc

from core.document import Document, Shape, _normalize_color
from core.path_model import Path
from core.constants import WORK_W_MM, WORK_H_MM

DEFAULT_COLOR = "#000000"

NAMED_COLORS = {
    "black": "#000000", "white": "#FFFFFF", "red": "#FF0000",
    "green": "#008000", "blue": "#0000FF", "yellow": "#FFFF00",
    "cyan": "#00FFFF", "magenta": "#FF00FF", "orange": "#FFA500",
    "purple": "#800080", "gray": "#808080", "grey": "#808080",
    "none": None, "transparent": None,
}


def parse_mm(value: str) -> float | None:
    if value is None:
        return None
    m = re.match(r"^([\d.]+)\s*(mm|px|cm|in|pt)?$", value.strip())
    if not m:
        return None
    num  = float(m.group(1))
    unit = m.group(2) or ""
    return num * {"mm": 1.0, "cm": 10.0, "in": 25.4, "pt": 25.4/72,
                  "px": 25.4/96, "": 25.4/96}.get(unit, 25.4/96)


def _get_svg_dimensions(filepath: str):
    root = ET.parse(filepath).getroot()
    width_mm  = parse_mm(root.get("width"))
    height_mm = parse_mm(root.get("height"))
    vb = root.get("viewBox")
    if vb:
        parts = re.split(r"[\s,]+", vb.strip())
        if len(parts) == 4:
            vb_x, vb_y, vb_w, vb_h = map(float, parts)
            return width_mm, height_mm, vb_x, vb_y, vb_w, vb_h
    return width_mm, height_mm, None, None, None, None


def _parse_svg_color(value: str) -> str:
    if not value:
        return DEFAULT_COLOR
    value = value.strip().lower()
    if value in ("none", "transparent"):
        return DEFAULT_COLOR
    if value in NAMED_COLORS:
        return NAMED_COLORS[value] or DEFAULT_COLOR
    m = re.match(r"^#([0-9a-f])([0-9a-f])([0-9a-f])$", value)
    if m:
        return f"#{m.group(1)*2}{m.group(2)*2}{m.group(3)*2}".upper()
    if re.match(r"^#[0-9a-f]{6}$", value):
        return value.upper()
    m = re.match(r"^rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)$", value)
    if m:
        return f"#{int(m.group(1)):02X}{int(m.group(2)):02X}{int(m.group(3)):02X}"
    return DEFAULT_COLOR


def _extract_color(attributes: dict) -> str:
    style = attributes.get("style", "")
    if style:
        m = re.search(r"stroke\s*:\s*([^;]+)", style)
        if m:
            return _parse_svg_color(m.group(1).strip())
    stroke = attributes.get("stroke", "")
    if stroke:
        return _parse_svg_color(stroke)
    return DEFAULT_COLOR


def _segment_to_path(segment, path: Path, is_first: bool):
    """Append a svgpathtools segment to our Path, preserving curve types."""
    if is_first:
        start = segment.start
        path.move_to(start.real, start.imag)

    if isinstance(segment, Line):
        path.line_to(segment.end.real, segment.end.imag)

    elif isinstance(segment, QuadraticBezier):
        path.quad_to(
            segment.control.real, segment.control.imag,
            segment.end.real,    segment.end.imag,
        )

    elif isinstance(segment, CubicBezier):
        path.cubic_to(
            segment.control1.real, segment.control1.imag,
            segment.control2.real, segment.control2.imag,
            segment.end.real,      segment.end.imag,
        )

    elif isinstance(segment, Arc):
        path.arc_to(
            segment.radius.real, segment.radius.imag,
            segment.rotation,
            bool(segment.arc),
            bool(segment.sweep),
            segment.end.real, segment.end.imag,
        )


def _compute_transform(all_points, filepath, work_w=WORK_W_MM, work_h=WORK_H_MM):
    width_mm, height_mm, vb_x, vb_y, vb_w, vb_h = _get_svg_dimensions(filepath)
    margin = 10

    if width_mm and height_mm and vb_w and vb_h and vb_w > 0 and vb_h > 0:
        sx = width_mm / vb_w
        sy = height_mm / vb_h
        ox = -(vb_x or 0) * sx
        oy = -(vb_y or 0) * sy
        if width_mm <= work_w and height_mm <= work_h:
            return {"sx": sx, "sy": sy, "ox": ox, "oy": oy}

    xs = [p[0] for p in all_points]
    ys = [p[1] for p in all_points]
    gw = max(xs) - min(xs)
    gh = max(ys) - min(ys)
    if gw == 0 or gh == 0:
        return {"sx": 1, "sy": 1, "ox": 0, "oy": 0}
    scale = min((work_w - 2*margin) / gw, (work_h - 2*margin) / gh)
    return {"sx": scale, "sy": scale,
            "ox": -min(xs) * scale + margin, "oy": -min(ys) * scale + margin}


def _apply_transform_to_path(path: Path, t: dict) -> Path:
    """Return a new Path with all coordinates scaled and offset."""
    sx, sy, ox, oy = t["sx"], t["sy"], t["ox"], t["oy"]

    from core.path_model import (MoveTo, LineTo, CubicTo, QuadTo, ArcTo, ClosePath)
    out = Path()
    for seg in path.segments:
        if isinstance(seg, MoveTo):
            out.move_to(seg.x * sx + ox, seg.y * sy + oy)
        elif isinstance(seg, LineTo):
            out.line_to(seg.x * sx + ox, seg.y * sy + oy)
        elif isinstance(seg, CubicTo):
            out.cubic_to(seg.cx1*sx+ox, seg.cy1*sy+oy,
                         seg.cx2*sx+ox, seg.cy2*sy+oy,
                         seg.x*sx+ox,   seg.y*sy+oy)
        elif isinstance(seg, QuadTo):
            out.quad_to(seg.cx*sx+ox, seg.cy*sy+oy,
                        seg.x*sx+ox,  seg.y*sy+oy)
        elif isinstance(seg, ArcTo):
            out.arc_to(seg.rx*sx, seg.ry*sy,
                       seg.x_rotation, seg.large_arc, seg.sweep,
                       seg.x*sx+ox, seg.y*sy+oy)
        elif isinstance(seg, ClosePath):
            out.close()
    return out


def import_svg(filepath: str, document: Document, source_name: str = None) -> list:
    """
    Parse an SVG file. Each path becomes a Shape with proper curve segments.
    Returns list of Layers that received shapes.
    """
    paths, attributes_list = svg2paths(filepath)
    source = source_name or filepath.replace("\\", "/").split("/")[-1]

    raw_paths: list[tuple[str, Path]] = []
    all_sample_points = []

    for svg_path, attributes in zip(paths, attributes_list):
        if not svg_path:
            continue
        color = _normalize_color(_extract_color(attributes))
        path  = Path()

        for i, segment in enumerate(svg_path):
            _segment_to_path(segment, path, is_first=(i == 0))

        if path.is_empty():
            continue

        # Check if path closes on itself
        sp = path.start_point()
        ep = path.end_point()
        if sp and ep:
            if (sp[0]-ep[0])**2 + (sp[1]-ep[1])**2 < 0.01:
                path.close()

        # Collect sample points for transform (use segment endpoints)
        from core.path_model import MoveTo, LineTo, CubicTo, QuadTo, ArcTo
        for seg in path.segments:
            if isinstance(seg, (MoveTo, LineTo, CubicTo, QuadTo, ArcTo)):
                all_sample_points.append((seg.x, seg.y))

        raw_paths.append((color, path))

    if not all_sample_points:
        return []

    transform    = _compute_transform(all_sample_points, filepath,
                                      document.work_w_mm, document.work_h_mm)
    affected     = []

    for color, path in raw_paths:
        transformed = _apply_transform_to_path(path, transform)
        shape  = Shape(path=transformed, source=source)
        layer  = document.get_or_create_layer_by_color(color)
        layer.shapes.append(shape)
        if layer not in affected:
            affected.append(layer)

    return affected
