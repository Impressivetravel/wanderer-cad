"""Wanderer CAD : PushPull et découpe des faces."""

import bmesh
import bpy
import gpu
import math
import numpy as np
from bpy_extras.view3d_utils import region_2d_to_origin_3d, region_2d_to_vector_3d
from gpu_extras.batch import batch_for_shader
from mathutils import Vector, geometry

from .core import NAV_TYPES, _LAST_TYPED, cp_frame, cp_set, cp_state, last_typed, osnap, unit_info
from .snapping import collect_snap_points
from .drawing import (
    _same_region, draw_snap_marker, find_snap_in, find_window_region, get_shader, main_window_region, region_rv3d,
)
from .base import view_height
from .booleans import _link_like, boolean_mesh, boolean_solvers
from .selection import BOX_BLUE, BOX_ORANGE, ray_cast_opaque
from .join_explode import EXPLODE_SHARP_DEG
from .surfaces import _point_in_poly, mesh_object_from_arrays, object_paths, planar_surfaces
from .hatch import _hatch_paths_of, _pip_np, _poly_area2, hatch_loop_groups, hatch_region_at
from .gumball_handles import mesh_is_closed
from .cplane import cmd_log, set_prompt


# ---- PushPull : tirer / pousser une face d'un solide ou d'une surface le long de sa normale ----
IMPRINT_LAYER = "dessin_imprint"


def imprint_offset(obj, P_world, Q_world):
    """Découpe la face plane de `obj` dont le pourtour est la chaîne fermée P par le contour décalé Q (à l'intérieur) :
    la face devient un anneau + une face intérieure. Les arêtes de Q sont marquées : PushPull ne fusionne pas ces deux
    régions bien qu'elles soient coplanaires. Retourne False (rien n'est modifié) si la situation ne s'y prête pas."""
    if obj.type != 'MESH' or len(P_world) < 3 or len(P_world) != len(Q_world) or obj.modifiers:
        return False
    from mathutils.kdtree import KDTree
    inv = obj.matrix_world.inverted()
    Pl = [inv @ Vector(p) for p in P_world]
    Ql = [inv @ Vector(q) for q in Q_world]
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        if not bm.verts:
            return False
        kd = KDTree(len(bm.verts))
        for v in bm.verts:
            kd.insert(v.co, v.index)
        kd.balance()
        size = max(max(obj.dimensions), 1e-6) / max(max(obj.scale), 1e-6)
        tol = 1e-5 * max(1.0, size)
        PV = []
        for p in Pl:
            _co, i, dist = kd.find(p)
            if i is None or dist > tol:
                return False
            PV.append(bm.verts[i])
        k = len(PV)
        if len(set(PV)) != k:
            return False
        pset = set(PV)
        # la face (ou le groupe de faces coplanaires, ex. triangulées) dont le pourtour est exactement P
        region = None
        for f in PV[0].link_faces:
            reg = pp_region(bm, f)
            bnd = pp_boundary(reg)
            if {v for e in bnd for v in e.verts} == pset and len(bnd) == k:
                region = reg
                break
        if region is None:
            return False
        n = region[0].normal.copy()
        d0 = n.dot(PV[0].co)
        u = (PV[1].co - PV[0].co)
        u = (u - n * u.dot(n)).normalized()
        w = n.cross(u)
        poly = [((v.co - PV[0].co).dot(u), (v.co - PV[0].co).dot(w)) for v in PV]
        for q in Ql:
            if abs(n.dot(q) - d0) > tol * 10:
                return False
            if not _point_in_poly(((q - PV[0].co).dot(u), (q - PV[0].co).dot(w)), poly):
                return False          # décalage vers l'extérieur : on garde le contour séparé
        area2 = sum(poly[i][0] * poly[(i + 1) % k][1] - poly[(i + 1) % k][0] * poly[i][1] for i in range(k))
        mat, smooth = region[0].material_index, region[0].smooth
        bmesh.ops.delete(bm, geom=region, context='FACES_ONLY')
        keep = {e for i in range(k) for e in [bm.edges.get((PV[i], PV[(i + 1) % k]))] if e is not None}
        loose = [e for e in {e for v in pset for e in v.link_edges} if not e.link_faces and e not in keep]
        if loose:
            bmesh.ops.delete(bm, geom=loose, context='EDGES')
        QV = [bm.verts.new(q) for q in Ql]
        order = list(range(k)) if area2 > 0 else list(range(k - 1, -1, -1))     # P dans le sens direct autour de n
        new_faces = []
        for a_, b_ in zip(order, order[1:] + order[:1]):
            new_faces.append(bm.faces.new((PV[a_], PV[b_], QV[b_], QV[a_])))
        new_faces.append(bm.faces.new([QV[i] for i in order]))
        lay = bm.edges.layers.int.get(IMPRINT_LAYER) or bm.edges.layers.int.new(IMPRINT_LAYER)
        for i in range(k):
            e = bm.edges.get((QV[i], QV[(i + 1) % k]))
            if e is not None:
                e[lay] = 1
        bm.normal_update()
        for f in new_faces:
            f.material_index, f.smooth = mat, smooth
            if f.normal.dot(n) < 0:
                f.normal_flip()
        bm.normal_update()
        bm.to_mesh(obj.data)
        obj.data.update()
        return True
    except (ValueError, IndexError, ReferenceError):
        return False
    finally:
        bm.free()


def pp_region(bm, f0):
    """La face f0 et les faces coplanaires qui lui sont reliées (une face « visuelle », même triangulée).
    Une arête marquée par Offset Edge (découpe d'une face) sépare deux régions même coplanaires."""
    n = f0.normal.copy()
    d = n.dot(f0.verts[0].co)
    tol = 1e-4 * max(1.0, abs(d))
    lay = bm.edges.layers.int.get(IMPRINT_LAYER)
    seen = {f0}
    stack = [f0]
    while stack:
        f = stack.pop()
        for e in f.edges:
            if lay is not None and e[lay]:
                continue
            for g in e.link_faces:
                if g not in seen and g.normal.dot(n) > 1.0 - 1e-6 and abs(n.dot(g.verts[0].co) - d) < tol:
                    seen.add(g)
                    stack.append(g)
    return list(seen)


def pp_boundary(faces):
    """Arêtes du pourtour d'un groupe de faces."""
    fs = set(faces)
    return [e for f in faces for e in f.edges if sum(1 for g in e.link_faces if g in fs) == 1]


PP_CURVED_AREA_RATIO = 4.0      # au-delà, une plaque plane tangente à des facettes courbes est une face à part (dessus d'une boîte à congés)
PP_PREVIEW_EDGES = 1500         # arêtes dessinées au plus dans l'aperçu d'une face courbe


def _pp_patch_area(f, cache):
    """Aire de la plaque plane (facettes coplanaires reliées) qui contient f."""
    a = cache.get(f)
    if a is not None:
        return a
    n = f.normal
    seen = {f}
    stack = [f]
    area = 0.0
    while stack:
        g = stack.pop()
        area += g.calc_area()
        for e in g.edges:
            for h in e.link_faces:
                if h not in seen and h.normal.dot(n) > 1.0 - 1e-6:
                    seen.add(h)
                    stack.append(h)
    for g in seen:
        cache[g] = area
    return area


