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


class DESSIN_MT_menu(bpy.types.Menu):
    bl_idname = "DESSIN_MT_menu"
    bl_label = "Wanderer"

    def draw(self, context):
        layout = self.layout
        layout.operator(DESSIN_OT_rectangle.bl_idname, icon='MESH_PLANE')
        layout.operator(DESSIN_OT_plan.bl_idname, icon='MESH_PLANE')
        layout.operator(DESSIN_OT_srf_corners.bl_idname, icon='MESH_PLANE')
        layout.operator(DESSIN_OT_polyligne.bl_idname, icon='CURVE_PATH')
        layout.operator(DESSIN_OT_xline.bl_idname, icon='CURVE_PATH')
        layout.operator(DESSIN_OT_curve_cp.bl_idname, icon='CURVE_NCURVE')
        layout.operator(DESSIN_OT_curve_interp.bl_idname, icon='CURVE_NCURVE')
        layout.operator(DESSIN_OT_pen.bl_idname, icon='CURVE_BEZCURVE')
        layout.operator(DESSIN_OT_sketch.bl_idname, icon='GREASEPENCIL')
        layout.operator(DESSIN_OT_point.bl_idname, icon='DOT')
        layout.operator(DESSIN_OT_stretch.bl_idname, icon='FULLSCREEN_ENTER')
        layout.operator(DESSIN_OT_divide.bl_idname, icon='SNAP_MIDPOINT')
        layout.operator(DESSIN_OT_overkill.bl_idname, icon='BRUSH_DATA')
        layout.operator(DESSIN_OT_fillet_curve.bl_idname, icon='MOD_BEVEL')
        layout.operator(DESSIN_OT_chamfer_curve.bl_idname, icon='MOD_BEVEL')
        layout.operator(DESSIN_OT_trim.bl_idname, icon='AREA_JOIN')
        layout.operator(DESSIN_OT_join.bl_idname, icon='AUTOMERGE_ON')
        layout.operator(DESSIN_OT_explode.bl_idname, icon='MOD_EXPLODE')
        layout.operator(DESSIN_OT_make2d.bl_idname, icon='MESH_PLANE')
        layout.operator("dessin.layout_new", icon='FILE')
        layout.operator("dessin.layout_detail", icon='SELECT_SET')
        layout.operator("dessin.layout_export_pdf", icon='FILE')
        layout.operator(DESSIN_OT_clip_plane.bl_idname, icon='MOD_BOOLEAN')
        layout.operator(DESSIN_OT_align.bl_idname, icon='ALIGN_CENTER')
        layout.operator(DESSIN_OT_light_point.bl_idname, icon='LIGHT_POINT')
        layout.operator(DESSIN_OT_light_spot.bl_idname, icon='LIGHT_SPOT')
        layout.operator(DESSIN_OT_light_sun.bl_idname, icon='LIGHT_SUN')
        layout.operator(DESSIN_OT_light_area.bl_idname, icon='LIGHT_AREA')
        layout.operator(DESSIN_OT_camera.bl_idname, icon='CAMERA_DATA')
        layout.operator(DESSIN_OT_camera_target.bl_idname, icon='OUTLINER_OB_EMPTY')
        layout.operator(DESSIN_OT_revolve.bl_idname, icon='MOD_SCREW')
        layout.operator(DESSIN_OT_loft.bl_idname, icon='MOD_MULTIRES')
        layout.operator(DESSIN_OT_sweep1.bl_idname, icon='CURVE_PATH')
        layout.operator(DESSIN_OT_sweep2.bl_idname, icon='CURVE_PATH')
        layout.operator(DESSIN_OT_planar_srf.bl_idname, icon='MESH_PLANE')
        layout.operator(DESSIN_OT_edge_srf.bl_idname, icon='MESH_GRID')
        layout.operator(DESSIN_OT_thicken.bl_idname, icon='MOD_SOLIDIFY')
        layout.operator(DESSIN_OT_cap.bl_idname, icon='MESH_CIRCLE')
        layout.operator(DESSIN_OT_split_face.bl_idname, icon='MOD_EDGESPLIT')
        layout.operator(DESSIN_OT_project_curve.bl_idname, icon='MOD_SHRINKWRAP')
        layout.operator(DESSIN_OT_patch.bl_idname, icon='MESH_GRID')
        layout.operator(DESSIN_OT_blend_srf.bl_idname, icon='MOD_SMOOTH')
        layout.operator(DESSIN_OT_match_srf.bl_idname, icon='SNAP_EDGE')
        layout.operator(DESSIN_OT_rail_revolve.bl_idname, icon='MOD_SCREW')
        layout.operator(DESSIN_OT_shell.bl_idname, icon='MOD_SOLIDIFY')
        layout.operator("dessin.pipe", icon='MESH_CYLINDER')
        layout.operator("dessin.intersect", icon='SELECT_INTERSECT')
        layout.operator("dessin.section", icon='MOD_BOOLEAN')
        layout.operator("dessin.contour", icon='ALIGN_JUSTIFY')
        layout.operator("dessin.extract_srf", icon='FACESEL')
        layout.operator("dessin.dup_border", icon='MOD_OUTLINE')
        layout.operator("dessin.dup_edge", icon='EDGESEL')
        layout.operator("dessin.merge_faces", icon='MOD_DECIM')
        layout.operator("dessin.unroll", icon='UV')
        layout.operator("dessin.rebuild_srf", icon='MESH_GRID')
        layout.operator("dessin.orient", icon='ORIENTATION_GIMBAL')
        layout.operator("dessin.pushpull", icon='FULLSCREEN_ENTER')
        layout.operator(DESSIN_OT_selection_boite.bl_idname, icon='RESTRICT_SELECT_OFF')
        layout.operator(DESSIN_OT_poly_center.bl_idname, icon='MESH_CIRCLE')
        layout.operator(DESSIN_OT_poly_circ.bl_idname, icon='MESH_CIRCLE')
        layout.operator(DESSIN_OT_poly_area.bl_idname, icon='MESH_CIRCLE')
        layout.operator(DESSIN_OT_poly_edge.bl_idname, icon='MESH_CIRCLE')
        layout.operator(DESSIN_OT_poly_star.bl_idname, icon='MESH_CIRCLE')
        layout.operator(DESSIN_OT_cercle.bl_idname, icon='MESH_CIRCLE')
        layout.operator(DESSIN_OT_cercle_diametre.bl_idname, icon='MESH_CIRCLE')
        layout.operator(DESSIN_OT_ellipse_centre.bl_idname, icon='MESH_CIRCLE')
        layout.operator(DESSIN_OT_ellipse_diametre.bl_idname, icon='MESH_CIRCLE')
        layout.operator(DESSIN_OT_ellipse_foyers.bl_idname, icon='MESH_CIRCLE')
        layout.operator(DESSIN_OT_ellipse_coin.bl_idname, icon='MESH_CIRCLE')
        layout.operator(DESSIN_OT_arc_cse.bl_idname, icon='SPHERECURVE')
        layout.operator(DESSIN_OT_arc_3pts.bl_idname, icon='SPHERECURVE')
        layout.separator()
        layout.operator(DESSIN_OT_boite.bl_idname, icon='MESH_CUBE')
        layout.operator(DESSIN_OT_cylindre.bl_idname, icon='MESH_CYLINDER')
        layout.operator(DESSIN_OT_cone.bl_idname, icon='MESH_CONE')
        layout.operator(DESSIN_OT_cone_tronque.bl_idname, icon='MESH_CONE')
        layout.operator(DESSIN_OT_pyramide.bl_idname, icon='MESH_CONE')
        layout.operator(DESSIN_OT_pyramide_tronquee.bl_idname, icon='MESH_CONE')
        layout.operator(DESSIN_OT_tube.bl_idname, icon='MESH_CYLINDER')
        layout.operator(DESSIN_OT_sphere.bl_idname, icon='MESH_UVSPHERE')
        layout.operator(DESSIN_OT_ellipsoide.bl_idname, icon='MESH_UVSPHERE')
        layout.operator(DESSIN_OT_sphere_tronquee.bl_idname, icon='MESH_UVSPHERE')
        layout.operator(DESSIN_OT_tore.bl_idname, icon='MESH_TORUS')
        layout.separator()
        layout.operator(DESSIN_OT_cotation.bl_idname, icon='DRIVER_DISTANCE')
        layout.operator(DESSIN_OT_cotation_rayon.bl_idname, icon='MESH_CIRCLE')
        layout.operator(DESSIN_OT_cotation_angle.bl_idname, icon='DRIVER_ROTATIONAL_DIFFERENCE')
        layout.operator(DESSIN_OT_annotation.bl_idname, icon='FONT_DATA')
        layout.operator(DESSIN_OT_mesure_aire.bl_idname, icon='SNAP_FACE')
        layout.separator()
        layout.operator(DESSIN_OT_deplacer.bl_idname, icon='ARROW_LEFTRIGHT')
        layout.operator(DESSIN_OT_copier.bl_idname, icon='DUPLICATE')
        layout.operator(DESSIN_OT_rotation.bl_idname, icon='FILE_REFRESH')
        layout.operator(DESSIN_OT_echelle.bl_idname, icon='FULLSCREEN_ENTER')
        layout.operator(DESSIN_OT_echelle_2d.bl_idname, icon='FULLSCREEN_ENTER')
        layout.operator(DESSIN_OT_echelle_1d.bl_idname, icon='FULLSCREEN_ENTER')
        layout.operator(DESSIN_OT_echelle_taille.bl_idname, icon='FULLSCREEN_ENTER')
        layout.operator(DESSIN_OT_miroir.bl_idname, icon='MOD_MIRROR')
        layout.operator(DESSIN_OT_array_linear.bl_idname, icon='MOD_ARRAY')
        layout.operator(DESSIN_OT_array_rect.bl_idname, icon='MOD_ARRAY')
        layout.operator(DESSIN_OT_array_polar.bl_idname, icon='MOD_ARRAY')
        layout.operator(DESSIN_OT_cut.bl_idname, icon='MOD_BOOLEAN')
        layout.operator(DESSIN_OT_bool_union.bl_idname, icon='SELECT_EXTEND')
        layout.operator(DESSIN_OT_bool_difference.bl_idname, icon='SELECT_SUBTRACT')
        layout.operator(DESSIN_OT_bool_intersection.bl_idname, icon='SELECT_INTERSECT')
        layout.operator(DESSIN_OT_bool_split.bl_idname, icon='SELECT_DIFFERENCE')
        layout.operator(DESSIN_OT_fillet_edge.bl_idname, icon='MOD_BEVEL')
        layout.operator(DESSIN_OT_chamfer_edge.bl_idname, icon='MOD_BEVEL')
        layout.operator(DESSIN_OT_offset_edge.bl_idname, icon='MOD_OFFSET')
        layout.operator(DESSIN_OT_offset_surface.bl_idname, icon='MOD_OFFSET')


def menu_add(self, context):
    self.layout.separator()
    self.layout.menu(DESSIN_MT_menu.bl_idname, icon='GREASEPENCIL')


def _late_imports():
    pass
