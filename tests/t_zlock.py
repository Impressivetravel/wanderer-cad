# Verrou d'axe Z sur Polyline (retour d'un utilisateur : « The Z axis lock does not seem to work (pressed Z) on polyline »)
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

# ================= 1. Vue de dessus : Z + longueur tapée =================
SEC = "dessus"
clear()
t = Tool("polyligne", (5, 2, 0)); t.click((5, 2, 0))
chk("premier point posé en (5, 2, 0)", [r4(p) for p in t.o.points] == [(5, 2, 0)], [r4(p) for p in t.o.points])
chk("l'invite annonce les trois axes X/Y/Z", "X/Y/Z" in t.prompt() and t.o.lock_keys() == "X/Y/Z", t.prompt())
t.key('Z', (5, 4, 0)); t.move((5, 4, 0))
chk("touche Z : le verrou est accepté (il était ignoré sans rien dire)", t.o.lock == 2 and t.o.track_label == "Z locked", (t.o.lock, t.o.track_label))
chk("... vue de dessus, souris seule : pas de hauteur désignable, le point reste à l'aplomb", same(t.o.effective_point(), (5, 2, 0)), r4(t.o.effective_point()))
t.typ("3", (5, 4, 0))
chk("... longueur tapée 3 : le segment monte de 3 à la verticale", same(t.o.effective_point(), (5, 2, 3)), r4(t.o.effective_point()))
t.key('RET', (5, 4, 0))
chk("Entrée : point posé en (5, 2, 3), verrou relâché", [r4(p) for p in t.o.points] == [(5, 2, 0), (5, 2, 3)] and t.o.lock is None, ([r4(p) for p in t.o.points], t.o.lock))
t.move((9, 2, 0))
chk("point suivant sans verrou : tracé à la hauteur du dernier point (z = 3)", same(t.o.cur, (9, 2, 3)) and same(t.o.effective_point(), (9, 2, 3)), r4(t.o.cur))
t.click((9, 2, 0))
t.key('Z', (9, 2, 0)); t.typ("-1.5", (9, 2, 0))
chk("Z puis -1.5 : le segment descend de 1,5", same(t.o.effective_point(), (9, 2, 1.5)), r4(t.o.effective_point()))
t.key('RET', (9, 2, 0))
t.key('X', (12, 4, 0)); t.move((12, 4, 0))
chk("verrou X toujours valable : (12, 2, 1.5)", t.o.lock == 0 and same(t.o.cur, (12, 2, 1.5)), r4(t.o.cur))
t.click((12, 4, 0))
new = built_after(lambda: t.key('RET', (12, 4, 0)))
chk("Entrée : une polyligne 3D passant par les 4 points", len(new) == 1 and new[0].data.dimensions == '3D'
    and cpts(new[0]) == [(5, 2, 0), (5, 2, 3), (9, 2, 3), (9, 2, 1.5), (12, 2, 1.5)][:len(cpts(new[0]))] and len(cpts(new[0])) == 5, [cpts(x) for x in new])
t.end()

