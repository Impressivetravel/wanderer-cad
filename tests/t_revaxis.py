# Axe de Revolve hors du plan de construction (retour : « Revolve ne fonctionne pas sur l'axe Z »)
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE, 'harness.py')).read())
exec(open(_os.path.join(_HERE, 'prec_lib.py')).read())
from mathutils import Vector, Matrix
BC = bpy.context
st = BC.scene.dessin
SEC = "?"
def chk(name, ok, meas=""): rec(SEC, name, ok, meas)
r4 = lambda v: tuple(round(x, 4) for x in v)
def same(a, b, tol=1e-6): return all(abs(x - y) <= tol for x, y in zip(a, b))
PIX = 0.15            # un pixel de la vue inclinée, en unités (les positions de souris sont des pixels entiers)
TOP = (rv3d.view_matrix.copy(), rv3d.perspective_matrix.copy(), rv3d.view_rotation.copy())
def view(R, side=False):
    VM2 = Matrix.Translation((0, 0, -50)) @ R
    rv3d.view_matrix = VM2; rv3d.perspective_matrix = WM @ VM2; rv3d.view_rotation = R.to_3x3().transposed().to_quaternion()
    rv3d.is_orthographic_side_view = side
def oblique():
    """Vue orthogonale inclinée de 45° (regard vers +Y et vers le bas) : le rayon de la souris n'est pas parallèle à Z."""
    c = math.sqrt(0.5)
    view(Matrix(((1, 0, 0, 0), (0, c, c, 0), (0, -c, c, 0), (0, 0, 0, 1))))
def front():
    """Vue de face : X à droite, Z en haut, regard vers +Y."""
    view(Matrix(((1, 0, 0, 0), (0, 0, 1, 0), (0, -1, 0, 0), (0, 0, 0, 1))), side=True)
def top():
    rv3d.view_matrix, rv3d.perspective_matrix, rv3d.view_rotation = TOP[0].copy(), TOP[1].copy(), TOP[2].copy()
    rv3d.is_orthographic_side_view = False
def px(P):
    q = m.project_px(rv3d, region, Vector(P)); return (q.x, q.y)
KEY = {'0': 'ZERO', '1': 'ONE', '2': 'TWO', '3': 'THREE', '4': 'FOUR', '5': 'FIVE', '6': 'SIX', '7': 'SEVEN', '8': 'EIGHT', '9': 'NINE', '.': 'PERIOD', '-': 'MINUS'}
class Tool:
    def __init__(self, cls, P0=(0, 0, 0)):
        if isinstance(cls, str): cls = getattr(m, "DESSIN_OT_" + cls)
        self.o = make(cls); self.r = type(self.o).invoke(self.o, ctx, ev('NONE', 'NOTHING', *px(P0))); self.last = None
    def send(self, *evs):
        for e in evs: self.last = type(self.o).modal(self.o, ctx, e)
        return self.last
    def move(self, P): return self.send(ev('MOUSEMOVE', 'NOTHING', *px(P)))
    def click(self, P):
        sx, sy = px(P); return self.send(ev('MOUSEMOVE', 'NOTHING', sx, sy), ev('LEFTMOUSE', 'PRESS', sx, sy), ev('LEFTMOUSE', 'RELEASE', sx, sy))
    def key(self, k, P=(0, 0, 0), **kw): return self.send(ev(k, 'PRESS', *px(P), **kw))
    def typ(self, txt, P=(0, 0, 0)):
        for ch in txt: self.send(ev(KEY[ch], 'PRESS', *px(P), unicode=ch, ascii=ch))
    def prompt(self): return m._CMD["prompt"].get(area.as_pointer(), "") or ""
    def end(self):
        try: self.key('ESC')
        except Exception: pass
        try: type(self.o).cleanup(self.o, ctx)
        except Exception: pass
def built_after(fn):
    before = {x.name for x in bpy.data.objects}; fn(); BC.view_layer.update()
    return [x for x in bpy.data.objects if x.name not in before]
def cpts(o): return [r4(o.matrix_world @ p.co.to_3d()) for p in o.data.splines[0].points]
for k, v in m.OSNAP_DEFAULTS.items(): setattr(st, "osnap_" + k, v)
st.ortho = st.polar = st.grid_snap = False
def poly(name, pts):
    cu = bpy.data.curves.new(name, 'CURVE'); cu.dimensions = '3D'; sp = cu.splines.new('POLY'); sp.points.add(len(pts) - 1)
    for p, q in zip(sp.points, pts): p.co = (*q, 1.0)
    o = bpy.data.objects.new(name, cu); BC.collection.objects.link(o); return o
def scene(axis_line=True):
    clear()
    pr = poly("Profile", [(2, 0, 0), (3, 0, 0), (3, 0, 4), (2, 0, 4)])       # profil dans le plan XZ, à côté de l'axe Z
    ax = poly("Axis", [(0, 0, 0), (0, 0, 5)]) if axis_line else None
    for o in bpy.data.objects: o.select_set(o is pr)
    BC.view_layer.objects.active = pr; BC.view_layer.update(); return pr
