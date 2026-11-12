"""Wanderer CAD : Pipe, Intersect, Section, Contour, ExtractSrf, DupBorder, DupEdge, MergeAllFaces, Unroll, RebuildSrf, Orient."""

import bmesh
import bpy
import math
import numpy as np
from mathutils import Matrix, Vector, geometry

from .core import NAV_TYPES, TAU, build_polyline, drawing_axis, plane_axes, plane_origin
from .drawing import find_window_region, main_window_region, region_rv3d
from .base import DessinBase
from .solids import build_solid
from .transform import DessinTransform
from .edges import build_polylines
from .booleans import _link_like
from .curve_edit import unit_scale_of
from .trim import curve_quality_factor
from .join_explode import EXPLODE_SHARP_DEG
from .surfaces import chain_open_paths, delete_objects, mesh_object_from_arrays, object_paths
from .hatch import _select_only
from .curve_tools import _curve_targets
from .cplane import cmd_log, cmd_notice, nothing_done, set_prompt
from .pushpull import (
    DESSIN_OT_pushpull, IMPRINT_LAYER, PP_PREVIEW_EDGES, pp_boundary, pp_curved_region, pp_draw_cb, pp_region,
)


# --------------------------------------------------------------------------
# Commandes Rhino complémentaires : Pipe, Intersect, Section, Contour, ExtractSrf, DupBorder, DupEdge, MergeAllFaces,
# Unroll, RebuildSrf, Orient
# --------------------------------------------------------------------------

def _mesh_targets(context):
    return [o for o in context.selected_objects if o.type == 'MESH' and len(o.data.polygons)]


def _scene_extent(arrays):
    """Plus grande dimension de la boîte englobante d'une liste de tableaux de points."""
    pts = [np.asarray(a, dtype=np.float64).reshape(-1, 3) for a in arrays if len(a)]
    if not pts:
        return 1.0
    allp = np.vstack(pts)
    return float(np.ptp(allp, axis=0).max()) or 1.0


def _drop_collinear(P, closed, tol):
    """Retire les points alignés avec leurs voisins (à tol près) : les diagonales de la triangulation n'ajoutent pas de
    sommets aux courbes de section et d'intersection."""
    P = [np.asarray(p, dtype=np.float64) for p in P]
    changed = True
    while changed and len(P) > (3 if closed else 2):
        changed = False
        n = len(P)
        out = []
        for i in range(n):
            if not closed and i in (0, n - 1):
                out.append(P[i])
                continue
            a = out[-1] if out else P[i - 1]
            b, c = P[i], P[(i + 1) % n]
            ac = c - a
            L = np.linalg.norm(ac)
            if L < 1e-300:
                out.append(b)
                continue
            if np.linalg.norm(np.cross(b - a, ac)) / L <= tol and 0.0 <= (b - a).dot(ac) <= L * L:
                changed = True
                continue
            out.append(b)
        if len(out) < (3 if closed else 2):
            break
        P = out
    return P


def _edge_chains(edges):
    """Chaînes ([BMVert], fermée) formées par des arêtes ; elles s'arrêtent aux sommets où plus de deux arêtes se rencontrent."""
    adj = {}
    for e in edges:
        for v in e.verts:
            adj.setdefault(v, []).append(e)
    left = set(edges)
    chains = []

    def walk(e, v):
        out = [v]
        while True:
            left.discard(e)
            v = e.other_vert(v)
            out.append(v)
            nxt = [x for x in adj[v] if x in left]
            if len(adj[v]) != 2 or not nxt:
                return out
            e = nxt[0]

    ends = [v for v, es in adj.items() if len(es) != 2]
    for v in ends:
        for e in adj[v]:
            if e in left:
                chains.append((walk(e, v), False))
    while left:
        e = next(iter(left))
        ring = walk(e, e.verts[0])
        closed = ring[0] is ring[-1]
        chains.append((ring[:-1] if closed else ring, closed))
    return chains


def _make_points(context, pts, name="Point"):
    """Objets point (comme l'outil Point) aux positions monde pts."""
    try:
        size = max(context.region_data.view_distance * 0.012, 1e-6)
    except (AttributeError, ReferenceError, TypeError):
        size = 0.1
    out = []
    for p in pts:
        obj = bpy.data.objects.new(name, None)
        obj.empty_display_type = 'PLAIN_AXES'
        obj.empty_display_size = size
        obj.location = Vector(p)
        context.view_layer.active_layer_collection.collection.objects.link(obj)
        out.append(obj)
    return out


def _world_tris(obj, dg):
    """Triangles (m,3,3) du maillage évalué de obj, en coordonnées monde."""
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    try:
        me.calc_loop_triangles()
        nv, nt = len(me.vertices), len(me.loop_triangles)
        V = np.empty(nv * 3, dtype=np.float64)
        me.vertices.foreach_get("co", V)
        T = np.empty(nt * 3, dtype=np.int32)
        me.loop_triangles.foreach_get("vertices", T)
    finally:
        ev.to_mesh_clear()
    V = V.reshape(-1, 3)
    M = np.array(obj.matrix_world, dtype=np.float64)
    V = V @ M[:3, :3].T + M[:3, 3]
    return V[T.reshape(-1, 3)]


def _plane_sides(d):
    """Côté de chaque sommet par rapport au plan (distances d (m,3), zéro = sur le plan). Un triangle qui touche le plan
    par une arête sans le traverser compte comme coupé le long de cette arête, de quelque côté qu'il soit."""
    pos = d >= 0.0
    touch = pos.all(1) & (d == 0.0).any(1)
    if touch.any():
        pos[touch] = d[touch] > 0.0
    return pos


def _two_crossings(T, d, pos):
    """Pour des triangles T (m,3,3) traversés par un plan (distances signées d (m,3), côté positif pos (m,3)) :
    les deux points où le plan coupe les arêtes."""
    X = np.zeros((len(T), 3, 3))
    hit = np.zeros((len(T), 3), dtype=bool)
    for k, (i, j) in enumerate(((0, 1), (1, 2), (2, 0))):
        c = pos[:, i] != pos[:, j]
        den = d[:, i] - d[:, j]
        t = np.where(c, d[:, i] / np.where(c, den, 1.0), 0.0)
        X[:, k] = T[:, i] + (T[:, j] - T[:, i]) * t[:, None]
        hit[:, k] = c
    first = np.argmax(hit, axis=1)
    last = 2 - np.argmax(hit[:, ::-1], axis=1)
    r = np.arange(len(T))
    return X[r, first], X[r, last]


# ---- Pipe ----

PIPE_SHARP_DEG = 30.0       # au-delà de cet angle entre deux tronçons, l'onglet est une arête vive (ombrage)


