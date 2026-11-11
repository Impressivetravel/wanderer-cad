"""Wanderer CAD : ShowEdges, Join, Explode, choix d'objets."""

import bmesh
import bpy
import gpu
import math
import numpy as np
import time
import types
from bpy_extras.view3d_utils import region_2d_to_origin_3d, region_2d_to_vector_3d
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

from .core import _redraw_all_areas, addon_globals, pref
from .drawing import _HOVER, find_window_region, get_shader, px_scale, region_rv3d
from .base import DessinBase
from .selection import _project_region, draw_box_cb, draw_fence_cb, objects_screen_bounds
from .offset_extrude import back_to_idle
from .trim import (
    circle_hints, is_xline, surface_trim, trim_mesh_cut_fn, trim_mesh_cutters, trim_wire, wire_graph, wire_paths,
    write_wire,
)


# --------------------------------------------------------------------------
# ShowEdges (comme Rhino) : arêtes nues (bord libre, une seule face) et non-manifold (plus de deux faces) surlignées
# --------------------------------------------------------------------------

_SHOWEDGES = {"handle": None, "on": False, "mode": 'NAKED', "objs": None, "key": None, "naked": None, "nonman": None,
              "alle": None, "counts": (0, 0, 0)}
SHOWEDGES_NAKED = (1.0, 0.0, 1.0, 1.0)        # magenta, comme les arêtes nues de Rhino
SHOWEDGES_NONMAN = (1.0, 0.55, 0.0, 1.0)      # orange : arêtes partagées par plus de deux faces
SHOWEDGES_ALL = (0.2, 0.75, 1.0, 1.0)


def showedges_targets(context):
    """Objets analysés : maillages à faces visibles (la sélection mémorisée, sinon tous)."""
    names = _SHOWEDGES["objs"]
    out = []
    for o in context.view_layer.objects:
        try:
            if o.type != 'MESH' or not o.visible_get():
                continue
        except (RuntimeError, ReferenceError):
            continue
        if names is not None and o.name not in names:
            continue
        out.append(o)
    return out


def showedges_collect(context):
    """(segments nus, segments non-manifold, toutes les arêtes, (nb nus, nb non-manifold, nb objets avec arêtes nues))."""
    dg = context.evaluated_depsgraph_get()
    naked, nonman, alle = [], [], []
    n_naked = n_nm = n_obj = 0
    edit = context.mode == 'EDIT_MESH'
    for o in showedges_targets(context):
        if edit and o.mode == 'EDIT':
            try:
                o.update_from_editmode()
            except (RuntimeError, AttributeError):
                pass
        try:
            ev = o.evaluated_get(dg)
            me = ev.to_mesh()
        except (RuntimeError, ReferenceError):
            continue
        if me is None:
            continue
        try:
            nv, ne, nl = len(me.vertices), len(me.edges), len(me.loops)
            if not nv or not ne or not len(me.polygons):
                continue          # courbe / contour sans face : pas d'arêtes de surface (comme Rhino)
            co = np.empty(nv * 3, dtype=np.float32)
            me.vertices.foreach_get('co', co)
            ev_ = np.empty(ne * 2, dtype=np.int32)
            me.edges.foreach_get('vertices', ev_)
            le = np.empty(nl, dtype=np.int32)
            me.loops.foreach_get('edge_index', le)
        finally:
            ev.to_mesh_clear()
        mw = np.array(o.matrix_world, dtype=np.float64)
        W = co.reshape(-1, 3).astype(np.float64) @ mw[:3, :3].T + mw[:3, 3]
        E = ev_.reshape(-1, 2)
        use = np.bincount(le, minlength=ne)
        nk = E[use == 1]
        nm = E[use > 2]
        if len(nk):
            n_obj += 1
        n_naked += len(nk)
        n_nm += len(nm)
        if len(nk):
            naked.append(W[nk.reshape(-1)])
        if len(nm):
            nonman.append(W[nm.reshape(-1)])
        if _SHOWEDGES["mode"] == 'ALL':
            alle.append(W[E[use > 0].reshape(-1)])
    cat = (lambda L: np.vstack(L).astype(np.float32) if L else None)
    return cat(naked), cat(nonman), cat(alle), (n_naked, n_nm, n_obj)


def _showedges_refresh(context):
    key = (_HOVER["version"], context.mode, _SHOWEDGES["mode"], _SHOWEDGES["objs"])
    if _SHOWEDGES["key"] == key:
        return
    _SHOWEDGES["key"] = key
    _SHOWEDGES["naked"], _SHOWEDGES["nonman"], _SHOWEDGES["alle"], _SHOWEDGES["counts"] = showedges_collect(context)


def _draw_segments(pts, color, width):
    if pts is None or not len(pts):
        return
    try:
        sh = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')       # trait épais aussi sur Mac (Metal)
        sh.bind()
        sh.uniform_float("viewportSize", gpu.state.viewport_get()[2:])
        sh.uniform_float("lineWidth", width)
        sh.uniform_float("color", color)
    except (ValueError, AttributeError, TypeError, SystemError):
        sh = get_shader('3D')
        sh.bind()
        sh.uniform_float("color", color)
        gpu.state.line_width_set(width)
    batch_for_shader(sh, 'LINES', {"pos": pts}).draw(sh)
    gpu.state.line_width_set(1.0)


def showedges_cb():
    if not _SHOWEDGES["on"]:
        return
    try:
        ctx = bpy.context
        if ctx.mode not in {'OBJECT', 'EDIT_MESH'}:
            return
        _showedges_refresh(ctx)
        gpu.state.blend_set('ALPHA')
        gpu.state.depth_test_set('NONE')          # visibles même derrière les faces, comme dans Rhino
        w = 3.0 * px_scale(0.5)
        if _SHOWEDGES["mode"] == 'ALL':
            _draw_segments(_SHOWEDGES["alle"], SHOWEDGES_ALL, 1.5 * px_scale(0.5))
        if _SHOWEDGES["mode"] in {'NAKED', 'ALL'}:
            _draw_segments(_SHOWEDGES["naked"], SHOWEDGES_NAKED, w)
        _draw_segments(_SHOWEDGES["nonman"], SHOWEDGES_NONMAN, w)
        gpu.state.blend_set('NONE')
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
        pass


