"""Wanderer CAD : Gumball : poignées d'extrusion et de coupe, affichage."""

import bmesh
import bpy
import gpu
import math
import numpy as np
import time
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector

from .core import AXES3, TAU, oneshot_shown, osnap_shown, pref, tr_text
from .drawing import get_shader, project_px, px_scale
from .subd import expand_groups
from .gumball import (
    DESSIN_OT_gumball, GUMBALL_AXES, GUMBALL_COLORS, GUMBALL_PX, GumballBase, extrude_direction, extrude_info,
    gumball_axes, gumball_k, gumball_selection, gumball_selection_cached,
)
from .surfaces import (
    chain_open_paths, deselect_all_objects, extrude_general, extrude_surface, mesh_object_from_arrays, nest_groups,
    outline_paths,
)
from .lights import _GUMBALL_TOOLS, _axis_matrix, _gz_set, gumball_flat_axes


# ---------------- Gumball : poignées Extrude (sphère) et Cut (petit trait), comme le Gumball de Rhino 8 ----------------
GB_DOT_POS = 0.50      # position de la sphère d'extrusion le long de la flèche (fraction de sa longueur)
GB_BAR_POS = 0.34      # position du trait de coupe
GB_DOT_R = 5.5         # rayon de la sphère (pixels d'interface) : assez grosse pour être attrapée, sans masquer la flèche
GB_BAR_L = 7.5         # demi-longueur du trait (pixels d'interface)
GB_PULL_NONE = {"ext": frozenset(), "cut": frozenset()}
_GB_PULL = {"t": 0.0, "sig": None, "res": GB_PULL_NONE}


def _gb_sphere_tris(n=10):
    P = lambda a, b: (math.sin(a) * math.cos(b), math.sin(a) * math.sin(b), math.cos(a))
    out = []
    for i in range(n):
        a0, a1 = math.pi * i / n, math.pi * (i + 1) / n
        for j in range(2 * n):
            b0, b1 = math.pi * j / n, math.pi * (j + 1) / n
            out += [P(a0, b0), P(a1, b0), P(a1, b1), P(a0, b0), P(a1, b1), P(a0, b1)]
    return out


def _gb_box_tris(x, y, z):
    c = [(sx * x, sy * y, sz * z) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    quads = ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3))
    out = []
    for q in quads:
        out += [c[q[0]], c[q[1]], c[q[2]], c[q[0]], c[q[2]], c[q[3]]]
    return out


GB_DOT_TRIS = _gb_sphere_tris()
GB_BAR_TRIS = _gb_box_tris(1.0, 0.2, 0.2)


class DESSIN_GT_gb_dot(bpy.types.Gizmo):
    """Sphère d'extrusion du Gumball (une vraie poignée : Blender la surligne et la détecte lui-même)."""
    bl_idname = "DESSIN_GT_gb_dot"
    __slots__ = ("shape",)

    def setup(self):
        if not hasattr(self, "shape"):
            self.shape = self.new_custom_shape('TRIS', GB_DOT_TRIS)

    def draw(self, context):
        self.draw_custom_shape(self.shape)

    def draw_select(self, context, select_id):
        self.draw_custom_shape(self.shape, select_id=select_id)


class DESSIN_GT_gb_bar(bpy.types.Gizmo):
    """Trait de coupe du Gumball (tirer / pousser de la matière)."""
    bl_idname = "DESSIN_GT_gb_bar"
    __slots__ = ("shape",)

    def setup(self):
        if not hasattr(self, "shape"):
            self.shape = self.new_custom_shape('TRIS', GB_BAR_TRIS)

    def draw(self, context):
        self.draw_custom_shape(self.shape)

    def draw_select(self, context, select_id):
        self.draw_custom_shape(self.shape, select_id=select_id)


def path_shape(P):
    """('line', direction) | ('planar', normale) | ('free', None) pour un contour (points monde)."""
    Q = np.array([tuple(p) for p in P], dtype=np.float64)
    if len(Q) < 2:
        return 'free', None
    c = Q.mean(axis=0)
    tol = 1e-6 * max(1.0, float(np.ptp(Q, axis=0).max())) + 2e-7 * float(np.abs(Q).max())
    if len(Q) == 2:
        d = Vector(tuple(Q[1] - Q[0]))
        return ('line', d.normalized()) if d.length > tol else ('free', None)
    _u, _s, vh = np.linalg.svd(Q - c, full_matrices=False)
    if np.abs((Q - c) @ vh[1]).max() <= tol:
        return 'line', Vector(tuple(vh[0])).normalized()
    if len(vh) >= 3 and np.abs((Q - c) @ vh[2]).max() <= tol:
        return 'planar', Vector(tuple(vh[2])).normalized()
    return 'free', None


def mesh_is_closed(me):
    """Vrai si chaque arête du maillage porte exactement deux faces (solide fermé)."""
    ne, nl = len(me.edges), len(me.loops)
    if not ne or not nl:
        return False
    ei = np.empty(nl, dtype=np.int32)
    me.loops.foreach_get("edge_index", ei)
    return bool((np.bincount(ei, minlength=ne) == 2).all())


def edit_planar_face(context):
    """(objet, indice de face, normale monde) si les faces sélectionnées en mode Édition forment une face plane entière
    d'un seul objet (ce que PushPull appelle une région) ; sinon None."""
    objs = [o for o in context.objects_in_mode_unique_data if o.type == 'MESH' and o.data.total_face_sel > 0]
    if len(objs) != 1 or objs[0].modifiers:
        return None
    o = objs[0]
    bm = bmesh.from_edit_mesh(o.data)
    bm.faces.index_update()
    bm.faces.ensure_lookup_table()
    sel = [f for f in bm.faces if f.select]
    if not sel:
        return None
    region = pp_region(bm, sel[0])
    if len(region) != len(sel) or any(not f.select for f in region):
        return None
    nw = (o.matrix_world.to_3x3().inverted_safe().transposed() @ sel[0].normal).normalized()
    return o, sel[0].index, nw


