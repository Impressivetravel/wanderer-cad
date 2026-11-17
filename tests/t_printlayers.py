# Réglages d'impression des calques, comme dans AutoCAD et Rhino : imprimé ou non, épaisseur de trait, couleur
# d'impression ; épaisseur propre à un objet ; modes de couleur de la mise en page (noir, couleurs, niveaux de gris).
# Tout est mesuré sur ce qui part à l'impression : entités d'export (mm de papier) et contenu du PDF.
import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
exec(open(_os.path.join(_HERE,'prec_lib.py')).read())
import os, shutil, tempfile, zlib, re
from mathutils import Vector
le = m.le
BC = bpy.context
TMP = tempfile.mkdtemp(prefix="wd_print_")
SEC = "?"
def chk(name, ok, meas=""): rec(SEC, name, ok, meas)


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
    for c in list(bpy.data.collections): bpy.data.collections.remove(c)
    m.layout_on_load()
    us = BC.scene.unit_settings; us.system = 'METRIC'; us.scale_length = 1.0; us.length_unit = 'METERS'
    return BC.scene


def layer(name, parent=None):
    c = bpy.data.collections.new(name)
    (parent or BC.scene.collection).children.link(c)
    return c


def box(name, col, sx, sy, sz, loc):
    me = bpy.data.meshes.new(name); bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=bm.verts); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); o.location = loc
    col.objects.link(o)
    return o


def line(name, col, a, b):
    cu = bpy.data.curves.new(name, 'CURVE'); cu.dimensions = '3D'
    sp = cu.splines.new('POLY'); sp.points.add(1)
    sp.points[0].co = (a[0], a[1], 0.0, 1.0); sp.points[1].co = (b[0], b[1], 0.0, 1.0)
    o = bpy.data.objects.new(name, cu)
    col.objects.link(o)
    return o


def ebox(e):
    P = np.vstack([np.asarray(p, dtype=float)[:, :2] for p, _c in e[1]])
    return tuple(round(float(v), 3) for v in (P[:, 0].min(), P[:, 1].min(), P[:, 0].max(), P[:, 1].max()))


def at(ents, rect, kind="Visible"):
    """Traits imprimés dont l'emprise est exactement `rect` (mm de papier)."""
    return [e for e in ents if e[0] == 'L' and e[-1] == kind and near(ebox(e), rect, 1e-3)]


def r3(c): return tuple(round(float(v), 3) for v in c[:3])
def kids(det, role): return [c for c in det.children if c.get("wd_gen") == role]
def refresh():
    BC.view_layer.update()
    m.layout_on_depsgraph(model)             # (dans Blender, c'est la mise à jour de la scène qui signale le changement)
    m.detail_rebuild(d, force=True)
    return m.layout_entities(L)


RW, RF, RC, RA = (30.0, 45.0, 50.0, 55.0), (65.0, 45.0, 75.0, 55.0), (67.5, 67.5, 72.5, 72.5), (20.0, 30.0, 80.0, 30.0)

# ---------------------------------------------------------------- A. par défaut : rien ne change
SEC = "par défaut"
model = reset()
walls, furn, axes = layer("Walls"), layer("Furniture"), layer("Axes")
chairs = layer("Chairs", furn)
A = box("A", walls, 2.0, 1.0, 0.5, (0, 0, 0.25))
B = box("B", furn, 1.0, 1.0, 1.0, (3, 0, 0.5))
Cc = box("C", chairs, 0.5, 0.5, 0.5, (3, 2, 0.25))
Ax = line("Axis", axes, (-2, -2), (4, -2))
BC.view_layer.update()
L = m.layout_create(model, "Plan", 'CUSTOM', custom=(100.0, 100.0), margin=2.0, title=False)
m.layout_open(BC, L)
D = L.dessin_layout
d = m.detail_create(L, 50.0, 50.0, 90.0, 90.0, 'TOP', scale=100.0, fit=False)
with m.quiet():
    d.dessin_detail.center = (1.0, 0.0, 0.0)
