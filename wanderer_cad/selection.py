"""Wanderer CAD : Sélection : fenêtre, capture, lasso, cercle, boucles, clic."""

import bmesh
import bpy
import gpu
import math
import numpy as np
from bpy_extras.view3d_utils import region_2d_to_origin_3d, region_2d_to_vector_3d
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector, geometry

from .core import AXES3, IDLE_TOOL, TAU, pref
from .snapping import _BBOX, _GEOM, _geom_ver, edit_selection
from .drawing import _HOVER, _same_region, find_window_region, get_shader, over_nav_gizmo, px_scale, region_rv3d
from .base import DessinBase
from .subd import copy_moved_edit, copy_moved_objects, ghost_for_edit, ghost_for_objects, ghost_hide, ghost_show


# --------------------------------------------------------------------------

BOX_BLUE = (0.25, 0.5, 1.0)
BOX_ORANGE = (1.0, 0.55, 0.1)


def _project_region(pts, persp, region):
    """pts (n,3) monde -> (sx, sy, ok) en pixels de la région ; ok : devant la caméra."""
    hom = np.hstack((pts, np.ones((len(pts), 1))))
    clip = hom @ persp.T
    w = clip[:, 3]
    ok = w > 1e-9
    ws = np.where(ok, w, 1.0)
    sx = (clip[:, 0] / ws * 0.5 + 0.5) * region.width
    sy = (clip[:, 1] / ws * 0.5 + 0.5) * region.height
    return sx, sy, ok


def _segments_hit_rect(x0, y0, x1, y1, xmin, ymin, xmax, ymax):
    """Liang-Barsky vectorisé : True pour les segments qui touchent le rectangle."""
    dx, dy = x1 - x0, y1 - y0
    t0 = np.zeros(len(x0))
    t1 = np.ones(len(x0))
    alive = np.ones(len(x0), dtype=bool)
    for pp, qq in ((-dx, x0 - xmin), (dx, xmax - x0), (-dy, y0 - ymin), (dy, ymax - y0)):
        par = pp == 0
        alive &= ~(par & (qq < 0))
        with np.errstate(divide='ignore', invalid='ignore'):
            r = qq / pp
        t0 = np.where((pp < 0) & ~par, np.maximum(t0, r), t0)
        t1 = np.where((pp > 0) & ~par, np.minimum(t1, r), t1)
    return alive & (t0 <= t1)


_NO_BBOX_TYPES = {'EMPTY', 'LIGHT', 'CAMERA', 'SPEAKER', 'LIGHT_PROBE'}


def _world_bboxes(objs):
    """(coins monde (n, 8, 3), boîte exploitable (n,)) des objets. Table gardée tant qu'aucune forme ni position ne change :
    dans une scène de milliers d'objets, chaque clic n'a plus à relire toutes les boîtes englobantes."""
    try:
        ver = (_GEOM["epoch"], len(bpy.data.objects))
    except (AttributeError, RuntimeError):
        ver = None
    if ver is None or _BBOX["ver"] != ver:
        _BBOX["ver"], _BBOX["rows"], _BBOX["W"], _BBOX["ok"] = ver, {}, None, None
    rows = _BBOX["rows"]
    ptrs = [o.as_pointer() for o in objs]
    miss = [i for i, p_ in enumerate(ptrs) if p_ not in rows]
    if miss:
        W = np.zeros((len(miss), 8, 3), dtype=np.float64)
        good = np.zeros(len(miss), dtype=bool)
        bbs, mws, at = [], [], []
        for j, i in enumerate(miss):
            o = objs[i]
            try:
                if o.type in _NO_BBOX_TYPES:
                    continue
                bbs.append([tuple(c) for c in o.bound_box])
                mws.append(np.array(o.matrix_world, dtype=np.float64))
                at.append(j)
            except (AttributeError, ReferenceError, RuntimeError, TypeError):
                continue
        if bbs:
            try:
                bb = np.array(bbs, dtype=np.float64)
                M = np.array(mws)
                w = np.einsum('nij,nkj->nki', M[:, :3, :3], bb) + M[:, None, :3, 3]
                fin = np.isfinite(w).all(axis=(1, 2)) & (np.abs(bb).max(axis=(1, 2)) < 1e18)
                at = np.array(at)
                W[at[fin]] = w[fin]
                good[at[fin]] = True
            except (ValueError, TypeError):
                pass
        base = 0 if _BBOX["W"] is None else len(_BBOX["W"])
        _BBOX["W"] = W if _BBOX["W"] is None else np.concatenate((_BBOX["W"], W))
        _BBOX["ok"] = good if _BBOX["ok"] is None else np.concatenate((_BBOX["ok"], good))
        for j, i in enumerate(miss):
            rows[ptrs[i]] = base + j
    if not ptrs:
        return np.zeros((0, 8, 3)), np.zeros(0, dtype=bool)
    r = np.fromiter((rows[p_] for p_ in ptrs), dtype=np.int64, count=len(ptrs))
    return _BBOX["W"][r], _BBOX["ok"][r]


def objects_screen_bounds(objs, persp, region):
    """Boîtes englobantes écran de plusieurs objets en un passage : (objs, xmin, xmax, ymin, ymax, sûr).
    sûr = False : boîte inexploitable (vide, lumière, objet derrière la caméra...), l'objet doit rester candidat."""
    objs = list(objs)
    n = len(objs)
    xmn, xmx = np.full(n, -np.inf), np.full(n, np.inf)
    ymn, ymx = np.full(n, -np.inf), np.full(n, np.inf)
    sure = np.zeros(n, dtype=bool)
    bbs, ids, mws = [], [], []
    for i, o in enumerate(objs):
        if o.type in {'EMPTY', 'LIGHT', 'CAMERA', 'SPEAKER', 'LIGHT_PROBE'}:
            continue
        try:
            bbs.append([tuple(c) for c in o.bound_box])
            mws.append(np.array(o.matrix_world, dtype=np.float64))
            ids.append(i)
        except (AttributeError, ReferenceError, RuntimeError, TypeError):
            continue
    if bbs:
        bb = np.array(bbs, dtype=np.float64)
        M = np.array(mws)
        w = np.einsum('nij,nkj->nki', M[:, :3, :3], bb) + M[:, None, :3, 3]
        hom = np.concatenate((w, np.ones(w.shape[:2] + (1,))), axis=2) @ persp.T
        ww = hom[..., 3]
        ok = (ww > 1e-9).all(axis=1) & np.isfinite(hom).all(axis=(1, 2))
        ws = np.where(ww > 1e-9, ww, 1.0)
        sx = (hom[..., 0] / ws * 0.5 + 0.5) * region.width
        sy = (hom[..., 1] / ws * 0.5 + 0.5) * region.height
        ids = np.array(ids)
        good = ids[ok]
        xmn[good], xmx[good] = sx.min(1)[ok], sx.max(1)[ok]
        ymn[good], ymx[good] = sy.min(1)[ok], sy.max(1)[ok]
        sure[good] = True
    return objs, xmn, xmx, ymn, ymx, sure


def objects_near_rect(objs, persp, region, rect, margin=2.0):
    """Objets dont la boîte englobante projetée peut toucher le rectangle écran (calcul groupé : un seul passage numpy).
    Les objets sans boîte exploitable (vides, lumières, derrière la caméra...) sont gardés."""
    objs = list(objs)
    if not objs:
        return objs
    w, good = _world_bboxes(objs)
    hom = np.concatenate((w, np.ones(w.shape[:2] + (1,))), axis=2) @ persp.T
    ww = hom[..., 3]
    ok = good & (ww > 1e-9).all(axis=1) & np.isfinite(hom).all(axis=(1, 2))
    ws = np.where(ww > 1e-9, ww, 1.0)
    sx = (hom[..., 0] / ws * 0.5 + 0.5) * region.width
    sy = (hom[..., 1] / ws * 0.5 + 0.5) * region.height
    xmin, ymin, xmax, ymax = rect
    out = ok & ((sx.max(1) < xmin - margin) | (sx.min(1) > xmax + margin)
                | (sy.max(1) < ymin - margin) | (sy.min(1) > ymax + margin))
    return [objs[i] for i in np.nonzero(~out)[0].tolist()]


def objects_under_cursor(context, region, rv3d, mx, my, radius, kinds=('MESH',), with_area=False):
    """Objets visibles (des types voulus) dont la boîte englobante projetée passe à moins de `radius` pixels du point
    (mx, my) de la région. Sert aux outils qui cherchent un bord ou une face sous le curseur à chaque mouvement de souris :
    dans une scène de milliers d'objets, seuls les deux ou trois objets voisins sont examinés, pas toute la scène.
    with_area=True : [(objet, surface de sa boîte à l'écran, plus grand côté)], sans les objets entièrement derrière la caméra."""
    try:
        persp = np.array(rv3d.perspective_matrix, dtype=np.float64)
        # liste des objets visibles et de leurs boîtes : relue seulement quand la scène change, pas à chaque mouvement de souris
        key = (_HOVER["version"], tuple(kinds), context.view_layer.as_pointer())
        c = _VIS.get("c")
        if c is None or c[0] != key:
            objs = [o for o in context.visible_objects if o.type in kinds]
            w, good = _world_bboxes(objs)
            c = (key, objs, np.concatenate((w, np.ones(w.shape[:2] + (1,))), axis=2), good)
            _VIS["c"] = c
            _VIS.pop("p", None)
        _k, objs, wh, good = c
        if not objs:
            return []
        # boîtes projetées : gardées tant que la vue ne bouge pas (un mouvement de souris ne les recalcule pas)
        sig = (key, persp.tobytes(), region.width, region.height)
        pr = _VIS.get("p")
        if pr is None or pr[0] != sig:
            hom = wh @ persp.T
            ww = hom[..., 3]
            ok = good & (ww > 1e-9).all(axis=1) & np.isfinite(hom).all(axis=(1, 2))
            ws = np.where(ww > 1e-9, ww, 1.0)
            sx = (hom[..., 0] / ws * 0.5 + 0.5) * region.width
            sy = (hom[..., 1] / ws * 0.5 + 0.5) * region.height
            x0, x1, y0, y1 = sx.min(1), sx.max(1), sy.min(1), sy.max(1)
            pr = (sig, x0, x1, y0, y1, ok, good & (ww <= 1e-9).all(axis=1), np.where(ok, (x1 - x0) * (y1 - y0), np.inf),
                  np.where(ok, np.maximum(x1 - x0, y1 - y0), np.inf))
            _VIS["p"] = pr
        _s, x0, x1, y0, y1, ok, behind, ar, side = pr
        m_ = 2.0
        out = ok & ((x1 < mx - radius - m_) | (x0 > mx + radius + m_)
                    | (y1 < my - radius - m_) | (y0 > my + radius + m_))
        if with_area:
            # boîte à cheval sur le plan de la caméra : surface infinie (dernier choix)
            keep = np.nonzero(~out & ~behind)[0]
            return [(objs[i], float(ar[i]), float(side[i])) for i in keep.tolist()]
        keep = np.nonzero(~out)[0]
        return [objs[i] for i in keep.tolist()]
    except (AttributeError, ReferenceError, RuntimeError, ValueError):
        _VIS.pop("c", None)
        _VIS.pop("p", None)
        res = [o for o in context.visible_objects if o.type in kinds]
        return [(o, float('inf'), float('inf')) for o in res] if with_area else res