def pp_curved_region(bm, f0):
    """La face courbe (au sens de Rhino) qui contient f0 : les facettes reliées par des arêtes douces et de taille
    comparable (flanc d'un cylindre, sphère, congé, voûte...). None si f0 appartient à une face plane.
    Une grande plaque plane tangente à des facettes courbes (dessus d'une boîte à congés, côté droit d'une forme oblongue)
    reste une face plane : on ne la traverse pas."""
    lay = bm.edges.layers.int.get(IMPRINT_LAYER)
    sharp = math.radians(EXPLODE_SHARP_DEG)
    cache = {}
    seen = {f0}
    stack = [f0]
    curved = False
    while stack:
        f = stack.pop()
        af = _pp_patch_area(f, cache)
        for e in f.edges:
            if len(e.link_faces) != 2 or (lay is not None and e[lay]):
                continue
            g = e.link_faces[0] if e.link_faces[1] is f else e.link_faces[1]
            if g in seen:
                continue
            if g.normal.dot(f.normal) > 1.0 - 1e-6:
                seen.add(g)
                stack.append(g)
                continue
            try:
                soft = e.smooth and not e.seam and e.calc_face_angle() <= sharp
            except ValueError:
                soft = False
            if not soft:
                continue
            ag = _pp_patch_area(g, cache)
            if max(af, ag) > PP_CURVED_AREA_RATIO * min(af, ag):
                continue
            seen.add(g)
            stack.append(g)
            curved = True
    return list(seen) if curved else None


def _pp_region_normals(obj, faces):
    """Normale (monde) en chaque sommet d'une face courbe : moyenne des normales de ses facettes, pondérée par l'angle.
    Les sommets d'un maillage qui approche une surface lisse sont sur cette surface : décalés de d le long de cette
    normale, ils restent sur la surface décalée (un cylindre de rayon r devient un cylindre de rayon r + d).
    Au bord de la face il manque les facettes de l'autre côté : on les prolonge (facettes « fantômes » qui continuent la
    courbure d'une rangée à la suivante), sinon la normale du bord serait décalée d'un demi-pas (bord d'une voûte,
    équateur d'une demi-sphère)."""
    nmat = obj.matrix_world.to_3x3().inverted().transposed()
    fs = set(faces)
    nw = {f: (nmat @ f.normal).normalized() for f in faces}

    def bend(f, e):
        """Rotation qui prolonge la courbure au-delà de l'arête de bord e de la facette f (None : pas de courbure connue)."""
        if len(f.verts) != 4:
            return None
        a, b = e.verts
        for x in f.edges:
            if a not in x.verts and b not in x.verts:
                for g in x.link_faces:
                    if g is not f and g in fs:
                        return nw[g].rotation_difference(nw[f])
        return None

    is_bnd = {}

    def bnd(e):
        r = is_bnd.get(e)
        if r is None:
            r = is_bnd[e] = sum(1 for g in e.link_faces if g in fs) == 1
        return r

    acc = {}
    for f in faces:
        nf = nw[f]
        for l in f.loops:
            w = l.calc_angle()
            tot = nf.copy()
            q1 = bend(f, l.edge) if bnd(l.edge) else False
            ep = l.link_loop_prev.edge
            q2 = bend(f, ep) if bnd(ep) else False
            g1 = None
            if q1 is not False:
                g1 = (q1 @ nf) if q1 is not None else nf
                tot += g1
            if q2 is not False:
                tot += (q2 @ nf) if q2 is not None else nf
                if g1 is not None:
                    tot += (q2 @ g1) if q2 is not None else g1        # facette fantôme en diagonale (coin de la face)
            acc[l.vert] = acc.get(l.vert, Vector((0.0, 0.0, 0.0))) + tot * w
    return {v: (n.normalized() if n.length > 1e-9 else None) for v, n in acc.items()}


def _pp_self_hits(bm):
    from mathutils.bvhtree import BVHTree
    bm.faces.ensure_lookup_table()
    t = BVHTree.FromBMesh(bm)
    fl = bm.faces
    return sum(1 for a, b in t.overlap(t) if a < b and not set(fl[a].verts) & set(fl[b].verts))


def _push_pull_curved(obj, bm, faces, dist):
    """PushPull d'une face courbe : elle est décalée de dist le long de ses normales (comme PushPull de Rhino sur une
    face non plane). Les faces voisines suivent quand le déplacement reste dans leur plan (bouchons d'un cylindre, faces
    percées par un trou) ; sinon la matière est ajoutée ou retirée par un booléen vérifié. Retourne un message ou ''."""
    me = obj.data
    inv3 = obj.matrix_world.to_3x3().inverted()
    nmat = inv3.transposed()
    size = max(max(obj.dimensions), 1e-6) / max(max(abs(sc) for sc in obj.scale), 1e-6)
    eps = max(1e-6, 1e-4 * size)
    fs = set(faces)
    normals = _pp_region_normals(obj, faces)
    if any(n is None for n in normals.values()):
        return "this face folds back on itself: it cannot be offset"
    disp = {v: inv3 @ (n * dist) for v, n in normals.items()}
    old_n = {f: f.normal.copy() for f in faces}

    def folded():
        """La face décalée se retourne quelque part (distance plus grande que son rayon de courbure)."""
        for f in faces:
            pts = [v.co + disp[v] for v in f.verts]
            n = geometry.normal(pts) if len(pts) >= 3 else None
            if n is None or n.length < 1e-12 or n.dot(old_n[f]) <= 1e-6:
                return True
        return False

    if folded():
        return "the distance is larger than the curvature of this face (it would fold over itself)"
    bound = pp_boundary(faces)
    closed_solid = all(len(e.link_faces) == 2 for e in bm.edges)
    if closed_solid:
        slide = True
        for e in bound:
            for v in e.verts:
                for g in v.link_faces:
                    if g not in fs and abs((nmat @ g.normal).normalized().dot(normals[v])) > 1e-4:
                        slide = False
                        break
                if not slide:
                    break
            if not slide:
                break
        if slide:
            # les voisines sont dans le plan du déplacement : la face glisse, les voisines s'agrandissent ou se réduisent
            before = [(v, v.co.copy()) for v in disp]
            vol0 = bm.calc_volume()
            for v, d in disp.items():
                v.co += d
            bm.normal_update()
            vol1 = bm.calc_volume()
            bad = vol1 * vol0 <= 0.0 or abs(vol1) < 1e-12 * max(1.0, abs(vol0))
            if not bad and len(bm.faces) <= 300000 and _pp_self_hits(bm):
                for v, co in before:
                    v.co = co
                bm.normal_update()
                hits0 = _pp_self_hits(bm)
                for v, d in disp.items():
                    v.co += d
                bm.normal_update()
                bad = _pp_self_hits(bm) > hits0
            if bad:
                return "the face would cross the rest of the solid at this distance"
            bm.to_mesh(me)
            me.update()
            return ""
        # sinon : coque entre la face et sa copie décalée, unie au solide (tirer) ou retirée (pousser)
        sgn = 1.0 if dist > 0 else -1.0
        cb = bmesh.new()
        try:
            base, top = {}, {}
            bverts = {v for e in bound for v in e.verts}
            for v, n in normals.items():
                t = n
                if v in bverts:
                    # au bord, le départ de la coque glisse dans le plan des faces voisines : il ne sort jamais du solide
                    for g in v.link_faces:
                        if g not in fs:
                            ng = (nmat @ g.normal).normalized()
                            k = t.dot(ng)
                            if k < 0.0:
                                t = t - ng * k
                base[v] = cb.verts.new(v.co + inv3 @ (t * (-sgn * eps)))
                top[v] = cb.verts.new(v.co + disp[v])
            for f in faces:
                cb.faces.new([base[v] for v in reversed(f.verts)])
                cb.faces.new([top[v] for v in f.verts])
            for e in bound:
                a, b = e.verts
                try:
                    cb.faces.new([base[a], base[b], top[b]])
                    cb.faces.new([base[a], top[b], top[a]])
                except ValueError:
                    pass
            cb.normal_update()
            bmesh.ops.recalc_face_normals(cb, faces=cb.faces[:])
            cme = bpy.data.meshes.new("pp_shell")
            cb.to_mesh(cme)
        finally:
            cb.free()
        cutter = bpy.data.objects.new("pp_shell", cme)
        cutter.matrix_world = obj.matrix_world.copy()
        bpy.context.scene.collection.objects.link(cutter)
        bpy.context.view_layer.update()
        try:
            good = solid_boolean(obj, cutter, 'UNION' if dist > 0 else 'DIFFERENCE', eps) if mesh_is_closed(cme) else None
        finally:
            bpy.data.objects.remove(cutter)
            if cme.users == 0:
                bpy.data.meshes.remove(cme)
        if good is None:
            return "the offset of this face could not be computed on this mesh (the solid is unchanged)"
        try:
            if len(good.polygons) == 0:
                return "the push removes the whole solid"
            write_solid(obj, good, eps)
        finally:
            bpy.data.meshes.remove(good)
        return ""
    # surface (ou polysurface ouverte) : la face décalée est reliée à l'ancienne par des parois
    lone = bool(bound) and all(len(e.link_faces) == 1 for e in bound) and len(fs) == len(bm.faces)
    top = {v: bm.verts.new(v.co + disp[v]) for v in disp}
    for f in faces:
        nf = bm.faces.new([top[v] for v in f.verts])
        nf.smooth = f.smooth
    for e in bound:
        a, b = e.verts
        try:
            bm.faces.new([a, b, top[b], top[a]])
        except ValueError:
            pass
    if not lone:
        bmesh.ops.delete(bm, geom=faces, context='FACES')
    bm.normal_update()
    if all(len(e.link_faces) == 2 for e in bm.edges):
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.to_mesh(me)
    me.update()
    return ""


