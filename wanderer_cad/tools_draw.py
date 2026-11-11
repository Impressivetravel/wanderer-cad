"""Wanderer CAD : Outils de dessin 2D : rectangle, polyligne, courbes, cercle, ellipse, arc, polygones."""

import bpy
import math
import numpy as np
import time
from bpy_extras.view3d_utils import region_2d_to_origin_3d, region_2d_to_vector_3d
from mathutils import Vector, geometry

from .core import (
    SNAP_RADIUS, TAU, _link_object, arc_samples, build_plane, build_polyline, build_shape_mesh,
    circle_through_origin, drawing_axis, edit_add_geometry, idle_tool, plane_axes, plane_origin,
)
from .drawing import _TAN, find_window_region, project_px, px_scale, region_rv3d
from .base import DessinBase


# --------------------------------------------------------------------------
# Outils
# --------------------------------------------------------------------------

class DESSIN_OT_rectangle(DessinBase):
    bl_idname = "dessin.rectangle"
    bl_label = "Rectangle"
    bl_description = "Draws a rectangle with the mouse, with snapping (C: from center)"

    TITLE = "Rectangle"
    PROP = (1,)
    NEEDED = 2
    NUMFIELDS = 2
    HAS_CENTER = True

    def prompt(self):
        if not self.points:
            return "first corner" + (" (center)" if self.center else "") + "   [C: from center]"
        return "opposite corner   (Shift: square, or type width, Tab, height, Enter)"

    def compute(self):
        if not self.points or self.cur is None:
            return [], [], "", None
        o = self.points[0]
        u, v, _ = plane_axes(self.axis)
        d = self.cur - o
        du, dv = d.dot(u), d.dot(v)
        w = self.sized(0, 2 * du if self.center else du, du)
        h = self.sized(1, 2 * dv if self.center else dv, dv)
        if abs(w) < 1e-9 or abs(h) < 1e-9:
            return [], [], "", None
        a0, b0 = (-w / 2.0, -h / 2.0) if self.center else (0.0, 0.0)
        uv = [(a0, b0), (a0 + w, b0), (a0 + w, b0 + h), (a0, b0 + h)]
        corners = [o + u * a + v * b for a, b in uv]
        info = f"Width {self.fmt(abs(w))}   Height {self.fmt(abs(h))}"
        return corners + [corners[0]], [], info, ("rect", corners)


class _PlanBody(DessinBase):
    bl_idname = "dessin.plan"
    bl_label = "Plane"
    bl_description = ("Draws a plane (one face): first corner then opposite corner, with snapping (C: from center, or type width / Tab / height)")

    TITLE = "Plane"
    PROP = (1,)
    NEEDED = 2
    NUMFIELDS = 2
    HAS_CENTER = True

    # même saisie et même aperçu que le rectangle (fonctions réutilisées, pas d'héritage entre classes Blender)
    prompt = DESSIN_OT_rectangle.prompt
    compute = DESSIN_OT_rectangle.compute

    def build(self, context, spec):
        if spec[0] == 'rect' and context.mode == 'EDIT_MESH':
            corners = list(spec[1])
            face = [0, 1, 2, 3]
            if (corners[1] - corners[0]).cross(corners[2] - corners[1]).dot(plane_axes(self.axis)[2]) < 0:
                face.reverse()
            return edit_add_geometry(context, corners, [], [face])
        if spec[0] == 'rect':
            return build_plane(context, "Plane", spec[1], plane_axes(self.axis)[2], self.points[0].copy())
        return super().build(context, spec)

    def after_finish(self, context):
        """Comme les autres outils de la barre : la commande terminée rend la main à la sélection."""
        if self.tool_id:
            try:
                idle_tool()
            except (RuntimeError, TypeError):
                pass


class DESSIN_OT_plan(_PlanBody):
    """Registered class; the shared code lives in the unregistered base so SubD variants can inherit it."""
    bl_idname = _PlanBody.bl_idname
    bl_label = _PlanBody.bl_label
    bl_description = _PlanBody.bl_description


class PolylineBase(DessinBase):
    """Saisie point par point (classe non enregistrée) : polyligne, courbe à points de contrôle."""
    NEEDED = 2
    NUMFIELDS = 1  # longueur du segment
    CAN_CLOSE = False   # C ferme sur le premier point (Polyline et courbes, comme l'option Close de Rhino / AutoCAD)

    def prompt(self):
        n = len(self.points)
        if n == 0:
            return "first point"
        txt = "next point   (Shift: orthogonal, or type the length then Enter)"
        if n >= 3:
            txt += "   [click the first point" + (" or C" if self.CAN_CLOSE else "") + ": close]"
        return txt + "   [Backspace: undo last point, Enter: finish]"

    TAN_PAIR = True     # Tan sur deux cercles : la 2e accroche calcule la tangente commune (comme Rhino)

    def tan_update(self, context, event):
        """Appelle l'accrochage avec l'état Tan (cercle mémorisé au 1er point) et recale le 1er point sur la tangente."""
        n = len(self.points)
        pend = getattr(self, "tan_pend", None)
        _TAN["first_ok"] = (n == 0)
        _TAN["pend"] = pend if (n == 1 and pend is not None) else None
        try:
            super().update_cursor(context, event)
        finally:
            _TAN["first_ok"] = False
            _TAN["pend"] = None
        info = _TAN["info"] if getattr(self, "snap_kind", None) == 10 else None
        self._tan_info = info
        if n == 0:
            self.tan_pend = None
        if len(self.points) == 1 and pend is not None:
            p0 = getattr(self, "tan_p0", None)
            if info is not None and info[0] == "common":
                self.points[0] = info[1].copy()
            elif p0 is not None:
                self.points[0] = p0.copy()

    def update_cursor(self, context, event):
        self.ortho = bool(event.shift)
        self.closing = False
        self.tan_update(context, event)
        if (not self.points or self.cur is None or not self.snap_on or self.lock is not None
                or self.mouse_over_ui(event)):
            return
        region = self.region
        rv3d = region_rv3d(region, self.area)
        m = Vector((event.mouse_x - region.x, event.mouse_y - region.y))
        best, best_d = None, SNAP_RADIUS * px_scale()
        for i, q in enumerate(self.points):
            sp = project_px(rv3d, region, q)
            if sp is None:
                continue
            dist = (sp - m).length
            if dist < best_d:
                best, best_d, best_sp = i, dist, sp
        if best is None:
            return
        if best == len(self.points) - 1 and len(self.points) > 1:
            return  # inutile de s'accrocher au dernier point posé
        self.closing = best == 0 and len(self.points) >= 3
        self.cur = self.points[best].copy()
        self.snap_screen = (best_sp.x, best_sp.y)
        self.snap_kind = 0
        self.refresh(context)

    def effective_point(self):
        if self.cur is None:
            return None
        if not self.points:
            return self.cur.copy()
        if getattr(self, "closing", False):
            return self.points[0].copy()
        last = self.points[-1]
        u, v, _ = plane_axes(self.axis)
        d = self.cur - last
        du, dv = d.dot(u), d.dot(v)
        if self.ortho and not self.snap_screen:
            if abs(du) >= abs(dv):
                dv = 0.0
            else:
                du = 0.0
        vec = u * du + v * dv
        t = self.typed_value(0)
        if t is not None:
            vec = (vec / vec.length if vec.length > 1e-9 else u) * t
        return last + vec

    def compute(self):
        if not self.points or self.cur is None:
            return [], [], "", None
        p = self.effective_point()
        pts = list(self.points) + [p]
        seg = (p - self.points[-1]).length
        total = sum((b - a).length for a, b in zip(self.points, self.points[1:])) + seg
        info = f"Segment {self.fmt(seg)}   Total {self.fmt(total)}"
        if getattr(self, "closing", False):
            info += "   [fermeture]"
        return pts, [], info, None

    def add_point(self, context):
        p = self.effective_point()
        if p is None:
            return
        if self.points and (p - self.points[-1]).length < 1e-9:
            return
        info = getattr(self, "_tan_info", None)
        if not self.points:
            # 1er point posé sur un cercle avec Tan : on le mémorise, le 2e clic Tan en déduira la tangente commune
            self.tan_pend = info[1] if (info is not None and info[0] == "first") else None
            self.tan_p0 = p.copy()
        elif len(self.points) == 1:
            self.tan_pend = None
        self.points.append(p)
        self.typed = ['', '']
        self.lock = None
        self.update_preview(context)

    def update_preview(self, context):
        self.refresh(context)

    def build_result(self, context, closed):
        if len(self.points) < 2:
            return False
        if context.mode == 'EDIT_MESH':
            n = len(self.points)
            edges = [(i, i + 1) for i in range(n - 1)] + ([(n - 1, 0)] if closed else [])
            edit_add_geometry(context, list(self.points), edges, [])
        else:
            build_polyline(context, "Polyline", list(self.points), closed)      # les outils de courbe créent toujours une vraie courbe
        self.finished = True
        return True

    def click(self, context):
        if getattr(self, "closing", False):
            if self.build_result(context, True):
                self.reset_state()
            return
        self.add_point(context)

    def modal(self, context, event):
        if (event.value == 'PRESS' and not (event.ctrl or event.alt or event.oskey)
                and self.area is not None and context.area is not None
                and find_window_region(self.area, event.mouse_x, event.mouse_y) is not None
                and not self.mouse_over_ui(event)):
            if event.type in {'RET', 'NUMPAD_ENTER', 'SPACE'}:
                if self.points and any(self.typed):
                    self.add_point(context)       # longueur saisie : on pose le point, la commande continue
                    return {'RUNNING_MODAL'}
                if self.build_result(context, False):
                    self.reset_state()
                return self.exit(context)
            if event.type == 'BACK_SPACE' and self.points and not any(self.typed):
                self.points.pop()
                self.preview = []
                self.refresh(context)
                return {'RUNNING_MODAL'}
            if (event.type == 'C' and self.CAN_CLOSE and len(self.points) >= 3
                    and not any(self.typed) and not event.shift):
                # C : ferme sur le premier point, comme l'option Close de Rhino / AutoCAD
                if self.build_result(context, True):
                    self.reset_state()
                if self.finished:
                    return self.exit(context)
                return {'RUNNING_MODAL'}
        return super().modal(context, event)

    def undo_step(self, context, event):
        # Ctrl+Z : retire le dernier point posé (option Undo de Rhino / AutoCAD), sans toucher au reste de la scène
        if self.points and not any(self.typed):
            self.points.pop()
            self.preview = []
            self.refresh(context)
        return {'RUNNING_MODAL'}

    def after_finish(self, context):
        if self.tool_id:
            try:
                idle_tool()
            except (RuntimeError, TypeError):
                pass


