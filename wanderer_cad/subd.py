"""Wanderer CAD : SubD : cage de contrôle et outils d'édition."""

import bmesh
import bpy
import gpu
import numpy as np
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector, geometry

from .core import edit_add_geometry, plane_axes
from .drawing import get_shader
from .tools_draw import _PlanBody
from .solids import (
    _BoiteBody, _ConeBody, _CylindreBody, _SphereBody, _ToreBody, box_geo, build_solid, frustum_geo, ring_pts,
    sphere_geo, torus_geo,
)


# --------------------------------------------------------------------------
# SubD (comme Rhino) : une SubD est un maillage de contrôle (cage) + un modificateur Subdivision Surface « SubD »
# --------------------------------------------------------------------------

SUBD_MOD = "SubD"


def subd_modifier(obj, create=False):
    """Modificateur de subdivision de l'objet (celui nommé SubD, sinon le premier Subdivision Surface)."""
    if obj is None or obj.type != 'MESH':
        return None
    mods = [m_ for m_ in obj.modifiers if m_.type == 'SUBSURF']
    mod = next((m_ for m_ in mods if m_.name == SUBD_MOD), mods[0] if mods else None)
    if mod is None and create:
        mod = obj.modifiers.new(SUBD_MOD, 'SUBSURF')
        mod.levels = 2
        mod.render_levels = 3
        try:
            mod.boundary_smooth = 'PRESERVE_CORNERS'
            mod.use_limit_surface = True
        except (AttributeError, TypeError):
            pass
        mod.show_in_editmode = True
        mod.show_on_cage = False
    return mod


def _subd_grid_cube(k):
    """Cube unité [-0,5 ; 0,5]^3 découpé en k x k faces par côté : (sommets, faces) en quads."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    if k > 1:
        bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=k - 1, use_grid_fill=True)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    V = [v.co.copy() for v in bm.verts]
    F = [[v.index for v in f.verts] for f in bm.faces]
    bm.free()
    return V, F


def _subd_outward(verts, faces):
    """Faces orientées de façon cohérente, normales vers l'extérieur (maillage fermé)."""
    bm = bmesh.new()
    try:
        vs = [bm.verts.new(p) for p in verts]
        for f in faces:
            try:
                bm.faces.new([vs[i] for i in f])
            except ValueError:
                pass
        bm.verts.index_update()
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        return [[v.index for v in f.verts] for f in bm.faces]
    finally:
        bm.free()


def subd_cage(fn, args, k):
    """Cage de contrôle d'une primitive SubD (faces orientées vers l'extérieur)."""
    res = _subd_cage_raw(fn, args, k)
    if res is None:
        return None
    verts, faces = res
    return verts, _subd_outward(verts, faces)


def _subd_cage_raw(fn, args, k):
    """Cage de contrôle d'une primitive SubD à partir de la spécification du solide équivalent : (sommets monde, faces)."""
    if fn is box_geo:
        o, u, v, n, w, d, h, center = args
        a0, b0 = (-w / 2.0, -d / 2.0) if center else (0.0, 0.0)
        V, F = _subd_grid_cube(k)
        pts = [o + u * (a0 + (p.x + 0.5) * w) + v * (b0 + (p.y + 0.5) * d) + n * ((p.z + 0.5) * h) for p in V]
        if (w * d * h) < 0:
            F = [list(reversed(f)) for f in F]
        return pts, F
    if fn is sphere_geo:
        o, U, V_, N = args[:4]
        V, F = _subd_grid_cube(max(2, k))
        pts = []
        for p in V:
            q = p.normalized()
            pts.append(o + U * q.x + V_ * q.y + N * q.z)
        return pts, F
    if fn is torus_geo:
        o, u, v, n, R, r = args[:6]
        return torus_geo(o, u, v, n, R, r, 4 * max(2, k), 2 * max(2, k))[:2]
    if fn is frustum_geo:
        o, u, v, n, r1, r2, h, seg, start = args
        seg = 4 * max(2, k)
        rings = max(1, k)
        verts, faces = [], []
        apex = r2 < 1e-9
        nr = rings + 1 if not apex else rings
        for j in range(nr):                       # anneaux du flanc, du bas vers le haut
            t = j / rings
            rr = r1 + (r2 - r1) * t
            verts += ring_pts(o + n * (h * t), u, v, rr, seg, start)
        for j in range(nr - 1):
            for i in range(seg):
                i2 = (i + 1) % seg
                faces.append([j * seg + i, j * seg + i2, (j + 1) * seg + i2, (j + 1) * seg + i])
        # bouchons : un anneau intérieur (faces en quads) puis un polygone central
        def cap(ring0, rr, z, flip):
            b = len(verts)
            verts.extend(ring_pts(o + n * z, u, v, rr * 0.55, seg, start))
            for i in range(seg):
                i2 = (i + 1) % seg
                f = [ring0 + i, ring0 + i2, b + i2, b + i]
                faces.append(list(reversed(f)) if flip else f)
            c = list(range(b, b + seg))
            faces.append(c if flip else list(reversed(c)))
        cap(0, r1, 0.0, True)
        if apex:
            top = len(verts)
            verts.append(o + n * h)
            base = (nr - 1) * seg
            for i in range(seg):
                faces.append([base + i, base + (i + 1) % seg, top])
        else:
            cap((nr - 1) * seg, r2, h, False)
        if h < 0:
            faces = [list(reversed(f)) for f in faces]
        return verts, faces
    return None


