import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
exec(open(_os.path.join(_HERE,'prec_lib.py')).read())
SEC="Maj+Q : Quick Type"
wm=bpy.context.window_manager
def items(kc):
    return [(km.name,it) for km in kc.keymaps for it in km.keymap_items if it.idname=="dessin.quick_type_toggle"]
mine=items(wm.keyconfigs.addon)
rec(SEC,"un raccourci Maj+Q existe dans « 3D View » (touche Q, Maj, rien d'autre)",
    len(mine)==1 and mine[0][0]=="3D View" and mine[0][1].type=='Q' and mine[0][1].shift and not (mine[0][1].alt or mine[0][1].ctrl or mine[0][1].oskey),mine and (mine[0][0],mine[0][1].type))
clash=[(km.name,it.idname) for km in wm.keyconfigs.default.keymaps for it in km.keymap_items
       if it.type=='Q' and it.active and it.shift and not (it.alt or it.ctrl or it.oskey)]
rec(SEC,"Blender n'utilise pas Maj+Q par défaut : aucun conflit",not clash,clash or "aucun")
import types
P=types.SimpleNamespace(cmd_type=False)       # le harnais n'enregistre pas le module comme add-on : préférences simulées
fake=types.SimpleNamespace(preferences=types.SimpleNamespace(addons={m.mode_click.__globals__['__package__']: types.SimpleNamespace(preferences=P)}), window_manager=wm)
def gesture():
    m.PREF_DEFAULTS["cmd_type"]=P.cmd_type       # pref() lit la valeur courante
    m.mode_click(fake,"cmd_type")
rec(SEC,"réglage Quick Type désactivé au départ",not P.cmd_type)
gesture()
rec(SEC,"le geste du raccourci active Quick Type",P.cmd_type)
old=m.PREF_DEFAULTS["cmd_type"]
m.PREF_DEFAULTS["cmd_type"]=True; m.unregister_cmd_keymap(); m.register_cmd_keymap()
n_letters=len([1 for km in wm.keyconfigs.addon.keymaps for it in km.keymap_items if it.idname=="dessin.command_line" and it.type=='Q' and not it.shift])
rec(SEC,"Quick Type actif : la lettre Q seule ouvre la ligne de commande, Maj+Q reste libre pour la bascule",n_letters>=1 and len(items(wm.keyconfigs.addon))==1,n_letters)
m.PREF_DEFAULTS["cmd_type"]=old; m.unregister_cmd_keymap(); m.register_cmd_keymap()
gesture()
rec(SEC,"le même geste le désactive",not P.cmd_type)
rec(SEC,"l'opérateur est enregistré (dessin.quick_type_toggle)",hasattr(bpy.ops.dessin,"quick_type_toggle"))
tt=bpy.types.DESSIN_OT_quick_type_toggle
rec(SEC,"description de l'opérateur citant Shift+Q","Shift+Q" in tt.bl_description,tt.bl_description)
summary()
