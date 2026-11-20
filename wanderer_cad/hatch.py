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
from .settings import _HATCH_EDIT
from .trim import wire_paths
from .surfaces import (
    _ProfileOp, _plane_of, chain_open_paths, delete_objects, deselect_all_objects, grid_mesh,
    mesh_object_from_arrays, object_paths, ordered_selection,
)


# ---- Hachures : moteur ----

from .hatch_engine import HATCH_MAX_LINES, HATCH_MAX_SEGS, HatchTooDense, segments_2d   # noqa: F401
from .hatch_patterns import hatch_families, is_custom, pattern_list


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
        flats, areas = _drop_duplicate_loops(flats, areas)
        groups.append((c, u, v, n, flats, areas))
    return groups, skipped


def _seg_dist(Q, F):
    """Distance de chaque point de Q au contour fermé F (2D)."""
    A = F
    B = np.roll(F, -1, axis=0)
    AB = B - A
    L2 = np.maximum((AB * AB).sum(axis=1), 1e-30)
    D = Q[:, None, :] - A[None, :, :]
    t = np.clip((D * AB[None]).sum(axis=2) / L2[None], 0.0, 1.0)
    X = A[None] + t[..., None] * AB[None]
    return np.sqrt(((Q[:, None, :] - X) ** 2).sum(axis=2)).min(axis=1)


def _drop_duplicate_loops(flats, areas):
    """Un contour tracé deux fois (le contour d'une hachure posé sur sa forme, une courbe copiée sur place) ne compte
    qu'une fois : sinon l'imbrication paire / impaire se trompe et les trous de la forme disparaissent."""
    keep = []
    boxes = [(F.min(axis=0), F.max(axis=0)) for F in flats]
    for i, F in enumerate(flats):
        size = float(np.ptp(F, axis=0).max())
        tol = max(1e-6 * size, 1e-9)
        dup = False
        for j in keep:
            if abs(areas[j] - areas[i]) > 1e-6 * max(areas[i], 1e-18):
                continue
            if float(np.abs(boxes[i][0] - boxes[j][0]).max()) > tol or float(np.abs(boxes[i][1] - boxes[j][1]).max()) > tol:
                continue
            G = flats[j]
            if len(F) * len(G) > 4_000_000:
                continue
            if float(_seg_dist(F, G).max()) <= tol and float(_seg_dist(G, F).max()) <= tol:
                dup = True
                break
        if not dup:
            keep.append(i)
    if len(keep) == len(flats):
        return flats, areas
    return [flats[i] for i in keep], [areas[i] for i in keep]


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


_GROUP_BOXES = {}


def _group_boxes(flats):
    """Boîtes (x0, y0, x1, y1) et premiers points des contours d'un plan, calculés une fois : au survol, seuls les
    contours dont la boîte contient le point sont testés (un plan de milliers de courbes reste fluide)."""
    key = id(flats)
    hit = _GROUP_BOXES.get(key)
    if hit is not None and hit[0] is flats:
        return hit[1], hit[2]
    if len(_GROUP_BOXES) > 64:
        _GROUP_BOXES.clear()
    bb = np.array([(F[:, 0].min(), F[:, 1].min(), F[:, 0].max(), F[:, 1].max()) for F in flats], dtype=np.float64).reshape(-1, 4)
    first = np.array([F[0] for F in flats], dtype=np.float64).reshape(-1, 2)
    _GROUP_BOXES[key] = (flats, bb, first)
    return bb, first


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
        bb, first = _group_boxes(flats)
        near = np.flatnonzero((bb[:, 0] <= p2[0]) & (bb[:, 2] >= p2[0]) & (bb[:, 1] <= p2[1]) & (bb[:, 3] >= p2[1]))
        cont = [int(i) for i in near if _pip_np(p2, flats[i])]
        if not cont:
            continue
        outer = min(cont, key=lambda i: areas[i])
        ob = bb[outer]
        inb = np.flatnonzero((first[:, 0] >= ob[0]) & (first[:, 0] <= ob[2]) & (first[:, 1] >= ob[1]) & (first[:, 1] <= ob[3]))
        cset = set(cont)
        inner = [int(j) for j in inb if j != outer and int(j) not in cset and areas[j] < areas[outer]
                 and _pip_np(flats[j][0], flats[outer])]
        holes = [j for j in inner if not any(k != j and areas[k] > areas[j] and _pip_np(flats[j][0], flats[k])
                                                 for k in inner)]
        best = (c, u, v, n, [flats[outer]] + [flats[j] for j in holes], t)
    return best


