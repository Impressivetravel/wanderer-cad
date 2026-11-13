"""Wanderer CAD : Préférences de l'add-on."""

import bpy
import os

from .core import PREF_DEFAULTS, pref_applied_language
from .snapping import _perf_caches_clear
from .drawing import _HOVER
from .icons import ICON_PALETTES
from .navigation import (
    DESSIN_OT_shortcuts_clear, NAV_STYLES, SHORTCUT_MODES, _update_cursor, _update_grs_keymap, _update_hide_native,
    _update_nav_inputs, _update_nav_style, _update_view_keymap, mouse_conflict, shortcut_tools, user_shortcut,
)
from .views import CMD_KEY_ITEMS
from .command_line import (
    DESSIN_MT_mouse_menu, MENU_BUTTON_ITEMS, _reload_addon_later, _update_cmd_line, _update_icon_palette,
    _update_mouse_orbit,
)


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


class DESSIN_OT_install_theme(bpy.types.Operator):
    bl_idname = "dessin.install_theme"
    bl_label = "Install theme"
    bl_description = "Installs and applies the theme (dark blue-gray « Blueprint », light « Vellum » or black and red « Ghost », which also switches the toolbar icons to Target). It changes Blender's colors and rounds the toolbar; pick another theme in Preferences > Themes to go back"
    bl_options = {'REGISTER'}

    which: bpy.props.EnumProperty(items=(('BLUEPRINT', "Wanderer Blueprint", "Dark theme"), ('VELLUM', "Wanderer Vellum", "Light theme"),
                                           ('GHOST', "Wanderer Ghost", "Black theme, signal red")),
                                  default='BLUEPRINT', options={'SKIP_SAVE'})

    def execute(self, context):
        name = {'BLUEPRINT': "Wanderer_Blueprint", 'VELLUM': "Wanderer_Vellum", 'GHOST': "Wanderer_Ghost"}[self.which]
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "themes", name + ".xml")
        if not os.path.isfile(path):
            self.report({'ERROR'}, "Theme file not found: " + path)
            return {'CANCELLED'}
        try:
            res = bpy.ops.preferences.theme_install(filepath=path, overwrite=True)
        except RuntimeError as e:
            self.report({'ERROR'}, "Could not install the theme: " + str(e))
            return {'CANCELLED'}
        if 'FINISHED' not in res:
            return {'CANCELLED'}
        msg = name.replace("_", " ") + " installed and applied"
        if self.which == 'GHOST':      # le thème Ghost s'accompagne des icônes Target (le changement recharge l'add-on)
            try:
                prefs = context.preferences.addons[__package__].preferences
                if prefs.icon_palette != 'TARGET':
                    prefs.icon_palette = 'TARGET'
                    msg += ": icons switched to Target"
            except (KeyError, AttributeError):
                pass
        self.report({'INFO'}, msg)
        return {'FINISHED'}


def _update_perf(self=None, context=None):
    """Budget d'accrochage ou qualité des courbes modifiés : les données gardées en mémoire sont recalculées."""
    _perf_caches_clear()
    _HOVER["version"] += 1
    _HOVER["data"] = None


