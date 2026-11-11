"""Wanderer CAD : Trim."""

import bmesh
import bpy
import gpu
import math
import numpy as np
from gpu_extras.batch import batch_for_shader
from mathutils import Vector, geometry

from .core import TAU, arc_bezier_data, pref
from .drawing import _HOVER, draw_px_points, get_shader, px_scale
from .base import DessinBase
from .dimensions import fit_circle_points


# --------------------------------------------------------------------------
# Trim : supprime la partie d'un tracé comprise entre deux intersections avec les courbes de coupe
# --------------------------------------------------------------------------

def is_xline(obj):
    """Ligne de construction (très longue) : à ignorer dans les calculs de tolérance liés à la taille de la scène."""
    try:
        return bool(obj.get("cad_xline")) or (obj.get("cad_noGrab") and obj.name.startswith("Construction Line"))
    except (ReferenceError, AttributeError):
        return False


CURVE_QUALITY = {'DRAFT': 0.5, 'NORMAL': 1.0, 'FINE': 2.0, 'VERY_FINE': 4.0}


def curve_quality_factor():
    """Facteur de finesse des courbes (préférences) : 1 = 96 côtés par cercle."""
    try:
        return CURVE_QUALITY.get(pref("curve_quality"), 1.0)
    except (KeyError, TypeError):
        return 1.0


def curve_wire_direct(obj):
    """Contour d'une courbe POLY / Bézier sans modificateur, calculé directement depuis ses points (sans passer par le graphe
    d'évaluation) : arcs et cercles échantillonnés finement, bevel et extrusion sans effet. None si la courbe n'est pas de ce type."""
    cu = obj.data
    if obj.modifiers or any(sp.type not in {'POLY', 'BEZIER'} for sp in cu.splines):
        return None
    mw = np.array(obj.matrix_world, dtype=np.float64)
    flat = cu.dimensions == '2D'
    qf = curve_quality_factor()
    n_seg = max(6, int(round(max(16, 2 * int(cu.resolution_u)) * qf)))
    verts, edges = [], []
    ts = np.linspace(0.0, 1.0, n_seg + 1)[1:]
    ts_arc = {}
    ctr = obj.get("dessin_centre")
    try:
        ctr = np.array(tuple(ctr), dtype=np.float64) if ctr is not None else None
        if ctr is not None and ctr.shape != (3,):
            ctr = None
    except (TypeError, ValueError):
        ctr = None
    for sp in cu.splines:
        if sp.type == 'POLY':
            P = np.array([tuple(q.co[:3]) for q in sp.points], dtype=np.float64).reshape(-1, 3)
        else:
            bp = sp.bezier_points
            m = len(bp)
            co = np.array([tuple(q.co) for q in bp], dtype=np.float64).reshape(-1, 3)
            hl = np.array([tuple(q.handle_left) for q in bp], dtype=np.float64).reshape(-1, 3)
            hr = np.array([tuple(q.handle_right) for q in bp], dtype=np.float64).reshape(-1, 3)
            P_list = [co[0]]
            last = m if sp.use_cyclic_u else m - 1
            for i in range(last):
                j = (i + 1) % m
                p0, p1, p2, p3 = co[i], hr[i], hl[j], co[j]
                d = p3 - p0
                dd = float(d @ d)
                straight = dd < 1e-24 or (np.linalg.norm(np.cross(p1 - p0, d)) <= 1e-7 * dd
                                          and np.linalg.norm(np.cross(p2 - p0, d)) <= 1e-7 * dd)
                if straight:
                    P_list.append(p3)
                else:
                    t = ts[:, None]
                    if ctr is not None:
                        # cercle / arc : le nombre de côtés suit l'angle couvert par le morceau (96 côtés par tour en qualité
                        # normale), que le cercle soit construit en 4 ou en 8 morceaux
                        va, vb = p0 - ctr, p3 - ctr
                        la, lb = float(np.linalg.norm(va)), float(np.linalg.norm(vb))
                        if la > 1e-12 and lb > 1e-12:
                            ang = math.acos(max(-1.0, min(1.0, float(va @ vb) / (la * lb))))
                            k_ = max(3, int(round(96.0 * qf * ang / (2.0 * math.pi))))
                            t = ts_arc.get(k_)
                            if t is None:
                                t = ts_arc[k_] = np.linspace(0.0, 1.0, k_ + 1)[1:][:, None]
                    B = ((1 - t) ** 3) * p0 + 3 * ((1 - t) ** 2) * t * p1 + 3 * (1 - t) * t * t * p2 + (t ** 3) * p3
                    P_list.extend(B)
            P = np.array(P_list, dtype=np.float64)
            if sp.use_cyclic_u and len(P) > 1:
                P = P[:-1]                 # le dernier point retombe sur le premier
        if len(P) < 2:
            continue
        if flat:
            P = P.copy()
            P[:, 2] = 0.0
        W = P @ mw[:3, :3].T + mw[:3, 3]
        base = len(verts)
        verts.extend(Vector(tuple(w)) for w in W)
        k = len(W)
        edges.extend((base + i, base + i + 1) for i in range(k - 1))
        if sp.use_cyclic_u and k > 2:
            edges.append((base + k - 1, base))
    return (verts, edges) if edges else None


