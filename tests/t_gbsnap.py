# Snappy Dragging du Gizmo (issue #24) : en tirant une flèche jusqu'au coin d'une autre boîte, c'est le point de la
# boîte déplacée le plus proche qui vient s'y poser (les deux boîtes se touchent), pas le centre du Gizmo ; si le
# Gizmo a été déplacé (Relocate Gizmo), c'est son centre qui se cale, comme dans Rhino.
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE, 'harness.py')).read())
exec(open(_os.path.join(_HERE, 'prec_lib.py')).read())
import bmesh
import types
BC = bpy.context
SEC = "?"
def chk(name, ok, meas=""): rec(SEC, name, ok, meas)
def clear():
    for o in list(bpy.data.objects): bpy.data.objects.remove(o)
def cube(name, loc, size=2):
    me = bpy.data.meshes.new(name); bm = bmesh.new(); bmesh.ops.create_cube(bm, size=size); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); o.location = loc; BC.collection.objects.link(o); return o
def only(o):
    for x in bpy.data.objects: x.select_set(x is o)
    BC.view_layer.objects.active = o; BC.view_layer.update()
def gop(kind, axis, x, y):
    o = make(m.DESSIN_OT_gumball); o.kind = kind; o.axis = axis
    r = type(o).invoke(o, ctx, ev('LEFTMOUSE', 'PRESS', *scr(x, y))); return o, r
def send(o, t, v, x, y, **k):
    r = type(o).modal(o, ctx, ev(t, v, *scr(x, y), **k)); BC.view_layer.update(); return r
def drag(kind, axis, start, path):
    o, r = gop(kind, axis, *start)
    if 'RUNNING_MODAL' not in r:
        return r
    for p in path:
        send(o, 'MOUSEMOVE', 'NOTHING', *p)
    return send(o, 'LEFTMOUSE', 'RELEASE', *path[-1])
def loc(o): return tuple(round(v, 3) for v in o.matrix_world.translation)
st = BC.scene.dessin
st.gumball = True

def scene():
    clear()
    a = cube("A", (-2.882, 0, 1)); b = cube("B", (0, 0, 1))
    only(a); st.gumball_pivot_on = False
    return a, b

SEC = "Snappy : le point le plus proche se pose sur le coin visé"
st.gumball_drag = 'SNAPPY'
a, b = scene()
r = drag('MOVE', 0, (-1.882, 0), [(-1.7, 0), (-1.4, -0.5), (-1.0, -1.0)])        # flèche X tirée jusqu'au coin de B
chk("la boîte A vient toucher B (sa face droite sur le coin x = -1)", abs(a.location.x - (-2.0)) < 1e-4, loc(a))
chk("... elle ne glisse que le long de la flèche", abs(a.location.y) < 1e-6 and abs(a.location.z - 1) < 1e-6, loc(a))
chk("... B ne bouge pas", loc(b) == (0, 0, 1), loc(b))

a, b = scene()
b.location.x = -6.0; BC.view_layer.update()                                        # B à gauche : on tire vers -X
drag('MOVE', 0, (-1.882, 0), [(-2.5, 0), (-4.0, -0.5), (-5.0, -1.0)])              # coin droit de B, x = -5
chk("dans l'autre sens : la face gauche de A se pose sur le coin droit de B", abs(a.location.x - (-4.0)) < 1e-4, loc(a))

a, b = scene()
drag('MOVE', 0, (-1.882, 0), [(-1.7, 0), (-1.0, -0.3), (0.0, -0.3)])               # milieu de l'arête de B (Mid), x = 0
chk("sur un point au milieu de B : la face la plus proche de A s'y pose aussi", abs(a.location.x - (-1.0)) < 1e-4, loc(a))

SEC = "Le plan de déplacement (carré du Gizmo) : le coin le plus proche"
a, b = scene()
b.location = (1.5, 3.0, 1); BC.view_layer.update()
o, r = gop('PLANE', 2, -2.882 + 0.6, 0.6)
if 'RUNNING_MODAL' in r:
    for p in [(-1.8, 0.8), (-1.0, 1.5), (0.5, 2.0)]:
        send(o, 'MOUSEMOVE', 'NOTHING', *p)
    send(o, 'LEFTMOUSE', 'RELEASE', 0.5, 2.0)                                       # coin (0.5, 2) de B
