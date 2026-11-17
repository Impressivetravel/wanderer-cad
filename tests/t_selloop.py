# Double-clic en mode Édition : boucle d'arêtes, anneau (Alt), rangée de faces, chaîne de sommets, plage entre deux éléments,
# ajout (Maj) et retrait (Ctrl), d'après la sélection de sous-objets de Rhino (« Loop and ring selection »).
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE, 'harness.py')).read())
exec(open(_os.path.join(_HERE, 'prec_lib.py')).read())
import bmesh
from mathutils import Vector
BC = bpy.context
SEC = "?"
def chk(name, ok, meas=""): rec(SEC, name, ok, meas)
ts = BC.tool_settings
def new_mesh(name, fill):
    if BC.mode != 'OBJECT': bpy.ops.object.mode_set(mode='OBJECT')
    clear()
    me = bpy.data.meshes.new(name); bm = bmesh.new(); fill(bm); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); BC.collection.objects.link(o)
    for x in bpy.data.objects: x.select_set(x is o)
    BC.view_layer.objects.active = o; bpy.ops.object.mode_set(mode='EDIT'); return o
def grid(): return new_mesh("Grid", lambda bm: bmesh.ops.create_grid(bm, x_segments=6, y_segments=6, size=15))      # 6 x 6 faces de 5, de -15 à 15
_KEEP = []
def B(o):
    bm = bmesh.from_edit_mesh(o.data); bm.verts.ensure_lookup_table(); bm.edges.ensure_lookup_table(); bm.faces.ensure_lookup_table()
    _KEEP[:] = [bm]; return bm            # (la référence est gardée : sans elle, les éléments rendus deviennent invalides)
def mode(kind): ts.mesh_select_mode = (kind == 'VERT', kind == 'EDGE', kind == 'FACE')
def none(o):
    bm = B(o)
    for f in bm.faces: f.select_set(False)
    for e in bm.edges: e.select_set(False)
    for v in bm.verts: v.select_set(False)
    bm.select_history.clear(); bmesh.update_edit_mesh(o.data)
def edge_at(o, x, y):
    bm = B(o); return min(bm.edges, key=lambda e: ((e.verts[0].co + e.verts[1].co) / 2 - Vector((x, y, 0))).length)
def face_at(o, x, y):
    bm = B(o); return min(bm.faces, key=lambda f: (f.calc_center_median() - Vector((x, y, 0))).length)
def vert_at(o, x, y):
    bm = B(o); return min(bm.verts, key=lambda v: (v.co - Vector((x, y, 0))).length)
def pick(o, el):
    """Ce que fait un clic : l'élément est sélectionné et devient le dernier de l'historique."""
    el.select_set(True); B(o).select_history.add(el); bmesh.update_edit_mesh(o.data)
def dbl(x, y, **kw):
    op = make(m.DESSIN_OT_select_loop)
    return type(op).invoke(op, ctx, ev('LEFTMOUSE', 'DOUBLE_CLICK', *scr(x, y), **kw))
def sel_edges(o): return sorted((round((e.verts[0].co.x + e.verts[1].co.x) / 2, 2), round((e.verts[0].co.y + e.verts[1].co.y) / 2, 2)) for e in B(o).edges if e.select)
def sel_faces(o): return sorted((round(f.calc_center_median().x, 2), round(f.calc_center_median().y, 2)) for f in B(o).faces if f.select)
def sel_verts(o): return sorted((round(v.co.x, 2), round(v.co.y, 2)) for v in B(o).verts if v.select)
XS = [-12.5, -7.5, -2.5, 2.5, 7.5, 12.5]            # milieux des six cases
NODES = [-15, -10, -5, 0, 5, 10, 15]
row = lambda y: [(x, y) for x in XS]                # arêtes horizontales (ou faces) d'une rangée
col = lambda x: [(x, y) for y in XS]

