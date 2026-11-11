"""Wanderer CAD : Classe de base des outils de dessin (saisie, accrochage, suivi)."""

import bpy
import math
import time
import numpy as np
from bpy_extras.view3d_utils import region_2d_to_origin_3d, region_2d_to_vector_3d
from mathutils import Vector, geometry

from .core import (
    AXES3, IDLE_FALLBACK, IDLE_TOOL, SNAP_NAMES, TAU, TRACK_DWELL, TRACK_MAX, TRACK_RADIUS, _LAST_TYPED, arc_samples,
    build_bezier_arc, build_polyline, build_shape_mesh, drawing_axis, edit_add_geometry, idle_tool, last_typed,
    osnap, plane_axes, plane_origin, pref, shape_output, unit_info,
)
from .snapping import collect_snap_points
from .drawing import (
    _HOVER, draw_pixel_cb, draw_view_cb, find_snap_in, find_window_region, main_window_region, over_nav_gizmo,
    project_px, px_scale, region_rv3d, track_lines_near,
)


# --------------------------------------------------------------------------
# Opérateur de base
# --------------------------------------------------------------------------

def view_height(base, o, n, ro, rv, rv3d):
    """Hauteur (le long de n, mesurée depuis o) désignée par le rayon souris. Si la hauteur est dans l'axe de la vue
    (vue de dessus pour une normale Z), comme Rhino / AutoCAD : distance du curseur au point de base, positive
    au-dessus de lui à l'écran, négative en dessous."""
    if abs(rv.normalized().dot(n)) > 0.98:
        hit = geometry.intersect_line_plane(ro, ro + rv, base, n)
        if hit is None:
            return None
        d = hit - base
        try:
            up = rv3d.view_rotation @ Vector((0.0, 1.0, 0.0))
        except (AttributeError, TypeError):
            up = d
        side = d.dot(up)
        return (base - o).dot(n) + math.copysign(d.length, side if abs(side) > 1e-12 else 1.0)
    res = geometry.intersect_line_line(base, base + n, ro, ro + rv)
    return (res[0] - o).dot(n) if res else None


def parse_coord(text, unit_f=1.0):
    """Saisie de coordonnées style Rhino/AutoCAD.
    '#x,y[,z]' ou 'x;y' : absolu (repère du plan) ; '@x,y[,z]' : relatif au dernier point ;
    'd<a' ou '@d<a' : polaire relatif (distance d, angle a en degrés depuis l'axe X du plan) ; '#d<a' : polaire absolu.
    Avec ';' comme séparateur, la virgule redevient décimale. Retourne (absolu, (x, y, z)) ou None si incomplet."""
    s = text.strip().replace(' ', '')
    if not s:
        return None
    absolute = True
    if s[0] == '#':
        s = s[1:]
    elif s[0] == '@':
        absolute, s = False, s[1:]
    elif '<' in s:
        absolute = False
    if ';' in s:
        sep, s = ';', s.replace(',', '.')
    else:
        sep = ','
    try:
        if '<' in s:
            d, a = s.split('<', 1)
            d, a = float(d), math.radians(float(a))
            return absolute, (d * math.cos(a) * unit_f, d * math.sin(a) * unit_f, 0.0)
        parts = [float(x) for x in s.split(sep)]
    except ValueError:
        return None
    if not 2 <= len(parts) <= 3:
        return None
    parts += [0.0] * (3 - len(parts))
    return absolute, tuple(x * unit_f for x in parts)