def hatch_segments_2d(rings, pattern, unit, rot, base, dd=None):
    """Segments 2D (N, 2, 2) du motif découpé par les anneaux (pair / impair : les trous restent vides).
    `pattern` : clé d'un motif, ou directement ses familles de lignes."""
    fams = pattern if isinstance(pattern, (list, tuple)) else hatch_families(pattern, dd)
    return segments_2d(rings, fams, unit, rot, base)


def hatch_mesh_data(dd, pattern, scale, rot):
    """(sommets, arêtes, faces) en coordonnées locales de l'objet hachure."""
    c, u, v = np.array(dd["c"]), np.array(dd["u"]), np.array(dd["v"])
    rings = [np.array(R, dtype=np.float64) for R in dd["rings"]]

    def to3(P2):
        P2 = np.asarray(P2, dtype=np.float64).reshape(-1, 2)
        return c + P2[:, :1] * u + P2[:, 1:2] * v
    fams = hatch_families(pattern, dd)
    if fams is None:
        polys = [[Vector((float(p[0]), float(p[1]), 0.0)) for p in R] for R in rings]
        tris = geometry.tessellate_polygon(polys)
        V = to3(np.vstack(rings))
        return V, [], [tuple(t) for t in tris]
    S = hatch_segments_2d(rings, fams, float(dd["unit"]) * scale, rot, dd.get("base", (0.0, 0.0)))
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


def keep_pattern_copy(dd, pattern):
    """Un motif importé est recopié dans la hachure : elle reste juste si le motif est retiré de la liste,
    ou si la hachure est copiée dans un autre fichier. True si la définition a changé."""
    if is_custom(pattern):
        from .hatch_patterns import _CUSTOM
        try:
            e = _CUSTOM.get(int(pattern[3:]))
        except ValueError:
            e = None
        if e is not None:
            fams = [list(f[:5]) + [list(f[5])] for f in e["fams"]]
            if dd.get("fams") != fams or dd.get("pat") != e["name"]:
                dd["fams"], dd["pat"] = fams, e["name"]
                return True
        return False
    if pattern and ("fams" in dd or "pat" in dd):
        dd.pop("fams", None)
        dd.pop("pat", None)
        return True
    return False


def rebuild_hatch(obj):
    """Reconstruit la géométrie d'une hachure à partir de sa définition et de ses réglages (motif, échelle, rotation)."""
    dd = json.loads(obj["dessin_hatch"])
    pg = obj.dessin_hatch
    try:
        pat = pg.pattern
    except (TypeError, ValueError):
        pat = ""
    if keep_pattern_copy(dd, pat):
        obj["dessin_hatch"] = json.dumps(dd)
    V, E, F = hatch_mesh_data(dd, pat, pg.scale, pg.rotation)
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
    keep_pattern_copy(dd, pattern)
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


def _rings_signature(world_rings):
    """Signature d'une zone (anneaux en coordonnées monde, le premier = contour) : normale, plan, aire nette, boîte."""
    R0 = np.asarray(world_rings[0], dtype=np.float64)
    if len(R0) < 3:
        return None
    o = R0[0]

    def vec_area(R):
        R = np.asarray(R, dtype=np.float64) - o
        return 0.5 * np.cross(R, np.roll(R, -1, axis=0)).sum(axis=0)
    a0 = vec_area(R0)
    la = float(np.linalg.norm(a0))
    if la < 1e-18:
        return None
    nrm = a0 / la
    net = la - sum(float(np.linalg.norm(vec_area(R))) for R in world_rings[1:] if len(R) >= 3)
    allp = np.vstack([np.asarray(R, dtype=np.float64) for R in world_rings])
    return nrm, float(nrm @ R0[0]), net, allp.min(axis=0), allp.max(axis=0), len(world_rings)