class DESSIN_OT_polyligne(PolylineBase):
    bl_idname = "dessin.polyligne"
    bl_label = "Polyline"
    bl_description = ("Draws a polyline point by point with snapping. Click the first point (or press C) to close the shape. Enter: finish, Backspace: undo last point")

    TITLE = "Polyline"
    CAN_CLOSE = True


def bspline_samples(pts, degree, closed, per_span=16):
    """Points d'une B-spline uniforme (extrémités accrochées si ouverte, périodique si fermée) définie par ses points de contrôle."""
    P = np.array([tuple(p) for p in pts], dtype=np.float64)
    n = len(P)
    d = max(1, min(degree, n - 1))
    if closed:
        P = np.vstack((P, P[:d]))
        m = len(P)
        knots = np.arange(m + d + 1, dtype=np.float64)
        t0, t1 = float(d), float(m)
    else:
        m = n
        knots = np.array([0.0] * (d + 1) + list(range(1, n - d)) + [float(n - d)] * (d + 1))
        t0, t1 = 0.0, float(n - d)
    count = max(2, int(round((t1 - t0) * per_span)) + 1)
    out = []
    for t in np.linspace(t0, t1, count):
        k = int(np.searchsorted(knots, t, side='right') - 1)
        k = max(d, min(k, m - 1))
        dd = [P[j + k - d].copy() for j in range(d + 1)]
        for r in range(1, d + 1):
            for j in range(d, r - 1, -1):
                den = knots[j + 1 + k - r] - knots[j + k - d]
                a = (t - knots[j + k - d]) / den if den > 1e-12 else 0.0
                dd[j] = (1.0 - a) * dd[j - 1] + a * dd[j]
        out.append(Vector(dd[d]))
    return out


class CurveCpLogic(PolylineBase):
    bl_idname = "dessin.curve_cp"
    bl_label = "Control Point Curve"
    bl_description = ("Draws a curve from its control points (the curve follows them without crossing them), with snapping. "
                      "D: degree 3 / 2 / 5, click the first point (or press C) to close, Enter: finish, Backspace: undo last point")

    TITLE = "Control Point Curve"
    CAN_CLOSE = True
    HAS_MODE = True
    MODES = ("Degree 3", "Degree 2", "Degree 5")
    DEGREES = (3, 2, 5)
    mode = 0

    def prompt(self):
        m = self.MODES[self.mode]
        if not self.points:
            return f"first control point   [D: {m}]"
        txt = f"next control point   [D: {m}]"
        if len(self.points) >= 3:
            txt += "   [click the first point: close]"
        return txt + "   [Backspace: undo last point, Enter: finish]"

    def curve_points(self, pts, closed):
        return bspline_samples(pts, self.DEGREES[self.mode], closed)

    def compute(self):
        if not self.points or self.cur is None:
            return [], [], "", None
        closing = getattr(self, "closing", False)
        p = self.effective_point()
        pts = list(self.points) + ([] if closing else [p])
        if len(pts) < 2:
            return [], [], "", None
        curve = self.curve_points(pts, closing) if len(pts) >= 3 else pts
        guides = [pts + ([pts[0]] if closing else [])]
        info = f"{len(pts)} control points   {self.MODES[self.mode]}" + ("   [close]" if closing else "")
        return curve, guides, info, None

    def build_result(self, context, closed):
        if len(self.points) < 2:
            return False
        pts = list(self.points)
        if closed and len(pts) < 3:
            closed = False
        mode = 'CURVE'      # les outils de courbe créent toujours une vraie courbe, quel que soit « Shapes as »
        if context.mode == 'EDIT_MESH' or mode != 'CURVE':
            samples = self.curve_points(pts, closed) if len(pts) >= 3 else pts
            if closed:
                samples = samples[:-1]
            if context.mode == 'EDIT_MESH':
                n = len(samples)
                edges = [(i, i + 1) for i in range(n - 1)] + ([(n - 1, 0)] if closed else [])
                edit_add_geometry(context, samples, edges, [])
            else:
                build_shape_mesh(context, "Control Point Curve", samples, closed, pts[0], mode, plane_axes(self.axis)[2])
        else:
            cu = bpy.data.curves.new("Control Point Curve", 'CURVE')
            cu.dimensions = '3D'
            sp = cu.splines.new('NURBS')
            sp.points.add(len(pts) - 1)
            for sp_pt, q in zip(sp.points, pts):
                sp_pt.co = (q.x, q.y, q.z, 1.0)
            sp.order_u = max(2, min(self.DEGREES[self.mode] + 1, len(pts)))
            sp.use_endpoint_u = not closed
            sp.use_cyclic_u = closed
            sp.resolution_u = 12
            _link_object(context, "Control Point Curve", cu)
        self.finished = True
        return True


