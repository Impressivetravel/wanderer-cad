"""Wanderer CAD : Ligne de commande, barre d'état, modes."""

import blf
import bpy
import gpu
import math
import time
from gpu_extras.batch import batch_for_shader

from .core import FR_ACTION_ALIASES, FR_ALIASES, TAU, lang, pref, tr_label, tr_text
from .drawing import find_window_region, get_shader
from .base import DessinBase
from .selection import DESSIN_OT_esc_select
from .objects import _act_invoke
from .gumball import DESSIN_MT_gumball
from .toolbar import DESSIN_TT_selection_boite, _SELECT_TOOL_IDS
from .navigation import BASE_VIEWS, DESSIN_OT_mouse_track, MOUSE_KEYMAPS, _update_view_keymap
from .views import CMD_ALIASES, CMD_KEY_ITEMS, DESSIN_MT_named_views, _CMD, current_view_name, tab_names, view_label
from .cplane import (
    _act_cplane_mode, _act_cplane_named, _act_cplane_redo, _act_cplane_undo, _act_op, _act_origin, _act_region,
    _act_select_linked, _act_select_similar, _act_select_similar_menu, _act_shading, _act_toggle, cmd_clean_label,
    cmd_log, cmd_tool_class, cmd_tool_classes, cp_apply_named, cp_current_rv3d,
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


CMD_ACTIONS = (
    ("Auto CPlane", "acp autocplane", "", "Turn Auto CPlane on / off: the construction plane follows the planar object or face you select", _act_auto_cplane),
    ("PushPull", "pp pushpull", "", "Pull or push a face of a solid or a surface along its normal: click the face, then move the mouse or type a distance", _act_invoke("dessin.pushpull")),
    ("Pipe", "pipe", "", "Tube around the selected curves (radius, caps)", _act_invoke("dessin.pipe")),
    ("Intersect", "int intersect", "", "Curves and points where the selected surfaces, solids and curves cross each other", _act_op("dessin.intersect")),
    ("Section", "sec section", "", "Section curves of the selected objects along a plane drawn as a line (two points)", _act_invoke("dessin.section")),
    ("Contour", "contour", "", "Evenly spaced section curves through the selected objects: base point, direction, distance", _act_invoke("dessin.contour")),
    ("Extract Surface", "extractsrf", "", "Detach faces of a solid or a polysurface as separate surfaces: click the faces (C: copy)", _act_invoke("dessin.extract_srf")),
    ("Duplicate Border", "dupborder", "", "Curves on the free borders of the selected surfaces", _act_op("dessin.dup_border")),
    ("Duplicate Edge", "dupedge", "", "Curve on an edge of a surface or a solid: click near the edge", _act_invoke("dessin.dup_edge")),
    ("Merge All Faces", "mergeallfaces mergeallcoplanarfaces", "", "Merge the neighbouring coplanar faces of the selected objects", _act_op("dessin.merge_faces")),
    ("Unroll Surface", "unroll unrollsrf", "", "Flatten the selected developable surfaces onto the construction plane (lengths and areas kept)", _act_op("dessin.unroll")),
    ("Rebuild Surface", "rebuildsrf", "", "Rebuild the selected surfaces with a number of points in each direction", _act_invoke("dessin.rebuild_srf")),
    ("Orient", "orient orient2pt", "", "Move and rotate objects with two reference points and two target points (D: scale, C: copy)", _act_invoke("dessin.orient")),
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
    ("Delete", "e del delete erase", "", "Delete the selected objects", _act_op("object.delete")),
    ("Extend Curve", "extendcrv extend extendcurve", "", "Extend the selected curves by a length or up to the nearest other curve", _act_invoke("dessin.extend_crv")),
    ("Select All", "sa all selectall", "", "Select every object", _act_op("object.select_all", action='SELECT')),
    ("Select None", "sn none deselect selnone", "", "Deselect everything", _act_op("object.select_all", action='DESELECT')),
    ("Invert Selection", "si invert selinvert", "", "Invert the selection", _act_op("object.select_all", action='INVERT')),
    ("Hide", "hi hide", "", "Hide the selected objects", _act_op("object.hide_view_set", unselected=False)),
    ("Isolate", "isolate", "", "Hide everything except the selected objects", _act_op("object.hide_view_set", unselected=True)),
    ("Show All", "show showall unhide", "", "Show the hidden objects", _act_op("object.hide_view_clear")),
    ("Zoom Extents", "z ze zoom extents zoomall", "", "Frame all the objects", _act_op("view3d.view_all")),
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
                    "dessin.fillet_curve_tool": "fillet_curve", "dessin.chamfer_curve_tool": "chamfer_curve"}


def run_on_selection(context, tool_id):
    name = RUN_ON_SELECTION.get(tool_id)
    area = context.area
    if name is None or area is None or area.type != 'VIEW_3D' or context.mode != 'OBJECT':
        return
    if not any(o.type in {'MESH', 'CURVE'} for o in context.selected_objects):
        return
    window = context.window
    region = next((r for r in area.regions if r.type == 'WINDOW'), None)
    if window is None or region is None:
        return

    def _go():
        try:
            with bpy.context.temp_override(window=window, area=area, region=region):
                getattr(bpy.ops.dessin, name)('INVOKE_DEFAULT')
        except (RuntimeError, TypeError, AttributeError, ReferenceError):
            pass
        return None
    try:
        bpy.app.timers.register(_go, first_interval=0.1)
    except (RuntimeError, ValueError):
        pass


def cmd_run(context, entry):
    """Exécute une commande ; retourne un message d'erreur ou ''."""
    try:
        if entry["kind"] == "tool":
            ref = entry["ref"]
            if ref in ("dessin.extrude_tool", "dessin.extrude_crv_tool"):      # Extrude : l'outil du mode courant
                ref = "dessin.extrude_tool" if context.mode == 'EDIT_MESH' else "dessin.extrude_crv_tool"
            bpy.ops.wm.tool_set_by_id(name=ref)
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
            "chip": (*mix(fg, bg, 0.14), 1.0), "line": (*mix(fg, bg, 0.22), 1.0)}


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


