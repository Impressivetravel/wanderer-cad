"""Wanderer CAD : Courbes : Rebuild, Simplify, Change Degree, points de contrôle, Match, Blend."""

import bpy
import numpy as np
from mathutils import Vector

from .core import _link_object
from .drawing import find_window_region, project_px, px_scale, region_rv3d
from .base import DessinBase
from .selection import objects_under_cursor
from .surfaces import object_paths
from .surface_tools import _rdp, fit_nurbs


def _curve_targets(context):
    return [o for o in context.selected_objects if o.type == 'CURVE' and "dessin_cotation" not in o.keys()
            and "dessin_cotation_texte" not in o.keys()]


def _write_paths_as(obj, paths, kind, n=None, p=3):
    """Remplace les splines de la courbe par `paths` (monde) : 'NURBS' ajustée (n points, degré p) ou 'POLY'."""
    cu = obj.data
    inv = obj.matrix_world.inverted()
    devs = []
    newsp = []
    for P, closed in paths:
        P = np.asarray(P, dtype=np.float64)
        if kind == 'NURBS':
            nn = max(p + 1, n) if not closed else max(p + 1, n)
            C, dev = fit_nurbs(P, nn, p, closed)
            devs.append(dev)
            newsp.append(('NURBS', [inv @ Vector(c) for c in C], closed))
        else:
            newsp.append(('POLY', [inv @ Vector(c) for c in P], closed))
    cu.splines.clear()
    for kind_, pts, closed in newsp:
        sp = cu.splines.new(kind_)
        sp.points.add(len(pts) - 1)
        for q, c in zip(sp.points, pts):
            q.co = (c.x, c.y, c.z, 1.0)
        sp.use_cyclic_u = closed
        if kind_ == 'NURBS':
            sp.order_u = p + 1
            sp.use_endpoint_u = not closed
            sp.resolution_u = 12
    return max(devs) if devs else 0.0


class DESSIN_OT_rebuild_crv(bpy.types.Operator):
    bl_idname = "dessin.rebuild_crv"
    bl_label = "Rebuild Curve"
    bl_description = ("Like Rebuild: rebuilds the selected curves as smooth NURBS curves with a given number of control "
                      "points and degree (the ends are kept)")
    bl_options = {'REGISTER', 'UNDO'}

    points: bpy.props.IntProperty(name="Point count", default=10, min=2, max=500)
    degree: bpy.props.IntProperty(name="Degree", default=3, min=1, max=5)

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def invoke(self, context, event):
        if not _curve_targets(context):
            self.report({'INFO'}, "Select the curves to rebuild first")
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self, width=260)

    def execute(self, context):
        objs = _curve_targets(context)
        if not objs:
            self.report({'INFO'}, "Select the curves to rebuild first")
            return {'CANCELLED'}
        dg = context.evaluated_depsgraph_get()
        dev = 0.0
        n_ok = 0
        for o in objs:
            paths = object_paths(o, dg)
            if not paths:
                continue
            dev = max(dev, _write_paths_as(o, paths, 'NURBS', self.points, min(self.degree, self.points - 1)))
            n_ok += 1
        self.report({'INFO'}, f"{n_ok} curve(s) rebuilt, max deviation {dev:.4g}")
        return {'FINISHED'}


class DESSIN_OT_simplify_crv(bpy.types.Operator):
    bl_idname = "dessin.simplify_crv"
    bl_label = "Simplify Curve"
    bl_description = ("Like SimplifyCrv / Fit: removes the points that are not needed to keep the shape within the tolerance "
                      "(nearly aligned points of polylines, dense curves turned into light polylines)")
    bl_options = {'REGISTER', 'UNDO'}

    tolerance: bpy.props.FloatProperty(name="Tolerance", default=0.001, min=0.0, subtype='DISTANCE', unit='LENGTH',
                                       description="Largest distance allowed between the old and the new curve")

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def invoke(self, context, event):
        if not _curve_targets(context):
            self.report({'INFO'}, "Select the curves to simplify first")
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self, width=260)

    def execute(self, context):
        objs = _curve_targets(context)
        dg = context.evaluated_depsgraph_get()
        before = after = 0
        for o in objs:
            paths = object_paths(o, dg)
            out = []
            for P, closed in paths:
                P = np.asarray(P, dtype=np.float64)
                before += len(P)
                if closed:
                    Q = np.vstack([P, P[:1]])
                    idx = _rdp(Q, self.tolerance)
                    keep = Q[idx][:-1]
                else:
                    keep = P[_rdp(P, self.tolerance)]
                if len(keep) < (3 if closed else 2):
                    keep = P
                after += len(keep)
                out.append((keep, closed))
            if out:
                _write_paths_as(o, out, 'POLY')
        self.report({'INFO'}, f"{before} points -> {after} points")
        return {'FINISHED'}