def wire_graph(obj, depsgraph):
    """(sommets monde [Vector], arêtes [(i, j)]) d'un contour (maillage sans face ou courbe), ou None."""
    if obj.type == 'MESH':
        me = obj.data
        if len(me.polygons) or not len(me.edges):
            return None
        mw = obj.matrix_world
        verts = [mw @ v.co for v in me.vertices]
        edges = [tuple(e.vertices) for e in me.edges]
        return verts, edges
    if obj.type == 'CURVE' and "dessin_cotation" not in obj.keys() and len(obj.data.splines):
        cu = obj.data
        direct_res = curve_wire_direct(obj)
        if direct_res is not None:
            return direct_res
        tmp = None
        try:
            if cu.bevel_depth != 0.0 or cu.extrude != 0.0 or cu.bevel_object is not None:
                # courbe épaissie (bevel / extrusion) : la version évaluée a déjà la section, la remettre à zéro ne la recalcule pas.
                # On évalue une copie sans épaisseur : le fil de la courbe, une arête par segment.
                tmp = obj.copy()
                tmp.data = cu.copy()
                tmp.data.bevel_depth = 0.0
                tmp.data.extrude = 0.0
                tmp.data.bevel_object = None
                tmp.data.taper_object = None
                bpy.context.scene.collection.objects.link(tmp)
                depsgraph = bpy.context.evaluated_depsgraph_get()
                src = tmp
            else:
                src = obj
            ev = src.evaluated_get(depsgraph)
            me = ev.to_mesh()
            mw = obj.matrix_world
            verts = [mw @ v.co for v in me.vertices]
            edges = [tuple(e.vertices) for e in me.edges]
            ev.to_mesh_clear()
        finally:
            if tmp is not None:
                data = tmp.data
                bpy.data.objects.remove(tmp)
                bpy.data.curves.remove(data)
        return (verts, edges) if edges else None
    return None


def wire_chain(edges, e0):
    """Chaîne d'arêtes autour de l'arête e0 (on s'arrête aux extrémités et aux carrefours).
    Retourne (sommets ordonnés, arêtes ordonnées, fermée, position de e0 dans la chaîne)."""
    adj = {}
    for k, (a, b) in enumerate(edges):
        adj.setdefault(a, []).append(k)
        adj.setdefault(b, []).append(k)
    a0, b0 = edges[e0]
    vs, es = [a0, b0], [e0]
    seen = {e0}
    closed = False
    cur_v, cur_e = b0, e0
    while len(adj[cur_v]) == 2:
        nxt = [k for k in adj[cur_v] if k != cur_e]
        if not nxt:
            break
        k = nxt[0]
        if k in seen:
            closed = True
            break
        seen.add(k)
        a, b = edges[k]
        v = b if a == cur_v else a
        es.append(k)
        vs.append(v)
        cur_v, cur_e = v, k
    if closed:
        vs.pop()               # le dernier sommet est le premier
        return vs, es, True, 0
    cur_v, cur_e = a0, e0
    back_v, back_e = [], []
    while len(adj[cur_v]) == 2:
        nxt = [k for k in adj[cur_v] if k != cur_e]
        if not nxt or nxt[0] in seen:
            break
        k = nxt[0]
        seen.add(k)
        a, b = edges[k]
        v = b if a == cur_v else a
        back_e.append(k)
        back_v.append(v)
        cur_v, cur_e = v, k
    vs = back_v[::-1] + vs
    es = back_e[::-1] + es
    return vs, es, False, len(back_e)


def trim_params(P0, P1, Q0, Q1, tol):
    """Paramètres s (sur P0->P1) des intersections avec les segments Q0->Q1 (tableaux (n,3)) à tol près."""
    d1 = P1 - P0
    a = float(d1 @ d1)
    if a < 1e-18 or len(Q0) == 0:
        return []
    d2 = Q1 - Q0
    r = P0 - Q0
    e = np.einsum('ij,ij->i', d2, d2)
    b = d2 @ d1
    c = float(d1 @ r.T) if False else r @ d1
    f = np.einsum('ij,ij->i', d2, r)
    den = a * e - b * b
    ok = (den > 1e-12 * a * np.maximum(e, 1e-18)) & (e > 1e-18)
    den_s = np.where(ok, den, 1.0)
    s = (b * f - c * e) / den_s
    t = (a * f - b * c) / den_s
    eps_s = tol / math.sqrt(a)
    eps_t = tol / np.sqrt(np.maximum(e, 1e-18))
    ok &= (s >= -eps_s) & (s <= 1 + eps_s) & (t >= -eps_t) & (t <= 1 + eps_t)
    if not ok.any():
        return []
    s = np.clip(s, 0.0, 1.0)
    t = np.clip(t, 0.0, 1.0)
    pa = P0 + np.outer(s, d1)
    pb = Q0 + d2 * t[:, None]
    ok &= np.linalg.norm(pa - pb, axis=1) <= tol
    return [float(x) for x in s[ok]]


