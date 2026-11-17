# Cartouche modifiable directement : sur la feuille comme un tableau (on glisse son bord, ses séparations, on ajoute une
# colonne ou une rangée), puis en dessin libre comme dans AutoCAD (traits, textes à champs, logo sur le calque
# « Title block »). Tout est mesuré en millimètres de papier.
import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
exec(open(_os.path.join(_HERE,'prec_lib.py')).read())
import contextlib, io, time
from mathutils import Vector
BC = bpy.context
SEC = "?"
def chk(name, ok, meas=""): rec(SEC, name, ok, meas)
space.show_gizmo_navigate = False


def reset():
    try:
        if m.is_layout(BC.window.scene):
            m.layout_close(BC)
    except Exception:
        pass
    for sc in list(bpy.data.scenes):
        if m.is_layout(sc):
            for o in list(sc.objects): bpy.data.objects.remove(o)
            bpy.data.scenes.remove(sc)
    clear()
    m.layout_on_load()
    us = BC.scene.unit_settings; us.system = 'METRIC'; us.scale_length = 1.0; us.length_unit = 'METERS'
    return BC.scene


def r4(t): return tuple(round(float(v), 4) for v in t)
def rect(D): return r4(m.title_layout(D)[0])
def cellrect(D, i): return r4(m.title_layout(D)[1][i][1:])
def heights(D): return [round(h, 4) for h in m.title_layout(D)[2]]
def labels(D): return [c.label for c in D.title_cells]
def starts(D): return [i for i, c in enumerate(D.title_cells) if c.new_row or i == 0]
def sheet_texts(L): return [o.data.body for o in L.objects if o.type == 'FONT' and o.get("wd_layout_gen")]
def title_lines(L):
    out = []
    for o in L.objects:
        if o.get("wd_layout_gen") in ('frame', 'title') and o.type == 'CURVE' and o.name.startswith("Title"):
            for sp in o.data.splines:
                out.append(tuple(r4(p.co[:2]) for p in sp.points))
    return out


move = lambda x, y: ev('MOUSEMOVE', 'NOTHING', *scr(x, y))
press = lambda x, y: ev('LEFTMOUSE', 'PRESS', *scr(x, y))
release = lambda x, y: ev('LEFTMOUSE', 'RELEASE', *scr(x, y))
dbl = lambda x, y: ev('LEFTMOUSE', 'DOUBLE_CLICK', *scr(x, y))
key = lambda k, **kw: ev(k, 'PRESS', *scr(20, 8), **kw)


def send(o, evs):
    r = {'RUNNING_MODAL'}
    for e in evs:
        with contextlib.redirect_stdout(io.StringIO()):
            r = type(o).modal(o, ctx, e)
        if 'FINISHED' in r or 'CANCELLED' in r:
            break
    BC.view_layer.update()
    return r


def enter(x=None, y=None):
    o = make(m.DESSIN_OT_title_edit)
    o.pick = x is not None
    with contextlib.redirect_stdout(io.StringIO()):
        r = type(o).invoke(o, ctx, dbl(x, y) if x is not None else ev('NONE', 'NOTHING', *scr(0, 0)))
    return o, r


# ---------------------------------------------------------------- A. ce qui se glisse, en millimètres
SEC = "traits"
model = reset()
L = m.layout_create(model, "Plan", 'A3', 'LANDSCAPE', 10.0, True)
m.layout_open(BC, L)
D = L.dessin_layout
HD = m.title_handles(D)
kinds = sorted(k + str(i) for k, i, _a, _b in HD)
chk("modèle Classic : 9 traits se glissent (le bord gauche, le haut, 2 traits entre rangées, 5 séparations de cases)",
    kinds == sorted(["W-1", "H-1", "H0", "H1", "V0", "V2", "V3", "V5", "V6"]), kinds)
chk("... le bord libre est le côté gauche du bloc (x = 240), le bas et la droite tiennent au cadre",
    next((a, b) for k, i, a, b in HD if k == 'W') == ((240.0, 10.0), (240.0, 44.0)), [h for h in HD if h[0] == 'W'])