def _pp_needs_boolean(bm, faces, vec, tol):
    """PushPull d'une région d'un solide fermé : vrai si le simple déplacement de la face donnerait un solide faux, et
    qu'il faut un booléen exact. C'est le cas quand
    - on pousse vers l'intérieur une région bordée par un mur (face non coplanaire) : le mur doit être recoupé ;
    - le prisme balayé par la région rencontre une autre partie du solide (fond traversé, autre branche atteinte) :
      rayons lancés depuis la région dans le sens de la poussée, et sommets du solide situés dans le prisme."""
    from mathutils.bvhtree import BVHTree
    rset = set(faces)
    n = faces[0].normal.copy()
    L = vec.length
    if L < 1e-12:
        return False
    dirv = vec / L
    inward = dirv.dot(n) < 0
    bound = pp_boundary(faces)
    if inward:
        d0 = n.dot(faces[0].verts[0].co)
        for e in bound:
            for g in e.link_faces:
                if g in rset:
                    continue
                if g.normal.dot(n) < 1.0 - 1e-6 or abs(n.dot(g.verts[0].co) - d0) > tol:
                    return True
    bm.faces.index_update()
    bm.faces.ensure_lookup_table()
    tree = BVHTree.FromBMesh(bm)
    ridx = {f.index for f in faces}
    samples = [v.co.copy() for v in {v for f in faces for v in f.verts}]
    samples += [f.calc_center_median() for f in faces]
    samples += [(e.verts[0].co + e.verts[1].co) * 0.5 for e in bound]
    for p in samples:
        o = p + dirv * tol
        left = L
        for _ in range(64):
            hit, _nrm, idx, dist = tree.ray_cast(o, dirv, left + tol)
            if hit is None:
                break
            if idx not in ridx:
                return True
            o = hit + dirv * tol
            left -= dist + tol
            if left < 0:
                break
    # sommets du solide à l'intérieur du prisme (une partie du solide se trouve sur le chemin)
    rverts = {v for f in faces for v in f.verts}
    pts = [v.co for v in bm.verts if v not in rverts]
    if not pts:
        return False
    P = np.array([tuple(q) for q in pts], dtype=np.float64)
    o0 = np.array(tuple(faces[0].verts[0].co), dtype=np.float64)
    dv = np.array(tuple(dirv), dtype=np.float64)
    depth = (P - o0) @ dv
    cand = np.nonzero((depth > tol) & (depth <= L + tol))[0]
    if not len(cand):
        return False
    o, u, w, _nn = _region_frame(faces)
    rings = _boundary_rings(bound)
    flat = [[((v.co - o).dot(u), (v.co - o).dot(w)) for v in r] for r in rings]
    if not flat:
        return False
    area = [abs(_poly_area2(F)) for F in flat]
    outer = int(np.argmax(area))
    U = np.array(tuple(u)); Wv = np.array(tuple(w)); O = np.array(tuple(o))
    for i in cand:
        q = P[i] - dv * depth[i] - O
        q2 = (float(q @ U), float(q @ Wv))
        if _pip_np(q2, flat[outer]) and not any(_pip_np(q2, flat[k]) for k in range(len(flat)) if k != outer):
            return True
    return False


def solid_boolean(obj, cutter, op, eps=None):
    """Booléen (UNION / DIFFERENCE / INTERSECT) entre le solide fermé obj et cutter, vérifié : le résultat doit être un
    solide fermé au volume cohérent. Retourne un maillage (à libérer par l'appelant), ou None si aucun solveur n'y arrive.
    Manifold (Blender 4.5+) : rapide et sûr sur des solides fermés. Exact sans « auto-intersection » se trompe sur
    certains maillages denses (faces de l'outil dans le plan des murs) : on l'utilise avec, en secours."""
    size = max(max(obj.dimensions), 1e-6) / max(max(abs(sc) for sc in obj.scale), 1e-6)
    if eps is None:
        eps = max(1e-6, 1e-4 * size)
    chk = bmesh.new()
    try:
        chk.from_mesh(obj.data)
        vol0 = abs(chk.calc_volume())
    finally:
        chk.free()
    tol = eps * size * size
    # Manifold refuse un outil non fermé (et laisse alors le solide tel quel, sans erreur) : on ne le tente que si l'outil l'est
    manifold_ok = 'MANIFOLD' in boolean_solvers() and mesh_is_closed(cutter.data)
    for solver, use_self in ([('MANIFOLD', False)] if manifold_ok else []) + [('EXACT', True)]:
        try:
            res = boolean_mesh(obj, [cutter], op, solver, use_self)
        except (RuntimeError, TypeError, ValueError):
            continue
        chk = bmesh.new()
        try:
            chk.from_mesh(res)
            closed = all(len(e.link_faces) == 2 for e in chk.edges)
            v1 = abs(chk.calc_volume()) if closed else 0.0
            empty = len(chk.faces) == 0
        finally:
            chk.free()
        if empty or (closed and (v1 >= vol0 - tol if op == 'UNION' else v1 <= vol0 + tol)):
            return res
        bpy.data.meshes.remove(res)
    return None


def write_solid(obj, res, eps):
    """Remplace la géométrie de obj par le maillage res (résultat d'un booléen), nettoyé et aux normales cohérentes."""
    bm = bmesh.new()
    try:
        bm.from_mesh(res)
        bmesh.ops.dissolve_degenerate(bm, dist=eps * 0.01, edges=bm.edges[:])
        bm.normal_update()
        if all(len(e.link_faces) == 2 for e in bm.edges):
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(obj.data)
        obj.data.update()
    finally:
        bm.free()


