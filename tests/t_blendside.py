import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
# Blend Surface : un clic prend un côté du bord (l'arête de Rhino), pas tout le pourtour de la surface
import bmesh, io, contextlib, math
import numpy as np
C=bpy.context
res=[]
def chk(n,ok,info=""): res.append(bool(ok)); print(("OK  " if ok else "BAD ")+n, info)
def clear():
    for o in list(bpy.data.objects): bpy.data.objects.remove(o)
def plane(name,x0,x1,y0=-1,y1=1,z=0,nx=1,ny=1):
    me=bpy.data.meshes.new(name); bm=bmesh.new()
    vs=[[bm.verts.new((x0+(x1-x0)*i/nx, y0+(y1-y0)*j/ny, z)) for j in range(ny+1)] for i in range(nx+1)]
    for i in range(nx):
        for j in range(ny):
            bm.faces.new((vs[i][j],vs[i+1][j],vs[i+1][j+1],vs[i][j+1]))
    bm.to_mesh(me); bm.free()
    o=bpy.data.objects.new(name,me); C.scene.collection.objects.link(o); C.view_layer.update(); return o
def tube(name,z0,z1,r=1.0,n=32):
    me=bpy.data.meshes.new(name); bm=bmesh.new()
    a=[bm.verts.new((r*math.cos(2*math.pi*i/n),r*math.sin(2*math.pi*i/n),z0)) for i in range(n)]
    b=[bm.verts.new((r*math.cos(2*math.pi*i/n),r*math.sin(2*math.pi*i/n),z1)) for i in range(n)]
    for i in range(n): bm.faces.new((a[i],a[(i+1)%n],b[(i+1)%n],b[i]))
    bm.to_mesh(me); bm.free()
    o=bpy.data.objects.new(name,me); C.scene.collection.objects.link(o); C.view_layer.update(); return o
G=m.DESSIN_OT_blend_srf.invoke.__globals__
def drive(evs,first='MOUSEMOVE'):
    o=make(m.DESSIN_OT_blend_srf); G['_BLEND']["on"]=False; G['_BLEND']["warned"]=0.0
    with contextlib.redirect_stdout(io.StringIO()):
        r=type(o).invoke(o,ctx,ev(first,'PRESS' if first=='LEFTMOUSE' else 'NOTHING',*scr(0,0)))
        if 'RUNNING_MODAL' not in r: return r,o
        for e in evs:
            if e[0]=='c': seq=[ev('MOUSEMOVE','NOTHING',*scr(e[1],e[2])),ev('LEFTMOUSE','PRESS',*scr(e[1],e[2]))]
            else: seq=[ev(e[0],'PRESS',*scr(0,0))]
            for x in seq:
                r=type(o).modal(o,ctx,x)
                if 'FINISHED' in r or 'CANCELLED' in r: return r,o
    return r,o
def bbox(q):
    P=np.array([tuple(q.matrix_world@v.co) for v in q.data.vertices]); return [round(float(x),4) for x in (*P.min(axis=0),*P.max(axis=0))]

# ---------------- 1. côtés d'un bord ----------------
sq=np.array([(0,0,0),(2,0,0),(2,2,0),(0,2,0)],dtype=float)
chk("bord d'un rectangle : quatre côtés", m.loop_sides(sq,True).tolist()==[0,1,2,3], m.loop_sides(sq,True).tolist())
sub=np.array([(0,0,0),(1,0,0),(2,0,0),(2,1,0),(2,2,0),(1,2,0),(0,2,0),(0,1,0)],dtype=float)
chk("rectangle dont chaque côté a deux segments : toujours quatre côtés", m.loop_sides(sub,True).tolist()==[0,0,1,1,2,2,3,3], m.loop_sides(sub,True).tolist())
rot=np.roll(sub,-1,axis=0)       # la boucle commence au milieu d'un côté
s=m.loop_sides(rot,True).tolist()
chk("... même quand la boucle commence au milieu d'un côté (le dernier côté rejoint le premier)", s[0]==s[-1] and len(set(s))==4, s)
circ=np.array([(math.cos(2*math.pi*i/48),math.sin(2*math.pi*i/48),0) for i in range(48)])
chk("bord d'un disque ou bout d'un tube : un seul côté (le cercle entier)", set(m.loop_sides(circ,True).tolist())=={0})
chk("bord ouvert en L : deux côtés", m.loop_sides(np.array([(0,0,0),(1,0,0),(2,0,0),(2,1,0)],dtype=float),False).tolist()==[0,0,1])

# ---------------- 2. deux plans face à face : le raccord relie les deux arêtes cliquées ----------------
for nx in (1,4):
    clear(); a=plane("A",-3,-1,nx=nx,ny=nx); b=plane("B",1,3,nx=nx,ny=nx)
    r,o=drive([('c',-1.0,0.0),('RET',),('c',1.0,0.0),('RET',)])
    bl=[q for q in bpy.data.objects if q.name.startswith("Blend")]
    chk(f"plans de {nx}x{nx} faces : un clic prend le côté visé ({nx} segment(s)), pas les 4 côtés", [len(p['segs']) for p in o.picks]==[nx,nx], [len(p['segs']) for p in o.picks])
    bb=bbox(bl[0]) if bl else None
    chk("... le raccord va d'une arête à l'autre : x de -1 à 1, y de -1 à 1, plat (z = 0)", 'FINISHED' in r and len(bl)==1 and bb==[-1.0,-1.0,0.0,1.0,1.0,0.0], bb)