chk("title_hit : sur la séparation PROJECT | SHEET (x = 376), à 0,3 mm près", m.title_hit(D, 376.3, 38.0, 0.5) == ('V', 0), m.title_hit(D, 376.3, 38.0, 0.5))
chk("... au milieu de la case TITLE : la case 2", m.title_hit(D, 300.0, 25.0, 0.5) == ('C', 2), m.title_hit(D, 300.0, 25.0, 0.5))
chk("... hors du cartouche : rien", m.title_hit(D, 100.0, 100.0, 0.5) is None)
with m.quiet():
    ok = m.title_drag(D, 'W', -1, 200.0, 20.0)
chk("bord gauche glissé à x = 200 : le bloc s'étire à 210 mm de large, toujours tenu à droite", ok and rect(D) == (200.0, 10.0, 410.0, 44.0) and near(D.title_w, 210.0), rect(D))
with m.quiet():
    m.title_drag(D, 'W', -1, 405.0, 20.0)
chk("... on ne peut pas le réduire à moins de 20 mm", near(D.title_w, 20.0), D.title_w)
with m.quiet():
    m.title_drag(D, 'W', -1, -500.0, 20.0)
chk("... ni l'étirer au-delà du cadre (400 mm)", near(D.title_w, 400.0), D.title_w)
with m.quiet():
    m.title_drag(D, 'W', -1, 200.0, 20.0)
    ok = m.title_drag(D, 'V', 0, 350.0, 38.0)
chk("séparation PROJECT | SHEET glissée à x = 350 : PROJECT fait 150 mm, SHEET 60 mm (les deux se partagent leur largeur)",
    ok and cellrect(D, 0) == (200.0, 31.0, 350.0, 44.0) and cellrect(D, 1) == (350.0, 31.0, 410.0, 44.0), (cellrect(D, 0), cellrect(D, 1)))
chk("... les autres rangées ne bougent pas", cellrect(D, 2)[2] == round(200.0 + 210.0 * 106.0 / 170.0, 4), cellrect(D, 2))
with m.quiet():
    m.title_drag(D, 'V', 0, 409.9, 38.0)
chk("... une case garde au moins 3 mm de large", near(cellrect(D, 1)[2] - cellrect(D, 1)[0], 3.0), cellrect(D, 1))
with m.quiet():
    m.title_drag(D, 'V', 0, 350.0, 38.0)
    ok = m.title_drag(D, 'H', -1, 300.0, 50.0)
chk("bord du haut glissé à y = 50 : la rangée du haut passe de 13 à 19 mm, le bloc grandit vers le haut", ok and heights(D) == [19.0, 12.0, 9.0] and rect(D) == (200.0, 10.0, 410.0, 50.0), (heights(D), rect(D)))
with m.quiet():
    ok = m.title_drag(D, 'H', 0, 300.0, 35.0)
chk("trait entre les rangées 1 et 2 glissé à y = 35 : la rangée du dessous (tenue par le bas) passe à 16 mm, celle du dessus garde 19 mm",
    ok and heights(D) == [19.0, 16.0, 9.0] and rect(D) == (200.0, 10.0, 410.0, 54.0), (heights(D), rect(D)))
with m.quiet():
    m.title_drag(D, 'H', 1, 300.0, 10.5)
chk("... une rangée garde au moins 3 mm de haut", heights(D)[2] == 3.0, heights(D))
bpy.ops.dessin.title_preset(preset='CLASSIC')
D.title_pos = 'TL'
HD = m.title_handles(D)
chk("bloc en haut à gauche : le bord libre est à droite (x = 180) et le trait du bas se glisse",
    next((a, b) for k, i, a, b in HD if k == 'W') == ((180.0, 253.0), (180.0, 287.0)) and ('H', 2) in [(k, i) for k, i, _a, _b in HD]
    and ('H', -1) not in [(k, i) for k, i, _a, _b in HD], [(k, i) for k, i, _a, _b in HD])
with m.quiet():
    m.title_drag(D, 'H', 0, 50.0, 270.0)
chk("... trait sous la rangée du haut glissé à y = 270 : c'est elle (tenue par le haut) qui passe à 17 mm", heights(D) == [17.0, 12.0, 9.0] and rect(D) == (10.0, 249.0, 180.0, 287.0), (heights(D), rect(D)))
with m.quiet():
    m.title_drag(D, 'W', -1, 130.0, 270.0)