def _subd_frame_coords(P, o, axes):
    A = np.array([tuple(a) for a in axes], dtype=np.float64)          # (3, 3) : lignes = axes
    return (np.asarray(P, dtype=np.float64) - np.array(tuple(o))) @ A.T


def subd_fit(context, obj, target_pts, o, axes, passes=2):
    """Comme une primitive SubD de Rhino : la surface lisse (et non la cage) a les dimensions demandées.
    On met la cage à l'échelle, axe par axe, jusqu'à ce que la surface subdivisée remplisse la boîte voulue."""
    T = _subd_frame_coords(target_pts, o, axes)
    tmin, tmax = T.min(0), T.max(0)
    for _ in range(passes):
        context.view_layer.update()          # matrix_world à jour (l'objet vient d'être placé)
        mw = obj.matrix_world.copy()
        inv = mw.inverted()
        dg = context.evaluated_depsgraph_get()
        ev = obj.evaluated_get(dg)
        me = ev.to_mesh()
        try:
            co = np.empty(len(me.vertices) * 3, dtype=np.float64)
            me.vertices.foreach_get('co', co)
        finally:
            ev.to_mesh_clear()
        W = co.reshape(-1, 3) @ np.array(mw, dtype=np.float64)[:3, :3].T + np.array(mw.translation)
        E = _subd_frame_coords(W, o, axes)
        emin, emax = E.min(0), E.max(0)
        ext_e, ext_t = emax - emin, tmax - tmin
        s = np.where(ext_e > 1e-9, ext_t / np.where(ext_e > 1e-9, ext_e, 1.0), 1.0)
        ce, ct = (emin + emax) / 2.0, (tmin + tmax) / 2.0
        if np.allclose(s, 1.0, atol=1e-5) and np.allclose(ce, ct, atol=1e-7 + 1e-6 * float(np.abs(ext_t).max())):
            break
        me0 = obj.data
        C = np.empty(len(me0.vertices) * 3, dtype=np.float64)
        me0.vertices.foreach_get('co', C)
        Wc = C.reshape(-1, 3) @ np.array(mw, dtype=np.float64)[:3, :3].T + np.array(mw.translation)
        L = _subd_frame_coords(Wc, o, axes)
        L = ct + (L - ce) * s
        A = np.array([tuple(a) for a in axes], dtype=np.float64)
        Wn = np.array(tuple(o)) + L @ A
        loc = np.hstack((Wn, np.ones((len(Wn), 1)))) @ np.array(inv, dtype=np.float64).T
        me0.vertices.foreach_set('co', loc[:, :3].astype(np.float32).ravel())
        me0.update()


class SubDMixin:
    """Primitives SubD : même saisie que le solide équivalent ; on construit une cage de contrôle + le modificateur SubD."""

    def build(self, context, spec):
        if spec is None or spec[0] != "solid":
            return super().build(context, spec)
        _kind, name, fn, args = spec
        try:
            k = int(context.scene.dessin.subd_faces)
        except (AttributeError, TypeError, ValueError):
            k = 2
        cage = subd_cage(fn, args, k)
        if cage is None:
            return super().build(context, spec)
        verts, faces = cage
        if context.mode == 'EDIT_MESH':
            return edit_add_geometry(context, verts, [], faces)      # en édition : la cage s'ajoute au maillage édité
        origin = self.points[0].copy()
        obj = build_solid(context, self.SOLID_NAME, verts, faces, [True] * len(faces), origin)
        obj["wd_subd"] = True
        subd_modifier(obj, create=True)
        target = fn(*args)[0]
        _o, u, v, n = self.frame()
        try:
            subd_fit(context, obj, target, origin, (u, v, n))
        except (RuntimeError, ValueError, AttributeError, ReferenceError):
            pass
        return obj


class DESSIN_OT_subd_box(SubDMixin, _BoiteBody):
    bl_idname = "dessin.subd_box"
    bl_label = "SubD Box"
    bl_description = ("SubD box like SubDBox: first corner, opposite corner, then height. Smooth surface over a quad control cage "
                      "(faces per side: SubD faces), editable in Edit Mode")
    TITLE = "SubD Box"
    SOLID_NAME = "SubD Box"


class DESSIN_OT_subd_sphere(SubDMixin, _SphereBody):
    bl_idname = "dessin.subd_sphere"
    bl_label = "SubD Sphere"
    bl_description = "SubD sphere like SubDSphere (quad ball): center then radius. Smooth surface over a quad control cage"
    TITLE = "SubD Sphere"
    SOLID_NAME = "SubD Sphere"


class DESSIN_OT_subd_cylinder(SubDMixin, _CylindreBody):
    bl_idname = "dessin.subd_cylinder"
    bl_label = "SubD Cylinder"
    bl_description = "SubD cylinder like SubDCylinder: center, radius, then height. Smooth surface over a quad control cage"
    TITLE = "SubD Cylinder"
    SOLID_NAME = "SubD Cylinder"


class DESSIN_OT_subd_cone(SubDMixin, _ConeBody):
    bl_idname = "dessin.subd_cone"
    bl_label = "SubD Cone"
    bl_description = "SubD cone like SubDCone: center, radius, then height. Smooth surface over a control cage"
    TITLE = "SubD Cone"
    SOLID_NAME = "SubD Cone"


