"""Wanderer CAD : Surfaces : Revolve, Extrude Curve, Loft, Sweep, Planar Surface."""

import bmesh
import bpy
import math
import numpy as np
from bpy_extras.view3d_utils import region_2d_to_origin_3d, region_2d_to_vector_3d
from mathutils import Vector, geometry

from .core import _link_object, plane_axes
from .drawing import region_rv3d
from .base import view_height
from .transform import DessinTransform
from .booleans import _drop_temp, _link_like
from .selection import ray_cast_opaque
from .trim import wire_graph, wire_paths
from .join_explode import EXPLODE_SHARP_DEG


# --------------------------------------------------------------------------
# Surfaces : Revolve / Loft / Sweep, et Align (options inspirées de Rhino)
# --------------------------------------------------------------------------

_PICK_ORDER = []          # noms des objets cliqués avec Join / Explode / Loft / Sweep / Align, dans l'ordre des clics


def ordered_selection(context, types=('MESH', 'CURVE')):
    """Objets sélectionnés, dans l'ordre où on les a cliqués (les autres ensuite, par nom)."""
    sel = {o.name: o for o in context.selected_objects if o.type in types}
    out = [sel.pop(n) for n in _PICK_ORDER if n in sel]
    out += [sel[n] for n in sorted(sel)]
    return out


def object_paths(obj, depsgraph):
    """Tous les contours d'un objet (courbe ou maillage sans face) : [(points monde (n,3), fermé)]."""
    g = wire_graph(obj, depsgraph)
    if not g or not g[1]:
        return []
    verts, edges = g
    out = []
    for path, closed in wire_paths(len(verts), edges):
        if len(path) < 2:
            continue
        P = np.array([tuple(verts[i]) for i in path], dtype=np.float64)
        keep = [0]
        for i in range(1, len(P)):
            if np.linalg.norm(P[i] - P[keep[-1]]) > 1e-9:
                keep.append(i)
        P = P[keep]
        if closed and len(P) > 1 and np.linalg.norm(P[0] - P[-1]) <= 1e-9:
            P = P[:-1]
        if len(P) >= 2:
            out.append((P, bool(closed) and len(P) >= 3))
    return out


def path_length(P, closed):
    Q = np.vstack([P, P[:1]]) if closed else P
    return float(np.linalg.norm(np.diff(Q, axis=0), axis=1).sum())


def object_profile(obj, depsgraph):
    """Le plus long contour de l'objet : (points (n,3), fermé) ou None."""
    paths = object_paths(obj, depsgraph)
    if not paths:
        return None
    return max(paths, key=lambda t: path_length(t[0], t[1]))


def refine_points(P, closed, n):
    """Ajoute des points (au milieu du plus long segment) jusqu'à n, sans bouger les points existants."""
    pts = [np.array(p, dtype=np.float64) for p in P]
    while len(pts) < n:
        m = len(pts)
        segs = m if closed else m - 1
        lens = [np.linalg.norm(pts[(i + 1) % m] - pts[i]) for i in range(segs)]
        i = int(np.argmax(lens))
        pts.insert(i + 1, (pts[i] + pts[(i + 1) % m]) * 0.5)
    return np.array(pts)


def newell_normal(P):
    return np.cross(P, np.roll(P, -1, axis=0)).sum(axis=0)


def align_sections(secs, closed):
    """Met les sections (même nombre de points) dans le même sens et sur la même couture (comme « Align direction »)."""
    out = [secs[0]]
    for S in secs[1:]:
        prev = out[-1]
        if closed:
            n1, n0 = newell_normal(S), newell_normal(prev)
            if np.linalg.norm(n1) > 1e-12 and np.linalg.norm(n0) > 1e-12 and n1.dot(n0) < 0:
                S = S[::-1]
            best, bk = None, 0
            for k in range(len(S)):
                dsum = float(np.linalg.norm(np.roll(S, -k, axis=0) - prev, axis=1).sum())
                if best is None or dsum < best:
                    best, bk = dsum, k
            S = np.roll(S, -bk, axis=0)
        else:
            a = float(np.linalg.norm(S - prev, axis=1).sum())
            b = float(np.linalg.norm(S[::-1] - prev, axis=1).sum())
            if b < a:
                S = S[::-1]
        out.append(S)
    return out


def catmull_rows(secs, closed, sub):
    """Interpole les sections (Catmull-Rom uniforme) : un lissage entre les profils, comme le Loft « Normal »."""
    A = np.array(secs)
    K = len(A)
    rows = []
    spans = K if closed else K - 1
    for i in range(spans):
        p0 = A[(i - 1) % K] if (closed or i > 0) else 2 * A[0] - A[1]
        p1, p2 = A[i % K], A[(i + 1) % K]
        p3 = A[(i + 2) % K] if (closed or i + 2 < K) else 2 * A[K - 1] - A[K - 2]
        for s in range(sub):
            t = s / sub
            rows.append(0.5 * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                               + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    if not closed:
        rows.append(A[-1])
    return np.array(rows)


def grid_mesh(rows, closed_profile, closed_rows, cap):
    """rows : (R, n, 3). Retourne (sommets (R*n, 3), faces) ; cap : n-gones aux deux bouts (profil fermé, lignes ouvertes)."""
    R, n = rows.shape[0], rows.shape[1]
    V = rows.reshape(-1, 3)
    F = []
    for r in range(R if closed_rows else R - 1):
        r2 = (r + 1) % R
        for j in range(n if closed_profile else n - 1):
            j2 = (j + 1) % n
            F.append((r * n + j, r * n + j2, r2 * n + j2, r2 * n + j))
    if cap and closed_profile and not closed_rows and n >= 3:
        F.append(tuple(range(n - 1, -1, -1)))
        F.append(tuple(range((R - 1) * n, R * n)))
    return V, F


def mesh_object_from_arrays(context, name, V, F, origin, fix_normals):
    """Crée l'objet maillage (sommets en coordonnées monde, origine de l'objet = origin)."""
    o = Vector(origin)
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(Vector(p) - o) for p in V], [], [tuple(f) for f in F])
    me.update()
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bm.faces.ensure_lookup_table()
    degenerate = [f for f in bm.faces if f.calc_area() < 1e-14]
    if degenerate:
        bmesh.ops.delete(bm, geom=degenerate, context='FACES_ONLY')
    loose = [e for e in bm.edges if not e.link_faces]
    if loose:
        bmesh.ops.delete(bm, geom=loose, context='EDGES')
    loose_v = [v for v in bm.verts if not v.link_edges]
    if loose_v:
        bmesh.ops.delete(bm, geom=loose_v, context='VERTS')
    if fix_normals:
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    me.update()
    obj = _link_object(context, name, me)
    obj.location = o
    return obj


def deselect_all_objects(context):
    """Désélectionne tout (sans trébucher sur un objet qui vient d'être supprimé)."""
    for ob in list(context.view_layer.objects):
        try:
            if ob is not None:
                ob.select_set(False)
        except (ReferenceError, RuntimeError):
            pass


def delete_objects(objs):
    for o in objs:
        try:
            data = o.data
            bpy.data.objects.remove(o)
            if data is not None and data.users == 0:
                if isinstance(data, bpy.types.Mesh):
                    bpy.data.meshes.remove(data)
                elif isinstance(data, bpy.types.Curve):
                    bpy.data.curves.remove(data)
        except (ReferenceError, RuntimeError):
            pass


# ---- Loft ----

def loft_surface(profiles, closed_loft=False, smooth=True, cap=True, points=0):
    """profiles : [(points (n,3), fermé)] dans l'ordre. Retourne (sommets, faces) ou (None, message)."""
    if len(profiles) < 2:
        return None, "Loft needs at least two curves"
    kinds = {c for _p, c in profiles}
    if len(kinds) > 1:
        return None, "Loft: mix of open and closed curves"
    closed = kinds.pop()
    n = max([len(p) for p, _c in profiles] + [int(points) if points else 0, 3 if closed else 2])
    secs = [refine_points(p, closed, n) for p, _c in profiles]
    secs = align_sections(secs, closed)
    if len(secs) <= 2:
        closed_loft = False
    rows = catmull_rows(secs, closed_loft, 8) if (smooth and len(secs) > 2) else np.array(secs)
    V, F = grid_mesh(rows, closed, closed_loft, cap)
    return (V, F, closed), ""


# ---- Sweep ----

def rail_frames(R, closed, upright):
    """Repères le long du rail : tangentes T, normales N, binormales B, et mitre (direction, facteur) aux angles."""
    m = len(R)
    T = np.zeros((m, 3))
    md = np.zeros((m, 3))
    mk = np.ones(m)
    for i in range(m):
        a = R[i] - R[i - 1] if (closed or i > 0) else None
        b = R[(i + 1) % m] - R[i] if (closed or i < m - 1) else None
        ta = a / np.linalg.norm(a) if a is not None and np.linalg.norm(a) > 1e-12 else None
        tb = b / np.linalg.norm(b) if b is not None and np.linalg.norm(b) > 1e-12 else None
        if ta is not None and tb is not None:
            t = ta + tb
            if np.linalg.norm(t) < 1e-9:
                t = ta
            t = t / np.linalg.norm(t)
            ch = float(t.dot(ta))
            turn = tb - ta
            if np.linalg.norm(turn) > 1e-9 and ch > 0.2:
                md[i] = turn / np.linalg.norm(turn)
                mk[i] = 1.0 / ch
        else:
            t = ta if ta is not None else tb
            if t is None:       # points confondus : on garde la tangente précédente
                t = T[i - 1] if i > 0 else np.array((1.0, 0.0, 0.0))
        T[i] = t
    z = np.array((0.0, 0.0, 1.0))
    N = np.zeros((m, 3))
    if upright:
        prev = np.array((1.0, 0.0, 0.0))
        for i in range(m):
            n = z - T[i] * z.dot(T[i])
            if np.linalg.norm(n) < 1e-6:
                n = prev - T[i] * prev.dot(T[i])
            N[i] = n / np.linalg.norm(n)
            prev = N[i]
    else:
        n0 = z - T[0] * z.dot(T[0])
        if np.linalg.norm(n0) < 1e-6:
            n0 = np.array((1.0, 0.0, 0.0)) - T[0] * T[0][0]
        N[0] = n0 / np.linalg.norm(n0)

        def transport(r, x0, x1, t0, t1):
            v1 = x1 - x0
            c1 = v1.dot(v1)
            if c1 < 1e-18:
                return r
            rl = r - (2.0 / c1) * v1.dot(r) * v1
            tl = t0 - (2.0 / c1) * v1.dot(t0) * v1
            v2 = t1 - tl
            c2 = v2.dot(v2)
            if c2 < 1e-18:
                return rl
            return rl - (2.0 / c2) * v2.dot(rl) * v2

        for i in range(m - 1):
            r = transport(N[i], R[i], R[i + 1], T[i], T[i + 1])
            r = r - T[i + 1] * T[i + 1].dot(r)
            N[i + 1] = r / np.linalg.norm(r)
        if closed and m > 2:
            r = transport(N[m - 1], R[m - 1], R[0], T[m - 1], T[0])
            r = r - T[0] * T[0].dot(r)
            r = r / np.linalg.norm(r)
            phi = math.atan2(float(np.cross(r, N[0]).dot(T[0])), float(r.dot(N[0])))
            seg = np.linalg.norm(np.diff(np.vstack([R, R[:1]]), axis=0), axis=1)
            s = np.concatenate([[0.0], np.cumsum(seg)[:-1]]) / max(seg.sum(), 1e-12)
            for i in range(m):
                th = phi * s[i]
                N[i] = N[i] * math.cos(th) + np.cross(T[i], N[i]) * math.sin(th)
    B = np.cross(T, N)
    return T, N, B, md, mk


