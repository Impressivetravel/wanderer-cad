# Ligne de commande : commandes « on désigne les objets, puis Entrée » (DupBorder, Pipe, Intersect, MergeAllFaces, Unroll,
# RebuildSrf) et commandes au survol (Section, Contour, ExtractSrf, DupEdge, Orient). Retour d'un utilisateur : « dupborder,
# Entrée : il ne se passe rien ».
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE, 'harness.py')).read())
exec(open(_os.path.join(_HERE, 'prec_lib.py')).read())
from mathutils import Vector
BC = bpy.context
SEC = "?"
def chk(name, ok, meas=""): rec(SEC, name, ok, meas)
def mk(name, verts, faces, loc=(0, 0, 0)):
    me = bpy.data.meshes.new(name); me.from_pydata(verts, [], faces); me.update()
    o = bpy.data.objects.new(name, me); BC.scene.collection.objects.link(o); o.location = loc; BC.view_layer.update(); return o
def plane(w=4.0, h=3.0, **kw): return mk("Plane", [(0, 0, 0), (w, 0, 0), (w, h, 0), (0, h, 0)], [(0, 1, 2, 3)], **kw)
def cube(a=2.0, tri=False, **kw):
    v = [(0, 0, 0), (a, 0, 0), (a, a, 0), (0, a, 0), (0, 0, a), (a, 0, a), (a, a, a), (0, a, a)]
    f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    if tri: f = [t for q in f for t in ((q[0], q[1], q[2]), (q[0], q[2], q[3]))]
    return mk("Cube", v, f, **kw)
def sel(*objs):
    for q in bpy.data.objects: q.select_set(q in objs)
    BC.view_layer.objects.active = objs[0] if objs else None; BC.view_layer.update()
def curves(): return [o for o in bpy.data.objects if o.type == 'CURVE']
def clen(o):
    tot = 0.0
    for s in o.data.splines:
        P = [o.matrix_world @ Vector(p.co[:3]) for p in s.points]
        tot += sum((b - a).length for a, b in zip(P, P[1:] + (P[:1] if s.use_cyclic_u else [])))
    return tot
# la ligne de commande sans écran : armer un outil et lancer une commande sont notés (et la commande exécutée pour de vrai)
armed, invoked, now = [], [], []
m.arm_tool = lambda name: armed.append(name)
m.run_soon = lambda fn, delay=0.1: fn()
def _invoke_in(window, area, region, name):
    invoked.append(name); getattr(bpy.ops.dessin, name)()
m.op_invoke_in = _invoke_in
m.op_invoke = lambda name: now.append(name)
ctx._o['window'] = object()
def typed(word):
    """Ce que fait la ligne de commande quand on tape un mot puis Entrée : la première suggestion est lancée."""
    del armed[:], invoked[:], now[:]
    sg = m.cmd_suggest(word)
    err = m.cmd_run(ctx, sg[0]) if sg else "no suggestion"
    BC.view_layer.update()
    return sg[0] if sg else None, err
def run(opcls, how="execute"):
    o = make(opcls)
    r = getattr(type(o), how)(o, ctx) if how == "execute" else type(o).invoke(o, ctx, ev('NONE', 'NOTHING', 500, 500))
    BC.view_layer.update(); return r, o
ELEVEN = {"Pipe": ("pipe", "dessin.pipe_tool"), "Intersect": ("intersect", "dessin.intersect_tool"), "Section": ("section", "dessin.section_tool"),
          "Contour": ("contour", "dessin.contour_tool"), "Extract Surface": ("extractsrf", "dessin.extract_srf_tool"),
          "Duplicate Border": ("dupborder", "dessin.dup_border_tool"), "Duplicate Edge": ("dupedge", "dessin.dup_edge_tool"),
          "Merge All Faces": ("mergeallfaces", "dessin.merge_faces_tool"), "Unroll Surface": ("unrollsrf", "dessin.unroll_tool"),
          "Rebuild Surface": ("rebuildsrf", "dessin.rebuild_srf_tool"), "Orient": ("orient2pt", "dessin.orient_tool")}