# ================= 1. Arêtes =================
SEC = "arêtes"
g = grid(); mode('EDGE'); none(g)
r = dbl(2.5, 0)
chk("double-clic sur une arête : toute sa boucle (les 6 arêtes de la ligne y = 0), rien d'autre", 'FINISHED' in r and sel_edges(g) == row(0), sel_edges(g))
r = dbl(2.5, 5, shift=True)
chk("Maj + double-clic sur une autre ligne : elle s'ajoute", sel_edges(g) == sorted(row(0) + row(5)), len(sel_edges(g)))
r = dbl(-7.5, 0, ctrl=True)
chk("Ctrl + double-clic sur une boucle sélectionnée : elle est retirée", sel_edges(g) == row(5), sel_edges(g))
r = dbl(0, 2.5)
chk("double-clic sans touche sur une arête verticale : la sélection est remplacée par sa colonne", sel_edges(g) == sorted((0, y) for y in XS), sel_edges(g))
none(g); r = dbl(2.5, 0, alt=True)
chk("Alt + double-clic : l'anneau (les 7 arêtes parallèles de la colonne de faces), pas la boucle", 'FINISHED' in r and sel_edges(g) == sorted((2.5, y) for y in NODES), sel_edges(g))
r = dbl(-7.5, 5, alt=True, shift=True)
chk("Maj + Alt + double-clic : un second anneau s'ajoute", sel_edges(g) == sorted([(2.5, y) for y in NODES] + [(-7.5, y) for y in NODES]), len(sel_edges(g)))
r = dbl(2.5, -5, alt=True, ctrl=True)
chk("Ctrl + Alt + double-clic : l'anneau est retiré", sel_edges(g) == sorted((-7.5, y) for y in NODES), sel_edges(g))
none(g); pick(g, edge_at(g, -7.5, 0)); pick(g, edge_at(g, 7.5, 0)); pick(g, edge_at(g, -2.5, 0))        # clic, Maj+clic plus loin, puis le 1er clic du double-clic
r = dbl(-2.5, 0, shift=True)
chk("plage : deux arêtes sélectionnées dans la boucle, Maj + double-clic entre les deux -> seulement les arêtes entre elles (4), pas toute la ligne", sel_edges(g) == [(x, 0) for x in XS[1:5]], sel_edges(g))
none(g); pick(g, edge_at(g, -7.5, 0)); r = dbl(2.5, 0, shift=True)
chk("une seule arête déjà sélectionnée dans la boucle, Maj + double-clic : la boucle entière", sel_edges(g) == row(0), sel_edges(g))
none(g); pick(g, edge_at(g, 2.5, -10)); pick(g, edge_at(g, 2.5, 10)); r = dbl(2.5, 0, shift=True, alt=True)
chk("plage dans un anneau : Maj + Alt + double-clic entre deux barreaux sélectionnés -> les 5 barreaux entre eux", sel_edges(g) == [(2.5, y) for y in NODES[1:6]], sel_edges(g))
none(g); pick(g, edge_at(g, 0, 2.5)); r = dbl(2.5, 0, shift=True, ctrl=True)
chk("Ctrl + Maj + double-clic (sous-objet à la Rhino depuis le mode Objet) : la boucle est AJOUTÉE (elle était retirée)", sel_edges(g) == sorted(row(0) + [(0, 2.5)]), len(sel_edges(g)))
none(g); r = dbl(-15, 2.5)
chk("arête du bord : la boucle fait le tour du contour (24 arêtes)", len(sel_edges(g)) == 24 and all(abs(x) == 15 or abs(y) == 15 for x, y in sel_edges(g)), len(sel_edges(g)))
none(g); r = dbl(2.5, 2.5)
chk("double-clic au milieu d'une face (aucune arête à moins de 10 px) : rien n'est pris, le clic est rendu à Blender", 'PASS_THROUGH' in r and not sel_edges(g), r)
keep = m.PREF_DEFAULTS.get("view_button"); m.PREF_DEFAULTS["view_button"] = 'ALT_LEFT'
r = dbl(2.5, 0, alt=True)
chk("préférence « Alt + clic gauche = navigation » : Alt + double-clic est laissé à la navigation", 'PASS_THROUGH' in r and not sel_edges(g), r)
m.PREF_DEFAULTS["view_button"] = keep

# ================= 2. Faces =================
SEC = "faces"
mode('FACE'); none(g)
pick(g, face_at(g, 2.5, 2.5)); pick(g, face_at(g, 7.5, 2.5)); r = dbl(7.5, 2.5, shift=True)
chk("clic sur une face, puis Maj + double-clic sur sa voisine de droite : la rangée horizontale (6 faces)", 'FINISHED' in r and sel_faces(g) == row(2.5), sel_faces(g))
none(g); pick(g, face_at(g, 2.5, 2.5)); pick(g, face_at(g, 2.5, 7.5)); r = dbl(2.5, 7.5, shift=True)
chk("... sur sa voisine du dessus : la colonne (le sens vient de la face précédente)", sel_faces(g) == col(2.5), sel_faces(g))
none(g); pick(g, face_at(g, 7.5, 2.5)); r = dbl(5.6, 2.5)
chk("sans voisine sélectionnée : le sens vient de l'arête de la face la plus proche du curseur (arête de gauche -> rangée)", sel_faces(g) == row(2.5), sel_faces(g))
none(g); pick(g, face_at(g, 7.5, 2.5)); r = dbl(7.5, 0.6)
chk("... (arête du bas -> colonne)", sel_faces(g) == col(7.5), sel_faces(g))
r = dbl(-9.4, 2.5, shift=True); n1 = len(sel_faces(g))
r = dbl(7.5, -12.4, ctrl=True)
chk("Maj ajoute une rangée, Ctrl + double-clic retire la colonne : il reste la rangée, moins la case commune", n1 == 11 and sel_faces(g) == [p for p in row(2.5) if p[0] != 7.5], (n1, sel_faces(g)))
none(g); pick(g, face_at(g, -7.5, 2.5)); pick(g, face_at(g, 7.5, 2.5)); pick(g, face_at(g, -2.5, 2.5)); r = dbl(-2.5, 2.5, shift=True)
chk("plage de faces : entre deux faces sélectionnées de la rangée -> les 4 faces entre elles", sel_faces(g) == [(x, 2.5) for x in XS[1:5]], sel_faces(g))
chk("mode faces : aucune arête ni sommet isolé n'est sélectionné en plus", all(e.select == all(f.select for f in e.link_faces) or any(f.select for f in e.link_faces) for e in B(g).edges if e.select), "")
none(g); r = dbl(40, 40)
chk("double-clic à côté du maillage : rien, le clic est rendu à Blender", 'PASS_THROUGH' in r and not sel_faces(g), r)

