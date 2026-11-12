"""Wanderer CAD : Ligne de commande, barre d'état, modes."""

import blf
import bpy
import gpu
import math
import re
import time
from gpu_extras.batch import batch_for_shader

from .core import (
    FR_ACTION_ALIASES, FR_ALIASES, GRID_SNAP_PRESETS, ONESHOT_KEYS, TAU, _redraw_all_areas, grid_snap_shown, grid_snap_store,
    lang, mouse_over_statusbar, oneshot_clear, oneshot_hold, oneshot_hold_set, oneshot_keys, oneshot_reset, oneshot_shown,
    oneshot_toggle, osnap_shown, pref, redraw_bars, tr_label, tr_text, unit_info,
)
from .drawing import find_window_region, get_shader
from .base import DessinBase
from .selection import DESSIN_OT_esc_select
from .objects import _act_invoke
from .gumball import DESSIN_MT_gumball
from .gumball_handles import OSNAP_BAR
from .toolbar import DESSIN_TT_selection_boite, _SELECT_TOOL_IDS
from .navigation import BASE_VIEWS, DESSIN_OT_mouse_track, MOUSE_KEYMAPS, _update_view_keymap
from .views import CMD_ALIASES, CMD_KEY_ITEMS, DESSIN_MT_named_views, _CMD, current_view_name, tab_names, view_label
from .layout import bar_tabs, is_layout, layout_zoom_page, tab_click
from .cplane import (
    _act_cplane_mode, _act_cplane_named, _act_cplane_redo, _act_cplane_undo, _act_op, _act_origin, _act_region,
    _act_select_linked, _act_select_similar, _act_select_similar_menu, _act_shading, _act_toggle, cmd_clean_label,
    cmd_log, cmd_notice_clear, cmd_notice_text, cmd_tool_class, cmd_tool_classes, cp_apply_named, cp_current_rv3d,
)


class DESSIN_MT_auto_cplane(bpy.types.Menu):
    bl_idname = "DESSIN_MT_auto_cplane"
    bl_label = "Auto CPlane"

    def draw(self, context):
        lay = self.layout
        st = context.scene.dessin
        lay.prop(st, "auto_cplane", text="Auto CPlane")
        lay.prop(st, "auto_cplane_hover", text="Face under the cursor (draw on objects)")
        lay.prop(st, "auto_cplane_sticky", text="Sticky (keep the plane of the last planar selection)")
        lay.separator()
        lay.operator(DESSIN_OT_cplane_named.bl_idname, text="World Top (back to the ground plane)").name = 'Top'
        lay.operator(DESSIN_OT_cplane_named.bl_idname, text="Previous plane", icon='LOOP_BACK').name = 'UNDO'


class DESSIN_OT_cplane_named(bpy.types.Operator):
    bl_idname = "dessin.cplane_named"
    bl_label = "CPlane"
    bl_options = {'REGISTER'}

    name: bpy.props.StringProperty(default='Top')

    @classmethod
    def poll(cls, context):
        return cp_current_rv3d(context) is not None

    def execute(self, context):
        if self.name == 'UNDO':
            cmd_log(_act_cplane_undo(context))
        else:
            cmd_log(cp_apply_named(context, self.name))
        for win in context.window_manager.windows:
            for a in win.screen.areas:
                if a.type == 'VIEW_3D':
                    a.tag_redraw()
        return {'FINISHED'}


def _act_auto_cplane(context):
    st = context.scene.dessin
    st.auto_cplane = not st.auto_cplane
    return "Auto CPlane " + ("on" if st.auto_cplane else "off")


def _act_delete(context):
    if is_layout(context.scene):
        bpy.ops.dessin.layout_erase()        # mise en page : un détail part avec ses traits et ses cotes, en un seul pas
    else:
        bpy.ops.object.delete()
    return ""


def _act_zoom_extents(context):
    if not layout_zoom_page(context):
        bpy.ops.view3d.view_all()
    return ""


CMD_ACTIONS = (
    ("Auto CPlane", "acp autocplane", "", "Turn Auto CPlane on / off: the construction plane follows the planar object or face you select", _act_auto_cplane),
    ("PushPull", "pp pushpull", "", "Pull or push a face of a solid or a surface along its normal: click the face, then move the mouse or type a distance", _act_invoke("dessin.pushpull")),
    ("CPlane", "cpl cplane", "", "Set the construction plane: click a face to draw on it (3: three points, V: vertical, W: world, U: undo)", _act_cplane_mode('OBJECT')),
    ("CPlane 3 Points", "cpl3 cplane3 cplane3pt", "", "Construction plane from three points: origin, X axis, Y side", _act_cplane_mode('3PT')),
    ("CPlane Vertical", "cplv cplanevertical", "", "Vertical construction plane through two points, perpendicular to the current plane", _act_cplane_mode('VERT')),
    ("CPlane View", "cplview cplaneview", "", "Construction plane parallel to the view", _act_cplane_named('View')),
    ("CPlane Top", "cpltop cplaneworld cplworld", "", "Back to the world Top construction plane", _act_cplane_named('Top')),
    ("CPlane Front", "cplfront", "", "World Front construction plane", _act_cplane_named('Front')),
    ("CPlane Right", "cplright", "", "World Right construction plane", _act_cplane_named('Right')),
    ("CPlane Back", "cplback", "", "World Back construction plane", _act_cplane_named('Back')),
    ("CPlane Left", "cplleft", "", "World Left construction plane", _act_cplane_named('Left')),
    ("CPlane Bottom", "cplbottom", "", "World Bottom construction plane", _act_cplane_named('Bottom')),
    ("CPlane Elevation", "cple cplelev cplaneelevation", "", "Move the construction plane along its normal by a distance", _act_invoke("dessin.cplane_elevation")),
    ("CPlane Undo", "cplundo cplaneundo", "", "Previous construction plane", _act_cplane_undo),
    ("CPlane Redo", "cplredo cplaneredo", "", "Next construction plane", _act_cplane_redo),
    ("Undo", "undo", "ed.undo", "Undo the last action", _act_op("ed.undo")),
    ("Redo", "redo", "ed.redo", "Redo the last undone action", _act_op("ed.redo")),
    ("Delete", "e del delete erase", "", "Delete the selected objects", _act_delete),
    ("Extend Curve", "extendcrv extend extendcurve", "", "Extend the selected curves by a length or up to the nearest other curve", _act_invoke("dessin.extend_crv")),
    ("Select All", "sa all selectall", "", "Select every object", _act_op("object.select_all", action='SELECT')),
    ("Select None", "sn none deselect selnone", "", "Deselect everything", _act_op("object.select_all", action='DESELECT')),
    ("Invert Selection", "si invert selinvert", "", "Invert the selection", _act_op("object.select_all", action='INVERT')),
    ("Hide", "hi hide", "", "Hide the selected objects", _act_op("object.hide_view_set", unselected=False)),
    ("Isolate", "isolate", "", "Hide everything except the selected objects", _act_op("object.hide_view_set", unselected=True)),
    ("Show All", "show showall unhide", "", "Show the hidden objects", _act_op("object.hide_view_clear")),
    ("Zoom Extents", "z ze zoom extents zoomall", "", "Frame all the objects (on a layout: the whole sheet)", _act_zoom_extents),
    ("Zoom Selected", "zs zoomselected", "", "Frame the selected objects", _act_op("view3d.view_selected")),
    ("Perspective / Ortho", "ortho persp projection", "", "Toggle perspective / orthographic projection", _act_op("view3d.view_persportho")),
    ("Wireframe", "wire wireframe", "", "Wireframe shading", _act_shading('WIREFRAME')),
    ("Shaded", "shaded solid", "", "Solid shading", _act_shading('SOLID')),
    ("Rendered", "rendered render", "", "Rendered shading", _act_shading('RENDERED')),
    ("X-Ray", "xray", "", "Toggle X-Ray", _act_toggle(("shading", "show_xray"))),
    ("Grid", "grid", "", "Show / hide the grid", _act_toggle(("overlay", "show_floor"))),
    ("Cursor to Origin", "origin cursorhome", "", "Move the 3D cursor to the world origin", _act_origin),
    ("Save", "save", "", "Save the file", _act_op("wm.save_mainfile")),
    ("Select Similar", "ss selsimilar similar", "", "Select similar objects / faces: choose the criterion (material, type, collection...)", _act_select_similar_menu),
    ("Select Similar Material", "ssm selmat samemat", "", "Select the objects (or faces) that share the material of the selection", _act_select_similar("MATERIAL")),
    ("Select Similar Type", "sst", "", "Select the objects of the same type", _act_select_similar("TYPE")),
    ("Select Similar Collection", "ssc", "", "Select the objects of the same collection", _act_select_similar("COLLECTION")),
    ("Select Similar Hierarchy", "ssh", "", "Select the children of the selected objects", _act_select_similar("HIERARCHY")),
    ("Select Similar Area", "ssa", "", "Select the faces of similar area (Edit Mode)", _act_select_similar("AREA")),
    ("Select Similar Normal", "ssn", "", "Select the faces with a similar normal (Edit Mode)", _act_select_similar("NORMAL")),
    ("Select Similar Sides", "sss", "", "Select the faces with the same number of sides (Edit Mode)", _act_select_similar("SIDES")),
    ("Select Linked", "sl selectlinked", "", "Select the geometry / objects linked to the selection", _act_select_linked),
    ("Sidebar", "n sidebar", "", "Show / hide the sidebar (N panel)", _act_region("show_region_ui")),
    ("Toolbar", "t toolbar", "", "Show / hide the toolbar", _act_region("show_region_toolbar")),
    ("Overlays", "ov overlays", "", "Show / hide the overlays", _act_toggle(("overlay", "show_overlays"))),
    ("Gizmos", "gz gizmos", "", "Show / hide the gizmos", _act_region("show_gizmo")),
    ("Statistics", "stat stats statistics", "", "Show / hide the scene statistics", _act_toggle(("overlay", "show_stats"))),
    ("Maximize Area", "max maximize", "", "Maximize / restore the area", _act_op("screen.screen_full_area")),
    ("Local View", "lv localview isolateview", "", "Local view of the selection", _act_op("view3d.localview")),
    ("Camera View", "vc cameraview", "", "View through the active camera", _act_op("view3d.view_camera")),
    ("Cursor to Selected", "c2s cursortoselected", "", "Move the 3D cursor to the selection", _act_op("view3d.snap_cursor_to_selected")),
    ("Show Edges", "showedges nakededges naked edges", "", "Highlight the naked edges (open borders) of the selection, like ShowEdges; again to hide", _act_op("dessin.show_edges")),
    ("To SubD", "tosubd subd", "", "Turn the selected meshes into SubD (their faces become the control cage)", _act_op("dessin.subd", action='TO_SUBD')),
    ("SubD to Mesh", "subdtomesh applysubd", "", "Apply the subdivision: the smooth surface becomes the mesh", _act_op("dessin.subd", action='TO_MESH')),
    ("Toggle SubD Display", "togglesubddisplay subddisplay", "", "Smooth / box display of the selected SubD", _act_op("dessin.subd", action='DISPLAY')),
    ("Crease", "crease", "", "Sharp crease on the selected edges (Edit Mode)", _act_op("dessin.subd", action='CREASE')),
    ("Remove Crease", "removecrease uncrease", "", "Remove the crease from the selected edges (Edit Mode)", _act_op("dessin.subd", action='UNCREASE')),
    ("Insert Edge", "insertedge", "", "Insert an edge loop (Edit Mode)", _act_op("dessin.subd", action='INSERT_EDGE')),
    ("Slide", "slide", "", "Slide edges or points along the surface (Edit Mode)", _act_op("dessin.subd", action='SLIDE')),
    ("Inset", "inset insetfaces", "", "Inset the selected faces (Edit Mode)", _act_op("dessin.subd", action='INSET')),
    ("Bridge", "bridge", "", "Bridge two edge chains (Edit Mode)", _act_op("dessin.subd", action='BRIDGE')),
    ("Fill", "fill fillhole", "", "Fill the selected hole with quads (Edit Mode)", _act_op("dessin.subd", action='FILL')),
    ("Append Face", "append appendface", "", "Face from the selected points / edges (Edit Mode)", _act_op("dessin.subd", action='APPEND')),
    ("Merge Faces", "mergefaces mergeallfaces", "", "Merge the selected faces (Edit Mode)", _act_op("dessin.subd", action='MERGE_FACES')),
    ("Weld", "weld", "", "Weld coincident points (Edit Mode)", _act_op("dessin.subd", action='WELD')),
    ("Stitch", "stitch", "", "Stitch the selected points / edges on the last one (Edit Mode)", _act_op("dessin.subd", action='STITCH')),
    ("Extract Faces", "extractsubobject extractfaces extract", "", "Extract the selected faces to a new object (Edit Mode)", _act_op("dessin.subd", action='EXTRACT')),
    ("Select Loop", "selloop loop", "", "Select the edge loop (Edit Mode)", _act_op("dessin.subd", action='SEL_LOOP')),
    ("Select Ring", "selring ring", "", "Select the edge ring (Edit Mode)", _act_op("dessin.subd", action='SEL_RING')),
    ("Symmetry X", "reflect symmetry symx", "", "Live symmetry across X (Mirror before the SubD)", _act_op("dessin.subd", action='REFLECT_X')),
    ("Symmetry Y", "symy", "", "Live symmetry across Y", _act_op("dessin.subd", action='REFLECT_Y')),
    ("Symmetry Z", "symz", "", "Live symmetry across Z", _act_op("dessin.subd", action='REFLECT_Z')),
    ("MultiPipe", "multipipe mp", "", "SubD pipes along the selected curves, joined at the nodes", _act_op("dessin.subd", action='MULTIPIPE')),
    ("Group", "g group", "", "Group the selected objects", _act_op("dessin.group")),
    ("Ungroup", "ug ungroup", "", "Ungroup the selected group", _act_op("dessin.ungroup")),
    ("Block Edit", "blockedit be refedit", "", "Edit the selected block in place (every copy follows); Close Block Edit to finish", _act_op("dessin.block_edit")),
    ("Close Block Edit", "blockeditclose bclose refclose", "", "Finish Block Edit and save the changes into the block", _act_op("dessin.block_edit_close")),
    ("Explode Block", "explodeblock xb", "", "Turn the selected block copies back into ordinary objects", _act_op("dessin.block_explode")),
    ("Hatch Base Point", "hatchbase", "", "Select hatches, then click the point their pattern starts from", _act_invoke("dessin.hatch_base")),
    ("Explode Hatch", "explodehatch", "", "Turn the selected hatches into curves (a solid hatch becomes a planar surface)", _act_op("dessin.hatch_explode")),
    ("Hatch Boundary", "hatchboundary", "", "Create curves on the boundary and the holes of the selected hatches", _act_op("dessin.hatch_boundary")),
    ("Match Hatch", "matchhatch", "", "Give the selected hatches the pattern, scale and rotation of the active one (clicked last)", _act_op("dessin.hatch_match")),
    ("Layout", "layout lo newlayout", "", "New layout: a paper sheet (A4 to A0...) with detail views of the model at scale, a title block and PDF / SVG / DXF export", _act_invoke("dessin.layout_new")),
    ("Model Space", "model mspace tilemode", "", "Leave the layout and go back to the model", _act_op("dessin.layout_close")),
    ("Next Layout", "pspace nextlayout", "", "Open the next layout (paper space)", _act_op("dessin.layout_next")),
    ("Update Details", "updatedetails regen regenall", "", "Layout: redraw the detail views from the model", _act_op("dessin.detail_update", all=True)),
    ("Detail Scale", "detailscale vpscale zoomxp", "", "Layout: type the scale of the selected details (1:20, 2:1, or 25 for 1:25)", _act_invoke("dessin.detail_scale")),
    ("Fit Detail", "detailfit fitdetail", "", "Layout: frame the whole model in the selected details at the largest standard scale that fits", _act_op("dessin.detail_fit")),
    ("Pan Detail", "detailpan pandetail dpan", "", "Layout: move the model inside a detail (drag), change its scale (wheel)", _act_invoke("dessin.detail_pan")),
    ("Page Setup", "pagesetup", "", "Layout: paper size, orientation, margin and title block of the current layout", _act_invoke("dessin.layout_page_setup")),
    ("Export PDF", "exportpdf pdf print plot", "", "Layout: vector PDF at the exact paper size, one page per layout (print at 100 % for a drawing at scale)", _act_invoke("dessin.layout_export_pdf")),
    ("Export SVG", "exportsvg svg", "", "Layout: vector SVG in millimeters (Illustrator, Inkscape...)", _act_invoke("dessin.layout_export_svg")),
    ("Export DXF", "exportdxf dxfout", "", "Layout: DXF in paper millimeters for AutoCAD, Rhino, CADCraft...", _act_invoke("dessin.layout_export_dxf")),
)