def bar_layout(ptr, region_w, left, right, sc, vw, cw, mw, hc):
    """Position des trois pastilles du bas (onglets de vue, ligne de commande, boutons de mode).
    Une seule ligne si tout tient entre la barre d'outils et la barre latérale ; sinon la ligne de commande passe
    au-dessus, seule, et les onglets + modes restent en bas (sur deux lignes si la vue est vraiment étroite).
    Retourne {"views": (x, y), "cmd": (x, y), "modes": (x, y)} (bas-gauche de chaque pastille)."""
    G = 18 * sc
    hp = 11 * sc * 1.6 + 11 * sc                       # hauteur d'une pastille d'onglets / de modes
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
        for k, w in row:
            out[k] = (x, y)
            x += w + G
        y += (hc if row[0][0] == "cmd" else hp) + 8 * sc
    return out


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
    sc = (1.0 + (base - 1.0) * 0.5) * (pref("cmd_size") or 100) / 100.0
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
    own_row = share < 360 * sc
    if _GROUP["cmd_row"].get(ptr) != own_row:
        _GROUP["cmd_row"][ptr] = own_row
        area.tag_redraw()
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
        chips_t = [("c", "Esc", "leave", 'key')]
        if tid == "dessin.trim_tool":
            try:
                fence = bpy.context.scene.dessin.trim_mode == 'FENCE'
            except (AttributeError, ReferenceError):
                fence = True
            hint = ("Drag a fence line across the parts to remove, or click one part" if fence else
                    "Drag a crossing box over the parts to remove, or click one part") + "  ·  cutting curves: select them first (none: all)"
            chips_t = [("c", "F", ("● " if fence else "") + "Fence", 'key'), ("c", "C", ("" if fence else "● ") + "Crossing", 'key')] + chips_t
        lines.append(([("t", name, "acc", True), ("t", hint, "dim")], chips_t))
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
    rows_w = max((sum(chip_w(c[1], c[2]) for c in r_) + gap * (len(r_) - 1) for r_ in chip_rows), default=0.0)
    width = min(maxw, max(used + (0 if two_rows else (gap + chips_w if chips else 0)), rows_w if two_rows else 0) + 2 * padx)
    h = nrows * lh + 2 * pv + (nrows - 1) * 4 * sc
    if _GROUP["cmd"].get(ptr) != width or _GROUP["cmd_h"].get(ptr) != h:
        area.tag_redraw()          # les onglets / boutons de mode se calent sur ces valeurs : on se redessine une fois, sans attendre la souris
    _GROUP["cmd"][ptr] = width
    _GROUP["cmd_h"][ptr] = h
    vw = _GROUP["views"].get(ptr, 0.0)
    mw_raw = modes_layout(context, ptr, sc)[2] if mw0 else 0.0
    x0, y0 = bar_layout(ptr, region.width, left, right, sc, vw, width, mw_raw, h)["cmd"]
    shader = get_shader('2D')
    gpu.state.blend_set('ALPHA')

    def fill(col, tris):
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