def interp_sections(local, idx, m, closed, pos=None):
    """local : [(n,3)] sections (repère du rail), idx : stations d'attache (croissantes). Retourne (m, n, 3).
    pos : abscisse de chaque station (par défaut son numéro) pour interpoler selon la distance et non selon l'indice."""
    n = local[0].shape[0]
    out = np.zeros((m, n, 3))
    if len(local) == 1:
        out[:] = local[0]
        return out
    P = np.arange(m, dtype=np.float64) if pos is None else np.asarray(pos, dtype=np.float64)
    for k in range(m):
        if k <= idx[0]:
            out[k] = local[0]
        elif k >= idx[-1]:
            out[k] = local[-1]
        else:
            j = int(np.searchsorted(idx, k, side='right')) - 1
            span = max(P[idx[j + 1]] - P[idx[j]], 1e-12)
            t = min(max((P[k] - P[idx[j]]) / span, 0.0), 1.0)
            out[k] = local[j] * (1 - t) + local[j + 1] * t
    return out


def polyline_nearest(R, closed, pts):
    """Point le plus proche de chaque point de pts sur la polyligne R : (segment, paramètre, point, distance)."""
    A = R
    B = np.roll(R, -1, axis=0) if closed else R[1:]
    if not closed:
        A = R[:-1]
    ab = B - A
    l2 = np.maximum((ab * ab).sum(axis=1), 1e-30)
    out = []
    for p in np.atleast_2d(pts):
        t = np.clip(((p - A) * ab).sum(axis=1) / l2, 0.0, 1.0)
        q = A + ab * t[:, None]
        d = np.linalg.norm(q - p, axis=1)
        out.append((d, t, q))
    return A, B, out


def section_normal(S, closed):
    """Normale du plan d'un profil (Newell si fermé, sinon plan moyen)."""
    c = S - S.mean(axis=0)
    if closed:
        n = newell_normal(S)
        if np.linalg.norm(n) > 1e-12:
            return n / np.linalg.norm(n)
    try:
        return np.linalg.svd(c, full_matrices=False)[2][-1]
    except np.linalg.LinAlgError:
        return np.array((0.0, 0.0, 1.0))


def sweep1_surface(rail, sections, upright=False, miter=True, cap=True):
    """rail : (points, fermé) ; sections : [(points, fermé)]. Retourne ((V, F, closed), '') ou (None, message).
    Chaque profil est mesuré dans le repère de l'ARÊTE du rail qu'il traverse (et non dans celui, en biais, du sommet le plus proche) :
    l'épaisseur reste constante, y compris aux angles du rail."""
    R, rclosed = rail
    if len(sections) == 0:
        return None, "Sweep needs at least one cross-section"
    kinds = {c for _p, c in sections}
    if len(kinds) > 1:
        return None, "Sweep: mix of open and closed cross-sections"
    sclosed = kinds.pop()
    T, N, B, md, mk = rail_frames(R, rclosed, upright)
    m = len(R)
    n = max(len(p) for p, _c in sections)
    n = max(n, 3 if sclosed else 2)
    # angles du rail : le décalage le long du rail (composante T du profil) n'a pas de sens sur un coin mitré
    ta = R - np.roll(R, 1, axis=0)
    tb = np.roll(R, -1, axis=0) - R
    la, lb = np.linalg.norm(ta, axis=1), np.linalg.norm(tb, axis=1)
    cosang = (ta * tb).sum(axis=1) / np.maximum(la * lb, 1e-30)
    corner = cosang < 0.9
    if not rclosed:
        corner[0] = corner[-1] = False
    keep_t = np.where(corner, 0.0, 1.0)
    A_, B_ = None, None
    entries = []
    for p, _c in sections:
        S = refine_points(p, sclosed, n)
        c = S.mean(axis=0)
        A_, B_, near = polyline_nearest(R, rclosed, c)
        d_, t_, q_ = near[0]
        dmin = float(d_.min())
        nrm = section_normal(S, sclosed)
        tol = max(1e-6, 1e-6 * float(np.ptp(R, axis=0).max()))
        cands = np.nonzero(d_ <= dmin + tol)[0]
        segdir = (B_ - A_)[cands]
        segdir = segdir / np.maximum(np.linalg.norm(segdir, axis=1, keepdims=True), 1e-30)
        s = int(cands[int(np.argmax(np.abs(segdir @ nrm)))])
        q = q_[s]
        te = (B_[s] - A_[s])
        te = te / max(float(np.linalg.norm(te)), 1e-30)
        # station d'attache : sommet le plus proche du point d'attache
        k = int(np.argmin(np.linalg.norm(R - q, axis=1)))
        ne = N[k] - te * float(te.dot(N[k]))
        if np.linalg.norm(ne) < 1e-6:
            ne = np.cross(te, np.array((0.0, 0.0, 1.0)))
            if np.linalg.norm(ne) < 1e-6:
                ne = np.array((1.0, 0.0, 0.0))
        ne = ne / np.linalg.norm(ne)
        be = np.cross(te, ne)
        d = S - q
        entries.append((k, np.stack([d @ ne, d @ be, d @ te], axis=1)))
    entries.sort(key=lambda e: e[0])
    idx = [e[0] for e in entries]
    local = align_sections([e[1] for e in entries], sclosed)
    L = interp_sections(local, idx, m, rclosed)
    rows = (R[:, None, :] + L[:, :, 0:1] * N[:, None, :] + L[:, :, 1:2] * B[:, None, :]
            + (L[:, :, 2:3] * keep_t[:, None, None]) * T[:, None, :])
    if miter:
        d = rows - R[:, None, :]
        par = np.einsum('mnk,mk->mn', d, md)
        rows = rows + (par * (mk - 1.0)[:, None])[:, :, None] * md[:, None, :]
    V, F = grid_mesh(rows, sclosed, rclosed, cap)
    return (V, F, sclosed), ""


def polyline_project(R, closed, Q):
    """Projette les points Q sur la polyligne R : (abscisse curviligne, point projeté, longueur totale)."""
    A = R if closed else R[:-1]
    B = np.roll(R, -1, axis=0) if closed else R[1:]
    ab = B - A
    ln = np.linalg.norm(ab, axis=1)
    l2 = np.maximum(ln * ln, 1e-30)
    start = np.concatenate([[0.0], np.cumsum(ln)[:-1]])
    Q = np.atleast_2d(Q)
    S = np.zeros(len(Q))
    P = np.zeros((len(Q), 3))
    chunk = max(1, int(1.5e6 / max(len(A), 1)))
    for i0 in range(0, len(Q), chunk):
        q = Q[i0:i0 + chunk]
        t = np.clip(((q[:, None, :] - A[None]) * ab[None]).sum(axis=2) / l2[None], 0.0, 1.0)
        pts = A[None] + ab[None] * t[:, :, None]
        d = np.linalg.norm(pts - q[:, None, :], axis=2)
        j = d.argmin(axis=1)
        r = np.arange(len(q))
        S[i0:i0 + chunk] = start[j] + t[r, j] * ln[j]
        P[i0:i0 + chunk] = pts[r, j]
    return S, P, float(ln.sum())


def polyline_point(R, closed, s):
    """Point d'abscisse curviligne s (tableau) sur la polyligne R."""
    A = R if closed else R[:-1]
    B = np.roll(R, -1, axis=0) if closed else R[1:]
    ab = B - A
    ln = np.maximum(np.linalg.norm(ab, axis=1), 1e-30)
    start = np.concatenate([[0.0], np.cumsum(ln)[:-1]])
    s = np.asarray(s, dtype=np.float64)
    j = np.clip(np.searchsorted(start, s, side='right') - 1, 0, len(A) - 1)
    t = np.clip((s - start[j]) / ln[j], 0.0, 1.0)
    return A[j] + ab[j] * t[:, None]