def trim_wire(verts, edges, e0, tcl, cutters, own_ids, tol, mesh_cut=None):
    """Retire la partie de la chaîne de e0 autour du point de clic (paramètre tcl le long de e0) entre deux intersections.
    cutters : (Q0, Q1, ids) segments de coupe (ids : (a, b) sommets du même objet, -1 sinon).
    Retourne (verts, edges) modifiés, ou None / un message si rien à couper."""
    vs, es, closed, k0 = wire_chain(edges, e0)
    n = len(es)
    Q0, Q1, qa, qb = cutters
    us = []
    for i in range(n):
        va, vb = vs[i], vs[(i + 1) % len(vs)] if closed else vs[i + 1]
        keep = ~((qa == va) | (qa == vb) | (qb == va) | (qb == vb))
        if own_ids is None:
            keep[:] = True
        for s in trim_params(np.array(verts[va], dtype=np.float64), np.array(verts[vb], dtype=np.float64), Q0[keep], Q1[keep], tol):
            us.append(i + s)
        if mesh_cut is not None:
            for s in mesh_cut(verts[va], verts[vb]):
                us.append(i + s)
    if not us:
        return "No intersection with the cutting curves"
    us.sort()
    merged = [us[0]]
    for u in us[1:]:
        if u - merged[-1] > 1e-7:
            merged.append(u)
    us = merged
    if closed and len(us) > 1 and us[-1] - us[0] > n - 1e-7:
        us.pop()
    uc = k0 + tcl
    if closed:
        if len(us) < 2:
            return "A closed curve needs two intersections to be trimmed"
        below = [u for u in us if u < uc - 1e-9]
        above = [u for u in us if u > uc + 1e-9]
        L = below[-1] if below else us[-1]
        U = above[0] if above else us[0]
    else:
        below = [u for u in us if u < uc - 1e-9]
        above = [u for u in us if u > uc + 1e-9]
        L = below[-1] if below else None
        U = above[0] if above else None
    new_verts = list(verts)

    def point_at(u):
        i = min(int(math.floor(u + 1e-12)), n - 1)
        fr = u - i
        va, vb = vs[i], vs[(i + 1) % len(vs)] if closed else vs[i + 1]
        return verts[va].lerp(verts[vb], fr)

    def vid(p):
        for j in set(vs):
            if (verts[j] - p).length <= tol:
                return j
        new_verts.append(p.copy())
        return len(new_verts) - 1

    def piece(items):
        ids = []
        for it in items:
            j = it if isinstance(it, int) else vid(it)
            if not ids or ids[-1] != j:
                ids.append(j)
        return ids

    pieces = []
    if closed:
        Lw = L + n if L < U else L
        items = [point_at(U)] + [vs[j % n] for j in range(int(math.floor(U + 1e-12)) + 1, int(math.floor(Lw + 1e-12)) + 1)] + [point_at(L)]
        pieces.append(piece(items))
    else:
        if L is not None:
            items = [vs[j] for j in range(0, int(math.floor(L + 1e-12)) + 1)] + [point_at(L)]
            pieces.append(piece(items))
        if U is not None:
            items = [point_at(U)] + [vs[j] for j in range(int(math.floor(U + 1e-12)) + 1, len(vs))]
            pieces.append(piece(items))
    chain_edges = set(es)
    new_edges = [e for k, e in enumerate(edges) if k not in chain_edges]
    for ids in pieces:
        for a, b in zip(ids, ids[1:]):
            new_edges.append((a, b))
    used = {v for e in new_edges for v in e}
    chain_v = set(vs)
    keep_v = [j for j in range(len(new_verts)) if j in used or j not in chain_v]
    remap = {old: k for k, old in enumerate(keep_v)}
    return [new_verts[j] for j in keep_v], [(remap[a], remap[b]) for a, b in new_edges]


