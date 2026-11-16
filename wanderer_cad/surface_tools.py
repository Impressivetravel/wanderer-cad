"""Wanderer CAD : Fillet / Chamfer / Extend Surface, Split at Isocurve, Network Surface."""

import bmesh
import bpy
import math
import numpy as np
from bpy_extras.view3d_utils import region_2d_to_origin_3d, region_2d_to_vector_3d
from mathutils import Vector

from .drawing import find_window_region, px_scale, region_rv3d
from .base import DessinBase
from .selection import boundary_world, nearest_segment_px, objects_under_cursor, ray_cast_opaque
from .surfaces import _ProfileOp, delete_objects, deselect_all_objects, grid_mesh, mesh_object_from_arrays
from .hatch import SRF_ROUND, _face_islands, _pick_surface, _select_only, round_surfaces


class DessinSrfRound(DessinBase):
    """Base de Fillet Surface / Chamfer Surface (classe non enregistrée)."""

    CHAMFER = False
    TITLE = "Fillet Surface"
    NEEDED = 2
    NUMFIELDS = 1
    PLANAR = False
    LOCK_OK = False
    WORD = "radius"

    def lock_allowed(self):
        return False

    def size(self):
        t = self.typed_value(0)
        if t is not None and t > 0:
            return t
        return SRF_ROUND["distance" if self.CHAMFER else "radius"]

    def prompt(self):
        val = self.fmt(self.size())
        if not self._picks:
            return f"click the first surface on the side to keep   ({self.WORD} {val}, type a value to change it)"
        return f"click the second surface on the side to keep   ({self.WORD} {val})"

    def invoke(self, context, event):
        self._mouse = None
        self._picks = []
        self.hilite = []
        if context.mode != 'OBJECT':
            self.report({'WARNING'}, "Switch to Object mode")
            return {'CANCELLED'}
        return super().invoke(context, event)

    def update_cursor(self, context, event):
        region = find_window_region(self.area, event.mouse_x, event.mouse_y)
        self._mouse = (event.mouse_x - region.x, event.mouse_y - region.y) if region is not None else None
        super().update_cursor(context, event)

    def compute(self):
        self.hilite = []
        obj, hit = _pick_surface(self, bpy.context)
        if obj is not None:
            mw = obj.matrix_world
            me = obj.data
            if len(me.edges) <= 4000:
                self.hilite = [(mw @ me.vertices[e.vertices[0]].co, mw @ me.vertices[e.vertices[1]].co) for e in me.edges]
            return [], [], obj.name, None
        return [], [], "No surface under the cursor", None

    def click(self, context):
        obj, hit = _pick_surface(self, context)
        if obj is None:
            self.report({'INFO'}, "Click a surface")
            return
        if self._picks and obj is self._picks[0][0]:
            self.report({'INFO'}, "Click another surface")
            return
        self._picks.append((obj, hit))
        if len(self._picks) < 2:
            self.points.append(hit)
            self.refresh(context)
            return
        size = self.size()
        SRF_ROUND["distance" if self.CHAMFER else "radius"] = size
        (A, ha), (B, hb) = self._picks
        ob, msg = round_surfaces(context, A, ha, B, hb, size, self.CHAMFER, SRF_ROUND["segments"])
        if ob is None:
            self.report({'WARNING'}, msg)
            self._picks = []
            self.reset_state()
            self.refresh(context)
            return
        _select_only(context, [A, B, ob])
        self.finished = True


class DESSIN_OT_fillet_srf(DessinSrfRound):
    bl_idname = "dessin.fillet_srf"
    bl_label = "Fillet Surface"
    bl_description = ("Like FilletSrf: click two intersecting surfaces on the side to keep; they are trimmed, joined and "
                      "rounded with a constant radius (type the radius before the second click)")
    TITLE = "Fillet Surface"


class DESSIN_OT_chamfer_srf(DessinSrfRound):
    bl_idname = "dessin.chamfer_srf"
    bl_label = "Chamfer Surface"
    bl_description = ("Like ChamferSrf: click two intersecting surfaces on the side to keep; they are trimmed, joined and "
                      "chamfered (type the distance before the second click)")
    TITLE = "Chamfer Surface"
    CHAMFER = True
    WORD = "distance"