chk("... bord droit glissé à x = 130 : le bloc fait 120 mm", rect(D)[2] == 130.0, rect(D))
bpy.ops.dessin.title_preset(preset='SIDE')
h0 = heights(D)
with m.quiet():
    ok = m.title_drag(D, 'H', 0, 380.0, 247.0)
chk("bandeau vertical : le trait sous le logo glissé de 10 mm vers le bas agrandit la rangée du logo (40 mm), la rangée NOTES absorbe",
    ok and heights(D)[0] == 40.0 and near(heights(D)[1], h0[1] - 10.0) and near(sum(heights(D)), 277.0) and heights(D)[2:] == h0[2:], (h0, heights(D)))
with m.quiet():
    ok = m.title_drag(D, 'H', 1, 380.0, 100.0)
chk("... le trait sous NOTES glissé à y = 100 : la rangée PROJECT (tenue par le bas) grandit, NOTES reste extensible",
    ok and near(heights(D)[2], 100.0 - (16 + 10 + 10 + 14) - 10.0) and D.title_cells[1].height == 0.0 and near(sum(heights(D)), 277.0), heights(D))
chk("... un bandeau du bas n'a pas de bord de largeur à glisser", (bpy.ops.dessin.title_preset(preset='STRIP'), [h for h in m.title_handles(D) if h[0] == 'W'])[1] == [])

# ---------------------------------------------------------------- B. colonnes et rangées
SEC = "colonnes, rangées"
bpy.ops.dessin.title_preset(preset='CLASSIC')
D.title_cell_index = 2                                   # TITLE (106 sur 170, rangée du milieu)
w0 = cellrect(D, 2)
r = bpy.ops.dessin.title_cell_add(where='COLUMN')
chk("Ajouter une colonne : la case TITLE est partagée en deux (2 x 53 mm), la nouvelle à sa droite devient la case active",
    r == {'FINISHED'} and len(D.title_cells) == 9 and D.title_cell_index == 3 and near(cellrect(D, 2)[2] - cellrect(D, 2)[0], 53.0)
    and near(cellrect(D, 3)[2] - cellrect(D, 3)[0], 53.0) and cellrect(D, 3)[2] == w0[2] and not D.title_cells[3].new_row,
    (len(D.title_cells), cellrect(D, 2), cellrect(D, 3)))
chk("... le reste de la rangée (SCALE, DATE) et les autres rangées ne bougent pas", labels(D) == ["PROJECT", "SHEET", "TITLE", "", "SCALE", "DATE", "DRAWN BY", "REV", "FORMAT"]
    and starts(D) == [0, 2, 6] and heights(D) == [13.0, 12.0, 9.0], (labels(D), starts(D)))
r = bpy.ops.dessin.title_cell_add(where='ROW')
chk("Ajouter une rangée : une rangée d'une case, de la même hauteur (12 mm), sous la rangée de la case active", r == {'FINISHED'} and starts(D) == [0, 2, 6, 7]
    and D.title_cell_index == 6 and heights(D) == [13.0, 12.0, 12.0, 9.0] and cellrect(D, 6) == (240.0, 19.0, 410.0, 31.0), (starts(D), heights(D), cellrect(D, 6)))
D.title_cell_index = 0
r = bpy.ops.dessin.title_cell_add(where='ROW_ABOVE')
chk("Rangée au-dessus de la première : elle prend la tête du cartouche, PROJECT commence toujours sa rangée", starts(D) == [0, 1, 3, 7, 8] and D.title_cell_index == 0
    and D.title_cells[1].label == "PROJECT" and heights(D) == [13.0, 13.0, 12.0, 12.0, 9.0], (starts(D), heights(D)))