def _pp_prism(obj, faces, n_local, dist, eps):
    """Prisme fermé (espace local de obj) : la région `faces` décalée de eps vers l'extérieur du sens de la poussée,
    puis extrudée de `dist` le long de n_local. Sert d'outil booléen à PushPull."""
    bm = bmesh.new()
    mat, smooth = faces[0].material_index, faces[0].smooth
    # bouchons reconstruits d'après le seul contour de la région (trous compris) : un prisme léger même si la face est
    # faite de milliers de facettes (le booléen exact est bien plus rapide)
    rings = _boundary_rings(pp_boundary(faces))
    made = False
    if rings:
        o, u, w, _n = _region_frame(faces)
        flat = [[Vector(((v.co - o).dot(u), (v.co - o).dot(w), 0.0)) for v in r] for r in rings]
        allv = [bm.verts.new(v.co) for r in rings for v in r]
        try:
            if len(rings) == 1:
                # un seul contour : un bouchon d'un seul tenant (la face créée par la coupe reste une seule face)
                g = bm.faces.new(allv)
                g.material_index, g.smooth = mat, smooth
                made = True
            for t in ([] if made else geometry.tessellate_polygon(flat)):
                g = bm.faces.new([allv[t[0]], allv[t[1]], allv[t[2]]])
                g.material_index, g.smooth = mat, smooth
                made = True
        except ValueError:
            made = False
    if not made:
        bm.clear()
        vmap = {}
        for f in faces:
            for v in f.verts:
                if v not in vmap:
                    vmap[v] = bm.verts.new(v.co)
        for f in faces:
            try:
                g = bm.faces.new([vmap[v] for v in f.verts])
                g.material_index, g.smooth = mat, smooth
            except ValueError:
                pass
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-9)
    sgn = 1.0 if dist < 0 else -1.0                   # poussée : le prisme dépasse un peu au-dessus de la face (côté vide)
    bmesh.ops.translate(bm, vec=n_local * (sgn * eps), verts=list(bm.verts))
    ret = bmesh.ops.extrude_face_region(bm, geom=list(bm.faces))
    moved = [g for g in ret["geom"] if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=n_local * (dist - sgn * eps), verts=moved)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new("pp_cutter")
    bm.to_mesh(me)
    bm.free()
    for mt in obj.data.materials:
        me.materials.append(mt)
    cutter = bpy.data.objects.new("pp_cutter", me)
    cutter.matrix_world = obj.matrix_world.copy()
    _link_like(cutter, obj)
    return cutter


def push_pull_mesh(obj, face_index, dist):
    """Tire (dist > 0) ou pousse (dist < 0) la face visée de `dist` (unités de la scène) le long de sa normale.
    Un solide reste un solide ; une surface seule devient un volume fermé. Comme PushPull de Rhino : une face poussée
    au-delà de la face opposée perce le solide (différence booléenne), une face tirée dans une autre partie du solide
    s'y unit. Retourne un message d'erreur ou ''."""
    me = obj.data
    if face_index < 0 or face_index >= len(me.polygons):
        return "Face not found"
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        bm.faces.ensure_lookup_table()
        bm.normal_update()
        f0 = bm.faces[face_index]
        curved = pp_curved_region(bm, f0)
        if curved is not None:
            return _push_pull_curved(obj, bm, curved, dist)
        faces = pp_region(bm, f0)
        bound = pp_boundary(faces)
        open_surface = bool(bound) and all(len(e.link_faces) == 1 for e in bound)
        closed_solid = not open_surface and all(len(e.link_faces) == 2 for e in bm.edges)
        nw = (obj.matrix_world.to_3x3() @ f0.normal).normalized()
        vec = obj.matrix_world.to_3x3().inverted() @ (nw * dist)
        size = max(max(obj.dimensions), 1e-6) / max(max(abs(sc) for sc in obj.scale), 1e-6)
        eps = max(1e-6, 1e-4 * size)
        if closed_solid and _pp_needs_boolean(bm, faces, vec, eps * 0.1):
            # la face déplacée rencontrerait le reste du solide : un booléen exact (prisme balayé par la région)
            n_loc = (obj.matrix_world.to_3x3().inverted() @ nw)
            scale_n = n_loc.length
            cutter = _pp_prism(obj, faces, n_loc.normalized(), dist * scale_n, eps)
            op = 'DIFFERENCE' if dist < 0 else 'UNION'
            try:
                good = solid_boolean(obj, cutter, op, eps)
            finally:
                cme = cutter.data
                bpy.data.objects.remove(cutter)
                if cme.users == 0:
                    bpy.data.meshes.remove(cme)
            if good is None:
                return "the cut could not be computed on this mesh (the solid is unchanged)"
            try:
                if len(good.polygons) == 0:
                    return "the push removes the whole solid"
                bm.clear()
                bm.from_mesh(good)
            finally:
                bpy.data.meshes.remove(good)
            bmesh.ops.dissolve_degenerate(bm, dist=eps * 0.01, edges=bm.edges[:])
            bm.normal_update()
            if all(len(e.link_faces) == 2 for e in bm.edges):
                bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
            bm.to_mesh(me)
            me.update()
            return ""
        ret = bmesh.ops.extrude_face_region(bm, geom=faces)
        verts = [g for g in ret["geom"] if isinstance(g, bmesh.types.BMVert)]
        bmesh.ops.translate(bm, vec=vec, verts=verts)
        if not open_surface:
            bmesh.ops.delete(bm, geom=faces, context='FACES')           # la face d'origine disparaît (avec ses diagonales) : le solide reste fermé
        bm.normal_update()
        if all(len(e.link_faces) == 2 for e in bm.edges):
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()
    return ""


def _region_frame(faces):
    f0 = faces[0]
    n = f0.normal.copy()
    v0 = f0.verts[0].co.copy()
    e = f0.verts[1].co - v0
    u = (e - n * e.dot(n)).normalized()
    return v0, u, n.cross(u), n


def _boundary_rings(bnd_edges):
    """Boucles ordonnées (listes de BMVert) formées par les arêtes de pourtour d'un groupe de faces."""
    adj = {}
    for e in bnd_edges:
        a, b = e.verts
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    rings, seen = [], set()
    for start in adj:
        if start in seen:
            continue
        ring = [start]
        seen.add(start)
        prev, cur = None, start
        while True:
            nxt = [w for w in adj[cur] if w is not prev and (w not in seen or (w is start and len(ring) > 2))]
            if not nxt:
                break
            w = nxt[0]
            if w is start:
                break
            ring.append(w)
            seen.add(w)
            prev, cur = cur, w
        if len(ring) >= 3:
            rings.append(ring)
    return rings


