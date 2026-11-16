"""Wanderer CAD : Hachures."""

import bmesh
import bpy
import json
import math
import numpy as np
from bpy_extras.view3d_utils import region_2d_to_origin_3d, region_2d_to_vector_3d
from mathutils import Matrix, Vector, geometry

from .snapping import _geom_ver
from .drawing import find_window_region, project_px, px_scale, region_rv3d
from .base import DessinBase
from .selection import ray_cast_opaque
from .settings import HATCH_PATTERNS, HATCH_PATTERN_ITEMS, _HATCH_EDIT
from .trim import wire_paths
from .surfaces import (
    _ProfileOp, _plane_of, chain_open_paths, delete_objects, deselect_all_objects, grid_mesh,
    mesh_object_from_arrays, object_paths, ordered_selection,
)


# ---- Hachures : moteur ----

HATCH_MAX_LINES = 6000          # lignes d'une famille de motif
HATCH_MAX_SEGS = 250000         # segments d'une hachure


class HatchTooDense(Exception):
    """Motif trop serré pour la zone : il faut une échelle plus grande."""


def is_hatch(obj):
    try:
        return obj is not None and obj.type == 'MESH' and "dessin_hatch" in obj.keys()
    except ReferenceError:
        return False


def _pip_np(pt, poly):
    """Point dans polygone 2D (pair / impair), vectorisé."""
    x, y = float(pt[0]), float(pt[1])
    P = np.asarray(poly, dtype=np.float64)
    Q = np.roll(P, -1, axis=0)
    yi, yj = P[:, 1], Q[:, 1]
    cross = (yi > y) != (yj > y)
    if not cross.any():
        return False
    xi, xj = P[cross, 0], Q[cross, 0]
    yi, yj = yi[cross], yj[cross]
    xs = xi + (y - yi) * (xj - xi) / (yj - yi)
    return bool(np.count_nonzero(x < xs) % 2)