# ================= 1. Une seule entrée par commande =================
SEC = "entrées"
ents = [e for e in m.cmd_entries() if e["kind"] in ("tool", "act")]
labels = [e["label"] for e in ents]
dups = sorted({l for l in labels if labels.count(l) > 1})
chk("aucune commande n'apparaît deux fois dans la ligne de commande", not dups, dups)
for lab, (alias, tid) in ELEVEN.items():
    sg = m.cmd_suggest(alias)
    chk(f"« {alias} » : une seule suggestion, l'outil {lab}", len(sg) >= 1 and sg[0]["key"] == "tool:" + tid and sum(1 for e in sg if e["label"] == lab) == 1, [(e["label"], e["key"]) for e in sg[:3]])
    sg = m.cmd_suggest(lab)
    chk(f"« {lab} » (nom complet) : même outil en tête", bool(sg) and sg[0]["key"] == "tool:" + tid, [(e["label"], e["key"]) for e in sg[:2]])
for word, tid in (("int", "dessin.intersect_tool"), ("sec", "dessin.section_tool"), ("unroll", "dessin.unroll_tool"), ("mergeallcoplanarfaces", "dessin.merge_faces_tool"), ("orient", "dessin.orient_tool"), ("pipe", "dessin.pipe_tool")):
    sg = m.cmd_suggest(word)
    chk(f"alias « {word} »", bool(sg) and sg[0]["key"] == "tool:" + tid, [(e["label"], e["key"]) for e in sg[:2]])
real_lang = m.lang
m.lang = lambda: 'FR'
try:
    for word, tid in (("dupliquerbord", "dessin.dup_border_tool"), ("tuyau", "dessin.pipe_tool"), ("developper", "dessin.unroll_tool"), ("fusionnerfaces", "dessin.merge_faces_tool"),
                      ("reconstruiresrf", "dessin.rebuild_srf_tool"), ("intersectionobjets", "dessin.intersect_tool"), ("coupe", "dessin.section_tool"), ("orienter", "dessin.orient_tool"),
                      ("extrairesrf", "dessin.extract_srf_tool"), ("dupliquerarete", "dessin.dup_edge_tool"), ("contours", "dessin.contour_tool")):
        sg = m.cmd_suggest(word)
        chk(f"français : alias « {word} »", bool(sg) and sg[0]["key"] == "tool:" + tid, [(e["label"], e["key"]) for e in sg[:2]])
    fr = m.tr_text("Duplicate Border: a closed solid has no free border  ·  use Duplicate Edge (DupEdge) to copy one of its edges")
    chk("français : le message du solide fermé est traduit", "solide fermé" in fr and "DupEdge" in fr and "closed" not in fr, fr)
    fr = m.tr_text("click the surfaces first, then Enter")
    chk("français : « cliquer d'abord les surfaces, puis Entrée »", fr == "cliquer d'abord les surfaces, puis Entrée", fr)
finally:
    m.lang = real_lang

# ================= 2. DupBorder =================
SEC = "DupBorder"
clear(); m.cmd_notice_clear()
chk("rien de sélectionné : la commande attend qu'on désigne (mode « arm »)", m.tool_run_mode(ctx, "dessin.dup_border_tool") == 'arm')
e, err = typed("dupborder")
chk("« dupborder » + Entrée sans sélection : l'outil de désignation est armé", err == "" and armed == ["dessin.dup_border_tool"] and not invoked and not curves(), (err, armed, invoked))
chk("... la barre de commande dit quoi faire (cliquer les surfaces, puis Entrée)", "Click the surfaces" in m.DESSIN_TT_dup_border.dessin_hint and "Enter" in m.DESSIN_TT_dup_border.dessin_hint, m.DESSIN_TT_dup_border.dessin_hint)
chk("... la commande est retenue pour Entrée = répéter", m._CMD["last"] == "tool:dessin.dup_border_tool", m._CMD["last"])
keys = {(k[0], k[1]["type"]) for k in m.DESSIN_TT_dup_border.bl_keymap}
chk("... outil armé : clic = désigner, Entrée / Espace = lancer, Échap = quitter",
    ("dessin.pick_object", 'LEFTMOUSE') in keys and ("dessin.dup_border", 'RET') in keys and ("dessin.dup_border", 'SPACE') in keys and ("dessin.tool_exit", 'ESC') in keys, sorted(keys))
