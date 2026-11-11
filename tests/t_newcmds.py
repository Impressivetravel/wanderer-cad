# Commandes Rhino complémentaires : Pipe, Intersect, Section, Contour, ExtractSrf, DupBorder, DupEdge, MergeAllFaces, Unroll, RebuildSrf, Orient
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
src=open(_os.path.join(_HERE,'t_pushpull.py')).read()
exec(src[src.index("\n")+1:src.index("# ---------------- 1. PushPull")])
import time, numpy as np
from mathutils.bvhtree import BVHTree
def mk(name,bm,loc=(0,0,0),rot=(0,0,0),scale=(1,1,1)):
    me=bpy.data.meshes.new(name); bm.normal_update(); bm.to_mesh(me); bm.free()
    o=bpy.data.objects.new(name,me); C.scene.collection.objects.link(o); o.location=loc; o.rotation_euler=rot; o.scale=scale; C.view_layer.update(); return o
def cyl(seg=64,r=1.0,h=2.0,caps=True,**kw):
    bm=bmesh.new(); bmesh.ops.create_cone(bm,cap_ends=caps,segments=seg,radius1=r,radius2=r,depth=h); return mk("Cyl",bm,**kw)
def ngon_area(n,r): return 0.5*n*r*r*math.sin(2*math.pi/n)
def sel(*objs):
    for q in bpy.data.objects: q.select_set(q in objs)
    C.view_layer.objects.active=objs[0] if objs else None; C.view_layer.update()
def poly(name,pts,closed=False): return m.build_polyline(C,name,[Vector(p) for p in pts],closed)
def solid_of(built):
    V,F,S=built[:3]; bm=bmesh.new(); vs=[bm.verts.new(tuple(p)) for p in V]
    for f in F: bm.faces.new([vs[i] for i in f])
    return mk("P",bm)
def plen(P,closed):
    P=[Vector(p) for p in P]; return sum((b-a).length for a,b in zip(P,P[1:]+(P[:1] if closed else [])))
def chain_len(C_,closed): return plen(C_,closed)
def curve_objs(prefix): return [o for o in bpy.data.objects if o.type=='CURVE' and o.name.startswith(prefix)]
def spl(o): return [( [ (o.matrix_world@Vector(p.co[:3])) for p in s.points], s.use_cyclic_u) for s in o.data.splines]

# ================= Pipe =================
A=ngon_area(48,0.5)
def pipe_case(name,P,closed,tolrel=1e-6,r=0.5):
    clear(); b=m.pipe_mesh(np.array(P,dtype=float),closed,r,48,True)
    o=solid_of(b); s=stats(o); L=plen(P,closed); exp=ngon_area(48,r)*L
    chk(name, solid_ok(s) and abs(s["vol"]-exp)/exp<tolrel, (s,exp)); return o
o=pipe_case("Pipe droit : volume = section x longueur, solide fermé",[(0,0,0),(4,0,0)],False)
o=pipe_case("Pipe en L (onglet à 90°) : volume = section x longueur de l'axe",[(0,0,0),(4,0,0),(4,3,0)],False)
d1=[min(math.hypot(v.co.y,v.co.z) if v.co.x<=4+1e-9 else 9, math.hypot(v.co.x-4,v.co.z)) for v in o.data.vertices]
chk("... tous les sommets à r=0,5 d'un des deux axes (onglet exact)", max(abs(x-0.5) for x in d1)<1e-6, (min(d1),max(d1)))
pipe_case("Pipe fermé sur un rectangle 4x3",[(0,0,0),(4,0,0),(4,3,0),(0,3,0)],True)
pipe_case("Pipe en zigzag 3D (ouvert, non plan)",[(0,0,0),(2,0,0),(2,2,1),(4,2,1),(4,0,3)],False)
circ=[(2*math.cos(2*math.pi*i/96),2*math.sin(2*math.pi*i/96),0) for i in range(96)]
pipe_case("Pipe sur un cercle (96 points) : tore fermé",circ,True)
pipe_case("Pipe fermé non plan (torsion répartie)",[(0,0,0),(4,0,0),(4,3,1),(0,3,2),(-1,1,3)],True,tolrel=2e-3)
chk("Pipe : rayon nul ou un seul point -> rien", m.pipe_mesh(np.array([(0,0,0),(1,0,0)],dtype=float),False,0.0) is None and m.pipe_mesh(np.array([(0,0,0),(0,0,0)],dtype=float),False,1.0) is None)
clear(); c=poly("L",[(0,0,0),(4,0,0),(4,3,0)]); sel(c)
r=bpy.ops.dessin.pipe(radius=0.5); pp_=[q for q in bpy.data.objects if q.name.startswith("Pipe")]
s=stats(pp_[0]) if pp_ else {}
chk("commande Pipe sur une polyligne : objet créé, sélectionné, solide fermé au bon volume", 'FINISHED' in r and len(pp_)==1 and pp_[0].select_get() and solid_ok(s) and abs(s["vol"]-ngon_area(48,0.5)*7)<1e-5, (r,s))
ns_=sum(1 for e in pp_[0].data.edges if e.use_edge_sharp) if pp_ else 0
chk("... l'onglet à 90° est marqué en arête vive (48 arêtes), pas le reste", ns_==48, ns_)
clear(); poly("L",[(0,0,0),(4,0,0),(4,3,0)]); C.view_layer.update()
def run_pipe(): sel(bpy.data.objects["L"]); bpy.ops.dessin.pipe(radius=0.5)
undo_redo("Pipe", run_pipe)
big=[(i*0.01,math.sin(i*0.02),math.cos(i*0.013)) for i in range(5000)]
t=time.perf_counter(); b=m.pipe_mesh(np.array(big),False,0.05,48,True); dt=time.perf_counter()-t
chk("Pipe sur 5000 points (240 000 faces) en moins de 3 s", b is not None and dt<3.0, round(dt,2))

