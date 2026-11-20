# Edit Group / Close Group (comme SketchUp, issue de xxiong-feiyi) : le groupe s'ouvre dans UNE vue (vue locale de
# Blender) : le reste du modèle y est caché, ses objets se sélectionnent un par un, ce qu'on y dessine entre dans le
# groupe ; clic droit > Close Group. La vue locale est simulée ici (pas de fenêtre en mode sans écran).
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE, 'harness.py')).read())
exec(open(_os.path.join(_HERE, 'prec_lib.py')).read())
import sys, types
from mathutils import Vector
BC = bpy.context
SEC = "?"
def chk(name, ok, meas=""): rec(SEC, name, ok, meas)
OB = [v for k, v in sys.modules.items() if k.endswith(".objects") and hasattr(v, "GE_KEY")][0]
CORE = [v for k, v in sys.modules.items() if k.endswith(".core") and hasattr(v, "LAST_VIEW3D")][0]

# ---- vue locale simulée : appartenance par vue
LOCAL = {}                                   # id(space) -> set(noms)
class RV:
    def __init__(s):
        s.view_location = Vector((0, 0, 0)); s.view_rotation = __import__("mathutils").Quaternion(); s.view_distance = 10.0
        s.view_perspective = 'PERSP'; s.view_camera_zoom = 0.0; s.view_camera_offset = (0.0, 0.0)
class Space:
    def __init__(s): s.local_view = None; s.region_3d = RV()
class Area:
    _n = 100
    def __init__(s):
        Area._n += 1; s._p = Area._n; s.type = 'VIEW_3D'; s.spaces = types.SimpleNamespace(active=Space())
    def as_pointer(s): return s._p
    def tag_redraw(s): pass
class Screen(dict):
    def __init__(s, areas): super().__init__(); s.areas = areas
def lv_set(o, space, state):
    if space.local_view is None: raise RuntimeError("Viewport not in local view")
    (LOCAL[id(space)].add if state else LOCAL[id(space)].discard)(o.name)
def lv_get(o, space):
    if space.local_view is None: raise RuntimeError("Viewport not in local view")
    return o.name in LOCAL[id(space)]
toggles = []
def toggle(context, frame=False):
    sp = context.area.spaces.active
    toggles.append(sp.local_view is None)
    if sp.local_view is None:
        sel = {o.name for o in context.view_layer.objects if o.select_get()}
        if not sel: return {'CANCELLED'}
        sp.local_view = object(); LOCAL[id(sp)] = sel
        sp.region_3d.view_location = Vector((0, 0, 0))        # (Blender garde la vue d'avant)
    else:
        sp.local_view = None; LOCAL.pop(id(sp), None)
        sp.region_3d.view_location = Vector((0, 0, 0))        # Blender revient à la vue de l'ouverture
    return {'FINISHED'}
OB._lv_set, OB._lv_get, OB._localview_toggle = lv_set, lv_get, toggle

A1, A2 = Area(), Area()
SCR = Screen([A1, A2])
OB._ge_screens = lambda: [SCR]
class Ctx:
    def __init__(s, area): s.area = area; s.screen = SCR; s.mode = 'OBJECT'; s.window = None
    view_layer = property(lambda s: BC.view_layer)
    scene = property(lambda s: BC.scene)
    preferences = property(lambda s: BC.preferences)
    selected_objects = property(lambda s: [o for o in BC.view_layer.objects if o.select_get()])
C1, C2 = Ctx(A1), Ctx(A2)

def clear():
    for o in list(bpy.data.objects): bpy.data.objects.remove(o)
def box(name, x):
    me = bpy.data.meshes.new(name); o = bpy.data.objects.new(name, me); o.location = (x, 0, 0)
    BC.collection.objects.link(o); BC.view_layer.update(); return o
def select(*objs):
    for o in BC.view_layer.objects: o.select_set(o in objs)
    if objs: BC.view_layer.objects.active = objs[0]
def run(cls, ctx):
    op = make(cls); return type(op).execute(op, ctx)
def names(objs): return sorted(o.name for o in objs)
def selnames(): return names(o for o in BC.view_layer.objects if o.select_get())
def click(ctx, o):
    """Clic de l'outil de sélection : le groupe entier si group_click le prend, sinon l'objet seul."""
    select()
    if not OB.group_click(ctx, o, 'SET'):
        select(o)
