"""Wanderer CAD : Accrochages aux objets (points, budget, niveaux de détail)."""

import bmesh
import bpy
import math
import numpy as np
import time
from mathutils import Matrix, Vector

from .core import (
    DETAIL_EDGE_CAP, DETAIL_SNAP_VERTS, EDGE_CAP, HEAVY_SNAP_VERTS, HEAVY_SNAP_VERTS_EDIT, SNAP_BIAS_LUT, pref,
)


# --------------------------------------------------------------------------
# Accrochages
# --------------------------------------------------------------------------

def edit_selection(context):
    """[(objet, indices, coordonnées monde)] des sommets sélectionnés des maillages en mode édition."""
    out = []
    try:
        objs = list(context.objects_in_mode_unique_data)
    except AttributeError:
        return out
    for obj in objs:
        if obj.type != 'MESH':
            continue
        try:
            bm = bmesh.from_edit_mesh(obj.data)
        except ValueError:
            continue
        bm.verts.ensure_lookup_table()
        idx = [v.index for v in bm.verts if v.select]
        if not idx:
            continue
        co = np.array([tuple(bm.verts[i].co) for i in idx], dtype=np.float64)
        mw = np.array(obj.matrix_world, dtype=np.float64)
        out.append((obj, idx, co @ mw[:3, :3].T + mw[:3, 3]))
    return out


def curve_edit_selection(context):
    """[(objet, références, coordonnées monde)] des points sélectionnés des courbes en mode édition.
    Références : (spline, point, attribut) ; un point de Bézier sélectionné emporte ses deux poignées."""
    out = []
    try:
        objs = list(context.objects_in_mode_unique_data)
    except AttributeError:
        return out
    for obj in objs:
        if obj.type != 'CURVE':
            continue
        refs, pts = [], []
        try:
            for si, sp in enumerate(obj.data.splines):
                if sp.type == 'BEZIER':
                    for pi, bp in enumerate(sp.bezier_points):
                        if bp.select_control_point:
                            names = ("co", "handle_left", "handle_right")
                        else:
                            names = tuple(n for n, f in (("handle_left", bp.select_left_handle),
                                                         ("handle_right", bp.select_right_handle)) if f)
                        for n in names:
                            refs.append((si, pi, n))
                            pts.append(tuple(getattr(bp, n)))
                else:
                    for pi, pt in enumerate(sp.points):
                        if pt.select:
                            refs.append((si, pi, "co"))
                            pts.append(tuple(pt.co)[:3])
        except (ReferenceError, RuntimeError, AttributeError):
            continue
        if not refs:
            continue
        co = np.array(pts, dtype=np.float64)
        mw = np.array(obj.matrix_world, dtype=np.float64)
        out.append((obj, refs, co @ mw[:3, :3].T + mw[:3, 3]))
    return out


def curve_edit_apply(obj, refs, world, Xn):
    """Applique la matrice monde Xn aux points `refs` (positions monde d'origine `world`)."""
    try:
        sps = obj.data.splines
    except (ReferenceError, AttributeError):
        return
    M = np.linalg.inv(np.array(obj.matrix_world, dtype=np.float64)) @ Xn
    h = np.hstack((world, np.ones((len(world), 1)))) @ M.T
    for (si, pi, n), p in zip(refs, h):
        try:
            sp = sps[si]
            if sp.type == 'BEZIER':
                setattr(sp.bezier_points[pi], n, Vector((p[0], p[1], p[2])))
            else:
                pt = sp.points[pi]
                pt.co = (p[0], p[1], p[2], pt.co[3])
        except (IndexError, ReferenceError, AttributeError):
            continue
    try:
        obj.update_tag()
    except (ReferenceError, RuntimeError):
        pass


class SnapData(tuple):
    """(points, homogènes, types, biais) + segments et cercles pour les accroches dynamiques (Near, Int, Perp, Tan)."""
    excl = None       # masque (bool par point) des points d'objets exclus (objets en cours de déplacement)
    obj_span = None   # grosses scènes : (débuts, fins, boîte min, boîte max) par objet, pour ignorer ceux hors de la vue
    edges0 = None     # segments d'origine (avant exclusions) : `ranges` les indexe
    circles0 = None   # cercles d'origine (avant exclusions)
    dead_base = ()    # noms d'objets masqués dans ces tableaux (modifiés / supprimés depuis, ou écartés par l'outil)
    dead_extra = ()   # noms d'objets écartés par l'outil dans le complément
    extra = None      # complément : petit SnapData des objets créés ou modifiés depuis le calcul des grands tableaux
    coarse = ()       # noms des objets allégés (boîte englobante ou échantillon) : leur détail est chargé sous le curseur
    _proj = None      # projection écran du complément (gardée tant que la vue ne change pas)
    ranges = None     # nom d'objet -> (début, fin) de ses points / arêtes / cercles
    edges = None      # (E, 2, 3) monde
    circles = ()      # [(centre, rayon, normale, e1, e2, points échantillonnés, tolérance)]


def bezier_world_samples(pts_world, closed, steps=8):
    """Échantillonne une spline de Bézier : pts_world = [(co, handle_gauche, handle_droite)] en coordonnées monde."""
    out = []
    n = len(pts_world)
    segs = n if closed else n - 1
    ts = np.linspace(0.0, 1.0, steps + 1)[:, None]
    for i in range(segs):
        p0, p1 = pts_world[i][0], pts_world[i][2]
        p2, p3 = pts_world[(i + 1) % n][1], pts_world[(i + 1) % n][0]
        out.append((1 - ts) ** 3 * p0 + 3 * (1 - ts) ** 2 * ts * p1 + 3 * (1 - ts) * ts ** 2 * p2 + ts ** 3 * p3)
    return np.vstack(out) if out else np.zeros((0, 3))