ents = refresh()
st = m.print_styles()
chk("chaque calque est imprimé, à l'épaisseur et à la couleur de la mise en page", all(st[n] == (True, 0.0, None) for n in ("Walls", "Furniture", "Chairs", "Axes")), st)
chk("les traits de la fenêtre gardent leur calque : un groupe par calque du modèle", sorted({c.get("wd_layer") for c in kids(d, 'vis')}) == ["Axes", "Chairs", "Furniture", "Walls"],
    sorted({c.get("wd_layer") for c in kids(d, 'vis')}))
chk("impression : les 4 objets sont là, en noir, à 0,35 mm", all(len(at(ents, r)) == 1 and near(at(ents, r)[0][2], 0.35) and r3(at(ents, r)[0][3]) == (0, 0, 0) for r in (RW, RF, RC, RA)),
    [(ebox(e), e[2]) for e in ents if e[0] == 'L'])

# ---------------------------------------------------------------- B. imprimé ou non
SEC = "imprimé ou non"
furn.dessin_layer.plot = False
ents = m.layout_entities(L)
chk("calque Furniture non imprimé : son objet n'est plus dans l'impression, ni celui de son sous-calque Chairs", not at(ents, RF) and not at(ents, RC) and at(ents, RW) and at(ents, RA),
    [ebox(e) for e in ents if e[0] == 'L' and e[-1] == "Visible"])
grey = [r3(c.color) for c in kids(d, 'vis') if c.get("wd_layer") in ("Furniture", "Chairs")]
chk("... à l'écran, sur la feuille, ils restent visibles en gris clair (sans rien recalculer)", grey == [r3(m.NOPLOT_GREY)] * 2
    and all(r3(c.color) == (0, 0, 0) for c in kids(d, 'vis') if c.get("wd_layer") in ("Walls", "Axes")), grey)
chairs.dessin_layer.plot = False
furn.dessin_layer.plot = True
ents = m.layout_entities(L)
chk("sous-calque seul non imprimé : son parent s'imprime, pas lui", at(ents, RF) and not at(ents, RC))
chk("... le parent retrouve sa couleur à l'écran", [r3(c.color) for c in kids(d, 'vis') if c.get("wd_layer") == "Furniture"] == [(0.0, 0.0, 0.0)])
chairs.dessin_layer.plot = True
ents = m.layout_entities(L)
chk("tout réimprimé : les 4 objets reviennent", all(at(ents, r) for r in (RW, RF, RC, RA)) and all(r3(c.color) == (0, 0, 0) for c in kids(d, 'vis')))

# ---------------------------------------------------------------- C. épaisseurs
SEC = "épaisseurs"
chk("liste des épaisseurs : Default puis celles d'AutoCAD, de 0,05 à 2,11 mm", m.PRINT_WIDTH_ITEMS[0][0] == 'DEFAULT' and m.print_width_value('W035') == 0.35
    and m.print_width_value('W211') == 2.11 and m.print_width_value('DEFAULT') == 0.0 and len(m.PRINT_WIDTH_ITEMS) == 24, len(m.PRINT_WIDTH_ITEMS))
walls.dessin_layer.print_width = 'W050'
ents = m.layout_entities(L)
chk("calque Walls à 0,50 mm : ses traits sont imprimés à 0,50, les autres restent à 0,35", near(at(ents, RW)[0][2], 0.5) and near(at(ents, RF)[0][2], 0.35) and near(at(ents, RA)[0][2], 0.35),
    [(ebox(e), e[2]) for e in ents if e[0] == 'L'])