chk("plan XY : le coin de A le plus proche se pose sur le coin de B (A et B se touchent par le coin)",
    abs(a.location.x - (-0.5)) < 1e-4 and abs(a.location.y - 1.0) < 1e-4 and abs(a.location.z - 1) < 1e-6, (loc(a), r))

SEC = "Snap from : Gizmo (comme Rhino)"
def snap_from(v):
    o = make(m.DESSIN_OT_gumball_snap_from); o.value = v; return type(o).execute(o, ctx)
m.PREF_DEFAULTS["gumball_snap_from"] = 'CLOSEST'
st.gumball_snap_from_set = False
chk("par défaut : Closest Point", m.gumball_snap_from(BC) == 'CLOSEST')
snap_from('GUMBALL')
chk("le menu enregistre le choix dans le fichier", st.gumball_snap_from == 'GUMBALL' and st.gumball_snap_from_set and m.gumball_snap_from(BC) == 'GUMBALL')
a, b = scene()
drag('MOVE', 0, (-1.882, 0), [(-1.7, 0), (-1.4, -0.5), (-1.0, -1.0)])
chk("Gizmo au centre de A : c'est lui qui vient sur le coin, A chevauche B", abs(a.location.x - (-1.0)) < 1e-4, loc(a))
a, b = scene()
st.gumball_pivot_on = True; st.gumball_pivot = (-3.882, 0, 1)                      # Relocate Gizmo : face gauche de A
drag('MOVE', 0, (-2.882, 0), [(-2.7, 0), (-1.4, -0.5), (-1.0, -1.0)])
chk("après Relocate Gizmo (face gauche de A) : cette face vient sur le coin", abs(a.location.x - 0.0) < 1e-4, loc(a))
st.gumball_pivot_on = False

SEC = "Snap from : Origin"
snap_from('ORIGIN')
a, b = scene()
for v in a.data.vertices: v.co.x += 1.0; v.co.y += 1.0                              # origine sur l'arête gauche-avant de A
a.location.x = -3.882; BC.view_layer.update()                                       # A occupe toujours x -3.882 .. -1.882
drag('MOVE', 0, (-1.882, 1.0), [(-1.7, 1.0), (-1.4, -0.5), (-1.0, -1.0)])
chk("l'origine de A (sur sa face gauche) vient sur le coin : A passe de l'autre côté du coin", abs(a.location.x - (-1.0)) < 1e-4, loc(a))
a, b = scene()
k = cube("K", (0, 0, 0), size=1); k.parent = a; k.matrix_parent_inverse = a.matrix_world.inverted(); k.location = (-4.5, 0, 1)
BC.view_layer.objects.active = k; k.select_set(False); BC.view_layer.update()
drag('MOVE', 0, (-1.882, 0), [(-1.7, 0), (-1.4, -0.5), (-1.0, -1.0)])
chk("objet actif enfant de l'objet déplacé : c'est son origine qui se cale", abs(k.matrix_world.translation.x - (-1.0)) < 1e-4,
    (loc(a), loc(k)))
BC.view_layer.objects.active = a

SEC = "Snap from : la préférence pour les fichiers où rien n'est choisi"
st.gumball_snap_from_set = False
m.PREF_DEFAULTS["gumball_snap_from"] = 'GUMBALL'
chk("fichier sans choix : la préférence décide", m.gumball_snap_from(BC) == 'GUMBALL')
a, b = scene()
drag('MOVE', 0, (-1.882, 0), [(-1.7, 0), (-1.4, -0.5), (-1.0, -1.0)])
chk("... et le glisser la suit (centre sur le coin)", abs(a.location.x - (-1.0)) < 1e-4, loc(a))
snap_from('CLOSEST')
chk("un choix dans le menu passe devant la préférence", m.gumball_snap_from(BC) == 'CLOSEST')
m.PREF_DEFAULTS["gumball_snap_from"] = 'CLOSEST'