# ---- ExtendSrf : prolonge un bord libre d'une surface ----

def _boundary_side(me, mw, e0, corner_deg=40.0):
    """Côté de bord libre contenant l'arête e0 (on s'arrête aux coins) : liste ordonnée d'indices de sommets."""
    bnd = {}
    for e in me.edges:
        bnd.setdefault(e.vertices[0], []).append(e.index)
        bnd.setdefault(e.vertices[1], []).append(e.index)
    face_count = {}
    for p in me.polygons:
        for ek in p.edge_keys:
            face_count[ek] = face_count.get(ek, 0) + 1
    def is_b(ei):
        e = me.edges[ei]
        return face_count.get(tuple(sorted(e.vertices)), 0) == 1
    if not is_b(e0):
        return None
    V = [mw @ v.co for v in me.vertices]
    chain = list(me.edges[e0].vertices)
    used = {e0}
    cos_lim = math.cos(math.radians(corner_deg))
    for end in (1, 0):
        while True:
            tip = chain[-1] if end == 1 else chain[0]
            prev = chain[-2] if end == 1 else chain[1]
            din = (V[tip] - V[prev]).normalized()
            nxt = None
            for ei in bnd.get(tip, ()):
                if ei in used or not is_b(ei):
                    continue
                a, b = me.edges[ei].vertices
                o = b if a == tip else a
                dout = (V[o] - V[tip])
                if dout.length < 1e-12:
                    continue
                if din.dot(dout.normalized()) >= cos_lim:
                    nxt = (ei, o)
                    break
            if nxt is None:
                break
            used.add(nxt[0])
            if end == 1:
                chain.append(nxt[1])
            else:
                chain.insert(0, nxt[1])
            if chain[0] == chain[-1]:
                break
    return chain


def extend_surface(obj, chain, dist):
    """Prolonge le côté `chain` (sommets du bord) de `dist`, dans la direction de la surface (ExtendSrf, type Line)."""
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    mw = obj.matrix_world
    imw = mw.inverted()
    sc = mw.to_scale()
    k = dist / max((abs(sc.x) + abs(sc.y) + abs(sc.z)) / 3.0, 1e-12)
    side = set(chain)
    dirs = []
    for i, vi in enumerate(chain):
        v = bm.verts[vi]
        inner = [e.other_vert(v) for e in v.link_edges if e.other_vert(v).index not in side]
        if inner:
            d = sum(((v.co - w.co).normalized() for w in inner), Vector())
        else:
            a = bm.verts[chain[max(i - 1, 0)]].co
            b = bm.verts[chain[min(i + 1, len(chain) - 1)]].co
            n = sum((f.normal for f in v.link_faces), Vector())
            d = (b - a).cross(n)
        dirs.append(d.normalized() if d.length > 1e-12 else Vector((0, 0, 1)))
    olds = [bm.verts[vi] for vi in chain]
    new = [bm.verts.new(v.co + d * k) for v, d in zip(olds, dirs)]
    for i in range(len(chain) - 1):
        a, b = olds[i], olds[i + 1]
        try:
            bm.faces.new((a, b, new[i + 1], new[i]))
        except ValueError:
            pass
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    me.update()


