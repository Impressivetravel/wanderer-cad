# Retours GitHub du 18 novembre : #20 Trim, #19 barre en Edit mode, #17 Alt + Gizmo, #18 Maj et Quick Type, #16 .pgp, #14 10+6+1/2
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE, 'harness.py')).read())
exec(open(_os.path.join(_HERE, 'prec_lib.py')).read())
import sys, types
SEC = "?"
def chk(name, ok, meas=""): rec(SEC, name, ok, meas)

SEC = "#20 Trim"
km = m.DESSIN_TT_trim.bl_keymap
ex = {it[1]["type"] for it in km if it[0] == "dessin.tool_exit"}
chk("Entrée, Entrée du pavé et Espace terminent l'outil Trim (Espace ne relance plus la commande)", {'RET', 'NUMPAD_ENTER', 'SPACE', 'ESC'} <= ex, sorted(ex))

SEC = "#19 barre du bas en Edit mode"
ka = bpy.context.window_manager.keyconfigs.addon
m.unregister_mouse_track(); m.register_mouse_track()
for name in ("Mesh", "Curve", "Object Mode"):
    km = ka.keymaps.get(name)
    chk(f"clic sur la barre posé dans le keymap « {name} »", km is not None and any(it.idname == "dessin.bar_click" and it.type == 'LEFTMOUSE' for it in km.keymap_items))
fake = types.SimpleNamespace(keymaps=[types.SimpleNamespace(name="3D View Tool: Edit Mesh, Knife", space_type='VIEW_3D', region_type='WINDOW'),
                                      types.SimpleNamespace(name="3D View Tool: Edit Mesh, Loop Cut", space_type='VIEW_3D', region_type='WINDOW'),
                                      types.SimpleNamespace(name="Outliner", space_type='OUTLINER', region_type='WINDOW')])
names = m.bar_click_keymap_names(fake)
chk("... et dans le keymap de chaque outil natif de la vue 3D (Knife, Loop Cut...), pas ailleurs",
    ("3D View Tool: Edit Mesh, Knife", 'VIEW_3D', 'WINDOW', True) in names and not any(n[0] == "Outliner" for n in names), names[:3])
m.register_bar_click(fake)
kk = ka.keymaps.get("3D View Tool: Edit Mesh, Knife")
chk("keymap d'outil créé côté add-on avec le clic sur la barre", kk is not None and any(it.idname == "dessin.bar_click" for it in kk.keymap_items))
op = make(m.DESSIN_OT_bar_click)
G = m.DESSIN_OT_bar_click.invoke.__globals__; keep = G["cmd_click_idle"]
G["cmd_click_idle"] = lambda c, e: False
r = type(op).invoke(op, ctx, ev('LEFTMOUSE', 'PRESS', 100, 100))
chk("clic hors de la barre : rendu à l'outil", r == {'CANCELLED', 'PASS_THROUGH'}, r)
G["cmd_click_idle"] = lambda c, e: True
r = type(op).invoke(op, ctx, ev('LEFTMOUSE', 'PRESS', 100, 100))
chk("clic sur un bouton de la barre : pris par la barre", r == {'FINISHED'}, r)
G["cmd_click_idle"] = keep