def _poly_area2(P):
    P = np.asarray(P, dtype=np.float64)
    x, y = P[:, 0], P[:, 1]
    return 0.5 * float(np.abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def hatch_loop_groups(paths):
    """Contours fermés plans regroupés par plan : [(c, u, v, n, [contour 2D], [aire])] et nb de contours ignorés.
    Les courbes ouvertes qui se touchent par leurs extrémités sont raccordées (comme PlanarSrf)."""
    paths, skipped = chain_open_paths(paths)
    loops = []
    for P, closed in paths:
        P = np.asarray(P, dtype=np.float64)
        if not closed or len(P) < 3:
            skipped += 1
            continue
        pl = _plane_of(P)
        scale = float(np.ptp(P, axis=0).max())
        if pl is None or pl[2] > max(1e-3 * scale, 1e-7):
            skipped += 1
            continue
        loops.append((P, pl))
    loops.sort(key=lambda t: -t[1][3])
    groups = []
    while loops:
        P0, (c, n, _d, _a) = loops[0]
        scale = float(np.ptp(P0, axis=0).max())
        grp, rest = [], []
        for item in loops:
            P, (_c2, n2, _d2, _a2) = item
            if abs(float(n.dot(n2))) > 0.9999 and float(np.abs((P - c) @ n).max()) <= max(1e-3 * scale, 1e-7):
                grp.append(item)
            else:
                rest.append(item)
        loops = rest
        u = P0[1] - P0[0]
        u = u - n * float(u.dot(n))
        u = u / (np.linalg.norm(u) or 1.0)
        # axes du plan alignés sur le monde quand c'est possible (le motif ne tourne pas avec le premier segment)
        for ax in (np.array((1.0, 0.0, 0.0)), np.array((0.0, 1.0, 0.0))):
            e = ax - n * float(ax @ n)
            if np.linalg.norm(e) > 0.3:
                u = e / np.linalg.norm(e)
                break
        v = np.cross(n, u)
        if float(n[2]) < -0.9:
            n, v = -n, -v            # plan vu de dessus : repère direct (X, Y, Z)
        flats = [np.stack([(P - c) @ u, (P - c) @ v], axis=1) for P, _pl in grp]
        areas = [_poly_area2(F) for F in flats]
        groups.append((c, u, v, n, flats, areas))
    return groups, skipped


def hatch_regions(groups):
    """Régions (contour extérieur + trous, par imbrication paire / impaire) : [(c, u, v, n, [anneaux 2D])]."""
    out = []
    for c, u, v, n, flats, areas in groups:
        m = len(flats)
        depth, parent = [], []
        for i in range(m):
            cont = [j for j in range(m) if j != i and areas[j] > areas[i] and _pip_np(flats[i][0], flats[j])]
            depth.append(len(cont))
            parent.append(min(cont, key=lambda j: areas[j]) if cont else None)
        for i in range(m):
            if depth[i] % 2:
                continue
            holes = [j for j in range(m) if depth[j] == depth[i] + 1 and parent[j] == i]
            out.append((c, u, v, n, [flats[i]] + [flats[j] for j in holes]))
    return out


def hatch_region_at(groups, o, d):
    """Région fermée qui contient le point visé par le rayon (o, d) : (c, u, v, n, anneaux 2D, distance) ou None.
    La plus petite boucle qui contient le point est le contour ; les boucles directement à l'intérieur sont les trous."""
    best = None
    o = np.asarray(o, dtype=np.float64)
    d = np.asarray(d, dtype=np.float64)
    for c, u, v, n, flats, areas in groups:
        dn = float(d @ n)
        if abs(dn) < 1e-6:
            continue
        t = float((c - o) @ n) / dn
        if best is not None and t >= best[5]:
            continue
        hit = o + d * t - c
        p2 = (float(hit @ u), float(hit @ v))
        cont = [i for i in range(len(flats)) if _pip_np(p2, flats[i])]
        if not cont:
            continue
        outer = min(cont, key=lambda i: areas[i])
        inner = [j for j in range(len(flats)) if j != outer and j not in cont and areas[j] < areas[outer]
                 and _pip_np(flats[j][0], flats[outer])]
        holes = [j for j in inner if not any(k != j and areas[k] > areas[j] and _pip_np(flats[j][0], flats[k])
                                                 for k in inner)]
        best = (c, u, v, n, [flats[outer]] + [flats[j] for j in holes], t)
    return best


def hatch_segments_2d(rings, pattern, unit, rot, base):
    """Segments 2D (N, 2, 2) du motif découpé par les anneaux (pair / impair : les trous restent vides)."""
    fams = HATCH_PATTERNS.get(pattern)
    if not fams:
        return np.zeros((0, 2, 2))
    A = np.vstack([np.asarray(R, dtype=np.float64) for R in rings])
    B = np.vstack([np.roll(np.asarray(R, dtype=np.float64), -1, axis=0) for R in rings])
    O = np.asarray(base, dtype=np.float64)
    unit = max(float(unit), 1e-12)
    segs = []
    total = 0
    for ang, al0, pp0, shift, spacing, dashes in fams:
        a = math.radians(ang) + rot
        dv = np.array((math.cos(a), math.sin(a)))
        nv = np.array((-math.sin(a), math.cos(a)))
        h, s, al0, pp0 = spacing * unit, shift * unit, al0 * unit, pp0 * unit
        dash = [x * unit for x in dashes]
        period = sum(abs(x) for x in dash)
        pa, pb = (A - O) @ nv, (B - O) @ nv
        qa, qb = (A - O) @ dv, (B - O) @ dv
        lo, hi = float(min(pa.min(), pb.min())), float(max(pa.max(), pb.max()))
        k0, k1 = math.ceil((lo - pp0) / h), math.floor((hi - pp0) / h)
        if k1 < k0:
            continue
        if k1 - k0 + 1 > HATCH_MAX_LINES:
            raise HatchTooDense()
        dp = pb - pa
        ok_e = np.abs(dp) > 1e-15
        for c0 in range(k0, k1 + 1, 256):
            ks = np.arange(c0, min(c0 + 256, k1 + 1))
            cc = pp0 + ks * h
            mask = ((pa[None, :] > cc[:, None]) != (pb[None, :] > cc[:, None])) & ok_e[None, :]
            tt = (cc[:, None] - pa[None, :]) / np.where(ok_e, dp, 1.0)[None, :]
            along = qa[None, :] + tt * (qb - qa)[None, :] - (al0 + ks * s)[:, None]
            for row, k in enumerate(ks):
                vals = np.sort(along[row][mask[row]])
                if len(vals) < 2:
                    continue
                bp = O + dv * (al0 + k * s) + nv * (pp0 + k * h)
                for i in range(0, len(vals) - 1, 2):
                    t0, t1 = float(vals[i]), float(vals[i + 1])
                    if t1 - t0 < 1e-12:
                        continue
                    if not dash or period < 1e-12:
                        segs.append((bp + dv * t0, bp + dv * t1))
                        total += 1
                    else:
                        m = math.floor(t0 / period)
                        while m * period < t1:
                            pos = m * period
                            for ln in dash:
                                if ln > 0:
                                    a_, b_ = max(pos, t0), min(pos + ln, t1)
                                    if b_ - a_ > 1e-12:
                                        segs.append((bp + dv * a_, bp + dv * b_))
                                        total += 1
                                pos += abs(ln)
                            m += 1
                    if total > HATCH_MAX_SEGS:
                        raise HatchTooDense()
    if not segs:
        return np.zeros((0, 2, 2))
    return np.array(segs, dtype=np.float64)


def hatch_mesh_data(dd, pattern, scale, rot):
    """(sommets, arêtes, faces) en coordonnées locales de l'objet hachure."""
    c, u, v = np.array(dd["c"]), np.array(dd["u"]), np.array(dd["v"])
    rings = [np.array(R, dtype=np.float64) for R in dd["rings"]]

    def to3(P2):
        P2 = np.asarray(P2, dtype=np.float64).reshape(-1, 2)
        return c + P2[:, :1] * u + P2[:, 1:2] * v
    if pattern == 'SOLID':
        polys = [[Vector((float(p[0]), float(p[1]), 0.0)) for p in R] for R in rings]
        tris = geometry.tessellate_polygon(polys)
        V = to3(np.vstack(rings))
        return V, [], [tuple(t) for t in tris]
    S = hatch_segments_2d(rings, pattern, float(dd["unit"]) * scale, rot, dd.get("base", (0.0, 0.0)))
    if not len(S):
        return np.zeros((0, 3)), [], []
    V = to3(S.reshape(-1, 2))
    E = [(2 * i, 2 * i + 1) for i in range(len(S))]
    return V, E, []


def _hatch_new_mesh(name, V, E, F):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(p) for p in V], E, F)
    me.update()
    return me


