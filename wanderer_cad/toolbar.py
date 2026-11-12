"""Wanderer CAD : Outils de la barre de gauche."""

import bpy

from .drawing import hover_draw_cursor
from .selection import circle_draw_cursor


class DESSIN_TT_deplacer(bpy.types.WorkSpaceTool):
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'OBJECT'
    bl_idname = "dessin.deplacer_tool"
    bl_label = "Move (base → destination)"
    bl_description = ("Moves the selection with a snapped base point and destination point. Shift: orthogonal, C: copy, type a distance then Enter")
    bl_icon = "ops.transform.translate"
    bl_widget = None
    bl_keymap = (
        ("dessin.deplacer", {"type": 'LEFTMOUSE', "value": 'PRESS'}, None),
        # la commande démarre dès que la souris bouge : accrochage visible avant le premier clic
        ("dessin.deplacer", {"type": 'MOUSEMOVE', "value": 'ANY'}, None),
        ("dessin.tool_exit", {"type": 'ESC', "value": 'PRESS'}, None),   # Échap hors commande : quitte l'outil
    )
    draw_cursor = staticmethod(hover_draw_cursor)
    bl_cursor = 'NONE'

    def draw_settings(context, layout, tool):
        layout.label(text="Select the objects first  ·  Shift: orthogonal  ·  C: copy  ·  distance + Enter")


class DESSIN_TT_copier(bpy.types.WorkSpaceTool):
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'OBJECT'
    bl_idname = "dessin.copier_tool"
    bl_label = "Copy (base → destinations)"
    bl_description = ("Copies the selection with a base point then several snapped destinations. Shift: orthogonal, type a distance then Enter, Enter/Esc: finish")
    bl_icon = "ops.transform.translate"
    bl_widget = None
    bl_keymap = (
        ("dessin.copier", {"type": 'LEFTMOUSE', "value": 'PRESS'}, None),
        ("dessin.copier", {"type": 'MOUSEMOVE', "value": 'ANY'}, None),
        ("dessin.tool_exit", {"type": 'ESC', "value": 'PRESS'}, None),   # Échap hors commande : quitte l'outil
    )
    draw_cursor = staticmethod(hover_draw_cursor)
    bl_cursor = 'NONE'

    def draw_settings(context, layout, tool):
        layout.label(text="Base point then as many destinations as you want  ·  Shift: orthogonal  ·  distance + Enter  ·  Esc: finish")


class DESSIN_TT_selection_boite(bpy.types.WorkSpaceTool):
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'OBJECT'
    bl_idname = "dessin.selection_boite_tool"
    bl_label = "Select"
    bl_description = ("Click or drag a box to select (left → right: fully inside, right → left: touched; Shift: add, "
                      "Ctrl/Cmd: remove; Ctrl/Cmd+Shift click: a vertex, edge or face, like Rhino). Drag an object to move it freely "
                      "in the view plane; use the Gumball handles for exact moves")
    bl_icon = "ops.generic.select_box"
    bl_widget = None
    bl_keymap = (
        ("dessin.select_loop", {"type": 'LEFTMOUSE', "value": 'DOUBLE_CLICK', "any": True}, None),
        ("dessin.selection_boite", {"type": 'LEFTMOUSE', "value": 'PRESS', "any": True}, None),
        ("dessin.deselect", {"type": 'ESC', "value": 'PRESS'}, None),
    )

    def draw_settings(context, layout, tool):
        layout.label(text="Esc: deselect  ·  Double-click an edge: select the loop  ·  Drag an object: move  ·  drag empty space: box (left → right: inside, right → left: touched)  ·  Shift: add  ·  Ctrl/Cmd: remove  ·  Ctrl/Cmd+Shift: vertex / edge / face")


class DESSIN_TT_selection_lasso(bpy.types.WorkSpaceTool):
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'OBJECT'
    bl_idname = "dessin.selection_lasso_tool"
    bl_label = "Lasso Select"
    bl_description = ("Drag a free-hand loop to select, like AutoCAD (start dragging to the right: fully inside, "
                      "to the left: touched; Shift: add, Ctrl/Cmd: remove). Click an object to select it")
    bl_icon = "ops.generic.select_lasso"
    bl_widget = None
    bl_keymap = (
        ("dessin.select_loop", {"type": 'LEFTMOUSE', "value": 'DOUBLE_CLICK', "any": True}, None),
        ("dessin.selection_lasso", {"type": 'LEFTMOUSE', "value": 'PRESS', "any": True}, None),
        ("dessin.deselect", {"type": 'ESC', "value": 'PRESS'}, None),
    )

    def draw_settings(context, layout, tool):
        layout.label(text="Esc: deselect  ·  Drag a free loop: start to the right = fully inside, to the left = touched (dashed)  ·  Shift: add  ·  Ctrl/Cmd: remove")


class DESSIN_TT_selection_rect(bpy.types.WorkSpaceTool):
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'OBJECT'
    bl_idname = "dessin.selection_rect_tool"
    bl_label = "Select Box"
    bl_description = ("Drag a box to select, without moving anything (left → right: fully inside, right → left: touched; "
                      "Shift: add, Ctrl/Cmd: remove). Click an object to select it")
    bl_icon = "ops.generic.select_box"
    bl_widget = None
    bl_keymap = (
        ("dessin.select_loop", {"type": 'LEFTMOUSE', "value": 'DOUBLE_CLICK', "any": True}, None),
        ("dessin.selection_rect", {"type": 'LEFTMOUSE', "value": 'PRESS', "any": True}, None),
        ("dessin.deselect", {"type": 'ESC', "value": 'PRESS'}, None),
    )

    def draw_settings(context, layout, tool):
        layout.label(text="Esc: deselect  ·  Drag a box: left → right = fully inside, right → left = touched (dashed)  ·  Shift: add  ·  Ctrl/Cmd: remove")


class DESSIN_TT_selection_cercle(bpy.types.WorkSpaceTool):
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'OBJECT'
    bl_idname = "dessin.selection_cercle_tool"
    bl_label = "Select Circle"
    bl_description = ("Paint a selection with a circular brush: everything the circle touches is selected while you drag "
                      "(Shift: add, Ctrl/Cmd: remove, mouse wheel while dragging: brush size)")
    bl_icon = "ops.generic.select_circle"
    bl_widget = None
    bl_keymap = (
        ("dessin.selection_cercle", {"type": 'LEFTMOUSE', "value": 'PRESS', "any": True}, None),
        ("dessin.deselect", {"type": 'ESC', "value": 'PRESS'}, None),
    )
    draw_cursor = staticmethod(circle_draw_cursor)

    def draw_settings(context, layout, tool):
        layout.label(text="Esc: deselect  ·  Drag to paint the selection  ·  Wheel: brush size  ·  Shift: add  ·  Ctrl/Cmd: remove")


_SELECT_TOOL_IDS = (DESSIN_TT_selection_boite.bl_idname, DESSIN_TT_selection_lasso.bl_idname,
                    DESSIN_TT_selection_rect.bl_idname, DESSIN_TT_selection_cercle.bl_idname)


class DESSIN_TT_polyligne(bpy.types.WorkSpaceTool):
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'OBJECT'
    bl_idname = "dessin.polyligne_tool"
    bl_label = "Polyline (point by point)"
    bl_description = ("Draws a polyline point by point with snapping; click the first point to close the shape, Enter to finish, length can be typed")
    bl_icon = "ops.gpencil.draw"
    bl_widget = None
    bl_keymap = (
        ("dessin.polyligne", {"type": 'LEFTMOUSE', "value": 'PRESS'}, None),
        ("dessin.polyligne", {"type": 'MOUSEMOVE', "value": 'ANY'}, None),
        ("dessin.tool_exit", {"type": 'ESC', "value": 'PRESS'}, None),   # Échap hors commande : quitte l'outil
    )
    draw_cursor = staticmethod(hover_draw_cursor)
    bl_cursor = 'NONE'

    def draw_settings(context, layout, tool):
        layout.prop(context.scene.dessin, "sortie_formes", text="")
        layout.label(text="Click: successive points  ·  click the first point: close  ·  Enter: finish  ·  Backspace: undo last point  ·  Shift: orthogonal")


class DESSIN_TT_plan(bpy.types.WorkSpaceTool):
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'OBJECT'
    bl_idname = "dessin.plan_tool"
    bl_label = "Plane (first corner → opposite corner)"
    bl_description = ("Draws a plane with the mouse with snapping, starting from the chosen point (C: from center, type width / Tab / height then Enter)")
    bl_icon = "ops.mesh.primitive_plane_add_gizmo"
    bl_widget = None
    bl_keymap = (
        ("dessin.plan", {"type": 'LEFTMOUSE', "value": 'PRESS'}, None),
        ("dessin.plan", {"type": 'MOUSEMOVE', "value": 'ANY'}, None),
        ("dessin.tool_exit", {"type": 'ESC', "value": 'PRESS'}, None),   # Échap hors commande : quitte l'outil
    )
    draw_cursor = staticmethod(hover_draw_cursor)
    bl_cursor = 'NONE'

    def draw_settings(context, layout, tool):
        layout.label(text="Click the first corner then the opposite corner  ·  C: from center  ·  width, Tab, height + Enter")


class DESSIN_TT_rotation(bpy.types.WorkSpaceTool):
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'OBJECT'
    bl_idname = "dessin.rotation_tool"
    bl_label = "Rotate (center, reference, angle)"
    bl_description = ("Rotates the selection: center, reference point, target point or typed angle. R: Reference (reference angle by two points, then the new angle). Shift: 15° steps, C: copy")
    bl_icon = "ops.transform.rotate"
    bl_widget = None
    bl_keymap = (
        ("dessin.rotation", {"type": 'LEFTMOUSE', "value": 'PRESS'}, None),
        # la commande démarre dès que la souris bouge : accrochage visible avant le premier clic
        ("dessin.rotation", {"type": 'MOUSEMOVE', "value": 'ANY'}, None),
        ("dessin.tool_exit", {"type": 'ESC', "value": 'PRESS'}, None),   # Échap hors commande : quitte l'outil
    )
    draw_cursor = staticmethod(hover_draw_cursor)
    bl_cursor = 'NONE'

    def draw_settings(context, layout, tool):
        layout.label(text="Select the objects first  ·  Shift: 15° steps  ·  C: copy  ·  angle + Enter")


class DESSIN_TT_echelle(bpy.types.WorkSpaceTool):
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'OBJECT'
    bl_idname = "dessin.echelle_tool"
    bl_label = "Scale"
    bl_description = ("Scales the selection: base point, two reference points or typed factor. R: Reference (reference length by two points, then new length; R again: free reference with a second base point), D: 3D / 2D / 1D, C: copy")
    bl_icon = "ops.transform.resize"
    bl_widget = None
    bl_keymap = (
        ("dessin.echelle", {"type": 'LEFTMOUSE', "value": 'PRESS'}, None),
        # la commande démarre dès que la souris bouge : accrochage visible avant le premier clic
        ("dessin.echelle", {"type": 'MOUSEMOVE', "value": 'ANY'}, None),
        ("dessin.tool_exit", {"type": 'ESC', "value": 'PRESS'}, None),   # Échap hors commande : quitte l'outil
    )
    draw_cursor = staticmethod(hover_draw_cursor)
    bl_cursor = 'NONE'

    def draw_settings(context, layout, tool):
        layout.label(text="Select the objects first  ·  D: 3D / 2D / 1D  ·  C: copy  ·  factor + Enter")


