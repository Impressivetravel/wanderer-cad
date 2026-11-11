"""Wanderer CAD : Untrim, SubD depuis des courbes, Edge Surface, Thicken, Cap, Blend / Match Surface, Shell, Align."""

import bmesh
import bpy
import gpu
import math
import numpy as np
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

from .core import idle_tool
from .drawing import find_window_region, get_shader, px_scale, region_rv3d
from .base import DessinBase
from .subd import subd_modifier
from .edges import build_edge_object
from .selection import _project_region
from .offset_extrude import back_to_idle, offset_surface_mesh
from .trim import wire_paths
from .surfaces import (
    _ProfileOp, _RevolveBody, _plane_of, align_sections, delete_objects, deselect_all_objects, grid_mesh,
    mesh_object_from_arrays, object_paths, ordered_selection, path_length, refine_points, rotation_matrix,
    sweep1_surface, sweep2_surface,
)
from .blocks import fill_hole, pick_boundary_loop, untrim_outer


class DessinUntrimBase(DessinBase):
    """Base de Untrim / UntrimHoles (classe non enregistrée)."""

    NEEDED = 1
    PLANAR = False
    LOCK_OK = False
    HAS_MODE = True
    mode = 0

    def lock_allowed(self):
        return False

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

    def loop_segments(self, o, loops, indices):
        me = o.data
        mw = o.matrix_world
        segs = []
        for li in indices:
            idx, closed = loops[li]
            P = [mw @ me.vertices[j].co for j in idx]
            if closed:
                P.append(P[0])
            segs.extend(zip(P[:-1], P[1:]))
        return segs[:6000]

    def targets(self, r):
        return []

    def compute(self):
        self.hilite = []
        r = pick_boundary_loop(self, bpy.context)
        if r is None:
            return [], [], "No free surface edge under the cursor", None
        o, loops, li, outer = r
        tg = self.targets(r)
        self.hilite = self.loop_segments(o, loops, tg) if tg else []
        kind = "outer edge" if li == outer else "hole"
        return [], [], f"{o.name} : {kind}", None


class DESSIN_OT_untrim(DessinUntrimBase):
    bl_idname = "dessin.untrim"
    bl_label = "Untrim"
    bl_description = ("Like Untrim: click an edge of a trimmed surface. A hole edge removes that hole; the outer edge gives the "
                      "surface back its shape before it was trimmed (D: all edges at once). Stays active")
    TITLE = "Untrim"
    MODES = ("This edge", "All edges")

    def prompt(self):
        return f"click the trimmed edge to remove   [D: {self.MODES[self.mode]}]"

    def targets(self, r):
        o, loops, li, outer = r
        return list(range(len(loops))) if self.mode == 1 else [li]

    def click(self, context):
        r = pick_boundary_loop(self, context)
        if r is None:
            self.report({'INFO'}, "Click an edge of a trimmed surface")
            return
        o, loops, li, outer = r
        msg = None
        if self.mode == 1 or li == outer:
            msg = untrim_outer(o)
            if msg is not None and self.mode == 1:        # pas de forme d'origine : on bouche au moins tous les trous
                for k, (idx, closed) in enumerate(loops):
                    if k != outer and closed:
                        fill_hole(o, idx)
                msg = None if len(loops) > 1 else msg
        else:
            fill_hole(o, loops[li][0])
        if msg:
            self.report({'WARNING'}, msg)
        self.reset_state()
        self.refresh(context)


class DESSIN_OT_untrim_holes(DessinUntrimBase):
    bl_idname = "dessin.untrim_holes"
    bl_label = "Untrim Holes"
    bl_description = ("Like UntrimHoles: click the edge of a hole in a surface to fill it (D: all the holes of that surface). "
                      "Stays active")
    TITLE = "Untrim Holes"
    MODES = ("This hole", "All holes")

    def prompt(self):
        return f"click the edge of a hole   [D: {self.MODES[self.mode]}]"

    def targets(self, r):
        o, loops, li, outer = r
        if self.mode == 1:
            return [k for k in range(len(loops)) if k != outer]
        return [] if li == outer else [li]

    def click(self, context):
        r = pick_boundary_loop(self, context)
        if r is None:
            self.report({'INFO'}, "Click the edge of a hole")
            return
        o, loops, li, outer = r
        todo = [k for k in range(len(loops)) if k != outer] if self.mode == 1 else ([] if li == outer else [li])
        if not todo:
            self.report({'INFO'}, "That is the outer edge, not a hole (use Untrim)")
            return
        # holes_fill n'ajoute pas de sommets : les indices des autres boucles restent valables
        for k in todo:
            if loops[k][1]:
                fill_hole(o, loops[k][0])
        self.reset_state()
        self.refresh(context)


def resample_path(P, n):
    """n+1 points régulièrement répartis (longueur d'arc) sur la polyligne P (n,3), de P[0] à P[-1]."""
    seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    t = np.linspace(0.0, s[-1], n + 1)
    return np.stack([np.interp(t, s, P[:, k]) for k in range(3)], axis=1)


# ---- SubD à partir de courbes (SubDLoft, SubDSweep1, SubDSweep2, SubD Revolve) ----

def subd_section(P, closed, k=None):
    """Points de cage d'une courbe : une polyligne à peu de sommets les garde (ses angles), une courbe dense
    (cercle, Bézier...) est rééchantillonnée régulièrement à k points."""
    P = np.asarray(P, dtype=np.float64)
    if k is None:
        try:
            f = int(bpy.context.scene.dessin.subd_faces)
        except (AttributeError, TypeError, ValueError):
            f = 2
        k = 4 * max(2, f) if closed else 2 * max(2, f) + 1
    if len(P) <= 24:
        return P.copy()
    if closed:
        Q = resample_path(np.vstack([P, P[:1]]), k)
        return Q[:-1]
    return resample_path(P, k - 1)


def subd_rail(R, closed, step):
    """Rail de la cage : ses sommets s'il en a peu, sinon des points espacés d'environ `step`."""
    R = np.asarray(R, dtype=np.float64)
    if len(R) <= 24:
        return R.copy()
    L = path_length(R, closed)
    n = int(max(3, min(64, round(L / max(step, 1e-9)))))
    if closed:
        return resample_path(np.vstack([R, R[:1]]), n)[:-1]
    return resample_path(R, n)


def subd_cap(V, F, ring, flip):
    """Bouchon en quads : un anneau intérieur (55 % vers le centre) puis un polygone central (comme SubDCylinder)."""
    V = list(V)
    c = np.mean([V[i] for i in ring], axis=0)
    base = len(V)
    V.extend([c + (V[i] - c) * 0.55 for i in ring])
    n = len(ring)
    for j in range(n):
        j2 = (j + 1) % n
        f = (ring[j], ring[j2], base + j2, base + j)
        F.append(tuple(reversed(f)) if flip else f)
    center = tuple(range(base, base + n))
    F.append(center if flip else tuple(reversed(center)))
    return np.array(V), F


def subd_interpolate(context, obj, iters=10):
    """La surface lisse passe par les points de la cage d'origine (les points des courbes) : on déplace la cage,
    plusieurs fois, de l'écart entre la surface et ces points."""
    me = obj.data
    n = len(me.vertices)
    T = np.empty(n * 3, dtype=np.float64)
    me.vertices.foreach_get('co', T)
    T = T.reshape(-1, 3)
    cage = T.copy()
    size = float(np.ptp(T, axis=0).max()) or 1.0
    for _ in range(iters):
        context.view_layer.update()
        dg = context.evaluated_depsgraph_get()
        ev = obj.evaluated_get(dg)
        em = ev.to_mesh()
        try:
            if len(em.vertices) < n:
                break
            E = np.empty(len(em.vertices) * 3, dtype=np.float64)
            em.vertices.foreach_get('co', E)
        finally:
            ev.to_mesh_clear()
        E = E.reshape(-1, 3)[:n]               # les n premiers sommets subdivisés correspondent aux sommets de la cage
        d = T - E
        cage += d
        me.vertices.foreach_set('co', cage.astype(np.float32).ravel())
        me.update()
        if float(np.abs(d).max()) < 1e-5 * size:
            break


def subd_object_from_cage(context, name, V, F, origin, interpolate=True):
    obj = mesh_object_from_arrays(context, name, V, F, origin, True)
    obj["wd_subd"] = True
    subd_modifier(obj, create=True)
    if interpolate:
        try:
            subd_interpolate(context, obj)
        except (RuntimeError, ValueError, ReferenceError):
            pass
    return obj


class _SubDCurvesOp(_ProfileOp):
    interpolate: bpy.props.BoolProperty(name="Through the curves", default=True,
                                        description="The smooth surface passes through smooth curves (circles, arcs, Bezier). "
                                                    "A polyline is always used as the control polygon, like its corners in Rhino")
    points: bpy.props.IntProperty(name="Points per curve", default=0, min=0, soft_max=64,
                                  description="Control points taken on each curve (0: automatic — a polyline keeps its corners)")
    cap: bpy.props.BoolProperty(name="Cap ends", default=True, description="Closes the ends when the curves are closed (solid)")
    delete_input: bpy.props.BoolProperty(name="Delete input", default=False)
    bl_options = {'REGISTER', 'UNDO'}

    def smooth_input(self, profs):
        return all(len(P) > 24 for P, _c in profs)

    def sections(self, profs):
        out = []
        for P, closed in profs:
            out.append((subd_section(P, closed, self.points or None), closed))
        return out

    def capped(self, V, F, nrows, n, closed_profile, closed_rows):
        if not (self.cap and closed_profile and not closed_rows and n >= 3):
            return np.asarray(V), list(F)
        V, F = subd_cap(V, list(F), list(range(n)), True)
        V, F = subd_cap(V, F, list(range((nrows - 1) * n, nrows * n)), False)
        return V, F

    def made(self, context, name, V, F, origin, objs, smooth=True):
        obj = subd_object_from_cage(context, name, V, F, origin, self.interpolate and smooth)
        if self.delete_input:
            delete_objects(objs)
        deselect_all_objects(context)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        msg = f"{name}: SubD created ({len(obj.data.vertices)} control points)"
        cmd_log(msg)
        self.report({'INFO'}, msg)
        return {'FINISHED'}


