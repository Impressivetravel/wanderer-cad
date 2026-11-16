"""Wanderer CAD : Layout — la feuille : cartouche personnalisable, champs automatiques, logo et images, symboles,
vue de détail agrandie, panneaux Title Block et Annotate."""

import bpy
import gpu
import math
import os
import re
import time
import numpy as np
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

from . import layout_engine as le
from .core import idle_tool, lang
from .base import DessinBase
from .drawing import draw_px_points, get_shader, line_px, px_scale
from .layout import (
    COL, GEN, SHEET, Z_IMAGE, _fit_size, _line_width, _local_matrix, _map_uv, _new_curve, _redraw, _remove, _sheet_text,
    _shown, _tr,
    detail_at, detail_create, detail_dress_refresh, detail_id, detail_map, detail_projector, detail_rebuild, details,
    double_click_blocked, dress_signature, frame_rect, is_layout, layout_collection, layouts, paper_label, paper_rebuild,
    paper_size, quiet, title_refresh, title_scale_text,
)


# --------------------------------------------------------------------------
# Cartouche : modèles et cases
# --------------------------------------------------------------------------
# Le cartouche est une suite de cases lues de gauche à droite ; une case marquée « new_row » commence une rangée. La
# largeur d'une case est relative aux autres cases de sa rangée ; la hauteur d'une rangée (mm) est celle de sa case la
# plus haute (0 : la rangée prend la place qui reste, utile dans un bandeau vertical). Le texte d'une case peut contenir
# des champs automatiques (<Scale>, <Sheet>...), comme les textes automatiques de SketchUp LayOut.

def _tc(label, text, width=1.0, height=10.0, size=3.5, new_row=False, align='LEFT', kind='TEXT'):
    return {"kind": kind, "label": label, "text": text, "new_row": new_row, "width": width, "height": height,
            "size": size, "align": align}


TITLE_CELL_KEYS = ("kind", "label", "text", "new_row", "width", "height", "size", "align")
TITLE_TEMPLATES = {
    # le cartouche d'origine : 170 x 34 mm en bas à droite
    'CLASSIC': ('BR', 170.0, [
        _tc("PROJECT", "<Project>", 136.0, 13.0, 5.0, True), _tc("SHEET", "<Sheet>", 34.0, 13.0, 6.5),
        _tc("TITLE", "<Title>", 106.0, 12.0, 4.0, True), _tc("SCALE", "<Scale>", 30.0, 12.0, 4.0), _tc("DATE", "<Date>", 34.0, 12.0, 3.2),
        _tc("DRAWN BY", "<DrawnBy>", 106.0, 9.0, 3.0, True), _tc("REV", "<Rev>", 30.0, 9.0, 3.0), _tc("FORMAT", "<Format>", 34.0, 9.0, 3.0),
    ]),
    # bandeau sur toute la largeur du cadre, en bas (une seule rangée, logo à gauche)
    'STRIP': ('BOTTOM', 170.0, [
        _tc("", "", 28.0, 16.0, 3.0, True, kind='LOGO'), _tc("PROJECT", "<Project>", 90.0, 16.0, 4.5), _tc("TITLE", "<Title>", 90.0, 16.0, 4.5),
        _tc("DRAWN BY", "<DrawnBy>", 40.0, 16.0, 3.0), _tc("DATE", "<Date>", 30.0, 16.0, 3.0), _tc("SCALE", "<Scale>", 30.0, 16.0, 3.5),
        _tc("REV", "<Rev>", 16.0, 16.0, 3.0), _tc("SHEET", "<Sheet>", 24.0, 16.0, 6.0, align='CENTER'),
    ]),
    # bandeau sur toute la hauteur du cadre, à droite (logo en haut, zone de notes, champs en bas), comme les planches d'architecte
    'SIDE': ('RIGHT', 62.0, [
        _tc("", "", 1.0, 30.0, 3.0, True, kind='LOGO'),
        _tc("NOTES", "", 1.0, 0.0, 2.5, True),
        _tc("PROJECT", "<Project>", 1.0, 18.0, 5.0, True),
        _tc("TITLE", "<Title>", 1.0, 16.0, 4.5, True),
        _tc("DRAWN BY", "<DrawnBy>", 1.0, 10.0, 3.0, True), _tc("DATE", "<Date>", 1.0, 10.0, 3.0),
        _tc("SCALE", "<Scale>", 1.0, 10.0, 3.5, True), _tc("REV", "<Rev>", 1.0, 10.0, 3.0),
        _tc("FORMAT", "<Format>", 1.0, 14.0, 3.0, True), _tc("SHEET", "<Sheet> / <Sheets>", 1.2, 14.0, 6.0),
    ]),
    # petit cartouche d'une rangée
    'COMPACT': ('BR', 120.0, [
        _tc("TITLE", "<Title>", 70.0, 12.0, 4.0, True), _tc("SCALE", "<Scale>", 25.0, 12.0, 3.5), _tc("SHEET", "<Sheet>", 25.0, 12.0, 5.0),
    ]),
}
TITLE_TEMPLATE_ITEMS = (
    ('CLASSIC', "Classic block", "A block of three rows in the bottom right corner: project, title, scale, date, sheet number"),
    ('STRIP', "Bottom strip", "A band across the bottom of the sheet: logo, project, title, drawn by, date, scale, sheet number"),
    ('SIDE', "Side strip", "A band along the right side of the sheet, as on architectural drawings: logo on top, room for notes, fields at the bottom"),
    ('COMPACT', "Compact", "One small row in the bottom right corner: title, scale, sheet number"),
)


def title_cells(L):
    """Cases du cartouche (dictionnaires) : celles de la mise en page, sinon le modèle d'origine (fichiers d'avant)."""
    if len(L.title_cells):
        return [{k: getattr(c, k) for k in TITLE_CELL_KEYS} for c in L.title_cells]
    return [dict(c) for c in TITLE_TEMPLATES['CLASSIC'][2]]


def title_cells_write(L, cells):
    L.title_cells.clear()
    for c in cells:
        it = L.title_cells.add()
        for k in TITLE_CELL_KEYS:
            setattr(it, k, c[k])
    L.title_cell_index = min(max(L.title_cell_index, 0), max(len(L.title_cells) - 1, 0))


def title_apply_template(L, key):
    """Remplace le cartouche de la mise en page par un modèle (position, largeur, cases)."""
    pos, w, cells = TITLE_TEMPLATES[key]
    L.title_pos = pos
    L.title_w = w
    title_cells_write(L, cells)
    L.title_cell_index = 0


def title_rows(cells):
    rows = []
    for c in cells:
        if c["new_row"] or not rows:
            rows.append([])
        rows[-1].append(c)
    return rows


def title_layout(L):
    """Géométrie du cartouche : ((x0, y0, x1, y1) du bloc, [(case, x0, y0, x1, y1)], hauteurs des rangées), en mm."""
    fx0, fy0, fx1, fy1 = frame_rect(L)
    fw, fh = fx1 - fx0, fy1 - fy0
    rows = title_rows(title_cells(L))
    pos = L.title_pos
    w = fw if pos == 'BOTTOM' else min(max(L.title_w, 20.0), fw)
    heights = [max(c["height"] for c in r) for r in rows]
    fixed = sum(h for h in heights if h > 0.0)
    nfree = sum(1 for h in heights if h <= 0.0)
    if pos == 'RIGHT':                       # bandeau vertical : les rangées libres se partagent la hauteur qui reste
        free = max((fh - fixed) / nfree, 0.0) if nfree else 0.0
    else:
        free = 10.0
    heights = [h if h > 0.0 else free for h in heights]
    tot = sum(heights)
    if tot > fh > 0.0:                       # plus haut que le cadre : tout est réduit pour tenir
        heights = [h * fh / tot for h in heights]
        tot = fh
    total = fh if pos == 'RIGHT' else tot
    x0 = fx0 if pos in ('BL', 'TL', 'BOTTOM') else fx1 - w
    x1 = x0 + w
    if pos in ('TR', 'TL'):
        y1 = fy1
        y0 = y1 - total
    else:
        y0 = fy0
        y1 = y0 + total
    y = y0 + tot if pos not in ('TR', 'TL') else y1          # haut de la première rangée
    placed = []
    for r, h in zip(rows, heights):
        ws = sum(max(c["width"], 0.05) for c in r)
        x = x0
        for c in r:
            cw = w * max(c["width"], 0.05) / ws
            placed.append((c, x, y - h, x + cw, y))
            x += cw
        y -= h
    return (x0, y0, x1, y1), placed, heights


# --------------------------------------------------------------------------
# Champs automatiques
# --------------------------------------------------------------------------

SHEET_FIELDS = (
    ("Project", "Project name (Title Block panel)"), ("Title", "Title of the sheet"), ("DrawnBy", "Drawn by"),
    ("Date", "Date typed in the Title Block panel"), ("Sheet", "Sheet number"), ("Sheets", "Number of sheets in the file"),
    ("Rev", "Revision"), ("Scale", "Scale of the viewports (or 'As noted' when they differ)"), ("Format", "Paper size"),
    ("Layout", "Name of the layout"), ("File", "Name of the Blender file"), ("Today", "Today's date"),
)
_SHEET_FIELD_RE = re.compile(r"<([A-Za-z]+)>")


def field_values(scene):
    """Valeur de chaque champ automatique pour une mise en page (clés en minuscules)."""
    L = scene.dessin_layout
    try:
        fname = os.path.splitext(os.path.basename(bpy.data.filepath))[0]
    except (AttributeError, TypeError):
        fname = ""
    count = str(len(layouts()))
    if L.t_number.strip().isdigit():                 # « 03 / 05 » : le nombre de planches s'écrit comme le numéro
        count = count.zfill(len(L.t_number.strip()))
    return {"project": L.t_project, "title": L.t_title, "drawnby": L.t_author, "author": L.t_author, "date": L.t_date,
            "sheet": L.t_number, "sheets": count, "rev": L.t_revision, "revision": L.t_revision,
            "scale": title_scale_text(scene), "format": paper_label(L), "layout": scene.name, "file": fname,
            "today": time.strftime("%d/%m/%Y" if lang() == 'FR' else "%Y-%m-%d")}