def revolved(): return [o for o in bpy.data.objects if o.type == 'MESH' and o.name.startswith("Revolve")]
def shape(o):
    """(rayon min, rayon max autour de Z, z min, z max, étendue en y) du maillage créé."""
    V = [o.matrix_world @ v.co for v in o.data.vertices]
    R = [math.hypot(v.x, v.y) for v in V]
    return (round(min(R), 3), round(max(R), 3), round(min(v.z for v in V), 3), round(max(v.z for v in V), 3), round(max(v.y for v in V) - min(v.y for v in V), 3))
AROUND_Z = (2.0, 3.0, 0.0, 4.0, 6.0)        # anneau de rayons 2 à 3, de z = 0 à 4, large de 6 en y : la révolution autour de Z
def start():
    t = Tool("revolve", (0, 0, 0))
    if getattr(t.o, "selecting", False): t.key('RET')
    def move(P, _m=t.move, **kw):            # les mouvements de souris rapprochés sont mis en attente : on les applique tout de suite
        r = t.send(ev('MOUSEMOVE', 'NOTHING', *px(P), **kw))
        if getattr(t.o, "_pending", None) is not None: t.o.flush_pending(ctx)
        return r
    t.move = move
    return t

# ================= 1. Vue inclinée (comme en perspective) =================
SEC = "incliné"
oblique(); scene(False)
t = start(); t.click((0, 0, 0))
chk("profil sélectionné, premier point de l'axe posé à l'origine", not t.o.selecting and [r4(p) for p in t.o.points] == [(0, 0, 0)], [r4(p) for p in t.o.points])
chk("l'invite annonce les trois axes, la longueur tapée et Entrée (axe perpendiculaire au plan)", "X/Y/Z" in t.prompt() and "length" in t.prompt() and "perpendicular" in t.prompt(), t.prompt())
up = px((0, 0, 5))
t.send(ev('Z', 'PRESS', *up, unicode='z', ascii='z')); t.send(ev('MOUSEMOVE', 'NOTHING', *up))
chk("touche Z : le verrou est accepté (il était ignoré : l'axe restait couché dans le plan)", t.o.lock == 2 and t.o.track_label == "Z locked", (t.o.lock, t.o.track_label))
a, d = t.o.axis_end()
chk("... la souris monte : l'axe est vertical, long d'environ 5", abs(d.x) < 1e-6 and abs(d.y) < 1e-6 and abs(d.z - 5) < 2 * PIX, r4(d))
t.send(ev('LEFTMOUSE', 'PRESS', *up), ev('LEFTMOUSE', 'RELEASE', *up))
chk("clic : deuxième point de l'axe à la verticale du premier", len(t.o.points) == 2 and abs(t.o.points[1].x) < 1e-6 and abs(t.o.points[1].y) < 1e-6 and t.o.points[1].z > 4, [r4(p) for p in t.o.points])
new = built_after(lambda: t.key('RET')); rv = revolved()
chk("Entrée (360°) : un solide de révolution autour de Z (anneau de rayons 2 à 3, de z = 0 à 4)", len(rv) == 1 and shape(rv[0]) == AROUND_Z, [shape(o) for o in rv])
t.end()

scene(True); st.osnap_end = True
t = start(); t.click((0, 0, 0)); t.move((0, 0, 5))
chk("accrochage à l'extrémité haute d'une ligne verticale : le point garde sa hauteur (il était rabattu sur le plan)", t.o.snap_kind is not None and same(t.o.cur, (0, 0, 5)), (t.o.snap_kind, r4(t.o.cur)))
t.click((0, 0, 5))
new = built_after(lambda: t.key('RET')); rv = revolved()
chk("... axe = les deux extrémités de la ligne verticale : révolution autour de Z", len(rv) == 1 and shape(rv[0]) == AROUND_Z, [shape(o) for o in rv])
t.end()

scene(False)
t = start(); t.click((0, 0, 0)); t.move((6, 0, 0)); t.click((6, 0, 0))
new = built_after(lambda: t.key('RET')); rv = revolved()
V = [rv[0].matrix_world @ v.co for v in rv[0].data.vertices] if rv else []
chk("axe dans le plan (le long de X), comme avant : révolution autour de X (x de 2 à 3, rayon 4 autour de X)", len(rv) == 1 and abs(min(v.x for v in V) - 2) < 1e-4 and abs(max(v.x for v in V) - 3) < 1e-4
    and abs(max(math.hypot(v.y, v.z) for v in V) - 4) < 1e-3, len(rv))
t.end()

scene(False)
t = start(); t.click((0, 0, 0)); t.move((-4, -3, 0))
a, d = t.o.axis_end()
chk("sans Maj ni Ortho : l'axe suit la souris dans le plan", same(d, (-4, -3, 0), 2 * PIX), r4(d))
t.move((-4, -3, 0), shift=True); a, d = t.o.axis_end()
chk("Maj : l'axe est ramené sur X", abs(d.y) < 1e-6 and abs(d.z) < 1e-6 and abs(d.x + 4) < 2 * PIX, r4(d))
st.ortho = True; t.move((-1.5, -4, 0)); a, d = t.o.axis_end(); st.ortho = False
chk("mode Ortho (F8) : toujours pris en compte, l'axe est ramené sur Y", abs(d.x) < 1e-6 and abs(d.z) < 1e-6 and abs(d.y + 4) < 2 * PIX, r4(d))
t.end()

