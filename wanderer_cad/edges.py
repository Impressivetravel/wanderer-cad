"""Wanderer CAD : Arêtes de maillages : Fillet Edge, Chamfer Edge, Offset Edge."""

import bmesh
import bpy
import math
import numpy as np
from bpy_extras.view3d_utils import region_2d_to_origin_3d
from mathutils import Vector

from .core import TAU, _link_object, build_bezier_arc, idle_tool, plane_axes
from .drawing import find_window_region, px_scale, region_rv3d
from .base import DessinBase


# --------------------------------------------------------------------------
# Fillet Edge (congé sur arêtes de maillages)
# --------------------------------------------------------------------------

FILLET_STATE = {"radius": 0.05, "segments": 8}
CHAMFER_STATE = {"radius": 0.02, "segments": 1}


def mesh_edge_geometry(obj):
    """(coordonnées monde des sommets, arêtes) d'un maillage, ou None."""
    me = obj.data
    nv, ne = len(me.vertices), len(me.edges)
    if nv == 0 or ne == 0 or ne > 400000:
        return None
    co = np.empty(nv * 3, dtype=np.float32)
    me.vertices.foreach_get('co', co)
    ed = np.empty(ne * 2, dtype=np.int32)
    me.edges.foreach_get('vertices', ed)
    mw = np.array(obj.matrix_world, dtype=np.float64)
    wco = co.reshape(-1, 3).astype(np.float64) @ mw[:3, :3].T + mw[:3, 3]
    return wco, ed.reshape(-1, 2)


