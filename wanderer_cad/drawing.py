"""Wanderer CAD : Dessin de l'aperçu dans la vue, régions et fenêtres."""

import blf
import bpy
import gpu
import math
import numpy as np
import time
from bpy.app.handlers import persistent
from bpy_extras.view3d_utils import region_2d_to_origin_3d, region_2d_to_vector_3d
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector

from .core import (
    AXES3, IDLE_TOOL, KIND_OSNAP, MARKER_SCALE, SNAP_BIAS_LUT, SNAP_COLORS, SNAP_RADIUS, TAU, TRACK_COLORS,
    TRACK_RADIUS, _redraw_all_areas, osnap, pref,
)
from .snapping import (
    SnapData, _GEOM, _LOD, _SNAP_LAST, _SNAP_LOD, _TIER, _lod_cells, _perf_caches_clear, _snap_lod_sets,
    collect_snap_points,
)


# --------------------------------------------------------------------------
# Dessin de l'aperçu
# --------------------------------------------------------------------------

def get_shader(dim):
    if bpy.app.version >= (4, 0, 0):
        name = 'UNIFORM_COLOR'
    else:
        name = '3D_UNIFORM_COLOR' if dim == '3D' else '2D_UNIFORM_COLOR'
    return gpu.shader.from_builtin(name)


def _same_region(op):
    try:
        return op.region is not None and bpy.context.region.as_pointer() == op.region.as_pointer()
    except ReferenceError:
        return False


def preview_colors():
    """(couleur du tracé en cours, couleur des points posés) : trait blanc sur fond sombre (noir sur fond clair), points bleus."""
    try:
        bg = bpy.context.preferences.themes[0].view_3d.space.gradients.high_gradient
        lum = 0.299 * bg[0] + 0.587 * bg[1] + 0.114 * bg[2]
    except (AttributeError, IndexError, TypeError):
        lum = 0.2
    line = (0.1, 0.11, 0.13, 1.0) if lum > 0.5 else (0.89, 0.89, 0.9, 1.0)
    return line, (0.23, 0.52, 0.76, 1.0)


def draw_view_cb(op):
    if not _same_region(op):
        return
    shader = get_shader('3D')
    gpu.state.blend_set('ALPHA')
    gpu.state.depth_test_set('NONE')
    shader.bind()

    # Fantôme transparent de la position initiale (outil Déplacer)
    ghost = getattr(op, "ghost_pts", None)
    if ghost is not None and op.points:
        if getattr(op, "ghost_batch", None) is None:
            op.ghost_batch = batch_for_shader(shader, 'LINES', {"pos": ghost})
        gpu.state.line_width_set(1.0)
        shader.uniform_float("color", (0.85, 0.9, 1.0, 0.45))
        op.ghost_batch.draw(shader)

    boxes = getattr(op, "light_boxes", None)
    if boxes is not None and op.points and getattr(op, "light", False):
        if getattr(op, "light_batch", None) is None:
            op.light_batch = batch_for_shader(shader, 'LINES', {"pos": boxes})
        gpu.state.line_width_set(1.0)
        shader.uniform_float("color", (0.85, 0.9, 1.0, 0.35))
        op.light_batch.draw(shader)
        xf = getattr(op, "preview_xform", None)
        if xf is not None:
            gpu.matrix.push()
            gpu.matrix.multiply_matrix(xf)
            gpu.state.line_width_set(1.6)
            shader.uniform_float("color", (1.0, 0.72, 0.2, 0.95))
            op.light_batch.draw(shader)
            gpu.matrix.pop()

    for O, k in getattr(op, "track_lines", ()):
        L = 500.0
        d = k if isinstance(k, Vector) else AXES3[k]
        batch = batch_for_shader(shader, 'LINES', {"pos": [tuple(O - d * L), tuple(O + d * L)]})
        gpu.state.line_width_set(1.0)
        shader.uniform_float("color", (1.0, 0.8, 0.2, 0.9) if isinstance(k, Vector) else TRACK_COLORS[k])
        batch.draw(shader)
    acquired = getattr(op, "track_pts", None)
    if acquired:
        draw_px_points(acquired, 8.0 * px_scale(0.35), (0.2, 0.9, 0.9, 1.0))
        shader.bind()

    gpu.state.line_width_set(1.0)
    for g in op.guides:
        if len(g) >= 2:
            batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": [tuple(p) for p in g]})
            shader.uniform_float("color", (0.75, 0.75, 0.75, 0.8))
            batch.draw(shader)

    hl = getattr(op, "hatch_lines", None)
    if hl:
        gpu.state.line_width_set(1.0)
        batch = batch_for_shader(shader, 'LINES', {"pos": hl})
        shader.uniform_float("color", (0.15, 1.0, 0.45, 0.55))
        batch.draw(shader)

    hil = getattr(op, "hilite", None)
    if hil:
        pts = [tuple(q) for seg in hil for q in seg]
        gpu.state.line_width_set(4.0 * px_scale())
        batch = batch_for_shader(shader, 'LINES', {"pos": pts})
        shader.uniform_float("color", (0.15, 1.0, 0.45, 1.0))
        batch.draw(shader)
        draw_px_points(pts, 8.0 * px_scale(0.35), (0.15, 1.0, 0.45, 1.0))
        shader.bind()

    line_col, point_col = preview_colors()
    gpu.state.line_width_set(2.0 * px_scale())
    for strip in getattr(op, "preview_extra", ()):
        if len(strip) >= 2:
            batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": [tuple(p) for p in strip]})
            shader.uniform_float("color", line_col)
            batch.draw(shader)
    if len(op.preview) >= 2:
        batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": [tuple(p) for p in op.preview]})
        shader.uniform_float("color", line_col)
        batch.draw(shader)

    if op.points and not getattr(op, "HIDE_POINTS", False):
        draw_px_points(op.points, 8.0 * px_scale(0.35), point_col)
        shader.bind()

    gpu.state.line_width_set(1.0)
    gpu.state.blend_set('NONE')