# ================= Intersect =================
def near(o):
    bm=bmesh.new(); bm.from_mesh(o.data); bm.transform(o.matrix_world); t=BVHTree.FromBMesh(bm); return t,bm
clear(); a=box(size=4,loc=(0,0,2),name="A"); b=box(size=4,loc=(2,2,4),name="B")
ch,pts=m.intersect_objects(C,[a,b])
ta,ba=near(a); tb,bb=near(b)
dmax=max(max(ta.find_nearest(Vector(p))[3],tb.find_nearest(Vector(p))[3]) for c_,_ in ch for p in c_) if ch else 9
chk("Intersect de deux boîtes : une boucle fermée de 6 sommets, sur les deux surfaces", len(ch)==1 and ch[0][1] and len(ch[0][0])==6 and dmax<1e-6 and not pts, ([ (len(c_),cl) for c_,cl in ch],dmax))
ba.free(); bb.free()
chk("... longueur de la boucle = 6 x 2", ch and abs(chain_len(ch[0][0],True)-12)<1e-6, chain_len(ch[0][0],True) if ch else None)
clear(); bm=bmesh.new(); bmesh.ops.create_uvsphere(bm,u_segments=48,v_segments=24,radius=2.0); sp=mk("S",bm)
bm=bmesh.new(); bmesh.ops.create_grid(bm,x_segments=3,y_segments=3,size=4); pl=mk("Pl",bm,loc=(0,0,1))
ch,pts=m.intersect_objects(C,[sp,pl]); ts,bs=near(sp)
ok=len(ch)==1 and ch[0][1] and all(abs(p[2]-1)<1e-6 and ts.find_nearest(Vector(p))[3]<1e-6 for p in ch[0][0])
rr=[math.hypot(p[0],p[1]) for p in ch[0][0]] if ch else [0]
chk("Intersect sphère / plan : un cercle fermé à z=1, sur la sphère, rayon ≈ √3", ok and abs(max(rr)-math.sqrt(3))<0.01, (len(ch),min(rr),max(rr)))
bs.free()
clear(); a=box(size=4,loc=(0,0,2),name="A"); l=poly("Ln",[(-5,0,2),(5,0,2)])
ch,pts=m.intersect_objects(C,[a,l]); xs=sorted(round(float(p[0]),6) for p in pts)
chk("Intersect courbe / solide : deux points exacts (x = -2 et 2)", not ch and xs==[-2.0,2.0] and all(abs(p[1])<1e-6 and abs(p[2]-2)<1e-6 for p in pts), xs)
clear(); l1=poly("L1",[(-1,0,0),(1,0,0)]); l2=poly("L2",[(0,-1,0),(0,1,0)])
ch,pts=m.intersect_objects(C,[l1,l2])
chk("Intersect de deux droites : un point à l'origine", len(pts)==1 and np.linalg.norm(pts[0])<1e-9, pts)
clear(); l1=poly("L1",[(-1,0,0),(1,0,0)]); l2=poly("L2",[(-2,0,0),(3,0,0)])
ch,pts=m.intersect_objects(C,[l1,l2]); chk("deux droites confondues : aucun point parasite", not pts and not ch, pts)
clear(); a=box(size=4,loc=(0,0,2),name="A"); bm=bmesh.new(); bmesh.ops.create_grid(bm,x_segments=2,y_segments=2,size=5); pl=mk("Pl",bm,loc=(0,0,0))
ch,pts=m.intersect_objects(C,[a,pl])
chk("Intersect d'une boîte posée sur un plan (contact sans traversée) : le contour de sa base, fermé, 4 sommets", len(ch)==1 and ch[0][1] and len(ch[0][0])==4 and abs(chain_len(ch[0][0],True)-16)<1e-6, [(len(c_),cl) for c_,cl in ch])
clear(); a=box(size=2,loc=(0,0,1),name="A"); b=box(size=2,loc=(10,0,1),name="B"); sel(a,b)
r=bpy.ops.dessin.intersect(); chk("Intersect sans rencontre : annulé, rien n'est créé", 'CANCELLED' in r and len(bpy.data.objects)==2, r)
clear(); a=box(size=4,loc=(0,0,2),name="A"); b=box(size=4,loc=(2,2,4),name="B"); C.view_layer.update()
def run_int(): sel(bpy.data.objects["A"],bpy.data.objects["B"]); bpy.ops.dessin.intersect()
undo_redo("Intersect", run_int)
clear(); bm=bmesh.new(); bmesh.ops.create_icosphere(bm,subdivisions=5,radius=2.0); s1=mk("I1",bm)
bm=bmesh.new(); bmesh.ops.create_icosphere(bm,subdivisions=5,radius=2.0); s2=mk("I2",bm,loc=(1.5,0.4,0.3))
t=time.perf_counter(); ch,pts=m.intersect_objects(C,[s1,s2]); dt=time.perf_counter()-t
chk("Intersect de deux sphères de 20 480 faces : une boucle fermée, en moins de 2 s", len(ch)==1 and ch[0][1] and dt<2.0, (len(ch),round(dt,2)))