class DESSIN_OT_curve_cp(CurveCpLogic):
    """Classe enregistrée (les sous-classes héritent de CurveCpLogic, non enregistrée : Blender perd le poll d'un parent enregistré)."""
    bl_idname = "dessin.curve_cp"
    bl_label = "Control Point Curve"
    bl_description = ("Draws a curve from its control points (the curve follows them without crossing them), with snapping. "
                      "D: degree 3 / 2 / 5, click the first point to close, Enter: finish, Backspace: undo last point")


def catmull_samples(pts, closed, per=14):
    """Points d'une courbe de Catmull-Rom centripète qui PASSE par chacun des points donnés."""
    P = [Vector(q) for q in pts]
    n = len(P)
    if n < 3:
        return P
    segs = n if closed else n - 1

    def at(i):
        if closed:
            return P[i % n]
        if i < 0:
            return P[0] * 2.0 - P[1]
        if i >= n:
            return P[-1] * 2.0 - P[-2]
        return P[i]

    out = []
    for i in range(segs):
        p0, p1, p2, p3 = at(i - 1), at(i), at(i + 1), at(i + 2)
        t0 = 0.0
        t1 = t0 + max((p1 - p0).length, 1e-9) ** 0.5
        t2 = t1 + max((p2 - p1).length, 1e-9) ** 0.5
        t3 = t2 + max((p3 - p2).length, 1e-9) ** 0.5
        for k in range(per):
            t = t1 + (t2 - t1) * k / per
            a1 = p0 * ((t1 - t) / (t1 - t0)) + p1 * ((t - t0) / (t1 - t0))
            a2 = p1 * ((t2 - t) / (t2 - t1)) + p2 * ((t - t1) / (t2 - t1))
            a3 = p2 * ((t3 - t) / (t3 - t2)) + p3 * ((t - t2) / (t3 - t2))
            b1 = a1 * ((t2 - t) / (t2 - t0)) + a2 * ((t - t0) / (t2 - t0))
            b2 = a2 * ((t3 - t) / (t3 - t1)) + a3 * ((t - t1) / (t3 - t1))
            out.append(b1 * ((t2 - t) / (t2 - t1)) + b2 * ((t - t1) / (t2 - t1)))
    out.append(P[0].copy() if closed else P[-1].copy())
    return out


def bezier_auto_curve(name, pts, closed):
    """Courbe de Bézier à poignées automatiques passant par les points (lissée, sans surépaisseur)."""
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    sp = cu.splines.new('BEZIER')
    sp.bezier_points.add(len(pts) - 1)
    for bp, q in zip(sp.bezier_points, pts):
        bp.co = q
        bp.handle_left_type = 'AUTO'
        bp.handle_right_type = 'AUTO'
    sp.use_cyclic_u = closed
    sp.resolution_u = 12
    return cu


class DESSIN_OT_curve_interp(CurveCpLogic):
    bl_idname = "dessin.curve_interp"
    bl_label = "Interpolate Curve"
    bl_description = ("Draws a smooth curve that passes through every point you click, with snapping. "
                      "Click the first point to close, Enter: finish, Backspace: undo last point")

    TITLE = "Interpolate Curve"
    HAS_MODE = False

    def prompt(self):
        if not self.points:
            return "first point of the curve"
        txt = "next point (the curve passes through it)"
        if len(self.points) >= 3:
            txt += "   [click the first point: close]"
        return txt + "   [Backspace: undo last point, Enter: finish]"

    def curve_points(self, pts, closed):
        return catmull_samples(pts, closed)

    def compute(self):
        curve, guides, info, spec = super().compute()
        return curve, [], info.replace(self.MODES[0], "").rstrip() if info else info, spec

    def build_result(self, context, closed):
        if len(self.points) < 2:
            return False
        pts = list(self.points)
        if closed and len(pts) < 3:
            closed = False
        mode = 'CURVE'      # les outils de courbe créent toujours une vraie courbe, quel que soit « Shapes as »
        if context.mode == 'EDIT_MESH' or mode != 'CURVE':
            samples = self.curve_points(pts, closed) if len(pts) >= 3 else pts
            if closed:
                samples = samples[:-1]
            if context.mode == 'EDIT_MESH':
                n = len(samples)
                edges = [(i, i + 1) for i in range(n - 1)] + ([(n - 1, 0)] if closed else [])
                edit_add_geometry(context, samples, edges, [])
            else:
                build_shape_mesh(context, "Interpolate Curve", samples, closed, pts[0], mode, plane_axes(self.axis)[2])
        else:
            _link_object(context, "Interpolate Curve", bezier_auto_curve("Interpolate Curve", pts, closed))
        self.finished = True
        return True


def simplify_polyline(pts, tol):
    """Ramer-Douglas-Peucker : garde les points qui s'écartent de plus de `tol` de la droite entre leurs voisins."""
    if len(pts) < 3:
        return list(pts)
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        pa, pb = pts[a], pts[b]
        ab = pb - pa
        L = ab.length
        far, far_d = -1, tol
        for i in range(a + 1, b):
            d = (pts[i] - pa).length if L < 1e-12 else (pts[i] - pa).cross(ab).length / L
            if d > far_d:
                far, far_d = i, d
        if far >= 0:
            keep[far] = True
            stack += [(a, far), (far, b)]
    return [q for q, k in zip(pts, keep) if k]


class DESSIN_OT_srf_corners(PolylineBase):
    bl_idname = "dessin.srf_corners"
    bl_label = "Surface from Corner Points"
    bl_description = ("Creates a surface from 3 or 4 corner points, with snapping: click the corners, the 4th click finishes "
                      "(Enter after the 3rd corner: triangle). Backspace: undo last point")

    TITLE = "Surface from Corner Points"
    NUMFIELDS = 0

    def prompt(self):
        n = len(self.points)
        if n == 0:
            return "first corner of surface"
        names = ("second", "third", "fourth")
        txt = f"{names[min(n - 1, 2)]} corner of surface"
        if n >= 3:
            txt = "fourth corner of surface   [Enter: triangle with 3 corners]"
        return txt + "   [Backspace: undo last point]"

    def compute(self):
        if not self.points or self.cur is None:
            return [], [], "", None
        p = self.effective_point()
        pts = list(self.points) + [p]
        return pts + [pts[0]], [], f"{len(self.points)} corner(s)", None

    def add_point(self, context):
        n = len(self.points)
        super().add_point(context)
        if len(self.points) == 4 and n == 3:
            if self.build_result(context, True):
                self.reset_state()
                self.after_finish(context)

    def build_result(self, context, closed):
        if len(self.points) < 3:
            return False
        pts = list(self.points[:4])
        if context.mode == 'EDIT_MESH':
            edit_add_geometry(context, pts, [], [list(range(len(pts)))])
        else:
            build_shape_mesh(context, "Surface", pts, True, pts[0], 'FACE', plane_axes(self.axis)[2])
        self.finished = True
        return True


