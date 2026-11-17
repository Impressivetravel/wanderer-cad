# Layout, suite : cartouche personnalisable (modèles, cases, champs automatiques, logo), images sur la feuille et dans
# l'export, textes à champs, titre de dessin numéroté, échelle graphique, vue de détail agrandie.
# Tout est mesuré : rectangles en millimètres, textes écrits, contenu des fichiers PDF / SVG / DXF.
import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
exec(open(_os.path.join(_HERE,'prec_lib.py')).read())
import base64, io as _io, os, re, shutil, struct, subprocess, tempfile, zlib
from mathutils import Vector
le = m.le
BC = bpy.context
TMP = tempfile.mkdtemp(prefix="wd_layout2_")


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


def box(name, sx, sy, sz, loc):
    me = bpy.data.meshes.new(name); bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=bm.verts); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); o.location = loc
    BC.scene.collection.objects.link(o)
    return o


def sheet_texts(L):
    return [o.data.body for o in L.objects if o.type == 'FONT' and o.get("wd_layout_gen")]


def kids(det, role):
    return [c for c in det.children if c.get("wd_gen") == role]


def r4(t):
    return tuple(round(float(v), 4) for v in t)


def write_png(path, w, h, rgba):
    """Image d'essai : rgba(x, y) -> (r, v, b, a) en 0-255, rangée du haut d'abord."""
    rows = bytearray()
    for y in range(h):
        rows.append(0)
        for x in range(w):
            rows += bytes(rgba(x, y))
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(bytes(rows), 9)) + chunk(b"IEND", b""))


LOGO = os.path.join(TMP, "logo.png")          # 60 x 30 px : moitié gauche rouge opaque, moitié droite transparente
write_png(LOGO, 60, 30, lambda x, y: (220, 20, 20, 255) if x < 30 else (0, 0, 0, 0))

# ---------------------------------------------------------------- A. cartouche : modèles et géométrie
SEC = "cartouche"
model = reset(); box("A", 2.0, 1.0, 0.5, (0, 0, 0.25))
L = m.layout_create(model, "Plan", 'A3', 'LANDSCAPE', 10.0, True)
D = L.dessin_layout
rec(SEC, "nouvelle mise en page : les 8 cases du cartouche d'origine sont là, prêtes à être modifiées", len(D.title_cells) == 8 and D.title_pos == 'BR' and D.title_w == 170.0, len(D.title_cells))
rc, placed, hs = m.title_layout(D)
rec(SEC, "modèle Classic : bloc de 170 x 34 mm en bas à droite du cadre, rangées de 13, 12 et 9 mm", r4(rc) == (240.0, 10.0, 410.0, 44.0) and near(hs, (13, 12, 9)), (r4(rc), hs))
c0 = placed[0]
rec(SEC, "... la case PROJECT occupe 136 mm de large sur la rangée du haut", c0[0]["label"] == "PROJECT" and r4(c0[1:]) == (240.0, 31.0, 376.0, 44.0), r4(c0[1:]))
rec(SEC, "zone libre pour les fenêtres : au-dessus du cartouche", r4(m.usable_rect(D)) == (10.0, 44.0, 410.0, 287.0), r4(m.usable_rect(D)))
BC.window.scene = L
r = bpy.ops.dessin.title_preset(preset='STRIP')
rc, placed, hs = m.title_layout(D)
rec(SEC, "modèle Bottom strip : bandeau de 16 mm sur toute la largeur du cadre, 8 cases dont le logo", r == {'FINISHED'} and r4(rc) == (10.0, 10.0, 410.0, 26.0) and len(placed) == 8 and placed[0][0]["kind"] == 'LOGO', (r4(rc), len(placed)))
rec(SEC, "... les cases se partagent la largeur selon leur poids (348 au total) : le logo fait 28 / 348 de 400 mm", near(placed[0][3] - placed[0][1], 400.0 * 28.0 / 348.0), placed[0][3] - placed[0][1])
bpy.ops.dessin.title_preset(preset='SIDE')
rc, placed, hs = m.title_layout(D)
rec(SEC, "modèle Side strip : bandeau de 62 mm sur toute la hauteur, à droite ; la rangée NOTES prend la place qui reste",
    r4(rc) == (348.0, 10.0, 410.0, 287.0) and near(sum(hs), 277.0) and near(hs[1], 277.0 - (30 + 18 + 16 + 10 + 10 + 14)), (r4(rc), hs))