def rebuild_hatch(obj):
    """Reconstruit la géométrie d'une hachure à partir de sa définition et de ses réglages (motif, échelle, rotation)."""
    dd = json.loads(obj["dessin_hatch"])
    pg = obj.dessin_hatch
    V, E, F = hatch_mesh_data(dd, pg.pattern, pg.scale, pg.rotation)
    old = obj.data
    obj.data = _hatch_new_mesh(old.name, V, E, F)
    for mat in old.materials:
        obj.data.materials.append(mat)
    if old.users == 0:
        bpy.data.meshes.remove(old)
    return obj


def hatch_auto_unit(context, c, u):
    """Pas de motif automatique : environ 10 pixels à l'écran au moment de la création."""
    try:
        rv3d, region = context.region_data, context.region
        a = project_px(rv3d, region, Vector(c))
        b = project_px(rv3d, region, Vector(c) + Vector(u))
        k = (b - a).length if a is not None and b is not None else 0.0
        if k > 1e-6:
            return 10.0 * px_scale() / k
    except (AttributeError, ReferenceError, TypeError):
        pass
    return None


def create_hatch(context, region, pattern=None, scale=None, rot=None, unit=None, name="Hatch"):
    """Crée l'objet hachure d'une région (c, u, v, n, anneaux 2D). Lève HatchTooDense si le motif est trop serré."""
    st = context.scene.dessin
    c, u, v, n, rings = region[:5]
    pattern = pattern or st.hatch_pattern
    scale = st.hatch_scale if scale is None else scale
    rot = st.hatch_rotation if rot is None else rot
    rings = [np.asarray(R, dtype=np.float64) for R in rings]
    lo = np.vstack(rings).min(axis=0)
    hi = np.vstack(rings).max(axis=0)
    mid2 = (lo + hi) * 0.5
    origin = np.asarray(c, dtype=np.float64) + mid2[0] * u + mid2[1] * v
    if unit is None:
        unit = st.hatch_spacing if st.hatch_spacing > 0.0 else hatch_auto_unit(context, origin, u)
        if unit is None:
            unit = float(np.linalg.norm(hi - lo)) / 40.0
    # définition en coordonnées locales (origine de l'objet au centre de la région, axes du monde) :
    # la hachure suit ensuite l'objet quand on le déplace, le tourne ou le met à l'échelle
    dd = {"c": [float(x) for x in (np.asarray(c) - origin)], "u": [float(x) for x in u], "v": [float(x) for x in v],
          "n": [float(x) for x in n], "rings": [[[float(p[0]), float(p[1])] for p in R] for R in rings],
          "unit": float(unit), "base": [0.0, 0.0]}
    V, E, F = hatch_mesh_data(dd, pattern, scale, rot)
    me = _hatch_new_mesh(name, V, E, F)
    obj = bpy.data.objects.new(name, me)
    context.view_layer.active_layer_collection.collection.objects.link(obj)
    obj.matrix_world = Matrix.Translation(Vector(origin))     # à jour tout de suite (contour créé juste après)
    obj["dessin_hatch"] = json.dumps(dd)
    _HATCH_EDIT["busy"] = True
    try:
        obj.dessin_hatch.pattern = pattern
        obj.dessin_hatch.scale = scale
        obj.dessin_hatch.rotation = rot
    finally:
        _HATCH_EDIT["busy"] = False
    return obj


def hatch_boundary_curve(context, obj, name="Hatch boundary"):
    """Courbe des contours d'une hachure (contour extérieur et trous), en coordonnées monde."""
    dd = json.loads(obj["dessin_hatch"])
    c, u, v = np.array(dd["c"]), np.array(dd["u"]), np.array(dd["v"])
    mw = obj.matrix_world
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    for R in dd["rings"]:
        R = np.asarray(R, dtype=np.float64)
        sp = cu.splines.new('POLY')
        sp.points.add(len(R) - 1)
        for i, p in enumerate(R):
            w = mw @ Vector(c + p[0] * u + p[1] * v)
            sp.points[i].co = (w.x, w.y, w.z, 1.0)
        sp.use_cyclic_u = True
    ob = bpy.data.objects.new(name, cu)
    for col in obj.users_collection:
        col.objects.link(ob)
        break
    else:
        context.view_layer.active_layer_collection.collection.objects.link(ob)
    return ob


_PATHS_CACHE = {}       # nom d'objet -> (clé, contours) : un plan de milliers de courbes n'est pas relu à chaque lancement