SEC = "Menu du Gizmo"
class _L:
    def __init__(s, log): s.log = log; s.enabled = True
    def column(s, **k): c = _L(s.log); s.log.append(("col", c)); return c
    def row(s, **k): return s.column()
    def separator(s, **k): pass
    def label(s, **k): s.log.append(("label", k.get("text"), s))
    def prop(s, *a, **k): s.log.append(("prop", a[1] if len(a) > 1 else None, s))
    def prop_enum(s, *a, **k): s.log.append(("enum", a[2] if len(a) > 2 else None, s))
    def operator(s, idn, **k):
        props = types.SimpleNamespace(); s.log.append(("op", idn, k.get("text"), k.get("icon"), props, s)); return props
def menu_ops():
    log = []
    mn = types.SimpleNamespace(layout=_L(log))
    m.DESSIN_MT_gumball.draw(mn, BC)
    return [(e[2].strip(), e[3], e[5].enabled) for e in log if e[0] == "op" and e[1] == "dessin.gumball_snap_from"]
st.gumball_drag = 'SNAPPY'
log0 = []; m.DESSIN_MT_gumball.draw(types.SimpleNamespace(layout=_L(log0)), BC)
heads = [(e[0], e[1]) for e in log0 if e[0] in ("enum", "op", "prop")][:5]
chk("tout en haut du menu : Smooth, Snappy, puis les trois choix de Snappy",
    heads == [("enum", "SMOOTH"), ("enum", "SNAPPY")] + [("op", "dessin.gumball_snap_from")] * 3, heads)
ops = menu_ops()
chk("trois choix sous Snappy / Smooth Dragging, le choix actif coché", [o[0] for o in ops] == ["Closest Point", "Gizmo", "Origin"]
    and [o[1] for o in ops] == ['RADIOBUT_ON', 'RADIOBUT_OFF', 'RADIOBUT_OFF'] and all(o[2] for o in ops), ops)
st.gumball_drag = 'SMOOTH'
ops = menu_ops()
chk("grisés en Smooth Dragging", ops and not any(o[2] for o in ops), ops)
st.gumball_drag = 'SNAPPY'

SEC = "Smooth Dragging : pas d'accrochage"
st.gumball_drag = 'SMOOTH'
a, b = scene()
drag('MOVE', 0, (-1.882, 0), [(-1.7, 0), (-1.4, -0.5), (-1.0, -1.0)])
chk("la flèche suit la souris (environ +0,9), sans se caler sur B", abs(a.location.x - (-2.0)) > 1e-3 and abs(a.location.x - (-2.0)) < 0.05, loc(a))
st.gumball_drag = 'SNAPPY'

SEC = "Objets avec enfants et modificateurs"
a, b = scene()
k = cube("K", (0, 0, 0), size=1); k.parent = a; k.matrix_parent_inverse = a.matrix_world.inverted()
k.location = (-3.882 + 0.0, 0, 1)                                                   # enfant collé à gauche de A
mod = a.modifiers.new("arr", 'ARRAY'); mod.count = 1
BC.view_layer.update()
drag('MOVE', 0, (-1.882, 0), [(-1.7, 0), (-1.4, -0.5), (-1.0, -1.0)])
chk("l'enfant suit et c'est toujours la face droite de A qui touche B", abs(a.location.x - (-2.0)) < 1e-4, loc(a))

SEC = "Ctrl tenu pendant le glisser : accrochage activé / coupé (comme Blender)"
snap_from('CLOSEST')
st.gumball_drag = 'SMOOTH'
a, b = scene()
o, r = gop('MOVE', 0, -1.882, 0)
for p in [(-1.7, 0), (-1.4, -0.5), (-1.0, -1.0)]:
    send(o, 'MOUSEMOVE', 'NOTHING', *p)