class DESSIN_OT_show_edges(bpy.types.Operator):
    bl_idname = "dessin.show_edges"
    bl_label = "Show Edges"
    bl_description = ("Like ShowEdges: highlights the naked edges (open borders, magenta) and the non-manifold edges (orange) "
                      "of the selected surfaces and solids (nothing selected: all of them). Run it again to hide them")
    bl_options = {'REGISTER'}

    mode: bpy.props.EnumProperty(name="Edges", items=(('NAKED', "Naked edges", "Open borders: edges used by a single face"),
                                                     ('NONMANIFOLD', "Non-manifold edges", "Edges shared by more than two faces"),
                                                     ('ALL', "All edges", "Every edge, naked ones in magenta")),
                                 default='NAKED', options={'SKIP_SAVE'})
    off: bpy.props.BoolProperty(default=False, options={'SKIP_SAVE', 'HIDDEN'})

    def execute(self, context):
        sel = [o.name for o in context.selected_objects if o.type == 'MESH']
        objs = tuple(sel) if sel else None
        same = _SHOWEDGES["on"] and _SHOWEDGES["mode"] == self.mode and (objs is None or objs == _SHOWEDGES["objs"])
        if self.off or same:       # relancée sans nouvelle sélection : on masque (une autre sélection : on l'analyse)
            _SHOWEDGES["on"] = False
            _SHOWEDGES["key"] = None
            _redraw_all_areas()
            cmd_log("Show Edges: off")
            self.report({'INFO'}, "Show Edges: off")
            return {'FINISHED'}
        _SHOWEDGES["objs"] = objs
        _SHOWEDGES["mode"] = self.mode
        _SHOWEDGES["on"] = True
        _SHOWEDGES["key"] = None
        _showedges_refresh(context)
        n_naked, n_nm, n_obj = _SHOWEDGES["counts"]
        if n_naked == 0 and n_nm == 0:
            msg = "Show Edges: no naked edge (closed solids)" if self.mode != 'NONMANIFOLD' else "Show Edges: no non-manifold edge"
        else:
            parts = []
            if self.mode != 'NONMANIFOLD':
                parts.append(f"{n_naked} naked edge(s) on {n_obj} object(s)")
            if n_nm:
                parts.append(f"{n_nm} non-manifold edge(s)")
            msg = "Show Edges: " + ", ".join(parts)
        msg += "   (ShowEdges again to hide)"
        _redraw_all_areas()
        cmd_log(msg)
        self.report({'INFO'}, msg)
        return {'FINISHED'}