SEC = "#18 Maj + lettre avec Quick Type"
wm = bpy.context.window_manager
tk = wm.keyconfigs.new("t18")
kmc = tk.keymaps.new(name="Curve", space_type='EMPTY')
iv = kmc.keymap_items.new("wm.call_menu", 'V', 'PRESS'); iv.properties.name = "VIEW3D_MT_edit_curve_handle_type_set"
kmo = tk.keymaps.new(name="Object Mode", space_type='EMPTY')
kmo.keymap_items.new("object.duplicate_move", 'D', 'PRESS', shift=True)
kmo.keymap_items.new("dessin.blender_key", 'V', 'PRESS', shift=True)        # l'entrée de Wanderer elle-même : ignorée
it = m.blender_key_item(tk, 'EDIT_CURVE', 'V', False)
chk("V en édition de courbe : le menu du type de poignée de Blender est trouvé", it is not None and it.idname == "wm.call_menu" and it.properties.name == "VIEW3D_MT_edit_curve_handle_type_set", it and it.idname)
chk("pas de Maj + V de Blender en édition de courbe : Maj + V lancera donc le V de Blender", m.blender_key_item(tk, 'EDIT_CURVE', 'V', True) is None)
chk("Maj + D en mode Objet : Blender a le sien, il le garde", m.blender_key_item(tk, 'OBJECT', 'D', True) is not None)
chk("les entrées de Wanderer ne comptent pas", m.blender_key_item(tk, 'OBJECT', 'V', True) is None)
G = m.DESSIN_OT_blender_key.invoke.__globals__
saved_q = G["quick_type_on"]; calls = []
saved_run = G["run_keymap_item"]; G["run_keymap_item"] = lambda it: (calls.append(it.idname), True)[1]
class _KC: user = tk
fctx = types.SimpleNamespace(area=types.SimpleNamespace(type='VIEW_3D'), mode='EDIT_CURVE', window_manager=types.SimpleNamespace(keyconfigs=_KC))
op = make(m.DESSIN_OT_blender_key); op.char = "v"
G["quick_type_on"] = lambda a: False
r = type(op).invoke(op, fctx, ev('V', 'PRESS', 10, 10, shift=True))
chk("Quick Type éteint : Maj + V reste à Blender tel quel", r == {'CANCELLED', 'PASS_THROUGH'} and not calls, r)
G["quick_type_on"] = lambda a: True
r = type(op).invoke(op, fctx, ev('V', 'PRESS', 10, 10, shift=True))
chk("Quick Type allumé, courbe : Maj + V ouvre le menu V de Blender", r == {'FINISHED'} and calls == ["wm.call_menu"], (r, calls))
fctx.mode = 'OBJECT'; op.char = "d"; calls.clear()
r = type(op).invoke(op, fctx, ev('D', 'PRESS', 10, 10, shift=True))
chk("Quick Type allumé, Maj + D (Blender en a un) : rendu à Blender (dupliquer)", r == {'CANCELLED', 'PASS_THROUGH'} and not calls, (r, calls))
G["quick_type_on"] = saved_q; G["run_keymap_item"] = saved_run
ia = kmo.keymap_items.new("object.select_all", 'A', 'PRESS'); ia.properties.action = 'SELECT'
for o in bpy.data.objects: o.select_set(False)
bpy.data.objects.new("QT18", None); bpy.context.scene.collection.objects.link(bpy.data.objects["QT18"]); bpy.context.view_layer.update()
okr = m.run_keymap_item(ia)
chk("le raccourci de Blender est lancé avec ses réglages (Select All, action Select)", okr and bpy.data.objects["QT18"].select_get(), okr)
wm.keyconfigs.remove(tk)
m.PREF_DEFAULTS["cmd_type"] = True
m.unregister_cmd_keymap(); m.register_cmd_keymap()
kmv = ka.keymaps.get("3D View")
chk("Quick Type : Maj + lettre enregistré pour chaque lettre, sauf Q", sum(1 for it in kmv.keymap_items if it.idname == "dessin.blender_key" and it.shift) == 25
    and not any(it.idname == "dessin.blender_key" and it.type == 'Q' for it in kmv.keymap_items))
m.unregister_mouse_track(); m.register_mouse_track()
qq = [it.idname for it in kmv.keymap_items if it.type == 'Q' and it.shift and not it.ctrl and not it.alt]
chk("Maj + Q : seulement la bascule de Quick Type (Quick Favorites de Blender ne part pas en même temps)", qq == ["dessin.quick_type_toggle"], qq)
m.PREF_DEFAULTS["cmd_type"] = False
m.unregister_cmd_keymap(); m.register_cmd_keymap()

SEC = "#22 extrusion du Gizmo = Extrude Manifold"
import bmesh, contextlib, io
C = bpy.context
def stats(o):
    bm = bmesh.from_edit_mesh(o.data)
    return (len(bm.faces), len(bm.edges), sum(1 for e in bm.edges if len(e.link_faces) != 2),
            round(max(v.co.z for v in bm.verts), 4), round(min(v.co.z for v in bm.verts), 4))
def setup(cuts):
    for o in list(bpy.data.objects): bpy.data.objects.remove(o)
    bpy.ops.mesh.primitive_cube_add(size=2); o = C.active_object
    bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_mode(type='FACE')
    if cuts:
        bpy.ops.mesh.select_all(action='SELECT'); bpy.ops.mesh.subdivide(number_cuts=cuts); bpy.ops.mesh.select_all(action='DESELECT')
    bm = bmesh.from_edit_mesh(o.data)
    for f in bm.faces:
        c = f.calc_center_median()
        f.select_set(f.normal.z > 0.9 and (not cuts or (abs(c.x) < 0.1 and abs(c.y) < 0.1)))
    bmesh.update_edit_mesh(o.data)
    return o
