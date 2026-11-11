# Booléens (Union, Difference, Intersection, Split) : volumes mesurés, solides fermés, maillages denses, faces coplanaires
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
src=open(_os.path.join(_HERE,'t_pushpull.py')).read()
exec(src[src.index("\n")+1:src.index("# ---------------- 1. PushPull")])
import time
def prim(kind, name, loc=(0,0,0), rot=(0,0,0), scale=(1,1,1), **kw):
    me=bpy.data.meshes.new(name); bm=bmesh.new()
    if kind=='box': bmesh.ops.create_cube(bm,size=kw.get('size',2))
    elif kind=='cyl': bmesh.ops.create_cone(bm,cap_ends=True,segments=kw.get('seg',32),radius1=kw.get('r',1),radius2=kw.get('r',1),depth=kw.get('h',2))
    elif kind=='sph': bmesh.ops.create_uvsphere(bm,u_segments=kw.get('u',32),v_segments=kw.get('v',16),radius=kw.get('r',1))
    elif kind=='ico': bmesh.ops.create_icosphere(bm,subdivisions=kw.get('sub',4),radius=kw.get('r',1))
    elif kind=='grid': bmesh.ops.create_grid(bm,x_segments=kw.get('n',4),y_segments=kw.get('n',4),size=kw.get('size',2))
    bm.to_mesh(me); bm.free()
    o=bpy.data.objects.new(name,me); C.scene.collection.objects.link(o); o.location=loc; o.rotation_euler=rot; o.scale=scale
    C.view_layer.update(); return o
def vol(o): return stats(o)["vol"]
def copy(o):
    c=o.copy(); c.data=o.data.copy(); C.scene.collection.objects.link(c); C.view_layer.update(); return c
def run(kind,A,B=(),delete=True):
    t=time.perf_counter()
    out,err=m.run_boolean(kind,list(A),list(B),delete); C.view_layer.update()
    return out,err,time.perf_counter()-t
def tot(objs): return sum(vol(o) for o in objs)
def allok(objs): return all(solid_ok(stats(o)) for o in objs)

# ---------------- 1. valeurs exactes ----------------
clear(); a=prim('box','A',size=4,loc=(0,0,2)); b=prim('box','B',size=4,loc=(2,2,4))
out,err,_=run('UNION',[a,b]); chk("union de deux boîtes : volume 64+64-8=120, solide fermé", len(out)==1 and abs(vol(out[0])-120)<1e-4 and allok(out), (err,[stats(o) for o in out]))
clear(); a=prim('box','A',size=4,loc=(0,0,2)); b=prim('box','B',size=4,loc=(2,2,4))
out,err,_=run('DIFFERENCE',[a],[b]); chk("différence : 64-8=56", len(out)==1 and abs(vol(out[0])-56)<1e-4 and allok(out), (err,[stats(o) for o in out]))
clear(); a=prim('box','A',size=4,loc=(0,0,2)); b=prim('box','B',size=4,loc=(2,2,4))
out,err,_=run('INTERSECT',[a],[b]); chk("intersection : 8", len(out)==1 and abs(vol(out[0])-8)<1e-4 and allok(out), (err,[stats(o) for o in out]))
clear(); a=prim('box','A',size=4,loc=(0,0,2)); b=prim('box','B',size=4,loc=(2,2,4))
out,err,_=run('SPLIT',[a],[b]); vs=sorted(vol(o) for o in out)
chk("split : deux pièces 8 et 56, l'outil reste", len(out)==2 and abs(vs[0]-8)<1e-4 and abs(vs[1]-56)<1e-4 and allok(out) and "B" in bpy.data.objects, (err,vs))
clear(); a=prim('box','A',size=4,loc=(0,0,2)); b=prim('box','B',size=2,loc=(10,0,1))
out,err,_=run('INTERSECT',[a],[b]); chk("intersection sans recouvrement : message, objets intacts", not out and err and len(bpy.data.objects)==2, err)

