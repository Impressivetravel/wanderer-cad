"""Wanderer CAD : Transformations : Move, Copy, Rotate, Scale, Mirror, Array, Cut."""

import bmesh
import bpy
import math
import numpy as np
import time
from bpy_extras.view3d_utils import region_2d_to_origin_3d, region_2d_to_vector_3d
from mathutils import Matrix, Vector

from .core import TAU, arc_samples, idle_tool, plane_axes, pref
from .snapping import (
    collect_snap_points, curve_edit_apply, curve_edit_selection, edit_selection, exclude_snap, merge_snap_data,
)
from .drawing import find_snap_in, find_window_region, px_scale, region_rv3d
from .base import DessinBase, view_height
from .subd import duplicate_hierarchy, expand_groups


class _PendingMove:
    """Copie légère d'un événement souris (l'événement de Blender ne doit pas être conservé)."""
    type = 'MOUSEMOVE'
    value = 'NOTHING'

    def __init__(self, e):
        self.mouse_x, self.mouse_y = e.mouse_x, e.mouse_y
        self.shift, self.ctrl, self.alt, self.oskey = e.shift, e.ctrl, e.alt, e.oskey


def has_shear(M, tol=1e-6):
    """True si la matrice monde M ne se réduit pas à position + rotation + échelle (cisaillement)."""
    try:
        loc, rot, sca = M.decompose()
        R = Matrix.LocRotScale(loc, rot, sca)
        ref = max(1.0, max(abs(v) for row in M for v in row))
        return max(abs(R[i][j] - M[i][j]) for i in range(4) for j in range(4)) > tol * ref
    except (ValueError, ZeroDivisionError):
        return False


def commit_world_xform(obj, xform):
    """Applique xform (monde) à obj. Si le résultat comporte un cisaillement (Scale 1D oblique, rotation d'un objet mis
    à l'échelle...), matrix_world ne peut pas le conserver : on reporte alors la transformation dans les données de l'objet."""
    mw0 = obj.matrix_world.copy()
    M = xform @ mw0
    kids = [(c, c.matrix_world.copy()) for c in obj.children]
    if not has_shear(M) or obj.type not in {'MESH', 'CURVE', 'SURFACE', 'LATTICE'} or obj.data is None:
        obj.matrix_world = M
        return
    try:
        if obj.data.users > 1:
            obj.data = obj.data.copy()
        D = mw0.inverted() @ M          # coordonnées locales : v' = D v, l'objet garde sa matrice d'origine
        obj.data.transform(D)
        if obj.type == 'MESH' and D.determinant() < 0:
            bm = bmesh.new()
            bm.from_mesh(obj.data)
            bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
            bm.to_mesh(obj.data)
            bm.free()
        obj.data.update()
    except (RuntimeError, ValueError, ReferenceError, AttributeError):
        obj.matrix_world = M
        return
    for c, cmw in kids:                 # les enfants ne suivent plus le parent : on les place un par un
        try:
            c.matrix_world = cmw
            commit_world_xform(c, xform)
        except ReferenceError:
            pass