# ================= 2. Vue de dessus : la souris ne peut pas désigner de hauteur =================
SEC = "dessus"
top(); scene(False)
t = start(); t.click((0, 0, 0))
t.key('Z', (0, 3, 0)); t.move((0, 3, 0))
chk("Z en vue de dessus : verrou accepté", t.o.lock == 2, t.o.lock)
t.typ("5", (0, 3, 0)); a, d = t.o.axis_end()
chk("... longueur tapée 5 : axe vertical de 5", same(d, (0, 0, 5)), r4(d))
t.key('RET', (0, 3, 0))
chk("Entrée : deuxième point en (0, 0, 5), la saisie est vidée pour l'angle, la commande continue", [r4(p) for p in t.o.points] == [(0, 0, 0), (0, 0, 5)] and not any(t.o.typed) and t.o.lock is None and "angle" in t.prompt(),
    ([r4(p) for p in t.o.points], t.o.typed, t.prompt()[:30]))
t.typ("90", (0, 3, 0)); new = built_after(lambda: t.key('RET', (0, 3, 0))); rv = revolved()
V = [rv[0].matrix_world @ v.co for v in rv[0].data.vertices] if rv else []
ang = [math.degrees(math.atan2(v.y, v.x)) for v in V]
chk("angle tapé 90 : un quart de tour autour de Z", len(rv) == 1 and abs(min(ang)) < 1e-3 and abs(max(ang) - 90) < 1e-3 and shape(rv[0])[:4] == AROUND_Z[:4], (len(rv), round(min(ang), 3) if ang else None, round(max(ang), 3) if ang else None))
t.end()
scene(False)
t = start(); t.click((0, 0, 0)); t.move((-4, 0, 0)); t.typ("2", (-4, 0, 0)); a, d = t.o.axis_end()
chk("sans verrou, longueur tapée 2 : l'axe va vers la souris, long de 2", same(d, (-2, 0, 0)), r4(d))
t.key('RET', (-4, 0, 0)); pts = [r4(p) for p in t.o.points]; new = built_after(lambda: t.key('RET', (-4, 0, 0))); rv = revolved()
chk("... Entrée, Entrée : révolution complète autour de X", pts == [(0, 0, 0), (-2, 0, 0)] and len(rv) == 1, (pts, len(rv)))
t.end()
scene(False)
t = start(); t.click((0, 0, 0)); t.typ("5", (0, 0, 0)); r = t.key('RET', (0, 0, 0))
chk("longueur tapée sans direction (souris sur le premier point, aucun verrou) : rien n'est posé, la commande reste en cours", len(t.o.points) == 1 and 'RUNNING_MODAL' in r and not revolved(), (len(t.o.points), r))
t.end()

# ================= 3. Vue de face : Z est dans le plan =================
SEC = "face"
front(); scene(False)
t = start(); t.click((0, 0, 0)); t.move((0, 0, 5)); t.click((0, 0, 5))
new = built_after(lambda: t.key('RET')); rv = revolved()
chk("vue de face, deux clics le long de Z : révolution autour de Z (inchangé)", len(rv) == 1 and shape(rv[0]) == AROUND_Z, [shape(o) for o in rv])
t.end()

# ================= 4. SubD Revolve hérite du même axe =================
SEC = "SubD"
oblique(); scene(False)
t = Tool("subd_revolve", (0, 0, 0))
if getattr(t.o, "selecting", False): t.key('RET')
t.click((0, 0, 0)); up = px((0, 0, 5))
t.send(ev('Z', 'PRESS', *up, unicode='z', ascii='z')); t.send(ev('MOUSEMOVE', 'NOTHING', *up)); t.send(ev('LEFTMOUSE', 'PRESS', *up), ev('LEFTMOUSE', 'RELEASE', *up))
new = built_after(lambda: t.key('RET'))
ok = len(new) == 1 and new[0].type == 'MESH'
V = [new[0].matrix_world @ v.co for v in new[0].data.vertices] if ok else []
chk("SubD Revolve, Z verrouillé : un objet centré sur l'axe Z, de z = 0 à 4", ok and abs(sum(v.x for v in V) / len(V)) < 1e-3 and abs(sum(v.y for v in V) / len(V)) < 1e-3 and min(v.z for v in V) > -1e-3 and max(v.z for v in V) < 4 + 1e-3,
    (len(new), [o.type for o in new]))
t.end()

