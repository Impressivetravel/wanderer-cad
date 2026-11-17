# Le Gumball reste à sa place pendant qu'on déplace la sélection (comme dans Rhino) : ses flèches ne suivent plus l'objet
# pendant le glisser ; elles le rejoignent au relâchement. (Retour : « la flèche part pendant que je déplace mon objet ».)
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE, 'harness.py')).read())
exec(open(_os.path.join(_HERE, 'prec_lib.py')).read())
import bmesh
from mathutils import Vector, Matrix
BC = bpy.context
SEC = "?"
def chk(name, ok, meas=""): rec(SEC, name, ok, meas)
r3 = lambda v: tuple(round(x, 3) for x in v)
def cube(loc=(0, 0, 1), size=2):
    me = bpy.data.meshes.new("Box"); bm = bmesh.new(); bmesh.ops.create_cube(bm, size=size); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new("Box", me); o.location = loc; BC.collection.objects.link(o)
    for x in bpy.data.objects: x.select_set(x is o)
    BC.view_layer.objects.active = o; BC.view_layer.update(); return o
class GZ(NS): pass
class Group:
    """Le groupe de poignées, avec de fausses poignées qui notent où on les pose."""
    def __init__(self):
        mk = lambda: [GZ(matrix_basis=Matrix.Identity(4), hide=True) for _ in range(3)]
        self.gz_move, self.gz_scale, self.gz_rot, self.gz_ext, self.gz_cut = mk(), mk(), mk(), [], []
        self.gz_plane = mk()
    place_pulls = m.DESSIN_GGT_gumball.place_pulls
def arrows():
    """Où le groupe pose ses trois flèches de déplacement (origine de chacune) et leur direction."""
    g = Group(); m.DESSIN_GGT_gumball.place(g, ctx); BC.view_layer.update()
    return [r3(z.matrix_basis.translation) for z in g.gz_move], [r3(z.matrix_basis.to_3x3() @ Vector((0, 0, 1))) for z in g.gz_move], [z.hide for z in g.gz_move]
def op(kind, axis, x, y, **kw):
    o = make(m.DESSIN_OT_gumball); o.kind = kind; o.axis = axis
    r = type(o).invoke(o, ctx, ev('LEFTMOUSE', 'PRESS', *scr(x, y), **kw)); return o, r
def send(o, t, v, x, y, **kw):
    r = type(o).modal(o, ctx, ev(t, v, *scr(x, y), **kw)); BC.view_layer.update(); return r
BC.scene.dessin.gumball = True

# ================= 1. Flèche de déplacement =================
SEC = "déplacer"
clear(); b = cube()
P0, D0, H0 = arrows()
chk("au repos : les trois flèches partent du centre de l'objet (0, 0, 1)", P0 == [(0, 0, 1)] * 3 and not any(H0) and m.gumball_frozen(ctx) is None, P0)
o, r = op('MOVE', 0, 1, 0)
chk("clic sur la flèche X : l'opération démarre, les poignées sont figées au point de départ", 'RUNNING_MODAL' in r and m.gumball_frozen(ctx) is not None and r3(m.gumball_frozen(ctx)[0]) == (0, 0, 1), r)
steps = []
for x in (3, 6, 11):
    send(o, 'MOUSEMOVE', 'NOTHING', x, 0)
    steps.append((round(b.matrix_world.translation.x, 3), arrows()[0][0]))
chk("pendant le glisser : l'objet suit la souris (x = 2, 5, 10)...", [s[0] for s in steps] == [2.0, 5.0, 10.0], [s[0] for s in steps])
chk("... et le Gumball l'accompagne, comme dans Rhino (flèches en x = 2, 5, 10)", [s[1] for s in steps] == [(2, 0, 1), (5, 0, 1), (10, 0, 1)], [s[1] for s in steps])
r = send(o, 'LEFTMOUSE', 'RELEASE', 11, 0)
P1, D1, H1 = arrows()
chk("relâchement : l'opération est validée, les flèches rejoignent l'objet en (10, 0, 1)", 'FINISHED' in r and m.gumball_frozen(ctx) is None and P1 == [(10, 0, 1)] * 3 and abs(b.matrix_world.translation.x - 10) < 1e-6, (r, P1))
o, r = op('MOVE', 1, 10, 1); send(o, 'MOUSEMOVE', 'NOTHING', 10, 7); mid = arrows()[0][0]; y_mid = round(b.matrix_world.translation.y, 3)
r = send(o, 'ESC', 'PRESS', 10, 7)
chk("Échap pendant le glisser (le Gumball avait suivi en y = 6) : l'objet revient, les poignées aussi, en (10, 0, 1)", 'CANCELLED' in r and y_mid == 6.0 and mid == (10, 6, 1) and m.gumball_frozen(ctx) is None and arrows()[0] == [(10, 0, 1)] * 3
    and abs(b.matrix_world.translation.y) < 1e-6, (r, y_mid, mid))
