"""Wanderer CAD : Solides : boîte, cylindre, cône, pyramide, sphère, tore, tube."""

import bpy
import math
import time
from bpy_extras.view3d_utils import region_2d_to_origin_3d, region_2d_to_vector_3d
from mathutils import Vector

from .core import TAU, _link_object, arc_samples, edit_add_geometry, grid_snap_len, grid_snap_step, plane_axes
from .drawing import find_window_region, region_rv3d
from .base import DessinBase, view_height


# --------------------------------------------------------------------------
# Solides (boîte, sphère, cylindre, cône, pyramide, tore...) : maillages fermés
# --------------------------------------------------------------------------

def ring_pts(c, u, v, r, seg, start=0.0):
    return [c + (u * math.cos(start + TAU * i / seg) + v * math.sin(start + TAU * i / seg)) * r
            for i in range(seg)]


def orient_outward(verts, faces):
    """Retourne les faces si le volume signé est négatif : les normales regardent toujours vers l'extérieur."""
    vol = 0.0
    for f in faces:
        a = Vector(verts[f[0]])
        for i in range(1, len(f) - 1):
            vol += a.dot(Vector(verts[f[i]]).cross(Vector(verts[f[i + 1]])))
    if vol < 0.0:
        faces = [list(reversed(f)) for f in faces]
    return faces


def box_geo(o, u, v, n, w, d, h, center):
    a0, b0 = (-w / 2.0, -d / 2.0) if center else (0.0, 0.0)
    uv = [(a0, b0), (a0 + w, b0), (a0 + w, b0 + d), (a0, b0 + d)]
    verts = [o + u * a + v * b for a, b in uv] + [o + u * a + v * b + n * h for a, b in uv]
    faces = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    return verts, faces, None


def frustum_geo(o, u, v, n, r1, r2, h, seg, start):
    """Cylindre (r1 = r2), cône (r2 = 0), tronc de cône ; seg petit -> pyramide / tronc de pyramide."""
    verts = ring_pts(o, u, v, r1, seg, start)
    faces = [list(range(seg - 1, -1, -1))]
    apex = r2 < 1e-9
    if apex:
        verts.append(o + n * h)
        for i in range(seg):
            faces.append([i, (i + 1) % seg, seg])
    else:
        verts += ring_pts(o + n * h, u, v, r2, seg, start)
        faces.append(list(range(seg, 2 * seg)))
        for i in range(seg):
            j = (i + 1) % seg
            faces.append([i, j, seg + j, seg + i])
    smooth = None
    if seg >= 16:
        smooth = [False] + ([True] * seg) + ([False] if not apex else [])
        if not apex:
            smooth = [False, False] + [True] * seg
    return verts, faces, smooth


def sphere_geo(o, U, V, N, seg, rings, cut=None):
    """Sphère / ellipsoïde de demi-axes U, V, N ; cut = fraction (-1..1) de N où l'on tranche, ou None."""
    lat_max = math.pi / 2.0 if cut is None else math.asin(max(-0.999, min(0.999, cut)))
    full = cut is None
    verts = [o - N]
    nrings = rings - 1 if full else rings
    for k in range(1, nrings + 1):
        lat = -math.pi / 2.0 + (lat_max + math.pi / 2.0) * k / rings
        cl, sl = math.cos(lat), math.sin(lat)
        for i in range(seg):
            t = TAU * i / seg
            verts.append(o + U * (cl * math.cos(t)) + V * (cl * math.sin(t)) + N * sl)
    if full:
        verts.append(o + N)
    faces = [[0, 1 + (i + 1) % seg, 1 + i] for i in range(seg)]
    for k in range(nrings - 1):
        b0 = 1 + k * seg
        b1 = b0 + seg
        for i in range(seg):
            j = (i + 1) % seg
            faces.append([b0 + i, b0 + j, b1 + j, b1 + i])
    last = 1 + (nrings - 1) * seg
    if full:
        top = len(verts) - 1
        for i in range(seg):
            faces.append([last + i, last + (i + 1) % seg, top])
        smooth = [True] * len(faces)
    else:
        faces.append(list(range(last, last + seg)))
        smooth = [True] * (len(faces) - 1) + [False]
    return verts, faces, smooth