def pp_curve_loops(context, obj, face_index):
    """Courbes fermées posées sur la face visée (même plan, à l'intérieur de son contour) : [(points monde)].
    Comme PushPull dans Rhino : une courbe dessinée sur une face la découpe, sans passer par une surface."""
    me = obj.data
    if face_index < 0 or face_index >= len(me.polygons):
        return []
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        bm.faces.ensure_lookup_table()
        bm.normal_update()
        faces = pp_region(bm, bm.faces[face_index])
        o, u, w, n = _region_frame(faces)
        mw = obj.matrix_world
        rings = _boundary_rings(pp_boundary(faces))
        if not rings:
            return []
        polys = [[((v.co - o).dot(u), (v.co - o).dot(w)) for v in r] for r in rings]
        outer = max(polys, key=lambda P: _poly_area2(P))
        size = max(max(obj.dimensions), 1e-6)
        tol = 1e-4 * max(1.0, size)
        # pourtour existant de la région (pour ignorer une courbe posée exactement dessus : la courbe laissée par Offset Edge
        # suit la découpe déjà faite, la redécouper créerait des sommets en double)
        A = np.array([a for P in polys for a in P], dtype=np.float64)
        B = np.array([b for P in polys for b in (P[1:] + P[:1])], dtype=np.float64)

        def on_boundary(Q2):
            q = np.asarray(Q2, dtype=np.float64)[:, None, :]
            ab = (B - A)[None, :, :]
            ln = (ab ** 2).sum(-1)
            t = np.clip(((q - A[None]) * ab).sum(-1) / np.where(ln > 0, ln, 1.0), 0.0, 1.0)
            d = np.sqrt((((A[None] + ab * t[..., None]) - q) ** 2).sum(-1)).min(axis=1)
            return bool((d <= tol * 10).all())
        inv = mw.inverted()
        dg = context.evaluated_depsgraph_get()
        out = []
        for c in context.visible_objects:
            if c is obj or not (c.type == 'CURVE' or (c.type == 'MESH' and not len(c.data.polygons))):
                continue
            if "dessin_cotation" in c.keys() or "dessin_cotation_texte" in c.keys():
                continue
            for P, closed in object_paths(c, dg):
                if not closed or len(P) < 3:
                    continue
                L = [inv @ Vector(p) for p in P]
                if any(abs((q - o).dot(n)) > tol for q in L):
                    continue
                Q2 = [((q - o).dot(u), (q - o).dot(w)) for q in L]
                if on_boundary(Q2):
                    continue
                if all(_point_in_poly(q, outer) for q in Q2):
                    out.append([tuple(p) for p in P])
        return out
    finally:
        bm.free()


def _ring_edge(rings, e):
    """Vrai si l'arête e relie deux sommets consécutifs d'un contour (arête du pourtour, à garder)."""
    a, b = e.verts
    for r in rings:
        n = len(r)
        for i in range(n):
            if (r[i] is a and r[(i + 1) % n] is b) or (r[i] is b and r[(i + 1) % n] is a):
                return True
    return False


def imprint_loops(obj, face_index, loops_world):
    """Découpe la face visée (et ses faces coplanaires) par des courbes fermées posées dessus : chaque zone devient une
    région à part (arêtes marquées), que PushPull peut tirer ou pousser seule. Retourne True si c'est fait."""
    me = obj.data
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        bm.faces.ensure_lookup_table()
        bm.normal_update()
        faces = pp_region(bm, bm.faces[face_index])
        o, u, w, n = _region_frame(faces)
        rings = _boundary_rings(pp_boundary(faces))
        inv = obj.matrix_world.inverted()
        new_loops = [[inv @ Vector(p) for p in L] for L in loops_world]
        if not rings or not new_loops:
            return False
        mat, smooth = faces[0].material_index, faces[0].smooth
        inner_edges = {e for f in faces for e in f.edges}
        inner_verts = {v for f in faces for v in f.verts}
        bmesh.ops.delete(bm, geom=faces, context='FACES_ONLY')
        # face faite de plusieurs facettes (triangulée, subdivisée) : ses arêtes et sommets intérieurs restaient orphelins
        # (le solide n'était plus fermé) ; seul le contour est gardé
        ring_verts = {v for r in rings for v in r}
        loose = [e for e in inner_edges if e.is_valid and not e.link_faces
                 and not (e.verts[0] in ring_verts and e.verts[1] in ring_verts and _ring_edge(rings, e))]
        if loose:
            bmesh.ops.delete(bm, geom=loose, context='EDGES')
        lone = [v for v in inner_verts if v.is_valid and not v.link_edges and v not in ring_verts]
        if lone:
            bmesh.ops.delete(bm, geom=lone, context='VERTS')
        vert_rings = [list(r) for r in rings] + [[bm.verts.new(q) for q in L] for L in new_loops]
        flat = [[((v.co - o).dot(u), (v.co - o).dot(w)) for v in r] for r in vert_rings]
        m_ = len(flat)
        areas = [_poly_area2(P) for P in flat]
        parent, depth = [], []
        for i in range(m_):
            cont = [j for j in range(m_) if j != i and areas[j] > areas[i] and _pip_np(flat[i][0], flat[j])]
            depth.append(len(cont))
            parent.append(min(cont, key=lambda j: areas[j]) if cont else None)
        made = []
        outer_i = max(range(len(rings)), key=lambda k: areas[k])
        existing_holes = {k for k in range(len(rings)) if k != outer_i}
        for i in range(m_):
            if i in existing_holes:
                continue                     # trou d'origine de la face : il reste vide
            holes = [j for j in range(m_) if parent[j] == i]
            if not holes:
                try:
                    made.append(bm.faces.new(vert_rings[i]))
                except ValueError:
                    pass
                continue
            idx_rings = [i] + holes
            polys = [[Vector((x, y, 0.0)) for x, y in flat[k]] for k in idx_rings]
            tris = geometry.tessellate_polygon(polys)
            allv = [v for k in idx_rings for v in vert_rings[k]]
            for t in tris:
                try:
                    made.append(bm.faces.new([allv[t[0]], allv[t[1]], allv[t[2]]]))
                except ValueError:
                    pass
        lay = bm.edges.layers.int.get(IMPRINT_LAYER) or bm.edges.layers.int.new(IMPRINT_LAYER)
        for r in vert_rings[len(rings):]:
            for a, b in zip(r, r[1:] + r[:1]):
                e = bm.edges.get((a, b))
                if e is not None:
                    e[lay] = 1
        bm.normal_update()
        for f in made:
            f.material_index, f.smooth = mat, smooth
            if f.normal.dot(n) < 0:
                f.normal_flip()
        bm.to_mesh(me)
        me.update()
        return bool(made)
    except (ValueError, IndexError, ReferenceError):
        return False
    finally:
        bm.free()


def pp_draw_cb(op):
    if not _same_region(op) or not op.lines:
        return
    shader = get_shader('3D')
    gpu.state.blend_set('ALPHA')
    gpu.state.line_width_set(2.0)
    shader.bind()
    shader.uniform_float("color", (BOX_ORANGE[0], BOX_ORANGE[1], BOX_ORANGE[2], 1.0) if op.stage == 'DIST'
                         else (BOX_BLUE[0], BOX_BLUE[1], BOX_BLUE[2], 1.0))
    batch_for_shader(shader, 'LINES', {"pos": [tuple(p) for p in op.lines]}).draw(shader)
    gpu.state.line_width_set(1.0)
    gpu.state.blend_set('NONE')


def pp_draw_px_cb(op):
    """Repère d'accrochage de PushPull (la hauteur est prise sur ce point)."""
    if not _same_region(op) or getattr(op, "snap_screen", None) is None:
        return
    draw_snap_marker(op.snap_screen[0], op.snap_screen[1], op.snap_kind)


