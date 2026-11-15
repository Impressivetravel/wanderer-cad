# Wanderer CAD

Precision drawing and modeling tools for Blender, with a workflow that feels familiar if you come from other CAD software: a command line, object snaps, tracking, dimensions, hatches, blocks and layers.

> **Status: stable (2.96.127).** Free and open source (GPL-3.0-or-later). Feedback and bug reports are very welcome.

![Wanderer CAD: precision drawing and modeling, without leaving the Blender viewport](docs/images/slides/01-wanderer-cad.jpg)

## A quick tour

| | |
|---|---|
| ![A command line, like CAD software](docs/images/slides/02-command-line.jpg) | ![A Gumball, as in Rhino](docs/images/slides/03-gumball.jpg) |
| ![Object snaps and SmartTrack](docs/images/slides/04-snaps-smarttrack.jpg) | ![Control points you can see](docs/images/slides/05-curves.jpg) |
| ![Extrude, with History](docs/images/slides/06-extrude-history.jpg) | ![Dimensions](docs/images/slides/07-dimensions.jpg) |
| ![Layouts, from the model to a sheet](docs/images/slides/08-layouts.jpg) | ![Layers and selection filters](docs/images/slides/09-layers-filters.jpg) |
| ![Every tool in the sidebar](docs/images/slides/10-tools-panel.jpg) | ![Your workflow in one click](docs/images/slides/11-presets-preferences.jpg) |
| ![Six themes, one click](docs/images/slides/12-themes.jpg) | ![Help where you need it](docs/images/slides/13-tooltips-display-as.jpg) |

## Features

- **Command line** at the bottom of the viewport: type a command name or an alias, then Enter or Space. Typed values (lengths, angles, coordinates) work with most tools, and **Ctrl/Cmd + V pastes numbers or a whole list of coordinates** into the running command. You can add **your own aliases** (`aliasedit`, as in AutoCAD and Rhino), and the interface speaks **eleven languages**, each with the command aliases that language uses in AutoCAD and Rhino.
- **Drawing**: polylines, control point curves, interpolated curves, rectangles, circles, ellipses, arcs, polygons, points, construction lines. `C` closes a curve, `F3` switches object snaps, **Enter repeats the last typed value**.
- **Curve editing**: join, explode, trim, split, divide, overkill, fillet, chamfer, extend, offset, rebuild, simplify, change degree, insert and remove control points, match and blend curves.
- **Curves from objects**: Intersect, Section, Contour, Duplicate Border, Duplicate Edge, Project.
- **Transform**: move, copy, rotate, scale (reference points, 1D, 2D, to size), mirror, rectangular and polar arrays, align, stretch, **Orient**. Move, rotate and scale also work on curve points in Edit Mode.
- **Gumball**: move, rotate and scale handles on the selection, plus an **extrusion sphere** and a **cut handle**: a closed flat curve cuts the solids on its way, or adds to them with Ctrl/Cmd.
- **Surfaces and solids**: planar, edge and network surfaces, patch, extrude (straight, along a curve, both sides, tapered, to a point), revolve, loft, sweep, **Pipe**, booleans (each result is checked: closed solid, coherent volume), **PushPull on flat and curved faces**, fillet and chamfer on edges and between surfaces, extend, split at isocurve, untrim, offset surface, **Extract Surface**, **Merge All Faces**, **Unroll Surface**, **Rebuild Surface**. Explode separates a solid into its smooth surfaces.
- **History** (option `H`, off by default) keeps the result editable: Extrude, Revolve, Thicken, Pipe and the booleans create a Blender modifier instead of a fixed mesh, so the height, the angle, the thickness or the radius can still be changed in the Modifiers tab, and a boolean follows its operand when you move it.
- **SubD**: boxes, spheres, cylinders, cones, tori and planes, loft, sweep, revolve and MultiPipe over a quad control cage, with cage editing tools (crease, insert edge, bevel, inset, bridge...) and live symmetry.
- **Precision**: object snaps (End, Near, Point, Mid, Cen, Int, Perp, Tan, Quad, Knot, Vertex) from the status bar or the OSnap menu, **one-shot snaps** (hold Shift over the snap boxes and click the ones you want for the next point), **Grid Snap** (`F9`, 10 cm by default), Ortho, axis locks (`X` / `Y` / `Z`), smart tracking (X / Y / Z lines and **the extension of the segment that ends at a tracked point**), polar tracking. A snap budget keeps very large scenes responsive.
- **Annotation**: linear, continued / baseline, ordinate, radius, angle and arc length dimensions, center marks, text, area and length measurement, **Make 2D** drawings from a 3D model.
- **Layouts**: paper sheets (A5 to A0, Letter, ANSI, Arch, custom) with **viewports on the model at scale** (hidden lines removed or dashed), with grips and a double-click to work inside them as in AutoCAD, a title block, dimensions on the sheet that give the length of the model and follow their viewport, and vector **PDF / SVG / DXF / DWG** export.
- **DXF and DWG**: import a drawing with its layers, colors, blocks and text; export the model (lines, polylines, true arcs and circles, 3D faces, text) or the sheets. DXF needs nothing; DWG goes through the free ODA File Converter installed on your computer.
- **Hatches**: ten patterns with scale, rotation and spacing, hatch by picking a point, match, base point, boundary, explode.
- **Blocks**: make, insert, edit in place (every copy follows), explode, select copies.
- **Layers** built on Blender collections: colors, sublayers, visibility and lock, saved layer states.
- **Selection**: select, box, circle, lasso, selection filters, and `Ctrl/Cmd + Shift` sub-object selection (vertex, edge, face, or an area of points) straight into Edit Mode.
- **Groups**, named view tabs and navigation presets.
- **Mac**: `Cmd` acts as `Ctrl` in every gesture.
- **Look**: six themes — Blueprint, Carbon and Midnight (dark), Graphite, Vellum and Ivory (light); icon styles Atlas, Blueprint, Ochre and Target. A **Presets** row sets the whole workflow to Rhino, AutoCAD or Blender in one click.