furn.dessin_layer.print_width = 'W025'
ents = m.layout_entities(L)
chk("calque Furniture à 0,25 mm : son sous-calque resté sur Default le suit", near(at(ents, RF)[0][2], 0.25) and near(at(ents, RC)[0][2], 0.25))
chairs.dessin_layer.print_width = 'W013'
ents = m.layout_entities(L)
chk("... le sous-calque réglé à 0,13 mm garde la sienne", near(at(ents, RC)[0][2], 0.13) and near(at(ents, RF)[0][2], 0.25))
D.lw_visible = 0.7
ents = m.layout_entities(L)
chk("épaisseur « Visible edges » de la mise en page à 0,70 : seuls les calques sur Default la prennent (Axes)", near(at(ents, RA)[0][2], 0.7) and near(at(ents, RW)[0][2], 0.5))
D.lw_visible = 0.35
D.show_lineweights = True
bev = {c.get("wd_layer"): round(c.data.bevel_depth, 4) for c in kids(d, 'vis')}
chk("Show line widths : à l'écran chaque calque a son épaisseur (demi-épaisseur en mm)", bev == {"Walls": 0.25, "Furniture": 0.125, "Chairs": 0.065, "Axes": 0.175}, bev)
walls.dessin_layer.print_width = 'W100'
chk("... elle suit tout de suite un changement dans la table des calques", next(c for c in kids(d, 'vis') if c.get("wd_layer") == "Walls").data.bevel_depth == 0.5)
walls.dessin_layer.print_width = 'W050'
D.show_lineweights = False
with m.quiet():
    d.dessin_detail.display = 'HIDDEN_DASHED'
    d.dessin_detail.view = 'FRONT'
ents = refresh()
hid = [e for e in ents if e[0] == 'L' and e[-1] == "Hidden"]
chk("arêtes cachées (le cube de Chairs derrière celui de Furniture) : à l'épaisseur du calque quand elle est plus fine que 0,18 mm (0,13)",
    sorted({round(e[2], 2) for e in hid}) == [0.13] and hid[0][4] == (3.0, 1.5), sorted({round(e[2], 2) for e in hid}))
chairs.dessin_layer.print_width = 'W050'
hid = [e for e in m.layout_entities(L) if e[0] == 'L' and e[-1] == "Hidden"]
chk("... jamais plus épaisses que « Hidden edges » de la mise en page : 0,18 mm pour un calque à 0,50", sorted({round(e[2], 2) for e in hid}) == [0.18], sorted({round(e[2], 2) for e in hid}))
chairs.dessin_layer.print_width = 'W013'
with m.quiet():
    d.dessin_detail.display = 'HIDDEN'
    d.dessin_detail.view = 'TOP'
ents = refresh()
for o in BC.view_layer.objects: o.select_set(False)
BC.window.scene = model
for o in model.objects: o.select_set(False)
B.select_set(True)
r = bpy.ops.dessin.object_print_width(width='W070')
BC.window.scene = L
ents = refresh()
chk("épaisseur propre à un objet (0,70 mm) : elle l'emporte sur celle de son calque", r == {'FINISHED'} and near(B.get("wd_lw"), 0.7) and near(at(ents, RF)[0][2], 0.7) and near(at(ents, RC)[0][2], 0.13),
    at(ents, RF)[0][2] if at(ents, RF) else None)
chk("... le bouton affiche l'épaisseur de la sélection", (BC.window.scene == L) and m.selection_print_width(types.SimpleNamespace(selected_objects=[B])) == "0.70 mm"
    and m.selection_print_width(types.SimpleNamespace(selected_objects=[A, B])) == "Mixed" and m.selection_print_width(types.SimpleNamespace(selected_objects=[A])) == "By Layer")
BC.window.scene = model
r = bpy.ops.dessin.object_print_width(width='DEFAULT')
BC.window.scene = L
ents = refresh()
chk("... By Layer : l'objet suit de nouveau son calque (0,25 mm)", "wd_lw" not in B.keys() and near(at(ents, RF)[0][2], 0.25))