def sweep2_stations(R1, c1, R2, c2, centers):
    """Stations (point du rail 1, point apparié du rail 2, abscisse sur le rail 1) :
    chaque point est apparié au point le plus proche de l'autre rail, donc les cordes restent perpendiculaires aux rails
    (rails parallèles / décalés, rectangles...). Si cet appariement n'est pas monotone, on retombe sur l'abscisse normalisée.
    Les sommets des deux rails et le point où chaque profil coupe le rail sont des stations."""
    A0 = refine_points(R1, c1, max(len(R1), 24))
    seg = np.linalg.norm((np.roll(A0, -1, axis=0) - A0) if c1 else (A0[1:] - A0[:-1]), axis=1)
    sA0 = np.concatenate([[0.0], np.cumsum(seg)[:-1]]) if c1 else np.concatenate([[0.0], np.cumsum(seg)])
    LA = float(seg.sum())
    Br = R2
    if not c1 and (np.linalg.norm(A0[0] - Br[0]) + np.linalg.norm(A0[-1] - Br[-1])
                   > np.linalg.norm(A0[0] - Br[-1]) + np.linalg.norm(A0[-1] - Br[0])):
        Br = Br[::-1]
    if c1 and float(newell_normal(A0).dot(newell_normal(Br))) < 0:
        Br = Br[::-1]                       # rails fermés tournant en sens inverse
    # candidats : échantillons du rail 1, sommets du rail 2 (projetés sur le rail 1), points d'attache des profils
    sB_, PB_, _LB = polyline_project(Br, c2, A0)
    sA_list = [sA0]
    PA_list = [A0]
    PB_list = [PB_]
    sv, qv, _l = polyline_project(A0, c1, Br)
    sA_list.append(sv)
    PA_list.append(qv)
    PB_list.append(Br)
    if len(centers):
        sc, qc, _l = polyline_project(A0, c1, np.array(centers))
        _sb, pbc, _lb = polyline_project(Br, c2, qc)
        sA_list.append(sc)
        PA_list.append(qc)
        PB_list.append(pbc)
    sA = np.concatenate(sA_list)
    PA = np.vstack(PA_list)
    PB = np.vstack(PB_list)
    if c1:
        sA = np.where(sA >= LA * (1 - 1e-9), 0.0, sA)
    order = np.argsort(sA, kind='stable')
    sA, PA, PB = sA[order], PA[order], PB[order]
    keep = [0]
    eps = max(1e-7 * LA, 1e-9)
    for i in range(1, len(sA)):
        if sA[i] - sA[keep[-1]] > eps:
            keep.append(i)
    sA, PA, PB = sA[keep], PA[keep], PB[keep]
    if not c1:
        PB[0], PB[-1] = Br[0], Br[-1]
    # contrôle : l'appariement par plus proche point doit avancer dans le même sens sur le rail 2
    sB, _p, LB = polyline_project(Br, c2, PB)
    good = True
    if c1:
        u = (sB - sB[0]) % LB
        good = bool(np.all(np.diff(u) >= -1e-6 * LB))
    else:
        good = bool(np.all(np.diff(sB) >= -1e-6 * LB))
    if not good:
        fr = sA / max(LA, 1e-30)
        if c1:
            s0 = float(sB[0])
            PB = polyline_point(Br, c2, (s0 + fr * LB) % LB)
        else:
            PB = polyline_point(Br, c2, fr * LB)
    return sA, PA, PB, LA


def sweep2_surface(rail1, rail2, sections, cap=True):
    """Deux rails : la section est déformée pour rester entre les deux rails.
    Largeur (entre les rails) mise à l'échelle avec l'écartement ; hauteur mise à l'échelle avec l'écartement mesuré
    perpendiculairement au rail (donc sans grossir aux coins mitrés)."""
    R1, c1 = rail1
    R2, c2 = rail2
    if len(sections) == 0:
        return None, "Sweep needs at least one cross-section"
    if c1 != c2:
        return None, "Sweep 2 rails: one rail is closed and the other open"
    kinds = {c for _p, c in sections}
    if len(kinds) > 1:
        return None, "Sweep: mix of open and closed cross-sections"
    sclosed = kinds.pop()
    n = max(max(len(p) for p, _c in sections), 3 if sclosed else 2)
    secs = [refine_points(p, sclosed, n) for p, _c in sections]
    sA, A, Bp, LA = sweep2_stations(R1, c1, R2, c2, [S.mean(axis=0) for S in secs])
    m = len(A)
    if m < 2:
        return None, "Sweep 2 rails: the rails are too short"
    T1, _N1, _B1, _md1, mk1 = rail_frames(A, c1, True)
    T2, _N2, _B2, _md2, mk2 = rail_frames(Bp, c2, True)
    flip = np.where((T1 * T2).sum(axis=1) < 0, -1.0, 1.0)
    T2 = T2 * flip[:, None]
    Tm = T1 + T2
    Tm = Tm / np.maximum(np.linalg.norm(Tm, axis=1, keepdims=True), 1e-12)
    chord = Bp - A
    cl = np.maximum(np.linalg.norm(chord, axis=1), 1e-9)
    e1 = chord / cl[:, None]
    f3 = np.cross(e1, Tm)
    bad = np.linalg.norm(f3, axis=1) < 1e-6
    f3[bad] = np.array((0.0, 0.0, 1.0))
    f3 = f3 / np.linalg.norm(f3, axis=1, keepdims=True)
    f2 = np.cross(f3, e1)
    mk = np.maximum(mk1, mk2)
    pd = cl / mk                                  # écartement perpendiculaire (aux coins mitrés la corde est plus longue que l'écartement)
    keep_t = np.where(mk > 1.03, 0.0, 1.0)         # pas de décalage le long du rail sur un coin mitré
    entries = []
    for S in secs:
        c = S.mean(axis=0)
        k = int(np.argmin(np.linalg.norm(A - polyline_project(A, c1, c)[1][0], axis=1)))
        d = S - A[k]
        entries.append((k, np.stack([d @ e1[k] / cl[k], d @ f2[k] / pd[k], d @ f3[k] / pd[k]], axis=1)))
    entries.sort(key=lambda e: e[0])
    idx = [e[0] for e in entries]
    local = align_sections([e[1] for e in entries], sclosed)
    L = interp_sections(local, idx, m, c1, sA)
    rows = (A[:, None, :] + L[:, :, 0:1] * (cl[:, None, None] * e1[:, None, :])
            + (L[:, :, 1:2] * (pd * keep_t)[:, None, None]) * f2[:, None, :]
            + (L[:, :, 2:3] * pd[:, None, None]) * f3[:, None, :])
    V, F = grid_mesh(rows, sclosed, c1, cap)
    return (V, F, sclosed), ""


# ---- Revolve ----

def rotation_matrix(axis, ang):
    a = np.array(axis, dtype=np.float64)
    a = a / np.linalg.norm(a)
    K = np.array(((0, -a[2], a[1]), (a[2], 0, -a[0]), (-a[1], a[0], 0)))
    return np.eye(3) + math.sin(ang) * K + (1 - math.cos(ang)) * (K @ K)


def revolve_surface(paths, origin, axis, angle_deg, cap=True):
    """Révolution des contours autour de l'axe (origin, axis). Retourne (sommets, faces)."""
    full = abs(angle_deg) >= 359.999
    ang = math.radians(max(-360.0, min(360.0, angle_deg)))
    steps = max(6, int(math.ceil(abs(ang) / (2 * math.pi) * 64)))
    o = np.array(origin, dtype=np.float64)
    allV, allF = [], []
    base = 0
    for P, closed in paths:
        rows = []
        count = steps if full else steps + 1
        for s in range(count):
            Rm = rotation_matrix(axis, ang * s / steps)
            rows.append((P - o) @ Rm.T + o)
        V, F = grid_mesh(np.array(rows), closed, full, cap and not full)
        allV.append(V)
        allF.extend([tuple(i + base for i in f) for f in F])
        base += len(V)
    return np.vstack(allV), allF


class _RevolveBody(DessinTransform):
    bl_idname = "dessin.revolve"
    bl_label = "Revolve"
    bl_description = ("Revolves curves around an axis defined by two points: select the curves, Enter, "
                      "axis start, axis end, then Enter for a full circle or type the angle (C: cap ends, D: delete input)")

    TITLE = "Revolve"
    NEEDED = 3
    NUMFIELDS = 1
    HAS_CENTER = True
    HAS_MODE = True
    EDIT_OK = False
    MODES = ("keep the input curves", "delete the input curves")
    NO_SELECTION = "Select the curves to revolve first"

    def invoke(self, context, event):
        self.mode = 0
        self._paths = None
        result = super().invoke(context, event)
        self.center = True          # cap activé par défaut (profil fermé, angle < 360°)
        if 'RUNNING_MODAL' in result:
            self.refresh(context)
        return result

    def prompt(self):
        n = len(self.points)
        if n == 0:
            return "start of the revolve axis"
        if n == 1:
            return "end of the revolve axis   (Shift: orthogonal)"
        cap = "cap ON" if self.center else "cap OFF"
        mode = self.MODES[self.mode]
        return f"angle: type degrees then Enter, or Enter / click for 360°   [C: cap ends ({cap}), D: {mode}]"

    def capture_ghost(self, max_edges=0):
        self.ghost_pts = None
        self.ghost_batch = None

    def apply_live(self, xform):
        pass

    def restore(self):
        pass

    def handle_typing(self, event):
        return len(self.points) >= 2 and super().handle_typing(event)

    def profile_paths(self, context):
        if self._paths is None:
            dg = bpy.context.evaluated_depsgraph_get()
            paths = []
            for obj, _m in self.items:
                try:
                    paths.extend(object_paths(obj, dg))
                except ReferenceError:
                    pass
            self._paths = paths
        return self._paths

    def click(self, context):
        if not self.points:
            self._paths = None
        super().click(context)

    def reset_state(self):
        self._paths = None
        super().reset_state()

    def modal(self, context, event):
        if (not self.selecting and len(self.points) == 2 and event.value == 'PRESS'
                and event.type in {'RET', 'NUMPAD_ENTER', 'SPACE'} and not any(self.typed)):
            self.finish_shape(context)
            if self.finished:
                return self.exit(context)
            return {'RUNNING_MODAL'}
        return super().modal(context, event)

    def axis_end(self):
        a = self.points[0]
        b = self.points[1] if len(self.points) > 1 else self.cur
        d = b - a
        if len(self.points) == 1 and self.ortho:
            u, v, _ = plane_axes(self.axis)
            du, dv = d.dot(u), d.dot(v)
            d = u * du if abs(du) >= abs(dv) else v * dv
        return a, d

    def compute(self):
        if not self.points or self.cur is None:
            return [], [], "", None
        a, d = self.axis_end()
        if d.length < 1e-9:
            return [], [], "", None
        ext = d.normalized() * max(d.length, 1e-3)
        axis_line = [a - ext * 3.0, a + ext * 4.0]
        if len(self.points) == 1:
            return [], [axis_line], f"Axis length {self.fmt(d.length)}", None
        ang = self.typed_raw(0)
        angle = 360.0 if ang is None else max(-360.0, min(360.0, ang))
        guides = [axis_line]
        paths = self.profile_paths(bpy.context)
        if paths and abs(angle) > 1e-6:
            for k in range(1, 13):
                Rm = rotation_matrix(d, math.radians(angle) * k / 12.0)
                o = np.array(a)
                for P, closed in paths[:20]:
                    Q = (P - o) @ Rm.T + o
                    guides.append([Vector(q) for q in (np.vstack([Q, Q[:1]]) if closed else Q)])
        info = f"Angle {angle:g}°"
        return [], guides, info, ("revolve", a.copy(), d.copy(), angle, bool(self.center), self.mode == 1)

    def build(self, context, spec):
        _, o, d, angle, cap, delete = spec
        objs = [obj for obj, _m in self.items if obj.name in bpy.data.objects]
        dg = bpy.context.evaluated_depsgraph_get()
        made = []
        for obj in objs:
            paths = object_paths(obj, dg)
            if not paths:
                continue
            V, F = revolve_surface(paths, o, d, angle, cap)
            made.append(mesh_object_from_arrays(context, "Revolve", V, F, o, True))
        if not made:
            self.report({'WARNING'}, "Revolve works on curves (or outlines without faces)")
            self.committed = True
            return None
        if delete:
            delete_objects(objs)
            self.items = []
        deselect_all_objects(context)
        for ob in made:
            ob.select_set(True)
        context.view_layer.objects.active = made[-1]
        self.committed = True
        return None