def draw_px_points(pts, size, color):
    """Points carrés dessinés en pixels écran (taille identique quelle que soit la version de Blender / l'écran Retina),
    à la place de gpu.state.point_size_set dont l'échelle varie d'une version à l'autre."""
    try:
        ctx = bpy.context
        region, rv3d = ctx.region, ctx.region_data
        if region is None or rv3d is None or pts is None or len(pts) == 0 or region.width < 2 or region.height < 2:
            return
        h = size / 2.0
        P = np.asarray([tuple(p) for p in pts] if not isinstance(pts, np.ndarray) else pts, dtype=np.float64).reshape(-1, 3)
        M = np.array(rv3d.perspective_matrix, dtype=np.float64)
        clip = np.hstack((P, np.ones((len(P), 1)))) @ M.T
        w_ = clip[:, 3]
        ok = w_ > 1e-9                      # derrière la caméra : pas dessiné (comme location_3d_to_region_2d)
        if not ok.any():
            return
        clip = clip[ok]
        xy = np.empty((len(clip), 2))
        xy[:, 0] = (clip[:, 0] / clip[:, 3] * 0.5 + 0.5) * region.width
        xy[:, 1] = (clip[:, 1] / clip[:, 3] * 0.5 + 0.5) * region.height
        off = np.array(((-h, -h), (h, -h), (h, h), (-h, -h), (h, h), (-h, h)))
        tris = (xy[:, None, :] + off[None, :, :]).reshape(-1, 2).astype(np.float32)
        w, ht = float(region.width), float(region.height)
        proj = Matrix(((2.0 / w, 0.0, 0.0, -1.0), (0.0, 2.0 / ht, 0.0, -1.0), (0.0, 0.0, 1.0, 0.0), (0.0, 0.0, 0.0, 1.0)))
        sh = get_shader('2D')
        with gpu.matrix.push_pop():
            with gpu.matrix.push_pop_projection():
                gpu.matrix.load_matrix(Matrix.Identity(4))
                gpu.matrix.load_projection_matrix(proj)
                sh.bind()
                sh.uniform_float("color", color)
                batch_for_shader(sh, 'TRIS', {"pos": tris}).draw(sh)
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
        pass


def px_scale(k=1.0):
    """Facteur d'échelle de l'interface (écran Retina / haute densité, échelle de résolution) pour les dessins en pixels."""
    try:
        sysp = bpy.context.preferences.system
        ps = getattr(sysp, "pixel_size", 1.0) or 1.0
        # le dpi d'un écran Retina (144) contient déjà l'échelle de pixel (2) : on ne les multiplie pas l'un par l'autre
        sc = max(1.0, (sysp.ui_scale or 1.0) * max((sysp.dpi or 72) / 72.0, ps))
        return 1.0 + (sc - 1.0) * k      # k < 1 : agrandissement atténué
    except (AttributeError, ReferenceError):
        return 1.0


def draw_snap_marker(x, y, kind):
    sc = px_scale(MARKER_SCALE)
    s = 7.0 * sc
    mode = 'LINE_LOOP'
    if kind in (0, 4):     # carré
        pts = [(x - s, y - s), (x + s, y - s), (x + s, y + s), (x - s, y + s)]
    elif kind == 1:        # triangle
        pts = [(x - s, y - s), (x + s, y - s), (x, y + s)]
    elif kind == 2:        # cercle
        pts = [(x + s * math.cos(a * TAU / 16), y + s * math.sin(a * TAU / 16)) for a in range(16)]
    elif kind in (6, 8):   # croix
        mode, pts = 'LINES', [(x - s, y - s), (x + s, y + s), (x - s, y + s), (x + s, y - s)]
    elif kind == 7:        # sablier
        pts = [(x - s, y + s), (x + s, y + s), (x - s, y - s), (x + s, y - s)]
    elif kind == 9:        # équerre
        mode, pts = 'LINE_STRIP', [(x - s, y + s), (x - s, y - s), (x + s, y - s)]
    elif kind == 10:       # cercle + tangente
        pts = [(x + s * math.cos(a * TAU / 16), y + s * math.sin(a * TAU / 16) - s * 0.2) for a in range(16)]
    else:                  # losange
        pts = [(x - s, y), (x, y - s), (x + s, y), (x, y + s)]
    shader = get_shader('2D')
    gpu.state.blend_set('ALPHA')
    gpu.state.line_width_set(2.0 * sc)
    batch = batch_for_shader(shader, mode, {"pos": pts})
    shader.bind()
    shader.uniform_float("color", SNAP_COLORS.get(kind, (1, 1, 1, 1)))
    batch.draw(shader)
    if kind == 10:
        batch = batch_for_shader(shader, 'LINES', {"pos": [(x - s * 1.3, y + s * 0.9), (x + s * 1.3, y + s * 0.9)]})
        batch.draw(shader)
    gpu.state.line_width_set(1.0)
    gpu.state.blend_set('NONE')


def draw_rhino_cursor(x, y):
    """Réticule des outils de tracé. Style Rhino : carré de sélection + quatre barres détachées ;
    style AutoCAD : deux lignes qui traversent la vue (taille en % de la vue) + carré de sélection."""
    sc = px_scale(1.0)
    col = tuple(pref("cursor_color")) + (1.0,)
    r = max(1.0, pref("cursor_pick")) * sc
    shader = get_shader('2D')
    gpu.state.blend_set('ALPHA')
    shader.bind()
    lines = [(x - r, y - r), (x + r, y - r), (x + r, y - r), (x + r, y + r), (x + r, y + r), (x - r, y + r), (x - r, y + r), (x - r, y - r)]
    if pref("cursor_style") == 'AUTOCAD':
        try:
            reg = bpy.context.region
            span = float(max(reg.width, reg.height))
        except (AttributeError, ReferenceError):
            span = 1000.0
        half = max(r * 2.0, span * pref("cursor_size") / 100.0 * (0.5 if pref("cursor_size") < 100 else 1.0))
        lines += [(x - half, y), (x - r, y), (x + r, y), (x + half, y), (x, y - half), (x, y - r), (x, y + r), (x, y + half)]
        gpu.state.line_width_set(max(1.0, 1.0 * sc))
        shader.uniform_float("color", col)
        batch_for_shader(shader, 'LINES', {"pos": lines}).draw(shader)
    else:
        off = r + 10.5 * sc
        tris_b, tris_w = [], []

        def quad(out, cx, cy, hw, hh):
            a, b, c, d = (cx - hw, cy - hh), (cx + hw, cy - hh), (cx + hw, cy + hh), (cx - hw, cy + hh)
            out += [a, b, c, a, c, d]

        for dx, dy, hw, hh in ((-off, 0, 3.5, 1.2), (off, 0, 3.5, 1.2), (0, -off, 1.2, 3.5), (0, off, 1.2, 3.5)):
            quad(tris_b, x + dx, y + dy, hw * sc + 0.9 * sc if hw > hh else hw * sc + 0.9 * sc, hh * sc + 0.9 * sc)
            quad(tris_w, x + dx, y + dy, hw * sc, hh * sc)
        for pts, c in ((tris_b, (0.0, 0.0, 0.0, 1.0)), (tris_w, col)):
            shader.uniform_float("color", c)
            batch_for_shader(shader, 'TRIS', {"pos": pts}).draw(shader)
        gpu.state.line_width_set(max(1.0, 1.0 * sc))
        shader.uniform_float("color", (0.0, 0.0, 0.0, 1.0))
        batch_for_shader(shader, 'LINES', {"pos": lines}).draw(shader)
    gpu.state.line_width_set(1.0)
    gpu.state.blend_set('NONE')


