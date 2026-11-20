# Trim d'une surface (maillage à faces) par une courbe projetée : murs extrudés coupés en vue de côté (rapport GitHub
# « Trim with Fence on an extruded mesh »), faces vues par la tranche, maillage non soudé, Fence / Crossing sur une surface,
# projection en vue perspective, et le sous-menu Select du clic droit.
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE, 'harness.py')).read())
exec(open(_os.path.join(_HERE, 'prec_lib.py')).read())
import bmesh, math, numpy as np
from mathutils import Vector, Matrix
BC = bpy.context
SEC = "?"
def chk(name, ok, meas=""): rec(SEC, name, ok, meas)

OUT = [(0, 0, 0), (10, 0, 0), (10, 6, 0), (5, 6, 0), (5, 9, 0), (0, 9, 0)]
T_ = 0.3
INN = [(T_, T_, 0), (10 - T_, T_, 0), (10 - T_, 6 - T_, 0), (5 - T_, 6 - T_, 0), (5 - T_, 9 - T_, 0), (T_, 9 - T_, 0)]
H_ = 3.0
def wall(hole=True, rot=0):
    """Mur en L (avec ou sans épaisseur) tiré de 3 m par PushPull, comme dans le rapport ; rot : quarts de tour autour de Z."""
    R = Matrix.Rotation(rot * math.pi / 2, 4, 'Z')
    c = Vector((5, 4.5, 0))
    tr = lambda L: np.array([tuple(R @ (Vector(p) - c) + c) for p in L], dtype=float)
    made, _sk = m.planar_surfaces([(tr(OUT), True)] + ([(tr(INN), True)] if hole else []))
    V, F = made[0]
    me = bpy.data.meshes.new('PS'); me.from_pydata([tuple(v) for v in V], [], [tuple(f) for f in F]); me.update()
    ob = bpy.data.objects.new('Planar Surface', me); BC.scene.collection.objects.link(ob)
    BC.view_layer.update()
    r = m.push_pull_mesh(ob, 0, H_)
    assert r == "", r
    BC.view_layer.update()
    return ob
# ligne de coupe légèrement inclinée, dessinée en vue Left (plan YZ), avec un petit retour au bout comme dans le rapport
CUT = [Vector((0, -3.0, 2.2)), Vector((0, -3.0, 2.6)), Vector((0, 12.0, 2.8))]
def line(y): return 2.6 + 0.2 * (y + 3.0) / 15.0
# vue Left : on regarde vers +X ; écran x = -Y, écran y = Z
VML = Matrix(((0, -1, 0, 0), (0, 0, 1, 0), (-1, 0, 0, -50), (0, 0, 0, 1)))
PL = np.array(WM @ VML)
def measure(ob):
    """(faces au-dessus de la coupe, sommets hors de la coupe et hors des sommets d'origine, faces dégénérées, nb faces)."""
    bm = bmesh.new(); bm.from_mesh(ob.data)
    above = sum(1 for f in bm.faces if any(v.co.z > line(v.co.y) + 1e-5 for v in f.verts))
    stray = sum(1 for v in bm.verts if abs(v.co.z - line(v.co.y)) > 1e-5 and abs(v.co.z) > 1e-6 and abs(v.co.z - H_) > 1e-6)
    degen = sum(1 for f in bm.faces if f.calc_area() < 1e-9)
    n = len(bm.faces); zmax = max(v.co.z for v in bm.verts)
    bm.free()
    return above, stray, degen, n, round(zmax, 4)
def side_click(ob, y, z):
    """Point de la surface sous un clic en vue Left (rayon le long de +X)."""
    ok, loc, _n, _i = ob.ray_cast(ob.matrix_world.inverted() @ Vector((-50, y, z)), Vector((1, 0, 0)))
    assert ok
    return loc

SEC = "tranche"
# Les faces parallèles à la vue (vues par la tranche) ont leurs deux croisements au même endroit du contour : la coupe doit
# rester droite (avant : la face était coupée en V jusqu'à son centre, avec des faces en lamelles).
for hole in (True, False):
    for rot in range(4):
        for rev in (False, True):
            ob = wall(hole, rot)
            cut = CUT[::-1] if rev else CUT
            ys = [v.co.y for v in ob.data.vertices]
            r = m.surface_trim(ob, [(cut, False)], PL, side_click(ob, 0.5 * (min(ys) + max(ys)) + 0.4, 2.95))
            above, stray, degen, n, zmax = measure(ob)
            chk(f"mur {'creux' if hole else 'plein'}, tour {rot}, coupe {'<-' if rev else '->'} : tout le haut retiré, coupe droite",
                r is None and above == 0 and stray == 0 and degen == 0 and n > 0, (r, above, stray, degen, n, zmax))
            bpy.data.objects.remove(ob)