def circle_info(c, P, min_pts=12):
    """(centre, rayon, normale, e1, e2, points, tolérance) si les points P forment un cercle / arc autour de c, sinon None."""
    P = np.asarray(P, dtype=np.float64)
    if len(P) < min_pts:
        return None
    c = np.asarray(c, dtype=np.float64)
    d = P - c
    r = np.linalg.norm(d, axis=1)
    rm = float(r.mean())
    if rm < 1e-9 or float(r.std()) > 0.03 * rm:
        return None
    if float(r.max() - r.min()) < 1e-3 * rm:
        # cercle en Bézier (4 arcs cubiques) : les nœuds sont exactement sur le cercle, les échantillons entre eux
        # légèrement à l'extérieur (jusqu'à 0,03 %) ; le plus petit rayon est le vrai (cote R400 et non R400.05)
        rm = float(r.min())
    cr = np.cross(d[0], d)
    j = int(np.argmax(np.linalg.norm(cr, axis=1)))
    n = cr[j]
    ln = float(np.linalg.norm(n))
    if ln < 1e-12:
        return None
    n = n / ln
    e1 = None
    for ax in (np.array((1.0, 0.0, 0.0)), np.array((0.0, 1.0, 0.0))):
        e = ax - n * float(ax @ n)
        if np.linalg.norm(e) > 0.3:
            e1 = e / np.linalg.norm(e)
            break
    if e1 is None:
        return None
    e2 = np.cross(n, e1)
    steps = np.linalg.norm(np.diff(P, axis=0), axis=1)
    tol = 2.0 * float(np.median(steps)) if len(steps) else 0.1 * rm
    return (c, rm, n, e1, e2, P, max(tol, 1e-6))


_SNAP_CACHE = {}    # nom d'objet -> (clé, points, types, segments, cercles, nb segments) : évite de recalculer les objets inchangés
_GEOM = {"ver": {}, "all": 0, "epoch": 0}    # nom d'ID -> n° de la dernière mise à jour de géométrie signalée par Blender (grosses scènes :
                                 # un maillage non signalé n'est pas relu sommet par sommet à chaque lancement d'outil)
_SNAP_LAST = {"key": None, "data": None, "out": None, "mkey": None, "objsig": None, "ov": None, "coarse": None}    # dernier jeu d'accrochage complet : réutilisé tel quel si la scène n'a pas bougé
_BBOX = {"ver": None, "rows": {}, "W": None, "ok": None}   # boîtes englobantes monde des objets, tant que la scène ne change pas
_SNAP_LOD = {}      # nom d'objet -> [clé, jeu d'accrochage détaillé, n° de dernier usage] : détail chargé sous le curseur
_LOD = {"tick": 0, "loads": 0, "x": -1e9, "y": -1e9, "t": 0.0, "pts": 0, "pending": None}
_LOD_PICK = 96              # objets allégés examinés sous le curseur (les plus petits à l'écran d'abord)
_LOD_MAX_OBJS = 600         # détails gardés en mémoire (les moins récemment survolés sont libérés)
_LOD_MAX_PTS = 3000000
_LOD_VERTS = 30000          # sommets lus par tranche (une tranche par mouvement de souris, puis en tâche de fond) : ~10 ms
_LOD_MIN_PX = 48.0          # un objet allégé n'est lu que s'il occupe au moins cette taille à l'écran : plus petit, ses
                            # milliers de sommets tiennent dans quelques pixels et on ne peut pas en viser un
_TIER = {"key": None, "box": None}


def _snap_handout(master, dead=(), extra=None, coarse=()):
    """Copie légère (mêmes tableaux) du jeu d'accrochage gardé en réserve : chaque outil y pose ses propres exclusions
    sans abîmer l'original. L'index écran déjà calculé pour la vue courante est repris.
    dead : objets de la réserve modifiés ou supprimés depuis ; extra : leurs versions à jour et les nouveaux objets.
    coarse : objets allégés, dont le détail est chargé quand le curseur passe dessus."""
    data = SnapData(tuple(master))
    data.edges0, data.circles0, data.ranges = master.edges0, master.circles0, master.ranges
    data.obj_span = master.obj_span
    data.coarse = coarse
    data.dead_base, data.dead_extra = set(dead), set()
    if extra is not None:
        ex = SnapData(tuple(extra))
        ex.edges0, ex.circles0, ex.ranges = extra.edges0, extra.circles0, extra.ranges
        data.extra = ex
    prev = _SNAP_LAST.get("out")
    scr = getattr(prev, "_scr", None) if prev is not None else None
    if scr is not None:
        data._scr = dict(scr, edges=None)
    _snap_apply_dead(data)
    if scr is not None and prev is not None and prev.edges is data.edges and scr.get("edges") is not None:
        data._scr["edges"] = scr["edges"]       # mêmes segments que le jeu précédent : leur projection écran ressert
    _SNAP_LAST["out"] = data
    return data


def _snap_apply_dead(data):
    """Recalcule masques, segments et cercles utiles d'un jeu d'accrochage d'après ses objets écartés."""
    def mask(sd, dead):
        ranges = sd.ranges or {}
        e0 = sd.edges0
        c0 = sd.circles0 if sd.circles0 is not None else []
        excl, emask, drop = None, None, set()
        for n in dead:
            r = ranges.get(n)
            if r is None:
                continue
            if excl is None:
                excl = np.zeros(len(sd[0]), dtype=bool)
                emask = np.ones(len(e0), dtype=bool) if e0 is not None else None
            excl[r[0]:r[1]] = True
            if emask is not None:
                emask[r[2]:r[3]] = False
            drop.update(range(r[4], r[5]))
        sd.excl = excl
        ed = None if e0 is None else (e0[emask] if emask is not None else e0)
        return ed, ([c for i, c in enumerate(c0) if i not in drop] if drop else list(c0))
    ed, circ = mask(data, data.dead_base)
    parts = [ed] if ed is not None and len(ed) else []
    ex = data.extra
    if ex is not None:
        ed2, circ2 = mask(ex, data.dead_extra)
        if ed2 is not None and len(ed2):
            parts.append(ed2)
        circ = circ + circ2
    data.edges = (parts[0] if len(parts) == 1 else np.concatenate(parts)) if parts else None
    data.circles = circ
    c = getattr(data, "_scr", None)
    if c is not None:
        c["edges"] = None