def wire_paths(n_verts, edges):
    """Décompose un graphe d'arêtes en chemins [(sommets, fermé)]."""
    adj = {}
    for k, (a, b) in enumerate(edges):
        adj.setdefault(a, []).append((k, b))
        adj.setdefault(b, []).append((k, a))
    used = set()
    paths = []

    def walk(start, first):
        path = [start]
        cur, e = start, first
        while True:
            used.add(e[0])
            cur = e[1]
            path.append(cur)
            if len(adj[cur]) != 2:
                return path, False
            nxt = [x for x in adj[cur] if x[0] != e[0] and x[0] not in used]
            if not nxt:
                return path, cur == start
            e = nxt[0]
            if e[1] == start and len(adj[start]) == 2:
                used.add(e[0])
                return path, True

    for v in adj:
        if len(adj[v]) != 2:
            for e in adj[v]:
                if e[0] not in used:
                    paths.append(walk(v, e))
    for v in adj:
        for e in adj[v]:
            if e[0] not in used:
                path, closed = walk(v, e)
                if closed and path[0] == path[-1]:
                    path.pop()
                paths.append((path, closed))
    out = []
    for path, closed in paths:
        if closed and len(path) > 1 and path[0] == path[-1]:
            path = path[:-1]
        out.append((path, closed))
    return out


def circle_hints(obj):
    """Cercles / arcs de Bézier de la courbe obj (avant une coupe) : [(centre, rayon, normale, e1, e2)] en coordonnées monde."""
    out = []
    if obj.type != 'CURVE':
        return out
    try:
        g = curve_wire_direct(obj)
    except (RuntimeError, ReferenceError):
        return out
    if g is None:
        return out
    cu = obj.data
    if not any(sp.type == 'BEZIER' for sp in cu.splines):
        return out
    verts, edges = g
    V = np.array([tuple(v) for v in verts], dtype=np.float64)
    for path, closed in wire_paths(len(verts), edges):
        if len(path) < 6:
            continue
        P = V[path]
        fit = fit_circle_points(P)
        if fit is None:
            continue
        c, r, n, e1, e2 = fit
        if np.abs(np.linalg.norm(P - c, axis=1) - r).max() > 0.002 * r:
            continue                # un vrai arc de Bézier colle au cercle à moins de 0,03 % : un contour libre est laissé tel quel
        out.append((np.asarray(c, dtype=np.float64), float(r), np.asarray(n), np.asarray(e1), np.asarray(e2)))
    return out


def _arc_spline_from_path(cu, inv, P, closed, hint):
    """Écrit le tracé P (points monde ordonnés, sur le cercle `hint`) comme vrai arc / cercle de Bézier. False si les points
    ne tiennent pas sur ce cercle."""
    c, r, n, e1, e2 = hint
    d = P - c
    x, y, z = d @ e1, d @ e2, d @ n
    rad = np.hypot(x, y)
    if np.abs(rad - r).max() > 0.012 * r or np.abs(z).max() > 0.012 * r:
        return False
    ang = np.arctan2(y, x)
    steps = np.diff(ang)
    steps = (steps + math.pi) % (2 * math.pi) - math.pi
    if closed:
        sweep = TAU if steps.sum() >= 0 else -TAU
        t0 = float(ang[0])
    else:
        sweep = float(steps.sum())
        t0 = float(ang[0])
        if abs(sweep) < 1e-6:
            return False
    cc, u, v = Vector(tuple(c)), Vector(tuple(e1)), Vector(tuple(e2))
    data = arc_bezier_data(cc, u, v, r, t0, sweep)
    if closed:
        first_left = data[-1][1]
        data = data[:-1]
        data[0] = (data[0][0], first_left, data[0][2])
    sp = cu.splines.new('BEZIER')
    sp.bezier_points.add(len(data) - 1)
    for bp, (pos, hl, hr) in zip(sp.bezier_points, data):
        bp.handle_left_type = bp.handle_right_type = 'FREE'
        bp.co, bp.handle_left, bp.handle_right = inv @ pos, inv @ hl, inv @ hr
    sp.use_cyclic_u = bool(closed)
    return True


def write_wire(obj, verts, edges, hints=None):
    """Remplace le contour de obj par (verts monde, edges)."""
    inv = obj.matrix_world.inverted()
    local = [inv @ v for v in verts]
    if obj.type == 'MESH':
        me = obj.data
        me.clear_geometry()
        me.from_pydata([tuple(v) for v in local], edges, [])
        me.update()
        return
    cu = obj.data
    cu.splines.clear()
    for path, closed in wire_paths(len(local), edges):
        if len(path) < 2:
            continue
        if closed and len(path) > 1 and path[-1] == path[0]:
            path = path[:-1]
        if hints and len(path) >= 3:
            Pw = np.array([tuple(verts[j]) for j in path], dtype=np.float64)
            if any(_arc_spline_from_path(cu, obj.matrix_world.inverted(), Pw, closed, h) for h in hints):
                continue
        sp = cu.splines.new('POLY')
        sp.points.add(len(path) - 1)
        for pt, j in zip(sp.points, path):
            q = local[j]
            pt.co = (q.x, q.y, q.z, 1.0)
        sp.use_cyclic_u = closed