class DESSIN_OT_sketch(PolylineBase):
    bl_idname = "dessin.sketch"
    bl_label = "Sketch"
    bl_description = ("Freehand drawing: press, drag the mouse and release, the stroke becomes a smooth curve. "
                      "Drag back onto the start to close it. Esc / Enter: finish")

    TITLE = "Sketch"
    NUMFIELDS = 0
    HIDE_POINTS = True      # pas de points pendant le tracé : le trait reste fluide et lisible
    LOCK_OK = False

    def invoke(self, context, event):
        self._down = False
        return super().invoke(context, event)

    def reset_state(self):
        super().reset_state()
        self._down = False

    def prompt(self):
        return "press and drag to sketch, release to finish the stroke   [Esc: leave]"

    def update_cursor(self, context, event):
        DessinBase.update_cursor(self, context, event)     # pas d'accroche aux points du tracé en cours
        self.closing = False

    def compute(self):
        if not self.points:
            return [], [], "", None
        return list(self.points), [], f"{len(self.points)} points", None

    def step_len(self):
        try:
            return max(1e-9, region_rv3d(self.region, self.area).view_distance * 0.004)
        except (AttributeError, ReferenceError, TypeError):
            return 0.01

    def fast_cursor(self, context, event):
        """Pendant le tracé : position du curseur sur le plan seulement (ni accrochages ni repérages, trop lents à chaque mouvement)."""
        region = find_window_region(self.area, event.mouse_x, event.mouse_y)
        if region is None:
            return
        self.region = region
        rv3d = region_rv3d(region, self.area)
        mx, my = event.mouse_x - region.x, event.mouse_y - region.y
        _CMD["mouse"][self.area.as_pointer()] = (mx, my)
        _CMD.setdefault("mouse_t", {})[self.area.as_pointer()] = time.monotonic()
        if not self.points:
            self.axis = drawing_axis(rv3d)
        _, _, n = plane_axes(self.axis)
        origin = self.points[0] if self.points else plane_origin(self.axis)
        coord = Vector((mx, my))
        ray_o = region_2d_to_origin_3d(region, rv3d, coord)
        ray_v = region_2d_to_vector_3d(region, rv3d, coord)
        hit = geometry.intersect_line_plane(ray_o, ray_o + ray_v, origin, n)
        if hit is not None:
            self.cur = hit
        self.snap_screen = None
        self.snap_kind = None
        self.track_lines = []
        self.track_label = ""
        self.track_screen = None

    def stroke_add(self, context, force=False):
        if self.cur is None:
            return
        p = self.cur.copy()
        if not self.points or (p - self.points[-1]).length >= self.step_len() * 0.2:      # tracé dense : l'aperçu reste fluide
            self.points.append(p)
            now = time.monotonic()
            if force or now - getattr(self, "_t_ref", 0.0) >= 0.03:      # aperçu redessiné ~30 fois par seconde au plus
                self._t_ref = now
                self.refresh(context)

    def stroke_end(self, context):
        self._down = False
        pts = list(self.points)
        tol = self.step_len() * 0.3      # ajustement fin : la courbe suit le tracé, avec peu de points
        closed = len(pts) >= 8 and (pts[0] - pts[-1]).length < self.step_len() * 4
        if closed:
            pts = pts[:-1]
        pts = simplify_polyline(pts, tol)
        self.points = pts
        if len(pts) >= 2 and self.build_stroke(context, pts, closed):
            self.finished = True
        self.reset_state()
        self.refresh(context)

    def build_stroke(self, context, pts, closed):
        if closed and len(pts) < 3:
            closed = False
        mode = 'CURVE'      # le croquis crée toujours une vraie courbe (un mesh de centaines de points n'est plus modifiable)
        if context.mode == 'EDIT_MESH' or mode != 'CURVE':
            samples = catmull_samples(pts, closed) if len(pts) >= 3 else pts
            if closed:
                samples = samples[:-1]
            if context.mode == 'EDIT_MESH':
                n = len(samples)
                edges = [(i, i + 1) for i in range(n - 1)] + ([(n - 1, 0)] if closed else [])
                edit_add_geometry(context, samples, edges, [])
            else:
                build_shape_mesh(context, "Sketch", samples, closed, pts[0], mode, plane_axes(self.axis)[2])
        else:
            _link_object(context, "Sketch", bezier_auto_curve("Sketch", pts, closed))
        try:
            bpy.ops.ed.undo_push(message="Sketch")
        except (RuntimeError, AttributeError):
            pass
        return True

    def modal(self, context, event):
        if self._down:
            if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
                self.fast_cursor(context, event)
                self.stroke_add(context)
                return {'RUNNING_MODAL'}
            if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
                self.fast_cursor(context, event)
                self.stroke_add(context, True)
                self.stroke_end(context)
                return {'RUNNING_MODAL'}
            if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
                self.reset_state()
                self.refresh(context)
                return {'RUNNING_MODAL'}
            return {'RUNNING_MODAL'}
        if (event.type == 'LEFTMOUSE' and event.value == 'PRESS' and self.area is not None and context.area is not None
                and find_window_region(self.area, event.mouse_x, event.mouse_y) is not None
                and not self.mouse_over_ui(event) and cmd_hit(self.area, event.mouse_x, event.mouse_y) is None):
            self.update_cursor(context, event)
            if self.cur is not None:
                self._down = True
                self.points = [self.cur.copy()]
                self.refresh(context)
                return {'RUNNING_MODAL'}
        if event.type in {'RET', 'NUMPAD_ENTER', 'SPACE'} and event.value == 'PRESS':
            return self.exit(context)
        return super().modal(context, event)


def bezier_path_samples(anchors, hin, hout, closed, per=16):
    """Points d'un tracé de Bézier : poignées hin / hout relatives aux ancres (fermé : le dernier point revient sur le premier)."""
    n = len(anchors)
    segs = n if closed else n - 1
    ts = np.linspace(0.0, 1.0, per + 1)[:, None]
    out = []
    for i in range(max(segs, 0)):
        j = (i + 1) % n
        p0 = np.array(tuple(anchors[i]))
        p1 = p0 + np.array(tuple(hout[i]))
        p3 = np.array(tuple(anchors[j]))
        p2 = p3 + np.array(tuple(hin[j]))
        seg = (1 - ts) ** 3 * p0 + 3 * (1 - ts) ** 2 * ts * p1 + 3 * (1 - ts) * ts ** 2 * p2 + ts ** 3 * p3
        for k, q in enumerate(seg):
            if out and k == 0:
                continue
            out.append(Vector(q))
    return out