_VBAR = {"hit": {}, "handle": None}
_GROUP = {"cmd": {}, "views": {}, "cmd_h": {}, "cmd_row": {}}


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


MODE_BUTTONS = (("ortho", "Ortho", "Ortho (F8): the cursor stays horizontal or vertical"),
                ("polar", "Polar", "Polar tracking (F10): the cursor snaps to angle steps (arrow: choose the step)"),
                ("osnap_enable", "OSnap", "Object snaps on / off (F3): End, Mid, Cen..."),
                ("smart_tracks", "SmartTrack", "Smart tracks on / off: alignment guides from points you hover"),
                ("gumball", "Gumball", "Gumball on / off: move / rotate / scale handles on the selection (arrow: Gumball menu, orientation Global / Local / View...)"),
                ("auto_cplane", "Auto CPlane", "Auto CPlane on / off: the construction plane follows the planar object or face you select (arrow: Sticky option, back to the ground plane)"),
                ("cmd_type", "Quick Type", "Quick Type on / off: typing a letter starts the command line (letters then lose Blender's own shortcuts; Space still opens it)"))
MODE_ARROWS = {"polar": "polarmenu", "gumball": "gumballmenu", "auto_cplane": "autocplanemenu"}


def mode_state(context, key):
    try:
        if key == "osnap_enable":
            return not context.scene.dessin.osnap_disable
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
    if key == 'gumballmenu':
        call_menu_later(context, DESSIN_MT_gumball.bl_idname)
        return
    if key == 'autocplanemenu':
        call_menu_later(context, DESSIN_MT_auto_cplane.bl_idname)
        return
    if key == "osnap_enable":
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


def modes_layout(context, ptr, sc):
    """Largeurs des boutons de mode (texte) : ([(clé, libellé, largeur)], largeur de la flèche Polar, largeur totale du cadre)."""
    _cmd_font(11 * sc)
    pad, gap, arrow = 9 * sc, 4 * sc, 24 * sc
    drawing = True      # tous les boutons restent visibles, outil de dessin actif ou non
    items = [(k, lab, blf.dimensions(0, lab)[0] + 2 * pad + (arrow if k in MODE_ARROWS else 0.0))
             for k, lab, _t in MODE_BUTTONS if (drawing or k == "gumball") and (k != "cmd_type" or pref("cmd_line"))]
    total = sum(w for _k, _l, w in items) + gap * (len(items) + 1)
    return items, arrow, total


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
    shader.bind()
    shader.uniform_float("color", (col[0], col[1], col[2], 1.0))
    gpu.state.line_width_set(2.0)
    batch_for_shader(shader, 'LINE_STRIP', {"pos": [(cx - s, cy + s * 0.45), (cx, cy - s * 0.55), (cx + s, cy + s * 0.45)]}).draw(shader)
    gpu.state.line_width_set(1.0)