class DessinEdgeRound(DessinBase):
    """Base de Fillet Edge / Chamfer Edge (classe non enregistrée)."""

    STATE = FILLET_STATE
    CHAMFER = False
    WORD = "radius"

    TITLE = "Fillet Edge"
    NEEDED = 2
    NUMFIELDS = 2
    EDIT_OK = True
    HAS_CENTER = False
    PLANAR = False
    LOCK_OK = False
    PICK_PX = 12.0

    # ---- cycle de vie ----
    def invoke(self, context, event):
        self.reenter_edit = False
        pre = {}
        if context.mode == 'EDIT_MESH':
            try:
                for o in context.objects_in_mode_unique_data:
                    if o.type == 'MESH':
                        o.update_from_editmode()
                        pre[o.name] = {e.index for e in o.data.edges if e.select}
            except (AttributeError, RuntimeError):
                pre = {}
            try:
                bpy.ops.object.mode_set(mode='OBJECT')
                self.reenter_edit = True
            except RuntimeError:
                self.report({'WARNING'}, "Switch to Object mode")
                return {'CANCELLED'}
        self.sel = {}
        self.hilite = []
        self.box = None
        self._press = None
        self.phase = 'pick'
        self.orig = {}
        self.work = {}
        self.geo = {}
        self.committed = False
        self.anchor = None
        self.mouse_moved = False
        result = super().invoke(context, event)
        if 'RUNNING_MODAL' not in result:
            if self.reenter_edit:
                try:
                    bpy.ops.object.mode_set(mode='EDIT')
                except RuntimeError:
                    pass
            return result
        for name, idx in pre.items():
            if idx:
                self.sel[name] = set(idx)
        if self.total_selected():
            self.begin_radius(context)
        else:
            self.refresh(context)
        return result

    def reset_state(self):
        self.restore_all()
        self.phase = 'pick'
        self.anchor = None
        self.mouse_moved = False
        super().reset_state()

    def cleanup(self, context):
        if not self.committed:
            self.restore_all()
        super().cleanup(context)
        if self.reenter_edit:
            try:
                bpy.ops.object.mode_set(mode='EDIT')
            except RuntimeError:
                pass

    def after_finish(self, context):
        if self.tool_id:
            try:
                idle_tool()
            except (RuntimeError, TypeError):
                pass

    # ---- sélection des arêtes ----
    def total_selected(self):
        return sum(len(v) for v in self.sel.values())

    def candidates(self, context):
        objs = [o for o in context.view_layer.objects if o.type == 'MESH' and o.visible_get()]
        chosen = [o for o in objs if o.select_get()]
        return chosen or objs

    def geometry(self, obj):
        g = self.geo.get(obj.name)
        if g is None and obj.name not in self.geo:
            g = mesh_edge_geometry(obj)
            self.geo[obj.name] = g
        return g

    def pick_edge(self, context):
        """(objet, indice d'arête) sous la souris, ou None."""
        if getattr(self, "_mouse", None) is None or self.region is None:
            return None
        rv3d = region_rv3d(self.region, self.area)
        if rv3d is None:
            return None
        P = np.array(rv3d.perspective_matrix, dtype=np.float64)
        W, H = self.region.width, self.region.height
        mx, my = self._mouse
        limit = self.PICK_PX * px_scale()
        cands = self.candidates(context)
        vkey = (P.tobytes(), W, H, id(self.geo))
        pc = getattr(self, "_pick_cache", None)
        if pc is None or pc[0] != vkey:
            pc = self._pick_cache = (vkey, {})         # arêtes projetées par objet, tant que la vue ne bouge pas
        per_obj = pc[1]
        r_ = limit + 2.0
        names = tuple(o.name for o in cands)
        bounds = getattr(self, "_pick_bounds", None)
        if bounds is None or bounds[0] != (vkey, names):
            bounds = self._pick_bounds = ((vkey, names), objects_screen_bounds(cands, P, self.region))
        bo, xmn, xmx, ymn, ymx, _sure = bounds[1]
        hitb = (xmx >= mx - r_) & (xmn <= mx + r_) & (ymx >= my - r_) & (ymn <= my + r_)
        near_objs = [bo[i] for i in np.nonzero(hitb)[0]]
        objs, parts = [], []
        for obj in near_objs:
            d = per_obj.get(obj.name)
            if d is None:
                g = self.geometry(obj)
                if g is None or not len(g[1]):
                    per_obj[obj.name] = False
                    continue
                wco, ed = g
                clip = np.hstack((wco, np.ones((len(wco), 1)))) @ P.T
                w = clip[:, 3]
                ok = w > 1e-9
                ws = np.where(ok, w, 1.0)
                sx = (clip[:, 0] / ws * 0.5 + 0.5) * W
                sy = (clip[:, 1] / ws * 0.5 + 0.5) * H
                zn = np.clip(clip[:, 2] / ws, -1.0, 1.0)  # profondeur écran : départage aussi les arêtes superposées en vue orthogonale
                a, b = ed[:, 0], ed[:, 1]
                d = per_obj[obj.name] = (sx[a], sy[a], sx[b], sy[b], ok[a] & ok[b],
                                         0.01 * (ws[a] + ws[b]) * 0.5 + 0.25 * (zn[a] + zn[b]))
            if d is False:
                continue
            objs.append(obj)
            parts.append(d)
        if not objs:
            return None
        owner = np.concatenate([np.full(len(d[0]), i, dtype=np.int32) for i, d in enumerate(parts)])
        local = np.concatenate([np.arange(len(d[0]), dtype=np.int64) for d in parts])
        ax, ay, bx, by, valid, depth = (np.concatenate([d[k] for d in parts]) for k in range(6))
        self._pick_data = (objs, owner, local, ax, ay, bx, by, valid, depth)
        m_ = limit + 1.0       # on ne calcule la distance que pour les arêtes dont la boîte écran est proche du curseur
        near = valid & (np.minimum(ax, bx) <= mx + m_) & (np.maximum(ax, bx) >= mx - m_) \
            & (np.minimum(ay, by) <= my + m_) & (np.maximum(ay, by) >= my - m_)
        idx = np.nonzero(near)[0]
        if not len(idx):
            return None
        ax, ay, bx, by = ax[idx], ay[idx], bx[idx], by[idx]
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        t = np.where(L2 > 1e-12, ((mx - ax) * dx + (my - ay) * dy) / np.where(L2 > 1e-12, L2, 1.0), 0.0)
        t = np.clip(t, 0.0, 1.0)
        dist = np.hypot(ax + dx * t - mx, ay + dy * t - my)
        score = dist + depth[idx]
        order = [int(j) for j in np.argsort(score)[:12] if dist[int(j)] <= limit]
        if not order:
            return None
        # vue ombrée : une arête cachée derrière une surface (ex. la courbe d'origine sous un solide) ne se choisit pas,
        # même si elle est plus proche du curseur à l'écran
        for j in order:
            k = int(idx[j])
            obj, e = objs[int(owner[k])], int(local[k])
            if not self.edge_hidden(context, obj, e, float(t[j])):
                return obj, e
        k = int(idx[order[0]])
        return objs[int(owner[k])], int(local[k])

    def edge_hidden(self, context, obj, e, t):
        """Le point de l'arête sous le curseur est-il masqué par une surface (vue ombrée, sans transparence) ?"""
        try:
            space = self.area.spaces.active
            if space.shading.type == 'WIREFRAME' or space.shading.show_xray:
                return False
            g = self.geometry(obj)
            if g is None:
                return False
            wco, ed = g
            a_, b_ = ed[e]
            pt = Vector(wco[a_]) + (Vector(wco[b_]) - Vector(wco[a_])) * t
            rv3d = region_rv3d(self.region, self.area)
            from bpy_extras.view3d_utils import location_3d_to_region_2d
            sp = location_3d_to_region_2d(self.region, rv3d, pt)
            if sp is None:
                return False
            ro = region_2d_to_origin_3d(self.region, rv3d, sp)
            d = pt - ro
            L = d.length
            if L < 1e-9:
                return False
            ok, loc, _n, _i, hit_obj, _m = ray_cast_opaque(context, ro, d / L)
            return bool(ok) and (loc - ro).length < L - max(1e-4, 1e-3 * L)
        except (AttributeError, ReferenceError, TypeError, ValueError, RuntimeError, IndexError):
            return False

    def box_select(self, context, remove):
        """Zone vers la droite : arêtes entièrement dedans ; vers la gauche : arêtes touchées (comme la sélection Rhino)."""
        x0, y0, x1, y1 = self.box
        crossing = x1 < x0
        xmin, xmax, ymin, ymax = min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1)
        rv3d = region_rv3d(self.region, self.area)
        if rv3d is None:
            return 0
        P = np.array(rv3d.perspective_matrix, dtype=np.float64)
        W, H = self.region.width, self.region.height
        n = 0
        for obj in self.candidates(context):
            g = self.geometry(obj)
            if g is None:
                continue
            wco, ed = g
            clip = np.hstack((wco, np.ones((len(wco), 1)))) @ P.T
            w = clip[:, 3]
            ok = w > 1e-9
            ws = np.where(ok, w, 1.0)
            sx = (clip[:, 0] / ws * 0.5 + 0.5) * W
            sy = (clip[:, 1] / ws * 0.5 + 0.5) * H
            a, b = ed[:, 0], ed[:, 1]
            valid = ok[a] & ok[b]
            if crossing:
                hit = _segments_hit_rect(sx[a], sy[a], sx[b], sy[b], xmin, ymin, xmax, ymax)
            else:
                ina = (sx[a] >= xmin) & (sx[a] <= xmax) & (sy[a] >= ymin) & (sy[a] <= ymax)
                inb = (sx[b] >= xmin) & (sx[b] <= xmax) & (sy[b] >= ymin) & (sy[b] <= ymax)
                hit = ina & inb
            idx = np.nonzero(hit & valid)[0]
            if not len(idx):
                continue
            s = self.sel.setdefault(obj.name, set())
            for i in idx.tolist():
                if remove:
                    s.discard(i)
                else:
                    s.add(i)
            n += len(idx)
        return n

    def box_select_from(self, context, box, remove):
        self.box = box
        try:
            return self.box_select(context, remove)
        finally:
            self.box = None

    def update_cursor(self, context, event):
        region = find_window_region(self.area, event.mouse_x, event.mouse_y) if self.area is not None else None
        if region is not None:
            self._mouse = (event.mouse_x - region.x, event.mouse_y - region.y)
        super().update_cursor(context, event)

    def edge_lines(self, items):
        out = []
        for name, idx in items:
            obj = bpy.data.objects.get(name)
            if obj is None:
                continue
            g = self.geometry(obj)
            if g is None:
                continue
            wco, ed = g
            for i in idx:
                if i < len(ed):
                    out.append([Vector(wco[ed[i][0]]), Vector(wco[ed[i][1]])])
        return out

    # ---- rayon ----
    def radius_now(self):
        t = self.typed_value(0)
        if t is not None:
            return abs(t)
        return self.STATE["radius"]

    def segments_now(self):
        if self.CHAMFER:
            return 1
        t = self.typed_raw(1)
        if t is not None:
            return int(max(1, min(64, round(t))))
        return self.STATE["segments"]

    def begin_radius(self, context):
        if not self.total_selected():
            return False
        self.phase = 'radius'
        self.anchor = self.cur.copy() if self.cur is not None else Vector()
        self.points = [self.anchor.copy()]
        self.mouse_moved = False
        self.typed = ['', '']
        self.apply_preview()
        self.refresh(context)
        return True

    def prompt(self):
        if self.phase == 'pick':
            return (f"click or drag a box to select the edges ({self.total_selected()} selected), then Enter   "
                    "[box to the right: inside, to the left: touching, Ctrl/Cmd: deselect, click a selected edge: remove it]")
        if self.CHAMFER:
            return f"type the distance <{self.fmt(self.STATE['radius'])}>, Enter to confirm"
        return (f"type the radius <{self.fmt(self.STATE['radius'])}>, Tab, segments, Enter to confirm   "
                "[↑/↓: segments]")

    def compute(self):
        if self.phase == 'pick':
            sel = self.edge_lines((n, s) for n, s in self.sel.items())
            hit = None
            try:
                if self._press is None:
                    hit = self.pick_edge(bpy.context)
            except (ReferenceError, RuntimeError):
                pass
            prev = []
            if hit is not None:
                prev = self.edge_lines([(hit[0].name, [hit[1]])])
                prev = prev[0] if prev else []
            self.hilite = sel[:3000]
            return prev, [], f"{self.total_selected()} edge(s) selected", None
        self.hilite = []
        r, n = self.radius_now(), self.segments_now()
        guides = self.edge_lines((nm, s) for nm, s in self.sel.items())[:3000]
        if self.CHAMFER:
            return [], guides, f"distance {self.fmt(r)}", ("fillet", r, n)
        return [], guides, f"radius {self.fmt(r)}   {n} segments", ("fillet", r, n)

    def refresh(self, context):
        super().refresh(context)
        if self.phase == 'radius':
            self.apply_preview()

    # ---- application sur les maillages ----
    def apply_preview(self):
        r, n = self.radius_now(), self.segments_now()
        for name, idx in self.sel.items():
            obj = bpy.data.objects.get(name)
            if obj is None or not idx:
                continue
            if name not in self.orig:
                self.orig[name] = obj.data
                self.work[name] = obj.data.copy()
                obj.data = self.work[name]
            fillet_mesh(self.orig[name], self.work[name], idx, r, n, self.CHAMFER)

    def restore_all(self):
        for name, orig in list(self.orig.items()):
            obj = bpy.data.objects.get(name)
            work = self.work.get(name)
            try:
                if obj is not None:
                    obj.data = orig
                if work is not None:
                    bpy.data.meshes.remove(work)
            except (ReferenceError, RuntimeError):
                pass
        self.orig = {}
        self.work = {}
        self.geo = {}

    def finish_shape(self, context):
        if self.phase != 'radius':
            return
        self.STATE["radius"] = self.radius_now()
        self.STATE["segments"] = self.segments_now()
        self.apply_preview()
        for name, orig in self.orig.items():
            work = self.work.get(name)
            obj = bpy.data.objects.get(name)
            if work is None or obj is None:
                continue
            base = orig.name
            if orig.users == 0:
                bpy.data.meshes.remove(orig)
                work.name = base
        self.committed = True
        self.finished = True

    # ---- événements ----
    def click(self, context):
        if self.phase == 'radius':
            return      # le rayon se tape au clavier (Entrée valide), un clic n'a pas d'effet
        hit = self.pick_edge(context)
        if hit is None:
            return
        obj, i = hit
        s = self.sel.setdefault(obj.name, set())
        if i in s:
            s.discard(i)
        else:
            s.add(i)
        self.refresh(context)

    def modal(self, context, event):
        inside = (self.area is not None and context.area is not None
                  and find_window_region(self.area, event.mouse_x, event.mouse_y) is not None
                  and not self.mouse_over_ui(event))
        if self.phase == 'pick' and self.area is not None and context.area is not None:
            region = find_window_region(self.area, event.mouse_x, event.mouse_y)
            if (event.type == 'LEFTMOUSE' and event.value == 'PRESS' and inside
                    and not (event.alt or event.oskey)):
                self._press = (event.mouse_x - region.x, event.mouse_y - region.y)
                self._press_ctrl = event.ctrl
                self.box = None
                return {'RUNNING_MODAL'}
            if self._press is not None:
                if event.type == 'ESC' and event.value == 'PRESS':
                    self._press = None
                    self.box = None
                    self.refresh(context)
                    return {'RUNNING_MODAL'}
                if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'} and region is not None:
                    mx, my = event.mouse_x - region.x, event.mouse_y - region.y
                    px0, py0 = self._press
                    if self.box is not None or math.hypot(mx - px0, my - py0) > 5.0 * px_scale():
                        self.box = (px0, py0, mx, my)
                        try:
                            self.area.tag_redraw()
                        except ReferenceError:
                            pass
                    return {'RUNNING_MODAL'}
                if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
                    box, ctrl = self.box, self._press_ctrl
                    self._press = None
                    self.box = None
                    if box is not None:
                        n = self.box_select_from(context, box, ctrl)
                    else:
                        self.update_cursor(context, event)
                        self.click(context)
                    self.refresh(context)
                    return {'RUNNING_MODAL'}
        if inside and event.value == 'PRESS':
            if event.type in {'RET', 'NUMPAD_ENTER', 'SPACE'}:
                if self.phase == 'pick':
                    if not self.total_selected() or not self.begin_radius(context):
                        return self.exit(context)
                    return {'RUNNING_MODAL'}
                self.finish_shape(context)
                return self.exit(context)
            if event.type in {'UP_ARROW', 'DOWN_ARROW'} and self.phase == 'radius' and not self.CHAMFER:
                step = 1 if event.type == 'UP_ARROW' else -1
                self.typed[1] = ''
                self.STATE["segments"] = max(1, min(64, self.STATE["segments"] + step))
                self.refresh(context)
                return {'RUNNING_MODAL'}
            if event.type == 'ESC' and self.phase == 'radius':
                return self.exit(context)
        return super().modal(context, event)