def torus_geo(o, u, v, n, R, r, sa=48, sb=24):
    verts = []
    for i in range(sa):
        a = TAU * i / sa
        d = u * math.cos(a) + v * math.sin(a)
        for j in range(sb):
            b = TAU * j / sb
            verts.append(o + d * (R + r * math.cos(b)) + n * (r * math.sin(b)))
    faces = []
    for i in range(sa):
        i2 = (i + 1) % sa
        for j in range(sb):
            j2 = (j + 1) % sb
            faces.append([i * sb + j, i2 * sb + j, i2 * sb + j2, i * sb + j2])
    return verts, faces, [True] * len(faces)


def tube_geo(o, u, v, n, ro, ri, h, seg=48):
    ob = ring_pts(o, u, v, ro, seg)
    ot = ring_pts(o + n * h, u, v, ro, seg)
    ib = ring_pts(o, u, v, ri, seg)
    it = ring_pts(o + n * h, u, v, ri, seg)
    verts = ob + ot + ib + it
    faces, smooth = [], []
    for i in range(seg):
        j = (i + 1) % seg
        faces.append([i, j, seg + j, seg + i])                       # extérieur
        smooth.append(True)
    for i in range(seg):
        j = (i + 1) % seg
        faces.append([2 * seg + i, 3 * seg + i, 3 * seg + j, 2 * seg + j])  # intérieur
        smooth.append(True)
    for i in range(seg):
        j = (i + 1) % seg
        faces.append([seg + i, seg + j, 3 * seg + j, 3 * seg + i])   # dessus
        smooth.append(False)
        faces.append([i, 2 * seg + i, 2 * seg + j, j])               # dessous
        smooth.append(False)
    return verts, faces, smooth


def build_solid(context, name, verts, faces, smooth, origin):
    """Objet maillage fermé dont l'origine est le premier point cliqué."""
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(p - origin) for p in verts], [], faces)
    me.update()
    if smooth is not None:
        try:
            me.polygons.foreach_set("use_smooth", smooth)
        except (AttributeError, TypeError, RuntimeError, ValueError):
            pass
    obj = _link_object(context, name, me)
    obj.location = origin
    return obj


