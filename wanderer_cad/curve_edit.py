"""Wanderer CAD : Xline, Stretch, Divide, Overkill, Fillet / Chamfer de courbes."""

import bpy
import gpu
import math
import numpy as np
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

from .core import idle_tool, plane_axes, pref, unit_info
from .drawing import draw_px_points, get_shader, project_px, px_scale, region_rv3d
from .base import DessinBase


# --------------------------------------------------------------------------
# Xline, Stretch, Divide, Overkill
# --------------------------------------------------------------------------

class DESSIN_OT_xline(DessinBase):
    bl_idname = "dessin.xline"
    bl_label = "Construction Line"
    bl_description = ("Draws a very long construction line through a point: click the point, then a second point for the direction "
                      "(Shift: orthogonal, or type the angle in degrees)")

    TITLE = "Construction Line"
    NEEDED = 2
    NUMFIELDS = 1
    EDIT_OK = False
    ortho = False

    def prompt(self):
        if not self.points:
            return "point the line goes through"
        return "direction   (Shift: orthogonal, or type the angle in degrees then Enter)"

    def update_cursor(self, context, event):
        self.ortho = bool(event.shift)
        super().update_cursor(context, event)

    def half_length(self):
        try:
            rv3d = region_rv3d(self.region, self.area)
            return max(20.0, float(rv3d.view_distance) * 30.0)
        except (AttributeError, TypeError, ReferenceError):
            return 200.0

    def compute(self):
        if not self.points or self.cur is None:
            return [], [], "", None
        u, v, _ = plane_axes(self.axis)
        o = self.points[0]
        d = self.cur - o
        du, dv = d.dot(u), d.dot(v)
        if self.ortho and not self.snap_screen:
            if abs(du) >= abs(dv):
                dv = 0.0
            else:
                du = 0.0
        ang = self.typed_raw(0)
        if ang is not None:
            du, dv = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        if math.hypot(du, dv) < 1e-9:
            return [], [], "", None
        direction = (u * du + v * dv).normalized()
        L = self.half_length()
        a, b = o - direction * L, o + direction * L
        angle = math.degrees(math.atan2(dv, du))
        return [a, b], [], f"Angle {angle:.2f}°", ("line", a, b)

    def build(self, context, spec):
        obj = super().build(context, spec)
        if obj is not None and context.mode != 'EDIT_MESH':
            obj.name = "Construction Line"
            obj["cad_noGrab"] = True
            obj["cad_xline"] = True
        return obj