def field_resolve(text, vals):
    """Remplace les champs <Nom> connus par leur valeur ; un nom inconnu reste tel quel."""
    return _SHEET_FIELD_RE.sub(lambda mt: vals.get(mt.group(1).lower(), mt.group(0)), text)


def has_field(text):
    keys = {"project", "title", "drawnby", "author", "date", "sheet", "sheets", "rev", "revision", "scale", "format",
            "layout", "file", "today"}
    return any(mt.group(1).lower() in keys for mt in _SHEET_FIELD_RE.finditer(text or ""))


def title_signature(scene):
    """Ce qu'affiche le cartouche une fois les champs remplis : s'il change (échelle d'un détail, nombre de planches,
    fichier renommé...), le cartouche est refait."""
    L = scene.dessin_layout
    if not L.show_title:
        return ""
    vals = field_values(scene)
    return "\n".join(field_resolve(c["text"], vals) for c in title_cells(L) if c["kind"] == 'TEXT')


def fields_refresh(scene):
    """Textes de la feuille qui contiennent des champs (<Scale>, <Sheet> / <Sheets>...) : le texte tapé devient un gabarit
    (propriété « wd_field ») et l'objet affiche sa valeur, remise à jour quand elle change. Un texte retouché à la main
    reprend sa liberté (ou devient un nouveau gabarit s'il contient encore un champ). Retourne True si un texte a changé."""
    changed = False
    vals = None
    try:
        for o in scene.objects:
            if o.type != 'FONT' or o.get(GEN) or o.get(SHEET):
                continue
            body = o.data.body
            tpl = o.get("wd_field")
            if tpl is not None and body != o.get("wd_field_out", ""):
                tpl = None
                del o["wd_field"]
                if "wd_field_out" in o.keys():
                    del o["wd_field_out"]
            if tpl is None:
                if not has_field(body):
                    continue
                tpl = body
                o["wd_field"] = tpl
            if vals is None:
                vals = field_values(scene)
            out = field_resolve(tpl, vals)
            if body != out:
                o.data.body = out
                changed = True
            if o.get("wd_field_out") != out:
                o["wd_field_out"] = out
    except (AttributeError, ReferenceError, RuntimeError):
        pass
    return changed


# --------------------------------------------------------------------------
# Images sur la feuille (logo du cartouche, image posée) : un objet vide qui affiche l'image
# --------------------------------------------------------------------------

IMAGE_GLOB = "*.png;*.jpg;*.jpeg;*.tif;*.tiff;*.bmp;*.webp;*.tga;*.exr"
_SHEET_IMG = {}          # données d'export gardées le temps d'un export : clé -> (largeur, hauteur, RVB, alpha)


def image_load(path):
    """Image Blender d'un fichier (réutilisée si elle est déjà chargée) ; None si le fichier manque."""
    if not path or not path.strip():
        return None
    ap = bpy.path.abspath(path)
    if not os.path.isfile(ap):
        return None
    try:
        return bpy.data.images.load(ap, check_existing=True)
    except (RuntimeError, OSError):
        return None


def image_empty(name, img, cx, cy, long_side):
    """Objet qui affiche une image, centrée en (cx, cy), son plus grand côté mesurant long_side mm."""
    o = bpy.data.objects.new(name, None)
    o.empty_display_type = 'IMAGE'
    o.data = img
    o.empty_display_size = max(long_side, 0.1)
    o.empty_image_offset = (-0.5, -0.5)
    o.empty_image_depth = 'DEFAULT'
    o.empty_image_side = 'DOUBLE_SIDED'
    o.use_empty_image_alpha = True
    o.color = (1.0, 1.0, 1.0, 1.0)
    o.location = (cx, cy, Z_IMAGE)
    return o


def is_sheet_image(o):
    try:
        return o.type == 'EMPTY' and o.empty_display_type == 'IMAGE' and o.data is not None
    except (AttributeError, ReferenceError):
        return False


def image_corners(o):
    """(coin bas gauche, côté bas, côté gauche) d'une image de la feuille, en mm de papier ; None si elle est vide."""
    iw, ih = o.data.size
    if not iw or not ih:
        return None
    long = float(max(iw, ih))
    sx, sy = o.empty_display_size * iw / long, o.empty_display_size * ih / long
    ox, oy = o.empty_image_offset
    M = _local_matrix(o)
    bl = M @ Vector((ox * sx, oy * sy, 0.0))
    R = M.to_3x3()
    u = R @ Vector((sx, 0.0, 0.0))
    v = R @ Vector((0.0, sy, 0.0))
    return (bl.x, bl.y), (u.x, u.y), (v.x, v.y)