class DessinTransform(DessinBase):
    """Base des outils qui transforment la sélection (déplacer, rotation, échelle)."""

    NEEDED = 2
    NUMFIELDS = 1
    HAS_CENTER = True  # C = copie
    NO_SELECTION = "Select the objects to transform first"
    EDIT_OK = True
    crv = False
    CURVE_EDIT_OK = False     # Move / Rotate / Scale : en édition de courbe, seuls les points sélectionnés bougent

    def edit_sel(self, context):
        return curve_edit_selection(context) if getattr(self, "crv", False) else edit_selection(context)

    def invoke(self, context, event):
        self.crv = context.mode == 'EDIT_CURVE' and self.CURVE_EDIT_OK
        self.edit = context.mode == 'EDIT_MESH' or self.crv
        if self.edit:
            self.items = self.edit_sel(context)
            self.selecting = not self.items
        else:
            sel = expand_groups(context, context.selected_objects)
            self.selecting = not sel
            if sel:
                selected = set(sel)
                self.items = [(o, o.matrix_world.copy()) for o in sel if o.parent not in selected]
            else:
                self.items = []
        self.committed = False
        self.ortho = False
        self.ghost_pts = None
        self.ghost_batch = None
        self.box = None
        self._sel_press = None
        self._sel_flags = (False, False)
        result = super().invoke(context, event)
        if 'RUNNING_MODAL' in result:
            if self.selecting:
                if event.type == 'LEFTMOUSE' and event.value == 'PRESS' and self.tool_id and self.region is not None:
                    # le clic qui a lancé l'outil commence déjà un clic ou une zone de sélection
                    self._sel_press = (event.mouse_x - self.region.x, event.mouse_y - self.region.y)
                    self._sel_flags = (event.shift, event.ctrl)
                self.refresh(context)
            else:
                self.capture_ghost()
        return result

    # ---- phase de sélection (comme « Sélectionnez les objets » de Rhino) ----
    def select_at(self, context, event):
        region = find_window_region(self.area, event.mouse_x, event.mouse_y)
        if region is None:
            return
        try:
            with context.temp_override(area=self.area, region=region):
                bpy.ops.view3d.select(location=(event.mouse_x - region.x, event.mouse_y - region.y),
                                      toggle=True)
        except (RuntimeError, TypeError):
            pass

    def select_all_visible(self, context):
        if self.edit:
            try:
                with context.temp_override(area=self.area, region=self.region):
                    (bpy.ops.curve if self.crv else bpy.ops.mesh).select_all(action='SELECT')
            except (RuntimeError, TypeError):
                pass
            return
        for o in context.view_layer.objects:
            try:
                if o.visible_get() and not o.select_get():
                    o.select_set(True)
            except RuntimeError:
                pass

    def selected_now(self, context):
        if self.edit:
            return self.edit_sel(context)
        out = []
        for o in context.view_layer.objects:
            try:
                if o.select_get() and o.visible_get():
                    out.append(o)
            except RuntimeError:
                pass
        return expand_groups(context, out)

    def refresh_selecting(self, context):
        sel = self.selected_now(context)
        n = sum(len(t[1]) for t in sel) if self.edit else len(sel)
        what = "points" if self.crv else "vertices" if self.edit else "objects"
        txt = (f"{self.TITLE} : select the {what} (click: add, drag: box, Shift+click: toggle, Ctrl/Cmd+click: remove, A: all)   |   "
               f"{n} selected   |   Enter/Space: confirm   Esc: exit")
        try:
            set_prompt(self.area, txt)
            self.area.tag_redraw()
        except ReferenceError:
            pass

    def begin_transform(self, context, event):
        """Fin de la sélection : on passe au point de base. False si rien n'est sélectionné."""
        sel = self.selected_now(context)
        if not sel:
            return False
        if self.edit:
            self.items = sel
        else:
            selected = set(sel)
            self.items = [(o, o.matrix_world.copy()) for o in sel if o.parent not in selected]
        self.selecting = False
        self.committed = False
        self.capture_ghost()
        DessinBase.reset_state(self)
        self.update_cursor(context, event)
        return True

    def click_select(self, context, x, y, shift, ctrl):
        """Clic de la phase de sélection : ajoute (Maj : bascule, Ctrl : retire) l'objet / l'élément sous la souris."""
        if self.edit:
            region = self.region
            try:
                with context.temp_override(area=self.area, region=region):
                    bpy.ops.view3d.select(location=(int(x), int(y)), extend=not (shift or ctrl),
                                          toggle=shift and not ctrl, deselect=ctrl, deselect_all=False)
            except (RuntimeError, TypeError):
                pass
            return
        hit = pick_object_at(context, self.area, self.region, x, y)
        if hit is None:
            return
        obj = hit[0]
        try:
            if ctrl:
                obj.select_set(False)
            elif shift:
                obj.select_set(not obj.select_get())
            else:
                obj.select_set(True)
            if obj.select_get():
                context.view_layer.objects.active = obj
        except (RuntimeError, ReferenceError):
            pass

    def box_select_objects(self, context, box, ctrl):
        """Zone de sélection (vers la droite : entièrement dedans, vers la gauche : touchés) ; ajoute à la sélection."""
        class _Box:
            pass
        helper = _Box()
        helper.area, helper.region = self.area, self.region
        helper.select_box_edit = lambda c, rect, crossing, ev: DESSIN_OT_selection_boite.select_box_edit(helper, c, rect, crossing, ev)
        ev = _Box()
        ev.shift, ev.ctrl = not ctrl, ctrl
        DESSIN_OT_selection_boite.select_box(helper, context, box, ev)

    def modal_select(self, context, event):
        if self.area is None or context.area is None:
            self.cleanup(context)
            return {'CANCELLED'}
        if self.tool_id and self.tool_changed(context):
            self.cleanup(context)
            return {'CANCELLED', 'PASS_THROUGH'}
        et = event.type
        inside = (find_window_region(self.area, event.mouse_x, event.mouse_y) is not None
                  and not self.mouse_over_ui(event))
        region = find_window_region(self.area, event.mouse_x, event.mouse_y)

        if et in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            if inside:
                if self._sel_press is not None and region is not None:
                    mx, my = event.mouse_x - region.x, event.mouse_y - region.y
                    px0, py0 = self._sel_press
                    if self.box is not None or math.hypot(mx - px0, my - py0) > 5.0 * px_scale():
                        self.box = (px0, py0, mx, my)
                self.refresh_selecting(context)  # le compteur suit aussi les changements faits ailleurs
            return {'RUNNING_MODAL'} if inside else {'PASS_THROUGH'}
        if et == 'LEFTMOUSE' and event.value == 'RELEASE' and self._sel_press is not None:
            shift, ctrl = self._sel_flags
            press, box = self._sel_press, self.box
            self._sel_press = None
            self.box = None
            if region is not None:
                if box is not None:
                    self.box_select_objects(context, box, ctrl)
                else:
                    self.click_select(context, press[0], press[1], shift, ctrl)
            self.refresh(context)
            return {'RUNNING_MODAL'}
        if not inside:
            return {'PASS_THROUGH'}
        if event.value != 'PRESS':
            return {'RUNNING_MODAL'} if et == 'LEFTMOUSE' else {'PASS_THROUGH'}

        plain = not (event.ctrl or event.alt or event.oskey)
        if et == 'LEFTMOUSE' and not event.alt and not event.oskey:
            self._sel_press = (event.mouse_x - region.x, event.mouse_y - region.y)
            self._sel_flags = (event.shift, event.ctrl)
            self.box = None
            return {'RUNNING_MODAL'}
        if et == 'ESC':
            return self.exit(context)
        if et in {'RET', 'NUMPAD_ENTER', 'SPACE'}:
            if not self.begin_transform(context, event):
                return self.exit(context)
            return {'RUNNING_MODAL'}
        if et == 'A' and plain:
            self.select_all_visible(context)
            self.refresh(context)
            return {'RUNNING_MODAL'}
        if et == 'TAB':
            return {'RUNNING_MODAL'}
        return {'PASS_THROUGH'}

    def modal(self, context, event):
        if (not self.selecting and not self.points and event.type == 'LEFTMOUSE'
                and event.value == 'PRESS' and not self.selected_now(context)):
            # la sélection a été vidée pendant l'attente : on repasse en phase de sélection
            self.restore()
            self.items = []
            self.ghost_pts = None
            self.ghost_batch = None
            self.selecting = True
        if self.selecting:
            return self.modal_select(context, event)
        if event.type not in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'} and getattr(self, "_pending", None) is not None:
            self.flush_pending(context)
        return super().modal(context, event)

    def update_cursor(self, context, event):
        self.ortho = bool(event.shift)
        if self.selecting:
            self.snap_screen = None
            self.snap_kind = None
            self.refresh(context)
            return
        if self.points and event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            now = time.monotonic()
            if now - getattr(self, "_t_move", 0.0) < getattr(self, "_gap", 0.022):      # objets lourds : on ne recalcule pas à chaque événement souris
                self._pending = _PendingMove(event)
                return
            self._t_move = now
            self._pending = None
            t0 = time.perf_counter()
            super().update_cursor(context, event)
            # le rythme s'adapte au coût réel d'une mise à jour (scène lourde : moins d'événements, plus fluide)
            cost = time.perf_counter() - t0
            self._cost = 0.6 * getattr(self, "_cost", cost) + 0.4 * cost
            self._gap = min(0.12, max(0.022, 1.3 * self._cost))
            return
        self._pending = None
        super().update_cursor(context, event)

    def flush_pending(self, context):
        p = getattr(self, "_pending", None)
        if p is not None and not self.selecting and self.area is not None:
            self._pending = None
            self._t_move = time.monotonic()
            super().update_cursor(context, p)

    def click(self, context):
        self.flush_pending(context)
        had_base = bool(self.points)
        if not self.points and not self.sync_selection(context):
            return
        DessinBase.click(self, context)
        if not had_base and len(self.points) == 1 and not self.edit and self.snap_on:
            # le point de base est posé : les objets déplacés ne s'accrochent plus à eux-mêmes (bien plus fluide)
            names = set()
            for obj, _ in self.items:
                names.add(obj.name)
                names.update(c.name for c in obj.children_recursive)
            self.snap_exclude = names
            try:
                ghost = collect_snap_points(context, only=names)        # le fantôme (position d'origine) reste accrochable
                if exclude_snap(self.snap_data, names):
                    self.snap_ghost = ghost                             # sans nouveau calcul : on masque les objets déplacés
                else:
                    self.collect_snaps(context)
                    self.snap_data = merge_snap_data(self.snap_data, ghost)
                    self.snap_pts, self.snap_hom, self.snap_kinds, self.snap_bias = self.snap_data
            except (RuntimeError, ReferenceError, ValueError):
                self.snap_exclude = None

    def find_snap(self, mx, my, region, rv3d):
        res = DessinBase.find_snap(self, mx, my, region, rv3d)
        ghost = getattr(self, "snap_ghost", None)
        if res is None and ghost is not None and self.snap_on:
            res = find_snap_in(ghost, mx, my, region, rv3d, ref=self.points[-1] if self.points else None)
        return res

    def capture_ghost(self, max_edges=40000):
        """Mémorise les arêtes (monde) des objets transformés pour afficher leur position initiale."""
        self.ghost_batch = None
        self.ghost_pts = None
        if self.edit:
            self.capture_ghost_edit()
            return
        try:
            dg = bpy.context.evaluated_depsgraph_get()
        except (RuntimeError, AttributeError):
            return
        objs = []
        for obj, _ in self.items:
            objs.append(obj)
            objs.extend(obj.children_recursive)
        chunks, total = [], 0
        total_v = 0
        for obj in objs:
            if obj.type not in {'MESH', 'CURVE', 'SURFACE', 'FONT'}:
                continue
            try:
                ev = obj.evaluated_get(dg)
                me = ev.to_mesh()
            except (RuntimeError, ReferenceError):
                continue
            try:
                nv, ne = len(me.vertices), len(me.edges)
                total_v += nv
                if nv == 0 or ne == 0 or total + ne > max_edges:
                    continue
                co = np.empty(nv * 3, dtype=np.float32)
                me.vertices.foreach_get('co', co)
                edges = np.empty(ne * 2, dtype=np.int32)
                me.edges.foreach_get('vertices', edges)
                mw = np.array(ev.matrix_world, dtype=np.float64)
                world = co.reshape(-1, 3).astype(np.float64) @ mw[:3, :3].T + mw[:3, 3]
                chunks.append(world[edges].astype(np.float32))
                total += ne
            finally:
                ev.to_mesh_clear()
        if chunks:
            self.ghost_pts = np.vstack(chunks)
        self.decide_light_preview(objs, total_v)

    def decide_light_preview(self, objs, total_v):
        """Sélection lourde (beaucoup de sommets ou d'objets) : aperçu par boîtes, les objets bougent au clic."""
        self.light = False
        self.light_boxes = None
        self.preview_xform = None
        if not pref("light_preview") or self.edit or not getattr(self, "LIGHT_OK", False):
            return
        scene_v = 0
        try:
            scene_v = sum(len(o.data.vertices) for o in bpy.context.view_layer.objects if o.type == 'MESH' and o.visible_get())
        except (ReferenceError, AttributeError, RuntimeError):
            pass
        if not (total_v > 150000 or len(objs) > 250 or (scene_v > 3000000 and total_v > 20000)):
            return
        edges = ((0, 1), (1, 3), (3, 2), (2, 0), (4, 5), (5, 7), (7, 6), (6, 4), (0, 4), (1, 5), (2, 6), (3, 7))
        pts = []
        for o in objs[:1500]:
            try:
                if o.type == 'EMPTY' or not o.bound_box:
                    continue
                mw = o.matrix_world
                cs = [mw @ Vector(c) for c in o.bound_box]
            except (ReferenceError, AttributeError):
                continue
            for a, b in edges:
                pts.append(tuple(cs[a]))
                pts.append(tuple(cs[b]))
        if pts:
            self.light = True
            self.light_boxes = np.array(pts, dtype=np.float32)
            self.light_batch = None

    def capture_ghost_edit(self):
        if self.crv:
            self.ghost_pts = None
            return
        chunks = []
        for obj, idx, w0 in self.items:
            try:
                bm = bmesh.from_edit_mesh(obj.data)
            except (ValueError, ReferenceError):
                continue
            pos = {i: w0[k] for k, i in enumerate(idx)}
            for e in bm.edges:
                a, b = e.verts[0].index, e.verts[1].index
                if a in pos and b in pos:
                    chunks.append((pos[a], pos[b]))
        if chunks:
            self.ghost_pts = np.array(chunks, dtype=np.float32).reshape(-1, 3)

    def edit_move(self, xform, duplicate=False):
        """Applique xform (monde) aux sommets sélectionnés d'origine ; duplicate : copie la géométrie."""
        X = np.array(xform, dtype=np.float64)
        if self.crv:        # courbe : on déplace les points sélectionnés (la copie n'existe pas pour les points de courbe)
            for obj, refs, w0 in self.items:
                curve_edit_apply(obj, refs, w0, X)
            return
        for obj, idx, w0 in self.items:
            try:
                bm = bmesh.from_edit_mesh(obj.data)
            except (ValueError, ReferenceError):
                continue
            bm.verts.ensure_lookup_table()
            mw = np.array(obj.matrix_world, dtype=np.float64)
            M = np.linalg.inv(mw) @ X
            if duplicate:
                verts = [bm.verts[i] for i in idx]
                vset = set(verts)
                geom = list(verts)
                geom += [e for e in bm.edges if e.verts[0] in vset and e.verts[1] in vset]
                geom += [f for f in bm.faces if all(v in vset for v in f.verts)]
                ret = bmesh.ops.duplicate(bm, geom=geom)
                new = [g for g in ret['geom'] if isinstance(g, bmesh.types.BMVert)]
                Mw = np.linalg.inv(mw) @ X @ mw
                for v in new:
                    p = Mw @ np.array((v.co.x, v.co.y, v.co.z, 1.0))
                    v.co = Vector((p[0], p[1], p[2]))
                if getattr(self, 'MIRRORS', False):
                    bmesh.ops.reverse_faces(bm, faces=[g for g in ret['geom'] if isinstance(g, bmesh.types.BMFace)])
                for g in ret['geom']:
                    g.select_set(False)
                bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=True)
                continue
            h = np.hstack((w0, np.ones((len(w0), 1)))) @ M.T
            for i, p in zip(idx, h):
                bm.verts[i].co = Vector((p[0], p[1], p[2]))
            bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=False)

    # ---- transformation en direct des objets sélectionnés ----
    def apply_live(self, xform):
        if self.edit:
            self.edit_move(xform)
            return
        for obj, mw in self.items:
            try:
                obj.matrix_world = xform @ mw
            except ReferenceError:
                pass

    def restore(self):
        if self.edit:
            self.edit_move(Matrix.Identity(4))
            return
        for obj, mw in self.items:
            try:
                obj.matrix_world = mw
            except ReferenceError:
                pass

    def refresh(self, context):
        if self.selecting:
            self.refresh_selecting(context)
            return
        super().refresh(context)
        if not self.points:
            return  # rien à appliquer (et on évite de relancer le graphe de dépendances à chaque mouvement)
        xform = Matrix.Identity(4)
        if self.cur is not None:
            _, _, _, spec = self.compute()
            if spec is not None:
                xform = spec[1]
        if getattr(self, "light", False) and not self.edit:
            self.preview_xform = xform       # aperçu par boîtes : on ne touche pas au graphe de dépendances
            return
        self.apply_live(xform)

    def sync_selection(self, context):
        """La sélection a pu changer pendant que l'outil attendait : on la relit au premier clic."""
        if self.edit:
            new = self.edit_sel(context)
            if not new:
                self.report({'WARNING'}, self.NO_SELECTION)
                return False
            same = (len(new) == len(self.items)
                    and all(a[0] == b[0] and a[1] == b[1] and np.allclose(a[2], b[2])
                            for a, b in zip(new, self.items)))
            if not same:
                self.items = new
                self.capture_ghost()
            return True
        sel = expand_groups(context, context.selected_objects)
        if not sel:
            self.report({'WARNING'}, self.NO_SELECTION)
            return False
        selected = set(sel)
        new = [(o, o.matrix_world.copy()) for o in sel if o.parent not in selected]
        old = {o.name: m for o, m in self.items}
        same = len(new) == len(old) and all(o.name in old and old[o.name] == m for o, m in new)
        if not same:
            self.items = new
            self.capture_ghost()
        return True

    def build(self, context, spec):
        xform = spec[1]
        if self.edit:
            if self.center:
                self.restore()
                self.edit_move(xform, duplicate=True)
            else:
                self.apply_live(xform)
            self.committed = True
            return None
        if self.center:
            for obj, mw in self.items:
                dup = duplicate_hierarchy(obj)
                dup.matrix_world = mw
                commit_world_xform(dup, xform)
            self.restore()
        else:
            self.restore()
            for obj, mw in self.items:
                try:
                    commit_world_xform(obj, xform)
                except ReferenceError:
                    pass
        self.committed = True
        return None

    def reset_state(self):
        was_committed = self.committed
        self._pending = None
        if getattr(self, "snap_exclude", None):
            self.snap_exclude = None
            self.snap_ghost = None
            try:
                self.collect_snaps(bpy.context)
            except (RuntimeError, ReferenceError, AttributeError):
                pass
        if not was_committed:
            self.restore()
        self.committed = False
        try:
            if self.edit:
                self.items = self.edit_sel(bpy.context)
            else:
                self.items = [(o, o.matrix_world.copy()) for o, _ in self.items]
        except ReferenceError:
            pass
        if was_committed and not self.finished:
            self.capture_ghost()
        super().reset_state()

    def cleanup(self, context):
        try:
            self.restore()
        except (ValueError, RuntimeError, ReferenceError):
            pass
        super().cleanup(context)

    def after_finish(self, context):
        """Comme sur Rhino : la commande terminée relâche la sélection et rend la main."""
        try:
            if not pref("esc_deselect"):
                pass
            elif self.crv:
                bpy.ops.curve.select_all(action='DESELECT')
            elif self.edit:
                bpy.ops.mesh.select_all(action='DESELECT')
            else:
                bpy.ops.object.select_all(action='DESELECT')
        except RuntimeError:
            pass
        if self.tool_id:
            try:
                idle_tool()
            except (RuntimeError, TypeError):
                pass


