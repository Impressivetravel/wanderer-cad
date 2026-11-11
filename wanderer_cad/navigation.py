"""Wanderer CAD : Raccourcis, navigation à la souris et au pavé tactile."""

import bpy
import math
import time
from mathutils import Quaternion

from .core import pref
from .drawing import find_window_region
from .selection import _SUBOBJ
from .layers import tool_families
from .gumball_handles import _update_native_gizmos


# ---- raccourcis clavier réglables (Préférences > Add-ons > Wanderer) ----
SHORTCUT_MODES = (("Object Mode", "Object"), ("Mesh", "Edit"))   # (keymap Blender, titre de la colonne)
_KEYMAPS = []   # (keymap, item) enregistrés dans la configuration « addon »


def shortcut_tools():
    """[(section, [(libellé, idname_outil)])] : les mêmes familles que l'onglet Tools et la barre d'outils."""
    return [(title, [(c.bl_label, c.bl_idname) for c in classes]) for title, classes in tool_families()]


def register_shortcuts():
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon if wm is not None else None
    if kc is None:
        return
    for km_name, _title in SHORTCUT_MODES:
        km = kc.keymaps.new(name=km_name, space_type='EMPTY')
        for _sec, tools in shortcut_tools():
            for _label, idname in tools:
                kmi = km.keymap_items.new("wm.tool_set_by_id", 'NONE', 'PRESS')   # aucune touche par défaut
                kmi.properties.name = idname
                _KEYMAPS.append((km, kmi))
    try:
        wm.keyconfigs.update()   # synchronise tout de suite la configuration utilisateur
    except (AttributeError, RuntimeError):
        pass


def unregister_shortcuts():
    for km, kmi in _KEYMAPS:
        try:
            km.keymap_items.remove(kmi)
        except (RuntimeError, ReferenceError, TypeError):
            pass
    _KEYMAPS.clear()


def user_shortcut(km_name, tool_id):
    """L'entrée de la configuration utilisateur (celle que l'on modifie ; Blender la mémorise)."""
    try:
        kc = bpy.context.window_manager.keyconfigs.user
        km = kc.keymaps.get(km_name) if kc is not None else None
        if km is None:
            return None
        for kmi in km.keymap_items:
            if kmi.idname == "wm.tool_set_by_id" and kmi.properties is not None:
                if getattr(kmi.properties, "name", None) == tool_id:
                    return kmi
    except (AttributeError, RuntimeError, ReferenceError):
        pass
    return None


class DESSIN_OT_shortcuts_clear(bpy.types.Operator):
    bl_idname = "dessin.shortcuts_clear"
    bl_label = "Clear all shortcuts"
    bl_description = "Removes every shortcut assigned to the Wanderer tools"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        n = 0
        for km_name, _t in SHORTCUT_MODES:
            for _sec, tools in shortcut_tools():
                for _label, idname in tools:
                    kmi = user_shortcut(km_name, idname)
                    if kmi is not None and kmi.type != 'NONE':
                        kmi.type = 'NONE'
                        n += 1
        self.report({'INFO'}, f"{n} shortcut(s) cleared")
        return {'FINISHED'}


# ---- vues orthogonales : le bouton d'orbite fait le pan (Face, Dessus, Droite...) ----
VIEW_BUTTONS = {'MIDDLE': ('MIDDLEMOUSE', False), 'RIGHT': ('RIGHTMOUSE', False), 'ALT_LEFT': ('LEFTMOUSE', True)}
_VIEW_KEYMAPS = []   # (keymap, item) enregistrés dans la configuration « addon »


def in_side_view(context):
    """True dans une vue orthogonale alignée sur un axe (Face, Dessus, Droite, Arrière, Dessous, Gauche)."""
    rv3d = getattr(context, "region_data", None)
    if rv3d is None:
        return False
    try:
        return bool(rv3d.is_orthographic_side_view) and rv3d.view_perspective == 'ORTHO'
    except (AttributeError, ReferenceError):
        return False


class DESSIN_OT_orbit_pan(bpy.types.Operator):
    bl_idname = "dessin.orbit_pan"
    bl_label = "Orbit / Pan (pan in orthographic side views)"
    bl_description = "In Front / Top / Right... orthographic views the orbit button pans the view; otherwise it orbits as usual"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D' and context.region_data is not None

    def invoke(self, context, event):
        if navigate_or_menu(context, event, start_navigation):
            return {'FINISHED'}
        return {'PASS_THROUGH'}      # perspective / vue libre : l'orbite de Blender (ou de votre keymap) s'applique

    def execute(self, context):
        return {'CANCELLED'}


