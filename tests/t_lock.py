# Lock / Unlock All / Unlock Selected (Rhino ; Freeze / Unfreeze dans 3ds Max), dans le clic droit et la ligne de commande.
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE, 'harness.py')).read())
exec(open(_os.path.join(_HERE, 'prec_lib.py')).read())
import bmesh, numpy as np
BC = bpy.context
SEC = "?"
def chk(name, ok, meas=""): rec(SEC, name, ok, meas)
def cube(name, loc, size=2):
    me = bpy.data.meshes.new(name); bm = bmesh.new(); bmesh.ops.create_cube(bm, size=size); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); o.location = loc; BC.collection.objects.link(o); BC.view_layer.update(); return o
def sel(*objs):
    for x in bpy.data.objects: x.select_set(x in objs)
def run(cls):
    o = make(cls); return type(o).execute(o, BC), o
clear()
A, B, C = cube("A", (0, 0, 1)), cube("B", (10, 0, 1)), cube("C", (-10, 0, 1))
frame = cube("Cadre", (0, 30, 0)); frame.hide_select = True        # verrou posé par Wanderer lui-même (cadre de mise en page)

SEC = "Lock"
sel(A, B)
r, o = run(m.DESSIN_OT_lock)
chk("Lock sur A et B : verrouillés (plus sélectionnables), désélectionnés, avec la marque", r == {'FINISHED'} and A.hide_select and B.hide_select
    and not A.select_get() and A.get("cad_locked") and not C.hide_select, r)
chk("ils restent visibles", A.visible_get() and B.visible_get())
pick = m.pick_object_at(ctx, area, region, *scr(0, 0))
chk("un clic sur A ne le prend plus", pick is None or pick[0] is not A, pick and pick[0].name)
pts = m.collect_snap_points(ctx)
P = np.asarray(pts[0]) if pts is not None else np.zeros((0, 3))
chk("on peut toujours s'accrocher sur un objet verrouillé (ses coins sont parmi les points d'accrochage)",
    len(P) and (np.abs(P - np.array((1, 1, 2))).sum(axis=1) < 1e-6).any(), len(P))

SEC = "Unlock Selected"
sel(C)
o = make(m.DESSIN_OT_unlock_selected)
r = type(o).invoke(o, ctx, ev('NONE', 'NOTHING', 0, 0))
chk("la commande démarre : la sélection d'avant est mise de côté, les objets verrouillés deviennent cliquables",
    'RUNNING_MODAL' in r and not C.select_get() and not A.hide_select and not B.hide_select and frame.hide_select, r)
type(o).modal(o, ctx, ev('LEFTMOUSE', 'PRESS', *scr(10, 0)))
chk("clic sur B : il est choisi (sélectionné)", B.select_get() and not A.select_get())
type(o).modal(o, ctx, ev('LEFTMOUSE', 'PRESS', *scr(-10, 0)))
chk("clic sur C (pas verrouillé) : ignoré", not C.select_get())
r = type(o).modal(o, ctx, ev('RET', 'PRESS', 0, 0))
chk("Entrée : B est libéré et sélectionné, A reste verrouillé", r == {'FINISHED'} and not B.hide_select and not B.get("cad_locked") and B.select_get()
    and A.hide_select and A.get("cad_locked"), r)
o = make(m.DESSIN_OT_unlock_selected); sel(C)
type(o).invoke(o, ctx, ev('NONE', 'NOTHING', 0, 0)); type(o).modal(o, ctx, ev('LEFTMOUSE', 'PRESS', *scr(0, 0)))
r = type(o).modal(o, ctx, ev('ESC', 'PRESS', 0, 0))
chk("Échap : rien n'est libéré (A reverrouillé) et la sélection d'avant revient", r == {'CANCELLED'} and A.hide_select and A.get("cad_locked") and C.select_get(), r)

SEC = "Unlock All"
sel(B); run(m.DESSIN_OT_lock); sel()
r, o = run(m.DESSIN_OT_unlock_all)
chk("Unlock All : A et B libérés et sélectionnés", r == {'FINISHED'} and not A.hide_select and not B.hide_select and A.select_get() and B.select_get()
    and not A.get("cad_locked"), r)
chk("... mais le verrou posé par Wanderer (cadre) n'est pas touché", frame.hide_select)
chk("plus rien de verrouillé : Unlock All et Unlock Selected ne sont plus proposés", not m.DESSIN_OT_unlock_all.poll(BC) and not m.DESSIN_OT_unlock_selected.poll(BC))

