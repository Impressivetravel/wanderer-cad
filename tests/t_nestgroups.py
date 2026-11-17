import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
exec(open(_os.path.join(_HERE,'prec_lib.py')).read())
# Extrude sur plusieurs objets : un objet par surface, sauf vrai contour imbriqué (trou), comme Rhino
import math, numpy as np, io, contextlib
SEC="Extrude : objets séparés"
def arch(x, s=1.0, n=40, dup=False):
    w, hh = 1.0*s, 1.4*s
    pts=[(x,0,0)]
    if dup: pts.append((x,0,0))
    pts += [(x+w,0,0),(x+w,hh,0)]
    for k in range(1,n):
        a=math.pi*k/n
        pts.append((x+w/2+(w/2)*math.cos(a), hh+(w/2)*math.sin(a), 0))
    pts.append((x,hh,0))
    return np.array(pts, dtype=np.float64)
def square(x,y,s):
    return np.array([(x,y,0),(x+s,y,0),(x+s,y+s,0),(x,y+s,0)], dtype=np.float64)
def grp(*paths): return [[(p, True)] for p in paths]
rec(SEC,"trois arches côte à côte, de tailles différentes : trois groupes",
    [len(g) for g in m.nest_groups(grp(arch(0,1.0),arch(2.6,1.15),arch(5.5,1.35)))]==[1,1,1])
rec(SEC,"... même avec les deux premiers points confondus (axe dégénéré)",
    [len(g) for g in m.nest_groups(grp(arch(0,1.0,dup=True),arch(2.6,1.15,dup=True),arch(5.5,1.35,dup=True)))]==[1,1,1])
rec(SEC,"arches qui se touchent presque : toujours séparées",
    [len(g) for g in m.nest_groups(grp(arch(0,1.0),arch(1.02,1.0),arch(2.04,1.0)))]==[1,1,1])
rec(SEC,"carré dans un carré : un seul groupe (trou), comme Rhino",
    [len(g) for g in m.nest_groups(grp(square(0,0,10), square(3,3,2)))]==[2])
rec(SEC,"deux carrés qui se chevauchent : pas de trou, deux groupes",
    [len(g) for g in m.nest_groups(grp(square(0,0,10), square(8,8,6)))]==[1,1])
rec(SEC,"un carré à cheval sur le bord : deux groupes",
    [len(g) for g in m.nest_groups(grp(square(0,0,10), square(9,4,3)))]==[1,1])
rec(SEC,"deux trous dans le même contour : un seul groupe",
    [len(g) for g in m.nest_groups(grp(square(0,0,20), square(2,2,3), square(12,12,3)))]==[3])
# la commande elle-même : trois surfaces -> trois extrusions
clear()
def srf(name, P):
    me=bpy.data.meshes.new(name); me.from_pydata([tuple(p) for p in P],[],[tuple(range(len(P)))]); me.update()
    o=bpy.data.objects.new(name,me); bpy.context.scene.collection.objects.link(o); return o
objs=[srf("S0",arch(0,1.0)), srf("S1",arch(2.6,1.15)), srf("S2",arch(5.5,1.35))]
bpy.context.view_layer.update()
new,r,o=run("extrude_srf",[C(0,0),M(0,3),T(2.0),'RET'],sel=objs)
def parts(ob):
    import bmesh
    bm=bmesh.new(); bm.from_mesh(ob.data); seen=set(); n=0
    for v in bm.verts:
        if v in seen: continue
        stack=[v]; comp=set()
        while stack:
            w=stack.pop()
            if w in comp: continue
            comp.add(w)
            for e in w.link_edges: stack.append(e.other_vert(w))
        seen|=comp; n+=1
    bm.free(); return n
rec(SEC,"Extrude Surface sur trois surfaces : trois objets, un seul morceau chacun, et les trois entrées gardées",
    len(new)==3 and all(parts(x)==1 for x in new) and all(x.name in bpy.data.objects for x in objs),
    [(x.name, parts(x)) for x in new])
# un trou : une seule extrusion
clear()
objs=[srf("B",square(0,0,10)), srf("H",square(3,3,2))]
bpy.context.view_layer.update()
new,r,o=run("extrude_crv",[C(0,0),M(0,3),T(2.0),'RET'],sel=objs)
rec(SEC,"Extrude Curve, un contour dans l'autre : une seule extrusion, percée",len(new)==1,[(x.name,len(x.data.polygons)) for x in new])
clear()
objs=[srf("S0",arch(0,1.0)), srf("S1",arch(2.6,1.15)), srf("S2",arch(5.5,1.35))]
bpy.context.view_layer.update()
new,r,o=run("extrude_crv",[C(0,0),M(0,3),T(2.0),'RET'],sel=objs)
rec(SEC,"Extrude Curve sur trois contours séparés : trois objets d'un seul morceau",
    len(new)==3 and all(parts(x)==1 for x in new),[(x.name,parts(x)) for x in new])
summary()