class DESSIN_OT_extend_srf(DessinBase):
    bl_idname = "dessin.extend_srf"
    bl_label = "Extend Surface"
    bl_description = ("Like ExtendSrf: click a free edge of a surface, then the extension length (mouse or typed value, Enter). "
                      "The surface continues straight along its own direction")

    TITLE = "Extend Surface"
    NEEDED = 2
    NUMFIELDS = 1
    PLANAR = False
    LOCK_OK = False

    def lock_allowed(self):
        return False

    def prompt(self):
        if self._side is None:
            return "click a free edge of a surface"
        return "extension length (mouse, or type it then Enter)"

    def invoke(self, context, event):
        self._mouse = None
        self._side = None
        self.hilite = []
        if context.mode != 'OBJECT':
            self.report({'WARNING'}, "Switch to Object mode")
            return {'CANCELLED'}
        return super().invoke(context, event)

    def update_cursor(self, context, event):
        region = find_window_region(self.area, event.mouse_x, event.mouse_y)
        self._mouse = (event.mouse_x - region.x, event.mouse_y - region.y) if region is not None else None
        super().update_cursor(context, event)

    def find_side(self, context):
        """(objet, chaîne de sommets, points monde) du bord libre le plus proche du curseur, ou None."""
        if self._mouse is None or self.region is None:
            return None
        try:
            rv3d = region_rv3d(self.region, self.area)
        except (AttributeError, ReferenceError):
            return None
        m = Vector(self._mouse)
        best, bd = None, 12.0 * px_scale()
        persp = np.array(rv3d.perspective_matrix, dtype=np.float64)
        for o in objects_under_cursor(context, self.region, rv3d, m.x, m.y, bd):
            if o.type != 'MESH' or not len(o.data.polygons) or len(o.data.edges) > 20000:
                continue
            FA, FB, FI = boundary_world(o)[:3]
            i, d = nearest_segment_px(FA, FB, persp, self.region, m.x, m.y)      # toutes les arêtes libres en un calcul
            if i is not None and d < bd:
                best, bd = (o, int(FI[i])), d
        if best is None:
            return None
        o, ei = best
        chain = _boundary_side(o.data, o.matrix_world, ei)
        if not chain:
            return None
        return o, chain, [o.matrix_world @ o.data.vertices[i].co for i in chain]

    def side_dir(self):
        o, chain, P = self._side
        me = o.data
        mw = o.matrix_world
        side = set(chain)
        acc = Vector()
        adj = {}
        for e in me.edges:
            adj.setdefault(e.vertices[0], []).append(e.vertices[1])
            adj.setdefault(e.vertices[1], []).append(e.vertices[0])
        for vi in chain:
            for w in adj.get(vi, ()):
                if w not in side:
                    acc += (mw @ me.vertices[vi].co) - (mw @ me.vertices[w].co)
        return acc.normalized() if acc.length > 1e-12 else Vector((0, 0, 1))

    def length(self):
        t = self.typed_value(0)
        if t is not None:
            return t
        if self.cur is None or not self.points:
            return 0.0
        return max(0.0, (self.cur - self.points[0]).dot(self.side_dir()))

    def compute(self):
        self.hilite = []
        if self._side is None:
            s = self.find_side(bpy.context)
            if s is None:
                return [], [], "No free surface edge under the cursor", None
            P = s[2]
            self.hilite = list(zip(P[:-1], P[1:]))
            return [], [], s[0].name, None
        o, chain, P = self._side
        L = self.length()
        d = self.side_dir()
        self.hilite = list(zip(P[:-1], P[1:]))
        moved = [p + d * L for p in P]
        guides = [[a, b] for a, b in zip(P, moved)][:: max(1, len(P) // 12)] + [moved]
        return [], guides, f"Extend {self.fmt(L)}", None

    def click(self, context):
        if self._side is None:
            s = self.find_side(context)
            if s is None:
                self.report({'INFO'}, "Click a free edge of a surface")
                return
            self._side = s
            self.points.append(self.cur.copy() if self.cur is not None else s[2][0].copy())
            self.refresh(context)
            return
        self.finish_shape(context)

    def can_confirm_typed(self):
        return self._side is not None

    def finish_shape(self, context):
        L = self.length()
        if L <= 1e-9 or self._side is None:
            self.report({'WARNING'}, "Extension length must be positive")
            return
        o, chain, _P = self._side
        extend_surface(o, chain, L)
        self._side = None
        self.finished = True


# ---- Split Isocurve : coupe une surface quadrillée le long d'une isocourbe ----

def iso_ring(f0, e0):
    """Barreaux (arêtes traversées) d'un anneau de quads passant par la face f0 en partant de l'arête e0.
    Retourne (barreaux orientés [(arête, sommet a, sommet b)], faces, fermé) : la face j est entre les barreaux j et j+1."""
    a0, b0 = e0.verts
    seen = set()

    def walk(f, e, a, b):
        rungs, faces = [], []
        while f is not None and len(f.verts) == 4 and f.index not in seen:
            seen.add(f.index)
            faces.append(f)
            loops = list(f.loops)
            idx = [l.edge for l in loops].index(e)
            opp = loops[(idx + 2) % 4].edge
            side = [x for x in a.link_edges if x is not e and x in f.edges]
            if not side:
                break
            a2 = side[0].other_vert(a)
            b2 = opp.other_vert(a2)
            rungs.append((opp, a2, b2))
            nxt = [g for g in opp.link_faces if g is not f]
            f, e, a, b = (nxt[0] if nxt else None), opp, a2, b2
        return rungs, faces
    rF, fF = walk(f0, e0, a0, b0)
    closed = bool(rF) and rF[-1][0] is e0
    if closed:
        return [(e0, a0, b0)] + rF[:-1], fF, True
    others = [g for g in e0.link_faces if g is not f0]
    rB, fB = walk(others[0], e0, a0, b0) if others else ([], [])
    return list(reversed(rB)) + [(e0, a0, b0)] + rF, list(reversed(fB)) + fF, False


def split_isocurve(obj, face_index, edge_index, t):
    """Coupe une surface quadrillée le long de l'isocourbe (fraction t des barreaux) et sépare les deux côtés."""
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    f0, e0 = bm.faces[face_index], bm.edges[edge_index]
    rungs, faces, closed = iso_ring(f0, e0)
    if len(rungs) < 2 or not faces:
        bm.free()
        return False
    nv = []
    for e, a, b in rungs:
        _ne, v = bmesh.utils.edge_split(e, a, t)
        nv.append(v)
    cut_edges = []
    for j, f in enumerate(faces):
        v1, v2 = nv[j], nv[(j + 1) % len(nv)]
        try:
            _nf, loop = bmesh.utils.face_split(f, v1, v2)
            cut_edges.append(loop.edge)
        except (ValueError, TypeError):
            pass
    if not cut_edges:
        bm.free()
        return False
    bmesh.ops.split_edges(bm, edges=cut_edges)
    save_untrimmed(obj)
    bm.to_mesh(me)
    bm.free()
    me.update()
    return True


class DESSIN_OT_split_iso(DessinBase):
    bl_idname = "dessin.split_iso"
    bl_label = "Split at Isocurve"
    bl_description = ("Like Split with the Isocurve option: hover a surface made of quads (loft, sweep, extrusion...), "
                      "the isocurve under the cursor lights up; D: other direction; click to split the surface in two")

    TITLE = "Split at Isocurve"
    NEEDED = 1
    HAS_MODE = True
    MODES = ("Direction 1", "Direction 2")
    mode = 0
    PLANAR = False
    LOCK_OK = False

    def lock_allowed(self):
        return False

    def prompt(self):
        return f"click on the surface where to split   [D: {self.MODES[self.mode]}]"

    def invoke(self, context, event):
        self._mouse = None
        self.hilite = []
        if context.mode != 'OBJECT':
            self.report({'WARNING'}, "Switch to Object mode")
            return {'CANCELLED'}
        return super().invoke(context, event)

    def update_cursor(self, context, event):
        region = find_window_region(self.area, event.mouse_x, event.mouse_y)
        self._mouse = (event.mouse_x - region.x, event.mouse_y - region.y) if region is not None else None
        super().update_cursor(context, event)

    def iso_under_cursor(self, context):
        """(objet, face, arête de départ, t, segments monde de l'isocourbe) ou None."""
        if self._mouse is None or self.region is None:
            return None
        try:
            rv3d = region_rv3d(self.region, self.area)
            ro = region_2d_to_origin_3d(self.region, rv3d, self._mouse)
            rv = region_2d_to_vector_3d(self.region, rv3d, self._mouse)
        except (AttributeError, ReferenceError, TypeError):
            return None
        ok, loc, _n, fi, obj, _m = ray_cast_opaque(context, ro, rv, skip_locked=True)
        if not ok or obj is None:
            return None
        obj = getattr(obj, "original", obj)
        if obj.type != 'MESH' or len(obj.modifiers) or fi < 0 or fi >= len(obj.data.polygons):
            return None
        if len(obj.data.polygons[fi].vertices) != 4:
            return None
        mw = obj.matrix_world
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bm.faces.ensure_lookup_table()
        try:
            f = bm.faces[fi]
            loops = list(f.loops)
            e0 = loops[self.mode % 2].edge
            rungs, faces, closed = iso_ring(f, e0)
            a0, b0 = e0.verts
            lp = mw.inverted() @ Vector(loc)
            # fraction : position du point touché entre les deux côtés « rails » de la face (le long du barreau e0)
            opp = loops[(self.mode % 2) + 2].edge
            oa = [x.other_vert(a0) for x in a0.link_edges if x is not e0 and x in f.edges][0]
            ob_ = opp.other_vert(oa)
            ax = ((b0.co + ob_.co) - (a0.co + oa.co)) * 0.5
            t = (lp - (a0.co + oa.co) * 0.5).dot(ax) / max(ax.length_squared, 1e-12)
            t = max(0.02, min(0.98, t))
            pts = [mw @ a.co.lerp(b.co, t) for _e, a, b in rungs]
            if closed:
                pts.append(pts[0])
            return obj, fi, e0.index, t, list(zip(pts[:-1], pts[1:]))
        except (IndexError, ValueError):
            return None
        finally:
            bm.free()

    def compute(self):
        self.hilite = []
        r = self.iso_under_cursor(bpy.context)
        if r is None:
            return [], [], "No quad surface under the cursor", None
        self.hilite = r[4]
        return [], [], r[0].name, None

    def click(self, context):
        r = self.iso_under_cursor(context)
        if r is None:
            self.report({'INFO'}, "Click on a surface made of quads")
            return
        obj, fi, ei, t, _segs = r
        if not split_isocurve(obj, fi, ei, t):
            self.report({'WARNING'}, "Could not split this surface")
            return
        deselect_all_objects(context)
        parts = _separate_loose(context, obj)
        _select_only(context, parts)
        self.report({'INFO'}, f"Surface split in {len(parts)} part(s)")
        self.finished = True


def _separate_loose(context, obj):
    """Sépare les parties non reliées d'un maillage en objets distincts (comme Separate > By Loose Parts)."""
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    isl = _face_islands(bm, same_tag=False)
    if len(isl) < 2:
        bm.free()
        return [obj]
    out = [obj]
    keep_idx = {f.index for f in isl[0]}
    for comp in isl[1:]:
        idx = {f.index for f in comp}
        b2 = bm.copy()
        b2.faces.ensure_lookup_table()
        bmesh.ops.delete(b2, geom=[f for f in b2.faces if f.index not in idx], context='FACES')
        m2 = bpy.data.meshes.new(me.name)
        b2.to_mesh(m2)
        b2.free()
        for mat in me.materials:
            m2.materials.append(mat)
        o2 = bpy.data.objects.new(obj.name, m2)
        o2.matrix_world = obj.matrix_world.copy()
        if obj.get("wd_untrimmed"):
            o2["wd_untrimmed"] = obj["wd_untrimmed"]
        for col in obj.users_collection[:1]:
            col.objects.link(o2)
        o2.select_set(True)
        out.append(o2)
    bm.faces.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.index not in keep_idx], context='FACES')
    bm.to_mesh(me)
    bm.free()
    me.update()
    return out


