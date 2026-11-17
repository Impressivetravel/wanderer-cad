# Layout : mises en page (espace papier), détails à l'échelle, lignes cachées, cotes sur la feuille, export PDF / SVG / DXF.
# Tout est mesuré : dimensions du papier, positions et longueurs des traits en millimètres, contenu des fichiers exportés.
import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
exec(open(_os.path.join(_HERE,'prec_lib.py')).read())
import json, os, re, shutil, subprocess, tempfile, time, zlib
from mathutils import Euler, Quaternion
le = m.le
BC = bpy.context
TMP = tempfile.mkdtemp(prefix="wd_layout_")


def reset():
    """Fichier vide : une scène de modèle en mètres, aucune mise en page."""
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


def box(name, sx, sy, sz, loc, col=None, scene=None):
    me = bpy.data.meshes.new(name); bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=bm.verts); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); o.location = loc
    (col or (scene or BC.scene).collection).objects.link(o)
    return o


def model_ab(k=1.0):
    """A : 2 x 1 x 0,5 posé au sol ; B : 0,5 x 0,5 x 1 derrière A (vu de face). k : unités par mètre."""
    a = box("A", 2.0 * k, 1.0 * k, 0.5 * k, (0, 0, 0.25 * k))
    b = box("B", 0.5 * k, 0.5 * k, 1.0 * k, (0, 2.0 * k, 0.5 * k))
    BC.view_layer.update()
    return a, b


def kids(det, role):
    return [c for c in det.children if c.get("wd_gen") == role]


def pts_of(objs):
    """Points (monde, mm) des splines d'objets générés."""
    out = []
    for o in objs:
        M = (o.parent.matrix_basis @ o.matrix_basis) if o.parent else o.matrix_basis
        for sp in o.data.splines:
            out += [tuple((M @ Vector(p.co[:3]))[:2]) for p in sp.points]
    return np.array(out).reshape(-1, 2)


def length_of(objs):
    tot = 0.0
    for o in objs:
        for sp in o.data.splines:
            P = np.array([p.co[:2] for p in sp.points])
            if sp.use_cyclic_u:
                P = np.vstack((P, P[:1]))
            tot += float(np.hypot(*(P[1:] - P[:-1]).T).sum())
    return tot


def bb(P):
    return (round(float(P[:, 0].min()), 4), round(float(P[:, 1].min()), 4), round(float(P[:, 0].max()), 4), round(float(P[:, 1].max()), 4))


def detail(scene, view, scale, center, cx=150.0, cy=150.0, w=200.0, h=120.0, **kw):
    d = m.detail_create(scene, cx, cy, w, h, view, scale=scale, fit=False)
    with m.quiet():
        d.dessin_detail.center = center
        for k_, v_ in kw.items():
            setattr(d.dessin_detail, k_, v_)
    m.detail_rebuild(d, force=True)
    return d


# ---------------------------------------------------------------- A. fonctions pures
SEC = "moteur"
rec(SEC, "fmt_scale : 1:20, 2:1, 1:2.5, 1:1", (le.fmt_scale(20), le.fmt_scale(0.5), le.fmt_scale(2.5), le.fmt_scale(1)) == ("1:20", "2:1", "1:2.5", "1:1"))
rec(SEC, "parse_scale : « 1:50 », « 1/50 », « 50 », « 2:1 », « 0,5 », « abc »",
    (le.parse_scale("1:50"), le.parse_scale("1/50"), le.parse_scale("50"), le.parse_scale("2:1"), le.parse_scale("0,5"), le.parse_scale("abc")) == (50.0, 50.0, 50.0, 0.5, 0.5, None))
rec(SEC, "fit_scale : 2 m x 1 m dans 120 x 90 mm -> 1:20", m.fit_scale(2.0, 1.0, 120.0, 90.0, 1000.0) == 20.0, m.fit_scale(2.0, 1.0, 120.0, 90.0, 1000.0))
rec(SEC, "fit_scale : 30 mm dans 200 mm -> agrandissement 5:1", m.fit_scale(0.03, 0.01, 200.0, 100.0, 1000.0) == 0.2, m.fit_scale(0.03, 0.01, 200.0, 100.0, 1000.0))
SG = np.array([(-10.0, 0.0, 10.0, 0.0), (0.0, -10.0, 0.0, 10.0), (20.0, 20.0, 30.0, 30.0), (-8.0, -8.0, 8.0, 8.0)])
Cq = le.clip_segments(SG, -5.0, -5.0, 5.0, 5.0)
rec(SEC, "clip_segments : 4 segments découpés au carré de 10 (un dehors)", len(Cq) == 3 and near(Cq[0], (-5, 0, 5, 0)) and near(Cq[2], (-5, -5, 5, 5)), Cq.round(3).tolist())
P_ = le.merge_segments(np.array([(0.0, 0.0, 1.0, 0.0), (1.0, 0.0, 1.0, 1.0), (1.0, 1.0, 0.0, 1.0), (0.0, 1.0, 0.0, 0.0), (5.0, 5.0, 6.0, 5.0)]))
rec(SEC, "merge_segments : un carré fermé + un segment", sorted((len(p), c) for p, c in P_) == [(2, False), (4, True)], [(len(p), c) for p, c in P_])
v_, h_ = le.clean_overlaps([np.array([(0.0, 0.0, 10.0, 0.0), (4.0, 0.0, 14.0, 0.0)])], [np.array([(8.0, 0.0, 20.0, 0.0), (0.0, 5.0, 3.0, 5.0)])])
rec(SEC, "clean_overlaps : visibles superposés fusionnés (0-14), caché sous un visible retiré (reste 14-20)",
    len(v_[0]) == 1 and near(sorted(v_[0][0][[0, 2]]), (0, 14)) and len(h_[0]) == 2 and any(near(sorted(r[[0, 2]]), (14, 20)) for r in h_[0]), (v_[0].round(3).tolist(), h_[0].round(3).tolist()))
L_ = le.clip_loop(np.array([(-2.0, -2.0), (2.0, -2.0), (2.0, 2.0), (-2.0, 2.0)]), -1.0, -1.0, 1.0, 3.0)
rec(SEC, "clip_loop : carré de 4 découpé à x, y dans [-1, 1] x [-1, 3]", len(L_) == 4 and bb(np.array(L_)) == (-1.0, -1.0, 1.0, 2.0), L_)

# ---------------------------------------------------------------- B. création d'une mise en page
SEC = "feuille"
model = reset(); model_ab()
L = m.layout_create(model, "Plan", 'A3', 'LANDSCAPE', 10.0, True)
us = L.unit_settings
rec(SEC, "la mise en page est une scène en millimètres (1 unité = 1 mm)", m.is_layout(L) and abs(us.scale_length - 0.001) < 1e-9 and us.length_unit == 'MILLIMETERS' and not m.is_layout(model))
paper = next(o for o in L.objects if o.get("wd_layout_gen") == 'paper')
V = np.array([v.co[:] for v in paper.data.vertices])
rec(SEC, "papier A3 paysage : 420 x 297 mm, coin en (0, 0)", near(V.min(0)[:2], (0, 0)) and near(V.max(0)[:2], (420, 297)), V.max(0)[:2].tolist())
fr = next(o for o in L.objects if o.name.startswith("Frame"))
rec(SEC, "cadre à 10 mm du bord", bb(pts_of([fr])) == (10.0, 10.0, 410.0, 287.0), bb(pts_of([fr])))
texts = [o.data.body for o in L.objects if o.type == 'FONT' and o.get("wd_layout_gen")]
rec(SEC, "cartouche : champs PROJECT / TITLE / SCALE / DATE / SHEET et format A3", all(t in texts for t in ("PROJECT", "TITLE", "SCALE", "DATE", "SHEET", "A3", "Plan")), texts)
rec(SEC, "calques de la mise en page : Sheet, Viewports, Annotations", [c.get("wd_layout_col") for c in L.collection.children] == ['sheet', 'details', 'annot'], [c.name for c in L.collection.children])
rec(SEC, "elle garde le modèle d'origine", m.layout_model(L) == model and L.dessin_layout.model == model)
with m.quiet():
    L.dessin_layout.paper, L.dessin_layout.orientation = 'A4', 'PORTRAIT'
m.paper_rebuild(L)
paper = next(o for o in L.objects if o.get("wd_layout_gen") == 'paper')
V = np.array([v.co[:] for v in paper.data.vertices])
rec(SEC, "A4 portrait : 210 x 297 mm", near(V.max(0)[:2], (210, 297)), V.max(0)[:2].tolist())
L.dessin_layout.paper = 'CUSTOM'; L.dessin_layout.custom_w, L.dessin_layout.custom_h = 500.0, 300.0; L.dessin_layout.orientation = 'LANDSCAPE'
paper = next(o for o in L.objects if o.get("wd_layout_gen") == 'paper')
V = np.array([v.co[:] for v in paper.data.vertices])
rec(SEC, "format personnalisé 500 x 300 mm (les réglages redessinent la feuille)", near(V.max(0)[:2], (500, 300)), V.max(0)[:2].tolist())
L.dessin_layout.show_title = False; L.dessin_layout.show_frame = False
rec(SEC, "sans cadre ni cartouche : il ne reste que le papier", [o.get("wd_layout_gen") for o in L.objects] == ['paper'], [o.name for o in L.objects])
L2 = m.layout_create(model, "Plan", 'A2')
rec(SEC, "deuxième mise en page : nom unique, onglet à la suite", L2.name != L.name and [s.name for s in m.layouts()] == [L.name, L2.name], [s.name for s in m.layouts()])

# cadrage de la feuille : vue orthogonale de Blender = view_distance x 72 / focale unités sur la plus grande dimension
_R = NS(width=2000, height=1000, x=0, y=0); _SP = NS(lens=50.0); _RV = NS(view_distance=0.0, view_location=(0, 0, 0))
_A = NS(regions=[])
px = m.paper_fit_view(BC, _A, _SP, _R, _RV, L)
vis_w = _RV.view_distance * 72.0 / 50.0                      # mm visibles sur les 2000 px de large
ui_ = BC.preferences.system.ui_scale
free_h = 1000 - 64 * ui_
rec(SEC, "cadrage : la feuille (500 x 300 mm) tient dans la vue libre (2000 x 936 px) avec 6 % de marge, centrée au-dessus de la barre du bas",
    abs(px - free_h / (300 * 1.06)) < 1e-6 and abs(vis_w - 2000 / px) < 1e-6 and abs(_RV.view_location[0] - 250.0) < 1e-6
    and abs(_RV.view_location[1] - (150.0 - (64 * ui_ / 2) / px)) < 1e-6, (round(px, 4), round(vis_w, 2), tuple(round(v, 3) for v in _RV.view_location)))