def ours(cuts, dz):
    o = setup(cuts)
    op = make(m.DESSIN_OT_gumball_extrude)
    piv, _t = m.gumball_selection(C)
    with contextlib.redirect_stdout(io.StringIO()):
        r = type(op).invoke(op, ctx, ev('LEFTMOUSE', 'PRESS', *scr(piv.x, piv.y)))
        type(op).modal(op, ctx, ev('LEFTMOUSE', 'RELEASE', *scr(piv.x, piv.y)))
        for ch in f"{dz:g}":
            type(op).modal(op, ctx, ev('A', 'PRESS', *scr(piv.x, piv.y), unicode=ch, ascii=ch))
        r = type(op).modal(op, ctx, ev('RET', 'PRESS', *scr(piv.x, piv.y)))
    st = stats(o); bpy.ops.object.mode_set(mode='OBJECT'); return r, st
def blender(cuts, dz):
    o = setup(cuts)
    bpy.ops.mesh.extrude_manifold(MESH_OT_extrude_region={"use_dissolve_ortho_edges": True},
                                  TRANSFORM_OT_translate={"value": (0, 0, dz), "use_automerge_and_split": True})
    st = stats(o); bpy.ops.object.mode_set(mode='OBJECT'); return st
for cuts, dz, what in ((0, 1.0, "dessus d'une boîte tiré de 1"), (0, -0.5, "dessus d'une boîte poussé de 0,5"),
                       (2, 0.5, "face du milieu tirée (bossage)"), (2, -0.5, "face du milieu poussée (poche)")):
    r, a = ours(cuts, dz); b = blender(cuts, dz)
    chk(f"{what} : même résultat qu'Extrude Manifold de Blender, sans arête non-manifold", 'FINISHED' in r and a == b and a[2] == 0, (r, a, b))

SEC = "#1 indicateur de rotation du Gizmo"
gb = sys.modules[[k for k in sys.modules if k.endswith(".gumball")][0]]
for o in list(bpy.data.objects): bpy.data.objects.remove(o)
bpy.ops.mesh.primitive_cube_add(size=2); cb = C.active_object; C.view_layer.update()
C.scene.dessin.gumball = True
op = make(m.DESSIN_OT_gumball); op.kind = 'ROTATE'; op.axis = 2
with contextlib.redirect_stdout(io.StringIO()):
    r = type(op).invoke(op, ctx, ev('LEFTMOUSE', 'PRESS', *scr(3, 0)))
    for x, y in ((3, 0.6), (2.9, 1.2), (2.6, 1.9)):
        type(op).modal(op, ctx, ev('MOUSEMOVE', 'NOTHING', *scr(x, y), shift=True))
rot = gb._GB_ROT["on"]
chk("pendant la rotation : l'indicateur est actif (centre, axe Z, angle parcouru)", rot is not None and abs(rot[1].z) > 0.99 and abs(rot[5] - op.value) < 1e-9 and rot[5] > 20, rot and round(rot[5], 2))
geo = gb.rot_indicator_geometry(region, rv3d, rot, 72.0)
c, pts = geo
ang = math.degrees(math.atan2((pts[-1] - c).y, (pts[-1] - c).x) - math.atan2((pts[0] - c).y, (pts[0] - c).x))
chk("l'arc part de la position de départ et va dans le sens de la rotation (anti-horaire vu de dessus)", abs(ang - rot[5]) < 0.5 and abs((pts[0] - c).length - 72.0) < 0.5, (round(ang, 2), round(rot[5], 2)))
gb.rot_indicator_draw()       # (sans interface : ne doit pas planter)
with contextlib.redirect_stdout(io.StringIO()):
    r = type(op).modal(op, ctx, ev('LEFTMOUSE', 'RELEASE', *scr(2.6, 1.9)))
chk("au relâchement : l'indicateur disparaît", gb._GB_ROT["on"] is None, r)
op = make(m.DESSIN_OT_gumball); op.kind = 'ROTATE'; op.axis = 2
with contextlib.redirect_stdout(io.StringIO()):
    type(op).invoke(op, ctx, ev('LEFTMOUSE', 'PRESS', *scr(3, 0)))
    type(op).modal(op, ctx, ev('LEFTMOUSE', 'RELEASE', *scr(3, 0)))
    for ch in "35":
        type(op).modal(op, ctx, ev('A', 'PRESS', *scr(3, 0), unicode=ch, ascii=ch))
rot = gb._GB_ROT["on"]
chk("angle tapé (35) : visible sur l'indicateur avant Entrée", rot is not None and abs(rot[5] - 35) < 1e-9, rot and rot[5])
with contextlib.redirect_stdout(io.StringIO()):
    type(op).modal(op, ctx, ev('ESC', 'PRESS', *scr(3, 0)))
chk("Échap : l'indicateur disparaît", gb._GB_ROT["on"] is None)