class DESSIN_OT_pen(PolylineBase):
    bl_idname = "dessin.pen"
    bl_label = "Pen (Bezier)"
    bl_description = ("Draws a Bezier curve with anchor points and handles, like a pen tool: click = corner point, click and drag = smooth point "
                      "(Alt while dragging: break the handle). Click the first point to close, Enter: finish, Backspace: undo last point")

    TITLE = "Pen"
    NUMFIELDS = 0

    def invoke(self, context, event):
        self.hin = []
        self.hout = []
        self._drag = False
        return super().invoke(context, event)

    def reset_state(self):
        super().reset_state()
        self.hin = []
        self.hout = []
        self._drag = False

    def prompt(self):
        if not self.points:
            return "first anchor point   (click: corner, click and drag: smooth)"
        txt = "next anchor point   (click: corner, click and drag: smooth, Alt: break the handle)"
        if len(self.points) >= 3:
            txt += "   [click the first point: close]"
        return txt + "   [Backspace: undo last point, Enter: finish]"

    def add_point(self, context):
        n = len(self.points)
        super().add_point(context)
        if len(self.points) > n:
            self.hin.append(Vector((0.0, 0.0, 0.0)))
            self.hout.append(Vector((0.0, 0.0, 0.0)))
            self._drag = True

    def drag_handle(self, event):
        if not self.points or self.cur is None or len(self.hout) != len(self.points):
            return
        d = self.cur - self.points[-1]
        self.hout[-1] = d.copy()
        if not event.alt:
            self.hin[-1] = -d
        self.refresh(bpy.context)

    def compute(self):
        if not self.points or self.cur is None:
            return [], [], "", None
        pts, hin, hout = list(self.points), list(self.hin), list(self.hout)
        closing = getattr(self, "closing", False)
        if len(hin) != len(pts):
            return [], [], "", None
        if not closing and not self._drag:
            pts.append(self.effective_point())
            hin.append(Vector((0.0, 0.0, 0.0)))
            hout.append(Vector((0.0, 0.0, 0.0)))
        curve = bezier_path_samples(pts, hin, hout, closing) if len(pts) >= 2 else []
        guides = []
        for a, hi, ho in zip(self.points, self.hin, self.hout):
            if hi.length > 1e-9 or ho.length > 1e-9:
                guides.append([a + hi, a, a + ho])
        info = f"{len(self.points)} anchor points" + ("   [close]" if closing else "")
        return curve, guides, info, None

    def build_result(self, context, closed):
        if len(self.points) < 2 or len(self.hin) != len(self.points):
            return False
        pts, hin, hout = list(self.points), list(self.hin), list(self.hout)
        if closed and len(pts) < 3:
            closed = False
        mode = 'CURVE'      # l'outil Bézier crée toujours une vraie courbe (points d'ancrage et poignées modifiables), quel que soit « Shapes as »
        if context.mode == 'EDIT_MESH' or mode != 'CURVE':
            samples = bezier_path_samples(pts, hin, hout, closed)
            if closed:
                samples = samples[:-1]
            if context.mode == 'EDIT_MESH':
                n = len(samples)
                edges = [(i, i + 1) for i in range(n - 1)] + ([(n - 1, 0)] if closed else [])
                edit_add_geometry(context, samples, edges, [])
            else:
                build_shape_mesh(context, "Pen Curve", samples, closed, pts[0], mode, plane_axes(self.axis)[2])
        else:
            cu = bpy.data.curves.new("Pen Curve", 'CURVE')
            cu.dimensions = '3D'
            sp = cu.splines.new('BEZIER')
            sp.bezier_points.add(len(pts) - 1)
            for bp, q, hi, ho in zip(sp.bezier_points, pts, hin, hout):
                bp.handle_left_type = 'FREE'
                bp.handle_right_type = 'FREE'
                bp.co = q
                bp.handle_left = q + hi
                bp.handle_right = q + ho
                big = max(hi.length, ho.length)
                if big > 1e-9 and (hi + ho).length < 1e-6 * big:
                    bp.handle_left_type = 'ALIGNED'
                    bp.handle_right_type = 'ALIGNED'
            sp.use_cyclic_u = closed
            sp.resolution_u = 12
            _link_object(context, "Pen Curve", cu)
        self.finished = True
        return True

    def modal(self, context, event):
        if self._drag:
            if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
                DessinBase.update_cursor(self, context, event)   # sans l'accroche aux points posés : on règle la poignée
                self.drag_handle(event)
                return {'RUNNING_MODAL'}
            if event.type == 'LEFTMOUSE':
                if event.value == 'RELEASE':
                    self._drag = False
                    self.refresh(context)
                    return {'RUNNING_MODAL'}
                self._drag = False       # un nouveau appui alors que le relâchement a été perdu
        res = super().modal(context, event)
        n = len(self.points)
        del self.hin[n:]
        del self.hout[n:]
        return res


class DESSIN_OT_point(DessinBase):
    bl_idname = "dessin.point"
    bl_label = "Point"
    bl_description = "Places points (empties): click where each point goes, with snapping. Enter / Esc: finish"

    TITLE = "Point"
    NEEDED = 1
    NUMFIELDS = 0
    LOCK_OK = False

    def prompt(self):
        return "click to place a point   [Enter / Esc: finish]"

    def click(self, context):
        if self.cur is None:
            return
        p = self.cur.copy()
        if context.mode == 'EDIT_MESH':
            edit_add_geometry(context, [p], [], [])
        else:
            try:
                size = max(region_rv3d(self.region, self.area).view_distance * 0.012, 1e-6)
            except (AttributeError, ReferenceError, TypeError):
                size = 0.1
            obj = bpy.data.objects.new("Point", None)
            obj.empty_display_type = 'PLAIN_AXES'
            obj.empty_display_size = size
            obj.location = p
            context.view_layer.active_layer_collection.collection.objects.link(obj)
            for o in context.selected_objects:
                o.select_set(False)
            obj.select_set(True)
            context.view_layer.objects.active = obj
        self.placed = True
        try:
            bpy.ops.ed.undo_push(message="Point")
        except (RuntimeError, AttributeError):
            pass
        self.refresh(context)

    def exit(self, context):
        if getattr(self, "placed", False):
            self.finished = True
        return super().exit(context)


class DESSIN_OT_cercle(DessinBase):
    bl_idname = "dessin.cercle"
    bl_label = "Circle"
    bl_description = "Draws a circle with the mouse: center then radius, with snapping"

    TITLE = "Circle"
    NEEDED = 2
    NUMFIELDS = 1

    def prompt(self):
        if not self.points:
            return "center"
        return "radius   (or type the radius then Enter)"

    def compute(self):
        if not self.points or self.cur is None:
            return [], [], "", None
        o = self.points[0]
        u, v, _ = plane_axes(self.axis)
        d = self.cur - o
        du, dv = d.dot(u), d.dot(v)
        dist = math.hypot(du, dv)
        r = dist
        t = self.typed_value(0)
        if t is not None:
            r = abs(t)
        if r < 1e-9:
            return [], [], "", None
        prev = arc_samples(o, u, v, r, 0.0, TAU, 96)
        if dist > 1e-9:
            end = o + (u * du + v * dv) / dist * r
        else:
            end = o + u * r
        info = f"Radius {self.fmt(r)}   Diameter {self.fmt(2 * r)}"
        return prev, [[o, end]], info, ("circle", o, u, v, r)


class DESSIN_OT_cercle_diametre(DessinBase):
    bl_idname = "dessin.cercle_diametre"
    bl_label = "Circle: Diameter"
    bl_description = "Draws a circle with the mouse: two ends of the diameter, with snapping"

    TITLE = "Circle: Diameter"
    NEEDED = 2
    NUMFIELDS = 1

    def prompt(self):
        if not self.points:
            return "first end of the diameter"
        return "second end   (or type the diameter then Enter)"

    def compute(self):
        if not self.points or self.cur is None:
            return [], [], "", None
        a = self.points[0]
        u, v, _ = plane_axes(self.axis)
        d = self.cur - a
        du, dv = d.dot(u), d.dot(v)
        dist = math.hypot(du, dv)
        if dist > 1e-9:
            dirv = (u * du + v * dv) / dist
        else:
            dirv = u.copy()
        diam = dist
        t = self.typed_value(0)
        if t is not None:
            diam = abs(t)
        if diam < 1e-9:
            return [], [], "", None
        c = a + dirv * (diam / 2.0)
        r = diam / 2.0
        prev = arc_samples(c, u, v, r, 0.0, TAU, 96)
        info = f"Diameter {self.fmt(diam)}   Radius {self.fmt(r)}"
        return prev, [[a, a + dirv * diam]], info, ("circle", c, u, v, r)


class StagedTypeMixin:
    """Saisie de valeurs étape par étape pour les outils à plusieurs points (arcs, ellipses) :
    on tape la valeur de l'étape en cours (longueur, rayon, angle) puis Entrée passe à l'étape suivante."""

    def can_confirm_typed(self):
        return True

    def typed_point(self):
        return None

    def dir_len(self, base, ref, mult=1.0):
        """Vecteur de base vers ref (dans le plan de dessin) ; sa longueur est la valeur saisie x mult, si elle existe."""
        u, v, _ = plane_axes(self.axis)
        d = ref - base
        du, dv = d.dot(u), d.dot(v)
        t = self.typed_value(0)
        if t is None:
            return d
        L = math.hypot(du, dv)
        dirv = (u * du + v * dv) / L if L > 1e-9 else u.copy()
        return dirv * abs(t) * mult

    def finish_shape(self, context):
        if len(self.points) < self.NEEDED - 1:
            pt = self.typed_point()
            if pt is None:
                self.report({'WARNING'}, "Type a valid value first")
                return
            self.points.append(pt)
            self.typed = ['', '', '']
            self.field = 0
            self.lock = None
            self.refresh(context)
            return
        super().finish_shape(context)

    def click(self, context):
        super().click(context)
        if not self.finished:
            self.typed = ['', '', '']
            self.field = 0