o, r = op('MOVE', 0, 11, 0); send(o, 'LEFTMOUSE', 'RELEASE', 11, 0)
for ch, k in (('4', 'FOUR'),): send(o, k, 'PRESS', 11, 0, unicode=ch, ascii=ch)
typing = (round(b.matrix_world.translation.x, 3), arrows()[0][0])
r = send(o, 'RET', 'PRESS', 11, 0)
chk("clic sans glisser puis valeur tapée (4) : pendant la saisie rien ne bouge (Rhino) ; Entrée : l'objet et le Gumball avancent de 4",
    typing == (10.0, (10, 0, 1)) and 'FINISHED' in r and arrows()[0] == [(14, 0, 1)] * 3, (typing, r, arrows()[0][0]))

# ================= 2. Rotation et échelle =================
SEC = "rotation, échelle"
clear(); b = cube(loc=(4, 0, 1)); BC.scene.dessin.gumball_pivot_on = False
slot = BC.scene.transform_orientation_slots[0]; keep_or = slot.type; slot.type = 'LOCAL'
P0, D0, H0 = arrows()
o, r = op('ROTATE', 2, 6, 0); send(o, 'MOUSEMOVE', 'NOTHING', 4, 3, shift=not m.pref("gumball_rot90"))
ang = round(math.degrees(b.matrix_world.to_euler().z), 1)
P1, D1, H1 = arrows()
_rot = [r3(Matrix.Rotation(math.radians(ang), 3, 'Z') @ Vector(d)) for d in D0]
chk("rotation autour de Z, orientation Local : l'objet tourne (90°), et les axes du Gumball tournent avec lui (Rhino)", abs(ang) == 90.0 and D1 == _rot and P1 == P0, (ang, D1[0], D0[0]))
r = send(o, 'LEFTMOUSE', 'RELEASE', 4, 3); P2, D2, H2 = arrows()
chk("relâchement : les axes des poignées suivent maintenant l'objet tourné", 'FINISHED' in r and D2 != D0 and abs(D2[0][0]) < 1e-3 and abs(D2[0][1]) > 1, (D2[0], D0[0]))
slot.type = keep_or
clear(); b = cube(loc=(0, 0, 1)); BC.scene.dessin.gumball_pivot_on = True; BC.scene.dessin.gumball_pivot = (1, 1, 0)
BC.scene.dessin.gumball_pivot_on = False
o, r = op('SCALE', 0, -2, 0); send(o, 'MOUSEMOVE', 'NOTHING', -6, 0)
sx = round(b.matrix_world.to_scale().x, 3); P1 = arrows()[0]
chk("échelle sur X : l'objet s'étire (×3), les poignées ne bougent pas", sx == 3.0 and P1 == [(0, 0, 1)] * 3, (sx, P1[0]))
send(o, 'LEFTMOUSE', 'RELEASE', -6, 0)

