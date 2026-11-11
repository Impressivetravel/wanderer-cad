"""Wanderer CAD : Groupes, matériaux, menus contextuels, édition de polylignes."""

import bpy
from mathutils import Matrix, Vector, geometry


# --------------------------------------------------------------------------
# Groupes (empty parent) : Group / Ungroup + sélection du groupe entier au clic
# --------------------------------------------------------------------------

GROUP_KEY = "cad_group"
_GROUP_SEL = {"last": set(), "on": False}


def is_group(obj):
    return obj is not None and obj.type == 'EMPTY' and bool(obj.get(GROUP_KEY))


def group_root(obj):
    """Groupe le plus haut contenant (ou étant) obj, ou None."""
    root = obj if is_group(obj) else None
    p = obj.parent
    while p is not None:
        if is_group(p):
            root = p
        p = p.parent
    return root


def group_members(root):
    out = [root]
    out.extend(root.children_recursive)
    return out


class DESSIN_OT_group(bpy.types.Operator):
    bl_idname = "dessin.group"
    bl_label = "Group"
    bl_description = "Groups the selected objects: they are selected and moved together (Ungroup to release them)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and len(context.selected_objects) >= 1

    def execute(self, context):
        sel = list(context.selected_objects)
        selected = set(sel)
        top = [o for o in sel if o.parent not in selected]
        if len(top) < 2:
            self.report({'WARNING'}, "Select at least two objects to group")
            return {'CANCELLED'}
        pts = []
        for o in top:
            pts += [o.matrix_world @ Vector(c) for c in o.bound_box] if o.type != 'EMPTY' else [o.matrix_world.translation]
        center = sum(pts, Vector()) / len(pts)
        empty = bpy.data.objects.new("Group", None)
        empty.empty_display_type = 'PLAIN_AXES'
        empty.empty_display_size = 0.1
        empty[GROUP_KEY] = True
        empty.location = center
        colls = list(top[0].users_collection) or [context.view_layer.active_layer_collection.collection]
        for c in colls:
            c.objects.link(empty)
        context.view_layer.update()
        for o in top:
            mw = o.matrix_world.copy()
            o.parent = empty
            o.matrix_parent_inverse = Matrix.Identity(4)
            o.matrix_world = mw
        for o in context.view_layer.objects:
            o.select_set(False)
        for o in group_members(empty):
            o.select_set(True)
        context.view_layer.objects.active = empty
        _GROUP_SEL["last"] = {o.name for o in group_members(empty)}
        self.report({'INFO'}, f"Group of {len(top)} objects")
        return {'FINISHED'}


class DESSIN_OT_ungroup(bpy.types.Operator):
    bl_idname = "dessin.ungroup"
    bl_label = "Ungroup"
    bl_description = "Releases the selected group(s): the objects keep their position and become independent"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and any(group_root(o) is not None for o in context.selected_objects)

    def execute(self, context):
        cand = {group_root(o) for o in context.selected_objects}
        cand.discard(None)
        # un niveau à la fois : on ne dégroupe que les groupes les plus externes parmi ceux choisis
        outer = [g for g in cand if not any(is_group(a) and a in cand for a in _ancestors(g))]
        freed = []
        for g in outer:
            parent = g.parent
            for ch in list(g.children):
                mw = ch.matrix_world.copy()
                ch.parent = parent
                ch.matrix_parent_inverse = parent.matrix_world.inverted() if parent is not None else Matrix.Identity(4)
                ch.matrix_world = mw
                freed.append(ch)
            bpy.data.objects.remove(g)
        context.view_layer.update()
        for o in context.view_layer.objects:
            try:
                o.select_set(False)
            except (RuntimeError, AttributeError):
                pass
        for o in freed:
            o.select_set(True)
        if freed:
            context.view_layer.objects.active = freed[0]
        _GROUP_SEL["last"] = {o.name for o in freed}
        self.report({'INFO'}, f"{len(outer)} group(s) released")
        return {'FINISHED'}


def _ancestors(obj):
    p = obj.parent
    while p is not None:
        yield p
        p = p.parent


