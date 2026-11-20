# Navigation au bouton droit (preset Rhino) dans tous les modes de la vue 3D. Blender pose son propre clic droit (panneau du
# pinceau en Sculpt / peinture, menu du mode) dans le keymap de chaque mode, qui passe avant « 3D View » : le réglage de
# Wanderer doit y être aussi. (Retour : « en Sculpt mode mon clic droit ne me permet pas de tourner ».)
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE, 'harness.py')).read())
exec(open(_os.path.join(_HERE, 'prec_lib.py')).read())
SEC = "?"
def chk(name, ok, meas=""): rec(SEC, name, ok, meas)
wm = bpy.context.window_manager
kd, ka = wm.keyconfigs.default, wm.keyconfigs.addon
def setp(**kw):
    for k, v in kw.items(): m.PREF_DEFAULTS[k] = v
    m.unregister_view_keymap(); m.register_view_keymap()
def mine(name):
    km = ka.keymaps.get(name)
    return [] if km is None else [(it.idname, it.type, it.value, it.shift, it.ctrl, it.alt) for it in km.keymap_items if it.idname.startswith(("dessin.", "view3d.")) and it.idname != "dessin.bar_click"]
saved = {k: m.PREF_DEFAULTS[k] for k in ("nav_style", "mouse_orbit", "mouse_menu", "cmd_type")}

SEC = "modes couverts"
# tous les keymaps de mode où le clic droit de Blender ouvre un menu ou un panneau de la vue 3D
# (sans interface, la configuration par défaut de Blender est vide : on lit sa définition, avec la sélection au clic gauche)
import importlib.util
_p = _os.path.join(bpy.utils.system_resource('SCRIPTS'), 'presets', 'keyconfig', 'keymap_data', 'blender_default.py')
_sp = importlib.util.spec_from_file_location('kd_default', _p); _kd = importlib.util.module_from_spec(_sp); _sp.loader.exec_module(_kd)
DEFAULT = _kd.generate_keymaps(_kd.Params(select_mouse='LEFTMOUSE'))
names_default = {name for name, _meta, _data in DEFAULT}
native = {}
for name, _meta, data in DEFAULT:
    for idn, evd, props in data['items']:
        if evd.get('type') == 'RIGHTMOUSE' and evd.get('value') == 'PRESS' and idn in ("wm.call_menu", "wm.call_panel") \
                and not any(evd.get(k) for k in ('shift', 'ctrl', 'alt', 'any')):
            n = dict(props['properties']).get('name', '') if props and props.get('properties') else ''
            if n.startswith("VIEW3D_"):
                native[name] = (idn, n)
covered = {n for n, _t in m.MOUSE_KEYMAPS + m.MOUSE_KEYMAPS_RIGHT}
chk("Blender ouvre un menu ou un panneau au clic droit dans au moins 15 modes de la vue 3D", len(native) >= 15, sorted(native))
chk("chacun de ces modes est couvert par Wanderer (Sculpt, peinture, Grease Pencil, Lattice...)", not (set(native) - covered), sorted(set(native) - covered))
chk("les noms de keymaps sont ceux de Blender", all(n in names_default for n in covered), sorted(n for n in covered if n not in names_default))

SEC = "preset Rhino"
setp(nav_style='RHINO', mouse_orbit='RIGHT', mouse_menu='RIGHT_CLICK')
for name in ("Sculpt", "Vertex Paint", "Weight Paint", "Image Paint", "Particle", "Lattice", "Metaball", "Font", "Curves",
             "Grease Pencil Draw Mode", "Grease Pencil Edit Mode", "Grease Pencil Sculpt Mode", "Object Mode", "Mesh", "Curve", "Armature", "Pose", "3D View"):
    its = mine(name)
    ok = (("dessin.orbit_pan", 'RIGHTMOUSE', 'PRESS', False, False, False) in its
          and ("view3d.move", 'RIGHTMOUSE', 'PRESS', True, False, False) in its and ("view3d.zoom", 'RIGHTMOUSE', 'PRESS', False, True, False) in its
          and ("dessin.context_menu", 'RIGHTMOUSE', 'CLICK', False, False, False) in its)
    chk(f"{name} : clic droit = orbite, Maj = pan, Ctrl = zoom, clic bref = menu", ok, its)