class DESSIN_OT_trim(bpy.types.Operator):
    bl_idname = "dessin.trim"
    bl_label = "Trim"
    bl_description = ("Trims curves, outlines and surfaces like Trim: the selected objects are the cutters - curves, outlines or solid / surface meshes (nothing selected: all curves); "
                      "click the part to remove: of a curve (between two intersections) or of a surface (the outline is projected along the view); "
                      "drag a box to remove every part it touches")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and context.area is not None and context.area.type == 'VIEW_3D'

    def invoke(self, context, event):
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS' and context.area is not None and cmd_click_idle(context, event):
            return {'CANCELLED'}
        region = find_window_region(context.area, event.mouse_x, event.mouse_y)
        if region is None:
            return {'CANCELLED', 'PASS_THROUGH'}
        if event.type != 'LEFTMOUSE' or event.value != 'PRESS':
            return self.click(context, event)
        # clic simple = Trim d'une portion ; glisser = cadre de sélection (fenêtre / capture) qui retire toutes les portions touchées
        self.area = context.area
        self.region = region
        self.start = (event.mouse_x - region.x, event.mouse_y - region.y)
        self.press_ev = types.SimpleNamespace(mouse_x=event.mouse_x, mouse_y=event.mouse_y)
        self.box = None
        try:
            self.fence = context.scene.dessin.trim_mode == 'FENCE'
        except (AttributeError, ReferenceError):
            self.fence = True
        self.handle = bpy.types.SpaceView3D.draw_handler_add(draw_fence_cb if self.fence else draw_box_cb, (self,), 'WINDOW', 'POST_PIXEL')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def end_modal(self):
        if getattr(self, "handle", None) is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self.handle, 'WINDOW')
            self.handle = None
        try:
            self.area.tag_redraw()
        except (AttributeError, ReferenceError):
            pass

    def modal(self, context, event):
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self.end_modal()
            return {'CANCELLED'}
        if event.type == 'MOUSEMOVE':
            x, y = event.mouse_x - self.region.x, event.mouse_y - self.region.y
            thr = 6.0 * px_scale()
            if self.box is not None or abs(x - self.start[0]) > thr or abs(y - self.start[1]) > thr:
                self.box = (self.start[0], self.start[1], x, y)
                self.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            box, ev = self.box, self.press_ev
            self.end_modal()
            if box is None:
                return self.click(context, ev)
            if getattr(self, "fence", False):
                return self.fence_trim(context, box)
            return self.box_trim(context, box)
        return {'RUNNING_MODAL'}

    def graphs_now(self, context):
        dg = context.evaluated_depsgraph_get()
        graphs = {}
        for obj in context.visible_objects:
            g = wire_graph(obj, dg)
            if g is not None and g[1]:
                graphs[obj] = g
        return dg, graphs

    def trim_edge(self, context, dg, graphs, target, e0, tcl):
        """Retire la portion de target portant l'arête e0 (paramètre tcl). Retourne True si quelque chose a été coupé, sinon un message (str) ou None."""
        mesh_objs = trim_mesh_cutters(context)
        cutter_objs = [o for o in context.selected_objects if o in graphs] or ([] if mesh_objs else list(graphs))
        Q0, Q1, QA, QB = [], [], [], []
        extent = 0.0
        all_ext = 0.0
        for o in cutter_objs:
            verts, edges = graphs[o]
            V = np.array([tuple(v) for v in verts], dtype=np.float64)
            E = np.array(edges, dtype=np.int64)
            Q0.append(V[E[:, 0]])
            Q1.append(V[E[:, 1]])
            if o is target:
                QA.append(E[:, 0])
                QB.append(E[:, 1])
            else:
                QA.append(np.full(len(E), -1))
                QB.append(np.full(len(E), -1))
            ext_o = float(np.linalg.norm(V.max(axis=0) - V.min(axis=0)))
            all_ext = max(all_ext, ext_o)
            if not is_xline(o):
                extent = max(extent, ext_o)
        verts, edges = graphs[target]
        V = np.array([tuple(v) for v in verts], dtype=np.float64)
        ext_t = float(np.linalg.norm(V.max(axis=0) - V.min(axis=0)))
        all_ext = max(all_ext, ext_t)
        if not is_xline(target):
            extent = max(extent, ext_t)
        if extent <= 0.0:
            extent = all_ext         # seulement des lignes de construction : on n'a pas mieux
        tol = max(1e-6, 1e-4 * extent)
        if Q0:
            cutters = (np.vstack(Q0), np.vstack(Q1), np.concatenate(QA), np.concatenate(QB))
        else:
            cutters = (np.zeros((0, 3)), np.zeros((0, 3)), np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64))
        res = trim_wire(verts, edges, e0, tcl, cutters, True, tol, trim_mesh_cut_fn(mesh_objs, dg, tol))
        if isinstance(res, str) or res is None:
            return res
        hints = circle_hints(target)
        write_wire(target, res[0], res[1], hints=hints)
        return True

    def multi_trim(self, context, hits_fn, what):
        """Retire, une à une, toutes les portions de courbes désignées par hits_fn(ax, ay, bx, by) -> (vivants, paramètre milieu)
        (les arêtes changent après chaque coupe)."""
        region = self.region
        rv3d = region_rv3d(region, self.area)
        failed = set()
        done = 0
        t_end = time.monotonic() + 8.0
        while done < 400 and time.monotonic() < t_end:
            dg, graphs = self.graphs_now(context)
            persp = np.array(rv3d.perspective_matrix, dtype=np.float64)
            cand = []
            for obj, (verts, edges) in graphs.items():
                if obj.hide_select:         # objet verrouillé : il peut servir de limite de coupe, pas être coupé
                    continue
                V = np.array([tuple(v) for v in verts], dtype=np.float64)
                E = np.array(edges, dtype=np.int64)
                sx, sy, ok = _project_region(V, persp, region)
                ax, ay, bx, by = sx[E[:, 0]], sy[E[:, 0]], sx[E[:, 1]], sy[E[:, 1]]
                good = ok[E[:, 0]] & ok[E[:, 1]]
                alive, tmid = hits_fn(ax, ay, bx, by)
                alive &= good
                for k in np.nonzero(alive)[0]:
                    tm = float(tmid[k])
                    mid = tuple(np.round(V[E[k, 0]] + (V[E[k, 1]] - V[E[k, 0]]) * tm, 4))
                    key = (obj.name, mid)
                    if key not in failed:
                        cand.append((obj, int(k), tm, key))
            hit = False
            for obj, k, tm, key in cand:
                try:
                    res = self.trim_edge(context, dg, graphs, obj, k, tm)
                except (RuntimeError, ReferenceError, ValueError):
                    res = None
                if res is True:
                    done += 1
                    hit = True
                    context.view_layer.update()
                    break
                failed.add(key)
            if not hit:
                break
        if not done:
            self.report({'INFO'}, f"Nothing to trim {what} (the parts must cross a cutting curve)")
            return {'CANCELLED'}
        self.report({'INFO'}, f"Trimmed {done} part(s)")
        return {'FINISHED'}

    def box_trim(self, context, box):
        """Cadre (Crossing) : toutes les portions de courbes touchées par le cadre sont retirées."""
        x0, x1 = sorted((box[0], box[2]))
        y0, y1 = sorted((box[1], box[3]))

        def hits(ax, ay, bx, by):
            # Liang-Barsky : part du segment à l'intérieur du cadre
            dx, dy = bx - ax, by - ay
            t0 = np.zeros(len(ax))
            t1 = np.ones(len(ax))
            alive = np.ones(len(ax), dtype=bool)
            for pp, qq in ((-dx, ax - x0), (dx, x1 - ax), (-dy, ay - y0), (dy, y1 - ay)):
                par = np.abs(pp) < 1e-12
                alive &= ~(par & (qq < 0))
                with np.errstate(divide='ignore', invalid='ignore'):
                    r = np.where(par, 0.0, qq / np.where(par, 1.0, pp))
                neg, pos = (pp < 0) & ~par, (pp > 0) & ~par
                t0 = np.where(neg, np.maximum(t0, r), t0)
                t1 = np.where(pos, np.minimum(t1, r), t1)
            alive &= t0 <= t1
            return alive, (t0 + t1) * 0.5
        return self.multi_trim(context, hits, "in the box")

    def fence_trim(self, context, line):
        """Ligne de coupe (Fence) : toutes les portions de courbes que la ligne traverse sont retirées."""
        fx0, fy0, fx1, fy1 = line
        fdx, fdy = fx1 - fx0, fy1 - fy0

        def hits(ax, ay, bx, by):
            dx, dy = bx - ax, by - ay
            den = dx * fdy - dy * fdx
            par = np.abs(den) < 1e-12
            with np.errstate(divide='ignore', invalid='ignore'):
                u = np.where(par, 0.0, ((fx0 - ax) * fdy - (fy0 - ay) * fdx) / np.where(par, 1.0, den))     # sur l'arête
                v = np.where(par, 0.0, ((fx0 - ax) * dy - (fy0 - ay) * dx) / np.where(par, 1.0, den))       # sur la ligne de coupe
            alive = ~par & (u >= 0.0) & (u <= 1.0) & (v >= 0.0) & (v <= 1.0)
            return alive, np.clip(u, 0.0, 1.0)
        return self.multi_trim(context, hits, "along the fence")

    def click(self, context, event):
        region = find_window_region(context.area, event.mouse_x, event.mouse_y)
        if region is None:
            return {'CANCELLED'}
        rv3d = context.area.spaces.active.region_3d
        dg = context.evaluated_depsgraph_get()
        persp = np.array(rv3d.perspective_matrix, dtype=np.float64)
        mx, my = event.mouse_x - region.x, event.mouse_y - region.y
        graphs = {}
        # gros fichiers : seuls les objets dont la boîte écran touche le curseur (puis la cible) sont analysés
        vis = list(context.visible_objects)
        bo, xmn, xmx, ymn, ymx, _sure = objects_screen_bounds(vis, persp, region)
        self._trim_bounds = (bo, xmn, xmx, ymn, ymx)

        def fill(mask):
            for i in np.nonzero(mask)[0]:
                obj = bo[int(i)]
                if obj in graphs or obj in self._no_graph:
                    continue
                g = wire_graph(obj, dg)
                if g is not None and g[1]:
                    graphs[obj] = g
                else:
                    self._no_graph.add(obj)
        self._no_graph = set()
        self._fill = fill
        best_d = 14.0 * px_scale()
        r_ = best_d + 2.0
        fill((xmx >= mx - r_) & (xmn <= mx + r_) & (ymx >= my - r_) & (ymn <= my + r_))
        # arête cliquée : la plus proche du curseur à l'écran
        best = None
        for obj, (verts, edges) in list(graphs.items()):
            if obj.hide_select:             # objet verrouillé : jamais coupé (mais il reste une limite de coupe)
                continue
            V = np.array([tuple(v) for v in verts], dtype=np.float64)
            E = np.array(edges, dtype=np.int64)
            sx, sy, ok = _project_region(V, persp, region)
            ax, ay, bx, by = sx[E[:, 0]], sy[E[:, 0]], sx[E[:, 1]], sy[E[:, 1]]
            dx, dy = bx - ax, by - ay
            l2 = dx * dx + dy * dy
            t = np.clip(((mx - ax) * dx + (my - ay) * dy) / np.where(l2 > 1e-12, l2, 1.0), 0.0, 1.0)
            dist = np.hypot(ax + t * dx - mx, ay + t * dy - my)
            dist[~(ok[E[:, 0]] & ok[E[:, 1]])] = np.inf
            k = int(np.argmin(dist))
            if dist[k] < best_d:
                best, best_d = (obj, k, float(t[k])), float(dist[k])
        if best is None:
            return self.try_surface(context, event, region, rv3d, graphs, "Click the part of a curve or of a surface to trim")
        target, e0, tcl = best
        self.fill_overlapping(graphs, target)        # les coupants possibles : objets qui recouvrent la cible à l'écran
        res = self.trim_edge(context, dg, graphs, target, e0, tcl)
        if res is not True:
            return self.try_surface(context, event, region, rv3d, graphs, res or "Nothing to trim")
        return {'FINISHED'}

    def fill_overlapping(self, graphs, target):
        """Ajoute aux graphes les objets dont la boîte écran recouvre celle de la cible (sans cible connue : tous)."""
        tb = getattr(self, "_trim_bounds", None)
        fill = getattr(self, "_fill", None)
        if tb is None or fill is None:
            return
        bo, xmn, xmx, ymn, ymx = tb
        try:
            i = bo.index(target)
        except ValueError:
            fill(np.ones(len(bo), dtype=bool))
            return
        if not (np.isfinite(xmn[i]) and np.isfinite(xmx[i]) and np.isfinite(ymn[i]) and np.isfinite(ymx[i])):
            fill(np.ones(len(bo), dtype=bool))
            return
        m_ = 2.0
        fill((xmx >= xmn[i] - m_) & (xmn <= xmx[i] + m_) & (ymx >= ymn[i] - m_) & (ymn <= ymx[i] + m_))

    def try_surface(self, context, event, region, rv3d, graphs, fallback_msg):
        """Trim d'une surface (maillage à faces) : les courbes de coupe sont projetées le long de la vue."""
        mx, my = event.mouse_x - region.x, event.mouse_y - region.y
        ro = region_2d_to_origin_3d(region, rv3d, Vector((mx, my)))
        rd = region_2d_to_vector_3d(region, rv3d, Vector((mx, my)))
        best = None
        for obj in context.visible_objects:
            if obj.type != 'MESH' or not len(obj.data.polygons) or obj in graphs or obj.hide_select:
                continue
            inv = obj.matrix_world.inverted()
            ok, loc, _nor, _idx = obj.ray_cast(inv @ ro, inv.to_3x3() @ rd)[:4]
            if ok:
                dist = (obj.matrix_world @ loc - ro).length
                if best is None or dist < best[0]:
                    best = (dist, obj, loc)
        if best is None:
            self.report({'INFO'}, fallback_msg)
            return {'CANCELLED'}
        _d, target, loc = best
        self.fill_overlapping(graphs, target)
        cutter_objs = [o for o in context.selected_objects if o in graphs] or list(graphs)
        paths = []
        for o in cutter_objs:
            verts, edges = graphs[o]
            for path, closed in wire_paths(len(verts), edges):
                if len(path) >= 2:
                    paths.append(([verts[j] for j in path], closed))
        if not paths:
            self.report({'INFO'}, "Select the curve(s) that cut the surface (or draw one in front of it)")
            return {'CANCELLED'}
        msg = surface_trim(target, paths, np.array(rv3d.perspective_matrix, dtype=np.float64), loc)
        if msg:
            self.report({'INFO'}, msg)
            return {'CANCELLED'}
        return {'FINISHED'}