SEC = "#16 import .pgp d'AutoCAD"
PG = m.DESSIN_OT_alias_import_pgp.execute.__globals__
pgp = """; acad.pgp
;  -- External Commands --
NOTEPAD,   START NOTEPAD, 1,*File to edit: ,
;  -- Command Aliases --
L,         *LINE
PL,        *PLINE
REC,       *RECTANG
C,         *CIRCLE
F,         *FILLET
DLI,       *DIMLINEAR
-I,        *-INSERT
TR,        *TRIM
LA,        *LAYER
SO,        *SOLID
MYCO,      *COPY
"""
pp = PG["parse_pgp"](pgp)
chk("lecture : les alias « X, *COMMANDE » seulement (commandes externes et commentaires ignorés)", ("L", "LINE") in pp and ("-I", "INSERT") in pp and not any(a == "NOTEPAD" for a, _c in pp), pp)
class _A:
    def __init__(s): s.alias = ""; s.command = ""
class _Col(list):
    def add(s): x = _A(); s.append(x); return x
prefs = types.SimpleNamespace(aliases=_Col())
x = prefs.aliases.add(); x.alias, x.command = "rec", "Polygon: Edge"          # un alias à soi : il est gardé
E = m.cmd_entries()
added, already, missing = PG["import_pgp_aliases"](prefs, pgp, E)
got = {a.alias: a.command for a in prefs.aliases}
chk("F -> Fillet Curve (2D), MYCO -> Copy, -I -> Insert Block ajoutés", got.get("f") == "Fillet Curve" and got.get("myco") == "Copy" and got.get("-i") == "Insert Block", got)
lab = lambda a: E[m.alias_target(E, a)]["label"]
chk("PL et DLI : Wanderer les connaît déjà (Polyline, Dimension), pas de doublon", "pl" not in got and "dli" not in got and lab("pl") == "Polyline" and lab("dli") == "Dimension", (lab("pl"), lab("dli")))
chk("votre alias « rec » est gardé tel quel", got.get("rec") == "Polygon: Edge", got.get("rec"))
chk("les alias que Wanderer connaît déjà (L, C, TR) ne sont pas ajoutés en double", "l" not in got and "c" not in got and "tr" not in got, sorted(got))
chk("commandes sans équivalent listées (LAYER, SOLID), le reste continue", "LAYER" in missing and "SOLID" in missing and added == 3, (added, already, missing))
added2, _al2, _m2 = PG["import_pgp_aliases"](prefs, pgp, E)
chk("importer deux fois : rien en double", added2 == 0, added2)

SEC = "#18 la puce Quick Type s'éteint tant que Maj est tenu"
redraws = []
core_g = m.shift_held_set.__globals__; saved_core_rb = core_g["redraw_bars"]; core_g["redraw_bars"] = lambda: redraws.append(1)
m.PREF_DEFAULTS["cmd_type"] = True
qctx = types.SimpleNamespace(area=None, scene=bpy.context.scene, window=None)
hold = make(m.DESSIN_OT_osnap_hold)
chk("Quick Type allumé, Maj relâché : la puce est allumée", m.mode_state(qctx, "cmd_type") is True)
r = type(hold).invoke(hold, qctx, ev('LEFT_SHIFT', 'PRESS', 10, 10, shift=True))
chk("Maj enfoncé : la puce s'éteint (et la barre est redessinée)", m.mode_state(qctx, "cmd_type") is False and redraws, (m.mode_state(qctx, "cmd_type"), len(redraws)))
chk("... et la touche Maj continue vers Blender (sélection Maj + clic, etc.)", 'PASS_THROUGH' in r, r)
n = len(redraws)
type(hold).invoke(hold, qctx, ev('LEFT_SHIFT', 'PRESS', 10, 10, shift=True))
chk("Maj toujours tenu : pas de nouveau dessin", len(redraws) == n)
type(hold).invoke(hold, qctx, ev('LEFT_SHIFT', 'RELEASE', 10, 10))
chk("Maj relâché : la puce se rallume", m.mode_state(qctx, "cmd_type") is True and len(redraws) == n + 1)
type(hold).invoke(hold, qctx, ev('RIGHT_SHIFT', 'PRESS', 10, 10, shift=True))
chk("Maj de droite : pareil", m.mode_state(qctx, "cmd_type") is False)
MT = m.DESSIN_OT_mouse_track.invoke.__globals__
saved_hit = MT["cmd_hit"]; MT["cmd_hit"] = lambda *a: None
saved_tcw = MT["tool_cursor_watch"]; MT["tool_cursor_watch"] = lambda c: None
track = make(m.DESSIN_OT_mouse_track)
tctx = types.SimpleNamespace(area=types.SimpleNamespace(type='VIEW_3D', as_pointer=lambda: 1, tag_redraw=lambda: None), mode='OBJECT')
type(track).invoke(track, tctx, ev('MOUSEMOVE', 'NOTHING', 10, 10))
chk("relâché sans que la touche soit vue (autre fenêtre, champ texte) : le mouvement de la souris rallume la puce", m.mode_state(qctx, "cmd_type") is True)
MT["cmd_hit"] = saved_hit; MT["tool_cursor_watch"] = saved_tcw
m.PREF_DEFAULTS["cmd_type"] = False
n = len(redraws)
type(hold).invoke(hold, qctx, ev('LEFT_SHIFT', 'PRESS', 10, 10, shift=True))
chk("Quick Type éteint : Maj ne redessine rien (Maj sert souvent)", len(redraws) == n and m.mode_state(qctx, "cmd_type") is False)
type(hold).invoke(hold, qctx, ev('LEFT_SHIFT', 'RELEASE', 10, 10))
core_g["redraw_bars"] = saved_core_rb