PAN2D_EDITORS = {'IMAGE_EDITOR': ("image", "view_pan"), 'CLIP_EDITOR': ("clip", "view_pan")}   # les autres : view2d.pan
EDITOR_MENUS = {   # menu contextuel de chaque éditeur
    'NODE_EDITOR': "NODE_MT_context_menu", 'DOPESHEET_EDITOR': "DOPESHEET_MT_context_menu", 'GRAPH_EDITOR': "GRAPH_MT_context_menu",
    'NLA_EDITOR': "NLA_MT_context_menu", 'SEQUENCE_EDITOR': "SEQUENCER_MT_context_menu", 'OUTLINER': "OUTLINER_MT_context_menu",
    'TEXT_EDITOR': "TEXT_MT_context_menu", 'CONSOLE': "CONSOLE_MT_context_menu", 'INFO': "INFO_MT_context_menu",
    'FILE_BROWSER': "FILEBROWSER_MT_context_menu"}


def is_pan_area(area):
    return area is not None and area.type != 'VIEW_3D' and area.type not in {'TOPBAR', 'STATUSBAR'}


class DESSIN_OT_pan2d(bpy.types.Operator):
    bl_idname = "dessin.pan2d"
    bl_label = "Pan (Shader / UV editors)"
    bl_description = "The orbit button pans in the Shader and UV editors"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return is_pan_area(context.area)

    def invoke(self, context, event):
        return {'FINISHED'} if navigate_or_menu(context, event, start_navigation) else {'PASS_THROUGH'}

    def execute(self, context):
        return {'CANCELLED'}


def view_snapshot(context):
    """Etat de la vue (pour savoir si un clic droit a vraiment déplacé la vue)."""
    rv3d = context.region_data if context.area is not None and context.area.type == 'VIEW_3D' else None
    if rv3d is not None:
        return ("3d", rv3d.view_rotation.copy(), rv3d.view_location.copy(), float(rv3d.view_distance))
    try:
        v2 = context.region.view2d
        return ("2d", tuple(v2.region_to_view(0, 0)), tuple(v2.region_to_view(100, 100)))
    except (AttributeError, RuntimeError, ReferenceError):
        return None


def view_moved(a, b):
    if a is None or b is None or a[0] != b[0]:
        return True
    if a[0] == "3d":
        return (abs(a[1].dot(b[1])) < 0.99999 or (a[2] - b[2]).length > 1e-4 * max(a[3], 1e-6) or abs(a[3] - b[3]) > 1e-4 * max(a[3], 1e-6))
    return any(abs(x - y) > 1e-6 for p, q in zip(a[1:], b[1:]) for x, y in zip(p, q))


def navigate_or_menu(context, event, start):
    """Clic droit style Rhino : glisser = orbite / pan, simple clic (relâché sans que la vue ait bougé) = menu contextuel.
    Blender n'envoie pas d'évènement CLICK quand le PRESS est déjà traité : on surveille donc la fin du mouvement de vue nous-mêmes."""
    win, area = context.window, context.area
    region = context.region
    watch = pref("mouse_menu") == 'RIGHT_CLICK' and event.type == 'RIGHTMOUSE'
    if not watch:
        return start(context)
    snap0 = view_snapshot(context)
    n0 = len(win.modal_operators)
    if not start(context):
        return False
    n1 = len(win.modal_operators)
    if n1 <= n0 or snap0 is None:
        return True

    def poll():
        try:
            if len(win.modal_operators) >= n1:
                return 0.03                      # bouton encore enfoncé
            with bpy.context.temp_override(window=win, area=area, region=region):
                moved = view_moved(snap0, view_snapshot(bpy.context))
                if not moved:
                    bpy.ops.dessin.context_menu('INVOKE_DEFAULT')
        except (RuntimeError, ReferenceError, AttributeError, TypeError):
            pass
        return None
    bpy.app.timers.register(poll, first_interval=0.05)
    return True


def start_navigation(context):
    """Lance le pan (vues orthogonales alignées) ou l'orbite choisis. False : laisser Blender / votre keymap faire l'orbite."""
    area_type = context.area.type if context.area is not None else ''
    if area_type and area_type != 'VIEW_3D':        # tous les autres éditeurs : le bouton d'orbite fait le pan
        cat, name = PAN2D_EDITORS.get(area_type, ("view2d", "pan"))
        try:
            getattr(getattr(bpy.ops, cat), name)('INVOKE_DEFAULT')
            return True
        except RuntimeError:
            return False
    if pref("view_pan") and in_side_view(context):
        try:
            bpy.ops.view3d.move('INVOKE_DEFAULT')
            return True
        except RuntimeError:
            pass
    if pref("mouse_orbit") != 'DEFAULT' or pref("mouse_menu") == 'RIGHT_CLICK':
        try:
            bpy.ops.view3d.rotate('INVOKE_DEFAULT')
            return True
        except RuntimeError:
            pass
    return False