class DessinEllipse(StagedTypeMixin, DessinBase):
    """Base des ellipses (classe non enregistrée) : chaque variante fournit ellipse_data()."""

    NEEDED = 3
    NUMFIELDS = 1
    SIDE_MULT = 1.0     # valeur saisie -> longueur du demi-axe (1 : rayon, 0.5 : diamètre)

    def ellipse_data(self):
        """Retourne (centre, demi-grand-axe vecteur A, demi-petit-axe vecteur W, aperçu partiel) ou None."""
        return None

    def axis_pair(self, c, A, cur):
        """Second axe perpendiculaire à A, de demi-longueur = distance de cur à la droite du premier axe (ou valeur saisie)."""
        _, _, nrm = plane_axes(self.axis)
        L = A.length
        if L < 1e-9:
            return None
        w = nrm.cross(A / L)
        B = abs((cur - c).dot(w))
        t = self.typed_value(0)
        if t is not None:
            B = abs(t) * self.SIDE_MULT
        return w * B

    def compute(self):
        if not self.points or self.cur is None:
            return [], [], "", None
        data = self.ellipse_data()
        if data is None:
            return [], [], "", None
        c, A, W, partial = data
        if A is None:
            return partial or [], [], "", None
        if W is None or W.length < 1e-9 or A.length < 1e-9:
            return [c - A, c + A], [], f"Axis {self.fmt(2 * A.length)}", None
        prev = arc_samples(c, A, W, 1.0, 0.0, TAU, 96)
        guides = [[c - A, c + A], [c - W, c + W]]
        a, b = (A.length, W.length) if A.length >= W.length else (W.length, A.length)
        info = f"Axes {self.fmt(2 * a)} × {self.fmt(2 * b)}"
        return prev, guides, info, ("ellipse", c, A, W)


class DESSIN_OT_ellipse_centre(DessinEllipse):
    bl_idname = "dessin.ellipse_centre"
    bl_label = "Ellipse: From Center"
    bl_description = "Ellipse: center, end of the first axis, then end of the second axis"

    TITLE = "Ellipse: From Center"

    def prompt(self):
        return ("center",
                "end of the first axis   (or type the radius then Enter)",
                "end of the second axis   (or type the radius then Enter)")[min(len(self.points), 2)]

    def typed_point(self):
        c = self.points[0]
        return c + self.dir_len(c, self.cur) if self.typed_value(0) else None

    def ellipse_data(self):
        n = len(self.points)
        c = self.points[0]
        if n == 1:
            return c, self.dir_len(c, self.cur), None, None
        A = self.points[1] - c
        return c, A, self.axis_pair(c, A, self.cur), None


class DESSIN_OT_ellipse_diametre(DessinEllipse):
    bl_idname = "dessin.ellipse_diametre"
    bl_label = "Ellipse: Diameter"
    bl_description = "Ellipse: two ends of the first axis, then end of the second axis"

    TITLE = "Ellipse: Diameter"
    SIDE_MULT = 0.5

    def prompt(self):
        return ("first end of the first axis",
                "second end of the first axis   (or type the length then Enter)",
                "end of the second axis   (or type the length then Enter)")[min(len(self.points), 2)]

    def typed_point(self):
        p0 = self.points[0]
        return p0 + self.dir_len(p0, self.cur) if self.typed_value(0) else None

    def ellipse_data(self):
        p0 = self.points[0]
        if len(self.points) == 1:
            vec = self.dir_len(p0, self.cur)
            return p0 + vec * 0.5, vec * 0.5, None, None
        c = (p0 + self.points[1]) * 0.5
        A = (self.points[1] - p0) * 0.5
        return c, A, self.axis_pair(c, A, self.cur), None


class DESSIN_OT_ellipse_foyers(DessinEllipse):
    bl_idname = "dessin.ellipse_foyers"
    bl_label = "Ellipse: From Foci"
    bl_description = "Ellipse: first focus, second focus, then a point on the ellipse"

    TITLE = "Ellipse: From Foci"

    def prompt(self):
        return ("first focus", "second focus   (or type the distance between the foci then Enter)",
                "point on the ellipse   (or type the total length of the main axis then Enter)")[min(len(self.points), 2)]

    def typed_point(self):
        f1 = self.points[0]
        return f1 + self.dir_len(f1, self.cur) if self.typed_value(0) else None

    def ellipse_data(self):
        f1 = self.points[0]
        if len(self.points) == 1:
            vec = self.dir_len(f1, self.cur)
            return f1 + vec * 0.5, vec * 0.5, None, None
        f2 = self.points[1]
        c = (f1 + f2) * 0.5
        u, v, nrm = plane_axes(self.axis)
        cf = (f2 - f1).length * 0.5
        a = ((self.cur - f1).length + (self.cur - f2).length) * 0.5
        t = self.typed_value(0)
        if t is not None:
            a = abs(t) * 0.5
        if a <= cf + 1e-9:
            return c, (f2 - f1) * 0.5, None, None  # le point doit être hors du segment des foyers
        b = math.sqrt(a * a - cf * cf)
        dirv = (f2 - f1) / (2.0 * cf) if cf > 1e-9 else u
        return c, dirv * a, nrm.cross(dirv) * b, None


class DESSIN_OT_ellipse_coin(DessinEllipse):
    bl_idname = "dessin.ellipse_coin"
    bl_label = "Ellipse: By Corners"
    bl_description = ("Ellipse inscribed in a rectangle: two opposite corners (or type width, Tab, height, Enter)")

    TITLE = "Ellipse: By Corners"
    PROP = (1,)
    NEEDED = 2
    NUMFIELDS = 2

    def prompt(self):
        return "first corner" if not self.points else "opposite corner   (Shift: circle, or type width, Tab, height, Enter)"

    def ellipse_data(self):
        o = self.points[0]
        u, v, _ = plane_axes(self.axis)
        d = self.cur - o
        du, dv = d.dot(u), d.dot(v)
        w = self.sized(0, du, du)
        h = self.sized(1, dv, dv)
        if abs(w) < 1e-9 or abs(h) < 1e-9:
            return o, None, None, []
        c = o + u * (w * 0.5) + v * (h * 0.5)
        return c, u * (w * 0.5), v * (h * 0.5), None


class DESSIN_OT_arc_cse(StagedTypeMixin, DessinBase):
    bl_idname = "dessin.arc_cse"
    bl_label = "Arc: Center, Start, End"
    bl_description = "Draws an arc: center, start point, end point (F: flip direction)"

    TITLE = "Arc"
    NEEDED = 3
    NUMFIELDS = 1
    HAS_FLIP = True

    def prompt(self):
        n = len(self.points)
        if n == 0:
            return "center"
        if n == 1:
            return "start point (sets the radius)   (or type the radius then Enter)"
        return "end point   (or type the angle in degrees then Enter)   [F: flip direction]"

    def typed_point(self):
        c = self.points[0]
        return c + self.dir_len(c, self.cur) if self.typed_value(0) else None

    def compute(self):
        n = len(self.points)
        if n == 0 or self.cur is None:
            return [], [], "", None
        c = self.points[0]
        u, v, _ = plane_axes(self.axis)
        if n == 1:
            d = self.dir_len(c, self.cur)
            return [], [[c, c + d]], f"Radius {self.fmt(math.hypot(d.dot(u), d.dot(v)))}", None
        s = self.points[1]
        ds = s - c
        su, sv = ds.dot(u), ds.dot(v)
        r = math.hypot(su, sv)
        if r < 1e-9:
            return [], [], "", None
        t0 = math.atan2(sv, su)
        de = self.cur - c
        eu, ev = de.dot(u), de.dot(v)
        if math.hypot(eu, ev) < 1e-9:
            return [], [[c, s]], "", None
        t1 = math.atan2(ev, eu)
        sweep = (t1 - t0) % TAU
        if self.flip:
            sweep -= TAU
        ang = self.typed_raw(0)
        if ang is not None:
            sweep = math.radians(max(-359.99, min(359.99, ang)))
            if self.flip:
                sweep = -sweep
            t1 = t0 + sweep
        if abs(sweep) < 1e-6:
            return [], [[c, s]], "", None
        end = c + (u * math.cos(t1) + v * math.sin(t1)) * r
        prev = arc_samples(c, u, v, r, t0, sweep)
        info = f"Radius {self.fmt(r)}   Angle {abs(math.degrees(sweep)):.1f}°"
        return prev, [[s, c, end]], info, ("arc", c, u, v, r, t0, sweep)


