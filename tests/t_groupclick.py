# Clic sur un objet d'un groupe : tout le groupe est sélectionné (et pas un seul objet), tant qu'il n'est pas dégroupé.
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE, 'harness.py')).read())
exec(open(_os.path.join(_HERE, 'prec_lib.py')).read())
import bmesh
BC = bpy.context
SEC = "groupe"
def chk(name, ok, meas=""): rec(SEC, name, ok, meas)
def cube(name, loc):
    me = bpy.data.meshes.new(name); bm = bmesh.new(); bmesh.ops.create_cube(bm, size=2); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); o.location = loc; BC.collection.objects.link(o); BC.view_layer.update(); return o
def sel(*objs):
    for x in bpy.data.objects: x.select_set(x in objs)
def selected(): return sorted(o.name for o in BC.selected_objects)
clear()
A, B, C = cube("A", (0, 0, 1)), cube("B", (4, 0, 1)), cube("C", (-6, 0, 1))
BC.scene.dessin.group_select = True
sel(A, B); BC.view_layer.objects.active = A
o = make(m.DESSIN_OT_group); r = type(o).execute(o, BC)
G = m.group_root(A)
chk("A et B groupés", r == {'FINISHED'} and G is not None and m.group_root(B) is G)
members = sorted(x.name for x in m.group_members(G))
# ce que fait le clic de Blender (view3d.select) sur A alors que le groupe est déjà sélectionné : A seul
sel(A)
chk("clic sur A (groupe déjà sélectionné) : tout le groupe est sélectionné, pas A seul", m.group_click(BC, A, 'SET') and selected() == members, selected())
sel(C); sel(C, B)
chk("Maj + clic sur B (ajout) : tout le groupe s'ajoute à C", m.group_click(BC, B, 'ADD_TOGGLE') and selected() == sorted(members + ["C"]), selected())
B.select_set(False)
chk("Maj + clic sur B à nouveau (retrait) : tout le groupe est retiré, C reste", m.group_click(BC, B, 'ADD_TOGGLE') and selected() == ["C"], selected())
sel(A, B, C, G); A.select_set(False)
chk("Ctrl + clic sur A : tout le groupe est retiré", m.group_click(BC, A, 'REMOVE') and selected() == ["C"], selected())
sel(A)
op = make(m.DESSIN_OT_selection_boite)
r = type(op).invoke(op, ctx, ev('LEFTMOUSE', 'PRESS', *scr(0, 0)))
if 'RUNNING_MODAL' in r:
    type(op).modal(op, ctx, ev('LEFTMOUSE', 'RELEASE', *scr(0, 0)))
chk("vrai clic (outil Select) sur A : le groupe entier", selected() == members, (r, selected()))
sel(C)
chk("objet hors groupe : rien de changé", m.group_click(BC, C, 'SET') is False and selected() == ["C"])
BC.scene.dessin.group_select = False; sel(A)
chk("sélection de groupe coupée (panneau Groups) : A seul", m.group_click(BC, A, 'SET') is False and selected() == ["A"])
BC.scene.dessin.group_select = True
sel(A, B, G); BC.view_layer.objects.active = A
o = make(m.DESSIN_OT_ungroup); type(o).execute(o, BC)
sel(A)
chk("après Ungroup : un clic sur A ne prend que A", m.group_root(A) is None and m.group_click(BC, A, 'SET') is False and selected() == ["A"], selected())
summary()