def image_pixels(img, max_px=1600):
    """(largeur, hauteur, octets RVB, octets alpha ou None), rangée du haut d'abord ; les grandes images sont réduites."""
    w, h = img.size
    if not w or not h:
        return None
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    a = np.clip(px.reshape(h, w, 4)[::-1], 0.0, 1.0)
    step = int(math.ceil(max(w, h) / float(max_px)))
    if step > 1:
        hh, ww = (h // step) * step, (w // step) * step
        blk = a[:hh, :ww].reshape(hh // step, step, ww // step, step, 4)
        al = blk[..., 3:4]
        wsum = al.sum(axis=(1, 3))
        rgb = (blk[..., :3] * al).sum(axis=(1, 3)) / np.maximum(wsum, 1e-6)       # (moyenne pondérée par l'opacité)
        a = np.concatenate((rgb, wsum / float(step * step)), axis=2)
    h2, w2 = a.shape[0], a.shape[1]
    rgb8 = (a[:, :, :3] * 255.0 + 0.5).astype(np.uint8)
    al8 = (a[:, :, 3] * 255.0 + 0.5).astype(np.uint8)
    return w2, h2, rgb8.tobytes(), (None if int(al8.min()) == 255 else al8.tobytes())


def sheet_image_entities(scene, view_layer=None, styles=None):
    """Entités image ('I', ...) d'une mise en page pour l'export : logo du cartouche et images posées sur la feuille.
    styles : réglages d'impression des calques ; une image d'un calque non imprimé n'est pas exportée."""
    out = []
    for o in scene.objects:
        if not is_sheet_image(o) or not _shown(o, view_layer):
            continue
        if styles and not styles.get(le.print_tag(o)[0], (True,))[0]:
            continue
        try:
            cn = image_corners(o)
            if cn is None:
                continue
            img = o.data
            key = "%s|%d|%d" % (img.name, img.size[0], img.size[1])
            data = _SHEET_IMG.get(key)
            if data is None:
                data = image_pixels(img)
                if data is None:
                    continue
                if len(_SHEET_IMG) > 12:
                    _SHEET_IMG.clear()
                _SHEET_IMG[key] = data
            out.append(('I', key, data, cn[0], cn[1], cn[2], "Images"))
        except (RuntimeError, AttributeError, ReferenceError, ValueError, TypeError):
            continue
    return out


def sheet_image_at(context, region, rv3d, mx, my):
    """Image de la feuille sous le curseur (la plus petite si plusieurs se recouvrent), pour la sélection au clic."""
    from bpy_extras.view3d_utils import location_3d_to_region_2d
    best, best_area = None, None
    try:
        if not is_layout(context.scene):
            return None
        for o in context.view_layer.objects:
            if not is_sheet_image(o) or o.hide_select or not o.visible_get():
                continue
            cn = image_corners(o)
            if cn is None:
                continue
            (ox, oy), (ux, uy), (vx, vy) = cn
            z = o.matrix_world.translation.z
            quad = [location_3d_to_region_2d(region, rv3d, Vector(p + (z,)))
                    for p in ((ox, oy), (ox + ux, oy + uy), (ox + ux + vx, oy + uy + vy), (ox + vx, oy + vy))]
            if any(q is None for q in quad):
                continue
            sign = 0
            inside = True
            for i in range(4):
                a, b = quad[i], quad[(i + 1) % 4]
                cr = (b.x - a.x) * (my - a.y) - (b.y - a.y) * (mx - a.x)
                if abs(cr) < 1e-9:
                    continue
                if sign == 0:
                    sign = 1 if cr > 0 else -1
                elif (cr > 0) != (sign > 0):
                    inside = False
                    break
            if inside:
                area = abs(ux * vy - uy * vx)
                if best is None or area < best_area:
                    best, best_area = o, area
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
        return None
    return best


# --------------------------------------------------------------------------
# Dessin du cartouche
# --------------------------------------------------------------------------

def title_logo(scene, L, x0, y0, x1, y1):
    """Logo du cartouche, ajusté dans la case (proportions gardées) ; sans fichier, un rappel gris qui ne s'imprime pas."""
    img = image_load(L.t_logo)
    if img is None or not img.size[0] or not img.size[1] or x1 - x0 < 1.0 or y1 - y0 < 1.0:
        if img is None and x1 - x0 > 6.0 and y1 - y0 > 3.0:
            o = _sheet_text(scene, "Logo", (x0 + x1) / 2.0, (y0 + y1) / 2.0 - 1.0, 2.5, 'CENTER', 0.7, x1 - x0)
            if o is not None:
                o[SHEET] = 'hint'
        return None
    iw, ih = img.size
    k = min((x1 - x0) / iw, (y1 - y0) / ih)
    o = image_empty("Logo", img, (x0 + x1) / 2.0, (y0 + y1) / 2.0, max(iw, ih) * k)
    o[SHEET] = 'logo'
    o.hide_select = True
    layout_collection(scene, 'sheet').objects.link(o)
    return o


def title_draw(scene, L, show):
    """Dessine le cartouche d'une mise en page : contour, séparations, libellés, textes (champs remplis) et logo."""
    (x0, y0, x1, y1), placed, _heights = title_layout(L)
    fx0, fy0, fx1, fy1 = frame_rect(L)
    eps = 1e-6
    outer = []
    for seg, on_frame in ((((x0, y0), (x0, y1)), abs(x0 - fx0) < eps), (((x0, y1), (x1, y1)), abs(y1 - fy1) < eps),
                          (((x1, y1), (x1, y0)), abs(x1 - fx1) < eps), (((x1, y0), (x0, y0)), abs(y0 - fy0) < eps)):
        if not (L.show_frame and on_frame):          # (un côté posé sur le cadre n'est pas tracé deux fois)
            outer.append((list(seg), False))
    if outer:
        cu = _new_curve("Title block", outer)
        _line_width(cu, L.lw_frame, show)
        _title_curve(scene, "Title block", cu, 'frame')
    inner, tops = [], set()
    for _c, cx0, cy0, cx1, cy1 in placed:
        if cx1 < x1 - eps:
            inner.append(([(cx1, cy0), (cx1, cy1)], False))
        if cy1 < y1 - eps and round(cy1, 5) not in tops:
            tops.add(round(cy1, 5))
            inner.append(([(x0, cy1), (x1, cy1)], False))
    if inner:
        cu = _new_curve("Title block lines", inner)
        _line_width(cu, L.lw_annot, show)
        _title_curve(scene, "Title block lines", cu, 'title')
    vals = field_values(scene)
    pad, lab = 1.5, 1.8
    for c, cx0, cy0, cx1, cy1 in placed:
        cw, ch = cx1 - cx0, cy1 - cy0
        label = c["label"].strip()
        if label:
            _sheet_text(scene, _tr(label), cx0 + pad, cy1 - pad - lab, lab, grey=0.35, max_w=cw - 2 * pad)
        if c["kind"] == 'LOGO':
            title_logo(scene, L, cx0 + pad, cy0 + pad, cx1 - pad, cy1 - pad - ((lab + pad * 0.5) if label else 0.0))
            continue
        value = field_resolve(c["text"], vals)
        if not value.strip():
            continue
        room = ch - ((lab + 2.5 * pad) if label else 2.0 * pad)
        size = min(c["size"], max(room, 1.5))
        if c["align"] == 'CENTER':
            x, al = (cx0 + cx1) / 2.0, 'CENTER'
        elif c["align"] == 'RIGHT':
            x, al = cx1 - pad, 'RIGHT'
        else:
            x, al = cx0 + pad, 'LEFT'
        _sheet_text(scene, value, x, cy0 + pad * 0.9, size, al, max_w=cw - 2 * pad)


def _title_curve(scene, name, cu, role):
    o = bpy.data.objects.new(name, cu)
    o[SHEET] = role
    o.color = (0.0, 0.0, 0.0, 1.0)
    o.hide_select = True
    layout_collection(scene, 'sheet').objects.link(o)
    return o


def title_copy(src, dst, free=True):
    """Reporte le cartouche d'une mise en page sur une autre : modèle (position, largeur, cases), logo, style des
    étiquettes, et les textes communs à toutes les planches (projet, auteur). Titre, numéro et indice restent propres à
    chaque planche. free : le cartouche libre (dessiné à la main) est recopié aussi, à la place de celui de `dst`."""
    S, D = src.dessin_layout, dst.dessin_layout
    for key in ("title_pos", "title_w", "t_logo", "label_style", "t_project", "t_author"):
        setattr(D, key, getattr(S, key))
    title_cells_write(D, title_cells(S) if len(S.title_cells) else [])
    if free and title_free_copy(src, dst):
        D.show_title = False              # (le cartouche libre remplace le cartouche généré)


# --------------------------------------------------------------------------
# Cartouche libre : des traits, des textes et un logo ordinaires, comme on le dessine dans AutoCAD
# --------------------------------------------------------------------------
# Le cartouche généré peut être converti en dessin libre : un rectangle, un trait par séparation, des textes (ceux qui
# contiennent des champs restent automatiques) et le logo, rangés sur le calque « Title block » de la mise en page. On
# le retouche alors avec les outils habituels (Stretch, Move, Line, Rectangle, Text, Field...) ; il se recopie sur les
# autres mises en page et sur les nouvelles.

def title_free_objects(scene):
    """Objets du cartouche libre d'une mise en page (calque « Title block »)."""
    c = layout_collection(scene, 'title', False)
    try:
        return list(c.objects) if c is not None else []
    except (AttributeError, ReferenceError):
        return []


def _free_line(col, name, pts, closed=False, lw=0.0):
    o = bpy.data.objects.new(name, _new_curve(name, [(pts, closed)]))
    o.color = (0.0, 0.0, 0.0, 1.0)
    if lw > 0.0:
        o["wd_lw"] = float(lw)             # épaisseur d'impression propre à l'objet (le contour, plus épais que les cases)
    col.objects.link(o)
    return o


def _free_text(col, name, body, x, y, size, align='LEFT', grey=0.0):
    fc = bpy.data.curves.new(name, 'FONT')
    fc.body = body
    fc.size = size
    fc.align_x = align
    fc.align_y = 'BOTTOM_BASELINE'
    o = bpy.data.objects.new(name, fc)
    o["dessin_text"] = True
    o.color = (grey, grey, grey, 1.0)
    o.location = (x, y, 0.0)
    col.objects.link(o)
    return o


def title_explode(scene):
    """Convertit le cartouche généré en dessin libre. Retourne les objets créés (le cartouche généré est masqué)."""
    L = scene.dessin_layout
    (x0, y0, x1, y1), placed, _heights = title_layout(L)
    col = layout_collection(scene, 'title')
    eps = 1e-6
    out = [_free_line(col, "Title outline", [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], True, L.lw_frame)]
    tops = set()
    for _c, cx0, cy0, cx1, cy1 in placed:
        if cx1 < x1 - eps:
            out.append(_free_line(col, "Title line", [(cx1, cy0), (cx1, cy1)]))
        if cy1 < y1 - eps and round(cy1, 5) not in tops:
            tops.add(round(cy1, 5))
            out.append(_free_line(col, "Title line", [(x0, cy1), (x1, cy1)]))
    vals = field_values(scene)
    pad, lab = 1.5, 1.8
    for c, cx0, cy0, cx1, cy1 in placed:
        cw, ch = cx1 - cx0, cy1 - cy0
        label = c["label"].strip()
        if label:
            out.append(_free_text(col, "Title caption", _tr(label), cx0 + pad, cy1 - pad - lab, lab, grey=0.35))
        if c["kind"] == 'LOGO':
            img = image_load(L.t_logo)
            bx0, by0, bx1, by1 = cx0 + pad, cy0 + pad, cx1 - pad, cy1 - pad - ((lab + pad * 0.5) if label else 0.0)
            if img is not None and img.size[0] and img.size[1] and bx1 - bx0 > 1.0 and by1 - by0 > 1.0:
                iw, ih = img.size
                k = min((bx1 - bx0) / iw, (by1 - by0) / ih)
                o = image_empty("Logo", img, (bx0 + bx1) / 2.0, (by0 + by1) / 2.0, max(iw, ih) * k)
                o["wd_image"] = 1
                col.objects.link(o)
                out.append(o)
            continue
        if not c["text"].strip():
            continue
        room = ch - ((lab + 2.5 * pad) if label else 2.0 * pad)
        size = _fit_size(field_resolve(c["text"], vals), min(c["size"], max(room, 1.5)), cw - 2 * pad)
        if c["align"] == 'CENTER':
            x, al = (cx0 + cx1) / 2.0, 'CENTER'
        elif c["align"] == 'RIGHT':
            x, al = cx1 - pad, 'RIGHT'
        else:
            x, al = cx0 + pad, 'LEFT'
        out.append(_free_text(col, "Title text", c["text"], x, cy0 + pad * 0.9, size, al))
    with quiet():
        L.show_title = False
    paper_rebuild(scene)
    fields_refresh(scene)
    return out


def title_free_copy(src, dst):
    """Recopie le cartouche libre de `src` sur `dst` (celui de `dst` est remplacé). Retourne le nombre d'objets copiés."""
    objs = title_free_objects(src)
    _remove(title_free_objects(dst))
    if not objs:
        return 0
    col = layout_collection(dst, 'title')
    for o in objs:
        c = o.copy()
        if o.data is not None and o.type != 'EMPTY':          # (une image garde son image)
            c.data = o.data.copy()
        if c.type == 'FONT' and c.get("wd_field") is not None:      # texte à champs : il se remplira pour sa planche
            c.data.body = c["wd_field"]
            del c["wd_field"]
            if "wd_field_out" in c.keys():
                del c["wd_field_out"]
        col.objects.link(c)
    fields_refresh(dst)
    return len(objs)


# --------------------------------------------------------------------------
# Cartouche : modification directe sur la feuille (comme un tableau : on glisse ses traits)
# --------------------------------------------------------------------------

TITLE_MIN = 3.0            # hauteur minimale d'une rangée, largeur minimale d'une case (mm)
TITLE_CORNERS = ('BR', 'BL', 'TR', 'TL')
_TITLE_EDIT = {"scene": None, "hover": None, "drag": None}
# scene : nom de la mise en page dont on modifie le cartouche (None : personne) ; hover / drag : (type, index) du trait
# survolé / glissé


def title_cells_ensure(L):
    """Les cases deviennent celles de la mise en page (un fichier d'avant n'a que le modèle d'origine, implicite)."""
    if not len(L.title_cells):
        title_cells_write(L, title_cells(L))


def title_row_cells(L):
    """[[indices des cases]] rangée par rangée, de haut en bas."""
    rows = []
    for i, c in enumerate(title_cells(L)):
        if c["new_row"] or not rows:
            rows.append([])
        rows[-1].append(i)
    return rows


def title_anchor(L):
    """Côtés du bloc tenus par le cadre : ('L' / 'R' / None : toute la largeur, 'B' / 'T' / None : toute la hauteur)."""
    pos = L.title_pos
    return (None if pos == 'BOTTOM' else ('L' if pos in ('BL', 'TL') else 'R'),
            None if pos == 'RIGHT' else ('T' if pos in ('TR', 'TL') else 'B'))


def title_handles(L):
    """Traits du cartouche qui se glissent : [(type, index, (ax, ay), (bx, by))] en mm de papier.
    'W' : bord libre du bloc (sa largeur) ; 'H' : trait sous la rangée `index` (-1 : bord du haut) ; 'V' : séparation à
    droite de la case `index`."""
    (x0, y0, x1, y1), placed, _heights = title_layout(L)
    rows = title_row_cells(L)
    ax, ay = title_anchor(L)
    out = []
    if ax == 'R':
        out.append(('W', -1, (x0, y0), (x0, y1)))
    elif ax == 'L':
        out.append(('W', -1, (x1, y0), (x1, y1)))
    n = len(rows)
    for r, idx in enumerate(rows):
        cy0, cy1 = placed[idx[0]][2], placed[idx[0]][4]
        if r == 0 and ay == 'B':
            out.append(('H', -1, (x0, cy1), (x1, cy1)))
        if r < n - 1 or ay == 'T':
            out.append(('H', r, (x0, cy0), (x1, cy0)))
        for i in idx[:-1]:
            out.append(('V', i, (placed[i][3], cy0), (placed[i][3], cy1)))
    return out


def title_hit(L, x, y, tol):
    """Ce qui se trouve au point (x, y) du papier : ('W' | 'H' | 'V', index) pour un trait qui se glisse (à moins de
    `tol` mm), ('C', index) dans une case, None hors du cartouche."""
    best, bd = None, tol
    for kind, idx, a, b in title_handles(L):
        if kind == 'H':
            d = abs(y - a[1]) if a[0] - tol <= x <= b[0] + tol else 1e9
        else:
            d = abs(x - a[0]) if a[1] - tol <= y <= b[1] + tol else 1e9
        if d <= bd and (best is None or d < bd - 1e-9 or kind == 'V'):      # (à un croisement, la séparation l'emporte)
            best, bd = (kind, idx), d
    if best is not None:
        return best
    for i, (_c, cx0, cy0, cx1, cy1) in enumerate(title_layout(L)[1]):
        if cx0 <= x <= cx1 and cy0 <= y <= cy1:
            return ('C', i)
    return None


def title_drag(L, kind, idx, x, y):
    """Glisse un trait du cartouche jusqu'au point (x, y) du papier. Retourne True si le cartouche a changé.
    Bord libre : largeur du bloc. Séparation : les deux cases voisines se partagent leur largeur. Trait horizontal : la
    rangée du côté tenu par le cadre change de hauteur (le bloc grandit) ; dans un bandeau vertical, c'est la rangée
    extensible qui absorbe."""
    title_cells_ensure(L)
    (x0, _y0, x1, _y1), placed, _heights = title_layout(L)
    fx0, fy0, fx1, fy1 = frame_rect(L)
    cells = L.title_cells
    ax, ay = title_anchor(L)
    if kind == 'W':
        if ax is None:
            return False
        w = min(max((x1 - x) if ax == 'R' else (x - x0), 20.0), max(fx1 - fx0, 20.0))
        if abs(w - L.title_w) < 1e-6:
            return False
        L.title_w = w
        return True
    if kind == 'V':
        rows = title_row_cells(L)
        if not any(idx in r and idx + 1 in r for r in rows):
            return False
        left, right = placed[idx][1], placed[idx + 1][3]
        span = right - left
        if span <= 1e-6:
            return False
        m = min(TITLE_MIN, span / 4.0)
        t = (min(max(x, left + m), right - m) - left) / span
        ws = cells[idx].width + cells[idx + 1].width
        a, b = max(ws * t, 0.05), max(ws * (1.0 - t), 0.05)
        if abs(a - cells[idx].width) < 1e-9:
            return False
        cells[idx].width, cells[idx + 1].width = a, b
        return True
    if kind == 'H':
        rows = title_row_cells(L)
        n = len(rows)
        raw = [max(cells[i].height for i in r) for r in rows]
        top = [placed[r[0]][4] for r in rows]
        bot = [placed[r[0]][2] for r in rows]
        if idx < 0:
            target, from_top = 0, False
        elif idx >= n - 1:
            target, from_top = n - 1, True
        else:
            free = [k for k, h in enumerate(raw) if h <= 0.0]
            if ay == 'T':
                target, from_top = idx, True
            elif ay is None and free and (raw[idx + 1] <= 0.0 or (raw[idx] > 0.0 and min(free) > idx + 1)):
                target, from_top = idx, True            # la rangée extensible est dessous : celles du dessus tiennent au haut
            else:
                target, from_top = idx + 1, False
        h = (top[target] - y) if from_top else (y - bot[target])
        h = min(max(h, TITLE_MIN), max(fy1 - fy0, TITLE_MIN))
        if all(abs(cells[i].height - h) < 1e-6 for i in rows[target]):
            return False
        for i in rows[target]:
            cells[i].height = h
        return True
    return False


def title_nearest_corner(L, x, y):
    """Coin du cadre le plus proche du point (x, y) : 'BR', 'BL', 'TR' ou 'TL'."""
    fx0, fy0, fx1, fy1 = frame_rect(L)
    return ('B' if y < (fy0 + fy1) / 2.0 else 'T') + ('L' if x < (fx0 + fx1) / 2.0 else 'R')


def title_insert(L, where):
    """Ajoute une case au cartouche et la rend active. 'COLUMN' : la case active est partagée en deux, la nouvelle à sa
    droite ; 'ROW' / 'ROW_ABOVE' : une rangée d'une case sous / au-dessus de la rangée active ; 'AFTER' : une case de
    largeur 1 après la case active, dans sa rangée."""
    title_cells_ensure(L)
    cells = L.title_cells
    i = min(max(L.title_cell_index, 0), len(cells) - 1)
    rows = title_row_cells(L)
    row = next(r for r in rows if i in r)
    row_h = max(cells[j].height for j in row)
    ref_h, ref_w, ref_size = cells[i].height, cells[i].width, cells[i].size
    it = cells.add()                       # (les cases déjà lues ne sont plus valables : on les reprend par leur index)
    it.size = min(ref_size, 3.5)
    if where == 'COLUMN':
        half = max(ref_w / 2.0, 0.05)
        cells[i].width = half
        it.width, it.height = half, row_h
        dest = i + 1
    elif where in ('ROW', 'ROW_ABOVE'):
        it.width, it.height, it.new_row = 1.0, (row_h if row_h > 0.0 else 10.0), True
        if where == 'ROW':
            dest = row[-1] + 1
        else:
            dest = row[0]
            cells[row[0]].new_row = True     # l'ancienne tête de rangée le reste, sous la nouvelle
    else:
        it.label, it.width, it.height = "LABEL", 1.0, ref_h
        dest = i + 1
    cells.move(len(cells) - 1, dest)
    L.title_cell_index = dest
    return dest


def title_remove(L):
    """Retire la case active (sa rangée disparaît avec elle si elle y était seule). False s'il n'en reste qu'une."""
    title_cells_ensure(L)
    cells = L.title_cells
    if len(cells) <= 1:
        return False
    i = min(max(L.title_cell_index, 0), len(cells) - 1)
    starts = cells[i].new_row or i == 0
    cells.remove(i)
    if starts and i < len(cells):           # la case suivante prend la tête de la rangée
        cells[i].new_row = True
    L.title_cell_index = min(i, len(cells) - 1)
    return True


def title_edit_draw():
    """Pendant la modification du cartouche : la case active en bleu, les traits qui se glissent marqués d'un carré, le
    trait survolé ou glissé en gras."""
    st = _TITLE_EDIT
    if st["scene"] is None:
        return
    try:
        sc = bpy.context.scene
        if sc.name != st["scene"] or not is_layout(sc) or not sc.dessin_layout.show_title:
            return
        L = sc.dessin_layout
        placed = title_layout(L)[1]
        handles = title_handles(L)
        shader = get_shader('3D')
        gpu.state.blend_set('ALPHA')
        gpu.state.depth_test_set('NONE')
        shader.bind()
        blue = (0.04, 0.4, 0.95, 1.0)
        i = L.title_cell_index
        if 0 <= i < len(placed):
            _c, cx0, cy0, cx1, cy1 = placed[i]
            q = [(cx0, cy0, 0.0), (cx1, cy0, 0.0), (cx1, cy1, 0.0), (cx0, cy1, 0.0)]
            shader.uniform_float("color", (0.1, 0.45, 1.0, 0.12))
            batch_for_shader(shader, 'TRIS', {"pos": [q[0], q[1], q[2], q[0], q[2], q[3]]}).draw(shader)
            gpu.state.line_width_set(line_px(2.0))
            shader.uniform_float("color", blue)
            batch_for_shader(shader, 'LINES', {"pos": [q[0], q[1], q[1], q[2], q[2], q[3], q[3], q[0]]}).draw(shader)
        hot = st["drag"] or st["hover"]
        if hot is not None and hot[0] in ('W', 'H', 'V'):
            for kind, idx, a, b in handles:
                if (kind, idx) == tuple(hot[:2]):
                    gpu.state.line_width_set(line_px(3.5))
                    shader.uniform_float("color", blue)
                    batch_for_shader(shader, 'LINES', {"pos": [(a[0], a[1], 0.0), (b[0], b[1], 0.0)]}).draw(shader)
        gpu.state.line_width_set(1.0)
        if handles:
            draw_px_points([((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0, 0.0) for _k, _i, a, b in handles],
                           7.0 * px_scale(0.35), blue)
        gpu.state.blend_set('NONE')
    except (AttributeError, ReferenceError, RuntimeError, ValueError, TypeError, SystemError):
        pass


# --------------------------------------------------------------------------
# Opérateurs : cartouche
# --------------------------------------------------------------------------

class _LayoutOp:
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return is_layout(context.scene)


def _title_changed(scene):
    paper_rebuild(scene)
    _redraw()


class DESSIN_OT_title_preset(_LayoutOp, bpy.types.Operator):
    bl_idname = "dessin.title_preset"
    bl_label = "Title Block Template"
    bl_description = ("Replaces the title block of this layout with a template; its cells can then be edited one by one. "
                      "A free title block (drawn by hand) is removed")

    preset: bpy.props.EnumProperty(name="Template", items=TITLE_TEMPLATE_ITEMS, default='CLASSIC')

    def execute(self, context):
        sc = context.scene
        L = sc.dessin_layout
        with quiet():
            title_apply_template(L, self.preset)
            L.show_title = True
            _remove(title_free_objects(sc))
        _title_changed(sc)
        return {'FINISHED'}


class DESSIN_OT_title_explode(_LayoutOp, bpy.types.Operator):
    bl_idname = "dessin.title_explode"
    bl_label = "Convert to Free Drawing"
    bl_description = ("Turns the title block into ordinary objects, as it is drawn in AutoCAD: a rectangle, one line per "
                      "separation, texts (those with fields like <Scale> stay automatic) and the logo, on the layer "
                      "'Title block'. Edit them with the usual tools: Stretch, Move, Line, Rectangle, Text, Field... "
                      "Copy to All Layouts and new layouts take this drawing")

    def execute(self, context):
        sc = context.scene
        L = sc.dessin_layout
        if title_free_objects(sc):
            self.report({'INFO'}, "This layout already has a free title block (layer 'Title block')")
            return {'CANCELLED'}
        with quiet():
            L.show_title = True               # (masqué : on convertit le cartouche tel qu'il serait dessiné)
        objs = title_explode(sc)
        try:
            for o in context.selected_objects:
                o.select_set(False)
        except (RuntimeError, ReferenceError, AttributeError):
            pass
        _redraw()
        self.report({'INFO'}, f"Free title block: {len(objs)} objects on the layer 'Title block'. Edit them with the usual tools")
        return {'FINISHED'}


class DESSIN_OT_title_free_select(_LayoutOp, bpy.types.Operator):
    bl_idname = "dessin.title_free_select"
    bl_label = "Select the Title Block"
    bl_description = "Selects every object of the free title block (to move it, copy it or delete it in one go)"

    def execute(self, context):
        objs = title_free_objects(context.scene)
        if not objs:
            return {'CANCELLED'}
        try:
            for o in context.selected_objects:
                o.select_set(False)
            for o in objs:
                o.select_set(True)
            context.view_layer.objects.active = objs[0]
        except (RuntimeError, ReferenceError, AttributeError):
            pass
        _redraw()
        return {'FINISHED'}


class DESSIN_OT_title_cell_add(_LayoutOp, bpy.types.Operator):
    bl_idname = "dessin.title_cell_add"
    bl_label = "Add Cell"
    bl_description = ("Adds a cell to the title block. Column: the selected cell is split in two, the new one on its right. "
                      "Row: a new row under the row of the selected cell (Row Above: over it)")

    where: bpy.props.EnumProperty(name="Where", default='AFTER', options={'SKIP_SAVE'},
                                  items=(('AFTER', "After", "A cell of width 1 after the selected one, in the same row"),
                                         ('COLUMN', "Column", "Splits the selected cell in two: the new cell is on its right"),
                                         ('ROW', "Row", "A new row of one cell under the row of the selected cell"),
                                         ('ROW_ABOVE', "Row Above", "A new row of one cell over the row of the selected cell")))

    def execute(self, context):
        sc = context.scene
        with quiet():
            title_insert(sc.dessin_layout, self.where)
        _title_changed(sc)
        return {'FINISHED'}


class DESSIN_OT_title_cell_remove(_LayoutOp, bpy.types.Operator):
    bl_idname = "dessin.title_cell_remove"
    bl_label = "Remove Cell"
    bl_description = "Removes the selected cell of the title block (its row goes with it when it was alone in it)"

    def execute(self, context):
        sc = context.scene
        with quiet():
            ok = title_remove(sc.dessin_layout)
        if not ok:
            self.report({'INFO'}, "The title block keeps at least one cell (untick Title Block to hide it)")
            return {'CANCELLED'}
        _title_changed(sc)
        return {'FINISHED'}


def event_paper_point(context, event, dx=0):
    """Point du papier (mm) sous la souris ; None hors d'une vue 3D."""
    from bpy_extras.view3d_utils import region_2d_to_location_3d
    try:
        region = next((r for r in context.area.regions if r.type == 'WINDOW'), None)
        rv = context.area.spaces.active.region_3d
        if region is None:
            return None
        p = region_2d_to_location_3d(region, rv, (event.mouse_x - region.x + dx, event.mouse_y - region.y),
                                     Vector((0.0, 0.0, 0.0)))
        return Vector((p.x, p.y))
    except (AttributeError, TypeError, ValueError):
        return None


def title_edit_reset():
    """Plus personne ne modifie de cartouche (fichier ouvert, module désactivé)."""
    _TITLE_EDIT.update(scene=None, hover=None, drag=None, stop=False)


def title_editing():
    """True pendant qu'on modifie le cartouche sur la feuille (la commande vit encore : elle vient de recevoir la souris)."""
    return _TITLE_EDIT["scene"] is not None and time.monotonic() - _TITLE_EDIT.get("beat", 0.0) < 5.0


class DESSIN_OT_title_edit(bpy.types.Operator):
    bl_idname = "dessin.title_edit"
    bl_label = "Edit Title Block"
    bl_description = ("Layout: edits the title block directly on the sheet, like a table. Drag its free edge to stretch it, "
                      "drag a line between two cells or two rows to resize them, drag the block to another corner of the "
                      "frame. Click a cell to select it (double-click: its text); C adds a column, R a row, X deletes the "
                      "cell. Enter, Esc or a click elsewhere: done. A double-click on the title block starts it too")
    bl_options = {'REGISTER', 'UNDO'}

    pick: bpy.props.BoolProperty(default=False, options={'SKIP_SAVE', 'HIDDEN'})     # lancé par un double-clic sur le cartouche

    @classmethod
    def poll(cls, context):
        return is_layout(context.scene) and context.area is not None and context.area.type == 'VIEW_3D' and context.mode == 'OBJECT'

    def tol(self, context, event):
        """Distance de capture d'un trait : 6 pixels de l'écran, en mm de papier."""
        a, b = event_paper_point(context, event), event_paper_point(context, event, 20)
        if a is None or b is None:
            return 1.0
        return max(abs(b.x - a.x) / 20.0 * 6.0, 1e-6)

    def invoke(self, context, event):
        sc = context.scene
        L = sc.dessin_layout
        self.changed = False
        self.drag = None
        hit = None
        if self.pick:
            # double-clic : seulement sur le cartouche, et pas sur une barre ou un panneau (le clic garde alors son usage)
            if not L.show_title or event is None or title_editing() or double_click_blocked(context, event):
                return {'CANCELLED', 'PASS_THROUGH'}
            p = event_paper_point(context, event)
            hit = title_hit(L, p.x, p.y, self.tol(context, event)) if p is not None else None
            if hit is None:
                return {'CANCELLED', 'PASS_THROUGH'}
        elif title_editing():
            _TITLE_EDIT["stop"] = True           # le bouton du panneau, pressé une seconde fois : on a fini
            _redraw()
            return {'CANCELLED'}
        with quiet():
            if not L.show_title:
                L.show_title = True
                self.changed = True
            title_cells_ensure(L)
        if self.changed:
            _title_changed(sc)
        if hit is not None and hit[0] == 'C':
            L.title_cell_index = hit[1]
        _TITLE_EDIT.update(scene=sc.name, hover=None, drag=None, stop=False, beat=time.monotonic())
        context.window_manager.modal_handler_add(self)
        self.status(context)
        _redraw()
        return {'RUNNING_MODAL'}

    def status(self, context, done=False):
        try:
            context.workspace.status_text_set(None if done else (
                "Title block: drag a line to resize  ·  drag the block to another corner  ·  click a cell, double-click: its text"
                "  ·  C: add a column  ·  R: add a row  ·  X: delete the cell  ·  Enter, Esc or a click elsewhere: done"))
        except (AttributeError, RuntimeError):
            pass

    def cursor(self, context, hot):
        try:
            if hot is None:
                context.window.cursor_modal_restore()
            else:
                context.window.cursor_modal_set('MOVE_Y' if hot[0] == 'H' else 'MOVE_X')
        except (AttributeError, RuntimeError, TypeError):
            pass

    def leave(self, context):
        _TITLE_EDIT.update(scene=None, hover=None, drag=None, stop=False)
        self.drag = None
        self.cursor(context, None)
        self.status(context, True)
        _redraw()
        return {'FINISHED'} if self.changed else {'CANCELLED'}

    def cancel(self, context):
        _TITLE_EDIT.update(scene=None, hover=None, drag=None, stop=False)

    def touch(self, context, did):
        if did:
            self.changed = True
            _title_changed(context.scene)

    def drag_to(self, context, L, p):
        kind, idx, start = self.drag
        did = False
        with quiet():
            if kind == 'C':
                # la case glissée : le bloc va dans le coin du cadre le plus proche de l'endroit où on l'emmène
                d = p - start
                if L.title_pos in TITLE_CORNERS and d.length > 3.0:
                    x0, y0, x1, y1 = title_layout(L)[0]
                    pos = title_nearest_corner(L, (x0 + x1) / 2.0 + d.x, (y0 + y1) / 2.0 + d.y)
                    if pos != L.title_pos:
                        L.title_pos = pos
                        self.drag = (kind, idx, p.copy())
                        did = True
            else:
                did = title_drag(L, kind, idx, p.x, p.y)
        self.touch(context, did)

    def cell_dialog(self, context):
        try:
            bpy.ops.dessin.title_cell_edit('INVOKE_DEFAULT')
        except (RuntimeError, AttributeError, TypeError):
            pass

    def modal(self, context, event):
        try:
            return self.step(context, event)
        except (AttributeError, ReferenceError, RuntimeError, ValueError, TypeError, IndexError):
            return self.leave(context)

    def step(self, context, event):
        st = _TITLE_EDIT
        sc = context.scene
        st["beat"] = time.monotonic()
        if st.get("stop") or st["scene"] != sc.name or not is_layout(sc) or not sc.dessin_layout.show_title:
            return self.leave(context)
        L = sc.dessin_layout
        et, val = event.type, event.value
        if et in {'ESC', 'RET', 'NUMPAD_ENTER', 'RIGHTMOUSE'} and val == 'PRESS':
            return self.leave(context)
        if et in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE', 'TRACKPADPAN', 'TRACKPADZOOM', 'MOUSEROTATE', 'MOUSESMARTZOOM'}:
            return {'PASS_THROUGH'}
        if self.drag is None and double_click_blocked(context, event):
            if st["hover"] is not None:
                st["hover"] = None
                self.cursor(context, None)
                _redraw()
            return {'PASS_THROUGH'}          # les panneaux et les barres restent utilisables (texte d'une case, modèle...)
        p = event_paper_point(context, event)
        if p is None:
            return {'RUNNING_MODAL'}
        if et == 'MOUSEMOVE':
            if self.drag is not None:
                self.drag_to(context, L, p)
            else:
                hit = title_hit(L, p.x, p.y, self.tol(context, event))
                hot = hit if hit is not None and hit[0] != 'C' else None
                if hot != st["hover"]:
                    st["hover"] = hot
                    self.cursor(context, hot)
                    _redraw()
            return {'RUNNING_MODAL'}
        if et == 'LEFTMOUSE' and val in {'PRESS', 'DOUBLE_CLICK'}:
            tol = self.tol(context, event)
            hit = title_hit(L, p.x, p.y, tol)
            if hit is None:
                x0, y0, x1, y1 = title_layout(L)[0]
                if x0 - 3.0 * tol <= p.x <= x1 + 3.0 * tol and y0 - 3.0 * tol <= p.y <= y1 + 3.0 * tol:
                    return {'RUNNING_MODAL'}             # (clic manqué de peu : on reste dans le cartouche)
                return self.leave(context) | {'PASS_THROUGH'}       # clic ailleurs : fini, et le clic garde son usage
            if hit[0] == 'C':
                L.title_cell_index = hit[1]
                if val == 'DOUBLE_CLICK':
                    self.cell_dialog(context)
                else:
                    self.drag = ('C', hit[1], p.copy())
            else:
                self.drag = (hit[0], hit[1], p.copy())
                st["drag"] = hit
            _redraw()
            return {'RUNNING_MODAL'}
        if et == 'LEFTMOUSE' and val == 'RELEASE':
            if self.drag is not None:
                self.drag_to(context, L, p)
                self.drag = None
                st["drag"] = None
                _redraw()
            return {'RUNNING_MODAL'}
        if val == 'PRESS' and self.drag is None and not (event.ctrl or event.alt or event.oskey):
            did = False
            with quiet():
                if et == 'C':
                    title_insert(L, 'COLUMN')
                    did = True
                elif et == 'R':
                    title_insert(L, 'ROW_ABOVE' if event.shift else 'ROW')
                    did = True
                elif et in {'X', 'DEL', 'BACK_SPACE'}:
                    did = title_remove(L)
                    if not did:
                        self.report({'INFO'}, "The title block keeps at least one cell (untick Title Block to hide it)")
                elif et == 'TAB' and len(L.title_cells):
                    L.title_cell_index = (L.title_cell_index + (-1 if event.shift else 1)) % len(L.title_cells)
                    _redraw()
            self.touch(context, did)
        return {'RUNNING_MODAL'}


class DESSIN_OT_title_cell_edit(_LayoutOp, bpy.types.Operator):
    bl_idname = "dessin.title_cell_edit"
    bl_label = "Title Block Cell"
    bl_description = "Caption, text and text height of the selected cell of the title block (double-click on a cell while editing the title block)"

    index: bpy.props.IntProperty(default=-1, options={'SKIP_SAVE', 'HIDDEN'})
    kind: bpy.props.EnumProperty(name="Content", default='TEXT',
                                 items=(('TEXT', "Text", "A caption and a text"), ('LOGO', "Logo", "The logo image, fitted in the cell")))
    label: bpy.props.StringProperty(name="Caption", default="", description="Small caption written in the top left corner of the cell")
    text: bpy.props.StringProperty(name="Text", default="",
                                   description="Text of the cell. Fields are replaced automatically: <Project> <Title> <DrawnBy> <Date> "
                                               "<Sheet> <Sheets> <Rev> <Scale> <Format> <Layout> <File> <Today>")
    size: bpy.props.FloatProperty(name="Text height", default=3.5, min=1.0, max=40.0, precision=1)
    align: bpy.props.EnumProperty(name="Align", default='LEFT', items=(('LEFT', "Left", ""), ('CENTER', "Center", ""), ('RIGHT', "Right", "")))

    def cell(self, context):
        L = context.scene.dessin_layout
        i = self.index if self.index >= 0 else L.title_cell_index
        return L.title_cells[i] if 0 <= i < len(L.title_cells) else None

    def invoke(self, context, event):
        with quiet():
            title_cells_ensure(context.scene.dessin_layout)
        c = self.cell(context)
        if c is None:
            return {'CANCELLED'}
        self.kind, self.label, self.text, self.size, self.align = c.kind, c.label, c.text, c.size, c.align
        return context.window_manager.invoke_props_dialog(self, width=380)

    def draw(self, context):
        col = self.layout.column(align=True)
        col.use_property_split = True
        col.use_property_decorate = False
        col.prop(self, "kind")
        col.prop(self, "label")
        if self.kind == 'TEXT':
            col.prop(self, "text")
            col.prop(self, "size")
            col.prop(self, "align")
            self.layout.label(text="Automatic fields: <Project> <Title> <DrawnBy> <Date> <Sheet> <Sheets>")
            self.layout.label(text="<Rev> <Scale> <Format> <Layout> <File> <Today>")

    def execute(self, context):
        sc = context.scene
        with quiet():
            title_cells_ensure(sc.dessin_layout)
            c = self.cell(context)
            if c is None:
                return {'CANCELLED'}
            c.kind, c.label, c.text, c.size, c.align = self.kind, self.label, self.text, self.size, self.align
        _title_changed(sc)
        return {'FINISHED'}


class DESSIN_OT_title_cell_move(_LayoutOp, bpy.types.Operator):
    bl_idname = "dessin.title_cell_move"
    bl_label = "Move Cell"
    bl_description = "Moves the selected cell before or after its neighbor (cells are read from left to right, row after row)"

    up: bpy.props.BoolProperty(default=True)

    def execute(self, context):
        sc = context.scene
        L = sc.dessin_layout
        i = L.title_cell_index
        j = i - 1 if self.up else i + 1
        if not (0 <= i < len(L.title_cells) and 0 <= j < len(L.title_cells)):
            return {'CANCELLED'}
        with quiet():
            a, b = L.title_cells[i].new_row, L.title_cells[j].new_row
            L.title_cells.move(i, j)
            L.title_cells[j].new_row, L.title_cells[i].new_row = b, a      # (les débuts de rangée restent à leur place)
            L.title_cell_index = j
        _title_changed(sc)
        return {'FINISHED'}


class DESSIN_OT_title_cell_field(_LayoutOp, bpy.types.Operator):
    bl_idname = "dessin.title_cell_field"
    bl_label = "Insert Field"
    bl_description = "Adds an automatic field to the text of the selected cell: it is filled in and kept up to date by itself"

    field: bpy.props.StringProperty(default="Scale")

    def execute(self, context):
        sc = context.scene
        L = sc.dessin_layout
        if not (0 <= L.title_cell_index < len(L.title_cells)):
            return {'CANCELLED'}
        c = L.title_cells[L.title_cell_index]
        with quiet():
            c.text = (c.text + " " if c.text.strip() else "") + f"<{self.field}>"
        _title_changed(sc)
        return {'FINISHED'}


class DESSIN_MT_title_fields(bpy.types.Menu):
    bl_idname = "DESSIN_MT_title_fields"
    bl_label = "Insert Field"

    def draw(self, context):
        for key, tip in SHEET_FIELDS:
            self.layout.operator(DESSIN_OT_title_cell_field.bl_idname, text=f"<{key}>   {tip}").field = key


class DESSIN_OT_title_copy_all(_LayoutOp, bpy.types.Operator):
    bl_idname = "dessin.title_copy_all"
    bl_label = "Copy to All Layouts"
    bl_description = ("Gives every layout of the file the title block of this one: template, cells, logo, project and author, "
                      "or the free title block drawn by hand. Each sheet keeps its own title, number and revision")

    def execute(self, context):
        src = context.scene
        n = 0
        for sc in layouts():
            if sc == src:
                continue
            with quiet():
                title_copy(src, sc)
                sc.dessin_layout.show_title = src.dessin_layout.show_title
            paper_rebuild(sc)
            n += 1
        _redraw()
        self.report({'INFO'}, f"Title block copied to {n} layout(s)")
        return {'FINISHED'}


class DESSIN_UL_title_cells(bpy.types.UIList):
    bl_idname = "DESSIN_UL_title_cells"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index=0):
        row = layout.row(align=True)
        row.label(text="", icon='TRIA_RIGHT' if (item.new_row or index == 0) else 'BLANK1')
        if item.kind == 'LOGO':
            row.label(text="Logo", icon='IMAGE_DATA')
        else:
            row.prop(item, "label", text="", emboss=False)
            row.prop(item, "text", text="", emboss=False)


# --------------------------------------------------------------------------
# Opérateurs : objets posés sur la feuille (image, champ, flèche du nord)
# --------------------------------------------------------------------------

def sheet_drop_point(context):
    """Point de la feuille où poser un nouvel objet : le milieu de ce que la vue montre, ramené sur le papier."""
    w, h = paper_size(context.scene.dessin_layout)
    x, y = w / 2.0, h / 2.0
    try:
        rv = context.space_data.region_3d
        x, y = float(rv.view_location.x), float(rv.view_location.y)
    except (AttributeError, TypeError):
        pass
    return min(max(x, 0.0), w), min(max(y, 0.0), h)


def sheet_place(context, o, collection='annot'):
    """Range un objet neuf sur la feuille et le sélectionne seul (le Gumball apparaît dessus)."""
    sc = context.scene
    layout_collection(sc, collection).objects.link(o)
    try:
        for x in context.selected_objects:
            x.select_set(False)
        o.select_set(True)
        context.view_layer.objects.active = o
    except (RuntimeError, ReferenceError, AttributeError):
        pass
    _redraw()


class DESSIN_OT_sheet_image(_LayoutOp, bpy.types.Operator):
    bl_idname = "dessin.sheet_image"
    bl_label = "Insert Image"
    bl_description = ("Layout: places an image on the sheet (a logo, a photo, a render). Move and resize it like any object; "
                      "it is exported in the PDF and the SVG")

    filepath: bpy.props.StringProperty(subtype='FILE_PATH', options={'SKIP_SAVE'})
    filter_glob: bpy.props.StringProperty(default=IMAGE_GLOB, options={'HIDDEN'})
    width: bpy.props.FloatProperty(name="Width (mm)", default=60.0, min=1.0, soft_max=1000.0,
                                   description="Width of the image on the sheet, in millimeters")
    x: bpy.props.FloatProperty(options={'HIDDEN', 'SKIP_SAVE'}, default=-1.0)
    y: bpy.props.FloatProperty(options={'HIDDEN', 'SKIP_SAVE'}, default=-1.0)

    def invoke(self, context, event):
        self.x, self.y = sheet_drop_point(context)
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        img = image_load(self.filepath)
        if img is None or not img.size[0] or not img.size[1]:
            self.report({'WARNING'}, "Insert Image: this file is not an image Blender can read")
            return {'CANCELLED'}
        if self.x < 0.0 or self.y < 0.0:
            self.x, self.y = sheet_drop_point(context)
        iw, ih = img.size
        o = image_empty(os.path.splitext(os.path.basename(self.filepath))[0] or "Image", img, self.x, self.y,
                        self.width * max(iw, ih) / float(iw))
        o["wd_image"] = 1
        sheet_place(context, o)
        self.report({'INFO'}, f"Image placed: {self.width:g} x {self.width * ih / iw:.1f} mm (move and resize it with the Gumball)")
        return {'FINISHED'}


SHEET_FIELD_ITEMS = tuple((k, f"<{k}>", tip) for k, tip in SHEET_FIELDS) + (
    ('SheetOf', "<Sheet> / <Sheets>", "Sheet number over the number of sheets: 02 / 05"),)


class DESSIN_OT_sheet_field(_LayoutOp, bpy.types.Operator):
    bl_idname = "dessin.sheet_field"
    bl_label = "Insert Field"
    bl_description = ("Layout: places a text that fills itself in and stays up to date (scale, sheet number, date, project...), "
                      "to build your own title block. Any text you type with <Scale>, <Sheet>... in it does the same")

    field: bpy.props.EnumProperty(name="Field", items=SHEET_FIELD_ITEMS, default='Scale')

    def execute(self, context):
        sc = context.scene
        fc = bpy.data.curves.new("Field", 'FONT')
        fc.body = "<Sheet> / <Sheets>" if self.field == 'SheetOf' else f"<{self.field}>"
        try:
            fc.size = max(float(sc.dessin.taille_texte), 1.0)
        except (AttributeError, TypeError):
            fc.size = 2.5
        fc.align_x = 'LEFT'
        fc.align_y = 'BOTTOM_BASELINE'
        o = bpy.data.objects.new("Field " + self.field, fc)
        o["dessin_text"] = True
        o.color = (0.0, 0.0, 0.0, 1.0)
        x, y = sheet_drop_point(context)
        o.location = (x, y, 0.0)
        sheet_place(context, o)
        fields_refresh(sc)
        return {'FINISHED'}


def north_arrow_paths(r):
    """Flèche du nord : un cercle, une pointe en losange vers le haut et la lettre N au-dessus (rayon r, en mm)."""
    circle = [(r * math.cos(t), r * math.sin(t)) for t in np.linspace(0.0, 2.0 * math.pi, 49)[:-1]]
    kite = [(0.0, r), (-r * 0.32, -r * 0.62), (0.0, -r * 0.3), (r * 0.32, -r * 0.62)]
    half = [(0.0, r), (0.0, -r * 0.3)]
    n0, n1, nw = r * 1.25, r * 1.85, r * 0.22
    letter = [(-nw, n0), (-nw, n1), (nw, n0), (nw, n1)]
    return [(circle, True), (kite, True), (half, False), (letter, False)]


class DESSIN_OT_sheet_north(_LayoutOp, bpy.types.Operator):
    bl_idname = "dessin.sheet_north"
    bl_label = "North Arrow"
    bl_description = "Layout: places a north arrow on the sheet. Turn it with the Gumball so that it points to the north of your plan"

    size: bpy.props.FloatProperty(name="Diameter (mm)", default=14.0, min=4.0, soft_max=60.0)

    def execute(self, context):
        cu = _new_curve("North arrow", north_arrow_paths(self.size / 2.0))
        o = bpy.data.objects.new("North arrow", cu)
        o.color = (0.0, 0.0, 0.0, 1.0)
        x, y = sheet_drop_point(context)
        o.location = (x, y, 0.0)
        sheet_place(context, o)
        return {'FINISHED'}


# --------------------------------------------------------------------------
# Vue de détail agrandie (comme VIEWDETAIL d'AutoCAD)
# --------------------------------------------------------------------------

def callout_scale(den):
    """Échelle d'une vue de détail tirée d'une fenêtre au 1:den : la plus proche échelle normalisée au moins deux fois
    plus grande."""
    cands = [d for _k, _n, d in le.SCALES if d <= den / 2.0 + 1e-9]
    return max(cands) if cands else den / 2.0


def callout_next_tag(scene):
    used = {o.dessin_detail.callout_tag.strip().upper() for o in details(scene) if o.dessin_detail.callout_of}
    for ch in "ABCDEFGHJKLMNPQRSTUVWXYZ":
        if ch not in used:
            return ch
    return str(len(used) + 1)


def callout_create(scene, parent, mx, my, w, h, px, py):
    """Vue de détail : la zone w x h (mm de papier) centrée en (mx, my) sur le détail `parent`, agrandie et posée en
    (px, py). Retourne le nouveau détail, ou None."""
    pd = parent.dessin_detail
    mp = detail_map(parent)
    if mp is None or pd.persp:
        return None
    uv = _map_uv(mp, (mx, my))
    proj = detail_projector(pd)
    center = Vector(pd.center) + proj.right * (uv[0] - mp[2]) + proj.up * (uv[1] - mp[3])
    den = callout_scale(pd.scale)
    k = pd.scale / den
    tag = callout_next_tag(scene)
    obj = detail_create(scene, px, py, max(w * k, 4.0), max(h * k, 4.0), pd.view, scale=den, fit=False,
                        name=f"Detail {tag}")
    d = obj.dessin_detail
    with quiet():
        for key in ("model", "rot", "cam_dist", "view_label", "display", "show_annotations", "tangent_edges", "sharp_angle",
                    "hidden_layers"):
            setattr(d, key, getattr(pd, key))
        d.center = center
        d.callout_of = detail_id(parent)
        d.callout_tag = tag
    detail_rebuild(obj, force=True)
    detail_dress_refresh(parent)                 # le repère (zone et lettre) apparaît sur la fenêtre d'origine
    scene["wd_dress"] = dress_signature(scene)
    title_refresh(scene)
    return obj


class DESSIN_OT_detail_callout(DessinBase):
    bl_idname = "dessin.detail_callout"
    bl_label = "Detail View"
    bl_description = ("Layout: an enlarged view of a part of a viewport, like VIEWDETAIL in AutoCAD. Draw a rectangle around the "
                      "part (two corners, inside a viewport), then click where the detail view goes. The part is marked with a "
                      "letter on the original viewport, and the mark follows the detail view")

    TITLE = "Detail View"
    PROP = ()
    NEEDED = 3
    NUMFIELDS = 0
    HAS_CENTER = False
    EDIT_OK = False

    def invoke(self, context, event):
        if not is_layout(context.scene):
            if event is not None and event.type == 'MOUSEMOVE':
                return {'CANCELLED', 'PASS_THROUGH'}
            self.report({'WARNING'}, "Detail View: open a layout first (the tabs under the view)")
            return {'CANCELLED'}
        return DessinBase.invoke(self, context, event)

    def prompt(self):
        if not self.points:
            return "first corner of the part to enlarge (inside a viewport)"
        if len(self.points) == 1:
            return "opposite corner of the part"
        return "position of the detail view"

    @staticmethod
    def _rect(a, b):
        return [Vector((a.x, a.y, 0.0)), Vector((b.x, a.y, 0.0)), Vector((b.x, b.y, 0.0)), Vector((a.x, b.y, 0.0))]

    def compute(self):
        if not self.points or self.cur is None:
            return [], [], "", None
        a = self.points[0]
        if len(self.points) == 1:
            c = self._rect(a, self.cur)
            w, h = abs(self.cur.x - a.x), abs(self.cur.y - a.y)
            return c + [c[0]], [], f"Part {w:.1f} x {h:.1f} mm", None
        b = self.points[1]
        region = self._rect(a, b)
        w, h = abs(b.x - a.x), abs(b.y - a.y)
        k, info = 2.0, ""
        try:
            parent = detail_at(bpy.context.scene, (a.x + b.x) / 2.0, (a.y + b.y) / 2.0)
            if parent is not None and not parent.dessin_detail.persp:
                den = callout_scale(parent.dessin_detail.scale)
                k = parent.dessin_detail.scale / den
                info = f"Detail view at {le.fmt_scale(den)}"
            else:
                info = "The part must be inside a viewport"
        except (AttributeError, ReferenceError):
            pass
        p = self.cur
        hw, hh = w * k / 2.0, h * k / 2.0
        c = self._rect(Vector((p.x - hw, p.y - hh, 0.0)), Vector((p.x + hw, p.y + hh, 0.0)))
        return c + [c[0]], [region + [region[0]]], info, ("callout", a.copy(), b.copy(), p.copy())

    def build(self, context, spec):
        if spec[0] != 'callout':
            return None
        _t, a, b, p = spec
        sc = context.scene
        w, h = abs(b.x - a.x), abs(b.y - a.y)
        if w < 1.0 or h < 1.0:
            self.report({'WARNING'}, "Detail View: the part is too small")
            return None
        mx, my = (a.x + b.x) / 2.0, (a.y + b.y) / 2.0
        parent = detail_at(sc, mx, my)
        if parent is None or parent.dessin_detail.persp:
            self.report({'WARNING'}, "Detail View: draw the rectangle inside a viewport (not a perspective one)")
            return None
        obj = callout_create(sc, parent, mx, my, w, h, p.x, p.y)
        if obj is None:
            return None
        try:
            for o in context.selected_objects:
                o.select_set(False)
            obj.select_set(True)
            context.view_layer.objects.active = obj
        except (RuntimeError, ReferenceError):
            pass
        d = obj.dessin_detail
        self.report({'INFO'}, f"Detail {d.callout_tag}: {le.fmt_scale(d.scale)} (from {le.fmt_scale(parent.dessin_detail.scale)})")
        return obj

    def after_finish(self, context):
        if getattr(self, "tool_id", None):
            try:
                idle_tool()
            except (RuntimeError, TypeError):
                pass


# --------------------------------------------------------------------------
# Panneaux
# --------------------------------------------------------------------------

class DESSIN_PT_layout_title(bpy.types.Panel):
    bl_label = "Title Block"
    bl_idname = "DESSIN_PT_layout_title"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Layout"
    bl_order = 2
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return is_layout(context.scene)

    def draw_header(self, context):
        if is_layout(context.scene):
            self.layout.prop(context.scene.dessin_layout, "show_title", text="")

    def draw(self, context):
        lay = self.layout
        sc = context.scene
        if not is_layout(sc):
            return
        L = sc.dessin_layout
        free = title_free_objects(sc)
        if free:
            # cartouche libre : dessiné à la main sur le calque « Title block », retouché avec les outils habituels
            box = lay.box()
            col = box.column(align=True)
            col.label(text=f"Free title block: {len(free)} objects", icon='GREASEPENCIL')
            col.label(text="Layer 'Title block': edit it with the usual tools")
            col = box.column(align=True)
            col.operator(DESSIN_OT_title_free_select.bl_idname, icon='RESTRICT_SELECT_OFF')
            col.operator(DESSIN_OT_title_copy_all.bl_idname, icon='DUPLICATE')
            col.operator_menu_enum(DESSIN_OT_title_preset.bl_idname, "preset", text="Back to a Template", icon='PRESET')
            col = lay.column(align=True)
            col.use_property_split = True
            col.use_property_decorate = False
            col.label(text="Values of the fields")
            for key in ("t_project", "t_title", "t_author", "t_date", "t_number", "t_revision", "t_scale"):
                col.prop(L, key)
            return
        editing = title_editing() and _TITLE_EDIT["scene"] == sc.name
        col = lay.column(align=True)
        col.operator(DESSIN_OT_title_edit.bl_idname, text="Done" if editing else "Edit on the Sheet",
                     icon='CHECKMARK' if editing else 'GREASEPENCIL', depress=editing)
        col.operator_menu_enum(DESSIN_OT_title_preset.bl_idname, "preset", text="Template", icon='PRESET')
        body = lay.column()
        body.active = L.show_title
        col = body.column(align=True)
        col.use_property_split = True
        col.use_property_decorate = False
        col.prop(L, "title_pos")
        if L.title_pos != 'BOTTOM':
            col.prop(L, "title_w")
        col = body.column(align=True)
        col.use_property_split = True
        col.use_property_decorate = False
        col.prop(L, "t_project")
        col.prop(L, "t_title")
        col.prop(L, "t_author")
        col.prop(L, "t_date")
        col.prop(L, "t_number")
        col.prop(L, "t_revision")
        col.prop(L, "t_scale")
        col.prop(L, "t_logo")
        body.label(text="Cells (left to right, row after row)")
        if not len(L.title_cells):
            body.operator(DESSIN_OT_title_preset.bl_idname, text="Edit the Cells", icon='GREASEPENCIL').preset = 'CLASSIC'
        else:
            row = body.row()
            row.template_list(DESSIN_UL_title_cells.bl_idname, "", L, "title_cells", L, "title_cell_index", rows=5)
            col = row.column(align=True)
            col.operator(DESSIN_OT_title_cell_remove.bl_idname, text="", icon='REMOVE')
            col.separator()
            col.operator(DESSIN_OT_title_cell_move.bl_idname, text="", icon='TRIA_UP').up = True
            col.operator(DESSIN_OT_title_cell_move.bl_idname, text="", icon='TRIA_DOWN').up = False
            row = body.row(align=True)
            row.operator(DESSIN_OT_title_cell_add.bl_idname, text="Column", icon='ADD').where = 'COLUMN'
            row.operator(DESSIN_OT_title_cell_add.bl_idname, text="Row", icon='ADD').where = 'ROW'
            if 0 <= L.title_cell_index < len(L.title_cells):
                c = L.title_cells[L.title_cell_index]
                box = body.box()
                col = box.column(align=True)
                col.use_property_split = True
                col.use_property_decorate = False
                col.prop(c, "kind")
                col.prop(c, "label")
                if c.kind == 'TEXT':
                    row = col.row(align=True)
                    row.prop(c, "text")
                    row.menu(DESSIN_MT_title_fields.bl_idname, text="", icon='DOWNARROW_HLT')
                    col.prop(c, "size")
                    col.prop(c, "align")
                col = box.column(align=True)
                col.use_property_split = True
                col.use_property_decorate = False
                col.prop(c, "new_row")
                col.prop(c, "width")
                col.prop(c, "height")
        col = lay.column(align=True)
        col.operator(DESSIN_OT_title_copy_all.bl_idname, icon='DUPLICATE')
        col.operator(DESSIN_OT_title_explode.bl_idname, icon='MOD_EXPLODE')


SHEET_ANNOTATE_OPS = (
    ("Text", "dessin.text"), ("Leader", "dessin.annotation"),
    ("Dimension", "dessin.cotation"), ("Continue", "dessin.cotation_chain"),
    ("Angle", "dessin.cotation_angle"), ("Radius", "dessin.cotation_rayon"),
    ("Line", "dessin.polyligne"), ("Rectangle", "dessin.rectangle"),
    ("Circle", "dessin.cercle"), ("Hatch", "dessin.hatch"),
)


class DESSIN_PT_layout_annotate(bpy.types.Panel):
    bl_label = "Annotate"
    bl_idname = "DESSIN_PT_layout_annotate"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Layout"
    bl_order = 3

    @classmethod
    def poll(cls, context):
        return is_layout(context.scene)

    def draw(self, context):
        lay = self.layout
        sc = context.scene
        if not is_layout(sc):
            return
        lay.label(text="Drawn on the sheet, in millimeters:")
        grid = lay.grid_flow(row_major=True, columns=2, even_columns=True, even_rows=True, align=True)
        for text, op in SHEET_ANNOTATE_OPS:
            grid.operator(op, text=text)
        col = lay.column(align=True)
        col.operator(DESSIN_OT_sheet_image.bl_idname, text="Image...", icon='IMAGE_DATA')
        col.operator_menu_enum(DESSIN_OT_sheet_field.bl_idname, "field", text="Field (automatic text)", icon='SORTALPHA')
        col.operator(DESSIN_OT_sheet_north.bl_idname, icon='ORIENTATION_GIMBAL')
        try:
            col = lay.column(align=True)
            col.use_property_split = True
            col.use_property_decorate = False
            col.prop(sc.dessin, "taille_texte", text="Text height (mm)")
        except (AttributeError, TypeError):
            pass


SHEET_CLASSES = (
    DESSIN_OT_title_preset, DESSIN_OT_title_explode, DESSIN_OT_title_free_select, DESSIN_OT_title_edit, DESSIN_OT_title_cell_edit,
    DESSIN_OT_title_cell_add, DESSIN_OT_title_cell_remove, DESSIN_OT_title_cell_move,
    DESSIN_OT_title_cell_field, DESSIN_MT_title_fields, DESSIN_OT_title_copy_all, DESSIN_UL_title_cells,
    DESSIN_OT_sheet_image, DESSIN_OT_sheet_field, DESSIN_OT_sheet_north, DESSIN_OT_detail_callout,
    DESSIN_PT_layout_title, DESSIN_PT_layout_annotate,
)


def _late_imports():
    """Noms définis dans des modules chargés après celui-ci : ils ne servent qu'à l'exécution des outils."""
    pass
