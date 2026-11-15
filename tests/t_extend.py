import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
exec(open(_os.path.join(_HERE,'undo_lib.py')).read())
# Extend Curve : outil interactif (clic près d'un bout, puis longueur à la souris, tapée, ou Entrée = jusqu'à la limite suivante)
import bmesh, io, contextlib, math
from mathutils.bvhtree import BVHTree
m.DessinTransform=mirror(m.DessinTransform)
C=bpy.context
res=[]
def chk(n,ok,info=""): res.append(bool(ok)); print(("OK  " if ok else "BAD ")+n, info)
def stats(o):
    bm=bmesh.new(); bm.from_mesh(o.data); bm.transform(o.matrix_world); bm.faces.ensure_lookup_table()
    vol=abs(bm.calc_volume(signed=True))
    naked=sum(1 for e in bm.edges if len(e.link_faces)==1)
    nonman=sum(1 for e in bm.edges if len(e.link_faces)>2)
    zs=[v.co.z for v in bm.verts]
    t=BVHTree.FromBMesh(bm); fl=bm.faces
    selfx=sum(1 for a,b in t.overlap(t) if a<b and not set(fl[a].verts)&set(fl[b].verts))
    dup=len(bm.verts)-len({tuple(round(c,6) for c in v.co) for v in bm.verts})
    r=dict(vol=round(vol,5),naked=naked,nonman=nonman,zmin=round(min(zs),6),zmax=round(max(zs),6),selfx=selfx,dup=dup)
    bm.free(); return r
def solid_ok(s): return s["naked"]==0 and s["nonman"]==0 and s["selfx"]==0 and s["dup"]==0
def clear():
    for o in list(bpy.data.objects): bpy.data.objects.remove(o)
def box(size=4,loc=(0,0,2),name="Box"):
    me=bpy.data.meshes.new(name); bm=bmesh.new(); bmesh.ops.create_cube(bm,size=size); bm.to_mesh(me); bm.free()
    o=bpy.data.objects.new(name,me); C.scene.collection.objects.link(o); o.location=loc; C.view_layer.update(); return o
def face_at(o,nz,z,center=None):
    best,bd=None,1e9
    for p in o.data.polygons:
        n=(o.matrix_world.to_3x3()@p.normal).normalized()
        if abs(n.z-nz)>1e-3: continue
        c=o.matrix_world@p.center
        if abs(c.z-z)>1e-4: continue
        if center is not None and len(p.vertices)!=4: continue
        d=0 if center is None else (c.x-center[0])**2+(c.y-center[1])**2
        if d<bd: best,bd=p.index,d
    return best
def imprint_square(o,z,h=1.0,cx=0.0,cy=0.0):
    r=m.build_polyline(C,"R",[Vector(p) for p in [(cx-h,cy-h,z),(cx+h,cy-h,z),(cx+h,cy+h,z),(cx-h,cy+h,z)]],True)
    C.view_layer.update()
    top=face_at(o,1,z)
    ok=m.imprint_loops(o,top,m.pp_curve_loops(C,o,top))
    bpy.data.objects.remove(r); return ok
K={'0':'ZERO','1':'ONE','2':'TWO','3':'THREE','4':'FOUR','5':'FIVE','.':'PERIOD','-':'MINUS'}
def E(o,*evs):
    r=None
    with contextlib.redirect_stdout(io.StringIO()):
        for e in evs:
            if isinstance(e,tuple) and e[0]=='c':
                sx,sy=scr(e[1],e[2]); seq=[ev('MOUSEMOVE','NOTHING',sx,sy),ev('LEFTMOUSE','PRESS',sx,sy),ev('LEFTMOUSE','RELEASE',sx,sy)]
            elif isinstance(e,tuple) and e[0]=='m': seq=[ev('MOUSEMOVE','NOTHING',*scr(e[1],e[2]))]
            elif isinstance(e,tuple) and e[0]=='t': seq=[ev(K[ch],'PRESS',*scr(0,0),unicode=ch,ascii=ch) for ch in e[1]]
            else: seq=[ev(e,'PRESS',*scr(0,0))]
            for x in seq:
                r=type(o).modal(o,ctx,x)
                if 'FINISHED' in r or 'CANCELLED' in r: return r
    return r
