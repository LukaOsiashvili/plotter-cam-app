from __future__ import annotations
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.document import Document, Layer, Shape
    from core.path_model import Path


class Command(ABC):
    @abstractmethod
    def execute(self): ...

    @abstractmethod
    def undo(self): ...


class CommandStack:
    def __init__(self, max_size: int = 200):
        self._undo_stack: list[Command] = []
        self._redo_stack: list[Command] = []
        self._max = max_size

    def push(self, cmd: Command):
        cmd.execute()
        self._undo_stack.append(cmd)
        if len(self._undo_stack) > self._max:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def undo(self) -> bool:
        if not self._undo_stack:
            return False
        cmd = self._undo_stack.pop()
        cmd.undo()
        self._redo_stack.append(cmd)
        return True

    def redo(self) -> bool:
        if not self._redo_stack:
            return False
        cmd = self._redo_stack.pop()
        cmd.execute()
        self._undo_stack.append(cmd)
        return True

    @property
    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    def clear(self):
        self._undo_stack.clear()
        self._redo_stack.clear()


# ── Concrete commands ─────────────────────────────────────────────────────────

class AddShapeCommand(Command):
    def __init__(self, document: Document, shape: Shape, layer: Layer):
        self._doc   = document
        self._shape = shape
        self._layer = layer

    def execute(self):
        if self._shape not in self._layer.shapes:
            self._layer.shapes.append(self._shape)
        if self._layer not in self._doc.layers:
            self._doc.layers.append(self._layer)

    def undo(self):
        if self._shape in self._layer.shapes:
            self._layer.shapes.remove(self._shape)
        if not self._layer.shapes and self._layer in self._doc.layers:
            self._doc.layers.remove(self._layer)


class AddShapesCommand(Command):
    """Add a batch of (shape, layer) pairs as a single undo step - used by Array/Duplicate."""

    def __init__(self, document: Document, entries: list[tuple[Shape, Layer]]):
        self._doc     = document
        self._entries = entries

    def execute(self):
        for shape, layer in self._entries:
            if layer not in self._doc.layers:
                self._doc.layers.append(layer)
            if shape not in layer.shapes:
                layer.shapes.append(shape)

    def undo(self):
        for shape, layer in self._entries:
            if shape in layer.shapes:
                layer.shapes.remove(shape)
            if not layer.shapes and layer in self._doc.layers:
                self._doc.layers.remove(layer)


class RemoveShapesCommand(Command):
    def __init__(self, document: Document, shape_ids: list[int]):
        self._doc = document
        self._shape_ids = shape_ids
        self._snapshots: list[tuple[Layer, Shape, int]] = []  # (layer, shape, index)

    def execute(self):
        self._snapshots.clear()
        for sid in self._shape_ids:
            layer, shape = self._doc.find_shape(sid)
            if layer and shape:
                idx = layer.shapes.index(shape)
                self._snapshots.append((layer, shape, idx))
                layer.shapes.remove(shape)
                if not layer.shapes and layer in self._doc.layers:
                    self._doc.layers.remove(layer)

    def undo(self):
        for layer, shape, idx in reversed(self._snapshots):
            if layer not in self._doc.layers:
                self._doc.layers.append(layer)
            layer.shapes.insert(idx, shape)


class TransformShapesCommand(Command):
    """Replace the path on one or more shapes - supports mirror, rotate, align."""

    def __init__(self, shapes: list[Shape], new_paths: list[Path]):
        self._shapes    = shapes
        self._new_paths = new_paths
        self._old_paths = [s.path for s in shapes]

    def execute(self):
        for shape, new_path in zip(self._shapes, self._new_paths):
            shape.path = new_path

    def undo(self):
        for shape, old_path in zip(self._shapes, self._old_paths):
            shape.path = old_path


class CompositeCommand(Command):
    """Bundle several commands into a single undo step - used by boolean ops
    (remove originals + add result as one atomic action)."""

    def __init__(self, commands: list[Command]):
        self._commands = commands

    def execute(self):
        for cmd in self._commands:
            cmd.execute()

    def undo(self):
        for cmd in reversed(self._commands):
            cmd.undo()


class SetShapePathCommand(Command):
    """Replace a single shape's path wholesale - used by node/point editing."""

    def __init__(self, shape: Shape, new_path: Path):
        self._shape    = shape
        self._new_path = new_path
        self._old_path = shape.path

    def execute(self):
        self._shape.path = self._new_path

    def undo(self):
        self._shape.path = self._old_path


class SetTextCommand(Command):
    """Replace a shape's compiled path AND its live TextData together - used
    by the text tool while the text stays editable (font/align/spacing edits
    regenerate the path from the same source string)."""

    def __init__(self, shape: Shape, new_path: Path, new_text):
        self._shape    = shape
        self._new_path = new_path
        self._new_text = new_text
        self._old_path = shape.path
        self._old_text = shape.text

    def execute(self):
        self._shape.path = self._new_path
        self._shape.text = self._new_text

    def undo(self):
        self._shape.path = self._old_path
        self._shape.text = self._old_text


class ConvertToCurvesCommand(Command):
    """Ctrl+Q - discard a shape's live TextData, freezing its current path as
    plain geometry. The path itself doesn't change; only editability is lost."""

    def __init__(self, shape: Shape):
        self._shape    = shape
        self._old_text = shape.text

    def execute(self):
        self._shape.text = None

    def undo(self):
        self._shape.text = self._old_text


class MoveShapeToLayerCommand(Command):
    def __init__(self, document: Document, shape_id: int, target_layer: Layer):
        self._doc = document
        self._shape_id = shape_id
        self._target = target_layer
        self._source: Layer | None = None

    def execute(self):
        self._source, _ = self._doc.find_shape(self._shape_id)
        self._doc.move_shape_to_layer(self._shape_id, self._target)

    def undo(self):
        if self._source:
            self._doc.move_shape_to_layer(self._shape_id, self._source)
