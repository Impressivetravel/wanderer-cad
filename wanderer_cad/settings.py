"""Wanderer CAD : Styles de cote, motifs de hachure et réglages de la scène."""

import bpy
import json
import math
import numpy as np
import types
from mathutils import Matrix, Vector

from .core import TAU, plane_axes


# --------------------------------------------------------------------------
# Cotations
# --------------------------------------------------------------------------

COTATIONS = "Dimensions"
LEGACY_COTATIONS = "Cotations"  # ancien nom de la collection (versions françaises)


def dimension_objects(scene=None):
    """Objets de cotation de la scène, y compris ceux de l'ancienne collection « Cotations ».
    Une mise en page (Layout) a ses propres cotes, rangées dans sa collection."""
    try:
        scene = scene or bpy.context.scene
        if is_layout(scene):
            col = layout_dims_collection(scene, create=False)
            return list(col.objects) if col is not None else []
    except (AttributeError, ReferenceError, NameError):
        pass
    out = []
    for name in (COTATIONS, LEGACY_COTATIONS):
        col = bpy.data.collections.get(name)
        if col is not None:
            out += list(col.objects)
    return out


def cotation_material(color=None):
    mat = bpy.data.materials.get("Dimension")
    if mat is None:
        mat = bpy.data.materials.new("Dimension")
        try:
            mat.use_nodes = True
        except Exception:
            pass
    if color is not None:
        mat.diffuse_color = (color[0], color[1], color[2], 1.0)
        nt = getattr(mat, "node_tree", None)
        if nt is not None:
            node = nt.nodes.get("Principled BSDF")
            if node is not None:
                for name in ("Base Color", "Emission Color", "Emission"):
                    sock = node.inputs.get(name)
                    if sock is not None and sock.type == 'RGBA':
                        sock.default_value = (color[0], color[1], color[2], 1.0)
                strength = node.inputs.get("Emission Strength")
                if strength is not None:
                    strength.default_value = 1.0
    return mat


def _cotation_thickness_update(self, context):
    for o in dimension_objects(self.id_data):
        if o.type == 'CURVE' and "dessin_cotation" in o.keys():
            h = o.get("dessin_hauteur", 0.0)
            o.data.bevel_depth = 0.05 * h * self.epaisseur_trait if self.epaisseur_trait > 0.0 else 0.0
            o.data.bevel_resolution = 0
        elif o.type == 'FONT' and "dessin_cotation_texte" in o.keys():
            h = o.get("dessin_hauteur", 0.0)
            o.data.fill_mode = 'BOTH'
            o.data.bevel_depth = 0.05 * h * self.epaisseur_trait if self.epaisseur_trait > 0.0 else 0.0
            o.data.bevel_resolution = 0


def _cotation_render_update(self, context):
    for o in dimension_objects(self.id_data):
        o.hide_render = not self.visible_rendu


def _cotation_color_update(self, context):
    """Changer la couleur met aussi à jour les cotations déjà tracées (matériau partagé)."""
    cotation_material(tuple(self.couleur))
    for o in dimension_objects(self.id_data):
        o.color = (self.couleur[0], self.couleur[1], self.couleur[2], 1.0)


_RESTYLE = {"busy": False}


def _cotation_restyle_update(self, context):
    """Un réglage de style de cote change : les cotes déjà posées sont reconstruites avec le nouveau style."""
    if _RESTYLE["busy"]:
        return
    _RESTYLE["busy"] = True
    try:
        ctx = bpy.context
        if self.id_data != ctx.scene:
            return          # les cotes sont reconstruites avec le style de la scène affichée : pas depuis une autre scène
        for o in list(dimension_objects(self.id_data)):
            try:
                if o.type == 'CURVE' and "dessin_dim" in o.keys():
                    rebuild_dimension(ctx, o)
            except (RuntimeError, ReferenceError, ValueError, TypeError, KeyError, AttributeError):
                continue
    finally:
        _RESTYLE["busy"] = False


def _update_ortho(self, context):
    if self.ortho and self.polar:
        self.polar = False


def _update_polar(self, context):
    if self.polar and self.ortho:
        self.ortho = False


DIM_STYLE_FIELDS = ("taille_texte", "ecart_texte", "position_texte", "prolongement", "decalage", "fleche_style", "fleche_taille",
                    "unite_cote", "decimales", "supprimer_zeros", "unite", "prefixe", "suffixe")