# ================= Section / Contour =================
clear(); a=box(size=4,loc=(0,0,2),name="A")
def cut(objs,no,c):
    sl=m._Slicer(C,objs); sl.set_normal(no); return sl.cut(c)
for z,lab in ((1.0,"au milieu"),(0.0,"posé sur la face du dessous"),(4.0,"posé sur la face du dessus")):
    ch,pts=cut([a],(0,0,1),z)
    chk(f"coupe d'une boîte par un plan horizontal {lab} : un rectangle fermé de 4 sommets, périmètre 16", len(ch)==1 and ch[0][1] and len(ch[0][0])==4 and abs(chain_len(ch[0][0],True)-16)<1e-6 and all(abs(p[2]-z)<1e-9 for p in ch[0][0]), [(len(c_),cl) for c_,cl in ch])
ch,pts=cut([a],(0,0,1),5.0); chk("plan hors de l'objet : rien", not ch and not pts)
clear(); cy=cyl(); ch,pts=cut([cy],(1,0,0),0.5)
w=max(p[1] for p in ch[0][0])-min(p[1] for p in ch[0][0]) if ch else 0
chk("coupe d'un cylindre par un plan vertical : rectangle fermé de 4 sommets, hauteur 2", len(ch)==1 and ch[0][1] and len(ch[0][0])==4 and abs(w-2*math.sqrt(0.75))<0.01, (len(ch),w))
clear(); bm=bmesh.new(); bmesh.ops.create_cone(bm,cap_ends=True,segments=64,radius1=1,radius2=1,depth=2); t1=mk("T",bm)
bm=bmesh.new()
for i in range(48):
    for j in range(24):
        pass
bm.free()
import bpy as _b
clear(); _b.ops.mesh.primitive_torus_add(major_radius=2,minor_radius=0.5,major_segments=48,minor_segments=24); to=C.object; C.view_layer.update()
ch,pts=cut([to],(0,1,0),0.0)
chk("coupe d'un tore par un plan passant par son axe : deux boucles fermées", len(ch)==2 and all(cl for _c,cl in ch), [(len(c_),cl) for c_,cl in ch])
clear(); l=poly("Ln",[(-5,0,2),(5,0,2),(5,3,2)]); ch,pts=cut([l],(1,0,0),1.0)
chk("coupe d'une courbe : un point exact", not ch and len(pts)==1 and np.linalg.norm(pts[0]-np.array((1,0,2)))<1e-9, pts)
clear(); a=box(size=4,loc=(0,0,2),name="A"); sel(a); m._LAST_TYPED.clear()
o,r=start(m.DESSIN_OT_contour); r=E(o,('c',0,0),('c',5,0),('m',1,0),('t','1'),'RET')
cs=curve_objs("Contour"); xs=sorted(round(spl(c_)[0][0][0].x,6) for c_ in cs)
okc=all(len(spl(c_))==1 and spl(c_)[0][1] and len(spl(c_)[0][0])==4 and abs(plen(spl(c_)[0][0],True)-16)<1e-5 for c_ in cs)
chk("outil Contour sur une boîte (base, direction X, distance 1 tapée) : 5 rectangles à x = -2..2", xs==[-2.0,-1.0,0.0,1.0,2.0] and okc, (r,xs,okc))
clear(); a=box(size=4,loc=(0,0,2),name="A"); sel(a)
o,r=start(m.DESSIN_OT_contour); r=E(o,('c',0,0),('c',5,0),('m',1,0),'RET')
chk("Contour : Entrée reprend la dernière distance (5 courbes)", len(curve_objs("Contour"))==5, len(curve_objs("Contour")))
clear(); a=box(size=4,loc=(0,0,2),name="A"); sel(a)
o,r=start(m.DESSIN_OT_section); r=E(o,('c',-5,0),('c',5,0))
cs=curve_objs("Section"); S_=spl(cs[0]) if cs else []
chk("outil Section : ligne de (-5,0) à (5,0) -> rectangle 4x4 dans le plan y=0", len(cs)==1 and len(S_)==1 and S_[0][1] and len(S_[0][0])==4 and all(abs(p.y)<1e-6 for p in S_[0][0]) and abs(plen(S_[0][0],True)-16)<1e-5, (r,[(len(x[0]),x[1]) for x in S_]))
clear(); o,r=start(m.DESSIN_OT_section)
chk("Section sans sélection : refusée avec un message", 'CANCELLED' in r and o._reports, (r,o._reports))
clear(); box(size=4,loc=(0,0,2),name="A"); C.view_layer.update()
def run_con():
    sel(bpy.data.objects["A"]); o,r=start(m.DESSIN_OT_contour); E(o,('c',0,0),('c',5,0),('m',1,0),('t','1'),'RET')