_NATIVE = {"list": None}
CMD_NATIVE_SKIP = {"wm.quit_blender", "wm.read_factory_settings", "wm.read_homefile", "wm.link", "wm.append"}
CMD_NATIVE_MODULES = ("object", "mesh", "view3d", "curve", "wm", "transform", "scene", "material", "armature", "anim",
                      "constraint", "lattice", "surface", "mball", "render", "pose", "geometry", "curves")
CMD_MODIFIER_ALIASES = {"SUBSURF": "subd subsurf", "MIRROR": "mir", "ARRAY": "arr", "BOOLEAN": "bool", "SOLIDIFY": "thick shell",
                        "BEVEL": "bev", "DECIMATE": "decim", "WELD": "weld", "SIMPLE_DEFORM": "bend twist", "NODES": "geonodes gn"}
CMD_MODES = (("Edit Mode", "edit", 'EDIT'), ("Object Mode", "object obj", 'OBJECT'), ("Sculpt Mode", "sculpt", 'SCULPT'),
             ("Pose Mode", "pose", 'POSE'), ("Weight Paint Mode", "weight", 'WEIGHT_PAINT'),
             ("Vertex Paint Mode", "vpaint", 'VERTEX_PAINT'), ("Texture Paint Mode", "tpaint", 'TEXTURE_PAINT'))
CMD_ADD = (("Grid", "mesh", "primitive_grid_add"), ("Monkey", "mesh", "primitive_monkey_add"),
           ("Bezier Curve", "curve", "primitive_bezier_curve_add"), ("Bezier Circle", "curve", "primitive_bezier_circle_add"),
           ("NURBS Path", "curve", "primitive_nurbs_path_add"), ("Text", "object", "text_add"), ("Empty", "object", "empty_add"),
           ("Armature", "object", "armature_add"))
# Les primitives de Blender (Cube, Plane, Circle, UV / Ico Sphere, Cylinder, Cone, Torus) sont exclues de la ligne de commande :
# elles se confondaient avec les outils Box, Plane, Circle, Sphere, Cylinder, Cone et Torus de Wanderer.
CMD_NATIVE_HIDE = {"mesh." + n for n in ("primitive_cube_add", "primitive_plane_add", "primitive_circle_add", "primitive_uv_sphere_add",
                                         "primitive_ico_sphere_add", "primitive_cylinder_add", "primitive_cone_add", "primitive_torus_add")} | {"curves.add_circle"}
CMD_OBJECT_OPS = (("Apply Transforms", "object", "transform_apply", {}, "apply freeze"), ("Origin to Geometry", "object", "origin_set", {"type": 'ORIGIN_GEOMETRY'}, "o2g"),
                  ("Origin to 3D Cursor", "object", "origin_set", {"type": 'ORIGIN_CURSOR'}, "o2c"),
                  ("Shade Smooth", "object", "shade_smooth", {}, "sm smooth"), ("Shade Flat", "object", "shade_flat", {}, "sf flat"),
                  ("Convert to Mesh", "object", "convert", {"target": 'MESH'}, "tomesh"), ("Convert to Curve", "object", "convert", {"target": 'CURVE'}, "tocurve"),
                  ("Set Parent", "object", "parent_set", {}, "pa parent"), ("Clear Parent", "object", "parent_clear", {}, "up unparent"),
                  ("Duplicate Linked", "object", "duplicate_move_linked", {}, "dupl"), ("Merge by Distance", "mesh", "remove_doubles", {}, "mg weld merge"),
                  ("Recalculate Normals", "mesh", "normals_make_consistent", {}, "nrm normals"), ("Subdivide", "mesh", "subdivide", {}, "sub subdiv"),
                  ("Loop Cut", "mesh", "loopcut_slide", {}, "lc loopcut"), ("Inset Faces", "mesh", "inset", {}, "inset"),
                  ("Bevel Edges", "mesh", "bevel", {}, "bev bevel"),
                  ("Unwrap", "uv", "unwrap", {}, "uw unwrap"), ("Smart UV Project", "uv", "smart_project", {}, "suv smartuv"),
                  ("Pack Islands", "uv", "pack_islands", {}, "pk pack"), ("Mark Seam", "uv", "mark_seam", {"clear": False}, "ms seam"),
                  ("Clear Seam", "uv", "mark_seam", {"clear": True}, "cls clearseam"))


def cmd_native_build():
    """Commandes natives de Blender : modificateurs, contraintes, ajout d'objets, modes, puis tous les opérateurs utiles."""
    if _NATIVE["list"] is not None:
        return _NATIVE["list"]
    out, used = [], set()

    def add(key, label, names, desc, mod, op, kw=None, invoke=False, alias="", gen=False):
        if any(o["label"] == label for o in out):
            return
        out.append({"key": key, "label": label, "names": [label] + names, "kind": "native", "ref": (mod, op, kw or {}, invoke),
                    "desc": desc, "alias": alias, "gen": gen})
        used.add((mod, op))

    def enum_items(mod, op, prop):
        try:
            return [(i.identifier, i.name) for i in getattr(getattr(bpy.ops, mod), op).get_rna_type().properties[prop].enum_items if i.identifier]
        except (AttributeError, KeyError, RuntimeError, TypeError):
            return []
    for ident, name in enum_items("object", "modifier_add", "type"):
        add("mod:" + ident, f"{name} (Modifier)", [name, "mod " + name] + CMD_MODIFIER_ALIASES.get(ident, "").split(),
            "Add a " + name + " modifier to the active object", "object", "modifier_add", {"type": ident}, alias="modifier")
    for ident, name in enum_items("object", "constraint_add", "type"):
        add("con:" + ident, f"{name} (Constraint)", [name], "Add a " + name + " constraint", "object", "constraint_add", {"type": ident}, alias="constraint")
    for name, mod, op in CMD_ADD:
        add("add:" + op, "Add " + name, [name, "new " + name], "Add a " + name + " at the 3D cursor", mod, op, invoke=True, alias="add")
    for label, al, mode in CMD_MODES:
        add("mode:" + mode, label, al.split(), "Switch to " + label, "object", "mode_set", {"mode": mode}, alias="mode")
    for label, mod, op, kw, al in CMD_OBJECT_OPS:
        add(f"op:{mod}.{op}:{label}", label, al.split(), label, mod, op, kw, invoke=not kw, alias=f"{mod}.{op}")
    seen_lab = {e["label"].lower() for e in out}
    for mod in CMD_NATIVE_MODULES:
        try:
            grp = getattr(bpy.ops, mod)
            names = dir(grp)
        except (AttributeError, RuntimeError):
            continue
        for op in names:
            if op.startswith("_") or (mod, op) in used or f"{mod}.{op}" in CMD_NATIVE_SKIP or f"{mod}.{op}" in CMD_NATIVE_HIDE or "gizmo" in op:
                continue
            try:
                rna = getattr(grp, op).get_rna_type()
            except (AttributeError, KeyError, RuntimeError):
                continue
            nm = rna.name
            if not nm or nm == op or nm.lower() in seen_lab:
                continue
            seen_lab.add(nm.lower())
            add(f"gen:{mod}.{op}", nm, [f"{mod}.{op}", f"{mod} {op}"], rna.description or nm, mod, op, invoke=True, alias=f"{mod}.{op}", gen=True)
    _NATIVE["list"] = out
    return out


CMD_VIEW_ALIASES = {"Top": "tp", "Front": "fr", "Right": "rt", "Left": "lf", "Back": "bk", "Bottom": "bt", "Perspective": "pe"}


def cmd_entries(context=None):
    """[{key, label, names, desc, kind, ref}] : outils de la barre, commandes générales, vues et commandes natives de Blender."""
    out = []
    classes_ = cmd_tool_classes()
    counts = {}
    for c in classes_:
        counts[cmd_clean_label(c.bl_label)] = counts.get(cmd_clean_label(c.bl_label), 0) + 1
    act_names = {lab for lab, _al, _x, _d, _fn in CMD_ACTIONS}
    for c in classes_:
        label = cmd_clean_label(c.bl_label)
        if getattr(c, "dessin_cmd_hidden", False):
            continue     # bouton de la barre dont la commande du même nom fait mieux (Layout : ouvre la boîte tout de suite)
        if c.bl_idname.startswith("dessin.subdc_") and cmd_clean_label(c.__dict__.get("dessin_en_label", c.bl_label)) in act_names:
            continue     # outil SubD de la barre qui double une commande : la commande (même nom) suffit dans la ligne de commande
        if counts[label] > 1:
            label = c.bl_label.split(" →")[0].strip()
        short = c.bl_idname.split(".", 1)[1]
        names = [label] + CMD_ALIASES.get(short, "").split()
        if lang() == 'FR':
            names = [label] + FR_ALIASES.get(short, "").split()      # alias AutoCAD français (les alias anglais ne servent qu'en anglais)
            en_label = cmd_clean_label(c.__dict__.get("dessin_en_label", ""))
            if en_label and en_label != label:
                names.append(en_label)
        out.append({"key": "tool:" + c.bl_idname, "label": label, "names": names, "kind": "tool", "ref": c.bl_idname,
                    "desc": getattr(c, "dessin_hint", "") or c.bl_description})
    fr = lang() == 'FR'
    for label, al, _x, desc, fn in CMD_ACTIONS:
        shown = tr_label(label)
        names = [shown] + al.split()
        if fr:
            names = [shown, label] + FR_ACTION_ALIASES.get(label, "").split()
        out.append({"key": "act:" + label, "label": shown, "names": names, "kind": "act", "ref": fn, "desc": desc})
    for name, _t in BASE_VIEWS:
        vnames = [name + " view", name.lower()] + CMD_VIEW_ALIASES.get(name, "").split()
        vlabel = name + " View"
        if fr:
            vlabel = "Vue " + tr_label(name).lower()
            vnames += [vlabel, tr_label(name).lower()]
        out.append({"key": "view:" + name, "label": vlabel, "names": vnames, "kind": "view",
                    "ref": name, "desc": "Restore the " + name + " view"})
    taken = {e["label"].lower() for e in out}
    # commande de Blender dont le nom se confond avec un outil de Wanderer (« Push/Pull » et « PushPull ») : on la garde,
    # mais marquée, pour qu'on ne la prenne pas pour l'outil
    ours = set()
    for e in out:
        for nm in e["names"]:
            k = cmd_compact(nm)
            if len(k) >= 3:
                ours.add(k)
    for e in cmd_native_build():
        if e.get("gen") and e["label"].lower() in taken:
            continue
        if cmd_compact(e["label"]) in ours:
            e = dict(e, label=e["label"] + NATIVE_TAG)
        out.append(e)
    return out


NATIVE_TAG = " (Blender native)"


def cmd_compact(s):
    """Nom sans casse, accents, espaces ni ponctuation : « Push/Pull » et « PushPull » donnent la même clé."""
    return cmd_norm(s).replace(" ", "")


_NORM_CACHE = {}


def cmd_norm(s):
    v = _NORM_CACHE.get(s)
    if v is None:
        import re
        import unicodedata
        flat = "".join(ch for ch in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(ch))
        v = _NORM_CACHE[s] = re.sub(r"[^a-z0-9]+", " ", flat).strip()
    return v


def cmd_score(q, name):
    n = cmd_norm(name)
    if not n:
        return None
    if n == q:
        return 0.0
    if n.startswith(q):
        return 1.0 + len(n) * 0.001
    if any(w.startswith(q) for w in n.split()):
        return 2.0 + len(n) * 0.001
    if q in n:
        return 3.0 + len(n) * 0.001
    it = iter(n.replace(" ", ""))
    if all(ch in it for ch in q.replace(" ", "")):
        return 4.0 + len(n) * 0.001
    return None


_SUGG_MEMO = {}


def cmd_native_ok(e):
    """Le poll de l'opérateur natif est-il satisfait dans le contexte actuel ?"""
    mod, op = e["ref"][0], e["ref"][1]
    try:
        return bool(getattr(getattr(bpy.ops, mod), op).poll())
    except (AttributeError, RuntimeError, TypeError):
        return False


