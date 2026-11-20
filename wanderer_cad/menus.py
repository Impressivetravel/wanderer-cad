"""Wanderer CAD : Menu Wanderer."""

import bpy

from .tools_draw import (
    DESSIN_OT_arc_3pts, DESSIN_OT_arc_cse, DESSIN_OT_cercle, DESSIN_OT_cercle_diametre, DESSIN_OT_curve_cp,
    DESSIN_OT_curve_interp, DESSIN_OT_ellipse_centre, DESSIN_OT_ellipse_coin, DESSIN_OT_ellipse_diametre,
    DESSIN_OT_ellipse_foyers, DESSIN_OT_pen, DESSIN_OT_plan, DESSIN_OT_point, DESSIN_OT_poly_area,
    DESSIN_OT_poly_center, DESSIN_OT_poly_circ, DESSIN_OT_poly_edge, DESSIN_OT_poly_star, DESSIN_OT_polyligne,
    DESSIN_OT_rectangle, DESSIN_OT_sketch, DESSIN_OT_srf_corners,
)
from .solids import (
    DESSIN_OT_boite, DESSIN_OT_cone, DESSIN_OT_cone_tronque, DESSIN_OT_cylindre, DESSIN_OT_ellipsoide,
    DESSIN_OT_pyramide, DESSIN_OT_pyramide_tronquee, DESSIN_OT_sphere, DESSIN_OT_sphere_tronquee, DESSIN_OT_tore,
    DESSIN_OT_tube,
)
from .transform import (
    DESSIN_OT_array_linear, DESSIN_OT_array_polar, DESSIN_OT_array_rect, DESSIN_OT_copier, DESSIN_OT_cut,
    DESSIN_OT_deplacer, DESSIN_OT_echelle, DESSIN_OT_echelle_1d, DESSIN_OT_echelle_2d, DESSIN_OT_echelle_taille,
    DESSIN_OT_miroir, DESSIN_OT_rotation,
)
from .edges import DESSIN_OT_chamfer_edge, DESSIN_OT_fillet_edge, DESSIN_OT_offset_edge
from .booleans import (
    DESSIN_OT_bool_difference, DESSIN_OT_bool_intersection, DESSIN_OT_bool_split, DESSIN_OT_bool_union,
)
from .selection import DESSIN_OT_selection_boite
from .dimensions import (
    DESSIN_OT_annotation, DESSIN_OT_cotation, DESSIN_OT_cotation_angle, DESSIN_OT_cotation_rayon,
    DESSIN_OT_mesure_aire,
)
from .curve_edit import (
    DESSIN_OT_chamfer_curve, DESSIN_OT_divide, DESSIN_OT_fillet_curve, DESSIN_OT_stretch, DESSIN_OT_xline,
)
from .display import DESSIN_OT_clip_plane, DESSIN_OT_overkill
from .offset_extrude import DESSIN_OT_offset_surface
from .join_explode import DESSIN_OT_explode, DESSIN_OT_join, DESSIN_OT_trim
from .surfaces import DESSIN_OT_loft, DESSIN_OT_planar_srf, DESSIN_OT_revolve, DESSIN_OT_sweep1, DESSIN_OT_sweep2
from .surface_edit import (
    DESSIN_OT_align, DESSIN_OT_blend_srf, DESSIN_OT_cap, DESSIN_OT_edge_srf, DESSIN_OT_match_srf, DESSIN_OT_patch,
    DESSIN_OT_project_curve, DESSIN_OT_rail_revolve, DESSIN_OT_shell, DESSIN_OT_split_face, DESSIN_OT_thicken,
)
from .make2d import DESSIN_OT_make2d
from .lights import (
    DESSIN_OT_camera, DESSIN_OT_camera_target, DESSIN_OT_light_area, DESSIN_OT_light_point, DESSIN_OT_light_spot,
    DESSIN_OT_light_sun,
)


