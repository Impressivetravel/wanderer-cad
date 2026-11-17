# Copier en glissant : Alt + glisser (Rhino) ou Maj + glisser (3ds Max), sur une flèche du Gumball ou sur l'objet lui-même.
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE, 'harness.py')).read())
exec(open(_os.path.join(_HERE, 'prec_lib.py')).read())
import bmesh
BC = bpy.context
SEC = "?"
def chk(name, ok, meas=""): rec(SEC, name, ok, meas)
def cube(loc=(0, 0, 1), size=2):
    me = bpy.data.meshes.new("Box"); bm = bmesh.new(); bmesh.ops.create_cube(bm, size=size); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new("Box", me); o.location = loc; BC.collection.objects.link(o)
    for x in bpy.data.objects: x.select_set(x is o)
    BC.view_layer.objects.active = o; BC.view_layer.update(); return o
def gop(kind, axis, x, y, **kw):
    o = make(m.DESSIN_OT_gumball); o.kind = kind; o.axis = axis
    r = type(o).invoke(o, ctx, ev('LEFTMOUSE', 'PRESS', *scr(x, y), **kw)); return o, r
def send(o, t, v, x, y, **kw):
    r = type(o).modal(o, ctx, ev(t, v, *scr(x, y), **kw)); BC.view_layer.update(); return r
def boxes(): return sorted(round(o.matrix_world.translation.x, 3) for o in bpy.data.objects if o.type == 'MESH')
BC.scene.dessin.gumball = True
PK = m.DESSIN_OT_apply_preset.execute.__globals__['__package__']
def setkey(k): m.PREF_DEFAULTS['copy_key'] = k      # (pref() lit ces valeurs quand l'add-on n'est pas installé)
def sel_drag(x0, x1, **mods):
    """Glisser l'objet lui-même avec l'outil Select (Rhino : on attrape l'objet et on le tire)."""
    o = make(m.DESSIN_OT_selection_boite)
    r = type(o).invoke(o, ctx, ev('LEFTMOUSE', 'PRESS', *scr(x0, 0), **mods))
    if 'RUNNING_MODAL' not in r:
        return r, boxes()
    for x in (x0 + 1, (x0 + x1) / 2, x1):
        send(o, 'MOUSEMOVE', 'NOTHING', x, 0, **mods)
    r = send(o, 'LEFTMOUSE', 'RELEASE', x1, 0, **mods)
    try: type(o).cleanup(o)
    except Exception: pass
    return r, boxes()
def gb_drag(**mods):
    clear(); cube()
    o, r = gop('MOVE', 0, 1, 0, **mods)
    for x in (3, 6, 11):
        send(o, 'MOUSEMOVE', 'NOTHING', x, 0, **mods)
    send(o, 'LEFTMOUSE', 'RELEASE', 11, 0, **mods)
    return boxes()

SEC = "Gumball, Alt (Rhino)"
chk("Alt + glisser la flèche X : une copie en x = 10, l'original reste en 0", gb_drag(alt=True) == [0.0, 10.0], boxes())
chk("sans touche : simple déplacement", gb_drag() == [10.0], boxes())
chk("Maj + glisser la flèche (réglage Alt) : pas de copie", gb_drag(shift=True) == [10.0], boxes())
clear(); cube(); r, bx = sel_drag(0, 10, alt=True)
chk("Alt + glisser l'objet lui-même : une copie en x = 10", bx == [0.0, 10.0], (r, bx))
clear(); cube(); r, bx = sel_drag(0, 10)
chk("glisser l'objet sans touche : simple déplacement", bx == [10.0], (r, bx))
clear(); cube(); r, bx = sel_drag(0, 10, shift=True)
chk("Maj + glisser l'objet (réglage Alt) : pas de copie, l'objet ne bouge pas (Maj ajoute à la sélection)", bx == [0.0], (r, bx))

SEC = "Maj (3ds Max)"
setkey('SHIFT')
chk("Maj + glisser la flèche X : une copie en x = 10", gb_drag(shift=True) == [0.0, 10.0], boxes())
chk("Alt + glisser la flèche : simple déplacement", gb_drag(alt=True) == [10.0], boxes())
clear(); cube()
o, r = gop('MOVE', 0, 1, 0, shift=True)
send(o, 'MOUSEMOVE', 'NOTHING', 3, 0, shift=True); send(o, 'LEFT_SHIFT', 'RELEASE', 3, 0)
send(o, 'MOUSEMOVE', 'NOTHING', 11, 0); send(o, 'LEFTMOUSE', 'RELEASE', 11, 0)
chk("Maj lâché pendant le glisser : la copie est gardée, comme dans 3ds Max", boxes() == [0.0, 10.0], boxes())
clear(); cube(); r, bx = sel_drag(0, 10, shift=True)
chk("Maj + glisser l'objet lui-même : une copie en x = 10", bx == [0.0, 10.0], (r, bx))
clear(); cube(); r, bx = sel_drag(0, 10, alt=True)
chk("Alt + glisser l'objet : laissé à Blender (pas de copie)", bx == [0.0] and 'PASS_THROUGH' in r, (r, bx))
clear(); cube()
o = make(m.DESSIN_OT_selection_boite); type(o).invoke(o, ctx, ev('LEFTMOUSE', 'PRESS', *scr(0, 0), shift=True))
chk("Maj + glisser : l'invite dit Shift: copy, Alt: keep dominant axis", "Shift: copy" in type(o).move_header(o, m.Vector((1, 0, 0))) and "Alt: keep dominant axis" in type(o).move_header(o, m.Vector((1, 0, 0))))
try: type(o).cleanup(o)
except Exception: pass
setkey('ALT')
chk("réglage Alt : l'invite dit Alt: copy, Shift: keep dominant axis", "Alt: copy" in type(o).move_header(o, m.Vector((1, 0, 0))))

