import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
exec(open(_os.path.join(_HERE,'prec_lib.py')).read())
# Préréglages des préférences : façon de travailler et apparence de Rhino, d'AutoCAD ou de Blender
import types
SEC="Préréglages"
P=types.SimpleNamespace(**dict(m.PREF_DEFAULTS))
ann=m.DESSIN_AP_prefs.__annotations__
bad=[]
for style,vals in m.WORKFLOW_PRESETS.items():
    for k,v in vals.items():
        if k not in ann: bad.append((style,k,"réglage inconnu")); continue
        items=ann[k].keywords.get("items")
        if items and not callable(items) and v not in [i[0] for i in items]: bad.append((style,k,v))
rec(SEC,"chaque préréglage ne touche que des réglages qui existent, avec des valeurs permises",not bad,bad)
rec(SEC,"réglages d'origine : c'est la façon de travailler de Blender",m.workflow_preset_of(P)=='BLENDER',m.workflow_preset_of(P))
ch=m.apply_workflow_preset(P,'RHINO')
rec(SEC,"Rhino : navigation Rhino, curseur Rhino, zoom vers le curseur ; Quick Type reste éteint (Espace ouvre la ligne de commande)",
    P.nav_style=='RHINO' and P.cursor_style=='RHINO' and P.nav_zoom_cursor and not P.cmd_type and P.cmd_line and P.rclick_enter and set(ch)=={"nav_style","cursor_style","nav_zoom_cursor","view_persp_mods"},ch)
m._update_nav_style(P,None)
rec(SEC,"... le style Rhino met l'orbite sur le bouton droit et le menu sur un clic droit bref",P.mouse_orbit=='RIGHT' and P.mouse_menu=='RIGHT_CLICK',(P.mouse_orbit,P.mouse_menu))
rec(SEC,"le préréglage en place est reconnu (Rhino), et l'appliquer de nouveau ne change rien",m.workflow_preset_of(P)=='RHINO' and m.apply_workflow_preset(P,'RHINO')==[])
ch=m.apply_workflow_preset(P,'AUTOCAD'); m._update_nav_style(P,None)
rec(SEC,"AutoCAD : navigation AutoCAD, réticule ; l'orbite quitte le bouton droit ; Quick Type reste éteint",P.nav_style=='AUTOCAD' and P.cursor_style=='AUTOCAD' and not P.cmd_type and m.workflow_preset_of(P)=='AUTOCAD' and P.mouse_orbit=='DEFAULT' and P.mouse_menu=='DEFAULT',(ch,P.mouse_orbit,P.mouse_menu))
P.cmd_type=True
rec(SEC,"un réglage modifié à la main (Quick Type allumé depuis la barre du bas) : le préréglage devient « custom »",m.workflow_preset_of(P) is None)
P.cmd_type=False
rec(SEC,"... éteint de nouveau : le préréglage AutoCAD est reconnu",m.workflow_preset_of(P)=='AUTOCAD')
P.cmd_type=True
rec(SEC,"appliquer le préréglage Rhino éteint Quick Type s'il était allumé","cmd_type" in m.apply_workflow_preset(P,'RHINO') and not P.cmd_type and m.workflow_preset_of(P)=='RHINO')
ch=m.apply_workflow_preset(P,'MAX'); m._update_nav_style(P,None)
rec(SEC,"3ds Max : navigation 3ds Max (milieu : panoramique, Alt + milieu : orbite), Maj + glisser copie, Entrée ne relance pas la commande",
    P.nav_style=='MAX' and P.copy_key=='SHIFT' and not P.enter_last and P.nav_zoom_cursor and m.workflow_preset_of(P)=='MAX' and P.mouse_orbit=='DEFAULT',(ch,P.mouse_orbit))
ch2=m.apply_workflow_preset(P,'RHINO')
rec(SEC,"... revenir à Rhino remet Alt + glisser pour copier",P.copy_key=='ALT' and "copy_key" in ch2 and m.workflow_preset_of(P)=='RHINO',ch2)
ch=m.apply_workflow_preset(P,'BLENDER')
rec(SEC,"Blender : retour exact aux réglages d'origine pour la navigation, la souris, le curseur et la saisie",all(getattr(P,k)==m.PREF_DEFAULTS[k] for k in m.WORKFLOW_PRESETS['BLENDER']) and m.workflow_preset_of(P)=='BLENDER',ch)
others=[k for k in m.PREF_DEFAULTS if k not in m.WORKFLOW_PRESETS['BLENDER'] and k not in ("mouse_orbit","mouse_menu") and getattr(P,k)!=m.PREF_DEFAULTS[k]]
rec(SEC,"les autres réglages (langue, icônes, performances...) ne sont jamais touchés",not others,others)
# opérateur
GP=m.DESSIN_OT_apply_preset.execute.__globals__
fake=types.SimpleNamespace(preferences=types.SimpleNamespace(addons={GP['__package__']:types.SimpleNamespace(preferences=P)},is_dirty=False))
o=make(m.DESSIN_OT_apply_preset); o.style='AUTOCAD'; r=type(o).execute(o,fake)
rec(SEC,"le bouton AutoCAD règle la façon de travailler, avec un compte rendu",'FINISHED' in r and m.workflow_preset_of(P)=='AUTOCAD' and fake.preferences.is_dirty and any("AutoCAD preset" in t for _l,t in o._reports),o._reports)
d=m.DESSIN_OT_apply_preset.description(None,types.SimpleNamespace(style='RHINO'))
rec(SEC,"chaque bouton explique ce qu'il règle (infobulle)","right button orbits" in d and all(m.PRESET_TIPS.get(s) for s,_n in m.PRESET_STYLES),d[:60])
rec(SEC,"... les infobulles Rhino, AutoCAD et 3ds Max disent que Quick Type reste éteint, et comment l'allumer",all("Quick Type stays off" in m.PRESET_TIPS[s] and "Shift+Q" in m.PRESET_TIPS[s] for s in ('RHINO','AUTOCAD','MAX')))
rec(SEC,"plus d'apparence (thèmes retirés) : les préréglages ne touchent pas aux couleurs de Blender",not hasattr(m,"LOOK_PRESETS") and not hasattr(m,"apply_look_preset"))
rec(SEC,"l'opérateur est enregistré",hasattr(bpy.ops.dessin,"apply_preset"))
m.apply_workflow_preset(P,'RHINO'); r1=P.view_persp_mods
m.apply_workflow_preset(P,'AUTOCAD'); r2=P.view_persp_mods
m.apply_workflow_preset(P,'BLENDER'); r3=P.view_persp_mods
rec(SEC,"orbite hors d'une vue de côté : Ctrl + Maj (Rhino), Alt (AutoCAD, Blender)",(r1,r2,r3)==('CTRL_SHIFT','ALT','ALT'),(r1,r2,r3))
summary()
