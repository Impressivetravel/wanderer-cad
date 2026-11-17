import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
import numpy as np, bmesh, time, random
ok=True
def chk(name,cond,extra=""):
    global ok
    ok&=bool(cond); print(("OK " if cond else "BAD"),name,extra)
def wipe():
    for o in list(bpy.data.objects): bpy.data.objects.remove(o)
    for me in list(bpy.data.meshes): bpy.data.meshes.remove(me)
    m._perf_caches_clear(); bpy.context.view_layer.update()
def cube(name,loc,size=1.0,sub=0):
    me=bpy.data.meshes.new(name); bm=bmesh.new(); bmesh.ops.create_cube(bm,size=size)
    if sub: bmesh.ops.subdivide_edges(bm,edges=bm.edges[:],cuts=sub,use_grid_fill=True)
    bm.to_mesh(me); bm.free()
    o=bpy.data.objects.new(name,me); bpy.context.scene.collection.objects.link(o); o.location=loc; return o
def grid(name,loc,n,size):
    me=bpy.data.meshes.new(name); bm=bmesh.new(); bmesh.ops.create_grid(bm,x_segments=n,y_segments=n,size=size)
    bm.to_mesh(me); bm.free()
    o=bpy.data.objects.new(name,me); bpy.context.scene.collection.objects.link(o); o.location=loc; return o
persp=np.array(rv3d.perspective_matrix,dtype=np.float64)
m._ASYNC_MIN=10**9
MINPX=m._LOD_MIN_PX; m._LOD_MIN_PX=0.0     # la règle de taille à l'écran est testée à part (section 8c)
st=bpy.context.scene.dessin
def find(d,x,y,tries=8,ref=None):
    r=None
    for _ in range(tries):
        r=m.find_snap_in(d,x,y,region,rv3d,ref)
    return r
def setb(v):
    m.PREF_DEFAULTS["snap_budget"]=v; m._update_perf()