r = bpy.ops.dessin.title_cell_remove()
chk("Supprimer une case seule dans sa rangée : la rangée disparaît", r == {'FINISHED'} and starts(D) == [0, 2, 6, 7] and D.title_cells[0].label == "PROJECT", (starts(D), labels(D)))
D.title_cell_index = 3
bpy.ops.dessin.title_cell_remove()
chk("Supprimer la colonne ajoutée : ses voisines reprennent la place (TITLE 53 / 117 de 170 mm)", len(D.title_cells) == 9 and near(cellrect(D, 2)[2] - cellrect(D, 2)[0], 170.0 * 53.0 / 117.0),
    cellrect(D, 2))
r = bpy.ops.dessin.title_cell_add()
chk("Ajouter une case (ancienne commande) : une case « LABEL » de largeur 1 après la case active", r == {'FINISHED'} and D.title_cells[D.title_cell_index].label == "LABEL"
    and near(D.title_cells[D.title_cell_index].width, 1.0), labels(D))
tx = sheet_texts(L)
chk("... la feuille est redessinée à chaque fois (le libellé de la nouvelle case y est)", "LABEL" in tx, tx)

# ---------------------------------------------------------------- C. sur la feuille, à la souris
SEC = "sur la feuille"
model = reset()
L = m.layout_create(model, "Plan", 'CUSTOM', custom=(48.0, 48.0), margin=2.0, title=True)
m.layout_open(BC, L)
D = L.dessin_layout
bpy.ops.dessin.title_preset(preset='COMPACT')
D.title_w = 40.0
chk("feuille d'essai : cartouche d'une rangée de 40 x 12 mm en bas à droite, 3 cases", rect(D) == (6.0, 2.0, 46.0, 14.0) and len(D.title_cells) == 3, rect(D))
o, r = enter(20.0, 30.0)
chk("double-clic hors du cartouche : rien ne démarre, le clic garde son usage", r == {'CANCELLED', 'PASS_THROUGH'} and m._TITLE_EDIT["scene"] is None, r)
o, r = enter(34.0, 8.0)
chk("double-clic sur le cartouche : on le modifie (la case cliquée, SCALE, devient la case active)", r == {'RUNNING_MODAL'} and m._TITLE_EDIT["scene"] == L.name
    and D.title_cell_index == 1 and m.title_editing(), (r, D.title_cell_index))
x_sep = cellrect(D, 0)[2]
r = send(o, [move(x_sep + 0.2, 8.0)])
chk("survol d'une séparation : elle est retenue (dessinée en gras, curseur de déplacement)", m._TITLE_EDIT["hover"] == ('V', 0), m._TITLE_EDIT["hover"])
r = send(o, [press(x_sep + 0.2, 8.0), move(20.0, 8.0), move(22.0, 9.0), release(22.0, 9.0)])
chk("séparation glissée à x = 22 : TITLE fait 16 mm, SCALE prend le reste jusqu'à SHEET", 'RUNNING_MODAL' in r and near(cellrect(D, 0)[2], 22.0) and near(cellrect(D, 1)[0], 22.0)
    and near(cellrect(D, 1)[2], 6.0 + 40.0 * 95.0 / 120.0) and m._TITLE_EDIT["drag"] is None, (cellrect(D, 0), cellrect(D, 1)))
chk("... les traits de la feuille suivent pendant qu'on glisse", any(near(a[0], 22.0) and near(b[0], 22.0) for a, b in title_lines(L)), title_lines(L))
r = send(o, [press(6.1, 8.0), move(16.0, 8.0), release(16.0, 8.0)])
chk("bord gauche glissé à x = 16 : le bloc fait 30 mm de large", near(D.title_w, 30.0) and rect(D) == (16.0, 2.0, 46.0, 14.0), rect(D))
r = send(o, [press(30.0, 14.1), move(30.0, 20.0), release(30.0, 20.0)])
chk("bord du haut glissé à y = 20 : la rangée fait 18 mm", heights(D) == [18.0] and rect(D) == (16.0, 2.0, 46.0, 20.0), (heights(D), rect(D)))
r = send(o, [press(44.0, 10.0), release(44.0, 10.0)])
chk("clic dans une case : elle devient la case active (SHEET)", D.title_cell_index == 2 and labels(D)[2] == "SHEET", D.title_cell_index)
r = send(o, [key('C')])
chk("touche C : la case active est partagée en deux colonnes", len(D.title_cells) == 4 and D.title_cell_index == 3 and near(cellrect(D, 3)[2], 46.0)
    and near(cellrect(D, 2)[2] - cellrect(D, 2)[0], cellrect(D, 3)[2] - cellrect(D, 3)[0]), (len(D.title_cells), cellrect(D, 2), cellrect(D, 3)))
