import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
import bpy,sys,types,numpy as np,importlib.util
exec(open(_os.path.join(_HERE,'addon_loader.py')).read())
m.register()
print("outils:",[t for t in (m.DESSIN_TT_selection_rect.bl_idname,m.DESSIN_TT_selection_cercle.bl_idname)])
got={}
def fake(context,area,region,inside_fn,seg_fn,crossing,ev): got.update(i=inside_fn,s=seg_fn,c=crossing,ev=ev)
m.select_objects_shape=fake
m.px_scale=lambda:1.0
S=types.SimpleNamespace(cursor=(100.0,100.0),first=True,area=None,region=None)
ctx=types.SimpleNamespace(mode='OBJECT')
ev=types.SimpleNamespace(shift=False,ctrl=False)
m.CIRCLE_SEL["radius"]=40.0
m.DESSIN_OT_selection_cercle.paint(S,ctx,ev)
x=np.array([100,139,141,100.]);y=np.array([100,100,100,141.])
print("points dans le cercle (r=40):",got["i"](x,y).tolist(),"attendu [T,T,F,F]")
# segment qui traverse le disque sans y avoir d'extrémité
print("segment traversant:",got["s"](np.array([50.]),np.array([70.]),np.array([150.]),np.array([70.])).tolist(),"attendu [True] (distance 30)")
print("segment éloigné:",got["s"](np.array([50.]),np.array([20.]),np.array([150.]),np.array([20.])).tolist(),"attendu [False]")
print("premier passage ev:",got["ev"], "crossing",got["c"])
S.first=False
m.DESSIN_OT_selection_cercle.paint(S,ctx,types.SimpleNamespace(shift=False,ctrl=False));print("passages suivants:",got["ev"])
m.DESSIN_OT_selection_cercle.paint(S,ctx,types.SimpleNamespace(shift=False,ctrl=True));print("avec Ctrl:",got["ev"])
from bl_ui.space_toolsystem_common import ToolDef
for mode in ('OBJECT','EDIT_MESH','EDIT_CURVE'):
    tl=m._tool_list(mode)
    for t in tl:
        if isinstance(t,tuple) and any(isinstance(x,ToolDef) and x.idname.startswith("dessin.selection") for x in t):
            print(mode,[x.idname for x in t if x is not None]); break
import os
print(m.DESSIN_TT_selection_rect.bl_icon, m.DESSIN_TT_selection_cercle.bl_icon)
for k in ("sel_box","sel_circle"):
    f=m.DESSIN_TT_selection_rect.bl_icon if k=="sel_box" else m.DESSIN_TT_selection_cercle.bl_icon
    print(k, os.path.exists(f+".dat") if not f.startswith("ops.") else "FALLBACK")