SEC = "non soudé"
# Maillage importé dont les faces ne partagent pas leurs arêtes : le haut part quand même en entier.
ob = wall(True)
bm = bmesh.new(); bm.from_mesh(ob.data)
bmesh.ops.split_edges(bm, edges=bm.edges[:])
bm.to_mesh(ob.data); bm.free(); ob.data.update(); BC.view_layer.update()
bm = bmesh.new(); bm.from_mesh(ob.data); loose = all(len(e.link_faces) == 1 for e in bm.edges); bm.free()
chk("préparation : aucune arête partagée", loose)
r = m.surface_trim(ob, [(CUT, False)], PL, side_click(ob, 4.9, 2.95))
above, stray, degen, n, zmax = measure(ob)
chk("faces non soudées : tout le haut retiré", r is None and above == 0 and stray == 0 and n == 24, (r, above, stray, n, zmax))
bpy.data.objects.remove(ob)
# deux murs séparés dans le même objet : seul celui qu'on clique est coupé (comme deux pièces dans Rhino)
ob = wall(False)
bm = bmesh.new(); bm.from_mesh(ob.data)
dup = bmesh.ops.duplicate(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:])
bmesh.ops.translate(bm, vec=Vector((30, 0, 0)), verts=[g for g in dup["geom"] if isinstance(g, bmesh.types.BMVert)])
bm.to_mesh(ob.data); bm.free(); ob.data.update(); BC.view_layer.update()
r = m.surface_trim(ob, [(CUT, False)], PL, side_click(ob, 4.5, 2.95))
bm = bmesh.new(); bm.from_mesh(ob.data)
near = sum(1 for f in bm.faces if f.calc_center_median().x < 20 and any(v.co.z > line(v.co.y) + 1e-5 for v in f.verts))
far = sum(1 for f in bm.faces if f.calc_center_median().x > 20 and any(abs(v.co.z - H_) < 1e-6 for v in f.verts))
bm.free()
chk("deux pièces séparées : la pièce cliquée est coupée, l'autre garde sa hauteur", r is None and near == 0 and far == 7, (r, near, far))
bpy.data.objects.remove(ob)

SEC = "fence"
def wire(name, pts):
    me = bpy.data.meshes.new(name); me.from_pydata([tuple(p) for p in pts], [(i, i + 1) for i in range(len(pts) - 1)], []); me.update()
    o = bpy.data.objects.new(name, me); BC.scene.collection.objects.link(o); return o
def left_view():
    rv3d.view_matrix = VML; rv3d.perspective_matrix = WM @ VML; rv3d.window_matrix = WM
    rv3d.view_rotation = VML.inverted().to_quaternion(); rv3d.is_perspective = False; rv3d.view_perspective = 'ORTHO'
def px(y, z): return (-y * S + W / 2, z * S + H / 2)
def drag(mode, a, b):
    """Trim : on glisse de a à b (monde y, z en vue Left) avec la ligne (Fence) ou le cadre (Crossing)."""
    BC.scene.dessin.trim_mode = mode
    o = make(m.DESSIN_OT_trim)
    r = type(o).invoke(o, ctx, ev('LEFTMOUSE', 'PRESS', *px(*a)))
    if 'RUNNING_MODAL' in r:
        mid = (0.5 * (a[0] + b[0]), 0.5 * (a[1] + b[1]))
        type(o).modal(o, ctx, ev('MOUSEMOVE', 'NOTHING', *px(*mid)))
        type(o).modal(o, ctx, ev('MOUSEMOVE', 'NOTHING', *px(*b)))
        r = type(o).modal(o, ctx, ev('LEFTMOUSE', 'RELEASE', *px(*b)))
    return r, o._reports
saved_draw = (m.draw_fence_cb, m.draw_box_cb)
_add, _rem = bpy.types.SpaceView3D.draw_handler_add, bpy.types.SpaceView3D.draw_handler_remove
left_view()
def scene(hole=True):
    for o in list(bpy.data.objects): bpy.data.objects.remove(o)
    ob = wall(hole); cw = wire("Polyline.001", CUT)
    for o in BC.view_layer.objects: o.select_set(False)
    cw.select_set(True); BC.view_layer.objects.active = cw; BC.view_layer.update()
    return ob, cw