class DESSIN_AP_prefs(bpy.types.AddonPreferences):
    bl_idname = __package__

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
        name="Language", default='EN',
        items=(('EN', "English", "Tool names, commands and prompts in English"),
               ('FR', "Français", "Tool names, commands and prompts in French (the English names stay usable in the command line)")),
        description="Language of the tools, the command line and its prompts. Restart Blender to apply")
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
        description="In Front / Top / Right... views the orbit button pans instead of orbiting (perspective views are unchanged)")
    view_persp: bpy.props.BoolProperty(
        name="Ctrl + Shift + orbit button: switch to perspective", default=True, update=_update_view_keymap,
        description="In orthographic side views, holding Ctrl + Shift with the orbit button switches the view to perspective and orbits")
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
        name="Zoom to cursor", default=False, update=_update_nav_inputs,
        description="The wheel zooms towards the mouse pointer instead of the center of the view")
    nav_invert_zoom: bpy.props.BoolProperty(
        name="Invert zoom direction", default=False, update=_update_nav_inputs,
        description="Reverses the wheel and the drag zoom direction")
    nav_auto_depth: bpy.props.BoolProperty(
        name="Orbit around the point under the cursor", default=False, update=_update_nav_inputs,
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
    oda_path: bpy.props.StringProperty(
        name="ODA File Converter", default="", subtype='FILE_PATH',
        description="DWG import and export go through the free ODA File Converter (opendesign.com). Leave empty when it is "
                    "installed in its usual place; otherwise choose the program here (on a Mac: ODAFileConverter.app)")
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

    def draw(self, context):
        layout = self.layout
        top0 = layout.row()
        top0.alignment = 'RIGHT'
        top0.operator(DESSIN_OT_prefs_reset.bl_idname, icon='LOOP_BACK')
        abox = layout.box()
        abox.label(text="Appearance")
        abox.prop(self, "language")
        if self.language != pref_applied_language():
            abox.label(text="Restart Blender to apply the language", icon='INFO')
        abox.prop(self, "icon_palette")
        abox.prop(self, "rich_tooltips")
        trow = abox.row(align=True)
        trow.label(text="Theme")
        trow.operator(DESSIN_OT_install_theme.bl_idname, text="Wanderer Blueprint").which = 'BLUEPRINT'
        trow.operator(DESSIN_OT_install_theme.bl_idname, text="Wanderer Vellum").which = 'VELLUM'
        trow.operator(DESSIN_OT_install_theme.bl_idname, text="Wanderer Ghost").which = 'GHOST'
        gbox = layout.box()
        gbox.label(text="Gumball")
        gcol = gbox.column(align=True)
        gcol.prop(self, "gumball_rot90")
        row = gcol.row()
        row.enabled = True
        row.prop(self, "gumball_step")
        gcol.prop(self, "gumball_line")
        gcol.label(text="Size: Gumball tab of the sidebar.")
        bbox = layout.box()
        bbox.label(text="Behavior")
        col = bbox.column(align=True)
        col.prop(self, "esc_deselect")
        col.prop(self, "enter_last")
        col.prop(self, "light_preview")
        col.prop(self, "auto_idle")
        col.prop(self, "show_toolbar_tools")
        col.prop(self, "remap_grs")
        bbox.label(text="Blender's main toolbar tools (checked = shown)")
        col = bbox.column(align=True)
        for key in list(HIDE_NATIVE_PREFIXES) + list(HIDE_TOOL_GROUPS):
            col.prop(self, key)
        pbox = layout.box()
        pbox.label(text="Performance and precision")
        col = pbox.column(align=True)
        col.prop(self, "snap_budget")
        col.label(text="Very large scenes: heavy objects are read when the cursor passes over them. 0 = no limit.")
        col = pbox.column(align=True)
        col.prop(self, "curve_quality")
        col.label(text="Sides given to circles, arcs and curves by Extrude, Planar Surface, Revolve, Trim...")
        pbox.prop(self, "far_warning")
        cbox = layout.box()
        cbox.label(text="Command line")
        cbox.label(text="Type a command name or alias, then Enter or Space, like in AutoCAD and Rhino.", icon='INFO')
        cbox.prop(self, "cmd_line")
        row = cbox.row()
        row.enabled = self.cmd_line
        row.prop(self, "cmd_type")
        row = cbox.row()
        row.enabled = self.cmd_line
        row.prop(self, "cmd_size")
        cbox.prop(self, "mode_icons")      # (la barre de modes reste affichée sans la ligne de commande : réglage toujours actif)
        row = cbox.row()
        row.enabled = self.cmd_line
        row.prop(self, "cmd_key")
        dbox = layout.box()
        dbox.label(text="DXF / DWG")
        dbox.prop(self, "oda_path")
        try:
            from .import_dxf import cad_converter
            found = cad_converter()
        except Exception:
            found = None
        if found is None:
            dbox.label(text="No DWG converter found: DXF works, DWG needs the free ODA File Converter", icon='INFO')
        else:
            dbox.label(text=("ODA File Converter found" if found[0] == 'oda' else "LibreDWG tools found") + ": DWG import and export are available",
                       icon='CHECKMARK')
        cbox.label(text="Examples: rec, c, pl, m, trim, zoom  ·  Tab completes  ·  Enter / Space on an empty line repeats the last command.")
        vbox = layout.box()
        vbox.label(text="View")
        col0 = vbox.column()
        col0.use_property_split = True
        col0.use_property_decorate = False
        col0.prop(self, "nav_style")
        col0.prop(self, "nav_zoom_cursor")
        col0.prop(self, "nav_invert_zoom")
        col0.prop(self, "nav_auto_depth")
        col0.prop(self, "nav_dblclick_all")
        vbox.separator()
        vbox.label(text="Mouse buttons")
        col = vbox.column()
        col.use_property_split = True                 # même colonne de libellés pour les trois réglages
        col.use_property_decorate = False
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
        vbox.label(text="By default secondary click (right click) displays the context menu.")
        vbox.prop(self, "rclick_enter")      # hors de la colonne « property split » : case alignée à gauche
        if mouse_conflict():
            vbox.label(text="Orbit and context menu use the same button: the context menu wins.", icon='ERROR')
        if self.mouse_middle != 'DEFAULT' and 'MIDDLE' in (self.mouse_orbit, self.mouse_menu):
            vbox.label(text="The middle button is already used by the orbit / context menu setting above.", icon='ERROR')
        vbox.separator()
        vbox.prop(self, "view_pan")
        if self.mouse_orbit == 'DEFAULT':       # sinon le bouton d'orbite choisi plus haut (style Rhino...) s'applique partout
            row = vbox.row()
            row.enabled = self.view_pan
            row.prop(self, "view_button")
        row2 = vbox.row()
        row2.enabled = self.view_pan
        row2.prop(self, "view_persp")
        vbox.label(text="Shift + the button keeps its usual action. Perspective views orbit as before.")
        layout.prop(self, "curve_points")
        kbox = layout.box()
        kbox.label(text="Crosshair (drawing tools)")
        kcol = kbox.column()
        kcol.use_property_split = True
        kcol.use_property_decorate = False
        kcol.prop(self, "cursor_style")
        row = kcol.row()
        row.enabled = self.cursor_style == 'AUTOCAD'
        row.prop(self, "cursor_size")
        kcol.prop(self, "cursor_pick")
        kcol.prop(self, "cursor_color")
        header, body = layout.panel("dessin_shortcuts_panel", default_closed=True)
        header.label(text="Shortcuts")
        if body is None:
            return
        layout = body
        top = layout.row(align=True)
        top.prop(self, "search", icon='VIEWZOOM', text="")
        top.operator(DESSIN_OT_shortcuts_clear.bl_idname, icon='X', text="Clear all")
        col = layout.column()
        col.label(text="Shortcuts: click a field, then press the key (Backspace over a field: clear). "
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


def _late_imports():
    """Noms définis dans des modules chargés après celui-ci : ils ne servent qu'à l'exécution des outils."""
    global HIDE_NATIVE_PREFIXES, HIDE_TOOL_GROUPS, _update_toolbar_filter
    from .registration import HIDE_NATIVE_PREFIXES, HIDE_TOOL_GROUPS, _update_toolbar_filter