def gumball_pull_info(context, axes, fresh=False):
    """Axes du Gumball (indices) où la sphère d'extrusion (« ext ») et le trait de coupe (« cut ») s'affichent.
    - courbe plane : pas de sphère dans les directions de son plan (l'extrusion y serait plate) ; droite : pas le long d'elle
    - surface plane : comme une courbe plane ; solide entier : aucune poignée (on sélectionne une de ses faces)
    - trait de coupe : sur l'axe perpendiculaire à des courbes planes fermées, ou à la face plane sélectionnée."""
    sig = None
    try:
        now = time.monotonic()
        names = tuple(o.name for o in context.selected_objects) if context.mode == 'OBJECT' else \
            tuple((o.name, o.data.total_face_sel, o.data.total_edge_sel, o.data.total_vert_sel) for o in context.objects_in_mode_unique_data)
        sig = (context.mode, names, tuple(round(c, 4) for a in axes for c in a))
        # refait au plus toutes les 0,3 s, et bien moins souvent si le calcul est long (gros maillage) : l'affichage du
        # Gumball ne doit jamais ralentir la navigation
        if not fresh and sig == _GB_PULL["sig"] and now - _GB_PULL["t"] < max(0.3, 25.0 * _GB_PULL.get("cost", 0.0)):
            return _GB_PULL["res"]
        res = _gumball_pull_compute(context, axes)
    except (AttributeError, RuntimeError, ReferenceError, TypeError, ValueError, np.linalg.LinAlgError):
        res = GB_PULL_NONE
    t1 = time.monotonic()
    _GB_PULL.update(t=t1, sig=sig, res=res, cost=(t1 - now) if sig is not None else 0.0)
    return res


