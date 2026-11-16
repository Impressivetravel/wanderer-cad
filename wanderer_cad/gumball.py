"""Wanderer CAD : Gumball : déplacer, pivoter, mettre à l'échelle."""

import bmesh
import bpy
import math
import numpy as np
import time
from bpy_extras.view3d_utils import location_3d_to_region_2d, region_2d_to_origin_3d, region_2d_to_vector_3d
from mathutils import Matrix, Vector, geometry

from .core import (
    AXES3, TAU, _LAST_TYPED, copy_held, copy_key_name, copy_mod_event, copy_shift, copy_update, fmt_typed, last_typed, lock_held,
    lock_key_name, osnap, pref, tr_text, unit_info,
)
from .snapping import collect_snap_points, curve_edit_apply, curve_edit_selection, edit_selection
from .drawing import find_snap_in, px_scale
from .base import DessinBase
from .subd import (
    drag_copy_commit, expand_groups, ghost_for_edit, ghost_for_objects, ghost_hide, ghost_show,
)


# --------------------------------------------------------------------------
# Gumball : poignées au centre de la sélection (déplacer / pivoter / mettre à l'échelle, valeur au clavier)
# --------------------------------------------------------------------------

GUMBALL_COLORS = ((0.93, 0.18, 0.18), (0.35, 0.85, 0.20), (0.22, 0.42, 0.95))
GUMBALL_AXES = "XYZ"
GUMBALL_PX = 95.0   # longueur des flèches en pixels


def gumball_k(context):
    """Pixels écran par pixel d'interface pour le Gumball : échelle de l'écran (plafonnée à 2, écrans Retina) x réglage utilisateur."""
    try:
        size = context.scene.dessin.gumball_size / 100.0
    except (AttributeError, ReferenceError):
        size = 1.0
    return min(px_scale(), 2.0) * size


_GB_EDIT = {"t": 0.0, "sig": None, "res": (None, [])}


_GB_PIV = {"sig": None}


def _rot_cols(m):
    m3 = m.to_3x3()
    return tuple(Vector(m3.col[i]).normalized() for i in range(3))


def gumball_axes(context):
    """Les trois axes (monde) des poignées du Gumball : l'orientation de transformation de Blender (liste Global / Local / Normal... de l'en-tête)."""
    try:
        slot = context.scene.transform_orientation_slots[0]
        kind = slot.type
        act = context.view_layer.objects.active
        if kind == 'GLOBAL':
            return AXES3
        if kind in {'LOCAL', 'GIMBAL'} and act is not None:
            return _rot_cols(act.matrix_world.to_quaternion().to_matrix())
        if kind == 'NORMAL':
            if context.mode == 'EDIT_MESH':
                n = extrude_direction(context)
                if n is not None:
                    return _rot_cols(n.to_track_quat('Z', 'Y').to_matrix())
            elif act is not None:
                return _rot_cols(act.matrix_world.to_quaternion().to_matrix())
        elif kind == 'VIEW' and context.region_data is not None:
            q = context.region_data.view_rotation
            return tuple((q @ AXES3[i]).normalized() for i in range(3))
        elif kind == 'CURSOR':
            return _rot_cols(context.scene.cursor.matrix.to_quaternion().to_matrix())
        elif kind == 'PARENT' and act is not None:
            ref = act.parent if act.parent is not None else act
            return _rot_cols(ref.matrix_world.to_quaternion().to_matrix())
        elif kind not in {'GLOBAL', 'LOCAL', 'GIMBAL', 'NORMAL', 'VIEW', 'CURSOR', 'PARENT'}:
            co = slot.custom_orientation
            if co is not None:
                return _rot_cols(co.matrix)
    except (AttributeError, RuntimeError, ReferenceError, TypeError, IndexError):
        pass
    return AXES3


# Pendant qu'on transforme la sélection (comme dans Rhino), le Gumball accompagne l'objet : son centre et ses axes de départ
# sont gardés ici, et la transformation en cours (« X ») leur est appliquée à chaque dessin. Sans repère de départ figé,
# il était recalculé depuis la sélection à chaque mouvement de souris (lent, et ses axes sautaient pendant une rotation).
# Poignée du Gumball sous la souris pendant qu'Alt est maintenu : Blender n'éclaire plus ses poignées avec Alt (Alt + clic
# ne leur est jamais donné), alors Wanderer l'éclaire lui-même pour qu'on voie ce qu'Alt + glisser va copier.
_ALT_HOVER = {"area": 0, "handle": None}

_GB_DRAG = {"pivot": None, "axes": None, "owner": "", "X": None, "typing": False}