class DESSIN_OT_arc_3pts(StagedTypeMixin, DessinBase):
    bl_idname = "dessin.arc_3pts"
    bl_label = "Arc: 3 Points"
    bl_description = "Draws an arc: start point, end point, point on the arc"

    TITLE = "Arc 3 points"
    NEEDED = 3
    NUMFIELDS = 1

    def prompt(self):
        n = len(self.points)
        if n == 0:
            return "start point"
        if n == 1:
            return "end point   (or type the chord length then Enter)"
        return "point on the arc   (or type the radius then Enter)"

    def typed_point(self):
        a = self.points[0]
        return a + self.dir_len(a, self.cur) if self.typed_value(0) else None

    def compute(self):
        n = len(self.points)
        if n == 0 or self.cur is None:
            return [], [], "", None
        a = self.points[0]
        u, v, _ = plane_axes(self.axis)
        if n == 1:
            e = a + self.dir_len(a, self.cur)
            return [], [[a, e]], f"Length {self.fmt((e - a).length)}", None
        b = self.points[1]
        bv = ((b - a).dot(u), (b - a).dot(v))
        pv = ((self.cur - a).dot(u), (self.cur - a).dot(v))
        if math.hypot(*bv) < 1e-9:
            return [], [], "", None
        rt = self.typed_value(0)
        if rt is not None:
            chord = math.hypot(*bv)
            R = abs(rt)
            if R < chord / 2 - 1e-9:
                return [a, b], [], f"Radius too small (min {self.fmt(chord / 2)})", None
            sgn = 1.0 if (bv[0] * pv[1] - bv[1] * pv[0]) >= 0 else -1.0
            sag = R - math.sqrt(max(R * R - chord * chord / 4, 0.0))
            wx, wy = -bv[1] / chord * sgn, bv[0] / chord * sgn
            pv = (bv[0] / 2 + wx * sag, bv[1] / 2 + wy * sag)
        cc = circle_through_origin(bv, pv)
        if cc is None:
            return [a, b], [], "", ("line", a, b)
        cx, cy = cc
        r = math.hypot(cx, cy)
        t0 = math.atan2(-cy, -cx)
        tb = math.atan2(bv[1] - cy, bv[0] - cx)
        tp = math.atan2(pv[1] - cy, pv[0] - cx)
        s = (tb - t0) % TAU
        sp = (tp - t0) % TAU
        sweep = s if sp < s else s - TAU
        center = a + u * cx + v * cy
        prev = arc_samples(center, u, v, r, t0, sweep)
        info = f"Radius {self.fmt(r)}   Angle {abs(math.degrees(sweep)):.1f}°"
        return prev, [[a, b]], info, ("arc", center, u, v, r, t0, sweep)


# --------------------------------------------------------------------------
# Polygones (centre / circonscrit / aire / arête / étoile)
# --------------------------------------------------------------------------

POLY_STATE = {"sides": 6, "star": 5}   # derniers nombres de côtés utilisés (mémorisés comme dans Rhino)


def regular_polygon(c, u, v, R, n, theta0):
    return [c + (u * math.cos(theta0 + TAU * k / n) + v * math.sin(theta0 + TAU * k / n)) * R for k in range(n)]


def star_polygon(c, u, v, R, r, n, theta0):
    pts = []
    for k in range(n):
        a = theta0 + TAU * k / n
        pts.append(c + (u * math.cos(a) + v * math.sin(a)) * R)
        b = a + math.pi / n
        pts.append(c + (u * math.cos(b) + v * math.sin(b)) * r)
    return pts


class DessinPolygon(DessinBase):
    """Base des polygones (classe non enregistrée) : le nombre de côtés se règle avec ↑ / ↓."""

    NEEDED = 2
    NUMFIELDS = 1
    STATE_KEY = "sides"
    SIDES_MIN = 3
    HAS_FLIP = False

    @property
    def nsides(self):
        return POLY_STATE[self.STATE_KEY]

    def side_hint(self):
        return f"   [type a number or ↑ / ↓ : {self.nsides} sides]"

    def angle_of(self, p, c, u, v):
        d = p - c
        return math.atan2(d.dot(v), d.dot(u))

    SIDES_MAX = 200
    _sides_buf = ""
    _sides_time = 0.0

    def modal(self, context, event):
        live = (self.area is not None and context.area is not None
                and find_window_region(self.area, event.mouse_x, event.mouse_y) is not None
                and not self.mouse_over_ui(event))
        if live and event.value == 'PRESS' and event.type in {'UP_ARROW', 'DOWN_ARROW'}:
            step = 1 if event.type == 'UP_ARROW' else -1
            POLY_STATE[self.STATE_KEY] = max(self.SIDES_MIN, min(self.SIDES_MAX, self.nsides + step))
            self._sides_buf = ""
            self.refresh(context)
            return {'RUNNING_MODAL'}
        if live and not self.points and event.value == 'PRESS' and not (event.ctrl or event.alt or event.oskey):
            # avant le premier point : taper un nombre fixe le nombre de côtés (comme dans Rhino)
            ch = event.unicode
            if ch and ch in "0123456789":
                now = time.time()
                buf = self._sides_buf if now - self._sides_time < 2.0 else ""
                nb = (buf + ch).lstrip("0")
                if nb and int(nb) > self.SIDES_MAX:
                    nb = ch.lstrip("0")
                self._sides_buf, self._sides_time = nb, now
                if nb:
                    POLY_STATE[self.STATE_KEY] = max(self.SIDES_MIN, min(self.SIDES_MAX, int(nb)))
                self.refresh(context)
                return {'RUNNING_MODAL'}
            if event.type == 'BACK_SPACE' and self._sides_buf:
                self._sides_buf = self._sides_buf[:-1]
                if self._sides_buf:
                    POLY_STATE[self.STATE_KEY] = max(self.SIDES_MIN, min(self.SIDES_MAX, int(self._sides_buf)))
                self.refresh(context)
                return {'RUNNING_MODAL'}
            if event.type in {'RET', 'NUMPAD_ENTER', 'SPACE'} and self._sides_buf:
                self._sides_buf = ""        # Entrée valide le nombre de côtés tapé, sans quitter l'outil
                self.refresh(context)
                return {'RUNNING_MODAL'}
        return super().modal(context, event)

    def poly_result(self, c, pts, extra_guides, info):
        closed = pts + [pts[0]]
        return closed, extra_guides, info, ("poly", pts)