class DESSIN_OT_orbit_hold(bpy.types.Operator):
    bl_idname = "dessin.orbit_hold"
    bl_label = "Orbit / Pan, hold for Context Menu"
    bl_description = "Drag with the orbit button to orbit (pan in side views, Shader and UV editors). Click and release without moving to open the context menu"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        if context.area is None:
            return False
        return is_pan_area(context.area) or (context.area.type == 'VIEW_3D' and context.region_data is not None)

    def invoke(self, context, event):
        self._btn = event.type
        self._x, self._y = event.mouse_x, event.mouse_y
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _menu(self, context):
        try:
            bpy.ops.dessin.context_menu('INVOKE_DEFAULT')
        except RuntimeError:
            pass
        return {'FINISHED'}

    def modal(self, context, event):
        if event.type == 'MOUSEMOVE':
            tol = max(1, pref("mouse_menu_tol"))
            if abs(event.mouse_x - self._x) > tol or abs(event.mouse_y - self._y) > tol:
                if not start_navigation(context):
                    try:
                        bpy.ops.view3d.rotate('INVOKE_DEFAULT')
                    except RuntimeError:
                        pass
                return {'FINISHED'}
            return {'RUNNING_MODAL'}
        if event.type == self._btn and event.value == 'RELEASE':
            return self._menu(context)          # clic relâché sans avoir bougé : menu contextuel
        if event.type == 'ESC':
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}

    def execute(self, context):
        return {'CANCELLED'}


class DESSIN_OT_trackpad_pan(bpy.types.Operator):
    bl_idname = "dessin.trackpad_pan"
    bl_label = "Trackpad orbit -> pan (orthographic side views)"
    bl_description = "Two-finger trackpad gesture pans in Front / Top / Right... orthographic views instead of orbiting"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D' and context.region_data is not None

    def invoke(self, context, event):
        if not (pref("view_pan") and in_side_view(context)):
            return {'PASS_THROUGH'}
        region, rv3d = context.region, context.region_data
        dx = event.mouse_x - event.mouse_prev_x           # défilement du trackpad : delta = position - position précédente
        dy = event.mouse_y - event.mouse_prev_y
        if dx or dy:
            try:
                from bpy_extras.view3d_utils import region_2d_to_location_3d
                c = (region.width / 2.0, region.height / 2.0)
                p0 = region_2d_to_location_3d(region, rv3d, c, rv3d.view_location)
                p1 = region_2d_to_location_3d(region, rv3d, (c[0] + dx, c[1] + dy), rv3d.view_location)
                rv3d.view_location = rv3d.view_location - (p1 - p0)    # le contenu suit les doigts
            except (RuntimeError, ReferenceError, AttributeError):
                return {'PASS_THROUGH'}
        return {'FINISHED'}                                # un seul geste, rien de modal : plus de pan qui reste collé

    def execute(self, context):
        return {'CANCELLED'}


class DESSIN_OT_trackpad_persp(bpy.types.Operator):
    bl_idname = "dessin.trackpad_persp"
    bl_label = "Trackpad orbit to Perspective (Ctrl + Shift + two fingers)"
    bl_description = "In Front / Top / Right... orthographic views, Ctrl + Shift + two-finger gesture switches to perspective and orbits"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D' and context.region_data is not None

    def invoke(self, context, event):
        rv3d = context.region_data
        if rv3d.view_perspective == 'CAMERA':
            return {'PASS_THROUGH'}
        if in_side_view(context):
            rv3d.view_perspective = 'PERSP'
        dx = event.mouse_x - event.mouse_prev_x
        dy = event.mouse_y - event.mouse_prev_y
        k = 0.005
        q = Quaternion((0.0, 0.0, 1.0), -dx * k) @ rv3d.view_rotation @ Quaternion((1.0, 0.0, 0.0), dy * k)
        rv3d.view_rotation = q.normalized()
        return {'FINISHED'}

    def execute(self, context):
        return {'CANCELLED'}