_A2 = NS(regions=[NS(type='TOOLS', width=100, height=900, x=0, y=0), NS(type='UI', width=400, height=900, x=1600, y=0),
                  NS(type='HEADER', width=2000, height=30, x=0, y=970), NS(type='TOOL_HEADER', width=2000, height=30, x=0, y=940)])
ov_ = BC.preferences.system.use_region_overlap
BC.preferences.system.use_region_overlap = True
px2 = m.paper_fit_view(BC, _A2, _SP, _R, _RV, L)
BC.preferences.system.use_region_overlap = ov_
fw2, fh2 = 2000 - 100 - 400, 1000 - 60 - 64 * ui_
rec(SEC, "... panneaux superposés (barre d'outils 100 px, barre latérale 400 px, en-têtes 60 px) : la feuille est cadrée entre eux",
    abs(px2 - min(fw2 / (500 * 1.06), fh2 / (300 * 1.06))) < 1e-6 and abs(_RV.view_location[0] - (250.0 - ((100 + 1600) / 2 - 1000) / px2)) < 1e-6
    and abs(_RV.view_location[1] - (150.0 - ((64 * ui_ + 940) / 2 - 500) / px2)) < 1e-6, (round(px2, 4), tuple(round(v, 3) for v in _RV.view_location)))

# ---------------------------------------------------------------- C. détails : échelle, vues, découpe
SEC = "détail"
model = reset(); a, b = model_ab()
L = m.layout_create(model, "Plan", 'A3')
d = detail(L, 'TOP', 20.0, (0.0, 0.0, 0.0))
P = pts_of(kids(d, 'vis'))
rec(SEC, "Top 1:20 : A (2 x 1 m) mesure 100 x 50 mm, centré dans le détail", near(P[(abs(P[:, 1] - 150) < 30)].min(0), (100, 125), 1e-4) and near(P[(abs(P[:, 1] - 150) < 30)].max(0), (200, 175), 1e-4), bb(P))
rec(SEC, "... B, à 2 m derrière (100 mm plus haut), est hors du cadre de 120 mm : il n'est pas tracé", abs(P[:, 1].max() - 175.0) < 1e-4, round(float(P[:, 1].max()), 4))
d2 = detail(L, 'FRONT', 20.0, (0.0, 0.0, 0.25), cy=150.0)
P = pts_of(kids(d2, 'vis'))
rec(SEC, "Front 1:20 : largeur 100 mm, hauteur de A 25 mm, B dépasse de 25 mm", bb(P) == (100.0, 137.5, 200.0, 187.5), bb(P))
rec(SEC, "Front, lignes cachées retirées : longueur visible = (5 + 1,5) m à 1:20 = 325 mm", abs(length_of(kids(d2, 'vis')) - 325.0) < 1e-3, round(length_of(kids(d2, 'vis')), 4))
rec(SEC, "... aucun trait caché n'est créé en affichage « Hidden »", not kids(d2, 'hid') and not kids(d2, 'hid_show'))
d2.dessin_detail.display = 'HIDDEN_DASHED'
rec(SEC, "Hidden, dashed : traits cachés = les deux montants de B derrière A = 1 m = 50 mm (le bas de B, sous un trait visible de A, n'est pas tracé)",
    abs(length_of(kids(d2, 'hid')) - 50.0) < 1e-3 and abs(length_of(kids(d2, 'vis')) - 325.0) < 1e-3, (round(length_of(kids(d2, 'hid')), 4), round(length_of(kids(d2, 'vis')), 4)))
rec(SEC, "... la source des cachés est masquée, les tirets (3 / 1,5 mm) sont affichés", kids(d2, 'hid')[0].hide_viewport and not kids(d2, 'hid_show')[0].hide_viewport
    and len(kids(d2, 'hid_show')[0].data.splines) > 3 and length_of(kids(d2, 'hid_show')) < 50.0, (len(kids(d2, 'hid_show')[0].data.splines), round(length_of(kids(d2, 'hid_show')), 3)))
d2.dessin_detail.display = 'WIREFRAME'
rec(SEC, "Wireframe : toutes les arêtes, superposées fusionnées = 7,5 m = 375 mm", abs(length_of(kids(d2, 'vis')) - 375.0) < 1e-3, round(length_of(kids(d2, 'vis')), 4))
d2.dessin_detail.display = 'HIDDEN'
d2.dessin_detail.scale = 10.0
P = pts_of(kids(d2, 'vis'))
rec(SEC, "échelle 1:10 : A fait 200 mm, découpé au cadre de 200 x 120 (rien ne dépasse)", bb(P) == (50.0, 100.0, 250.0, 200.0) or (P[:, 0].min() >= 50 - 1e-6 and P[:, 0].max() <= 250 + 1e-6), bb(P))
rec(SEC, "... la liste d'échelles suit (1:10) et l'étiquette aussi", d2.dessin_detail.scale_preset == 'S1_10' and kids(d2, 'label')[0].data.body.endswith("1:10"), (d2.dessin_detail.scale_preset, kids(d2, 'label')[0].data.body))
d2.dessin_detail.scale_preset = 'S1_50'
rec(SEC, "choisir 1:50 dans la liste règle l'échelle (A = 40 mm)", d2.dessin_detail.scale == 50.0 and abs((pts_of(kids(d2, 'vis'))[:, 0].max() - pts_of(kids(d2, 'vis'))[:, 0].min()) - 40.0) < 1e-4, d2.dessin_detail.scale)
d2.dessin_detail.width, d2.dessin_detail.height = 30.0, 10.0
P = pts_of(kids(d2, 'vis')); F = pts_of([d2])
rec(SEC, "détail rétréci à 30 x 10 mm : le cadre suit et les traits sont découpés", bb(F) == (135.0, 145.0, 165.0, 155.0) and P[:, 0].min() >= 135 - 1e-6 and P[:, 0].max() <= 165 + 1e-6
    and P[:, 1].min() >= 145 - 1e-6 and P[:, 1].max() <= 155 + 1e-6, (bb(F), bb(P)))
# cadrage automatique
d3 = m.detail_create(L, 300.0, 220.0, 120.0, 90.0, 'TOP')
rec(SEC, "Fit : Top de A + B (2 x 2,75 m) dans 120 x 90 mm -> 1:50, centré sur le modèle", d3.dessin_detail.scale == 50.0 and near(d3.dessin_detail.center, (0.0, 0.875, 0.5), 1e-6), (d3.dessin_detail.scale, tuple(d3.dessin_detail.center)))
# isométrie : cube unité
model = reset(); box("U", 1.0, 1.0, 1.0, (0, 0, 0)); BC.view_layer.update()
L = m.layout_create(model, "Iso", 'A3')
di = detail(L, 'ISO_SE', 10.0, (0.0, 0.0, 0.0), w=250.0, h=200.0)
P = pts_of(kids(di, 'vis'))
rec(SEC, "isométrie d'un cube de 1 m à 1:10 : largeur 141,42 mm, hauteur 163,30 mm", abs((P[:, 0].max() - P[:, 0].min()) - 100.0 * math.sqrt(2.0)) < 1e-3 and abs((P[:, 1].max() - P[:, 1].min()) - 200.0 * math.sqrt(2.0 / 3.0)) < 1e-3,
    (round(float(P[:, 0].max() - P[:, 0].min()), 4), round(float(P[:, 1].max() - P[:, 1].min()), 4)))
rec(SEC, "... 9 arêtes visibles sur 12 (les 3 du fond sont cachées)", abs(length_of(kids(di, 'vis')) - 9 * 100.0 * math.sqrt(2.0 / 3.0)) < 1e-2, round(length_of(kids(di, 'vis')), 4))
# vue en perspective copiée du modèle
with m.quiet():
    di.dessin_detail.view = 'CUSTOM'; di.dessin_detail.rot = tuple(Euler((math.radians(60), 0, math.radians(35)), 'XYZ').to_quaternion())
    di.dessin_detail.persp = True; di.dessin_detail.cam_dist = 6.0; di.dessin_detail.center = (0, 0, 0)
ok = m.detail_rebuild(di, force=True)
P = pts_of(kids(di, 'vis'))
rec(SEC, "vue en perspective : le cube est tracé (étiquette sans échelle)", ok and len(P) >= 6 and ":" not in kids(di, 'label')[0].data.body, (len(P), kids(di, 'label')[0].data.body))
# unités du modèle : millimètres
model = reset(); us = model.unit_settings; us.scale_length = 0.001; us.length_unit = 'MILLIMETERS'
model_ab(1000.0)
L = m.layout_create(model, "mm", 'A3')
d = detail(L, 'TOP', 20.0, (0.0, 0.0, 0.0))
P = pts_of(kids(d, 'vis')); P = P[abs(P[:, 1] - 150) < 30]
rec(SEC, "modèle en millimètres (A = 2000 x 1000 unités) : même dessin, 100 x 50 mm à 1:20", near(P.min(0), (100, 125), 1e-3) and near(P.max(0), (200, 175), 1e-3), bb(P))
d4 = m.detail_create(L, 300.0, 220.0, 120.0, 90.0, 'FRONT')
rec(SEC, "... et Fit choisit 1:20 pour la vue de face (2 m x 1 m dans 120 x 90)", d4.dessin_detail.scale == 20.0, d4.dessin_detail.scale)

# ---------------------------------------------------------------- D. calques, annotations, courbes
SEC = "contenu"
model = reset(); a, b = model_ab()
furn = bpy.data.collections.new("Furniture"); model.collection.children.link(furn)
sub = bpy.data.collections.new("Chairs"); furn.children.link(sub)
c = box("C", 0.4, 0.4, 0.4, (3.0, 0.0, 0.2), sub)
circ = m.build_bezier_arc(BC, "Circle", Vector((-3.0, 0.0, 0.0)), Vector((1, 0, 0)), Vector((0, 1, 0)), 0.5, 0.0, m.TAU, True)
fc = bpy.data.curves.new("T", 'FONT'); fc.body = "A8"; fc.size = 0.3
txt = bpy.data.objects.new("T", fc); txt.location = (-1.0, -1.2, 0.0); txt["dessin_text"] = True; model.collection.objects.link(txt)
BC.view_layer.update()
L = m.layout_create(model, "Plan", 'A3')
d = detail(L, 'TOP', 50.0, (0.0, 0.0, 0.0), w=250.0, h=160.0)
P = pts_of(kids(d, 'vis'))
rec(SEC, "Top 1:50 : A, B, C (x = 3,2 m -> 64 mm) et le cercle (x = -3,5 m -> -70 mm)", abs(P[:, 0].max() - 214.0) < 1e-3 and abs(P[:, 0].min() - 80.0) < 1e-3, bb(P))
cp = np.array([p for p in P if p[0] < 105.0]); r = np.hypot(cp[:, 0] - 90.0, cp[:, 1] - 150.0)
rec(SEC, "le cercle (courbe de Bézier, r = 0,5 m) reste rond : r = 10 mm à 0,01 mm près, 128 points", len(cp) >= 100 and abs(r.max() - 10.0) < 0.01 and abs(r.min() - 10.0) < 0.01, (len(cp), round(float(r.min()), 4), round(float(r.max()), 4)))
fills = kids(d, 'fill')
rec(SEC, "le texte du modèle devient un aplat : contours (A : 2, 8 : 3) et triangles affichés", len(fills) == 1 and len(fills[0].data.splines) == 5 and list(fills[0]["wd_fill_n"]) == [5]
    and len(kids(d, 'fill_show')) == 1 and len(kids(d, 'fill_show')[0].data.polygons) > 50, (len(fills), [len(f.data.splines) for f in fills]))