# ---------------------------------------------------------------- D. couleurs
SEC = "couleurs"
walls.dessin_layer.color = (0.2, 0.4, 1.0)
m.layer_apply_color(walls)
ents = refresh()
chk("mode Black : tout est noir, même un calque coloré", r3(at(ents, RW)[0][3]) == (0, 0, 0))
D.print_color = 'COLOR'
ents = m.layout_entities(L)
chk("mode Layer colors : le calque Walls s'imprime dans sa couleur", r3(at(ents, RW)[0][3]) == (0.2, 0.4, 1.0), at(ents, RW)[0][3])
D.print_color = 'GRAY'
ents = m.layout_entities(L)
g = 0.299 * 0.2 + 0.587 * 0.4 + 0.114 * 1.0
chk("mode Grayscale : sa couleur devient un gris de même luminosité (0,409)", near(at(ents, RW)[0][3], (g, g, g), 1e-6), at(ents, RW)[0][3])
D.print_color = 'BLACK'
axes.dessin_layer.print_color = (1.0, 0.0, 0.0)
ents = m.layout_entities(L)
chk("couleur d'impression choisie pour Axes : elle s'active d'elle-même et s'imprime en rouge même en mode Black", axes.dessin_layer.use_print_color and r3(at(ents, RA)[0][3]) == (1, 0, 0)
    and r3(at(ents, RW)[0][3]) == (0, 0, 0), at(ents, RA)[0][3])
D.print_color = 'COLOR'
ents = m.layout_entities(L)
chk("... en mode Layer colors aussi, à la place de la couleur du calque", r3(at(ents, RA)[0][3]) == (1, 0, 0) and r3(at(ents, RW)[0][3]) == (0.2, 0.4, 1.0))
D.print_color = 'GRAY'
ents = m.layout_entities(L)
chk("... en Grayscale elle passe en gris (0,299)", near(at(ents, RA)[0][3], (0.299,) * 3, 1e-6), at(ents, RA)[0][3])
D.print_color = 'BLACK'
furn.dessin_layer.print_color = (0.0, 0.5, 0.0)
ents = m.layout_entities(L)
chk("couleur d'impression d'un calque parent : son sous-calque sans couleur propre la prend", r3(at(ents, RC)[0][3]) == (0, 0.5, 0) and r3(at(ents, RF)[0][3]) == (0, 0.5, 0))
furn.dessin_layer.use_print_color = False
axes.dessin_layer.use_print_color = False
ents = m.layout_entities(L)
chk("couleur d'impression retirée : retour au mode de la mise en page (noir)", r3(at(ents, RA)[0][3]) == (0, 0, 0) and r3(at(ents, RC)[0][3]) == (0, 0, 0))
chk("à l'écran, la couleur du calque reste celle du modèle (les couleurs d'impression ne touchent que l'impression)",
    r3(next(c for c in kids(d, 'vis') if c.get("wd_layer") == "Walls").color) == (0.2, 0.4, 1.0))

# ---------------------------------------------------------------- E. la feuille : cadre, fenêtres, annotations, images
SEC = "feuille"
ann = m.layout_collection(L, 'annot')
ln = line("Note", ann, (10.0, 90.0), (40.0, 90.0))
ln.color = (0.0, 0.0, 0.0, 1.0)
BC.view_layer.update()
RN = (10.0, 90.0, 40.0, 90.0)
ents = m.layout_entities(L)
chk("trait dessiné sur la feuille : imprimé à l'épaisseur des annotations (0,18 mm)", len(at(ents, RN, "Sheet")) == 1 and near(at(ents, RN, "Sheet")[0][2], 0.18))
ann.dessin_layer.print_width = 'W100'
ents = m.layout_entities(L)
chk("calque Annotations de la feuille à 1,00 mm : ce trait s'imprime à 1,00", near(at(ents, RN, "Sheet")[0][2], 1.0))
ln["wd_lw"] = 0.4
ents = m.layout_entities(L)
chk("... épaisseur propre à l'objet (0,40 mm, le contour d'un cartouche libre par exemple) : elle l'emporte", near(at(ents, RN, "Sheet")[0][2], 0.4))
ann.dessin_layer.plot = False
ents = m.layout_entities(L)
chk("calque Annotations non imprimé : le trait n'est plus dans l'impression", not at(ents, RN, "Sheet"))
ann.dessin_layer.plot = True
vp = m.layout_collection(L, 'details')
nb = lambda es: len([e for e in es if e[0] == 'L' and e[-1] == "Viewport borders"])
vp.dessin_layer.plot = False
ents = m.layout_entities(L)
chk("calque Viewports non imprimé (l'usage d'AutoCAD) : le cadre des fenêtres ne s'imprime pas, leur contenu si", nb(ents) == 0 and all(at(ents, r) for r in (RW, RF, RC, RA)), nb(ents))
vp.dessin_layer.plot = True
chk("... réimprimé : le cadre revient", nb(m.layout_entities(L)) == 1)
sh = m.layout_collection(L, 'sheet')
nf = lambda es: len([e for e in es if e[0] == 'L' and e[-1] in ("Frame", "Title block")])
nt = lambda es: len([e for e in es if e[0] == 'F'])
t0 = nt(m.layout_entities(L))
D.show_title = True
n0, t1 = nf(m.layout_entities(L)), nt(m.layout_entities(L))
sh.dessin_layer.plot = False
ents = m.layout_entities(L)
chk("calque Sheet non imprimé : ni cadre, ni cartouche, ni ses textes (l'étiquette de la fenêtre reste)", n0 >= 2 and nf(ents) == 0 and t1 > t0 and nt(ents) == t0, (n0, nf(ents), t0, t1, nt(ents)))
sh.dessin_layer.plot = True
D.show_title = False