# ================= 3. Sécurité : jamais de poignées bloquées =================
SEC = "sécurité"
clear(); b = cube(); o, r = op('MOVE', 0, 1, 0); send(o, 'MOUSEMOVE', 'NOTHING', 6, 0)
class Win(NS): pass
ctx._o['window'] = Win(modal_operators=[NS(bl_idname="DESSIN_OT_gumball")])
chk("l'opération figure parmi les commandes en cours de la fenêtre : poignées figées", m.gumball_frozen(ctx) is not None)
ctx._o['window'] = Win(modal_operators=[NS(bl_idname="DESSIN_OT_selection_boite")])
chk("l'opération a disparu sans prévenir (annulée par Blender) : les poignées sont libérées d'elles-mêmes et rejoignent l'objet", m.gumball_frozen(ctx) is None and arrows()[0] == [(5, 0, 1)] * 3, arrows()[0][0])
ctx._o['window'] = None
m.gumball_freeze(ctx, (1, 2, 3), "DESSIN_OT_selection")
ctx._o['window'] = Win(modal_operators=[NS(bl_idname="DESSIN_OT_selection_boite")])
chk("objet glissé avec l'outil Select : les poignées sont figées tant que ce glisser dure", m.gumball_frozen(ctx) is not None and arrows()[0] == [(1, 2, 3)] * 3, arrows()[0][0])
sb = make(m.DESSIN_OT_selection_boite); sb.area = area; sb._h = None; type(sb).cleanup(sb)
chk("... et libérées dès qu'il se termine", m.gumball_frozen(ctx) is None and arrows()[0] == [(5, 0, 1)] * 3, arrows()[0][0])
ctx._o['window'] = None


# ================= 4. Arcs de rotation en quart de cercle (comme Rhino) =================
# Retour : « pour pivoter ce sont des cercles non entiers, ça permet de mieux cliquer sur l'icône extruder et trim ;
# dans l'actuel c'est une sphère complète »
SEC = "arcs"
P = m.gb_arc_points()
chk("l'arc est un quart de cercle de rayon 1 qui va de -X à -Y dans le repère de sa poignée", all(abs(math.hypot(x, y) - 1) < 1e-9 and x <= 1e-9 and y <= 1e-9 and z == 0 for x, y, z in P)
    and all(abs(u - v) < 1e-9 for u, v in zip(P[0], (-1, 0, 0))) and all(abs(u - v) < 1e-9 for u, v in zip(P[-1], (0, -1, 0))), (P[0], P[-1]))
T = m.gb_arc_tris(0.03)
dist = [abs(math.hypot(math.hypot(x, y) - 1, z) - 0.03) for x, y, z in T]
chk("son tracé est un tube de rayon constant autour de cet arc (visible sous tous les angles) : 24 x 6 x 2 triangles", len(T) == 24 * 6 * 2 * 3 and max(dist) < 1e-9, (len(T), max(dist)))
clear(); b = cube()
g = Group(); m.DESSIN_GGT_gumball.place(g, ctx)
L = g.gz_move[0].matrix_basis.to_scale().x                         # longueur d'une flèche, en unités
AX = [Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))]
piv = Vector((0, 0, 1))
def world(gz, pts): return [gz.matrix_basis @ Vector(q) for q in pts]
ok, worst = True, 1e9
for a in range(3):
    Wp = world(g.gz_rot[a], P); bx, by = AX[(a + 1) % 3], AX[(a + 2) % 3]
    ok = ok and all(abs((w - piv).length - m.GB_ARC_R * L) < 1e-6 and abs((w - piv).dot(AX[a])) < 1e-6 and (w - piv).dot(bx) <= 1e-6 and (w - piv).dot(by) <= 1e-6 for w in Wp)
    for k in range(3):                                              # distance de l'arc à la sphère d'extrusion et au trait de coupe des trois flèches
        for f in (m.GB_DOT_POS, m.GB_BAR_POS):
            worst = min(worst, min((w - (piv + AX[k] * (f * L))).length for w in Wp))
chk("chaque arc est dans le plan perpendiculaire à son axe, du côté opposé aux deux flèches (entre les poignées d'échelle)", ok and not any(z.hide for z in g.gz_rot), ok)
old = abs(0.62 - m.GB_DOT_POS) * L
chk("... il passe loin de la sphère d'extrusion et du trait de coupe : au moins 60 px, contre 11 px pour l'ancien cercle entier", worst * S > 60 and old * S < 12, (round(worst * S, 1), round(old * S, 1)))
hit = lambda P3: m.gumball_handle_at(ctx, *scr(P3[0], P3[1]), region, rv3d)
c45 = math.sqrt(0.5) * m.GB_ARC_R * L
chk("clic au milieu de l'arc bleu (entre -X et -Y) : rotation autour de Z", hit((-c45, -c45)) == ('ROTATE', 2), hit((-c45, -c45)))
chk("clic à l'endroit où passait l'ancien cercle, entre les flèches X et Y : plus de rotation", hit((c45, c45)) is None, hit((c45, c45)))
chk("la sphère d'extrusion et le trait de coupe de la flèche X ne sont plus sous une poignée de rotation", hit((m.GB_DOT_POS * L, 0)) == ('MOVE', 0) and hit((m.GB_BAR_POS * L, 0)) == ('MOVE', 0), (hit((m.GB_DOT_POS * L, 0)), hit((m.GB_BAR_POS * L, 0))))