class DESSIN_OT_trim_mode(bpy.types.Operator):
    bl_idname = "dessin.trim_mode"
    bl_label = "Trim: Fence / Crossing"
    bl_description = "Chooses how Trim cuts when you drag: with a fence line or with a crossing box"
    bl_options = {'INTERNAL'}

    mode: bpy.props.EnumProperty(items=(('FENCE', "Fence", ""), ('CROSSING', "Crossing", "")), default='FENCE', options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        # utilisable en mode Objet comme en mode Édition (EDIT_MESH : la touche reste telle quelle dans la barre d'outils)
        return context.area is not None and context.area.type == 'VIEW_3D'

    def execute(self, context):
        context.scene.dessin.trim_mode = self.mode
        self.report({'INFO'}, "Trim: " + ("Fence line" if self.mode == 'FENCE' else "Crossing box"))
        for win in context.window_manager.windows:
            for a in win.screen.areas:
                if a.type == 'VIEW_3D':
                    a.tag_redraw()
        return {'FINISHED'}


class DESSIN_OT_tool_from_edit(bpy.types.Operator):
    """Outil de la barre du mode édition dont la commande ne travaille qu'en mode objet : quitte l'édition puis la lance."""
    bl_idname = "dessin.tool_from_edit"
    bl_label = "Leave Edit Mode and run the tool"
    bl_options = {'INTERNAL'}

    cmd: bpy.props.StringProperty()
    tool: bpy.props.StringProperty()

    def invoke(self, context, event):
        if context.mode.startswith('EDIT'):
            try:
                bpy.ops.object.mode_set(mode='OBJECT')
            except RuntimeError:
                self.report({'WARNING'}, "Switch to Object mode to use this tool")
                return {'CANCELLED'}
        try:
            bpy.ops.wm.tool_set_by_id(name=self.tool)
        except (RuntimeError, TypeError):
            pass
        f = getattr(bpy.ops.dessin, self.cmd, None)
        if f is not None:
            try:
                f('INVOKE_DEFAULT')
            except RuntimeError:
                pass
        return {'FINISHED'}


def _edit_native(op_id, mode='EDIT_MESH'):
    """La commande tourne-t-elle telle quelle en mode édition (ou bascule-t-elle d'elle-même) ?"""
    if mode != 'EDIT_MESH':
        return False        # édition de courbe : toute commande quitte d'abord l'édition (elles travaillent sur des objets)
    c = addon_globals().get("DESSIN_OT_" + op_id.split(".", 1)[-1])
    if c is None or issubclass(c, DessinBase):
        return True
    poll = getattr(c, "poll", None)
    if poll is None:
        return True
    try:
        import inspect
        return "EDIT_MESH" in inspect.getsource(getattr(poll, "__func__", poll))
    except (OSError, TypeError):
        return False


def _edit_variant(cls, mode='EDIT_MESH'):
    """Même outil pour la barre du mode édition : les commandes réservées au mode objet passent par tool_from_edit."""
    km = []
    main = next((i[0] for i in cls.bl_keymap if i[0] not in ("dessin.pick_object", "dessin.tool_exit", "dessin.grs_key")), None)
    opc = addon_globals().get("DESSIN_OT_" + main.split(".", 1)[1]) if main and main.startswith("dessin.") else None
    crv_ok = mode == 'EDIT_CURVE' and getattr(opc, "CURVE_EDIT_OK", False)     # Move / Rotate / Scale travaillent sur les points d'une courbe
    for item in cls.bl_keymap:
        op = item[0]
        if op == "dessin.rclick_run":
            continue
        if mode != 'EDIT_MESH' and not crv_ok:
            if op in ("dessin.tool_exit", "dessin.grs_key"):
                km.append(item)
            elif op == "dessin.trim_mode":
                km.append(item)
            elif item[1].get("type") != 'MOUSEMOVE':
                cmd = main if op == "dessin.pick_object" else op
                if cmd:
                    km.append(("dessin.tool_from_edit", item[1], {"properties": [("cmd", cmd.split(".", 1)[1]), ("tool", cls.bl_idname)]}))
            continue
        if op == "dessin.pick_object":
            # on reste en mode édition pendant la sélection (zone, clic) ; Entrée / Espace quitte l'édition et lance la commande
            km.append(("dessin.select_loop", {"type": 'LEFTMOUSE', "value": 'DOUBLE_CLICK', "any": True}, None))
            km.append(("view3d.select_box", {"type": 'LEFTMOUSE', "value": 'CLICK_DRAG', "shift": True}, {"properties": [("mode", 'ADD')]}))
            km.append(("view3d.select_box", {"type": 'LEFTMOUSE', "value": 'CLICK_DRAG', "ctrl": True}, {"properties": [("mode", 'SUB')]}))
            km.append(("view3d.select_box", {"type": 'LEFTMOUSE', "value": 'CLICK_DRAG'}, {"properties": [("mode", 'SET')]}))
        elif op.startswith("dessin.") and op not in ("dessin.tool_exit", "dessin.grs_key") and not _edit_native(op):
            if item[1].get("type") == 'MOUSEMOVE':
                continue           # le survol seul ne doit pas faire quitter le mode édition
            km.append(("dessin.tool_from_edit", item[1],
                       {"properties": [("cmd", op.split(".", 1)[1]), ("tool", cls.bl_idname)]}))
        else:
            km.append(item)
    suffix = "_edit" if mode == 'EDIT_MESH' else "_crv"
    return type(cls.__name__ + suffix, (cls,), {"bl_context_mode": mode, "bl_keymap": tuple(km)})


class DESSIN_OT_bar_click(bpy.types.Operator):
    """Clic sur une puce de la barre du bas (Quick Type, OSnap, Gumball...) avec un outil de sélection natif de Blender."""
    bl_idname = "dessin.bar_click"
    bl_label = "Command bar click"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D'

    def invoke(self, context, event):
        if cmd_click_idle(context, event):
            return {'FINISHED'}
        return {'CANCELLED', 'PASS_THROUGH'}


class DESSIN_OT_rclick_run(bpy.types.Operator):
    """Outils « on désigne les objets, puis Entrée » (Join, Explode...) : clic droit rapide = Entrée (option des préférences)."""
    bl_idname = "dessin.rclick_run"
    bl_label = "Right click = Enter"
    bl_options = {'INTERNAL'}

    cmd: bpy.props.StringProperty()
    action: bpy.props.StringProperty(default="")

    def invoke(self, context, event):
        if not pref("rclick_enter") or context.area is None or context.area.type != 'VIEW_3D':
            return {'PASS_THROUGH'}          # option décochée : le clic droit garde son rôle (orbite, menu...)
        self._x, self._y = event.mouse_x, event.mouse_y
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            tol = max(1, pref("mouse_menu_tol"))
            if abs(event.mouse_x - self._x) > tol or abs(event.mouse_y - self._y) > tol:
                if not start_navigation(context):
                    try:
                        bpy.ops.view3d.rotate('INVOKE_DEFAULT')
                    except RuntimeError:
                        pass
                return {'FINISHED'}
            return {'RUNNING_MODAL'}
        if event.type == 'RIGHTMOUSE' and event.value == 'RELEASE':
            f = getattr(bpy.ops.dessin, self.cmd, None)
            if f is not None:
                try:
                    if self.action:
                        f('INVOKE_DEFAULT', action=self.action)
                    else:
                        f('INVOKE_DEFAULT')
                except (RuntimeError, TypeError):
                    pass
            return {'FINISHED'}
        if event.type == 'ESC':
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}