class DESSIN_OT_subd_loft(_SubDCurvesOp, bpy.types.Operator):
    bl_idname = "dessin.subd_loft"
    bl_label = "SubD Loft"
    bl_description = ("SubD through curves in the order you clicked them, like SubDLoft (options: closed loft, through the curves, "
                      "points per curve, cap)")

    closed: bpy.props.BoolProperty(name="Closed loft", default=False, description="Joins the last curve back to the first one")

    def invoke(self, context, event):
        _objs, profs = self.profiles(context)
        if len(profs) < 2:
            self.report({'INFO'}, "SubD Loft: click at least two curves in order, then Enter")
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self, width=300)

    def draw(self, context):
        col = self.layout.column()
        for k in ("closed", "interpolate", "points", "cap", "delete_input"):
            col.prop(self, k)

    def execute(self, context):
        objs, profs = self.profiles(context)
        if len(profs) < 2:
            self.report({'WARNING'}, "SubD Loft needs at least two curves")
            return {'CANCELLED'}
        kinds = {c for _p, c in profs}
        if len(kinds) > 1:
            self.report({'WARNING'}, "SubD Loft: mix of open and closed curves")
            return {'CANCELLED'}
        closed = kinds.pop()
        secs = self.sections(profs)
        n = max(len(p) for p, _c in secs)
        secs = [refine_points(p, closed, n) for p, _c in secs]
        secs = align_sections(secs, closed)
        closed_rows = self.closed and len(secs) > 2
        V, F = grid_mesh(np.array(secs), closed, closed_rows, False)
        V, F = self.capped(V, F, len(secs), n, closed, closed_rows)
        return self.made(context, "SubD Loft", V, F, np.asarray(secs[0]).mean(axis=0), objs, self.smooth_input(profs))


class _Subd_sweep1Body(_SubDCurvesOp, bpy.types.Operator):
    bl_idname = "dessin.subd_sweep1"
    bl_label = "SubD Sweep 1"
    bl_description = "SubD swept along one rail, like SubDSweep1: click the rail, then the cross-section(s), then Enter"

    frame: bpy.props.EnumProperty(name="Frame", default='FREEFORM',
                                  items=(('FREEFORM', "Freeform", "The sections follow the rail with minimal twist"),
                                         ('UPRIGHT', "Keep Z up (roadlike)", "The sections stay upright along the rail")))
    NRAILS = 1

    def invoke(self, context, event):
        _objs, profs = self.profiles(context)
        if len(profs) < self.NRAILS + 1:
            self.report({'INFO'}, "Click the rail" + ("s" if self.NRAILS == 2 else "") + ", then the cross-section(s), then Enter")
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self, width=300)

    def draw(self, context):
        col = self.layout.column()
        if self.NRAILS == 1:
            col.prop(self, "frame", text="")
        for k in ("interpolate", "points", "cap", "delete_input"):
            col.prop(self, k)

    def execute(self, context):
        objs, profs = self.profiles(context)
        nr = self.NRAILS
        if len(profs) < nr + 1:
            self.report({'WARNING'}, "Not enough curves: rail(s) first, then at least one cross-section")
            return {'CANCELLED'}
        rails, sections = profs[:nr], self.sections(profs[nr:])
        kinds = {c for _p, c in sections}
        if len(kinds) > 1:
            self.report({'WARNING'}, "SubD Sweep: mix of open and closed cross-sections")
            return {'CANCELLED'}
        sclosed = kinds.pop()
        n = max(len(p) for p, _c in sections)
        sections = [(refine_points(p, sclosed, n), c) for p, c in sections]
        S0 = sections[0][0]
        per = path_length(S0, sclosed) / max(len(S0), 1)
        # rail : un rang de cage environ toutes les demi-largeurs de section (assez pour suivre le rail, pas plus)
        R = [(subd_rail(P, c, max(per * len(S0) / 2.0, path_length(P, c) / 24.0)), c) for P, c in rails]
        if nr == 1:
            built, msg = sweep1_surface(R[0], sections, self.frame == 'UPRIGHT', True, False)
        else:
            built, msg = sweep2_surface(R[0], R[1], sections, False)
        if built is None:
            self.report({'WARNING'}, msg)
            return {'CANCELLED'}
        V, F, _closed = built
        V = np.asarray(V)
        rclosed = R[0][1]
        V, F = self.capped(V, F, len(V) // n, n, sclosed, rclosed)
        return self.made(context, "SubD Sweep" + (" 1" if nr == 1 else " 2"), V, F, S0.mean(axis=0), objs, self.smooth_input(profs[nr:]))


class DESSIN_OT_subd_sweep1(_Subd_sweep1Body):
    """Registered class; the shared code lives in the unregistered base so SubD variants can inherit it."""
    bl_idname = _Subd_sweep1Body.bl_idname
    bl_label = _Subd_sweep1Body.bl_label
    bl_description = _Subd_sweep1Body.bl_description


class DESSIN_OT_subd_sweep2(_Subd_sweep1Body):
    bl_idname = "dessin.subd_sweep2"
    bl_label = "SubD Sweep 2"
    bl_description = "SubD swept along two rails, like SubDSweep2: click the two rails, then the cross-section(s), then Enter"
    NRAILS = 2


class DESSIN_OT_subd_revolve(_RevolveBody):
    bl_idname = "dessin.subd_revolve"
    bl_label = "SubD Revolve"
    bl_description = ("SubD revolved around an axis, like Revolve with a SubD result: select the curves, Enter, two points for the axis, "
                      "then Enter for 360° or type the angle (C: cap, D: delete input). The surface passes through the profile")
    TITLE = "SubD Revolve"

    def build(self, context, spec):
        _, o, d, angle, cap, delete = spec
        objs = [obj for obj, _m in self.items if obj.name in bpy.data.objects]
        dg = bpy.context.evaluated_depsgraph_get()
        made = []
        full = abs(angle) >= 359.999
        try:
            f = int(context.scene.dessin.subd_faces)
        except (AttributeError, TypeError, ValueError):
            f = 2
        steps = 4 * max(2, f) if full else max(2, int(math.ceil(abs(angle) / 360.0 * 4 * max(2, f))))
        ang = math.radians(max(-360.0, min(360.0, angle)))
        oo = np.array(o, dtype=np.float64)
        for obj in objs:
            for P, closed in object_paths(obj, dg) or []:
                Q = subd_section(P, closed)
                rows = []
                for s_ in range(steps if full else steps + 1):
                    Rm = rotation_matrix(d, ang * s_ / steps)
                    rows.append((Q - oo) @ Rm.T + oo)
                V, F = grid_mesh(np.array(rows), closed, full, False)
                if cap and closed and not full:
                    n = len(Q)
                    V, F = subd_cap(V, list(F), list(range(n)), True)
                    V, F = subd_cap(V, F, list(range(len(rows) * n - n, len(rows) * n)), False)
                made.append(subd_object_from_cage(context, "SubD Revolve", V, F, o, len(P) > 24))
        if not made:
            self.report({'WARNING'}, "SubD Revolve works on curves (or outlines without faces)")
            self.committed = True
            return None
        if delete:
            delete_objects(objs)
            self.items = []
        deselect_all_objects(context)
        for ob in made:
            ob.select_set(True)
        context.view_layer.objects.active = made[-1]
        self.committed = True
        return None


def edge_surface(curves, segments=24):
    """2 courbes : surface réglée ; 3 ou 4 courbes bout à bout : carreau de Coons. Retourne ((V, F), message)."""
    curves = [np.asarray(c, dtype=np.float64) for c in curves]
    k = len(curves)
    lens = [path_length(c, False) for c in curves]
    if min(lens) < 1e-9:
        return None, "A curve is too short"
    if k == 2:
        a, b = curves
        if np.linalg.norm(a[0] - b[0]) + np.linalg.norm(a[-1] - b[-1]) > np.linalg.norm(a[0] - b[-1]) + np.linalg.norm(a[-1] - b[0]):
            b = b[::-1]
        A, C = resample_path(a, segments), resample_path(b, segments)
        rows = np.stack([(1 - v) * A + v * C for v in np.linspace(0.0, 1.0, 3)])
        return grid_mesh(rows, False, False, False), ""
    if k not in (3, 4):
        return None, "Edge Surface needs 2, 3 or 4 curves"
    tol = 0.02 * max(lens)
    chain = [curves[0]]
    left = list(range(1, k))
    while left:
        end = chain[-1][-1]
        best = None
        for j in left:
            for flip in (False, True):
                c = curves[j][::-1] if flip else curves[j]
                d = float(np.linalg.norm(c[0] - end))
                if best is None or d < best[0]:
                    best = (d, j, c)
        if best[0] > tol:
            return None, "The curves must touch end to end"
        chain.append(best[2])
        left.remove(best[1])
    if float(np.linalg.norm(chain[-1][-1] - chain[0][0])) > tol:
        return None, "The curves must form a closed chain of 3 or 4 edges"
    la = (path_length(chain[0], False) + (path_length(chain[2], False) if k == 4 else 0.0)) / (2 if k == 4 else 1)
    lb = (path_length(chain[1], False) + (path_length(chain[3], False) if k == 4 else 0.0)) / (2 if k == 4 else 1)
    if k == 3:
        lb = max(lb, path_length(chain[2], False))
    nu = int(max(2, segments))
    nv = int(min(400, max(2, round(segments * lb / max(la, 1e-9)))))
    A = resample_path(chain[0], nu)
    B = resample_path(chain[1], nv)
    if k == 4:
        C = resample_path(chain[2][::-1], nu)
        D = resample_path(chain[3][::-1], nv)
    else:
        C = np.tile(B[-1], (nu + 1, 1))
        D = resample_path(chain[2][::-1], nv)
    p00, p10, p01, p11 = A[0], A[-1], C[0], C[-1]
    rows = []
    for j in range(nv + 1):
        v = j / nv
        row = []
        for i in range(nu + 1):
            u = i / nu
            S = ((1 - v) * A[i] + v * C[i] + (1 - u) * D[j] + u * B[j]
                 - ((1 - u) * (1 - v) * p00 + u * (1 - v) * p10 + (1 - u) * v * p01 + u * v * p11))
            row.append(S)
        rows.append(row)
    return grid_mesh(np.array(rows), False, False, False), ""


class DESSIN_OT_edge_srf(_ProfileOp, bpy.types.Operator):
    bl_idname = "dessin.edge_srf"
    bl_label = "Edge Surface"
    bl_description = ("Creates a surface from 2, 3 or 4 curves touching end to end: click the curves, then Enter / Space")
    bl_options = {'REGISTER', 'UNDO'}

    segments: bpy.props.IntProperty(name="Segments", default=24, min=2, max=400,
                                    description="Number of subdivisions along the first edge")
    delete_input: bpy.props.BoolProperty(name="Delete input", default=False)

    def invoke(self, context, event):
        return self.execute(context)

    def execute(self, context):
        dg = context.evaluated_depsgraph_get()
        objs, profs = self.profiles(context)
        if len(profs) < 2:
            self.report({'INFO'}, "Click 2, 3 or 4 curves, then Enter")
            return {'CANCELLED'}
        if len(profs) > 4:
            self.report({'WARNING'}, "Edge Surface works with 2 to 4 curves")
            return {'CANCELLED'}
        built, msg = edge_surface([p[0] for p in profs], self.segments)
        if built is None:
            self.report({'WARNING'}, msg)
            return {'CANCELLED'}
        V, F = built
        out = mesh_object_from_arrays(context, "Edge Surface", V, F, np.asarray(V).mean(axis=0), False)
        if self.delete_input:
            delete_objects(objs)
        deselect_all_objects(context)
        out.select_set(True)
        context.view_layer.objects.active = out
        return {'FINISHED'}


class DESSIN_OT_thicken(_ProfileOp, bpy.types.Operator):
    bl_idname = "dessin.thicken"
    bl_label = "Thicken"
    bl_description = ("Gives a thickness to surfaces, making solids: click the surfaces (or select them first), Enter / Space, "
                      "then the thickness and the direction")
    bl_options = {'REGISTER', 'UNDO'}

    thickness: bpy.props.FloatProperty(name="Thickness", default=0.02, min=1e-6, subtype='DISTANCE', unit='LENGTH')
    direction: bpy.props.EnumProperty(name="Direction", default='NORMAL',
                                      items=(('NORMAL', "Along the normal", ""),
                                             ('OPPOSITE', "Opposite to the normal", ""),
                                             ('BOTH', "Both sides (centered)", "")))
    delete_input: bpy.props.BoolProperty(name="Delete input", default=True)

    def invoke(self, context, event):
        if not [o for o in context.selected_objects if o.type == 'MESH' and len(o.data.polygons)]:
            self.report({'INFO'}, "Click the surfaces to thicken, then Enter")
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self, width=300)

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, "thickness")
        col.prop(self, "direction", text="")
        col.prop(self, "delete_input")

    def execute(self, context):
        targets = [o for o in context.selected_objects if o.type == 'MESH' and len(o.data.polygons)]
        if not targets:
            self.report({'INFO'}, "Click the surfaces to thicken, then Enter")
            return {'CANCELLED'}
        made = []
        for obj in targets:
            if self.direction == 'BOTH':
                me = offset_surface_mesh(obj, self.thickness * 0.5, True, True)
            else:
                me = offset_surface_mesh(obj, self.thickness * (1.0 if self.direction == 'NORMAL' else -1.0), True, False)
            new = bpy.data.objects.new("Thick " + obj.name, me)
            new.matrix_world = obj.matrix_world.copy()
            for c in (obj.users_collection or [context.scene.collection]):
                c.objects.link(new)
            made.append(new)
        if self.delete_input:
            delete_objects(targets)
        deselect_all_objects(context)
        for ob in made:
            ob.select_set(True)
        context.view_layer.objects.active = made[-1]
        return {'FINISHED'}