class DESSIN_OT_stretch(DessinBase):
    bl_idname = "dessin.stretch"
    bl_label = "Stretch"
    bl_description = ("Stretches the points inside a crossing window: two corners for the window, then a base point and a destination point "
                      "(Shift: orthogonal, or type the distance). Works on the selected objects, or on all visible curves and meshes")

    TITLE = "Stretch"
    NEEDED = 4
    NUMFIELDS = 1
    EDIT_OK = False
    ortho = False

    def prompt(self):
        n = len(self.points)
        if n == 0:
            return "first corner of the crossing window"
        if n == 1:
            return "opposite corner of the window"
        if n == 2:
            return "base point"
        return "destination   (Shift: orthogonal, or type the distance then Enter)"

    def update_cursor(self, context, event):
        self.ortho = bool(event.shift)
        super().update_cursor(context, event)

    def window_corners(self, a, b):
        u, v, _ = plane_axes(self.axis)
        d = b - a
        du, dv = d.dot(u), d.dot(v)
        return [a.copy(), a + u * du, a + u * du + v * dv, a + v * dv]

    def delta(self):
        u, v, _ = plane_axes(self.axis)
        d = self.cur - self.points[2]
        du, dv = d.dot(u), d.dot(v)
        if self.ortho:
            if abs(du) >= abs(dv):
                dv = 0.0
            else:
                du = 0.0
        vec = u * du + v * dv if self.PLANAR else d
        t = self.typed_value(0)
        if t is not None:
            vec = (vec / vec.length if vec.length > 1e-9 else u.copy()) * t
        return vec

    def compute(self):
        n = len(self.points)
        if n == 0 or self.cur is None:
            return [], [], "", None
        if n == 1:
            c = self.window_corners(self.points[0], self.cur)
            return c + [c[0]], [], "", None
        c = self.window_corners(self.points[0], self.points[1])
        win = c + [c[0]]
        if n == 2:
            return [], [win], "", None
        vec = self.delta()
        if vec.length < 1e-9:
            return [], [win], "", None
        o = self.points[2]
        info = f"Distance {self.fmt(vec.length)}   \u0394 ({self.fmt(vec.x)}, {self.fmt(vec.y)}, {self.fmt(vec.z)})"
        return [], [win, [o, o + vec]], info, ("stretch", vec)

    def window_rect(self):
        rv3d = region_rv3d(self.region, self.area)
        xs, ys = [], []
        for q in self.window_corners(self.points[0], self.points[1]):
            sp = project_px(rv3d, self.region, q)
            if sp is not None:
                xs.append(sp.x)
                ys.append(sp.y)
        if not xs:
            return None
        return min(xs), min(ys), max(xs), max(ys)

    def build(self, context, spec):
        if spec[0] != 'stretch':
            return None
        rect = self.window_rect()
        if rect is None:
            self.report({'WARNING'}, "The window is not visible")
            return None
        rv3d = region_rv3d(self.region, self.area)
        persp = np.array(rv3d.perspective_matrix, dtype=np.float64)
        W, H = float(self.region.width), float(self.region.height)
        xmin, ymin, xmax, ymax = rect
        vec = np.array(spec[1], dtype=np.float64)

        def inside(P):
            h = np.hstack((P, np.ones((len(P), 1)))) @ persp.T
            w = h[:, 3]
            ok = w > 1e-9
            w = np.where(ok, w, 1.0)
            sx = (h[:, 0] / w * 0.5 + 0.5) * W
            sy = (h[:, 1] / w * 0.5 + 0.5) * H
            return ok & (sx >= xmin) & (sx <= xmax) & (sy >= ymin) & (sy <= ymax)

        objs = [o for o in context.selected_objects if o.type in {'MESH', 'CURVE'}]
        if not objs:
            objs = [o for o in context.view_layer.objects if o.type in {'MESH', 'CURVE'} and o.visible_get() and not o.hide_select]
        moved, touched = 0, 0
        for o in objs:
            mw = np.array(o.matrix_world, dtype=np.float64)
            inv = np.linalg.inv(mw)
            n = 0
            if o.type == 'MESH':
                me = o.data
                cnt = len(me.vertices)
                if not cnt:
                    continue
                co = np.empty(cnt * 3, dtype=np.float64)
                me.vertices.foreach_get('co', co)
                co = co.reshape(-1, 3)
                world = co @ mw[:3, :3].T + mw[:3, 3]
                sel = inside(world)
                n = int(sel.sum())
                if n:
                    world[sel] += vec
                    new = world @ inv[:3, :3].T + inv[:3, 3]
                    me.vertices.foreach_set('co', new.reshape(-1))
                    me.update()
            else:
                for sp in o.data.splines:
                    if sp.type == 'BEZIER':
                        for bp in sp.bezier_points:
                            trio = [bp.co, bp.handle_left, bp.handle_right]
                            P = np.array([tuple(t) for t in trio], dtype=np.float64) @ mw[:3, :3].T + mw[:3, 3]
                            ins = inside(P)
                            if ins[0]:
                                ins[:] = True
                            if ins.any():
                                P[ins] += vec
                                Q = P @ inv[:3, :3].T + inv[:3, 3]
                                for flag, q, name in zip(ins, Q, ('co', 'handle_left', 'handle_right')):
                                    if flag:
                                        setattr(bp, name, tuple(q))
                                n += 1
                    else:
                        pts = list(sp.points)
                        if not pts:
                            continue
                        P = np.array([tuple(p.co[:3]) for p in pts], dtype=np.float64) @ mw[:3, :3].T + mw[:3, 3]
                        ins = inside(P)
                        if ins.any():
                            P[ins] += vec
                            Q = P @ inv[:3, :3].T + inv[:3, 3]
                            for flag, p_, q in zip(ins, pts, Q):
                                if flag:
                                    p_.co = (q[0], q[1], q[2], p_.co[3])
                            n += int(ins.sum())
                if n:
                    o.data.update_tag()
            if n:
                moved += n
                touched += 1
        if not moved:
            self.report({'WARNING'}, "No point inside the window")
            return None
        self.report({'INFO'}, f"Stretched {moved} point(s) on {touched} object(s)")
        return objs[0]

    def after_finish(self, context):
        if self.tool_id:
            try:
                idle_tool()
            except (RuntimeError, TypeError):
                pass