class DESSIN_OT_poly_center(DessinPolygon):
    bl_idname = "dessin.poly_center"
    bl_label = "Polygon: Center, Radius"
    bl_description = "Regular polygon inscribed in a circle: center then a vertex (↑ / ↓: number of sides, or type the radius)"
    TITLE = "Polygon (inscribed)"

    def prompt(self):
        if not self.points:
            return "center" + self.side_hint()
        return "vertex   (or type the radius then Enter)" + self.side_hint()

    def compute(self):
        if not self.points or self.cur is None:
            return [], [], "", None
        c = self.points[0]
        u, v, _ = plane_axes(self.axis)
        d = self.cur - c
        dist = math.hypot(d.dot(u), d.dot(v))
        R = dist
        t = self.typed_value(0)
        if t is not None:
            R = abs(t)
        if R < 1e-9:
            return [], [], "", None
        th = self.angle_of(self.cur, c, u, v) if dist > 1e-9 else 0.0
        pts = regular_polygon(c, u, v, R, self.nsides, th)
        info = f"{self.nsides} sides   Radius {self.fmt(R)}"
        return self.poly_result(c, pts, [[c, pts[0]]], info)


class DESSIN_OT_poly_circ(DessinPolygon):
    bl_idname = "dessin.poly_circ"
    bl_label = "Polygon: Circumscribed"
    bl_description = "Regular polygon circumscribed about a circle: center then the middle of an edge (↑ / ↓: number of sides, or type the radius)"
    TITLE = "Polygon (circumscribed)"

    def prompt(self):
        if not self.points:
            return "center" + self.side_hint()
        return "middle of an edge   (or type the inner radius then Enter)" + self.side_hint()

    def compute(self):
        if not self.points or self.cur is None:
            return [], [], "", None
        c = self.points[0]
        u, v, _ = plane_axes(self.axis)
        d = self.cur - c
        dist = math.hypot(d.dot(u), d.dot(v))
        a = dist
        t = self.typed_value(0)
        if t is not None:
            a = abs(t)
        if a < 1e-9:
            return [], [], "", None
        n = self.nsides
        th = (self.angle_of(self.cur, c, u, v) if dist > 1e-9 else 0.0) - math.pi / n
        R = a / math.cos(math.pi / n)
        pts = regular_polygon(c, u, v, R, n, th)
        mid = (pts[0] + pts[1]) / 2.0
        circ = arc_samples(c, u, v, a, 0.0, TAU, 64)
        info = f"{n} sides   Inner radius {self.fmt(a)}"
        return self.poly_result(c, pts, [[c, mid], circ], info)


class DESSIN_OT_poly_area(DessinPolygon):
    bl_idname = "dessin.poly_area"
    bl_label = "Polygon: Area"
    bl_description = "Regular polygon with a given area: center then a vertex, or type the area (↑ / ↓: number of sides)"
    TITLE = "Polygon (area)"

    def prompt(self):
        if not self.points:
            return "center" + self.side_hint()
        return "vertex   (or type the area then Enter)" + self.side_hint()

    def compute(self):
        if not self.points or self.cur is None:
            return [], [], "", None
        c = self.points[0]
        u, v, _ = plane_axes(self.axis)
        n = self.nsides
        k = 0.5 * n * math.sin(TAU / n)       # aire = k · R²
        d = self.cur - c
        dist = math.hypot(d.dot(u), d.dot(v))
        R = dist
        t = self.typed_raw(0)
        if t is not None:
            R = math.sqrt(abs(t) * self.unit_f ** 2 / k)
        if R < 1e-9:
            return [], [], "", None
        th = self.angle_of(self.cur, c, u, v) if dist > 1e-9 else 0.0
        pts = regular_polygon(c, u, v, R, n, th)
        area = k * R * R / (self.unit_f ** 2)
        info = f"{n} sides   Area {area:.3f} {self.unit_label}²".rstrip()
        return self.poly_result(c, pts, [[c, pts[0]]], info)


class DESSIN_OT_poly_edge(DessinPolygon):
    bl_idname = "dessin.poly_edge"
    bl_label = "Polygon: Edge"
    bl_description = "Regular polygon from one edge: two points (F: other side, ↑ / ↓: number of sides, or type the edge length)"
    TITLE = "Polygon (edge)"
    HAS_FLIP = True

    def prompt(self):
        if not self.points:
            return "start of the edge" + self.side_hint()
        return "end of the edge   (or type the length then Enter)   [F: other side]" + self.side_hint()

    def compute(self):
        if not self.points or self.cur is None:
            return [], [], "", None
        p0 = self.points[0]
        u, v, nrm = plane_axes(self.axis)
        d = self.cur - p0
        du, dv = d.dot(u), d.dot(v)
        L = math.hypot(du, dv)
        if L < 1e-9:
            return [], [], "", None
        e = (u * du + v * dv) / L
        t = self.typed_value(0)
        if t is not None:
            L = abs(t)
        if L < 1e-9:
            return [], [], "", None
        n = self.nsides
        p1 = p0 + e * L
        left = nrm.cross(e)
        if self.flip:
            left = -left
        c = (p0 + p1) / 2.0 + left * (L / 2.0 / math.tan(math.pi / n))
        R = L / (2.0 * math.sin(math.pi / n))
        a0 = self.angle_of(p0, c, u, v)
        # sens de parcours : p0 -> p1 doit tourner autour du centre
        a1 = self.angle_of(p1, c, u, v)
        da = (a1 - a0 + math.pi) % TAU - math.pi
        direction = 1.0 if da > 0 else -1.0
        pts = [c + (u * math.cos(a0 + direction * TAU * k / n) + v * math.sin(a0 + direction * TAU * k / n)) * R
               for k in range(n)]
        info = f"{n} sides   Edge {self.fmt(L)}"
        return self.poly_result(c, pts, [[p0, p1]], info)


class DESSIN_OT_poly_star(DessinPolygon):
    bl_idname = "dessin.poly_star"
    bl_label = "Polygon: Star"
    bl_description = "Star: center, outer radius then inner radius (↑ / ↓: number of points, or type outer / Tab / inner)"
    TITLE = "Star"
    STATE_KEY = "star"
    NEEDED = 3
    NUMFIELDS = 2

    def side_hint(self):
        return f"   [↑ / ↓ : {self.nsides} points]"

    def prompt(self):
        k = len(self.points)
        if k == 0:
            return "center" + self.side_hint()
        if k == 1:
            return "outer radius   (or type outer, Tab, inner, Enter)" + self.side_hint()
        return "inner radius" + self.side_hint()

    def compute(self):
        if not self.points or self.cur is None:
            return [], [], "", None
        c = self.points[0]
        u, v, _ = plane_axes(self.axis)
        pts_all = self.points + [self.cur]
        d = pts_all[1] - c
        dist = math.hypot(d.dot(u), d.dot(v))
        R = dist
        t = self.typed_value(0)
        if t is not None:
            R = abs(t)
        if R < 1e-9:
            return [], [], "", None
        th = self.angle_of(pts_all[1], c, u, v) if dist > 1e-9 else 0.0
        n = self.nsides
        if len(self.points) >= 2:
            d2 = pts_all[2] - c
            r = math.hypot(d2.dot(u), d2.dot(v))
        else:
            r = 0.5 * R * math.cos(math.pi / n) if n > 2 else 0.5 * R
            r = 0.4 * R
        t2 = self.typed_value(1)
        if t2 is not None:
            r = abs(t2)
        r = max(r, 1e-6)
        pts = star_polygon(c, u, v, R, r, n, th)
        info = f"{n} points   Outer {self.fmt(R)}   Inner {self.fmt(r)}"
        spec_ok = len(self.points) >= 2 or t2 is not None
        closed = pts + [pts[0]]
        return closed, [[c, pts[0]]], info, (("poly", pts) if spec_ok else None)


def _late_imports():
    """Noms définis dans des modules chargés après celui-ci : ils ne servent qu'à l'exécution des outils."""
    global _CMD, cmd_hit
    from .views import _CMD
    from .command_line import cmd_hit