undo_redo("Contour", run_con)
clear(); bm=bmesh.new(); bmesh.ops.create_icosphere(bm,subdivisions=6,radius=2.0); s1=mk("I1",bm)
t=time.perf_counter(); sl=m._Slicer(C,[s1]); sl.set_normal((0,0,1)); n=sum(len(sl.cut(-2+4*k/101)[0]) for k in range(1,101)); dt=time.perf_counter()-t
chk("100 coupes d'une sphère de 81 920 faces en moins de 8 s", n==100 and dt<8.0, (n,round(dt,2)))

# ================= ExtractSrf =================
clear(); a=box(size=4,loc=(0,0,2),name="A"); top=face_at(a,1,4.0)
new,msg=m.extract_face(C,a,top,False); C.view_layer.update()
nk=sum(1 for e in a.data.edges) ; s=stats(a)
chk("ExtractSrf sur le dessus d'une boîte : une surface d'aire 16, la boîte garde 5 faces et un bord libre de 4 arêtes", new is not None and len(new.data.polygons)==1 and abs(new.data.polygons[0].area-16)<1e-6 and len(a.data.polygons)==5 and s["naked"]==4, (msg,s))
chk("... la surface extraite est à la même place (z=4)", new is not None and all(abs((new.matrix_world@v.co).z-4)<1e-6 for v in new.data.vertices))
clear(); a=box(size=4,loc=(0,0,2),name="A"); new,msg=m.extract_face(C,a,face_at(a,1,4.0),True)
chk("ExtractSrf en copie : la boîte reste un solide fermé de 6 faces", new is not None and len(a.data.polygons)==6 and solid_ok(stats(a)))
clear(); cy=cyl(); side=[p.index for p in cy.data.polygons if abs(p.normal.z)<0.5][0]
new,msg=m.extract_face(C,cy,side,False)
chk("ExtractSrf sur le flanc d'un cylindre : les 64 facettes d'un coup, il reste les 2 bouchons", new is not None and len(new.data.polygons)==64 and len(cy.data.polygons)==2, (msg,len(cy.data.polygons)))
clear(); bm=bmesh.new(); bmesh.ops.create_grid(bm,x_segments=3,y_segments=3,size=2); pl=mk("Pl",bm)
new,msg=m.extract_face(C,pl,0,False); chk("ExtractSrf sur une surface seule : refusé avec un message", new is None and msg, msg)
def tool(cls,evs):
    o=make(cls); r=None
    with contextlib.redirect_stdout(io.StringIO()):
        r=type(o).invoke(o,ctx,ev('NONE','NOTHING',*scr(0,0)))
        for e in evs:
            if e[0]=='c': seq=[ev('MOUSEMOVE','NOTHING',*scr(e[1],e[2])),ev('LEFTMOUSE','PRESS',*scr(e[1],e[2])),ev('LEFTMOUSE','RELEASE',*scr(e[1],e[2]))]
            elif e[0]=='m': seq=[ev('MOUSEMOVE','NOTHING',*scr(e[1],e[2]))]
            else: seq=[ev(e[0],'PRESS',*scr(0,0))]
            for x in seq:
                r=type(o).modal(o,ctx,x)
                if 'FINISHED' in r or 'CANCELLED' in r: return r,o
    return r,o
clear(); a=box(size=4,loc=(0,0,2),name="A"); C.view_layer.update()
r,o=tool(m.DESSIN_OT_extract_srf,[('m',0.5,0.5)]); nl=len(o.lines)//2
r2=type(o).modal(o,ctx,ev('LEFTMOUSE','PRESS',*scr(0.5,0.5))); r3=type(o).modal(o,ctx,ev('RET','PRESS',*scr(0,0)))
sf=[q for q in bpy.data.objects if q.name.startswith("Surface")]
chk("outil Extract Surface : survol = contour de la face (4 arêtes), clic = extraction, Entrée = fin", nl==4 and 'FINISHED' in r3 and len(sf)==1 and len(a.data.polygons)==5 and sf[0].select_get(), (nl,r3,len(sf)))
clear(); box(size=4,loc=(0,0,2),name="A"); C.view_layer.update()
undo_redo("Extract Surface", lambda: tool(m.DESSIN_OT_extract_srf,[('c',0.5,0.5),('RET',)]))

