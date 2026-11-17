# Cote de rayon sur un congé : l'arc d'un congé fait partie d'une polyligne (Fillet Curve remplace le coin par de petits
# segments), il n'est pas un objet « cercle ». Demandé : pouvoir coter le rayon d'un congé (R). Avant, l'outil Radius /
# Diameter ne trouvait « aucun cercle ou arc sous le curseur » sur un congé ou sur le coin d'un rectangle arrondi.
import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE, 'harness.py')).read())
exec(open(_os.path.join(_HERE, 'prec_lib.py')).read())
from mathutils import Vector
SEC = "?"
def chk(name, ok, meas=""): rec(SEC, name, ok, meas)
bpy.context.scene.dessin.unite_cote = 'SCENE'


def poly(name, pts, closed=False):
    cu = bpy.data.curves.new(name, 'CURVE'); cu.dimensions = '3D'
    sp = cu.splines.new('POLY'); sp.points.add(len(pts) - 1)
    for p, q in zip(sp.points, pts): p.co = (q[0], q[1], q[2], 1.0)
    sp.use_cyclic_u = closed
    ob = bpy.data.objects.new(name, cu); bpy.context.scene.collection.objects.link(ob); bpy.context.view_layer.update()
    return ob
def fonts(): return sorted(o_.data.body for o_ in bpy.data.objects if o_.type == 'FONT')
def num(t): return float(t.lstrip('RØ⌀ ').replace(',', '.'))
def on_arc(cx, cy, r, deg): return (cx + r * math.cos(math.radians(deg)), cy + r * math.sin(math.radians(deg)))
V = lambda *a: Vector(a + (0.0,) * (3 - len(a)))

# ---------------------------------------------------------------- A. polyligne en L, congé de rayon 4
SEC = "congé d'une polyligne"
clear()
P, n = m.round_path([V(-10, 0), V(10, 0), V(10, 12)], False, 4.0, False)       # ce que fait Fillet Curve : coin (10, 0) -> arc de centre (6, 4)
poly("L", P)
chk("Fillet Curve remplace le coin par un arc de petits segments (2,5°), dans la même polyligne", n == 1 and len(P) == 39, (n, len(P)))
a = on_arc(6, 4, 4, -45)
new, r, o = run("cotation_rayon", [C(*a), C(a[0] + 3, a[1] - 3)])
tx = fonts()
chk("Radius / Diameter, clic sur le congé puis position de la cote : une cote « R4 » est créée", len(tx) == 1 and tx[0].startswith("R") and abs(num(tx[0]) - 4.0) < 1e-3, tx)
clear(); poly("L", P)
o = make(m.DESSIN_OT_cotation_rayon)
with contextlib.redirect_stdout(io.StringIO()):
    type(o).invoke(o, ctx, ev('NONE', 'NOTHING', *scr(0, 0)))
    type(o).modal(o, ctx, ev('MOUSEMOVE', 'NOTHING', *scr(*a)))
info = o.circ
chk("au survol : centre (6, 4), rayon 4 exactement, et seul l'arc est surligné (pas les deux droites)", info is not None and near(info[0], (6, 4, 0), 1e-4) and abs(info[1] - 4.0) < 1e-5
    and len(info[5]) == 37 and near(info[5][0], (6, 0, 0), 1e-4) and near(info[5][-1], (10, 4, 0), 1e-4), info and (tuple(np.round(info[0], 4)), round(info[1], 6), len(info[5])))
with contextlib.redirect_stdout(io.StringIO()):
    type(o).modal(o, ctx, ev('MOUSEMOVE', 'NOTHING', *scr(0, 0)))
chk("au survol d'une des deux droites : aucun cercle (ce n'est pas un arc)", o.circ is None)
with contextlib.redirect_stdout(io.StringIO()):
    type(o).modal(o, ctx, ev('MOUSEMOVE', 'NOTHING', *scr(*on_arc(6, 4, 4, -88))))