class DESSIN_OT_orbit_persp(bpy.types.Operator):
    bl_idname = "dessin.orbit_persp"
    bl_label = "Orbit to Perspective (from orthographic side views)"
    bl_description = "In Front / Top / Right... orthographic views, Ctrl + Shift + the orbit button switches to perspective and orbits"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D' and context.region_data is not None

    def invoke(self, context, event):
        if not in_side_view(context):
            return {'PASS_THROUGH'}
        try:
            context.region_data.view_perspective = 'PERSP'
            bpy.ops.view3d.rotate('INVOKE_DEFAULT')
        except (RuntimeError, AttributeError):
            return {'PASS_THROUGH'}
        return {'FINISHED'}

    def execute(self, context):
        return {'CANCELLED'}


CONTEXT_MENUS = {
    'OBJECT': "VIEW3D_MT_object_context_menu", 'EDIT_MESH': "VIEW3D_MT_edit_mesh_context_menu",
    'EDIT_CURVE': "VIEW3D_MT_edit_curve_context_menu", 'EDIT_SURFACE': "VIEW3D_MT_edit_curve_context_menu",
    'EDIT_ARMATURE': "VIEW3D_MT_armature_context_menu", 'POSE': "VIEW3D_MT_pose_context_menu",
    'EDIT_TEXT': "VIEW3D_MT_edit_font_context_menu", 'EDIT_METABALL': "VIEW3D_MT_edit_metaball_context_menu",
    'EDIT_LATTICE': "VIEW3D_MT_edit_lattice_context_menu",
}


class DESSIN_OT_context_menu(bpy.types.Operator):
    bl_idname = "dessin.context_menu"
    bl_label = "Context Menu (mouse button chosen in the preferences)"
    bl_description = "Opens the context menu of the current mode"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type not in {'TOPBAR', 'STATUSBAR'}

    def invoke(self, context, event):
        if context.area.type == 'IMAGE_EDITOR':
            name = "IMAGE_MT_uvs_context_menu" if getattr(context.space_data, "mode", '') == 'UV' else None
        elif context.area.type == 'VIEW_3D':
            name = CONTEXT_MENUS.get(context.mode)
        else:
            name = EDITOR_MENUS.get(context.area.type)
        if name is None or not hasattr(bpy.types, name):
            return {'PASS_THROUGH'}
        try:
            bpy.ops.wm.call_menu(name=name)
        except RuntimeError:
            return {'PASS_THROUGH'}
        return {'FINISHED'}

    def execute(self, context):
        return {'CANCELLED'}


class DESSIN_OT_mouse_track(bpy.types.Operator):
    """Suit la souris au-dessus des boutons de la barre du bas / de la ligne de commande (survol, info-bulles) quand aucun outil n'est armé."""
    bl_idname = "dessin.mouse_track"
    bl_label = "Track the mouse over the bar"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D'

    def invoke(self, context, event):
        area = context.area
        ptr = area.as_pointer()
        if _SUBOBJ["objs"] and context.mode not in {'EDIT_MESH', 'EDIT_CURVE'}:
            _SUBOBJ["objs"] = set()        # sorti de l'Édition autrement (Tab) : Échap redevient normal
        hot = _CMD.setdefault("hot", {})
        try:
            hit = cmd_hit(area, event.mouse_x, event.mouse_y)
            if hit is not None:
                region = find_window_region(area, event.mouse_x, event.mouse_y)
                _CMD["mouse"][ptr] = (event.mouse_x - region.x, event.mouse_y - region.y)
                _CMD.setdefault("mouse_t", {})[ptr] = time.monotonic()
                hot[ptr] = True
                area.tag_redraw()
            elif hot.pop(ptr, False):        # la souris vient de quitter la barre : on efface le survol
                _CMD["mouse"].pop(ptr, None)
                area.tag_redraw()
        except (AttributeError, ReferenceError, RuntimeError):
            pass
        return {'CANCELLED', 'PASS_THROUGH'}

    def execute(self, context):
        return {'CANCELLED'}


class DESSIN_OT_mouse_block(bpy.types.Operator):
    bl_idname = "dessin.mouse_block"
    bl_label = "Unused mouse button"
    bl_description = "Swallows the click of a mouse button whose action was moved elsewhere in the preferences"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D'

    def invoke(self, context, event):
        return {'FINISHED'}

    def execute(self, context):
        return {'CANCELLED'}


MIDDLE_OPS = {'PAN': "view3d.move", 'ZOOM': "view3d.zoom", 'VIEW_ALL': "view3d.view_all",
              'VIEW_SELECTED': "view3d.view_selected", 'PERSP': "view3d.view_persportho"}