# ================= 5. Orient : dresser un objet à la verticale =================
SEC = "Orient"
import bmesh
def bar():
    clear(); me = bpy.data.meshes.new("Bar"); bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1); bmesh.ops.scale(bm, vec=(6, 1, 1), verts=bm.verts)
    bmesh.ops.translate(bm, vec=(3, 0.5, 0.5), verts=bm.verts); bm.to_mesh(me); bm.free()
    b = bpy.data.objects.new("Bar", me); BC.collection.objects.link(b)          # barre de 6 x 1 x 1 couchée le long de X, coin à l'origine
    for o in bpy.data.objects: o.select_set(o is b)
    BC.view_layer.objects.active = b; BC.view_layer.update(); return b
def ext(o):
    V = [o.matrix_world @ v.co for v in o.data.vertices]
    return tuple(round(max(v[i] for v in V) - min(v[i] for v in V), 3) for i in range(3))
oblique(); st.osnap_end = False; b = bar()
for k_ in m.OSNAP_DEFAULTS: setattr(st, "osnap_" + k_, False)
t = Tool("orient", (0, 0, 0))
if getattr(t.o, "selecting", False): t.key('RET')
t.o._gap = 0.0
def omove(P):
    t.send(ev('MOUSEMOVE', 'NOTHING', *px(P)))
    if getattr(t.o, "_pending", None) is not None: t.o.flush_pending(ctx)
omove((0, 0, 0)); t.click((0, 0, 0)); omove((6, 0, 0)); t.click((6, 0, 0))
chk("deux points de référence le long de la barre", [r4(p) for p in t.o.points] == [(0, 0, 0), (6, 0, 0)], [r4(p) for p in t.o.points])
t.send(ev('Z', 'PRESS', *px((-8, -8, 0)), unicode='z', ascii='z'))
chk("cible 1 : pas de verrou (un point libre n'a pas de direction)", t.o.lock is None, t.o.lock)
omove((-8, -8, 0)); t.click((-8, -8, 0)); up = px((-8, -8, 6))
t.send(ev('Z', 'PRESS', *up, unicode='z', ascii='z')); t.send(ev('MOUSEMOVE', 'NOTHING', *up))
if getattr(t.o, "_pending", None) is not None: t.o.flush_pending(ctx)
chk("cible 2 : la touche Z est acceptée (elle était refusée), le point monte à la verticale de la cible 1", t.o.lock == 2 and (t.o.cur - t.o.points[2]).to_2d().length < 1e-6 and t.o.cur.z > 4, (t.o.lock, r4(t.o.cur)))
t.send(ev('LEFTMOUSE', 'PRESS', *up), ev('LEFTMOUSE', 'RELEASE', *up)); BC.view_layer.update()
e = ext(b); V = [b.matrix_world @ v.co for v in b.data.vertices]
chk("clic : la barre est dressée (6 de haut, 1 x 1 au sol), son coin est sur la cible 1", e == (1.0, 1.0, 6.0) and abs(min(v.z for v in V)) < 1e-4 and min((v - Vector((-8, -8, 0))).length for v in V) < PIX, e)
t.end(); top()
for k_, v_ in m.OSNAP_DEFAULTS.items(): setattr(st, "osnap_" + k_, v_)


# ======================================================================================================================
# Suite : les autres commandes qui restaient dans le plan de construction (retour : « sur Rhino, Mirror fonctionne aussi
# en axe Z, en vue perspective »)
# ======================================================================================================================
import json
class T(Tool):
    """Outil lancé, sélection validée ; les mouvements de souris en attente sont appliqués tout de suite."""
    def __init__(self, cls, P0=(0, 0, 0)):
        Tool.__init__(self, cls, P0)
        if getattr(self.o, "selecting", False): self.key('RET', P0)
    def mv(self, P, **kw):
        r = self.send(ev('MOUSEMOVE', 'NOTHING', *px(P), **kw))
        if getattr(self.o, "_pending", None) is not None: self.o.flush_pending(ctx)
        return r
    def cl(self, P):
        self.mv(P); sx, sy = px(P); return self.send(ev('LEFTMOUSE', 'PRESS', sx, sy), ev('LEFTMOUSE', 'RELEASE', sx, sy))
    def k(self, key, P=(0, 0, 0)): return self.send(ev(key, 'PRESS', *px(P), unicode=key.lower(), ascii=key.lower()))
    def info(self): return self.o.compute()[2]
def block(size=(6, 2, 1), corner=(0, 0, 0), name="Block"):
    """Pavé dont un coin est en `corner`, sélectionné."""
    me = bpy.data.meshes.new(name); bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1); bmesh.ops.scale(bm, vec=size, verts=bm.verts)
    bmesh.ops.translate(bm, vec=tuple(c + s_ / 2 for c, s_ in zip(corner, size)), verts=bm.verts); bm.to_mesh(me); bm.free()
    b = bpy.data.objects.new(name, me); BC.collection.objects.link(b)
    for o in bpy.data.objects: o.select_set(o is b)
    BC.view_layer.objects.active = b; BC.view_layer.update(); return b
def box3(o):
    V = [o.matrix_world @ v.co for v in o.data.vertices]
    return tuple(round(min(v[i] for v in V), 3) for i in range(3)), tuple(round(max(v[i] for v in V), 3) for i in range(3))
