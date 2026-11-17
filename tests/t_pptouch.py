import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
# PushPull : une courbe fermée posée sur une face et qui touche son bord (arête contre arête), comme dans Rhino
import bmesh
from mathutils.bvhtree import BVHTree
C=bpy.context
res=[]
def chk(n,ok,info=""): res.append(bool(ok)); print(("OK  " if ok else "BAD ")+n, info)
def stats(o):
    bm=bmesh.new(); bm.from_mesh(o.data); bm.transform(o.matrix_world); bm.faces.ensure_lookup_table()
    vol=abs(bm.calc_volume(signed=True))
    naked=sum(1 for e in bm.edges if len(e.link_faces)==1)
    nonman=sum(1 for e in bm.edges if len(e.link_faces)>2)
    dup=len(bm.verts)-len({tuple(round(c,6) for c in v.co) for v in bm.verts})
    zero=sum(1 for f in bm.faces if f.calc_area()<1e-9)
    r=dict(vol=round(vol,5),naked=naked,nonman=nonman,dup=dup,zero=zero,faces=len(bm.faces)); bm.free(); return r
def solid_ok(s): return s["naked"]==0 and s["nonman"]==0 and s["dup"]==0 and s["zero"]==0
def clear():
    for o in list(bpy.data.objects): bpy.data.objects.remove(o)
def box():
    me=bpy.data.meshes.new("Box"); bm=bmesh.new(); bmesh.ops.create_cube(bm,size=4); bm.to_mesh(me); bm.free()
    o=bpy.data.objects.new("Box",me); C.scene.collection.objects.link(o); o.location=(0,0,2); C.view_layer.update(); return o
def top_face(o, pt):
    """Face du dessus (z = 4) qui contient le point pt (x, y)."""
    for p in o.data.polygons:
        if p.normal.z < 0.9: continue
        P=[(o.matrix_world@o.data.vertices[v].co) for v in p.vertices]
        if abs(P[0].z-4)>1e-6: continue
        if m._point_in_poly(pt,[(q.x,q.y) for q in P]):
            return p.index
    return None
def side_face(o):
    return [p.index for p in o.data.polygons if p.normal.y < -0.9][0]

CASES = {
  "rectangle contre une arête":        [(-1,-2),(1,-2),(1,0),(-1,0)],
  "rectangle dans un coin":            [(-2,-2),(0,-2),(0,0),(-2,0)],
  "bande d'un bord à l'autre":         [(-2,-2),(2,-2),(2,0),(-2,0)],
  "rectangle qui touche par un sommet":[(0,-2),(1,-1),(0,0),(-1,-1)],
}
for name, pts in CASES.items():
    clear(); o=box()
    r=m.build_polyline(C,"R",[Vector((x,y,4)) for x,y in pts],True); C.view_layer.update()
    top=top_face(o,(1.5,1.5))
    loops=m.pp_curve_loops(C,o,top)
    ok=bool(loops) and m.imprint_loops(o,top,loops)
    s=stats(o)
    cx=sum(p[0] for p in pts)/len(pts); cy=sum(p[1] for p in pts)/len(pts)
    inner=top_face(o,(cx,cy)); outer=top_face(o,(1.5,1.5))
    chk(name+" : courbe trouvée et face découpée, solide fermé", ok and solid_ok(s) and inner is not None and inner!=outer, (len(loops), ok, s))
    if ok and inner is not None:
        msg=m.push_pull_mesh(o,inner,1.0); C.view_layer.update(); s2=stats(o)
        zmax=max((o.matrix_world@v.co).z for v in o.data.vertices)
        chk(name+" : PushPull de la zone, solide fermé", msg=="" and solid_ok(s2) and abs(zmax-5)<1e-6, (msg,s2,zmax))
    bpy.data.objects.remove(r)

# la face d'origine avec un trou : la zone posée contre le bord du trou
clear(); o=box()
r=m.build_polyline(C,"R",[Vector(p) for p in [(-1,-1,4),(1,-1,4),(1,1,4),(-1,1,4)]],True); C.view_layer.update()
t=top_face(o,(0,0)); m.imprint_loops(o,t,m.pp_curve_loops(C,o,t)); bpy.data.objects.remove(r)
m.push_pull_mesh(o,top_face(o,(0,0)),-4.0); C.view_layer.update()   # trou traversant
s=stats(o)
r=m.build_polyline(C,"R",[Vector(p) for p in [(-1,1,4),(1,1,4),(1,2,4),(-1,2,4)]],True); C.view_layer.update()
t=top_face(o,(1.5,1.5)); loops=m.pp_curve_loops(C,o,t)
ok=bool(loops) and m.imprint_loops(o,t,loops); s=stats(o)
chk("zone entre le trou et le bord : découpée, le trou reste vide", ok and solid_ok(s) and top_face(o,(0,0)) is None and top_face(o,(0,1.5)) is not None, (len(loops),ok,s))

# sur une face verticale (le cas du retour : rectangle contre l'arête du bas)
clear(); o=box()
r=m.build_polyline(C,"R",[Vector(p) for p in [(-1,-2,0),(1,-2,0),(1,-2,2),(-1,-2,2)]],True); C.view_layer.update()
f=side_face(o); loops=m.pp_curve_loops(C,o,f)
ok=bool(loops) and m.imprint_loops(o,f,loops); s=stats(o)
chk("face verticale, rectangle contre l'arête du bas", ok and solid_ok(s), (len(loops),ok,s))
print("RESULTAT",sum(res),"/",len(res))
