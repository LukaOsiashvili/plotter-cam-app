from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTreeWidget, QAbstractItemView


class LayerTreeWidget(QTreeWidget):
    """
    Two-level tree: Layer nodes at top, Shape nodes as children.
    Drag/drop rules:
    - Layer nodes: reorder among top level only
    - Shape nodes: reorder within or move between layer nodes
    """

    def _get_type(self, item):
        if item is None:
            return None
        data = item.data(0, Qt.ItemDataRole.UserRole)
        return data.get("type") if data else None

    def _drop_is_valid(self, event) -> bool:
        source_type = self._get_type(self.currentItem())
        if source_type is None:
            return False

        target   = self.itemAt(event.position().toPoint())
        position = self.dropIndicatorPosition()

        if source_type == "layer":
            if position == QAbstractItemView.DropIndicatorPosition.OnItem:
                return self._get_type(target) == "layer"
            if position == QAbstractItemView.DropIndicatorPosition.OnViewport:
                return True
            return self._get_type(target) == "layer"

        if source_type == "shape":
            if position == QAbstractItemView.DropIndicatorPosition.OnItem:
                return self._get_type(target) == "layer"
            if position == QAbstractItemView.DropIndicatorPosition.OnViewport:
                return False
            return self._get_type(target) == "shape"

        return False

    def dragMoveEvent(self, event):
        if self._drop_is_valid(event):
            super().dragMoveEvent(event)
        else:
            event.ignore()

    def dropEvent(self, event):
        if self._drop_is_valid(event):
            super().dropEvent(event)
        else:
            event.ignore()