def menu_group(self, context):
    if context.mode != 'OBJECT':
        return
    layout = self.layout
    sel = context.selected_objects
    layout.separator()
    if len(sel) >= 2:
        layout.operator(DESSIN_OT_group.bl_idname, icon='GROUP')
    if any(group_root(o) is not None for o in sel):
        layout.operator(DESSIN_OT_ungroup.bl_idname, icon='UGLYPACKAGE')
    layout.separator()


class DESSIN_OT_material_remove_all(bpy.types.Operator):
    bl_idname = "dessin.material_remove_all"
    bl_label = "Remove All Materials"
    bl_description = "Removes every material slot from the selected objects"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return any(getattr(o, "material_slots", None) is not None and o.type in {'MESH', 'CURVE', 'SURFACE', 'FONT', 'META'}
                   for o in context.selected_objects)

    def execute(self, context):
        n = 0
        done = set()
        for o in context.selected_objects:
            if o.type not in {'MESH', 'CURVE', 'SURFACE', 'FONT'} or o.data is None or o.data.as_pointer() in done:
                continue
            done.add(o.data.as_pointer())
            n += len(o.data.materials)
            o.data.materials.clear()
        self.report({'INFO'}, "%d material slot(s) removed" % n)
        return {'FINISHED'}


class DESSIN_MT_ctx_material(bpy.types.Menu):
    bl_idname = "DESSIN_MT_ctx_material"
    bl_label = "Material"

    def draw(self, context):
        layout = self.layout
        layout.operator("object.material_slot_copy", text="Copy Material to Selected", icon='COPYDOWN')
        layout.separator()
        layout.operator("material.copy", text="Copy Material", icon='COPYDOWN')
        layout.operator("material.paste", text="Paste Material", icon='PASTEDOWN')
        layout.separator()
        layout.operator("object.material_slot_remove_unused", text="Remove Unused Slots", icon='X')
        layout.operator(DESSIN_OT_material_remove_all.bl_idname, text="Remove All Materials", icon='TRASH')


class DESSIN_MT_ctx_select(bpy.types.Menu):
    bl_idname = "DESSIN_MT_ctx_select"
    bl_label = "Select"

    def draw(self, context):
        layout = self.layout
        if context.mode == 'EDIT_MESH':
            layout.operator("mesh.select_linked", text="Linked", icon='LINKED')
            layout.operator("mesh.select_linked_pick", text="Linked Under Cursor").deselect = False
            layout.separator()
            layout.operator("object.material_slot_select", text="Select Material Slot")
            layout.operator("object.material_slot_deselect", text="Deselect Material Slot")
            layout.separator()
            layout.operator("mesh.select_similar", text="Similar...")
            layout.operator("mesh.select_all", text="Invert Selection").action = 'INVERT'
            return
        layout.operator("object.select_linked", text="Same Material").type = 'MATERIAL'
        layout.operator("object.select_linked", text="Same Object Data (instances)").type = 'OBDATA'
        layout.operator("object.select_linked", text="Same Modifiers").type = 'MODIFIERS'
        layout.operator("object.select_linked", text="Same Collection Instance").type = 'DUPGROUP'
        layout.separator()
        layout.operator("object.select_grouped", text="Same Type").type = 'TYPE'
        layout.operator("object.select_grouped", text="Same Collection").type = 'COLLECTION'
        layout.operator("object.select_grouped", text="Same Parent").type = 'SIBLINGS'
        layout.operator("object.select_grouped", text="Children").type = 'CHILDREN_RECURSIVE'
        layout.operator("object.select_grouped", text="Parent").type = 'PARENT'
        layout.separator()
        layout.operator("object.select_all", text="Invert Selection").action = 'INVERT'