def start(cls):
    o=make(cls)
    with contextlib.redirect_stdout(io.StringIO()):
        r=type(o).invoke(o,ctx,ev('NONE','NOTHING',*scr(0,0)))
    return o,r
def line(name,a,b):
    return m.build_polyline(C,name,[Vector(a),Vector(b)],False)
def pts(o,si=0):
    sp=o.data.splines[si]
    return [tuple(round(c,5) for c in (o.matrix_world@Vector(p.co[:3]))) for p in sp.points]
def click(o,x,y):
    sx,sy=scr(x,y)
    with contextlib.redirect_stdout(io.StringIO()):
        for e in (ev('MOUSEMOVE','NOTHING',sx,sy),ev('LEFTMOUSE','PRESS',sx,sy),ev('LEFTMOUSE','RELEASE',sx,sy)):
            r=type(o).modal(o,ctx,e)
    return r
def ext():
    for q in bpy.data.objects: q.select_set(False)
    o,r=start(m.DESSIN_OT_extend_crv); return o

# ---------------- 1. ligne prolongée jusqu'à la courbe suivante (Entrée) ----------------
clear(); L=line("L",(0,0,0),(2,0,0)); B=line("B",(5,-3,0),(5,3,0)); C.view_layer.update()
o=ext(); E(o,('m',1.8,0.0))
chk("survol près du bout : l'outil annonce la limite suivante (à 3 du bout)", "next curve or surface" in (o.info if hasattr(o,"info") else "") or (o._end is None and len(o.guides)==1 and abs((o.guides[0][1]-o.guides[0][0]).length-3.0)<1e-6), getattr(o,"guides",None))
click(o,1.8,0.0)
chk("clic près du bout droit : le bout est choisi, la limite est à 3", o._end is not None and o._end[2] is True and o._hits and abs(o._hits[0]-3.0)<1e-6, o._hits)
r=E(o,'RET'); C.view_layer.update()
chk("Entrée sans rien taper : la ligne va exactement jusqu'à la courbe (x = 5)", pts(L)==[(0.0,0.0,0.0),(5.0,0.0,0.0)], pts(L))
chk("... elle reste une ligne de deux points, et l'outil reste actif pour un autre bout", len(L.data.splines)==1 and len(L.data.splines[0].points)==2 and 'RUNNING_MODAL' in r and o._end is None, r)
E(o,'ESC')

# ---------------- 2. longueur tapée, au début ou à la fin ----------------
clear(); L=line("L",(0,0,0),(2,0,0)); C.view_layer.update()
o=ext(); click(o,1.8,0.0); E(o,('t','1.5'),'RET'); C.view_layer.update()
chk("longueur tapée 1.5 puis Entrée : le bout passe de x=2 à x=3.5", pts(L)==[(0.0,0.0,0.0),(3.5,0.0,0.0)], pts(L))
click(o,0.2,0.0); E(o,('t','1'),'RET'); C.view_layer.update()
chk("clic près du début, 1 tapé : le début recule de x=0 à x=-1", pts(L)==[(-1.0,0.0,0.0),(3.5,0.0,0.0)], pts(L))
E(o,'ESC')

# ---------------- 3. à la souris, avec arrêt sur la limite ----------------
clear(); L=line("L",(0,0,0),(2,0,0)); B=line("B",(8,-3,0),(8,3,0)); C.view_layer.update()
o=ext(); click(o,1.8,0.0); click(o,4.5,0.6); C.view_layer.update()
chk("clic à x=4.5 (loin de la limite) : la ligne s'arrête à x=4.5, dans son prolongement (y reste 0)", pts(L)==[(0.0,0.0,0.0),(4.5,0.0,0.0)], pts(L))
click(o,4.3,0.0); click(o,8.0+8.0/S,0.4); C.view_layer.update()
chk("clic à 8 pixels de la limite : le bout se pose exactement dessus (x = 8)", pts(L)==[(0.0,0.0,0.0),(8.0,0.0,0.0)], pts(L))
click(o,7.8,0.0); r=click(o,7.99,0.02); C.view_layer.update()
chk("clic sur le bout lui-même : longueur nulle refusée avec un message, rien ne change", pts(L)==[(0.0,0.0,0.0),(8.0,0.0,0.0)] and any("positive" in t for _l,t in o._reports), o._reports[-1:])
E(o,'ESC')