def run_macro(text, report=None):
    """Exécute une ou plusieurs commandes Blender séparées par « ; », par ex.
    view3d.view_selected ; wm.call_menu(name='VIEW3D_MT_add'). Retourne le nombre de commandes lancées."""
    import ast
    done = 0
    for part in [t.strip() for t in text.split(";") if t.strip()]:
        try:
            node = ast.parse(part if "(" in part else part + "()", mode="eval").body
            if not isinstance(node, ast.Call):
                raise ValueError
            path, f = [], node.func
            while isinstance(f, ast.Attribute):
                path.append(f.attr)
                f = f.value
            if isinstance(f, ast.Name):
                path.append(f.id)
            path = path[::-1]
            if path[:2] == ['bpy', 'ops']:
                path = path[2:]
            if len(path) != 2:
                raise ValueError
            kwargs = {k.arg: ast.literal_eval(k.value) for k in node.keywords if k.arg}
            fn = getattr(getattr(bpy.ops, path[0]), path[1])
            fn('INVOKE_DEFAULT', **kwargs)
            done += 1
        except (SyntaxError, ValueError, TypeError, AttributeError, RuntimeError):
            if report:
                report({'WARNING'}, f"Cannot run: {part}")
    return done


def effective_middle():
    """Action du bouton du milieu : celle des préférences ; avec le style Rhino (orbite au clic droit) et « Keep current keymap »,
    le bouton du milieu ne fait plus rien (ni orbite ni pan : tout passe par le clic droit)."""
    mode = pref("mouse_middle")
    if mode == 'DEFAULT' and pref("nav_style") == 'RHINO' and pref("mouse_orbit") == 'RIGHT':
        return 'NONE'
    return mode


class DESSIN_OT_middle_action(bpy.types.Operator):
    bl_idname = "dessin.middle_action"
    bl_label = "Middle Mouse Button Action"
    bl_description = "Runs the action chosen for the middle mouse button in the add-on preferences"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D'

    def invoke(self, context, event):
        mode = effective_middle()
        if mode in MIDDLE_OPS:
            run_macro(MIDDLE_OPS[mode])
        elif mode == 'CONTEXT_MENU':
            bpy.ops.dessin.context_menu('INVOKE_DEFAULT')
        elif mode == 'CUSTOM':
            run_macro(pref("mouse_middle_op"), self.report)
        return {'FINISHED'}     # NONE (et toute action) : le clic molette n'orbite plus

    def execute(self, context):
        return {'CANCELLED'}


MOUSE_BUTTONS = {'MIDDLE': ('MIDDLEMOUSE', False), 'RIGHT': ('RIGHTMOUSE', False), 'ALT_RIGHT': ('RIGHTMOUSE', True)}
# keymaps où Blender place le clic droit / la molette : le même réglage doit y être posé pour passer en premier
MOUSE_KEYMAPS = (("3D View", 'VIEW_3D'), ("Object Mode", 'EMPTY'), ("Mesh", 'EMPTY'), ("Curve", 'EMPTY'),
                 ("Armature", 'EMPTY'), ("Pose", 'EMPTY'))


MOUSE_KEYMAPS_2D = (("View2D", 'EMPTY'), ("View2D Buttons List", 'EMPTY'), ("Node Editor", 'NODE_EDITOR'), ("Image", 'IMAGE_EDITOR'),
                    ("UV Editor", 'EMPTY'), ("Clip", 'CLIP_EDITOR'), ("Clip Editor", 'CLIP_EDITOR'), ("Graph Editor", 'GRAPH_EDITOR'),
                    ("Dopesheet", 'DOPESHEET_EDITOR'), ("NLA Editor", 'NLA_EDITOR'), ("Sequencer", 'SEQUENCE_EDITOR'),
                    ("SequencerPreview", 'SEQUENCE_EDITOR'), ("Outliner", 'OUTLINER'), ("Property Editor", 'PROPERTIES'),
                    ("Text", 'TEXT_EDITOR'), ("Console", 'CONSOLE'), ("Info", 'INFO'), ("File Browser", 'FILE_BROWSER'))


def mouse_conflict():
    """True si le menu contextuel et l'orbite sont réglés sur le même bouton."""
    orbit, menu = pref("mouse_orbit"), pref("mouse_menu")
    return orbit != 'DEFAULT' and orbit == menu