def snaps(on):
    for k_ in m.OSNAP_DEFAULTS: setattr(st, "osnap_" + k_, False)
    if on: st.osnap_end = st.osnap_vertex = True
def meshes(): return [o for o in bpy.data.objects if o.type == 'MESH']
def iso():
    """Vue orthogonale de trois quarts : aucun des trois plans du monde n'est vu par la tranche."""
    view(Matrix.Rotation(math.radians(-60), 4, 'X') @ Matrix.Rotation(math.radians(-30), 4, 'Z'))

# ================= 6. Revolve : Entrée après le premier point (comme Rhino) =================
SEC = "Revolve Entrée"
snaps(False)
for vname, vfn in (("vue inclinée", oblique), ("vue de dessus", top)):
    vfn(); scene(False)
    t = start(); t.click((0, 0, 0)); t.move((-3, -2, 0)); r = t.key('RET', (-3, -2, 0))
    chk(f"{vname} : Entrée après le premier point = axe par ce point, perpendiculaire au plan de construction (avant : la commande se fermait)",
        'RUNNING_MODAL' in r and len(t.o.points) == 2 and abs(t.o.points[1].x) < 1e-6 and abs(t.o.points[1].y) < 1e-6 and t.o.points[1].z > 0.5, (r, [r4(q) for q in t.o.points]))
    new = built_after(lambda: t.key('RET', (-3, -2, 0))); rv = revolved()
    chk("... Entrée encore : révolution complète autour de Z", len(rv) == 1 and shape(rv[0]) == AROUND_Z, [shape(o) for o in rv])
    t.end()

# ================= 7. Rotate : X / Y / Z choisit l'axe =================
SEC = "Rotate"
oblique(); clear(); b = block()
t = T("rotation"); t.cl((0, 0, 0))
chk("centre posé ; l'invite annonce X / Y / Z", len(t.o.points) == 1 and "X / Y / Z: rotation axis" in t.prompt(), t.prompt()[:120])
t.k('X'); t.mv((0, 3, 0))
chk("touche X : le plan de travail passe par le centre, perpendiculaire à X ; l'axe est annoncé", t.o.axis == 0 and "around X" in t.info() and abs(t.o.cur.x) < 1e-6, (t.o.axis, t.info(), r4(t.o.cur)))
t.typ("90"); new = built_after(lambda: t.key('RET')); BC.view_layer.update()
chk("90 tapé, Entrée : le pavé 6 x 2 x 1 a tourné de 90° autour de X (il occupe maintenant 6 x 1 x 2, au-dessus du sol)", box3(b) == ((0, -1, 0), (6, 0, 2)), box3(b))
t.end()
iso(); clear(); b = block()
t = T("rotation"); t.cl((0, 0, 0)); t.k('X'); t.cl((0, 3, 0)); t.mv((0, 0, 3))
chk("à la souris : référence sur Y, cible sur Z -> angle de 90° autour de X", "90.00" in t.info() and "around X" in t.info(), t.info())
t.cl((0, 0, 3)); BC.view_layer.update()
chk("... clic : même résultat qu'avec l'angle tapé", box3(b) == ((0, -1, 0), (6, 0, 2)), box3(b))
t.end(); oblique()
clear(); b = block()
t = T("rotation"); t.cl((0, 0, 0)); t.k('Y'); t.typ("90"); t.key('RET'); BC.view_layer.update()
chk("touche Y, 90 : le pavé se dresse (6 de haut), comme une rotation de 90° en vue de face", box3(b) == ((-1, 0, 0), (0, 2, 6)), box3(b))
t.end()
clear(); b = block()
t = T("rotation"); t.cl((0, 0, 0)); t.k('X'); t.k('X')
chk("X deux fois : retour au plan de construction", t.o.axis == 2 and "around" not in t.info(), (t.o.axis, t.info()))
t.k('Z'); t.typ("90"); t.key('RET'); BC.view_layer.update()
chk("Z (l'axe du plan de construction) puis 90 : rotation à plat, comme avant", box3(b) == ((-2, 0, 0), (0, 6, 1)), box3(b))
t.end()
clear(); b = block()
t = T("rotation"); t.cl((0, 0, 0)); t.cl((5, 0, 0)); t.k('X')
chk("X après le point de référence : sans effet (l'axe se choisit juste après le centre)", t.o.axis == 2, t.o.axis)
t.end()
top(); clear(); b = block()
t = T("rotation"); t.cl((0, 0, 0)); t.k('X'); t.typ("90"); t.key('RET'); BC.view_layer.update()
chk("vue de dessus : X puis l'angle tapé fonctionne aussi (la souris ne peut pas désigner l'angle, le clavier oui)", box3(b) == ((0, -1, 0), (6, 0, 2)), box3(b))
t.end()

