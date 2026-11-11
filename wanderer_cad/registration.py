"""Wanderer CAD : Enregistrement des classes, outils et raccourcis."""

import bpy
import time

from .core import CPLANES, _CPLANE, _LANG_APPLIED, addon_globals, apply_language, lang, pref
from .snapping import _LOD, _lod_timer, _perf_caches_clear
from .drawing import (
    _apply_dimension_settings, _on_depsgraph_update, _on_load_clear, _on_load_post, _on_undo_redo, ensure_idle_tool,
    ensure_statusbar_osnap, find_window_region,
)
from .base import DessinBase
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
from .subd import (
    DESSIN_OT_subd, DESSIN_OT_subd_box, DESSIN_OT_subd_cone, DESSIN_OT_subd_cylinder, DESSIN_OT_subd_plane,
    DESSIN_OT_subd_sphere, DESSIN_OT_subd_torus, DESSIN_PT_subd,
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
from .selection import (
    DESSIN_OT_deselect, DESSIN_OT_esc_select, DESSIN_OT_select_loop, DESSIN_OT_selection_boite,
    DESSIN_OT_selection_cercle, DESSIN_OT_selection_lasso, DESSIN_OT_selection_rect, _SelShapeBase,
)
from .settings import DESSIN_PG_dim, DESSIN_PG_dimstyle, DESSIN_PG_hatch, DESSIN_PG_layerstate, DESSIN_PG_settings
from .dimensions import (
    DESSIN_OT_annotation, DESSIN_OT_center_mark, DESSIN_OT_cotation, DESSIN_OT_cotation_angle,
    DESSIN_OT_cotation_arc, DESSIN_OT_cotation_chain, DESSIN_OT_cotation_edit, DESSIN_OT_cotation_ordinate,
    DESSIN_OT_cotation_rayon, DESSIN_OT_cotations_supprimer, DESSIN_OT_dimstyle_add, DESSIN_OT_dimstyle_remove,
    DESSIN_OT_dimstyle_update, DESSIN_OT_dist, DESSIN_OT_id_point, DESSIN_OT_mesure_aire, DESSIN_OT_text,
    DESSIN_PT_cotation, DESSIN_PT_hatch, DESSIN_UL_dimstyles,
)
from .layers import (
    DESSIN_MT_layer_move_to, DESSIN_OT_layer_carry, DESSIN_OT_layer_click, DESSIN_OT_layer_colors_view,
    DESSIN_OT_layer_current, DESSIN_OT_layer_delete, DESSIN_OT_layer_delete_all, DESSIN_OT_layer_duplicate,
    DESSIN_OT_layer_fold, DESSIN_OT_layer_isolate, DESSIN_OT_layer_lock_all, DESSIN_OT_layer_move,
    DESSIN_OT_layer_move_selection, DESSIN_OT_layer_new, DESSIN_OT_layer_object, DESSIN_OT_layer_purge,
    DESSIN_OT_layer_refresh_colors, DESSIN_OT_layer_rename, DESSIN_OT_layer_reparent, DESSIN_OT_layer_select,
    DESSIN_OT_layer_set, DESSIN_OT_layer_show_all, DESSIN_OT_layer_state, DESSIN_PG_layer, DESSIN_PT_layers,
    DESSIN_PT_layers_filter, DESSIN_PT_toolbox, layer_button_menu,
)
from .import_dxf import DESSIN_OT_import_cad, menu_import_cad
from .objects import (
    DESSIN_MT_ctx_material, DESSIN_MT_ctx_polyline, DESSIN_MT_ctx_select, DESSIN_OT_extend_crv, DESSIN_OT_group,
    DESSIN_OT_material_remove_all, DESSIN_OT_poly_edit, DESSIN_OT_track_to, DESSIN_OT_ungroup, _GROUP_SEL,
    install_ctx_object_menu, menu_ctx_extra, menu_group, uninstall_ctx_object_menu,
)
from .curve_edit import (
    DESSIN_OT_chamfer_curve, DESSIN_OT_divide, DESSIN_OT_fillet_curve, DESSIN_OT_stretch, DESSIN_OT_xline,
    DessinCornerRound,
)
from .display import (
    DESSIN_OT_clip_edit, DESSIN_OT_clip_plane, DESSIN_OT_overkill, DESSIN_OT_sel_filter, DESSIN_OT_sel_filter_hold,
    DESSIN_PT_clip, DESSIN_PT_groups, DESSIN_PT_selfilter, DESSIN_PT_shapes, _CLIP, _group_select_tick,
    clear_clip_planes, register_sel_filter_keys, sel_filter_restore, unregister_sel_filter_keys,
)
from .gumball import (
    DESSIN_MT_gumball, DESSIN_OT_gumball, DESSIN_OT_gumball_extrude, DESSIN_OT_gumball_relocate,
    DESSIN_OT_gumball_reset, DESSIN_OT_gumball_set, DESSIN_OT_gumball_settings, GumballBase,
)
from .offset_extrude import DESSIN_OT_extrude, DESSIN_OT_offset_surface
from .trim import _CURVE_PTS, _TRIM_HL, curve_points_cb, trim_highlight_cb
from .join_explode import (
    DESSIN_OT_bar_click, DESSIN_OT_explode, DESSIN_OT_join, DESSIN_OT_pick_object, DESSIN_OT_rclick_run,
    DESSIN_OT_show_edges, DESSIN_OT_tool_exit, DESSIN_OT_tool_from_edit, DESSIN_OT_trim, DESSIN_OT_trim_mode,
    _SHOWEDGES, _edit_variant, showedges_cb,
)
from .surfaces import (
    DESSIN_OT_extrude_crv, DESSIN_OT_extrude_path, DESSIN_OT_extrude_srf, DESSIN_OT_loft, DESSIN_OT_planar_srf,
    DESSIN_OT_revolve, DESSIN_OT_sweep1, DESSIN_OT_sweep2, _ProfileOp,
)
from .hatch import (
    DESSIN_OT_hatch, DESSIN_OT_hatch_base, DESSIN_OT_hatch_boundary, DESSIN_OT_hatch_explode, DESSIN_OT_hatch_match,
    DESSIN_OT_hatch_region,
)
from .surface_tools import (
    DESSIN_OT_chamfer_srf, DESSIN_OT_extend_srf, DESSIN_OT_fillet_srf, DESSIN_OT_network_srf, DESSIN_OT_split_iso,
)
from .curve_tools import (
    DESSIN_OT_blend_crv, DESSIN_OT_change_degree, DESSIN_OT_insert_point, DESSIN_OT_match_crv, DESSIN_OT_rebuild_crv,
    DESSIN_OT_remove_point, DESSIN_OT_simplify_crv,
)
from .blocks import (
    DESSIN_OT_block, DESSIN_OT_block_delete, DESSIN_OT_block_edit, DESSIN_OT_block_edit_close,
    DESSIN_OT_block_explode, DESSIN_OT_block_insert, DESSIN_OT_block_select, DESSIN_PT_blocks,
)
from .surface_edit import (
    DESSIN_OT_align, DESSIN_OT_blend_srf, DESSIN_OT_cap, DESSIN_OT_edge_srf, DESSIN_OT_match_srf, DESSIN_OT_patch,
    DESSIN_OT_project_curve, DESSIN_OT_rail_revolve, DESSIN_OT_shell, DESSIN_OT_split_face, DESSIN_OT_subd_loft,
    DESSIN_OT_subd_revolve, DESSIN_OT_subd_sweep1, DESSIN_OT_subd_sweep2, DESSIN_OT_thicken, DESSIN_OT_untrim,
    DESSIN_OT_untrim_holes,
)
from .make2d import DESSIN_OT_make2d
from .lights import (
    DESSIN_OT_camera, DESSIN_OT_camera_target, DESSIN_OT_light_area, DESSIN_OT_light_point, DESSIN_OT_light_spot,
    DESSIN_OT_light_sun,
)
from .gumball_handles import (
    DESSIN_GGT_gumball, DESSIN_GT_gb_bar, DESSIN_GT_gb_dot, DESSIN_OT_gumball_pull, DESSIN_PT_gumball, _EXT_BALL,
    draw_extrude_ball, statusbar_osnap,
)
from .menus import DESSIN_MT_menu, menu_add
from .icons import ensure_icon
from .toolbar import RHINO_TOOLS
from .toolbar import (
    DESSIN_TT_align, DESSIN_TT_annotation, DESSIN_TT_arc_3pts, DESSIN_TT_array_polar, DESSIN_TT_blend_crv,
    DESSIN_TT_blend_srf, DESSIN_TT_block, DESSIN_TT_block_insert, DESSIN_TT_boite, DESSIN_TT_bool_union,
    DESSIN_TT_camera, DESSIN_TT_camera_target, DESSIN_TT_cap, DESSIN_TT_center_mark, DESSIN_TT_chamfer,
    DESSIN_TT_chamfer_c, DESSIN_TT_chamfer_srf, DESSIN_TT_change_degree, DESSIN_TT_clip_plane, DESSIN_TT_cotation,
    DESSIN_TT_cotation_angle, DESSIN_TT_cotation_arc, DESSIN_TT_cotation_chain, DESSIN_TT_cotation_edit,
    DESSIN_TT_cotation_ordinate, DESSIN_TT_cotation_rayon, DESSIN_TT_cut, DESSIN_TT_deplacer, DESSIN_TT_dist,
    DESSIN_TT_divide, DESSIN_TT_edge_srf, DESSIN_TT_explode, DESSIN_TT_extend_srf, DESSIN_TT_extrude,
    DESSIN_TT_extrude_crv, DESSIN_TT_extrude_path, DESSIN_TT_extrude_srf, DESSIN_TT_fillet_c, DESSIN_TT_fillet_srf,
    DESSIN_TT_hatch, DESSIN_TT_hatch_region, DESSIN_TT_id_point, DESSIN_TT_insert_point, DESSIN_TT_join,
    DESSIN_TT_light_area, DESSIN_TT_light_point, DESSIN_TT_light_spot, DESSIN_TT_light_sun, DESSIN_TT_loft,
    DESSIN_TT_make2d, DESSIN_TT_match_crv, DESSIN_TT_match_srf, DESSIN_TT_mesure_aire, DESSIN_TT_miroir,
    DESSIN_TT_network_srf, DESSIN_TT_offset, DESSIN_TT_offset_surface, DESSIN_TT_overkill, DESSIN_TT_patch,
    DESSIN_TT_plan, DESSIN_TT_planar_srf, DESSIN_TT_polyligne, DESSIN_TT_project_curve, DESSIN_TT_rail_revolve,
    DESSIN_TT_rebuild_crv, DESSIN_TT_remove_point, DESSIN_TT_revolve, DESSIN_TT_selection_boite,
    DESSIN_TT_selection_cercle, DESSIN_TT_selection_lasso, DESSIN_TT_selection_rect, DESSIN_TT_shell,
    DESSIN_TT_simplify_crv, DESSIN_TT_split_face, DESSIN_TT_split_iso, DESSIN_TT_srf_corners, DESSIN_TT_stretch,
    DESSIN_TT_subd_box, DESSIN_TT_subd_plane, DESSIN_TT_sweep1, DESSIN_TT_sweep2, DESSIN_TT_text, DESSIN_TT_thicken,
    DESSIN_TT_tore, DESSIN_TT_trim, DESSIN_TT_untrim, DESSIN_TT_untrim_holes, TOOL_ORDER, _EDIT_TOOLS,
    _SELECT_TOOL_IDS, _SUBD_EDIT_LIST, _SUBD_OBJ_LIST,
)
from .navigation import (
    DEFAULT_TABS, DESSIN_OT_context_menu, DESSIN_OT_grs_key, DESSIN_OT_middle_action, DESSIN_OT_mouse_block,
    DESSIN_OT_mouse_track, DESSIN_OT_orbit_hold, DESSIN_OT_orbit_pan, DESSIN_OT_orbit_persp, DESSIN_OT_pan2d,
    DESSIN_OT_shortcuts_clear, DESSIN_OT_trackpad_pan, DESSIN_OT_trackpad_persp, add_grs_to_tool_keymaps,
    apply_nav_inputs, register_grs_keymap, register_shortcuts, register_view_keymap, start_navigation,
    unregister_grs_keymap, unregister_shortcuts, unregister_view_keymap,
)
from .views import (
    CMD_ALIASES, DESSIN_MT_named_views, DESSIN_OT_view_delete, DESSIN_OT_view_duplicate, DESSIN_OT_view_pin,
    DESSIN_OT_view_rename, DESSIN_OT_view_restore, DESSIN_OT_view_save, DESSIN_OT_view_update, DESSIN_PG_view,
    DESSIN_PT_named_views, _CMD, named_view_button_menu,
)
from .cplane import DESSIN_OT_cplane, DESSIN_OT_cplane_elevation, _CP_DRAW, cplane_draw_cb
from .pushpull import DESSIN_OT_pushpull, _AUTOCP, autocp_timer
from .rhino_commands import (
    DESSIN_OT_contour, DESSIN_OT_dup_border, DESSIN_OT_dup_edge, DESSIN_OT_extract_srf, DESSIN_OT_intersect,
    DESSIN_OT_merge_faces, DESSIN_OT_orient, DESSIN_OT_pipe, DESSIN_OT_rebuild_srf, DESSIN_OT_section,
    DESSIN_OT_unroll,
)
from .command_line import (
    CmdKeyEvent, DESSIN_MT_auto_cplane, DESSIN_MT_mouse_menu, DESSIN_MT_polar_angle, DESSIN_OT_command_line,
    DESSIN_OT_cplane_named, _VBAR, cmd_bar_cb, cmd_hit, register_cmd_keymap, register_mouse_track,
    unregister_cmd_keymap, unregister_mouse_track, views_bar_cb,
)
from .preferences import DESSIN_AP_prefs, DESSIN_OT_install_theme, DESSIN_OT_prefs_reset


classes = (
    DESSIN_OT_command_line,
    DESSIN_OT_orbit_pan,
    DESSIN_OT_orbit_persp,
    DESSIN_OT_trackpad_pan,
    DESSIN_OT_trackpad_persp,
    DESSIN_PG_view,
    DESSIN_OT_view_restore,
    DESSIN_OT_view_save,
    DESSIN_OT_view_update,
    DESSIN_OT_view_duplicate,
    DESSIN_OT_view_rename,
    DESSIN_OT_view_delete,
    DESSIN_OT_view_pin,
    DESSIN_PT_named_views,
    DESSIN_MT_named_views,
    DESSIN_OT_orbit_hold,
    DESSIN_OT_pan2d,
    DESSIN_MT_mouse_menu,
    DESSIN_OT_context_menu,
    DESSIN_OT_middle_action,
    DESSIN_OT_mouse_block,
    DESSIN_OT_mouse_track,
    DESSIN_OT_grs_key,
    DESSIN_OT_rectangle,
    DESSIN_OT_plan,
    DESSIN_OT_srf_corners,
    DESSIN_OT_polyligne,
    DESSIN_OT_xline,
    DESSIN_OT_stretch,
    DESSIN_OT_divide,
    DESSIN_OT_overkill,
    DESSIN_OT_show_edges,
    DESSIN_OT_fillet_curve,
    DESSIN_OT_chamfer_curve,
    DESSIN_OT_clip_plane,
    DESSIN_OT_clip_edit,
    DESSIN_OT_sel_filter,
    DESSIN_OT_sel_filter_hold,
    DESSIN_PT_clip,
    DESSIN_OT_curve_cp,
    DESSIN_OT_curve_interp,
    DESSIN_OT_pen,
    DESSIN_OT_sketch,
    DESSIN_OT_point,
    DESSIN_OT_selection_boite,
    DESSIN_OT_poly_center,
    DESSIN_OT_poly_circ,
    DESSIN_OT_poly_area,
    DESSIN_OT_poly_edge,
    DESSIN_OT_poly_star,
    DESSIN_OT_cercle,
    DESSIN_OT_cercle_diametre,
    DESSIN_OT_ellipse_centre,
    DESSIN_OT_ellipse_diametre,
    DESSIN_OT_ellipse_foyers,
    DESSIN_OT_ellipse_coin,
    DESSIN_OT_arc_cse,
    DESSIN_OT_arc_3pts,
    DESSIN_OT_boite,
    DESSIN_OT_cylindre,
    DESSIN_OT_cone,
    DESSIN_OT_cone_tronque,
    DESSIN_OT_pyramide,
    DESSIN_OT_pyramide_tronquee,
    DESSIN_OT_tube,
    DESSIN_OT_sphere,
    DESSIN_OT_ellipsoide,
    DESSIN_OT_sphere_tronquee,
    DESSIN_OT_tore,
    DESSIN_OT_cotation,
    DESSIN_OT_cotation_rayon,
    DESSIN_OT_cotation_angle,
    DESSIN_OT_annotation,
    DESSIN_OT_subd_box,
    DESSIN_OT_subd_sphere,
    DESSIN_OT_subd_cylinder,
    DESSIN_OT_subd_cone,
    DESSIN_OT_subd_torus,
    DESSIN_OT_subd_plane,
    DESSIN_OT_subd,
    DESSIN_OT_subd_loft,
    DESSIN_OT_subd_sweep1,
    DESSIN_OT_subd_sweep2,
    DESSIN_OT_subd_revolve,
    DESSIN_PT_subd,
    DESSIN_OT_text,
    DESSIN_OT_dist,
    DESSIN_OT_center_mark,
    DESSIN_OT_hatch_region,
    DESSIN_OT_cotation_chain,
    DESSIN_OT_cotation_ordinate,
    DESSIN_OT_cotation_arc,
    DESSIN_OT_cotation_edit,
    DESSIN_OT_hatch_base,
    DESSIN_OT_id_point,
    DESSIN_OT_mesure_aire,
    DESSIN_OT_deplacer,
    DESSIN_OT_copier,
    DESSIN_OT_rotation,
    DESSIN_OT_echelle,
    DESSIN_OT_echelle_2d,
    DESSIN_OT_echelle_1d,
    DESSIN_OT_echelle_taille,
    DESSIN_OT_miroir,
    DESSIN_OT_array_rect,
    DESSIN_OT_array_linear,
    DESSIN_OT_array_polar,
    DESSIN_OT_cut,
    DESSIN_OT_bool_union,
    DESSIN_OT_bool_difference,
    DESSIN_OT_bool_intersection,
    DESSIN_OT_bool_split,
    DESSIN_OT_fillet_edge,
    DESSIN_OT_chamfer_edge,
    DESSIN_OT_offset_edge,
    DESSIN_OT_offset_surface,
    DESSIN_OT_extrude,
    DESSIN_OT_trim,
    DESSIN_OT_tool_exit,
    DESSIN_OT_rclick_run,
    DESSIN_OT_bar_click,
    DESSIN_OT_esc_select,
    DESSIN_OT_poly_edit,
    DESSIN_OT_extend_crv,
    DESSIN_MT_ctx_polyline,
    DESSIN_OT_tool_from_edit,
    DESSIN_OT_join,
    DESSIN_OT_explode,
    DESSIN_OT_pick_object,
    DESSIN_OT_revolve,
    DESSIN_OT_extrude_crv,
    DESSIN_OT_extrude_srf,
    DESSIN_OT_planar_srf,
    DESSIN_OT_hatch,
    DESSIN_OT_hatch_explode,
    DESSIN_OT_hatch_boundary,
    DESSIN_OT_pipe,
    DESSIN_OT_intersect,
    DESSIN_OT_section,
    DESSIN_OT_contour,
    DESSIN_OT_extract_srf,
    DESSIN_OT_dup_edge,
    DESSIN_OT_dup_border,
    DESSIN_OT_merge_faces,
    DESSIN_OT_unroll,
    DESSIN_OT_rebuild_srf,
    DESSIN_OT_orient,
    DESSIN_OT_hatch_match,
    DESSIN_OT_fillet_srf,
    DESSIN_OT_chamfer_srf,
    DESSIN_OT_extend_srf,
    DESSIN_OT_split_iso,
    DESSIN_OT_network_srf,
    DESSIN_OT_rebuild_crv,
    DESSIN_OT_simplify_crv,
    DESSIN_OT_change_degree,
    DESSIN_OT_insert_point,
    DESSIN_OT_remove_point,
    DESSIN_OT_match_crv,
    DESSIN_OT_blend_crv,
    DESSIN_OT_untrim,
    DESSIN_OT_untrim_holes,
    DESSIN_OT_block,
    DESSIN_OT_block_insert,
    DESSIN_OT_block_explode,
    DESSIN_OT_block_edit,
    DESSIN_OT_block_edit_close,
    DESSIN_OT_block_delete,
    DESSIN_OT_block_select,
    DESSIN_OT_edge_srf,
    DESSIN_OT_thicken,
    DESSIN_OT_cap,
    DESSIN_OT_split_face,
    DESSIN_OT_project_curve,
    DESSIN_OT_patch,
    DESSIN_OT_blend_srf,
    DESSIN_OT_match_srf,
    DESSIN_OT_rail_revolve,
    DESSIN_OT_shell,
    DESSIN_OT_loft,
    DESSIN_OT_sweep1,
    DESSIN_OT_sweep2,
    DESSIN_OT_extrude_path,
    DESSIN_OT_align,
    DESSIN_OT_make2d,
    DESSIN_OT_light_point,
    DESSIN_OT_light_spot,
    DESSIN_OT_light_sun,
    DESSIN_OT_light_area,
    DESSIN_OT_camera,
    DESSIN_OT_camera_target,
    DESSIN_MT_menu,
    DESSIN_PG_dimstyle,
    DESSIN_PG_hatch,
    DESSIN_PG_dim,
    DESSIN_PG_layerstate,
    DESSIN_PG_settings,
    DESSIN_UL_dimstyles,
    DESSIN_OT_dimstyle_add,
    DESSIN_OT_dimstyle_update,
    DESSIN_OT_dimstyle_remove,
    DESSIN_OT_cotations_supprimer,
    DESSIN_OT_import_cad,
    DESSIN_PG_layer,
    DESSIN_OT_layer_current,
    DESSIN_OT_layer_new,
    DESSIN_OT_layer_delete,
    DESSIN_OT_layer_move_selection,
    DESSIN_OT_layer_select,
    DESSIN_OT_layer_isolate,
    DESSIN_OT_layer_click,
    DESSIN_OT_layer_object,
    DESSIN_PT_layers_filter,
    DESSIN_PT_toolbox,
    DESSIN_OT_layer_carry,
    DESSIN_OT_layer_fold,
    DESSIN_OT_layer_reparent,
    DESSIN_MT_layer_move_to,
    DESSIN_OT_layer_state,
    DESSIN_OT_layer_set,
    DESSIN_OT_layer_duplicate,
    DESSIN_OT_layer_delete_all,
    DESSIN_OT_layer_rename,
    DESSIN_OT_layer_move,
    DESSIN_OT_layer_purge,
    DESSIN_OT_layer_show_all,
    DESSIN_OT_layer_lock_all,
    DESSIN_OT_layer_colors_view,
    DESSIN_OT_layer_refresh_colors,
    DESSIN_PT_layers,
    DESSIN_OT_group,
    DESSIN_OT_ungroup,
    DESSIN_OT_material_remove_all,
    DESSIN_MT_ctx_material,
    DESSIN_OT_track_to,
    DESSIN_MT_ctx_select,
    DESSIN_PT_shapes,
    DESSIN_PT_groups,
    DESSIN_OT_gumball,
    DESSIN_OT_gumball_relocate,
    DESSIN_OT_gumball_reset,
    DESSIN_OT_gumball_set,
    DESSIN_OT_gumball_settings,
    DESSIN_MT_gumball,
    DESSIN_OT_gumball_extrude,
    DESSIN_OT_gumball_pull,
    DESSIN_OT_deselect,
    DESSIN_OT_selection_lasso,
    DESSIN_OT_selection_rect,
    DESSIN_OT_selection_cercle,
    DESSIN_OT_cplane,
    DESSIN_OT_cplane_elevation,
    DESSIN_OT_pushpull,
    DESSIN_OT_cplane_named,
    DESSIN_MT_auto_cplane,
    DESSIN_OT_select_loop,
    DESSIN_GT_gb_dot,
    DESSIN_GT_gb_bar,
    DESSIN_GGT_gumball,
    DESSIN_PT_gumball,
    DESSIN_PT_cotation,
    DESSIN_PT_hatch,
    DESSIN_PT_blocks,
    DESSIN_OT_shortcuts_clear,
    DESSIN_OT_prefs_reset,
    DESSIN_OT_install_theme,
    DESSIN_OT_trim_mode,
    DESSIN_AP_prefs,
    DESSIN_MT_polar_angle,
    DESSIN_PT_selfilter,
)


def _tool_list(mode):
    from bl_ui.space_toolsystem_common import ToolSelectPanelHelper
    return ToolSelectPanelHelper._tool_class_from_space_type('VIEW_3D')._tools[mode]


def _arrange_tools(mode, chain, head=()):
    """Place nos outils juste après « Transformer », dans l'ordre voulu, avec leurs séparateurs.
    `head` (Select / Move + Lasso) va dans le même bloc que « Cursor », juste avant lui."""
    from bl_ui.space_toolsystem_common import ToolDef
    tools = _tool_list(mode)
    ours = {id(cls._bl_tool) for cls, _ in list(chain) + list(head)}
    tools[:] = [t for t in tools if id(t) not in ours]
    if head:
        group = tuple(cls._bl_tool for cls, _ in head)
        pos = 0
        for k, t in enumerate(tools):
            if isinstance(t, ToolDef) and t.idname == "builtin.cursor":
                pos = k
                break
        else:
            for k, t in enumerate(tools):
                if t is None:
                    pos = k
                    break
        tools.insert(pos, group)
    idx = len(tools) - 1
    for k, t in enumerate(tools):
        if isinstance(t, ToolDef) and t.idname == "builtin.transform":
            idx = k
            break
    block = []
    for cls, sep in chain:
        if sep:
            block.append(None)
        if getattr(cls, "_in_group", False) and block and block[-1] is not None:
            prev = block[-1]
            block[-1] = (prev,) + (cls._bl_tool,) if isinstance(prev, ToolDef) else prev + (cls._bl_tool,)
            continue
        block.append(cls._bl_tool)
    if idx + 1 < len(tools) and tools[idx + 1] is not None:
        block.append(None)
    tools[idx + 1:idx + 1] = block


def _flatten_singletons(mode):
    """Un menu déroulant d'un seul outil n'a pas de raison d'être : on l'aplatit."""
    tools = _tool_list(mode)
    for k, t in enumerate(tools):
        if isinstance(t, tuple) and len(t) == 1:
            tools[k] = t[0]


def _tidy_separators(mode):
    tools = _tool_list(mode)
    out = []
    for t in tools:
        if t is None and (not out or out[-1] is None):
            continue
        out.append(t)
    tools[:] = out


HIDE_NATIVE_PREFIXES = {"show_tool_annotate": "builtin.annotate", "show_tool_measure": "builtin.measure", "show_tool_cube": "builtin.primitive"}
_HIDDEN_SAVED = {}


HIDE_TOOL_GROUPS = {   # réglage -> outils natifs de la barre d'outils masqués (Objet et Édition)
    "show_tool_cursor": {"builtin.cursor"},
    "show_tool_select": {"builtin.select", "builtin.select_box", "builtin.select_circle", "builtin.select_lasso"},
    "show_tool_move": {"builtin.move"},
    "show_tool_rotate": {"builtin.rotate"},
    "show_tool_scale": {"builtin.scale", "builtin.scale_cage"},
    "show_tool_transform": {"builtin.transform"},
}


def _native_tool_hidden(idname):
    """True si cet outil natif de Blender doit être masqué dans la barre d'outils (réglages des préférences)."""
    if not idname or not idname.startswith("builtin."):
        return False
    if idname in {"builtin.breakdowner", "builtin.push", "builtin.relax"}:      # outils d'animation (pose), inutiles ici
        return True
    for key, prefix in HIDE_NATIVE_PREFIXES.items():
        if idname.startswith(prefix) and not pref(key):
            return True
    for key, names in HIDE_TOOL_GROUPS.items():
        if idname in names and not pref(key):
            return True
    return False


_TB_FILTER = {"orig": None, "cls": None}


def _toolbar_wanderer_ids():
    keep = set(_SELECT_TOOL_IDS)
    ids = {c.bl_idname for n, c in addon_globals().items() if n.startswith("DESSIN_TT_") and isinstance(c, type) and hasattr(c, "bl_idname")}
    return ids - keep


def _install_toolbar_filter():
    """Masque nos outils à l'affichage de la barre seulement : la recherche d'outil (wm.tool_set_by_id) les voit toujours."""
    import sys
    from bl_ui.space_toolsystem_common import ToolSelectPanelHelper, ToolDef
    cls = ToolSelectPanelHelper._tool_class_from_space_type('VIEW_3D')
    if cls is None or _TB_FILTER["orig"] is not None:
        return
    orig = cls.__dict__["tools_from_context"]
    base = orig.__func__

    def tools_from_context(klass, context, mode=None):
        items = base(klass, context, mode)
        try:
            if sys._getframe(1).f_code.co_name != "draw_cls":
                return items
            ours = set() if pref("show_toolbar_tools") else _toolbar_wanderer_ids()
        except (ValueError, AttributeError, KeyError):
            return items
        hide = lambda n: n in ours or _native_tool_hidden(n)
        out = []
        for it in items:
            if type(it) is tuple:      # un groupe ; un ToolDef est lui aussi un tuple nommé : ne pas le confondre
                it = tuple(x for x in it if not hide(getattr(x, "idname", None)))
                if not any(x is not None for x in it):
                    continue
                if len([x for x in it if x is not None]) == 1:
                    it = next(x for x in it if x is not None)
            elif hide(getattr(it, "idname", None)):
                continue
            if it is None and (not out or out[-1] is None):
                continue
            out.append(it)
        return out
    _TB_FILTER["orig"], _TB_FILTER["cls"] = orig, cls
    cls.tools_from_context = classmethod(tools_from_context)


def _remove_toolbar_filter():
    if _TB_FILTER["orig"] is not None:
        _TB_FILTER["cls"].tools_from_context = _TB_FILTER["orig"]
        _TB_FILTER["orig"] = _TB_FILTER["cls"] = None


def _update_toolbar_filter():
    try:
        wm = bpy.context.window_manager
        for w in wm.windows:
            for a in w.screen.areas:
                for r in a.regions:
                    r.tag_redraw()
    except (AttributeError, RuntimeError, ReferenceError):
        pass


def _hide_native_tools():
    """Réglages d'affichage des outils natifs : le masquage se fait au dessin de la barre (filtre), la liste de Blender n'est jamais
    modifiée. Rend aussi à la liste ce qu'une ancienne version y avait retiré, puis redessine."""
    _restore_native_tools()
    _update_toolbar_filter()


def _restore_native_tools():
    for mode, original in list(_HIDDEN_SAVED.items()):
        tools = _tool_list(mode)
        known = {id(t) for t in original if t is not None}
        extra = [t for t in tools if t is not None and id(t) not in known]
        tools[:] = original + extra
        _tidy_separators(mode)
    _HIDDEN_SAVED.clear()


def _enrich_tooltips():
    """Infobulles détaillées des outils : description, mode d'emploi pas à pas, alias de la ligne de commande, touches utiles."""
    on = pref("rich_tooltips")
    for name, cls in list(addon_globals().items()):
        if not (name.startswith("DESSIN_TT_") and hasattr(cls, "bl_idname") and hasattr(cls, "bl_description")):
            continue
        base = getattr(cls, "_plain_desc", None)
        if base is None:
            base = cls.bl_description
            cls._plain_desc = base
        if not on:
            cls.bl_description = base
            continue
        lines = [base]
        hint = getattr(cls, "dessin_hint", "")
        steps = [h.strip() for h in hint.split("·") if h.strip()] if hint else []
        if steps:
            lines += ["", "How to use:"] + ["  • " + h for h in steps]
        key = cls.bl_idname.split(".", 1)[-1]
        alias = CMD_ALIASES.get(key)
        if alias:
            lines += ["", "Command line: type  " + "  or  ".join(alias.split())]
        hover = any(k[1].get("type") == 'MOUSEMOVE' for k in getattr(cls, "bl_keymap", ()) if len(k) > 1 and isinstance(k[1], dict))
        if hover:
            lines += ["", "While drawing:", "  • Esc: cancel   • Enter / Space: confirm", "  • Shift: orthogonal   • S: snap on / off",
                      "  • X / Y / Z: lock an axis", "  • Type a value, Tab: next field"]
        cls.bl_description = "\n".join(lines)


class _NoHintLayout:
    """Enveloppe d'un layout qui ignore les libellés d'aide (les réglages de l'outil restent affichés)."""

    def __init__(self, layout):
        object.__setattr__(self, "_layout", layout)

    def label(self, *args, **kwargs):
        return None

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_layout"), name)

    def __setattr__(self, name, value):
        setattr(object.__getattribute__(self, "_layout"), name, value)


def _apply_tool_hints_pref():
    """Réglage « Show tool hints in the toolbar header » : masque (par défaut) le texte d'aide de l'en-tête, déjà donné par la ligne de commande."""
    for name, cls in list(addon_globals().items()):
        orig = getattr(cls, "draw_settings", None) if name.startswith("DESSIN_TT_") else None
        if orig is None or getattr(orig, "_no_hints", False):
            continue

        def make(fn):
            def draw_settings(context, layout, tool):
                fn(context, _NoHintLayout(layout), tool)
            draw_settings._no_hints = True
            return draw_settings
        cls.draw_settings = make(orig)


def rclick_filter(op, context, event, orig):
    """« Enable quick secondary click as return key » : clic droit rapide = Entrée dans toutes les commandes (dessin,
    sélection des objets, extrusion...) ; glisser avec le bouton droit = orbite / pan. None : l'évènement n'est pas concerné."""
    et = event.type
    area = context.area
    if area is None:
        return None
    rc = getattr(op, "_rc", None)
    tol = max(1, pref("mouse_menu_tol"))
    if rc is None:
        if (et == 'RIGHTMOUSE' and event.value == 'PRESS' and not (event.ctrl or event.alt or event.oskey or event.shift)
                and find_window_region(area, event.mouse_x, event.mouse_y) is not None
                and not getattr(op, "mouse_over_ui", lambda e: False)(event) and cmd_hit(area, event.mouse_x, event.mouse_y) is None):
            op._rc = (event.mouse_x, event.mouse_y, time.monotonic())
            op._rc_swallow = False
            return {'RUNNING_MODAL'}
        if et == 'RIGHTMOUSE' and getattr(op, "_rc_swallow", False) and event.value in {'RELEASE', 'CLICK', 'CLICK_DRAG'}:
            # fin d'une orbite lancée depuis la commande : ce relâchement ne doit jamais valider la commande
            if event.value != 'CLICK_DRAG':
                op._rc_swallow = event.value == 'RELEASE'      # le CLICK éventuel qui suit le relâchement est absorbé aussi
            return {'RUNNING_MODAL'}
        if et == 'RIGHTMOUSE' and getattr(op, "_rc_swallow", False):
            op._rc_swallow = False
        return None
    moved = abs(event.mouse_x - rc[0]) > tol or abs(event.mouse_y - rc[1]) > tol
    drag = et == 'RIGHTMOUSE' and event.value == 'CLICK_DRAG'      # Blender signale lui-même le glissé
    if et in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'} or drag:
        if moved or drag:
            op._rc = None
            op._rc_swallow = True
            if not start_navigation(context):
                try:
                    bpy.ops.view3d.rotate('INVOKE_DEFAULT')
                except RuntimeError:
                    pass
        return {'RUNNING_MODAL'}
    if et == 'RIGHTMOUSE' and event.value == 'RELEASE':
        op._rc = None
        op._rc_swallow = True                  # absorbe le CLICK que Blender envoie juste après le relâchement
        # Entrée seulement pour un vrai clic rapide (relâché vite, au même endroit), comme Rhino : un clic droit maintenu
        # (on s'apprêtait à orbiter) ne valide jamais la commande
        if not moved and time.monotonic() - rc[2] <= rclick_quick_s():
            return orig(op, context, CmdKeyEvent(event, 'RET', ""))
        return {'RUNNING_MODAL'}
    return None


def rclick_quick_s():
    """Durée maximale d'un clic droit « rapide » : le délai du double-clic de Blender (350 ms par défaut)."""
    try:
        return max(0.15, min(1.0, bpy.context.preferences.inputs.mouse_double_click_time / 1000.0))
    except (AttributeError, TypeError):
        return 0.35


IS_MAC = __import__("sys").platform == "darwin"


class _CmdAsCtrl:
    """Évènement vu à travers ⌘ = Ctrl (Mac). Tout le reste est lu sur l'évènement d'origine."""
    __slots__ = ("_e",)

    def __init__(self, e):
        object.__setattr__(self, "_e", e)

    def __getattr__(self, k):
        return getattr(self._e, k)

    ctrl = property(lambda self: True)
    oskey = property(lambda self: False)


def _cmd_orbits():
    """⌘ sert-il à émuler le 3e bouton de souris (réglage Blender) ? Il garde alors son rôle de navigation."""
    try:
        inp = bpy.context.preferences.inputs
        return bool(inp.use_mouse_emulate_3_button and inp.mouse_emulate_3_button_modifier == 'OSKEY')
    except AttributeError:
        return False


def mac_event(event):
    """Sur Mac, ⌘ fait office de Ctrl pour choisir et dessiner (⌘+clic retire, ⌘+Maj+clic = sous-objet), comme Rhino pour Mac."""
    try:
        if IS_MAC and event.oskey and not event.ctrl and not _cmd_orbits():
            return _CmdAsCtrl(event)
    except (AttributeError, ReferenceError):
        pass
    return event


def _wrap_mac(cls):
    """invoke() / modal() de la classe reçoivent l'évènement avec ⌘ = Ctrl sur Mac."""
    if not IS_MAC or "_mac_wrapped" in cls.__dict__:
        return
    def make(orig):
        def wrapped(self, context, event):      # exactement 3 arguments : Blender vérifie la signature à l'enregistrement
            return orig(self, context, mac_event(event))
        return wrapped
    for name in ("invoke", "modal"):
        orig = getattr(cls, name, None)
        if orig is None or not callable(orig):
            continue
        setattr(cls, name, make(orig))
    cls._mac_wrapped = True


def _modal_scene_lost(op, context):
    """Un objet tenu par la commande a disparu (annulation, suppression, autre fichier) : la commande s'arrête proprement
    au lieu de laisser une erreur Python, des aperçus et des gestionnaires orphelins."""
    for fn in (getattr(op, "cleanup", None), (lambda c: DessinBase.cleanup(op, c)) if isinstance(op, DessinBase) else None):
        if fn is None:
            continue
        try:
            fn(context)
            break
        except Exception:
            continue
    try:
        op.report({'WARNING'}, "Command cancelled: the scene changed during the command (undo or deleted object)")
    except Exception:
        pass
    try:
        go = getattr(op, "go_idle", None)
        if go is not None:
            go()
    except Exception:
        pass
    return {'CANCELLED'}


def _wrap_guard(cls):
    """Enveloppe modal() : une référence à un objet supprimé (ReferenceError) arrête la commande proprement."""
    if "_guard_wrapped" in cls.__dict__:
        return
    orig = cls.modal

    def modal(self, context, event):
        try:
            return orig(self, context, event)
        except ReferenceError:
            return _modal_scene_lost(self, context)
    cls.modal = modal
    cls._guard_wrapped = True


PASTE_KEYS = {'0': 'ZERO', '1': 'ONE', '2': 'TWO', '3': 'THREE', '4': 'FOUR', '5': 'FIVE', '6': 'SIX', '7': 'SEVEN', '8': 'EIGHT',
              '9': 'NINE', '.': 'PERIOD', ',': 'COMMA', '-': 'MINUS', ';': 'SEMI_COLON', '#': 'NONE', '@': 'NONE', '<': 'NONE',
              '\t': 'TAB', '\n': 'RET', ' ': 'RET'}
PASTE_MAX = 4000        # caractères collés au plus


class PasteEvent:
    """Touche fabriquée à partir d'un caractère collé : même forme qu'un évènement clavier, à la position de la souris."""

    def __init__(self, src, ch):
        self.type = PASTE_KEYS[ch]
        self.value = 'PRESS'
        self.unicode = self.ascii = "" if ch in "\t\n " else ch
        self.ctrl = self.alt = self.shift = self.oskey = self.hyper = False
        self.is_repeat = False
        self.is_tablet = False
        self.pressure = 1.0
        for k in ("mouse_x", "mouse_y", "mouse_region_x", "mouse_region_y", "mouse_prev_x", "mouse_prev_y",
                  "mouse_prev_press_x", "mouse_prev_press_y"):
            setattr(self, k, getattr(src, k, 0))


def paste_text(text):
    """Texte du presse-papiers prêt à être rejoué touche par touche, ou None s'il ne contient pas que des nombres et des
    coordonnées. Espaces et retours à la ligne valent Entrée (un par séparateur) ; une ligne vide vaut donc Entrée seule."""
    if not text:
        return None
    t = text.replace("\r\n", "\n").replace("\r", "\n").lstrip(" \n")
    end_enter = t.endswith("\n")
    t = t.rstrip(" \n")
    if not t or len(t) > PASTE_MAX or any(ch not in PASTE_KEYS for ch in t):
        return None
    out, prev_space = [], False
    for ch in t:
        if ch == " ":
            if not prev_space:
                out.append("\n")
            prev_space = True
            continue
        prev_space = False
        out.append(ch)
    return "".join(out) + ("\n" if end_enter else "")


def paste_feed(op, context, event):
    """Ctrl/Cmd + V pendant une commande : les nombres et coordonnées du presse-papiers sont entrés comme s'ils étaient
    tapés (« #0,0 », « @10,0 », « 12.5 », plusieurs points séparés par des espaces ou des retours à la ligne)."""
    try:
        raw = context.window_manager.clipboard
    except (AttributeError, RuntimeError, UnicodeDecodeError):
        raw = ""
    text = paste_text(raw)
    if text is None:
        try:
            op.report({'INFO'}, "Paste: the clipboard holds no numbers or coordinates")
        except (AttributeError, RuntimeError, ReferenceError):
            pass
        return {'RUNNING_MODAL'}
    res = {'RUNNING_MODAL'}
    for ch in text:
        res = type(op).modal(op, context, PasteEvent(event, ch))
        if not isinstance(res, set) or res & {'FINISHED', 'CANCELLED'}:
            return res
    return {'RUNNING_MODAL'}


def _is_paste(event):
    return (event.type == 'V' and event.value == 'PRESS' and (event.ctrl or event.oskey) and not event.alt and not event.shift
            and not isinstance(event, PasteEvent))


def _wrap_paste(cls):
    """Enveloppe le modal() d'une commande qui gère elle-même le clic droit : Ctrl/Cmd + V colle des nombres."""
    if "_paste_wrapped" in cls.__dict__ or "_rc_wrapped" in cls.__dict__:
        return
    orig = cls.modal

    def modal(self, context, event):
        if _is_paste(event):
            return paste_feed(self, context, event)
        return orig(self, context, event)
    cls.modal = modal
    cls._paste_wrapped = True


def _wrap_rclick(cls):
    """Enveloppe le modal() d'une commande : le clic droit rapide vaut Entrée si l'option est cochée ; Ctrl/Cmd + V colle
    des nombres ou des coordonnées."""
    if "_rc_wrapped" in cls.__dict__:
        return
    orig = cls.modal

    def modal(self, context, event):
        if _is_paste(event):
            return paste_feed(self, context, event)
        if hasattr(self, "coord_pre"):
            res = self.coord_pre(context, event)      # coordonnées tapées et From : avant le modal de l'outil
            if res is not None:
                return res
        if pref("rclick_enter") or getattr(self, "_rc", None) is not None:
            res = rclick_filter(self, context, event, orig)
            if res is not None:
                return res
        return orig(self, context, event)
    cls.modal = modal
    cls._rc_wrapped = True


def register():
    # les préférences d'abord : la langue choisie doit être connue avant d'enregistrer les noms d'outils
    bpy.utils.register_class(DESSIN_AP_prefs)
    try:
        _LANG_APPLIED["v"] = lang()
        tool_classes = [c for n, c in list(addon_globals().items()) if n.startswith("DESSIN_TT_") and isinstance(c, type)]
        tool_classes += [c for grp in _SUBD_OBJ_LIST + _SUBD_EDIT_LIST for c in grp if c not in tool_classes]
        apply_language(list(classes) + tool_classes)
    except (KeyError, AttributeError, ReferenceError, RuntimeError):
        pass
    rc_bases = (DessinBase, GumballBase, DessinCornerRound, DESSIN_OT_divide, DESSIN_OT_offset_surface, DESSIN_OT_blend_srf)
    mac_cls = rc_bases + (DESSIN_OT_selection_boite, _SelShapeBase, DESSIN_OT_selection_cercle, DESSIN_OT_select_loop,
                          DESSIN_OT_layer_current, DESSIN_OT_layer_click, DESSIN_OT_view_restore, _ProfileOp)
    for c in classes:
        if c is not DESSIN_AP_prefs:
            if issubclass(c, rc_bases) and hasattr(c, "modal"):
                _wrap_rclick(c)
            elif c is DESSIN_OT_pushpull:
                _wrap_paste(c)
            if issubclass(c, bpy.types.Operator) and callable(getattr(c, "modal", None)):
                _wrap_guard(c)        # en dernier : c'est l'enveloppe la plus extérieure
            if issubclass(c, mac_cls):
                _wrap_mac(c)            # Mac : ⌘ = Ctrl (après l'enveloppe du clic droit, pour qu'elle voie aussi ⌘ comme Ctrl)
            bpy.utils.register_class(c)
    _enrich_tooltips()
    _apply_tool_hints_pref()
    bpy.types.Scene.dessin = bpy.props.PointerProperty(type=DESSIN_PG_settings)
    bpy.types.Object.dessin_hatch = bpy.props.PointerProperty(type=DESSIN_PG_hatch)
    bpy.types.Object.dessin_dim = bpy.props.PointerProperty(type=DESSIN_PG_dim)
    bpy.types.Collection.dessin_layer = bpy.props.PointerProperty(type=DESSIN_PG_layer)
    bpy.types.Scene.dessin_views = bpy.props.CollectionProperty(type=DESSIN_PG_view)
    bpy.types.Scene.dessin_view_tabs = bpy.props.StringProperty(default=DEFAULT_TABS)
    bpy.types.Scene.dessin_view_labels = bpy.props.StringProperty()
    bpy.types.STATUSBAR_HT_header.prepend(statusbar_osnap)
    bpy.app.timers.register(ensure_statusbar_osnap, first_interval=1.0)
    bpy.app.timers.register(ensure_statusbar_osnap, first_interval=4.0)
    bpy.app.timers.register(ensure_idle_tool, first_interval=1.5)
    bpy.types.UI_MT_button_context_menu.prepend(named_view_button_menu)
    bpy.types.VIEW3D_MT_add.append(menu_add)
    bpy.types.TOPBAR_MT_file_import.append(menu_import_cad)
    bpy.types.UI_MT_button_context_menu.append(layer_button_menu)
    bpy.types.VIEW3D_MT_object_context_menu.prepend(menu_group)
    install_ctx_object_menu()
    bpy.types.VIEW3D_MT_edit_mesh_context_menu.append(menu_ctx_extra)
    bpy.types.VIEW3D_MT_object.append(menu_group)
    _GROUP_SEL["on"] = True
    _CLIP["alive"] = True
    _GROUP_SEL["last"] = set()
    try:
        bpy.app.timers.register(_group_select_tick, first_interval=0.5, persistent=True)
    except (RuntimeError, ValueError):
        pass
    if _on_depsgraph_update not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph_update)
    if _on_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load_post)
    for hl in (bpy.app.handlers.undo_post, bpy.app.handlers.redo_post):
        if _on_undo_redo not in hl:
            hl.append(_on_undo_redo)
    if _on_load_clear not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load_clear)
    try:
        bpy.app.timers.register(_apply_dimension_settings, first_interval=0.5)  # après l'activation (données accessibles)
    except (RuntimeError, ValueError):
        pass
    fallbacks = {"move": "ops.transform.translate", "copy": "ops.transform.translate",
                 "rotate": "ops.transform.rotate", "scale": "ops.transform.resize",
                 "plane": "ops.mesh.primitive_plane_add_gizmo", "polyline": "ops.gpencil.draw"}
    for cls, kind, _sep in TOOL_ORDER:
        cls.bl_icon = ensure_icon(kind, fallbacks.get(kind, "ops.generic.select_box"))
    for _grp in _SUBD_OBJ_LIST + _SUBD_EDIT_LIST:
        for _c in _grp:
            _c.bl_icon = ensure_icon(_c.dessin_icon, "ops.generic.select_box")
    for _grp in RHINO_TOOLS.values():
        for _c in _grp:
            _c.bl_icon = ensure_icon(_c.dessin_icon, "ops.generic.select_box")
    DESSIN_TT_selection_boite.bl_icon = ensure_icon("select", "ops.generic.select_box")
    DESSIN_TT_selection_rect.bl_icon = ensure_icon("sel_box", "ops.generic.select_box")
    DESSIN_TT_selection_cercle.bl_icon = ensure_icon("sel_circle", "ops.generic.select_circle")
    DESSIN_TT_offset_surface.bl_icon = ensure_icon("offset_srf", "ops.generic.select_box")
    DESSIN_TT_trim.bl_icon = ensure_icon("trim", "ops.generic.select_box")
    DESSIN_TT_join.bl_icon = ensure_icon("join", "ops.generic.select_box")
    DESSIN_TT_explode.bl_icon = ensure_icon("explode", "ops.generic.select_box")
    DESSIN_TT_align.bl_icon = ensure_icon("align", "ops.generic.select_box")
    DESSIN_TT_revolve.bl_icon = ensure_icon("revolve", "ops.generic.select_box")
    DESSIN_TT_loft.bl_icon = ensure_icon("loft", "ops.generic.select_box")
    DESSIN_TT_sweep1.bl_icon = ensure_icon("sweep", "ops.generic.select_box")
    DESSIN_TT_sweep2.bl_icon = ensure_icon("sweep2", "ops.generic.select_box")
    DESSIN_TT_extrude_path.bl_icon = ensure_icon("extrude_path", "ops.generic.select_box")
    DESSIN_TT_make2d.bl_icon = ensure_icon("make2d", "ops.generic.select_box")
    DESSIN_TT_light_point.bl_icon = ensure_icon("light_point", "ops.generic.select_box")
    DESSIN_TT_light_spot.bl_icon = ensure_icon("light_spot", "ops.generic.select_box")
    DESSIN_TT_light_sun.bl_icon = ensure_icon("light_sun", "ops.generic.select_box")
    DESSIN_TT_light_area.bl_icon = ensure_icon("light_area", "ops.generic.select_box")
    DESSIN_TT_camera.bl_icon = ensure_icon("camera", "ops.generic.select_box")
    DESSIN_TT_camera_target.bl_icon = ensure_icon("camera_target", "ops.generic.select_box")
    DESSIN_TT_extrude.bl_icon = ensure_icon("extrude", "ops.mesh.extrude_region_move")
    DESSIN_TT_extrude_crv.bl_icon = ensure_icon("extrude", "ops.mesh.extrude_region_move")
    DESSIN_TT_extrude_srf.bl_icon = ensure_icon("extrude", "ops.mesh.extrude_region_move")
    DESSIN_TT_planar_srf.bl_icon = ensure_icon("planar_srf", "ops.generic.select_box")
    DESSIN_TT_hatch.bl_icon = ensure_icon("hatch", "ops.generic.select_box")
    DESSIN_TT_block.bl_icon = ensure_icon("block", "ops.generic.select_box")
    DESSIN_TT_block_insert.bl_icon = ensure_icon("block_insert", "ops.generic.select_box")
    for _c, _k in ((DESSIN_TT_blend_crv, "blend_crv"), (DESSIN_TT_match_crv, "match_crv"), (DESSIN_TT_rebuild_crv, "rebuild_crv"),
                   (DESSIN_TT_simplify_crv, "simplify_crv"), (DESSIN_TT_change_degree, "change_degree"),
                   (DESSIN_TT_insert_point, "insert_point"), (DESSIN_TT_remove_point, "remove_point")):
        _c.bl_icon = ensure_icon(_k, "ops.generic.select_box")
    DESSIN_TT_untrim.bl_icon = ensure_icon("untrim", "ops.generic.select_box")
    DESSIN_TT_untrim_holes.bl_icon = ensure_icon("untrim_holes", "ops.generic.select_box")
    for _c, _k in ((DESSIN_TT_network_srf, "network_srf"), (DESSIN_TT_fillet_srf, "fillet_srf"), (DESSIN_TT_chamfer_srf, "chamfer_srf"),
                   (DESSIN_TT_extend_srf, "extend_srf"), (DESSIN_TT_split_iso, "split_iso")):
        _c.bl_icon = ensure_icon(_k, "ops.generic.select_box")
    DESSIN_TT_hatch_region.bl_icon = ensure_icon("hatch_region", "ops.generic.select_box")
    DESSIN_TT_edge_srf.bl_icon = ensure_icon("edge_srf", "ops.generic.select_box")
    DESSIN_TT_thicken.bl_icon = ensure_icon("thicken", "ops.generic.select_box")
    DESSIN_TT_blend_srf.bl_icon = ensure_icon("blend_srf", "ops.generic.select_box")
    DESSIN_TT_match_srf.bl_icon = ensure_icon("match_srf", "ops.generic.select_box")
    DESSIN_TT_rail_revolve.bl_icon = ensure_icon("rail_revolve", "ops.generic.select_box")
    DESSIN_TT_shell.bl_icon = ensure_icon("shell", "ops.generic.select_box")
    DESSIN_TT_cap.bl_icon = ensure_icon("cap", "ops.generic.select_box")
    DESSIN_TT_split_face.bl_icon = ensure_icon("split_face", "ops.generic.select_box")
    DESSIN_TT_project_curve.bl_icon = ensure_icon("project_curve", "ops.generic.select_box")
    DESSIN_TT_patch.bl_icon = ensure_icon("patch", "ops.generic.select_box")
    DESSIN_TT_stretch.bl_icon = ensure_icon("stretch", "ops.generic.select_box")
    DESSIN_TT_divide.bl_icon = ensure_icon("divide", "ops.generic.select_box")
    DESSIN_TT_overkill.bl_icon = ensure_icon("overkill", "ops.generic.select_box")
    DESSIN_TT_fillet_c.bl_icon = ensure_icon("fillet_c", "ops.generic.select_box")
    DESSIN_TT_chamfer_c.bl_icon = ensure_icon("chamfer_c", "ops.generic.select_box")
    DESSIN_TT_clip_plane.bl_icon = ensure_icon("clip_plane", "ops.generic.select_box")
    DESSIN_TT_selection_lasso.bl_icon = ensure_icon("lasso", "ops.generic.select_lasso")

    add_grs_to_tool_keymaps([t[0] for t in TOOL_ORDER] + [DESSIN_TT_selection_lasso, DESSIN_TT_selection_boite, DESSIN_TT_selection_rect, DESSIN_TT_selection_cercle,
                                                           DESSIN_TT_offset_surface, DESSIN_TT_trim, DESSIN_TT_extrude, DESSIN_TT_extrude_crv, DESSIN_TT_extrude_srf,
                                                           DESSIN_TT_planar_srf, DESSIN_TT_edge_srf, DESSIN_TT_thicken, DESSIN_TT_cap, DESSIN_TT_split_face, DESSIN_TT_project_curve, DESSIN_TT_patch,
                                                           DESSIN_TT_stretch, DESSIN_TT_divide, DESSIN_TT_overkill, DESSIN_TT_fillet_c, DESSIN_TT_chamfer_c, DESSIN_TT_clip_plane,
                                                           DESSIN_TT_blend_srf, DESSIN_TT_match_srf, DESSIN_TT_rail_revolve, DESSIN_TT_shell,
                                                           DESSIN_TT_join, DESSIN_TT_explode,
                                                           DESSIN_TT_align, DESSIN_TT_revolve, DESSIN_TT_loft, DESSIN_TT_sweep1, DESSIN_TT_sweep2, DESSIN_TT_make2d,
                                                           DESSIN_TT_light_point, DESSIN_TT_light_spot, DESSIN_TT_light_sun,
                                                           DESSIN_TT_light_area, DESSIN_TT_camera, DESSIN_TT_camera_target]
                            # tous les autres outils aussi (SubD, Text, DIST, ID...) : G / R / S se comportent partout de la même façon
                            + [c for n, c in sorted(addon_globals().items()) if n.startswith("DESSIN_TT_") and isinstance(c, type)
                               and issubclass(c, bpy.types.WorkSpaceTool)]
                            + [c for grp in _SUBD_OBJ_LIST + _SUBD_EDIT_LIST for c in grp])
    _EDIT_TOOLS.clear()
    for cls in [t[0] for t in TOOL_ORDER] + [DESSIN_TT_selection_lasso, DESSIN_TT_selection_boite, DESSIN_TT_selection_rect, DESSIN_TT_selection_cercle]:
        # même outil en mode édition (maillage) : sous-classe ordinaire, pas une classe Blender enregistrée
        _EDIT_TOOLS.append(type(cls.__name__ + "_edit", (cls,), {"bl_context_mode": 'EDIT_MESH'}))

    def register_set(mode, selection_cls, lasso_cls, chain, extra=()):
        # Select / Move et Lasso juste sous l'outil « Transform » de Blender, puis nos outils après un séparateur
        head = []
        if selection_cls is not None:
            lasso_cls._in_group = True        # Select / Move, Select Box, Select Circle et Lasso partagent un menu déroulant
            head = [(selection_cls, False)] + [(c, False) for c in extra] + [(lasso_cls, False)]
        for cls, _sep in head + list(chain):
            bpy.utils.register_tool(cls, after={"builtin.transform"}, separator=False, group=False)
        _arrange_tools(mode, list(chain), head)

    _names = [t[0] for t in TOOL_ORDER]
    def _between(first, last):
        return _names[_names.index(first):_names.index(last) + 1]
    _groups = [
        _between(DESSIN_TT_polyligne, DESSIN_TT_arc_3pts) + [DESSIN_TT_project_curve, DESSIN_TT_blend_crv, DESSIN_TT_match_crv,
            DESSIN_TT_rebuild_crv, DESSIN_TT_simplify_crv, DESSIN_TT_change_degree, DESSIN_TT_insert_point, DESSIN_TT_remove_point],                   # courbes
        _between(DESSIN_TT_deplacer, DESSIN_TT_array_polar) + [DESSIN_TT_align, DESSIN_TT_stretch],                     # transformer
        [DESSIN_TT_join, DESSIN_TT_explode, DESSIN_TT_trim, DESSIN_TT_cut, DESSIN_TT_divide, DESSIN_TT_overkill, DESSIN_TT_split_face, DESSIN_TT_fillet_c, DESSIN_TT_chamfer_c] + _between(DESSIN_TT_bool_union, DESSIN_TT_chamfer)
            + [DESSIN_TT_offset_surface, DESSIN_TT_offset, DESSIN_TT_block, DESSIN_TT_block_insert],  # modifier, blocs
        [DESSIN_TT_plan, DESSIN_TT_srf_corners, DESSIN_TT_planar_srf, DESSIN_TT_edge_srf, DESSIN_TT_network_srf, DESSIN_TT_patch, DESSIN_TT_extrude_crv, DESSIN_TT_extrude_srf, DESSIN_TT_extrude_path, DESSIN_TT_revolve,
         DESSIN_TT_rail_revolve, DESSIN_TT_loft, DESSIN_TT_sweep1, DESSIN_TT_sweep2],                                  # surfaces
        [DESSIN_TT_blend_srf, DESSIN_TT_match_srf, DESSIN_TT_fillet_srf, DESSIN_TT_chamfer_srf, DESSIN_TT_extend_srf, DESSIN_TT_split_iso,
         DESSIN_TT_untrim, DESSIN_TT_untrim_holes, DESSIN_TT_thicken, DESSIN_TT_cap, DESSIN_TT_shell],  # édition de surfaces
        _between(DESSIN_TT_boite, DESSIN_TT_tore),                                                  # solides
        _between(DESSIN_TT_subd_box, DESSIN_TT_subd_plane),                                         # SubD
        [DESSIN_TT_light_point, DESSIN_TT_light_spot, DESSIN_TT_light_sun, DESSIN_TT_light_area,
         DESSIN_TT_camera, DESSIN_TT_camera_target],                                                # lumières / caméras
        [DESSIN_TT_cotation, DESSIN_TT_cotation_chain, DESSIN_TT_cotation_ordinate, DESSIN_TT_cotation_arc, DESSIN_TT_cotation_rayon, DESSIN_TT_cotation_angle, DESSIN_TT_annotation, DESSIN_TT_text, DESSIN_TT_center_mark, DESSIN_TT_cotation_edit, DESSIN_TT_hatch, DESSIN_TT_hatch_region, DESSIN_TT_mesure_aire, DESSIN_TT_dist, DESSIN_TT_id_point, DESSIN_TT_make2d, DESSIN_TT_clip_plane],    # annotation
    ]
    for _gi, _fk in ((0, "curves"), (1, "transform"), (2, "modify"), (4, "srf_edit"), (5, "solids")):
        _groups[_gi] = list(_groups[_gi]) + RHINO_TOOLS[_fk]
    obj_chain = []
    for g in _groups:
        for i, c in enumerate(g):
            obj_chain.append((c, i == 0))
    _edit_of = dict(zip(_names, _EDIT_TOOLS[:-4]))
    _edit_extra = []
    for c, _s in obj_chain:
        if c not in _edit_of and c is not DESSIN_TT_extrude:
            _ev = _edit_variant(c)
            _edit_of[c] = _ev
            _edit_extra.append(_ev)
    edit_chain = [(_edit_of[c], sep) for c, sep in obj_chain if c in _edit_of]
    # commandes SubD : après les primitives SubD (outils propres au mode Objet / au mode Édition)
    _ko = [c for c, _s in obj_chain].index(DESSIN_TT_subd_plane) + 1
    obj_chain[_ko:_ko] = [(c, i == 0 and gi == 0) for gi, grp in enumerate(_SUBD_OBJ_LIST) for i, c in enumerate(grp)]
    _ke = [c for c, _s in edit_chain].index(_edit_of[DESSIN_TT_subd_plane]) + 1
    _sub_edit = [(c, i == 0 and gi == 0) for gi, grp in enumerate(_SUBD_EDIT_LIST) for i, c in enumerate(grp)]
    edit_chain[_ke:_ke] = _sub_edit
    k_mir = [c for c, _s in edit_chain].index(_edit_of[DESSIN_TT_miroir]) + 1
    edit_chain.insert(k_mir, (DESSIN_TT_extrude, False))            # Extrude : mode édition seulement
    register_set('OBJECT', DESSIN_TT_selection_boite, DESSIN_TT_selection_lasso, obj_chain, extra=(DESSIN_TT_selection_rect, DESSIN_TT_selection_cercle))
    register_set('EDIT_MESH', _EDIT_TOOLS[-3], _EDIT_TOOLS[-4], edit_chain, extra=(_EDIT_TOOLS[-2], _EDIT_TOOLS[-1]))
    _EDIT_TOOLS.append(DESSIN_TT_extrude)
    _EDIT_TOOLS.extend(_edit_extra)
    _EDIT_TOOLS.extend(c for c, _s in _sub_edit)
    # mode édition d'une courbe : outils de courbe, de transformation, de modification et de surfaces (ils quittent l'édition puis se lancent)
    def _crv_select_keymap(select_op):
        km = [("dessin.bar_click", {"type": 'LEFTMOUSE', "value": 'PRESS'}, None),
              ("view3d.select", {"type": 'LEFTMOUSE', "value": 'PRESS'}, {"properties": [("deselect_all", True)]}),
              ("view3d.select", {"type": 'LEFTMOUSE', "value": 'PRESS', "shift": True}, {"properties": [("toggle", True)]})]
        for mods, mode in (({}, 'SET'), ({"shift": True}, 'ADD'), ({"ctrl": True}, 'SUB')):
            km.append((select_op, dict({"type": 'LEFTMOUSE', "value": 'CLICK_DRAG'}, **mods), {"properties": [("mode", mode)]}))
        km.append(("dessin.deselect", {"type": 'ESC', "value": 'PRESS'}, None))
        return tuple(km)
    sel_crv = type("DESSIN_TT_selection_boite_crv", (DESSIN_TT_selection_boite,),
                   {"bl_context_mode": 'EDIT_CURVE', "bl_keymap": _crv_select_keymap("view3d.select_box")})
    lasso_crv = type("DESSIN_TT_selection_lasso_crv", (DESSIN_TT_selection_lasso,),
                     {"bl_context_mode": 'EDIT_CURVE', "bl_keymap": _crv_select_keymap("view3d.select_lasso")})
    circ_crv = type("DESSIN_TT_selection_cercle_crv", (DESSIN_TT_selection_cercle,),
                    {"bl_context_mode": 'EDIT_CURVE', "bl_keymap": _crv_select_keymap("view3d.select_circle")})
    _EDIT_TOOLS.extend([lasso_crv, sel_crv, circ_crv])
    crv_chain = []
    for g in _groups[:4] + _groups[-1:]:
        for i, c in enumerate(g):
            crv = _edit_variant(c, 'EDIT_CURVE')
            _EDIT_TOOLS.append(crv)
            crv_chain.append((crv, i == 0))
    try:
        register_set('EDIT_CURVE', sel_crv, lasso_crv, crv_chain, extra=(circ_crv,))
    except (KeyError, ValueError, RuntimeError, AttributeError):
        pass
    for mode in ('OBJECT', 'EDIT_MESH', 'EDIT_CURVE'):
        _flatten_singletons(mode)
    _hide_native_tools()
    _install_toolbar_filter()
    register_shortcuts()
    register_grs_keymap()
    apply_nav_inputs()
    register_view_keymap()
    register_cmd_keymap()
    register_mouse_track()
    register_sel_filter_keys()
    if _CMD["handle"] is None:
        _CMD["handle"] = bpy.types.SpaceView3D.draw_handler_add(cmd_bar_cb, (), 'WINDOW', 'POST_PIXEL')
    if _VBAR["handle"] is None:
        _VBAR["handle"] = bpy.types.SpaceView3D.draw_handler_add(views_bar_cb, (), 'WINDOW', 'POST_PIXEL')
    if _EXT_BALL["handle"] is None:
        _EXT_BALL["handle"] = bpy.types.SpaceView3D.draw_handler_add(draw_extrude_ball, (), 'WINDOW', 'POST_PIXEL')
    if _TRIM_HL["handle"] is None:
        _TRIM_HL["handle"] = bpy.types.SpaceView3D.draw_handler_add(trim_highlight_cb, (), 'WINDOW', 'POST_VIEW')
    if _SHOWEDGES["handle"] is None:
        _SHOWEDGES["handle"] = bpy.types.SpaceView3D.draw_handler_add(showedges_cb, (), 'WINDOW', 'POST_VIEW')
    if _CURVE_PTS["handle"] is None:
        _CURVE_PTS["handle"] = bpy.types.SpaceView3D.draw_handler_add(curve_points_cb, (), 'WINDOW', 'POST_VIEW')
    if _CP_DRAW["handle"] is None:
        _CP_DRAW["handle"] = bpy.types.SpaceView3D.draw_handler_add(cplane_draw_cb, (), 'WINDOW', 'POST_VIEW')
    if not bpy.app.timers.is_registered(autocp_timer):
        bpy.app.timers.register(autocp_timer, first_interval=0.5, persistent=True)


