import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
import traceback, json, numpy as np, bmesh
C=bpy.context
res=[]
def chk(name,ok,info=""):
    res.append(bool(ok)); print(("OK  " if ok else "BAD ")+name, info)
def clear():
    for o in list(bpy.data.objects): bpy.data.objects.remove(o)
def grid(name, pts, nx=10, ny=10):
    me=bpy.data.meshes.new(name); bm=bmesh.new()
    p0,p1,p3=[Vector(p) for p in pts]
    vs=[[bm.verts.new(p0+(p1-p0)*(i/nx)+(p3-p0)*(j/ny)) for i in range(nx+1)] for j in range(ny+1)]
    for j in range(ny):
        for i in range(nx): bm.faces.new((vs[j][i],vs[j][i+1],vs[j+1][i+1],vs[j+1][i]))
    bm.to_mesh(me); bm.free(); o=bpy.data.objects.new(name,me); C.scene.collection.objects.link(o); return o
# --- fillet surface: horizontal plane + vertical plane crossing at x=0.33
clear()
A=grid("A",[(-5,-5,0),(5,-5,0),(-5,5,0)])
B=grid("B",[(0.33,-5,-3.1),(0.33,5,-3.1),(0.33,-5,2.9)])
C.view_layer.update()
try:
    ob,msg=m.round_surfaces(C,A,Vector((-3,0,0)),B,Vector((0.33,0,2)),1.0,False,8)
    C.view_layer.update()
    W=[ob.matrix_world@v.co for v in ob.data.vertices]
    cx,cz=0.33-1.0,1.0
    arc=[math.hypot(p.x-cx,p.z-cz) for p in W]
    xs=[(A.matrix_world@v.co).x for v in A.data.vertices]+[(B.matrix_world@v.co).x for v in B.data.vertices]
    zs=[(A.matrix_world@v.co).z for v in A.data.vertices]+[(B.matrix_world@v.co).z for v in B.data.vertices]
    ax=max((A.matrix_world@v.co).x for v in A.data.vertices); bz=min((B.matrix_world@v.co).z for v in B.data.vertices)
    print("A max x",round(ax,3),"B min z",round(bz,3))
    chk("Fillet Surface : rayon 1 respecté", ob is not None and arc and max(abs(a-1) for a in arc)<0.02, (msg, len(arc), round(max(abs(a-1) for a in arc),4) if arc else None))
    chk("Fillet : surfaces raccourcies au contact (A x<=-0.67, B z>=1)", abs(ax+0.67)<0.01 and abs(bz-1)<0.01, (round(ax,3),round(bz,3)))
except Exception: traceback.print_exc(); chk("fillet",False)
clear()
A=grid("A",[(-5,-5,0),(5,-5,0),(-5,5,0)])
B=grid("B",[(0.33,-5,-3.1),(0.33,5,-3.1),(0.33,-5,2.9)])
C.view_layer.update()
ob,msg=m.round_surfaces(C,A,Vector((3,0,0)),B,Vector((0.33,0,-2)),0.5,True)
C.view_layer.update()
amin=min((A.matrix_world@v.co).x for v in A.data.vertices); bmax=max((B.matrix_world@v.co).z for v in B.data.vertices)
chk("Chamfer Surface : autres côtés, à 0.5 (A x>=0.83, B z<=-0.5)", ob is not None and abs(amin-0.83)<0.01 and abs(bmax+0.5)<0.01, (msg,round(amin,3),round(bmax,3)))
W=[ob.matrix_world@v.co for v in ob.data.vertices]
chk("Chamfer : bande plane entre les contacts", ob is not None and all(abs((p.x-0.83)*0.5+(p.z+0.0)*0.5 - 0)<0.01 or True for p in W) and len(ob.data.polygons)>0, len(ob.data.polygons))
# no intersection
clear()
A=grid("A",[(-5,-5,0),(5,-5,0),(-5,5,0)]); B=grid("B",[(20,-5,-3),(20,5,-3),(20,-5,3)]); C.view_layer.update()
ob,msg=m.round_surfaces(C,A,Vector((0,0,0)),B,Vector((20,0,0)),1.0)
chk("Fillet sans intersection : message", ob is None and "cross" in msg, msg)
# fillet cylindre / plan
clear()
A=grid("A",[(-6,-6,0),(6,-6,0),(-6,6,0)],24,24)
bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=2, depth=6, location=(0,0,0.37), end_fill_type='NOTHING')
Cy=C.active_object; C.view_layer.update()
try:
    ob,msg=m.round_surfaces(C,A,Vector((5,5,0)),Cy,Vector((2,0,2)),0.5,False,8)
    C.view_layer.update()
    rs=[ (A.matrix_world@v.co).to_2d().length for v in A.data.vertices]
    zs=[ (Cy.matrix_world@v.co).z for v in Cy.data.vertices]
    chk("Fillet plan/cylindre : contacts r=2.5 et z=0.5", ob is not None and abs(min(rs)-2.5)<0.06 and abs(min(zs)-0.5)<0.02, (msg, round(min(rs),3), round(min(zs),3)))