rec(SEC, "... zone libre pour les fenêtres : à gauche du bandeau", r4(m.usable_rect(D)) == (10.0, 10.0, 348.0, 287.0), r4(m.usable_rect(D)))
bpy.ops.dessin.title_preset(preset='COMPACT')
rc, placed, hs = m.title_layout(D)
rec(SEC, "modèle Compact : une rangée de 120 x 12 mm en bas à droite", r4(rc) == (290.0, 10.0, 410.0, 22.0) and len(placed) == 3, r4(rc))
D.title_pos = 'TL'; D.title_w = 100.0
rc, placed, hs = m.title_layout(D)
rec(SEC, "position Top left, largeur 100 mm : le bloc passe en haut à gauche", r4(rc) == (10.0, 275.0, 110.0, 287.0), r4(rc))
rec(SEC, "... zone libre : sous le bloc", r4(m.usable_rect(D)) == (10.0, 10.0, 410.0, 275.0), r4(m.usable_rect(D)))
lines = [o for o in L.objects if o.get("wd_layout_gen") in ('frame', 'title') and o.type == 'CURVE' and o.name.startswith("Title")]
P = np.array([p.co[:2] for o in lines for sp in o.data.splines for p in sp.points])
rec(SEC, "... ses traits sont redessinés à cet endroit (changer un réglage refait la feuille)", len(P) and near((P[:, 0].min(), P[:, 1].min(), P[:, 0].max(), P[:, 1].max()), (10, 275, 110, 287)), None if not len(P) else (P.min(0).tolist(), P.max(0).tolist()))
D.title_pos = 'BR'
bpy.ops.dessin.title_preset(preset='CLASSIC')

# ---------------------------------------------------------------- B. champs automatiques
SEC = "champs"
vals = {"scale": "1:50", "sheet": "02", "sheets": "05"}
rec(SEC, "<Scale>, <SHEET> / <sheets> : remplacés quelle que soit la casse ; un nom inconnu reste tel quel",
    m.field_resolve("Ech. <Scale> - <SHEET> / <sheets> <Truc>", vals) == "Ech. 1:50 - 02 / 05 <Truc>", m.field_resolve("Ech. <Scale> - <SHEET> / <sheets> <Truc>", vals))
rec(SEC, "has_field : « <Scale> » oui, « <b> » et « a < b » non", m.has_field("x <Scale>") and not m.has_field("<b>") and not m.has_field("a < b > c"))
D.t_project = "Villa"; D.t_title = "Plans"; D.t_author = "TO"; D.t_revision = "B"
tx = sheet_texts(L)
rec(SEC, "cartouche : les champs sont remplis (Villa, Plans, TO, B, 01, A3)", all(t in tx for t in ("Villa", "Plans", "TO", "B", "01", "A3")), tx)
i = next(k for k, c in enumerate(D.title_cells) if c.label == "SHEET")
D.title_cells[i].text = "<Sheet> / <Sheets>"
rec(SEC, "case SHEET réglée sur « <Sheet> / <Sheets> » : « 01 / 01 » (une seule planche)", "01 / 01" in sheet_texts(L), sheet_texts(L))
L2 = m.layout_create(model, "Coupes", 'A3')
D2 = L2.dessin_layout
rec(SEC, "deuxième mise en page : elle reprend le cartouche de la première (cases, projet, auteur), numéro 02",
    len(D2.title_cells) == 8 and D2.title_cells[i].text == "<Sheet> / <Sheets>" and D2.t_project == "Villa" and D2.t_author == "TO" and D2.t_number == "02" and "02 / 02" in sheet_texts(L2), (D2.t_project, D2.t_number, sheet_texts(L2)))
rec(SEC, "... son titre et son indice lui sont propres", D2.t_title == L2.name and D2.t_revision == "")
m.title_refresh(L)
rec(SEC, "la première planche passe d'elle-même à « 01 / 02 » (nombre de planches)", "01 / 02" in sheet_texts(L) and "01 / 01" not in sheet_texts(L), sheet_texts(L))
det = m.detail_create(L, 150, 150, 120, 80, 'TOP', scale=20.0, fit=False)
rec(SEC, "champ <Scale> : l'échelle de la fenêtre (1:20)", "1:20" in sheet_texts(L), sheet_texts(L))
det.dessin_detail.scale = 50.0
rec(SEC, "... il suit un changement d'échelle (1:50)", "1:50" in sheet_texts(L) and "1:20" not in sheet_texts(L), sheet_texts(L))

# ---------------------------------------------------------------- C. cases : ajouter, retirer, déplacer, insérer un champ
SEC = "cases"
D.title_cell_index = 0
r = bpy.ops.dessin.title_cell_add()
rec(SEC, "Add Cell : une case de plus, juste après la case choisie, dans la même rangée", r == {'FINISHED'} and len(D.title_cells) == 9 and D.title_cell_index == 1 and not D.title_cells[1].new_row and D.title_cells[1].label == "LABEL", len(D.title_cells))
D.title_cells[1].label = "CLIENT"; D.title_cells[1].text = "M. Dupont"; D.title_cells[1].width = 60.0
rows = m.title_rows(m.title_cells(D))
rec(SEC, "... la rangée du haut a 3 cases (PROJECT, CLIENT, SHEET) ; le texte tapé est écrit sur la feuille", [c["label"] for c in rows[0]] == ["PROJECT", "CLIENT", "SHEET"] and "M. Dupont" in sheet_texts(L) and "CLIENT" in sheet_texts(L), [c["label"] for c in rows[0]])
r = bpy.ops.dessin.title_cell_field(field="Today")
rec(SEC, "Insert Field : « <Today> » ajouté au texte de la case, puis remplacé par la date du jour", D.title_cells[1].text == "M. Dupont <Today>" and any(t.startswith("M. Dupont 20") for t in sheet_texts(L)), D.title_cells[1].text)
r = bpy.ops.dessin.title_cell_move(up=True)
rec(SEC, "Move Cell (vers le haut) : CLIENT passe avant PROJECT et prend la tête de la rangée", [c.label for c in D.title_cells][:3] == ["CLIENT", "PROJECT", "SHEET"] and D.title_cells[0].new_row and not D.title_cells[1].new_row and D.title_cell_index == 0,
    [(c.label, c.new_row) for c in D.title_cells][:3])