def fillet_mesh(src, dst, edge_idx, radius, segments, chamfer=False):
    """dst = src dont les arêtes edge_idx sont arrondies (congé de rayon `radius`)."""
    bm = bmesh.new()
    bm.from_mesh(src)
    bm.edges.ensure_lookup_table()
    edges = [bm.edges[i] for i in edge_idx if i < len(bm.edges)]
    if edges:
        offs = []
        for e in edges:
            if len(e.link_faces) == 2:
                a = e.link_faces[0].normal.angle(e.link_faces[1].normal, 0.0)
                offs.append(radius if chamfer else (radius * math.tan(a / 2.0) if a > 1e-3 else 0.0))
            else:
                offs.append(radius)
        off = sum(offs) / len(offs)
        if off > 1e-9:
            try:
                ret = bmesh.ops.bevel(bm, geom=edges, offset=off, offset_type='OFFSET', segments=segments,
                                      profile=0.5, affect='EDGES', clamp_overlap=True, loop_slide=True)
                for f in ret.get("faces", []):
                    if f.is_valid:
                        f.smooth = not chamfer
            except (RuntimeError, ValueError, TypeError):
                pass
    bm.normal_update()
    bm.to_mesh(dst)
    bm.free()
    dst.update()


class DESSIN_OT_fillet_edge(DessinEdgeRound):
    bl_idname = "dessin.fillet_edge"
    bl_label = "Fillet Edge"
    bl_description = ("Rounds the edges of solids: click the edges or drag a box (right: inside, left: touching, "
                      "Ctrl/Cmd: deselect), Enter, then type the radius (↑/↓: segments). "
                      "In Edit mode the selected edges are used")