class DessinBase(bpy.types.Operator):
    bl_options = {'REGISTER', 'UNDO'}

    TITLE = ""
    NEEDED = 2
    NUMFIELDS = 0
    HAS_CENTER = False
    HAS_FLIP = False
    HAS_MODE = False
    EDIT_OK = True  # la commande fonctionne aussi en mode édition (maillage) : elle ajoute alors de la géométrie
    COORD_OK = True  # saisie #x,y / @x,y / d<angle
    LOCK_OK = True  # X / Y / Z : verrouille le déplacement du curseur sur un axe à partir du dernier point posé
    PLANAR = True  # False : les points accrochés gardent leur vraie position 3D
    PROP = ()      # étapes (nb de points posés) où Maj impose des proportions : 1 = base carrée, 2 = hauteur = côté (cube)

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D'

    # ---- à surcharger ----
    def prompt(self):
        return ""

    def compute(self):
        """Retourne (aperçu, guides, info, spec)."""
        return [], [], "", None

    # ---- cycle de vie ----
    def invoke(self, context, event):
        if event.type == 'MOUSEMOVE' and _HOVER["running"] > 0:
            return {'CANCELLED', 'PASS_THROUGH'}  # une commande est déjà armée
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS' and cmd_click_idle(context, event):
            return {'CANCELLED'}                  # clic sur une puce de la barre de commande
        area = context.area
        prev = _CMD["op"].get(area.as_pointer()) if area is not None else None
        if prev is not None and prev is not self:
            try:
                alive = prev.area is not None and not getattr(prev, "_done", None)
                same = alive and prev.bl_idname == self.bl_idname and bool(prev.points)
            except (ReferenceError, AttributeError):
                alive = same = False
            if same and event.type == 'LEFTMOUSE' and event.value == 'PRESS':
                # clic dans la partie transparente de la barre latérale (chevauchement des régions) : la commande en
                # cours l'a laissé passer et l'outil s'est relancé ; le clic revient à la commande en cours
                try:
                    prev.update_cursor(context, event)
                    if prev.cur is not None:
                        prev.click(context)
                        if prev.finished:
                            prev._done = prev.exit(context)
                except (ReferenceError, AttributeError, RuntimeError):
                    pass
                return {'CANCELLED'}
            if alive:
                try:                              # ancienne commande restée en arrière-plan : on la termine
                    prev._done = {'CANCELLED'}
                    prev.cleanup(context)
                except (ReferenceError, AttributeError, RuntimeError):
                    pass
        if context.mode != 'OBJECT' and not (self.EDIT_OK and context.mode == 'EDIT_MESH') \
                and not (getattr(self, 'CURVE_EDIT_OK', False) and context.mode == 'EDIT_CURVE'):
            try:
                bpy.ops.object.mode_set(mode='OBJECT')
            except RuntimeError:
                self.report({'WARNING'}, "Switch to Object mode to draw")
                return {'CANCELLED'}

        self.area = area
        _CMD["op"][area.as_pointer()] = self
        self.tool_id = self.active_dessin_tool(context)
        self.finished = False
        self._snap_time = time.monotonic()
        if event.type == 'MOUSEMOVE' and (self.tool_id is None or self.mouse_over_ui(event)):
            return {'CANCELLED', 'PASS_THROUGH'}
        self.region = (find_window_region(area, event.mouse_x, event.mouse_y)
                       or main_window_region(area))
        if self.region is None:
            return {'CANCELLED'}

        self.unit_f, self.unit_label = unit_info(context.scene)
        self.snap_on = True
        self.snap_screen = None
        self.snap_kind = None
        self.center = False
        self.flip = False
        self.shift = False
        self.axis = 2
        self.cur = None
        self.points = []
        self.typed = ['', '', '']
        self.field = 0
        self.coord = ''
        self.coord_pt = None
        self.from_state = None     # From (AutoCAD) : None, 'BASE' (on attend le point de base), 'OFFSET' (on tape le décalage)
        self.from_base = None
        self._from_dir = None
        self.preview = []
        self.guides = []
        self.info = ""
        self.lock = None
        self.track_pts = []
        self.track_lines = []
        self.track_label = ""
        self.track_screen = None
        self._snap_pt = None
        self._hover_pt = None
        self._hover_t = 0.0
        self._timer = None
        try:
            self._timer = context.window_manager.event_timer_add(0.1, window=context.window)
        except (AttributeError, TypeError, RuntimeError):
            self._timer = None
        self.collect_snaps(context)

        self._h_view = bpy.types.SpaceView3D.draw_handler_add(
            draw_view_cb, (self,), 'WINDOW', 'POST_VIEW')
        self._h_pix = bpy.types.SpaceView3D.draw_handler_add(
            draw_pixel_cb, (self,), 'WINDOW', 'POST_PIXEL')

        context.window_manager.modal_handler_add(self)
        _HOVER["running"] += 1
        self._counted = True
        self.update_cursor(context, event)
        if (event.type == 'LEFTMOUSE' and event.value == 'PRESS'
                and self.cur is not None and self.tool_id is not None):
            # Lancé par un clic depuis la barre d'outils : ce clic pose déjà le premier point
            self.click(context)
        else:
            self.refresh(context)
        return {'RUNNING_MODAL'}

    @staticmethod
    def active_tool_id(context):
        try:
            tool = context.workspace.tools.from_space_view3d_mode(context.mode, create=False)
        except (AttributeError, RuntimeError, TypeError):
            return None
        return tool.idname if tool is not None else None

    @classmethod
    def active_dessin_tool(cls, context):
        tid = cls.active_tool_id(context)
        return tid if tid is not None and tid.startswith("dessin.") else None

    def tool_changed(self, context):
        return self.active_tool_id(context) != self.tool_id

    def mouse_over_ui(self, event):
        """Souris au-dessus de la barre d'outils, de la barre latérale ou des en-têtes."""
        space = self.area.spaces.active
        shown = {
            'TOOLS': getattr(space, "show_region_toolbar", True),
            'UI': getattr(space, "show_region_ui", True),
            'HEADER': getattr(space, "show_region_header", True),
            'TOOL_HEADER': getattr(space, "show_region_tool_header", True),
        }
        x, y = event.mouse_x, event.mouse_y
        for r in self.area.regions:
            if shown.get(r.type) and r.x <= x < r.x + r.width and r.y <= y < r.y + r.height:
                return True
        return over_nav_gizmo(self.area, x, y)

    def cleanup(self, context):
        try:
            if _CMD["op"].get(self.area.as_pointer()) is self:
                del _CMD["op"][self.area.as_pointer()]
        except (AttributeError, ReferenceError):
            pass
        if getattr(self, '_counted', False):
            self._counted = False
            _HOVER["running"] = max(0, _HOVER["running"] - 1)
        if getattr(self, '_timer', None) is not None:
            try:
                context.window_manager.event_timer_remove(self._timer)
            except (AttributeError, TypeError, RuntimeError, ReferenceError):
                pass
            self._timer = None
        for attr in ('_h_view', '_h_pix'):
            h = getattr(self, attr, None)
            if h is not None:
                bpy.types.SpaceView3D.draw_handler_remove(h, 'WINDOW')
                setattr(self, attr, None)
        try:
            set_prompt(self.area, None)
            context.workspace.status_text_set(None)
            self.area.tag_redraw()
        except (ReferenceError, AttributeError):
            pass

    def cancel(self, context):
        self.cleanup(context)

    def after_finish(self, context):
        """Commande validée : si elle venait de la barre d'outils, on retrouve l'outil de sélection."""
        if getattr(self, "tool_id", None):
            try:
                idle_tool()
            except (RuntimeError, TypeError):
                pass

    def deselect_all(self):
        try:
            if bpy.context.mode == 'EDIT_MESH':
                bpy.ops.mesh.select_all(action='DESELECT')
            elif bpy.context.mode == 'OBJECT':
                bpy.ops.object.select_all(action='DESELECT')
        except (RuntimeError, AttributeError):
            pass

    def go_idle(self):
        """Quitte l'outil : on retrouve Select / Move (ou la sélection de Blender si l'add-on n'est pas complet)."""
        try:     # les puces de la commande qui se termine ne doivent plus capter les clics de Select
            _CMD["hit"].pop(self.area.as_pointer(), None)
            self.area.tag_redraw()
        except (AttributeError, ReferenceError, NameError):
            pass
        if not getattr(self, "tool_id", None) or not pref("auto_idle"):
            return
        for name in (IDLE_TOOL, IDLE_FALLBACK):
            try:
                bpy.ops.wm.tool_set_by_id(name=name)
                return
            except (RuntimeError, TypeError):
                continue

    def exit(self, context):
        self.cleanup(context)
        if self.finished:
            cmd_log(self.TITLE)
            self.after_finish(context)
            return {'FINISHED'}
        if pref("esc_deselect"):
            self.deselect_all()  # Échap : la sélection est relâchée aussi
        self.go_idle()      # Échap / Entrée sans rien faire : on sort de l'outil
        return {'CANCELLED'}

    def undo_step(self, context, event):
        """Ctrl+Z pendant la commande. Par défaut : la commande est annulée, comme Échap (un second Ctrl+Z annule ensuite
        l'opération précédente). Les commandes point par point retirent leur dernier point."""
        return self.exit(context)

    # ---- accrochage ----
    def collect_snaps(self, context):
        self.snap_data = collect_snap_points(context, getattr(self, "snap_exclude", None))
        self.snap_pts, self.snap_hom, self.snap_kinds, self.snap_bias = self.snap_data
        self._seen = _HOVER["version"]

    def find_snap(self, mx, my, region, rv3d):
        if not self.snap_on or self.snap_hom is None:
            return None
        data = getattr(self, "snap_data", None)
        if data is None or data[0] is not self.snap_pts:
            data = (self.snap_pts, self.snap_hom, self.snap_kinds, self.snap_bias)
        return find_snap_in(data, mx, my, region, rv3d, ref=self.points[-1] if self.points else None)

    def update_cursor(self, context, event):
        if self.coord_pt is not None:
            self.cur = self.coord_pt.copy()
            self.refresh(context)
            return
        region = find_window_region(self.area, event.mouse_x, event.mouse_y)
        if region is None or self.mouse_over_ui(event):
            self.snap_screen = None
            self.snap_kind = None
            _CMD["mouse"].pop(self.area.as_pointer(), None)     # plus de réticule hors de la vue
            try:
                self.area.tag_redraw()
            except ReferenceError:
                pass
            return
        self.region = region
        _CMD["mouse"][self.area.as_pointer()] = (event.mouse_x - region.x, event.mouse_y - region.y)
        _CMD.setdefault("mouse_t", {})[self.area.as_pointer()] = time.monotonic()
        if not self.points and _HOVER["version"] != self._seen:
            now = time.monotonic()
            if now - self._snap_time > 0.25:  # la scène a changé : on rafraîchit les accrochages
                self._snap_time = now
                self.collect_snaps(context)
        rv3d = region_rv3d(region, self.area)
        mx = event.mouse_x - region.x
        my = event.mouse_y - region.y

        if not self.points:
            if self.PLANAR:
                autocp_hover(context, region, rv3d, mx, my)
            self.axis = drawing_axis(rv3d)
        _, _, n = plane_axes(self.axis)
        origin = self.points[0] if self.points else plane_origin(self.axis)

        snap = self.find_snap(mx, my, region, rv3d)
        self.track_lines = []
        self.track_label = ""
        self.track_screen = None
        if snap is not None:
            p, self.snap_screen, self.snap_kind = snap
            self._snap_pt = p.copy()
            if osnap("project") or (self.points and self.PLANAR):
                p = p - n * (p - origin).dot(n)     # Project : on reste dans le plan de construction
            self.cur = p
        else:
            self.snap_screen = None
            self.snap_kind = None
            coord = Vector((mx, my))
            ray_o = region_2d_to_origin_3d(region, rv3d, coord)
            ray_v = region_2d_to_vector_3d(region, rv3d, coord)
            hit = geometry.intersect_line_plane(ray_o, ray_o + ray_v, origin, n)
            if hit is not None:
                self.cur = hit
            self._snap_pt = None
            if self.snap_on and self.lock is None and pref("smart_tracks"):
                if not self.track_midpoint(region, rv3d, mx, my, n, origin):
                    self.track_cursor(region, rv3d, mx, my, ray_o, ray_v, origin, n)
        if self.lock is not None and self.points and self.cur is not None and self.lock_allowed():
            self.apply_lock(region, rv3d, mx, my)
        elif (self.points and self.cur is not None and self.PLANAR and self.snap_screen is None and not self.track_lines
              and self.lock_allowed()):
            self.apply_ortho_polar(context, region, rv3d)
        self.refresh(context)

    def apply_ortho_polar(self, context, region, rv3d):
        """Ortho (F8) : axes du plan seulement ; Polar (F10) : angles multiples du pas, avec une ligne guide."""
        try:
            st = context.scene.dessin
            ortho, polar = st.ortho, st.polar
        except (AttributeError, ReferenceError):
            return
        if not (ortho or polar):
            return
        u, v, _n = plane_axes(self.axis)
        O = self.points[-1]
        d = self.cur - O
        du, dv = d.dot(u), d.dot(v)
        length = math.hypot(du, dv)
        if length < 1e-9:
            return
        if ortho:
            if abs(du) >= abs(dv):
                self.cur = O + u * du
                self.track_lines = [(O, u.copy())]
            else:
                self.cur = O + v * dv
                self.track_lines = [(O, v.copy())]
            self.track_label = "Ortho"
        else:
            inc = float(st.polar_angle)
            ang = math.degrees(math.atan2(dv, du))
            target = round(ang / inc) * inc
            t = math.radians(target)
            dirn = u * math.cos(t) + v * math.sin(t)
            proj = max(d.dot(dirn), 0.0)
            cand = O + dirn * proj
            a, b = project_px(rv3d, region, self.cur), project_px(rv3d, region, cand)
            if a is None or b is None or (a - b).length > TRACK_RADIUS * px_scale(1.0):
                return
            self.cur = cand
            self.track_lines = [(O, dirn)]
            self.track_label = f"Polar {target % 360:g}°"
        sp = project_px(rv3d, region, self.cur)
        self.track_screen = (sp.x, sp.y) if sp is not None else None

    # ---- verrouillage d'axe (touches X / Y / Z) ----
    def lock_allowed(self):
        return self.LOCK_OK

    def apply_lock(self, region, rv3d, mx, my):
        k = self.lock
        a = AXES3[k]
        O = self.points[-1]
        n = plane_axes(self.axis)[2]
        in_plane = abs(a.dot(n)) < 0.5
        if not in_plane and self.PLANAR:
            return  # un axe hors du plan ne peut rien faire pour une commande plane
        if in_plane or self.snap_screen is not None:
            p = O + a * (self.cur - O).dot(a)
        else:
            coord = Vector((mx, my))
            ro = region_2d_to_origin_3d(region, rv3d, coord)
            rv = region_2d_to_vector_3d(region, rv3d, coord)
            res = geometry.intersect_line_line(O, O + a, ro, ro + rv)
            p = res[0] if res else self.cur
        self.cur = p
        self.track_lines = [(O, k)]
        self.track_label = "XYZ"[k] + " locked"
        sp = project_px(rv3d, region, p)
        self.track_screen = (sp.x, sp.y) if sp is not None else None

    # ---- repérage (SmartTrack) ----
    def track_dirs(self):
        if self.PLANAR:
            return [i for i in range(3) if i != self.axis]
        return [0, 1, 2]

    def track_midpoint(self, region, rv3d, mx, my, n, origin):
        """Milieu de deux points posés / acquis : le curseur s'y accroche quand il passe à proximité."""
        pts = list(self.points) + list(self.track_pts)
        if len(pts) < 2:
            return False
        here = Vector((mx, my))
        best = None
        for i in range(len(pts)):
            for j in range(i + 1, len(pts)):
                m = (pts[i] + pts[j]) * 0.5
                if (pts[i] - pts[j]).length < 1e-6:
                    continue
                if self.points and self.PLANAR:
                    m = m - n * (m - origin).dot(n)
                sp = project_px(rv3d, region, m)
                if sp is None:
                    continue
                dist = (sp - here).length
                if dist < TRACK_RADIUS * px_scale(1.0) * 1.5 and (best is None or dist < best[0]):
                    best = (dist, m, sp)
        if best is None:
            return False
        _, m, sp = best
        self.cur = m
        self._snap_pt = m.copy()
        self.snap_screen = (sp.x, sp.y)
        self.snap_kind = 1
        self.track_lines = []
        self.track_label = "midpoint of tracked points"
        return True

    def track_ext_dirs(self, p):
        """Directions des segments (courbes, arêtes) qui finissent au point p : leurs prolongements sont des lignes de
        repérage, comme SmartTrack de Rhino et l'accrochage Extension d'AutoCAD. Les directions déjà couvertes par les
        axes X / Y / Z sont laissées de côté ; commande plane : seulement les directions du plan de construction."""
        cache = self.__dict__.setdefault("_ext_cache", {})
        edges = getattr(getattr(self, "snap_data", None), "edges", None)
        key = (round(p.x, 6), round(p.y, 6), round(p.z, 6), self.axis if self.PLANAR else -1)
        hit = cache.get(key)
        if hit is not None and hit[0] is edges:
            return hit[1]
        out = []
        if edges is not None and len(edges):
            q = np.array(tuple(p), dtype=np.float64)
            tol = max(1e-6, 1e-7 * float(np.abs(q).max()))
            vecs = []
            for near, far in ((0, 1), (1, 0)):
                at = np.flatnonzero(np.abs(edges[:, near, 0] - q[0]) <= tol)      # une colonne d'abord : rapide sur 200 000 segments
                if len(at):
                    at = at[np.abs(edges[at, near, 1:] - q[1:]).max(axis=1) <= tol]
                if len(at):
                    vecs.append((edges[at, near, :] - edges[at, far, :])[:8])      # du segment vers l'extérieur
            n = plane_axes(self.axis)[2] if self.PLANAR else None
            for v in (np.concatenate(vecs) if vecs else ()):
                d = Vector(v)
                if n is not None:
                    if abs(d.normalized().dot(n)) > 1e-4 if d.length > 1e-12 else True:
                        continue
                if d.length < 1e-9:
                    continue
                d.normalize()
                if any(abs(abs(d.dot(a)) - 1.0) < 1e-9 for a in AXES3):
                    continue                            # déjà une ligne X / Y / Z
                if any(abs(d.dot(o)) > 1.0 - 1e-9 for o in out):
                    continue
                out.append(d)
                if len(out) >= 4:
                    break
        cache[key] = (edges, out)
        return out

    def track_cursor(self, region, rv3d, mx, my, ray_o, ray_v, origin, n):
        """Accroche le curseur aux lignes alignées (X/Y/Z) issues des points posés et des points acquis, et aux
        prolongements des segments qui finissent en ces points."""
        origins = list(self.points) + list(self.track_pts)
        if not origins:
            return
        found = track_lines_near(origins, self.track_dirs(), rv3d, region, mx, my, extra=self.track_ext_dirs)
        if not found:
            return
        vec = lambda k: k if isinstance(k, Vector) else AXES3[k]
        _, O1, k1 = found[0]
        d1 = vec(k1)
        pt = None
        lines = [(O1, k1)]
        for _, O2, k2 in found[1:]:
            if abs(vec(k2).dot(d1)) > 1.0 - 1e-9:
                continue
            res = geometry.intersect_line_line(O1, O1 + d1, O2, O2 + vec(k2))
            if not res:
                continue
            pa, pb = res
            if (pa - pb).length > 1e-3 * max(1.0, (pa - O1).length):
                continue
            sp = project_px(rv3d, region, pa)
            if sp is None or (sp - Vector((mx, my))).length > 3 * TRACK_RADIUS:
                continue
            pt = pa
            lines = [(O1, k1), (O2, k2)]
            break
        if pt is None:
            res = geometry.intersect_line_line(O1, O1 + d1, ray_o, ray_o + ray_v)
            if not res:
                return
            pt = res[0]
        if self.points and self.PLANAR:
            pt = pt - n * (pt - origin).dot(n)
        sp = project_px(rv3d, region, pt)
        if sp is None:
            return
        self.cur = pt
        self.track_lines = lines
        self.track_label = " ∩ ".join("Ext" if isinstance(k, Vector) else "XYZ"[k] for _, k in lines)
        self.track_screen = (sp.x, sp.y)

    def track_tick(self):
        """Acquiert un point d'accrochage survolé assez longtemps (comme les SmartTrack de Rhino)."""
        p = self._snap_pt
        if p is None or self.snap_screen is None or not pref("smart_tracks"):
            self._hover_pt = None
            return
        now = time.monotonic()
        if self._hover_pt is None or (p - self._hover_pt).length > 1e-6:
            self._hover_pt = p.copy()
            self._hover_t = now
            return
        if now - self._hover_t < TRACK_DWELL:
            return
        for q in list(self.points) + self.track_pts:
            if (q - p).length < 1e-6:
                return
        self.track_pts.append(p.copy())
        if len(self.track_pts) > TRACK_MAX:
            self.track_pts.pop(0)
        try:
            self.area.tag_redraw()
        except ReferenceError:
            pass

    # ---- affichage ----
    def constrain_proportional(self):
        """Maj : base carrée (étape 1) ou hauteur égale au côté de la base, soit un cube (étape 2)."""
        if not (self.shift and self.PROP and self.cur is not None and self.points):
            return
        k = len(self.points)
        if k not in self.PROP:
            return
        u, v, n = plane_axes(self.axis)
        o = self.points[0]
        if k == 1:
            d = self.cur - o
            du, dv, dn = d.dot(u), d.dot(v), d.dot(n)
            m = max(abs(du), abs(dv))
            if m < 1e-12:
                return
            self.cur = o + u * math.copysign(m, du if du else 1.0) + v * math.copysign(m, dv if dv else 1.0) + n * dn
        else:
            b = self.points[1] - o
            side = max(abs(b.dot(u)), abs(b.dot(v))) * (2.0 if self.center else 1.0)
            last = self.points[-1]
            base = last - n * (last - o).dot(n)
            h = (self.cur - o).dot(n)
            if side > 1e-12:
                self.cur = base + n * math.copysign(side, h if h else 1.0)

    def prompt_tail(self):
        """Fin d'invite commune (S: snap, Shift+F: From, Esc, Enter/Space) : masquée quand les touches servent à autre chose."""
        return True

    def refresh(self, context):
        self.constrain_proportional()
        if self.cur is not None:
            self.preview, self.guides, self.info, _ = self.compute()
        fs = getattr(self, "from_state", None)
        if fs == 'OFFSET' and self.from_base is not None and self.cur is not None:
            self.guides = list(self.guides or []) + [[self.from_base, self.cur]]
        txt = f"{self.TITLE} : {self.prompt()}"
        if fs == 'BASE':
            txt = f"{self.TITLE} : From: base point   (Esc: cancel From)"
        elif fs == 'OFFSET':
            txt = f"{self.TITLE} : From: offset   (type @x,y  @distance<angle  or a distance along the cursor, Enter)"
        if self.info:
            txt += f"   |   {self.info}"
        if self.coord:
            txt += f"   |   coords: {self.coord}" + ("" if self.coord_pt is not None else " _")
        if any(self.typed):
            txt += "   |   typed: " + " / ".join(s or "_" for s in self.typed[:max(1, self.NUMFIELDS)])
        last = self.last_typed_now()
        if last:
            txt += "   |   Enter: " + " / ".join(x or "_" for x in last[:max(1, self.NUMFIELDS)]) + " (last value)"
        if getattr(self, "track_label", ""):
            txt += f"   |   tracking: {self.track_label}"
        if getattr(self, "lock", None) is not None:
            txt += "   |   [X/Y/Z: change axis, same key: release]"
        elif self.points and self.lock_allowed():
            txt += "   |   [X/Y/Z: lock axis]"
        snap_txt = "ON" if self.snap_on else "OFF"
        if self.snap_on and self.snap_kind is not None and self.snap_screen is not None:
            snap_txt += f" [{SNAP_NAMES[self.snap_kind]}]"
        if self.prompt_tail():
            txt += (f"   |   S: snap {snap_txt}" + ("   |   Shift+F: From" if self.COORD_OK and fs is None else "")
                    + ("   |   Esc: cancel" if last else "   |   Esc: cancel   Enter/Space: quit"))
        if self.tool_id and not self.points and not any(self.typed):
            # invite « au repos » de l'outil : réaffichée dès qu'on le sélectionne, avant même que la souris entre dans la vue
            _CMD.setdefault("tool_prompt", {})[self.tool_id] = f"{self.TITLE} : {self.prompt()}   |   S: snap ON   |   Esc: cancel   Enter/Space: quit"
        try:
            set_prompt(self.area, txt)
            self.area.tag_redraw()
        except ReferenceError:
            pass

    def fmt(self, value):
        x = value / self.unit_f
        s = f"{x:.3f}".rstrip('0').rstrip('.')
        return f"{s} {self.unit_label}".strip()

    # ---- saisie numérique ----
    def typed_value(self, i):
        s = self.typed[i]
        if s in ('', '-', '.', '-.'):
            return None
        try:
            return float(s) * self.unit_f
        except ValueError:
            return None

    def typed_raw(self, i):
        """Valeur saisie sans conversion d'unité (angle en degrés, facteur d'échelle...)."""
        s = self.typed[i]
        if s in ('', '-', '.', '-.'):
            return None
        try:
            return float(s)
        except ValueError:
            return None

    def can_confirm_typed(self):
        return len(self.points) == self.NEEDED - 1

    # ---- Entrée = dernière valeur saisie (comme le <défaut> de Rhino / AutoCAD) ----
    def last_typed_key(self):
        return (self.bl_idname, len(self.points))

    def last_typed_now(self):
        """Valeurs que reprendrait Entrée à cette étape (None si rien à reprendre)."""
        if (not self.points or not self.NUMFIELDS or any(self.typed) or self.coord
                or getattr(self, "from_state", None) or getattr(self, "selecting", False)):
            return None
        return last_typed(self.last_typed_key())

    def remember_typed(self):
        if any(self.typed) and self.NUMFIELDS:
            _LAST_TYPED[self.last_typed_key()] = list(self.typed)

    def reuse_last_typed(self, context, event):
        """Entrée sans saisie : remet la dernière valeur tapée à cette étape. Vrai si elle peut être validée."""
        last = self.last_typed_now()
        if not last or self.cur is None:
            return False
        keep = (list(self.typed), self.field)
        self.typed = list(last) + [''] * (len(self.typed) - len(last))
        ok = False
        try:
            if self.can_confirm_typed():
                self.refresh(context)       # comme une frappe : la valeur s'applique dans la direction du curseur
                ok = self.cur is not None
        except (RuntimeError, ReferenceError, ValueError, AttributeError):
            ok = False
        if not ok:
            self.typed, self.field = keep
        return ok

    def sized(self, i, mouse_val, mouse_for_sign):
        t = self.typed_value(i)
        if t is None:
            return mouse_val
        if self.typed[i].startswith('-'):
            return -abs(t)
        return abs(t) if mouse_for_sign >= 0 else -abs(t)

    # ---- saisie de coordonnées / angles ----
    def coord_target(self):
        u, v, n = plane_axes(self.axis)
        fb = self.from_base if getattr(self, "from_state", None) == 'OFFSET' else None
        if fb is not None:
            txt = self.coord.strip().replace(' ', '')
            body = txt[1:] if txt[:1] == '@' else txt
            try:            # distance seule : le long de la direction base -> curseur (comme la distance directe d'AutoCAD)
                d = float(body.replace(',', '.')) * self.unit_f if body and not any(c in body for c in ',;<#') else None
            except ValueError:
                d = None
            if d is not None:
                ref = self._from_dir if self._from_dir is not None else fb + u
                w = ref - fb
                w = w - n * w.dot(n)
                w = w.normalized() if w.length > 1e-9 else u.copy()
                return fb + w * d
        r = parse_coord(self.coord, self.unit_f)
        if r is None:
            return None
        absolute, (x, y, z) = r
        if fb is not None and not self.coord.strip().startswith('#'):
            base = fb             # From : le décalage part du point de base choisi (avec ou sans @)
        else:
            base = plane_origin(self.axis) if (absolute or not self.points) else self.points[-1]
        return base + u * x + v * y + n * z

    def coord_update(self):
        self.coord_pt = self.coord_target()
        if self.coord_pt is not None:
            self.cur = self.coord_pt.copy()

    def handle_coord(self, event):
        if event.value != 'PRESS' or event.oskey:
            return False
        if (event.ctrl or event.alt) and (event.unicode or "") not in ('#', '@', '<'):
            return False            # AltGr (Ctrl + Alt sous Windows, Option sur Mac) sert à taper # et @ sur bien des claviers
        if event.type == 'ESC' and self.coord:
            self.coord, self.coord_pt = '', None
            return True
        if event.type == 'BACK_SPACE' and self.coord:
            self.coord = self.coord[:-1]
            self.coord_update()
            if not self.coord:
                self.coord_pt = None
            return True
        ch = event.unicode
        if not ch:
            return False
        if not self.coord:
            if ch in '#@':
                self.coord = ch
                self._from_dir = self.cur.copy() if self.cur is not None else None
                return True
            if getattr(self, "from_state", None) == 'OFFSET' and ch in "0123456789.-":
                self._from_dir = self.cur.copy() if self.cur is not None else None
                self.coord = ch
                self.coord_update()
                return True
            t = self.typed[self.field]
            if ch in '<;' and self.points and t not in ('', '-'):
                self.coord, self.typed, self.field = t + ch, ['', '', ''], 0
                self.coord_update()
                return True
            return False
        if ch not in "0123456789.,-;<":
            return False
        self.coord += ch
        self.coord_update()
        return True

    def coord_pre(self, context, event):
        """Saisie de coordonnées et From, traitées avant le modal propre à chaque outil (sinon la polyligne, par
        exemple, prendrait Entrée ou les chiffres pour elle). Retourne un résultat de modal, ou None pour continuer."""
        if not self.COORD_OK or getattr(self, "area", None) is None or event.value != 'PRESS':
            return None
        et = event.type
        if et in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE', 'TIMER'} or getattr(self, "selecting", False):
            return None
        try:
            if find_window_region(self.area, event.mouse_x, event.mouse_y) is None or self.mouse_over_ui(event):
                return None
            if et == 'LEFTMOUSE' and cmd_hit(self.area, event.mouse_x, event.mouse_y) is not None:
                return None          # clic sur la barre de commande : pour elle
        except (ReferenceError, AttributeError):
            return None
        if (et == 'LEFTMOUSE' and self.from_state == 'OFFSET' and not self.coord
                and not (event.ctrl or event.alt or event.oskey)):
            self.from_state, self.from_base = None, None   # clic pendant le décalage : point cliqué normal
            return None
        if (self.COORD_OK and et == 'F' and event.value == 'PRESS' and event.shift
                and not (event.ctrl or event.alt or event.oskey)):
            # Maj+F : From (AutoCAD) : point de base temporaire, puis décalage tapé (@x,y, @d<angle ou distance)
            if self.from_state is None:
                self.from_state, self.from_base = 'BASE', None
            else:
                self.from_state, self.from_base = None, None
            self.coord, self.coord_pt = '', None
            self.refresh(context)
            return {'RUNNING_MODAL'}
        if self.from_state is not None and et == 'ESC' and event.value == 'PRESS' and not self.coord:
            self.from_state, self.from_base = None, None     # Échap : on quitte seulement From
            self.refresh(context)
            return {'RUNNING_MODAL'}
        if (self.from_state == 'BASE' and et == 'LEFTMOUSE' and event.value == 'PRESS'
                and not (event.ctrl or event.alt or event.oskey)):
            self.update_cursor(context, event)
            if self.cur is not None:
                self.from_base = self.cur.copy()
                self.from_state = 'OFFSET'
                self.refresh(context)
            return {'RUNNING_MODAL'}

        if self.COORD_OK and self.handle_coord(event):
            self.refresh(context)
            return {'RUNNING_MODAL'}

        if self.COORD_OK and self.coord and et in {'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS':
            if self.coord_confirm(context) and self.finished:
                return self.exit(context)
            self.refresh(context)
            return {'RUNNING_MODAL'}
        return None

    def coord_confirm(self, context):
        pt = self.coord_target()
        if pt is None:
            self.report({'WARNING'}, "Incomplete coordinates (#x,y  @x,y  d<angle)")
            return False
        self.cur = pt
        self.coord, self.coord_pt = '', None
        self.from_state, self.from_base = None, None
        self.click(context)
        return True

    def handle_typing(self, event):
        if event.value != 'PRESS' or event.ctrl or event.alt or event.oskey:
            return False
        if event.type == 'TAB':
            self.field = (self.field + 1) % self.NUMFIELDS
            return True
        if event.type == 'BACK_SPACE':
            self.typed[self.field] = self.typed[self.field][:-1]
            return True
        ch = event.unicode
        if not ch or ch not in "0123456789.,-":
            return False
        if ch == '-':
            if event.type.startswith('NUMPAD') or self.typed[self.field]:
                return False
        if ch == ',':
            ch = '.'
        if ch == '.' and '.' in self.typed[self.field]:
            return True
        self.typed[self.field] += ch
        return True

    # ---- construction ----
    def build_edit(self, context, spec):
        """Mode édition : la forme devient de la géométrie (sommets + arêtes) du maillage édité."""
        kind = spec[0]
        if kind == 'rect':
            pts, edges = list(spec[1]), [(0, 1), (1, 2), (2, 3), (3, 0)]
        elif kind == 'line':
            pts, edges = [spec[1], spec[2]], [(0, 1)]
        elif kind == 'poly':
            pts = list(spec[1])
            edges = [(i, (i + 1) % len(pts)) for i in range(len(pts))]
        elif kind == 'circle':
            _, c, u, v, r = spec
            pts = arc_samples(c, u, v, r, 0.0, TAU, seg=48)[:-1]
            edges = [(i, (i + 1) % len(pts)) for i in range(len(pts))]
        elif kind == 'arc':
            _, c, u, v, r, t0, sweep = spec
            pts = arc_samples(c, u, v, r, t0, sweep, seg=48)
            edges = [(i, i + 1) for i in range(len(pts) - 1)]
        elif kind == 'ellipse':
            _, c, A, W = spec
            pts = arc_samples(c, A, W, 1.0, 0.0, TAU, seg=64)[:-1]
            edges = [(i, (i + 1) % len(pts)) for i in range(len(pts))]
        else:
            return None
        return edit_add_geometry(context, pts, edges, [])

    def build(self, context, spec):
        kind = spec[0]
        if context.mode == 'EDIT_MESH':
            return self.build_edit(context, spec)
        mode = shape_output(context)
        if mode != 'CURVE' and kind in {'ellipse', 'poly', 'rect', 'line', 'circle', 'arc'}:
            # contour en maillage (arêtes, avec ou sans face) au lieu d'une courbe
            if kind == 'ellipse':
                _, c, A, W = spec
                return build_shape_mesh(context, "Ellipse", arc_samples(c, A, W, 1.0, 0.0, TAU, seg=64)[:-1], True, c, mode, plane_axes(self.axis)[2])
            if kind == 'poly':
                return build_shape_mesh(context, "Polygon", list(spec[1]), True, spec[1][0], mode, plane_axes(self.axis)[2])
            if kind == 'rect':
                return build_shape_mesh(context, "Rectangle", list(spec[1]), True, spec[1][0], mode, plane_axes(self.axis)[2])
            if kind == 'line':
                return build_shape_mesh(context, "Line", [spec[1], spec[2]], False, spec[1], mode, plane_axes(self.axis)[2])
            if kind == 'circle':
                _, c, u, v, r = spec
                return build_shape_mesh(context, "Circle", arc_samples(c, u, v, r, 0.0, TAU, seg=48)[:-1], True, c, mode, plane_axes(self.axis)[2])
            _, c, u, v, r, t0, sweep = spec
            return build_shape_mesh(context, "Arc", arc_samples(c, u, v, r, t0, sweep, seg=48), False, c, mode, plane_axes(self.axis)[2])
        if kind == 'ellipse':
            _, c, A, W = spec  # ellipse = image affine d'un cercle unité : c + A cos t + W sin t
            return build_bezier_arc(context, "Ellipse", c, A, W, 1.0, 0.0, TAU, True)
        if kind == 'poly':
            return build_polyline(context, "Polygon", spec[1], True)
        if kind == 'rect':
            return build_polyline(context, "Rectangle", spec[1], True)
        if kind == 'line':
            return build_polyline(context, "Line", [spec[1], spec[2]], False)
        if kind == 'circle':
            _, c, u, v, r = spec
            return build_bezier_arc(context, "Circle", c, u, v, r, 0.0, TAU, True)
        if kind == 'arc':
            _, c, u, v, r, t0, sweep = spec
            return build_bezier_arc(context, "Arc", c, u, v, r, t0, sweep, False)
        return None

    def reset_state(self):
        self.points = []
        self.typed = ['', '', '']
        self.field = 0
        self.flip = False
        self.preview = []
        self.guides = []
        self.lock = None
        self.track_pts = []
        self.track_lines = []
        self.track_label = ""
        self.track_screen = None

    def finish_shape(self, context):
        _, _, _, spec = self.compute()
        if spec is None:
            self.report({'WARNING'}, "Invalid shape")
            return
        self.build(context, spec)
        self.finished = True
        self.reset_state()

    def click(self, context):
        if not self.points:
            self.points.append(self.cur.copy())
        elif len(self.points) < self.NEEDED - 1:
            self.points.append(self.cur.copy())
        else:
            self.finish_shape(context)
            return
        self.lock = None  # le verrouillage ne vaut que pour le segment en cours
        self.refresh(context)

    # ---- événements ----
    def modal(self, context, event):
        done = getattr(self, "_done", None)
        if done:                                  # terminée depuis une autre instance (voir invoke)
            return {'FINISHED'} if 'FINISHED' in done else {'CANCELLED'}
        if self.area is None or context.area is None:
            self.cleanup(context)
            return {'CANCELLED'}
        if self.tool_id and self.tool_changed(context):
            # l'utilisateur a choisi un autre outil : on rend la main sans avaler son clic
            self.cleanup(context)
            return {'CANCELLED', 'PASS_THROUGH'}
        et = event.type
        self.shift = bool(event.shift)

        if et == 'TIMER':
            self.track_tick()
            return {'PASS_THROUGH'}

        if et in {'LEFT_SHIFT', 'RIGHT_SHIFT'} and self.PROP and self.points:
            self.update_cursor(context, event)   # Maj enfoncé / relâché : l'aperçu change tout de suite
            return {'RUNNING_MODAL'}

        if et in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            self.update_cursor(context, event)
            if (find_window_region(self.area, event.mouse_x, event.mouse_y) is None
                    or self.mouse_over_ui(event)):
                return {'PASS_THROUGH'}  # sinon les boutons de la barre d'outils ne s'activent plus
            return {'RUNNING_MODAL'}

        # Hors de la vue (autres zones, barre d'outils, barre latérale) : ce n'est pas pour nous
        if (find_window_region(self.area, event.mouse_x, event.mouse_y) is None
                or self.mouse_over_ui(event)):
            return {'PASS_THROUGH'}

        if et == 'LEFTMOUSE' and event.value == 'PRESS' and not getattr(self, "_chip_busy", False):
            hit = cmd_hit(self.area, event.mouse_x, event.mouse_y)
            if hit is not None:
                # clic sur une puce de la barre de commande : même effet que la touche correspondante
                if hit[0] == 'open':
                    bpy.ops.dessin.command_line('INVOKE_DEFAULT')
                    return {'RUNNING_MODAL'}
                if hit[0] == 'view':
                    bpy.ops.dessin.view_restore('INVOKE_DEFAULT', name=hit[1])
                    return {'RUNNING_MODAL'}
                if hit[0] == 'viewmenu':
                    new_view_dialog_later(context)
                    return {'RUNNING_MODAL'}
                if hit[0] == 'osnap':
                    vbar_toggle(context, hit[1])
                    return {'RUNNING_MODAL'}
                if hit[0] == 'mode':
                    mode_click(context, hit[1])
                    self.update_cursor(context, event)
                    return {'RUNNING_MODAL'}
                key = cmd_chip_key(hit[1]) if hit[0] == 'key' else None
                if key is not None:
                    self._chip_busy = True
                    try:
                        return self.modal(context, CmdKeyEvent(event, key[0], key[1]))
                    finally:
                        self._chip_busy = False
                return {'RUNNING_MODAL'}

        if et in {'Z', 'Y'} and event.value == 'PRESS' and (event.ctrl or event.oskey) and self.points:
            # Ctrl+Z en pleine commande : l'annulation de Blender reviendrait sur l'opération PRÉCÉDENTE pendant que la commande
            # tient encore ses objets (erreurs, aperçus orphelins). Elle agit donc sur la commande elle-même.
            if et == 'Z' and not event.shift:
                return self.undo_step(context, event)
            return {'RUNNING_MODAL'}        # rétablir : sans objet tant que la commande est en cours

        if et == 'ESC' and event.value == 'PRESS':
            return self.exit(context)   # Échap : annule la commande en cours et quitte l'outil

        if et in {'RET', 'NUMPAD_ENTER', 'SPACE'} and event.value == 'PRESS':
            if not any(self.typed) and not event.is_repeat:
                self.reuse_last_typed(context, event)
            if (self.points and any(self.typed) and self.cur is not None
                    and self.can_confirm_typed()):
                self.remember_typed()
                self.finish_shape(context)
                if self.finished:
                    return self.exit(context)
                return {'RUNNING_MODAL'}
            idle_space = (et == 'SPACE' and not self.points and not event.is_repeat
                          and pref("cmd_line") and pref("cmd_key") == 'SPACE')
            res = self.exit(context)
            if idle_space:      # outil armé, rien en cours : Espace quitte l'outil ET ouvre la ligne de commande
                try:
                    bpy.ops.dessin.command_line('INVOKE_DEFAULT')
                except RuntimeError:
                    pass
            return res

        if self.points and self.NUMFIELDS and self.handle_typing(event):
            self.refresh(context)
            return {'RUNNING_MODAL'}

        if et == 'LEFTMOUSE':
            if event.alt or event.oskey:
                return {'PASS_THROUGH'}      # Alt/Cmd+clic gauche = navigation (orbite), pas un clic d'outil
            if event.value == 'PRESS' and not event.ctrl:
                self.update_cursor(context, event)
                if self.cur is not None:
                    self.coord, self.coord_pt = '', None
                    self.from_state, self.from_base = None, None
                    far_origin_check(self, context, self.cur)
                    if self.points:
                        self.remember_typed()       # valeur tapée puis validée d'un clic : retenue elle aussi
                    self.click(context)
                    if self.finished:
                        return self.exit(context)
            return {'RUNNING_MODAL'}

        if et == 'TAB':
            return {'RUNNING_MODAL'}

        if event.value == 'PRESS' and not (event.ctrl or event.alt or event.oskey):
            if et in {'F3', 'F8', 'F10'}:
                try:
                    st = context.scene.dessin
                    if et == 'F3':
                        st.osnap_disable = not st.osnap_disable   # F3 : accrochages objet on / off, comme AutoCAD
                    elif et == 'F8':
                        st.ortho = not st.ortho
                    else:
                        st.polar = not st.polar
                except (AttributeError, ReferenceError):
                    pass
                self.update_cursor(context, event)
                return {'RUNNING_MODAL'}
            if et == 'S':
                self.snap_on = not self.snap_on
                self.update_cursor(context, event)
                return {'RUNNING_MODAL'}
            if et in {'X', 'Y', 'Z'} and self.points and self.lock_allowed():
                k = "XYZ".index(et)
                if self.PLANAR and abs(AXES3[k].dot(plane_axes(self.axis)[2])) >= 0.5:
                    return {'RUNNING_MODAL'}  # cet axe sort du plan de construction : sans effet ici
                self.lock = None if self.lock == k else k
                self.update_cursor(context, event)
                return {'RUNNING_MODAL'}
            if et == 'C' and self.HAS_CENTER:
                self.center = not self.center
                self.refresh(context)
                return {'RUNNING_MODAL'}
            if et == 'F' and self.HAS_FLIP:
                self.flip = not self.flip
                self.refresh(context)
                return {'RUNNING_MODAL'}
            if et == 'D' and self.HAS_MODE:
                self.mode = (self.mode + 1) % len(self.MODES)
                self.refresh(context)
                return {'RUNNING_MODAL'}

        # Navigation (clic droit mappé sur l'orbite/pan, molette, pavé numérique...) et le reste
        return {'PASS_THROUGH'}


def _late_imports():
    """Noms définis dans des modules chargés après celui-ci : ils ne servent qu'à l'exécution des outils."""
    global CmdKeyEvent, _CMD, autocp_hover, cmd_chip_key, cmd_click_idle, cmd_hit, cmd_log, far_origin_check
    global mode_click, new_view_dialog_later, set_prompt, vbar_toggle
    from .curve_edit import far_origin_check
    from .views import _CMD
    from .cplane import cmd_log, set_prompt
    from .pushpull import autocp_hover
    from .command_line import (
        CmdKeyEvent, cmd_chip_key, cmd_click_idle, cmd_hit, mode_click, new_view_dialog_later, vbar_toggle,
    )