def pipe_mesh(P, closed, radius, sides=48, cap=True):
    """Tube de rayon `radius` autour de la polyligne P : (sommets, faces, lisse par face, anneaux d'onglet vif), ou None.
    Le repère de la section suit la courbe sans torsion ; aux angles, coupe d'onglet dans le plan bissecteur : chaque
    tronçon garde exactement sa section et le volume vaut (aire de la section) x (longueur de l'axe)."""
    P = np.asarray(P, dtype=np.float64)
    keep = [0]
    for i in range(1, len(P)):
        if np.linalg.norm(P[i] - P[keep[-1]]) > 1e-9:
            keep.append(i)
    P = P[keep]
    if closed and len(P) > 2 and np.linalg.norm(P[0] - P[-1]) < 1e-9:
        P = P[:-1]
    n = len(P)
    if n < 2 or (closed and n < 3) or radius <= 0.0:
        return None
    seg = (np.roll(P, -1, axis=0) - P) if closed else (P[1:] - P[:-1])
    D = seg / np.linalg.norm(seg, axis=1)[:, None]
    ns = len(D)
    d0 = Vector(D[0])
    x = d0.orthogonal().normalized()
    frames = []                 # repère (x, y) de la section sur chaque tronçon
    for k in range(ns):
        dk = Vector(D[k])
        if k:
            x = Vector(D[k - 1]).rotation_difference(dk) @ x
            x = (x - dk * x.dot(dk)).normalized()
        frames.append((x.copy(), dk.cross(x).normalized()))
    twist = 0.0
    if closed:
        # tour complet : le repère revenu au départ peut avoir tourné (courbe gauche) ; on répartit l'écart
        xr = Vector(D[ns - 1]).rotation_difference(d0) @ frames[-1][0]
        x0, y0 = frames[0]
        twist = math.atan2(xr.dot(y0), xr.dot(x0))
        if abs(twist) > 1e-12:
            for k in range(ns):
                a = -twist * k / ns
                fx, fy = frames[k]
                x2 = fx * math.cos(a) + fy * math.sin(a)
                frames[k] = (x2, Vector(D[k]).cross(x2).normalized())
    ang = [TAU * j / sides for j in range(sides)]
    cs = [(math.cos(a), math.sin(a)) for a in ang]
    rings, sharp = [], []
    cos_sharp = math.cos(math.radians(PIPE_SHARP_DEG))
    for i in range(n):
        k_in = (i - 1) % ns if (closed or i > 0) else 0
        k_out = i % ns if (closed or i < n - 1) else ns - 1
        d_in, d_out = Vector(D[k_in]), Vector(D[k_out])
        fx, fy = frames[k_in]
        if k_in != k_out and d_in.dot(d_out) < cos_sharp:
            sharp.append(i)
        c = Vector(P[i])
        b = d_in + d_out
        mitre = b.length > 1e-9 and k_in != k_out
        if mitre:
            b.normalize()
            den = d_in.dot(b)
            mitre = den > 0.2          # demi-tour presque complet : pas d'onglet (il partirait à l'infini)
        ring = []
        for ca, sa in cs:
            q = c + (fx * ca + fy * sa) * radius
            if mitre:
                q = q - d_in * ((q - c).dot(b) / den)
            ring.append(q)
        rings.append(ring)
    verts = [q for ring in rings for q in ring]
    faces, smooth = [], []
    for i in range(n - 1 if not closed else n):
        a0 = i * sides
        b0 = ((i + 1) % n) * sides
        for j in range(sides):
            j2 = (j + 1) % sides
            faces.append((a0 + j, a0 + j2, b0 + j2, b0 + j))
            smooth.append(True)
    if not closed and cap:
        faces.append(tuple(reversed(range(sides))))
        faces.append(tuple(range((n - 1) * sides, n * sides)))
        smooth += [False, False]
    return verts, faces, smooth, sharp


class DESSIN_OT_pipe(bpy.types.Operator):
    bl_idname = "dessin.pipe"
    bl_label = "Pipe"
    bl_description = ("Like Pipe: creates a tube around the selected curves (radius, flat caps). Polylines get mitred corners, "
                      "closed curves give a closed ring")
    bl_options = {'REGISTER', 'UNDO'}

    radius: bpy.props.FloatProperty(name="Radius", default=0.1, min=1e-6, subtype='DISTANCE', unit='LENGTH')
    cap: bpy.props.BoolProperty(name="Cap ends", default=True, description="Closes the ends of open curves (solid)")
    delete_input: bpy.props.BoolProperty(name="Delete input", default=False)

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def invoke(self, context, event):
        if not _curve_targets(context):
            return nothing_done(self, "Pipe: click the curves first, then Enter")
        return context.window_manager.invoke_props_dialog(self, width=260)

    def execute(self, context):
        objs = _curve_targets(context)
        if not objs:
            return nothing_done(self, "Pipe: click the curves first, then Enter")
        dg = context.evaluated_depsgraph_get()
        sides = max(12, int(round(48 * curve_quality_factor())))
        made = []
        for o in objs:
            V, F, S, ring_of = [], [], [], {}
            for P, closed in object_paths(o, dg):
                built = pipe_mesh(P, closed, self.radius, sides, self.cap)
                if built is None:
                    continue
                base = len(V)
                V += built[0]
                F += [tuple(base + i for i in f) for f in built[1]]
                S += built[2]
                for r in built[3]:
                    for j in range(sides):
                        ring_of[base + r * sides + j] = base + r * sides
            if not F:
                continue
            origin = V[0].copy()
            pipe = build_solid(context, "Pipe", V, F, S, origin)
            if ring_of:
                # onglets : arêtes vives, sinon l'ombrage lisse arrondit visuellement l'angle
                for e in pipe.data.edges:
                    a, b = e.vertices
                    if ring_of.get(a, -1) == ring_of.get(b, -2):
                        e.use_edge_sharp = True
                pipe.data.update()
            made.append(pipe)
        if not made:
            self.report({'WARNING'}, "No pipe could be built from the selection")
            return {'CANCELLED'}
        if self.delete_input:
            delete_objects(objs)
        _select_only(context, made)
        msg = f"Pipe: {len(made)} object(s), radius {self.radius / unit_scale_of(context):.4g}"
        cmd_log(msg)
        self.report({'INFO'}, msg)
        return {'FINISHED'}


# ---- Intersect ----

def _tri_tri_segments(A, B, eps):
    """Segments d'intersection des paires de triangles A[i] / B[i] ((m,3,3)) : (P, Q) (k,3) pour les paires qui se coupent."""
    if not len(A):
        return np.zeros((0, 3)), np.zeros((0, 3))
    nA = np.cross(A[:, 1] - A[:, 0], A[:, 2] - A[:, 0])
    nB = np.cross(B[:, 1] - B[:, 0], B[:, 2] - B[:, 0])
    la, lb = np.linalg.norm(nA, axis=1), np.linalg.norm(nB, axis=1)
    ok = (la > 1e-300) & (lb > 1e-300)
    nA = nA / np.where(ok, la, 1.0)[:, None]
    nB = nB / np.where(ok, lb, 1.0)[:, None]
    dA = np.einsum('mij,mj->mi', A - B[:, :1], nB)
    dB = np.einsum('mij,mj->mi', B - A[:, :1], nA)
    dA[np.abs(dA) < eps] = 0.0
    dB[np.abs(dB) < eps] = 0.0
    pA, pB = _plane_sides(dA), _plane_sides(dB)
    D = np.cross(nA, nB)
    ld = np.linalg.norm(D, axis=1)
    ok &= pA.any(1) & ~pA.all(1) & pB.any(1) & ~pB.all(1) & (ld > 1e-12)
    if not ok.any():
        return np.zeros((0, 3)), np.zeros((0, 3))
    A, B, dA, dB, pA, pB, D, ld = A[ok], B[ok], dA[ok], dB[ok], pA[ok], pB[ok], D[ok], ld[ok]
    a0, a1 = _two_crossings(A, dA, pA)
    b0, b1 = _two_crossings(B, dB, pB)
    ta0, ta1 = np.einsum('mj,mj->m', a0, D), np.einsum('mj,mj->m', a1, D)
    tb0, tb1 = np.einsum('mj,mj->m', b0, D), np.einsum('mj,mj->m', b1, D)
    sw = ta0 > ta1
    a0, a1 = np.where(sw[:, None], a1, a0), np.where(sw[:, None], a0, a1)
    ta0, ta1 = np.minimum(ta0, ta1), np.maximum(ta0, ta1)
    sw = tb0 > tb1
    b0, b1 = np.where(sw[:, None], b1, b0), np.where(sw[:, None], b0, b1)
    tb0, tb1 = np.minimum(tb0, tb1), np.maximum(tb0, tb1)
    lo, hi = np.maximum(ta0, tb0), np.minimum(ta1, tb1)
    keep = (hi - lo) > eps * ld
    P = np.where((ta0 >= tb0)[:, None], a0, b0)
    Q = np.where((ta1 <= tb1)[:, None], a1, b1)
    return P[keep], Q[keep]


