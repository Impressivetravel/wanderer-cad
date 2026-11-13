"""Wanderer CAD : Layout — mises en page (espace papier), vues de détail à l'échelle, cartouche, export PDF / SVG / DXF."""

import bpy
import gpu
import json
import math
import os
import random
import time
import numpy as np
from bpy.app.handlers import persistent
from gpu_extras.batch import batch_for_shader
from mathutils import Euler, Matrix, Quaternion, Vector

from . import layout_engine as le
from .core import cp_set, cp_state, idle_tool, lang
from .base import DessinBase
from .drawing import find_window_region, get_shader, px_scale
from .tools_draw import DESSIN_OT_rectangle


# --------------------------------------------------------------------------
# Principe
# --------------------------------------------------------------------------
# Une mise en page est une scène dont l'unité est le millimètre de papier (1 unité = 1 mm, origine en bas à gauche de la
# feuille). Un détail est un rectangle (courbe) posé sur la feuille : il montre le modèle selon une vue et une échelle ;
# ses traits sont des objets enfants générés, découpés à son cadre. Tout ce que l'on dessine d'autre dans la scène
# (lignes, textes, cotes, hachures des outils habituels) est de l'annotation en espace papier.

GEN = "wd_gen"                   # objet généré d'un détail (valeur : rôle) ; le cadre du détail porte 'detail'
SHEET = "wd_layout_gen"          # objet généré de la feuille (papier, cadre, cartouche)
COL = "wd_layout_col"            # collection d'une mise en page (valeur : 'sheet', 'details', 'annot', 'dims')
Z_PAPER = -0.5
Z_FILL = -0.05
ISO_TILT = math.acos(1.0 / math.sqrt(3.0))
ISO_TURN = {'ISO_SE': 45.0, 'ISO_SW': -45.0, 'ISO_NE': 135.0, 'ISO_NW': -135.0}

_STATE = {"busy": False, "views": {}, "model_ver": {}, "built": {}, "cache": {}, "last_model": {}, "paper": set(), "items": None,
          "hold": 0.0, "active_vp": None}
# hold : heure du dernier Annuler / Rétablir. Tant que rien d'autre n'a changé, le minuteur ne retouche pas la mise en page :
# l'état affiché est celui d'un pas de l'historique, et Annuler / Rétablir continuent de le parcourir normalement
# views : état de chaque vue 3D avant la mise en page (rendu au retour) ; paper : vues 3D actuellement en espace papier
# active_vp : nom de la fenêtre dans laquelle on travaille (double-clic dedans, comme l'espace objet d'AutoCAD) ; None sinon

PAPER_ITEMS = [(k, n, "") for k, n, _w, _h in le.PAPERS] + [('CUSTOM', "Custom", "Width and height typed below")]
SCALE_ITEMS = [(k, n, "") for k, n, _d in le.SCALES] + [('CUSTOM', "Custom", "Scale typed below")]
VIEW_ITEMS = (
    ('TOP', "Top", ""), ('FRONT', "Front", ""), ('RIGHT', "Right", ""), ('LEFT', "Left", ""), ('BACK', "Back", ""),
    ('BOTTOM', "Bottom", ""),
    ('ISO_SW', "Isometric SW", "Isometric view from the south-west"), ('ISO_SE', "Isometric SE", "Isometric view from the south-east"),
    ('ISO_NE', "Isometric NE", "Isometric view from the north-east"), ('ISO_NW', "Isometric NW", "Isometric view from the north-west"),
    ('CUSTOM', "Model view", "A view copied from the model: the current 3D view or a named view"),
)
VIEW_LABELS = {k: n for k, n, _d in VIEW_ITEMS}
DISPLAY_ITEMS = (
    ('WIREFRAME', "Wireframe", "Every edge of the model, nothing hidden (fastest)"),
    ('HIDDEN', "Hidden", "Only what is visible from this view"),
    ('HIDDEN_DASHED', "Hidden, dashed", "What is visible, plus the hidden edges as dashed lines"),
)


class quiet:
    """Suspend les fonctions update des propriétés pendant qu'on les modifie par programme."""

    def __enter__(self):
        self.prev = _STATE["busy"]
        _STATE["busy"] = True

    def __exit__(self, *a):
        _STATE["busy"] = self.prev


# --------------------------------------------------------------------------
# Accès aux données
# --------------------------------------------------------------------------

def is_layout(scene):
    try:
        return bool(scene.dessin_layout.is_layout)
    except (AttributeError, ReferenceError):
        return False


def layouts():
    """Mises en page du fichier, dans l'ordre des onglets."""
    try:
        out = [s for s in bpy.data.scenes if is_layout(s)]
    except (AttributeError, RuntimeError):
        return []
    out.sort(key=lambda s: (s.dessin_layout.order, s.name))
    return out


def layout_model(scene):
    """Scène du modèle montrée par une mise en page (celle d'origine, sinon la première scène qui n'est pas une mise en page)."""
    try:
        m = scene.dessin_layout.model
        if m is not None and not is_layout(m) and m.name in bpy.data.scenes:
            return m
    except (AttributeError, ReferenceError):
        pass
    return next((s for s in bpy.data.scenes if not is_layout(s)), None)


def model_of(scene):
    """La scène elle-même, ou le modèle d'une mise en page."""
    return layout_model(scene) if is_layout(scene) else scene


def paper_size(L):
    """(largeur, hauteur) de la feuille en mm, orientation comprise."""
    if L.paper == 'CUSTOM':
        w, h = max(L.custom_w, 10.0), max(L.custom_h, 10.0)
        return (max(w, h), min(w, h)) if L.orientation == 'LANDSCAPE' else (min(w, h), max(w, h))
    w, h = le.PAPER_SIZE[L.paper]
    return (w, h) if L.orientation == 'LANDSCAPE' else (h, w)


def paper_label(L):
    name = next((n.split(" (")[0].split(" /")[0] for k, n, _w, _h in le.PAPERS if k == L.paper), None)
    w, h = paper_size(L)
    return name or ("%g x %g mm" % (w, h))


def mm_per_unit(scene):
    """Millimètres réels par unité Blender d'une scène de modèle."""
    us = scene.unit_settings
    if us.system == 'NONE':
        return 1000.0
    return (us.scale_length or 1.0) * 1000.0


def frame_rect(L):
    w, h = paper_size(L)
    m = min(max(L.margin, 0.0), min(w, h) * 0.4)
    return m, m, w - m, h - m


def is_detail(obj):
    try:
        return obj is not None and obj.type == 'CURVE' and bool(obj.dessin_detail.is_detail)
    except (AttributeError, ReferenceError):
        return False


def details(scene):
    return [o for o in scene.objects if is_detail(o)]


def detail_children(obj, role=None):
    return [c for c in obj.children if c.get(GEN) and (role is None or c.get(GEN) == role)]


def obj_scene(obj):
    try:
        us = obj.users_scene
        return us[0] if us else None
    except (AttributeError, ReferenceError):
        return None


def detail_model(obj):
    d = obj.dessin_detail
    try:
        if d.model is not None and not is_layout(d.model) and d.model.name in bpy.data.scenes:
            return d.model
    except (AttributeError, ReferenceError):
        pass
    sc = obj_scene(obj)
    return layout_model(sc) if sc is not None else None


def detail_quat(d):
    if d.view in ISO_TURN:
        return Euler((ISO_TILT, 0.0, math.radians(ISO_TURN[d.view])), 'XYZ').to_quaternion()
    if d.view == 'CUSTOM':
        q = Quaternion(d.rot)
        return q.normalized() if q.magnitude > 1e-9 else Quaternion((1.0, 0.0, 0.0, 0.0))
    return _axis_quat(d.view)


def detail_hidden(d):
    return [n for n in d.hidden_layers.split("\n") if n]


def detail_caption(d):
    if d.label.strip():
        return d.label.strip()
    if d.view == 'CUSTOM':
        return d.view_label.strip() or ("Perspective" if d.persp else "View")
    name = VIEW_LABELS.get(d.view, d.view)
    if d.view in ISO_TURN:
        name = "Isometric"
    return _tr(name)


def _tr(text):
    """Texte écrit sur la feuille, dans la langue du module."""
    if lang() != 'FR':
        return text
    return {"Top": "Dessus", "Front": "Face", "Right": "Droite", "Left": "Gauche", "Back": "Arrière", "Bottom": "Dessous",
            "Isometric": "Isométrie", "View": "Vue", "Perspective": "Perspective", "PROJECT": "PROJET", "TITLE": "TITRE",
            "DRAWN BY": "DESSINÉ PAR", "DATE": "DATE", "SCALE": "ÉCHELLE", "SHEET": "PLANCHE", "REV": "IND.",
            "FORMAT": "FORMAT", "As noted": "Voir vues", "landscape": "paysage", "portrait": "portrait"}.get(text, text)


def layout_collection(scene, key, create=True):
    """Collection (calque) d'une mise en page : 'sheet' (feuille), 'details', 'annot' (annotations), 'dims' (cotes)."""
    for c in scene.collection.children:
        if c.get(COL) == key:
            return c
    if not create:
        return None
    name = {"sheet": "Sheet", "details": "Viewports", "annot": "Annotations", "dims": "Layout dimensions"}[key]
    c = bpy.data.collections.new(name)
    c[COL] = key
    scene.collection.children.link(c)
    return c


def layout_dims_collection(scene, create=True):
    """Cotes posées sur une mise en page : jamais la collection « Dimensions » du modèle (elle serait partagée)."""
    return layout_collection(scene, 'dims', create)


def _remove(objs):
    for o in list(objs):
        try:
            data = o.data
            bpy.data.objects.remove(o, do_unlink=True)
            if data is not None and data.users == 0:
                if isinstance(data, bpy.types.Mesh):
                    bpy.data.meshes.remove(data)
                elif isinstance(data, bpy.types.Curve):
                    bpy.data.curves.remove(data)
        except (ReferenceError, RuntimeError):
            pass


def shown_color(color):
    """Couleur à l'écran sur le papier blanc : le blanc (objets sans couleur de calque) devient noir."""
    r, g, b = color[:3]
    if min(r, g, b) > 0.9:
        return (0.0, 0.0, 0.0)
    return (r, g, b)


def print_color(color, mode):
    return (0.0, 0.0, 0.0) if mode == 'BLACK' else shown_color(color)


def _new_curve(name, paths, z=0.0):
    """Courbe à splines POLY à partir de [(points 2D, fermé)]."""
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    cu.resolution_u = 1
    for P, closed in paths:
        P = np.asarray(P, dtype=np.float64)
        if len(P) < 2:
            continue
        sp = cu.splines.new('POLY')
        sp.points.add(len(P) - 1)
        co = np.zeros((len(P), 4))
        co[:, 0:2] = P[:, 0:2]
        co[:, 2] = z
        co[:, 3] = 1.0
        sp.points.foreach_set("co", co.ravel())
        sp.use_cyclic_u = bool(closed)
    return cu


def _line_width(cu, width, show):
    """Épaisseur de trait visible à l'écran (1 unité = 1 mm) ou simple fil."""
    if show and width > 0.0:
        cu.bevel_depth = width / 2.0
        cu.bevel_resolution = 0
        cu.fill_mode = 'FULL'
    else:
        cu.bevel_depth = 0.0


def _rect_path(x0, y0, x1, y1):
    return ([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], True)


# --------------------------------------------------------------------------
# Propriétés
# --------------------------------------------------------------------------

def _layout_update(self, context):
    if _STATE["busy"]:
        return
    scene = self.id_data
    if is_layout(scene):
        paper_rebuild(scene)
        _redraw()


def _layout_lw_update(self, context):
    if _STATE["busy"]:
        return
    scene = self.id_data
    if is_layout(scene):
        apply_lineweights(scene)


def _detail_update(self, context):
    if _STATE["busy"]:
        return
    obj = self.id_data
    if is_detail(obj):
        detail_rebuild(obj)
        _redraw()


def _detail_scale_update(self, context):
    if _STATE["busy"]:
        return
    with quiet():
        self.scale_preset = le.scale_preset(self.scale)
    obj = self.id_data
    if is_detail(obj):
        detail_rebuild(obj)
        layout_refresh_dims(obj_scene(obj))
        title_refresh(obj_scene(obj))           # le cartouche affiche l'échelle commune des détails (ou « As noted »)
        _redraw()


def _detail_preset_update(self, context):
    if _STATE["busy"]:
        return
    if self.scale_preset != 'CUSTOM':
        self.scale = le.SCALE_DEN[self.scale_preset]        # (sa propre fonction update redessine le détail)


class DESSIN_PG_layout(bpy.types.PropertyGroup):
    is_layout: bpy.props.BoolProperty(default=False)
    model: bpy.props.PointerProperty(type=bpy.types.Scene, name="Model", description="Scene shown by the viewports of this layout")
    order: bpy.props.IntProperty(default=0)
    paper: bpy.props.EnumProperty(name="Paper", items=PAPER_ITEMS, default='A3', update=_layout_update,
                                  description="Paper size of the sheet")
    orientation: bpy.props.EnumProperty(name="Orientation", default='LANDSCAPE', update=_layout_update,
                                        items=(('LANDSCAPE', "Landscape", ""), ('PORTRAIT', "Portrait", "")))
    custom_w: bpy.props.FloatProperty(name="Width", default=420.0, min=10.0, soft_max=2000.0, update=_layout_update,
                                      description="Width of a custom sheet, in millimeters")
    custom_h: bpy.props.FloatProperty(name="Height", default=297.0, min=10.0, soft_max=2000.0, update=_layout_update,
                                      description="Height of a custom sheet, in millimeters")
    margin: bpy.props.FloatProperty(name="Margin", default=10.0, min=0.0, soft_max=40.0, update=_layout_update,
                                    description="Distance between the edge of the paper and the frame, in millimeters")
    show_frame: bpy.props.BoolProperty(name="Frame", default=True, update=_layout_update,
                                       description="Draws the frame of the sheet (printed)")
    show_title: bpy.props.BoolProperty(name="Title block", default=True, update=_layout_update,
                                       description="Draws a title block in the bottom right corner of the frame, filled with the fields below")
    t_project: bpy.props.StringProperty(name="Project", default="", update=_layout_update)
    t_title: bpy.props.StringProperty(name="Title", default="", update=_layout_update)
    t_author: bpy.props.StringProperty(name="Drawn by", default="", update=_layout_update)
    t_date: bpy.props.StringProperty(name="Date", default="", update=_layout_update)
    t_number: bpy.props.StringProperty(name="Sheet", default="01", update=_layout_update, description="Sheet number")
    t_revision: bpy.props.StringProperty(name="Revision", default="", update=_layout_update)
    t_scale: bpy.props.StringProperty(name="Scale", default="", update=_layout_update,
                                      description="Scale written in the title block (empty: the scale of the viewports, or 'As noted' when they differ)")
    label_size: bpy.props.FloatProperty(name="Label height", default=3.0, min=1.0, max=20.0, update=_layout_update,
                                        description="Height of the label written under each viewport (view name and scale), in millimeters")
    lw_visible: bpy.props.FloatProperty(name="Visible edges", default=0.35, min=0.01, max=2.0, step=5, precision=2,
                                        update=_layout_lw_update, description="Printed line width of the visible edges, in millimeters")
    lw_hidden: bpy.props.FloatProperty(name="Hidden edges", default=0.18, min=0.01, max=2.0, step=5, precision=2,
                                       update=_layout_lw_update, description="Printed line width of the hidden (dashed) edges, in millimeters")
    lw_annot: bpy.props.FloatProperty(name="Annotations", default=0.18, min=0.01, max=2.0, step=5, precision=2,
                                      update=_layout_lw_update,
                                      description="Printed line width of dimensions, hatches and of everything drawn on the sheet, in millimeters")
    lw_frame: bpy.props.FloatProperty(name="Frame", default=0.5, min=0.01, max=2.0, step=5, precision=2,
                                      update=_layout_lw_update, description="Printed line width of the sheet frame and title block, in millimeters")
    lw_border: bpy.props.FloatProperty(name="Viewport borders", default=0.18, min=0.01, max=2.0, step=5, precision=2,
                                       update=_layout_lw_update, description="Printed line width of the viewport borders, in millimeters")
    show_lineweights: bpy.props.BoolProperty(name="Show line widths", default=False, update=_layout_lw_update,
                                             description="Displays the lines with their printed width (zoom in to see it). Off: thin lines, like a CAD screen")
    print_color: bpy.props.EnumProperty(name="Colors", default='BLACK',
                                        items=(('BLACK', "Black", "Everything is printed in black"),
                                               ('COLOR', "Layer colors", "Lines keep the color of their object / layer (white becomes black)")))
    auto_update: bpy.props.BoolProperty(name="Update when opened", default=True,
                                        description="The viewports are redrawn from the model each time the layout is opened after the model changed. "
                                                    "Turn it off for very heavy models and use Update Viewports")
    new_view: bpy.props.EnumProperty(name="View", items=VIEW_ITEMS[:-1], default='TOP',
                                     description="View shown by the next viewport you draw")


