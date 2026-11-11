import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
import numpy as np, bmesh, time, random
ok=True
_fs=None
def chk(name,cond,extra=""):
    global ok
    ok&=bool(cond); print(("OK " if cond else "BAD"),name,extra)
for o in list(bpy.data.objects): bpy.data.objects.remove(o)
random.seed(3)
def cube(name,loc,size=1.0,sub=0):
    me=bpy.data.meshes.new(name); bm=bmesh.new(); bmesh.ops.create_cube(bm,size=size)
    if sub: bmesh.ops.subdivide_edges(bm,edges=bm.edges[:],cuts=sub,use_grid_fill=True)
    bm.to_mesh(me); bm.free()
    o=bpy.data.objects.new(name,me); bpy.context.scene.collection.objects.link(o); o.location=loc; return o
N=1500
objs=[cube("C%04d"%i,(random.uniform(-400,400),random.uniform(-400,400),0),1.0,sub=3) for i in range(N)]
near=cube("Near",(3,2,0),2.0)
bpy.context.view_layer.update()
t=time.perf_counter(); d1=m.collect_snap_points(ctx); t1=time.perf_counter()-t
chk("collecte initiale",len(d1[0])>m._ASYNC_MIN,(len(d1[0]),round(t1,3)))
chk("boîtes par objet présentes",d1.obj_span is not None and len(d1.obj_span[0])>=N)
t=time.perf_counter(); d2=m.collect_snap_points(ctx); t2=time.perf_counter()-t
chk("2e collecte : réutilisation globale",d2 is not d1 and d2[0] is d1[0] and t2<t1/5,(round(t1,3),round(t2,4)))
m._HOVER['version']+=1
t=time.perf_counter(); dS=m.collect_snap_points(ctx); tS=time.perf_counter()-t
chk('scène touchée sans changement : tableaux réutilisés',dS[0] is d1[0],(round(tS*1000,1),'ms'))
# exclusions indépendantes
m.exclude_snap(d2,["Near"])
d3=m.collect_snap_points(ctx)
chk("exclusion d'un outil n'abîme pas la réserve",d3.excl is None and (d3.edges is None or len(d3.edges)==len(d1.edges)),(d2.excl is not None))
# index écran : culling == complet pour les points visibles
persp=np.array(rv3d.perspective_matrix,dtype=np.float64)
ca=m._build_screen_index(d1,persp,region.width,region.height)
sp=d1.obj_span; d1.obj_span=None
cb=m._build_screen_index(d1,persp,region.width,region.height); d1.obj_span=sp
chk("index : mêmes points visibles",np.array_equal(np.sort(ca["order"]),np.sort(cb["order"])),(len(ca["order"]),len(cb["order"]),len(d1[0])))
io_=ca["order"]
chk("index : mêmes coordonnées écran",np.allclose(ca["sx"][io_],cb["sx"][io_]) and np.allclose(ca["sy"][io_],cb["sy"][io_]))
ta=time.perf_counter(); [m._build_screen_index(d1,persp,region.width,region.height) for _ in range(3)]; ta=(time.perf_counter()-ta)/3
d1.obj_span=None; tb=time.perf_counter(); [m._build_screen_index(d1,persp,region.width,region.height) for _ in range(3)]; tb=(time.perf_counter()-tb)/3; d1.obj_span=sp
print("   index écran : %.1f ms avec tri par objet, %.1f ms sans"%(ta*1000,tb*1000))
_orig_find=m.find_snap_in
def _find(d,x,y,region,rv3d):
    m._screen_index(d,np.array(rv3d.perspective_matrix,dtype=np.float64),region,allow_async=False)
    return _orig_find(d,x,y,region,rv3d)
