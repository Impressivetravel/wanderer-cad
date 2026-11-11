"""Wanderer CAD : Journal de commande, plan de construction (CPlane)."""

import bpy
import gpu
import math
from bpy_extras.view3d_utils import region_2d_to_origin_3d, region_2d_to_vector_3d
from gpu_extras.batch import batch_for_shader
from mathutils import Vector, geometry

from .core import (
    CP_WORLD, NAV_TYPES, addon_globals, cp_frame, cp_redo, cp_set, cp_state, cp_undo, drawing_axis, plane_axes,
    plane_origin, pref, tr_text,
)
from .drawing import (
    _same_region, find_window_region, get_shader, main_window_region, project_px, px_scale, region_rv3d,
)
from .selection import BOX_BLUE, BOX_ORANGE, ray_cast_opaque
from .toolbar import _SUBD_EDIT_LIST, _SUBD_OBJ_LIST
from .views import _CMD


def cmd_log(txt):
    _CMD["log"].append(txt)
    del _CMD["log"][:-50]


def set_prompt(area, txt):
    """Invite de la commande en cours : dans la barre de commande (ou, si elle est masquée, dans l'en-tête de la vue)."""
    try:
        key = area.as_pointer()
        if not pref("cmd_line"):
            area.header_text_set(tr_text(txt) if txt else txt)
            return
        if txt:
            _CMD["prompt"][key] = txt
            if key not in _CMD["cleared"]:
                _CMD["cleared"].add(key)
                area.header_text_set(None)       # l'en-tête (onglets de vues) reste visible
        else:
            _CMD["prompt"].pop(key, None)
            _CMD["cleared"].discard(key)
            area.header_text_set(None)
        area.tag_redraw()
    except (ReferenceError, AttributeError, RuntimeError):
        pass


def cmd_tool_classes():
    seen, out = set(), []
    for name, c in list(addon_globals().items()):
        if (name.startswith("DESSIN_TT_") and isinstance(c, type) and issubclass(c, bpy.types.WorkSpaceTool)
                and getattr(c, "bl_idname", "").startswith("dessin.") and c.bl_idname not in seen and c.bl_label):
            seen.add(c.bl_idname)
            out.append(c)
    return out


def cmd_tool_class(tool_id):
    for c in cmd_tool_classes():
        if c.bl_idname == tool_id:
            return c
    for grp in _SUBD_OBJ_LIST + _SUBD_EDIT_LIST:      # outils de commandes SubD (pas dans la liste des commandes : déjà des actions)
        for c in grp:
            if c.bl_idname == tool_id:
                return c
    return None


def cmd_clean_label(label):
    import re
    return re.sub(r"\s*\(.*?\)", "", label).strip()


def _act_op(op, **kw):
    def run(context):
        mod, name = op.split(".")
        getattr(getattr(bpy.ops, mod), name)(**kw)
        return ""
    return run


def _act_shading(kind):
    def run(context):
        context.area.spaces.active.shading.type = kind
        return ""
    return run


def _act_toggle(path):
    def run(context):
        obj = context.area.spaces.active
        for part in path[:-1]:
            obj = getattr(obj, part)
        setattr(obj, path[-1], not getattr(obj, path[-1]))
        return ""
    return run


def _act_origin(context):
    context.scene.cursor.location = (0.0, 0.0, 0.0)
    return "3D cursor moved to the origin"


def _sel_similar_object(kind):
    return {"MATERIAL": ("select_linked", {"type": 'MATERIAL'}), "TYPE": ("select_grouped", {"type": 'TYPE'}),
            "COLLECTION": ("select_grouped", {"type": 'COLLECTION'}), "HIERARCHY": ("select_grouped", {"type": 'CHILDREN_RECURSIVE'})}.get(kind)


def _act_select_similar(kind):
    """Select Similar selon le mode : objets partageant un matériau / type / collection, ou faces semblables en mode édition."""
    def run(context):
        if context.mode == 'EDIT_MESH':
            et = {"MATERIAL": 'MATERIAL', "AREA": 'AREA', "NORMAL": 'NORMAL', "SIDES": 'POLYGON_SIDES'}.get(kind)
            if et is None:
                raise RuntimeError("not available in Edit Mode")
            if not context.tool_settings.mesh_select_mode[2]:
                bpy.ops.mesh.select_mode(type='FACE')           # ces critères concernent les faces
            bpy.ops.mesh.select_similar(type=et, compare='EQUAL')
            return "Select Similar " + kind.title()
        spec = _sel_similar_object(kind)
        if spec is None:
            raise RuntimeError("available in Edit Mode only")
        getattr(bpy.ops.object, spec[0])(**spec[1])
        return "Select Similar " + kind.title()
    return run