def _hatch_paths_of(context, objs):
    dg = context.evaluated_depsgraph_get()
    paths = []
    for o in objs:
        if is_hatch(o) or "dessin_cotation" in o.keys() or "dessin_cotation_texte" in o.keys():
            continue
        try:
            key = (o.data.as_pointer(), np.array(o.matrix_world).tobytes(), _geom_ver(o.name), _geom_ver(o.data.name), o.mode)
        except (AttributeError, ReferenceError):
            key = None
        hit = _PATHS_CACHE.get(o.name) if key is not None else None
        if hit is not None and hit[0] == key:
            got = hit[1]
        else:
            got = object_paths(o, dg)
            if key is not None:
                if len(_PATHS_CACHE) > 20000:
                    _PATHS_CACHE.clear()
                _PATHS_CACHE[o.name] = (key, got)
        paths.extend((P.copy(), c) for P, c in got)
    return paths


def _select_only(context, objs):
    deselect_all_objects(context)
    for o in objs:
        try:
            o.select_set(True)
        except (RuntimeError, ReferenceError):
            pass
    if objs:
        context.view_layer.objects.active = objs[-1]


class DESSIN_OT_hatch(_ProfileOp, bpy.types.Operator):
    bl_idname = "dessin.hatch"
    bl_label = "Hatch"
    bl_description = ("Like Hatch: fills closed planar curves with a pattern (curves inside another one become holes). "
                      "Click the curves (or select them first), then Enter / Space")
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        return self.execute(context)

    def execute(self, context):
        objs = [o for o in ordered_selection(context) if not is_hatch(o)]
        paths = _hatch_paths_of(context, objs)
        if not paths:
            self.report({'INFO'}, "Click the closed planar curves to hatch, then Enter")
            return {'CANCELLED'}
        groups, skipped = hatch_loop_groups(paths)
        regions = hatch_regions(groups)
        if not regions:
            self.report({'WARNING'}, "Hatch needs closed planar curves (or curves whose ends touch)")
            return {'CANCELLED'}
        made = []
        try:
            for rg in regions:
                made.append(create_hatch(context, rg))
        except HatchTooDense:
            delete_objects(made)
            self.report({'WARNING'}, "Pattern too dense for this area: increase the hatch scale")
            return {'CANCELLED'}
        _select_only(context, made)
        msg = f"{len(made)} hatch(es) created"
        if skipped:
            msg += f", {skipped} curve(s) ignored (open or not planar)"
        self.report({'INFO'}, msg)
        return {'FINISHED'}


class DESSIN_OT_hatch_region(DessinBase):
    bl_idname = "dessin.hatch_region"
    bl_label = "Hatch Region"
    bl_description = ("Hatch by picking a point: click inside an area closed by curves (curves inside it become holes). "
                      "The area under the cursor lights up. D: next pattern. Stays active to hatch several areas")

    TITLE = "Hatch Region"
    NEEDED = 1
    HAS_MODE = True
    MODES = tuple(p[1] for p in HATCH_PATTERN_ITEMS)
    mode = 0
    PLANAR = False
    LOCK_OK = False

    def lock_allowed(self):
        return False

    def prompt(self):
        return f"click inside a closed area   [D: pattern {self.MODES[self.mode]}]"

    def invoke(self, context, event):
        self._mouse = None
        self.hilite = []
        self.hatch_lines = None
        self._region = None
        try:
            keys = [p[0] for p in HATCH_PATTERN_ITEMS]
            self.mode = keys.index(context.scene.dessin.hatch_pattern)
        except (ValueError, AttributeError):
            self.mode = 0
        self.collect_loops(context)
        return super().invoke(context, event)

    def collect_loops(self, context):
        objs = []
        for o in context.visible_objects:
            if o.type == 'CURVE' or (o.type == 'MESH' and not len(o.data.polygons)):
                objs.append(o)
        try:
            self._groups, _sk = hatch_loop_groups(_hatch_paths_of(context, objs))
        except (ValueError, RuntimeError, ReferenceError):
            self._groups = []

    def update_cursor(self, context, event):
        region = find_window_region(self.area, event.mouse_x, event.mouse_y)
        self._mouse = (event.mouse_x - region.x, event.mouse_y - region.y) if region is not None else None
        super().update_cursor(context, event)

    def pattern(self):
        return HATCH_PATTERN_ITEMS[self.mode % len(HATCH_PATTERN_ITEMS)][0]

    def find_region(self):
        if self._mouse is None or self.region is None or not self._groups:
            return None
        try:
            rv3d = region_rv3d(self.region, self.area)
            o = region_2d_to_origin_3d(self.region, rv3d, self._mouse)
            d = region_2d_to_vector_3d(self.region, rv3d, self._mouse)
        except (AttributeError, ReferenceError, TypeError):
            return None
        return hatch_region_at(self._groups, np.array(o), np.array(d))

    def compute(self):
        self.hilite = []
        self.hatch_lines = None
        rg = self.find_region()
        self._region = rg
        if rg is None:
            return [], [], "No closed area under the cursor", None
        c, u, v, n, rings, _t = rg
        segs = []
        for R in rings:
            P = [Vector(c + p[0] * u + p[1] * v) for p in R]
            segs.extend((P[i], P[(i + 1) % len(P)]) for i in range(len(P)))
        self.hilite = segs[:4000]
        st = bpy.context.scene.dessin
        pat = self.pattern()
        if pat != 'SOLID':
            unit = st.hatch_spacing if st.hatch_spacing > 0.0 else None
            if unit is None:
                try:
                    rv3d = region_rv3d(self.region, self.area)
                    a = project_px(rv3d, self.region, Vector(c))
                    b = project_px(rv3d, self.region, Vector(c) + Vector(u))
                    k = (b - a).length if a is not None and b is not None else 0.0
                    unit = 10.0 * px_scale() / k if k > 1e-6 else None
                except (AttributeError, ReferenceError, TypeError):
                    unit = None
            if unit is not None:
                try:
                    S = hatch_segments_2d(rings, pat, unit * st.hatch_scale, st.hatch_rotation, (0.0, 0.0))
                    if len(S) <= 20000:
                        P = S.reshape(-1, 2)
                        self.hatch_lines = [tuple(c + p[0] * u + p[1] * v) for p in P]
                except HatchTooDense:
                    pass
        return [], [], f"Hatch {self.MODES[self.mode]}", ("hatch", rg)

    def click(self, context):
        rg = self.find_region()
        if rg is None:
            self.report({'INFO'}, "Click inside an area closed by curves")
            return
        try:
            context.scene.dessin.hatch_pattern = self.pattern()
            ob = create_hatch(context, rg[:5], pattern=self.pattern())
        except HatchTooDense:
            self.report({'WARNING'}, "Pattern too dense for this area: increase the hatch scale")
            return
        if context.scene.dessin.hatch_boundary:
            hatch_boundary_curve(context, ob)
        self.reset_state()
        self.refresh(context)

    def cleanup(self, context):
        self.hilite = []
        self.hatch_lines = None
        super().cleanup(context)