r = send(o, [key('R')])
chk("touche R : une rangée sous la rangée active", starts(D) == [0, 4] and D.title_cell_index == 4 and heights(D) == [18.0, 18.0], (starts(D), heights(D)))
r = send(o, [key('R', shift=True)])
chk("Maj + R : une rangée au-dessus", starts(D) == [0, 4, 5] and D.title_cell_index == 4, starts(D))
r = send(o, [key('X'), key('X')])
chk("touche X deux fois : les deux rangées ajoutées sont retirées", starts(D) == [0] and len(D.title_cells) == 4, (starts(D), len(D.title_cells)))
r = send(o, [key('TAB')])
i0 = D.title_cell_index
r = send(o, [key('TAB', shift=True)])
chk("Tab / Maj + Tab : case suivante / précédente", D.title_cell_index == (i0 - 1) % 4, (i0, D.title_cell_index))
r = send(o, [press(30.0, 10.0), move(28.0, 12.0), release(28.0, 12.0)])
chk("clic dans une case avec un petit tremblement : le bloc ne change pas de coin", D.title_pos == 'BR', D.title_pos)
r = send(o, [press(30.0, 10.0), move(20.0, 30.0), move(12.0, 40.0), release(12.0, 40.0)])
chk("bloc glissé vers le haut à gauche : il va dans ce coin du cadre", D.title_pos == 'TL' and rect(D) == (2.0, 28.0, 32.0, 46.0), (D.title_pos, rect(D)))
r = send(o, [press(10.0, 40.0), move(40.0, 6.0), release(40.0, 6.0)])
chk("... et revient en bas à droite de la même façon", D.title_pos == 'BR' and rect(D) == (16.0, 2.0, 46.0, 20.0), (D.title_pos, rect(D)))
r = send(o, [press(15.5, 10.0), release(15.5, 10.0)])
chk("clic manqué de peu (0,5 mm hors du bloc) : on reste dans le cartouche", 'RUNNING_MODAL' in r and m._TITLE_EDIT["scene"] == L.name, r)
area.regions.append(Region(type='UI', x=900, y=0, width=100, height=1000, data=None))
r = send(o, [press(42.0, 10.0)])
chk("clic sur un panneau qui recouvre la vue : il passe au panneau (les réglages restent utilisables)", r == {'PASS_THROUGH'}, r)
area.regions.pop()
r = send(o, [press(20.0, 40.0)])
chk("clic ailleurs sur la feuille : fini, la commande est validée et le clic garde son usage", r == {'FINISHED', 'PASS_THROUGH'} and m._TITLE_EDIT["scene"] is None and not m.title_editing(), r)
o, r = enter(30.0, 10.0)
r = send(o, [ev('ESC', 'PRESS', *scr(30, 10))])
chk("Échap sans rien avoir changé : la commande est annulée (rien dans l'historique)", r == {'CANCELLED'} and m._TITLE_EDIT["scene"] is None, r)
D.show_title = False
o, r = enter()
chk("bouton « Edit on the Sheet » : le cartouche masqué est affiché et on le modifie", r == {'RUNNING_MODAL'} and D.show_title and m.title_editing(), r)
o2, r2 = enter()
chk("... le même bouton pressé une seconde fois : la modification se termine", r2 == {'CANCELLED'} and send(o, [move(30.0, 10.0)]) == {'FINISHED'} and not m.title_editing(), r2)
o, r = enter(30.0, 10.0)
D.show_title = False
r = send(o, [move(30.0, 10.0)])
chk("cartouche masqué pendant qu'on le modifie : la commande s'arrête d'elle-même", ('FINISHED' in r or 'CANCELLED' in r) and m._TITLE_EDIT["scene"] is None, r)
D.show_title = True
D.title_cell_index = 0
r = bpy.ops.dessin.title_cell_edit(label="CLIENT", text="Mairie <Sheet>", size=2.0, align='CENTER')
c = D.title_cells[0]
chk("texte d'une case (double-clic) : libellé, texte à champ, hauteur et alignement sont écrits dans la case et sur la feuille",
    r == {'FINISHED'} and (c.label, c.text, c.size, c.align) == ("CLIENT", "Mairie <Sheet>", 2.0, 'CENTER') and "Mairie 01" in sheet_texts(L), sheet_texts(L))