class DESSIN_PG_detail(bpy.types.PropertyGroup):
    is_detail: bpy.props.BoolProperty(default=False)
    model: bpy.props.PointerProperty(type=bpy.types.Scene, name="Model", update=_detail_update,
                                     description="Scene shown by this viewport (empty: the model of the layout)")
    view: bpy.props.EnumProperty(name="View", items=VIEW_ITEMS, default='TOP', update=_detail_update,
                                 description="Direction the model is seen from")
    rot: bpy.props.FloatVectorProperty(size=4, default=(1.0, 0.0, 0.0, 0.0))
    persp: bpy.props.BoolProperty(name="Perspective", default=False, update=_detail_update,
                                  description="Perspective view (the scale is exact only in the plane of the target)")
    cam_dist: bpy.props.FloatProperty(default=10.0, min=1e-6)
    view_label: bpy.props.StringProperty(default="")
    scale: bpy.props.FloatProperty(name="Scale 1 :", default=10.0, min=1e-6, soft_min=0.01, soft_max=10000.0, precision=3,
                                   update=_detail_scale_update,
                                   description="Scale denominator: 20 means 1:20 (1 mm on paper = 20 mm of the model); 0.5 means 2:1")
    scale_preset: bpy.props.EnumProperty(name="Scale", items=SCALE_ITEMS, default='S1_10', update=_detail_preset_update,
                                         description="Scale of the viewport")
    center: bpy.props.FloatVectorProperty(name="Center", size=3, subtype='XYZ', default=(0.0, 0.0, 0.0), update=_detail_update,
                                          description="Point of the model shown at the center of the viewport")
    width: bpy.props.FloatProperty(name="Width", default=120.0, min=1.0, update=_detail_update,
                                   description="Width of the viewport on the sheet, in millimeters")
    height: bpy.props.FloatProperty(name="Height", default=90.0, min=1.0, update=_detail_update,
                                    description="Height of the viewport on the sheet, in millimeters")
    locked: bpy.props.BoolProperty(name="Locked", default=False,
                                   description="Locks the scale and the framing of the viewport: Fit, Pan and the scale list do nothing")
    display: bpy.props.EnumProperty(name="Display", items=DISPLAY_ITEMS, default='HIDDEN', update=_detail_update,
                                    description="How the model is drawn in the viewport")
    show_annotations: bpy.props.BoolProperty(name="Model annotations", default=True, update=_detail_update,
                                             description="Shows the dimensions, texts and hatches of the model in the viewport")
    tangent_edges: bpy.props.BoolProperty(name="Tangent edges", default=False, update=_detail_update,
                                          description="Also draws the edges between smooth surfaces")
    sharp_angle: bpy.props.FloatProperty(name="Sharp edge angle", default=math.radians(25.0), min=0.0, max=math.pi, subtype='ANGLE',
                                         update=_detail_update, description="Edges between faces that make a larger angle are drawn")
    show_border: bpy.props.BoolProperty(name="Border", default=True, update=_detail_update,
                                        description="Prints the rectangle of the viewport (it stays visible on screen, lighter, to select the viewport)")
    show_label: bpy.props.BoolProperty(name="Label", default=True, update=_detail_update,
                                       description="Writes the view name and the scale under the viewport")
    label: bpy.props.StringProperty(name="Caption", default="", update=_detail_update,
                                    description="Text written under the viewport before the scale (empty: the name of the view)")
    hidden_layers: bpy.props.StringProperty(default="", update=_detail_update)


# --------------------------------------------------------------------------
# Feuille : papier, cadre, cartouche
# --------------------------------------------------------------------------

def _sheet_object(scene, name, data, role, color=(0.0, 0.0, 0.0), z=0.0):
    o = bpy.data.objects.new(name, data)
    o.location = (0.0, 0.0, z)
    o[SHEET] = role
    o.color = (color[0], color[1], color[2], 1.0)
    o.hide_select = True
    layout_collection(scene, 'sheet').objects.link(o)
    return o


def _fit_size(text, size, max_w):
    est = len(text) * 0.58 * size
    if est > max_w > 0.0:
        size = max(size * max_w / est, 1.0)
    return size


def _sheet_text(scene, text, x, y, size, align='LEFT', grey=0.0, max_w=0.0):
    if not text:
        return None
    fc = bpy.data.curves.new("Sheet text", 'FONT')
    fc.body = text
    fc.size = _fit_size(text, size, max_w)
    fc.align_x = align
    fc.align_y = 'BOTTOM_BASELINE'
    o = _sheet_object(scene, "Sheet text", fc, 'text', (grey, grey, grey))
    o.location = (x, y, 0.0)
    return o


def title_scale_text(scene):
    L = scene.dessin_layout
    if L.t_scale.strip():
        return L.t_scale.strip()
    dens = sorted({round(d.dessin_detail.scale, 9) for d in details(scene) if not d.dessin_detail.persp})
    if not dens:
        return ""
    if len(dens) == 1:
        return le.fmt_scale(dens[0])
    return _tr("As noted")


def title_rect(L):
    """Rectangle du cartouche (x0, y0, x1, y1), en bas à droite du cadre."""
    x0, y0, x1, _y1 = frame_rect(L)
    tw = min(170.0, x1 - x0)
    return x1 - tw, y0, x1, y0 + 34.0


def paper_rebuild(scene):
    """Reconstruit le papier, le cadre et le cartouche d'une mise en page."""
    if _STATE["busy"]:
        return
    L = scene.dessin_layout
    with quiet():
        _remove([o for o in scene.objects if o.get(SHEET)])
        w, h = paper_size(L)
        me = bpy.data.meshes.new("Paper")
        me.from_pydata([(0.0, 0.0, 0.0), (w, 0.0, 0.0), (w, h, 0.0), (0.0, h, 0.0)], [], [(0, 1, 2, 3)])
        _sheet_object(scene, "Paper", me, 'paper', (0.995, 0.995, 0.995), Z_PAPER)
        show = L.show_lineweights
        fx0, fy0, fx1, fy1 = frame_rect(L)
        if L.show_frame:
            cu = _new_curve("Frame", [_rect_path(fx0, fy0, fx1, fy1)])
            _line_width(cu, L.lw_frame, show)
            _sheet_object(scene, "Frame", cu, 'frame')
        if L.show_title:
            x0, y0, x1, y1 = title_rect(L)
            tw = x1 - x0
            cr = x1 - min(34.0, tw * 0.25)            # colonne de droite (planche, date, format)
            cm = cr - min(30.0, tw * 0.2)             # colonne du milieu (échelle, indice)
            r1, r2 = y0 + 9.0, y0 + 21.0              # lignes
            outer = [([(x0, y1), (x0, y0)], False), ([(x0, y1), (x1, y1)], False)]
            if not L.show_frame:
                outer = [_rect_path(x0, y0, x1, y1)]
            cu = _new_curve("Title block", outer)
            _line_width(cu, L.lw_frame, show)
            _sheet_object(scene, "Title block", cu, 'frame')
            inner = [([(x0, r1), (x1, r1)], False), ([(x0, r2), (x1, r2)], False), ([(cr, y0), (cr, y1)], False),
                     ([(cm, y0), (cm, r2)], False)]
            cu = _new_curve("Title block lines", inner)
            _line_width(cu, L.lw_annot, show)
            _sheet_object(scene, "Title block lines", cu, 'title')
            pad, lab = 1.5, 1.8
            cells = (
                (_tr("PROJECT"), L.t_project, x0, r2, cr, y1, 5.0),
                (_tr("SHEET"), L.t_number, cr, r2, x1, y1, 6.5),
                (_tr("TITLE"), L.t_title, x0, r1, cm, r2, 4.0),
                (_tr("SCALE"), title_scale_text(scene), cm, r1, cr, r2, 4.0),
                (_tr("DATE"), L.t_date, cr, r1, x1, r2, 3.2),
                (_tr("DRAWN BY"), L.t_author, x0, y0, cm, r1, 3.0),
                (_tr("REV"), L.t_revision, cm, y0, cr, r1, 3.0),
                (_tr("FORMAT"), paper_label(L), cr, y0, x1, r1, 3.0),
            )
            for label, value, cx0, cy0, cx1, cy1, size in cells:
                _sheet_text(scene, label, cx0 + pad, cy1 - pad - lab, lab, grey=0.35, max_w=cx1 - cx0 - 2 * pad)
                room = cy1 - cy0 - lab - 2.5 * pad
                size = min(size, max(room, 1.5))
                _sheet_text(scene, value, cx0 + pad, cy0 + pad * 0.9, size, max_w=cx1 - cx0 - 2 * pad)
        scene["wd_title_scale"] = title_scale_text(scene)


def apply_lineweights(scene):
    """Reporte les épaisseurs de trait (affichage à l'écran) sur les objets générés de la mise en page."""
    L = scene.dessin_layout
    show = L.show_lineweights
    for o in scene.objects:
        if o.type != 'CURVE':
            continue
        role = o.get(GEN) or o.get(SHEET)
        w = {"vis": L.lw_visible, "hid_show": L.lw_hidden, "ann": L.lw_annot, "frame": L.lw_frame, "title": L.lw_annot,
             "detail": L.lw_border}.get(role)
        if w is not None:
            _line_width(o.data, w, show and not (role == 'detail' and not o.dessin_detail.show_border))


# --------------------------------------------------------------------------
# Détails
# --------------------------------------------------------------------------

def model_version(scene):
    return _STATE["model_ver"].get(scene.name, 0) if scene is not None else 0


def detail_signature(d, model):
    q = detail_quat(d)
    return (model.name, model_version(model), tuple(round(x, 7) for x in q), bool(d.persp),
            round(d.cam_dist, 6) if d.persp else 0.0, tuple(round(x, 6) for x in d.center) if d.persp else None,
            d.display, bool(d.show_annotations), bool(d.tangent_edges), round(d.sharp_angle, 5), d.hidden_layers)


def detail_projector(d):
    return le.Projector(detail_quat(d), d.persp, tuple(d.center), d.cam_dist)


def detail_projection(obj, force=False):
    """(projection du modèle dans la vue du détail, projecteur) ; la projection est gardée tant que rien ne change."""
    d = obj.dessin_detail
    model = detail_model(obj)
    if model is None:
        return None, None
    proj = detail_projector(d)
    sig = detail_signature(d, model)
    c = _STATE["cache"].get(obj.name)
    if c is not None and c[0] == sig and not force:
        return c[1], proj
    _wait_cursor(True)                 # gros modèle : la lecture et les lignes cachées prennent quelques secondes
    try:
        # les détails d'une même mise en page lisent le modèle une seule fois (gardé le temps de la série, pas au-delà)
        key = (model.name, model_version(model), d.hidden_layers, bool(d.show_annotations))
        got = _STATE.get("items")
        if got is not None and got[0] == key:
            items = got[1]
        else:
            items = le.collect_model(model, detail_hidden(d), d.show_annotations)
            _STATE["items"] = (key, items)
        P = le.project_model(items, proj, d.display, math.degrees(d.sharp_angle), d.tangent_edges)
    finally:
        _wait_cursor(False)
    _STATE["cache"][obj.name] = (sig, P)
    return P, proj


def _wait_cursor(on):
    try:
        win = bpy.context.window
        if win is not None and not bpy.app.background:
            if on:
                win.cursor_modal_set('WAIT')
            else:
                win.cursor_modal_restore()
    except (AttributeError, RuntimeError, TypeError):
        pass


def _set_rect(cu, w, h):
    while len(cu.splines):
        cu.splines.remove(cu.splines[0])
    sp = cu.splines.new('POLY')
    sp.points.add(3)
    for pt, (x, y) in zip(sp.points, ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2))):
        pt.co = (x, y, 0.0, 1.0)
    sp.use_cyclic_u = True


def _child(parent, name, data, role, color=(0.0, 0.0, 0.0), z=0.0, hidden=False):
    o = bpy.data.objects.new(name, data)
    o.location = (0.0, 0.0, z)
    o[GEN] = role
    o.color = (color[0], color[1], color[2], 1.0)
    o.hide_select = True
    o.hide_viewport = bool(hidden)
    o.hide_render = bool(hidden)
    (parent.users_collection[0] if parent.users_collection else bpy.context.scene.collection).objects.link(o)
    o.parent = parent
    return o


def detail_label_text(d):
    cap = detail_caption(d)
    if d.persp:
        return cap
    return f"{cap}   {le.fmt_scale(d.scale)}"


def detail_rebuild(obj, force=False):
    """Redessine un détail : cadre, traits du modèle (visibles, cachés, annotations), aplats et étiquette.
    force : relit le modèle même si rien ne semble avoir changé."""
    if _STATE["busy"] or not is_detail(obj):
        return False
    scene = obj_scene(obj)
    if scene is None:
        return False
    L = scene.dessin_layout
    d = obj.dessin_detail
    with quiet():
        model = detail_model(obj)
        P, proj = detail_projection(obj, force)
        _set_rect(obj.data, d.width, d.height)
        _line_width(obj.data, L.lw_border, L.show_lineweights and d.show_border)
        grey = 0.0 if d.show_border else 0.72
        obj.color = (grey, grey, grey * 1.05 if grey else 0.0, 1.0)
        _remove(detail_children(obj))
        show = L.show_lineweights
        n = 0
        if P is not None and model is not None:
            cu_, cv_ = proj.uv(np.array(d.center, dtype=np.float64))[0]
            k = mm_per_unit(model) / max(d.scale, 1e-9)
            geo = le.to_paper(P, float(cu_), float(cv_), k, d.width, d.height)
            for role, color, paths in geo["lines"]:
                col = shown_color(color)
                if role == 'hid':
                    # la source (non tiretée, masquée) sert à l'export ; les tirets ne servent qu'à l'affichage
                    _child(obj, f"{obj.name} hidden", _new_curve("Viewport hidden", paths), 'hid', col, hidden=True)
                    cu = _new_curve("Viewport hidden dashes", le.dash_paths(paths))
                    _line_width(cu, L.lw_hidden, show)
                    shade = tuple(0.35 + 0.65 * c for c in col) if max(col) < 0.05 else col
                    _child(obj, f"{obj.name} hidden dashes", cu, 'hid_show', shade)
                    n += 2
                else:
                    cu = _new_curve("Viewport " + role, paths)
                    _line_width(cu, L.lw_visible if role == 'vis' else L.lw_annot, show)
                    _child(obj, f"{obj.name} {'lines' if role == 'vis' else 'annotations'}", cu, role, col)
                    n += 1
            if geo["fills"]:
                loops, counts, colors, flags = [], [], [], []
                shown = {}
                for color, lps, polys, is_text in geo["fills"]:
                    loops += [(lp, True) for lp in lps]
                    counts.append(len(lps))
                    colors += list(color[:3])
                    flags.append(1 if is_text else 0)
                    shown.setdefault(shown_color(color), []).extend(polys)
                src = _child(obj, f"{obj.name} fills", _new_curve("Viewport fills", loops), 'fill', hidden=True)
                src["wd_fill_n"] = counts
                src["wd_fill_c"] = colors
                src["wd_fill_t"] = flags
                n += 1
                for col, polys in shown.items():
                    verts, faces = [], []
                    for poly in polys:
                        base = len(verts)
                        verts += [(float(p[0]), float(p[1]), 0.0) for p in poly]
                        faces.append(tuple(range(base, base + len(poly))))
                    if not faces:
                        continue
                    me = bpy.data.meshes.new("Viewport fills")
                    me.from_pydata(verts, [], faces)
                    fo = _child(obj, f"{obj.name} fills shown", me, 'fill_show', col, z=Z_FILL)
                    fo["wd_nosnap"] = 1            # les triangles d'un texte ne sont pas des points d'accrochage
                    n += 1
        if d.show_label:
            fc = bpy.data.curves.new("Viewport label", 'FONT')
            fc.body = detail_label_text(d)
            fc.size = L.label_size
            fc.align_x = 'LEFT'
            fc.align_y = 'BOTTOM_BASELINE'
            lab = _child(obj, f"{obj.name} label", fc, 'label')
            lab.location = (-d.width / 2.0, -d.height / 2.0 - L.label_size * 1.35, 0.0)
            n += 1
        obj["wd_nchild"] = len(detail_children(obj))
        obj.rotation_euler = (0.0, 0.0, 0.0)
        obj.scale = (1.0, 1.0, 1.0)
        obj.location.z = 0.0
        if model is not None:
            _STATE["built"][obj.name] = model_version(model)
        detail_dims_follow(obj)
    return True


def detail_create(scene, cx, cy, w, h, view='TOP', scale=None, fit=True, name=None):
    """Nouveau détail sur la mise en page `scene`, centré en (cx, cy), de w x h mm."""
    with quiet():
        cu = bpy.data.curves.new("Viewport", 'CURVE')
        cu.dimensions = '3D'
        cu.resolution_u = 1
        obj = bpy.data.objects.new(name or ("Viewport " + VIEW_LABELS.get(view, "View")), cu)
        obj[GEN] = 'detail'
        detail_id(obj)
        layout_collection(scene, 'details').objects.link(obj)
        obj.location = (cx, cy, 0.0)
        d = obj.dessin_detail
        d.is_detail = True
        d.view = view
        d.width, d.height = max(w, 1.0), max(h, 1.0)
        if scale:
            d.scale = scale
            d.scale_preset = le.scale_preset(scale)
    if fit:
        detail_fit(obj, pick_scale=not scale, rebuild=False)
    detail_rebuild(obj, force=True)
    title_refresh(scene)
    return obj


def fit_scale(extent_w, extent_h, w, h, mm, margin=0.9):
    """Plus grande échelle normalisée où (extent_w x extent_h unités du modèle) tient dans (w x h mm)."""
    need = max(extent_w * mm / max(w * margin, 1e-9), extent_h * mm / max(h * margin, 1e-9), 1e-9)
    for _k, _n, den in le.SCALES:
        if den >= need * (1.0 - 1e-9):
            return den
    mag = 10.0 ** math.floor(math.log10(need))
    for m in (1.0, 2.0, 2.5, 5.0, 10.0):
        if m * mag >= need:
            return m * mag
    return need


def detail_extent(obj):
    """(emprise (u0, v0, u1, v1) du modèle dans la vue du détail, centre 3D de cette emprise), ou (None, None)."""
    d = obj.dessin_detail
    model = detail_model(obj)
    if model is None:
        return None, None
    items = le.collect_model(model, detail_hidden(d), d.show_annotations)
    proj = le.Projector(detail_quat(d), False)
    ext = le.model_extent(items, proj)
    if ext is None:
        return None, None
    pts = [it.V for it in items if it.V is not None and len(it.V)] + [lp for it in items for lp in it.loops]
    allp = np.concatenate(pts)
    c = Vector((allp.min(axis=0) + allp.max(axis=0)) * 0.5)
    uc, vc = (ext[0] + ext[2]) * 0.5, (ext[1] + ext[3]) * 0.5
    c = c + proj.right * (uc - c.dot(proj.right)) + proj.up * (vc - c.dot(proj.up))
    return ext, c


def detail_fit(obj, pick_scale=True, rebuild=True):
    """Cadre le modèle dans le détail : centre, et (pick_scale) la plus grande échelle normalisée qui tient."""
    d = obj.dessin_detail
    ext, c = detail_extent(obj)
    if ext is None:
        return False
    with quiet():
        d.center = c
        if pick_scale:
            den = fit_scale(ext[2] - ext[0], ext[3] - ext[1], d.width, d.height, mm_per_unit(detail_model(obj)))
            d.scale = den
            d.scale_preset = le.scale_preset(den)
    if rebuild:
        detail_rebuild(obj)
        sc = obj_scene(obj)
        if sc is not None:
            layout_refresh_dims(sc)
            title_refresh(sc)
    return True


def title_refresh(scene):
    """Le cartouche affiche l'échelle des détails : il est refait quand elle change."""
    try:
        if scene.dessin_layout.show_title and scene.get("wd_title_scale", "") != title_scale_text(scene):
            paper_rebuild(scene)
    except (AttributeError, ReferenceError):
        pass