# ================= 8. Array Polar : X / Y / Z choisit l'axe =================
SEC = "Array Polar"
oblique(); clear(); b = block(size=(1, 1, 1), corner=(-0.5, 2.5, -0.5))          # cube centré en (0, 3, 0)
t = T("array_polar"); t.cl((0, 0, 0)); t.k('X')
chk("touche X après le centre : axe du réseau = X", t.o.axis == 0 and "around X" in t.info() and "X / Y / Z" in t.prompt(), (t.o.axis, t.info()))
t.typ("4"); new = built_after(lambda: t.key('RET')); BC.view_layer.update()
cen = sorted(r4(sum((o.matrix_world @ v.co for v in o.data.vertices), Vector()) / len(o.data.vertices)) for o in meshes())
chk("4 éléments sur 360° : quatre cubes autour de X, en (0, ±3, 0) et (0, 0, ±3)", len(cen) == 4 and all(any(same(c, q, 1e-4) for c in cen) for q in ((0, 3, 0), (0, -3, 0), (0, 0, 3), (0, 0, -3))), cen)
t.end()
clear(); b = block(size=(1, 1, 1), corner=(2.5, -0.5, -0.5))
t = T("array_polar"); t.cl((0, 0, 0)); t.typ("4"); t.key('RET'); BC.view_layer.update()
cen = sorted(r4(sum((o.matrix_world @ v.co for v in o.data.vertices), Vector()) / len(o.data.vertices)) for o in meshes())
chk("sans touche d'axe : réseau à plat autour de Z, comme avant", len(cen) == 4 and all(any(same(c, q, 1e-4) for c in cen) for q in ((3, 0, 0), (-3, 0, 0), (0, 3, 0), (0, -3, 0))), cen)
t.end()

# ================= 9. Mirror : X / Y / Z comme XAxis / YAxis / ZAxis de Rhino =================
SEC = "Mirror"
def others(b): return [o for o in meshes() if o is not b]
for key, want, what in (('X', ((2, -5, 1), (4, -3, 2)), "de l'autre côté de l'axe X (y inversé)"), ('Y', ((-4, 3, 1), (-2, 5, 2)), "de l'autre côté de l'axe Y (x inversé)"),
                        ('Z', ((2, 3, -2), (4, 5, -1)), "sous le plan de construction (z inversé)")):
    oblique(); clear(); b = block(size=(2, 2, 1), corner=(2, 3, 1))
    t = T("miroir"); t.mv((8, -8, 0))
    chk(f"l'invite annonce X / Y / Z avant le premier point", "X / Y / Z" in t.prompt(), t.prompt()[:110]) if key == 'X' else None
    new = built_after(lambda: t.k(key, (8, -8, 0)))
    chk(f"touche {key} avant le premier point : copie miroir par l'origine, {what} ; l'original ne bouge pas", len(new) == 1 and box3(new[0]) == want and box3(b) == ((2, 3, 1), (4, 5, 2)),
        [box3(o) for o in new])
    V = new[0].data if new else None
    chk("... la copie n'est pas retournée (échelle positive, volume vu de l'extérieur)", bool(new) and all(s_ > 0 for s_ in new[0].scale) and new[0].matrix_world.determinant() > 0, tuple(new[0].scale) if new else None)
    t.end()
oblique(); clear(); b = block(size=(2, 2, 1), corner=(2, 3, 1))
t = T("miroir"); t.cl((0, 0, 0)); t.k('Z', (3, 3, 0)); t.mv((3, 3, 0))
chk("après le premier point, Z : miroir par rapport au plan parallèle au plan de construction, annoncé", t.o.flat and "plane through" in t.info() and "Z: back" in t.prompt(), (t.o.flat, t.info()))
t.k('Z', (3, 3, 0))
chk("Z encore : retour à la ligne de miroir", not t.o.flat and "Mirror line" in t.info(), t.info())
t.k('Z', (3, 3, 0)); new = built_after(lambda: t.key('RET', (3, 3, 0)))
chk("Z puis Entrée : copie sous le plan (z de -2 à -1)", len(new) == 1 and box3(new[0]) == ((2, 3, -2), (4, 5, -1)), [box3(o) for o in new])
t.end()
clear(); b = block(size=(2, 2, 1), corner=(2, 3, 1)); snaps(True)
t = T("miroir"); t.mv((4, 5, 2))
chk("premier point accroché au coin haut du pavé : il garde sa hauteur", t.o.snap_kind is not None and same(t.o.cur, (4, 5, 2)), (t.o.snap_kind, r4(t.o.cur)))
t.cl((4, 5, 2)); snaps(False); t.k('Z', (8, 8, 0)); new = built_after(lambda: t.cl((8, 8, 0)))
chk("Z puis clic : miroir par rapport au plan z = 2 (dessus du pavé) : la copie est posée dessus, de z = 2 à 3", len(new) == 1 and box3(new[0]) == ((2, 3, 2), (4, 5, 3)), [box3(o) for o in new])
t.end()
clear(); b = block(size=(2, 2, 1), corner=(2, 3, 1))
t = T("miroir"); t.cl((0, 0, 0)); new = built_after(lambda: t.cl((0, -6, 0)))
chk("deux clics le long de Y, comme avant : copie de l'autre côté du plan vertical", len(new) == 1 and box3(new[0]) == ((-4, 3, 1), (-2, 5, 2)), [box3(o) for o in new])
t.end()
clear(); b = block(size=(2, 2, 1), corner=(2, 3, 1))
t = T("miroir"); t.cl((0, 0, 0)); t.k('X', (-6, -1, 0)); t.mv((-6, -1, 0))
chk("X après le premier point : verrou de direction dans le plan, comme avant", t.o.lock == 0 and not t.o.flat, (t.o.lock, t.o.flat))
new = built_after(lambda: t.cl((-6, -1, 0)))
chk("... clic : copie de l'autre côté de la ligne le long de X", len(new) == 1 and box3(new[0]) == ((2, -5, 1), (4, -3, 2)), [box3(o) for o in new])
t.end()
front(); clear(); b = block(size=(2, 2, 1), corner=(2, 3, 1))
t = T("miroir"); t.mv((6, 0, 6)); new = built_after(lambda: t.k('Y', (6, 0, 6)))
chk("vue de face : c'est Y qui sort du plan -> miroir par rapport au plan de la vue (y inversé)", len(new) == 1 and box3(new[0]) == ((2, -5, 1), (4, -3, 2)), [box3(o) for o in new])
t.end()