m.title_edit_draw()
m._TITLE_EDIT.update(scene=L.name, hover=('V', 0), drag=None)
m.title_edit_draw()
m.title_edit_reset()
chk("le dessin de la case active et des traits ne lève pas d'erreur", True)

# ---------------------------------------------------------------- D. cartouche libre
SEC = "cartouche libre"
model = reset()
L = m.layout_create(model, "Plan", 'A3', 'LANDSCAPE', 10.0, True)
m.layout_open(BC, L)
D = L.dessin_layout
D.t_project = "Villa"; D.t_title = "Plans"; D.t_revision = "B"
r = bpy.ops.dessin.title_explode()
free = m.title_free_objects(L)
col = m.layout_collection(L, 'title', False)
curves = [o for o in free if o.type == 'CURVE']
texts = [o for o in free if o.type == 'FONT']
chk("Convert to Free Drawing : le cartouche généré est masqué, ses objets sont sur le calque « Title block »", r == {'FINISHED'} and not D.show_title
    and col is not None and col.name == "Title block" and not [o for o in L.objects if o.get("wd_layout_gen") == 'title'], (r, D.show_title))
out = [o for o in curves if o.data.splines[0].use_cyclic_u]
chk("... un rectangle fermé de 170 x 34 mm pour le contour, à l'épaisseur du cadre (0,5 mm)", len(out) == 1 and near(out[0].get("wd_lw", 0.0), 0.5)
    and near(sorted(r4(p.co[:2]) for p in out[0].data.splines[0].points), [(240, 10), (240, 44), (410, 10), (410, 44)]), [o.name for o in out])
seg = sorted(tuple(r4(p.co[:2]) for p in o.data.splines[0].points) for o in curves if not o.data.splines[0].use_cyclic_u)
chk("... un trait par séparation : 2 traits entre les rangées et 5 entre les cases, chacun son objet", len(seg) == 7
    and ((240.0, 31.0), (410.0, 31.0)) in seg and ((240.0, 19.0), (410.0, 19.0)) in seg and ((376.0, 31.0), (376.0, 44.0)) in seg, seg)
chk("... aucun de ces objets n'est verrouillé : on les retouche avec les outils habituels", not [o for o in free if o.hide_select or o.get("wd_layout_gen") or o.get("wd_gen")])
bodies = sorted(o.data.body for o in texts)
chk("... les textes : libellés et valeurs, les champs remplis (Villa, Plans, B, 01, A3)", all(t in bodies for t in ("PROJECT", "SHEET", "Villa", "Plans", "B", "01", "A3")), bodies)
sh = next(o for o in texts if o.get("wd_field") == "<Sheet>")
D.t_number = "07"
m.layout_sync(L)
chk("... un texte à champ reste automatique : le numéro de planche changé dans le panneau y est reporté", sh.data.body == "07", sh.data.body)
ents = m.layout_entities(L)
def plen(P, closed):
    P = np.asarray(P, dtype=float)
    Q = np.vstack([P, P[:1]]) if closed else P
    return float(np.hypot(*(Q[1:] - Q[:-1]).T).sum())
ln = sum(plen(P, c) for e in ents if e[0] == 'L' and e[-1] == "Sheet" for P, c in e[1])
chk("... le cartouche libre est imprimé : 803 mm de traits (contour 408, rangées 340, cases 55)", near(ln, 803.0, 1e-3), ln)
r = bpy.ops.dessin.title_explode()
chk("... convertir une seconde fois ne double rien", r == {'CANCELLED'} and len(m.title_free_objects(L)) == len(free), len(m.title_free_objects(L)))
r = bpy.ops.dessin.title_free_select()
chk("Select the Title Block : tous ses objets sont sélectionnés", r == {'FINISHED'} and all(o.select_get() for o in free))
L2 = m.layout_create(model, "Coupes", 'A3', 'LANDSCAPE', 10.0, True)
f2 = m.title_free_objects(L2)
chk("nouvelle mise en page : elle reçoit le cartouche libre (mêmes objets, des copies), pas le cartouche généré",
    len(f2) == len(free) and not L2.dessin_layout.show_title and not set(f2) & set(free) and not {o.data for o in f2 if o.type != 'EMPTY'} & {o.data for o in free}, len(f2))