class DESSIN_OT_revolve(_RevolveBody):
    """Registered class; the shared code lives in the unregistered base so SubD variants can inherit it."""
    bl_idname = _RevolveBody.bl_idname
    bl_label = _RevolveBody.bl_label
    bl_description = _RevolveBody.bl_description


# ---- Extrude (mode objet) : courbes / contours / faces -> volume ou surface ----

def outline_paths(obj, depsgraph):
    """Contours d'un objet : courbes et polylignes, ou bord (arêtes à une seule face) d'un maillage à faces."""
    try:
        if obj.type == 'MESH' and len(obj.data.polygons):
            ev = obj.evaluated_get(depsgraph)
            me = ev.to_mesh()
            try:
                bm = bmesh.new()
                bm.from_mesh(me)
                bm.transform(ev.matrix_world)
                bm.edges.ensure_lookup_table()
                bound = [e for e in bm.edges if len(e.link_faces) == 1]
                if not bound:
                    bm.free()
                    return []
                ids = {}
                verts, edges = [], []
                for e in bound:
                    pair = []
                    for v in e.verts:
                        if v.index not in ids:
                            ids[v.index] = len(verts)
                            verts.append(tuple(v.co))
                        pair.append(ids[v.index])
                    edges.append(tuple(pair))
                bm.free()
            finally:
                ev.to_mesh_clear()
            out = []
            for path, closed in wire_paths(len(verts), edges):
                if len(path) >= 2:
                    P = np.array([verts[i] for i in path], dtype=np.float64)
                    if closed and len(P) > 1 and np.linalg.norm(P[0] - P[-1]) <= 1e-9:
                        P = P[:-1]
                    out.append((P, bool(closed)))
            return out
    except (RuntimeError, ReferenceError):
        return []
    return object_paths(obj, depsgraph)


def _offset_loop(P, n, d, closed, inward_sign):
    """Décalage d'une polyligne plane (normale n) de d vers l'intérieur (côté gauche si inward_sign > 0), coins vifs (onglet)."""
    P = np.asarray(P, dtype=np.float64)
    m = len(P)
    if abs(d) < 1e-15 or m < 2:
        return P.copy()
    E = np.roll(P, -1, axis=0) - P if closed else np.vstack([P[1:] - P[:-1], (P[-1] - P[-2])[None]])
    L = np.linalg.norm(E, axis=1)
    L[L < 1e-15] = 1.0
    E = E / L[:, None]
    N = np.cross(n, E) * inward_sign                   # normale de chaque segment, vers l'intérieur
    out = P.copy()
    for i in range(m):
        if closed:
            a, b = N[i - 1], N[i]
        elif i == 0:
            a = b = N[0]
        elif i == m - 1:
            a = b = N[m - 2]
        else:
            a, b = N[i - 1], N[i]
        mv = a + b
        ln = np.linalg.norm(mv)
        if ln < 1e-9:
            mv, k = b, 1.0
        else:
            mv = mv / ln
            k = float(mv @ b)
            k = 1.0 / max(k, 0.2)                         # onglet borné (angles très aigus)
        out[i] = P[i] + mv * d * k
    return out


def _loop_orientation(P, n):
    """+1 si le contour fermé tourne dans le sens direct autour de n, -1 sinon."""
    P = np.asarray(P, dtype=np.float64)
    c = P.mean(axis=0)
    acc = np.sum(np.cross(P - c, np.roll(P, -1, axis=0) - c), axis=0)
    return 1.0 if float(acc @ n) >= 0 else -1.0


def extrude_general(paths, vec, cap=True, both=False, taper=0.0, apex=None):
    """ExtrudeCrv avec options de Rhino : BothSides (des deux côtés), Tapered (dépouille, angle en radians : positif = se
    resserre), ToPoint (vers un sommet). Les trous (contours dans un autre) s'élargissent quand le contour se resserre.
    Retourne (sommets, faces)."""
    v = np.asarray(vec, dtype=np.float64)
    h = float(np.linalg.norm(v))
    n = v / h if h > 1e-15 else np.array((0.0, 0.0, 1.0))
    loops = [(np.asarray(P, dtype=np.float64), bool(c)) for P, c in paths if len(P) >= 2]
    allV, allF = [], []
    base = 0
    # trous : contours fermés contenus dans un autre (dans le plan perpendiculaire à n)
    u = np.cross(n, (1.0, 0.0, 0.0))
    if np.linalg.norm(u) < 0.3:
        u = np.cross(n, (0.0, 1.0, 0.0))
    u = u / np.linalg.norm(u)
    w = np.cross(n, u)
    flat = [np.stack([P @ u, P @ w], axis=1) for P, _c in loops]
    depth = []
    for i, (P, c) in enumerate(loops):
        k = 0
        if c:
            for j, (Q, cq) in enumerate(loops):
                if j != i and cq and _pip_np(flat[i][0], flat[j]):
                    k += 1
        depth.append(k)
    tops, bottoms = [], []
    for i, (P, c) in enumerate(loops):
        if apex is not None:
            A = np.asarray(apex, dtype=np.float64)
            V = np.vstack([P, A[None]])
            ia = len(P)
            segs = len(P) if c else len(P) - 1
            allV.append(V)
            allF.extend(tuple(base + x for x in (k, (k + 1) % len(P), ia)) for k in range(segs))
            base += len(V)
            if c:
                bottoms.append(P)
            continue
        sign = (_loop_orientation(P, n) if c else 1.0) * (-1.0 if depth[i] % 2 else 1.0)
        d = h * math.tan(taper) if taper else 0.0
        top = _offset_loop(P, n, d, c, sign) + v
        if both:
            bot = _offset_loop(P, n, d, c, sign) - v
            rows = np.stack([bot, P, top])
        else:
            bot = P
            rows = np.stack([P, top])
        V, F = grid_mesh(rows, c, False, False)
        allV.append(V)
        allF.extend(tuple(x + base for x in f) for f in F)
        base += len(V)
        if c:
            tops.append(top)
            bottoms.append(bot)
    if cap:
        for ring_set, flip in ((bottoms, True), (tops, False)):
            if not ring_set:
                continue
            try:
                regions, _sk = planar_surfaces([(R, True) for R in ring_set])
            except (ValueError, RuntimeError, TypeError, np.linalg.LinAlgError):
                regions = []
            for Vr, Fr in regions:
                Vr = np.asarray(Vr, dtype=np.float64)
                allV.append(Vr)
                allF.extend(tuple(x + base for x in (reversed(f) if flip else f)) for f in Fr)
                base += len(Vr)
    if not allV:
        return np.zeros((0, 3)), []
    return np.vstack(allV), allF


_OPT_MEM = {}       # options mémorisées d'une utilisation à l'autre (Solid, DeleteInput... comme Rhino)


def extrude_surface(paths, vec, cap=True):
    """Extrusion des contours le long de vec : (sommets, faces). Les contours fermés peuvent être bouchés (volume) :
    les bouchons suivent les trous (un contour dans un autre donne un anneau, pas un couvercle plein)."""
    allV, allF = [], []
    base = 0
    v = np.array(vec, dtype=np.float64)
    closed_paths = []
    for P, closed in paths:
        rows = np.stack([P, P + v])
        V, F = grid_mesh(rows, closed, False, False)
        allV.append(V)
        allF.extend([tuple(i + base for i in f) for f in F])
        base += len(V)
        if closed and len(P) >= 3:
            closed_paths.append((P, closed))
    if cap and closed_paths:
        regions = []
        try:
            regions, _skipped = planar_surfaces(closed_paths)
        except (ValueError, RuntimeError, TypeError, np.linalg.LinAlgError):
            regions = []
        if len(regions) == 0 or sum(len(F) for _V, F in regions) == 0:
            pass        # contours non plans : pas de bouchon (comme Solid=Yes de Rhino, qui ne bouche que les courbes planes)
        else:
            for Vr, Fr in regions:
                Vr = np.asarray(Vr, dtype=np.float64)
                allV.append(Vr)
                allF.extend(tuple(i + base for i in reversed(f)) for f in Fr)       # bas
                base += len(Vr)
                allV.append(Vr + v)
                allF.extend(tuple(i + base for i in f) for f in Fr)                  # haut
                base += len(Vr)
    return np.vstack(allV), allF


