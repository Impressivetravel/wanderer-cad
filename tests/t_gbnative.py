# Le Gizmo laisse passer les poignées propres à Blender (direction du Sun, cône du Spot, taille de l'Area, focale de la
# caméra) quand elles se superposent à lui. (Retour : « le Gizmo empêche de bouger la tige du Sun ».)
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE, 'harness.py')).read())
exec(open(_os.path.join(_HERE, 'prec_lib.py')).read())
import bmesh
from mathutils import Vector, Matrix
BC = bpy.context
SEC = "?"
def chk(name, ok, meas=""): rec(SEC, name, ok, meas)
class GZ(NS): pass
class Group:
    def __init__(self):
        mk = lambda b: [GZ(matrix_basis=Matrix.Identity(4), hide=True, select_bias=b) for _ in range(3)]
        self.gz_move, self.gz_scale, self.gz_rot, self.gz_plane = mk(1.0), mk(1.0), mk(1.0), mk(1.0)
        self.gz_ext, self.gz_cut = mk(2.0), mk(2.0)
    place_pulls = m.DESSIN_GGT_gumball.place_pulls
def only(*objs):
    for x in bpy.data.objects: x.select_set(x in objs)
    BC.view_layer.objects.active = objs[0] if objs else None; BC.view_layer.update()
def light(kind, loc=(0, 0, 3)):
    o = bpy.data.objects.new(kind.title(), bpy.data.lights.new(kind.title(), kind)); o.location = loc
    BC.collection.objects.link(o); return o
def cube(loc=(4, 0, 1)):
    me = bpy.data.meshes.new("Box"); bm = bmesh.new(); bmesh.ops.create_cube(bm, size=2); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new("Box", me); o.location = loc; BC.collection.objects.link(o); return o
def placed(g=None):
    g = g or Group(); m.DESSIN_GGT_gumball.place(g, ctx); return g
BC.scene.dessin.gumball = True
sun, spot, area, point, box = light('SUN'), light('SPOT', (2, 0, 3)), light('AREA', (4, 0, 3)), light('POINT', (6, 0, 3)), cube()
cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam")); BC.collection.objects.link(cam)
emp = bpy.data.objects.new("Empty", None); BC.collection.objects.link(emp)
handles = lambda g: g.gz_move + g.gz_scale + g.gz_rot + g.gz_plane

SEC = "priorité"
only(box); g = placed()
chk("maillage : le Gizmo reste devant (comme avant)", all(z.select_bias == 1.0 for z in handles(g)) and all(z.select_bias == 2.0 for z in g.gz_ext + g.gz_cut),
    sorted({z.select_bias for z in handles(g)}))
for o in (sun, spot, area, point, cam, emp):
    only(o); g = placed()
    b = sorted({z.select_bias for z in handles(g)}); bp = sorted({z.select_bias for z in g.gz_ext + g.gz_cut})
    chk(f"{o.name} : les poignées de Blender passent devant celles du Gizmo pour le clic", b == [1.0 - m.GB_YIELD] and bp == [2.0 - m.GB_YIELD], (b, bp))
    chk(f"{o.name} : les flèches du Gizmo restent affichées", not any(z.hide for z in g.gz_move), [z.hide for z in g.gz_move])
# le même groupe de poignées suit la sélection : lampe puis maillage
g = Group(); only(sun); placed(g); only(box); placed(g)
chk("lampe puis maillage, même vue : le Gizmo repasse devant", all(z.select_bias == 1.0 for z in handles(g)) and all(z.select_bias == 2.0 for z in g.gz_ext), sorted({z.select_bias for z in handles(g)}))
only(box, sun); BC.view_layer.objects.active = box; g = placed()
chk("maillage actif + lampe sélectionnée : le Gizmo reste devant", all(z.select_bias == 1.0 for z in handles(g)))
only(sun, box); g = placed()
chk("lampe active + maillage sélectionné : les poignées de la lampe passent devant", all(z.select_bias == 1.0 - m.GB_YIELD for z in handles(g)))
chk("recul plus grand que la profondeur d'une scène, ordre entre poignées gardé", m.GB_YIELD >= 1e4 and (2.0 - m.GB_YIELD) > (1.0 - m.GB_YIELD))

SEC = "échelle"
only(sun); g = placed()
chk("Sun seul : pas de poignées d'échelle (elles couvraient le point de direction)", all(z.hide for z in g.gz_scale) and not any(z.hide for z in g.gz_move + g.gz_rot),
    ([z.hide for z in g.gz_scale], [z.hide for z in g.gz_rot]))
sun2 = light('SUN', (0, 3, 3)); only(sun, sun2); g = placed()
chk("deux Sun : pas de poignées d'échelle", all(z.hide for z in g.gz_scale))
for o in (spot, area):
    only(o); g = placed()
    chk(f"{o.name} : l'échelle reste (elle change le cône / la taille)", not all(z.hide for z in g.gz_scale), [z.hide for z in g.gz_scale])
only(sun, box); g = placed()
chk("Sun + maillage : l'échelle reste", not all(z.hide for z in g.gz_scale), [z.hide for z in g.gz_scale])
only(box); g = placed()
chk("maillage : l'échelle reste", not any(z.hide for z in g.gz_scale), [z.hide for z in g.gz_scale])
# Alt maintenu : la détection des poignées par Wanderer ignore aussi l'échelle d'un Sun
only(sun)
p = m.project_px(rv3d, region, Vector(sun.location))
k = m.gumball_k(ctx)
hit = [m.gumball_handle_at(ctx, p.x + dx * m.GUMBALL_PX * 0.6 * k, p.y + dy * m.GUMBALL_PX * 0.6 * k, region, rv3d) for dx, dy in ((-1, 0), (0, -1), (1, 0), (0, 1))]
chk("Sun, Alt : aucune poignée d'échelle détectée, les flèches oui", not any(h and h[0] == 'SCALE' for h in hit) and any(h and h[0] == 'MOVE' for h in hit), hit)
only(box)
p = m.project_px(rv3d, region, Vector(box.location) )
piv = m.gumball_selection(ctx)[0]; p = m.project_px(rv3d, region, piv)
# les poignées d'échelle vont jusqu'au bord de l'objet (au moins GB_REACH_MIN pixels) : on vise le carré du bout
hit = [m.gumball_handle_at(ctx, p.x + dx * m.GB_REACH_MIN * k, p.y + dy * m.GB_REACH_MIN * k, region, rv3d) for dx, dy in ((-1, 0), (0, -1), (1, 0), (0, 1))]
chk("maillage, Alt : les poignées d'échelle sont détectées", any(h and h[0] == 'SCALE' for h in hit), hit)
summary()