def _point_in_poly2(pt, poly):
    x, y = pt
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            if x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                inside = not inside
    return inside


def surface_trim(obj, paths, persp_np, hit_local):
    """Retire de la surface de obj la partie cernée par les contours `paths` ([(points monde, fermé)]) vus depuis la caméra.
    Les contours sont projetés sur la surface le long de la vue (orthogonale ou perspective), la face cliquée (hit_local)
    et tout ce qui l'entoure jusqu'au contour est supprimé. Retourne None si c'est fait, sinon un message."""
    from mathutils.bvhtree import BVHTree
    mw = obj.matrix_world
    inv = obj.matrix_world.inverted()
    Pm = np.asarray(persp_np, dtype=np.float64)
    Pinv = np.linalg.inv(Pm)
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    clicked_pt = Vector(hit_local)

    def unproject(x, y, z):
        v = Pinv @ np.array((x, y, z, 1.0))
        return Vector((v[0] / v[3], v[1] / v[3], v[2] / v[3]))

    cache = {}

    def v2(v):
        r = cache.get(v)
        if r is None:
            w = mw @ v.co
            c = Pm @ np.array((w.x, w.y, w.z, 1.0))
            r = (c[0] / c[3], c[1] / c[3]) if c[3] > 1e-9 else False
            cache[v] = r
        return r

    # --- contours en 2D (coordonnées écran normalisées)
    P2 = []
    for pts, closed in paths:
        q = []
        ok = True
        for w in pts:
            c = Pm @ np.array((w.x, w.y, w.z, 1.0))
            if c[3] <= 1e-9:
                ok = False
                break
            xy = (c[0] / c[3], c[1] / c[3])
            if not q or math.hypot(xy[0] - q[-1][0], xy[1] - q[-1][1]) > 1e-9:
                q.append(xy)
        if closed and len(q) > 1 and math.hypot(q[0][0] - q[-1][0], q[0][1] - q[-1][1]) <= 1e-9:
            q.pop()
        if ok and len(q) >= 2 and (not closed or len(q) >= 3):
            P2.append({"pts": q, "closed": closed})
    if not P2:
        bm.free()
        return "The cutting curves are not visible from this view"
    allx = [c[0] for p in P2 for c in p["pts"]]
    ally = [c[1] for p in P2 for c in p["pts"]]
    bx0, bx1, by0, by1 = min(allx) - 1e-4, max(allx) + 1e-4, min(ally) - 1e-4, max(ally) + 1e-4

    tracked = set()
    for f in bm.faces:
        pts = [v2(v) for v in f.verts]
        if any(p is False for p in pts):
            continue
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        if max(xs) >= bx0 and min(xs) <= bx1 and max(ys) >= by0 and min(ys) <= by1:
            tracked.update(f.verts)
    if not tracked:
        bm.free()
        return "The cutting curves do not cross this surface"

    def active_faces():
        return list({f for v in tracked if v.is_valid for f in v.link_faces})

    def find_events(edges):
        """Croisements (arête, t, chemin, position le long du chemin) entre les arêtes et les contours."""
        m = len(edges)
        C0 = np.empty((m, 3))
        C1 = np.empty((m, 3))
        valid = np.ones(m, dtype=bool)
        for k, e in enumerate(edges):
            for arr, v in ((C0, e.verts[0]), (C1, e.verts[1])):
                w = mw @ v.co
                c = Pm @ np.array((w.x, w.y, w.z, 1.0))
                arr[k] = (c[0], c[1], c[3])
        valid = (C0[:, 2] > 1e-9) & (C1[:, 2] > 1e-9)
        out = []
        for pid, p in enumerate(P2):
            pts, closed = p["pts"], p["closed"]
            n = len(pts)
            for j in range(n if closed else n - 1):
                ax, ay = pts[j]
                bx_, by_ = pts[(j + 1) % n]
                dx, dy = bx_ - ax, by_ - ay
                f0 = dy * (C0[:, 0] - ax * C0[:, 2]) - dx * (C0[:, 1] - ay * C0[:, 2])
                f1 = dy * (C1[:, 0] - ax * C1[:, 2]) - dx * (C1[:, 1] - ay * C1[:, 2])
                cross = valid & ((f0 > 0) != (f1 > 0))
                if not cross.any():
                    continue
                idx = np.nonzero(cross)[0]
                t = f0[idx] / (f0[idx] - f1[idx])
                X = C0[idx, 0] + t * (C1[idx, 0] - C0[idx, 0])
                Y = C0[idx, 1] + t * (C1[idx, 1] - C0[idx, 1])
                W = C0[idx, 2] + t * (C1[idx, 2] - C0[idx, 2])
                u = ((X / W - ax) * dx + (Y / W - ay) * dy) / (dx * dx + dy * dy)
                good = (u >= 0.0) & (u < 1.0)
                for k, tt, uu in zip(idx[good], t[good], u[good]):
                    out.append((int(k), float(tt), pid, j + float(uu)))
        return out

    seam_edges = set()
    for _it in range(3):
        faces = active_faces()
        edges = list({e for f in faces for e in f.edges})
        events = find_events(edges)
        hit_edges = {}
        for k, _t, pid, _pos in events:
            hit_edges.setdefault(pid, set()).add(edges[k])
        seams = []
        for pid, p in enumerate(P2):
            if not p["closed"]:
                continue
            for f in faces:
                poly = [v2(v) for v in f.verts]
                if any(q is False for q in poly) or not _point_in_poly2(p["pts"][0], poly):
                    continue
                if not any(e in hit_edges.get(pid, ()) for e in f.edges):
                    seams.append((pid, f))
        if not seams:
            break
        for pid, f in seams:
            if not f.is_valid:
                continue
            ys = [c[1] for c in P2[pid]["pts"]]
            yc = 0.5 * (min(ys) + max(ys))
            a, b, c = unproject(-1.0, yc, -1.0), unproject(1.0, yc, -1.0), unproject(-1.0, yc, 1.0)
            nrm = (b - a).cross(c - a)
            if nrm.length < 1e-12:
                continue
            ret = bmesh.ops.bisect_plane(bm, geom=[f] + list(f.edges) + list(f.verts), dist=1e-7,
                                         plane_co=inv @ a, plane_no=(mw.to_3x3().transposed() @ nrm).normalized(),
                                         clear_inner=False, clear_outer=False)
            for g in ret.get("geom_cut", ()):
                if isinstance(g, bmesh.types.BMEdge):
                    seam_edges.add(g)
                elif isinstance(g, bmesh.types.BMVert):
                    tracked.add(g)
    faces = active_faces()
    edges = list({e for f in faces for e in f.edges})
    events = find_events(edges)
    if not events:
        bm.free()
        return "The cutting curves do not cross this surface"
    # --- on coupe les arêtes aux croisements
    by_edge = {}
    for k, t, pid, pos in events:
        by_edge.setdefault(k, []).append((t, pid, pos))
    crossings = []                     # (pid, pos, sommet)
    for k, lst in by_edge.items():
        e = edges[k]
        lst.sort()
        cur_e, start = e, e.verts[0]
        tprev = 0.0
        for t, pid, pos in lst:
            tr = (t - tprev) / (1.0 - tprev) if tprev < 1.0 else 1.0
            other = cur_e.other_vert(start)
            if tr <= 1e-6:
                vert = start
            elif tr >= 1.0 - 1e-6:
                vert = other
            else:
                _ne, vert = bmesh.utils.edge_split(cur_e, start, tr)
                tracked.add(vert)
                start, tprev = vert, t
            crossings.append((pid, pos, vert))
    for _p, _pos, v in crossings:
        tracked.add(v)
    # --- pour chaque face : les croisements s'apparient (entrée / sortie) le long du contour
    by_face = {}
    for pid, pos, v in crossings:
        for f in v.link_faces:
            by_face.setdefault((f, pid), []).append((pos, v))
    pairs = []
    for (f, pid), lst in by_face.items():
        poly = [v2(v) for v in f.verts]
        if any(q is False for q in poly) or len(poly) < 3:
            continue
        p = P2[pid]
        lst = sorted({(pos, v) for pos, v in lst}, key=lambda a: a[0])
        merged = []
        for pos, v in lst:                     # un croisement exactement sur un sommet du contour est compté une seule fois
            if merged and merged[-1][1] is v and abs(merged[-1][0] - pos) < 1e-6:
                continue
            merged.append((pos, v))
        lst = merged
        q_pos = lst[0][0] - 1e-6              # juste avant le premier croisement : dans la face (=> c'est une sortie) ou non
        n_pts = len(p["pts"])
        if q_pos < 0.0:
            q_pos = q_pos + n_pts if p["closed"] else 0.0
        jj = int(math.floor(q_pos)) % n_pts
        fr = q_pos - math.floor(q_pos)
        a_pt, b_pt = p["pts"][jj], p["pts"][(jj + 1) % n_pts]
        inside0 = _point_in_poly2((a_pt[0] * (1 - fr) + b_pt[0] * fr, a_pt[1] * (1 - fr) + b_pt[1] * fr), poly)
        if p["closed"]:
            if len(lst) % 2:
                continue
            seq = lst[1:] + lst[:1] if inside0 else lst
        else:
            seq = lst[1:] if inside0 else lst
            if len(seq) % 2:
                seq = seq[:-1]
        for a in range(0, len(seq) - 1, 2):
            (pa, va), (pb, vb) = seq[a], seq[a + 1]
            if va is not vb:
                pairs.append((pid, pa, va, pb, vb))
    barrier = set()
    n_cut = 0
    for pid, pa, va, pb, vb in pairs:
        p = P2[pid]
        n = len(p["pts"])
        if pa < pb:
            ks = [k for k in range(n) if pa + 1e-6 < k < pb - 1e-6]
        else:
            ks = [k for k in range(n) if k > pa + 1e-6 or k < pb - 1e-6]
            ks.sort(key=lambda k: (k <= pa, k))
        mid_pos = 0.5 * (pa + pb) if pa < pb else ((pa + pb + n) * 0.5) % n
        j0 = int(mid_pos) % n
        j1 = (j0 + 1) % n
        fr = mid_pos - int(mid_pos)
        mid2 = (p["pts"][j0][0] * (1 - fr) + p["pts"][j1][0] * fr, p["pts"][j0][1] * (1 - fr) + p["pts"][j1][1] * fr)
        cands = [f for f in va.link_faces if f.is_valid and f in vb.link_faces]
        face = None
        if len(cands) == 1:
            face = cands[0]
        else:
            for f in cands:
                poly = [v2(v) for v in f.verts]
                if not any(q is False for q in poly) and _point_in_poly2(mid2, poly):
                    face = f
                    break
        if face is None:
            continue
        coords = []
        for k in ks:
            a_, b_ = unproject(p["pts"][k][0], p["pts"][k][1], -1.0), unproject(p["pts"][k][0], p["pts"][k][1], 1.0)
            hit = geometry.intersect_line_plane(inv @ a_, inv @ b_, face.verts[0].co, face.normal)
            coords.append(tuple(hit if hit is not None else face.calc_center_median()))
        if not coords and bm.edges.get((va, vb)) is not None:
            barrier.add(bm.edges.get((va, vb)))
            continue
        try:
            bmesh.utils.face_split(face, va, vb, coords=coords)
        except (ValueError, RuntimeError):
            continue
        n_cut += 1
        # arêtes créées : va -> c1 -> ... -> vb
        chain = [va]
        if coords:
            prev, cur = va, None
            nodes = []
            back = vb
            seq_v = []
            for c in reversed(coords):
                found = None
                for e in back.link_edges:
                    o = e.other_vert(back)
                    if o is not va and (o.co - Vector(c)).length < 1e-5 and len(o.link_edges) == 2:
                        found = o
                        break
                if found is None:
                    break
                seq_v.append(found)
                back = found
            chain = [va] + seq_v[::-1] + [vb]
            for v_ in seq_v:
                tracked.add(v_)
        else:
            chain = [va, vb]
        for a_v, b_v in zip(chain, chain[1:]):
            e = bm.edges.get((a_v, b_v))
            if e is not None:
                barrier.add(e)
    if not n_cut and not barrier:
        bm.free()
        return "The cutting curves do not cross this surface"
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    bvh = BVHTree.FromBMesh(bm)
    found = bvh.find_nearest(clicked_pt)
    if found is None or found[2] is None:
        bm.free()
        return "Click on the surface"
    start = bm.faces[found[2]]

    def flood(block):
        seen = {start}
        stack = [start]
        while stack:
            f = stack.pop()
            for e in f.edges:
                if e in block:
                    continue
                for g in e.link_faces:
                    if g not in seen:
                        seen.add(g)
                        stack.append(g)
        return seen
    region = flood(barrier)
    whole = flood(set())
    if len(region) == len(whole):
        bm.free()
        return "The cutting curves do not split this surface (the outline must cross it or be closed)"
    save_untrimmed(obj)
    bmesh.ops.delete(bm, geom=list(region), context='FACES')
    extra = [e for e in seam_edges if e.is_valid and e not in barrier]
    if extra:
        try:
            bmesh.ops.dissolve_edges(bm, edges=extra, use_verts=False, use_face_split=False)
        except (RuntimeError, ValueError):
            pass
    bm.to_mesh(me)
    me.update()
    bm.free()
    return None