# ================= 3. Sommets =================
SEC = "sommets"
mode('VERT'); none(g)
pick(g, vert_at(g, 0, 0)); pick(g, vert_at(g, 5, 0)); r = dbl(5, 0, shift=True)
chk("clic sur un sommet, puis Maj + double-clic sur son voisin de droite : la chaîne horizontale (7 sommets)", 'FINISHED' in r and sel_verts(g) == [(x, 0) for x in NODES], sel_verts(g))
none(g); pick(g, vert_at(g, 0, 0)); pick(g, vert_at(g, 0, 5)); r = dbl(0, 5, shift=True)
chk("... sur son voisin du dessus : la chaîne verticale", sel_verts(g) == [(0, y) for y in NODES], sel_verts(g))
none(g); r = dbl(2.5, 5)
chk("sans sommet visé : la boucle de l'arête la plus proche, comme avant", sel_verts(g) == [(x, 5) for x in NODES], sel_verts(g))
r = dbl(-7.5, 5, ctrl=True)
chk("Ctrl + double-clic : la chaîne est retirée", not sel_verts(g), sel_verts(g))

# ================= 4. Boucles fermées (tube de 8 faces) =================
SEC = "fermées"
t = new_mesh("Tube", lambda bm: bmesh.ops.create_cone(bm, cap_ends=False, segments=8, radius1=5, radius2=5, depth=10))
bm = B(t)
rim = next(e for e in bm.edges if e.verts[0].co.z > 4 and e.verts[1].co.z > 4)
side = next(e for e in bm.edges if abs(e.verts[0].co.z - e.verts[1].co.z) > 9)
p, c = m.edge_loop_path(rim)
chk("boucle du bord haut d'un tube : 8 arêtes, fermée, dans l'ordre (chaque arête touche la suivante)", len(p) == 8 and c and all(set(p[i].verts) & set(p[(i + 1) % 8].verts) for i in range(8)), (len(p), c))
p, c = m.edge_loop_path(side)
chk("boucle d'une génératrice : elle seule (ses deux bouts sont sur le bord)", len(p) == 1 and not c, (len(p), c))
p, c = m.edge_ring_path(side)
chk("anneau d'une génératrice : les 8 génératrices, fermé", len(p) == 8 and c and all(abs(e.verts[0].co.z - e.verts[1].co.z) > 9 for e in p), (len(p), c))
p, c = m.edge_ring_path(rim)
chk("anneau d'une arête du bord : elle et celle d'en face (2)", len(p) == 2 and not c, (len(p), c))
f = side.link_faces[0]
p, c = m.face_loop_path(f, side)
chk("rangée de faces autour du tube : 8 faces, fermée", len(p) == 8 and c and len(set(p)) == 8, (len(p), c))
p, c = m.face_loop_path(f, next(e for e in f.edges if e.verts[0].co.z > 4 and e.verts[1].co.z > 4))
chk("rangée dans l'autre sens : la face seule (bord des deux côtés)", len(p) == 1 and not c, (len(p), c))
p, c = m.edge_ring_path(side); p[1].select_set(True); p[5].select_set(True)
part = m.loop_range(p, c, 3, lambda x: x.select)
chk("plage dans une boucle fermée : de la 2e à la 6e en passant par la 4e (5 éléments), pas par l'autre côté", part is not None and part == p[1:6], None if part is None else len(part))
p[5].select_set(False)
chk("un seul élément sélectionné dans une boucle fermée : pas de plage (boucle entière)", m.loop_range(p, c, 3, lambda x: x.select) is None)
mode('EDGE'); bpy.ops.object.mode_set(mode='OBJECT')

summary()