# ---------------------------------------------------------------- F. PDF
SEC = "pdf"
walls.dessin_layer.print_width = 'W050'
axes.dessin_layer.print_color = (1.0, 0.0, 0.0)
chairs.dessin_layer.plot = False
path = os.path.join(TMP, "p.pdf")
le.write_pdf(path, [m.layout_page(L)])
raw = open(path, "rb").read()
streams = [zlib.decompress(s_) for s_ in re.findall(rb"stream\n(.*?)\nendstream", raw, re.S) if s_[:2] == b"x\x9c" or s_[:1] == b"x"]
txt = b"\n".join(streams).decode("latin-1")
chk("PDF : un trait rouge (Axes), un trait à 0,500 mm (Walls), aucun à 0,130 mm (Chairs, non imprimé)",
    "1.000 0.000 0.000 RG" in txt and "0.500 w" in txt and "0.130 w" not in txt, re.findall(r"RG ([0-9.]+) w", txt))
chairs.dessin_layer.plot = True

# ---------------------------------------------------------------- G. panneaux, copie de calque
SEC = "panneaux"


class FakeLayout:
    def __getattr__(self, n):
        def f(*a, **k):
            return FakeLayout()
        return f

    def __setattr__(self, n, v):
        pass


bad = []
for cls in (m.DESSIN_PT_layout_print_layers, m.DESSIN_PT_layout_print, m.DESSIN_PT_layers_print):
    try:
        cls.draw(types.SimpleNamespace(layout=FakeLayout()), BC)
    except Exception as e:
        bad.append((cls.__name__, repr(e)))
chk("Print by Layer (onglet Layout), Print et Print Settings (onglet Layers) se dessinent sans erreur", not bad, bad)
rows = []


class CountLayout(FakeLayout):
    def label(self, *a, **k):
        rows.append(k.get("text", ""))
        return CountLayout()

    def __getattr__(self, n):
        def f(*a, **k):
            return CountLayout()
        return f


n = m.draw_layer_print_table(CountLayout(), model.collection)
chk("la table liste les 4 calques du modèle, sous-calque compris, dans l'ordre de l'arborescence", n == 4 and [r for r in rows if r] == ["Walls", "Furniture", "Chairs", "Axes"], rows)
chk("ordre de l'onglet Layout : Print puis Print by Layer", m.DESSIN_PT_layout_print.bl_order == 6 and m.DESSIN_PT_layout_print_layers.bl_order == 7)
BC.window.scene = model
new = m.layer_copy_tree(walls, model.collection, BC)
chk("un calque dupliqué garde ses réglages d'impression", new.dessin_layer.print_width == 'W050' and new.dessin_layer.plot and not new.dessin_layer.use_print_color, new.dessin_layer.print_width)
shutil.rmtree(TMP, ignore_errors=True)
summary()