class DESSIN_OT_subd_torus(SubDMixin, _ToreBody):
    bl_idname = "dessin.subd_torus"
    bl_label = "SubD Torus"
    bl_description = "SubD torus like SubDTorus: center, first radius, second radius. Smooth surface over a quad control cage"
    TITLE = "SubD Torus"
    SOLID_NAME = "SubD Torus"


class DESSIN_OT_subd_plane(_PlanBody):
    bl_idname = "dessin.subd_plane"
    bl_label = "SubD Plane"
    bl_description = "SubD plane like SubDPlane: first corner then opposite corner. A grid of quads (SubD faces per side), smooth, with sharp corners"
    TITLE = "SubD Plane"

    def build(self, context, spec):
        if spec[0] != 'rect':
            return super().build(context, spec)
        try:
            k = max(1, int(context.scene.dessin.subd_faces)) * 2
        except (AttributeError, TypeError, ValueError):
            k = 4
        c = [Vector(p) for p in spec[1]]
        verts = []
        for j in range(k + 1):
            for i in range(k + 1):
                a, b = i / k, j / k
                verts.append(c[0] + (c[1] - c[0]) * a + (c[3] - c[0]) * b)
        faces = [[j * (k + 1) + i, j * (k + 1) + i + 1, (j + 1) * (k + 1) + i + 1, (j + 1) * (k + 1) + i]
                 for j in range(k) for i in range(k)]
        if (c[1] - c[0]).cross(c[3] - c[0]).dot(plane_axes(self.axis)[2]) < 0:
            faces = [list(reversed(f)) for f in faces]
        if context.mode == 'EDIT_MESH':
            return edit_add_geometry(context, verts, [], faces)
        origin = self.points[0].copy()
        obj = build_solid(context, "SubD Plane", verts, faces, [True] * len(faces), origin)
        obj["wd_subd"] = True
        subd_modifier(obj, create=True)        # coins conservés (bord lisse, angles vifs) : le plan garde ses dimensions
        return obj


SUBD_ACTIONS = (
    ('TO_SUBD', "To SubD", "Turn the selected meshes into SubD (smooth surface over their faces as control cage), like ToSubD"),
    ('TO_MESH', "SubD to Mesh", "Apply the subdivision: the smooth surface becomes the mesh (the control cage is lost)"),
    ('DISPLAY', "Toggle SubD Display", "Smooth / box display of the SubD, like ToggleSubDDisplay"),
    ('CREASE', "Crease", "Sharp crease on the selected edges (Edit Mode)"),
    ('UNCREASE', "Remove Crease", "Remove the crease from the selected edges (Edit Mode)"),
    ('INSERT_EDGE', "Insert Edge", "Insert an edge loop across the faces, like InsertEdge (Edit Mode)"),
    ('SLIDE', "Slide", "Slide the selected edges or points along the surface (Edit Mode)"),
    ('BRIDGE', "Bridge", "Bridge two edge chains with faces (Edit Mode)"),
    ('FILL', "Fill", "Fill the selected hole with quads (Edit Mode)"),
    ('APPEND', "Append Face", "Create a face from the selected points or edges, like Append (Edit Mode)"),
    ('BEVEL', "Bevel", "Bevel the selected edges (Edit Mode)"),
    ('INSET', "Inset", "Inset the selected faces: a smaller copy of each face surrounded by a ring of faces (Edit Mode)"),
    ('MERGE_FACES', "Merge Faces", "Merge the selected faces into one (Edit Mode)"),
    ('WELD', "Weld", "Weld the points that are at the same place (Edit Mode)"),
    ('STITCH', "Stitch", "Stitch the selected points / edges together, on the last selected (Edit Mode)"),
    ('EXTRACT', "Extract Faces", "Extract the selected faces into a separate object (Edit Mode)"),
    ('SEL_LOOP', "Select Loop", "Select the edge loop of the selected edges (Edit Mode)"),
    ('SEL_RING', "Select Ring", "Select the edge ring of the selected edges (Edit Mode)"),
    ('REFLECT_X', "Symmetry X", "Symmetry across the X axis of the object, live (Mirror before the SubD), like Reflect"),
    ('REFLECT_Y', "Symmetry Y", "Symmetry across the Y axis of the object, live"),
    ('REFLECT_Z', "Symmetry Z", "Symmetry across the Z axis of the object, live"),
    ('MULTIPIPE', "MultiPipe", "SubD pipes along the selected curves or wire meshes, joined at the nodes, like MultiPipe"),
)
SUBD_EDIT_ONLY = {'CREASE', 'UNCREASE', 'INSERT_EDGE', 'SLIDE', 'BRIDGE', 'FILL', 'APPEND', 'BEVEL', 'INSET', 'MERGE_FACES', 'WELD',
                  'STITCH', 'EXTRACT', 'SEL_LOOP', 'SEL_RING'}


def _subd_targets(context):
    if context.mode == 'EDIT_MESH':
        return [o for o in context.objects_in_mode_unique_data if o.type == 'MESH']
    return [o for o in context.selected_objects if o.type == 'MESH']