def trim_mesh_cutters(context, exclude=()):
    """Maillages à faces sélectionnés (hors objets exclus) : ils servent de cutters au Trim."""
    return [o for o in context.selected_objects
            if o.type == 'MESH' and len(o.data.polygons) and o not in exclude]


def trim_mesh_cut_fn(objs, depsgraph, tol):
    """Fonction (A, B) -> [s] : paramètres où le segment A->B traverse la surface des maillages objs."""
    if not objs:
        return None
    bvh = make2d_collect(objs, depsgraph)[1]
    if bvh is None:
        return None

    def cut(A, B):
        d = B - A
        L = d.length
        if L < 1e-12:
            return []
        d = d / L
        out = []
        pos = 0.0
        for _ in range(64):
            hit = bvh.ray_cast(A + d * pos, d, L - pos + tol)
            if hit[0] is None:
                break
            dist = pos + hit[3]
            if dist > L + tol:
                break
            out.append(min(max(dist / L, 0.0), 1.0))
            pos = dist + max(tol * 2.0, 1e-7)
            if pos >= L:
                break
        return out
    return cut


_CURVE_PTS = {"handle": None}


def curve_points_cb():
    """Points de contrôle des courbes sélectionnées (comme « Points On » de Rhino) : visibles dès que la courbe est cliquée."""
    if not pref("curve_points"):
        return
    try:
        ctx = bpy.context
        if ctx.mode != 'OBJECT' or ctx.region_data is None:
            return
        objs = [o for o in ctx.selected_objects if o.type == 'CURVE' and o.visible_get()]
        if not objs:
            return
        key = (_HOVER["version"], tuple(o.name for o in objs))
        cache = _CURVE_PTS.get("cache")
        if cache is not None and cache[0] == key:
            pts, poly = cache[1], cache[2]          # rien n'a changé depuis l'image précédente : on ne relit pas les courbes
        else:
            pts, poly = curve_points_collect(objs)
            _CURVE_PTS["cache"] = (key, pts, poly)
        if not len(pts):
            return
        shader = get_shader('3D')
        gpu.state.blend_set('ALPHA')
        gpu.state.depth_test_set('NONE')
        if poly:
            shader.bind()
            gpu.state.line_width_set(1.0)
            shader.uniform_float("color", (0.9, 0.9, 0.9, 0.55))
            batch_for_shader(shader, 'LINES', {"pos": poly}).draw(shader)
        draw_px_points(pts, 9.0 * px_scale(0.35), (0.0, 0.0, 0.0, 1.0))
        draw_px_points(pts, 6.0 * px_scale(0.35), (1.0, 1.0, 1.0, 1.0))
        gpu.state.blend_set('NONE')
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
        pass