# ================= DupBorder / DupEdge =================
clear(); bm=bmesh.new(); bmesh.ops.create_grid(bm,x_segments=4,y_segments=4,size=2); pl=mk("Pl",bm)
ch=m.border_chains(pl)
chk("DupBorder d'une surface plane 4x4 : une boucle fermée de périmètre 16", len(ch)==1 and ch[0][1] and abs(plen(ch[0][0],True)-16)<1e-6, [(len(c_),cl) for c_,cl in ch])
clear(); cy=cyl(caps=False); ch=m.border_chains(cy)
chk("DupBorder d'un cylindre sans bouchons : deux cercles fermés de 64 points", len(ch)==2 and all(cl and len(c_)==64 for c_,cl in ch), [(len(c_),cl) for c_,cl in ch])
clear(); a=box(); sel(a); r=bpy.ops.dessin.dup_border()
chk("DupBorder d'un solide fermé : annulé (pas de bord libre)", 'CANCELLED' in r and len(bpy.data.objects)==1, r)
clear(); cyl(caps=False); C.view_layer.update()
def run_db(): sel(bpy.data.objects["Cyl"]); bpy.ops.dessin.dup_border()
undo_redo("Duplicate Border", run_db)
def fchain(o,pick):
    bm=bmesh.new(); bm.from_mesh(o.data); bm.edges.ensure_lookup_table(); bm.normal_update()
    e=[x for x in bm.edges if pick(x)][0]; ch,cl=m.feature_edge_chain(bm,e); r=(len(ch),cl); bm.free(); return r
clear(); a=box()
chk("DupEdge sur une boîte : une arête = 2 sommets (arrêt aux coins)", fchain(a,lambda e: True)==(2,False), fchain(a,lambda e: True))
clear(); cy=cyl()
chk("DupEdge sur le bord d'un cylindre : le cercle entier (64 points, fermé)", fchain(cy,lambda e: abs(e.verts[0].co.z-1)<1e-6 and abs(e.verts[1].co.z-1)<1e-6)==(64,True))
clear(); bm=bmesh.new(); bmesh.ops.create_grid(bm,x_segments=4,y_segments=4,size=2); pl=mk("Pl",bm)
chk("DupEdge sur le bord d'une surface plane : un côté entier (5 points), pas tout le tour", fchain(pl,lambda e: len(e.link_faces)==1)==(5,False), fchain(pl,lambda e: len(e.link_faces)==1))
clear(); a=box(size=4,loc=(0,0,2),name="A"); C.view_layer.update()
r,o=tool(m.DESSIN_OT_dup_edge,[('m',1.8,0.3)]); nl=len(o.lines)//2
type(o).modal(o,ctx,ev('LEFTMOUSE','PRESS',*scr(1.8,0.3))); r3=type(o).modal(o,ctx,ev('RET','PRESS',*scr(0,0)))
ed=curve_objs("Edge"); P=spl(ed[0])[0][0] if ed else []
chk("outil Duplicate Edge : clic près de l'arête x=2 du dessus -> courbe de (2,-2,4) à (2,2,4)", nl==1 and 'FINISHED' in r3 and len(ed)==1 and len(P)==2 and all(abs(p.x-2)<1e-6 and abs(p.z-4)<1e-6 for p in P) and abs((P[1]-P[0]).length-4)<1e-6, (nl,r3,[tuple(p) for p in P]))

# ================= MergeAllFaces =================
def dense_box(cuts=5,size=4,loc=(0,0,2)):
    bm=bmesh.new(); bmesh.ops.create_cube(bm,size=size); bmesh.ops.subdivide_edges(bm,edges=bm.edges[:],cuts=cuts,use_grid_fill=True); return mk("D",bm,loc=loc)
clear(); d=dense_box(); n0,n1=m.merge_coplanar_faces(d); s=stats(d)
chk("MergeAllFaces sur une boîte subdivisée (216 faces) : 6 faces, 8 sommets, volume 64, solide fermé", (n0,n1)==(216,6) and len(d.data.vertices)==8 and abs(s["vol"]-64)<1e-5 and solid_ok(s), (n0,n1,len(d.data.vertices),s))
clear(); a=box(size=4,loc=(0,0,2)); imprint_square(a,4.0); n0=len(a.data.polygons); r0,r1=m.merge_coplanar_faces(a); s=stats(a)
chk("MergeAllFaces efface une découpe (Offset Edge / PushPull) : retour à 6 faces", r1==6 and n0>6 and solid_ok(s) and abs(s["vol"]-64)<1e-5, (n0,r0,r1))
clear(); a=box(size=4,loc=(0,0,2),name="A"); b=box(size=4,loc=(4,0,2),name="B"); out,_e=m.run_boolean('UNION',[a,b],[],True); u=out[0]
n0,n1=m.merge_coplanar_faces(u); s=stats(u)
chk("MergeAllFaces après l'union de deux boîtes accolées : 6 faces, volume 128", n1==6 and abs(s["vol"]-128)<1e-5 and solid_ok(s), (n0,n1,s))
clear(); cy=cyl(); sel(cy); r=bpy.ops.dessin.merge_faces()
chk("MergeAllFaces sur un cylindre : rien à réunir (les facettes courbes restent)", 'CANCELLED' in r and len(cy.data.polygons)==66, (r,len(cy.data.polygons)))
clear(); dense_box(); C.view_layer.update()
def run_mf(): sel(bpy.data.objects["D"]); bpy.ops.dessin.merge_faces()
undo_redo("Merge All Faces", run_mf)

