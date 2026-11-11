# Wanderer CAD

Precision drawing and modeling tools for Blender, with a workflow that feels familiar if you come from other CAD software: a command line, object snaps, tracking, dimensions, hatches, blocks and layers.

> **Status: stable (2.96.124).** Free and open source (GPL-3.0-or-later). Feedback and bug reports are very welcome.

![The dimensioned drawing on the left, the model and the command line on the right](docs/images/napoleone-00-hero.jpg)

*One Blender session, two viewports: the dimensioned drawing in wireframe on the left, the model on the right with the layers and the command line completing `spl`. The piece is the **Napoleone** coffee table, designed by **Claudio Salocchi for Acerbis**, remodeled with Wanderer CAD only. See [the full workflow](#a-complete-example-two-napoleone-coffee-tables) below.*

![Two Napoleone coffee tables modeled with Wanderer CAD](docs/images/napoleone-01-overview.jpg)

## Features

- **Command line** at the bottom of the viewport: type a command name or an alias, then Enter or Space. Typed values (lengths, angles, coordinates) work with most tools, and **Ctrl/Cmd + V pastes numbers or a whole list of coordinates** into the running command.
- **Drawing**: polylines, control point curves, interpolated curves, rectangles, circles, ellipses, arcs, polygons, points, construction lines. `C` closes a curve, `F3` switches object snaps, **Enter repeats the last typed value**.
- **Curve editing**: join, explode, trim, split, divide, overkill, fillet, chamfer, extend, offset, rebuild, simplify, change degree, insert and remove control points, match and blend curves.
- **Curves from objects**: Intersect, Section, Contour, Duplicate Border, Duplicate Edge, Project.
- **Transform**: move, copy, rotate, scale (reference points, 1D, 2D, to size), mirror, rectangular and polar arrays, align, stretch, **Orient**. Move, rotate and scale also work on curve points in Edit Mode.
- **Gumball**: move, rotate and scale handles on the selection, plus an **extrusion sphere** and a **cut handle**: a closed flat curve cuts the solids on its way, or adds to them with Ctrl/Cmd.
- **Surfaces and solids**: planar, edge and network surfaces, patch, extrude (straight, along a curve, both sides, tapered, to a point), revolve, loft, sweep, **Pipe**, booleans (each result is checked: closed solid, coherent volume), **PushPull on flat and curved faces**, fillet and chamfer on edges and between surfaces, extend, split at isocurve, untrim, offset surface, **Extract Surface**, **Merge All Faces**, **Unroll Surface**, **Rebuild Surface**. Explode separates a solid into its smooth surfaces.
- **SubD**: boxes, spheres, cylinders, cones, tori and planes, loft, sweep, revolve and MultiPipe over a quad control cage, with cage editing tools (crease, insert edge, bevel, inset, bridge...) and live symmetry.
- **Precision**: object snaps (End, Near, Point, Mid, Cen, Int, Perp, Tan, Quad, Knot, Vertex), smart tracking (X / Y / Z lines and **the extension of the segment that ends at a tracked point**), polar tracking. A snap budget keeps very large scenes responsive.
- **Annotation**: linear, continued / baseline, ordinate, radius, angle and arc length dimensions, center marks, text, area and length measurement, **Make 2D** drawings from a 3D model.
- **Hatches**: ten patterns with scale, rotation and spacing, hatch by picking a point, match, base point, boundary, explode.
- **Blocks**: make, insert, edit in place (every copy follows), explode, select copies.
- **Layers** built on Blender collections: colors, sublayers, visibility and lock, saved layer states.
- **Selection**: select, box, circle, lasso, selection filters, and `Ctrl/Cmd + Shift` sub-object selection (vertex, edge, face, or an area of points) straight into Edit Mode.
- **Groups**, named view tabs and navigation presets.
- **Mac**: `Cmd` acts as `Ctrl` in every gesture.
- **Look**: themes Blueprint, Vellum and Ghost; icon styles Atlas, Blueprint, Ochre and Target.

## A complete example: two Napoleone coffee tables

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

## The interface

Layers are Blender collections, with a color, visibility, lock and saved states. Selection filters decide what a click can pick. Everything else lives in the add-on preferences: language, icon style, Gumball behaviour, snap budget, curve quality.

| | |
|---|---|
| ![Layers panel](docs/images/ui-layers.jpg) | ![Selection filters panel](docs/images/ui-selection-filters.jpg) |
| **Layers.** One layer per material here, each with its color; sublayers, layer states, a search field, and per-layer visibility, lock, viewport and render switches. | **Selection filters.** What a click is allowed to pick. Shift on the bottom button turns everything off, a click on one line keeps only that type. |

The mouse navigation of the viewport can follow the program you come from — Blender, Rhino, SolidWorks, AutoCAD / Revit / Inventor / Fusion, Maya / Cinema 4D / Houdini, 3DS Max — or any combination of buttons you set yourself.

![Navigation style](docs/images/ui-navigation-style.jpg)

Everything else is in the add-on preferences:

![Add-on preferences](docs/images/ui-preferences.jpg)

Three themes ship with the add-on and install in one click from those preferences. Here they are with the two tables in wireframe:

![The three built-in themes](docs/images/napoleone-16-themes.jpg)

## Installation

Requires **Blender 4.2 or newer**. Developed and tested on Blender 5.1 and 5.2.

1. Download the latest `wanderer-x.y.z.zip` from the [Releases](../../releases) page.
2. In Blender: *Edit > Preferences > Get Extensions*, open the drop-down menu at the top right and choose **Install from Disk...**, then select the zip.
3. Enable **Wanderer CAD**. If you have an older version installed, remove it first and restart Blender.

## What changed

See [CHANGELOG.md](CHANGELOG.md).

## Source layout

Since 2.96.124 the add-on is a package of 42 modules in `wanderer_cad/` (one per family of tools: `tools_draw`, `transform`, `booleans`, `gumball`, `pushpull`, `rhino_commands`, `layers`...). `__init__.py` only loads them.

## Build the zip yourself

```
python scripts/build_zip.py
```

The zip is written to `dist/`.

## Tests

The regression suites replay the tools in a headless Blender with the same mouse and keyboard events a user would send, and measure the result (coordinates, lengths, volumes, Undo / Redo states, timings).

```
pip install bpy numpy
python scripts/run_tests.py -j 4
```

See [tests/README.md](tests/README.md) for what each suite measures.

## Feedback

Please open an [issue](../../issues) with your Blender version, what you did and what you expected. Screenshots help.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
