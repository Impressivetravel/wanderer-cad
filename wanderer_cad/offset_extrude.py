"""Wanderer CAD : Offset Surface et Extrude (mode édition)."""

import bmesh
import bpy
import gpu
import math
import numpy as np
from bpy_extras.view3d_utils import region_2d_to_origin_3d, region_2d_to_vector_3d
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

from .core import IDLE_FALLBACK, IDLE_TOOL, fmt_typed, last_typed, pref, unit_info
from .drawing import area_over_ui, find_window_region, get_shader, project_px, px_scale
from .base import DessinBase
from .selection import ray_cast_opaque
from .gumball import DESSIN_OT_gumball_extrude, GumballBase


# --------------------------------------------------------------------------
# Offset Surface (objet) et Extrude (mode édition)
# --------------------------------------------------------------------------

def offset_coords(obj, dist):
    """(coordonnées locales d'origine, coordonnées décalées de dist monde le long des normales).
    Chaque sommet est placé à la distance dist de toutes les faces qui l'entourent (angles vifs respectés)."""
    me = obj.data
    nv, npoly = len(me.vertices), len(me.polygons)
    co = np.empty(nv * 3)
    me.vertices.foreach_get('co', co)
    co = co.reshape(-1, 3)
    fn = np.empty(npoly * 3)
    me.polygons.foreach_get('normal', fn)
    fn = fn.reshape(-1, 3)
    lt = np.empty(npoly, dtype=np.int64)
    me.polygons.foreach_get('loop_total', lt)
    lv = np.empty(len(me.loops), dtype=np.int64)
    me.loops.foreach_get('vertex_index', lv)
    M = np.array(obj.matrix_world.to_3x3(), dtype=np.float64)
    Minv = np.linalg.inv(M)
    fnw = fn @ Minv          # normale monde = (M^-1)^T n
    ln = np.linalg.norm(fnw, axis=1)
    fnw = fnw / np.where(ln > 1e-12, ln, 1.0)[:, None]
    N = fnw[np.repeat(np.arange(npoly), lt)]
    A = np.zeros((nv, 3, 3))
    b = np.zeros((nv, 3))
    np.add.at(A, lv, N[:, :, None] * N[:, None, :])
    np.add.at(b, lv, N)
    dw = (np.linalg.pinv(A, rcond=1e-3) @ b[:, :, None])[:, :, 0] * dist
    length = np.linalg.norm(dw, axis=1)
    cap = 4.0 * abs(dist)
    dw *= np.where(length > cap, cap / np.where(length > 1e-12, length, 1.0), 1.0)[:, None]
    return co, co + dw @ Minv.T


def offset_surface_mesh(obj, dist, solid, both=False):
    """Nouveau maillage : la surface de obj décalée de dist (signe = sens). solid : fermé en épaisseur ;
    both + solid : épaisseur centrée sur la surface (de -|dist| à +|dist|)."""
    me = obj.data
    if solid and both:
        co, newco = offset_coords(obj, abs(dist))
        _c, co = offset_coords(obj, -abs(dist))
        dist = abs(dist)
    else:
        co, newco = offset_coords(obj, dist)
    if not solid:
        out = me.copy()
        out.name = "Offset " + me.name
        out.vertices.foreach_set('co', newco.ravel())
        out.update()
        return out
    bm = bmesh.new()
    vo = [bm.verts.new(c) for c in co]
    vn = [bm.verts.new(c) for c in newco]
    outer, inner = (vn, vo) if dist >= 0 else (vo, vn)
    count = {}
    for p in me.polygons:
        vs = list(p.vertices)
        for k in range(len(vs)):
            a_, b_ = vs[k], vs[(k + 1) % len(vs)]
            count.setdefault((min(a_, b_), max(a_, b_)), []).append((a_, b_))
        try:
            f1 = bm.faces.new([outer[i] for i in vs])
            f2 = bm.faces.new([inner[i] for i in reversed(vs)])
            f1.material_index = f2.material_index = p.material_index
        except ValueError:
            pass
    for lst in count.values():
        if len(lst) != 1:
            continue
        a_, b_ = lst[0]
        quad = [vn[b_], vn[a_], vo[a_], vo[b_]] if dist >= 0 else [vo[b_], vo[a_], vn[a_], vn[b_]]
        try:
            bm.faces.new(quad)
        except ValueError:
            pass
    out = bpy.data.meshes.new("Offset " + me.name)
    bm.to_mesh(out)
    bm.free()
    for m in me.materials:
        out.materials.append(m)
    return out