# ================= 10. Stretch : base et destination en 3D =================
SEC = "Stretch"
def ends(o): return [r4(o.matrix_world @ q.co.to_3d()) for q in o.data.splines[0].points]
oblique(); clear(); snaps(True); ln = poly("Line", [(0, 0, 0), (4, 0, 0)])
for o in bpy.data.objects: o.select_set(True)
BC.view_layer.objects.active = ln; BC.view_layer.update()
t = T("stretch"); snaps(False); t.cl((3, -2, 0)); t.cl((5, 2, 0)); snaps(True); t.cl((4, 0, 0)); snaps(False)
chk("fenêtre puis point de base accroché au bout de la ligne", len(t.o.points) == 3 and same(t.o.points[2], (4, 0, 0)) and "X/Y/Z" in t.prompt(), ([r4(q) for q in t.o.points], t.prompt()[-70:]))
up = (4, 0, 3); t.k('Z', up); t.mv(up)
chk("touche Z à la destination : acceptée (elle était ignorée), le déplacement est vertical", t.o.lock == 2 and abs(t.o.delta().x) < 1e-6 and abs(t.o.delta().y) < 1e-6 and abs(t.o.delta().z - 3) < 2 * PIX, (t.o.lock, r4(t.o.delta())))
t.typ("2.5", up); t.key('RET', up); BC.view_layer.update()
chk("2.5 tapé, Entrée : le bout de la ligne monte de 2,5 ; l'autre bout ne bouge pas", ends(ln) == [(0, 0, 0), (4, 0, 2.5)], ends(ln))
t.end()
clear(); snaps(True); ln = poly("Line", [(0, 0, 2), (4, 0, 2)]); tg = poly("Target", [(8, 3, 5), (9, 3, 5)])
for o in bpy.data.objects: o.select_set(o is ln)
BC.view_layer.objects.active = ln; BC.view_layer.update()
t = T("stretch"); snaps(False); t.cl((3, 1, 0)); t.cl((5, 3, 0)); snaps(True); t.cl((4, 0, 2)); snaps(False)
chk("ligne en hauteur (z = 2) : le point de base accroché garde sa hauteur (il était rabattu sur le plan)", len(t.o.points) == 3 and same(t.o.points[2], (4, 0, 2)), [r4(q) for q in t.o.points])
t.mv((7, 3, 2))
chk("souris libre : la destination est sous le curseur, à la hauteur du point de base (pas de chute vers le plan de construction)", abs(t.o.delta().z) < 1e-6 and same(t.o.delta(), (3, 3, 0), 2 * PIX), r4(t.o.delta()))
snaps(True); t.mv((8, 3, 5))
chk("destination accrochée à un point plus haut : déplacement 3D exact", t.o.snap_kind is not None and same(t.o.delta(), (4, 3, 3)), (t.o.snap_kind, r4(t.o.delta())))
t.cl((8, 3, 5)); snaps(False); BC.view_layer.update()
chk("... clic : le bout de la ligne est sur ce point", ends(ln) == [(0, 0, 2), (8, 3, 5)], ends(ln))
t.end()

# ================= 11. Construction Line : Z =================
SEC = "Construction Line"
for vname, vfn in (("vue inclinée", oblique), ("vue de dessus", top)):
    vfn(); clear()
    t = T("xline", (1, 2, 0)); t.cl((1, 2, 0)); t.k('Z', (1, 5, 0)); t.mv((1, 5, 0))
    chk(f"{vname} : touche Z acceptée (elle était ignorée), ligne annoncée le long de Z", t.o.lock == 2 and t.info() == "Along Z", (t.o.lock, t.info()))
    new = built_after(lambda: t.cl((1, 5, 0)))
    P = cpts(new[0]) if new and new[0].type == 'CURVE' else []
    chk("... clic : une ligne de construction verticale par (1, 2)", len(new) == 1 and len(P) == 2 and all(abs(q[0] - 1) < 2 * PIX and abs(q[1] - 2) < 2 * PIX for q in P) and abs(P[0][2] - P[1][2]) > 100
        and new[0].get("cad_xline"), P)
    t.end()