## A complete example: two Napoleone coffee tables

![The dimensioned drawing on the left, the model and the command line on the right](docs/images/napoleone-00-hero.jpg)

*One Blender session, two viewports: the dimensioned drawing in wireframe on the left, the model on the right with the layers and the command line completing `spl`. The piece is the **Napoleone** coffee table, designed by **Claudio Salocchi for Acerbis**, remodeled with Wanderer CAD only. *

![Two Napoleone coffee tables modeled with Wanderer CAD](docs/images/napoleone-01-overview.jpg)

The pictures below are screenshots taken while modeling two **Napoleone** coffee tables — the model designed by **Claudio Salocchi** for **Acerbis** — in two sizes: a 72 x 72 cm one and a 144 x 72 cm one, both 355.5 mm high. The construction is a folded steel "V" bridge resting on two lacquered sides, base plates and a glass top. Every part was made with Wanderer commands, in millimetres, from the reference models.

A screen recording of the session is in [docs/demos/napoleone-workflow.mp4](docs/demos/napoleone-workflow.mp4).

| | |
|---|---|
| ![Polyline with typed coordinates](docs/images/napoleone-03-polyline-coordinates.jpg) **1. Polyline with coordinates.** The profile of the bridge is drawn in the Right view: `#0,360.16`, `#36.84,360.16`, `#360,37`... | ![Offset](docs/images/napoleone-04-offset.jpg) **2. Fillet Curve, then Offset.** The corners get a 6 mm radius, then the curve is offset by the sheet thickness (5 mm). |
| ![Object snaps](docs/images/napoleone-05-osnap.jpg) **3. Object snaps.** The two ends are closed with short lines snapped to End, then everything is joined into one closed curve. | ![Extrude Curve](docs/images/napoleone-06-extrude-curve.jpg) **4. Extrude Curve.** The closed profile becomes a 720 mm long solid. |
| ![Box with typed dimensions](docs/images/napoleone-07-box.jpg) **5. Box.** Two corners and a height, typed. | ![Gumball cut](docs/images/napoleone-08-gumball-cut.jpg) **6. Gumball cut.** A closed curve drawn on the face is dragged through the solid with the cut handle of the Gumball. |
| ![Fillet Edge](docs/images/napoleone-09-fillet-edge.jpg) **7. Fillet Edge.** Box-select the edges, type the radius. | ![Holes with the Gumball](docs/images/napoleone-10-gumball-holes.jpg) **8. Copy, Mirror, cut.** Four circles, copied and mirrored, cut the holes of the base plate in one go. |
| ![Stretch](docs/images/napoleone-11-stretch.jpg) **9. Stretch.** The second table is a copy stretched by 720 mm with a crossing window. | ![Dimensions](docs/images/napoleone-12-dimensions.jpg) **10. Dimensions and layers.** One layer per material, dimensions on their own layer. |

![Gumball cut, recorded](docs/demos/gumball-cut.gif)

### The drawing

The same model in wireframe, dimensioned. The height is measured from the underside of the base plates, not from the floor: the table stands 19.66 mm above the origin, exactly like the reference model.