def _divide_points(P, closed, mode, count, length, ends):
    """Points régulièrement répartis sur un contour (P : (n,3))."""
    Q = np.vstack((P, P[:1])) if closed else P
    seg = np.linalg.norm(np.diff(Q, axis=0), axis=1)
    cum = np.concatenate(([0.0], np.cumsum(seg)))
    total = cum[-1]
    if total < 1e-9:
        return []
    if mode == 'COUNT':
        n = max(2, int(count))
        step = total / n
    else:
        step = max(1e-6, float(length))
        n = max(1, int(round(total / step)) if closed else int(total / step + 1e-9))
    ts = [i * step for i in range(n + 1)]
    ts = [t for t in ts if t <= total + 1e-9]
    if closed and ts and abs(ts[-1] - total) < 1e-6:
        ts = ts[:-1]
    if not ends and not closed:
        ts = [t for t in ts if t > 1e-9 and t < total - 1e-9]
    return [Vector((np.interp(t, cum, Q[:, 0]), np.interp(t, cum, Q[:, 1]), np.interp(t, cum, Q[:, 2]))) for t in ts]


class DESSIN_OT_divide(bpy.types.Operator):
    bl_idname = "dessin.divide"
    bl_label = "Divide"
    bl_description = ("Places point markers (one object) at regular intervals along the selected curves or outlines: a number of segments or a segment length")
    bl_options = {'REGISTER', 'UNDO'}

    mode: bpy.props.EnumProperty(name="By", items=(('COUNT', "Number of segments", ""), ('LENGTH', "Segment length", "")), default='COUNT')
    count: bpy.props.IntProperty(name="Segments", default=5, min=2, max=500)
    length: bpy.props.FloatProperty(name="Length", default=0.1, min=1e-5, subtype='DISTANCE')
    ends: bpy.props.BoolProperty(name="Include end points", default=True)

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and context.area is not None and context.area.type == 'VIEW_3D'

    def points(self, context):
        pts = []
        for P, closed in self._paths:
            pts += _divide_points(P, closed, self.mode, self.count, self.length, self.ends)
        return pts

    def status(self, context):
        pts = self._pts
        if self.mode == 'COUNT':
            what = f"{self.count} segments" + (f"  [typed: {self._typed}]" if self._typed else "")
        else:
            what = f"length {unit_text(context, self.length)}" + (f"  [typed: {self._typed}]" if self._typed else "")
        txt = (f"Divide : {what}  ({len(pts)} points)   |   Up/Down or wheel: change   digits: type a value   "
               f"Tab: number / length   E: end points {'ON' if self.ends else 'OFF'}   Enter/click: validate   Esc: cancel")
        try:
            context.area.header_text_set(txt)
            context.area.tag_redraw()
        except (AttributeError, ReferenceError):
            pass

    def finish_modal(self, context):
        try:
            bpy.types.SpaceView3D.draw_handler_remove(self._h, 'WINDOW')
        except (ValueError, AttributeError):
            pass
        try:
            context.area.header_text_set(None)
            context.area.tag_redraw()
        except (AttributeError, ReferenceError):
            pass

    def invoke(self, context, event):
        objs = [o for o in context.selected_objects if o.type in {'MESH', 'CURVE'}]
        if not objs:
            self.report({'INFO'}, "Select the curves to divide (click them, then Enter)")
            return {'CANCELLED'}
        dg = context.evaluated_depsgraph_get()
        self._paths = [pp for o in objs for pp in object_paths(o, dg)]
        if not self._paths:
            self.report({'WARNING'}, "No curve to divide in the selection")
            return {'CANCELLED'}
        total = sum(path_length(P, c) for P, c in self._paths)
        self.length = max(total / max(self.count, 1) / max(len(self._paths), 1), 1e-5)
        self._typed = ""
        self._pts = self.points(context)
        self._h = bpy.types.SpaceView3D.draw_handler_add(self.draw_points, (), 'WINDOW', 'POST_VIEW')
        context.window_manager.modal_handler_add(self)
        self.status(context)
        return {'RUNNING_MODAL'}

    def draw_points(self):
        pts = self._pts
        if not pts:
            return
        shader = get_shader('3D')
        gpu.state.blend_set('ALPHA')
        draw_px_points(pts, 8.0 * px_scale(0.35), (1.0, 0.8, 0.1, 1.0))
        gpu.state.blend_set('NONE')

    def modal(self, context, event):
        if context.area is None:
            self.finish_modal(context)
            return {'CANCELLED'}
        t, v = event.type, event.value
        if t in {'ESC', 'RIGHTMOUSE'} and v == 'PRESS':
            self.finish_modal(context)
            return {'CANCELLED'}
        if (t in {'RET', 'NUMPAD_ENTER', 'SPACE', 'LEFTMOUSE'}) and v == 'PRESS':
            if self._typed:
                try:
                    x = float(self._typed)
                    if self.mode == 'COUNT':
                        self.count = max(2, min(500, int(x)))
                    else:
                        self.length = max(1e-5, x * unit_scale_of(context))
                except ValueError:
                    pass
            self.finish_modal(context)
            res = self.execute(context)
            _idle_later()
            return res
        if v != 'PRESS' and not (t in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}):
            return {'PASS_THROUGH'}
        step = 0
        if t in {'UP_ARROW', 'RIGHT_ARROW', 'WHEELUPMOUSE', 'NUMPAD_PLUS', 'EQUAL'}:
            step = 1
        elif t in {'DOWN_ARROW', 'LEFT_ARROW', 'WHEELDOWNMOUSE', 'NUMPAD_MINUS', 'MINUS'} and not self._typed:
            step = -1
        if step:
            self._typed = ""
            if self.mode == 'COUNT':
                self.count = max(2, min(500, self.count + step))
            else:
                self.length = max(1e-5, self.length * (1.1 if step > 0 else 1 / 1.1))
        elif t == 'TAB':
            self.mode = 'LENGTH' if self.mode == 'COUNT' else 'COUNT'
            self._typed = ""
        elif t == 'E':
            self.ends = not self.ends
        elif t == 'BACK_SPACE':
            self._typed = self._typed[:-1]
        elif event.unicode and event.unicode in "0123456789.":
            self._typed += event.unicode
        else:
            return {'PASS_THROUGH'}
        if self._typed:
            try:
                x = float(self._typed)
                if self.mode == 'COUNT':
                    self.count = max(2, min(500, int(x)))
                else:
                    self.length = max(1e-5, x * unit_scale_of(context))
            except ValueError:
                pass
        self._pts = self.points(context)
        self.status(context)
        return {'RUNNING_MODAL'}

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, "mode", expand=True)
        col.prop(self, "count" if self.mode == 'COUNT' else "length")
        col.prop(self, "ends")

    def execute(self, context):
        objs = [o for o in context.selected_objects if o.type in {'MESH', 'CURVE'}]
        if not objs:
            self.report({'INFO'}, "Select the curves to divide (click them, then Enter)")
            return {'CANCELLED'}
        dg = context.evaluated_depsgraph_get()
        pts = []
        for o in objs:
            for P, closed in object_paths(o, dg):
                pts += _divide_points(P, closed, self.mode, self.count, self.length, self.ends)
        if not pts:
            self.report({'WARNING'}, "No curve to divide in the selection")
            return {'CANCELLED'}
        if len(pts) > 2000:
            self.report({'WARNING'}, f"Too many points ({len(pts)}, limit 2000): use fewer segments or a longer length")
            return {'CANCELLED'}
        # un seul objet (croix de repère) : des centaines d'Empties ralentiraient tous les accrochages
        coll = context.view_layer.active_layer_collection.collection
        for o in context.selected_objects:
            o.select_set(False)
        allp = np.array([tuple(p) for p in pts], dtype=np.float64)
        span = float(np.linalg.norm(allp.max(axis=0) - allp.min(axis=0)))
        size = min(max(span / 150.0, 1e-4), 0.05 if span < 5 else span / 150.0)
        verts, edges = [], []
        for p in pts:
            c = len(verts)
            verts.append(tuple(p))
            for ax in range(3):
                for sgn in (-1.0, 1.0):
                    q = list(p)
                    q[ax] += sgn * size
                    edges.append((c, len(verts)))
                    verts.append(tuple(q))
        me = bpy.data.meshes.new("Divide Points")
        me.from_pydata(verts, edges, [])
        me.update()
        ob = bpy.data.objects.new("Divide Points", me)
        ob["cad_noGrab"] = True
        coll.objects.link(ob)
        ob.select_set(True)
        context.view_layer.objects.active = ob
        self.report({'INFO'}, f"{len(pts)} point(s) created")
        return {'FINISHED'}