class DESSIN_OT_subd(bpy.types.Operator):
    bl_idname = "dessin.subd"
    bl_label = "SubD"
    bl_description = "SubD tools like the SubD commands of Rhino"
    bl_options = {'REGISTER', 'UNDO'}

    action: bpy.props.EnumProperty(name="Action", items=[(a, n, d) for a, n, d in SUBD_ACTIONS], default='TO_SUBD')

    @classmethod
    def description(cls, context, props):
        return next((d for a, _n, d in SUBD_ACTIONS if a == props.action), cls.bl_description)

    @classmethod
    def poll(cls, context):
        return context.mode in {'OBJECT', 'EDIT_MESH'} and context.area is not None and context.area.type == 'VIEW_3D'

    def invoke(self, context, event):
        return self.execute(context)

    def done(self, msg, level='INFO'):
        cmd_log(msg)
        self.report({level}, msg)
        return {'FINISHED'}

    def execute(self, context):
        a = self.action
        label = next(n for k, n, _d in SUBD_ACTIONS if k == a)
        if a in SUBD_EDIT_ONLY and context.mode != 'EDIT_MESH':
            self.report({'WARNING'}, f"{label}: select edges, faces or points in Edit Mode (Tab) first")
            return {'CANCELLED'}
        try:
            meth = "do_reflect" if a.startswith("REFLECT_") else "do_" + a.lower()
            return getattr(self, meth)(context, label)
        except RuntimeError as e:
            self.report({'WARNING'}, f"{label}: {str(e).splitlines()[-1] if str(e) else 'not possible here'}")
            return {'CANCELLED'}

    # ---- objets ----
    def do_to_subd(self, context, label):
        objs = _subd_targets(context)
        if not objs:
            self.report({'WARNING'}, "To SubD: select meshes first")
            return {'CANCELLED'}
        n = 0
        for o in objs:
            if subd_modifier(o) is None:
                subd_modifier(o, create=True)
                o["wd_subd"] = True
                n += 1
            else:
                subd_modifier(o).show_viewport = True
        return self.done(f"To SubD: {n} object(s) converted" + ("" if n == len(objs) else f", {len(objs) - n} already SubD"))

    def do_to_mesh(self, context, label):
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        objs = [o for o in context.selected_objects if subd_modifier(o) is not None]
        if not objs:
            self.report({'WARNING'}, "SubD to Mesh: select SubD objects first")
            return {'CANCELLED'}
        for o in objs:
            mod = subd_modifier(o)
            # les modificateurs avant la SubD (Symétrie...) sont appliqués d'abord, dans l'ordre de la pile
            upto = list(o.modifiers)[:list(o.modifiers).index(mod) + 1]
            with context.temp_override(object=o, active_object=o, selected_objects=[o], selected_editable_objects=[o]):
                for md in upto:
                    if md.name == mod.name:
                        md.show_viewport = True          # affichage « cage » : on applique quand même la surface lisse
                    if md.show_viewport:
                        bpy.ops.object.modifier_apply(modifier=md.name)
            if "wd_subd" in o.keys():
                del o["wd_subd"]
        return self.done(f"SubD to Mesh: {len(objs)} object(s)")

    def do_display(self, context, label):
        mods = [subd_modifier(o) for o in _subd_targets(context)]
        mods = [m_ for m_ in mods if m_ is not None]
        if not mods:
            self.report({'WARNING'}, "Toggle SubD Display: no SubD in the selection")
            return {'CANCELLED'}
        on = not all(m_.show_viewport for m_ in mods)
        for m_ in mods:
            m_.show_viewport = on
        return self.done("SubD display: " + ("smooth" if on else "box (control cage)"))

    def do_reflect(self, context, label):
        """Symétrie (comme Symmetry / Reflect de Rhino) : la cage est coupée en son milieu sur l'axe, la moitié négative
        est supprimée et un Mirror (avant la SubD) recrée l'autre moitié, soudée au plan. Relancée : la symétrie est
        appliquée (les deux moitiés deviennent la cage) et retirée."""
        axis = "XYZ".index(self.action[-1])
        objs = _subd_targets(context)
        if not objs:
            self.report({'WARNING'}, "Symmetry: select a mesh first")
            return {'CANCELLED'}
        was_edit = context.mode == 'EDIT_MESH'
        if was_edit:
            bpy.ops.object.mode_set(mode='OBJECT')
        msgs = []
        try:
            for o in objs:
                mm = next((m_ for m_ in o.modifiers if m_.type == 'MIRROR' and m_.name.startswith("Symmetry")), None)
                if mm is not None and mm.use_axis[axis]:
                    with context.temp_override(object=o, active_object=o, selected_objects=[o], selected_editable_objects=[o]):
                        try:
                            o.modifiers.move(list(o.modifiers).index(mm), 0)
                        except (AttributeError, RuntimeError, ValueError):
                            pass
                        bpy.ops.object.modifier_apply(modifier=mm.name)
                    msgs.append("applied (both halves kept)")
                    continue
                e = Vector((0.0, 0.0, 0.0))
                e[axis] = 1.0
                me = o.data
                co = [v.co[axis] for v in me.vertices]
                if not co:
                    continue
                c = (min(co) + max(co)) / 2.0
                if abs(c) > 1e-9:
                    # le plan de symétrie passe par le milieu de l'objet : l'origine y est ramenée (l'objet ne bouge pas)
                    me.transform(Matrix.Translation(-e * c))
                    o.matrix_world = o.matrix_world @ Matrix.Translation(e * c)
                bm = bmesh.new()
                bm.from_mesh(me)
                bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], dist=1e-6,
                                       plane_co=(0.0, 0.0, 0.0), plane_no=tuple(e), clear_inner=True)
                for v in bm.verts:
                    if abs(v.co[axis]) < 1e-6:
                        v.co[axis] = 0.0
                bm.to_mesh(me)
                bm.free()
                me.update()
                if mm is None:
                    mm = o.modifiers.new("Symmetry", 'MIRROR')
                    mm.use_axis = (False, False, False)
                    mm.use_clip = True
                    mm.use_mirror_merge = True
                    mm.merge_threshold = 1e-4
                    try:
                        o.modifiers.move(len(o.modifiers) - 1, 0)       # avant la subdivision : la jonction reste lisse
                    except (AttributeError, RuntimeError):
                        pass
                ax = list(mm.use_axis)
                ax[axis] = True
                mm.use_axis = ax
                msgs.append("on")
        finally:
            if was_edit:
                bpy.ops.object.mode_set(mode='EDIT')
        state = msgs[0] if len(set(msgs)) == 1 and msgs else ", ".join(msgs)
        return self.done(f"Symmetry {'XYZ'[axis]}: {state}" + ("  (the cage is cut in the middle, edit one half)" if "on" in msgs else ""))

    def do_multipipe(self, context, label):
        """Un seul réseau de tubes (comme MultiPipe) : toutes les courbes sélectionnées, soudées aux extrémités communes
        et aux jonctions en T (une extrémité posée sur une autre courbe)."""
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        srcs = [o for o in context.selected_objects if o.type in {'CURVE', 'MESH'}]
        dg = context.evaluated_depsgraph_get()
        P, chains = [], []          # points monde, et pour chaque courbe la liste ordonnée de ses arêtes
        for src in srcs:
            ev = src.evaluated_get(dg)
            try:
                me = ev.to_mesh()
            except RuntimeError:
                continue
            try:
                if me is None or len(me.polygons) or not len(me.edges):
                    continue
                mw = src.matrix_world
                base = len(P)
                P += [mw @ v.co for v in me.vertices]
                chains.append([(base + e.vertices[0], base + e.vertices[1]) for e in me.edges])
            finally:
                ev.to_mesh_clear()
        if not chains:
            self.report({'WARNING'}, "MultiPipe: select curves or wire meshes (edges without faces) first")
            return {'CANCELLED'}
        Pn = np.array([tuple(p) for p in P], dtype=np.float64)
        size = float(np.linalg.norm(Pn.max(0) - Pn.min(0))) or 1.0
        tol = 1e-5 * size + 1e-7
        # croisements entre courbes différentes (X, T, extrémité ou sommet posé sur une autre courbe) : on coupe les arêtes
        # concernées au point de rencontre, pour que le réseau soit relié comme avec MultiPipe
        owner = [ci for ci, c in enumerate(chains) for _e in c]
        edges = [e for c in chains for e in c]
        A = np.array([tuple(P[a]) for a, _b in edges], dtype=np.float64)
        B = np.array([tuple(P[b]) for _a, b in edges], dtype=np.float64)
        lo, hi = np.minimum(A, B) - tol * 10, np.maximum(A, B) + tol * 10
        splits = {}
        for i in range(len(edges)):
            cand = np.nonzero(np.all(lo[i + 1:] <= hi[i], axis=1) & np.all(hi[i + 1:] >= lo[i], axis=1))[0] + i + 1
            for j in cand:
                if owner[j] == owner[i]:
                    continue
                res = geometry.intersect_line_line(P[edges[i][0]], P[edges[i][1]], P[edges[j][0]], P[edges[j][1]])
                if res is None:
                    continue
                q1, q2 = res
                if (q1 - q2).length > tol * 10:
                    continue
                ok = True
                ts = []
                for k, q in ((i, q1), (j, q2)):
                    a_, b_ = P[edges[k][0]], P[edges[k][1]]
                    ab = b_ - a_
                    L2 = ab.length_squared
                    t = (q - a_).dot(ab) / L2 if L2 > 1e-24 else 0.0
                    if t < -1e-6 or t > 1.0 + 1e-6:
                        ok = False
                    ts.append(t)
                if not ok:
                    continue
                pq = (q1 + q2) * 0.5
                idx = len(P)
                P.append(pq)
                for k, t in zip((i, j), ts):
                    if 1e-6 < t < 1.0 - 1e-6:
                        splits.setdefault(k, []).append((t, idx))
        new_edges = []
        for k, (a, b) in enumerate(edges):
            pts_ = [a] + [ix for _t, ix in sorted(splits.get(k, []))] + [b]
            new_edges += list(zip(pts_[:-1], pts_[1:]))
        edges = new_edges
        # soudure des points confondus
        key, remap, V = {}, {}, []
        for i, p in enumerate(P):
            q = (round(p.x / tol), round(p.y / tol), round(p.z / tol))
            if q not in key:
                key[q] = len(V)
                V.append(p)
            remap[i] = key[q]
        E = sorted({tuple(sorted((remap[a], remap[b]))) for a, b in edges if remap[a] != remap[b]})
        me = bpy.data.meshes.new("MultiPipe")
        me.from_pydata([tuple(v) for v in V], E, [])
        me.update()
        obj = bpy.data.objects.new("MultiPipe", me)
        context.collection.objects.link(obj)
        sk = obj.modifiers.new("MultiPipe", 'SKIN')
        sk.use_smooth_shade = True
        r = context.scene.dessin.subd_radius or max(size * 0.03, 1e-4)
        for sv in me.skin_vertices[0].data:
            sv.radius = (r, r)
        subd_modifier(obj, create=True)
        obj["wd_subd"] = True
        for o in context.selected_objects:
            o.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        return self.done(f"MultiPipe: {len(E)} segment(s), radius {r:.4g}  (Pipe radius in the SubD panel, 0 = automatic)")

    # ---- mode édition ----
    def _bm(self, context):
        out = []
        for o in _subd_targets(context):
            out.append((o, bmesh.from_edit_mesh(o.data)))
        return out

    def do_crease(self, context, label, value=1.0):
        n = 0
        for o, bm in self._bm(context):
            lay = bm.edges.layers.float.get('crease_edge') or bm.edges.layers.float.new('crease_edge')
            for e in bm.edges:
                if e.select:
                    e[lay] = value
                    n += 1
            bmesh.update_edit_mesh(o.data, loop_triangles=False, destructive=False)
        if not n:
            self.report({'WARNING'}, f"{label}: select edges first")
            return {'CANCELLED'}
        return self.done(f"{label}: {n} edge(s)")

    def do_uncrease(self, context, label):
        return self.do_crease(context, label, 0.0)

    def do_insert_edge(self, context, label):
        bpy.ops.mesh.loopcut_slide('INVOKE_DEFAULT')
        return {'FINISHED'}

    def do_slide(self, context, label):
        if context.tool_settings.mesh_select_mode[1] or context.tool_settings.mesh_select_mode[2]:
            bpy.ops.transform.edge_slide('INVOKE_DEFAULT')
        else:
            bpy.ops.transform.vert_slide('INVOKE_DEFAULT')
        return {'FINISHED'}

    def _counts(self, context):
        f = v = 0
        for o in _subd_targets(context):
            bm = bmesh.from_edit_mesh(o.data)
            f += len(bm.faces)
            v += len(bm.verts)
        return f, v

    def _checked(self, context, label, run, hint, what="faces"):
        """Lance l'opération et dit honnêtement ce qui a changé (Blender ne renvoie pas toujours d'erreur)."""
        f0, v0 = self._counts(context)
        try:
            run()
        except RuntimeError as e:
            self.report({'WARNING'}, f"{label}: {hint}")
            return {'CANCELLED'}
        f1, v1 = self._counts(context)
        if what == "add" and f1 <= f0:
            self.report({'WARNING'}, f"{label}: no face created ({hint})")
            return {'CANCELLED'}
        if what == "add":
            what = "faces"
        if what == "faces" and f1 == f0:
            self.report({'WARNING'}, f"{label}: nothing done ({hint})")
            return {'CANCELLED'}
        if what == "verts" and v1 == v0:
            self.report({'WARNING'}, f"{label}: nothing done ({hint})")
            return {'CANCELLED'}
        if what == "faces":
            return self.done(f"{label}: {abs(f1 - f0)} face(s) {'added' if f1 > f0 else 'removed'}")
        return self.done(f"{label}: {v0 - v1} point(s) merged")

    def do_bridge(self, context, label):
        return self._checked(context, label, lambda: bpy.ops.mesh.bridge_edge_loops(),
                             "select two separate edge loops or chains with the same number of edges", what="add")

    def do_fill(self, context, label):
        def run():
            try:
                bpy.ops.mesh.fill_grid()
            except RuntimeError:
                bpy.ops.mesh.edge_face_add()
        return self._checked(context, label, run, "select the closed border of a hole", what="add")

    def do_append(self, context, label):
        return self._checked(context, label, lambda: bpy.ops.mesh.edge_face_add(),
                             "select at least three points or two edges", what="add")

    def do_inset(self, context, label):
        if not any(f.select for o in _subd_targets(context) for f in bmesh.from_edit_mesh(o.data).faces):
            self.report({'WARNING'}, "Inset: select faces first")
            return {'CANCELLED'}
        bpy.ops.mesh.inset('INVOKE_DEFAULT')
        return {'FINISHED'}

    def do_bevel(self, context, label):
        bpy.ops.mesh.bevel('INVOKE_DEFAULT', affect='EDGES')
        return {'FINISHED'}

    def do_merge_faces(self, context, label):
        return self._checked(context, label, lambda: bpy.ops.mesh.dissolve_faces(), "select at least two adjacent faces")

    def do_weld(self, context, label):
        before = sum(len(bmesh.from_edit_mesh(o.data).verts) for o in _subd_targets(context))
        bpy.ops.mesh.remove_doubles(threshold=1e-4)
        after = sum(len(bmesh.from_edit_mesh(o.data).verts) for o in _subd_targets(context))
        return self.done(f"Weld: {before - after} point(s) welded")

    def do_stitch(self, context, label):
        def run():
            try:
                bpy.ops.mesh.merge(type='LAST')
            except (RuntimeError, TypeError):
                bpy.ops.mesh.merge(type='CENTER')
        return self._checked(context, label, run, "select at least two points or edges", what="verts")

    def do_extract(self, context, label):
        bpy.ops.mesh.separate(type='SELECTED')
        return self.done("Extract Faces: the selected faces are now a separate object")

    def do_sel_loop(self, context, label):
        if hasattr(bpy.ops.mesh, "select_edge_loop_multi"):
            bpy.ops.mesh.select_edge_loop_multi()
        else:
            bpy.ops.mesh.loop_multi_select(ring=False)
        return {'FINISHED'}

    def do_sel_ring(self, context, label):
        if hasattr(bpy.ops.mesh, "select_edge_ring_multi"):
            bpy.ops.mesh.select_edge_ring_multi()
        else:
            bpy.ops.mesh.loop_multi_select(ring=True)
        return {'FINISHED'}