def _same_area(sa, sb):
    if sa is None or sb is None or sa[5] != sb[5]:
        return False
    size = float(np.linalg.norm(sa[4] - sa[3]))
    tol = 1e-5 * size + 1e-9
    return (abs(abs(float(sa[0] @ sb[0])) - 1.0) < 1e-6 and abs(sa[1] - (sb[1] if sa[0] @ sb[0] > 0 else -sb[1])) <= tol
            and abs(sa[2] - sb[2]) <= 1e-4 * max(abs(sa[2]), 1e-12)
            and float(np.abs(sa[3] - sb[3]).max()) <= tol and float(np.abs(sa[4] - sb[4]).max()) <= tol)


def hatch_world_rings(obj):
    dd = json.loads(obj["dessin_hatch"])
    c, u, v = np.array(dd["c"]), np.array(dd["u"]), np.array(dd["v"])
    M = np.array(obj.matrix_world, dtype=np.float64)
    out = []
    for R in dd["rings"]:
        R = np.asarray(R, dtype=np.float64)
        P = c + R[:, :1] * u + R[:, 1:2] * v
        out.append(P @ M[:3, :3].T + M[:3, 3])
    return out


def hatch_on_area(context, region, skip=()):
    """La hachure visible qui remplit déjà exactement cette zone (mêmes contour et trous), ou None."""
    c, u, v, _n, rings = region[:5]
    c, u, v = np.asarray(c, dtype=np.float64), np.asarray(u, dtype=np.float64), np.asarray(v, dtype=np.float64)
    want = _rings_signature([c + np.asarray(R, dtype=np.float64)[:, :1] * u + np.asarray(R, dtype=np.float64)[:, 1:2] * v
                             for R in rings])
    if want is None:
        return None
    for o in context.view_layer.objects:
        if not is_hatch(o) or o in skip:
            continue
        try:
            if not o.visible_get():
                continue
            if _same_area(want, _rings_signature(hatch_world_rings(o))):
                return o
        except (KeyError, TypeError, ValueError, ReferenceError, RuntimeError):
            continue
    return None


def hatch_restyle(obj, pattern, scale, rot):
    """Donne un autre motif à une hachure (son calque, son pas et son point de base restent). Lève HatchTooDense."""
    pg = obj.dessin_hatch
    old = (pg.pattern, pg.scale, pg.rotation)
    _HATCH_EDIT["busy"] = True
    try:
        pg.pattern, pg.scale, pg.rotation = pattern, scale, rot
        try:
            rebuild_hatch(obj)
        except HatchTooDense:
            pg.pattern, pg.scale, pg.rotation = old
            raise
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
        if is_hatch(o) or "dessin_cotation" in o.keys() or "dessin_cotation_texte" in o.keys() or "cad_clip" in o.keys():
            continue            # (plan de coupe : son repère n'est pas un contour du dessin)
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