# ---- Styles de navigation : (opérateur, bouton, alt, maj, ctrl) ajoutés devant le keymap de Blender ----
NAV_STYLES = (
    ('BLENDER', "Blender", "Middle button orbits, Shift + middle pans, Ctrl + middle zooms"),
    ('RHINO', "Rhino", "Right button orbits (pans in side views), Shift + right pans, Ctrl + right zooms"),
    ('SOLIDWORKS', "SolidWorks", "Middle button rotates, Ctrl + middle pans, Shift + middle zooms"),
    ('AUTOCAD', "AutoCAD / Revit / Inventor / Fusion", "Middle button pans, Shift + middle orbits, wheel zooms"),
    ('MAYA', "Maya / Cinema 4D / Houdini", "Alt + left orbits, Alt + middle pans, Alt + right zooms"),
    ('MAX', "3DS Max", "Middle button pans, Alt + middle orbits, wheel zooms"),
    ('CUSTOM', "Custom", "Use the mouse buttons chosen below"),
)
NAV_KEYS = {
    'SOLIDWORKS': (("view3d.move", 'MIDDLEMOUSE', dict(ctrl=True)), ("view3d.zoom", 'MIDDLEMOUSE', dict(shift=True))),
    'AUTOCAD': (("view3d.rotate", 'MIDDLEMOUSE', dict(shift=True)), ("view3d.move", 'MIDDLEMOUSE', {})),
    'MAYA': (("view3d.rotate", 'LEFTMOUSE', dict(alt=True)), ("view3d.move", 'MIDDLEMOUSE', dict(alt=True)),
             ("view3d.zoom", 'RIGHTMOUSE', dict(alt=True))),
    'MAX': (("view3d.rotate", 'MIDDLEMOUSE', dict(alt=True)), ("view3d.move", 'MIDDLEMOUSE', {})),
}


def apply_nav_inputs():
    """Réglages natifs de Blender liés à la navigation (zoom vers le curseur, pivot, sens du zoom...)."""
    try:
        inp = bpy.context.preferences.inputs
        inp.use_zoom_to_mouse = pref("nav_zoom_cursor")
        inp.use_rotate_around_active = True       # toujours : l'orbite tourne autour de la sélection
        inp.use_mouse_depth_navigate = pref("nav_auto_depth")
        inp.invert_zoom_wheel = pref("nav_invert_zoom")
        inp.invert_mouse_zoom = pref("nav_invert_zoom")
        if pref("mouse_menu") == 'RIGHT_CLICK':
            inp.drag_threshold_mouse = pref("mouse_menu_tol")     # seuil clic / glissement de Blender
    except (AttributeError, RuntimeError):
        pass