DIM_STYLE_DEFAULTS = (
    ("Standard", {"fleche_style": 'FLECHE', "fleche_taille": 0.8, "position_texte": 'AU_DESSUS', "ecart_texte": 0.3,
                  "prolongement": 0.5, "decalage": 0.25, "decimales": 2, "supprimer_zeros": False}),
    ("Architecture (ticks)", {"fleche_style": 'TRAIT', "fleche_taille": 0.7, "position_texte": 'AU_DESSUS', "ecart_texte": 0.3,
                              "prolongement": 0.8, "decalage": 0.4, "decimales": 0, "supprimer_zeros": True}),
    ("Mechanical (closed arrows)", {"fleche_style": 'FERME', "fleche_taille": 1.0, "position_texte": 'CENTRE', "ecart_texte": 0.3,
                                    "prolongement": 0.5, "decalage": 0.25, "decimales": 2, "supprimer_zeros": False}),
)


def dimstyle_apply(st, name_or_item):
    """Reporte les réglages d'un style de cotation sur les réglages courants."""
    try:
        data = json.loads(name_or_item.data)
    except (ValueError, AttributeError, TypeError):
        return
    for k, v in data.items():
        try:
            setattr(st, k, v)
        except (TypeError, ValueError, AttributeError):
            pass


def dimstyle_snapshot(st):
    out = {}
    for k in DIM_STYLE_FIELDS:
        try:
            v = getattr(st, k)
        except AttributeError:
            continue
        out[k] = v
    return out


def _dimstyle_index_update(self, context):
    try:
        item = self.dim_styles[self.dim_style_index]
    except (IndexError, KeyError):
        return
    dimstyle_apply(self, item)


def ensure_dim_styles(st):
    """Styles de cotation prêts à l'emploi (créés une fois, dans une scène qui n'en a pas)."""
    if len(st.dim_styles):
        return
    base = dimstyle_snapshot(st)
    for name, vals in DIM_STYLE_DEFAULTS:
        it = st.dim_styles.add()
        it.name = name
        d = dict(base)
        d.update(vals)
        it.data = json.dumps(d)


# --------------------------------------------------------------------------
# Hachures (Hatch de Rhino) : motifs, réglages par objet
# --------------------------------------------------------------------------

# Familles de lignes d'un motif, en unités de motif (1 = pas de base) :
# (angle°, décalage le long, décalage perpendiculaire, glissement le long par ligne, écart entre lignes, tirets)
# tirets : longueurs > 0 tracées, < 0 vides (vide = ligne continue)
HATCH_PATTERNS = {
    'SOLID': None,
    'HATCH1': ((45.0, 0.0, 0.0, 0.0, 1.0, ()),),
    'HATCH2': ((45.0, 0.0, 0.0, 0.0, 1.0, ()), (135.0, 0.0, 0.0, 0.0, 1.0, ())),
    'HATCH3': ((45.0, 0.0, 0.0, 0.0, 1.0, ()), (45.0, 0.0, 0.25, 0.0, 1.0, ())),
    'DASH': ((45.0, 0.0, 0.0, 0.5, 1.0, (1.0, -0.5)),),
    'GRID': ((0.0, 0.0, 0.0, 0.0, 1.0, ()), (90.0, 0.0, 0.0, 0.0, 1.0, ())),
    'GRID60': ((0.0, 0.0, 0.0, 0.0, 1.0, ()), (60.0, 0.0, 0.0, 0.0, 1.0, ()), (120.0, 0.0, 0.0, 0.0, 1.0, ())),
    'PLUS': ((0.0, -0.15, 0.0, 0.0, 1.0, (0.3, -0.7)), (90.0, -0.15, 0.0, 0.0, 1.0, (0.3, -0.7))),
    'SQUARES': ((0.0, 0.0, 0.0, 0.0, 1.0, (0.5, -0.5)), (0.0, 0.0, 0.5, 0.0, 1.0, (0.5, -0.5)),
                (90.0, 0.0, 0.0, 0.0, 1.0, (0.5, -0.5)), (90.0, 0.0, -0.5, 0.0, 1.0, (0.5, -0.5))),
    'BRICK': ((0.0, 0.0, 0.0, 0.0, 1.0, ()), (90.0, 0.0, 0.0, 1.0, 1.0, (1.0, -1.0))),
}
HATCH_PATTERN_ITEMS = (
    ('SOLID', "Solid", "Solid fill"),
    ('HATCH1', "Hatch1", "Parallel lines at 45 degrees"),
    ('HATCH2', "Hatch2", "Crossed lines at 45 degrees"),
    ('HATCH3', "Hatch3", "Pairs of lines at 45 degrees"),
    ('DASH', "Dash", "Dashed lines at 45 degrees"),
    ('GRID', "Grid", "Square grid"),
    ('GRID60', "Grid60", "Triangular grid (60 degrees)"),
    ('PLUS', "Plus", "Small plus signs"),
    ('SQUARES', "Squares", "Small squares"),
    ('BRICK', "Brick", "Brick courses"),
)
_HATCH_EDIT = {"busy": False}


