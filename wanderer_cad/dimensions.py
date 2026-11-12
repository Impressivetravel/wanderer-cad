"""Wanderer CAD : Cotations, annotations, texte, mesures."""

import bpy
import json
import math
import numpy as np
from mathutils import Matrix, Vector

from .core import TAU, UNIT_LABEL, UNIT_TO_M, plane_axes, plane_origin
from .drawing import _HOVER, find_window_region, project_px, px_scale, region_rv3d
from .base import DessinBase
from .selection import _project_region
from .settings import (
    _dim_replay_spec, _op_plane, arrow_extra, build_cotation, dim_owner, dim_store_def, dimension_objects,
    dimstyle_snapshot, ensure_dim_styles, rebuild_dimension,
)


class DESSIN_OT_cotation(DessinBase):
    bl_idname = "dessin.cotation"
    bl_label = "Dimension"
    bl_description = ("Measures and dimensions: two points then the position of the dimension line, with snapping. D: aligned / horizontal / vertical, X/Y/Z: lock axis. Stays active to chain measurements")

    TITLE = "Dimension"
    NEEDED = 3
    HAS_MODE = True
    MODES = ("Aligned", "Horizontal", "Vertical")
    mode = 0

    def lock_allowed(self):
        return len(self.points) == 1  # on verrouille la direction de la mesure, pas le placement de la ligne

    def prompt(self):
        n = len(self.points)
        m = self.MODES[self.mode]
        if n == 0:
            return f"first point to measure   [D: {m}]"
        if n == 1:
            return f"second point   [D: {m}]"
        return f"dimension line position   [D: {m}]   (click: create the dimension)"

    def unit_for_text(self):
        st = bpy.context.scene.dessin
        if st.unite_cote == 'SCENE':
            return self.unit_f, self.unit_label
        scale = bpy.context.scene.unit_settings.scale_length or 1.0
        return UNIT_TO_M[st.unite_cote] / scale, UNIT_LABEL[st.unite_cote]

    def text_for(self, length):
        st = bpy.context.scene.dessin
        factor, label = self.unit_for_text()
        length = length * layout_dim_factor(self)      # mise en page : cote posée sur un détail = longueur du modèle
        txt = f"{length / factor:.{st.decimales}f}"
        if st.supprimer_zeros and "." in txt:
            txt = txt.rstrip("0").rstrip(".")
        if st.unite and label:
            txt += f" {label}"
        return st.prefixe + txt + st.suffixe

    def text_height(self, mid, e):
        st = bpy.context.scene.dessin
        if st.taille_texte > 0.0:
            return st.taille_texte
        try:
            rv3d = region_rv3d(self.region, self.area)
            a = project_px(rv3d, self.region, mid)
            b = project_px(rv3d, self.region, mid + e)
            k = (b - a).length if a is not None and b is not None else 0.0  # pixels par unité
            if k > 1e-6:
                return 18.0 * px_scale() / k
        except (AttributeError, ReferenceError):
            pass
        return 0.1

    def screen_right(self):
        try:
            rv3d = region_rv3d(self.region, self.area)
            return rv3d.view_rotation @ Vector((1.0, 0.0, 0.0)), rv3d.view_rotation @ Vector((0.0, 0.0, 1.0))
        except (AttributeError, ReferenceError):
            return Vector((1.0, 0.0, 0.0)), Vector((0.0, 0.0, 1.0))

    def compute(self):
        n = len(self.points)
        self.dim_label = None
        if n == 0 or self.cur is None:
            return [], [], "", None
        st = bpy.context.scene.dessin
        u, v, nrm = _op_plane(self)
        p0 = self.points[0]
        if n == 1:
            d = self.cur - p0
            length = d.length
            if length < 1e-9:
                return [], [], "", None
            return [p0, self.cur], [], f"Length {self.text_for(length)}", None
        p1 = self.points[1]
        d = p1 - p0
        du, dv = d.dot(u), d.dot(v)
        fe = getattr(self, "fixed_e", None)
        if fe is not None:                      # cote continue / ligne de base : direction de la cote d'origine
            e = Vector(fe)
            e = e if d.dot(e) >= 0 else -e
        elif self.mode == 1:
            e = u if du >= 0 else -u
        elif self.mode == 2:
            e = v if dv >= 0 else -v
        else:
            ln = math.hypot(du, dv)
            if ln < 1e-9:
                return [], [], "", None
            e = (u * du + v * dv) / ln
        length = abs(d.dot(e))
        if length < 1e-9:
            return [], [], "", None
        f = nrm.cross(e)
        off = (self.cur - p0).dot(f)
        a = p0 + f * off
        b = p0 + e * d.dot(e) + f * off
        mid = (a + b) * 0.5
        right, towards = self.screen_right()
        te = e.copy()
        if te.dot(right) < 0 or (abs(te.dot(right)) < 1e-6 and te.dot(v) < 0):
            te = -te
        sign = 1.0 if nrm.dot(towards) >= 0 else -1.0
        Z = nrm * sign
        Y = Z.cross(te)
        h = self.text_height(mid, e)
        gap, ext, arrow = st.decalage * h, st.prolongement * h, st.fleche_taille * h
        e1 = (a - p0).normalized() if (a - p0).length > 1e-9 else f
        e2 = (b - p1).normalized() if (b - p1).length > 1e-9 else f
        text = self.text_for(length)
        if st.position_texte == 'CENTRE':
            half = 0.5 * (len(text) * 0.62 * h) + st.ecart_texte * h
            if 2.0 * half < (b - a).length:
                main = [(a, mid - e * half), (mid + e * half, b)]
            else:
                main = [(a, b)]
            loc = mid
        else:
            main = [(a, b)]
            loc = mid + Y * (st.ecart_texte * h)
        segs = main + [(p0 + e1 * min(gap, (a - p0).length), a + e1 * ext),
                       (p1 + e2 * min(gap, (b - p1).length), b + e2 * ext)]
        for tip, sgn in ((a, 1.0), (b, -1.0)):
            extra_a = arrow_extra(st.fleche_style, tip, e * sgn, f, arrow)
            if extra_a is not None:
                segs.extend(extra_a)
            elif st.fleche_style == 'TRAIT':
                dd = (e + f).normalized() * (arrow * 0.5)
                segs.append((tip - dd, tip + dd))
            else:
                back = tip + e * (arrow * sgn)
                segs.append((tip, back + f * (arrow * 0.3)))
                segs.append((tip, back - f * (arrow * 0.3)))
        self.dim_label = (loc, text)
        guides = [[x, y] for x, y in segs[len(main):]]
        thickness = 0.05 * h * st.epaisseur_trait
        spec = ("dim", {"segments": segs, "text": text, "length": length, "height": h,
                        "frame": (te, Y, Z, loc), "thickness": thickness})
        return [a, b], guides, f"Dimension {text}", spec

    def build(self, context, spec):
        if spec[0] == 'dim':
            return build_cotation(context, spec[1])
        return super().build(context, spec)

    def finish_shape(self, context):
        _, _, _, spec = self.compute()
        if spec is None:
            self.report({'WARNING'}, "Invalid dimension")
            return
        obj = self.build(context, spec)
        if obj is not None and spec[0] == 'dim':
            dim_store_def(obj, self, spec)
        self.dim_label = None
        self.reset_state()  # la commande reste active : on enchaîne les mesures
        self.refresh(context)

    def cleanup(self, context):
        self.dim_label = None
        super().cleanup(context)


def fit_circle_points(P):
    """Cercle / arc passant par les points ordonnés P (n,3) : (c, r, n, e1, e2) ou None si ce n'est pas un cercle."""
    P = np.asarray(P, dtype=np.float64)
    if len(P) < 6:
        return None
    c0 = P.mean(axis=0)
    _u, sv, vt = np.linalg.svd(P - c0, full_matrices=False)
    n = vt[2]
    e1, e2 = vt[0], vt[1]
    x, y = (P - c0) @ e1, (P - c0) @ e2
    A = np.column_stack((2.0 * x, 2.0 * y, np.ones(len(x))))
    sol, *_ = np.linalg.lstsq(A, x * x + y * y, rcond=None)
    a, b, c = sol
    r2 = c + a * a + b * b
    if r2 <= 1e-18:
        return None
    r = math.sqrt(r2)
    res = np.abs(np.hypot(x - a, y - b) - r).max()
    extent = float(np.linalg.norm(P.max(axis=0) - P.min(axis=0)))
    if res > 0.02 * r or r > 20.0 * max(extent, 1e-12):
        return None
    return c0 + a * e1 + b * e2, r, n, e1, e2