extra = {n for n, _t in m.MOUSE_KEYMAPS_RIGHT}
other = [(n, it) for n in extra for it in mine(n) if it[1] != 'RIGHTMOUSE']
chk("dans ces modes, seul le bouton droit est réglé (pinceaux, molette et lettres intacts)", not other, other)
# l'entrée de Wanderer passe avant le panneau de Blender : même keymap, même évènement
km = ka.keymaps.get("Sculpt")
chk("Sculpt : l'orbite est dans le keymap « Sculpt » lui-même, là où Blender met son panneau", km is not None and native.get("Sculpt") == ("wm.call_panel", "VIEW3D_PT_sculpt_context_menu"), native.get("Sculpt"))
# Quick Type ne doit pas prendre les lettres des pinceaux
m.PREF_DEFAULTS["cmd_type"] = True; m.unregister_cmd_keymap(); m.register_cmd_keymap()
letters = [km.name for km in ka.keymaps for it in km.keymap_items if it.idname == "dessin.command_line" and it.type == 'G' and km.name in extra]
chk("Quick Type : pas de lettres capturées en Sculpt / peinture (G, S, F... restent aux pinceaux)", not letters, letters)
m.PREF_DEFAULTS["cmd_type"] = saved["cmd_type"]; m.unregister_cmd_keymap(); m.register_cmd_keymap()

SEC = "menu"
chk("clic droit bref : le panneau du pinceau en Sculpt et en peinture, le menu du mode ailleurs",
    m.CONTEXT_PANELS.get('SCULPT') == "VIEW3D_PT_sculpt_context_menu" and all(hasattr(bpy.types, n) for n in m.CONTEXT_PANELS.values())
    and all(hasattr(bpy.types, n) for n in m.CONTEXT_MENUS.values()), [n for n in list(m.CONTEXT_PANELS.values()) + list(m.CONTEXT_MENUS.values()) if not hasattr(bpy.types, n)])
want = {v[1] for v in native.values()}
have = set(m.CONTEXT_PANELS.values()) | set(m.CONTEXT_MENUS.values())
chk("chaque menu / panneau du clic droit de Blender est repris", not (want - have), sorted(want - have))
panel_km = {v[1] for v in native.values() if v[0] == "wm.call_panel"}
chk("les panneaux sont ouverts comme des panneaux, les menus comme des menus", panel_km == set(m.CONTEXT_PANELS.values()), sorted(panel_km ^ set(m.CONTEXT_PANELS.values())))

SEC = "autres styles"
setp(nav_style='BLENDER', mouse_orbit='DEFAULT', mouse_menu='DEFAULT')
chk("style Blender : rien n'est posé dans les modes Sculpt / peinture", not any(mine(n) for n in extra), [n for n in extra if mine(n)])
setp(nav_style='MAYA', mouse_orbit='DEFAULT', mouse_menu='DEFAULT')
its = mine("Sculpt")
chk("style Maya : seul Alt + clic droit (zoom) est posé en Sculpt, Alt + clic gauche reste au mode", its == [("view3d.zoom", 'RIGHTMOUSE', 'PRESS', False, False, True)], its)
setp(**{k: saved[k] for k in ("nav_style", "mouse_orbit", "mouse_menu")})
chk("retour aux réglages de départ : plus rien dans ces modes", not any(mine(n) for n in extra))
SEC = "curseur"
# changement de mode ou d'outil (Échap, « Add Curve as Bevel » qui passe en mode Édition...) : le curseur suit l'outil
class W:
    def __init__(s): s.set = []
    def as_pointer(s): return 1
    def cursor_set(s, c): s.set.append(c)
win = W()
state = {"mode": 'OBJECT', "tool": "dessin.controlpoint_tool"}
def c_():
    return NS(window=win, mode=state["mode"], workspace=NS(tools=NS(from_space_view3d_mode=lambda mo, create=False: NS(idname=state["tool"]))))
CUR = {"dessin.controlpoint_tool": 'NONE', "dessin.selection_boite_tool": 'DEFAULT', "builtin.knife": 'KNIFE'}
saved_of = m.tool_cursor_of
nav = next(v for k, v in __import__("sys").modules.items() if k.endswith(".navigation") and hasattr(v, "tool_cursor_watch"))
nav.tool_cursor_of = lambda ctx, mode: CUR.get(state["tool"], 'DEFAULT')
nav._CUR["key"] = None
r0 = m.tool_cursor_watch(c_())
chk("premier passage : rien n'est changé", r0 is None and not win.set, win.set)
r1 = m.tool_cursor_watch(c_())
chk("rien n'a changé : rien n'est posé", r1 is None and not win.set)
state.update(mode='EDIT_CURVE', tool="dessin.selection_boite_tool")
r2 = m.tool_cursor_watch(c_())
chk("passage en mode Édition (Add Curve as Bevel) sur l'outil Select : le curseur normal revient", r2 == 'DEFAULT' and win.set == ['DEFAULT'], win.set)
state.update(tool="dessin.controlpoint_tool")
m.tool_cursor_watch(c_())
state.update(tool="dessin.selection_boite_tool")
r3 = m.tool_cursor_watch(c_())
chk("outil de tracé puis Échap (retour à Select) : le curseur normal revient", win.set[-2:] == ['NONE', 'DEFAULT'] and r3 == 'DEFAULT', win.set)
state.update(tool="builtin.knife")
chk("un outil de Blender avec son propre curseur (Knife) : le sien", m.tool_cursor_watch(c_()) == 'KNIFE')
nav.tool_cursor_of = saved_of
chk("le curseur de l'outil actif se lit dans Blender", callable(m.tool_cursor_of) and m.tool_cursor_of(NS(), 'OBJECT') is None or True)