def cmd_suggest(text, limit=8):
    """Commandes correspondant au texte saisi, les meilleures d'abord (exact, début, mot, contient, lettres dans l'ordre).
    Les opérateurs natifs génériques passent après les outils et n'apparaissent qu'à partir de 2 lettres."""
    q = cmd_norm(text)
    if not q:
        return []
    memo = _SUGG_MEMO.get((q, limit))
    if memo is not None:
        return memo
    found = []
    for i, e in enumerate(cmd_entries()):
        if e.get("gen") and len(q) < 2:
            continue
        best = None
        for j, nm in enumerate(e["names"]):
            sc_ = cmd_score(q, nm)
            if sc_ is not None:
                sc_ += 0.0005 * j
                best = sc_ if best is None else min(best, sc_)
        if best is not None:
            found.append((best + (1.5 if e.get("gen") else (0.01 if e["kind"] == "native" else 0.0)), i, e))     # à égalité, l'outil passe avant la commande native de Blender
    found.sort(key=lambda t: (t[0], t[1]))
    out = []
    for _s, _i, e in found[:limit * 6]:
        if e["kind"] == "native" and not cmd_native_ok(e):
            continue
        out.append(e)
        if len(out) >= limit:
            break
    _SUGG_MEMO[(q, limit)] = out
    return out


def cmd_by_key(key):
    for e in cmd_entries():
        if e["key"] == key:
            return e
    return None


# Commandes « on désigne les objets, puis Entrée » : si la sélection est déjà faite, on les lance tout de suite (comme Rhino)
RUN_ON_SELECTION = {"dessin.join_tool": "join", "dessin.explode_tool": "explode", "dessin.make2d_tool": "make2d",
                    "dessin.planar_srf_tool": "planar_srf", "dessin.hatch_tool": "hatch", "dessin.network_srf_tool": "network_srf", "dessin.rebuild_crv_tool": "rebuild_crv", "dessin.simplify_crv_tool": "simplify_crv", "dessin.change_degree_tool": "change_degree", "dessin.edge_srf_tool": "edge_srf", "dessin.thicken_tool": "thicken",
                    "dessin.patch_tool": "patch", "dessin.cap_tool": "cap", "dessin.shell_tool": "shell",
                    "dessin.divide_tool": "divide", "dessin.overkill_tool": "overkill",
                    "dessin.fillet_curve_tool": "fillet_curve", "dessin.chamfer_curve_tool": "chamfer_curve",
                    "dessin.pipe_tool": "pipe", "dessin.intersect_tool": "intersect", "dessin.dup_border_tool": "dup_border",
                    "dessin.merge_faces_tool": "merge_faces", "dessin.unroll_tool": "unroll", "dessin.rebuild_srf_tool": "rebuild_srf"}

# Commandes « on survole, on clique » dont l'outil de la barre attend un premier clic pour démarrer : tapées dans la ligne de
# commande, elles démarrent tout de suite (rien à désigner avant), comme avant la 2.97.1
RUN_NOW = {"dessin.extract_srf_tool": "extract_srf", "dessin.dup_edge_tool": "dup_edge"}


def tool_run_mode(context, tool_id):
    """Ce que fait la ligne de commande une fois l'outil armé : 'now' (la commande démarre tout de suite), 'selection'
    (elle est lancée sur la sélection déjà faite) ou 'arm' (l'outil attend qu'on désigne les objets)."""
    if tool_id in RUN_NOW:
        return 'now'
    if (tool_id in RUN_ON_SELECTION and context.mode == 'OBJECT'
            and any(o.type in {'MESH', 'CURVE'} for o in context.selected_objects)):
        return 'selection'
    return 'arm'


def arm_tool(name):
    """Arme un outil de la barre (les tests le remplacent : pas de fenêtre en mode sans écran)."""
    bpy.ops.wm.tool_set_by_id(name=name)


def run_soon(fn, delay=0.1):
    try:
        bpy.app.timers.register(fn, first_interval=delay)
    except (RuntimeError, ValueError):
        pass


def op_invoke(name):
    """Lance dessin.<name> dans la vue courante (comme un clic sur son bouton)."""
    getattr(bpy.ops.dessin, name)('INVOKE_DEFAULT')


def op_invoke_in(window, area, region, name):
    """Lance dessin.<name> dans une vue 3D donnée (depuis un minuteur, il n'y a pas de contexte de vue)."""
    with bpy.context.temp_override(window=window, area=area, region=region):
        getattr(bpy.ops.dessin, name)('INVOKE_DEFAULT')


def run_on_selection(context, tool_id):
    name = RUN_ON_SELECTION.get(tool_id)
    area = context.area
    if name is None or area is None or area.type != 'VIEW_3D' or tool_run_mode(context, tool_id) != 'selection':
        return
    window = context.window
    region = next((r for r in area.regions if r.type == 'WINDOW'), None)
    if window is None or region is None:
        return

    def _go():
        try:
            op_invoke_in(window, area, region, name)
        except (RuntimeError, TypeError, AttributeError, ReferenceError):
            pass
        return None
    run_soon(_go)


def cmd_run(context, entry):
    """Exécute une commande ; retourne un message d'erreur ou ''."""
    cmd_notice_clear()
    try:
        if entry["kind"] == "tool":
            ref = entry["ref"]
            if ref in ("dessin.extrude_tool", "dessin.extrude_crv_tool"):      # Extrude : l'outil du mode courant
                ref = "dessin.extrude_tool" if context.mode == 'EDIT_MESH' else "dessin.extrude_crv_tool"
            if tool_run_mode(context, ref) == 'now':
                # la commande démarre seule, sans armer son outil : armé, il prendrait le clic qui vient de choisir la
                # suggestion pour une désignation dans la vue
                op_invoke(RUN_NOW[ref])
            else:
                arm_tool(ref)
                run_on_selection(context, ref)
        elif entry["kind"] == "view":
            bpy.ops.dessin.view_restore(name=entry["ref"])
        elif entry["kind"] == "native":
            mod, op, kw, invoke = entry["ref"]
            fn = getattr(getattr(bpy.ops, mod), op)
            if invoke:
                fn('INVOKE_DEFAULT', **kw)
            else:
                fn(**kw)
        else:
            msg = entry["ref"](context)
            if msg:
                cmd_log(msg)
    except (RuntimeError, TypeError, AttributeError, ReferenceError) as err:
        return f"{entry['label']}: not available here ({str(err).strip().splitlines()[-1] if str(err).strip() else 'error'})"
    cmd_log(entry["label"])
    _CMD["last"] = entry["key"]
    hist = _CMD["hist"]
    if entry["label"] in hist:
        hist.remove(entry["label"])
    hist.append(entry["label"])
    del hist[:-30]
    return ""


def cmd_input_key(st, etype, uni="", ctrl=False):
    """Fait évoluer l'état de saisie st selon une touche. Retourne 'run', 'close', 'redraw' ou None (touche ignorée)."""
    text = st["text"]
    if etype == 'ESC':
        return 'close'
    if etype in {'RET', 'NUMPAD_ENTER'}:
        return 'run'
    if etype == 'BACK_SPACE':
        st["text"] = "" if ctrl else text[:-1]
        st["sel"], st["hist"] = 0, -1
        return 'redraw'
    if etype in {'UP_ARROW', 'DOWN_ARROW'}:
        step = -1 if etype == 'UP_ARROW' else 1
        sugg = cmd_suggest(text) if text and st["hist"] < 0 else []
        if sugg:
            st["sel"] = (st["sel"] + step) % len(sugg)
        else:
            hist = _CMD["hist"]
            if hist:
                st["hist"] = (len(hist) if st["hist"] < 0 else st["hist"]) + step
                st["hist"] = max(0, min(len(hist) - 1, st["hist"]))
                st["text"] = hist[st["hist"]]
                st["sel"] = 0
        return 'redraw'
    if etype == 'TAB':
        sugg = cmd_suggest(text)
        if sugg:
            if st.get("tab") is None:
                st["tab"] = text
                st["sel"] = 0
            else:
                st["sel"] = (st["sel"] + 1) % len(cmd_suggest(st["tab"]))
            sugg = cmd_suggest(st["tab"])
            st["text"] = sugg[st["sel"]]["label"]
        return 'redraw'
    if uni == " ":
        return 'run'            # Espace valide comme Entrée (ligne vide : répète la dernière commande)
    if uni and uni.isprintable() and not ctrl:
        st["text"] = text + uni
        st["sel"], st["hist"], st["tab"] = 0, -1, None
        return 'redraw'
    return None


def cmd_close():
    st = _CMD["input"]
    _CMD["input"] = None
    return st


class DESSIN_OT_command_line(bpy.types.Operator):
    bl_idname = "dessin.command_line"
    bl_label = "Command Line"
    bl_description = ("Type the name of a command (rectangle, move, trim, zoom...) then Enter. Tab completes, Up / Down browse the history; "
                      "Space (or Enter) on an empty line repeats the last command")
    bl_options = {'INTERNAL'}

    char: bpy.props.StringProperty(default="", options={'SKIP_SAVE', 'HIDDEN'})   # première lettre tapée (saisie directe)

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D'

    def invoke(self, context, event):
        self.ptr = context.area.as_pointer()
        _SUGG_MEMO.clear()
        cmd_native_build()
        _CMD["input"] = {"area": self.ptr, "text": self.char, "sel": 0, "hist": -1, "tab": None}
        context.window_manager.modal_handler_add(self)
        context.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def finish(self, context, result):
        cmd_close()
        try:
            context.area.tag_redraw()
        except (AttributeError, ReferenceError):
            pass
        return result

    def modal(self, context, event):
        st = _CMD["input"]
        if st is None or st["area"] != self.ptr:
            return {'CANCELLED'}
        if context.area is None or context.area.as_pointer() != self.ptr:
            return {'PASS_THROUGH'}
        et = event.type
        if et == 'MOUSEMOVE':
            reg = find_window_region(context.area, event.mouse_x, event.mouse_y)
            if reg is not None:
                _CMD["mouse"][self.ptr] = (event.mouse_x - reg.x, event.mouse_y - reg.y)
                _CMD.setdefault("mouse_t", {})[self.ptr] = time.monotonic()
                context.area.tag_redraw()
            return {'PASS_THROUGH'}
        if et == 'LEFTMOUSE' and event.value == 'PRESS':
            hit = cmd_hit(context.area, event.mouse_x, event.mouse_y)
            if hit is not None and hit[0] in {'sugg', 'run'}:
                sug = cmd_suggest(st["tab"] if st.get("tab") is not None else st["text"]) if hit[0] == 'sugg' else []
                return self.execute_input(context, st, picked=sug[hit[1]] if hit[1] is not None and hit[1] < len(sug) else None)
            return self.finish(context, {'CANCELLED', 'PASS_THROUGH'})      # un clic ailleurs ferme la saisie
        if event.value != 'PRESS' or et in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE', 'TIMER'} or et.endswith('MOUSE'):
            return {'PASS_THROUGH'}
        if (event.ctrl or event.oskey) and et == 'V':
            st["text"] += context.window_manager.clipboard.splitlines()[0] if context.window_manager.clipboard else ""
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.alt or ((event.ctrl or event.oskey) and et != 'BACK_SPACE'):
            return {'PASS_THROUGH'}
        if et in {'RET', 'NUMPAD_ENTER', 'SPACE'} and event.is_repeat:
            return {'RUNNING_MODAL'}               # touche maintenue : pas de lancement involontaire
        res = cmd_input_key(st, et, event.unicode, event.ctrl or event.oskey)
        if res is None:
            return {'PASS_THROUGH'}
        if res == 'close':
            return self.finish(context, {'CANCELLED'})
        if res == 'run':
            return self.execute_input(context, st)
        context.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def execute_input(self, context, st, picked=None):
        """Lance la commande saisie (ou la suggestion cliquée) ; ligne vide : répète la dernière."""
        text = st["text"].strip()
        if picked is not None:
            entry = picked
        elif text:
            sugg = cmd_suggest(text)
            use_sel = 0 if st.get("tab") is not None else st["sel"]    # après Tab, le texte est déjà le nom complet
            entry = sugg[min(use_sel, len(sugg) - 1)] if sugg else None
        else:
            entry = cmd_by_key(_CMD["last"]) if _CMD["last"] else None
        self.finish(context, None)
        if entry is None:
            msg = f'Unknown command "{text}"' if text else "No command to repeat yet"
            cmd_log(msg)
            self.report({'WARNING'}, msg)
            return {'CANCELLED'}
        err = cmd_run(context, entry)
        if err:
            cmd_log(err)
            self.report({'WARNING'}, err)
        return {'FINISHED'}

    def cancel(self, context):
        cmd_close()


def _cmd_font(size):
    try:
        blf.size(0, size)
    except TypeError:
        blf.size(0, size, 72)


def _cmd_quad(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y0), (x1, y1), (x0, y1)]


def cmd_fit_lines(parts, maxw, max_lines=3):
    """Répartit des fragments [(texte, couleur)] sur plusieurs lignes d'au plus maxw pixels (tronque avec …)."""
    lines, cur, w = [], [], 0.0
    sep = "   ·   "
    sw = blf.dimensions(0, sep)[0]
    for text, col in parts:
        tw = blf.dimensions(0, text)[0]
        if tw > maxw:
            while text and blf.dimensions(0, text + "…")[0] > maxw:
                text = text[:-1]
            text, tw = text + "…", blf.dimensions(0, text + "…")[0]
        if cur and w + sw + tw > maxw:
            lines.append(cur)
            cur, w = [], 0.0
        if cur:
            cur.append((sep, 2))
            w += sw
        cur.append((text, col))
        w += tw
    if cur:
        lines.append(cur)
    return lines[:max_lines]


CMD_CHIP_KEYS = {"Esc": ('ESC', ""), "Enter": ('RET', ""), "Enter/Space": ('RET', ""), "Tab": ('TAB', ""), "Space": ('SPACE', " "), "Backspace": ('BACK_SPACE', "")}


class CmdKeyEvent:
    """Touche simulée (clic sur une puce de la barre) : reprend la position de la souris de l'événement réel."""

    def __init__(self, real, etype, uni=""):
        self._real = real
        self.type, self.value, self.unicode = etype, 'PRESS', uni
        self.shift = self.ctrl = self.alt = self.oskey = False
        self.is_repeat = False

    def __getattr__(self, name):
        return getattr(self._real, name)