DESSIN_TT_echelle_2d = None   # définis plus bas (après _draw_tool_cls)
DESSIN_TT_echelle_1d = None
DESSIN_TT_echelle_taille = None
SHAPE_OPS = {"dessin.xline", "dessin.rectangle", "dessin.cercle", "dessin.cercle_diametre", "dessin.ellipse_centre", "dessin.ellipse_diametre",
             "dessin.ellipse_foyers", "dessin.ellipse_coin", "dessin.arc_cse", "dessin.arc_3pts", "dessin.poly_center",
             "dessin.poly_circ", "dessin.poly_area", "dessin.poly_edge", "dessin.poly_star"}


def _draw_tool_cls(name, idname, op, label, desc, hint, hover=True):
    """Fabrique un outil de la barre pour une commande de dessin (armé au survol : accrochage visible)."""
    keymap = ((op, {"type": 'LEFTMOUSE', "value": 'PRESS'}, None),)
    if hover:
        keymap += ((op, {"type": 'MOUSEMOVE', "value": 'ANY'}, None),)
    # Échap hors commande en cours : quitte l'outil (une commande modale en cours gère Échap elle-même)
    keymap += (("dessin.tool_exit", {"type": 'ESC', "value": 'PRESS'}, None),)

    shaped = op in SHAPE_OPS

    def draw_settings(context, layout, tool):
        if shaped:
            layout.prop(context.scene.dessin, "sortie_formes", text="")
        layout.label(text=hint)

    attrs = {
        "bl_space_type": 'VIEW_3D', "bl_context_mode": 'OBJECT', "bl_idname": idname,
        "bl_label": label, "bl_description": desc, "bl_icon": "ops.generic.select_box",
        "bl_widget": None, "bl_keymap": keymap, "draw_settings": draw_settings, "dessin_hint": hint,
    }
    if hover:
        attrs["draw_cursor"] = staticmethod(hover_draw_cursor)
        attrs["bl_cursor"] = 'NONE'       # le curseur de l'OS est remplacé par le réticule dessiné
    return type(name, (bpy.types.WorkSpaceTool,), attrs)


DESSIN_TT_rectangle = _draw_tool_cls(
    "DESSIN_TT_rectangle", "dessin.rectangle_tool", "dessin.rectangle", "Rectangle",
    "Draws a rectangle with the mouse with snapping (C: from center, type width / Tab / height)",
    "First corner then opposite corner  ·  C: from center  ·  width, Tab, height + Enter")
DESSIN_TT_miroir = _draw_tool_cls(
    "DESSIN_TT_miroir", "dessin.mirror_tool", "dessin.mirror", "Mirror",
    "Mirrors the selection about a plane defined by a line of two points (Shift: orthogonal, C: copy / replace)",
    "Two points of the mirror line  ·  Shift: orthogonal  ·  C: keep or replace the original")
DESSIN_TT_array_rect = _draw_tool_cls(
    "DESSIN_TT_array_rect", "dessin.array_rect_tool", "dessin.array_rect", "Array: Rectangular",
    "Rectangular array: base corner then opposite corner of the unit cell (type counts X, Y, Z and spacings with Tab)",
    "Unit cell: two corners  ·  type X count, Tab, Y count, Tab, Z count, Tab, spacings  ·  Enter")
DESSIN_TT_array_linear = _draw_tool_cls(
    "DESSIN_TT_array_linear", "dessin.array_linear_tool", "dessin.array_linear", "Array: Linear",
    "Linear array: base point then second point (D: spacing or total length, type count / Tab / spacing)",
    "Base point, second point  ·  D: spacing / total length  ·  type count, Tab, spacing + Enter")
DESSIN_TT_array_polar = _draw_tool_cls(
    "DESSIN_TT_array_polar", "dessin.array_polar_tool", "dessin.array_polar", "Array: Polar",
    "Polar array around a center: click the center, type the count and the angle (D: rotate items, F: other direction)",
    "Center  ·  type count, Tab, angle + Enter  ·  D: rotate items / keep orientation  ·  F: direction")
DESSIN_TT_array_rect._in_group = True
DESSIN_TT_array_polar._in_group = True
DESSIN_TT_cut = _draw_tool_cls(
    "DESSIN_TT_cut", "dessin.cut_tool", "dessin.cut", "Split",
    "Splits solids into separate parts with a vertical plane defined by a line, and caps the cut",
    "Solids  ·  line of the splitting plane (two points, or click an existing line)")
DESSIN_TT_fillet = _draw_tool_cls(
    "DESSIN_TT_fillet", "dessin.fillet_edge_tool", "dessin.fillet_edge", "Fillet Edge",
    "Rounds the edges of solids: click the edges, Enter, then type the radius (↑/↓: segments)",
    "Click or drag a box (right: inside, left: touching, Ctrl/Cmd: remove)  ·  Enter  ·  type the radius, Tab, segments  ·  Enter: confirm")
DESSIN_TT_chamfer = _draw_tool_cls(
    "DESSIN_TT_chamfer", "dessin.chamfer_edge_tool", "dessin.chamfer_edge", "Chamfer Edge",
    "Bevels the edges of solids: click the edges or drag a box, Enter, then type the distance",
    "Click or drag a box (right: inside, left: touching, Ctrl/Cmd: remove)  ·  Enter  ·  type the distance  ·  Enter: confirm")
DESSIN_TT_chamfer._in_group = True
DESSIN_TT_offset = _draw_tool_cls(
    "DESSIN_TT_offset", "dessin.offset_edge_tool", "dessin.offset_edge", "Offset Edge",
    "Parallel copy of edges or curves: click the edges (or a curve), Enter, then the side with the mouse and the distance typed",
    "Click edges / a curve or drag a box  ·  Enter  ·  mouse: side  ·  type the distance  ·  click / Enter: confirm")
DESSIN_TT_offset._in_group = True
DESSIN_TT_bool_union = _draw_tool_cls(
    "DESSIN_TT_bool_union", "dessin.bool_union_tool", "dessin.bool_union", "Boolean Union",
    "Joins several solids into one: click the objects, then Enter",
    "Click the objects to join  ·  Enter  ·  D: keep the originals")
DESSIN_TT_bool_difference = _draw_tool_cls(
    "DESSIN_TT_bool_difference", "dessin.bool_difference_tool", "dessin.bool_difference", "Boolean Difference",
    "Subtracts solids from others: objects to cut into + Enter, then objects to subtract + Enter",
    "Objects to cut into, Enter  ·  objects to subtract, Enter  ·  D: keep the originals")
DESSIN_TT_bool_intersection = _draw_tool_cls(
    "DESSIN_TT_bool_intersection", "dessin.bool_intersection_tool", "dessin.bool_intersection", "Boolean Intersection",
    "Keeps only the volume shared by two sets of solids: first set + Enter, then second set + Enter",
    "First set, Enter  ·  second set, Enter  ·  D: keep the originals")
DESSIN_TT_bool_split = _draw_tool_cls(
    "DESSIN_TT_bool_split", "dessin.bool_split_tool", "dessin.bool_split", "Boolean Split",
    "Splits solids with other solids (inside part and outside part): objects to split + Enter, then cutters + Enter",
    "Objects to split, Enter  ·  cutting objects, Enter")
DESSIN_TT_bool_difference._in_group = True
DESSIN_TT_bool_intersection._in_group = True
DESSIN_TT_bool_split._in_group = True
DESSIN_TT_poly_center = _draw_tool_cls(
    "DESSIN_TT_poly_center", "dessin.poly_center_tool", "dessin.poly_center", "Polygon: Center, Radius",
    "Regular polygon inscribed in a circle: center then a vertex (↑ / ↓: number of sides, or type the radius)",
    "Center, then a vertex  ·  ↑ / ↓: number of sides  ·  type the radius + Enter")
DESSIN_TT_poly_circ = _draw_tool_cls(
    "DESSIN_TT_poly_circ", "dessin.poly_circ_tool", "dessin.poly_circ", "Polygon: Circumscribed",
    "Regular polygon circumscribed about a circle: center then the middle of an edge (↑ / ↓: number of sides)",
    "Center, then the middle of an edge  ·  ↑ / ↓: number of sides  ·  type the radius + Enter")
DESSIN_TT_poly_area = _draw_tool_cls(
    "DESSIN_TT_poly_area", "dessin.poly_area_tool", "dessin.poly_area", "Polygon: Area",
    "Regular polygon with a given area: center then a vertex, or type the area (↑ / ↓: number of sides)",
    "Center, then a vertex  ·  ↑ / ↓: number of sides  ·  type the area + Enter")
DESSIN_TT_poly_edge = _draw_tool_cls(
    "DESSIN_TT_poly_edge", "dessin.poly_edge_tool", "dessin.poly_edge", "Polygon: Edge",
    "Regular polygon from one edge: two points (F: other side, ↑ / ↓: number of sides)",
    "Start and end of an edge  ·  F: other side  ·  ↑ / ↓: number of sides  ·  type the length + Enter")
DESSIN_TT_poly_star = _draw_tool_cls(
    "DESSIN_TT_poly_star", "dessin.poly_star_tool", "dessin.poly_star", "Polygon: Star",
    "Star: center, outer radius then inner radius (↑ / ↓: number of points)",
    "Center, outer radius, inner radius  ·  ↑ / ↓: number of points  ·  type outer, Tab, inner")
for _t in (DESSIN_TT_poly_circ, DESSIN_TT_poly_area, DESSIN_TT_poly_edge, DESSIN_TT_poly_star):
    _t._in_group = True  # même menu déroulant (tête : Polygon: Center, Radius)
DESSIN_TT_cercle = _draw_tool_cls(
    "DESSIN_TT_cercle", "dessin.cercle_tool", "dessin.cercle", "Circle: Center, Radius",
    "Draws a circle with the mouse with snapping (center then radius, or type the radius)",
    "Center then radius  ·  type the radius + Enter")
DESSIN_TT_cercle_d = _draw_tool_cls(
    "DESSIN_TT_cercle_d", "dessin.cercle_diametre_tool", "dessin.cercle_diametre", "Circle: Diameter",
    "Draws a circle with the mouse: two ends of the diameter, with snapping",
    "Two ends of the diameter  ·  type the diameter + Enter")
DESSIN_TT_cercle_d._in_group = True  # même menu déroulant que le cercle (centre, rayon)
DESSIN_TT_ellipse_c = _draw_tool_cls(
    "DESSIN_TT_ellipse_c", "dessin.ellipse_centre_tool", "dessin.ellipse_centre", "Ellipse: From Center",
    "Ellipse: center, end of the first axis, then end of the second axis",
    "Center, end of the first axis, end of the second axis")
DESSIN_TT_ellipse_d = _draw_tool_cls(
    "DESSIN_TT_ellipse_d", "dessin.ellipse_diametre_tool", "dessin.ellipse_diametre", "Ellipse: Diameter",
    "Ellipse: two ends of the first axis, then end of the second axis",
    "Two ends of the first axis, then end of the second axis")
DESSIN_TT_ellipse_f = _draw_tool_cls(
    "DESSIN_TT_ellipse_f", "dessin.ellipse_foyers_tool", "dessin.ellipse_foyers", "Ellipse: From Foci",
    "Ellipse: first focus, second focus, then a point on the ellipse",
    "First focus, second focus, point on the ellipse")