class DESSIN_OT_change_degree(bpy.types.Operator):
    bl_idname = "dessin.change_degree"
    bl_label = "Change Degree"
    bl_description = ("Like ChangeDegree: sets the degree of the selected curves; their points become control points "
                      "(degree 1: polyline, 2 to 5: smooth NURBS curve)")
    bl_options = {'REGISTER', 'UNDO'}

    degree: bpy.props.IntProperty(name="Degree", default=3, min=1, max=5)

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def invoke(self, context, event):
        if not _curve_targets(context):
            self.report({'INFO'}, "Select the curves first")
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self, width=240)

    def execute(self, context):
        n = 0
        for o in _curve_targets(context):
            cu = o.data
            datas = []
            for sp in cu.splines:
                if sp.type == 'BEZIER':
                    pts = []
                    bp = sp.bezier_points
                    for i, q in enumerate(bp):        # polygone de contrôle de la Bézier (nœuds + poignées)
                        if i > 0 or sp.use_cyclic_u:
                            pts.append(q.handle_left.copy())
                        pts.append(q.co.copy())
                        if i < len(bp) - 1 or sp.use_cyclic_u:
                            pts.append(q.handle_right.copy())
                    if sp.use_cyclic_u and pts:
                        pts = pts[1:] + pts[:1]
                else:
                    pts = [Vector(q.co[:3]) for q in sp.points]
                datas.append((pts, sp.use_cyclic_u))
            cu.splines.clear()
            for pts, cyc in datas:
                kind = 'POLY' if self.degree == 1 else 'NURBS'
                sp = cu.splines.new(kind)
                sp.points.add(len(pts) - 1)
                for q, c in zip(sp.points, pts):
                    q.co = (c.x, c.y, c.z, 1.0)
                sp.use_cyclic_u = cyc
                if kind == 'NURBS':
                    sp.order_u = max(2, min(self.degree + 1, len(pts)))
                    sp.use_endpoint_u = not cyc
                    sp.resolution_u = 12
            n += 1
        self.report({'INFO'}, f"{n} curve(s) set to degree {self.degree}")
        return {'FINISHED'}


# ---- points de contrôle : insertion / suppression au clic ----

def _cubic(p0, p1, p2, p3, t):
    a = p0.lerp(p1, t); b = p1.lerp(p2, t); c = p2.lerp(p3, t)
    d = a.lerp(b, t); e = b.lerp(c, t)
    return d.lerp(e, t), (a, d, e, c)


def _spline_segments_world(o, sp):
    """[(index du segment, polyligne monde échantillonnée)] d'une spline (segments entre points de contrôle)."""
    mw = o.matrix_world
    out = []
    if sp.type == 'BEZIER':
        bp = sp.bezier_points
        n = len(bp)
        segs = n if sp.use_cyclic_u else n - 1
        for i in range(segs):
            a, b = bp[i], bp[(i + 1) % n]
            pts = [mw @ _cubic(a.co, a.handle_right, b.handle_left, b.co, k / 16)[0] for k in range(17)]
            out.append((i, pts))
    else:
        P = [Vector(q.co[:3]) for q in sp.points]
        n = len(P)
        segs = n if sp.use_cyclic_u else n - 1
        for i in range(segs):
            out.append((i, [mw @ P[i], mw @ P[(i + 1) % n]]))
    return out