def gumball_freeze(context, pivot, owner):
    """Fige le Gumball en `pivot` tant que l'opération modale `owner` (début du nom de sa classe) est en cours."""
    try:
        _GB_DRAG["axes"] = [Vector(a) for a in gumball_axes(context)]
        _GB_DRAG["pivot"] = Vector(pivot)
        _GB_DRAG["owner"] = owner
        _GB_DRAG["X"] = None
    except (AttributeError, TypeError, ValueError, ReferenceError):
        gumball_unfreeze()


def gumball_drag_xform(X):
    """Transformation appliquée en ce moment à la sélection : le Gumball la suit (déplacement, rotation)."""
    _GB_DRAG["X"] = None if X is None else X.copy()


def gumball_typing():
    """Une valeur est en cours de saisie dans la bulle : le Gumball ne garde que ses flèches de déplacement (Rhino)."""
    return bool(_GB_DRAG["typing"]) and _GB_DRAG["pivot"] is not None


def gumball_unfreeze(context=None):
    _GB_DRAG["typing"] = False
    _GB_DRAG["pivot"] = _GB_DRAG["axes"] = _GB_DRAG["X"] = None
    if context is not None:
        try:
            for area in context.screen.areas:           # les poignées rejoignent tout de suite la sélection
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
        except (AttributeError, ReferenceError, RuntimeError):
            pass


def gumball_frozen(context):
    """(centre, axes) des poignées figées, ou None si aucun déplacement n'est en cours. Si l'opération s'est terminée sans
    prévenir (annulée par Blender), le Gumball est libéré."""
    if _GB_DRAG["pivot"] is None:
        return None
    try:
        ops = context.window.modal_operators
    except (AttributeError, RuntimeError, ReferenceError):
        ops = None
    if ops is not None and not any(op.bl_idname.startswith(_GB_DRAG["owner"]) for op in ops):
        gumball_unfreeze()
        return None
    X = _GB_DRAG["X"]
    if X is None:
        return _GB_DRAG["pivot"], _GB_DRAG["axes"]
    R = X.to_3x3()
    axes = []
    for a in _GB_DRAG["axes"]:
        v = R @ a
        axes.append(v.normalized() if v.length > 1e-9 else Vector(a))      # (échelle : les axes gardent leur direction)
    return X @ _GB_DRAG["pivot"], axes


def gumball_selection(context):
    """(centre des poignées, éléments) : centre de la boîte englobante, ou point choisi avec Relocate Gumball."""
    pivot, items = _gumball_selection_raw(context)
    if pivot is None or not items:
        return pivot, items
    try:
        st = context.scene.dessin
        if st.gumball_pivot_on:
            if context.mode == 'EDIT_CURVE':
                sig = (context.mode, sum(len(r) for _o, r, _w in items))
            else:
                sig = (context.mode, tuple(sorted(o.name for o in context.selected_objects)) if context.mode == 'OBJECT'
                       else tuple((o.name, o.data.total_vert_sel) for o in context.objects_in_mode_unique_data if o.type == 'MESH'))
            if st.gumball_autoreset and _GB_PIV["sig"] is not None and sig != _GB_PIV["sig"]:
                st.gumball_pivot_on = False
            else:
                _GB_PIV["sig"] = sig
                return Vector(st.gumball_pivot), items
    except (AttributeError, ReferenceError, RuntimeError):
        pass
    return pivot, items


def _gumball_selection_raw(context):
    """(centre de la boîte englobante, éléments à transformer) : objets (groupes développés) ou sommets en mode édition."""
    if context.mode in {'EDIT_MESH', 'EDIT_CURVE'}:
        sel = edit_selection(context) if context.mode == 'EDIT_MESH' else curve_edit_selection(context)
        if not sel:
            return None, []
        allp = np.vstack([w for _o, _i, w in sel])
        return Vector((allp.min(axis=0) + allp.max(axis=0)) / 2.0), sel
    sel = expand_groups(context, context.selected_objects)
    selected = set(sel)
    top = [o for o in sel if o.parent not in selected]
    pts = []
    for o in sel:
        if o.type == 'EMPTY' or not o.bound_box:
            pts.append(o.matrix_world.translation.copy())
        else:
            mw = o.matrix_world
            pts += [mw @ Vector(c) for c in o.bound_box]
    if not pts:
        return None, []
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return (lo + hi) / 2.0, top