class DessinSolid(DessinBase):
    """Base des solides (classe non enregistrée). Chaque étape = un clic ; chaque dimension peut être saisie."""

    SOLID_NAME = "Solide"
    HEIGHT_AT = ()   # valeurs de len(self.points) où le curseur règle une hauteur (le long de la normale)
    SIDES = False    # nombre de côtés réglable (↑ / ↓)

    # ---- aides de calcul ----
    def frame(self):
        u, v, n = plane_axes(self.axis)
        return self.points[0], u, v, n

    def pts(self):
        return list(self.points) + [self.cur]

    def radial(self, i, p, o, u, v):
        d = p - o
        r = math.hypot(d.dot(u), d.dot(v))
        t = self.typed_value(i)
        return abs(t) if t is not None else r

    def vert(self, i, p, o, n):
        h = (p - o).dot(n)
        return self.sized(i, h, h)

    def typed_height(self, i):
        h = self.sized(i, 0.0, 1.0)
        return h if abs(h) > 1e-9 else None

    def lock_allowed(self):
        return self.LOCK_OK and len(self.points) not in self.HEIGHT_AT

    def can_confirm_typed(self):
        return True

    def typed_complete(self):
        return all(self.typed_value(i) is not None for i in range(self.NUMFIELDS))

    # ---- curseur en mode hauteur ----
    def update_cursor(self, context, event):
        if len(self.points) not in self.HEIGHT_AT:
            return super().update_cursor(context, event)
        region = find_window_region(self.area, event.mouse_x, event.mouse_y)
        if region is None or self.mouse_over_ui(event):
            self.snap_screen = None
            self.snap_kind = None
            try:
                self.area.tag_redraw()
            except ReferenceError:
                pass
            return
        self.region = region
        rv3d = region_rv3d(region, self.area)
        mx = event.mouse_x - region.x
        my = event.mouse_y - region.y
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
            h = grid_snap_len(view_height(base, o, n, ro, rv, rv3d), grid_snap_step(context))
        if h is not None:
            self.cur = base + n * h
        elif self.cur is None:
            self.cur = base.copy()
        self.refresh(context)

    # ---- étapes ----
    STAGE_FIELD = {}   # étape (nb de points posés) -> champ de saisie à activer ; par défaut étape - 1

    def advance_field(self):
        k = len(self.points)
        self.field = min(self.STAGE_FIELD.get(k, max(0, k - 1)), self.NUMFIELDS - 1)

    def click(self, context):
        super().click(context)
        if not self.finished:
            self.advance_field()

    def finish_shape(self, context):
        """Entrée avec saisie : étape suivante, ou construction si toutes les dimensions sont connues."""
        _, _, _, spec = self.compute()
        last_stage = len(self.points) >= self.NEEDED - 1
        if spec is not None and (last_stage or self.typed_complete()):
            self.build(context, spec)
            self.finished = True
            self.reset_state()
            return
        if last_stage:
            self.report({'WARNING'}, "Invalid shape")
            return
        self.points.append(self.cur.copy())
        self.lock = None
        self.advance_field()
        self.refresh(context)

    def build(self, context, spec):
        if spec[0] != 'solid':
            return super().build(context, spec)
        _, name, fn, args = spec
        verts, faces, smooth = fn(*args)
        faces = orient_outward(verts, faces)
        if context.mode == 'EDIT_MESH':
            return edit_add_geometry(context, verts, [], faces)
        return build_solid(context, name, verts, faces, smooth, self.points[0].copy())

    def modal(self, context, event):
        if (self.SIDES and event.value == 'PRESS' and event.type in {'UP_ARROW', 'DOWN_ARROW'}
                and self.area is not None and context.area is not None
                and find_window_region(self.area, event.mouse_x, event.mouse_y) is not None
                and not self.mouse_over_ui(event)):
            step = 1 if event.type == 'UP_ARROW' else -1
            self.sides = max(3, min(64, self.sides + step))
            self._sides_buf = ""
            self.refresh(context)
            return {'RUNNING_MODAL'}
        if (self.SIDES and not self.points and event.value == 'PRESS' and not (event.ctrl or event.alt or event.oskey)
                and self.area is not None and context.area is not None
                and find_window_region(self.area, event.mouse_x, event.mouse_y) is not None
                and not self.mouse_over_ui(event)):
            # avant le premier point : taper un nombre fixe le nombre de côtés
            ch = event.unicode
            buf = getattr(self, "_sides_buf", "")
            if time.time() - getattr(self, "_sides_time", 0.0) >= 2.0:
                buf = ""
            if ch and ch in "0123456789":
                nb = (buf + ch).lstrip("0")
                if nb and int(nb) > 64:
                    nb = ch.lstrip("0")
                self._sides_buf, self._sides_time = nb, time.time()
                if nb:
                    self.sides = max(3, min(64, int(nb)))
                self.refresh(context)
                return {'RUNNING_MODAL'}
            if event.type == 'BACK_SPACE' and buf:
                self._sides_buf = buf[:-1]
                if self._sides_buf:
                    self.sides = max(3, min(64, int(self._sides_buf)))
                self.refresh(context)
                return {'RUNNING_MODAL'}
            if event.type in {'RET', 'NUMPAD_ENTER', 'SPACE'} and buf:
                self._sides_buf = ""
                self.refresh(context)
                return {'RUNNING_MODAL'}
        return super().modal(context, event)

    def reset_state(self):
        super().reset_state()

    def invoke(self, context, event):
        self.sides = getattr(type(self), "DEFAULT_SIDES", 4)
        return super().invoke(context, event)

    @staticmethod
    def empty():
        return [], [], "", None