# ================= 2. Vue inclinée : Z à la souris =================
SEC = "incliné"
clear(); oblique()
chk("vue inclinée : le plan de construction reste le sol (axe Z)", m.drawing_axis(rv3d) == 2)
t = Tool("polyligne", (5, 2, 0)); t.click((5, 2, 0))
p0 = t.o.points[0].copy()
chk("premier point au sol, sous la souris (à un pixel près)", abs(p0.x - 5) < 1e-4 and abs(p0.y - 2) < PIX and abs(p0.z) < 1e-4, r4(p0))
t.key('Z', (5, 2, 3)); t.move((5, 2, 3))
chk("Z verrouillé, souris au-dessus : le curseur monte à la verticale du point", t.o.lock == 2 and abs(t.o.cur.x - p0.x) < 1e-6 and abs(t.o.cur.y - p0.y) < 1e-6 and abs(t.o.cur.z - 3) < PIX, r4(t.o.cur))
z1 = t.o.cur.z
t.move((6.3, 2, 3))
chk("souris décalée sur le côté : le curseur reste sur la verticale", abs(t.o.cur.x - p0.x) < 1e-6 and abs(t.o.cur.y - p0.y) < 1e-6 and abs(t.o.cur.z - z1) < PIX, r4(t.o.cur))
t.click((5, 2, 3))
p1 = t.o.points[1].copy()
chk("clic : second point à la verticale du premier, environ 3 plus haut", len(t.o.points) == 2 and abs(p1.x - p0.x) < 1e-6 and abs(p1.y - p0.y) < 1e-6 and abs(p1.z - 3) < PIX, r4(p1))
t.move((9, 2, 3))
chk("point suivant sans verrou : dans le plan horizontal du dernier point", abs(t.o.cur.z - p1.z) < 1e-6 and abs(t.o.cur.x - 9) < 1e-6, r4(t.o.cur))
t.click((9, 2, 3))
p2 = t.o.points[2].copy()
t.key('Z', (9, 2, 2)); t.move((9, 2, 2)); t.typ("2", (9, 2, 2))
chk("Z, souris en dessous, 2 tapé : descend de 2 exactement", same(t.o.effective_point(), (p2.x, p2.y, p2.z - 2)), r4(t.o.effective_point()))
t.key('RET', (9, 2, 2))
new = built_after(lambda: t.key('RET', (9, 2, 2)))
pts = cpts(new[0]) if new else []
chk("polyligne créée : 4 sommets, deux segments verticaux exacts", len(pts) == 4 and pts[0][:2] == pts[1][:2] and pts[2][:2] == pts[3][:2] and abs(pts[1][2] - pts[2][2]) < 1e-6 and abs(pts[2][2] - pts[3][2] - 2) < 1e-4, pts)
t.end()
# accrochage pendant le verrou Z : on monte jusqu'à la hauteur du point accroché
clear()
em = bpy.data.objects.new("Repere", None); BC.scene.collection.objects.link(em); em.location = (12, 6, 5); BC.view_layer.update()
t = Tool("polyligne", (5, 2, 0)); t.click((5, 2, 0)); p0 = t.o.points[0].copy()
t.key('Z', (12, 6, 5)); t.move((12, 6, 5))
chk("Z verrouillé, souris accrochée à un point situé à z = 5 : le curseur monte exactement à z = 5, à la verticale",
    t.o.snap_kind is not None and same(t.o.cur, (p0.x, p0.y, 5.0)), (r4(t.o.cur), t.o.snap_kind))
t.click((12, 6, 5))
chk("... clic : point posé à (x0, y0, 5)", len(t.o.points) == 2 and same(t.o.points[1], (p0.x, p0.y, 5.0)), [r4(p) for p in t.o.points])
t.end(); top()

# ================= 2 bis. Vue en perspective =================
SEC = "perspective"
clear()
_keep = (rv3d.view_matrix.copy(), rv3d.window_matrix.copy(), rv3d.perspective_matrix.copy(), rv3d.view_rotation.copy(), rv3d.is_perspective, rv3d.view_perspective)
eye, tgt = Vector((14.0, -16.0, 12.0)), Vector((5.0, 2.0, 1.0))
fwd = (tgt - eye).normalized(); right = fwd.cross(Vector((0, 0, 1))).normalized(); up = right.cross(fwd)
Rm = Matrix((right, up, -fwd)).to_4x4()
VMp = Rm @ Matrix.Translation(-eye)
nearp, farp, f = 0.1, 1000.0, 1.0 / math.tan(math.radians(25))
WMp = Matrix(((f, 0, 0, 0), (0, f, 0, 0), (0, 0, -(farp + nearp) / (farp - nearp), -2 * farp * nearp / (farp - nearp)), (0, 0, -1, 0)))
rv3d.view_matrix = VMp; rv3d.window_matrix = WMp; rv3d.perspective_matrix = WMp @ VMp
rv3d.view_rotation = Rm.to_3x3().transposed().to_quaternion(); rv3d.is_perspective = True; rv3d.view_perspective = 'PERSP'
try:
    t = Tool("polyligne", (5, 2, 0)); t.click((5, 2, 0))
    p0 = t.o.points[0].copy()
    chk("perspective : premier point au sol, sous la souris", abs(p0.z) < 1e-4 and (p0 - Vector((5, 2, 0))).length < 0.1, r4(p0))
    t.key('Z', (5, 2, 3)); t.move((5, 2, 3))
    chk("perspective : Z verrouillé, la souris monte le curseur à la verticale du point (vers z = 3)",
        t.o.lock == 2 and abs(t.o.cur.x - p0.x) < 1e-5 and abs(t.o.cur.y - p0.y) < 1e-5 and abs(t.o.cur.z - 3) < 0.1, r4(t.o.cur))
    t.click((5, 2, 3)); p1 = t.o.points[1].copy()
    t.move((8, 4, 3))
    chk("perspective : le point suivant se pose dans le plan horizontal du dernier point", abs(t.o.cur.z - p1.z) < 1e-5 and (t.o.cur - Vector((8, 4, p1.z))).length < 0.1, r4(t.o.cur))
    t.click((8, 4, 3))
    new = built_after(lambda: t.key('RET', (8, 4, 3)))
    pts = cpts(new[0]) if new else []
    chk("perspective : polyligne 3D créée, premier segment vertical", len(pts) == 3 and pts[0][:2] == pts[1][:2] and pts[1][2] > 2.9 and abs(pts[2][2] - pts[1][2]) < 1e-4, pts)
    t.end()