# ---------------- 4. polyligne : le dernier segment s'allonge dans sa direction ----------------
clear(); P=m.build_polyline(C,"P",[Vector((0,0,0)),Vector((2,0,0)),Vector((3,1,0))],False); C.view_layer.update()
o=ext(); click(o,2.9,0.9); E(o,('t',str(round(math.sqrt(2),6))),'RET'); C.view_layer.update()
chk("polyligne : le dernier segment (à 45°) s'allonge de √2, jusqu'à (4, 2)", pts(P)==[(0.0,0.0,0.0),(2.0,0.0,0.0),(4.0,2.0,0.0)], pts(P))
E(o,'ESC')

# ---------------- 5. arc (Bézier) : la courbe d'origine ne bouge pas, le prolongement est droit et tangent ----------------
clear(); A=m.build_bezier_arc(C,"A",Vector((0,0,0)),Vector((1,0,0)),Vector((0,1,0)),2.0,0.0,math.pi/2,False); C.view_layer.update()
def bez_eval(o,seg,k=16):
    bp=o.data.splines[0].bezier_points; a,b=bp[seg],bp[seg+1]
    return [o.matrix_world@m._cubic(a.co,a.handle_right,b.handle_left,b.co,i/k)[0] for i in range(k+1)]
n0=len(A.data.splines[0].bezier_points); before=[bez_eval(A,i) for i in range(n0-1)]
endp=A.matrix_world@A.data.splines[0].bezier_points[-1].co
o=ext(); click(o,endp.x+0.02,endp.y-0.05); E(o,('t','1'),'RET'); C.view_layer.update()
n1=len(A.data.splines[0].bezier_points); after=[bez_eval(A,i) for i in range(n0-1)]
dev=max((p-q).length for a,b in zip(before,after) for p,q in zip(a,b))
chk("arc : un point de plus, et l'arc d'origine ne bouge pas (écart 0)", n1==n0+1 and dev<1e-6, (n0,n1,dev))
tail=bez_eval(A,n1-2)
chk("... le prolongement est droit, long de 1, tangent à l'arc (ici vers -x depuis (0,2))", all(abs(p.y-2.0)<1e-5 for p in tail) and abs(tail[0].x-0.0)<1e-5 and abs(tail[-1].x-(-1.0))<1e-5, [(round(p.x,4),round(p.y,4)) for p in tail[::8]])
E(o,'ESC')

