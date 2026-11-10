import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
import numpy as np
ok=True
def chk(name,cond,extra=""):
    global ok
    ok&=bool(cond); print(("OK " if cond else "BAD"),name,extra)
# pas des coordonnées : comparé au pas réel d'un sommet de maillage Blender
me=bpy.data.meshes.new("T"); me.vertices.add(1)
for x in (1.0,10.0,100.0,999.0,1500.0,12345.0,250000.0):
    me.vertices[0].co=(x,0,0); a=me.vertices[0].co.x
    me.vertices[0].co=(x+m.far_origin_step((x,0,0))*0.51,0,0); b=me.vertices[0].co.x
    me.vertices[0].co=(x+m.far_origin_step((x,0,0))*0.2,0,0); c=me.vertices[0].co.x
    st_=m.far_origin_step((x,0,0))
    chk("pas à %g : %.6g (Blender stocke bien ce pas)"%(x,st_),b!=a and c==a and abs((b-a)-st_)<st_*1e-6,(a,b,c))
chk("pas en mètres avec une scène en millimètres",abs(m.far_origin_step((100000.0,0,0),0.001)-0.0078125e-3)<1e-12,m.far_origin_step((100000.0,0,0),0.001))
# message : une fois, seulement loin de l'origine
class Op:
    def __init__(s): s.r=[]
    def report(s,lv,msg): s.r.append((list(lv)[0],msg))
op=Op(); m._FAR["told"]=False
chk("près de l'origine : aucun message",not m.far_origin_check(op,ctx,Vector((120,45,3))) and not op.r)
chk("à 400 m : aucun message",not m.far_origin_check(op,ctx,Vector((400,45,3))) and not op.r)
chk("à 1,5 km : message",m.far_origin_check(op,ctx,Vector((1500,45,3))) and len(op.r)==1 and op.r[0][0]=='WARNING',op.r)
print("   ",op.r[0][1] if op.r else "")
chk("une seule fois par fichier",not m.far_origin_check(op,ctx,Vector((2500,45,3))) and len(op.r)==1)
m._on_load_clear(); chk("nouveau fichier : le message peut revenir",m._FAR["told"] is False)
m.PREF_DEFAULTS["far_warning"]=False
chk("réglage coupé : aucun message",not m.far_origin_check(op,ctx,Vector((2500,45,3))) and len(op.r)==1)
m.PREF_DEFAULTS["far_warning"]=True
# scène en millimètres : 100 m (100 000 unités) -> pas 0,008 mm, pas de message ; 2 km -> message
bpy.context.scene.unit_settings.scale_length=0.001; m._FAR["told"]=False; op=Op()
chk("mm, 100 m : aucun message",not m.far_origin_check(op,ctx,Vector((100000,0,0))))
chk("mm, 2 km : message",m.far_origin_check(op,ctx,Vector((2000000,0,0))),op.r)
print("   ",op.r[0][1] if op.r else "")
bpy.context.scene.unit_settings.scale_length=1.0
# dans un vrai outil : ligne tracée loin de l'origine
m._FAR["told"]=False
rv3d.view_location=Vector((0,0,0))
o=make(m.DESSIN_OT_polyligne)
type(o).invoke(o,ctx,ev('NONE','NOTHING',*scr(0,0)))
o.cur=Vector((3000,10,0))
import types
orig=type(o).update_cursor
type(o).update_cursor=lambda self,c,e: None
for e in (ev('LEFTMOUSE','PRESS',*scr(1,1)),ev('LEFTMOUSE','RELEASE',*scr(1,1))):
    type(o).modal(o,ctx,e)
type(o).update_cursor=orig
chk("outil : message au premier point posé loin",any('Far from the origin' in r[1] for r in o._reports),o._reports)
try: type(o).cleanup(o,ctx)
except Exception: pass
print("RESULTAT","TOUT OK" if ok else "ECHECS")
