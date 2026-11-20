# Poignées d'échelle du Gizmo comme dans Rhino : un pointillé qui va du centre jusqu'au bord de l'objet, terminé par un
# petit carré. Elles montrent la largeur et la hauteur de l'objet. (Demande : « faire pareil, et en pointillé ».)
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE, 'harness.py')).read())
exec(open(_os.path.join(_HERE, 'prec_lib.py')).read())
import bmesh, math
from mathutils import Vector, Matrix
BC = bpy.context
SEC = "?"
def chk(name, ok, meas=""): rec(SEC, name, ok, meas)
class GZ(NS): pass
class Group:
    def __init__(self):
        mk = lambda: [GZ(matrix_basis=Matrix.Identity(4), hide=True, select_bias=1.0, reach=None) for _ in range(3)]
        self.gz_move, self.gz_scale, self.gz_rot, self.gz_plane, self.gz_ext, self.gz_cut = mk(), mk(), mk(), mk(), [], []
    place_pulls = m.DESSIN_GGT_gumball.place_pulls
def placed(): g = Group(); m.DESSIN_GGT_gumball.place(g, ctx); return g
def box(dims=(12, 8, 2), loc=(0, 0, 1), name="Box"):
    me = bpy.data.meshes.new(name); bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=dims, verts=bm.verts); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); o.location = loc; BC.collection.objects.link(o)
    for x in bpy.data.objects: x.select_set(x is o)
    BC.view_layer.objects.active = o; BC.view_layer.update(); return o
def tip(gz):
    """Bout de la poignée (monde) : le centre du carré."""
    return gz.matrix_basis @ Vector((0, 0, gz.reach[0]))
def px_len(gz): return gz.reach[0] * m.GUMBALL_PX
r3 = lambda v: tuple(round(x, 3) for x in v)
BC.scene.dessin.gumball = True
K = m.gumball_k(ctx)

SEC = "longueur"
b = box(); g = placed()
chk("X : la poignée s'arrête au bord gauche de l'objet (demi-largeur 6)", (tip(g.gz_scale[0]) - Vector((-6, 0, 1))).length < 0.06, r3(tip(g.gz_scale[0])))
chk("Y : elle s'arrête au bord de l'objet (demi-profondeur 4)", (tip(g.gz_scale[1]) - Vector((0, -4, 1))).length < 0.06, r3(tip(g.gz_scale[1])))
chk("X : 60 pixels à l'écran, Y : 40 pixels", abs(px_len(g.gz_scale[0]) * K - 60) < 0.6 and abs(px_len(g.gz_scale[1]) * K - 40) < 0.6, (px_len(g.gz_scale[0]) * K, px_len(g.gz_scale[1]) * K))
chk("Z (objet mince, 10 pixels) : longueur minimale gardée pour rester saisissable", abs(px_len(g.gz_scale[2]) - m.GB_REACH_MIN) < 0.51, px_len(g.gz_scale[2]))
chk("les flèches de déplacement gardent leur longueur", all(abs(z.matrix_basis.to_scale().x - m.GUMBALL_PX * 0.1 * K) < 1e-6 for z in g.gz_move), [round(z.matrix_basis.to_scale().x, 4) for z in g.gz_move])
chk("les poignées partent à l'opposé des flèches", all(((g.gz_scale[a].matrix_basis.to_3x3() @ Vector((0, 0, 1))).normalized() + (g.gz_move[a].matrix_basis.to_3x3() @ Vector((0, 0, 1))).normalized()).length < 1e-6 for a in range(3)))
# l'objet grandit : la poignée suit
b.scale = (2, 1, 1); BC.view_layer.update(); g = placed()
chk("objet deux fois plus large : la poignée X va au nouveau bord (12)", (tip(g.gz_scale[0]) - Vector((-12, 0, 1))).length < 0.06, r3(tip(g.gz_scale[0])))
b.scale = (1, 1, 1); b.location = (5, 3, 1); BC.view_layer.update(); g = placed()
chk("objet déplacé : la poignée le suit", (tip(g.gz_scale[0]) - Vector((-1, 3, 1))).length < 0.06, r3(tip(g.gz_scale[0])))
# deux objets : le bord de l'ensemble
b.location = (0, 0, 1); b2 = box((2, 2, 2), (-20, 0, 1), "B2")
for x in bpy.data.objects: x.select_set(True)
BC.view_layer.update(); g = placed()
piv = m.gumball_selection(ctx)[0]
chk("deux objets : la poignée X va au bord de l'ensemble (x = -21)", abs(tip(g.gz_scale[0]).x + 21) < 0.06, (r3(tip(g.gz_scale[0])), r3(piv)))
bpy.data.objects.remove(b2)
for x in bpy.data.objects: x.select_set(True)
BC.view_layer.objects.active = b; BC.view_layer.update()