def _act_select_similar_menu(context):
    """Ouvre le menu des critères (comme les options de SelSimilar dans Rhino)."""
    if context.mode == 'EDIT_MESH':
        bpy.ops.mesh.select_similar('INVOKE_DEFAULT')
    else:
        bpy.ops.object.select_linked('INVOKE_DEFAULT')
    return ""


def _act_select_linked(context):
    if context.mode == 'EDIT_MESH':
        bpy.ops.mesh.select_linked()
    else:
        bpy.ops.object.select_linked('INVOKE_DEFAULT')
    return ""


def _act_region(attr):
    def run(context):
        sp = context.area.spaces.active
        setattr(sp, attr, not getattr(sp, attr))
        return ""
    return run


# ---- CPlane : plan de construction personnalisé (face, 3 points, vertical, vue, monde, élévation, annuler / rétablir) ----
_CP_DRAW = {"handle": None}


def _cp_nice(x):
    """Pas de grille « rond » (1, 2, 5 x 10^k) proche de x."""
    if x <= 0:
        return 1.0
    e = math.floor(math.log10(x))
    f = x / 10.0 ** e
    return (1.0 if f < 1.5 else 2.0 if f < 3.5 else 5.0 if f < 7.5 else 10.0) * 10.0 ** e


def cplane_draw_cb():
    """Petite grille dans le plan de construction personnalisé de la zone 3D (rien s'il n'y en a pas)."""
    try:
        rv3d = bpy.context.region_data
        if rv3d is None:
            return
        st = cp_state(rv3d)
        if not st or st["cur"] is None:
            return
        o, x, y, _z = st["cur"]
        step = _cp_nice(max(rv3d.view_distance, 0.05) / 14.0)
        half = step * 8
        shader = get_shader('3D')
        gpu.state.blend_set('ALPHA')
        gpu.state.line_width_set(1.0)
        shader.bind()
        pts = []
        for i in range(-8, 9):
            if i == 0:
                continue
            pts += [o + x * (i * step) - y * half, o + x * (i * step) + y * half,
                    o + y * (i * step) - x * half, o + y * (i * step) + x * half]
        shader.uniform_float("color", (BOX_ORANGE[0], BOX_ORANGE[1], BOX_ORANGE[2], 0.28))
        batch_for_shader(shader, 'LINES', {"pos": [tuple(p) for p in pts]}).draw(shader)
        gpu.state.line_width_set(2.0)
        for d, col in ((x, (0.95, 0.25, 0.25, 0.8)), (y, (0.3, 0.85, 0.3, 0.8))):
            shader.uniform_float("color", col)
            batch_for_shader(shader, 'LINES', {"pos": [tuple(o - d * half), tuple(o + d * half)]}).draw(shader)
        gpu.state.line_width_set(1.0)
        gpu.state.blend_set('NONE')
    except (ReferenceError, AttributeError, RuntimeError, TypeError):
        pass


def cp_current_rv3d(context):
    area = context.area
    if area is None or area.type != 'VIEW_3D':
        area = next((a for a in context.window.screen.areas if a.type == 'VIEW_3D'), None) if context.window else None
    if area is None:
        return None
    return area.spaces.active.region_3d


def cp_pick(context, region, rv3d, mx, my):
    """Point 3D sous le curseur : sommet proche d'une face visée, sinon point visé, sinon plan de construction courant."""
    coord = Vector((mx, my))
    ro = region_2d_to_origin_3d(region, rv3d, coord)
    rv = region_2d_to_vector_3d(region, rv3d, coord)
    try:
        ok, loc, _nor, idx, obj, mat = ray_cast_opaque(context, ro, rv)
    except (RuntimeError, TypeError, ValueError):
        ok = False
    if ok:
        best, bd = None, 14.0 * px_scale()
        try:
            me = obj.evaluated_get(context.evaluated_depsgraph_get()).data
            for vi in me.polygons[idx].vertices:
                w = mat @ me.vertices[vi].co
                sp = project_px(rv3d, region, w)
                if sp is not None and (sp - coord).length < bd:
                    best, bd = w, (sp - coord).length
        except (AttributeError, IndexError, RuntimeError, ReferenceError):
            pass
        return (best if best is not None else loc), True
    axis = drawing_axis(rv3d)
    n = plane_axes(axis)[2]
    hit = geometry.intersect_line_plane(ro, ro + rv, plane_origin(axis), n)
    return hit, False