class DESSIN_OT_chamfer_edge(DessinEdgeRound):
    bl_idname = "dessin.chamfer_edge"
    bl_label = "Chamfer Edge"
    bl_description = ("Bevels the edges of solids with a flat cut: click the edges or drag a box (right: inside, "
                      "left: touching, Ctrl/Cmd: deselect), Enter, then type the distance. "
                      "In Edit mode the selected edges are used")
    TITLE = "Chamfer Edge"
    NUMFIELDS = 1
    STATE = CHAMFER_STATE
    CHAMFER = True


# --------------------------------------------------------------------------
# Offset Edge (copie parallèle d'arêtes de maillage ou de courbes)
# --------------------------------------------------------------------------

OFFSET_STATE = {"dist": 0.05}


def curve_edge_geometry(obj):
    """(sommets monde, arêtes) de la courbe évaluée, ou None."""
    try:
        dg = bpy.context.evaluated_depsgraph_get()
        ev = obj.evaluated_get(dg)
        me = ev.to_mesh()      # maillage temporaire (pas un bloc de données : rien à supprimer de bpy.data, qui ralentit avec la taille du fichier)
    except (RuntimeError, ReferenceError, TypeError):
        return None
    if me is None:
        return None
    try:
        nv, ne = len(me.vertices), len(me.edges)
        if nv == 0 or ne == 0 or ne > 400000:
            return None
        co = np.empty(nv * 3, dtype=np.float32)
        me.vertices.foreach_get('co', co)
        ed = np.empty(ne * 2, dtype=np.int32)
        me.edges.foreach_get('vertices', ed)
    finally:
        try:
            ev.to_mesh_clear()
        except (RuntimeError, ReferenceError):
            pass
    mw = np.array(obj.matrix_world, dtype=np.float64)
    wco = co.reshape(-1, 3).astype(np.float64) @ mw[:3, :3].T + mw[:3, 3]
    return wco, ed.reshape(-1, 2)