def _hatch_prop_update(self, context):
    """Motif, échelle ou rotation d'une hachure changé : elle est reconstruite, ainsi que les autres hachures
    sélectionnées (comme le panneau Propriétés de Rhino, qui modifie toute la sélection)."""
    if _HATCH_EDIT["busy"]:
        return
    obj = self.id_data
    _HATCH_EDIT["busy"] = True
    try:
        targets = [obj]
        try:
            for o in bpy.context.selected_objects:
                if o is not obj and is_hatch(o):
                    o.dessin_hatch.pattern = self.pattern
                    o.dessin_hatch.scale = self.scale
                    o.dessin_hatch.rotation = self.rotation
                    targets.append(o)
        except (AttributeError, RuntimeError, ReferenceError):
            pass
        for o in targets:
            try:
                rebuild_hatch(o)
            except HatchTooDense:
                pass
            except (RuntimeError, ReferenceError, ValueError, TypeError, KeyError, AttributeError):
                pass
    finally:
        _HATCH_EDIT["busy"] = False


class DESSIN_PG_hatch(bpy.types.PropertyGroup):
    pattern: bpy.props.EnumProperty(name="Pattern", items=HATCH_PATTERN_ITEMS, default='HATCH1', update=_hatch_prop_update)
    scale: bpy.props.FloatProperty(name="Scale", default=1.0, min=0.01, soft_max=20.0, update=_hatch_prop_update,
                                   description="Pattern scale (1 = spacing chosen when the hatch was created)")
    rotation: bpy.props.FloatProperty(name="Rotation", default=0.0, subtype='ANGLE', update=_hatch_prop_update,
                                      description="Pattern rotation")


_DIM_EDIT = {"busy": False}


def dim_owner(obj):
    """La cote (courbe portant sa définition) d'un objet : elle-même, ou le parent d'un texte de cote."""
    try:
        if obj is None:
            return None
        if obj.type == 'FONT' and "dessin_cotation_texte" in obj.keys():
            obj = obj.parent
        if obj is not None and obj.type == 'CURVE' and "dessin_dim" in obj.keys():
            return obj
    except ReferenceError:
        pass
    return None


def _dim_text_update(self, context):
    """Texte personnalisé d'une cote (<> = valeur mesurée) : la cote est reconstruite avec ce texte."""
    if _DIM_EDIT["busy"]:
        return
    obj = self.id_data
    try:
        data = json.loads(obj["dessin_dim"])
        data["txt"] = self.text
        obj["dessin_dim"] = json.dumps(data)
        new = rebuild_dimension(bpy.context, obj)
        if new:
            try:
                bpy.context.view_layer.objects.active = new
                new.select_set(True)
            except (RuntimeError, ReferenceError, AttributeError):
                pass
    except (KeyError, ValueError, RuntimeError, ReferenceError, TypeError, AttributeError):
        pass


class DESSIN_PG_dim(bpy.types.PropertyGroup):
    text: bpy.props.StringProperty(name="Text", default="", update=_dim_text_update,
                                   description="Text of the dimension: <> is the measured value (e.g. 4x <> or <> TYP). Empty: the value only")


class DESSIN_PG_dimstyle(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="Name", default="Style")
    data: bpy.props.StringProperty(default="{}")


class DESSIN_PG_layerstate(bpy.types.PropertyGroup):
    data: bpy.props.StringProperty()