def nest_groups(groups):
    """Regroupe les contours de plusieurs objets quand un contour fermé plan est à l'intérieur d'un autre (même plan) :
    ils forment alors une seule région à trou (ExtrudeCrv / PlanarSrf de Rhino). groups : [[(P, fermé)], ...] par objet."""
    n = len(groups)
    if n < 2:
        return groups
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    info = []      # (groupe, P, centre, normale, axe u, axe v, contour 2D, aire)
    for gi, paths in enumerate(groups):
        for P, closed in paths:
            P = np.asarray(P, dtype=np.float64)
            if not closed or len(P) < 3:
                continue
            pl = _plane_of(P)
            if pl is None or pl[2] > max(1e-3 * float(np.ptp(P, axis=0).max()), 1e-7):
                continue
            c, nrm = np.asarray(pl[0], dtype=np.float64), np.asarray(pl[1], dtype=np.float64)
            info.append((gi, P, c, nrm, float(pl[3])))
    for a_ in range(len(info)):
        ga, Pa, ca, na, aa = info[a_]
        u = Pa[1] - Pa[0]
        u = u - na * float(u.dot(na))
        u = u / (np.linalg.norm(u) or 1.0)
        v = np.cross(na, u)
        scale = float(np.ptp(Pa, axis=0).max())
        flat_a = np.stack([(Pa - ca) @ u, (Pa - ca) @ v], axis=1)
        for b_ in range(len(info)):
            gb, Pb, _cb, nb, ab = info[b_]
            if gb == ga or ab >= aa or abs(float(na.dot(nb))) < 0.9999:
                continue
            if float(np.abs((Pb - ca) @ na).max()) > max(1e-3 * scale, 1e-7):
                continue
            q = Pb[0] - ca
            if _point_in_poly(np.array([q @ u, q @ v]), flat_a):
                parent[find(gb)] = find(ga)
    out = {}
    for gi in range(n):
        out.setdefault(find(gi), []).extend(groups[gi])
    return list(out.values())