m.find_snap_in=_find
# accrochage sur un sommet du cube proche (coin (4,3,1) -> écran)
sx,sy=scr(4,3)
r=m.find_snap_in(d3,sx,sy,region,rv3d)
chk("accrochage au coin du cube",r is not None and abs(r[0].x-4)<1e-6 and abs(r[0].y-3)<1e-6,r and tuple(r[0]))
# déplacement : la nouvelle position est accrochable, l'ancienne non
near.location=(10,8,0); bpy.context.view_layer.update()
d4=m.collect_snap_points(ctx)
r_old=m.find_snap_in(d4,sx,sy,region,rv3d); r_new=m.find_snap_in(d4,*scr(11,9),region,rv3d)
chk("objet déplacé : ancien coin libéré",r_old is None or abs(r_old[0].x-4)>1e-3)
chk("objet déplacé : nouveau coin accroché",r_new is not None and abs(r_new[0].x-11)<1e-6,r_new and tuple(r_new[0]))
# modification de géométrie (sommets déplacés par script + update)
co=np.empty(len(near.data.vertices)*3,dtype=np.float32); near.data.vertices.foreach_get('co',co)
co=co.reshape(-1,3); co[:,0]*=2.0; near.data.vertices.foreach_set('co',co.ravel()); near.data.update()
bpy.context.view_layer.update()
d5=m.collect_snap_points(ctx)
r_g=m.find_snap_in(d5,*scr(12,9),region,rv3d)
chk("géométrie modifiée : nouveau sommet accroché",r_g is not None and abs(r_g[0].x-12)<1e-6,(r_g and tuple(r_g[0]), m._GEOM["ver"].get("Near")))
# bmesh
bm=bmesh.new(); bm.from_mesh(near.data)
for v in bm.verts: v.co.y*=1.5
bm.to_mesh(near.data); bm.free(); near.data.update(); bpy.context.view_layer.update()
d6=m.collect_snap_points(ctx)
r_b=m.find_snap_in(d6,*scr(12,9.5),region,rv3d)
chk("géométrie bmesh : nouveau sommet accroché",r_b is not None and abs(r_b[0].y-9.5)<1e-6,r_b and tuple(r_b[0]))
# validation légère : temps d'une collecte après un petit changement
near.location=(10,8.5,0); bpy.context.view_layer.update()
t=time.perf_counter(); d7=m.collect_snap_points(ctx); t7=time.perf_counter()-t
print("   collecte après déplacement d'un objet : %.0f ms (initiale %.0f ms)"%(t7*1000,t1*1000))
chk("collecte incrémentale plus rapide",t7<t1*0.7,(round(t7,3),round(t1,3)))
# objects_near_rect : équivalence avec le calcul direct
def ref(objs,persp,region,rect,margin=2.0):
    keep=[]
    for o in objs:
        if o.type in {'EMPTY','LIGHT','CAMERA'}: keep.append(o); continue
        bb=np.array([tuple(c) for c in o.bound_box]); mw=np.array(o.matrix_world)
        w=bb@mw[:3,:3].T+mw[:3,3]; sxx,syy,okk=m._project_region(w,persp,region)
        if okk.all() and (sxx.max()<rect[0]-margin or sxx.min()>rect[2]+margin or syy.max()<rect[1]-margin or syy.min()>rect[3]+margin): continue
        keep.append(o)
    return keep
em=bpy.data.objects.new("E",None); bpy.context.scene.collection.objects.link(em); bpy.context.view_layer.update()
allo=list(bpy.context.view_layer.objects)
same=True
for _ in range(6):
    x,y=random.uniform(100,900),random.uniform(100,900); rect=(x-40,y-40,x+40,y+40)
    a=[o.name for o in m.objects_near_rect(allo,persp,region,rect)]; b=[o.name for o in ref(allo,persp,region,rect)]
    same&=(a==b)
