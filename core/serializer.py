"""
Serializer for the .dcam project format (DIY CAM).
Format: UTF-8 JSON, version-stamped.
"""
from __future__ import annotations

import json
import itertools
from pathlib import Path as FsPath

import core.document as _doc_module
from core.document import Document, Layer, Shape, TextData
from core.constants import WORK_W_MM, WORK_H_MM
from core.path_model import (
    Path, MoveTo, LineTo, CubicTo, QuadTo, ArcTo, ClosePath
)

DCAM_VERSION = 1
DCAM_EXT     = ".dcam"


# ── Public API ────────────────────────────────────────────────────────────────

def save_dcam(doc: Document, path: str | FsPath) -> None:
    data = {
        "version":   DCAM_VERSION,
        "app":       "DIY CAM Software",
        "work_area": {
            "width_mm":      doc.work_w_mm,
            "height_mm":     doc.work_h_mm,
            "origin_corner": doc.origin_corner,
            "motion_mode":   doc.motion_mode,
        },
        "layers": [_layer_to_dict(layer) for layer in doc.layers],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_dcam(path: str | FsPath) -> Document:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    version = data.get("version", 1)
    if version > DCAM_VERSION:
        raise ValueError(
            f"File version {version} is newer than this app supports (max {DCAM_VERSION})."
        )

    wa  = data.get("work_area", {})
    doc = Document(
        work_w_mm=wa.get("width_mm",  WORK_W_MM),
        work_h_mm=wa.get("height_mm", WORK_H_MM),
        origin_corner=wa.get("origin_corner", "top-left"),
        motion_mode=wa.get("motion_mode", "absolute"),
    )

    max_id = 0
    for layer_data in data.get("layers", []):
        layer = _dict_to_layer(layer_data)
        doc.layers.append(layer)
        for shape in layer.shapes:
            if shape.id > max_id:
                max_id = shape.id

    # Advance the global ID counter above any restored IDs so new shapes
    # don't collide with loaded ones.
    if max_id > 0:
        _doc_module._id_counter = itertools.count(max_id + 1)

    return doc


# ── Save helpers ──────────────────────────────────────────────────────────────

def _layer_to_dict(layer: Layer) -> dict:
    return {
        "name":         layer.name,
        "color":        layer.color,
        "operation":    layer.operation,
        "speed":        layer.speed,
        "rapid_speed":  layer.rapid_speed,
        "pass_count":   layer.pass_count,
        "line_spacing": layer.line_spacing,
        "line_angle":   layer.line_angle,
        "cross_hatch":  layer.cross_hatch,
        "visible":      layer.visible,
        "locked":       layer.locked,
        "shapes":       [_shape_to_dict(s) for s in layer.shapes],
    }


def _shape_to_dict(shape: Shape) -> dict:
    d = {
        "id":     shape.id,
        "source": shape.source,
        "path":   [_seg_to_dict(seg) for seg in shape.path.segments],
    }
    if shape.text is not None:
        d["text"] = _text_to_dict(shape.text)
    return d


def _text_to_dict(t: TextData) -> dict:
    return {
        "content": t.content, "font_family": t.font_family, "font_size_mm": t.font_size_mm,
        "bold": t.bold, "italic": t.italic, "align": t.align,
        "line_spacing": t.line_spacing, "word_spacing_mm": t.word_spacing_mm,
        "letter_spacing_mm": t.letter_spacing_mm, "is_paragraph": t.is_paragraph,
        "box_w_mm": t.box_w_mm, "box_h_mm": t.box_h_mm, "x_mm": t.x_mm, "y_mm": t.y_mm,
    }


def _seg_to_dict(seg) -> dict:
    if isinstance(seg, MoveTo):
        return {"t": "M", "x": seg.x, "y": seg.y}
    if isinstance(seg, LineTo):
        return {"t": "L", "x": seg.x, "y": seg.y}
    if isinstance(seg, CubicTo):
        return {"t": "C",
                "cx1": seg.cx1, "cy1": seg.cy1,
                "cx2": seg.cx2, "cy2": seg.cy2,
                "x":   seg.x,   "y":   seg.y}
    if isinstance(seg, QuadTo):
        return {"t": "Q", "cx": seg.cx, "cy": seg.cy, "x": seg.x, "y": seg.y}
    if isinstance(seg, ArcTo):
        return {"t": "A",
                "rx": seg.rx, "ry": seg.ry, "xr": seg.x_rotation,
                "la": seg.large_arc, "sw": seg.sweep,
                "x":  seg.x, "y": seg.y}
    if isinstance(seg, ClosePath):
        return {"t": "Z"}
    raise TypeError(f"Unknown segment type: {type(seg).__name__}")


# ── Load helpers ──────────────────────────────────────────────────────────────

def _dict_to_layer(d: dict) -> Layer:
    layer = Layer(
        name=         d.get("name",         "Layer"),
        color=        d.get("color",        "#000000"),
        operation=    d.get("operation",    "Line Draw"),
        speed=        d.get("speed",        1200.0),
        rapid_speed=  d.get("rapid_speed",  3000.0),
        pass_count=   d.get("pass_count",   1),
        line_spacing= d.get("line_spacing", 1.0),
        line_angle=   d.get("line_angle",   "Horizontal"),
        cross_hatch=  d.get("cross_hatch",  False),
        visible=      d.get("visible",      True),
        locked=       d.get("locked",       False),
    )
    for shape_data in d.get("shapes", []):
        layer.shapes.append(_dict_to_shape(shape_data))
    return layer


def _dict_to_shape(d: dict) -> Shape:
    segments = [_dict_to_seg(s) for s in d.get("path", [])]
    text = _dict_to_text(d["text"]) if "text" in d else None
    # Pass id explicitly - bypasses default_factory so the counter is not incremented.
    return Shape(path=Path(segments=segments), id=d["id"], source=d.get("source", ""), text=text)


def _dict_to_text(d: dict) -> TextData:
    return TextData(
        content=d.get("content", ""), font_family=d.get("font_family", "Arial"),
        font_size_mm=d.get("font_size_mm", 10.0), bold=d.get("bold", False),
        italic=d.get("italic", False), align=d.get("align", "left"),
        line_spacing=d.get("line_spacing", 1.2), word_spacing_mm=d.get("word_spacing_mm", 0.0),
        letter_spacing_mm=d.get("letter_spacing_mm", 0.0), is_paragraph=d.get("is_paragraph", False),
        box_w_mm=d.get("box_w_mm", 60.0), box_h_mm=d.get("box_h_mm", 40.0),
        x_mm=d.get("x_mm", 0.0), y_mm=d.get("y_mm", 0.0),
    )


def _dict_to_seg(d: dict):
    t = d["t"]
    if t == "M": return MoveTo(d["x"], d["y"])
    if t == "L": return LineTo(d["x"], d["y"])
    if t == "C": return CubicTo(d["cx1"], d["cy1"], d["cx2"], d["cy2"], d["x"], d["y"])
    if t == "Q": return QuadTo(d["cx"], d["cy"], d["x"], d["y"])
    if t == "A": return ArcTo(d["rx"], d["ry"], d["xr"], d["la"], d["sw"], d["x"], d["y"])
    if t == "Z": return ClosePath()
    raise ValueError(f"Unknown segment code: {t!r}")