def _gumball_pull_compute(context, axes):
    if context.mode == 'EDIT_MESH':
        nf, ne = extrude_info(context)
        n = extrude_direction(context) if (nf or ne) else None
        if n is None:
            return GB_PULL_NONE
        a = max(range(3), key=lambda k: abs(axes[k].dot(n)))
        if abs(axes[a].dot(n)) < 0.5:
            return GB_PULL_NONE
        hit = edit_planar_face(context) if nf else None
        cut = frozenset({a}) if hit is not None and abs(axes[a].dot(hit[2])) > 0.966 else frozenset()
        return {"ext": frozenset({a}), "cut": cut}
    if context.mode != 'OBJECT':
        return GB_PULL_NONE
    sel = expand_groups(context, context.selected_objects)
    if not sel or len(sel) > 40:
        return GB_PULL_NONE
    dg = context.evaluated_depsgraph_get()
    shapes, curves_only, closed_all = [], True, True
    for o in sel:
        if o.type == 'MESH' and len(o.data.polygons):
            curves_only = False
            if len(o.data.polygons) > 50000 or mesh_is_closed(o.data):
                return GB_PULL_NONE                     # solide entier
            nor = np.empty(len(o.data.polygons) * 3, dtype=np.float32)
            o.data.polygons.foreach_get("normal", nor)
            nor = nor.reshape(-1, 3)
            if float((nor @ nor[0]).min()) < 1.0 - 1e-5:
                return GB_PULL_NONE                     # surface courbe : Extrude Surface
        elif o.type not in {'CURVE', 'MESH'}:
            return GB_PULL_NONE
        paths = outline_paths(o, dg)
        if not paths:
            return GB_PULL_NONE
        for P, c in paths:
            if len(P) > 4000:
                P = P[::len(P) // 4000 + 1]
            shapes.append(path_shape(P))
            closed_all = closed_all and bool(c)
    ext = set()
    for a in range(3):
        d = axes[a]
        if all(not ((k == 'planar' and abs(d.dot(v)) < 0.05) or (k == 'line' and abs(d.dot(v)) > 0.999)) for k, v in shapes):
            ext.add(a)
    cut = set()
    planar = [v for k, v in shapes if k == 'planar']
    if curves_only and closed_all and planar and len(planar) == len(shapes) and all(abs(planar[0].dot(v)) > 1.0 - 1e-6 for v in planar):
        a = max(range(3), key=lambda k: abs(axes[k].dot(planar[0])))
        if abs(axes[a].dot(planar[0])) > 0.966:
            cut.add(a)
    return {"ext": frozenset(ext), "cut": frozenset(cut)}


def split_closed_shells(me):
    """Sépare un maillage en (coques fermées, reste) : deux nouveaux maillages (mêmes matériaux), ou (None, None) s'il
    n'a aucune coque fermée. Une coque = des faces reliées par leurs arêtes ; fermée = chaque arête porte 2 faces."""
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        seen, closed, opened = set(), [], []
        for f0 in bm.faces:
            if f0 in seen:
                continue
            seen.add(f0)
            stack, shell, ok = [f0], [], True
            while stack:
                f = stack.pop()
                shell.append(f)
                for e in f.edges:
                    if len(e.link_faces) != 2:
                        ok = False
                    for g in e.link_faces:
                        if g not in seen:
                            seen.add(g)
                            stack.append(g)
            (closed if ok and len(shell) >= 4 else opened).append(shell)
        if not closed:
            return None, None
        out = []
        for drop in (opened, closed):
            b2 = bm.copy()
            try:
                b2.faces.ensure_lookup_table()
                kill = [b2.faces[f.index] for sh in drop for f in sh]
                if kill:
                    bmesh.ops.delete(b2, geom=kill, context='FACES')
                loose = [v for v in b2.verts if not v.link_faces]
                if loose:
                    bmesh.ops.delete(b2, geom=loose, context='VERTS')
                m2 = me.copy()
                b2.to_mesh(m2)
                m2.update()
                out.append(m2)
            finally:
                b2.free()
        return out[0], out[1]
    finally:
        bm.free()


def gumball_cut(context, selected, paths, vec, boss):
    """Trait de coupe du Gumball sur des courbes planes fermées : le prisme balayé par les courbes le long de vec est
    retiré des solides qu'il traverse (comme BooleanDifference) ; avec Ctrl (boss), ou quand les courbes sont posées sur
    une face et qu'on tire vers l'extérieur, il leur est ajouté (BooleanUnion). (message d'erreur ou '', nb coupés, nb ajoutés)"""
    from mathutils.bvhtree import BVHTree
    L = vec.length
    u = vec / L
    A = np.array([tuple(p) for P, _c in paths for p in P], dtype=np.float64)
    size = max(float(np.ptp(A, axis=0).max()), L, 1e-6)
    eps = max(1e-6, 1e-4 * size)
    pts = [np.asarray(P, dtype=np.float64) for P, _c in paths]
    flags = [c for _P, c in paths]

    def prism(shifted):
        """Prisme fermé balayé par les courbes. shifted : il part eps en arrière (courbe posée sur une face : jamais de
        face de l'outil dans le plan de cette face) ; sinon il part exactement du plan de la courbe (cotes exactes)."""
        sh = np.array(tuple(-u * eps), dtype=np.float64) if shifted else np.zeros(3)
        Vs, Fs = [], []
        for g in nest_groups([[(P + sh, c) for P, c in zip(pts, flags)]]):
            V, F = extrude_surface(g, u * (L + (eps if shifted else 0.0)), True)
            base = len(Vs)
            Vs += [tuple(p) for p in V]
            Fs += [tuple(i + base for i in f) for f in F]
        if not Fs:
            return None, 0.0
        me = bpy.data.meshes.new("gb_cutter")
        me.from_pydata(Vs, [], Fs)
        me.update()
        bmc = bmesh.new()
        try:
            bmc.from_mesh(me)
            bmesh.ops.remove_doubles(bmc, verts=list(bmc.verts), dist=eps * 1e-3)     # bouchons et parois soudés : un prisme fermé
            bmesh.ops.recalc_face_normals(bmc, faces=bmc.faces)
            vol = abs(bmc.calc_volume())
            bmc.to_mesh(me)
        finally:
            bmc.free()
        ob = bpy.data.objects.new("gb_cutter", me)
        context.scene.collection.objects.link(ob)
        return ob, vol

    exact, pvol = prism(False)
    if exact is None:
        return "the curves do not make a closed outline", 0, 0
    over, _v = prism(True)
    area = pvol / L
    lo, hi = np.minimum(A.min(axis=0), (A + np.array(tuple(vec))).min(axis=0)) - 10 * eps, \
        np.maximum(A.max(axis=0), (A + np.array(tuple(vec))).max(axis=0)) + 10 * eps
    sel = set(selected)
    ncut = nadd = nfail = nopen = 0
    open_name = ""
    parts = []
    try:
        for t in list(context.visible_objects):
            if t in sel or t is exact or t is over or t.type != 'MESH' or t.modifiers or not len(t.data.polygons):
                continue
            bb = np.array([tuple(t.matrix_world @ Vector(c)) for c in t.bound_box])
            if np.any(bb.max(axis=0) < lo) or np.any(bb.min(axis=0) > hi):
                continue
            target, rest = t, None
            if not mesh_is_closed(t.data):
                # une surface libre (face dupliquée, plan...) est rangée dans le même objet que le solide : on coupe
                # les parties fermées et on laisse le reste tel quel
                solid, rest = split_closed_shells(t.data)
                if solid is None:
                    nopen += 1
                    open_name = open_name or t.name
                    continue
                t = bpy.data.objects.new("gb_part", solid)
                t.matrix_world = target.matrix_world.copy()
                context.scene.collection.objects.link(t)
                parts.append((t, target, rest))
            inter = solid_boolean(t, exact, 'INTERSECT')
            real = False                                # le prisme entre-t-il vraiment dans la matière ?
            if inter is not None:
                bi = bmesh.new()
                try:
                    bi.from_mesh(inter)
                    bi.transform(t.matrix_world)
                    real = len(bi.faces) > 0 and abs(bi.calc_volume()) > 3.0 * area * eps
                finally:
                    bi.free()
                bpy.data.meshes.remove(inter)
            bt = bmesh.new()                            # les courbes sont-elles posées sur une face du solide ?
            try:
                bt.from_mesh(t.data)
                bt.transform(t.matrix_world)
                tree = BVHTree.FromBMesh(bt)
                step = max(1, len(A) // 64)
                on_face = all((tree.find_nearest(Vector(tuple(q)))[3] or 0.0) <= 10 * eps for q in A[::step])
            finally:
                bt.free()
            if boss:
                op, tool = ('UNION', exact) if real else (('UNION', over) if on_face else (None, None))
            elif real:
                op, tool = 'DIFFERENCE', (over if on_face else exact)
            else:
                op, tool = ('UNION', over) if on_face else (None, None)
            if op is None:
                continue
            res = solid_boolean(t, tool, op)
            if res is None:
                nfail += 1
                continue
            if len(res.polygons) == 0:
                bpy.data.meshes.remove(res)
                nfail += 1
                continue
            bv = bmesh.new()
            try:
                bv.from_mesh(t.data)
                v0 = abs(bv.calc_volume())
                bv.clear()
                bv.from_mesh(res)
                v1 = abs(bv.calc_volume())
            finally:
                bv.free()
            if abs(v1 - v0) <= 1e-7 * max(v0, 1e-12):       # rien n'a changé (prisme déjà dans la matière...) : on ne touche pas
                bpy.data.meshes.remove(res)
                continue
            write_solid(t, res, eps)
            bpy.data.meshes.remove(res)
            if rest is not None:                        # solide coupé + surfaces libres d'origine, dans l'objet d'origine
                bj = bmesh.new()
                try:
                    bj.from_mesh(t.data)
                    bj.from_mesh(rest)
                    bj.to_mesh(target.data)
                    target.data.update()
                finally:
                    bj.free()
            if op == 'UNION':
                nadd += 1
            else:
                ncut += 1
    finally:
        for ob in [exact, over] + [p[0] for p in parts]:
            if ob is not None:
                me = ob.data
                bpy.data.objects.remove(ob)
                if me.users == 0:
                    bpy.data.meshes.remove(me)
        for _p, _t, rest in parts:
            if rest is not None and rest.users == 0:
                bpy.data.meshes.remove(rest)
    if not (ncut or nadd):
        if nfail:
            return "the cut could not be computed on this solid (unchanged)", 0, 0
        if nopen:
            return f"'{open_name}' is an open surface, not a closed solid: nothing to cut (close it first, e.g. with Cap)", 0, 0
        return "nothing to cut: no solid on the path of the curve", 0, 0
    return "", ncut, nadd


class DESSIN_OT_gumball_pull(GumballBase):
    bl_idname = "dessin.gumball_pull"
    bl_label = "Gumball Extrude / Cut"
    bl_description = ("Gumball handles like Rhino. Sphere: extrudes the curve, the flat surface or the selected faces along "
                      "the arrow (Shift: both sides). Short line: pushes or pulls material, a closed flat curve cuts the "
                      "solids on its way (Ctrl/Cmd: adds instead), a selected flat face is pushed or pulled like PushPull. "
                      "Drag, or click then type the distance and press Enter")

    pull: bpy.props.EnumProperty(items=(('EXTRUDE', "Extrude", ""), ('CUT', "Cut", "")), default='EXTRUDE', options={'SKIP_SAVE'})
    axis: bpy.props.IntProperty(default=0, min=0, max=2, options={'SKIP_SAVE'})

    NO_COPY = True
    kind = 'MOVE'

    @classmethod
    def poll(cls, context):
        return context.mode in {'OBJECT', 'EDIT_MESH'} and context.area is not None and context.area.type == 'VIEW_3D'

    def setup_selection(self, context):
        pivot, top = gumball_selection(context)
        if not top:
            return False
        axes = gumball_axes(context)
        info = gumball_pull_info(context, axes, fresh=True)
        if self.axis not in info["ext" if self.pull == 'EXTRUDE' else "cut"]:
            return False
        self.pivot = pivot
        self.edit = False
        self.items = []
        self.dir = axes[self.axis].copy()
        self.lines = []
        self.stage = 'DIST'
        self.area, self.region = context.area, context.region
        self.ctrl = self.both = False
        if context.mode == 'EDIT_MESH':
            hit = edit_planar_face(context)
            if hit is None:
                return False
            obj, fidx, nw = hit
            bm = bmesh.from_edit_mesh(obj.data)
            bm.faces.ensure_lookup_table()
            rings = _boundary_rings(pp_boundary(pp_region(bm, bm.faces[fidx])))
            self.paths = [([obj.matrix_world @ v.co for v in r], True) for r in rings]
            self.job = ('face', obj.name, fidx, 1.0 if nw.dot(self.dir) >= 0 else -1.0, nw.copy())
        else:
            objs = expand_groups(context, context.selected_objects)
            dg = context.evaluated_depsgraph_get()
            self.paths = [(np.asarray(P, dtype=np.float64), bool(c)) for o in objs for P, c in outline_paths(o, dg)]
            self.job = ('obj', [o.name for o in objs])
        return bool(self.paths)

    def invoke(self, context, event):
        if context.mode == 'EDIT_MESH' and self.pull == 'EXTRUDE':
            try:                                        # faces / arêtes sélectionnées : l'extrusion du mode Édition
                bpy.ops.dessin.gumball_extrude('INVOKE_DEFAULT')
            except RuntimeError:
                pass
            return {'CANCELLED'}
        res = super().invoke(context, event)
        if 'RUNNING_MODAL' in res:
            self._h = bpy.types.SpaceView3D.draw_handler_add(pp_draw_cb, (self,), 'WINDOW', 'POST_VIEW')
        return res

    def modal(self, context, event):
        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE', 'LEFTMOUSE', 'LEFT_CTRL', 'RIGHT_CTRL', 'LEFT_SHIFT', 'RIGHT_SHIFT', 'OSKEY'}:
            self.ctrl = bool(event.ctrl or event.oskey)
            self.both = bool(event.shift)
        return super().modal(context, event)

    def _label(self):
        ax = GUMBALL_AXES[self.axis]
        v = self.value / self.unit_f
        if self.job[0] == 'face':
            return f"PushPull {ax}: {v:.3f} {self.unit_label}".strip()
        if self.pull == 'EXTRUDE':
            return f"Extrude {ax}: {v:.3f} {self.unit_label}".strip() + ("  (both sides)" if self.both else "  [Shift: both sides]")
        return f"Cut {ax}: {v:.3f} {self.unit_label}".strip() + ("  (add)" if self.ctrl else "  [Ctrl/Cmd: add]")

    def apply(self, value):
        self.value = value
        vec = self.dir * value
        lines = []
        for P, closed in self.paths[:40]:
            n = len(P)
            top = [Vector(p) + vec for p in P]
            for i in range(n if closed else n - 1):
                lines += [top[i], top[(i + 1) % n]]
            for i in range(0, n, max(1, n // 24)):
                lines += [Vector(P[i]), top[i]]
        self.lines = lines
        try:
            self.area.tag_redraw()
        except (AttributeError, ReferenceError):
            pass

    def restore(self):
        self.lines = []

    def _end(self, context):
        if getattr(self, "_h", None) is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._h, 'WINDOW')
            self._h = None
        self.lines = []
        self.finish_ui(context)

    def cancel_all(self, context):
        self._end(context)
        return {'CANCELLED'}

    def commit(self, context):
        self._end(context)
        if abs(self.value) < 1e-9:
            return {'CANCELLED'}
        try:
            msg = self.build(context, self.value)
        except (RuntimeError, ValueError, ReferenceError, IndexError, np.linalg.LinAlgError) as ex:
            msg = str(ex) or "failed"
        if msg:
            self.report({'WARNING'}, "Gumball: " + msg)
            return {'CANCELLED'}
        return {'FINISHED'}

    def build(self, context, d):
        vec = self.dir * d
        if self.job[0] == 'face':
            _k, name, fidx, sgn, nw = self.job
            obj = bpy.data.objects.get(name)
            if obj is None:
                return "the object is gone"
            target = sum((Vector(p) for P, _c in self.paths for p in P), Vector()) / max(1, sum(len(P) for P, _c in self.paths)) + vec
            bpy.ops.object.mode_set(mode='OBJECT')
            try:
                msg = push_pull_mesh(obj, fidx, d * sgn)
            finally:
                bpy.ops.object.mode_set(mode='EDIT')
            if not msg:                                 # la face déplacée reste sélectionnée : on peut continuer à la tirer
                try:
                    bm = bmesh.from_edit_mesh(obj.data)
                    nm = obj.matrix_world.to_3x3().inverted_safe().transposed()
                    tol = 1e-4 * max(1.0, max(obj.dimensions))
                    R = np.array([tuple(Vector(p) + vec) for P, _c in self.paths for p in P])
                    lo, hi = R.min(axis=0) - tol, R.max(axis=0) + tol
                    keep = []
                    for f in bm.faces:
                        c = obj.matrix_world @ f.calc_center_median()
                        if ((nm @ f.normal).normalized().dot(nw) > 0.999 and abs((c - target).dot(nw)) <= tol
                                and all(lo[i] <= c[i] <= hi[i] for i in range(3))):
                            keep.append(f)
                        f.select_set(False)
                    for f in keep:                      # après avoir tout désélectionné : sinon une face voisine la retire
                        f.select_set(True)
                    bm.select_flush_mode()
                    bmesh.update_edit_mesh(obj.data)
                except (ValueError, ReferenceError, RuntimeError):
                    pass
            return msg
        objs = [bpy.data.objects[n] for n in self.job[1] if n in bpy.data.objects]
        if self.pull == 'CUT':
            closed = [(P, c) for P, c in self.paths if c]
            msg, ncut, nadd = gumball_cut(context, objs, closed, vec, self.ctrl)
            if not msg:
                self.report({'INFO'}, f"Gumball: {ncut} solid(s) cut, {nadd} extended")
            return msg
        groups = [[(P, c) for P, c in self.paths]]
        if any(not c for _P, c in self.paths):
            chained, left = chain_open_paths(self.paths)
            if left == 0:
                groups = [[pc] for pc in chained]
        made = 0
        for paths in nest_groups(groups):
            if not paths:
                continue
            if self.both:
                V, F = extrude_general(paths, vec, True, True, 0.0, None)
            else:
                V, F = extrude_surface(paths, vec, True)
            if len(F):
                mesh_object_from_arrays(context, "Extrusion", V, F, Vector(paths[0][0][0]), True)
                made += 1
        if made:                                        # comme Rhino : la courbe reste sélectionnée, on peut continuer
            deselect_all_objects(context)
            for o in objs:
                o.select_set(True)
            context.view_layer.objects.active = objs[0]
        return "" if made else "nothing to extrude"


class DESSIN_GGT_gumball(bpy.types.GizmoGroup):
    bl_idname = "DESSIN_GGT_gumball"
    bl_label = "Gumball"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'3D', 'PERSISTENT'}

    @classmethod
    def poll(cls, context):
        try:
            if not context.scene.dessin.gumball or foreign_modal(context):
                return False
            if context.mode == 'OBJECT':
                if not context.selected_objects:
                    return False
            elif context.mode == 'EDIT_MESH':
                if not any(o.data.total_vert_sel > 0 for o in context.objects_in_mode_unique_data if o.type == 'MESH'):
                    return False
            elif context.mode == 'EDIT_CURVE':
                if not any(o.type == 'CURVE' for o in context.objects_in_mode_unique_data):
                    return False
            else:
                return False
            tool = context.workspace.tools.from_space_view3d_mode(context.mode, create=False)
        except (AttributeError, RuntimeError, TypeError):
            return False
        return tool is None or tool.idname in _GUMBALL_TOOLS

    def setup(self, context):
        self.gz_move, self.gz_scale, self.gz_rot = [], [], []
        self.gz_ext = None
        for a in range(3):
            col = GUMBALL_COLORS[a]
            for store, kind, gtype, style in ((self.gz_move, 'MOVE', "GIZMO_GT_arrow_3d", 'NORMAL'),
                                              (self.gz_scale, 'SCALE', "GIZMO_GT_arrow_3d", 'BOX'),
                                              (self.gz_rot, 'ROTATE', "GIZMO_GT_dial_3d", None)):
                gz = self.gizmos.new(gtype)
                props = gz.target_set_operator(DESSIN_OT_gumball.bl_idname)
                props.kind = kind
                props.axis = a
                _gz_set(gz, color=col, alpha=0.9, color_highlight=(1.0, 0.85, 0.2), alpha_highlight=1.0,
                        use_draw_modal=True, use_draw_scale=False, scale_basis=1.0)
                if style is not None:
                    _gz_set(gz, draw_style=style)
                else:
                    _gz_set(gz, draw_options={'CLIP'}, line_width=float(pref("gumball_line")))
                store.append(gz)
        # sphère d'extrusion et trait de coupe (comme le Gumball de Rhino) : créés à part, pour qu'une erreur ici ne retire
        # jamais les flèches
        self.gz_ext, self.gz_cut = [], []
        try:
            for a in range(3):
                for store, gtype, pull in ((self.gz_ext, DESSIN_GT_gb_dot.bl_idname, 'EXTRUDE'),
                                           (self.gz_cut, DESSIN_GT_gb_bar.bl_idname, 'CUT')):
                    gz = self.gizmos.new(gtype)
                    props = gz.target_set_operator(DESSIN_OT_gumball_pull.bl_idname)
                    props.pull = pull
                    props.axis = a
                    _gz_set(gz, color=GUMBALL_COLORS[a], alpha=1.0, color_highlight=(1.0, 0.85, 0.2), alpha_highlight=1.0,
                            use_draw_modal=False, use_draw_scale=False, scale_basis=1.0, select_bias=2.0)
                    gz.hide = True
                    store.append(gz)
        except Exception:
            self.gz_ext, self.gz_cut = [], []

    def place(self, context):
        pivot, top = gumball_selection_cached(context)
        rv3d, region = context.region_data, context.region
        every = self.gz_move + self.gz_scale + self.gz_rot
        pulls = getattr(self, "gz_ext", []) + getattr(self, "gz_cut", [])
        if pivot is None or not top or rv3d is None or region is None:
            for gz in every + pulls:
                gz.hide = True
            return
        v = rv3d.perspective_matrix @ Vector((pivot.x, pivot.y, pivot.z, 1.0))
        proj = rv3d.window_matrix[0][0] or 1.0
        px = max(abs(v.w), 1e-6) / (0.5 * region.width * proj)      # unités monde par pixel au centre
        px *= gumball_k(context)
        axes = gumball_axes(context)
        for a in range(3):
            d = axes[a]
            self.gz_move[a].matrix_basis = _axis_matrix(pivot, d, GUMBALL_PX * px)
            self.gz_scale[a].matrix_basis = _axis_matrix(pivot, -d, GUMBALL_PX * 0.98 * px)
            self.gz_rot[a].matrix_basis = _axis_matrix(pivot, d, GUMBALL_PX * 0.62 * px)
        lw = float(pref("gumball_line"))
        for gz in self.gz_rot:
            _gz_set(gz, line_width=lw)
        for gz in every:
            gz.hide = False
        flat = gumball_flat_axes(context, axes)
        for a in flat:
            self.gz_scale[a].hide = True
        if pulls:
            self.place_pulls(context, pivot, axes, px, rv3d)

    def place_pulls(self, context, pivot, axes, px, rv3d):
        """Sphère d'extrusion et trait de coupe : seulement sur les flèches où l'opération est possible."""
        try:
            info = gumball_pull_info(context, axes)
            eye = rv3d.view_rotation @ Vector((0.0, 0.0, 1.0))
            for a in range(3):
                d = axes[a]
                gz = self.gz_ext[a]
                gz.hide = a not in info["ext"]
                if not gz.hide:
                    gz.matrix_basis = Matrix.Translation(pivot + d * (GB_DOT_POS * GUMBALL_PX * px)) @ Matrix.Scale(GB_DOT_R * px, 4)
                gz = self.gz_cut[a]
                b = d.cross(eye)
                gz.hide = a not in info["cut"] or b.length < 1e-3       # flèche vue de bout : pas de trait
                if not gz.hide:
                    b.normalize()
                    R = Matrix((b, d, b.cross(d))).transposed().to_4x4()      # trait en travers de la flèche, face à la vue
                    gz.matrix_basis = Matrix.Translation(pivot + d * (GB_BAR_POS * GUMBALL_PX * px)) @ R @ Matrix.Scale(GB_BAR_L * px, 4)
        except Exception:
            for gz in self.gz_ext + self.gz_cut:
                gz.hide = True

    def refresh(self, context):
        self.place(context)

    def draw_prepare(self, context):
        self.place(context)
        try:
            sp = context.space_data
            if (native_gizmos_hidden() and not _NATIVE_GIZMOS["pending"]
                    and (sp.show_gizmo_object_translate or sp.show_gizmo_object_rotate or sp.show_gizmo_object_scale)):
                _NATIVE_GIZMOS["pending"] = True
                bpy.app.timers.register(_native_gizmos_off, first_interval=0.0)
        except (AttributeError, ReferenceError, RuntimeError):
            pass


_NATIVE_GIZMOS = {"pending": False}


def _native_gizmos_off():
    """Coupe les gizmos Déplacer / Pivoter / Échelle de Blender (le Gumball les remplace) dans toutes les vues 3D."""
    _NATIVE_GIZMOS["pending"] = False
    if not native_gizmos_hidden():
        return None
    try:
        for win in bpy.context.window_manager.windows:
            for area in win.screen.areas:
                if area.type != 'VIEW_3D':
                    continue
                for sp in area.spaces:
                    if sp.type == 'VIEW_3D':
                        for attr in ("show_gizmo_object_translate", "show_gizmo_object_rotate", "show_gizmo_object_scale"):
                            if getattr(sp, attr, False):
                                setattr(sp, attr, False)
    except (AttributeError, RuntimeError, ReferenceError):
        pass
    return None


def native_gizmos_hidden():
    """Les gizmos natifs sont masqués (le Gumball les remplace) tant qu'aucun outil Move / Rotate / Scale / Transform de Blender n'est affiché."""
    return not any(pref(k) for k in ("show_tool_move", "show_tool_rotate", "show_tool_scale", "show_tool_transform"))


def _update_native_gizmos():
    """Réglage « Hide Blender's gizmos » : coché = on les coupe tout de suite ; décoché = on les réaffiche dans toutes les vues 3D."""
    on = native_gizmos_hidden()
    try:
        for win in bpy.context.window_manager.windows:
            for area in win.screen.areas:
                if area.type != 'VIEW_3D':
                    continue
                for sp in area.spaces:
                    if sp.type == 'VIEW_3D':
                        for attr in ("show_gizmo_object_translate", "show_gizmo_object_rotate", "show_gizmo_object_scale"):
                            if hasattr(sp, attr):
                                setattr(sp, attr, not on)
                area.tag_redraw()
    except (AttributeError, RuntimeError, ReferenceError):
        pass


EXT_BALL_ENABLED = False   # poignée d'extrusion orange du Gumball : retirée pour l'instant (clic non fiable)
EXT_BALL_R = 5.0      # rayon de la boule d'extrusion (pixels, avant échelle de l'interface)


def ext_ball_px():
    return EXT_BALL_R * px_scale(0.3)      # échelle atténuée : sur écran Retina la boule restait énorme
_EXT_BALL = {"handle": None, "hover": False}


def foreign_modal(context):
    """True si une commande modale de Blender (Loop Cut, Knife, Bevel...) est en cours : le Gumball s'efface alors et
    ne touche pas au maillage en édition pendant qu'elle travaille."""
    try:
        for op in context.window.modal_operators:
            if not op.bl_idname.startswith("DESSIN_OT"):
                return True
    except (AttributeError, RuntimeError, ReferenceError):
        pass
    return False


def extrude_ball_pos(context, region=None, rv3d=None):
    """Position écran (région, pixels) de la boule d'extrusion, ou None quand elle n'est pas affichée.
    Elle est sur la flèche du Gumball la plus proche de la normale des faces / arêtes sélectionnées."""
    if not EXT_BALL_ENABLED:
        return None
    try:
        if context.mode != 'EDIT_MESH' or not context.scene.dessin.gumball or foreign_modal(context):
            return None
        tool = context.workspace.tools.from_space_view3d_mode(context.mode, create=False)
        if tool is not None and tool.idname not in _GUMBALL_TOOLS:
            return None
        rv3d = rv3d or context.region_data
        region = region or context.region
        if rv3d is None or region is None or region.type != 'WINDOW':
            return None
        nf, ne = extrude_info(context)
        if not (nf or ne):
            return None
        pivot, top = gumball_selection_cached(context)
        if pivot is None or not top:
            return None
        nd = extrude_direction(context) or Vector((0.0, 0.0, 1.0))
    except (AttributeError, RuntimeError, ReferenceError, TypeError):
        return None
    v = rv3d.perspective_matrix @ Vector((pivot.x, pivot.y, pivot.z, 1.0))
    proj = rv3d.window_matrix[0][0] or 1.0
    px = max(abs(v.w), 1e-6) / (0.5 * region.width * proj) * gumball_k(context)
    axis = max(range(3), key=lambda k: abs(AXES3[k].dot(nd)))
    a_dir = AXES3[axis] * (1.0 if AXES3[axis].dot(nd) >= 0 else -1.0)
    line = a_dir if a_dir.dot(nd) > 0.966 else nd       # normale oblique : sur la normale elle-même
    return project_px(rv3d, region, pivot + line * (0.45 * GUMBALL_PX * px))


def draw_extrude_ball():
    context = bpy.context
    pos = extrude_ball_pos(context)
    if pos is None:
        return
    r = ext_ball_px()
    shader = get_shader('2D')
    gpu.state.blend_set('ALPHA')
    shader.bind()
    n = 28
    ring = [(pos.x + r * math.cos(TAU * i / n), pos.y + r * math.sin(TAU * i / n)) for i in range(n)]
    fan = []
    for i in range(n):
        fan += [(pos.x, pos.y), ring[i], ring[(i + 1) % n]]
    col = (1.0, 0.85, 0.3, 1.0) if _EXT_BALL["hover"] else (1.0, 0.65, 0.12, 1.0)
    shader.uniform_float("color", col)
    batch_for_shader(shader, 'TRIS', {"pos": fan}).draw(shader)
    shader.uniform_float("color", (1.0, 1.0, 1.0, 0.9))
    gpu.state.line_width_set(1.5)
    batch_for_shader(shader, 'LINE_LOOP', {"pos": ring}).draw(shader)
    gpu.state.line_width_set(1.0)
    gpu.state.blend_set('NONE')


def extrude_ball_hit(context, mx, my, region=None, rv3d=None):
    """True si le point (région) tombe sur la boule d'extrusion."""
    pos = extrude_ball_pos(context, region, rv3d)
    return pos is not None and (pos - Vector((mx, my))).length <= ext_ball_px() + 4.0 * px_scale(0.5)


def gumball_handle_at(context, mx, my, region, rv3d):
    """(type, axe) de la poignée du Gumball sous le point (région, pixels), ou None.
    Sert quand Alt est maintenu : Blender n'active alors pas toujours les poignées lui-même."""
    try:
        if not context.scene.dessin.gumball or foreign_modal(context):
            return None
        pivot, top = gumball_selection_cached(context)
    except (AttributeError, RuntimeError, ReferenceError, TypeError):
        return None
    if pivot is None or not top or rv3d is None or region is None:
        return None
    v = rv3d.perspective_matrix @ Vector((pivot.x, pivot.y, pivot.z, 1.0))
    proj = rv3d.window_matrix[0][0] or 1.0
    px = max(abs(v.w), 1e-6) / (0.5 * region.width * proj) * gumball_k(context)
    m = Vector((mx, my))
    sp = project_px(rv3d, region, pivot)
    if sp is None:
        return None
    sc = px_scale()
    best, best_d = None, 1e9

    def seg_dist(a, b):
        ab = b - a
        l2 = ab.length_squared
        t = 0.0 if l2 < 1e-9 else max(0.0, min(1.0, (m - a).dot(ab) / l2))
        return (a + ab * t - m).length

    axes = gumball_axes(context)
    flat = gumball_flat_axes(context, axes)
    for a in range(3):
        d = axes[a]
        tip = project_px(rv3d, region, pivot + d * (GUMBALL_PX * px))
        if tip is not None:
            dist = seg_dist(sp, tip)
            if dist <= 9.0 * sc and dist < best_d:
                best, best_d = ('MOVE', a), dist
        tip2 = project_px(rv3d, region, pivot - d * (GUMBALL_PX * 0.98 * px))
        if tip2 is not None and a not in flat:
            dist = seg_dist(sp, tip2)
            if dist <= 9.0 * sc and dist < best_d:
                best, best_d = ('SCALE', a), dist
        bu = d.orthogonal().normalized()
        bv = d.cross(bu)
        R = GUMBALL_PX * 0.62 * px
        ring = []
        for i in range(49):
            ang = TAU * i / 48
            q = project_px(rv3d, region, pivot + (bu * math.cos(ang) + bv * math.sin(ang)) * R)
            ring.append(q)
        for q0, q1 in zip(ring, ring[1:]):
            if q0 is None or q1 is None:
                continue
            dist = seg_dist(q0, q1)
            if dist <= 6.0 * sc and dist < best_d - 3.0 * sc:     # une flèche garde la priorité près du centre
                best, best_d = ('ROTATE', a), dist
    return best


class DESSIN_PT_gumball(bpy.types.Panel):
    bl_label = "Gumball"
    bl_idname = "DESSIN_PT_gumball"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Wanderer"

    def draw(self, context):
        col = self.layout.column()
        col.prop(context.scene.dessin, "gumball")
        col.prop(context.scene.dessin, "gumball_size", slider=True)
        try:
            sysp = context.preferences.system
            col.label(text=f"Screen scale detected: x{px_scale():.2f}  (dpi {sysp.dpi}, pixel size {sysp.pixel_size:g})")
        except (AttributeError, ReferenceError):
            pass
        stp = pref("gumball_step")
        if pref("gumball_rot90"):
            col.label(text=f"Arrows: move  ·  arcs: rotate ({stp}° steps, Shift: free)  ·  boxes: scale")
        else:
            col.label(text=f"Arrows: move  ·  arcs: rotate (free, Shift: {stp}° steps)  ·  boxes: scale")
        col.label(text="Edit mode, face / edge selected: orange ball = extrude")
        col.label(text="Drag, or click then type the value")


OSNAP_BAR = (("end", "End"), ("near", "Near"), ("point", "Point"), ("mid", "Mid"), ("cen", "Cen"), ("int", "Int"),
             ("perp", "Perp"), ("tan", "Tan"), ("quad", "Quad"), ("knot", "Knot"), ("vertex", "Vertex"), ("project", "Project"))


def main_view3d(context):
    """(fenêtre, zone, région WINDOW) du plus grand viewport 3D de la fenêtre (la barre d'état n'en est pas un)."""
    try:
        win = context.window
        best = None
        for a in win.screen.areas:
            if a.type == 'VIEW_3D':
                if best is None or a.width * a.height > best.width * best.height:
                    best = a
        if best is None:
            return None, None, None
        return win, best, next((r for r in best.regions if r.type == 'WINDOW'), None)
    except (AttributeError, ReferenceError):
        return None, None, None


def statusbar_osnap(self, context):
    """Barre OSnap à gauche de la barre d'état de Blender (cases à cocher, comme dans Rhino)."""
    try:
        st = context.scene.dessin
    except (AttributeError, ReferenceError):
        return
    one = oneshot_shown()
    row = self.layout.row(align=True)
    row.label(text="OSnap")
    sub = row.row(align=True)
    sub.active = one or not st.osnap_disable        # F3 : cases grisées (elles restent cliquables)
    for key, label in OSNAP_BAR:
        # cases en boutons : l'opérateur voit la touche Maj (Maj + clic = accrochage ponctuel, comme Rhino). Maj tenu
        # au-dessus de la barre : toutes paraissent décochées ; seuls les accrochages ponctuels cliqués sont cochés
        on = osnap_shown(st, key)
        try:
            sub.operator("dessin.osnap_set", text=label, icon='CHECKBOX_HLT' if on else 'CHECKBOX_DEHLT', emboss=False).key = key
        except (AttributeError, TypeError, RuntimeError):
            sub.prop(st, "osnap_" + key, text=label)        # opérateur absent (module en cours d'arrêt) : la case d'origine
    if one:
        # l'indication vient APRÈS les cases : elles ne bougent pas sous la souris quand Maj les décoche
        row.label(text=tr_text("one shot"))
    self.layout.separator(factor=2.0)


def _late_imports():
    """Noms définis dans des modules chargés après celui-ci : ils ne servent qu'à l'exécution des outils."""
    global _boundary_rings, pp_boundary, pp_draw_cb, pp_region, push_pull_mesh, solid_boolean, write_solid
    from .pushpull import (
        _boundary_rings, pp_boundary, pp_draw_cb, pp_region, push_pull_mesh, solid_boolean, write_solid,
    )