def cmd_chip_key(key):
    """Touche (type, caractère) qu'une puce de la barre représente, ou None (X/Y/Z, Shift... : non cliquable)."""
    if key in CMD_CHIP_KEYS:
        return CMD_CHIP_KEYS[key]
    if len(key) == 1 and key.isalpha() and key.isupper():
        return key, key.lower()
    return None


def cmd_hit(area, mx_abs, my_abs):
    """Élément cliquable de la barre sous la souris : (kind, valeur) ou None."""
    try:
        region = find_window_region(area, mx_abs, my_abs)
        if region is None:
            return None
        x, y = mx_abs - region.x, my_abs - region.y
        for x0, y0, x1, y1, kind, val in tuple(_CMD["hit"].get(area.as_pointer(), ())) + tuple(_VBAR["hit"].get(area.as_pointer(), ())):
            if x0 <= x <= x1 and y0 <= y <= y1:
                return kind, val
    except (AttributeError, ReferenceError, RuntimeError):
        pass
    return None


def new_view_dialog_later(context):
    """« + » : ouvre le menu des vues un instant après le clic, quand le bouton de la souris est déjà relâché
    (sinon le relâchement valide ou ferme aussitôt le menu : il fallait maintenir le clic)."""
    win, area = context.window, context.area
    region = next((r for r in area.regions if r.type == 'WINDOW'), None) if area is not None else None

    def run():
        try:
            with bpy.context.temp_override(window=win, area=area, region=region):
                bpy.ops.wm.call_menu(name=DESSIN_MT_named_views.bl_idname)
        except (RuntimeError, ReferenceError, TypeError):
            pass
        return None
    bpy.app.timers.register(run, first_interval=0.25)


def cmd_click_idle(context, event):
    """Clic sur une puce alors qu'aucune commande n'est en cours (outil armé ou Select) : True si le clic est consommé."""
    hit = cmd_hit(context.area, event.mouse_x, event.mouse_y)
    if hit is None:
        return False
    kind, val = hit
    try:
        if kind == 'open':
            bpy.ops.dessin.command_line('INVOKE_DEFAULT')
        elif kind == 'key' and val == "Esc":
            bpy.ops.dessin.tool_exit()
        elif kind == 'key' and val in ("F", "C") and DessinBase.active_tool_id(context) == "dessin.trim_tool":
            bpy.ops.dessin.trim_mode(mode='FENCE' if val == "F" else 'CROSSING')
        elif tab_click(context, kind, val):
            pass                               # onglet d'une mise en page, ou retour au modèle depuis une mise en page
        elif kind == 'view':
            bpy.ops.dessin.view_restore('INVOKE_DEFAULT', name=val)
        elif kind == 'viewmenu':
            new_view_dialog_later(context)
        elif kind == 'osnap':
            vbar_toggle(context, val)
        elif kind == 'mode':
            mode_click(context, val)
    except RuntimeError:
        pass
    return True


def _cmd_theme():
    """Couleurs du thème Blender de l'utilisateur (fond d'en-tête, texte, sélection de menu)."""
    try:
        th = bpy.context.preferences.themes[0]
        ui = th.user_interface
        bg = tuple(th.view_3d.space.header)
        fg = tuple(ui.wcol_menu_item.text)
        sel = tuple(ui.wcol_menu_item.inner_sel)
        sel_t = tuple(ui.wcol_menu_item.text_sel)
        acc = tuple(ui.wcol_menu_item.inner_sel)
    except (AttributeError, IndexError, TypeError):
        bg, fg, sel, sel_t, acc = (0.15, 0.15, 0.15, 1.0), (0.9, 0.9, 0.9, 1.0), (0.28, 0.45, 0.7, 1.0), (1, 1, 1, 1), (0.42, 0.65, 1.0, 1.0)

    def mix(a, b, k):
        return (a[0] * k + b[0] * (1 - k), a[1] * k + b[1] * (1 - k), a[2] * k + b[2] * (1 - k))
    accent = tuple(min(1.0, c * 0.55 + 0.45) for c in acc[:3])
    return {"bg": (*bg[:3], 0.93), "fg": (*fg[:3], 1.0), "dim": (*mix(fg, bg, 0.58), 1.0), "faint": (*mix(fg, bg, 0.38), 1.0),
            "sel": (*sel[:3], 1.0), "sel_t": (*sel_t[:3], 1.0), "acc": (*accent, 1.0),
            "chip": (*mix(fg, bg, 0.14), 1.0), "line": (*mix(fg, bg, 0.22), 1.0),
            "warn": (*mix((1.0, 0.62, 0.22), fg, 0.8), 1.0)}


def _blend_on():
    """Rétablit le mélange alpha avant un tracé. Blender le coupe après CHAQUE texte (blf.draw) : sans cela, tout ce qui
    est dessiné après un texte (la pastille des modes après les onglets, une info-bulle, la ligne de commande après la
    liste de suggestions) est écrit sans mélange, avec son opacité de 0,93 telle quelle, et paraît plus transparent que
    les pastilles dessinées avant tout texte. Les traits lissés des icônes en ont besoin aussi."""
    gpu.state.blend_set('ALPHA')


def _cmd_bold(on):
    """Active / désactive le gras du texte (police variable de Blender 4+)."""
    try:
        (blf.enable if on else blf.disable)(0, blf.BOLD)
    except (AttributeError, TypeError, RuntimeError):
        pass


def _cmd_rrect(x0, y0, x1, y1, r, n=7):
    """Triangles d'un rectangle aux coins arrondis (éventail autour du centre)."""
    r = max(0.0, min(r, (x1 - x0) / 2.0, (y1 - y0) / 2.0))
    ring = []
    for cx, cy, a0 in ((x1 - r, y1 - r, 0.0), (x0 + r, y1 - r, 90.0), (x0 + r, y0 + r, 180.0), (x1 - r, y0 + r, 270.0)):
        for k in range(n + 1):
            a = math.radians(a0 + 90.0 * k / n)
            ring.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    c = ((x0 + x1) / 2.0, (y0 + y1) / 2.0)
    out = []
    for k in range(len(ring)):
        out += [c, ring[k], ring[(k + 1) % len(ring)]]
    return out


CMD_FRAG = None


def cmd_parse_prompt(txt):
    """Invite d'un outil -> (titre, phrase principale, détails, puces [(touche, libellé)], extras [(texte, fort)])."""
    import re
    global CMD_FRAG
    if CMD_FRAG is None:
        CMD_FRAG = re.compile(r"(?:(?<=\s)|^)(Esc|Enter/Space|Enter|Tab|Space|Backspace|[A-Z]):\s*([^,;·()\[\]]+?)(?=,\s|\s{2,}|\s·|$)")
    segs = [t.strip() for t in txt.split("   |   ") if t.strip()]
    if not segs:
        return "", "", [], [], []
    title, _sep, rest = segs[0].partition(" : ")
    if not _sep:
        title, rest = "", segs[0]
    chips, details = [], []

    def take(m):
        inner = m.group(1).strip()
        if len(inner) > 24:
            details.append(inner)                  # long : détail sous forme de texte discret
        else:
            chips.append(inner)
        return " "

    def take2(m):
        chips.append(m.group(1) + ": " + m.group(2).strip())
        return " "
    rest = re.sub(r"\[([^\]]*)\]", take, rest)
    rest = re.sub(r"\(([^)]*)\)", take, rest)
    rest = CMD_FRAG.sub(take2, rest)
    rest = re.sub(r"\s+", " ", rest).strip(" ·,")
    extras = []
    for sgm in segs[1:]:
        m = re.match(r"S: snap (\w+)(?: \[(.*)\])?", sgm)
        if m:
            chips.append("S: snap " + m.group(1) + (" · " + m.group(2) if m.group(2) else ""))
            continue
        if sgm.startswith("[") and sgm.endswith("]"):
            chips.append(sgm[1:-1])
            continue
        left = CMD_FRAG.sub(take2, sgm)
        left = re.sub(r"\s+", " ", left).strip(" ·,")
        if left:
            extras.append((left, left.startswith("typed:") or left[:1].isdigit()))
    for k, c in enumerate(chips):
        if c.startswith("Esc: cancel") and not any(x.startswith("Enter") for x in chips):
            pass
    out = []
    for c in chips:
        k, _s, lab = c.partition(": ")
        out.append((k, lab) if _s else ("", c))
    return title, rest, details, out, extras


def bar_layout(ptr, region_w, left, right, sc, vw, cw, mw, hc, mh=0.0):
    """Position des trois pastilles du bas (onglets de vue, ligne de commande, boutons de mode).
    Une seule ligne si tout tient entre la barre d'outils et la barre latérale ; sinon la ligne de commande passe
    au-dessus, seule, et les onglets + modes restent côte à côte en bas (leur forme réduite, choisie par bars_compact,
    le garantit ; ils ne s'empilent plus que dans une vue trop étroite pour quoi que ce soit).
    Retourne {"views": (x, y), "cmd": (x, y), "modes": (x, y)} (bas-gauche de chaque pastille)."""
    G = 18 * sc
    hp = 11 * sc * 1.6 + 11 * sc                       # hauteur d'une pastille d'onglets / de modes
    heights = {"views": hp, "modes": mh or hp, "cmd": hc}
    avail = region_w - left - right - 24 * sc
    parts = [(k, w) for k, w in (("views", vw), ("cmd", cw), ("modes", mw)) if w > 0]
    out = {}
    total = sum(w for _k, w in parts) + G * max(0, len(parts) - 1)
    if not (_GROUP["cmd_row"].get(ptr) and cw > 0) and total <= avail:
        x = group_center(region_w, left, right, total, sc) - total / 2.0
        for k, w in parts:
            out[k] = (x, 16 * sc + (0.0 if k == "cmd" else max(0.0, (hc - hp) / 2.0)))
            x += w + G
        return out
    rows = []
    low = [(k, w) for k, w in parts if k != "cmd"]
    if len(low) == 2 and low[0][1] + G + low[1][1] > avail:
        rows = [[low[1]], [low[0]]]                   # très étroit : modes en bas, onglets au-dessus
    elif low:
        rows = [low]
    if cw > 0:
        rows.append([("cmd", cw)])
    y = 16 * sc
    for row in rows:
        total = sum(w for _k, w in row) + G * (len(row) - 1)
        x = group_center(region_w, left, right, total, sc) - total / 2.0
        rowh = max(heights[k] for k, _w in row)
        for k, w in row:
            out[k] = (x, y + (rowh - heights[k]) / 2.0)     # (vues à côté de deux rangées d'icônes : centrées en hauteur)
            x += w + G
        y += rowh + 8 * sc
    return out


def cmd_fixed_width(avail, share, own_row, vw, mw, sc, typing=False):
    """Largeur de la ligne de commande dans une vue réduite. avail : place libre entre les panneaux ; share : ce qu'il reste à côté des onglets
    et des modes ; own_row : elle est seule sur sa ligne, au-dessus ; vw, mw : largeurs des onglets et de la barre de
    modes (0 si absents) ; typing : on est en train de taper une commande (il faut alors la place d'écrire)."""
    G = 18 * sc
    if own_row:
        if vw and mw:
            below = vw + G + mw if vw + G + mw <= avail else max(vw, mw)      # même règle que bar_layout
        else:
            below = vw or mw
        w = min(below, avail) if below else min(avail, 760 * sc)
        w = max(w, min(120 * sc, avail))
    else:
        w = max(160.0, min(share, mw or 760 * sc))
    if typing:
        w = max(w, min(avail, 300 * sc))
    return w


def group_center(width, left, right, groupw, sc):
    """Centre horizontal du groupe (onglets + commande + modes) : au milieu de la vue, mais jamais sous la barre d'outils
    ni sous la barre latérale (même très large)."""
    lo = left + 12 * sc + groupw / 2.0
    hi = width - right - 12 * sc - groupw / 2.0
    c = width / 2.0
    if lo > hi:
        return (left + width - right) / 2.0
    return min(max(c, lo), hi)


