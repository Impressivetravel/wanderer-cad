import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
import math, numpy as np, bmesh
C=bpy.context
res=[]
def chk(n,ok,info=""): res.append(bool(ok)); print(("OK  " if ok else "BAD ")+n, info)
def clear():
    for o in list(bpy.data.objects): bpy.data.objects.remove(o)
def naked(o): return sum(len(i) for i,c in m.boundary_loops(o.data))
clear()
# planar srf: circle outline with 2 square holes
outer=[Vector((math.cos(t)*5,math.sin(t)*5,0)) for t in np.linspace(0,2*math.pi,48,endpoint=False)]
o1=m.build_polyline(C,"O",outer,True)
h1=m.build_polyline(C,"H1",[Vector(p) for p in [(-3,-1,0),(-1,-1,0),(-1,1,0),(-3,1,0)]],True)
h2=m.build_polyline(C,"H2",[Vector(p) for p in [(1,-1,0),(3,-1,0),(3,1,0),(1,1,0)]],True)
C.view_layer.update()
for x in C.view_layer.objects: x.select_set(True)
op=make(m.DESSIN_OT_planar_srf); type(op).execute(op,ctx)
SRF=[x for x in bpy.data.objects if x.type=='MESH'][0]
L=m.boundary_loops(SRF.data); oi=m.outer_loop_index(SRF.data,L)
chk("surface plane : 3 bords, extérieur = cercle", len(L)==3 and len(L[oi][0])>=48, [len(i) for i,c in L])
hole=[k for k in range(len(L)) if k!=oi][0]
m.fill_hole(SRF,L[hole][0]); L2=m.boundary_loops(SRF.data)
chk("UntrimHoles : un trou bouché", len(L2)==2, [len(i) for i,c in L2])
area=sum(p.area for p in SRF.data.polygons)
m.untrim_outer(SRF); L3=m.boundary_loops(SRF.data)
xs=[v.co.x+SRF.location.x for v in SRF.data.vertices]; ys=[v.co.y+SRF.location.y for v in SRF.data.vertices]
chk("Untrim (sans copie, plane) : rectangle englobant 10x10", len(SRF.data.polygons)==1 and abs(max(xs)-min(xs)-10)<0.01 and abs(max(ys)-min(ys)-10)<0.05, (round(max(xs)-min(xs),3),round(max(ys)-min(ys),3)))
# backup restore
clear()
bpy.ops.mesh.primitive_uv_sphere_add(); sp=C.active_object
nf=len(sp.data.polygons)
m.save_untrimmed(sp)
bm=bmesh.new(); bm.from_mesh(sp.data); bm.faces.ensure_lookup_table()
bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.calc_center_median().z>0.5], context='FACES'); bm.to_mesh(sp.data); bm.free()
cut=len(sp.data.polygons)
r=m.untrim_outer(sp)
chk("Untrim : forme d'origine rendue (copie avant découpe)", r is None and len(sp.data.polygons)==nf and "wd_untrimmed" not in sp.keys() and not any(me.name.startswith(".wd_untrim") for me in bpy.data.meshes), (cut,len(sp.data.polygons)))
# split iso keeps backup on both pieces
clear()
me=bpy.data.meshes.new("G"); bm=bmesh.new()
vs=[[bm.verts.new((i,j,0)) for i in range(11)] for j in range(6)]
for j in range(5):
    for i in range(10): bm.faces.new((vs[j][i],vs[j][i+1],vs[j+1][i+1],vs[j+1][i]))
bm.to_mesh(me); bm.free(); G=bpy.data.objects.new("G",me); C.scene.collection.objects.link(G)
bm=bmesh.new(); bm.from_mesh(G.data); bm.faces.ensure_lookup_table(); f=bm.faces[12]; e0=list(f.loops)[0].edge; fi,ei=f.index,e0.index; bm.free()
m.split_isocurve(G,fi,ei,0.3); parts=m._separate_loose(C,G)
chk("Split iso : les 2 morceaux gardent la forme d'origine", all(p.get("wd_untrimmed") for p in parts), [p.get("wd_untrimmed") for p in parts])
r=m.untrim_outer(parts[1]); chk("Untrim d'un morceau : surface entière", r is None and len(parts[1].data.polygons)==50, len(parts[1].data.polygons))
chk("la copie reste pour l'autre morceau", bpy.data.meshes.get(parts[0]["wd_untrimmed"]) is not None)
print("RESULTAT",sum(res),"/",len(res))