def detail_at(scene, x, y, tol=0.0):
    """Détail (le plus petit) dont le cadre contient le point papier (x, y)."""
    best = None
    for o in details(scene):
        d = o.dessin_detail
        if abs(x - o.location.x) <= d.width / 2.0 + tol and abs(y - o.location.y) <= d.height / 2.0 + tol:
            if best is None or d.width * d.height < best.dessin_detail.width * best.dessin_detail.height:
                best = o
    return best


def layout_scale_at(scene, pts):
    """Dénominateur d'échelle du détail qui contient tous les points (cotes posées sur la feuille), sinon 1."""
    best = None
    for o in details(scene):
        d = o.dessin_detail
        if d.persp:
            continue
        if all(abs(p[0] - o.location.x) <= d.width / 2.0 + 1e-4 and abs(p[1] - o.location.y) <= d.height / 2.0 + 1e-4 for p in pts):
            if best is None or d.width * d.height < best.dessin_detail.width * best.dessin_detail.height:
                best = o
    return float(best.dessin_detail.scale) if best is not None else 1.0


def layout_dim_factor(op):
    """Facteur appliqué à la longueur mesurée d'une cote : sur une mise en page, une cote posée sur un détail donne
    la vraie longueur du modèle (longueur sur le papier x échelle)."""
    stored = getattr(op, "lfac", None)
    f = None
    try:
        sc = bpy.context.scene
        if is_layout(sc):
            ld = getattr(op, "ldet", None)
            det = bpy.data.objects.get(ld) if ld else None
            if det is not None and is_detail(det) and not det.dessin_detail.persp and det.name in sc.objects:
                f = float(det.dessin_detail.scale)                   # cote attachée : l'échelle de son détail, où qu'elle soit
            else:
                pts = list(getattr(op, "points", ()) or ())[:2]      # les points mesurés (pas la position du texte)
                if not pts and getattr(op, "cur", None) is not None:
                    pts = [op.cur]
                if pts:
                    f = layout_scale_at(sc, pts)
    except (AttributeError, ReferenceError, TypeError):
        f = None
    if f is None:
        f = float(stored[0]) if stored else 1.0
    try:
        op.lfac = [f] if abs(f - 1.0) > 1e-12 else None
    except AttributeError:
        pass
    return f


def layout_refresh_dims(scene):
    """Les cotes de la mise en page sont recalculées (l'échelle d'un détail a pu changer)."""
    try:
        if scene is None or bpy.context.scene != scene:
            return
        col = layout_dims_collection(scene, create=False)
        if col is None:
            return
        for o in list(col.objects):
            if o.type == 'CURVE' and "dessin_dim" in o.keys():
                try:
                    rebuild_dimension(bpy.context, o)
                except (RuntimeError, ReferenceError, ValueError, TypeError, KeyError, AttributeError):
                    continue
    except (AttributeError, ReferenceError, RuntimeError):
        pass


# --------------------------------------------------------------------------
# Cotes associées aux détails
# --------------------------------------------------------------------------
# Une cote posée sur un détail mesure le modèle vu dans ce détail. Ses points sont mémorisés dans le repère de la vue du
# modèle (u, v) : quand le détail est déplacé, que son contenu est décalé (Pan) ou que son échelle change, la cote est
# replacée sur les mêmes points du modèle. Définition de la cote (JSON « dessin_dim ») : ldet = nom du détail ('' : aucun),
# luv = points en (u, v), lsig = état des points au moment de l'attache, lorg = position de l'objet à ce moment.

def detail_map(obj):
    """Correspondance papier <-> modèle d'un détail : (x, y du centre sur la feuille, u, v du centre dans la vue, mm par unité
    du modèle, vue). None pour une vue en perspective (pas d'échelle unique)."""
    d = obj.dessin_detail
    model = detail_model(obj)
    if model is None or d.persp:
        return None
    try:
        c = np.asarray(detail_projector(d).uv(np.array([tuple(d.center)], dtype=float)), dtype=float)[0]
    except (ValueError, TypeError, AttributeError):
        return None
    q = detail_quat(d)
    return [float(obj.location.x), float(obj.location.y), float(c[0]), float(c[1]), mm_per_unit(model) / max(d.scale, 1e-9),
            float(q.w), float(q.x), float(q.y), float(q.z)]


def _map_uv(mp, p):
    return [mp[2] + (p[0] - mp[0]) / mp[4], mp[3] + (p[1] - mp[1]) / mp[4]]


def _map_paper(mp, uv, z=0.0):
    return [mp[0] + (uv[0] - mp[2]) * mp[4], mp[1] + (uv[1] - mp[3]) * mp[4], z]


def layout_dims(scene):
    """Cotes (courbes portant leur définition) posées sur une mise en page."""
    col = layout_dims_collection(scene, create=False)
    if col is None:
        return []
    return [o for o in col.objects if o.type == 'CURVE' and "dessin_dim" in o.keys()]


def _dim_sig(data):
    """État des points d'une cote : change quand un outil (Move Dimension Line...) la modifie."""
    vals = [x for p in data.get("points", ()) for x in p] + list(data.get("cur", ()))
    if data.get("circ"):
        vals += list(data["circ"][0]) + [data["circ"][1]]
    return [round(float(x), 6) for x in vals]


def _detail_of_points(scene, pts):
    """Détail (non perspective, le plus petit) dont le cadre contient tous les points."""
    best = None
    for o in details(scene):
        d = o.dessin_detail
        if d.persp:
            continue
        if all(abs(p[0] - o.location.x) <= d.width / 2.0 + 1e-4 and abs(p[1] - o.location.y) <= d.height / 2.0 + 1e-4 for p in pts):
            if best is None or d.width * d.height < best.dessin_detail.width * best.dessin_detail.height:
                best = o
    return best


def _points_in(det, pts):
    d = det.dessin_detail
    return all(abs(p[0] - det.location.x) <= d.width / 2.0 + 1e-4 and abs(p[1] - det.location.y) <= d.height / 2.0 + 1e-4 for p in pts)


def _dim_detail(scene, data):
    """Détail auquel une cote est attachée (None : aucun, ou il n'existe plus dans cette mise en page).
    Retrouvé par son nom, sinon par son identifiant (détail renommé, mise en page copiée)."""
    ld = data.get("ldet")
    if not ld:
        return None
    det = bpy.data.objects.get(ld)
    if det is not None and is_detail(det) and det.name in scene.objects:
        return det
    lid = data.get("ldid")
    if lid is not None:
        for o in details(scene):
            if o.get("wd_id") == lid:
                return o
    return None


def detail_id(obj):
    """Identifiant d'un détail, stable quand on le renomme (les cotes attachées le retrouvent)."""
    v = obj.get("wd_id")
    if v is None:
        v = random.getrandbits(30)
        obj["wd_id"] = v
    return int(v)


def dim_link(scene, o, data=None, det='AUTO'):
    """Attache une cote à un détail : ses points sont mémorisés dans le repère de la vue du modèle.
    det='AUTO' : le détail sur lequel ses points mesurés sont posés ; None : cote de papier, attachée à rien."""
    try:
        if data is None:
            data = json.loads(o["dessin_dim"])
        pts = data.get("points") or []
        if det == 'AUTO':
            det = _detail_of_points(scene, pts[:2]) if pts else None
        mp = detail_map(det) if det is not None else None
        if mp is None:
            data["ldet"] = ""
            data.pop("luv", None)
        else:
            luv = {"p": [_map_uv(mp, p) for p in pts], "c": _map_uv(mp, data["cur"])}
            if data.get("circ"):
                luv["o"] = _map_uv(mp, data["circ"][0])
                luv["r"] = float(data["circ"][1]) / mp[4]
            data["ldet"] = det.name
            data["ldid"] = detail_id(det)
            data["luv"] = luv
        data["lsig"] = _dim_sig(data)
        data["lorg"] = [float(o.location.x), float(o.location.y)]
        o["dessin_dim"] = json.dumps(data)
        return det
    except (KeyError, ValueError, TypeError, AttributeError, ReferenceError):
        return None


def _dim_moved(o, data):
    """Déplacement donné à la main à une cote (gumball, Move) depuis sa dernière construction : (dx, dy) ou None."""
    lorg = data.get("lorg")
    if not lorg or (abs(o.location.x - lorg[0]) < 1e-4 and abs(o.location.y - lorg[1]) < 1e-4):
        return None
    try:
        if any(abs(v) > 1e-6 for v in o.rotation_euler) or any(abs(v - 1.0) > 1e-6 for v in o.scale):
            return None                       # cote tournée ou mise à l'échelle à la main : on n'y touche pas
        spec = _dim_replay_spec(data)
        org = Vector(spec[1]["frame"][3])
    except (KeyError, ValueError, TypeError, AttributeError, IndexError):
        return None
    dx, dy = o.location.x - org.x, o.location.y - org.y
    if abs(dx) < 1e-3 and abs(dy) < 1e-3:     # (moins d'un micron : précision des positions d'objet)
        return (0.0, 0.0)                     # le style a déplacé le texte, pas l'utilisateur
    return (dx, dy)


def dims_sync(scene, moved=True):
    """Tient à jour l'attache des cotes : nouvelles cotes, cotes déplacées à la main (leur définition suit), cotes modifiées
    par un outil, détail supprimé ou renommé. moved=False : seulement les nouvelles (pendant une commande)."""
    n = 0
    try:
        if bpy.context.scene != scene:
            return 0
        for o in layout_dims(scene):
            try:
                data = json.loads(o["dessin_dim"])
            except (ValueError, TypeError, KeyError):
                continue
            ld = data.get("ldet")
            if ld is None:
                dim_link(scene, o, data)                 # cote que l'on vient de poser
                n += 1
                continue
            if not moved:
                continue
            det = _dim_detail(scene, data)
            target = det
            need = data.get("lsig") != _dim_sig(data) or (det is not None and det.name != ld)      # (détail renommé)
            if ld and det is None:
                # son détail n'existe plus. Un autre détail sous ses points (copie) : elle s'y attache ; sinon elle mesurait
                # un dessin qui a disparu : elle part avec lui
                target = _detail_of_points(scene, (data.get("points") or [])[:2])
                if target is None:
                    _remove([o] + list(o.children))
                    n += 1
                    continue
                need = True
            m = _dim_moved(o, data)
            if m is not None:
                if m != (0.0, 0.0):
                    data["points"] = [[p[0] + m[0], p[1] + m[1]] + list(p[2:]) for p in data["points"]]
                    c = data["cur"]
                    data["cur"] = [c[0] + m[0], c[1] + m[1]] + list(c[2:])
                    if data.get("circ"):
                        cc = data["circ"][0]
                        data["circ"][0] = [cc[0] + m[0], cc[1] + m[1]] + list(cc[2:])
                    # cote copiée ou portée sur un autre détail : elle s'attache à celui sur lequel elle est maintenant
                    pts = data["points"][:2]
                    geo = _detail_of_points(scene, pts)
                    if ld and geo is not None and geo != det and (det is None or not _points_in(det, pts)):
                        target = geo
                need = True
            if need:
                dim_link(scene, o, data, target)
                n += 1
    except (AttributeError, ReferenceError, RuntimeError):
        pass
    return n


def detail_dims_follow(obj):
    """Après un changement du détail (déplacé, Pan, échelle) : ses cotes sont replacées sur les mêmes points du modèle.
    Retourne le nombre de cotes replacées."""
    try:
        new = detail_map(obj)
        old = obj.get("wd_map")
        old = [float(x) for x in old] if old is not None else None
        if new is None:
            if old is not None:
                del obj["wd_map"]
            return 0
        obj["wd_map"] = new
        if old is None or len(old) != len(new) or max(abs(a - b) for a, b in zip(old, new)) < 1e-9:
            return 0
        scene = obj_scene(obj)
        if scene is None or bpy.context.scene != scene:
            return 0
        same_view = all(abs(old[i] - new[i]) < 1e-6 for i in range(5, 9))
        n = 0
        for o in layout_dims(scene):
            try:
                data = json.loads(o["dessin_dim"])
            except (ValueError, TypeError, KeyError):
                continue
            if not data.get("luv") or _dim_detail(scene, data) != obj:
                continue
            if not same_view:                 # autre vue : les points ne désignent plus rien, la cote reste où elle est
                dim_link(scene, o, data)
                continue
            luv = data["luv"]
            if data.get("lsig") != _dim_sig(data):
                # un outil a modifié la cote depuis l'attache (Move Dimension Line...) : ses points actuels font foi
                luv = {"p": [_map_uv(old, p) for p in data["points"]], "c": _map_uv(old, data["cur"])}
                if data.get("circ"):
                    luv["o"] = _map_uv(old, data["circ"][0])
                    luv["r"] = float(data["circ"][1]) / old[4]
            m = _dim_moved(o, data)
            if m is not None and m != (0.0, 0.0):
                # cote déplacée à la main. Avec le détail (sélectionnés ensemble) : rien à ajouter, elle est replacée sur ses
                # points. Sans lui : ce déplacement est gardé, dans le repère du modèle
                moved_with = abs(m[0] - (new[0] - old[0])) < 1e-3 and abs(m[1] - (new[1] - old[1])) < 1e-3
                if not moved_with:
                    du, dv = m[0] / old[4], m[1] / old[4]
                    luv = dict(luv, p=[[u + du, v + dv] for u, v in luv["p"]], c=[luv["c"][0] + du, luv["c"][1] + dv])
                    if "o" in luv:
                        luv["o"] = [luv["o"][0] + du, luv["o"][1] + dv]
            data["luv"] = luv
            pts = data["points"]
            data["points"] = [_map_paper(new, uv, p[2] if len(p) > 2 else 0.0) for uv, p in zip(luv["p"], pts)]
            c = data["cur"]
            data["cur"] = _map_paper(new, luv["c"], c[2] if len(c) > 2 else 0.0)
            if data.get("circ") and "o" in luv:
                cc = data["circ"][0]
                data["circ"][0] = _map_paper(new, luv["o"], cc[2] if len(cc) > 2 else 0.0)
                data["circ"][1] = float(luv["r"]) * new[4]
            data["lsig"] = _dim_sig(data)
            data["lfac"] = [float(obj.dessin_detail.scale)]
            o["dessin_dim"] = json.dumps(data)
            try:
                built = rebuild_dimension(bpy.context, o)
            except (RuntimeError, ReferenceError, ValueError, TypeError, KeyError, AttributeError):
                built = None
            if built:
                data["lorg"] = [float(built.location.x), float(built.location.y)]
                built["dessin_dim"] = json.dumps(data)
                n += 1
        return n
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
        return 0


# --------------------------------------------------------------------------
# Création d'une mise en page
# --------------------------------------------------------------------------

def unique_layout_name(name):
    taken = {s.name for s in bpy.data.scenes}
    if name not in taken:
        return name
    stem = name.rstrip("0123456789 ") or name
    k = 2
    while f"{stem} {k}" in taken:
        k += 1
    return f"{stem} {k}"


def layout_create(model, name="Layout", paper='A3', orientation='LANDSCAPE', margin=10.0, title=True,
                  custom=(420.0, 297.0)):
    """Crée la scène d'une mise en page vide (papier, cadre, cartouche) pour le modèle `model`."""
    sc = bpy.data.scenes.new(unique_layout_name(name.strip() or "Layout"))
    us = sc.unit_settings
    us.system = 'METRIC'
    us.scale_length = 0.001
    us.length_unit = 'MILLIMETERS'
    L = sc.dessin_layout
    with quiet():
        L.is_layout = True
        L.model = model
        L.order = max([s.dessin_layout.order for s in layouts() if s != sc] + [0]) + 1
        L.paper, L.orientation, L.margin, L.show_title = paper, orientation, margin, title
        L.custom_w, L.custom_h = custom
        L.t_date = time.strftime("%d/%m/%Y" if lang() == 'FR' else "%Y-%m-%d")
        L.t_title = sc.name
        L.t_number = f"{len(layouts()):02d}"               # feuilles numérotées à la suite : 01, 02, 03...
        try:
            L.t_project = os.path.splitext(os.path.basename(bpy.data.filepath))[0]
        except (AttributeError, TypeError):
            pass
        # réglages de dessin : ceux du modèle (style de cote, accrochages), avec une hauteur de texte fixe sur le papier
        try:
            src, dst = model.dessin, sc.dessin
            for key in DIM_STYLE_FIELDS + ("couleur", "epaisseur_trait", "sortie_formes"):
                try:
                    setattr(dst, key, getattr(src, key))
                except (AttributeError, TypeError, ValueError):
                    pass
            dst.taille_texte = 2.5           # 2,5 mm sur le papier
            dst.couleur = (0.0, 0.0, 0.0)    # cotes noires : la couleur claire du modèle se perdrait sur le papier blanc
            dst.hatch_spacing = 2.0
            ensure_dim_styles(dst)
            sc["wd_dim_v2"] = 1
            sc["wd_shapes_v2"] = 1
        except (AttributeError, ReferenceError):
            pass
    layout_collection(sc, 'sheet')
    layout_collection(sc, 'details')
    layout_collection(sc, 'annot')
    paper_rebuild(sc)
    layout_current_layer(sc)
    return sc


def layout_current_layer(scene):
    """Ce que l'on dessine sur la feuille va dans le calque « Annotations », tant qu'aucun autre calque n'est choisi."""
    try:
        vl = scene.view_layers[0]
        if vl.active_layer_collection != vl.layer_collection:
            return
        ann = layout_collection(scene, 'annot')
        lc = next((c for c in vl.layer_collection.children if c.collection == ann), None)
        if lc is None:
            vl.update()
            lc = next((c for c in vl.layer_collection.children if c.collection == ann), None)
        if lc is not None:
            vl.active_layer_collection = lc
    except (AttributeError, IndexError, RuntimeError, ReferenceError):
        pass


def usable_rect(L):
    """Zone libre de la feuille pour les détails : le cadre, moins la bande du cartouche."""
    x0, y0, x1, y1 = frame_rect(L)
    if L.show_title:
        y0 = title_rect(L)[3]
    return x0, y0, x1, y1