def _is_cutter(o):
    return o.type == 'CURVE' or (o.type == 'MESH' and len(o.data.polygons) == 0 and len(o.data.edges) > 0)


class DESSIN_OT_split_face(bpy.types.Operator):
    bl_idname = "dessin.split_face"
    bl_label = "Split Face"
    bl_description = ("Splits the faces of a surface along curves or polylines drawn on it, seen from the current view: "
                      "click the surface and the curves, then Enter / Space")
    bl_options = {'REGISTER', 'UNDO'}

    cut_through: bpy.props.BoolProperty(name="Through the whole object", default=False,
                                        description="Also cut the faces hidden behind the first one")
    separate: bpy.props.BoolProperty(name="Separate the pieces", default=False,
                                     description="Make the area inside the curves a separate object")
    delete_curves: bpy.props.BoolProperty(name="Delete the curves", default=False)

    @staticmethod
    def _view(context):
        area = context.area if (context.area and context.area.type == 'VIEW_3D') else None
        if area is None:
            for a in context.window.screen.areas:
                if a.type == 'VIEW_3D':
                    area = a
                    break
        if area is None:
            return None, None
        reg = next((r for r in area.regions if r.type == 'WINDOW'), None)
        return area, reg

    def invoke(self, context, event):
        sel = ordered_selection(context, ('MESH', 'CURVE'))
        if not [o for o in sel if not _is_cutter(o)] or not [o for o in sel if _is_cutter(o)]:
            self.report({'INFO'}, "Click the surface, then the curves drawn on it, then Enter")
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self, width=300)

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, "cut_through")
        col.prop(self, "separate")
        col.prop(self, "delete_curves")

    def execute(self, context):
        sel = ordered_selection(context, ('MESH', 'CURVE'))
        cutters = [o for o in sel if _is_cutter(o)]
        targets = [o for o in sel if not _is_cutter(o)]
        if not targets or not cutters:
            self.report({'INFO'}, "Click the surface, then the curves drawn on it, then Enter")
            return {'CANCELLED'}
        area, reg = self._view(context)
        if area is None:
            self.report({'WARNING'}, "A 3D view is needed: the cut follows what you see")
            return {'CANCELLED'}
        win = context.window
        made, cut = [], 0
        for tgt in targets:
            for o in context.view_layer.objects:
                o.select_set(False)
            tgt.select_set(True)
            context.view_layer.objects.active = tgt
            before = len(tgt.data.polygons)
            try:
                bpy.ops.object.mode_set(mode='EDIT')
                bpy.ops.mesh.select_all(action='DESELECT')
                for c in cutters:
                    c.select_set(True)
                with context.temp_override(window=win, area=area, region=reg):
                    bpy.ops.mesh.knife_project(cut_through=self.cut_through)
                if self.separate:
                    bm = bmesh.from_edit_mesh(tgt.data)
                    if any(f.select for f in bm.faces):
                        names = {o.name for o in bpy.data.objects}
                        bpy.ops.mesh.separate(type='SELECTED')
                        made += [o for o in bpy.data.objects if o.name not in names]
            except RuntimeError as exc:
                self.report({'WARNING'}, "Cut failed on %s: %s" % (tgt.name, exc))
            finally:
                if context.object and context.object.mode != 'OBJECT':
                    bpy.ops.object.mode_set(mode='OBJECT')
            cut += max(0, len(tgt.data.polygons) - before)
        for o in context.view_layer.objects:
            o.select_set(False)
        if self.delete_curves:
            delete_objects(cutters)
        for o in targets + made:
            if o.name in bpy.data.objects:
                o.select_set(True)
        context.view_layer.objects.active = targets[0]
        if cut == 0 and not made:
            self.report({'WARNING'}, "Nothing was cut: the curves must be seen over the surface from the current view")
            return {'CANCELLED'}
        self.report({'INFO'}, "Face split")
        return {'FINISHED'}


def project_curve_paths(paths, targets, depsgraph, mode, both, view_dir):
    """Projette des contours (points monde) sur des maillages : liste de (points (n,3), fermé)."""
    from mathutils.bvhtree import BVHTree
    trees = []
    lo, hi = None, None
    for t in targets:
        try:
            tree = BVHTree.FromObject(t, depsgraph)
        except Exception:
            continue
        M = t.matrix_world.copy()
        trees.append((tree, M, M.inverted_safe()))
        bb = np.array([tuple(M @ Vector(c)) for c in t.bound_box])
        lo = bb.min(axis=0) if lo is None else np.minimum(lo, bb.min(axis=0))
        hi = bb.max(axis=0) if hi is None else np.maximum(hi, bb.max(axis=0))
    if not trees:
        return []
    diag = float(np.linalg.norm(hi - lo)) or 1.0
    step = diag / 150.0
    out = []
    for P, closed in paths:
        if mode == 'AUTO':
            pl = _plane_of(P) if len(P) >= 3 else None
            if pl is not None and pl[2] <= max(1e-3 * float(np.ptp(P, axis=0).max()), 1e-7):
                d = pl[1]
            else:
                d = np.array([0.0, 0.0, -1.0])
        elif mode == 'VIEW':
            d = np.array(view_dir, dtype=np.float64)
        else:
            d = {'X': np.array([1.0, 0, 0]), 'Y': np.array([0, 1.0, 0]), 'Z': np.array([0, 0, -1.0])}[mode]
        d = d / (np.linalg.norm(d) or 1.0)
        Q = [P[0]]
        n = len(P)
        for i in range(n if closed else n - 1):
            a, b = P[i], P[(i + 1) % n]
            k = max(1, min(200, int(math.ceil(float(np.linalg.norm(b - a)) / step))))
            for j in range(1, k + 1):
                Q.append(a + (b - a) * (j / k))
        if closed:
            Q = Q[:-1]
        hits = []
        for q in Q:
            best = None
            for tree, M, Mi in trees:
                o = Mi @ Vector(q)
                for sgn in ((1.0, -1.0) if both else (1.0,)):
                    dl = (Mi.to_3x3() @ Vector(d * sgn))
                    ln = dl.length
                    if ln < 1e-12:
                        continue
                    loc, nor, idx, dist = tree.ray_cast(o, dl / ln)
                    if loc is None:
                        continue
                    w = M @ loc
                    t = (w - Vector(q)).length
                    if best is None or t < best[0]:
                        best = (t, np.array(w))
            hits.append(None if best is None else best[1])
        if closed and all(h is not None for h in hits):
            out.append((np.array(hits), True))
            continue
        if closed:
            k0 = next(i for i, h in enumerate(hits) if h is None)
            hits = hits[k0:] + hits[:k0]
        chain = []
        for h in hits + [None]:
            if h is None:
                if len(chain) >= 2:
                    out.append((np.array(chain), False))
                chain = []
            else:
                chain.append(h)
    return out


