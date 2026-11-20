# Décalage vers l'intérieur d'un contour dont une partie s'effondre (pointes d'un croissant, passage étroit) : avant, le
# décalage était refusé (« Cannot offset: the distance is too large ») ; il garde maintenant les parties valables.
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE, 'harness.py')).read())
exec(open(_os.path.join(_HERE, 'prec_lib.py')).read())
import math, sys
from mathutils import Vector
SEC = "?"
def chk(name, ok, meas=""): rec(SEC, name, ok, meas)
E = [v for k, v in sys.modules.items() if k.endswith(".edges") and hasattr(v, "offset_polyline")][0]
Z = Vector((0, 0, 1))

def arc(c, r, a0, a1, n):
    return [Vector((c[0] + r * math.cos(a0 + (a1 - a0) * i / n), c[1] + r * math.sin(a0 + (a1 - a0) * i / n), 0)) for i in range(n)]

def area(L):
    return 0.5 * sum(L[i].x * L[(i + 1) % len(L)].y - L[(i + 1) % len(L)].x * L[i].y for i in range(len(L)))

def min_dist(L, P):
    best = 1e9
    for q in L:
        for i in range(len(P)):
            a, b = P[i], P[(i + 1) % len(P)]
            ab = b - a
            t = max(0.0, min(1.0, (q - a).dot(ab) / ab.dot(ab)))
            best = min(best, (q - (a + ab * t)).length)
    return best

def offset(P, d):
    Q = E.offset_polyline(P, True, Z, d)
    if E.offset_collapsed(P, True, Q, abs(d)):
        return E.offset_trim(P, True, Z, Q, abs(d)), True
    return [(Q, True)], False

# croissant (contour dans le sens trigonométrique) : grand arc de rayon 2, petit arc de rayon 1.6 décalé
R, r, cx = 2.0, 1.6, 0.9
# points où les cercles se coupent
x = (R * R - r * r + cx * cx) / (2 * cx); y = math.sqrt(R * R - x * x)
aR = math.atan2(y, x); ar = math.atan2(y, x - cx)
outer = arc((0, 0), R, aR, 2 * math.pi - aR, 64)
inner = arc((cx, 0), r, -ar, ar - 2 * math.pi, 64)[::-1]
inner = arc((cx, 0), r, 2 * math.pi - ar, ar, 64)
P = outer + inner
if area(P) < 0: P = P[::-1]

SEC = "Croissant décalé vers l'intérieur"
parts, trimmed = offset(P, 0.05)
chk("petite distance : une boucle (les pointes très fines sont déjà coupées)", len(parts) == 1, len(parts))
parts, trimmed = offset(P, 0.25)
chk("distance qui fait s'effondrer les pointes : plus refusé", trimmed and len(parts) >= 1, (trimmed, len(parts)))
if parts:
    L = parts[0][0]
    chk("... la forme rétrécie reste dans le croissant, à la bonne distance partout", abs(min_dist(L, P) - 0.25) < 0.25 * 0.01, round(min_dist(L, P), 4))
    chk("... elle tourne dans le même sens et ne se recoupe plus", area(L) > 0 and not E._self_crossings(__import__("numpy").array([(q.x, q.y) for q in L]), True)[1], round(area(L), 4))
    chk("... plus petite que le croissant", area(L) < area(P) * 0.8, (round(area(L), 3), round(area(P), 3)))
parts, trimmed = offset(P, 0.9)
chk("distance plus grande que l'épaisseur : tout s'effondre, rien", parts == [], len(parts))

SEC = "Passage étroit : la forme se sépare en deux îlots"
# haltère : deux carrés 2x2 reliés par un couloir de 0,4 de large
pts = [(-3, -1), (-1, -1), (-1, -0.2), (1, -0.2), (1, -1), (3, -1), (3, 1), (1, 1), (1, 0.2), (-1, 0.2), (-1, 1), (-3, 1)]
D = [Vector((a, b, 0)) for a, b in pts]
dense = []
for i in range(len(D)):
    a, b = D[i], D[(i + 1) % len(D)]
    k = max(1, int((b - a).length / 0.1))
    dense += [a.lerp(b, j / k) for j in range(k)]
parts, trimmed = offset(dense, 0.3)
chk("couloir plus étroit que 2 × la distance : deux îlots", trimmed and len(parts) == 2, len(parts))
chk("... chacun à la bonne distance du contour", all(abs(min_dist(L, dense) - 0.3) < 0.003 for L, _c in parts), [round(min_dist(L, dense), 4) for L, _c in parts])
parts, trimmed = offset(dense, 0.1)
chk("couloir assez large : une seule boucle", len(parts) == 1, len(parts))

SEC = "Vers l'extérieur"
parts, trimmed = offset(dense, -0.5)
chk("décalage vers l'extérieur d'une forme creuse : une boucle propre (encoches comblées)", len(parts) == 1 and area(parts[0][0]) > area(dense), len(parts))

SEC = "Commande Offset sur une courbe en croissant"
import contextlib, io
BC = bpy.context
for o_ in list(bpy.data.objects): bpy.data.objects.remove(o_)
cres = m.build_polyline(BC, "Croissant", [Vector((q.x, q.y, 0)) for q in P], True); BC.view_layer.update()
for q in bpy.data.objects: q.select_set(q is cres)
BC.view_layer.objects.active = cres
K = {'0': 'ZERO', '1': 'ONE', '2': 'TWO', '3': 'THREE', '4': 'FOUR', '5': 'FIVE', '.': 'PERIOD'}
def E_(o, *evs):
    r = None
    with contextlib.redirect_stdout(io.StringIO()):
        for e in evs:
            if isinstance(e, tuple) and e[0] == 'm': seq = [ev('MOUSEMOVE', 'NOTHING', *scr(e[1], e[2]))]
            elif isinstance(e, tuple) and e[0] == 't': seq = [ev(K[ch], 'PRESS', *scr(0, 0), unicode=ch, ascii=ch) for ch in e[1]]
            else: seq = [ev(e, 'PRESS', *scr(0, 0))]
            for x in seq:
                r = type(o).modal(o, ctx, x)
                if 'FINISHED' in r or 'CANCELLED' in r: return r
    return r
o = make(m.DESSIN_OT_offset_edge)
with contextlib.redirect_stdout(io.StringIO()):
    type(o).invoke(o, ctx, ev('NONE', 'NOTHING', *scr(0, 0)))
before = set(bpy.data.objects)
r = E_(o, ('m', -1.5, 0.0), ('t', '0.25'), 'RET'); BC.view_layer.update()
new = [q for q in bpy.data.objects if q not in before]
chk("Offset de 0,25 vers l'intérieur : une courbe est créée (avant : « Cannot offset »)", len(new) == 1 and new[0].type == 'CURVE', [q.name for q in new])
if new:
    sp = new[0].data.splines[0]
    pts = [new[0].matrix_world @ Vector(p.co[:3]) for p in sp.points] if sp.type == 'POLY' else [new[0].matrix_world @ bp.co for bp in sp.bezier_points]
    chk("... fermée, à 0,25 du croissant partout", sp.use_cyclic_u and abs(min_dist(pts, P) - 0.25) < 0.004, round(min_dist(pts, P), 4))

summary()