# ---------------- 6. NURBS (Control Point Curve) : la courbe garde sa forme, un segment droit s'ajoute ----------------
clear()
cu=bpy.data.curves.new("N",'CURVE'); cu.dimensions='3D'; sp=cu.splines.new('NURBS'); cp=[(0,0,0),(1,2,0),(3,2,0),(4,0,0)]
sp.points.add(len(cp)-1)
for a,q in zip(sp.points,cp): a.co=(*q,1.0)
sp.order_u=4; sp.use_endpoint_u=True; sp.resolution_u=12
N=m._link_object(C,"N",cu); C.view_layer.update()
o=ext(); click(o,3.9,0.2); E(o,('t','2'),'RET'); C.view_layer.update()
d=(Vector((4,0,0))-Vector((3,2,0))).normalized(); q=Vector((4,0,0))+d*2
chk("NURBS : ses points de contrôle n'ont pas bougé", pts(N,0)==[tuple(float(c) for c in p) for p in cp], pts(N,0))
chk("... un segment droit de 2 part du bout, dans la direction de la courbe", len(N.data.splines)==2 and N.data.splines[1].type=='POLY' and pts(N,1)==[(4.0,0.0,0.0),tuple(round(c,5) for c in q)], [pts(N,i) for i in range(1,len(N.data.splines))])
E(o,'ESC')
# NURBS « ouverte » de Blender (sans Endpoint) : le prolongement part du vrai bout de la courbe, pas du point de contrôle
clear()
cu=bpy.data.curves.new("U",'CURVE'); cu.dimensions='3D'; sp=cu.splines.new('NURBS'); sp.points.add(len(cp)-1)
for a,q in zip(sp.points,cp): a.co=(*q,1.0)
sp.order_u=4; sp.use_endpoint_u=False; sp.resolution_u=64
U=m._link_object(C,"U",cu); C.view_layer.update()
dg=C.evaluated_depsgraph_get(); paths=m.object_paths(U,dg); Pth=paths[0][0]
p,dr=m.extension_ray(U,0,True)
ends=[Vector(Pth[0]),Vector(Pth[-1])]; near=min((p-e).length for e in ends)
chk("NURBS sans Endpoint : le bout calculé est le vrai bout de la courbe affichée (écart < 0.001)", near<1e-3 and (p-Vector((4,0,0))).length>0.3, (near,tuple(round(c,4) for c in p)))

# ---------------- 7. arrêt sur une surface (mur) ----------------
clear(); L=line("L",(0,0,0),(2,0,0))
me=bpy.data.meshes.new("Wall"); bm=bmesh.new()
vs=[bm.verts.new(v) for v in ((6,-2,-2),(6,2,-2),(6,2,2),(6,-2,2))]; bm.faces.new(vs); bm.to_mesh(me); bm.free()
W_=bpy.data.objects.new("Wall",me); C.scene.collection.objects.link(W_); C.view_layer.update()
o=ext(); click(o,1.8,0.0)
chk("une surface sur le chemin compte comme limite (mur à x = 6, soit à 4 du bout)", o._hits and abs(o._hits[0]-4.0)<1e-4, o._hits)
E(o,'RET'); C.view_layer.update()
chk("Entrée : la ligne s'arrête sur le mur", pts(L)==[(0.0,0.0,0.0),(6.0,0.0,0.0)], pts(L))
E(o,'ESC')

# ---------------- 8. sans limite : Entrée ne fait rien de faux, une courbe fermée ne se prolonge pas ----------------
clear(); L=line("L",(0,0,0),(2,0,0)); R=m.build_polyline(C,"R",[Vector(p) for p in [(-3,-3,0),(-2,-3,0),(-2,-2,0),(-3,-2,0)]],True); C.view_layer.update()
o=ext(); E(o,('m',-2.5,-3.0))
chk("courbe fermée : aucun bout à prolonger", o._end is None and not o.hilite, len(o.hilite))
click(o,-2.5,-3.0)
chk("... et un clic dessus ne choisit rien", o._end is None)
E(o,'ESC')

# ---------------- 9. la commande « extend » de la ligne de commande lance cet outil ----------------
sug=m.cmd_suggest("extend")
top=sug[0] if sug else None
chk("ligne de commande : « extend » propose Extend Curve en premier, comme outil", top is not None and top["label"]=="Extend Curve" and top["kind"]=="tool" and top["ref"]=="dessin.extend_crv_tool", top and (top["label"],top["kind"],top.get("ref")))
sug=m.cmd_suggest("ex"); chk("alias « ex » (AutoCAD) : Extend Curve", any(s["label"]=="Extend Curve" for s in sug[:3]), [s["label"] for s in sug[:4]])
chk("l'outil est dans la barre (famille Modify) avec son icône", m.DESSIN_TT_extend_crv in m.RHINO_TOOLS["modify"] and "extend_crv" in m.ICON_SVG)

print("RESULTAT", "TOUT OK" if all(res) else f"{res.count(False)} ECHEC(S) sur {len(res)}")