SEC = "Extrusion de courbes : lissage auto et Limited Dissolve (kalpit3d)"
import math as _math, bmesh as _bmesh
for o in list(bpy.data.objects): bpy.data.objects.remove(o)
C = bpy.context
sq = [(x * 0.5, 0, 0) for x in range(5)] + [(2, y * 0.5, 0) for y in range(1, 5)] + [(2 - x * 0.5, 2, 0) for x in range(1, 5)] + [(0, 2 - y * 0.5, 0) for y in range(1, 4)]
r = m.build_polyline(C, "SQ", [Vector(p) for p in sq], True)
h = m.build_polyline(C, "HOLE", [Vector((1 + 0.4 * _math.cos(t * _math.tau / 32), 1 + 0.4 * _math.sin(t * _math.tau / 32), 0)) for t in range(32)], True)
gp = [(50 * _math.sin(_math.radians(t * 0.3)), 50 - 50 * _math.cos(_math.radians(t * 0.3)), 0) for t in range(20)] + [(5, -1, 0), (0, -1, 0)]
g = m.build_polyline(C, "GENTLE", [Vector((p[0] + 10, p[1], p[2])) for p in gp], True)
C.view_layer.update()
cls = m.DESSIN_OT_extrude_crv
o = make(cls); cls = type(o)
o.items = [(r, None), (h, None), (g, None)]
o.history = False
cls.build(o, ctx, ("extrude", Vector((0, 0, 0)), Vector((0, 0, 3)), True, False))
outs = sorted((ob for ob in bpy.data.objects if ob.type == 'MESH'), key=lambda ob: ob.location.x)
chk("deux extrusions (le carré troué, la forme à arc doux)", len(outs) == 2, [ob.name for ob in outs])
def info(ob):
    me = ob.data
    ec = {}
    for p in me.polygons:
        for k in p.edge_keys: ec[k] = ec.get(k, 0) + 1
    return me, ec
me, ec = info(outs[0])
chk("carré troué : les points alignés des côtés et le bouchon en triangles sont nettoyés (Limited Dissolve)",
    len(me.polygons) <= 40 and not any(len(p.vertices) == 3 for p in me.polygons), len(me.polygons))
chk("... le solide reste fermé (aucune arête libre)", all(v == 2 for v in ec.values()), sum(1 for v in ec.values() if v != 2))
chk("... les faces sont lissées", all(p.use_smooth for p in me.polygons))
sharp = me.attributes.get("sharp_edge")
nsharp = sum(1 for d in sharp.data if d.value) if sharp else 0
ang = []
bm = _bmesh.new(); bm.from_mesh(me); bm.edges.ensure_lookup_table()
want = sum(1 for e in bm.edges if e.is_manifold and e.calc_face_angle() > _math.radians(30.0) + 1e-6)
bm.free()
chk("... arêtes à plus de 30° vives (coins du carré, bords des bouchons), le reste lisse (Shade Auto Smooth)", sharp is not None and nsharp == want and 0 < nsharp < len(me.edges), (nsharp, want, len(me.edges)))
me2, ec2 = info(outs[1])
chk("arc doux (0,3° par segment) : ses facettes restent (1° l'aurait aplati), dissolve à 0,1° seulement",
    m.EXTRUDE_DISSOLVE_DEG <= 0.1 and len(me2.polygons) == 24 and all(v == 2 for v in ec2.values()), len(me2.polygons))
for o2 in list(bpy.data.objects): bpy.data.objects.remove(o2)

summary()