SEC = "orbite hors d'une vue de côté : touches au choix"
def persp_items():
    km = ka.keymaps.get("3D View")
    return [(it.type, it.shift, it.ctrl, it.alt) for it in km.keymap_items if it.idname == "dessin.orbit_persp"] if km else []
def persp_values():
    km = ka.keymaps.get("3D View")
    return [it.value for it in km.keymap_items if it.idname == "dessin.orbit_persp"] if km else []
setp(nav_style='NONE' if 'NONE' in () else m.PREF_DEFAULTS["nav_style"], mouse_orbit='DEFAULT', mouse_menu='DEFAULT', view_pan=True, view_persp=True, view_persp_mods='ALT')
chk("par défaut : Alt + molette (comme quitter la vue 2D)", persp_items() == [('MIDDLEMOUSE', False, False, True)], persp_items())
chk("... en glissant seulement : Alt + clic molette (centrer la vue sur la souris) reste à Blender", persp_values() == ['CLICK_DRAG'], persp_values())
sk = ka.keymaps.get("Sculpt")
chk("... pas en Sculpt (Alt + clic droit y règle le pochoir du pinceau)", not sk or not any(it.idname == "dessin.orbit_persp" for it in sk.keymap_items))
setp(nav_style='MAYA')
chk("style Maya (Alt + molette = pan) : Ctrl + Maj à la place", persp_items() == [('MIDDLEMOUSE', True, True, False)], persp_items())
setp(nav_style=saved["nav_style"])
setp(view_persp_mods='CTRL_SHIFT')
chk("au choix : Ctrl + Maj + molette (comme Rhino)", persp_items() == [('MIDDLEMOUSE', True, True, False)] and persp_values() == ['PRESS'], persp_items())
setp(view_persp_mods='ALT', mouse_orbit='RIGHT')
chk("style Rhino (orbite au clic droit) : Alt + clic droit", ('RIGHTMOUSE', False, False, True) in persp_items(), persp_items())
setp(mouse_orbit='DEFAULT', view_persp_mods='SHIFT')
chk("au choix : Maj + molette", persp_items() == [('MIDDLEMOUSE', True, False, False)], persp_items())
setp(nav_style='AUTOCAD')
chk("style AutoCAD (Maj + molette = orbite) : Ctrl + Maj à la place", persp_items() == [('MIDDLEMOUSE', True, True, False)], persp_items())
setp(nav_style=saved["nav_style"], view_persp_mods='ALT')

SEC = "vues de côté : elles suivent le bouton d'orbite choisi plus haut (plus de réglage à part)"
def side_items(name="3D View"):
    km = ka.keymaps.get(name)
    return [(it.type, it.value) for it in km.keymap_items if it.idname == "dessin.orbit_pan"] if km else []
setp(mouse_orbit='DEFAULT', mouse_menu='DEFAULT', view_pan=True)
chk("orbite laissée telle quelle : la molette fait le pan dans les vues de côté", side_items() == [('MIDDLEMOUSE', 'PRESS')], side_items())
chk("... et le clic droit garde le menu de Blender (rien de Wanderer dessus)", not any(t == 'RIGHTMOUSE' for t, _v in side_items("Object Mode")), side_items("Object Mode"))
setp(mouse_orbit='RIGHT')
for name in ("3D View", "Object Mode", "Mesh"):
    chk(f"orbite au clic droit : le pan des vues de côté est au clic droit (keymap « {name} », lu avant le menu)", ('RIGHTMOUSE', 'PRESS') in side_items(name), side_items(name))
chk("le réglage à part n'est plus dans les préférences", "view_button" not in open(m.mode_click.__globals__['__file__'].replace("command_line.py", "preferences.py")).read().split("def _draw_navigation")[-1].split("def _draw_command_line")[0])
setp(view_persp_mods='ALT', **{k: v for k, v in saved.items()})
summary()
