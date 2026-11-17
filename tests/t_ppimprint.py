import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
import bmesh, numpy as np
C=bpy.context
res=[]
def chk(n,ok,info=""): res.append(bool(ok)); print(("OK  " if ok else "BAD ")+n, info)
def naked(o):
    ec={}
    for p in o.data.polygons:
        for k in p.edge_keys: ec[k]=ec.get(k,0)+1
    return sum(1 for v in ec.values() if v==1)
for o in list(bpy.data.objects): bpy.data.objects.remove(o)
me=bpy.data.meshes.new("Box"); bm=bmesh.new(); bmesh.ops.create_cube(bm,size=4); bm.to_mesh(me); bm.free()
box=bpy.data.objects.new("Box",me); C.scene.collection.objects.link(box); box.location=(0,0,2)
rect=m.build_polyline(C,"R",[Vector(p) for p in [(-1,-1,4),(1,-1,4),(1,1,4),(-1,1,4)]],True)
C.view_layer.update()
top=[p.index for p in box.data.polygons if p.normal.z>0.9][0]
loops=m.pp_curve_loops(C,box,top)
chk("courbe sur la face trouvée", len(loops)==1, len(loops))
ok=m.imprint_loops(box,top,loops)
inner=[p.index for p in box.data.polygons if p.normal.z>0.9 and abs(sum((box.data.vertices[v].co.x for v in p.vertices))/len(p.vertices))<0.01 and len(p.vertices)==4 and max(abs(box.data.vertices[v].co.x) for v in p.vertices)<1.01]
chk("face découpée (zone intérieure + anneau), solide fermé", ok and naked(box)==0 and len(inner)==1, (ok, naked(box), len(box.data.polygons)))
msg=m.push_pull_mesh(box, inner[0], 1.0)
C.view_layer.update()
zs=max((box.matrix_world@v.co).z for v in box.data.vertices)
chk("PushPull de la zone intérieure : bosse de 1, solide fermé", msg=="" and abs(zs-5)<1e-6 and naked(box)==0, (msg, zs, naked(box)))
# ring push down
ring=[p.index for p in box.data.polygons if p.normal.z>0.9 and abs((box.matrix_world@box.data.vertices[p.vertices[0]].co).z-4)<1e-6]
msg=m.push_pull_mesh(box, ring[0], -0.5)
chk("PushPull de l'anneau extérieur seul", msg=="" and naked(box)==0, (msg,naked(box)))
print("RESULTAT",sum(res),"/",len(res))