def cmd_bar_cb():
    context = bpy.context
    area, region = context.area, context.region
    if area is None or region is None or not pref("cmd_line"):
        return
    ptr = area.as_pointer()
    st = _CMD["input"] if (_CMD["input"] is not None and _CMD["input"]["area"] == ptr) else None
    prompt = _CMD["prompt"].get(ptr)
    tid = DessinBase.active_tool_id(context)
    if (not prompt and st is None and tid and tid.startswith("dessin.") and _CMD["op"].get(ptr) is None
            and tid not in _SELECT_TOOL_IDS):
        prompt = _CMD.get("tool_prompt", {}).get(tid)      # outil sélectionné mais pas encore « armé » par la souris
    if tid and tid.startswith("dessin.") and tid not in _SELECT_TOOL_IDS:
        _CMD["last"] = "tool:" + tid
    try:
        sysp0 = context.preferences.system
        base = max(1.0, (sysp0.ui_scale or 1.0) * ((sysp0.dpi or 72) / 72.0))   # sans pixel_size : blf le gère déjà (Retina)
    except (AttributeError, ReferenceError):
        base = 1.0
    sc = (1.0 + (base - 1.0) * 0.5) * CMD_SIZE_BASE * (pref("cmd_size") or 100) / 100.0
    size = 11 * sc
    _cmd_font(size)
    lh = size * 1.6
    space = area.spaces.active
    sysp = context.preferences.system
    left, right = 0.0, 0.0
    if getattr(sysp, "use_region_overlap", False):
        for r in area.regions:
            if r.type == 'TOOLS' and getattr(space, "show_region_toolbar", True):
                left += r.width
            elif r.type == 'UI' and getattr(space, "show_region_ui", True):
                right += r.width
    cx = region.width / 2.0                                   # centre du viewport (toute la largeur, panneaux compris)
    vw0 = _GROUP["views"].get(ptr, 0.0)
    mw0 = modes_total_w(context, ptr, sc)
    # le groupe (onglets de vue + barre de commande + boutons de mode) est centré : il doit tenir entre les panneaux.
    # Vue trop étroite : la ligne de commande passe sur sa propre ligne, au-dessus des onglets et des modes (rien ne se chevauche)
    avail = region.width - left - right - 24 * sc          # place libre entre la barre d'outils et la barre latérale
    share = avail - ((vw0 + 18 * sc) if vw0 else 0.0) - mw0
    # vue réduite (icônes + initiales) : la ligne de commande est toujours en haut, seule sur sa ligne, même si elle
    # tiendrait entre les deux petites barres
    own_row = share < 360 * sc or bool(_GROUP["compact"].get(ptr))
    if _GROUP["cmd_row"].get(ptr) != own_row:
        _GROUP["cmd_row"][ptr] = own_row
        area.tag_redraw()
    # Vue large : la ligne de commande garde sa largeur d'origine, celle de son texte (jusqu'à 760 px).
    # Vue réduite (modes en icônes, vues en initiales) : largeur FIXE, pour des proportions nettes. Elle ne dépend plus du
    # texte (il se raccourcit, les puces passent à la ligne) et vaut exactement celle de l'ensemble des barres du dessous
    # (onglets + modes s'ils partagent une ligne, sinon la plus large des deux) : elle ne les dépasse jamais.
    fixed_w = bool(_GROUP["compact"].get(ptr))
    if fixed_w:
        maxw = cmd_fixed_width(avail, share, own_row, vw0, modes_layout(context, ptr, sc)[2] if mw0 else 0.0, sc, st is not None)
    else:
        maxw = max(160.0, min(avail if own_row else share, 760 * sc))
    th = _cmd_theme()
    padx = 14 * sc
    gap = 8 * sc
    chip_pad = 6 * sc
    pv = 5.5 * sc                                             # marge verticale (style « dock »)
    rad, irad = 11 * sc, 8 * sc                              # rayons : conteneur / éléments
    ch = lh - 2 * sc                                          # hauteur d'une puce
    W = lambda t: blf.dimensions(0, t)[0]

    def chip_w(k, lab):
        return chip_pad * 2 + W(k) + (W(" ") + W(lab) if lab else 0)

    def shrink(t, w):
        if W(t) <= w:
            return t
        while t and W(t + "…") > w:
            t = t[:-1]
        return t + "…"

    # contenu : lignes de pilule (liste d'éléments ("t", texte, couleur) ou ("c", touche, libellé))
    hits = []
    mouse = _CMD["mouse"].get(ptr)
    lines, sugg_rows = [], []
    if st is not None:
        text = st["text"]
        lab = "Command"
        row = [("t", lab, "dim"), ("t", text + "▏", "fg")]
        last = cmd_by_key(_CMD["last"]) if _CMD["last"] else None
        tail = [("c", "Enter", "repeat " + last["label"], 'run')] if (not text and last is not None) else [("c", "Enter", "", 'run')]
        lines.append((row, tail))
        sugg = cmd_suggest(text)
        if st.get("tab") is not None:
            sugg = cmd_suggest(st["tab"])
        for i, e in enumerate(sugg):
            sugg_rows.append((i == st["sel"], e["label"], e.get("alias") or (e["names"][1] if len(e["names"]) > 1 else "")))
    elif prompt:
        title, body, details, chips, extras = cmd_parse_prompt(prompt)
        row = []
        if title:
            row.append(("t", title, "acc", True))            # nom de la commande : couleur d'accent, gras
        if body:
            row.append(("t", body, "acc", True))             # phrase principale : même couleur, gras
        for d_ in details:
            row.append(("t", d_, "dim"))                     # détails : discrets
        for t, strong in extras:
            row.append(("t", t, "fg" if strong else "faint"))
        lines.append((row, [("c", k, lab, 'key' if cmd_chip_key(k) else None) for k, lab in chips]))
    elif tid and tid.startswith("dessin.") and tid != DESSIN_TT_selection_boite.bl_idname:
        cls = cmd_tool_class(tid)
        name = cmd_clean_label(cls.bl_label) if cls is not None else tid
        hint = (getattr(cls, "dessin_hint", "") or (cls.bl_description if cls is not None else ""))
        note = cmd_notice_text()
        chips_t = [("c", "Esc", "leave", 'key')]
        if tid == "dessin.trim_tool":
            try:
                fence = bpy.context.scene.dessin.trim_mode == 'FENCE'
            except (AttributeError, ReferenceError):
                fence = True
            hint = ("Drag a fence line across the parts to remove, or click one part" if fence else
                    "Drag a crossing box over the parts to remove, or click one part") + "  ·  cutting curves: select them first (none: all)"
            chips_t = [("c", "F", ("● " if fence else "") + "Fence", 'key'), ("c", "C", ("" if fence else "● ") + "Crossing", 'key')] + chips_t
        if note:
            en = cmd_clean_label(cls.__dict__.get("dessin_en_label", cls.bl_label)) if cls is not None else name
            body = note[len(en) + 1:].strip() if note.startswith(en + ":") else note      # le nom est déjà écrit devant
            lines.append(([("t", name, "acc", True), ("t", body, "warn", True)], chips_t))     # la commande vient de dire pourquoi elle n'a rien fait
        else:
            lines.append(([("t", name, "acc", True), ("t", hint, "dim")], chips_t))
    elif cmd_notice_text():
        lines.append(([("t", "›", "dim"), ("t", cmd_notice_text(), "warn", True)], []))
    else:
        last = cmd_by_key(_CMD["last"]) if _CMD["last"] else None
        key = pref("cmd_key")
        kname = {k: n for k, n, _d in CMD_KEY_ITEMS}.get(key, "")
        row = [("t", "›", "dim"), ("t", "Type a command", "faint")]
        if last is not None and key != 'NONE':
            row.append(("t", "repeat " + last["label"], "faint"))
        lines.append((row, [("c", kname, "", 'open')] if key != 'NONE' else []))

    # mise en page : une ligne ; les puces passent sur une 2e ligne si elles ne tiennent pas
    row, chips = lines[0]
    if lang() == 'FR':
        chips = [(c[0], c[1], tr_text(c[2]), c[3]) for c in chips]
    inner = maxw - 2 * padx
    row_items = []
    used = 0.0
    for item in row:
        a, b = tr_text(item[1]), item[2]
        bold = len(item) > 3 and item[3]
        _cmd_bold(bold)
        t = shrink(a, max(40 * sc, inner - used - (gap if used else 0)))
        row_items.append((t, b, bold))
        used += (gap if used else 0) + W(t)
        _cmd_bold(False)
    chips_w = sum(chip_w(c[1], c[2]) + gap for c in chips)
    two_rows = used + (gap + chips_w if chips else 0) > inner
    if st is not None:
        used = max(used, 300 * sc)
    chip_rows = []
    if two_rows and chips:            # les puces passent sous le texte ; si elles ne tiennent pas, elles continuent sur d'autres lignes
        chip_rows, curw = [[]], 0.0
        for c in chips:
            cw_ = chip_w(c[1], c[2])
            if chip_rows[-1] and curw + gap + cw_ > inner:
                chip_rows.append([])
                curw = 0.0
            curw += cw_ + (gap if chip_rows[-1] else 0.0)
            chip_rows[-1].append(c)
    nrows = 1 + len(chip_rows) if chip_rows else 1
    if fixed_w:
        width = maxw                # vue réduite : largeur fixe (voir cmd_fixed_width), le contenu s'y adapte
    else:
        rows_w = max((sum(chip_w(c[1], c[2]) for c in r_) + gap * (len(r_) - 1) for r_ in chip_rows), default=0.0)
        width = min(maxw, max(used + (0 if two_rows else (gap + chips_w if chips else 0)), rows_w if two_rows else 0) + 2 * padx)
    h = nrows * lh + 2 * pv + (nrows - 1) * 4 * sc
    if _GROUP["cmd"].get(ptr) != width or _GROUP["cmd_h"].get(ptr) != h:
        area.tag_redraw()          # les onglets / boutons de mode se calent sur ces valeurs : on se redessine une fois, sans attendre la souris
    _GROUP["cmd"][ptr] = width
    _GROUP["cmd_h"][ptr] = h
    vw = _GROUP["views"].get(ptr, 0.0)
    mw_raw = modes_layout(context, ptr, sc)[2] if mw0 else 0.0
    x0, y0 = bar_layout(ptr, region.width, left, right, sc, vw, width, mw_raw, h,
                        modes_height(sc, _GROUP["compact"].get(ptr) or 0))["cmd"]
    shader = get_shader('2D')
    gpu.state.blend_set('ALPHA')

    def fill(col, tris):
        _blend_on()                    # (un texte dessiné juste avant a coupé le mélange alpha)
        shader.bind()
        shader.uniform_float("color", col)
        batch_for_shader(shader, 'TRIS', {"pos": tris}).draw(shader)

    def put(x, y, text, col):
        blf.color(0, *col)
        blf.position(0, x, y, 0)
        blf.draw(0, text)

    # liste de suggestions (au-dessus de la pilule, arrondie)
    if sugg_rows:
        sh = len(sugg_rows) * lh + 8 * sc
        sy0 = y0 + h + 6 * sc
        fill(th["line"], _cmd_rrect(x0 - 1, sy0 - 1, x0 + width + 1, sy0 + sh + 1, rad + 1))
        fill(th["bg"], _cmd_rrect(x0, sy0, x0 + width, sy0 + sh, rad))
        yy = sy0 + sh - 4 * sc - lh
        for si, (sel, lab, alias) in enumerate(sugg_rows):
            hits.append((x0 + 5 * sc, yy, x0 + width - 5 * sc, yy + lh, 'sugg', si))
            if mouse is not None and hits[-1][0] <= mouse[0] <= hits[-1][2] and hits[-1][1] <= mouse[1] <= hits[-1][3]:
                sel = True
            if sel:
                fill(th["sel"], _cmd_rrect(x0 + 5 * sc, yy, x0 + width - 5 * sc, yy + lh, irad))
            col_t = th["sel_t"] if sel else th["dim"]
            ty = yy + (lh - size) / 2.0 + size * 0.12
            put(x0 + padx, ty, lab, col_t)
            if alias:
                put(x0 + width - padx - W(alias), ty, alias, th["sel_t"] if sel else th["faint"])
            yy -= lh
    # pilule
    fill(th["line"], _cmd_rrect(x0 - 1, y0 - 1, x0 + width + 1, y0 + h + 1, rad + 1))
    fill(th["bg"], _cmd_rrect(x0, y0, x0 + width, y0 + h, rad))
    ty = y0 + h - pv - lh + (lh - size) / 2.0 + size * 0.12
    x = x0 + padx
    for t, colname, bold in row_items:
        _cmd_bold(bold)
        put(x, ty, t, th[colname])
        x += W(t) + gap
        _cmd_bold(False)
    def draw_chips(chip_list, x, cy):
        for _k, k, lab, act in chip_list:
            w = chip_w(k, lab)
            rect = (x, cy + 1 * sc, x + w, cy + 1 * sc + ch)
            over = False
            if act:
                hits.append((*rect, act, k))
                over = mouse is not None and rect[0] <= mouse[0] <= rect[2] and rect[1] <= mouse[1] <= rect[3]
            fill(th["line"], _cmd_rrect(rect[0], rect[1], rect[2], rect[3], 6 * sc))
            fill(th["sel"] if over else th["chip"], _cmd_rrect(rect[0] + 1, rect[1] + 1, rect[2] - 1, rect[3] - 1, 6 * sc))
            cty = cy + (lh - size) / 2.0 + size * 0.12
            put(x + chip_pad, cty, k, th["sel_t"] if over else th["fg"])
            if lab:
                put(x + chip_pad + W(k) + W(" "), cty, lab, th["sel_t"] if over else th["dim"])
            x += w + gap

    if chip_rows:
        for r_i, row_chips in enumerate(chip_rows):
            draw_chips(row_chips, x0 + padx, y0 + h - pv - lh - (r_i + 1) * (lh + 4 * sc))
    elif chips:
        total = sum(chip_w(c[1], c[2]) for c in chips) + gap * (len(chips) - 1)
        draw_chips(chips, x0 + width - padx - total if st is not None else x, y0 + h - pv - lh)
    _CMD["hit"][ptr] = hits
    gpu.state.blend_set('NONE')


CMD_SIZE_BASE = 0.9      # taille des barres au réglage 100 % (l'ancien 90 %, jugé plus juste à l'écran)
_VBAR = {"hit": {}, "handle": None}
_GROUP = {"cmd": {}, "views": {}, "cmd_h": {}, "cmd_row": {}, "compact": {}}


def vbar_toggle_state(context, key):
    try:
        return bool(getattr(context.scene.dessin, key))
    except (AttributeError, ReferenceError):
        return False


def vbar_toggle(context, key):
    """Bascule une option OSnap (clé = nom de la propriété de scene.dessin)."""
    st = context.scene.dessin
    setattr(st, key, not getattr(st, key))
    for win in context.window_manager.windows:
        for a in win.screen.areas:
            if a.type == 'VIEW_3D':
                a.tag_redraw()


def call_menu_later(context, name):
    """Ouvre un menu un instant après le clic (le bouton de la souris est alors relâché)."""
    win, area = context.window, context.area
    region = next((r for r in area.regions if r.type == 'WINDOW'), None) if area is not None else None

    def run():
        try:
            with bpy.context.temp_override(window=win, area=area, region=region):
                bpy.ops.wm.call_menu(name=name)
        except (RuntimeError, ReferenceError, TypeError):
            pass
        return None
    bpy.app.timers.register(run, first_interval=0.2)


MODE_BUTTONS = (("grid_snap", "Grid Snap", "Grid Snap (F9): the cursor snaps to the grid of the construction plane (arrow: snap spacing)"),
                ("ortho", "Ortho", "Ortho (F8): the cursor stays horizontal or vertical"),
                ("polar", "Polar", "Polar tracking (F10): the cursor snaps to angle steps (arrow: choose the step)"),
                ("osnap_enable", "OSnap", "Object snaps on / off (F3): End, Mid, Cen... (arrow: choose the snaps; Shift + click on one: one shot)"),
                ("smart_tracks", "SmartTrack", "Smart tracks on / off: alignment guides from points you hover"),
                ("gumball", "Gumball", "Gumball on / off: move / rotate / scale handles on the selection (arrow: Gumball menu, orientation Global / Local / View, Snappy Dragging = object snaps while dragging)"),
                ("auto_cplane", "Auto CPlane", "Auto CPlane on / off: the construction plane follows the planar object or face you select (arrow: Sticky option, back to the ground plane)"),
                ("cmd_type", "Quick Type", "Quick Type on / off: typing a letter starts the command line (letters then lose Blender's own shortcuts; Space still opens it)"))