class ExtrudeCrvLogic(DessinTransform):
    bl_idname = "dessin.extrude_crv"
    bl_label = "Extrude Curve"
    bl_description = ("Extrudes curves, outlines or flat surfaces into a volume: select them, Enter, base point, then the height "
                      "(mouse or typed value, Enter). C: cap the ends, D: delete the input")

    TITLE = "Extrude"
    NEEDED = 2
    NUMFIELDS = 1
    HAS_CENTER = True
    HAS_MODE = True
    EDIT_OK = False
    PLANAR = False      # les points accrochés gardent leur hauteur
    MODES = ("keep the input curves", "delete the input curves")
    NO_SELECTION = "Select the curves or flat surfaces to extrude first"

    def invoke(self, context, event):
        mem = _OPT_MEM.get(self.bl_idname, {})
        self.mode = mem.get("mode", 0)
        self._paths = None
        result = super().invoke(context, event)
        self.center = mem.get("cap", True)   # bouchons activés par défaut ; Cap et DeleteInput sont mémorisés comme dans Rhino
        self.both = mem.get("both", False) if self.EXTRA_OPTS else False
        self.taper = mem.get("taper", False) if self.EXTRA_OPTS else False
        self.topoint = mem.get("topoint", False) if self.EXTRA_OPTS else False
        self.draft = mem.get("draft", 5.0)
        self.NUMFIELDS = 2 if self.taper and not self.topoint else 1
        if 'RUNNING_MODAL' in result:
            self.refresh(context)
        return result

    EXTRA_OPTS = False      # BothSides / Tapered / ToPoint (Extrude Curve seulement)

    def prompt(self):
        if not self.points:
            return "apex position on the plane (then its height)" if getattr(self, "topoint", False) else "base point"
        cap = "cap ON" if self.center else "cap OFF"
        extra = ""
        if self.EXTRA_OPTS:
            ang = self.draft_deg()
            extra = (f", B: both sides ({'ON' if self.both else 'OFF'}), T: tapered "
                     f"({f'{ang:g}°, Tab: angle' if self.taper else 'OFF'}), P: to point ({'ON' if self.topoint else 'OFF'})")
        what = "apex height" if getattr(self, "topoint", False) else "height"
        return (f"{what}: move the mouse or type the value then Enter   "
                f"[C: cap the ends ({cap}), D: {self.MODES[self.mode]}{extra}, Shift: orthogonal]")

    def draft_deg(self):
        t = self.typed_raw(1) if self.taper else None
        return t if t is not None else self.draft

    def modal(self, context, event):
        if (self.EXTRA_OPTS and not getattr(self, "selecting", False) and event.value == 'PRESS'
                and event.type in {'B', 'T', 'P'} and not (event.ctrl or event.alt or event.oskey)):
            if event.type == 'B':
                self.both = not self.both
            elif event.type == 'T':
                self.taper = not self.taper
            else:
                self.topoint = not self.topoint
            self.NUMFIELDS = 2 if self.taper and not self.topoint else 1
            if self.field >= self.NUMFIELDS:
                self.field = 0
            self.refresh(context)
            return {'RUNNING_MODAL'}
        return super().modal(context, event)

    def capture_ghost(self, max_edges=0):
        self.ghost_pts = None
        self.ghost_batch = None

    def apply_live(self, xform):
        pass

    def restore(self):
        pass

    def can_confirm_typed(self):
        return len(self.points) >= 1

    def handle_typing(self, event):
        return len(self.points) >= 1 and super().handle_typing(event)

    def profile_paths(self, context):
        if self._paths is None:
            dg = bpy.context.evaluated_depsgraph_get()
            paths = []
            for obj, _m in self.items:
                try:
                    paths.extend(outline_paths(obj, dg))
                except ReferenceError:
                    pass
            self._paths = paths
        return self._paths

    def click(self, context):
        if not self.points:
            self._paths = None
        super().click(context)

    def reset_state(self):
        self._paths = None
        super().reset_state()

    def curve_normal(self):
        """Normale commune des profils plans, comme ExtrudeCrv de Rhino : une courbe plane s'extrude perpendiculairement à
        son propre plan, quelle que soit la vue (une courbe dessinée à plat puis tournée de 90° part de côté, pas vers le
        haut). None si un profil n'est pas plan, si c'est une droite, ou si les profils sont dans des plans non parallèles :
        on garde alors l'axe du plan de construction (règle de Rhino pour les courbes non planes)."""
        paths = self.profile_paths(bpy.context)
        hit = getattr(self, "_cn_cache", None)
        if hit is not None and hit[0] is paths:
            return hit[1]
        res = None
        try:
            pts_all = [p for P, _c in paths for p in P]
            if pts_all and len(paths) <= 500:
                A = np.array([tuple(p) for p in pts_all], dtype=np.float64)
                size = float(np.ptp(A, axis=0).max())
                tol = 1e-6 * max(1.0, size) + 2e-7 * float(np.abs(A).max())
                common = None
                for P, _c in paths:
                    Q = np.array([tuple(p) for p in P], dtype=np.float64)
                    if len(Q) < 3:
                        common = None
                        break
                    c = Q.mean(axis=0)
                    _u, s, vh = np.linalg.svd(Q - c, full_matrices=False)
                    if len(s) < 3:
                        common = None
                        break
                    nrm = vh[2]
                    if np.abs((Q - c) @ vh[1]).max() <= tol or np.abs((Q - c) @ nrm).max() > tol:
                        common = None          # droite (pas de plan) ou courbe non plane
                        break
                    if common is None:
                        common = nrm
                    elif abs(float(common @ nrm)) < 1.0 - 1e-6:
                        common = None          # plans non parallèles
                        break
                if common is not None:
                    res = Vector(tuple(common)).normalized()
        except (ValueError, np.linalg.LinAlgError, TypeError):
            res = None
        self._cn_cache = (paths, res)
        return res

    def height_axis(self):
        base = plane_axes(self.axis)[2]
        n = self.curve_normal()
        if n is None:
            return base
        d = n.dot(base)
        if abs(d) > 1e-6:
            return n if d > 0 else -n            # courbe à plat dans le plan de construction : même sens qu'avant
        try:                                     # courbe « debout » : le sens positif vient vers l'observateur
            rv3d = region_rv3d(self.region, self.area)
            eye = rv3d.view_rotation @ Vector((0.0, 0.0, 1.0))
            d = n.dot(eye)
        except (AttributeError, ReferenceError, TypeError):
            d = 0.0
        if abs(d) > 1e-6:
            return n if d > 0 else -n
        k = max(range(3), key=lambda i: abs(n[i]))
        return n if n[k] > 0 else -n

    def update_cursor(self, context, event):
        """La hauteur suit la souris sur la verticale du point de base (et non sur le plan de construction, où elle resterait nulle)."""
        super().update_cursor(context, event)
        if (getattr(self, "selecting", False) or not self.points or self.cur is None
                or self.region is None or self.mouse_over_ui(event)):
            return
        if self.snap_screen is not None:
            # point accroché : sa hauteur compte, même si « Project » le ramène d'habitude dans le plan de construction
            raw = getattr(self, "_snap_pt", None)
            if raw is not None:
                n = self.height_axis()
                p0 = self.points[0]
                self.cur = p0 + n * (raw - p0).dot(n)
                self.refresh(context)
            return
        try:
            region = self.region
            rv3d = region_rv3d(region, self.area)
            coord = Vector((event.mouse_x - region.x, event.mouse_y - region.y))
            ro = region_2d_to_origin_3d(region, rv3d, coord)
            rv = region_2d_to_vector_3d(region, rv3d, coord)
            n = self.height_axis()
            p0 = self.points[0]
            h = view_height(p0, p0, n, ro, rv, rv3d)     # vue dans l'axe de la hauteur : distance du curseur (Rhino / AutoCAD)
        except (AttributeError, ReferenceError, TypeError, RuntimeError):
            return
        if h is not None:
            self.cur = p0 + n * h
            self.refresh(context)

    def height_vec(self):
        n = self.height_axis()
        d = self.cur - self.points[0]
        h = d.dot(n)
        t = self.typed_value(0)
        if t is not None:
            h = t if t < 0 else abs(t) * (1.0 if h >= 0 else -1.0)
        return n * h

    def compute(self):
        if not self.points or self.cur is None:
            return [], [], "", None
        vec = self.height_vec()
        if vec.length < 1e-9:
            return [], [], "", None
        opts = {}
        if self.EXTRA_OPTS and (self.both or self.taper or self.topoint):
            opts = {"both": self.both and not self.topoint, "taper": math.radians(self.draft_deg()) if self.taper and not self.topoint else 0.0,
                    "apex": tuple(self.points[0] + vec) if self.topoint else None}
        guides = []
        paths = self.profile_paths(bpy.context)[:20]
        if opts:
            try:
                V, F = extrude_general(paths, vec, False, opts["both"], opts["taper"], opts["apex"])
                edges = set()
                for f in F:
                    for i in range(len(f)):
                        edges.add(tuple(sorted((f[i], f[(i + 1) % len(f)]))))
                for a, b in list(edges)[:3000]:
                    guides.append([Vector(V[a]), Vector(V[b])])
            except (ValueError, IndexError, np.linalg.LinAlgError):
                pass
        else:
            for P, closed in paths:
                top = [Vector(p) + vec for p in P]
                if closed:
                    top.append(top[0])
                guides.append(top)
                step = max(1, len(P) // 24)
                for p in P[::step]:
                    guides.append([Vector(p), Vector(p) + vec])
        info = f"Height {self.fmt(vec.length)}"
        if opts.get("taper"):
            info += f"   draft {self.draft_deg():g}°"
        if opts.get("both"):
            info += "   both sides"
        return [], guides, info, ("extrude", self.points[0].copy(), vec.copy(), bool(self.center), self.mode == 1, opts)

    def build(self, context, spec):
        _, origin, vec, cap, delete = spec[:5]
        opts = spec[5] if len(spec) > 5 else {}
        _OPT_MEM[self.bl_idname] = {"cap": bool(cap), "mode": 1 if delete else 0, "both": getattr(self, "both", False),
                                    "taper": getattr(self, "taper", False), "topoint": getattr(self, "topoint", False),
                                    "draft": self.draft_deg() if getattr(self, "taper", False) else getattr(self, "draft", 5.0)}
        objs = [obj for obj, _m in self.items if obj.name in bpy.data.objects]
        dg = bpy.context.evaluated_depsgraph_get()
        made = []
        groups = [[(P, c) for P, c in outline_paths(obj, dg)] for obj in objs]
        if cap:
            # courbes ouvertes dont les bouts se touchent (même non jointes, même de plusieurs objets) : un seul contour
            # fermé, donc un solide bouché, comme Rhino
            allp = [pc for g in groups for pc in g]
            if any(not c for _P, c in allp):
                chained, left = chain_open_paths(allp)
                if left == 0:
                    groups = [[pc] for pc in chained]
            groups = nest_groups(groups)      # contours imbriqués (même venant d'objets différents) : un seul solide avec trou, comme Rhino
        for paths in groups:
            if not paths:
                continue
            if opts:
                V, F = extrude_general(paths, vec, cap, opts["both"], opts["taper"], opts["apex"])
                if not len(F):
                    continue
            else:
                V, F = extrude_surface(paths, vec, cap)
            made.append(mesh_object_from_arrays(context, "Extrusion", V, F, origin, True))
        if not made:
            self.report({'WARNING'}, "Extrude works on curves, outlines and flat surfaces")
            self.committed = True
            return None
        if delete:
            delete_objects(objs)
            self.items = []
        deselect_all_objects(context)
        for ob in made:
            ob.select_set(True)
        context.view_layer.objects.active = made[-1]
        self.committed = True
        return None


class DESSIN_OT_extrude_crv(ExtrudeCrvLogic):
    """Classe enregistrée (les sous-classes héritent de ExtrudeCrvLogic, non enregistrée : Blender perd le poll d'un parent enregistré)."""
    bl_idname = "dessin.extrude_crv"
    bl_label = "Extrude Curve"
    bl_description = ("Like ExtrudeCrv: extrudes curves, outlines or flat surfaces into a volume: select them, Enter, base point, "
                      "then the height (mouse or typed value, Enter). C: cap (Solid), D: delete the input, B: both sides, "
                      "T: tapered (draft angle, Tab to type it), P: to point")
    EXTRA_OPTS = True


FACE_PICK_KEY = "dessin_face_pick"


def face_island(bm, f0):
    """Une « face » au sens de Rhino : f0 et les faces reliées sans arête vive (même plan, ou courbure douce comme le
    flanc d'un cylindre), sans franchir une découpe marquée par Offset Edge / PushPull."""
    lay = bm.edges.layers.int.get(IMPRINT_LAYER)
    sharp = math.radians(EXPLODE_SHARP_DEG)
    seen = {f0}
    stack = [f0]
    while stack:
        f = stack.pop()
        for e in f.edges:
            if len(e.link_faces) != 2 or (lay is not None and e[lay]):
                continue
            g = e.link_faces[0] if e.link_faces[1] is f else e.link_faces[1]
            if g in seen:
                continue
            coplanar = g.normal.dot(f.normal) > 1.0 - 1e-6
            try:
                soft = e.smooth and not e.seam and e.calc_face_angle() <= sharp
            except ValueError:
                soft = False
            if coplanar or soft:
                seen.add(g)
                stack.append(g)
    return list(seen)


def mesh_is_polysurface(obj):
    """Vrai pour un solide ou une polysurface : plusieurs faces au sens de Rhino (séparées par des arêtes vives).
    Une surface simple (plane ou courbe, d'un seul tenant) répond faux."""
    if obj is None or obj.type != 'MESH' or len(obj.data.polygons) < 2 or obj.get(FACE_PICK_KEY):
        return False
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        bm.faces.ensure_lookup_table()
        bm.normal_update()
        return len(face_island(bm, bm.faces[0])) < len(bm.faces)
    finally:
        bm.free()


def face_pick_object(context, obj, face_index):
    """Copie (objet surface provisoire) de la face de Rhino qui contient la facette `face_index` de obj. (objet, clé)."""
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        bm.faces.ensure_lookup_table()
        bm.normal_update()
        isl = face_island(bm, bm.faces[face_index])
        key = (obj.name, min(f.index for f in isl))
        out = bmesh.new()
        vmap = {}
        for f in isl:
            for v in f.verts:
                if v not in vmap:
                    vmap[v] = out.verts.new(v.co)
        for f in isl:
            try:
                g = out.faces.new([vmap[v] for v in f.verts])
                g.material_index, g.smooth = f.material_index, f.smooth
            except ValueError:
                pass
        me = bpy.data.meshes.new(obj.data.name + "_face")
        out.to_mesh(me)
        out.free()
    finally:
        bm.free()
    for mt in obj.data.materials:
        me.materials.append(mt)
    tmp = bpy.data.objects.new(obj.name + " face", me)
    tmp.matrix_world = obj.matrix_world.copy()
    tmp[FACE_PICK_KEY] = 1
    _link_like(tmp, obj)
    return tmp, key


class DESSIN_OT_extrude_srf(ExtrudeCrvLogic):
    bl_idname = "dessin.extrude_srf"
    bl_label = "Extrude Surface"
    bl_description = ("Extrudes surfaces (faces) into a solid along their normal: select them, or click a face of a solid or "
                      "a polysurface (like a sub-object face in Rhino), Enter, base point, then the height "
                      "(mouse or typed value, Enter). C: cap the ends, D: delete the input")
    NO_SELECTION = "Select the surfaces to extrude first"

    # ---- faces de solides / polysurfaces : un clic choisit la face, comme Ctrl+Maj+clic dans Rhino ----
    def invoke(self, context, event):
        self._face_tmps = {}
        self._presel = []
        if context.mode == 'OBJECT':
            for o in list(context.selected_objects):
                if mesh_is_polysurface(o):
                    # un solide entier n'a pas de sens pour ExtrudeSrf : on demande la face
                    self._presel.append(o.name)
                    o.select_set(False)
        return super().invoke(context, event)

    def click_select(self, context, x, y, shift, ctrl):
        if not self.edit and not shift and not ctrl:
            try:
                rv3d = region_rv3d(self.region, self.area)
                coord = Vector((x, y))
                ro = region_2d_to_origin_3d(self.region, rv3d, coord)
                rv = region_2d_to_vector_3d(self.region, rv3d, coord)
                ok, _loc, _n, idx, obj, _m = ray_cast_opaque(context, ro, rv, True)
            except (RuntimeError, TypeError, ValueError, ReferenceError, AttributeError):
                ok, obj = False, None
            if ok and obj is not None and obj.type == 'MESH' and not obj.get(FACE_PICK_KEY):
                try:
                    dg = context.evaluated_depsgraph_get()
                    same = len(obj.evaluated_get(dg).data.polygons) == len(obj.data.polygons)
                except (RuntimeError, ReferenceError):
                    same = False
                if same and 0 <= idx < len(obj.data.polygons) and mesh_is_polysurface(obj):
                    tmp, key = face_pick_object(context, obj, idx)
                    old = self._face_tmps.get(key)
                    if old is not None and bpy.data.objects.get(old) is not None:
                        _drop_temp(tmp, True)          # face déjà choisie : on la resélectionne
                        tmp = bpy.data.objects[old]
                    else:
                        self._face_tmps[key] = tmp.name
                    obj.select_set(False)
                    tmp.select_set(True)
                    context.view_layer.objects.active = tmp
                    return
        super().click_select(context, x, y, shift, ctrl)

    def begin_transform(self, context, event):
        poly = [o for o in self.selected_now(context) if mesh_is_polysurface(o)]
        if poly:
            for o in poly:
                o.select_set(False)
            cmd_log("Extrude Surface: click a face of the solid to extrude it (a whole solid cannot be extruded)")
        return super().begin_transform(context, event)

    def refresh_selecting(self, context):
        super().refresh_selecting(context)
        if not self.edit:
            n = len([o for o in self.selected_now(context)])
            txt = (f"{self.TITLE} : select the surfaces, or click a face of a solid (click: add, drag: box, "
                   f"Shift+click: toggle, Ctrl/Cmd+click: remove)   |   {n} selected   |   Enter/Space: confirm   Esc: exit")
            try:
                set_prompt(self.area, txt)
            except ReferenceError:
                pass

    def cleanup(self, context):
        super().cleanup(context)
        for name in list(getattr(self, "_face_tmps", {}).values()):
            o = bpy.data.objects.get(name)
            if o is not None:
                _drop_temp(o, True)
        self._face_tmps = {}
        if not getattr(self, "finished", False):
            for name in getattr(self, "_presel", []):
                o = bpy.data.objects.get(name)
                if o is not None:
                    try:
                        o.select_set(True)
                    except RuntimeError:
                        pass
        self._presel = []

    def _normal(self):
        """Normale moyenne (monde) des surfaces sélectionnées."""
        # calculée une fois par commande (et en un passage numpy) : elle était refaite face par face plusieurs fois à chaque
        # mouvement de souris, ce qui faisait ramer l'aperçu sur une surface dense
        try:
            key = tuple((obj.name, len(obj.data.polygons) if obj.type == 'MESH' else 0,
                         tuple(tuple(r) for r in obj.matrix_world)) for obj, _m in self.items) + (self.axis,)
        except (ReferenceError, AttributeError):
            key = None
        hit = getattr(self, "_nrm_cache", None)
        if key is not None and hit is not None and hit[0] == key:
            return hit[1].copy()
        total = Vector((0.0, 0.0, 0.0))
        for obj, _m in self.items:
            try:
                if obj.type != 'MESH':
                    continue
                M = obj.matrix_world.to_3x3()
                nm = M.inverted_safe().transposed()
                n = len(obj.data.polygons)
                if not n:
                    continue
                nor = np.empty(n * 3, dtype=np.float32)
                ar = np.empty(n, dtype=np.float32)
                obj.data.polygons.foreach_get('normal', nor)
                obj.data.polygons.foreach_get('area', ar)
                v = (nor.reshape(-1, 3).astype(np.float64) * ar.astype(np.float64)[:, None]).sum(axis=0)
                total += nm @ Vector(v)
            except ReferenceError:
                pass
        res = plane_axes(self.axis)[2] if total.length < 1e-12 else total.normalized()
        if key is not None:
            self._nrm_cache = (key, res.copy())
        return res

    def height_axis(self):
        return self._normal()

    def height_vec(self):
        n = self._normal()
        d = self.cur - self.points[0]
        h = d.dot(n)
        t = self.typed_value(0)
        if t is not None:
            h = t if t < 0 else abs(t) * (1.0 if h >= 0 else -1.0)
        return n * h

    def build(self, context, spec):
        _, origin, vec, cap, delete = spec[:5]
        _OPT_MEM[self.bl_idname] = {"cap": bool(cap), "mode": 1 if delete else 0}
        objs = [obj for obj, _m in self.items if obj.name in bpy.data.objects and obj.type == 'MESH' and len(obj.data.polygons)]
        dg = bpy.context.evaluated_depsgraph_get()
        made = []
        for obj in objs:
            ev = obj.evaluated_get(dg)
            me = ev.to_mesh()
            try:
                bm = bmesh.new()
                bm.from_mesh(me)
            finally:
                ev.to_mesh_clear()
            bm.transform(ev.matrix_world)
            bm.faces.ensure_lookup_table()
            bound = [e for e in bm.edges if len(e.link_faces) == 1]
            geom = list(bm.faces) + list(bm.edges) + list(bm.verts)
            ext = bmesh.ops.extrude_face_region(bm, geom=geom)
            new_verts = [g for g in ext["geom"] if isinstance(g, bmesh.types.BMVert)]
            bmesh.ops.translate(bm, verts=new_verts, vec=vec)
            if not cap:
                # sans bouchon : on ne garde que la face translatée et les parois
                bmesh.ops.delete(bm, geom=[f for f in bm.faces if f not in
                                           {g for g in ext["geom"] if isinstance(g, bmesh.types.BMFace)}
                                           and all(v not in new_verts for v in f.verts)], context='FACES')
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
            V = [tuple(v.co) for v in bm.verts]
            idx = {v: i for i, v in enumerate(bm.verts)}
            F = [tuple(idx[v] for v in f.verts) for f in bm.faces]
            bm.free()
            made.append(mesh_object_from_arrays(context, "Extrusion", V, F, origin, False))
        if not made:
            self.report({'WARNING'}, "Extrude Surface works on surfaces (meshes with faces)")
            self.committed = True
            return None
        if delete:
            delete_objects(objs)
            self.items = []
        deselect_all_objects(context)
        for ob in made:
            ob.select_set(True)
        context.view_layer.objects.active = made[-1]
        self.committed = True
        return None


# ---- Loft / Sweep / Align (sélection par clics puis Entrée, avec une fenêtre d'options comme sur Rhino) ----

class _ProfileOp:
    """Aide commune : contours des objets sélectionnés (dans l'ordre des clics)."""

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and context.area is not None and context.area.type == 'VIEW_3D'

    def profiles(self, context):
        dg = context.evaluated_depsgraph_get()
        objs, profs = [], []
        for o in ordered_selection(context):
            p = object_profile(o, dg)
            if p is not None:
                objs.append(o)
                profs.append(p)
        return objs, profs

    def finish(self, context, name, built, origin, delete, objs):
        V, F, closed = built
        out = mesh_object_from_arrays(context, name, V, F, origin, True)
        if delete:
            delete_objects(objs)
        deselect_all_objects(context)
        out.select_set(True)
        context.view_layer.objects.active = out
        return out


class DESSIN_OT_loft(_ProfileOp, bpy.types.Operator):
    bl_idname = "dessin.loft"
    bl_label = "Loft"
    bl_description = ("Creates a surface through curves, in the order you clicked them "
                      "(options: closed loft, straight or smooth sections, cap, delete input)")
    bl_options = {'REGISTER', 'UNDO'}

    style: bpy.props.EnumProperty(name="Style", default='SMOOTH',
                                  items=(('SMOOTH', "Normal (smooth)", "Smooth surface through the sections"),
                                         ('STRAIGHT', "Straight sections", "Straight ruled surface between sections")))
    closed: bpy.props.BoolProperty(name="Closed loft", default=False,
                                   description="Joins the last section back to the first one")
    cap: bpy.props.BoolProperty(name="Cap ends", default=True, description="Closes the ends when the curves are closed (solid)")
    points: bpy.props.IntProperty(name="Refit points", default=0, min=0, soft_max=200,
                                  description="Number of points per section (0: automatic)")
    delete_input: bpy.props.BoolProperty(name="Delete input", default=False)

    def invoke(self, context, event):
        objs, profs = self.profiles(context)
        if len(profs) < 2:
            self.report({'INFO'}, "Click at least two curves in the order of the loft, then Enter")
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self, width=300)

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, "style", text="")
        col.prop(self, "closed")
        col.prop(self, "cap")
        col.prop(self, "points")
        col.prop(self, "delete_input")

    def execute(self, context):
        objs, profs = self.profiles(context)
        built, msg = loft_surface(profs, self.closed, self.style == 'SMOOTH', self.cap, self.points)
        if built is None:
            self.report({'WARNING'}, msg)
            return {'CANCELLED'}
        origin = profs[0][0].mean(axis=0)
        self.finish(context, "Loft", built, origin, self.delete_input, objs)
        return {'FINISHED'}


