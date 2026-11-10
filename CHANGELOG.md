# Wanderer CAD 2.96.123 — what's new since 2.96.122

123 adds **hatching**, **blocks**, more **dimension** tools, a set of Rhino-style **curve and surface** tools, **sub-object selection**, a **Mac** pass, two new looks (**Ghost** theme, **Target** icons) and a lot of work on **precision, stability and speed in big scenes**.

It is also the release where the add-on moves from beta to **stable**: every tool was run again for geometric precision, Undo/Redo, odd scenes and speed (see "How it was tested").

## New tools

**Hatch**
- **Hatch:** fills closed planar curves with a pattern. Curves inside another one become holes. Ten patterns (Solid, Hatch 1–3, Dash, Grid, Grid 60°, Plus, Squares, Brick), with scale, rotation and spacing.
- **Hatch Region:** click inside an area closed by curves.
- **Hatch Base Point**, **Match Hatch** (copy pattern, scale and rotation from the hatch you clicked last), **Hatch Boundary** (curves on the outline and the holes), **Explode Hatch** (curves; a solid hatch becomes a planar surface).
- A **Hatch panel** in the Wanderer tab.

**Blocks**
- **Block:** select objects, click a base point. Every copy of the block updates together.
- **Insert Block** (with scale and rotation), **Block Edit** / **Close Block Edit** (edit in place, all copies follow), **Select Block Copies**, **Delete Block**, and **Explode** also works on a block.
- A **Blocks panel** in the Wanderer tab.

**Dimensions and annotation**
- **Continue Dimension** (continue or baseline), **Ordinate Dimension**, **Arc Length Dimension**, **Move Dimension Line** (on a dimension already placed).
- **Center Mark** on circles, arcs and ellipses (`D`: small cross or center lines).
- The text of the selected dimension can be edited in the panel; `<>` stands for the measured value (`4x <>`, `<> TYP`).

**Curves**
- **Rebuild Curve** (point count and degree), **Simplify Curve** (within a tolerance), **Change Degree**.
- **Insert Control Point** / **Remove Control Point**.
- **Match Curve** (tangency or position) and **Blend Curve**.

**Surfaces**
- **Network Surface**, **Fillet Surface**, **Chamfer Surface**, **Extend Surface**, **Split at Isocurve**.
- **Untrim** and **Untrim Holes**.

**Extrude Curve** (this tool was called "Extrude Straight") now has **B** both sides, **T** tapered (Tab for the angle) and **P** to a point.

## Selection

- **Ctrl/Cmd + Shift + click** selects a vertex, an edge or a face under the cursor and goes into Edit Mode with it selected, without pressing Tab. **Ctrl/Cmd + click** removes it; **Esc** goes back to Object Mode.
- **Ctrl/Cmd + Shift + drag** (box or lasso) selects the visible vertices of every mesh in the area, or the points of every curve, and puts those objects into Edit Mode together. Blender cannot edit a mesh and a curve together: if the area holds both, the type with the most points in the area is used.
- **Move, Rotate and Scale work on curve points** in Edit Mode: moving one vertex of a polyline no longer moves the whole object.

## Workflow

- **C closes** a polyline or a control point curve, like the Close option in Rhino and AutoCAD.
- **F3** switches object snaps on and off.
- **Ctrl/Cmd + Z during a command** removes the last point (it used to undo the previous operation in Blender while the command was still running).
- **PushPull on curves:** click inside closed curves to make a surface and pull it. Curves drawn on a face cut it first (inner area and outer ring).
- **Offset Edge:** a circle or an arc is offset as a real circle or arc (radius r ± d), not a polyline. A closed outline offset inside a face splits that face, so PushPull can raise the ring into a wall.
- **Explode** now works like Rhino: a solid separates into its smooth surfaces. A cylinder gives 3, a box 6, a sphere stays whole (before, every facet became an object: 34 for a 32-sided cylinder). It also explodes blocks.
- **Quadrant snap** (0°, 90°, 180°, 270° of a circle or arc) is **on by default** and works on circles and arcs drawn outside Wanderer too (Blender, imports, NURBS), with their center.
- **Circles and arcs** are built with one Bézier segment per 45° at most: a circle has 8 control points, like in Rhino. The gap to the true circle is 0.0004 % of the radius (4 µm on 1 m) instead of 0.027 % (0.27 mm).