chk("... ses champs sont ceux de sa planche : numéro 02, titre « Coupes »", "02" in [o.data.body for o in f2 if o.type == 'FONT'] and "Coupes" in [o.data.body for o in f2 if o.type == 'FONT'],
    sorted(o.data.body for o in f2 if o.type == 'FONT'))
L3 = m.layout_create(model, "Sans", 'A3', 'LANDSCAPE', 10.0, False)
chk("mise en page créée sans cartouche : elle n'en reçoit aucun", not m.title_free_objects(L3) and not L3.dessin_layout.show_title)
mv = next(o for o in free if o.type == 'CURVE' and not o.data.splines[0].use_cyclic_u)
mv.location.x += 5.0
BC.view_layer.update()
r = bpy.ops.dessin.title_copy_all()
f2 = m.title_free_objects(L2)
chk("Copy to All Layouts : le cartouche libre retouché remplace celui des autres planches (y compris celle qui n'en avait pas)",
    r == {'FINISHED'} and len(f2) == len(free) and len(m.title_free_objects(L3)) == len(free) and any(near(o.location.x, 5.0) for o in f2), len(f2))
BC.window.scene = L2
r = bpy.ops.dessin.layout_duplicate()
L4 = BC.window.scene
chk("Duplicate Layout : la copie a le cartouche libre une seule fois", m.is_layout(L4) and L4 != L2 and len(m.title_free_objects(L4)) == len(free)
    and not L4.dessin_layout.show_title, (L4.name, len(m.title_free_objects(L4))))
BC.window.scene = L
r = bpy.ops.dessin.title_preset(preset='COMPACT')
chk("Back to a Template : le cartouche libre est retiré, le cartouche généré revient", r == {'FINISHED'} and not m.title_free_objects(L) and D.show_title
    and [o for o in L.objects if o.get("wd_layout_gen") == 'title'], len(m.title_free_objects(L)))
r = bpy.ops.dessin.title_copy_all()
chk("... et Copy to All Layouts le reporte partout : plus de cartouche libre nulle part", not m.title_free_objects(L2) and L2.dessin_layout.show_title
    and len(L2.dessin_layout.title_cells) == 3, len(m.title_free_objects(L2)))

# ---------------------------------------------------------------- E. panneau
SEC = "panneau"


class FakeLayout:
    def __getattr__(self, n):
        def f(*a, **k):
            return FakeLayout()
        return f

    def __setattr__(self, n, v):
        pass


bad = []
for state in ("modèle", "modification", "libre"):
    try:
        if state == "modification":
            m._TITLE_EDIT.update(scene=L.name, hover=None, drag=None, beat=time.monotonic())
        if state == "libre":
            m.title_edit_reset()
            bpy.ops.dessin.title_explode()
        p = types.SimpleNamespace(layout=FakeLayout())
        m.DESSIN_PT_layout_title.draw(p, BC)
        m.DESSIN_PT_layout_title.draw_header(p, BC)
    except Exception as e:
        bad.append((state, repr(e)))
chk("le panneau Title Block se dessine dans ses trois états : modèle, modification sur la feuille, cartouche libre", not bad, bad)
km = [k for k in bpy.context.window_manager.keyconfigs.addon.keymaps["Object Mode"].keymap_items if k.idname in ("dessin.detail_pan", "dessin.title_edit")] \
    if bpy.context.window_manager.keyconfigs.addon else None
chk("double-clic : la commande des fenêtres est essayée d'abord, puis celle du cartouche", km is None or [k.idname for k in km] == ["dessin.detail_pan", "dessin.title_edit"],
    None if km is None else [k.idname for k in km])
summary()