class DESSIN_PG_settings(bpy.types.PropertyGroup):
    tool_search: bpy.props.StringProperty(name="Search", default="", options={'TEXTEDIT_UPDATE'},
                                         description="Shows only the tools whose name or command alias contains this text")
    layer_states: bpy.props.CollectionProperty(type=DESSIN_PG_layerstate)
    layer_state_name: bpy.props.StringProperty(name="Name", default="", description="Name of the layer state to save")
    layer_col_exclude: bpy.props.BoolProperty(name="Exclude", default=True, description="Column: exclude the layer from the view layer")
    layer_col_select: bpy.props.BoolProperty(name="Selectable", default=True, description="Column: layer objects can be selected (off: locked)")
    layer_col_hide: bpy.props.BoolProperty(name="Hide in viewport", default=True, description="Column: hide the layer in the 3D views (eye)")
    layer_col_viewport: bpy.props.BoolProperty(name="Disable in viewports", default=True, description="Column: disable the layer in all viewports (monitor)")
    layer_col_render: bpy.props.BoolProperty(name="Disable in renders", default=True, description="Column: disable the layer in renders (camera)")
    layer_col_holdout: bpy.props.BoolProperty(name="Holdout", default=False, description="Column: holdout")
    layer_col_indirect: bpy.props.BoolProperty(name="Indirect only", default=False, description="Column: indirect only")
    layer_sort_alpha: bpy.props.BoolProperty(name="Sort Alphabetically", default=False, description="Sorts the layers by name instead of keeping your own order")
    layer_sync_select: bpy.props.BoolProperty(name="Sync Selection", default=True, description="Clicking a layer selects its objects in the 3D view")
    layer_show_objects: bpy.props.BoolProperty(name="Objects", default=False, description="Lists the objects under each layer (limited to 300 rows)")
    layer_search: bpy.props.StringProperty(name="Name", default="", options={'TEXTEDIT_UPDATE'}, description="Shows only the layers whose name contains this text")
    layer_search_exact: bpy.props.BoolProperty(name="Exact Match", default=False)
    layer_search_case: bpy.props.BoolProperty(name="Case Sensitive", default=False)
    # --- apparence
    couleur: bpy.props.FloatVectorProperty(
        name="Color", subtype='COLOR', size=3, min=0.0, max=1.0, default=(0.1, 0.6, 1.0),
        update=_cotation_color_update,
        description="Color of lines and text (also updates existing dimensions)")
    epaisseur_trait: bpy.props.FloatProperty(
        name="Line thickness", default=0.0, min=0.0, soft_max=5.0, update=_cotation_thickness_update,
        description="Line thickness multiplier (0 = single wire, no thickness: this is what keeps dimensions out of renders)")
    subd_faces: bpy.props.IntProperty(
        name="SubD faces", default=2, min=1, max=8,
        description="SubD primitives: number of faces along each side of the control cage (like the face counts of SubDBox)")
    subd_radius: bpy.props.FloatProperty(
        name="Pipe radius", default=0.0, min=0.0, unit='LENGTH',
        description="MultiPipe: radius of the pipes (0: automatic, 4 % of the size of the curves)")
    sortie_formes: bpy.props.EnumProperty(
        name="Shapes as", default='CURVE',
        items=(('MESH', "Mesh (edges)", "Rectangles, circles, ellipses, polygons, arcs and polylines are created as mesh edges"),
               ('FACE', "Mesh (face)", "Closed shapes are created as a mesh with a filled face"),
               ('CURVE', "Curve", "Shapes are created as curve objects")),
        description="Type of object created by the 2D drawing tools")
    trim_mode: bpy.props.EnumProperty(
        name="Trim cut", default='FENCE',
        items=(('FENCE', "Fence", "Drag a straight line: every part it crosses is trimmed (F)"),
               ('CROSSING', "Crossing", "Drag a box: every part it touches is trimmed (C)")),
        description="How the Trim tool cuts when you drag: with a fence line or with a crossing box. Clicking a single part always works")
    auto_cplane: bpy.props.BoolProperty(
        name="Auto CPlane", default=False,
        description="The construction plane follows the planar object (Object mode) or the planar faces (Edit mode) you select, so you can draw on them")
    auto_cplane_hover: bpy.props.BoolProperty(
        name="Face under the cursor", default=True,
        description="Auto CPlane: while a drawing tool waits for its first point, the construction plane sits on the flat face "
                    "under the cursor, so you draw on the object instead of behind it")
    auto_cplane_sticky: bpy.props.BoolProperty(
        name="Sticky", default=False,
        description="Auto CPlane: the plane stays on the last planar selection when you select something that is not planar (otherwise it goes back to the ground plane)")
    gumball: bpy.props.BoolProperty(
        name="Show Gumball", default=True,
        description="Show the move / rotate / scale handles on the selection (objects, or vertices / edges / faces in Edit mode) when no drawing tool is active")
    offset_surf_dist: bpy.props.FloatProperty(
        name="Distance", default=0.1, min=0.0, subtype='DISTANCE', unit='LENGTH',
        description="Offset Surface: distance of the offset (remembered between uses)")
    offset_surf_solid: bpy.props.BoolProperty(
        name="Solid", default=False, description="Offset Surface: close the offset into a solid (walls on the free edges)")
    offset_surf_both: bpy.props.BoolProperty(
        name="Both sides", default=False,
        description="Offset Surface: offset on both sides of the surface (two surfaces, or one solid centered on the surface when Solid is on)")
    offset_surf_delete: bpy.props.BoolProperty(
        name="Delete input", default=False, description="Offset Surface: delete the original surface after the offset")
    gumball_drag: bpy.props.EnumProperty(
        name="Gumball dragging", default='SMOOTH',
        items=(('SNAPPY', "Snappy Dragging", "Moving with an arrow snaps to the object snaps (End, Mid, Cen...) under the cursor"),
               ('SMOOTH', "Smooth Dragging", "Moving with an arrow follows the mouse freely")),
        description="How the Gumball arrows move the selection")
    gumball_autoreset: bpy.props.BoolProperty(
        name="AutoReset Gumball", default=False,
        description="The Gumball goes back to the center of the selection each time the selection changes")
    gumball_pivot_on: bpy.props.BoolProperty(default=False)
    gumball_pivot: bpy.props.FloatVectorProperty(size=3, subtype='XYZ', default=(0.0, 0.0, 0.0))
    gumball_size: bpy.props.FloatProperty(
        name="Gumball size", default=100.0, min=20.0, max=300.0, subtype='PERCENTAGE',
        description="Size of the Gumball handles (100% = default; lower it on high-resolution screens if the handles look too big)")
    osnap_end: bpy.props.BoolProperty(name="End", default=True, description="End points of curves, polylines and open edges")
    osnap_near: bpy.props.BoolProperty(name="Near", default=True, description="Nearest point on an edge or curve")
    osnap_point: bpy.props.BoolProperty(name="Point", default=True, description="Empties, loose vertices and the world origin")
    osnap_mid: bpy.props.BoolProperty(name="Mid", default=True, description="Middle of edges and curve segments")
    osnap_cen: bpy.props.BoolProperty(name="Cen", default=True, description="Centers of circles, arcs, ellipses and polygons")
    osnap_int: bpy.props.BoolProperty(name="Int", default=True, description="Intersection of two edges or curves")
    osnap_perp: bpy.props.BoolProperty(name="Perp", default=False, description="Perpendicular to an edge from the last point picked")
    osnap_tan: bpy.props.BoolProperty(name="Tan", default=False, description="Tangent to a circle or arc from the last point picked. Line / Polyline: Tan on a first circle, then Tan on a second one, gives the exact common tangent")
    osnap_quad: bpy.props.BoolProperty(name="Quad", default=True, description="Quadrant points (0, 90, 180, 270 degrees) of circles and arcs")
    osnap_knot: bpy.props.BoolProperty(name="Knot", default=False, description="Control points and handles of curves")
    osnap_vertex: bpy.props.BoolProperty(name="Vertex", default=True, description="Vertices of meshes that have faces")
    osnap_project: bpy.props.BoolProperty(
        name="Project", default=False,
        description="Snapped points are projected onto the construction plane, so everything stays in the same plane")
    osnap_disable: bpy.props.BoolProperty(name="Disable", default=False, description="Turns every object snap off (F3 while drawing)",
                                          update=lambda self, context: _update_cursor(self, context))
    grid_snap: bpy.props.BoolProperty(
        name="Grid Snap", default=False,
        description="The cursor snaps to the grid of the construction plane, every snap spacing (F9 while drawing). "
                    "Object snaps and typed coordinates still win")
    grid_snap_step: bpy.props.FloatProperty(
        name="Snap Spacing", default=0.1, min=1e-9, precision=6,
        description="Spacing of the Grid Snap points, as a real length in metres (0.1 = 10 cm). "
                    "The Grid Snap menu shows and sets it in the unit of the scene")
    ortho: bpy.props.BoolProperty(
        name="Ortho", default=False, update=_update_ortho,
        description="Constrains the cursor to the horizontal and vertical directions of the construction plane (F8). Object snaps still win")
    polar: bpy.props.BoolProperty(
        name="Polar", default=False, update=_update_polar,
        description="The cursor snaps to angles that are multiples of the polar increment, with a guide line (F10). Object snaps still win")
    polar_angle: bpy.props.EnumProperty(
        name="Polar increment", default='45',
        items=(('5', "5°", ""), ('10', "10°", ""), ('15', "15°", ""), ('22.5', "22.5°", ""),
               ('30', "30°", ""), ('45', "45°", ""), ('90', "90°", "")),
        description="Angle between two polar guide lines")
    group_select: bpy.props.BoolProperty(
        name="Select whole group on click", default=True,
        description="Clicking an object that belongs to a group selects the entire group")
    visible_rendu: bpy.props.BoolProperty(
        name="Visible in render", default=False, update=_cotation_render_update,
        description="Dimensions (lines and text) appear in renders")
    # --- texte
    taille_texte: bpy.props.FloatProperty(
        name="Text height", default=0.0, min=0.0, subtype='DISTANCE', unit='LENGTH',
        description="Text height (0 = automatic: about 18 pixels on screen at drawing time)", update=_cotation_restyle_update)
    ecart_texte: bpy.props.FloatProperty(
        name="Text gap", default=0.3, min=0.0, soft_max=2.0,
        description="Distance between the text and the dimension line (in text heights)", update=_cotation_restyle_update)
    position_texte: bpy.props.EnumProperty(
        name="Text position", default='AU_DESSUS',
        items=(('AU_DESSUS', "Above the line", ""), ('CENTRE', "In the line", "")), update=_cotation_restyle_update)
    # --- lignes et flèches
    prolongement: bpy.props.FloatProperty(
        name="Extension line overshoot", default=0.5, min=0.0, soft_max=3.0,
        description="Extension lines past the dimension line (in text heights)", update=_cotation_restyle_update)
    decalage: bpy.props.FloatProperty(
        name="Extension line offset", default=0.25, min=0.0, soft_max=3.0,
        description="Gap between the measured point and the start of the extension line (in text heights)", update=_cotation_restyle_update)
    fleche_style: bpy.props.EnumProperty(
        name="Arrowheads", default='FLECHE',
        items=(('FLECHE', "Open arrow", ""), ('TRAIT', "Oblique tick", ""), ('FERME', "Closed arrow", ""),
               ('POINT', "Dot", ""), ('AUCUN', "None", "")), update=_cotation_restyle_update)
    fleche_taille: bpy.props.FloatProperty(
        name="Arrowhead size", default=0.8, min=0.0, soft_max=4.0,
        description="Size of arrows / ticks (in text heights)", update=_cotation_restyle_update)
    # --- unités et format
    unite_cote: bpy.props.EnumProperty(
        name="Unit", default='CENTIMETERS',
        items=(('SCENE', "Scene default", ""), ('MILLIMETERS', "Millimeters", ""),
               ('CENTIMETERS', "Centimeters", ""), ('METERS', "Meters", "")), update=_cotation_restyle_update)
    decimales: bpy.props.IntProperty(name="Resolution (decimals)", default=2, min=0, max=6, update=_cotation_restyle_update)
    supprimer_zeros: bpy.props.BoolProperty(name="Remove trailing zeros", default=False, update=_cotation_restyle_update)
    unite: bpy.props.BoolProperty(name="Show unit", default=False, update=_cotation_restyle_update)
    prefixe: bpy.props.StringProperty(name="Prefix", default="", update=_cotation_restyle_update)
    suffixe: bpy.props.StringProperty(name="Suffix", default="", update=_cotation_restyle_update)
    dim_styles: bpy.props.CollectionProperty(type=DESSIN_PG_dimstyle)
    # --- blocs
    block_insert: bpy.props.EnumProperty(name="Block", items=lambda self, context: _block_items(self, context),
                                         description="Block placed by Insert")
    block_scale: bpy.props.FloatProperty(name="Scale", default=1.0, min=1e-4, description="Scale of the inserted blocks")
    block_rotation: bpy.props.FloatProperty(name="Rotation", default=0.0, subtype='ANGLE', description="Rotation of the inserted blocks")
    # --- hachures
    hatch_pattern: bpy.props.EnumProperty(name="Pattern", items=HATCH_PATTERN_ITEMS, default='HATCH1',
                                          description="Pattern of the new hatches")
    hatch_scale: bpy.props.FloatProperty(name="Scale", default=1.0, min=0.01, soft_max=20.0,
                                         description="Pattern scale of the new hatches")
    hatch_rotation: bpy.props.FloatProperty(name="Rotation", default=0.0, subtype='ANGLE',
                                            description="Pattern rotation of the new hatches")
    hatch_spacing: bpy.props.FloatProperty(name="Spacing", default=0.0, min=0.0, subtype='DISTANCE', unit='LENGTH',
                                           description="Pattern spacing at scale 1 (0 = automatic: about 10 pixels on screen when the hatch is created)")
    hatch_boundary: bpy.props.BoolProperty(name="Boundary", default=False,
                                           description="Hatch Region also creates the boundary curves of the area")
    dim_style_index: bpy.props.IntProperty(default=0, update=_dimstyle_index_update)