class DESSIN_OT_project_curve(bpy.types.Operator):
    bl_idname = "dessin.project_curve"
    bl_label = "Project Curve"
    bl_description = ("Projects curves onto surfaces: click the curves, then the surface(s), then Enter / Space. "
                      "The projected curves can then be used with Split Face or Trim")
    bl_options = {'REGISTER', 'UNDO'}

    direction: bpy.props.EnumProperty(
        name="Direction", default='AUTO',
        items=(('AUTO', "Perpendicular to the curve's plane", "Falls back to straight down for non-planar curves"),
               ('Z', "Along Z (down)", ""), ('X', "Along X", ""), ('Y', "Along Y", ""),
               ('VIEW', "Current view", "")))
    both_ways: bpy.props.BoolProperty(name="Both ways", default=True,
                                      description="Also look behind the curve, not only in the projection direction")
    delete_input: bpy.props.BoolProperty(name="Delete the original curves", default=False)

    def _split(self, context):
        sel = ordered_selection(context, ('MESH', 'CURVE'))
        return [o for o in sel if _is_cutter(o)], [o for o in sel if not _is_cutter(o)]

    def invoke(self, context, event):
        cur, tgt = self._split(context)
        if not cur or not tgt:
            self.report({'INFO'}, "Click the curves, then the surface(s), then Enter")
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self, width=320)

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, "direction", text="")
        col.prop(self, "both_ways")
        col.prop(self, "delete_input")

    def execute(self, context):
        cur, tgt = self._split(context)
        if not cur or not tgt:
            self.report({'INFO'}, "Click the curves, then the surface(s), then Enter")
            return {'CANCELLED'}
        dg = context.evaluated_depsgraph_get()
        view_dir = (0.0, 0.0, -1.0)
        rv = None
        if context.area and context.area.type == 'VIEW_3D':
            rv = context.area.spaces.active.region_3d
        else:
            for a in context.window.screen.areas:
                if a.type == 'VIEW_3D':
                    rv = a.spaces.active.region_3d
                    break
        if rv is not None:
            v = rv.view_rotation @ Vector((0.0, 0.0, -1.0))
            view_dir = (v.x, v.y, v.z)
        made = []
        for c in cur:
            paths = object_paths(c, dg)
            chains = project_curve_paths(paths, tgt, dg, self.direction, self.both_ways, view_dir)
            if chains:
                made.append((c, chains))
        if not made:
            self.report({'WARNING'}, "Nothing to project: the curves do not face the surface in this direction")
            return {'CANCELLED'}
        for o in context.view_layer.objects:
            o.select_set(False)
        last = None
        count = 0
        for c, chains in made:
            last = build_edge_object(context, "Projected " + c.name, [(Q, cl) for Q, cl in chains])
            last.select_set(True)
            count += len(chains)
        if self.delete_input:
            delete_objects([c for c, _ in made])
        context.view_layer.objects.active = last
        self.report({'INFO'}, "%d projected curve(s)" % count)
        return {'FINISHED'}


def patch_surface(P, density):
    """Surface de remplissage (membrane) dans un contour fermé 3D (n,3) monde. Retourne (V, F) ou None."""
    from mathutils.geometry import delaunay_2d_cdt
    V2v = Vector
    c = P.mean(axis=0)
    _u, _s, vt = np.linalg.svd(P - c)
    ax_u, ax_v, nrm = vt[0], vt[1], vt[2]
    diag = float(np.linalg.norm(np.ptp(P, axis=0))) or 1.0
    L = diag / max(6, density)
    # contour rééchantillonné
    B = []
    n = len(P)
    for i in range(n):
        a, b = P[i], P[(i + 1) % n]
        k = max(1, int(math.ceil(float(np.linalg.norm(b - a)) / L)))
        for j in range(k):
            B.append(a + (b - a) * (j / k))
    B = np.array(B)
    nb = len(B)
    uv = np.stack([(B - c) @ ax_u, (B - c) @ ax_v], axis=1)
    umin, vmin = uv.min(axis=0)
    umax, vmax = uv.max(axis=0)
    gu = np.arange(umin + L * 0.5, umax, L)
    gv = np.arange(vmin + L * 0.5, vmax, L)
    G = np.array([(x, y) for x in gu for y in gv]) if len(gu) and len(gv) else np.zeros((0, 2))
    if len(G):
        inside = np.zeros(len(G), dtype=bool)
        for i in range(nb):
            x1, y1 = uv[i]
            x2, y2 = uv[(i + 1) % nb]
            cond = ((y1 > G[:, 1]) != (y2 > G[:, 1]))
            xint = (x2 - x1) * (G[:, 1] - y1) / ((y2 - y1) or 1e-30) + x1
            inside ^= cond & (G[:, 0] < xint)
        dmin = np.min(np.linalg.norm(G[:, None, :] - uv[None, :, :], axis=2), axis=1)
        G = G[inside & (dmin > 0.6 * L)]
    pts2 = [V2v((float(x), float(y))) for x, y in uv] + [V2v((float(x), float(y))) for x, y in G]
    faces_in = [list(range(nb))]
    try:
        vo, eo, fo, ov, oe, of = delaunay_2d_cdt(pts2, [], faces_in, 1, 1e-7)
    except Exception:
        return None
    if not fo:
        return None
    ni = len(G)
    m = len(vo)
    # correspondance : sommets de sortie -> entrée
    mp = []
    for k in range(m):
        src = ov[k]
        mp.append(src[0] if src else -1)
    if any(s < 0 for s in mp):
        return None
    pos = np.zeros((m, 3))
    fixed = np.zeros(m, dtype=bool)
    for k, s in enumerate(mp):
        if s < nb:
            pos[k] = B[s]
            fixed[k] = True
        else:
            g = G[s - nb]
            pos[k] = c + ax_u * g[0] + ax_v * g[1]
    free = np.where(~fixed)[0]
    if len(free) > 3500:
        return None
    if len(free):
        idx = {int(v): i for i, v in enumerate(free)}
        nbrs = [set() for _ in range(m)]
        for f in fo:
            for i in range(len(f)):
                a, b = f[i], f[(i + 1) % len(f)]
                nbrs[a].add(b)
                nbrs[b].add(a)
        A = np.zeros((len(free), len(free)))
        rhs = np.zeros((len(free), 3))
        for v in free:
            i = idx[int(v)]
            A[i, i] = len(nbrs[v])
            for w in nbrs[v]:
                if fixed[w]:
                    rhs[i] += pos[w]
                else:
                    A[i, idx[int(w)]] -= 1.0
        try:
            sol = np.linalg.solve(A, rhs)
        except np.linalg.LinAlgError:
            return None
        pos[free] = sol
    F = [tuple(f) for f in fo]
    return pos, F


class DESSIN_OT_patch(bpy.types.Operator):
    bl_idname = "dessin.patch"
    bl_label = "Patch"
    bl_description = ("Fills a closed outline with a smooth surface (like a stretched membrane): click closed curves, "
                      "or a surface with a hole (its open edges are filled), then Enter / Space")
    bl_options = {'REGISTER', 'UNDO'}

    density: bpy.props.IntProperty(name="Density", default=24, min=8, max=80,
                                   description="Number of divisions across the outline: more = finer surface")
    delete_input: bpy.props.BoolProperty(name="Delete input", default=False)

    def _loops(self, context):
        dg = context.evaluated_depsgraph_get()
        loops, used = [], []
        for o in ordered_selection(context):
            got = False
            if o.type == 'MESH' and len(o.data.polygons):
                for lp in _surface_loops(o):
                    if lp['closed'] and len(lp['P']) >= 3:
                        loops.append(np.array(lp['P'], dtype=np.float64))
                        got = True
            else:
                for P, closed in object_paths(o, dg):
                    if closed and len(P) >= 3:
                        loops.append(np.array(P, dtype=np.float64))
                        got = True
            if got:
                used.append(o)
        return loops, used

    def invoke(self, context, event):
        loops, _u = self._loops(context)
        if not loops:
            self.report({'INFO'}, "Click closed curves (or a surface with a hole), then Enter")
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self, width=280)

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, "density")
        col.prop(self, "delete_input")

    def execute(self, context):
        loops, used = self._loops(context)
        if not loops:
            self.report({'INFO'}, "Click closed curves (or a surface with a hole), then Enter")
            return {'CANCELLED'}
        for o in context.view_layer.objects:
            o.select_set(False)
        last, failed = None, 0
        for P in loops:
            r = patch_surface(P, self.density)
            if r is None:
                failed += 1
                continue
            V, F = r
            last = mesh_object_from_arrays(context, "Patch", V, F, V.mean(axis=0), True)
            last.select_set(True)
        if last is None:
            self.report({'WARNING'}, "Patch failed: the outline must be closed, not self-crossing, and not too complex")
            return {'CANCELLED'}
        if self.delete_input:
            delete_objects(used)
        context.view_layer.objects.active = last
        if failed:
            self.report({'WARNING'}, "%d outline(s) could not be filled" % failed)
        return {'FINISHED'}


def cap_mesh(me, planar_only=True):
    """Bouche les trous (bords ouverts) d'un maillage. Retourne (nb bouchés, nb ignorés)."""
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bound = [e for e in bm.edges if len(e.link_faces) == 1]
    capped = skipped = 0
    if bound:
        ids = {}
        verts = []
        edges = []
        for e in bound:
            pair = []
            for v in e.verts:
                if v.index not in ids:
                    ids[v.index] = len(verts)
                    verts.append(v)
                pair.append(ids[v.index])
            edges.append(tuple(pair))
        for path, closed in wire_paths(len(verts), edges):
            if not closed or len(path) < 3:
                skipped += 1
                continue
            vs = [verts[i] for i in path]
            if vs[0] == vs[-1]:
                vs = vs[:-1]
            P = np.array([tuple(v.co) for v in vs])
            pl = _plane_of(P)
            scale = float(np.ptp(P, axis=0).max()) if len(P) else 0.0
            flat = pl is not None and pl[2] <= max(1e-4 * scale, 1e-7)
            if planar_only and not flat:
                skipped += 1
                continue
            # sens : l'arête du bord doit être parcourue à l'envers par la nouvelle face
            e0 = bm.edges.get((vs[0], vs[1]))
            if e0 is not None and e0.link_faces:
                f = e0.link_faces[0]
                for lp in f.loops:
                    if lp.vert == vs[0] and lp.link_loop_next.vert == vs[1]:
                        vs = vs[::-1]
                        break
                    if lp.vert == vs[1] and lp.link_loop_next.vert == vs[0]:
                        break
            try:
                if flat:
                    bm.faces.new(vs)
                else:
                    es = [bm.edges.get((vs[i], vs[(i + 1) % len(vs)])) for i in range(len(vs))]
                    bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=False, edges=[x for x in es if x])
                capped += 1
            except ValueError:
                skipped += 1
    bm.to_mesh(me)
    bm.free()
    me.update()
    return capped, skipped


class DESSIN_OT_cap(_ProfileOp, bpy.types.Operator):
    bl_idname = "dessin.cap"
    bl_label = "Cap"
    bl_description = ("Closes the open ends of surfaces to make solids: click the objects (or select them first), Enter / Space")
    bl_options = {'REGISTER', 'UNDO'}

    planar_only: bpy.props.BoolProperty(name="Planar holes only", default=True,
                                        description="Only caps holes whose edge is flat (off: fills any hole with triangles)")

    def invoke(self, context, event):
        return self.execute(context)

    def execute(self, context):
        targets = [o for o in context.selected_objects if o.type == 'MESH' and len(o.data.polygons)]
        if not targets:
            self.report({'INFO'}, "Click the open surfaces to cap, then Enter")
            return {'CANCELLED'}
        done = skipped = 0
        for obj in targets:
            c, s = cap_mesh(obj.data, self.planar_only)
            done += c
            skipped += s
        if not done:
            self.report({'WARNING'}, "Nothing to cap" + (f" ({skipped} hole(s) not flat)" if skipped else ""))
            return {'CANCELLED'}
        self.report({'INFO'}, f"{done} hole(s) capped" + (f", {skipped} ignored" if skipped else ""))
        return {'FINISHED'}