def _idle_later():
    """Retour à Select / Move juste après la fin de la commande (hors de l'opérateur en cours)."""
    def _go():
        back_to_idle()
        return None
    try:
        bpy.app.timers.register(_go, first_interval=0.05)
    except (RuntimeError, ValueError):
        pass


_FAR = {"told": False}


def far_origin_step(p, scale_length=1.0):
    """Plus petit pas (en mètres) que Blender peut représenter au point p : ses coordonnées sont stockées sur 24 bits
    (environ 7 chiffres), donc le pas grandit avec la distance à l'origine."""
    try:
        a = max(abs(float(p[0])), abs(float(p[1])), abs(float(p[2])))
    except (TypeError, ValueError, IndexError):
        return 0.0
    if not (a > 0.0) or a == float('inf'):
        return 0.0
    return float(np.spacing(np.float32(a))) * (scale_length or 1.0)


def far_origin_check(op, context, p):
    """Un message, une fois par fichier, quand on dessine si loin de l'origine que le pas des coordonnées dépasse 0,05 mm."""
    if _FAR["told"]:
        return False
    try:
        if not pref("far_warning"):
            return False
        sl = context.scene.unit_settings.scale_length or 1.0
        step = far_origin_step(p, sl)
        if step < 5e-5:
            return False
        _FAR["told"] = True
        dist = max(abs(float(p[0])), abs(float(p[1])), abs(float(p[2]))) * sl
        far = f"{dist / 1000.0:.1f} km" if dist >= 1000.0 else f"{dist:.0f} m"
        op.report({'WARNING'}, f"Far from the origin ({far}): Blender stores coordinates with about 7 digits, so the smallest step "
                               f"here is {step * 1000.0:.2f} mm. Work near the origin for exact dimensions")
        return True
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
        return False