class DESSIN_OT_pushpull(bpy.types.Operator):
    bl_idname = "dessin.pushpull"
    bl_label = "PushPull"
    bl_description = ("Pulls or pushes a face of a solid or a surface along its normal: click the face, then move the mouse "
                      "(or type a distance) and click / Enter. A negative distance pushes the face into the solid. "
                      "Closed curves drawn on a face split it first (inside zone / outer ring), and a zone closed by curves "
                      "alone can be pulled directly, without making a surface first")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D' and context.mode == 'OBJECT'

    def prompt(self):
        if self.stage == 'PICK':
            set_prompt(self.area, "PushPull: click the face to pull or push  |  Esc: cancel")
        else:
            t = f"  typed: {self.typed}" if self.typed else ""
            lv = None if self.typed else last_typed((self.bl_idname, 'DIST'))
            ent = "click / Enter to confirm" if lv is None else f"click to confirm, Enter: {lv.lstrip('-')} (last value)"
            set_prompt(self.area, f"PushPull: distance {self.fmt(self.dist)}{t}  |  move the mouse or type a value, {ent}, Esc to cancel")

    def fmt(self, value):
        x = value / (self.unit_f or 1.0)
        s = f"{x:.3f}".rstrip('0').rstrip('.')
        return (f"{s} {self.unit_label}").strip()

    def invoke(self, context, event):
        self.area = context.area
        self.region = find_window_region(self.area, event.mouse_x, event.mouse_y) or main_window_region(self.area)
        if self.region is None:
            return {'CANCELLED'}
        self.rv3d = region_rv3d(self.region, self.area)
        self.unit_f, self.unit_label = unit_info(context.scene)
        self.stage = 'PICK'
        self.lines = []
        self.target = None            # (objet, indice de face, régions de faces, normale monde, point de départ)
        self._backup = None
        self._temp_obj = None
        self._groups = None
        self._loops_cache = None
        self.hover_key = None
        self.dist = 0.0
        self.typed = ""
        self.snap_screen = None
        self.snap_kind = None
        self._snapd = None
        self._h = bpy.types.SpaceView3D.draw_handler_add(pp_draw_cb, (self,), 'WINDOW', 'POST_VIEW')
        self._hpx = bpy.types.SpaceView3D.draw_handler_add(pp_draw_px_cb, (self,), 'WINDOW', 'POST_PIXEL')
        self.prompt()
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def cleanup(self):
        if getattr(self, "_h", None) is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._h, 'WINDOW')
            self._h = None
        if getattr(self, "_hpx", None) is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._hpx, 'WINDOW')
            self._hpx = None
        self.snap_screen = None
        self._snapd = None
        set_prompt(self.area, None)
        try:
            self.area.tag_redraw()
        except ReferenceError:
            pass

    def hit_face(self, context, region, mx, my):
        coord = Vector((mx, my))
        ro = region_2d_to_origin_3d(region, self.rv3d, coord)
        rv = region_2d_to_vector_3d(region, self.rv3d, coord)
        try:
            dg = context.evaluated_depsgraph_get()
            ok, loc, _nor, idx, obj, _m = ray_cast_opaque(context, ro, rv, True)
        except (RuntimeError, TypeError, ValueError):
            return None
        if not ok or obj is None or obj.type != 'MESH':
            return None
        try:
            if len(obj.evaluated_get(dg).data.polygons) != len(obj.data.polygons):
                return ("modifiers", obj)             # un modificateur change les faces : l'indice ne correspond plus
        except (RuntimeError, ReferenceError):
            return None
        return (obj, idx, loc)

    def curve_loops(self, context, obj, idx):
        key = (obj.name, idx)
        cache = getattr(self, "_loops_cache", None)
        if cache is None or cache[0] != key:
            try:
                loops = pp_curve_loops(context, obj, idx)
            except (RuntimeError, ReferenceError, ValueError):
                loops = []
            self._loops_cache = (key, loops)
        return self._loops_cache[1]

    def hover_lines(self, context, obj, idx, loc):
        """Surbrillance : la zone fermée par une courbe sous le curseur, sinon la face (et les courbes posées dessus)."""
        segs, nw = self.region_lines(obj, idx)
        loops = self.curve_loops(context, obj, idx) if not getattr(self, "_curved", None) else []
        if not loops:
            return segs
        o = Vector(loops[0][0])
        u = (Vector(loops[0][1]) - o)
        u = (u - nw * u.dot(nw)).normalized()
        w = nw.cross(u)
        p2 = ((Vector(loc) - o).dot(u), (Vector(loc) - o).dot(w))
        inside = [L for L in loops if _pip_np(p2, [((Vector(q) - o).dot(u), (Vector(q) - o).dot(w)) for q in L])]
        lines = []
        pick = [min(inside, key=lambda L: _poly_area2([((Vector(q) - o).dot(u), (Vector(q) - o).dot(w)) for q in L]))] if inside else loops
        for L in pick:
            for a, b in zip(L, L[1:] + L[:1]):
                lines += [Vector(a), Vector(b)]
        return lines if inside else segs + lines

    def face_at(self, obj, loc):
        from mathutils.bvhtree import BVHTree
        me = obj.data
        tree = BVHTree.FromPolygons([tuple(v.co) for v in me.vertices], [tuple(p.vertices) for p in me.polygons])
        _co, _n, idx, _d = tree.find_nearest(obj.matrix_world.inverted() @ Vector(loc))
        return idx

    def region_lines(self, obj, idx):
        """Contour (en monde) de la face visée, pour la surbrillance, et sa normale monde.
        Le résultat est gardé pour toutes les facettes de la même face : survoler un cylindre dense ne recalcule rien."""
        me = obj.data
        key = (obj.name, me.as_pointer(), len(me.polygons), len(me.vertices), tuple(obj.matrix_world.col[3]))
        cache = getattr(self, "_rl", None)
        if cache is None or cache[0] != key:
            cache = self._rl = (key, {})
        mw = obj.matrix_world
        nw = (mw.to_3x3() @ me.polygons[idx].normal).normalized()
        hit = cache[1].get(idx)
        if hit is not None:
            self._curved = hit[1]
            return hit[0], nw
        bm = bmesh.new()
        try:
            bm.from_mesh(me)
            bm.faces.ensure_lookup_table()
            bm.normal_update()
            f0 = bm.faces[idx]
            self._curved = None
            segs = []
            faces = pp_curved_region(bm, f0)
            if faces is not None:
                # face courbe : son pourtour (ou son maillage, si elle n'en a pas : sphère) et de quoi dessiner son décalage
                normals = _pp_region_normals(obj, faces)
                bnd = pp_boundary(faces)
                bset = set(bnd)
                inner = [e for e in {e for f in faces for e in f.edges} if e not in bset]
                room = max(0, PP_PREVIEW_EDGES - len(bnd))
                if len(inner) > room:
                    inner = inner[::max(1, len(inner) // max(room, 1))][:room]
                cv = []
                for e in bnd + inner:
                    a, b = e.verts
                    if normals.get(a) is None or normals.get(b) is None:
                        continue
                    pa, pb = mw @ a.co, mw @ b.co
                    cv.append((pa, normals[a], pb, normals[b]))
                    if e in bset or not bnd:
                        segs += [pa, pb]
                self._curved = cv
            else:
                faces = pp_region(bm, f0)
                for e in pp_boundary(faces):
                    segs += [mw @ e.verts[0].co, mw @ e.verts[1].co]
            for f in faces:
                cache[1][f.index] = (segs, self._curved)
            return segs, nw
        finally:
            bm.free()

    def curve_region(self, context, region, mx, my):
        if getattr(self, "_groups", None) is None:
            objs = [o for o in context.visible_objects if o.type == 'CURVE' or (o.type == 'MESH' and not len(o.data.polygons))]
            try:
                self._groups, _sk = hatch_loop_groups(_hatch_paths_of(context, objs))
            except (ValueError, RuntimeError, ReferenceError):
                self._groups = []
        if not self._groups:
            return None
        coord = Vector((mx, my))
        ro = region_2d_to_origin_3d(region, self.rv3d, coord)
        rv = region_2d_to_vector_3d(region, self.rv3d, coord)
        return hatch_region_at(self._groups, np.array(ro), np.array(rv))

    def undo_prep(self):
        """Annulation : la face redécoupée retrouve sa forme, la surface provisoire disparaît."""
        b = getattr(self, "_backup", None)
        if b:
            obj, me = bpy.data.objects.get(b[0]), bpy.data.meshes.get(b[1])
            if obj is not None and me is not None:
                old = obj.data
                obj.data = me
                if old.users == 0:
                    bpy.data.meshes.remove(old)
            self._backup = None
        t = getattr(self, "_temp_obj", None)
        if t and bpy.data.objects.get(t) is not None:
            o = bpy.data.objects[t]
            me = o.data
            bpy.data.objects.remove(o)
            if me.users == 0:
                bpy.data.meshes.remove(me)
        self._temp_obj = None

    def snap_dist(self, context, region, mx, my):
        """Hauteur prise sur un point accroché (End, Mid, Cen, Int...) : sa distance au plan de la face, le long de sa
        normale, comme la distance d'extrusion accrochée de Rhino. None si rien n'est accroché."""
        self.snap_screen = None
        self.snap_kind = None
        if osnap("disable"):
            return None
        try:
            if self._snapd is None:
                context.view_layer.update()       # la face vient peut-être d'être découpée : l'accrochage la voit à jour
                self._snapd = collect_snap_points(context, None)
            hit = find_snap_in(self._snapd, mx, my, region, self.rv3d)
        except (RuntimeError, ReferenceError, AttributeError, ValueError, TypeError):
            return None
        if hit is None:
            return None
        _obj, _idx, _segs, nw, p0 = self.target
        self.snap_screen = (float(hit[1][0]), float(hit[1][1]))
        self.snap_kind = hit[2]
        return (Vector(hit[0]) - p0).dot(nw)

    def update_dist(self, context, region, mx, my):
        obj, idx, segs, nw, p0 = self.target
        s = self.snap_dist(context, region, mx, my)
        if s is not None:
            self.dist = s
            return
        coord = Vector((mx, my))
        ro = region_2d_to_origin_3d(region, self.rv3d, coord)
        rv = region_2d_to_vector_3d(region, self.rv3d, coord)
        h = view_height(p0, p0, nw, ro, rv, self.rv3d)     # face vue de face (dessus en vue Top) : distance du curseur
        if h is not None:
            self.dist = h

    def refresh_preview(self):
        obj, idx, segs, nw, p0 = self.target
        cv = getattr(self, "_curved", None)
        if cv:
            d = self.dist
            lines = list(segs)
            for pa, na, pb, nb in cv:           # face courbe : chaque sommet suit sa normale
                lines += [pa + na * d, pb + nb * d]
            self.lines = lines
            return
        off = nw * self.dist
        lines = list(segs) + [p + off for p in segs]
        for i in range(0, len(segs), 2):
            lines += [segs[i], segs[i] + off, segs[i + 1], segs[i + 1] + off]
        self.lines = lines

    def finish(self, context):
        obj, idx, _segs, _nw, _p0 = self.target
        d = self.dist
        t = None
        if self.typed not in ("", "-", ".", "-."):
            try:
                t = float(self.typed) * self.unit_f
            except ValueError:
                t = None
        if t is not None:
            d = t if (t < 0 or d >= 0) else -t         # une valeur saisie garde le sens de la souris, sauf si on tape un signe
        self.cleanup()
        if abs(d) < 1e-9:
            self.undo_prep()
            return {'CANCELLED'}
        b = getattr(self, "_backup", None)
        if b and bpy.data.meshes.get(b[1]) is not None:
            bpy.data.meshes.remove(bpy.data.meshes[b[1]])      # la découpe est gardée : plus besoin de la copie
        self._backup = None
        self._temp_obj = None
        try:
            msg = push_pull_mesh(obj, idx, d)
        except (RuntimeError, ReferenceError, ValueError) as err:
            msg = str(err)
        if msg:
            self.report({'WARNING'}, "PushPull: " + msg)
            return {'CANCELLED'}
        cmd_log("PushPull: " + self.fmt(d))
        return {'FINISHED'}

    def modal(self, context, event):
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self.undo_prep()
            self.cleanup()
            return {'CANCELLED'}
        if event.type in NAV_TYPES or event.type.startswith('TRACKPAD'):
            return {'PASS_THROUGH'}
        region = find_window_region(self.area, event.mouse_x, event.mouse_y)
        if self.stage == 'DIST' and event.value == 'PRESS':
            if event.type in {'RET', 'NUMPAD_ENTER', 'SPACE'}:
                if self.typed in ("", "-", ".", "-."):
                    lv = last_typed((self.bl_idname, 'DIST'))
                    if lv is not None:
                        self.typed = lv          # Entrée sans saisie : dernière distance tapée, dans le sens de la souris
                else:
                    _LAST_TYPED[(self.bl_idname, 'DIST')] = self.typed
                return self.finish(context)
            if event.type == 'BACK_SPACE':
                self.typed = self.typed[:-1]
                self.prompt()
                return {'RUNNING_MODAL'}
            ch = event.unicode
            if ch and (ch.isdigit() or ch in '.-,'):
                self.typed += '.' if ch == ',' else ch
                self.prompt()
                return {'RUNNING_MODAL'}
        if region is None:
            return {'RUNNING_MODAL'}
        mx, my = event.mouse_x - region.x, event.mouse_y - region.y
        if event.type == 'MOUSEMOVE':
            if self.stage == 'PICK':
                h = self.hit_face(context, region, mx, my)
                key = (h[0].name, h[1]) if h and h[0] != "modifiers" and len(h) == 3 else None
                if key is not None:
                    self.hover_key = key
                    self.lines = self.hover_lines(context, h[0], h[1], h[2])
                    self.area.tag_redraw()
                elif h is None:
                    rg = self.curve_region(context, region, mx, my)
                    self.hover_key = None
                    self.lines = []
                    if rg is not None:
                        c, u, v, n, rings, _t = rg
                        for R in rings:
                            P = [Vector(c + p[0] * u + p[1] * v) for p in R]
                            for a, b in zip(P, P[1:] + P[:1]):
                                self.lines += [a, b]
                    self.area.tag_redraw()
            else:
                self.region = region
                self.update_dist(context, region, mx, my)
                self.refresh_preview()
                self.prompt()
                self.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            self.region = region
            if self.stage == 'PICK':
                h = self.hit_face(context, region, mx, my)
                if h is None:
                    # pas de face : zone fermée par des courbes sous le curseur -> surface plane créée, puis tirée
                    rg = self.curve_region(context, region, mx, my)
                    if rg is None:
                        cmd_log("PushPull: click on a face or inside closed curves")
                        return {'RUNNING_MODAL'}
                    c, u, v, n, rings, t = rg
                    built = planar_surfaces([(np.array([c + p[0] * u + p[1] * v for p in R]), True) for R in rings])[0]
                    if not built:
                        return {'RUNNING_MODAL'}
                    V, F = built[0]
                    V = np.asarray(V, dtype=np.float64)
                    tmp = mesh_object_from_arrays(context, "PushPull", V, F, Vector(V.mean(axis=0)), False)
                    for poly in tmp.data.polygons:
                        if Vector(poly.normal).dot(Vector(n)) < 0:
                            poly.flip()
                    tmp.data.update()
                    self._temp_obj = tmp.name
                    ro = region_2d_to_origin_3d(region, self.rv3d, Vector((mx, my)))
                    rv = region_2d_to_vector_3d(region, self.rv3d, Vector((mx, my)))
                    loc = ro + rv * float(t)
                    h = (tmp, self.face_at(tmp, loc), loc)
                if h[0] == "modifiers":
                    cmd_log("PushPull: apply the modifiers of this object first")
                    return {'RUNNING_MODAL'}
                obj, idx, loc = h
                self.region_lines(obj, idx)
                loops = (self.curve_loops(context, obj, idx)
                         if getattr(self, "_temp_obj", None) is None and not getattr(self, "_curved", None) else [])
                if loops:
                    # courbes posées sur la face : elles la découpent d'abord (zone intérieure / anneau extérieur)
                    self._backup = (obj.name, obj.data.copy().name)
                    if imprint_loops(obj, idx, loops):
                        idx = self.face_at(obj, loc)
                    else:
                        bpy.data.meshes.remove(bpy.data.meshes[self._backup[1]])
                        self._backup = None
                segs, nw = self.region_lines(obj, idx)
                self.target = (obj, idx, segs, nw, Vector(loc))
                self.stage = 'DIST'
                self.dist = 0.0
                self.typed = ""
                self.refresh_preview()
                self.prompt()
                self.area.tag_redraw()
                return {'RUNNING_MODAL'}
            return self.finish(context)
        return {'RUNNING_MODAL'}


# ---- Auto CPlane : le plan de construction suit la face / l'objet plan sélectionné (désactivé par défaut) ----
_AUTOCP = {"sig": {}}


def autocp_frame_object(obj):
    """Repère (origine, X, Y, Z) en monde d'un objet maillage entièrement plan, sinon None."""
    me = obj.data
    n = len(me.polygons)
    if n == 0 or n > 200000:
        return None
    nm = np.empty(n * 3, dtype=np.float64)
    me.polygons.foreach_get("normal", nm)
    nm = nm.reshape(-1, 3)
    n0 = nm[0]
    if np.any(nm @ n0 < 1.0 - 1e-5):
        return None
    mv = len(me.vertices)
    co = np.empty(mv * 3, dtype=np.float64)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    if float(np.ptp(co @ n0)) > 1e-4 * max(1.0, float(np.ptp(co, axis=0).max())):
        return None
    mw = obj.matrix_world
    z = (mw.to_3x3() @ Vector(n0)).normalized()
    c = mw @ Vector(co.mean(axis=0))
    return autocp_make_frame(c, z)


def autocp_make_frame(c, z):
    up = Vector((0.0, 0.0, 1.0))
    x = Vector((1.0, 0.0, 0.0)) if abs(z.dot(up)) > 0.999 else up.cross(z)    # face verticale : X horizontal
    return cp_frame(c, x, z.cross(x))


def autocp_frame_faces(obj):
    """Repère des faces sélectionnées (mode Édition) si elles sont toutes dans un même plan, sinon None."""
    bm = bmesh.from_edit_mesh(obj.data)
    faces = [f for f in bm.faces if f.select]
    if not faces:
        return None
    n0 = faces[0].normal
    d0 = n0.dot(faces[0].verts[0].co)
    for f in faces[1:]:
        if f.normal.dot(n0) < 1.0 - 1e-5 or abs(n0.dot(f.verts[0].co) - d0) > 1e-4 * max(1.0, abs(d0)):
            return None
    mw = obj.matrix_world
    c = sum((f.calc_center_median() for f in faces), Vector()) / len(faces)
    return autocp_make_frame(mw @ c, (mw.to_3x3() @ n0).normalized())


def autocp_hover(context, region, rv3d, mx, my):
    """Auto CPlane, option « face sous le curseur » : tant qu'un outil de dessin attend son premier point, le plan de
    construction se pose sur la face plane survolée (on dessine sur l'objet, pas derrière lui) ; dans le vide, il
    revient au plan d'avant."""
    try:
        st = context.scene.dessin
        if not (st.auto_cplane and st.auto_cplane_hover):
            return
    except AttributeError:
        return
    cs = cp_state(rv3d, create=True)
    coord = Vector((mx, my))
    try:
        ro = region_2d_to_origin_3d(region, rv3d, coord)
        rv = region_2d_to_vector_3d(region, rv3d, coord)
        ok, loc, nrm, _i, obj, _m = ray_cast_opaque(context, ro, rv, True)
    except (RuntimeError, TypeError, ValueError, ReferenceError):
        ok = False
    if ok and obj is not None and obj.type == 'MESH' and "dessin_hatch" not in obj.keys():
        z = Vector(nrm).normalized()
        if z.dot(rv) > 0:
            z = -z
        cur = cs.get("cur")
        if cs.get("hover") and cur is not None:
            o_, _x, _y, z0 = cur
            if Vector(z0).dot(z) > 1.0 - 1e-6 and abs(Vector(z0).dot(Vector(loc) - Vector(o_))) < 1e-6:
                return                                    # même plan : on ne touche à rien
        if not cs.get("hover"):
            cs["hover_prev"] = (cs.get("cur"), cs.get("auto", False))
        cp_set(rv3d, autocp_make_frame(Vector(loc), z), record=False, auto=True)
        cs["hover"] = True
        return
    if cs.get("hover"):
        prev, was_auto = cs.get("hover_prev", (None, False))
        cp_set(rv3d, prev, record=False, auto=was_auto)
        cs["hover"] = False


def autocp_apply(window, scene, mode):
    """Calcule le plan de la sélection courante et l'applique aux vues 3D de la fenêtre. Retourne True si quelque chose a changé."""
    st = scene.dessin
    frame = None
    try:
        ctx_view_layer = window.view_layer
        obj = ctx_view_layer.objects.active
        if mode == 'EDIT_MESH' and obj is not None and obj.type == 'MESH':
            frame = autocp_frame_faces(obj)
        elif mode == 'OBJECT':
            sel = [o for o in ctx_view_layer.objects if o.select_get()]
            if len(sel) == 1 and sel[0].type == 'MESH':
                frame = autocp_frame_object(sel[0])
    except (ReferenceError, RuntimeError, AttributeError, ValueError):
        frame = None
    changed = False
    for area in window.screen.areas:
        if area.type != 'VIEW_3D':
            continue
        rv3d = area.spaces.active.region_3d
        cs = cp_state(rv3d, create=True)
        if frame is not None:
            cp_set(rv3d, frame, auto=True)
            changed = True
        elif cs["cur"] is not None and cs.get("auto") and not st.auto_cplane_sticky:
            cp_set(rv3d, None, auto=True)           # sans « Sticky » : plus de face plane, on revient au plan du sol
            changed = True
        if changed:
            area.tag_redraw()
    return changed


def autocp_timer():
    """Surveille la sélection (peu coûteux : un tuple comparé) seulement quand le bouton Auto CPlane est actif."""
    try:
        for win in bpy.context.window_manager.windows:
            scene = win.scene
            if not scene.dessin.auto_cplane:
                _AUTOCP["sig"].pop(win.as_pointer(), None)
                continue
            vl = win.view_layer
            act = vl.objects.active
            mode = act.mode if act is not None else 'OBJECT'
            if mode == 'EDIT':
                mode = 'EDIT_MESH'
            if mode == 'EDIT_MESH' and act is not None and act.type == 'MESH':
                me = act.data
                sig = (mode, act.name, me.total_face_sel, me.total_vert_sel)
            elif mode == 'OBJECT':
                names = tuple(o.name for o in vl.objects if o.select_get())
                sig = (mode, names, act.name if act is not None else "", tuple(round(c, 5) for row in act.matrix_world for c in row) if act is not None and len(names) == 1 else None)
            else:
                continue
            key = win.as_pointer()
            if _AUTOCP["sig"].get(key) != sig:
                first = key not in _AUTOCP["sig"]
                _AUTOCP["sig"][key] = sig
                if not first:                       # le premier relevé ne change pas le plan : seul un changement de sélection le fait
                    autocp_apply(win, scene, mode)
    except (ReferenceError, RuntimeError, AttributeError, ValueError):
        pass
    return 0.3


def _late_imports():
    pass