def edge_chains(wco, edges, picked):
    """Assemble les arêtes choisies en chaînes continues : [(points Vector, fermée)]."""
    key = {}
    pts = []
    vid = {}

    def vkey(i):
        k = tuple(np.round(wco[i], 6))
        if k not in key:
            key[k] = len(pts)
            pts.append(Vector(wco[i]))
        vid[i] = key[k]
        return key[k]
    segs = []
    for e in picked:
        a, b = vkey(int(edges[e][0])), vkey(int(edges[e][1]))
        if a != b:
            segs.append((a, b))
    adj = {}
    for si, (a, b) in enumerate(segs):
        adj.setdefault(a, []).append(si)
        adj.setdefault(b, []).append(si)
    used = [False] * len(segs)
    out = []

    def walk(start, first):
        path = [start]
        cur, si = start, first
        while si is not None and not used[si]:
            used[si] = True
            a, b = segs[si]
            nxt = b if a == cur else a
            path.append(nxt)
            cur = nxt
            more = [x for x in adj[cur] if not used[x]]
            si = more[0] if (len(adj[cur]) == 2 and more) else None
        return path
    for v, lst in adj.items():          # chaînes ouvertes : on part des extrémités
        if len(lst) != 2:
            for si in lst:
                if not used[si]:
                    out.append((walk(v, si), False))
    for si in range(len(segs)):         # le reste : boucles fermées
        if not used[si]:
            path = walk(segs[si][0], si)
            out.append((path, path[0] == path[-1]))
    res = []
    for path, closed in out:
        P = [pts[i] for i in path]
        if closed and len(P) > 1 and (P[0] - P[-1]).length < 1e-9:
            P = P[:-1]
        clean = [P[0]]
        for q in P[1:]:
            if (q - clean[-1]).length > 1e-9:
                clean.append(q)
        if closed and len(clean) > 2 and (clean[0] - clean[-1]).length < 1e-9:
            clean.pop()
        if len(clean) >= 2:
            res.append((clean, closed and len(clean) >= 3))
    return res


def chain_normal(P, closed, fallback):
    """Normale du plan d'une chaîne (méthode de Newell) ; `fallback` si elle est alignée."""
    n = Vector()
    m = len(P)
    for i in range(m):
        a, b = P[i], P[(i + 1) % m]
        n += a.cross(b)
    if n.length < 1e-9 * max(1.0, sum((q - P[0]).length for q in P)):
        return fallback.copy()
    n.normalize()
    if n.dot(fallback) < 0:
        n.negate()
    return n


