from PySide6.QtWidgets import (
    QMainWindow, QToolBar,
    QStatusBar, QFileDialog, QMessageBox, QDialog,
    QWidget, QVBoxLayout, QHBoxLayout, QApplication,
    QLabel, QFrame
)
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtCore import Qt, QTimer

from pathlib import Path as FsPath
from dataclasses import replace

from core.document import Document, Layer, Shape
from core.commands import (
    CommandStack, AddShapeCommand, AddShapesCommand, RemoveShapesCommand, MoveShapeToLayerCommand,
    TransformShapesCommand, SetShapePathCommand, CompositeCommand, SetTextCommand, ConvertToCurvesCommand,
)
from core import boolean_ops
from ui.text_engine import compile_text_path, compile_text_glyphs
from core import transforms
from core.importers.svg import import_svg
from core.importers.dxf import import_dxf
from core.serializer import save_dcam, load_dcam, DCAM_EXT
from core.exporters.gcode import export_gcode, generate_gcode
from core.exporters.svg import export_svg
from core.toolpath import estimate_job_time_seconds
from core.theme import get_theme, set_theme, load_builtin, Theme
from core.serial_link import SerialWorker

from ui.canvas.canvas_view import CAMCanvasWithRulers
from ui.canvas.tools.base_tool import ToolMode
from ui.canvas.tools.select_tool import SelectTool
from ui.canvas.tools.point_edit_tool import PointEditTool
from ui.canvas.tools.line_tool import LineTool
from ui.canvas.tools.polyline_tool import PolylineTool
from ui.canvas.tools.rect_tool import RectTool
from ui.canvas.tools.circle_tool import CircleTool
from ui.canvas.tools.ngon_tool import NgonTool
from ui.canvas.tools.bezier_tool import BezierTool
from ui.canvas.tools.text_tool import TextTool

from ui.panels.layer_panel import LayerPanel
from ui.widgets.tool_panel import ToolPanel
from ui.widgets.operations_bar import OperationsBar
from ui.widgets.text_toolbar import TextToolbar
from ui.widgets.machine_panel import MachinePanel
from ui.widgets.color_palette import ColorPaletteWidget
from ui.dialogs.layer_dialog import LayerDialog
from ui.dialogs.rotate_dialog import RotateDialog
from ui.dialogs.work_area_dialog import WorkAreaDialog
from ui.dialogs.array_dialog import ArrayDialog
from ui.dialogs.simulation_window import SimulationWindow
from ui.dialogs.connect_dialog import ConnectDialog
from ui.dialogs.machine_settings_dialog import MachineSettingsDialog, parse_settings_line