# ================= Unroll =================
def flat_stats(o,pts,faces):
    P=[Vector((x,y,0)) for x,y in pts]
    ar=[]; pe=[]
    for f in faces:
        q=[P[i] for i in f]; ar.append(abs(sum((q[i].x*q[(i+1)%len(q)].y-q[(i+1)%len(q)].x*q[i].y) for i in range(len(q))))/2); pe.append(sum((q[(i+1)%len(q)]-q[i]).length for i in range(len(q))))
    bm=bmesh.new(); bm.from_mesh(o.data); bm.transform(o.matrix_world)
    a3=sorted(f.calc_area() for f in bm.faces); p3=sorted(f.calc_perimeter() for f in bm.faces); bm.free()
    da=max(abs(x-y) for x,y in zip(sorted(ar),a3)) if len(ar)==len(a3) else 9
    dp=max(abs(x-y) for x,y in zip(sorted(pe),p3)) if len(pe)==len(p3) else 9
    xs=[p[0] for p in pts]; ys=[p[1] for p in pts]
    return da,dp,(max(xs)-min(xs),max(ys)-min(ys)),sum(ar)
clear(); cy=cyl(caps=False); pts,faces,info=m.unroll_mesh(cy); da,dp,dim,ar=flat_stats(cy,pts,faces)
Wd=64*2*math.sin(math.pi/64)
chk("Unroll d'un flanc de cylindre : rectangle (périmètre du 64-gone) x 2, chaque facette garde aire et périmètre", da<1e-6 and dp<1e-6 and sorted(round(x,5) for x in dim)==sorted([round(Wd,5),2.0]), (da,dp,dim,Wd))
clear(); bm=bmesh.new(); bmesh.ops.create_cone(bm,cap_ends=False,segments=48,radius1=1.5,radius2=0.0,depth=2.0); co=mk("Cone",bm)
pts,faces,info=m.unroll_mesh(co); da,dp,dim,ar=flat_stats(co,pts,faces) if pts else (9,9,None,0)
sl_=math.hypot(1.5,2.0); ap=[p for p in pts if sum(1 for q in pts if abs(q[0]-p[0])<1e-9 and abs(q[1]-p[1])<1e-9)>=1] if pts else []
rad=sorted({round(math.hypot(p[0]-pts[faces[0][[i for i in range(3)][0]]][0],p[1]-pts[faces[0][0]][1]),4) for p in pts}) if pts else []
chk("Unroll d'un cône : secteur plat, aires et périmètres des 48 triangles conservés", pts is not None and da<1e-6 and dp<1e-5 and abs(ar-info)<1e-5, (da,dp,ar,info))
clear(); a=box(); pts,faces,info=m.unroll_mesh(a); da,dp,dim,ar=flat_stats(a,pts,faces)
chk("Unroll d'une boîte : patron de 6 faces, aire 96, 14 sommets (croix)", len(faces)==6 and abs(ar-96)<1e-5 and da<1e-6, (len(faces),ar,len(pts)))
clear(); bm=bmesh.new(); bmesh.ops.create_uvsphere(bm,u_segments=32,v_segments=16,radius=2.0); sp=mk("S",bm)
pts,faces,info=m.unroll_mesh(sp); chk("Unroll d'une sphère : refusé (non développable) avec un message", pts is None and "developable" in info, info)
clear(); bm=bmesh.new(); bmesh.ops.create_uvsphere(bm,u_segments=256,v_segments=128,radius=2.0); sp=mk("S",bm)
pts,faces,info=m.unroll_mesh(sp); chk("... même une sphère très fine (32 512 faces) est refusée", pts is None, info if pts is None else len(pts))
clear(); cy=cyl(caps=False,rot=(0.3,0.2,0.5),loc=(3,1,2),scale=(2,2,1)); sel(cy); r=bpy.ops.dessin.unroll()
un=[q for q in bpy.data.objects if q.name.startswith("Unrolled")]
ok=len(un)==1 and all(abs((un[0].matrix_world@v.co).z)<1e-6 for v in un[0].data.vertices)
a2=sum(p.area for p in un[0].data.polygons) if un else 0
bm=bmesh.new(); bm.from_mesh(cy.data); bm.transform(cy.matrix_world); a3=sum(f.calc_area() for f in bm.faces); bm.free()
chk("commande Unroll (objet tourné, à l'échelle) : patron à plat sur le plan de construction, aire monde conservée, 64 faces soudées", 'FINISHED' in r and ok and abs(a2-a3)<1e-4 and len(un[0].data.polygons)==64 and len(un[0].data.vertices)==130, (r,a2,a3,len(un[0].data.vertices) if un else None))
clear(); cyl(caps=False); C.view_layer.update()
def run_un(): sel(bpy.data.objects["Cyl"]); bpy.ops.dessin.unroll()
undo_redo("Unroll", run_un)