ob, cw = scene()
r, reps = drag('FENCE', (0.5, 2.93), (8.5, 2.93))
above, stray, degen, n, zmax = measure(ob)
chk("Fence tirée dans le haut du mur (au-dessus de la courbe de coupe) : le haut est retiré sur toute la longueur",
    'FINISHED' in r and above == 0 and stray == 0 and degen == 0 and n == 24, (r, reps, above, stray, n, zmax))
chk("la courbe de coupe reste en place (comme dans Rhino)", cw.name in bpy.data.objects and len(cw.data.edges) == 2, len(cw.data.edges))
r2, reps2 = drag('FENCE', (0.5, 2.93), (8.5, 2.93))
chk("même Fence une seconde fois : plus rien à couper, le mur n'est pas touché", 'CANCELLED' in r2 and measure(ob)[3] == 24, (r2, reps2))
ob, cw = scene(False)
r, reps = drag('CROSSING', (2.0, 2.85), (7.0, 2.98))
above, stray, degen, n, zmax = measure(ob)
chk("Crossing posé sur le haut du mur plein : le haut est retiré", 'FINISHED' in r and above == 0 and stray == 0 and n == 7, (r, reps, above, n, zmax))
ob, cw = scene()
r, reps = drag('FENCE', (4.5, 2.0), (4.5, 2.97))            # la ligne traverse la courbe de coupe : le bas puis le haut
n = measure(ob)[3]
chk("Fence qui traverse la courbe de coupe : une seule partie part, l'objet n'est jamais vidé", 'FINISHED' in r and 0 < n < 36, (r, reps, n))
ob, cw = scene()
r, reps = drag('FENCE', (-20.0, 20.0), (-12.0, 20.0))
chk("Fence dans le vide : rien n'est coupé", 'CANCELLED' in r and measure(ob)[3] == 36, (r, reps))

SEC = "perspective"
# Vue en perspective : une courbe plane est projetée perpendiculairement à son plan (Rhino), pas le long de la vue.
persp = NS(is_perspective=True, perspective_matrix=Matrix(((1.2, 0.3, 0, 0), (-0.2, 0.4, 1.1, 0), (0.6, -0.7, 0.3, 20), (0.6, -0.7, 0.3, 21))))
Pp = m.trim_projection([(CUT, False)], persp)
n_ = np.array(Pp)[2, :3]
chk("courbe plane (plan YZ) : projection le long de X, quelle que soit la vue", abs(abs(n_[0]) - 1) < 1e-9 and abs(n_[1]) < 1e-9 and abs(n_[2]) < 1e-9, tuple(np.round(n_, 6)))
for o in list(bpy.data.objects): bpy.data.objects.remove(o)
ob = wall(True)
r = m.surface_trim(ob, [(CUT, False)], Pp, side_click(ob, 4.9, 2.95))
above, stray, degen, n, zmax = measure(ob)
chk("vue perspective : même coupe qu'en vue Left", r is None and above == 0 and stray == 0 and degen == 0 and n == 24, (r, above, stray, n, zmax))
Pl = m.trim_projection([([Vector((0, -3, 2.6)), Vector((0, 12, 2.8))], False)], persp)
chk("une droite seule (pas de plan) : projection le long de la vue", np.allclose(Pl, np.array(persp.perspective_matrix)))
Po = m.trim_projection([(CUT, False)], NS(is_perspective=False, perspective_matrix=WM @ VML))
chk("vue parallèle : projection le long de la vue (inchangé)", np.allclose(Po, PL))

SEC = "menu"
# Sous-menu Select du clic droit : chaque entrée doit être une valeur que Blender connaît (avant : 'MODIFIERS' n'existe pas
# dans object.select_linked, le menu s'arrêtait sur une erreur Python).
class _Op:
    def __init__(self, idname, log): object.__setattr__(self, "_i", idname); object.__setattr__(self, "_l", log)
    def __setattr__(self, k, v): self._l.append((self._i, k, v))
class _Layout:
    def __init__(self): self.log = []
    def operator(self, idname, **k): return _Op(idname, self.log)
    def separator(self, **k): pass
bad = []
lay = _Layout()
m.DESSIN_MT_ctx_select.draw(NS(layout=lay), NS(mode='OBJECT'))
for idname, prop, val in lay.log:
    mod, name = idname.split(".")
    rna = getattr(getattr(bpy.ops, mod), name).get_rna_type()
    p = rna.properties.get(prop)
    if p is None or (p.type == 'ENUM' and val not in {e.identifier for e in p.enum_items}):
        bad.append((idname, prop, val))
chk("clic droit > Select (mode Objet) : toutes les entrées sont valides", not bad and len(lay.log) >= 8, bad or len(lay.log))
summary()
