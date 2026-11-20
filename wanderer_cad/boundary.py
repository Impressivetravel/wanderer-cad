"""Wanderer CAD : Boundary (contour d'une zone par un point cliqué dedans, comme BOUNDARY d'AutoCAD) et outils communs
aux commandes « on clique dans une zone fermée » (Area par point, Hatch Region)."""

import bpy
import numpy as np
from bpy_extras.view3d_utils import region_2d_to_origin_3d, region_2d_to_vector_3d
from mathutils import Vector

from .core import build_polyline, local_view_token, obj_visible, plane_axes
from .snapping import _GEOM
from .drawing import _HOVER, find_window_region, region_rv3d
from .base import DessinBase
from .regions import RegionFinder, ring_area, ring_length

_FINDER = {"key": None, "finder": None}


def region_objects(context, space=None):
    """Courbes et contours (maillages sans face) visibles : ce qui peut fermer une zone."""
    out = []
    for o in context.visible_objects:
        try:
            if not (o.type == 'CURVE' or (o.type == 'MESH' and not len(o.data.polygons))):
                continue
        except (AttributeError, ReferenceError):
            continue
        if space is not None and not obj_visible(o, space):
            continue
        out.append(o)
    return out


def region_finder_reset():
    """À appeler au lancement d'une commande et après avoir créé des objets : les zones seront relues."""
    _FINDER["key"] = _FINDER["finder"] = None


def region_finder(context, axis, space=None):
    """Zones fermées des courbes visibles dans les plans parallèles à la vue (gardées tant que rien ne bouge)."""
    u, v, n = plane_axes(axis)
    try:
        # (clé légère : pas de parcours des objets à chaque mouvement de souris)
        key = (_HOVER["version"], _GEOM["epoch"], len(bpy.data.objects), tuple(round(x, 6) for x in n),
               context.scene.as_pointer(), local_view_token(space))
    except (AttributeError, ReferenceError):
        key = None
    if key is not None and _FINDER["key"] == key and _FINDER["finder"] is not None:
        return _FINDER["finder"]
    from .hatch import _hatch_paths_of
    try:
        paths = _hatch_paths_of(context, region_objects(context, space))
    except (ValueError, RuntimeError, ReferenceError):
        paths = []
    f = RegionFinder(paths, tuple(u), tuple(v), tuple(n))
    _FINDER["key"], _FINDER["finder"] = key, f
    return f


def region_under_mouse(op, context, mouse, islands=True):
    """Zone fermée sous la souris pour une commande (DessinBase) : (c, u, v, n, anneaux 2D, distance) ou None."""
    if mouse is None or op.region is None:
        return None
    try:
        rv3d = region_rv3d(op.region, op.area)
        o = region_2d_to_origin_3d(op.region, rv3d, mouse)
        d = region_2d_to_vector_3d(op.region, rv3d, mouse)
        space = op.area.spaces.active
    except (AttributeError, ReferenceError, TypeError):
        return None
    # Le relevé des zones est gardé pour toute la commande : ce qu'elle crée (contours, hachures) suit des traits déjà là
    # et ne change pas les zones. Relu seulement si la vue change de plan (ou de vue locale).
    try:
        lk = (tuple(round(x, 6) for x in plane_axes(op.axis)[2]), local_view_token(space))
    except (AttributeError, ReferenceError, TypeError):
        lk = None
    held = getattr(op, "_rf", None)
    if held is None or held[0] != lk:
        region_finder_reset()
        held = (lk, region_finder(context, op.axis, space))
        try:
            op._rf = held
        except AttributeError:
            pass
    return held[1].at_ray(np.array(o), np.array(d), islands=islands)


def region_world_rings(rg):
    c, u, v, _n, rings, _t = rg
    c, u, v = np.asarray(c), np.asarray(u), np.asarray(v)
    return [[Vector(c + p[0] * u + p[1] * v) for p in R] for R in rings]


def region_hilite(rg, cap=4000):
    segs = []
    for P in region_world_rings(rg):
        segs.extend((P[i], P[(i + 1) % len(P)]) for i in range(len(P)))
    return segs[:cap]


def region_measure(rg):
    """(aire, périmètre du contour, périmètre total, centre) d'une zone : les îlots sont déduits de l'aire."""
    rings = rg[4]
    area = abs(ring_area(rings[0])) - sum(abs(ring_area(R)) for R in rings[1:])
    outer = ring_length(rings[0])
    total = outer + sum(ring_length(R) for R in rings[1:])
    R0 = np.asarray(rings[0])
    c, u, v = np.asarray(rg[0]), np.asarray(rg[1]), np.asarray(rg[2])
    m = R0.mean(axis=0)
    return area, outer, total, Vector(c + m[0] * u + m[1] * v)


def region_to_curves(context, rg, name="Boundary"):
    """Une polyligne fermée par anneau (contour, puis îlots), dans le calque courant."""
    made = []
    for P in region_world_rings(rg):
        if len(P) >= 3:
            made.append(build_polyline(context, name, P, True))
    return made


class DESSIN_OT_boundary(DessinBase):
    bl_idname = "dessin.boundary"
    bl_label = "Boundary"
    bl_description = ("Like BOUNDARY: click inside an area closed by curves or lines, even lines that only cross each "
                      "other, to create a closed polyline around it (and around the islands inside it). The area under the "
                      "cursor lights up. D: with or without the islands. Stays active to pick several areas")

    TITLE = "Boundary"
    EDIT_OK = False
    NEEDED = 1
    HAS_MODE = True
    MODES = ("With islands", "Outer only")
    mode = 0
    PLANAR = False
    LOCK_OK = False

    def lock_allowed(self):
        return False

    def prompt(self):
        return f"click inside a closed area   [D: {self.MODES[(self.mode + 1) % len(self.MODES)]}]"

    def invoke(self, context, event):
        self._mouse = None
        self.hilite = []
        self._made = 0
        self._rf = None
        return super().invoke(context, event)

    def update_cursor(self, context, event):
        region = find_window_region(self.area, event.mouse_x, event.mouse_y)
        self._mouse = (event.mouse_x - region.x, event.mouse_y - region.y) if region is not None else None
        super().update_cursor(context, event)

    def find_region(self):
        return region_under_mouse(self, bpy.context, self._mouse, islands=self.mode == 0)

    def compute(self):
        self.hilite = []
        rg = self.find_region()
        if rg is None:
            return [], [], "No closed area under the cursor", None
        self.hilite = region_hilite(rg)
        n = len(rg[4]) if self.mode == 0 else 1
        return [], [], f"Boundary: {n} closed polyline{'s' if n > 1 else ''} ({self.MODES[self.mode]})", None

    def click(self, context):
        rg = self.find_region()
        if rg is None:
            self.report({'INFO'}, "Click inside an area closed by curves")
            return
        if self.mode == 1:
            rg = rg[:4] + ([rg[4][0]],) + rg[5:]
        made = region_to_curves(context, rg)
        self._made += len(made)
        if made:
            try:
                bpy.ops.ed.undo_push(message="Boundary")
            except (RuntimeError, AttributeError):
                pass
        self.report({'INFO'}, f"Boundary: {len(made)} closed polyline{'s' if len(made) > 1 else ''} created")
        self.reset_state()
        self.refresh(context)

    def exit(self, context):
        if getattr(self, "_made", 0):
            self.finished = True          # des contours ont été créés : la commande se termine « faite »
        return super().exit(context)

    def cleanup(self, context):
        self.hilite = []
        super().cleanup(context)


def _late_imports():
    pass