def cotation_collection(context):
    if is_layout(context.scene):
        return layout_dims_collection(context.scene)      # mise en page : ses cotes ne se mêlent pas à celles du modèle
    col = bpy.data.collections.get(COTATIONS)
    if col is None:
        col = bpy.data.collections.new(COTATIONS)
    if col.name not in context.scene.collection.children:
        try:
            context.scene.collection.children.link(col)
        except RuntimeError:
            pass
    return col


def arrow_extra(style, tip, inward, side, size):
    """Segments d'une pointe de cote pour les styles autres que la flèche ouverte / le trait oblique ; None si le style est géré ailleurs."""
    if style == 'AUCUN':
        return []
    if style == 'FERME':
        back = tip + inward * size
        a = back + side * (size * 0.3)
        b = back - side * (size * 0.3)
        return [(tip, a), (tip, b), (a, b)]
    if style == 'POINT':
        r = size * 0.22
        u = inward.normalized() if inward.length > 1e-12 else Vector((1.0, 0.0, 0.0))
        w = side.normalized() if side.length > 1e-12 else Vector((0.0, 1.0, 0.0))
        pts = [tip + (u * math.cos(t) + w * math.sin(t)) * r for t in [TAU * i / 10 for i in range(11)]]
        return list(zip(pts[:-1], pts[1:]))
    return None


