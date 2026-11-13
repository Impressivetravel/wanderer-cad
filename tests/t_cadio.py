# Export DXF du modèle, import et export DWG par un convertisseur. Le DXF écrit est relu par un lecteur indépendant
# (ezdxf, s'il est installé : pip install ezdxf) et par l'import de l'add-on ; la passerelle DWG est essayée avec un faux
# convertisseur qui note ses arguments (le vrai ODA File Converter n'est pas installé sur la machine d'essai).
import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
exec(open(_os.path.join(_HERE,'prec_lib.py')).read())
import json, math, os, shutil, stat, tempfile
BC = bpy.context
TMP = tempfile.mkdtemp(prefix="wd_cadio_")
SEC = "?"
def chk(name, ok, meas=""): rec(SEC, name, ok, meas)
try:
    import ezdxf
except Exception:
    ezdxf = None


def curve(name, pts, closed=False, kind='POLY', col=None, order=4, endpoint=True):
    cu = bpy.data.curves.new(name, 'CURVE'); cu.dimensions = '3D'
    sp = cu.splines.new(kind)
    sp.points.add(len(pts) - 1)
    for p, q in zip(sp.points, pts):
        p.co = (q[0], q[1], q[2], 1.0)
    sp.use_cyclic_u = closed
    if kind == 'NURBS':
        sp.order_u = order; sp.use_endpoint_u = endpoint
    o = bpy.data.objects.new(name, cu)
    (col or BC.scene.collection).objects.link(o)
    return o


def mesh(name, verts, faces=(), edges=(), col=None, loc=(0, 0, 0)):
    me = bpy.data.meshes.new(name); me.from_pydata(verts, edges, faces); me.update()
    o = bpy.data.objects.new(name, me); o.location = loc
    (col or BC.scene.collection).objects.link(o)
    return o


def text(name, body, size, loc, rotz=0.0, align='LEFT'):
    fc = bpy.data.curves.new(name, 'FONT'); fc.body = body; fc.size = size; fc.align_x = align
    o = bpy.data.objects.new(name, fc); o.location = loc; o.rotation_euler = (0, 0, math.radians(rotz))
    BC.scene.collection.objects.link(o)
    return o


def build():
    clear()
    us = BC.scene.unit_settings; us.system = 'METRIC'; us.scale_length = 1.0; us.length_unit = 'MILLIMETERS'
    walls = bpy.data.collections.new("Murs porteurs"); BC.scene.collection.children.link(walls)
    walls.dessin_layer.color = (1.0, 0.0, 0.0); walls.dessin_layer.use_color = True
    made = {}
    made["line"] = curve("Ligne", [(0, 0, 0), (2, 1, 0)], col=walls)
    made["rect"] = curve("Rectangle", [(0, 0, 0.5), (3, 0, 0.5), (3, 2, 0.5), (0, 2, 0.5)], closed=True)
    made["p3d"] = curve("Poly3D", [(0, 0, 0), (1, 0, 1), (1, 1, 2), (0, 1, 3)])
    bpy.ops.curve.primitive_bezier_circle_add(radius=1.5, location=(5, 5, 0))
    made["circle"] = BC.view_layer.objects.active
    # arc de 30° à 200°, rayon 2, centre (0, 5, 1), dans un plan incliné de 30° autour de X
    ca, sa = math.cos(math.radians(30)), math.sin(math.radians(30))
    arc = []
    for i in range(40):
        a = math.radians(30 + 170 * i / 39.0)
        x, y = 2 * math.cos(a), 2 * math.sin(a)
        arc.append((x, 5 + y * ca, 1 + y * sa))
    made["arc"] = curve("Arc", arc)
    made["arc_pts"] = arc
    made["nurbs"] = curve("Nurbs", [(6, 0, 0), (7, 2, 0), (8, -1, 0), (9, 2, 1), (10, 0, 1), (11, 1, 0)], kind='NURBS')
    made["dodeca"] = curve("Dodecagone", [(20 + math.cos(math.radians(30 * i)), math.sin(math.radians(30 * i)), 0) for i in range(12)], closed=True)
    made["box"] = mesh("Boite", [(-.5, -.5, -.5), (.5, -.5, -.5), (.5, .5, -.5), (-.5, .5, -.5), (-.5, -.5, .5), (.5, -.5, .5), (.5, .5, .5), (-.5, .5, .5)],
                       [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)], loc=(10, 5, 0.5))
    made["hexa"] = mesh("Hexagone", [(math.cos(math.radians(60 * i)), math.sin(math.radians(60 * i)), 0) for i in range(6)], [tuple(range(6))], loc=(14, 5, 0))
    made["wire"] = mesh("Fil", [(0, 0, 0), (0, 0, 2)], edges=[(0, 1)], loc=(16, 0, 0))
    made["t1"] = text("Texte", "Salon été", 0.3, (2, 8, 0), rotz=30.0)
    made["t2"] = text("Titre", "PLAN", 0.5, (6, 8, 0), align='CENTER')
    hid = curve("Cache", [(0, 0, 0), (50, 50, 50)])
    hid.hide_set(True)
    BC.view_layer.update()
    return made


