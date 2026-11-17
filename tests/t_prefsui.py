import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
exec(open(_os.path.join(_HERE,'prec_lib.py')).read())
# Préférences : une section repliable par sujet, chaque réglage dessiné une fois et une seule
import types
SEC="Préférences : organisation"
CALLS=[]
class Lay:
    def __init__(s,panel=None): s.panel_key=panel
    def _rec(s,kind,val): CALLS.append((s.panel_key,kind,val))
    def row(s,**k): return Lay(s.panel_key)
    def column(s,**k): return Lay(s.panel_key)
    def box(s): return Lay(s.panel_key)
    def split(s,**k): return Lay(s.panel_key)
    def separator(s,**k): pass
    def label(s,text="",icon='NONE',**k): s._rec("label",text)
    def menu(s,idname,text="",**k): s._rec("menu",idname)
    def prop(s,data,name,**k): s._rec("prop",name if data is P else "other:"+name)
    def operator(s,idname,**k): s._rec("op",idname); return types.SimpleNamespace()
    def panel(s,key,default_closed=False):
        CALLS.append((key,"panel",default_closed)); return Lay(key),Lay(key)
    def __setattr__(s,k,v): object.__setattr__(s,k,v)
P=make(m.DESSIN_AP_prefs)
for k,v in m.PREF_DEFAULTS.items():
    try: setattr(P,k,v)
    except Exception: pass
P.search=""
P.aliases=[]
P.layout=Lay()
m.DESSIN_AP_prefs.draw(P,bpy.context)
panels=[(c[0],c[2]) for c in CALLS if c[1]=="panel"]
rec(SEC,"dix sections, toutes repliables, dans l'ordre prévu",
    [p for p,_c in panels]==["dessin_prefs_"+k for k,_t,_c,_f in m.DESSIN_AP_prefs.PANELS],[p for p,_c in panels])
open_now=[p for p,c in panels if not c]
rec(SEC,"ouvertes au départ : préréglages, apparence, navigation, ligne de commande",
    open_now==["dessin_prefs_presets","dessin_prefs_appearance","dessin_prefs_navigation","dessin_prefs_command"],open_now)
props=[c[2] for c in CALLS if c[1]=="prop"]
# seconde passe : les réglages qui n'apparaissent que dans certains cas (clic droit = Entrée, bouton du milieu libre)
CALLS2=CALLS[:]; CALLS.clear()
P.mouse_menu='RIGHT_CLICK'; P.mouse_middle='CUSTOM'; P.cursor_style='AUTOCAD'
m.DESSIN_AP_prefs.draw(P,bpy.context)
cond=[c[2] for c in CALLS if c[1]=="prop"]
where2={c[2]:c[0] for c in CALLS if c[1]=="prop"}
CALLS[:]=CALLS2
dupes=sorted({p for p in props if props.count(p)>1 and not p.startswith("other:")})
rec(SEC,"aucun réglage n'est dessiné deux fois",not dupes,dupes)
# tous les réglages des préférences sont accessibles
ann=[k for k,v in m.DESSIN_AP_prefs.__annotations__.items() if hasattr(v,"keywords")]
hidden={"search","smart_tracks","mouse_menu","aliases"}       # champ de recherche, barre du bas, menu, liste d'alias
missing=[k for k in ann if k not in props and k not in cond and k not in hidden]
rec(SEC,"chaque réglage des préférences est dessiné quelque part",not missing,missing)
rec(SEC,"les réglages liés au clic droit et au bouton du milieu apparaissent quand ils servent",
    where2.get("mouse_menu_tol")=="dessin_prefs_navigation" and where2.get("mouse_middle_op")=="dessin_prefs_navigation",
    (where2.get("mouse_menu_tol"),where2.get("mouse_middle_op")))
rec(SEC,"le bouton de remise à zéro est là, et plus aucun bouton de thème (thèmes retirés de l'add-on)",
    any(c[2]=="dessin.prefs_reset" for c in CALLS if c[1]=="op") and not [c for c in CALLS if c[1]=="op" and "theme" in c[2]])
# chaque réglage est dans la section qui lui correspond
where={c[2]:c[0] for c in CALLS if c[1]=="prop"}
expect={"nav_style":"navigation","mouse_orbit":"navigation","view_pan":"navigation","rclick_enter":"navigation",
        "cmd_line":"command","cmd_key":"command","mode_icons":"command",
        "cursor_style":"drawing","curve_points":"drawing","light_preview":"drawing","esc_deselect":"drawing",
        "icon_palette":"appearance","language":"appearance","rich_tooltips":"appearance",
        "gumball_step":"gumball","show_toolbar_tools":"toolbar","show_tool_cursor":"toolbar",
        "snap_budget":"perf","curve_quality":"perf","far_warning":"perf"}
bad=[(k,where.get(k)) for k,sec in expect.items() if where.get(k)!="dessin_prefs_"+sec]
rec(SEC,"chaque réglage est dans la section attendue",not bad,bad)
rec(SEC,"la section Appearance dit où trouver les thèmes (site des extensions Blender)",
    "themes are no longer included" in str(CALLS) and "extensions.blender.org" in str(CALLS))
rec(SEC,"plus de thèmes dans l'add-on : ni opérateur, ni dossier","install_theme" not in dir(bpy.ops.dessin) and not hasattr(m,"THEME_NAMES")
    and not _os.path.isdir(_os.path.join(_HERE,'..','wanderer_cad','themes')))
summary()