def gumball_selection_cached(context):
    """Version pour le dessin : en mode édition le calcul est limité à quelques fois par seconde."""
    if context.mode not in {'EDIT_MESH', 'EDIT_CURVE'}:
        return gumball_selection(context)
    now = time.monotonic()
    try:
        if context.mode == 'EDIT_MESH':
            sig = tuple((o.name, o.data.total_vert_sel) for o in context.objects_in_mode_unique_data if o.type == 'MESH')
        else:
            sig = ('C',) + tuple(o.name for o in context.objects_in_mode_unique_data if o.type == 'CURVE')
    except (AttributeError, ReferenceError):
        sig = None
    sig = (context.mode, sig)
    if sig != _GB_EDIT["sig"] or now - _GB_EDIT["t"] > (0.25 if context.mode == 'EDIT_MESH' else 0.12):
        _GB_EDIT["sig"] = sig
        _GB_EDIT["t"] = now
        pivot, items = gumball_selection(context)
        _GB_EDIT["res"] = (pivot, bool(items))
    pivot, ok = _GB_EDIT["res"]
    return (pivot, [True]) if ok and pivot is not None else (None, [])


class GumballBase(bpy.types.Operator):
    """Logique du Gumball (classe non enregistrée) : glisser = direct, simple clic = on tape la valeur."""

    bl_options = {'REGISTER', 'UNDO'}

    def mouse(self, context, event):
        return Vector((event.mouse_x - context.region.x, event.mouse_y - context.region.y))

    def sample(self, context, event):
        """Valeur brute sous la souris : paramètre sur l'axe (déplacement, échelle) ou angle (rotation)."""
        region, rv3d = context.region, context.region_data
        m = self.mouse(context, event)
        ro = region_2d_to_origin_3d(region, rv3d, m)
        rv = region_2d_to_vector_3d(region, rv3d, m)
        if self.kind == 'PLANE':                # déplacement dans le plan perpendiculaire à l'axe : point visé sur ce plan
            return geometry.intersect_line_plane(ro, ro + rv, self.pivot, self.dir)
        if self.kind == 'ROTATE':
            hit = geometry.intersect_line_plane(ro, ro + rv, self.pivot, self.dir)
            if hit is None:
                return None
            d = hit - self.pivot
            if d.length < 1e-9:
                return None
            return math.atan2(d.dot(self.bv), d.dot(self.bu))
        res = geometry.intersect_line_line(self.pivot, self.pivot + self.dir, ro, ro + rv)
        if not res:
            return None
        return (res[0] - self.pivot).dot(self.dir)

    def default_value(self):
        if self.kind == 'PLANE':
            return Vector((0.0, 0.0, 0.0))
        return 1.0 if self.kind == 'SCALE' else 0.0

    def enter_last(self, enter=True):
        """Validation en mode saisie : retient la valeur tapée ; Entrée sans rien taper reprend la dernière (comme Rhino)."""
        key = (self.bl_idname, self.kind)
        if self.typed not in ('', '-', '.', '-.'):
            _LAST_TYPED[key] = self.value
        elif enter:
            v = last_typed(key)
            if v is not None:
                self.value = v
                self.apply(v)

    def snap_move(self, context, event, value):
        """Snappy Dragging : la flèche se cale sur l'accrochage (End, Mid, Cen...) sous le curseur."""
        try:
            if self.kind not in {'MOVE', 'PLANE'} or self.edit or context.scene.dessin.gumball_drag != 'SNAPPY' or osnap("disable"):
                return value
            if getattr(self, "_snapd", None) is None:
                names = set()
                for obj, _ in self.items:
                    names.add(obj.name)
                    names.update(c.name for c in obj.children_recursive)
                self._snapd = collect_snap_points(context, names)
            m = self.mouse(context, event)
            hit = find_snap_in(self._snapd, m.x, m.y, context.region, context.region_data)
        except (RuntimeError, ReferenceError, AttributeError, ValueError, TypeError):
            return value
        if hit is None:
            return value
        if self.kind == 'PLANE':                # le centre des poignées vient à l'aplomb du point accroché, dans le plan
            d = hit[0] - self.pivot
            return d - self.dir * d.dot(self.dir)
        return (hit[0] - self.pivot).dot(self.dir)

    def value_from_sample(self, s, shift):
        if s is None:
            return self.value
        if self.kind == 'PLANE':
            return s - self.ref
        if self.kind == 'MOVE':
            return s - self.ref
        if self.kind == 'SCALE':
            return s / self.ref if abs(self.ref) > 1e-6 else 1.0
        delta = s - self.last
        while delta > math.pi:
            delta -= TAU
        while delta < -math.pi:
            delta += TAU
        self.last = s
        self.acc += delta
        deg = math.degrees(self.acc)
        if (not shift) if pref("gumball_rot90") else shift:   # pas de 90° (par défaut) ; Maj = rotation libre
            stp = float(pref("gumball_step"))
            deg = round(deg / stp) * stp
        return deg

    def xform(self, value, uniform=False):
        p = self.pivot
        if self.kind == 'PLANE':
            return Matrix.Translation(value)
        if self.kind == 'MOVE':
            return Matrix.Translation(self.dir * value)
        if self.kind == 'ROTATE':
            return Matrix.Translation(p) @ Matrix.Rotation(math.radians(value), 4, self.dir) @ Matrix.Translation(-p)
        S = Matrix.Scale(value, 4) if uniform else Matrix.Scale(value, 4, self.dir)
        return Matrix.Translation(p) @ S @ Matrix.Translation(-p)

    def edit_apply(self, X):
        Xn = np.array(X, dtype=np.float64)
        for obj, idx, w0 in self.items:
            if obj.type == 'CURVE':
                curve_edit_apply(obj, idx, w0, Xn)
                continue
            try:
                bm = bmesh.from_edit_mesh(obj.data)
            except (ValueError, ReferenceError):
                continue
            bm.verts.ensure_lookup_table()
            M = np.linalg.inv(np.array(obj.matrix_world, dtype=np.float64)) @ Xn
            h = np.hstack((w0, np.ones((len(w0), 1)))) @ M.T
            for i, p in zip(idx, h):
                bm.verts[i].co = Vector((p[0], p[1], p[2]))
            bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=False)

    def apply(self, value):
        X = self.xform(value, getattr(self, "uniform", False))
        gumball_drag_xform(X)                     # le Gumball suit la sélection pendant l'opération (comme Rhino)
        if self.edit:
            self.edit_apply(X)
            return
        for obj, mw in self.items:
            try:
                obj.matrix_world = X @ mw
            except ReferenceError:
                pass

    def restore(self):
        gumball_drag_xform(None)
        if self.edit:
            self.edit_apply(Matrix.Identity(4))
            return
        for obj, mw in self.items:
            try:
                obj.matrix_world = mw
            except ReferenceError:
                pass

    def label(self):
        base = self._label()
        if not getattr(self, "alt_copy", False) or getattr(self, "NO_COPY", False):
            return base
        if self.edit and copy_shift() and not getattr(self, "ctrl_held", False):
            return "Extrude - " + base                  # (3ds Max : Maj + glisser des arêtes ou des faces)
        return "Copy - " + base

    def _label(self):
        ax = GUMBALL_AXES[self.axis]
        if self.kind == 'PLANE':
            names = "".join(GUMBALL_AXES[i] for i in range(3) if i != self.axis)
            v = self.value / self.unit_f
            return f"Move in the {names} plane: ({v.x:.3f}, {v.y:.3f}, {v.z:.3f}) {self.unit_label}".strip()
        if self.kind == 'MOVE':
            v = self.value / self.unit_f
            return f"Move {ax}: {v:.3f} {self.unit_label}".strip()
        if self.kind == 'ROTATE':
            return f"Rotate around {ax}: {self.value:.2f}°"
        return f"Scale {'(uniform)' if getattr(self, 'uniform', False) else ax}: ×{self.value:.4f}"

    def bubble(self, context):
        """Bulle de saisie près de la poignée cliquée (comme Rhino), dans le style des barres du bas."""
        try:
            if self.mode != 'type':
                value_bubble_hide(context.area)
                return
            region, rv3d = context.region, context.region_data
            p0 = location_3d_to_region_2d(region, rv3d, self.pivot)
            p1 = location_3d_to_region_2d(region, rv3d, self.pivot + self.dir * 1e-3)
            if p0 is None:
                value_bubble_hide(context.area)
                return
            L = GUMBALL_PX * gumball_k(context)
            if self.kind == 'ROTATE':
                a = p0 + Vector((0.45, 0.45)) * L
            else:
                v = (p1 - p0) if p1 is not None else Vector((1.0, 0.0))
                v = v.normalized() if v.length > 1e-9 else Vector((1.0, 0.0))
                a = p0 + v * L * (1.25 if self.kind == 'MOVE' else -0.93)    # au bout de la flèche (Rhino)
            ax = GUMBALL_AXES[self.axis]
            col = (*GUMBALL_COLORS[self.axis][:3], 1.0)
            if self.kind == 'MOVE':
                parts = [(tr_text("Distance to move in "), None, False), (ax, col, True)]
            elif self.kind == 'ROTATE':
                parts = [(tr_text("Angle to rotate around "), None, False), (ax, col, True)]
            else:
                parts = [(tr_text("Scale factor along "), None, False), (ax, col, True)]
            value_bubble_show(context.area, (a.x, a.y), parts, self.typed)
        except (AttributeError, ReferenceError, TypeError, ValueError, RuntimeError):
            pass

    def header(self, context):
        self.bubble(context)
        if self.mode == 'type':
            unit = {'MOVE': self.unit_label or "", 'ROTATE': "°", 'SCALE': "×"}[self.kind]
            lv = last_typed((self.bl_idname, self.kind)) if not self.typed else None
            last = "" if lv is None else f" (nothing typed: {fmt_typed(lv / self.unit_f if self.kind == 'MOVE' else lv)}, last value)"
            txt = f"{self.label()}   |   type the value: {self.typed or '_'} {unit}   |   Enter: apply{last}   Esc: cancel"
        else:
            txt = f"{self.label()}   |   release: apply   Esc: cancel" + ("" if self.kind == 'PLANE' else "   (a click without dragging lets you type the value)") + (f"   |   90° steps, {lock_key_name()}: free rotation" if self.kind == 'ROTATE' else "")
            if not getattr(self, "NO_COPY", False):
                txt += f"   |   {copy_key_name()}: copy"
        try:
            set_prompt(context.area, txt)
        except (AttributeError, ReferenceError):
            pass

    def update_ghost(self, context):
        if not getattr(self, "alt_copy", False) or getattr(self, "NO_COPY", False) or self.mode == 'wait':
            ghost_hide()
            return
        if getattr(self, "_ghost", None) is None:
            self._ghost = ghost_for_edit(self.items) if self.edit else ghost_for_objects(self.items)
        ghost_show(context.area, self._ghost)

    def finish_ui(self, context):
        _ALT_HOVER["handle"] = None
        value_bubble_hide(getattr(context, "area", None))
        gumball_unfreeze(context)
        ghost_hide()
        try:
            set_prompt(context.area, None)
        except (AttributeError, ReferenceError):
            pass

    def setup_selection(self, context):
        """Remplit pivot, edit, items et dir ; False si rien à faire."""
        pivot, top = gumball_selection(context)
        if not top:
            return False
        self.pivot = pivot
        self.edit = context.mode in {'EDIT_MESH', 'EDIT_CURVE'}
        if context.mode == 'EDIT_CURVE':
            self.NO_COPY = True
        self.items = top if self.edit else [(o, o.matrix_world.copy()) for o in top]
        self.dir = gumball_axes(context)[self.axis].copy()
        return True

    def invoke(self, context, event):
        if context.region is None or context.region_data is None or not self.setup_selection(context):
            return {'CANCELLED'}
        self.bu = self.dir.orthogonal().normalized()
        self.bv = self.dir.cross(self.bu)
        self.unit_f, self.unit_label = unit_info(context.scene)
        self.press = self.mouse(context, event)
        self.mode = 'wait'
        self.typed = ''
        self.alt_copy = copy_held(event)
        self.ctrl_held = bool(event.ctrl)
        self.uniform = False
        self.value = self.default_value()
        self.acc = 0.0
        s0 = self.sample(context, event)
        if s0 is None:
            return {'CANCELLED'}
        self.ref = s0
        self.last = s0
        gumball_freeze(context, self.pivot, "DESSIN_OT_gumball")       # repère de départ du Gumball, qui suit ensuite la sélection
        context.window_manager.modal_handler_add(self)
        self.header(context)
        return {'RUNNING_MODAL'}

    def typed_value(self):
        t = self.typed
        if t in ('', '-', '.', '-.'):
            return self.default_value()
        try:
            v = float(t)
        except ValueError:
            return self.default_value()
        return v * self.unit_f if self.kind == 'MOVE' else v

    def cancel_all(self, context):
        self.restore()
        self.finish_ui(context)
        return {'CANCELLED'}

    def commit(self, context):
        if getattr(self, "alt_copy", False) and not getattr(self, "NO_COPY", False):
            drag_copy_commit(context, self.items, self.edit, ctrl=getattr(self, "ctrl_held", False))
        self.finish_ui(context)
        return {'FINISHED'}

    def modal(self, context, event):
        et = event.type
        if et in {'LEFT_CTRL', 'RIGHT_CTRL'}:
            self.ctrl_held = event.value == 'PRESS'                        # (3ds Max : Ctrl + Maj = copie détachée)
        elif et in {'MOUSEMOVE', 'LEFTMOUSE'}:
            self.ctrl_held = bool(event.ctrl)
        mod = copy_mod_event(event, getattr(self, "alt_copy", False))     # Alt ou Maj : copie (selon les préférences)
        if mod is not None:
            self.alt_copy = mod[0]
            self.header(context)
            self.update_ghost(context)
            return {'RUNNING_MODAL'}
        if et in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            self.alt_copy = copy_update(event, getattr(self, "alt_copy", False))
            self.update_ghost(context)
        elif event.value == 'PRESS' and copy_held(event):
            self.alt_copy = True
        if self.mode == 'type':
            if event.value == 'PRESS':
                if et == 'ESC':
                    return self.cancel_all(context)
                if et in {'RET', 'NUMPAD_ENTER'}:
                    self.enter_last(True)
                    self.apply(self.value)          # l'objet se déplace maintenant, une fois la valeur validée
                    return self.commit(context)
                if et == 'LEFTMOUSE':           # clic ailleurs : la saisie est abandonnée et le clic agit normalement (Rhino)
                    self.cancel_all(context)
                    return {'CANCELLED', 'PASS_THROUGH'}
                if et == 'BACK_SPACE':
                    self.typed = self.typed[:-1]
                elif event.unicode and event.unicode in "0123456789.,-":
                    ch = "." if event.unicode == "," else event.unicode
                    if ch == '-':
                        self.typed = self.typed[1:] if self.typed.startswith('-') else '-' + self.typed
                    else:
                        self.typed += ch
                else:
                    return {'PASS_THROUGH'}
                self.value = self.typed_value()      # (appliquée seulement à la validation, comme dans Rhino)
                self.header(context)
                return {'RUNNING_MODAL'}
            return {'PASS_THROUGH'} if et not in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'} else {'RUNNING_MODAL'}
        # glisser
        if et in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            m = self.mouse(context, event)
            if self.mode == 'wait' and (m - self.press).length > 5.0 * px_scale():
                self.mode = 'drag'
            if self.mode == 'drag':
                self.uniform = lock_held(event) and self.kind == 'SCALE'
                self.value = self.value_from_sample(self.sample(context, event), lock_held(event))
                self.value = self.snap_move(context, event, self.value)
                self.apply(self.value)
                self.header(context)
            return {'RUNNING_MODAL'}
        if et == 'LEFTMOUSE' and event.value == 'RELEASE':
            if self.mode == 'drag':
                return self.commit(context)
            if self.kind == 'PLANE':
                return self.cancel_all(context)         # déplacement dans un plan : pas de valeur à taper, un clic ne fait rien
            self.mode = 'type'          # simple clic : on tape la valeur
            _GB_DRAG["typing"] = True
            self.typed = ''
            self.value = self.default_value()
            self.header(context)
            return {'RUNNING_MODAL'}
        if et in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            return self.cancel_all(context)
        return {'RUNNING_MODAL'}