def layout_initial_details(scene, mode):
    """Détails posés à la création : 'ONE' (vue de dessus) ou 'FOUR' (dessus, face, droite, isométrie)."""
    L = scene.dessin_layout
    x0, y0, x1, y1 = usable_rect(L)
    gap, pad, lab = 8.0, 8.0, L.label_size * 2.2
    made = []
    if mode == 'ONE':
        w, h = x1 - x0 - 2 * pad, y1 - y0 - 2 * pad - lab
        if w > 10.0 and h > 10.0:
            made.append(detail_create(scene, (x0 + x1) / 2.0, (y0 + y1) / 2.0 + lab / 2.0, w, h, 'TOP'))
    elif mode == 'FOUR':
        w = (x1 - x0 - 2 * pad - gap) / 2.0
        h = (y1 - y0 - 2 * pad - gap - 2 * lab) / 2.0
        if w > 10.0 and h > 10.0:
            xl, xr = x0 + pad + w / 2.0, x1 - pad - w / 2.0
            yb, yt = y0 + pad + lab + h / 2.0, y1 - pad - h / 2.0
            cells = (('TOP', xl, yt), ('ISO_SE', xr, yt), ('FRONT', xl, yb), ('RIGHT', xr, yb))
            for view, cx, cy in cells:
                made.append(detail_create(scene, cx, cy, w, h, view))
            ortho = [o for o in made if o.dessin_detail.view in ('TOP', 'FRONT', 'RIGHT')]
            den = max(o.dessin_detail.scale for o in ortho)
            ext, c = detail_extent(ortho[0])
            for o in made:              # même échelle et même centre : les vues sont alignées entre elles
                d = o.dessin_detail
                with quiet():
                    if o in ortho:
                        d.scale = den
                        d.scale_preset = le.scale_preset(den)
                        if c is not None:
                            d.center = c
                detail_rebuild(o)
    title_refresh(scene)
    return made


# --------------------------------------------------------------------------
# Vue 3D d'une mise en page : dessus, sans rotation, papier blanc ; retour au modèle
# --------------------------------------------------------------------------

_SHADING = ("type", "light", "color_type", "wireframe_color_type", "background_type", "show_xray", "show_shadows", "show_cavity",
            "show_object_outline")
_OVERLAY = ("show_floor", "show_axis_x", "show_axis_y", "show_axis_z", "show_cursor", "show_ortho_grid",
            "show_relationship_lines", "show_object_origins")


def _view3d_areas(win):
    out = []
    try:
        for area in win.screen.areas:
            if area.type == 'VIEW_3D':
                sp = area.spaces.active
                region = next((r for r in area.regions if r.type == 'WINDOW'), None)
                rv = getattr(sp, "region_3d", None)
                if rv is not None and region is not None:
                    out.append((area, sp, region, rv))
    except (AttributeError, ReferenceError):
        pass
    return out


def _save_view(sp, rv):
    st = {"rot": tuple(rv.view_rotation), "loc": tuple(rv.view_location), "dist": rv.view_distance,
          "persp": rv.view_perspective, "lock": bool(rv.lock_rotation), "bg": tuple(sp.shading.background_color)}
    for k in _SHADING:
        st["s_" + k] = getattr(sp.shading, k, None)
    for k in _OVERLAY:
        st["o_" + k] = getattr(sp.overlay, k, None)
    cs = cp_state(rv)
    st["cplane"] = cs["cur"] if cs else None
    return st


def _restore_view(sp, rv, st):
    try:
        rv.lock_rotation = st.get("lock", False)
        rv.view_perspective = st["persp"]
        rv.view_rotation = st["rot"]
        rv.view_location = st["loc"]
        rv.view_distance = st["dist"]
        sp.shading.background_color = st["bg"]
    except (KeyError, TypeError, AttributeError):
        pass
    for k in _SHADING:
        v = st.get("s_" + k)
        if v is not None:
            try:
                setattr(sp.shading, k, v)
            except (TypeError, AttributeError):
                pass
    for k in _OVERLAY:
        v = st.get("o_" + k)
        if v is not None:
            try:
                setattr(sp.overlay, k, v)
            except (TypeError, AttributeError):
                pass
    try:
        cp_set(rv, st.get("cplane"), record=False)
    except (AttributeError, ReferenceError):
        pass


def _free_rect(context, area, sp, region):
    """Partie de la vue 3D que rien ne recouvre (px, dans la région) : sans la barre d'outils, la barre latérale, les
    en-têtes superposés ni les onglets et la ligne de commande du bas."""
    x0, y0, x1, y1 = 0.0, 0.0, float(region.width), float(region.height)
    try:
        sysp = context.preferences.system
        ui = float(sysp.ui_scale)
        overlap = bool(sysp.use_region_overlap)
    except AttributeError:
        ui, overlap = 1.0, False
    if overlap:
        try:
            for r in area.regions:
                if r.width <= 1 or r.height <= 1:
                    continue
                if r.type == 'TOOLS' and getattr(sp, "show_region_toolbar", True):
                    x0 += r.width
                elif r.type == 'UI' and getattr(sp, "show_region_ui", True):
                    x1 -= r.width
                elif r.type in {'HEADER', 'TOOL_HEADER'}:
                    if (r.y - region.y) > region.height / 2.0:
                        y1 -= r.height
                    else:
                        y0 += r.height
        except (AttributeError, ReferenceError):
            pass
    y0 += 64.0 * ui                     # onglets de vue et ligne de commande
    if x1 - x0 < 120.0 or y1 - y0 < 120.0:
        return 0.0, 0.0, float(region.width), float(region.height)
    return x0, y0, x1, y1


def paper_fit_view(context, area, sp, region, rv, scene, margin=1.06):
    """Cadre la feuille entière dans la partie libre de la vue 3D."""
    w, h = paper_size(scene.dessin_layout)
    fx0, fy0, fx1, fy1 = _free_rect(context, area, sp, region)
    px = min((fx1 - fx0) / (w * margin), (fy1 - fy0) / (h * margin))       # pixels par millimètre
    big = float(max(region.width, region.height, 1))
    # vue orthogonale de Blender : la plus grande dimension de la région montre view_distance x 72 / focale unités
    rv.view_distance = big * sp.lens / (72.0 * max(px, 1e-6))
    dx = (fx0 + fx1) / 2.0 - region.width / 2.0
    dy = (fy0 + fy1) / 2.0 - region.height / 2.0
    rv.view_location = (w / 2.0 - dx / px, h / 2.0 - dy / px, 0.0)
    return px


def layout_zoom_page(context):
    """Zoom Extents dans une mise en page : la feuille entière dans la vue (retourne False hors d'une mise en page)."""
    win = context.window
    if win is None or not is_layout(win.scene):
        return False
    here = getattr(context, "area", None)
    done = False
    for area, sp, region, rv in _view3d_areas(win):
        if here is None or here.type != 'VIEW_3D' or area == here:
            paper_fit_view(context, area, sp, region, rv, win.scene)
            area.tag_redraw()
            done = True
    return done


def _paper_view(context, win, area, sp, region, rv, scene, fit=True):
    """Règle une vue 3D pour la feuille : vue de dessus orthogonale sans rotation, couleurs d'objet, papier sur fond gris."""
    sh, ov = sp.shading, sp.overlay
    for key, val in (("type", 'SOLID'), ("light", 'FLAT'), ("color_type", 'OBJECT'), ("wireframe_color_type", 'OBJECT'),
                     ("background_type", 'VIEWPORT'), ("show_xray", False), ("show_shadows", False), ("show_cavity", False),
                     ("show_object_outline", False)):
        try:
            setattr(sh, key, val)
        except (TypeError, AttributeError):
            pass
    try:
        sh.background_color = (0.33, 0.34, 0.36)
    except (TypeError, AttributeError):
        pass
    for key in _OVERLAY:
        try:
            setattr(ov, key, False)
        except (TypeError, AttributeError):
            pass
    try:
        cp_set(rv, None, record=False)
    except (AttributeError, ReferenceError):
        pass
    rv.lock_rotation = False
    if rv.view_perspective == 'CAMERA':
        rv.view_perspective = 'ORTHO'
    try:
        view = context.preferences.view
        smooth = view.smooth_view
        view.smooth_view = 0
        try:
            with context.temp_override(window=win, area=area, region=region, space_data=sp):
                bpy.ops.view3d.view_axis(type='TOP')
        finally:
            view.smooth_view = smooth
    except (RuntimeError, TypeError, AttributeError):
        pass
    rv.view_perspective = 'ORTHO'
    rv.view_rotation = Quaternion((1.0, 0.0, 0.0, 0.0))
    rv.lock_rotation = True
    saved = scene.get("wd_view")
    if saved is not None and len(saved) == 3 and not fit:
        rv.view_location = (saved[0], saved[1], 0.0)
        rv.view_distance = saved[2]
    else:
        paper_fit_view(context, area, sp, region, rv, scene)


def _looks_paper(sp, rv):
    try:
        return bool(rv.lock_rotation) and rv.view_perspective == 'ORTHO' and sp.shading.light == 'FLAT' and not sp.overlay.show_floor
    except (AttributeError, ReferenceError):
        return False


def _state_to_json(st):
    return json.dumps({k: (list(v) if isinstance(v, tuple) else v) for k, v in st.items() if k != "cplane"})


def _enter_paper(context, win, scene, model=None, fit=None):
    """Passe en espace papier les vues 3D de la fenêtre qui n'y sont pas encore (leur état est gardé pour le retour)."""
    first = scene.get("wd_view") is None
    for area, sp, region, rv in _view3d_areas(win):
        ptr = area.as_pointer()
        if ptr not in _STATE["paper"]:
            if not _looks_paper(sp, rv):          # (une vue déjà réglée pour le papier : fichier enregistré sur une mise en page)
                st = _save_view(sp, rv)
                _STATE["views"][ptr] = st
                if model is not None:
                    try:
                        model["wd_layout_view"] = _state_to_json(st)      # retrouvé si le fichier est rouvert sur la mise en page
                    except (TypeError, ValueError, AttributeError):
                        pass
            _STATE["paper"].add(ptr)
        _paper_view(context, win, area, sp, region, rv, scene, fit=first if fit is None else fit)
        area.tag_redraw()


def _leave_paper(win, model):
    """Rend aux vues 3D de la fenêtre l'état qu'elles avaient avant la mise en page."""
    for area, sp, _region, rv in _view3d_areas(win):
        ptr = area.as_pointer()
        if ptr not in _STATE["paper"] and not _looks_paper(sp, rv):
            continue
        _STATE["paper"].discard(ptr)
        st = _STATE["views"].pop(ptr, None)
        if st is None and model is not None:
            try:
                st = json.loads(model.get("wd_layout_view", "") or "null")
            except (TypeError, ValueError):
                st = None
        if st is not None:
            _restore_view(sp, rv, st)
        else:                      # état inconnu : une vue de travail ordinaire
            rv.lock_rotation = False
            try:
                sp.overlay.show_floor = sp.overlay.show_axis_x = sp.overlay.show_axis_y = True
                sp.overlay.show_cursor = sp.overlay.show_relationship_lines = sp.overlay.show_object_origins = True
                sp.shading.background_type = 'THEME'
                sp.shading.light = 'STUDIO'
                rv.view_perspective = 'PERSP'
                rv.view_rotation = _axis_quat(None)
            except (TypeError, AttributeError):
                pass
        area.tag_redraw()


def layout_open(context, scene, fit=None):
    """Affiche une mise en page dans la fenêtre : la scène change, les vues 3D passent en espace papier."""
    win = context.window
    if win is None or scene is None or not is_layout(scene):
        return False
    prev = win.scene
    key = win.as_pointer()
    areas = _view3d_areas(win)
    model = None
    if not is_layout(prev):
        _STATE["last_model"][key] = prev.name
        model = prev
    else:
        _remember_paper_view(prev, areas)
    win.scene = scene
    layout_current_layer(scene)
    _enter_paper(context, win, scene, model, fit)
    _STATE["hold"] = 0.0
    if scene.dessin_layout.auto_update:
        redrawn = 0
        for o in details(scene):
            m = detail_model(o)
            if m is not None and _STATE["built"].get(o.name) != model_version(m):
                detail_rebuild(o)
                redrawn += 1
        title_refresh(scene)
        if redrawn:
            _undo_push(win, "Update Viewports")       # (objets refaits hors d'une commande annulable : voir _undo_push)
    return True


def _remember_paper_view(scene, areas):
    for _area, _sp, _region, rv in areas[:1]:
        try:
            scene["wd_view"] = [rv.view_location[0], rv.view_location[1], rv.view_distance]
        except (AttributeError, TypeError, ReferenceError):
            pass


def layout_close(context):
    """Retour au modèle : la scène et les vues 3D retrouvent l'état qu'elles avaient avant la mise en page."""
    win = context.window
    if win is None or not is_layout(win.scene):
        return False
    cur = win.scene
    areas = _view3d_areas(win)
    _remember_paper_view(cur, areas)
    name = _STATE["last_model"].get(win.as_pointer())
    model = bpy.data.scenes.get(name) if name else None
    if model is None or is_layout(model):
        model = layout_model(cur)
    if model is None:
        return False
    win.scene = model
    _leave_paper(win, model)
    return True


def _redraw():
    try:
        for win in bpy.context.window_manager.windows:
            for a in win.screen.areas:
                if a.type == 'VIEW_3D':
                    a.tag_redraw()
    except (AttributeError, RuntimeError, ReferenceError):
        pass


# --------------------------------------------------------------------------
# Suivi : modèle modifié, détails déplacés / redimensionnés / copiés / supprimés
# --------------------------------------------------------------------------

@persistent
def layout_on_depsgraph(scene=None, depsgraph=None, *args):
    """Une scène de modèle a changé : ses détails seront redessinés à la prochaine ouverture d'une mise en page."""
    try:
        if _STATE["hold"] and time.monotonic() - _STATE["hold"] > 0.5:
            _STATE["hold"] = 0.0        # quelque chose a changé depuis le dernier Annuler / Rétablir : l'entretien reprend
        if scene is not None and not is_layout(scene):
            _STATE["model_ver"][scene.name] = _STATE["model_ver"].get(scene.name, 0) + 1
    except (AttributeError, ReferenceError):
        pass


@persistent
def layout_on_undo(*args):
    """Annuler / Rétablir : l'entretien des mises en page attend le prochain changement (voir _STATE["hold"])."""
    _STATE["hold"] = time.monotonic()
    _STATE["items"] = None


def _undo_push(win, message="Layout"):
    """Pas d'annulation après une retouche faite hors d'une commande. Indispensable : Blender réutilise à l'annulation les
    blocs qu'il croit inchangés ; des objets créés ou supprimés sans pas d'annulation le font planter."""
    try:
        with bpy.context.temp_override(window=win):
            bpy.ops.ed.undo_push(message=message)
    except (RuntimeError, TypeError, AttributeError):
        pass


def layout_after_command(context, op=None):
    """Fin d'une commande dans une mise en page : ce qui en découle (détail redimensionné ou copié, cotes qui suivent leur
    détail, encre) est fait tout de suite, donc dans le même pas d'annulation que la commande.
    op : la commande qui se termine ; si elle n'est pas annulable, la retouche reçoit son propre pas d'annulation."""
    try:
        sc = context.scene
        if _STATE["busy"] or not is_layout(sc):
            return False
        _STATE["hold"] = 0.0
        layout_ink(sc)
        dims_sync(sc, moved=False)
        if layout_sync(sc):
            if op is not None and 'UNDO' not in (getattr(op, "bl_options", None) or ()):
                _undo_push(context.window)
            _redraw()
            return True
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
        pass
    return False


@persistent
def layout_on_load(*args):
    for key in ("views", "model_ver", "built", "cache", "last_model", "paper"):
        _STATE[key].clear()
    _STATE["busy"] = False
    _STATE["items"] = None
    _STATE["hold"] = 0.0


def _modal_running(win):
    try:
        return len(win.modal_operators) > 0
    except (AttributeError, RuntimeError):
        return False


def layout_ink(scene):
    """Sur le papier blanc, un objet à la couleur par défaut (blanc) serait invisible : il passe au noir, comme la couleur 7
    d'AutoCAD. Les objets d'un calque coloré ou à la couleur choisie ne sont pas touchés. Retourne le nombre d'objets changés."""
    n = 0
    try:
        for o in scene.objects:
            c = o.color
            if c[0] > 0.99 and c[1] > 0.99 and c[2] > 0.99 and not o.get(GEN) and not o.get(SHEET):
                o.color = (0.0, 0.0, 0.0, 1.0)
                n += 1
    except (AttributeError, ReferenceError, RuntimeError):
        pass
    return n


def layout_sync(scene, win=None):
    """Remet d'aplomb une mise en page après les manipulations ordinaires de Blender :
    détail mis à l'échelle (sa taille change, pas son contenu), copié (ses traits sont refaits), supprimé (ses traits partent)."""
    changed = False
    orphans = [o for o in scene.objects if o.get(GEN) and o.get(GEN) != 'detail' and o.parent is None]
    if orphans:
        with quiet():
            _remove(orphans)
        changed = True
    ids = set()
    for o in details(scene):
        d = o.dessin_detail
        if o.get("wd_id") is None or o.get("wd_id") in ids:      # détail copié : son propre identifiant
            o["wd_id"] = random.getrandbits(30)
        ids.add(o.get("wd_id"))
        sx, sy = abs(o.scale.x), abs(o.scale.y)
        rz = o.rotation_euler.z
        resized = abs(sx - 1.0) > 1e-6 or abs(sy - 1.0) > 1e-6
        if resized or abs(rz) > 1e-6 or abs(o.rotation_euler.x) > 1e-6 or abs(o.rotation_euler.y) > 1e-6:
            with quiet():
                if resized:
                    d.width, d.height = max(d.width * sx, 1.0), max(d.height * sy, 1.0)
            detail_rebuild(o)
            changed = True
        elif len(detail_children(o)) != int(o.get("wd_nchild", -1)):
            detail_rebuild(o)
            changed = True
        else:
            mp = o.get("wd_map")
            if mp is None or abs(mp[0] - o.location.x) > 1e-6 or abs(mp[1] - o.location.y) > 1e-6:
                with quiet():
                    if detail_dims_follow(o):          # détail déplacé : ses cotes le suivent
                        changed = True
    with quiet():
        if dims_sync(scene):
            changed = True
    if changed:
        title_refresh(scene)
    return changed