def draw_pixel_cb(op):
    if not _same_region(op):
        return
    lab = getattr(op, "dim_label", None)
    if lab is not None:
        try:
            sp = project_px(bpy.context.region_data, bpy.context.region, lab[0])
        except (AttributeError, ReferenceError):
            sp = None
        if sp is not None:
            try:
                blf.size(0, 15)
            except TypeError:
                blf.size(0, 15, 72)
            blf.color(0, 0.4, 0.95, 0.95, 1.0)
            w, _h = blf.dimensions(0, lab[1])
            blf.position(0, sp.x - w / 2.0, sp.y + 8.0, 0)
            blf.draw(0, lab[1])
    ts = getattr(op, "track_screen", None)
    if ts is not None and op.snap_screen is None:
        x, y = ts
        sc = px_scale(MARKER_SCALE)
        s = 6.0 * sc
        shader = get_shader('2D')
        gpu.state.blend_set('ALPHA')
        gpu.state.line_width_set(2.0 * sc)
        batch = batch_for_shader(shader, 'LINES', {"pos": [(x - s, y - s), (x + s, y + s), (x - s, y + s), (x + s, y - s)]})
        shader.bind()
        shader.uniform_float("color", (0.2, 0.9, 0.9, 1.0))
        batch.draw(shader)
        gpu.state.line_width_set(1.0)
        gpu.state.blend_set('NONE')
    if getattr(op, "box", None) is not None:
        draw_box_cb(op)
    if op.snap_screen is not None:
        draw_snap_marker(op.snap_screen[0], op.snap_screen[1], op.snap_kind)


def project_px(rv3d, region, p):
    """Position écran (pixels dans la région) d'un point 3D, ou None s'il est derrière la caméra."""
    v = rv3d.perspective_matrix @ Vector((p.x, p.y, p.z, 1.0))
    if v.w <= 1e-9:
        return None
    return Vector(((v.x / v.w * 0.5 + 0.5) * region.width, (v.y / v.w * 0.5 + 0.5) * region.height))


def track_lines_near(origins, dirs, rv3d, region, mx, my, extra=None):
    """Lignes de repérage (origine, direction) passant à moins de TRACK_RADIUS pixels du curseur.
    direction : indice d'axe (0 / 1 / 2) ou vecteur unitaire (prolongement d'un segment : extra(O) -> [vecteurs])."""
    found = []
    m = Vector((mx, my))
    for O in origins:
        a = project_px(rv3d, region, O)
        if a is None or (m - a).length < 8.0:
            continue
        for k in list(dirs) + (list(extra(O)) if extra is not None else []):
            d = k if isinstance(k, Vector) else AXES3[k]
            b = None
            for sgn in (1.0, -1.0):
                step = 1.0
                for _ in range(5):
                    bb = project_px(rv3d, region, O + d * (step * sgn))
                    if bb is None:
                        break
                    if (bb - a).length >= 40.0:
                        b = bb
                        break
                    step *= 4.0
                if b is not None:
                    break
            if b is None:
                continue
            ab = b - a
            dist = abs((m.x - a.x) * ab.y - (m.y - a.y) * ab.x) / ab.length
            if dist < TRACK_RADIUS:
                found.append((dist, O, k))
    found.sort(key=lambda t: t[0])
    return found


def _seg_dist2d(ax, ay, bx, by, px, py):
    """Distance (pixels) d'un point à des segments écran."""
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    safe = np.where(L > 1e-12, L, 1.0)
    t = np.clip(np.where(L > 1e-12, ((px - ax) * dx + (py - ay) * dy) / safe, 0.0), 0.0, 1.0)
    return np.hypot(ax + t * dx - px, ay + t * dy - py)


def _seg_seg_point(a, b, c, d):
    """Point d'intersection 3D de deux segments (extrémités exclues : elles sont déjà des accroches), ou None."""
    d1, d2, r = b - a, d - c, a - c
    a_, e_, b_ = d1.dot(d1), d2.dot(d2), d1.dot(d2)
    den = a_ * e_ - b_ * b_
    if a_ < 1e-18 or e_ < 1e-18 or den < 1e-9 * a_ * e_:
        return None
    c_, f_ = d1.dot(r), d2.dot(r)
    s_ = (b_ * f_ - c_ * e_) / den
    t_ = (b_ * s_ + f_) / e_
    if not (1e-6 < s_ < 1.0 - 1e-6 and 1e-6 < t_ < 1.0 - 1e-6):
        return None
    p, q = a + d1 * s_, c + d2 * t_
    if (p - q).length > 1e-4 * (d1.length + d2.length):
        return None
    return (p + q) * 0.5


_TAN = {"first_ok": False, "pend": None, "info": None}     # Tan : cercle mémorisé au 1er point, résultat de la dernière accroche calculée


def circle_samples(circ, n=160):
    """Points du cercle idéal (même repère que circle_info), réduits à ceux qui touchent la partie dessinée (arc)."""
    cc, r, nn, e1, e2, P, tol = circ
    th = np.linspace(0.0, 2.0 * math.pi, n, endpoint=False)
    S = cc + r * (np.cos(th)[:, None] * e1 + np.sin(th)[:, None] * e2)
    if len(P) <= 400:
        d = np.min(np.linalg.norm(S[:, None, :] - P[None, :, :], axis=2), axis=1)
        S = S[d <= tol * 2.0]
    return S


def common_tangents(A, B):
    """Tangentes communes à deux cercles coplanaires : liste de (point sur A, point sur B), 2 extérieures + 2 croisées. [] sinon."""
    ca, ra, na, e1a, e2a = A[0], A[1], A[2], A[3], A[4]
    cb, rb, nb = B[0], B[1], B[2]
    if abs(float(na @ nb)) < 0.999:
        return []
    d3 = cb - ca
    if abs(float(d3 @ na)) > 1e-4 * max(ra, rb, 1e-9):
        return []
    L = float(np.linalg.norm(d3))
    if L < 1e-9:
        return []
    u = d3 / L
    w = np.cross(na, u)
    out = []
    for b in (1.0, -1.0):          # b = 1 : tangentes extérieures, b = -1 : croisées
        delta = b * rb - ra
        c = delta / L
        if abs(c) > 1.0:
            continue
        s_ = math.sqrt(max(0.0, 1.0 - c * c))
        for sg in ((1.0, -1.0) if s_ > 1e-12 else (1.0,)):
            m = c * u + sg * s_ * w
            out.append((ca - ra * m, cb - b * rb * m))
    return out


