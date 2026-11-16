"""Wanderer CAD : Préférences de l'add-on."""

import bpy
import os

from .core import PREF_DEFAULTS, lang, pref_applied_language
from .snapping import _perf_caches_clear
from .drawing import _HOVER
from .icons import ICON_PALETTES
from .navigation import (
    DESSIN_OT_shortcuts_clear, NAV_STYLES, SHORTCUT_MODES, _update_cursor, _update_grs_keymap, _update_hide_native,
    _update_auto_depth, _update_invert_zoom, _update_nav_inputs, _update_nav_style, _update_zoom_cursor, _update_view_keymap, mouse_conflict, shortcut_tools, user_shortcut,
)
from .views import CMD_KEY_ITEMS
from .command_line import (
    DESSIN_MT_mouse_menu, MENU_BUTTON_ITEMS, _reload_addon_later, _update_cmd_line, _update_icon_palette,
    _update_mouse_orbit, alias_changed, alias_target, cmd_entries, language_changed,
)
from .languages import LANGUAGE_ITEMS


class DESSIN_OT_prefs_reset(bpy.types.Operator):
    bl_idname = "dessin.prefs_reset"
    bl_label = "Reset to defaults"
    bl_description = "Puts every Wanderer setting back to its default value (keyboard shortcuts are not changed)"
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event, message="Reset all Wanderer settings to their defaults?")

    def execute(self, context):
        try:
            prefs = context.preferences.addons[__package__].preferences
        except KeyError:
            return {'CANCELLED'}
        palette_before = prefs.icon_palette
        for name in list(PREF_DEFAULTS):
            try:
                prefs.property_unset(name)
            except (AttributeError, RuntimeError, TypeError):
                pass
        for fn in (_update_hide_native, _update_cmd_line, _update_view_keymap, _update_grs_keymap):
            try:
                fn(prefs, context) if fn is _update_hide_native else fn()
            except Exception:
                pass
        if prefs.icon_palette != palette_before:
            _reload_addon_later()
        self.report({'INFO'}, "Wanderer settings reset")
        return {'FINISHED'}


def _update_perf(self=None, context=None):
    """Budget d'accrochage ou qualité des courbes modifiés : les données gardées en mémoire sont recalculées."""
    _perf_caches_clear()
    _HOVER["version"] += 1
    _HOVER["data"] = None


# ---- alias de l'utilisateur (AliasEdit d'AutoCAD, alias de Rhino) ----

_ALIAS_IO = {"busy": False}


def _alias_file():
    """Copie des alias dans le dossier de configuration de Blender : elle survit à la désinstallation de l'add-on, dont les
    préférences sont effacées (mise à jour par « retirer puis installer »)."""
    return os.path.join(bpy.utils.user_resource('CONFIG', path="wanderer_cad", create=True), "aliases.json")