x_free = a.location.x
send(o, 'LEFT_CTRL', 'PRESS', -1.0, -1.0, ctrl=True)
x_ctrl = a.location.x
chk("Smooth Dragging + Ctrl : la boîte se cale tout de suite (sans bouger la souris)", abs(x_free - (-2.0)) > 1e-3 and abs(x_ctrl - (-2.0)) < 1e-4, (round(x_free, 3), round(x_ctrl, 3)))
send(o, 'LEFT_CTRL', 'RELEASE', -1.0, -1.0)
chk("... Ctrl relâché : elle suit de nouveau la souris", abs(a.location.x - x_free) < 1e-6, round(a.location.x, 3))
send(o, 'LEFTMOUSE', 'RELEASE', -1.0, -1.0)
st.gumball_drag = 'SNAPPY'
a, b = scene()
o, r = gop('MOVE', 0, -1.882, 0)
for p in [(-1.7, 0), (-1.4, -0.5)]:
    send(o, 'MOUSEMOVE', 'NOTHING', *p)
send(o, 'MOUSEMOVE', 'NOTHING', -1.0, -1.0, ctrl=True)
chk("Snappy Dragging + Ctrl : pas d'accrochage", abs(a.location.x - (-2.0)) > 1e-3, round(a.location.x, 3))
send(o, 'LEFTMOUSE', 'RELEASE', -1.0, -1.0, ctrl=True)
MK = m.gumball_snapmark.__globals__["_GB_SNAPMARK"]
chk("repère d'accrochage effacé en fin de glisser", MK["pt"] is None)

SEC = "Touche B : choisir le point de base (comme Blender)"
a, b = scene()
o, r = gop('MOVE', 0, -1.882, 0)
send(o, 'MOUSEMOVE', 'NOTHING', -1.5, 0)
send(o, 'B', 'PRESS', -1.5, 0)
chk("B : la boîte revient à sa place pour choisir le point", abs(a.location.x - (-2.882)) < 1e-6 and o.picking, round(a.location.x, 3))
send(o, 'MOUSEMOVE', 'NOTHING', -3.882, -1.0)
chk("... le point de la boîte sous le curseur est marqué", MK["pt"] is not None and abs(MK["pt"].x - (-3.882)) < 1e-6, MK["pt"])
send(o, 'LEFTMOUSE', 'RELEASE', -3.882, -1.0)          # coin gauche de A choisi comme point de base
chk("... point de base choisi (coin gauche de A)", not o.picking and o.free and abs(o._own[0][0] - (-3.882)) < 1e-6)
for p in [(-2.0, -0.5), (-1.2, -0.9), (-1.0, -1.0)]:
    send(o, 'MOUSEMOVE', 'NOTHING', *p)
r = send(o, 'LEFTMOUSE', 'PRESS', -1.0, -1.0)
chk("le coin choisi vient sur le coin de B, le clic valide", 'FINISHED' in r and abs(a.location.x - 0.0) < 1e-4, (r, round(a.location.x, 3)))
st.gumball_drag = 'SMOOTH'
a, b = scene()
o, r = gop('MOVE', 0, -1.882, 0)
send(o, 'MOUSEMOVE', 'NOTHING', -1.5, 0)
send(o, 'B', 'PRESS', -1.5, 0)
send(o, 'LEFTMOUSE', 'RELEASE', -3.882, -1.0)
send(o, 'MOUSEMOVE', 'NOTHING', -3.0, 0.3)
chk("Smooth : le point de base suit la souris le long de la flèche", abs(a.location.x - (-2.882 + 0.882)) < 1e-3, round(a.location.x, 3))
r = send(o, 'ESC', 'PRESS', -3.0, 0.3)
chk("Échap annule : la boîte revient", 'CANCELLED' in r and abs(a.location.x - (-2.882)) < 1e-6, (r, round(a.location.x, 3)))
st.gumball_drag = 'SNAPPY'


SEC = "Mode Édition : Ctrl, Snappy et B sur des sommets"
def edit_scene(sel_fn):
    a, b = scene()
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(a.data)
    for g in list(bm.verts) + list(bm.edges) + list(bm.faces): g.select_set(False)
    for v in bm.verts:
        if sel_fn(a.matrix_world @ v.co):
            v.select_set(True)
    bm.select_flush(True)
    bmesh.update_edit_mesh(a.data)
    return a, b
