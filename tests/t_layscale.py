import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
# Mises en page : échelles d'architecte (pieds et pouces) quand le modèle est en unités impériales ; un plan de coupe
# du modèle ne s'imprime pas dans une fenêtre.
import bmesh
import numpy as np
from mathutils import Vector
C=bpy.context; le=m.le
res=[]
def chk(name,ok,info=""):
    res.append(bool(ok)); print(("OK  " if ok else "BAD ")+name, info)
# ---- échelles tapées
T=(('1/4"=1\'-0"',48.0),('1/4" = 1\'',48.0),('1/8" = 1\'-0"',96.0),('3"=1\'-0"',4.0),('1 1/2" = 1\'-0"',8.0),('1" = 10\'',120.0),
   ('1"=100\'',1200.0),('3/16"=1\'',64.0),('1" = 1\'6"',18.0),("1:50",50.0),("1/50",50.0),("2:1",0.5),("25",25.0),("1 : 75",75.0))
bad=[(t,le.parse_scale(t)) for t,d in T if le.parse_scale(t) is None or abs(le.parse_scale(t)-d)>1e-9]
chk("échelles tapées : 1/4\" = 1'-0\", 1\" = 10'... et les métriques comme avant", not bad, bad)
bad=[t for t in ("", "abc", '1/4" = ', '= 1\'', '0" = 1\'', '1/0" = 1\'', "1:0", "-5") if le.parse_scale(t) is not None]
chk("textes qui ne sont pas des échelles : refusés", not bad, bad)
chk("écriture : 1:48 en impérial = 1/4\" = 1'-0\" ; en métrique 1:48 ; 1:50 reste 1:50 en impérial",
    le.fmt_scale(48.0,True)=='1/4" = 1\'-0"' and le.fmt_scale(48.0)=="1:48" and le.fmt_scale(50.0,True)=="1:50" and le.fmt_scale(0.5,True)=="2:1",
    (le.fmt_scale(48.0,True), le.fmt_scale(48.0), le.fmt_scale(50.0,True)))