# ---- NetworkSrf : surface de Gordon sur un réseau de courbes croisées ----

def _nat_spline(x, Y, xs):
    """Spline cubique naturelle passant par (x, Y) (Y : (k, d)), évaluée en xs."""
    x = np.asarray(x, dtype=np.float64)
    Y = np.asarray(Y, dtype=np.float64)
    xs = np.asarray(xs, dtype=np.float64)
    k = len(x)
    if k == 2:
        t = ((xs - x[0]) / (x[1] - x[0]))[:, None]
        return Y[0] * (1 - t) + Y[1] * t
    h = np.diff(x)
    A = np.zeros((k, k))
    R = np.zeros((k,) + Y.shape[1:])
    A[0, 0] = A[-1, -1] = 1.0
    for i in range(1, k - 1):
        A[i, i - 1] = h[i - 1]
        A[i, i] = 2.0 * (h[i - 1] + h[i])
        A[i, i + 1] = h[i]
        R[i] = 6.0 * ((Y[i + 1] - Y[i]) / h[i] - (Y[i] - Y[i - 1]) / h[i - 1])
    M = np.linalg.solve(A, R)
    j = np.clip(np.searchsorted(x, xs, side='right') - 1, 0, k - 2)
    hj = h[j][:, None]
    a = ((x[j + 1] - xs)[:, None]) / hj
    b = ((xs - x[j])[:, None]) / hj
    return (a * Y[j] + b * Y[j + 1] + ((a ** 3 - a) * M[j] + (b ** 3 - b) * M[j + 1]) * (hj ** 2) / 6.0)