def dynamic_snap(snap, mx, my, region, rv3d, persp, ref, radius, more=()):
    """Accroches calculées au curseur : Int, Perp, Tan, Near (dans cet ordre de priorité).
    more : détails chargés sous le curseur, dont les arêtes s'ajoutent à celles de `snap`."""
    want_near, want_int = osnap("near"), osnap("int")
    want_perp = osnap("perp") and ref is not None
    want_tan = osnap("tan") and (ref is not None or _TAN["first_ok"])
    here = Vector((mx, my))
    close = []          # (distance écran, tableau d'arêtes, n° d'arête) des arêtes proches du curseur, toutes sources réunies
    if want_near or want_int or want_perp:
        m = radius * 1.5
        for src in (snap,) + tuple(more):
            edges = getattr(src, "edges", None)
            if edges is None or not len(edges):
                continue
            sxa, sya, sxb, syb, eok, exmin, exmax, eymin, eymax = _edge_screen(src, persp, region)
            with np.errstate(invalid='ignore'):
                near_box = (eok & (exmin <= mx + m) & (exmax >= mx - m) & (eymin <= my + m) & (eymax >= my - m))
            idx = np.nonzero(near_box)[0]
            if len(idx):
                dist = _seg_dist2d(sxa[idx], sya[idx], sxb[idx], syb[idx], mx, my)
                for o in np.argsort(dist)[:16]:
                    if dist[o] <= m:
                        close.append((float(dist[o]), edges, int(idx[o])))
        if more and len(close) > 1:
            close.sort(key=lambda t: t[0])
            del close[16:]
    best = {}

    def offer(kind, p3, extra=None):
        sp = project_px(rv3d, region, p3)
        if sp is None:
            return
        d = (sp - here).length
        if d <= radius and (kind not in best or d < best[kind][0]):
            best[kind] = (d, p3, (sp.x, sp.y), extra)

    seg = lambda e: (Vector(e[1][e[2], 0]), Vector(e[1][e[2], 1]))
    if want_int and len(close) >= 2:
        for i in range(len(close)):
            for j in range(i + 1, len(close)):
                a, b = seg(close[i])
                c, d = seg(close[j])
                pt = _seg_seg_point(a, b, c, d)
                if pt is not None:
                    offer(8, pt)
    if want_perp:
        for e_ in close:
            a, b = seg(e_)
            ab = b - a
            L = ab.dot(ab)
            if L > 1e-18:
                t = (ref - a).dot(ab) / L
                if 0.0 < t < 1.0:
                    offer(9, a + ab * t)
    if want_tan and ref is None:
        # 1er point : on s'accroche au cercle (le point de tangence sera calculé au 2e clic, comme dans Rhino)
        for circ in list(getattr(snap, "circles", ()))[:300]:
            S = circle_samples(circ)
            if not len(S):
                continue
            sx, sy, ok = _project_region(S, persp, region)
            dd = np.hypot(sx - mx, sy - my)
            dd[~ok] = np.inf
            j = int(np.argmin(dd))
            if dd[j] <= radius:
                offer(10, Vector(S[j]), ("first", circ))
    elif want_tan:
        pend = _TAN["pend"]
        if pend is not None:
            for circ in list(getattr(snap, "circles", ()))[:300]:
                if circ[0] is pend[0] or float(np.linalg.norm(circ[0] - pend[0])) < 1e-9:
                    continue
                for ta, tb in common_tangents(pend, circ):
                    if any(float(np.min(np.linalg.norm(c_[5] - t_, axis=1))) > c_[6] * 2.0 for c_, t_ in ((pend, ta), (circ, tb))):
                        continue
                    offer(10, Vector(tb), ("common", Vector(ta)))
        for (cc, r, n, e1, e2, P, tol) in getattr(snap, "circles", ()):
            v = np.array(ref, dtype=np.float64) - cc
            v = v - n * float(v @ n)
            dd = float(np.linalg.norm(v))
            if dd <= r * 1.0001:
                continue
            phi = math.atan2(float(v @ e2), float(v @ e1))
            alpha = math.acos(r / dd)
            for sg in (1.0, -1.0):
                th = phi + sg * alpha
                T = cc + r * (math.cos(th) * e1 + math.sin(th) * e2)
                if float(np.min(np.linalg.norm(P - T, axis=1))) <= tol:
                    offer(10, Vector(T))
    if want_near and close and close[0][0] <= radius and 7 not in best:
        a, b = seg(close[0])
        o = region_2d_to_origin_3d(region, rv3d, here)
        v = region_2d_to_vector_3d(region, rv3d, here)
        d1, r_ = b - a, a - o
        a_, b_, c_, f_ = d1.dot(d1), d1.dot(v), d1.dot(r_), v.dot(r_)
        den = a_ - b_ * b_
        s_ = 0.0 if den < 1e-12 * max(a_, 1e-12) else (b_ * f_ - c_) / den
        pn = a + d1 * min(1.0, max(0.0, s_))
        try:
            # corde d'un cercle ou d'un arc connu : le point Near est reporté sur le cercle vrai (sinon il reste sur la corde,
            # jusqu'à 0,03 % du rayon à l'intérieur)
            an, bn = np.array(a, dtype=np.float64), np.array(b, dtype=np.float64)
            for (cc, r, n, e1, e2, P, tol) in list(getattr(snap, "circles", ()))[:300]:
                on = True
                for q in (an, bn):
                    w = q - cc
                    hgt = float(w @ n)
                    if abs(hgt) > tol or abs(float(np.linalg.norm(w - n * hgt)) - r) > tol:
                        on = False
                        break
                if on:
                    w = np.array(pn, dtype=np.float64) - cc
                    w = w - n * float(w @ n)
                    lw = float(np.linalg.norm(w))
                    if lw > 1e-12:
                        pn = Vector(cc + w * (r / lw))
                    break
        except (ValueError, TypeError):
            pass
        offer(7, pn)
    for kind in (8, 9, 10, 7):
        if kind in best:
            d, p3, sp, extra = best[kind]
            _TAN["info"] = extra
            return p3, sp, kind
    return None


_CELL = 48.0