def build_cotation(context, d):
    """Crée une cote : courbe (lignes) + texte, rangés dans la collection « Cotations »."""
    st = context.scene.dessin
    col = cotation_collection(context)
    mat = cotation_material(tuple(st.couleur))
    rgba = (st.couleur[0], st.couleur[1], st.couleur[2], 1.0)
    cu = bpy.data.curves.new("Dimension", 'CURVE')
    cu.dimensions = '3D'
    if d["thickness"] > 0.0:
        cu.bevel_depth = d["thickness"]
        cu.bevel_resolution = 0
    cu.materials.append(mat)
    # l'origine de la cote est placée sur le texte : la ligne de parenté (pointillés) devient invisible
    org = Vector(d["frame"][3])
    for a, b in d["segments"]:
        sp = cu.splines.new('POLY')
        sp.points.add(1)
        a, b = Vector(a) - org, Vector(b) - org
        sp.points[0].co = (a.x, a.y, a.z, 1.0)
        sp.points[1].co = (b.x, b.y, b.z, 1.0)
    obj = bpy.data.objects.new(d.get("name") or ("Dimension " + d["text"]), cu)
    obj.location = org
    obj["dessin_cotation"] = d["length"]
    obj["dessin_hauteur"] = d["height"]
    obj.color = rgba
    obj.hide_render = not st.visible_rendu
    col.objects.link(obj)
    if d.get("notext"):          # repère de centre : lignes seules, pas de texte
        return obj
    fc = bpy.data.curves.new("Dimension text", 'FONT')
    fc.body = d["text"]
    fc.size = d["height"]
    fc.align_x = d.get("halign", 'CENTER')
    fc.align_y = d.get("valign") or ('BOTTOM' if st.position_texte == 'AU_DESSUS' else 'CENTER')
    fc.materials.append(mat)
    # Texte plein (Fill Mode : Both) ; le contour garde l'épaisseur des lignes de cote
    fc.fill_mode = 'BOTH'
    if d["thickness"] > 0.0:
        fc.bevel_depth = d["thickness"]
        fc.bevel_resolution = 0
    tobj = bpy.data.objects.new("Dimension text " + d["text"], fc)
    tobj["dessin_cotation_texte"] = True
    tobj["dessin_hauteur"] = d["height"]
    tobj.color = rgba
    tobj.hide_render = not st.visible_rendu
    X, Y, Z, loc = d["frame"]
    tobj.matrix_world = Matrix(((X.x, Y.x, Z.x, loc.x), (X.y, Y.y, Z.y, loc.y),
                                (X.z, Y.z, Z.z, loc.z), (0.0, 0.0, 0.0, 1.0)))
    col.objects.link(tobj)
    tobj.parent = obj
    tobj.matrix_parent_inverse = Matrix.Translation(-org)     # (matrix_world de obj n'est pas encore à jour ici)
    return obj