# Menu Wanderer (Add > Wanderer) rangé en sous-menus : une seule longue liste dépassait la hauteur de l'écran et
# Blender la faisait défiler. (titre, icône, [opérateur ou "dessin.xxx", icône] ; None = séparateur)
_S = None
WANDERER_SUBMENUS = (
    ("Curves", 'CURVE_DATA', [
        (DESSIN_OT_polyligne, 'CURVE_PATH'), (DESSIN_OT_xline, 'CURVE_PATH'), (DESSIN_OT_curve_cp, 'CURVE_NCURVE'),
        (DESSIN_OT_curve_interp, 'CURVE_NCURVE'), (DESSIN_OT_pen, 'CURVE_BEZCURVE'), (DESSIN_OT_sketch, 'GREASEPENCIL'),
        (DESSIN_OT_point, 'DOT'), _S,
        (DESSIN_OT_rectangle, 'MESH_PLANE'), (DESSIN_OT_cercle, 'MESH_CIRCLE'), (DESSIN_OT_cercle_diametre, 'MESH_CIRCLE'),
        (DESSIN_OT_arc_cse, 'SPHERECURVE'), (DESSIN_OT_arc_3pts, 'SPHERECURVE'), _S,
        (DESSIN_OT_ellipse_centre, 'MESH_CIRCLE'), (DESSIN_OT_ellipse_diametre, 'MESH_CIRCLE'),
        (DESSIN_OT_ellipse_foyers, 'MESH_CIRCLE'), (DESSIN_OT_ellipse_coin, 'MESH_CIRCLE'), _S,
        (DESSIN_OT_poly_center, 'MESH_CIRCLE'), (DESSIN_OT_poly_circ, 'MESH_CIRCLE'), (DESSIN_OT_poly_area, 'MESH_CIRCLE'),
        (DESSIN_OT_poly_edge, 'MESH_CIRCLE'), (DESSIN_OT_poly_star, 'MESH_CIRCLE'),
    ]),
    ("Curve Tools", 'MOD_CURVE', [
        (DESSIN_OT_trim, 'AREA_JOIN'), (DESSIN_OT_join, 'AUTOMERGE_ON'), (DESSIN_OT_explode, 'MOD_EXPLODE'),
        (DESSIN_OT_fillet_curve, 'MOD_BEVEL'), (DESSIN_OT_chamfer_curve, 'MOD_BEVEL'), ("dessin.extend_crv", 'FULLSCREEN_ENTER'),
        (DESSIN_OT_stretch, 'FULLSCREEN_ENTER'), (DESSIN_OT_divide, 'SNAP_MIDPOINT'), (DESSIN_OT_overkill, 'BRUSH_DATA'), ("dessin.break_crv", 'MOD_DECIM'), ("dessin.match_props", 'BRUSH_DATA'), _S,
        (DESSIN_OT_project_curve, 'MOD_SHRINKWRAP'), ("dessin.intersect", 'SELECT_INTERSECT'), ("dessin.section", 'MOD_BOOLEAN'),
        ("dessin.contour", 'ALIGN_JUSTIFY'), (DESSIN_OT_make2d, 'MESH_PLANE'), _S,
        ("dessin.dup_border", 'MOD_OUTLINE'), ("dessin.dup_face_border", 'FACESEL'), ("dessin.dup_edge", 'EDGESEL'),
    ]),
    ("Surfaces", 'SURFACE_DATA', [
        (DESSIN_OT_plan, 'MESH_PLANE'), (DESSIN_OT_srf_corners, 'MESH_PLANE'), (DESSIN_OT_planar_srf, 'MESH_PLANE'),
        (DESSIN_OT_edge_srf, 'MESH_GRID'), (DESSIN_OT_patch, 'MESH_GRID'), _S,
        (DESSIN_OT_revolve, 'MOD_SCREW'), (DESSIN_OT_rail_revolve, 'MOD_SCREW'), (DESSIN_OT_loft, 'MOD_MULTIRES'),
        (DESSIN_OT_sweep1, 'CURVE_PATH'), (DESSIN_OT_sweep2, 'CURVE_PATH'), _S,
        (DESSIN_OT_blend_srf, 'MOD_SMOOTH'), (DESSIN_OT_match_srf, 'SNAP_EDGE'), ("dessin.rebuild_srf", 'MESH_GRID'),
        ("dessin.extract_srf", 'FACESEL'), (DESSIN_OT_split_face, 'MOD_EDGESPLIT'), ("dessin.merge_faces", 'MOD_DECIM'),
        ("dessin.unroll", 'UV'), (DESSIN_OT_offset_surface, 'MOD_OFFSET'),
    ]),
    ("Solids", 'MESH_CUBE', [
        (DESSIN_OT_boite, 'MESH_CUBE'), (DESSIN_OT_cylindre, 'MESH_CYLINDER'), (DESSIN_OT_tube, 'MESH_CYLINDER'),
        (DESSIN_OT_cone, 'MESH_CONE'), (DESSIN_OT_cone_tronque, 'MESH_CONE'), (DESSIN_OT_pyramide, 'MESH_CONE'),
        (DESSIN_OT_pyramide_tronquee, 'MESH_CONE'), (DESSIN_OT_sphere, 'MESH_UVSPHERE'), (DESSIN_OT_ellipsoide, 'MESH_UVSPHERE'),
        (DESSIN_OT_sphere_tronquee, 'MESH_UVSPHERE'), (DESSIN_OT_tore, 'MESH_TORUS'), ("dessin.pipe", 'MESH_CYLINDER'), _S,
        (DESSIN_OT_thicken, 'MOD_SOLIDIFY'), (DESSIN_OT_shell, 'MOD_SOLIDIFY'), (DESSIN_OT_cap, 'MESH_CIRCLE'),
        ("dessin.pushpull", 'FULLSCREEN_ENTER'), _S,
        (DESSIN_OT_bool_union, 'SELECT_EXTEND'), (DESSIN_OT_bool_difference, 'SELECT_SUBTRACT'),
        (DESSIN_OT_bool_intersection, 'SELECT_INTERSECT'), (DESSIN_OT_bool_split, 'SELECT_DIFFERENCE'), _S,
        (DESSIN_OT_fillet_edge, 'MOD_BEVEL'), (DESSIN_OT_chamfer_edge, 'MOD_BEVEL'), (DESSIN_OT_offset_edge, 'MOD_OFFSET'),
    ]),
    ("Transform", 'ORIENTATION_GLOBAL', [
        (DESSIN_OT_deplacer, 'ARROW_LEFTRIGHT'), (DESSIN_OT_copier, 'DUPLICATE'), (DESSIN_OT_rotation, 'FILE_REFRESH'),
        (DESSIN_OT_miroir, 'MOD_MIRROR'), _S,
        (DESSIN_OT_echelle, 'FULLSCREEN_ENTER'), (DESSIN_OT_echelle_2d, 'FULLSCREEN_ENTER'),
        (DESSIN_OT_echelle_1d, 'FULLSCREEN_ENTER'), (DESSIN_OT_echelle_taille, 'FULLSCREEN_ENTER'), _S,
        (DESSIN_OT_array_linear, 'MOD_ARRAY'), (DESSIN_OT_array_rect, 'MOD_ARRAY'), (DESSIN_OT_array_polar, 'MOD_ARRAY'), _S,
        (DESSIN_OT_align, 'ALIGN_CENTER'), ("dessin.orient", 'ORIENTATION_GIMBAL'), ("dessin.orient3pt", 'ORIENTATION_GIMBAL'),
        (DESSIN_OT_cut, 'MOD_BOOLEAN'), ("dessin.slice", 'MOD_EDGESPLIT'),
    ]),
    ("Dimensions and Hatches", 'DRIVER_DISTANCE', [
        (DESSIN_OT_cotation, 'DRIVER_DISTANCE'), (DESSIN_OT_cotation_rayon, 'MESH_CIRCLE'),
        (DESSIN_OT_cotation_angle, 'DRIVER_ROTATIONAL_DIFFERENCE'), (DESSIN_OT_annotation, 'FONT_DATA'),
        (DESSIN_OT_mesure_aire, 'SNAP_FACE'), _S,
        ("dessin.hatch", 'MOD_LATTICE'), ("dessin.hatch_region", 'MOD_LATTICE'), ("dessin.boundary", 'MESH_PLANE'), _S,
        ("dessin.block", 'OUTLINER_COLLECTION'), ("dessin.block_insert", 'OUTLINER_OB_GROUP_INSTANCE'),
    ]),
    ("Lights and Cameras", 'LIGHT', [
        (DESSIN_OT_light_point, 'LIGHT_POINT'), (DESSIN_OT_light_spot, 'LIGHT_SPOT'), (DESSIN_OT_light_sun, 'LIGHT_SUN'),
        (DESSIN_OT_light_area, 'LIGHT_AREA'), _S, (DESSIN_OT_camera, 'CAMERA_DATA'),
        (DESSIN_OT_camera_target, 'OUTLINER_OB_EMPTY'),
    ]),
    ("Layout", 'FILE', [
        ("dessin.layout_new", 'FILE'), ("dessin.layout_detail", 'SELECT_SET'), ("dessin.detail_callout", 'ZOOM_SELECTED'),
        ("dessin.layout_export_pdf", 'FILE'), _S, (DESSIN_OT_clip_plane, 'MOD_BOOLEAN'),
    ]),
)