def _snap_extra(names, where, chunks, kinds, edge_chunks, circles):
    """Petit jeu d'accrochage des objets `names` (créés ou modifiés depuis le calcul des grands tableaux)."""
    pcs, kcs, ecs, circ, rng = [], [], [], [], {}
    p = e = 0
    for n in names:
        st, en = where[n]
        cs = chunks[st[1]:en[1]]
        es = edge_chunks[st[2]:en[2]]
        cc = circles[st[3]:en[3]]
        np_, ne_ = sum(len(c) for c in cs), sum(len(c) for c in es)
        rng[n] = (p, p + np_, e, e + ne_, len(circ), len(circ) + len(cc))
        pcs += cs
        kcs += kinds[st[1]:en[1]]
        ecs += es
        circ += cc
        p += np_
        e += ne_
    if p == 0 and e == 0 and not circ:
        return None
    pts = np.vstack(pcs) if pcs else np.zeros((0, 3), dtype=np.float64)
    k = np.concatenate(kcs) if kcs else np.zeros(0, dtype=np.int8)
    ex = SnapData((pts, np.hstack((pts, np.ones((len(pts), 1)))), k, SNAP_BIAS_LUT[k]))
    ex.edges0 = np.concatenate(ecs) if ecs else None
    ex.circles0 = circ
    ex.ranges = rng
    return ex


_OVERLAY_MAX_PTS = 200000     # au-delà (ou trop d'objets changés) les grands tableaux sont recalculés
_OVERLAY_MAX_OBJS = 600


def _geom_ver(name):
    return max(_GEOM["ver"].get(name, 0), _GEOM["all"])


def _perf_caches_clear():
    _SNAP_CACHE.clear()
    _GEOM["ver"].clear()
    _GEOM["all"] = 0
    _SNAP_LAST["key"] = _SNAP_LAST["data"] = _SNAP_LAST["out"] = _SNAP_LAST["mkey"] = _SNAP_LAST["objsig"] = _SNAP_LAST["ov"] = None
    _SNAP_LAST["coarse"] = None
    _SNAP_LOD.clear()
    _LOD["pts"] = 0
    _LOD["pending"] = None
    _TIER["key"] = _TIER["box"] = None
    _GEOM["epoch"] += 1
    _BBOX["ver"], _BBOX["rows"], _BBOX["W"], _BBOX["ok"] = None, {}, None, None
    try:
        _BOUNDARY.clear()
        _BOUNDARY_W.clear()
        _PATHS_CACHE.clear()
        _VIS.clear()
    except NameError:
        pass


def curve_snap_key(obj, mw):
    """Signature d'une courbe pour le cache des accroches (points, poignées, réglages, position) ; None si illisible."""
    import zlib
    try:
        if len(obj.modifiers):
            return None            # forme évaluée qui dépend des modificateurs : pas de cache
        cu = obj.data
        h = zlib.crc32(mw.tobytes())
        meta = [cu.as_pointer(), cu.resolution_u, cu.dimensions, repr(obj.get("dessin_centre")), len(cu.splines),
                cu.bevel_depth, cu.extrude, cu.offset, cu.bevel_mode, bool(cu.bevel_object), bool(cu.taper_object)]
        for sp in cu.splines:
            meta += [sp.type, sp.use_cyclic_u, sp.order_u, sp.resolution_u, sp.use_endpoint_u, sp.use_bezier_u]
            if sp.type == 'BEZIER':
                n = len(sp.bezier_points)
                a = np.empty(n * 9, dtype=np.float32)
                b = np.empty(n * 3, dtype=np.float32)
                c = np.empty(n * 3, dtype=np.float32)
                sp.bezier_points.foreach_get('co', b)
                sp.bezier_points.foreach_get('handle_left', c)
                a[:n * 3] = b
                a[n * 3:n * 6] = c
                sp.bezier_points.foreach_get('handle_right', c)
                a[n * 6:] = c
            else:
                n = len(sp.points)
                a = np.empty(n * 4, dtype=np.float32)
                sp.points.foreach_get('co', a)
            meta.append(n)
            h = zlib.crc32(a.tobytes(), h)
        return (tuple(meta), h)
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
        return None


class _InstProxy:
    """Objet vu à travers une instance de bloc : mêmes données, matrice monde de l'instance (pour l'accrochage)."""

    def __init__(self, o, M, name):
        self.__dict__["_o"] = o
        self.__dict__["matrix_world"] = M
        self.__dict__["name"] = name

    def __getattr__(self, k):
        return getattr(self.__dict__["_o"], k)

    def visible_get(self):
        return True


def _instance_proxies(context, limit=3000):
    """Objets des blocs (collections instanciées) visibles, avec la matrice de chaque copie."""
    out = []

    def walk(col, M, prefix, depth):
        for o in col.all_objects:
            if len(out) >= limit:
                return
            W = M @ o.matrix_world
            if o.type == 'EMPTY' and o.instance_type == 'COLLECTION' and o.instance_collection is not None:
                if depth < 4:
                    c2 = o.instance_collection
                    walk(c2, W @ Matrix.Translation(-Vector(c2.instance_offset)), prefix + o.name + ">", depth + 1)
            elif o.type in {'MESH', 'CURVE'}:
                out.append(_InstProxy(o, W, prefix + o.name))
    try:
        for e in context.view_layer.objects:
            if e.type == 'EMPTY' and e.instance_type == 'COLLECTION' and e.instance_collection is not None and e.visible_get():
                c = e.instance_collection
                walk(c, e.matrix_world @ Matrix.Translation(-Vector(c.instance_offset)), e.name + ">", 0)
    except (ReferenceError, AttributeError, RuntimeError):
        pass
    return out


