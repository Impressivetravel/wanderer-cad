"""Wanderer CAD : Vues nommées."""

import bpy
import time

from .core import pref, tr_label
from .navigation import BASE_VIEWS, _axis_quat, detect_axis


class DESSIN_PG_view(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty()
    base: bpy.props.BoolProperty(description="Replaces one of the standard views (Top, Front...)")
    full: bpy.props.BoolProperty(description="Also stores the position and the distance")
    pinned: bpy.props.BoolProperty(default=True, description="Shown as a tab in the viewport header")
    rot: bpy.props.FloatVectorProperty(size=4, subtype='QUATERNION', default=(1.0, 0.0, 0.0, 0.0))
    loc: bpy.props.FloatVectorProperty(size=3, subtype='TRANSLATION')
    dist: bpy.props.FloatProperty(default=10.0)
    persp: bpy.props.BoolProperty(default=True)
    lens: bpy.props.FloatProperty(default=50.0)
    has_shading: bpy.props.BoolProperty(description="Also stores the display mode (Wireframe / Solid / X-Ray...)")
    shade_type: bpy.props.StringProperty(default='SOLID')
    xray: bpy.props.BoolProperty()
    xray_wire: bpy.props.BoolProperty(default=True)
    xray_alpha: bpy.props.FloatProperty(default=0.5)
    xray_alpha_wire: bpy.props.FloatProperty(default=0.0)


def base_labels(scene):
    """Noms affichés des vues de base renommées (Top -> Plan...)."""
    out = {}
    for line in scene.dessin_view_labels.split("\n"):
        key, _sep, label = line.partition("|")
        if key and label:
            out[key] = label
    return out


def view_label(scene, name):
    return base_labels(scene).get(name, tr_label(name))


def set_base_label(scene, name, label):
    labels = base_labels(scene)
    if label and label != name:
        labels[name] = label
    else:
        labels.pop(name, None)
    scene.dessin_view_labels = "\n".join(f"{k}|{v}" for k, v in labels.items())


def find_view(scene, name, base=None):
    for v in scene.dessin_views:
        if v.name == name and (base is None or v.base == base):
            return v
    return None


def unique_view_name(scene, name):
    taken = {v.name for v in scene.dessin_views} | {n for n, _a in BASE_VIEWS}
    if name not in taken:
        return name
    k = 2
    stem = name.rstrip("0123456789 ") or name
    while f"{stem} {k}" in taken:
        k += 1
    return f"{stem} {k}"


def view3d_targets(context):
    """(space, rv3d, region WINDOW) du viewport sous le menu (le menu est dans l'en-tête : pas de region_data)."""
    area = context.area
    if area is None or area.type != 'VIEW_3D':
        return None, None, None
    space = area.spaces.active
    region = next((r for r in area.regions if r.type == 'WINDOW'), None)
    return space, getattr(space, "region_3d", None), region


def store_view(entry, rv3d, space):
    entry.rot = tuple(rv3d.view_rotation)
    entry.loc = tuple(rv3d.view_location)
    entry.dist = rv3d.view_distance
    entry.persp = rv3d.view_perspective != 'ORTHO'
    entry.lens = space.lens
    entry.full = True
    sh = space.shading                      # mode d'affichage du viewport (Filaire, Solide, X-Ray...)
    entry.shade_type, entry.xray, entry.xray_wire = sh.type, sh.show_xray, sh.show_xray_wireframe
    entry.xray_alpha, entry.xray_alpha_wire = sh.xray_alpha, sh.xray_alpha_wireframe
    entry.has_shading = True


def entry_shading(entry):
    if entry is None or not entry.has_shading:
        return None
    return (entry.shade_type, entry.xray, entry.xray_wire, entry.xray_alpha, entry.xray_alpha_wire)


def apply_view(context, rot, axis, full, loc, dist, persp, lens, shading=None):
    space, rv3d, region = view3d_targets(context)
    if rv3d is None:
        return False
    if rv3d.view_perspective == 'CAMERA':
        rv3d.view_perspective = 'PERSP'
    if axis:      # vue alignée : passe par l'opérateur de Blender (les autres outils savent alors qu'on est en vue Face / Dessus...)
        view = context.preferences.view
        smooth = view.smooth_view
        view.smooth_view = 0
        try:
            with context.temp_override(area=context.area, region=region, space_data=space):
                bpy.ops.view3d.view_axis(type=axis)
        except RuntimeError:
            rv3d.view_rotation = rot
        finally:
            view.smooth_view = smooth
    else:
        rv3d.view_rotation = rot
    if full:
        rv3d.view_location = loc
        rv3d.view_distance = dist
    rv3d.view_perspective = 'PERSP' if persp else 'ORTHO'
    if persp and lens:
        space.lens = lens
    if shading is not None:
        sh = space.shading
        try:
            sh.type = shading[0]
            sh.show_xray, sh.show_xray_wireframe = shading[1], shading[2]
            sh.xray_alpha, sh.xray_alpha_wireframe = shading[3], shading[4]
        except (TypeError, ValueError):
            pass
    return True


class NamedViewOp:
    bl_options = {'INTERNAL'}
    name: bpy.props.StringProperty(options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.scene is not None


_LAST_TAB = {"name": None, "time": 0.0}


class DESSIN_OT_view_restore(NamedViewOp, bpy.types.Operator):
    bl_idname = "dessin.view_restore"
    bl_label = "Restore Named View"
    bl_description = "Restores this view in the viewport. Double-click a tab to rename it, right-click for more"

    def invoke(self, context, event):
        if is_layout(context.scene):
            return self.execute(context)
        now = time.monotonic()
        double = _LAST_TAB["name"] == self.name and now - _LAST_TAB["time"] < 0.45
        _LAST_TAB["name"], _LAST_TAB["time"] = self.name, now
        if double or (event is not None and event.ctrl):       # double clic ou Ctrl + clic : renommer
            _LAST_TAB["name"] = None
            return bpy.ops.dessin.view_rename('INVOKE_DEFAULT', name=self.name)      # double clic : renommer
        return self.execute(context)

    def execute(self, context):
        came_from_layout = is_layout(context.scene)
        if came_from_layout:
            layout_close(context)                     # une vue du modèle demandée depuis une mise en page : retour au modèle
        scene = context.scene
        leaving = current_view_name(context)
        if leaving == self.name and not came_from_layout:
            return {'FINISHED'}                       # déjà dans cette vue : elle reste telle quelle
        if leaving:
            save_into_view(context, leaving)          # la vue quittée garde son dernier cadrage et son affichage
        entry = find_view(scene, self.name)
        base_axis = dict(BASE_VIEWS).get(self.name, "?")
        if entry is not None:
            rot, full, loc, dist, persp, lens = Quaternion_(entry.rot), entry.full, entry.loc, entry.dist, entry.persp, entry.lens
            axis = None if persp else detect_axis(rot)      # vue orthographique alignée : vraie vue Face / Dessus...
        elif base_axis != "?":
            axis, rot, full, loc, dist, persp, lens = base_axis, _axis_quat(base_axis), False, (0, 0, 0), 0.0, base_axis is None, 0.0
        else:
            self.report({'WARNING'}, f"View '{self.name}' not found")
            return {'CANCELLED'}
        if not apply_view(context, rot, axis, full, loc, dist, persp, lens, entry_shading(entry)):
            self.report({'WARNING'}, "No 3D viewport")
            return {'CANCELLED'}
        _VIEW_OF_AREA[context.area.as_pointer()] = self.name
        if self.name not in tab_names(scene):         # une vue choisie dans le menu « + » devient un onglet
            bpy.ops.dessin.view_pin(name=self.name)
        return {'FINISHED'}


def Quaternion_(q):
    from mathutils import Quaternion
    return Quaternion(q)


class DESSIN_OT_view_save(NamedViewOp, bpy.types.Operator):
    bl_idname = "dessin.view_save"
    bl_label = "Save Current View"
    bl_description = "Saves the current view under a name"

    def invoke(self, context, event):
        self.name = unique_view_name(context.scene, "View")
        return context.window_manager.invoke_props_dialog(self, width=260)

    def draw(self, context):
        self.layout.prop(self, "name", text="Name")

    def execute(self, context):
        space, rv3d, _r = view3d_targets(context)
        if rv3d is None:
            self.report({'WARNING'}, "No 3D viewport")
            return {'CANCELLED'}
        entry = context.scene.dessin_views.add()
        entry.name = unique_view_name(context.scene, self.name.strip() or "View")
        store_view(entry, rv3d, space)
        return {'FINISHED'}


class DESSIN_OT_view_update(NamedViewOp, bpy.types.Operator):
    bl_idname = "dessin.view_update"
    bl_label = "Update Named View"
    bl_description = "Replaces this view with the current view"

    def execute(self, context):
        space, rv3d, _r = view3d_targets(context)
        if rv3d is None:
            self.report({'WARNING'}, "No 3D viewport")
            return {'CANCELLED'}
        entry = find_view(context.scene, self.name)
        if entry is None:
            if self.name not in dict(BASE_VIEWS):
                return {'CANCELLED'}
            entry = context.scene.dessin_views.add()
            entry.name = self.name
            entry.base = True
        store_view(entry, rv3d, space)
        return {'FINISHED'}


class DESSIN_OT_view_duplicate(NamedViewOp, bpy.types.Operator):
    bl_idname = "dessin.view_duplicate"
    bl_label = "Duplicate Named View"
    bl_description = "Makes a copy of this view that you can then adjust"

    def execute(self, context):
        scene = context.scene
        src = find_view(scene, self.name)
        new = scene.dessin_views.add()
        new.name = unique_view_name(scene, f"{self.name} 2")
        if src is not None:
            for key in ("rot", "loc", "dist", "persp", "lens", "full", "has_shading", "shade_type", "xray", "xray_wire",
                        "xray_alpha", "xray_alpha_wire"):
                setattr(new, key, getattr(src, key))
        else:
            axis = dict(BASE_VIEWS).get(self.name)
            new.rot = tuple(_axis_quat(axis))
            new.persp = axis is None
            space, rv3d, _r = view3d_targets(context)
            if rv3d is not None:
                new.loc, new.dist, new.lens, new.full = tuple(rv3d.view_location), rv3d.view_distance, space.lens, True
        new.base = False
        return {'FINISHED'}


class DESSIN_OT_view_rename(NamedViewOp, bpy.types.Operator):
    bl_idname = "dessin.view_rename"
    bl_label = "Rename Named View"
    bl_description = "Renames this view"

    new_name: bpy.props.StringProperty(name="Name")

    def invoke(self, context, event):
        self.new_name = view_label(context.scene, self.name)
        return context.window_manager.invoke_props_dialog(self, width=260)

    def draw(self, context):
        self.layout.prop(self, "new_name", text="Name")

    def execute(self, context):
        scene = context.scene
        new = self.new_name.strip()
        if not new:
            return {'CANCELLED'}
        entry = find_view(scene, self.name, base=False)
        if entry is not None:
            if new != entry.name:
                entry.name = unique_view_name(scene, new)
            return {'FINISHED'}
        if self.name in dict(BASE_VIEWS):          # vue de base : seul le nom affiché change
            set_base_label(scene, self.name, new)
            return {'FINISHED'}
        return {'CANCELLED'}


class DESSIN_OT_view_delete(NamedViewOp, bpy.types.Operator):
    bl_idname = "dessin.view_delete"
    bl_label = "Delete Named View"
    bl_description = "Deletes this view (a standard view goes back to its default)"

    def execute(self, context):
        views = context.scene.dessin_views
        if self.name in dict(BASE_VIEWS):
            set_base_label(context.scene, self.name, "")
        for k, v in enumerate(views):
            if v.name == self.name:
                views.remove(k)
                return {'FINISHED'}
        return {'FINISHED'} if self.name in dict(BASE_VIEWS) else {'CANCELLED'}


class DESSIN_MT_named_views(bpy.types.Menu):
    bl_idname = "DESSIN_MT_named_views"
    bl_label = "Named Views"


    def draw(self, context):
        layout = self.layout
        layout.operator_context = 'INVOKE_DEFAULT'
        scene = model_of(context.scene) or context.scene      # dans une mise en page : les vues de son modèle
        for name, _axis in BASE_VIEWS:
            layout.operator(DESSIN_OT_view_restore.bl_idname, text=view_label(scene, name)).name = name
        users = [v.name for v in scene.dessin_views if not v.base]
        if users:
            layout.separator()
            for name in users:
                layout.operator(DESSIN_OT_view_restore.bl_idname, text=name).name = name
        layout.separator()
        if not is_layout(context.scene):
            layout.operator(DESSIN_OT_view_save.bl_idname, text="New Viewport...", icon='ADD')
        menu_layouts(layout, context)


def tab_names(scene):
    """Noms des vues affichées en onglets : vues de base épinglées, puis les vues de l'utilisateur épinglées."""
    pinned = {n for n in scene.dessin_view_tabs.split(",") if n}
    names = [n for n, _a in BASE_VIEWS if n in pinned]
    names += [v.name for v in scene.dessin_views if not v.base and v.pinned]
    return names


def active_view_name(context):
    """Vue nommée qui correspond à la vue actuelle (sert à allumer l'onglet), sinon « Perspective » en vue libre."""
    space, rv3d, _r = view3d_targets(context)
    if rv3d is None or rv3d.view_perspective == 'CAMERA':
        return None
    persp = rv3d.view_perspective != 'ORTHO'
    rot = rv3d.view_rotation
    for v in context.scene.dessin_views:
        if v.persp != persp or abs(Quaternion_(v.rot).dot(rot)) < 0.9999:
            continue
        if v.full and ((Vector_(v.loc) - rv3d.view_location).length > 1e-3 * max(1.0, v.dist)
                       or abs(v.dist - rv3d.view_distance) > 1e-3 * max(1.0, v.dist)):
            continue
        return v.name
    if persp:
        return "Perspective"
    axis = detect_axis(rot)
    return next((n for n, a in BASE_VIEWS if a == axis), None) if axis else None


_VIEW_OF_AREA = {}   # viewport (pointeur de la zone) -> dernière vue nommée rappelée


def view_belongs(context, name):
    """Le viewport est-il encore « dans » cette vue (même type de projection, même axe) ?"""
    space, rv3d, _r = view3d_targets(context)
    if rv3d is None or rv3d.view_perspective == 'CAMERA':
        return False
    persp = rv3d.view_perspective != 'ORTHO'
    entry = find_view(context.scene, name)
    if entry is not None:
        if entry.persp != persp:
            return False
        return persp or detect_axis(rv3d.view_rotation) == detect_axis(Quaternion_(entry.rot))
    axis = dict(BASE_VIEWS).get(name, "?")
    if axis == "?":
        return False
    return persp if axis is None else (not persp and detect_axis(rv3d.view_rotation) == axis)


def current_view_name(context):
    """Vue nommée dans laquelle se trouve le viewport : la dernière rappelée tant qu'on y est, sinon celle qui correspond."""
    if context.area is not None:
        mem = _VIEW_OF_AREA.get(context.area.as_pointer())
        if mem and view_belongs(context, mem):
            return mem
    return active_view_name(context)


def save_into_view(context, name):
    space, rv3d, _r = view3d_targets(context)
    if rv3d is None:
        return
    entry = find_view(context.scene, name)
    if entry is None:
        if name not in dict(BASE_VIEWS):
            return
        entry = context.scene.dessin_views.add()
        entry.name = name
        entry.base = True
    store_view(entry, rv3d, space)


def Vector_(v):
    from mathutils import Vector
    return Vector(v)


class DESSIN_OT_view_pin(NamedViewOp, bpy.types.Operator):
    bl_idname = "dessin.view_pin"
    bl_label = "Show / Hide Tab"
    bl_description = "Shows or hides this view as a tab in the viewport header"

    def execute(self, context):
        scene = context.scene
        entry = find_view(scene, self.name, base=False)
        if entry is not None:
            entry.pinned = not entry.pinned
            return {'FINISHED'}
        if self.name in dict(BASE_VIEWS):
            tabs = [n for n in scene.dessin_view_tabs.split(",") if n]
            if self.name in tabs:
                tabs.remove(self.name)
            else:
                tabs.append(self.name)
            scene.dessin_view_tabs = ",".join(tabs)
            return {'FINISHED'}
        return {'CANCELLED'}


class DESSIN_PT_named_views(bpy.types.Panel):
    """Le menu des vues dans un popover : le bouton « + » de l'en-tête a ainsi le style des autres boutons (Global, Mix...)."""
    bl_idname = "DESSIN_PT_named_views"
    bl_label = "Named Views"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'HEADER'
    bl_ui_units_x = 9

    def draw(self, context):
        self.layout.menu_contents(DESSIN_MT_named_views.bl_idname)


def named_view_button_menu(self, context):
    """Clic droit sur un onglet de vue : dupliquer, renommer, supprimer, masquer."""
    op = getattr(context, "button_operator", None)
    try:
        if op is None or not op.bl_rna.identifier.endswith("view_restore"):
            return
        name = op.name
    except (AttributeError, ReferenceError, RuntimeError):
        return
    layout = self.layout
    is_user = find_view(context.scene, name, base=False) is not None
    layout.operator(DESSIN_OT_view_duplicate.bl_idname, text="Duplicate View", icon='DUPLICATE').name = name
    layout.operator(DESSIN_OT_view_rename.bl_idname, text="Rename View...", icon='GREASEPENCIL').name = name
    if is_user:
        layout.operator(DESSIN_OT_view_delete.bl_idname, text="Delete View", icon='X').name = name
    else:
        layout.operator(DESSIN_OT_view_delete.bl_idname, text="Reset View", icon='LOOP_BACK').name = name
    layout.operator(DESSIN_OT_view_pin.bl_idname, text="Hide Tab", icon='HIDE_ON').name = name
    layout.separator()


def named_views_header(self, context):
    """Onglets de vues façon Rhino (Top | Front | Perspective | Right) et « + » pour le menu complet."""
    layout = self.layout
    active = current_view_name(context)
    row = layout.row(align=False)          # boutons séparés aux coins arrondis, comme Global / Mix
    for name in tab_names(context.scene):
        row.operator(DESSIN_OT_view_restore.bl_idname, text=view_label(context.scene, name), depress=(name == active)).name = name
    row.popover(DESSIN_PT_named_views.bl_idname, text="", icon='ADD')
    if pref("cmd_line"):
        row.operator(DESSIN_OT_command_line.bl_idname, text="", icon='CONSOLE')


# ---- Ligne de commande (barre en bas de la vue 3D : invite de l'outil actif, saisie du nom d'une commande) ----
_CMD = {"hit": {}, "op": {}, "mouse": {}, "prompt": {}, "cleared": set(), "log": [], "hist": [], "last": None, "input": None, "handle": None, "notice": None}
CMD_KEY_ITEMS = (('SPACE', "Space", "Space opens the command line (Space again on an empty line repeats the last command)"),
                 ('RET', "Enter", "Enter opens the command line (Enter again on an empty line repeats the last command)"),
                 ('ACCENT_GRAVE', "` (backtick)", "The ` key opens the command line"),
                 ('NONE', "None", "No key: click the command bar at the bottom of the viewport"))
CMD_ALIASES = {
    "layout_detail_tool": "viewport mview mv vports detail",
    "deplacer_tool": "m move", "copier_tool": "co cp copy", "selection_boite_tool": "select sel", "selection_lasso_tool": "lasso", "selection_rect_tool": "selbox", "selection_cercle_tool": "selcircle",
    "polyligne_tool": "pl line polyline", "plan_tool": "plane srf", "rotation_tool": "ro rot rotate", "echelle_tool": "sc scale",
    "echelle_2d_tool": "s2 scale2d", "echelle_1d_tool": "s1 scale1d", "echelle_taille_tool": "ss scalesize scaletosize", "rectangle_tool": "rec rect", "mirror_tool": "mi mirror",
    "array_rect_tool": "ar arrayrect", "array_linear_tool": "arl arraylinear", "array_polar_tool": "arp arraypolar", "cut_tool": "split cut",
    "fillet_edge_tool": "f fillet", "chamfer_edge_tool": "cha chamfer", "offset_edge_tool": "o offset",
    "bool_union_tool": "uni union", "bool_difference_tool": "su subtract diff difference", "bool_intersection_tool": "in intersect",
    "bool_split_tool": "bsplit booleansplit", "poly_center_tool": "pol polygon", "cercle_tool": "c ci circle", "cercle_diametre_tool": "cd",
    "ellipse_centre_tool": "el ellipse", "arc_cse_tool": "a arc", "arc_3pts_tool": "a3 arc3", "boite_tool": "bx box",
    "cylindre_tool": "cyl cylinder", "cone_tool": "cone", "pyramide_tool": "pyr pyramid", "tube_tool": "tube",
    "sphere_tool": "sp sph sphere", "tore_tool": "to torus", "cotation_tool": "dli dim dimension",
    "cotation_rayon_tool": "dra dimrad radius", "mesure_aire_tool": "aa area", "subd_loft_tool": "subdloft", "subd_sweep1_tool": "subdsweep1 subdsweep", "subd_sweep2_tool": "subdsweep2", "subd_revolve_tool": "subdrevolve", "subd_box_tool": "subdbox", "subd_sphere_tool": "subdsphere quadball", "subd_cylinder_tool": "subdcylinder subdcyl", "subd_cone_tool": "subdcone", "subd_torus_tool": "subdtorus", "subd_plane_tool": "subdplane", "text_tool": "text dt tx mtext", "center_mark_tool": "dimcenter centermark cm", "hatch_tool": "h hatch", "untrim_tool": "untrim", "untrim_holes_tool": "untrimholes", "block_tool": "block b", "block_insert_tool": "insert ins", "rebuild_crv_tool": "rebuild rb", "simplify_crv_tool": "simplifycrv fitcrv", "change_degree_tool": "changedegree", "insert_point_tool": "insertcontrolpoint insertpoint inspt", "remove_point_tool": "removecontrolpoint removepoint rempt", "match_crv_tool": "matchcrv mc", "blend_crv_tool": "blendcrv bc", "network_srf_tool": "networksrf ns", "fillet_srf_tool": "filletsrf fs", "chamfer_srf_tool": "chamfersrf chs", "extend_srf_tool": "extendsrf exs", "split_iso_tool": "splitiso spi", "cotation_chain_tool": "dimcontinue dimbaseline dco dba", "cotation_ordinate_tool": "dimordinate dor", "cotation_arc_tool": "dimarc dimcurvelength dar", "cotation_edit_tool": "dimedit dimmove de", "hatch_region_tool": "hatchregion bh bhatch", "dist_tool": "di dist distance", "id_point_tool": "id idpoint", "cotation_angle_tool": "dan dimangle angle", "annotation_tool": "lead leader note annotation", "curve_cp_tool": "crv curve", "extrude_path_tool": "extrudecrvalongcrv extrudepath", "srf_corners_tool": "srfpt corners", "curve_interp_tool": "ic interp interpcrv", "sketch_tool": "sk sketch", "pen_tool": "pen bezier", "point_tool": "pt point",
    "trim_tool": "tr trim", "join_tool": "j join", "explode_tool": "x explode", "align_tool": "al align",
    "make2d_tool": "m2d make2d", "revolve_tool": "rev revolve", "loft_tool": "loft", "sweep1_tool": "sweep1 sw1", "sweep2_tool": "sweep2 sw2",
    "light_point_tool": "pointlight", "light_spot_tool": "spotlight", "light_sun_tool": "sunlight", "light_area_tool": "arealight",
    "camera_tool": "cam camera", "camera_target_tool": "camt", "offset_surface_tool": "offsrf", "extrude_tool": "ext extrude", "extrude_crv_tool": "extrudecrv extc ec", "extrude_srf_tool": "extrudesrf exts es", "planar_srf_tool": "ps planarsrf", "edge_srf_tool": "edgesrf esrf", "thicken_tool": "thicken th", "cap_tool": "cap", "split_face_tool": "splitface sf", "project_curve_tool": "project proj", "patch_tool": "patch", "xline_tool": "xl xline", "stretch_tool": "st stretch", "divide_tool": "div divide", "overkill_tool": "overkill ok", "clip_plane_tool": "clip clippingplane clp", "fillet_curve_tool": "fc filletcurve fillet2d", "chamfer_curve_tool": "cc chamfercurve chamfer2d", "blend_srf_tool": "blendsrf bs", "match_srf_tool": "matchsrf ms", "rail_revolve_tool": "railrev rr", "shell_tool": "shell sh",
    # commandes Rhino de la 2.96.124 (une seule entrée dans la ligne de commande : l'outil de la barre)
    "pipe_tool": "pipe", "intersect_tool": "int intersect", "section_tool": "sec section", "contour_tool": "contour",
    "extract_srf_tool": "extractsrf", "dup_border_tool": "dupborder", "dup_edge_tool": "dupedge",
    "merge_faces_tool": "mergeallfaces mergeallcoplanarfaces", "unroll_tool": "unroll unrollsrf",
    "rebuild_srf_tool": "rebuildsrf", "orient_tool": "orient orient2pt",
}


def _late_imports():
    """Noms définis dans des modules chargés après celui-ci : ils ne servent qu'à l'exécution des outils."""
    global DESSIN_OT_command_line
    from .command_line import DESSIN_OT_command_line
    global is_layout, layout_close, menu_layouts, model_of
    from .layout import is_layout, layout_close, menu_layouts, model_of