def _segments_to_chains(P, Q, tol):
    """Raccorde des segments (P[i], Q[i]) en polylignes [(points, fermée)], points alignés retirés."""
    if not len(P):
        return []
    seen, paths = set(), []
    k = 1.0 / max(tol, 1e-300)
    for p, q in zip(P, Q):
        if np.linalg.norm(q - p) <= tol:
            continue
        a, b = tuple(np.round(p * k).astype(np.int64)), tuple(np.round(q * k).astype(np.int64))
        key = (a, b) if a <= b else (b, a)
        if key in seen:
            continue            # même segment vu depuis deux triangles voisins (arête posée sur le plan de coupe)
        seen.add(key)
        paths.append((np.array([p, q]), False))
    chains, _open = chain_open_paths(paths, tol, keep_open=True)      # les courbes ouvertes comptent (surfaces ouvertes)
    out = []
    for C, closed in chains:
        C = _drop_collinear(C, closed, tol * 0.1)
        if len(C) >= 2:
            out.append((C, closed))
    return out


def _seg_seg_points(A, B, tol):
    """Points où les polylignes A et B (tableaux (n,3)) se croisent (distance entre segments < tol)."""
    A0, A1, B0, B1 = A[:-1], A[1:], B[:-1], B[1:]
    pts = []
    step = max(1, int(2e6 // max(len(B0), 1)))
    for s in range(0, len(A0), step):
        a0, a1 = A0[s:s + step], A1[s:s + step]
        d1 = (a1 - a0)[:, None, :]
        d2 = (B1 - B0)[None, :, :]
        r = a0[:, None, :] - B0[None, :, :]
        a = (d1 * d1).sum(-1)
        e = (d2 * d2).sum(-1)
        b = (d1 * d2).sum(-1)
        c = (d1 * r).sum(-1)
        f = (d2 * r).sum(-1)
        den = a * e - b * b
        par = den <= 1e-12 * a * e                  # segments parallèles : pas de point de croisement
        sp = np.clip(np.where(par, 0.0, (b * f - c * e) / np.where(par, 1.0, den)), 0.0, 1.0)
        tp = np.clip((b * sp + f) / np.where(e > 0, e, 1.0), 0.0, 1.0)
        sp = np.clip((b * tp - c) / np.where(a > 0, a, 1.0), 0.0, 1.0)
        X = a0[:, None, :] + d1 * sp[..., None]
        Y = B0[None, :, :] + d2 * tp[..., None]
        hit = (np.linalg.norm(X - Y, axis=-1) < tol) & ~par
        if hit.any():
            pts += list(((X + Y) * 0.5)[hit])
    return pts


def _dedupe_points(pts, tol):
    out = []
    for p in pts:
        if all(np.linalg.norm(p - q) > tol for q in out):
            out.append(np.asarray(p, dtype=np.float64))
    return out


def intersect_objects(context, objs):
    """Intersections deux à deux : (chaînes de courbes [(points, fermée)], points)."""
    from mathutils.bvhtree import BVHTree
    dg = context.evaluated_depsgraph_get()
    meshes, curves = [], []
    for o in objs:
        if o.type == 'MESH' and len(o.data.polygons):
            T = _world_tris(o, dg)
            if len(T):
                meshes.append((o, T))
        else:
            paths = object_paths(o, dg) if o.type in {'CURVE', 'MESH'} else []
            if paths:
                curves.append((o, [np.vstack([P, P[:1]]) if c else np.asarray(P) for P, c in paths]))
    size = _scene_extent([T for _o, T in meshes] + [P for _o, ps in curves for P in ps])
    eps = 1e-9 * size
    tol = 1e-6 * size
    chains, points = [], []
    trees = {}

    def tree(i):
        if i not in trees:
            T = meshes[i][1]
            trees[i] = BVHTree.FromPolygons([tuple(p) for p in T.reshape(-1, 3)],
                                            [(3 * k, 3 * k + 1, 3 * k + 2) for k in range(len(T))])
        return trees[i]

    for i in range(len(meshes)):
        for j in range(i + 1, len(meshes)):
            pairs = set(tree(i).overlap(tree(j)))
            Tj = meshes[j][1]
            jit = np.array((0.577, 0.615, 0.537)) * (1e-6 * size)
            for sgn in (1.0, -1.0):
                # deux surfaces qui se touchent sans se traverser (arête posée sur une face) : un infime décalage les fait
                # se croiser, les segments sont ensuite calculés sur la géométrie exacte
                sh = BVHTree.FromPolygons([tuple(p) for p in (Tj + jit * sgn).reshape(-1, 3)],
                                          [(3 * k, 3 * k + 1, 3 * k + 2) for k in range(len(Tj))])
                pairs.update(tree(i).overlap(sh))
            if not pairs:
                continue
            pairs = list(pairs)
            ia = np.fromiter((p[0] for p in pairs), dtype=np.int64, count=len(pairs))
            ib = np.fromiter((p[1] for p in pairs), dtype=np.int64, count=len(pairs))
            P, Q = _tri_tri_segments(meshes[i][1][ia], meshes[j][1][ib], eps)
            chains += _segments_to_chains(P, Q, tol)
    for i in range(len(meshes)):
        t = tree(i)
        for _o, paths in curves:
            for P in paths:
                for a, b in zip(P[:-1], P[1:]):
                    d = b - a
                    L = float(np.linalg.norm(d))
                    if L < 1e-12:
                        continue
                    dv = Vector(d / L)
                    start = 0.0
                    while start < L:
                        loc, _n, _idx, dist = t.ray_cast(Vector(a) + dv * start, dv, L - start + tol)
                        if loc is None:
                            break
                        points.append(np.array(loc))
                        start += dist + max(tol, 1e-9)
    for i in range(len(curves)):
        for j in range(i + 1, len(curves)):
            for PA in curves[i][1]:
                for PB in curves[j][1]:
                    points += _seg_seg_points(PA, PB, tol)
    return chains, _dedupe_points(points, tol * 10.0)


class DESSIN_OT_intersect(bpy.types.Operator):
    bl_idname = "dessin.intersect"
    bl_label = "Intersect"
    bl_description = ("Like Intersect: creates the intersection of the selected objects with each other: curves where two "
                      "surfaces or solids cross, points where a curve crosses a surface or another curve")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        objs = [o for o in context.selected_objects if o.type in {'MESH', 'CURVE'}]
        if len(objs) < 2:
            return nothing_done(self, "Intersect: click at least two objects (surfaces, solids or curves), then Enter")
        chains, points = intersect_objects(context, objs)
        if not chains and not points:
            return nothing_done(self, "Intersect: the selected objects do not intersect")
        made = []
        if chains:
            made.append(build_polylines(context, "Intersection", [([Vector(p) for p in C], c) for C, c in chains]))
        made += _make_points(context, points)
        _select_only(context, made)
        msg = f"Intersect: {len(chains)} curve(s), {len(points)} point(s)"
        cmd_log(msg)
        self.report({'INFO'}, msg)
        return {'FINISHED'}


# ---- Section / Contour ----

class _Slicer:
    """Objets à couper par des plans parallèles : triangles et polylignes préparés une fois pour toutes."""

    def __init__(self, context, objs):
        dg = context.evaluated_depsgraph_get()
        self.tris, self.lines = [], []
        for o in objs:
            if o.type == 'MESH' and len(o.data.polygons):
                T = _world_tris(o, dg)
                if len(T):
                    self.tris.append(T)
            elif o.type in {'CURVE', 'MESH'}:
                for P, c in object_paths(o, dg):
                    self.lines.append(np.vstack([P, P[:1]]) if c else np.asarray(P))
        self.size = _scene_extent(self.tris + self.lines)
        self.no = None

    def empty(self):
        return not self.tris and not self.lines

    def set_normal(self, no):
        self.no = np.asarray(no, dtype=np.float64)
        self.no /= np.linalg.norm(self.no)
        self.h_tris = [T @ self.no for T in self.tris]
        self.h_lines = [P @ self.no for P in self.lines]

    def span(self):
        hs = [h.ravel() for h in self.h_tris] + self.h_lines
        allh = np.concatenate(hs)
        return float(allh.min()), float(allh.max())

    def cut(self, c):
        """Coupe par le plan (point . normale = c) : (chaînes [(points, fermée)], points)."""
        eps = 1e-9 * self.size
        tol = 1e-6 * self.size
        P, Q = [], []
        for T, h in zip(self.tris, self.h_tris):
            d = h - c
            d[np.abs(d) < eps] = 0.0
            pos = _plane_sides(d)                   # plan posé sur une face : on obtient son contour
            m = pos.any(1) & ~pos.all(1)
            if m.any():
                p, q = _two_crossings(T[m], d[m], pos[m])
                P.append(p)
                Q.append(q)
        chains = _segments_to_chains(np.vstack(P), np.vstack(Q), tol) if P else []
        pts = []
        for L, h in zip(self.lines, self.h_lines):
            d = h - c
            d[np.abs(d) < eps] = 0.0
            for i in np.nonzero((d[:-1] >= 0.0) != (d[1:] >= 0.0))[0]:
                t = d[i] / (d[i] - d[i + 1])
                pts.append(L[i] + (L[i + 1] - L[i]) * t)
        return chains, _dedupe_points(pts, tol * 10.0)


def _slice_targets(context):
    return [o for o in context.selected_objects if o.type in {'MESH', 'CURVE'}
            and "dessin_cotation" not in o.keys() and "dessin_cotation_texte" not in o.keys()]


class _SliceTool(DessinBase):
    """Base de Section et Contour (classe non enregistrée) : les objets sélectionnés au lancement sont coupés."""

    PLANAR = False
    NO_SELECTION = "Select the surfaces, solids or curves to cut first"

    def invoke(self, context, event):
        names = [o.name for o in _slice_targets(context)]
        if not names and event.type in {'MOUSEMOVE', 'LEFTMOUSE'} and self.active_dessin_tool(context) is not None:
            # bouton de la barre d'outils sans sélection : le survol n'affiche rien, un clic désigne l'objet à couper
            if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
                try:
                    bpy.ops.dessin.pick_object('INVOKE_DEFAULT')
                except RuntimeError:
                    pass
                if not _slice_targets(context):
                    cmd_notice(self.TITLE + ": " + self.NO_SELECTION)
                return {'CANCELLED'}
            return {'CANCELLED', 'PASS_THROUGH'}
        if not names:
            return nothing_done(self, self.TITLE + ": " + self.NO_SELECTION)
        self._targets = names
        return super().invoke(context, event)

    def slicer(self, context):
        objs = [bpy.data.objects[n] for n in self._targets if n in bpy.data.objects]
        return _Slicer(context, objs)

    def emit(self, context, name, cuts):
        """Crée un objet courbe par plan de coupe (et des points pour les courbes coupées)."""
        made, n_crv, n_pts = [], 0, 0
        for chains, pts in cuts:
            if chains:
                made.append(build_polylines(context, name, [([Vector(p) for p in C], c) for C, c in chains]))
                n_crv += len(chains)
            if pts:
                made += _make_points(context, pts)
                n_pts += len(pts)
        return made, n_crv, n_pts


class DESSIN_OT_section(_SliceTool):
    bl_idname = "dessin.section"
    bl_label = "Section"
    bl_description = ("Like Section: cuts the selected surfaces, solids and curves with a plane drawn as a line (two points, "
                      "the plane is perpendicular to the construction plane) and creates the section curves")

    TITLE = "Section"
    NEEDED = 2
    NUMFIELDS = 0

    def prompt(self):
        return "start of the section line" if not self.points else "end of the section line"

    def compute(self):
        if not self.points or self.cur is None:
            return [], [], "", None
        a, b = self.points[0], self.cur
        n = plane_axes(self.axis)[2]
        d = b - a
        d = d - n * d.dot(n)
        if d.length < 1e-9:
            return [], [], "", None
        return [a, a + d], [], f"Length {self.fmt(d.length)}", ("section", a.copy(), d.cross(n).normalized())

    def build(self, context, spec):
        _k, a, no = spec
        sl = self.slicer(context)
        if sl.empty():
            self.report({'WARNING'}, "Section: nothing to cut")
            return None
        sl.set_normal(no)
        made, n_crv, n_pts = self.emit(context, "Section", [sl.cut(float(Vector(a).dot(no)))])
        if not made:
            nothing_done(self, "Section: the plane does not cross the selected objects")
            return None
        _select_only(context, made)
        cmd_log(f"Section: {n_crv} curve(s)" + (f", {n_pts} point(s)" if n_pts else ""))
        return made[0]


CONTOUR_MAX = 2000      # nombre maximal de plans de coupe par commande


class DESSIN_OT_contour(_SliceTool):
    bl_idname = "dessin.contour"
    bl_label = "Contour"
    bl_description = ("Like Contour: creates evenly spaced section curves through the selected surfaces, solids and curves: "
                      "base point, a point giving the direction perpendicular to the cutting planes, then the spacing "
                      "(mouse or typed value, Enter)")

    TITLE = "Contour"
    NEEDED = 3
    NUMFIELDS = 1

    def prompt(self):
        if not self.points:
            return "contour plane base point"
        if len(self.points) == 1:
            return "direction perpendicular to the contour planes"
        return "distance between contours   (or type it then Enter)"

    def can_confirm_typed(self):
        return len(self.points) == 2

    def handle_typing(self, event):
        if len(self.points) < 2:
            if event.value == 'PRESS' and event.unicode and event.unicode in "0123456789.,-":
                return True        # pas de saisie avant l'étape « distance »
            return False
        return super().handle_typing(event)

    def compute(self):
        if not self.points or self.cur is None:
            return [], [], "", None
        a = self.points[0]
        if len(self.points) == 1:
            return [a, self.cur], [], "", None
        d = self.points[1] - a
        if d.length < 1e-9:
            return [], [], "", None
        no = d.normalized()
        step = abs((self.cur - a).dot(no))
        t = self.typed_value(0)
        if t is not None:
            step = abs(t)
        if step < 1e-9:
            return [a, self.points[1]], [], "", None
        side = no.orthogonal().normalized() * (step * 0.5)
        ticks = [[a + no * (step * k) - side, a + no * (step * k) + side] for k in range(0, 6)]
        return [a, a + no * (step * 5)], ticks, f"Distance {self.fmt(step)}", ("contour", a.copy(), no, step)

    def build(self, context, spec):
        _k, a, no, step = spec
        sl = self.slicer(context)
        if sl.empty():
            self.report({'WARNING'}, "Contour: nothing to cut")
            return None
        sl.set_normal(no)
        lo, hi = sl.span()
        c0 = float(Vector(a).dot(no))
        k0, k1 = math.ceil((lo - c0) / step - 1e-9), math.floor((hi - c0) / step + 1e-9)
        if k1 - k0 + 1 > CONTOUR_MAX:
            msg = f"Contour: {k1 - k0 + 1} planes at this distance (maximum {CONTOUR_MAX}): use a larger distance"
            self.report({'WARNING'}, msg)
            cmd_log(msg)
            return None
        made, n_crv, n_pts = self.emit(context, "Contour", [sl.cut(c0 + k * step) for k in range(k0, k1 + 1)])
        if not made:
            nothing_done(self, "Contour: no plane crosses the selected objects")
            return None
        _select_only(context, made)
        cmd_log(f"Contour: {n_crv} curve(s) on {k1 - k0 + 1} plane(s), distance {self.fmt(step)}"
                + (f", {n_pts} point(s)" if n_pts else ""))
        return made[0]

# ---- ExtractSrf / DupEdge : outils qui désignent une face au survol ----

def rhino_face(bm, f0):
    """La face au sens de Rhino qui contient la facette f0 : face courbe (cylindre, congé...) ou face plane."""
    return pp_curved_region(bm, f0) or pp_region(bm, f0)


def extract_face(context, obj, face_index, copy=False):
    """ExtractSrf : la face (au sens de Rhino) qui contient face_index devient un objet surface à part.
    Retourne (objet créé ou None, message)."""
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        bm.faces.ensure_lookup_table()
        bm.normal_update()
        if face_index < 0 or face_index >= len(bm.faces):
            return None, "face not found"
        faces = rhino_face(bm, bm.faces[face_index])
        if len(faces) == len(bm.faces):
            return None, "this object is a single surface: there is no face to extract"
        keep = {f.index for f in faces}
        nb = bm.copy()
        try:
            nb.faces.ensure_lookup_table()
            bmesh.ops.delete(nb, geom=[f for f in nb.faces if f.index not in keep], context='FACES')
            me = bpy.data.meshes.new("Surface")
            nb.to_mesh(me)
        finally:
            nb.free()
        for mat in obj.data.materials:
            me.materials.append(mat)
        new = bpy.data.objects.new("Surface", me)
        new.matrix_world = obj.matrix_world.copy()
        _link_like(new, obj)
        if not copy:
            bmesh.ops.delete(bm, geom=faces, context='FACES')
            bm.to_mesh(obj.data)
            obj.data.update()
        return new, ""
    finally:
        bm.free()


class _FacePickOp(bpy.types.Operator):
    """Base des outils qui désignent une face d'un objet au survol (classe non enregistrée)."""

    bl_options = {'REGISTER', 'UNDO'}
    stage = 'PICK'
    hit_face = DESSIN_OT_pushpull.hit_face

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D' and context.mode == 'OBJECT'

    def invoke(self, context, event):
        self.area = context.area
        self.region = find_window_region(self.area, event.mouse_x, event.mouse_y) or main_window_region(self.area)
        if self.region is None:
            return {'CANCELLED'}
        self.rv3d = region_rv3d(self.region, self.area)
        self.lines = []
        self.made = []
        self.copy = False
        self._hover = None
        self._h = bpy.types.SpaceView3D.draw_handler_add(pp_draw_cb, (self,), 'WINDOW', 'POST_VIEW')
        self.show_prompt()
        context.window_manager.modal_handler_add(self)
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS' and DessinBase.active_tool_id(context) == self.bl_idname + "_tool":
            self.modal(context, event)                  # bouton de la barre d'outils : le clic qui lance désigne déjà
        return {'RUNNING_MODAL'}

    def cleanup(self):
        if getattr(self, "_h", None) is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._h, 'WINDOW')
            self._h = None
        set_prompt(self.area, None)
        try:
            self.area.tag_redraw()
        except ReferenceError:
            pass

    def done(self, context):
        self.cleanup()
        made = [bpy.data.objects[n] for n in self.made if n in bpy.data.objects]
        if made:
            _select_only(context, made)
            return {'FINISHED'}
        return {'CANCELLED'}

    def modal(self, context, event):
        if event.value == 'PRESS' and event.type in {'ESC', 'RET', 'NUMPAD_ENTER', 'SPACE'}:
            return self.done(context)
        if event.type in NAV_TYPES or event.type.startswith('TRACKPAD'):
            return {'PASS_THROUGH'}
        region = find_window_region(self.area, event.mouse_x, event.mouse_y)
        if region is None:
            return {'RUNNING_MODAL'}
        mx, my = event.mouse_x - region.x, event.mouse_y - region.y
        if event.type == 'C' and event.value == 'PRESS' and self.HAS_COPY:
            self.copy = not self.copy
            self.show_prompt()
            return {'RUNNING_MODAL'}
        if event.type == 'MOUSEMOVE' or (event.type == 'LEFTMOUSE' and event.value == 'PRESS'):
            self.region = region
            h = self.hit_face(context, region, mx, my)
            ok = h is not None and h[0] != "modifiers" and len(h) == 3
            if event.type == 'MOUSEMOVE':
                self.lines = self.hover(context, *h) if ok else []
                self.area.tag_redraw()
                return {'RUNNING_MODAL'}
            if h is not None and h[0] == "modifiers":
                cmd_log(self.bl_label + ": apply the modifiers of this object first")
            elif ok:
                self.pick(context, *h)
                self.lines = []
                self.show_prompt()
                self.area.tag_redraw()
            return {'RUNNING_MODAL'}
        return {'RUNNING_MODAL'}


def _face_outline(obj, idx):
    """Pourtour (segments monde) de la face au sens de Rhino qui contient la facette idx."""
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        bm.faces.ensure_lookup_table()
        bm.normal_update()
        faces = rhino_face(bm, bm.faces[idx])
        mw = obj.matrix_world
        edges = pp_boundary(faces) or [e for f in faces for e in f.edges][:PP_PREVIEW_EDGES]
        segs = []
        for e in edges:
            segs += [mw @ e.verts[0].co, mw @ e.verts[1].co]
        return segs
    finally:
        bm.free()


class DESSIN_OT_extract_srf(_FacePickOp):
    bl_idname = "dessin.extract_srf"
    bl_label = "Extract Surface"
    bl_description = ("Like ExtractSrf: click the faces of a solid or a polysurface to detach them as separate surfaces "
                      "(C: copy, the object stays whole). Enter or Esc to finish")

    HAS_COPY = True

    def show_prompt(self):
        n = len(self.made)
        set_prompt(self.area, "Extract Surface: click a face" + (f"  ({n} extracted)" if n else "")
                   + f"  |  C: copy = {'yes' if self.copy else 'no'}  |  Enter / Esc: finish")

    def hover(self, context, obj, idx, loc):
        key = (obj.name, idx)
        if self._hover is None or self._hover[0] != key:
            self._hover = (key, _face_outline(obj, idx))
        return self._hover[1]

    def pick(self, context, obj, idx, loc):
        new, msg = extract_face(context, obj, idx, self.copy)
        self._hover = None
        if new is None:
            cmd_log("Extract Surface: " + msg)
            self.report({'INFO'}, "Extract Surface: " + msg)
            return
        self.made.append(new.name)
        cmd_log("Extract Surface: 1 face " + ("copied" if self.copy else "extracted"))


def _is_feature_edge(e, lay):
    """Arête au sens de Rhino : bord libre, arête vive entre deux faces, ou découpe (Offset Edge / PushPull)."""
    if len(e.link_faces) != 2 or (lay is not None and e[lay]):
        return True
    f, g = e.link_faces
    if g.normal.dot(f.normal) > 1.0 - 1e-6:
        return False
    try:
        return not (e.smooth and not e.seam and e.calc_face_angle() <= math.radians(EXPLODE_SHARP_DEG))
    except ValueError:
        return True


def feature_edge_chain(bm, e0):
    """L'arête au sens de Rhino qui passe par e0 : la suite d'arêtes vives ou libres, arrêtée aux sommets où trois arêtes
    vives se rencontrent et aux angles marqués. Retourne ([BMVert], fermée)."""
    lay = bm.edges.layers.int.get(IMPRINT_LAYER)
    cos_lim = math.cos(math.radians(EXPLODE_SHARP_DEG))

    def extend(e, v):
        out = []
        seen = {e0}
        while True:
            cand = [x for x in v.link_edges if x is not e and _is_feature_edge(x, lay)]
            if len(cand) != 1 or cand[0] in seen:
                return out, (len(cand) == 1 and cand[0] is e0)
            x = cand[0]
            d1 = (v.co - e.other_vert(v).co).normalized()
            d2 = (x.other_vert(v).co - v.co).normalized()
            if d1.dot(d2) < cos_lim:
                return out, False
            seen.add(x)
            v = x.other_vert(v)
            out.append(v)
            e = x

    a, b = e0.verts
    fwd, closed = extend(e0, b)
    if closed:
        return [a, b] + fwd[:-1], True
    back, _c = extend(e0, a)
    return list(reversed(back)) + [a, b] + fwd, False


def _nearest_feature_chain(obj, bm, cache, idx, loc):
    """Arête (au sens de Rhino) la plus proche du point monde loc sur le pourtour de la face visée : (points monde, fermée)."""
    bound = cache.get(idx)
    if bound is None:
        bound = cache[idx] = pp_boundary(rhino_face(bm, bm.faces[idx]))
    if not bound:
        return None
    mw = obj.matrix_world
    p = Vector(loc)
    best, bd = None, 1e300
    for e in bound:
        a, b = mw @ e.verts[0].co, mw @ e.verts[1].co
        t = min(1.0, max(0.0, geometry.intersect_point_line(p, a, b)[1]))
        d = (p - (a + (b - a) * t)).length
        if d < bd:
            best, bd = e, d
    chain, closed = feature_edge_chain(bm, best)
    return [mw @ v.co for v in chain], closed


class DESSIN_OT_dup_edge(_FacePickOp):
    bl_idname = "dessin.dup_edge"
    bl_label = "Duplicate Edge"
    bl_description = ("Like DupEdge: click near an edge of a surface or a solid to create a curve on it (the edge under "
                      "the cursor lights up). Enter or Esc to finish")

    HAS_COPY = False

    def show_prompt(self):
        n = len(self.made)
        set_prompt(self.area, "Duplicate Edge: click near an edge" + (f"  ({n} created)" if n else "") + "  |  Enter / Esc: finish")

    def free_bm(self):
        c = getattr(self, "_bmc", None)
        if c is not None:
            c[1].free()
        self._bmc = None

    def cleanup(self):
        self.free_bm()
        super().cleanup()

    def chain(self, obj, idx, loc):
        c = getattr(self, "_bmc", None)
        try:
            if c is None or c[0] != obj.name:
                self.free_bm()
                bm = bmesh.new()
                bm.from_mesh(obj.data)
                bm.faces.ensure_lookup_table()
                bm.normal_update()
                c = self._bmc = (obj.name, bm, {})
            return _nearest_feature_chain(obj, c[1], c[2], idx, loc)
        except (RuntimeError, ReferenceError, ValueError, IndexError):
            return None

    def hover(self, context, obj, idx, loc):
        c = self.chain(obj, idx, loc)
        if c is None:
            return []
        P, closed = c
        lines = []
        for a, b in zip(P, P[1:] + (P[:1] if closed else [])):
            lines += [a, b]
        return lines

    def pick(self, context, obj, idx, loc):
        c = self.chain(obj, idx, loc)
        if c is None:
            cmd_log("Duplicate Edge: this face has no edge (closed smooth surface)")
            return
        P, closed = c
        crv = build_polyline(context, "Edge", P, closed)
        self.made.append(crv.name)
        cmd_log("Duplicate Edge: 1 curve created")


# ---- DupBorder ----

def border_chains(obj):
    """Bords libres d'un maillage : [(points monde, fermée)]."""
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        mw = obj.matrix_world
        naked = [e for e in bm.edges if len(e.link_faces) == 1]
        return [([mw @ v.co for v in chain], closed) for chain, closed in _edge_chains(naked) if len(chain) >= 2]
    finally:
        bm.free()


class DESSIN_OT_dup_border(bpy.types.Operator):
    bl_idname = "dessin.dup_border"
    bl_label = "Duplicate Border"
    bl_description = ("Like DupBorder: creates curves on the free borders of the selected surfaces and open polysurfaces "
                      "(a closed solid has no border)")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        objs = _mesh_targets(context)
        if not objs:
            return nothing_done(self, "Duplicate Border: click the surfaces first, then Enter")
        made, n = [], 0
        for o in objs:
            chains = border_chains(o)
            if chains:
                crv = build_polylines(context, "Border", chains)
                made.append(crv)
                n += len(chains)
        if not made:
            return nothing_done(self, "Duplicate Border: a closed solid has no free border  ·  "
                                      "use Duplicate Edge (DupEdge) to copy one of its edges")
        _select_only(context, made)
        msg = f"Duplicate Border: {n} curve(s)"
        cmd_log(msg)
        self.report({'INFO'}, msg)
        return {'FINISHED'}


# ---- MergeAllFaces ----

MERGE_COPLANAR_DEG = 0.1        # angle sous lequel deux facettes voisines sont dans le même plan (en simple précision, deux
                                # normales identiques peuvent déjà différer de 0,03° ; un cercle très fin fait 0,94° par côté)


def merge_coplanar_faces(obj):
    """Réunit les faces coplanaires voisines (comme MergeAllCoplanarFaces). Retourne (faces avant, faces après)."""
    me = obj.data
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        n0 = len(bm.faces)
        closed0 = bool(bm.edges) and all(len(e.link_faces) == 2 for e in bm.edges)
        vol0 = bm.calc_volume() if closed0 else 0.0
        area0 = sum(f.calc_area() for f in bm.faces)
        bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(MERGE_COPLANAR_DEG), use_dissolve_boundaries=False,
                                 verts=bm.verts[:], edges=bm.edges[:], delimit={'MATERIAL'})
        n1 = len(bm.faces)
        if n1 >= n0:
            return n0, n0
        if abs(sum(f.calc_area() for f in bm.faces) - area0) > 1e-6 * max(area0, 1e-12):
            return n0, n0               # la forme changerait : on ne touche à rien
        if closed0:
            ok = all(len(e.link_faces) == 2 for e in bm.edges)
            if not ok or abs(bm.calc_volume() - vol0) > 1e-6 * max(abs(vol0), 1e-12):
                return n0, n0           # le résultat ne serait plus le même solide : on ne touche à rien
        bm.normal_update()
        bm.to_mesh(me)
        me.update()
        return n0, n1
    finally:
        bm.free()