r, o = run(m.DESSIN_OT_dup_border)
chk("Entrée sans avoir rien désigné : avertissement (et non un simple message discret)", 'CANCELLED' in r and o._reports and o._reports[0][0] == 'WARNING', o._reports)
chk("... répété dans la barre de commande", "click the surfaces first" in (m.cmd_notice_text() or ""), m.cmd_notice_text())
P = plane(4.0, 3.0, loc=(1, 1, 0)); sel(P)                      # on clique la surface, puis Entrée
r, o = run(m.DESSIN_OT_dup_border)
cs = curves()
chk("surface désignée puis Entrée : une courbe de bordure fermée", 'FINISHED' in r and len(cs) == 1 and cs[0].data.splines[0].use_cyclic_u, (r, len(cs)))
chk("... longueur = périmètre 4 x 3 (14)", len(cs) == 1 and abs(clen(cs[0]) - 14.0) < 1e-6, [clen(c) for c in cs])
chk("... la courbe est sélectionnée", len(cs) == 1 and cs[0].select_get() and not P.select_get())

clear(); m.cmd_notice_clear()
P = plane(4.0, 3.0, loc=(1, 1, 0)); sel(P)
chk("surface déjà sélectionnée : la commande part tout de suite (mode « selection »)", m.tool_run_mode(ctx, "dessin.dup_border_tool") == 'selection')
e, err = typed("dupborder")
cs = curves()
chk("« dupborder » + Entrée avec une surface sélectionnée : la bordure est créée tout de suite", err == "" and invoked == ["dup_border"] and len(cs) == 1 and abs(clen(cs[0]) - 14.0) < 1e-6, (err, invoked, [clen(c) for c in cs]))
chk("... sans message d'avertissement", m.cmd_notice_text() is None, m.cmd_notice_text())

clear(); m.cmd_notice_clear()
Cb = cube(2.0); sel(Cb)
e, err = typed("dupborder")
chk("solide fermé sélectionné : aucune courbe (un solide n'a pas de bord libre)", invoked == ["dup_border"] and not curves(), (invoked, len(curves())))
note = m.cmd_notice_text() or ""
chk("... la barre de commande l'explique et propose Duplicate Edge", "closed solid" in note and "Duplicate Edge" in note, note)
r, o = run(m.DESSIN_OT_dup_border)
chk("... en avertissement", o._reports and o._reports[0][0] == 'WARNING' and "closed solid" in o._reports[0][1], o._reports)
# boîte ouverte (sans couvercle) : la bordure est le carré du haut
clear(); m.cmd_notice_clear()
a = 2.0
Ob = mk("Open", [(0, 0, 0), (a, 0, 0), (a, a, 0), (0, a, 0), (0, 0, a), (a, 0, a), (a, a, a), (0, a, a)],
        [(0, 3, 2, 1), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]); sel(Ob)
e, err = typed("dupborder")
cs = curves()
zs = [round((cs[0].matrix_world @ Vector(p.co[:3])).z, 6) for p in cs[0].data.splines[0].points] if cs else []
chk("boîte sans couvercle : une bordure, le carré du haut (périmètre 8, z = 2)", len(cs) == 1 and abs(clen(cs[0]) - 8.0) < 1e-6 and set(zs) == {2.0}, ([clen(c) for c in cs], zs))
m.cmd_notice("x")
e, err = typed("dupborder")
chk("une nouvelle commande efface le message de la précédente", m.cmd_notice_text() is None or "x" != m.cmd_notice_text(), m.cmd_notice_text())

# ================= 3. Les autres commandes « on désigne, puis Entrée » =================
SEC = "désigner"
for lab, tid, opname, cls in (("Pipe", "dessin.pipe_tool", "pipe", m.DESSIN_OT_pipe), ("Intersect", "dessin.intersect_tool", "intersect", m.DESSIN_OT_intersect),
                              ("Merge All Faces", "dessin.merge_faces_tool", "merge_faces", m.DESSIN_OT_merge_faces), ("Unroll Surface", "dessin.unroll_tool", "unroll", m.DESSIN_OT_unroll),
                              ("Rebuild Surface", "dessin.rebuild_srf_tool", "rebuild_srf", m.DESSIN_OT_rebuild_srf)):
    clear(); m.cmd_notice_clear()
    e, err = typed(ELEVEN[lab][0])
    chk(f"{lab} sans sélection : outil armé, rien n'est lancé", err == "" and armed == [tid] and not invoked and len(bpy.data.objects) == 0, (err, armed, invoked))
    r, o = run(cls, "invoke" if hasattr(cls, "invoke") and "invoke" in vars(cls) else "execute")
    chk(f"... Entrée sans rien désigner : avertissement visible dans la barre", 'CANCELLED' in r and o._reports and o._reports[0][0] == 'WARNING' and (m.cmd_notice_text() or "").startswith(lab.split()[0]), (o._reports, m.cmd_notice_text()))
    chk(f"... l'outil garde une indication (cliquer, puis Entrée)", "Click" in getattr(m, "DESSIN_TT_" + opname).dessin_hint and "Enter" in getattr(m, "DESSIN_TT_" + opname).dessin_hint)