class DESSIN_OT_tool_exit(bpy.types.Operator):
    bl_idname = "dessin.tool_exit"
    bl_label = "Leave the tool"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        back_to_idle()
        return {'FINISHED'}


# --------------------------------------------------------------------------
# Join / Explode (comme dans Rhino : on désigne les objets, puis Entrée)
# --------------------------------------------------------------------------

JOIN_TOL = 1e-4          # tolérance de jonction (unités Blender)
EXPLODE_LIMIT = 2000     # nombre maximal de morceaux créés par un Explode
EXPLODE_SHARP_DEG = 30.0  # Explode : au-delà de cet angle entre deux facettes, l'arête sépare deux surfaces


def _spline_nodes(sp):
    """Nœuds d'une spline POLY ou BEZIER sous forme commune : dicts co / hl / hr / tl / tr (poignées + types)."""
    nodes = []
    if sp.type == 'BEZIER':
        for q in sp.bezier_points:
            nodes.append({"co": q.co.copy(), "hl": q.handle_left.copy(), "hr": q.handle_right.copy(),
                          "tl": q.handle_left_type, "tr": q.handle_right_type, "r": q.radius})
    else:
        for q in sp.points:
            c = Vector(q.co[:3])
            nodes.append({"co": c, "hl": c.copy(), "hr": c.copy(), "tl": 'VECTOR', "tr": 'VECTOR', "r": q.radius})
    return nodes