# deux plans à angle droit : le raccord part tangent à chaque plan
clear(); a=plane("A",-3,-1)
me=bpy.data.meshes.new("V"); bm=bmesh.new(); vs=[bm.verts.new(v) for v in ((0,-1,1),(0,1,1),(0,1,3),(0,-1,3))]; bm.faces.new(vs); bm.to_mesh(me); bm.free()
v=bpy.data.objects.new("V",me); C.scene.collection.objects.link(v); C.view_layer.update()
o=make(m.DESSIN_OT_blend_srf); G['_BLEND']["on"]=False
with contextlib.redirect_stdout(io.StringIO()):
    type(o).invoke(o,ctx,ev('MOUSEMOVE','NOTHING',*scr(0,0)))
li_a=[i for i,l in enumerate(o.loops) if l['obj']=="A"][0]; li_v=[i for i,l in enumerate(o.loops) if l['obj']=="V"][0]
def side_at(li,pred):
    l=o.loops[li]; P=l['P']; n=len(P)
    for si in range(n):
        mid=(P[si]+P[(si+1)%n])/2
        if pred(mid): return si
o.hover=(li_a,side_at(li_a,lambda q: abs(q[0]+1)<1e-6)); o.picks[0]={'li':li_a,'segs':set(o.segs_of(*o.hover))}
o.hover=(li_v,side_at(li_v,lambda q: abs(q[2]-1)<1e-6)); o.picks[1]={'li':li_v,'segs':set(o.segs_of(*o.hover))}
runs=[G['_blend_run'](o.loops[p['li']],p['segs']) for p in o.picks]
G['_BLEND']["last"]=(runs[0],runs[1],["A","V"]); o.end_modal(bpy.context)
r=type(o).execute(o,ctx); C.view_layer.update()
bl=[q for q in bpy.data.objects if q.name.startswith("Blend")]
bb=bbox(bl[0]) if bl else None
chk("plans à angle droit : le raccord relie le bord du plan horizontal (x=-1, z=0) au bas du plan vertical (x=0, z=1), sans déborder",
    'FINISHED' in r and len(bl)==1 and bb==[-1.0,-1.0,0.0,0.0,1.0,1.0], bb)
# tangence : le premier rang quitte le plan horizontal à plat, le dernier arrive verticalement
WV=np.array([tuple(bl[0].matrix_world@v.co) for v in bl[0].data.vertices])
near_a=WV[(WV[:,0]<-0.9)]; near_v=WV[(WV[:,2]>0.9)]
chk("... il part tangent au plan horizontal (z reste ~0 près de x=-1) et arrive tangent au plan vertical (x reste ~0 près de z=1)",
    float(np.abs(near_a[:,2]).max())<0.02 and float(np.abs(near_v[:,0]).max())<0.02, (round(float(np.abs(near_a[:,2]).max()),4),round(float(np.abs(near_v[:,0]).max()),4)))

# ---------------- 3. C : tout le bord ; bout d'un tube : le cercle entier d'un clic ----------------
clear(); a=plane("A",-3,-1,nx=4,ny=4); b=plane("B",1,3,nx=4,ny=4)
r,o=drive([('C',),('c',-1.0,0.0)])
chk("C (ChainEdges) puis clic : tout le pourtour (16 segments)", o.chain and o.picks[0] is not None and len(o.picks[0]['segs'])==16, o.picks[0] and len(o.picks[0]['segs']))
clear(); t1=tube("T1",0,1); t2=tube("T2",3,4)
o=make(m.DESSIN_OT_blend_srf); G['_BLEND']["on"]=False
with contextlib.redirect_stdout(io.StringIO()):
    type(o).invoke(o,ctx,ev('MOUSEMOVE','NOTHING',*scr(0,0)))
top=[i for i,l in enumerate(o.loops) if l['obj']=="T1" and abs(l['P'][:,2].mean()-1)<1e-6][0]
chk("bout d'un tube : un clic prend le cercle entier (32 segments), sans appuyer sur C", not o.chain and len(o.segs_of(top,5))==32, len(o.segs_of(top,5)))
o.end_modal(bpy.context)

# ---------------- 4. que des solides : message clair, pas de silence ----------------
clear()
for nm,x in (("S1",-3),("S2",3)):
    me=bpy.data.meshes.new(nm); bm=bmesh.new(); bmesh.ops.create_cube(bm,size=2); bm.to_mesh(me); bm.free()
    q=bpy.data.objects.new(nm,me); C.scene.collection.objects.link(q); q.location=(x,0,0)
C.view_layer.update(); m.cmd_notice_clear()
r,o=drive([],first='RET')
note=m.cmd_notice_text() or ""
chk("deux solides fermés : la commande dit pourquoi elle ne démarre pas, et quoi faire (Extract Surface)", 'CANCELLED' in r and "no open edge" in note and "Extract Surface" in note and any(l=='WARNING' for l,_t in o._reports), (r,note))
m.cmd_notice_clear(); r,o=drive([])
chk("au simple survol (outil armé) : le message s'affiche, sans alerte Blender répétée", "no open edge" in (m.cmd_notice_text() or "") and not o._reports, o._reports)
m.cmd_notice_clear(); o2=make(m.DESSIN_OT_blend_srf)
with contextlib.redirect_stdout(io.StringIO()): r=type(o2).invoke(o2,ctx,ev('MOUSEMOVE','NOTHING',*scr(1,1)))
chk("... et il ne revient pas à chaque mouvement de souris", m.cmd_notice_text() is None, m.cmd_notice_text())

print("RESULTAT", "TOUT OK" if all(res) else f"{res.count(False)} ECHEC(S) sur {len(res)}")