def pick_curve_segment(op, context, px=14.0):
    """(objet, index de spline, index de segment, t, point monde) sur la courbe la plus proche du curseur, ou None."""
    mouse = getattr(op, "_mouse", None)
    if mouse is None or op.region is None:
        return None
    try:
        rv3d = region_rv3d(op.region, op.area)
    except (AttributeError, ReferenceError):
        return None
    m = Vector(mouse)
    best, bd = None, px * px_scale()
    for o in objects_under_cursor(context, op.region, rv3d, m.x, m.y, bd, ('CURVE',)):
        if o.type != 'CURVE' or "dessin_cotation" in o.keys() or "dessin_cotation_texte" in o.keys():
            continue
        for si, sp in enumerate(o.data.splines):
            for gi, pts in _spline_segments_world(o, sp):
                scr = [project_px(rv3d, op.region, p) for p in pts]
                for k in range(len(scr) - 1):
                    a, b = scr[k], scr[k + 1]
                    if a is None or b is None:
                        continue
                    ab = b - a
                    tt = max(0.0, min(1.0, (m - a).dot(ab) / max(ab.length_squared, 1e-12)))
                    d = (a + ab * tt - m).length
                    if d < bd:
                        tseg = (k + tt) / (len(pts) - 1)
                        best, bd = (o, si, gi, tseg, pts[k].lerp(pts[k + 1], tt)), d
    return best


def pick_control_point(op, context, px=14.0):
    """(objet, index de spline, index du point, point monde) : point de contrôle le plus proche du curseur."""
    mouse = getattr(op, "_mouse", None)
    if mouse is None or op.region is None:
        return None
    try:
        rv3d = region_rv3d(op.region, op.area)
    except (AttributeError, ReferenceError):
        return None
    m = Vector(mouse)
    best, bd = None, px * px_scale()
    near = objects_under_cursor(context, op.region, rv3d, m.x, m.y, bd, ('CURVE',))
    seen = {o.name for o in near}
    # les points de contrôle d'une NURBS peuvent être loin de la courbe elle-même : ces courbes restent toujours candidates
    near += [o for o in context.visible_objects if o.type == 'CURVE' and o.name not in seen
             and any(sp.type == 'NURBS' for sp in o.data.splines)]
    for o in near:
        if o.type != 'CURVE' or "dessin_cotation" in o.keys() or "dessin_cotation_texte" in o.keys():
            continue
        mw = o.matrix_world
        for si, sp in enumerate(o.data.splines):
            pts = [q.co for q in sp.bezier_points] if sp.type == 'BEZIER' else [Vector(q.co[:3]) for q in sp.points]
            for pi, p in enumerate(pts):
                w = mw @ Vector(p)
                s = project_px(rv3d, op.region, w)
                if s is not None and (s - m).length < bd:
                    best, bd = (o, si, pi, w), (s - m).length
    return best


def _spline_dump(sp):
    d = {"type": sp.type, "cyc": sp.use_cyclic_u, "order": sp.order_u, "end": sp.use_endpoint_u,
         "res": sp.resolution_u, "smooth": sp.use_smooth}
    if sp.type == 'BEZIER':
        d["pts"] = [(q.co.copy(), q.handle_left.copy(), q.handle_right.copy(), q.handle_left_type, q.handle_right_type, q.radius, q.tilt)
                    for q in sp.bezier_points]
    else:
        d["pts"] = [(Vector(q.co), q.radius, q.tilt) for q in sp.points]
    return d


def _spline_load(cu, d):
    sp = cu.splines.new(d["type"])
    if d["type"] == 'BEZIER':
        sp.bezier_points.add(len(d["pts"]) - 1)
        for q, (co, hl, hr, tl, tr, r, ti) in zip(sp.bezier_points, d["pts"]):
            q.handle_left_type, q.handle_right_type = 'FREE', 'FREE'
            q.co, q.handle_left, q.handle_right = co, hl, hr
            q.handle_left_type, q.handle_right_type = tl, tr
            q.radius, q.tilt = r, ti
    else:
        sp.points.add(len(d["pts"]) - 1)
        for q, (co, r, ti) in zip(sp.points, d["pts"]):
            q.co = co
            q.radius, q.tilt = r, ti
    sp.use_cyclic_u = d["cyc"]
    try:
        sp.order_u = d["order"]
        sp.use_endpoint_u = d["end"]
    except (AttributeError, TypeError, ValueError):
        pass
    sp.resolution_u = d["res"]
    sp.use_smooth = d["smooth"]
    return sp