# ---------------- 2. faces coplanaires (cas piège des solveurs) ----------------
clear(); a=prim('box','A',size=4,loc=(0,0,2)); b=prim('box','B',size=2,loc=(1,1,3))     # B affleure 3 faces de A
out,err,_=run('DIFFERENCE',[a],[b]); chk("différence, outil affleurant trois faces : 64-8=56", len(out)==1 and abs(vol(out[0])-56)<1e-4 and allok(out), (err,[stats(o) for o in out]))
clear(); a=prim('box','A',size=4,loc=(0,0,2)); b=prim('box','B',size=4,loc=(4,0,2))     # boîtes accolées (face commune)
out,err,_=run('UNION',[a,b]); chk("union de deux boîtes accolées : 128, solide fermé", len(out)==1 and abs(vol(out[0])-128)<1e-4 and allok(out), (err,[stats(o) for o in out]))
clear(); a=prim('box','A',size=4,loc=(0,0,2)); b=prim('box','B',size=4,loc=(0,0,2))
out,err,_=run('UNION',[a,b]); chk("union de deux boîtes identiques superposées : 64", len(out)==1 and abs(vol(out[0])-64)<1e-4 and allok(out), (err,[stats(o) for o in out]))

# ---------------- 3. cohérence sur maillages denses : vol(A∪B)+vol(A∩B)=vol(A)+vol(B), vol(A−B)+vol(A∩B)=vol(A) ----------------
def consistency(name, mk, tol=1e-4):
    clear(); A,B=mk(); vA,vB=tot(A),tot(B)
    r={}
    for kind in ('UNION','DIFFERENCE','INTERSECT'):
        clear(); A,B=mk()
        out,err,dt=(run('UNION',A+B) if kind=='UNION' else run(kind,A,B))
        r[kind]=(tot(out),allok(out) and len(out)>=1,dt,err)
    sc=max(vA,vB,1.0)
    if len(B)>1:      # outils qui se recouvrent : leur volume réel est celui de leur union
        clear(); A,B=mk(); u,_e=m.run_boolean('UNION',B,[],True); vB=tot(u)
    e1=abs(r['UNION'][0]+r['INTERSECT'][0]-vA-vB)/sc; e2=abs(r['DIFFERENCE'][0]+r['INTERSECT'][0]-vA)/sc
    ok=all(r[k][1] for k in r) and e1<tol and e2<tol
    chk(name, ok, dict(vA=vA,vB=vB,e1=round(e1,7),e2=round(e2,7),**{k:(round(v[0],5),v[1],round(v[2],3),v[3]) for k,v in r.items()}))
consistency("sphère 64x32 et boîte", lambda: ([prim('sph','A',u=64,v=32,r=2)],[prim('box','B',size=3,loc=(1,1,1))]))
consistency("cylindre 96 côtés traversant une boîte", lambda: ([prim('box','A',size=4)],[prim('cyl','B',seg=96,r=1,h=6)]))
consistency("cylindre 96 côtés affleurant le dessus et le dessous de la boîte", lambda: ([prim('box','A',size=4)],[prim('cyl','B',seg=96,r=1,h=4)]))
consistency("deux cylindres 128 côtés coaxiaux de même rayon décalés en hauteur (parois confondues)", lambda: ([prim('cyl','A',seg=128,r=1,h=4)],[prim('cyl','B',seg=128,r=1,h=4,loc=(0,0,2))]))
consistency("deux cylindres 128 côtés croisés à 90°", lambda: ([prim('cyl','A',seg=128,r=1,h=6)],[prim('cyl','B',seg=128,r=1,h=6,rot=(math.pi/2,0,0))]))
consistency("deux sphères ico (5 subdivisions) décalées", lambda: ([prim('ico','A',sub=5,r=2)],[prim('ico','B',sub=5,r=2,loc=(1.5,0.5,0.3))]), tol=2e-4)
consistency("objets tournés et à l'échelle non uniforme", lambda: ([prim('box','A',size=4,rot=(0.3,0.5,0.7),scale=(1,0.5,2))],[prim('cyl','B',seg=64,r=1,h=8,rot=(1.1,0.2,0),scale=(1.5,1,1))]))
consistency("deux outils qui se recouvrent (B = 2 objets)", lambda: ([prim('box','A',size=4)],[prim('cyl','B',seg=48,r=1,h=6),prim('cyl','B2',seg=48,r=1,h=6,loc=(0.8,0,0))]))
def pocket():
    a=prim('box','A',size=4,loc=(0,0,2))
    r=m.build_polyline(C,"R",[Vector(p) for p in [(-1,-1,4),(1,-1,4),(1,1,4),(-1,1,4)]],True)
    cut=prim('box','K',size=2,loc=(0,0,3.5)); out,_e=m.run_boolean('DIFFERENCE',[a],[cut],True); bpy.data.objects.remove(r)
    return out