def cp_pick_cb(op):
    if not _same_region(op) or not op.pts and op.hover is None:
        return
    shader = get_shader('3D')
    gpu.state.blend_set('ALPHA')
    gpu.state.point_size_set(9.0)
    shader.bind()
    shader.uniform_float("color", (BOX_ORANGE[0], BOX_ORANGE[1], BOX_ORANGE[2], 1.0))
    if op.pts:
        batch_for_shader(shader, 'POINTS', {"pos": [tuple(p) for p in op.pts]}).draw(shader)
        seq = list(op.pts) + ([op.hover] if op.hover is not None else [])
        if len(seq) >= 2:
            gpu.state.line_width_set(1.5)
            batch_for_shader(shader, 'LINE_STRIP', {"pos": [tuple(p) for p in seq]}).draw(shader)
            gpu.state.line_width_set(1.0)
    if op.hover is not None:
        shader.uniform_float("color", (BOX_BLUE[0], BOX_BLUE[1], BOX_BLUE[2], 1.0))
        batch_for_shader(shader, 'POINTS', {"pos": [tuple(op.hover)]}).draw(shader)
    gpu.state.point_size_set(1.0)
    gpu.state.blend_set('NONE')


class DESSIN_OT_cplane(bpy.types.Operator):
    bl_idname = "dessin.cplane"
    bl_label = "CPlane"
    bl_description = ("Sets the construction plane the drawing tools work on: click a face to align the plane with it, "
                      "or press 3 (three points), V (vertical plane), W (back to the world plane), U (undo the plane)")
    bl_options = {'REGISTER'}

    mode: bpy.props.EnumProperty(name="Mode", default='OBJECT',
                                 items=(('OBJECT', "Object", "Click a face"), ('3PT', "3 Points", "Origin, X axis, Y axis"),
                                        ('VERT', "Vertical", "Two points: a plane standing on the line, perpendicular to the current plane")))

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D'

    def prompt(self):
        txt = {'OBJECT': "CPlane: click a face to align the plane with it  |  3: three points  V: vertical  W: world plane  U: undo plane  Esc: cancel",
               '3PT': ("CPlane 3 points: origin" if not self.pts else "CPlane 3 points: point on the X axis" if len(self.pts) == 1
                       else "CPlane 3 points: point on the Y side") + "  |  Esc: cancel",
               'VERT': ("CPlane vertical: first point of the line" if not self.pts else "CPlane vertical: second point of the line") + "  |  Esc: cancel"}[self.mode]
        set_prompt(self.area, txt)

    def invoke(self, context, event):
        self.area = context.area
        self.region = find_window_region(self.area, event.mouse_x, event.mouse_y) or main_window_region(self.area)
        if self.region is None:
            return {'CANCELLED'}
        self.rv3d = region_rv3d(self.region, self.area)
        self.pts = []
        self.hover = None
        self._h = bpy.types.SpaceView3D.draw_handler_add(cp_pick_cb, (self,), 'WINDOW', 'POST_VIEW')
        self.prompt()
        context.window_manager.modal_handler_add(self)
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

    def done(self, context, frame, msg):
        cp_set(self.rv3d, frame)
        self.cleanup()
        cmd_log(msg)
        return {'FINISHED'}

    def face_frame(self, context, mx, my):
        coord = Vector((mx, my))
        ro = region_2d_to_origin_3d(self.region, self.rv3d, coord)
        rv = region_2d_to_vector_3d(self.region, self.rv3d, coord)
        try:
            ok, loc, nor, _i, _o, _m = ray_cast_opaque(context, ro, rv)
        except (RuntimeError, TypeError, ValueError):
            ok = False
        if not ok:
            return None
        z = Vector(nor).normalized()
        if z.dot(rv) > 0:
            z = -z                                       # la normale regarde vers nous
        up = Vector((0.0, 0.0, 1.0))
        x = Vector((1.0, 0.0, 0.0)) if abs(z.dot(up)) > 0.999 else up.cross(z)    # face verticale : X horizontal
        return cp_frame(loc, x, z.cross(x))

    def modal(self, context, event):
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self.cleanup()
            return {'CANCELLED'}
        if event.type in NAV_TYPES or event.type.startswith(('NUMPAD', 'TRACKPAD')):
            return {'PASS_THROUGH'}
        if event.value == 'PRESS' and event.type in {'THREE', 'V', 'W', 'O', 'U'} and not (event.ctrl or event.alt or event.oskey):
            if event.type == 'W':
                return self.done(context, None, "CPlane: world plane")
            if event.type == 'U':
                msg = "CPlane: previous plane" if cp_undo(self.rv3d) else "CPlane: nothing to undo"
                self.cleanup()
                cmd_log(msg)
                return {'FINISHED'}
            self.mode = {'THREE': '3PT', 'V': 'VERT', 'O': 'OBJECT'}[event.type]
            self.pts = []
            self.prompt()
            return {'RUNNING_MODAL'}
        region = find_window_region(self.area, event.mouse_x, event.mouse_y)
        if region is None:
            return {'RUNNING_MODAL'}
        mx, my = event.mouse_x - region.x, event.mouse_y - region.y
        if event.type == 'MOUSEMOVE':
            if self.mode != 'OBJECT':
                self.hover, _hit = cp_pick(context, region, self.rv3d, mx, my)
                self.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            self.region = region
            if self.mode == 'OBJECT':
                fr = self.face_frame(context, mx, my)
                if fr is None:
                    cmd_log("CPlane: click on a face (or press 3 / V)")
                    return {'RUNNING_MODAL'}
                return self.done(context, fr, "CPlane: aligned with the face")
            p, _hit = cp_pick(context, region, self.rv3d, mx, my)
            if p is None:
                return {'RUNNING_MODAL'}
            self.pts.append(p.copy())
            need = 3 if self.mode == '3PT' else 2
            if len(self.pts) < need:
                self.prompt()
                self.area.tag_redraw()
                return {'RUNNING_MODAL'}
            if self.mode == '3PT':
                x = self.pts[1] - self.pts[0]
                fr = cp_frame(self.pts[0], x, self.pts[2] - self.pts[0]) if x.length > 1e-9 else None
            else:
                ax = drawing_axis(self.rv3d)
                n = plane_axes(ax)[2]
                x = self.pts[1] - self.pts[0]
                fr = cp_frame(self.pts[0], x, n) if x.length > 1e-9 else None
            if fr is None:
                cmd_log("CPlane: the points are aligned, pick them again")
                self.pts = []
                self.prompt()
                return {'RUNNING_MODAL'}
            return self.done(context, fr, "CPlane: " + ("3 points" if self.mode == '3PT' else "vertical plane"))
        return {'RUNNING_MODAL'}