_STATUS_POLL_MS = 200   # '?' position request rate while connected


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("DIY CAM Software")
        self.setMinimumSize(1200, 650)
        self.resize(1400, 850)
        self.showMaximized()

        self.document      = Document()
        self.cmd_stack     = CommandStack()
        self._selection    : list[int] = []
        self._ngon_sides   = 6
        self._tools        : dict = {}  # mode → tool instance
        self._current_file : str | None = None
        self._dirty        : bool = False

        self._build_central()
        self._build_menu()
        self._build_toolbar()
        self._build_statusbar()

        self._apply_theme()
        self._on_tool_changed(ToolMode.SELECT)
        self.canvas.set_work_area(self.document.work_w_mm, self.document.work_h_mm)

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_central(self):
        self.canvas      = CAMCanvasWithRulers()
        self.palette     = ColorPaletteWidget()
        self.tool_panel  = ToolPanel()
        self.ops_bar     = OperationsBar()
        self.text_toolbar = TextToolbar()
        self.text_toolbar.setVisible(False)
        self.layer_panel = LayerPanel()
        self.machine_panel = MachinePanel()

        right_col = QWidget()
        right_col.setFixedWidth(340)
        right_layout = QVBoxLayout(right_col)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)
        right_layout.addWidget(self.layer_panel, 1)
        right_layout.addWidget(self.machine_panel)

        middle = QWidget()
        mid_layout = QVBoxLayout(middle)
        mid_layout.setContentsMargins(0, 0, 0, 0)
        mid_layout.setSpacing(8)
        mid_layout.addWidget(self.canvas)
        mid_layout.addWidget(self.palette)

        columns = QWidget()
        col_layout = QHBoxLayout(columns)
        col_layout.setContentsMargins(0, 0, 0, 0)
        col_layout.setSpacing(8)
        col_layout.addWidget(self.tool_panel)
        col_layout.addWidget(middle)
        col_layout.addWidget(right_col)

        central = QWidget()
        layout  = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        layout.addWidget(self.ops_bar)
        layout.addWidget(self.text_toolbar)
        layout.addWidget(columns)
        self.setCentralWidget(central)

        self.layer_panel.shapes_removed.connect(self._on_shapes_removed)
        self.layer_panel.layer_removed.connect(self._on_layer_removed)
        self.layer_panel.layer_settings.connect(self._on_layer_settings)
        self.layer_panel.shape_clicked.connect(self._on_tree_shape_clicked)
        self.layer_panel.layer_visibility_toggled.connect(self._on_layer_visibility)
        self.layer_panel.layer_lock_toggled.connect(self._on_layer_lock)

        self.machine_panel.connect_triggered.connect(self.on_connect)
        self.machine_panel.disconnect_triggered.connect(self.on_disconnect)
        self.machine_panel.send_triggered.connect(self.on_send)
        self.machine_panel.pause_triggered.connect(self.on_pause_job)
        self.machine_panel.resume_triggered.connect(self.on_resume_job)
        self.machine_panel.stop_triggered.connect(self.on_stop_job)
        self.machine_panel.cancel_triggered.connect(self.on_cancel_job)
        self.machine_panel.motion_mode_changed.connect(self._on_motion_mode_changed)
        self.machine_panel.estimate_requested.connect(self.on_estimate_time)
        self.machine_panel.simulate_requested.connect(self.on_simulate)
        self.machine_panel.jog_requested.connect(self.on_jog)
        self.machine_panel.set_zero_requested.connect(lambda: self._send_machine_command("G92 X0 Y0"))
        self.machine_panel.go_home_requested.connect(lambda: self._send_machine_command("G28"))
        self.machine_panel.settings_requested.connect(self.on_machine_settings)
        self.machine_panel.go_zero_requested.connect(lambda: self._send_machine_command("G90 G0 X0 Y0"))
        self.machine_panel.pen_requested.connect(lambda down: self._send_machine_command("M3" if down else "M5"))
        self.machine_panel.set_motion_mode(self.document.motion_mode)
        self._loaded_job_path: str | None = None
        self._loaded_job_text: str | None = None
        self._serial: SerialWorker | None = None
        self._status_timer = QTimer(self)
        self._status_timer.setInterval(_STATUS_POLL_MS)
        self._status_timer.timeout.connect(self._poll_machine_status)

        self.canvas.selection_changed.connect(self._on_selection_changed)
        self.canvas.shape_drawn.connect(self._on_shape_drawn)
        self.canvas.cursor_moved.connect(self._on_cursor_moved)
        self.canvas.transform_changed.connect(self._on_zoom_changed)
        self.canvas.shapes_moved.connect(self._on_shapes_moved)
        self.canvas.shapes_resized.connect(self._on_shapes_resized)
        self.canvas.shape_path_edited.connect(self._on_shape_path_edited)
        self.canvas.shape_text_edited.connect(self._on_shape_text_edited)
        self.canvas.shape_double_clicked.connect(self._on_shape_double_clicked)
        self.text_toolbar.style_changed.connect(self._on_text_style_changed)
        self.palette.color_picked.connect(self._on_color_picked)
        self.tool_panel.tool_changed.connect(self._on_tool_changed)
        self.tool_panel.ngon_sides_changed.connect(self._on_ngon_sides_changed)
        self.ops_bar.mirror_x_triggered.connect(self._on_mirror_x)
        self.ops_bar.mirror_y_triggered.connect(self._on_mirror_y)
        self.ops_bar.rotate_triggered.connect(self._on_rotate)
        self.ops_bar.array_triggered.connect(self._on_array)
        self.ops_bar.align_triggered.connect(self._on_align)
        self.ops_bar.union_triggered.connect(self._on_union)
        self.ops_bar.subtract_triggered.connect(self._on_subtract)
        self.ops_bar.intersect_triggered.connect(self._on_intersect)
        self.ops_bar.undo_triggered.connect(self.on_undo)
        self.ops_bar.redo_triggered.connect(self.on_redo)
        self.ops_bar.size_changed.connect(self._on_size_changed)

    def _build_menu(self):
        mb = self.menuBar()

        file_menu = mb.addMenu("&File")
        self._add_action(file_menu, "New",             "Ctrl+N",       self.on_new)
        file_menu.addSeparator()
        self._add_action(file_menu, "Open...",         "Ctrl+O",       self.on_open)
        self._add_action(file_menu, "Save",            "Ctrl+S",       self.on_save)
        self._add_action(file_menu, "Save As...",      "Ctrl+Shift+S", self.on_save_as)
        file_menu.addSeparator()
        self._add_action(file_menu, "Import SVG...",   "Ctrl+I",       self.on_import_svg)
        self._add_action(file_menu, "Import DXF...",   "Ctrl+Shift+I", self.on_import_dxf)
        file_menu.addSeparator()
        self._add_action(file_menu, "Export GCODE...", "Ctrl+E",       self.on_export_gcode)
        self._add_action(file_menu, "Export SVG...",   None,           self.on_export_svg)
        file_menu.addSeparator()
        self._add_action(file_menu, "Open Job (G-code)...", None,     self.on_open_job)
        file_menu.addSeparator()
        self._add_action(file_menu, "Exit",            None,           self.close)

        edit_menu = mb.addMenu("&Edit")
        self._add_action(edit_menu, "Undo", "Ctrl+Z", self.on_undo)
        self._add_action(edit_menu, "Redo", "Ctrl+Y", self.on_redo)
        edit_menu.addSeparator()
        self._add_action(edit_menu, "Convert to Curves", "Ctrl+Q", self.on_convert_to_curves)
        edit_menu.addSeparator()
        self._add_action(edit_menu, "Work Area...", None, self.on_work_area_settings)

        view_menu = mb.addMenu("&View")
        self._add_action(view_menu, "Fit to Window", "Ctrl+F", self.canvas.fit_view)
        self._add_action(view_menu, "Reset Zoom",    "Ctrl+0", self.canvas.reset_zoom)
        view_menu.addSeparator()
        theme_menu = view_menu.addMenu("Theme")
        for name, label in [("midnight", "Midnight"), ("slate", "Slate"), ("light", "Light"), ("jetbrains_dark", "JetBrains Darcula"), ("jetbrains_light_cards", "JetBrains Light Cards")]:
            action = QAction(label, self)
            action.setData(name)
            action.triggered.connect(lambda checked, n=name: self._on_theme_selected(n))
            theme_menu.addAction(action)
        theme_menu.addSeparator()
        self._add_action(theme_menu, "Import Theme...", None, self._on_import_theme)

        machine_menu = mb.addMenu("&Machine")
        self._add_action(machine_menu, "Simulate Toolpath...",   "Ctrl+M", self.on_simulate)
        machine_menu.addSeparator()
        self._add_action(machine_menu, "Connect to Plotter...", "Ctrl+K", self.on_connect)
        machine_menu.addSeparator()
        self._add_action(machine_menu, "Send to Plotter",        "Ctrl+P", self.on_send)

        help_menu = mb.addMenu("&Help")
        self._add_action(help_menu, "About", None, self.on_about)

    def _build_toolbar(self):
        tb = QToolBar("Main Toolbar")
        tb.setMovable(False)
        self.addToolBar(tb)
        tb.addAction("Import SVG", self.on_import_svg)
        tb.addAction("Import DXF", self.on_import_dxf)
        tb.addSeparator()
        tb.addAction("Export GCODE", self.on_export_gcode)
        tb.addSeparator()
        tb.addAction("Fit View", self.canvas.fit_view)
        tb.addSeparator()
        tb.addAction("Connect", self.on_connect)
        tb.addAction("Send Job", self.on_send)

    def _build_statusbar(self):
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Ready")

        self._lbl_sel   = QLabel("")
        self._lbl_coord = QLabel("X:  -      Y:  -     mm")
        self._lbl_zoom  = QLabel("100%")
        self._lbl_coord.setMinimumWidth(200)
        self._lbl_zoom.setMinimumWidth(52)

        def _vsep() -> QFrame:
            f = QFrame()
            f.setFrameShape(QFrame.Shape.VLine)
            return f

        self.status.addPermanentWidget(self._lbl_sel)
        self.status.addPermanentWidget(_vsep())
        self.status.addPermanentWidget(self._lbl_coord)
        self.status.addPermanentWidget(_vsep())
        self.status.addPermanentWidget(self._lbl_zoom)

    def _add_action(self, menu, label, shortcut, slot):
        action = QAction(label, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(slot)
        menu.addAction(action)
        return action

    # ── Tool management ───────────────────────────────────────────────────────

    def _get_tool(self, mode: str):
        if mode not in self._tools:
            c = self.canvas.canvas
            self._tools[mode] = {
                ToolMode.SELECT:    lambda: SelectTool(c),
                ToolMode.POINT_EDIT: lambda: PointEditTool(c, self.document),
                ToolMode.LINE:      lambda: LineTool(c),
                ToolMode.POLYLINE:  lambda: PolylineTool(c),
                ToolMode.RECT:      lambda: RectTool(c),
                ToolMode.CIRCLE:    lambda: CircleTool(c),
                ToolMode.NGON:      lambda: NgonTool(c, self._ngon_sides),
                ToolMode.BEZIER:    lambda: BezierTool(c),
                ToolMode.TEXT:      lambda: TextTool(c, self.document, self._request_select_tool),
            }.get(mode, lambda: None)()
        return self._tools.get(mode)

    def _on_tool_changed(self, mode: str):
        tool = self._get_tool(mode)
        if tool:
            self.canvas.set_tool(tool)
        labels = {
            ToolMode.SELECT:     "Select - click or drag to select shapes",
            ToolMode.POINT_EDIT: "Edit Points - drag a node to reshape the selected shape",
            ToolMode.LINE:     "Draw Line - click two points  (Shift = axis-aligned)",
            ToolMode.POLYLINE: "Draw Polyline - click points, Enter to finish",
            ToolMode.RECT:     "Draw Rectangle - click two corners  (Shift = square)",
            ToolMode.CIRCLE:   "Draw Circle/Ellipse - click center then edge  (Shift = circle)",
            ToolMode.NGON:     f"Draw Polygon ({self._ngon_sides} sides) - click center then edge  (Shift = equilateral)",
            ToolMode.BEZIER:   "Bezier Pen - click for a corner, click+drag for a curve handle, Enter to finish, click start point to close",
            ToolMode.TEXT:     "Text - click for artistic text, click+drag for a paragraph box; Escape cancels, click elsewhere commits",
        }
        self.status.showMessage(labels.get(mode, mode))
        self._sync_text_toolbar()

    def _request_select_tool(self):
        """Passed into TextTool - called when an existing-shape edit session
        ends (commit or cancel), so control returns to Select for normal
        move/transform. Deferred to dodge tool-switch re-entrancy."""
        QTimer.singleShot(0, lambda: self.tool_panel.set_tool(ToolMode.SELECT))

    def _on_ngon_sides_changed(self, sides: int):
        self._ngon_sides = sides
        if ToolMode.NGON in self._tools:
            self._tools[ToolMode.NGON].sides = sides

    # ── Canvas signal handlers ────────────────────────────────────────────────

    def _on_shape_drawn(self, shape: Shape, color: str):
        layer = self.document.get_or_create_layer_by_color(color)
        cmd   = AddShapeCommand(self.document, shape, layer)
        self.cmd_stack.push(cmd)
        self.canvas.draw_shape(shape, color)
        self.layer_panel.add_shape(layer, shape)
        self._mark_dirty()
        self.status.showMessage(f"Shape drawn  |  Layer: {layer.name}")
        self.tool_panel.set_tool(ToolMode.SELECT)

    def _on_cursor_moved(self, x_mm: float, y_mm: float):
        self._lbl_coord.setText(f"X: {x_mm:7.2f}   Y: {y_mm:7.2f}  mm")

    def _on_zoom_changed(self, ox, oy, sx, sy):
        self._lbl_zoom.setText(f"{int(sx * 100)}%")

    def _on_selection_changed(self, shape_ids: list):
        self._selection = list(shape_ids)
        self.palette.set_has_selection(bool(shape_ids))
        self.layer_panel.sync_selection(shape_ids)
        point_edit_ok = False
        single_shape = None
        if len(shape_ids) == 1:
            _, single_shape = self.document.find_shape(shape_ids[0])
            point_edit_ok = single_shape is not None and single_shape.text is None
        self.tool_panel.set_point_edit_enabled(point_edit_ok)
        self.ops_bar.set_util_enabled(bool(shape_ids))
        self.ops_bar.set_boolean_enabled(len(shape_ids) >= 2)
        self._sync_text_toolbar()
        self._update_size_fields()

        n = len(shape_ids)
        self._lbl_sel.setText(f"{n} selected" if n else "")

        if not shape_ids:
            self.status.showMessage("Ready")
        elif n == 1:
            layer, shape = self.document.find_shape(shape_ids[0])
            if layer:
                self.status.showMessage(
                    f"Selected: {shape.source or 'Shape'}  |  "
                    f"Layer: {layer.name}  |  Operation: {layer.operation}"
                )
        else:
            self.status.showMessage(f"{n} shapes selected")

    def _on_color_picked(self, new_color: str):
        if not self._selection:
            return
        for sid in list(self._selection):
            layer, shape = self.document.find_shape(sid)
            if layer and shape:
                target = self.document.get_or_create_layer_by_color(new_color)
                cmd = MoveShapeToLayerCommand(self.document, sid, target)
                self.cmd_stack.push(cmd)
        self._refresh_views()
        self.canvas.deselect_all()
        self._mark_dirty()
        self.status.showMessage(f"Reassigned {len(self._selection)} shape(s) to {new_color.upper()}")

    def _on_tree_shape_clicked(self, shape_id: int):
        self.canvas.select_shape(shape_id, additive=False)
        self.canvas.canvas.setFocus()

    def _on_shapes_removed(self, shape_ids: list):
        cmd = RemoveShapesCommand(self.document, shape_ids)
        self.cmd_stack.push(cmd)
        for sid in shape_ids:
            self.canvas.clear_shape(sid)
        self._rebuild_layer_panel()
        self._mark_dirty()

    def _on_layer_removed(self, layer: Layer):
        self.canvas.clear_layer(layer)
        self.document.remove_layer(layer)
        self._rebuild_layer_panel()
        self._mark_dirty()

    def _on_layer_visibility(self, layer: Layer, visible: bool):
        layer.visible = visible
        self.canvas.rebuild(self.document.layers)
        self._mark_dirty()

    def _on_layer_lock(self, layer: Layer, locked: bool):
        layer.locked = locked
        self._mark_dirty()

    def _on_layer_settings(self, layer: Layer):
        dialog = LayerDialog(layer, parent=self)
        if dialog.exec():
            self.layer_panel.update_layer_node_label(layer)
            self._refresh_views()
            self._mark_dirty()

    def on_work_area_settings(self):
        dialog = WorkAreaDialog(
            self.document.work_w_mm, self.document.work_h_mm,
            self.document.origin_corner, parent=self
        )
        if dialog.exec():
            w_mm, h_mm, origin_corner = dialog.values()
            self.document.work_w_mm     = w_mm
            self.document.work_h_mm     = h_mm
            self.document.origin_corner = origin_corner
            self.canvas.set_work_area(w_mm, h_mm)
            self._mark_dirty()
            self.status.showMessage(f"Work area: {w_mm:.1f} x {h_mm:.1f} mm  |  Origin: {origin_corner}")

    # ── Undo / Redo ───────────────────────────────────────────────────────────

    def on_undo(self):
        if self.cmd_stack.undo():
            self._refresh_views()
            self._mark_dirty()
            self.status.showMessage("Undo")

    def on_redo(self):
        if self.cmd_stack.redo():
            self._refresh_views()
            self._mark_dirty()
            self.status.showMessage("Redo")

    # ── Project file (New / Open / Save) ─────────────────────────────────────

    def on_new(self):
        if not self._confirm_discard():
            return
        self.document      = Document()
        self.cmd_stack     = CommandStack()
        self._current_file = None
        self._dirty        = False
        self._selection    = []
        self._tools        = {}
        self.canvas.set_work_area(self.document.work_w_mm, self.document.work_h_mm)
        self.machine_panel.set_motion_mode(self.document.motion_mode)
        self._refresh_views()
        self._on_tool_changed(ToolMode.SELECT)
        self._update_title()
        self.status.showMessage("New project")

    def on_open(self):
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Project", "",
            f"DCAM Files (*{DCAM_EXT});;All Files (*)"
        )
        if not path:
            return
        try:
            doc = load_dcam(path)
            self.document      = doc
            self.cmd_stack     = CommandStack()
            self._current_file = path
            self._dirty        = False
            self._selection    = []
            self._tools        = {}
            self.canvas.set_work_area(self.document.work_w_mm, self.document.work_h_mm)
            self.machine_panel.set_motion_mode(self.document.motion_mode)
            self._refresh_views()
            self._update_title()
            self.canvas.fit_view()
            self.status.showMessage(f"Opened: {FsPath(path).name}")
        except Exception as e:
            QMessageBox.warning(self, "Open Failed", str(e))

    def on_save(self):
        if self._current_file:
            self._do_save(self._current_file)
        else:
            self.on_save_as()

    def on_save_as(self):
        default = FsPath(self._current_file).stem if self._current_file else "project"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Project As", f"{default}{DCAM_EXT}",
            f"DCAM Files (*{DCAM_EXT});;All Files (*)"
        )
        if path:
            self._do_save(path)

    def _do_save(self, path: str):
        try:
            save_dcam(self.document, path)
            self._current_file = path
            self._dirty        = False
            self._update_title()
            self.status.showMessage(f"Saved: {FsPath(path).name}")
        except Exception as e:
            QMessageBox.warning(self, "Save Failed", str(e))

    def _mark_dirty(self):
        self._dirty = True
        self._update_title()

    def _update_title(self):
        dirty = " *" if self._dirty else ""
        if self._current_file:
            name = FsPath(self._current_file).stem
            self.setWindowTitle(f"DIY CAM Software - {name}{dirty}")
        else:
            self.setWindowTitle(f"DIY CAM Software{dirty}")

    def _confirm_discard(self) -> bool:
        """Returns True if it's safe to discard the current project."""
        if not self._dirty:
            return True
        reply = QMessageBox.question(
            self, "Unsaved Changes",
            "You have unsaved changes. Discard and continue?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return reply == QMessageBox.StandardButton.Discard

    def closeEvent(self, event):
        if self._dirty:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "Save changes before closing?",
                QMessageBox.StandardButton.Save |
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save,
            )
            if reply == QMessageBox.StandardButton.Save:
                self.on_save()
                if self._dirty:   # save was cancelled (no path chosen yet)
                    event.ignore()
                    return
            elif reply == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
        if self._serial:
            self._serial.disconnect()
            self._serial.wait(2000)
        event.accept()

    # ── Import ────────────────────────────────────────────────────────────────

    def on_import_svg(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import SVG", "", "SVG Files (*.svg)")
        if not path:
            return
        try:
            before  = {id(l): len(l.shapes) for l in self.document.layers}
            affected = import_svg(path, self.document)
            total   = 0
            for layer in affected:
                old_count  = before.get(id(layer), 0)
                new_shapes = layer.shapes[old_count:]
                for shape in new_shapes:
                    self.canvas.draw_shape(shape, layer.color)
                    self.layer_panel.add_shape(layer, shape)
                total += len(new_shapes)
            self.canvas.fit_view()
            self.status.showMessage(f"Imported {total} shapes from {path}")
        except Exception as e:
            self.status.showMessage(f"SVG import failed: {e}")

    def on_import_dxf(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import DXF", "", "DXF Files (*.dxf)")
        if not path:
            return
        try:
            before   = {id(l): len(l.shapes) for l in self.document.layers}
            affected = import_dxf(path, self.document)
            total    = 0
            for layer in affected:
                old_count  = before.get(id(layer), 0)
                new_shapes = layer.shapes[old_count:]
                for shape in new_shapes:
                    self.canvas.draw_shape(shape, layer.color)
                    self.layer_panel.add_shape(layer, shape)
                total += len(new_shapes)
            self.canvas.fit_view()
            self.status.showMessage(f"Imported {total} shapes from {path}")
        except Exception as e:
            self.status.showMessage(f"DXF import failed: {e}")

    # ── Export / Machine ──────────────────────────────────────────────────────

    def on_export_gcode(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export GCODE", "output.gcode", "GCODE Files (*.gcode *.nc *.txt)"
        )
        if not path:
            return
        try:
            export_gcode(self.document, path)
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))
            return
        self.status.showMessage(f"G-code exported to {path}")

    def _on_motion_mode_changed(self, mode: str):
        self.document.motion_mode = mode
        self.status.showMessage(f"Motion mode: {mode}")

    def on_simulate(self):
        window = SimulationWindow(self.document, parent=self)
        window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        window.setWindowModality(Qt.WindowModality.NonModal)
        self._sim_window = window   # keep alive; not modal, editing can continue
        window.show()

    def on_export_svg(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export SVG", "output.svg", "SVG Files (*.svg)"
        )
        if not path:
            return
        try:
            export_svg(self.document, path)
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))
            return
        self.status.showMessage(f"SVG exported to {path}")

    def on_estimate_time(self):
        seconds = estimate_job_time_seconds(self.document)
        h, rem = divmod(int(seconds), 3600)
        m, s   = divmod(rem, 60)
        text = f"{h}h {m:02}m {s:02}s" if h else f"{m}m {s:02}s"
        self.machine_panel.set_time_estimate(text)
        self.status.showMessage(f"Estimated job time: {text}")

    def on_open_job(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Job (G-code)", "", "GCODE Files (*.gcode *.nc *.txt);;All Files (*)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError as e:
            QMessageBox.critical(self, "Open failed", str(e))
            return
        self._loaded_job_path = path
        self._loaded_job_text = text
        line_count = len([l for l in text.splitlines() if l.strip()])
        name = FsPath(path).name
        self.machine_panel.set_loaded_job(f"Job loaded: {name} ({line_count} lines)")
        self.status.showMessage(f"Job loaded from {path} - ready to send once a connection exists")

    # ── Machine connection / streaming ──────────────────────────────────────

    def on_connect(self):
        dlg = ConnectDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        port, baud = dlg.selected_port(), dlg.selected_baud()
        if not port:
            QMessageBox.warning(self, "Connect", "No serial port selected.")
            return

        self.machine_panel.set_status(f"Connecting to {port}...")
        self._serial = SerialWorker(port, baud)
        self._serial.connected.connect(self._on_serial_connected)
        self._serial.disconnected.connect(self._on_serial_disconnected)
        self._serial.job_progress.connect(self._on_serial_progress)
        self._serial.job_finished.connect(self._on_serial_job_finished)
        self._serial.log.connect(self._on_serial_log)
        self._serial.status.connect(self.machine_panel.set_position)
        self._serial.machine_reset.connect(self._on_machine_reset)
        self._serial.settings_received.connect(self._on_settings_received)
        self._serial.motor_power.connect(self.machine_panel.set_motor_power)
        self._serial.motor_power_problem.connect(self._on_motor_power_problem)
        self._serial.start()

    def on_disconnect(self):
        if self._serial:
            self._serial.disconnect()

    def _on_serial_connected(self, machine_name: str):
        self.machine_panel.set_connected(True, machine_name)
        self.status.showMessage(f"Connected - {machine_name}")
        self._status_timer.start()

    def _on_serial_disconnected(self, reason: str):
        self._status_timer.stop()
        self.machine_panel.set_connected(False)
        if reason:
            self.status.showMessage(f"Disconnected: {reason}")
            QMessageBox.warning(self, "Connection lost", reason)
        else:
            self.status.showMessage("Disconnected")
        if self._serial:
            self._serial.wait()
        self._serial = None

    def _on_serial_progress(self, done: int, total: int):
        self.machine_panel.set_progress(done, total)

    def _on_serial_job_finished(self, success: bool):
        self.machine_panel.set_job_active(False)
        self.status.showMessage("Job complete" if success else "Job stopped/aborted")

    def _on_serial_log(self, text: str):
        self.machine_panel.append_log(text)

    def on_send(self):
        if not self._serial:
            QMessageBox.warning(self, "Send Job", "Connect to a plotter first.")
            return
        text = self._loaded_job_text if self._loaded_job_text else generate_gcode(self.document)
        lines = text.splitlines()
        self.machine_panel.set_job_active(True)
        self._serial.send_job(lines)
        self.status.showMessage("Streaming job...")

    def on_pause_job(self):
        if self._serial:
            self._serial.request_pause()
            self.status.showMessage("Job paused")

    def on_resume_job(self):
        if self._serial:
            self._serial.request_resume()
            self.status.showMessage("Job resumed")

    def on_stop_job(self):
        if self._serial:
            self._serial.request_stop()
            self.status.showMessage("Stopping job...")

    def on_cancel_job(self):
        if self._serial:
            self._serial.request_cancel()
            self.status.showMessage("Cancelling job - returning to start...")

    def _on_machine_reset(self):
        self.status.showMessage("The machine restarted - position lost")
        QMessageBox.warning(
            self, "Machine restarted",
            "The plotter restarted unexpectedly (power dip or reset button).\n\n"
            "It no longer knows where the carriage is, and a running job was stopped "
            "- the pen may have stopped mid-drawing.\n\n"
            "Switch the motor power off, push the carriage to the parking corner (0,0), "
            "then continue.")

    def _on_motor_power_problem(self, during_job: bool):
        if during_job:
            self.status.showMessage("Motor power lost - job stopped")
            QMessageBox.warning(
                self, "Motor power lost",
                "The motor power supply dropped during the job, so the plotter stopped.\n\n"
                "Moves sent while the motors had no power did not happen, so the position "
                "the plotter believes in may be wrong.\n\n"
                "Switch the power module back on, push the carriage to the parking corner "
                "(0,0), then start again.")
        else:
            self.status.showMessage("Motor power is off - nothing was drawn")
            QMessageBox.information(
                self, "Motor power is off",
                "The plotter's motors have no power, so the job was not started.\n\n"
                "Switch on the power module (and wake the power bank), then send the job again.")

    def on_machine_settings(self):
        if self._serial:
            self._serial.request_settings()

    def _on_settings_received(self, line: str):
        values = parse_settings_line(line)
        if not values:
            return
        dialog = MachineSettingsDialog(values, self)
        result = dialog.exec()
        if result == MachineSettingsDialog.RESET:
            self._send_machine_command("$RST")
            self.status.showMessage("Plotter settings restored to defaults")
        elif result == QDialog.DialogCode.Accepted:
            commands = dialog.changed_commands()
            for command in commands:
                self._send_machine_command(command)
            self.status.showMessage(f"{len(commands)} plotter setting(s) saved" if commands
                                    else "No settings changed")

    def on_jog(self, dx_mm: float, dy_mm: float):
        self._send_machine_command(f"$J X{dx_mm:.3f} Y{dy_mm:.3f}")

    def _send_machine_command(self, line: str):
        if self._serial:
            self._serial.send_command(line)

    def _poll_machine_status(self):
        if self._serial:
            self._serial.request_status()

    def on_about(self):
        QMessageBox.about(self, "About DIY CAM Software",
            "DIY CAM Software\n\nBachelor's Project\n\n"
            "Built with Python + PySide6\n"
            "ezdxf · svgpathtools · Shapely · pyserial")

    # ── Transform operations ──────────────────────────────────────────────────

    def _on_mirror_x(self):
        box = self._group_bounding_box(self._selection)
        if box is None:
            return
        cx = (box[0] + box[2]) / 2
        self._apply_transform(lambda p: transforms.mirror_x(p, cx))

    def _on_mirror_y(self):
        box = self._group_bounding_box(self._selection)
        if box is None:
            return
        cy = (box[1] + box[3]) / 2
        self._apply_transform(lambda p: transforms.mirror_y(p, cy))

    def _on_rotate(self):
        if not self._selection:
            return
        dialog = RotateDialog(parent=self)
        if dialog.exec():
            angle = dialog.angle()
            box = self._group_bounding_box(self._selection)
            if box is None:
                return
            center = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
            self._apply_transform(lambda p: transforms.rotate(p, angle, center))

    def _apply_transform(self, fn):
        """Apply a path transform to every selected shape, push to undo stack."""
        if not self._selection:
            return
        entries = []
        for sid in self._selection:
            layer, shape = self.document.find_shape(sid)
            if shape:
                entries.append((shape, layer, fn(shape.path)))
        if not entries:
            return
        cmd = TransformShapesCommand([e[0] for e in entries], [e[2] for e in entries])
        self.cmd_stack.push(cmd)
        for shape, layer, _ in entries:
            self.canvas.redraw_shape(shape, layer.color)
        self._mark_dirty()
        self._update_size_fields()

    def _on_align(self, mode: str):
        order = self.canvas.selection_order
        if len(order) < 2:
            self.status.showMessage("Select 2+ shapes - last selected is the alignment reference")
            return
        _, ref_shape = self.document.find_shape(order[-1])
        if not ref_shape:
            return
        entries = []
        for sid in order[:-1]:
            layer, shape = self.document.find_shape(sid)
            if shape:
                entries.append((shape, layer, transforms.align(shape.path, ref_shape.path, mode)))
        if not entries:
            return
        cmd = TransformShapesCommand([e[0] for e in entries], [e[2] for e in entries])
        self.cmd_stack.push(cmd)
        for shape, layer, _ in entries:
            self.canvas.redraw_shape(shape, layer.color)
        self._mark_dirty()

    def _on_array(self):
        if not self._selection:
            return
        dialog = ArrayDialog(parent=self)
        if not dialog.exec():
            return
        count_x, count_y, spacing_x, spacing_y = dialog.values()
        box = self._group_bounding_box(self._selection)
        if box is None:
            return
        # spacing is the gap between copies, not center-to-center offset -
        # the step must clear the whole selection's own footprint first.
        step_x = (box[2] - box[0]) + spacing_x
        step_y = (box[3] - box[1]) + spacing_y
        entries = []
        for sid in self._selection:
            layer, shape = self.document.find_shape(sid)
            if not shape:
                continue
            for row in range(count_y):
                for col in range(count_x):
                    if row == 0 and col == 0:
                        continue   # original stays in place
                    new_path  = transforms.translate(shape.path, col * step_x, row * step_y)
                    new_shape = Shape(path=new_path, source=shape.source)
                    entries.append((new_shape, layer))
        if not entries:
            return
        cmd = AddShapesCommand(self.document, entries)
        self.cmd_stack.push(cmd)
        for shape, layer in entries:
            self.canvas.draw_shape(shape, layer.color)
            self.layer_panel.add_shape(layer, shape)
        self._mark_dirty()
        self.status.showMessage(f"Array: {len(entries)} duplicate(s) created")

    def _on_union(self):
        self._apply_boolean_op(boolean_ops.union)

    def _on_subtract(self):
        self._apply_boolean_op(boolean_ops.subtract, ordered=True)

    def _on_intersect(self):
        self._apply_boolean_op(boolean_ops.intersect)

    def _apply_boolean_op(self, op_fn, ordered: bool = False):
        order = list(self.canvas.selection_order)
        if len(order) < 2:
            self.status.showMessage("Select 2+ shapes for this operation")
            return
        entries = []
        for sid in order:
            layer, shape = self.document.find_shape(sid)
            if shape:
                entries.append((sid, layer, shape))
        if len(entries) < 2:
            return
        if ordered:
            entries = [entries[-1]] + entries[:-1]   # last selected = base, matches align's "last = reference"
        base_layer = entries[0][1]

        new_paths = op_fn([shape for _, _, shape in entries])
        if not new_paths:
            self.status.showMessage("Boolean operation produced no result")
            return

        new_shapes = [Shape(path=p) for p in new_paths]
        remove_cmd = RemoveShapesCommand(self.document, order)
        add_cmd    = AddShapesCommand(self.document, [(s, base_layer) for s in new_shapes])
        self.cmd_stack.push(CompositeCommand([remove_cmd, add_cmd]))

        for sid in order:
            self.canvas.clear_shape(sid)
        for shape in new_shapes:
            self.canvas.draw_shape(shape, base_layer.color)
        self.canvas.deselect_all()
        self._rebuild_layer_panel()
        self._mark_dirty()
        self.status.showMessage(f"{len(new_shapes)} shape(s) created")

    def _on_shapes_moved(self, shape_ids: list, dx: float, dy: float):
        """Live text needs its own TextData.x_mm/y_mm kept in sync - otherwise a
        later re-edit or Convert to Curves regenerates the glyphs at the
        original (pre-move) position, since that's what TextData still says."""
        plain_shapes, plain_paths, text_commands, redraw = [], [], [], []
        for sid in shape_ids:
            layer, shape = self.document.find_shape(sid)
            if not shape:
                continue
            new_path = transforms.translate(shape.path, dx, dy)
            if shape.text is not None:
                new_text = replace(shape.text, x_mm=shape.text.x_mm + dx, y_mm=shape.text.y_mm + dy)
                text_commands.append(SetTextCommand(shape, new_path, new_text))
            else:
                plain_shapes.append(shape)
                plain_paths.append(new_path)
            redraw.append((shape, layer))
        if not redraw:
            return
        commands = list(text_commands)
        if plain_shapes:
            commands.append(TransformShapesCommand(plain_shapes, plain_paths))
        self.cmd_stack.push(commands[0] if len(commands) == 1 else CompositeCommand(commands))
        for shape, layer in redraw:
            self.canvas.redraw_shape(shape, layer.color)
        self._mark_dirty()

    def _on_shape_path_edited(self, shape_id: int, new_path):
        layer, shape = self.document.find_shape(shape_id)
        if not shape:
            return
        cmd = SetShapePathCommand(shape, new_path)
        self.cmd_stack.push(cmd)
        self.canvas.redraw_shape(shape, layer.color)
        self._mark_dirty()
        self._update_size_fields()

    def _on_shape_double_clicked(self, shape_id: int):
        _, shape = self.document.find_shape(shape_id)
        if shape is not None and shape.text is not None:
            self.canvas.select_shape(shape_id)
            self.tool_panel.set_tool(ToolMode.TEXT)

    def _on_shape_text_edited(self, shape_id, new_path, new_text):
        if shape_id is None:
            layer = self.document.get_or_create_layer_by_color(get_theme().draw_color)
            shape = Shape(path=new_path, text=new_text)
            cmd   = AddShapeCommand(self.document, shape, layer)
            self.cmd_stack.push(cmd)
            self.canvas.draw_shape(shape, layer.color)
            self.layer_panel.add_shape(layer, shape)
            self.status.showMessage(f"Text added  |  Layer: {layer.name}")
        else:
            layer, shape = self.document.find_shape(shape_id)
            if not shape:
                return
            cmd = SetTextCommand(shape, new_path, new_text)
            self.cmd_stack.push(cmd)
            self.canvas.redraw_shape(shape, layer.color)
        self._mark_dirty()
        self._update_size_fields()
        self._sync_text_toolbar()

    def _on_text_style_changed(self, changes: dict):
        tool = self._tools.get(ToolMode.TEXT)
        if self.tool_panel.current_tool() == ToolMode.TEXT and tool is not None and tool.apply_style_change(**changes):
            return
        if len(self._selection) == 1:
            layer, shape = self.document.find_shape(self._selection[0])
            if shape is not None and shape.text is not None:
                new_text = replace(shape.text, **changes)
                new_path = compile_text_path(new_text)
                cmd = SetTextCommand(shape, new_path, new_text)
                self.cmd_stack.push(cmd)
                self.canvas.redraw_shape(shape, layer.color)
                self._mark_dirty()

    def on_convert_to_curves(self):
        """Explodes each selected text shape into one shape per glyph - CAD/CAM
        editing needs to select individual letters, not one merged text blob."""
        commands = []
        canvas_updates = []   # (removed_shape_id, layer, new_shapes)
        for sid in list(self._selection):
            layer, shape = self.document.find_shape(sid)
            if shape is None or shape.text is None:
                continue
            glyph_paths = compile_text_glyphs(shape.text)
            if not glyph_paths:
                commands.append(ConvertToCurvesCommand(shape))
                continue
            new_shapes = [Shape(path=p) for p in glyph_paths]
            commands.append(RemoveShapesCommand(self.document, [sid]))
            commands.append(AddShapesCommand(self.document, [(s, layer) for s in new_shapes]))
            canvas_updates.append((sid, layer, new_shapes))
        if not commands:
            return

        self.cmd_stack.push(commands[0] if len(commands) == 1 else CompositeCommand(commands))
        for sid, layer, new_shapes in canvas_updates:
            self.canvas.clear_shape(sid)
            for s in new_shapes:
                self.canvas.draw_shape(s, layer.color)
        if canvas_updates:
            self.canvas.deselect_all()
        self._rebuild_layer_panel()
        self._mark_dirty()
        self._sync_text_toolbar()
        self.status.showMessage(f"Converted {len(self._selection)} text object(s) to curves")

    def _sync_text_toolbar(self):
        tool = self._tools.get(ToolMode.TEXT)
        if self.tool_panel.current_tool() == ToolMode.TEXT and tool is not None:
            self.text_toolbar.set_values(tool.current_text)
            self.text_toolbar.setVisible(True)
            return
        if len(self._selection) == 1:
            _, shape = self.document.find_shape(self._selection[0])
            if shape is not None and shape.text is not None:
                self.text_toolbar.set_values(shape.text)
                self.text_toolbar.setVisible(True)
                return
        self.text_toolbar.setVisible(False)

    def _group_bounding_box(self, shape_ids: list) -> tuple[float, float, float, float] | None:
        boxes = []
        for sid in shape_ids:
            _, shape = self.document.find_shape(sid)
            if shape:
                boxes.append(transforms.bounding_box(shape.path))
        if not boxes:
            return None
        return (min(b[0] for b in boxes), min(b[1] for b in boxes),
                max(b[2] for b in boxes), max(b[3] for b in boxes))

    def _update_size_fields(self):
        box = self._group_bounding_box(self._selection) if self._selection else None
        if box is None:
            self.ops_bar.set_size(0.0, 0.0, enabled=False)
            return
        min_x, min_y, max_x, max_y = box
        self.ops_bar.set_size(max_x - min_x, max_y - min_y, enabled=True)

    def _on_size_changed(self, w_mm: float, h_mm: float):
        box = self._group_bounding_box(self._selection)
        if box is None:
            return
        min_x, min_y, max_x, max_y = box
        old_w = max_x - min_x
        old_h = max_y - min_y
        sx = w_mm / old_w if old_w > 1e-6 else 1.0
        sy = h_mm / old_h if old_h > 1e-6 else 1.0
        self._on_shapes_resized(list(self._selection), sx, sy, min_x, min_y)

    def _on_shapes_resized(self, shape_ids: list, sx: float, sy: float, ax: float, ay: float):
        """Same staleness problem as move: a live text shape's box/font size
        must scale along with its path, or a later re-edit/Convert to Curves
        snaps back to the original size. Non-uniform (sx != sy) resize can't
        be reproduced exactly on regeneration - font size and box width scale
        independently, so it approximates the skew rather than reproducing it."""
        plain_shapes, plain_paths, text_commands, redraw = [], [], [], []
        for sid in shape_ids:
            layer, shape = self.document.find_shape(sid)
            if not shape:
                continue
            new_path = transforms.scale(shape.path, sx, sy, ax, ay)
            if shape.text is not None:
                td = shape.text
                new_text = replace(
                    td,
                    x_mm=ax + (td.x_mm - ax) * sx,
                    y_mm=ay + (td.y_mm - ay) * sy,
                    font_size_mm=max(0.1, td.font_size_mm * sy),
                    box_w_mm=max(0.1, td.box_w_mm * sx),
                    box_h_mm=max(0.1, td.box_h_mm * sy),
                )
                text_commands.append(SetTextCommand(shape, new_path, new_text))
            else:
                plain_shapes.append(shape)
                plain_paths.append(new_path)
            redraw.append((shape, layer))
        if not redraw:
            return
        commands = list(text_commands)
        if plain_shapes:
            commands.append(TransformShapesCommand(plain_shapes, plain_paths))
        self.cmd_stack.push(commands[0] if len(commands) == 1 else CompositeCommand(commands))
        for shape, layer in redraw:
            self.canvas.redraw_shape(shape, layer.color)
        self._mark_dirty()
        self._update_size_fields()

    # ── Theme ─────────────────────────────────────────────────────────────────

    def _apply_theme(self):
        QApplication.instance().setStyleSheet(get_theme().to_qss())
        self.canvas.canvas.apply_theme()

    def _on_theme_selected(self, name: str):
        set_theme(load_builtin(name))
        self._apply_theme()
        self.status.showMessage(f"Theme: {get_theme().name}")

    def _on_import_theme(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Theme", "", "CAM Theme Files (*.camtheme)"
        )
        if path:
            try:
                set_theme(Theme.load(path))
                self._apply_theme()
                self.status.showMessage(f"Theme loaded: {get_theme().name}")
            except Exception as e:
                QMessageBox.warning(self, "Theme Error", f"Could not load theme:\n{e}")

    # ── View helpers ──────────────────────────────────────────────────────────

    def _refresh_views(self):
        self.canvas.rebuild(self.document.layers)
        self._rebuild_layer_panel()

    def _rebuild_layer_panel(self):
        self.layer_panel.clear()
        for layer in self.document.layers:
            for shape in layer.shapes:
                self.layer_panel.add_shape(layer, shape)

    # ── Keyboard shortcuts ────────────────────────────────────────────────────

    NUDGE_SMALL_MM = 0.5
    NUDGE_LARGE_MM = 5.0

    _ALIGN_KEYS = {
        Qt.Key.Key_C: "center_h",   # CorelDRAW: center on X axis
        Qt.Key.Key_E: "center_v",   # CorelDRAW: center on Y axis
        Qt.Key.Key_R: "right",
        Qt.Key.Key_B: "bottom",
    }
    _ARROW_DELTAS = {
        Qt.Key.Key_Left:  (-1, 0),
        Qt.Key.Key_Right: (1, 0),
        Qt.Key.Key_Up:    (0, -1),
        Qt.Key.Key_Down:  (0, 1),
    }

    def keyPressEvent(self, event):
        key       = event.key()
        shift     = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        ctrl      = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        multi_sel = len(self._selection) >= 2

        shortcuts = {
            Qt.Key.Key_Space: ToolMode.SELECT,
            Qt.Key.Key_P:     ToolMode.POLYLINE,
            Qt.Key.Key_Q:     ToolMode.RECT,
            Qt.Key.Key_O:     ToolMode.CIRCLE,
            Qt.Key.Key_N:     ToolMode.NGON,
        }

        if ctrl and key == Qt.Key.Key_A:
            self.canvas.select_all()
        elif key == Qt.Key.Key_Escape:
            if self._selection:
                self.canvas.deselect_all()
            else:
                super().keyPressEvent(event)
        elif key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            if self._selection:
                self._on_shapes_removed(list(self._selection))
        elif key in self._ARROW_DELTAS and self._selection:
            dx, dy = self._ARROW_DELTAS[key]
            step   = self.NUDGE_LARGE_MM if shift else self.NUDGE_SMALL_MM
            self._on_shapes_moved(list(self._selection), dx * step, dy * step)
        elif key in self._ALIGN_KEYS:
            self._on_align(self._ALIGN_KEYS[key])
        elif key == Qt.Key.Key_L:
            if multi_sel:
                self._on_align("left")
            else:
                self.tool_panel.set_tool(ToolMode.LINE)
        elif key == Qt.Key.Key_T:
            if multi_sel:
                self._on_align("top")
            else:
                self._ngon_sides = 3
                self.tool_panel.ngon_sides_changed.emit(3)
                self.tool_panel.set_tool(ToolMode.NGON)
        elif key in shortcuts:
            self.tool_panel.set_tool(shortcuts[key])
        else:
            super().keyPressEvent(event)