class _EdgeAdj:
    """Voisinage des segments par extrémité : {clé de sommet: [(arête, extrémité)]} servi à la demande, à partir de clés
    entières triées (numpy) et d'une recherche dichotomique. Remplace un dictionnaire Python de tous les segments, qui
    demandait plus de 2 secondes à construire dans une scène de 300 000 segments."""
    _M = (73856093, 19349663, 83492791)

    def __init__(self, edges):
        q = np.round(np.asarray(edges, dtype=np.float64).reshape(-1, 3) * 1e5).astype(np.int64)   # arête i : lignes 2i et 2i+1
        self.q = q
        h = (q[:, 0] * self._M[0]) ^ (q[:, 1] * self._M[1]) ^ (q[:, 2] * self._M[2])
        self.order = np.argsort(h, kind='stable')
        self.h = h[self.order]

    def get(self, key, default=()):
        k = np.array(key, dtype=np.int64)
        hv = (k[0:1] * self._M[0]) ^ (k[1:2] * self._M[1]) ^ (k[2:3] * self._M[2])
        lo = int(np.searchsorted(self.h, hv[0], side='left'))
        hi = int(np.searchsorted(self.h, hv[0], side='right'))
        out = []
        for j in self.order[lo:hi].tolist():
            if self.q[j, 0] == key[0] and self.q[j, 1] == key[1] and self.q[j, 2] == key[2]:
                out.append((j // 2, j % 2))
        return out if out else default


def edge_chain_circle(edges, adj, e0, cos_min=0.55, limit=20000):
    """Suit à partir de l'arête e0 les arêtes qui se prolongent sans angle vif, puis ajuste un cercle.
    adj : {clé de sommet: [(arête, extrémité)]}. Retourne (c, r, n, e1, e2, points ordonnés, tol) ou None."""
    def key(pt):
        return (round(pt[0] * 1e5), round(pt[1] * 1e5), round(pt[2] * 1e5))
    seen = {e0}
    pts = [edges[e0][0], edges[e0][1]]
    closed = False
    for end in (1, 0):
        cur, cend = e0, end
        for _ in range(limit):
            tip = edges[cur][cend]
            tail = edges[cur][1 - cend]
            d_in = tip - tail
            ln = np.linalg.norm(d_in)
            if ln < 1e-12:
                break
            d_in = d_in / ln
            best, best_dot = None, cos_min
            for (e, ei) in adj.get(key(tip), ()):
                if e in seen:
                    continue
                other = edges[e][1 - ei]
                d_out = other - tip
                lo = np.linalg.norm(d_out)
                if lo < 1e-12:
                    continue
                dot = float(d_in @ d_out) / lo
                if dot > best_dot:
                    best, best_dot = (e, ei), dot
            if best is None:
                if any(e == e0 and True for (e, _i) in adj.get(key(tip), ()) if e != cur) and len(seen) > 2:
                    closed = True
                break
            e, ei = best
            seen.add(e)
            nxt = edges[e][1 - ei]
            if end == 1:
                pts.append(nxt)
            else:
                pts.insert(0, nxt)
            cur, cend = e, 1 - ei
    if len(pts) < 6:
        return None
    P = np.array(pts)
    fit = fit_circle_points(P)
    if fit is None:
        return None
    c, r, n, e1, e2 = fit
    steps = np.linalg.norm(np.diff(P, axis=0), axis=1)
    return (c, r, n, e1, e2, P, max(2.0 * float(np.median(steps)), 1e-6))


class DESSIN_OT_cotation_rayon(DessinBase):
    bl_idname = "dessin.cotation_rayon"
    bl_label = "Radius / Diameter"
    bl_description = ("Radius or diameter dimension: click a circle or an arc drawn with the toolkit, then the position of the "
                      "dimension. D: radius / diameter. Stays active to chain dimensions")

    TITLE = "Radius / Diameter"
    NEEDED = 2
    HAS_MODE = True
    MODES = ("Radius", "Diameter")
    mode = 0
    PLANAR = False
    LOCK_OK = False

    unit_for_text = DESSIN_OT_cotation.unit_for_text
    text_for = DESSIN_OT_cotation.text_for
    text_height = DESSIN_OT_cotation.text_height
    screen_right = DESSIN_OT_cotation.screen_right

    def lock_allowed(self):
        return False

    def prompt(self):
        m = self.MODES[self.mode]
        if not self.points:
            return f"click a circle or an arc   [D: {m}]"
        return f"position of the dimension   [D: {m}]   (click: create the dimension)"

    def invoke(self, context, event):
        self.circ = None
        self._mouse = None
        self.dim_label = None
        return super().invoke(context, event)

    def update_cursor(self, context, event):
        region = find_window_region(self.area, event.mouse_x, event.mouse_y)
        self._mouse = (event.mouse_x - region.x, event.mouse_y - region.y) if region is not None else None
        super().update_cursor(context, event)

    def find_circle(self):
        """Cercle / arc le plus proche du curseur (en pixels), ou None."""
        data = getattr(self, "snap_data", None)
        circles = getattr(data, "circles", ())
        if self._mouse is None or self.region is None:
            return None
        try:
            rv3d = region_rv3d(self.region, self.area)
            persp = np.array(rv3d.perspective_matrix, dtype=np.float64)
        except (AttributeError, ReferenceError):
            return None
        mx, my = self._mouse
        if circles:
            # tous les cercles sont projetés à l'écran une seule fois par vue (et non un par un à chaque mouvement de souris :
            # un plan de plusieurs centaines de cercles ramait)
            sig = (persp.tobytes(), self.region.width, self.region.height)
            cs = getattr(self, "_circ_scr", None)
            if cs is None or cs[0] != sig or cs[1] is not circles:
                try:
                    P = np.vstack([np.asarray(info[5], dtype=np.float64).reshape(-1, 3) for info in circles])
                    owner = np.repeat(np.arange(len(circles)), [len(info[5]) for info in circles])
                    sx, sy, ok = _project_region(P, persp, self.region)
                    cs = (sig, circles, sx, sy, ok, owner)
                except (ValueError, TypeError):
                    cs = (sig, circles, None, None, None, None)
                self._circ_scr = cs
            if cs[2] is not None and len(cs[2]):
                d = np.hypot(cs[2] - mx, cs[3] - my)
                d[~cs[4]] = np.inf
                i = int(np.argmin(d))
                if float(d[i]) < 25.0 * px_scale():
                    return circles[int(cs[5][i])]
        return self.find_edge_circle(data, persp, mx, my)

    def find_edge_circle(self, data, persp, mx, my):
        """Cercle ou arc formé par des arêtes de maillage / de courbe sous le curseur (formes en mode « Mesh »)."""
        edges = getattr(data, "edges", None)
        if edges is None or len(edges) < 6:
            return None
        # projection écran de tous les segments : une fois par vue, pas à chaque mouvement de souris
        sig = (persp.tobytes(), self.region.width, self.region.height)
        es = getattr(self, "_edge_scr", None)
        if es is None or es[0] != sig or es[1] is not edges:
            sxa, sya, oka = _project_region(edges[:, 0], persp, self.region)
            sxb, syb, okb = _project_region(edges[:, 1], persp, self.region)
            es = (sig, edges, sxa, sya, sxb, syb, oka & okb, np.minimum(sxa, sxb), np.maximum(sxa, sxb),
                  np.minimum(sya, syb), np.maximum(sya, syb))
            self._edge_scr = es
        _s, _e, sxa, sya, sxb, syb, eok, exmin, exmax, eymin, eymax = es
        R = 14.0 * px_scale()
        cand = np.nonzero(eok & (exmin <= mx + R) & (exmax >= mx - R) & (eymin <= my + R) & (eymax >= my - R))[0]
        if not len(cand):
            return None
        ax, ay = sxa[cand], sya[cand]
        dx, dy = sxb[cand] - ax, syb[cand] - ay
        l2 = dx * dx + dy * dy
        t = np.clip(((mx - ax) * dx + (my - ay) * dy) / np.where(l2 > 1e-12, l2, 1.0), 0.0, 1.0)
        dist = np.hypot(ax + t * dx - mx, ay + t * dy - my)
        j = int(np.argmin(dist))
        if dist[j] > R:
            return None
        e0 = int(cand[j])
        cache = getattr(self, "_edge_cache", None)
        if cache is None or cache[0] is not edges:
            cache = (edges, _EdgeAdj(edges), {})
            self._edge_cache = cache
        _e, adj, found = cache
        if e0 not in found:
            found[e0] = edge_chain_circle(edges, adj, e0)
        return found[e0]

    def geometry(self, info, q):
        """(c, r, u, n) : centre, rayon, direction du centre vers q dans le plan du cercle, normale."""
        c, r, n, e1, e2, _P, _tol = info
        c, n, e1 = Vector(c), Vector(n), Vector(e1)
        qv = Vector(q)
        w = qv - c
        w = w - n * w.dot(n)
        u = w.normalized() if w.length > 1e-9 else e1
        return c, float(r), u, n, w.length

    def compute(self):
        self.dim_label = None
        if self.cur is None:
            return [], [], "", None
        st = bpy.context.scene.dessin
        if not self.points:
            info = self.find_circle()
            self.circ = info
            if info is None:
                return [], [], "No circle or arc under the cursor", None
            P = [Vector(p) for p in info[5]]
            r = float(info[1])
            val = r if self.mode == 0 else 2.0 * r
            return P, [], ("R " if self.mode == 0 else "Ø ") + self.text_for(val), None
        info = self.circ
        if info is None:
            return [], [], "", None
        c, r, u, nrm, wl = self.geometry(info, self.cur)
        if r < 1e-9:
            return [], [], "", None
        right, towards = self.screen_right()
        te = u.copy()
        if te.dot(right) < 0 or (abs(te.dot(right)) < 1e-6 and te.dot(towards) < 0):
            te = -te
        sign = 1.0 if nrm.dot(towards) >= 0 else -1.0
        Z = nrm * sign
        Y = Z.cross(te)
        h = self.text_height(c + u * r, u)
        arrow = st.fleche_taille * h
        f = nrm.cross(u)
        P = c + u * r
        if self.mode == 0:
            text = "R" + self.text_for(r)
            end = c + u * wl if wl > r else P
            value = r
            if wl > r:
                loc = end + te * (len(text) * 0.31 * h + st.ecart_texte * h) * (1.0 if te.dot(u) >= 0 else -1.0)
                main = [(c, end)]
            elif st.position_texte == 'CENTRE':
                loc = (c + P) * 0.5
                half = 0.5 * (len(text) * 0.62 * h) + st.ecart_texte * h
                if 2.0 * half < r:
                    main = [(c, loc - u * half), (loc + u * half, P)]
                else:
                    main = [(c, P)]
            else:
                loc = (c + P) * 0.5 + Y * (st.ecart_texte * h)
                main = [(c, P)]
            segs = list(main)
            tips = [(P, -u)]
            cross = 0.5 * arrow
            segs.append((c - te * cross, c + te * cross))     # croix au centre
            segs.append((c - Y * cross, c + Y * cross))
        else:
            text = "Ø" + self.text_for(2.0 * r)
            value = 2.0 * r
            A, B = c - u * r, c + u * r
            loc = c if st.position_texte == 'CENTRE' else c + Y * (st.ecart_texte * h)
            if st.position_texte == 'CENTRE':
                half = 0.5 * (len(text) * 0.62 * h) + st.ecart_texte * h
                if 2.0 * half < 2.0 * r:
                    main = [(A, c - u * half), (c + u * half, B)]
                else:
                    main = [(A, B)]
            else:
                main = [(A, B)]
            segs = list(main)
            tips = [(A, u), (B, -u)]
        for tip, inward in tips:
            extra_a = arrow_extra(st.fleche_style, tip, inward, f, arrow)
            if extra_a is not None:
                segs.extend(extra_a)
            elif st.fleche_style == 'TRAIT':
                dd = (inward + f).normalized() * (arrow * 0.5)
                segs.append((tip - dd, tip + dd))
            else:
                back = tip + inward * arrow
                segs.append((tip, back + f * (arrow * 0.3)))
                segs.append((tip, back - f * (arrow * 0.3)))
        self.dim_label = (loc, text)
        thickness = 0.05 * h * st.epaisseur_trait
        spec = ("dim", {"segments": segs, "text": text, "length": value, "height": h,
                        "frame": (te, Y, Z, loc), "thickness": thickness})
        ring = [Vector(p) for p in info[5]]
        return ring, [list(s) for s in segs[len(main):]], f"{text}", spec

    def click(self, context):
        if not self.points:
            if self.find_circle() is None:
                self.report({'INFO'}, "Click a circle or an arc")
                return
            self.circ = self.find_circle()
            self.points.append(Vector(self.circ[0]))
            self.refresh(context)
            return
        self.finish_shape(context)

    def build(self, context, spec):
        if spec[0] == 'dim':
            return build_cotation(context, spec[1])
        return super().build(context, spec)

    def finish_shape(self, context):
        _, _, _, spec = self.compute()
        if spec is None:
            self.report({'WARNING'}, "Invalid dimension")
            return
        obj = self.build(context, spec)
        if obj is not None and spec[0] == 'dim':
            dim_store_def(obj, self, spec)
        self.dim_label = None
        self.circ = None
        self.reset_state()
        self.refresh(context)

    def cleanup(self, context):
        self.dim_label = None
        super().cleanup(context)


class DESSIN_OT_center_mark(DessinBase):
    bl_idname = "dessin.center_mark"
    bl_label = "Center Mark"
    bl_description = ("Like DimCenterMark: click a circle, an arc or an ellipse to put a center mark on it. "
                      "D: small cross / center lines going past the curve. Stays active to chain marks")

    TITLE = "Center Mark"
    NEEDED = 2
    HAS_MODE = True
    MODES = ("Cross", "Center lines")
    mode = 0
    PLANAR = False
    LOCK_OK = False

    text_height = DESSIN_OT_cotation.text_height
    find_circle = DESSIN_OT_cotation_rayon.find_circle
    find_edge_circle = DESSIN_OT_cotation_rayon.find_edge_circle

    def lock_allowed(self):
        return False

    def prompt(self):
        return f"click a circle, an arc or an ellipse   [D: {self.MODES[self.mode]}]   (click: create the center mark)"

    def invoke(self, context, event):
        self._mouse = None
        return super().invoke(context, event)

    def update_cursor(self, context, event):
        region = find_window_region(self.area, event.mouse_x, event.mouse_y)
        self._mouse = (event.mouse_x - region.x, event.mouse_y - region.y) if region is not None else None
        super().update_cursor(context, event)

    def mark_spec(self, info):
        c, r, n, e1, _e2, _P, _tol = info
        c, n, e1 = Vector(c), Vector(n), Vector(e1)
        if r < 1e-9:
            return None, []
        try:
            ux = Vector(plane_axes(self.axis)[0])
        except (TypeError, IndexError, ValueError):
            ux = e1
        ux = ux - n * ux.dot(n)
        if ux.length < 1e-6:
            ux = e1
        ux.normalize()
        uy = n.cross(ux)
        st = bpy.context.scene.dessin
        h = self.text_height(c, ux)
        half = min(2.0 * h, 0.35 * r) if self.mode == 0 else 1.25 * float(r)
        segs = [(c - ux * half, c + ux * half), (c - uy * half, c + uy * half)]
        spec = ("dim", {"segments": segs, "text": "", "length": float(r), "height": h, "frame": (ux, uy, n, c),
                        "thickness": 0.05 * h * st.epaisseur_trait, "name": "Center mark", "notext": True})
        return spec, segs

    def compute(self):
        if self.cur is None:
            return [], [], "", None
        info = self.find_circle()
        if info is None:
            return [], [], "No circle, arc or ellipse under the cursor", None
        spec, segs = self.mark_spec(info)
        ring = [Vector(p) for p in info[5]]
        return ring, [list(s_) for s_ in segs], "Center mark", spec

    def click(self, context):
        _ring, _segs, _txt, spec = self.compute()
        if spec is None:
            self.report({'INFO'}, "Click a circle, an arc or an ellipse")
            return
        build_cotation(context, spec[1])
        self.reset_state()
        self.refresh(context)


class DESSIN_OT_cotation_angle(DessinBase):
    bl_idname = "dessin.cotation_angle"
    bl_label = "Angular Dimension"
    bl_description = ("Angle dimension: click the vertex, a point on the first side, a point on the second side, then the position of the arc. "
                      "D: inner / reflex angle. Stays active to chain dimensions")

    TITLE = "Angular Dimension"
    NEEDED = 4
    HAS_MODE = True
    MODES = ("Inner angle", "Reflex angle")
    mode = 0
    PLANAR = False
    LOCK_OK = False

    unit_for_text = DESSIN_OT_cotation.unit_for_text
    text_height = DESSIN_OT_cotation.text_height
    screen_right = DESSIN_OT_cotation.screen_right

    def lock_allowed(self):
        return False

    def prompt(self):
        n = len(self.points)
        m = self.MODES[self.mode]
        if n == 0:
            return f"vertex of the angle   [D: {m}]"
        if n == 1:
            return f"point on the first side   [D: {m}]"
        if n == 2:
            return f"point on the second side   [D: {m}]"
        return f"position of the arc   [D: {m}]   (click: create the dimension)"

    def angle_text(self, deg):
        st = bpy.context.scene.dessin
        txt = f"{deg:.{st.decimales}f}"
        if st.supprimer_zeros and "." in txt:
            txt = txt.rstrip("0").rstrip(".")
        return st.prefixe + txt + "°" + st.suffixe

    def geometry(self):
        """(c, ua, va, sweep, R, normale, legs) ou None."""
        c, p1, p2 = self.points[0], self.points[1], self.points[2]
        a, b = p1 - c, p2 - c
        la, lb = a.length, b.length
        if la < 1e-9 or lb < 1e-9:
            return None
        nrm = a.cross(b)
        if nrm.length < 1e-9 * la * lb:
            nrm = plane_axes(self.axis)[2].copy()
        else:
            nrm = nrm.normalized()
        ua = a.normalized()
        va = nrm.cross(ua)
        theta = math.atan2(b.dot(va), b.dot(ua)) % TAU
        sweep = theta if self.mode == 0 else theta - TAU
        w = self.cur - c
        w = w - nrm * w.dot(nrm)
        R = w.length if w.length > 1e-9 else 0.5 * min(la, lb)
        return c, ua, va, sweep, R, nrm, (la, lb)

    def compute(self):
        self.dim_label = None
        n = len(self.points)
        if n == 0 or self.cur is None:
            return [], [], "", None
        c = self.points[0]
        if n == 1:
            return [c, self.cur], [], "", None
        if n == 2:
            return [self.points[1], c, self.cur], [], "", None
        st = bpy.context.scene.dessin
        geo = self.geometry()
        if geo is None or abs(geo[3]) < 1e-6:
            return [], [], "", None
        c, ua, va, sweep, R, nrm, legs = geo
        sgn = 1.0 if sweep >= 0 else -1.0
        deg = abs(math.degrees(sweep))
        text = self.angle_text(deg)
        amid = sweep * 0.5
        dm = ua * math.cos(amid) + va * math.sin(amid)
        mid = c + dm * R
        h = self.text_height(mid, dm)
        gap, ext, arrow = st.decalage * h, st.prolongement * h, st.fleche_taille * h

        def arc_pairs(t0, t1):
            k = max(2, int(abs(t1 - t0) / (math.pi / 48)) + 1)
            pts = [c + (ua * math.cos(t0 + (t1 - t0) * i / k) + va * math.sin(t0 + (t1 - t0) * i / k)) * R for i in range(k + 1)]
            return list(zip(pts[:-1], pts[1:]))

        if st.position_texte == 'CENTRE':
            half = min(abs(sweep) * 0.45, (len(text) * 0.62 * h * 0.5 + st.ecart_texte * h) / max(R, 1e-9))
            main = arc_pairs(0.0, amid - sgn * half) + arc_pairs(amid + sgn * half, sweep)
        else:
            main = arc_pairs(0.0, sweep)
        d1 = ua
        d2 = ua * math.cos(sweep) + va * math.sin(sweep)
        segs = list(main)
        for d_i, L in ((d1, legs[0]), (d2, legs[1])):
            if R > L + gap:
                segs.append((c + d_i * (L + gap), c + d_i * (R + ext)))
        tg0 = va * sgn
        tg1 = (-ua * math.sin(sweep) + va * math.cos(sweep)) * -sgn
        for tip, inward, side in ((c + d1 * R, tg0, d1), (c + d2 * R, tg1, d2)):
            extra_a = arrow_extra(st.fleche_style, tip, inward, side, arrow)
            if extra_a is not None:
                segs.extend(extra_a)
            elif st.fleche_style == 'TRAIT':
                dd = (inward + side).normalized() * (arrow * 0.5)
                segs.append((tip - dd, tip + dd))
            else:
                back = tip + inward * arrow
                segs.append((tip, back + side * (arrow * 0.3)))
                segs.append((tip, back - side * (arrow * 0.3)))
        right, towards = self.screen_right()
        te = (-ua * math.sin(amid) + va * math.cos(amid)) * sgn
        if te.dot(right) < 0 or (abs(te.dot(right)) < 1e-6 and te.dot(towards) < 0):
            te = -te
        sign = 1.0 if nrm.dot(towards) >= 0 else -1.0
        Z = nrm * sign
        Y = Z.cross(te)
        if st.position_texte == 'CENTRE':
            loc, valign = mid, 'CENTER'
        elif Y.dot(dm) >= 0:
            loc, valign = mid + Y * (st.ecart_texte * h), 'BOTTOM'
        else:
            loc, valign = mid - Y * (st.ecart_texte * h), 'TOP'
        self.dim_label = (loc, text)
        thickness = 0.05 * h * st.epaisseur_trait
        spec = ("dim", {"segments": segs, "text": text, "length": deg, "height": h, "valign": valign,
                        "frame": (te, Y, Z, loc), "thickness": thickness})
        pre = [a for a, _b in main] + ([main[-1][1]] if main else [])
        return pre, [list(x) for x in segs[len(main):]], f"Angle {text}", spec

    def build(self, context, spec):
        if spec[0] == 'dim':
            return build_cotation(context, spec[1])
        return super().build(context, spec)

    def click(self, context):
        if len(self.points) == 3 and self.points[0] is not None:
            if self.cur is None:
                return
            self.finish_shape(context)
            return
        if self.cur is None:
            return
        if self.points and (self.cur - self.points[-1]).length < 1e-9:
            return
        self.points.append(self.cur.copy())
        self.refresh(context)

    def finish_shape(self, context):
        _, _, _, spec = self.compute()
        if spec is None:
            self.report({'WARNING'}, "Invalid angle")
            return
        obj = self.build(context, spec)
        if obj is not None and spec[0] == 'dim':
            dim_store_def(obj, self, spec)
        self.dim_label = None
        self.reset_state()
        self.refresh(context)

    def invoke(self, context, event):
        self.dim_label = None
        return super().invoke(context, event)

    def cleanup(self, context):
        self.dim_label = None
        super().cleanup(context)


# ---- Cotations avancées : continue / ligne de base, ordonnée, longueur d'arc, déplacement d'une cote posée ----

def pick_dimension_at(op, kinds=None, px=16.0):
    """Cote sous le curseur (objet courbe portant sa définition), ou None."""
    mouse = getattr(op, "_mouse", None)
    if mouse is None or op.region is None:
        return None
    try:
        rv3d = region_rv3d(op.region, op.area)
    except (AttributeError, ReferenceError):
        return None
    m = Vector(mouse)
    best, best_d = None, px * px_scale()
    for o in dimension_objects():
        try:
            if o.type != 'CURVE' or "dessin_dim" not in o.keys() or not o.visible_get():
                continue
            if kinds is not None and json.loads(o["dessin_dim"]).get("cls") not in kinds:
                continue
            mw = o.matrix_world
            for sp in o.data.splines:
                pts = [project_px(rv3d, op.region, mw @ Vector(p.co[:3])) for p in sp.points]
                for a, b in zip(pts, pts[1:]):
                    if a is None or b is None:
                        continue
                    ab = b - a
                    t = max(0.0, min(1.0, (m - a).dot(ab) / max(ab.length_squared, 1e-12)))
                    d = (a + ab * t - m).length
                    if d < best_d:
                        best, best_d = o, d
            for ch in o.children:
                q = project_px(rv3d, op.region, ch.matrix_world.translation)
                if q is not None and (q - m).length < best_d:
                    best, best_d = o, (q - m).length
        except (ReferenceError, ValueError, KeyError, AttributeError):
            continue
    return best


def _dim_segments_world(spec):
    if spec is None or spec[0] != 'dim':
        return []
    return [(Vector(a), Vector(b)) for a, b in spec[1]["segments"]]


def _make_dim_from_def(context, data):
    """Crée une cote à partir d'une définition (même format que celle mémorisée par les outils de cote)."""
    spec = _dim_replay_spec(data)
    if spec is None or spec[0] != 'dim':
        return None
    obj = build_cotation(context, spec[1])
    obj["dessin_dim"] = json.dumps(data)
    return obj


def _lin_dir(data):
    """Direction mesurée d'une cote linéaire mémorisée."""
    if data.get("fixed_e"):
        return Vector(data["fixed_e"]).normalized()
    if data.get("uvn"):
        u, v, n = (Vector(x) for x in data["uvn"])
    else:
        u, v, n = plane_axes(data.get("axis", 2))
    p0, p1 = Vector(data["points"][0]), Vector(data["points"][1])
    d = p1 - p0
    mode = data.get("mode", 0)
    if mode == 1:
        return u
    if mode == 2:
        return v
    w = u * d.dot(u) + v * d.dot(v)
    return w.normalized() if w.length > 1e-12 else u


class DESSIN_OT_cotation_chain(DessinBase):
    bl_idname = "dessin.cotation_chain"
    bl_label = "Continue Dimension"
    bl_description = ("Chained dimensions, like DimContinue / DimBaseline: click a linear dimension, then the next points. "
                      "D: continue (end to end) / baseline (all from the first point, stacked). Stays active")

    TITLE = "Continue Dimension"
    NEEDED = 2
    HAS_MODE = True
    MODES = ("Continue", "Baseline")
    mode = 0
    LOCK_OK = False

    def lock_allowed(self):
        return False

    def prompt(self):
        if self._base is None:
            return f"click a linear dimension to continue from   [D: {self.MODES[self.mode]}]"
        return f"next point   [D: {self.MODES[self.mode]}]   (Enter: finish)"

    def invoke(self, context, event):
        self._mouse = None
        self._base = None
        self._prev = None
        self._k = 0
        self.hilite = []
        return super().invoke(context, event)

    def update_cursor(self, context, event):
        region = find_window_region(self.area, event.mouse_x, event.mouse_y)
        self._mouse = (event.mouse_x - region.x, event.mouse_y - region.y) if region is not None else None
        super().update_cursor(context, event)

    def new_def(self):
        b = self._base
        if b is None or self.cur is None:
            return None
        data = dict(b)
        data.pop("txt", None)
        e = _lin_dir(b)
        u, v, n = (Vector(x) for x in b["uvn"]) if b.get("uvn") else plane_axes(b.get("axis", 2))
        f = n.cross(e)
        p0 = Vector(b["points"][0])
        cur0 = Vector(b["cur"])
        data["fixed_e"] = [float(x) for x in e]
        if self.mode == 0:
            data["points"] = [list(self._prev), [float(x) for x in self.cur]]
            data["cur"] = list(cur0)
        else:
            off0 = (cur0 - p0).dot(f)
            sgn = 1.0 if off0 >= 0 else -1.0
            st = bpy.context.scene.dessin
            h = st.taille_texte if st.taille_texte > 0.0 else float(b["h"])
            data["points"] = [list(p0), [float(x) for x in self.cur]]
            data["cur"] = list(cur0 + f * (sgn * 2.5 * h * (self._k + 1)))
        if (Vector(data["points"][1]) - Vector(data["points"][0])).dot(e) == 0:
            return None
        return data

    def compute(self):
        self.hilite = []
        if self._base is None:
            o = pick_dimension_at(self, kinds=("dessin.cotation", "dessin.cotation_chain"))
            if o is not None:
                mw = o.matrix_world
                self.hilite = [(mw @ Vector(sp.points[0].co[:3]), mw @ Vector(sp.points[-1].co[:3])) for sp in o.data.splines]
                return [], [], "Linear dimension", None
            return [], [], "No linear dimension under the cursor", None
        data = self.new_def()
        if data is None:
            return [], [], "", None
        spec = _dim_replay_spec(data)
        segs = _dim_segments_world(spec)
        self.dim_label = (Vector(spec[1]["frame"][3]), spec[1]["text"]) if spec else None
        return [], [[a, b] for a, b in segs], self.MODES[self.mode], spec

    def click(self, context):
        if self._base is None:
            o = pick_dimension_at(self, kinds=("dessin.cotation", "dessin.cotation_chain"))
            if o is None:
                self.report({'INFO'}, "Click a linear dimension")
                return
            self._base = json.loads(o["dessin_dim"])
            self._base["cls"] = "dessin.cotation"
            self._prev = list(self._base["points"][1])
            self._k = 0
            self.refresh(context)
            return
        data = self.new_def()
        if data is None:
            return
        obj = _make_dim_from_def(context, data)
        if obj is None:
            self.report({'WARNING'}, "Invalid dimension")
            return
        self._prev = [float(x) for x in self.cur]
        self._k += 1
        self.dim_label = None
        self.refresh(context)

    def cleanup(self, context):
        self.dim_label = None
        self.hilite = []
        super().cleanup(context)


class DESSIN_OT_cotation_ordinate(DessinBase):
    bl_idname = "dessin.cotation_ordinate"
    bl_label = "Ordinate Dimension"
    bl_description = ("Like DimOrdinate: click the base point (datum), then for each feature the point and the end of the leader. "
                      "The leader direction chooses X or Y (D: auto / X / Y). Stays active on the same datum")

    TITLE = "Ordinate Dimension"
    NEEDED = 3
    HAS_MODE = True
    MODES = ("Auto", "X datum", "Y datum")
    mode = 0
    LOCK_OK = False

    unit_for_text = DESSIN_OT_cotation.unit_for_text
    text_for = DESSIN_OT_cotation.text_for
    text_height = DESSIN_OT_cotation.text_height
    screen_right = DESSIN_OT_cotation.screen_right

    def lock_allowed(self):
        return False

    def prompt(self):
        n = len(self.points)
        m = self.MODES[self.mode]
        if n == 0:
            return f"base point (datum, 0,0)   [D: {m}]"
        if n == 1:
            return f"feature point   [D: {m}]"
        return f"end of the leader   [D: {m}]   (click: create)"

    def compute(self):
        self.dim_label = None
        n = len(self.points)
        if n == 0 or self.cur is None:
            return [], [], "", None
        if n == 1:
            return [self.points[0], self.cur], [], "", None
        st = bpy.context.scene.dessin
        u, v, nrm = _op_plane(self)
        o, p = self.points[0], self.points[1]
        d = self.cur - p
        if self.mode == 1:
            xdat = True
        elif self.mode == 2:
            xdat = False
        else:
            xdat = abs(d.dot(v)) >= abs(d.dot(u))
        meas, lead = (u, v) if xdat else (v, u)
        value = (p - o).dot(meas)
        text = self.text_for(value)
        L = d.dot(lead)
        if abs(L) < 1e-9:
            return [], [], "", None
        ld = lead if L > 0 else -lead
        end = p + ld * abs(L) + meas * d.dot(meas)
        h = self.text_height(end, ld)
        gap = st.decalage * h
        jog = d.dot(meas)
        k1 = p + ld * (abs(L) * 0.55)
        k2 = k1 + ld * (abs(L) * 0.15) + meas * jog
        segs = [(p + ld * min(gap, abs(L) * 0.3), k1), (k1, k2), (k2, end)] if abs(jog) > 1e-9 else [(p + ld * min(gap, abs(L) * 0.3), end)]
        right, towards = self.screen_right()
        te = ld.copy()
        if te.dot(right) < 0 or (abs(te.dot(right)) < 1e-6 and te.dot(towards) < 0):
            te = -te
        sign = 1.0 if nrm.dot(towards) >= 0 else -1.0
        Z = nrm * sign
        Y = Z.cross(te)
        loc = end + ld * (len(text) * 0.31 * h + st.ecart_texte * h)
        self.dim_label = (loc, text)
        spec = ("dim", {"segments": segs, "text": text, "length": value, "height": h, "valign": 'CENTER',
                        "frame": (te, Y, Z, loc), "thickness": 0.05 * h * st.epaisseur_trait})
        return [], [[a, b] for a, b in segs], f"{'X' if xdat else 'Y'} = {text}", spec

    def build(self, context, spec):
        if spec[0] == 'dim':
            return build_cotation(context, spec[1])
        return super().build(context, spec)

    def finish_shape(self, context):
        _, _, _, spec = self.compute()
        if spec is None:
            self.report({'WARNING'}, "Invalid dimension")
            return
        obj = self.build(context, spec)
        if obj is not None:
            dim_store_def(obj, self, spec)
        datum = self.points[0].copy()
        self.dim_label = None
        self.reset_state()
        self.points = [datum]           # on reste sur le même point de base (comme DimOrdinate)
        self.refresh(context)

    def cleanup(self, context):
        self.dim_label = None
        super().cleanup(context)


class DESSIN_OT_cotation_arc(DessinBase):
    bl_idname = "dessin.cotation_arc"
    bl_label = "Arc Length Dimension"
    bl_description = ("Arc length, like DimCurveLength on an arc: click an arc, then the position of the dimension arc. "
                      "Stays active to chain dimensions")

    TITLE = "Arc Length Dimension"
    NEEDED = 2
    LOCK_OK = False
    PLANAR = False

    unit_for_text = DESSIN_OT_cotation.unit_for_text
    text_for = DESSIN_OT_cotation.text_for
    text_height = DESSIN_OT_cotation.text_height
    screen_right = DESSIN_OT_cotation.screen_right
    find_circle = DESSIN_OT_cotation_rayon.find_circle
    find_edge_circle = DESSIN_OT_cotation_rayon.find_edge_circle

    def lock_allowed(self):
        return False

    def prompt(self):
        if not self.points:
            return "click an arc"
        return "position of the dimension arc   (click: create)"

    def invoke(self, context, event):
        self.circ = None
        self.arc_param = None
        self._mouse = None
        self.dim_label = None
        return super().invoke(context, event)

    def update_cursor(self, context, event):
        region = find_window_region(self.area, event.mouse_x, event.mouse_y)
        self._mouse = (event.mouse_x - region.x, event.mouse_y - region.y) if region is not None else None
        super().update_cursor(context, event)

    @staticmethod
    def arc_of(info):
        """(angle de départ, balayage) d'un arc (échantillons ordonnés), ou None pour un cercle complet."""
        c, r, n, e1, e2, P, _tol = info
        P = np.asarray(P, dtype=np.float64)
        if len(P) < 3:
            return None
        if float(np.linalg.norm(P[0] - P[-1])) < 1e-6 * max(r, 1e-9) or float(np.linalg.norm(P[0] - P[-1])) < _tol * 0.5:
            return None
        c, e1, e2 = np.asarray(c), np.asarray(e1), np.asarray(e2)
        a = np.unwrap(np.arctan2((P - c) @ e2, (P - c) @ e1))
        sweep = float(a[-1] - a[0])
        if abs(sweep) < 1e-6 or abs(sweep) > TAU - 1e-4:
            return None
        return (float(a[0]), sweep)

    def arc_geometry(self):
        c, r, n, e1, e2 = self.circ[:5]
        return Vector(c), float(r), Vector(n), Vector(e1), Vector(e2)

    def compute(self):
        self.dim_label = None
        if self.cur is None:
            return [], [], "", None
        st = bpy.context.scene.dessin
        if not self.points:
            info = self.find_circle()
            self.circ = info
            if info is None:
                return [], [], "No arc under the cursor", None
            ap = self.arc_of(info)
            if ap is None:
                return [Vector(p) for p in info[5]], [], "Full circle: click an arc", None
            return [Vector(p) for p in info[5]], [], "Arc " + self.text_for(float(info[1]) * abs(ap[1])), None
        if self.circ is None or self.arc_param is None:
            return [], [], "", None
        c, r, nrm, e1, e2 = self.arc_geometry()
        a0, sweep = self.arc_param
        w = self.cur - c
        w = w - nrm * w.dot(nrm)
        R = w.length if w.length > 1e-9 else r * 1.2
        value = r * abs(sweep)
        text = self.text_for(value)
        amid = a0 + sweep * 0.5
        dm = e1 * math.cos(amid) + e2 * math.sin(amid)
        h = self.text_height(c + dm * R, dm)
        gap, ext, arrow = st.decalage * h, st.prolongement * h, st.fleche_taille * h
        k = max(2, int(abs(sweep) / (math.pi / 48)) + 1)
        arc = [c + (e1 * math.cos(a0 + sweep * i / k) + e2 * math.sin(a0 + sweep * i / k)) * R for i in range(k + 1)]
        segs = list(zip(arc[:-1], arc[1:]))
        nmain = len(segs)
        sgn = 1.0 if sweep >= 0 else -1.0
        for ang in (a0, a0 + sweep):
            dr = e1 * math.cos(ang) + e2 * math.sin(ang)
            if abs(R - r) > gap:
                s_ = 1.0 if R > r else -1.0
                segs.append((c + dr * (r + s_ * gap), c + dr * (R + s_ * ext)))
        tg0 = (-e1 * math.sin(a0) + e2 * math.cos(a0)) * sgn
        a1 = a0 + sweep
        tg1 = (e1 * math.sin(a1) - e2 * math.cos(a1)) * sgn
        for tip, inward, ang in ((arc[0], tg0, a0), (arc[-1], tg1, a1)):
            side = e1 * math.cos(ang) + e2 * math.sin(ang)
            extra_a = arrow_extra(st.fleche_style, tip, inward, side, arrow)
            if extra_a is not None:
                segs.extend(extra_a)
            elif st.fleche_style == 'TRAIT':
                dd = (inward + side).normalized() * (arrow * 0.5)
                segs.append((tip - dd, tip + dd))
            else:
                back = tip + inward * arrow
                segs.append((tip, back + side * (arrow * 0.3)))
                segs.append((tip, back - side * (arrow * 0.3)))
        right, towards = self.screen_right()
        te = (-e1 * math.sin(amid) + e2 * math.cos(amid)) * sgn
        if te.dot(right) < 0 or (abs(te.dot(right)) < 1e-6 and te.dot(towards) < 0):
            te = -te
        sign = 1.0 if nrm.dot(towards) >= 0 else -1.0
        Z = nrm * sign
        Y = Z.cross(te)
        mid = c + dm * R
        out = 1.0 if Y.dot(dm) >= 0 else -1.0
        loc = mid + Y * (out * st.ecart_texte * h)
        valign = 'BOTTOM' if out > 0 else 'TOP'
        # symbole d'arc au-dessus du texte (petit arc, comme la cote de longueur d'arc d'AutoCAD)
        sw = max(len(text) * 0.62 * h * 0.5, 0.6 * h)
        sc_ = loc + Y * (out * 1.15 * h)
        sym = [sc_ + te * (sw * math.cos(math.radians(t))) + Y * (out * 0.35 * h * math.sin(math.radians(t)))
               for t in range(180, -1, -15)]
        segs.extend(zip(sym[:-1], sym[1:]))
        self.dim_label = (loc, text)
        spec = ("dim", {"segments": segs, "text": text, "length": value, "height": h, "valign": valign,
                        "frame": (te, Y, Z, loc), "thickness": 0.05 * h * st.epaisseur_trait})
        return [a for a, _b in segs[:nmain]] + [arc[-1]], [list(x) for x in segs[nmain:]], f"Arc length {text}", spec

    def click(self, context):
        if not self.points:
            info = self.find_circle()
            ap = self.arc_of(info) if info is not None else None
            if ap is None:
                self.report({'INFO'}, "Click an arc (not a full circle)")
                return
            self.circ = info
            self.arc_param = ap
            self.points.append(Vector(info[0]))
            self.refresh(context)
            return
        _, _, _, spec = self.compute()
        if spec is None:
            return
        obj = build_cotation(context, spec[1])
        dim_store_def(obj, self, spec)
        self.dim_label = None
        self.circ = None
        self.arc_param = None
        self.reset_state()
        self.refresh(context)

    def cleanup(self, context):
        self.dim_label = None
        super().cleanup(context)


class DESSIN_OT_cotation_edit(DessinBase):
    bl_idname = "dessin.cotation_edit"
    bl_label = "Move Dimension Line"
    bl_description = ("Moves the dimension line (or the text of a radius / ordinate dimension) of a dimension already placed: "
                      "click the dimension, then its new position. Stays active")

    TITLE = "Move Dimension Line"
    NEEDED = 2
    LOCK_OK = False
    PLANAR = False

    def lock_allowed(self):
        return False

    def prompt(self):
        return "click a dimension" if self._dim is None else "new position of the dimension line   (click: apply)"

    def invoke(self, context, event):
        self._mouse = None
        self._dim = None
        self.hilite = []
        return super().invoke(context, event)

    def update_cursor(self, context, event):
        region = find_window_region(self.area, event.mouse_x, event.mouse_y)
        self._mouse = (event.mouse_x - region.x, event.mouse_y - region.y) if region is not None else None
        super().update_cursor(context, event)

    def moved_def(self):
        try:
            data = json.loads(self._dim["dessin_dim"])
        except (ReferenceError, KeyError, ValueError):
            self._dim = None
            return None
        mw = self._dim.matrix_world
        data["cur"] = [float(x) for x in self.cur]
        return data

    def compute(self):
        self.hilite = []
        if self._dim is None:
            o = pick_dimension_at(self)
            if o is not None:
                mw = o.matrix_world
                self.hilite = [(mw @ Vector(sp.points[0].co[:3]), mw @ Vector(sp.points[-1].co[:3])) for sp in o.data.splines]
                return [], [], "Dimension", None
            return [], [], "No dimension under the cursor", None
        if self.cur is None:
            return [], [], "", None
        data = self.moved_def()
        if data is None:
            return [], [], "", None
        spec = _dim_replay_spec(data)
        segs = _dim_segments_world(spec)
        self.dim_label = (Vector(spec[1]["frame"][3]), spec[1]["text"]) if spec else None
        return [], [[a, b] for a, b in segs], "", spec

    def click(self, context):
        if self._dim is None:
            o = pick_dimension_at(self)
            if o is None:
                self.report({'INFO'}, "Click a dimension")
                return
            self._dim = o
            self.points.append(self.cur.copy() if self.cur is not None else Vector())
            self.refresh(context)
            return
        data = self.moved_def()
        if data is not None:
            self._dim["dessin_dim"] = json.dumps(data)
            try:
                rebuild_dimension(context, self._dim)
            except (RuntimeError, ReferenceError, ValueError, KeyError):
                pass
        self._dim = None
        self.dim_label = None
        self.reset_state()
        self.refresh(context)

    def cleanup(self, context):
        self.dim_label = None
        self.hilite = []
        super().cleanup(context)


class DESSIN_OT_annotation(DessinBase):
    bl_idname = "dessin.annotation"
    bl_label = "Annotation (leader)"
    bl_description = ("Text note with a leader line: click the point to point at, click where the text goes, then type the text and press Enter. "
                      "Stays active to chain notes")

    TITLE = "Annotation"
    NEEDED = 3
    PLANAR = False
    LOCK_OK = False

    unit_for_text = DESSIN_OT_cotation.unit_for_text
    text_height = DESSIN_OT_cotation.text_height
    screen_right = DESSIN_OT_cotation.screen_right

    def lock_allowed(self):
        return False

    def invoke(self, context, event):
        self.note = ""
        self.dim_label = None
        return super().invoke(context, event)

    def reset_state(self):
        super().reset_state()
        self.note = ""

    def prompt(self):
        n = len(self.points)
        if n == 0:
            return "point to point at (the arrow)"
        if n == 1:
            return "where the text goes"
        return "type the text, Enter: create   (Backspace: erase, Esc: cancel)"

    def compute(self):
        self.dim_label = None
        n = len(self.points)
        if n == 0 or self.cur is None:
            return [], [], "", None
        tip = self.points[0]
        if n == 1:
            return [tip, self.cur], [], "", None
        st = bpy.context.scene.dessin
        anchor = self.points[1]
        d = anchor - tip
        if d.length < 1e-9:
            return [], [], "", None
        nrm = plane_axes(self.axis)[2]
        right, towards = self.screen_right()
        te = right - nrm * right.dot(nrm)
        if te.length < 1e-6:
            te = plane_axes(self.axis)[0].copy()
        te = te.normalized()
        sign = 1.0 if nrm.dot(towards) >= 0 else -1.0
        Z = nrm * sign
        Y = Z.cross(te)
        h = self.text_height(anchor, te)
        arrow = st.fleche_taille * h
        inward = d.normalized()
        side = nrm.cross(inward)
        segs = [(tip, anchor)]
        extra_a = arrow_extra(st.fleche_style, tip, inward, side, arrow)
        if extra_a is not None:
            segs.extend(extra_a)
        elif st.fleche_style == 'TRAIT':
            dd = (inward + side).normalized() * (arrow * 0.5)
            segs.append((tip - dd, tip + dd))
        else:
            back = tip + inward * arrow
            segs.append((tip, back + side * (arrow * 0.3)))
            segs.append((tip, back - side * (arrow * 0.3)))
        right_side = d.dot(te) >= 0
        loc = anchor + te * (0.4 * h * (1.0 if right_side else -1.0))
        halign = 'LEFT' if right_side else 'RIGHT'
        text = self.note
        self.dim_label = (loc + te * (len(text) * 0.31 * h * (1.0 if right_side else -1.0)), text + "|")
        thickness = 0.05 * h * st.epaisseur_trait
        spec = ("dim", {"segments": segs, "text": text, "length": 0.0, "height": h, "halign": halign, "valign": 'CENTER',
                        "frame": (te, Y, Z, loc), "thickness": thickness})
        return [tip, anchor], [list(x) for x in segs[1:]], "", spec

    def click(self, context):
        if self.cur is None:
            return
        if len(self.points) < 2:
            if self.points and (self.cur - self.points[-1]).length < 1e-9:
                return
            self.points.append(self.cur.copy())
            self.refresh(context)
            return
        self.finish_shape(context)

    def finish_shape(self, context):
        if not self.note.strip():
            self.report({'INFO'}, "Type the text first")
            return
        _, _, _, spec = self.compute()
        if spec is None:
            return
        obj = build_cotation(context, spec[1])
        obj["dessin_note"] = True
        self.dim_label = None
        self.reset_state()
        self.refresh(context)

    def modal(self, context, event):
        if (len(self.points) == 2 and event.value == 'PRESS' and not (event.ctrl or event.alt or event.oskey)
                and self.area is not None and context.area is not None
                and find_window_region(self.area, event.mouse_x, event.mouse_y) is not None
                and not self.mouse_over_ui(event)):
            if event.type in {'RET', 'NUMPAD_ENTER'}:
                self.finish_shape(context)
                return {'RUNNING_MODAL'}
            if event.type == 'BACK_SPACE':
                self.note = self.note[:-1]
                self.refresh(context)
                return {'RUNNING_MODAL'}
            ch = event.unicode
            if event.type == 'SPACE':
                ch = " "
            if ch and ch.isprintable():
                self.note += ch
                self.refresh(context)
                return {'RUNNING_MODAL'}
        return super().modal(context, event)

    def cleanup(self, context):
        self.dim_label = None
        super().cleanup(context)


class DESSIN_OT_text(DessinBase):
    bl_idname = "dessin.text"
    bl_label = "Text"
    bl_description = ("Single-line text like TEXT: click the insertion point (snaps and typed coordinates work), type the text; "
                      "Enter: next line below, Enter on an empty line: finish. Height: text size of the dimension settings")

    TITLE = "Text"
    NEEDED = 2
    PLANAR = False
    LOCK_OK = False

    text_height = DESSIN_OT_cotation.text_height
    screen_right = DESSIN_OT_cotation.screen_right

    def lock_allowed(self):
        return False

    def invoke(self, context, event):
        self.note = ""
        self.line = 0
        self.dim_label = None
        self.frame = None
        return super().invoke(context, event)

    def reset_state(self):
        super().reset_state()
        self.note = ""
        self.line = 0
        self.frame = None

    def prompt(self):
        if not self.points:
            return "insertion point (bottom left of the text)"
        return "type the text   (Enter: next line, Enter on an empty line: finish, Backspace: erase, Esc: finish)"

    def prompt_tail(self):
        return not self.points     # pendant la frappe, S, Maj+F et Espace sont du texte

    def coord_pre(self, context, event):
        if self.points:
            return None        # on tape le texte : les chiffres, @, # ... font partie du texte
        return DessinBase.coord_pre(self, context, event)

    def text_frame(self, p):
        """(X, Y, Z, hauteur) : X le long de l'écran dans le plan de construction, Z vers l'observateur."""
        nrm = plane_axes(self.axis)[2]
        right, towards = self.screen_right()
        te = right - nrm * right.dot(nrm)
        if te.length < 1e-6:
            te = plane_axes(self.axis)[0].copy()
        te = te.normalized()
        Z = nrm * (1.0 if nrm.dot(towards) >= 0 else -1.0)
        Y = Z.cross(te)
        return te, Y, Z, self.text_height(p, te)

    def line_origin(self):
        X, Y, Z, h = self.frame
        return self.points[0] - Y * (1.6 * h * self.line)

    def compute(self):
        self.dim_label = None
        if not self.points:
            return [], [], "", None
        if self.frame is None:
            self.frame = self.text_frame(self.points[0])
        X, Y, Z, h = self.frame
        o = self.line_origin()
        text = self.note
        w = len(text) * 0.62 * h
        self.dim_label = (o + X * (w / 2.0) + Y * (h * 0.2), text + "|")
        box = [o, o + X * max(w, h * 0.6), o + X * max(w, h * 0.6) + Y * h, o + Y * h, o]
        return [], [box], f"Height {self.fmt(h)}", None

    def click(self, context):
        if self.cur is None:
            return
        if not self.points:
            self.points.append(self.cur.copy())
            self.frame = self.text_frame(self.points[0])
            self.refresh(context)
            return
        self.commit_line(context)          # un clic pendant la saisie valide la ligne, comme Entrée

    def commit_line(self, context):
        """Crée la ligne tapée ; retourne False si elle était vide (fin de la commande)."""
        if not self.note.strip():
            return False
        X, Y, Z, h = self.frame
        o = self.line_origin()
        fc = bpy.data.curves.new("Text", 'FONT')
        fc.body = self.note
        fc.size = h
        fc.align_x = 'LEFT'
        fc.align_y = 'BOTTOM_BASELINE'
        obj = bpy.data.objects.new("Text", fc)
        obj.matrix_world = Matrix(((X.x, Y.x, Z.x, o.x), (X.y, Y.y, Z.y, o.y), (X.z, Y.z, Z.z, o.z), (0.0, 0.0, 0.0, 1.0)))
        obj["dessin_text"] = True
        try:
            context.collection.objects.link(obj)
        except (AttributeError, RuntimeError):
            context.scene.collection.objects.link(obj)
        self.note = ""
        self.line += 1
        self.refresh(context)
        return True

    def modal(self, context, event):
        if (self.points and event.value == 'PRESS' and not (event.ctrl or event.alt or event.oskey)
                and self.area is not None and context.area is not None
                and find_window_region(self.area, event.mouse_x, event.mouse_y) is not None
                and not self.mouse_over_ui(event)):
            if event.type in {'RET', 'NUMPAD_ENTER'}:
                if not self.commit_line(context):
                    self.finished = True
                    self.dim_label = None
                    return self.exit(context)
                return {'RUNNING_MODAL'}
            if event.type == 'ESC':
                self.finished = self.line > 0
                self.dim_label = None
                return self.exit(context)
            if event.type == 'BACK_SPACE':
                self.note = self.note[:-1]
                self.refresh(context)
                return {'RUNNING_MODAL'}
            ch = " " if event.type == 'SPACE' else event.unicode
            if ch and ch.isprintable():
                self.note += ch
                self.refresh(context)
                return {'RUNNING_MODAL'}
        return super().modal(context, event)

    def cleanup(self, context):
        self.dim_label = None
        super().cleanup(context)


class DESSIN_OT_dist(DessinBase):
    bl_idname = "dessin.dist"
    bl_label = "Distance"
    bl_description = ("Like DIST: distance, X / Y / Z deltas and angles between two points (snaps and typed coordinates work). "
                      "Nothing is created; the result is copied to the clipboard")

    TITLE = "Distance"
    NEEDED = 2
    PLANAR = False      # vraie distance 3D entre les points accrochés
    NUMFIELDS = 0

    def prompt(self):
        return "first point" if not self.points else "second point"

    def measure(self, a, b):
        u, v, n = plane_axes(self.axis)
        d = b - a
        du, dv, dn = d.dot(u), d.dot(v), d.dot(n)
        flat = math.hypot(du, dv)
        ang = math.degrees(math.atan2(dv, du)) % 360.0 if flat > 1e-12 else 0.0
        elev = math.degrees(math.atan2(dn, flat)) if d.length > 1e-12 else 0.0
        return d.length, du, dv, dn, ang, elev

    def compute(self):
        if not self.points or self.cur is None:
            return [], [], "", None
        a = self.points[0]
        L, du, dv, dn, ang, elev = self.measure(a, self.cur)
        info = (f"Distance {self.fmt(L)}   dX {self.fmt(du)}   dY {self.fmt(dv)}   dZ {self.fmt(dn)}   "
                f"Angle in plane {ang:.2f}°   From plane {elev:.2f}°")
        return [a, self.cur], [], info, None

    def click(self, context):
        if self.cur is None:
            return
        if not self.points:
            self.points.append(self.cur.copy())
            self.refresh(context)
            return
        a, b = self.points[0], self.cur.copy()
        L, du, dv, dn, ang, elev = self.measure(a, b)
        msg = (f"Distance = {self.fmt(L)},  Angle in XY plane = {ang:.2f}°,  Angle from XY plane = {elev:.2f}°   "
               f"Delta X = {self.fmt(du)},  Delta Y = {self.fmt(dv)},  Delta Z = {self.fmt(dn)}")
        try:
            context.window_manager.clipboard = f"{L / self.unit_f:.6g}"
        except (AttributeError, RuntimeError):
            pass
        cmd_log(msg)
        self.report({'INFO'}, msg)
        self.finished = True


class DESSIN_OT_id_point(DessinBase):
    bl_idname = "dessin.id_point"
    bl_label = "ID Point"
    bl_description = ("Like ID: click a point (snaps work) to read its X, Y, Z coordinates (world, and construction plane if it is not the world). "
                      "Nothing is created; the coordinates are copied to the clipboard")

    TITLE = "ID"
    NEEDED = 2
    PLANAR = False
    NUMFIELDS = 0
    LOCK_OK = False

    def lock_allowed(self):
        return False

    def prompt(self):
        return "point"

    def coords_text(self, p):
        f = self.unit_f
        txt = f"X = {p.x / f:.4f}   Y = {p.y / f:.4f}   Z = {p.z / f:.4f}"
        if self.axis == 3:
            u, v, n = plane_axes(self.axis)
            o = plane_origin(self.axis)
            d = p - o
            txt += f"   (CPlane: x = {d.dot(u) / f:.4f}   y = {d.dot(v) / f:.4f}   z = {d.dot(n) / f:.4f})"
        return txt + (f"   [{self.unit_label}]" if self.unit_label else "")

    def compute(self):
        if self.cur is None:
            return [], [], "", None
        return [], [], self.coords_text(self.cur), None

    def click(self, context):
        if self.cur is None:
            return
        p = self.cur.copy()
        msg = self.coords_text(p)
        f = self.unit_f
        try:
            context.window_manager.clipboard = f"{p.x / f:.6g}, {p.y / f:.6g}, {p.z / f:.6g}"
        except (AttributeError, RuntimeError):
            pass
        cmd_log("ID: " + msg)
        self.report({'INFO'}, "ID: " + msg)
        self.finished = True


class DESSIN_OT_dimstyle_add(bpy.types.Operator):
    bl_idname = "dessin.dimstyle_add"
    bl_label = "Save Dimension Style"
    bl_description = "Saves the current text, arrow and unit settings as a named dimension style"
    bl_options = {'REGISTER', 'UNDO'}

    name: bpy.props.StringProperty(name="Name", default="My style")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=260)

    def execute(self, context):
        st = context.scene.dessin
        ensure_dim_styles(st)
        it = st.dim_styles.add()
        it.name = self.name.strip() or "Style"
        it.data = json.dumps(dimstyle_snapshot(st))
        st.dim_style_index = len(st.dim_styles) - 1
        return {'FINISHED'}


class DESSIN_OT_dimstyle_update(bpy.types.Operator):
    bl_idname = "dessin.dimstyle_update"
    bl_label = "Update Dimension Style"
    bl_description = "Overwrites the selected dimension style with the current settings"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        st = context.scene.dessin
        return 0 <= st.dim_style_index < len(st.dim_styles)

    def execute(self, context):
        st = context.scene.dessin
        st.dim_styles[st.dim_style_index].data = json.dumps(dimstyle_snapshot(st))
        return {'FINISHED'}


class DESSIN_OT_dimstyle_remove(bpy.types.Operator):
    bl_idname = "dessin.dimstyle_remove"
    bl_label = "Delete Dimension Style"
    bl_description = "Deletes the selected dimension style"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        st = context.scene.dessin
        return 0 <= st.dim_style_index < len(st.dim_styles)

    def execute(self, context):
        st = context.scene.dessin
        st.dim_styles.remove(st.dim_style_index)
        st.dim_style_index = max(0, min(st.dim_style_index, len(st.dim_styles) - 1))
        return {'FINISHED'}


class DESSIN_UL_dimstyles(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.prop(item, "name", text="", emboss=False, icon='DRIVER_DISTANCE')


def loop_area(pts):
    """Aire d'un contour fermé (méthode de Newell : fonctionne aussi dans un plan quelconque)."""
    n = Vector((0.0, 0.0, 0.0))
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        n.x += (a.y - b.y) * (a.z + b.z)
        n.y += (a.z - b.z) * (a.x + b.x)
        n.z += (a.x - b.x) * (a.y + b.y)
    return 0.5 * n.length


def measure_edge_loops(edges, coords):
    """edges : [(i, j)] ; coords : {i: Vector}. Retourne (périmètre total, aire des contours fermés)."""
    perim = sum((coords[i] - coords[j]).length for i, j in edges)
    adj = {}
    for i, j in edges:
        adj.setdefault(i, []).append(j)
        adj.setdefault(j, []).append(i)
    seen, area = set(), 0.0
    for start in adj:
        if start in seen:
            continue
        comp, stack = [], [start]
        while stack:
            v = stack.pop()
            if v in seen:
                continue
            seen.add(v)
            comp.append(v)
            stack.extend(adj[v])
        if len(comp) >= 3 and all(len(adj[v]) == 2 for v in comp):
            order, prev, cur = [start], None, start
            while True:
                nxt = [w for w in adj[cur] if w != prev]
                nx = nxt[0] if nxt else adj[cur][0]
                if nx == start or len(order) > len(comp):
                    break
                order.append(nx)
                prev, cur = cur, nx
            area += loop_area([coords[v] for v in order])
    return perim, area


def selection_measure(context):
    """(aire, périmètre, centre, libellé) de la sélection : faces d'un maillage, ou contours (courbes, arêtes). None si rien."""
    import bmesh
    area = perim = 0.0
    pts_all = []
    count = 0
    if context.mode == 'EDIT_MESH':
        sources = [(o, bmesh.from_edit_mesh(o.data), True, False) for o in context.objects_in_mode_unique_data
                   if o.type == 'MESH']
    else:
        dg = context.evaluated_depsgraph_get()
        sources = []
        for o in context.selected_objects:
            if o.type not in {'MESH', 'CURVE'}:
                continue
            try:
                me = o.evaluated_get(dg).to_mesh()
            except RuntimeError:
                continue
            bm = bmesh.new()
            bm.from_mesh(me)
            o.evaluated_get(dg).to_mesh_clear()
            sources.append((o, bm, False, True))
    for o, bm, only_sel, free in sources:
        mw = o.matrix_world
        faces = [f for f in bm.faces if f.select or not only_sel]
        if faces:
            ecount = {}
            for f in faces:
                w = [mw @ v.co for v in f.verts]
                area += loop_area(w)
                pts_all.extend(w)
                for e in f.edges:
                    ecount[e] = ecount.get(e, 0) + 1
            for e, k in ecount.items():
                if k == 1:
                    perim += (mw @ e.verts[0].co - mw @ e.verts[1].co).length
            count += len(faces)
        else:
            edges = [e for e in bm.edges if e.select or not only_sel]
            if edges:
                coords = {v.index: mw @ v.co for e in edges for v in e.verts}
                p_, a_ = measure_edge_loops([(e.verts[0].index, e.verts[1].index) for e in edges], coords)
                perim += p_
                area += a_
                pts_all.extend(coords.values())
                count += len(edges)
        if free:
            bm.free()
    if not count or not pts_all:
        return None
    center = sum(pts_all, Vector((0.0, 0.0, 0.0))) / len(pts_all)
    return area, perim, center


class DESSIN_OT_mesure_aire(DessinBase):
    bl_idname = "dessin.mesure_aire"
    bl_label = "Area / Perimeter"
    bl_description = ("Quick measure (nothing is added to the scene): click the corners of a contour to read its area and "
                      "perimeter. D: measure the selection instead. The result is copied to the clipboard")

    TITLE = "Area / Perimeter"
    NEEDED = 1000
    HAS_MODE = True
    MODES = ("Points", "Selection")
    mode = 0
    PLANAR = False
    LOCK_OK = True

    def invoke(self, context, event):
        self.dim_label = None
        self.last = None
        self._sel = (-1, None)
        return super().invoke(context, event)

    def prompt(self):
        if self.mode == 1:
            return "area and perimeter of the selection   [D: Points]"
        n = len(self.points)
        if n < 2:
            return "click the corners of the contour   [D: Selection]"
        return "next corner   [click the first point, or Enter: close and measure]   [D: Selection]"

    def area_text(self, a):
        k = self.unit_f * self.unit_f
        s = f"{a / k:.3f}".rstrip('0').rstrip('.')
        return f"{s} {self.unit_label}²".strip() if self.unit_label else s

    def dist_text(self, d):
        return self.fmt(d)

    def result_text(self, area, perim):
        return f"A = {self.area_text(area)}   P = {self.dist_text(perim)}"

    def selection_result(self, context):
        key = _HOVER["version"]
        if self._sel[0] != key:
            try:
                self._sel = (key, selection_measure(context))
            except (RuntimeError, ReferenceError, AttributeError):
                self._sel = (key, None)
        return self._sel[1]

    def compute(self):
        self.dim_label = None
        if self.mode == 1:
            res = self.selection_result(bpy.context)
            if res is None:
                return [], [], "Nothing selected (faces, closed curves or edge loops)", None
            area, perim, center = res
            text = self.result_text(area, perim)
            self.dim_label = (center, text)
            return [], [], text, None
        if self.last is not None and not self.points:
            self.dim_label = (self.last[1], self.last[0])
        if self.cur is None or not self.points:
            return [], [], (self.last[0] if self.last else ""), None
        pts = list(self.points) + [self.cur]
        if len(pts) == 2:
            d = (pts[1] - pts[0]).length
            return pts, [], f"Length {self.dist_text(d)}", None
        area = loop_area(pts)
        perim = sum((pts[i] - pts[(i + 1) % len(pts)]).length for i in range(len(pts)))
        text = self.result_text(area, perim)
        cen = sum(pts, Vector((0.0, 0.0, 0.0))) / len(pts)
        self.dim_label = (cen, text)
        return pts + [pts[0]], [], text, None

    def close_contour(self, context):
        pts = list(self.points)
        if len(pts) < 3:
            return False
        area = loop_area(pts)
        perim = sum((pts[i] - pts[(i + 1) % len(pts)]).length for i in range(len(pts)))
        text = self.result_text(area, perim)
        cen = sum(pts, Vector((0.0, 0.0, 0.0))) / len(pts)
        self.last = (text, cen)
        try:
            context.window_manager.clipboard = text
        except (AttributeError, RuntimeError):
            pass
        self.report({'INFO'}, text + "   (copied)")
        self.reset_state()
        self.refresh(context)
        return True

    def click(self, context):
        if self.mode == 1:
            return
        if len(self.points) >= 3 and (self.cur - self.points[0]).length <= 1e-6 * max(1.0, self.points[0].length):
            self.close_contour(context)
            return
        self.points.append(self.cur.copy())
        self.last = None
        self.refresh(context)

    def modal(self, context, event):
        if (event.type in {'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS' and self.mode == 0
                and len(self.points) >= 3 and self.area is not None
                and find_window_region(self.area, event.mouse_x, event.mouse_y) is not None
                and not self.mouse_over_ui(event)):
            self.close_contour(context)
            return {'RUNNING_MODAL'}
        return super().modal(context, event)

    def cleanup(self, context):
        self.dim_label = None
        super().cleanup(context)


class DESSIN_OT_cotations_supprimer(bpy.types.Operator):
    bl_idname = "dessin.cotations_supprimer"
    bl_label = "Delete All Dimensions"
    bl_description = "Deletes the objects in the «Dimensions» collection"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        objs = dimension_objects()
        if not objs:
            return {'CANCELLED'}
        for o in objs:
            data = o.data
            bpy.data.objects.remove(o)
            if data is not None and data.users == 0:
                try:
                    bpy.data.curves.remove(data)
                except (RuntimeError, ReferenceError):
                    pass
        return {'FINISHED'}


def draw_cotation_style(layout, st, compact=False):
    col = layout.column(align=True)
    col.prop(st, "couleur")
    col.prop(st, "epaisseur_trait")
    col.prop(st, "visible_rendu")
    if compact:
        col.prop(st, "taille_texte")
        col.prop(st, "decimales")
        return
    col.separator()
    col.label(text="Text")
    col.prop(st, "taille_texte")
    col.prop(st, "ecart_texte")
    col.prop(st, "position_texte", text="")
    col.separator()
    col.label(text="Lines and arrowheads")
    col.prop(st, "decalage")
    col.prop(st, "prolongement")
    col.prop(st, "fleche_style", text="")
    col.prop(st, "fleche_taille")
    col.separator()
    col.label(text="Units and format")
    col.prop(st, "unite_cote", text="")
    col.prop(st, "decimales")
    col.prop(st, "supprimer_zeros")
    col.prop(st, "unite")
    col.prop(st, "prefixe")
    col.prop(st, "suffixe")


class DESSIN_PT_cotation(bpy.types.Panel):
    bl_label = "Dimension"
    bl_idname = "DESSIN_PT_cotation"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Wanderer"

    def draw(self, context):
        st = context.scene.dessin
        lay = self.layout
        box = lay.box()
        box.label(text="Styles")
        row = box.row()
        row.template_list("DESSIN_UL_dimstyles", "", st, "dim_styles", st, "dim_style_index", rows=3)
        col = row.column(align=True)
        col.operator(DESSIN_OT_dimstyle_add.bl_idname, icon='ADD', text="")
        col.operator(DESSIN_OT_dimstyle_remove.bl_idname, icon='REMOVE', text="")
        col.operator(DESSIN_OT_dimstyle_update.bl_idname, icon='FILE_REFRESH', text="")
        dob = dim_owner(context.active_object)
        if dob is not None:
            box = lay.box()
            box.label(text="Selected dimension", icon='DRIVER_DISTANCE')
            box.prop(dob.dessin_dim, "text")
            box.label(text="<> = measured value, e.g. 4x <>  or  <> TYP")
        draw_cotation_style(lay, st)
        lay.separator()
        lay.operator(DESSIN_OT_cotations_supprimer.bl_idname, icon='TRASH')


class DESSIN_PT_hatch(bpy.types.Panel):
    bl_label = "Hatch"
    bl_idname = "DESSIN_PT_hatch"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Wanderer"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        st = context.scene.dessin
        lay = self.layout
        ob = context.active_object
        hs = [o for o in context.selected_objects if is_hatch(o)]
        if hs:
            src = ob if is_hatch(ob) else hs[0]
            box = lay.box()
            box.label(text=f"Selected hatch{'es' if len(hs) > 1 else ''} ({len(hs)})", icon='MOD_LATTICE')
            col = box.column(align=True)
            col.prop(src.dessin_hatch, "pattern", text="")
            col.prop(src.dessin_hatch, "scale")
            col.prop(src.dessin_hatch, "rotation")
            row = box.row(align=True)
            row.operator(DESSIN_OT_hatch_base.bl_idname, text="Base Point")
            row.operator(DESSIN_OT_hatch_match.bl_idname, text="Match")
            row = box.row(align=True)
            row.operator(DESSIN_OT_hatch_boundary.bl_idname, text="Boundary")
            row.operator(DESSIN_OT_hatch_explode.bl_idname, text="Explode")
        lay.label(text="New hatches")
        col = lay.column(align=True)
        col.prop(st, "hatch_pattern", text="")
        col.prop(st, "hatch_scale")
        col.prop(st, "hatch_rotation")
        col.prop(st, "hatch_spacing")
        lay.prop(st, "hatch_boundary")
        row = lay.row(align=True)
        row.operator(DESSIN_OT_hatch.bl_idname, text="Hatch")
        row.operator(DESSIN_OT_hatch_region.bl_idname, text="By Point")


def _late_imports():
    """Noms définis dans des modules chargés après celui-ci : ils ne servent qu'à l'exécution des outils."""
    global DESSIN_OT_hatch, DESSIN_OT_hatch_base, DESSIN_OT_hatch_boundary, DESSIN_OT_hatch_explode
    global DESSIN_OT_hatch_match, DESSIN_OT_hatch_region, cmd_log, is_hatch
    from .hatch import (
        DESSIN_OT_hatch, DESSIN_OT_hatch_base, DESSIN_OT_hatch_boundary, DESSIN_OT_hatch_explode,
    DESSIN_OT_hatch_match, DESSIN_OT_hatch_region, is_hatch,
    )
    from .cplane import cmd_log
    global layout_dim_factor
    from .layout import layout_dim_factor
