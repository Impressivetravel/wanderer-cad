"""Wanderer CAD : Make2D."""

import bmesh
import bpy
import math
import numpy as np

from .trim import wire_paths
from .surfaces import ordered_selection


# --------------------------------------------------------------------------
# Make2D : dessin 2D (lignes visibles / cachées) des objets sélectionnés, selon une vue du plugin
# --------------------------------------------------------------------------

MAKE2D_LIMIT = 60000          # arêtes candidates maximum (au-delà : on prévient)


def named_view_rotation(scene, name):
    """Rotation (quaternion) d'une vue nommée du plugin : vue enregistrée, sinon vue de base."""
    entry = find_view(scene, name)
    if entry is not None:
        return Quaternion_(entry.rot)
    axis = dict(BASE_VIEWS).get(name)
    return _axis_quat(axis)


def make2d_view_items(self, context):
    scene = context.scene
    items = [(n, view_label(scene, n), "") for n, _a in BASE_VIEWS]
    items += [(v.name, v.name, "") for v in scene.dessin_views if not v.base]
    make2d_view_items.cache = items
    return items


make2d_view_items.cache = []


def mesh_world_data(obj, depsgraph):
    """(sommets monde [Vector], triangles, bmesh monde) d'un objet, d'après sa forme évaluée (modificateurs compris)."""
    ev = obj.evaluated_get(depsgraph)
    me = ev.to_mesh()
    bm = bmesh.new()
    bm.from_mesh(me)
    ev.to_mesh_clear()
    bm.transform(obj.matrix_world)
    bm.normal_update()
    return bm


def make2d_collect(objs, depsgraph):
    """Rassemble les maillages des objets : bmesh monde par objet + arbre BVH global (occultation)."""
    from mathutils.bvhtree import BVHTree
    bms, verts, tris = [], [], []
    for o in objs:
        try:
            bm = mesh_world_data(o, depsgraph)
        except (RuntimeError, AttributeError, TypeError):
            continue
        bms.append((o, bm))
        base = len(verts)
        verts.extend(v.co.copy() for v in bm.verts)
        for lt in bm.calc_loop_triangles():
            tris.append(tuple(base + l.vert.index for l in lt))
    bvh = BVHTree.FromPolygons(verts, tris, epsilon=0.0) if tris else None
    return bms, bvh, verts


def make2d_project(bms, bvh, quat, diag, tangent=False, hidden=False, sharp_deg=25.0):
    """Projette les arêtes caractéristiques selon la rotation `quat` (projection parallèle, l'observateur regarde vers -Z de la vue).
    Retourne {objet: ([segments visibles (a, b)], [segments cachés])} avec a, b = points 2D (u, v)."""
    from mathutils import Vector
    right = quat @ Vector((1.0, 0.0, 0.0))
    up = quat @ Vector((0.0, 1.0, 0.0))
    look = quat @ Vector((0.0, 0.0, -1.0))
    toward = -look                          # vers l'observateur
    eps = max(diag * 1e-5, 1e-9)
    far = diag * 4.0 + 1.0
    sharp = math.radians(sharp_deg)
    tan_min = math.radians(1.0)

    def visible(p):
        if bvh is None:
            return True
        return bvh.ray_cast(p + toward * eps, toward, far)[0] is None

    def uv(p):
        return (p.dot(right), p.dot(up))

    out = {}
    for obj, bm in bms:
        vis_segs, hid_segs = [], []
        for e in bm.edges:
            faces = e.link_faces
            nf = len(faces)
            keep = False
            if nf != 2:
                keep = True                                  # bord, arête libre ou non-variété
            else:
                f0, f1 = faces
                front0, front1 = f0.normal.dot(look) < 0.0, f1.normal.dot(look) < 0.0
                if front0 != front1:
                    keep = True                              # silhouette
                else:
                    ang = e.calc_face_angle(0.0)
                    if ang >= sharp or not e.smooth:
                        keep = True                          # arête vive
                    elif tangent and ang >= tan_min:
                        keep = True                          # arête tangente (surfaces lisses)
            if not keep:
                continue
            a, b = e.verts[0].co, e.verts[1].co
            ua, ub = uv(a), uv(b)
            l2d = math.hypot(ub[0] - ua[0], ub[1] - ua[1])
            if l2d < diag * 1e-7:
                continue                                     # arête dans l'axe de la vue
            n = max(2, min(40, int(l2d / (diag * 0.02)) + 2))
            ts = [i / (n - 1) for i in range(n)]
            vs = [visible(a.lerp(b, t)) for t in ts]
            # frontières de visibilité par dichotomie
            cuts = [0.0]
            states = [vs[0]]
            for i in range(n - 1):
                if vs[i] != vs[i + 1]:
                    lo, hi = ts[i], ts[i + 1]
                    s_lo = vs[i]
                    for _k in range(14):
                        mid = (lo + hi) * 0.5
                        if visible(a.lerp(b, mid)) == s_lo:
                            lo = mid
                        else:
                            hi = mid
                    cuts.append((lo + hi) * 0.5)
                    states.append(vs[i + 1])
            cuts.append(1.0)
            for k, state in enumerate(states):
                t0, t1 = cuts[k], cuts[k + 1]
                if t1 - t0 <= 1e-9:
                    continue
                seg = (uv(a.lerp(b, t0)), uv(a.lerp(b, t1)))
                if state:
                    vis_segs.append(seg)
                elif hidden:
                    hid_segs.append(seg)
        out[obj] = (vis_segs, hid_segs)
    return out