class DESSIN_PT_subd(bpy.types.Panel):
    bl_label = "SubD"
    bl_idname = "DESSIN_PT_subd"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Wanderer"

    @classmethod
    def poll(cls, context):
        return context.mode in {'OBJECT', 'EDIT_MESH'}

    def draw(self, context):
        lay = self.layout
        st = context.scene.dessin
        col = lay.column(align=True)
        if context.mode == 'OBJECT':
            g = col.grid_flow(row_major=True, columns=2, even_columns=True, align=True)
            for tid, txt in (("dessin.subd_box_tool", "Box"), ("dessin.subd_sphere_tool", "Sphere"),
                             ("dessin.subd_cylinder_tool", "Cylinder"), ("dessin.subd_cone_tool", "Cone"),
                             ("dessin.subd_torus_tool", "Torus"), ("dessin.subd_plane_tool", "Plane")):
                g.operator("wm.tool_set_by_id", text=txt).name = tid
            col.prop(st, "subd_faces")
            col.separator()
        acts = (('TO_SUBD', 'TO_MESH'), ('DISPLAY',), ('REFLECT_X', 'REFLECT_Y', 'REFLECT_Z'))
        if context.mode == 'EDIT_MESH':
            acts = (('CREASE', 'UNCREASE'), ('INSERT_EDGE', 'SLIDE'), ('BEVEL', 'INSET'), ('BRIDGE', 'FILL'), ('APPEND',),
                    ('MERGE_FACES', 'EXTRACT'), ('WELD', 'STITCH'), ('SEL_LOOP', 'SEL_RING'), ('DISPLAY',),
                    ('REFLECT_X', 'REFLECT_Y', 'REFLECT_Z'))
        names = {a: n for a, n, _d in SUBD_ACTIONS}
        for row_acts in acts:
            row = col.row(align=True)
            for a in row_acts:
                row.operator(DESSIN_OT_subd.bl_idname, text=names[a]).action = a
        if context.mode == 'OBJECT':
            col.separator()
            row = col.row(align=True)
            row.operator(DESSIN_OT_subd.bl_idname, text="MultiPipe").action = 'MULTIPIPE'
            row.prop(st, "subd_radius", text="Radius")