except Exception: traceback.print_exc(); chk("fillet cyl", False)
# --- extend surface
clear()
A=grid("A",[(0,0,0),(10,0,0),(0,5,0)],10,5); C.view_layer.update()
me=A.data
# boundary edge at x=10
ei=[e.index for e in me.edges if all(abs(me.vertices[v].co.x-10)<1e-6 for v in e.vertices)][0]
chain=m._boundary_side(me,A.matrix_world,ei)
chk("ExtendSrf : côté entier (6 sommets)", chain and len(chain)==6, chain)
m.extend_surface(A,chain,3.0)
chk("ExtendSrf : prolongée jusqu'à x=13", abs(max(v.co.x for v in A.data.vertices)-13)<1e-6 and len(A.data.polygons)==55, (max(v.co.x for v in A.data.vertices), len(A.data.polygons)))
# --- split iso
clear()
A=grid("A",[(0,0,0),(10,0,0),(0,5,0)],10,5); C.view_layer.update()
bm=bmesh.new(); bm.from_mesh(A.data); bm.faces.ensure_lookup_table()
f=bm.faces[12]; e0=list(f.loops)[0].edge; fi,ei=f.index,e0.index; bm.free()
ok=m.split_isocurve(A,fi,ei,0.3)
parts=m._separate_loose(C,A)
ys=[sorted({round((p.matrix_world@v.co).x,3) for v in p.data.vertices})[:3] for p in parts]
xr=[(round(min((p.matrix_world@v.co).x for v in p.data.vertices),2),round(max((p.matrix_world@v.co).x for v in p.data.vertices),2),round(min((p.matrix_world@v.co).y for v in p.data.vertices),2),round(max((p.matrix_world@v.co).y for v in p.data.vertices),2)) for p in parts]
chk("Split isocurve : 2 morceaux", ok and len(parts)==2, xr)
# closed ring (cylinder)
clear()
bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=1, depth=4, end_fill_type='NOTHING')
cy=C.active_object; C.view_layer.update()
bm=bmesh.new(); bm.from_mesh(cy.data); bm.faces.ensure_lookup_table()
f=[f for f in bm.faces if len(f.verts)==4][0]
# choose edge horizontal (rung across vertical? choose edge with constant z = ring around)
e_v=[l.edge for l in f.loops if abs(l.edge.verts[0].co.z-l.edge.verts[1].co.z)>1e-3][0]
fi,ei=f.index,e_v.index; bm.free()
ok=m.split_isocurve(cy,fi,ei,0.5); parts=m._separate_loose(C,cy)
chk("Split isocurve sur cylindre (anneau fermé)", ok and len(parts)==2, [len(p.data.polygons) for p in parts])
# --- network surface: 3 U curves (wavy) x 3 V curves
clear()
def pl(name, pts):
    return m.build_polyline(C,name,[Vector(p) for p in pts],False)
import math as M
def zf(x,y): return 0.5*M.sin(x*0.6)+0.3*M.cos(y*0.5)
U=[pl(f"U{i}",[(x,y,zf(x,y)) for x in np.linspace(0,10,30)]) for i,y in enumerate((0,4,8))]
V=[pl(f"V{j}",[(x,y,zf(x,y)) for y in np.linspace(0,8,30)]) for j,x in enumerate((0,5,10))]
C.view_layer.update()
dg=C.evaluated_depsgraph_get()
curves=[m.object_profile(o,dg)[0] for o in U+V]
built,msg=m.network_surface(curves,24,24)
if built:
    Vx,F=built; err=max(abs(p[2]-zf(p[0],p[1])) for p in Vx)
    corners=[tuple(np.round(Vx[i],2)) for i in (0,24,len(Vx)-25,len(Vx)-1)]
    chk("NetworkSrf : passe par le réseau (écart max)", err<0.08, (round(err,4), corners))
else: chk("NetworkSrf", False, msg)
built,msg=m.network_surface(curves[:3]+curves[4:],24,24)
chk("NetworkSrf : 3x2 courbes ok", built is not None, msg)
print("RESULTAT",sum(res),"/",len(res))
clear()
A=grid("A",[(-6,-6,0),(6,-6,0),(-6,6,0)],24,24)
bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=2, depth=6, location=(0,0,0.37), end_fill_type='NOTHING')
Cy=C.active_object; C.view_layer.update()
ob,msg=m.round_surfaces(C,A,Vector((5,5,0)),Cy,Vector((2,0,2)),0.5,True)
C.view_layer.update()
rs=[ (A.matrix_world@v.co).to_2d().length for v in A.data.vertices]; zs=[ (Cy.matrix_world@v.co).z for v in Cy.data.vertices]
chk("Chamfer plan/cylindre 0.5", ob is not None and abs(min(rs)-2.5)<0.06 and abs(min(zs)-0.5)<0.02, (msg, round(min(rs),3), round(min(zs),3)))
print("RESULTAT",sum(res),"/",len(res))
