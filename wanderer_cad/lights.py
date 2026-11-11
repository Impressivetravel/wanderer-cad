"""Wanderer CAD : Lumières et caméras."""

import bpy
import math
import numpy as np
import time
from mathutils import Matrix, Vector

from .core import TAU, _link_object, arc_samples, plane_axes
from .snapping import curve_edit_selection, edit_selection
from .base import DessinBase
from .subd import expand_groups


# --------------------------------------------------------------------------
# Lumières et caméra : on les pose avec la souris (clic, glisser pour la taille / la direction)
# --------------------------------------------------------------------------

class LightBase(DessinBase):
    """Base des outils lumière / caméra (classe non enregistrée) : objets, pas de mode édition."""

    EDIT_OK = False
    DATA_NAME = "Light"
    LIGHT_TYPE = 'POINT'
    ENERGY = 10.0

    def new_light(self, context, loc, rot=None, name=None):
        data = bpy.data.lights.new(name or self.DATA_NAME, self.LIGHT_TYPE)
        data.energy = self.ENERGY
        obj = _link_object(context, name or self.DATA_NAME, data)
        obj.location = loc
        if rot is not None:
            obj.rotation_euler = rot.to_euler()
        return obj

    def aim_quat(self, a, b):
        """Rotation qui oriente l'axe -Z de l'objet de a vers b (lumières et caméras regardent vers -Z)."""
        d = b - a
        if d.length < 1e-9:
            d = Vector((0.0, 0.0, -1.0))
        return d.to_track_quat('-Z', 'Y')


class DESSIN_OT_light_point(LightBase):
    bl_idname = "dessin.light_point"
    bl_label = "Point Light"
    bl_description = "Places a point light: click its position, then drag / click to set its radius (or type the radius)"

    TITLE = "Point Light"
    NEEDED = 2
    NUMFIELDS = 1

    def prompt(self):
        if not self.points:
            return "position of the light"
        return "radius (drag, or type the radius then Enter)"

    def compute(self):
        if not self.points or self.cur is None:
            return [], [], "", None
        c = self.points[0]
        u, v, _ = plane_axes(self.axis)
        d = self.cur - c
        r = math.hypot(d.dot(u), d.dot(v))
        t = self.typed_value(0)
        if t is not None:
            r = abs(t)
        prev = arc_samples(c, u, v, r, 0.0, TAU, 64) if r > 1e-9 else []
        return prev, [], f"Radius {self.fmt(r)}", ("point", c.copy(), r)

    def build(self, context, spec):
        _, c, r = spec
        obj = self.new_light(context, c)
        if r > 1e-6:
            obj.data.shadow_soft_size = r


class DESSIN_OT_light_spot(LightBase):
    bl_idname = "dessin.light_spot"
    bl_label = "Spot Light"
    bl_description = ("Places a spot light: its position, the point it aims at, then the radius of the cone at that point "
                      "(drag, or type the radius)")

    TITLE = "Spot Light"
    NEEDED = 3
    NUMFIELDS = 1
    PLANAR = False
    LIGHT_TYPE = 'SPOT'

    def prompt(self):
        n = len(self.points)
        if n == 0:
            return "position of the spot"
        if n == 1:
            return "target point (where the spot aims)"
        return "radius of the cone at the target (drag, or type the radius then Enter)"

    def compute(self):
        n = len(self.points)
        if n == 0 or self.cur is None:
            return [], [], "", None
        p0 = self.points[0]
        if n == 1:
            return [], [[p0, self.cur]], f"Distance {self.fmt((self.cur - p0).length)}", None
        p1 = self.points[1]
        axis = p1 - p0
        L = axis.length
        if L < 1e-9:
            return [], [], "", None
        f = axis / L
        r = (self.cur - p0).cross(f).length
        t = self.typed_value(0)
        if t is not None:
            r = abs(t)
        ang = 2.0 * math.atan2(r, L) if r > 1e-9 else math.radians(45.0)
        ang = max(math.radians(1.0), min(math.radians(179.0), ang))
        rr = L * math.tan(ang / 2.0)
        a = f.orthogonal().normalized()
        b = f.cross(a)
        ring = [p1 + (a * math.cos(TAU * i / 48) + b * math.sin(TAU * i / 48)) * rr for i in range(49)]
        guides = [[p0, p1]] + [[p0, ring[k]] for k in (0, 12, 24, 36)]
        info = f"Cone {math.degrees(ang):.1f}°   Radius {self.fmt(rr)}"
        return ring, guides, info, ("spot", p0.copy(), p1.copy(), ang)

    def build(self, context, spec):
        _, p0, p1, ang = spec
        obj = self.new_light(context, p0, self.aim_quat(p0, p1))
        obj.data.spot_size = ang
        obj.data.spot_blend = 0.15