def _rewrite_curve(cu, dumps):
    cu.splines.clear()
    for d in dumps:
        _spline_load(cu, d)


def insert_control_point(o, si, gi, t):
    """Ajoute un point sur le segment gi de la spline si, à la fraction t (Bézier : sans changer la forme)."""
    cu = o.data
    dumps = [_spline_dump(sp) for sp in cu.splines]
    d = dumps[si]
    pts = d["pts"]
    n = len(pts)
    j = (gi + 1) % n if d["cyc"] else gi + 1
    if d["type"] == 'BEZIER':
        a, b = pts[gi], pts[(gi + 1) % n]
        mid, (h_a, h_ml, h_mr, h_b) = _cubic(a[0], a[2], b[1], b[0], t)
        pts[gi] = (a[0], a[1], h_a, a[3], 'FREE' if a[4] in ('AUTO', 'ALIGNED') else a[4], a[5], a[6])
        pts[(gi + 1) % n] = (b[0], h_b, b[2], 'FREE' if b[3] in ('AUTO', 'ALIGNED') else b[3], b[4], b[5], b[6])
        newp = (mid, h_ml, h_mr, 'ALIGNED', 'ALIGNED', a[5], a[6])
    else:
        ca, cb = pts[gi][0], pts[(gi + 1) % n][0]
        newp = (ca.lerp(cb, t), pts[gi][1], pts[gi][2])
    pts.insert(gi + 1, newp)
    _rewrite_curve(cu, dumps)


def remove_control_point(o, si, pi):
    cu = o.data
    dumps = [_spline_dump(sp) for sp in cu.splines]
    d = dumps[si]
    if len(d["pts"]) <= (3 if d["cyc"] else 2):
        return False
    del d["pts"][pi]
    if d["type"] == 'NURBS':
        d["order"] = min(d["order"], len(d["pts"]))
    _rewrite_curve(cu, dumps)
    return True


class DESSIN_OT_insert_point(DessinBase):
    bl_idname = "dessin.insert_point"
    bl_label = "Insert Control Point"
    bl_description = ("Like InsertControlPoint / InsertEditPoint: click on a curve to add a point there "
                      "(polylines and Bézier curves keep their shape). Stays active")

    TITLE = "Insert Control Point"
    NEEDED = 1
    PLANAR = False
    LOCK_OK = False

    def lock_allowed(self):
        return False

    def prompt(self):
        return "click on a curve where to add a point"

    def invoke(self, context, event):
        self._mouse = None
        self.hilite = []
        if context.mode != 'OBJECT':
            self.report({'WARNING'}, "Switch to Object mode")
            return {'CANCELLED'}
        return super().invoke(context, event)

    def update_cursor(self, context, event):
        region = find_window_region(self.area, event.mouse_x, event.mouse_y)
        self._mouse = (event.mouse_x - region.x, event.mouse_y - region.y) if region is not None else None
        super().update_cursor(context, event)

    def compute(self):
        self.hilite = []
        r = pick_curve_segment(self, bpy.context)
        if r is None:
            return [], [], "No curve under the cursor", None
        o, si, gi, t, w = r
        segs = dict(_spline_segments_world(o, o.data.splines[si]))[gi]
        self.hilite = list(zip(segs[:-1], segs[1:]))
        return [w], [], o.name, None

    def click(self, context):
        r = pick_curve_segment(self, context)
        if r is None:
            self.report({'INFO'}, "Click on a curve")
            return
        o, si, gi, t, _w = r
        insert_control_point(o, si, gi, t)
        self.reset_state()
        self.refresh(context)