SEC = "Clic droit et ligne de commande"
class Lay:
    def __init__(s): s.ops = []; s.order = []
    def operator(s, idname, **k): s.ops.append(idname); s.order.append(idname); return NS()
    def menu(s, idname, **k): s.order.append(idname)
    def separator(s): pass
sel(A); L = Lay(); m.ctx_extra_items(L, BC)
chk("clic droit avec une sélection : Lock ; rien de verrouillé : pas de Unlock", "dessin.lock" in L.ops and "dessin.unlock_all" not in L.ops, L.ops)
run(m.DESSIN_OT_lock); sel(); L = Lay(); m.ctx_extra_items(L, BC)
chk("clic droit dans le vide, un objet verrouillé : Unlock All et Unlock Selected (pas Lock)", "dessin.unlock_all" in L.ops and "dessin.unlock_selected" in L.ops and "dessin.lock" not in L.ops, L.ops)
first = lambda t: (m.cmd_suggest(t) or [{"label": None}])[0]["label"]
got = {t: first(t) for t in ("lock", "freeze", "unlock", "unfreeze", "unlockselected")}
chk("ligne de commande : lock / freeze, unlock / unfreeze (3ds Max), unlockselected", got == {"lock": "Lock", "freeze": "Lock", "unlock": "Unlock All", "unfreeze": "Unlock All", "unlockselected": "Unlock Selected"}, got)
sel(B); L = Lay(); m.ctx_extra_items(L, BC)
names = [x for x in L.order if x in ("DESSIN_MT_ctx_select", "DESSIN_MT_ctx_display", "DESSIN_MT_ctx_material", "dessin.lock", "dessin.unlock_all")]
chk("ordre du clic droit : Select, Display As, Material, puis Lock / Unlock", names == ["DESSIN_MT_ctx_select", "DESSIN_MT_ctx_display", "DESSIN_MT_ctx_material", "dessin.lock", "dessin.unlock_all"], L.order)
# le vrai menu : le bloc est tout en haut, avant Shade Smooth (et pas répété avant Copy Objects)
cls = bpy.types.VIEW3D_MT_object_context_menu
G = m.install_ctx_object_menu.__globals__
saved_draw, saved_orig = cls.draw, G['_CTX_DRAW']["orig"]
def fake_orig(self, context):
    self.layout.operator("object.shade_smooth"); self.layout.operator("view3d.copybuffer")
try:
    G['_CTX_DRAW']["orig"] = None
    cls.draw = fake_orig
    m.install_ctx_object_menu()
    L = Lay(); sel(B)
    cls.draw(NS(layout=L), BC)
    o = L.order
    chk("Isolate (une sélection) dans le bloc, après Lock ; Show All seulement s'il y a des objets masqués",
        "object.hide_view_set" in o and o.index("dessin.lock") < o.index("object.hide_view_set") < o.index("object.shade_smooth")
        and "object.hide_view_clear" not in o, o)
    C.hide_set(True); L2 = Lay(); cls.draw(NS(layout=L2), BC); C.hide_set(False)
    chk("Local View juste sous Isolate (une sélection, pas encore en vue locale)", "view3d.localview" in o
        and o.index("object.hide_view_set") + 1 == o.index("view3d.localview"), o)
    class _LT:
        def __init__(s): s.ops = []; s.order = []; s.texts = []
        def operator(s, idname, **k): s.order.append(idname); s.texts.append(k.get("text")); return NS()
        def menu(s, idname, **k): s.order.append(idname)
        def separator(s): pass
    sp_saved = getattr(BC, "space_data", None)
    L3 = _LT(); fake = NS(mode='OBJECT', scene=BC.scene, view_layer=BC.view_layer, selected_objects=BC.selected_objects,
                         space_data=NS(local_view=object()))
    m.ctx_extra_items(L3, fake)
    chk("déjà en vue locale : « Quit Local View » (même sans sélection)", "Quit Local View" in L3.texts and "Local View" not in L3.texts, L3.texts)
    chk("... un objet masqué : Show All apparaît, avant Shade Smooth", "object.hide_view_clear" in L2.order
        and L2.order.index("object.hide_view_clear") < L2.order.index("object.shade_smooth"), L2.order)
    chk("clic droit en mode objet : Select, Display As, Material, Lock tout en haut, avant Shade Smooth, une seule fois",
        o.index("DESSIN_MT_ctx_select") < o.index("DESSIN_MT_ctx_display") < o.index("DESSIN_MT_ctx_material") < o.index("dessin.lock")
        < o.index("object.shade_smooth") and o.count("DESSIN_MT_ctx_select") == 1, o)
finally:
    m.uninstall_ctx_object_menu()
    cls.draw = saved_draw
    G['_CTX_DRAW']["orig"] = saved_orig
summary()
