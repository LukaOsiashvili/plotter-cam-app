# DIY CAM Software - cam_app

## Project overview
Bachelor's project: a DIY CAM (Computer-Aided Manufacturing) desktop application built in Python + PySide6.
The goal is to combine the best of CorelDRAW (drawing), LightBurn and RDWorks (CAM workflow) into one tool
that generates G-code and streams it to a DIY Arduino CNC plotter over serial.

The machine uses 28BYJ-48 stepper motors with gears for X/Y axes, and either a servo or stepper for Z (pen up/down).
The firmware (in `../firmware/`) is a custom GRBL-like G-code parser written for Arduino.

## Technology stack
- **UI framework**: PySide6 (LGPL - fully open source, no licence issues for academic use)
- **Vector import**: ezdxf (DXF), svgpathtools (SVG)
- **Geometry**: Shapely (boolean ops, offset paths)
- **Serial comms**: pyserial
- **Theming**: tomllib (built-in Python 3.11+), `.camtheme` TOML files
- **Language**: Python 3.11+
- **Venv**: `.venv/` inside `cam_app/`

## Architecture

### Package structure
```
cam_app/
  core/
    constants.py         # PIXELS_PER_MM, WORK_W_MM, WORK_H_MM
    document.py          # Document, Layer, Shape data model
    path_model.py        # PathSegment types: MoveTo, LineTo, ArcTo, CubicTo, QuadTo, ClosePath
    commands.py          # Undo/redo - Command ABC + CommandStack
    theme.py             # Theme dataclass, get_theme()/set_theme(), .camtheme loader, to_qss()
    importers/
      svg.py             # SVG → Path model (curves preserved, no polyline sampling)
      dxf.py             # DXF → Path model (circles = two 180° arcs)
    exporters/
      gcode.py           # Stub - raises NotImplementedError
  ui/
    canvas/
      canvas.py          # CAMCanvas (QGraphicsView) - rendering, zoom/pan, crosshair, cursor_moved signal
      canvas_view.py     # CAMCanvasWithRulers - wraps canvas + rulers, forwards all public signals
      rulers.py          # Mm-calibrated rulers, dynamic tick spacing, theme-aware
      tools/
        base_tool.py     # ToolMode constants + BaseTool ABC
        select_tool.py   # Click + rubber-band selection, shift-additive
        line_tool.py
        polyline_tool.py
        rect_tool.py
        circle_tool.py
        ngon_tool.py
        draw_tool.py     # Shared base for all drawing tools
    panels/
      layer_panel.py     # Layer cards panel (QScrollArea + LayerCard widgets) - RIGHT DOCK
      layer_tree.py      # QTreeWidget subclass with drag/drop validation (used inside cards)
    widgets/
      tool_panel.py      # Left tool strip - ToolPanel widget
      color_palette.py   # Bottom color swatch bar
      icons.py           # SVG icon strings + make_icon() helper
    dialogs/
      layer_dialog.py    # LayerDialog - per-layer operation settings
    main_window.py
  themes/
    midnight.camtheme    # Default dark blue (Midnight CAM)
    slate.camtheme       # VS Code-inspired dark
    light.camtheme       # Clean light theme
  main.py
```

### Core data model
- `Document` owns a list of `Layer` objects (named, not just color-keyed)
- Each `Layer` has: `name`, `color`, `operation`, `speed`, `rapid_speed`, `pass_count`,
  `line_spacing`, `line_angle`, `visible`, `locked`, `shapes: list[Shape]`
- `Shape` owns a `Path` - a list of `PathSegment` objects
- No polyline approximation in the data model; curves stay as curves through to G-code export

### Canvas / tool architecture
- `CAMCanvas` (QGraphicsView) handles only: rendering shapes, zoom/pan, crosshair overlay,
  emitting raw events (`cursor_moved`, `selection_changed`, `shape_drawn`, `transform_changed`)