chk("objects_near_rect identique au calcul direct",same)
t=time.perf_counter(); [m.objects_near_rect(allo,persp,region,(500,500,512,512)) for _ in range(10)]; tn=(time.perf_counter()-t)/10
print("   objects_near_rect : %.2f ms (%d objets)"%(tn*1000,len(allo)))
near.location=(0,0,0); bpy.context.view_layer.update()
allo=[o for o in allo if o.name in bpy.data.objects] if False else list(bpy.context.view_layer.objects)
a=[o.name for o in m.objects_near_rect(allo,persp,region,(495,495,505,505))]
chk("boîtes mises à jour après déplacement","Near" in a)
# ---- complément : la réserve ressert quand un objet bouge, apparaît ou disparaît
bpy.context.view_layer.update()
dA=m.collect_snap_points(ctx); base=dA[0]
near.location=(20,-6,0); bpy.context.view_layer.update()
dB=m.collect_snap_points(ctx)
chk("objet déplacé : grands tableaux réutilisés",dB[0] is base and dB.extra is not None and "Near" in dB.dead_base,(len(dB.extra[0]) if dB.extra is not None else None))
chk("objet déplacé : accroché à la nouvelle place",(lambda r: r is not None and abs(r[0].x-22)<1e-6 and abs(r[0].y+4.5)<1e-6)(m.find_snap_in(dB,*scr(22,-4.5),region,rv3d)))
chk("objet déplacé : ancienne place libérée",m.find_snap_in(dB,*scr(-2,-1.5),region,rv3d) is None)
pl=m.build_polyline(bpy.context,"NewPoly",[Vector((30,20,0)),Vector((40,20,0)),Vector((40,28,0))],False)
bpy.context.view_layer.update()
dC=m.collect_snap_points(ctx)
chk("nouvel objet : grands tableaux réutilisés",dC[0] is base and "NewPoly" in dC.extra.ranges)
r=m.find_snap_in(dC,*scr(40,20),region,rv3d)
chk("nouvel objet : sommet accroché",r is not None and abs(r[0].x-40)<1e-6 and abs(r[0].y-20)<1e-6,r and (tuple(r[0]),r[2]))
r=m.find_snap_in(dC,*scr(35,20),region,rv3d)
chk("nouvel objet : milieu accroché",r is not None and abs(r[0].x-35)<1e-6,r and (tuple(r[0]),r[2]))
st=bpy.context.scene.dessin
r=m.find_snap_in(dC,*scr(32.3,20),region,rv3d)
chk("nouvel objet : Near sur son segment",(r is not None and r[2]==7 and abs(r[0].y-20)<1e-6) or not m.osnap("near"),r and (tuple(r[0]),r[2]))
dD=m.collect_snap_points(ctx); m.exclude_snap(dD,["NewPoly"])
chk("exclusion d'un objet du complément",m.find_snap_in(dD,*scr(40,20),region,rv3d) is None and m.find_snap_in(dC,*scr(40,20),region,rv3d) is not None)
dE=m.collect_snap_points(ctx,exclude={"Near"})
chk("collecte avec exclusion : réserve réutilisée",dE[0] is base and m.find_snap_in(dE,*scr(22,-4.5),region,rv3d) is None)
dF=m.collect_snap_points(ctx)
chk("après une collecte avec exclusion : l'objet revient",m.find_snap_in(dF,*scr(22,-4.5),region,rv3d) is not None)
bpy.data.objects.remove(pl); bpy.context.view_layer.update()
dG=m.collect_snap_points(ctx)
chk("objet supprimé : plus accrochable",dG[0] is base and m.find_snap_in(dG,*scr(40,20),region,rv3d) is None)
victim=objs[0]; vloc=victim.matrix_world.translation.copy(); vn=victim.name
bpy.data.objects.remove(victim); bpy.context.view_layer.update()
dH=m.collect_snap_points(ctx)
chk("objet de la réserve supprimé : masqué",dH[0] is base and vn in dH.dead_base)
for o in objs[1:800]: o.location.z+=1.0
bpy.context.view_layer.update()
dI=m.collect_snap_points(ctx)
chk("beaucoup d'objets changés : tableaux recalculés",dI[0] is not base and dI.extra is None)
t=time.perf_counter(); near.location=(21,-6,0); bpy.context.view_layer.update(); dJ=m.collect_snap_points(ctx); tJ=time.perf_counter()-t
print("   collecte après déplacement (avec complément) : %.0f ms"%(tJ*1000))
# annuler : caches invalidés
m._on_undo_redo(); chk("annuler invalide la réserve",m._SNAP_LAST["data"] is None)
print("RESULTAT","TOUT OK" if ok else "ECHECS")
