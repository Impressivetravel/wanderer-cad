"""Wanderer CAD : Icônes des outils."""

import bpy
import math
import os

from .core import TAU, pref


# --------------------------------------------------------------------------
# Outil dans la barre d'outils de gauche
# --------------------------------------------------------------------------

ICON_WEIGHT = 1.7   # épaisseur des traits des icônes (1.0 = ancien style)
ICON_LINE = (222, 226, 232, 255)   # trait principal
ICON_DIM = (120, 128, 140, 255)    # constructions / objet d'origine
ICON_ACC = (255, 168, 38, 255)     # couleur d'accent : ce qui est créé, points à cliquer
ICON_FILL = (255, 168, 38, 70)     # aplat translucide de l'accent


class _IconPen:
    """Dessine des traits arrondis, des aplats et des points en triangles colorés (grille 0-255, y vers le haut)."""

    def __init__(self):
        self.tris = []

    @staticmethod
    def _pt(p):
        return (max(0, min(255, int(round(p[0])))), max(0, min(255, int(round(p[1])))))

    def _disc(self, c, r, col, n=10):
        for i in range(n):
            a0, a1 = TAU * i / n, TAU * (i + 1) / n
            self.tris.append((self._pt(c), self._pt((c[0] + r * math.cos(a0), c[1] + r * math.sin(a0))),
                              self._pt((c[0] + r * math.cos(a1), c[1] + r * math.sin(a1))), col))

    def line(self, pts, col, w, closed=False, joints=None):
        pts = list(pts)
        if closed:
            pts = pts + [pts[0]]
        hw = w * 0.30 * ICON_WEIGHT
        if joints is None:
            joints = len(pts) < 14
        for a, b in zip(pts, pts[1:]):
            dx, dy = b[0] - a[0], b[1] - a[1]
            ln = math.hypot(dx, dy)
            if ln < 1e-6:
                continue
            nx, ny = -dy / ln * hw, dx / ln * hw
            q = [(a[0] + nx, a[1] + ny), (b[0] + nx, b[1] + ny), (b[0] - nx, b[1] - ny), (a[0] - nx, a[1] - ny)]
            self.tris.append((self._pt(q[0]), self._pt(q[1]), self._pt(q[2]), col))
            self.tris.append((self._pt(q[0]), self._pt(q[2]), self._pt(q[3]), col))
        ends = pts if joints else (pts[:1] + pts[-1:])
        for p in ends:
            self._disc(p, hw, col)

    def poly(self, pts, fill, outline=None, w=9):
        if fill is not None:
            for i in range(1, len(pts) - 1):
                self.tris.append((self._pt(pts[0]), self._pt(pts[i]), self._pt(pts[i + 1]), fill))
        if outline is not None:
            self.line(pts, outline, w, closed=True)

    def dash(self, a, b, col, w=7, n=7):
        for i in range(n):
            t0, t1 = i / n, (i + 0.55) / n
            self.line([(a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0),
                       (a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1)], col, w, joints=False)

    def ell(self, c, rx, ry, col, w=9, fill=None, a0=0, a1=360):
        n = max(8, int(abs(a1 - a0) / 360.0 * 56))
        pts = [(c[0] + rx * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
                c[1] + ry * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]
        if fill is not None:
            for i in range(1, n):
                self.tris.append((self._pt(pts[0]), self._pt(pts[i]), self._pt(pts[i + 1]), fill))
        if col is not None:
            self.line(pts, col, w, joints=False)

    def dot(self, p, col, r=13):
        h = r * 0.34
        x0, y0, x1, y1 = p[0] - h, p[1] - h, p[0] + h, p[1] + h
        self.tris.append((self._pt((x0, y0)), self._pt((x1, y0)), self._pt((x1, y1)), col))
        self.tris.append((self._pt((x0, y0)), self._pt((x1, y1)), self._pt((x0, y1)), col))

    def arrow(self, a, b, col, w=9, h=26):
        self.line([a, b], col, w, joints=False)
        ang = math.atan2(b[1] - a[1], b[0] - a[0])
        tip = [b, (b[0] - h * math.cos(ang - 0.45), b[1] - h * math.sin(ang - 0.45)),
               (b[0] - h * math.cos(ang + 0.45), b[1] - h * math.sin(ang + 0.45))]
        self.tris.append((self._pt(tip[0]), self._pt(tip[1]), self._pt(tip[2]), col))


# ---- Icônes de la barre d'outils : dessin SVG (grille 24) converti en triangles colorés ----
ICON_SET = "_c16"          # version du dessin des icônes
ICON_PALETTES = (('EARTH', "Atlas", "One muted color per tool family (recommended)", 'e'),
                 ('BLUE', "Blueprint", "White icons, light blue for what the tool creates or modifies", 'b'),
                 ('AMBER', "Ochre", "The original look: white icons, ochre for what the tool creates", 'a'),
                 ('TARGET', "Target", "Dimmed grey icons: only what the tool creates or modifies lights up, in signal red", 't'))


def icon_suffix():
    code = {p[0]: p[3] for p in ICON_PALETTES}.get(pref("icon_palette"), 'e')
    try:     # le nom change dès que les familles de couleurs changent : Blender garde sinon l'ancienne icône en cache
        import zlib
        tag = "%04x" % (zlib.crc32(repr((ICON_FAMILIES, ICON_FAMILY_COLORS)).encode()) & 0xFFFF)
    except NameError:
        tag = ""
    return ICON_SET + tag + code
SVG_N = (228, 228, 230, 255)     # existant / contexte
SVG_A = (217, 168, 78, 255)      # ce que l'outil crée ou modifie
SVG_AF = (217, 168, 78, 48)      # aplat translucide
SVG_G = (133, 133, 138, 255)     # référence (pointillés)
SVG_STROKE = 1.05                # épaisseur du trait (unités de la grille 24)


def _svg_poly(pts):
    return [(x, y) for x, y in pts]


def _svg_arc(x1, y1, rx, ry, phi, fa, fs, x2, y2, n=18):
    """Arc elliptique SVG (conversion point d'arrivée -> centre) en liste de points."""
    if rx == 0 or ry == 0 or (x1 == x2 and y1 == y2):
        return [(x2, y2)]
    rx, ry = abs(rx), abs(ry)
    ph = math.radians(phi)
    cp, sp = math.cos(ph), math.sin(ph)
    dx, dy = (x1 - x2) / 2.0, (y1 - y2) / 2.0
    x1p, y1p = cp * dx + sp * dy, -sp * dx + cp * dy
    lam = (x1p ** 2) / (rx ** 2) + (y1p ** 2) / (ry ** 2)
    if lam > 1:
        rx *= math.sqrt(lam)
        ry *= math.sqrt(lam)
    num = rx ** 2 * ry ** 2 - rx ** 2 * y1p ** 2 - ry ** 2 * x1p ** 2
    den = rx ** 2 * y1p ** 2 + ry ** 2 * x1p ** 2
    co = math.sqrt(max(0.0, num / den)) if den else 0.0
    if fa == fs:
        co = -co
    cxp, cyp = co * rx * y1p / ry, -co * ry * x1p / rx
    cx, cy = cp * cxp - sp * cyp + (x1 + x2) / 2.0, sp * cxp + cp * cyp + (y1 + y2) / 2.0

    def ang(ux, uy, vx, vy):
        a = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
        return a
    t1 = ang(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dt = ang((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not fs and dt > 0:
        dt -= 2 * math.pi
    elif fs and dt < 0:
        dt += 2 * math.pi
    out = []
    steps = max(4, int(abs(dt) / (2 * math.pi) * 36))
    for i in range(1, steps + 1):
        t = t1 + dt * i / steps
        out.append((cx + rx * math.cos(t) * cp - ry * math.sin(t) * sp, cy + rx * math.cos(t) * sp + ry * math.sin(t) * cp))
    return out


def _svg_path(d):
    """Chemin SVG (M L H V C A Z, absolus et relatifs) -> [(points, fermé)]."""
    import re
    toks = re.findall(r"([MmLlHhVvCcSsAaZz])|(-?(?:\d+\.?\d*|\.\d+)(?:e-?\d+)?)", d)
    items = [t[0] if t[0] else float(t[1]) for t in toks]
    subs, cur, i = [], [], 0
    x = y = sx = sy = 0.0
    cmd = None
    last_c = None

    def num(n):
        nonlocal i
        v = items[i:i + n]
        i += n
        return v
    while i < len(items):
        if isinstance(items[i], str):
            cmd = items[i]
            i += 1
            if cmd in "Zz":
                if cur:
                    subs.append((cur, True))
                cur, x, y = [], sx, sy
                continue
        rel = cmd.islower()
        c = cmd.upper()
        if c not in "CS":
            last_c = None
        if c == "M":
            a, b = num(2)
            x, y = (x + a, y + b) if rel else (a, b)
            if cur:
                subs.append((cur, False))
            cur, sx, sy = [(x, y)], x, y
            cmd = "l" if rel else "L"
        elif c == "L":
            a, b = num(2)
            x, y = (x + a, y + b) if rel else (a, b)
            cur.append((x, y))
        elif c == "H":
            (a,) = num(1)
            x = x + a if rel else a
            cur.append((x, y))
        elif c == "V":
            (a,) = num(1)
            y = y + a if rel else a
            cur.append((x, y))
        elif c in "CS":
            if c == "C":
                v = num(6)
                if rel:
                    v = [v[0] + x, v[1] + y, v[2] + x, v[3] + y, v[4] + x, v[5] + y]
            else:
                w = num(4)
                if rel:
                    w = [w[0] + x, w[1] + y, w[2] + x, w[3] + y]
                v = [2 * x - last_c[0], 2 * y - last_c[1]] + list(w) if last_c else [x, y] + list(w)
            p0 = (x, y)
            last_c = (v[2], v[3])
            for k in range(1, 13):
                t = k / 12.0
                u = 1 - t
                cur.append((u ** 3 * p0[0] + 3 * u * u * t * v[0] + 3 * u * t * t * v[2] + t ** 3 * v[4],
                            u ** 3 * p0[1] + 3 * u * u * t * v[1] + 3 * u * t * t * v[3] + t ** 3 * v[5]))
            x, y = v[4], v[5]
        elif c == "A":
            rx, ry, phi, fa, fs, a, b = num(7)
            ex, ey = (x + a, y + b) if rel else (a, b)
            cur.extend(_svg_arc(x, y, rx, ry, phi, int(fa), int(fs), ex, ey))
            x, y = ex, ey
        else:
            i += 1
    if cur:
        subs.append((cur, False))
    return subs


def _svg_ear_clip(pts):
    """Triangulation d'un polygone simple (convexe ou non)."""
    n = len(pts)
    if n < 3:
        return []
    area = sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))
    idx = list(range(n)) if area > 0 else list(range(n))[::-1]
    tris = []

    def cross(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    def inside(p, a, b, c):
        return cross(a, b, p) >= -1e-9 and cross(b, c, p) >= -1e-9 and cross(c, a, p) >= -1e-9
    guard = 0
    while len(idx) > 3 and guard < 4000:
        guard += 1
        for k in range(len(idx)):
            a, b, c = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            if cross(pts[a], pts[b], pts[c]) <= 1e-9:
                continue
            if any(inside(pts[o], pts[a], pts[b], pts[c]) for o in idx if o not in (a, b, c)):
                continue
            tris.append((pts[a], pts[b], pts[c]))
            idx.pop(k)
            break
        else:
            break
    if len(idx) == 3:
        tris.append((pts[idx[0]], pts[idx[1]], pts[idx[2]]))
    return tris


def _svg_clip_convex(subject, clip):
    """Sutherland-Hodgman : subject découpé par le polygone convexe clip."""
    def side(p, a, b):
        return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
    area = sum(clip[i][0] * clip[(i + 1) % len(clip)][1] - clip[(i + 1) % len(clip)][0] * clip[i][1] for i in range(len(clip)))
    sgn = 1 if area > 0 else -1
    out = list(subject)
    for i in range(len(clip)):
        a, b = clip[i], clip[(i + 1) % len(clip)]
        inp, out = out, []
        if not inp:
            break
        for j in range(len(inp)):
            p, q = inp[j - 1], inp[j]
            sp, sq = side(p, a, b) * sgn, side(q, a, b) * sgn
            if sq >= 0:
                if sp < 0:
                    t = sp / (sp - sq)
                    out.append((p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t))
                out.append(q)
            elif sp >= 0:
                t = sp / (sp - sq)
                out.append((p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t))
    return out


def _svg_circle(cx, cy, r, n=40):
    return [(cx + r * math.cos(TAU * i / n), cy + r * math.sin(TAU * i / n)) for i in range(n)]


def _svg_shapes(inner):
    """Éléments SVG simples -> [(sous-chemins [(pts, fermé)], classe, opacité, tirets)]."""
    import re
    shapes = []
    pos = 0
    rot_re = re.compile(r"rotate\(\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s*\)")

    def rotate(subs, tr):
        m = rot_re.search(tr or "")
        if not m:
            return subs
        a, cx, cy = math.radians(float(m.group(1))), float(m.group(2)), float(m.group(3))
        ca, sa = math.cos(a), math.sin(a)
        return [([(cx + (px - cx) * ca - (py - cy) * sa, cy + (px - cx) * sa + (py - cy) * ca) for px, py in pts], c) for pts, c in subs]

    def element(tag, attrs, gtr=None):
        at = dict(re.findall(r'([\w-]+)="([^"]*)"', attrs))
        f = lambda k, d=0.0: float(at.get(k, d))
        subs = []
        if tag == "path":
            subs = _svg_path(at["d"])
        elif tag == "circle":
            subs = [(_svg_circle(f("cx"), f("cy"), f("r")), True)]
        elif tag == "ellipse":
            n = 44
            subs = [([(f("cx") + f("rx") * math.cos(TAU * i / n), f("cy") + f("ry") * math.sin(TAU * i / n)) for i in range(n)], True)]
        elif tag == "rect":
            x, y, w, h = f("x"), f("y"), f("width"), f("height")
            r = min(f("rx"), w / 2, h / 2)
            if r <= 0:
                subs = [([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], True)]
            else:
                pts = []
                for cx_, cy_, a0 in ((x + w - r, y + r, -90), (x + w - r, y + h - r, 0), (x + r, y + h - r, 90), (x + r, y + r, 180)):
                    for k in range(5):
                        a = math.radians(a0 + 90 * k / 4)
                        pts.append((cx_ + r * math.cos(a), cy_ + r * math.sin(a)))
                subs = [(pts, True)]
        subs = rotate(subs, at.get("transform"))
        subs = rotate(subs, gtr)
        dash = None
        if "stroke-dasharray" in at:
            v = [float(t) for t in at["stroke-dasharray"].split()]
            dash = (v[0], v[1] if len(v) > 1 else v[0])
        shapes.append((subs, at.get("class", "n"), float(at.get("opacity", 1)), dash))
    for m in re.finditer(r'<g transform="([^"]*)">(.*?)</g>|<(path|circle|rect|ellipse)\s+([^>]*?)/>', inner, re.S):
        if m.group(1) is not None:
            for mm in re.finditer(r"<(path|circle|rect|ellipse)\s+([^>]*?)/>", m.group(2)):
                element(mm.group(1), mm.group(2), m.group(1))
        else:
            element(m.group(3), m.group(4))
    return shapes


def _svg_to_pen(g, shapes):
    S = 256.0 / 24.0
    hw = SVG_STROKE * S / 2.0
    wscale = hw / (0.30 * ICON_WEIGHT)

    def P(p):
        return (p[0] * S, 256.0 - p[1] * S)

    def mul(col, k):
        return (col[0], col[1], col[2], int(col[3] * k))

    def stroke(pts, col, closed):
        pts = [P(p) for p in pts]
        if len(pts) < 2:
            return
        seq = pts + [pts[0]] if closed else pts
        g.line(seq, col, wscale, joints=False)
        # disques aux extrémités et aux angles marqués
        ends = {0, len(seq) - 1}
        for i in range(1, len(seq) - 1):
            a, b, c = seq[i - 1], seq[i], seq[i + 1]
            v1, v2 = (b[0] - a[0], b[1] - a[1]), (c[0] - b[0], c[1] - b[1])
            l1, l2 = math.hypot(*v1), math.hypot(*v2)
            if l1 > 1e-6 and l2 > 1e-6 and (v1[0] * v2[0] + v1[1] * v2[1]) / (l1 * l2) < 0.94:
                ends.add(i)
        for i in ends:
            g._disc(seq[i], hw, col)

    def dashed(pts, closed, dash):
        seq = pts + [pts[0]] if closed else pts
        on, off = dash[0], dash[1]
        out, cur, phase, left = [], [seq[0]], True, on
        for a, b in zip(seq, seq[1:]):
            ln = math.hypot(b[0] - a[0], b[1] - a[1])
            t = 0.0
            while ln - t > left:
                t += left
                p = (a[0] + (b[0] - a[0]) * t / ln, a[1] + (b[1] - a[1]) * t / ln)
                if phase:
                    cur.append(p)
                    out.append(cur)
                    cur = []
                else:
                    cur = [p]
                phase = not phase
                left = on if phase else off
            left -= ln - t
            if phase:
                cur.append(b)
        if phase and len(cur) > 1:
            out.append(cur)
        return out
    for subs, cls, op, dash in shapes:
        if op <= 0:
            continue
        col = {"n": SVG_N, "a": SVG_A, "af": SVG_A, "g": SVG_G}.get(cls, SVG_N)
        col = mul(col, op)
        if cls == "g" and dash is None:
            dash = (2.0, 2.4)
        for pts, closed in subs:
            if cls == "af" and len(pts) >= 3:
                for t in _svg_ear_clip(pts):
                    g.tris.append((g._pt(P(t[0])), g._pt(P(t[1])), g._pt(P(t[2])), mul(SVG_AF, op)))
            if dash is not None:
                for piece in dashed(pts, closed, dash):
                    stroke(piece, col, False)
            else:
                stroke(pts, col, closed)


def _svg_bool(kind):
    """Icônes booléennes : deux cercles, le résultat en accent."""
    A = _svg_circle(9.5, 12, 6.2)
    B = _svg_circle(14.5, 12, 6.2)
    lens = _svg_clip_convex(A, B)
    sh = []
    if kind == "bool_u":
        sh += [([(A, True)], "af", 1, None), ([(B, True)], "af", 1, None)]
    elif kind == "bool_d":
        sh += [([(A, True)], "af", 1, None), ([(B, True)], "g", 1, None)]
    else:
        sh += [([(lens, True)], "af", 1, None), ([(A, True)], "n", 1, None), ([(B, True)], "n", 1, None)]
        if kind == "bool_s":
            sh += [([([(12, 6.3), (12, 17.7)], False)], "a", 1, (2.0, 2.0))]
    return sh


def _svg_star():
    pts = []
    for i in range(10):
        r = 9.0 if i % 2 == 0 else 4.0
        a = -math.pi / 2 + i * math.pi / 5
        pts.append("%.2f %.2f" % (12 + r * math.cos(a), 12.5 + r * math.sin(a)))
    return "M" + " L".join(pts) + "z"


ICON_SVG = {
    'select': '<path class="n" d="M6 4l12 7.2-5.2 1.4L10.6 18z"/>',
    'lasso': '<path class="n" d="M12 4.5c-4.6 0-8 1.9-8 4.4s3.4 4.4 8 4.4 8-1.9 8-4.4-3.4-4.4-8-4.4z" stroke-dasharray="2.4 2.4"/><path class="a" d="M9.5 13c-.2 2.7.6 4.6 2.8 6.5"/>',
    'sel_box': '<rect class="n" x="4" y="4" width="13" height="13" rx="1" stroke-dasharray="2.4 2.4"/><path class="a" d="M11 9l8 4.8-3.4 1-1.6 3.4z"/>',
    'sel_circle': '<circle class="n" cx="10.5" cy="10.5" r="7" stroke-dasharray="2.4 2.4"/><path class="a" d="M11 9l8 4.8-3.4 1-1.6 3.4z"/>',
    'cursor': '<circle class="a" cx="12" cy="12" r="5"/><path class="n" d="M12 3v4M12 17v4M3 12h4M17 12h4"/>',
    'move': '<rect class="g" x="3.5" y="12.5" width="8" height="8" rx="1"/><rect class="af" x="12.5" y="3.5" width="8" height="8" rx="1"/><path class="n" d="M9 15l5-5M10.5 10H14v3.5"/>',
    'copy': '<rect class="n" x="3.5" y="8.5" width="11" height="11" rx="1.5"/><rect class="af" x="9.5" y="4.5" width="11" height="11" rx="1.5"/>',
    'rotate': '<path class="g" d="M5 19.5h8v-8H5z"/><g transform="rotate(35 15.5 8.5)"><rect class="af" x="11" y="4" width="9" height="9" rx="1"/></g><path class="n" d="M4.5 9A8 8 0 0 1 10 4M7.5 3.2 10.2 4 9 6.6"/>',
    'scale': '<rect class="g" x="3.5" y="13.5" width="7" height="7" rx="1"/><rect class="af" x="8.5" y="3.5" width="12" height="12" rx="1.5"/><path class="n" d="M10 14l5.5-5.5M11.5 8.5H15.5V12.5"/>',
    'scale2d': '<rect class="af" x="5.5" y="5.5" width="13" height="13" rx="1.5"/><path class="n" d="M3 12h3M18 12h3M12 3v3M12 18v3M4.5 10.5 3 12l1.5 1.5M19.5 10.5 21 12l-1.5 1.5M10.5 4.5 12 3l1.5 1.5M10.5 19.5 12 21l1.5-1.5"/>',
    'scale1d': '<rect class="af" x="6.5" y="7.5" width="11" height="9" rx="1.5"/><path class="n" d="M2.5 12H6M18 12h3.5M4 10.4 2.5 12 4 13.6M20 10.4l1.5 1.6-1.5 1.6"/>',
    'scalesize': '<rect class="af" x="6.5" y="6.5" width="11" height="11" rx="1.5"/><path class="n" d="M3 4v16M2 4h2M2 20h2M21 4v16M20 4h2M20 20h2"/>',
    'mirror': '<path class="g" d="M12 3v18"/><path class="n" d="M9 7 4 17h5z"/><path class="af" d="M15 7l5 10h-5z"/>',
    'array_l': '<rect class="n" x="2.5" y="8.5" width="5" height="7" rx="1"/><rect class="a" x="9.5" y="8.5" width="5" height="7" rx="1" opacity=".75"/><rect class="a" x="16.5" y="8.5" width="5" height="7" rx="1" opacity=".5"/>',
    'array_r': '<rect class="n" x="3.0" y="4" width="5" height="5.5" rx="1" opacity="1"/><rect class="a" x="3.0" y="12" width="5" height="5.5" rx="1" opacity="0.7"/><rect class="a" x="9.5" y="4" width="5" height="5.5" rx="1" opacity="0.7"/><rect class="a" x="9.5" y="12" width="5" height="5.5" rx="1" opacity="0.7"/><rect class="a" x="16.0" y="4" width="5" height="5.5" rx="1" opacity="0.7"/><rect class="a" x="16.0" y="12" width="5" height="5.5" rx="1" opacity="0.7"/>',
    'array_p': '<circle class="g" cx="12" cy="12" r="7.5"/><circle class="n" cx="12.00" cy="4.50" r="2.1"/><circle class="a" cx="19.13" cy="9.68" r="2.1"/><circle class="a" cx="16.41" cy="18.07" r="2.1"/><circle class="a" cx="7.59" cy="18.07" r="2.1"/><circle class="a" cx="4.87" cy="9.68" r="2.1"/>',
    'cut': '<rect class="n" x="3.5" y="5.5" width="17" height="13" rx="1.5"/><path class="a" d="M3 20 21 4" stroke-dasharray="3 2.4"/><path class="a" d="M19.5 20.5 4.5 3.5" opacity="0"/>',
    'fillet': '<path class="n" d="M4 20V12M12 4h8"/><path class="a" d="M4 12a8 8 0 0 1 8-8"/>',
    'chamfer': '<path class="n" d="M4 20V12M12 4h8"/><path class="a" d="M4 12 12 4"/>',
    'offset': '<path class="n" d="M4 17C4 9 10 5 20 5"/><path class="a" d="M4 21C4 11.5 11 8 21 8.5" opacity="0"/><path class="a" d="M8 20c0-6.5 4.5-10 12-10.2"/>',
    'srf_pts': '<path class="af" d="M5 17 3.5 7l15-2 2 11z"/><circle class="a" cx="3.5" cy="7" r="1.7"/><circle class="a" cx="18.5" cy="5" r="1.7"/><circle class="a" cx="20.5" cy="16" r="1.7"/><circle class="a" cx="5" cy="17" r="1.7"/>',
    'plane': '<path class="af" d="M7 6h14l-4 12H3z"/>',
    'polyline': '<path class="n" d="M3.5 17 9 8l6 8 5.5-10"/><circle class="a" cx="3.5" cy="17" r="1.7"/><circle class="a" cx="9" cy="8" r="1.7"/><circle class="a" cx="15" cy="16" r="1.7"/><circle class="a" cx="20.5" cy="6" r="1.7"/>',
    'curve_cp': '<path class="n" d="M3.5 17C7 4 12 4 12 12s5 8 8.5-5"/><circle class="a" cx="3.5" cy="17" r="1.7"/><circle class="a" cx="12" cy="12" r="1.7"/><circle class="a" cx="20.5" cy="7" r="1.7"/>',
    'curve_i': '<path class="n" d="M3.5 17C7 4 9 4 12 12s5 8 8.5-5"/><circle class="a" cx="3.5" cy="17" r="1.7"/><circle class="a" cx="12" cy="12" r="1.7"/><circle class="a" cx="8" cy="7" r="1.7"/><circle class="a" cx="20.5" cy="7" r="1.7"/>',
    'sketch': '<path class="n" d="M3.5 15c2-6 3.5-7 5-3s2.5 6 4.5 1 3-9 5-6 1.5 5 2.5 5.5"/><path class="g" d="M19 18l2-2" />',
    'pen': '<path class="n" d="M3.5 18C7 18 8 6 12 6s5 12 8.5 12"/><path class="g" d="M3.5 18 8 11M20.5 18 16 11"/><circle class="a" cx="3.5" cy="18" r="1.7"/><circle class="a" cx="20.5" cy="18" r="1.7"/><circle class="a" cx="12" cy="6" r="1.7"/>',
    'point': '<circle class="a" cx="12" cy="12" r="3.2"/><path class="g" d="M12 3.5v4M12 16.5v4M3.5 12h4M16.5 12h4"/>',
    'rect': '<rect class="n" x="3.5" y="6.5" width="17" height="11" rx="1"/><circle class="a" cx="3.5" cy="6.5" r="1.7"/><circle class="a" cx="20.5" cy="17.5" r="1.7"/>',
    'circle': '<circle class="n" cx="12" cy="12" r="8"/><circle class="a" cx="12" cy="12" r="1.5"/><path class="a" d="M12 12l5.7-5.7"/>',
    'circle_d': '<circle class="n" cx="12" cy="12" r="8"/><path class="a" d="M4 12h16"/><circle class="a" cx="4" cy="12" r="1.5"/><circle class="a" cx="20" cy="12" r="1.5"/>',
    'ellipse': '<ellipse class="n" cx="12" cy="12" rx="9" ry="5.5"/><circle class="a" cx="12" cy="12" r="1.5"/><path class="a" d="M12 12h9"/>',
    'polygon': '<path class="n" d="M12 3.5 19.4 7.8v8.4L12 20.5 4.6 16.2V7.8z"/><circle class="a" cx="12" cy="12" r="1.5"/><path class="a" d="M12 12V3.5"/>',
    'arc3': '<path class="n" d="M4.5 17A8.5 8.5 0 0 1 19.5 17"/><circle class="a" cx="4.5" cy="17" r="1.7"/><circle class="a" cx="19.5" cy="17" r="1.7"/><circle class="a" cx="12" cy="8.5" r="1.7"/>',
    'box': '<path class="n" d="M12 3 20 7.5v9L12 21 4 16.5v-9z"/><path class="af" d="M12 3 20 7.5 12 12 4 7.5z"/><path class="n" d="M12 12v9"/>',
    'cylinder': '<ellipse class="af" cx="12" cy="6.5" rx="7" ry="3"/><path class="n" d="M5 6.5v11c0 1.7 3.1 3 7 3s7-1.3 7-3v-11"/>',
    'cone': '<path class="n" d="M12 3.5 5 17.5c0 1.7 3.1 3 7 3s7-1.3 7-3z"/><ellipse class="af" cx="12" cy="17.5" rx="7" ry="3" opacity=".9"/>',
    'pyramid': '<path class="n" d="M12 3.5 4 17l8 3.5 8-3.5z"/><path class="af" d="M12 3.5 4 17l8 3.5z"/><path class="n" d="M12 20.5V10"/>',
    'sphere': '<circle class="n" cx="12" cy="12" r="8.5"/><ellipse class="af" cx="12" cy="12" rx="8.5" ry="3"/>',
    'torus': '<ellipse class="n" cx="12" cy="12" rx="9" ry="6"/><path class="af" d="M7.2 12.6c1.2-2.6 3.1-3.1 4.8-3.1s3.6.5 4.8 3.1c-1.5 1.5-3 2-4.8 2s-3.3-.5-4.8-2z"/>',
    'tube': '<ellipse class="n" cx="12" cy="6.5" rx="7" ry="3"/><ellipse class="a" cx="12" cy="6.5" rx="3.2" ry="1.3"/><path class="n" d="M5 6.5v11c0 1.7 3.1 3 7 3s7-1.3 7-3v-11"/>',
    'extrude_path': '<path class="g" d="M3.5 19c3 0 3-10 8-10s5-4 9-4"/><path class="af" d="M4.5 19.5h7v-3h-7z"/><path class="n" d="M4.5 16.5V12l3-2.5h11v4l-3 2.5"/><path class="a" d="M11.5 19.5l4-3M11.5 16.5l4-3"/>',
    'extrude': '<path class="g" d="M4.5 19.5h11v-5h-11z"/><path class="af" d="M4.5 14.5V8l4-4h11v6.5l-4 4z"/><path class="n" d="M15.5 14.5V8M4.5 8h11M15.5 8l4-4"/>',
    'revolve': '<path class="g" d="M6 3v18"/><path class="a" d="M6 5c4 1 4 4 2.5 7S10 18 6 19"/><path class="n" d="M10 12a7 3.2 0 0 1 11 0M19.3 9.6 21 12l-2.8.6"/><ellipse class="af" cx="14" cy="12" rx="3.2" ry="7" opacity="0"/>',
    'loft': '<ellipse class="n" cx="12" cy="5.5" rx="6" ry="2"/><ellipse class="n" cx="12" cy="12" rx="3.2" ry="1.5"/><ellipse class="n" cx="12" cy="18.5" rx="7" ry="2.2"/><path class="a" d="M6 5.5c4 3 2.5 8 .6 7.6M18 5.5c-4 3-2.5 8-.6 7.6" opacity="0"/><path class="a" d="M6 5.5C9.5 8 9 10.5 8.8 12M18 5.5c-3.5 2.5-3 5-2.8 6.5M8.8 12C8 14.5 6 16.5 5 18.5M15.2 12c.8 2.5 2.8 4.5 3.8 6.5"/>',
    'sweep': '<path class="n" d="M3.5 19C8 19 8 8 13 8h7.5"/><ellipse class="af" cx="5" cy="17.2" rx="2" ry="3.4" transform="rotate(-20 5 17.2)"/><path class="a" d="M17 6 20.5 8 17 10"/>',
    'trim': '<path class="n" d="M3.5 12h17"/><path class="a" d="M12 3.5v8.5"/><path class="g" d="M12 12v8.5"/><circle class="a" cx="12" cy="12" r="1.5"/>',
    'join': '<path class="n" d="M3.5 18 10 9"/><path class="n" d="M14 15l6.5-9"/><path class="a" d="M10 9l4 6"/><circle class="a" cx="10" cy="9" r="1.7"/><circle class="a" cx="14" cy="15" r="1.7"/>',
    'explode': '<path class="a" d="M10 12h4"/><path class="n" d="M3.5 12h3.5M17 12h3.5M12 3.5v3.5M12 17v3.5M5.5 5.5 8 8M18.5 5.5 16 8M5.5 18.5 8 16M18.5 18.5 16 16"/>',
    'align': '<path class="g" d="M3.5 3.5v17"/><rect class="af" x="5.5" y="5" width="12" height="4" rx="1"/><rect class="n" x="5.5" y="10.5" width="7" height="4" rx="1"/><rect class="n" x="5.5" y="16" width="14" height="4" rx="1"/>',
    'make2d': '<path class="n" d="M12 2.5 18 6v7l-6 3.5L6 13V6z"/><path class="n" d="M12 9.5v7M6 6l6 3.5L18 6"/><path class="g" d="M3 19.5h18"/><path class="af" d="M6 19.5l0 0h12v2H6z" opacity="0"/><path class="a" d="M6 19.5h12"/>',
    'dim': '<path class="n" d="M3.5 7v10M20.5 7v10"/><path class="a" d="M3.5 12h17M6.5 9.8 3.5 12l3 2.2M17.5 9.8l3 2.2-3 2.2"/>',
    'dim_r': '<circle class="n" cx="12" cy="12" r="8.5"/><path class="a" d="M12 12l6-6M14 6h4v4"/><circle class="a" cx="12" cy="12" r="1.2"/>',
    'dim_a': '<path class="n" d="M4 19h16M4 19 17 6"/><path class="a" d="M11 19a7 7 0 0 0-2.1-5M9.2 14.6 8.4 17M9.2 14.6 11.5 15.3"/>',
    'note': '<path class="n" d="M4 19 11 11h9"/><path class="a" d="M4 19l3.2-.6M4 19l.8-3.2"/><path class="g" d="M13.5 6.5h6M13.5 9h4"/>',
    'area': '<path class="af" d="M5 18 4.5 7.5 13 5l6.5 6.5L16 19z"/><path class="n" d="M8 15l6-6M11 17.5l6-6" opacity=".6"/>',
    'light_point': '<circle class="af" cx="12" cy="12" r="3.8"/><path class="n" d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1"/>',
    'light_spot': '<path class="af" d="M9.5 3.5h5l-1.2 4h-2.6z"/><path class="n" d="M10.7 7.5 5.5 20.5h13l-5.2-13"/><path class="a" d="M8 20.5c1.2 1 2.6 1.4 4 1.4s2.8-.4 4-1.4" opacity="0"/>',
    'light_sun': '<circle class="af" cx="12" cy="12" r="4.2"/><path class="n" d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2 2M16.7 16.7l2 2M18.7 5.3l-2 2M7.3 16.7l-2 2"/>',
    'light_area': '<rect class="af" x="4.5" y="4.5" width="15" height="6.5" rx="1.2"/><path class="n" d="M7 14.5v5M12 14.5v6M17 14.5v5"/>',
    'camera': '<rect class="n" x="3.5" y="7.5" width="12.5" height="10" rx="2"/><path class="af" d="M16 11.5l4.5-2.5v8L16 14.5z"/>',
    'camera_t': '<rect class="n" x="3.5" y="5.5" width="12.5" height="9" rx="2"/><path class="af" d="M16 9l4.5-2.2v7L16 12z"/><circle class="a" cx="12" cy="19.5" r="1.7"/><path class="g" d="M10 15v2.5"/>',
    'ellipse_d': '<ellipse class="n" cx="12" cy="12" rx="9" ry="5.5"/><path class="g" d="M3 12h18"/><circle class="a" cx="3" cy="12" r="1.6"/><circle class="a" cx="21" cy="12" r="1.6"/>',
    'ellipse_f': '<ellipse class="n" cx="12" cy="12" rx="9" ry="5.5"/><circle class="a" cx="7.5" cy="12" r="1.6"/><circle class="a" cx="16.5" cy="12" r="1.6"/>',
    'ellipse_k': '<rect class="g" x="3" y="6.5" width="18" height="11"/><ellipse class="n" cx="12" cy="12" rx="9" ry="5.5"/><circle class="a" cx="3" cy="6.5" r="1.6"/><circle class="a" cx="21" cy="17.5" r="1.6"/>',
    'poly_k': '<path class="n" d="M12 3.5 19.4 7.75v8.5L12 20.5 4.6 16.25v-8.5z"/><circle class="g" cx="12" cy="12" r="7.36"/><circle class="a" cx="12" cy="12" r="1.4"/>',
    'poly_a': '<path class="af" d="M12 3.5 19.4 7.75v8.5L12 20.5 4.6 16.25v-8.5z"/>',
    'poly_e': '<path class="n" d="M12 3.5 19.4 7.75v8.5L12 20.5 4.6 16.25v-8.5z"/><path class="a" d="M12 3.5 19.4 7.75"/><circle class="a" cx="12" cy="3.5" r="1.6"/><circle class="a" cx="19.4" cy="7.75" r="1.6"/>',
    'arc': '<path class="n" d="M4.5 18A7.5 7.5 0 0 1 19.5 18"/><path class="g" d="M4.5 18H12"/><circle class="a" cx="12" cy="18" r="1.6"/><circle class="a" cx="4.5" cy="18" r="1.6"/><circle class="a" cx="19.5" cy="18" r="1.6"/>',
    'tcone': '<path class="n" d="M7.8 6 4.5 17.5M16.2 6l3.3 11.5"/><ellipse class="n" cx="12" cy="6" rx="4.2" ry="1.7"/><ellipse class="af" cx="12" cy="17.5" rx="7.5" ry="3"/>',
    'tpyramid': '<path class="af" d="M4 17l8 3.5 8-3.5-8-3.5z"/><path class="n" d="M9.5 8.5 12 7.3l2.5 1.2L12 9.7z"/><path class="n" d="M9.5 8.5 4 17M14.5 8.5 20 17M12 9.7v3.8M12 20.5V14"/>',
    'ellipsoid': '<ellipse class="n" cx="12" cy="12" rx="9.5" ry="6.5"/><ellipse class="af" cx="12" cy="12" rx="9.5" ry="2.6"/>',
    'tsphere': '<path class="n" d="M6.2 7.5a8.5 8.5 0 1 0 11.6 0"/><ellipse class="af" cx="12" cy="7.5" rx="5.8" ry="2.1"/>',
    'offset_srf': '<path class="n" d="M3 19l3-7h12l-3 7z"/><path class="af" d="M3 10 6 3h12l-3 7z"/><path class="g" d="M12 17v-6"/>',
}
ICON_SVG["poly_s"] = '<path class="n" d="%s"/><circle class="a" cx="12" cy="12.5" r="1.4"/>' % _svg_star()
ICON_SVG['dim_chain'] = '<path class="n" d="M3 7v12M11 7v12M21 7v12"/><path class="a" d="M3.60 10.00L10.40 10.00"/><path class="af" d="M3.60 10.00L5.80 9.08L5.80 10.92zM10.40 10.00L8.20 10.92L8.20 9.08z"/><path class="a" d="M11.60 10.00L20.40 10.00"/><path class="af" d="M11.60 10.00L13.80 9.08L13.80 10.92zM20.40 10.00L18.20 10.92L18.20 9.08z"/>'
ICON_SVG['dim_ord'] = '<path class="g" d="M2.5 20.5h19M4.5 18.5v4"/><circle class="n" cx="4.5" cy="20.5" r="1.3"/><path class="a" d="M11 18.5V12l2-2V5M18 18.5V5"/><circle class="n" cx="11" cy="20.5" r="1"/><circle class="n" cx="18" cy="20.5" r="1"/><path class="af" d="M11.5 3.2h3v1.4h-3zM16.5 3.2h3v1.4h-3z"/>'
ICON_SVG['dim_arc'] = '<path class="n" d="M18.93 16.00L18.55 15.41L18.13 14.86L17.66 14.34L17.14 13.87L16.59 13.45L16.00 13.07L15.38 12.75L14.74 12.48L14.07 12.27L13.39 12.12L12.70 12.03L12.00 12.00L11.30 12.03L10.61 12.12L9.93 12.27L9.26 12.48L8.62 12.75L8.00 13.07L7.41 13.45L6.86 13.87L6.34 14.34L5.87 14.86L5.45 15.41L5.07 16.00"/><path class="n" d="M19.62 15.60L23.69 13.25M4.38 15.60L0.31 13.25"/><path class="a" d="M22.83 13.75L22.24 12.83L21.58 11.97L20.84 11.16L20.03 10.42L19.17 9.76L18.25 9.17L17.28 8.67L16.28 8.25L15.24 7.93L14.17 7.69L13.09 7.55L12.00 7.50L10.91 7.55L9.83 7.69L8.76 7.93L7.72 8.25L6.72 8.67L5.75 9.17L4.83 9.76L3.97 10.42L3.16 11.16L2.42 11.97L1.76 12.83L1.17 13.75"/><path class="af" d="M22.83 13.75L21.04 12.51L22.46 11.61zM1.17 13.75L1.54 11.61L2.96 12.51z"/>'
ICON_SVG['dim_edit'] = '<path class="n" d="M3 13v8M21 13v8"/><path class="a" d="M3.60 16.00L20.40 16.00"/><path class="af" d="M3.60 16.00L5.80 15.08L5.80 16.92zM20.40 16.00L18.20 16.92L18.20 15.08z"/><path class="n" d="M12 3v9"/><path class="n" d="M9.5 5.5 12 3l2.5 2.5M9.5 9.5 12 12l2.5-2.5"/>'
ICON_SVG['fillet_srf'] = '<path class="g" d="M4 4v16h16" stroke-dasharray="1.6 1.6"/><path class="n" d="M4 3v8M13 20h8"/><path class="a" d="M4 11a9 9 0 0 0 9 9"/><circle class="n" cx="4" cy="11" r="1.4"/><circle class="n" cx="13" cy="20" r="1.4"/>'
ICON_SVG['chamfer_srf'] = '<path class="g" d="M4 4v16h16" stroke-dasharray="1.6 1.6"/><path class="n" d="M4 3v8M13 20h8"/><path class="a" d="M4 11l9 9"/><circle class="n" cx="4" cy="11" r="1.4"/><circle class="n" cx="13" cy="20" r="1.4"/>'
ICON_SVG['extend_srf'] = '<rect class="af" x="3" y="6" width="11" height="12" rx="1"/><path class="n" d="M14 6v12"/><path class="g" d="M14 6h7v12h-7" stroke-dasharray="1.6 1.6"/><path class="a" d="M15.5 12H21M18.6 9.6 21 12l-2.4 2.4"/>'
ICON_SVG['split_iso'] = '<path class="g" d="M3 9.7h8M13 9.7h8M3 14.3h8M13 14.3h8M7 5v14M17 5v14"/><path class="n" d="M11 5H3v14h8M13 5h8v14h-8"/><path class="a" d="M12 2.5v19"/>'
ICON_SVG['network_srf'] = '<path class="n" d="M4 6c5-2 11-2 16 0M4 12c5-1.6 11-1.6 16 0M4 18c5 2 11 2 16 0"/><path class="a" d="M4 6v12M12 4.5c.6 5 .6 10 0 15M20 6v12"/>'
ICON_SVG['blend_crv'] = '<path class="n" d="M2.5 18.5h6M15.5 5.5h6"/><path class="a" d="M8.5 18.5c5 0 2-13 7-13"/><circle class="n" cx="8.5" cy="18.5" r="1.3"/><circle class="n" cx="15.5" cy="5.5" r="1.3"/>'
ICON_SVG['match_crv'] = '<path class="n" d="M14 20c4 0 6.5-3 6.5-8V4"/><path class="g" d="M3 15c3-5 6-6 9-4" stroke-dasharray="1.6 1.6"/><path class="a" d="M3 15c3-5 6-6 9-3s1.2 8 2 8"/><circle class="n" cx="14" cy="20" r="1.4"/>'
ICON_SVG['rebuild_crv'] = '<path class="g" d="M3 17 7 6l5 10 4-11 5 12" stroke-dasharray="1.6 1.6"/><path class="a" d="M3 17c2-7 3-9 5-7s3 5 5 3 3-7 5-6 2 6 3 10"/><circle class="n" cx="3" cy="17" r="1.2"/><circle class="n" cx="7" cy="6" r="1.2"/><circle class="n" cx="12" cy="16" r="1.2"/><circle class="n" cx="16" cy="5" r="1.2"/><circle class="n" cx="21" cy="17" r="1.2"/>'
ICON_SVG['simplify_crv'] = '<path class="g" d="M3 18l3-2.5 3-1 3-3.5 3-1.5 3-3.5 3-1" stroke-dasharray="1.4 1.4"/><path class="a" d="M3 18l9-7 9-6"/><circle class="n" cx="3" cy="18" r="1.3"/><circle class="n" cx="12" cy="11" r="1.3"/><circle class="n" cx="21" cy="5" r="1.3"/>'
ICON_SVG['change_degree'] = '<path class="g" d="M3 19 8 6l8 2 5 11" stroke-dasharray="1.6 1.6"/><path class="a" d="M3 19C5 11 7 8 11 8s8 4 10 11"/><path class="n" d="M17 2.5v5M14.8 4.6 17 2.5l2.2 2.1"/>'
ICON_SVG['insert_point'] = '<path class="n" d="M2.5 17c4-9 8-11 12-9s5 7 7 9"/><circle class="a" cx="11" cy="8.2" r="2"/><path class="a" d="M18 2.5v5M15.5 5h5"/>'
ICON_SVG['remove_point'] = '<path class="n" d="M2.5 17c4-9 8-11 12-9s5 7 7 9"/><circle class="a" cx="11" cy="8.2" r="2"/><path class="a" d="M15.5 5h5"/>'
ICON_SVG['block'] = '<rect class="g" x="3" y="3" width="18" height="18" rx="1.5" stroke-dasharray="1.6 1.6"/><rect class="af" x="6.5" y="9" width="7" height="8.5" rx="1"/><circle class="n" cx="15.5" cy="9.5" r="3"/><path class="a" d="M3 21l3.5-3.5"/><circle class="a" cx="3" cy="21" r="1.6"/>'
ICON_SVG['block_insert'] = '<path class="g" d="M12 3 20 7.5v9L12 21l-8-4.5v-9z" stroke-dasharray="1.6 1.6"/><path class="af" d="M12 7.5 16.5 10v5L12 17.5 7.5 15v-5z"/><path class="a" d="M12 1v5M9.8 3.8 12 6l2.2-2.2"/>'
ICON_SVG['untrim'] = '<path class="g" d="M3 4h18v16H3z" stroke-dasharray="1.6 1.6"/><path class="n" d="M3 4h11c-1 4 3 6 2 9s-6 3-7 7H3z"/><path class="a" d="M14 4h7v16H9c1-4 6-4 7-7s-3-5-2-9z"/>'
ICON_SVG['untrim_holes'] = '<rect class="n" x="3" y="4" width="18" height="16" rx="1"/><circle class="af" cx="12" cy="12" r="4"/><circle class="a" cx="12" cy="12" r="4"/>'
ICON_SVG["hatch"] = '<path class="a" d="M19.71 5.00L20.00 5.29M16.03 5.00L20.00 8.97M12.35 5.00L20.00 12.65M8.68 5.00L13.68 10.00M18.00 14.32L20.00 16.32M5.00 5.00L11.51 11.51M16.49 16.49L19.00 19.00M4.00 7.68L11.16 14.84M13.16 16.84L15.32 19.00M4.00 11.35L11.65 19.00M4.00 15.03L7.97 19.00M4.00 18.71L4.29 19.00"/><rect class="n" x="4" y="5" width="16" height="14" rx="1"/><circle class="n" cx="14.5" cy="13.5" r="3.6"/>'
ICON_SVG["hatch_region"] = '<path class="a" d="M19.71 5.00L20.00 5.29M16.03 5.00L20.00 8.97M12.35 5.00L19.35 12.00M8.68 5.00L15.68 12.00M5.00 5.00L12.00 12.00M4.00 7.68L11.00 14.68M4.00 11.35L11.00 18.35M4.00 15.03L7.97 19.00M4.00 18.71L4.29 19.00"/><path class="n" d="M4 5h16v7h-9v7H4z"/><path class="n" d="M14 13.5l6 3.6-2.6.7-.8 2.7z"/>'

# Icônes SubD (style « forme lisse dans sa cage » : cage grise pointillée, points de contrôle, forme lisse colorée)
ICON_SVG.update({
    'subd_box': '<path class="g" d="M12.00 2.60 L20.60 7.40 L20.60 16.60 L12.00 21.40 L3.40 16.60 L3.40 7.40z"/><path class="g" d="M3.40 7.40 L12.00 12.20 L20.60 7.40 M12.00 12.20 L12.00 21.40"/><path class="n" d="M13.92 5.55 L16.96 7.25 C18.02 7.84 18.88 9.31 18.88 10.52 L18.88 13.48 C18.88 14.69 18.02 16.16 16.96 16.75 L13.92 18.45 C12.86 19.04 11.14 19.04 10.08 18.45 L7.04 16.75 C5.98 16.16 5.12 14.69 5.12 13.48 L5.12 10.52 C5.12 9.31 5.98 7.84 7.04 7.25 L10.08 5.55 C11.14 4.96 12.86 4.96 13.92 5.55z"/><path class="af" d="M13.40 5.26 L17.48 7.54 C18.25 7.97 18.25 8.67 17.48 9.10 L13.40 11.38 C12.63 11.81 11.37 11.81 10.60 11.38 L6.52 9.10 C5.75 8.67 5.75 7.97 6.52 7.54 L10.60 5.26 C11.37 4.83 12.63 4.83 13.40 5.26z"/><path class="n" d="M12.00 13.36 V17.92"/><circle class="af" cx="12.00" cy="2.60" r="0.50"/><circle class="af" cx="20.60" cy="7.40" r="0.50"/><circle class="af" cx="20.60" cy="16.60" r="0.50"/><circle class="af" cx="12.00" cy="21.40" r="0.50"/><circle class="af" cx="3.40" cy="16.60" r="0.50"/><circle class="af" cx="3.40" cy="7.40" r="0.50"/>',
    'subd_sphere': '<path class="g" d="M4.00 4.00 L20.00 4.00 L20.00 20.00 L4.00 20.00z"/><circle class="n" cx="12" cy="12" r="7.6"/><path class="af" d="M7.4 7.4 C10.2 6.4 13.8 6.4 16.6 7.4 C17.6 10.2 17.6 13.8 16.6 16.6 C13.8 17.6 10.2 17.6 7.4 16.6 C6.4 13.8 6.4 10.2 7.4 7.4z" opacity=".75"/><circle class="af" cx="4.00" cy="4.00" r="0.50"/><circle class="af" cx="20.00" cy="4.00" r="0.50"/><circle class="af" cx="20.00" cy="20.00" r="0.50"/><circle class="af" cx="4.00" cy="20.00" r="0.50"/>',
    'subd_cylinder': '<path class="g" d="M4.00 3.00 L20.00 3.00 L20.00 21.00 L4.00 21.00z"/><ellipse class="af" cx="12" cy="6.8" rx="6.2" ry="2.4"/><path class="n" d="M5.8 6.8 V16 C5.8 18.6 8.6 19.4 12 19.4 C15.4 19.4 18.2 18.6 18.2 16 V6.8"/><circle class="af" cx="4.00" cy="3.00" r="0.50"/><circle class="af" cx="20.00" cy="3.00" r="0.50"/><circle class="af" cx="20.00" cy="21.00" r="0.50"/><circle class="af" cx="4.00" cy="21.00" r="0.50"/>',
    'subd_cone': '<path class="g" d="M12.00 2.50 L20.50 20.50 L3.50 20.50z"/><path class="n" d="M10.9 6.2 C11.5 5.2 12.5 5.2 13.1 6.2 L18.2 16.4 C18.2 18.4 15.4 19.2 12 19.2 C8.6 19.2 5.8 18.4 5.8 16.4z"/><ellipse class="af" cx="12" cy="16.4" rx="6.2" ry="2.2"/><circle class="af" cx="12.00" cy="2.50" r="0.50"/><circle class="af" cx="20.50" cy="20.50" r="0.50"/><circle class="af" cx="3.50" cy="20.50" r="0.50"/>',
    'subd_torus': '<path class="g" d="M2.50 6.00 L21.50 6.00 L21.50 18.00 L2.50 18.00z"/><ellipse class="n" cx="12" cy="12" rx="8.2" ry="4.8"/><path class="af" d="M7.6 12.4c1.1-2 2.8-2.5 4.4-2.5s3.3.5 4.4 2.5c-1.3 1.2-2.7 1.6-4.4 1.6s-3.1-.4-4.4-1.6z"/><circle class="af" cx="2.50" cy="6.00" r="0.50"/><circle class="af" cx="21.50" cy="6.00" r="0.50"/><circle class="af" cx="21.50" cy="18.00" r="0.50"/><circle class="af" cx="2.50" cy="18.00" r="0.50"/>',
    'subd_plane': '<path class="g" d="M7.00 5.00 L21.00 5.00 L17.00 19.00 L3.00 19.00z"/><path class="g" d="M14 5 L10 19 M5 12 L19 12"/><path class="af" d="M11.20 7.00 L16.20 7.00 C17.63 7.00 18.44 8.11 18.01 9.48 L16.39 14.52 C15.96 15.89 14.43 17.00 13.00 17.00 L8.00 17.00 C6.57 17.00 5.76 15.89 6.19 14.52 L7.81 9.48 C8.24 8.11 9.77 7.00 11.20 7.00z"/><circle class="af" cx="7.00" cy="5.00" r="0.50"/><circle class="af" cx="21.00" cy="5.00" r="0.50"/><circle class="af" cx="17.00" cy="19.00" r="0.50"/><circle class="af" cx="3.00" cy="19.00" r="0.50"/>',
    'subdc_to_subd': '<path class="n" d="M2.5 8.5h7v7h-7z"/><path class="n" d="M10.6 12H13M11.6 10.6 13 12l-1.4 1.4"/><path class="g" d="M14.00 8.25 L21.50 8.25 L21.50 15.75 L14.00 15.75z"/><path class="af" d="M17.20 9.60 L18.30 9.60 C19.29 9.60 20.10 10.41 20.10 11.40 L20.10 12.60 C20.10 13.59 19.29 14.40 18.30 14.40 L17.20 14.40 C16.21 14.40 15.40 13.59 15.40 12.60 L15.40 11.40 C15.40 10.41 16.21 9.60 17.20 9.60z"/><circle class="af" cx="14.00" cy="8.25" r="0.50"/><circle class="af" cx="21.50" cy="8.25" r="0.50"/><circle class="af" cx="21.50" cy="15.75" r="0.50"/><circle class="af" cx="14.00" cy="15.75" r="0.50"/>',
    'subdc_to_mesh': '<path class="g" d="M2.50 8.25 L10.00 8.25 L10.00 15.75 L2.50 15.75z"/><path class="n" d="M5.70 9.60 L6.80 9.60 C7.79 9.60 8.60 10.41 8.60 11.40 L8.60 12.60 C8.60 13.59 7.79 14.40 6.80 14.40 L5.70 14.40 C4.71 14.40 3.90 13.59 3.90 12.60 L3.90 11.40 C3.90 10.41 4.71 9.60 5.70 9.60z"/><circle class="af" cx="2.50" cy="8.25" r="0.50"/><circle class="af" cx="10.00" cy="8.25" r="0.50"/><circle class="af" cx="10.00" cy="15.75" r="0.50"/><circle class="af" cx="2.50" cy="15.75" r="0.50"/><path class="n" d="M11 12H13.4M12 10.6 13.4 12 12 13.4"/><path class="af" d="M14.5 8.5h7v7h-7z"/>',
    'subdc_display': '<path class="g" d="M4.00 4.00 L20.00 4.00 L20.00 20.00 L4.00 20.00z"/><path class="n" d="M10.40 6.20 L13.60 6.20 C15.91 6.20 17.80 8.09 17.80 10.40 L17.80 13.60 C17.80 15.91 15.91 17.80 13.60 17.80 L10.40 17.80 C8.09 17.80 6.20 15.91 6.20 13.60 L6.20 10.40 C6.20 8.09 8.09 6.20 10.40 6.20z"/><path class="af" d="M12 6.2 C14.8 6.2 17.8 7 17.8 12 C17.8 17 14.8 17.8 12 17.8z" opacity=".8"/><circle class="af" cx="4.00" cy="4.00" r="0.50"/><circle class="af" cx="20.00" cy="4.00" r="0.50"/><circle class="af" cx="20.00" cy="20.00" r="0.50"/><circle class="af" cx="4.00" cy="20.00" r="0.50"/>',
    'subdc_loft': '<path class="af" d="M5.2 5.4 C7.8 8.8 8.1 10.8 8.1 12 C8.1 13.2 7.8 15.2 5.2 18.6 H18.8 C16.2 15.2 15.9 13.2 15.9 12 C15.9 10.8 16.2 8.8 18.8 5.4z"/><ellipse class="n" cx="12" cy="5" rx="7" ry="1.9"/><ellipse class="n" cx="12" cy="12" rx="4" ry="1.2"/><ellipse class="n" cx="12" cy="19" rx="7" ry="1.9"/><circle class="af" cx="5.00" cy="5.00" r="0.50"/><circle class="af" cx="19.00" cy="5.00" r="0.50"/><circle class="af" cx="8.00" cy="12.00" r="0.50"/><circle class="af" cx="16.00" cy="12.00" r="0.50"/><circle class="af" cx="5.00" cy="19.00" r="0.50"/><circle class="af" cx="19.00" cy="19.00" r="0.50"/>',
    'subdc_sweep1': '<path class="af" d="M2.8 16.2 C6.6 9.4 12 5.6 18.4 3.4 L20.6 7.2 C15 9 10.2 12.4 6.6 18.6z"/><path class="g" d="M4.7 17.4 C8.4 11 13.4 7.4 19.5 5.3"/><ellipse class="n" cx="4.7" cy="17.4" rx="2.4" ry="1.4" transform="rotate(-55 4.7 17.4)"/><ellipse class="n" cx="19.5" cy="5.3" rx="2.4" ry="1.4" transform="rotate(-70 19.5 5.3)"/><circle class="af" cx="2.80" cy="16.20" r="0.50"/><circle class="af" cx="6.60" cy="18.60" r="0.50"/><circle class="af" cx="18.40" cy="3.40" r="0.50"/><circle class="af" cx="20.60" cy="7.20" r="0.50"/>',
    'subdc_sweep2': '<path class="af" d="M3 7.5 C9 4.5 15 4.5 21 7.5 V17.5 C15 14.5 9 14.5 3 17.5z"/><path class="n" d="M3 7.5 C9 4.5 15 4.5 21 7.5"/><path class="n" d="M3 17.5 C9 14.5 15 14.5 21 17.5"/><path class="g" d="M12 5.25 V15.25"/><path class="n" d="M3 7.5 V17.5"/><circle class="af" cx="3.00" cy="7.50" r="0.50"/><circle class="af" cx="21.00" cy="7.50" r="0.50"/><circle class="af" cx="3.00" cy="17.50" r="0.50"/><circle class="af" cx="21.00" cy="17.50" r="0.50"/><circle class="af" cx="12.00" cy="5.25" r="0.50"/><circle class="af" cx="12.00" cy="15.25" r="0.50"/>',
    'subdc_revolve': '<path class="af" d="M7 3.5 C13.6 4.8 11.4 10 13 12 C14.6 14 16.4 18.4 7 20.5z"/><path class="g" d="M7 1.8 V22.2"/><path class="n" d="M7 3.5 C13.6 4.8 11.4 10 13 12 C14.6 14 16.4 18.4 7 20.5"/><path class="a" d="M16.4 6.6 C20.6 8.2 21.6 11.4 20 14.4 M18.4 14.2 l1.6 .3 .5-1.6"/><circle class="af" cx="7.00" cy="3.50" r="0.50"/><circle class="af" cx="13.00" cy="12.00" r="0.50"/><circle class="af" cx="7.00" cy="20.50" r="0.50"/>',
})

# Commandes Rhino ajoutées en 2.96.124 (Pipe, Intersect, Section, Contour, ExtractSrf, DupBorder, DupEdge, MergeAllFaces,
# UnrollSrf, RebuildSrf, Orient)
ICON_SVG.update({
    'pipe': '<path class="g" d="M4 18C4 12 8 8 12 8C16 8 20 6 20 6" stroke-dasharray="1.6 1.6"/><path class="a" d="M2 17.1C2 11 6 7 12 7C17 7 22 5 22 5M6 18.9C6 13 10 9 14 9C18 9 22 7 22 7M22 5V7"/><circle class="af" cx="4" cy="18" r="2.4"/><circle class="n" cx="4" cy="18" r="2.4"/>',
    'intersect': '<rect class="n" x="3" y="7" width="12" height="10" rx="1"/><rect class="n" x="9" y="4" width="12" height="10" rx="1"/><rect class="af" x="9" y="7" width="6" height="7" rx="0.5"/><rect class="a" x="9" y="7" width="6" height="7" rx="0.5"/>',
    'section': '<path class="n" d="M4 17.5V6.5L12 2.5L20 6.5V17.5L12 21.5Z"/><path class="g" d="M4 6.5L12 10.5L20 6.5M12 10.5V21.5" stroke-dasharray="1.4 1.4"/><path class="af" d="M2 12.5L22 8.5V10.7L2 14.7Z"/><path class="a" d="M2 12.5L22 8.5V10.7L2 14.7Z"/>',
    'contour': '<path class="n" d="M5 20V10C5 6 10 4 12 4C14 4 19 6 19 10V20Z"/><path class="g" d="M3 9H21M3 13H21M3 17H21" stroke-dasharray="1.4 1.4"/><path class="a" d="M6 9C9 7.6 15 7.6 18 9M5.5 13C9 11.4 15 11.4 18.5 13M5 17C9 15.6 15 15.6 19 17"/>',
    'extract_srf': '<path class="n" d="M4 16V8L12 4L20 8V16L12 20Z"/><path class="g" d="M4 8L12 12L20 8M12 12V20" stroke-dasharray="1.4 1.4"/><path class="af" d="M4 8L12 4L20 8L12 12Z"/><path class="a" d="M4 8L12 4L20 8L12 12Z"/><path class="a" d="M12 3.4V1.8M3.6 7.6L2.4 6.4M20.4 7.6L21.6 6.4"/>',
    'dup_border': '<path class="af" d="M4 18C6 14 8 10 12 8C16 6 19 8 20 12L18 20Z" opacity=".55"/><path class="a" d="M4 18C6 14 8 10 12 8C16 6 19 8 20 12L18 20Z"/><circle class="a" cx="12" cy="8" r="1.5"/><circle class="a" cx="4" cy="18" r="1.5"/>',
    'dup_edge': '<path class="n" d="M4 17V9L12 5L20 9V17L12 21Z"/><path class="g" d="M4 9L12 13L20 9M12 13V21" stroke-dasharray="1.4 1.4"/><path class="a" d="M12 5L20 9"/><circle class="a" cx="12" cy="5" r="1.6"/><circle class="a" cx="20" cy="9" r="1.6"/>',
    'merge_faces': '<path class="g" d="M12 4V20M3 12H21" stroke-dasharray="1.4 1.4"/><rect class="af" x="3" y="4" width="18" height="16" rx="1.5"/><rect class="a" x="3" y="4" width="18" height="16" rx="1.5"/>',
    'unroll': '<ellipse class="n" cx="8" cy="6" rx="4" ry="1.8"/><path class="n" d="M4 6V16C4 18.4 12 18.4 12 16V6"/><path class="n" d="M14 11H16.6M15.3 9.6L16.7 11L15.3 12.4"/><rect class="af" x="17.6" y="5" width="4.9" height="12" rx="0.8"/><rect class="a" x="17.6" y="5" width="4.9" height="12" rx="0.8"/>',
    'rebuild_srf': '<path class="g" d="M3 17L7 7L12 11L17 5L21 14" stroke-dasharray="1.4 1.4"/><path class="a" d="M3 17C5 12 8 9 12 9C16 9 19 11 21 14"/><circle class="a" cx="3" cy="17" r="1.4"/><circle class="a" cx="9" cy="10" r="1.4"/><circle class="a" cx="15" cy="10" r="1.4"/><circle class="a" cx="21" cy="14" r="1.4"/>',
    'orient': '<rect class="n" x="3" y="12" width="7" height="7" rx="1"/><path class="g" d="M6.5 12V8M3 15.5H1" stroke-dasharray="1.4 1.4"/><path class="a" d="M14 11L18 6M14 11L20 12"/><g transform="rotate(-30 17 15)"><rect class="af" x="13.5" y="13" width="7" height="7" rx="1"/></g><path class="n" d="M11 15L13 14M12.3 12.5L13.8 14.2L11.9 15"/>',
})

# Mise en page (2.96.125) : la feuille avec son cartouche, et un détail (cadre + vue du modèle)
ICON_SVG.update({
    'layout': '<rect class="n" x="3" y="3.5" width="18" height="17" rx="1.2"/><rect class="af" x="5.5" y="6" width="7" height="6" rx="0.6"/>'
              '<path class="g" d="M14.5 7h4M14.5 9.5h4M5.5 14.5h7"/><path class="a" d="M13.5 15.5h7.5M13.5 15.5v5M13.5 18h7.5"/>',
    'detail': '<rect class="a" x="3" y="4.5" width="18" height="15" rx="1"/><path class="n" d="M12 7.5 16.5 10v5L12 17.5 7.5 15v-5z"/>'
              '<path class="n" d="M7.5 10 12 12.5 16.5 10M12 12.5v5"/><path class="af" d="M12 7.5 16.5 10 12 12.5 7.5 10z"/>',
})

ICON_ALIAS = {"scale_2d": "scale2d", "scale_1d": "scale1d", "scale_size": "scalesize", "ellipse_c": "ellipse", "poly_c": "polygon", "camera_target": "camera_t"}


def svg_icon_bytes(kind):
    """Données .dat de l'icône `kind` d'après ICON_SVG, ou None si elle n'a pas de dessin SVG."""
    key = ICON_ALIAS.get(kind, kind)
    if key in ("bool_u", "bool_d", "bool_i", "bool_s"):
        shapes = _svg_bool(key)
    elif key in ICON_SVG:
        shapes = _svg_shapes(ICON_SVG[key])
    else:
        return None
    g = _IconPen()
    _svg_to_pen(g, shapes)
    coords, colors = bytearray(), bytearray()
    for a, b, c, col in g.tris:
        for x, y in (a, b, c):
            coords += bytes((x, y))
            colors += bytes(col)
    return b"VCO\x00" + bytes((0xFF, 0xFF, 0x00, 0x00)) + bytes(coords) + bytes(colors)


def _icon_bytes(kind="move"):
    """Icônes de la barre d'outils (format .dat de Blender : triangles colorés sur grille 256).
    Style CAO : trait clair, gris pour les constructions, orange pour ce qui est créé / les points cliqués."""
    data = svg_icon_bytes(kind)
    if data is not None:
        return data
    g = _IconPen()
    LINE, DIM, ACC, FILLA = ICON_LINE, ICON_DIM, ICON_ACC, ICON_FILL
    k = kind
    if k=="move":
        g.poly([(30,90),(90,90),(90,150),(30,150)],None,DIM,7)
        g.arrow((100,120),(150,120),LINE)
        g.poly([(160,90),(226,90),(226,156),(160,156)],FILLA,ACC,9)
    elif k=="copy":
        g.poly([(30,60),(150,60),(150,180),(30,180)],None,LINE,9)
        g.poly([(100,76),(226,76),(226,200),(100,200)],FILLA,ACC,9)
    elif k=="rotate":
        g.poly([(52,52),(168,52),(168,168),(52,168)],None,DIM,7)
        g.poly([(128,36),(214,122),(128,208),(42,122)],FILLA,ACC,9)
        g.ell((128,122),52,52,LINE,8,a0=200,a1=340)
    elif k=="scale":
        g.poly([(34,34),(222,34),(222,222),(34,222)],None,DIM,7)
        g.poly([(34,34),(124,34),(124,124),(34,124)],FILLA,ACC,9)
        g.arrow((130,130),(206,206),LINE,8,24)
    elif k=="scale_2d":
        g.poly([(34,34),(222,34),(222,222),(34,222)],None,DIM,7)
        g.poly([(34,34),(124,34),(124,124),(34,124)],FILLA,ACC,9)
        g.arrow((130,80),(206,80),LINE,8,24); g.arrow((80,130),(80,206),LINE,8,24)
    elif k=="scale_1d":
        g.poly([(34,60),(222,60),(222,196),(34,196)],None,DIM,7)
        g.poly([(34,60),(124,60),(124,196),(34,196)],FILLA,ACC,9)
        g.arrow((130,128),(210,128),LINE,8,24)
    elif k=="scale_size":
        g.poly([(60,60),(196,60),(196,196),(60,196)],FILLA,ACC,9)
        g.arrow((128,128),(196,196),LINE,8,24)
        g.poly([(34,34),(34,222)],None,LINE,7); g.poly([(222,34),(222,222)],None,LINE,7)
    elif k=="plane":
        g.poly([(40,56),(216,56),(216,200),(40,200)],(255,168,38,200),ACC,9)   # rectangle plein, vu de face
        g.dot((40,56),LINE,16); g.dot((216,200),LINE,16)
    elif k=="curve_cp":
        cp=[(34,60),(80,200),(170,200),(222,80)]
        g.dash(cp[0],cp[1],DIM,6,4); g.dash(cp[1],cp[2],DIM,6,4); g.dash(cp[2],cp[3],DIM,6,4)
        curve=[]
        for i in range(25):
            t=i/24; a=(1-t)**3; b=3*t*(1-t)**2; c=3*t*t*(1-t); e=t**3
            curve.append((a*cp[0][0]+b*cp[1][0]+c*cp[2][0]+e*cp[3][0], a*cp[0][1]+b*cp[1][1]+c*cp[2][1]+e*cp[3][1]))
        g.line(curve,ACC,10)
        for q in cp: g.dot(q,LINE,15)
    elif k=="polyline":
        pts=[(36,60),(92,192),(156,100),(220,198)]
        g.line(pts,ACC,10)
        for p in pts: g.dot(p,LINE,16)
    elif k=="rect":
        g.poly([(36,64),(220,64),(220,192),(36,192)],None,LINE,10)
        g.dot((36,64),ACC,20); g.dot((220,192),ACC,20)
    elif k=="circle":
        g.ell((128,128),90,90,LINE,10); g.dash((128,128),(218,128),ACC,8,6); g.dot((128,128),ACC,18)
    elif k=="circle_d":
        g.ell((128,128),90,90,LINE,10); g.dot((38,128),ACC,18); g.dot((218,128),ACC,18); g.dash((38,128),(218,128),DIM,7,9)
    elif k=="ellipse_c":
        g.ell((128,128),108,66,LINE,10); g.dot((128,128),ACC,18); g.dash((128,128),(236,128),ACC,8,6)
    elif k=="ellipse_d":
        g.ell((128,128),108,66,LINE,10); g.dot((20,128),ACC,18); g.dot((236,128),ACC,18); g.dash((20,128),(236,128),DIM,7,10)
    elif k=="ellipse_f":
        g.ell((128,128),108,66,LINE,10); g.dot((72,128),ACC,18); g.dot((184,128),ACC,18)
    elif k=="ellipse_k":
        g.poly([(20,62),(236,62),(236,194),(20,194)],None,DIM,6)
        g.ell((128,128),108,66,LINE,10); g.dot((20,62),ACC,18); g.dot((236,194),ACC,18)
    elif k=="arc":
        g.ell((128,70),96,96,LINE,10,a0=25,a1=155); g.dot((128,70),ACC,18)
        g.dash((128,70),(215,115),DIM,7,5)
    elif k=="arc3":
        g.ell((128,70),96,96,LINE,10,a0=25,a1=155)
        for p in ((217,112),(128,166),(39,112)): g.dot(p,ACC,18)
    elif k=="dim":
        g.line([(36,70),(36,190)],DIM,8); g.line([(220,70),(220,190)],DIM,8)
        g.arrow((128,130),(40,130),ACC,9,28); g.arrow((128,130),(216,130),ACC,9,28)
    elif k=="dim_r":
        g.ell((128,128),92,92,LINE,10); g.dot((128,128),ACC,18)
        g.arrow((128,128),(193,193),ACC,9,28)
    elif k.startswith("subdc_"):
        a = k[6:]
        def cage():      # cage de contrôle : pointillée, avec ses points aux coins (même langage que les primitives SubD)
            q = [(40,60),(216,60),(216,196),(40,196)]
            for i_ in range(4):
                g.dash(q[i_], q[(i_+1) % 4], DIM, 6, 7)
            for p_ in q:
                g.dot(p_, ACC, 11)
        if a == "loft":
            g.ell((128,60),80,22,DIM,7); g.ell((128,128),56,18,LINE,8); g.ell((128,196),80,22,DIM,7)
            g.line([(48,60),(72,128),(48,196)],ACC,9); g.line([(208,60),(184,128),(208,196)],ACC,9)
        elif a == "sweep1":
            g.line([(30,200),(90,120),(170,90),(226,40)],DIM,8); g.ell((60,170),26,26,LINE,9,fill=FILLA); g.ell((196,66),26,26,ACC,9)
        elif a == "sweep2":
            g.line([(30,190),(120,150),(226,170)],DIM,8); g.line([(30,90),(120,50),(226,70)],DIM,8)
            g.line([(60,80),(60,180)],LINE,9); g.line([(190,64),(190,166)],ACC,9)
        elif a == "revolve":
            g.dash((50,30),(50,226),DIM,6,7); g.line([(50,60),(130,90),(110,170),(50,200)],LINE,9)
            g.ell((50,128),150,40,ACC,8,a0=-60,a1=60)
        elif a == "to_subd":
            g.poly([(24,84),(108,84),(108,172),(24,172)],None,LINE,8); g.arrow((116,128),(150,128),DIM,7,20)
            g.ell((196,128),40,40,LINE,9,fill=FILLA)
        elif a == "to_mesh":
            g.ell((60,128),40,40,DIM,8); g.arrow((108,128),(142,128),DIM,7,20)
            g.poly([(150,84),(234,84),(234,172),(150,172)],FILLA,LINE,9)
        elif a == "multipipe":
            g.line([(40,210),(128,128)],LINE,26); g.line([(216,210),(128,128)],LINE,26); g.line([(128,128),(128,36)],LINE,26)
            g.ell((128,128),20,20,ACC,6,fill=FILLA)
        elif a == "display":
            cage(); g.ell((128,128),62,48,LINE,9,fill=FILLA)
        elif a.startswith("sym_"):
            ax = a[-1]
            if ax == "x":
                g.dash((128,30),(128,226),ACC,7,7); g.poly([(40,80),(108,80),(108,176),(60,176)],FILLA,LINE,8); g.poly([(148,80),(216,80),(196,176),(148,176)],None,DIM,7)
            elif ax == "y":
                g.dash((30,128),(226,128),ACC,7,7); g.poly([(60,40),(196,40),(176,108),(80,108)],FILLA,LINE,8); g.poly([(80,148),(176,148),(196,216),(60,216)],None,DIM,7)
            else:
                g.dash((40,216),(216,40),ACC,7,7); g.poly([(36,36),(150,36),(36,150)],FILLA,LINE,8); g.poly([(220,106),(220,220),(106,220)],None,DIM,7)
        elif a == "crease":
            cage(); g.line([(40,60),(216,60)],ACC,14); g.dot((40,60),ACC,14); g.dot((216,60),ACC,14)
        elif a == "uncrease":
            cage(); g.line([(40,60),(216,60)],LINE,8); g.line([(150,110),(210,170)],ACC,10); g.line([(210,110),(150,170)],ACC,10)
        elif a == "insert_edge":
            cage(); g.line([(128,60),(128,196)],ACC,11)
        elif a == "slide":
            cage(); g.line([(128,60),(128,196)],LINE,9); g.arrow((128,128),(60,128),ACC,8,22); g.arrow((128,128),(196,128),ACC,8,22)
        elif a == "inset":
            g.poly([(40,60),(216,60),(216,196),(40,196)],None,LINE,8); g.poly([(84,94),(172,94),(172,162),(84,162)],FILLA,ACC,8)
            for p_,q_ in (((40,60),(84,94)),((216,60),(172,94)),((216,196),(172,162)),((40,196),(84,162))): g.line([p_,q_],DIM,5)
        elif a == "bevel":
            g.line([(40,200),(40,100),(100,40),(216,40)],LINE,10); g.line([(40,100),(100,40)],ACC,12)
        elif a == "bridge":
            g.line([(40,60),(216,60)],LINE,10); g.line([(40,196),(216,196)],LINE,10)
            g.poly([(70,60),(186,60),(186,196),(70,196)],FILLA,ACC,6)
        elif a == "fill":
            g.poly([(40,60),(216,60),(216,196),(40,196)],FILLA,LINE,10)
        elif a == "append":
            for p_ in ((50,190),(206,190),(128,60)): g.dot(p_,ACC,16)
            g.poly([(50,190),(206,190),(128,60)],FILLA,LINE,8)
        elif a == "merge_faces":
            g.poly([(40,60),(216,60),(216,196),(40,196)],FILLA,LINE,10); g.dash((128,60),(128,196),DIM,5,6); g.dash((40,128),(216,128),DIM,5,6)
        elif a == "extract":
            g.poly([(30,90),(150,90),(150,210),(30,210)],None,DIM,7); g.poly([(106,40),(226,40),(226,160),(106,160)],FILLA,LINE,9)
        elif a == "weld":
            g.dot((50,128),DIM,16); g.dot((206,128),DIM,16); g.arrow((60,128),(116,128),LINE,7,20); g.arrow((196,128),(140,128),LINE,7,20); g.dot((128,128),ACC,22)
        elif a == "stitch":
            g.line([(40,70),(216,70)],LINE,9); g.line([(40,186),(216,186)],LINE,9)
            g.line([(60,70),(90,186),(120,70),(150,186),(180,70),(200,186)],ACC,6)
        elif a == "sel_loop":
            cage(); g.ell((128,128),88,34,ACC,9)
        else:   # sel_ring
            cage()
            for x_ in (70,110,150,190): g.line([(x_,72),(x_,184)],ACC,9)
    elif k.startswith("subd_"):
        sub = k[5:]
        if sub == "box":
            g.poly([(40,40),(216,40),(216,216),(40,216)],None,DIM,6)
            g.ell((128,128),74,74,LINE,10,fill=FILLA)
        elif sub == "sphere":
            g.poly([(40,40),(216,40),(216,216),(40,216)],None,DIM,6); g.line([(40,128),(216,128)],DIM,5); g.line([(128,40),(128,216)],DIM,5)
            g.ell((128,128),80,80,LINE,10,fill=FILLA)
        elif sub == "cylinder":
            g.poly([(52,40),(204,40),(204,216),(52,216)],None,DIM,6)
            g.ell((128,70),68,22,LINE,8); g.ell((128,186),68,22,LINE,8); g.line([(60,70),(60,186)],LINE,9); g.line([(196,70),(196,186)],LINE,9)
        elif sub == "cone":
            g.poly([(52,40),(204,40),(204,216),(52,216)],None,DIM,6)
            g.ell((128,186),68,22,LINE,8); g.line([(60,186),(128,52)],LINE,9); g.line([(196,186),(128,52)],LINE,9)
        elif sub == "torus":
            g.poly([(30,60),(226,60),(226,196),(30,196)],None,DIM,6)
            g.ell((128,128),88,52,LINE,10,fill=FILLA); g.ell((128,128),34,16,LINE,8)
        else:
            for i in range(3):
                y = 60 + 68 * i
                g.line([(40,y),(216,y)],DIM,5); g.line([(40+88*i,60),(40+88*i,196)],DIM,5)
            g.line([(40,196),(90,150),(166,150),(216,196)],LINE,9)
        for p in ((40,40),(216,40),(216,216),(40,216)) if sub in ("box","sphere") else ():
            g.dot(p,ACC,14)
    elif k=="text":
        g.line([(52,56),(204,56)],LINE,16); g.line([(128,56),(128,206)],LINE,16)
        g.line([(40,222),(216,222)],DIM,7); g.dot((40,222),ACC,16)
    elif k=="center_mark":
        g.ell((128,128),78,78,LINE,10)
        g.line([(128,58),(128,198)],ACC,9); g.line([(58,128),(198,128)],ACC,9)
    elif k=="dist":
        g.dot((44,180),ACC,18); g.dot((212,76),ACC,18)
        g.dash((44,180),(212,76),LINE,8,6)
        g.line([(44,180),(212,180)],DIM,6); g.line([(212,180),(212,76)],DIM,6)
    elif k=="id_point":
        g.line([(128,40),(128,216)],DIM,7); g.line([(40,128),(216,128)],DIM,7)
        g.ell((128,128),46,46,LINE,9); g.dot((128,128),ACC,20)
    elif k=="area":
        g.poly([(40,70),(150,44),(216,120),(176,214),(66,186)],FILLA,LINE,10)
        for p in ((40,70),(150,44),(216,120),(176,214),(66,186)): g.dot(p,ACC,16)
    elif k=="join":
        g.line([(30,62),(122,146)],LINE,10); g.line([(122,146),(226,98)],LINE,10)
        g.dot((122,146),ACC,24)
        g.dot((30,62),DIM,14); g.dot((226,98),DIM,14)
    elif k=="light_point":          # comme l'icône Point de Blender : anneau, point central et pied
        g.ell((128,158),64,64,LINE,11)
        g.dot((128,158),ACC,22)
        g.line([(128,94),(128,30)],LINE,11)
    elif k=="light_sun":            # disque cerclé et rayons
        g.ell((128,128),40,40,LINE,11)
        g.dot((128,128),ACC,18)
        for a in range(8):
            ang=math.radians(a*45)
            g.line([(128+math.cos(ang)*68,128+math.sin(ang)*68),(128+math.cos(ang)*108,128+math.sin(ang)*108)],LINE,11)
    elif k=="light_spot":           # feuille : le faisceau du spot, avec son pied
        g.line([(60,70),(80,134),(124,184),(196,214),(214,196),(204,124),(160,78),(96,56)],LINE,11,closed=True)
        g.line([(60,70),(150,150)],ACC,10)
        g.line([(34,34),(52,52)],LINE,10)
    elif k=="light_area":           # rectangle incliné avec un point central
        g.line([(64,70),(214,110),(192,214),(42,174)],LINE,11,closed=True)
        g.dot((128,142),ACC,24)
        g.line([(20,40),(42,62)],LINE,10)
    elif k in ("camera","camera_target"):   # caméra de cinéma : deux bobines, boîtier et objectif (tout reste dans la grille)
        sc=1.0 if k=="camera" else 0.8
        ox=0 if k=="camera" else -16
        oy=0 if k=="camera" else 22
        def P(x,y): return (ox+x*sc, oy+y*sc)
        g.ell(P(78,172),32*sc,32*sc,LINE,11)
        g.ell(P(150,180),36*sc,36*sc,LINE,11)
        g.line([P(26,40),P(172,40),P(172,138),P(26,138)],LINE,11,closed=True)
        g.line([P(172,70),P(232,34),P(232,148),P(172,108)],LINE,11)
        g.dot(P(99,89),ACC,24*sc)
        if k=="camera_target":
            g.line([(212,56),(212,136)],ACC,10)
            g.line([(176,96),(244,96)],ACC,10)
    elif k=="align":
        g.line([(30,26),(30,230)],DIM,9)
        g.line([(44,196),(214,196)],ACC,20)
        g.line([(44,128),(160,128)],LINE,20)
        g.line([(44,60),(100,60)],LINE,20)
    elif k=="revolve":
        g.dash((70,238),(70,18),DIM,8,9)
        g.line([(70,208),(112,176),(132,128),(112,80),(70,48)],ACC,11)
        g.ell((70,208),70,22,LINE,8,a0=-20,a1=200)
        g.ell((70,48),70,22,LINE,8,a0=160,a1=380)
    elif k=="loft":
        g.line([(50,205),(80,128),(50,52)],LINE,8)
        g.line([(206,205),(176,128),(206,52)],LINE,8)
        g.ell((128,205),78,22,ACC,10)
        g.ell((128,128),48,15,LINE,9)
        g.ell((128,52),78,22,ACC,10)
    elif k=="sweep2":
        g.line([(24,30),(70,36),(120,70),(160,130),(232,190)],LINE,11)
        g.line([(24,96),(70,104),(120,140),(160,200),(232,236)],LINE,11)
        g.ell((38,64),22,22,ACC,10)
        g.dot((120,105),DIM,12)
    elif k=="sweep":
        g.line([(24,36),(70,44),(120,84),(160,150),(232,214)],LINE,11)
        g.ell((38,40),28,28,ACC,10)
        g.ell((214,200),22,22,DIM,9)
        g.dot((120,84),DIM,12)
    elif k=="explode":
        for a in range(6):
            ang=math.radians(a*60+20)
            g.line([(128+math.cos(ang)*38,128+math.sin(ang)*38),(128+math.cos(ang)*98,128+math.sin(ang)*98)],ACC if a%2==0 else LINE,10)
        g.dot((128,128),DIM,16)
    elif k=="make2d":     # volume (gris) -> dessin à plat (blanc)
        g.poly([(30,100),(110,100),(110,180),(30,180)],None,DIM,8)
        g.poly([(60,130),(140,130),(140,210),(60,210)],None,DIM,8)
        for a,b in (((30,100),(60,130)),((110,100),(140,130)),((110,180),(140,210)),((30,180),(60,210))): g.line([a,b],DIM,8)
        g.poly([(150,28),(226,28),(226,104),(150,104)],None,LINE,10)
        g.arrow((150,158),(184,116),ACC,10,26)
    elif k=="trim":
        g.line([(24,120),(232,120)],LINE,10)
        g.line([(128,120),(128,30)],ACC,10)
        g.dash((128,120),(128,226),DIM,8,5)
        g.dot((128,120),ACC,18)
    elif k=="offset_srf":
        g.poly([(24,50),(150,34),(232,74),(106,90)],None,DIM,8)
        g.poly([(24,140),(150,124),(232,164),(106,180)],FILLA,LINE,9)
        g.arrow((128,66),(128,126),ACC,9,28)
    elif k=="extrude":
        g.poly([(40,44),(150,44),(216,84),(106,84)],None,DIM,8)
        for a,b in (((40,44),(40,134)),((150,44),(150,134)),((216,84),(216,174))): g.line([a,b],DIM,7)
        g.poly([(40,134),(150,134),(216,174),(106,174)],FILLA,LINE,9)
        g.arrow((128,100),(128,226),ACC,9,28)
    elif k=="planar_srf":
        g.poly([(30,50),(226,50),(226,206),(30,206)],FILLA,ACC,9)
        g.poly([(90,96),(170,96),(170,160),(90,160)],None,LINE,9)
    elif k=="edge_srf":
        g.line([(26,60),(90,36),(166,36),(230,60)],ACC,11)
        g.line([(26,200),(90,224),(166,224),(230,200)],ACC,11)
        g.line([(26,60),(26,200)],LINE,9)
        g.line([(230,60),(230,200)],LINE,9)
        g.line([(26,130),(230,130)],DIM,6)
        g.line([(128,40),(128,222)],DIM,6)
    elif k=="thicken":
        g.poly([(30,60),(150,44),(226,84),(106,100)],None,DIM,8)
        g.poly([(30,60),(150,44),(150,92),(30,108)],None,LINE,8)
        g.poly([(30,108),(150,92),(226,132),(106,148)],FILLA,ACC,9)
        g.line([(226,84),(226,132)],LINE,8)
    elif k=="split_face":
        g.poly([(24,70),(150,40),(236,90),(110,128)],None,LINE,9)
        g.poly([(24,70),(110,128),(110,214),(24,156)],None,DIM,8)
        g.poly([(110,128),(236,90),(236,176),(110,214)],None,DIM,8)
        g.poly([(80,86),(150,74),(176,98),(112,112)],FILLA,ACC,10)
    elif k=="project_curve":
        g.poly([(20,150),(150,120),(236,170),(106,206)],FILLA,LINE,9)
        g.line([(60,40),(100,30),(150,50),(200,36)],DIM,8)
        g.line([(60,40),(60,150)],DIM,5)
        g.line([(100,30),(100,160)],DIM,5)
        g.line([(150,50),(150,168)],DIM,5)
        g.line([(60,152),(100,160),(150,168),(200,172)],ACC,11)
    elif k=="patch":
        g.poly([(30,150),(70,60),(190,50),(228,150),(130,214)],FILLA,ACC,10)
        g.line([(70,60),(130,214)],DIM,6)
        g.line([(190,50),(130,214)],DIM,6)
        g.line([(30,150),(228,150)],DIM,6)
    elif k=="xline":
        g.line([(14,200),(242,56)],ACC,10)
        g.dot((128,128),LINE,14)
    elif k=="stretch":
        g.poly([(30,70),(110,70),(110,190),(30,190)],None,DIM,6)
        g.line([(110,130),(210,130)],ACC,10)
        g.arrow((200,130),(244,130),ACC,10)
        g.line([(110,70),(110,190)],LINE,9)
    elif k=="divide":
        g.line([(24,176),(90,70),(166,186),(232,80)],LINE,9)
        for _p in ((24,176),(90,70),(166,186),(232,80)):
            g.dot(_p,ACC,13)
    elif k=="overkill":
        g.line([(30,70),(226,70)],DIM,6)
        g.line([(30,130),(226,130)],LINE,9)
        g.line([(30,190),(226,190)],DIM,6)
        g.line([(60,40),(196,220)],ACC,10)
    elif k=="cap":
        g.line([(60,70),(60,190)],LINE,9)
        g.line([(196,70),(196,190)],LINE,9)
        g.ell((128,190),68,26,LINE,9,a0=180,a1=360)
        g.ell((128,70),68,26,ACC,10)
        g.poly([(64,70),(100,50),(158,50),(194,70),(158,90),(100,90)],FILLA,None,1)
    elif k=="blend_srf":
        g.poly([(20,40),(100,40),(100,100),(20,100)],FILLA,LINE,8)
        g.poly([(156,156),(236,156),(236,216),(156,216)],FILLA,LINE,8)
        g.line([(100,70),(128,70),(128,186),(156,186)],ACC,11)
        g.line([(100,100),(122,150),(134,150),(156,156)],ACC,8)
    elif k=="match_srf":
        g.poly([(24,50),(110,50),(110,206),(24,206)],FILLA,LINE,9)
        g.poly([(146,50),(232,70),(232,226),(146,206)],None,DIM,8)
        g.arrow((110,128),(146,128),ACC,9,26)
    elif k=="rail_revolve":
        g.line([(128,24),(128,232)],DIM,6)
        g.line([(128,50),(190,80),(160,130),(200,190)],ACC,11)
        g.line([(128,50),(66,80),(96,130),(56,190)],LINE,9)
        g.ell((128,190),72,22,LINE,8,a0=0,a1=180)
    elif k=="shell":
        g.poly([(40,70),(150,70),(150,200),(40,200)],None,LINE,9)
        g.poly([(150,70),(216,40),(216,170),(150,200)],None,LINE,9)
        g.poly([(40,70),(106,40),(216,40),(150,70)],None,ACC,9)
        g.poly([(64,110),(126,110),(126,180),(64,180)],None,DIM,7)
    elif k=="select":
        g.poly([(106, 55), (200, 55), (200, 149), (106, 149)],None,DIM,8)
        g.poly([(57, 201), (57, 95), (84, 118), (104, 76), (125, 86), (107, 127), (143, 128)],FILLA,LINE,10)
    elif k=="lasso":     # boucle pointillée orange + flèche de sélection (comme l'icône Lasso de Blender)
        ca, sa = math.cos(math.radians(18)), math.sin(math.radians(18))
        loop = []
        for i in range(37):
            t = math.radians(360 * i / 36)
            ex, ey = 84 * math.cos(t), 66 * math.sin(t)
            loop.append((150 + ex * ca - ey * sa, 142 + ex * sa + ey * ca))
        for i in range(0, 36, 4):
            g.line(loop[i:i + 4], ACC, 12, joints=False)
        arrow = [(57, 201), (57, 95), (84, 118), (104, 76), (125, 86), (107, 127), (143, 128)]
        g.poly([((x - 57) * 0.92 + 51, (y - 201) * 0.92 + 165) for x, y in arrow], FILLA, LINE, 10)
    elif k=="sel_box":
        g.poly([(40, 40), (176, 40), (176, 176), (40, 176)], None, ACC, 11)
        arrow = [(57, 201), (57, 95), (84, 118), (104, 76), (125, 86), (107, 127), (143, 128)]
        g.poly([((x - 57) * 0.92 + 100, (y - 201) * 0.92 + 190) for x, y in arrow], FILLA, LINE, 10)
    elif k=="sel_circle":
        ring = [(108 + 80 * math.cos(math.radians(360 * i / 36)), 108 + 80 * math.sin(math.radians(360 * i / 36))) for i in range(37)]
        for i in range(0, 36, 4):
            g.line(ring[i:i + 4], ACC, 12, joints=False)
        arrow = [(57, 201), (57, 95), (84, 118), (104, 76), (125, 86), (107, 127), (143, 128)]
        g.poly([((x - 57) * 0.92 + 100, (y - 201) * 0.92 + 190) for x, y in arrow], FILLA, LINE, 10)
    elif k=="poly_c":
        g.poly([(128, 224), (45, 176), (45, 80), (128, 32), (211, 80), (211, 176)],None,LINE,10)
        g.dash((128,128),(128, 224),ACC,8,5); g.dot((128,128),ACC,18); g.dot((128, 224),ACC,18)
    elif k=="poly_k":
        g.ell((128,128),84,84,DIM,6)
        g.poly([(211, 176), (128, 224), (45, 176), (45, 80), (128, 32), (211, 80)],None,LINE,10)
        g.dash((128,128),(128,212),ACC,8,5); g.dot((128,128),ACC,18)
    elif k=="poly_a":
        g.poly([(128, 224), (45, 176), (45, 80), (128, 32), (211, 80), (211, 176)],FILLA,ACC,10)
        g.dot((128,128),LINE,18)
    elif k=="poly_e":
        g.poly([(211, 176), (128, 224), (45, 176), (45, 80), (128, 32), (211, 80)],None,LINE,10)
        g.line([(45, 80),(128, 32)],ACC,14)
        g.dot((45, 80),ACC,20); g.dot((128, 32),ACC,20)
    elif k=="poly_s":
        g.poly([(128, 232), (102, 164), (29, 160), (86, 114), (67, 44), (128, 84), (189, 44), (170, 114), (227, 160), (154, 164)],FILLA,ACC,9)
        g.dot((128,128),LINE,18)
    elif k=="mirror":
        g.dash((128,236),(128,20),LINE,8,9)
        g.poly([(40,60),(110,60),(110,200)],None,DIM,8)
        g.poly([(216,60),(146,60),(146,200)],FILLA,ACC,9)
    elif k=="array_r":
        for i in range(3):
            for j in range(3):
                x=40+i*72; y=40+j*72
                if i==0 and j==0: g.poly([(x-22,y-22),(x+22,y-22),(x+22,y+22),(x-22,y+22)],None,LINE,8)
                else: g.poly([(x-22,y-22),(x+22,y-22),(x+22,y+22),(x-22,y+22)],FILLA,ACC,8)
    elif k=="array_l":
        for i in range(4):
            x=36+i*62; y=52+i*50
            if i==0: g.poly([(x-24,y-24),(x+24,y-24),(x+24,y+24),(x-24,y+24)],None,LINE,8)
            else: g.poly([(x-24,y-24),(x+24,y-24),(x+24,y+24),(x-24,y+24)],FILLA,ACC,8)
    elif k=="array_p":
        g.ell((128,128),84,84,DIM,6)
        for i in range(6):
            a=math.pi/2+i*math.pi/3; x=128+84*math.cos(a); y=128+84*math.sin(a)
            if i==0: g.poly([(x-20,y-20),(x+20,y-20),(x+20,y+20),(x-20,y+20)],None,LINE,8)
            else: g.poly([(x-20,y-20),(x+20,y-20),(x+20,y+20),(x-20,y+20)],FILLA,ACC,8)
        g.dot((128,128),ACC,18)
    elif k=="fillet":
        g.dash((40,100),(40,36),DIM,8,4); g.dash((40,36),(110,36),DIM,8,3)
        g.line([(226,36),(100,36)],LINE,10)
        g.ell((100,100),60,64,ACC,12,None,180,270)
        g.line([(40,100),(40,226)],LINE,10)
        g.dot((40,36),DIM,16)
    elif k=="chamfer":
        g.dash((40,100),(40,36),DIM,8,4); g.dash((40,36),(110,36),DIM,8,3)
        g.line([(226,36),(110,36)],LINE,10)
        g.line([(110,36),(40,106)],ACC,12)
        g.line([(40,106),(40,226)],LINE,10)
        g.dot((40,36),DIM,16)
    elif k=="fillet_c":
        g.dash((196,130),(196,66),DIM,8,4); g.dash((196,66),(136,66),DIM,8,3)
        g.line([(30,66),(136,66)],LINE,10)
        g.ell((136,130),60,64,ACC,12,None,270,360)
        g.line([(196,130),(196,226)],LINE,10)
        g.dot((196,66),DIM,16)
    elif k=="chamfer_c":
        g.dash((196,130),(196,66),DIM,8,4); g.dash((196,66),(130,66),DIM,8,3)
        g.line([(30,66),(130,66)],LINE,10)
        g.line([(130,66),(196,132)],ACC,12)
        g.line([(196,132),(196,226)],LINE,10)
        g.dot((196,66),DIM,16)
    elif k=="clip_plane":
        g.poly([(36,160),(150,112),(226,158),(112,206)],FILLA,ACC,9)
        g.line([(130,150),(130,60)],LINE,10)
        g.arrow((130,80),(130,34),LINE,10)
    elif k=="offset":
        g.line([(36,226),(36,36),(226,36)],LINE,10)
        g.dash((36,36),(100,100),DIM,8,4)
        g.line([(100,226),(100,100),(226,100)],ACC,12)
        g.dot((36,36),DIM,16)
    elif k=="bool_u":
        g.poly([(30,50),(150,50),(150,80),(222,80),(222,206),(100,206),(100,176),(30,176)],FILLA,ACC,10)
    elif k=="bool_d":
        g.poly([(100,80),(222,80),(222,206),(100,206)],None,DIM,8)
        g.poly([(30,50),(150,50),(150,80),(100,80),(100,176),(30,176)],FILLA,ACC,10)
    elif k=="bool_i":
        g.poly([(30,50),(150,50),(150,176),(30,176)],None,DIM,8)
        g.poly([(100,80),(222,80),(222,206),(100,206)],None,DIM,8)
        g.poly([(100,80),(150,80),(150,176),(100,176)],FILLA,ACC,10)
    elif k=="bool_s":
        g.poly([(30,50),(150,50),(150,176),(30,176)],None,LINE,9)
        g.poly([(100,80),(222,80),(222,206),(100,206)],None,DIM,8)
        g.line([(100,80),(150,80),(150,176),(100,176),(100,80)],ACC,12)
    elif k=="cut":
        g.poly([(36,60),(116,60),(116,184),(36,184)],None,DIM,8)
        g.poly([(142,60),(222,60),(222,184),(142,184)],FILLA,ACC,9)
        g.dash((129,236),(129,20),LINE,8,9)
    elif k=="box":
        top=[(128,226),(212,177),(128,128),(44,177)]; l=[(44,177),(128,128),(128,30),(44,79)]; r=[(128,128),(212,177),(212,79),(128,30)]
        g.poly(top,FILLA,ACC,9); g.poly(l,None,LINE,9); g.poly(r,None,LINE,9)
    elif k in("cylinder","tube"):
        g.line([(40,190),(40,66)],LINE,9); g.line([(216,190),(216,66)],LINE,9)
        g.ell((128,66),88,28,LINE,9,a0=180,a1=360)
        g.ell((128,190),88,28,ACC,9,fill=FILLA)
        if k=="tube": g.ell((128,190),50,16,ACC,8)
    elif k=="cone":
        g.line([(40,70),(128,226),(216,70)],LINE,9); g.ell((128,70),88,28,LINE,9,a0=180,a1=360)
        g.ell((128,70),88,28,ACC,9,a0=0,a1=180)
    elif k=="tcone":
        g.line([(40,66),(90,188)],LINE,9); g.line([(216,66),(166,188)],LINE,9)
        g.ell((128,66),88,28,LINE,9,a0=180,a1=360); g.ell((128,188),38,14,ACC,9,fill=FILLA)
    elif k=="pyramid":
        g.poly([(128,226),(30,96),(128,46)],None,LINE,9); g.poly([(128,226),(128,46),(226,96)],FILLA,ACC,9)
    elif k=="tpyramid":
        g.poly([(98,176),(128,164),(128,42),(30,90)],None,LINE,9); g.poly([(128,164),(158,176),(226,90),(128,42)],None,LINE,9)
        g.poly([(98,176),(128,188),(158,176),(128,164)],FILLA,ACC,9)
    elif k in("sphere","ellipsoid"):
        rx,ry=(98,98) if k=="sphere" else (112,74)
        g.ell((128,128),rx,ry,LINE,10); g.ell((128,128),rx,26,ACC,8,a0=180,a1=360); g.ell((128,128),rx,26,DIM,6,a0=0,a1=180)
    elif k=="tsphere":
        g.ell((128,128),98,98,LINE,10,a0=193,a1=347)
        g.ell((128,150),95,24,ACC,9,fill=FILLA)
    elif k=="torus":
        g.ell((128,128),112,78,LINE,10); g.ell((128,128),56,28,ACC,9)

    else:
        raise ValueError(kind)

    coords, colors = bytearray(), bytearray()
    for a, b, c, col in g.tris:
        for x, y in (a, b, c):
            coords += bytes((x, y))
            colors += bytes(col)
    return b"VCO\x00" + bytes((0xFF, 0xFF, 0x00, 0x00)) + bytes(coords) + bytes(colors)


# Palette « tons terre » : une teinte par famille d'outils (remplace l'ambre sur ce que l'outil crée ou modifie)
ICON_FAMILY_COLORS = ((169, 185, 209), (224, 144, 122), (169, 189, 126), (227, 184, 99),
                      (185, 154, 196), (217, 168, 140), (201, 163, 107), (143, 194, 189), (214, 140, 170))
ICON_FAMILIES = (
    ("select", "sel_box", "sel_circle", "lasso", "stretch", "move", "copy", "rotate", "scale", "scale_2d", "scale_1d", "scale_size", "mirror", "array_l", "array_r", "array_p", "align", "orient"),
    ("join", "explode", "trim", "cut", "divide", "overkill", "split_face", "bool_u", "bool_d", "bool_i", "bool_s", "fillet", "chamfer", "fillet_c", "chamfer_c", "offset_srf", "offset",
     "block", "block_insert", "merge_faces"),
    ("polyline", "xline", "curve_cp", "curve_i", "pen", "sketch", "point", "rect", "circle", "circle_d", "ellipse_c", "ellipse_d", "ellipse_f", "ellipse_k",
     "poly_c", "poly_k", "poly_a", "poly_e", "poly_s", "arc", "arc3", "project_curve",
     "blend_crv", "match_crv", "rebuild_crv", "simplify_crv", "change_degree", "insert_point", "remove_point", "intersect", "section", "contour", "dup_border", "dup_edge"),
    ("plane", "srf_pts", "planar_srf", "edge_srf", "network_srf", "patch", "extrude", "extrude_path", "revolve", "rail_revolve", "loft", "sweep", "sweep2"),
    ("blend_srf", "match_srf", "fillet_srf", "chamfer_srf", "extend_srf", "split_iso", "untrim", "untrim_holes", "thicken", "cap", "shell", "extract_srf", "unroll", "rebuild_srf"),
    ("box", "cylinder", "cone", "tcone", "pyramid", "tpyramid", "tube", "sphere", "ellipsoid", "tsphere", "torus", "pipe"),
    ("light_point", "light_spot", "light_sun", "light_area", "camera", "camera_target"),
    ("dim", "dim_chain", "dim_ord", "dim_arc", "dim_r", "dim_a", "note", "text", "center_mark", "dim_edit", "hatch", "hatch_region", "area", "dist", "id_point", "make2d", "clip_plane", "layout", "detail"),
    ("subd_box", "subd_sphere", "subd_cylinder", "subd_cone", "subd_torus", "subd_plane", "subdc_to_subd", "subdc_to_mesh",
     "subdc_loft", "subdc_sweep1", "subdc_sweep2", "subdc_revolve",
     "subdc_multipipe", "subdc_display", "subdc_sym_x", "subdc_sym_y", "subdc_sym_z", "subdc_crease", "subdc_uncrease",
     "subdc_insert_edge", "subdc_slide", "subdc_bevel", "subdc_inset", "subdc_bridge", "subdc_fill", "subdc_append", "subdc_merge_faces",
     "subdc_extract", "subdc_weld", "subdc_stitch", "subdc_sel_loop", "subdc_sel_ring"),
)
_ICON_ACCENT_RGB = {(245, 184, 61), (255, 168, 38), (217, 168, 78)}
_ICON_CONTEXT_RGB = {(228, 228, 230), (222, 226, 232)}
_ICON_REF_RGB = {(133, 133, 138)}


def _family_recolor(kind, data):
    """Remplace la couleur d'accent (ambre) par celle de la famille de l'outil, en gardant la transparence."""
    palette = pref("icon_palette")
    if palette == 'AMBER' or not data.startswith(b"VCO\x00"):
        return data
    fi = next((i for i, f in enumerate(ICON_FAMILIES) if kind in f), None)
    if palette == 'EARTH' and fi is None:
        return data
    n = (len(data) - 8) // 6
    off = 8 + 2 * n
    out = bytearray(data)
    if palette == 'TARGET':     # contexte grisé, seule la cible (ce que l'outil crée) en rouge signal
        for v in range(n):
            o = off + 4 * v
            c = (out[o], out[o + 1], out[o + 2])
            if c in _ICON_ACCENT_RGB:
                out[o], out[o + 1], out[o + 2] = 255, 70, 78
            elif c in _ICON_CONTEXT_RGB:
                out[o], out[o + 1], out[o + 2] = 160, 160, 166
            elif c in _ICON_REF_RGB:
                out[o], out[o + 1], out[o + 2] = 96, 96, 102
        return bytes(out)
    r, g, b = (106, 169, 255) if palette == 'BLUE' else ICON_FAMILY_COLORS[fi]
    for v in range(n):
        o = off + 4 * v
        if (out[o], out[o + 1], out[o + 2]) in _ICON_ACCENT_RGB:
            out[o], out[o + 1], out[o + 2] = r, g, b
    return bytes(out)


def ensure_icon(kind, fallback):
    """Écrit l'icône dans le dossier de config de Blender et retourne son chemin (sans .dat)."""
    try:
        try:   # extension (Blender 4.2+) : dossier utilisateur propre à l'extension ; sinon dossier de config
            folder = bpy.utils.extension_path_user(__package__, path="icons", create=True)
        except (AttributeError, ValueError, RuntimeError, TypeError):
            folder = bpy.utils.user_resource('CONFIG', path="wanderer_icons", create=True)
        base = os.path.join(folder, kind + icon_suffix())  # nom versionné : Blender garde les icônes en cache jusqu'au redémarrage
        data = _family_recolor(kind, _icon_bytes(kind))
        path = base + ".dat"
        current = None
        if os.path.exists(path):
            with open(path, "rb") as f:
                current = f.read()
        if current != data:
            with open(path, "wb") as f:
                f.write(data)
        return base
    except Exception:
        return fallback


def _late_imports():
    pass