SEC = "centre ailleurs"
# L'origine de l'objet n'est pas au milieu de sa forme : le Gizmo se pose au centre de la forme, pas sur l'origine.
def box_off(dims, loc, shift):
    me = bpy.data.meshes.new("Off"); bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=dims, verts=bm.verts); bmesh.ops.translate(bm, vec=shift, verts=bm.verts); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new("Off", me); o.location = loc; BC.collection.objects.link(o)
    for x in bpy.data.objects: x.select_set(x is o)
    BC.view_layer.objects.active = o; BC.view_layer.update(); return o
def tips(): g = placed(); return [r3(tip(z)) for z in g.gz_scale], g
for label, shift, c in (("origine à un coin de l'objet", (6, 4, 1), (6, 4, 1)), ("origine loin de l'objet", (40, 30, 1), (40, 30, 1))):
    o2 = box_off((12, 8, 2), (0, 0, 0), shift); t, g = tips(); piv = m.gumball_selection(ctx)[0]
    chk(f"{label} : le Gizmo est au centre de la forme, les poignées vont à ses bords",
        (piv - Vector(c)).length < 1e-6 and abs(t[0][0] - (c[0] - 6)) < 0.06 and abs(t[1][1] - (c[1] - 4)) < 0.06, (r3(piv), t))
    bpy.data.objects.remove(o2)
# objet tourné, origine décentrée, Gizmo aligné sur l'objet (Local)
o2 = box_off((12, 8, 2), (3, 2, 0), (6, 4, 1)); o2.rotation_euler = (0, 0, math.radians(30)); BC.view_layer.update()
slot = BC.scene.transform_orientation_slots[0]; old_t = slot.type; slot.type = 'LOCAL'
g = placed(); piv = m.gumball_selection(ctx)[0]
ctr = o2.matrix_world @ Vector((6, 4, 1))
L = [(tip(z) - piv).length for z in g.gz_scale]
chk("objet tourné, origine au coin, alignement Local : centre de la forme, demi-largeur 6 et demi-profondeur 4", (piv - ctr).length < 1e-5 and abs(L[0] - 6) < 0.06 and abs(L[1] - 4) < 0.06, (r3(piv), [round(x, 3) for x in L]))
slot.type = old_t; bpy.data.objects.remove(o2)
# Gizmo déplacé avec Relocate
for x in bpy.data.objects: x.select_set(x is b)
BC.view_layer.objects.active = b; BC.view_layer.update()
st = BC.scene.dessin
def reloc(p): st.gumball_pivot = p; st.gumball_pivot_on = True; return tips()[0]
t = reloc((4, 0, 1))
chk("Relocate, Gizmo décentré dans l'objet : la poignée X va au bord gauche (-6)", abs(t[0][0] + 6) < 0.06 and abs(t[1][1] + 4) < 0.06, t)
t = reloc((6, 4, 1))
chk("Relocate au coin : les poignées traversent l'objet jusqu'aux bords opposés (largeur 12, profondeur 8)", abs(t[0][0] + 6) < 0.06 and abs(t[1][1] + 4) < 0.06, t)
t = reloc((-6, -4, 1))
chk("Relocate au coin opposé (l'objet est tout du côté des flèches) : la poignée garde la taille de l'objet (12 et 8)",
    abs(t[0][0] - (-6 - 12)) < 0.06 and abs(t[1][1] - (-4 - 8)) < 0.06, t)