class MoveLogic:
    """Logique commune de Déplacer et Copier (classe simple, non enregistrée dans Blender)."""

    TITLE = "Move"
    NEEDED = 2
    PLANAR = False  # les points accrochés et les lignes de repérage gardent leur hauteur
    NO_SELECTION = "Select the objects to move first"

    def prompt(self):
        suffix = " (copy)" if self.center else ""
        if not self.points:
            return "base point" + suffix + "   [C: copy]"
        return ("destination point" + suffix
                + "   (Shift: orthogonal, or type the distance then Enter)")

    def delta_vec(self):
        u, v, _ = plane_axes(self.axis)
        d = self.cur - self.points[0]
        if not self.ortho:
            vec = d.copy()
            t = self.typed_value(0)
            if t is not None:
                vec = (d / d.length if d.length > 1e-9 else u.copy()) * t
            return vec
        du, dv = d.dot(u), d.dot(v)
        if self.ortho:
            if abs(du) >= abs(dv):
                dv = 0.0
            else:
                du = 0.0
        vec = u * du + v * dv
        t = self.typed_value(0)
        if t is not None:
            length = vec.length
            direction = vec / length if length > 1e-9 else u
            vec = direction * t
        return vec

    def compute(self):
        if not self.points or self.cur is None:
            return [], [], "", None
        vec = self.delta_vec()
        if vec.length < 1e-9:
            return [], [], "", None
        o = self.points[0]
        info = (f"Distance {self.fmt(vec.length)}   "
                f"Δ ({self.fmt(vec.x)}, {self.fmt(vec.y)}, {self.fmt(vec.z)})")
        return [], [[o, o + vec]], info, ("xform", Matrix.Translation(vec))


class DESSIN_OT_deplacer(MoveLogic, DessinTransform):
    CURVE_EDIT_OK = True
    LIGHT_OK = True
    bl_idname = "dessin.deplacer"
    bl_label = "Move"
    bl_description = ("Moves the selection: base point then destination point, with snapping (Shift: orthogonal, C: copy, or type the distance)")


class DESSIN_OT_copier(MoveLogic, DessinTransform):
    LIGHT_OK = True
    bl_idname = "dessin.copier"
    bl_label = "Copy"
    bl_description = ("Copies the selection: base point then as many destination points as you want (Shift: orthogonal, or type a distance then Enter). Enter / Esc: finish")

    TITLE = "Copy"
    HAS_CENTER = False  # c'est toujours une copie
    NO_SELECTION = "Select the objects to copy first"

    def invoke(self, context, event):
        self.count = 0
        result = super().invoke(context, event)
        self.center = True
        if 'RUNNING_MODAL' in result:
            self.refresh(context)
        return result

    def prompt(self):
        if getattr(self, "selecting", False):
            return ""
        if not self.points:
            return "base point"
        n = getattr(self, "count", 0)
        done = (f" - {n} copies" if n > 1 else " - 1 copy") if n else ""
        return ("destination point" + done
                + "   (Shift: orthogonal, or type the distance then Enter; Enter/Esc: finish)")

    def finish_shape(self, context):
        _, _, _, spec = self.compute()
        if spec is None:
            self.report({'WARNING'}, "Copie invalide")
            return
        self.build(context, spec)      # crée la copie et remet les originaux en place
        self.count += 1
        self.committed = False
        self.typed = ['', '']
        self.preview = []
        self.guides = []
        self.points = self.points[:1]  # on garde le point de base pour la copie suivante
        self.lock = None

    def exit(self, context):
        self.finished = self.count > 0
        return super().exit(context)

    def modal(self, context, event):
        if (not getattr(self, "selecting", False) and event.value == 'PRESS' and self.count
                and self.area is not None and context.area is not None):
            if event.type == 'ESC':
                return self.exit(context)
            if (event.type in {'RET', 'NUMPAD_ENTER', 'SPACE'} and not any(self.typed)
                    and find_window_region(self.area, event.mouse_x, event.mouse_y) is not None
                    and not self.mouse_over_ui(event)):
                return self.exit(context)
        return super().modal(context, event)