def merge_segments(segs, tol):
    """Chaîne les segments 2D en polylignes : [(points [(u, v)], fermé)]."""
    index, pts, edges, seen = {}, [], [], set()
    for a, b in segs:
        ids = []
        for p in (a, b):
            key = (round(p[0] / tol), round(p[1] / tol))
            if key not in index:
                index[key] = len(pts)
                pts.append(p)
            ids.append(index[key])
        if ids[0] == ids[1]:
            continue
        k = (min(ids), max(ids))
        if k in seen:
            continue
        seen.add(k)
        edges.append((ids[0], ids[1]))
    paths = []
    for path, closed in wire_paths(len(pts), edges):
        P = [pts[i] for i in path]
        if closed and len(P) > 1 and abs(P[0][0] - P[-1][0]) + abs(P[0][1] - P[-1][1]) <= tol * 2:
            P = P[:-1]
        if len(P) >= 2:
            paths.append((P, bool(closed) and len(P) >= 3))
    return paths


def bbox_2d(segs):
    xs = [p[0] for s in segs for p in s]
    ys = [p[1] for s in segs for p in s]
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def new_poly_curve(name, paths, place):
    """Courbe à plusieurs splines POLY. place(u, v) -> (x, y, z) monde."""
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    for P, closed in paths:
        sp = cu.splines.new('POLY')
        sp.points.add(len(P) - 1)
        for pt, (u, v) in zip(sp.points, P):
            x, y, z = place(u, v)
            pt.co = (x, y, z, 1.0)
        sp.use_cyclic_u = closed
    return cu


def output_collection(context, name):
    name = name.strip() or "Make2D"
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        context.scene.collection.children.link(col)
    elif col.name not in context.scene.collection.children_recursive and col not in context.scene.collection.children_recursive:
        try:
            context.scene.collection.children.link(col)
        except RuntimeError:
            pass
    return col