class DESSIN_OT_cplane_elevation(bpy.types.Operator):
    bl_idname = "dessin.cplane_elevation"
    bl_label = "CPlane Elevation"
    bl_description = "Moves the construction plane along its normal by a distance (keeps its orientation)"
    bl_options = {'REGISTER'}

    distance: bpy.props.FloatProperty(name="Distance", default=0.0, subtype='DISTANCE', unit='LENGTH')

    @classmethod
    def poll(cls, context):
        return cp_current_rv3d(context) is not None

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=260)

    def execute(self, context):
        rv3d = cp_current_rv3d(context)
        if rv3d is None:
            return {'CANCELLED'}
        st = cp_state(rv3d)
        if st is not None and st["cur"] is not None:
            o, x, y, z = st["cur"]
        else:                                    # pas de plan personnalisé : on part du plan de la vue (XY, Front, Right...)
            ax = drawing_axis(rv3d)
            u, v, _n = plane_axes(ax)
            o, x, y, z = cp_frame(plane_origin(ax), u, v)
        cp_set(rv3d, (o + z * self.distance, x, y, z))
        cmd_log("CPlane: moved along its normal")
        return {'FINISHED'}


def cp_apply_named(context, name):
    rv3d = cp_current_rv3d(context)
    if rv3d is None:
        return "No 3D view"
    if name == 'View':
        rot = rv3d.view_rotation
        st = cp_state(rv3d)
        o = st["cur"][0] if st and st["cur"] is not None else Vector((0.0, 0.0, 0.0))
        cp_set(rv3d, (o, rot @ Vector((1, 0, 0)), rot @ Vector((0, 1, 0)), rot @ Vector((0, 0, 1))))
        return "CPlane: parallel to the view"
    spec = CP_WORLD[name]
    cp_set(rv3d, cp_frame(*spec) if spec is not None else None)
    return "CPlane: world " + name.lower()


def _act_cplane_named(name):
    def run(context):
        return cp_apply_named(context, name)
    return run


def _act_cplane_undo(context):
    rv3d = cp_current_rv3d(context)
    return "CPlane: previous plane" if rv3d is not None and cp_undo(rv3d) else "CPlane: nothing to undo"


def _act_cplane_redo(context):
    rv3d = cp_current_rv3d(context)
    return "CPlane: next plane" if rv3d is not None and cp_redo(rv3d) else "CPlane: nothing to redo"


def _act_cplane_mode(mode):
    def run(context):
        bpy.ops.dessin.cplane('INVOKE_DEFAULT', mode=mode)
        return ""
    return run


def _late_imports():
    pass