def register_view_keymap():
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon if wm is not None else None
    if kc is None:
        return
    enabled, persp, button = pref("view_pan"), pref("view_persp"), pref("view_button")
    orbit_sel, menu_sel = pref("mouse_orbit"), pref("mouse_menu")
    orbit_btn = button if orbit_sel == 'DEFAULT' else orbit_sel
    menu_btn = menu_sel if menu_sel not in ('DEFAULT', 'RIGHT_CLICK') else None
    middle_on = effective_middle() != 'DEFAULT' and menu_btn != 'MIDDLE' and orbit_sel != 'MIDDLE'
    hold_on = menu_sel == 'RIGHT_CLICK' and orbit_btn == 'RIGHT'     # menu au relâchement du clic droit (sans glisser)
    nav_items = NAV_KEYS.get(pref("nav_style"), ())
    dbl = pref("nav_dblclick_all")
    remap = orbit_sel != 'DEFAULT' or menu_btn is not None or middle_on or hold_on or bool(nav_items) or dbl
    if not enabled and not remap:
        return

    def add(km, *args, **kw):
        kmi = km.keymap_items.new(*args, **kw)
        _VIEW_KEYMAPS.append((km, kmi))
        return kmi

    keymaps = [kc.keymaps.new(name=n, space_type=t) for n, t in (MOUSE_KEYMAPS if remap else MOUSE_KEYMAPS[:1])]
    if enabled:
        add(keymaps[0], DESSIN_OT_trackpad_pan.bl_idname, 'TRACKPADPAN', 'ANY')
        if persp:
            add(keymaps[0], DESSIN_OT_trackpad_persp.bl_idname, 'TRACKPADPAN', 'ANY', shift=True, ctrl=True)
    for km in keymaps:
        for op, mtype, mods in nav_items:
            add(km, op, mtype, 'PRESS', **mods)
        if dbl:
            add(km, "view3d.view_all", 'MIDDLEMOUSE', 'DOUBLE_CLICK')
        if middle_on:
            add(km, DESSIN_OT_middle_action.bl_idname, 'MIDDLEMOUSE', 'PRESS')
            if effective_middle() == 'NONE':      # Maj / Ctrl + molette (pan, zoom natifs de Blender) ne font rien non plus
                for mods in (dict(shift=True), dict(ctrl=True), dict(shift=True, ctrl=True)):
                    add(km, DESSIN_OT_mouse_block.bl_idname, 'MIDDLEMOUSE', 'PRESS', **mods)
        if menu_btn is not None:
            mtype, alt = MOUSE_BUTTONS[menu_btn]
            add(km, DESSIN_OT_context_menu.bl_idname, mtype, 'PRESS', alt=alt)
            if menu_btn != 'RIGHT' and orbit_btn != 'RIGHT':
                add(km, DESSIN_OT_mouse_block.bl_idname, 'RIGHTMOUSE', 'PRESS')   # le clic droit simple ne fait plus rien
        if (menu_btn is not None and menu_btn == orbit_btn) or (middle_on and orbit_btn == 'MIDDLE'):
            continue                                   # le menu / l'action de la molette a priorité sur ce bouton
        if enabled or orbit_sel != 'DEFAULT' or hold_on:
            mtype, alt = VIEW_BUTTONS[orbit_btn]
            add(km, DESSIN_OT_orbit_pan.bl_idname, mtype, 'PRESS', alt=alt)
            if hold_on:         # clic sans glisser : Blender envoie un évènement CLICK au relâchement -> menu contextuel
                add(km, DESSIN_OT_context_menu.bl_idname, mtype, 'CLICK', alt=alt)
            if (enabled or hold_on) and persp:
                add(km, DESSIN_OT_orbit_persp.bl_idname, mtype, 'PRESS', alt=alt, shift=True, ctrl=True)
        if orbit_sel == 'RIGHT':                       # Shift / Ctrl + clic droit : pan / zoom, comme avec la molette
            add(km, "view3d.move", 'RIGHTMOUSE', 'PRESS', shift=True)
            add(km, "view3d.zoom", 'RIGHTMOUSE', 'PRESS', ctrl=True)
    if orbit_sel == 'RIGHT':
        # tous les autres éditeurs (nodes, UV, timeline, outliner...) : le clic droit fait le pan, comme la molette par défaut
        for n, t in MOUSE_KEYMAPS_2D:
            km = kc.keymaps.new(name=n, space_type=t)
            if menu_btn is not None:
                mtype, alt = MOUSE_BUTTONS[menu_btn]
                add(km, DESSIN_OT_context_menu.bl_idname, mtype, 'PRESS', alt=alt)
            if menu_btn != 'RIGHT':
                add(km, DESSIN_OT_pan2d.bl_idname, 'RIGHTMOUSE', 'PRESS')
                if hold_on:
                    add(km, DESSIN_OT_context_menu.bl_idname, 'RIGHTMOUSE', 'CLICK')
    try:
        wm.keyconfigs.update()
    except (AttributeError, RuntimeError):
        pass


def unregister_view_keymap():
    for km, kmi in _VIEW_KEYMAPS:
        try:
            km.keymap_items.remove(kmi)
        except (RuntimeError, ReferenceError, TypeError):
            pass
    _VIEW_KEYMAPS.clear()
    try:
        bpy.context.window_manager.keyconfigs.update()   # retire aussi l'entrée de la configuration utilisateur
    except (AttributeError, RuntimeError):
        pass


# ---- G / R / S : Move / Rotate / Scale du Toolkit à la place de ceux de Blender (désactivé par défaut) ----
GRS_SHORTCUTS = (("G", "dessin.deplacer_tool"), ("R", "dessin.rotation_tool"), ("S", "dessin.echelle_tool"))
_GRS_KEYMAPS = []   # (keymap, item) enregistrés dans la configuration « addon »