class DESSIN_OT_remove_point(DessinBase):
    bl_idname = "dessin.remove_point"
    bl_label = "Remove Control Point"
    bl_description = "Like RemoveControlPoint: click near a control point of a curve to delete it. Stays active"

    TITLE = "Remove Control Point"
    NEEDED = 1
    PLANAR = False
    LOCK_OK = False

    def lock_allowed(self):
        return False

    def prompt(self):
        return "click a control point to remove"

    def invoke(self, context, event):
        self._mouse = None
        self.hilite = []
        if context.mode != 'OBJECT':
            self.report({'WARNING'}, "Switch to Object mode")
            return {'CANCELLED'}
        return super().invoke(context, event)

    def update_cursor(self, context, event):
        region = find_window_region(self.area, event.mouse_x, event.mouse_y)
        self._mouse = (event.mouse_x - region.x, event.mouse_y - region.y) if region is not None else None
        super().update_cursor(context, event)

    def compute(self):
        self.hilite = []
        r = pick_control_point(self, bpy.context)
        if r is None:
            return [], [], "No control point under the cursor", None
        w = r[3]
        e = 0.0001
        self.hilite = [(w, w + Vector((e, 0, 0)))]
        return [w], [], f"{r[0].name} : point {r[2] + 1}", None

    def click(self, context):
        r = pick_control_point(self, context)
        if r is None:
            self.report({'INFO'}, "Click a control point")
            return
        if not remove_control_point(r[0], r[1], r[2]):
            self.report({'WARNING'}, "A curve needs at least 2 points")
        self.reset_state()
        self.refresh(context)


# ---- MatchCrv / BlendCrv : extrémités de courbes ----

def curve_end(o, si, at_end):
    """(point monde, direction sortante unitaire, longueur de la poignée / du dernier segment) d'une extrémité de spline."""
    sp = o.data.splines[si]
    mw = o.matrix_world
    if sp.type == 'BEZIER':
        q = sp.bezier_points[-1] if at_end else sp.bezier_points[0]
        p = mw @ q.co
        h = mw @ (q.handle_left if at_end else q.handle_right)
        d = p - h
        if d.length < 1e-12:
            other = sp.bezier_points[-2 if at_end else 1]
            d = p - mw @ other.co
        return p, d.normalized(), (p - h).length
    P = [mw @ Vector(q.co[:3]) for q in sp.points]
    p, prev = (P[-1], P[-2]) if at_end else (P[0], P[1])
    d = p - prev
    return p, d.normalized() if d.length > 1e-12 else Vector((1, 0, 0)), d.length


def pick_curve_end(op, context):
    """(objet, spline, extrémité finale ?) : courbe sous le curseur et le bout le plus proche du clic."""
    r = pick_curve_segment(op, context)
    if r is None:
        return None
    o, si, gi, t, w = r
    sp = o.data.splines[si]
    if sp.use_cyclic_u:
        return None
    n = len(sp.bezier_points) if sp.type == 'BEZIER' else len(sp.points)
    pos = (gi + t) / max(n - 1, 1)
    return o, si, pos >= 0.5


def match_curve(A, sia, enda, B, sib, endb, tangency):
    """Déplace l'extrémité de A sur celle de B (position), et aligne sa tangente (tangence) : MatchCrv."""
    pB, dB, _l = curve_end(B, sib, endb)
    sp = A.data.splines[sia]
    inv = A.matrix_world.inverted()
    tgt = inv @ pB
    dir_in = (inv.to_3x3() @ dB).normalized()        # A doit arriver en continuant B en sens inverse
    if sp.type == 'BEZIER':
        q = sp.bezier_points[-1] if enda else sp.bezier_points[0]
        hin = q.handle_left if enda else q.handle_right
        hout = q.handle_right if enda else q.handle_left
        L = (hin - q.co).length or 1e-3
        delta = tgt - q.co
        q.handle_left_type = q.handle_right_type = 'FREE'
        q.co = tgt
        if tangency:
            if enda:
                q.handle_left = tgt + dir_in * L
                q.handle_right = tgt - dir_in * L
            else:
                q.handle_right = tgt + dir_in * L
                q.handle_left = tgt - dir_in * L
        else:
            if enda:
                q.handle_left = q.handle_left + delta
                q.handle_right = q.handle_right + delta
            else:
                q.handle_left = q.handle_left + delta
                q.handle_right = q.handle_right + delta
        return True
    pts = sp.points
    i0, i1 = (len(pts) - 1, len(pts) - 2) if enda else (0, 1)
    last, prev = Vector(pts[i0].co[:3]), Vector(pts[i1].co[:3])
    L = (last - prev).length
    pts[i0].co = (tgt.x, tgt.y, tgt.z, pts[i0].co[3])
    if tangency and len(pts) >= 3:
        q = tgt + dir_in * L
        pts[i1].co = (q.x, q.y, q.z, pts[i1].co[3])
    return True