def offset_polyline(P, closed, n, d):
    """Décale la chaîne P (plan de normale n) de d vers la gauche du sens de parcours (angles en onglet).
    Les segments devenus trop courts pour la distance (un petit chanfrein, une facette d'arc plus petite que d) disparaissent,
    leurs voisins se rejoignent : le décalage ne se retourne pas sur lui-même."""
    pts = [Vector(p) for p in P]
    for _ in range(4 * len(pts) + 8):
        m = len(pts)
        cnt = m if closed else m - 1
        if m < 4 or cnt < 3:
            break
        T, ln = [], []
        for i in range(cnt):
            t = pts[(i + 1) % m] - pts[i]
            ln.append(t.length)
            if t.length < 1e-12:
                return _offset_raw(pts, closed, n, d)
            t.normalize()
            T.append(t)
        Lf = [n.cross(t) for t in T]
        M = {}
        for i in range(m):
            if not closed and (i == 0 or i == m - 1):
                continue
            l0, l1 = Lf[(i - 1) % cnt], Lf[i % cnt]
            den = 1.0 + l0.dot(l1)
            if den >= 0.1:
                M[i] = (l0 + l1) * (d / den)
        bad = None
        for i in range(cnt):
            a_, b_ = i, (i + 1) % m
            if a_ in M and b_ in M and ln[i] + (M[b_] - M[a_]).dot(T[i]) < -1e-9:
                bad = i
                break
        if bad is None:
            break
        ia, ib = (bad - 1) % cnt, (bad + 1) % cnt
        hit = _line_meet(pts[ia], T[ia], pts[ib], T[ib])
        if hit is None:
            break
        a_, b_ = bad, (bad + 1) % m
        new = []
        for j, p in enumerate(pts):
            if j == a_:
                new.append(hit[0])
            elif j != b_:
                new.append(p)
        pts = new
    return _offset_raw(pts, closed, n, d)


def _offset_raw(P, closed, n, d):
    m = len(P)
    cnt = m if closed else m - 1
    L = []
    for i in range(cnt):
        t = P[(i + 1) % m] - P[i]
        t.normalize()
        L.append(n.cross(t))
    out = []
    for i in range(m):
        if not closed and i == 0:
            out.append(P[0] + L[0] * d)
        elif not closed and i == m - 1:
            out.append(P[i] + L[-1] * d)
        else:
            l0, l1 = L[(i - 1) % cnt], L[i % cnt]
            den = 1.0 + l0.dot(l1)
            if den < 0.1:
                out.append(P[i] + l0 * d)
                out.append(P[i] + l1 * d)
            else:
                out.append(P[i] + (l0 + l1) * (d / den))
    return out


def offset_collapsed(P, closed, Q, d):
    """Le décalage Q (à la distance d) de la chaîne P s'est-il effondré ? Un décalage valide reste partout à au moins d de P ;
    s'il se rapproche (distance trop grande pour la forme), il se retourne sur lui-même. Contrôle sur les sommets et les milieux."""
    A = np.array([tuple(p) for p in P], dtype=np.float64)
    B = np.array([tuple(q) for q in Q], dtype=np.float64)
    if len(A) < 2 or len(B) < 2 or d < 1e-12 or len(A) * len(B) > 4e7:
        return False
    Bn = np.roll(B, -1, axis=0) if closed else B[1:]
    Bc = B if closed else B[:-1]
    S = np.vstack([B, (Bc + Bn) * 0.5, Bc * 0.75 + Bn * 0.25, Bc * 0.25 + Bn * 0.75])
    A1 = np.roll(A, -1, axis=0) if closed else A[1:]
    A0 = A if closed else A[:-1]
    ab = A1 - A0
    l2 = np.einsum('ij,ij->i', ab, ab)
    best = np.full(len(S), np.inf)
    for i in range(0, len(S), 512):
        chunk = S[i:i + 512]
        w = chunk[:, None, :] - A0[None, :, :]
        t = np.clip(np.einsum('kij,ij->ki', w, ab) / np.where(l2 > 1e-18, l2, 1.0), 0.0, 1.0)
        proj = A0[None, :, :] + t[:, :, None] * ab[None, :, :]
        best[i:i + 512] = np.linalg.norm(chunk[:, None, :] - proj, axis=2).min(axis=1)
    return bool(best.min() < d * (1.0 - 2e-3) - 1e-9)


def nearest_on_chain(P, closed, q):
    """(indice du segment, point le plus proche) de q sur la chaîne."""
    m = len(P)
    cnt = m if closed else m - 1
    best = None
    for i in range(cnt):
        a, b = P[i], P[(i + 1) % m]
        ab = b - a
        t = max(0.0, min(1.0, (q - a).dot(ab) / ab.dot(ab))) if ab.length_squared > 1e-18 else 0.0
        c = a + ab * t
        d2 = (q - c).length_squared
        if best is None or d2 < best[0]:
            best = (d2, i, c)
    return best[1], best[2]