SEC = "3ds Max : Clone Options"
setkey('SHIFT')
CL = m.clone_make.__globals__['_CLONE']
calls = []
m.DESSIN_OT_clone_options  # (enregistré)
clear(); A = cube()
o, r = gop('MOVE', 0, 1, 0, shift=True)
for x in (3, 6, 11):
    send(o, 'MOUSEMOVE', 'NOTHING', x, 0, shift=True)
real_ops = m.clone_dialog.__globals__['bpy']
send(o, 'LEFTMOUSE', 'RELEASE', 11, 0, shift=True)
chk("Maj + glisser un objet : l'original revient en place, la fenêtre Clone Options décide (sans fenêtre ici : une copie, comme avant)",
    boxes() == [0.0, 10.0] and CL["items"] == [], boxes())
def prep(n_objs=1):
    clear(); objs = [cube((0, 3 * i, 1)) for i in range(n_objs)]
    CL["items"] = [(ob.name, ob.matrix_world.copy(), m.Matrix.Translation((10, 0, 0)) @ ob.matrix_world) for ob in objs]
    return objs
A, = prep()
made = m.clone_make(BC, 'COPY', 3, "Box002")
xs = sorted(round(d.matrix_world.translation.x, 3) for d in made)
chk("Copy, 3 copies : à 10, 20 et 30 (même pas que la première), géométrie propre à chacune", xs == [10.0, 20.0, 30.0] and all(d.data is not A.data for d in made), xs)
chk("... nommées Box002, Box003, Box004 et sélectionnées (l'original ne l'est plus)", [d.name for d in made] == ["Box002", "Box003", "Box004"]
    and all(d.select_get() for d in made) and not A.select_get(), [d.name for d in made])
A, = prep()
made = m.clone_make(BC, 'INSTANCE', 2, "")
chk("Instance : les copies partagent la géométrie de l'original (Alt+D)", len(made) == 2 and all(d.data is A.data for d in made))
A, B = prep(2)
made = m.clone_make(BC, 'COPY', 1, "Ignored")
chk("deux objets : une copie de chacun, le nom n'est pas imposé", len(made) == 2 and "Ignored" not in [d.name for d in made])
chk("nom proposé : le suivant libre (Box -> Box.001, Box002 -> Box003)", m.clone_name_next("Box002", 1) == "Box003" and m.clone_name_next("Box", 2) == "Box.002"
    and m.clone_name_default("Box") not in bpy.data.objects)
A, = prep()
op = make(m.DESSIN_OT_clone_options)
type(op).cancel(op, BC)
chk("Annuler : aucune copie, plus rien en attente", CL["items"] == [] and len([x for x in bpy.data.objects if x.type == 'MESH']) == 1)

SEC = "3ds Max : mode édition"
def edit_cube():
    clear(); ob = cube()
    BC.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(ob.data)
    for g in list(bm.verts) + list(bm.edges) + list(bm.faces): g.select_set(False)
    return ob, bm
def move_sel(ob, d):
    items = m.edit_selection(BC)
    bm = bmesh.from_edit_mesh(ob.data); bm.verts.ensure_lookup_table()
    for i in items[0][1]: bm.verts[i].co.x += d
    return items
def counts(ob):
    bpy.ops.object.mode_set(mode='OBJECT'); n = (len(ob.data.vertices), len(ob.data.edges), len(ob.data.polygons))
    xs = sorted({round(v.co.x, 3) for v in ob.data.vertices}); return n, xs
