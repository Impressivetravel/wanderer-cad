"""Wanderer CAD : Break (couper une courbe entre deux points ou en un point, comme BREAK / BREAKATPOINT d'AutoCAD) et
Match Properties (copier calque, couleur, type de ligne, épaisseur, matériau... d'un objet sur d'autres, comme MATCHPROP)."""

import math

import bpy
import numpy as np
from mathutils import Vector

from .core import obj_visible, pref
from .drawing import find_window_region, px_scale, region_rv3d
from .base import DessinBase
from .linetypes import lt_apply, lt_eligible

_SKIP_KEYS = ("dessin_cotation", "dessin_cotation_texte", "dessin_dim", "dessin_hatch", "cad_clip", "wd_gen", "wd_layout_gen")


# --------------------------------------------------------------------------
# Courbe sous le curseur, point le plus proche
# --------------------------------------------------------------------------

def breakable(o):
    try:
        if any(k in o.keys() for k in _SKIP_KEYS):
            return False
        if o.type == 'CURVE':
            return True
        return o.type == 'MESH' and len(o.data.edges) > 0 and not len(o.data.polygons)
    except (AttributeError, ReferenceError):
        return False


def _screen(pts, persp, region):
    P = np.asarray(pts, dtype=np.float64).reshape(-1, 3)
    h = np.hstack((P, np.ones((len(P), 1)))) @ np.asarray(persp, dtype=np.float64).T
    w = h[:, 3]
    ok = w > 1e-9
    ws = np.where(ok, w, 1.0)
    sx = (h[:, 0] / ws * 0.5 + 0.5) * region.width
    sy = (h[:, 1] / ws * 0.5 + 0.5) * region.height
    return sx, sy, ok


def _seg_dist2d(sx, sy, a, b, mx, my):
    ax, ay, bx, by = sx[a], sy[a], sx[b], sy[b]
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    t = np.clip(((mx - ax) * dx + (my - ay) * dy) / np.where(l2 > 1e-12, l2, 1.0), 0.0, 1.0)
    px, py = ax + t * dx, ay + t * dy
    return np.hypot(px - mx, py - my), t


def wire_of(o, dg=None):
    """(sommets monde [Vector], arêtes [(i, j)]) du trait entier d'une courbe ou d'un contour, ou None."""
    from .trim import wire_graph
    try:
        return wire_graph(o, dg or bpy.context.evaluated_depsgraph_get())
    except (RuntimeError, ReferenceError, AttributeError, TypeError):
        return None


def pick_curve_at(context, area, region, mx, my, px=10.0):
    """(objet, sommets, arêtes, arête, t) de la courbe la plus proche du curseur (à moins de px pixels), ou None."""
    rv3d = region_rv3d(region, area)
    if rv3d is None:
        return None
    persp = rv3d.perspective_matrix
    space = area.spaces.active
    best = None
    dg = context.evaluated_depsgraph_get()
    from .selection import objects_near_rect
    try:        # seuls les objets dont la boîte passe près du curseur sont lus (calcul groupé, grosses scènes)
        cands = objects_near_rect([o for o in context.visible_objects if o.type in {'CURVE', 'MESH'}],
                                  np.array(persp, dtype=np.float64), region, (mx - px, my - px, mx + px, my + px))
    except (RuntimeError, ReferenceError, AttributeError, ValueError, TypeError):
        cands = list(context.visible_objects)
    for o in cands:
        if not breakable(o) or o.hide_select or not obj_visible(o, space):
            continue
        g = wire_of(o, dg)
        if g is None or not g[1]:
            continue
        V, E = g
        sx, sy, ok = _screen([tuple(v) for v in V], persp, region)
        Ea = np.asarray(E, dtype=np.int64).reshape(-1, 2)
        good = ok[Ea[:, 0]] & ok[Ea[:, 1]]
        if not good.any():
            continue
        d, t = _seg_dist2d(sx, sy, Ea[:, 0], Ea[:, 1], mx, my)
        d = np.where(good, d, np.inf)
        k = int(np.argmin(d))
        if d[k] <= px and (best is None or d[k] < best[0]):
            best = (float(d[k]), o, V, E, k, float(t[k]))
    return None if best is None else best[1:]