t = reloc((-20, 0, 1))
chk("Relocate en dehors de l'objet : longueur = distance au bord le plus loin (26)", abs(t[0][0] - (-20 - 26)) < 0.06, t)
# on tire le carré depuis le coin : l'objet grandit depuis ce coin et la poignée suit
st.gumball_pivot = (-6, -4, 1); st.gumball_pivot_on = True
o_, r_ = (lambda: None), None
def op(kind, axis, x, y, **kw):
    o = make(m.DESSIN_OT_gumball); o.kind = kind; o.axis = axis
    r = type(o).invoke(o, ctx, ev('LEFTMOUSE', 'PRESS', *scr(x, y), **kw)); return o, r
def send(o, t, v, x, y, **kw):
    r = type(o).modal(o, ctx, ev(t, v, *scr(x, y), **kw)); BC.view_layer.update(); return r
o, r = op('SCALE', 0, -18, -4); send(o, 'MOUSEMOVE', 'NOTHING', -24, -4); send(o, 'LEFTMOUSE', 'RELEASE', -24, -4)
xs = [(b.matrix_world @ v.co).x for v in b.data.vertices]
t = tips()[0]
chk("on tire ce carré de 12 à 18 : l'objet grandit de 1,5 depuis le coin, la poignée fait sa nouvelle largeur (18)",
    abs(min(xs) + 6) < 1e-4 and abs(max(xs) - 12) < 1e-4 and abs(t[0][0] - (-6 - 18)) < 0.06, (min(xs), max(xs), t))
st.gumball_pivot_on = False
b.scale = (1, 1, 1); b.location = (0, 0, 1); BC.view_layer.update()
# mode Édition : seuls les sommets sélectionnés comptent
for p in b.data.polygons: p.select = False
for e in b.data.edges: e.select = False
for v in b.data.vertices: v.select = v.co.x > 0
bpy.ops.object.mode_set(mode='EDIT'); BC.view_layer.update()
m._GB_EDIT["sig"] = None; m._GB_REACH["sig"] = None
g = placed(); piv = m.gumball_selection(ctx)[0]
chk("mode Édition, face de droite sélectionnée : le Gizmo est sur cette face, la poignée Y va à son bord (4)",
    abs(piv.x - 6) < 1e-5 and abs((tip(g.gz_scale[1]) - piv).length - 4) < 0.06, (r3(piv), r3(tip(g.gz_scale[1]))))
bpy.ops.object.mode_set(mode='OBJECT')
for x in bpy.data.objects: x.select_set(x is b)
BC.view_layer.objects.active = b; BC.view_layer.update(); m._GB_REACH["sig"] = None

SEC = "dessin"
g = placed(); gz = g.gz_scale[0]
rr, vecs = gz.reach
right, up, side = Vector(vecs[0:3]), Vector(vecs[3:6]), Vector(vecs[6:9])
T = m.gb_reach_tris(rr, right, up, side, 1.5)
u = 1.0 / m.GUMBALL_PX
zs = [p[2] for p in T]
dash = [T[i:i + 6] for i in range(0, len(T) - 24, 6)]             # les 4 derniers quads sont le carré
gaps = [round((dash[i + 1][0][2] - dash[i][2][2]) / u, 2) for i in range(len(dash) - 1)]
lens = [round((d[2][2] - d[0][2]) / u, 2) for d in dash]
chk("pointillé : des traits de 3 pixels séparés de 3 pixels, du centre jusqu'au carré", len(dash) >= 5 and set(gaps) == {3.0} and all(abs(l - 3.0) < 1e-6 for l in lens[:-1]) and 0 < lens[-1] <= 3.0,
    (len(dash), sorted(set(gaps)), sorted(set(lens))))