# ================= 5. Carré de déplacement dans un plan =================
SEC = "plan"
Q = m.gb_plane_quad()
ok = True
for a in range(3):
    Wp = world(g.gz_plane[a], Q); bx, by = AX[(a + 1) % 3], AX[(a + 2) % 3]
    ok = ok and all(abs((w - piv).dot(AX[a])) < 1e-6 and m.GB_PLANE_LO * L - 1e-6 <= (w - piv).dot(bx) <= m.GB_PLANE_HI * L + 1e-6
                    and m.GB_PLANE_LO * L - 1e-6 <= (w - piv).dot(by) <= m.GB_PLANE_HI * L + 1e-6 for w in Wp)
chk("trois carrés, chacun dans l'angle de deux flèches (de 20 % à 34 % de leur longueur), dans leur plan ; ils sont affichés", ok and len(g.gz_plane) == 3 and not any(z.hide for z in g.gz_plane), ok)
near = min((Vector(q) * L - Vector((f * L, 0, 0))).length for q in Q for f in (m.GB_DOT_POS, m.GB_BAR_POS))
chk("... à plus de 15 px de la sphère d'extrusion et du trait de coupe", near * S > 15, round(near * S, 1))
mid = (m.GB_PLANE_LO + m.GB_PLANE_HI) / 2 * L
chk("clic au milieu du carré entre X et Y : déplacement dans le plan XY", hit((mid, mid)) == ('PLANE', 2), hit((mid, mid)))
o, r = op('PLANE', 2, mid, mid)
chk("le déplacement démarre, les poignées sont figées", 'RUNNING_MODAL' in r and m.gumball_frozen(ctx) is not None, r)
send(o, 'MOUSEMOVE', 'NOTHING', mid + 5, mid + 3); loc = r3(b.matrix_world.translation); lab = o.label()
chk("glisser de (5, 3) : l'objet suit dans le plan XY, sans changer de hauteur ; le Gumball l'accompagne", loc == (5, 3, 1) and arrows()[0] == [(5, 3, 1)] * 3 and "XY plane" in lab, (loc, lab))
r = send(o, 'LEFTMOUSE', 'RELEASE', mid + 5, mid + 3)
chk("relâchement : validé, les poignées rejoignent l'objet", 'FINISHED' in r and arrows()[0] == [(5, 3, 1)] * 3 and r3(b.matrix_world.translation) == (5, 3, 1), (r, arrows()[0][0]))
o, r = op('PLANE', 2, 5 + mid, 3 + mid); r = send(o, 'LEFTMOUSE', 'RELEASE', 5 + mid, 3 + mid)
chk("clic sans glisser sur le carré : rien ne bouge, pas de saisie de valeur", 'CANCELLED' in r and r3(b.matrix_world.translation) == (5, 3, 1) and m.gumball_frozen(ctx) is None, r)
o, r = op('PLANE', 2, 5 + mid, 3 + mid); send(o, 'MOUSEMOVE', 'NOTHING', 9, 9); r = send(o, 'ESC', 'PRESS', 9, 9)
chk("Échap pendant le glisser : l'objet revient", 'CANCELLED' in r and r3(b.matrix_world.translation) == (5, 3, 1), r3(b.matrix_world.translation))
o, r = op('PLANE', 0, 5, 3)
chk("vue de dessus, plan YZ vu par la tranche : le déplacement ne démarre pas (rien à désigner)", 'CANCELLED' in r and m.gumball_frozen(ctx) is None, r)
bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='SELECT'); BC.view_layer.update()
bm = bmesh.from_edit_mesh(b.data); z0 = sorted(round((b.matrix_world @ v.co).x, 3) for v in bm.verts)
o, r = op('PLANE', 2, 5 + mid, 3 + mid); send(o, 'MOUSEMOVE', 'NOTHING', 5 + mid + 2, 3 + mid); r = send(o, 'LEFTMOUSE', 'RELEASE', 5 + mid + 2, 3 + mid)
bm = bmesh.from_edit_mesh(b.data); z1 = sorted(round((b.matrix_world @ v.co).x, 3) for v in bm.verts)
chk("mode Édition : les sommets sélectionnés se déplacent dans le plan (+2 en X)", 'FINISHED' in r and all(abs(q - p - 2) < 1e-4 for p, q in zip(z0, z1)), (z0[:2], z1[:2]))
bpy.ops.object.mode_set(mode='OBJECT')