class DESSIN_OT_make2d(bpy.types.Operator):
    bl_idname = "dessin.make2d"
    bl_label = "Make 2D"
    bl_description = ("Creates a 2D drawing (visible and hidden lines) of the selected objects as seen from one of the named views, "
                      "or as a third / first angle projection")
    bl_options = {'REGISTER', 'UNDO'}

    view: bpy.props.EnumProperty(name="View", items=make2d_view_items)
    projection: bpy.props.EnumProperty(
        name="Projection", default='VIEW',
        items=(('VIEW', "View", "Parallel projection seen from the chosen view"),
               ('THIRD', "Third angle projection", "Front, with Top above and Right on the right"),
               ('FIRST', "First angle projection", "Front, with Top below and Right on the left")))
    tangent_edges: bpy.props.BoolProperty(
        name="Tangent edges", default=False,
        description="Also draws the edges between smooth surfaces (can add many lines on finely tessellated meshes)")
    hidden_lines: bpy.props.BoolProperty(name="Hidden lines", default=False,
                                         description="Also creates the hidden lines, as separate grey objects")
    viewport_rect: bpy.props.BoolProperty(name="Viewport rectangle", default=False,
                                          description="Adds a rectangle around each drawing")
    group_output: bpy.props.BoolProperty(name="Group output", default=False,
                                         description="Parents the results of each view to an Empty so they move together")
    place_beside: bpy.props.BoolProperty(name="Place beside the objects", default=True,
                                         description="Puts the drawing flat on the ground (XY), to the right of the objects. Off: at the world origin")
    sharp_angle: bpy.props.FloatProperty(name="Sharp edge angle", default=math.radians(25.0), min=0.0, max=math.pi,
                                         subtype='ANGLE', description="Edges between faces that make a larger angle are drawn")
    collection_name: bpy.props.StringProperty(name="Collection name", default="Make2D")

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and context.area is not None and context.area.type == 'VIEW_3D'

    def invoke(self, context, event):
        objs = ordered_selection(context)
        if not objs:
            self.report({'INFO'}, "Click the objects, then Enter")
            return {'CANCELLED'}
        names = [i[0] for i in make2d_view_items(self, context)]
        cur = current_view_name(context)
        self.view = cur if cur in names else "Top"
        return context.window_manager.invoke_props_dialog(self, width=340)

    def draw(self, context):
        layout = self.layout
        layout.label(text="View")
        layout.prop(self, "view", text="")
        layout.label(text="Projection")
        col = layout.column(align=True)
        col.prop(self, "projection", expand=True)
        layout.label(text="Options")
        col = layout.column(align=True)
        col.prop(self, "tangent_edges")
        col.prop(self, "hidden_lines")
        col.prop(self, "viewport_rect")
        col.prop(self, "group_output")
        col.prop(self, "place_beside")
        col.prop(self, "sharp_angle")
        layout.label(text="Collection name")
        layout.prop(self, "collection_name", text="")
        if self.projection != 'VIEW':
            layout.label(text="Top / Front / Right are used (the view above is ignored)", icon='INFO')

    def execute(self, context):
        scene = context.scene
        objs = ordered_selection(context)
        if not objs:
            self.report({'INFO'}, "Select objects first")
            return {'CANCELLED'}
        depsgraph = context.evaluated_depsgraph_get() if hasattr(context, "evaluated_depsgraph_get") else bpy.context.evaluated_depsgraph_get()
        bms, bvh, verts = make2d_collect(objs, depsgraph)
        try:
            if not bms or not verts:
                self.report({'WARNING'}, "No geometry to project")
                return {'CANCELLED'}
            P = np.array([tuple(v) for v in verts])
            lo, hi = P.min(axis=0), P.max(axis=0)
            diag = float(np.linalg.norm(hi - lo)) or 1.0
            if sum(len(bm.edges) for _o, bm in bms) > MAKE2D_LIMIT:
                self.report({'WARNING'}, "Very heavy model: Make 2D may take a while")
            if self.projection == 'VIEW':
                views = [(self.view, named_view_rotation(scene, self.view))]
            else:
                views = [(n, _axis_quat(a)) for n, a in (("Front", 'FRONT'), ("Top", 'TOP'), ("Right", 'RIGHT'))]
            results = {}
            for vname, quat in views:
                res = make2d_project(bms, bvh, quat, diag, self.tangent_edges, self.hidden_lines, self.sharp_angle)
                allsegs = [s for vis, hid in res.values() for s in vis + hid]
                results[vname] = (res, bbox_2d(allsegs))
        finally:
            for _o, bm in bms:
                bm.free()
        if all(b is None for _r, b in results.values()):
            self.report({'WARNING'}, "Nothing to draw in this view")
            return {'CANCELLED'}
        gap = diag * 0.1
        offsets = self.layout_offsets(results, lo, hi, gap)
        col = output_collection(context, self.collection_name)
        made = []
        for vname, (res, bb) in results.items():
            if bb is None:
                continue
            ox, oy = offsets[vname]
            place = (lambda ox, oy: (lambda u, v: (u + ox, v + oy, 0.0)))(ox, oy)
            tol = max(diag * 1e-6, 1e-9)
            label = view_label(scene, vname) if vname in dict(BASE_VIEWS) or find_view(scene, vname) else vname
            parent = None
            if self.group_output:
                parent = bpy.data.objects.new(f"Make2D {label}", None)
                parent.empty_display_type = 'PLAIN_AXES'
                parent.empty_display_size = diag * 0.02
                col.objects.link(parent)
                made.append(parent)
            for obj, (vis, hid) in res.items():
                for suffix, segs, grey in ((label, vis, False), (f"{label} hidden", hid, True)):
                    paths = merge_segments(segs, tol)
                    if not paths:
                        continue
                    cu = new_poly_curve(f"{obj.name} {suffix}", paths, place)
                    o = bpy.data.objects.new(cu.name, cu)
                    if grey:
                        o.color = (0.5, 0.5, 0.5, 1.0)
                    col.objects.link(o)
                    if parent is not None:
                        o.parent = parent
                    made.append(o)
            if self.viewport_rect:
                pad = diag * 0.02
                x0, y0, x1, y1 = bb[0] - pad, bb[1] - pad, bb[2] + pad, bb[3] + pad
                cu = new_poly_curve(f"Make2D {label} frame", [([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], True)], place)
                o = bpy.data.objects.new(cu.name, cu)
                col.objects.link(o)
                if parent is not None:
                    o.parent = parent
                made.append(o)
        for o in context.selected_objects:
            o.select_set(False)
        for o in made:
            o.select_set(True)
        if made:
            context.view_layer.objects.active = made[0]
        self.report({'INFO'}, f"Make 2D: {len(made)} object(s) in '{col.name}'")
        return {'FINISHED'}

    def layout_offsets(self, results, lo, hi, gap):
        """Décalage (x, y) de chaque dessin : à droite des objets, vues en croix pour les projections à 3 vues."""
        if not self.place_beside:
            return {n: (0.0, 0.0) for n in results}
        def bb(n):
            return results[n][1]
        if self.projection == 'VIEW':
            n = next(iter(results))
            b = bb(n)
            if b is None:
                return {n: (0.0, 0.0)}
            return {n: (hi[0] + gap - b[0], lo[1] - b[1])}
        fb = bb("Front") or (0.0, 0.0, 0.0, 0.0)
        x0 = hi[0] + gap - fb[0]
        y0 = lo[1] - fb[1]
        offs = {"Front": (x0, y0)}
        tb, rb = bb("Top"), bb("Right")
        if tb is not None:
            if self.projection == 'THIRD':
                offs["Top"] = (x0, y0 + fb[3] + gap - tb[1])
            else:
                offs["Top"] = (x0, y0 + fb[1] - gap - tb[3])
        if rb is not None:
            if self.projection == 'THIRD':
                offs["Right"] = (x0 + fb[2] + gap - rb[0], y0)
            else:
                offs["Right"] = (x0 + fb[0] - gap - rb[2], y0)
        return offs


def _late_imports():
    """Noms définis dans des modules chargés après celui-ci : ils ne servent qu'à l'exécution des outils."""
    global BASE_VIEWS, Quaternion_, _axis_quat, current_view_name, find_view, view_label
    from .navigation import BASE_VIEWS, _axis_quat
    from .views import Quaternion_, current_view_name, find_view, view_label