def _op_id(it):
    return it if isinstance(it, str) else it.bl_idname


def _draw_items(layout, items):
    for it in items:
        if it is None:
            layout.separator()
            continue
        op, icon = it
        idn = _op_id(op)
        try:
            layout.operator(idn, icon=icon)
        except (RuntimeError, TypeError):          # opérateur absent (version de Blender) : ligne sautée
            pass


def _make_submenu(i, title, items):
    def draw(self, context):
        _draw_items(self.layout, items)
    return type(f"DESSIN_MT_menu_{i}", (bpy.types.Menu,),
                {"bl_idname": f"DESSIN_MT_menu_{i}", "bl_label": title, "draw": draw})


SUBMENU_CLASSES = tuple(_make_submenu(i, t, items) for i, (t, _ic, items) in enumerate(WANDERER_SUBMENUS))


class DESSIN_MT_menu(bpy.types.Menu):
    bl_idname = "DESSIN_MT_menu"
    bl_label = "Wanderer"

    def draw(self, context):
        layout = self.layout
        for cls, (_t, icon, _items) in zip(SUBMENU_CLASSES, WANDERER_SUBMENUS):
            layout.menu(cls.bl_idname, icon=icon)


def menu_add(self, context):
    """« Wanderer » tout en haut du menu Add, avec le W du logo."""
    from .hatch_patterns import logo_icon
    icon = logo_icon()
    if icon:
        self.layout.menu(DESSIN_MT_menu.bl_idname, icon_value=icon)
    else:
        self.layout.menu(DESSIN_MT_menu.bl_idname, icon='GREASEPENCIL')
    self.layout.separator()


def _late_imports():
    pass