_VIS = {}           # objets visibles + boîtes englobantes pour objects_under_cursor, tant que la scène ne change pas


_BOUNDARY = {}      # nom d'objet -> (clé, bords libres, arêtes libres) : recalculés seulement si le maillage change


def boundary_cached(o):
    """(boucles de bord libre, arêtes libres [(index, sommet a, sommet b)]) du maillage de o, gardées tant qu'il ne change pas."""
    me = o.data
    key = (me.as_pointer(), len(me.vertices), len(me.edges), len(me.polygons), _geom_ver(o.name), _geom_ver(me.name), o.mode)
    hit = _BOUNDARY.get(o.name)
    if hit is not None and hit[0] == key:
        return hit[1], hit[2]
    cnt = {}
    for p in me.polygons:
        for ek in p.edge_keys:
            cnt[ek] = cnt.get(ek, 0) + 1
    free = [(e.index, e.vertices[0], e.vertices[1]) for e in me.edges if cnt.get(tuple(sorted(e.vertices)), 0) == 1]
    loops = boundary_loops(me) if free else []        # même ordre des boucles que boundary_loops (les index sont réutilisés ailleurs)
    if len(_BOUNDARY) > 400:
        _BOUNDARY.clear()
    _BOUNDARY[o.name] = (key, loops, free)
    return loops, free


_BOUNDARY_W = {}    # nom d'objet -> (clé, segments de bord en coordonnées monde) pour la recherche sous le curseur


def boundary_world(o):
    """Bords libres de o en coordonnées monde, prêts pour un calcul groupé :
    (A, B, index d'arête) des arêtes libres et (A, B, n° de boucle) des segments de chaque boucle de bord."""
    loops, free = boundary_cached(o)
    me = o.data
    mwn = np.array(o.matrix_world, dtype=np.float64)
    key = (me.as_pointer(), len(me.vertices), len(me.edges), len(me.polygons), _geom_ver(o.name), _geom_ver(me.name),
           o.mode, mwn.tobytes())
    hit = _BOUNDARY_W.get(o.name)
    if hit is not None and hit[0] == key:
        return hit[1]
    nv = len(me.vertices)
    co = np.empty(nv * 3, dtype=np.float32)
    me.vertices.foreach_get('co', co)
    W = co.reshape(-1, 3).astype(np.float64) @ mwn[:3, :3].T + mwn[:3, 3]
    if free:
        fa = np.array([f[1] for f in free], dtype=np.int64)
        fb = np.array([f[2] for f in free], dtype=np.int64)
        fi = np.array([f[0] for f in free], dtype=np.int64)
    else:
        fa = fb = fi = np.zeros(0, dtype=np.int64)
    la, lb, ll = [], [], []
    for li, (idx, closed) in enumerate(loops):
        seq = list(idx) + ([idx[0]] if closed and len(idx) else [])
        la += seq[:-1]
        lb += seq[1:]
        ll += [li] * (len(seq) - 1)
    la, lb, ll = np.array(la, dtype=np.int64), np.array(lb, dtype=np.int64), np.array(ll, dtype=np.int64)
    res = (W[fa], W[fb], fi, W[la] if len(la) else np.zeros((0, 3)), W[lb] if len(lb) else np.zeros((0, 3)), ll)
    if len(_BOUNDARY_W) > 400:
        _BOUNDARY_W.clear()
    _BOUNDARY_W[o.name] = (key, res)
    return res


def nearest_segment_px(A, B, persp, region, mx, my):
    """(indice, distance en pixels) du segment monde A[i]-B[i] le plus proche du point écran (mx, my), ou (None, inf)."""
    if not len(A):
        return None, float("inf")
    sxa, sya, oka = _project_region(A, persp, region)
    sxb, syb, okb = _project_region(B, persp, region)
    dx, dy = sxb - sxa, syb - sya
    l2 = dx * dx + dy * dy
    t = np.clip(((mx - sxa) * dx + (my - sya) * dy) / np.where(l2 > 1e-12, l2, 1.0), 0.0, 1.0)
    d = np.hypot(sxa + t * dx - mx, sya + t * dy - my)
    d[~(oka & okb)] = np.inf
    i = int(np.argmin(d))
    return (i, float(d[i])) if np.isfinite(d[i]) else (None, float("inf"))


def bbox_vs_rect(obj, persp, region, rect, margin=2.0):
    """Boîte englobante projetée contre un rectangle écran : 'out' (entièrement dehors), 'in' (entièrement dedans)
    ou None (on ne peut pas conclure sans la géométrie)."""
    if obj.type in {'EMPTY', 'LIGHT', 'CAMERA', 'SPEAKER', 'LIGHT_PROBE'}:
        return None
    try:
        bb = np.array([tuple(c) for c in obj.bound_box], dtype=np.float64)
        mw = np.array(obj.matrix_world, dtype=np.float64)
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
        return None
    if bb.shape != (8, 3) or not np.isfinite(bb).all() or np.abs(bb).max() > 1e18:
        return None
    pts = bb @ mw[:3, :3].T + mw[:3, 3]
    sx, sy, ok = _project_region(pts, persp, region)
    if not ok.all():
        return None
    xmin, ymin, xmax, ymax = rect
    if (sx.max() < xmin - margin or sx.min() > xmax + margin
            or sy.max() < ymin - margin or sy.min() > ymax + margin):
        return 'out'
    if sx.min() >= xmin and sx.max() <= xmax and sy.min() >= ymin and sy.max() <= ymax:
        return 'in'
    return None


def bbox_outside_rect(obj, persp, region, rect, margin=2.0):
    """Test rapide : la boîte englobante de l'objet, projetée à l'écran, est-elle entièrement hors du rectangle ?
    (False si on ne peut pas conclure : objet derrière la caméra, boîte vide...)."""
    try:
        bb = np.array([tuple(c) for c in obj.bound_box], dtype=np.float64)
        mw = np.array(obj.matrix_world, dtype=np.float64)
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
        return False
    if bb.shape != (8, 3):
        return False
    pts = bb @ mw[:3, :3].T + mw[:3, 3]
    sx, sy, ok = _project_region(pts, persp, region)
    if not ok.all():
        return False
    xmin, ymin, xmax, ymax = rect
    return (sx.max() < xmin - margin or sx.min() > xmax + margin
            or sy.max() < ymin - margin or sy.min() > ymax + margin)


def object_hit_box(obj, dg, persp, region, rect, crossing):
    """L'objet est-il entièrement dans la boîte (fenêtre) ou touché par elle (capture) ?"""
    if obj.type not in {'EMPTY', 'LIGHT', 'CAMERA', 'SPEAKER', 'LIGHT_PROBE'} and bbox_outside_rect(obj, persp, region, rect):
        return False
    xmin, ymin, xmax, ymax = rect
    return object_hit_shape(obj, dg, persp, region,
                            lambda sx, sy: (sx >= xmin) & (sx <= xmax) & (sy >= ymin) & (sy <= ymax),
                            lambda ax, ay, bx, by: _segments_hit_rect(ax, ay, bx, by, xmin, ymin, xmax, ymax),
                            crossing)


def points_in_poly(px_, py_, poly):
    """Points (pixels) dans un polygone fermé (règle pair-impair) : tableau de booléens."""
    px_ = np.asarray(px_, dtype=np.float64)
    py_ = np.asarray(py_, dtype=np.float64)
    res = np.zeros(len(px_), dtype=bool)
    xs, ys = poly[:, 0], poly[:, 1]
    with np.errstate(invalid='ignore'):
        cand = np.nonzero((px_ >= xs.min()) & (px_ <= xs.max()) & (py_ >= ys.min()) & (py_ <= ys.max()))[0]
    if len(cand) == 0:
        return res
    x, y = px_[cand], py_[cand]
    inside = np.zeros(len(cand), dtype=bool)
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi, xj, yj = xs[i], ys[i], xs[j], ys[j]
        if yi != yj:
            inside ^= ((yi > y) != (yj > y)) & (x < (xj - xi) * (y - yi) / (yj - yi) + xi)
        j = i
    res[cand] = inside
    return res


def segments_hit_poly(ax, ay, bx, by, poly):
    """Segments (pixels) qui coupent le contour d'un polygone fermé."""
    ax, ay, bx, by = (np.asarray(v, dtype=np.float64) for v in (ax, ay, bx, by))
    res = np.zeros(len(ax), dtype=bool)
    xs, ys = poly[:, 0], poly[:, 1]
    with np.errstate(invalid='ignore'):
        out = ((np.maximum(ax, bx) < xs.min()) | (np.minimum(ax, bx) > xs.max())
               | (np.maximum(ay, by) < ys.min()) | (np.minimum(ay, by) > ys.max()))
    cand = np.nonzero(~out)[0]
    if len(cand) == 0:
        return res
    a_x, a_y, b_x, b_y = ax[cand], ay[cand], bx[cand], by[cand]
    hit = np.zeros(len(cand), dtype=bool)
    m = len(poly)
    for i in range(m):
        cx, cy = xs[i], ys[i]
        dx, dy = xs[(i + 1) % m], ys[(i + 1) % m]
        d1 = (b_x - a_x) * (cy - a_y) - (b_y - a_y) * (cx - a_x)
        d2 = (b_x - a_x) * (dy - a_y) - (b_y - a_y) * (dx - a_x)
        d3 = (dx - cx) * (a_y - cy) - (dy - cy) * (a_x - cx)
        d4 = (dx - cx) * (b_y - cy) - (dy - cy) * (b_x - cx)
        hit |= (d1 * d2 < 0) & (d3 * d4 < 0)
    res[cand] = hit
    return res


def object_hit_shape(obj, dg, persp, region, inside_fn, seg_fn, crossing):
    """L'objet est-il entièrement dans la forme (fenêtre) ou touché par elle (capture) ?
    inside_fn(sx, sy) : points dans la forme ; seg_fn(ax, ay, bx, by) : segments qui en coupent le contour."""
    mw = np.array(obj.matrix_world, dtype=np.float64)
    edges = None
    pts = None
    if obj.type in {'MESH', 'CURVE', 'SURFACE', 'FONT', 'META'}:
        try:
            ev = obj.evaluated_get(dg)
            me = ev.to_mesh()
        except (RuntimeError, ReferenceError):
            me = None
        if me is not None:
            try:
                nv = len(me.vertices)
                if nv:
                    co = np.empty(nv * 3, dtype=np.float32)
                    me.vertices.foreach_get('co', co)
                    pts = co.reshape(-1, 3).astype(np.float64) @ mw[:3, :3].T + mw[:3, 3]
                    ne = len(me.edges)
                    if ne:
                        e = np.empty(ne * 2, dtype=np.int32)
                        me.edges.foreach_get('vertices', e)
                        edges = e.reshape(-1, 2)
            finally:
                ev.to_mesh_clear()
    if pts is None or len(pts) == 0:
        pts = mw[:3, 3].reshape(1, 3)  # vide, lumière, caméra... : leur origine
    sx, sy, ok = _project_region(pts, persp, region)
    inside = ok & inside_fn(sx, sy)
    if not crossing:
        return bool(inside.all())
    if inside.any():
        return True
    if edges is not None:
        a, b = edges[:, 0], edges[:, 1]
        good = ok[a] & ok[b]
        if good.any():
            a, b = a[good], b[good]
            return bool(seg_fn(sx[a], sy[a], sx[b], sy[b]).any())
    return False