DESSIN_TT_ellipse_k = _draw_tool_cls(
    "DESSIN_TT_ellipse_k", "dessin.ellipse_coin_tool", "dessin.ellipse_coin", "Ellipse: By Corners",
    "Ellipse inscribed in a rectangle: two opposite corners (width / Tab / height can be typed)",
    "First corner then opposite corner  ·  width, Tab, height + Enter")
for _t in (DESSIN_TT_ellipse_d, DESSIN_TT_ellipse_f, DESSIN_TT_ellipse_k):
    _t._in_group = True  # menu déroulant propre aux ellipses (tête : Ellipse depuis le centre)
DESSIN_TT_arc_cse = _draw_tool_cls(
    "DESSIN_TT_arc_cse", "dessin.arc_cse_tool", "dessin.arc_cse", "Arc: Center, Start, End",
    "Draws an arc: center, start point then end point, with snapping",
    "Center, start point then end point")
DESSIN_TT_arc_3pts = _draw_tool_cls(
    "DESSIN_TT_arc_3pts", "dessin.arc_3pts_tool", "dessin.arc_3pts", "Arc: 3 Points",
    "Draws an arc through three points, with snapping",
    "Start, intermediate point then end")
DESSIN_TT_arc_3pts._in_group = True  # même menu déroulant que l'arc (centre, début, fin)

DESSIN_TT_boite = _draw_tool_cls(
    "DESSIN_TT_boite", "dessin.boite_tool", "dessin.boite", "Box",
    "Box: first corner, opposite corner, then height (C: from center, type width / Tab / depth / Tab / height)",
    "First corner, opposite corner, height  ·  C: from center  ·  width, Tab, depth, Tab, height + Enter")
DESSIN_TT_cylindre = _draw_tool_cls(
    "DESSIN_TT_cylindre", "dessin.cylindre_tool", "dessin.cylindre", "Cylinder",
    "Cylinder: base center, radius then height",
    "Center, radius, height  ·  type radius, Tab, height + Enter")
DESSIN_TT_cone = _draw_tool_cls(
    "DESSIN_TT_cone", "dessin.cone_tool", "dessin.cone", "Cone",
    "Cone: base center, radius then apex height",
    "Center, radius, height  ·  type radius, Tab, height + Enter")
DESSIN_TT_cone_tronque = _draw_tool_cls(
    "DESSIN_TT_cone_tronque", "dessin.cone_tronque_tool", "dessin.cone_tronque", "Truncated Cone",
    "Truncated cone: base center, radius, height then top radius",
    "Center, radius, height, top radius  ·  type radius, Tab, height, Tab, top radius")
DESSIN_TT_pyramide = _draw_tool_cls(
    "DESSIN_TT_pyramide", "dessin.pyramide_tool", "dessin.pyramide", "Pyramid",
    "Pyramid: base center, radius, height (↑ / ↓: number of sides)",
    "Center, radius, height  ·  ↑ / ↓: number of sides")
DESSIN_TT_pyramide_tronquee = _draw_tool_cls(
    "DESSIN_TT_pyramide_tronquee", "dessin.pyramide_tronquee_tool", "dessin.pyramide_tronquee", "Truncated Pyramid",
    "Truncated pyramid: base center, radius, height then top radius (↑ / ↓: number of sides)",
    "Center, radius, height, top radius  ·  ↑ / ↓: number of sides")
DESSIN_TT_tube = _draw_tool_cls(
    "DESSIN_TT_tube", "dessin.tube_tool", "dessin.tube", "Tube",
    "Tube: center, outer radius, inner radius then height",
    "Center, outer radius, inner radius, height  ·  type Ro, Tab, Ri, Tab, height")
DESSIN_TT_sphere = _draw_tool_cls(
    "DESSIN_TT_sphere", "dessin.sphere_tool", "dessin.sphere", "Sphere",
    "Sphere: center then radius (or type the radius)",
    "Center then radius  ·  type the radius + Enter")
DESSIN_TT_ellipsoide = _draw_tool_cls(
    "DESSIN_TT_ellipsoide", "dessin.ellipsoide_tool", "dessin.ellipsoide", "Ellipsoid",
    "Ellipsoid: center then the ends of the three axes",
    "Center, axis 1, axis 2, axis 3 (height)  ·  type a, Tab, b, Tab, c")
DESSIN_TT_sphere_tronquee = _draw_tool_cls(
    "DESSIN_TT_sphere_tronquee", "dessin.sphere_tronquee_tool", "dessin.sphere_tronquee", "Truncated Sphere",
    "Sphere cut by a plane: center, radius then cut height",
    "Center, radius, cut height  ·  type radius, Tab, height")
DESSIN_TT_tore = _draw_tool_cls(
    "DESSIN_TT_tore", "dessin.tore_tool", "dessin.tore", "Torus",
    "Torus: center, major radius then tube radius",
    "Center, major radius, tube radius  ·  type R, Tab, r")
DESSIN_TT_cylindre._in_group = True
DESSIN_TT_cone._in_group = True
DESSIN_TT_cone_tronque._in_group = True
DESSIN_TT_pyramide._in_group = True
DESSIN_TT_pyramide_tronquee._in_group = True
DESSIN_TT_tube._in_group = True
DESSIN_TT_ellipsoide._in_group = True
DESSIN_TT_sphere_tronquee._in_group = True
DESSIN_TT_tore._in_group = True

DESSIN_TT_cotation = _draw_tool_cls(
    "DESSIN_TT_cotation", "dessin.cotation_tool", "dessin.cotation", "Dimension (measure)",
    "Measures and dimensions: two points then the position of the dimension line (D: aligned / horizontal / vertical)",
    "Two points then the dimension line  ·  D: aligned / horizontal / vertical")


def _cotation_settings(context, layout, tool):
    st = context.scene.dessin
    layout.label(text="Two points, then the dimension line  ·  D: mode  ·  X/Y/Z: axis")
    layout.prop(st, "couleur", text="")
    layout.prop(st, "taille_texte")
    layout.prop(st, "decimales")


DESSIN_TT_cotation.draw_settings = _cotation_settings

DESSIN_TT_cotation_rayon = _draw_tool_cls(
    "DESSIN_TT_cotation_rayon", "dessin.cotation_rayon_tool", "dessin.cotation_rayon", "Radius / Diameter",
    "Radius or diameter dimension: click a circle or an arc, then the position of the dimension (D: radius / diameter)",
    "Click a circle or an arc, then the dimension position  ·  D: radius / diameter")
DESSIN_TT_cotation_rayon.draw_settings = _cotation_settings
DESSIN_TT_cotation_angle = _draw_tool_cls(
    "DESSIN_TT_cotation_angle", "dessin.cotation_angle_tool", "dessin.cotation_angle", "Angular Dimension",
    "Angle dimension: the vertex, a point on each side, then the position of the arc (D: inner / reflex angle)",
    "Vertex, point on the first side, point on the second side, then the arc  ·  D: inner / reflex angle")
DESSIN_TT_cotation_angle.draw_settings = _cotation_settings
DESSIN_TT_annotation = _draw_tool_cls(
    "DESSIN_TT_annotation", "dessin.annotation_tool", "dessin.annotation", "Annotation (leader)",
    "Text note with a leader line: click the point to point at, click where the text goes, type the text, Enter",
    "Point to point at, then the text position  ·  type the text  ·  Enter: create  ·  Esc: cancel")
DESSIN_TT_annotation.draw_settings = _cotation_settings
def _subd_settings(context, layout, tool):
    layout.prop(context.scene.dessin, "subd_faces")
    layout.label(text=getattr(tool, "dessin_hint", "") if hasattr(tool, "dessin_hint") else "")


DESSIN_TT_subd_box = _draw_tool_cls(
    "DESSIN_TT_subd_box", "dessin.subd_box_tool", "dessin.subd_box", "SubD Box",
    "SubD box like SubDBox: first corner, opposite corner, then height. Smooth surface over a quad control cage, editable in Edit Mode",
    "First corner, opposite corner, height  ·  C: from center  ·  SubD faces: faces per side of the cage")
DESSIN_TT_subd_sphere = _draw_tool_cls(
    "DESSIN_TT_subd_sphere", "dessin.subd_sphere_tool", "dessin.subd_sphere", "SubD Sphere",
    "SubD sphere like SubDSphere (quad ball): center then radius",
    "Center, then radius  ·  SubD faces: density of the cage")
DESSIN_TT_subd_cylinder = _draw_tool_cls(
    "DESSIN_TT_subd_cylinder", "dessin.subd_cylinder_tool", "dessin.subd_cylinder", "SubD Cylinder",
    "SubD cylinder like SubDCylinder: center, radius, then height",
    "Center, radius, height  ·  SubD faces: density of the cage")
DESSIN_TT_subd_cone = _draw_tool_cls(
    "DESSIN_TT_subd_cone", "dessin.subd_cone_tool", "dessin.subd_cone", "SubD Cone",
    "SubD cone like SubDCone: center, radius, then height",
    "Center, radius, height  ·  SubD faces: density of the cage")
DESSIN_TT_subd_torus = _draw_tool_cls(
    "DESSIN_TT_subd_torus", "dessin.subd_torus_tool", "dessin.subd_torus", "SubD Torus",
    "SubD torus like SubDTorus: center, first radius, second radius",
    "Center, first radius, second radius  ·  SubD faces: density of the cage")
DESSIN_TT_subd_plane = _draw_tool_cls(
    "DESSIN_TT_subd_plane", "dessin.subd_plane_tool", "dessin.subd_plane", "SubD Plane",
    "SubD plane like SubDPlane: first corner then opposite corner (a grid of quads, sharp corners)",
    "First corner, opposite corner  ·  SubD faces: density of the grid")
for _t in (DESSIN_TT_subd_box, DESSIN_TT_subd_sphere, DESSIN_TT_subd_cylinder, DESSIN_TT_subd_cone, DESSIN_TT_subd_torus, DESSIN_TT_subd_plane):
    _t.draw_settings = _subd_settings
for _t in (DESSIN_TT_subd_sphere, DESSIN_TT_subd_cylinder, DESSIN_TT_subd_cone, DESSIN_TT_subd_torus, DESSIN_TT_subd_plane):
    _t._in_group = True          # un seul menu déroulant SubD (tête : SubD Box)
def _subd_cmd_tool(name, action, label, desc, hint, mode, kind, group=False, keymap=None):
    """Outil de la barre pour une commande SubD : on désigne (objets en mode Objet, sommets / arêtes / faces en Édition),
    puis Entrée / Espace / clic droit lance la commande."""
    cls = _draw_tool_cls(name, f"dessin.subdc_{action.lower()}_{'edit' if mode == 'EDIT_MESH' else 'obj'}_tool", "dessin.subd",
                         label, desc, hint, hover=False)
    run = [("dessin.subd", {"type": k, "value": 'PRESS'}, {"properties": [("action", action)]}) for k in ('RET', 'NUMPAD_ENTER', 'SPACE')]
    if keymap is None:
        if mode == 'EDIT_MESH':
            pick = [("dessin.select_loop", {"type": 'LEFTMOUSE', "value": 'DOUBLE_CLICK', "any": True}, None),
                    ("dessin.selection_boite", {"type": 'LEFTMOUSE', "value": 'PRESS', "any": True}, None)]
        else:
            pick = [("dessin.pick_object", {"type": 'LEFTMOUSE', "value": 'PRESS'}, None)]
        keymap = tuple(pick + run + [
            ("dessin.rclick_run", {"type": 'RIGHTMOUSE', "value": 'PRESS'}, {"properties": [("cmd", "subd"), ("action", action)]}),
            ("dessin.tool_exit", {"type": 'ESC', "value": 'PRESS'}, None)])
    cls.bl_keymap = keymap
    cls.bl_context_mode = mode
    cls.dessin_icon = kind
    cls._in_group = group
    return cls


