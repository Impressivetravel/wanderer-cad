# Clic de sélection dans une scène avec des blocs lourds (palmiers, chaises...) : avant, chaque clic dans le vide relisait
# les maillages de toutes les instances (0,5 s chez l'utilisateur, la sélection « saccadait »). La géométrie d'une
# définition est maintenant lue une fois, et les blocs loin du clic ne sont pas lus du tout.
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE, 'harness.py')).read())
exec(open(_os.path.join(_HERE, 'prec_lib.py')).read())
import sys, time, bmesh
BC = bpy.context
SEC = "?"
def chk(name, ok, meas=""): rec(SEC, name, ok, meas)
SEL = [v for k, v in sys.modules.items() if k.endswith(".selection") and hasattr(v, "pick_object_at")][0]
for o in list(bpy.data.objects): bpy.data.objects.remove(o)

# définition lourde : une grille de ~250 000 sommets, dans une collection hors scène
defc = bpy.data.collections.new("Palm")
me = bpy.data.meshes.new("PalmMesh"); bm = bmesh.new()
bmesh.ops.create_grid(bm, x_segments=500, y_segments=500, size=1.5); bm.to_mesh(me); bm.free()
po = bpy.data.objects.new("PalmMesh", me); defc.objects.link(po)
insts = []
for i, (x, y) in enumerate([(-30, -30), (-30, 30), (30, -30), (30, 30), (-30, 0), (30, 0), (0, 30), (0, -30)]):
    e = bpy.data.objects.new(f"Palm.{i}", None); e.instance_type = 'COLLECTION'; e.instance_collection = defc
    e.location = (x, y, 0); BC.collection.objects.link(e); insts.append(e)
BC.view_layer.update()

def pick(x, y):
    t = time.perf_counter()
    h = SEL.pick_object_at(ctx, area, region, *scr(x, y))
    return h, (time.perf_counter() - t) * 1000

for shading in ('SOLID', 'WIREFRAME'):
    SEC = f"Clic dans le vide ({shading})"
    space.shading.type = shading
    if hasattr(SEL, "_INST_GEOM"): SEL._INST_GEOM["epoch"] = None
    h1, t1 = pick(10, 10)
    h2, t2 = pick(12, 8)
    h3, t3 = pick(-12, 9)
    chk("rien n'est touché", h1 is None and h2 is None and h3 is None, (h1, h2, h3))
    chk("clics suivants rapides (blocs loin du clic ignorés, définition gardée)", t2 < 60 and t3 < 60, (round(t1), round(t2), round(t3)))

SEC = "Clic sur un bloc"
space.shading.type = 'WIREFRAME'
h, t = pick(30.75, 30.0)                  # sur une ligne de la grille du palmier en (30, 30)
chk("le bloc sous le curseur est bien pris (filaire : ses arêtes)", h is not None and h[0].name == "Palm.3", (h and h[0].name, round(t)))
space.shading.type = 'SOLID'
h, t = pick(30.2, 30.3)
chk("en solide aussi", h is not None and h[0].name == "Palm.3", (h and h[0].name, round(t)))

SEC = "Le cache suit les changements"
insts[3].location.x += 100; BC.view_layer.update()
m = [v for k, v in sys.modules.items() if k.endswith(".snapping") and hasattr(v, "_GEOM")][0]
m._GEOM["epoch"] += 1                     # (Blender le fait au déplacement : mise à jour de la scène)
h, _t = pick(30.75, 30.0)
chk("bloc déplacé : plus touché à son ancienne place", h is None or h[0].name != "Palm.3", h and h[0].name)
h, _t = pick(130.75, 30.0)
chk("... touché à la nouvelle", h is not None and h[0].name == "Palm.3", h and h[0].name)
space.shading.type = 'SOLID'

summary()
