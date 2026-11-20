# Blocs : sélection au clic et au cadre, Block Edit sur une copie tournée et mise à l'échelle, blocs imbriqués, BEDIT
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE, 'harness.py')).read())
exec(open(_os.path.join(_HERE, 'prec_lib.py')).read())
import bmesh, math, numpy as np
BC = bpy.context
SEC = "?"
def chk(name, ok, meas=""): rec(SEC, name, ok, meas)
def cube(name, loc, size=2):
    me = bpy.data.meshes.new(name); bm = bmesh.new(); bmesh.ops.create_cube(bm, size=size); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); o.location = loc; BC.collection.objects.link(o); BC.view_layer.update(); return o
clear()
A = cube("A", (0, 0, 1))
L = m.build_polyline(BC, "Trait", [Vector((-1, -3, 0)), Vector((1, -3, 0))], False)
BC.view_layer.update()
d, inst = m.make_block(BC, [A, L], Vector((0, 0, 0)), name="Porte")
inst.location = (10, 0, 0); BC.view_layer.update()
inst2 = m.new_block_instance(BC, d, Matrix.Translation((-10, 0, 0)) @ Matrix.Rotation(math.radians(90), 4, 'Z') @ Matrix.Scale(2, 4))
BC.view_layer.update(); m._VIS.clear() if hasattr(m, "_VIS") else None

SEC = "Sélection"
pk = m.pick_object_at(ctx, area, region, *scr(10, 0))
chk("un clic sur la face d'un bloc prend l'instance", pk is not None and pk[0] is inst, pk and pk[0].name)
pk = m.pick_object_at(ctx, area, region, *scr(-10, 0))
chk("un clic sur la copie tournée et agrandie prend cette copie", pk is not None and pk[0] is inst2, pk and pk[0].name)
pk = m.pick_object_at(ctx, area, region, *scr(10, -3))
chk("un clic sur une courbe du bloc prend l'instance", pk is not None and pk[0] is inst, pk and pk[0].name)
persp = np.array(region_rv3d_(), dtype=np.float64) if False else np.array(rv3d.perspective_matrix, dtype=np.float64)
dg = BC.evaluated_depsgraph_get()
x0, y0 = scr(7, -5); x1, y1 = scr(13, 3)
rect = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
chk("cadre autour du bloc (fenêtre) : pris", m.object_hit_box(inst, dg, persp, region, rect, False))
x0, y0 = scr(9.5, -1); x1, y1 = scr(13, 3)
rect = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
chk("cadre qui couvre une partie : pas en fenêtre, oui en capture", not m.object_hit_box(inst, dg, persp, region, rect, False)
    and m.object_hit_box(inst, dg, persp, region, rect, True))
x0, y0 = scr(12, 2); x1, y1 = scr(14, 4)
rect = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
chk("cadre à côté : rien", not m.object_hit_box(inst, dg, persp, region, rect, True))

SEC = "Block Edit sur une copie tournée"
for o in bpy.data.objects: o.select_set(False)
inst2.select_set(True); BC.view_layer.objects.active = inst2
r = bpy.ops.dessin.block_edit()
st = m.block_edit_state()
ed = bpy.data.collections.get(st["col"])
cA = next(o for o in ed.objects if o.get("wd_block_src") == "A")
chk("la copie éditable est à la place de l'instance (tournée, agrandie)", (cA.matrix_world.translation - Vector((-10, 0, 2))).length < 1e-6
    and abs(cA.matrix_world.to_scale().x - 2) < 1e-6, cA.matrix_world.translation)
cA.location.z += 2                      # monte de 2 dans le monde = 1 dans le bloc (échelle 2)
n = cube("Neuf", (-10, 4, 0), 1); n.users_collection[0].objects.unlink(n) if n.users_collection[0] is not ed else None
if ed not in n.users_collection: ed.objects.link(n)
r = bpy.ops.dessin.block_edit_close()
BC.view_layer.update()
chk("Close : déplacement repris dans le bloc à l'échelle", r == {'FINISHED'} and abs(d.objects["A"].location.z - 2) < 1e-6, d.objects["A"].location)
nn = next((o for o in d.objects if o.name.startswith("Neuf")), None)
chk("Close : nouvel objet entré dans le bloc, à la bonne place", nn is not None and (nn.matrix_world.translation - Vector((2, 0, 0))).length < 1e-6
    and abs(nn.matrix_world.to_scale().x - 0.5) < 1e-6, nn and nn.matrix_world.translation)
chk("l'autre copie suit", any((W.translation - Vector((10, 0, 2))).length < 1e-6 for s_, W in m.instance_parts(inst) if s_.name == "A"))
chk("plus d'édition en cours, collection d'édition retirée", m.block_edit_state()["inst"] is None and bpy.data.collections.get(st["col"]) is None)

SEC = "Blocs imbriqués"
d2, big = m.make_block(BC, [inst], Vector((0, 0, 0)), name="Pièce")
big.location = (0, 40, 0); BC.view_layer.update()
pk = m.pick_object_at(ctx, area, region, *scr(10, 40))
chk("un clic sur un bloc dans un bloc prend le bloc extérieur", pk is not None and pk[0] is big, pk and pk[0].name)
r = bpy.ops.dessin.block_explode() if False else None
for o in bpy.data.objects: o.select_set(False)
big.select_set(True); BC.view_layer.objects.active = big
bpy.ops.dessin.block_explode()
inner = [o for o in BC.view_layer.objects if o.instance_type == 'COLLECTION' and o.instance_collection is d and o.visible_get()]
chk("Explode : le bloc intérieur reste un bloc", any((o.matrix_world.translation - Vector((10, 40, 0))).length < 1e-6 for o in inner),
    [tuple(round(x, 2) for x in o.matrix_world.translation) for o in inner])

SEC = "Double-clic"
for o in bpy.data.objects: o.select_set(False)
i3 = next(o for o in inner if o.visible_get())
i3.select_set(True); BC.view_layer.objects.active = i3
op = make(m.DESSIN_OT_hatch_dblclick)
r = type(op).invoke(op, BC, ev('LEFTMOUSE', 'DOUBLE_CLICK', *scr(0, 0)))
chk("double-clic sur un bloc : Block Edit", r == {'FINISHED'} and m.block_edit_state()["inst"] == i3.name, r)
bpy.ops.dessin.block_edit_close()

SEC = "Commande"

names = " ".join(c[1] for c in getattr(m, "CMD_ACTIONS", ()) if c[0] in ("Block Edit", "Close Block Edit"))
chk("BEDIT et BCLOSE tapés dans la ligne de commande", "bedit" in names.split() and "bclose" in names.split(), names)
summary()