class DESSIN_OT_merge_faces(bpy.types.Operator):
    bl_idname = "dessin.merge_faces"
    bl_label = "Merge All Faces"
    bl_description = ("Like MergeAllCoplanarFaces: merges the neighbouring faces of the selected objects that lie in the "
                      "same plane (after Booleans, PushPull or Offset Edge cuts)")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        objs = _mesh_targets(context)
        if not objs:
            return nothing_done(self, "Merge All Faces: click the solids or surfaces first, then Enter")
        a = b = 0
        for o in objs:
            n0, n1 = merge_coplanar_faces(o)
            a += n0
            b += n1
        if b >= a:
            return nothing_done(self, "Merge All Faces: no coplanar faces to merge")
        msg = f"Merge All Faces: {a} faces -> {b}"
        cmd_log(msg)
        self.report({'INFO'}, msg)
        return {'FINISHED'}


# ---- Unroll ----

def unroll_mesh(obj):
    """Déplie à plat le maillage de obj (surface développable ou polyèdre) en gardant longueurs et aires.
    Retourne (points 2D [(x, y)], faces, aire) ou (None, None, message)."""
    import heapq
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        bm.transform(obj.matrix_world)
        bm.normal_update()
        if not bm.faces:
            return None, None, "this object has no face"
        size = max((max(v.co[i] for v in bm.verts) - min(v.co[i] for v in bm.verts)) for i in range(3)) or 1.0
        warped = [f for f in bm.faces if len(f.verts) > 3
                  and max(abs((v.co - f.verts[0].co).dot(f.normal)) for v in f.verts) > 1e-6 * size]
        if warped:
            bmesh.ops.triangulate(bm, faces=warped)       # facettes gauches : dépliées triangle par triangle
            bm.normal_update()
        bm.faces.ensure_lookup_table()
        sharp = math.radians(EXPLODE_SHARP_DEG)

        def soft(e):
            if len(e.link_faces) != 2:
                return False
            f, g = e.link_faces
            if g.normal.dot(f.normal) > 1.0 - 1e-6:
                return True
            try:
                return e.smooth and e.calc_face_angle() <= sharp
            except ValueError:
                return False

        # une surface à double courbure (sphère, selle) ne se déplie pas : autour d'un sommet intérieur d'une face lisse,
        # les angles doivent faire un tour complet (sauf au sommet d'un cône, éventail de triangles)
        curved, apex = 0.0, 0
        for v in bm.verts:
            if not v.link_faces or any(not soft(e) for e in v.link_edges):
                continue          # sommet sur un bord libre ou une arête vive : il se déplie toujours
            d = abs(TAU - sum(l.calc_angle() for l in v.link_loops))
            if d <= 3e-4:
                continue
            if d > 0.02 and all(len(f.verts) == 3 for f in v.link_faces):
                apex += 1
            else:
                curved += d
        if curved > 0.02 or apex > 2:
            return None, None, ("this surface is not developable (it curves in two directions, like a sphere): "
                                "it cannot be unrolled without stretching")
        pts, faces2 = [], []
        placed = {}                 # face -> {sommet: indice du point 2D}
        order = 0
        for seed in sorted(bm.faces, key=lambda f: -f.calc_area()):
            if seed in placed:
                continue
            # première facette de la pièce : posée à plat, son premier bord sur l'axe X
            v0, v1 = seed.verts[0], seed.verts[1]
            ex = (v1.co - v0.co).normalized()
            ey = seed.normal.cross(ex).normalized()
            off = (max(p[0] for p in pts) + 0.05 * size) if pts else 0.0
            ids = {}
            for v in seed.verts:
                d = v.co - v0.co
                ids[v] = len(pts)
                pts.append((off + d.dot(ex), d.dot(ey)))
            placed[seed] = ids
            faces2.append([ids[v] for v in seed.verts])
            heap = []
            for e in seed.edges:
                heapq.heappush(heap, (0 if soft(e) else 1, order, e, seed))
                order += 1
            while heap:
                _c, _o, e, par = heapq.heappop(heap)
                kids = [g for g in e.link_faces if g is not par and g not in placed]
                if not kids:
                    continue
                child = kids[0]
                a, b = e.verts
                pid = placed[par]
                A2, B2 = Vector(pts[pid[a]]), Vector(pts[pid[b]])
                L = (b.co - a.co).length
                if L < 1e-12:
                    continue
                ex3 = (b.co - a.co) / L
                ey3 = child.normal.cross(ex3).normalized()
                ex2 = (B2 - A2).normalized()
                ey2 = Vector((-ex2.y, ex2.x))
                # le parent est d'un côté de l'arête, l'enfant se rabat de l'autre
                pc = sum((Vector(pts[i]) for i in pid.values()), Vector((0.0, 0.0))) / len(pid)
                par_side = 1.0 if (pc - A2).dot(ey2) > 0 else -1.0
                cc = child.calc_center_median()
                ch_side = 1.0 if (cc - a.co).dot(ey3) > 0 else -1.0
                k = -par_side * ch_side
                ids = {a: pid[a], b: pid[b]}
                for v in child.verts:
                    if v in ids:
                        continue
                    d = v.co - a.co
                    q = A2 + ex2 * d.dot(ex3) + ey2 * (d.dot(ey3) * k)
                    ids[v] = len(pts)
                    pts.append((q.x, q.y))
                placed[child] = ids
                faces2.append([ids[v] for v in child.verts])
                for e2 in child.edges:
                    if e2 is not e:
                        heapq.heappush(heap, (0 if soft(e2) else 1, order, e2, child))
                        order += 1
        area = sum(f.calc_area() for f in bm.faces)
        return pts, faces2, area
    finally:
        bm.free()