def unit_scale_of(context):
    """Longueurs saisies : unités Blender par unité affichée de la scène (mm, cm, m, pouces...), comme les autres outils."""
    try:
        return unit_info(context.scene)[0]
    except AttributeError:
        return 1.0


def unit_text(context, value):
    """Longueur (unités Blender) écrite dans l'unité affichée de la scène : « 6 mm »."""
    try:
        f, label = unit_info(context.scene)
    except AttributeError:
        f, label = 1.0, ""
    return f"{value / (f or 1.0):.4g}" + (f" {label}" if label else "")


# --------------------------------------------------------------------------
# Fillet Curve / Chamfer Curve (arrondir ou chanfreiner les angles de polylignes et de lignes)
# --------------------------------------------------------------------------

CORNER_STATE = {"fillet": 0.05, "chamfer": 0.05}


def corner_points(prev, p, nxt, r, chamfer, dmax_prev, dmax_next):
    """Points qui remplacent le sommet p (angle prev-p-nxt) : arc de rayon r (congé) ou coupe à la distance r (chanfrein).
    Retourne None si l'angle est (presque) plat ou si le rayon est nul."""
    u = prev - p
    w = nxt - p
    lu, lw = u.length, w.length
    if lu < 1e-9 or lw < 1e-9 or r <= 1e-9:
        return None
    u = u / lu
    w = w / lw
    th = math.acos(max(-1.0, min(1.0, u.dot(w))))          # angle intérieur
    if th > math.pi - math.radians(8.0) or th < 0.05:
        return None
    d = r if chamfer else r / math.tan(th / 2.0)
    d = min(d, dmax_prev, dmax_next)
    if d < 1e-9:
        return None
    a = p + u * d
    b = p + w * d
    if chamfer:
        return [a, b]
    rr = d * math.tan(th / 2.0)
    c = p + (u + w).normalized() * (rr / math.sin(th / 2.0))
    va, vb = a - c, b - c
    phi = math.pi - th
    n = max(2, int(math.ceil(math.degrees(phi) / 2.5)))      # pas de 2,5° : écart à l'arc idéal sous 0,03 % du rayon
    sp = math.sin(phi)
    pts = []
    for i in range(n + 1):
        t = i / n
        pts.append(c + va * (math.sin((1.0 - t) * phi) / sp) + vb * (math.sin(t * phi) / sp))
    pts[0], pts[-1] = a, b
    return pts