# ================= Bulle de saisie (clic sur une poignée, puis on tape la valeur) =================
SEC = "bulle"
clear(); b = cube()
o, r = op('MOVE', 1, 0, 3); send(o, 'LEFTMOUSE', 'RELEASE', 0, 3)
d = m._VBUBBLE["data"]
chk("clic sans glisser sur la flèche Y : la bulle s'ouvre, « Distance to move in Y », Y dans la couleur de l'axe",
    d is not None and "".join(t for t, _c, _b in d[1]) == "Distance to move in Y" and d[1][1][1] is not None and d[2] == "", d and d[1])
g = Group(); m.DESSIN_GGT_gumball.place(g, ctx)
chk("pendant la saisie, seules les flèches de déplacement restent (comme Rhino)", not any(z.hide for z in g.gz_move) and all(z.hide for z in g.gz_scale + g.gz_rot + getattr(g, "gz_plane", [])),
    ([z.hide for z in g.gz_scale], [z.hide for z in g.gz_rot]))
t0 = m._VBUBBLE["t0"]
chk("petite animation d'apparition : elle commence à 0, finit à 1 en un peu plus d'un dixième de seconde", m.vbubble_pop(t0) == 0.0 and 0 < m.vbubble_pop(t0 + 0.05) < 1 and m.vbubble_pop(t0 + m.VBUBBLE_POP) == 1.0)
for ch, k in (('2', 'TWO'), ('5', 'FIVE')): send(o, k, 'PRESS', 0, 3, unicode=ch, ascii=ch)
chk("... ce qu'on tape s'y affiche (25), sans unité", m._VBUBBLE["data"] is not None and m._VBUBBLE["data"][2] == "25", m._VBUBBLE["data"] and m._VBUBBLE["data"][2])
r = send(o, 'RET', 'PRESS', 0, 3)
chk("Entrée : la valeur est appliquée et la bulle se ferme", 'FINISHED' in r and m._VBUBBLE["data"] is None and m._VBUBBLE["handle"] is None, r)
o, r = op('ROTATE', 2, 6, 0); send(o, 'LEFTMOUSE', 'RELEASE', 6, 0)
chk("rotation : « Angle to rotate around Z »", m._VBUBBLE["data"] is not None and "".join(t for t, _c, _b in m._VBUBBLE["data"][1]) == "Angle to rotate around Z")
r = send(o, 'ESC', 'PRESS', 6, 0)
chk("Échap : la bulle se ferme", m._VBUBBLE["data"] is None)
o, r = op('MOVE', 0, 3, 0); send(o, 'LEFTMOUSE', 'RELEASE', 3, 0)
x0 = round(b.matrix_world.translation.x, 3)
for ch, k in (('7', 'SEVEN'),): send(o, k, 'PRESS', 3, 0, unicode=ch, ascii=ch)
r = send(o, 'LEFTMOUSE', 'PRESS', 30, 30)
g = Group(); m.DESSIN_GGT_gumball.place(g, ctx)
chk("clic ailleurs pendant la saisie : abandon (l'objet n'a pas bougé), le clic agit ensuite normalement, le Gumball redevient complet",
    'CANCELLED' in r and 'PASS_THROUGH' in r and round(b.matrix_world.translation.x, 3) == x0 and m._VBUBBLE["data"] is None and not any(z.hide for z in g.gz_rot), (r, round(b.matrix_world.translation.x, 3), x0))

summary()