def _arclen(P):
    s = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))])
    return s / max(s[-1], 1e-15), s[-1]


def _at_param(P, sP, s):
    """Point(s) de la polyligne P aux paramètres de longueur normalisée s."""
    s = np.atleast_1d(s)
    return np.stack([np.interp(s, sP, P[:, k]) for k in range(3)], axis=1)


def _closest_params(P, Q):
    """(distance mini, paramètre sur P, paramètre sur Q, point milieu) entre deux polylignes."""
    sP, _ = _arclen(P)
    sQ, _ = _arclen(Q)
    A0, A1 = P[:-1], P[1:]
    B0, B1 = Q[:-1], Q[1:]
    best = (np.inf, 0.0, 0.0, None)
    for i in range(len(A0)):
        a0, d1 = A0[i], A1[i] - A0[i]
        d2 = B1 - B0
        r = a0 - B0
        aa = float(d1 @ d1)
        ee = np.einsum('ij,ij->i', d2, d2)
        ff = np.einsum('ij,ij->i', d2, r)
        cc = r @ d1
        bb = d2 @ d1
        den = aa * ee - bb * bb
        s = np.where(den > 1e-18, np.clip((bb * ff - cc * ee) / np.where(den > 1e-18, den, 1.0), 0.0, 1.0), 0.0)
        t = (bb * s + ff) / np.where(ee > 1e-18, ee, 1.0)
        lo_, hi_ = t < 0.0, t > 1.0
        t = np.clip(t, 0.0, 1.0)
        aa_ = max(aa, 1e-18)
        s = np.where(lo_, np.clip(-cc / aa_, 0.0, 1.0), np.where(hi_, np.clip((bb - cc) / aa_, 0.0, 1.0), s))
        pa = a0 + d1 * s[:, None]
        pb = B0 + d2 * t[:, None]
        d = np.linalg.norm(pa - pb, axis=1)
        j = int(np.argmin(d))
        if d[j] < best[0]:
            best = (float(d[j]), float(sP[i] + (sP[i + 1] - sP[i]) * s[j]), float(sQ[j] + (sQ[j + 1] - sQ[j]) * t[j]),
                    (pa[j] + pb[j]) * 0.5)
    return best