def _pattern_name(key):
    return next((p[1] for p in pattern_list() if p[0] == key), key)


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
        made, changed = [], []
        st = context.scene.dessin
        try:
            for rg in regions:
                # zone déjà hachurée : sa hachure prend le nouveau motif (au lieu d'une seconde par-dessus)
                old = hatch_on_area(context, rg, skip=changed)
                if old is not None:
                    hatch_restyle(old, st.hatch_pattern, st.hatch_scale, st.hatch_rotation)
                    changed.append(old)
                else:
                    made.append(create_hatch(context, rg))
        except HatchTooDense:
            delete_objects(made)
            self.report({'WARNING'}, "Pattern too dense for this area: increase the hatch scale")
            return {'CANCELLED'}
        _select_only(context, made + changed)
        parts = []
        if made:
            parts.append(f"{len(made)} hatch(es) created")
        if changed:
            parts.append(f"{len(changed)} hatch(es) changed to {_pattern_name(st.hatch_pattern)}")
        msg = ", ".join(parts)
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
    MODES = tuple(p[1] for p in pattern_list())
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
        self._rf = None
        pats = pattern_list()
        self._pat_keys = [p[0] for p in pats]
        self.MODES = tuple(p[1] for p in pats)
        try:
            self.mode = self._pat_keys.index(context.scene.dessin.hatch_pattern)
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
        keys = getattr(self, "_pat_keys", None) or [p[0] for p in pattern_list()]
        return keys[self.mode % len(keys)]

    def find_region(self):
        if self._mouse is None or self.region is None or not self._groups:
            return None
        try:
            rv3d = region_rv3d(self.region, self.area)
            o = region_2d_to_origin_3d(self.region, rv3d, self._mouse)
            d = region_2d_to_vector_3d(self.region, rv3d, self._mouse)
        except (AttributeError, ReferenceError, TypeError):
            return None
        rg = hatch_region_at(self._groups, np.array(o), np.array(d))
        if rg is None:
            # pas de contour fermé d'un seul tenant : la zone fermée par des traits qui se croisent (comme AutoCAD)
            from .boundary import region_under_mouse
            try:
                rg = region_under_mouse(self, bpy.context, self._mouse, islands=True)
            except (ValueError, RuntimeError, ReferenceError, AttributeError):
                rg = None
        return rg

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
        st = context.scene.dessin
        existing = hatch_on_area(context, rg[:5])
        try:
            st.hatch_pattern = self.pattern()
            if existing is not None:
                # zone déjà hachurée : sa hachure prend le motif choisi (au lieu d'une seconde par-dessus)
                ob = hatch_restyle(existing, self.pattern(), st.hatch_scale, st.hatch_rotation)
            else:
                ob = create_hatch(context, rg[:5], pattern=self.pattern())
        except HatchTooDense:
            self.report({'WARNING'}, "Pattern too dense for this area: increase the hatch scale")
            return
        if existing is not None:
            self.report({'INFO'}, f"Hatch changed to {_pattern_name(self.pattern())}")
        elif st.hatch_boundary:
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


class DESSIN_OT_hatch_import(bpy.types.Operator):
    bl_idname = "dessin.hatch_import"
    bl_label = "Import Hatch Patterns"
    bl_description = ("Adds the hatch patterns of a .pat file (AutoCAD, Rhino, Revit: acad.pat, acadiso.pat or your own) "
                      "to the list of patterns. They are saved with the file")
    bl_options = {'REGISTER', 'UNDO'}

    filepath: bpy.props.StringProperty(subtype='FILE_PATH', options={'SKIP_SAVE'})
    filter_glob: bpy.props.StringProperty(default="*.pat", options={'HIDDEN'})

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        from .hatch_patterns import add_custom_patterns, read_pat_file
        try:
            pats = read_pat_file(self.filepath)
        except OSError as e:
            self.report({'WARNING'}, f"Cannot read the file: {e}")
            return {'CANCELLED'}
        if not pats:
            self.report({'WARNING'}, "No hatch pattern found in this file")
            return {'CANCELLED'}
        keys = add_custom_patterns(context.scene, pats)
        try:
            context.scene.dessin.hatch_pattern = keys[0]
        except (TypeError, ValueError):
            pass
        self.report({'INFO'}, f"{len(keys)} hatch pattern(s) imported")
        return {'FINISHED'}