class _BoiteBody(DessinSolid):
    bl_idname = "dessin.boite"
    bl_label = "Box"
    bl_description = ("Box: first corner, opposite corner, then height (C: from center, or type width / Tab / depth / Tab / height)")

    TITLE = "Box"
    PROP = (1, 2)
    SOLID_NAME = "Box"
    NEEDED = 3
    NUMFIELDS = 3
    HAS_CENTER = True
    HEIGHT_AT = (2,)
    STAGE_FIELD = {2: 2}

    def prompt(self):
        if not self.points:
            return "first corner" + (" (center)" if self.center else "") + "   [C: from center]"
        if len(self.points) == 1:
            return "opposite corner   (Shift: square, or type width, Tab, depth, Tab, height, Enter)"
        return "height   (Shift: cube, or type the height then Enter)"

    def compute(self):
        if not self.points or self.cur is None:
            return self.empty()
        o, u, v, n = self.frame()
        pts = self.pts()
        stage = len(self.points)
        d = pts[1] - o
        du, dv = d.dot(u), d.dot(v)
        w = self.sized(0, 2 * du if self.center else du, du)
        p = self.sized(1, 2 * dv if self.center else dv, dv)
        if abs(w) < 1e-9 or abs(p) < 1e-9:
            return self.empty()
        h = self.vert(2, pts[2], o, n) if stage >= 2 else (self.typed_height(2) or 0.0)
        a0, b0 = (-w / 2.0, -p / 2.0) if self.center else (0.0, 0.0)
        uv = [(a0, b0), (a0 + w, b0), (a0 + w, b0 + p), (a0, b0 + p)]
        bot = [o + u * a + v * b for a, b in uv]
        prev = bot + [bot[0]]
        guides = []
        info = f"Width {self.fmt(abs(w))}   Depth {self.fmt(abs(p))}"
        spec = None
        if abs(h) > 1e-9:
            top = [q + n * h for q in bot]
            guides = [top + [top[0]]] + [[bot[i], top[i]] for i in range(4)]
            info += f"   Height {self.fmt(abs(h))}"
            spec = ("solid", self.SOLID_NAME, box_geo, (o, u, v, n, w, p, h, self.center))
        return prev, guides, info, spec


class DESSIN_OT_boite(_BoiteBody):
    """Registered class; the shared code lives in the unregistered base so SubD variants can inherit it."""
    bl_idname = _BoiteBody.bl_idname
    bl_label = _BoiteBody.bl_label
    bl_description = _BoiteBody.bl_description