# Intersect : deux surfaces qui se croisent, sélectionnées avant
clear(); m.cmd_notice_clear()
A = plane(4.0, 4.0, loc=(0, 0, 1))
B = mk("V", [(2, -1, 0), (2, 5, 0), (2, 5, 3), (2, -1, 3)], [(0, 1, 2, 3)]); sel(A, B)
e, err = typed("intersect")
cs = curves()
chk("Intersect avec deux surfaces sélectionnées : la courbe d'intersection est créée tout de suite (longueur 4)", invoked == ["intersect"] and len(cs) == 1 and abs(clen(cs[0]) - 4.0) < 1e-6, (invoked, [clen(c) for c in cs]))
clear(); m.cmd_notice_clear()
A = plane(4.0, 4.0); sel(A)
e, err = typed("intersect")
chk("Intersect avec un seul objet : avertissement « au moins deux objets », l'outil reste armé", armed == ["dessin.intersect_tool"] and "at least two" in (m.cmd_notice_text() or ""), m.cmd_notice_text())
clear(); m.cmd_notice_clear()
A = plane(4.0, 4.0); B = plane(4.0, 4.0, loc=(10, 0, 0)); sel(A, B)
e, err = typed("intersect")
chk("Intersect, deux objets qui ne se touchent pas : dit dans la barre", "do not intersect" in (m.cmd_notice_text() or "") and not curves(), m.cmd_notice_text())
# MergeAllFaces
clear(); m.cmd_notice_clear()
Cb = cube(2.0, tri=True); sel(Cb)
e, err = typed("mergeallfaces")
chk("Merge All Faces sur un cube triangulé sélectionné : 12 faces -> 6", invoked == ["merge_faces"] and len(Cb.data.polygons) == 6 and m.cmd_notice_text() is None, (invoked, len(Cb.data.polygons)))
e, err = typed("mergeallfaces")
chk("... une seconde fois : « rien à fusionner », dit dans la barre", len(Cb.data.polygons) == 6 and "no coplanar faces" in (m.cmd_notice_text() or ""), m.cmd_notice_text())
# Unroll : demi-cylindre (développable)
clear(); m.cmd_notice_clear()
nseg = 24; rad = 1.0; hgt = 2.0
vv = [(rad * math.cos(math.pi * i / nseg), rad * math.sin(math.pi * i / nseg), z) for i in range(nseg + 1) for z in (0.0, hgt)]
ff = [(2 * i, 2 * i + 2, 2 * i + 3, 2 * i + 1) for i in range(nseg)]
half = mk("Half", vv, ff); sel(half)
area0 = sum(p.area for p in half.data.polygons)
e, err = typed("unroll")
flat = [o for o in bpy.data.objects if o is not half]
fa = sum(p.area for p in flat[0].data.polygons) if flat else 0.0
zs = [abs((flat[0].matrix_world @ v.co).z) for v in flat[0].data.vertices] if flat else [1]
chk("Unroll avec une surface sélectionnée : patron plat de même aire, dans le plan", invoked == ["unroll"] and len(flat) == 1 and abs(fa - area0) < 1e-6 * area0 and max(zs) < 1e-6, (invoked, fa, area0))
# Pipe : courbe sélectionnée -> la boîte de réglages s'ouvre (rayon, côtés)
clear(); m.cmd_notice_clear()
L = m.build_polyline(BC, "Axe", [Vector((0, 0, 0)), Vector((4, 0, 0))], False); sel(L)
chk("Pipe avec une courbe sélectionnée : mode « selection »", m.tool_run_mode(ctx, "dessin.pipe_tool") == 'selection')
r, o = run(m.DESSIN_OT_pipe, "invoke")
chk("... la boîte rayon / options s'ouvre", 'RUNNING_MODAL' in r and not o._reports, (r, o._reports))
o.radius = 0.5; r = type(o).execute(o, ctx); BC.view_layer.update()
tubes = [q for q in bpy.data.objects if q.type == 'MESH']
chk("... OK : un tube de 4 de long et 1 de diamètre", 'FINISHED' in r and len(tubes) == 1 and abs(tubes[0].dimensions.x - 4.0) < 1e-6 and abs(tubes[0].dimensions.z - 1.0) < 1e-3, (r, [tuple(t.dimensions) for t in tubes]))
sel(tubes[0])
e, err = typed("pipe")
chk("Pipe avec un maillage sélectionné (pas de courbe) : avertissement, l'outil reste armé", armed == ["dessin.pipe_tool"] and "click the curves first" in (m.cmd_notice_text() or ""), m.cmd_notice_text())