Pf = pts_of(fills)
rec(SEC, "... à sa place : x de -1 m (-20 mm), hauteur d'environ 0,3 m x 0,7 = 4,2 mm", abs(Pf[:, 0].min() - 130.0) < 1.0 and 3.0 < (Pf[:, 1].max() - Pf[:, 1].min()) < 5.0, bb(Pf))
d.dessin_detail.show_annotations = False
rec(SEC, "Model annotations décoché : plus de texte dans le détail", not kids(d, 'fill') and not kids(d, 'fill_show'))
d.dessin_detail.show_annotations = True
bpy.ops.dessin.detail_layer.poll  # (opérateur présent)
d.dessin_detail.hidden_layers = "Furniture"
P = pts_of(kids(d, 'vis'))
rec(SEC, "calque « Furniture » masqué dans ce détail : C (rangé dans son sous-calque) disparaît", abs(P[:, 0].max() - 170.0) < 1e-3, bb(P))
dB = detail(L, 'TOP', 50.0, (0.0, 0.0, 0.0), cx=150.0, cy=60.0, w=250.0, h=60.0)
rec(SEC, "... mais reste dans les autres détails", abs(pts_of(kids(dB, 'vis'))[:, 0].max() - 214.0) < 1e-3, bb(pts_of(kids(dB, 'vis'))))
d.dessin_detail.hidden_layers = ""
c.hide_viewport = True; BC.view_layer.update()
m.detail_rebuild(d, force=True)
rec(SEC, "objet masqué dans le modèle : absent du détail", abs(pts_of(kids(d, 'vis'))[:, 0].max() - 170.0) < 1e-3, bb(pts_of(kids(d, 'vis'))))
c.hide_viewport = False; BC.view_layer.update()
# couleur de calque
furn.dessin_layer.color = (1.0, 0.0, 0.0); furn.dessin_layer.use_color = True
sub.dessin_layer.color = (0.0, 0.0, 1.0); sub.dessin_layer.use_color = True
BC.view_layer.update(); m.detail_rebuild(d, force=True)
cols = sorted(tuple(round(x, 2) for x in k_.color[:3]) for k_ in kids(d, 'vis'))
rec(SEC, "les traits gardent la couleur de leur calque (C en bleu, le reste en noir)", cols == [(0.0, 0.0, 0.0), (0.0, 0.0, 1.0)], cols)
# bloc (instance de collection)
blk = bpy.data.collections.new("BlockDef"); box("K", 0.2, 0.2, 0.2, (0, 0, 0.1), blk)
tb = bpy.data.objects.new("KT", bpy.data.curves.new("KT", 'FONT')); tb.data.body = "K"; tb.data.size = 0.2; blk.objects.link(tb)
inst = bpy.data.objects.new("Block", None); inst.instance_type = 'COLLECTION'; inst.instance_collection = blk; inst.location = (0.0, -2.5, 0.0)
model.collection.objects.link(inst); BC.view_layer.update()
m.detail_rebuild(d, force=True)
P = pts_of(kids(d, 'vis'))
rec(SEC, "un bloc (instance de collection) est dessiné à sa place (y = -2,5 m -> -52 mm)", abs(P[:, 1].min() - (150.0 - 52.0)) < 1e-3, bb(P))
rec(SEC, "... son texte une seule fois (pas d'aplat en double qui s'annulerait)", list(kids(d, 'fill')[0]["wd_fill_n"]) in ([5, 1], [1, 5]), list(kids(d, 'fill')[0]["wd_fill_n"]))

# ---------------------------------------------------------------- E. modèle modifié, détail manipulé
SEC = "suivi"
model = reset(); a, b = model_ab()
L = m.layout_create(model, "Plan", 'A3')
d = detail(L, 'TOP', 20.0, (0.0, 0.0, 0.0))
v0 = m.model_version(model)
a.location.x = 1.0; BC.view_layer.update()
rec(SEC, "déplacer un objet du modèle marque ses détails comme à refaire", m.model_version(model) > v0 and m._STATE["built"].get(d.name) != m.model_version(model), (v0, m.model_version(model)))
opened = m.layout_open(BC, L)
P = pts_of(kids(d, 'vis')); Pa = P[abs(P[:, 1] - 150) < 30]
rec(SEC, "ouvrir la mise en page redessine le détail (A décalé de 1 m = 50 mm)", opened and BC.window.scene == L and near(Pa.min(0), (150, 125), 1e-4), bb(Pa))
rec(SEC, "... et la fenêtre montre la mise en page ; les onglets : vues du modèle puis mises en page",
    [(k_, v_, on) for k_, v_, _t, on in m.bar_tabs(BC)] == [('view', 'Top', False), ('view', 'Front', False), ('view', 'Perspective', False), ('view', 'Right', False), ('layout', 'Plan', True), ('viewmenu', '+', False)],
    [(k_, v_, on) for k_, v_, _t, on in m.bar_tabs(BC)])
# mise à l'échelle du cadre (gumball, S) : la taille du détail change, pas son contenu
d.scale = (0.5, 1.5, 1.0)
ch = m.layout_sync(L)
P = pts_of(kids(d, 'vis'))
rec(SEC, "cadre mis à l'échelle x 0,5 / y 1,5 : le détail fait 100 x 180 mm, échelle d'objet remise à 1", ch and near((d.dessin_detail.width, d.dessin_detail.height), (100.0, 180.0)) and near(d.scale, (1, 1, 1)), (d.dessin_detail.width, d.dessin_detail.height, tuple(d.scale)))
rec(SEC, "... le dessin n'est pas déformé (A fait toujours 50 mm de haut) et il est découpé au nouveau cadre", abs((P[abs(P[:, 1] - 150) < 30][:, 1].max() - P[abs(P[:, 1] - 150) < 30][:, 1].min()) - 50.0) < 1e-4 and P[:, 0].max() <= 200 + 1e-6, bb(P))
rec(SEC, "rien d'autre à faire ensuite", m.layout_sync(L) is False)
# déplacement : les traits suivent le cadre
d.location.x += 30.0
P2 = pts_of(kids(d, 'vis'))
rec(SEC, "déplacer le cadre déplace ses traits (enfants)", near(P2[:, 0].min() - P[:, 0].min(), 30.0, 1e-6) and m.layout_sync(L) is False, round(float(P2[:, 0].min() - P[:, 0].min()), 6))
# copie du cadre
cp = d.copy(); cp.data = d.data.copy(); cp.location.y -= 100.0
for uc in d.users_collection: uc.objects.link(cp)
rec(SEC, "copier le cadre : la copie est un détail sans traits...", m.is_detail(cp) and not kids(cp, 'vis'))
m.layout_sync(L)
rec(SEC, "... que l'entretien redessine", len(kids(cp, 'vis')) == 1 and abs(length_of(kids(cp, 'vis')) - length_of(kids(d, 'vis'))) < 1e-6, len(kids(cp, 'vis')))
# suppression du cadre
n_before = len(L.objects)
gen = [c_.name for c_ in cp.children]
bpy.data.objects.remove(cp)
m.layout_sync(L)
rec(SEC, "supprimer le cadre supprime ses traits", not any(n in bpy.data.objects for n in gen) and len(L.objects) == n_before - 1 - len(gen), (n_before, len(L.objects)))
# retour au modèle
closed = m.layout_close(BC)
rec(SEC, "retour au modèle", closed and BC.window.scene == model and BC.scene == model)
m.layout_open(BC, L)
r = bpy.ops.dessin.view_restore(name="Front")
rec(SEC, "demander une vue du modèle depuis la mise en page ramène au modèle", BC.window.scene == model, (r, BC.window.scene.name))

# ---------------------------------------------------------------- F. outils sur la feuille : Detail, cotes à l'échelle du détail
SEC = "outils"
model = reset(); a, b = model_ab()
dm_new, _r, _o = run("cotation", [C(-1, -0.5), C(1, -0.5), C(0, -1.2), 'ESC'])
mdim = next((o for o in dm_new if "dessin_dim" in o.keys()), None)
mtxt = next((o.data.body for o in dm_new if o.type == 'FONT'), None)
rec(SEC, "cote posée dans le modèle (2 m, en cm) : « 200.00 », rangée dans « Dimensions »", mdim is not None and mtxt == "200.00" and mdim.users_collection[0].name == "Dimensions", (mtxt, mdim and mdim.users_collection[0].name))
L = m.layout_create(model, "Plan", 'CUSTOM', custom=(100.0, 100.0), margin=2.0, title=False)
m.layout_open(BC, L)
L.dessin_layout.new_view = 'TOP'
new, r_, o_ = run("layout_detail", [C(5, 5), C(35, 25)])
det = next((o for o in new if m.is_detail(o)), None)
rec(SEC, "Viewport : deux coins (5, 5) et (35, 25) -> détail de 30 x 20 mm centré en (20, 15), vue Top", det is not None and near((det.dessin_detail.width, det.dessin_detail.height), (30, 20)) and near(det.location[:2], (20, 15)) and det.dessin_detail.view == 'TOP',
    det and (det.dessin_detail.width, det.dessin_detail.height, tuple(det.location)))
rec(SEC, "... échelle ajustée (1:200 : A, B et la cote, 3,5 m de haut, dans 30 x 20 mm) et cote du modèle visible (traits + texte)", det is not None and det.dessin_detail.scale == 200.0 and len(kids(det, 'ann')) == 1 and len(kids(det, 'fill')) == 1,
    det and (det.dessin_detail.scale, len(kids(det, 'ann')), len(kids(det, 'fill'))))