def redraw_region(op):
    """Redessine seulement la région de la vue (pas la barre latérale, la barre d'outils, les en-têtes) : bien plus léger pendant un cadre de sélection."""
    try:
        op.region.tag_redraw()
    except (AttributeError, ReferenceError):
        try:
            op.area.tag_redraw()
        except (AttributeError, ReferenceError):
            pass


def draw_fence_cb(op):
    """Ligne de coupe du Trim (pointillés), du point d'appui à la souris."""
    if not _same_region(op) or op.box is None:
        return
    x0, y0, x1, y1 = op.box
    ln = math.hypot(x1 - x0, y1 - y0)
    if ln < 1.0:
        return
    segs = []
    d = 12.0 * px_scale(1.0)
    for i in range(int(ln // d) + 1):
        k0, k1 = i * d / ln, min(i * d + 0.6 * d, ln) / ln
        segs += [(x0 + (x1 - x0) * k0, y0 + (y1 - y0) * k0), (x0 + (x1 - x0) * k1, y0 + (y1 - y0) * k1)]
    shader = get_shader('2D')
    gpu.state.blend_set('ALPHA')
    shader.bind()
    gpu.state.line_width_set(1.5)
    shader.uniform_float("color", (1.0, 1.0, 1.0, 1.0))
    batch_for_shader(shader, 'LINES', {"pos": segs}).draw(shader)
    gpu.state.line_width_set(1.0)
    gpu.state.blend_set('NONE')


def draw_box_cb(op):
    if not _same_region(op) or op.box is None:
        return
    x0, y0, x1, y1 = op.box
    crossing = x1 < x0
    col = BOX_ORANGE if crossing else BOX_BLUE
    shader = get_shader('2D')
    gpu.state.blend_set('ALPHA')
    shader.bind()
    quad = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    batch = batch_for_shader(shader, 'TRIS', {"pos": [quad[0], quad[1], quad[2], quad[0], quad[2], quad[3]]})
    shader.uniform_float("color", (col[0], col[1], col[2], 0.12))
    batch.draw(shader)
    gpu.state.line_width_set(1.5)
    shader.uniform_float("color", (col[0], col[1], col[2], 1.0))
    if not crossing:
        batch = batch_for_shader(shader, 'LINE_LOOP', {"pos": quad})
    else:  # pointillé pour la capture
        segs = []
        for (ax, ay), (bx, by) in zip(quad, quad[1:] + quad[:1]):
            ln = math.hypot(bx - ax, by - ay)
            n = int(ln // 12)
            for i in range(n + 1):
                t0, t1 = i * 12 / max(ln, 1e-6), min(i * 12 + 7, ln) / max(ln, 1e-6)
                segs += [(ax + (bx - ax) * t0, ay + (by - ay) * t0), (ax + (bx - ax) * t1, ay + (by - ay) * t1)]
        batch = batch_for_shader(shader, 'LINES', {"pos": segs})
    batch.draw(shader)
    gpu.state.line_width_set(1.0)
    gpu.state.blend_set('NONE')


_SEL_TYPE_PROP = {"SURFACE": "surf", "GREASEPENCIL": "grease_pencil", "GPENCIL": "grease_pencil", "CURVES": "curves"}


def type_selectable(space, obj):
    """Filtres de sélection du panneau « Selection Filters » (réglages show_object_select_* de la vue) : le type de l'objet est-il sélectionnable ?"""
    if space is None:
        return True
    name = _SEL_TYPE_PROP.get(obj.type, obj.type.lower())
    try:
        return bool(getattr(space, "show_object_select_" + name, True))
    except (AttributeError, RuntimeError, ReferenceError):
        return True


def ray_cast_opaque(context, ro, rv, skip_locked=False):
    """scene.ray_cast qui traverse les objets transparents (affichage filaire / boîte) et, si skip_locked, ceux qu'on ne peut pas
    sélectionner (calque verrouillé). Même retour que scene.ray_cast : (ok, loc, normal, index, obj, matrix)."""
    dg = context.evaluated_depsgraph_get()
    org = ro
    res = (False, None, None, -1, None, None)
    for _ in range(12):
        res = context.scene.ray_cast(dg, org, rv)
        ok, loc, _n, _i, obj, _m = res
        if not ok or obj is None:
            return res
        try:
            skip = obj.display_type in {'WIRE', 'BOUNDS'} or not obj.visible_get() or (skip_locked and obj.hide_select)
        except (RuntimeError, ReferenceError):
            skip = False
        if not skip:
            return res
        org = loc + Vector(rv).normalized() * 1e-4
    return (False, None, None, -1, None, None)


def _wire_pick_before(context, area, region, rv3d, mx, my, ro, rdir, max_dist, skip):
    """Objet filaire (courbe, maillage sans face) à moins de 6 px du curseur et pas plus loin que la surface touchée
    (distance max_dist de la caméra) : le plus proche du curseur, sinon None."""
    dg = context.evaluated_depsgraph_get()
    persp = np.array(rv3d.perspective_matrix, dtype=np.float64)
    r = 6.0 * px_scale()
    rect = (mx - r, my - r, mx + r, my + r)
    xmin, ymin, xmax, ymax = rect
    org = np.array(ro, dtype=np.float64)
    rd = np.array(rdir, dtype=np.float64)
    best = None
    cands = [o for o in context.view_layer.objects if o is not skip and o.type in {'MESH', 'CURVE', 'FONT'}]
    for o in objects_near_rect(cands, persp, region, rect):
        try:
            if o.hide_select or not o.visible_get() or not type_selectable(area.spaces.active, o) or o.get("cad_noGrab"):
                continue
            ev = o.evaluated_get(dg)
            me = ev.to_mesh()
        except (RuntimeError, ReferenceError):
            continue
        try:
            if me is None or len(me.polygons) or not len(me.edges):
                continue
            nv = len(me.vertices)
            co = np.empty(nv * 3, dtype=np.float32)
            me.vertices.foreach_get('co', co)
            e = np.empty(len(me.edges) * 2, dtype=np.int32)
            me.edges.foreach_get('vertices', e)
        finally:
            ev.to_mesh_clear()
        mw = np.array(o.matrix_world, dtype=np.float64)
        pts = co.reshape(-1, 3).astype(np.float64) @ mw[:3, :3].T + mw[:3, 3]
        e = e.reshape(-1, 2)
        sx, sy, okp = _project_region(pts, persp, region)
        good = okp[e[:, 0]] & okp[e[:, 1]]
        if not good.any():
            continue
        a, b = e[good, 0], e[good, 1]
        hit = _segments_hit_rect(sx[a], sy[a], sx[b], sy[b], xmin, ymin, xmax, ymax)
        if not hit.any():
            continue
        va = np.unique(np.concatenate([a[hit], b[hit]]))
        dist = float(((pts[va] - org) @ rd).min())
        if dist > max_dist + 1e-4 * max(abs(max_dist), 1.0):
            continue                       # derrière la surface touchée : elle gagne
        key = float(np.hypot(sx[va] - mx, sy[va] - my).min())
        if best is None or key < best[0]:
            best = (key, o)
    return best[1] if best else None


def pick_object_at(context, area, region, mx, my):
    """(objet, point 3D touché ou None) sous le curseur : lancer de rayon sur les maillages, sinon contact des arêtes."""
    rv3d = region_rv3d(region, area)
    if rv3d is None:
        return None
    m = Vector((mx, my))
    try:   # affichage filaire : l'intérieur des faces est transparent, seules les arêtes se touchent
        wire = area.spaces.active.shading.type == 'WIREFRAME'
    except AttributeError:
        wire = False
    ok, obj, loc, ro, rv = False, None, None, None, None
    try:
        if wire:
            raise ValueError
        ro = region_2d_to_origin_3d(region, rv3d, m)
        rv = region_2d_to_vector_3d(region, rv3d, m)
        dg0 = context.evaluated_depsgraph_get()
        org = ro
        for _ in range(12):     # on traverse ce qui n'est pas sélectionnable (calque verrouillé) ou transparent (filaire, boîte)
            ok, loc, _n, _i, obj, _mat = context.scene.ray_cast(dg0, org, rv)
            if not ok or obj is None:
                break
            try:
                skip = (obj.hide_select or not obj.visible_get() or not type_selectable(area.spaces.active, obj)
                        or obj.display_type in {'WIRE', 'BOUNDS'})
            except (RuntimeError, ReferenceError):
                skip = True
            if not skip:
                break
            org = loc + rv.normalized() * 1e-4
            ok, obj = False, None
    except (RuntimeError, TypeError, ValueError):
        ok, obj = False, None
    if ok and obj is not None:
        try:
            if not obj.hide_select and obj.visible_get() and type_selectable(area.spaces.active, obj):
                try:   # une courbe (sans faces) devant la surface touchée reste prioritaire : le rayon la traverse
                    w = _wire_pick_before(context, area, region, rv3d, mx, my, ro, rv.normalized(), float((loc - ro).dot(rv.normalized())), obj)
                except (RuntimeError, ValueError, AttributeError, TypeError, ReferenceError):
                    w = None
                if w is not None:
                    return w, None
                return obj, loc
        except (RuntimeError, ReferenceError):
            pass
    try:
        dg = context.evaluated_depsgraph_get()
        persp = np.array(rv3d.perspective_matrix, dtype=np.float64)
        r = 6.0 * px_scale()
        rect = (mx - r, my - r, mx + r, my + r)
        for o in objects_near_rect(context.view_layer.objects, persp, region, rect):
            try:
                if o.hide_select or not o.visible_get() or o.type == 'EMPTY' or not type_selectable(area.spaces.active, o):
                    continue
            except RuntimeError:
                continue
            if object_hit_box(o, dg, persp, region, rect, True):
                return o, None
    except (RuntimeError, ValueError, AttributeError):
        pass
    return None


def edge_loop(edge):
    """Arêtes de la « boucle » qui passe par `edge` : on traverse les sommets de valence 4 (face opposée), les
    sommets de valence 2 (fil, contour dessiné) et on suit le bord des maillages ouverts."""
    loop = {edge}
    for start in edge.verts:
        cur_e, v = edge, start
        while True:
            others = [x for x in v.link_edges if x is not cur_e]
            nxt = None
            if len(v.link_edges) == 2:
                nxt = others[0]
            elif len(cur_e.link_faces) == 1:                 # bord : l'autre arête de bord du sommet
                bd = [x for x in others if len(x.link_faces) == 1]
                nxt = bd[0] if len(bd) == 1 else None
            elif len(v.link_edges) == 4 and len(cur_e.link_faces) == 2:
                faces = set(cur_e.link_faces)
                opp = [x for x in others if not (set(x.link_faces) & faces)]
                nxt = opp[0] if len(opp) == 1 else None
            if nxt is None or nxt in loop:
                break
            loop.add(nxt)
            cur_e, v = nxt, nxt.other_vert(v)
    return loop


def pick_edit_edge(context, area, region, mx, my):
    """(objet, arête BMesh) la plus proche de la souris (10 px), la plus proche de la caméra à distance égale."""
    rv3d = region_rv3d(region, area)
    if rv3d is None:
        return None
    persp = np.array(rv3d.perspective_matrix, dtype=np.float64)
    limit = 10.0 * px_scale()
    best = None
    for obj in context.objects_in_mode_unique_data:
        if obj.type != 'MESH':
            continue
        try:
            bm = bmesh.from_edit_mesh(obj.data)
        except ValueError:
            continue
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        if not len(bm.edges) or len(bm.edges) > 300000:
            continue
        mw = np.array(obj.matrix_world, dtype=np.float64)
        co = np.array([tuple(v.co) for v in bm.verts], dtype=np.float64)
        w = co @ mw[:3, :3].T + mw[:3, 3]
        sx, sy, ok = _project_region(w, persp, region)
        clip = np.hstack((w, np.ones((len(w), 1)))) @ persp.T
        zn = clip[:, 2] / np.where(np.abs(clip[:, 3]) > 1e-9, clip[:, 3], 1.0)
        ea = np.array([e.verts[0].index for e in bm.edges], dtype=np.int64)
        eb = np.array([e.verts[1].index for e in bm.edges], dtype=np.int64)
        hid = np.array([e.hide for e in bm.edges], dtype=bool)
        ax, ay, bx, by = sx[ea], sy[ea], sx[eb], sy[eb]
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        t = np.where(L2 > 1e-9, ((mx - ax) * dx + (my - ay) * dy) / np.where(L2 > 1e-9, L2, 1.0), 0.0)
        t = np.clip(t, 0.0, 1.0)
        dist = np.hypot(ax + dx * t - mx, ay + dy * t - my)
        dist = np.where(ok[ea] & ok[eb] & ~hid, dist, np.inf)
        depth = (zn[ea] + zn[eb]) * 0.5
        for i in np.nonzero(dist <= limit)[0]:
            key = (round(float(dist[i]) / 4.0), float(depth[i]))
            if best is None or key < best[0]:
                best = (key, obj, int(i))
    if best is None:
        return None
    return best[1], best[2]      # (objet, indice de l'arête)


class DESSIN_OT_select_loop(bpy.types.Operator):
    bl_idname = "dessin.select_loop"
    bl_label = "Select Loop"
    bl_description = "Double-click an edge to select its whole loop (Shift: add, Ctrl/Cmd: remove)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D' and context.mode == 'EDIT_MESH'

    def invoke(self, context, event):
        region = find_window_region(context.area, event.mouse_x, event.mouse_y)
        if region is None or event.alt or event.oskey:
            return {'CANCELLED', 'PASS_THROUGH'}
        for r in context.area.regions:
            if (r.type in {'TOOLS', 'UI', 'HEADER', 'TOOL_HEADER'} and r.x <= event.mouse_x < r.x + r.width
                    and r.y <= event.mouse_y < r.y + r.height):
                return {'CANCELLED', 'PASS_THROUGH'}
        hit = pick_edit_edge(context, context.area, region, event.mouse_x - region.x, event.mouse_y - region.y)
        if hit is None:
            return {'CANCELLED', 'PASS_THROUGH'}
        obj, index = hit
        return self.select(context, obj, index, event.shift, event.ctrl)

    def select(self, context, obj, index, shift, ctrl):
        bm = bmesh.from_edit_mesh(obj.data)      # on garde cette référence : sinon les arêtes deviennent invalides
        bm.edges.ensure_lookup_table()
        loop = edge_loop(bm.edges[index])
        if not (shift or ctrl):
            for o in context.objects_in_mode_unique_data:
                if o.type == 'MESH':
                    b = bmesh.from_edit_mesh(o.data)
                    for v in b.verts:
                        v.select_set(False)
                    for e in b.edges:
                        e.select_set(False)
                    for f in b.faces:
                        f.select_set(False)
                    if b is not bm:
                        bmesh.update_edit_mesh(o.data, loop_triangles=False, destructive=False)
        for e in loop:
            e.select_set(not ctrl)
        bm.select_flush_mode()
        bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
        return {'FINISHED'}


_SUBOBJ = {"objs": set()}     # objets passés en Édition par Ctrl+Maj+clic (Échap les ramène en mode Objet)


def subobject_hit(context, area, region, mx, my):
    """Ctrl+Maj+clic (Rhino) : élément de maillage sous la souris -> (objet, 'VERT' / 'EDGE' / 'FACE', indice) ou None.
    Sommet à moins de 12 px, sinon arête à moins de 8 px, sinon la face visée. Les indices sont ceux du maillage d'origine
    (la cage d'une SubD, pas la surface lisse)."""
    from mathutils.bvhtree import BVHTree
    from bpy_extras.view3d_utils import location_3d_to_region_2d
    rv3d = region_rv3d(region, area)
    if rv3d is None:
        return None
    coord = Vector((mx, my))
    ro = region_2d_to_origin_3d(region, rv3d, coord)
    rv = region_2d_to_vector_3d(region, rv3d, coord)
    ok, loc, _nor, _idx, obj, _mat = ray_cast_opaque(context, ro, rv, True)
    if not ok or obj is None:
        return None
    obj = getattr(obj, "original", obj)
    if obj.type != 'MESH' or obj.hide_select:
        return None
    if obj.mode == 'EDIT':
        obj.update_from_editmode()
    me = obj.data
    if not me.polygons:
        return None
    mw = obj.matrix_world
    wv = [mw @ v.co for v in me.vertices]
    bvh = BVHTree.FromPolygons(wv, [tuple(p.vertices) for p in me.polygons])
    hit = bvh.ray_cast(ro, rv)
    fi = hit[2] if hit[2] is not None else bvh.find_nearest(loc)[2]
    if fi is None:
        return None
    # sommet, puis arête, les plus proches du curseur parmi TOUT l'objet (pas seulement la face visée), s'ils sont visibles
    r_v, r_e = 12.0 * px_scale(), 8.0 * px_scale()
    P = np.array(rv3d.perspective_matrix, dtype=np.float64)
    W = np.array([tuple(v) for v in wv], dtype=np.float64)
    clip = np.hstack((W, np.ones((len(W), 1)))) @ P.T
    okw = clip[:, 3] > 1e-9
    ws = np.where(okw, clip[:, 3], 1.0)
    sx = (clip[:, 0] / ws * 0.5 + 0.5) * region.width
    sy = (clip[:, 1] / ws * 0.5 + 0.5) * region.height
    dv = np.where(okw, np.hypot(sx - mx, sy - my), np.inf)
    zn = clip[:, 2] / ws                       # profondeur : à distance écran égale (±2 px), le plus proche de la caméra
    q = 2.0 * px_scale()

    def visible_pt(pt):
        sp = location_3d_to_region_2d(region, rv3d, pt)
        if sp is None:
            return False
        o2 = region_2d_to_origin_3d(region, rv3d, sp)
        d = pt - o2
        L = d.length
        if L < 1e-9:
            return True
        ok2, loc2, _n2, _i2, _ob2, _m2 = ray_cast_opaque(context, o2, d / L, True)
        return not ok2 or (loc2 - o2).length >= L - max(1e-4, 2e-3 * L)
    for vi in np.lexsort((zn, np.round(dv / q)))[:8]:
        if dv[vi] > r_v:
            continue
        if visible_pt(wv[int(vi)]):
            return obj, 'VERT', int(vi)
    ne = len(me.edges)
    if ne:
        ed = np.empty(ne * 2, dtype=np.int64)
        me.edges.foreach_get('vertices', ed)
        ed = ed.reshape(-1, 2)
        ax, ay, bx, by = sx[ed[:, 0]], sy[ed[:, 0]], sx[ed[:, 1]], sy[ed[:, 1]]
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        t = np.clip(((mx - ax) * dx + (my - ay) * dy) / np.where(L2 > 1e-12, L2, 1.0), 0.0, 1.0)
        de = np.hypot(ax + dx * t - mx, ay + dy * t - my)
        de = np.where(okw[ed[:, 0]] & okw[ed[:, 1]], de, np.inf)
        ze = (zn[ed[:, 0]] + zn[ed[:, 1]]) * 0.5
        for ei in np.lexsort((ze, np.round(de / q)))[:8]:
            if de[ei] > r_e:
                continue
            a_, b_ = ed[int(ei)]
            pt = wv[int(a_)] + (wv[int(b_)] - wv[int(a_)]) * float(t[ei])
            if visible_pt(pt):
                return obj, 'EDGE', int(ei)
    return obj, 'FACE', fi


SUBOBJ_OCCLUSION_MAX = 40000      # au-delà de ce nombre de sommets dans la zone, on ne teste plus leur visibilité (trop long)


def subobject_box(context, area, region, inside_fn):
    """Ctrl+Maj + zone (Rhino) : les sommets visibles de TOUS les objets maillage touchés par la zone sont sélectionnés,
    et ces objets passent en Édition. Retourne le nombre de sommets sélectionnés."""
    from mathutils.bvhtree import BVHTree
    rv3d = region_rv3d(region, area)
    if rv3d is None:
        return 0
    persp = np.array(rv3d.perspective_matrix, dtype=np.float64)
    space = area.spaces.active
    xray = bool(getattr(getattr(space, "shading", None), "show_xray", False)) if space is not None else False
    vm = np.array(rv3d.view_matrix.inverted(), dtype=np.float64)
    if rv3d.is_perspective:
        eye = vm[:3, 3]
        ortho_dir = None
    else:
        eye = None
        ortho_dir = -vm[:3, 2] / max(np.linalg.norm(vm[:3, 2]), 1e-12)
    cand = []          # (objet, indices dans la zone, positions monde)
    bvhs = []
    for obj in context.view_layer.objects:
        try:
            if obj.type not in {'MESH', 'CURVE'} or obj.hide_select or not obj.visible_get() or not type_selectable(space, obj):
                continue
        except RuntimeError:
            continue
        if obj.type == 'CURVE':        # courbes : points de contrôle (Bézier : le point, ses poignées le suivent)
            refs, pts = [], []
            for si, sp in enumerate(obj.data.splines):
                if sp.type == 'BEZIER':
                    for pi, bp in enumerate(sp.bezier_points):
                        refs.append((si, pi, True))
                        pts.append(tuple(bp.co))
                else:
                    for pi, pt in enumerate(sp.points):
                        refs.append((si, pi, False))
                        pts.append(tuple(pt.co)[:3])
            if not pts:
                continue
            mw = np.array(obj.matrix_world, dtype=np.float64)
            Wc = np.array(pts, dtype=np.float64) @ mw[:3, :3].T + mw[:3, 3]
            sx, sy, ok = _project_region(Wc, persp, region)
            inside = np.nonzero(ok & inside_fn(sx, sy))[0]
            if len(inside):
                cand.append((obj, inside, Wc, refs))
            continue
        if obj.mode == 'EDIT':
            try:
                obj.update_from_editmode()
            except (RuntimeError, AttributeError):
                pass
        me = obj.data
        nv = len(me.vertices)
        if nv == 0 or nv > 300000:
            continue
        co = np.empty(nv * 3, dtype=np.float32)
        me.vertices.foreach_get('co', co)
        mw = np.array(obj.matrix_world, dtype=np.float64)
        W = co.reshape(-1, 3).astype(np.float64) @ mw[:3, :3].T + mw[:3, 3]
        sx, sy, ok = _project_region(W, persp, region)
        inside = np.nonzero(ok & inside_fn(sx, sy))[0]
        if len(me.polygons) and not xray:
            tri = [tuple(pg.vertices) for pg in me.polygons]
            bvhs.append(BVHTree.FromPolygons([tuple(v) for v in W], tri))
        if len(inside):
            cand.append((obj, inside, W, None))
    if not cand:
        return 0
    total = sum(len(c[1]) for c in cand)
    hits = {}
    for obj, inside, W, refs in cand:
        keep = inside
        if bvhs and total <= SUBOBJ_OCCLUSION_MAX:       # un sommet caché derrière une face n'est pas pris (sauf en mode X-ray)
            vis = []
            for i in inside:
                P = Vector(W[int(i)])
                if eye is not None:
                    d = P - Vector(eye)
                    L = d.length
                    if L < 1e-9:
                        vis.append(i)
                        continue
                    o, dv = Vector(eye), d / L
                else:
                    dv = Vector(ortho_dir)
                    L = 1.0e4
                    o = P - dv * L
                tol = max(1e-4, 2e-3 * L)
                blocked = False
                for b in bvhs:
                    h = b.ray_cast(o, dv, L)
                    if h[0] is not None and h[3] < L - tol:
                        blocked = True
                        break
                if not blocked:
                    vis.append(i)
            keep = np.array(vis, dtype=np.int64)
        if len(keep):
            hits[obj.name] = (obj, keep, refs)
    if not hits:
        return 0
    # maillages et courbes ne s'éditent pas ensemble : on garde le type qui a le plus de points dans la zone
    npts = {'MESH': 0, 'CURVE': 0}
    for h in hits.values():
        npts[h[0].type] += len(h[1])
    kind = 'CURVE' if npts['CURVE'] > npts['MESH'] else 'MESH'
    hits = {k: h for k, h in hits.items() if h[0].type == kind}
    editmode = 'EDIT_CURVE' if kind == 'CURVE' else 'EDIT_MESH'
    vl = context.view_layer
    edited = {o.name for o in context.objects_in_mode_unique_data} if context.mode == editmode else set()
    objs = [h[0] for h in hits.values()]
    if context.mode == 'OBJECT' or not all(o.name in edited for o in objs):
        keep_edit = [vl.objects[n] for n in edited if n in vl.objects]
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        else:
            for o in context.selected_objects:
                o.select_set(False)
        for o in keep_edit + objs:
            o.select_set(True)
        vl.objects.active = objs[0]
        bpy.ops.object.mode_set(mode='EDIT')
        _SUBOBJ["objs"] = {o.name for o in keep_edit + objs}
        try:
            bpy.ops.wm.tool_set_by_id(name=IDLE_TOOL)
        except (RuntimeError, TypeError):
            pass
        fresh = not keep_edit
    else:
        fresh = False
    ts = context.tool_settings
    n = 0
    if kind == 'CURVE':
        for obj, idx, refs in hits.values():
            if fresh:
                for sp in obj.data.splines:
                    for bp in sp.bezier_points:
                        bp.select_control_point = bp.select_left_handle = bp.select_right_handle = False
                    for pt in sp.points:
                        pt.select = False
            for i in idx:
                si, pi, bez = refs[int(i)]
                sp = obj.data.splines[si]
                if bez:
                    bp = sp.bezier_points[pi]
                    bp.select_control_point = bp.select_left_handle = bp.select_right_handle = True
                else:
                    sp.points[pi].select = True
                n += 1
            obj.update_tag()
        return n
    ts.mesh_select_mode = (True, False, False)
    for obj, idx, _refs in hits.values():
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        if fresh:
            for e in list(bm.verts) + list(bm.edges) + list(bm.faces):
                e.select = False
        for i in idx:
            if int(i) < len(bm.verts) and not bm.verts[int(i)].hide:
                bm.verts[int(i)].select_set(True)
                n += 1
        bm.select_flush_mode()
        bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
    return n


def subobject_apply(context, obj, kind, index):
    """Ajoute l'élément à la sélection, en passant l'objet en Édition si besoin."""
    vl = context.view_layer
    entering = context.mode == 'OBJECT'
    if entering:
        for o in context.selected_objects:
            o.select_set(False)
        obj.select_set(True)
        vl.objects.active = obj
        bpy.ops.object.mode_set(mode='EDIT')
        _SUBOBJ["objs"] = {obj.name}
        try:      # en Édition, l'outil actif est propre au mode : on y met Select de Wanderer (sinon ⌘/Ctrl+Maj+clic = chemin le plus court de Blender)
            bpy.ops.wm.tool_set_by_id(name=IDLE_TOOL)
        except (RuntimeError, TypeError):
            pass
    elif obj.mode != 'EDIT':
        bpy.ops.object.mode_set(mode='OBJECT')      # un autre objet : on l'ajoute à l'édition multi-objets
        obj.select_set(True)
        vl.objects.active = obj
        bpy.ops.object.mode_set(mode='EDIT')
        if _SUBOBJ["objs"]:
            _SUBOBJ["objs"].add(obj.name)
    ts = context.tool_settings
    k = {'VERT': 0, 'EDGE': 1, 'FACE': 2}[kind]
    mode = [False, False, False] if entering else list(ts.mesh_select_mode)
    mode[k] = True
    ts.mesh_select_mode = mode
    bm = bmesh.from_edit_mesh(obj.data)
    seq = (bm.verts, bm.edges, bm.faces)[k]
    seq.ensure_lookup_table()
    if entering:
        for e in list(bm.verts) + list(bm.edges) + list(bm.faces):
            e.select = False
    if index >= len(seq):
        return False
    el = seq[index]
    el.select_set(True)            # comme Rhino : Ctrl+Maj ajoute toujours ; Ctrl+clic retire
    bm.select_history.discard(el)
    bm.select_history.add(el)
    bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
    return True


def pick_edit_element(context, area, region, mx, my):
    """Mode édition : élément sous la souris à saisir pour le déplacer.
    Retourne (objet, sélectionné ?, indice du sommet si c'est un sommet, point monde d'ancrage) ou None.
    Sommet (sélectionné ou non) à moins de 10 px, sinon arête sélectionnée, sinon face sélectionnée."""
    rv3d = region_rv3d(region, area)
    if rv3d is None:
        return None
    persp = np.array(rv3d.perspective_matrix, dtype=np.float64)
    r = 10.0 * px_scale()
    best = None
    cache = []
    for obj in context.objects_in_mode_unique_data:
        if obj.type != 'MESH':
            continue
        try:
            bm = bmesh.from_edit_mesh(obj.data)
        except ValueError:
            continue
        bm.verts.ensure_lookup_table()
        n = len(bm.verts)
        if n == 0 or n > 300000:
            continue
        mw = np.array(obj.matrix_world, dtype=np.float64)
        co = np.array([tuple(v.co) for v in bm.verts], dtype=np.float64)
        w = co @ mw[:3, :3].T + mw[:3, 3]
        sx, sy, ok = _project_region(w, persp, region)
        d = np.hypot(sx - mx, sy - my)
        hid = np.array([v.hide for v in bm.verts], dtype=bool)
        d = np.where(ok & ~hid, d, np.inf)
        clip = np.hstack((w, np.ones((len(w), 1)))) @ persp.T
        zn = clip[:, 2] / np.where(np.abs(clip[:, 3]) > 1e-9, clip[:, 3], 1.0)    # profondeur : plus petit = plus près
        cache.append((obj, bm, w, sx, sy, ok))
        for i in np.nonzero(d <= r)[0]:
            key = (round(float(d[i]) / 4.0), float(zn[i]))     # à peu près même distance écran : le plus proche de la caméra
            if best is None or key < best[0]:
                best = (key, obj, bool(bm.verts[int(i)].select), int(i), Vector(w[i]))
    if best is not None:
        return best[1], best[2], best[3], best[4]
    for obj, bm, w, sx, sy, ok in cache:       # arête sélectionnée proche
        bm.edges.ensure_lookup_table()
        for e in bm.edges:
            if not e.select or e.hide:
                continue
            a, b = e.verts[0].index, e.verts[1].index
            if not (ok[a] and ok[b]):
                continue
            ax, ay, bx, by = sx[a], sy[a], sx[b], sy[b]
            dx, dy = bx - ax, by - ay
            L2 = dx * dx + dy * dy
            t = 0.0 if L2 < 1e-9 else max(0.0, min(1.0, ((mx - ax) * dx + (my - ay) * dy) / L2))
            if math.hypot(ax + dx * t - mx, ay + dy * t - my) <= 8.0 * px_scale():
                return obj, True, None, Vector(w[a] if t < 0.5 else w[b])
    for obj, bm, w, sx, sy, ok in cache:       # face sélectionnée sous la souris
        bm.faces.ensure_lookup_table()
        count = 0
        for f in bm.faces:
            if not f.select or f.hide:
                continue
            count += 1
            if count > 5000:
                break
            idx = [v.index for v in f.verts]
            if not all(ok[i] for i in idx):
                continue
            inside = False
            j = len(idx) - 1
            for k in range(len(idx)):
                xi, yi, xj, yj = sx[idx[k]], sy[idx[k]], sx[idx[j]], sy[idx[j]]
                if (yi > my) != (yj > my) and mx < (xj - xi) * (my - yi) / (yj - yi + 1e-12) + xi:
                    inside = not inside
                j = k
            if inside:
                near = min(idx, key=lambda i: math.hypot(sx[i] - mx, sy[i] - my))
                return obj, True, None, Vector(w[near])
    return None


class DESSIN_OT_deselect(bpy.types.Operator):
    bl_idname = "dessin.deselect"
    bl_label = "Deselect All"
    bl_description = "Deselects everything (Esc with the Select tool)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (context.area is not None and context.area.type == 'VIEW_3D' and context.mode in {'OBJECT', 'EDIT_MESH', 'EDIT_CURVE', 'EDIT_SURFACE'}
                and pref("esc_deselect"))

    def execute(self, context):
        try:
            deselect_current_mode(context)
        except RuntimeError:
            return {'CANCELLED'}
        return {'FINISHED'}


def deselect_current_mode(context):
    """Désélectionne tout dans le mode courant (objets, sommets de maillage, points de courbe)."""
    mode = context.mode
    if mode in {'EDIT_MESH', 'EDIT_CURVE'} and _SUBOBJ["objs"]:
        _SUBOBJ["objs"] = set()              # sélection de sous-objets (Ctrl+Maj+clic) : Échap revient en mode Objet, comme Rhino
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
    elif mode == 'EDIT_MESH':
        bpy.ops.mesh.select_all(action='DESELECT')
    elif mode in {'EDIT_CURVE', 'EDIT_SURFACE'}:
        bpy.ops.curve.select_all(action='DESELECT')
    elif mode == 'OBJECT':
        bpy.ops.object.select_all(action='DESELECT')


class DESSIN_OT_esc_select(bpy.types.Operator):
    """Échap dans la vue 3D, sans commande en cours : retour à l'outil Select et désélection (objets ou éléments en édition)."""
    bl_idname = "dessin.esc_select"
    bl_label = "Back to Select"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return (context.area is not None and context.area.type == 'VIEW_3D'
                and context.mode in {'OBJECT', 'EDIT_MESH', 'EDIT_CURVE', 'EDIT_SURFACE'})

    def invoke(self, context, event):
        if _CMD["op"].get(context.area.as_pointer()) is not None or _CMD["input"] is not None:
            return {'PASS_THROUGH'}          # une commande (ou la ligne de commande) gère elle-même Échap
        if not (pref("auto_idle") or pref("esc_deselect")):
            return {'PASS_THROUGH'}
        if pref("auto_idle") and DessinBase.active_tool_id(context) != IDLE_TOOL:
            back_to_idle()
        if pref("esc_deselect"):
            try:
                deselect_current_mode(context)
            except RuntimeError:
                pass
        return {'FINISHED'}


def select_edit_shape(context, area, region, inside_fn, seg_fn, crossing, event):
    """Sélection en mode édition par une forme écran (boîte, lasso) : sommets, arêtes ou faces selon le mode."""
    rv3d = region_rv3d(region, area)
    persp = np.array(rv3d.perspective_matrix, dtype=np.float64)
    vmode, emode, fmode = context.tool_settings.mesh_select_mode
    replace = not (event.shift or event.ctrl)
    value = not event.ctrl
    for obj in context.objects_in_mode_unique_data:
        if obj.type != 'MESH':
            continue
        try:
            bm = bmesh.from_edit_mesh(obj.data)
        except ValueError:
            continue
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        if not len(bm.verts):
            continue
        mw = np.array(obj.matrix_world, dtype=np.float64)
        co = np.array([tuple(v.co) for v in bm.verts], dtype=np.float64)
        sx, sy, ok = _project_region(co @ mw[:3, :3].T + mw[:3, 3], persp, region)
        inside = ok & inside_fn(sx, sy)
        if replace:
            for v in bm.verts:
                v.select_set(False)
        if vmode:
            for i in np.nonzero(inside)[0]:
                v = bm.verts[int(i)]
                if not v.hide:
                    v.select_set(value)
        else:
            ne = len(bm.edges)
            ea = np.array([e.verts[0].index for e in bm.edges], dtype=np.int64) if ne else np.zeros(0, dtype=np.int64)
            eb = np.array([e.verts[1].index for e in bm.edges], dtype=np.int64) if ne else np.zeros(0, dtype=np.int64)
            if crossing and ne:
                hit_e = inside[ea] | inside[eb]
                both = ok[ea] & ok[eb]
                if both.any():
                    h = np.zeros(ne, dtype=bool)
                    h[both] = seg_fn(sx[ea[both]], sy[ea[both]], sx[eb[both]], sy[eb[both]])
                    hit_e |= h
            else:
                hit_e = inside[ea] & inside[eb] if ne else np.zeros(0, dtype=bool)
            if emode:
                for i in np.nonzero(hit_e)[0]:
                    e = bm.edges[int(i)]
                    if not e.hide:
                        e.select_set(value)
            else:
                for f in bm.faces:
                    if f.hide:
                        continue
                    if crossing:
                        hit = any(inside[v.index] for v in f.verts) or any(hit_e[e.index] for e in f.edges)
                    else:
                        hit = all(inside[v.index] for v in f.verts)
                    if hit:
                        f.select_set(value)
        bm.select_flush_mode()
        bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)


def select_objects_shape(context, area, region, inside_fn, seg_fn, crossing, event, rect=None):
    """Sélection d'objets par une forme écran (boîte, lasso) : Maj ajoute, Ctrl retire."""
    rv3d = region_rv3d(region, area)
    persp = np.array(rv3d.perspective_matrix, dtype=np.float64)
    dg = bpy.context.evaluated_depsgraph_get()
    hit = []
    space = area.spaces.active
    for obj in context.view_layer.objects:
        try:
            if obj.hide_select or not obj.visible_get() or not type_selectable(space, obj):
                continue
        except RuntimeError:
            continue
        if rect is not None:     # boîte : test rapide sur la boîte englobante avant la géométrie
            q = bbox_vs_rect(obj, persp, region, rect, 0.0)
            if q == 'out':
                continue
            if q == 'in':
                hit.append(obj)
                continue
        if object_hit_shape(obj, dg, persp, region, inside_fn, seg_fn, crossing):
            hit.append(obj)
    if not (event.shift or event.ctrl):
        for obj in context.view_layer.objects:
            try:
                if obj.select_get() and obj not in hit:
                    obj.select_set(False)
            except RuntimeError:
                pass
    for obj in hit:
        try:
            obj.select_set(not event.ctrl)
        except RuntimeError:
            pass
    if hit and not event.ctrl and context.view_layer.objects.active not in hit:
        context.view_layer.objects.active = hit[0]
    if _SF["solo"] is not None:
        sel_filter_restore(context)     # « seulement ce type » : valable pour une sélection, même si elle n'a rien trouvé


class DESSIN_OT_selection_boite(bpy.types.Operator):
    bl_idname = "dessin.selection_boite"
    bl_label = "Select"
    bl_description = ("Click to select, drag an empty area for a box (left to right = fully inside, right to left = touched; "
                      "Shift: add, Ctrl/Cmd: remove), drag an object to move it in the view plane. "
                      "Ctrl/Cmd+Shift+drag: enters Edit Mode with the visible vertices of every object in the area selected")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (context.area is not None and context.area.type == 'VIEW_3D'
                and context.mode in {'OBJECT', 'EDIT_MESH'})

    def invoke(self, context, event):
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS' and context.area is not None and cmd_click_idle(context, event):
            return {'CANCELLED'}
        self.area = context.area
        self.region = find_window_region(self.area, event.mouse_x, event.mouse_y)
        if self.region is None:
            return {'CANCELLED', 'PASS_THROUGH'}
        space = self.area.spaces.active
        for r in self.area.regions:  # clic sur la barre d'outils / latérale : pas pour nous
            if (r.type in {'TOOLS', 'UI', 'HEADER', 'TOOL_HEADER'} and r.x <= event.mouse_x < r.x + r.width
                    and r.y <= event.mouse_y < r.y + r.height):
                return {'CANCELLED', 'PASS_THROUGH'}
        if over_nav_gizmo(self.area, event.mouse_x, event.mouse_y):
            return {'CANCELLED', 'PASS_THROUGH'}
        if event.oskey or (event.alt and pref("view_button") == 'ALT_LEFT'):
            return {'CANCELLED', 'PASS_THROUGH'}
        self.start = (event.mouse_x - self.region.x, event.mouse_y - self.region.y)
        self.start_abs = (event.mouse_x, event.mouse_y)
        self.sub = bool(event.ctrl and event.shift and not event.alt)      # Ctrl+Maj + zone : sommets (Rhino)
        if event.alt and not (event.shift or event.ctrl):
            # Alt + poignée du Gumball : on lance nous-mêmes la transformation (avec copie)
            try:
                with context.temp_override(area=self.area, region=self.region):
                    handle = gumball_handle_at(context, self.start[0], self.start[1], self.region,
                                               region_rv3d(self.region, self.area))
                    if handle is not None:
                        bpy.ops.dessin.gumball('INVOKE_DEFAULT', kind=handle[0], axis=handle[1])
                        return {'FINISHED'}
            except (RuntimeError, TypeError, AttributeError):
                pass
        if context.mode == 'EDIT_MESH' and not (event.shift or event.ctrl or event.alt):
            try:
                with context.temp_override(area=self.area, region=self.region):
                    on_ball = extrude_ball_hit(context, self.start[0], self.start[1], self.region, region_rv3d(self.region, self.area))
                    if on_ball:
                        bpy.ops.dessin.gumball_extrude('INVOKE_DEFAULT')
                        return {'FINISHED'}
            except (RuntimeError, TypeError, AttributeError):
                pass
        self.box = None
        self.dragged = False
        self.moving = False
        self.grab = None
        self.copy_flag = bool(event.alt)      # Alt maintenu pendant le déplacement : on déplace une copie
        self.edit_mode = context.mode == 'EDIT_MESH'
        if not (event.shift or event.ctrl):
            if context.mode == 'OBJECT':
                self.grab = pick_object_at(context, self.area, self.region, self.start[0], self.start[1])
            elif self.edit_mode:
                try:
                    self.grab = pick_edit_element(context, self.area, self.region, self.start[0], self.start[1])
                except (RuntimeError, ReferenceError, ValueError):
                    self.grab = None
        try:   # lignes de construction (Xline) et repères Divide : ils se sélectionnent d'un clic mais ne captent pas le glisser
            if self.grab is not None and not self.edit_mode and self.grab[0].get("cad_noGrab"):
                self.grab = None
        except (TypeError, AttributeError, IndexError, ReferenceError):
            pass
        if event.alt and self.grab is None:
            return {'CANCELLED', 'PASS_THROUGH'}     # Alt hors d'un objet : on laisse Blender / la navigation
        self._h = bpy.types.SpaceView3D.draw_handler_add(draw_box_cb, (self,), 'WINDOW', 'POST_PIXEL')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def cleanup(self):
        ghost_hide()
        if getattr(self, "_h", None) is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._h, 'WINDOW')
            self._h = None
        try:
            self.area.tag_redraw()
        except ReferenceError:
            pass

    # ---- déplacement libre (comme l'outil Tweak) : glisser un objet = le déplacer dans le plan de la vue ----
    def plane_point(self, context, cx, cy):
        rv3d = region_rv3d(self.region, self.area)
        m = Vector((cx, cy))
        ro = region_2d_to_origin_3d(self.region, rv3d, m)
        rv = region_2d_to_vector_3d(self.region, rv3d, m)
        n = rv3d.view_rotation @ Vector((0.0, 0.0, -1.0))
        return geometry.intersect_line_plane(ro, ro + rv, self.plane_o, n)

    def begin_move(self, context):
        obj, hit = self.grab
        if not obj.select_get():
            for o in context.view_layer.objects:
                try:
                    if o.select_get():
                        o.select_set(False)
                except RuntimeError:
                    pass
            obj.select_set(True)
        context.view_layer.objects.active = obj
        pivot, top = gumball_selection(context)
        if not top:
            return False
        self.mv_items = [(o, o.matrix_world.copy()) for o in top]
        self.plane_o = hit if hit is not None else obj.matrix_world.translation.copy()
        p0 = self.plane_point(context, self.start[0], self.start[1])
        if p0 is None:
            return False
        self.p0 = p0
        self.moving = True
        return True

    def begin_move_edit(self, context):
        obj, selected, vidx, anchor = self.grab
        if not selected and vidx is not None:        # sommet non sélectionné : il devient la sélection
            for o in context.objects_in_mode_unique_data:
                if o.type == 'MESH':
                    bm = bmesh.from_edit_mesh(o.data)
                    for v in bm.verts:
                        v.select_set(False)
                    bm.select_flush_mode()
            bm = bmesh.from_edit_mesh(obj.data)
            bm.verts.ensure_lookup_table()
            bm.verts[vidx].select_set(True)
            bm.select_flush_mode()
            bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
        self.items = edit_selection(context)
        if not self.items:
            return False
        self.plane_o = anchor
        p0 = self.plane_point(context, self.start[0], self.start[1])
        if p0 is None:
            return False
        self.p0 = p0
        self.moving = True
        return True

    def edit_translate(self, d):
        Xn = np.array(Matrix.Translation(d), dtype=np.float64)
        for obj, idx, w0 in self.items:
            try:
                bm = bmesh.from_edit_mesh(obj.data)
            except (ValueError, ReferenceError):
                continue
            bm.verts.ensure_lookup_table()
            M = np.linalg.inv(np.array(obj.matrix_world, dtype=np.float64)) @ Xn
            h = np.hstack((w0, np.ones((len(w0), 1)))) @ M.T
            for i, p in zip(idx, h):
                bm.verts[i].co = Vector((p[0], p[1], p[2]))
            bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=False)

    def move_header(self, d):
        tag = "Copy" if getattr(self, "copy_flag", False) else "Move"
        return (f"{tag}: {d.x:.3f}, {d.y:.3f}, {d.z:.3f}   |   Alt: copy   Shift: keep dominant axis   Esc: cancel")

    def move_to(self, context, cx, cy, shift):
        p = self.plane_point(context, cx, cy)
        if p is None:
            return
        d = p - self.p0
        if shift:                       # Maj : on garde l'axe dominant
            a = max(range(3), key=lambda i: abs(d[i]))
            d = AXES3[a] * d[a]
        if self.edit_mode:
            self.edit_translate(d)
            self.move_delta = d
            try:
                set_prompt(self.area, self.move_header(d))
            except ReferenceError:
                pass
            return
        T = Matrix.Translation(d)
        for o, mw in self.mv_items:
            try:
                o.matrix_world = T @ mw
            except ReferenceError:
                pass
        self.move_delta = d
        try:
            set_prompt(self.area, self.move_header(d))
        except ReferenceError:
            pass

    def cancel_move(self, context):
        if self.edit_mode:
            self.edit_translate(Vector((0.0, 0.0, 0.0)))
            return
        for o, mw in self.mv_items:
            try:
                o.matrix_world = mw
            except ReferenceError:
                pass

    def end_ui(self):
        ghost_hide()
        try:
            set_prompt(self.area, None)
        except ReferenceError:
            pass

    def update_ghost(self, context):
        """Pendant une copie (Alt), la position d'origine reste visible en transparence."""
        if not self.moving or not getattr(self, "copy_flag", False):
            ghost_hide()
            return
        if getattr(self, "_ghost", None) is None:
            self._ghost = ghost_for_edit(self.items) if self.edit_mode else ghost_for_objects(self.mv_items)
        ghost_show(self.area, self._ghost)

    def modal(self, context, event):
        if event.type in {'LEFT_ALT', 'RIGHT_ALT'}:
            self.copy_flag = event.value == 'PRESS'
            if self.moving:
                self.move_to(context, event.mouse_x - self.region.x, event.mouse_y - self.region.y, event.shift)
                self.update_ghost(context)
            return {'RUNNING_MODAL'}
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            if self.moving:
                self.cancel_move(context)
                self.end_ui()
            self.cleanup()
            return {'CANCELLED'}
        if event.type == 'MOUSEMOVE':
            self.copy_flag = bool(event.alt)
            cx, cy = event.mouse_x - self.region.x, event.mouse_y - self.region.y
            if not self.dragged and math.hypot(cx - self.start[0], cy - self.start[1]) > 5.0 * px_scale():
                self.dragged = True
                if self.grab is not None:
                    ok = self.begin_move_edit(context) if self.edit_mode else self.begin_move(context)
                    if not ok:
                        self.grab = None
            if self.dragged:
                if self.moving:
                    self.move_to(context, cx, cy, event.shift)
                    self.update_ghost(context)
                    redraw_region(self)
                else:
                    self.box = (self.start[0], self.start[1], cx, cy)
                    redraw_region(self)
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            self.cleanup()
            if self.moving:
                if self.copy_flag or event.alt:
                    if self.edit_mode:
                        copy_moved_edit(self.items)
                    else:
                        copy_moved_objects(context, self.mv_items)
                self.end_ui()
                return {'FINISHED'}
            if self.dragged:
                cx, cy = event.mouse_x - self.region.x, event.mouse_y - self.region.y
                self.select_box(context, (self.start[0], self.start[1], cx, cy), event)
            else:
                self.select_click(context, event)
            return {'FINISHED'}
        return {'RUNNING_MODAL'}

    def select_click(self, context, event):
        if event.ctrl and event.shift and not event.alt:
            # Rhino : Ctrl+Maj+clic sélectionne un sommet, une arête ou une face (sous-objet) sans passer par Tab
            try:
                with context.temp_override(area=self.area, region=self.region):
                    hit = subobject_hit(context, self.area, self.region, self.start[0], self.start[1])
                    if hit is not None:
                        subobject_apply(context, *hit)
            except (RuntimeError, ReferenceError, ValueError, TypeError):
                pass
            return
        try:
            with context.temp_override(area=self.area, region=self.region):
                bpy.ops.view3d.select(location=self.start_int(),
                                      toggle=event.shift and not event.ctrl,
                                      deselect=event.ctrl,
                                      deselect_all=not (event.shift or event.ctrl))
        except (RuntimeError, TypeError):
            pass
        if _SF["solo"] is not None and context.mode == 'OBJECT':
            sel_filter_restore(context)

    def start_int(self):
        return (int(self.start[0]), int(self.start[1]))

    def sub_select(self, context, inside_fn):
        try:
            with context.temp_override(area=self.area, region=self.region):
                n = subobject_box(context, self.area, self.region, inside_fn)
            if n:
                self.report({'INFO'}, f"{n} points selected (Esc: back to Object mode)")
        except (RuntimeError, ReferenceError, ValueError, TypeError):
            pass

    def select_box_edit(self, context, rect, crossing, event):
        xmin, ymin, xmax, ymax = rect
        select_edit_shape(context, self.area, self.region,
                          lambda sx, sy: (sx >= xmin) & (sx <= xmax) & (sy >= ymin) & (sy <= ymax),
                          lambda ax, ay, bx, by: _segments_hit_rect(ax, ay, bx, by, xmin, ymin, xmax, ymax),
                          crossing, event)

    def select_box(self, context, box, event):
        x0, y0, x1, y1 = box
        crossing = x1 < x0
        rect = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
        if getattr(self, "sub", False):
            xmin, ymin, xmax, ymax = rect
            self.sub_select(context, lambda sx, sy: (sx >= xmin) & (sx <= xmax) & (sy >= ymin) & (sy <= ymax))
            return
        if context.mode == 'EDIT_MESH':
            self.select_box_edit(context, rect, crossing, event)
            return
        xmin, ymin, xmax, ymax = rect
        select_objects_shape(context, self.area, self.region,
                             lambda sx, sy: (sx >= xmin) & (sx <= xmax) & (sy >= ymin) & (sy <= ymax),
                             lambda ax, ay, bx, by: _segments_hit_rect(ax, ay, bx, by, xmin, ymin, xmax, ymax),
                             crossing, event, rect)