# ================= RebuildSrf =================
clear(); bm=bmesh.new(); bmesh.ops.create_grid(bm,x_segments=4,y_segments=4,size=2); pl=mk("Pl",bm)
dev,msg=m.rebuild_surface(pl,9,3); C.view_layer.update()
bb=[v.co for v in pl.data.vertices]
chk("RebuildSrf d'un plan 5x5 en 9x3 : 27 sommets, 16 faces, toujours plan et de même taille, écart nul", msg=="" and len(pl.data.vertices)==27 and len(pl.data.polygons)==16 and max(abs(c.z) for c in bb)<1e-6 and abs(max(c.x for c in bb)-2)<1e-6 and abs(min(c.y for c in bb)+2)<1e-6 and dev<1e-6, (msg,dev,len(pl.data.vertices)))
def vault(seg=32,r=2.0,h=3.0):
    bm=bmesh.new()
    ring=[(r*math.cos(math.pi*i/seg),r*math.sin(math.pi*i/seg)) for i in range(seg+1)]
    lo=[bm.verts.new((x,0,z)) for x,z in ring]; hi=[bm.verts.new((x,h,z)) for x,z in ring]
    for i in range(seg): bm.faces.new([lo[i],hi[i],hi[i+1],lo[i+1]])
    return mk("Vault",bm)
clear(); v=vault(); n_ref=Vector(v.data.polygons[0].normal); dev,msg=m.rebuild_surface(v,17,5)
R=[math.hypot(c.co.x,c.co.z) for c in v.data.vertices]
chk("RebuildSrf d'une voûte en 17x5 : sommets sur le cylindre (à 0,001 près), coins exacts, écart rapporté petit, normales gardées", msg=="" and len(v.data.vertices)==85 and max(abs(x-2) for x in R)<1e-3 and dev<0.02 and v.data.polygons[0].normal.dot(n_ref)>0.9 and abs(max(c.co.y for c in v.data.vertices)-3)<1e-6, (msg,dev,min(R),max(R)))
clear(); cy=cyl(caps=False); dev,msg=m.rebuild_surface(cy,32,4); s=stats(cy)
R=[math.hypot(c.co.x,c.co.y) for c in cy.data.vertices]
chk("RebuildSrf d'un tube fermé en 32x4 : 128 sommets, 96 faces, 2 bords libres de 32, rayon gardé", msg=="" and len(cy.data.vertices)==128 and len(cy.data.polygons)==96 and s["naked"]==64 and max(abs(x-1) for x in R)<1e-3, (msg,dev,s["naked"],min(R),max(R)))
clear(); cy=cyl(); dev,msg=m.rebuild_surface(cy,8,8)
chk("RebuildSrf d'un solide (pas une grille) : refusé avec un message, objet intact", dev is None and msg and len(cy.data.polygons)==66, msg)
clear(); vault(); C.view_layer.update()
def run_rb(): sel(bpy.data.objects["Vault"]); bpy.ops.dessin.rebuild_srf(count_u=9,count_v=3)
undo_redo("Rebuild Surface", run_rb)

# ================= Orient =================
# (la boîte est loin des points cliqués : ils ne s'accrochent pas à elle)
clear(); b=box(size=2,loc=(-20,-20,1)); sel(b)
o,r=start(m.DESSIN_OT_orient); r=E(o,('c',0,0),('c',2,0),('c',10,0),('c',10,5)); C.view_layer.update()
M=b.matrix_world; xa=(M.to_3x3()@Vector((1,0,0)))
chk("Orient : (0,0)-(2,0) vers (10,0)-(10,5) -> déplacé et tourné de 90° autour du point de référence, taille gardée", 'FINISHED' in r and (M.translation-Vector((30,-20,1))).length<1e-4 and (xa-Vector((0,1,0))).length<1e-5, (tuple(M.translation),tuple(xa)))
clear(); b=box(size=2,loc=(-20,-20,1)); sel(b)
o,r=start(m.DESSIN_OT_orient); r=E(o,'D',('c',0,0),('c',2,0),('c',10,0),('c',10,5)); C.view_layer.update()
xa=(b.matrix_world.to_3x3()@Vector((1,0,0)))
chk("Orient + D (échelle) : facteur 5/2 = 2,5", abs(xa.length-2.5)<1e-5 and (b.matrix_world.translation-Vector((60,-50,2.5))).length<1e-3, (xa.length,tuple(b.matrix_world.translation)))
clear(); b=box(size=2,loc=(-20,-20,1)); sel(b)
o,r=start(m.DESSIN_OT_orient); r=E(o,'C',('c',0,0),('c',2,0),('c',10,0),('c',10,5)); C.view_layer.update()
cp=[q for q in bpy.data.objects if q is not b]
chk("Orient + C (copie) : l'original reste, une copie est orientée", len(cp)==1 and (b.matrix_world.translation-Vector((-20,-20,1))).length<1e-6 and (cp[0].matrix_world.translation-Vector((30,-20,1))).length<1e-4, len(bpy.data.objects))
clear(); b=box(size=2,loc=(-20,-20,1)); sel(b)
o,r=start(m.DESSIN_OT_orient); r=E(o,('c',0,0),('c',2,0),('c',10,0),'ESC'); C.view_layer.update()
chk("Orient puis Échap avant la fin : l'objet revient à sa place", (b.matrix_world.translation-Vector((-20,-20,1))).length<1e-6 and len(bpy.data.objects)==1, tuple(b.matrix_world.translation))
clear(); box(size=2,loc=(-20,-20,1)); C.view_layer.update()
def run_or(): sel(bpy.data.objects["Box"]); o,r=start(m.DESSIN_OT_orient); E(o,('c',0,0),('c',2,0),('c',10,0),('c',10,5))
undo_redo("Orient", run_or)
# ---------------- boutons de la barre d'outils et icônes des 11 commandes ----------------
_tt={"pipe":"dessin.pipe","intersect":"dessin.intersect","section":"dessin.section","contour":"dessin.contour","extract_srf":"dessin.extract_srf",
     "dup_border":"dessin.dup_border","dup_edge":"dessin.dup_edge","merge_faces":"dessin.merge_faces","unroll":"dessin.unroll",
     "rebuild_srf":"dessin.rebuild_srf","orient":"dessin.orient"}