_SUBD_SEL_HINT = "Select edges / faces / points (double-click: loop)  ·  Enter / Space / right click: "
DESSIN_TT_subdc_to_subd = _subd_cmd_tool(
    "DESSIN_TT_subdc_to_subd", 'TO_SUBD', "To SubD", "Turns the selected meshes into SubD, like ToSubD: click the objects (or select them first), then Enter",
    "Click the meshes (or select them first)  ·  Enter / Space: To SubD", 'OBJECT', "subdc_to_subd")
DESSIN_TT_subdc_to_mesh = _subd_cmd_tool(
    "DESSIN_TT_subdc_to_mesh", 'TO_MESH', "SubD to Mesh", "Applies the subdivision of the selected SubD (the smooth surface becomes the mesh): click the objects, then Enter",
    "Click the SubD objects  ·  Enter / Space: apply", 'OBJECT', "subdc_to_mesh", group=True)
DESSIN_TT_subdc_multipipe = _subd_cmd_tool(
    "DESSIN_TT_subdc_multipipe", 'MULTIPIPE', "MultiPipe", "SubD pipes along curves, joined at the nodes, like MultiPipe: click the curves, then Enter",
    "Click the curves  ·  Enter / Space: MultiPipe  ·  radius: SubD panel", 'OBJECT', "subdc_multipipe", group=True)
_SUBD_OBJ_EXTRA = []
_SUBD_EDIT_EXTRA = []
for _mode in ('OBJECT', 'EDIT_MESH'):
    _suf = "" if _mode == 'OBJECT' else "_edit"
    _hint = "Click the SubD objects" if _mode == 'OBJECT' else "Select the parts of the SubD"
    _t = [_subd_cmd_tool(f"DESSIN_TT_subdc_display{_suf}", 'DISPLAY', "Toggle SubD Display",
                         "Smooth / box (control cage) display of the SubD, like ToggleSubDDisplay: Enter to toggle",
                         _hint + "  ·  Enter / Space: smooth / box display", _mode, "subdc_display", group=(_mode == 'OBJECT'))]
    for _ax, _g in (("X", False), ("Y", True), ("Z", True)):
        _t.append(_subd_cmd_tool(f"DESSIN_TT_subdc_sym_{_ax.lower()}{_suf}", f'REFLECT_{_ax}', f"Symmetry {_ax}",
                                 f"Live symmetry across the {_ax} axis of the object (Mirror before the SubD), like Reflect: Enter to toggle",
                                 _hint + f"  ·  Enter / Space: symmetry {_ax} on / off", _mode, f"subdc_sym_{_ax.lower()}", group=_g))
    (_SUBD_OBJ_EXTRA if _mode == 'OBJECT' else _SUBD_EDIT_EXTRA).append(_t)
DESSIN_TT_subdc_insert_edge = _subd_cmd_tool(
    "DESSIN_TT_subdc_insert_edge", 'INSERT_EDGE', "Insert Edge", "Inserts an edge loop, like InsertEdge: hover an edge and click, move to slide it, click to confirm",
    "Hover an edge, click, slide, click  ·  Esc: leave", 'EDIT_MESH', "subdc_insert_edge",
    keymap=(("mesh.loopcut_slide", {"type": 'LEFTMOUSE', "value": 'PRESS'}, None),
            ("dessin.tool_exit", {"type": 'ESC', "value": 'PRESS'}, None)))
_SUBD_EDIT_LIST = [
    [_subd_cmd_tool("DESSIN_TT_subdc_crease", 'CREASE', "Crease", "Sharp crease on the selected edges, like Crease: select the edges, then Enter",
                    _SUBD_SEL_HINT + "crease", 'EDIT_MESH', "subdc_crease"),
     _subd_cmd_tool("DESSIN_TT_subdc_uncrease", 'UNCREASE', "Remove Crease", "Removes the crease from the selected edges, like RemoveCrease: select the edges, then Enter",
                    _SUBD_SEL_HINT + "remove the crease", 'EDIT_MESH', "subdc_uncrease", group=True)],
    [DESSIN_TT_subdc_insert_edge,
     _subd_cmd_tool("DESSIN_TT_subdc_slide", 'SLIDE', "Slide", "Slides the selected edges or points along the surface, like Slide: select, then Enter and move the mouse",
                    _SUBD_SEL_HINT + "slide", 'EDIT_MESH', "subdc_slide", group=True),
     _subd_cmd_tool("DESSIN_TT_subdc_bevel", 'BEVEL', "Bevel", "Bevels the selected edges, like Bevel: select the edges, then Enter and move the mouse",
                    _SUBD_SEL_HINT + "bevel", 'EDIT_MESH', "subdc_bevel", group=True),
     _subd_cmd_tool("DESSIN_TT_subdc_inset", 'INSET', "Inset", "Insets the selected faces (smaller face + ring of faces): select the faces, then Enter and move the mouse",
                    _SUBD_SEL_HINT + "inset", 'EDIT_MESH', "subdc_inset", group=True)],
    [_subd_cmd_tool("DESSIN_TT_subdc_bridge", 'BRIDGE', "Bridge", "Bridges two edge chains with faces, like Bridge: select both chains, then Enter",
                    _SUBD_SEL_HINT + "bridge", 'EDIT_MESH', "subdc_bridge"),
     _subd_cmd_tool("DESSIN_TT_subdc_fill", 'FILL', "Fill", "Fills the selected hole with quads, like Fill: select the border, then Enter",
                    _SUBD_SEL_HINT + "fill", 'EDIT_MESH', "subdc_fill", group=True),
     _subd_cmd_tool("DESSIN_TT_subdc_append", 'APPEND', "Append Face", "Creates a face from the selected points or edges, like Append: select, then Enter",
                    _SUBD_SEL_HINT + "create the face", 'EDIT_MESH', "subdc_append", group=True)],
    [_subd_cmd_tool("DESSIN_TT_subdc_merge_faces", 'MERGE_FACES', "Merge Faces", "Merges the selected faces into one, like MergeFaces: select the faces, then Enter",
                    _SUBD_SEL_HINT + "merge", 'EDIT_MESH', "subdc_merge_faces"),
     _subd_cmd_tool("DESSIN_TT_subdc_extract", 'EXTRACT', "Extract Faces", "Extracts the selected faces into a separate object, like ExtractSubObject: select the faces, then Enter",
                    _SUBD_SEL_HINT + "extract", 'EDIT_MESH', "subdc_extract", group=True),
     _subd_cmd_tool("DESSIN_TT_subdc_weld", 'WELD', "Weld", "Welds the points that are at the same place, like Weld: select, then Enter",
                    _SUBD_SEL_HINT + "weld", 'EDIT_MESH', "subdc_weld", group=True),
     _subd_cmd_tool("DESSIN_TT_subdc_stitch", 'STITCH', "Stitch", "Stitches the selected points / edges onto the last selected, like Stitch: select, then Enter",
                    _SUBD_SEL_HINT + "stitch", 'EDIT_MESH', "subdc_stitch", group=True)],
    [_subd_cmd_tool("DESSIN_TT_subdc_sel_loop", 'SEL_LOOP', "Select Loop", "Selects the loops of the selected edges, like SelLoop: select an edge, then Enter",
                    _SUBD_SEL_HINT + "select the loop", 'EDIT_MESH', "subdc_sel_loop"),
     _subd_cmd_tool("DESSIN_TT_subdc_sel_ring", 'SEL_RING', "Select Ring", "Selects the rings of the selected edges, like SelRing: select an edge, then Enter",
                    _SUBD_SEL_HINT + "select the ring", 'EDIT_MESH', "subdc_sel_ring", group=True)],
] + _SUBD_EDIT_EXTRA
_SUBD_OBJ_LIST = [[DESSIN_TT_subdc_to_subd, DESSIN_TT_subdc_to_mesh, DESSIN_TT_subdc_multipipe]] + _SUBD_OBJ_EXTRA


DESSIN_TT_text = _draw_tool_cls(
    "DESSIN_TT_text", "dessin.text_tool", "dessin.text", "Text",
    "Single-line text like TEXT: insertion point, type the text, Enter: next line, Enter on an empty line: finish",
    "Insertion point  ·  type the text  ·  Enter: next line  ·  Enter on an empty line: finish")
DESSIN_TT_text.draw_settings = _cotation_settings
DESSIN_TT_dist = _draw_tool_cls(
    "DESSIN_TT_dist", "dessin.dist_tool", "dessin.dist", "Distance",
    "Like DIST: distance, X / Y / Z deltas and angles between two points. Nothing is created",
    "First point, second point  ·  result in the command bar, distance copied to the clipboard")
DESSIN_TT_center_mark = _draw_tool_cls(
    "DESSIN_TT_center_mark", "dessin.center_mark_tool", "dessin.center_mark", "Center Mark",
    "Like DimCenterMark: click a circle, an arc or an ellipse to put a center mark on it (D: cross / center lines)",
    "Click a circle, an arc or an ellipse  ·  D: cross / center lines")
DESSIN_TT_center_mark.draw_settings = _cotation_settings
DESSIN_TT_cotation_chain = _draw_tool_cls(
    "DESSIN_TT_cotation_chain", "dessin.cotation_chain_tool", "dessin.cotation_chain", "Continue Dimension",
    "Chained dimensions like DimContinue / DimBaseline: click a linear dimension, then the next points (D: continue / baseline)",
    "Click a linear dimension, then the next points  ·  D: continue / baseline  ·  Enter: finish")
DESSIN_TT_cotation_chain.draw_settings = _cotation_settings
DESSIN_TT_cotation_ordinate = _draw_tool_cls(
    "DESSIN_TT_cotation_ordinate", "dessin.cotation_ordinate_tool", "dessin.cotation_ordinate", "Ordinate Dimension",
    "Like DimOrdinate: base point, then for each feature the point and the end of the leader (D: auto / X / Y)",
    "Base point, then feature point and leader end  ·  D: auto / X / Y  ·  stays on the same base point")
DESSIN_TT_cotation_ordinate.draw_settings = _cotation_settings
DESSIN_TT_cotation_arc = _draw_tool_cls(
    "DESSIN_TT_cotation_arc", "dessin.cotation_arc_tool", "dessin.cotation_arc", "Arc Length Dimension",
    "Arc length dimension: click an arc, then the position of the dimension arc",
    "Click an arc, then the position of the dimension arc")
DESSIN_TT_cotation_arc.draw_settings = _cotation_settings
DESSIN_TT_cotation_edit = _draw_tool_cls(
    "DESSIN_TT_cotation_edit", "dessin.cotation_edit_tool", "dessin.cotation_edit", "Move Dimension Line",
    "Moves the dimension line of a dimension already placed: click the dimension, then its new position",
    "Click a dimension, then its new position")