r = bpy.ops.dessin.title_cell_remove()
rec(SEC, "Remove Cell : CLIENT retirée, PROJECT reprend la tête de la rangée ; 8 cases", len(D.title_cells) == 8 and D.title_cells[0].label == "PROJECT" and D.title_cells[0].new_row and "CLIENT" not in sheet_texts(L),
    [(c.label, c.new_row) for c in D.title_cells][:2])
D.title_cells[0].height = 20.0
rc, placed, hs = m.title_layout(D)
rec(SEC, "hauteur de rangée 20 mm sur PROJECT : la rangée du haut grandit, le bloc fait 41 mm", near(hs, (20, 12, 9)) and r4(rc) == (240.0, 10.0, 410.0, 51.0), (hs, r4(rc)))
D.title_cells[0].height = 13.0
bpy.ops.dessin.title_preset(preset='STRIP')
D2.t_title = "Coupes AA"
r = bpy.ops.dessin.title_copy_all()
rec(SEC, "Copy to All Layouts : la deuxième planche reçoit le bandeau ; elle garde son titre et son numéro",
    r == {'FINISHED'} and D2.title_pos == 'BOTTOM' and len(D2.title_cells) == 8 and D2.t_title == "Coupes AA" and D2.t_number == "02" and "Coupes AA" in sheet_texts(L2), (D2.title_pos, sheet_texts(L2)))

# ---------------------------------------------------------------- D. logo du cartouche
SEC = "logo"
hint = [o for o in L.objects if o.get("wd_layout_gen") == 'hint']
rec(SEC, "sans fichier : la case du logo porte un rappel gris « Logo »", len(hint) == 1 and hint[0].data.body == "Logo", [o.name for o in hint])
ents = m.layout_entities(L)
rec(SEC, "... qui ne s'imprime pas (aucune image, et le mot Logo n'est pas dans les aplats de texte exportés)", not any(e[0] == 'I' for e in ents))
n_text = sum(1 for e in ents if e[0] == 'F')
D.t_logo = LOGO
logo = [o for o in L.objects if o.get("wd_layout_gen") == 'logo']
rc, placed, hs = m.title_layout(D)
cell = placed[0]
ok = len(logo) == 1 and logo[0].type == 'EMPTY' and logo[0].empty_display_type == 'IMAGE' and logo[0].data is not None
cn = m.image_corners(logo[0]) if ok else None
rec(SEC, "avec un fichier : une image 2:1 ajustée dans la case (marge 1,5 mm), centrée, proportions gardées",
    ok and near(cn[1][0] / cn[2][1], 2.0) and cn[0][0] >= cell[1] + 1.5 - 1e-6 and cn[0][0] + cn[1][0] <= cell[3] - 1.5 + 1e-6
    and cn[0][1] >= cell[2] + 1.5 - 1e-6 and cn[0][1] + cn[2][1] <= cell[4] - 1.5 + 1e-6
    and near(cn[0][0] + cn[1][0] / 2.0, (cell[1] + cell[3]) / 2.0) and near(cn[2][1], 13.0, 1e-4), cn)
rec(SEC, "... le rappel « Logo » a disparu, l'image n'est pas sélectionnable (elle fait partie de la feuille)", not [o for o in L.objects if o.get("wd_layout_gen") == 'hint'] and logo[0].hide_select)
D.t_logo = os.path.join(TMP, "absent.png")
rec(SEC, "fichier introuvable : pas d'erreur, le rappel revient", len([o for o in L.objects if o.get("wd_layout_gen") == 'hint']) == 1 and not [o for o in L.objects if o.get("wd_layout_gen") == 'logo'])
D.t_logo = LOGO

# ---------------------------------------------------------------- E. image posée sur la feuille, export
SEC = "images"
m.layout_open(BC, L)
r = bpy.ops.dessin.sheet_image(filepath=LOGO, width=60.0, x=100.0, y=200.0)
img_o = BC.view_layer.objects.active
cn = m.image_corners(img_o)
rec(SEC, "Insert Image (largeur 60 mm) : image de 60 x 30 mm centrée en (100, 200), sélectionnée, dans le calque Annotations",
    r == {'FINISHED'} and m.is_sheet_image(img_o) and near(cn[0], (70, 185)) and near(cn[1], (60, 0)) and near(cn[2], (0, 30)) and img_o.select_get()
    and img_o.users_collection[0].get("wd_layout_col") == 'annot', cn)