except Exception as e:
    import traceback; traceback.print_exc(); chk("perspective", False, repr(e))
finally:
    rv3d.view_matrix, rv3d.window_matrix, rv3d.perspective_matrix, rv3d.view_rotation, rv3d.is_perspective, rv3d.view_perspective = _keep

# ================= 3. Commandes planes : rien ne change =================
SEC = "planes"
clear()
for nm, lab in (("rectangle", "Rectangle"), ("cercle", "Circle")):
    t = Tool(nm, (5, 2, 0)); t.click((5, 2, 0))
    t.key('Z', (7, 4, 0))
    chk(f"{lab} : Z reste sans effet (la figure est plane)", t.o.lock is None, t.o.lock)
    chk(f"{lab} : l'invite n'annonce plus que les axes utiles (X/Y)", t.o.lock_keys() == "X/Y" and "X/Y/Z" not in t.prompt() and "X/Y" in t.prompt(), t.prompt())
    t.key('X', (7, 4, 0))
    chk(f"{lab} : X fonctionne toujours", t.o.lock == 0, t.o.lock)
    t.end()
chk("Polyline, Curve (points de contrôle, interpolée), Surface par coins : sortie du plan permise le long d'un axe verrouillé",
    all(getattr(m, "DESSIN_OT_" + n).LOCK_3D for n in ("polyligne", "curve_cp", "curve_interp", "srf_corners")))
chk("Sketch et Pen (tracé à main levée, Bézier) : restent dans le plan", not m.DESSIN_OT_sketch.LOCK_3D and not m.DESSIN_OT_pen.LOCK_3D)
# les autres commandes point par point
for nm, kind in (("curve_cp", "NURBS"), ("curve_interp", "BEZIER")):
    clear()
    t = Tool(nm, (5, 2, 0)); t.click((5, 2, 0)); t.click((9, 2, 0))
    t.key('Z', (9, 4, 0)); t.typ("3", (9, 4, 0)); t.key('RET', (9, 4, 0))
    t.click((9, 7, 0)); t.click((5, 7, 0))
    new = built_after(lambda: t.key('RET', (5, 7, 0)))
    sp = new[0].data.splines[0] if new else None
    P = [r4(new[0].matrix_world @ q.co.to_3d()) for q in (sp.bezier_points if sp.type == 'BEZIER' else sp.points)] if sp else []
    chk(f"{getattr(m, 'DESSIN_OT_' + nm).bl_label} : Z + 3 tapé, la courbe ({kind}) passe par (9,2,3) puis continue à z = 3",
        len(new) == 1 and sp.type == kind and new[0].data.dimensions == '3D' and P == [(5, 2, 0), (9, 2, 0), (9, 2, 3), (9, 7, 3), (5, 7, 3)], P)
    t.end()
clear(); oblique()
t = Tool("srf_corners", (5, 2, 0)); t.click((5, 2, 0)); t.click((11, 2, 0))
t.key('Z', (11, 2, 4)); t.move((11, 2, 4)); t.click((11, 2, 4))
new = built_after(lambda: t.click((5, 2, 4)))
V = [new[0].matrix_world @ v.co for v in new[0].data.vertices] if new else []
chk("Surface from Corner Points : un coin monté à la verticale avec Z (souris), la surface a bien ce coin en hauteur",
    len(new) == 1 and len(V) == 4 and len(new[0].data.polygons) == 1 and abs(V[2].x - V[1].x) < 1e-5 and abs(V[2].y - V[1].y) < 1e-5 and abs(V[2].z - 4) < PIX and abs(V[3].z - V[2].z) < 1e-5,
    [r4(v) for v in V])
t.end(); top(); clear()
front()
t = Tool("rectangle", (5, 0, 2)); t.click((5, 0, 2))
chk("vue de face, Rectangle : plan XZ, axes annoncés X/Z", m.drawing_axis(rv3d) == 1 and t.o.lock_keys() == "X/Z", (m.drawing_axis(rv3d), t.o.lock_keys()))
t.key('Y', (7, 0, 4))
chk("... Y (hors du plan) sans effet", t.o.lock is None)
t.end()
t = Tool("polyligne", (5, 0, 2)); t.click((5, 0, 2))
t.key('Y', (7, 0, 4)); t.typ("2.5", (7, 0, 4))
chk("vue de face, Polyline : Y + 2.5 tapé = segment en profondeur de 2,5", t.o.lock == 1 and abs(abs(t.o.effective_point().y - t.o.points[0].y) - 2.5) < 1e-6
    and abs(t.o.effective_point().x - 5) < 1e-6 and abs(t.o.effective_point().z - 2) < 1e-6, r4(t.o.effective_point()))
t.end(); top()

summary()