def expand_groups(context, objs):
    """Ajoute à la liste tous les membres des groupes touchés (cliquer un objet d'un groupe = tout le groupe)."""
    try:
        if not context.scene.dessin.group_select:
            return list(objs)
    except AttributeError:
        return list(objs)
    out, seen = [], set()

    def add(o):
        if o.name not in seen:
            seen.add(o.name)
            out.append(o)
    for o in objs:
        add(o)
        root = group_root(o)
        if root is not None:
            for m in group_members(root):
                try:
                    if m.visible_get():
                        add(m)
                except RuntimeError:
                    pass
    return out


def duplicate_hierarchy(obj, parent=None):
    """Copie obj (données comprises) et tous ses enfants : un groupe copié reste un groupe complet."""
    dup = obj.copy()
    if obj.data is not None:
        dup.data = obj.data.copy()
    for coll in obj.users_collection:
        coll.objects.link(dup)
    if parent is not None:
        dup.parent = parent
        dup.matrix_parent_inverse = obj.matrix_parent_inverse.copy()
    for ch in obj.children:
        duplicate_hierarchy(ch, dup)
    return dup


_GHOST = {"pts": None, "batch": None, "handle": None, "area": None}


def ghost_for_objects(items, max_edges=500000):
    """Arêtes (monde) de la position d'origine des objets : items = [(objet, matrice monde d'origine)]. Tableau (2n, 3) ou None."""
    try:
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
    except (RuntimeError, AttributeError):
        return None
    chunks, total = [], 0
    for top, mw0 in items:
        try:
            X = np.array(mw0 @ top.matrix_world.inverted_safe(), dtype=np.float64)
            objs = [top] + list(top.children_recursive)
        except (ReferenceError, ValueError):
            continue
        for obj in objs:
            if obj.type not in {'MESH', 'CURVE', 'SURFACE', 'FONT'}:
                continue
            try:
                ev = obj.evaluated_get(dg)
                me = ev.to_mesh()
            except (RuntimeError, ReferenceError):
                continue
            try:
                nv, ne = len(me.vertices), len(me.edges)
                if nv == 0 or ne == 0:
                    continue
                if total + ne > max_edges:
                    # objet trop dense pour être redessiné à chaque image : on n'affiche que sa boîte englobante
                    mw = np.array(ev.matrix_world, dtype=np.float64)
                    bb = np.array([tuple(c) for c in ev.bound_box], dtype=np.float64) @ mw[:3, :3].T + mw[:3, 3]
                    box = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)]
                    chunks.append(np.array([[bb[a], bb[b]] for a, b in box], dtype=np.float32).reshape(-1, 3))
                    continue
                co = np.empty(nv * 3, dtype=np.float32)
                me.vertices.foreach_get('co', co)
                edges = np.empty(ne * 2, dtype=np.int32)
                me.edges.foreach_get('vertices', edges)
                mw = np.array(ev.matrix_world, dtype=np.float64)
                world = co.reshape(-1, 3).astype(np.float64) @ mw[:3, :3].T + mw[:3, 3]
                world = world @ X[:3, :3].T + X[:3, 3]
                chunks.append(world[edges].astype(np.float32))
                total += ne
            finally:
                ev.to_mesh_clear()
    return np.vstack(chunks) if chunks else None