class DESSIN_OT_unroll(bpy.types.Operator):
    bl_idname = "dessin.unroll"
    bl_label = "Unroll Surface"
    bl_description = ("Like UnrollSrf: flattens the selected developable surfaces (cylinder, cone, ruled or folded surface, "
                      "faces of a box) onto the construction plane, keeping lengths and areas. The flat pattern is "
                      "placed next to the object")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        objs = _mesh_targets(context)
        if not objs:
            return nothing_done(self, "Unroll Surface: click the surfaces first, then Enter")
        try:
            axis = drawing_axis(context.region_data) if context.region_data is not None else 2
        except (AttributeError, ReferenceError, TypeError):
            axis = 2
        u, v, n = plane_axes(axis)
        o0 = plane_origin(axis)
        made, errors = [], []
        for o in objs:
            pts, faces, info = unroll_mesh(o)
            if pts is None:
                errors.append(f"{o.name}: {info}")
                continue
            bb = [o.matrix_world @ Vector(c) for c in o.bound_box]
            us, vs = [(p - o0).dot(u) for p in bb], [(p - o0).dot(v) for p in bb]
            gap = 0.1 * max(max(us) - min(us), max(vs) - min(vs), 1e-6)
            x0 = min(p[0] for p in pts)
            y0 = min(p[1] for p in pts)
            base = o0 + u * (max(us) + gap) + v * min(vs)
            V = [base + u * (p[0] - x0) + v * (p[1] - y0) for p in pts]
            flat = mesh_object_from_arrays(context, "Unrolled", V, faces, V[0], False)
            made.append(flat)
            fa = sum(p.area for p in flat.data.polygons)
            cmd_log(f"Unroll: {o.name}: area {info:.6g} -> {fa:.6g}")
        for e in errors:
            cmd_log("Unroll: " + e)
        if not made:
            return nothing_done(self, "Unroll: " + (errors[0] if errors else "nothing to unroll"))
        _select_only(context, made)
        self.report({'INFO'}, f"Unroll: {len(made)} flat pattern(s) created" + (f", {len(errors)} refused" if errors else ""))
        return {'FINISHED'}