def _build_screen_index(snap, persp, region_w, region_h):
    """Calcul pur (sans accès à Blender) : projection écran + grille spatiale. Peut tourner dans un thread."""
    pts, hom = snap[0], snap[1]
    span = getattr(snap, "obj_span", None)
    if span is not None:
        # grosse scène : on écarte d'abord les objets dont la boîte englobante est hors de la vue (zoom sur un détail :
        # presque tout), puis seuls leurs points restants sont projetés. Les autres ne sont jamais candidats.
        s_, e_, lo, hi = span
        m_ = len(s_)
        cor = np.empty((m_, 8, 4), dtype=np.float64)
        for j in range(8):
            cor[:, j, 0] = hi[:, 0] if j & 1 else lo[:, 0]
            cor[:, j, 1] = hi[:, 1] if j & 2 else lo[:, 1]
            cor[:, j, 2] = hi[:, 2] if j & 4 else lo[:, 2]
        cor[:, :, 3] = 1.0
        cc = cor @ persp.T
        wc = cc[..., 3]
        front = wc > 1e-9
        wsc = np.where(front, wc, 1.0)
        bx = (cc[..., 0] / wsc * 0.5 + 0.5) * region_w
        by = (cc[..., 1] / wsc * 0.5 + 0.5) * region_h
        out = front.all(axis=1) & ((bx.max(1) < -_CELL) | (bx.min(1) > region_w + _CELL)
                                   | (by.max(1) < -_CELL) | (by.min(1) > region_h + _CELL))
        gone = int((e_[out] - s_[out]).sum())
    if span is not None and gone * 2 > len(pts):
        sel = np.ones(len(pts), dtype=bool)
        for a_, b_ in zip(s_[out].tolist(), e_[out].tolist()):
            sel[a_:b_] = False
        idx = np.nonzero(sel)[0]
        clip = hom[idx] @ persp.T
        w = clip[:, 3]
        okv = w > 1e-9
        ws = np.where(okv, w, 1.0)
        sxv = (clip[:, 0] / ws * 0.5 + 0.5) * region_w
        syv = (clip[:, 1] / ws * 0.5 + 0.5) * region_h
        okv &= (np.abs(sxv) < 1e5) & (np.abs(syv) < 1e5)
        vis = okv & (sxv > -_CELL) & (sxv < region_w + _CELL) & (syv > -_CELL) & (syv < region_h + _CELL)
        keep = np.nonzero(vis)[0]
        ix = np.floor(sxv[keep] / _CELL).astype(np.int64) + 2100
        iy = np.floor(syv[keep] / _CELL).astype(np.int64) + 2100
        ksel = ix * 5000 + iy
        srt = np.argsort(ksel, kind='stable')
        order = idx[keep][srt]
        sx = np.zeros(len(pts), dtype=np.float64)
        sy = np.zeros(len(pts), dtype=np.float64)
        ok = np.zeros(len(pts), dtype=bool)
        sx[idx], sy[idx], ok[idx] = sxv, syv, okv
        return {"sx": sx, "sy": sy, "ok": ok, "key": ksel[srt], "order": order, "edges": None}
    clip = hom @ persp.T
    w = clip[:, 3]
    ok = w > 1e-9
    ws = np.where(ok, w, 1.0)
    sx = (clip[:, 0] / ws * 0.5 + 0.5) * region_w
    sy = (clip[:, 1] / ws * 0.5 + 0.5) * region_h
    ok &= (np.abs(sx) < 1e5) & (np.abs(sy) < 1e5)
    ix = np.floor(np.clip(sx, -1e5, 1e5) / _CELL).astype(np.int64) + 2100
    iy = np.floor(np.clip(sy, -1e5, 1e5) / _CELL).astype(np.int64) + 2100
    key = ix * 5000 + iy
    # seuls les points visibles (marge d'une cellule) sont triés
    vis = ok & (sx > -_CELL) & (sx < region_w + _CELL) & (sy > -_CELL) & (sy < region_h + _CELL)
    order = np.nonzero(vis)[0]
    ksel = key[order]
    srt = np.argsort(ksel, kind='stable')
    order = order[srt]
    return {"sx": sx, "sy": sy, "ok": ok, "key": ksel[srt], "order": order, "edges": None}


_ASYNC_MIN = 150000     # au-delà, l'index écran est construit dans un thread : la souris ne gèle plus à chaque changement de vue
_ASYNC = {"busy": False}


def _screen_index(snap, persp, region, allow_async=False):
    """Projection écran des points / arêtes d'accrochage + grille spatiale, gardées tant que la vue ne change pas.
    Retourne None si les données ne permettent pas de garder un cache (tuple simple), ou si l'index est en cours de calcul."""
    if not isinstance(snap, SnapData):
        return None
    sig = (persp.tobytes(), region.width, region.height)
    c = getattr(snap, "_scr", None)
    if c is not None and c["sig"] == sig:
        return c
    if allow_async and len(snap[0]) > _ASYNC_MIN:
        if not _ASYNC["busy"]:
            _ASYNC["busy"] = True
            rw, rh = region.width, region.height
            pm = persp.copy()

            def work():
                try:
                    res = _build_screen_index(snap, pm, rw, rh)
                    res["sig"] = sig
                    snap._scr = res
                except Exception:
                    pass
                _ASYNC["busy"] = False
                bpy.app.timers.register(_nav_redraw_all, first_interval=0.0)
            import threading
            threading.Thread(target=work, daemon=True).start()
        return None
    c = _build_screen_index(snap, persp, region.width, region.height)
    c["sig"] = sig
    snap._scr = c
    return c


def _nav_redraw_all():
    try:
        for win in bpy.context.window_manager.windows:
            for a in win.screen.areas:
                if a.type == 'VIEW_3D':
                    a.tag_redraw()
    except (AttributeError, RuntimeError):
        pass
    return None


def _screen_candidates(c, mx, my, r):
    """Indices des points dont la cellule touche le carré (mx, my) ± r."""
    span = int(math.ceil(r / _CELL))
    cx, cy = int(math.floor(mx / _CELL)) + 2100, int(math.floor(my / _CELL)) + 2100
    keys, order = c["key"], c["order"]
    parts = []
    for dx in range(-span, span + 1):
        base = (cx + dx) * 5000
        lo = np.searchsorted(keys, base + cy - span, side='left')
        hi = np.searchsorted(keys, base + cy + span, side='right')
        if hi > lo:
            parts.append(order[lo:hi])
    return np.concatenate(parts) if parts else np.zeros(0, dtype=np.int64)