def blend_curve_points(A, sia, enda, B, sib, endb, bulge=1.0):
    pA, dA, _ = curve_end(A, sia, enda)
    pB, dB, _ = curve_end(B, sib, endb)
    k = (pB - pA).length / 3.0 * bulge
    return pA, pA + dA * k, pB + dB * k, pB


def build_blend_curve(context, pts):
    pA, hA, hB, pB = pts
    cu = bpy.data.curves.new("Blend Curve", 'CURVE')
    cu.dimensions = '3D'
    sp = cu.splines.new('BEZIER')
    sp.bezier_points.add(1)
    a, b = sp.bezier_points
    for q in (a, b):
        q.handle_left_type = q.handle_right_type = 'FREE'
    a.co, a.handle_right, a.handle_left = pA, hA, pA - (hA - pA)
    b.co, b.handle_left, b.handle_right = pB, hB, pB - (hB - pB)
    sp.resolution_u = 24
    return _link_object(context, "Blend Curve", cu)


class DessinCrvEnds(DessinBase):
    """Base de Match Curve / Blend Curve (classe non enregistrée) : deux clics près des extrémités de deux courbes."""

    NEEDED = 2
    PLANAR = False
    LOCK_OK = False

    def lock_allowed(self):
        return False

    def invoke(self, context, event):
        self._mouse = None
        self._first = None
        self.hilite = []
        if context.mode != 'OBJECT':
            self.report({'WARNING'}, "Switch to Object mode")
            return {'CANCELLED'}
        return super().invoke(context, event)

    def update_cursor(self, context, event):
        region = find_window_region(self.area, event.mouse_x, event.mouse_y)
        self._mouse = (event.mouse_x - region.x, event.mouse_y - region.y) if region is not None else None
        super().update_cursor(context, event)

    def end_hilite(self, r):
        o, si, at_end = r
        p, d, _l = curve_end(o, si, at_end)
        sp = o.data.splines[si]
        segs = _spline_segments_world(o, sp)
        pts = segs[-1][1] if at_end else segs[0][1]
        return list(zip(pts[:-1], pts[1:])) + [(p, p + d * 0.0001)], p

    def compute(self):
        self.hilite = []
        r = pick_curve_end(self, bpy.context)
        if r is None:
            if self._first is not None:
                self.hilite = self.end_hilite(self._first)[0]
            return [], [], "Click near the end of an open curve", None
        hl, p = self.end_hilite(r)
        self.hilite = hl + (self.end_hilite(self._first)[0] if self._first is not None else [])
        guides = []
        if self._first is not None and (r[0], r[1]) != (self._first[0], self._first[1]):
            guides = self.preview_with(r)
        return [p], guides, r[0].name + (" : end" if r[2] else " : start"), None

    def preview_with(self, r):
        return []

    def click(self, context):
        r = pick_curve_end(self, context)
        if r is None:
            self.report({'INFO'}, "Click near the end of an open curve")
            return
        if self._first is None:
            self._first = r
            self.points.append(self.cur.copy() if self.cur is not None else Vector())
            self.refresh(context)
            return
        if (r[0], r[1]) == (self._first[0], self._first[1]):
            self.report({'INFO'}, "Click another curve")
            return
        self.apply(context, self._first, r)
        self._first = None
        self.finished = True