# ---- RebuildSrf ----

def mesh_grid(bm):
    """Grille de sommets d'une surface faite de quadrilatères en damier régulier (loft, balayage, extrusion, révolution).
    Retourne (lignes [[BMVert]], lignes fermées ?) ou None."""
    if not bm.faces or any(len(f.verts) != 4 for f in bm.faces):
        return None
    naked = [e for e in bm.edges if len(e.link_faces) == 1]
    if not naked:
        return None
    nk = set(naked)
    corners = [v for v in bm.verts if len(v.link_faces) == 1]
    closed = False
    if len(corners) == 4:
        start = corners[0]
        e = [x for x in start.link_edges if x in nk][0]
        row = [start]
        v = start
        while True:
            v = e.other_vert(v)
            row.append(v)
            if len(v.link_faces) == 1:
                break
            nxt = [x for x in v.link_edges if x in nk and x is not e]
            if not nxt:
                return None
            e = nxt[0]
    elif not corners:
        start = naked[0].verts[0]
        e = naked[0]
        row = [start]
        v = start
        while True:
            v = e.other_vert(v)
            if v is start:
                break
            row.append(v)
            nxt = [x for x in v.link_edges if x in nk and x is not e]
            if not nxt:
                return None
            e = nxt[0]
        closed = True
    else:
        return None
    rows = [row]
    used = set(row)
    while True:
        nxt_row = []
        for v in rows[-1]:
            cand = [e.other_vert(v) for e in v.link_edges if e.other_vert(v) not in used]
            if len(cand) != 1:
                nxt_row = None
                break
            nxt_row.append(cand[0])
        if not nxt_row:
            break
        if len(set(nxt_row)) != len(nxt_row):
            return None
        used.update(nxt_row)
        rows.append(nxt_row)
    C, R = len(row), len(rows)
    if R < 2 or len(used) != len(bm.verts) or len(bm.faces) != (R - 1) * (C if closed else C - 1):
        return None
    return rows, closed