- Active tool is a strategy object (`BaseTool` subclass) held by the canvas
- Switching tools = swapping the strategy; canvas.py never needs to change
- All drawing state lives in the tool object, not the canvas
- `CAMCanvasWithRulers` wraps `CAMCanvas` and forwards all public signals as attributes

### Theming system
- Global singleton: `get_theme()` / `set_theme(theme)` in `core/theme.py`
- `Theme` dataclass with all color/font/size values; `Theme.to_qss()` generates full app QSS
- `.camtheme` files are TOML; loaded via `Theme.load(path)` or `load_builtin(name)`
- 3 bundled themes in `themes/`: `midnight` (default), `slate`, `light`
- Applied on startup and on theme switch: `QApplication.instance().setStyleSheet(get_theme().to_qss())`
- Custom-painted widgets (`RulerWidget`, `ColorPaletteWidget`, canvas `drawForeground`) call `get_theme()` in their paint methods
- Never hardcode colors anywhere - always `get_theme().some_field`
- Theme menu under View → Theme in the main menu bar

### Layer panel - card-based design (IN PROGRESS)
- The right-dock layer panel uses a `QScrollArea` with stacked `LayerCard` widgets
- Each `LayerCard` has a header (always visible): color accent bar + name + operation + eye/lock + chevron
- Chevron expands a collapsible shape list inside the card
- Shape list is collapsed by default - no visual clutter for layers with many shapes
- Clicking a shape in the list selects it on canvas; clicking the card header selects all shapes in that layer
- Double-click card header → `LayerDialog` settings
- Replaces the old `QTreeWidget` approach

### Undo/redo
- Command pattern: every user action that mutates the document creates a `Command` object
- `CommandStack` on the document handles `undo()` / `redo()`
- Ctrl+Z / Ctrl+Y wired in main_window

### Status bar
- Left: transient message (tool hints, import results, action feedback)
- Right permanent widgets (via `addPermanentWidget`): `[N selected] | [X: mm  Y: mm] | [zoom%]`
- `cursor_moved` signal from canvas drives live coordinate display
- `transform_changed` signal drives zoom percentage

## Key conventions
- **PySide6 signals**: use `Signal` and `Slot` from `PySide6.QtCore`
- **No hardcoded colors**: every color comes from `get_theme().field_name`
- **No constants duplication**: shared constants in `core/constants.py`
- **Encapsulation**: `main_window.py` must never access canvas internals - public API only
- **No polyline approximation**: curves stored as curve segments, approximated only at render/export time
- **No explanatory comments**: only "why" comments for non-obvious constraints/workarounds
- **Tool panel styling**: done entirely via global QSS from `theme.to_qss()` - `_apply_styles()` is a no-op

## Implemented features

### Drawing tools
- [x] Select (click + rubber-band, shift-additive)
- [x] Line (Shift = axis-aligned)
- [x] Polyline (Enter to finish, Escape to cancel)
- [x] Rectangle (Shift = square)
- [x] Circle / Ellipse (Shift = circle)
- [x] N-gon with right-click presets (triangle, pentagon, hexagon, heptagon, octagon)

### File I/O
- [x] Import SVG (curves preserved)
- [x] Import DXF (lines, circles, arcs, polylines, splines)

### UI / UX
- [x] Mm-calibrated rulers with dynamic tick spacing (no bundling at low zoom)
- [x] Theming system with 3 bundled themes + Import Theme...
- [x] Canvas crosshair overlay (faint, follows cursor, clears on leave)
- [x] Live coordinate display in status bar (X/Y in mm)
- [x] Live zoom % in status bar
- [x] Selection count in status bar
- [x] Left-border accent indicator on active tool button
- [x] Layer visibility toggle (eye icon per layer card)
- [x] Layer lock toggle (lock icon per layer card)

### Transform / utility
- [x] Mirror X - flips around shape's own vertical center axis
- [x] Mirror Y - flips around shape's own horizontal center axis
- [x] Rotate - dialog with angle + CW/CCW, rotates around bounding box center
- [x] Align - 6 modes (left/right/top/bottom/center_h/center_v); last selected = reference
- [x] All transforms undoable via TransformShapesCommand