# ================= 4. Commandes au survol =================
SEC = "survol"
clear(); m.cmd_notice_clear()
for lab, tid, opname in (("Extract Surface", "dessin.extract_srf_tool", "extract_srf"), ("Duplicate Edge", "dessin.dup_edge_tool", "dup_edge")):
    chk(f"{lab} : mode « now » (rien à désigner avant)", m.tool_run_mode(ctx, tid) == 'now')
    e, err = typed(ELEVEN[lab][0])
    chk(f"{lab} depuis la ligne de commande : la commande démarre tout de suite (sans armer l'outil, qui prendrait le clic sur la suggestion pour une désignation)",
        err == "" and armed == [] and now == [opname] and not invoked, (err, armed, now))
    chk(f"... et Entrée la répète", m._CMD["last"] == "tool:" + tid and m.cmd_by_key(m._CMD["last"]) is not None, m._CMD["last"])
for lab, tid in (("Section", "dessin.section_tool"), ("Contour", "dessin.contour_tool"), ("Orient", "dessin.orient_tool")):
    Cb = cube(2.0); sel(Cb)
    chk(f"{lab} : mode « arm » même avec une sélection (la commande démarre au survol de la vue)", m.tool_run_mode(ctx, tid) == 'arm')
    e, err = typed(ELEVEN[lab][0])
    chk(f"{lab} depuis la ligne de commande : outil armé", err == "" and armed == [tid] and not invoked and not now, (err, armed, invoked, now))
    clear()
m.cmd_notice_clear()
for cls in (m.DESSIN_OT_section, m.DESSIN_OT_contour):
    o = make(cls)
    r = type(o).invoke(o, ctx, ev('NONE', 'NOTHING', 500, 500))
    chk(f"{cls.bl_label} lancée sans sélection : avertissement dans la barre (et non plus un message discret)",
        'CANCELLED' in r and o._reports and o._reports[0][0] == 'WARNING' and "cut first" in (m.cmd_notice_text() or ""), (r, o._reports, m.cmd_notice_text()))
    m.cmd_notice_clear()
# Section : objet sélectionné, deux clics -> la section (carré 2 x 2 d'un cube coupé en son milieu)
clear()
Cb = cube(2.0, loc=(-1, -1, 0)); sel(Cb)
o = make(m.DESSIN_OT_section)
r = type(o).invoke(o, ctx, ev('NONE', 'NOTHING', *scr(-3, 0)))
for x, y in ((-3, 0), (3, 0)):
    sx, sy = scr(x, y)
    for e_ in (ev('MOUSEMOVE', 'NOTHING', sx, sy), ev('LEFTMOUSE', 'PRESS', sx, sy), ev('LEFTMOUSE', 'RELEASE', sx, sy)):
        r = type(o).modal(o, ctx, e_)
        if 'FINISHED' in r or 'CANCELLED' in r: break
BC.view_layer.update()
cs = curves()
chk("Section d'un cube sélectionné (ligne par son milieu) : un carré 2 x 2, périmètre 8", len(cs) == 1 and abs(clen(cs[0]) - 8.0) < 1e-6, [clen(c) for c in cs])