def layout_tick():
    """Minuteur : entretien des mises en page affichées (aucun travail tant qu'une commande est en cours)."""
    try:
        wm = bpy.context.window_manager
        if not _STATE["busy"]:
            _STATE["items"] = None          # la copie du modèle lue pour les détails n'est gardée que le temps d'une série
        for win in wm.windows:
            sc = win.scene
            if _STATE["busy"]:
                continue
            areas = _view3d_areas(win)
            if not is_layout(sc):
                # la fenêtre montre un modèle : une vue restée en espace papier (annulation, scène changée par le menu
                # de Blender) retrouve son état d'avant
                if any(a.as_pointer() in _STATE["paper"] for a, _s, _r, _v in areas):
                    _leave_paper(win, sc)
                continue
            if any(a.as_pointer() not in _STATE["paper"] for a, _s, _r, _v in areas):
                _enter_paper(bpy.context, win, sc, layout_model(sc))       # mise en page affichée sans passer par ses onglets
            for _area, _sp, _region, rv in areas:
                if rv.view_perspective != 'ORTHO' or abs(abs(rv.view_rotation.w) - 1.0) > 1e-6:
                    rv.view_perspective = 'ORTHO'
                    rv.view_rotation = Quaternion((1.0, 0.0, 0.0, 0.0))
                    rv.lock_rotation = True
            if layout_ink(sc):                  # même pendant une commande : on voit tout de suite ce que l'on vient de poser
                _redraw()
            dims_sync(sc, moved=False)          # cotes que l'on vient de poser : attachées à leur détail
            if _modal_running(win) or _STATE["hold"]:
                continue
            # commande de Blender (G, Suppr, copier-coller...) ou d'un autre add-on : la retouche a son pas d'annulation
            if layout_sync(sc, win):
                _undo_push(win)
                _redraw()
    except (AttributeError, ReferenceError, RuntimeError):
        pass
    return 0.4


_DRAW = {"handle": None}


def layout_draw_cb():
    """Cadre des détails sélectionnés, en bleu net : la couleur de sélection du thème, claire, se perd sur le papier blanc."""
    try:
        context = bpy.context
        sc = context.scene
        if not is_layout(sc) or context.mode != 'OBJECT':
            return
        sel = [o for o in details(sc) if o.select_get()]
        live = sc.objects.get(_STATE["active_vp"]) if _STATE["active_vp"] else None
        if live is not None and not is_detail(live):
            live = None
        if not sel and live is None:
            return
        act = context.view_layer.objects.active
        shader = get_shader('3D')
        gpu.state.blend_set('ALPHA')
        gpu.state.depth_test_set('NONE')
        gpu.state.line_width_set(2.0 * px_scale())
        shader.bind()
        for o in sel:
            d = o.dessin_detail
            M = o.matrix_world
            w, h = d.width / 2.0, d.height / 2.0
            c = [tuple(M @ Vector((x, y, 0.0))) for x, y in ((-w, -h), (w, -h), (w, h), (-w, h))]
            shader.uniform_float("color", (0.04, 0.4, 0.95, 1.0) if o == act else (0.25, 0.55, 0.95, 0.85))
            batch_for_shader(shader, 'LINES', {"pos": [c[0], c[1], c[1], c[2], c[2], c[3], c[3], c[0]]}).draw(shader)
        if live is not None:              # fenêtre dans laquelle on travaille : bord épais, comme l'espace objet d'AutoCAD
            d = live.dessin_detail
            M = live.matrix_world
            w, h = d.width / 2.0, d.height / 2.0
            c = [tuple(M @ Vector((x, y, 0.0))) for x, y in ((-w, -h), (w, -h), (w, h), (-w, h))]
            gpu.state.line_width_set(ACTIVE_VP_WIDTH * px_scale())
            shader.uniform_float("color", (0.04, 0.4, 0.95, 1.0))
            batch_for_shader(shader, 'LINES', {"pos": [c[0], c[1], c[1], c[2], c[2], c[3], c[3], c[0]]}).draw(shader)
        gpu.state.line_width_set(1.0)
        gpu.state.blend_set('NONE')
    except (AttributeError, ReferenceError, RuntimeError, ValueError):
        pass


# --------------------------------------------------------------------------
# Export : entités de la feuille
# --------------------------------------------------------------------------

def _local_matrix(o):
    return (o.parent.matrix_basis @ o.matrix_basis) if o.parent is not None else o.matrix_basis


def _spline_paths(o):
    M = _local_matrix(o)
    out = []
    for sp in o.data.splines:
        n = len(sp.points)
        if n < 2:
            continue
        co = np.empty(n * 4)
        sp.points.foreach_get("co", co)
        P = co.reshape(-1, 4)[:, :3]
        A = np.array(M, dtype=np.float64)
        W = P @ A[:3, :3].T + A[:3, 3]
        out.append((W[:, :2], bool(sp.use_cyclic_u)))
    return out


def _shown(o, view_layer):
    try:
        return not o.hide_viewport and o.visible_get(view_layer=view_layer)
    except (RuntimeError, ReferenceError, AttributeError, TypeError):
        return True


def layout_entities(scene):
    """Tout ce qui s'imprime sur une mise en page, en mm de papier : entités ('L', ...) et ('F', ...) du moteur d'export,
    dans l'ordre du tracé (aplats de hachures, traits, puis textes)."""
    L = scene.dessin_layout
    mode = L.print_color
    try:
        vl = scene.view_layers[0]
    except IndexError:
        vl = None
    under, lines, over = [], [], []
    for o in scene.objects:
        role = o.get(SHEET)
        if role in ('frame', 'title') and o.type == 'CURVE' and _shown(o, vl):
            lines.append(('L', _spline_paths(o), L.lw_frame if role == 'frame' else L.lw_annot, (0.0, 0.0, 0.0), None,
                          "Frame" if role == 'frame' else "Title block"))
    for det in details(scene):
        if not _shown(det, vl):
            continue
        if det.dessin_detail.show_border:
            lines.append(('L', _spline_paths(det), L.lw_border, (0.0, 0.0, 0.0), None, "Viewport borders"))
        for c in det.children:
            role = c.get(GEN)
            if c.type != 'CURVE' or role not in ('vis', 'hid', 'ann', 'fill'):
                continue
            col = print_color(c.color, mode)
            if role == 'vis':
                lines.append(('L', _spline_paths(c), L.lw_visible, col, None, "Visible"))
            elif role == 'hid':
                lines.insert(0, ('L', _spline_paths(c), L.lw_hidden, col, (3.0, 1.5), "Hidden"))
            elif role == 'ann':
                lines.append(('L', _spline_paths(c), L.lw_annot, col, None, "Annotations"))
            else:
                loops = [P for P, _closed in _spline_paths(c)]
                counts = list(c.get("wd_fill_n", [len(loops)]))
                colors = list(c.get("wd_fill_c", []))
                flags = list(c.get("wd_fill_t", []))
                i = 0
                for k, n in enumerate(counts):
                    grp = loops[i:i + n]
                    i += n
                    rgb = tuple(colors[k * 3:k * 3 + 3]) if len(colors) >= k * 3 + 3 else (0.0, 0.0, 0.0)
                    is_text = bool(flags[k]) if k < len(flags) else True
                    (over if is_text else under).append(('F', grp, print_color(rgb, mode), "Text" if is_text else "Fills"))
    # tout ce qui est dessiné sur la feuille (outils habituels) et les textes générés : lus comme un modèle vu de dessus
    items = le.collect_model(scene, (), True)
    for o in scene.objects:                       # textes générés (cartouche, étiquettes) : exclus de collect_model
        if o.type == 'FONT' and (o.get(SHEET) or o.get(GEN)) and _shown(o, vl) and (o.parent is None or _shown(o.parent, vl)):
            try:
                V, E, cnt, T = le._temp_mesh(o.data, le._setup_font)
                it = le.Item('ANNOT', o.name, tuple(o.color[:3]))
                it.text = True
                A = np.array(_local_matrix(o), dtype=np.float64)
                le._fill_item(it, V @ A[:3, :3].T + A[:3, 3], E, cnt, T)
                items.append(it)
            except (RuntimeError, AttributeError, TypeError, ReferenceError):
                continue
    if items:
        P = le.project_model(items, le.Projector(Quaternion((1.0, 0.0, 0.0, 0.0))), 'WIREFRAME')
        w, h = paper_size(L)
        geo = le.to_paper(P, w / 2.0, h / 2.0, 1.0, w, h)
        off = np.array((w / 2.0, h / 2.0))
        for _role, color, paths in geo["lines"]:
            lines.append(('L', [(p + off, c) for p, c in paths], L.lw_annot, print_color(color, mode), None, "Sheet"))
        for color, loops, _polys, is_text in geo["fills"]:
            (over if is_text else under).append(('F', [lp + off for lp in loops], print_color(color, mode),
                                                 "Text" if is_text else "Fills"))
    return under + lines + over


def layout_page(scene):
    w, h = paper_size(scene.dessin_layout)
    return {"name": scene.name, "w": w, "h": h, "ents": layout_entities(scene)}


# --------------------------------------------------------------------------
# Opérateurs : mises en page
# --------------------------------------------------------------------------

def _layout_by_name(name):
    sc = bpy.data.scenes.get(name)
    return sc if sc is not None and is_layout(sc) else None


class DESSIN_OT_layout_new(bpy.types.Operator):
    bl_idname = "dessin.layout_new"
    bl_label = "New Layout"
    bl_description = ("Creates a layout: a paper sheet with viewports of the model at scale, a title block, "
                      "and vector PDF / SVG / DXF export")
    bl_options = {'REGISTER', 'UNDO'}

    name: bpy.props.StringProperty(name="Name", default="Layout")
    paper: bpy.props.EnumProperty(name="Paper", items=PAPER_ITEMS, default='A3')
    orientation: bpy.props.EnumProperty(name="Orientation", default='LANDSCAPE',
                                        items=(('LANDSCAPE', "Landscape", ""), ('PORTRAIT', "Portrait", "")))
    custom_w: bpy.props.FloatProperty(name="Width (mm)", default=420.0, min=10.0)
    custom_h: bpy.props.FloatProperty(name="Height (mm)", default=297.0, min=10.0)
    margin: bpy.props.FloatProperty(name="Margin (mm)", default=10.0, min=0.0, soft_max=40.0)
    title_block: bpy.props.BoolProperty(name="Title block", default=True)
    initial: bpy.props.EnumProperty(name="Viewports", default='FOUR',
                                    items=(('NONE', "None", "Empty sheet: draw the viewports yourself"),
                                           ('ONE', "1 view", "One viewport: the Top view"),
                                           ('FOUR', "4 views", "Top, Front, Right and an isometric view, aligned, at the same scale")))

    def invoke(self, context, event):
        self.name = unique_layout_name("Layout 1")          # Layout 1, Layout 2, Layout 3...
        return context.window_manager.invoke_props_dialog(self, width=300)

    def draw(self, context):
        lay = self.layout
        lay.use_property_split = True
        lay.use_property_decorate = False
        lay.prop(self, "name")
        lay.prop(self, "paper")
        if self.paper == 'CUSTOM':
            lay.prop(self, "custom_w")
            lay.prop(self, "custom_h")
        lay.prop(self, "orientation")
        lay.prop(self, "margin")
        lay.prop(self, "title_block")
        lay.prop(self, "initial")

    def execute(self, context):
        model = model_of(context.scene)
        if model is None:
            self.report({'WARNING'}, "No model scene")
            return {'CANCELLED'}
        sc = layout_create(model, self.name, self.paper, self.orientation, self.margin, self.title_block,
                           (self.custom_w, self.custom_h))
        if self.initial != 'NONE':
            layout_initial_details(sc, self.initial)
        layout_open(context, sc, fit=True)
        try:
            idle_tool()            # le bouton Layout de la barre reste armé sinon : chaque clic rouvrirait la boîte
        except (RuntimeError, TypeError, AttributeError):
            pass
        self.report({'INFO'}, f"Layout '{sc.name}': {paper_label(sc.dessin_layout)}, {len(details(sc))} viewport(s)")
        return {'FINISHED'}


_LAST_TAB = {"name": None, "time": 0.0}


class DESSIN_OT_layout_open(bpy.types.Operator):
    bl_idname = "dessin.layout_open"
    bl_label = "Open Layout"
    bl_description = "Shows this layout (paper space). Double-click its tab to rename it"
    bl_options = {'INTERNAL'}

    name: bpy.props.StringProperty(options={'SKIP_SAVE'})

    def invoke(self, context, event):
        now = time.monotonic()
        double = _LAST_TAB["name"] == self.name and now - _LAST_TAB["time"] < 0.45
        _LAST_TAB["name"], _LAST_TAB["time"] = self.name, now
        if double or (event is not None and event.ctrl):
            _LAST_TAB["name"] = None
            return bpy.ops.dessin.layout_rename('INVOKE_DEFAULT', name=self.name)
        return self.execute(context)

    def execute(self, context):
        sc = _layout_by_name(self.name)
        if sc is None:
            self.report({'WARNING'}, f"Layout '{self.name}' not found")
            return {'CANCELLED'}
        if context.window is not None and context.window.scene == sc:
            return {'FINISHED'}
        if not layout_open(context, sc):
            return {'CANCELLED'}
        return {'FINISHED'}


class DESSIN_OT_layout_close(bpy.types.Operator):
    bl_idname = "dessin.layout_close"
    bl_label = "Model Space"
    bl_description = "Leaves the layout and goes back to the model, with the view you had"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        if not is_layout(context.scene):
            return {'CANCELLED'}
        return {'FINISHED'} if layout_close(context) else {'CANCELLED'}


class DESSIN_OT_layout_next(bpy.types.Operator):
    bl_idname = "dessin.layout_next"
    bl_label = "Next Layout"
    bl_description = "Opens the next layout (from the model: the first one)"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        ls = layouts()
        if not ls:
            self.report({'INFO'}, "No layout yet: use Layout to create one")
            return {'CANCELLED'}
        cur = context.scene
        nxt = ls[(ls.index(cur) + 1) % len(ls)] if cur in ls else ls[0]
        if nxt != cur:
            layout_open(context, nxt)
        return {'FINISHED'}


class DESSIN_OT_layout_rename(bpy.types.Operator):
    bl_idname = "dessin.layout_rename"
    bl_label = "Rename Layout"
    bl_description = "Renames this layout"
    bl_options = {'REGISTER', 'UNDO'}

    name: bpy.props.StringProperty(options={'SKIP_SAVE'})
    new_name: bpy.props.StringProperty(name="Name")

    def invoke(self, context, event):
        self.new_name = self.name
        return context.window_manager.invoke_props_dialog(self, width=260)

    def draw(self, context):
        self.layout.prop(self, "new_name", text="Name")

    def execute(self, context):
        sc = _layout_by_name(self.name)
        new = self.new_name.strip()
        if sc is None or not new:
            return {'CANCELLED'}
        if new != sc.name:
            old = sc.name
            sc.name = unique_layout_name(new)
            if sc.dessin_layout.t_title == old:
                sc.dessin_layout.t_title = sc.name
        _redraw()
        return {'FINISHED'}


class DESSIN_OT_layout_delete(bpy.types.Operator):
    bl_idname = "dessin.layout_delete"
    bl_label = "Delete Layout"
    bl_description = "Deletes this layout and everything drawn on it (the model is not touched)"
    bl_options = {'REGISTER', 'UNDO'}

    name: bpy.props.StringProperty(options={'SKIP_SAVE'})

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        sc = _layout_by_name(self.name)
        if sc is None:
            return {'CANCELLED'}
        for win in context.window_manager.windows:
            if win.scene == sc:
                with context.temp_override(window=win):
                    layout_close(bpy.context)
        if any(win.scene == sc for win in context.window_manager.windows):
            self.report({'WARNING'}, "This layout is still displayed")
            return {'CANCELLED'}
        objs = [o for o in sc.objects if len(o.users_scene) <= 1]      # (un objet aussi lié à une autre scène y reste)
        cols = list(sc.collection.children_recursive)
        for o in objs:
            _STATE["cache"].pop(o.name, None)
        _remove(objs)
        for c in cols:
            try:
                if not len(c.all_objects):
                    bpy.data.collections.remove(c)
            except (ReferenceError, RuntimeError):
                pass
        bpy.data.scenes.remove(sc)
        _redraw()
        return {'FINISHED'}


class DESSIN_OT_layout_erase(bpy.types.Operator):
    bl_idname = "dessin.layout_erase"
    bl_label = "Delete"
    bl_description = ("Layout: deletes the selected objects. A viewport goes with its linework and the dimensions placed on it, "
                      "in a single undo step")
    bl_options = {'REGISTER', 'UNDO'}

    confirm: bpy.props.BoolProperty(default=False, options={'SKIP_SAVE', 'HIDDEN'})

    @classmethod
    def poll(cls, context):
        # hors d'une mise en page, la touche garde la commande de Blender (cette commande ne se propose pas)
        return is_layout(context.scene) and context.mode == 'OBJECT' and bool(context.selected_objects)

    def invoke(self, context, event):
        if self.confirm:
            return context.window_manager.invoke_confirm(self, event)
        return self.execute(context)

    def execute(self, context):
        try:
            res = bpy.ops.object.delete(use_global=False, confirm=False)
        except RuntimeError:
            return {'CANCELLED'}
        if 'FINISHED' not in res:
            return {'CANCELLED'}
        _STATE["hold"] = 0.0
        layout_sync(context.scene)           # traits et cotes des détails supprimés : dans le même pas d'annulation
        _redraw()
        return {'FINISHED'}


_ERASE_KEYS = []


def erase_keys_register():
    """Suppr / X dans une mise en page : la suppression et ses suites (traits, cotes du détail) en un seul pas d'annulation."""
    try:
        wm = bpy.context.window_manager
        kc = wm.keyconfigs.addon if wm is not None else None
        if kc is None:
            return
        km = kc.keymaps.new(name="Object Mode", space_type='EMPTY')
        for key, confirm in (('DEL', False), ('X', True)):
            kmi = km.keymap_items.new("dessin.layout_erase", key, 'PRESS')
            kmi.properties.confirm = confirm
            _ERASE_KEYS.append((km, kmi))
    except (AttributeError, RuntimeError, TypeError):
        pass


def erase_keys_unregister():
    for km, kmi in _ERASE_KEYS:
        try:
            km.keymap_items.remove(kmi)
        except (RuntimeError, ReferenceError, TypeError):
            pass
    _ERASE_KEYS.clear()