def _snap_box_tier(objs):
    """Très grosse scène : noms des maillages qui n'entrent pas dans les grands tableaux d'accrochage (budget de points des
    préférences dépassé). Les petits objets gardent tout leur détail ; les plus lourds ne sont lus que lorsque le curseur
    passe dessus. None : le budget n'est pas atteint (ou illimité), rien ne change.
    Ne sont jamais allégés : courbes, contours sans faces (ce qu'on dessine) et objets en cours d'édition."""
    try:
        budget = float(pref("snap_budget")) * 1e6
    except (TypeError, ValueError):
        budget = 0.0
    if budget <= 0.0:
        return None
    key = (_GEOM["epoch"], len(objs), budget, len(bpy.data.meshes))
    if _TIER["key"] == key:
        return _TIER["box"]
    rows, dense, total, wire = [], [], 0, 0
    for o in objs:
        try:
            if o.type != 'MESH' or o.mode == 'EDIT':
                continue
            me = o.data
            nv = len(me.vertices)
            if nv == 0 or nv > 300000:
                continue                        # vide, ou énorme : déjà hors des grands tableaux
            if not len(me.polygons):
                wire += nv + len(me.edges)      # contour : toujours gardé, mais il compte dans le total
                total += nv + len(me.edges)
            elif nv > HEAVY_SNAP_VERTS:
                dense.append(o.name)
                total += min(nv, 6000)
            else:
                c = nv + len(me.edges)
                rows.append((c, o.name))
                total += c
        except (AttributeError, ReferenceError, RuntimeError):
            continue
    box = None
    if total > budget:
        # les objets denses ne donnaient déjà qu'un échantillon : ils passent entièrement à la demande ; puis les objets
        # ordinaires, du plus léger au plus lourd, tant que le budget le permet
        box = set(dense)
        rows.sort()
        acc = wire
        for c, n_ in rows:
            acc += c
            if acc > budget:
                box.add(n_)
    _TIER["key"], _TIER["box"] = key, box
    return box


def _snap_lod_sets(snap, region, rv3d, mx, my, R, timer=False):
    """Détail complet des objets allégés qui sont sous le curseur (les plus petits à l'écran d'abord, au plus `_LOD_PICK`).
    Les objets ne sont lus que lorsque le curseur ralentit, par tranches de quelques millisecondes : une tranche par
    mouvement de souris, puis la suite en tâche de fond si le curseur s'arrête. Les détails restent en mémoire tant
    qu'ils servent (les moins récemment survolés sont libérés)."""
    coarse = getattr(snap, "coarse", None)
    if not coarse:
        return ()
    if timer:
        slow = True
    else:
        # on ne lit un objet que lorsque le curseur ralentit pour viser (petits déplacements) ou repart après une pause :
        # traverser la scène d'un geste rapide ne déclenche aucune lecture, la souris reste fluide
        now = time.monotonic()
        slow = (math.hypot(mx - _LOD["x"], my - _LOD["y"]) <= 10.0 * px_scale()) or (now - _LOD["t"] > 0.15)
        _LOD["x"], _LOD["y"], _LOD["t"] = mx, my, now
    _LOD["pending"] = None          # reposé plus bas s'il reste des objets à lire ici
    try:
        ctx = bpy.context
        if ctx.mode not in {'OBJECT', 'EDIT_MESH'}:
            return ()
        under = objects_under_cursor(ctx, region, rv3d, mx, my, R, with_area=True)
    except (AttributeError, ReferenceError, RuntimeError, ValueError, TypeError):
        return ()
    dead = snap.dead_extra or ()
    picks = []
    min_side = _LOD_MIN_PX * px_scale()
    for o, area, side in under:
        if side < min_side:
            continue                # trop petit à l'écran pour viser un de ses points : il sera lu quand on zoomera
        try:
            n_ = o.name
        except ReferenceError:
            continue
        if n_ in coarse and n_ not in dead:
            picks.append((area, n_, o))
    if not picks:
        return ()
    picks.sort(key=lambda t: (t[0], t[1]))
    _LOD["tick"] += 1
    tick = _LOD["tick"]
    out = []
    stamp = (_GEOM["epoch"], _GEOM["all"])
    todo, todo_v, left = [], 0, 0
    for _a, n_, o in picks[:_LOD_PICK]:
        hit = _SNAP_LOD.get(n_)
        key = None
        if hit is None or hit[3] != stamp:
            # la scène a changé depuis la dernière vérification de ce détail (ou il n'existe pas) : clé relue
            try:
                me = o.data
                nv = len(me.vertices)
                key = (me.as_pointer(), nv, len(me.edges), np.array(o.matrix_world, dtype=np.float64).tobytes(),
                       _geom_ver(n_), _geom_ver(me.name))
            except (AttributeError, ReferenceError, RuntimeError):
                continue
            if hit is not None and hit[0] == key:
                hit[3] = stamp
            elif hit is not None:
                _LOD["pts"] -= len(hit[1][0])
                del _SNAP_LOD[n_]
                hit = None
        if hit is None:
            if slow and (not todo or todo_v + nv <= _LOD_VERTS):
                todo.append((n_, key))
                todo_v += nv
            else:
                left += 1           # la suite sera lue à la tranche suivante
            continue
        hit[2] = tick
        if len(hit[1][0]):
            out.append(hit[1])
    if todo:
        try:
            d = collect_snap_points(ctx, only={n_ for n_, _k in todo}, detail=True)
        except (AttributeError, ReferenceError, RuntimeError, ValueError, TypeError, MemoryError):
            d = None
        rng = d.ranges if d is not None else {}
        for n_, key in todo:
            r = rng.get(n_)
            if r is None or r[1] <= r[0]:
                # illisible (ou sans point) : noté vide pour ne pas être relu à chaque mouvement
                z3 = np.zeros((0, 3), dtype=np.float64)
                k0 = np.zeros(0, dtype=np.int8)
                sub = SnapData((z3, np.zeros((0, 4), dtype=np.float64), k0, SNAP_BIAS_LUT[k0]))
                _SNAP_LOD[n_] = [key, sub, tick, stamp]
                continue
            # une seule lecture pour toute la tranche, puis un jeu par objet (vues sur les mêmes tableaux)
            sub = SnapData((d[0][r[0]:r[1]], d[1][r[0]:r[1]], d[2][r[0]:r[1]], d[3][r[0]:r[1]]))
            sub.edges = sub.edges0 = d.edges0[r[2]:r[3]] if (d.edges0 is not None and r[3] > r[2]) else None
            sub.circles0 = list(d.circles0[r[4]:r[5]])
            sub.circles = list(sub.circles0)
            _LOD["loads"] += 1
            _SNAP_LOD[n_] = [key, sub, tick, stamp]
            _LOD["pts"] += len(sub[0])
            out.append(sub)
        while len(_SNAP_LOD) > 1 and (len(_SNAP_LOD) > _LOD_MAX_OBJS or _LOD["pts"] > _LOD_MAX_PTS):
            old = min(_SNAP_LOD, key=lambda k_: _SNAP_LOD[k_][2])
            if _SNAP_LOD[old][2] == tick:
                break               # tout ce qui reste sert à cet instant même
            _LOD["pts"] -= len(_SNAP_LOD[old][1][0])
            del _SNAP_LOD[old]
    if slow and left:
        # il reste des objets à lire sous le curseur : la suite se fait en tâche de fond, même si la souris ne bouge plus
        _LOD["pending"] = (snap, region, rv3d, mx, my, R, time.monotonic())
        try:
            if not bpy.app.timers.is_registered(_lod_timer):
                bpy.app.timers.register(_lod_timer, first_interval=0.01)
        except (AttributeError, RuntimeError, ValueError):
            pass
    return out