def _edge_screen(snap, persp, region):
    """(sxa, sya, sxb, syb, ok, xmin, xmax, ymin, ymax) des arêtes, en cache tant que la vue ne change pas."""
    c = _screen_index(snap, persp, region)
    edges = snap.edges
    if c is not None and c["edges"] is not None:
        return c["edges"]
    sxa, sya, oka = _project_region(edges[:, 0], persp, region)
    sxb, syb, okb = _project_region(edges[:, 1], persp, region)
    res = (sxa, sya, sxb, syb, oka & okb, np.minimum(sxa, sxb), np.maximum(sxa, sxb), np.minimum(sya, syb), np.maximum(sya, syb))
    if c is not None:
        c["edges"] = res
    return res


_NAVST = {"pb": None, "t": 0.0, "timer": False}


def _nav_settle_redraw():
    """Redessine les vues 3D peu après la fin d'une navigation, pour retrouver l'accrochage."""
    if _NAVST["timer"]:
        return
    _NAVST["timer"] = True

    def later():
        _NAVST["timer"] = False
        try:
            for win in bpy.context.window_manager.windows:
                for a in win.screen.areas:
                    if a.type == 'VIEW_3D':
                        a.tag_redraw()
        except (AttributeError, RuntimeError):
            pass
        return None
    bpy.app.timers.register(later, first_interval=0.15)


def _depth_penalty(hom, persp):
    """Pénalité de 0 à 1 pixel selon la profondeur : entre deux points superposés à l'écran (le haut et le bas d'une boîte
    vue de dessus), l'accrochage prend celui qui est devant, pas celui qui est caché derrière."""
    clip = np.asarray(hom, dtype=np.float64) @ persp.T
    w = np.where(np.abs(clip[:, 3]) > 1e-12, clip[:, 3], 1e-12)
    z = clip[:, 2] / w
    if len(z) < 2:
        return np.zeros(len(z))
    lo, hi = float(np.min(z)), float(np.max(z))
    if hi - lo < 1e-12:
        return np.zeros(len(z))
    return (z - lo) / (hi - lo)


def _extra_candidate(ex, persp, region, mx, my, R, allowed):
    """Meilleur point du complément d'accrochage sous le curseur : (distance, point, écran, type) ou None."""
    hom = ex[1]
    if not len(hom):
        return None
    sig = (persp.tobytes(), region.width, region.height)
    pr = ex._proj
    if pr is None or pr[0] != sig:
        clip = hom @ persp.T
        w = clip[:, 3]
        ok = w > 1e-9
        ws = np.where(ok, w, 1.0)
        pr = (sig, (clip[:, 0] / ws * 0.5 + 0.5) * region.width, (clip[:, 1] / ws * 0.5 + 0.5) * region.height, ok,
              _depth_penalty(hom, persp))
        ex._proj = pr
    _sig, sx, sy, ok, pen = pr
    dist = np.hypot(sx - mx, sy - my) + ex[3] + pen
    bad = ~ok | ~allowed[ex[2]]
    if ex.excl is not None:
        bad |= ex.excl
    dist[bad] = np.inf
    i = int(np.argmin(dist))
    if dist[i] <= R:
        return float(dist[i]), Vector(ex[0][i]), (float(sx[i]), float(sy[i])), int(ex[2][i])
    return None


def find_snap_in(snap, mx, my, region, rv3d, ref=None):
    """Point d'accrochage le plus proche de (mx, my) en pixels. snap = (pts, hom, kinds, bias) (+ segments / cercles).
    ref : dernier point posé (pour Perp et Tan)."""
    _TAN["info"] = None
    if osnap("disable"):
        return None
    pts, hom, kinds, bias = snap
    persp = np.array(rv3d.perspective_matrix, dtype=np.float64)
    allowed = np.array([osnap(KIND_OSNAP[k]) for k in range(len(SNAP_BIAS_LUT))], dtype=bool)
    R = SNAP_RADIUS * px_scale()
    if isinstance(snap, SnapData):
        # pendant une navigation (pan / orbite / zoom) la vue change à chaque image : pas de recalcul coûteux, on attend qu'elle se stabilise
        now = time.monotonic()
        pb = persp.tobytes()
        cc = getattr(snap, "_scr", None)
        if cc is not None and cc["sig"][0] != pb and (cc["sig"][1], cc["sig"][2]) == (region.width, region.height):
            if _NAVST["pb"] != pb:
                _NAVST["pb"], _NAVST["t"] = pb, now
            if now - _NAVST["t"] < 0.12:
                _nav_settle_redraw()
                return None
    c = _screen_index(snap, persp, region, allow_async=True)
    extra = getattr(snap, "extra", None)
    # complément (objets créés ou modifiés depuis le calcul des grands tableaux) : peu de points, projetés directement
    cand = _extra_candidate(extra, persp, region, mx, my, R, allowed) if extra is not None else None
    # détail des objets allégés (très grosse scène, objets denses) qui sont sous le curseur
    # Leurs points rejoignent ceux des grands tableaux dans une seule comparaison : même résultat que si tout était en réserve.
    lods = _snap_lod_sets(snap, region, rv3d, mx, my, R) if isinstance(snap, SnapData) and snap.coarse else ()
    more = []
    parts = []      # (x écran, y écran, homogènes, biais, types, points) des candidats de chaque source
    if lods:
        vsig = (persp.tobytes(), region.width, region.height)
        for d_ in lods:
            lc = _lod_cells(d_, persp, region, mx, my, R, allowed)
            if lc is not None:
                c_, i_ = lc
                parts.append((c_["sx"][i_], c_["sy"][i_], d_[1][i_], d_[3][i_], d_[2][i_], d_[0][i_]))
            sc_ = getattr(d_, "_scr", None)
            if d_.edges is not None and sc_ is not None and sc_.get("sig") == vsig:
                more.append(d_)

    def best_of(parts):
        """Meilleur candidat de toutes les sources réunies : (distance, point, écran, type) ou None."""
        if not parts:
            return None
        if len(parts) == 1:
            sx_, sy_, hom_, bias_, kinds_, pts_ = parts[0]
        else:
            sx_, sy_, hom_, bias_, kinds_, pts_ = (np.concatenate([p_[k_] for p_ in parts]) for k_ in range(6))
        dist = np.hypot(sx_ - mx, sy_ - my) + bias_
        dist = dist + _depth_penalty(hom_, persp)       # points confondus à l'écran : le plus proche de l'œil gagne
        j = int(np.argmin(dist))
        if dist[j] <= R:
            return float(dist[j]), Vector(pts_[j]), (float(sx_[j]), float(sy_[j])), int(kinds_[j])
        return None
    if c is None and isinstance(snap, SnapData) and len(snap[0]) > _ASYNC_MIN:
        # index en cours de calcul en arrière-plan : ce qu'on vient de dessiner (et les détails déjà lus) reste accrochable
        bo = best_of(parts)
        if bo is not None and (cand is None or bo[0] <= cand[0]):
            cand = bo
        return (cand[1], cand[2], cand[3]) if cand is not None else None
    if c is not None:
        idx = _screen_candidates(c, mx, my, R)
        if len(idx):
            idx = idx[c["ok"][idx] & allowed[kinds[idx]]]
            exm = getattr(snap, "excl", None)
            if exm is not None and len(idx):
                idx = idx[~exm[idx]]
        if len(idx):
            parts.insert(0, (c["sx"][idx], c["sy"][idx], hom[idx], bias[idx], kinds[idx], pts[idx]))
        bo = best_of(parts)
        if bo is not None and (cand is None or bo[0] <= cand[0]):
            return bo[1], bo[2], bo[3]
        if cand is not None:
            return cand[1], cand[2], cand[3]
        return dynamic_snap(snap, mx, my, region, rv3d, persp, ref, R, more)
    clip = hom @ persp.T
    w = clip[:, 3]
    ok = w > 1e-9
    w_safe = np.where(ok, w, 1.0)
    sx = (clip[:, 0] / w_safe * 0.5 + 0.5) * region.width
    sy = (clip[:, 1] / w_safe * 0.5 + 0.5) * region.height
    dist = np.hypot(sx - mx, sy - my) + bias + _depth_penalty(hom, persp)
    dist[~ok | ~allowed[kinds]] = np.inf
    i = int(np.argmin(dist))
    if dist[i] <= R:
        return Vector(pts[i]), (float(sx[i]), float(sy[i])), int(kinds[i])
    return dynamic_snap(snap, mx, my, region, rv3d, persp, ref, R)