class DESSIN_OT_layout_duplicate(bpy.types.Operator):
    bl_idname = "dessin.layout_duplicate"
    bl_label = "Duplicate Layout"
    bl_description = "Makes a copy of this layout: same sheet, same viewports, same annotations"
    bl_options = {'REGISTER', 'UNDO'}

    name: bpy.props.StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        src = _layout_by_name(self.name) or (context.scene if is_layout(context.scene) else None)
        if src is None:
            return {'CANCELLED'}
        L = src.dessin_layout
        sc = layout_create(layout_model(src), src.name + " copy", L.paper, L.orientation, L.margin, L.show_title,
                           (L.custom_w, L.custom_h))
        D = sc.dessin_layout
        with quiet():
            for key in ("show_frame", "t_project", "t_title", "t_author", "t_date", "t_revision", "t_scale",
                        "label_size", "lw_visible", "lw_hidden", "lw_annot", "lw_frame", "lw_border", "show_lineweights",
                        "print_color", "auto_update"):
                setattr(D, key, getattr(L, key))
            for key in DIM_STYLE_FIELDS + ("couleur", "epaisseur_trait"):      # même style de cote que l'original
                try:
                    setattr(sc.dessin, key, getattr(src.dessin, key))
                except (AttributeError, TypeError, ValueError):
                    pass
        # objets de la feuille : les détails (leurs traits seront refaits) et les annotations, à l'identique
        mapping = {}
        for o in src.objects:
            if o.get(SHEET) or (o.get(GEN) and o.get(GEN) != 'detail'):
                continue
            c = o.copy()
            if o.data is not None:
                c.data = o.data.copy()
            mapping[o] = c
            key = next((uc.get(COL) for uc in o.users_collection if uc.get(COL)), None)
            (layout_collection(sc, key) if key else sc.collection).objects.link(c)
        for o, c in mapping.items():
            if o.parent in mapping:
                c.parent = mapping[o.parent]
        paper_rebuild(sc)
        for o in details(sc):
            detail_rebuild(o, force=True)
        layout_open(context, sc, fit=True)
        return {'FINISHED'}


class DESSIN_OT_layout_page_setup(bpy.types.Operator):
    bl_idname = "dessin.layout_page_setup"
    bl_label = "Page Setup"
    bl_description = "Paper size, orientation, margin and title block of the current layout"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return is_layout(context.scene)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=320)

    def draw(self, context):
        draw_page_settings(self.layout, context.scene.dessin_layout)

    def execute(self, context):
        return {'FINISHED'}


# --------------------------------------------------------------------------
# Opérateurs : détails
# --------------------------------------------------------------------------

def selected_details(context):
    """Détails visés par une commande : ceux sélectionnés, sinon le détail actif, sinon l'unique détail de la feuille."""
    sc = context.scene
    if not is_layout(sc):
        return []
    out = [o for o in (getattr(context, "selected_objects", None) or ()) if is_detail(o)]
    act = context.view_layer.objects.active
    if not out and is_detail(act):
        out = [act]
    if not out:
        ds = details(sc)
        if len(ds) == 1:
            out = ds
    return out


def active_detail(context):
    act = context.view_layer.objects.active if context.view_layer is not None else None
    if is_detail(act) and act.name in context.scene.objects:
        return act
    ds = selected_details(context)
    return ds[0] if ds else None


class DESSIN_OT_layout_detail(DessinBase):
    bl_idname = "dessin.layout_detail"
    bl_label = "Viewport"
    bl_description = ("Layout: draws a viewport of the model on the sheet (first corner, then opposite corner). "
                      "The view is the one chosen in the Layout panel; the scale is fitted, then set in the panel")

    TITLE = "Viewport"
    PROP = ()
    NEEDED = 2
    NUMFIELDS = 2
    HAS_CENTER = True
    EDIT_OK = False

    # même saisie et même aperçu que le rectangle (fonctions réutilisées, pas d'héritage entre classes Blender)
    compute = DESSIN_OT_rectangle.compute

    def invoke(self, context, event):
        if not is_layout(context.scene):
            # hors d'une mise en page : rien à dessiner ; le survol ne dit rien, le clic explique quoi faire
            if event is not None and event.type == 'MOUSEMOVE':
                return {'CANCELLED', 'PASS_THROUGH'}
            if event is not None and event.type == 'LEFTMOUSE' and cmd_click_idle(context, event):
                return {'CANCELLED'}
            self.report({'WARNING'}, "Viewport: open a layout first (Layout command, or the tabs under the view)")
            return {'CANCELLED'}
        return DessinBase.invoke(self, context, event)

    def prompt(self):
        if not self.points:
            return "first corner of the detail" + (" (center)" if self.center else "") + "   [C: from center]"
        return "opposite corner   (or type width, Tab, height, Enter)"

    def build(self, context, spec):
        if spec[0] != 'rect':
            return None
        xs = [p.x for p in spec[1]]
        ys = [p.y for p in spec[1]]
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        if w < 2.0 or h < 2.0:
            self.report({'WARNING'}, "Viewport too small")
            return None
        sc = context.scene
        obj = detail_create(sc, (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0, w, h, sc.dessin_layout.new_view)
        try:
            for o in context.selected_objects:
                o.select_set(False)
            obj.select_set(True)
            context.view_layer.objects.active = obj
        except (RuntimeError, ReferenceError):
            pass
        return obj

    def after_finish(self, context):
        if getattr(self, "tool_id", None):
            try:
                idle_tool()
            except (RuntimeError, TypeError):
                pass


class DESSIN_OT_detail_add(bpy.types.Operator):
    bl_idname = "dessin.detail_add"
    bl_label = "Add Viewport"
    bl_description = "Adds a viewport with this view in the middle of the free area of the sheet (move and resize it afterwards)"
    bl_options = {'REGISTER', 'UNDO'}

    view: bpy.props.EnumProperty(name="View", items=VIEW_ITEMS[:-1], default='TOP')

    @classmethod
    def poll(cls, context):
        return is_layout(context.scene)

    def execute(self, context):
        sc = context.scene
        x0, y0, x1, y1 = usable_rect(sc.dessin_layout)
        w, h = (x1 - x0) * 0.45, (y1 - y0) * 0.45
        n = len(details(sc))
        obj = detail_create(sc, (x0 + x1) / 2.0 + (n % 4) * 8.0, (y0 + y1) / 2.0 - (n % 4) * 8.0, w, h, self.view)
        for o in context.selected_objects:
            o.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        return {'FINISHED'}


class DESSIN_OT_detail_update(bpy.types.Operator):
    bl_idname = "dessin.detail_update"
    bl_label = "Update Viewports"
    bl_description = "Redraws the viewports from the model (the selected ones, or all of them)"
    bl_options = {'REGISTER', 'UNDO'}

    all: bpy.props.BoolProperty(name="All", default=False, options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return is_layout(context.scene)

    def execute(self, context):
        sc = context.scene
        objs = details(sc) if self.all else (selected_details(context) or details(sc))
        t0 = time.monotonic()
        _STATE["items"] = None              # Update : le modèle est relu (une fois pour toute la série)
        for o in objs:
            detail_rebuild(o, force=True)
        title_refresh(sc)
        layout_refresh_dims(sc)
        self.report({'INFO'}, f"{len(objs)} viewport(s) updated in {time.monotonic() - t0:.1f} s")
        return {'FINISHED'}


class DESSIN_OT_detail_fit(bpy.types.Operator):
    bl_idname = "dessin.detail_fit"
    bl_label = "Fit Viewport"
    bl_description = ("Frames the whole model in the selected viewports: centers it and picks the largest standard scale that fits "
                      "(Keep scale: only centers)")
    bl_options = {'REGISTER', 'UNDO'}

    keep_scale: bpy.props.BoolProperty(name="Keep scale", default=False, options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return is_layout(context.scene)

    def execute(self, context):
        objs = [o for o in selected_details(context)]
        if not objs:
            self.report({'INFO'}, "Select a viewport first (click its border)")
            return {'CANCELLED'}
        done = 0
        for o in objs:
            if o.dessin_detail.locked:
                continue
            if detail_fit(o, pick_scale=not self.keep_scale):
                done += 1
        if not done:
            self.report({'INFO'}, "Nothing to fit (viewport locked, or empty model)")
            return {'CANCELLED'}
        return {'FINISHED'}


class DESSIN_OT_detail_scale(bpy.types.Operator):
    bl_idname = "dessin.detail_scale"
    bl_label = "Viewport Scale"
    bl_description = "Sets the scale of the selected viewports: type 1:20, 1/50, 2:1, or just 25 for 1:25"
    bl_options = {'REGISTER', 'UNDO'}

    text: bpy.props.StringProperty(name="Scale", default="1:10")

    @classmethod
    def poll(cls, context):
        return is_layout(context.scene)

    def invoke(self, context, event):
        objs = selected_details(context)
        if not objs:
            self.report({'INFO'}, "Select a viewport first (click its border)")
            return {'CANCELLED'}
        self.text = le.fmt_scale(objs[0].dessin_detail.scale)
        return context.window_manager.invoke_props_dialog(self, width=240)

    def draw(self, context):
        self.layout.prop(self, "text")

    def execute(self, context):
        den = le.parse_scale(self.text)
        if den is None:
            self.report({'WARNING'}, "Type a scale such as 1:20, 2:1 or 25")
            return {'CANCELLED'}
        n = 0
        for o in selected_details(context):
            if not o.dessin_detail.locked:
                o.dessin_detail.scale = den
                n += 1
        if not n:
            self.report({'INFO'}, "The viewport is locked")
            return {'CANCELLED'}
        title_refresh(context.scene)
        return {'FINISHED'}


def _model_view_items(self, context):
    model = model_of(context.scene) if context is not None else None
    items = [('CURRENT', "Current model view", "The 3D view you had in the model before opening the layout")]
    if model is not None:
        try:
            items += [(v.name, v.name, "Named view of the model") for v in model.dessin_views if not v.base]
        except (AttributeError, ReferenceError):
            pass
    _model_view_items.cache = items
    return items


_model_view_items.cache = []


class DESSIN_OT_detail_view_set(bpy.types.Operator):
    bl_idname = "dessin.detail_view_set"
    bl_label = "Use a Model View"
    bl_description = ("Shows in the selected viewport a view copied from the model: the 3D view you had before opening the layout, "
                      "or one of the named views (a perspective view stays in perspective)")
    bl_options = {'REGISTER', 'UNDO'}

    source: bpy.props.EnumProperty(name="View", items=_model_view_items)

    @classmethod
    def poll(cls, context):
        return is_layout(context.scene)

    def invoke(self, context, event):
        if not selected_details(context):
            self.report({'INFO'}, "Select a viewport first (click its border)")
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self, width=280)

    def draw(self, context):
        self.layout.prop(self, "source", text="")

    def execute(self, context):
        objs = selected_details(context)
        if not objs:
            return {'CANCELLED'}
        model = model_of(context.scene)
        rot = loc = dist = None
        persp = False
        label = ""
        if self.source == 'CURRENT':
            st = None
            if context.area is not None:
                st = _STATE["views"].get(context.area.as_pointer())
            if st is None:
                st = next(iter(_STATE["views"].values()), None)
            if st is None:
                self.report({'WARNING'}, "The model view is not known: open the layout from the model, or use a named view")
                return {'CANCELLED'}
            rot, loc, dist, persp = st["rot"], st["loc"], st["dist"], st["persp"] != 'ORTHO'
        else:
            v = find_view(model, self.source) if model is not None else None
            if v is None:
                self.report({'WARNING'}, f"View '{self.source}' not found")
                return {'CANCELLED'}
            rot, persp, label = tuple(v.rot), bool(v.persp), v.name
            if v.full:
                loc, dist = tuple(v.loc), v.dist
        for o in objs:
            d = o.dessin_detail
            with quiet():
                d.view = 'CUSTOM'
                d.rot = rot
                d.view_label = label
                d.persp = persp
                if loc is not None and persp:
                    d.center = loc
                    d.cam_dist = max(dist, 1e-6)
            if persp:
                detail_rebuild(o, force=True)
            else:
                detail_fit(o, pick_scale=False)
        return {'FINISHED'}


class DESSIN_OT_detail_layer(bpy.types.Operator):
    bl_idname = "dessin.detail_layer"
    bl_label = "Hide / Show Layer in Viewport"
    bl_description = "Hides or shows this layer of the model in the selected viewports only"
    bl_options = {'REGISTER', 'UNDO'}

    layer: bpy.props.StringProperty(options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return is_layout(context.scene)

    def execute(self, context):
        objs = selected_details(context)
        if not objs or not self.layer:
            return {'CANCELLED'}
        hide = self.layer not in detail_hidden(objs[0].dessin_detail)
        for o in objs:
            names = detail_hidden(o.dessin_detail)
            if hide and self.layer not in names:
                names.append(self.layer)
            elif not hide and self.layer in names:
                names.remove(self.layer)
            o.dessin_detail.hidden_layers = "\n".join(names)
        return {'FINISHED'}


class DESSIN_OT_detail_pan(bpy.types.Operator):
    bl_idname = "dessin.detail_pan"
    bl_label = "Pan Viewport"
    bl_description = ("Works inside a viewport, like model space in AutoCAD: double-click inside it (or MS), then drag to pan "
                      "the model; wheel: next / previous standard scale. Double-click outside, Enter, Esc or right-click: "
                      "back to the sheet")
    bl_options = {'REGISTER', 'UNDO'}

    pick: bpy.props.BoolProperty(default=False, options={'SKIP_SAVE', 'HIDDEN'})     # lancé par un double-clic dans la vue

    @classmethod
    def poll(cls, context):
        return is_layout(context.scene) and context.area is not None and context.area.type == 'VIEW_3D' and context.mode == 'OBJECT'

    def paper_point(self, context, event):
        from bpy_extras.view3d_utils import region_2d_to_location_3d
        region = next((r for r in context.area.regions if r.type == 'WINDOW'), None)
        rv = context.area.spaces.active.region_3d
        if region is None:
            return None
        p = region_2d_to_location_3d(region, rv, (event.mouse_x - region.x, event.mouse_y - region.y), Vector((0.0, 0.0, 0.0)))
        return Vector((p.x, p.y))

    def invoke(self, context, event):
        self.obj = None
        self.start = None
        self.changed = False
        if self.pick:
            # double-clic : seulement dans une fenêtre, et pas sur une barre ou un panneau (le clic garde alors son usage)
            o = None
            if event is not None and not double_click_blocked(context, event):
                p = self.paper_point(context, event)
                o = detail_at(context.scene, p.x, p.y) if p is not None else None
            if o is None:
                return {'CANCELLED', 'PASS_THROUGH'}
        else:
            o = active_detail(context)
        self.activate(context, o)
        context.window_manager.modal_handler_add(self)
        self.status(context)
        return {'RUNNING_MODAL'}

    def activate(self, context, o):
        """La fenêtre dans laquelle on travaille : son bord est épaissi (les poignées s'effacent pendant ce temps)."""
        _STATE["active_vp"] = o.name if o is not None else None
        _redraw()

    def status(self, context, done=False):
        try:
            context.workspace.status_text_set(None if done else "Viewport: drag inside it to pan the model  ·  Wheel: scale  ·  "
                                              "Double-click outside, Enter or Esc: back to the sheet")
        except (AttributeError, RuntimeError):
            pass

    def leave(self, context):
        for c in (detail_children(self.obj) if self.obj is not None and self.start is not None else ()):
            c.location.x = c.location.y = 0.0
        self.status(context, True)
        self.activate(context, None)
        if self.changed:
            layout_refresh_dims(context.scene)
        return {'FINISHED'} if self.changed else {'CANCELLED'}

    def apply(self, context, delta):
        o = self.obj
        d = o.dessin_detail
        model = detail_model(o)
        if model is None:
            return
        k = mm_per_unit(model) / max(d.scale, 1e-9)
        proj = detail_projector(d)
        d.center = Vector(d.center) - (proj.right * delta.x + proj.up * delta.y) / k     # (update : le détail est redessiné)
        self.changed = True

    def modal(self, context, event):
        et = event.type
        if et in {'ESC', 'RET', 'NUMPAD_ENTER', 'RIGHTMOUSE', 'SPACE'} and event.value == 'PRESS':
            return self.leave(context)
        if et == 'LEFTMOUSE' and event.value in {'PRESS', 'DOUBLE_CLICK'}:
            p = self.paper_point(context, event)
            o = detail_at(context.scene, p.x, p.y) if p is not None else None
            if o is None:
                if event.value == 'DOUBLE_CLICK':          # double-clic hors de toute fenêtre : retour à la feuille (AutoCAD)
                    return self.leave(context)
                return {'RUNNING_MODAL'}
            self.activate(context, o)                      # (cliquer dans une autre fenêtre la rend active)
            if o.dessin_detail.locked:
                self.report({'INFO'}, "This viewport is locked (Display Locked): uncheck Locked to pan or zoom in it")
                return {'RUNNING_MODAL'}
            self.obj, self.start = o, p
            self.base = {c.name: (c.location.x, c.location.y) for c in detail_children(o)}
            return {'RUNNING_MODAL'}
        if et == 'MOUSEMOVE' and self.start is not None and self.obj is not None:
            p = self.paper_point(context, event)
            if p is not None:
                delta = p - self.start
                for c in detail_children(self.obj):            # aperçu : les traits suivent la souris, le cadre les découpera au relâchement
                    if c.get(GEN) != 'label':
                        bx, by = self.base.get(c.name, (0.0, 0.0))
                        c.location.x, c.location.y = bx + delta.x, by + delta.y
            return {'RUNNING_MODAL'}
        if et == 'LEFTMOUSE' and event.value == 'RELEASE' and self.start is not None:
            p = self.paper_point(context, event)
            if p is not None and self.obj is not None:
                self.apply(context, p - self.start)
            self.start = None
            return {'RUNNING_MODAL'}
        if et in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} and self.start is None:
            p = self.paper_point(context, event)
            o = detail_at(context.scene, p.x, p.y) if p is not None else None
            if o is None:
                return {'PASS_THROUGH'}
            d = o.dessin_detail
            if d.locked:
                return {'RUNNING_MODAL'}
            dens = [den for _k, _n, den in le.SCALES]
            if et == 'WHEELUPMOUSE':
                nxt = max([x for x in dens if x < d.scale * (1 - 1e-9)], default=None)
            else:
                nxt = min([x for x in dens if x > d.scale * (1 + 1e-9)], default=None)
            if nxt is not None:
                self.obj = o
                self.activate(context, o)
                d.scale = nxt
                self.changed = True
                title_refresh(context.scene)
            return {'RUNNING_MODAL'}
        if et in {'MIDDLEMOUSE', 'TRACKPADPAN', 'TRACKPADZOOM', 'MOUSEROTATE'}:
            return {'PASS_THROUGH'}
        return {'RUNNING_MODAL'}


class DESSIN_OT_detail_text_match(bpy.types.Operator):
    bl_idname = "dessin.detail_text_match"
    bl_label = "Match Model Text Height"
    bl_description = ("Sets the text height of the model dimensions so that they print at the height typed here, "
                      "in the scale of the selected viewport (the dimensions of the model are rebuilt)")
    bl_options = {'REGISTER', 'UNDO'}

    height: bpy.props.FloatProperty(name="Height on paper (mm)", default=2.5, min=0.5, max=50.0)

    @classmethod
    def poll(cls, context):
        return is_layout(context.scene)

    def invoke(self, context, event):
        if not selected_details(context):
            self.report({'INFO'}, "Select a viewport first (click its border)")
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self, width=280)

    def draw(self, context):
        self.layout.prop(self, "height")

    def execute(self, context):
        objs = selected_details(context)
        if not objs:
            return {'CANCELLED'}
        o = objs[0]
        model = detail_model(o)
        if model is None:
            return {'CANCELLED'}
        h = self.height * o.dessin_detail.scale / mm_per_unit(model)
        win = context.window
        cur = win.scene
        try:                     # les cotes du modèle sont refaites dans leur scène
            win.scene = model
            model.dessin.taille_texte = h
        finally:
            win.scene = cur
        _STATE["items"] = None
        for d in details(cur):
            if detail_model(d) == model:
                detail_rebuild(d, force=True)
        self.report({'INFO'}, f"Model text height: {h:.4g} (prints {self.height:g} mm at {le.fmt_scale(o.dessin_detail.scale)})")
        return {'FINISHED'}


# --------------------------------------------------------------------------
# Opérateurs : export
# --------------------------------------------------------------------------

def _export_name(scene, ext, all_layouts=False):
    base = os.path.splitext(os.path.basename(bpy.data.filepath))[0] if bpy.data.filepath else "layout"
    name = base if all_layouts else f"{base} - {scene.name}" if bpy.data.filepath else scene.name
    safe = "".join(ch if ch.isalnum() or ch in " -_." else "_" for ch in name).strip() or "layout"
    folder = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else os.path.expanduser("~")
    return os.path.join(folder, safe + ext)


class _LayoutExport:
    bl_options = {'REGISTER'}
    filepath: bpy.props.StringProperty(subtype='FILE_PATH', options={'SKIP_SAVE'})
    all_layouts: bpy.props.BoolProperty(name="All layouts", default=False,
                                        description="Exports every layout of the file instead of the current one")
    check_existing: bpy.props.BoolProperty(default=True, options={'HIDDEN'})
    EXT = ".pdf"

    @classmethod
    def poll(cls, context):
        return bool(layouts())

    def targets(self, context):
        if self.all_layouts or not is_layout(context.scene):
            return layouts()
        return [context.scene]

    def invoke(self, context, event):
        if not is_layout(context.scene):
            self.all_layouts = True
        if not self.filepath:
            sc = context.scene if is_layout(context.scene) else layouts()[0]
            self.filepath = _export_name(sc, self.EXT, self.all_layouts)
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        scs = self.targets(context)
        if not scs:
            self.report({'WARNING'}, "No layout to export")
            return {'CANCELLED'}
        name = os.path.basename(self.filepath or "")
        if not name or name.startswith(".") and name.lower() == self.EXT:
            self.report({'WARNING'}, "Export: no file name")      # (commande lancée sans passer par le choix du fichier)
            return {'CANCELLED'}
        path = bpy.path.ensure_ext(bpy.path.abspath(self.filepath), self.EXT)
        t0 = time.monotonic()
        try:
            redrawn = 0
            for sc in scs:                     # détails en retard sur le modèle : redessinés avant l'export
                if sc.dessin_layout.auto_update:
                    for o in details(sc):
                        m = detail_model(o)
                        if m is not None and o.name in _STATE["built"] and _STATE["built"][o.name] != model_version(m):
                            detail_rebuild(o)
                            redrawn += 1
            if redrawn:
                _undo_push(context.window, "Update Viewports")
            written = self.write(path, [layout_page(sc) for sc in scs])
        except OSError as e:
            self.report({'ERROR'}, f"Cannot write the file: {e}")
            return {'CANCELLED'}
        except RuntimeError as e:              # (DWG : pas de convertisseur sur cet ordinateur, ou il a échoué)
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        self.report({'INFO'}, f"{len(scs)} layout(s) exported in {time.monotonic() - t0:.1f} s: {written}")
        self.after(written)
        return {'FINISHED'}

    def after(self, written):
        pass


class DESSIN_OT_layout_export_pdf(_LayoutExport, bpy.types.Operator):
    bl_idname = "dessin.layout_export_pdf"
    bl_label = "Export PDF"
    bl_description = ("Vector PDF at the exact paper size, one page per layout: print it at 100 % (no fit to page) "
                      "and the drawing is at scale")
    EXT = ".pdf"
    filter_glob: bpy.props.StringProperty(default="*.pdf", options={'HIDDEN'})
    open_after: bpy.props.BoolProperty(name="Open the PDF", default=True, description="Opens the file once written (to check it or print it)")

    def write(self, path, pages):
        title = os.path.splitext(os.path.basename(path))[0]
        le.write_pdf(path, pages, title, "Wanderer CAD")
        return path

    def after(self, written):
        if self.open_after and not bpy.app.background:
            try:
                bpy.ops.wm.path_open(filepath=written)
            except (RuntimeError, TypeError):
                pass


class DESSIN_OT_layout_export_svg(_LayoutExport, bpy.types.Operator):
    bl_idname = "dessin.layout_export_svg"
    bl_label = "Export SVG"
    bl_description = "Vector SVG in millimeters (Illustrator, Inkscape, Affinity...). Several layouts: one file each"
    EXT = ".svg"
    filter_glob: bpy.props.StringProperty(default="*.svg", options={'HIDDEN'})

    def write(self, path, pages):
        if len(pages) == 1:
            le.write_svg(path, pages[0])
            return path
        stem = os.path.splitext(path)[0]
        for pg in pages:
            safe = "".join(ch if ch.isalnum() or ch in " -_." else "_" for ch in pg["name"])
            le.write_svg(f"{stem} - {safe}.svg", pg)
        return stem + " - *.svg"


class DESSIN_OT_layout_export_dxf(_LayoutExport, bpy.types.Operator):
    bl_idname = "dessin.layout_export_dxf"
    bl_label = "Export DXF"
    bl_description = ("DXF (R12) in paper millimeters for AutoCAD, Rhino, CADCraft... one layer per kind of line; "
                      "several layouts are placed side by side. Texts are exported as outlines")
    EXT = ".dxf"
    filter_glob: bpy.props.StringProperty(default="*.dxf", options={'HIDDEN'})

    def write(self, path, pages):
        le.write_dxf(path, pages)
        return path


class DESSIN_OT_layout_export_dwg(_LayoutExport, bpy.types.Operator):
    bl_idname = "dessin.layout_export_dwg"
    bl_label = "Export DWG"
    bl_description = ("DWG in paper millimeters for AutoCAD: the same drawing as Export DXF, converted by the free ODA File "
                      "Converter installed on this computer")
    EXT = ".dwg"
    filter_glob: bpy.props.StringProperty(default="*.dwg", options={'HIDDEN'})

    def write(self, path, pages):
        import shutil
        import tempfile
        from .import_dxf import cad_convert
        tmp = tempfile.mkdtemp(prefix="wd_layout_dwg_")
        try:
            dxf = os.path.join(tmp, os.path.splitext(os.path.basename(path))[0] + ".dxf")
            le.write_dxf(dxf, pages)
            made = cad_convert(dxf, "DWG")
            try:
                shutil.move(made, path)
            finally:
                shutil.rmtree(os.path.dirname(made), ignore_errors=True)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        return path


# --------------------------------------------------------------------------
# Interface : onglets de la barre de vues, menus, panneaux
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# Poignées d'une fenêtre sélectionnée, comme les grips d'AutoCAD : 4 aux coins pour la redimensionner (le coin opposé ne
# bouge pas, le modèle reste à sa place sur la feuille), 1 au centre pour la déplacer (quand le Gumball est coupé, sinon
# c'est lui qui la déplace), 1 triangle qui ouvre la liste d'échelles.
# --------------------------------------------------------------------------
GRIP_CORNERS = ((-1, -1), (1, -1), (1, 1), (-1, 1))
GRIP_MOVE = 4                     # numéro de la poignée centrale
GRIP_PX = 4.5                     # demi-côté d'une poignée, en pixels d'interface
GRIP_MIN = 2.0                    # plus petit côté d'une fenêtre (mm)
GRIP_COLOR = (0.05, 0.36, 0.95)   # bleu des poignées d'AutoCAD
GRIP_HOT = (1.0, 0.36, 0.26)      # poignée survolée
GRIP_SCALE_OFFSET = (20.0, -20.0)  # le triangle d'échelle, en pixels depuis le centre (hors des flèches du Gumball)
ACTIVE_VP_WIDTH = 4.5             # épaisseur du bord de la fenêtre dans laquelle on travaille
GRIP_SQUARE = [(-1.0, -1.0, 0.0), (1.0, -1.0, 0.0), (1.0, 1.0, 0.0), (-1.0, -1.0, 0.0), (1.0, 1.0, 0.0), (-1.0, 1.0, 0.0)]
GRIP_TRIANGLE = [(-1.25, 0.9, 0.0), (1.25, 0.9, 0.0), (0.0, -1.1, 0.0)]


def detail_rect(obj):
    """Rectangle papier d'une fenêtre : (x et y du centre, largeur, hauteur), en millimètres."""
    d = obj.dessin_detail
    return (float(obj.location.x), float(obj.location.y), float(d.width), float(d.height))


def grip_points(rect):
    """Les quatre coins d'un rectangle papier, dans l'ordre de GRIP_CORNERS."""
    cx, cy, w, h = rect
    return [(cx + sx * w / 2.0, cy + sy * h / 2.0) for sx, sy in GRIP_CORNERS]


def grip_opposite(rect, corner):
    """Le coin qui ne bouge pas quand on tire le coin `corner`."""
    return grip_points(rect)[(corner + 2) % 4]


def grip_rect(rect, corner, p, min_size=GRIP_MIN):
    """Nouveau rectangle (cx, cy, w, h) quand le coin `corner` est tiré jusqu'au point papier p : le coin opposé ne bouge
    pas. Tiré au-delà du coin opposé, le cadre se retourne ; il garde toujours une taille minimale."""
    sx, sy = GRIP_CORNERS[corner]
    ox, oy = grip_opposite(rect, corner)
    dx, dy = p[0] - ox, p[1] - oy
    if abs(dx) < min_size:
        dx = math.copysign(min_size, dx if abs(dx) > 1e-12 else sx)
    if abs(dy) < min_size:
        dy = math.copysign(min_size, dy if abs(dy) > 1e-12 else sy)
    return (ox + dx / 2.0, oy + dy / 2.0, abs(dx), abs(dy))


def detail_set_rect(obj, rect, keep_model=True):
    """Donne à une fenêtre le rectangle papier (cx, cy, w, h).
    keep_model : le dessin du modèle ne bouge pas sur la feuille (une fenêtre d'AutoCAD dont on tire un coin découvre plus
    ou moins du modèle, elle ne le déplace pas) ; sinon le modèle suit la fenêtre (elle est déplacée)."""
    if not is_detail(obj):
        return False
    d = obj.dessin_detail
    cx, cy, w, h = rect
    sx, sy = cx - obj.location.x, cy - obj.location.y
    with quiet():
        if keep_model and not d.persp and (abs(sx) > 1e-12 or abs(sy) > 1e-12):
            model = detail_model(obj)
            if model is not None:
                k = mm_per_unit(model) / max(d.scale, 1e-9)
                proj = detail_projector(d)
                d.center = Vector(d.center) + (proj.right * sx + proj.up * sy) / k
        d.width, d.height = max(float(w), 1.0), max(float(h), 1.0)
        obj.location.x, obj.location.y = cx, cy
    detail_rebuild(obj)
    with quiet():
        detail_dims_follow(obj)             # ses cotes restent sur les mêmes points du modèle
    return True


def grip_target(context):
    """La fenêtre qui montre ses poignées : l'objet actif, s'il est une fenêtre sélectionnée de la mise en page affichée."""
    try:
        sc = context.scene
        if not is_layout(sc) or context.mode != 'OBJECT' or _STATE["active_vp"]:
            return None
        act = context.view_layer.objects.active
        if is_detail(act) and act.select_get() and act.name in sc.objects:
            return act
    except (AttributeError, ReferenceError, RuntimeError):
        pass
    return None


def double_click_blocked(context, event):
    """True si le double-clic tombe sur une barre du bas, un panneau ou hors de la vue : il n'entre pas dans une fenêtre."""
    area = context.area
    if area is None or area.type != 'VIEW_3D':
        return True
    if find_window_region(area, event.mouse_x, event.mouse_y) is None or event.alt or event.oskey or event.ctrl:
        return True
    for r in area.regions:
        if (r.type in {'TOOLS', 'UI', 'HEADER', 'TOOL_HEADER'} and r.x <= event.mouse_x < r.x + r.width
                and r.y <= event.mouse_y < r.y + r.height):
            return True
    try:
        return cmd_hit(area, event.mouse_x, event.mouse_y) is not None
    except (AttributeError, TypeError, RuntimeError):
        return False


class DESSIN_OT_viewport_grip(DessinBase):
    bl_idname = "dessin.viewport_grip"
    bl_label = "Viewport Grip"
    bl_description = ("Layout: grip of the selected viewport. Corner: click it (or drag it) to the new position; the opposite "
                      "corner stays in place and the model does not move on the sheet. Center: moves the viewport. "
                      "Object snaps, Grid Snap and typed sizes work as in the drawing tools")
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    TITLE = "Viewport"
    PROP = ()
    NEEDED = 2
    NUMFIELDS = 2
    HAS_CENTER = False
    EDIT_OK = False

    corner: bpy.props.IntProperty(default=0, min=0, max=GRIP_MOVE, options={'SKIP_SAVE', 'HIDDEN'})

    def invoke(self, context, event):
        obj = grip_target(context)
        if obj is None:
            return {'CANCELLED', 'PASS_THROUGH'}
        self.vp_name = obj.name
        self.rect0 = detail_rect(obj)
        self.press = (event.mouse_x, event.mouse_y) if event is not None else (0, 0)
        self.released = False
        res = DessinBase.invoke(self, context, event)
        if 'RUNNING_MODAL' not in res:
            return res
        if self.corner == GRIP_MOVE:
            base = (self.rect0[0], self.rect0[1])
        else:
            base = grip_opposite(self.rect0, self.corner)
        self.points = [Vector((base[0], base[1], 0.0))]        # le point fixe : la suite est un seul clic
        self.typed = ['', '', '']
        self.update_cursor(context, event)
        self.refresh(context)
        return res

    def prompt(self):
        if self.corner == GRIP_MOVE:
            return "new position of the viewport"
        return "new corner of the viewport   (or type width, Tab, height, Enter)"

    def compute(self):
        if not self.points or self.cur is None:
            return [], [], "", None
        if self.corner == GRIP_MOVE:
            cx, cy, w, h = self.rect0
            d = self.cur - self.points[0]
            c = [Vector((x + d.x, y + d.y, 0.0)) for x, y in grip_points(self.rect0)]
            return c + [c[0]], [], f"Move {self.fmt(math.hypot(d.x, d.y))}", ("move", (cx + d.x, cy + d.y, w, h))
        return DESSIN_OT_rectangle.compute(self)

    def modal(self, context, event):
        # la poignée a été pressée puis tirée : relâcher pose le point (cliquer la poignée, bouger, puis cliquer marche aussi)
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE' and not self.released:
            self.released = True
            moved = math.hypot(event.mouse_x - self.press[0], event.mouse_y - self.press[1]) > 5.0 * px_scale()
            if moved and self.points:
                self.update_cursor(context, event)
                if self.cur is not None:
                    self.click(context)
                    if self.finished:
                        return self.exit(context)
            return {'RUNNING_MODAL'}
        return DessinBase.modal(self, context, event)

    def build(self, context, spec):
        obj = context.scene.objects.get(self.vp_name)
        if obj is None or not is_detail(obj):
            return None
        if spec[0] == 'move':
            rect, keep = spec[1], False
        elif spec[0] == 'rect':
            xs = [p.x for p in spec[1]]
            ys = [p.y for p in spec[1]]
            w, h = max(xs) - min(xs), max(ys) - min(ys)
            if w < GRIP_MIN or h < GRIP_MIN:
                self.report({'WARNING'}, "Viewport too small")
                return None
            rect, keep = ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0, w, h), True
        else:
            return None
        detail_set_rect(obj, rect, keep_model=keep)
        _redraw()
        return obj

    def after_finish(self, context):
        if getattr(self, "tool_id", None):
            try:
                idle_tool()
            except (RuntimeError, TypeError):
                pass