class _SweepBase(_ProfileOp):
    NRAILS = 1

    frame: bpy.props.EnumProperty(name="Frame", default='FREEFORM',
                                  items=(('FREEFORM', "Freeform", "The sections follow the rail with minimal twist"),
                                         ('UPRIGHT', "Keep Z up (roadlike)", "The sections stay upright along the rail")))
    miter: bpy.props.BoolProperty(name="Miter corners", default=True,
                                  description="Keeps the thickness constant at the corners of a polyline rail")
    cap: bpy.props.BoolProperty(name="Cap ends", default=True, description="Closes the ends when the sections are closed (solid)")
    delete_input: bpy.props.BoolProperty(name="Delete input", default=False)
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        objs, profs = self.profiles(context)
        if len(profs) < self.NRAILS + 1:
            self.report({'INFO'}, "Click the rail, then the cross-section(s), then Enter" if self.NRAILS == 1
                        else "Click the two rails, then the cross-section(s), then Enter")
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self, width=300)

    def draw(self, context):
        col = self.layout.column()
        if self.NRAILS == 1:
            col.prop(self, "frame", text="")
            col.prop(self, "miter")
        col.prop(self, "cap")
        col.prop(self, "delete_input")

    def execute(self, context):
        objs, profs = self.profiles(context)
        nr = self.NRAILS
        if len(profs) < nr + 1:
            self.report({'WARNING'}, "Not enough curves: rail(s) first, then at least one cross-section")
            return {'CANCELLED'}
        rails, sections = profs[:nr], profs[nr:]
        if nr == 1:
            built, msg = sweep1_surface(rails[0], sections, self.frame == 'UPRIGHT', self.miter, self.cap)
        else:
            built, msg = sweep2_surface(rails[0], rails[1], sections, self.cap)
        if built is None:
            self.report({'WARNING'}, msg)
            return {'CANCELLED'}
        origin = sections[0][0].mean(axis=0)
        self.finish(context, "Sweep 1 Rail" if nr == 1 else "Sweep 2 Rails", built, origin, self.delete_input, objs)
        return {'FINISHED'}