class DESSIN_OT_light_sun(LightBase):
    bl_idname = "dessin.light_sun"
    bl_label = "Sun Light"
    bl_description = "Places a sun light: click its position, then the point it aims at (the direction of the light)"

    TITLE = "Sun Light"
    NEEDED = 2
    NUMFIELDS = 0
    PLANAR = False
    LIGHT_TYPE = 'SUN'
    ENERGY = 3.0

    def prompt(self):
        return "position of the sun" if not self.points else "target point (direction of the light)"

    def compute(self):
        if not self.points or self.cur is None:
            return [], [], "", None
        p0 = self.points[0]
        d = self.cur - p0
        if d.length < 1e-9:
            return [], [], "", None
        f = d.normalized()
        tip = self.cur
        a = f.orthogonal().normalized() * (d.length * 0.08)
        guides = [[p0, tip], [tip, tip - f * (d.length * 0.15) + a], [tip, tip - f * (d.length * 0.15) - a]]
        return [], guides, f"Direction ({f.x:.2f}, {f.y:.2f}, {f.z:.2f})", ("sun", p0.copy(), tip.copy())

    def build(self, context, spec):
        _, p0, p1 = spec
        self.new_light(context, p0, self.aim_quat(p0, p1))


class DESSIN_OT_light_area(LightBase):
    bl_idname = "dessin.light_area"
    bl_label = "Area Light"
    bl_description = ("Places a rectangular area light like a rectangle: two opposite corners (or type width, Tab, height); "
                      "it lights away from the construction plane (F: flip, C: from center)")

    TITLE = "Area Light"
    PROP = (1,)
    NEEDED = 2
    NUMFIELDS = 2
    HAS_CENTER = True
    HAS_FLIP = True
    LIGHT_TYPE = 'AREA'
    ENERGY = 10.0

    def prompt(self):
        if not self.points:
            return "first corner" + (" (center)" if self.center else "") + "   [C: from center]"
        return "opposite corner   (Shift: square, or type width, Tab, height, Enter)   [F: flip the light direction]"

    def compute(self):
        if not self.points or self.cur is None:
            return [], [], "", None
        o = self.points[0]
        u, v, n = plane_axes(self.axis)
        d = self.cur - o
        du, dv = d.dot(u), d.dot(v)
        w = self.sized(0, 2 * du if self.center else du, du)
        h = self.sized(1, 2 * dv if self.center else dv, dv)
        if abs(w) < 1e-9 or abs(h) < 1e-9:
            return [], [], "", None
        a0, b0 = (-w / 2.0, -h / 2.0) if self.center else (0.0, 0.0)
        corners = [o + u * (a0 + x) + v * (b0 + y) for x, y in ((0, 0), (w, 0), (w, h), (0, h))]
        c = o + u * (a0 + w / 2.0) + v * (b0 + h / 2.0)
        emit = n if self.flip else -n
        tip = c + emit * (min(abs(w), abs(h)) * 0.5)
        info = f"Width {self.fmt(abs(w))}   Height {self.fmt(abs(h))}"
        return corners + [corners[0]], [[c, tip]], info, ("area", c, u.copy(), v.copy(), n.copy(), abs(w), abs(h), bool(self.flip))

    def build(self, context, spec):
        _, c, u, v, n, w, h, flip = spec
        z = -n if flip else n                      # une lumière surface éclaire vers -Z local
        vv = -v if flip else v                     # repère direct
        rot = Matrix((u, vv, z)).transposed()
        obj = self.new_light(context, c, rot)
        obj.data.shape = 'RECTANGLE'
        obj.data.size = w
        obj.data.size_y = h