def round_path(P, closed, r, chamfer, only=None):
    """Arrondit (ou chanfreine) les angles d'un contour. P : liste de Vector. Retourne (points, nombre d'angles traités)."""
    pts = [Vector(p) for p in P]
    if only is None:                       # points consécutifs confondus : l'angle ne serait pas vu
        pts = [p for i, p in enumerate(pts) if i == 0 or (p - pts[i - 1]).length > 1e-9]
        if closed and len(pts) > 1 and (pts[0] - pts[-1]).length <= 1e-9:
            pts.pop()
    n = len(pts)
    idx = range(n) if closed else range(1, n - 1)
    todo = {}
    for i in idx:
        if only is not None and i not in only:
            continue
        a, b, c = pts[(i - 1) % n], pts[i], pts[(i + 1) % n]
        if r > 1e-9 and corner_points(a, b, c, r, chamfer, 1e18, 1e18) is not None:
            todo[i] = True
    out = []
    count = 0
    for i in range(n):
        if i not in todo:
            out.append(pts[i])
            continue
        a, b, c = pts[(i - 1) % n], pts[i], pts[(i + 1) % n]
        la, lc = (a - b).length, (c - b).length
        ma = la * 0.5 if (i - 1) % n in todo else la
        mc = lc * 0.5 if (i + 1) % n in todo else lc
        res = corner_points(a, b, c, r, chamfer, ma, mc)
        if res:
            out.extend(res)
            count += 1
        else:
            out.append(b)
    return out, count


def _line_meet(p0, d0, p1, d1):
    """Point d'intersection de deux droites (ou None si parallèles / non coplanaires) : (point, t0, t1)."""
    n = d0.cross(d1)
    nn = n.length_squared
    if nn < 1e-12:
        return None
    w = p1 - p0
    t0 = w.cross(d1).dot(n) / nn
    t1 = w.cross(d0).dot(n) / nn
    q0, q1 = p0 + d0 * t0, p1 + d1 * t1
    scale = max((p1 - p0).length, 1e-6)
    if (q0 - q1).length > 1e-4 * scale + 1e-6:
        return None
    return (q0 + q1) * 0.5, t0, t1


def join_corner(PA, PB):
    """Relie deux polylignes ouvertes par un angle vif (prolonge ou raccourcit leurs derniers segments).
    Retourne (points, indice de l'angle) ou None."""
    A = [Vector(p) for p in PA]
    B = [Vector(p) for p in PB]
    best = None
    for fa in (False, True):
        for fb in (False, True):
            ea = A[0] if fa else A[-1]
            eb = B[0] if fb else B[-1]
            d = (ea - eb).length
            if best is None or d < best[0]:
                best = (d, fa, fb)
    _d, fa, fb = best
    A2 = A[::-1] if fa else A            # le bout choisi de A en dernier
    B2 = B if fb else B[::-1]            # le bout choisi de B en premier
    if len(A2) < 2 or len(B2) < 2:
        return None
    da = (A2[-1] - A2[-2])
    db = (B2[0] - B2[1])
    if da.length < 1e-9 or db.length < 1e-9:
        return None
    da.normalize()
    db.normalize()
    hit = _line_meet(A2[-2], da, B2[1], db)
    if hit is None:
        return None
    X, ta, tb = hit
    if ta <= 1e-9 or tb <= 1e-9:
        return None
    pts = A2[:-1] + [X] + B2[1:]
    return pts, len(A2) - 1