wipe(); random.seed(5)
# 60 petits cubes (8 sommets), 6 cubes moyens (subdivisés), 4 objets denses, 1 contour, 1 cercle
small=[cube("S%02d"%i,(-40+ (i%10)*8, -40+(i//10)*6,0),2.0) for i in range(60)]
mid=[cube("M%d"%i,(-36+i*12,0,0),4.0,sub=6) for i in range(6)]
dense=[grid("D%d"%i,(-30+i*20,30,0),110,4.0) for i in range(4)]       # 111² = 12 321 sommets > 8000
wire=m.build_polyline(bpy.context,"Wire",[Vector((-45,-46,0)),Vector((45,-46,0)),Vector((45,-44,0))],False)
bpy.context.view_layer.update()

# ---------- 1. sans limite : référence
setb(0.0)
d0=m.collect_snap_points(ctx)
n0=len(d0[0])
chk("sans limite : denses marqués allégés (échantillon)",set(d0.coarse)=={o.name for o in dense},sorted(d0.coarse))
probes=[]
for o in small[:20]+mid:
    mw=o.matrix_world
    for v in list(o.data.vertices)[:8]:
        p=mw@v.co; probes.append((o.name,p.copy()))
ref={}
for i,(n_,p) in enumerate(probes):
    r=find(d0,*scr(p.x,p.y)); ref[i]=r
chk("référence : tous les sommets sondés accrochent",all(r is not None for r in ref.values()),sum(r is None for r in ref.values()))

# ---------- 2. budget minuscule : les objets lourds sortent des grands tableaux
setb(0.0006)        # 600 points
d1=m.collect_snap_points(ctx)
n1=len(d1[0])
chk("budget : moins de points en réserve",n1<n0 and n1<=600+200,(n0,n1))
chk("budget : objets moyens et denses à la demande",all(o.name in d1.coarse for o in mid+dense),len(d1.coarse))
chk("budget : contour jamais allégé","Wire" not in d1.coarse and wire.name in d1.ranges and d1.ranges[wire.name][1]>d1.ranges[wire.name][0])
bad=0; kinds=0
for i,(n_,p) in enumerate(probes):
    r=find(d1,*scr(p.x,p.y))
    r0=ref[i]
    if r is None or (r[0]-r0[0]).length>1e-9: bad+=1
    elif r[2]!=r0[2]: kinds+=1
chk("budget : mêmes points d'accrochage que sans limite sous le curseur",bad==0,(bad,len(probes)))
chk("budget : mêmes types d'accroche",kinds==0,kinds)

# ---------- 3. objet dense : vrais sommets (et non l'échantillon) + Near / Mid sur ses arêtes
o=dense[1]; mw=o.matrix_world
vs=[mw@v.co for v in o.data.vertices]
hits=0; exact=0
for v in random.sample(vs,40):
    r=find(d1,*scr(v.x,v.y))
    if r is not None:
        hits+=1
        if min((r[0]-w).length for w in vs)<1e-6 or r[2] in (7,8): exact+=1
chk("dense : accrochage sous le curseur",hits==40,hits)
chk("dense : points réels de l'objet",exact==hits,(exact,hits))
st.osnap_near=True
e=o.data.edges[len(o.data.edges)//2]; a=mw@o.data.vertices[e.vertices[0]].co; b=mw@o.data.vertices[e.vertices[1]].co
# zoom fort pour séparer les arêtes : on teste Near par le calcul direct
q=a.lerp(b,0.3)
dl=m._SNAP_LOD.get(o.name)
chk("dense : détail en mémoire avec arêtes",dl is not None and dl[1].edges is not None and len(dl[1].edges)==len(o.data.edges),dl and (len(dl[1][0]),None if dl[1].edges is None else len(dl[1].edges)))
chk("dense : sommets sans les milieux (objet léger en mémoire)",dl is not None and len(dl[1][0])<=len(o.data.vertices)+2,dl and len(dl[1][0]))
st.osnap_near=False

# ---------- 4. un seul chargement par mouvement, mémoire bornée
m._SNAP_LOD.clear(); l0=m._LOD["loads"]
p=mid[0].matrix_world@mid[0].data.vertices[0].co
# geste rapide (grands sauts rapprochés dans le temps) : aucune lecture
for k in range(6):
    pk=mid[k%6].matrix_world@mid[k%6].data.vertices[0].co
    m.find_snap_in(d1,*scr(pk.x,pk.y),region,rv3d)
chk("geste rapide à travers la scène : aucune lecture d'objet",m._LOD["loads"]-l0==0,m._LOD["loads"]-l0)
m.find_snap_in(d1,scr(p.x,p.y)[0]+9,scr(p.x,p.y)[1],region,rv3d); l0=m._LOD["loads"]
m.find_snap_in(d1,scr(p.x,p.y)[0]+3,scr(p.x,p.y)[1],region,rv3d)
chk("curseur qui ralentit : une lecture, une seule par mouvement",m._LOD["loads"]-l0==1,m._LOD["loads"]-l0)
import time as _t; _t.sleep(0.2); m._SNAP_LOD.clear(); l0=m._LOD["loads"]
m.find_snap_in(d1,scr(p.x,p.y)[0]+300,scr(p.x,p.y)[1]+200,region,rv3d); m.find_snap_in(d1,*scr(p.x,p.y),region,rv3d)
_t.sleep(0.2); m.find_snap_in(d1,*scr(p.x,p.y),region,rv3d)
chk("après une pause : lecture au premier mouvement",m._LOD["loads"]-l0==1,m._LOD["loads"]-l0)
for o_ in mid+dense:
    pp=o_.matrix_world@o_.data.vertices[0].co
    find(d1,*scr(pp.x,pp.y))
chk("détails gardés : au plus %d objets"%m._LOD_MAX_OBJS,len(m._SNAP_LOD)<=m._LOD_MAX_OBJS,len(m._SNAP_LOD))
l1=m._LOD["loads"]
for _ in range(20): m.find_snap_in(d1,*scr(pp.x,pp.y),region,rv3d)
chk("survol répété : aucun rechargement",m._LOD["loads"]==l1,m._LOD["loads"]-l1)

# ---------- 5. objet déplacé / modifié / supprimé / exclu
o=mid[2]; p_old=o.matrix_world@o.data.vertices[0].co
find(d1,*scr(p_old.x,p_old.y))
o.location=(o.location.x+1.5,o.location.y+17.0,0); bpy.context.view_layer.update()
d2=m.collect_snap_points(ctx)
p_new=o.matrix_world@o.data.vertices[0].co
r_new=find(d2,*scr(p_new.x,p_new.y)); r_old=find(d2,*scr(p_old.x,p_old.y))
chk("déplacé : nouveau sommet accroché",r_new is not None and (r_new[0].xy-p_new.xy).length<1e-6,r_new and tuple(r_new[0]))
chk("déplacé : ancien sommet libéré",r_old is None or (r_old[0]-p_old).length>1e-3,r_old and tuple(r_old[0]))
co=np.empty(len(o.data.vertices)*3,dtype=np.float32); o.data.vertices.foreach_get('co',co)
co=co.reshape(-1,3); co[:,0]*=1.5; o.data.vertices.foreach_set('co',co.ravel()); o.data.update(); bpy.context.view_layer.update()
d3=m.collect_snap_points(ctx)
p_mod=o.matrix_world@o.data.vertices[0].co
r_mod=find(d3,*scr(p_mod.x,p_mod.y))
chk("modifié : sommet à jour",r_mod is not None and (r_mod[0].xy-p_mod.xy).length<1e-6,(tuple(p_mod),r_mod and tuple(r_mod[0])))
d4=m.collect_snap_points(ctx)
m.exclude_snap(d4,[o.name])
r_ex=find(d4,*scr(p_mod.x,p_mod.y))
chk("exclu par l'outil : pas d'accrochage sur lui",r_ex is None or (r_ex[0]-p_mod).length>1e-3,r_ex and tuple(r_ex[0]))
d5=m.collect_snap_points(ctx)
chk("exclusion d'un outil : la réserve reste intacte",find(d5,*scr(p_mod.x,p_mod.y)) is not None)
nm=o.name; bpy.data.objects.remove(o); bpy.context.view_layer.update()
d6=m.collect_snap_points(ctx)
r_del=find(d6,*scr(p_mod.x,p_mod.y))
chk("supprimé : plus d'accrochage",r_del is None or (r_del[0]-p_mod).length>1e-3,r_del and tuple(r_del[0]))
chk("supprimé : retiré des objets allégés",nm not in d6.coarse)

# ---------- 6. annuler / rétablir et changement de fichier vident les détails
find(d6,*scr(p.x,p.y)); chk("détail chargé",len(m._SNAP_LOD)>0)
m._on_undo_redo(); chk("annuler : détails relus",len(m._SNAP_LOD)==0 and m._TIER["key"] is None)

# ---------- 7. budget large : comportement d'avant (aucun objet ordinaire allégé)
setb(2.0)
d7=m.collect_snap_points(ctx)
chk("budget par défaut non atteint : seuls les denses sont à la demande",set(d7.coarse)=={o.name for o in dense},len(d7.coarse))
chk("budget par défaut : mêmes points que sans limite",len(d7[0])==len(m.collect_snap_points(ctx)[0]))

# ---------- 8. Near / Perp sur un objet à la demande (zoom : cube seul, arêtes longues)
wipe(); setb(0.00001)
big=cube("Big",(0,0,0),40.0)
filler=[cube("F%d"%i,(-45+i*3,-45,0),1.0) for i in range(4)]
bpy.context.view_layer.update()
d8=m.collect_snap_points(ctx)
chk("cube à la demande","Big" in d8.coarse,sorted(d8.coarse))
st.osnap_near=True
r=find(d8,*scr(7.3,20.0))          # arête du haut (y=20), loin des sommets et du milieu
chk("Near sur une arête d'un objet à la demande",r is not None and r[2]==7 and abs(r[0].y-20.0)<1e-6 and abs(r[0].x-7.3)<0.2,r and (tuple(r[0]),r[2]))
r=find(d8,*scr(0.0,20.0))
chk("Mid sur une arête d'un objet à la demande",r is not None and r[2]==1 and abs(r[0].x)<1e-6,r and (tuple(r[0]),r[2]))
st.osnap_perp=True
r=find(d8,*scr(20.0,5.02),ref=Vector((30,5,0)))
chk("Perp sur un objet à la demande",r is not None and r[2] in (9,7) and abs(r[0].x-20.0)<1e-6,r and (tuple(r[0]),r[2]))
# mêmes réponses qu'en mode sans limite (le cube est alors dans les grands tableaux)
got=[find(d8,*scr(7.3,20.0)),find(d8,*scr(0.0,20.0)),find(d8,*scr(20.0,5.02),ref=Vector((30,5,0))),find(d8,*scr(20.0,20.0)),find(d8,*scr(13.1,-20.0))]
setb(0.0); d9=m.collect_snap_points(ctx)
chk("sans limite : cube dans les grands tableaux","Big" not in d9.coarse)
exp=[find(d9,*scr(7.3,20.0)),find(d9,*scr(0.0,20.0)),find(d9,*scr(20.0,5.02),ref=Vector((30,5,0))),find(d9,*scr(20.0,20.0)),find(d9,*scr(13.1,-20.0))]
same=[g is not None and e is not None and g[2]==e[2] and (g[0].xy-e[0].xy).length<1e-6 for g,e in zip(got,exp)]
chk("à la demande = sans limite (Near, Mid, Perp, Vertex)",all(same),[(tuple(g[0]),g[2],tuple(e[0]),e[2]) for g,e,s_ in zip(got,exp,same) if not s_])
st.osnap_near=False; st.osnap_perp=False

# ---------- 8b. vue d'ensemble : 70 objets à la demande superposés sous le curseur
wipe(); setb(0.00001); random.seed(11)
pile=[cube("P%02d"%i,(random.uniform(-0.6,0.6),random.uniform(-0.6,0.6),random.uniform(-3,3)),random.uniform(1.0,2.0),sub=2) for i in range(70)]
bpy.context.view_layer.update()
dp=m.collect_snap_points(ctx)
chk("pile : tous à la demande",len(dp.coarse)==70,len(dp.coarse))
tg=[]
random.seed(12)
for o_ in random.sample(pile,25):
    v=o_.matrix_world@o_.data.vertices[random.randrange(len(o_.data.vertices))].co; tg.append(v)
import time as _t
moves=0; tmax=0.0
for v in tg[:1]:
    x,y=scr(v.x,v.y)
    for k in range(60):
        t=_t.perf_counter(); m.find_snap_in(dp,x+(k%3),y,region,rv3d); tmax=max(tmax,_t.perf_counter()-t); moves+=1
        if len(m._SNAP_LOD)>=70: break
chk("pile : les 70 objets sous le curseur sont lus en quelques mouvements",len(m._SNAP_LOD)==70 and moves<=40,(len(m._SNAP_LOD),moves))
chk("pile : aucun mouvement au-dessus de 60 ms pendant la lecture",tmax<0.060,round(tmax*1000,1))
gotp=[find(dp,*scr(v.x,v.y),tries=3) for v in tg]
setb(0.0); dq=m.collect_snap_points(ctx)
expp=[find(dq,*scr(v.x,v.y),tries=1) for v in tg]
samep=[g is not None and e is not None and (g[0]-e[0]).length<1e-9 and g[2]==e[2] for g,e in zip(gotp,expp)]
chk("pile : même point que sans limite pour 25 sommets visés",all(samep),(sum(samep),len(samep)))
setb(0.00001); dp=m.collect_snap_points(ctx)
t=_t.perf_counter()
for k in range(200): m.find_snap_in(dp,scr(tg[0].x,tg[0].y)[0]+(k%5),scr(tg[0].x,tg[0].y)[1]+(k%3),region,rv3d)
tp=(_t.perf_counter()-t)/200*1000
print("   pile de 70 objets à la demande sous le curseur : %.2f ms par mouvement"%tp)
chk("pile : survol fluide (< 20 ms)",tp<20.0,round(tp,2))
# mémoire bornée : plafond de points respecté
old_cap=m._LOD_MAX_PTS; m._LOD_MAX_PTS=3000
for v in tg: find(dp,*scr(v.x+8,v.y+8),tries=1); find(dp,*scr(v.x,v.y),tries=4)
tot=sum(len(h[1][0]) for h in m._SNAP_LOD.values())
chk("plafond de mémoire des détails respecté (hors objets sous le curseur)",m._LOD["pts"]==tot,(m._LOD["pts"],tot,len(m._SNAP_LOD)))
m._LOD_MAX_PTS=old_cap

# ---------- 8b2. curseur arrêté : la lecture continue en tâche de fond, par tranches
m._SNAP_LOD.clear(); m._LOD["pts"]=0; old_v=m._LOD_VERTS; m._LOD_VERTS=400      # tranches de ~4 objets
_t.sleep(0.2)
x0,y0=scr(tg[0].x,tg[0].y)
m.find_snap_in(dp,x0,y0,region,rv3d)
n1=len(m._SNAP_LOD)
chk("tranche : une partie seulement est lue au premier mouvement",0<n1<70,n1)
chk("tâche de fond programmée",m._LOD["pending"] is not None and bpy.app.timers.is_registered(m._lod_timer))
ticks=0; tmaxb=0.0
while ticks<200:
    t=_t.perf_counter(); r=m._lod_timer(); tmaxb=max(tmaxb,_t.perf_counter()-t); ticks+=1
    if r is None: break
chk("tâche de fond : tout est lu sans bouger la souris",len(m._SNAP_LOD)==70 and m._LOD["pending"] is None,(len(m._SNAP_LOD),ticks))
chk("tâche de fond : tranches courtes (< 60 ms)",tmaxb<0.060,round(tmaxb*1000,1))
rb=m.find_snap_in(dp,x0,y0,region,rv3d)
chk("tâche de fond : le point visé est accroché sans autre mouvement",rb is not None and (rb[0]-expp[0][0]).length<1e-9,rb and tuple(rb[0]))
# un geste rapide annule la suite
m._SNAP_LOD.clear(); m._LOD["pts"]=0; _t.sleep(0.2)
m.find_snap_in(dp,x0,y0,region,rv3d); m.find_snap_in(dp,x0+300,y0+250,region,rv3d)
chk("geste rapide : la tâche de fond s'arrête",m._LOD["pending"] is None and m._lod_timer() is None)
# objet illisible : pas de boucle sans fin
m._SNAP_LOD.clear(); m._LOD["pts"]=0; _t.sleep(0.2)
_orig_collect=m.collect_snap_points
def _boom(*a,**k):
    if k.get("detail"): raise RuntimeError("illisible")
    return _orig_collect(*a,**k)
m.collect_snap_points=_boom
m.find_snap_in(dp,x0,y0,region,rv3d); ticks=0
while ticks<400 and m._lod_timer() is not None: ticks+=1
m.collect_snap_points=_orig_collect
chk("lecture impossible : la tâche de fond s'arrête d'elle-même",ticks<100,ticks)
m._SNAP_LOD.clear(); m._LOD["pts"]=0; m._LOD_VERTS=old_v

# ---------- 8c. taille à l'écran : un objet à la demande trop petit pour être visé n'est pas lu ; il l'est dès qu'il grandit
wipe(); setb(0.00001); m._LOD_MIN_PX=MINPX
tiny=cube("Tiny",(10,10,0),3.0,sub=3)        # 30 px à l'écran
bigc=cube("Bigc",(-20,-20,0),8.0,sub=3)      # 80 px
bpy.context.view_layer.update()
dz=m.collect_snap_points(ctx)
vt=tiny.matrix_world@tiny.data.vertices[0].co; vb=bigc.matrix_world@bigc.data.vertices[0].co
l0=m._LOD["loads"]
rt=find(dz,*scr(vt.x,vt.y)); 
chk("30 px à l'écran : pas lu, pas d'accrochage",rt is None and m._LOD["loads"]==l0,(rt and tuple(rt[0]),m._LOD["loads"]-l0))
rb=find(dz,*scr(vb.x,vb.y))
chk("80 px à l'écran : lu et accroché",rb is not None and (rb[0].xy-vb.xy).length<1e-6,rb and tuple(rb[0]))
# zoom x2 (vue simulée) : le petit objet fait 60 px, il devient accrochable
from mathutils import Matrix as _M
Z=_M(((2,0,0,0),(0,2,0,0),(0,0,1,0),(0,0,0,1)))
rv2=RV(view_matrix=rv3d.view_matrix,window_matrix=Z@rv3d.window_matrix,perspective_matrix=Z@rv3d.perspective_matrix,is_perspective=False,
       view_perspective='ORTHO',view_rotation=rv3d.view_rotation,is_orthographic_side_view=False,view_location=rv3d.view_location,
       view_distance=rv3d.view_distance,view_camera_zoom=0,view_camera_offset=(0,0))
sx2,sy2=(vt.x*S*2+W/2, vt.y*S*2+H/2)
rz=None
m.find_snap_in(dz,sx2,sy2,region,rv2); _t.sleep(0.15)     # la vue vient de changer : l'accrochage attend qu'elle se pose
for _ in range(6): rz=m.find_snap_in(dz,sx2,sy2,region,rv2)
chk("après zoom x2 (60 px) : lu et accroché",rz is not None and (rz[0].xy-vt.xy).length<1e-6,rz and tuple(rz[0]))
m._LOD_MIN_PX=0.0

# ---------- 9. temps de collecte à froid : 3000 objets moyens
wipe(); random.seed(2)
objs=[cube("C%04d"%i,(random.uniform(-45,45),random.uniform(-45,45),0),1.0,sub=7) for i in range(1500)]
bpy.context.view_layer.update()
res={}
for b in (0.0,0.2):
    setb(b)
    t=time.perf_counter(); d=m.collect_snap_points(ctx); t1=time.perf_counter()-t
    ci=m._build_screen_index(d,persp,region.width,region.height)
    mem=sum(a.nbytes for a in d[:4])+sum(v.nbytes for v in ci.values() if hasattr(v,"nbytes"))+(d.edges0.nbytes if d.edges0 is not None else 0)
    res[b]=(len(d[0]),t1,mem)
    print("   budget %.1f M : %d points, collecte %.0f ms, mémoire %.0f Mo, allégés %d"%(b,len(d[0]),t1*1000,mem/1e6,len(d.coarse)))
chk("budget : collecte à froid plus rapide",res[0.2][1]<res[0.0][1]*0.6,(round(res[0.0][1],3),round(res[0.2][1],3)))
chk("budget : mémoire réduite",res[0.2][2]<res[0.0][2]*0.5,(res[0.0][2]//10**6,res[0.2][2]//10**6))
chk("budget respecté",res[0.2][0]<=200000+2000,res[0.2][0])
# survol : temps par mouvement une fois le détail chargé
d=m.collect_snap_points(ctx)
o=objs[10]; pp=o.matrix_world@o.data.vertices[0].co
find(d,*scr(pp.x,pp.y))
t=time.perf_counter()
for i in range(200): m.find_snap_in(d,scr(pp.x,pp.y)[0]+(i%7),scr(pp.x,pp.y)[1]+(i%5),region,rv3d)
tm=(time.perf_counter()-t)/200*1000
print("   survol d'un objet à la demande : %.2f ms par mouvement"%tm)
chk("survol fluide (< 20 ms)",tm<20.0,round(tm,2))
setb(2.0); m._LOD_MIN_PX=MINPX
print("RESULTAT","TOUT OK" if ok else "ECHECS")