bad=[(n,d) for _k,n,d in le.SCALES_IMPERIAL if le.parse_scale(n) is None or abs(le.parse_scale(n)-d)>1e-9 or le.fmt_scale(d,True)!=n]
chk("chaque échelle d'architecte de la liste se relit et se réécrit à l'identique", not bad and len(le.SCALES_IMPERIAL)==14, bad)
keys=[k for k,_n,_d in m.SCALE_ITEMS] if hasattr(m,"SCALE_ITEMS") else []
chk("fichiers existants : les anciennes échelles et « Custom » gardent leur rang dans la liste", keys[:len(le.SCALES)]==[k for k,_n,_d in le.SCALES] and keys[len(le.SCALES)]=='CUSTOM', keys[:17])
# ---- modèle en pieds : une maison de 26 × 20 pieds
model=C.scene
us=model.unit_settings; us.system='IMPERIAL'; us.scale_length=0.3048; us.length_unit='FEET'
me=bpy.data.meshes.new("Maison"); bm=bmesh.new(); bmesh.ops.create_cube(bm,size=1.0); bmesh.ops.scale(bm,vec=(26.0,20.0,9.0),verts=bm.verts); bm.to_mesh(me); bm.free()
ob=bpy.data.objects.new("Maison",me); model.collection.objects.link(ob); C.view_layer.update()
L=m.layout_create(model,"Plan",'ARCH_B','LANDSCAPE',margin=10.0,title=True)
m.layout_open(C,L)
d=m.detail_create(L,200.0,160.0,300.0,200.0,'TOP',scale=None,fit=True)
dd=d.dessin_detail
imp=[dn for _k,_n,dn in le.SCALES_IMPERIAL]
chk("Fit sur un modèle en pieds : une échelle d'architecte (1/4\" = 1'-0\")", any(abs(dd.scale-x)<1e-9 for x in imp) and abs(dd.scale-48.0)<1e-9, dd.scale)
lab=[c.data.body for c in d.children if c.get("wd_gen")=='label']
chk("étiquette de la fenêtre et cartouche : 1/4\" = 1'-0\"", lab and lab[0].endswith('1/4" = 1\'-0"') and m.title_scale_text(L)=='1/4" = 1\'-0"', (lab, m.title_scale_text(L)))
# la maison mesure 26 pieds = 7924.8 mm -> 165.1 mm sur le papier
P=np.array([(c.matrix_world@Vector(p.co[:3]))[:2] for c in d.children if c.get("wd_gen")=='vis' for sp in c.data.splines for p in sp.points])
w,h=P[:,0].max()-P[:,0].min(), P[:,1].max()-P[:,1].min()
chk("26 × 20 pieds à 1/4\" = 1'-0\" : 6,5 × 5 pouces sur le papier (165,1 × 127 mm)", abs(w-165.1)<1e-3 and abs(h-127.0)<1e-3, (w,h))
for o in C.selected_objects: o.select_set(False)
d.select_set(True); C.view_layer.objects.active=d
r=bpy.ops.dessin.detail_scale(text='1/8" = 1\'-0"')
chk("échelle tapée 1/8\" = 1'-0\" -> 1:96, la liste suit", r=={'FINISHED'} and abs(dd.scale-96.0)<1e-9 and dd.scale_preset=='I18_1', (r,dd.scale,dd.scale_preset))
r=bpy.ops.dessin.detail_scale(text='1:50')
chk("une échelle métrique reste possible sur un plan en pieds (écrite 1:50)", abs(dd.scale-50.0)<1e-9 and dd.scale_preset=='S1_50' and [c.data.body for c in d.children if c.get("wd_gen")=='label'][0].endswith("1:50"), dd.scale)
names=[n for _k,n,_d in le.scale_list(True)]
chk("liste d'échelles d'un plan en pieds : agrandissements, 1:1, puis les échelles d'architecte (pas de 1:20, 1:50...)", "1:1" in names and '1/4" = 1\'-0"' in names and "1:50" not in names and "1:50" in [n for _k,n,_d in le.scale_list(False)], names)
dd.scale=48.0
chk("vue de détail d'une fenêtre à 1/4\" : 1/2\" = 1'-0\" (le double, dans la même famille)", abs(m.callout_scale(48.0)-24.0)<1e-9 and abs(m.callout_scale(50.0)-25.0)<1e-9, (m.callout_scale(48.0), m.callout_scale(50.0)))
# ---- modèle métrique : rien ne change
us.system='METRIC'; us.scale_length=1.0; us.length_unit='METERS'
bpy.ops.dessin.detail_fit()
chk("le même modèle en mètres : Fit donne une échelle métrique, écrite 1:n", le.scale_preset(dd.scale).startswith('S') and [c.data.body for c in d.children if c.get("wd_gen")=='label'][0].endswith(le.fmt_scale(dd.scale)), dd.scale)
# ---- un plan de coupe du modèle ne s'imprime pas
def layers_in(o): return sorted({c.get("wd_layer","?") for c in o.children if c.get("wd_gen") in ('vis','hid')})
n0=sum(len(sp.points) for c in d.children if c.get("wd_gen")=='vis' for sp in c.data.splines)
V_,E_=m.clip_symbol_geometry(40.0)
cme=bpy.data.meshes.new("Clipping Plane"); cme.from_pydata(V_,E_,[]); cme.update()
cp=bpy.data.objects.new("Clipping Plane",cme); cp["cad_clip"]=1; cp["cad_clip_on"]=1; cp["cad_clip_v"]=m.CLIP_VER; cp["cad_clip_sym"]=m.CLIP_SYMBOL
model.collection.objects.link(cp)
m.detail_rebuild(d,force=True); s0=dd.scale
n1=sum(len(sp.points) for c in d.children if c.get("wd_gen")=='vis' for sp in c.data.splines)
chk("plan de coupe dans le modèle : son repère n'est pas tracé dans la fenêtre", n1==n0, (n0,n1))
bpy.ops.dessin.detail_fit()
chk("... et Fit ne cadre pas sur lui (il est 3 fois plus grand que la maison)", abs(dd.scale-s0)<1e-9, (s0,dd.scale))
print("RESULTAT",sum(res),"/",len(res))