with m.quiet():
    det.dessin_detail.scale = 100.0; det.dessin_detail.center = (0.0, 0.0, 0.0); det.dessin_detail.show_annotations = False
m.detail_rebuild(det, force=True)
BC.view_layer.update()
P = pts_of(kids(det, 'vis'))
rec(SEC, "A à 1:100 : 20 x 10 mm autour de (20, 15)", bb(P) == (10.0, 10.0, 30.0, 20.0), bb(P))
# cote sur la feuille, accrochée aux extrémités de A dans le détail
before = {o.name for o in bpy.data.objects}
new, r_, o_ = run("cotation", [C(10.1, 10.1), C(29.9, 10.1), C(20, 7), 'ESC'])
ldim = next((o for o in new if "dessin_dim" in o.keys()), None)
ltxt = next((o.data.body for o in new if o.type == 'FONT'), None)
data = json.loads(ldim["dessin_dim"]) if ldim else {}
rec(SEC, "cote posée sur le détail, accrochée aux extrémités de A (20 mm de papier à 1:100) : elle donne la longueur du modèle, « 200.00 » cm",
    ltxt == "200.00" and data.get("lfac") == [100.0] and near(data.get("points"), [(10, 10, 0), (30, 10, 0)], 1e-5), (ltxt, data.get("lfac"), data.get("points")))
rec(SEC, "... rangée dans les cotes de la mise en page, pas dans celles du modèle", ldim is not None and ldim.users_collection[0].get("wd_layout_col") == 'dims' and "Dimensions" not in [c_.name for c_ in L.collection.children_recursive]
    and mdim.name in bpy.data.collections["Dimensions"].objects, ldim and ldim.users_collection[0].name)
th = next((o.data.size for o in new if o.type == 'FONT'), 0.0)
rec(SEC, "... texte de 2,5 mm de haut sur le papier", abs(th - 2.5) < 1e-6, th)
new2, r_, o_ = run("cotation", [C(-40, -40), C(-10, -40), C(-25, -33), 'ESC'])
ptxt = next((o.data.body for o in new2 if o.type == 'FONT'), None)
rec(SEC, "cote posée hors de tout détail : longueur sur le papier (30 mm = « 3.00 » cm)", ptxt == "3.00", ptxt)
det.dessin_detail.scale = 50.0
ltxt2 = sorted(o.data.body for o in m.layout_dims_collection(L).objects if o.type == 'FONT')
rec(SEC, "échelle du détail passée à 1:50 : la cote posée dessus est recalculée (20 mm x 50 = « 100.00 »), l'autre ne change pas", ltxt2 == ["100.00", "3.00"], ltxt2)
L.dessin.decimales = 0
ltxt3 = sorted(o.data.body for o in m.layout_dims_collection(L).objects if o.type == 'FONT')
mt3 = [o.data.body for o in bpy.data.collections["Dimensions"].objects if o.type == 'FONT']
rec(SEC, "style de cote de la mise en page (0 décimale) : ses cotes suivent, celles du modèle non", ltxt3 == ["100", "3"] and mt3 == ["200.00"], (ltxt3, mt3))
# un trait dessiné sur la feuille est en millimètres
new, r_, o_ = run("polyligne", [C(-40, -20), C(-10, -20), 'RET'])
ln = new[0] if new else None
rec(SEC, "Polyline sur la feuille : 30 mm, dans le calque Annotations", ln is not None and abs(length_of([ln]) - 30.0) < 1e-6 and ln.users_collection[0].get("wd_layout_col") == 'annot', ln and (length_of([ln]), ln.users_collection[0].name))
# encre : la couleur d'objet par défaut (blanc) serait invisible sur le papier
rec(SEC, "encre : le trait que l'on vient de dessiner est noir dès la fin de la commande (la couleur d'objet par défaut, blanche, ne se verrait pas)",
    tuple(ln.color) == (0.0, 0.0, 0.0, 1.0), tuple(ln.color))
gen_before = {o.name: tuple(o.color) for o in L.objects if o.get("wd_gen") or o.get("wd_layout_gen")}
red = box("Rouge", 5, 5, 0.1, (-30, 30, 0), scene=L); red.color = (1.0, 0.0, 0.0, 1.0)
wh = box("Blanc", 5, 5, 0.1, (-30, 40, 0), scene=L)       # objet arrivé autrement (collé, importé...) : blanc
c0 = tuple(wh.color)
n_ink = m.layout_ink(L)
rec(SEC, "... un objet blanc arrivé autrement passe au noir au passage du minuteur ; un objet de couleur et les objets générés ne changent pas",
    c0 == (1.0, 1.0, 1.0, 1.0) and tuple(wh.color) == (0.0, 0.0, 0.0, 1.0) and tuple(red.color) == (1.0, 0.0, 0.0, 1.0) and n_ink == 1
    and gen_before == {o.name: tuple(o.color) for o in L.objects if o.get("wd_gen") or o.get("wd_layout_gen")} and m.layout_ink(L) == 0, (c0, tuple(wh.color), n_ink))
dcol = sorted({tuple(round(v, 3) for v in o.color[:3]) for o in m.layout_dims_collection(L).objects})
rec(SEC, "cotes de la mise en page : noires (le bleu clair des cotes du modèle ne se lirait pas sur le papier)", dcol == [(0.0, 0.0, 0.0)] and tuple(L.dessin.couleur) == (0.0, 0.0, 0.0), dcol)
m.layout_close(BC)

# ---------------------------------------------------------------- F2. cotes attachées aux détails : elles suivent le détail
SEC = "cotes"
model = reset(); a, b = model_ab()
L = m.layout_create(model, "Plan", 'CUSTOM', custom=(100.0, 100.0), margin=2.0, title=False)
m.layout_open(BC, L)
det = detail(L, 'TOP', 100.0, (0.0, 0.0, 0.0), cx=10.0, cy=10.0, w=40.0, h=30.0, show_annotations=False)   # A : 20 x 10 mm autour de (10, 10)
BC.view_layer.update()


def dims_of(scene):
    """[(points, position de la ligne de cote, texte, objet)] des cotes de la mise en page, triées par x du premier point."""
    out = []
    for o in m.layout_dims(scene):
        d_ = json.loads(o["dessin_dim"])
        txt = next((c.data.body for c in o.children if c.type == 'FONT'), None)
        out.append(([tuple(round(v, 4) for v in p[:2]) for p in d_["points"]], tuple(round(v, 4) for v in d_["cur"][:2]), txt, o, d_))
    out.sort(key=lambda t: t[0][0])
    return out


def shown_pts(o):
    """Extrémités mesurées telles qu'elles sont dessinées (monde) : bornes en x des traits de la cote."""
    P = pts_of([o]); return (round(float(P[:, 0].min()), 3), round(float(P[:, 0].max()), 3))


run("cotation", [C(0.1, 5.1), C(19.9, 5.1), C(10, 2), 'ESC'])
run("cotation", [C(-40, -40), C(-10, -40), C(-25, -33), 'ESC'])
m.layout_sync(L)
D = dims_of(L)
pd, ad = D[0], D[1]          # cote de papier (x = -40), cote posée sur le détail (x = 0)
rec(SEC, "cote posée sur A dans le détail : attachée au détail (points mémorisés dans le repère du modèle : -1 m et +1 m)",
    ad[0] == [(0.0, 5.0), (20.0, 5.0)] and ad[2] == "200.00" and ad[4].get("ldet") == det.name and near(ad[4]["luv"]["p"], [(-1.0, -0.5), (1.0, -0.5)], 1e-6),
    (ad[0], ad[2], ad[4].get("ldet"), ad[4].get("luv")))
rec(SEC, "cote hors de tout détail : cote de papier, attachée à rien", pd[2] == "3.00" and pd[4].get("ldet") == "" and "luv" not in pd[4], (pd[2], pd[4].get("ldet")))
# Pan : le modèle glisse de 5 mm vers la gauche dans le détail (centre de la vue à x = +0,5 m)
det.dessin_detail.center = (0.5, 0.0, 0.0)
D = dims_of(L); pd, ad = D[0], D[1]
P = pts_of(kids(det, 'vis'))
rec(SEC, "Pan (le dessin glisse de 5 mm vers la gauche) : la cote suit, elle reste sur les extrémités de A et donne 200.00",
    ad[0] == [(-5.0, 5.0), (15.0, 5.0)] and ad[1] == (5.0, 2.0) and ad[2] == "200.00" and near(bb(P)[:1] + bb(P)[2:3], (-5.0, 15.0), 1e-4) and shown_pts(ad[3]) == (-5.0, 15.0),
    (ad[0], ad[1], ad[2], bb(P), shown_pts(ad[3])))
rec(SEC, "... la cote de papier ne bouge pas", pd[0] == [(-40.0, -40.0), (-10.0, -40.0)] and pd[2] == "3.00", (pd[0], pd[2]))
# échelle 1:50 : le dessin double autour du centre du détail (10, 10)
det.dessin_detail.scale = 50.0
D = dims_of(L); pd, ad = D[0], D[1]
rec(SEC, "échelle 1:100 -> 1:50 : la cote est replacée sur A agrandi (40 mm sur le papier), sa valeur ne change pas (200.00), l'autre reste à 3.00",
    ad[0] == [(-20.0, 0.0), (20.0, 0.0)] and ad[1] == (0.0, -6.0) and ad[2] == "200.00" and pd[2] == "3.00" and pd[0] == [(-40.0, -40.0), (-10.0, -40.0)], (ad[0], ad[1], ad[2], pd[2]))