def nearest_on_wire(V, E, p, edge_ids=None):
    """(arête, t, distance) du point du trait le plus proche de p (3D)."""
    P = np.array([tuple(v) for v in V], dtype=np.float64)
    Ea = np.asarray(E, dtype=np.int64).reshape(-1, 2)
    ids = np.arange(len(Ea)) if edge_ids is None else np.asarray(list(edge_ids), dtype=np.int64)
    A, B = P[Ea[ids, 0]], P[Ea[ids, 1]]
    d = B - A
    l2 = (d * d).sum(axis=1)
    q = np.asarray(tuple(p), dtype=np.float64)
    t = np.clip(((q - A) * d).sum(axis=1) / np.where(l2 > 1e-24, l2, 1.0), 0.0, 1.0)
    dist = np.linalg.norm(A + t[:, None] * d - q, axis=1)
    k = int(np.argmin(dist))
    return int(ids[k]), float(t[k]), float(dist[k])


# --------------------------------------------------------------------------
# Coupure d'une chaîne d'arêtes
# --------------------------------------------------------------------------

class Chain:
    """Chaîne ordonnée d'arêtes (une courbe d'un seul tenant) et position le long d'elle (u : n° d'arête + fraction)."""

    def __init__(self, V, E, e0):
        from .trim import wire_chain
        self.V, self.E = V, E
        vs, es, closed, _k = wire_chain(E, e0)
        self.vs, self.es, self.closed = vs, es, closed
        self.n = len(es)
        P = [V[vs[i]] for i in range(len(vs))]
        if closed:
            P = P + [P[0]]
        self.P = P
        self.cum = [0.0]
        for a, b in zip(P, P[1:]):
            self.cum.append(self.cum[-1] + (b - a).length)
        self.total = self.cum[-1]

    def u_of(self, e, t):
        i = self.es.index(e)
        a, _b = self.E[e]
        return i + (t if a == self.vs[i] else 1.0 - t)

    def point(self, u):
        n = self.n
        if self.closed:
            u = u % n
        i = min(int(math.floor(u + 1e-12)), n - 1)
        fr = u - i
        return self.P[i].lerp(self.P[i + 1], fr)

    def length_at(self, u):
        n = self.n
        k = math.floor(u / n) if self.closed else 0
        uu = u - k * n
        i = min(int(math.floor(uu + 1e-12)), n - 1)
        return k * self.total + self.cum[i] + (self.cum[i + 1] - self.cum[i]) * (uu - i)

    def path(self, u0, u1):
        """Points de u0 à u1 (u0 < u1 ; sur une courbe fermée, u1 peut dépasser n)."""
        pts = [self.point(u0)]
        j = int(math.floor(u0 + 1e-9)) + 1
        while j < u1 - 1e-9:
            pts.append(self.P[j % self.n].copy() if self.closed else self.P[j].copy())
            j += 1
        pts.append(self.point(u1))
        out = [pts[0]]
        for p in pts[1:]:
            if (p - out[-1]).length > 1e-12:
                out.append(p)
        return out

    def removed(self, ua, ub):
        """Partie retirée entre ua et ub (la plus courte sur une courbe fermée) : liste de points."""
        lo, hi = min(ua, ub), max(ua, ub)
        if self.closed:
            fwd = self.length_at(hi) - self.length_at(lo)
            if fwd <= self.total - fwd:
                return self.path(lo, hi)
            return self.path(hi, lo + self.n)
        return self.path(lo, hi)

    def pieces(self, ua, ub=None):
        """Morceaux gardés [(points, fermé)] après la coupure (en un point si ub est None)."""
        eps = 1e-9 * max(self.n, 1)
        tiny = 1e-9 * max(self.total, 1e-9)
        if ub is None or abs(ua - ub) <= eps:
            if self.closed:
                return [self.path(ua, ua + self.n)]          # ouverte en ce point
            if ua <= eps or ua >= self.n - eps:
                return None                                   # au bout : rien à couper
            return [self.path(0.0, ua), self.path(ua, float(self.n))]
        lo, hi = min(ua, ub), max(ua, ub)
        if self.closed:
            fwd = self.length_at(hi) - self.length_at(lo)
            if fwd <= self.total - fwd:
                keep = self.path(hi, lo + self.n)
            else:
                keep = self.path(lo, hi)
            return [keep] if len(keep) >= 2 else []
        out = []
        if self.length_at(lo) > tiny:
            out.append(self.path(0.0, lo))
        if self.total - self.length_at(hi) > tiny:
            out.append(self.path(hi, float(self.n)))
        return out