def draw_lasso_cb(op):
    if not _same_region(op) or not getattr(op, "dragged", False) or len(op.pts) < 2:
        return
    crossing = bool(op.crossing)
    col = BOX_ORANGE if crossing else BOX_BLUE
    shader = get_shader('2D')
    gpu.state.blend_set('ALPHA')
    shader.bind()
    pts = [tuple(p) for p in op.pts]
    segs = []
    if crossing:   # pointillé pour la capture, comme la boîte
        for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1]):
            ln = math.hypot(bx - ax, by - ay)
            for i in range(int(ln // 12) + 1):
                k0, k1 = i * 12 / max(ln, 1e-6), min(i * 12 + 7, ln) / max(ln, 1e-6)
                segs += [(ax + (bx - ax) * k0, ay + (by - ay) * k0), (ax + (bx - ax) * k1, ay + (by - ay) * k1)]
    else:
        for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1]):
            segs += [(ax, ay), (bx, by)]
    gpu.state.line_width_set(1.5)
    shader.uniform_float("color", (col[0], col[1], col[2], 1.0))
    batch_for_shader(shader, 'LINES', {"pos": segs}).draw(shader)
    gpu.state.line_width_set(1.0)
    gpu.state.blend_set('NONE')


class _SelShapeBase:
    """Base commune (non enregistrée) du Lasso et de Select Box : un opérateur enregistré ne doit jamais hériter d'un autre."""

    @classmethod
    def poll(cls, context):
        return (context.area is not None and context.area.type == 'VIEW_3D'
                and context.mode in {'OBJECT', 'EDIT_MESH'})

    def invoke(self, context, event):
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS' and context.area is not None and cmd_click_idle(context, event):
            return {'CANCELLED'}
        self.area = context.area
        self.region = find_window_region(self.area, event.mouse_x, event.mouse_y)
        if self.region is None:
            return {'CANCELLED', 'PASS_THROUGH'}
        for r in self.area.regions:  # clic sur la barre d'outils / latérale : pas pour nous
            if (r.type in {'TOOLS', 'UI', 'HEADER', 'TOOL_HEADER'} and r.x <= event.mouse_x < r.x + r.width
                    and r.y <= event.mouse_y < r.y + r.height):
                return {'CANCELLED', 'PASS_THROUGH'}
        if over_nav_gizmo(self.area, event.mouse_x, event.mouse_y):
            return {'CANCELLED', 'PASS_THROUGH'}
        if event.alt or event.oskey:
            return {'CANCELLED', 'PASS_THROUGH'}
        self.start = (event.mouse_x - self.region.x, event.mouse_y - self.region.y)
        self.sub = bool(event.ctrl and event.shift and not event.alt)
        if context.mode == 'EDIT_MESH' and not (event.shift or event.ctrl or event.alt):
            try:
                with context.temp_override(area=self.area, region=self.region):
                    if extrude_ball_hit(context, self.start[0], self.start[1], self.region, region_rv3d(self.region, self.area)):
                        bpy.ops.dessin.gumball_extrude('INVOKE_DEFAULT')
                        return {'FINISHED'}
            except (RuntimeError, TypeError, AttributeError):
                pass
        self.pts = [self.start]
        self.dragged = False
        self.crossing = False
        self._h = bpy.types.SpaceView3D.draw_handler_add(draw_lasso_cb, (self,), 'WINDOW', 'POST_PIXEL')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def cleanup(self):
        if getattr(self, "_h", None) is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._h, 'WINDOW')
            self._h = None
        try:
            self.area.tag_redraw()
        except ReferenceError:
            pass

    def modal(self, context, event):
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self.cleanup()
            return {'CANCELLED'}
        if event.type == 'MOUSEMOVE':
            cx, cy = event.mouse_x - self.region.x, event.mouse_y - self.region.y
            if not self.dragged and math.hypot(cx - self.start[0], cy - self.start[1]) > 5.0 * px_scale():
                self.dragged = True
                self.crossing = cx < self.start[0]       # comme AutoCAD : le sens du premier geste décide
            if self.dragged:
                lx, ly = self.pts[-1]
                if math.hypot(cx - lx, cy - ly) >= 3.0 * px_scale():
                    self.pts.append((cx, cy))
                redraw_region(self)
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            self.cleanup()
            if self.dragged and len(self.pts) >= 3:
                self.select_lasso(context, event)
            elif not self.dragged:
                self.select_click(context, event)
            return {'FINISHED'}
        return {'RUNNING_MODAL'}

    select_click = DESSIN_OT_selection_boite.select_click
    start_int = DESSIN_OT_selection_boite.start_int
    sub_select = DESSIN_OT_selection_boite.sub_select

    def select_lasso(self, context, event):
        poly = np.array(self.pts, dtype=np.float64)
        inside_fn = lambda sx, sy: points_in_poly(sx, sy, poly)
        if getattr(self, "sub", False):
            self.sub_select(context, inside_fn)
            return
        seg_fn = lambda ax, ay, bx, by: segments_hit_poly(ax, ay, bx, by, poly)
        if context.mode == 'EDIT_MESH':
            select_edit_shape(context, self.area, self.region, inside_fn, seg_fn, self.crossing, event)
        else:
            select_objects_shape(context, self.area, self.region, inside_fn, seg_fn, self.crossing, event)


