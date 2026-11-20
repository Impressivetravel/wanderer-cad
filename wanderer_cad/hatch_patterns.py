"""Wanderer CAD : bibliothèque de motifs de hachure.

Un motif est une liste de familles de lignes, comme dans un fichier .pat d'AutoCAD ou de Rhino :
(angle en degrés, origine le long de la ligne, origine perpendiculaire, décalage le long de la ligne d'une ligne à
la suivante, écart entre deux lignes, tirets). Un tiret positif est un trait, négatif un vide, 0 un point.
L'unité 1 est l'écart des lignes du motif ANSI31 (Hatch1) : à l'échelle 1, environ 10 pixels à la création.

Les motifs de matériaux sont décrits ici par un « carreau » (deux vecteurs de répétition et des segments) :
`tile_families` en tire les familles de lignes équivalentes. Les fichiers .pat importés s'ajoutent à la liste
(rangés dans la scène, et recopiés dans chaque hachure qui s'en sert)."""

import json
import math
import os

import numpy as np

try:
    import bpy
except ImportError:          # tests hors de Blender
    bpy = None


# --------------------------------------------------------------------------
# Carreau -> familles de lignes
# --------------------------------------------------------------------------

def _egcd(a, b):
    if b == 0:
        return (1 if a >= 0 else -1), 0, abs(a)
    x, y, g = _egcd(b, a % b)
    return y, x - (a // b) * y, g


def tile_families(t1, t2, segs, search=40):
    """Familles de lignes d'un motif répété sur le réseau (t1, t2). `segs` : [((x0, y0), (x1, y1))] ; un segment de
    longueur nulle est un point. Chaque direction doit être celle d'un vecteur du réseau (pente rationnelle)."""
    t1 = np.asarray(t1, dtype=np.float64)
    t2 = np.asarray(t2, dtype=np.float64)
    det = abs(float(t1[0] * t2[1] - t1[1] * t2[0]))
    fams = []
    for p0, p1 in segs:
        p0 = np.asarray(p0, dtype=np.float64)
        p1 = np.asarray(p1, dtype=np.float64)
        L = float(np.linalg.norm(p1 - p0))
        d = (p1 - p0) / L if L > 1e-12 else None
        best = None
        for i in range(-search, search + 1):
            for j in range(-search, search + 1):
                if (i == 0 and j == 0) or math.gcd(i, j) != 1:
                    continue
                v = i * t1 + j * t2
                lv = float(np.linalg.norm(v))
                if d is None:
                    ok = True
                else:
                    ok = abs(float(v[0] * d[1] - v[1] * d[0])) < 1e-7 * lv and float(v @ d) > 0
                if ok and (best is None or lv < best[0] - 1e-9):
                    best = (lv, i, j, v)
        if best is None:
            raise ValueError(f"direction {p1 - p0} is not a direction of the tile")
        P, i, j, v = best
        if d is None:
            d = v / P
        a, b, _g = _egcd(i, j)          # a·i + b·j = 1
        g = -b * t1 + a * t2            # det(v, g) = det(t1, t2)
        n = np.array((-d[1], d[0]))
        if float(g @ n) < 0:
            g = -g
        assert abs(float(g @ n) * P - det) < 1e-6 * max(det, 1.0)
        dashes = (round(L, 9), -round(P - L, 9)) if P - L > 1e-9 else ()
        fams.append((round(math.degrees(math.atan2(d[1], d[0])), 9), round(float(p0 @ d), 9), round(float(p0 @ n), 9),
                     round(float(g @ d), 9), round(float(g @ n), 9), dashes))
    return tuple(fams)


def _poly(pts, closed=True):
    n = len(pts)
    return [(pts[k], pts[(k + 1) % n]) for k in range(n if closed else n - 1)]


def _rot(segs, deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    r = lambda p: (p[0] * c - p[1] * s, p[0] * s + p[1] * c)
    return [(r(a), r(b)) for a, b in segs]


def _rotv(v, deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return (v[0] * c - v[1] * s, v[0] * s + v[1] * c)


def _dots(pts):
    return [(p, p) for p in pts]


def _material_patterns():
    pats = {}
    # Béton : granulats (petits triangles) et points, comme AR-CONC
    tri = lambda x, y, k: _poly([(x, y), (x + 2 * k, y), (x + k, y + 2 * k)])
    pats['CONCRETE'] = tile_families((10, 0), (0, 10),
        tri(1, 1, 0.5) + _poly([(6, 2), (7, 2), (7, 4)]) + _poly([(3, 6), (4, 7), (2, 7)])
        + _poly([(7, 7), (8, 6), (8, 8)])
        + _dots([(4.5, 2.5), (8.5, 4.5), (1.5, 4.5), (5.5, 5), (6, 8.5), (1, 8.8), (9.2, 1.2), (3.2, 9.3)]))
    # Terre : groupes de trois traits, horizontaux puis verticaux, comme EARTH
    e = []
    for k in range(3):
        e.append(((0.3, 0.6 + 0.7 * k), (2.3, 0.6 + 0.7 * k)))
        e.append(((3.0 + 0.7 * k, 3.0), (3.0 + 0.7 * k, 5.0)))
    pats['EARTH'] = tile_families((5.2, 0), (0, 5.2), e)
    # Gravier : cailloux à facettes
    pats['GRAVEL'] = tile_families((10, 0), (0, 10),
        _poly([(1, 1), (3, 1), (4, 2), (3, 3), (1, 3), (0.5, 2)])
        + _poly([(6, 1), (8, 2), (8, 3), (7, 4), (5, 3)])
        + _poly([(2, 5), (4, 6), (4, 7), (3, 8), (1, 7), (1, 6)])
        + _poly([(6, 6), (8, 6), (9, 7), (8, 9), (6, 8)]))
    # Sable : points semés
    pats['SAND'] = tile_families((6, 0), (0, 6), _dots(
        [(0.5, 0.5), (3.2, 1.0), (5.0, 2.2), (1.6, 2.6), (4.1, 3.9), (0.4, 4.4), (2.7, 5.1), (5.4, 5.3),
         (2.3, 0.2), (1.2, 1.4), (3.6, 2.6), (0.9, 3.4), (5.1, 0.9), (3.0, 4.4), (4.6, 5.6), (1.8, 5.6)]))
    # Gazon / végétation : touffes en éventail sur un réseau en quinconce
    pats['GRASS'] = tile_families((6, 0), (3, 5),
        [((0, 0), (0, 2)), ((0, 0), (0.9, 1.5)), ((0, 0), (-0.9, 1.5)), ((0, 0), (1.8, 1.0)), ((0, 0), (-1.8, 1.0))])
    # Isolant : zigzag (isolation en rouleaux), rangées espacées
    pats['INSULATION'] = tile_families((3, 0), (0, 3.6), [((0, 0), (1.5, 3)), ((1.5, 3), (3, 0))])
    # Pierre appareillée : assises de hauteurs et de longueurs différentes
    a = [((0, 0), (12, 0)), ((0, 2), (12, 2)), ((0, 3.5), (12, 3.5))]
    a += [((x, 0), (x, 2)) for x in (0, 5)] + [((x, 2), (x, 3.5)) for x in (2.5, 8, 10.5)]
    a += [((x, 3.5), (x, 6)) for x in (3.5, 9)]
    pats['ASHLAR'] = tile_families((12, 0), (0, 6), a)
    # Chevrons (parquet, pavés), comme AR-HBONE : briques 2 x 1 tournées à 45°
    hb = _poly([(0, 0), (4, 0), (4, 2), (0, 2)]) + _poly([(4, -2), (6, -2), (6, 2), (4, 2)])
    pats['HERRINGBONE'] = tile_families(_rotv((2, 2), 45), _rotv((4, -4), 45), _rot(hb, 45))
    # Nid d'abeille (hexagones)
    s3 = math.sqrt(3.0)
    pats['HONEYCOMB'] = tile_families((3, s3), (3, -s3),
        [((0, 0), (2, 0)), ((2, 0), (3, s3)), ((2, 0), (3, -s3))])
    # Points réguliers en quinconce
    pats['DOTS'] = tile_families((2, 0), (1, 1), _dots([(0, 0)]))
    # Petites croix
    pats['CROSS'] = tile_families((3, 0), (0, 3), [((-0.4, -0.4), (0.4, 0.4)), ((-0.4, 0.4), (0.4, -0.4))])
    # Eau : traits courts en quinconce
    pats['WATER'] = tile_families((8, 0), (4, 1.5), [((0, 0), (3, 0))])
    return pats


HATCH_PATTERNS = {
    'SOLID': None,
    'HATCH1': ((45.0, 0.0, 0.0, 0.0, 1.0, ()),),
    'HATCH2': ((45.0, 0.0, 0.0, 0.0, 1.0, ()), (135.0, 0.0, 0.0, 0.0, 1.0, ())),
    'HATCH3': ((45.0, 0.0, 0.0, 0.0, 1.0, ()), (45.0, 0.0, 0.25, 0.0, 1.0, ())),
    'DASH': ((45.0, 0.0, 0.0, 0.5, 1.0, (1.0, -0.5)),),
    'GRID': ((0.0, 0.0, 0.0, 0.0, 1.0, ()), (90.0, 0.0, 0.0, 0.0, 1.0, ())),
    'GRID60': ((0.0, 0.0, 0.0, 0.0, 1.0, ()), (60.0, 0.0, 0.0, 0.0, 1.0, ()), (120.0, 0.0, 0.0, 0.0, 1.0, ())),
    'PLUS': ((0.0, -0.15, 0.0, 0.0, 1.0, (0.3, -0.7)), (90.0, -0.15, 0.0, 0.0, 1.0, (0.3, -0.7))),
    'SQUARES': ((0.0, 0.0, 0.0, 0.0, 1.0, (0.5, -0.5)), (0.0, 0.0, 0.5, 0.0, 1.0, (0.5, -0.5)),
                (90.0, 0.0, 0.0, 0.0, 1.0, (0.5, -0.5)), (90.0, 0.0, -0.5, 0.0, 1.0, (0.5, -0.5))),
    'BRICK': ((0.0, 0.0, 0.0, 0.0, 1.0, ()), (90.0, 0.0, 0.0, 1.0, 1.0, (1.0, -1.0))),
}
HATCH_PATTERNS.update(_material_patterns())

# (clé, nom, description, numéro) : les numéros ne changent jamais (ils sont enregistrés dans les fichiers)
BUILTIN_ITEMS = (
    ('SOLID', "Solid", "Solid fill", 0),
    ('HATCH1', "Hatch1", "Parallel lines at 45 degrees (ANSI31)", 1),
    ('HATCH2', "Hatch2", "Crossed lines at 45 degrees (ANSI37)", 2),
    ('HATCH3', "Hatch3", "Pairs of lines at 45 degrees (ANSI32, steel)", 3),
    ('DASH', "Dash", "Dashed lines at 45 degrees", 4),
    ('GRID', "Grid", "Square grid (tiles)", 5),
    ('GRID60', "Grid60", "Triangular grid (60 degrees)", 6),
    ('PLUS', "Plus", "Small plus signs", 7),
    ('SQUARES', "Squares", "Small squares", 8),
    ('BRICK', "Brick", "Brick courses", 9),
    ('CONCRETE', "Concrete", "Concrete: aggregate and dots (AR-CONC)", 10),
    ('EARTH', "Earth", "Earth, soil: groups of three strokes (EARTH)", 11),
    ('GRAVEL', "Gravel", "Gravel, crushed stone", 12),
    ('SAND', "Sand", "Sand, mortar, plaster: scattered dots (AR-SAND)", 13),
    ('GRASS', "Grass", "Grass, vegetation: tufts (GRASS)", 14),
    ('INSULATION', "Insulation", "Insulation: zigzag (batt insulation)", 15),
    ('ASHLAR', "Ashlar", "Stone masonry: courses of cut stone", 16),
    ('HERRINGBONE', "Herringbone", "Herringbone: parquet, pavers (AR-HBONE)", 17),
    ('HONEYCOMB', "Honeycomb", "Hexagons", 18),
    ('DOTS', "Dots", "Regular dots", 19),
    ('CROSS', "Cross", "Small crosses", 20),
    ('WATER', "Water", "Water: short staggered strokes", 21),
)
HATCH_PATTERN_ITEMS = tuple((k, n, d) for k, n, d, _i in BUILTIN_ITEMS)
CUSTOM_BASE = 1000          # numéros des motifs importés : 1000 + leur identifiant


# --------------------------------------------------------------------------
# Fichiers .pat (AutoCAD, Rhino, Revit)
# --------------------------------------------------------------------------

def parse_pat(text):
    """Motifs d'un fichier .pat : [(nom, description, familles)] en unités du motif ANSI31 (écart 1).
    Les fichiers métriques (;%UNITS=MM, acadiso.pat) sont reconnus. Les lignes illisibles sont ignorées."""
    unit = 0.125
    for raw in text.splitlines()[:40]:
        s = raw.strip().upper().replace(" ", "")
        if s.startswith(";%UNITS=MM"):
            unit = 3.175
            break
        if s.startswith(";%UNITS=INCH"):
            break
    out = []
    cur = None
    for raw in text.splitlines():
        s = raw.split(";", 1)[0].strip()
        if not s:
            continue
        if s.startswith("*"):
            name, _sep, desc = s[1:].partition(",")
            cur = [name.strip(), desc.strip(), []]
            out.append(cur)
            continue
        if cur is None:
            continue
        try:
            vals = [float(x) for x in s.replace("\t", " ").split(",") if x.strip() != ""]
        except ValueError:
            continue
        if len(vals) < 5:
            continue
        ang, x0, y0, dx, dy = vals[:5]
        dashes = tuple(round(x / unit, 9) for x in vals[5:])
        if abs(dy) < 1e-12:
            continue
        a = math.radians(ang)
        ca, sa = math.cos(a), math.sin(a)
        if dy < 0:
            dx, dy = -dx, -dy
        cur[2].append((ang, round((x0 * ca + y0 * sa) / unit, 9), round((-x0 * sa + y0 * ca) / unit, 9),
                       round(dx / unit, 9), round(dy / unit, 9), dashes))
    return [(n, d, tuple(f)) for n, d, f in out if n and f]


# --------------------------------------------------------------------------
# Motifs importés : rangés dans la scène (dessin.hatch_custom, JSON), lus ici
# --------------------------------------------------------------------------

_CUSTOM = {}            # numéro -> {"id", "name", "desc", "fams"}
_ITEMS = []             # éléments de l'énumération (gardés en mémoire : Blender ne les copie pas)


def custom_key(cid):
    return f"PAT{int(cid)}"


def _scene_custom(scene):
    try:
        return json.loads(scene.dessin.hatch_custom or "[]")
    except (AttributeError, ValueError, TypeError, ReferenceError):
        return []


def refresh_custom():
    """Relit les motifs importés de toutes les scènes et refait la liste des motifs."""
    _CUSTOM.clear()
    if bpy is not None:
        try:
            scenes = list(bpy.data.scenes)
        except (AttributeError, RuntimeError):
            scenes = []
        for sc in scenes:
            for e in _scene_custom(sc):
                try:
                    cid = int(e["id"])
                    _CUSTOM[cid] = {"id": cid, "name": str(e["name"]), "desc": str(e.get("desc", "")),
                                    "fams": tuple((float(f[0]), float(f[1]), float(f[2]), float(f[3]), float(f[4]),
                                                   tuple(float(x) for x in f[5])) for f in e["fams"])}
                except (KeyError, ValueError, TypeError, IndexError):
                    pass
    _rebuild_items()


def _rebuild_items():
    items = []
    for k, n, d, num in BUILTIN_ITEMS:
        items.append((k, n, d, preview_icon(k), num))
    for cid in sorted(_CUSTOM):
        e = _CUSTOM[cid]
        k = custom_key(cid)
        items.append((k, e["name"], (e["desc"] or e["name"]) + " (imported)", preview_icon(k), CUSTOM_BASE + cid))
    _ITEMS[:] = items


def pattern_items(self=None, context=None):
    if not _ITEMS:
        _rebuild_items()
    return _ITEMS


def pattern_list():
    """[(clé, nom)] de tous les motifs, dans l'ordre de la liste."""
    return [(it[0], it[1]) for it in pattern_items()]


def hatch_families(key, dd=None):
    """Familles de lignes d'un motif : intégré, importé, ou à défaut celles recopiées dans la hachure (dd["fams"])."""
    if key in HATCH_PATTERNS:
        return HATCH_PATTERNS[key]
    if isinstance(key, str) and key.startswith("PAT"):
        try:
            e = _CUSTOM.get(int(key[3:]))
        except ValueError:
            e = None
        if e is not None:
            return e["fams"]
    if dd is not None and dd.get("fams"):
        return tuple((f[0], f[1], f[2], f[3], f[4], tuple(f[5])) for f in dd["fams"])
    return HATCH_PATTERNS['HATCH1']          # motif importé introuvable : lignes à 45°


def is_custom(key):
    return isinstance(key, str) and key.startswith("PAT")


def add_custom_patterns(scene, pats):
    """Ajoute des motifs (nom, description, familles) à la scène ; un motif du même nom est remplacé.
    Renvoie les clés des motifs ajoutés."""
    cur = _scene_custom(scene)
    used = set(_CUSTOM) | {int(e.get("id", 0)) for e in cur}
    nxt = max(used, default=0) + 1
    keys = []
    for name, desc, fams in pats:
        hit = next((e for e in cur if e.get("name", "").upper() == name.upper()), None)
        rec = {"name": name, "desc": desc, "fams": [list(f[:5]) + [list(f[5])] for f in fams]}
        if hit is not None:
            hit.update(rec)
            keys.append(custom_key(hit["id"]))
        else:
            rec["id"] = nxt
            cur.append(rec)
            keys.append(custom_key(nxt))
            nxt += 1
    scene.dessin.hatch_custom = json.dumps(cur)
    refresh_custom()
    return keys


def remove_custom_pattern(scene, key):
    if not is_custom(key):
        return False
    cid = int(key[3:])
    cur = [e for e in _scene_custom(scene) if int(e.get("id", -1)) != cid]
    scene.dessin.hatch_custom = json.dumps(cur)
    refresh_custom()
    return True


# --------------------------------------------------------------------------
# Aperçus (icônes de la liste des motifs)
# --------------------------------------------------------------------------

_PREV = {"coll": None}
PREVIEW_SIZE = 64


def _swatch(fams, size=PREVIEW_SIZE, unit=None):
    """Image RGBA (size x size) du motif sur un fond sombre arrondi."""
    img = np.zeros((size, size, 4), dtype=np.float32)
    yy, xx = np.mgrid[0:size, 0:size] + 0.5
    r = size * 0.16
    cx = np.clip(xx, r, size - r)
    cy = np.clip(yy, r, size - r)
    inside = (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r
    img[inside] = (0.13, 0.14, 0.16, 1.0)
    if fams is None:
        m = inside & (xx > 7) & (xx < size - 7) & (yy > 7) & (yy < size - 7)
        img[m] = (0.82, 0.84, 0.88, 1.0)
        return img
    from .hatch_engine import segments_2d
    pad = 5.0
    ring = np.array(((pad, pad), (size - pad, pad), (size - pad, size - pad), (pad, size - pad)), dtype=np.float64)
    if unit is None:
        spans = [abs(f[4]) for f in fams if abs(f[4]) > 1e-9]
        per = [sum(abs(x) for x in f[5]) for f in fams if f[5]]
        big = max(spans + per + [1.0])
        unit = max(4.0, min(7.0, 34.0 / big)) if big > 3.0 else 7.0
    try:
        S = segments_2d([ring], fams, unit, 0.0, (size * 0.5, size * 0.5), dot=0.6 / unit, max_segs=20000)
    except Exception:          # motif trop dense : l'aperçu reste vide
        S = np.zeros((0, 2, 2))
    col = np.array((0.86, 0.88, 0.92, 1.0), dtype=np.float32)
    for (x0, y0), (x1, y1) in S:
        n = int(max(abs(x1 - x0), abs(y1 - y0)) * 2) + 2
        xs = np.linspace(x0, x1, n)
        ys = np.linspace(y0, y1, n)
        ix = np.clip(xs.astype(int), 0, size - 1)
        iy = np.clip(ys.astype(int), 0, size - 1)
        img[iy, ix] = col
    return img


def preview_icon(key):
    coll = _PREV["coll"]
    if coll is None:
        return 0
    try:
        if key in coll:
            return coll[key].icon_id
        fams = hatch_families(key)
        if fams is None and key != 'SOLID':
            return 0
        pv = coll.new(key)
        img = _swatch(fams)
        pv.icon_size = (32, 32)
        pv.icon_pixels_float = _swatch(fams, 32, None).ravel()
        pv.image_size = (PREVIEW_SIZE, PREVIEW_SIZE)
        pv.image_pixels_float = img.ravel()
        return pv.icon_id
    except Exception:          # sans interface (tests en arrière-plan) : pas d'icône
        return 0


def register_previews():
    if bpy is None or _PREV["coll"] is not None:
        return
    try:
        from bpy.utils import previews
        _PREV["coll"] = previews.new()
    except (ImportError, RuntimeError, AttributeError):
        _PREV["coll"] = None
    _ITEMS.clear()


def unregister_previews():
    coll = _PREV["coll"]
    _PREV["coll"] = None
    if coll is not None:
        try:
            from bpy.utils import previews
            previews.remove(coll)
        except (RuntimeError, AttributeError, KeyError):
            pass


def forget_preview(key):
    coll = _PREV["coll"]
    if coll is not None and key in coll:
        try:
            del coll[key]
        except (KeyError, RuntimeError):
            pass


def read_pat_file(path):
    with open(os.fsdecode(path), "rb") as fh:
        raw = fh.read()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return parse_pat(raw.decode(enc))
        except UnicodeDecodeError:
            continue
    return []


# --------------------------------------------------------------------------
# Icône « W » du logo (menu Add) : dessinée dans la couleur du texte des menus du thème
# --------------------------------------------------------------------------

LOGO_W = (
    ((502.64, 589.91), (502.64, 429.92), (450.80, 429.92), (397.00, 551.91), (318.32, 313.28), (195.92, 313.28),
     (326.96, 710.72), (449.36, 710.72)),
    ((574.64, 710.72), (697.04, 710.72), (828.08, 313.28), (705.68, 313.28), (627.00, 551.91), (573.20, 429.92),
     (521.36, 429.92), (521.36, 589.91)),
)
_LOGO = {"col": None}


def _inside(x, y, poly):
    ins = np.zeros(x.shape, dtype=bool)
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if y1 == y2:
            continue
        c = (y1 > y) != (y2 > y)
        xs = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
        ins ^= c & (x < xs)
    return ins


def logo_pixels(size=32, color=(0.9, 0.9, 0.9)):
    """Pixels RGBA (prémultipliés, ligne du bas d'abord) du W du logo, lissés."""
    acc = np.zeros((size, size), dtype=np.float64)
    ss = 4
    lo, hi = 195.92, 828.08                 # largeur du W : remplit l'icône avec une petite marge
    span = (hi - lo) / 0.92
    cx, cy = (lo + hi) * 0.5, (313.28 + 710.72) * 0.5
    yy, xx = np.mgrid[0:size, 0:size]
    for oy in range(ss):
        for ox in range(ss):
            X = cx + ((xx + (ox + 0.5) / ss) / size - 0.5) * span
            Y = cy - ((yy + (oy + 0.5) / ss) / size - 0.5) * span       # ligne 0 = bas de l'image
            acc += _inside(X, Y, LOGO_W[0]) | _inside(X, Y, LOGO_W[1])
    acc /= ss * ss
    img = np.zeros((size, size, 4), dtype=np.float32)
    for k in range(3):
        img[..., k] = color[k] * acc
    img[..., 3] = acc
    return img


def logo_icon():
    """icon_value du W (0 si les aperçus ne sont pas disponibles)."""
    coll = _PREV["coll"]
    if coll is None:
        return 0
    try:
        col = tuple(round(float(c), 3) for c in
                    bpy.context.preferences.themes[0].user_interface.wcol_menu_item.text[:3])
    except (AttributeError, IndexError, TypeError):
        col = (0.9, 0.9, 0.9)
    try:
        if "_logo_w" in coll and _LOGO["col"] == col:
            return coll["_logo_w"].icon_id
        if "_logo_w" in coll:
            del coll["_logo_w"]
        pv = coll.new("_logo_w")
        small, big = logo_pixels(32, col), logo_pixels(64, col)
        pv.icon_size = (32, 32)
        pv.icon_pixels_float = small.ravel()
        pv.image_size = (64, 64)
        pv.image_pixels_float = big.ravel()
        _LOGO["col"] = col
        return pv.icon_id
    except Exception:          # sans interface : pas d'icône
        return 0