def apply_break(context, obj, V, E, chain, pieces):
    """Remplace la chaîne coupée par ses morceaux : le premier reste dans l'objet (avec ses autres courbes), les autres
    deviennent des objets à part (copies de l'objet : même calque, couleur, type de ligne...). Retourne les objets."""
    from .trim import circle_hints, write_wire
    hints = circle_hints(obj)
    chain_e = set(chain.es)
    keep_e = [e for k, e in enumerate(E) if k not in chain_e]

    def graph(extra_paths, base_edges):
        verts = list(V)
        edges = list(base_edges)
        for pts in extra_paths:
            i0 = len(verts)
            verts.extend(p.copy() for p in pts)
            edges.extend((i0 + k, i0 + k + 1) for k in range(len(pts) - 1))
        used = sorted({v for e in edges for v in e})
        remap = {v: k for k, v in enumerate(used)}
        return [verts[v] for v in used], [(remap[a], remap[b]) for a, b in edges]

    made = [obj]
    first = pieces[:1]
    vv, ee = graph(first, keep_e)
    if not ee:
        return []
    write_wire(obj, vv, ee, hints)
    for pts in pieces[1:]:
        o2 = obj.copy()
        if obj.data is not None:
            o2.data = obj.data.copy()
        for c in obj.users_collection:
            c.objects.link(o2)
        vv, ee = graph([pts], [])
        write_wire(o2, vv, ee, hints)
        made.append(o2)
    for o in made:
        try:
            o.update_tag()
        except (ReferenceError, AttributeError):
            pass
    return made