def _rev_nodes(nodes):
    return [{"co": n["co"], "hl": n["hr"], "hr": n["hl"], "tl": n["tr"], "tr": n["tl"], "r": n["r"]} for n in reversed(nodes)]


def _join_poly_splines(cu, tol):
    """Raccorde bout à bout les splines ouvertes POLY et BEZIER (arcs, cercles ouverts, lignes) de la courbe cu dont les
    extrémités coïncident. Des polylignes seules donnent une polyligne ; dès qu'un arc est présent, le résultat est une
    spline de Bézier : les arcs restent de vrais arcs et les segments gardent des poignées vectorielles."""
    sps = [sp for sp in cu.splines if sp.type in {'POLY', 'BEZIER'} and not sp.use_cyclic_u
           and (len(sp.points) if sp.type == 'POLY' else len(sp.bezier_points)) >= 2]
    if len(sps) < 1:
        return
    chains = [{"nodes": _spline_nodes(sp), "bez": sp.type == 'BEZIER'} for sp in sps]
    changed = True
    while changed and len(chains) > 1:
        changed = False
        for i in range(len(chains)):
            for j in range(i + 1, len(chains)):
                for ra in (False, True):
                    for rb in (False, True):
                        x = _rev_nodes(chains[i]["nodes"]) if ra else chains[i]["nodes"]
                        y = _rev_nodes(chains[j]["nodes"]) if rb else chains[j]["nodes"]
                        if (x[-1]["co"] - y[0]["co"]).length <= tol:
                            joint = dict(x[-1])
                            joint["hr"], joint["tr"] = y[0]["hr"], y[0]["tr"]
                            chains[i] = {"nodes": x[:-1] + [joint] + y[1:], "bez": chains[i]["bez"] or chains[j]["bez"]}
                            del chains[j]
                            changed = True
                            break
                    if changed:
                        break
                if changed:
                    break
            if changed:
                break
    for sp in sps:
        cu.splines.remove(sp)
    for ch in chains:
        nodes = ch["nodes"]
        closed = (nodes[0]["co"] - nodes[-1]["co"]).length <= tol and len(nodes) >= (3 if ch["bez"] else 4)
        if closed:
            first = dict(nodes[0])
            first["hl"], first["tl"] = nodes[-1]["hl"], nodes[-1]["tl"]
            nodes = [first] + nodes[1:-1]
        if not ch["bez"]:
            sp = cu.splines.new('POLY')
            sp.points.add(len(nodes) - 1)
            for pt, n in zip(sp.points, nodes):
                pt.co = (n["co"].x, n["co"].y, n["co"].z, 1.0)
            sp.use_cyclic_u = closed
        else:
            sp = cu.splines.new('BEZIER')
            sp.bezier_points.add(len(nodes) - 1)
            for pt, n in zip(sp.bezier_points, nodes):
                pt.co = n["co"]
                pt.handle_left_type = pt.handle_right_type = 'FREE'
                pt.handle_left, pt.handle_right = n["hl"], n["hr"]
                pt.handle_left_type, pt.handle_right_type = n["tl"], n["tr"]
                pt.radius = n["r"]
            sp.use_cyclic_u = closed


class DESSIN_OT_join(bpy.types.Operator):
    bl_idname = "dessin.join"
    bl_label = "Join"
    bl_description = ("Joins the selected curves end to end, or the selected surfaces / outlines into one object "
                      "(points closer than the tolerance are merged)")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and context.area is not None and context.area.type == 'VIEW_3D'

    def execute(self, context):
        objs = [o for o in context.selected_objects if o.type in {'MESH', 'CURVE'}]
        if not objs:
            self.report({'INFO'}, "Select the curves or surfaces to join (click them, then Enter)")
            return {'CANCELLED'}
        kinds = {o.type for o in objs}
        if len(kinds) > 1:
            self.report({'WARNING'}, "Join works on curves only or on meshes only")
            return {'CANCELLED'}
        kind = kinds.pop()
        active = context.view_layer.objects.active
        if active not in objs:
            active = objs[0]
            context.view_layer.objects.active = active
        if len(objs) > 1:
            try:
                bpy.ops.object.join()
            except RuntimeError as err:
                self.report({'WARNING'}, f"Join failed: {err}")
                return {'CANCELLED'}
            active = context.view_layer.objects.active
        if kind == 'MESH':
            bm = bmesh.new()
            bm.from_mesh(active.data)
            n0 = len(bm.verts)
            bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=JOIN_TOL)
            n1 = len(bm.verts)
            bm.to_mesh(active.data)
            bm.free()
            active.data.update()
            self.report({'INFO'}, f"Joined: {len(objs)} object(s), {n0 - n1} point(s) merged")
        else:
            before = len(active.data.splines)
            _join_poly_splines(active.data, JOIN_TOL)
            self.report({'INFO'}, f"Joined: {before} curve(s) -> {len(active.data.splines)}")
        for o in list(context.view_layer.objects):
            if o is not None:
                o.select_set(o is active)
        return {'FINISHED'}