class DESSIN_OT_grs_key(bpy.types.Operator):
    """G / R / S depuis le keymap des outils du Toolkit : prioritaire sur les raccourcis de Blender (mode Objet compris)."""
    bl_idname = "dessin.grs_key"
    bl_label = "Switch to Move / Rotate / Scale tool"
    bl_options = {'INTERNAL'}

    tool: bpy.props.StringProperty(options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D'

    def invoke(self, context, event):
        if not pref("remap_grs") or context.mode not in {'OBJECT', 'EDIT_MESH'} or event.ctrl or event.alt or event.shift or event.oskey:
            return {'PASS_THROUGH'}
        try:
            bpy.ops.wm.tool_set_by_id(name=self.tool)
        except RuntimeError:
            return {'PASS_THROUGH'}
        return {'FINISHED'}

    def execute(self, context):
        return {'CANCELLED'}


def add_grs_to_tool_keymaps(tools):
    """Ajoute G / R / S au keymap de chaque outil du Toolkit (une seule fois par classe)."""
    items = tuple(("dessin.grs_key", {"type": key, "value": 'PRESS'}, {"properties": [("tool", tool)]})
                  for key, tool in GRS_SHORTCUTS)
    for cls in tools:
        if getattr(cls, "_grs_added", False):
            continue
        cls.bl_keymap = tuple(cls.bl_keymap) + items
        cls._grs_added = True


def register_grs_keymap():
    if not pref("remap_grs"):
        return
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon if wm is not None else None
    if kc is None:
        return
    for km_name, _title in SHORTCUT_MODES:
        km = kc.keymaps.new(name=km_name, space_type='EMPTY')
        for key, tool in GRS_SHORTCUTS:
            kmi = km.keymap_items.new("wm.tool_set_by_id", key, 'PRESS')
            kmi.properties.name = tool
            _GRS_KEYMAPS.append((km, kmi))
    try:
        wm.keyconfigs.update()
    except (AttributeError, RuntimeError):
        pass


def unregister_grs_keymap():
    for km, kmi in _GRS_KEYMAPS:
        try:
            km.keymap_items.remove(kmi)
        except (RuntimeError, ReferenceError, TypeError):
            pass
    _GRS_KEYMAPS.clear()
    try:
        bpy.context.window_manager.keyconfigs.update()   # retire aussi l'entrée de la configuration utilisateur
    except (AttributeError, RuntimeError):
        pass


def _update_grs_keymap(self=None, context=None):
    unregister_grs_keymap()
    register_grs_keymap()


def _update_hide_native(self, context):
    _hide_native_tools()
    _update_native_gizmos()


def _update_view_keymap(self=None, context=None):
    unregister_view_keymap()
    register_view_keymap()


def _update_nav_style(self, context):
    """Un style règle le bouton d'orbite (Rhino) ou ajoute ses propres raccourcis ; « Custom » ne touche à rien."""
    style = self.nav_style
    if style == 'RHINO':
        self.mouse_orbit = 'RIGHT'
        self.mouse_menu = 'RIGHT_CLICK'
        return
    if style != 'CUSTOM' and (self.mouse_orbit != 'DEFAULT' or self.mouse_menu == 'RIGHT_CLICK'):
        self.mouse_menu = 'DEFAULT' if self.mouse_menu == 'RIGHT_CLICK' else self.mouse_menu
        self.mouse_orbit = 'DEFAULT'
        return
    _update_view_keymap()


def _update_cursor(self, context):
    try:
        for win in bpy.context.window_manager.windows:
            for area in win.screen.areas:
                area.tag_redraw()
    except (AttributeError, RuntimeError):
        pass


def _update_nav_inputs(self, context):
    apply_nav_inputs()
    _update_view_keymap()


# ---- Named Views (vues nommées, comme dans Rhino) : menu « Named Views » de l'en-tête du viewport 3D ----
BASE_VIEWS = (("Top", 'TOP'), ("Front", 'FRONT'), ("Perspective", None), ("Right", 'RIGHT'),
              ("Bottom", 'BOTTOM'), ("Back", 'BACK'), ("Left", 'LEFT'))
DEFAULT_TABS = "Top,Front,Perspective,Right"       # vues de base affichées en onglets (comme Rhino)
_AXIS_EULER = {'TOP': (0.0, 0.0, 0.0), 'BOTTOM': (math.pi, 0.0, 0.0), 'FRONT': (math.pi / 2, 0.0, 0.0),
               'BACK': (math.pi / 2, 0.0, math.pi), 'LEFT': (math.pi / 2, 0.0, -math.pi / 2),
               'RIGHT': (math.pi / 2, 0.0, math.pi / 2)}
_PERSP_EULER = (math.radians(63.559), 0.0, math.radians(46.692))   # vue par défaut de Blender


def _axis_quat(axis):
    from mathutils import Euler
    return Euler(_AXIS_EULER[axis] if axis else _PERSP_EULER, 'XYZ').to_quaternion()


def detect_axis(quat, tol=1e-3):
    """'TOP', 'FRONT'... si la rotation est exactement une vue alignée sur un axe, sinon None."""
    for axis in _AXIS_EULER:
        q = _axis_quat(axis)
        if abs(abs(q.dot(quat)) - 1.0) < tol:
            return axis
    return None


def _late_imports():
    """Noms définis dans des modules chargés après celui-ci : ils ne servent qu'à l'exécution des outils."""
    global _CMD, _hide_native_tools, cmd_hit
    from .views import _CMD
    from .command_line import cmd_hit
    from .registration import _hide_native_tools