def network_surface(curves, nu=32, nv=32):
    """Surface de Gordon passant par un réseau de courbes (deux familles qui se croisent).
    Retourne ((sommets, faces), '') ou (None, message)."""
    C = [np.asarray(c, dtype=np.float64) for c in curves if len(c) >= 2]
    n = len(C)
    if n < 4:
        return None, "NetworkSrf needs at least 2 curves in each direction"
    allp = np.vstack(C)
    tol = 2e-3 * float(np.linalg.norm(allp.max(axis=0) - allp.min(axis=0)))
    inter = {}
    for i in range(n):
        for j in range(i + 1, n):
            d, si, sj, X = _closest_params(C[i], C[j])
            if d <= tol:
                inter[(i, j)] = (si, sj, X)
    color = [-1] * n
    color[0] = 0
    stack = [0]
    while stack:
        i = stack.pop()
        for j in range(n):
            if (min(i, j), max(i, j)) in inter:
                if color[j] < 0:
                    color[j] = 1 - color[i]
                    stack.append(j)
                elif color[j] == color[i]:
                    return None, "Curves of the same direction cross each other"
    if -1 in color:
        return None, "Every curve must cross the curves of the other direction"
    U = [i for i in range(n) if color[i] == 0]
    V = [i for i in range(n) if color[i] == 1]
    if len(U) < 2 or len(V) < 2:
        return None, "NetworkSrf needs at least 2 curves in each direction"

    def par(a, b):
        key = (min(a, b), max(a, b))
        if key not in inter:
            return None
        si, sj, X = inter[key]
        return (si, sj, X) if a < b else (sj, si, X)
    for a in U:
        for b in V:
            if par(a, b) is None:
                return None, "Each curve must cross every curve of the other direction"
    V.sort(key=lambda b: par(U[0], b)[0])
    U.sort(key=lambda a: par(V[0], a)[0])
    Cs = list(C)
    for a in U:                         # même sens de parcours pour toutes les courbes d'une famille
        if par(a, V[0])[0] > par(a, V[-1])[0]:
            Cs[a] = Cs[a][::-1]
    for b in V:
        if par(b, U[0])[0] > par(b, U[-1])[0]:
            Cs[b] = Cs[b][::-1]
    C = Cs
    inter = {}
    for a in U:
        for b in V:
            d, sa, sb, X = _closest_params(C[a], C[b])
            inter[(a, b)] = (sa, sb, X)
    S_U = np.array([[inter[(a, b)][0] for b in V] for a in U])     # (nU, nV) paramètres sur les courbes U
    S_V = np.array([[inter[(a, b)][1] for a in U] for b in V])     # (nV, nU) paramètres sur les courbes V
    X = np.array([[inter[(a, b)][2] for b in V] for a in U])       # (nU, nV, 3)
    uk = S_U.mean(axis=0)
    vk = S_V.mean(axis=0)
    if np.any(np.diff(uk) <= 1e-9) or np.any(np.diff(vk) <= 1e-9):
        return None, "Could not order the curves of the network"
    us = np.linspace(uk[0], uk[-1], nu + 1)
    vs = np.linspace(vk[0], vk[-1], nv + 1)

    def curve_on(Pc, s_knots, g_knots, gs):
        sP, _ = _arclen(Pc)
        s = np.interp(gs, g_knots, s_knots)
        return _at_param(Pc, sP, s)
    CU = np.array([curve_on(C[a], S_U[i], uk, us) for i, a in enumerate(U)])   # (nU, nu+1, 3)
    CV = np.array([curve_on(C[b], S_V[j], vk, vs) for j, b in enumerate(V)])   # (nV, nv+1, 3)
    LU = np.stack([_nat_spline(vk, CU[:, k, :], vs) for k in range(nu + 1)], axis=1)       # (nv+1, nu+1, 3)
    LV = np.stack([_nat_spline(uk, CV[:, k, :], us) for k in range(nv + 1)], axis=0)       # (nv+1, nu+1, 3)
    Tv = np.stack([_nat_spline(vk, X[:, j, :], vs) for j in range(len(V))], axis=0)        # (nV, nv+1, 3)
    T = np.stack([_nat_spline(uk, Tv[:, r, :], us) for r in range(nv + 1)], axis=0)        # (nv+1, nu+1, 3)
    G = LU + LV - T
    Vx, F = grid_mesh(G, False, False, False)
    return (Vx, F), ""