th = [c.data.size for c in ad[3].children if c.type == 'FONT']
rec(SEC, "... son texte garde 2,5 mm de haut", th == [2.5], th)
# le détail est déplacé (gumball) : ses cotes le suivent au passage du minuteur
det.location.x += 7.0; det.location.y += 3.0
ch = m.layout_sync(L)
D = dims_of(L); pd, ad = D[0], D[1]
rec(SEC, "détail déplacé de (7, 3) mm : sa cote le suit, la cote de papier non", ch and ad[0] == [(-13.0, 3.0), (27.0, 3.0)] and ad[2] == "200.00" and pd[0] == [(-40.0, -40.0), (-10.0, -40.0)], (ch, ad[0], pd[0]))
# détail et cote sélectionnés et déplacés ensemble : pas de double déplacement
det.location.x -= 4.0; ad[3].location.x -= 4.0
m.layout_sync(L)
D = dims_of(L); ad = D[1]
loc = tuple(round(v, 4) for v in ad[3].matrix_basis.translation[:2])
rec(SEC, "détail et cote déplacés ensemble de -4 mm : la cote n'est déplacée qu'une fois", ad[0] == [(-17.0, 3.0), (23.0, 3.0)] and shown_pts(ad[3]) == (-17.0, 23.0), (ad[0], shown_pts(ad[3]), loc))
# la cote seule est déplacée à la main : sa définition suit, et ce décalage est gardé ensuite
ad[3].location.y -= 2.0
m.layout_sync(L)
D = dims_of(L); ad = D[1]
rec(SEC, "cote déplacée seule de -2 mm en y (gumball) : sa définition suit l'objet", ad[0] == [(-17.0, 1.0), (23.0, 1.0)] and ad[1] == (3.0, -5.0), (ad[0], ad[1]))
det.dessin_detail.center = (0.0, 0.0, 0.0)          # Pan inverse : + 0,5 m x 20 mm/m = + 10 mm
D = dims_of(L); ad = D[1]
rec(SEC, "... puis Pan de +10 mm : la cote suit avec son décalage", ad[0] == [(-7.0, 1.0), (33.0, 1.0)] and ad[2] == "200.00", (ad[0], ad[2]))
n_before = len(m.layout_dims(L))
m.layout_sync(L); ch2 = m.layout_sync(L)
rec(SEC, "rien à refaire au passage suivant du minuteur (aucune cote reconstruite, aucun pas d'annulation en trop)", ch2 is False and len(m.layout_dims(L)) == n_before, ch2)
# détail et sa cote copiés 60 mm plus loin (Copy, Ctrl+C / Ctrl+V) : la copie de la cote s'attache à la copie du détail
def dup(o, dx):
    c = o.copy(); c.data = o.data.copy(); o.users_collection[0].objects.link(c); c.location.x += dx
    for ch in o.children:
        if ch.get("wd_gen"): continue
        cc = ch.copy(); cc.data = ch.data.copy(); ch.users_collection[0].objects.link(cc); cc.parent = c
        cc.matrix_parent_inverse = ch.matrix_parent_inverse.copy()
    return c
det2 = dup(det, 60.0); dim2 = dup(ad[3], 60.0)
BC.view_layer.update(); m.layout_sync(L)
D = dims_of(L); ad, ad2 = D[1], D[2]
rec(SEC, "détail et cote copiés à +60 mm : la copie de la cote est attachée à la copie du détail (redessinée), l'original à l'original",
    ad2[0] == [(53.0, 1.0), (93.0, 1.0)] and ad2[4].get("ldet") == det2.name and ad[4].get("ldet") == det.name and len(kids(det2, 'vis')) == 1 and ad2[2] == "200.00",
    (ad2[0], ad2[4].get("ldet"), ad[4].get("ldet")))
det2.dessin_detail.center = (0.25, 0.0, 0.0)        # Pan de la copie : -0,25 m x 20 = -5 mm
D = dims_of(L); ad, ad2 = D[1], D[2]
rec(SEC, "Pan de la copie : seule sa cote suit", ad2[0] == [(48.0, 1.0), (88.0, 1.0)] and ad[0] == [(-7.0, 1.0), (33.0, 1.0)], (ad2[0], ad[0]))
for o_ in [det2] + list(det2.children) + [ad2[3]] + list(ad2[3].children): bpy.data.objects.remove(o_)
m.layout_sync(L)
D = dims_of(L); ad = D[1]
# autre vue : les points ne désignent plus les mêmes arêtes, la cote reste où elle est
keep = (ad[0], ad[1])
det.dessin_detail.view = 'FRONT'
D = dims_of(L); ad = D[1]
rec(SEC, "changement de vue du détail (Top -> Front) : la cote reste où elle est sur le papier", (ad[0], ad[1]) == keep, (ad[0], ad[1]))
det.dessin_detail.center = (0.0, 0.0, 0.25)
D = dims_of(L); ad = D[1]
rec(SEC, "... et suit de nouveau le détail dans sa nouvelle vue (Pan de 0,25 m vers le haut = -5 mm)", ad[0] == [(-7.0, -4.0), (33.0, -4.0)], ad[0])
# détail renommé : sa cote reste attachée (identifiant du détail), même si ses points sont hors du cadre
det.dessin_detail.center = (2.0, 0.0, 0.25)          # la cote sort du cadre (Pan de 2 m = -40 mm)
def attached(scene):
    return next(t for t in dims_of(scene) if t[4].get("ldet"))
ad = attached(L); out_pts = ad[0]
det.name = "Élévation A"
ch = m.layout_sync(L)
D = dims_of(L); ad = attached(L)
det.dessin_detail.center = (0.0, 0.0, 0.25)
ad2 = attached(L)
rec(SEC, "détail renommé alors que sa cote est hors du cadre : elle reste attachée (au nouveau nom) et suit le Pan suivant",
    out_pts == [(-47.0, -4.0), (-7.0, -4.0)] and ad[4].get("ldet") == "Élévation A" and len(D) == 2 and ad2[0] == [(-7.0, -4.0), (33.0, -4.0)], (out_pts, ad[4].get("ldet"), ad2[0]))
# détail supprimé (Suppr) : ses traits partent, sa cote aussi ; la cote de papier reste
n_obj = len(L.objects)
bpy.data.objects.remove(det)
ch = m.layout_sync(L)
D = dims_of(L)
rec(SEC, "détail supprimé : ses traits et sa cote partent avec lui, la cote de papier reste", ch and len(D) == 1 and D[0][2] == "3.00" and not [o for o in L.objects if o.get("wd_gen")]
    and m.layout_sync(L) is False, (len(D), [o.name for o in L.objects if o.get("wd_gen")]))
m.layout_close(BC)
# cote de rayon sur un cercle du détail (cylindre de rayon 1 m vu de dessus à 1:100 : cercle de 10 mm)
model = reset()
me_ = bpy.data.meshes.new("Cyl"); bm_ = bmesh.new(); bmesh.ops.create_cone(bm_, cap_ends=True, segments=64, radius1=1.0, radius2=1.0, depth=0.5); bm_.to_mesh(me_); bm_.free()
model.collection.objects.link(bpy.data.objects.new("Cyl", me_)); BC.view_layer.update()
L = m.layout_create(model, "Plan", 'CUSTOM', custom=(100.0, 100.0), margin=2.0, title=False)
m.layout_open(BC, L)
det = m.detail_create(L, 10.0, 10.0, 40.0, 30.0, 'TOP', scale=100.0, fit=False)
BC.view_layer.update()
run("cotation_rayon", [C(20.0, 10.0), C(26, 16), 'ESC'])
m.layout_sync(L)
D = dims_of(L)
rec(SEC, "cote de rayon sur le cercle du détail (10 mm à 1:100) : « R100.00 », attachée au détail", len(D) == 1 and D[0][2] == "R100.00" and D[0][4].get("ldet") == det.name and abs(D[0][4]["circ"][1] - 10.0) < 1e-6, D and (D[0][2], D[0][4].get("ldet")))
det.dessin_detail.scale = 50.0
D = dims_of(L)
rec(SEC, "... échelle 1:50 : le cercle coté passe à 20 mm sur le papier, la cote le suit et donne toujours R100.00",
    len(D) == 1 and D[0][2] == "R100.00" and abs(D[0][4]["circ"][1] - 20.0) < 1e-6 and D[0][1] == (42.0, 22.0) and D[0][4].get("lfac") == [50.0], D and (D[0][2], D[0][4]["circ"][1], D[0][1]))
m.layout_close(BC)

# ---------------------------------------------------------------- G. opérateurs
SEC = "opérateurs"
model = reset(); a, b = model_ab()
r = bpy.ops.dessin.layout_new(name="Sheet A", paper='A3', orientation='LANDSCAPE', initial='FOUR')
L = BC.window.scene
ds = m.details(L)
rec(SEC, "New Layout (4 vues) : la mise en page s'ouvre avec Top, Front, Right et une isométrie", r == {'FINISHED'} and m.is_layout(L) and sorted(o.dessin_detail.view for o in ds) == ['FRONT', 'ISO_SE', 'RIGHT', 'TOP'], [o.dessin_detail.view for o in ds])
orth = {o.dessin_detail.view: o for o in ds}
rec(SEC, "... les trois vues à la même échelle et au même centre : Top au-dessus de Front, Right à droite, alignées",
    len({orth[v].dessin_detail.scale for v in ('TOP', 'FRONT', 'RIGHT')}) == 1 and len({tuple(orth[v].dessin_detail.center) for v in ('TOP', 'FRONT', 'RIGHT')}) == 1
    and abs(orth['TOP'].location.x - orth['FRONT'].location.x) < 1e-6 and abs(orth['RIGHT'].location.y - orth['FRONT'].location.y) < 1e-6
    and orth['TOP'].location.y > orth['FRONT'].location.y and orth['RIGHT'].location.x > orth['FRONT'].location.x, [(v, o.dessin_detail.scale, tuple(o.location[:2])) for v, o in orth.items()])
Pt, Pf = pts_of(kids(orth['TOP'], 'vis')), pts_of(kids(orth['FRONT'], 'vis'))
rec(SEC, "... les projections se correspondent (mêmes x en Top et en Front)", abs(Pt[:, 0].min() - Pf[:, 0].min()) < 1e-4 and abs(Pt[:, 0].max() - Pf[:, 0].max()) < 1e-4, (bb(Pt), bb(Pf)))
texts = [o.data.body for o in L.objects if o.type == 'FONT' and o.get("wd_layout_gen")]
rec(SEC, "le cartouche affiche l'échelle commune", le.fmt_scale(orth['TOP'].dessin_detail.scale) in texts, texts)
for o in L.objects: o.select_set(False)
orth['FRONT'].select_set(True); BC.view_layer.objects.active = orth['FRONT']
r = bpy.ops.dessin.detail_scale(text="1:25")
rec(SEC, "Viewport Scale « 1:25 » sur le détail sélectionné ; le cartouche passe à « As noted »", r == {'FINISHED'} and orth['FRONT'].dessin_detail.scale == 25.0 and "As noted" in [o.data.body for o in L.objects if o.type == 'FONT' and o.get("wd_layout_gen")])
orth['FRONT'].dessin_detail.scale = orth['TOP'].dessin_detail.scale        # (réglage du panneau, sans passer par la commande)
t_same = [o.data.body for o in L.objects if o.type == 'FONT' and o.get("wd_layout_gen")]
orth['FRONT'].dessin_detail.scale = 25.0
t_diff = [o.data.body for o in L.objects if o.type == 'FONT' and o.get("wd_layout_gen")]
rec(SEC, "échelle réglée dans le panneau : le cartouche suit aussi (échelle commune, puis « As noted »)",
    le.fmt_scale(orth['TOP'].dessin_detail.scale) in t_same and "As noted" not in t_same and "As noted" in t_diff, (t_same[-4:], t_diff[-4:]))