def curve_points_collect(objs):
    """(points monde (n, 3), segments du polygone de contrôle) des courbes, 4000 points au plus."""
    pts, poly = [], []
    for o in objs:
        mw = o.matrix_world
        for sp in o.data.splines:
            if sp.type == 'BEZIER':
                pts += [mw @ bp.co for bp in sp.bezier_points]
            else:
                cv = [mw @ Vector(p.co[:3]) for p in sp.points]
                pts += cv
                if sp.type == 'NURBS':      # polygone de contrôle
                    for a, b in zip(cv, cv[1:]):
                        poly += [tuple(a), tuple(b)]
                    if sp.use_cyclic_u and len(cv) > 2:
                        poly += [tuple(cv[-1]), tuple(cv[0])]
            if len(pts) > 4000:
                break
        if len(pts) > 4000:
            break
    return np.array([tuple(p) for p in pts], dtype=np.float64).reshape(-1, 3), poly


_TRIM_HL = {"handle": None}
TRIM_HL_COLOR = (1.0, 0.1, 0.75, 1.0)


def trim_highlight_cb():
    """Surligne les cutters (objets sélectionnés) tant que l'outil Trim est actif."""
    context = bpy.context
    try:
        if context.mode != 'OBJECT' or DessinBase.active_tool_id(context) != "dessin.trim_tool":
            return
        dg = context.evaluated_depsgraph_get()
        objs = list(context.selected_objects)
    except (AttributeError, RuntimeError, ReferenceError):
        return
    pts = []
    for o in objs:
        try:
            if o.type == 'MESH' and len(o.data.polygons):
                me = o.data
                mw = o.matrix_world
                for e in me.edges:
                    pts.append(mw @ me.vertices[e.vertices[0]].co)
                    pts.append(mw @ me.vertices[e.vertices[1]].co)
            elif o.type in {'MESH', 'CURVE'} and "dessin_cotation" not in o.keys():
                ev = o.evaluated_get(dg)
                me = ev.to_mesh()
                mw = o.matrix_world
                for e in me.edges:
                    pts.append(mw @ me.vertices[e.vertices[0]].co)
                    pts.append(mw @ me.vertices[e.vertices[1]].co)
                ev.to_mesh_clear()
        except (RuntimeError, AttributeError, ReferenceError):
            continue
        if len(pts) > 400000:
            break
    if not pts:
        return
    shader = get_shader('3D')
    shader.bind()
    gpu.state.blend_set('ALPHA')
    gpu.state.depth_test_set('NONE')
    gpu.state.line_width_set(3.0)
    shader.uniform_float("color", TRIM_HL_COLOR)
    batch_for_shader(shader, 'LINES', {"pos": [tuple(p) for p in pts]}).draw(shader)
    gpu.state.line_width_set(1.0)
    gpu.state.depth_test_set('NONE')
    gpu.state.blend_set('NONE')


def _late_imports():
    """Noms définis dans des modules chargés après celui-ci : ils ne servent qu'à l'exécution des outils."""
    global make2d_collect, save_untrimmed
    from .blocks import save_untrimmed
    from .make2d import make2d_collect