class DESSIN_OT_hatch_base(DessinBase):
    bl_idname = "dessin.hatch_base"
    bl_label = "Hatch Base Point"
    bl_description = "Like HatchBase: select hatches, then click the point the pattern starts from"

    TITLE = "Hatch Base Point"
    NEEDED = 1
    PLANAR = False
    LOCK_OK = False
    NO_SELECTION = "Select the hatches first"

    def lock_allowed(self):
        return False

    def prompt(self):
        return "new base point of the pattern"

    def invoke(self, context, event):
        self._hatches = [o for o in context.selected_objects if is_hatch(o)]
        if not self._hatches:
            self.report({'INFO'}, self.NO_SELECTION)
            return {'CANCELLED'}
        return super().invoke(context, event)

    def compute(self):
        if self.cur is None:
            return [], [], "", None
        return [self.cur], [], "Base point", None

    def click(self, context):
        if self.cur is None:
            return
        for o in self._hatches:
            try:
                dd = json.loads(o["dessin_hatch"])
                q = np.array(o.matrix_world.inverted() @ self.cur) - np.array(dd["c"])
                dd["base"] = [float(q @ np.array(dd["u"])), float(q @ np.array(dd["v"]))]
                o["dessin_hatch"] = json.dumps(dd)
                rebuild_hatch(o)
            except (HatchTooDense, KeyError, ValueError, ReferenceError, RuntimeError):
                continue
        self.finished = True


class DESSIN_OT_hatch_explode(bpy.types.Operator):
    bl_idname = "dessin.hatch_explode"
    bl_label = "Explode Hatch"
    bl_description = ("Like Explode on a hatch: the pattern becomes curves (a solid hatch becomes a planar surface). "
                      "Select the hatches first")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        hs = [o for o in context.selected_objects if is_hatch(o)]
        if not hs:
            self.report({'INFO'}, "Select the hatches to explode first")
            return {'CANCELLED'}
        made = []
        for o in hs:
            me = o.data
            mw = o.matrix_world.copy()
            cols = list(o.users_collection)
            if len(me.polygons):
                ob = bpy.data.objects.new("Hatch fill", me.copy())
                ob.matrix_world = mw
            else:
                cu = bpy.data.curves.new("Hatch lines", 'CURVE')
                cu.dimensions = '3D'
                for e in me.edges:
                    a, b = me.vertices[e.vertices[0]].co, me.vertices[e.vertices[1]].co
                    sp = cu.splines.new('POLY')
                    sp.points.add(1)
                    sp.points[0].co = (a.x, a.y, a.z, 1.0)
                    sp.points[1].co = (b.x, b.y, b.z, 1.0)
                ob = bpy.data.objects.new("Hatch lines", cu)
                ob.matrix_world = mw
            for col in cols[:1] or [context.view_layer.active_layer_collection.collection]:
                col.objects.link(ob)
            made.append(ob)
        delete_objects(hs)
        _select_only(context, made)
        self.report({'INFO'}, f"{len(hs)} hatch(es) exploded")
        return {'FINISHED'}