# ---- Surfaces (lot 2) : Blend / Match / Rail Revolve / Shell ----

def _densify(P, closed, step):
    """Points régulièrement espacés (≈ step) le long d'une polyligne."""
    P = np.asarray(P, dtype=np.float64)
    if closed:
        P = np.vstack([P, P[:1]])
    L = path_length(P, False)
    n = int(min(4000, max(2, L / max(step, 1e-9))))
    return resample_path(P, n)


def _surface_loops(obj):
    """Bords d'un maillage à faces, en coordonnées monde :
    [{'ids': [indices de sommets], 'closed': bool, 'P': (n,3), 'out': (nseg,3) direction sortante de chaque segment}]"""
    me = obj.data
    M = np.array(obj.matrix_world, dtype=np.float64)
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get('co', co)
    world = co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3]
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.edges.ensure_lookup_table()
    outward = {}
    edges = []
    ids = {}
    verts = []
    for e in bm.edges:
        if len(e.link_faces) != 1:
            continue
        a, b = e.verts[0].index, e.verts[1].index
        fc = np.array(e.link_faces[0].calc_center_median(), dtype=np.float64) @ M[:3, :3].T + M[:3, 3]
        t = world[b] - world[a]
        ln = float(np.linalg.norm(t))
        if ln < 1e-12:
            continue
        t /= ln
        d = (world[a] + world[b]) * 0.5 - fc
        d = d - t * float(d.dot(t))
        dn = float(np.linalg.norm(d))
        outward[(min(a, b), max(a, b))] = d / dn if dn > 1e-12 else np.zeros(3)
        pair = []
        for v in (a, b):
            if v not in ids:
                ids[v] = len(verts)
                verts.append(v)
            pair.append(ids[v])
        edges.append(tuple(pair))
    bm.free()
    out = []
    for path, closed in wire_paths(len(verts), edges):
        vid = [verts[i] for i in path]
        if closed and len(vid) > 1 and vid[0] == vid[-1]:
            vid = vid[:-1]
        if len(vid) < 2:
            continue
        n = len(vid)
        nseg = n if closed else n - 1
        segs = np.array([outward.get((min(vid[i], vid[(i + 1) % n]), max(vid[i], vid[(i + 1) % n])), np.zeros(3))
                         for i in range(nseg)])
        out.append({'ids': vid, 'closed': bool(closed), 'P': world[vid], 'out': segs})
    return out


def _edge_candidates(obj, depsgraph):
    """Bords utilisables d'un objet : surface (bords + sens sortant) ou courbe (chemins, sans sens)."""
    if obj.type == 'MESH' and len(obj.data.polygons):
        return _surface_loops(obj)
    return [{'ids': None, 'closed': bool(c), 'P': np.asarray(P, dtype=np.float64), 'out': None}
            for P, c in object_paths(obj, depsgraph)]


def _facing_run(loop, other_pts, spacing):
    """Plus longue suite continue de segments de `loop` qui regardent `other_pts` (distance minimale).
    Retourne (indices de position dans loop['P'], segments sortants correspondants)."""
    P = loop['P']
    n = len(P)
    closed = loop['closed']
    nseg = n if closed else n - 1
    if nseg < 1:
        return None
    a = P[:nseg]
    b = P[(np.arange(nseg) + 1) % n]
    mids = (a + b) * 0.5
    d = np.empty(nseg)
    for s in range(0, nseg, 512):
        blk = mids[s:s + 512]
        d[s:s + 512] = np.sqrt(((blk[:, None, :] - other_pts[None, :, :]) ** 2).sum(axis=2)).min(axis=1)
    thr = float(d.min()) * 1.02 + spacing
    keep = d <= thr
    if keep.all():
        segs = list(range(nseg))
    else:
        if closed:
            s0 = int(np.argmin(keep))                      # un segment qui ne regarde pas : point de départ
            order = [(s0 + 1 + k) % nseg for k in range(nseg)]
        else:
            order = list(range(nseg))
        best, cur = [], []
        for i in order:
            if keep[i]:
                cur.append(i)
            else:
                if len(cur) > len(best):
                    best = cur
                cur = []
        if len(cur) > len(best):
            best = cur
        segs = best
    if not segs:
        return None
    idx = [segs[0]] + [(s + 1) % n for s in segs]
    return idx, (loop['out'][segs] if loop['out'] is not None else None)