n = m.layout_ink(L)
rec(SEC, "elle n'est pas « encrée » en noir comme un trait blanc", tuple(img_o.color[:3]) == (1.0, 1.0, 1.0))
px = m.image_pixels(img_o.data)
rec(SEC, "pixels lus pour l'export : 60 x 30, rouge à gauche, transparent à droite (rangée du haut d'abord)",
    px[0] == 60 and px[1] == 30 and tuple(px[2][:3]) == (220, 20, 20) and px[3] is not None and px[3][0] == 255 and px[3][59] == 0, (px[0], px[1], tuple(px[2][:3])))
big = os.path.join(TMP, "big.png")
write_png(big, 400, 100, lambda x, y: (0, 0, 255, 255))
bimg = m.image_load(big)
pb = m.image_pixels(bimg, max_px=100)
rec(SEC, "grande image (400 x 100) limitée à 100 px : réduite à 100 x 25, couleur gardée, sans transparence",
    pb[:2] == (100, 25) and tuple(pb[2][:3]) == (0, 0, 255) and pb[3] is None, pb[:2])
ents = m.layout_entities(L)
im = [e for e in ents if e[0] == 'I']
rec(SEC, "entités de la page : 2 images (logo, image posée), placées avant les traits", len(im) == 2 and ents[0][0] == 'I' and ents[1][0] == 'I' and all(e[-1] == "Images" for e in im), [e[0] for e in ents[:4]])
e_img = next(e for e in im if near(e[4], (60, 0)))
rec(SEC, "... l'image posée : coin (70, 185), côtés (60, 0) et (0, 30) mm", near(e_img[3], (70, 185)) and near(e_img[5], (0, 30)), e_img[3:6])
img_o.scale = (2.0, 2.0, 1.0); BC.view_layer.update()
cn2 = m.image_corners(img_o)
rec(SEC, "image agrandie 2 fois (Gumball) : 120 x 60 mm, toujours centrée en (100, 200)", near(cn2[1], (120, 0)) and near(cn2[2], (0, 60)) and near(cn2[0], (40, 170)), cn2)
img_o.scale = (1.0, 1.0, 1.0); BC.view_layer.update()
pdf = os.path.join(TMP, "a.pdf")
pg = m.layout_page(L)
le.write_pdf(pdf, [pg, m.layout_page(L2)], "t")
raw = open(pdf, "rb").read()
rec(SEC, "PDF : une seule copie de l'image pour ses deux emplois sur la page, avec son masque de transparence",
    raw.count(b"/Subtype /Image") == 2 and raw.count(b"/SMask") == 1 and raw.count(b"/DeviceGray") == 1 and b"/XObject << /Im1" in raw, (raw.count(b"/Subtype /Image"), raw.count(b"/SMask")))
streams = [zlib.decompress(s_) for s_ in re.findall(rb"stream\n(.*?)\nendstream", raw, re.S) if s_[:1] == b"x"]
page1 = next(s_ for s_ in streams if b" cm /Im1 Do" in s_)
rec(SEC, "... placée par « 60 0 0 30 70 185 cm /Im1 Do » (mm) dans le flux de la page", b"q 60.0000 0.0000 0.0000 30.0000 70.0000 185.0000 cm /Im1 Do Q" in page1)
if shutil.which("qpdf"):
    out = subprocess.run(["qpdf", "--check", pdf], capture_output=True, text=True)
    rec(SEC, "... qpdf --check : aucune erreur de syntaxe", out.returncode == 0, (out.stdout + out.stderr).strip().splitlines()[-1:])
if shutil.which("pdftoppm"):
    subprocess.run(["pdftoppm", "-r", "25.4", "-f", "1", "-l", "1", "-png", pdf, os.path.join(TMP, "pg")], check=True)     # 1 px par mm
    png = next(os.path.join(TMP, f) for f in sorted(os.listdir(TMP)) if f.startswith("pg") and f.endswith(".png"))
    try:
        from PIL import Image as _PI
        im_ = _PI.open(png).convert("RGB")
        H_ = im_.size[1]
        left = im_.getpixel((85, H_ - 200)); right = im_.getpixel((115, H_ - 200))
        rec(SEC, "... rendu du PDF : rouge dans la moitié gauche de l'image (85, 200), papier blanc dans la moitié transparente (115, 200)",
            left[0] > 180 and left[1] < 80 and min(right) > 235, (left, right))
    except ImportError:
        pass