BC.scene.dessin.group_select = True

clear()
a, b, c = box("A", 0), box("B", 2), box("C", 9)
d, e = box("D", 4), box("E", 5)
select(d, e); r1 = run(m.DESSIN_OT_group, C1); g2 = BC.view_layer.objects.active; g2.name = "G2"
select(a, b, d, e, g2); r2 = run(m.DESSIN_OT_group, C1); g1 = BC.view_layer.objects.active; g1.name = "G1"
assert 'FINISHED' in r1 and 'FINISHED' in r2 and d.parent == g2 and g2.parent == g1, (r1, r2)
BC.view_layer.update()

SEC = "Ouvrir (clic droit > Edit Group)"
select(a)
log = []
class L:
    def operator(s, idn, **k): log.append(idn); return types.SimpleNamespace()
    def separator(s): pass
OB.menu_group_edit(L(), C1)
chk("menu du clic droit sur un objet du groupe : Edit Group", log == ["dessin.group_edit"], log)
A1.spaces.active.region_3d.view_location = Vector((3, 4, 0))
r = run(m.DESSIN_OT_group_edit, C1)
sp1 = A1.spaces.active
chk("le groupe s'ouvre dans cette vue (vue locale, sans recadrer)", 'FINISHED' in r and sp1.local_view is not None, r)
chk("seul le groupe reste visible dans cette vue (C est caché)", LOCAL[id(sp1)] == {"G1", "A", "B", "G2", "D", "E"}, sorted(LOCAL[id(sp1)]))
chk("l'autre vue n'est pas touchée", A2.spaces.active.local_view is None)
chk("rien n'est sélectionné en entrant", selnames() == [], selnames())
chk("état gardé par vue", [l["group"] for l in OB.group_edit_stack(C1)] == ["G1"] and OB.group_edit_stack(C2) == [])

SEC = "Pendant l'édition"
click(C1, a)
chk("un clic prend l'objet seul, plus tout le groupe", selnames() == ["A"], selnames())
click(C1, d)
chk("un sous-groupe se prend en entier", selnames() == ["D", "E", "G2"], selnames())
click(C2, a)
chk("dans l'autre vue, un clic prend toujours tout le groupe", selnames() == ["A", "B", "D", "E", "G1", "G2"], selnames())
SUBD = [v for k, v in sys.modules.items() if k.endswith(".subd") and hasattr(v, "expand_groups")][0]
SUBD._late_imports()
chk("déplacer un objet du groupe ouvert : lui seul bouge (Move, Gizmo, glisser)", names(SUBD.expand_groups(C1, [a])) == ["A"],
    names(SUBD.expand_groups(C1, [a])))
chk("... un sous-groupe bouge en entier", names(SUBD.expand_groups(C1, [d])) == ["D", "E", "G2"], names(SUBD.expand_groups(C1, [d])))
chk("dans l'autre vue : tout le groupe bouge", names(SUBD.expand_groups(C2, [a])) == ["A", "B", "D", "E", "G1", "G2"])
chk("sans vue (minuteur de sélection) : le groupe ouvert est connu quand même",
    OB.open_groups_all(types.SimpleNamespace(screen=None, window=None)) == {"G1"})
log.clear(); select(); OB.menu_group_edit(L(), C1)
chk("clic droit dans le vide : Close Group", log == ["dessin.group_close"], log)
select(a); OB.group_edit_stack(C1)
log.clear(); OB.menu_group_edit(L(), C1)
chk("clic droit sur un objet seul du groupe ouvert : Close Group, pas d'Edit Group", log == ["dessin.group_close"], log)
select(a); r = run(m.DESSIN_OT_ungroup, C1)
chk("Ungroup du groupe ouvert : refusé", 'CANCELLED' in r and bpy.data.objects.get("G1") is not None, r)
CORE.LAST_VIEW3D[0] = A1.as_pointer()
n = box("N", 1); BC.view_layer.update()
OB._GE_SEEN["n"] = -1; OB.group_edit_depsgraph(BC.scene)
chk("un objet dessiné pendant l'édition apparaît dans la vue du groupe", "N" in LOCAL[id(sp1)])