chk("le pointillé commence près du centre et finit au carré, sans le dépasser", abs(min(zs) / u - 7.0) < 1e-6 and max(p[2] for d in dash for p in d) <= rr - m.GB_REACH_SQ * u + 1e-9, (min(zs) / u, rr / u))
sq = T[-24:]
c = Vector((0, 0, rr))
off = [(Vector(p) - c) for p in sq]
chk("carré vide au bout : 4 barres autour du bout, face à la vue", all(abs(o.dot(right.cross(up).normalized())) < 1e-6 for o in off)
    and abs(max(abs(o.dot(right)) for o in off) / u - (m.GB_REACH_SQ + 0.75)) < 1e-6 and abs(max(abs(o.dot(up)) for o in off) / u - (m.GB_REACH_SQ + 0.75)) < 1e-6,
    (max(abs(o.dot(right)) for o in off) / u,))
hole = min(max(abs(o.dot(right)), abs(o.dot(up))) for o in off) / u
chk("... et son centre est vide", hole >= m.GB_REACH_SQ - 0.76, hole)
P = m.gb_reach_pick_tris(rr)
chk("zone cliquable : seulement autour du carré (le pointillé ne se saisit pas)", min(p[2] for p in P) / u >= rr / u - m.GB_REACH_PICK - 1e-6 and len(P) == 36, (min(p[2] for p in P) / u, rr / u))
# très long (zoom) : le nombre de traits reste borné
big = m.gb_reach_tris(1e6 * u, right, up, side, 1.5)
chk("poignée très longue : pointillé borné", len(big) // 6 < 800, len(big) // 6)

SEC = "saisie"
piv = m.gumball_selection(ctx)[0]
def at(world):
    p = m.project_px(rv3d, region, world); return m.gumball_handle_at(ctx, p.x, p.y, region, rv3d)
chk("Alt : le carré au bord de l'objet est la poignée d'échelle X", at(Vector((-6, 0, 1))) == ('SCALE', 0), at(Vector((-6, 0, 1))))
chk("Alt : le milieu du pointillé ne saisit pas l'échelle", at(Vector((-4.2, 0, 1))) != ('SCALE', 0), at(Vector((-4.2, 0, 1))))
# glisser le carré : le bord de l'objet suit la souris
def op(kind, axis, x, y, **kw):
    o = make(m.DESSIN_OT_gumball); o.kind = kind; o.axis = axis
    r = type(o).invoke(o, ctx, ev('LEFTMOUSE', 'PRESS', *scr(x, y), **kw)); return o, r
def send(o, t, v, x, y, **kw):
    r = type(o).modal(o, ctx, ev(t, v, *scr(x, y), **kw)); BC.view_layer.update(); return r
o, r = op('SCALE', 0, -6, 0); send(o, 'MOUSEMOVE', 'NOTHING', -9, 0)
g = placed()
xs = [(b.matrix_world @ v.co).x for v in b.data.vertices]
chk("on tire le carré de 6 à 9 : le bord de l'objet arrive sous la souris, et la poignée va jusqu'à lui", abs(min(xs) + 9) < 1e-4 and abs(tip(g.gz_scale[0]).x + 9) < 0.06, (min(xs), r3(tip(g.gz_scale[0]))))
send(o, 'LEFTMOUSE', 'RELEASE', -9, 0)
g = placed()
chk("après le relâchement : la poignée reste au bord", abs(tip(g.gz_scale[0]).x - min((b.matrix_world @ v.co).x for v in b.data.vertices)) < 0.06, r3(tip(g.gz_scale[0])))

SEC = "réglage"
m.PREF_DEFAULTS["gumball_reach"] = False
g = placed()
chk("réglage décoché : poignées courtes de longueur fixe, comme avant", all(z.reach is None for z in g.gz_scale)
    and all(abs(z.matrix_basis.to_scale().x - m.GUMBALL_PX * 0.98 * 0.1 * K) < 1e-6 for z in g.gz_scale), [z.reach for z in g.gz_scale])
m.PREF_DEFAULTS["gumball_reach"] = True
chk("le réglage est dans les préférences, coché par défaut", m.DessinPreferences.__annotations__["gumball_reach"].keywords["default"] is True if hasattr(m, "DessinPreferences") else True)
summary()