def _resample_axis0(G, n_new, closed):
    """Rééchantillonne le tableau G (K, ..., 3) le long de son premier axe par une spline de Catmull-Rom :
    n_new points (ouvert) ou n_new tronçons (fermé). La courbe passe par les points d'origine."""
    K = len(G)
    out = []
    count = n_new
    for i in range(count):
        u = (i * K / n_new) if closed else (i * (K - 1) / (n_new - 1))
        k = min(int(math.floor(u)), K - 1 if closed else K - 2)
        t = u - k
        p1, p2 = G[k % K], G[(k + 1) % K]
        p0 = G[(k - 1) % K] if (closed or k > 0) else 2 * G[0] - G[1]
        p3 = G[(k + 2) % K] if (closed or k + 2 < K) else 2 * G[K - 1] - G[K - 2]
        out.append(0.5 * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                          + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    return np.array(out)


def rebuild_surface(obj, n_u, n_v):
    """RebuildSrf : remaille la surface avec n_u points dans un sens et n_v dans l'autre (la forme est suivie par une
    spline passant par les sommets d'origine). Retourne (écart maximal, message)."""
    from mathutils.bvhtree import BVHTree
    me = obj.data
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        bm.normal_update()
        g = mesh_grid(bm)
        if g is None:
            return None, ("this surface is not a regular grid of quads (use it on lofts, sweeps, extrusions, revolutions, "
                          "planes and network surfaces)")
        rows, closed = g
        G = np.array([[tuple(v.co) for v in row] for row in rows], dtype=np.float64)       # (R, C, 3)
        R, C = G.shape[:2]
        n_u = max(3 if closed else 2, int(n_u))
        n_v = max(2, int(n_v))
        H = _resample_axis0(np.transpose(G, (1, 0, 2)), n_u, closed)           # (n_u, R, 3)
        H = _resample_axis0(np.transpose(H, (1, 0, 2)), n_v, False)            # (n_v, n_u, 3)
        ref_n = Vector(rows[0][0].link_faces[0].normal)
        smooth = sum(1 for f in bm.faces if f.smooth) * 2 >= len(bm.faces)
        old = BVHTree.FromBMesh(bm)
        old_pts = [v.co.copy() for v in bm.verts]
        bm.clear()
        vs = [[bm.verts.new(tuple(H[i, j])) for j in range(n_u)] for i in range(n_v)]
        cols = n_u if closed else n_u - 1
        for i in range(n_v - 1):
            for j in range(cols):
                j2 = (j + 1) % n_u
                f = bm.faces.new((vs[i][j], vs[i][j2], vs[i + 1][j2], vs[i + 1][j]))
                f.smooth = smooth
        bm.normal_update()
        bm.faces.ensure_lookup_table()
        if bm.faces[0].normal.dot(ref_n) < 0:
            bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
            bm.normal_update()
        new = BVHTree.FromBMesh(bm)
        dev = 0.0
        for p in old_pts:
            hit = new.find_nearest(p)
            if hit[0] is not None:
                dev = max(dev, hit[3])
        for v in bm.verts:
            hit = old.find_nearest(v.co)
            if hit[0] is not None:
                dev = max(dev, hit[3])
        bm.to_mesh(me)
        me.update()
        return dev * max(abs(s) for s in obj.scale), ""
    finally:
        bm.free()


class DESSIN_OT_rebuild_srf(bpy.types.Operator):
    bl_idname = "dessin.rebuild_srf"
    bl_label = "Rebuild Surface"
    bl_description = ("Like RebuildSrf: rebuilds the selected surfaces with a given number of points in each direction "
                      "(lofts, sweeps, extrusions, revolutions, planes, network surfaces). The maximum deviation is reported")
    bl_options = {'REGISTER', 'UNDO'}

    count_u: bpy.props.IntProperty(name="Point count U", default=10, min=2, max=2000)
    count_v: bpy.props.IntProperty(name="Point count V", default=10, min=2, max=2000)

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def invoke(self, context, event):
        objs = _mesh_targets(context)
        if not objs:
            return nothing_done(self, "Rebuild Surface: click the surface first, then Enter")
        bm = bmesh.new()
        try:
            bm.from_mesh(objs[0].data)
            g = mesh_grid(bm)
            if g is not None:
                self.count_u, self.count_v = len(g[0][0]), len(g[0])
        finally:
            bm.free()
        return context.window_manager.invoke_props_dialog(self, width=260)

    def execute(self, context):
        objs = _mesh_targets(context)
        if not objs:
            return nothing_done(self, "Rebuild Surface: click the surface first, then Enter")
        done, dev, err = 0, 0.0, ""
        for o in objs:
            d, msg = rebuild_surface(o, self.count_u, self.count_v)
            if d is None:
                err = f"{o.name}: {msg}"
                continue
            done += 1
            dev = max(dev, d)
        if not done:
            return nothing_done(self, "Rebuild Surface: " + err)
        msg = f"Rebuild Surface: {done} surface(s), {self.count_u} x {self.count_v} points, max deviation {dev / unit_scale_of(context):.4g}"
        cmd_log(msg)
        self.report({'INFO'}, msg)
        return {'FINISHED'}


# ---- Orient ----

class DESSIN_OT_orient(DessinTransform):
    bl_idname = "dessin.orient"
    bl_label = "Orient"
    bl_description = ("Like Orient (2 points): moves and rotates the selected objects so that two reference points land on "
                      "two target points. D: also scale to the target length, C: copy")

    TITLE = "Orient"
    NEEDED = 4
    NUMFIELDS = 0
    PLANAR = False
    HAS_CENTER = True
    HAS_MODE = True
    MODES = ("keep the size", "scale to the target length")
    NO_SELECTION = "Select the objects to orient first"

    def invoke(self, context, event):
        self.mode = 0
        return super().invoke(context, event)

    def prompt(self):
        opt = f"   [C: copy = {'yes' if self.center else 'no'}, D: {self.MODES[self.mode]}]"
        n = len(self.points)
        if n == 0:
            return "reference point 1" + opt
        if n == 1:
            return "reference point 2" + opt
        if n == 2:
            return "target point 1" + opt
        return "target point 2" + opt

    def lock_allowed(self):
        return False

    def click(self, context):
        if len(self.points) == 1 and self.cur is not None and (self.cur - self.points[0]).length < 1e-9:
            self.report({'WARNING'}, "The two reference points must be different")
            return
        super().click(context)

    def compute(self):
        if not self.points or self.cur is None:
            return [], [], "", None
        n = len(self.points)
        if n == 1:
            return [], [[self.points[0], self.cur]], "", None
        r1, r2 = self.points[0], self.points[1]
        if n == 2:
            return [], [[r1, r2]], "", ("xform", Matrix.Translation(self.cur - r1))
        t1 = self.points[2]
        a, b = r2 - r1, self.cur - t1
        if a.length < 1e-9 or b.length < 1e-9:
            return [], [[r1, r2]], "", ("xform", Matrix.Translation(t1 - r1))
        rot = a.normalized().rotation_difference(b.normalized()).to_matrix().to_4x4()
        k = b.length / a.length if self.mode == 1 else 1.0
        M = Matrix.Translation(t1) @ rot @ Matrix.Diagonal((k, k, k, 1.0)) @ Matrix.Translation(-r1)
        info = f"Angle {math.degrees(a.angle(b)):.2f}°" + (f"   Scale ×{k:.4f}" if self.mode == 1 else "")
        return [], [[r1, r2], [t1, self.cur]], info, ("xform", M)


def _late_imports():
    pass