# Accrochage au survol quand un outil de la barre est actif mais qu'aucune commande ne tourne encore
_HOVER = {"data": None, "version": 0, "seen": -1, "time": 0.0, "running": 0}


def _clip_timer():
    _CLIP["pending"] = False
    if _CLIP["alive"]:
        update_clip_planes()
    return None


@persistent
def _on_depsgraph_update(scene=None, depsgraph=None, *args):
    _HOVER["version"] += 1
    v = _HOVER["version"]
    try:
        ups = depsgraph.updates if depsgraph is not None else None
        if ups is None or len(ups) > 5000:
            _GEOM["ver"].clear()
            _GEOM["all"] = v          # mise à jour massive (ou inconnue) : tout est à relire
            _GEOM["epoch"] += 1
        else:
            gv = _GEOM["ver"]
            moved = False
            for u in ups:
                if u.is_updated_geometry:
                    gv[u.id.name] = v
                    moved = True
                elif u.is_updated_transform:
                    moved = True
            if moved:
                _GEOM["epoch"] += 1   # une forme ou une position a changé (une simple sélection ne compte pas)
    except (AttributeError, ReferenceError, RuntimeError, TypeError):
        _GEOM["ver"].clear()
        _GEOM["all"] = v
        _GEOM["epoch"] += 1
    layer_check_new_objects()
    # plans de coupe : mise à jour regroupée (au plus ~20 fois par seconde) au lieu d'un passage sur tous les objets à chaque mise à jour de la scène
    if _CLIP["alive"] and not _CLIP["pending"]:
        _CLIP["pending"] = True
        try:
            bpy.app.timers.register(_clip_timer, first_interval=0.05)
        except (RuntimeError, ValueError):
            _CLIP["pending"] = False


def _apply_dimension_settings():
    """Applique l'épaisseur courante aux cotations déjà présentes (0 par défaut : fil simple, invisible au rendu)."""
    try:
        scenes = list(bpy.data.scenes)
    except (RuntimeError, AttributeError):
        return None  # données inaccessibles pendant l'activation : on réessaiera via le minuteur
    for sc in scenes:
        st = getattr(sc, "dessin", None)
        if st is not None:
            try:
                _cotation_thickness_update(st, None)
                ensure_dim_styles(st)
            except (RuntimeError, ReferenceError, AttributeError, TypeError, ValueError, KeyError):
                pass
            try:
                if "wd_dim_v2" not in sc.keys():
                    # une seule fois par scène : cotations en centimètres par défaut (avant : unités de la scène)
                    if st.unite_cote == 'SCENE':
                        st.unite_cote = 'CENTIMETERS'
                    sc["wd_dim_v2"] = 1
            except (RuntimeError, ReferenceError, AttributeError, TypeError, ValueError, KeyError):
                pass
            try:
                if "wd_shapes_v2" not in sc.keys():
                    # une seule fois par scène : les fichiers créés quand « Shapes as » valait Mesh par défaut passent à Curve
                    if st.sortie_formes == 'MESH':
                        st.sortie_formes = 'CURVE'
                    sc["wd_shapes_v2"] = 1
                    _redraw_all_areas()
            except (RuntimeError, ReferenceError, AttributeError, TypeError, ValueError, KeyError):
                pass
    return None


@persistent
def ensure_statusbar_osnap():
    """Pose la barre OSnap dans la barre d'état si elle n'y est plus (Blender peut la réinitialiser au démarrage ou au chargement d'un fichier)."""
    try:
        hdr = bpy.types.STATUSBAR_HT_header
        funcs = getattr(hdr.draw, "_draw_funcs", None) or []
        if statusbar_osnap not in funcs and not any(getattr(f, "__package__", "") == "statusbar_osnap" for f in funcs):
            hdr.prepend(statusbar_osnap)
            for win in bpy.context.window_manager.windows:
                for a in win.screen.areas:
                    a.tag_redraw()
    except Exception:
        pass
    return None


_NATIVE_SELECT = ("builtin.select", "builtin.select_box", "builtin.select_circle", "builtin.select_lasso")


def ensure_idle_tool():
    """Au démarrage / chargement d'un fichier : si l'outil actif est une sélection native de Blender (enregistrée dans le .blend),
    on remet Select / Move : seul lui traite les clics sur la barre (onglets de vues, ligne de commande)."""
    try:
        wm = bpy.context.window_manager
        for win in wm.windows:
            for area in win.screen.areas:
                if area.type != 'VIEW_3D':
                    continue
                region = next((r for r in area.regions if r.type == 'WINDOW'), None)
                if region is None:
                    continue
                with bpy.context.temp_override(window=win, area=area, region=region):
                    mode = bpy.context.mode
                    if mode not in ('OBJECT', 'EDIT_MESH'):
                        continue
                    tool = win.workspace.tools.from_space_view3d_mode(mode, create=False)
                    if tool is not None and tool.idname in _NATIVE_SELECT:
                        bpy.ops.wm.tool_set_by_id(name=IDLE_TOOL)
    except Exception:
        pass
    return None