def draw_mode_icon(key, cx, cy, s, col):
    """Petites icônes vectorielles des modes (style AutoCAD)."""
    shader = get_shader('2D')
    seg, loop = [], []
    if key == "ortho":
        loop = [(cx - s, cy + s), (cx - s, cy - s), (cx + s, cy - s)]
        seg = [(cx - s, cy - s + s * 0.55), (cx - s + s * 0.55, cy - s + s * 0.55), (cx - s + s * 0.55, cy - s + s * 0.55),
               (cx - s + s * 0.55, cy - s)]
    elif key == "polar":
        pts = [(cx + s * math.cos(a * TAU / 20), cy + s * math.sin(a * TAU / 20)) for a in range(20)]
        for i in range(20):
            seg += [pts[i], pts[(i + 1) % 20]]
        seg += [(cx - s, cy - s * 0.3), (cx + s, cy + s * 0.5)]
    elif key == "osnap_enable":
        seg = [(cx - s, cy - s), (cx + s, cy - s), (cx + s, cy - s), (cx + s, cy + s), (cx + s, cy + s), (cx - s, cy + s),
               (cx - s, cy + s), (cx - s, cy - s), (cx - s * 0.45, cy - s * 0.45), (cx + s * 0.45, cy + s * 0.45),
               (cx - s * 0.45, cy + s * 0.45), (cx + s * 0.45, cy - s * 0.45)]
    elif key == "gumball":
        seg = [(cx - s, cy), (cx + s, cy), (cx, cy - s), (cx, cy + s), (cx + s, cy), (cx + s * 0.55, cy + s * 0.4),
               (cx + s, cy), (cx + s * 0.55, cy - s * 0.4), (cx, cy + s), (cx + s * 0.4, cy + s * 0.55),
               (cx, cy + s), (cx - s * 0.4, cy + s * 0.55)]
    elif key == "auto_cplane":
        loop = [(cx - s, cy - s * 0.6), (cx + s * 0.5, cy - s * 0.6), (cx + s, cy + s * 0.5), (cx - s * 0.5, cy + s * 0.5), (cx - s, cy - s * 0.6)]
        seg = [(cx, cy + s * 0.5), (cx, cy + s), (cx - s * 0.25, cy + s * 0.7), (cx, cy + s), (cx + s * 0.25, cy + s * 0.7), (cx, cy + s)]
    elif key == "smart_tracks":
        seg = [(cx - s, cy), (cx - s * 0.45, cy), (cx + s * 0.45, cy), (cx + s, cy),
               (cx, cy - s), (cx, cy - s * 0.45), (cx, cy + s * 0.45), (cx, cy + s),
               (cx - s * 0.3, cy - s * 0.3), (cx + s * 0.3, cy + s * 0.3), (cx - s * 0.3, cy + s * 0.3), (cx + s * 0.3, cy - s * 0.3)]
    shader.bind()
    shader.uniform_float("color", col)
    gpu.state.line_width_set(1.6)
    if loop:
        batch_for_shader(shader, 'LINE_STRIP', {"pos": loop}).draw(shader)
    if seg:
        batch_for_shader(shader, 'LINES', {"pos": seg}).draw(shader)
    gpu.state.line_width_set(1.0)