oblique(); clear()
t = T("xline", (1, 2, 0)); t.cl((1, 2, 0)); new = built_after(lambda: t.cl((6, 4, 0)))
P = cpts(new[0]) if new else []
chk("sans verrou, comme avant : ligne dans le plan (z = 0)", len(new) == 1 and all(abs(q[2]) < 1e-6 for q in P), P[:2])
t.end()

# ================= 12. Dimension : coter une hauteur =================
SEC = "Dimension"
def dim_data(o): return json.loads(o["dessin_dim"])
oblique(); clear(); snaps(True); b = block(size=(2, 2, 2), corner=(0, -2, 0))            # coin bas (2, -2, 0), coin haut (2, -2, 2)
for o in bpy.data.objects: o.select_set(False)
t = T("cotation", (2, -2, 0)); t.cl((2, -2, 0)); t.mv((2, -2, 2))
chk("deuxième point accroché au coin situé à l'aplomb du premier : il garde sa hauteur (avant : rabattu, longueur nulle)", t.o.snap_kind is not None and same(t.o.cur, (2, -2, 2)), (t.o.snap_kind, r4(t.o.cur)))
chk("... la longueur annoncée est la hauteur, 2", "2" in t.info() and t.o.compute()[0] and same(t.o.compute()[0][1], (2, -2, 2)), t.info())
t.cl((2, -2, 2)); snaps(False)
chk("clic : la cote passe dans le plan vertical qui fait face à la vue (X, Z)", t.o.uvn is not None and same(t.o.uvn[0], (1, 0, 0)) and same(t.o.uvn[1], (0, 0, 1)) and same(t.o.uvn[2], (0, 1, 0)), t.o.uvn)
t.mv((5, -2, 2)); prev, guides, info, spec = t.o.compute()
chk("souris déplacée de côté : ligne de cote verticale à x = 5, de z = 0 à 2, longueur 2", spec is not None and abs(spec[1]["length"] - 2) < 1e-6 and len(prev) == 2 and same(prev[0], (5, -2, 0), 2 * PIX) and same(prev[1], (5, -2, 2), 2 * PIX),
    ([r4(q) for q in prev], spec[1]["length"] if spec else None))
new = built_after(lambda: t.cl((5, -2, 2)))
dm = [o for o in new if "dessin_dim" in o.keys()]
chk("clic : la cote est créée, son plan vertical est mémorisé", len(dm) == 1 and same(dim_data(dm[0])["uvn"][2], (0, 1, 0)) and dim_data(dm[0])["mode"] == 0, len(dm))
V = [dm[0].matrix_world @ q.co.to_3d() for sp_ in dm[0].data.splines for q in sp_.points] if dm and dm[0].type == 'CURVE' else []
chk("... son tracé est dans ce plan (y = -2) et couvre la hauteur", bool(V) and all(abs(v.y + 2) < 1e-4 for v in V) and min(v.z for v in V) < 0.3 and max(v.z for v in V) > 1.7, (len(V), round(min((v.z for v in V), default=0), 2), round(max((v.z for v in V), default=0), 2)))
ok = False
try: ok = bool(m.rebuild_dimension(ctx, dm[0]))
except Exception as ex: ok = repr(ex)
chk("... elle se reconstruit quand le style change", ok is True, ok)
chk("la commande reste active et retrouve le plan de construction pour la cote suivante", not t.o.points and t.o.uvn is None and not t.o._upright, (len(t.o.points), t.o.uvn))
t.cl((-6, -6, 0)); t.cl((-2, -6, 0)); t.mv((-4, -8, 0)); prev, guides, info, spec = t.o.compute()
chk("cote suivante à plat, comme avant : longueur 4 dans le plan (z = 0)", spec is not None and abs(spec[1]["length"] - 4) < 2 * PIX and all(abs(q.z) < 1e-6 for q in prev), (spec[1]["length"] if spec else None))
t.end()
clear(); t = T("cotation", (3, 3, 0)); t.cl((3, 3, 0)); up = (3, 3, 4); t.k('Z', up); t.mv(up)
chk("sans rien à accrocher : touche Z acceptée (elle était ignorée), la mesure monte à la verticale", t.o.lock == 2 and abs(t.o.cur.z - 4) < 2 * PIX and (t.o.cur - t.o.points[0]).to_2d().length < 1e-6, (t.o.lock, r4(t.o.cur)))
sx, sy = px(up); t.send(ev('LEFTMOUSE', 'PRESS', sx, sy), ev('LEFTMOUSE', 'RELEASE', sx, sy)); t.mv((6, 3, 4)); prev, guides, info, spec = t.o.compute()
chk("... clic puis souris de côté : cote verticale d'environ 4", t.o._upright and spec is not None and abs(spec[1]["length"] - 4) < 2 * PIX, spec[1]["length"] if spec else None)
t.end(); top()
for k_, v_ in m.OSNAP_DEFAULTS.items(): setattr(st, "osnap_" + k_, v_)

summary()