class DESSIN_GT_vp_grip(bpy.types.Gizmo):
    """Poignée carrée d'une fenêtre (Blender la surligne et la détecte lui-même)."""
    bl_idname = "DESSIN_GT_vp_grip"
    __slots__ = ("shape",)

    def setup(self):
        if not hasattr(self, "shape"):
            self.shape = self.new_custom_shape('TRIS', GRIP_SQUARE)

    def draw(self, context):
        self.draw_custom_shape(self.shape)

    def draw_select(self, context, select_id):
        self.draw_custom_shape(self.shape, select_id=select_id)


class DESSIN_GT_vp_scale(bpy.types.Gizmo):
    """Triangle d'échelle d'une fenêtre : il ouvre la liste d'échelles."""
    bl_idname = "DESSIN_GT_vp_scale"
    __slots__ = ("shape",)

    def setup(self):
        if not hasattr(self, "shape"):
            self.shape = self.new_custom_shape('TRIS', GRIP_TRIANGLE)

    def draw(self, context):
        self.draw_custom_shape(self.shape)

    def draw_select(self, context, select_id):
        self.draw_custom_shape(self.shape, select_id=select_id)


def grip_layout(rect, px, gumball_on):
    """Où placer les poignées d'une fenêtre : {"corners": [4 points], "move": point ou None, "scale": point}, en
    millimètres de papier. px : millimètres par pixel d'interface ; la poignée du centre s'efface quand le Gumball est là."""
    cx, cy, _w, _h = rect
    return {"corners": grip_points(rect), "move": None if gumball_on else (cx, cy),
            "scale": (cx + GRIP_SCALE_OFFSET[0] * px, cy + GRIP_SCALE_OFFSET[1] * px)}