i2 = o.circ
chk("au survol du tout premier segment du congé (contre la droite) : le même arc", i2 is not None and abs(i2[1] - 4.0) < 1e-5 and len(i2[5]) == 37, i2 and (round(i2[1], 6), len(i2[5])))
try: type(o).cleanup(o, ctx)
except Exception: pass
clear(); poly("L", P)
new, r, o = run("cotation_rayon", [K('D'), C(*a), C(a[0] + 3, a[1] - 3)])
tx = fonts()
chk("touche D (diamètre) : « Ø8 »", len(tx) == 1 and abs(num(tx[0]) - 8.0) < 1e-3 and not tx[0].startswith("R"), tx)
clear(); poly("L", P)
new, r, o = run("cotation_arc", [C(*a), C(a[0] + 2, a[1] - 2)])
tx = fonts()
chk("Arc Length Dimension sur le congé : longueur d'un quart de cercle de rayon 4 (6,283)", len(tx) == 1 and abs(num(tx[0].split()[-1].strip("⌒ ")) - 2 * math.pi) < 0.01, tx)
clear(); poly("L", P)
new, r, o = run("center_mark", [C(*a), C(*a)])
cm = [x for x in bpy.data.objects if x.name != "L"]
ctr = None
if cm:
    pts = [x.matrix_world @ Vector(p.co[:3]) for x in cm if x.type == 'CURVE' for s_ in x.data.splines for p in s_.points]
    pts += [x.matrix_world @ v.co for x in cm if x.type == 'MESH' for v in x.data.vertices]
    if pts: ctr = sum(pts, Vector()) / len(pts)
chk("Center Mark sur le congé : la marque est au centre de l'arc (6, 4)", ctr is not None and (ctr - Vector((6, 4, 0))).length < 0.05, ctr and tuple(round(c, 3) for c in ctr))

# ---------------------------------------------------------------- B. rectangle arrondi (contour fermé, quatre congés)
SEC = "rectangle arrondi"
clear()
R, n = m.round_path([V(0, 0), V(20, 0), V(20, 10), V(0, 10)], True, 2.5, False)
poly("Slot", R, closed=True)
got = []
for (cx, cy, deg) in ((17.5, 2.5, -45), (17.5, 7.5, 45), (2.5, 7.5, 135), (2.5, 2.5, -135)):
    o = make(m.DESSIN_OT_cotation_rayon)
    with contextlib.redirect_stdout(io.StringIO()):
        type(o).invoke(o, ctx, ev('NONE', 'NOTHING', *scr(10, 5)))
        type(o).modal(o, ctx, ev('MOUSEMOVE', 'NOTHING', *scr(*on_arc(cx, cy, 2.5, deg))))
    i_ = o.circ
    got.append(i_ is not None and near(i_[0], (cx, cy, 0), 1e-4) and abs(i_[1] - 2.5) < 1e-5 and len(i_[5]) == 37)
    try: type(o).cleanup(o, ctx)
    except Exception: pass
chk("les quatre coins d'un rectangle arrondi (rayon 2,5) : chacun donne son arc, son centre, R = 2,5", n == 4 and got == [True] * 4, got)
a = on_arc(17.5, 2.5, 2.5, -45)
new, r, o = run("cotation_rayon", [C(*a), C(a[0] + 3, a[1] - 3)])
chk("... la cote créée : « R2.5 »", len(fonts()) == 1 and abs(num(fonts()[0]) - 2.5) < 1e-3, fonts())
o = make(m.DESSIN_OT_cotation_rayon)
with contextlib.redirect_stdout(io.StringIO()):
    type(o).invoke(o, ctx, ev('NONE', 'NOTHING', *scr(10, 5)))
    type(o).modal(o, ctx, ev('MOUSEMOVE', 'NOTHING', *scr(10, 0)))
chk("... au survol d'un côté droit : aucun cercle", o.circ is None)
try: type(o).cleanup(o, ctx)
except Exception: pass

# ---------------------------------------------------------------- C. ce qui ne doit pas être pris pour un arc
SEC = "pas un arc"
clear()
poly("Rect", [V(0, 0), V(20, 0), V(20, 10), V(0, 10)], closed=True)      # (les quatre coins d'un rectangle sont sur un même cercle)
new, r, o = run("cotation_rayon", [C(10, 0), C(12, -3)])
chk("rectangle à angles vifs : aucune cote de rayon", fonts() == [], fonts())
clear()
hexa = [V(*on_arc(0, 0, 8, k * 60)) for k in range(6)]
poly("Hex", hexa, closed=True)
new, r, o = run("cotation_rayon", [C(*((hexa[0] + hexa[1]) / 2)[:2]), C(12, 3)])
chk("hexagone : aucune cote de rayon (des côtés de 60°, pas un arc)", fonts() == [], fonts())