def extrude_along_surface(path, sections, cap=True):
    """Extrusion le long d'une courbe : le profil est translaté tout le long du chemin (sans rotation).
    path : (points, fermé) ; sections : [(points, fermé)]. Retourne ((V, F, fermé), '') ou (None, message)."""
    R, rclosed = path
    if not sections:
        return None, "Extrude Along Curve needs at least one profile"
    kinds = {c for _p, c in sections}
    if len(kinds) > 1:
        return None, "Extrude Along Curve: mix of open and closed profiles"
    sclosed = kinds.pop()
    P0 = sections[0][0]
    c = np.asarray(P0).mean(axis=0)
    R = np.asarray(R, dtype=np.float64)
    if not rclosed and np.linalg.norm(R[-1] - c) < np.linalg.norm(R[0] - c):
        R = R[::-1]
    off = R - R[0]
    n = max(len(p) for p, _c in sections)
    n = max(n, 3 if sclosed else 2)
    S = refine_points(P0, sclosed, n)
    rows = np.asarray(S)[None, :, :] + off[:, None, :]
    V, F = grid_mesh(rows, sclosed, rclosed, cap)
    return (V, F, sclosed), ""


class DESSIN_OT_extrude_path(_ProfileOp, bpy.types.Operator):
    bl_idname = "dessin.extrude_path"
    bl_label = "Extrude Along Curve"
    bl_description = ("Extrudes a profile along a path curve (the profile keeps its orientation): click the path first, then the profile; Enter")
    bl_options = {'REGISTER', 'UNDO'}

    cap: bpy.props.BoolProperty(name="Cap ends", default=True, description="Closes the ends when the profile is closed (solid)")
    delete_input: bpy.props.BoolProperty(name="Delete input", default=False)

    def invoke(self, context, event):
        objs, profs = self.profiles(context)
        if len(profs) < 2:
            self.report({'INFO'}, "Click the path first, then the profile, then Enter")
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self, width=300)

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, "cap")
        col.prop(self, "delete_input")

    def execute(self, context):
        objs, profs = self.profiles(context)
        if len(profs) < 2:
            self.report({'WARNING'}, "Not enough curves: the path first, then the profile")
            return {'CANCELLED'}
        built, msg = extrude_along_surface(profs[0], profs[1:], self.cap)
        if built is None:
            self.report({'WARNING'}, msg)
            return {'CANCELLED'}
        self.finish(context, "Extrude Along Curve", built, profs[1][0].mean(axis=0), self.delete_input, objs)
        return {'FINISHED'}


class DESSIN_OT_sweep1(_SweepBase, bpy.types.Operator):
    bl_idname = "dessin.sweep1"
    bl_label = "Sweep 1 Rail"
    bl_description = "Sweeps cross-sections along one rail: click the rail first, then the cross-sections; Enter"
    NRAILS = 1


class DESSIN_OT_sweep2(_SweepBase, bpy.types.Operator):
    bl_idname = "dessin.sweep2"
    bl_label = "Sweep 2 Rails"
    bl_description = "Sweeps cross-sections between two rails: click the two rails first, then the cross-sections; Enter"
    NRAILS = 2


# ---- Surfaces : Planar Surface / Edge Surface / Thicken / Cap ----

def _plane_of(P):
    """(centre, normale unitaire, écart max au plan, aire) d'un contour fermé (n,3)."""
    n = newell_normal(P)
    ln = float(np.linalg.norm(n))
    if ln < 1e-14:
        return None
    n = n / ln
    c = P.mean(axis=0)
    return c, n, float(np.abs((P - c) @ n).max()), ln * 0.5


def _point_in_poly(pt, poly):
    """Point dans polygone 2D (lancer de rayon)."""
    x, y = pt
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-30) + xi:
            inside = not inside
        j = i
    return inside


def chain_open_paths(paths, tol=None):
    """Raccorde, comme PlanarSrf de Rhino, les courbes ouvertes dont les extrémités se touchent (à tol près),
    même si elles viennent d'objets différents. paths : [(P, closed)] -> ([(P, closed)], nb de chaînes restées ouvertes)."""
    closed_out = [(P, c) for P, c in paths if c]
    pieces = [np.asarray(P, dtype=np.float64) for P, c in paths if not c and len(P) >= 2]
    if not pieces:
        return closed_out, 0
    allp = np.vstack(pieces)
    scale = float(np.ptp(allp, axis=0).max()) or 1.0
    if tol is None:
        tol = max(1e-4 * scale, 1e-7)
    # extrémités de tous les morceaux dans un arbre de recherche : trouver le morceau suivant ne parcourt plus tous les
    # autres (avec des milliers de courbes, la double boucle Python d'origine prenait des minutes)
    from mathutils import kdtree
    ends = np.stack([np.stack((Q[0], Q[-1])) for Q in pieces]).reshape(-1, 3)      # ligne 2k : début de k, 2k+1 : fin
    kd = kdtree.KDTree(len(ends))
    for j, e_ in enumerate(ends):
        kd.insert(e_, j)
    kd.balance()
    reach = tol * 1.01 + 1e-6 * scale        # l'arbre est en simple précision : rayon un peu large, distances recalculées
    alive = np.ones(len(pieces), dtype=bool)
    n_alive = len(pieces)
    nxt = 0
    open_left = 0
    while n_alive:
        while not alive[nxt]:
            nxt += 1
        k0 = nxt
        alive[k0] = False
        n_alive -= 1
        chain = pieces[k0]
        grew = True
        while grew and n_alive:
            grew = False
            best = None
            for end in (1, 0):
                pt = chain[-1] if end else chain[0]
                cand = sorted(j for _co, j, _d in kd.find_range(pt, reach) if alive[j // 2])
                for j in cand:                                       # ordre croissant : même choix que la double boucle
                    d = float(np.linalg.norm(ends[j] - pt))
                    if d <= tol and (best is None or d < best[0]):
                        best = (d, end, j // 2, bool(j % 2))
            if best:
                _d, end, k, rev = best
                Q = pieces[k][::-1] if rev else pieces[k]
                if end:
                    chain = np.vstack([chain, Q[1:] if np.linalg.norm(Q[0] - chain[-1]) <= tol else Q])
                else:
                    Qr = Q[::-1]
                    chain = np.vstack([Qr[:-1] if np.linalg.norm(Qr[-1] - chain[0]) <= tol else Qr, chain])
                alive[k] = False
                n_alive -= 1
                grew = True
        if len(chain) >= 3 and float(np.linalg.norm(chain[0] - chain[-1])) <= tol:
            closed_out.append((chain[:-1], True))
        else:
            open_left += 1
    return closed_out, open_left


def planar_surfaces(paths):
    """Contours fermés -> surfaces planes (trous gérés par imbrication paire / impaire).
    Les courbes ouvertes qui se touchent par leurs extrémités sont d'abord raccordées (sans les joindre).
    Retourne ([(sommets, faces)], nb de contours ignorés)."""
    loops = []
    paths, skipped = chain_open_paths(paths)
    for P, closed in paths:
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
    out = []
    while loops:
        P0, (c, n, _d, _a) = loops[0]
        scale = float(np.ptp(P0, axis=0).max())
        group, rest = [], []
        for item in loops:
            P, (_c2, n2, _d2, _a2) = item
            if abs(float(n.dot(n2))) > 0.9999 and float(np.abs((P - c) @ n).max()) <= max(1e-3 * scale, 1e-7):
                group.append(item)
            else:
                rest.append(item)
        loops = rest
        u = P0[1] - P0[0]
        u = u - n * float(u.dot(n))
        u = u / (np.linalg.norm(u) or 1.0)
        v = np.cross(n, u)
        flat = [np.stack([(P - c) @ u, (P - c) @ v], axis=1) for P, _pl in group]
        depth, parent = [], []
        for i in range(len(group)):
            cont = [j for j in range(len(group)) if j != i and group[j][1][3] > group[i][1][3]
                    and _point_in_poly(flat[i][0], flat[j])]
            depth.append(len(cont))
            parent.append(min(cont, key=lambda j: group[j][1][3]) if cont else None)
        for i in range(len(group)):
            if depth[i] % 2:
                continue
            holes = [j for j in range(len(group)) if depth[j] == depth[i] + 1 and parent[j] == i]
            rings = [i] + holes
            if not holes:
                V = group[i][0]
                F = [tuple(range(len(V)))]
            else:
                polys = [[Vector((float(p[0]), float(p[1]), 0.0)) for p in flat[k]] for k in rings]
                tris = geometry.tessellate_polygon(polys)
                V = np.vstack([group[k][0] for k in rings])
                F = [tuple(t) for t in tris]
            out.append((np.array(V, dtype=np.float64), F))
    return out, skipped


class DESSIN_OT_planar_srf(_ProfileOp, bpy.types.Operator):
    bl_idname = "dessin.planar_srf"
    bl_label = "Planar Surface"
    bl_description = ("Creates planar surfaces from closed planar curves (curves inside another one become holes): "
                      "click the curves (or select them first), then Enter / Space")
    bl_options = {'REGISTER', 'UNDO'}

    delete_input: bpy.props.BoolProperty(name="Delete input", default=False)

    def invoke(self, context, event):
        return self.execute(context)

    def execute(self, context):
        dg = context.evaluated_depsgraph_get()
        objs = ordered_selection(context)
        paths = []
        used = []
        for o in objs:
            p = object_paths(o, dg)
            if p:
                paths.extend(p)
                used.append(o)
        if not paths:
            self.report({'INFO'}, "Click the closed planar curves, then Enter")
            return {'CANCELLED'}
        made, skipped = planar_surfaces(paths)
        if not made:
            self.report({'WARNING'}, "Planar Surface needs closed planar curves (or curves whose ends touch)")
            return {'CANCELLED'}
        deselect_all_objects(context)
        last = None
        for V, F in made:
            last = mesh_object_from_arrays(context, "Planar Surface", V, F, V.mean(axis=0), False)
            last.select_set(True)
        if self.delete_input:
            delete_objects(used)
        context.view_layer.objects.active = last
        msg = f"{len(made)} planar surface(s) created"
        if skipped:
            msg += f", {skipped} curve(s) ignored (open or not planar)"
        self.report({'INFO'}, msg)
        return {'FINISHED'}


def _late_imports():
    """Noms définis dans des modules chargés après celui-ci : ils ne servent qu'à l'exécution des outils."""
    global IMPRINT_LAYER, _pip_np, cmd_log, set_prompt
    from .hatch import _pip_np
    from .cplane import cmd_log, set_prompt
    from .pushpull import IMPRINT_LAYER