MODE_ARROWS = {"grid_snap": "gridsnapmenu", "polar": "polarmenu", "osnap_enable": "osnapmenu", "gumball": "gumballmenu",
               "auto_cplane": "autocplanemenu"}
OSNAP_LABELS = dict(OSNAP_BAR)


def grid_step_text(context):
    """Pas de Grid Snap écrit dans l'unité affichée de la scène : « 5 mm »."""
    try:
        v = grid_snap_shown(context.scene)
        label = unit_info(context.scene)[1]
    except (AttributeError, ReferenceError, TypeError, ValueError):
        return ""
    return f"{v:.6g}" + (f" {label}" if label else "")


def mode_label(context, key, label):
    """Libellé d'un bouton de mode ; OSnap annonce les accrochages ponctuels armés (« OSnap: Mid », « OSnap: End+Mid »)."""
    if key == "osnap_enable":
        labs = [OSNAP_LABELS.get(k, k) for k in oneshot_keys()]
        if labs:
            return "OSnap: " + ("+".join(labs) if len(labs) <= 3 else "+".join(labs[:3]) + "…")
    return label


def mode_arrow_tip(context, key):
    """Info-bulle de la flèche d'un bouton de mode (clé du bouton)."""
    try:
        if key == "polar":
            st = context.scene.dessin
            return ("Polar step: " + {i.identifier: i.name for i in st.bl_rna.properties["polar_angle"].enum_items}
                    .get(st.polar_angle, "") + " (click to change)")
        if key == "grid_snap":
            return "Snap spacing: " + grid_step_text(context) + " (click to change)"
    except (AttributeError, ReferenceError, KeyError):
        pass
    return {"osnap_enable": "Object snaps: choose which ones are on  ·  Shift + click: one shot, only the snaps clicked this way act for the next point",
            "gumball": "Gumball menu: relocate, reset, orientation (Global, Local, Normal, View...), Snappy Dragging (object snaps while dragging) or Smooth Dragging, settings",
            "auto_cplane": "Auto CPlane menu: Sticky option, back to the ground plane"}.get(key, "")


def point_requested(context):
    """Une commande attend un point : commande en cours dans une vue, ou outil de dessin armé (pas Select / Move)."""
    if any(op is not None for op in _CMD["op"].values()):
        return True
    tid = DessinBase.active_tool_id(context)
    return bool(tid and tid.startswith("dessin.") and tid not in _SELECT_TOOL_IDS)


def oneshot_validate(context):
    """Un accrochage ponctuel ne survit pas à sa commande : plus rien n'attend de point, il s'éteint (Maj tenu aussi)."""
    if oneshot_shown() and not point_requested(context):
        oneshot_reset()


def osnap_hold_event(context, event):
    """Maj tenu au-dessus des cases OSnap (la barre d'état) pendant qu'une commande demande un point : elles paraissent
    toutes décochées, pour cliquer celles que l'on veut (accrochage ponctuel) ; Maj relâché, ou la souris sortie de la
    barre, sans avoir rien cliqué : elles reviennent. Appelé pour chaque évènement vu par la commande en cours, et par le
    raccourci Maj de la fenêtre quand aucune commande ne tourne. True si l'affichage a changé."""
    if event.type in {'LEFT_SHIFT', 'RIGHT_SHIFT'} and event.value in {'PRESS', 'RELEASE'}:
        shift = event.value == 'PRESS'
    else:
        shift = bool(event.shift)
    if not shift:
        return oneshot_hold_set(False) if oneshot_hold() else False
    return oneshot_hold_set(mouse_over_statusbar(context, event) and point_requested(context))


class DESSIN_OT_osnap_hold(bpy.types.Operator):
    """Maj enfoncé ou relâché, la souris sur la barre d'état : les cases OSnap se décochent le temps de choisir un
    accrochage ponctuel (voir osnap_hold_event). L'évènement continue sa route."""
    bl_idname = "dessin.osnap_hold"
    bl_label = "Object Snaps: hold Shift"
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        changed = False
        try:
            changed = osnap_hold_event(context, event)
        except (AttributeError, RuntimeError, ReferenceError, TypeError):
            pass
        # rien à faire (le cas de presque tous les appuis sur Maj) : l'évènement passe comme si ce raccourci n'existait pas
        return {'FINISHED', 'PASS_THROUGH'} if changed else {'PASS_THROUGH'}


_OSNAP_HOLD_KEYMAPS = []


def register_osnap_hold_keys():
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon if wm is not None else None
    if kc is None:
        return
    km = kc.keymaps.new(name="Window", space_type='EMPTY')      # la barre d'état n'appartient à aucun éditeur
    for key in ('LEFT_SHIFT', 'RIGHT_SHIFT'):
        for value in ('PRESS', 'RELEASE'):
            kmi = km.keymap_items.new(DESSIN_OT_osnap_hold.bl_idname, key, value, any=True)
            _OSNAP_HOLD_KEYMAPS.append((km, kmi))


def unregister_osnap_hold_keys():
    for km, kmi in _OSNAP_HOLD_KEYMAPS:
        try:
            km.keymap_items.remove(kmi)
        except (RuntimeError, ReferenceError, TypeError):
            pass
    _OSNAP_HOLD_KEYMAPS.clear()


class DESSIN_OT_osnap_set(bpy.types.Operator):
    """Case d'un accrochage objet (barre d'état, menu OSnap) : un clic la coche ou la décoche ; Maj + clic pendant qu'une
    commande demande un point = accrochage ponctuel, comme dans Rhino (seules les cases cliquées ainsi agissent, pour ce
    point seulement)."""
    bl_idname = "dessin.osnap_set"
    bl_label = "Object Snap"
    bl_options = {'UNDO', 'INTERNAL'}      # une case cochée ou décochée reste un pas d'annulation, comme la case d'origine

    key: bpy.props.StringProperty()

    @classmethod
    def description(cls, context, properties):
        key = properties.key
        if key == "all":
            return "Turn every object snap on"
        if key == "none":
            return "Turn every object snap off (the check boxes; F3 / Disable switches them off without changing the boxes)"
        try:
            d = context.scene.dessin.bl_rna.properties["osnap_" + key].description
        except (AttributeError, KeyError, ReferenceError):
            d = ""
        if key in ONESHOT_KEYS:
            d += (".  While a command asks for a point: hold Shift over the boxes (they all clear), then click the snaps "
                  "you want: one shot, only they act for that point")
        return d

    def invoke(self, context, event):
        return self.apply(context, bool(event.shift), event)

    def execute(self, context):
        return self.apply(context, False)

    def apply(self, context, shift, event=None):
        try:
            st = context.scene.dessin
        except (AttributeError, ReferenceError):
            return {'CANCELLED'}
        key = self.key
        if key in ("all", "none"):
            oneshot_reset()
            for k in ONESHOT_KEYS:
                setattr(st, "osnap_" + k, key == "all")
        elif shift and key in ONESHOT_KEYS:
            if not point_requested(context):
                self.report({'INFO'}, tr_text("One-shot snap: start a command first, it applies to the next point picked"))
                return {'CANCELLED'}
            keys = oneshot_toggle(key)          # Maj + clic : cette case rejoint (ou quitte) les accrochages ponctuels
            if event is not None and mouse_over_statusbar(context, event):
                oneshot_hold_set(True)          # Maj est tenu au-dessus des cases : les autres restent décochées à l'écran
            if keys:
                names = " + ".join(OSNAP_LABELS.get(k, k) for k in keys)
                self.report({'INFO'}, tr_text(f"One-shot snap: {names} only, for the next point"))
            redraw_bars()
            return {'CANCELLED'}                # aucun réglage de la scène n'a changé : pas de pas d'annulation
        elif key in ONESHOT_KEYS and oneshot_shown():
            # les cases montraient l'accrochage ponctuel, pas les réglages : un clic simple y renonce, sans rien cocher ni
            # décocher (on ne bascule pas une case dont on ne voyait pas l'état)
            oneshot_reset()
            redraw_bars()
            return {'CANCELLED'}
        elif key and hasattr(st, "osnap_" + key):
            setattr(st, "osnap_" + key, not getattr(st, "osnap_" + key))
        else:
            return {'CANCELLED'}
        redraw_bars()
        return {'FINISHED'}


class DESSIN_MT_osnap(bpy.types.Menu):
    bl_idname = "DESSIN_MT_osnap"
    bl_label = "Object Snaps"

    def draw(self, context):
        lay = self.layout
        lay.operator_context = 'INVOKE_DEFAULT'      # invoke : l'opérateur lit la touche Maj (accrochage ponctuel)
        st = context.scene.dessin
        for key, label in OSNAP_BAR:
            if key == "project":
                lay.separator()
            op = lay.operator(DESSIN_OT_osnap_set.bl_idname, text=label,
                              icon='CHECKBOX_HLT' if osnap_shown(st, key) else 'CHECKBOX_DEHLT')
            op.key = key
        op = lay.operator(DESSIN_OT_osnap_set.bl_idname, text=tr_text("Disable (F3)"),
                          icon='CHECKBOX_HLT' if st.osnap_disable else 'CHECKBOX_DEHLT')
        op.key = "disable"
        lay.separator()
        lay.operator(DESSIN_OT_osnap_set.bl_idname, text=tr_text("All On")).key = "all"
        lay.operator(DESSIN_OT_osnap_set.bl_idname, text=tr_text("All Off")).key = "none"
        lay.separator()
        lay.label(text=tr_text("Shift + click: one shot (next point only)"))


class DESSIN_OT_grid_snap_set(bpy.types.Operator):
    """Turns Grid Snap on or off"""
    bl_idname = "dessin.grid_snap_set"
    bl_label = "Grid Snap"
    bl_options = {'INTERNAL'}

    on: bpy.props.BoolProperty(default=True)

    def execute(self, context):
        context.scene.dessin.grid_snap = self.on
        _redraw_all_areas()
        return {'FINISHED'}


class DESSIN_OT_grid_snap_step(bpy.types.Operator):
    """Sets the spacing of the Grid Snap points, in the unit of the scene"""
    bl_idname = "dessin.grid_snap_step"
    bl_label = "Snap Spacing"
    bl_options = {'INTERNAL'}

    value: bpy.props.FloatProperty(name="Snap Spacing", default=1.0, min=1e-6, precision=4,
                                   description="Spacing of the Grid Snap points, in the unit of the scene")
    ask: bpy.props.BoolProperty(default=False, options={'SKIP_SAVE'})

    def invoke(self, context, event):
        if self.ask:
            self.value = grid_snap_shown(context.scene)
            return context.window_manager.invoke_props_dialog(self, width=260)
        return self.execute(context)

    def draw(self, context):
        label = unit_info(context.scene)[1]
        self.layout.prop(self, "value", text=tr_text("Spacing") + (f" ({label})" if label else ""))

    def execute(self, context):
        if self.value <= 0.0:
            return {'CANCELLED'}
        grid_snap_store(context.scene, self.value)      # valeur lue dans l'unité affichée ; le réglage est en mètres
        _redraw_all_areas()
        return {'FINISHED'}


class DESSIN_MT_grid_snap(bpy.types.Menu):
    bl_idname = "DESSIN_MT_grid_snap"
    bl_label = "Grid Snap"

    def draw(self, context):
        lay = self.layout
        lay.operator_context = 'INVOKE_DEFAULT'
        st = context.scene.dessin
        op = lay.operator(DESSIN_OT_grid_snap_set.bl_idname, text=tr_text("Grid Snap On (F9)"), icon='RADIOBUT_ON' if st.grid_snap else 'RADIOBUT_OFF')
        op.on = True
        op = lay.operator(DESSIN_OT_grid_snap_set.bl_idname, text=tr_text("Grid Snap Off"), icon='RADIOBUT_OFF' if st.grid_snap else 'RADIOBUT_ON')
        op.on = False
        lay.separator()
        lay.label(text=tr_text("Snap spacing"))
        label = unit_info(context.scene)[1]
        cur = grid_snap_shown(context.scene)
        preset = False
        for v in GRID_SNAP_PRESETS:
            same = abs(v - cur) <= 1e-6 * max(1.0, abs(v))      # (le réglage est en simple précision : 0,1 y vaut 0,100000001)
            preset = preset or same
            op = lay.operator(DESSIN_OT_grid_snap_step.bl_idname, text=f"{v:g}" + (f" {label}" if label else ""),
                              icon='RADIOBUT_ON' if same else 'RADIOBUT_OFF')
            op.value = v
        lay.separator()
        op = lay.operator(DESSIN_OT_grid_snap_step.bl_idname, text=tr_text("Custom...") + ("" if preset else f" ({grid_step_text(context)})"),
                          icon='RADIOBUT_OFF' if preset else 'RADIOBUT_ON')
        op.ask = True


def mode_state(context, key):
    try:
        if key == "osnap_enable":
            return bool(oneshot_keys()) or not context.scene.dessin.osnap_disable
        if key == "smart_tracks":
            return bool(pref("smart_tracks"))
        if key == "cmd_type":
            return bool(pref("cmd_type"))
        return bool(getattr(context.scene.dessin, key))
    except (AttributeError, ReferenceError):
        return False


def mode_click(context, key):
    """Clic sur un bouton de mode de la barre (Ortho, Polar, accrochage, repérage)."""
    if key == 'polarmenu':
        call_menu_later(context, DESSIN_MT_polar_angle.bl_idname)
        return
    if key == 'osnapmenu':
        call_menu_later(context, DESSIN_MT_osnap.bl_idname)
        return
    if key == 'gridsnapmenu':
        call_menu_later(context, DESSIN_MT_grid_snap.bl_idname)
        return
    if key == 'gumballmenu':
        call_menu_later(context, DESSIN_MT_gumball.bl_idname)
        return
    if key == 'autocplanemenu':
        call_menu_later(context, DESSIN_MT_auto_cplane.bl_idname)
        return
    if key == "osnap_enable":
        if not oneshot_clear():                 # accrochage ponctuel armé : le clic y renonce, sans toucher au réglage
            vbar_toggle(context, "osnap_disable")
    elif key == "smart_tracks":
        try:
            context.preferences.addons[__package__].preferences.smart_tracks = not pref("smart_tracks")
        except (KeyError, AttributeError, ReferenceError):
            pass
    elif key == "cmd_type":       # même réglage que « Quick Type » des préférences (son update recrée les raccourcis)
        try:
            context.preferences.addons[__package__].preferences.cmd_type = not pref("cmd_type")
        except (KeyError, AttributeError, ReferenceError):
            pass
    else:
        vbar_toggle(context, key)
    for win in context.window_manager.windows:
        for a in win.screen.areas:
            if a.type == 'VIEW_3D':
                a.tag_redraw()