DESSIN_TT_cotation_edit.draw_settings = _cotation_settings
for _t in (DESSIN_TT_cotation_chain, DESSIN_TT_cotation_ordinate, DESSIN_TT_cotation_arc):
    _t._in_group = True       # menu déroulant de Dimension

DESSIN_TT_id_point = _draw_tool_cls(
    "DESSIN_TT_id_point", "dessin.id_point_tool", "dessin.id_point", "ID Point",
    "Like ID: click a point to read its X, Y, Z coordinates. Nothing is created",
    "Click a point (snaps work)  ·  coordinates in the command bar and copied to the clipboard")
DESSIN_TT_mesure_aire = _draw_tool_cls(
    "DESSIN_TT_mesure_aire", "dessin.mesure_aire_tool", "dessin.mesure_aire", "Area / Perimeter",
    "Quick measure: click the corners of a contour (Enter or first point to close), D: measure the selection. Nothing is created",
    "Click the corners, Enter to close  ·  D: measure the selection  ·  result copied to the clipboard")

DESSIN_TT_echelle_2d = _draw_tool_cls(
    "DESSIN_TT_echelle_2d", "dessin.echelle_2d_tool", "dessin.echelle_2d", "Scale 2D",
    "Scales the selection in the construction plane only (like Scale2D): base point, two reference points or typed factor",
    "Select the objects first  ·  base point, reference points or factor + Enter  ·  C: copy  ·  R: reference / free reference")
DESSIN_TT_echelle_2d._in_group = True
DESSIN_TT_echelle_1d = _draw_tool_cls(
    "DESSIN_TT_echelle_1d", "dessin.echelle_1d_tool", "dessin.echelle_1d", "Scale 1D",
    "Scales the selection in one direction only, the one from the base point to the reference point (like Scale1D)",
    "Select the objects first  ·  base point, reference points or factor + Enter  ·  C: copy  ·  R: reference / free reference")
DESSIN_TT_echelle_1d._in_group = True
DESSIN_TT_echelle_taille = _draw_tool_cls(
    "DESSIN_TT_echelle_taille", "dessin.echelle_taille_tool", "dessin.echelle_taille", "Scale to Size",
    "Scales the selection to exact overall dimensions (bounding box): click, then type the final X, Y, Z size",
    "Select the objects first  ·  click in the viewport  ·  type the final size  ·  Keep proportions: one value drives the others",
    hover=False)
DESSIN_TT_echelle_taille._in_group = True
DESSIN_TT_curve_cp = _draw_tool_cls(
    "DESSIN_TT_curve_cp", "dessin.curve_cp_tool", "dessin.curve_cp", "Control Point Curve",
    "Curve from its control points, with snapping (D: degree, click the first point to close, Enter to finish)",
    "Click the control points  ·  D: degree 3 / 2 / 5  ·  click the first point: close  ·  Enter: finish  ·  Backspace: undo last point")


DESSIN_TT_curve_interp = _draw_tool_cls(
    "DESSIN_TT_curve_interp", "dessin.curve_interp_tool", "dessin.curve_interp", "Interpolate Curve",
    "Smooth curve that passes through every point you click, with snapping",
    "Click the points the curve must pass through  ·  click the first point: close  ·  Enter: finish  ·  Backspace: undo last point")
DESSIN_TT_sketch = _draw_tool_cls(
    "DESSIN_TT_sketch", "dessin.sketch_tool", "dessin.sketch", "Sketch",
    "Freehand drawing: press, drag and release, the stroke becomes a smooth curve",
    "Press and drag: draw  ·  release: end the stroke (dragging back onto the start closes it)  ·  Esc: leave")
DESSIN_TT_srf_corners = _draw_tool_cls(
    "DESSIN_TT_srf_corners", "dessin.srf_corners_tool", "dessin.srf_corners", "Surface from Corner Points",
    "Surface from 3 or 4 corner points, with snapping (the 4th click finishes, Enter after the 3rd: triangle)",
    "Click the 3 or 4 corners  ·  4th click: finish  ·  Enter after the 3rd corner: triangle  ·  Backspace: undo last point")
DESSIN_TT_pen = _draw_tool_cls(
    "DESSIN_TT_pen", "dessin.pen_tool", "dessin.pen", "Pen (Bezier)",
    "Bezier curve with anchor points and handles: click = corner point, click and drag = smooth point (Alt while dragging: break the handle)",
    "Click: corner point  ·  click and drag: smooth point  ·  Alt: break the handle  ·  click the first point: close  ·  Enter: finish  ·  Backspace: undo last point")
DESSIN_TT_point = _draw_tool_cls(
    "DESSIN_TT_point", "dessin.point_tool", "dessin.point", "Point",
    "Places points (empties) with snapping",
    "Click to place a point  ·  Enter / Esc: finish")


DESSIN_TT_trim = _draw_tool_cls(
    "DESSIN_TT_trim", "dessin.trim_tool", "dessin.trim", "Trim",
    "Trims curves, outlines and surfaces: the selected objects are the cutting curves (nothing selected: all of them), click the part to remove or drag a fence line across several (F: fence, C: crossing box; surfaces: the outline is projected along the view)",
    "Select the cutting curves first (none: all)  ·  click a part to remove it, or drag a fence line (F) / a crossing box (C) to remove several  ·  Esc / Enter: leave",
    hover=False)
DESSIN_TT_trim.bl_keymap += (("dessin.tool_exit", {"type": 'RET', "value": 'PRESS'}, None),
                             ("dessin.trim_mode", {"type": 'F', "value": 'PRESS'}, {"properties": [("mode", 'FENCE')]}),
                             ("dessin.trim_mode", {"type": 'C', "value": 'PRESS'}, {"properties": [("mode", 'CROSSING')]}))


def _trim_tool_settings(context, layout, tool):
    layout.prop(context.scene.dessin, "trim_mode", expand=True)
    layout.label(text="F: fence line  ·  C: crossing box  ·  click a part to trim it")


DESSIN_TT_trim.draw_settings = _trim_tool_settings
def _pick_then_run_tool(name, idname, op, label, desc, hint):
    """Outil « on désigne les objets (clics), puis Entrée / Espace » : Join, Explode."""
    cls = _draw_tool_cls(name, idname, op, label, desc, hint, hover=False)
    cls.bl_keymap = (("dessin.pick_object", {"type": 'LEFTMOUSE', "value": 'PRESS'}, None),
                     (op, {"type": 'RET', "value": 'PRESS'}, None),
                     (op, {"type": 'NUMPAD_ENTER', "value": 'PRESS'}, None),
                     (op, {"type": 'SPACE', "value": 'PRESS'}, None),
                     ("dessin.rclick_run", {"type": 'RIGHTMOUSE', "value": 'PRESS'}, {"properties": [("cmd", op.split(".", 1)[1])]}),
                     ("dessin.tool_exit", {"type": 'ESC', "value": 'PRESS'}, None))
    return cls


DESSIN_TT_join = _pick_then_run_tool(
    "DESSIN_TT_join", "dessin.join_tool", "dessin.join", "Join",
    "Joins curves end to end, or surfaces / outlines into one object: click the objects (or select them first), then Enter / Space",
    "Click the objects to join (or select them first)  ·  Enter / Space: join  ·  Esc: leave")
DESSIN_TT_explode = _pick_then_run_tool(
    "DESSIN_TT_explode", "dessin.explode_tool", "dessin.explode", "Explode",
    "Explodes polylines into segments, curves into their parts, meshes into faces: click the objects (or select them first), then Enter / Space",
    "Click the objects to explode (or select them first)  ·  Enter / Space: explode  ·  Esc: leave")
DESSIN_TT_align = _pick_then_run_tool(
    "DESSIN_TT_align", "dessin.align_tool", "dessin.align", "Align",
    "Aligns objects along their bounding boxes (left / center / right, front / back, bottom / top): click the objects, then Enter",
    "Click the objects to align  ·  Enter / Space: options  ·  Esc: leave")
DESSIN_TT_make2d = _pick_then_run_tool(
    "DESSIN_TT_make2d", "dessin.make2d_tool", "dessin.make2d", "Make 2D",
    "Creates a 2D drawing (visible and hidden lines) of the selected objects from a named view or as a third / first angle projection: click the objects, then Enter",
    "Click the objects to draw in 2D  ·  Enter / Space: options  ·  Esc: leave")
DESSIN_TT_revolve = _draw_tool_cls(
    "DESSIN_TT_revolve", "dessin.revolve_tool", "dessin.revolve", "Revolve",
    "Revolves curves around an axis: select the curves, Enter, two points for the axis, then Enter for 360° or type the angle (C: cap, D: delete input)",
    "Select the curves, Enter  ·  axis start, axis end  ·  Enter: 360° or type the angle  ·  C: cap  ·  D: delete input")
DESSIN_TT_subd_loft = _pick_then_run_tool(
    "DESSIN_TT_subd_loft", "dessin.subd_loft_tool", "dessin.subd_loft", "SubD Loft",
    "SubD through curves, like SubDLoft: click the curves in order, then Enter (options: closed, through the curves, points, cap)",
    "Click the curves in order  ·  Enter / Space: SubD Loft options  ·  Esc: leave")
DESSIN_TT_subd_sweep1 = _pick_then_run_tool(
    "DESSIN_TT_subd_sweep1", "dessin.subd_sweep1_tool", "dessin.subd_sweep1", "SubD Sweep 1",
    "SubD swept along one rail, like SubDSweep1: click the rail first, then the cross-sections, then Enter",
    "Click the rail first, then the cross-sections  ·  Enter / Space: options  ·  Esc: leave")
DESSIN_TT_subd_sweep2 = _pick_then_run_tool(
    "DESSIN_TT_subd_sweep2", "dessin.subd_sweep2_tool", "dessin.subd_sweep2", "SubD Sweep 2",
    "SubD swept along two rails, like SubDSweep2: click the two rails, then the cross-sections, then Enter",
    "Click the two rails, then the cross-sections  ·  Enter / Space: options  ·  Esc: leave")
DESSIN_TT_subd_revolve = _draw_tool_cls(
    "DESSIN_TT_subd_revolve", "dessin.subd_revolve_tool", "dessin.subd_revolve", "SubD Revolve",
    "SubD revolved around an axis: select the curves, Enter, two points for the axis, then Enter for 360° or type the angle (C: cap, D: delete input)",
    "Select the curves, Enter  ·  axis start, axis end  ·  Enter: 360° or type the angle  ·  C: cap  ·  D: delete input")
for _t, _k in ((DESSIN_TT_subd_loft, "subdc_loft"), (DESSIN_TT_subd_sweep1, "subdc_sweep1"), (DESSIN_TT_subd_sweep2, "subdc_sweep2"),
               (DESSIN_TT_subd_revolve, "subdc_revolve")):
    _t.dessin_icon = _k
    _t._in_group = _t is not DESSIN_TT_subd_loft
_SUBD_OBJ_LIST.insert(0, [DESSIN_TT_subd_loft, DESSIN_TT_subd_sweep1, DESSIN_TT_subd_sweep2, DESSIN_TT_subd_revolve])
DESSIN_TT_loft = _pick_then_run_tool(
    "DESSIN_TT_loft", "dessin.loft_tool", "dessin.loft", "Loft",
    "Creates a surface through curves: click them in order, then Enter (options: closed, straight / smooth, cap)",
    "Click the curves in order  ·  Enter / Space: loft options  ·  Esc: leave")