def aliases_save(prefs):
    if _ALIAS_IO["busy"] or prefs is None:
        return
    try:
        import json
        data = [{"alias": a.alias, "command": a.command} for a in prefs.aliases]
        with open(_alias_file(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def aliases_restore(prefs):
    """Add-on réinstallé (préférences vides) : reprend les alias gardés dans le dossier de configuration. Retourne leur nombre."""
    if prefs is None:
        return 0
    try:
        if len(prefs.aliases):
            return 0
        import json
        with open(_alias_file(), "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return 0
    n = 0
    _ALIAS_IO["busy"] = True
    try:
        for d in data if isinstance(data, list) else ():
            if isinstance(d, dict) and str(d.get("alias", "")).strip():
                it = prefs.aliases.add()
                it.alias, it.command = str(d["alias"]), str(d.get("command", ""))
                n += 1
    except Exception:
        pass
    finally:
        _ALIAS_IO["busy"] = False
    if n:
        alias_changed()
    return n


def aliases_restore_soon():
    """À l'activation de l'add-on : tout de suite si les préférences sont prêtes, sinon un instant plus tard."""
    def go():
        try:
            aliases_restore(_wanderer_prefs(bpy.context))
        except Exception:
            pass
        return None
    if _wanderer_prefs(bpy.context) is not None:
        go()
    else:
        try:
            bpy.app.timers.register(go, first_interval=0.5)
        except Exception:
            pass


def _alias_update(self, context):
    alias_changed()
    aliases_save(_wanderer_prefs(context))


class DESSIN_PG_alias(bpy.types.PropertyGroup):
    alias: bpy.props.StringProperty(
        name="Alias", default="", update=_alias_update,
        description="What you type in the command line (for example ee)")
    command: bpy.props.StringProperty(
        name="Command", default="", update=_alias_update,
        description="The command it runs: its name or one of its aliases (for example Extend Curve, extend, Move, m)")


def _wanderer_prefs(context):
    try:
        return context.preferences.addons[__package__].preferences
    except (KeyError, AttributeError, TypeError):
        return None


def _prefs_dirty(context):
    try:
        context.preferences.is_dirty = True        # enregistré avec les préférences de Blender
    except (AttributeError, TypeError):
        pass


class DESSIN_OT_alias_add(bpy.types.Operator):
    bl_idname = "dessin.alias_add"
    bl_label = "Add alias"
    bl_description = "Adds a command alias: type the alias, then the command it runs (its name or one of its aliases)"
    bl_options = {'INTERNAL'}

    alias: bpy.props.StringProperty(default="", options={'SKIP_SAVE'})
    command: bpy.props.StringProperty(default="", options={'SKIP_SAVE'})

    def execute(self, context):
        prefs = _wanderer_prefs(context)
        if prefs is None:
            return {'CANCELLED'}
        it = prefs.aliases.add()
        it.alias, it.command = self.alias, self.command
        alias_changed()
        aliases_save(prefs)
        _prefs_dirty(context)
        return {'FINISHED'}


class DESSIN_OT_alias_remove(bpy.types.Operator):
    bl_idname = "dessin.alias_remove"
    bl_label = "Remove alias"
    bl_description = "Removes this alias"
    bl_options = {'INTERNAL'}

    index: bpy.props.IntProperty(default=-1, options={'SKIP_SAVE'})

    def execute(self, context):
        prefs = _wanderer_prefs(context)
        if prefs is None or not (0 <= self.index < len(prefs.aliases)):
            return {'CANCELLED'}
        prefs.aliases.remove(self.index)
        alias_changed()
        aliases_save(prefs)
        _prefs_dirty(context)
        return {'FINISHED'}


def _prop_hint(layout, data, name, hint):
    """Champ texte avec un texte d'aide gris tant qu'il est vide (Blender 4.1 et plus)."""
    try:
        layout.prop(data, name, text="", placeholder=hint)
    except TypeError:
        layout.prop(data, name, text="")


def draw_aliases(layout, prefs):
    """Liste des alias : alias, commande, ce qu'il lance (ou « unknown command »), bouton pour le retirer."""
    try:
        entries = cmd_entries()
    except Exception:
        entries = []
    col = layout.column(align=True)
    if not len(prefs.aliases):
        col.label(text="No alias yet. Example: the alias  ee  for the command  Extend Curve.", icon='INFO')
    for i, it in enumerate(prefs.aliases):
        row = col.row(align=True)
        _prop_hint(row, it, "alias", "Alias you type (e.g. ee)")
        row.label(text="", icon='FORWARD')
        _prop_hint(row, it, "command", "Command it runs (e.g. Extend Curve)")
        k = alias_target(entries, it.command) if it.command.strip() else None
        sub = row.row(align=True)
        sub.ui_units_x = 9
        if k is not None:
            sub.label(text=entries[k]["label"], icon='CHECKMARK')
        elif it.command.strip():
            sub.label(text="unknown command", icon='ERROR')
        else:
            sub.label(text="")
        row.operator(DESSIN_OT_alias_remove.bl_idname, text="", icon='X').index = i
    layout.operator(DESSIN_OT_alias_add.bl_idname, icon='ADD')


class DESSIN_OT_alias_edit(bpy.types.Operator):
    bl_idname = "dessin.alias_edit"
    bl_label = "Command aliases"
    bl_description = ("Like AliasEdit in AutoCAD and the aliases of Rhino: create your own aliases for the command line. "
                      "Also in Preferences > Add-ons > Wanderer CAD")
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        if _wanderer_prefs(context) is None:
            self.report({'WARNING'}, "Wanderer preferences are not available")
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self, width=560)

    def draw(self, context):
        lay = self.layout
        lay.label(text="Alias, then the command it runs (its name or one of its aliases). Your aliases come first.")
        draw_aliases(lay, _wanderer_prefs(context))

    def execute(self, context):
        alias_changed()
        aliases_save(_wanderer_prefs(context))
        _prefs_dirty(context)
        return {'FINISHED'}


# ---- préréglages : retrouver d'un clic ses habitudes de Rhino, d'AutoCAD, de 3ds Max ou de Blender ----
# Deux blocs indépendants : la façon de travailler (navigation, souris, curseur, saisie des commandes) et l'apparence
# (thème). On peut garder la façon de travailler de Blender avec l'apparence de Rhino, par exemple.

PRESET_STYLES = (('RHINO', "Rhino"), ('AUTOCAD', "AutoCAD"), ('MAX', "3ds Max"), ('BLENDER', "Blender"))
_WORKFLOW_KEYS = ("nav_style", "cursor_style", "nav_zoom_cursor", "cmd_line", "cmd_type", "rclick_enter", "enter_last",
                  "auto_idle", "esc_deselect", "copy_key")
WORKFLOW_PRESETS = {
    # Rhino : le bouton droit tourne la vue, clic droit = Entrée. Quick Type (taper une lettre lance la ligne de commande)
    # reste éteint par défaut : les lettres gardent les raccourcis de Blender, Espace ouvre la ligne de commande ; on
    # l'allume depuis la barre du bas (ou Maj + Q) quand on le veut
    'RHINO': {"nav_style": 'RHINO', "cursor_style": 'RHINO', "nav_zoom_cursor": True, "cmd_line": True, "cmd_type": False,
              "rclick_enter": True, "enter_last": True, "auto_idle": True, "esc_deselect": True, "copy_key": 'ALT'},
    # AutoCAD : le bouton du milieu déplace la vue, réticule ; Quick Type éteint par défaut, comme pour Rhino
    'AUTOCAD': {"nav_style": 'AUTOCAD', "cursor_style": 'AUTOCAD', "nav_zoom_cursor": True, "cmd_line": True, "cmd_type": False,
                "rclick_enter": True, "enter_last": True, "auto_idle": True, "esc_deselect": True, "copy_key": 'ALT'},
    # 3ds Max : le bouton du milieu déplace la vue (Alt + milieu tourne), zoom vers la souris, Maj + glisser copie ;
    # un clic droit termine la commande, mais Entrée ne relance pas la précédente (ce n'est pas une habitude de 3ds Max)
    'MAX': {"nav_style": 'MAX', "cursor_style": 'RHINO', "nav_zoom_cursor": True, "cmd_line": True, "cmd_type": False,
            "rclick_enter": True, "enter_last": False, "auto_idle": True, "esc_deselect": True, "copy_key": 'SHIFT'},
    # Blender : navigation et raccourcis de Blender (les lettres gardent leur rôle ; Espace ouvre la ligne de commande)
    'BLENDER': {k: PREF_DEFAULTS[k] for k in _WORKFLOW_KEYS},
}
PRESET_TIPS = {
    'RHINO': "Work as in Rhino: the right button orbits (a quick right click is Enter), Rhino cursor, zoom towards the cursor. Space opens the command line; Quick Type stays off (turn it on in the bottom bar, or Shift+Q, to start a command by typing a letter)",
    'AUTOCAD': "Work as in AutoCAD: the middle button pans (Shift + middle orbits), crosshair cursor, zoom towards the cursor. Space opens the command line; Quick Type stays off (turn it on in the bottom bar, or Shift+Q, to start a command by typing a letter)",
    'MAX': "Work as in 3ds Max: the middle button pans (Alt + middle orbits), zoom towards the cursor, Shift + drag copies an object (Clone Options: copy or instance, number, name) and extrudes edges or faces. Space opens the command line; Quick Type stays off (turn it on in the bottom bar, or Shift+Q, to start a command by typing a letter)",
    'BLENDER': "Work as in Blender: Blender's navigation, the letters keep Blender's shortcuts (Space opens the command line). The Wanderer tools stay",
}


def _alt_emulates_mouse():
    """Blender émule-t-il le bouton du milieu avec Alt ? Alt + glisser fait alors tourner la vue au lieu de copier."""
    try:
        inp = bpy.context.preferences.inputs
        return bool(inp.use_mouse_emulate_3_button and inp.mouse_emulate_3_button_modifier == 'ALT')
    except AttributeError:
        return False


def workflow_preset_of(prefs):
    """Le préréglage que suivent les réglages actuels ('RHINO', 'AUTOCAD', 'BLENDER'), ou None s'ils sont personnalisés."""
    for style, values in WORKFLOW_PRESETS.items():
        try:
            if all(getattr(prefs, k) == v for k, v in values.items()):
                return style
        except AttributeError:
            return None
    return None


def apply_workflow_preset(prefs, style):
    """Applique la façon de travailler `style`. Retourne les noms des réglages qui ont changé."""
    changed = []
    for name, value in WORKFLOW_PRESETS[style].items():       # (le style de navigation d'abord : il règle la souris)
        try:
            if getattr(prefs, name) != value:
                setattr(prefs, name, value)
                changed.append(name)
        except (AttributeError, TypeError):
            pass
    return changed


class DESSIN_OT_apply_preset(bpy.types.Operator):
    bl_idname = "dessin.apply_preset"
    bl_label = "Apply preset"
    bl_description = "Sets several Wanderer options at once, to work like Rhino, AutoCAD, 3ds Max or Blender"
    bl_options = {'INTERNAL'}

    style: bpy.props.EnumProperty(items=[(k, n, "") for k, n in PRESET_STYLES], default='RHINO', options={'SKIP_SAVE'})

    @classmethod
    def description(cls, context, properties):
        return PRESET_TIPS[properties.style]

    def execute(self, context):
        prefs = _wanderer_prefs(context)
        if prefs is None:
            return {'CANCELLED'}
        name = dict(PRESET_STYLES)[self.style]
        n = len(apply_workflow_preset(prefs, self.style))
        _prefs_dirty(context)
        self.report({'INFO'}, f"{name} preset  ·  " + (f"{n} option(s) changed" if n else "already set"))
        return {'FINISHED'}


class DESSIN_AP_prefs(bpy.types.AddonPreferences):
    bl_idname = __package__

    aliases: bpy.props.CollectionProperty(type=DESSIN_PG_alias)

    snap_budget: bpy.props.FloatProperty(
        name="Snap budget (million points)", default=2.0, min=0.0, max=50.0, step=50, precision=1, update=_update_perf,
        description="Very large scenes: number of snap points kept ready for the whole scene. Beyond it the heaviest objects are "
                    "read only when the cursor passes over them, so tools start faster and use less memory. "
                    "Curves and outlines are never reduced. 0: no limit")
    curve_quality: bpy.props.EnumProperty(
        name="Curve quality", default='NORMAL', update=_update_perf,
        items=(('DRAFT', "Draft (48 sides)", "Lightest meshes. A circle gives 48 sides (0.21 % of the radius off the true circle)"),
               ('NORMAL', "Normal (96 sides)", "A circle gives 96 sides (0.054 % of the radius off the true circle)"),
               ('FINE', "Fine (192 sides)", "A circle gives 192 sides (0.013 % of the radius off the true circle)"),
               ('VERY_FINE', "Very fine (384 sides)", "Heaviest meshes. A circle gives 384 sides (0.003 % of the radius off the true circle)")),
        description="Number of sides the tools give to circles, arcs and curves when they build a mesh or cut "
                    "(Extrude, Planar Surface, Revolve, Trim...). The curves themselves stay exact")
    far_warning: bpy.props.BoolProperty(
        name="Warn when drawing far from the origin", default=True,
        description="Blender stores coordinates with about 7 significant digits. Far from the origin the smallest step grows "
                    "(about 0.1 mm at 1 km): a message tells you once per file")

    search: bpy.props.StringProperty(name="Search", default="", options={'TEXTEDIT_UPDATE'})
    esc_deselect: bpy.props.BoolProperty(
        name="Deselect when leaving a tool", default=True,
        description="Esc (and the end of a transform command) also deselects the objects / elements")
    enter_last: bpy.props.BoolProperty(
        name="Enter repeats the last typed value", default=True,
        description="While a tool waits for a value (radius, size, distance, height, angle), Enter with nothing typed uses the "
                    "value you typed last time in that tool, like the <default> of Rhino and AutoCAD. A click still takes "
                    "the value under the mouse")
    light_preview: bpy.props.BoolProperty(
        name="Light preview for heavy selections", default=True,
        description="Move, Rotate, Scale... on a heavy selection or a very complex scene: boxes follow the mouse and the real objects move at the click, so the viewport stays smooth")
    auto_idle: bpy.props.BoolProperty(
        name="Return to Select", default=True,
        description="After a command, or Esc, the Select tool becomes active again. Off: the tool stays active")
    smart_tracks: bpy.props.BoolProperty(
        name="Smart Tracks", default=True,
        description="Tracking lines from snapped points (axis alignment, intersections, midpoint of two tracked points)")
    show_tool_select: bpy.props.BoolProperty(
        name="Select (box / circle / lasso)", default=False, update=_update_hide_native,
        description="Shows Blender's own Select tools in the toolbar (Select replaces them)")
    show_toolbar_tools: bpy.props.BoolProperty(
        name="Show Wanderer tools in the toolbar", default=True, update=lambda self, context: _update_toolbar_filter(),
        description="Shows the Wanderer tools in the left toolbar. Off: the toolbar keeps only Select / Lasso and Blender's tools; "
                    "the tools stay available in the Wanderer tab of the sidebar, with their shortcuts and in the command line")
    show_tool_annotate: bpy.props.BoolProperty(name="Annotate", default=False, update=_update_hide_native,
                                               description="Shows Blender's own Annotate tools in the toolbar")
    show_tool_measure: bpy.props.BoolProperty(name="Measure", default=False, update=_update_hide_native,
                                              description="Shows Blender's own Measure tool in the toolbar")
    show_tool_cube: bpy.props.BoolProperty(name="Add Cube", default=False, update=_update_hide_native,
                                           description="Shows Blender's own Add primitive tools (Add Cube...) in the toolbar")
    show_tool_cursor: bpy.props.BoolProperty(name="Cursor", default=False, update=_update_hide_native,
                                             description="Shows Blender's 3D Cursor tool in the toolbar")
    show_tool_move: bpy.props.BoolProperty(name="Move", default=False, update=_update_hide_native,
                                           description="Shows Blender's own Move tool in the toolbar")
    show_tool_rotate: bpy.props.BoolProperty(name="Rotate", default=False, update=_update_hide_native,
                                             description="Shows Blender's own Rotate tool in the toolbar")
    show_tool_scale: bpy.props.BoolProperty(name="Scale", default=False, update=_update_hide_native,
                                            description="Shows Blender's own Scale tools in the toolbar")
    show_tool_transform: bpy.props.BoolProperty(name="Transform", default=False, update=_update_hide_native,
                                                description="Shows Blender's own Transform (all-in-one gizmo) tool in the toolbar")
    gumball_rot90: bpy.props.BoolProperty(
        name="Gumball rotation in steps", default=True,
        description="On: the Gumball rotates in steps and Shift gives free rotation. Off: free rotation, Shift gives steps")
    copy_key: bpy.props.EnumProperty(
        name="Copy while dragging",
        items=(('ALT', "Alt + drag (Rhino)", "Hold Alt while dragging an object or a Gumball handle to move a copy, like in Rhino. "
                "Shift keeps the dominant axis"),
               ('SHIFT', "Shift + drag (3ds Max)", "Like in 3ds Max: Shift + drag an object or a Gumball handle opens Clone "
                "Options (copy or instance, number of copies, name); on edges or faces it extrudes, and Ctrl + Shift + drag "
                "copies them. The copy is kept even if you let go of Shift. Alt then keeps the dominant axis; Shift + click "
                "still adds to the selection")),
        default='ALT',
        description="Key that turns a drag (an object or a Gumball handle) into a copy")
    gumball_step: bpy.props.EnumProperty(
        name="Rotation step", default='90',
        items=(('5', "5°", ""), ('10', "10°", ""), ('15', "15°", ""), ('30', "30°", ""), ('45', "45°", ""), ('90', "90°", "")),
        description="Angle of each step when the Gumball rotates with steps enabled")
    gumball_line: bpy.props.FloatProperty(
        name="Arc thickness", default=3.0, min=1.0, max=8.0, precision=1,
        description="Line thickness of the Gumball rotation arcs, in pixels")
    rich_tooltips: bpy.props.BoolProperty(
        name="Detailed tool tooltips", default=True, update=_update_icon_palette,
        description="Hovering a tool shows how to use it step by step, its command line alias and the useful keys. Changing it reloads the add-on")
    language: bpy.props.EnumProperty(
        name="Language", default='EN', items=LANGUAGE_ITEMS, update=language_changed,
        description="Language of the tool names and of the command line, with the command aliases AutoCAD and Rhino use "
                    "in that language. Applied at once (the add-on reloads)")
    icon_palette: bpy.props.EnumProperty(
        name="Toolbar icon colors", default='EARTH', update=_update_icon_palette,
        items=[(c, n, d) for c, n, d, _k in ICON_PALETTES],
        description="Color scheme of the toolbar icons. Changing it reloads the add-on")
    remap_grs: bpy.props.BoolProperty(
        name="G / R / S use the Toolkit tools (Recommended)", default=False, update=_update_grs_keymap,
        description="G, R and S activate the Toolkit Move, Rotate and Scale tools (Object and Edit mode) instead of Blender's own. "
                    "Off by default: you can still assign any key to any tool below")
    view_pan: bpy.props.BoolProperty(
        name="Pan in orthographic side views", default=True, update=_update_view_keymap,
        description="In Front / Top / Right... views the orbit button pans instead of orbiting (perspective views are unchanged).")
    view_persp: bpy.props.BoolProperty(
        name="Ctrl + Shift + orbit button: orbit out of the view", default=True, update=_update_view_keymap,
        description="In orthographic side views, holding Ctrl + Shift with the orbit button orbits. The view switches to perspective "
                    "only if Auto Perspective is on in Preferences > Navigation; otherwise it stays orthographic (User Orthographic)")
    view_button: bpy.props.EnumProperty(
        name="Orbit button", default='MIDDLE', update=_update_view_keymap,
        items=(('MIDDLE', "Middle mouse button", "Your orbit button is the middle mouse button (Blender default)"),
               ('RIGHT', "Right mouse button", "Your orbit button is the right mouse button (a simple right click no longer opens the context menu in side views)"),
               ('ALT_LEFT', "Alt + Left mouse button", "Your orbit button is Alt + left mouse button (3-button emulation)")),
        description="The button you use to orbit")

    cursor_style: bpy.props.EnumProperty(
        name="Crosshair style", default='AUTOCAD', update=_update_cursor,
        items=(('RHINO', "Rhino", "Selection box with four detached bars"),
               ('AUTOCAD', "AutoCAD", "Two lines crossing the view, with a selection box at the center")),
        description="Cursor shown by the drawing tools")
    cursor_size: bpy.props.IntProperty(
        name="Crosshair size", default=8, min=1, max=100, subtype='PERCENTAGE', update=_update_cursor,
        description="Length of the crosshair lines as a percentage of the view (100: full screen, like AutoCAD)")
    cursor_pick: bpy.props.FloatProperty(
        name="Pick box size", default=2.0, min=1.0, max=20.0, precision=1, subtype='PIXEL', update=_update_cursor,
        description="Half-size of the square at the center of the crosshair, in pixels")
    cursor_color: bpy.props.FloatVectorProperty(
        name="Crosshair color", default=(1.0, 1.0, 1.0), min=0.0, max=1.0, subtype='COLOR', size=3, update=_update_cursor,
        description="Color of the crosshair")
    nav_style: bpy.props.EnumProperty(
        name="Navigation style", default='BLENDER', update=_update_nav_style,
        items=NAV_STYLES, description="Mouse navigation of the 3D viewport, like in other CAD / 3D programs")
    nav_zoom_cursor: bpy.props.BoolProperty(
        name="Zoom to cursor", default=False, update=_update_zoom_cursor,
        description="The wheel zooms towards the mouse pointer instead of the center of the view")
    nav_invert_zoom: bpy.props.BoolProperty(
        name="Invert zoom direction", default=False, update=_update_invert_zoom,
        description="Reverses the wheel and the drag zoom direction")
    nav_auto_depth: bpy.props.BoolProperty(
        name="Orbit around the point under the cursor", default=False, update=_update_auto_depth,
        description="Orbit and zoom use the surface under the mouse pointer as pivot (Auto Depth)")
    nav_dblclick_all: bpy.props.BoolProperty(
        name="Double-click middle button: Zoom Extents", default=False, update=_update_nav_inputs,
        description="Double-clicking the middle button frames all the objects")

    mouse_orbit: bpy.props.EnumProperty(
        name="Orbit button", default='DEFAULT', update=_update_mouse_orbit,
        items=(('DEFAULT', "Keep current keymap", "Do not change how the view is orbited"),
               ('MIDDLE', "Middle mouse button", "Orbit with the middle mouse button"),
               ('RIGHT', "Right mouse button", "Orbit with the right mouse button (Shift + right: pan, Ctrl + right: zoom)")),
        description="Mouse button that orbits the view (and pans in all the other editors)")
    mouse_menu: bpy.props.EnumProperty(
        name="Context menu button", default='DEFAULT', update=_update_view_keymap, items=MENU_BUTTON_ITEMS,
        description="Mouse button that opens the context menu")
    mouse_middle: bpy.props.EnumProperty(
        name="Middle button action", default='DEFAULT', update=_update_view_keymap,
        items=(('DEFAULT', "Keep current keymap", "Do not change the middle mouse button (it follows the two settings above)"),
               ('NONE', "Nothing", "A middle click does nothing (it no longer orbits)"),
               ('PAN', "Pan", "Pan the view"),
               ('ZOOM', "Zoom", "Zoom the view"),
               ('VIEW_ALL', "Frame All", "Show all objects"),
               ('VIEW_SELECTED', "Frame Selected", "Frame the selected objects"),
               ('PERSP', "Perspective / Orthographic", "Toggle between perspective and orthographic"),
               ('CONTEXT_MENU', "Context menu", "Open the context menu"),
               ('CUSTOM', "Custom command / macro", "Run the command(s) typed below")),
        description="What the middle mouse button does. The orbit / context menu settings above take priority when they use the middle button")
    mouse_middle_op: bpy.props.StringProperty(
        name="Command", default="", update=_update_view_keymap,
        description="One or several Blender commands separated by ';', e.g. view3d.view_selected ; "
                    "wm.call_menu(name='VIEW3D_MT_add'). Tip: right-click a button in Blender > Copy Python Command")
    cmd_line: bpy.props.BoolProperty(
        name="Command line", default=True, update=_update_cmd_line,
        description="Shows a command bar at the bottom of the 3D viewport: prompt and options of the active tool, "
                    "and a field to type the name of a command")
    cmd_type: bpy.props.BoolProperty(
        name="Quick Type: start a command by typing", default=False, update=_update_cmd_line,
        description="Quick Type: typing a letter in the 3D viewport starts the command line with that letter (Enter or Space to run), "
                    "like Rhino / AutoCAD. While it is on, the letters no longer trigger Blender's own shortcuts there; "
                    "turn it off to get them back (Space still opens the command line)")
    cmd_size: bpy.props.IntProperty(
        name="Command bar size", default=100, min=40, max=250, subtype='PERCENTAGE', update=_update_cmd_line,
        description="Size of the command bar text and pill (lower it if it looks too big on your screen)")
    mode_icons: bpy.props.BoolProperty(
        name="Mode bar: icons only", default=False, update=_update_cmd_line,
        description="Always show the mode buttons at the bottom right of the 3D viewport (Grid Snap, Ortho, Polar, OSnap, "
                    "SmartTrack, Gumball, Auto CPlane, Quick Type) as icons, even when the viewport is wide. "
                    "Off: they show their names and only turn into icons when the viewport gets narrow")
    cmd_key: bpy.props.EnumProperty(
        name="Open with", items=CMD_KEY_ITEMS, default='SPACE', update=_update_cmd_line,
        description="Key that opens the command line in the 3D viewport")
    curve_points: bpy.props.BoolProperty(
        name="Show control points of selected curves", default=True,
        description="Shows the anchor / control points of the selected curves in the 3D viewport, like « Points On » in Rhino "
                    "(Tab: edit them)")
    rclick_enter: bpy.props.BoolProperty(
        name="Enable quick secondary click as return key", default=True,
        description="By default secondary click (right click) displays the context menu. "
                    "Enabled: a quick right click acts as the return key while a command runs; dragging still orbits")
    mouse_menu_tol: bpy.props.IntProperty(
        name="Movement tolerance", default=6, min=1, max=50, subtype='PIXEL', update=_update_nav_inputs,
        description="Pixels the mouse can move during a right click before it counts as a drag (orbit)")

    # ---- Préférences : une section par sujet, dans l'ordre où l'on s'en sert ----
    # Chaque section est un panneau repliable : ouvertes, celles que l'on règle en arrivant (préréglages, apparence,
    # navigation, ligne de commande) ; fermées, celles que l'on ne touche qu'une fois (outils, performances, DXF, raccourcis).

    def _panel(self, layout, key, title, closed=False):
        header, body = layout.panel("dessin_prefs_" + key, default_closed=closed)
        header.label(text=title)
        return body

    def _split(self, layout):
        """Colonne à libellés alignés (comme le reste des préférences de Blender)."""
        col = layout.column()
        col.use_property_split = True
        col.use_property_decorate = False
        return col

    def _draw_presets(self, layout):
        now = workflow_preset_of(self)
        layout.label(text="Find your habits in one click. A preset only sets options that stay editable below.  "
                          "Current workflow: " + (dict(PRESET_STYLES)[now] if now else "custom"), icon='INFO')
        row = layout.row(align=True)
        row.label(text="Workflow")
        for style, name in PRESET_STYLES:
            op = row.operator(DESSIN_OT_apply_preset.bl_idname, text=name, depress=(now == style))
            op.style = style

    def _draw_appearance(self, layout):
        col = layout.column(align=True)        # (deux lignes : un libellé de Blender ne passe pas à la ligne)
        col.label(text="The Wanderer themes are no longer included in the add-on.", icon='INFO')
        col.label(text="Get them from the Blender Extensions website (extensions.blender.org) or next to the add-on on "
                       "the GitHub releases page,", icon='BLANK1')
        col.label(text="then choose one in Preferences > Themes.", icon='BLANK1')
        col = self._split(layout)
        col.prop(self, "icon_palette")
        col.prop(self, "language")
        if lang() != pref_applied_language():
            layout.label(text="Applying the language... If the names do not change, restart Blender.", icon='INFO')
        else:
            layout.label(text="The language is applied at once. If a name stays in the previous language, restart Blender.")
        layout.prop(self, "rich_tooltips")

    def _draw_navigation(self, layout):
        col = self._split(layout)
        col.prop(self, "nav_style")
        col.prop(self, "nav_zoom_cursor")
        col.prop(self, "nav_invert_zoom")
        col.prop(self, "nav_auto_depth")
        col.prop(self, "nav_dblclick_all")
        layout.separator()
        layout.label(text="Mouse buttons")
        col = self._split(layout)                 # même colonne de libellés pour les trois réglages
        col.prop(self, "mouse_orbit")
        row = col.row(heading="Context menu button")
        row.menu(DESSIN_MT_mouse_menu.bl_idname, text=next(n for i, n, _d in MENU_BUTTON_ITEMS if i == self.mouse_menu))
        if self.mouse_menu == 'RIGHT_CLICK':
            col.prop(self, "mouse_menu_tol", text="Movement tolerance (px)")
        col.prop(self, "mouse_middle")
        if self.mouse_middle == 'DEFAULT' and self.nav_style == 'RHINO' and self.mouse_orbit == 'RIGHT':
            col.label(text="Rhino style: the middle button does nothing (orbit and pan use the right button)", icon='INFO')
        if self.mouse_middle == 'CUSTOM':
            col.prop(self, "mouse_middle_op")
        layout.label(text="By default secondary click (right click) displays the context menu.")
        layout.prop(self, "rclick_enter")         # hors de la colonne « property split » : case alignée à gauche
        if mouse_conflict():
            layout.label(text="Orbit and context menu use the same button: the context menu wins.", icon='ERROR')
        if self.mouse_middle != 'DEFAULT' and 'MIDDLE' in (self.mouse_orbit, self.mouse_menu):
            layout.label(text="The middle button is already used by the orbit / context menu setting above.", icon='ERROR')
        layout.separator()
        layout.label(text="Orthographic side views (Front, Top, Right...)")
        layout.prop(self, "view_pan")
        if self.mouse_orbit == 'DEFAULT':         # sinon le bouton d'orbite choisi plus haut (style Rhino...) s'applique partout
            row = layout.row()
            row.enabled = self.view_pan
            row.prop(self, "view_button")
        row = layout.row()
        row.enabled = self.view_pan
        row.prop(self, "view_persp")
        layout.label(text="Shift + the button keeps its usual action. Perspective views orbit as before.")

    def _draw_command_line(self, layout):
        layout.label(text="Type a command name or alias, then Enter or Space, like in AutoCAD and Rhino.", icon='INFO')
        layout.prop(self, "cmd_line")
        col = layout.column(align=True)
        col.enabled = self.cmd_line
        col.prop(self, "cmd_type")
        col.prop(self, "cmd_key")
        col.prop(self, "cmd_size")
        layout.prop(self, "mode_icons")           # (la barre de modes reste affichée sans la ligne de commande)
        layout.label(text="Examples: rec, c, pl, m, trim, zoom  ·  Tab completes  ·  Enter / Space on an empty line "
                          "repeats the last command.")
        layout.separator()
        layout.label(text="Your own aliases, like AliasEdit in AutoCAD and Rhino (command line: aliasedit). "
                          "They come before the built-in ones.", icon='INFO')
        draw_aliases(layout, self)

    def _draw_drawing(self, layout):
        col = self._split(layout)
        col.prop(self, "cursor_style")
        row = col.row()
        row.enabled = self.cursor_style == 'AUTOCAD'
        row.prop(self, "cursor_size")
        col.prop(self, "cursor_pick")
        col.prop(self, "cursor_color")
        layout.separator()
        col = layout.column(align=True)
        col.prop(self, "curve_points")
        col.prop(self, "light_preview")
        col.prop(self, "enter_last")
        col.prop(self, "esc_deselect")
        col.prop(self, "auto_idle")

    def _draw_gumball(self, layout):
        col = layout.column(align=True)
        col.prop(self, "copy_key")
        if self.copy_key == 'ALT' and _alt_emulates_mouse():
            col.label(text="Alt also emulates the middle button (Blender: Input > Emulate 3 Button Mouse): use Shift, "
                           "or change that setting", icon='ERROR')
        col.prop(self, "gumball_rot90")
        col.prop(self, "gumball_step")
        col.prop(self, "gumball_line")
        col.label(text="Size: Gumball tab of the sidebar.")

    def _draw_toolbar(self, layout):
        layout.prop(self, "show_toolbar_tools")
        layout.prop(self, "remap_grs")
        layout.separator()
        layout.label(text="Blender's main toolbar tools (checked = shown)")
        col = layout.column(align=True)
        for key in list(HIDE_NATIVE_PREFIXES) + list(HIDE_TOOL_GROUPS):
            col.prop(self, key)

    def _draw_performance(self, layout):
        col = layout.column(align=True)
        col.prop(self, "snap_budget")
        col.label(text="Very large scenes: heavy objects are read when the cursor passes over them. 0 = no limit.")
        col = layout.column(align=True)
        col.prop(self, "curve_quality")
        col.label(text="Sides given to circles, arcs and curves by Extrude, Planar Surface, Revolve, Trim...")
        layout.prop(self, "far_warning")

    def _draw_shortcuts(self, layout):
        top = layout.row(align=True)
        top.prop(self, "search", icon='VIEWZOOM', text="")
        top.operator(DESSIN_OT_shortcuts_clear.bl_idname, icon='X', text="Clear all")
        layout.label(text="Shortcuts: click a field, then press the key (Backspace over a field: clear). "
                          "They switch to the tool from the 3D viewport.")
        flt = self.search.strip().lower()
        for section, tools in shortcut_tools():
            rows = [(lab, tid) for lab, tid in tools if flt in lab.lower() or flt in section.lower()]
            if not rows:
                continue
            box = layout.box()
            head = box.split(factor=0.4)
            head.label(text=section)
            sub = head.row()
            for _km, title in SHORTCUT_MODES:
                sub.label(text=title)
            for lab, tid in rows:
                line = box.split(factor=0.4)
                line.label(text=lab)
                keys = line.row(align=True)
                for km_name, _title in SHORTCUT_MODES:
                    kmi = user_shortcut(km_name, tid)
                    if kmi is None:
                        keys.label(text="—")
                    else:
                        cell = keys.row(align=True)
                        cell.active = kmi.active
                        cell.prop(kmi, "type", text="", full_event=True)

    PANELS = (("presets", "Presets", False, "_draw_presets"),
              ("appearance", "Appearance: icons, language", False, "_draw_appearance"),
              ("navigation", "Navigation and mouse", False, "_draw_navigation"),
              ("command", "Command line and aliases", False, "_draw_command_line"),
              ("drawing", "Drawing: crosshair and behavior", True, "_draw_drawing"),
              ("gumball", "Gumball", True, "_draw_gumball"),
              ("toolbar", "Toolbar", True, "_draw_toolbar"),
              ("perf", "Performance and precision", True, "_draw_performance"),
              ("shortcuts", "Shortcuts", True, "_draw_shortcuts"))

    def draw(self, context):
        layout = self.layout
        top = layout.row()
        top.alignment = 'RIGHT'
        top.operator(DESSIN_OT_prefs_reset.bl_idname, icon='LOOP_BACK')
        for key, title, closed, fn in self.PANELS:
            body = self._panel(layout, key, title, closed)
            if body is not None:
                getattr(self, fn)(body)


def _late_imports():
    """Noms définis dans des modules chargés après celui-ci : ils ne servent qu'à l'exécution des outils."""
    global HIDE_NATIVE_PREFIXES, HIDE_TOOL_GROUPS, _update_toolbar_filter
    from .registration import HIDE_NATIVE_PREFIXES, HIDE_TOOL_GROUPS, _update_toolbar_filter