def offset_arc_object(context, src, P, Q, closed, d):
    """Si le contour P de `src` est un cercle ou un arc, crée son décalage Q comme vrai cercle / arc (rayon exact r ± d).
    Retourne False si P n'en est pas un : le décalage reste alors une polyligne."""
    try:
        Pn = np.array([tuple(q) for q in P], dtype=np.float64)
        Qn = np.array([tuple(q) for q in Q], dtype=np.float64)
        if len(Pn) < 6 or len(Qn) < 6:
            return False
        fp = fit_circle_points(Pn)
        fq = fit_circle_points(Qn)
        if fp is None or fq is None:
            return False
        c, r, n, e1, e2 = fp
        cq, rq = fq[0], fq[1]
        if np.linalg.norm(np.asarray(cq) - np.asarray(c)) > 1e-3 * max(r, 1e-9):
            return False
        cen = src.get("dessin_centre")
        if cen is not None and len(src.data.splines) == 1 and src.data.splines[0].type == 'BEZIER':
            # rayon exact : distance des points d'ancrage au centre enregistré (les échantillons, eux, sont à ±0,0004 %)
            mw = src.matrix_world
            cw = mw @ Vector(tuple(cen))
            r = float(np.mean([(mw @ bp.co - cw).length for bp in src.data.splines[0].bezier_points]))
            c = np.array(cw, dtype=np.float64)
        r_new = r + d if rq > r else r - d
        if r_new <= 1e-9:
            return False
        e1, e2 = np.asarray(e1, dtype=np.float64), np.asarray(e2, dtype=np.float64)
        dq = Pn - c          # angles lus sur l'arc d'origine : ses extrémités sont exactes (celles de la polyligne décalée
        ang = np.arctan2(dq @ e2, dq @ e1)     # sont tournées d'une demi-corde)
        if closed:
            t0, sweep = 0.0, TAU
        else:
            steps = np.diff(ang)
            steps = (steps + math.pi) % (2 * math.pi) - math.pi
            t0, sweep = float(ang[0]), float(steps.sum())
            if abs(sweep) < 1e-6:
                return False
        build_bezier_arc(context, "Offset", Vector(tuple(c)), Vector(tuple(e1)), Vector(tuple(e2)), r_new, t0, sweep, bool(closed))
        return True
    except (ValueError, TypeError, AttributeError, ReferenceError, np.linalg.LinAlgError):
        return False