## Mac

- **⌘ acts as Ctrl** in every Wanderer selection and tool gesture (unless ⌘ is set as the emulated middle button). Help texts read **Ctrl/Cmd**.
- Fixed the navigation gizmo click zone on Retina screens, which covered the upper-right quarter of the viewport.

## Themes and icons

- New theme **Ghost** (black with signal red). It switches the icons to **Target**.
- Icon styles: **Atlas** (one color per tool family), **Blueprint** (white and blue), **Ochre** (white and ochre) and the new **Target** (dimmed grey, only what the tool creates lights up in red). Saved preferences are kept.

## Big scenes and speed

- **Snap budget** (Preferences > Performance and precision, 2 million points by default, 0 = no limit). Lighter objects stay ready; very dense ones (over 8,000 vertices) are read in detail when the cursor slows down over them. In a 10,000-object city scene: first launch of a tool 2.6 s → 0.65 s, snap memory 1.25 GB → 0.47 GB. In the whole-city view, an object smaller than about 48 px on screen is read only after you zoom in.
- **Snaps follow your edits:** snap data is refreshed when geometry actually changes, and cleared on Undo/Redo and when a file is loaded.
- **Edit Mode on dense meshes:** the object being edited keeps all its vertices (up to 120,000) for snapping. Before, only some of them could be snapped.
- **Open curves chained into outlines** (Planar Surface and the tools built on it): 5,000 loose segments take 0.1 s instead of 82 s, with the same result.
- **Curve quality** (Preferences): Draft / Normal / Fine / Very fine = 48 / 96 / 192 / 384 sides per circle when curves become meshes. Normal is the default.
- **Far from the origin:** Blender stores coordinates with about 7 digits. Beyond roughly 500 m the step between two positions exceeds 0.05 mm. Wanderer now says so once per file when you place a point there (Preferences: can be turned off). Working near the origin keeps full precision.

## Fixes

- **Offset Edge on a face** (reported on GitHub): see above, the ring now splits the face.
- **Edge picking** in Fillet Edge, Chamfer Edge and Offset Edge skips edges hidden behind a surface, such as the original curve under a solid.
- **Ctrl/Cmd + Shift + click in Edit Mode** no longer runs Blender's shortest-path selection.
- **Move on a polyline vertex** moved the whole object (see Selection).
- **Quadrant** points of circles and arcs were not found at all (Midpoint, Near or nothing): see Workflow.
- **Dense meshes in Edit Mode**: a click on a vertex could find no snap (see above).
- **Navigation gizmo** on Retina screens (see Mac).

## How it was tested

- **More than 40 regression suites** replay the tools in a headless Blender with the same mouse and keyboard events a user would send, and **measure** the result: coordinates, lengths and volumes against exact values, Undo/Redo states compared field by field for every tool, every tool on empty scenes, wrong selections and extreme typed values (97 tools × 7 scenarios × 6 variants: no exception), and time per mouse move. They are in the `tests/` folder (`python scripts/run_tests.py`).
- Tested on **Blender 5.1 and 5.2**. The declared minimum is 4.2.
- Tried by hand on a Mac for the SubD tools, Offset Edge / PushPull and Ctrl/Cmd + Shift + click, and run on a 10,000-object city scene in Blender on Windows.

## Good to know

- To update: **uninstall the previous version, install the new zip, restart Blender.**
- **Copy** on curve points in Edit Mode, and the move ghost for curve points, are not available yet.
- Ctrl/Cmd + Z inside a command and the Boolean tools were tested with simulated events, not yet by hand on every platform. Reports are welcome.
- Not in yet (Rhino commands people ask for): Pipe, Intersect, Contour/Section, ExtractSrf, Unroll, RebuildSrf, Orient, DXF export.