def _op_plane(op):
    """Plan d'une cote : celui mémorisé à sa création (reconstruction), sinon le plan de construction courant."""
    uvn = getattr(op, "uvn", None)
    if uvn is not None:
        return Vector(uvn[0]), Vector(uvn[1]), Vector(uvn[2])
    return plane_axes(op.axis)


DIM_DEF_EXTRA = ("fixed_e", "arc_param", "lfac")    # attributs supplémentaires mémorisés avec une cote (s'ils existent)
# lfac : [facteur] appliqué à la longueur mesurée (cote posée sur un détail d'une mise en page : échelle du détail)


def dim_store_def(obj, op, spec):
    """Mémorise dans la cote ce qu'il faut pour la reconstruire quand le style change."""
    try:
        right, towards = op.screen_right()
        circ = getattr(op, "circ", None)
        data = {"cls": op.bl_idname, "points": [[float(x) for x in p] for p in op.points],
                "cur": [float(x) for x in op.cur], "mode": int(getattr(op, "mode", 0)), "axis": op.axis,
                "uf": float(getattr(op, "unit_f", 1.0) or 1.0), "ul": str(getattr(op, "unit_label", "") or ""),
                "h": float(spec[1]["height"]), "right": [float(x) for x in right], "towards": [float(x) for x in towards]}
        u_, v_, n_ = _op_plane(op)
        data["uvn"] = [[float(x) for x in u_], [float(x) for x in v_], [float(x) for x in n_]]
        for key in DIM_DEF_EXTRA:
            val = getattr(op, key, None)
            if val is not None:
                data[key] = [float(x) for x in val]
        if circ is not None and op.bl_idname in ("dessin.cotation_rayon", "dessin.cotation_arc"):
            data["circ"] = [[float(x) for x in circ[0]], float(circ[1]), [float(x) for x in circ[2]],
                            [float(x) for x in circ[3]], [float(x) for x in circ[4]]]
        obj["dessin_dim"] = json.dumps(data)
    except (AttributeError, TypeError, ValueError, ReferenceError):
        pass


