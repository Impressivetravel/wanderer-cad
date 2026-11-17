import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
import numpy as np
import traceback, json, time
for o in list(bpy.data.objects): bpy.data.objects.remove(o)
C=bpy.context
R=m.build_polyline(C,"Outer",[Vector(p) for p in [(0,0,0),(40,0,0),(40,30,0),(0,30,0)]],True)
H=m.build_polyline(C,"Hole",[Vector(p) for p in [(10,10,0),(20,10,0),(20,20,0),(10,20,0)]],True)
CI=m.build_bezier_arc(C,"Trou",Vector((30,15,0)),Vector((1,0,0)),Vector((0,1,0)),4.0,0.0,m.TAU,True)
C.view_layer.update()
res=[]
def chk(name,ok,info=""):
    res.append(ok); print(("OK  " if ok else "BAD ")+name, info)
# 1) Hatch from curves
for o in C.view_layer.objects: o.select_set(o.name in ("Outer","Hole","Trou"))
st=C.scene.dessin; st.hatch_spacing=1.0
op=make(m.DESSIN_OT_hatch); r=type(op).execute(op,ctx); print(r, op._reports[-1:])
hs=[o for o in bpy.data.objects if m.is_hatch(o)]
chk("1 hatch créée avec 2 trous", len(hs)==1 and len(json.loads(hs[0]["dessin_hatch"])["rings"])==3, [len(json.loads(h["dessin_hatch"])["rings"]) for h in hs])
h=hs[0]; me=h.data
# no edge midpoint inside holes
mw=h.matrix_world
mids=[(mw@((me.vertices[e.vertices[0]].co+me.vertices[e.vertices[1]].co)/2)) for e in me.edges]
inhole=sum(1 for p in mids if 10<p.x<20 and 10<p.y<20) + sum(1 for p in mids if (p.x-30)**2+(p.y-15)**2<3.9**2)
outside=sum(1 for p in mids if not (-1e-6<p.x<40+1e-6 and -1e-6<p.y<30+1e-6))
chk("motif hors des trous et dans le contour", inhole==0 and outside==0 and len(me.edges)>50, (len(me.edges),inhole,outside))
# 2) live edit
n1=len(h.data.edges); h.dessin_hatch.pattern='HATCH2'; n2=len(h.data.edges)
chk("édition motif Hatch2 (≈ x2 lignes)", 1.6<n2/n1<2.4, (n1,n2))
h.dessin_hatch.scale=2.0; n3=len(h.data.edges); chk("échelle 2 (moins de lignes)", n3<n2*0.7,(n2,n3))
h.dessin_hatch.pattern='SOLID'; chk("Solid : faces", len(h.data.polygons)>0 and len(h.data.edges)>0,(len(h.data.polygons),))
area=sum(p.area for p in h.data.polygons); exp=40*30-100-math.pi*16
chk("aire solid = contour - trous", abs(area-exp)<0.02*exp,(round(area,2),round(exp,2)))
for pat in ['HATCH1','HATCH3','DASH','GRID','GRID60','PLUS','SQUARES','BRICK']:
    t=time.time(); h.dessin_hatch.pattern=pat; chk(f"motif {pat}", len(h.data.edges)>0, (len(h.data.edges), f"{time.time()-t:.3f}s"))
# 3) moved object then rebuild keeps position
h.location.x+=100; h.dessin_hatch.rotation=math.radians(30); C.view_layer.update()
xs=[ (h.matrix_world@v.co).x for v in h.data.vertices]; chk("hachure déplacée garde sa position", min(xs)>99.9 and max(xs)<140.1,(round(min(xs),2),round(max(xs),2)))
h.location.x-=100
# 4) multi-select edit
for o in C.view_layer.objects: o.select_set(o.name in ("Outer",))
op=make(m.DESSIN_OT_hatch); type(op).execute(op,ctx)
h2=[o for o in bpy.data.objects if m.is_hatch(o) and o is not h][0]
h.select_set(True); h2.select_set(True); C.view_layer.objects.active=h
h.dessin_hatch.pattern='GRID'; chk("édition multi-sélection", h2.dessin_hatch.pattern=='GRID', h2.dessin_hatch.pattern)
# 5) too dense
try:
    h.dessin_hatch.scale=0.001
    chk("trop dense : pas de plantage", True, h.dessin_hatch.scale)
except Exception as e: chk("trop dense", False, e)
h.dessin_hatch.scale=1.0
# 6) region at point
groups,_=m.hatch_loop_groups(m._hatch_paths_of(C,[R,H,CI]))
rg=m.hatch_region_at(groups,np.array((5,5,50.0)),np.array((0,0,-1.0)))
chk("région au point (5,5): contour + 2 trous", rg is not None and len(rg[4])==3, None if rg is None else len(rg[4]))
rg=m.hatch_region_at(groups,np.array((15,15,50.0)),np.array((0,0,-1.0)))
chk("région au point dans le trou carré", rg is not None and len(rg[4])==1 and abs(m._poly_area2(rg[4][0])-100)<1e-6, None if rg is None else m._poly_area2(rg[4][0]))
rg=m.hatch_region_at(groups,np.array((60,5,50.0)),np.array((0,0,-1.0)))
chk("hors de toute zone : rien", rg is None)
# 7) boundary, match, explode
for o in C.view_layer.objects: o.select_set(False)
h.select_set(True)
op=make(m.DESSIN_OT_hatch_boundary); type(op).execute(op,ctx)
b=[o for o in bpy.data.objects if o.name.startswith("Hatch boundary")]
chk("boundary : 3 contours", len(b)==1 and len(b[0].data.splines)==3, [len(x.data.splines) for x in b])
for o in C.view_layer.objects: o.select_set(False)
h.dessin_hatch.pattern='BRICK'; h2.select_set(True); h.select_set(True); C.view_layer.objects.active=h
op=make(m.DESSIN_OT_hatch_match); type(op).execute(op,ctx); chk("match", h2.dessin_hatch.pattern=='BRICK')
for o in C.view_layer.objects: o.select_set(False)
h2.select_set(True); n=len(h2.data.edges); h2n=h2.name
op=make(m.DESSIN_OT_hatch_explode); type(op).execute(op,ctx)
ex=[o for o in bpy.data.objects if o.name.startswith("Hatch lines")]
chk("explode -> courbe", len(ex)==1 and len(ex[0].data.splines)==n and bpy.data.objects.get(h2n) is None, (n,[len(x.data.splines) for x in ex]))
# 8) snap ignores hatch
n_with=len(m.collect_snap_points(C)[0]); hd=h.data; h.data=bpy.data.meshes.new("e"); m._SNAP_CACHE.clear(); n_wo=len(m.collect_snap_points(C)[0]); h.data=hd
chk("accrochage ignore les hachures", n_with==n_wo, (n_with,n_wo))
print("RESULTAT",sum(res),"/",len(res))
