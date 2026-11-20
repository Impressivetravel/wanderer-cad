import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
# Walk : un raccourci vers la marche de Blender (view3d.walk), réglée dans Préférences > Navigation > Walk.
res=[]
def chk(name,ok,info=""):
    res.append(bool(ok)); print(("OK  " if ok else "BAD ")+name, info)
from bl_ui.space_toolsystem_common import ToolDef
def ids(t): return [x.idname for x in t] if isinstance(t,tuple) and not isinstance(t,ToolDef) else (t.idname if isinstance(t,ToolDef) else t)
for mode in ('OBJECT','EDIT_MESH'):
    L=[ids(t) for t in m._tool_list(mode)]
    k=next(i for i,t in enumerate(L) if isinstance(t,list) and "dessin.selection_boite_tool" in t)
    chk(f"{mode} : Walk juste à côté du menu de Select (avant le Curseur)", L[k+1]=="dessin.walk_tool" and L[k+2]=="builtin.cursor", L[k:k+3])
    g=next((t for t in L if isinstance(t,list) and "dessin.align_tool" in t), None)
    chk(f"{mode} : Orient et Orient 3 Points dans le menu déroulant d'Align", g==["dessin.align_tool","dessin.orient_tool","dessin.orient3pt_tool"], g)
    chk(f"{mode} : Walk n'apparaît qu'une fois", sum(1 for t in L for x in (t if isinstance(t,list) else [t]) if x=="dessin.walk_tool")==1)
W_=m.RHINO_TOOLS["nav"][0]
fam=dict(m.tool_families())
chk("panneau des outils : Walk dans la famille Select, Orient après Align", "dessin.walk_tool" in [c.bl_idname for c in fam["Select"]]
    and [c.bl_idname for c in fam["Transform"]].index("dessin.orient_tool")==[c.bl_idname for c in fam["Transform"]].index("dessin.align_tool")+1, [c.bl_label for c in fam["Select"]])
km=[k for k in W_.bl_keymap if k[1].get("type")=='LEFTMOUSE']
chk("un clic dans la vue lance la marche de Blender elle-même (view3d.walk), sans fonction propre à l'add-on", len(km)==1 and km[0][0]=="view3d.walk" and km[0][2] is None, W_.bl_keymap)
chk("... pas d'opérateur Walk de l'add-on", not hasattr(bpy.types,"DESSIN_OT_walk") and not hasattr(m,"DESSIN_OT_walk"))
chk("... l'opérateur existe dans Blender", hasattr(bpy.ops.view3d,"walk") and bpy.ops.view3d.walk.get_rna_type() is not None)
chk("... le survol ne lance rien (pas de marche au simple passage de la souris)", not any(k[1].get("type")=='MOUSEMOVE' for k in W_.bl_keymap), W_.bl_keymap)
chk("icône Walk", getattr(W_,"dessin_icon",None)=="walk" and "walk" in m.ICON_SVG)
chk("l'aide renvoie aux préférences de Blender", "Preferences > Navigation > Walk" in W_.bl_description, W_.bl_description)
got=[(m.cmd_suggest(t) or [{"label":None}])[0]["label"] for t in ("walk","walkabout")]
chk("ligne de commande : walk, walkabout -> l'outil Walk", got==["Walk","Walk"], got)
print("RESULTAT",sum(res),"/",len(res))