_all=[c for g in m.RHINO_TOOLS.values() for c in g]
chk("11 boutons, chacun avec son icône dessinée et sa commande", len(_all)==11 and sorted(c.dessin_icon for c in _all)==sorted(_tt)
    and all(m.svg_icon_bytes(c.dessin_icon) for c in _all) and all(any(k[0]==_tt[c.dessin_icon] for k in c.bl_keymap) for c in _all),
    [(c.__name__,c.dessin_icon) for c in _all])
chk("chaque icône appartient à une famille de couleurs", all(any(k in f for f in m.ICON_FAMILIES) for k in _tt), None)
from bl_ui.space_toolsystem_toolbar import VIEW3D_PT_tools_active as _TB
def _ids(mode):
    out=[]
    def walk(it):
        if it is None: return
        if hasattr(it,"idname"): out.append(it.idname)
        elif isinstance(it,(tuple,list)):
            for q in it: walk(q)
    walk(list(_TB._tools[mode])); return out
_o=_ids('OBJECT'); _e=_ids('EDIT_MESH')
chk("les 11 boutons sont dans la barre d'outils du mode Objet, une seule fois chacun", "dessin.untrim_tool" in _o and all(_o.count(c.bl_idname)==1 for c in _all), [c.bl_idname for c in _all if _o.count(c.bl_idname)!=1])
chk("... et dans celle du mode Édition (variante)", sum(1 for c in _all if any(i and i.startswith(c.bl_idname) for i in _e))==11, [i for i in _e if i and ("pipe" in i or "orient" in i)])
m.unregister(); _o2=_ids('OBJECT')
chk("désactiver l'add-on retire les 11 boutons", not any(c.bl_idname in _o2 for c in _all), [c.bl_idname for c in _all if c.bl_idname in _o2])
m.register()
chk("Auto CPlane est désactivé par défaut (comme Rhino)", C.scene.dessin.auto_cplane is False and C.scene.dessin.bl_rna.properties["auto_cplane"].default is False, C.scene.dessin.auto_cplane)
# ---------------- boutons : lancement sans sélection (Section / Contour) et clic de lancement (Extract Surface) ----------------
clear(); b=box(size=2,loc=(0,0,1)); C.view_layer.update()
for q in bpy.data.objects: q.select_set(False)
def _mk():
    o=make(m.DESSIN_OT_section); type(o).active_dessin_tool=classmethod(lambda cls,c: "dessin.section_tool"); type(o).active_tool_id=staticmethod(lambda c: "dessin.section_tool"); return o
if True:
    o=_mk()
    with contextlib.redirect_stdout(io.StringIO()): r=type(o).invoke(o,ctx,ev('MOUSEMOVE','NOTHING',*scr(0,0)))
    chk("bouton Section sans sélection : le survol ne lance rien et n'affiche aucun message", r=={'CANCELLED','PASS_THROUGH'} and not o._reports, (r,o._reports))
    b.select_set(True); C.view_layer.update()
    o=_mk()
    with contextlib.redirect_stdout(io.StringIO()): r=type(o).invoke(o,ctx,ev('MOUSEMOVE','NOTHING',*scr(3,3)))
    chk("bouton Section avec une sélection : l'outil s'arme au survol", 'RUNNING_MODAL' in r, r)
    E(o,('c',-3,0),('c',3,0)); C.view_layer.update()
    crv=[q for q in bpy.data.objects if q.type=='CURVE']
    chk("... et deux clics donnent la section (rectangle 2 x 2)", len(crv)==1 and abs(crv[0].dimensions.x-2)<1e-6 and abs(max(crv[0].dimensions.y,crv[0].dimensions.z)-2)<1e-6, [tuple(q.dimensions) for q in crv])
print("RESULTAT",sum(res),"/",len(res))