DESSIN_TT_sweep1 = _pick_then_run_tool(
    "DESSIN_TT_sweep1", "dessin.sweep1_tool", "dessin.sweep1", "Sweep 1 Rail",
    "Sweeps cross-sections along one rail: click the rail first, then the cross-sections, then Enter",
    "Click the rail first, then the cross-sections  ·  Enter / Space: sweep options  ·  Esc: leave")
DESSIN_TT_extrude_path = _pick_then_run_tool(
    "DESSIN_TT_extrude_path", "dessin.extrude_path_tool", "dessin.extrude_path", "Extrude Along Curve",
    "Extrudes a profile along a path curve, keeping its orientation: click the path first, then the profile, then Enter",
    "Click the path first, then the profile  ·  Enter / Space: options  ·  Esc: leave")
DESSIN_TT_sweep2 = _pick_then_run_tool(
    "DESSIN_TT_sweep2", "dessin.sweep2_tool", "dessin.sweep2", "Sweep 2 Rails",
    "Sweeps cross-sections between two rails: click the two rails first, then the cross-sections, then Enter",
    "Click the two rails first, then the cross-sections  ·  Enter / Space: sweep options  ·  Esc: leave")
def _hatch_settings(context, layout, tool):
    st = context.scene.dessin
    layout.prop(st, "hatch_pattern", text="")
    layout.prop(st, "hatch_scale")
    layout.prop(st, "hatch_rotation")
    layout.prop(st, "hatch_spacing")
    layout.prop(st, "hatch_boundary")


DESSIN_TT_hatch = _pick_then_run_tool(
    "DESSIN_TT_hatch", "dessin.hatch_tool", "dessin.hatch", "Hatch",
    "Like Hatch: fills closed planar curves with a pattern (curves inside another one become holes): click the curves, then Enter / Space",
    "Click the closed curves to hatch (or select them first)  ·  Enter / Space: create  ·  Esc: leave")
DESSIN_TT_hatch.draw_settings = _hatch_settings
DESSIN_TT_hatch_region = _draw_tool_cls(
    "DESSIN_TT_hatch_region", "dessin.hatch_region_tool", "dessin.hatch_region", "Hatch Region",
    "Hatch by picking a point: click inside an area closed by curves (curves inside it become holes)",
    "Click inside a closed area  ·  D: next pattern  ·  Esc: leave")
DESSIN_TT_hatch_region.draw_settings = _hatch_settings
DESSIN_TT_hatch_region._in_group = True     # menu déroulant de Hatch

DESSIN_TT_network_srf = _pick_then_run_tool(
    "DESSIN_TT_network_srf", "dessin.network_srf_tool", "dessin.network_srf", "Network Surface",
    "Like NetworkSrf: a surface through a network of curves crossing in two directions (2 + 2 at least): click the curves, then Enter / Space",
    "Click the curves of both directions (or select them first)  ·  Enter / Space: create  ·  Esc: leave")
DESSIN_TT_fillet_srf = _draw_tool_cls(
    "DESSIN_TT_fillet_srf", "dessin.fillet_srf_tool", "dessin.fillet_srf", "Fillet Surface",
    "Like FilletSrf: click two intersecting surfaces on the side to keep; they are trimmed and joined by a constant radius fillet",
    "Click the first surface, then the second, on the sides to keep  ·  type the radius before the second click")
DESSIN_TT_chamfer_srf = _draw_tool_cls(
    "DESSIN_TT_chamfer_srf", "dessin.chamfer_srf_tool", "dessin.chamfer_srf", "Chamfer Surface",
    "Like ChamferSrf: click two intersecting surfaces on the side to keep; they are trimmed and joined by a chamfer",
    "Click the first surface, then the second, on the sides to keep  ·  type the distance before the second click")
DESSIN_TT_chamfer_srf._in_group = True       # menu déroulant de Fillet Surface
DESSIN_TT_extend_srf = _draw_tool_cls(
    "DESSIN_TT_extend_srf", "dessin.extend_srf_tool", "dessin.extend_srf", "Extend Surface",
    "Like ExtendSrf: click a free edge of a surface, then the extension length",
    "Click a free edge, then the length (mouse or typed, Enter)")
DESSIN_TT_split_iso = _draw_tool_cls(
    "DESSIN_TT_split_iso", "dessin.split_iso_tool", "dessin.split_iso", "Split at Isocurve",
    "Splits a surface made of quads along the isocurve under the cursor (D: other direction)",
    "Hover the surface: the isocurve lights up  ·  D: other direction  ·  click: split")
DESSIN_TT_rebuild_crv = _pick_then_run_tool(
    "DESSIN_TT_rebuild_crv", "dessin.rebuild_crv_tool", "dessin.rebuild_crv", "Rebuild Curve",
    "Like Rebuild: rebuilds curves as smooth NURBS with a point count and a degree: click the curves, then Enter / Space",
    "Click the curves (or select them first)  ·  Enter / Space: options  ·  Esc: leave")
DESSIN_TT_simplify_crv = _pick_then_run_tool(
    "DESSIN_TT_simplify_crv", "dessin.simplify_crv_tool", "dessin.simplify_crv", "Simplify Curve",
    "Like SimplifyCrv: removes the points not needed to keep the shape within a tolerance: click the curves, then Enter / Space",
    "Click the curves (or select them first)  ·  Enter / Space: options  ·  Esc: leave")
DESSIN_TT_change_degree = _pick_then_run_tool(
    "DESSIN_TT_change_degree", "dessin.change_degree_tool", "dessin.change_degree", "Change Degree",
    "Like ChangeDegree: sets the degree of curves (1: polyline, 2 to 5: smooth): click the curves, then Enter / Space",
    "Click the curves (or select them first)  ·  Enter / Space: options  ·  Esc: leave")
DESSIN_TT_insert_point = _draw_tool_cls(
    "DESSIN_TT_insert_point", "dessin.insert_point_tool", "dessin.insert_point", "Insert Control Point",
    "Click on a curve to add a control point there (polylines and Bézier curves keep their shape)",
    "Click on a curve where to add a point")
DESSIN_TT_remove_point = _draw_tool_cls(
    "DESSIN_TT_remove_point", "dessin.remove_point_tool", "dessin.remove_point", "Remove Control Point",
    "Click near a control point of a curve to delete it",
    "Click a control point to remove it")
DESSIN_TT_match_crv = _draw_tool_cls(
    "DESSIN_TT_match_crv", "dessin.match_crv_tool", "dessin.match_crv", "Match Curve",
    "Like MatchCrv: click near the end of the curve to change, then near the end of the curve to match (D: tangency / position)",
    "End of the curve to change, then end of the curve to match  ·  D: tangency / position")
DESSIN_TT_blend_crv = _draw_tool_cls(
    "DESSIN_TT_blend_crv", "dessin.blend_crv_tool", "dessin.blend_crv", "Blend Curve",
    "Like BlendCrv: click near the end of a curve, then near the end of another: a smooth curve joins them",
    "End of the first curve, then end of the second curve")
for _t in (DESSIN_TT_simplify_crv, DESSIN_TT_change_degree, DESSIN_TT_remove_point):
    _t._in_group = True       # Rebuild / Simplify / Change Degree, et Insert / Remove Point : menus déroulants
DESSIN_TT_block = _draw_tool_cls(
    "DESSIN_TT_block", "dessin.block_tool", "dessin.block", "Block",
    "Like Block: select objects, then click the base point; they become a block whose copies all update together",
    "Select the objects first, then click the base point")
DESSIN_TT_block_insert = _draw_tool_cls(
    "DESSIN_TT_block_insert", "dessin.block_insert_tool", "dessin.block_insert", "Insert Block",
    "Like Insert: click the insertion points of the chosen block (D: next block)",
    "Click the insertion points  ·  D: next block  ·  Esc: leave")
DESSIN_TT_block_insert._in_group = True       # menu déroulant de Block


def _block_settings(context, layout, tool):
    st = context.scene.dessin
    layout.prop(st, "block_insert", text="")
    layout.prop(st, "block_scale")
    layout.prop(st, "block_rotation")


DESSIN_TT_block_insert.draw_settings = _block_settings
DESSIN_TT_untrim = _draw_tool_cls(
    "DESSIN_TT_untrim", "dessin.untrim_tool", "dessin.untrim", "Untrim",
    "Like Untrim: click an edge of a trimmed surface; a hole disappears, the outer edge gives back the shape before trimming (D: all edges)",
    "Click the trimmed edge  ·  D: this edge / all edges")
DESSIN_TT_untrim_holes = _draw_tool_cls(
    "DESSIN_TT_untrim_holes", "dessin.untrim_holes_tool", "dessin.untrim_holes", "Untrim Holes",
    "Like UntrimHoles: click the edge of a hole in a surface to fill it (D: all the holes of the surface)",
    "Click the edge of a hole  ·  D: this hole / all holes")
DESSIN_TT_untrim_holes._in_group = True       # menu déroulant de Untrim
DESSIN_TT_planar_srf = _pick_then_run_tool(
    "DESSIN_TT_planar_srf", "dessin.planar_srf_tool", "dessin.planar_srf", "Planar Surface",
    "Creates planar surfaces from closed planar curves (curves inside another one become holes): click the curves, then Enter / Space",
    "Click the closed planar curves (or select them first)  ·  Enter / Space: create  ·  Esc: leave")
DESSIN_TT_edge_srf = _pick_then_run_tool(
    "DESSIN_TT_edge_srf", "dessin.edge_srf_tool", "dessin.edge_srf", "Edge Surface",
    "Creates a surface from 2, 3 or 4 curves touching end to end: click the curves, then Enter / Space",
    "Click 2, 3 or 4 curves  ·  Enter / Space: create  ·  Esc: leave")
DESSIN_TT_thicken = _pick_then_run_tool(
    "DESSIN_TT_thicken", "dessin.thicken_tool", "dessin.thicken", "Thicken",
    "Gives a thickness to surfaces, making solids: click the surfaces, Enter / Space, then the thickness and direction",
    "Click the surfaces to thicken (or select them first)  ·  Enter / Space: options  ·  Esc: leave")
DESSIN_TT_split_face = _pick_then_run_tool(
    "DESSIN_TT_split_face", "dessin.split_face_tool", "dessin.split_face", "Split Face",
    "Splits a surface along curves or polylines drawn on it, as seen from the current view: click the surface and the curves, then Enter / Space",
    "Click the surface, then the curves on it (view them from above the face)  ·  Enter / Space: split  ·  Esc: leave")
DESSIN_TT_project_curve = _pick_then_run_tool(
    "DESSIN_TT_project_curve", "dessin.project_curve_tool", "dessin.project_curve", "Project Curve",
    "Projects curves onto surfaces: click the curves, then the surface(s), then Enter / Space",
    "Click the curves, then the surface(s) to project onto  ·  Enter / Space: project  ·  Esc: leave")
DESSIN_TT_divide = _pick_then_run_tool(
    "DESSIN_TT_divide", "dessin.divide_tool", "dessin.divide", "Divide",
    "Places points at regular intervals along curves or outlines: click the curves (or select them first), then Enter / Space",
    "Click the curves to divide (or select them first)  ·  Enter / Space: live preview, wheel or typed number of segments  ·  Esc: leave")