![Wireframe with dimensions](docs/images/napoleone-14-wireframe-dimensions.jpg)

The angular dimension on the fold reads **90°** — the two halves of the "V" are an exact right angle, and the sheet measures 5 mm everywhere.

![Angular dimension on the fold of the V](docs/images/napoleone-15-angle-dimension.jpg)

The finished models were measured against the reference: same overall sizes (720 x 720 x 355.5 mm and 1440 x 720 x 355.5 mm), and every part is a closed solid.

![Modeled tables in front of the reference models](docs/images/napoleone-13-reference.jpg)

*The reference models (grey) are the **Napoleone** coffee table, designed by **Claudio Salocchi** and produced by **Acerbis**. The design, its name and the Acerbis name belong to their owners; they are used here as a modeling exercise only, and this project is not affiliated with the designer or the manufacturer.*

## Layouts: from the model to a sheet

A layout is a tab next to the view tabs. It is a paper sheet in millimetres: viewports show the model in a view and at a scale, dimensions placed on a viewport give the real length of the model, and the sheet is exported as a vector PDF at the exact paper size.

![A layout with four viewports, dimensions and the Layout panel](docs/images/layout-01-sheet.png)

*`layout` creates the sheet (here A3 with four viewports), `mv` draws another one, `dim` snaps to the linework of a viewport: the table reads 144.00 x 72.00, the wall 250.00. Changing the scale of a viewport or panning it takes its dimensions along.*

![The PDF exported from that layout](docs/images/layout-02-pdf.png)

*`pdf` writes the sheet: visible edges 0.35 mm, hidden edges dashed 0.18 mm, title block filled from the panel.*

## The interface

Layers are Blender collections, with a color, visibility, lock and saved states. Selection filters decide what a click can pick. Everything else lives in the add-on preferences: language, icon style, Gumball behaviour, snap budget, curve quality.

| | |
|---|---|
| ![Layers panel](docs/images/ui-layers.jpg) | ![Selection filters panel](docs/images/ui-selection-filters.jpg) |
| **Layers.** One layer per material here, each with its color; sublayers, layer states, a search field, and per-layer visibility, lock, viewport and render switches. | **Selection filters.** What a click is allowed to pick. Shift on the bottom button turns everything off, a click on one line keeps only that type. |

The mouse navigation of the viewport can follow the program you come from — Blender, Rhino, SolidWorks, AutoCAD / Revit / Inventor / Fusion, Maya / Cinema 4D / Houdini, 3DS Max — or any combination of buttons you set yourself.

![Navigation style](docs/images/ui-navigation-style.jpg)

Everything else is in the add-on preferences, in ten sections: Presets, Appearance, Navigation and mouse, Command line and aliases, Drawing, Gumball, Toolbar, Performance, DXF / DWG and Shortcuts.

![Add-on preferences](docs/images/wassily-preferences.jpg)

*The Presets row sets the workflow (Rhino, AutoCAD, Blender) in one click; the theme has its own row just below. Every option a preset sets stays editable in the sections underneath.*

The right-click menu gained a **Display As** submenu (Bounds, Wire, Solid, Textured) for the selected objects, with a dot on the current choice.

![Display As in the object context menu](docs/images/wassily-display-as.jpg)

Six themes ship with the add-on and install in one click from the preferences: **Blueprint**, **Carbon** and **Midnight** for the dark ones — the screenshots above are in Blueprint — and three light ones, here on the same model:

![Graphite, Vellum and Ivory](docs/images/wassily-themes-light.jpg)

*Left to right: **Graphite**, which follows the Rhino interface, **Vellum** and **Ivory**.*

## Installation

Requires **Blender 4.2 or newer**. Developed and tested on Blender 5.1 and 5.2.

1. Download the latest `wanderer-x.y.z.zip` from the [Releases](../../releases) page.
2. In Blender: *Edit > Preferences > Get Extensions*, open the drop-down menu at the top right and choose **Install from Disk...**, then select the zip.
3. Enable **Wanderer CAD**. If you have an older version installed, remove it first and restart Blender.

## What changed

See [CHANGELOG.md](CHANGELOG.md).

## Source layout

The add-on is a package of 44 modules in `wanderer_cad/` (one per family of tools: `tools_draw`, `transform`, `booleans`, `gumball`, `pushpull`, `rhino_commands`, `layers`, `layout`...). `__init__.py` only loads them.

## Build the zip yourself

```
python scripts/build_zip.py
```

The zip is written to `dist/`.

## Feedback

Please open an [issue](../../issues) with your Blender version, what you did and what you expected. Screenshots help.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