orth['FRONT'].dessin_detail.locked = True
r1 = bpy.ops.dessin.detail_scale(text="1:5"); r2 = bpy.ops.dessin.detail_fit()
rec(SEC, "détail verrouillé : Viewport Scale et Fit ne le modifient pas", orth['FRONT'].dessin_detail.scale == 25.0 and r1 == {'CANCELLED'} and r2 == {'CANCELLED'}, orth['FRONT'].dessin_detail.scale)
orth['FRONT'].dessin_detail.locked = False
r = bpy.ops.dessin.detail_fit()
rec(SEC, "Fit : la vue de face seule (2 x 1 m dans 188 x 103 mm) tient à 1:20", r == {'FINISHED'} and orth['FRONT'].dessin_detail.scale == 20.0, orth['FRONT'].dessin_detail.scale)
r = bpy.ops.dessin.detail_layer(layer="Nope")
r = bpy.ops.dessin.detail_update(all=True)
rec(SEC, "Update Viewports", r == {'FINISHED'} and all(len(kids(o, 'vis')) >= 1 for o in ds))
r = bpy.ops.dessin.layout_rename(name=L.name, new_name="Façade")
rec(SEC, "Rename Layout (accents)", L.name == "Façade" and [s.name for s in m.layouts()] == ["Façade"], L.name)
n_obj = len(L.objects)
r = bpy.ops.dessin.layout_duplicate(name=L.name)
Lc = BC.window.scene
rec(SEC, "feuilles numérotées à la suite : 01 pour la première, 02 pour sa copie", L.dessin_layout.t_number == "01" and Lc.dessin_layout.t_number == "02", (L.dessin_layout.t_number, Lc.dessin_layout.t_number))
rec(SEC, "Duplicate Layout : même feuille, mêmes détails redessinés", r == {'FINISHED'} and Lc != L and m.is_layout(Lc) and len(m.details(Lc)) == 4 and len(Lc.objects) == n_obj
    and abs(length_of(kids(next(o for o in m.details(Lc) if o.dessin_detail.view == 'TOP'), 'vis')) - length_of(kids(orth['TOP'], 'vis'))) < 1e-6, (Lc.name, len(Lc.objects), n_obj))
r = bpy.ops.dessin.layout_next()
rec(SEC, "Next Layout : passe à l'autre mise en page", BC.window.scene == L, BC.window.scene.name)
name_c = Lc.name
r = bpy.ops.dessin.layout_delete(name=name_c)
rec(SEC, "Delete Layout : la copie disparaît, l'original et le modèle sont intacts", r == {'FINISHED'} and name_c not in bpy.data.scenes and len(L.objects) == n_obj and len(model.objects) == 2, [s.name for s in bpy.data.scenes])
r = bpy.ops.dessin.layout_delete(name=L.name)
rec(SEC, "supprimer la mise en page affichée : retour au modèle d'abord", r == {'FINISHED'} and BC.window.scene == model and not m.layouts() and not [o for o in bpy.data.objects if o.get("wd_gen") or o.get("wd_layout_gen")],
    (BC.window.scene.name, len(bpy.data.objects)))
ents = {e["label"]: e for e in m.cmd_entries()}
rec(SEC, "ligne de commande : Layout, Viewport, Export PDF (alias print, plot), Model", all(k_ in ents for k_ in ("Layout", "Viewport", "Export PDF", "Model", "Update Viewports", "Viewport Scale"))
    and "print" in ents["Export PDF"]["names"] and "mview" in ents["Viewport"]["names"], sorted(k_ for k_ in ents if "ayout" in k_ or "iewport" in k_))
best = m.cmd_suggest("layout")
rec(SEC, "taper « layout » propose la commande Layout en premier", bool(best) and best[0]["label"] == "Layout", best and best[0]["label"])
allnames = {}
for e in m.cmd_entries():
    if e["kind"] in ("tool", "act"):
        for nm in e["names"]:
            allnames.setdefault(m.cmd_compact(nm), set()).add(e["label"])
dup = {k_: v_ for k_, v_ in allnames.items() if len(v_) > 1 and any(x in ("Layout", "Viewport", "Model", "Next Layout", "Update Viewports", "Viewport Scale", "Fit Viewport", "Pan Viewport", "Page Setup", "Export PDF", "Export SVG", "Export DXF") for x in v_)}
shared = dup.pop("ms", None)           # ms : Pan Viewport sur une mise en page (AutoCAD), Match Surface dans le modèle
rec(SEC, "aucun alias des nouvelles commandes ne double un alias existant (sauf ms, départagé selon l'endroit)", not dup and shared == {"Pan Viewport", "Match Surface"}, (dup, shared))
rec(SEC, "... dans le modèle, « ms » lance Match Surface", m.cmd_suggest("ms")[0]["label"] == "Match Surface", [e_["label"] for e_ in m.cmd_suggest("ms")[:3]])
# boutons de la barre d'outils : Layout et Detail (menu déroulant de Layout), avec leur icône
tl, td = m.DESSIN_TT_layout, m.DESSIN_TT_layout_detail
labels = [e["label"] for e in m.cmd_entries() if e["kind"] in ("tool", "act")]
rec(SEC, "barre d'outils : boutons Layout et Viewport ; dans la ligne de commande, une seule entrée « Layout » (la commande) et une seule « Viewport » (l'outil)",
    tl.bl_idname == "dessin.layout_tool" and td.bl_idname == "dessin.layout_detail_tool" and labels.count("Layout") == 1 and labels.count("Viewport") == 1
    and ents["Layout"]["kind"] == "act" and ents["Viewport"]["kind"] == "tool", (labels.count("Layout"), labels.count("Viewport"), ents["Layout"]["kind"], ents["Viewport"]["kind"]))
ic = [m.svg_icon_bytes(k_) for k_ in ("layout", "detail")]
rec(SEC, "... chacun a son icône dessinée (triangles .dat), rangée dans la famille Annotation",
    all(d_ is not None and d_[:4] == b"VCO\x00" and len(d_) > 2000 for d_ in ic) and all(k_ in m.ICON_FAMILIES[7] for k_ in ("layout", "detail"))
    and tl in dict(m.tool_families())["Annotation"] and td in dict(m.tool_families())["Annotation"], [d_ and len(d_) for d_ in ic])
from bl_ui.space_toolsystem_toolbar import VIEW3D_PT_tools_active as _TB
def _tool_ids(mode):
    out = []
    def walk(it):
        if it is None: return
        if hasattr(it, "idname"): out.append(it.idname)
        elif isinstance(it, (tuple, list)):
            for q in it: walk(q)
    walk(list(_TB._tools[mode])); return out
_o = _tool_ids('OBJECT')
rec(SEC, "... dans la barre du mode Objet, une seule fois chacun, Viewport juste après Layout", _o.count(tl.bl_idname) == 1 and _o.count(td.bl_idname) == 1 and _o.index(td.bl_idname) == _o.index(tl.bl_idname) + 1,
    [i for i in _o if i and "layout" in i])
n_sc, n_ob = len(bpy.data.scenes), len(bpy.data.objects)
new, r_, o_ = run("layout_detail", [C(5, 5), C(35, 25)])
rec(SEC, "Viewport hors d'une mise en page : la commande s'arrête avec un message, rien n'est créé, on reste dans le modèle",
    r_ == {'CANCELLED'} and not new and len(bpy.data.scenes) == n_sc and len(bpy.data.objects) == n_ob and BC.window.scene == model, (r_, len(new)))

# ---------------------------------------------------------------- G2. annuler / rétablir
SEC = "annulation"
model = reset(); a, b = model_ab()
bpy.ops.ed.undo_push(message="start")
n0 = len(bpy.data.objects)
r = bpy.ops.dessin.layout_new(name="L1", initial='ONE')
bpy.ops.ed.undo_push(message="layout")
made = (len(m.layouts()), BC.window.scene.name, len([o for o in bpy.data.objects if o.get("wd_gen")]))
bpy.ops.ed.undo()
rec(SEC, "New Layout puis Annuler : plus de mise en page ni d'objet généré, la fenêtre revient au modèle", made[0] == 1 and made[1] == "L1" and not m.layouts() and bpy.context.window.scene.name == "Scene"
    and len(bpy.data.objects) == n0 and not [o for o in bpy.data.objects if o.get("wd_gen") or o.get("wd_layout_gen")], (made, [s_.name for s_ in bpy.data.scenes], len(bpy.data.objects)))
bpy.ops.ed.redo()
L = m.layouts()[0] if m.layouts() else None
rec(SEC, "Rétablir : la mise en page revient, avec son détail et ses traits, et elle est affichée", L is not None and bpy.context.window.scene == L and len(m.details(L)) == 1 and len(kids(m.details(L)[0], 'vis')) == 1,
    (L and L.name, bpy.context.window.scene.name))
d = m.details(L)[0]
len0 = length_of(kids(d, 'vis')); sc0 = d.dessin_detail.scale
bpy.ops.ed.undo_push(message="before scale")
d.dessin_detail.scale = sc0 / 2.0
bpy.ops.ed.undo_push(message="scale")
len1 = length_of(kids(m.details(L)[0], 'vis'))
bpy.ops.ed.undo()
L = m.layouts()[0]; d = m.details(L)[0]
rec(SEC, "échelle d'un détail changée puis Annuler : l'échelle, les traits et l'étiquette reviennent", len1 > len0 + 1.0 and d.dessin_detail.scale == sc0 and abs(length_of(kids(d, 'vis')) - len0) < 1e-6
    and kids(d, 'label')[0].data.body.endswith(le.fmt_scale(sc0)) and m.layout_sync(L) is False, (len0, len1, d.dessin_detail.scale, kids(d, 'label')[0].data.body))
m.layout_tick()
rec(SEC, "l'entretien périodique ne modifie rien quand tout est en ordre", len(m.details(L)) == 1 and abs(length_of(kids(m.details(L)[0], 'vis')) - len0) < 1e-6)
# détail déplacé (gumball), sa cote le suit au passage du minuteur : Annuler défait les deux d'un seul coup
m._STATE["hold"] = 0.0                                 # (l'utilisateur reprend le travail : l'entretien n'attend plus)
small = m.detail_create(L, 20.0, 25.0, 30.0, 30.0, 'TOP', scale=100.0, fit=False, name="Petit")
BC = bpy.context; BC.view_layer.update()
run("cotation", [C(10, 20), C(25, 20), C(17, 15), 'ESC'])
m.layout_tick()
bpy.ops.ed.undo_push(message="dim")
def petit():
    L_ = m.layouts()[0]
    return L_, next(o for o in m.details(L_) if o.name == "Petit")