def _lod_timer():
    """Tâche de fond : finit de lire, tranche par tranche, les objets qui sont sous le curseur arrêté."""
    pend = _LOD["pending"]
    if pend is None or time.monotonic() - pend[6] > 2.0:
        _LOD["pending"] = None
        return None
    snap, region, rv3d, mx, my, R, _t = pend
    try:
        _snap_lod_sets(snap, region, rv3d, mx, my, R, timer=True)
    except Exception:
        _LOD["pending"] = None
        return None
    if _LOD["pending"] is None:
        _nav_redraw_all()           # tout est lu : l'accrochage au survol se met à jour
        return None
    return 0.01


def _lod_cells(d, persp, region, mx, my, R, allowed):
    """Points d'un détail chargé sous le curseur qui sont candidats à l'accrochage : (index écran, indices) ou None."""
    c = _screen_index(d, persp, region, allow_async=True)
    if c is None:
        return None
    idx = _screen_candidates(c, mx, my, R)
    if not len(idx):
        return None
    idx = idx[c["ok"][idx] & allowed[d[2][idx]]]
    if not len(idx):
        return None
    return c, idx


def collect_snap_points(context, exclude=None, only=None, detail=False):
    """Points, segments et cercles d'accrochage de la scène.
    detail=True (avec only) : tout le détail des objets demandés, même denses (chargement sous le curseur)."""
    import zlib
    try:
        gkey = (_HOVER["version"], context.mode, context.scene.as_pointer(), context.view_layer.as_pointer(),
                frozenset(exclude) if exclude else None, frozenset(only) if only is not None else None,
                len(context.view_layer.objects))
    except (AttributeError, ReferenceError, RuntimeError, TypeError):
        gkey = None
    last = _SNAP_LAST["data"]
    if gkey is not None and _SNAP_LAST["key"] == gkey and last is not None and context.mode == 'OBJECT' and not detail:
        # rien n'a bougé depuis le dernier passage (lancement d'un outil juste après le survol, commande répétée...) :
        # mêmes tableaux, sans relire la scène. Copie légère : chaque outil garde ses propres exclusions.
        ov = _SNAP_LAST["ov"] or ((), None)
        return _snap_handout(last, ov[0], ov[1], _SNAP_LAST.get("coarse") or ())
    seen_names = set()
    coarse = set()
    chunks, kinds = [], []
    edge_chunks, circles = [], []
    edge_total = [0]
    free_edges = [False, 0]     # [objet courant filaire ?, segments déjà gardés hors plafond]
    if context.mode == 'EDIT_MESH' and not detail:
        for o in context.objects_in_mode_unique_data:  # les données du maillage doivent refléter l'édition
            try:
                o.update_from_editmode()
            except (RuntimeError, AttributeError):
                pass

    def add(a, k):
        a = np.asarray(a, dtype=np.float64).reshape(-1, 3)
        if len(a):
            chunks.append(a)
            kinds.append(np.full(len(a), k, dtype=np.int8))

    def add_edges(a, b_):
        a = np.asarray(a, dtype=np.float64).reshape(-1, 3)
        b_ = np.asarray(b_, dtype=np.float64).reshape(-1, 3)
        if not len(a):
            return
        if free_edges[0]:
            # courbes et contours sans faces (ce qu'on dessine) : toujours accrochables en Near / Int / Perp, même si les
            # maillages d'une très grosse scène ont déjà rempli le plafond
            if free_edges[1] + len(a) <= EDGE_CAP:
                edge_chunks.append(np.stack((a, b_), axis=1))
                free_edges[1] += len(a)
        elif edge_total[0] + len(a) <= edge_cap:
            edge_chunks.append(np.stack((a, b_), axis=1))
            edge_total[0] += len(a)

    add([[0.0, 0.0, 0.0]], 3)
    starts = []      # (nom, nb de blocs de points, d'arêtes, de cercles) au début de chaque objet : sert à retrouver les points d'un objet

    if detail and only is not None:
        objs_all = [o for o in (context.view_layer.objects.get(n_) for n_ in only)
                    if o is not None and o.visible_get() and "dessin_hatch" not in o.keys()]
    else:
        objs_all = [o for o in context.view_layer.objects if o.visible_get() and not (exclude and o.name in exclude)
                    and (only is None or o.name in only) and "dessin_hatch" not in o.keys()]
    box_tier = _snap_box_tier(objs_all) if (only is None and not detail) else None
    edge_cap = DETAIL_EDGE_CAP if detail else EDGE_CAP
    for obj in objs_all + (
                _instance_proxies(context) if only is None else []):   # hachures : motif non accrochable ; blocs : leur géométrie l'est
        starts.append((obj.name, len(chunks), len(edge_chunks), len(circles)))
        try:
            free_edges[0] = obj.type == 'CURVE' or (obj.type == 'MESH' and not len(obj.data.polygons))
        except (AttributeError, ReferenceError, RuntimeError):
            free_edges[0] = False
        mw = np.array(obj.matrix_world, dtype=np.float64)
        R, T = mw[:3, :3], mw[:3, 3]

        def to_world(a, R=R, T=T):
            return np.asarray(a, dtype=np.float64).reshape(-1, 3) @ R.T + T

        dense = None     # points de l'objet pour reconnaître un cercle / arc
        i0, e0, c0, et0 = len(chunks), len(edge_chunks), len(circles), edge_total[0]
        ckey = None
        cheap = None

        def store(obj=obj, i0=i0, e0=e0, c0=c0, et0=et0):
            if ckey is not None and not detail:     # le détail chargé sous le curseur a son propre cache (_SNAP_LOD)
                _SNAP_CACHE[obj.name] = (ckey, chunks[i0:], kinds[i0:], edge_chunks[e0:], circles[c0:], edge_total[0] - et0, cheap)
        if obj.type == 'EMPTY':
            add([T], 3)

        elif obj.type == 'MESH':
            me = obj.data
            nv = len(me.vertices)
            if nv == 0:
                continue
            in_edit = obj.mode == 'EDIT'
            if not detail and not in_edit and (nv > 300000 or (box_tier is not None and obj.name in box_tier)):
                # objet énorme, ou budget de la scène dépassé : rien n'entre dans les grands tableaux et ses sommets ne sont
                # pas lus. Tout son détail est chargé dès que le curseur passe dessus (_snap_lod_sets).
                coarse.add(obj.name)
                seen_names.add(obj.name)
                _SNAP_CACHE.pop(obj.name, None)
                continue
            heavy_lim = HEAVY_SNAP_VERTS_EDIT if in_edit else (DETAIL_SNAP_VERTS if detail else HEAVY_SNAP_VERTS)
            if nv > heavy_lim and not in_edit and not detail:
                coarse.add(obj.name)            # échantillon seulement : le détail vient sous le curseur
            hit = None if detail else _SNAP_CACHE.get(obj.name)
            # validation légère : même maillage, même place, et Blender n'a signalé aucun changement de géométrie depuis
            cheap = (me.as_pointer(), nv, len(me.edges), len(me.polygons), mw.tobytes(), repr(obj.get("dessin_centre")),
                     _geom_ver(obj.name), _geom_ver(me.name))
            if hit is not None and not in_edit and len(hit) > 6 and hit[6] == cheap:
                seen_names.add(obj.name)
                chunks.extend(hit[1])
                kinds.extend(hit[2])
                edge_chunks.extend(hit[3])
                circles.extend(hit[4])
                edge_total[0] += hit[5]
                continue
            co = np.empty(nv * 3, dtype=np.float32)
            me.vertices.foreach_get('co', co)
            seen_names.add(obj.name)
            if not detail:
                ckey = (me.as_pointer(), nv, len(me.edges), len(me.polygons), mw.tobytes(), zlib.crc32(co), repr(obj.get("dessin_centre")), in_edit)
                if hit is not None and hit[0] == ckey:
                    if len(hit) > 6:
                        _SNAP_CACHE[obj.name] = hit[:6] + (cheap,)     # contenu identique : la validation légère est remise à jour
                    chunks.extend(hit[1])
                    kinds.extend(hit[2])
                    edge_chunks.extend(hit[3])
                    circles.extend(hit[4])
                    edge_total[0] += hit[5]
                    continue
            if nv > heavy_lim:
                # objet dense (modèle BlenderKit...) : un sommet par cellule d'une grille 32³ + coins de la boîte englobante,
                # sinon des millions de points ralentissent tout l'accrochage. Détail sous le curseur : grille 64³, sans les
                # coins de la boîte (ce ne sont pas des points de l'objet).
                co3 = co.reshape(-1, 3)
                if detail and nv > 250000:
                    co3 = co3[::int(math.ceil(nv / 250000.0))]      # objet géant : un sommet sur k suffit à remplir la grille
                w = to_world(co3)
                g = 64 if detail else 32
                mn, mxv = w.min(axis=0), w.max(axis=0)
                ext = np.maximum(mxv - mn, 1e-9)
                q = np.floor((w - mn) / ext * (g - 0.001)).astype(np.int64)
                _u, first = np.unique((q[:, 0] * 64 + q[:, 1]) * 64 + q[:, 2], return_index=True)
                add(w[first], 4 if len(me.polygons) else 0)
                if not detail:
                    add([(x, y, z) for x in (mn[0], mxv[0]) for y in (mn[1], mxv[1]) for z in (mn[2], mxv[2])], 4)
                store()
                continue
            w = to_world(co)
            dense = w
            ne = len(me.edges)
            used = np.zeros(nv, dtype=bool)
            ev = None
            if ne:
                ev = np.empty(ne * 2, dtype=np.int32)
                me.edges.foreach_get('vertices', ev)
                ev = ev.reshape(-1, 2)
                used[ev.ravel()] = True
            if len(me.polygons):
                add(w[used], 4)             # Vertex : sommets d'un maillage à faces
            else:
                add(w[used], 0)             # End : extrémités d'arêtes (contours, polylignes)
            add(w[~used], 3)                # Point : sommets isolés
            if ev is not None:
                if not (detail and nv > HEAVY_SNAP_VERTS):
                    add((w[ev[:, 0]] + w[ev[:, 1]]) * 0.5, 1)     # objet dense lu sous le curseur : sommets et arêtes, sans
                add_edges(w[ev[:, 0]], w[ev[:, 1]])               # les milieux de ses milliers de petites arêtes

        elif obj.type == 'CURVE':
            ckey = curve_snap_key(obj, mw)
            if ckey is not None:
                seen_names.add(obj.name)
                hit = _SNAP_CACHE.get(obj.name)
                if hit is not None and hit[0] == ckey:
                    chunks.extend(hit[1])
                    kinds.extend(hit[2])
                    edge_chunks.extend(hit[3])
                    circles.extend(hit[4])
                    edge_total[0] += hit[5]
                    continue
            for sp in obj.data.splines:
                if sp.type == 'BEZIER':
                    bp = sp.bezier_points
                    n = len(bp)
                    if n == 0:
                        continue
                    trip = [(to_world([tuple(p.co)])[0], to_world([tuple(p.handle_left)])[0],
                             to_world([tuple(p.handle_right)])[0]) for p in bp]
                    if obj.get("dessin_centre") is not None:
                        # cercle / arc / ellipse : seules les extrémités d'un arc ouvert sont des End ; les nœuds intérieurs
                        # (quadrants de la construction en Bézier) sont des Knot, les vrais quadrants viennent de Quad
                        if sp.use_cyclic_u:
                            add([t[0] for t in trip], 6)
                        else:
                            add([trip[0][0], trip[-1][0]], 0)
                            add([t[0] for t in trip[1:-1]], 6)
                    else:
                        add([t[0] for t in trip], 0)
                    add([t[1] for t in trip] + [t[2] for t in trip], 6)
                    segs = n if sp.use_cyclic_u else n - 1
                    mids = []
                    for i in range(segs):
                        a_, b_ = bp[i], bp[(i + 1) % n]
                        m = (np.array(a_.co) + 3.0 * np.array(a_.handle_right)
                             + 3.0 * np.array(b_.handle_left) + np.array(b_.co)) / 8.0
                        mids.append(m)
                    if mids:
                        add(to_world(mids), 1)
                    samples = bezier_world_samples(trip, sp.use_cyclic_u)
                    if len(samples) > 1:
                        add_edges(samples[:-1], samples[1:])
                        dense = samples if dense is None else np.vstack((dense, samples))
                elif sp.type == 'POLY':
                    pts = [tuple(p.co[:3]) for p in sp.points]
                    n = len(pts)
                    if n == 0:
                        continue
                    wp = to_world(pts)
                    add(wp, 0)          # End : sommets d'une polyligne (extrémités de chaque segment, comme Rhino)
                    segs = n if sp.use_cyclic_u else n - 1
                    mids = [
                        (np.array(pts[i]) + np.array(pts[(i + 1) % n])) * 0.5
                        for i in range(segs)
                    ]
                    if mids:
                        add(to_world(mids), 1)
                    idx_a = np.arange(segs)
                    add_edges(wp[idx_a], wp[(idx_a + 1) % n])
                else:   # NURBS : points de contrôle (Knot) ; la courbe évaluée donne extrémités (End), milieu (Mid) et arêtes (Near, Int...)
                    try:
                        add(to_world([tuple(p.co[:3]) for p in sp.points]), 6)
                    except (AttributeError, RuntimeError):
                        pass
                    nurbs_pending = True
            if locals().get("nurbs_pending"):
                nurbs_pending = False
                try:
                    ev = obj.evaluated_get(context.evaluated_depsgraph_get())
                    me_ev = ev.to_mesh()
                    try:
                        nv_ev = len(me_ev.vertices)
                        if 1 < nv_ev <= 200000:
                            cv = np.empty(nv_ev * 3, dtype=np.float64)
                            me_ev.vertices.foreach_get('co', cv)
                            wv = cv.reshape(-1, 3) @ R.T + T
                            ne_ev = len(me_ev.edges)
                            evv = np.empty(ne_ev * 2, dtype=np.int32)
                            me_ev.edges.foreach_get('vertices', evv)
                            evv = evv.reshape(-1, 2)
                            if ne_ev:
                                add_edges(wv[evv[:, 0]], wv[evv[:, 1]])
                                dense = wv if dense is None else np.vstack((dense, wv))
                                chain = [int(evv[0, 0])]
                                chains = []
                                for a_, b_ in evv:
                                    if int(a_) != chain[-1]:
                                        chains.append(chain)
                                        chain = [int(a_)]
                                    chain.append(int(b_))
                                chains.append(chain)
                                for ch in chains:
                                    pts_c = wv[ch]
                                    if len(pts_c) < 2:
                                        continue
                                    if not np.allclose(pts_c[0], pts_c[-1], atol=1e-9):
                                        add(pts_c[[0, -1]], 0)
                                    seg = np.linalg.norm(np.diff(pts_c, axis=0), axis=1)
                                    cum = np.concatenate(([0.0], np.cumsum(seg)))
                                    if cum[-1] > 1e-12:
                                        half = cum[-1] * 0.5
                                        j = int(np.searchsorted(cum, half))
                                        j = min(max(j, 1), len(cum) - 1)
                                        t = (half - cum[j - 1]) / max(cum[j] - cum[j - 1], 1e-12)
                                        add([pts_c[j - 1] + (pts_c[j] - pts_c[j - 1]) * t], 1)
                    finally:
                        ev.to_mesh_clear()
                except (RuntimeError, AttributeError, ReferenceError, ValueError, TypeError):
                    pass

        c = obj.get("dessin_centre")
        cw = None
        if c is not None:
            cw = to_world([tuple(c)])[0]
            add([cw], 2)
        elif obj.type == 'CURVE' and dense is not None and len(obj.data.splines) == 1:
            # cercle / arc dessiné autrement (Blender, import, NURBS) : centre retrouvé par ajustement, comme Rhino
            try:
                fit = fit_circle_points(dense)
            except (ValueError, np.linalg.LinAlgError):
                fit = None
            if fit is not None:
                cw = np.asarray(fit[0], dtype=np.float64)
                add([cw], 2)
        if cw is not None and dense is not None:
            # centre connu (cercle / arc de Wanderer) : un petit arc n'a que quelques échantillons, ils suffisent
            info = circle_info(cw, dense, 3 if obj.get("dessin_centre") is not None else 12)
            if info is not None:
                cc, r, n, e1, e2, P, tol = info
                circles.append(info)
                for q in (cc + r * e1, cc + r * e2, cc - r * e1, cc - r * e2):
                    if float(np.min(np.linalg.norm(P - q, axis=1))) <= tol:
                        add([q], 5)                 # Quad : quadrants couverts par le cercle / arc
        store()

    if only is None and not exclude:
        for n_ in [n_ for n_ in _SNAP_CACHE if n_ not in seen_names]:
            _SNAP_CACHE.pop(n_, None)           # objets disparus (ou cachés) : on libère la mémoire
    if not chunks:
        chunks.append(np.array([[1e9, 1e9, 1e9]]))
        kinds.append(np.full(1, 3, dtype=np.int8))
    ends = starts[1:] + [("", len(chunks), len(edge_chunks), len(circles))]
    mkey = gkey[1:4] if gkey is not None else None
    big = sum(len(c) for c in chunks) > _ASYNC_MIN
    cur = None
    if big and gkey is not None and only is None and context.mode == 'OBJECT':
        # signature de chaque objet : gros blocs (venus du cache par objet) par identité, petits blocs recréés à chaque
        # passage (vides, coins de boîte) par contenu
        cur = {}
        for st, en in zip(starts, ends):
            if en[1] > st[1] or en[2] > st[2] or en[3] > st[3]:
                cur[st[0]] = (tuple(id(c_) if c_.size > 64 else (c_.tobytes(), int(k_[0]))
                                    for c_, k_ in zip(chunks[st[1]:en[1]], kinds[st[1]:en[1]])),
                              tuple(map(id, edge_chunks[st[2]:en[2]])), tuple(map(id, circles[st[3]:en[3]])))
        osig = _SNAP_LAST["objsig"]
        if last is not None and osig is not None and _SNAP_LAST["mkey"] == mkey:
            # très grosse scène : les grands tableaux déjà assemblés resservent. Les objets modifiés ou supprimés depuis y
            # sont masqués, leurs versions à jour et les nouveaux objets vont dans un petit complément.
            dead = [n_ for n_, sg in osig.items() if cur.get(n_) != sg]
            fresh = [n_ for n_, sg in cur.items() if osig.get(n_) != sg]
            if len(dead) + len(fresh) <= _OVERLAY_MAX_OBJS:
                where = {st[0]: (st, en) for st, en in zip(starts, ends)}
                if sum(len(c) for n_ in fresh for c in chunks[where[n_][0][1]:where[n_][1][1]]) <= _OVERLAY_MAX_PTS:
                    extra = _snap_extra(fresh, where, chunks, kinds, edge_chunks, circles) if fresh else None
                    _SNAP_LAST["key"], _SNAP_LAST["ov"] = gkey, (tuple(dead), extra)
                    _SNAP_LAST["coarse"] = coarse = frozenset(coarse)
                    return _snap_handout(last, dead, extra, coarse)
    poff = np.concatenate(([0], np.cumsum([len(c) for c in chunks])))
    eoff = np.concatenate(([0], np.cumsum([len(c) for c in edge_chunks]))) if edge_chunks else np.zeros(1, dtype=np.int64)
    ranges = {st[0]: (int(poff[st[1]]), int(poff[en[1]]), int(eoff[st[2]]), int(eoff[en[2]]), st[3], en[3])
              for st, en in zip(starts, ends)}
    pts = np.vstack(chunks)
    k = np.concatenate(kinds)
    hom = np.hstack((pts, np.ones((len(pts), 1))))
    data = SnapData((pts, hom, k, SNAP_BIAS_LUT[k]))
    data.edges = data.edges0 = np.concatenate(edge_chunks) if edge_chunks else None
    data.circles0 = circles
    data.circles = list(circles)
    data.ranges = ranges
    data.obj_span = None
    if only is None:
        data.coarse = coarse = frozenset(coarse)
    if len(pts) > _ASYNC_MIN:
        # grosse scène : boîte englobante de chaque objet, pour ne projeter à l'écran que ceux qui sont dans la vue
        try:
            sp = np.array([(r[0], r[1]) for r in ranges.values() if r[1] > r[0]], dtype=np.int64)
            if len(sp):
                sp = sp[np.argsort(sp[:, 0])]
                if (sp[1:, 0] >= sp[:-1, 1]).all():
                    lo = np.minimum.reduceat(pts, sp[:, 0], axis=0)
                    hi = np.maximum.reduceat(pts, sp[:, 0], axis=0)
                    # reduceat va jusqu'au début suivant : exact si les plages se suivent sans trou, sinon simplement plus large
                    data.obj_span = (sp[:, 0].copy(), sp[:, 1].copy(), lo, hi)
        except (ValueError, IndexError, TypeError):
            data.obj_span = None
    if gkey is not None and context.mode == 'OBJECT' and only is None and not exclude:
        _SNAP_LAST["key"], _SNAP_LAST["data"], _SNAP_LAST["out"] = gkey, data, None
        _SNAP_LAST["mkey"], _SNAP_LAST["objsig"], _SNAP_LAST["ov"] = mkey, cur, ((), None)
        _SNAP_LAST["coarse"] = coarse
        return _snap_handout(data, coarse=coarse)
    return data