class DESSIN_OT_hatch_boundary(bpy.types.Operator):
    bl_idname = "dessin.hatch_boundary"
    bl_label = "Hatch Boundary"
    bl_description = "Like DupBorder on a hatch: creates curves on the outer boundary and the holes of the selected hatches"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        hs = [o for o in context.selected_objects if is_hatch(o)]
        if not hs:
            self.report({'INFO'}, "Select the hatches first")
            return {'CANCELLED'}
        made = [hatch_boundary_curve(context, o) for o in hs]
        _select_only(context, made)
        self.report({'INFO'}, f"{len(made)} boundary curve(s) created")
        return {'FINISHED'}


class DESSIN_OT_hatch_match(bpy.types.Operator):
    bl_idname = "dessin.hatch_match"
    bl_label = "Match Hatch"
    bl_description = ("Like MatchProperties for hatches: gives the selected hatches the pattern, scale and rotation "
                      "of the active hatch (the one clicked last)")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        src = context.view_layer.objects.active
        if not is_hatch(src):
            self.report({'INFO'}, "Select the hatches to change, then click the reference hatch last")
            return {'CANCELLED'}
        dst = [o for o in context.selected_objects if is_hatch(o) and o is not src]
        if not dst:
            self.report({'INFO'}, "Select the hatches to change, then click the reference hatch last")
            return {'CANCELLED'}
        s = src.dessin_hatch
        _HATCH_EDIT["busy"] = True
        try:
            for o in dst:
                o.dessin_hatch.pattern, o.dessin_hatch.scale, o.dessin_hatch.rotation = s.pattern, s.scale, s.rotation
                try:
                    dd, ds = json.loads(o["dessin_hatch"]), json.loads(src["dessin_hatch"])
                    dd["unit"] = ds["unit"] * src.matrix_world.to_scale().x / max(o.matrix_world.to_scale().x, 1e-12)
                    o["dessin_hatch"] = json.dumps(dd)
                    rebuild_hatch(o)
                except HatchTooDense:
                    self.report({'WARNING'}, f"{o.name}: pattern too dense for this area")
        finally:
            _HATCH_EDIT["busy"] = False
        self.report({'INFO'}, f"{len(dst)} hatch(es) matched to {src.name}")
        return {'FINISHED'}


# ---- Surfaces : FilletSrf / ChamferSrf, ExtendSrf, Split Isocurve, NetworkSrf ----

SRF_ROUND = {"radius": 0.1, "segments": 8, "distance": 0.1}


def _bm_world_copy(objs_tags):
    """bmesh réunissant des maillages en coordonnées monde ; material_index = étiquette de chaque objet."""
    bm = bmesh.new()
    for tag, o in objs_tags:
        tmp = bmesh.new()
        tmp.from_mesh(o.data)
        tmp.transform(o.matrix_world)
        for f in tmp.faces:
            f.material_index = tag
        me = bpy.data.meshes.new("_wd_tmp")
        tmp.to_mesh(me)
        tmp.free()
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
    return bm


def _face_islands(bm, same_tag=True):
    """Îlots de faces reliées (par arête), sans passer d'une étiquette à l'autre si same_tag."""
    bm.faces.ensure_lookup_table()
    seen = set()
    out = []
    for f in bm.faces:
        if f.index in seen:
            continue
        stack, comp = [f], []
        seen.add(f.index)
        while stack:
            g = stack.pop()
            comp.append(g)
            for e in g.edges:
                for h in e.link_faces:
                    if h.index not in seen and (not same_tag or h.material_index == g.material_index):
                        seen.add(h.index)
                        stack.append(h)
        out.append(comp)
    return out


def _intersect_cut(context, bm):
    """Découpe les faces d'étiquette 0 et 1 le long de leur intersection (Intersect (Knife) de Blender, côtés séparés)."""
    me = bpy.data.meshes.new("_wd_cut")
    bm.to_mesh(me)
    ob = bpy.data.objects.new("_wd_cut", me)
    context.scene.collection.objects.link(ob)
    vl = context.view_layer
    prev_active = vl.objects.active
    prev_sel = [o for o in context.selected_objects]
    try:
        for o in prev_sel:
            o.select_set(False)
        vl.objects.active = ob
        ob.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT')
        ebm = bmesh.from_edit_mesh(me)
        for f in ebm.faces:
            f.select_set(f.material_index == 0)
        bmesh.update_edit_mesh(me)
        bpy.ops.mesh.intersect(mode='SELECT_UNSELECT', separate_mode='ALL', threshold=1e-6)
        bpy.ops.object.mode_set(mode='OBJECT')
        out = bmesh.new()
        out.from_mesh(me)
    finally:
        try:
            if ob.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
        except RuntimeError:
            pass
        bpy.data.objects.remove(ob)
        bpy.data.meshes.remove(me)
        for o in prev_sel:
            try:
                o.select_set(True)
            except ReferenceError:
                pass
        vl.objects.active = prev_active
    return out


def _bm_from_world(o):
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bm.transform(o.matrix_world)
    return bm