DESSIN_TT_overkill = _pick_then_run_tool(
    "DESSIN_TT_overkill", "dessin.overkill_tool", "dessin.overkill", "Overkill",
    "Cleans curves, outlines and meshes: merges duplicate points, removes duplicate edges, points on a straight line and identical objects: click the objects, then Enter / Space",
    "Click the objects to clean (or select them first)  ·  Enter / Space: tolerance and options  ·  Esc: leave")
DESSIN_TT_fillet_c = _pick_then_run_tool(
    "DESSIN_TT_fillet_c", "dessin.fillet_curve_tool", "dessin.fillet_curve", "Fillet Curve",
    "Rounds the corners of polylines with an arc, or joins two lines with a rounded corner: click the curves (or select them first), then Enter / Space",
    "Click the polylines (or two lines)  ·  Enter / Space: live preview, wheel or typed radius  ·  Enter / click: validate  ·  Esc: leave")
DESSIN_TT_chamfer_c = _pick_then_run_tool(
    "DESSIN_TT_chamfer_c", "dessin.chamfer_curve_tool", "dessin.chamfer_curve", "Chamfer Curve",
    "Cuts the corners of polylines at a distance, or joins two lines with a chamfered corner: click the curves (or select them first), then Enter / Space",
    "Click the polylines (or two lines)  ·  Enter / Space: live preview, wheel or typed distance  ·  Enter / click: validate  ·  Esc: leave")
DESSIN_TT_clip_plane = _draw_tool_cls(
    "DESSIN_TT_clip_plane", "dessin.clip_plane_tool", "dessin.clip_plane", "Clipping Plane",
    "Draws a clipping plane: the view hides what is on the side of the arrow (move it with the gumball, flip / switch off in the Wanderer panel)",
    "First corner then opposite corner (in the active view plane)  ·  the arrow points to the hidden side  ·  C: from center")
DESSIN_TT_stretch = _draw_tool_cls(
    "DESSIN_TT_stretch", "dessin.stretch_tool", "dessin.stretch", "Stretch",
    "Stretches the points inside a crossing window: window corners, base point, destination (Shift: orthogonal, or type the distance)",
    "Two corners of the crossing window  ·  base point, destination  ·  Shift: orthogonal  ·  type the distance + Enter")
DESSIN_TT_xline = _draw_tool_cls(
    "DESSIN_TT_xline", "dessin.xline_tool", "dessin.xline", "Construction Line",
    "Very long construction line: a point it goes through, then a second point for the direction (Shift: orthogonal, or type the angle)",
    "Point, then direction  ·  Shift: orthogonal  ·  type the angle in degrees + Enter")
DESSIN_TT_patch = _pick_then_run_tool(
    "DESSIN_TT_patch", "dessin.patch_tool", "dessin.patch", "Patch",
    "Fills a closed outline with a smooth surface: click closed curves (or a surface with a hole), then Enter / Space",
    "Click the closed curves (or a surface with a hole)  ·  Enter / Space: patch  ·  Esc: leave")
DESSIN_TT_cap = _pick_then_run_tool(
    "DESSIN_TT_cap", "dessin.cap_tool", "dessin.cap", "Cap",
    "Closes the open ends of surfaces to make solids: click the objects (or select them first), Enter / Space",
    "Click the open surfaces to cap (or select them first)  ·  Enter / Space: cap  ·  Esc: leave")
DESSIN_TT_blend_srf = _pick_then_run_tool(
    "DESSIN_TT_blend_srf", "dessin.blend_srf_tool", "dessin.blend_srf", "Blend Surface",
    "Creates a smooth surface between the facing edges of two surfaces or curves: click the two objects, then Enter / Space",
    "Click the two surfaces (or curves)  ·  Enter / Space: blend options  ·  Esc: leave")
DESSIN_TT_blend_srf.bl_description = ("Creates a smooth surface between two edges: click the first edge (C: chain the connected edges), Enter, "
                                      "click the second edge, Enter - then adjust the continuity and tension in the panel")
DESSIN_TT_blend_srf.dessin_hint = "Click the first edge  ·  C: chain edges  ·  Enter  ·  second edge  ·  Enter  ·  Esc: leave"
DESSIN_TT_blend_srf.bl_keymap = (("dessin.blend_srf", {"type": 'LEFTMOUSE', "value": 'PRESS'}, None),
                                 ("dessin.blend_srf", {"type": 'MOUSEMOVE', "value": 'ANY'}, None),
                                 ("dessin.tool_exit", {"type": 'ESC', "value": 'PRESS'}, None))
DESSIN_TT_match_srf = _pick_then_run_tool(
    "DESSIN_TT_match_srf", "dessin.match_srf_tool", "dessin.match_srf", "Match Surface",
    "Moves the edge of the first clicked surface onto the facing edge of the second: click the surface to change, then the target, then Enter / Space",
    "Click the surface to change, then the target  ·  Enter / Space: match  ·  Esc: leave")
DESSIN_TT_rail_revolve = _pick_then_run_tool(
    "DESSIN_TT_rail_revolve", "dessin.rail_revolve_tool", "dessin.rail_revolve", "Rail Revolve",
    "Revolves a profile around an axis, the rail curve controlling the radius: click the profile, then the rail (then an axis line), then Enter / Space",
    "Click the profile, then the rail (optional: axis line)  ·  Enter / Space: options  ·  Esc: leave")
DESSIN_TT_shell = _pick_then_run_tool(
    "DESSIN_TT_shell", "dessin.shell_tool", "dessin.shell", "Shell",
    "Hollows out solids, keeping a wall thickness: click the solids, Enter / Space, then the thickness and the face to remove",
    "Click the solids to hollow out (or select them first)  ·  Enter / Space: options  ·  Esc: leave")
DESSIN_TT_light_point = _draw_tool_cls(
    "DESSIN_TT_light_point", "dessin.light_point_tool", "dessin.light_point", "Point Light",
    "Places a point light: click its position, then drag to set its radius (or type the radius)",
    "Position  ·  drag or type the radius, Enter")
DESSIN_TT_light_spot = _draw_tool_cls(
    "DESSIN_TT_light_spot", "dessin.light_spot_tool", "dessin.light_spot", "Spot Light",
    "Places a spot light: position, target point, then the radius of the cone at the target",
    "Position  ·  target  ·  radius of the cone (drag or type), Enter")
DESSIN_TT_light_spot._in_group = True
DESSIN_TT_light_sun = _draw_tool_cls(
    "DESSIN_TT_light_sun", "dessin.light_sun_tool", "dessin.light_sun", "Sun Light",
    "Places a sun light: its position, then the point it aims at",
    "Position  ·  target point (direction of the light)")
DESSIN_TT_light_sun._in_group = True
DESSIN_TT_light_area = _draw_tool_cls(
    "DESSIN_TT_light_area", "dessin.light_area_tool", "dessin.light_area", "Area Light",
    "Places a rectangular area light like a rectangle: two corners (C: from center, F: flip direction, type width / Tab / height)",
    "Two corners  ·  Shift: square  ·  C: from center  ·  F: flip the direction  ·  width, Tab, height + Enter")
DESSIN_TT_light_area._in_group = True
DESSIN_TT_camera = _draw_tool_cls(
    "DESSIN_TT_camera", "dessin.camera_tool", "dessin.camera_add", "Camera",
    "Places a camera (50 mm, like Blender's own): a first click for its position, a second click to aim it in steps of 90° (Shift: free aim)",
    "First click: the camera  ·  second click: direction (steps of 90°)  ·  Shift: free aim")
DESSIN_TT_camera_target = _draw_tool_cls(
    "DESSIN_TT_camera_target", "dessin.camera_target_tool", "dessin.camera_target", "Camera with Target",
    "Places a camera (50 mm) with a first click and an Empty with a second click (Track To): move the Empty to re-aim the camera",
    "First click: the camera  ·  second click: the target Empty")
DESSIN_TT_camera_target._in_group = True
DESSIN_TT_offset_surface = _draw_tool_cls(
    "DESSIN_TT_offset_surface", "dessin.offset_surface_tool", "dessin.offset_surface", "Offset Surface",
    "Offsets a surface or an object along its normals: select it (or click it), click an arrow to flip the direction, type the distance, Enter / Space to validate",
    "Select or click a surface  ·  arrows: click to flip  ·  type the distance  ·  S: solid  ·  X: delete input  ·  Enter / Space: validate",
    hover=False)


def _offset_surface_settings(context, layout, tool):
    st = context.scene.dessin
    layout.prop(st, "offset_surf_dist")
    layout.prop(st, "offset_surf_solid")
    layout.prop(st, "offset_surf_both")
    layout.prop(st, "offset_surf_delete")
    layout.label(text="Arrow: click to flip  ·  Enter / Space: validate")


DESSIN_TT_offset_surface.draw_settings = _offset_surface_settings

DESSIN_TT_extrude = _draw_tool_cls(
    "DESSIN_TT_extrude", "dessin.extrude_tool", "dessin.extrude", "Extrude",
    "Extrudes the selected faces or edges along their normal: click, move the mouse or type the distance, click / Enter / Space to validate",
    "Select faces / edges first  ·  click  ·  mouse or typed distance  ·  click / Enter / Space: validate",
    hover=False)
DESSIN_TT_extrude.bl_context_mode = 'EDIT_MESH'
DESSIN_TT_extrude_crv = _draw_tool_cls(
    "DESSIN_TT_extrude_crv", "dessin.extrude_crv_tool", "dessin.extrude_crv", "Extrude Curve",
    "Like ExtrudeCrv: extrudes curves, outlines or flat surfaces into a volume: select them, Enter, base point, then the height (mouse or typed value, Enter)",
    "Select the curves first, Enter  ·  base point  ·  height  ·  C: cap  ·  D: delete input  ·  B: both sides  ·  T: tapered (Tab: angle)  ·  P: to point")
DESSIN_TT_extrude_srf = _draw_tool_cls(
    "DESSIN_TT_extrude_srf", "dessin.extrude_srf_tool", "dessin.extrude_srf", "Extrude Surface",
    "Extrudes surfaces into a solid along their normal: select them, Enter, base point, then the height (mouse or typed value, Enter)",
    "Select the surfaces first, Enter  ·  base point  ·  height (mouse or typed)  ·  C: cap the ends  ·  D: delete the input")

# ---- commandes Rhino de la 2.96.124 : un bouton par commande ----
DESSIN_TT_pipe = _pick_then_run_tool(
    "DESSIN_TT_pipe", "dessin.pipe_tool", "dessin.pipe", "Pipe",
    "Like Pipe: a round tube along curves. Click the curves (or select them first), then Enter: radius, sides, caps",
    "Click the curves  ·  Enter / Space: radius and options  ·  Esc: leave")
DESSIN_TT_intersect = _pick_then_run_tool(
    "DESSIN_TT_intersect", "dessin.intersect_tool", "dessin.intersect", "Intersect",
    "Like Intersect: creates the curves where surfaces / solids meet, and points where curves cross. Click the objects, then Enter",
    "Click two objects or more  ·  Enter / Space: intersection curves  ·  Esc: leave")
DESSIN_TT_section = _draw_tool_cls(
    "DESSIN_TT_section", "dessin.section_tool", "dessin.section", "Section",
    "Like Section: cuts the selected objects with a plane given by two points (perpendicular to the construction plane) and creates the section curves",
    "Select the objects first  ·  start of the section line, then its end  ·  Shift: orthogonal")