def camera_frustum(p0, p1, lens, aim=None):
    """(coins du cadre, guides) d'une caméra en p0 qui regarde vers p1 (ou dans la direction aim), à la focale donnée."""
    d = (p1 - p0) if aim is None else aim
    L = d.length
    f = d / L if L > 1e-9 else Vector((0.0, 0.0, -1.0))
    right = f.cross(Vector((0.0, 0.0, 1.0)))
    if right.length < 1e-6:
        right = Vector((1.0, 0.0, 0.0))
    right.normalize()
    up = right.cross(f)
    w = L * 36.0 / lens
    h = w * 9.0 / 16.0
    c = p0 + f * L
    corners = [c + right * sx * w / 2.0 + up * sy * h / 2.0 for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    return corners, [[p0, k] for k in corners]


class DESSIN_OT_camera(LightBase):
    bl_idname = "dessin.camera_add"
    bl_label = "Camera"
    bl_description = ("Places a camera (50 mm, like Blender's own): a first click for its position, a second click to aim it "
                      "in steps of 90° (Shift: free aim)")

    TITLE = "Camera"
    NEEDED = 2
    NUMFIELDS = 0
    PLANAR = False
    LENS = 50.0
    SIZE = 1.0

    def prompt(self):
        if not self.points:
            return "position of the camera (50 mm)"
        return "click to set the direction (steps of 90°)   (Shift: free aim)"

    def aim(self, p0):
        """Direction de visée : l'axe du plan de construction le plus proche du curseur (cran de 90°), ou libre avec Maj."""
        u, v, _ = plane_axes(self.axis)
        if not self.points or self.cur is None:
            return v.copy()
        d = self.cur - p0
        if d.length < 1e-9:
            return v.copy()
        if self.shift:
            return d.normalized()
        du, dv = d.dot(u), d.dot(v)
        if abs(du) >= abs(dv):
            return u * (1.0 if du >= 0 else -1.0)
        return v * (1.0 if dv >= 0 else -1.0)

    def compute(self):
        if self.cur is None:
            return [], [], "", None
        p0 = self.points[0] if self.points else self.cur
        f = self.aim(p0)
        L = self.SIZE * self.LENS / 36.0
        corners, guides = camera_frustum(p0, p0, self.LENS, f * L)
        info = f"Focal length {self.LENS:g} mm   Direction ({f.x:.2f}, {f.y:.2f}, {f.z:.2f})"
        spec = ("camera", p0.copy(), f.copy()) if self.points else None
        return corners + [corners[0]], guides, info, spec

    def build(self, context, spec):
        _, p0, f = spec
        cam = bpy.data.cameras.new("Camera")
        cam.lens = self.LENS
        obj = _link_object(context, "Camera", cam)
        obj.location = p0
        obj.rotation_euler = f.to_track_quat('-Z', 'Y').to_euler()
        if context.scene.camera is None:
            context.scene.camera = obj


class DESSIN_OT_camera_target(LightBase):
    bl_idname = "dessin.camera_target"
    bl_label = "Camera with Target"
    bl_description = ("Places a camera (50 mm) with a first click and an Empty with a second click: the camera follows the Empty "
                      "(Track To), so moving the Empty re-aims the camera")

    TITLE = "Camera with Target"
    NEEDED = 2
    NUMFIELDS = 0
    PLANAR = False
    LENS = 50.0

    def prompt(self):
        if not self.points:
            return "click to place the camera (50 mm)"
        return "click to place the target Empty (the camera looks at it)"

    def compute(self):
        if not self.points or self.cur is None:
            return [], [], "", None
        p0 = self.points[0]
        L = (self.cur - p0).length
        if L < 1e-9:
            return [], [], "", None
        corners, guides = camera_frustum(p0, self.cur, self.LENS)
        info = f"Focal length {self.LENS:g} mm   Distance {self.fmt(L)}"
        return corners + [corners[0]], guides + [[p0, self.cur]], info, ("camera", p0.copy(), self.cur.copy(), self.LENS, L)

    def build(self, context, spec):
        _, p0, p1, lens, L = spec
        cam = bpy.data.cameras.new("Camera")
        cam.lens = lens
        size = 1.0                      # taille d'affichage par défaut de Blender, comme l'outil Camera
        cam.display_size = size
        obj = _link_object(context, "Camera", cam)
        obj.location = p0
        obj.rotation_euler = self.aim_quat(p0, p1).to_euler()
        target = bpy.data.objects.new("Camera Target", None)
        target.empty_display_type = 'PLAIN_AXES'
        target.empty_display_size = 0.5
        target.location = p1
        context.view_layer.active_layer_collection.collection.objects.link(target)
        con = obj.constraints.new('TRACK_TO')
        con.target = target
        con.track_axis = 'TRACK_NEGATIVE_Z'
        con.up_axis = 'UP_Y'
        target.select_set(True)
        if context.scene.camera is None:
            context.scene.camera = obj


_GUMBALL_TOOLS = ("builtin.select", "builtin.select_box", "builtin.select_circle", "builtin.select_lasso",
                  "dessin.selection_boite_tool", "dessin.selection_lasso_tool",
                  "dessin.selection_rect_tool", "dessin.selection_cercle_tool")


def _gz_set(gz, **kw):
    for k, v in kw.items():
        try:
            setattr(gz, k, v)
        except (AttributeError, TypeError, ValueError):
            pass


def _axis_matrix(origin, axis, scale):
    q = Vector((0.0, 0.0, 1.0)).rotation_difference(axis)
    return Matrix.Translation(origin) @ q.to_matrix().to_4x4() @ Matrix.Scale(scale, 4)


_GB_FLAT = {"t": 0.0, "sig": None, "res": frozenset()}


def gumball_flat_axes(context, axes):
    """Indices des axes du Gumball le long desquels la sélection n'a aucune épaisseur (ex. un Plane en Z) : pas d'échelle possible."""
    sig = None
    try:
        now = time.monotonic()
        sig = (context.mode, tuple(round(c, 4) for a in axes for c in a))
        if sig == _GB_FLAT["sig"] and now - _GB_FLAT["t"] < 0.25:
            return _GB_FLAT["res"]
        pts = []
        if context.mode in {'EDIT_MESH', 'EDIT_CURVE'}:
            sel = edit_selection(context) if context.mode == 'EDIT_MESH' else curve_edit_selection(context)
            if not sel:
                return frozenset()
            allp = np.vstack([w for _o, _i, w in sel])
            if len(allp) > 20000:
                allp = allp[::max(1, len(allp) // 20000)]
            pts = allp
        else:
            sel = expand_groups(context, context.selected_objects)
            lst = []
            for o in sel:
                if o.type == 'EMPTY' or not o.bound_box:
                    lst.append(tuple(o.matrix_world.translation))
                else:
                    mw = o.matrix_world
                    lst += [tuple(mw @ Vector(c)) for c in o.bound_box]
            if not lst:
                return frozenset()
            pts = np.array(lst, dtype=float)
        ext = pts.max(axis=0) - pts.min(axis=0)
        diag = float(np.linalg.norm(ext)) or 1.0
        flat = set()
        for i in range(3):
            d = np.array([axes[i].x, axes[i].y, axes[i].z])
            pr = pts @ d
            if float(pr.max() - pr.min()) <= max(1e-6, diag * 1e-5):
                flat.add(i)
        res = frozenset(flat) if len(flat) < 3 else frozenset()
    except (AttributeError, RuntimeError, ReferenceError, TypeError, ValueError):
        res = frozenset()
    _GB_FLAT.update(t=time.monotonic(), sig=sig, res=res)
    return res


def _late_imports():
    pass