@persistent
def _on_undo_redo(*args):
    """Annuler / rétablir : Blender peut remettre un maillage en place sans le signaler objet par objet,
    donc tout est relu au prochain passage (les caches lourds par objet restent, vérifiés par leur contenu)."""
    _HOVER["version"] += 1
    _GEOM["ver"].clear()
    _GEOM["all"] = _HOVER["version"]
    _GEOM["epoch"] += 1
    _SNAP_LAST["key"] = _SNAP_LAST["data"] = _SNAP_LAST["out"] = _SNAP_LAST["mkey"] = _SNAP_LAST["objsig"] = _SNAP_LAST["ov"] = None
    _SNAP_LAST["coarse"] = None
    _SNAP_LOD.clear()
    _LOD["pts"] = 0
    _LOD["pending"] = None
    _TIER["key"] = _TIER["box"] = None


@persistent
def _on_load_clear(*args):
    _perf_caches_clear()        # autre fichier : les caches d'accrochage et de boîtes ne valent plus rien
    _HOVER["version"] += 1
    _HOVER["data"] = None
    _FAR["told"] = False


def _on_load_post(*args):
    _SF["saved"] = _SF["solo"] = _SF["sig"] = None
    bpy.app.timers.register(ensure_statusbar_osnap, first_interval=0.5)
    bpy.app.timers.register(ensure_idle_tool, first_interval=1.0)
    _apply_dimension_settings()
    _NATIVE_GIZMOS["pending"] = False
    bpy.app.timers.register(_native_gizmos_off, first_interval=0.5)


def hover_draw_cursor(context, tool, xy):
    """Secours : marque d'accrochage dessinée par l'outil lui-même (aucune commande en cours)."""
    draw_rhino_cursor(xy[0], xy[1])     # toujours : le curseur de l'OS est masqué par l'outil (bl_cursor = 'NONE')
    if _HOVER["running"] > 0:
        return  # la commande en cours dessine déjà ses propres accrochages
    ctx = bpy.context
    region, rv3d = ctx.region, ctx.region_data
    if region is None or rv3d is None:
        return
    now = time.monotonic()
    stale = _HOVER["version"] != _HOVER["seen"]
    if _HOVER["data"] is None or (stale and now - _HOVER["time"] > 0.25):
        try:
            _HOVER["data"] = collect_snap_points(ctx)
        except Exception:
            _HOVER["data"] = None
            return
        _HOVER["seen"] = _HOVER["version"]
        _HOVER["time"] = now
    # xy suit le repère de dessin du curseur (fenêtre entière ou région selon le cas)
    try:
        vx, vy, _w, _h = gpu.state.viewport_get()
    except Exception:
        vx, vy = region.x, region.y
    ox, oy = region.x - vx, region.y - vy
    snap = find_snap_in(_HOVER["data"], xy[0] - ox, xy[1] - oy, region, rv3d)
    if snap is not None:
        draw_snap_marker(snap[1][0] + ox, snap[1][1] + oy, snap[2])


# --------------------------------------------------------------------------
# Régions
# --------------------------------------------------------------------------

def over_nav_gizmo(area, x, y):
    """Souris au-dessus du gizmo de navigation (cercle des axes + zoom / main / caméra) en haut à droite."""
    region = main_window_region(area)
    if region is None:
        return False
    space = area.spaces.active
    if not getattr(space, "show_gizmo", True) or not getattr(space, "show_gizmo_navigate", True):
        return False
    try:
        prefs = bpy.context.preferences
        if prefs.view.mini_axis_type == 'NONE':
            return False
        size = prefs.view.gizmo_size_navigate_v3d or 80
        # ui_scale contient déjà la densité de l'écran (Retina : 2, comme dpi / 72) : ne pas multiplier les deux,
        # sinon la zone du gizmo couvre tout le quart haut-droit de la vue sur Mac et y bloque les clics
        scale = prefs.system.ui_scale or 1.0
    except AttributeError:
        size, scale = 80, 1.0
    right = region.x + region.width
    if getattr(space, "show_region_ui", False):
        for r in area.regions:
            if r.type == 'UI' and r.x < right:
                right = r.x  # la barre latérale chevauche la vue : le gizmo se place à sa gauche
    top = region.y + region.height
    return right - 1.45 * size * scale <= x <= right and top - 3.6 * size * scale <= y <= top     # gizmo + ses 4 boutons


def area_over_ui(area, x, y):
    """Souris au-dessus de la barre d'outils, de la barre latérale, des en-têtes, du Gizmo de navigation ou de la barre de commande
    (ces zones recouvrent la vue 3D : un opérateur modal ne doit pas leur voler les clics)."""
    try:
        space = area.spaces.active
        shown = {'TOOLS': getattr(space, "show_region_toolbar", True), 'UI': getattr(space, "show_region_ui", True),
                 'HEADER': getattr(space, "show_region_header", True),
                 'TOOL_HEADER': getattr(space, "show_region_tool_header", True)}
        for r in area.regions:
            if shown.get(r.type) and r.x <= x < r.x + r.width and r.y <= y < r.y + r.height:
                return True
        return over_nav_gizmo(area, x, y) or cmd_hit(area, x, y) is not None
    except (AttributeError, ReferenceError, RuntimeError):
        return False


def find_window_region(area, x, y):
    for r in area.regions:
        if r.type == 'WINDOW' and r.x <= x < r.x + r.width and r.y <= y < r.y + r.height:
            return r
    return None


def main_window_region(area):
    best = None
    for r in area.regions:
        if r.type == 'WINDOW' and (best is None or r.width * r.height > best.width * best.height):
            best = r
    return best


def region_rv3d(region, area):
    rv3d = region.data
    if rv3d is None:
        rv3d = area.spaces.active.region_3d
    return rv3d


def _late_imports():
    """Noms définis dans des modules chargés après celui-ci : ils ne servent qu'à l'exécution des outils."""
    global _CLIP, _FAR, _NATIVE_GIZMOS, _SF, _cotation_thickness_update, _native_gizmos_off, _project_region
    global cmd_hit, draw_box_cb, ensure_dim_styles, layer_check_new_objects, statusbar_osnap, update_clip_planes
    from .selection import _project_region, draw_box_cb
    from .settings import _cotation_thickness_update, ensure_dim_styles
    from .layers import layer_check_new_objects
    from .curve_edit import _FAR
    from .display import _CLIP, _SF, update_clip_planes
    from .gumball_handles import _NATIVE_GIZMOS, _native_gizmos_off, statusbar_osnap
    from .command_line import cmd_hit