L, d = petit()
x0 = d.location.x; p0 = dims_of(L)[0][0]; att = dims_of(L)[0][4].get("ldet")
d.location.x += 6.0
bpy.ops.ed.undo_push(message="move detail")           # commande de Blender (G) : son pas d'annulation, sans la cote
m.layout_tick()                                        # le minuteur passe : la cote suit, avec un pas d'annulation à elle
p1 = dims_of(m.layouts()[0])[0][0]
bpy.ops.ed.undo()                                      # 1er Annuler : la cote revient
hold1 = m._STATE["hold"] > 0.0
m.layout_tick(); m.layout_tick()                       # le minuteur ne la redéplace pas (sinon Annuler tournerait en rond)
L, d = petit(); pa = dims_of(L)[0][0]; xa = d.location.x
bpy.ops.ed.undo()                                      # 2e Annuler : le détail revient
m.layout_tick()
L, d = petit(); p2 = dims_of(L)[0][0]; x2 = d.location.x
rec(SEC, "détail déplacé de 6 mm par une commande de Blender : la cote suit au passage du minuteur (pas d'annulation à part)",
    att == "Petit" and p0 == [(10.0, 20.0), (25.0, 20.0)] and p1 == [(16.0, 20.0), (31.0, 20.0)], (att, p0, p1))
rec(SEC, "... Annuler : la cote revient et le minuteur attend (il ne refait pas ce que l'on vient d'annuler) ; Annuler encore : le détail revient",
    hold1 and pa == p0 and abs(xa - (x0 + 6.0)) < 1e-6 and p2 == p0 and abs(x2 - x0) < 1e-6, (hold1, pa, xa, p2, x2))
bpy.ops.ed.redo(); m.layout_tick(); bpy.ops.ed.redo(); m.layout_tick()
L, d = petit(); p4 = dims_of(L)[0][0]
rec(SEC, "Rétablir deux fois : le détail repart, sa cote aussi", abs(d.location.x - (x0 + 6.0)) < 1e-6 and p4 == p1, (d.location.x, p4))
# après un Annuler, l'entretien reprend dès que quelque chose change
bpy.ops.ed.undo(); m.layout_tick()
L, d = petit(); pb = dims_of(L)[0][0]
m._STATE["hold"] = time.monotonic() - 1.0              # (une seconde plus tard)
d.location.y += 0.0; d.location.y = d.location.y; bpy.context.view_layer.update(); m.layout_on_depsgraph(L, None)
m.layout_tick()
L, d = petit(); pc = dims_of(L)[0][0]
rec(SEC, "... après un Annuler, l'entretien reprend au premier changement : la cote rejoint son détail", pb == p0 and m._STATE["hold"] == 0.0 and pc == p1, (pb, pc, m._STATE["hold"]))
# commande de Wanderer (gumball, Move...) : la cote suit à la fin de la commande, dans le même pas d'annulation
bpy.ops.ed.undo_push(message="avant")
L, d = petit(); x5 = d.location.x; p5 = dims_of(L)[0][0]
d.location.y += 4.0
done = m.layout_after_command(bpy.context)             # (appelé par l'enveloppe de modal() quand la commande se termine)
bpy.ops.ed.undo_push(message="gumball")                # le pas d'annulation de la commande
L, d = petit(); p6 = dims_of(L)[0][0]
bpy.ops.ed.undo()
m.layout_tick()
L, d = petit(); p7 = dims_of(L)[0][0]
rec(SEC, "détail déplacé par une commande de Wanderer : la cote suit à la fin de la commande ; un seul Annuler défait les deux",
    done and p6 == [(p5[0][0], p5[0][1] + 4.0), (p5[1][0], p5[1][1] + 4.0)] and p7 == p5 and abs(d.location.x - x5) < 1e-6, (done, p5, p6, p7))
# Suppr dans une mise en page : le détail part avec ses traits et sa cote, et un seul Annuler ramène tout
bpy.ops.ed.undo_push(message="avant suppr")
L, d = petit()
n_obj = len(L.objects); n_dim = len(m.layout_dims(L)); n_kid = len(d.children)
for o_ in L.objects: o_.select_set(False)
d.select_set(True); bpy.context.view_layer.objects.active = d
r = bpy.ops.dessin.layout_erase()
bpy.ops.ed.undo_push(message="Delete")                 # (le pas d'annulation de la commande)
L = m.layouts()[0]
gone = (not [o for o in m.details(L) if o.name == "Petit"], len(m.layout_dims(L)), len([o for o in L.objects if o.get("wd_gen") and o.get("wd_gen") != 'detail' and o.parent is None]), len(L.objects))
bpy.ops.ed.undo()
m.layout_tick()
L, d = petit()
rec(SEC, "Suppr sur un détail (commande de la mise en page) : le cadre, ses traits et sa cote partent ensemble ; un seul Annuler ramène tout",
    r == {'FINISHED'} and gone[0] and gone[1] == n_dim - 1 and gone[2] == 0 and gone[3] == n_obj - 1 - n_kid - 2 and len(L.objects) == n_obj
    and len(m.layout_dims(L)) == n_dim and len(d.children) == n_kid, (r, gone, n_obj, len(L.objects)))
km = [k for k in bpy.context.window_manager.keyconfigs.addon.keymaps["Object Mode"].keymap_items if k.idname == "dessin.layout_erase"]
m.layout_close(bpy.context)
rec(SEC, "... touches Suppr et X reliées à cette commande ; hors d'une mise en page elle ne se propose pas (la suppression de Blender reste)",
    sorted(k.type for k in km) == ['DEL', 'X'] and not bpy.ops.dessin.layout_erase.poll(), [k.type for k in km])
BC = bpy.context

# ---------------------------------------------------------------- H. export
SEC = "export"
model = reset(); a, b = model_ab()
fc = bpy.data.curves.new("T", 'FONT'); fc.body = "A8"; fc.size = 0.3
txt = bpy.data.objects.new("T", fc); txt.location = (-1.0, -1.2, 0.0); model.collection.objects.link(txt); BC.view_layer.update()
L = m.layout_create(model, "Plan", 'A3')
L.dessin_layout.t_project = "Maison é"
dT = detail(L, 'TOP', 50.0, (0.0, 0.0, 0.0), cx=110.0, cy=200.0, w=160.0, h=120.0)
dF = detail(L, 'FRONT', 20.0, (0.0, 0.0, 0.25), cx=300.0, cy=200.0, w=160.0, h=120.0, display='HIDDEN_DASHED')
m.layout_open(BC, L)
new, r_, o_ = run("polyligne", [C(20, 20), C(40, 20), 'RET'])        # trait d'annotation sur la feuille : (20, 20) -> (40, 20)
pg = m.layout_page(L)
kinds = {}
for e in pg["ents"]:
    kinds[(e[0], e[-1])] = kinds.get((e[0], e[-1]), 0) + 1
rec(SEC, "entités de la page : cadre, cartouche, bordures, visibles, cachés, feuille, textes", all(k_ in kinds for k_ in (('L', 'Frame'), ('L', 'Title block'), ('L', 'Viewport borders'), ('L', 'Visible'), ('L', 'Hidden'), ('L', 'Sheet'), ('F', 'Text'))), kinds)
order = [e[0] + ":" + e[-1] for e in pg["ents"]]
rec(SEC, "ordre du tracé : les cachés avant les visibles, les textes en dernier", order.index("L:Hidden") < order.index("L:Visible") and order[-1] == "F:Text", sorted(set(order)))
pdf = _os.path.join(TMP, "plan.pdf")
r = bpy.ops.dessin.layout_export_pdf(filepath=pdf, open_after=False)
raw = open(pdf, "rb").read() if _os.path.exists(pdf) else b""
mb = re.search(rb"/MediaBox \[0 0 ([\d.]+) ([\d.]+)\]", raw)
rec(SEC, "Export PDF : fichier écrit, une page au format A3 exact (1190,55 x 841,89 pt)", r == {'FINISHED'} and raw.startswith(b"%PDF-1.4") and mb is not None and abs(float(mb.group(1)) - 420 * 72 / 25.4) < 0.01 and abs(float(mb.group(2)) - 297 * 72 / 25.4) < 0.01
    and raw.count(b"/Type /Page ") == 1, mb and (mb.group(1), mb.group(2)))
st = re.search(rb"stream\n(.*?)\nendstream", raw, re.S)
txt_stream = zlib.decompress(st.group(1)).decode("ascii") if st else ""
rec(SEC, "... contenu en millimètres (72 / 25,4), bouts ronds, épaisseurs 0,35 / 0,18 / 0,5 mm, tirets 3 / 1,5 mm", "2.834646 0 0 2.834646 0 0 cm" in txt_stream and "1 J 1 j" in txt_stream and " 0.350 w " in txt_stream
    and " 0.180 w [3.00 1.50] 0 d" in txt_stream and " 0.500 w " in txt_stream and "f*" in txt_stream, len(txt_stream))


def pdf_strokes(stream):
    """[(épaisseur, tirets, [points])] des tracés d'un flux de page."""
    out, w, dash, cur = [], None, None, []
    for line in stream.split("\n"):
        mm_ = re.match(r"[\d.]+ [\d.]+ [\d.]+ RG ([\d.]+) w (\[.*?\]) 0 d", line)
        if mm_:
            w, dash = float(mm_.group(1)), mm_.group(2)
            continue
        if line.endswith(" S"):
            nums = re.findall(r"(-?[\d.]+) (-?[\d.]+) [ml]", line)
            out.append((w, dash, [(float(x), float(y)) for x, y in nums], line.endswith("h S")))
    return out