class DESSIN_OT_track_to(bpy.types.Operator):
    bl_idname = "dessin.track_to"
    bl_label = "Track To"
    bl_description = ("Makes the selected cameras and lights aim at the active object (Track To constraint: -Z towards the target, Y up). "
                      "Select the camera(s) first, then the target last (it stays active)")
    bl_options = {'REGISTER', 'UNDO'}

    clear: bpy.props.BoolProperty(name="Clear", default=False, options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and bool(context.selected_objects)

    def execute(self, context):
        act = context.active_object
        if self.clear:
            n = 0
            for o in context.selected_objects:
                for c in [c for c in o.constraints if c.type == 'TRACK_TO']:
                    o.constraints.remove(c)
                    n += 1
            self.report({'INFO'}, f"{n} Track To constraint(s) removed")
            return {'FINISHED'}
        others = [o for o in context.selected_objects if o is not act]
        if act is None or not others:
            self.report({'WARNING'}, "Select the camera first, then the target last (Shift+click) so it is the active object")
            return {'CANCELLED'}
        for o in others:
            for c in [c for c in o.constraints if c.type == 'TRACK_TO']:
                o.constraints.remove(c)
            c = o.constraints.new('TRACK_TO')
            c.target = act
            c.track_axis = 'TRACK_NEGATIVE_Z'
            c.up_axis = 'UP_Y'
        self.report({'INFO'}, f"{len(others)} object(s) now track {act.name}")
        return {'FINISHED'}


POLY_EDIT_ACTIONS = (
    ('CLOSE', "Close", "Closes the polyline: the last point joins the first"),
    ('OPEN', "Open", "Opens a closed polyline"),
    ('REVERSE', "Reverse", "Reverses the direction of the polyline"),
    ('CURVE_FIT', "Curve Fit", "Smooth curve passing through every vertex"),
    ('SPLINE_FIT', "Spline Fit", "Smooth spline that follows the vertices (they become control points)"),
    ('DECURVE', "Decurve", "Back to straight segments between the vertices"),
    ('WIDTH', "Width", "Gives the polyline a thickness"),
)


def _spline_points(sp):
    if sp.type == 'BEZIER':
        return [bp.co.copy() for bp in sp.bezier_points]
    return [Vector(p.co[:3]) for p in sp.points]


def _rebuild_spline(cu, kind, pts, closed):
    """Crée dans `cu` une spline POLY / BEZIER (poignées automatiques) / NURBS passant par ou contrôlée par `pts`."""
    if kind == 'BEZIER':
        sp = cu.splines.new('BEZIER')
        sp.bezier_points.add(len(pts) - 1)
        for bp, q in zip(sp.bezier_points, pts):
            bp.co = q
            bp.handle_left_type = bp.handle_right_type = 'AUTO'
    else:
        sp = cu.splines.new(kind)
        sp.points.add(len(pts) - 1)
        for sp_pt, q in zip(sp.points, pts):
            sp_pt.co = (q.x, q.y, q.z, 1.0)
        if kind == 'NURBS':
            sp.order_u = max(2, min(4, len(pts)))
            sp.use_endpoint_u = not closed
    sp.use_cyclic_u = closed
    sp.resolution_u = 12


class DESSIN_OT_extend_crv(bpy.types.Operator):
    bl_idname = "dessin.extend_crv"
    bl_label = "Extend Curve"
    bl_description = ("Extends the selected curves at one or both ends: by a length, or up to the nearest other curve / outline "
                      "(the extension follows the end of the curve). Command line: ExtendCrv")
    bl_options = {'REGISTER', 'UNDO'}

    mode: bpy.props.EnumProperty(
        name="Extend", items=(('LENGTH', "By length", "Extends the end by the given length"),
                              ('BOUNDARY', "To boundary", "Extends up to the nearest other curve or outline")), default='LENGTH')
    end: bpy.props.EnumProperty(
        name="End", items=(('END', "End", "Last point of the curve"), ('START', "Start", "First point of the curve"),
                           ('BOTH', "Both", "Both ends")), default='END')
    length: bpy.props.FloatProperty(name="Length", default=1.0, min=0.0, unit='LENGTH')

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and any(o.type == 'CURVE' for o in context.selected_objects)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        lay = self.layout
        lay.prop(self, "mode")
        lay.prop(self, "end")
        if self.mode == 'LENGTH':
            lay.prop(self, "length")

    @staticmethod
    def _boundaries(context, exclude):
        dg = context.evaluated_depsgraph_get()
        segs = []
        for obj in context.visible_objects:
            if obj in exclude:
                continue
            g = wire_graph(obj, dg)
            if g is None:
                continue
            verts, edges = g
            segs += [(verts[i], verts[j]) for i, j in edges]
            if len(segs) > 30000:
                break
        return segs

    @staticmethod
    def _hit(p, d, segs, tol=1e-3):
        best = None
        for a, b in segs:
            r = geometry.intersect_line_line(p, p + d, a, b)
            if r is None:
                continue
            c1, c2 = r
            if (c1 - c2).length > tol:
                continue
            t = (c1 - p).dot(d)
            ab = b - a
            l2 = ab.dot(ab)
            if t <= 1e-6 or l2 < 1e-18:
                continue
            u = (c2 - a).dot(ab) / l2
            if -1e-6 <= u <= 1.0 + 1e-6 and (best is None or t < best):
                best = t
        return best

    def _extent(self, p, d, segs):
        """Longueur d'extension au point monde p dans la direction d (None : aucune limite trouvée)."""
        if self.mode == 'LENGTH':
            return self.length
        return self._hit(p, d, segs)

    def execute(self, context):
        sel = [o for o in context.selected_objects if o.type == 'CURVE']
        segs = self._boundaries(context, set(sel)) if self.mode == 'BOUNDARY' else []
        ends = {'END': (False,), 'START': (True,), 'BOTH': (False, True)}[self.end]
        done = missed = 0
        for obj in sel:
            mw = obj.matrix_world
            inv = mw.inverted()
            m3 = mw.to_3x3()
            for sp in obj.data.splines:
                if sp.use_cyclic_u:
                    continue
                for at_start in ends:
                    if sp.type == 'BEZIER':
                        bps = sp.bezier_points
                        if len(bps) < 2:
                            continue
                        data = [(bp.co.copy(), bp.handle_left.copy(), bp.handle_right.copy(), bp.handle_left_type, bp.handle_right_type)
                                for bp in bps]
                        if at_start:
                            co, hl, hr = data[0][0], data[0][1], data[0][2]
                            d = m3 @ (co - hr if (co - hr).length > 1e-9 else co - data[1][0])
                        else:
                            co, hl, hr = data[-1][0], data[-1][1], data[-1][2]
                            d = m3 @ (co - hl if (co - hl).length > 1e-9 else co - data[-2][0])
                        if d.length < 1e-12:
                            continue
                        d.normalize()
                        pw = mw @ co
                        ln = self._extent(pw, d, segs)
                        if ln is None:
                            missed += 1
                            continue
                        qw = pw + d * ln
                        q = inv @ qw
                        dl = (inv.to_3x3() @ d) * (ln / 3.0)
                        new = (q, q - dl, q + dl, 'FREE', 'FREE')
                        if at_start:
                            new = (q, q + dl, q - dl, 'FREE', 'FREE')       # le point de départ « regarde » vers l'extérieur
                            data.insert(0, new)
                        else:
                            data.append(new)
                        bps.add(1)
                        for bp, (c, l, r, tl, tr) in zip(bps, data):
                            bp.handle_left_type = bp.handle_right_type = 'FREE'
                            bp.co = c
                            bp.handle_left, bp.handle_right = l, r
                            bp.handle_left_type, bp.handle_right_type = tl, tr
                    else:
                        pts = [Vector(pt.co[:3]) for pt in sp.points]
                        if len(pts) < 2:
                            continue
                        a, b = (pts[0], pts[1]) if at_start else (pts[-1], pts[-2])
                        d = m3 @ (a - b)
                        if d.length < 1e-12:
                            continue
                        d.normalize()
                        pw = mw @ a
                        ln = self._extent(pw, d, segs)
                        if ln is None:
                            missed += 1
                            continue
                        q = inv @ (pw + d * ln)
                        pts = [q] + pts if at_start else pts + [q]
                        kind, closed, order = sp.type, sp.use_cyclic_u, sp.order_u
                        sp.points.add(1)
                        for pt, c in zip(sp.points, pts):
                            pt.co = (c.x, c.y, c.z, 1.0)
                    done += 1
        if missed:
            self.report({'WARNING'}, f"{missed} end(s) have no boundary in their direction")
        return {'FINISHED'} if done else {'CANCELLED'}


def _act_invoke(op):
    def run(context):
        mod, name = op.split(".")
        getattr(getattr(bpy.ops, mod), name)('INVOKE_DEFAULT')
        return ""
    return run


class DESSIN_OT_poly_edit(bpy.types.Operator):
    bl_idname = "dessin.poly_edit"
    bl_label = "Edit Polyline"
    bl_options = {'REGISTER', 'UNDO'}

    action: bpy.props.EnumProperty(name="Action", items=[(a, n, d) for a, n, d in POLY_EDIT_ACTIONS], default='CLOSE')
    width: bpy.props.FloatProperty(name="Width", default=0.05, min=0.0, soft_max=1.0, unit='LENGTH')

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and any(o.type == 'CURVE' for o in context.selected_objects)

    def invoke(self, context, event):
        if self.action == 'WIDTH':
            return context.window_manager.invoke_props_dialog(self)
        return self.execute(context)

    def draw(self, context):
        if self.action == 'WIDTH':
            self.layout.prop(self, "width")

    def execute(self, context):
        done = 0
        for obj in context.selected_objects:
            if obj.type != 'CURVE':
                continue
            cu = obj.data
            a = self.action
            if a == 'WIDTH':
                cu.bevel_depth = self.width / 2.0
                cu.bevel_resolution = 2
                done += 1
                continue
            if a in {'CLOSE', 'OPEN'}:
                for sp in cu.splines:
                    sp.use_cyclic_u = (a == 'CLOSE')
            elif a == 'REVERSE':
                for sp in cu.splines:
                    if sp.type == 'BEZIER':
                        data = [(bp.co.copy(), bp.handle_left.copy(), bp.handle_right.copy(), bp.handle_left_type, bp.handle_right_type)
                                for bp in sp.bezier_points]
                        for bp, (c, hl, hr, tl, tr) in zip(sp.bezier_points, reversed(data)):
                            bp.handle_left_type = bp.handle_right_type = 'FREE'
                            bp.co = c
                            bp.handle_left, bp.handle_right = hr, hl
                            bp.handle_left_type, bp.handle_right_type = tr, tl
                    else:
                        co = [tuple(p.co) for p in sp.points]
                        for p, c in zip(sp.points, reversed(co)):
                            p.co = c
            else:       # CURVE_FIT / SPLINE_FIT / DECURVE : on reconstruit les splines
                kind = {'CURVE_FIT': 'BEZIER', 'SPLINE_FIT': 'NURBS', 'DECURVE': 'POLY'}[a]
                old = [(_spline_points(sp), sp.use_cyclic_u) for sp in cu.splines]
                cu.splines.clear()
                for pts, closed in old:
                    if len(pts) >= 2:
                        _rebuild_spline(cu, kind, pts, closed)
            done += 1
        return {'FINISHED'} if done else {'CANCELLED'}


class DESSIN_MT_ctx_polyline(bpy.types.Menu):
    bl_idname = "DESSIN_MT_ctx_polyline"
    bl_label = "Polyline"

    def draw(self, context):
        layout = self.layout
        layout.operator("object.editmode_toggle", text="Edit Polyline", icon='EDITMODE_HLT')
        layout.separator()
        layout.operator(DESSIN_OT_poly_edit.bl_idname, text="Close").action = 'CLOSE'
        layout.operator(DESSIN_OT_poly_edit.bl_idname, text="Open").action = 'OPEN'
        layout.separator()
        layout.operator(DESSIN_OT_join.bl_idname, text="Join")
        layout.operator(DESSIN_OT_poly_edit.bl_idname, text="Reverse").action = 'REVERSE'
        layout.operator(DESSIN_OT_poly_edit.bl_idname, text="Width").action = 'WIDTH'
        layout.separator()
        layout.operator(DESSIN_OT_poly_edit.bl_idname, text="Curve Fit").action = 'CURVE_FIT'
        layout.operator(DESSIN_OT_poly_edit.bl_idname, text="Spline Fit").action = 'SPLINE_FIT'
        layout.operator(DESSIN_OT_poly_edit.bl_idname, text="Decurve").action = 'DECURVE'


def ctx_extra_items(layout, context):
    if context.mode == 'OBJECT' and any(o.type in {'CAMERA', 'LIGHT'} for o in context.selected_objects):
        layout.operator(DESSIN_OT_track_to.bl_idname, text="Track To (aim at active object)", icon='TRACKER')
        layout.operator(DESSIN_OT_track_to.bl_idname, text="Clear Track To", icon='X').clear = True
    if context.mode == 'OBJECT':
        layout.menu(DESSIN_MT_ctx_material.bl_idname, icon='MATERIAL')
    layout.menu(DESSIN_MT_ctx_select.bl_idname, icon='RESTRICT_SELECT_OFF')


def menu_ctx_extra(self, context):
    """Sous-menus Material et Select à la fin d'un menu contextuel (mode édition, ou secours)."""
    self.layout.separator()
    ctx_extra_items(self.layout, context)


class _CopyHookLayout:
    """Enveloppe du layout du clic droit : nos menus s'insèrent juste avant « Copy Objects »."""

    def __init__(self, layout, context, state):
        object.__setattr__(self, "_layout", layout)
        object.__setattr__(self, "_context", context)
        object.__setattr__(self, "_state", state)

    def operator(self, idname, *args, **kwargs):
        lay = object.__getattribute__(self, "_layout")
        state = object.__getattribute__(self, "_state")
        if idname == "view3d.copybuffer" and not state["done"]:
            state["done"] = True
            ctx_extra_items(lay, object.__getattribute__(self, "_context"))
            lay.separator()
        return lay.operator(idname, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_layout"), name)

    def __setattr__(self, name, value):
        setattr(object.__getattribute__(self, "_layout"), name, value)


class _MenuSelf:
    """Faux « self » du menu d'origine : tout est délégué sauf `layout`."""

    def __init__(self, menu, layout):
        object.__setattr__(self, "_menu", menu)
        object.__setattr__(self, "layout", layout)

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_menu"), name)


_CTX_DRAW = {"orig": None}


def install_ctx_object_menu():
    cls = bpy.types.VIEW3D_MT_object_context_menu
    if _CTX_DRAW["orig"] is not None:
        return
    orig = cls.draw
    _CTX_DRAW["orig"] = orig

    def draw(self, context):
        state = {"done": False}
        if context.mode == 'OBJECT' and any(o.type == 'CURVE' for o in context.selected_objects):
            self.layout.menu(DESSIN_MT_ctx_polyline.bl_idname, icon='CURVE_DATA')      # « Polyline » tout en haut du menu
            self.layout.separator()
        proxy = _CopyHookLayout(self.layout, context, state)
        orig(_MenuSelf(self, proxy), context)
        if not state["done"]:                  # « Copy Objects » introuvable (autre version de Blender) : à la fin
            menu_ctx_extra(self, context)
    if hasattr(orig, "_draw_funcs"):      # Blender garde ici la liste des append / prepend du menu
        draw._draw_funcs = orig._draw_funcs
    cls.draw = draw


def uninstall_ctx_object_menu():
    orig = _CTX_DRAW["orig"]
    if orig is not None:
        try:
            bpy.types.VIEW3D_MT_object_context_menu.draw = orig
        except (AttributeError, TypeError):
            pass
        _CTX_DRAW["orig"] = None


def _late_imports():
    """Noms définis dans des modules chargés après celui-ci : ils ne servent qu'à l'exécution des outils."""
    global DESSIN_OT_join, wire_graph
    from .trim import wire_graph
    from .join_explode import DESSIN_OT_join