def offset_arrows(targets, limit=8):
    """[(position monde, normale monde)] : quelques flèches réparties sur les plus grandes faces."""
    cands = []
    for obj in targets:
        me = obj.data
        n = len(me.polygons)
        if not n:
            continue
        areas = np.empty(n)
        me.polygons.foreach_get('area', areas)
        cen = np.empty(n * 3)
        me.polygons.foreach_get('center', cen)
        nor = np.empty(n * 3)
        me.polygons.foreach_get('normal', nor)
        cen, nor = cen.reshape(-1, 3), nor.reshape(-1, 3)
        idx = np.where(areas >= 0.3 * areas.max())[0]
        if len(idx) > 300:
            idx = idx[::len(idx) // 300 + 1]
        M = np.array(obj.matrix_world, dtype=np.float64)
        Mi = np.linalg.inv(M[:3, :3])
        pw = cen[idx] @ M[:3, :3].T + M[:3, 3]
        nw = nor[idx] @ Mi
        nw /= np.maximum(np.linalg.norm(nw, axis=1), 1e-12)[:, None]
        cands.extend(zip(pw, nw))
    if not cands:
        return []
    chosen = [0]
    P = np.array([c[0] for c in cands])
    dmin = np.linalg.norm(P - P[0], axis=1)
    while len(chosen) < min(limit, len(cands)):
        j = int(np.argmax(dmin))
        if dmin[j] < 1e-9:
            break
        chosen.append(j)
        dmin = np.minimum(dmin, np.linalg.norm(P - P[j], axis=1))
    return [(Vector(cands[j][0]), Vector(cands[j][1])) for j in chosen]


_OFFSET_ACTIVE = []


def back_to_idle():
    """Retour à Select / Move (Échap dans un outil de la barre)."""
    if not pref("auto_idle"):
        return
    for name in (IDLE_TOOL, IDLE_FALLBACK):
        try:
            bpy.ops.wm.tool_set_by_id(name=name)
            return
        except (RuntimeError, TypeError):
            continue


def draw_offset_cb(op):
    ctx = bpy.context
    try:
        if ctx.area != op.area or ctx.region_data is None:
            return
    except ReferenceError:
        return
    if op not in _OFFSET_ACTIVE:
        return
    rv3d, region = ctx.region_data, ctx.region
    shader = get_shader('2D')
    sc = px_scale()
    gpu.state.blend_set('ALPHA')
    both = op.both
    items = [(i, p, n * sg) for i, (p, n) in enumerate(op.arrows) for sg in ((1.0, -1.0) if both else (op.sign,))]
    for i, p, d in items:
        a = project_px(rv3d, region, p)
        b = project_px(rv3d, region, p + d * op.arrow_len)
        if a is None or b is None:
            continue
        hot = (i == op.hover)
        col = (1.0, 1.0, 0.4, 1.0) if hot else (1.0, 0.55, 0.1, 1.0)
        gpu.state.line_width_set((4.0 if hot else 2.5) * sc)
        shader.bind()
        shader.uniform_float("color", col)
        batch_for_shader(shader, 'LINES', {"pos": [tuple(a), tuple(b)]}).draw(shader)
        v = b - a
        if v.length > 2.0:
            v.normalize()
            h = 11.0 * sc
            perp = Vector((-v.y, v.x))
            tri = [tuple(b + v * h * 0.6), tuple(b - v * h * 0.6 + perp * h * 0.55), tuple(b - v * h * 0.6 - perp * h * 0.55)]
            batch_for_shader(shader, 'TRIS', {"pos": tri}).draw(shader)
    gpu.state.line_width_set(1.0)
    gpu.state.blend_set('NONE')


class DESSIN_OT_offset_surface(bpy.types.Operator):
    bl_idname = "dessin.offset_surface"
    bl_label = "Offset Surface"
    bl_description = ("Offsets a surface (or a whole object) along its normals, like OffsetSrf: click it (or select it first), "
                      "click an arrow to flip the direction, type the distance, Enter or Space to validate")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and context.area is not None and context.area.type == 'VIEW_3D'

    def pick_targets(self, context, event):
        region = find_window_region(context.area, event.mouse_x, event.mouse_y)
        hit = None
        if region is not None:
            rv3d = context.area.spaces.active.region_3d
            m = Vector((event.mouse_x - region.x, event.mouse_y - region.y))
            try:
                ro = region_2d_to_origin_3d(region, rv3d, m)
                rv = region_2d_to_vector_3d(region, rv3d, m)
                ok, _loc, _nor, _idx, ob, _mat = ray_cast_opaque(context, ro, rv, True)
                hit = ob if ok and ob is not None and ob.type == 'MESH' else None
            except (AttributeError, RuntimeError, TypeError):
                hit = None
        if hit is not None:
            return [hit]
        return [o for o in context.selected_objects if o.type == 'MESH' and len(o.data.polygons)]

    def header(self, context):
        unit = self.unit_label
        d = (self.typed + "_") if self.typed else f"{self.dist / self.unit_f:.4g}"
        txt = (f"Offset Surface: {d} {unit}   |   direction: {'normal' if self.sign > 0 else 'opposite'}   |   "
               f"S: solid {'ON' if self.solid else 'off'}   B: both sides {'ON' if self.both else 'off'}   X: delete input {'ON' if self.delete else 'off'}   "
               f"|   click an arrow (or F): flip   type the distance   Enter / Space: validate   Esc: cancel").strip()
        try:
            set_prompt(context.area, txt)
            context.area.tag_redraw()
        except (AttributeError, ReferenceError):
            pass

    def rebuild(self):
        self.remove_created()
        for obj in self.targets:
            sides = (1.0, -1.0) if (self.both and not self.solid) else (self.sign,)
            for sd in sides:
                me = offset_surface_mesh(obj, sd * self.dist, self.solid, self.both)
                new = bpy.data.objects.new("Offset " + obj.name, me)
                new.matrix_world = obj.matrix_world.copy()
                cols = obj.users_collection or [bpy.context.scene.collection]
                for c in cols:
                    c.objects.link(new)
                self.created.append((obj, new))

    def remove_created(self):
        for _old, new in self.created:
            try:
                me = new.data
                bpy.data.objects.remove(new)
                if me is not None and me.users == 0:
                    bpy.data.meshes.remove(me)
            except (ReferenceError, RuntimeError):
                pass
        self.created = []

    def abort(self):
        """Interrompt cette instance (une nouvelle commande démarre)."""
        self.remove_created()
        try:
            self.finish_ui(bpy.context)
        except (AttributeError, ReferenceError):
            pass

    def finish_ui(self, context):
        if self in _OFFSET_ACTIVE:
            _OFFSET_ACTIVE.remove(self)
        if self._handle is not None:
            try:
                bpy.types.SpaceView3D.draw_handler_remove(self._handle, 'WINDOW')
            except (ValueError, RuntimeError):
                pass
            self._handle = None
        try:
            set_prompt(self.area, None)
            self.area.tag_redraw()
        except (AttributeError, ReferenceError):
            pass

    def invoke(self, context, event):
        self._handle = None
        self.targets = self.pick_targets(context, event)
        if not self.targets:
            self.report({'INFO'}, "Select a surface or an object to offset (or click it)")
            return {'CANCELLED', 'PASS_THROUGH'}
        st = context.scene.dessin
        self.area = context.area
        self.unit_f, self.unit_label = unit_info(context.scene)
        self.dist = max(st.offset_surf_dist, 1e-6)
        self.solid = st.offset_surf_solid
        self.both = st.offset_surf_both
        self.delete = st.offset_surf_delete
        self.sign = 1.0
        self.typed = ""
        self.hover = -1
        self.created = []
        for other in list(_OFFSET_ACTIVE):          # une seule instance à la fois (pas de flèches fantômes)
            other.abort()
        _OFFSET_ACTIVE.append(self)
        self.arrows = offset_arrows(self.targets)
        diag = 0.0
        for o in self.targets:
            dim = o.dimensions
            diag = max(diag, math.sqrt(dim.x ** 2 + dim.y ** 2 + dim.z ** 2))
        self.arrow_len = max(0.15 * diag, 1e-3)
        self.rebuild()
        self._handle = bpy.types.SpaceView3D.draw_handler_add(draw_offset_cb, (self,), 'WINDOW', 'POST_PIXEL')
        context.window_manager.modal_handler_add(self)
        self.header(context)
        return {'RUNNING_MODAL'}

    def release_refs(self):
        """Plus aucune référence vers des objets Blender une fois la commande terminée (l'annulation les invalide)."""
        self.created = []
        self.targets = []
        self.arrows = []

    def cancel_all(self, context):
        self.remove_created()
        self.finish_ui(context)
        self.release_refs()
        return {'CANCELLED'}

    def commit(self, context):
        if not self.created or self.dist < 1e-9:
            return self.cancel_all(context)
        st = context.scene.dessin
        st.offset_surf_dist = self.dist
        st.offset_surf_solid = self.solid
        st.offset_surf_both = self.both
        st.offset_surf_delete = self.delete
        for o in context.view_layer.objects:
            o.select_set(False)
        last = None
        for _old, new in self.created:
            new.select_set(True)
            last = new
        if self.delete:
            for old in self.targets:
                try:
                    bpy.data.objects.remove(old)
                except (ReferenceError, RuntimeError):
                    pass
        if last is not None:
            context.view_layer.objects.active = last
        self.finish_ui(context)
        self.release_refs()
        return {'FINISHED'}

    def arrow_under(self, context, event):
        region = find_window_region(context.area, event.mouse_x, event.mouse_y)
        if region is None:
            return -1
        rv3d = context.area.spaces.active.region_3d
        m = Vector((event.mouse_x - region.x, event.mouse_y - region.y))
        best, best_d = -1, 16.0 * px_scale()
        for i, (p, n) in enumerate(self.arrows):
            a = project_px(rv3d, region, p)
            b = project_px(rv3d, region, p + n * self.sign * self.arrow_len)
            if a is None or b is None:
                continue
            ab = b - a
            t = 0.0 if ab.length < 1e-6 else max(0.0, min(1.0, (m - a).dot(ab) / ab.length_squared))
            d = (m - (a + ab * t)).length
            if d < best_d:
                best, best_d = i, d
        return best

    def sync_settings(self, context):
        st = context.scene.dessin
        if (st.offset_surf_solid != self.solid or st.offset_surf_delete != self.delete
                or st.offset_surf_both != self.both
                or (not self.typed and abs(st.offset_surf_dist - self.dist) > 1e-9)):
            self.solid, self.delete, self.both = st.offset_surf_solid, st.offset_surf_delete, st.offset_surf_both
            if not self.typed:
                self.dist = max(st.offset_surf_dist, 1e-6)
            self.rebuild()
            self.header(context)

    def modal(self, context, event):
        et = event.type
        if self.area is None or context.area is None:
            return self.cancel_all(context)
        if et in {'Z', 'Y'} and event.value == 'PRESS' and (event.ctrl or event.oskey):
            # Annuler / rétablir pendant la commande : on libère nos objets AVANT que Blender ne les remplace (sinon plantage)
            self.remove_created()
            self.finish_ui(context)
            self.release_refs()
            return {'CANCELLED', 'PASS_THROUGH'}
        tid = DessinBase.active_tool_id(context)
        if tid is not None and tid != "dessin.offset_surface_tool":
            self.remove_created()
            self.finish_ui(context)
            return {'CANCELLED', 'PASS_THROUGH'}
        if et in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            h = self.arrow_under(context, event)
            if h != self.hover:
                self.hover = h
                context.area.tag_redraw()
            self.sync_settings(context)
            return {'PASS_THROUGH'}
        if find_window_region(context.area, event.mouse_x, event.mouse_y) is None or area_over_ui(context.area, event.mouse_x, event.mouse_y):
            return {'PASS_THROUGH'}
        if event.value != 'PRESS':
            return {'RUNNING_MODAL'} if et == 'LEFTMOUSE' else {'PASS_THROUGH'}
        if et == 'ESC':
            r = self.cancel_all(context)
            back_to_idle()
            return r
        if et in {'RET', 'NUMPAD_ENTER', 'SPACE'}:
            return self.commit(context)
        if et == 'LEFTMOUSE':
            if event.alt or event.oskey:
                return {'PASS_THROUGH'}
            if self.arrow_under(context, event) >= 0:
                self.sign = -self.sign
                self.rebuild()
                self.header(context)
                context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        changed = False
        if et == 'F' and not event.ctrl:
            self.sign = -self.sign
            changed = True
        elif et == 'S' and not (event.ctrl or event.alt):
            context.scene.dessin.offset_surf_solid = self.solid = not self.solid
            changed = True
        elif et == 'B' and not (event.ctrl or event.alt):
            context.scene.dessin.offset_surf_both = self.both = not self.both
            changed = True
        elif et == 'X' and not (event.ctrl or event.alt):
            context.scene.dessin.offset_surf_delete = self.delete = not self.delete
        elif et == 'BACK_SPACE':
            self.typed = self.typed[:-1]
            changed = True
        elif event.unicode and event.unicode in "0123456789.,-" and not (event.ctrl or event.alt):
            ch = "." if event.unicode == "," else event.unicode
            if ch == '-':
                self.sign = -self.sign
            else:
                self.typed += ch
            changed = True
        else:
            return {'PASS_THROUGH'}
        if self.typed:
            try:
                self.dist = max(float(self.typed) * self.unit_f, 1e-6)
            except ValueError:
                pass
        if changed:
            self.rebuild()
        self.header(context)
        context.area.tag_redraw()
        return {'RUNNING_MODAL'}


class DESSIN_OT_extrude(GumballBase):
    bl_idname = "dessin.extrude"
    bl_label = "Extrude"
    bl_description = ("Extrudes the selected faces (or edges) along their normal: click, move the mouse (or type the "
                      "distance) and click / Enter / Space to validate")

    kind = 'MOVE'
    axis = 0

    NO_COPY = True
    setup_selection = DESSIN_OT_gumball_extrude.setup_selection
    drop_backups = DESSIN_OT_gumball_extrude.drop_backups
    label = DESSIN_OT_gumball_extrude.label
    cancel_all = DESSIN_OT_gumball_extrude.cancel_all
    commit = DESSIN_OT_gumball_extrude.commit

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and context.area is not None and context.area.type == 'VIEW_3D'

    def header(self, context):
        if self.mode == 'type':
            txt = f"{self.label()}   |   type the distance: {self.typed or '_'} {self.unit_label}   |   Enter / Space / click: apply   Esc: cancel"
        else:
            lv = last_typed((self.bl_idname, self.kind))
            ent = "click: apply" if lv is None else f"click: apply   Enter / Space: {fmt_typed(lv / self.unit_f)} (last value)"
            txt = f"{self.label()}   |   move the mouse, or type the distance   |   {ent}   Esc: cancel"
            if lv is None:
                txt = f"{self.label()}   |   move the mouse, or type the distance   |   click / Enter / Space: apply   Esc: cancel"
        try:
            set_prompt(context.area, txt)
        except (AttributeError, ReferenceError):
            pass

    def invoke(self, context, event):
        if context.region is None or context.region_data is None:
            return {'CANCELLED', 'PASS_THROUGH'}
        if not self.setup_selection(context):
            self.report({'INFO'}, "Select faces or edges to extrude")
            return {'CANCELLED', 'PASS_THROUGH'}
        self.bu = self.dir.orthogonal().normalized()
        self.bv = self.dir.cross(self.bu)
        self.unit_f, self.unit_label = unit_info(context.scene)
        self.press = self.mouse(context, event)
        self.mode = 'follow'
        self.typed = ''
        self.uniform = False
        self.value = 0.0
        self.acc = 0.0
        s0 = self.sample(context, event)
        if s0 is None:
            return self.cancel_all(context)
        self.ref = s0
        self.last = s0
        context.window_manager.modal_handler_add(self)
        self.header(context)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        et = event.type
        if et in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            if self.mode == 'follow':
                self.value = self.value_from_sample(self.sample(context, event), event.shift)
                self.apply(self.value)
                self.header(context)
            return {'RUNNING_MODAL'}
        if et == 'LEFTMOUSE':
            if event.alt or event.oskey:
                return {'PASS_THROUGH'}
            if event.value == 'PRESS':
                return self.commit(context)
            if event.value == 'RELEASE' and (self.mouse(context, event) - self.press).length > 5.0 * px_scale():
                return self.commit(context)     # on a glissé : le relâchement valide
            return {'RUNNING_MODAL'}
        if event.value == 'PRESS':
            if et in {'ESC', 'RIGHTMOUSE'}:
                r = self.cancel_all(context)
                if et == 'ESC':
                    back_to_idle()
                return r
            if et in {'RET', 'NUMPAD_ENTER', 'SPACE'}:
                self.enter_last()
                return self.commit(context)
            if et == 'BACK_SPACE' and self.typed:
                self.typed = self.typed[:-1]
            elif event.unicode and event.unicode in "0123456789.,-" and not (event.ctrl or event.alt):
                ch = "." if event.unicode == "," else event.unicode
                if ch == '-':
                    self.typed = self.typed[1:] if self.typed.startswith('-') else '-' + self.typed
                else:
                    self.typed += ch
            else:
                return {'PASS_THROUGH'}
            self.mode = 'type'
            self.value = self.typed_value()
            self.apply(self.value)
            self.header(context)
            return {'RUNNING_MODAL'}
        return {'PASS_THROUGH'}


def _late_imports():
    """Noms définis dans des modules chargés après celui-ci : ils ne servent qu'à l'exécution des outils."""
    global set_prompt
    from .cplane import set_prompt