def _blend_edges(objA, objB, depsgraph):
    """Choisit les deux bords qui se font face. Retourne (run A, run B) = (points (n,3), sortants (n-1,3) ou None)."""
    ca, cb = _edge_candidates(objA, depsgraph), _edge_candidates(objB, depsgraph)
    if not ca or not cb:
        return None
    allp = np.vstack([l['P'] for l in ca + cb])
    diag = float(np.linalg.norm(allp.max(axis=0) - allp.min(axis=0))) or 1.0
    step = diag / 250.0
    da = [_densify(l['P'], l['closed'], step) for l in ca]
    db = [_densify(l['P'], l['closed'], step) for l in cb]
    best = None
    for i, A in enumerate(da):
        for j, B in enumerate(db):
            d = float(np.sqrt(((A[::max(1, len(A) // 120), None, :] - B[None, ::max(1, len(B) // 120), :]) ** 2).sum(axis=2)).min())
            if best is None or d < best[0]:
                best = (d, i, j)
    _d, i, j = best
    ra = _facing_run(ca[i], db[j], step)
    rb = _facing_run(cb[j], da[i], step)
    if ra is None or rb is None:
        return None
    return (ca[i]['P'][ra[0]], ra[1]), (cb[j]['P'][rb[0]], rb[1])


def _nearest_dir(samples, run_pts, run_out):
    """Direction sortante du segment le plus proche de chaque échantillon."""
    if run_out is None:
        return np.zeros_like(samples)
    mids = (run_pts[:-1] + run_pts[1:]) * 0.5
    d = ((samples[:, None, :] - mids[None, :, :]) ** 2).sum(axis=2)
    return run_out[d.argmin(axis=1)]


def blend_surface(runA, runB, tangent=True, tension=1.0, segments=24, rows_n=12):
    """Surface de raccord entre deux bords : réglée (position) ou hermite (tangence avec les surfaces)."""
    (PA, oA), (PB, oB) = runA, runB
    if path_length(PA, False) < 1e-9 or path_length(PB, False) < 1e-9:
        return None, "An edge is too short"
    if np.linalg.norm(PA[0] - PB[0]) + np.linalg.norm(PA[-1] - PB[-1]) > np.linalg.norm(PA[0] - PB[-1]) + np.linalg.norm(PA[-1] - PB[0]):
        PB = PB[::-1]
        oB = oB[::-1] if oB is not None else None
    n = int(max(segments, 8))
    A = resample_path(PA, n)
    B = resample_path(PB, n)
    gap = np.linalg.norm(B - A, axis=1)
    if float(gap.max()) < 1e-9:
        return None, "The edges are already touching"
    rows = []
    ts = np.linspace(0.0, 1.0, int(max(rows_n, 2)) + 1) if tangent else np.array([0.0, 1.0])
    if tangent:
        dA = _nearest_dir(A, PA, oA)
        dB = _nearest_dir(B, PB if oB is not None else PB, oB)
        L = (gap * float(tension))[:, None]
        # un sens sortant opposé à la direction du raccord est inversé (surface dont les normales sont à l'envers)
        flipA = (dA * (B - A)).sum(axis=1) < 0
        flipB = (dB * (A - B)).sum(axis=1) < 0
        dA[flipA] *= -1.0
        dB[flipB] *= -1.0
    for t in ts:
        if tangent:
            h00, h10, h01, h11 = 2 * t ** 3 - 3 * t ** 2 + 1, t ** 3 - 2 * t ** 2 + t, -2 * t ** 3 + 3 * t ** 2, t ** 3 - t ** 2
            rows.append(h00 * A + h10 * dA * L + h01 * B - h11 * dB * L)
        else:
            rows.append((1 - t) * A + t * B)
    return grid_mesh(np.array(rows), False, False, False), ""


_BLEND = {"on": False, "last": None}
BLEND_COLORS = {"hover": (1.0, 0.85, 0.2, 1.0), "A": (1.0, 0.35, 0.25, 1.0), "B": (0.25, 0.8, 1.0, 1.0)}


def _blend_collect(context):
    """Bords utilisables de tous les objets visibles (surfaces : bords ouverts ; courbes : chemins)."""
    dg = context.evaluated_depsgraph_get()
    loops = []
    for ob in context.visible_objects:
        if ob.type not in {'MESH', 'CURVE'} or "dessin_cotation" in ob.keys():
            continue
        try:
            cands = _edge_candidates(ob, dg)
        except (RuntimeError, ReferenceError, ValueError, TypeError, AttributeError):
            continue
        for l in cands:
            if len(l['P']) >= 2:
                loops.append(dict(l, obj=ob.name))
        if len(loops) > 4000:
            break
    return loops


def _blend_run(loop, segs):
    """Plus longue suite continue de segments choisis. Retourne (points (n,3), sortants ou None)."""
    P = np.asarray(loop['P'], dtype=np.float64)
    n = len(P)
    closed = loop['closed']
    nseg = n if closed else n - 1
    keep = np.zeros(nseg, dtype=bool)
    for s in segs:
        if 0 <= s < nseg:
            keep[s] = True
    if not keep.any():
        return None
    if keep.all():
        order = list(range(nseg))
    elif closed:
        s0 = int(np.argmin(keep))
        order = [(s0 + 1 + k) % nseg for k in range(nseg)]
    else:
        order = list(range(nseg))
    best, cur = [], []
    for i in order:
        if keep[i]:
            cur.append(i)
        else:
            if len(cur) > len(best):
                best = cur
            cur = []
    if len(cur) > len(best):
        best = cur
    idx = [best[0]] + [(s + 1) % n for s in best]
    out = np.asarray(loop['out'], dtype=np.float64)[best] if loop['out'] is not None else None
    return P[idx], out


def blend_surface2(runA, runB, contA='TANGENT', contB='TANGENT', tenA=1.0, tenB=1.0, segments=24, rows_n=12):
    """Raccord entre deux bords, continuité réglable de chaque côté (position / tangence / courbure approchée)."""
    (PA, oA), (PB, oB) = runA, runB
    if path_length(PA, False) < 1e-9 or path_length(PB, False) < 1e-9:
        return None, "An edge is too short"
    if np.linalg.norm(PA[0] - PB[0]) + np.linalg.norm(PA[-1] - PB[-1]) > np.linalg.norm(PA[0] - PB[-1]) + np.linalg.norm(PA[-1] - PB[0]):
        PB = PB[::-1]
        oB = oB[::-1] if oB is not None else None
    n = int(max(segments, 8))
    A = resample_path(PA, n)
    B = resample_path(PB, n)
    chord = B - A
    gap = np.linalg.norm(chord, axis=1)
    if float(gap.max()) < 1e-9:
        return None, "The edges are already touching"
    unit = chord / np.maximum(gap, 1e-12)[:, None]
    if contA == 'POSITION' and contB == 'POSITION':
        ts = np.array([0.0, 1.0])
        return grid_mesh(np.array([(1 - t) * A + t * B for t in ts]), False, False, False), ""
    dA = _nearest_dir(A, PA, oA) if contA != 'POSITION' else np.zeros_like(A)
    dB = _nearest_dir(B, PB, oB) if contB != 'POSITION' else np.zeros_like(B)
    flipA = (dA * chord).sum(axis=1) < 0
    flipB = (dB * -chord).sum(axis=1) < 0
    dA[flipA] *= -1.0
    dB[flipB] *= -1.0
    badA = np.linalg.norm(dA, axis=1) < 1e-9          # côté sans direction (position, courbe) : on suit la corde
    badB = np.linalg.norm(dB, axis=1) < 1e-9
    dA[badA] = unit[badA]
    dB[badB] = -unit[badB]
    TA = dA * (gap * float(tenA))[:, None]
    TB = -dB * (gap * float(tenB))[:, None]            # sens de parcours à l'arrivée
    quintic = contA == 'CURVATURE' or contB == 'CURVATURE'
    rows = []
    for t in np.linspace(0.0, 1.0, int(max(rows_n, 2)) + 1):
        if quintic:
            H0 = 1 - 10 * t ** 3 + 15 * t ** 4 - 6 * t ** 5
            H1 = t - 6 * t ** 3 + 8 * t ** 4 - 3 * t ** 5
            H4 = -4 * t ** 3 + 7 * t ** 4 - 3 * t ** 5
            H5 = 10 * t ** 3 - 15 * t ** 4 + 6 * t ** 5
            rows.append(H0 * A + H1 * TA + H4 * TB + H5 * B)
        else:
            h00, h10, h01, h11 = 2 * t ** 3 - 3 * t ** 2 + 1, t ** 3 - 2 * t ** 2 + t, -2 * t ** 3 + 3 * t ** 2, t ** 3 - t ** 2
            rows.append(h00 * A + h10 * TA + h01 * B + h11 * TB)
    return grid_mesh(np.array(rows), False, False, False), ""


def blend_draw_cb(op):
    """Surligne l'arête survolée et les arêtes déjà choisies (1er bord, 2e bord)."""
    try:
        loops = op.loops
        layers = [("hover", op.hover_pts()), ("A", op.pick_pts(0)), ("B", op.pick_pts(1))]
    except (AttributeError, ReferenceError, RuntimeError):
        return
    shader = get_shader('3D')
    shader.bind()
    gpu.state.blend_set('ALPHA')
    gpu.state.depth_test_set('NONE')
    for key, pts in layers:
        if not pts:
            continue
        gpu.state.line_width_set(5.0 if key == "hover" else 4.0)
        shader.uniform_float("color", BLEND_COLORS[key])
        batch_for_shader(shader, 'LINES', {"pos": pts}).draw(shader)
    gpu.state.line_width_set(1.0)


class DESSIN_OT_blend_srf(_ProfileOp, bpy.types.Operator):
    bl_idname = "dessin.blend_srf"
    bl_label = "Blend Surface"
    bl_description = ("Creates a smooth surface between two edges, like Rhino: click the first edge (C: chain the connected edges), "
                      "Enter, click the second edge, Enter. Then adjust the continuity and tension of each side in the panel")
    bl_options = {'REGISTER', 'UNDO'}

    cont_a: bpy.props.EnumProperty(name="Continuity 1", default='TANGENT',
                                   items=(('POSITION', "Position", "The surface touches the first edge"),
                                          ('TANGENT', "Tangency", "Leaves the first surface along its own direction"),
                                          ('CURVATURE', "Curvature (approximate)", "Smoother start: tangency with a flat curvature profile")))
    cont_b: bpy.props.EnumProperty(name="Continuity 2", default='TANGENT',
                                   items=(('POSITION', "Position", "The surface touches the second edge"),
                                          ('TANGENT', "Tangency", "Reaches the second surface along its own direction"),
                                          ('CURVATURE', "Curvature (approximate)", "Smoother end: tangency with a flat curvature profile")))
    tension_a: bpy.props.FloatProperty(name="Tension 1", default=1.0, min=0.0, soft_max=3.0,
                                       description="Length of the tangent on the first side (1: the distance between the edges)")
    tension_b: bpy.props.FloatProperty(name="Tension 2", default=1.0, min=0.0, soft_max=3.0,
                                       description="Length of the tangent on the second side")
    lock: bpy.props.BoolProperty(name="Lock tensions", default=True, description="Tension 2 follows tension 1")
    segments: bpy.props.IntProperty(name="Segments", default=24, min=4, max=400)
    steps: bpy.props.IntProperty(name="Rows", default=12, min=2, max=100, description="Subdivisions across the blend")
    delete_input: bpy.props.BoolProperty(name="Delete input", default=False)

    # ---- sélection interactive des bords ----
    def invoke(self, context, event):
        if _BLEND["on"]:
            return {'CANCELLED', 'PASS_THROUGH'}
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS' and context.area is not None and cmd_click_idle(context, event):
            return {'CANCELLED'}
        region = find_window_region(context.area, event.mouse_x, event.mouse_y)
        if region is None and event.type == 'MOUSEMOVE':
            return {'CANCELLED', 'PASS_THROUGH'}
        self.area = context.area
        self.region = region or next((r for r in context.area.regions if r.type == 'WINDOW'), None)
        if self.region is None:
            return {'CANCELLED'}
        self.loops = _blend_collect(context)
        if not self.loops:
            self.report({'INFO'}, "No open edge found: blend needs surfaces with open edges or curves")
            return {'CANCELLED'}
        segA, segB, lid, sid = [], [], [], []
        for li, l in enumerate(self.loops):
            P = np.asarray(l['P'], dtype=np.float64)
            n = len(P)
            nseg = n if l['closed'] else n - 1
            segA.append(P[:nseg])
            segB.append(P[(np.arange(nseg) + 1) % n])
            lid.append(np.full(nseg, li))
            sid.append(np.arange(nseg))
        self.SA, self.SB = np.vstack(segA), np.vstack(segB)
        self.LID, self.SID = np.concatenate(lid), np.concatenate(sid)
        self.phase = 0
        self.picks = [None, None]
        self.chain = True
        self.hover = None
        self.mouse = (event.mouse_x - self.region.x, event.mouse_y - self.region.y)
        _BLEND["on"] = True
        self.handle = bpy.types.SpaceView3D.draw_handler_add(blend_draw_cb, (self,), 'WINDOW', 'POST_VIEW')
        context.window_manager.modal_handler_add(self)
        self.update_hover()
        if event.type == 'LEFTMOUSE':
            self.click(event)
        self.prompt()
        return {'RUNNING_MODAL'}

    def prompt(self):
        which = "first" if self.phase == 0 else "second"
        txt = (f"Blend Surface: select the {which} edge   [ChainEdges: {'Yes' if self.chain else 'No'} (C)  ·  Shift: add  ·  Ctrl/Cmd: remove  ·  "
               f"Enter: done  ·  Backspace: clear  ·  Esc: cancel]")
        set_prompt(self.area, txt)

    def end_modal(self, context):
        if getattr(self, "handle", None) is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self.handle, 'WINDOW')
            self.handle = None
        _BLEND["on"] = False
        set_prompt(self.area, "")
        try:
            self.area.tag_redraw()
        except (AttributeError, ReferenceError):
            pass

    def update_hover(self):
        self.hover = None
        rv3d = region_rv3d(self.region, self.area)
        if rv3d is None or not len(self.SA):
            return
        persp = np.array(rv3d.perspective_matrix, dtype=np.float64)
        ax, ay, oka = _project_region(self.SA, persp, self.region)
        bx, by, okb = _project_region(self.SB, persp, self.region)
        mx, my = self.mouse
        dx, dy = bx - ax, by - ay
        ll = np.maximum(dx * dx + dy * dy, 1e-12)
        t = np.clip(((mx - ax) * dx + (my - ay) * dy) / ll, 0.0, 1.0)
        d = np.hypot(ax + dx * t - mx, ay + dy * t - my)
        d = np.where(oka & okb, d, 1e9)
        k = int(d.argmin())
        if d[k] <= 14.0 * px_scale():
            self.hover = (int(self.LID[k]), int(self.SID[k]))

    def segs_of(self, li, si):
        l = self.loops[li]
        n = len(l['P'])
        nseg = n if l['closed'] else n - 1
        return set(range(nseg)) if self.chain else {si}

    def seg_points(self, li, segs):
        l = self.loops[li]
        P = np.asarray(l['P'], dtype=np.float64)
        n = len(P)
        pts = []
        for s in sorted(segs):
            pts.append(tuple(P[s]))
            pts.append(tuple(P[(s + 1) % n]))
        return pts

    def hover_pts(self):
        if self.hover is None:
            return []
        li, si = self.hover
        return self.seg_points(li, self.segs_of(li, si))

    def pick_pts(self, phase):
        p = self.picks[phase]
        return self.seg_points(p['li'], p['segs']) if p else []

    def click(self, event):
        mx, my = event.mouse_x - self.region.x, event.mouse_y - self.region.y
        self.mouse = (mx, my)
        self.update_hover()
        if self.hover is None:
            return
        li, si = self.hover
        segs = self.segs_of(li, si)
        cur = self.picks[self.phase]
        if cur is not None and cur['li'] == li and event.ctrl:
            cur['segs'] -= segs
            if not cur['segs']:
                self.picks[self.phase] = None
        elif cur is not None and cur['li'] == li and event.shift:
            cur['segs'] |= segs
        else:
            self.picks[self.phase] = {'li': li, 'segs': set(segs)}

    def modal(self, context, event):
        et, ev = event.type, event.value
        try:
            self.area.tag_redraw()
        except ReferenceError:
            self.end_modal(context)
            return {'CANCELLED'}
        if et == 'ESC' and ev == 'PRESS':
            self.end_modal(context)
            back_to_idle()
            return {'CANCELLED'}
        if et == 'MOUSEMOVE':
            self.mouse = (event.mouse_x - self.region.x, event.mouse_y - self.region.y)
            self.update_hover()
            return {'PASS_THROUGH'}
        if et == 'LEFTMOUSE' and ev == 'PRESS':
            if event.alt or event.oskey:
                return {'PASS_THROUGH'}
            if find_window_region(self.area, event.mouse_x, event.mouse_y) is None or cmd_hit(self.area, event.mouse_x, event.mouse_y) is not None:
                return {'PASS_THROUGH'}
            self.click(event)
            return {'RUNNING_MODAL'}
        if et == 'C' and ev == 'PRESS' and not (event.ctrl or event.alt or event.oskey):
            self.chain = not self.chain
            self.prompt()
            return {'RUNNING_MODAL'}
        if et == 'BACK_SPACE' and ev == 'PRESS':
            self.picks[self.phase] = None
            return {'RUNNING_MODAL'}
        if et in {'RET', 'NUMPAD_ENTER', 'SPACE'} and ev == 'PRESS':
            if self.picks[self.phase] is None:
                self.report({'INFO'}, "Click an edge first")
                return {'RUNNING_MODAL'}
            if self.phase == 0:
                self.phase = 1
                self.prompt()
                return {'RUNNING_MODAL'}
            runs = [_blend_run(self.loops[p['li']], p['segs']) for p in self.picks]
            names = [self.loops[p['li']]['obj'] for p in self.picks]
            if runs[0] is None or runs[1] is None:
                self.report({'WARNING'}, "No usable edge in the selection")
                return {'RUNNING_MODAL'}
            _BLEND["last"] = (runs[0], runs[1], names)
            self.end_modal(context)
            res = self.execute(context)
            if 'FINISHED' in res:
                idle_tool()
            return res
        return {'PASS_THROUGH'}

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, "cont_a", text="1")
        col.prop(self, "cont_b", text="2")
        col.prop(self, "lock")
        col.prop(self, "tension_a", text="Tension 1")
        sub = col.column()
        sub.enabled = not self.lock
        sub.prop(self, "tension_b", text="Tension 2")
        col.prop(self, "segments")
        col.prop(self, "steps")
        col.prop(self, "delete_input")

    def execute(self, context):
        last = _BLEND["last"]
        if last is None:
            self.report({'WARNING'}, "Pick the two edges first")
            return {'CANCELLED'}
        runA, runB, names = last
        tb = self.tension_a if self.lock else self.tension_b
        built, msg = blend_surface2(runA, runB, self.cont_a, self.cont_b, self.tension_a, tb, self.segments, self.steps)
        if built is None:
            self.report({'WARNING'}, msg)
            return {'CANCELLED'}
        V, F = built
        out = mesh_object_from_arrays(context, "Blend Surface", V, F, np.asarray(V).mean(axis=0), False)
        if self.delete_input:
            delete_objects([bpy.data.objects[n] for n in set(names) if n in bpy.data.objects])
        deselect_all_objects(context)
        out.select_set(True)
        context.view_layer.objects.active = out
        return {'FINISHED'}


def _closest_on_polyline(pt, P):
    """Point le plus proche de pt sur la polyligne P (n,3)."""
    a, b = P[:-1], P[1:]
    ab = b - a
    ll = np.maximum((ab * ab).sum(axis=1), 1e-24)
    t = np.clip(((pt - a) * ab).sum(axis=1) / ll, 0.0, 1.0)
    q = a + ab * t[:, None]
    return q[((q - pt) ** 2).sum(axis=1).argmin()]


class DESSIN_OT_match_srf(_ProfileOp, bpy.types.Operator):
    bl_idname = "dessin.match_srf"
    bl_label = "Match Surface"
    bl_description = ("Moves the edge of the first clicked surface onto the facing edge of the second one (optionally keeping "
                      "tangent continuity): click the surface to change, then the target, then Enter / Space")
    bl_options = {'REGISTER', 'UNDO'}

    continuity: bpy.props.EnumProperty(name="Continuity", default='POSITION',
                                       items=(('POSITION', "Position", "The edge touches the target edge"),
                                              ('TANGENT', "Tangent", "The next row of points also follows the target surface")))

    def invoke(self, context, event):
        objs = ordered_selection(context)
        if len(objs) != 2 or objs[0].type != 'MESH' or not len(objs[0].data.polygons):
            self.report({'INFO'}, "Click the surface to change, then the target surface (or curve), then Enter")
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self, width=280)

    def draw(self, context):
        self.layout.prop(self, "continuity", text="")

    def execute(self, context):
        objs = ordered_selection(context)
        if len(objs) != 2 or objs[0].type != 'MESH' or not len(objs[0].data.polygons):
            self.report({'WARNING'}, "Select the surface to change, then the target")
            return {'CANCELLED'}
        src, dst = objs
        dg = context.evaluated_depsgraph_get()
        loops = _surface_loops(src)
        cands = _edge_candidates(dst, dg)
        if not loops or not cands:
            self.report({'WARNING'}, "No open edge found")
            return {'CANCELLED'}
        allp = np.vstack([l['P'] for l in loops + cands])
        diag = float(np.linalg.norm(allp.max(axis=0) - allp.min(axis=0))) or 1.0
        step = diag / 250.0
        dd = [_densify(l['P'], l['closed'], step) for l in cands]
        best = None
        for i, l in enumerate(loops):
            A = _densify(l['P'], l['closed'], step)
            for j, B in enumerate(dd):
                d = float(np.sqrt(((A[::max(1, len(A) // 120), None, :] - B[None, ::max(1, len(B) // 120), :]) ** 2).sum(axis=2)).min())
                if best is None or d < best[0]:
                    best = (d, i, j)
        _d, i, j = best
        runA = _facing_run(loops[i], dd[j], step)
        runB = _facing_run(cands[j], _densify(loops[i]['P'], loops[i]['closed'], step), step)
        if runA is None or runB is None:
            self.report({'WARNING'}, "No facing edges found")
            return {'CANCELLED'}
        pos, _outA = runA
        ids = [loops[i]['ids'][k] for k in pos]
        PB, oB = cands[j]['P'][runB[0]], runB[1]
        me = src.data
        M = np.array(src.matrix_world, dtype=np.float64)
        Mi = np.linalg.inv(M)
        co = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get('co', co)
        co = co.reshape(-1, 3)
        world = co @ M[:3, :3].T + M[:3, 3]
        new = world.copy()
        moved = {}
        for vid in ids:
            q = _closest_on_polyline(world[vid], PB)
            moved[vid] = q
            new[vid] = q
        if self.continuity == 'TANGENT' and oB is not None:
            mids = (PB[:-1] + PB[1:]) * 0.5
            nbr = {}
            for e in me.edges:
                a, b = e.vertices
                if a in moved and b not in moved:
                    nbr.setdefault(b, []).append(a)
                elif b in moved and a not in moved:
                    nbr.setdefault(a, []).append(b)
            for v, srcs in nbr.items():
                s = srcs[0]
                q = moved[s]
                k = int(((mids - q) ** 2).sum(axis=1).argmin())
                direction = oB[k]                      # la surface cible se prolonge dans le sens sortant de son bord
                length = float(np.linalg.norm(world[v] - world[s]))
                if float(np.linalg.norm(direction)) > 1e-9:
                    new[v] = q + direction * length
        loc = new @ Mi[:3, :3].T + Mi[:3, 3]
        me.vertices.foreach_set('co', loc.ravel())
        me.update()
        self.report({'INFO'}, f"{len(ids)} point(s) matched")
        return {'FINISHED'}


def rail_revolve(profile, pclosed, rail, origin, axis, cap=True, steps=96):
    """Révolution du profil autour de l'axe, guidée par le rail : le rayon (et la hauteur) du profil suivent ceux du rail.
    Retourne ((V, F), message)."""
    a = np.asarray(axis, dtype=np.float64)
    a = a / np.linalg.norm(a)
    helper = np.array([1.0, 0.0, 0.0]) if abs(a[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    e1 = np.cross(a, helper)
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(a, e1)
    o = np.asarray(origin, dtype=np.float64)

    def cyl(P):
        rel = np.asarray(P, dtype=np.float64) - o
        return np.hypot(rel @ e1, rel @ e2), np.arctan2(rel @ e2, rel @ e1), rel @ a

    rr, rphi, rh = cyl(rail)
    rphi = np.unwrap(rphi)
    if len(rphi) < 2 or abs(rphi[-1] - rphi[0]) < math.radians(1.0):
        return None, "The rail must go around the axis"
    if rphi[-1] < rphi[0]:
        rr, rphi, rh = rr[::-1], rphi[::-1], rh[::-1]
    dphi = np.diff(rphi)
    if (dphi < -1e-6).any():
        return None, "The rail must go around the axis in a single direction"
    keep = np.concatenate([[True], dphi > 1e-9])
    rr, rphi, rh = rr[keep], rphi[keep], rh[keep]
    span = float(rphi[-1] - rphi[0])
    full = span >= 2 * math.pi * 0.995
    if span > 2 * math.pi:
        span = 2 * math.pi
    if rr[0] < 1e-9:
        return None, "The rail starts on the axis"
    pr, pphi, ph = cyl(profile)
    pphi = np.unwrap(pphi)
    pphi = pphi - pphi[0]
    n_rows = int(max(steps, 8))
    phis = rphi[0] + np.linspace(0.0, span, n_rows + 1)
    if full:
        phis = phis[:-1]
    rows = []
    for ph_i in phis:
        k = float(np.interp(ph_i, rphi, rr)) / float(rr[0])
        dh = float(np.interp(ph_i, rphi, rh)) - float(rh[0])
        ang = pphi + (ph_i - rphi[0]) + math.atan2(float((np.asarray(profile[0]) - o) @ e2), float((np.asarray(profile[0]) - o) @ e1))
        rows.append(o + (pr * k * np.cos(ang))[:, None] * e1 + (pr * k * np.sin(ang))[:, None] * e2 + (ph + dh)[:, None] * a)
    return grid_mesh(np.array(rows), bool(pclosed), bool(full), bool(cap and not full)), ""


class DESSIN_OT_rail_revolve(_ProfileOp, bpy.types.Operator):
    bl_idname = "dessin.rail_revolve"
    bl_label = "Rail Revolve"
    bl_description = ("Revolves a profile around an axis while a rail curve controls the radius: click the profile, then the rail "
                      "(then optionally a straight line for the axis), then Enter / Space")
    bl_options = {'REGISTER', 'UNDO'}

    axis: bpy.props.EnumProperty(name="Axis", default='Z',
                                 items=(('Z', "Z axis", "Vertical axis through the centre of the rail"),
                                        ('X', "X axis", "Axis along X through the centre of the rail"),
                                        ('Y', "Y axis", "Axis along Y through the centre of the rail"),
                                        ('LINE', "Third curve", "A straight third curve gives the axis")))
    steps: bpy.props.IntProperty(name="Segments", default=96, min=8, max=720)
    cap: bpy.props.BoolProperty(name="Cap ends", default=True)
    delete_input: bpy.props.BoolProperty(name="Delete input", default=False)

    def invoke(self, context, event):
        objs, profs = self.profiles(context)
        if len(profs) < 2:
            self.report({'INFO'}, "Click the profile, then the rail (then an axis line), then Enter")
            return {'CANCELLED'}
        self.axis = 'LINE' if len(profs) >= 3 else ('Z' if self.axis == 'LINE' else self.axis)
        return context.window_manager.invoke_props_dialog(self, width=300)

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, "axis", text="")
        col.prop(self, "steps")
        col.prop(self, "cap")
        col.prop(self, "delete_input")

    def execute(self, context):
        objs, profs = self.profiles(context)
        if len(profs) < 2:
            self.report({'WARNING'}, "Select the profile and the rail")
            return {'CANCELLED'}
        profile, pclosed = profs[0][0], bool(profs[0][1])
        rail = profs[1][0]
        if self.axis == 'LINE' and len(profs) >= 3:
            ax = profs[2][0]
            axis = ax[-1] - ax[0]
            if float(np.linalg.norm(axis)) < 1e-9:
                self.report({'WARNING'}, "The axis line is too short")
                return {'CANCELLED'}
            origin = ax[0]
        else:
            axis = np.array({'X': (1.0, 0.0, 0.0), 'Y': (0.0, 1.0, 0.0)}.get(self.axis, (0.0, 0.0, 1.0)))
            c = (np.asarray(rail).min(axis=0) + np.asarray(rail).max(axis=0)) * 0.5
            origin = c - axis * float(c.dot(axis))
        built, msg = rail_revolve(profile, pclosed, rail, origin, axis, self.cap, self.steps)
        if built is None:
            self.report({'WARNING'}, msg)
            return {'CANCELLED'}
        V, F = built
        out = mesh_object_from_arrays(context, "Rail Revolve", V, F, np.asarray(origin), True)
        if self.delete_input:
            delete_objects(objs)
        deselect_all_objects(context)
        out.select_set(True)
        context.view_layer.objects.active = out
        return {'FINISHED'}


class DESSIN_OT_shell(_ProfileOp, bpy.types.Operator):
    bl_idname = "dessin.shell"
    bl_label = "Shell"
    bl_description = ("Hollows out solids, keeping a wall thickness: click the solids (or select them first), Enter / Space, then the "
                      "thickness and the face(s) to remove")
    bl_options = {'REGISTER', 'UNDO'}

    thickness: bpy.props.FloatProperty(name="Wall thickness", default=0.02, min=1e-6, subtype='DISTANCE', unit='LENGTH')
    side: bpy.props.EnumProperty(name="Wall", default='INSIDE',
                                 items=(('INSIDE', "Inside", "The outer shape stays the same"),
                                        ('OUTSIDE', "Outside", "The inner shape stays the same")))
    open_face: bpy.props.EnumProperty(name="Open face", default='TOP',
                                      items=(('NONE', "None (closed cavity)", "Hollow without any opening"),
                                             ('TOP', "Top", "Removes the top face"),
                                             ('BOTTOM', "Bottom", "Removes the bottom face"),
                                             ('LARGEST', "Largest face", "Removes the face with the largest area"),
                                             ('SELECTED', "Selected faces", "Removes the faces selected in Edit Mode")))
    delete_input: bpy.props.BoolProperty(name="Delete input", default=True)

    def invoke(self, context, event):
        if not [o for o in context.selected_objects if o.type == 'MESH' and len(o.data.polygons)]:
            self.report({'INFO'}, "Click the solids to hollow out, then Enter")
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self, width=300)

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, "thickness")
        col.prop(self, "side", expand=True)
        col.prop(self, "open_face", text="")
        col.prop(self, "delete_input")

    def execute(self, context):
        targets = [o for o in context.selected_objects if o.type == 'MESH' and len(o.data.polygons)]
        if not targets:
            self.report({'INFO'}, "Click the solids to hollow out, then Enter")
            return {'CANCELLED'}
        made = []
        for obj in targets:
            me = shell_mesh(obj, self.thickness, self.side == 'INSIDE', self.open_face)
            new = bpy.data.objects.new("Shell " + obj.name, me)
            new.matrix_world = obj.matrix_world.copy()
            for c in (obj.users_collection or [context.scene.collection]):
                c.objects.link(new)
            made.append(new)
        if self.delete_input:
            delete_objects(targets)
        deselect_all_objects(context)
        for ob in made:
            ob.select_set(True)
        context.view_layer.objects.active = made[-1]
        return {'FINISHED'}


def shell_mesh(obj, thickness, inside, open_face):
    """Maillage évidé : retire la ou les faces d'ouverture puis donne une épaisseur de paroi."""
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    closed_solid = all(len(e.link_faces) == 2 for e in bm.edges)
    if closed_solid:
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    sx = obj.matrix_world.to_3x3()
    remove = []
    if open_face == 'SELECTED':
        remove = [f for f in bm.faces if me.polygons[f.index].select]
    elif open_face in ('TOP', 'BOTTOM'):
        sign = 1.0 if open_face == 'TOP' else -1.0
        cand = []
        for f in bm.faces:
            nw = (sx @ f.normal).normalized()
            if nw.z * sign > 0.9:
                cand.append((f, (obj.matrix_world @ f.calc_center_median()).z * sign))
        if cand:
            best = max(z for _f, z in cand)
            tol = 1e-4 * max(1.0, abs(best))
            remove = [f for f, z in cand if z >= best - tol]
    elif open_face == 'LARGEST':
        remove = [max(bm.faces, key=lambda f: f.calc_area())]
    if remove:
        bmesh.ops.delete(bm, geom=remove, context='FACES_ONLY')
        bm.faces.ensure_lookup_table()
        loose = [e for e in bm.edges if not e.link_faces]
        if loose:
            bmesh.ops.delete(bm, geom=loose, context='EDGES')
        loose_v = [v for v in bm.verts if not v.link_edges]
        if loose_v:
            bmesh.ops.delete(bm, geom=loose_v, context='VERTS')
    t = abs(thickness) if inside else -abs(thickness)
    bmesh.ops.solidify(bm, geom=list(bm.faces), thickness=t)
    out = bpy.data.meshes.new("Shell " + me.name)
    bm.to_mesh(out)
    bm.free()
    for m in me.materials:
        out.materials.append(m)
    return out


def object_bounds(obj):
    """(min, max) de la boîte englobante de l'objet, en coordonnées monde."""
    mw = obj.matrix_world
    pts = np.array([tuple(mw @ Vector(c)) for c in obj.bound_box])
    return pts.min(axis=0), pts.max(axis=0)


_ALIGN_ITEMS = lambda a, b, c: (('NONE', "None", "Do not move along this axis"),
                                ('MIN', a, ""), ('CENTER', b, ""), ('MAX', c, ""))


class DESSIN_OT_align(_ProfileOp, bpy.types.Operator):
    bl_idname = "dessin.align"
    bl_label = "Align"
    bl_description = ("Aligns the selected objects along their bounding boxes (left / center / right, front / center / back, "
                      "bottom / center / top) on the selection, the last clicked object or the world origin")
    bl_options = {'REGISTER', 'UNDO'}

    x_mode: bpy.props.EnumProperty(name="X", default='NONE', items=_ALIGN_ITEMS("Left", "Center", "Right"))
    y_mode: bpy.props.EnumProperty(name="Y", default='NONE', items=_ALIGN_ITEMS("Front", "Center", "Back"))
    z_mode: bpy.props.EnumProperty(name="Z", default='NONE', items=_ALIGN_ITEMS("Bottom", "Center", "Top"))
    reference: bpy.props.EnumProperty(name="Align to", default='SELECTION',
                                      items=(('SELECTION', "Selection", "Bounding box of all the selected objects"),
                                             ('ACTIVE', "Last clicked object", "The last clicked object stays in place"),
                                             ('WORLD', "World origin", "Align on the world axes")))

    def invoke(self, context, event):
        if not context.selected_objects:
            self.report({'INFO'}, "Click the objects to align, then Enter")
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self, width=320)

    def draw(self, context):
        col = self.layout.column()
        col.label(text="Align along:")
        for prop in ("x_mode", "y_mode", "z_mode"):
            row = col.row()
            row.prop(self, prop, expand=True)
        col.separator()
        col.prop(self, "reference")

    def execute(self, context):
        objs = [o for o in context.selected_objects]
        modes = (self.x_mode, self.y_mode, self.z_mode)
        if not objs or all(m == 'NONE' for m in modes):
            self.report({'INFO'}, "Choose at least one alignment")
            return {'CANCELLED'}
        bounds = {o.name: object_bounds(o) for o in objs}
        if self.reference == 'SELECTION':
            lo = np.min([b[0] for b in bounds.values()], axis=0)
            hi = np.max([b[1] for b in bounds.values()], axis=0)
        elif self.reference == 'ACTIVE':
            act = context.view_layer.objects.active
            if act is None or act.name not in bounds:
                act = objs[-1]
            lo, hi = bounds[act.name]
            objs = [o for o in objs if o is not act]
        else:
            lo = hi = np.zeros(3)
        ref = {'MIN': lo, 'CENTER': (lo + hi) * 0.5, 'MAX': hi}
        moved = 0
        for o in objs:
            b0, b1 = bounds[o.name]
            mine = {'MIN': b0, 'CENTER': (b0 + b1) * 0.5, 'MAX': b1}
            delta = Vector((0.0, 0.0, 0.0))
            for k, m in enumerate(modes):
                if m != 'NONE':
                    delta[k] = float(ref[m][k] - mine[m][k])
            if delta.length > 1e-12:
                mw = o.matrix_world.copy()
                mw.translation += delta
                o.matrix_world = mw
                moved += 1
        self.report({'INFO'}, f"Aligned {moved} object(s)")
        return {'FINISHED'}


def _late_imports():
    """Noms définis dans des modules chargés après celui-ci : ils ne servent qu'à l'exécution des outils."""
    global cmd_click_idle, cmd_hit, cmd_log, set_prompt
    from .cplane import cmd_log, set_prompt
    from .command_line import cmd_click_idle, cmd_hit