ob, bm = edit_cube()
top = max(bm.faces, key=lambda f: f.calc_center_median().x); top.select_set(True); bm.select_flush_mode()
items = move_sel(ob, 2.0)
m.drag_copy_commit(BC, items, True)
n, xs = counts(ob)
chk("Maj + glisser une face : extrusion (cube 8/12/6 -> 12 sommets, 20 arêtes, 10 faces), la face posée 2 plus loin", n == (12, 20, 10) and xs == [-1.0, 1.0, 3.0], (n, xs))
ob, bm = edit_cube()
e = max(bm.edges, key=lambda e: e.verts[0].co.x + e.verts[1].co.x); e.select_set(True); bm.select_flush_mode()
items = move_sel(ob, 2.0)
m.drag_copy_commit(BC, items, True)
n, xs = counts(ob)
chk("Maj + glisser une arête : une nouvelle face qui la relie à la copie (10 sommets, 7 faces)", n == (10, 15, 7) and xs == [-1.0, 1.0, 3.0], (n, xs))
ob, bm = edit_cube()
top = max(bm.faces, key=lambda f: f.calc_center_median().x); top.select_set(True); bm.select_flush_mode()
items = move_sel(ob, 2.0)
m.drag_copy_commit(BC, items, True, ctrl=True)
n, xs = counts(ob)
chk("Ctrl + Maj + glisser une face : copie détachée (le cube reste entier, + 4 sommets, 1 face)", n == (12, 16, 7) and xs == [-1.0, 1.0, 3.0], (n, xs))
setkey('ALT')
ob, bm = edit_cube()
top = max(bm.faces, key=lambda f: f.calc_center_median().x); top.select_set(True); bm.select_flush_mode()
items = move_sel(ob, 2.0)
m.drag_copy_commit(BC, items, True)
n, xs = counts(ob)
chk("réglage Alt (Rhino) : Alt + glisser une face reste une copie détachée", n == (12, 16, 7), (n, xs))

SEC = "Alt maintenu : la poignée sous la souris s'éclaire"
AH = m.DESSIN_OT_gumball_alt_hover.invoke.__globals__['_ALT_HOVER']
clear(); cube()
def hov(t, v, x, y, **kw):
    o = make(m.DESSIN_OT_gumball_alt_hover); return type(o).invoke(o, ctx, ev(t, v, *scr(x, y), **kw))
r = hov('LEFT_ALT', 'PRESS', 2, 0)
chk("Alt pressé au-dessus de la flèche X : elle est repérée, l'évènement continue son chemin (navigation...)", AH["handle"] == ('MOVE', 0) and r == {'PASS_THROUGH'}, (AH["handle"], r))
hov('MOUSEMOVE', 'NOTHING', 0, 2, alt=True)
chk("la souris passe sur la flèche Y, Alt toujours maintenu : c'est elle qui est repérée", AH["handle"] == ('MOVE', 1), AH["handle"])
hov('MOUSEMOVE', 'NOTHING', 30, 30, alt=True)
chk("loin du Gumball : plus rien d'éclairé", AH["handle"] is None, AH["handle"])
hov('MOUSEMOVE', 'NOTHING', 2, 0, alt=True); hov('LEFT_ALT', 'RELEASE', 2, 0)
chk("Alt lâché : plus rien d'éclairé", AH["handle"] is None, AH["handle"])
m.PREF_DEFAULTS['copy_key'] = 'SHIFT'; hov('LEFT_ALT', 'PRESS', 2, 0)
chk("réglage Maj : Alt n'éclaire rien (Blender éclaire lui-même avec Maj)", AH["handle"] is None, AH["handle"])
m.PREF_DEFAULTS['copy_key'] = 'ALT'
class GZ:
    n = 100
    def __init__(self, c): GZ.n += 1; self.p = GZ.n; self.color = c; self.alpha = 0.5; self.color_highlight = (1.0, 0.85, 0.2); self.alpha_highlight = 1.0
    def as_pointer(self): return self.p
G = NS(gz_move=[GZ((1, 0, 0)), GZ((0, 1, 0)), GZ((0, 0, 1))], gz_scale=[], gz_rot=[], gz_plane=[])
hov('LEFT_ALT', 'PRESS', 0, 2); m.alt_hover_light(G, ctx)
chk("la flèche Y prend la couleur de surbrillance, les autres gardent la leur", tuple(G.gz_move[1].color) == (1.0, 0.85, 0.2) and G.gz_move[1].alpha == 1.0 and G.gz_move[0].color == (1, 0, 0), G.gz_move[1].color)
hov('LEFT_ALT', 'RELEASE', 0, 2); m.alt_hover_light(G, ctx)
chk("Alt lâché : la flèche Y retrouve sa couleur", G.gz_move[1].color == (0, 1, 0) and G.gz_move[1].alpha == 0.5, G.gz_move[1].color)
hov('LEFT_ALT', 'PRESS', 2, 0)
o, r = gop('MOVE', 0, 2, 0, alt=True); send(o, 'MOUSEMOVE', 'NOTHING', 6, 0, alt=True); send(o, 'LEFTMOUSE', 'RELEASE', 6, 0)
chk("après Alt + glisser, la surbrillance ne reste pas accrochée", AH["handle"] is None, AH["handle"])
summary()