def views_bar_cb():
    """Onglets de vues (Top / Front / Perspective / Right...) en bas à gauche de la vue 3D, dessinés comme la barre de commande."""
    context = bpy.context
    area, region = context.area, context.region
    if area is None or region is None:
        return
    ptr = area.as_pointer()
    try:
        names = tab_names(context.scene)
        active = current_view_name(context)
    except (AttributeError, ReferenceError):
        return
    try:
        sysp = context.preferences.system
        base = max(1.0, (sysp.ui_scale or 1.0) * ((sysp.dpi or 72) / 72.0))
    except (AttributeError, ReferenceError):
        base = 1.0
    sc = (1.0 + (base - 1.0) * 0.5) * (pref("cmd_size") or 100) / 100.0
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
    names = list(names) + ["+"]
    labels = [view_label(context.scene, n) for n in names[:-1]] + ["+"]
    widths = [W(t) + 2 * padx for t in labels]
    widths[-1] = max(widths[-1], h)
    total = sum(widths) + gap * (len(names) - 1) + 8 * sc
    x0 = left + 12 * sc
    hc = _GROUP["cmd_h"].get(ptr, 0.0) if pref("cmd_line") else 0.0
    cw_ = _GROUP["cmd"].get(ptr, 0.0) if pref("cmd_line") else 0.0
    mw_ = modes_layout(context, ptr, sc)[2] if modes_visible(context, ptr) else 0.0
    lay = bar_layout(ptr, region.width, left, right, sc, total if len(names) > 1 else 0.0, cw_, mw_, hc)
    y0 = 16 * sc
    shader = get_shader('2D')
    gpu.state.blend_set('ALPHA')

    def fill(col, tris):
        shader.bind()
        shader.uniform_float("color", col)
        batch_for_shader(shader, 'TRIS', {"pos": tris}).draw(shader)

    mouse = _CMD["mouse"].get(ptr)
    hits = []

    def pill(px0, items, widths_, total_):
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
            blf.position(0, x + padx, y0 + (h - size) / 2.0 + size * 0.12, 0)
            blf.draw(0, text)
            x += w + gap

    # onglets de vue centrés, sous la ligne de commande
    if len(names) > 1:
        if _GROUP["views"].get(ptr) != total:
            area.tag_redraw()
        _GROUP["views"][ptr] = total
        vx0, y0 = lay["views"]
        pill(vx0, [('viewmenu' if n == "+" else 'view', n, t, n == active) for n, t in zip(names, labels)], widths, total)
    # boutons de mode (Ortho, Polar, accrochage, repérage) à droite de la ligne de commande, seulement quand on dessine
    if modes_visible(context, ptr):
        items, arrow_w, mw = modes_layout(context, ptr, sc)
        mx0, y0 = lay["modes"]
        fill(th["line"], _cmd_rrect(mx0 - 1, y0 - 1, mx0 + mw + 1, y0 + h + 1, rad + 1))
        fill(th["bg"], _cmd_rrect(mx0, y0, mx0 + mw, y0 + h, rad))
        x = mx0 + 4 * sc
        tip = None
        tips = {k: t for k, _l, t in MODE_BUTTONS}
        for key, lab, w in items:
            rect = (x, y0 + 4 * sc, x + w, y0 + h - 4 * sc)
            has_arrow = key in MODE_ARROWS
            trect = (rect[0], rect[1], rect[2] - (arrow_w if has_arrow else 0.0), rect[3])       # partie texte
            arect = (trect[2], rect[1], rect[2], rect[3]) if has_arrow else None                   # partie flèche (dans la même bulle)
            hits.append((*trect, 'mode', key))
            on = mode_state(context, key)
            tover = mouse is not None and trect[0] <= mouse[0] <= trect[2] and trect[1] <= mouse[1] <= trect[3]
            aover = bool(has_arrow) and mouse is not None and arect[0] <= mouse[0] <= arect[2] and arect[1] <= mouse[1] <= arect[3]
            if tover:
                tip = (tips[key], trect)
            if on:
                fill(th["sel"], _cmd_rrect(rect[0], rect[1], rect[2], rect[3], irad))
            elif tover or aover:
                fill(th["chip"], _cmd_rrect(rect[0], rect[1], rect[2], rect[3], irad))
            blf.color(0, *(th["sel_t"] if on else (th["fg"] if (tover or aover) else th["dim"])))
            blf.position(0, rect[0] + 9 * sc, y0 + (h - size) / 2.0 + size * 0.12, 0)
            blf.draw(0, lab)
            if has_arrow:
                hits.append((*arect, 'mode', MODE_ARROWS[key]))
                if aover:
                    fill(th["line"] if on else th["sel"], _cmd_rrect(arect[0], arect[1], arect[2], arect[3], irad))
                    if key == "polar":
                        tip = ("Polar step: " + {i.identifier: i.name for i in context.scene.dessin.bl_rna.properties["polar_angle"].enum_items}
                               .get(context.scene.dessin.polar_angle, "") + " (click to change)", arect)
                    else:
                        tip = ("Gumball menu: relocate, reset, orientation (Global, Local, Normal, View...), dragging, settings", arect)
                # séparateur fin entre le texte et la flèche : montre que la flèche est un bouton à part
                fill((*th["sel_t"][:3], 0.35) if on else (*th["dim"][:3], 0.35),
                     [(arect[0] - 0.5, arect[1] + 6 * sc), (arect[0] + 0.5, arect[1] + 6 * sc), (arect[0] + 0.5, arect[3] - 6 * sc),
                      (arect[0] - 0.5, arect[1] + 6 * sc), (arect[0] + 0.5, arect[3] - 6 * sc), (arect[0] - 0.5, arect[3] - 6 * sc)])
                draw_chevron((arect[0] + arect[2]) / 2.0, (arect[1] + arect[3]) / 2.0, 3.6 * sc,
                             th["sel_t"] if on else (th["fg"] if (tover or aover) else th["dim"]))
            x += w + 4 * sc
        if tip is not None and _mode_tip_fresh(ptr):
            ttxt, rect = tip
            tw = blf.dimensions(0, ttxt)[0] + 18 * sc
            tx0 = min(max(rect[0] - 4 * sc, left + 8 * sc), region.width - right - tw - 8 * sc)
            ty0 = y0 + h + 8 * sc
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