class DESSIN_OT_gumball(GumballBase):
    bl_idname = "dessin.gumball"
    bl_label = "Gumball"
    bl_description = ("Drag to transform the selection from its center; click without dragging, then type the "
                      "distance / angle / scale factor and press Enter")

    kind: bpy.props.EnumProperty(items=(('MOVE', "Move", ""), ('ROTATE', "Rotate", ""), ('SCALE', "Scale", ""), ('PLANE', "Move in a plane", "")),
                                 default='MOVE', options={'SKIP_SAVE'})
    axis: bpy.props.IntProperty(default=0, min=0, max=2, options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.mode in {'OBJECT', 'EDIT_MESH', 'EDIT_CURVE'} and context.area is not None and context.area.type == 'VIEW_3D'


def _gb_redraw(context):
    _GB_EDIT["t"] = 0.0
    try:
        for win in context.window_manager.windows:
            for a in win.screen.areas:
                if a.type == 'VIEW_3D':
                    a.tag_redraw()
    except (AttributeError, RuntimeError, ReferenceError):
        pass


class DESSIN_OT_gumball_relocate(DessinBase):
    bl_idname = "dessin.gumball_relocate"
    bl_label = "Relocate Gumball"
    bl_description = "Moves the Gumball to a point you click (with snapping): rotations and scaling then use that point"

    TITLE = "Relocate Gumball"
    NEEDED = 1
    PLANAR = False
    LOCK_OK = False

    def prompt(self):
        return "click the new location of the Gumball   (snapping on)"

    def click(self, context):
        try:
            st = context.scene.dessin
            st.gumball_pivot = self.cur
            st.gumball_pivot_on = True
        except (AttributeError, ReferenceError):
            pass
        _GB_PIV["sig"] = None
        _gb_redraw(context)
        self.finished = True


class DESSIN_OT_gumball_reset(bpy.types.Operator):
    bl_idname = "dessin.gumball_reset"
    bl_label = "Reset Gumball"
    bl_description = "Puts the Gumball back at the center of the selection"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        context.scene.dessin.gumball_pivot_on = False
        _gb_redraw(context)
        return {'FINISHED'}


class DESSIN_OT_gumball_set(bpy.types.Operator):
    bl_idname = "dessin.gumball_set"
    bl_label = "Gumball On / Off"
    bl_options = {'INTERNAL'}

    on: bpy.props.BoolProperty(default=True)

    def execute(self, context):
        context.scene.dessin.gumball = self.on
        _gb_redraw(context)
        return {'FINISHED'}


class DESSIN_OT_gumball_settings(bpy.types.Operator):
    bl_idname = "dessin.gumball_settings"
    bl_label = "Settings..."
    bl_description = "Opens the Gumball settings of the add-on (rotation steps, line thickness) in the preferences"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        try:
            bpy.ops.preferences.addon_show(module=__package__)
        except (RuntimeError, TypeError):
            self.report({'INFO'}, "Preferences > Add-ons > Wanderer > Gumball")
        return {'FINISHED'}


class DESSIN_MT_gumball(bpy.types.Menu):
    bl_idname = "DESSIN_MT_gumball"
    bl_label = "Gumball"

    def draw(self, context):
        lay = self.layout
        st = context.scene.dessin
        lay.operator(DESSIN_OT_gumball_relocate.bl_idname, text="Relocate Gumball")
        lay.operator(DESSIN_OT_gumball_reset.bl_idname, text="Reset Gumball")
        lay.prop(st, "gumball_autoreset", text="AutoReset Gumball", toggle=False)
        lay.separator()
        op = lay.operator(DESSIN_OT_gumball_set.bl_idname, text="Gumball On", icon='RADIOBUT_ON' if st.gumball else 'RADIOBUT_OFF')
        op.on = True
        op = lay.operator(DESSIN_OT_gumball_set.bl_idname, text="Gumball Off", icon='RADIOBUT_OFF' if st.gumball else 'RADIOBUT_ON')
        op.on = False
        lay.separator()
        try:
            lay.label(text="Orientation (same as the header list)")
            lay.prop(context.scene.transform_orientation_slots[0], "type", expand=True)
        except (AttributeError, IndexError, RuntimeError):
            pass
        lay.separator()
        for item in st.bl_rna.properties["gumball_drag"].enum_items:
            lay.prop_enum(st, "gumball_drag", item.identifier)
        lay.separator()
        lay.operator(DESSIN_OT_gumball_settings.bl_idname, text="Settings...")


_EXT_CACHE = {"t": 0.0, "sig": None, "dir": None}


def extrude_direction(context):
    """Direction (monde) d'extrusion des faces / arêtes sélectionnées, ou None ; calculée au plus 4 fois par seconde."""
    now = time.monotonic()
    try:
        sig = tuple((o.name, o.data.total_face_sel, o.data.total_edge_sel, o.data.total_vert_sel)
                    for o in context.objects_in_mode_unique_data if o.type == 'MESH')
    except (AttributeError, ReferenceError):
        return None
    if sig == _EXT_CACHE["sig"] and now - _EXT_CACHE["t"] < 0.25:
        return _EXT_CACHE["dir"]
    dsum = Vector()
    for obj in context.objects_in_mode_unique_data:
        if obj.type != 'MESH':
            continue
        try:
            bm = bmesh.from_edit_mesh(obj.data)
        except ValueError:
            continue
        nm = obj.matrix_world.to_3x3().inverted_safe().transposed()
        faces = [f for f in bm.faces if f.select]
        if faces:
            for f in faces:
                dsum += (nm @ f.normal).normalized() * f.calc_area()
        else:
            for e in bm.edges:
                if e.select:
                    for f in e.link_faces:
                        dsum += (nm @ f.normal).normalized()
    out = dsum.normalized() if dsum.length > 1e-9 else Vector((0.0, 0.0, 1.0))
    _EXT_CACHE.update(t=now, sig=sig, dir=out)
    return out


def extrude_info(context):
    """(faces, arêtes) sélectionnées en mode édition (nombres), pour savoir si la poignée d'extrusion s'affiche."""
    nf = ne = 0
    try:
        for o in context.objects_in_mode_unique_data:
            if o.type == 'MESH':
                nf += o.data.total_face_sel
                ne += o.data.total_edge_sel
    except (AttributeError, ReferenceError):
        pass
    return nf, ne


def mirror_plane_cleanup(obj, bm, tol=1e-5):
    """Après une extrusion : les faces posées sur un plan de symétrie (Mirror avec Clipping) sont supprimées, comme le fait
    l'extrusion de Blender ; sinon elles deviennent des faces internes (arêtes non-manifold) une fois le miroir appliqué."""
    axes = set()
    for md in obj.modifiers:
        if md.type == 'MIRROR' and md.show_viewport and md.use_clip and md.mirror_object is None:
            axes |= {i for i in range(3) if md.use_axis[i]}
    if not axes:
        return 0
    walls = [f for f in bm.faces if any(all(abs(v.co[a]) <= tol for v in f.verts) for a in axes)]
    if walls:
        bmesh.ops.delete(bm, geom=walls, context='FACES')
    return len(walls)


class DESSIN_OT_gumball_extrude(GumballBase):
    bl_idname = "dessin.gumball_extrude"
    bl_label = "Extrude"
    bl_description = ("Extrudes the selected faces (or edges) along their normal: drag, or click without dragging, "
                      "type the distance and press Enter")

    NO_COPY = True
    kind = 'MOVE'
    axis = 0

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and context.area is not None and context.area.type == 'VIEW_3D'

    def setup_selection(self, context):
        self.backups = []
        items = []
        dsum = Vector()
        pts = []
        for obj in context.objects_in_mode_unique_data:
            if obj.type != 'MESH':
                continue
            bm = bmesh.from_edit_mesh(obj.data)
            faces = [f for f in bm.faces if f.select]
            edges = [] if faces else [e for e in bm.edges if e.select]
            if not faces and not edges:
                continue
            nm = obj.matrix_world.to_3x3().inverted_safe().transposed()
            if faces:
                for f in faces:
                    dsum += (nm @ f.normal).normalized() * f.calc_area()
            else:
                for e in edges:
                    for f in e.link_faces:
                        dsum += (nm @ f.normal).normalized()
            tmp = bpy.data.meshes.new("dessin_extrude_backup")
            bm.to_mesh(tmp)                      # copie de secours (pour Échap)
            self.backups.append((obj, tmp))
            if faces:
                ret = bmesh.ops.extrude_face_region(bm, geom=faces)
                # comme l'extrusion de Blender : les faces d'origine disparaissent (sinon elles restent à l'intérieur du volume)
                bmesh.ops.delete(bm, geom=[f for f in faces if f.is_valid], context='FACES')
            else:
                ret = bmesh.ops.extrude_edge_only(bm, edges=edges)
            geom = ret["geom"]
            if mirror_plane_cleanup(obj, bm):
                geom = [g for g in geom if g.is_valid]
            new_verts = [g for g in geom if isinstance(g, bmesh.types.BMVert)]
            for v in bm.verts:
                v.select_set(False)
            for g in geom:
                g.select_set(True)
            bm.select_flush_mode()
            bm.verts.ensure_lookup_table()
            bm.verts.index_update()
            mw = np.array(obj.matrix_world, dtype=np.float64)
            co = np.array([tuple(v.co) for v in new_verts], dtype=np.float64)
            w0 = co @ mw[:3, :3].T + mw[:3, 3]
            items.append((obj, [v.index for v in new_verts], w0))
            pts.append(w0)
            bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=True)
        if not items:
            return False
        if dsum.length < 1e-9:
            dsum = Vector((0.0, 0.0, 1.0))
        allp = np.vstack(pts)
        self.pivot = Vector((allp.min(axis=0) + allp.max(axis=0)) / 2.0)
        self.edit = True
        self.items = items
        self.dir = dsum.normalized()
        return True

    def drop_backups(self):
        for _o, tmp in self.backups:
            try:
                bpy.data.meshes.remove(tmp)
            except (ReferenceError, RuntimeError):
                pass
        self.backups = []

    def label(self):
        return f"Extrude: {self.value / self.unit_f:.3f} {self.unit_label}".strip()

    def cancel_all(self, context):
        for obj, tmp in self.backups:               # on revient au maillage d'avant l'extrusion
            try:
                bm = bmesh.from_edit_mesh(obj.data)
                bm.clear()
                bm.from_mesh(tmp)
                bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=True)
            except (ReferenceError, RuntimeError, ValueError):
                pass
        self.drop_backups()
        self.finish_ui(context)
        return {'CANCELLED'}

    def commit(self, context):
        if abs(self.value) < 1e-9:                  # distance nulle : pas d'extrusion
            return self.cancel_all(context)
        self.drop_backups()
        self.finish_ui(context)
        return {'FINISHED'}


def _late_imports():
    """Noms définis dans des modules chargés après celui-ci : ils ne servent qu'à l'exécution des outils."""
    global set_prompt, value_bubble_hide, value_bubble_show
    from .cplane import set_prompt
    from .command_line import value_bubble_hide, value_bubble_show