# ================= 5. Courbes ouvertes (surfaces ouvertes) =================
# Défaut trouvé en écrivant ces essais : Intersect, Section et Contour écartaient toute courbe qui ne se refermait pas
# (deux surfaces planes qui se croisent ne donnaient rien : « the selected objects do not intersect »)
SEC = "ouvertes"
import numpy as np
ch = m._segments_to_chains(np.array([[2., 2, 1], [2, 0, 1]]), np.array([[2., 4, 1], [2, 2, 1]]), 1e-6)
chk("deux segments alignés bout à bout : une courbe ouverte de 2 points (0 -> 4)", len(ch) == 1 and ch[0][1] is False and len(ch[0][0]) == 2 and abs(np.linalg.norm(ch[0][0][1] - ch[0][0][0]) - 4.0) < 1e-9, [(len(c), cl) for c, cl in ch])
ch = m._segments_to_chains(np.array([[0., 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]]), np.array([[1., 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 0]]), 1e-6)
chk("quatre segments en carré : toujours une boucle fermée de 4 points", len(ch) == 1 and ch[0][1] is True and len(ch[0][0]) == 4, [(len(c), cl) for c, cl in ch])
clear(); m.cmd_notice_clear()
A = plane(4.0, 4.0, loc=(0, 0, 1))
B = mk("V", [(2, 1, 0), (2, 3, 0), (2, 3, 3), (2, 1, 3)], [(0, 1, 2, 3)]); sel(A, B)
r = bpy.ops.dessin.intersect(); BC.view_layer.update()
cs = curves()
pts = [tuple(round(c, 6) for c in (cs[0].matrix_world @ Vector(p.co[:3]))) for p in cs[0].data.splines[0].points] if cs else []
chk("Intersect d'un plan et d'une cloison plus étroite : une ligne ouverte (2,1,1) -> (2,3,1)", 'FINISHED' in r and len(cs) == 1 and not cs[0].data.splines[0].use_cyclic_u and sorted(pts) == [(2.0, 1.0, 1.0), (2.0, 3.0, 1.0)], pts)
clear()
Cb = cube(2.0)
Pl = mk("Cut", [(1, -1, 1), (3, -1, 1), (3, 3, 1), (1, 3, 1)], [(0, 1, 2, 3)]); sel(Cb, Pl)
r = bpy.ops.dessin.intersect(); BC.view_layer.update()
cs = curves()
pts = [tuple(round(c, 6) for c in (cs[0].matrix_world @ Vector(p.co[:3]))) for p in cs[0].data.splines[0].points] if cs else []
chk("Intersect d'un cube et d'un plan qui n'y entre qu'à moitié : un U ouvert de 4 sommets, longueur 4",
    len(cs) == 1 and len(cs[0].data.splines) == 1 and not cs[0].data.splines[0].use_cyclic_u and len(pts) == 4 and abs(clen(cs[0]) - 4.0) < 1e-6
    and set(pts) == {(1.0, 0.0, 1.0), (2.0, 0.0, 1.0), (2.0, 2.0, 1.0), (1.0, 2.0, 1.0)}, pts)
clear()
A = plane(4.0, 4.0, loc=(-2, -2, 0)); sel(A)
o = make(m.DESSIN_OT_section)
r = type(o).invoke(o, ctx, ev('NONE', 'NOTHING', *scr(-3, 0)))
for x, y in ((-3, 0), (3, 0)):
    sx, sy = scr(x, y)
    for e_ in (ev('MOUSEMOVE', 'NOTHING', sx, sy), ev('LEFTMOUSE', 'PRESS', sx, sy), ev('LEFTMOUSE', 'RELEASE', sx, sy)):
        r = type(o).modal(o, ctx, e_)
        if 'FINISHED' in r or 'CANCELLED' in r: break
BC.view_layer.update()
cs = curves()
pts = [tuple(round(c, 6) for c in (cs[0].matrix_world @ Vector(p.co[:3]))) for p in cs[0].data.splines[0].points] if cs else []
chk("Section d'une surface plane ouverte : une ligne ouverte (-2,0,0) -> (2,0,0)", len(cs) == 1 and not cs[0].data.splines[0].use_cyclic_u and sorted(pts) == [(-2.0, 0.0, 0.0), (2.0, 0.0, 0.0)], (pts, o._reports))
# Contour d'un demi-cylindre ouvert : des arcs ouverts, un par plan
clear()
half = mk("Half", vv, ff); sel(half)
dg = BC.evaluated_depsgraph_get()
sl = m._Slicer(BC, [half]); sl.set_normal(Vector((0, 0, 1)))
arc = 2 * nseg * math.sin(math.pi / (2 * nseg))            # longueur de la ligne brisée inscrite dans le demi-cercle de rayon 1
cuts = [sl.cut(z) for z in (0.5, 1.0, 1.5)]
ok = all(len(chains) == 1 and chains[0][1] is False and abs(sum(np.linalg.norm(b - a) for a, b in zip(chains[0][0], chains[0][0][1:])) - arc) < 1e-6 for chains, _p in cuts)
chk("Contour d'un demi-cylindre (surface ouverte) : un arc ouvert par plan, de la bonne longueur", ok, [[(len(c), cl) for c, cl in chains] for chains, _p in cuts])

summary()