### File I/O
- [x] Native project save/load (.dcam format - JSON, version-stamped, ID-preserving)
- [x] Unsaved-changes prompt on close / new / open

## Planned / TODO - roadmap to "ready for firmware work"

Phased so each phase unblocks the next. The `Layer` model already carries `operation`,
`speed`, `rapid_speed`, `pass_count`, `line_spacing`, `line_angle` - nothing consumes
them yet, so most of Phase 2 is wiring up what the data model already anticipated.

### Phase 1 - Foundations CAM needs before it means anything
- [x] Bezier pen tool - click for a corner (straight LineTo), click+drag for a symmetric curve handle (CubicTo, mirrored in/out like Illustrator/CorelDRAW); Enter finishes open, click-on-start closes, Escape cancels
- [x] Node/point editing (drag individual path nodes - anchors + bezier control points; simple move only, no CorelDRAW-style node types/curve conversion)
- [x] Text tool - CorelDRAW-style: click = artistic text (free-growing, manual line breaks),
      click+drag = paragraph text (wraps to box width). Glyphs are real outline curves from
      installed system fonts (`ui/text_engine.py`, Qt font rasterization - the one Qt
      dependency inside otherwise-Qt-free `core/`), built at a large virtual point size and
      scaled down (Qt's outline scaling is non-linear/hinted at small sizes).
      Text stays **live** (`Shape.text: TextData | None`, persisted in .dcam) - reselecting it
      with the Text tool reopens the overlay editor; a `TextToolbar` (font, size, bold/italic,
      align, line/word/letter spacing - letter spacing skips the space character per spec)
      edits it directly, live, whether or not you're mid-edit. **Ctrl+Q converts to curves**
      (discards TextData, freezes the current path) - this reassigned Ctrl+Q away from Exit
      (File → Exit has no shortcut now). Point-edit is disabled on live text shapes (editing
      nodes would be silently overwritten by the next style change) - convert to curves first.
      Known gaps: paragraph box isn't resizable after creation; per-character manual
      placement means no real font kerning.

      Refinements after initial build:
      - Single-click selects a live text shape normally (Select tool); **double-click**
        enters edit mode (`CAMCanvas.mouseDoubleClickEvent` → `SelectTool.handle_double_click`
        → `shape_double_clicked` signal). Canceling/committing that edit session hands
        control back to Select automatically; a manually-entered session (you switched to
        the Text tool yourself) is left alone - see `TextTool._suppress_notify`.
      - The overlay editor live-previews letter/word/line spacing too (QFont letter/word
        spacing + QTextBlockFormat line height), not just font/style/alignment - exact
        spacing (spaces excluded from letter-spacing) is only guaranteed once compiled to
        real glyph curves on commit.
      - Fixed the requested font/size not showing while typing: the app's global QSS
        (`QApplication.setStyleSheet`) was silently overriding `QTextEdit.setFont()`. Fix
        pins font-family/size/weight/style directly in the editor's own per-widget
        stylesheet (same-widget QSS beats the app-wide rule) and additionally applies the
        QFont retroactively via `QTextCharFormat` over the whole document, not just as the
        format for future keystrokes. Cursor width bumped to 2px for visibility.
      - Convert to Curves explodes text into **one shape per subpath/contour**, not per
        character - a glyph is not one shape ("O" has an outer ring + inner hole, "i" has
        a dot + stem); `compile_text_glyphs` splits at every contour boundary.
      - Moving/resizing a live text shape (Select tool) now keeps `TextData` in sync
        (`x_mm`/`y_mm` on move; `font_size_mm`/`box_w_mm`/`box_h_mm`/`x_mm`/`y_mm` on
        resize) - previously only `shape.path` was transformed, so a later re-edit or
        Convert to Curves silently reverted to the original position/size. Non-uniform
        resize (skew) still can't be reproduced exactly on regeneration - font size and
        box width scale independently, approximating rather than exactly reproducing shear.
      - Paragraph text box has a resize handle (bottom-right corner, visible while editing)
        that live re-wraps content and persists through commit - separate from Select-mode
        object resize, which scales the whole compiled shape (letters skew) via the fix above.
- [x] Array / duplicate (X count, Y count, X/Y spacing) - spacing is edge-to-edge gap between the selection's own bounding box, not center offset; whole multi-selection duplicated as one rigid group
- [x] Boolean ops: Union, Subtract, Intersect (via Shapely) - curves flattened only for the op (core/geometry.py), result is a plain polygon Path; single undo step via CompositeCommand
- [x] Work area / bed config (bed size, origin corner, units, safe travel bounds) - Edit → Work Area... dialog; origin_corner stored but only consumed at G-code export (Phase 3), not yet reflected on-screen

Mirror/rotate were also fixed to treat a multi-shape selection as one rigid
group (shared bounding-box center/axis), not each shape mirrored/rotated
around its own individual center.

### Phase 2 - CAM operation engine
- [x] Outline toolpath: walk each shape's Path, respecting `pass_count` - `core/toolpath.py`,
      `generate_outline_strokes`
- [x] Hatch fill toolpath: parallel scan lines at `line_angle`, spaced by `line_spacing`,
      clipped against shape via Shapely; correct even-odd/nonzero hole handling (new
      `geometry.shape_fill_polygon`, chained `symmetric_difference` across rings rather than
      `boolean_ops`' union, which would fill holes solid); optional cross-hatch
      (`Layer.cross_hatch`, exposed in Layer Settings dialog next to Line Angle, engrave-only)
- [x] Per-layer operation dispatch: `operation` field selects outline ("Line Draw") vs
      fill ("Engrave") - `generate_shape_strokes`
- [x] Toolpath ordering/optimization: layer stack order is authoritative (`generate_document_toolpath`
      carries pen position across layers); within a layer, greedy nearest-neighbor ordering
      (`order_strokes`) with stroke-direction reversal to cut pen-up travel

`core/toolpath.py` produces `PenStroke` - ordered, pen-down moves, deliberately not G-code itself
so Phase 3's G-code export and Phase 4's simulation preview can both consume the same structure.
`PenStroke.points` is always flattened (used for nearest-neighbor distance math); `PenStroke.segments`
carries the original `LineTo`/`ArcTo` geometry for outline strokes (only `CubicTo`/`QuadTo` get
flattened, since G-code has no native Bezier) - hatch-fill strokes are segment-less scanlines.
Reversing a stroke during ordering (`_reverse_stroke`) correctly flips an `ArcTo`'s `sweep` flag
rather than just reversing points. No UI surface yet; verified via a throwaway script.

### Phase 3 - G-code generation
Dialect: `G21 G17 G90`/`G91 G0 G1 G2 G3 M3 M5 G28 M2` - no `F`/`S` (no spindle; feed control is the
future machine-control panel's job, Phase 5) and no G54-59/canned cycles/tool change (none of that
applies to a 2-axis plotter with a pen-lift Z). Decided jointly with the user before implementing:
- [x] Curve flattening at export time only (never in the data model), tolerance setting - done in
      Phase 2 already (`PenStroke`), with the fix above so arcs specifically don't get flattened
- [x] G0 (rapid, pen up) / G1 (feed, pen down) / G2-G3 (arcs from ArcTo directly, no flattening) -
      `core/exporters/gcode.py`. Only true circular arcs (rx==ry, no rotation) emit G2/G3 with I/J
      center offsets; rotated/elliptical arcs fall back to sampled G1 chords (matches the existing
      canvas-rendering fallback in `geometry.arc_params`/`_sample_arc`)
- [x] M3/M5 pen commands (bare, no S-word - firmware hard-codes the servo angle internally)
- [x] Header/footer: G21, G17, G90/G91 per `Document.motion_mode`; footer is M5, G28, M2 - no G28
      at job start, only end (park/home as a safe resting state)
- [x] `Document.origin_corner` now actually consumed: default changed to `"top-left"` (matches
      this project's own machine and the doc's native top-left/Y-down mm space - a 1:1 mapping,
      no axis flip). Other corners flip X and/or Y as needed; a **single**-axis flip reverses arc
      handedness (mirroring flips G2↔G3), a double flip (bottom-right) or no flip doesn't (rotation
      preserves handedness) - `gcode._corner_flips` / `swap_arc`
- [x] `Document.motion_mode: "absolute" | "incremental"` (G90/G91), persisted in `.dcam`, toggled
      live from a combo box in `MachinePanel` (below the layer panel) - not deferred to Phase 5,
      built now per explicit request. Incremental mode emits X/Y as deltas from the previous point;
      arc I/J offsets are always relative to the arc's own start regardless of mode (GRBL convention)
- [x] Export G-code to file - File → Export GCODE... (`Ctrl+E`), already-existing stub wired up
- [x] Export SVG - `core/exporters/svg.py`, File → Export SVG...; mm as the SVG user unit directly
      (`viewBox="0 0 work_w work_h"`), so it round-trips through the existing `importers/svg.py`
      unchanged; one `<path>` per Shape grouped by layer (`stroke=layer.color`), invisible layers skipped
- [x] Job time estimate - `toolpath.estimate_job_time_seconds` (pen-down length / `layer.speed` +
      pen-up travel / `layer.rapid_speed`, per layer, mm/min → seconds); "Estimate" button + live
      label in `MachinePanel`, shown before Send Job as the roadmap asked. Purely a planning number -
      G-code itself still carries no feedrate (see above)
- [x] Save/reopen a generated job - the G-code file itself already *is* the persisted job (plain
      text, no reference back to `Document`, per the Phase 5 design note below); added the other
      half, File → Open Job (G-code)..., which reads a previously exported file back into memory
      (`MainWindow._loaded_job_text`) independent of the current document, ready for Phase 5's
      Send Job to stream once serial exists

Not yet revisited: multi-color layers with only one physical pen currently just cut in stack order
with no pause-for-pen-change - out of scope until there's real multi-pen hardware.

**Bug fixed after initial Phase 2 build:** overlapping/nested Engrave shapes (e.g. a letter "O"
drawn as two separate circle Shapes rather than one Shape with a hole subpath) were each hatched
independently, double-filling their shared area instead of the smaller one punching a hole in the
bigger one. `geometry.shape_fill_polygon` (single shape, even-odd across its own rings) is now a
thin wrapper around new `geometry.combined_fill_polygon(shapes, ...)`, which XORs every ring across
*all* shapes in the layer at once. Hatch generation moved from per-shape to whole-layer
(`toolpath.generate_layer_hatch_strokes`, called once from `generate_layer_toolpath` for Engrave
layers instead of per-shape `generate_shape_strokes`) - so nested and partially-overlapping engrave
shapes both cancel out correctly in their shared area, matching normal laser/vinyl-cutter
overlapping-fill behavior.

**Bug fixed after initial Phase 3 build, then corrected again after user feedback:** incremental
mode's first move was computed as a delta from machine `(0, 0)`, making it numerically identical to
absolute mode's first line. First fix tried using the compound bounding-box center as the assumed
start (mirroring `MainWindow._group_bounding_box`'s multi-select convention) - wrong: that still
encodes a computed offset between document-space "home" and the artwork, which doesn't exist for a
relative-mode job. **Corrected design**: in incremental mode there is no absolute reference at all -
the operator is expected to jog/home the pen to the drawing's own start point by hand before running
the job, so the file must not encode *any* travel distance from home to the artwork. Fixed by
seeding `cur` with the toolpath's own first point (`to_machine(strokes[0].points[0])`) rather than
machine `(0,0)` or a computed center - the first move then comes out as an exact zero delta and gets
skipped (same zero-length-travel skip every other move uses), so drawing starts immediately with no
leading `G0`. Absolute mode is unaffected (`cur` still starts at true machine `(0,0)`, since absolute
coordinates need no starting reference at all). Only the single initial reference point changes;
every move after that still tracks normally from wherever the previous one left off.

**Follow-up bug:** the fix above only touched `gcode.py`'s text output - `toolpath.build_simulation_segments`
(Phase 4's simulation window, and `estimate_job_time_seconds` which is built on top of it) still
always started from document `(0,0)` regardless of `motion_mode`, so the Simulation window kept
showing the same phantom travel-from-origin leg in both modes, which is what made the G-code fix
look like it hadn't done anything when checked via Preview. Fixed the same way: in incremental mode,
`build_simulation_segments` now drops the very first segment when it's a pen-up travel leg, matching
the skipped leading `G0` in the G-code. The time estimate is correspondingly shorter in incremental
mode too, since that phantom travel no longer counts toward it.

### Phase 4 - Preview / simulation
- [x] Toolpath simulation in its own dedicated window (not a canvas overlay) - pen-down
      strokes vs pen-up travel visually distinct, animated playback, time estimate - a dry
      run before anything touches real hardware

`core/toolpath.py` gained `SimSegment`/`build_simulation_segments` (framework-free): the same
per-layer walk as `generate_document_toolpath`, but also splitting out each pen-up travel leg and
timing every leg from `layer.speed`/`rapid_speed` - `estimate_job_time_seconds` is now just
`sum(seg.duration_s for seg in build_simulation_segments(...))`, so the Phase 3 time estimate and
the Phase 4 playback clock can't drift apart. `ui/dialogs/simulation_window.py` (`SimulationWindow`,
non-modal - editing can continue while it's open, no live reference back into `Document`) animates
it: pen-down solid in the layer's color, pen-up travel dashed, a moving pen-position dot, play/pause/
stop, a scrubber, and a speed multiplier (auto-picked so real job time compresses to ~20s of
playback by default - these steppers are slow, watching a multi-minute job at 1x isn't useful).
Opened via Machine → Simulate Toolpath... (`Ctrl+M`) or the new button in `MachinePanel`.

**Architecture issue fixed:** `SimulationWindow` used to build its animation via
`toolpath.build_simulation_segments(document)` - straight from `Document`, entirely independent of
`core/exporters/gcode.py`. This caused a real bug: an incremental-mode fix landed in `gcode.py`
(drop the phantom leading travel-from-origin move) but Preview kept showing the old behavior, since
it had its own separate, parallel derivation from `Document` and never touched the G-code path.

Fixed with a new `core/gcode_parser.py`: `parse_gcode(document, text)` parses this project's own
G-code dialect (`G21/G17/G90/G91`, `G0/G1/G2/G3`, `M3/M5`, `G28/M2`, the `; layer: <name>  pass <n>`
comments) back into `SimSegment`s - geometry, motion order, and pen state come **entirely from the
G-code text**. Arcs are re-derived with a center-parameterized sampler (start/end/center/clockwise →
points, via I/J offsets), distinct from `geometry.py`'s SVG-endpoint form used for authoring. Since
G-code deliberately carries no F/S feedrate words, stroke/travel *timing* is still looked up from
`Document.layers[].speed`/`rapid_speed` by matching the layer-name comments - geometry is 100%
file-authoritative, only timing needs the live Document as a side lookup. `SimulationWindow` now
calls `generate_gcode(document)` and parses *that* instead of calling `build_simulation_segments`
directly - this also incidentally proved the incremental-mode leading-G0 skip is structural (the
text itself has no leading `G0` to parse), not a special case that needs replicating in the parser.

`MachinePanel`'s Estimate button still calls `estimate_job_time_seconds` → `build_simulation_segments`
directly (unchanged) - left as a direct-from-Document planning number rather than round-tripping
through generated G-code text on every estimate click, since it's just a number, not a correctness
check like Preview is.

### Phase 5 - Machine communication & control
G-code generation already turns the document into plain text with no reference back to
`Document` - that text is the decoupling point. A background `QThread` streaming worker
(`core/serial_link.py`, `SerialWorker`) sends the already-generated lines; further edits to
the drawing can't affect an in-flight job because the worker never touches `Document` at all.
No workspace snapshot needed.

Built with an eye toward this becoming a real multi-machine tool beyond just this one
bachelor's-project plotter, not just "whatever gets this one board working."

- [x] Serial port connect/disconnect dialog - `ui/dialogs/connect_dialog.py`. Lists OS-reported
      ports only (`serial.tools.list_ports.comports()`), does **not** probe each port for a
      firmware handshake before showing the list (that would reset every attached board just
      from opening the dialog, is slow with several machines attached, and touches hardware you
      haven't chosen yet) - the real machine name only becomes known after picking a port and
      actually connecting
- [x] **Protocol** (jointly designed, documented in full in `core/serial_link.py`'s module
      docstring, which is the source of truth for both sides - summary below). The real
      firmware lives in `../firmware/cam_firmware/` and implements all of it
- [x] Background streaming worker - `SerialWorker(QThread)`, one persistent thread per
      connection (not per-job), so job streaming and future one-off commands (manual jog) share
      the same open port. **Not** the naive "send a line, block for its ack, send the next" -
      that would be both slow and force the machine to sit idle between every single move.
      Instead, GRBL-style character-counting flow control: the firmware reports its serial RX
      ring-buffer size (`buffer=`) once at handshake, and the PC keeps that buffer topped up
      continuously (tracking bytes sent-but-not-yet-acked against that one number) rather than
      waiting for each ack - so firmware can start physically moving on the first couple of
      lines while more are still arriving, and neither side ever needs the whole job resident
      in memory at once. Firmware's separate motion-planner queue is intentionally invisible to
      the PC - if it fills up, firmware just stops draining its RX buffer, which the PC already
      sees as slowing acks against the one number it does track; no second buffer size needs to
      cross the wire for that backpressure to work
- [x] Pause / resume / stop - real-time, out-of-band single bytes (`0x21`/`!`, `0x7E`/`~`,
      `0x18`/Ctrl-X), written immediately, bypassing the line queue entirely, so firmware's
      low-level serial read can act on them the instant they arrive regardless of what's still
      buffered - same idea as GRBL's real-time command bytes. Deliberately not a queued
      G-code-line-shaped message: waiting in line behind already-buffered moves would defeat
      the "ASAP" requirement. Pause only stops the PC from topping up the buffer further
      (firmware's planner drains what it already has and stops - expected feed-hold-style
      deceleration, not an instant motor freeze); Stop does the same plus discards the PC's own
      remaining queued lines and drains stray trailing replies before returning to Ready
- [x] Editing stays fully live during a stream - `SerialWorker` only ever holds the frozen
      G-code text string handed to `send_job()`, verified by constructing `MainWindow` and
      driving `MachinePanel`'s state transitions directly; a real hardware round-trip still
      needs actual firmware to test against
- [x] Machine position readout (2026-10-29/30): `?` polled 5x/s, `<...>` status lines →
      `SerialWorker.status(state, MX, MY, WX, WY, pen_down)`. Work position large, machine
      position small, in the Control tab. Positions always come from the firmware, never
      computed here
- [x] Manual machine control panel: `MachinePanel` has Job and Control tabs.
      - Control: jog cross + arrow keys (up = toward Y = 0), steps 0.1/1/10 mm.
      - Set Zero (`G92 X0 Y0`), Go to Zero (`G90 G0 X0 Y0`), Home (`G28`, centre of the
        pad), Lower/Raise Pen (`M3`/`M5`).
      - Disabled while disconnected or during a job.
      - One-off commands via `SerialWorker.send_command()`.
- [x] Job robustness (2026-10-30):
      - every job starts with a `$JOB` bounds line (`core/job_bounds.py`, arcs
        included), sent alone and acked before streaming;
      - job lines numbered `N<n>`, replies matched by number, resend recovery, `Rx` probe
        for a lost last line;
      - any job error sends `^X`;
      - job end waits for the firmware's `Idle`;
      - Stop (`^X`) and Cancel (`^C`, returns to the job start).
- [x] Connect without resetting the Uno (DTR/RTS off before `open()`, flush, `$I` hello)
      - the position survives reconnects. An unexpected `READY` = the machine restarted:
      the job stops and a warning dialog appears.
- [ ] Disconnect/error mid-job recovery (resume) - **tried 2026-10-30 and reverted**: on
      the machine the carriage moved to a wrong position. Kept off for now; see the
      firmware's CLAUDE.md for what was tried.

**Firmware side:** `../firmware/cam_firmware/` (PlatformIO, Arduino Uno - see that folder's
CLAUDE.md and DESIGN.md). Implemented and verified on hardware:
- motion with look-ahead, backlash compensation, arcs, pen;
- work coordinates, bounds check, line numbers, connect without reset;
- default work area 115 x 140 mm (`core/constants.py`) = the machine's soft limits.

**Protocol quick reference** (full spec in `core/serial_link.py`):
```
Connect:   open with DTR off, "\n" flush, "$I" → "READY name=.. buffer=128 line=96 reset=0|1"
Job:       "$JOB ABS|REL|NONE .." alone → ok | error:limit; then "N<n> <gcode>*<cs>" lines
Replies:   "ok N<n>" | "resend N<k>" | "error:<reason>" (job aborts, PC sends ^X)
Commands:  unnumbered "<gcode>*<cs>" → ok | error:.. ($J, G92, G28, M3/M5, ...)
Status:    '?' → "<Idle|MPos:x,y|WPos:x,y|Pen:up|Rx:n|Free:..|Plan:..>"
Real-time: '!' pause | '~' resume | ^X emergency stop | ^C cancel | '?' status
```

### Deferred / later
- [ ] Live pen position mirrored on canvas from real machine status reports during a stream
- [ ] Pen/material presets (speed + pass_count bundles)
- [ ] Job-complete notification
- [ ] **Performance on large drawings** (user report 2026-10-28): even selecting a shape
      in a large drawing makes the app freeze ("not responding"). Profile before changing
      anything. Suspects: full canvas repaint of every shape on each selection change,
      hit-testing against every point of every path, the layer panel rebuilding its whole
      tree.

## Keyboard shortcuts
| Key | Action |
|-----|--------|
| Space | Select tool |
| L | Line - **align-left instead if 2+ shapes selected** |
| P | Polyline |
| Q | Rectangle |
| O | Circle |
| N | N-gon (hexagon default) |
| T | Triangle (N-gon, 3 sides) - **align-top instead if 2+ shapes selected** |
| C | Align: center on X axis (center_h) |
| E | Align: center on Y axis (center_v) |
| R | Align: right |
| B | Align: bottom |
| Ctrl+A | Select all shapes |
| Ctrl+Z | Undo |
| Ctrl+Y | Redo |
| Ctrl+F | Fit view |
| Ctrl+0 | Reset zoom |
| Delete / Backspace | Remove selected shapes |
| Arrow keys | Nudge selection 0.5mm (Shift = 5mm) |
| Escape | Deselect if something's selected, else cancel current drawing |
| Enter | Finish polyline |

**L/T context-sensitivity**: since CorelDRAW's align shortcuts (L/T) collide with this app's
existing tool shortcuts (Line/Triangle), `MainWindow.keyPressEvent` checks `len(self._selection) >= 2`
first - align wins when 2+ shapes are selected, otherwise the letter switches tools as before.
C/E/R/B had no collision so they're unconditional aligns.

## Hardware notes
- Plotter uses 28BYJ-48 stepper motors (gear-driven X/Y, servo or stepper for Z)
- Firmware in `../firmware/` - custom G-code parser for Arduino (GRBL-like)
- Communication: USB serial, 115200 baud
- G-code dialect: G0, G1, G2, G3, G28, M3/M5 for pen up/down; no F/S words (see Phase 3)
- Machine (0,0) is top-left by default (`Document.origin_corner`), matching this plotter and the
  app's own top-left/Y-down document space - other corners are supported per-document for future machines