class DESSIN_GGT_viewport_grips(bpy.types.GizmoGroup):
    bl_idname = "DESSIN_GGT_viewport_grips"
    bl_label = "Viewport Grips"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'3D', 'PERSISTENT'}

    @classmethod
    def poll(cls, context):
        try:
            if grip_target(context) is None or foreign_modal(context):
                return False
            tool = context.workspace.tools.from_space_view3d_mode(context.mode, create=False)
        except (AttributeError, RuntimeError, TypeError):
            return False
        return tool is None or tool.idname in _GUMBALL_TOOLS

    def setup(self, context):
        self.gz_corner, self.gz_move, self.gz_scale = [], None, None
        for i in range(4):
            gz = self.gizmos.new(DESSIN_GT_vp_grip.bl_idname)
            gz.target_set_operator(DESSIN_OT_viewport_grip.bl_idname).corner = i
            self.gz_corner.append(gz)
        self.gz_move = self.gizmos.new(DESSIN_GT_vp_grip.bl_idname)
        self.gz_move.target_set_operator(DESSIN_OT_viewport_grip.bl_idname).corner = GRIP_MOVE
        self.gz_scale = self.gizmos.new(DESSIN_GT_vp_scale.bl_idname)
        self.gz_scale.target_set_operator("wm.call_menu").name = DESSIN_MT_viewport_scale.bl_idname
        for gz in self.gz_corner + [self.gz_move, self.gz_scale]:
            for k, v in (("color", GRIP_COLOR), ("alpha", 1.0), ("color_highlight", GRIP_HOT), ("alpha_highlight", 1.0),
                         ("use_draw_modal", False), ("use_draw_scale", False), ("scale_basis", 1.0), ("select_bias", 3.0)):
                try:
                    setattr(gz, k, v)
                except (AttributeError, TypeError, ValueError):
                    pass

    def place(self, context):
        obj = grip_target(context)
        rv3d, region = context.region_data, context.region
        every = list(getattr(self, "gz_corner", [])) + [g for g in (getattr(self, "gz_move", None), getattr(self, "gz_scale", None)) if g]
        if obj is None or rv3d is None or region is None:
            for gz in every:
                gz.hide = True
            return
        rect = detail_rect(obj)
        v = rv3d.perspective_matrix @ Vector((rect[0], rect[1], 0.0, 1.0))
        proj = rv3d.window_matrix[0][0] or 1.0
        px = max(abs(v.w), 1e-6) / (0.5 * region.width * proj) * px_scale()      # millimètres par pixel d'interface
        try:
            gumball_on = bool(context.scene.dessin.gumball)
        except AttributeError:
            gumball_on = False
        where = grip_layout(rect, px, gumball_on)
        z = float(obj.location.z)
        size = Matrix.Scale(GRIP_PX * px, 4)
        for gz, (x, y) in zip(self.gz_corner, where["corners"]):
            gz.matrix_basis = Matrix.Translation((x, y, z)) @ size
            gz.hide = False
        if where["move"] is None:
            self.gz_move.hide = True
        else:
            self.gz_move.matrix_basis = Matrix.Translation((where["move"][0], where["move"][1], z)) @ size
            self.gz_move.hide = False
        self.gz_scale.matrix_basis = Matrix.Translation((where["scale"][0], where["scale"][1], z)) @ Matrix.Scale(GRIP_PX * 1.25 * px, 4)
        self.gz_scale.hide = False

    def refresh(self, context):
        self.place(context)

    def draw_prepare(self, context):
        self.place(context)


class DESSIN_MT_viewport_scale(bpy.types.Menu):
    bl_idname = "DESSIN_MT_viewport_scale"
    bl_label = "Viewport Scale"

    def draw(self, context):
        lay = self.layout
        obj = active_detail(context)
        if obj is None:
            lay.label(text="Select a viewport first")
            return
        d = obj.dessin_detail
        lay.enabled = True
        col = lay.column()
        col.enabled = not d.locked and not d.persp
        col.operator_context = 'EXEC_DEFAULT'
        for _key, name, den in le.SCALES:
            on = abs(den - d.scale) <= 1e-9 * max(1.0, den)
            col.operator(DESSIN_OT_detail_scale.bl_idname, text=name, icon='RADIOBUT_ON' if on else 'RADIOBUT_OFF').text = name
        col.separator()
        col.operator_context = 'INVOKE_DEFAULT'
        col.operator(DESSIN_OT_detail_scale.bl_idname, text="Custom...")
        col.operator(DESSIN_OT_detail_fit.bl_idname, text="Fit")
        lay.separator()
        lay.prop(d, "locked", text="Display Locked")
        lay.operator(DESSIN_OT_detail_pan.bl_idname, text="Activate (pan inside)")


class DESSIN_OT_viewport_paper(bpy.types.Operator):
    bl_idname = "dessin.viewport_paper"
    bl_label = "Paper Space"
    bl_description = "Back to the sheet of the layout (paper space, PS in AutoCAD). From the model, opens the layout"

    def execute(self, context):
        if is_layout(context.scene):
            self.report({'INFO'}, "Paper space: you are on the sheet (double-click inside a viewport, or MS, to work in it)")
            return {'CANCELLED'}
        try:
            return bpy.ops.dessin.layout_next()
        except RuntimeError:
            return {'CANCELLED'}


_VP_KEYS = []


def viewport_keys_register():
    """Double-clic dans une fenêtre d'une mise en page : on y entre (comme l'espace objet d'AutoCAD)."""
    try:
        wm = bpy.context.window_manager
        kc = wm.keyconfigs.addon if wm is not None else None
        if kc is None:
            return
        km = kc.keymaps.new(name="Object Mode", space_type='EMPTY')
        kmi = km.keymap_items.new(DESSIN_OT_detail_pan.bl_idname, 'LEFTMOUSE', 'DOUBLE_CLICK')
        kmi.properties.pick = True
        _VP_KEYS.append((km, kmi))
    except (AttributeError, RuntimeError, TypeError):
        pass


def viewport_keys_unregister():
    for km, kmi in _VP_KEYS:
        try:
            km.keymap_items.remove(kmi)
        except (RuntimeError, ReferenceError, TypeError):
            pass
    _VP_KEYS.clear()


def bar_tabs(context):
    """Onglets de la barre du bas : vues du modèle, puis mises en page, puis « + ».
    [(type, valeur, texte, actif)] avec type = 'view', 'layout' ou 'viewmenu'."""
    sc = context.scene
    if is_layout(sc):
        model = layout_model(sc)
        names = tab_names(model) if model is not None else []
        active = None
    else:
        model = sc
        names = tab_names(sc)
        active = current_view_name(context)
    tabs = [('view', n, view_label(model, n), n == active) for n in names]
    tabs += [('layout', s.name, s.name, s == sc) for s in layouts()]
    tabs.append(('viewmenu', "+", "+", False))
    return tabs


def tab_click(context, kind, val):
    """Clic sur un onglet de vue ou de mise en page. Retourne True si le clic est traité."""
    if kind == 'layout':
        bpy.ops.dessin.layout_open('INVOKE_DEFAULT', name=val)
        return True
    if kind == 'view' and is_layout(context.scene):
        layout_close(context)
        try:
            bpy.ops.dessin.view_restore(name=val)
        except RuntimeError:
            pass
        return True
    return False


def menu_layouts(layout, context):
    """Entrées « mises en page » du menu « + » de la barre de vues."""
    layout.separator()
    cur = context.scene
    for s in layouts():
        layout.operator(DESSIN_OT_layout_open.bl_idname, text=s.name, icon='DOT' if s == cur else 'FILE').name = s.name
    layout.operator(DESSIN_OT_layout_new.bl_idname, text="New Layout...", icon='ADD')
    if is_layout(cur):
        layout.operator(DESSIN_OT_layout_close.bl_idname, text="Back to the Model", icon='LOOP_BACK')


def draw_page_settings(lay, L):
    lay.use_property_split = True
    lay.use_property_decorate = False
    col = lay.column(align=True)
    col.prop(L, "paper")
    if L.paper == 'CUSTOM':
        col.prop(L, "custom_w")
        col.prop(L, "custom_h")
    col.prop(L, "orientation")
    col.prop(L, "margin")
    col.prop(L, "show_frame")
    col.prop(L, "show_title")
    if L.show_title:
        col = lay.column(align=True)
        col.prop(L, "t_project")
        col.prop(L, "t_title")
        col.prop(L, "t_author")
        col.prop(L, "t_date")
        col.prop(L, "t_number")
        col.prop(L, "t_revision")
        col.prop(L, "t_scale")


class DESSIN_PT_layout(bpy.types.Panel):
    bl_label = "Layouts"
    bl_idname = "DESSIN_PT_layout"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Layout"

    def draw(self, context):
        lay = self.layout
        cur = context.scene
        ls = layouts()
        lay.operator(DESSIN_OT_layout_new.bl_idname, text="New Layout", icon='ADD')
        if not ls:
            lay.label(text="A layout is a paper sheet with")
            lay.label(text="views of the model at scale.")
            return
        box = lay.box()
        for s in ls:
            row = box.row(align=True)
            row.operator(DESSIN_OT_layout_open.bl_idname, text=s.name, depress=(s == cur), icon='FILE').name = s.name
            row.operator(DESSIN_OT_layout_duplicate.bl_idname, text="", icon='DUPLICATE').name = s.name
            row.operator(DESSIN_OT_layout_rename.bl_idname, text="", icon='GREASEPENCIL').name = s.name
            row.operator(DESSIN_OT_layout_delete.bl_idname, text="", icon='TRASH').name = s.name
        if is_layout(cur):
            lay.operator(DESSIN_OT_layout_close.bl_idname, text="Back to the Model", icon='LOOP_BACK')


class DESSIN_PT_layout_page(bpy.types.Panel):
    bl_label = "Page"
    bl_idname = "DESSIN_PT_layout_page"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Layout"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return is_layout(context.scene)

    def draw(self, context):
        if not is_layout(context.scene):
            return
        L = context.scene.dessin_layout
        draw_page_settings(self.layout, L)
        col = self.layout.column(align=True)
        col.prop(L, "model")
        col.prop(L, "auto_update")


class DESSIN_PT_layout_detail(bpy.types.Panel):
    bl_label = "Viewports"
    bl_idname = "DESSIN_PT_layout_detail"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Layout"

    @classmethod
    def poll(cls, context):
        return is_layout(context.scene)

    def draw(self, context):
        lay = self.layout
        sc = context.scene
        if not is_layout(sc):
            return
        L = sc.dessin_layout
        row = lay.row(align=True)
        row.operator(DESSIN_OT_layout_detail.bl_idname, text="Draw a Viewport", icon='ADD')
        row.prop(L, "new_view", text="")
        row = lay.row(align=True)
        row.operator(DESSIN_OT_detail_update.bl_idname, text="Update", icon='FILE_REFRESH')
        row.operator(DESSIN_OT_detail_pan.bl_idname, text="Pan", icon='VIEW_PAN')
        row.operator(DESSIN_OT_detail_fit.bl_idname, text="Fit", icon='FULLSCREEN_ENTER')
        obj = active_detail(context)
        if obj is None:
            lay.label(text="Click the border of a viewport", icon='INFO')
            lay.label(text="to see its settings here.")
            return
        d = obj.dessin_detail
        box = lay.box()
        box.label(text=obj.name, icon='SELECT_SET')
        col = box.column(align=True)
        col.use_property_split = True
        col.use_property_decorate = False
        col.prop(d, "view")
        if d.view == 'CUSTOM':
            col.label(text=(d.view_label or "Model view") + (" (perspective)" if d.persp else ""))
        col.operator(DESSIN_OT_detail_view_set.bl_idname, icon='VIEW_CAMERA')
        col = box.column(align=True)
        col.use_property_split = True
        col.use_property_decorate = False
        col.enabled = not d.locked and not d.persp
        col.prop(d, "scale_preset")
        if d.scale_preset == 'CUSTOM':
            col.prop(d, "scale")
        col = box.column(align=True)
        col.use_property_split = True
        col.use_property_decorate = False
        col.prop(d, "locked")
        col.prop(d, "display")
        col.prop(d, "show_annotations")
        col.prop(d, "tangent_edges")
        col.prop(d, "sharp_angle")
        col = box.column(align=True)
        col.use_property_split = True
        col.use_property_decorate = False
        col.prop(d, "width")
        col.prop(d, "height")
        col.prop(d, "show_border")
        col.prop(d, "show_label")
        if d.show_label:
            col.prop(d, "label")
        box.operator(DESSIN_OT_detail_text_match.bl_idname, icon='FONT_DATA')


class DESSIN_PT_layout_layers(bpy.types.Panel):
    bl_label = "Layers in this Viewport"
    bl_idname = "DESSIN_PT_layout_layers"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Layout"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return is_layout(context.scene) and active_detail(context) is not None

    def draw(self, context):
        lay = self.layout
        obj = active_detail(context) if is_layout(context.scene) else None
        model = detail_model(obj) if obj is not None else None
        if model is None:
            return
        hidden = set(detail_hidden(obj.dessin_detail))
        lay.label(text="Hide model layers in this viewport only:")
        col = lay.column(align=True)

        def walk(c, depth):
            for ch in c.children:
                row = col.row(align=True)
                row.separator(factor=depth * 1.5)
                off = ch.name in hidden
                op = row.operator(DESSIN_OT_detail_layer.bl_idname, text=ch.name, emboss=False,
                                  icon='HIDE_ON' if off else 'HIDE_OFF')
                op.layer = ch.name
                if not off:
                    walk(ch, depth + 1)
        walk(model.collection, 0)
        if not len(model.collection.children):
            lay.label(text="The model has no layer")


class DESSIN_PT_layout_print(bpy.types.Panel):
    bl_label = "Print"
    bl_idname = "DESSIN_PT_layout_print"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Layout"

    @classmethod
    def poll(cls, context):
        return bool(layouts())

    def draw(self, context):
        lay = self.layout
        sc = context.scene
        if is_layout(sc):
            L = sc.dessin_layout
            col = lay.column(align=True)
            col.use_property_split = True
            col.use_property_decorate = False
            col.label(text="Line widths (mm)")
            col.prop(L, "lw_visible")
            col.prop(L, "lw_hidden")
            col.prop(L, "lw_annot")
            col.prop(L, "lw_border")
            col.prop(L, "lw_frame")
            col.prop(L, "show_lineweights")
            col.prop(L, "print_color")
        col = lay.column(align=True)
        col.operator(DESSIN_OT_layout_export_pdf.bl_idname, icon='FILE')
        row = col.row(align=True)
        row.operator(DESSIN_OT_layout_export_svg.bl_idname, text="SVG")
        row.operator(DESSIN_OT_layout_export_dxf.bl_idname, text="DXF")
        row.operator(DESSIN_OT_layout_export_dwg.bl_idname, text="DWG")


LAYOUT_CLASSES = (
    DESSIN_PG_layout, DESSIN_PG_detail,
    DESSIN_OT_layout_new, DESSIN_OT_layout_open, DESSIN_OT_layout_close, DESSIN_OT_layout_next, DESSIN_OT_layout_rename,
    DESSIN_OT_layout_delete, DESSIN_OT_layout_duplicate, DESSIN_OT_layout_page_setup, DESSIN_OT_layout_erase,
    DESSIN_OT_layout_detail, DESSIN_OT_detail_add, DESSIN_OT_detail_update, DESSIN_OT_detail_fit, DESSIN_OT_detail_scale,
    DESSIN_OT_detail_view_set, DESSIN_OT_detail_layer, DESSIN_OT_detail_pan, DESSIN_OT_detail_text_match,
    DESSIN_OT_layout_export_pdf, DESSIN_OT_layout_export_svg, DESSIN_OT_layout_export_dxf, DESSIN_OT_layout_export_dwg,
    DESSIN_OT_viewport_grip, DESSIN_OT_viewport_paper, DESSIN_MT_viewport_scale, DESSIN_GT_vp_grip, DESSIN_GT_vp_scale, DESSIN_GGT_viewport_grips,
    DESSIN_PT_layout, DESSIN_PT_layout_page, DESSIN_PT_layout_detail, DESSIN_PT_layout_layers, DESSIN_PT_layout_print,
)


def layout_register():
    bpy.types.Scene.dessin_layout = bpy.props.PointerProperty(type=DESSIN_PG_layout)
    bpy.types.Object.dessin_detail = bpy.props.PointerProperty(type=DESSIN_PG_detail)
    if layout_on_depsgraph not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(layout_on_depsgraph)
    if layout_on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(layout_on_load)
    for hl in (bpy.app.handlers.undo_post, bpy.app.handlers.redo_post):
        if layout_on_undo not in hl:
            hl.append(layout_on_undo)
    try:
        if not bpy.app.timers.is_registered(layout_tick):
            bpy.app.timers.register(layout_tick, first_interval=1.0, persistent=True)
    except (RuntimeError, ValueError):
        pass
    if _DRAW["handle"] is None and not bpy.app.background:
        _DRAW["handle"] = bpy.types.SpaceView3D.draw_handler_add(layout_draw_cb, (), 'WINDOW', 'POST_VIEW')
    erase_keys_register()
    viewport_keys_register()


def layout_unregister():
    erase_keys_unregister()
    viewport_keys_unregister()
    _STATE["active_vp"] = None
    try:                                   # (Pan Detail interrompu par la désactivation : son message ne doit pas rester)
        for ws in bpy.data.workspaces:
            ws.status_text_set(None)
    except (AttributeError, RuntimeError):
        pass
    if _DRAW["handle"] is not None:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(_DRAW["handle"], 'WINDOW')
        except (ValueError, RuntimeError):
            pass
        _DRAW["handle"] = None
    try:
        if bpy.app.timers.is_registered(layout_tick):
            bpy.app.timers.unregister(layout_tick)
    except (RuntimeError, ValueError):
        pass
    for hl, fn in ((bpy.app.handlers.depsgraph_update_post, layout_on_depsgraph), (bpy.app.handlers.load_post, layout_on_load),
                   (bpy.app.handlers.undo_post, layout_on_undo), (bpy.app.handlers.redo_post, layout_on_undo)):
        if fn in hl:
            hl.remove(fn)
    for key in ("views", "model_ver", "built", "cache", "last_model", "paper"):
        _STATE[key].clear()
    _STATE["items"] = None
    _STATE["hold"] = 0.0
    try:
        del bpy.types.Object.dessin_detail
        del bpy.types.Scene.dessin_layout
    except AttributeError:
        pass


def _late_imports():
    """Noms définis dans des modules chargés après celui-ci : ils ne servent qu'à l'exécution des outils."""
    global DIM_STYLE_FIELDS, _axis_quat, current_view_name, ensure_dim_styles, find_view, rebuild_dimension
    global cmd_click_idle, cmd_hit, tab_names, view_label, foreign_modal, _GUMBALL_TOOLS
    from .command_line import cmd_click_idle, cmd_hit
    from .gumball_handles import foreign_modal, _GUMBALL_TOOLS
    global _dim_replay_spec
    from .settings import DIM_STYLE_FIELDS, _dim_replay_spec, ensure_dim_styles, rebuild_dimension
    from .navigation import _axis_quat
    from .views import current_view_name, find_view, tab_names, view_label