def _new_object_like(src, data, name):
    obj = bpy.data.objects.new(name, data)
    obj.matrix_world = src.matrix_world.copy()
    for c in (src.users_collection or [bpy.context.scene.collection]):
        c.objects.link(obj)
    return obj


class DESSIN_OT_explode(bpy.types.Operator):
    bl_idname = "dessin.explode"
    bl_label = "Explode"
    bl_description = ("Explodes the selected objects: polylines into segments, curves with several parts into separate curves, "
                      "meshes into one object per face (or per edge for outlines)")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and context.area is not None and context.area.type == 'VIEW_3D'

    def explode_mesh(self, obj):
        """Comme Explode de Rhino : un solide se sépare en ses surfaces (zones lisses séparées par des arêtes vives),
        pas en chacune de ses facettes. Un cylindre donne 3 surfaces, une boîte 6, une sphère reste entière."""
        me = obj.data
        if len(me.polygons) > 1:
            bm = bmesh.new()
            bm.from_mesh(me)
            bm.faces.ensure_lookup_table()
            sharp = math.radians(EXPLODE_SHARP_DEG)

            def soft(e):
                if len(e.link_faces) != 2 or not e.smooth or e.seam:
                    return False
                try:
                    return e.calc_face_angle() <= sharp
                except ValueError:
                    return False
            seen, isl = set(), []
            for f in bm.faces:
                if f.index in seen:
                    continue
                stack, comp = [f], []
                seen.add(f.index)
                while stack:
                    g = stack.pop()
                    comp.append(g.index)
                    for e in g.edges:
                        if soft(e):
                            for h in e.link_faces:
                                if h.index not in seen:
                                    seen.add(h.index)
                                    stack.append(h)
                isl.append(comp)
            in_face = set()
            for pl in me.polygons:
                in_face.update(pl.edge_keys)
            loose = [e for e in me.edges if tuple(sorted(e.vertices)) not in in_face]
            if len(isl) + len(loose) <= 1:
                bm.free()
                return None
            if len(isl) > EXPLODE_LIMIT:
                bm.free()
                self.report({'WARNING'}, f"{obj.name}: too many pieces ({len(isl)}, limit {EXPLODE_LIMIT})")
                return None
            out = []
            for comp in isl:
                keep = set(comp)
                b2 = bm.copy()
                b2.faces.ensure_lookup_table()
                bmesh.ops.delete(b2, geom=[f for f in b2.faces if f.index not in keep], context='FACES')
                bmesh.ops.delete(b2, geom=[e for e in b2.edges if not e.link_faces], context='EDGES')
                nm = bpy.data.meshes.new(obj.name)
                b2.to_mesh(nm)
                b2.free()
                for m_ in me.materials:
                    nm.materials.append(m_)
                nm.update()
                out.append(_new_object_like(obj, nm, obj.name))
            bm.free()
            verts = [tuple(v.co) for v in me.vertices]
            for e in loose:
                nm = bpy.data.meshes.new(obj.name)
                nm.from_pydata([verts[e.vertices[0]], verts[e.vertices[1]]], [(0, 1)], [])
                nm.update()
                out.append(_new_object_like(obj, nm, obj.name))
            return out
        out = []
        verts = [tuple(v.co) for v in me.vertices]
        in_face = set()
        for p in me.polygons:
            in_face.update(e for e in p.edge_keys)
        total = len(me.polygons) + sum(1 for e in me.edges if tuple(sorted(e.vertices)) not in in_face)
        if total <= 1:
            return None
        if total > EXPLODE_LIMIT:
            self.report({'WARNING'}, f"{obj.name}: too many pieces ({total}, limit {EXPLODE_LIMIT})")
            return None
        for p in me.polygons:
            idx = list(p.vertices)
            nm = bpy.data.meshes.new(obj.name)
            nm.from_pydata([verts[i] for i in idx], [], [list(range(len(idx)))])
            for m in me.materials:
                nm.materials.append(m)
            nm.polygons[0].material_index = p.material_index
            nm.update()
            out.append(_new_object_like(obj, nm, obj.name))
        for e in me.edges:
            if tuple(sorted(e.vertices)) in in_face:
                continue
            nm = bpy.data.meshes.new(obj.name)
            nm.from_pydata([verts[e.vertices[0]], verts[e.vertices[1]]], [(0, 1)], [])
            nm.update()
            out.append(_new_object_like(obj, nm, obj.name))
        return out

    def explode_curve(self, obj):
        cu = obj.data
        pieces = []                       # [(type, points)]
        if len(cu.splines) > 1:
            for sp in cu.splines:
                pieces.append(sp)
            mode = 'SPLINES'
        elif len(cu.splines) == 1 and cu.splines[0].type in {'POLY', 'BEZIER'}:
            mode = 'SEGMENTS'
        else:
            return None
        out = []
        if mode == 'SPLINES':
            for sp in pieces:
                nc = bpy.data.curves.new(obj.name, 'CURVE')
                nc.dimensions = cu.dimensions
                for m in cu.materials:
                    nc.materials.append(m)
                ns_ = nc.splines.new(sp.type)
                if sp.type == 'BEZIER':
                    ns_.bezier_points.add(len(sp.bezier_points) - 1)
                    for a, b in zip(sp.bezier_points, ns_.bezier_points):
                        b.handle_left_type = b.handle_right_type = 'FREE'
                        b.co, b.handle_left, b.handle_right = a.co, a.handle_left, a.handle_right
                else:
                    ns_.points.add(len(sp.points) - 1)
                    for a, b in zip(sp.points, ns_.points):
                        b.co = a.co
                ns_.use_cyclic_u = sp.use_cyclic_u
                out.append(_new_object_like(obj, nc, obj.name))
            return out
        sp = cu.splines[0]
        if sp.type == 'POLY':
            pts = [Vector(p.co[:3]) for p in sp.points]
            n = len(pts)
            segs = [(pts[i], pts[(i + 1) % n]) for i in range(n if sp.use_cyclic_u else n - 1)]
            if len(segs) <= 1:
                return None
            if len(segs) > EXPLODE_LIMIT:
                self.report({'WARNING'}, f"{obj.name}: too many segments ({len(segs)})")
                return None
            for a, b in segs:
                nc = bpy.data.curves.new(obj.name, 'CURVE')
                nc.dimensions = cu.dimensions
                for m in cu.materials:
                    nc.materials.append(m)
                s2 = nc.splines.new('POLY')
                s2.points.add(1)
                s2.points[0].co = (a.x, a.y, a.z, 1.0)
                s2.points[1].co = (b.x, b.y, b.z, 1.0)
                out.append(_new_object_like(obj, nc, obj.name))
            return out
        bp = sp.bezier_points
        n = len(bp)
        count = n if sp.use_cyclic_u else n - 1
        if count <= 1:
            return None
        for i in range(count):
            a, b = bp[i], bp[(i + 1) % n]
            nc = bpy.data.curves.new(obj.name, 'CURVE')
            nc.dimensions = cu.dimensions
            for m in cu.materials:
                nc.materials.append(m)
            s2 = nc.splines.new('BEZIER')
            s2.bezier_points.add(1)
            for q, src in ((s2.bezier_points[0], a), (s2.bezier_points[1], b)):
                q.handle_left_type = q.handle_right_type = 'FREE'
                q.co, q.handle_left, q.handle_right = src.co, src.handle_left, src.handle_right
            out.append(_new_object_like(obj, nc, obj.name))
        return out

    def execute(self, context):
        insts = [o for o in context.selected_objects if is_block_instance(o)]
        objs = [o for o in context.selected_objects if o.type in {'MESH', 'CURVE'}]
        if not objs and not insts:
            self.report({'INFO'}, "Select the objects to explode (click them, then Enter)")
            return {'CANCELLED'}
        created = []
        for inst in insts:                  # un bloc éclaté redonne ses objets (comme Explode sur un bloc dans Rhino)
            created.extend(explode_block(context, inst))
        for obj in objs:
            res = self.explode_mesh(obj) if obj.type == 'MESH' else self.explode_curve(obj)
            if not res:
                continue
            data = obj.data
            bpy.data.objects.remove(obj)
            if data.users == 0:
                (bpy.data.meshes if isinstance(data, bpy.types.Mesh) else bpy.data.curves).remove(data)
            created.extend(res)
        if not created:
            self.report({'INFO'}, "Nothing to explode")
            return {'CANCELLED'}
        for o in list(context.view_layer.objects):
            if o is not None:
                o.select_set(False)
        for o in created:
            if o is not None:
                o.select_set(True)
        context.view_layer.objects.active = created[-1]
        self.report({'INFO'}, f"Exploded into {len(created)} object(s)")
        return {'FINISHED'}