class DESSIN_OT_rotation(DessinTransform):
    CURVE_EDIT_OK = True
    LIGHT_OK = True
    bl_idname = "dessin.rotation"
    bl_label = "Rotate"
    bl_description = ("Rotates the selection: center, reference point then target point, or typed angle (R: Reference = reference angle by two points then new angle; Shift: 15° steps, C: copy)")

    TITLE = "Rotate"
    NEEDED = 3
    LOCK_OK = False
    NO_SELECTION = "Select the objects to rotate first"

    def invoke(self, context, event):
        self.refrot = False
        self.NEEDED = 3
        return super().invoke(context, event)

    def reset_state(self):
        self.refrot = False
        self.NEEDED = 3
        DessinTransform.reset_state(self)

    def can_confirm_typed(self):
        if getattr(self, "refrot", False):
            return len(self.points) == 3       # Entrée valide le nouvel angle tapé
        return len(self.points) >= 1

    def handle_typing(self, event):
        if getattr(self, "refrot", False) and len(self.points) < 3:
            if event.value == 'PRESS' and event.unicode and event.unicode in "0123456789.,-":
                return True        # pas de saisie avant l'étape « nouvel angle » (les chiffres n'atteignent pas Blender)
            return False
        return DessinTransform.handle_typing(self, event)

    def click(self, context):
        if getattr(self, "refrot", False) and len(self.points) < 3:
            self.typed = ['', '', '']
        DessinTransform.click(self, context)

    def modal(self, context, event):
        # R : Référence (comme AutoCAD) : l'angle de référence est donné par deux points quelconques
        if (event.type == 'R' and event.value == 'PRESS'
                and not (event.ctrl or event.alt or event.oskey or event.shift)
                and find_window_region(self.area, event.mouse_x, event.mouse_y) is not None
                and not self.mouse_over_ui(event)):
            if not getattr(self, "selecting", False) and len(self.points) <= 1 and not any(self.typed):
                self.refrot = not getattr(self, "refrot", False)
                self.NEEDED = 4 if self.refrot else 3
                self.refresh(context)
            return {'RUNNING_MODAL'}
        return DessinTransform.modal(self, context, event)

    def prompt(self):
        suffix = " (copy)" if self.center else ""
        n = len(self.points)
        ref = getattr(self, "refrot", False)
        if n == 0:
            return "center of rotation" + suffix + "   [C: copy, R: reference " + ("ON" if ref else "off") + "]"
        if ref:
            if n == 1:
                return "reference angle: first point   [R: back to normal]"
            if n == 2:
                return "reference angle: second point"
            return "new angle: point, or type the angle then Enter   (Shift: 15° steps)"
        if n == 1:
            return "angle (type then Enter) or first reference point   [R: reference by two points]"
        return "second point   (Shift: 15° steps, or type the angle then Enter)"

    def compute(self):
        n = len(self.points)
        if n == 0 or self.cur is None:
            return [], [], "", None
        c = self.points[0]
        u, v, _ = plane_axes(self.axis)
        axis_vec = u.cross(v).normalized()
        typed = self.typed_raw(0)  # degrés

        if getattr(self, "refrot", False) and n >= 2:
            # Référence (AutoCAD) : angle de référence = direction p1 -> p2, nouvel angle = direction centre -> curseur
            # (ou angle tapé, absolu, depuis l'axe X du plan) ; la rotation est leur différence
            p1 = self.points[1]
            if n == 2:
                d = self.cur - p1
                info = f"Reference angle {math.degrees(math.atan2(d.dot(v), d.dot(u))) % 360:.2f}°" if d.length > 1e-9 else ""
                return [], [[p1, self.cur]], info, None
            d0 = self.points[2] - p1
            if math.hypot(d0.dot(u), d0.dot(v)) < 1e-9:
                return [], [], "", None
            ref_a = math.atan2(d0.dot(v), d0.dot(u))
            e = self.cur - c
            new_a = math.atan2(e.dot(v), e.dot(u))
            if self.ortho:
                step = math.radians(15.0)
                new_a = round(new_a / step) * step
            if typed is not None:
                new_a = math.radians(typed)
            angle = (new_a - ref_a + math.pi) % TAU - math.pi
            radius = max(math.hypot(e.dot(u), e.dot(v)), d0.length, 1e-6)
            guides = [[p1, self.points[2]], [c, c + (u * math.cos(new_a) + v * math.sin(new_a)) * radius]]
            if abs(angle) < 1e-9:
                return [], guides, "", None
            xform = Matrix.Translation(c) @ Matrix.Rotation(angle, 4, axis_vec) @ Matrix.Translation(-c)
            prev = arc_samples(c, u, v, radius, ref_a, angle)
            info = (f"Reference {math.degrees(ref_a) % 360:.2f}°  ->  new {math.degrees(new_a) % 360:.2f}°"
                    f"   Rotation {math.degrees(angle):.2f}°")
            return prev, guides, info, ("xform", xform)
        if getattr(self, "refrot", False) and n == 1:
            return [], [[c, self.cur]], "", None

        if n == 1:
            if typed is None:
                return [], [[c, self.cur]], "", None
            e = self.cur - c
            radius = math.hypot(e.dot(u), e.dot(v))
            if radius < 1e-9:
                radius = 1.0
            a0 = 0.0
            angle = math.radians(typed)
            guides = [[c, c + u * radius]]
        else:
            p1 = self.points[1]
            d0 = p1 - c
            radius = math.hypot(d0.dot(u), d0.dot(v))
            if radius < 1e-9:
                return [], [], "", None
            a0 = math.atan2(d0.dot(v), d0.dot(u))
            e = self.cur - c
            a1 = math.atan2(e.dot(v), e.dot(u))
            angle = (a1 - a0 + math.pi) % TAU - math.pi
            if self.ortho:
                step = math.radians(15.0)
                angle = round(angle / step) * step
            if typed is not None:
                angle = math.radians(typed)
            guides = [[c, p1], [c, self.cur]]

        if abs(angle) < 1e-9:
            return [], guides, "", None
        xform = (Matrix.Translation(c) @ Matrix.Rotation(angle, 4, axis_vec)
                 @ Matrix.Translation(-c))
        prev = arc_samples(c, u, v, radius, a0, angle)
        info = f"Angle {math.degrees(angle):.2f}°"
        return prev, guides, info, ("xform", xform)