class DESSIN_OT_selection_lasso(_SelShapeBase, bpy.types.Operator):
    bl_idname = "dessin.selection_lasso"
    bl_label = "Lasso Select"
    bl_description = ("Drag a free-hand loop to select (drag to the right first: objects fully inside, to the left first: objects touched; "
                      "Shift: add, Ctrl/Cmd: remove). A simple click selects one object")
    bl_options = {'REGISTER', 'UNDO'}


class DESSIN_OT_selection_rect(_SelShapeBase, bpy.types.Operator):
    bl_idname = "dessin.selection_rect"
    bl_options = {'REGISTER', 'UNDO'}
    bl_label = "Select Box"
    bl_description = ("Drag a box to select, without moving anything (drag to the right: objects fully inside, to the left: "
                      "objects touched; Shift: add, Ctrl/Cmd: remove). A simple click selects one object")

    def modal(self, context, event):
        if event.type == 'MOUSEMOVE':
            cx, cy = event.mouse_x - self.region.x, event.mouse_y - self.region.y
            if not self.dragged and math.hypot(cx - self.start[0], cy - self.start[1]) > 5.0 * px_scale():
                self.dragged = True
                self.crossing = cx < self.start[0]
            if self.dragged:
                sx, sy = self.start
                self.pts = [(sx, sy), (cx, sy), (cx, cy), (sx, cy)]
                redraw_region(self)
            return {'RUNNING_MODAL'}
        return _SelShapeBase.modal(self, context, event)


