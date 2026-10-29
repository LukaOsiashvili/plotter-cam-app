from __future__ import annotations
from dataclasses import dataclass, field
from typing import List
import itertools

from core.path_model import Path
from core.constants import WORK_W_MM, WORK_H_MM

_id_counter = itertools.count(1)


def _next_id() -> int:
    return next(_id_counter)


def _normalize_color(color: str) -> str:
    color = color.strip().upper()
    if not color.startswith("#"):
        color = "#" + color
    return color


TEXT_ALIGNMENTS = ("left", "center", "right", "justify")


@dataclass
class TextData:
    """Live text properties - kept on a Shape until 'Convert to Curves' (Ctrl+Q)
    discards it and freezes shape.path as plain geometry. shape.path is always
    the up-to-date compiled outline while this is set; see ui/text_engine.py."""
    content:           str   = ""
    font_family:       str   = "Arial"
    font_size_mm:      float = 10.0
    bold:              bool  = False
    italic:            bool  = False
    align:             str   = "left"   # left | center | right | justify (justify: paragraph only)
    line_spacing:      float = 1.2      # multiplier of nominal font line height
    word_spacing_mm:   float = 0.0      # extra, added on top of the space glyph's own advance
    letter_spacing_mm: float = 0.0      # extra, added after each non-space character
    is_paragraph:      bool  = False    # False = artistic text (free-growing), True = wraps to box_w_mm
    box_w_mm:          float = 60.0
    box_h_mm:          float = 40.0
    x_mm:              float = 0.0      # anchor: top-left of box (paragraph) or top-left of text block (artistic)
    y_mm:              float = 0.0


@dataclass
class Shape:
    path:   Path
    id:     int  = field(default_factory=_next_id)
    source: str  = ""   # filename this shape was imported from
    text:   "TextData | None" = None   # present only for live (not-yet-converted) text shapes


@dataclass
class Layer:
    name:         str          = "Layer"
    color:        str          = "#000000"
    operation:    str          = "Line Draw"    # "Line Draw" | "Engrave"
    speed:        float        = 1200.0         # mm/min
    rapid_speed:  float        = 3000.0         # mm/min
    pass_count:   int          = 1
    line_spacing: float        = 1.0            # mm, engrave only
    line_angle:   str          = "Horizontal"   # engrave only
    cross_hatch:  bool         = False          # engrave only - add a second pass perpendicular to line_angle
    visible:      bool         = True
    locked:       bool         = False
    shapes:       List[Shape]  = field(default_factory=list)

    @property
    def label(self) -> str:
        return self.name


ORIGIN_CORNERS = ("top-left", "top-right", "bottom-left", "bottom-right")
MOTION_MODES   = ("absolute", "incremental")


@dataclass
class Document:
    layers:        List[Layer]  = field(default_factory=list)
    work_w_mm:     float        = WORK_W_MM
    work_h_mm:     float        = WORK_H_MM
    origin_corner: str          = "top-left"      # machine (0,0) corner - consumed at G-code export.
                                                   # Document space is itself top-left-origin/Y-down (matches
                                                   # canvas/screen convention), so "top-left" is a 1:1 mapping
                                                   # with no axis flip - the common case for this project's
                                                   # own plotter. Per-machine/per-document choice for others.
    motion_mode:   str          = "absolute"      # "absolute" (G90) | "incremental" (G91) - G-code export

    # ── Layer API ─────────────────────────────────────────────────────────────

    def add_layer(self, name: str = "Layer", color: str = "#000000") -> Layer:
        color = _normalize_color(color)
        layer = Layer(name=name, color=color)
        self.layers.append(layer)
        return layer

    def get_or_create_layer_by_color(self, color: str) -> Layer:
        """Used by importers: find first layer matching this color or create one."""
        color = _normalize_color(color)
        for layer in self.layers:
            if layer.color.upper() == color:
                return layer
        return self.add_layer(name=color, color=color)

    def remove_layer(self, layer: Layer):
        if layer in self.layers:
            self.layers.remove(layer)

    # ── Shape API ─────────────────────────────────────────────────────────────

    def find_shape(self, shape_id: int) -> tuple[Layer | None, Shape | None]:
        for layer in self.layers:
            for shape in layer.shapes:
                if shape.id == shape_id:
                    return layer, shape
        return None, None

    def move_shape_to_layer(self, shape_id: int, target_layer: Layer) -> bool:
        src_layer, shape = self.find_shape(shape_id)
        if src_layer is None or src_layer is target_layer:
            return False
        src_layer.shapes.remove(shape)
        target_layer.shapes.append(shape)
        if not src_layer.shapes:
            self.layers.remove(src_layer)
        return True

    def move_shape_to_color(self, shape_id: int, color: str):
        target = self.get_or_create_layer_by_color(color)
        self.move_shape_to_layer(shape_id, target)

    def remove_shape(self, shape_id: int):
        layer, shape = self.find_shape(shape_id)
        if layer and shape:
            layer.shapes.remove(shape)
            if not layer.shapes:
                self.layers.remove(layer)

    def clear(self):
        self.layers.clear()