class ScaleBase(DessinTransform):
    CURVE_EDIT_OK = True
    """Logique commune de Scale, Scale2D et Scale1D (classe non enregistrée)."""
    LIGHT_OK = True
    START_MODE = 0
    NEEDED = 3
    PLANAR = False  # les références accrochées gardent leur hauteur (points alignés sur Z)
    HAS_MODE = True
    MODES = ("3D", "2D (in the plane)", "1D (along the reference)")
    NO_SELECTION = "Select the objects to scale first"

    def invoke(self, context, event):
        self.mode = self.START_MODE
        self.refmode = False
        self.acadref = False
        self.NEEDED = 3
        return super().invoke(context, event)

    def reset_state(self):
        self.refmode = False
        self.acadref = False
        self.NEEDED = 3
        DessinTransform.reset_state(self)

    def can_confirm_typed(self):
        if self.refmode or getattr(self, "acadref", False):
            return len(self.points) == 3   # Entrée valide la nouvelle longueur tapée
        return len(self.points) >= 1

    def handle_typing(self, event):
        if (self.refmode or getattr(self, "acadref", False)) and len(self.points) < 3:
            # pas de saisie avant l'étape « nouvelle longueur » (on avale les chiffres pour ne pas déclencher Blender)
            if event.value == 'PRESS' and event.unicode and event.unicode in "0123456789.,-":
                return True
            return False
        return DessinTransform.handle_typing(self, event)

    def click(self, context):
        if (self.refmode or getattr(self, "acadref", False)) and len(self.points) < 3:
            self.typed = ['', '', '']
        DessinTransform.click(self, context)

    def modal(self, context, event):
        # R : référence libre (avant ou après le point de base) ; la touche ne doit jamais atteindre Rotate de Blender
        if (event.type == 'R' and event.value == 'PRESS'
                and not (event.ctrl or event.alt or event.oskey or event.shift)
                and find_window_region(self.area, event.mouse_x, event.mouse_y) is not None
                and not self.mouse_over_ui(event)):
            if not getattr(self, "selecting", False) and len(self.points) <= 1 and not any(self.typed):
                # R : normal -> Référence (AutoCAD : longueur de référence par deux points) -> référence libre -> normal
                if not self.refmode and not getattr(self, "acadref", False):
                    self.acadref = True
                elif getattr(self, "acadref", False):
                    self.acadref, self.refmode = False, True
                else:
                    self.refmode = False
                self.NEEDED = 4 if (self.refmode or self.acadref) else 3
                self.refresh(context)
            return {'RUNNING_MODAL'}
        return DessinTransform.modal(self, context, event)

    def ref_label(self):
        if getattr(self, "acadref", False):
            return "reference"
        return "free reference" if self.refmode else "off"

    def prompt(self):
        suffix = " (copy)" if self.center else ""
        n = len(self.points)
        if n == 0:
            return ("base point" + suffix + "   [C: copy, " + ("D: 3D / 2D / 1D, " if self.HAS_MODE else "") + "R: "
                    + self.ref_label() + "]")
        if getattr(self, "acadref", False):
            if n == 1:
                return "reference length: first point   [R: next mode]"
            if n == 2:
                return "reference length: second point"
            return "new length: point (distance from the base point), or type the length then Enter" + ("   [D: 3D / 2D / 1D]" if self.HAS_MODE else "")
        if self.refmode:
            if n == 1:
                return "first reference point (end of the reference length)   [R: back to normal]"
            if n == 2:
                return "second base point (where the first base point goes)"
            return "second reference point (new length from the second base point), or type the length" + ("   [D: 3D / 2D / 1D]" if self.HAS_MODE else "")
        if n == 1:
            return "factor (type then Enter) or first reference point   [R: reference by two points]"
        return "second reference point, or type the new length" + ("   [D: 3D / 2D / 1D]" if self.HAS_MODE else "")

    def measure(self, d, direction=None):
        """Longueur d'un vecteur selon le mode (3D / 2D dans le plan / 1D le long de la référence)."""
        u, v, _ = plane_axes(self.axis)
        if self.mode == 1:
            return math.hypot(d.dot(u), d.dot(v))
        if self.mode == 2 and direction is not None:
            return abs(d.dot(direction))
        return d.length

    def compute(self):
        n = len(self.points)
        if n == 0 or self.cur is None:
            return [], [], "", None
        c = self.points[0]
        u, v, _ = plane_axes(self.axis)

        dest = c   # point où arrive le point de base (second point de base en mode référence)
        if getattr(self, "acadref", False):
            # Référence (AutoCAD) : longueur de référence = distance p1 -> p2 (deux points quelconques),
            # nouvelle longueur = distance base -> curseur, ou valeur tapée ; facteur = nouvelle / référence
            if n == 1:
                return [], [[c, self.cur]], "", None
            r1pt = self.points[1]
            if n == 2:
                return [], [[r1pt, self.cur]], f"Reference length {self.fmt(self.measure(self.cur - r1pt))}", None
            d0 = self.points[2] - r1pt
            r0 = self.measure(d0)
            if r0 < 1e-9:
                return [], [], "", None
            direction = d0.normalized()
            r1 = self.measure(self.cur - c, direction)
            typed = self.typed_value(0)
            if typed is not None:
                r1 = abs(typed)
            factor = r1 / r0
            guides = [[r1pt, self.points[2]], [c, self.cur]]
            extra = f"   Reference {self.fmt(r0)} -> {self.fmt(r1)}"
        elif self.refmode:
            if n == 1:
                return [], [[c, self.cur]], "", None
            r1pt = self.points[1]
            d0 = r1pt - c
            r0 = self.measure(d0)
            if n == 2:
                return [], [[c, r1pt]], f"Reference length {self.fmt(r0)}", None
            if r0 < 1e-9:
                return [], [], "", None
            dest = self.points[2]
            direction = d0.normalized()
            typed = self.typed_value(0)
            r1 = self.measure(self.cur - dest, direction)
            if typed is not None:
                r1 = abs(typed)
            factor = r1 / r0
            guides = [[c, r1pt], [dest, self.cur]]
            extra = f"   Reference {self.fmt(r0)} -> {self.fmt(r1)}"
        else:
            typed = self.typed_raw(0)
            extra = ""
            if n == 1:
                if typed is None:
                    return [], [[c, self.cur]], "", None
                factor = typed
                direction = u
                guides = []
            else:
                p1 = self.points[1]
                d0 = p1 - c
                e = self.cur - c
                r0 = self.measure(d0)
                if r0 < 1e-9:
                    return [], [], "", None
                direction = d0.normalized()
                r1 = self.measure(e, direction)
                if typed is not None:
                    r1 = typed          # comme Rhino : la valeur tapée est la nouvelle distance (et non le facteur)
                factor = r1 / r0
                extra = f"   Reference {self.fmt(r0)} -> {self.fmt(abs(r1))}"
                guides = [[c, p1], [c, self.cur]]

        if abs(factor) < 1e-9:
            return [], guides, "", None
        if self.mode == 0:
            scale = Matrix.Scale(factor, 4)
        elif self.mode == 1:
            scale = Matrix.Scale(factor, 4, u) @ Matrix.Scale(factor, 4, v)
        else:
            scale = Matrix.Scale(factor, 4, direction)
        xform = Matrix.Translation(dest) @ scale @ Matrix.Translation(-c)
        info = f"Factor {factor:.4g}   Mode {self.MODES[self.mode]}" + extra
        return [], guides, info, ("xform", xform)


class DESSIN_OT_echelle(ScaleBase):
    bl_idname = "dessin.echelle"
    bl_label = "Scale"
    bl_description = ("Scales the selection: base point, two reference points, or typed factor "
                      "(R: Reference = reference length by two points then new length; R again: free reference with a second base point; D: 3D / 2D / 1D, C: copy)")

    TITLE = "Scale"


class DESSIN_OT_echelle_2d(ScaleBase):
    bl_idname = "dessin.echelle_2d"
    bl_label = "Scale 2D"
    bl_description = ("Scales the selection in the construction plane only (uniform in X and Y of the plane), like Scale2D: "
                      "base point, two reference points or typed factor. R: reference by two points (again: free reference), C: copy")

    TITLE = "Scale 2D"
    HAS_MODE = False
    START_MODE = 1
    MODES = ("3D", "2D (in the plane)", "1D (along the reference)")


class DESSIN_OT_echelle_1d(ScaleBase):
    bl_idname = "dessin.echelle_1d"
    bl_label = "Scale 1D"
    bl_description = ("Scales the selection in one direction only (the one from the base point to the reference point; "
                      "X of the plane if a factor is typed), like Scale1D: base point, two reference points or typed factor. R: reference by two points (again: free reference), C: copy")

    TITLE = "Scale 1D"
    HAS_MODE = False
    START_MODE = 2


def _world_bbox(objs):
    """Boîte englobante alignée sur le monde d'une liste d'objets : (min, max) ou None."""
    pts = []
    for o in objs:
        try:
            if o.type == 'EMPTY' or not o.bound_box:
                continue
            mw = o.matrix_world
            pts.extend(mw @ Vector(c) for c in o.bound_box)
        except (ReferenceError, AttributeError):
            pass
    if not pts:
        return None
    return (Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts))),
            Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts))))


class DESSIN_OT_echelle_taille(bpy.types.Operator):
    bl_idname = "dessin.echelle_taille"
    bl_label = "Scale to Size"
    bl_description = ("Scales the selected objects to exact overall dimensions (bounding box): type the final X, Y, Z size. "
                      "Keep proportions: change one value and the others follow")
    bl_options = {'REGISTER', 'UNDO'}

    size_x: bpy.props.FloatProperty(name="X", subtype='DISTANCE', min=0.0, precision=4)
    size_y: bpy.props.FloatProperty(name="Y", subtype='DISTANCE', min=0.0, precision=4)
    size_z: bpy.props.FloatProperty(name="Z", subtype='DISTANCE', min=0.0, precision=4)
    orig_x: bpy.props.FloatProperty(options={'HIDDEN', 'SKIP_SAVE'})
    orig_y: bpy.props.FloatProperty(options={'HIDDEN', 'SKIP_SAVE'})
    orig_z: bpy.props.FloatProperty(options={'HIDDEN', 'SKIP_SAVE'})
    keep_ratio: bpy.props.BoolProperty(name="Keep proportions", default=True)
    anchor: bpy.props.EnumProperty(name="Scale from", items=(
        ('CENTER', "Center", "Scale around the center of the bounding box"),
        ('BASE', "Base center", "Scale around the center of the bottom face (the base stays in place)"),
        ('MIN', "Min corner", "Scale around the lowest corner of the bounding box")), default='CENTER')

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and bool(context.selected_objects)

    def invoke(self, context, event):
        bb = _world_bbox(context.selected_objects)
        if bb is None:
            self.report({'WARNING'}, "Select objects with a volume or a length first")
            return {'CANCELLED'}
        d = bb[1] - bb[0]
        self.orig_x, self.orig_y, self.orig_z = d.x, d.y, d.z
        self.size_x, self.size_y, self.size_z = d.x, d.y, d.z
        return context.window_manager.invoke_props_dialog(self, width=300)

    def draw(self, context):
        col = self.layout.column(align=True)
        col.label(text="Final overall size (bounding box)")
        col.prop(self, "size_x")
        col.prop(self, "size_y")
        col.prop(self, "size_z")
        self.layout.prop(self, "keep_ratio")
        self.layout.prop(self, "anchor")

    def factors(self):
        old = (self.orig_x, self.orig_y, self.orig_z)
        new = (self.size_x, self.size_y, self.size_z)
        f = [1.0, 1.0, 1.0]
        for i in range(3):
            if old[i] > 1e-9 and new[i] > 1e-9:
                f[i] = new[i] / old[i]
        if self.keep_ratio:
            changed = [i for i in range(3) if abs(f[i] - 1.0) > 1e-7]
            if changed:
                f = [f[changed[0]]] * 3
        return f

    def cancel(self, context):
        try:
            idle_tool()
        except (RuntimeError, TypeError):
            pass

    def execute(self, context):
        objs = list(context.selected_objects)
        bb = _world_bbox(objs)
        if bb is None:
            return {'CANCELLED'}
        lo, hi = bb
        if self.anchor == 'MIN':
            a = lo.copy()
        elif self.anchor == 'BASE':
            a = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
        else:
            a = (lo + hi) / 2
        fx, fy, fz = self.factors()
        sc = Matrix.Diagonal(Vector((fx, fy, fz, 1.0)))
        xform = Matrix.Translation(a) @ sc @ Matrix.Translation(-a)
        tops = [o for o in objs if o.parent not in set(objs)]
        for o in tops:
            try:
                commit_world_xform(o, xform)
            except (ReferenceError, ValueError):
                pass
        bpy.context.view_layer.update()
        try:
            idle_tool()
        except (RuntimeError, TypeError):
            pass
        self.report({'INFO'}, f"Scaled by {fx:.4g} x {fy:.4g} x {fz:.4g}")
        return {'FINISHED'}