class DessinFrustum(DessinSolid):
    """Cylindre, cône, tronc de cône, pyramide, tronc de pyramide (classe non enregistrée)."""

    KIND = 'cyl'   # cyl | cone | tcone | pyr | tpyr
    NEEDED = 3
    NUMFIELDS = 2
    HEIGHT_AT = (2,)

    def prompt(self):
        n = len(self.points)
        side = f"   [type a number or ↑ / ↓: {self.sides} sides]" if self.SIDES else ""
        if n == 0:
            return "base center"
        if n == 1:
            return "radius" + ("  (circumscribed circle)" if self.SIDES else "") + side + "   (or type the radius, Tab, the height, Enter)"
        if n == 2:
            return "height   (or type the height then Enter)"
        return "top radius" + side + "   (or type, then Enter)"

    def compute(self):
        if not self.points or self.cur is None:
            return self.empty()
        o, u, v, n = self.frame()
        pts = self.pts()
        stage = len(self.points)
        r = self.radial(0, pts[1], o, u, v)
        if r < 1e-9:
            return self.empty()
        poly = self.SIDES
        seg = self.sides if poly else 48
        start = (math.pi / seg if seg % 2 == 0 else 0.0) if poly else 0.0
        trunc = self.KIND in ('tcone', 'tpyr')
        apex = self.KIND in ('cone', 'pyr')
        h = self.vert(1, pts[2], o, n) if stage >= 2 else (self.typed_height(1) or 0.0)

        def outline(c, rr):
            ring = ring_pts(c, u, v, rr, seg, start)
            return ring + [ring[0]]
        prev = outline(o, r)
        info = (f"Radius {self.fmt(r)}" if not poly else f"Radius {self.fmt(r)}   {seg} sides")
        if abs(h) < 1e-9:
            return prev, [], info, None
        info += f"   Height {self.fmt(abs(h))}"
        top_c = o + n * h
        if trunc:
            if stage >= 3:
                r2 = self.radial(2, pts[3], o, u, v)
            else:
                t = self.typed_value(2)
                r2 = abs(t) if t is not None else None
            show_r2 = r if r2 is None else r2
        else:
            r2 = r if self.KIND in ('cyl',) else 0.0
            show_r2 = r2
        guides = []
        ring_b = ring_pts(o, u, v, r, seg, start)
        if apex:
            guides = [[q, top_c] for q in ring_b[::max(1, seg // 4)]]
        else:
            if show_r2 > 1e-9:
                guides.append(outline(top_c, show_r2))
            ring_t = ring_pts(top_c, u, v, show_r2, seg, start)
            guides += [[ring_b[i], ring_t[i]] for i in range(0, seg, max(1, seg // 4))]
        spec = None
        if trunc:
            if r2 is not None and r2 > 1e-9:
                info += f"   Top radius {self.fmt(r2)}"
                spec = ("solid", self.SOLID_NAME, frustum_geo, (o, u, v, n, r, r2, h, seg, start))
        else:
            spec = ("solid", self.SOLID_NAME, frustum_geo, (o, u, v, n, r, r2, h, seg, start))
        return prev, guides, info, spec


class _CylindreBody(DessinFrustum):
    bl_idname = "dessin.cylindre"
    bl_label = "Cylinder"
    bl_description = "Cylinder: base center, radius then height (or type radius / Tab / height)"
    TITLE = "Cylinder"
    SOLID_NAME = "Cylinder"
    KIND = 'cyl'


class DESSIN_OT_cylindre(_CylindreBody):
    """Registered class; the shared code lives in the unregistered base so SubD variants can inherit it."""
    bl_idname = _CylindreBody.bl_idname
    bl_label = _CylindreBody.bl_label
    bl_description = _CylindreBody.bl_description


class _ConeBody(DessinFrustum):
    bl_idname = "dessin.cone"
    bl_label = "Cone"
    bl_description = "Cone: base center, radius then apex height (or type radius / Tab / height)"
    TITLE = "Cone"
    SOLID_NAME = "Cone"
    KIND = 'cone'


class DESSIN_OT_cone(_ConeBody):
    """Registered class; the shared code lives in the unregistered base so SubD variants can inherit it."""
    bl_idname = _ConeBody.bl_idname
    bl_label = _ConeBody.bl_label
    bl_description = _ConeBody.bl_description


class DESSIN_OT_cone_tronque(DessinFrustum):
    bl_idname = "dessin.cone_tronque"
    bl_label = "Truncated Cone"
    bl_description = "Truncated cone: base center, radius, height then top radius (type radius / Tab / height / Tab / top radius)"
    TITLE = "Truncated Cone"
    SOLID_NAME = "Truncated Cone"
    KIND = 'tcone'
    NEEDED = 4
    NUMFIELDS = 3


class DESSIN_OT_pyramide(DessinFrustum):
    bl_idname = "dessin.pyramide"
    bl_label = "Pyramid"
    bl_description = "Pyramid: base center, radius (circumscribed circle), height; arrows ↑ / ↓: number of sides"
    TITLE = "Pyramid"
    SOLID_NAME = "Pyramid"
    KIND = 'pyr'
    SIDES = True
    DEFAULT_SIDES = 4


class DESSIN_OT_pyramide_tronquee(DessinFrustum):
    bl_idname = "dessin.pyramide_tronquee"
    bl_label = "Truncated Pyramid"
    bl_description = "Truncated pyramid: base center, radius, height then top radius; arrows ↑ / ↓: number of sides"
    TITLE = "Truncated Pyramid"
    SOLID_NAME = "Truncated Pyramid"
    KIND = 'tpyr'
    NEEDED = 4
    NUMFIELDS = 3
    SIDES = True
    DEFAULT_SIDES = 4


def _sphere_wire(c, U, V, N):
    """Équateur (aperçu) + deux méridiens (repères) d'une sphère / ellipsoïde."""
    eq = arc_samples(c, U, V, 1.0, 0.0, TAU, 64)
    m1 = arc_samples(c, U, N, 1.0, 0.0, TAU, 64)
    m2 = arc_samples(c, V, N, 1.0, 0.0, TAU, 64)
    return eq, [m1, m2]


class _SphereBody(DessinSolid):
    bl_idname = "dessin.sphere"
    bl_label = "Sphere"
    bl_description = "Sphere: center then radius (or type the radius)"
    TITLE = "Sphere"
    SOLID_NAME = "Sphere"
    NEEDED = 2
    NUMFIELDS = 1

    def prompt(self):
        return "center" if not self.points else "radius   (or type the radius then Enter)"

    def compute(self):
        if not self.points or self.cur is None:
            return self.empty()
        o, u, v, n = self.frame()
        r = self.radial(0, self.cur, o, u, v)
        if r < 1e-9:
            return self.empty()
        eq, mer = _sphere_wire(o, u * r, v * r, n * r)
        return eq, mer, f"Radius {self.fmt(r)}   Diameter {self.fmt(2 * r)}", \
            ("solid", self.SOLID_NAME, sphere_geo, (o, u * r, v * r, n * r, 48, 24, None))


class DESSIN_OT_sphere(_SphereBody):
    """Registered class; the shared code lives in the unregistered base so SubD variants can inherit it."""
    bl_idname = _SphereBody.bl_idname
    bl_label = _SphereBody.bl_label
    bl_description = _SphereBody.bl_description


class DESSIN_OT_sphere_tronquee(DessinSolid):
    bl_idname = "dessin.sphere_tronquee"
    bl_label = "Truncated Sphere"
    bl_description = ("Sphere cut by a plane: center, radius then cut height (measured from the center; type radius / Tab / height)")
    TITLE = "Truncated Sphere"
    SOLID_NAME = "Truncated Sphere"
    NEEDED = 3
    NUMFIELDS = 2
    HEIGHT_AT = (2,)

    def prompt(self):
        if not self.points:
            return "center"
        if len(self.points) == 1:
            return "radius   (or type the radius, Tab, the cut height, Enter)"
        return "cut height from the center   (or type the value then Enter)"

    def compute(self):
        if not self.points or self.cur is None:
            return self.empty()
        o, u, v, n = self.frame()
        pts = self.pts()
        stage = len(self.points)
        r = self.radial(0, pts[1], o, u, v)
        if r < 1e-9:
            return self.empty()
        eq, mer = _sphere_wire(o, u * r, v * r, n * r)
        info = f"Radius {self.fmt(r)}"
        z = self.vert(1, pts[2], o, n) if stage >= 2 else self.typed_height(1)
        if z is None:
            return eq, mer, info, None
        z = max(-0.999 * r, min(0.999 * r, z))
        rc = math.sqrt(max(r * r - z * z, 0.0))
        mer = mer + [arc_samples(o + n * z, u, v, rc, 0.0, TAU, 64)]
        info += f"   Cut at {self.fmt(z)}"
        return eq, mer, info, ("solid", self.SOLID_NAME, sphere_geo,
                               (o, u * r, v * r, n * r, 48, 24, z / r))


class DESSIN_OT_ellipsoide(DessinSolid):
    bl_idname = "dessin.ellipsoide"
    bl_label = "Ellipsoid"
    bl_description = ("Ellipsoid: center, end of the first axis, of the second axis then of the third (height); type a / Tab / b / Tab / c")
    TITLE = "Ellipsoid"
    SOLID_NAME = "Ellipsoid"
    NEEDED = 4
    NUMFIELDS = 3
    HEIGHT_AT = (3,)

    def prompt(self):
        k = len(self.points)
        if k == 0:
            return "center"
        if k == 1:
            return "end of the first axis   (or type a, Tab, b, Tab, c, Enter)"
        if k == 2:
            return "end of the second axis"
        return "end of the third axis (height)   (or type c then Enter)"

    def compute(self):
        if not self.points or self.cur is None:
            return self.empty()
        o, u, v, n = self.frame()
        pts = self.pts()
        stage = len(self.points)
        d = pts[1] - o
        du, dv = d.dot(u), d.dot(v)
        L = math.hypot(du, dv)
        a = self.radial(0, pts[1], o, u, v)
        if a < 1e-9:
            return self.empty()
        e1 = (u * du + v * dv) / L if L > 1e-9 else u.copy()
        e2 = n.cross(e1)
        if stage >= 2:
            b = abs((pts[2] - o).dot(e2))
            t = self.typed_value(1)
            if t is not None:
                b = abs(t)
        else:
            t = self.typed_value(1)
            b = abs(t) if t is not None else a
        if b < 1e-9:
            return self.empty()
        A, B = e1 * a, e2 * b
        info = f"a {self.fmt(a)}   b {self.fmt(b)}"
        eq = arc_samples(o, A, B, 1.0, 0.0, TAU, 64)
        if stage < 2 and self.typed_value(2) is None:
            return eq, [[o - A, o + A]], info, None
        c = abs(self.vert(2, pts[3], o, n)) if stage >= 3 else abs(self.typed_value(2) or 0.0)
        if c < 1e-9:
            return eq, [[o - A, o + A], [o - B, o + B]], info, None
        N = n * c
        info += f"   c {self.fmt(c)}"
        guides = [arc_samples(o, A, N, 1.0, 0.0, TAU, 64), arc_samples(o, B, N, 1.0, 0.0, TAU, 64)]
        return eq, guides, info, ("solid", self.SOLID_NAME, sphere_geo, (o, A, B, N, 48, 24, None))


class _ToreBody(DessinSolid):
    bl_idname = "dessin.tore"
    bl_label = "Torus"
    bl_description = "Torus: center, major radius then tube radius (type R / Tab / r)"
    TITLE = "Torus"
    SOLID_NAME = "Torus"
    NEEDED = 3
    NUMFIELDS = 2

    def prompt(self):
        k = len(self.points)
        if k == 0:
            return "center"
        if k == 1:
            return "major radius   (or type R, Tab, r, Enter)"
        return "tube radius"

    def compute(self):
        if not self.points or self.cur is None:
            return self.empty()
        o, u, v, n = self.frame()
        pts = self.pts()
        stage = len(self.points)
        R = self.radial(0, pts[1], o, u, v)
        if R < 1e-9:
            return self.empty()
        prev = arc_samples(o, u, v, R, 0.0, TAU, 96)
        info = f"Major radius {self.fmt(R)}"
        t = self.typed_value(1)
        if t is not None:
            r = abs(t)
        elif stage >= 2:
            d = pts[2] - o
            r = abs(math.hypot(d.dot(u), d.dot(v)) - R)
        else:
            return prev, [], info, None
        if r < 1e-9 or r >= R:
            return prev, [], info + "   (tube radius must stay below R)", None
        guides = [arc_samples(o, u, v, R + r, 0.0, TAU, 96), arc_samples(o, u, v, R - r, 0.0, TAU, 96)]
        info += f"   Tube radius {self.fmt(r)}"
        return prev, guides, info, ("solid", self.SOLID_NAME, torus_geo, (o, u, v, n, R, r, 48, 24))


class DESSIN_OT_tore(_ToreBody):
    """Registered class; the shared code lives in the unregistered base so SubD variants can inherit it."""
    bl_idname = _ToreBody.bl_idname
    bl_label = _ToreBody.bl_label
    bl_description = _ToreBody.bl_description


class DESSIN_OT_tube(DessinSolid):
    bl_idname = "dessin.tube"
    bl_label = "Tube"
    bl_description = ("Tube (hollow cylinder): center, outer radius, inner radius then height (type Ro / Tab / Ri / Tab / height)")
    TITLE = "Tube"
    SOLID_NAME = "Tube"
    NEEDED = 4
    NUMFIELDS = 3
    HEIGHT_AT = (3,)

    def prompt(self):
        k = len(self.points)
        if k == 0:
            return "base center"
        if k == 1:
            return "outer radius   (or type Ro, Tab, Ri, Tab, height, Enter)"
        if k == 2:
            return "second radius (inside or outside the first)"
        return "height   (or type the height then Enter)"

    def compute(self):
        if not self.points or self.cur is None:
            return self.empty()
        o, u, v, n = self.frame()
        pts = self.pts()
        stage = len(self.points)
        ro = self.radial(0, pts[1], o, u, v)
        if ro < 1e-9:
            return self.empty()
        prev = arc_samples(o, u, v, ro, 0.0, TAU, 96)
        info = f"Outer radius {self.fmt(ro)}"
        if stage >= 2:
            ri = self.radial(1, pts[2], o, u, v)
        else:
            t = self.typed_value(1)
            ri = abs(t) if t is not None else None
        if ri is None:
            return prev, [], info, None
        if ri < 1e-9 or abs(ri - ro) < 1e-9:
            return prev, [], info + "   (invalid second radius)", None
        if ri > ro:     # comme Rhino : le second rayon peut être à l'extérieur du premier (paroi vers l'extérieur)
            ro, ri = ri, ro
            prev = arc_samples(o, u, v, ro, 0.0, TAU, 96)
            info = f"Outer radius {self.fmt(ro)}"
        guides = [arc_samples(o, u, v, ri, 0.0, TAU, 96)]
        info += f"   Inner radius {self.fmt(ri)}"
        h = self.vert(2, pts[3], o, n) if stage >= 3 else (self.typed_height(2) or 0.0)
        if abs(h) < 1e-9:
            return prev, guides, info, None
        tc = o + n * h
        guides += [arc_samples(tc, u, v, ro, 0.0, TAU, 96), arc_samples(tc, u, v, ri, 0.0, TAU, 96)]
        for k in range(4):
            a = k * math.pi / 2
            d = u * math.cos(a) + v * math.sin(a)
            guides.append([o + d * ro, tc + d * ro])
        info += f"   Height {self.fmt(abs(h))}"
        return prev, guides, info, ("solid", self.SOLID_NAME, tube_geo, (o, u, v, n, ro, ri, h, 48))


def _late_imports():
    pass