CIRCLE_SEL = {"radius": 40.0}          # rayon du pinceau en pixels (échelle d'interface 1)


def draw_circle_outline(cx, cy, r, color, fill=False):
    n = 48
    pts = [(cx + r * math.cos(TAU * i / n), cy + r * math.sin(TAU * i / n)) for i in range(n)]
    shader = get_shader('2D')
    gpu.state.blend_set('ALPHA')
    shader.bind()
    if fill:
        shader.uniform_float("color", (color[0], color[1], color[2], 0.10))
        batch_for_shader(shader, 'TRI_FAN', {"pos": [(cx, cy)] + pts + [pts[0]]}).draw(shader)
    gpu.state.line_width_set(1.5)
    shader.uniform_float("color", (color[0], color[1], color[2], 0.95))
    batch_for_shader(shader, 'LINE_LOOP', {"pos": pts}).draw(shader)
    gpu.state.line_width_set(1.0)
    gpu.state.blend_set('NONE')


def circle_draw_cursor(context, tool, xy):
    """Pinceau circulaire qui suit la souris quand l'outil Select Circle est actif."""
    draw_circle_outline(xy[0], xy[1], CIRCLE_SEL["radius"] * px_scale(), BOX_BLUE)


def draw_circle_cb(op):
    if not _same_region(op):
        return
    draw_circle_outline(op.cursor[0], op.cursor[1], CIRCLE_SEL["radius"] * px_scale(), BOX_ORANGE if op.subtract else BOX_BLUE, fill=True)