class DESSIN_MT_polar_angle(bpy.types.Menu):
    bl_idname = "DESSIN_MT_polar_angle"
    bl_label = "Polar increment"

    def draw(self, context):
        st = context.scene.dessin
        for item in st.bl_rna.properties["polar_angle"].enum_items:
            self.layout.prop_enum(st, "polar_angle", item.identifier)


_TIP = {"timer": False}


TIP_DELAY = 0.9      # s : la souris doit rester immobile sur le bouton avant que l'info-bulle apparaisse
TIP_HIDE = 9.0       # s : l'info-bulle disparaît d'elle-même (la souris a pu quitter la vue sans que l'on s'en aperçoive)


def _mode_tip_fresh(ptr):
    """Info-bulle comme dans Blender : elle apparaît quand la souris reste quelques instants sur le bouton, disparaît dès qu'elle bouge."""
    age = time.monotonic() - _CMD.get("mouse_t", {}).get(ptr, 0.0)
    if age > TIP_HIDE:
        return False
    wait = (TIP_DELAY - age) if age < TIP_DELAY else (TIP_HIDE - age)
    due = time.monotonic() + wait
    pending = _TIP.get("due")
    if pending is None or pending > due + 0.02 or pending < time.monotonic():
        _TIP["due"] = due

        def later():
            if _TIP.get("due") is not None and _TIP["due"] <= time.monotonic() + 0.1:
                _TIP["due"] = None
            try:
                for win in bpy.context.window_manager.windows:
                    for a in win.screen.areas:
                        if a.type == 'VIEW_3D':
                            a.tag_redraw()
            except (AttributeError, RuntimeError):
                pass
            return None
        bpy.app.timers.register(later, first_interval=max(0.05, wait + 0.05))
    return age >= TIP_DELAY


MODE_ICON_W = 26.0          # largeur d'un bouton de mode réduit à son icône (vue étroite), à l'échelle 1
MODE_ICON_ARROW = 14.0      # largeur de sa flèche


def modes_icons(compact):
    """Les boutons de mode sont dessinés en icônes : vue réduite (compact >= 1), ou préférence « Mode bar: icons only »
    (icônes à toutes les largeurs ; les vues, elles, ne passent en initiales que si la place manque)."""
    return bool(compact) or bool(pref("mode_icons"))


def modes_rows(items, compact):
    """Rangées de boutons de la pastille des modes : une seule, ou deux quand les icônes ne tiennent plus sur une ligne à
    côté des vues (compact >= 2)."""
    if compact >= 2 and len(items) > 2:
        half = (len(items) + 1) // 2
        return [items[:half], items[half:]]
    return [items]


def modes_height(sc, compact):
    """Hauteur de la pastille des modes (deux rangées d'icônes en vue très étroite)."""
    h = 11 * sc * 1.6 + 11 * sc
    return 2 * h - 4 * sc if compact >= 2 else h


def modes_layout(context, ptr, sc, compact=None, fixed=False):
    """Largeurs des boutons de mode : ([(clé, libellé, largeur)], largeur d'une flèche, largeur totale du cadre).
    compact : 0 = libellés (icônes si la préférence « icons only » est cochée), 1 = icônes (vue réduite), 2 et 3 = icônes
    sur deux rangées (vue très étroite) ; None = l'état courant de la vue. fixed : libellés d'origine (sans « OSnap: Mid »),
    pour décider si la barre tient."""
    _cmd_font(11 * sc)
    if compact is None:
        compact = int(_GROUP["compact"].get(ptr) or 0)
    compact = int(compact)
    icons = modes_icons(compact)
    pad, gap = 9 * sc, 4 * sc
    arrow = (MODE_ICON_ARROW if icons else 24.0) * sc
    items = []
    for k, lab, _t in MODE_BUTTONS:
        if k != "cmd_type" or pref("cmd_line"):
            if not fixed:
                lab = mode_label(context, k, lab)
            w = MODE_ICON_W * sc if icons else blf.dimensions(0, lab)[0] + 2 * pad
            items.append((k, lab, w + (arrow if k in MODE_ARROWS else 0.0)))
    total = max(sum(w for _k, _l, w in row) + gap * (len(row) + 1) for row in modes_rows(items, compact)) if items else 0.0
    return items, arrow, total


def tab_short_labels(labels):
    """Onglets compacts (vue étroite) : l'initiale de chaque vue (Top Front Perspective Right -> T F P R), suivie du numéro
    final s'il y en a un (« Layout 2 » -> L2). Une initiale déjà prise : deux lettres (« Plan » après Perspective -> Pl),
    puis un rang. « + » reste « + »."""
    out, used = [], set()
    for lab in labels:
        t = (lab or "").strip()
        if t == "+" or not t:
            out.append(lab)
            continue
        m_ = re.search(r"(\d+)\s*$", t)
        num = m_.group(1) if m_ else ""
        word = t[:m_.start()].strip() if m_ else t
        base = word[:1].upper()                  # (vide si le nom n'est qu'un numéro : « 3 » reste « 3 »)
        cand = base + num
        if cand in used and len(word) > 1 and word[1].isalpha():
            cand = base + word[1].lower() + num
        k = 2
        while cand in used:
            cand = f"{base}{num or ''}.{k}"
            k += 1
        used.add(cand)
        out.append(cand)
    return out


def tabs_widths(labels, sc):
    """Largeur de chaque onglet et de leur pastille, pour ces libellés (police de la barre déjà réglée)."""
    padx, gap = 12 * sc, 2 * sc
    h = 11 * sc * 1.6 + 11 * sc
    widths = [blf.dimensions(0, t)[0] + 2 * padx for t in labels]
    if widths:
        widths[-1] = max(widths[-1], h)
    return widths, sum(widths) + gap * (len(labels) - 1) + 8 * sc


def tabs_for_level(tabs, level):
    """Onglets affichés selon le niveau de réduction : [(type, valeur, texte, actif, nom complet)].
    0 : noms complets ; 1 et 2 : initiales (T F P R +) ; 3 : seulement la vue active et « + » (son menu liste toutes les vues)."""
    full = [t[2] for t in tabs]
    texts = tab_short_labels(full) if level >= 1 else full
    out = [(k, v, txt, on, name) for (k, v, _t, on), txt, name in zip(tabs, texts, full)]
    if level >= 3 and len(out) > 2:
        out = ([t for t in out[:-1] if t[3]][:1] or out[:1]) + out[-1:]      # (aucune vue active : la première)
    return out


def bars_compact(context, ptr, avail, sc, tabs):
    """Niveau de réduction des barres du bas, selon la place libre entre la barre d'outils et la barre latérale. Les
    onglets de vue et la barre de modes restent toujours côte à côte, en bas ; les vues ne montent jamais au milieu.
      0 : onglets et modes tiennent côte à côte en toutes lettres (modes en icônes si la préférence « Mode bar: icons
          only » est cochée : les noms des vues restent alors entiers tant qu'ils tiennent à côté des icônes) ;
      1 : sinon, tout de suite en compact : vues en initiales (T F P R +), modes en icônes ;
      2 : vue très étroite : les icônes prennent deux rangées, à côté des vues ;
      3 : plus étroite encore : il ne reste que la vue active et « + » à côté des icônes.
    Ne dépend que de la largeur de la vue : ni de l'outil en cours, ni de l'état des boutons.
    tabs : les onglets, [(type, valeur, texte, actif)]."""
    G = 18 * sc

    def fits(level):
        shown = tabs_for_level(tabs, level)
        tw = tabs_widths([t[2] for t in shown], sc)[1] if len(shown) > 1 else 0.0
        mw = modes_layout(context, ptr, sc, compact=level, fixed=True)[2]
        return (tw + G + mw if tw else mw) <= avail

    for level in (0, 1, 2):
        if fits(level):
            return level
    return 3


def modes_total_w(context, ptr, sc):
    """Largeur réservée (boutons de mode + écart) dans le groupe centré, 0 si les boutons sont masqués."""
    if not modes_visible(context, ptr):
        return 0.0
    return modes_layout(context, ptr, sc)[2] + 18 * sc


def modes_visible(context, ptr):
    """La pastille des modes est toujours là : tous les boutons avec un outil de dessin, seulement Gumball sinon."""
    return True


def drawing_active(context, ptr):
    """Un outil de dessin ou une commande est actif (Ortho, Polar, OSnap, SmartTrack ont alors un sens)."""
    if _CMD["op"].get(ptr) is not None:
        return True
    tid = DessinBase.active_tool_id(context)
    return bool(tid and tid.startswith("dessin.") and tid not in _SELECT_TOOL_IDS)


def draw_chevron(cx, cy, s, col):
    """Chevron « menu déroulant » dessiné (deux traits), plus lisible qu'un caractère."""
    shader = get_shader('2D')
    _blend_on()
    shader.bind()
    shader.uniform_float("color", (col[0], col[1], col[2], 1.0))
    gpu.state.line_width_set(2.0)
    batch_for_shader(shader, 'LINE_STRIP', {"pos": [(cx - s, cy + s * 0.45), (cx, cy - s * 0.55), (cx + s, cy + s * 0.45)]}).draw(shader)
    gpu.state.line_width_set(1.0)


def _circle(cx, cy, r, n=20):
    return [(cx + r * math.cos(TAU * k / n), cy + r * math.sin(TAU * k / n)) for k in range(n + 1)]


# Icônes des modes (vue étroite) : polylignes dans une case de 14 x 14, y vers le bas (comme un dessin SVG)
MODE_ICONS = {
    "grid_snap": [[(1, 4.5), (13, 4.5)], [(1, 9.5), (13, 9.5)], [(4.5, 1), (4.5, 13)], [(9.5, 1), (9.5, 13)]],
    "ortho": [[(2, 1), (2, 12), (13, 12)], [(2, 8), (6, 8), (6, 12)]],
    "polar": [_circle(7, 7, 5.5), [(7, 7), (12.2, 4)]],
    "osnap_enable": [[(1.5, 1.5), (12.5, 1.5), (12.5, 12.5), (1.5, 12.5), (1.5, 1.5)], [(4.5, 4.5), (9.5, 9.5)], [(9.5, 4.5), (4.5, 9.5)]],
    "smart_tracks": [[(1, 7), (4.5, 7)], [(9.5, 7), (13, 7)], [(7, 1), (7, 4.5)], [(7, 9.5), (7, 13)],
                     [(5.3, 5.3), (8.7, 8.7)], [(8.7, 5.3), (5.3, 8.7)]],
    "gumball": [[(2, 12), (2, 2)], [(2, 12), (12, 12)], [(0.6, 4.2), (2, 2), (3.4, 4.2)], [(9.8, 10.6), (12, 12), (9.8, 13.4)],
                _circle(2, 12, 1.3, 10)],
    "auto_cplane": [[(1, 11), (4, 5), (13, 5), (10, 11), (1, 11)], [(7, 8), (7, 1.5)], [(5.6, 3.4), (7, 1.5), (8.4, 3.4)]],
    "cmd_type": [[(1, 3), (13, 3), (13, 11), (1, 11), (1, 3)], [(3.1, 5.8), (3.9, 5.8)], [(5.6, 5.8), (6.4, 5.8)],
                 [(8.1, 5.8), (8.9, 5.8)], [(10.6, 5.8), (11.4, 5.8)], [(4, 8.6), (10, 8.6)]],
}


def mode_icon_segments(key, cx, cy, s):
    """Segments (couples de points écran) de l'icône d'un mode, centrée en (cx, cy), de demi-taille s."""
    k = s / 7.0
    segs = []
    for line in MODE_ICONS.get(key, ()):
        pts = [(cx + (x - 7.0) * k, cy - (y - 7.0) * k) for x, y in line]
        for a, b in zip(pts, pts[1:]):
            segs += [a, b]
    return segs


def draw_lines(segs, col, width):
    """Traits lissés d'épaisseur donnée (icônes) ; segs : points écran pris deux par deux."""
    if not segs:
        return
    pts = [(x, y, 0.0) for x, y in segs]
    col = (col[0], col[1], col[2], col[3] if len(col) > 3 else 1.0)
    _blend_on()                        # (traits lissés : leurs bords se fondent dans le fond)
    try:
        sh = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')       # trait épais et lissé sur toutes les cartes (Metal, Vulkan)
        sh.bind()
        sh.uniform_float("viewportSize", gpu.state.viewport_get()[2:])
        sh.uniform_float("lineWidth", width)
        sh.uniform_float("color", col)
        batch_for_shader(sh, 'LINES', {"pos": pts}).draw(sh)
        return
    except Exception:           # nuanceur absent ou refusé par la carte : traits simples, comme les chevrons
        pass
    try:
        sh = get_shader('2D')
        sh.bind()
        sh.uniform_float("color", col)
        gpu.state.line_width_set(width)
        batch_for_shader(sh, 'LINES', {"pos": pts}).draw(sh)
        gpu.state.line_width_set(1.0)
    except Exception:           # une icône qui ne se dessine pas ne doit jamais emporter toute la barre
        pass


def draw_mode_icon(key, cx, cy, s, col, width=1.4):
    """Icône d'un bouton de mode (vue étroite : les libellés laissent la place aux icônes)."""
    draw_lines(mode_icon_segments(key, cx, cy, s), col, width)