class DessinCornerRound(bpy.types.Operator):
    """Base de Fillet Curve / Chamfer Curve (classe non enregistrée)."""
    bl_options = {'REGISTER', 'UNDO'}
    CHAMFER = False
    KEY = "fillet"
    WORD = "radius"
    TITLE = "Fillet Curve"

    radius: bpy.props.FloatProperty(name="Radius", default=0.05, min=0.0, max=1000.0, precision=5, subtype='DISTANCE')

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and context.area is not None and context.area.type == 'VIEW_3D'

    def collect(self, context):
        """Objets sélectionnés exploitables : [(objet, [(P monde (n,3), fermé)])] et nombre d'objets ignorés."""
        items, skipped = [], 0
        dg = context.evaluated_depsgraph_get()
        for o in context.selected_objects:
            if o.type == 'CURVE':
                if any(sp.type != 'POLY' for sp in o.data.splines):
                    skipped += 1
                    continue
                mw = np.array(o.matrix_world, dtype=np.float64)
                paths = []
                for sp in o.data.splines:
                    if len(sp.points) < 2:
                        continue
                    P = np.array([tuple(p.co[:3]) for p in sp.points], dtype=np.float64) @ mw[:3, :3].T + mw[:3, 3]
                    paths.append((P, bool(sp.use_cyclic_u) and len(P) >= 3))
            elif o.type == 'MESH':
                if len(o.data.polygons):
                    skipped += 1
                    continue
                paths = object_paths(o, dg)
            else:
                continue
            if paths:
                items.append((o, paths))
        return items, skipped

    def plan(self, items, r):
        """Calcule le résultat : {"join": bool, "results": [(objet, [(points, fermé)])], "count": n, "remove": [objets]}."""
        if len(items) == 2 and all(len(p) == 1 and not p[0][1] for _o, p in items):
            hit = join_corner(items[0][1][0][0], items[1][1][0][0])
            if hit is not None:
                pts, k = hit
                out, cnt = round_path(pts, False, r, self.CHAMFER, only={k})
                return {"join": True, "results": [(items[0][0], [(out, False)])], "count": max(cnt, 1), "remove": [items[1][0]]}
        results, total = [], 0
        for o, paths in items:
            new, cnt = [], 0
            for P, closed in paths:
                out, c = round_path(P, closed, r, self.CHAMFER)
                new.append((out, closed))
                cnt += c
            if cnt:
                results.append((o, new))
                total += cnt
        return {"join": False, "results": results, "count": total, "remove": []}

    def status(self, context):
        typed = f"  [typed: {self._typed}]" if self._typed else ""
        pl = self._plan
        what = ("corner joined" if pl["join"] else f"{pl['count']} corner(s)") if pl["count"] else "no corner"
        txt = (f"{self.TITLE} : {self.WORD} {unit_text(context, self.radius)}{typed}  ({what})   |   Up/Down or wheel: change   digits: type a value   "
               f"Enter/click: validate   Esc: cancel")
        try:
            context.area.header_text_set(txt)
            context.area.tag_redraw()
        except (AttributeError, ReferenceError):
            pass

    def finish_modal(self, context):
        try:
            bpy.types.SpaceView3D.draw_handler_remove(self._h, 'WINDOW')
        except (ValueError, AttributeError):
            pass
        try:
            context.area.header_text_set(None)
            context.area.tag_redraw()
        except (AttributeError, ReferenceError):
            pass

    def refresh(self, context):
        self._plan = self.plan(self._items, self.radius)

    def invoke(self, context, event):
        items, skipped = self.collect(context)
        if not items:
            self.report({'INFO'}, "Select the polylines to " + ("round" if not self.CHAMFER else "chamfer")
                        + " (click them, then Enter)" + ("   (Bezier / NURBS curves are not supported)" if skipped else ""))
            return {'CANCELLED'}
        self._items = items
        self.radius = max(CORNER_STATE[self.KEY], 1e-5)
        self._typed = ""
        self.refresh(context)
        self._h = bpy.types.SpaceView3D.draw_handler_add(self.draw_preview, (), 'WINDOW', 'POST_VIEW')
        context.window_manager.modal_handler_add(self)
        self.status(context)
        return {'RUNNING_MODAL'}

    def draw_preview(self):
        try:
            res = self._plan["results"]
        except AttributeError:
            return
        segs = []
        for _o, paths in res:
            for pts, closed in paths:
                q = list(pts) + ([pts[0]] if closed else [])
                for a, b in zip(q, q[1:]):
                    segs += [tuple(a), tuple(b)]
        if not segs:
            return
        shader = get_shader('3D')
        gpu.state.blend_set('ALPHA')
        gpu.state.line_width_set(3.0 * px_scale())
        batch = batch_for_shader(shader, 'LINES', {"pos": segs})
        shader.bind()
        shader.uniform_float("color", (1.0, 0.8, 0.1, 1.0))
        batch.draw(shader)
        gpu.state.line_width_set(1.0)
        gpu.state.blend_set('NONE')

    def modal(self, context, event):
        if context.area is None:
            self.finish_modal(context)
            return {'CANCELLED'}
        t, v = event.type, event.value
        if t in {'ESC', 'RIGHTMOUSE'} and v == 'PRESS':
            self.finish_modal(context)
            return {'CANCELLED'}
        if t in {'RET', 'NUMPAD_ENTER', 'SPACE', 'LEFTMOUSE'} and v == 'PRESS':
            if self._typed:
                try:
                    self.radius = max(0.0, float(self._typed) * unit_scale_of(context))
                except ValueError:
                    pass
            self.finish_modal(context)
            CORNER_STATE[self.KEY] = max(self.radius, 1e-5)
            res = self.execute(context)
            _idle_later()
            return res
        if v != 'PRESS' and t not in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}
        step = 0
        if t in {'UP_ARROW', 'RIGHT_ARROW', 'WHEELUPMOUSE', 'NUMPAD_PLUS', 'EQUAL'}:
            step = 1
        elif t in {'DOWN_ARROW', 'LEFT_ARROW', 'WHEELDOWNMOUSE', 'NUMPAD_MINUS'} or (t == 'MINUS' and not self._typed):
            step = -1
        if step:
            self._typed = ""
            self.radius = max(1e-5, self.radius * (1.1 if step > 0 else 1 / 1.1))
        elif t == 'BACK_SPACE':
            self._typed = self._typed[:-1]
        elif event.unicode and event.unicode in "0123456789.":
            self._typed += event.unicode
        else:
            return {'PASS_THROUGH'}
        if self._typed:
            try:
                self.radius = max(0.0, float(self._typed) * unit_scale_of(context))
            except ValueError:
                pass
        self.refresh(context)
        self.status(context)
        return {'RUNNING_MODAL'}

    def draw(self, context):
        self.layout.prop(self, "radius", text=self.WORD.capitalize())

    @staticmethod
    def write_paths(o, paths):
        """Remplace la géométrie de l'objet (courbe POLY ou contour en maillage) par les contours donnés (points monde)."""
        inv = np.linalg.inv(np.array(o.matrix_world, dtype=np.float64))
        if o.type == 'CURVE':
            cu = o.data
            cu.splines.clear()
            for pts, closed in paths:
                sp = cu.splines.new('POLY')
                sp.points.add(len(pts) - 1)
                for pt, q in zip(sp.points, pts):
                    l = inv[:3, :3] @ np.array(tuple(q)) + inv[:3, 3]
                    pt.co = (l[0], l[1], l[2], 1.0)
                sp.use_cyclic_u = bool(closed)
            cu.update_tag()
        else:
            verts, edges = [], []
            for pts, closed in paths:
                base = len(verts)
                for q in pts:
                    l = inv[:3, :3] @ np.array(tuple(q)) + inv[:3, 3]
                    verts.append((l[0], l[1], l[2]))
                n = len(pts)
                edges += [(base + i, base + i + 1) for i in range(n - 1)]
                if closed and n > 2:
                    edges.append((base + n - 1, base))
            me = o.data
            me.clear_geometry()
            me.from_pydata(verts, edges, [])
            me.update()

    def execute(self, context):
        items, skipped = self.collect(context)
        if not items:
            self.report({'INFO'}, "Select the polylines first")
            return {'CANCELLED'}
        plan = self.plan(items, self.radius)
        if not plan["count"]:
            self.report({'WARNING'}, "No corner to " + ("round" if not self.CHAMFER else "chamfer")
                        + " (angles too flat, or the distance is too small / larger than the segments)")
            return {'CANCELLED'}
        for o, paths in plan["results"]:
            self.write_paths(o, paths)
        for o in plan["remove"]:
            try:
                bpy.data.objects.remove(o, do_unlink=True)
            except (ReferenceError, RuntimeError):
                pass
        keep = plan["results"][0][0]
        for o in list(context.selected_objects):
            o.select_set(False)
        keep.select_set(True)
        context.view_layer.objects.active = keep
        msg = "Corner joined" if plan["join"] else f"{plan['count']} corner(s) processed"
        if skipped:
            msg += f"  ({skipped} Bezier / NURBS or surface object(s) ignored)"
        self.report({'INFO'}, msg)
        return {'FINISHED'}


class DESSIN_OT_fillet_curve(DessinCornerRound):
    bl_idname = "dessin.fillet_curve"
    bl_label = "Fillet Curve"
    bl_description = ("Rounds the corners of the selected polylines with an arc, or joins two lines with a rounded corner: "
                      "type the radius or use the wheel, Enter to validate")
    KEY = "fillet"
    WORD = "radius"
    TITLE = "Fillet Curve"
    CHAMFER = False


class DESSIN_OT_chamfer_curve(DessinCornerRound):
    bl_idname = "dessin.chamfer_curve"
    bl_label = "Chamfer Curve"
    bl_description = ("Cuts the corners of the selected polylines at a distance, or joins two lines with a chamfered corner: "
                      "type the distance or use the wheel, Enter to validate")
    KEY = "chamfer"
    WORD = "distance"
    TITLE = "Chamfer Curve"
    CHAMFER = True


def _late_imports():
    """Noms définis dans des modules chargés après celui-ci : ils ne servent qu'à l'exécution des outils."""
    global back_to_idle, object_paths, path_length
    from .offset_extrude import back_to_idle
    from .surfaces import object_paths, path_length