class DESSIN_OT_pick_object(bpy.types.Operator):
    bl_idname = "dessin.pick_object"
    bl_label = "Pick object"
    bl_description = "Adds the object under the cursor to the selection (click it again to remove it)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and context.area is not None and context.area.type == 'VIEW_3D'

    def invoke(self, context, event):
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS' and context.area is not None and cmd_click_idle(context, event):
            return {'CANCELLED'}
        region = find_window_region(context.area, event.mouse_x, event.mouse_y)
        if region is None:
            return {'CANCELLED', 'PASS_THROUGH'}
        rv3d = context.area.spaces.active.region_3d
        mx, my = event.mouse_x - region.x, event.mouse_y - region.y
        persp = np.array(rv3d.perspective_matrix, dtype=np.float64)
        dg = context.evaluated_depsgraph_get()
        best, best_d = None, 14.0 * px_scale()
        for obj in context.visible_objects:
            g = wire_graph(obj, dg)
            if g is None or not g[1]:
                continue
            V = np.array([tuple(v) for v in g[0]], dtype=np.float64)
            E = np.array(g[1], dtype=np.int64)
            sx, sy, ok = _project_region(V, persp, region)
            ax, ay, bx, by = sx[E[:, 0]], sy[E[:, 0]], sx[E[:, 1]], sy[E[:, 1]]
            dx, dy = bx - ax, by - ay
            l2 = dx * dx + dy * dy
            t = np.clip(((mx - ax) * dx + (my - ay) * dy) / np.where(l2 > 1e-12, l2, 1.0), 0.0, 1.0)
            dist = np.hypot(ax + t * dx - mx, ay + t * dy - my)
            dist[~(ok[E[:, 0]] & ok[E[:, 1]])] = np.inf
            d = float(dist.min())
            if d < best_d:
                best, best_d = obj, d
        if best is None:
            ro = region_2d_to_origin_3d(region, rv3d, Vector((mx, my)))
            rd = region_2d_to_vector_3d(region, rv3d, Vector((mx, my)))
            near = None
            for obj in context.visible_objects:
                if obj.type != 'MESH' or not len(obj.data.polygons):
                    continue
                inv = obj.matrix_world.inverted()
                ok, loc, _n, _i = obj.ray_cast(inv @ ro, inv.to_3x3() @ rd)[:4]
                if ok:
                    dist = (obj.matrix_world @ loc - ro).length
                    if near is None or dist < near[0]:
                        near = (dist, obj)
            best = near[1] if near else None
        if best is None:
            return {'CANCELLED'}
        best.select_set(not best.select_get())
        if best.name in _PICK_ORDER:
            _PICK_ORDER.remove(best.name)
        if best.select_get():
            _PICK_ORDER.append(best.name)
            context.view_layer.objects.active = best
        return {'FINISHED'}


def _late_imports():
    """Noms définis dans des modules chargés après celui-ci : ils ne servent qu'à l'exécution des outils."""
    global _PICK_ORDER, cmd_click_idle, cmd_log, explode_block, is_block_instance, start_navigation
    from .surfaces import _PICK_ORDER
    from .curve_tools import is_block_instance
    from .blocks import explode_block
    from .navigation import start_navigation
    from .cplane import cmd_log
    from .command_line import cmd_click_idle