class DESSIN_OT_match_crv(DessinCrvEnds):
    bl_idname = "dessin.match_crv"
    bl_label = "Match Curve"
    bl_description = ("Like MatchCrv: click near the end of the curve to change, then near the end of the curve to match. "
                      "D: position / tangency")

    TITLE = "Match Curve"
    HAS_MODE = True
    MODES = ("Tangency", "Position")
    mode = 0

    def prompt(self):
        if self._first is None:
            return f"click near the end of the curve to change   [D: {self.MODES[self.mode]}]"
        return f"click near the end of the curve to match   [D: {self.MODES[self.mode]}]"

    def preview_with(self, r):
        pB, dB, _l = curve_end(r[0], r[1], r[2])
        pA, _dA, _ = curve_end(self._first[0], self._first[1], self._first[2])
        return [[pA, pB]]

    def apply(self, context, a, b):
        match_curve(a[0], a[1], a[2], b[0], b[1], b[2], self.mode == 0)


class DESSIN_OT_blend_crv(DessinCrvEnds):
    bl_idname = "dessin.blend_crv"
    bl_label = "Blend Curve"
    bl_description = ("Like BlendCrv: click near the end of a curve, then near the end of another one: a smooth curve "
                      "joins them, tangent to both")

    TITLE = "Blend Curve"

    def prompt(self):
        if self._first is None:
            return "click near the end of the first curve"
        return "click near the end of the second curve"

    def preview_with(self, r):
        a = self._first
        pA, hA, hB, pB = blend_curve_points(a[0], a[1], a[2], r[0], r[1], r[2])
        pts = [_cubic(pA, hA, hB, pB, k / 24)[0] for k in range(25)]
        return [pts]

    def apply(self, context, a, b):
        pts = blend_curve_points(a[0], a[1], a[2], b[0], b[1], b[2])
        build_blend_curve(context, pts)


# ---- Blocs (Block, Insert, BlockEdit, ExplodeBlock, gestionnaire) : collections instanciées de Blender ----

BLOCKS = "Blocks"
def block_edit_state():
    """État de Block Edit, lu dans la scène elle-même (la collection d'édition porte l'instance et le bloc édités) :
    il suit Annuler / Rétablir et l'enregistrement du fichier, ce qu'une variable Python ne fait pas."""
    try:
        for c in bpy.data.collections:
            if "wd_be_inst" in c.keys():
                return {"inst": c["wd_be_inst"], "col": c.name, "def": c.get("wd_be_def"), "prev_col": c.get("wd_be_prev")}
    except (AttributeError, ReferenceError, RuntimeError):
        pass
    return {"inst": None, "col": None, "def": None, "prev_col": None}


def blocks_root(context, create=True):
    """Collection « Blocks » qui range les définitions (exclue de la vue : seules les instances se voient)."""
    root = bpy.data.collections.get(BLOCKS)
    if root is None and create:
        root = bpy.data.collections.new(BLOCKS)
        context.scene.collection.children.link(root)
    if root is not None:
        lc = _find_layer_col(context.view_layer.layer_collection, root)
        if lc is not None and not lc.exclude and block_edit_state()["def"] is None:
            lc.exclude = True
    return root


def _find_layer_col(lc, col):
    if lc.collection is col:
        return lc
    for ch in lc.children:
        r = _find_layer_col(ch, col)
        if r is not None:
            return r
    return None


def block_defs():
    root = bpy.data.collections.get(BLOCKS)
    return list(root.children) if root is not None else []


def is_block_instance(o):
    try:
        return (o is not None and o.type == 'EMPTY' and o.instance_type == 'COLLECTION' and o.instance_collection is not None
                and o.instance_collection.name in {c.name for c in block_defs()})
    except ReferenceError:
        return False


def block_instances(defcol):
    return [o for o in bpy.data.objects if o.type == 'EMPTY' and o.instance_type == 'COLLECTION'
            and o.instance_collection is defcol]


def new_block_instance(context, defcol, matrix, name=None):
    e = bpy.data.objects.new(name or defcol.name, None)
    e.instance_type = 'COLLECTION'
    e.instance_collection = defcol
    e.empty_display_size = 0.0
    e.empty_display_type = 'PLAIN_AXES'
    context.view_layer.active_layer_collection.collection.objects.link(e)
    e.matrix_world = matrix
    return e


def _block_items(self, context):
    items = [(c.name, c.name, f"Block definition {c.name}") for c in block_defs()]
    return items or [('NONE', "(no block)", "Create a block first with Block")]


def _late_imports():
    pass