def ghost_for_edit(items):
    """Arêtes (monde) de la sélection en mode édition à sa position d'origine : items = [(objet, indices, positions monde)]."""
    chunks = []
    for obj, idx, w0 in items:
        try:
            bm = bmesh.from_edit_mesh(obj.data)
        except (ValueError, ReferenceError):
            continue
        pos = {i: w0[k] for k, i in enumerate(idx)}
        for e in bm.edges:
            a, b = e.verts[0].index, e.verts[1].index
            if a in pos and b in pos:
                chunks.append((pos[a], pos[b]))
    return np.array(chunks, dtype=np.float32).reshape(-1, 3) if chunks else None


def draw_ghost_cb():
    pts = _GHOST["pts"]
    if pts is None:
        return
    try:
        if bpy.context.area.as_pointer() != _GHOST["area"].as_pointer():
            return
    except (ReferenceError, AttributeError):
        return
    shader = get_shader('3D')
    gpu.state.blend_set('ALPHA')
    gpu.state.depth_test_set('NONE')
    shader.bind()
    if _GHOST["batch"] is None:
        _GHOST["batch"] = batch_for_shader(shader, 'LINES', {"pos": pts})
    gpu.state.line_width_set(1.0)
    shader.uniform_float("color", (0.85, 0.9, 1.0, 0.45))
    _GHOST["batch"].draw(shader)
    gpu.state.blend_set('NONE')