def xs(a, fn):
    bm = bmesh.from_edit_mesh(a.data)
    return sorted({round((a.matrix_world @ v.co).x, 3) for v in bm.verts if fn(v)})
st.gumball_drag = 'SMOOTH'
a, b = edit_scene(lambda p: abs(p.x - (-1.882)) < 1e-6)        # la face droite de A
o, r = gop('MOVE', 0, -1.882, 0)
for p in [(-1.7, 0), (-1.4, -0.5), (-1.0, -1.0)]:
    send(o, 'MOUSEMOVE', 'NOTHING', *p)
x_free = xs(a, lambda v: v.select)
send(o, 'LEFT_CTRL', 'PRESS', -1.0, -1.0, ctrl=True)
x_ctrl = xs(a, lambda v: v.select)
chk("Smooth + Ctrl en mode Édition : les sommets sélectionnés se calent sur le coin de B (x = -1)", x_free != [-1.0] and x_ctrl == [-1.0], (x_free, x_ctrl))
send(o, 'LEFT_CTRL', 'RELEASE', -1.0, -1.0)
chk("... Ctrl relâché : ils suivent de nouveau la souris", xs(a, lambda v: v.select) == x_free, xs(a, lambda v: v.select))
send(o, 'LEFT_CTRL', 'PRESS', -1.0, -1.0, ctrl=True)
send(o, 'LEFTMOUSE', 'RELEASE', -1.0, -1.0, ctrl=True)
chk("... relâché avec Ctrl : la face reste calée", xs(a, lambda v: v.select) == [-1.0] and xs(a, lambda v: not v.select) == [-3.882])
bpy.ops.object.mode_set(mode='OBJECT')

st.gumball_drag = 'SNAPPY'
a, b = edit_scene(lambda p: abs(p.x - (-1.882)) < 1e-6 and abs(p.y + 1) < 1e-6 and abs(p.z) < 1e-6)   # un seul sommet
o, r = gop('MOVE', 0, -1.882, -1.0)
for p in [(-2.3, -1.0), (-3.0, -1.0), (-3.85, -1.0)]:
    send(o, 'MOUSEMOVE', 'NOTHING', *p)
got = xs(a, lambda v: v.select)
send(o, 'LEFTMOUSE', 'RELEASE', -3.85, -1.0)
chk("Snappy en mode Édition : le sommet se pose sur un autre sommet du même maillage (x = -3,882)", got == [-3.882], got)
bpy.ops.object.mode_set(mode='OBJECT')

a, b = edit_scene(lambda p: abs(p.x - (-1.882)) < 1e-6)
o, r = gop('MOVE', 0, -1.882, 0)
send(o, 'MOUSEMOVE', 'NOTHING', -1.5, 0)
send(o, 'B', 'PRESS', -1.5, 0)
chk("B en mode Édition : les sommets reviennent à leur place pour choisir le point", o.picking and xs(a, lambda v: v.select) == [-1.882])
send(o, 'MOUSEMOVE', 'NOTHING', -1.882, 1.0)
send(o, 'LEFTMOUSE', 'RELEASE', -1.882, 1.0)
chk("... point de base pris sur un sommet déplacé", not o.picking and abs(o._own[0][0] - (-1.882)) < 1e-6 and abs(o._own[0][1] - 1.0) < 1e-6, o._own)
for p in [(-1.4, 0.5), (-1.0, 1.0)]:
    send(o, 'MOUSEMOVE', 'NOTHING', *p)
r = send(o, 'LEFTMOUSE', 'PRESS', -1.0, 1.0)
chk("... il vient sur le coin de B, le clic valide", 'FINISHED' in r and xs(a, lambda v: v.select) == [-1.0], (r, xs(a, lambda v: v.select)))
bpy.ops.object.mode_set(mode='OBJECT')
st.gumball_drag = 'SNAPPY'


summary()