class DESSIN_OT_network_srf(_ProfileOp, bpy.types.Operator):
    bl_idname = "dessin.network_srf"
    bl_label = "Network Surface"
    bl_description = ("Like NetworkSrf: creates a surface through a network of curves crossing in two directions "
                      "(at least 2 + 2): click the curves, then Enter / Space")
    bl_options = {'REGISTER', 'UNDO'}

    segments: bpy.props.IntProperty(name="Segments", default=32, min=2, max=300,
                                    description="Subdivisions in each direction")
    delete_input: bpy.props.BoolProperty(name="Delete input", default=False)

    def invoke(self, context, event):
        return self.execute(context)

    def execute(self, context):
        objs, profs = self.profiles(context)
        if len(profs) < 4:
            self.report({'INFO'}, "Click at least 2 curves in each direction, then Enter")
            return {'CANCELLED'}
        built, msg = network_surface([p[0] for p in profs], self.segments, self.segments)
        if built is None:
            self.report({'WARNING'}, msg)
            return {'CANCELLED'}
        V, F = built
        out = mesh_object_from_arrays(context, "Network Surface", V, F, np.asarray(V).mean(axis=0), False)
        for p in out.data.polygons:
            p.use_smooth = True
        if self.delete_input:
            delete_objects(objs)
        _select_only(context, [out])
        return {'FINISHED'}