SEC = "Groupe dans le groupe"
select(d); log.clear(); OB.menu_group_edit(L(), C1)
chk("clic droit sur un sous-groupe : Close Group et Edit Group", log == ["dessin.group_close", "dessin.group_edit"], log)
r = run(m.DESSIN_OT_group_edit, C1)
chk("Edit Group descend d'un niveau", [l["group"] for l in OB.group_edit_stack(C1)] == ["G1", "G2"], r)
chk("... seul le sous-groupe reste visible", LOCAL[id(sp1)] == {"G2", "D", "E"}, sorted(LOCAL[id(sp1)]))
click(C1, d)
chk("... ses objets se prennent un par un", selnames() == ["D"], selnames())
r = run(m.DESSIN_OT_group_close, C1)
chk("Close Group remonte d'un niveau", [l["group"] for l in OB.group_edit_stack(C1)] == ["G1"] and sp1.local_view is not None, r)
chk("... le groupe du dessus réapparaît (et l'objet dessiné)", {"G1", "A", "B", "G2", "D", "E", "N"} <= LOCAL[id(sp1)] and "C" not in LOCAL[id(sp1)],
    sorted(LOCAL[id(sp1)]))
chk("... le sous-groupe refermé est sélectionné", selnames() == ["D", "E", "G2"], selnames())

SEC = "Fermer (clic droit > Close Group)"
sp1.region_3d.view_location = Vector((7, 1, 0))
r = run(m.DESSIN_OT_group_close, C1)
chk("la vue quitte la vue locale : tout le modèle revient", sp1.local_view is None and OB.group_edit_stack(C1) == [], r)
chk("... sans revenir à la vue d'avant l'ouverture (on reste où on a navigué)", tuple(sp1.region_3d.view_location) == (7, 1, 0),
    tuple(sp1.region_3d.view_location))
chk("l'objet dessiné pendant l'édition est entré dans le groupe, à sa place", n.parent == g1 and abs(n.matrix_world.translation.x - 1) < 1e-6,
    (n.parent and n.parent.name, tuple(n.matrix_world.translation)))
chk("le groupe est sélectionné en entier", selnames() == ["A", "B", "D", "E", "G1", "G2", "N"], selnames())
chk("l'état de la vue est effacé de l'écran", OB.GE_KEY not in SCR.keys())
chk("Échap ne ferme pas (seul le clic droit ferme) : pas de raccourci Échap", not any(
    it.idname in ("dessin.group_close",) for kc in [bpy.context.window_manager.keyconfigs.addon] if kc
    for km in kc.keymaps for it in km.keymap_items))

SEC = "Vue déjà en vue locale (touche /)"
select(c, a); toggle(C2)
chk("(vue locale de départ : A et C)", LOCAL[id(A2.spaces.active)] == {"A", "C"})
select(a); r = run(m.DESSIN_OT_group_edit, C2)
chk("Edit Group dans cette vue", LOCAL[id(A2.spaces.active)] >= {"G1", "A", "B"} and "C" not in LOCAL[id(A2.spaces.active)], r)
run(m.DESSIN_OT_group_close, C2)
chk("Close Group rend la vue locale d'avant, sans la quitter", A2.spaces.active.local_view is not None and LOCAL[id(A2.spaces.active)] == {"A", "C"},
    sorted(LOCAL.get(id(A2.spaces.active), ())))
toggle(C2)

SEC = "Vue sortie de la vue locale autrement"
select(a); run(m.DESSIN_OT_group_edit, C1)
toggle(C1)
chk("la vue n'est plus en vue locale : plus de groupe ouvert (Close Group disparaît)", OB.group_edit_stack(C1) == []
    and not m.DESSIN_OT_group_close.poll(C1))
SCR.clear()

SEC = "Visibilité par vue (accrochages, clics)"
chk("obj_visible : hors vue locale, comme visible_get()", CORE.obj_visible(a, None) is True and CORE.obj_visible(a, Space()) is True)
chk("le cache des accrochages change avec la vue locale", CORE.local_view_token(Space()) is None)

SEC = "Commandes"
chk("commandes editgroup / closegroup", any(e[0] == "Edit Group" and "editgroup" in e[1] for e in m.CMD_ACTIONS)
    and any(e[0] == "Close Group" and "closegroup" in e[1] for e in m.CMD_ACTIONS))

summary()