consistency("solide à poche, outil dans le plan des murs de la poche", lambda: (pocket(),[prim('box','B',size=2,loc=(1,0,3))]))
def dense_pocket():
    a=prim('cyl','A',seg=128,r=3,h=4,loc=(0,0,2)); k=prim('cyl','K',seg=128,r=2,h=2,loc=(0,0,3))
    out,_e=m.run_boolean('DIFFERENCE',[a],[k],True); return out
consistency("cylindre creusé (128 côtés), outil cylindrique de même rayon que la poche, décalé en hauteur", lambda: (dense_pocket(),[prim('cyl','B',seg=128,r=2,h=2,loc=(0,0,1.5))]))
consistency("cylindre creusé (128 côtés), boîte dont les faces passent par l'axe", lambda: (dense_pocket(),[prim('box','B',size=3,loc=(1.5,1.5,2.5))]))

def dense_box(cuts=5,size=4,loc=(0,0,2)):
    me=bpy.data.meshes.new("D"); bm=bmesh.new(); bmesh.ops.create_cube(bm,size=size)
    bmesh.ops.subdivide_edges(bm,edges=bm.edges[:],cuts=cuts,use_grid_fill=True); bm.to_mesh(me); bm.free()
    o=bpy.data.objects.new("D",me); C.scene.collection.objects.link(o); o.location=loc; C.view_layer.update(); return o
def exact(name, mk, kind, expect):
    clear(); A,B=mk(); out,err,dt=(run('UNION',A+B) if kind=='UNION' else run(kind,A,B))
    chk(name, len(out)>=1 and abs(tot(out)-expect)<1e-4 and allok(out), (err,round(dt,3),[stats(o) for o in out]))
exact("boîte subdivisée (5 coupes) moins un outil dont les murs sont dans le plan des murs : 64-4x4x0.5=56", lambda: ([dense_box()],[prim('box','B',size=4,loc=(0,0,5.25),scale=(1,1,0.875))]), 'DIFFERENCE', 64-16*0.5)
exact("boîte subdivisée moins une boîte affleurant trois faces : 56", lambda: ([dense_box()],[prim('box','B',size=2,loc=(1,1,3))]), 'DIFFERENCE', 56)
exact("deux boîtes subdivisées (5 et 7 coupes) accolées : union 128", lambda: ([dense_box(5)],[dense_box(7,loc=(4,0,2))]), 'UNION', 128)
exact("deux boîtes subdivisées superposées décalées d'une demi-maille : intersection", lambda: ([dense_box(5)],[dense_box(5,loc=(1/3,0,2))]), 'INTERSECT', (4-1/3)*16)
exact("boîte subdivisée percée de part en part par une boîte aux murs sur des lignes du maillage : 64-(4/3)^2*4", lambda: ([dense_box(5)],[prim('box','B',size=4/3,loc=(0,0,2),scale=(1,1,4))]), 'DIFFERENCE', 64-(4/3)**2*4)

# ---------------- 4. surfaces ouvertes : toujours possibles (solveur Exact) ----------------
clear(); a=prim('grid','A',n=4,size=4); b=prim('box','B',size=2)
out,err,_=run('DIFFERENCE',[a],[b]); s=stats(out[0]) if out else None
bm=bmesh.new(); bm.from_mesh(out[0].data) if out else None; area=sum(f.calc_area() for f in bm.faces); bm.free()
chk("surface plane 8x8 moins une boîte : trou de 2x2 (aire 64-4=60)", len(out)==1 and abs(area-60)<1e-4, (err,area))

# ---------------- 5. trois objets, option garder les originaux ----------------
clear(); a=prim('box','A',size=4); b=prim('box','B',size=4,loc=(2,0,0)); c=prim('box','Cc',size=4,loc=(4,0,0))
out,err,_=run('UNION',[a,b,c],delete=False)
chk("union de trois boîtes, originaux gardés : 128, 4 objets", len(out)==1 and abs(vol(out[0])-128)<1e-4 and allok(out) and len(bpy.data.objects)==4, (err,len(bpy.data.objects)))
print("RESULTAT",sum(res),"/",len(res))
