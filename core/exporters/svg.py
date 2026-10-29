"""SVG export - the drawing (not the toolpath) as plain vector paths, one
<path> per Shape, grouped by layer. Uses mm as the SVG user unit directly
(viewBox "0 0 work_w work_h" with width/height in mm), so it round-trips
cleanly with core/importers/svg.py (which reads width/viewBox to build its
own mm scale factor - a 1:1 viewBox means that factor comes out to 1).
"""
from __future__ import annotations
from xml.sax.saxutils import escape

from core.document import Document, Layer
from core.path_model import MoveTo, LineTo, CubicTo, QuadTo, ArcTo, ClosePath

_NUM = "{:.4f}"


def export_svg(document: Document, filepath: str) -> None:
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(generate_svg(document))


def generate_svg(document: Document) -> str:
    w, h = document.work_w_mm, document.work_h_mm
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_NUM.format(w)}mm" '
        f'height="{_NUM.format(h)}mm" viewBox="0 0 {_NUM.format(w)} {_NUM.format(h)}">',
    ]

    for layer in document.layers:
        if not layer.visible or not layer.shapes:
            continue
        lines.append(f'  <g id="{escape(layer.name)}" stroke="{layer.color}" '
                      f'fill="none" stroke-width="0.3">')
        for shape in layer.shapes:
            d = _path_to_svg_d(shape.path)
            if d:
                lines.append(f'    <path d="{d}" />')
        lines.append("  </g>")

    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def _path_to_svg_d(path) -> str:
    parts = []
    for seg in path.segments:
        if isinstance(seg, MoveTo):
            parts.append(f"M {_NUM.format(seg.x)} {_NUM.format(seg.y)}")
        elif isinstance(seg, LineTo):
            parts.append(f"L {_NUM.format(seg.x)} {_NUM.format(seg.y)}")
        elif isinstance(seg, CubicTo):
            parts.append(f"C {_NUM.format(seg.cx1)} {_NUM.format(seg.cy1)} "
                          f"{_NUM.format(seg.cx2)} {_NUM.format(seg.cy2)} "
                          f"{_NUM.format(seg.x)} {_NUM.format(seg.y)}")
        elif isinstance(seg, QuadTo):
            parts.append(f"Q {_NUM.format(seg.cx)} {_NUM.format(seg.cy)} "
                          f"{_NUM.format(seg.x)} {_NUM.format(seg.y)}")
        elif isinstance(seg, ArcTo):
            parts.append(f"A {_NUM.format(seg.rx)} {_NUM.format(seg.ry)} "
                          f"{_NUM.format(seg.x_rotation)} {1 if seg.large_arc else 0} "
                          f"{1 if seg.sweep else 0} {_NUM.format(seg.x)} {_NUM.format(seg.y)}")
        elif isinstance(seg, ClosePath):
            parts.append("Z")
    return " ".join(parts)