# --------------------------------------------------------------------------
# Interface
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# Boîte de sélection (fenêtre / capture, comme l'addon Cross Select)
def bake_negative_scale(obj):
    """Objet maillage miroir : on reporte l'inversion dans le maillage pour garder une échelle positive (sinon -1)."""
    try:
        if (obj.type != 'MESH' or obj.data.users != 1 or obj.children
                or obj.matrix_world.to_3x3().determinant() >= 0.0):
            return
        flip = Matrix.Scale(-1.0, 4, Vector((1.0, 0.0, 0.0)))
        mw = obj.matrix_world.copy()
        obj.data.transform(flip)
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()
        obj.matrix_world = mw @ flip
    except (RuntimeError, ReferenceError, ValueError):
        pass


class DESSIN_OT_miroir(DessinTransform):
    bl_idname = "dessin.mirror"
    bl_label = "Mirror"
    bl_description = ("Mirrors the selection about a plane: two points define the mirror line in the construction plane "
                      "(Shift: orthogonal, C: keep / replace the original)")

    TITLE = "Mirror"
    NEEDED = 2
    NUMFIELDS = 0
    MIRRORS = True
    NO_SELECTION = "Select the objects to mirror first"

    def invoke(self, context, event):
        result = super().invoke(context, event)
        self.center = True   # comme dans Rhino : le miroir garde l'original (C : le remplacer)
        if 'RUNNING_MODAL' in result:
            self.refresh(context)
        return result

    def prompt(self):
        if getattr(self, "selecting", False):
            return ""
        mode = "copy" if self.center else "replace"
        if not self.points:
            return f"start of the mirror line ({mode})   [C: copy / replace]"
        return f"end of the mirror line ({mode})   (Shift: orthogonal)   [C: copy / replace]"

    def compute(self):
        if not self.points or self.cur is None:
            return [], [], "", None
        a = self.points[0]
        u, v, nrm = plane_axes(self.axis)
        d = self.cur - a
        du, dv = d.dot(u), d.dot(v)
        if self.ortho:
            if abs(du) >= abs(dv):
                dv = 0.0
            else:
                du = 0.0
        L = math.hypot(du, dv)
        if L < 1e-9:
            return [], [], "", None
        e = (u * du + v * dv) / L
        m = nrm.cross(e)
        m.normalize()
        R3 = Matrix(((1 - 2 * m.x * m.x, -2 * m.x * m.y, -2 * m.x * m.z),
                     (-2 * m.y * m.x, 1 - 2 * m.y * m.y, -2 * m.y * m.z),
                     (-2 * m.z * m.x, -2 * m.z * m.y, 1 - 2 * m.z * m.z)))
        xform = Matrix.Translation(m * (2.0 * a.dot(m))) @ R3.to_4x4()
        ext = max(L, 1e-3) * 6.0
        info = f"Mirror line {self.fmt(L)}   ({'copy' if self.center else 'replace'})"
        return [], [[a - e * ext, a + e * ext]], info, ("xform", xform)

    def reverse_edit_faces(self):
        """Mode édition : un miroir retourne l'orientation des faces déplacées, on la rétablit."""
        for obj, idx, _w0 in self.items:
            try:
                bm = bmesh.from_edit_mesh(obj.data)
            except (ValueError, ReferenceError):
                continue
            bm.verts.ensure_lookup_table()
            vs = {bm.verts[i] for i in idx}
            faces = [f for f in bm.faces if all(x in vs for x in f.verts)]
            if faces:
                bmesh.ops.reverse_faces(bm, faces=faces)
            bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=True)

    def build(self, context, spec):
        before = set(bpy.data.objects.keys())
        super().build(context, spec)
        if self.edit:
            if not self.center:
                self.reverse_edit_faces()   # (les copies sont retournées dans edit_move)
            return None
        if self.center:
            for name in set(bpy.data.objects.keys()) - before:
                bake_negative_scale(bpy.data.objects[name])
        else:
            for obj, _mw in self.items:
                bake_negative_scale(obj)
        return None


# --------------------------------------------------------------------------
# Array (rectangulaire, linéaire, polaire)
# --------------------------------------------------------------------------

ARRAY_STATE = {"nx": 3, "ny": 3, "nz": 1, "n_lin": 5, "n_pol": 6, "ang": 360.0}   # derniers réglages (comme Rhino)
ARRAY_MAX = 5000