def ghost_show(area, pts):
    """Affiche en transparence la position d'origine (comme l'outil Déplacer) pendant une copie."""
    if pts is None:
        return
    if _GHOST["pts"] is not pts:
        _GHOST["pts"], _GHOST["batch"] = pts, None
    _GHOST["area"] = area
    if _GHOST["handle"] is None:
        _GHOST["handle"] = bpy.types.SpaceView3D.draw_handler_add(draw_ghost_cb, (), 'WINDOW', 'POST_VIEW')
    try:
        area.tag_redraw()
    except (ReferenceError, AttributeError):
        pass


def ghost_hide():
    area = _GHOST["area"]
    if _GHOST["handle"] is not None:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(_GHOST["handle"], 'WINDOW')
        except (ValueError, RuntimeError):
            pass
        _GHOST["handle"] = None
    _GHOST["pts"] = _GHOST["batch"] = None
    _GHOST["area"] = None
    try:
        area.tag_redraw()
    except (ReferenceError, AttributeError):
        pass


def copy_moved_objects(context, items):
    """items : [(objet, matrice monde d'origine)] déjà déplacés : les originaux reviennent en place, les copies gardent la position."""
    dups = []
    for obj, mw in items:
        try:
            dup = duplicate_hierarchy(obj)
            dup.matrix_world = obj.matrix_world.copy()
            obj.matrix_world = mw
        except ReferenceError:
            continue
        dups.append(dup)
    for o in context.view_layer.objects:
        try:
            o.select_set(False)
        except RuntimeError:
            pass
    for dup in dups:
        dup.select_set(True)
    if dups:
        context.view_layer.objects.active = dups[-1]
    return dups


def copy_moved_edit(items):
    """items : [(objet, indices, positions monde d'origine)] : la géométrie sélectionnée, déjà déplacée, est dupliquée ;
    l'original revient en place et la copie devient la sélection."""
    for obj, idx, w0 in items:
        try:
            bm = bmesh.from_edit_mesh(obj.data)
        except (ValueError, ReferenceError):
            continue
        bm.verts.ensure_lookup_table()
        verts = [bm.verts[i] for i in idx]
        vset = set(verts)
        geom = list(verts)
        geom += [e for e in bm.edges if e.verts[0] in vset and e.verts[1] in vset]
        geom += [f for f in bm.faces if all(v in vset for v in f.verts)]
        ret = bmesh.ops.duplicate(bm, geom=geom)
        inv = np.linalg.inv(np.array(obj.matrix_world, dtype=np.float64))
        for v, p in zip(verts, w0):
            q = inv @ np.array((p[0], p[1], p[2], 1.0))
            v.co = Vector((q[0], q[1], q[2]))
        for g in geom:
            g.select_set(False)
        for g in ret['geom']:
            g.select_set(True)
        bm.select_flush_mode()
        bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=True)


def _late_imports():
    """Noms définis dans des modules chargés après celui-ci : ils ne servent qu'à l'exécution des outils."""
    global cmd_log, group_members, group_root
    from .objects import group_members, group_root
    from .cplane import cmd_log