# ---- Édition des courbes : Rebuild, Simplify, Change Degree, points de contrôle, MatchCrv, BlendCrv ----

def _bspline_basis(t, n, p, closed):
    """Matrice (len(t), n) des fonctions de base B-spline uniformes (ouverte : extrémités accrochées, fermée : périodique)."""
    t = np.asarray(t, dtype=np.float64)
    if closed:
        m = n + p
        knots = np.arange(m + p + 1, dtype=np.float64)
        tt = t + p
    else:
        knots = np.array([0.0] * (p + 1) + list(range(1, n - p)) + [float(n - p)] * (p + 1))
        m = n
        tt = np.clip(t, 0.0, float(n - p) - 1e-9)
    N = np.zeros((len(tt), len(knots) - 1))
    for i in range(len(knots) - 1):
        N[:, i] = (tt >= knots[i]) & (tt < knots[i + 1])
    if not closed:
        N[tt >= knots[-1] - 1e-12, m - 1] = 1.0
    for d in range(1, p + 1):
        Nn = np.zeros((len(tt), len(knots) - 1 - d))
        for i in range(len(knots) - 1 - d):
            a = knots[i + d] - knots[i]
            b = knots[i + d + 1] - knots[i + 1]
            left = (tt - knots[i]) / a * N[:, i] if a > 1e-12 else 0.0
            right = (knots[i + d + 1] - tt) / b * N[:, i + 1] if b > 1e-12 else 0.0
            Nn[:, i] = left + right
        N = Nn
    N = N[:, :m]
    if closed:
        W = N[:, :n].copy()
        W[:, :p] += N[:, n:n + p]
        return W
    return N


def fit_nurbs(P, n, p, closed):
    """Points de contrôle (n, 3) d'une B-spline de degré p approchant au mieux la polyligne P (moindres carrés).
    Extrémités conservées pour une courbe ouverte. Retourne (points, écart max)."""
    P = np.asarray(P, dtype=np.float64)
    if closed:
        Q = np.vstack([P, P[:1]])
    else:
        Q = P
    seg = np.linalg.norm(np.diff(Q, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    L = max(s[-1], 1e-15)
    # échantillons denses pour un ajustement stable
    k = max(200, 8 * n)
    ss = np.linspace(0.0, L, k + 1)[:-1] if closed else np.linspace(0.0, L, k)
    S = np.stack([np.interp(ss, s, Q[:, j]) for j in range(3)], axis=1)
    if closed:
        t = ss / L * n
    else:
        t = ss / L * (n - p)
    A = _bspline_basis(t, n, p, closed)
    if closed:
        C, *_ = np.linalg.lstsq(A, S, rcond=None)
    else:
        C = np.zeros((n, 3))
        C[0], C[-1] = S[0], S[-1]
        rhs = S - np.outer(A[:, 0], C[0]) - np.outer(A[:, -1], C[-1])
        inner, *_ = np.linalg.lstsq(A[:, 1:-1], rhs, rcond=None)
        C[1:-1] = inner
    dev = float(np.linalg.norm(A @ C - S, axis=1).max())
    return C, dev


def _rdp(P, tol):
    """Douglas-Peucker : indices gardés d'une polyligne ouverte."""
    P = np.asarray(P, dtype=np.float64)
    keep = np.zeros(len(P), dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(P) - 1)]
    while stack:
        a, b = stack.pop()
        if b <= a + 1:
            continue
        ab = P[b] - P[a]
        L2 = float(ab @ ab)
        seg = P[a + 1:b] - P[a]
        if L2 < 1e-24:
            d = np.linalg.norm(seg, axis=1)
        else:
            tt = np.clip(seg @ ab / L2, 0.0, 1.0)
            d = np.linalg.norm(seg - np.outer(tt, ab), axis=1)
        i = int(np.argmax(d))
        if d[i] > tol:
            j = a + 1 + i
            keep[j] = True
            stack.append((a, j))
            stack.append((j, b))
    return np.nonzero(keep)[0]


def _late_imports():
    """Noms définis dans des modules chargés après celui-ci : ils ne servent qu'à l'exécution des outils."""
    global save_untrimmed
    from .blocks import save_untrimmed