# ---------------------------------------------------------------- D. la découpe de l'arc dans une chaîne de points
SEC = "arc dans une chaîne"
def arc_pts(c, r, d0, d1, n): return [np.array([c[0] + r * math.cos(math.radians(d0 + (d1 - d0) * k / n)), c[1] + r * math.sin(math.radians(d0 + (d1 - d0) * k / n)), 0.0]) for k in range(n + 1)]
arc = arc_pts((0, 0), 5.0, 0, 90, 36)
chain = [np.array([5.0, -30.0, 0.0])] + arc + [np.array([-30.0, 5.0, 0.0])]
chk("droite, quart de cercle, droite : l'arc va du 2e point à l'avant-dernier, où que l'on clique dessus",
    all(m.arc_run(chain, i) == (1, 37) for i in (1, 2, 18, 35, 36)), [m.arc_run(chain, i) for i in (1, 2, 18, 35, 36)])
chk("... un clic sur une des droites : pas d'arc", m.arc_run(chain, 0) is None and m.arc_run(chain, 37) is None)
small = [np.array([5.0, -30.0, 0.0])] + arc_pts((0, 0), 5.0, 0, 7.5, 3) + [np.array([4.957 - 30 * math.sin(math.radians(7.5)), 0.6526 + 30 * math.cos(math.radians(7.5)), 0.0])]
chk("petit congé de 7,5° (3 segments) : reconnu", m.arc_run(small, 2) == (1, 4), m.arc_run(small, 2))
tiny = [np.array([5.0, -30.0, 0.0])] + arc_pts((0, 0), 5.0, 0, 5, 2) + [np.array([-30.0, 30.0, 0.0])]
chk("congé de 5° (2 segments, 3 points) : trop peu de points pour affirmer un arc", m.arc_run(tiny, 1) is None, m.arc_run(tiny, 1))
dshape = arc + [arc[0]]                       # un arc refermé par sa corde
chk("arc refermé par une corde : la corde, bien plus longue que les segments de l'arc, n'en fait pas partie", m.arc_run(dshape, 10) == (0, 36), m.arc_run(dshape, 10))
far = [(np.array(p) + np.array([5000.0, 3000.0, 0.0])).astype(np.float32).astype(np.float64) for p in
       [np.array([1.0, -30.0, 0.0])] + arc_pts((0, 0), 1.0, 0, 90, 36) + [np.array([-30.0, 1.0, 0.0])]]
rn = m.arc_run(far, 18)
fit = m.fit_circle_points(np.array(far)[rn[0]:rn[1] + 1], min_pts=4) if rn else None
chk("congé de rayon 1 à 5 000 unités de l'origine (points en simple précision) : reconnu en entier, rayon à 0,001 près",
    rn == (1, 37) and fit is not None and abs(fit[1] - 1.0) < 1e-3, (rn, fit and round(fit[1], 5)))
two = arc_pts((0, 0), 5.0, 0, 90, 36) + arc_pts((0, 10), 5.0, -90, -180, 36)[1:]        # deux arcs de même rayon, tangents (un S)
chk("deux arcs tangents de même rayon (un S) : chacun le sien", m.arc_run(two, 10) == (0, 36) and m.arc_run(two, 50) == (36, 72), (m.arc_run(two, 10), m.arc_run(two, 50)))

# ---------------------------------------------------------------- E. un cercle entier reste trouvé comme avant
SEC = "cercle entier"
clear()
me = bpy.data.meshes.new("MC"); bm = bmesh.new(); bmesh.ops.create_circle(bm, segments=48, radius=3.0); bm.to_mesh(me); bm.free()
ob = bpy.data.objects.new("MC", me); bpy.context.scene.collection.objects.link(ob); ob.location = (12, 0, 0); bpy.context.view_layer.update()
new, r, o = run("cotation_rayon", [C(15, 0), C(18, 3)])
chk("cercle en maillage (48 arêtes, r = 3) : « R3 », comme avant", len(fonts()) == 1 and abs(num(fonts()[0]) - 3.0) < 1e-3, fonts())
clear()
me = bpy.data.meshes.new("M12"); bm = bmesh.new(); bmesh.ops.create_circle(bm, segments=12, radius=3.0); bm.to_mesh(me); bm.free()
ob = bpy.data.objects.new("M12", me); bpy.context.scene.collection.objects.link(ob); bpy.context.view_layer.update()
new, r, o = run("cotation_rayon", [C(3 * math.cos(math.radians(15)), 3 * math.sin(math.radians(15))), C(5, 3)])
chk("cercle en maillage de 12 côtés : toujours reconnu comme un cercle entier (r = 3 à 2 % près)", len(fonts()) == 1 and abs(num(fonts()[0]) - 3.0) < 0.06, fonts())
summary()