class DESSIN_OT_break_crv(DessinBase):
    bl_idname = "dessin.break_crv"
    bl_label = "Break"
    bl_description = ("Like BREAK: click a curve at the first break point, then the second point: the part between them is "
                      "removed (on a closed curve, the shorter part). D: At Point, to cut a curve in two at one point "
                      "without a gap (like BREAKATPOINT). Enter after the first point also breaks there")

    TITLE = "Break"
    EDIT_OK = False
    NEEDED = 2
    HAS_MODE = True
    MODES = ("Two points", "At point")
    mode = 0
    PLANAR = False
    LOCK_OK = False

    def lock_allowed(self):
        return False

    def prompt(self):
        other = self.MODES[(self.mode + 1) % len(self.MODES)]
        if self.MODES[self.mode] == "At point":
            return f"click the curve where it should be cut in two   [D: {other}]"
        if self._target is None:
            return f"click the curve at the first break point   [D: {other}]"
        return "second break point   [Enter: break at the first point]"

    def invoke(self, context, event):
        self._mouse = None
        self._target = None
        self.hilite = []
        return super().invoke(context, event)

    def update_cursor(self, context, event):
        region = find_window_region(self.area, event.mouse_x, event.mouse_y)
        self._mouse = (event.mouse_x - region.x, event.mouse_y - region.y) if region is not None else None
        super().update_cursor(context, event)

    def _pick(self, context):
        """(objet, sommets, arêtes, arête, t) de la courbe désignée : celle sous le curseur, au point accroché s'il y en a un."""
        if self._mouse is None or self.region is None:
            return None
        hit = pick_curve_at(context, self.area, self.region, self._mouse[0], self._mouse[1], 10.0 * _ui())
        if hit is None:
            return None
        o, V, E, k, t = hit
        if self.snap_kind is not None and self.cur is not None:
            k2, t2, dist = nearest_on_wire(V, E, self.cur)
            if dist <= 1e-6 * max(1.0, self.cur.length):
                k, t = k2, t2          # point accroché sur la courbe : exact
        return o, V, E, k, t

    def _second_u(self, context):
        tg = self._target
        if tg is None:
            return None
        o, V, E, chain, ua = tg
        p = self.cur
        if p is None:
            return None
        k, t, _d = nearest_on_wire(V, E, p, edge_ids=chain.es)
        if self.snap_kind is None and self._mouse is not None and self.region is not None:
            # sans accroche : le point de la courbe le plus proche du curseur à l'écran
            rv3d = region_rv3d(self.region, self.area)
            if rv3d is not None:
                P = [tuple(v) for v in V]
                sx, sy, ok = _screen(P, rv3d.perspective_matrix, self.region)
                Ea = np.asarray([E[e] for e in chain.es], dtype=np.int64)
                d, tt = _seg_dist2d(sx, sy, Ea[:, 0], Ea[:, 1], self._mouse[0], self._mouse[1])
                j = int(np.argmin(d))
                k, t = chain.es[j], float(tt[j])
        return chain.u_of(k, t)

    def compute(self):
        self.hilite = []
        tg = self._target
        if tg is None:
            return [], [], "", None
        _o, _V, _E, chain, ua = tg
        ub = self._second_u(bpy.context)
        if ub is None:
            return [], [], "", None
        P = chain.removed(ua, ub)
        self.hilite = [(P[i], P[i + 1]) for i in range(len(P) - 1)]
        gap = abs(chain.length_at(max(ua, ub)) - chain.length_at(min(ua, ub)))
        if chain.closed:
            gap = min(gap, chain.total - gap)
        return [], [], f"Break: gap {self.fmt(gap)}", None

    def _do(self, context, obj, V, E, chain, ua, ub):
        pieces = chain.pieces(ua, ub)
        if pieces is None:
            self.report({'INFO'}, "This point is at the end of the curve: nothing to cut")
            return False
        if not pieces:
            self.report({'INFO'}, "Nothing would be left of this curve")
            return False
        made = apply_break(context, obj, V, E, chain, pieces)
        if not made:
            return False
        _step(self, "Break")
        n = len(made)
        self.report({'INFO'}, "Break: " + ("curve opened" if n == 1 and chain.closed and ub is None
                                           else f"{n} piece{'s' if n > 1 else ''}"))
        return True

    def click(self, context):
        if self._target is None:
            hit = self._pick(context)
            if hit is None:
                self.report({'INFO'}, "Click on a curve or a line")
                return
            o, V, E, k, t = hit
            chain = Chain(V, E, k)
            ua = chain.u_of(k, t)
            if self.MODES[self.mode] == "At point":
                self._do(context, o, V, E, chain, ua, None)
                self.reset_state()
                self.refresh(context)
                return
            self._target = (o, V, E, chain, ua)
            self.points = [chain.point(ua)]
            self.refresh(context)
            return
        o, V, E, chain, ua = self._target
        ub = self._second_u(context)
        if ub is not None:
            self._do(context, o, V, E, chain, ua, ub)
        self._target = None
        self.hilite = []
        self.reset_state()
        self.refresh(context)

    def modal(self, context, event):
        if (event.type in {'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS' and self._target is not None
                and self.area is not None and find_window_region(self.area, event.mouse_x, event.mouse_y) is not None):
            o, V, E, chain, ua = self._target         # Entrée après le premier point : coupé en ce point
            self._do(context, o, V, E, chain, ua, None)
            self._target = None
            self.hilite = []
            self.reset_state()
            self.refresh(context)
            return {'RUNNING_MODAL'}
        return super().modal(context, event)

    def reset_state(self):
        super().reset_state()
        if getattr(self, "_target", None) is not None and not self.points:
            self._target = None

    def exit(self, context):
        if getattr(self, "_did", False):
            self.finished = True          # (la commande reste active entre deux coupures : Échap la termine)
        return super().exit(context)

    def cleanup(self, context):
        self.hilite = []
        super().cleanup(context)


def _step(op, message):
    """Une action faite pendant une commande qui reste active : un pas d'annulation à elle, et la commande se termine
    « faite » (Échap ne l'annule pas)."""
    op._did = True
    try:
        bpy.ops.ed.undo_push(message=message)
    except (RuntimeError, AttributeError):
        pass


def _ui():
    try:
        return max(float(px_scale()), 0.5)
    except (AttributeError, TypeError, ValueError):
        return 1.0


# --------------------------------------------------------------------------
# Match Properties
# --------------------------------------------------------------------------

MATCH_KEYS = (("match_layer", "Layer"), ("match_color", "Color"), ("match_linetype", "Linetype"),
              ("match_print", "Print width"), ("match_material", "Material"), ("match_text", "Text"),
              ("match_hatch", "Hatch"))


def match_apply(context, src, dst, st):
    """Copie sur dst les propriétés de src choisies dans st (réglages de la scène). Retourne la liste de ce qui a changé."""
    done = []
    if dst is src or dst.get("cad_clip") or dst.get("wd_gen") or dst.get("wd_layout_gen"):
        return done
    # les cotes sont reconnues par leur calque (« Dimensions ») : elles n'en changent pas, et rien n'y est rangé
    dims = any(k in o.keys() for o in (src, dst) for k in ("dessin_cotation", "dessin_cotation_texte", "dessin_dim"))
    if st.match_layer and src.users_collection and not dims:
        target = src.users_collection[0]
        if list(dst.users_collection) != [target]:
            for c in list(dst.users_collection):
                if c != target:
                    c.objects.unlink(dst)
            if dst.name not in target.objects:
                target.objects.link(dst)
            done.append("layer")
    if st.match_color:
        if src.get("wd_lc"):
            pg = getattr(dst.users_collection[0], "dessin_layer", None) if dst.users_collection else None
            if pg is not None and pg.use_color:
                dst.color = (pg.color[0], pg.color[1], pg.color[2], 1.0)
                dst["wd_lc"] = 1
            elif dst.get("wd_lc"):
                dst.color = (1.0, 1.0, 1.0, 1.0)
                del dst["wd_lc"]
        else:
            dst.color = tuple(src.color)
            if "wd_lc" in dst.keys():
                del dst["wd_lc"]
        done.append("color")
    elif "layer" in done:
        pg = getattr(dst.users_collection[0], "dessin_layer", None) if dst.users_collection else None
        if dst.get("wd_lc") and pg is not None and pg.use_color:
            dst.color = (pg.color[0], pg.color[1], pg.color[2], 1.0)
    if st.match_linetype and lt_eligible(dst):
        lt = src.get("wd_lt") if lt_eligible(src) else None
        if lt:
            dst["wd_lt"] = lt
        elif "wd_lt" in dst.keys():
            del dst["wd_lt"]
        done.append("linetype")
    if "layer" in done or "linetype" in done:
        lt_apply(dst)
    if st.match_print:
        lw = src.get("wd_lw")
        if lw:
            dst["wd_lw"] = float(lw)
        elif "wd_lw" in dst.keys():
            del dst["wd_lw"]
        done.append("print width")
    if st.match_material and getattr(src.data, "materials", None) is not None and getattr(dst.data, "materials", None) is not None \
            and src.type in {'MESH', 'CURVE', 'SURFACE', 'FONT', 'META'} and dst.type in {'MESH', 'CURVE', 'SURFACE', 'FONT', 'META'} \
            and not dst.get("dessin_hatch") and not src.get("dessin_hatch"):
        mats = list(src.data.materials)
        if mats or len(dst.data.materials):
            dst.data.materials.clear()
            for m in mats:
                dst.data.materials.append(m)
            done.append("material")
    if st.match_text and src.type == 'FONT' and dst.type == 'FONT':
        a, b = src.data, dst.data
        b.size = a.size
        if a.font is not None:
            b.font = a.font
        b.align_x, b.align_y = a.align_x, a.align_y
        b.space_line = a.space_line
        done.append("text")
    if st.match_hatch and "dessin_hatch" in src.keys() and "dessin_hatch" in dst.keys():
        import json
        from .hatch import HatchTooDense, rebuild_hatch
        from .settings import _HATCH_EDIT
        s = src.dessin_hatch
        _HATCH_EDIT["busy"] = True
        try:
            dst.dessin_hatch.pattern, dst.dessin_hatch.scale, dst.dessin_hatch.rotation = s.pattern, s.scale, s.rotation
            dd, ds = json.loads(dst["dessin_hatch"]), json.loads(src["dessin_hatch"])
            dd["unit"] = ds["unit"] * src.matrix_world.to_scale().x / max(dst.matrix_world.to_scale().x, 1e-12)
            dst["dessin_hatch"] = json.dumps(dd)
            rebuild_hatch(dst)
            done.append("hatch")
        except (HatchTooDense, KeyError, ValueError, RuntimeError):
            pass
        finally:
            _HATCH_EDIT["busy"] = False
    try:
        dst.update_tag()
    except (ReferenceError, AttributeError):
        pass
    return done


class DESSIN_OT_match_props(DessinBase):
    bl_idname = "dessin.match_props"
    bl_label = "Match Properties"
    bl_description = ("Like MATCHPROP: click the source object, then click the objects that should take its layer, color, "
                      "linetype, print width, material (and text or hatch settings). With objects already selected: click "
                      "the source and they all take its properties. The properties copied are chosen in the tool settings")

    TITLE = "Match Properties"
    EDIT_OK = False
    NEEDED = 1000
    PLANAR = False
    LOCK_OK = False
    COORD_OK = False

    def lock_allowed(self):
        return False

    def prompt(self):
        if self._src is None:
            if self._pre:
                return f"click the source object ({len(self._pre)} selected object{'s' if len(self._pre) > 1 else ''} will take its properties)"
            return "click the source object"
        return f"click the objects that take the properties of {self._src.name}   [Enter / Esc: done]"

    def invoke(self, context, event):
        self._mouse = None
        self._pre = [o for o in context.selected_objects] if context.mode == 'OBJECT' else []
        self._src = None
        self._count = 0
        return super().invoke(context, event)

    def update_cursor(self, context, event):
        region = find_window_region(self.area, event.mouse_x, event.mouse_y)
        self._mouse = (event.mouse_x - region.x, event.mouse_y - region.y) if region is not None else None
        super().update_cursor(context, event)

    def compute(self):
        return [], [], (f"{self._count} object(s) changed" if self._src is not None else ""), None

    def _pick(self, context):
        if self._mouse is None or self.region is None:
            return None
        from .selection import pick_object_at
        try:
            hit = pick_object_at(context, self.area, self.region, self._mouse[0], self._mouse[1])
        except (RuntimeError, ReferenceError, AttributeError, TypeError):
            hit = None
        o = hit[0] if hit else None
        if o is None:
            got = pick_curve_at(context, self.area, self.region, self._mouse[0], self._mouse[1], 10.0 * _ui())
            o = got[0] if got else None
        return o

    def click(self, context):
        o = self._pick(context)
        if o is None:
            self.report({'INFO'}, "Click an object")
            return
        st = context.scene.dessin
        if self._src is None:
            self._src = o
            if self._pre:
                n = 0
                for d in self._pre:
                    if d is not o and match_apply(context, o, d, st):
                        n += 1
                self._count = n
                self.finished = True
                self.report({'INFO'}, f"Match Properties: {n} object(s) took the properties of {o.name}")
                self._end = True
                return
            for x in context.selected_objects:
                x.select_set(False)
            try:
                o.select_set(True)
                context.view_layer.objects.active = o
            except RuntimeError:
                pass
            self.refresh(context)
            return
        if match_apply(context, self._src, o, st):
            self._count += 1
            _step(self, "Match Properties")
        self.refresh(context)

    def modal(self, context, event):
        if getattr(self, "_end", False):
            return self.exit(context)
        return super().modal(context, event)

    def exit(self, context):
        if getattr(self, "_did", False):
            self.finished = True
        return super().exit(context)


def draw_match_settings(layout, st):
    row = layout.row(align=True)
    for key, name in MATCH_KEYS:
        row.prop(st, key, text=name, toggle=True)


def _late_imports():
    pass