def _bm_keep_island(bm, tag, hit):
    """Copie de bm réduite à l'îlot d'étiquette `tag` le plus proche de `hit`."""
    isl = [c for c in _face_islands(bm) if c[0].material_index == tag]
    if not isl:
        return None, 0
    best = min(isl, key=lambda comp: min((f.calc_center_median() - Vector(hit)).length for f in comp))
    keep = {f.index for f in best}
    out = bm.copy()
    out.faces.ensure_lookup_table()
    bmesh.ops.delete(out, geom=[f for f in out.faces if f.index not in keep], context='FACES')
    return out, len([c for c in isl])


def _bm_combined(parts):
    bm = bmesh.new()
    for tag, src in parts:
        me = bpy.data.meshes.new("_wd_tmp")
        src.to_mesh(me)
        for p in me.polygons:
            p.material_index = tag
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
    return bm


def _bm_offset(bm, sign, dist):
    out = bm.copy()
    out.normal_update()               # mêmes normales que l'arbre BVH de la surface (pas de recalcul : le côté choisi reste valable)
    for v in out.verts:
        v.co = v.co + v.normal * (sign * dist)
    return out


def _side_sign(bvh_src, pt):
    """+1 / -1 : côté (selon la normale de la surface) où se trouve le point."""
    loc, nrm, _i, _d = bvh_src.find_nearest(pt)
    if loc is None:
        return 1.0
    return 1.0 if (Vector(pt) - loc).dot(nrm) >= 0 else -1.0


def _contact_chain(bm, bvh_other, h, tol):
    """Bord découpé d'une surface (sommets à la distance h de l'autre surface) : polyligne ordonnée (points, fermée)."""
    edges = []
    for e in bm.edges:
        if len(e.link_faces) != 1:
            continue
        ok = True
        for v in e.verts:
            loc, _n, _i, d = bvh_other.find_nearest(v.co)
            if loc is None or abs(d - h) > tol:
                ok = False
                break
        if ok:
            edges.append((e.verts[0].index, e.verts[1].index))
    if not edges:
        return None, False
    bm.verts.ensure_lookup_table()
    paths = wire_paths(len(bm.verts), edges)
    if not paths:
        return None, False
    path, closed = max(paths, key=lambda pc: len(pc[0]))
    P = np.array([tuple(bm.verts[i].co) for i in path], dtype=np.float64)
    if closed and len(P) > 2 and np.linalg.norm(P[0] - P[-1]) < 1e-9:
        P = P[:-1]
    return P, bool(closed)