def _dim_classes():
    """Classes de cote accessibles par bl_idname ET par nom de classe (cotes posées par une version plus ancienne)."""
    out = {}
    for c in (DESSIN_OT_cotation, DESSIN_OT_cotation_rayon, DESSIN_OT_cotation_angle,
              DESSIN_OT_cotation_ordinate, DESSIN_OT_cotation_arc):
        out[c.bl_idname] = c
        out[c.__name__] = c
    return out


def _dim_replay_spec(data):
    cls = _dim_classes().get(data.get("cls"))
    if cls is None:
        return None
    st = bpy.context.scene.dessin
    right, towards = Vector(data["right"]), Vector(data["towards"])
    h0 = float(data["h"])
    fake = types.SimpleNamespace(points=[Vector(p) for p in data["points"]], cur=Vector(data["cur"]), mode=data["mode"],
                                 axis=data["axis"], unit_f=data["uf"], unit_label=data["ul"], dim_label=None, circ=None,
                                 region=None, area=None)
    if data.get("circ"):
        c, r, n, e1, e2 = data["circ"]
        fake.circ = (c, r, n, e1, e2, np.zeros((0, 3)), 1e-6)
    fake.uvn = data.get("uvn")
    for key in DIM_DEF_EXTRA:
        setattr(fake, key, data.get(key))
    fake.ldet = data.get("ldet")          # mise en page : détail auquel la cote est attachée (son échelle fait foi)
    fake.screen_right = lambda: (right, towards)
    fake.text_height = lambda mid, e: st.taille_texte if st.taille_texte > 0.0 else h0
    for name in ("unit_for_text", "text_for", "angle_text", "geometry", "arc_geometry", "compute"):
        f = getattr(cls, name, None)
        if f is not None:
            setattr(fake, name, types.MethodType(f, fake))
    spec = fake.compute()[3]
    txt = data.get("txt")
    if spec is not None and spec[0] == 'dim' and txt:
        spec[1]["text"] = txt.replace("<>", spec[1]["text"])     # texte personnalisé : <> = valeur mesurée
    return spec


def rebuild_dimension(context, obj):
    """Reconstruit une cote déjà posée avec les réglages de style actuels (texte, flèches, prolongements, format)."""
    data = json.loads(obj["dessin_dim"])
    spec = _dim_replay_spec(data)
    if spec is None or spec[0] != 'dim':
        return False
    try:
        was_sel = obj.select_get()
    except (RuntimeError, ReferenceError):
        was_sel = False
    for o in [obj] + list(obj.children):
        d = o.data
        bpy.data.objects.remove(o, do_unlink=True)
        if d is not None and d.users == 0:
            bpy.data.curves.remove(d)
    new = build_cotation(context, spec[1])
    new["dessin_dim"] = json.dumps(data)
    _DIM_EDIT["busy"] = True
    try:
        new.dessin_dim.text = data.get("txt", "")
    except AttributeError:
        pass
    finally:
        _DIM_EDIT["busy"] = False
    if was_sel:
        try:
            new.select_set(True)
        except (RuntimeError, ReferenceError):
            pass
    return new


def _late_imports():
    """Noms définis dans des modules chargés après celui-ci : ils ne servent qu'à l'exécution des outils."""
    global DESSIN_OT_cotation, DESSIN_OT_cotation_angle, DESSIN_OT_cotation_arc, DESSIN_OT_cotation_ordinate
    global DESSIN_OT_cotation_rayon, HatchTooDense, _block_items, _update_cursor, is_hatch, rebuild_hatch
    from .dimensions import (
        DESSIN_OT_cotation, DESSIN_OT_cotation_angle, DESSIN_OT_cotation_arc, DESSIN_OT_cotation_ordinate,
    DESSIN_OT_cotation_rayon,
    )
    from .hatch import HatchTooDense, is_hatch, rebuild_hatch
    from .curve_tools import _block_items
    global is_layout, layout_dims_collection
    from .layout import is_layout, layout_dims_collection
    from .navigation import _update_cursor