class DessinArray(DessinTransform):
    """Base des outils Array : les copies sont des duplicatas de la sélection (classe non enregistrée)."""

    NUMFIELDS = 3
    HAS_CENTER = False
    EDIT_OK = True
    NO_SELECTION = "Select the objects to array first"
    PREVIEW_MAX = 250

    # ---- saisie sûre (la liste typed peut être plus courte que NUMFIELDS) ----
    def pad_typed(self):
        while len(self.typed) < 6:
            self.typed.append('')

    def typed_value(self, i):
        self.pad_typed()
        return super().typed_value(i)

    def typed_raw(self, i):
        self.pad_typed()
        return super().typed_raw(i)

    def traw(self, i):
        return self.typed_raw(i)

    def tval(self, i):
        return self.typed_value(i)

    def handle_typing(self, event):
        while len(self.typed) < 6:
            self.typed.append('')
        return super().handle_typing(event)

    def reset_state(self):
        super().reset_state()
        self.typed = [''] * 6

    def count(self, i, key):
        t = self.traw(i)
        if t is not None:
            return max(1, int(round(abs(t))))
        return ARRAY_STATE[key]

    def can_confirm_typed(self):
        return True

    # ---- aperçu : boîtes englobantes des copies ----
    def capture_ghost(self, max_edges=500000):
        self._bbox = None
        super().capture_ghost(max_edges)

    def item_bbox(self):
        if getattr(self, "_bbox", None) is not None:
            return self._bbox
        pts = []
        try:
            if self.edit:
                for _o, _idx, w0 in self.items:
                    if len(w0):
                        pts.append(np.min(w0, axis=0))
                        pts.append(np.max(w0, axis=0))
            else:
                for obj, _mw in self.items:
                    mw = obj.matrix_world
                    pts += [mw @ Vector(c) for c in obj.bound_box]
        except ReferenceError:
            pass
        if not pts:
            self._bbox = ()
            return self._bbox
        arr = np.array([tuple(p) for p in pts], dtype=np.float64)
        lo, hi = arr.min(axis=0), arr.max(axis=0)
        x0, y0, z0 = lo
        x1, y1, z1 = hi
        self._bbox = tuple(Vector(p) for p in (
            (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
            (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)))
        return self._bbox

    @staticmethod
    def box_path(c, X):
        p = [X @ q for q in c]
        order = (0, 1, 2, 3, 0, 4, 5, 6, 7, 4, 5, 1, 2, 6, 7, 3)
        return [p[i] for i in order]

    def instance_guides(self, mats):
        bb = self.item_bbox()
        if not bb:
            return []
        center = sum(bb, Vector()) / 8.0
        out = []
        for M in mats[:self.PREVIEW_MAX]:
            X = M(center) if callable(M) else M
            out.append(self.box_path(bb, X))
        return out

    def refresh(self, context):
        if self.selecting:
            self.refresh_selecting(context)
            return
        DessinBase.refresh(self, context)   # pas de déplacement en direct des originaux : seules les copies s'affichent

    # ---- construction ----
    def finish_shape(self, context):
        _, _, _, spec = self.compute()
        if spec is None:
            self.refresh(context)
            return
        self.build(context, spec)
        self.store_state()
        self.finished = True
        self.reset_state()

    def store_state(self):
        pass

    def build(self, context, spec):
        mats = spec[1]
        if len(mats) > ARRAY_MAX:
            self.report({'WARNING'}, f"Too many copies ({len(mats)}), limit {ARRAY_MAX}")
            return None
        if self.edit:
            cen = Vector()
            n = 0
            for _o, _idx, w0 in self.items:
                for p in w0:
                    cen += Vector(p)
                    n += 1
            cen = cen / n if n else cen
            for M in mats:
                self.edit_move(M(cen) if callable(M) else M, duplicate=True)
        else:
            for M in mats:
                for obj, mw in self.items:
                    dup = duplicate_hierarchy(obj)
                    X = M(mw.translation) if callable(M) else M
                    dup.matrix_world = X @ mw
        self.committed = True
        return None


class DESSIN_OT_array_rect(DessinArray):
    bl_idname = "dessin.array_rect"
    bl_label = "Array: Rectangular"
    bl_description = ("Rectangular array of the selection: base corner then opposite corner of the unit cell "
                      "(type X count, Tab, Y count, Tab, Z count, Tab, X / Y / Z spacing)")

    TITLE = "Array"
    NUMFIELDS = 6
    PLANAR = True

    @property
    def NEEDED(self):
        return 3 if self.count(2, "nz") > 1 else 2

    def height_stage(self):
        return (not getattr(self, "selecting", False) and len(self.points) == 2 and self.count(2, "nz") > 1)

    ARROW_KEYS = {'RIGHT_ARROW': ("nx", 1, 0), 'LEFT_ARROW': ("nx", -1, 0),
                  'UP_ARROW': ("ny", 1, 1), 'DOWN_ARROW': ("ny", -1, 1),
                  'PAGE_UP': ("nz", 1, 2), 'PAGE_DOWN': ("nz", -1, 2)}

    def modal(self, context, event):
        k = self.ARROW_KEYS.get(event.type)
        if (k and event.value == 'PRESS' and not getattr(self, "selecting", False)
                and self.area is not None and context.area is not None
                and find_window_region(self.area, event.mouse_x, event.mouse_y) is not None
                and not self.mouse_over_ui(event)):
            key, step, idx = k
            self.pad_typed()
            self.typed[idx] = ''          # la flèche remplace une valeur tapée
            ARRAY_STATE[key] = max(1, min(100, ARRAY_STATE[key] + step))
            self.refresh(context)
            return {'RUNNING_MODAL'}
        return super().modal(context, event)

    def lock_allowed(self):
        return self.LOCK_OK and not self.height_stage()

    def prompt(self):
        if getattr(self, "selecting", False):
            return ""
        nx, ny, nz = self.count(0, "nx"), self.count(1, "ny"), self.count(2, "nz")
        cnt = f"{nx}×{ny}×{nz}"
        if not self.points:
            return f"first corner of the unit cell ({cnt})"
        if len(self.points) == 1:
            return (f"opposite corner of the unit cell ({cnt})   "
                    "(arrows: ←→ X count, ↑↓ Y count, PgUp/PgDn Z count; or type counts with Tab)")
        return "Z spacing   (or type the spacing then Enter)"

    def update_cursor(self, context, event):
        if not self.height_stage():
            return super().update_cursor(context, event)
        region = find_window_region(self.area, event.mouse_x, event.mouse_y)
        if region is None or self.mouse_over_ui(event):
            self.snap_screen = None
            self.snap_kind = None
            return
        self.region = region
        rv3d = region_rv3d(region, self.area)
        mx, my = event.mouse_x - region.x, event.mouse_y - region.y
        o = self.points[0]
        _, _, n = plane_axes(self.axis)
        last = self.points[-1]
        base = last - n * (last - o).dot(n)
        self.track_lines = []
        self.track_label = ""
        self.track_screen = None
        h = None
        snap = self.find_snap(mx, my, region, rv3d)
        if snap is not None:
            p, self.snap_screen, self.snap_kind = snap
            self._snap_pt = p.copy()
            h = (p - o).dot(n)
        else:
            self.snap_screen = None
            self.snap_kind = None
            self._snap_pt = None
            coord = Vector((mx, my))
            ro = region_2d_to_origin_3d(region, rv3d, coord)
            rv = region_2d_to_vector_3d(region, rv3d, coord)
            h = view_height(base, o, n, ro, rv, rv3d)
        if h is not None:
            self.cur = base + n * h
        elif self.cur is None:
            self.cur = base.copy()
        self.refresh(context)

    def compute(self):
        if not self.points or self.cur is None:
            return [], [], "", None
        o = self.points[0]
        u, v, n = plane_axes(self.axis)
        pts = self.points + [self.cur]
        stage = len(self.points)
        nx, ny, nz = self.count(0, "nx"), self.count(1, "ny"), self.count(2, "nz")
        d = pts[1] - o
        du, dv = d.dot(u), d.dot(v)
        sx = self.sized(3, du, du)
        sy = self.sized(4, dv, dv)
        if stage >= 2:
            dz = (pts[2] - o).dot(n)
            sz = self.sized(5, dz, dz)
        else:
            sz = self.sized(5, 0.0, 1.0)
        total = nx * ny * nz
        info = f"{nx}×{ny}×{nz} = {total} items   Spacing {self.fmt(abs(sx))} × {self.fmt(abs(sy))}"
        if nz > 1:
            info += f" × {self.fmt(abs(sz))}"
        ok = ((nx == 1 or abs(sx) > 1e-9) and (ny == 1 or abs(sy) > 1e-9)
              and (nz == 1 or abs(sz) > 1e-9) and total > 1)
        cell = [o, o + u * sx, o + u * sx + v * sy, o + v * sy, o]
        if not ok:
            return cell, [], info, None
        mats = []
        for k in range(nz):
            for j in range(ny):
                for i in range(nx):
                    if i == j == k == 0:
                        continue
                    mats.append(Matrix.Translation(u * (sx * i) + v * (sy * j) + n * (sz * k)))
        return cell, self.instance_guides(mats), info, ("array", mats)

    def store_state(self):
        ARRAY_STATE["nx"] = self.count(0, "nx")
        ARRAY_STATE["ny"] = self.count(1, "ny")
        ARRAY_STATE["nz"] = self.count(2, "nz")


class DESSIN_OT_array_linear(DessinArray):
    bl_idname = "dessin.array_linear"
    bl_label = "Array: Linear"
    bl_description = ("Linear array: base point then a second point (spacing, or total length with D); "
                      "type the count, Tab, the spacing (Shift: orthogonal)")

    TITLE = "Array (linear)"
    NEEDED = 2
    NUMFIELDS = 2
    PLANAR = False
    HAS_MODE = True
    MODES = ("spacing = base → point", "total length = base → point")

    def invoke(self, context, event):
        self.mode = 0
        return super().invoke(context, event)

    def prompt(self):
        if getattr(self, "selecting", False):
            return ""
        n = self.count(0, "n_lin")
        if not self.points:
            return f"base point ({n} items)"
        return (f"second point: {self.MODES[self.mode]}   (type count, Tab, spacing, Enter)   "
                "[D: spacing / total length, Shift: orthogonal]")

    def compute(self):
        if not self.points or self.cur is None:
            return [], [], "", None
        a = self.points[0]
        u, v, _ = plane_axes(self.axis)
        d = self.cur - a
        if self.ortho:
            du, dv = d.dot(u), d.dot(v)
            d = u * du if abs(du) >= abs(dv) else v * dv
        n = self.count(0, "n_lin")
        if n < 2:
            return [], [], "", None
        length = d.length
        direction = d / length if length > 1e-9 else u.copy()
        t = self.tval(1)
        if t is not None:
            step = direction * abs(t)
        elif self.mode == 1:
            step = d / (n - 1)
        else:
            step = d
        if step.length < 1e-9:
            return [], [[a, self.cur]], "", None
        mats = [Matrix.Translation(step * k) for k in range(1, n)]
        info = f"{n} items   Spacing {self.fmt(step.length)}   Total {self.fmt(step.length * (n - 1))}"
        return [], [[a, a + step * (n - 1)]] + self.instance_guides(mats), info, ("array", mats)

    def store_state(self):
        ARRAY_STATE["n_lin"] = self.count(0, "n_lin")


class DESSIN_OT_array_polar(DessinArray):
    bl_idname = "dessin.array_polar"
    bl_label = "Array: Polar"
    bl_description = ("Polar array around an axis perpendicular to the construction plane: click the center, "
                      "type the count and the angle (D: rotate items or not, F: other direction)")

    TITLE = "Array (polar)"
    NEEDED = 2
    NUMFIELDS = 2
    HAS_MODE = True
    HAS_FLIP = True
    MODES = ("rotate items", "keep orientation")

    def invoke(self, context, event):
        self.mode = 0
        return super().invoke(context, event)

    def prompt(self):
        if getattr(self, "selecting", False):
            return ""
        n = self.count(0, "n_pol")
        if not self.points:
            return f"center of the polar array ({n} items, {ARRAY_STATE['ang']:g}°)"
        return ("click to confirm   (type count, Tab, angle, Enter)   "
                f"[D: {self.MODES[self.mode]}, F: other direction]")

    def compute(self):
        if not self.points or self.cur is None:
            return [], [], "", None
        c = self.points[0]
        u, v, nrm = plane_axes(self.axis)
        n = self.count(0, "n_pol")
        ang = self.traw(1)
        if ang is None:
            ang = ARRAY_STATE["ang"]
        if n < 2 or abs(ang) < 1e-9:
            return [], [[c, self.cur]], "", None
        full = abs(abs(ang) - 360.0) < 1e-6
        step = math.radians(ang) / (n if full else (n - 1))
        if self.flip:
            step = -step
        mats = []
        for k in range(1, n):
            R = Matrix.Translation(c) @ Matrix.Rotation(step * k, 4, nrm) @ Matrix.Translation(-c)
            if self.mode == 0:
                mats.append(R)
            else:
                mats.append(lambda p, R=R: Matrix.Translation((R @ p) - p))
        info = f"{n} items   {ang:g}°   {self.MODES[self.mode]}"
        radius = (self.cur - c).length
        ring = arc_samples(c, u, v, max(radius, 1e-6), 0.0, TAU, 64) if radius > 1e-9 else []
        return [], [[c, self.cur], ring] + self.instance_guides(mats), info, ("array", mats)

    def store_state(self):
        ARRAY_STATE["n_pol"] = self.count(0, "n_pol")
        a = self.traw(1)
        if a is not None:
            ARRAY_STATE["ang"] = a


# --------------------------------------------------------------------------
# Cut (solides)
# --------------------------------------------------------------------------

def cut_mesh_by_plane(obj, co, no, keep):
    """Coupe un maillage avec un plan monde (co, no). keep : 'pos', 'neg' ou 'both'.
    Retourne la liste des objets résultants (l'original reste le premier)."""
    mw = obj.matrix_world
    inv = mw.inverted()
    lco = inv @ co
    lno = (mw.to_3x3().transposed() @ no).normalized()

    def run(me, clear_inner, clear_outer):
        bm = bmesh.new()
        bm.from_mesh(me)
        closed = all(len(e.link_faces) == 2 for e in bm.edges) and len(bm.faces) > 0
        ret = bmesh.ops.bisect_plane(bm, geom=list(bm.verts) + list(bm.edges) + list(bm.faces),
                                     dist=1e-7, plane_co=lco, plane_no=lno,
                                     clear_inner=clear_inner, clear_outer=clear_outer)
        if closed:
            cut = [g for g in ret["geom_cut"] if isinstance(g, bmesh.types.BMEdge) and g.is_valid]
            if cut:
                try:
                    bmesh.ops.holes_fill(bm, edges=cut, sides=0)
                except (RuntimeError, ValueError, TypeError):
                    try:
                        bmesh.ops.triangle_fill(bm, edges=cut, use_beauty=True)
                    except (RuntimeError, ValueError, TypeError):
                        pass
        bm.normal_update()
        out = bm.verts and len(bm.faces) + len(bm.edges) > 0
        bm.to_mesh(me)
        bm.free()
        me.update()
        return bool(out)

    src = obj.data
    results = []
    if keep == 'both':
        other = obj.copy()
        other.data = src.copy()
        for coll in obj.users_collection:
            coll.objects.link(other)
        obj.data = src.copy()
        if run(obj.data, True, False):    # côté positif conservé (on enlève l'intérieur = négatif)
            results.append(obj)
        if run(other.data, False, True):
            results.append(other)
        else:
            bpy.data.objects.remove(other)
        return results
    obj.data = src.copy()
    run(obj.data, keep == 'pos', keep == 'neg')
    return [obj]


class DESSIN_OT_cut(DessinArray):
    bl_idname = "dessin.cut"
    bl_label = "Split"
    bl_description = ("Splits solids into separate parts with a vertical plane defined by a line (two points) "
                      "and closes the cut faces")
    TITLE = "Split"
    NEEDED = 2
    NUMFIELDS = 0
    EDIT_OK = False
    HAS_MODE = False
    HAS_FLIP = False
    PLANAR = True
    MODES = ("keep both parts", "keep one side", "keep the other side")
    NO_SELECTION = "Select the solids to split first"

    def invoke(self, context, event):
        if context.mode == 'EDIT_MESH':
            try:
                bpy.ops.object.mode_set(mode='OBJECT')
            except RuntimeError:
                self.report({'WARNING'}, "Switch to Object mode")
                return {'CANCELLED'}
        self.mode = 0
        return super().invoke(context, event)

    def pick_line(self, context):
        """Segment (A, B monde) de la ligne existante sous la souris (courbe, polyligne ou contour), ou None."""
        mouse = _CMD["mouse"].get(self.area.as_pointer()) if self.area is not None else None
        if mouse is None or self.region is None:
            return None
        rv3d = region_rv3d(self.region, self.area)
        if rv3d is None:
            return None
        persp = np.array(rv3d.perspective_matrix, dtype=np.float64)
        skip = {o.name for o, _mw in self.items}
        dg = context.evaluated_depsgraph_get()
        m = np.array(mouse, dtype=np.float64)
        best, best_d = None, 8.0 * px_scale()
        for obj in context.view_layer.objects:
            try:
                if obj.name in skip or obj.type not in {'CURVE', 'MESH'} or not obj.visible_get():
                    continue
                if obj.type == 'MESH' and len(obj.data.polygons):
                    continue
                paths = object_paths(obj, dg)
            except (RuntimeError, ReferenceError):
                continue
            for P, closed in paths:
                Q = np.vstack((P, P[:1])) if closed else P
                if len(Q) < 2:
                    continue
                sx, sy, ok = _project_region(Q, persp, self.region)
                S = np.stack((sx, sy), axis=1)
                A, B = S[:-1], S[1:]
                good = ok[:-1] & ok[1:]
                AB = B - A
                L2 = np.maximum((AB * AB).sum(axis=1), 1e-9)
                t = np.clip(((m - A) * AB).sum(axis=1) / L2, 0.0, 1.0)
                d = np.linalg.norm(A + AB * t[:, None] - m, axis=1)
                d = np.where(good, d, 1e9)
                i = int(np.argmin(d))
                if d[i] < best_d:
                    best_d = d[i]
                    best = (Vector(Q[i]), Vector(Q[i + 1]))
        return best

    def click(self, context):
        if (not self.selecting and not self.points and not self.edit
                and (self.snap_screen is None or self.snap_kind == 7)):
            seg = self.pick_line(context)
            if seg is not None and (seg[1] - seg[0]).length > 1e-9:
                self.flush_pending(context)
                if not self.sync_selection(context):
                    return
                self.points = [seg[0]]
                self.cur = seg[1]
                self.finish_shape(context)
                return
        super().click(context)

    def prompt(self):
        if getattr(self, "selecting", False):
            return ""
        if not self.points:
            return "first point of the splitting line (or click an existing line)"
        return "second point"

    def compute(self):
        if not self.points or self.cur is None:
            return [], [], "", None
        a = self.points[0]
        u, v, n = plane_axes(self.axis)
        d = self.cur - a
        d = d - n * d.dot(n)
        if d.length < 1e-9:
            return [], [], "", None
        d.normalize()
        pn = d.cross(n)
        if self.flip:
            pn = -pn
        bb = self.item_bbox()
        ext = 1.0
        z0, z1 = 0.0, 1.0
        if bb:
            ext = max((q - a).length for q in bb) * 1.5 + 1e-6
            zs = [(q - a).dot(n) for q in bb]
            z0, z1 = min(zs), max(zs)
        e0, e1 = a - d * ext, a + d * ext
        rect = [e0 + n * z0, e1 + n * z0, e1 + n * z1, e0 + n * z1, e0 + n * z0]
        mid = a + d * ((self.cur - a).dot(d) / 2.0)
        tick = [mid, mid + pn * ext * 0.15]
        guides = [rect, tick]
        if self.mode == 0:
            guides.append([mid, mid - pn * ext * 0.15])
        keep = ('both', 'pos', 'neg')[self.mode]
        info = "Split: both parts kept"
        return [a, a + d * ((self.cur - a).dot(d))], guides, info, ("cut", a, pn, keep)

    def build(self, context, spec):
        _, co, no, keep = spec
        made = []
        for obj, _mw in self.items:
            try:
                if obj.type != 'MESH':
                    continue
                made.extend(cut_mesh_by_plane(obj, co, no, keep))
            except ReferenceError:
                continue
        self.committed = True
        if not made:
            self.report({'WARNING'}, "No mesh solid to split")
        return None

    def store_state(self):
        pass


def _late_imports():
    """Noms définis dans des modules chargés après celui-ci : ils ne servent qu'à l'exécution des outils."""
    global DESSIN_OT_selection_boite, _CMD, _project_region, object_paths, pick_object_at, set_prompt
    from .selection import DESSIN_OT_selection_boite, _project_region, pick_object_at
    from .surfaces import object_paths
    from .views import _CMD
    from .cplane import set_prompt