def export(path, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        try:
            return bpy.ops.dessin.export_cad('EXEC_DEFAULT', filepath=path, **kw)
        except RuntimeError as ex:
            return str(ex)

# ================= 1. Reconnaître un arc, échantillonner une courbe =================
SEC = "courbes"
ring = [(3 + 2 * math.cos(math.radians(a)), 1 + 2 * math.sin(math.radians(a)), 4.0) for a in np.arange(0, 360, 360 / 64.0)]
f = m.fit_circle(ring, True)
chk("64 points d'un cercle : centre (3, 1, 4), rayon 2, normale Z", f is not None and near(f[0], (3, 1, 4), 1e-9) and abs(f[1] - 2) < 1e-9 and near(f[2], (0, 0, 1), 1e-9), f and (tuple(f[0]), f[1]))
ccw = [(2 * math.cos(math.radians(a)), 2 * math.sin(math.radians(a)), 0.0) for a in np.linspace(20, 250, 30)]
f = m.fit_circle(ccw, False)
chk("arc de 20° à 250° dans le sens direct : normale +Z, angles 20 et 250", f is not None and near(f[2], (0, 0, 1), 1e-9) and abs(f[3] - 20) < 1e-6 and abs(f[4] - 250) < 1e-6, f and (tuple(f[2]), f[3], f[4]))
f = m.fit_circle(ccw[::-1], False)
ax, ay, nz = m.dxf_ocs(f[2]) if f else (None, None, None)
p0 = f and (np.array(f[0]) + f[1] * (math.cos(math.radians(f[3])) * ax + math.sin(math.radians(f[3])) * ay))
p1 = f and (np.array(f[0]) + f[1] * (math.cos(math.radians(f[4])) * ax + math.sin(math.radians(f[4])) * ay))
chk("le même arc parcouru dans l'autre sens : la normale se retourne (-Z) et les angles redonnent ses deux extrémités", f is not None and near(f[2], (0, 0, -1), 1e-9)
    and near(p0, ccw[-1], 1e-9) and near(p1, ccw[0], 1e-9), f and (tuple(f[2]), f[3], f[4]))
oval = [(3 * math.cos(math.radians(a)), 2 * math.sin(math.radians(a)), 0.0) for a in np.arange(0, 360, 6)]
helix = [(math.cos(math.radians(a)), math.sin(math.radians(a)), a / 360.0) for a in np.arange(0, 360, 6)]
zig = [(math.cos(math.radians(a)), math.sin(math.radians(a)), 0.0) for a in (0, 20, 40, 30, 60, 80, 100, 120, 140, 160)]
chk("une ellipse, une hélice, des points qui reviennent en arrière : pas des arcs", m.fit_circle(oval, True) is None and m.fit_circle(helix, False) is None and m.fit_circle(zig, False) is None)
made = build()
for key, what in (("nurbs", "NURBS ouverte (ordre 4, extrémités atteintes)"), ("circle", "cercle de Bézier")):
    o = made[key]
    sp = o.data.splines[0]
    mine, closed, smooth = m.spline_points(sp, o.data.resolution_u)
    mine = np.array([tuple(o.matrix_world @ p) for p in mine])
    ev_ = o.evaluated_get(BC.evaluated_depsgraph_get()); me = ev_.to_mesh()
    ref = np.array([tuple(o.matrix_world @ v.co) for v in me.vertices]); ev_.to_mesh_clear()
    seg_a = mine if not closed else np.vstack((mine, mine[:1]))
    def dist(p):
        best = 1e9
        for a, b in zip(seg_a[:-1], seg_a[1:]):
            ab = b - a; t = max(0.0, min(1.0, float((p - a) @ ab) / max(float(ab @ ab), 1e-18)))
            best = min(best, float(np.linalg.norm(p - (a + t * ab))))
        return best
    worst = max(dist(p) for p in ref)
    size = float(np.ptp(ref, axis=0).max())
    ends = closed or (near(mine[0], ref[0], 1e-6) and near(mine[-1], ref[-1], 1e-6))
    chk(f"{what} : les points calculés par Blender sont sur la courbe échantillonnée (écart < 0,5 % de sa taille), mêmes extrémités",
        smooth and worst < 0.005 * size and ends, (round(worst, 5), round(size, 3), len(mine), len(ref)))

# ================= 2. Le fichier DXF, relu par un lecteur indépendant =================
SEC = "DXF"
path = os.path.join(TMP, "modele.dxf")
r = export(path, units='MM')
chk("Export DXF : le fichier est écrit", r == {'FINISHED'} and os.path.isfile(path) and os.path.getsize(path) > 2000, (r, os.path.exists(path)))
raw = open(path, encoding="cp1252").read()
chk("... en DXF R12 (AC1009), page de code Windows-1252, terminé par EOF", "AC1009" in raw and "ANSI_1252" in raw and raw.rstrip().endswith("EOF"))
header, layers, blocks, ents = m.dxf_parse(open(path, "rb").read())
kinds = {}
for e in ents:
    k = m.dxf_get(e, 0) if not isinstance(e, dict) else e.get("type")
    kinds[k] = kinds.get(k, 0) + 1
if ezdxf is None:
    print("NOTE : ezdxf n'est pas installé (pip install ezdxf) : la relecture indépendante du DXF est sautée.")
else:
    doc = ezdxf.readfile(path)
    aud = doc.audit()
    msp = doc.modelspace()
    chk("ezdxf lit le fichier sans erreur ni réparation", len(aud.errors) == 0 and len(aud.fixes) == 0, (len(aud.errors), len(aud.fixes)))
    cnt = {}
    for e in msp:
        cnt[e.dxftype()] = cnt.get(e.dxftype(), 0) + 1
    chk("entités : 2 LINE (ligne, arête libre), 4 POLYLINE (rectangle, polyligne 3D, NURBS, dodécagone), 1 CIRCLE, 1 ARC, 10 3DFACE (6 + 4), 2 TEXT ; l'objet caché n'y est pas",
        cnt == {"LINE": 2, "POLYLINE": 4, "CIRCLE": 1, "ARC": 1, "3DFACE": 10, "TEXT": 2}, cnt)
    L = {l.dxf.name: l.dxf.color for l in doc.layers}
    ln = [e for e in msp if e.dxftype() == "LINE" and e.dxf.layer == "MURS_PORTEURS"]
    chk("calque « Murs porteurs » -> MURS_PORTEURS, rouge (couleur 1) ; la ligne y est, couleur du calque", L.get("MURS_PORTEURS") == 1 and len(ln) == 1 and ln[0].dxf.color == 256, (L, len(ln)))
    chk("la ligne (0, 0)-(2, 1) m est écrite en millimètres : (0, 0, 0)-(2000, 1000, 0)", len(ln) == 1 and near(ln[0].dxf.start, (0, 0, 0)) and near(ln[0].dxf.end, (2000, 1000, 0)), ln and (tuple(ln[0].dxf.start), tuple(ln[0].dxf.end)))
    wire = [e for e in msp if e.dxftype() == "LINE" and e.dxf.layer == "0"]
    chk("l'arête libre du maillage : une LINE de (16000, 0, 0) à (16000, 0, 2000)", len(wire) == 1 and near(sorted([tuple(wire[0].dxf.start), tuple(wire[0].dxf.end)]), [(16000, 0, 0), (16000, 0, 2000)]))
    pl = {len(list(e.vertices)): e for e in msp if e.dxftype() == "POLYLINE"}
    rect = next((e for e in msp if e.dxftype() == "POLYLINE" and e.is_2d_polyline and len(list(e.vertices)) == 4), None)
    rp = [tuple(v.dxf.location) for v in rect.vertices] if rect is not None else []
    chk("le rectangle : polyligne 2D fermée, à l'altitude 500 mm, ses 4 sommets exacts", rect is not None and rect.is_2d_polyline and rect.is_closed and abs(rect.dxf.elevation[2] - 500) < 1e-9
        and near([p[:2] for p in rp], [(0, 0), (3000, 0), (3000, 2000), (0, 2000)]), rp)
    p3 = [e for e in msp if e.dxftype() == "POLYLINE" and e.is_3d_polyline and len(list(e.vertices)) == 4]
    chk("la polyligne gauche : polyligne 3D ouverte, sommets exacts", len(p3) == 1 and not p3[0].is_closed
        and near([tuple(v.dxf.location) for v in p3[0].vertices], [(0, 0, 0), (1000, 0, 1000), (1000, 1000, 2000), (0, 1000, 3000)]))
    dd = pl.get(12)
    chk("un dodécagone (12 côtés) reste une polyligne fermée : il n'est pas pris pour un cercle", dd is not None and dd.is_closed)
    ci = [e for e in msp if e.dxftype() == "CIRCLE"][0]
    chk("le cercle de Bézier de rayon 1,5 m en (5, 5) : un vrai CIRCLE, centre (5000, 5000, 0), rayon 1500 à 0,5 mm près", near(ci.dxf.center, (5000, 5000, 0), 1e-3) and abs(ci.dxf.radius - 1500) < 0.5 and near(ci.dxf.extrusion, (0, 0, 1)),
        (tuple(ci.dxf.center), ci.dxf.radius))
    ar = [e for e in msp if e.dxftype() == "ARC"][0]
    a_pts = np.array(made["arc_pts"]) * 1000.0
    s_, e_ = np.array(ar.start_point), np.array(ar.end_point)
    ends = (near(s_, a_pts[0], 1e-3) and near(e_, a_pts[-1], 1e-3)) or (near(s_, a_pts[-1], 1e-3) and near(e_, a_pts[0], 1e-3))
    nrm = np.array(ar.dxf.extrusion)
    cw = np.array(ar.ocs().to_wcs(ar.dxf.center))
    sweep = (ar.dxf.end_angle - ar.dxf.start_angle) % 360.0
    chk("l'arc incliné : un vrai ARC, rayon 2000, centre (0, 5000, 1000), 170° d'ouverture, mêmes extrémités, dans son plan (normale inclinée de 30°)",
        abs(ar.dxf.radius - 2000) < 1e-3 and near(cw, (0, 5000, 1000), 1e-3) and abs(sweep - 170) < 1e-4 and ends and abs(abs(nrm[2]) - math.cos(math.radians(30))) < 1e-6,
        (ar.dxf.radius, tuple(np.round(cw, 4)), round(sweep, 6), ends, tuple(np.round(nrm, 4))))
    mid = cw + 2000 * (math.cos(math.radians(ar.dxf.start_angle + sweep / 2)) * np.array(ar.ocs().ux) + math.sin(math.radians(ar.dxf.start_angle + sweep / 2)) * np.array(ar.ocs().uy))
    chk("... et il passe par le milieu de l'arc d'origine (pas par l'arc complémentaire)", float(np.linalg.norm(a_pts - mid, axis=1).min()) < 100.0, tuple(np.round(mid, 2)))
    nb = [e for e in msp if e.dxftype() == "POLYLINE" and len(list(e.vertices)) > 12][0]
    npts = np.array([tuple(v.dxf.location) for v in nb.vertices])
    chk("la NURBS : une polyligne 3D qui part de (6000, 0, 0) et arrive en (11000, 1000, 0)", nb.is_3d_polyline and near(npts[0], (6000, 0, 0), 1e-6) and near(npts[-1], (11000, 1000, 0), 1e-6) and len(npts) >= 16, len(npts))
    fa = [e for e in msp if e.dxftype() == "3DFACE"]
    quads = [f_ for f_ in fa if tuple(f_.dxf.vtx2) != tuple(f_.dxf.vtx3)]
    tris = [f_ for f_ in fa if tuple(f_.dxf.vtx2) == tuple(f_.dxf.vtx3)]
    area = 0.0
    for f_ in quads:
        a_, b_, c_, d_ = (np.array(f_.dxf.get(k)) for k in ("vtx0", "vtx1", "vtx2", "vtx3"))
        area += 0.5 * np.linalg.norm(np.cross(b_ - a_, c_ - a_)) + 0.5 * np.linalg.norm(np.cross(c_ - a_, d_ - a_))
    chk("la boîte de 1 m : 6 faces à 4 sommets, 6 m² (6 000 000 mm²), centrée en (10000, 5000, 500)", len(quads) == 6 and abs(area - 6e6) < 1.0
        and near(np.mean([np.array(f_.dxf.vtx0) for f_ in quads] + [np.array(f_.dxf.vtx2) for f_ in quads], axis=0), (10000, 5000, 500), 1e-6), (len(quads), area))
    vis_edges = 0
    for f_ in tris:
        inv = f_.dxf.get("invisible_edges", 0)
        vis_edges += sum(1 for k in range(3) if not inv & (1 << k))
    t_area = sum(0.5 * np.linalg.norm(np.cross(np.array(f_.dxf.vtx1) - np.array(f_.dxf.vtx0), np.array(f_.dxf.vtx2) - np.array(f_.dxf.vtx0))) for f_ in tris)
    chk("la face à 6 côtés : 4 triangles, même aire (2,598 m²), et seules ses 6 arêtes de contour sont visibles", len(tris) == 4 and abs(t_area - 1.5 * math.sqrt(3) * 1e6) < 1.0 and vis_edges == 6, (len(tris), t_area, vis_edges))
    tx = sorted([e for e in msp if e.dxftype() == "TEXT"], key=lambda e: e.dxf.insert[0])
    chk("le texte « Salon été » : hauteur 300, tourné de 30°, en (2000, 8000), accents compris",
        len(tx) == 2 and tx[0].plain_text() == "Salon été" and abs(tx[0].dxf.height - 300) < 1e-4 and abs(tx[0].dxf.rotation - 30) < 1e-6 and near(tx[0].dxf.insert, (2000, 8000, 0), 1e-6),
        tx and (tx[0].plain_text(), tx[0].dxf.height, tx[0].dxf.rotation))
    omega = m.dxf_escape_text("R = 10 Ω, été")
    chk("... un caractère absent de la page de code (oméga) est écrit \\U+03A9, comme le fait AutoCAD", omega == "R = 10 \\U+03A9, été", omega)
    chk("le titre centré : hauteur 500, alignement centré sur (6000, 8000)", tx[1].dxf.text == "PLAN" and abs(tx[1].dxf.height - 500) < 1e-4 and tx[1].dxf.halign == 1 and near(tx[1].dxf.align_point, (6000, 8000, 0), 1e-6))
    emin, emax = doc.header["$EXTMIN"], doc.header["$EXTMAX"]
    chk("étendue du dessin écrite dans l'en-tête", emin[0] <= -2000 and emax[0] >= 20000 and emax[2] >= 3000, (tuple(emin), tuple(emax)))
r = export(os.path.join(TMP, "metres.dxf"), units='M')
t_ = open(os.path.join(TMP, "metres.dxf"), encoding="cp1252").read()
h2, _l2, _b2, e2 = m.dxf_parse(open(os.path.join(TMP, "metres.dxf"), "rb").read())
chk("unités « mètres » : les mêmes nombres que dans la scène (ligne jusqu'en 2, 1), et le fichier dit ses unités", r == {'FINISHED'} and "\n11\n2\n 21\n1\n".replace(" ", "") in t_ and h2.get("$INSUNITS") == "6", h2.get("$INSUNITS"))
for ob in BC.view_layer.objects: ob.select_set(False)
made["box"].select_set(True); made["line"].select_set(True)
r = export(os.path.join(TMP, "selection.dxf"), units='MM', selected=True)
t_ = open(os.path.join(TMP, "selection.dxf"), encoding="cp1252").read()
chk("« Selection only » : seulement la boîte et la ligne (6 faces, 1 ligne)", r == {'FINISHED'} and t_.count("\n3DFACE\n") == 6 and t_.count("\nLINE\n") == 1 and t_.count("\nPOLYLINE\n") == 0 and "TEXT" not in t_.split("ENTITIES")[1],
    (t_.count("\n3DFACE\n"), t_.count("\nLINE\n")))
r = export(os.path.join(TMP, "sansfaces.dxf"), units='MM', faces=False, arcs=False)
t_ = open(os.path.join(TMP, "sansfaces.dxf"), encoding="cp1252").read()
chk("sans les faces ni les arcs : aucun 3DFACE, le cercle et l'arc deviennent des polylignes", r == {'FINISHED'} and "3DFACE" not in t_ and "\nCIRCLE\n" not in t_ and "\nARC\n" not in t_ and t_.count("\nPOLYLINE\n") == 6, t_.count("\nPOLYLINE\n"))

# ================= 3. Aller-retour par l'import de l'add-on =================
SEC = "aller-retour"
def measure():
    deps = BC.evaluated_depsgraph_get()
    tot, lo, hi, faces, texts = 0.0, None, None, 0, []
    for o in BC.view_layer.objects:
        if not o.visible_get():
            continue
        if o.type == 'CURVE':
            for sp in o.data.splines:
                pts, closed, _s = m.spline_points(sp, o.data.resolution_u)
                P = np.array([tuple(o.matrix_world @ p) for p in pts])
                Q = np.vstack((P, P[:1])) if closed else P
                tot += float(np.linalg.norm(np.diff(Q, axis=0), axis=1).sum())
                lo = P.min(0) if lo is None else np.minimum(lo, P.min(0)); hi = P.max(0) if hi is None else np.maximum(hi, P.max(0))
        elif o.type == 'MESH':
            faces += len(o.data.polygons)
            P = np.array([tuple(o.matrix_world @ v.co) for v in o.data.vertices])
            if len(P):
                lo = P.min(0) if lo is None else np.minimum(lo, P.min(0)); hi = P.max(0) if hi is None else np.maximum(hi, P.max(0))
            for e in o.data.edges:
                if not o.data.polygons:
                    tot += float(np.linalg.norm(P[e.vertices[0]] - P[e.vertices[1]]))
        elif o.type == 'FONT':
            texts.append(o.data.body)
    return tot, lo, hi, faces, sorted(texts)
src_len, src_lo, src_hi, src_faces, src_txt = measure()
clear()
us = BC.scene.unit_settings; us.system = 'METRIC'; us.scale_length = 1.0; us.length_unit = 'MILLIMETERS'
with contextlib.redirect_stdout(io.StringIO()):
    r = bpy.ops.dessin.import_cad('EXEC_DEFAULT', filepath=path, units='AUTO', mode='ENTITY')
BC.view_layer.update()
back_len, back_lo, back_hi, back_faces, back_txt = measure()
chk("réimporter le DXF (unités lues dans le fichier) : le dessin revient à sa taille, en mètres", r == {'FINISHED'} and near(back_lo, src_lo, 2e-3) and near(back_hi, src_hi, 2e-3), (tuple(np.round(back_lo, 4)), tuple(np.round(back_hi, 4))))
chk("... même longueur totale de courbes à 0,1 % près", abs(back_len - src_len) < 1e-3 * src_len, (round(src_len, 4), round(back_len, 4)))
chk("... les faces des solides et les deux textes reviennent", back_faces == 10 and back_txt == src_txt, (back_faces, back_txt))
cols = {c.name for c in bpy.data.collections}
chk("... le calque revient avec son nom DXF et sa couleur rouge", any("MURS_PORTEURS" in n for n in cols)
    and any(c.dessin_layer.use_color and near(c.dessin_layer.color, (1, 0, 0), 0.02) for c in bpy.data.collections if "MURS_PORTEURS" in c.name), sorted(cols))

# ================= 4. DWG : la passerelle vers le convertisseur =================
SEC = "DWG"
made = build()
chk("aucun convertisseur sur cette machine", m.cad_converter() is None, m.cad_converter())
dwg = os.path.join(TMP, "modele.dwg")
r = export(dwg, units='MM')
chk("Export DWG sans convertisseur : la commande s'arrête, dit d'installer ODA File Converter, n'écrit rien", (r == {'CANCELLED'} or "ODA File Converter" in str(r)) and not os.path.exists(dwg), r)
with contextlib.redirect_stdout(io.StringIO()):
    try:
        r = bpy.ops.dessin.import_cad('EXEC_DEFAULT', filepath=path.replace(".dxf", ".dwg"))
    except RuntimeError as ex:
        r = str(ex)
chk("Import d'un DWG sans convertisseur : même message, rien n'est importé", r == {'CANCELLED'} or "ODA File Converter" in str(r) or "not found" in str(r), r)
# faux convertisseur : note ses arguments et « convertit » en recopiant le fichier sous l'autre extension
fake = os.path.join(TMP, "ODAFileConverter")
log = os.path.join(TMP, "appels.json")
open(fake, "w").write(f'''#!{sys.executable}
import sys, os, json, shutil, fnmatch
a = sys.argv[1:]
calls = json.load(open({log!r})) if os.path.exists({log!r}) else []
calls.append({{"args": a, "files": sorted(os.listdir(a[0]))}})
json.dump(calls, open({log!r}, "w"))
if os.environ.get("WD_FAKE_FAIL"):
    sys.stderr.write("licence manquante\\n"); sys.exit(3)
for f in os.listdir(a[0]):
    if fnmatch.fnmatch(f.upper(), a[6].upper()):
        shutil.copyfile(os.path.join(a[0], f), os.path.join(a[1], os.path.splitext(f)[0] + "." + a[3].lower()))
''')
os.chmod(fake, os.stat(fake).st_mode | stat.S_IEXEC)
m.PREF_DEFAULTS["oda_path"] = fake
chk("chemin du convertisseur réglé dans les préférences : il est trouvé", m.cad_converter() == ('oda', fake), m.cad_converter())
r = export(dwg, units='MM')
calls = json.load(open(log))
c = calls[-1]
chk("Export DWG : le convertisseur est appelé comme ODA File Converter l'attend (dossier d'entrée, dossier de sortie, ACAD2018, DWG, 0, 1, *.DXF)",
    r == {'FINISHED'} and len(c["args"]) == 7 and os.path.isabs(c["args"][0]) and os.path.isabs(c["args"][1]) and c["args"][0] != c["args"][1]
    and c["args"][2:] == ["ACAD2018", "DWG", "0", "1", "*.DXF"] and c["files"] == ["modele.dxf"], (r, c["args"][2:], c["files"]))
chk("... le fichier .dwg est à l'endroit demandé, les dossiers temporaires sont supprimés", os.path.isfile(dwg) and os.path.getsize(dwg) > 2000 and not os.path.exists(c["args"][0]) and not os.path.exists(c["args"][1]), os.path.exists(dwg))
r = export(os.path.join(TMP, "v2013.dwg"), units='MM', version='ACAD2013')
chk("... version DWG choisie (2013) transmise au convertisseur", r == {'FINISHED'} and json.load(open(log))[-1]["args"][2] == "ACAD2013", json.load(open(log))[-1]["args"][2])
r = export(os.path.join(TMP, "parformat"), units='MM', kind='DWG')
chk("... sans extension, le format choisi (DWG) donne le nom du fichier", r == {'FINISHED'} and os.path.isfile(os.path.join(TMP, "parformat.dwg")))
clear()
us = BC.scene.unit_settings; us.system = 'METRIC'; us.scale_length = 1.0; us.length_unit = 'MILLIMETERS'
with contextlib.redirect_stdout(io.StringIO()):
    r = bpy.ops.dessin.import_cad('EXEC_DEFAULT', filepath=dwg, units='AUTO', mode='ENTITY')
BC.view_layer.update()
c = json.load(open(log))[-1]
d_len, d_lo, d_hi, d_faces, d_txt = measure()
chk("Import DWG : le convertisseur est appelé pour en faire un DXF (version, DXF, 0, 1, *.DWG), puis le dessin est lu",
    r == {'FINISHED'} and c["args"][3:] == ["DXF", "0", "1", "*.DWG"] and c["files"] == ["modele.dwg"] and d_faces == 10 and abs(d_len - src_len) < 1e-3 * src_len and d_txt == src_txt,
    (r, c["args"][2:], d_faces, round(d_len, 3)))
os.environ["WD_FAKE_FAIL"] = "1"
bad = os.path.join(TMP, "echec.dwg")
made = build()
r = export(bad, units='MM')
del os.environ["WD_FAKE_FAIL"]
left = [f for f in os.listdir(tempfile.gettempdir()) if f.startswith(("wd_cad_", "wd_dxf_"))]
chk("le convertisseur échoue : la commande s'arrête avec son message, aucun fichier ni dossier temporaire ne reste", (r == {'CANCELLED'} or "produced no file" in str(r)) and not os.path.exists(bad) and not left, (r, left))
app = os.path.join(TMP, "ODAFileConverter.app")
os.makedirs(os.path.join(app, "Contents", "MacOS"))
shutil.copy(fake, os.path.join(app, "Contents", "MacOS", "ODAFileConverter"))
m.PREF_DEFAULTS["oda_path"] = app
chk("sur Mac, on peut désigner l'application ODAFileConverter.app : le programme est trouvé dedans", m.cad_converter() == ('oda', os.path.join(app, "Contents", "MacOS", "ODAFileConverter")), m.cad_converter())
m.PREF_DEFAULTS["oda_path"] = fake
# feuilles d'une mise en page en DWG
model = BC.scene
Lp = m.layout_create(model, "Plan", 'A4', margin=10.0, title=True)
m.layout_open(BC, Lp)
m.detail_create(Lp, 150.0, 110.0, 120.0, 80.0, 'TOP', scale=100.0, fit=False)
sheet_dwg = os.path.join(TMP, "feuille.dwg")
with contextlib.redirect_stdout(io.StringIO()):
    r = bpy.ops.dessin.layout_export_dwg('EXEC_DEFAULT', filepath=sheet_dwg)
c = json.load(open(log))[-1]
chk("Export DWG d'une mise en page : la feuille part au convertisseur et le .dwg est écrit", r == {'FINISHED'} and os.path.isfile(sheet_dwg) and c["args"][2:] == ["ACAD2018", "DWG", "0", "1", "*.DXF"], (r, c["args"][2:]))
m.PREF_DEFAULTS["oda_path"] = ""
with contextlib.redirect_stdout(io.StringIO()):
    try:
        r = bpy.ops.dessin.layout_export_dwg('EXEC_DEFAULT', filepath=os.path.join(TMP, "feuille2.dwg"))
    except RuntimeError as ex:
        r = str(ex)
chk("... sans convertisseur : message, rien n'est écrit", (r == {'CANCELLED'} or "ODA File Converter" in str(r)) and not os.path.exists(os.path.join(TMP, "feuille2.dwg")), r)
m.layout_close(BC)
first = lambda t: (m.cmd_suggest(t) or [{"label": None}])[0]["label"]
chk("ligne de commande : importdwg / dxfin, exportmodel / saveasdwg", (first("importdwg"), first("dxfin"), first("exportmodel"), first("saveasdwg")) == ("Import DXF / DWG",) * 2 + ("Export Model (DXF / DWG)",) * 2,
    (first("importdwg"), first("dxfin"), first("exportmodel"), first("saveasdwg")))
shutil.rmtree(TMP, ignore_errors=True)
summary()