def round_surfaces(context, A, hitA, B, hitB, size, chamfer=False, segments=8):
    """FilletSrf / ChamferSrf sur maillages, comme Rhino : les deux surfaces sont coupées et gardées du côté cliqué,
    raccourcies jusqu'aux lignes de contact, et une bande d'arrondi (rayon constant) ou de chanfrein les relie.
    Retourne (objet bande, '') ou (None, message). Les objets A et B sont modifiés (ajustés)."""
    from mathutils.bvhtree import BVHTree
    Af, Bf = _bm_from_world(A), _bm_from_world(B)
    try:
        cut = _intersect_cut(context, _bm_combined([(0, Af), (1, Bf)]))
    except RuntimeError as ex:
        Af.free(); Bf.free()
        return None, f"Intersection failed: {ex}"
    Ak, nA_isl = _bm_keep_island(cut, 0, hitA)
    Bk, nB_isl = _bm_keep_island(cut, 1, hitB)
    cut.free()
    if Ak is None or Bk is None or nA_isl < 2 or nB_isl < 2:
        Af.free(); Bf.free()
        for b_ in (Ak, Bk):
            if b_ is not None:
                b_.free()
        return None, "The two surfaces must cross each other"
    bvhA, bvhB = BVHTree.FromBMesh(Af), BVHTree.FromBMesh(Bf)
    lo = Vector((min(v.co.x for v in Af.verts), min(v.co.y for v in Af.verts), min(v.co.z for v in Af.verts)))
    hi = Vector((max(v.co.x for v in Af.verts), max(v.co.y for v in Af.verts), max(v.co.z for v in Af.verts)))
    tol = max(2e-4 * (hi - lo).length, 1e-6)

    def side_of(bvh_surf, pts_bm, hit):
        """Côté de la surface (selon sa normale) où se trouve la partie gardée de l'autre surface, près de l'intersection."""
        acc = 0.0
        for v in pts_bm.verts:
            loc, nrm, _i, d = bvh_surf.find_nearest(v.co)
            if loc is not None and tol * 5 < d < max(4.0 * size, tol * 50):
                acc += (v.co - loc).dot(nrm) / d
        if abs(acc) > 1e-9:
            return 1.0 if acc > 0 else -1.0
        return _side_sign(bvh_surf, Vector(hit))
    sA, sB = side_of(bvhA, Bk, hitB), side_of(bvhB, Ak, hitA)
    gA = sum((v.co for v in Ak.verts), Vector()) / max(len(Ak.verts), 1)
    gB = sum((v.co for v in Bk.verts), Vector()) / max(len(Bk.verts), 1)
    h = size
    if chamfer:                              # distance le long des surfaces -> distance à l'autre surface
        seam_v = min(Ak.verts, key=lambda v: bvhB.find_nearest(v.co)[3] or 0.0).co
        la, na, _i, _d = bvhA.find_nearest(seam_v)
        lb, nb, _i, _d = bvhB.find_nearest(seam_v)
        if na is not None and nb is not None:
            ang = (na * sA).angle(nb * sB)
            h = size * math.sin(max(1e-3, math.pi - ang))
    Aoff, Boff = _bm_offset(Af, sA, h), _bm_offset(Bf, sB, h)
    for b_ in (Aoff, Boff):                  # le décalage suit la normale recalculée : on vérifie le côté
        pass

    def trim(keep_bm, off_bm, bvh_other):
        cutb = _intersect_cut(context, _bm_combined([(0, keep_bm), (1, off_bm)]))
        isl = [c for c in _face_islands(cutb) if c[0].material_index == 0]
        if len(isl) < 2:
            cutb.free()
            return None

        def mean_d(comp):
            ds = [bvh_other.find_nearest(f.calc_center_median())[3] for f in comp]
            return sum(ds) / len(ds)
        best = max(isl, key=mean_d)
        keep = {f.index for f in best}
        out = cutb.copy()
        cutb.free()
        out.faces.ensure_lookup_table()
        bmesh.ops.delete(out, geom=[f for f in out.faces if f.index not in keep or f.material_index != 0], context='FACES')
        for v in [v for v in out.verts if not v.link_faces]:
            out.verts.remove(v)
        return out
    try:
        At = trim(Ak, Boff, bvhB)
        Bt = trim(Bk, Aoff, bvhA)
    except RuntimeError as ex:
        At = Bt = None
    for b_ in (Ak, Bk, Aoff, Boff):
        b_.free()
    if At is None or Bt is None:
        Af.free(); Bf.free()
        for b_ in (At, Bt):
            if b_ is not None:
                b_.free()
        return None, "The radius is too large for these surfaces" if not chamfer else "The distance is too large for these surfaces"
    CA, closed = _contact_chain(At, bvhB, h, max(tol, h * 2e-3))
    CB, _cl = _contact_chain(Bt, bvhA, h, max(tol, h * 2e-3))
    if CA is None or CB is None:
        Af.free(); Bf.free(); At.free(); Bt.free()
        return None, "Could not find the contact lines"
    rows = []
    k = 1 if chamfer else max(2, segments)
    for p in CA:
        pv = Vector(p)
        if chamfer:
            d = np.linalg.norm(CB - p, axis=1)
            q = Vector(CB[int(np.argmin(d))])
            rows.append([pv.lerp(q, i / k) for i in range(k + 1)])
            continue
        loc, nrm, _i, _d = bvhA.find_nearest(pv)
        c = pv + nrm.normalized() * (sA * h)
        qloc, _n2, _i2, _d2 = bvhB.find_nearest(c)
        a_, b_ = pv - c, qloc - c
        th = a_.angle(b_) if a_.length > 1e-12 and b_.length > 1e-12 else 0.0
        row = []
        for i in range(k + 1):
            t = i / k
            if th < 1e-6:
                row.append(pv.lerp(qloc, t))
            else:
                w = (a_ * math.sin((1 - t) * th) + b_ * math.sin(t * th)) / math.sin(th)
                row.append(c + w.normalized() * h)
        rows.append(row)
    G = np.array([[tuple(x) for x in r] for r in rows], dtype=np.float64)
    Vx, F = grid_mesh(G, False, closed, False)
    strip = mesh_object_from_arrays(context, "Chamfer Surface" if chamfer else "Fillet Surface", Vx, F, Vx.mean(axis=0), True)
    if not chamfer:
        for poly in strip.data.polygons:
            poly.use_smooth = True
    for mat in A.data.materials:
        strip.data.materials.append(mat)
    for obj, bmt in ((A, At), (B, Bt)):
        save_untrimmed(obj)
        bmt.transform(obj.matrix_world.inverted())
        for f in bmt.faces:
            f.material_index = 0
        bmt.to_mesh(obj.data)
        bmt.free()
        obj.data.update()
    Af.free(); Bf.free()
    return strip, ""


def _pick_surface(op, context):
    """(objet maillage à faces, point touché) sous le curseur, ou (None, None)."""
    mouse = getattr(op, "_mouse", None)
    if mouse is None or op.region is None:
        return None, None
    try:
        rv3d = region_rv3d(op.region, op.area)
        ro = region_2d_to_origin_3d(op.region, rv3d, mouse)
        rv = region_2d_to_vector_3d(op.region, rv3d, mouse)
    except (AttributeError, ReferenceError, TypeError):
        return None, None
    ok, loc, _n, _i, obj, _m = ray_cast_opaque(context, ro, rv, skip_locked=True)
    if not ok or obj is None:
        return None, None
    obj = getattr(obj, "original", obj)
    if obj.type != 'MESH' or not len(obj.data.polygons):
        return None, None
    return obj, Vector(loc)


def _late_imports():
    """Noms définis dans des modules chargés après celui-ci : ils ne servent qu'à l'exécution des outils."""
    global save_untrimmed
    from .blocks import save_untrimmed