DESSIN_TT_contour = _draw_tool_cls(
    "DESSIN_TT_contour", "dessin.contour_tool", "dessin.contour", "Contour",
    "Like Contour: evenly spaced section curves through the selected objects: base point, direction, then the spacing (mouse or typed)",
    "Select the objects first  ·  base point  ·  direction  ·  spacing (mouse or typed, Enter)")
DESSIN_TT_contour._in_group = True          # menu déroulant de Section
DESSIN_TT_extract_srf = _draw_tool_cls(
    "DESSIN_TT_extract_srf", "dessin.extract_srf_tool", "dessin.extract_srf", "Extract Surface",
    "Like ExtractSrf: click the faces of a solid to detach them as separate surfaces (C: copy, the solid stays whole)",
    "Click: start  ·  hover a face, click to extract it  ·  C: copy  ·  Enter / Esc: done", hover=False)
DESSIN_TT_dup_border = _pick_then_run_tool(
    "DESSIN_TT_dup_border", "dessin.dup_border_tool", "dessin.dup_border", "Duplicate Border",
    "Like DupBorder: creates curves on the free edges of the selected surfaces. Click the surfaces, then Enter",
    "Click the surfaces  ·  Enter / Space: border curves  ·  Esc: leave")
DESSIN_TT_dup_edge = _draw_tool_cls(
    "DESSIN_TT_dup_edge", "dessin.dup_edge_tool", "dessin.dup_edge", "Duplicate Edge",
    "Like DupEdge: click the edges of a surface or solid to copy them as curves",
    "Click: start  ·  hover an edge, click to copy it as a curve  ·  Enter / Esc: done", hover=False)
DESSIN_TT_dup_edge._in_group = True         # menu déroulant de Duplicate Border
DESSIN_TT_merge_faces = _pick_then_run_tool(
    "DESSIN_TT_merge_faces", "dessin.merge_faces_tool", "dessin.merge_faces", "Merge All Faces",
    "Like MergeAllFaces: merges the coplanar faces of the selected objects into single faces. Click the objects, then Enter",
    "Click the objects  ·  Enter / Space: merge coplanar faces  ·  Esc: leave")
DESSIN_TT_unroll = _pick_then_run_tool(
    "DESSIN_TT_unroll", "dessin.unroll_tool", "dessin.unroll", "Unroll Surface",
    "Like UnrollSrf: flattens a developable surface (cylinder, cone, folded plates) onto the construction plane, true lengths. Click the surface, then Enter",
    "Click the surfaces  ·  Enter / Space: unroll  ·  Esc: leave")
DESSIN_TT_rebuild_srf = _pick_then_run_tool(
    "DESSIN_TT_rebuild_srf", "dessin.rebuild_srf_tool", "dessin.rebuild_srf", "Rebuild Surface",
    "Like Rebuild: rebuilds a surface made of a grid of quads with the number of points you choose in U and V. Click the surface, then Enter",
    "Click the surface  ·  Enter / Space: point counts U and V  ·  Esc: leave")
DESSIN_TT_orient = _draw_tool_cls(
    "DESSIN_TT_orient", "dessin.orient_tool", "dessin.orient", "Orient",
    "Like Orient (2 points): moves and rotates the selection so that two reference points land on two target points (D: also scale, C: copy)",
    "Select the objects  ·  2 reference points, then 2 target points  ·  D: scale to the target length  ·  C: copy")
for _t, _k in ((DESSIN_TT_pipe, "pipe"), (DESSIN_TT_intersect, "intersect"), (DESSIN_TT_section, "section"), (DESSIN_TT_contour, "contour"),
               (DESSIN_TT_extract_srf, "extract_srf"), (DESSIN_TT_dup_border, "dup_border"), (DESSIN_TT_dup_edge, "dup_edge"),
               (DESSIN_TT_merge_faces, "merge_faces"), (DESSIN_TT_unroll, "unroll"), (DESSIN_TT_rebuild_srf, "rebuild_srf"),
               (DESSIN_TT_orient, "orient")):
    _t.dessin_icon = _k
# famille de la barre d'outils -> boutons ajoutés à la fin de cette famille
RHINO_TOOLS = {
    "curves": [DESSIN_TT_intersect, DESSIN_TT_section, DESSIN_TT_contour, DESSIN_TT_dup_border, DESSIN_TT_dup_edge],
    "transform": [DESSIN_TT_orient],
    "modify": [DESSIN_TT_merge_faces],
    "srf_edit": [DESSIN_TT_extract_srf, DESSIN_TT_unroll, DESSIN_TT_rebuild_srf],
    "solids": [DESSIN_TT_pipe],
}

# ---- mise en page (2.96.125) : Layout = nouvelle feuille, Detail = vue du modèle à l'échelle sur la feuille ----
DESSIN_TT_layout = _draw_tool_cls(
    "DESSIN_TT_layout", "dessin.layout_tool", "dessin.layout_new", "Layout",
    "Layout: a paper sheet with detail views of the model at scale, a title block, dimensions and notes, and vector PDF / SVG / DXF export. "
    "Click in the view to choose the paper",
    "Click in the view: name, paper size, details  ·  layouts are the tabs under the view  ·  Esc: leave", hover=False)
DESSIN_TT_layout.dessin_cmd_hidden = True      # la ligne de commande a déjà la commande « Layout » (elle ouvre la boîte tout de suite)
DESSIN_TT_layout_detail = _draw_tool_cls(
    "DESSIN_TT_layout_detail", "dessin.layout_detail_tool", "dessin.layout_detail", "Detail",
    "Layout: draws a detail view of the model on the sheet (first corner, then opposite corner). Its view, scale and layers are set in the Layout panel",
    "On a layout: first corner then opposite corner of the detail  ·  C: from center  ·  width, Tab, height + Enter")
DESSIN_TT_layout_detail._in_group = True        # menu déroulant de Layout
DESSIN_TT_layout.dessin_icon = "layout"
DESSIN_TT_layout_detail.dessin_icon = "detail"
LAYOUT_TOOLS = [DESSIN_TT_layout, DESSIN_TT_layout_detail]     # à la fin de la famille Annotation de la barre

# ordre dans la barre d'outils (un séparateur avant chaque famille)
for _t in (DESSIN_TT_curve_cp, DESSIN_TT_curve_interp, DESSIN_TT_pen, DESSIN_TT_sketch):
    _t._in_group = True   # menu déroulant des courbes (tête : Polyline)
for _t in (DESSIN_TT_srf_corners, DESSIN_TT_planar_srf, DESSIN_TT_edge_srf, DESSIN_TT_network_srf, DESSIN_TT_patch,      # tête : Plane
           DESSIN_TT_extrude_srf, DESSIN_TT_extrude_path,                                          # tête : Extrude Curve
           DESSIN_TT_rail_revolve,                                                                 # tête : Revolve
           DESSIN_TT_sweep1, DESSIN_TT_sweep2):                                                    # tête : Loft
    _t._in_group = True   # menus déroulants des surfaces
TOOL_ORDER = (
    (DESSIN_TT_deplacer, "move", True),
    (DESSIN_TT_copier, "copy", False),
    (DESSIN_TT_rotation, "rotate", False),
    (DESSIN_TT_echelle, "scale", False),
    (DESSIN_TT_echelle_2d, "scale_2d", False),
    (DESSIN_TT_echelle_1d, "scale_1d", False),
    (DESSIN_TT_echelle_taille, "scale_size", False),
    (DESSIN_TT_miroir, "mirror", False),
    (DESSIN_TT_array_linear, "array_l", False),
    (DESSIN_TT_array_rect, "array_r", False),
    (DESSIN_TT_array_polar, "array_p", False),
    (DESSIN_TT_cut, "cut", False),
    (DESSIN_TT_bool_union, "bool_u", False),
    (DESSIN_TT_bool_difference, "bool_d", False),
    (DESSIN_TT_bool_intersection, "bool_i", False),
    (DESSIN_TT_bool_split, "bool_s", False),
    (DESSIN_TT_fillet, "fillet", False),
    (DESSIN_TT_chamfer, "chamfer", False),
    (DESSIN_TT_offset, "offset", False),
    (DESSIN_TT_polyligne, "polyline", False),
    (DESSIN_TT_curve_cp, "curve_cp", False),
    (DESSIN_TT_curve_interp, "curve_i", False),
    (DESSIN_TT_pen, "pen", False),
    (DESSIN_TT_sketch, "sketch", False),
    (DESSIN_TT_xline, "xline", False),
    (DESSIN_TT_point, "point", False),
    (DESSIN_TT_rectangle, "rect", False),
    (DESSIN_TT_cercle, "circle", False),
    (DESSIN_TT_cercle_d, "circle_d", False),
    (DESSIN_TT_ellipse_c, "ellipse_c", False),
    (DESSIN_TT_ellipse_d, "ellipse_d", False),
    (DESSIN_TT_ellipse_f, "ellipse_f", False),
    (DESSIN_TT_ellipse_k, "ellipse_k", False),
    (DESSIN_TT_poly_center, "poly_c", False),
    (DESSIN_TT_poly_circ, "poly_k", False),
    (DESSIN_TT_poly_area, "poly_a", False),
    (DESSIN_TT_poly_edge, "poly_e", False),
    (DESSIN_TT_poly_star, "poly_s", False),
    (DESSIN_TT_arc_cse, "arc", False),
    (DESSIN_TT_arc_3pts, "arc3", False),
    (DESSIN_TT_plan, "plane", False),
    (DESSIN_TT_srf_corners, "srf_pts", False),
    (DESSIN_TT_boite, "box", True),
    (DESSIN_TT_cylindre, "cylinder", False),
    (DESSIN_TT_cone, "cone", False),
    (DESSIN_TT_cone_tronque, "tcone", False),
    (DESSIN_TT_pyramide, "pyramid", False),
    (DESSIN_TT_pyramide_tronquee, "tpyramid", False),
    (DESSIN_TT_tube, "tube", False),
    (DESSIN_TT_sphere, "sphere", False),
    (DESSIN_TT_ellipsoide, "ellipsoid", False),
    (DESSIN_TT_sphere_tronquee, "tsphere", False),
    (DESSIN_TT_tore, "torus", False),
    (DESSIN_TT_subd_box, "subd_box", True),
    (DESSIN_TT_subd_sphere, "subd_sphere", False),
    (DESSIN_TT_subd_cylinder, "subd_cylinder", False),
    (DESSIN_TT_subd_cone, "subd_cone", False),
    (DESSIN_TT_subd_torus, "subd_torus", False),
    (DESSIN_TT_subd_plane, "subd_plane", False),
    (DESSIN_TT_cotation, "dim", True),
    (DESSIN_TT_cotation_rayon, "dim_r", False),
    (DESSIN_TT_cotation_angle, "dim_a", False),
    (DESSIN_TT_annotation, "note", False),
    (DESSIN_TT_text, "text", False),
    (DESSIN_TT_center_mark, "center_mark", False),
    (DESSIN_TT_cotation_chain, "dim_chain", False),
    (DESSIN_TT_cotation_ordinate, "dim_ord", False),
    (DESSIN_TT_cotation_arc, "dim_arc", False),
    (DESSIN_TT_cotation_edit, "dim_edit", False),
    (DESSIN_TT_mesure_aire, "area", False),
    (DESSIN_TT_dist, "dist", False),
    (DESSIN_TT_id_point, "id_point", False),
)
_EDIT_TOOLS = []


def _late_imports():
    pass
