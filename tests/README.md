# Wanderer CAD — regression suites

These suites replay the tools without opening Blender. They use Blender's Python module (`bpy`), send each tool the
same mouse and keyboard events a user would, and measure what comes out: coordinates, lengths, volumes, undo / redo
states and timings. Nothing is assumed from reading the code.

## Run

```
pip install bpy numpy
python scripts/run_tests.py            # everything (about 4 minutes; 2 minutes with -j 4)
python scripts/run_tests.py prec       # only the suites whose name contains "prec"
python scripts/run_tests.py -j 4 -v    # 4 at a time, full output
python scripts/run_tests.py --bench    # adds the per-mouse-move timings
```

A single suite can be run directly: `python tests/t_prec1.py`.
The add-on tested is `wanderer_cad/__init__.py`; set `WANDERER_SRC=/path/to/file.py` to test another copy.

## What each group checks

| Suites | What is measured |
|---|---|
| `t_prec1` … `t_prec6`, `t_edgecirc`, `t_quality` | Geometric precision: drawn shapes, typed values, transforms, offsets, booleans, extrusions, circles and arcs against their exact values |
| `t_undo`, `t_undo2`, `t_undo3`, `t_undo4`, `t_undo4b`, `t_undo_mid` | Undo / Redo: the scene is compared field by field before, after undo and after redo, for every tool and command line action; Ctrl+Z and deleted objects in the middle of a command |
| `t_stress`, `t_stress2`, `t_stressvar` | Stability: every tool on empty scenes, wrong selections, Escape at each step, extreme typed values; then again with other units, a transformed view, perspective, a custom CPlane and a heavy scene |
| `t_perf`, `t_budget`, `t_rt` | Performance: snap data reuse, snap budget and on-demand detail in very large scenes, time per mouse move |
| `t_alltools`, `t_reginherit`, `t_wf`, `t_esc`, `t_dimesc`, `t_coord`, `t_osnap`, `t_tan`, `t_tan2`, `t_quadnew`, `t_arcr`, `t_circ`, `t_autocp`, `t_far` | Workflow: every tool starts and finishes, right-click = Enter, C to close, F3, coordinates entry, object snaps, tangents, Auto CPlane, far-from-origin notice |
| `t_hatch`, `t_hatchreg`, `t_srf`, `t_crv`, `t_blocks`, `t_dimadv`, `t_untrim`, `t_extopts`, `t_extcap`, `t_ppimprint` | Features: hatches, surfaces, curve editing, blocks, dimensions, untrim, extrude options |

## Writing a suite

`harness.py` loads the add-on as `m`, builds a fake top view (1000 x 1000 px, 10 px per unit) and gives:
`make(cls)` (a tool instance), `ev(type, value, x, y)` (an event), `scr(x, y)` (world to pixels), `ctx`, `region`, `rv3d`.
`prec_lib.py` adds `run(tool, [C(x, y), M(x, y), T(values), 'RET'])` to drive a tool with clicks, moves and typed
values, and `undo_lib.py` adds `snapshot()` / `diff()` to compare two states of the scene.

Do not name your own globals `S`, `W` or `H`: the harness uses them. Typed values must be sent as keystrokes (`T(...)`),
and clicks within 12 px of an object snap to it.