def exclude_snap(data, names):
    """Retire les objets `names` de l'accrochage sans recalculer ni copier les millions de points : un masque suffit. False si impossible."""
    if not isinstance(data, SnapData) or not getattr(data, "ranges", None):
        return False
    if data.edges0 is None and data.edges is not None:
        data.edges0 = data.edges
    if data.circles0 is None:
        data.circles0 = list(data.circles)
    data.dead_base = set(data.dead_base) | set(names)
    data.dead_extra = set(data.dead_extra) | set(names)
    _snap_apply_dead(data)
    return True


def merge_snap_data(a, b):
    """Réunit deux jeux d'accrochage (points, segments, cercles)."""
    pts = np.vstack((a[0], b[0]))
    k = np.concatenate((a[2], b[2]))
    data = SnapData((pts, np.hstack((pts, np.ones((len(pts), 1)))), k, SNAP_BIAS_LUT[k]))
    ea, eb = getattr(a, "edges", None), getattr(b, "edges", None)
    data.edges = np.concatenate([e for e in (ea, eb) if e is not None]) if (ea is not None or eb is not None) else None
    data.circles = list(getattr(a, "circles", ())) + list(getattr(b, "circles", ()))
    return data


def _late_imports():
    """Noms définis dans des modules chargés après celui-ci : ils ne servent qu'à l'exécution des outils."""
    global _ASYNC_MIN, _BOUNDARY, _BOUNDARY_W, _HOVER, _PATHS_CACHE, _VIS, _nav_redraw_all, _screen_candidates
    global _screen_index, fit_circle_points, objects_under_cursor, px_scale
    from .drawing import _ASYNC_MIN, _HOVER, _nav_redraw_all, _screen_candidates, _screen_index, px_scale
    from .selection import _BOUNDARY, _BOUNDARY_W, _VIS, objects_under_cursor
    from .dimensions import fit_circle_points
    from .hatch import _PATHS_CACHE