class DESSIN_OT_offset_edge(DessinEdgeRound):
    bl_idname = "dessin.offset_edge"
    bl_label = "Offset Edge"
    bl_description = ("Parallel copy of edges or curves: click the edges (or a curve) or drag a box, Enter, then move the mouse "
                      "to choose the side and type the distance. In Edit mode the selected edges are used")

    TITLE = "Offset Edge"
    NUMFIELDS = 1
    STATE = OFFSET_STATE
    CHAMFER = True      # pas de segments / flèches ↑ ↓

    # ---- sélection : meshes et courbes (une courbe entière à la fois) ----
    def candidates(self, context):
        # tous les objets visibles (pas seulement ceux déjà sélectionnés) : on peut piocher plusieurs formes à la zone
        return [o for o in context.view_layer.objects if o.type in {'MESH', 'CURVE'} and o.visible_get()]

    def geometry(self, obj):
        if obj.name in self.geo:
            return self.geo[obj.name]
        g = curve_edge_geometry(obj) if obj.type == 'CURVE' else mesh_edge_geometry(obj)
        self.geo[obj.name] = g
        return g

    def all_edges(self, obj):
        g = self.geometry(obj)
        return range(len(g[1])) if g is not None else range(0)

    def click(self, context):
        if self.phase == 'radius':
            self.finish_shape(context)
            return
        hit = self.pick_edge(context)
        if hit is None:
            return
        obj, i = hit
        s = self.sel.setdefault(obj.name, set())
        if obj.type == 'CURVE':
            if s:
                s.clear()
            else:
                s.update(self.all_edges(obj))
        elif i in s:
            s.discard(i)
        else:
            s.add(i)
        self.refresh(context)

    def box_select(self, context, remove):
        before = {k: len(v) for k, v in self.sel.items()}
        n = super().box_select(context, remove)
        for name, s in self.sel.items():
            obj = bpy.data.objects.get(name)
            if obj is None or obj.type != 'CURVE':
                continue
            if remove and len(s) < before.get(name, 0):
                s.clear()
            elif not remove and len(s) > before.get(name, 0):
                s.update(self.all_edges(obj))
        return n

    # ---- phase « distance » ----
    def begin_radius(self, context):
        if not self.total_selected():
            return False
        self.phase = 'radius'
        self.anchor = self.cur.copy() if self.cur is not None else Vector()
        self.points = [self.anchor.copy()]
        self.typed = ['', '', '']
        self.refresh(context)
        return True

    def prompt(self):
        if self.phase == 'pick':
            return (f"click the edges / a curve or drag a box ({self.total_selected()} selected), then Enter   "
                    "[box to the right: inside, to the left: touching, Ctrl/Cmd: deselect]")
        return "move the mouse to choose the side and the distance, or type the distance   (click / Enter: confirm)"

    def source_chains(self):
        """[(nom objet, points, fermée)] des arêtes choisies."""
        out = []
        for name, idx in self.sel.items():
            obj = bpy.data.objects.get(name)
            g = self.geometry(obj) if obj is not None else None
            if g is None or not idx:
                continue
            for P, closed in edge_chains(g[0], g[1], sorted(idx)):
                out.append((name, P, closed))
        return out

    def offset_chains(self):
        """[(nom objet, points décalés, fermée)] d'après la souris (côté) et la saisie (distance)."""
        fallback = plane_axes(self.axis)[2]
        t = self.typed_value(0)
        res = []
        self._collapsed = False
        for name, P, closed in self.source_chains():
            n = chain_normal(P, closed, fallback)
            seg, c = nearest_on_chain(P, closed, self.cur)
            m = len(P)
            tvec = P[(seg + 1) % m] - P[seg]
            if tvec.length < 1e-12:
                continue
            tvec.normalize()
            left = n.cross(tvec)
            v = self.cur - c
            v -= n * v.dot(n)
            side = 1.0 if v.dot(left) >= 0 else -1.0
            d = abs(t) if t is not None else v.length
            if d < 1e-9:
                continue
            Q = offset_polyline(P, closed, n, side * d)
            if offset_collapsed(P, closed, Q, d):      # distance trop grande pour la forme : pas de décalage (comme « Cannot offset »)
                self._collapsed = True
                continue
            res.append((name, Q, closed, d, P))
        return res

    def compute(self):
        if self.phase == 'pick':
            self.preview_extra = []
            return super().compute()
        self.hilite = []
        self.preview_extra = []
        if self.cur is None:
            return [], [], "", None
        res = self.offset_chains()
        for _nm, Q, closed, _d, _P in res:
            self.preview_extra.append(Q + [Q[0]] if closed else Q)
        guides = self.edge_lines((nm, s) for nm, s in self.sel.items())[:3000]
        info = f"distance {self.fmt(res[0][3])}" if res else ("distance too large: the shape would collapse" if getattr(self, "_collapsed", False) else "distance 0")
        return [], guides, info, ("offset", res) if res else None

    def apply_preview(self):
        pass

    def restore_all(self):
        self.geo = {}

    def finish_shape(self, context):
        if self.phase != 'radius' or self.cur is None:
            return
        res = self.offset_chains()
        if not res:
            self.report({'WARNING'}, "Cannot offset: the distance is too large for this shape" if getattr(self, "_collapsed", False) else "Distance is zero")
            return
        self.STATE["dist"] = res[0][3]
        by_obj = {}
        src_of = {}
        for name, Q, closed, _d, P in res:
            by_obj.setdefault(name, []).append((Q, closed))
            src_of.setdefault(name, []).append((P, closed))
        self.split_faces = 0
        split_curves = []
        for name in list(by_obj):
            src = bpy.data.objects.get(name)
            if src is None or src.type != 'MESH':
                continue
            # contour fermé d'une face, décalé vers l'intérieur : la face est découpée (anneau + face intérieure), comme SketchUp.
            # La courbe décalée est aussi créée, comme dans Rhino : la ligne reste visible et sélectionnable (sans elle, la
            # découpe se fond dans la face et ne réapparaît qu'avec PushPull)
            rest = []
            for (Q, closed), (P, _c) in zip(by_obj[name], src_of.get(name, [])):
                if closed and imprint_offset(src, P, Q):
                    self.split_faces += 1
                    split_curves.append((Q, closed))
                else:
                    rest.append((Q, closed))
            by_obj[name] = rest
        if split_curves and not self.reenter_edit:
            build_polylines(context, "Offset", split_curves)
        if self.split_faces:
            self.report({'INFO'}, f"{self.split_faces} face(s) split: PushPull the ring to raise a wall")
        for name, chains in by_obj.items():
            src = bpy.data.objects.get(name)
            if src is None or not chains:
                continue
            if src.type == 'CURVE':
                # cercle ou arc : le décalage est un vrai cercle / arc de rayon r ± d (comme Rhino), pas une polyligne
                rest = []
                for (Q, closed), (P, _c) in zip(chains, src_of.get(name, [])):
                    if not offset_arc_object(context, src, P, Q, closed, self.STATE["dist"]):
                        rest.append((Q, closed))
                if rest:
                    build_polylines(context, "Offset", rest)
            elif self.reenter_edit:
                self.append_edges(src, chains)
            else:
                build_edge_object(context, "Offset", chains)
        self.committed = True
        self.finished = True

    @staticmethod
    def append_edges(obj, chains):
        """Ajoute les chaînes (coordonnées monde) au maillage de l'objet (en mode Objet : on retourne ensuite en Édition)."""
        inv = obj.matrix_world.inverted()
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        for Q, closed in chains:
            vs = [bm.verts.new(inv @ q) for q in Q]
            pairs = list(zip(vs, vs[1:])) + ([(vs[-1], vs[0])] if closed and len(vs) > 2 else [])
            for a, b in pairs:
                try:
                    bm.edges.new((a, b))
                except ValueError:
                    pass
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()


def build_polylines(context, name, chains):
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    for Q, closed in chains:
        sp = cu.splines.new('POLY')
        sp.points.add(len(Q) - 1)
        for pt, q in zip(sp.points, Q):
            pt.co = (q.x, q.y, q.z, 1.0)
        sp.use_cyclic_u = closed
    return _link_object(context, name, cu)


def build_edge_object(context, name, chains):
    verts, edges = [], []
    for Q, closed in chains:
        base = len(verts)
        verts += [tuple(q) for q in Q]
        edges += [(base + i, base + i + 1) for i in range(len(Q) - 1)]
        if closed and len(Q) > 2:
            edges.append((base + len(Q) - 1, base))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, edges, [])
    me.update()
    return _link_object(context, name, me)


def _late_imports():
    """Noms définis dans des modules chargés après celui-ci : ils ne servent qu'à l'exécution des outils."""
    global _line_meet, _segments_hit_rect, fit_circle_points, imprint_offset, objects_screen_bounds, ray_cast_opaque
    from .selection import _segments_hit_rect, objects_screen_bounds, ray_cast_opaque
    from .dimensions import fit_circle_points
    from .curve_edit import _line_meet
    from .pushpull import imprint_offset