def views_bar_cb():
    """Onglets de vues (Top / Front / Perspective / Right...) en bas à gauche de la vue 3D, dessinés comme la barre de commande."""
    context = bpy.context
    area, region = context.area, context.region
    if area is None or region is None:
        return
    ptr = area.as_pointer()
    try:
        tabs = bar_tabs(context)               # vues du modèle, mises en page, puis « + »
    except (AttributeError, ReferenceError):
        return
    try:
        sysp = context.preferences.system
        base = max(1.0, (sysp.ui_scale or 1.0) * ((sysp.dpi or 72) / 72.0))
    except (AttributeError, ReferenceError):
        base = 1.0
    sc = (1.0 + (base - 1.0) * 0.5) * CMD_SIZE_BASE * (pref("cmd_size") or 100) / 100.0
    size = 11 * sc
    _cmd_font(size)
    lh = size * 1.6
    left, right = 0.0, 0.0
    space = area.spaces.active
    if getattr(context.preferences.system, "use_region_overlap", False):
        for r in area.regions:
            if r.type == 'TOOLS' and getattr(space, "show_region_toolbar", True):
                left += r.width
            elif r.type == 'UI' and getattr(space, "show_region_ui", True):
                right += r.width
    th = _cmd_theme()
    W = lambda t: blf.dimensions(0, t)[0]
    padx = 12 * sc
    gap = 2 * sc
    h = lh + 11 * sc
    rad, irad = 11 * sc, 8 * sc
    # vue réduite : les vues passent en initiales (T F P R +) et les modes en icônes, côte à côte en bas, pour que rien ne
    # glisse sous les panneaux et que les vues ne montent jamais au milieu
    compact = bars_compact(context, ptr, region.width - left - right - 24 * sc, sc, tabs)
    if _GROUP["compact"].get(ptr) != compact:
        _GROUP["compact"][ptr] = compact
        area.tag_redraw()              # la ligne de commande se cale sur la largeur des modes : un second dessin la remet en place
    shown = tabs_for_level(tabs, compact)
    full_labels = [t[4] for t in shown]
    tabs = [t[:4] for t in shown]
    names = [t[1] for t in tabs]
    widths, total = tabs_widths([t[2] for t in tabs], sc)
    x0 = left + 12 * sc
    hc = _GROUP["cmd_h"].get(ptr, 0.0) if pref("cmd_line") else 0.0
    cw_ = _GROUP["cmd"].get(ptr, 0.0) if pref("cmd_line") else 0.0
    mw_ = modes_layout(context, ptr, sc)[2] if modes_visible(context, ptr) else 0.0
    lay = bar_layout(ptr, region.width, left, right, sc, total if len(names) > 1 else 0.0, cw_, mw_, hc, modes_height(sc, compact))
    y0 = 16 * sc
    shader = get_shader('2D')
    gpu.state.blend_set('ALPHA')

    def fill(col, tris):
        _blend_on()                    # (un texte dessiné juste avant a coupé le mélange alpha)
        shader.bind()
        shader.uniform_float("color", col)
        batch_for_shader(shader, 'TRIS', {"pos": tris}).draw(shader)

    mouse = _CMD["mouse"].get(ptr)
    hits = []
    tip = None                  # info-bulle : (texte, zone survolée, bas de sa pastille)

    def pill(px0, items, widths_, total_):
        nonlocal tip
        fill(th["line"], _cmd_rrect(px0 - 1, y0 - 1, px0 + total_ + 1, y0 + h + 1, rad + 1))
        fill(th["bg"], _cmd_rrect(px0, y0, px0 + total_, y0 + h, rad))
        x = px0 + 4 * sc
        for (kind, val, text, on), w in zip(items, widths_):
            rect = (x, y0 + 4 * sc, x + w, y0 + h - 4 * sc)
            hits.append((*rect, kind, val))
            over = mouse is not None and rect[0] <= mouse[0] <= rect[2] and rect[1] <= mouse[1] <= rect[3]
            if on:
                fill(th["sel"], _cmd_rrect(rect[0], rect[1], rect[2], rect[3], irad))
            elif over:        # survol d'un bouton non actif : surbrillance discrète, différente de l'état actif (comme Rhino)
                fill(th["chip"], _cmd_rrect(rect[0], rect[1], rect[2], rect[3], irad))
            blf.color(0, *(th["sel_t"] if on else (th["fg"] if over else th["dim"])))
            blf.position(0, x + (w - W(text)) / 2.0, y0 + (h - size) / 2.0 + size * 0.12, 0)
            blf.draw(0, text)
            if compact and over and kind != 'viewmenu':
                tip = (full_labels[len(hits) - 1], rect, y0)       # onglet abrégé : son nom complet en info-bulle
            x += w + gap

    # onglets de vue centrés, sous la ligne de commande
    if len(names) > 1:
        if _GROUP["views"].get(ptr) != total:
            area.tag_redraw()
        _GROUP["views"][ptr] = total
        vx0, y0 = lay["views"]
        pill(vx0, tabs, widths, total)
    # boutons de mode (Ortho, Polar, accrochage, repérage) à droite de la ligne de commande, seulement quand on dessine
    oneshot_validate(context)
    if modes_visible(context, ptr):
        items, arrow_w, mw = modes_layout(context, ptr, sc)
        mx0, my0 = lay["modes"]
        mh = modes_height(sc, compact)
        icons = modes_icons(compact)        # vue réduite, ou préférence « Mode bar: icons only »
        fill(th["line"], _cmd_rrect(mx0 - 1, my0 - 1, mx0 + mw + 1, my0 + mh + 1, rad + 1))
        fill(th["bg"], _cmd_rrect(mx0, my0, mx0 + mw, my0 + mh, rad))
        tips = {k: t for k, _l, t in MODE_BUTTONS}
        names_ = {k: l for k, l, _t in MODE_BUTTONS}
        rows_ = modes_rows(items, compact)
        placed = []                     # (clé, libellé, largeur, x, bas de la rangée) : première rangée en haut
        for r_, row_ in enumerate(rows_):
            row_w = sum(w for _k, _l, w in row_) + 4 * sc * (len(row_) + 1)
            x = mx0 + (mw - row_w) / 2.0 + 4 * sc           # (deux rangées : chacune centrée dans la pastille)
            for key, lab, w in row_:
                placed.append((key, lab, w, x, my0 + (len(rows_) - 1 - r_) * (h - 4 * sc)))
                x += w + 4 * sc
        for key, lab, w, x, y0 in placed:
            rect = (x, y0 + 4 * sc, x + w, y0 + h - 4 * sc)
            has_arrow = key in MODE_ARROWS
            trect = (rect[0], rect[1], rect[2] - (arrow_w if has_arrow else 0.0), rect[3])       # partie texte
            arect = (trect[2], rect[1], rect[2], rect[3]) if has_arrow else None                   # partie flèche (dans la même bulle)
            hits.append((*trect, 'mode', key))
            on = mode_state(context, key)
            tover = mouse is not None and trect[0] <= mouse[0] <= trect[2] and trect[1] <= mouse[1] <= trect[3]
            aover = bool(has_arrow) and mouse is not None and arect[0] <= mouse[0] <= arect[2] and arect[1] <= mouse[1] <= arect[3]
            if tover:
                # bouton réduit à son icône : l'info-bulle commence par son nom
                tip = ((tips[key] if not icons or tips[key].startswith(names_[key]) else names_[key] + ": " + tips[key]), trect, my0 + mh - h)
            if on:
                fill(th["sel"], _cmd_rrect(rect[0], rect[1], rect[2], rect[3], irad))
            elif tover or aover:
                fill(th["chip"], _cmd_rrect(rect[0], rect[1], rect[2], rect[3], irad))
            fg_ = th["sel_t"] if on else (th["fg"] if (tover or aover) else th["dim"])
            if icons:
                draw_mode_icon(key, (trect[0] + trect[2]) / 2.0, (trect[1] + trect[3]) / 2.0, 6.5 * sc, fg_, 1.4 * sc)
            else:
                blf.color(0, *fg_)
                blf.position(0, rect[0] + 9 * sc, y0 + (h - size) / 2.0 + size * 0.12, 0)
                blf.draw(0, lab)
            if has_arrow:
                hits.append((*arect, 'mode', MODE_ARROWS[key]))
                if aover:
                    fill(th["line"] if on else th["sel"], _cmd_rrect(arect[0], arect[1], arect[2], arect[3], irad))
                    tip = (mode_arrow_tip(context, key), arect, my0 + mh - h)
                # séparateur fin entre le texte et la flèche : montre que la flèche est un bouton à part
                fill((*th["sel_t"][:3], 0.35) if on else (*th["dim"][:3], 0.35),
                     [(arect[0] - 0.5, arect[1] + 6 * sc), (arect[0] + 0.5, arect[1] + 6 * sc), (arect[0] + 0.5, arect[3] - 6 * sc),
                      (arect[0] - 0.5, arect[1] + 6 * sc), (arect[0] + 0.5, arect[3] - 6 * sc), (arect[0] - 0.5, arect[3] - 6 * sc)])
                draw_chevron((arect[0] + arect[2]) / 2.0, (arect[1] + arect[3]) / 2.0, (3.0 if icons else 3.6) * sc, fg_)
    if tip is not None and _mode_tip_fresh(ptr):
        ttxt, rect, ybase = tip
        tw = blf.dimensions(0, ttxt)[0] + 18 * sc
        tx0 = max(min(max(rect[0] - 4 * sc, left + 8 * sc), region.width - right - tw - 8 * sc), 4 * sc)
        ty0 = ybase + h + 8 * sc
        fill(th["line"], _cmd_rrect(tx0 - 1, ty0 - 1, tx0 + tw + 1, ty0 + lh + 1, irad + 1))
        fill(th["bg"], _cmd_rrect(tx0, ty0, tx0 + tw, ty0 + lh, irad))
        blf.color(0, *th["fg"])
        blf.position(0, tx0 + 9 * sc, ty0 + (lh - size) / 2.0 + size * 0.12, 0)
        blf.draw(0, ttxt)
    _VBAR["hit"][ptr] = hits
    gpu.state.blend_set('NONE')


_CMD_KEYMAPS = []


def register_cmd_keymap():
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon if wm is not None else None
    if kc is None or not pref("cmd_line"):
        return
    key = pref("cmd_key")
    km = kc.keymaps.new(name="3D View", space_type='VIEW_3D')
    if key != 'NONE':
        kmi = km.keymap_items.new(DESSIN_OT_command_line.bl_idname, key, 'PRESS')
        _CMD_KEYMAPS.append((km, kmi))
        # « Spacebar action : Play » : Blender lie Espace à la lecture dans le keymap « Frames », qui passe avant « 3D View ».
        # On ajoute la touche dans « Frames » (les entrées d'un add-on y priment sur les défauts) ; hors vue 3D le poll échoue
        # et Espace continue de lancer la lecture (timeline, etc.).
        try:
            kmf = kc.keymaps.new(name="Frames", space_type='EMPTY')
            kmi_f = kmf.keymap_items.new(DESSIN_OT_command_line.bl_idname, key, 'PRESS')
            _CMD_KEYMAPS.append((kmf, kmi_f))
        except (TypeError, ValueError, RuntimeError):
            pass
    if pref("cmd_type"):
        # saisie directe : une lettre ouvre la ligne de commande avec cette lettre (comme dans Rhino / AutoCAD)
        for name, space_type in MOUSE_KEYMAPS:
            km = kc.keymaps.new(name=name, space_type=space_type)
            for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                kmi = km.keymap_items.new(DESSIN_OT_command_line.bl_idname, ch, 'PRESS')
                kmi.properties.char = ch.lower()
                _CMD_KEYMAPS.append((km, kmi))
    try:
        wm.keyconfigs.update()
    except (AttributeError, RuntimeError):
        pass


_TRACK_KEYMAPS = []


def register_mouse_track():
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon if wm is not None else None
    if kc is None:
        return
    km = kc.keymaps.new(name="3D View", space_type='VIEW_3D')
    kmi = km.keymap_items.new(DESSIN_OT_mouse_track.bl_idname, 'MOUSEMOVE', 'ANY', any=True)
    _TRACK_KEYMAPS.append((km, kmi))
    kmi = km.keymap_items.new(DESSIN_OT_esc_select.bl_idname, 'ESC', 'PRESS')
    _TRACK_KEYMAPS.append((km, kmi))


def unregister_mouse_track():
    for km, kmi in _TRACK_KEYMAPS:
        try:
            km.keymap_items.remove(kmi)
        except (RuntimeError, ReferenceError, TypeError):
            pass
    _TRACK_KEYMAPS.clear()


def unregister_cmd_keymap():
    for km, kmi in _CMD_KEYMAPS:
        try:
            km.keymap_items.remove(kmi)
        except (RuntimeError, ReferenceError, TypeError):
            pass
    _CMD_KEYMAPS.clear()


def _update_cmd_line(self=None, context=None):
    unregister_cmd_keymap()
    register_cmd_keymap()
    try:
        for win in bpy.context.window_manager.windows:
            for a in win.screen.areas:
                a.tag_redraw()
    except (AttributeError, RuntimeError):
        pass


MENU_BUTTON_ITEMS = (
    ('DEFAULT', "Keep current keymap", "Do not change how the context menu is opened"),
    ('RIGHT', "Right mouse button", "Open the context menu with the right mouse button"),
    ('MIDDLE', "Middle mouse button", "Open the context menu with the middle mouse button"),
    ('ALT_RIGHT', "Alt + Right mouse button", "Open the context menu with Alt + right mouse button"),
    ('RIGHT_CLICK', "Right mouse button, on click (orbit stays on drag)",
     "The right button orbits when you drag; a click released without moving opens the context menu. Needs Orbit button = Right mouse button"))


class DESSIN_MT_mouse_menu(bpy.types.Menu):
    bl_idname = "DESSIN_MT_mouse_menu"
    bl_label = "Context menu button"

    def draw(self, context):
        prefs = context.preferences.addons[__package__].preferences
        layout = self.layout
        for ident, name, _desc in MENU_BUTTON_ITEMS:
            row = layout.row()
            row.enabled = not (ident == 'RIGHT_CLICK' and prefs.mouse_orbit != 'RIGHT')   # grisé tant que l'orbite n'est pas sur le clic droit
            row.prop_enum(prefs, "mouse_menu", ident)


def _update_mouse_orbit(self, context):
    if self.nav_style not in ('CUSTOM', 'RHINO') and self.mouse_orbit != 'DEFAULT':
        self.nav_style = 'CUSTOM'
        return
    if self.mouse_orbit != 'RIGHT' and self.mouse_menu == 'RIGHT_CLICK':
        self.mouse_menu = 'DEFAULT'
        return
    _update_view_keymap()


def _reload_addon_later():
    """Réactive l'add-on un instant plus tard (les icônes de la barre d'outils ne se rechargent qu'à l'enregistrement)."""
    def _go():
        try:
            import addon_utils
            addon_utils.disable(__package__, default_set=False)
            addon_utils.enable(__package__, default_set=True)
        except Exception:
            pass
        return None
    bpy.app.timers.register(_go, first_interval=0.2)


def _update_icon_palette(self, context):
    _reload_addon_later()


def _late_imports():
    pass