def unregister():
    unregister_shortcuts()
    unregister_grs_keymap()
    unregister_view_keymap()
    unregister_cmd_keymap()
    unregister_mouse_track()
    unregister_sel_filter_keys()
    if _CMD["handle"] is not None:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(_CMD["handle"], 'WINDOW')
        except (ValueError, RuntimeError):
            pass
        _CMD["handle"] = None
    if _VBAR["handle"] is not None:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(_VBAR["handle"], 'WINDOW')
        except (ValueError, RuntimeError):
            pass
        _VBAR["handle"] = None
    _VBAR["hit"].clear()
    _CMD["prompt"].clear()
    _CMD["hit"].clear()
    _CMD["op"].clear()
    _CMD["mouse"].clear()
    _CMD["cleared"].clear()
    _CMD["input"] = None
    if _EXT_BALL["handle"] is not None:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(_EXT_BALL["handle"], 'WINDOW')
        except (ValueError, RuntimeError):
            pass
        _EXT_BALL["handle"] = None
    if _TRIM_HL["handle"] is not None:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(_TRIM_HL["handle"], 'WINDOW')
        except (ValueError, RuntimeError):
            pass
        _TRIM_HL["handle"] = None
    if _SHOWEDGES["handle"] is not None:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(_SHOWEDGES["handle"], 'WINDOW')
        except (ValueError, RuntimeError):
            pass
        _SHOWEDGES["handle"] = None
    _SHOWEDGES["on"] = False
    if _CURVE_PTS["handle"] is not None:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(_CURVE_PTS["handle"], 'WINDOW')
        except (ValueError, RuntimeError):
            pass
        _CURVE_PTS["handle"] = None
    if _CP_DRAW["handle"] is not None:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(_CP_DRAW["handle"], 'WINDOW')
        except (ValueError, RuntimeError):
            pass
        _CP_DRAW["handle"] = None
    if bpy.app.timers.is_registered(autocp_timer):
        bpy.app.timers.unregister(autocp_timer)
    _LOD["pending"] = None
    if bpy.app.timers.is_registered(_lod_timer):
        bpy.app.timers.unregister(_lod_timer)
    _AUTOCP["sig"].clear()
    CPLANES.clear()
    _CPLANE["cur"] = None
    _remove_toolbar_filter()
    _restore_native_tools()
    _CLIP["alive"] = False
    sel_filter_restore()
    clear_clip_planes()
    if _on_depsgraph_update in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph_update)
    if _on_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load_post)
    for hl in (bpy.app.handlers.undo_post, bpy.app.handlers.redo_post):
        if _on_undo_redo in hl:
            hl.remove(_on_undo_redo)
    if _on_load_clear in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load_clear)
    _perf_caches_clear()
    for c in reversed(_EDIT_TOOLS):
        bpy.utils.unregister_tool(c)
    _EDIT_TOOLS.clear()
    for _grp in _SUBD_OBJ_LIST:
        for _c in _grp:
            try:
                bpy.utils.unregister_tool(_c)
            except (RuntimeError, ValueError, KeyError):
                pass
    bpy.utils.unregister_tool(DESSIN_TT_offset_surface)
    bpy.utils.unregister_tool(DESSIN_TT_trim)
    bpy.utils.unregister_tool(DESSIN_TT_join)
    bpy.utils.unregister_tool(DESSIN_TT_explode)
    bpy.utils.unregister_tool(DESSIN_TT_align)
    bpy.utils.unregister_tool(DESSIN_TT_extrude_crv)
    bpy.utils.unregister_tool(DESSIN_TT_extrude_srf)
    for _c in (DESSIN_TT_planar_srf, DESSIN_TT_edge_srf, DESSIN_TT_thicken, DESSIN_TT_cap, DESSIN_TT_split_face, DESSIN_TT_project_curve, DESSIN_TT_patch,
               DESSIN_TT_stretch, DESSIN_TT_divide, DESSIN_TT_overkill, DESSIN_TT_fillet_c, DESSIN_TT_chamfer_c, DESSIN_TT_blend_srf, DESSIN_TT_match_srf, DESSIN_TT_rail_revolve, DESSIN_TT_shell,
               DESSIN_TT_hatch, DESSIN_TT_hatch_region, DESSIN_TT_network_srf, DESSIN_TT_fillet_srf, DESSIN_TT_chamfer_srf,
               DESSIN_TT_extend_srf, DESSIN_TT_split_iso, DESSIN_TT_blend_crv, DESSIN_TT_match_crv, DESSIN_TT_rebuild_crv,
               DESSIN_TT_simplify_crv, DESSIN_TT_change_degree, DESSIN_TT_insert_point, DESSIN_TT_remove_point,
               DESSIN_TT_block, DESSIN_TT_block_insert, DESSIN_TT_untrim, DESSIN_TT_untrim_holes):
        bpy.utils.unregister_tool(_c)
    for _g in RHINO_TOOLS.values():
        for _c in _g:
            try:
                bpy.utils.unregister_tool(_c)
            except (RuntimeError, ValueError, KeyError):
                pass
    bpy.utils.unregister_tool(DESSIN_TT_revolve)
    bpy.utils.unregister_tool(DESSIN_TT_loft)
    bpy.utils.unregister_tool(DESSIN_TT_sweep1)
    bpy.utils.unregister_tool(DESSIN_TT_sweep2)
    bpy.utils.unregister_tool(DESSIN_TT_extrude_path)
    bpy.utils.unregister_tool(DESSIN_TT_make2d)
    bpy.utils.unregister_tool(DESSIN_TT_clip_plane)
    for _t in (DESSIN_TT_light_point, DESSIN_TT_light_spot, DESSIN_TT_light_sun, DESSIN_TT_light_area, DESSIN_TT_camera, DESSIN_TT_camera_target):
        bpy.utils.unregister_tool(_t)
    for cls, _kind, _sep in reversed(TOOL_ORDER):
        bpy.utils.unregister_tool(cls)
    bpy.utils.unregister_tool(DESSIN_TT_selection_lasso)
    bpy.utils.unregister_tool(DESSIN_TT_selection_cercle)
    bpy.utils.unregister_tool(DESSIN_TT_selection_rect)
    bpy.utils.unregister_tool(DESSIN_TT_selection_boite)
    for mode in ('OBJECT', 'EDIT_MESH'):
        _tidy_separators(mode)
    _GROUP_SEL["on"] = False
    uninstall_ctx_object_menu()
    for menu, fn in ((bpy.types.VIEW3D_MT_object_context_menu, menu_group), (bpy.types.VIEW3D_MT_object, menu_group),
                     (bpy.types.VIEW3D_MT_edit_mesh_context_menu, menu_ctx_extra)):
        try:
            menu.remove(fn)
        except (ValueError, RuntimeError):
            pass
    bpy.types.VIEW3D_MT_add.remove(menu_add)
    try:
        bpy.types.UI_MT_button_context_menu.remove(layer_button_menu)
    except (ValueError, RuntimeError):
        pass
    try:
        bpy.types.TOPBAR_MT_file_import.remove(menu_import_cad)
    except (ValueError, RuntimeError):
        pass
    for _menu, _fn in ((bpy.types.UI_MT_button_context_menu, named_view_button_menu),
                       (bpy.types.STATUSBAR_HT_header, statusbar_osnap)):
        try:
            _menu.remove(_fn)
        except (ValueError, RuntimeError):
            pass
    del bpy.types.Scene.dessin_view_labels
    del bpy.types.Scene.dessin_view_tabs
    del bpy.types.Scene.dessin_views
    del bpy.types.Scene.dessin
    try:
        del bpy.types.Object.dessin_hatch
        del bpy.types.Object.dessin_dim
    except AttributeError:
        pass
    del bpy.types.Collection.dessin_layer
    for c in reversed(classes):
        bpy.utils.unregister_class(c)


def _late_imports():
    pass