class DESSIN_OT_hatch_pattern_remove(bpy.types.Operator):
    bl_idname = "dessin.hatch_pattern_remove"
    bl_label = "Remove Imported Pattern"
    bl_description = ("Removes the chosen imported pattern from the list. The hatches that use it keep their look "
                      "(each hatch keeps a copy of its pattern)")
    bl_options = {'REGISTER', 'UNDO'}

    key: bpy.props.StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        from .hatch_patterns import forget_preview, remove_custom_pattern
        st = context.scene.dessin
        key = self.key or st.hatch_pattern
        if not is_custom(key):
            self.report({'INFO'}, "Only the imported patterns can be removed")
            return {'CANCELLED'}
        # les hachures qui s'en servent gardent leur copie du motif (déjà dans leur définition)
        for o in bpy.data.objects:
            if is_hatch(o):
                try:
                    if o.dessin_hatch.pattern == key:
                        dd = json.loads(o["dessin_hatch"])
                        keep_pattern_copy(dd, key)
                        o["dessin_hatch"] = json.dumps(dd)
                except (TypeError, ValueError, KeyError, ReferenceError):
                    pass
        if st.hatch_pattern == key:
            st.hatch_pattern = 'HATCH1'
        remove_custom_pattern(context.scene, key)
        forget_preview(key)
        return {'FINISHED'}


def draw_hatch_editor(layout, context, obj, compact=False):
    """Réglages d'une hachure (motif en vignettes, échelle, rotation) et ses commandes."""
    from .core import tr_label
    hs = [o for o in context.selected_objects if is_hatch(o)]
    pg = obj.dessin_hatch
    row = layout.row()
    row.template_icon_view(pg, "pattern", show_labels=True, scale=5.0, scale_popup=4.0)
    col = row.column(align=True)
    col.prop(pg, "pattern", text="")
    col.prop(pg, "scale")
    col.prop(pg, "rotation")
    if len(hs) > 1:
        col.label(text=tr_label(f"{len(hs)} hatches selected: all change"), icon='INFO')
    row = layout.row(align=True)
    row.operator(DESSIN_OT_hatch_base.bl_idname, text="Base Point")
    row.operator(DESSIN_OT_hatch_match.bl_idname, text="Match")
    row = layout.row(align=True)
    row.operator(DESSIN_OT_hatch_boundary.bl_idname, text="Boundary")
    row.operator(DESSIN_OT_hatch_explode.bl_idname, text="Explode")


class DESSIN_OT_hatch_edit(bpy.types.Operator):
    bl_idname = "dessin.hatch_edit"
    bl_label = "Edit Hatch"
    bl_description = ("Like HatchEdit: changes the pattern, scale and rotation of the selected hatches (pattern shown "
                      "as pictures). Also opened by a double-click on a hatch")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and any(is_hatch(o) for o in context.selected_objects)

    def _target(self, context):
        ob = context.active_object
        if is_hatch(ob) and ob.select_get():
            return ob
        return next((o for o in context.selected_objects if is_hatch(o)), None)

    def invoke(self, context, event):
        ob = self._target(context)
        if ob is None:
            return {'CANCELLED', 'PASS_THROUGH'}
        context.view_layer.objects.active = ob
        return context.window_manager.invoke_popup(self, width=340)

    def draw(self, context):
        ob = self._target(context)
        lay = self.layout
        if ob is None:
            lay.label(text="Select a hatch")
            return
        lay.label(text=ob.name, icon='MOD_LATTICE')
        draw_hatch_editor(lay, context, ob)

    def execute(self, context):
        return {'FINISHED'}


class DESSIN_OT_hatch_dblclick(bpy.types.Operator):
    bl_idname = "dessin.hatch_dblclick"
    bl_label = "Edit (double-click)"
    bl_description = ("Double-click a hatch to edit its pattern, scale and rotation; double-click a block to edit it "
                      "in place (Block Edit)")
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def invoke(self, context, event):
        ob = context.active_object
        if ob is None or not ob.select_get() or event.shift or event.ctrl or event.alt or event.oskey:
            return {'CANCELLED', 'PASS_THROUGH'}
        if is_hatch(ob):
            bpy.ops.dessin.hatch_edit('INVOKE_DEFAULT')
            return {'FINISHED'}
        from .curve_tools import block_edit_state, is_block_instance
        if is_block_instance(ob) and block_edit_state()["inst"] is None:
            bpy.ops.dessin.block_edit()
            return {'FINISHED'}
        return {'CANCELLED', 'PASS_THROUGH'}


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