class DESSIN_OT_selection_cercle(bpy.types.Operator):
    bl_idname = "dessin.selection_cercle"
    bl_label = "Select Circle"
    bl_description = ("Paint a selection with a circular brush: everything the circle touches is selected while you drag "
                      "(Shift: add, Ctrl/Cmd: remove, mouse wheel: brush size). A simple click selects what is under the circle")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (context.area is not None and context.area.type == 'VIEW_3D'
                and context.mode in {'OBJECT', 'EDIT_MESH'})

    def invoke(self, context, event):
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS' and context.area is not None and cmd_click_idle(context, event):
            return {'CANCELLED'}
        self.area = context.area
        self.region = find_window_region(self.area, event.mouse_x, event.mouse_y)
        if self.region is None:
            return {'CANCELLED', 'PASS_THROUGH'}
        for r in self.area.regions:
            if (r.type in {'TOOLS', 'UI', 'HEADER', 'TOOL_HEADER'} and r.x <= event.mouse_x < r.x + r.width
                    and r.y <= event.mouse_y < r.y + r.height):
                return {'CANCELLED', 'PASS_THROUGH'}
        if over_nav_gizmo(self.area, event.mouse_x, event.mouse_y):
            return {'CANCELLED', 'PASS_THROUGH'}
        if event.alt or event.oskey:
            return {'CANCELLED', 'PASS_THROUGH'}
        self.cursor = (event.mouse_x - self.region.x, event.mouse_y - self.region.y)
        self.last = self.cursor
        self.first = True
        self.subtract = bool(event.ctrl)
        self._h = bpy.types.SpaceView3D.draw_handler_add(draw_circle_cb, (self,), 'WINDOW', 'POST_PIXEL')
        context.window_manager.modal_handler_add(self)
        self.paint(context, event)
        return {'RUNNING_MODAL'}

    def cleanup(self):
        if getattr(self, "_h", None) is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._h, 'WINDOW')
            self._h = None
        try:
            self.area.tag_redraw()
        except ReferenceError:
            pass

    def paint(self, context, event):
        """Sélectionne (ou retire) ce que touche le cercle. Le premier passage remplace la sélection sauf avec Maj / Ctrl."""
        import types as _types
        cx, cy = self.cursor
        R = CIRCLE_SEL["radius"] * px_scale()
        inside_fn = lambda sx, sy: (sx - cx) ** 2 + (sy - cy) ** 2 <= R * R

        def seg_fn(ax, ay, bx, by):
            dx, dy = bx - ax, by - ay
            ln = dx * dx + dy * dy
            t = np.clip(((cx - ax) * dx + (cy - ay) * dy) / np.where(ln > 1e-12, ln, 1.0), 0.0, 1.0)
            px, py = ax + t * dx, ay + t * dy
            return (px - cx) ** 2 + (py - cy) ** 2 <= R * R
        if self.first:
            ev = _types.SimpleNamespace(shift=bool(event.shift), ctrl=bool(event.ctrl))
        else:
            ev = _types.SimpleNamespace(shift=not event.ctrl, ctrl=bool(event.ctrl))
        self.first = False
        if context.mode == 'EDIT_MESH':
            select_edit_shape(context, self.area, self.region, inside_fn, seg_fn, True, ev)
        else:
            select_objects_shape(context, self.area, self.region, inside_fn, seg_fn, True, ev)

    def modal(self, context, event):
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self.cleanup()
            return {'CANCELLED'}
        if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE', 'NUMPAD_PLUS', 'NUMPAD_MINUS'} and event.value in {'PRESS', 'NOTHING'}:
            up = event.type in {'WHEELUPMOUSE', 'NUMPAD_PLUS'}
            CIRCLE_SEL["radius"] = min(400.0, max(5.0, CIRCLE_SEL["radius"] * (1.15 if up else 1 / 1.15)))
            redraw_region(self)
            return {'RUNNING_MODAL'}
        if event.type == 'MOUSEMOVE':
            self.cursor = (event.mouse_x - self.region.x, event.mouse_y - self.region.y)
            self.subtract = bool(event.ctrl)
            if math.hypot(self.cursor[0] - self.last[0], self.cursor[1] - self.last[1]) >= max(3.0, CIRCLE_SEL["radius"] * 0.15) * px_scale():
                self.last = self.cursor
                self.paint(context, event)
            redraw_region(self)
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            self.cleanup()
            return {'FINISHED'}
        return {'RUNNING_MODAL'}


def _late_imports():
    """Noms définis dans des modules chargés après celui-ci : ils ne servent qu'à l'exécution des outils."""
    global _CMD, _SF, back_to_idle, boundary_loops, cmd_click_idle, extrude_ball_hit, gumball_handle_at
    global gumball_selection, sel_filter_restore, set_prompt
    from .display import _SF, sel_filter_restore
    from .gumball import gumball_selection
    from .offset_extrude import back_to_idle
    from .blocks import boundary_loops
    from .gumball_handles import extrude_ball_hit, gumball_handle_at
    from .views import _CMD
    from .cplane import set_prompt
    from .command_line import cmd_click_idle