strokes = pdf_strokes(txt_stream)
vis = np.array([p for w_, d_, pts_, c_ in strokes if abs(w_ - 0.35) < 1e-9 for p in pts_])
front = vis[vis[:, 0] > 200.0]
rec(SEC, "... traits visibles de la vue de face à 1:20 : x de 250 à 350 mm, y de 187,5 à 237,5 mm (au micron)", bb(front) == (250.0, 187.5, 350.0, 237.5), bb(front))
hid = [pts_ for w_, d_, pts_, c_ in strokes if d_ == "[3.00 1.50]"]
hl = sum(float(np.hypot(*(np.array(p[1:]) - np.array(p[:-1])).T).sum()) for p in hid)
rec(SEC, "... traits cachés : 50 mm en tirets", abs(hl - 50.0) < 1e-2, round(hl, 3))
ann = [pts_ for w_, d_, pts_, c_ in strokes if abs(w_ - 0.18) < 1e-9 and d_ == "[]" and len(pts_) == 2 and abs(pts_[0][1] - 20.0) < 1e-6 and abs(pts_[1][1] - 20.0) < 1e-6 and pts_[0][0] < 100]
rec(SEC, "... le trait dessiné sur la feuille : (20, 20) -> (40, 20)", len(ann) == 1 and sorted(ann[0]) == [(20.0, 20.0), (40.0, 20.0)], ann)
frame = [pts_ for w_, d_, pts_, c_ in strokes if abs(w_ - 0.5) < 1e-9 and c_]
rec(SEC, "... le cadre : rectangle fermé de (10, 10) à (410, 287)", len(frame) == 1 and bb(np.array(frame[0])) == (10.0, 10.0, 410.0, 287.0), frame[:1])
if shutil.which("qpdf"):
    q = subprocess.run(["qpdf", "--check", pdf], capture_output=True, text=True)
    rec(SEC, "... qpdf --check : aucune erreur de syntaxe", q.returncode == 0 and "No syntax or stream encoding errors" in q.stdout, q.stdout.strip().splitlines()[-1:] if q.stdout else q.stderr[:200])
if shutil.which("pdfinfo"):
    q = subprocess.run(["pdfinfo", pdf], capture_output=True, text=True)
    rec(SEC, "... pdfinfo : A3, producteur Wanderer CAD", "(A3)" in q.stdout and "Wanderer CAD" in q.stdout, [ln for ln in q.stdout.splitlines() if "Page size" in ln or "Producer" in ln])
if shutil.which("pdftoppm"):
    png = _os.path.join(TMP, "page")
    subprocess.run(["pdftoppm", "-r", "254", "-gray", "-png", pdf, png], capture_output=True)      # 254 dpi : 10 pixels par mm
    f = png + "-1.png"
    img = bpy.data.images.load(f) if _os.path.exists(f) else None
    if img is not None:
        W_, H_ = img.size
        px = np.array(img.pixels[:]).reshape(H_, W_, -1)[:, :, 0]         # ligne 0 = bas de la page

        def dark(xmm, ymm, r=2):
            return float(px[int(round(ymm * 10)) - r:int(round(ymm * 10)) + r + 1, int(round(xmm * 10)) - r:int(round(xmm * 10)) + r + 1].min())
        rec(SEC, "... rendu de la page (254 dpi) : 4200 x 2970 pixels, encre sur le bas de A en vue de face (x 300, y 187,5), papier blanc à côté",
            W_ == 4200 and H_ in (2970, 2971) and dark(300.0, 187.5) < 0.35 and dark(300.0, 180.0) > 0.95 and dark(250.0, 200.0) < 0.35 and dark(30.0, 20.0) < 0.6,
            ((W_, H_), round(dark(300.0, 187.5), 3), round(dark(300.0, 180.0), 3), round(dark(250.0, 200.0), 3), round(dark(30.0, 20.0), 3)))
        tx = px[int(170 * 10):int(180 * 10), int(85 * 10):int(100 * 10)]
        rec(SEC, "... le texte du modèle « A8 » est rempli (pixels noirs dans sa zone, à 1:50)", float(tx.min()) < 0.3 and 0.01 < float((tx < 0.5).mean()) < 0.6, (round(float(tx.min()), 3), round(float((tx < 0.5).mean()), 4)))
        bpy.data.images.remove(img)
L2 = m.layout_create(model, "Détails", 'A4', 'PORTRAIT')
detail(L2, 'TOP', 20.0, (0.0, 0.0, 0.0), cx=105.0, cy=180.0, w=150.0, h=100.0)
pdf2 = _os.path.join(TMP, "tout.pdf")
r = bpy.ops.dessin.layout_export_pdf(filepath=pdf2, all_layouts=True, open_after=False)
raw2 = open(pdf2, "rb").read() if _os.path.exists(pdf2) else b""
boxes = re.findall(rb"/MediaBox \[0 0 ([\d.]+) ([\d.]+)\]", raw2)
rec(SEC, "All layouts : deux pages, A3 paysage puis A4 portrait", r == {'FINISHED'} and [(round(float(x_) * 25.4 / 72), round(float(y_) * 25.4 / 72)) for x_, y_ in boxes] == [(420, 297), (210, 297)], boxes)
svg = _os.path.join(TMP, "plan.svg")
r = bpy.ops.dessin.layout_export_svg(filepath=svg)
import xml.dom.minidom as _x
doc = _x.parse(svg) if _os.path.exists(svg) else None
root = doc.documentElement if doc else None
paths_ = doc.getElementsByTagName("path") if doc else []
rec(SEC, "Export SVG : 420 x 297 mm, viewBox en millimètres, traits et aplats", r == {'FINISHED'} and root.getAttribute("width") == "420.000mm" and root.getAttribute("viewBox") == "0 0 420.000 297.000"
    and any(p.getAttribute("stroke-dasharray") == "3.00 1.50" for p in paths_) and any(p.getAttribute("fill-rule") == "evenodd" for p in paths_)
    and any(p.getAttribute("stroke-width") == "0.350" for p in paths_), len(paths_))
dxf = _os.path.join(TMP, "plan.dxf")
r = bpy.ops.dessin.layout_export_dxf(filepath=dxf)
dtxt = open(dxf).read() if _os.path.exists(dxf) else ""
rec(SEC, "Export DXF : R12, calques VISIBLE / HIDDEN (type de ligne HIDDEN) / FRAME / TEXT", r == {'FINISHED'} and "AC1009" in dtxt and all(("\n2\n" + n + "\n") in dtxt for n in ("VISIBLE", "HIDDEN", "FRAME", "TEXT")) and dtxt.rstrip().endswith("EOF"), len(dtxt))
try:
    import ezdxf
    docx = ezdxf.readfile(dxf)
    msp = docx.modelspace()
    vx = [v.dxf.location for e in msp if e.dxftype() == 'POLYLINE' and e.dxf.layer == "VISIBLE" for v in e.vertices]
    fx = [p for p in vx if p[0] > 200.0]
    rec(SEC, "... relu par ezdxf : polylignes du calque VISIBLE aux bonnes coordonnées (vue de face : 250 à 350 mm)", docx.dxfversion == "AC1009" and abs(min(p[0] for p in fx) - 250.0) < 1e-3 and abs(max(p[0] for p in fx) - 350.0) < 1e-3
        and docx.layers.get("HIDDEN").dxf.linetype == "HIDDEN", (len(vx), docx.dxfversion))
except ImportError:
    pass
# couleurs : noir ou couleurs de calque
a.color = (1.0, 0.0, 0.0, 1.0); BC.view_layer.update(); m.detail_rebuild(dF, force=True)
cols_b = {e[3] for e in m.layout_entities(L) if e[0] == 'L' and e[-1] == "Visible"}
L.dessin_layout.print_color = 'COLOR'
cols_c = {tuple(round(x, 3) for x in e[3]) for e in m.layout_entities(L) if e[0] == 'L' and e[-1] == "Visible"}
rec(SEC, "Colors : Black -> tout en noir ; Layer colors -> A en rouge, le blanc devient noir", cols_b == {(0.0, 0.0, 0.0)} and cols_c == {(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)}, (cols_b, cols_c))
L.dessin_layout.show_lineweights = True
vv = kids(dF, 'vis')[0]
rec(SEC, "Show line widths : les traits visibles ont 0,35 mm d'épaisseur à l'écran, le cadre 0,5 mm", abs(vv.data.bevel_depth - 0.175) < 1e-6 and abs(next(o for o in L.objects if o.name.startswith("Frame")).data.bevel_depth - 0.25) < 1e-6, vv.data.bevel_depth)
L.dessin_layout.show_lineweights = False
rec(SEC, "... décoché : simples fils", kids(dF, 'vis')[0].data.bevel_depth == 0.0)
dF.dessin_detail.show_border = False
rec(SEC, "Border décoché : la bordure du détail n'est plus imprimée", sum(1 for e in m.layout_entities(L) if e[-1] == "Viewport borders") == 1)

cwd_before = set(os.listdir("."))
r_empty = [bpy.ops.dessin.layout_export_pdf(), bpy.ops.dessin.layout_export_svg(filepath=""), bpy.ops.dessin.layout_export_dxf(filepath=".dxf")]
rec(SEC, "export lancé sans nom de fichier : refusé, aucun fichier « .pdf » / « .svg » / « .dxf » écrit dans le dossier courant",
    all(r_ == {'CANCELLED'} for r_ in r_empty) and set(os.listdir(".")) == cwd_before, (r_empty, sorted(set(os.listdir(".")) - cwd_before)))

# ---------------------------------------------------------------- I. fichier enregistré puis rouvert
SEC = "fichier"
blend = _os.path.join(TMP, "layout.blend")
n_det = {o.name: len(o.children) for o in m.details(L)}
bpy.ops.wm.save_as_mainfile(filepath=blend, check_existing=False)
bpy.ops.wm.open_mainfile(filepath=blend)
BC = bpy.context
ls = m.layouts()
rec(SEC, "fichier rouvert : les deux mises en page sont là, avec leurs détails et leurs traits", [s.name for s in ls] == ["Plan", "Détails"] and {o.name: len(o.children) for o in m.details(ls[0])} == n_det, [s.name for s in ls])
L = ls[0]
dF = next(o for o in m.details(L) if o.dessin_detail.view == 'FRONT')
rec(SEC, "... réglages conservés (vue, échelle 1:20, affichage, modèle)", dF.dessin_detail.scale == 20.0 and dF.dessin_detail.display == 'HIDDEN_DASHED' and m.detail_model(dF) == bpy.data.scenes["Scene"], (dF.dessin_detail.scale, dF.dessin_detail.display))
ok = m.detail_rebuild(dF, force=True)
rec(SEC, "... le détail se redessine depuis le modèle rechargé", ok and abs(length_of(kids(dF, 'vis')) - 325.0) < 1e-3, round(length_of(kids(dF, 'vis')), 4))
pdf3 = _os.path.join(TMP, "apres.pdf")
r = bpy.ops.dessin.layout_export_pdf(filepath=pdf3, all_layouts=True, open_after=False)
rec(SEC, "... et s'exporte", r == {'FINISHED'} and _os.path.getsize(pdf3) > 2000, _os.path.exists(pdf3) and _os.path.getsize(pdf3))
shutil.rmtree(TMP, ignore_errors=True)
summary()