svg = os.path.join(TMP, "a.svg")
le.write_svg(svg, pg)
txt = open(svg, encoding="utf-8").read()
mi = re.findall(r'<image class="Images" width="1" height="1" preserveAspectRatio="none" transform="matrix\(([^)]*)\)" href="data:image/png;base64,([^"]*)"', txt)
rec(SEC, "SVG : 2 images intégrées (PNG en base64), avant les traits", len(mi) == 2 and txt.index("<image") < txt.index("<path"), len(mi))
mat = next(tuple(float(v) for v in a.split()) for a, _b in mi if abs(float(a.split()[0]) - 60.0) < 1e-6)
rec(SEC, "... matrice de l'image posée : (60, 0, 0, -30, 70, 215) — son coin haut gauche, axe y retourné", near(mat, (60, 0, 0, -30, 70, 215)), mat)
data = base64.b64decode(next(b for a, b in mi if abs(float(a.split()[0]) - 60.0) < 1e-6))
rec(SEC, "... le PNG intégré est valide : 60 x 30, RVBA", data[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", data[16:24]) == (60, 30) and data[25] == 6, struct.unpack(">II", data[16:24]))
rgb = bytes([10, 20, 30, 40, 50, 60])
pn = le.png_bytes(2, 1, rgb)
rec(SEC, "png_bytes : en-tête, taille et type de couleur (2 = RVB sans alpha)", pn[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", pn[16:24]) == (2, 1) and pn[25] == 2)
try:
    from PIL import Image as _PI
    back = _PI.open(_io.BytesIO(pn)).convert("RGB")
    rec(SEC, "... relu par un autre programme : mêmes pixels", back.getpixel((0, 0)) == (10, 20, 30) and back.getpixel((1, 0)) == (40, 50, 60), back.getpixel((0, 0)))
except ImportError:
    pass
dxf = os.path.join(TMP, "a.dxf")
le.write_dxf(dxf, [pg])
dt = open(dxf).read()
rec(SEC, "DXF : pas d'image en R12, son contour est tracé sur le calque IMAGES", "\n2\nIMAGES\n" in dt and "\n8\nIMAGES\n" in dt)
rec(SEC, "image_quad : les 4 coins de l'image posée", near(le.image_quad(e_img), [(70, 185), (130, 185), (130, 215), (70, 215)]), le.image_quad(e_img))
# sélection au clic (vue de dessus simulée : 10 px par mm, centre de l'écran = origine)
img_o.location = (20.0, 10.0, m.Z_IMAGE); BC.view_layer.update()
hit = m.sheet_image_at(BC, region, rv3d, *scr(25.0, 12.0))
miss = m.sheet_image_at(BC, region, rv3d, *scr(-20.0, -20.0))
rec(SEC, "clic dans l'image : elle est prise ; clic à côté : rien", hit == img_o and miss is None, (hit and hit.name, miss))
img_o.hide_select = True
rec(SEC, "image verrouillée (non sélectionnable) : le clic la traverse", m.sheet_image_at(BC, region, rv3d, *scr(25.0, 12.0)) is None)
img_o.hide_select = False
img_o.location = (100.0, 200.0, m.Z_IMAGE); BC.view_layer.update()
# duplication de la mise en page : l'image est copiée sans dupliquer le fichier image
n_img = len(bpy.data.images)
r = bpy.ops.dessin.layout_duplicate(name=L.name)
L3 = BC.window.scene
im3 = [o for o in L3.objects if m.is_sheet_image(o) and not o.get("wd_layout_gen")]
rec(SEC, "Duplicate Layout : l'image posée est copiée (même fichier image, pas de doublon), le bandeau et le logo aussi",
    r == {'FINISHED'} and len(im3) == 1 and im3[0].data == img_o.data and len(bpy.data.images) == n_img and L3.dessin_layout.title_pos == 'BOTTOM'
    and len([o for o in L3.objects if o.get("wd_layout_gen") == 'logo']) == 1, (len(im3), len(bpy.data.images), n_img))
m.layout_open(BC, L)

# ---------------------------------------------------------------- F. textes à champs, flèche du nord
SEC = "annotations"
fc = bpy.data.curves.new("Text", 'FONT'); fc.body = "Echelle <Scale> - planche <Sheet>"
t1 = bpy.data.objects.new("Text", fc); t1["dessin_text"] = True
m.layout_collection(L, 'annot').objects.link(t1)
ch = m.fields_refresh(L)
rec(SEC, "texte tapé avec des champs : il affiche leur valeur, le texte tapé est gardé comme gabarit", ch and t1.data.body == "Echelle 1:50 - planche 01" and t1.get("wd_field") == "Echelle <Scale> - planche <Sheet>", t1.data.body)
rec(SEC, "rien à refaire tant que rien ne change", m.fields_refresh(L) is False)
det.dessin_detail.scale = 100.0
rec(SEC, "l'échelle de la fenêtre change : le texte suit (1:100)", t1.data.body == "Echelle 1:100 - planche 01", t1.data.body)
t1.data.body = "Texte libre"
m.fields_refresh(L)
rec(SEC, "texte retouché à la main, sans champ : il redevient un texte ordinaire", t1.data.body == "Texte libre" and "wd_field" not in t1.keys())
t1.data.body = "Format <Format>"
m.fields_refresh(L)
rec(SEC, "texte retouché avec un champ : nouveau gabarit, « Format A3 »", t1.data.body == "Format A3" and t1.get("wd_field") == "Format <Format>", t1.data.body)
r = bpy.ops.dessin.sheet_field(field='SheetOf')
f1 = BC.view_layer.objects.active
rec(SEC, "Insert Field « <Sheet> / <Sheets> » : un texte sélectionné qui affiche « 01 / 03 », à la hauteur de texte de la feuille (2,5 mm)",
    r == {'FINISHED'} and f1.type == 'FONT' and f1.data.body == "01 / 03" and near(f1.data.size, 2.5) and f1.select_get() and f1.get("dessin_text"), f1.data.body)
r = bpy.ops.dessin.sheet_north(size=14.0)
na = BC.view_layer.objects.active
Pn = np.array([p.co[:2] for sp in na.data.splines for p in sp.points])
rec(SEC, "North Arrow : une courbe (cercle de 14 mm, pointe, lettre N) posée sur la feuille, sélectionnée",
    r == {'FINISHED'} and na.type == 'CURVE' and len(na.data.splines) == 4 and near(Pn[:, 0].min(), -7.0, 1e-3) and near(Pn[:, 0].max(), 7.0, 1e-3)
    and Pn[:, 1].max() > 12.0 and na.users_collection[0].get("wd_layout_col") == 'annot', (len(na.data.splines), Pn.min(0).tolist(), Pn.max(0).tolist()))
ents = m.layout_entities(L)
rec(SEC, "... elle s'imprime avec les annotations de la feuille", any(e[0] == 'L' and e[-1] == "Sheet" for e in ents))

# ---------------------------------------------------------------- G. titre de dessin numéroté, échelle graphique
SEC = "fenêtres"
model = reset(); box("A", 8.0, 5.0, 3.0, (0, 0, 1.5))
L = m.layout_create(model, "Plan", 'A3')
D = L.dessin_layout
m.layout_open(BC, L)
made = m.layout_initial_details(L, 'FOUR')
top = next(o for o in made if o.dessin_detail.view == 'TOP')
front = next(o for o in made if o.dessin_detail.view == 'FRONT')
lab = [c.data.body for c in kids(top, 'label')]
rec(SEC, "style « Name and scale » (par défaut) : une étiquette « Top   1:100 »", lab == ["Top   " + le.fmt_scale(top.dessin_detail.scale)], lab)
D.label_style = 'TITLE'
labs = {o.dessin_detail.view: sorted(c.data.body for c in kids(o, 'label')) for o in made}
sc_t = "Scale " + le.fmt_scale(top.dessin_detail.scale)
rec(SEC, "style « Drawing title » : numéro, nom et échelle sur chaque fenêtre, numérotées 1 à 4 dans l'ordre de création",
    labs['TOP'] == sorted(["1", "Top", sc_t]) and [labs[o.dessin_detail.view][0] for o in made] == ["1", "2", "3", "4"], labs)
mk = kids(top, 'mark')
P = np.array([p.co[:2] for sp in mk[0].data.splines for p in sp.points]) if mk else np.zeros((0, 2))
s_ = D.label_size
rec(SEC, "... un cercle de 2,5 fois la hauteur d'étiquette et un trait, sous la fenêtre à gauche", len(mk) == 1 and len(mk[0].data.splines) == 2 and near(P[:, 0].min(), -top.dessin_detail.width / 2.0, 1e-3)
    and P[:, 1].max() < -top.dessin_detail.height / 2.0, None if not len(P) else (P.min(0).tolist(), P.max(0).tolist()))
top.dessin_detail.number = "A1"
rec(SEC, "numéro tapé « A1 » : il remplace le numéro automatique", "A1" in [c.data.body for c in kids(top, 'label')])
top.dessin_detail.number = ""
rec(SEC, "nice_step : 0,6 -> 0,5 ; 12 -> 10 ; 3 -> 2 ou 5 ; 150 -> 200 ou 100", m.nice_step(0.6) == 0.5 and m.nice_step(12) == 10 and m.nice_step(3) in (2, 5) and m.nice_step(150) in (100, 200), (m.nice_step(0.6), m.nice_step(12), m.nice_step(3), m.nice_step(150)))
with m.quiet():
    top.dessin_detail.scale = 100.0
sp_ = m.scalebar_spec(top.dessin_detail, model, 100.0)
rec(SEC, "échelle graphique au 1:100 (modèle en mètres) : 4 divisions de 1 m, soit 10 mm chacune sur le papier", sp_ is not None and near(sp_[0], 10.0) and sp_[1] == 1.0 and sp_[2] == 4 and sp_[3] == "m", sp_)
with m.quiet():
    top.dessin_detail.scale = 50.0
sp_ = m.scalebar_spec(top.dessin_detail, model, 100.0)
rec(SEC, "... au 1:50 : divisions de 0,5 m (10 mm)", sp_ is not None and near(sp_[0], 10.0) and sp_[1] == 0.5, sp_)
rec(SEC, "... trop étroite pour la fenêtre (25 mm) : 2 divisions seulement", m.scalebar_spec(top.dessin_detail, model, 25.0)[2] == 2, m.scalebar_spec(top.dessin_detail, model, 25.0))
with m.quiet():
    top.dessin_detail.scale = 100.0
top.dessin_detail.show_scalebar = True
labs_t = [c.data.body for c in kids(top, 'label')]
mk = kids(top, 'mark')
P = np.array([p.co[:2] for sp in mk[0].data.splines for p in sp.points])
w2 = top.dessin_detail.width / 2.0
rec(SEC, "Scale bar coché : graduations 0, 1, 2, 3 et « 4 m » ; la barre fait 40 mm et finit au bord droit de la fenêtre",
    all(t in labs_t for t in ("0", "1", "2", "3", "4 m")) and near(P[:, 0].max(), w2, 1e-3) and any(near(x, w2 - 40.0, 1e-3) for x in P[:, 0]), labs_t)
ents = m.layout_entities(L)
ann = [e for e in ents if e[0] == 'L' and e[-1] == "Annotations"]
rec(SEC, "titre de dessin et échelle graphique sont imprimés (traits d'annotation, épaisseur des annotations)", len(ann) >= 4 and all(near(e[2], D.lw_annot) for e in ann), len(ann))
m.layout_sync(L)
n0 = len(L.objects)
bpy.data.objects.remove(top)
ch = m.layout_sync(L)
labs = [sorted(c.data.body for c in kids(o, 'label'))[0] for o in m.details(L)]
rec(SEC, "fenêtre 1 supprimée : ses traits partent, les autres sont renumérotées 1, 2, 3", ch and labs == ["1", "2", "3"], labs)

# ---------------------------------------------------------------- H. vue de détail agrandie
SEC = "vue de détail"
rec(SEC, "échelle d'une vue de détail : 1:100 -> 1:50, 1:50 -> 1:25, 1:20 -> 1:10, 1:1 -> 2:1, 1:30 -> 1:10",
    [m.callout_scale(v) for v in (100.0, 50.0, 20.0, 1.0, 30.0)] == [50.0, 25.0, 10.0, 0.5, 10.0], [m.callout_scale(v) for v in (100.0, 50.0, 20.0, 1.0, 30.0)])
model = reset(); box("A", 8.0, 5.0, 3.0, (0, 0, 1.5))
L = m.layout_create(model, "Plan", 'CUSTOM', custom=(100.0, 100.0), margin=2.0, title=False)
m.layout_open(BC, L)
par = m.detail_create(L, 0.0, 10.0, 100.0, 70.0, 'TOP', scale=100.0, fit=False)
with m.quiet():
    par.dessin_detail.center = (0.0, 0.0, 0.0)
m.detail_rebuild(par, force=True)
m.layout_sync(L)
# zone de 14 x 10 mm autour du coin bas droit du modèle (4 m, -2,5 m) -> (40, -15) sur la feuille
new, r_, o_ = run("detail_callout", [C(33.0, -20.0), C(47.0, -10.0), C(10.0, -30.0)])
ch_ = next((o for o in new if m.is_detail(o)), None)
cd = ch_.dessin_detail if ch_ is not None else None
rec(SEC, "Detail View (deux coins de la zone, puis la position) : une fenêtre au 1:50 de 28 x 20 mm, posée en (10, -30)",
    ch_ is not None and cd.scale == 50.0 and near((cd.width, cd.height), (28.0, 20.0)) and near(ch_.location[:2], (10.0, -30.0)), cd and (cd.scale, cd.width, cd.height, tuple(ch_.location)))
rec(SEC, "... centrée sur le point du modèle visé : (4 m, -2,5 m)", cd is not None and near(cd.center[:2], (4.0, -2.5), 1e-4), cd and tuple(cd.center))
rec(SEC, "... même vue que l'original, lettre A, étiquette « Detail A   1:50 », sélectionnée",
    cd is not None and cd.view == 'TOP' and cd.callout_tag == "A" and cd.callout_of == par.get("wd_id") and [c.data.body for c in kids(ch_, 'label')] == ["Detail A   1:50"] and ch_.select_get(),
    cd and (cd.callout_tag, [c.data.body for c in kids(ch_, 'label')]))
vis = kids(ch_, 'vis')
Pv = np.array([p.co[:2] for o in vis for sp in o.data.splines for p in sp.points]) if vis else np.zeros((0, 2))
rec(SEC, "... elle montre le coin du modèle : ses deux arêtes se croisent au centre de la fenêtre", len(Pv) and any(near(p, (0, 0), 1e-3) for p in Pv), None if not len(Pv) else Pv.round(2).tolist()[:6])
mk = kids(par, 'mark')
Pm = np.array([p.co[:2] for sp in mk[0].data.splines for p in sp.points]) if mk else np.zeros((0, 2))
rec(SEC, "sur la fenêtre d'origine : un repère rectangulaire de 14 x 10 mm autour de la zone, avec la lettre A",
    len(mk) == 1 and near((Pm[:, 0].min(), Pm[:, 1].min(), Pm[:, 0].max(), Pm[:, 1].max()), (33.0, -30.0, 47.0, -20.0), 1e-4) and "A" in [c.data.body for c in kids(par, 'label')],
    None if not len(Pm) else (Pm.min(0).tolist(), Pm.max(0).tolist()))
m.layout_sync(L)
cd.center = (3.0, -2.5, 0.0)                      # la vue de détail est recadrée (Pan) : 1 m vers la gauche
ch = m.layout_sync(L)
mk = kids(par, 'mark')
Pm = np.array([p.co[:2] for sp in mk[0].data.splines for p in sp.points])
rec(SEC, "vue de détail recadrée d'un mètre : son repère suit sur l'original (10 mm vers la gauche)", ch and near((Pm[:, 0].min(), Pm[:, 0].max()), (23.0, 37.0), 1e-4), (Pm[:, 0].min(), Pm[:, 0].max()))
cd.scale = 25.0
m.layout_sync(L)
mk = kids(par, 'mark')
Pm = np.array([p.co[:2] for sp in mk[0].data.splines for p in sp.points])
rec(SEC, "vue de détail passée au 1:25 : elle montre deux fois moins, son repère rétrécit (7 x 5 mm)", near((Pm[:, 0].max() - Pm[:, 0].min(), Pm[:, 1].max() - Pm[:, 1].min()), (7.0, 5.0), 1e-4), (Pm[:, 0].max() - Pm[:, 0].min(), Pm[:, 1].max() - Pm[:, 1].min()))
new2, r2, o2 = run("detail_callout", [C(-40.0, 0.0), C(-30.0, 10.0), C(-25.0, -35.0)])
ch2 = next((o for o in new2 if m.is_detail(o)), None)
rec(SEC, "deuxième vue de détail : lettre B ; l'original porte deux repères", ch2 is not None and ch2.dessin_detail.callout_tag == "B"
    and sorted(c.data.body for c in kids(par, 'label') if c.data.body in ("A", "B")) == ["A", "B"], ch2 and ch2.dessin_detail.callout_tag)
cd.center = (4.8, -2.5, 0.0); cd.scale = 50.0
m.layout_sync(L)
Pm = np.array([p.co[:2] for sp in kids(par, 'mark')[0].data.splines for p in sp.points])
rec(SEC, "vue de détail recadrée au bord de l'original : son repère est découpé au cadre de la fenêtre (50 mm)", near(Pm[:, 0].max(), 50.0, 1e-4), Pm[:, 0].max())
new3, r3, o3 = run("detail_callout", [C(-48.0, -48.0), C(-44.0, -44.0), C(30.0, -40.0)])
rec(SEC, "zone dessinée hors de toute fenêtre : rien n'est créé", not [o for o in new3 if m.is_detail(o)], [o.name for o in new3])
ents = m.layout_entities(L)
rec(SEC, "les repères sont imprimés avec les annotations", any(e[0] == 'L' and e[-1] == "Annotations" for e in ents))
bpy.data.objects.remove(ch_)
m.layout_sync(L)
rec(SEC, "vue de détail A supprimée : son repère disparaît de l'original, B reste", sorted(c.data.body for c in kids(par, 'label') if c.data.body in ("A", "B")) == ["B"],
    [c.data.body for c in kids(par, 'label')])
D = L.dessin_layout
D.label_style = 'TITLE'
rec(SEC, "titre de dessin : la vue de détail porte sa lettre dans le cercle, l'original le numéro 1",
    "B" in [c.data.body for c in kids(ch2, 'label')] and "Detail B" in [c.data.body for c in kids(ch2, 'label')] and "1" in [c.data.body for c in kids(par, 'label')],
    [c.data.body for c in kids(ch2, 'label')])

# ---------------------------------------------------------------- I. panneaux
SEC = "panneaux"


class FakeLayout:
    def __getattr__(self, n):
        def f(*a, **k):
            return FakeLayout()
        return f

    def __setattr__(self, n, v):
        pass


bad = []
for cls in (m.DESSIN_PT_layout_title, m.DESSIN_PT_layout_annotate, m.DESSIN_PT_layout_detail, m.DESSIN_PT_layout_page):
    for style in ('CLASSIC', 'SIDE'):
        try:
            bpy.ops.dessin.title_preset(preset=style)
            L.dessin_layout.show_title = True
            p = types.SimpleNamespace(layout=FakeLayout())
            cls.draw(p, BC)
            if hasattr(cls, "draw_header"):
                cls.draw_header(p, BC)
        except Exception as e:
            bad.append((cls.__name__, style, repr(e)))
rec(SEC, "Title Block, Annotate, Viewports et Page se dessinent sans erreur (cartouche Classic et Side strip)", not bad, bad)
order = [getattr(c, "bl_order", None) for c in (m.DESSIN_PT_layout, m.DESSIN_PT_layout_page, m.DESSIN_PT_layout_title, m.DESSIN_PT_layout_annotate,
                                                m.DESSIN_PT_layout_detail, m.DESSIN_PT_layout_layers, m.DESSIN_PT_layout_print)]
rec(SEC, "ordre de l'onglet Layout : Layouts, Page, Title Block, Annotate, Viewports, Layers, Print", order == [0, 1, 2, 3, 4, 5, 6], order)
for _text, op in m.SHEET_ANNOTATE_OPS:
    mod, name = op.split(".")
    if not hasattr(getattr(bpy.ops, mod), name) or getattr(getattr(bpy.ops, mod), name).get_rna_type() is None:
        bad.append(op)
rec(SEC, "chaque bouton du panneau Annotate lance une commande qui existe", not bad, bad)

shutil.rmtree(TMP, ignore_errors=True)
summary()
