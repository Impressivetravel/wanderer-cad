import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
exec(open(_os.path.join(_HERE,'undo_lib.py')).read())
# Arêtes au sens de Rhino : un clic des outils Offset Edge / Fillet Edge / Chamfer Edge prend toute l'arête ; DupBorder : une courbe par boucle
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
def cyl(r=2.0,h=2.0,n=64,caps=True,name="Cyl"):
    me=bpy.data.meshes.new(name); bm=bmesh.new()
    bmesh.ops.create_cone(bm,cap_ends=caps,cap_tris=False,segments=n,radius1=r,radius2=r,depth=h)
    for f in bm.faces: f.smooth=len(f.verts)==4
    bm.to_mesh(me); bm.free()
    o=bpy.data.objects.new(name,me); C.scene.collection.objects.link(o); o.location=(0,0,h/2); C.view_layer.update(); return o
def click(o,x,y,ctrl=False):
    sx,sy=scr(x,y)
    with contextlib.redirect_stdout(io.StringIO()):
        for e in (ev('MOUSEMOVE','NOTHING',sx,sy),ev('LEFTMOUSE','PRESS',sx,sy,ctrl=ctrl),ev('LEFTMOUSE','RELEASE',sx,sy,ctrl=ctrl)):
            r=type(o).modal(o,ctx,e)
    return r
def nsel(o): return sum(len(v) for v in o.sel.values())

# ---------------- 1. Offset Edge : le bord d'un cylindre se prend d'un clic ----------------
for cls,label in ((m.DESSIN_OT_offset_edge,"Offset Edge"),(m.DESSIN_OT_fillet_edge,"Fillet Edge"),(m.DESSIN_OT_chamfer_edge,"Chamfer Edge")):
    clear(); c=cyl(); C.view_layer.update()
    for q in bpy.data.objects: q.select_set(False)
    o,r=start(cls)
    click(o,2.0,0.0)
    chk(f"{label} : un clic sur le bord d'un cylindre prend le cercle entier (64 segments), pas un seul", nsel(o)==64, nsel(o))
    zs={round(float((c.matrix_world@c.data.vertices[v].co).z),6) for i in o.sel.get("Cyl",()) for v in c.data.edges[i].vertices}
    chk(f"{label} : ... et seulement le cercle du haut (celui sous le curseur), pas celui du bas ni les génératrices", zs=={2.0}, zs)
    click(o,2.0,0.0)
    chk(f"{label} : un second clic sur cette arête la retire en entier", nsel(o)==0, nsel(o))
    click(o,2.0,0.0,ctrl=True)
    chk(f"{label} : Ctrl+clic ne prend qu'un segment du maillage", nsel(o)==1, nsel(o))
    click(o,2.0,0.0)
    chk(f"{label} : clic sur ce segment déjà choisi : toute l'arête est retirée", nsel(o)==0, nsel(o))
    E(o,'ESC'); E(o,'ESC')
    # un cube : chaque arête reste une arête (les angles arrêtent la chaîne)
    clear(); b=box(); C.view_layer.update()
    for q in bpy.data.objects: q.select_set(False)
    o,r=start(cls); click(o,2.0,0.0)
    chk(f"{label} : sur un cube, un clic prend une arête, pas le tour de la face", nsel(o)==1, nsel(o))
    E(o,'ESC'); E(o,'ESC')

# survol : toute l'arête est annoncée avant le clic
clear(); c=cyl(); C.view_layer.update()
for q in bpy.data.objects: q.select_set(False)
o,r=start(m.DESSIN_OT_offset_edge); E(o,('m',2.0,0.0))
chk("Offset Edge : au survol, toute l'arête s'allume (64 segments)", len(getattr(o,"preview_extra",[]))==64, len(getattr(o,"preview_extra",[])))
E(o,'ESC'); E(o,'ESC')

# ---------------- 2. Offset Edge sur le cercle entier : une courbe fermée décalée ----------------
clear(); c=cyl(); C.view_layer.update()
for q in bpy.data.objects: q.select_set(False)
o,r=start(m.DESSIN_OT_offset_edge)
click(o,2.0,0.0); r=E(o,'RET',('m',1.0,0.0),('t','0.5'),'RET'); C.view_layer.update()
crv=[q for q in bpy.data.objects if q.type=='CURVE']
ok=len(crv)==1 and len(crv[0].data.splines)==1 and crv[0].data.splines[0].use_cyclic_u and len(crv[0].data.splines[0].points)==64
rad=sorted(round((crv[0].matrix_world@Vector(p.co[:3])).to_2d().length,4) for p in crv[0].data.splines[0].points) if ok else []
chk("Offset Edge du cercle (un clic, 0.5 vers l'intérieur) : une courbe fermée de 64 points", ok, [(len(s.points),s.use_cyclic_u) for q in crv for s in q.data.splines])
chk("... décalée de 0.5 exactement (apothème 2·cos(π/64) − 0.5)", ok and abs(rad[0]-rad[-1])<1e-4 and abs(rad[0]*math.cos(math.pi/64)-(2*math.cos(math.pi/64)-0.5))<1e-4, rad[:1]+rad[-1:])

# ---------------- 3. DupBorder : une courbe par boucle ----------------
def run(opcls):
    o=make(opcls); r=type(o).execute(o,ctx); C.view_layer.update(); return r,o
clear(); c=cyl(caps=False,name="Tube"); C.view_layer.update()
for q in bpy.data.objects: q.select_set(q is c)
C.view_layer.objects.active=c
r,o=run(m.DESSIN_OT_dup_border); bs=[q for q in bpy.data.objects if q.type=='CURVE']
chk("DupBorder d'un tube ouvert : deux courbes (haut et bas), une par boucle", 'FINISHED' in r and len(bs)==2, [(q.name,len(q.data.splines)) for q in bs])
chk("... chacune est une seule polyligne fermée de 64 points", all(len(q.data.splines)==1 and q.data.splines[0].type=='POLY' and q.data.splines[0].use_cyclic_u and len(q.data.splines[0].points)==64 for q in bs))
chk("... l'une à z=0, l'autre à z=2", sorted({round((q.matrix_world@Vector(p.co[:3])).z,6) for p in q.data.splines[0].points}.pop() for q in bs)==[0.0,2.0])
chk("... les deux sont sélectionnées, le tube ne l'est plus", all(q.select_get() for q in bs) and not c.select_get())
# Offset Edge : un clic sur une des deux bordures ne prend que celle-là
for q in bpy.data.objects: q.select_set(False)
c.hide_set(True); C.view_layer.update()
o,r=start(m.DESSIN_OT_offset_edge); click(o,2.0,0.0)
chk("Offset Edge : un clic sur une bordure prend cette courbe entière et elle seule", len(o.sel)==1 and nsel(o)==64, {k:len(v) for k,v in o.sel.items()})
E(o,'ESC'); E(o,'ESC'); c.hide_set(False)
# Explode de la bordure : ses segments
top=[q for q in bs if abs((q.matrix_world@Vector(q.data.splines[0].points[0].co[:3])).z-2.0)<1e-6][0]
for q in bpy.data.objects: q.select_set(q is top)
C.view_layer.objects.active=top
before=set(bpy.data.objects)
r,o=run(m.DESSIN_OT_explode) if hasattr(m,"DESSIN_OT_explode") else (None,None)
after=[q for q in bpy.data.objects if q.type=='CURVE' and abs((q.matrix_world@Vector(q.data.splines[0].points[0].co[:3])).z-2.0)<1e-6]
chk("Explode de cette polyligne : 64 segments séparés", r is not None and 'FINISHED' in r and len(after)==64 and all(len(q.data.splines[0].points)==2 for q in after), (r,len(after)))

# DupFaceBorder : une courbe par boucle aussi (face avec un trou)
clear()
me=bpy.data.meshes.new("Ring"); bm=bmesh.new()
bmesh.ops.create_grid(bm,x_segments=3,y_segments=3,size=3)
bm.faces.ensure_lookup_table()
mid=[f for f in bm.faces if abs(f.calc_center_median().x)<0.5 and abs(f.calc_center_median().y)<0.5]
bmesh.ops.delete(bm,geom=mid,context='FACES'); bm.to_mesh(me); bm.free()
ring=bpy.data.objects.new("Ring",me); C.scene.collection.objects.link(ring); C.view_layer.update()
bm=bmesh.new(); bm.from_mesh(ring.data); bm.faces.ensure_lookup_table(); bm.normal_update()
ch=m.face_border_chains(ring,bm,0); bm.free()
made=m.border_curves(C,"Border",ch)
chk("DupFaceBorder d'une face trouée : contour et trou, deux courbes fermées séparées", len(ch)==2 and len(made)==2 and all(len(q.data.splines)==1 and q.data.splines[0].use_cyclic_u for q in made), [(len(q.data.splines)) for q in made])

# ---------------- 4. objets déjà sélectionnés : Offset Edge les prend d'office (comme Rhino) ----------------
clear(); c=cyl(caps=False,name="Tube"); C.view_layer.update()
for q in bpy.data.objects: q.select_set(q is c)
C.view_layer.objects.active=c
r,o=run(m.DESSIN_OT_dup_border); bs=[q for q in bpy.data.objects if q.type=='CURVE']
top=[q for q in bs if abs((q.matrix_world@Vector(q.data.splines[0].points[0].co[:3])).z-2.0)<1e-6][0]
for q in bpy.data.objects: q.select_set(q is top)
C.view_layer.objects.active=top
o,r=start(m.DESSIN_OT_offset_edge)
chk("courbe sélectionnée avant Offset Edge : elle est déjà prise (64 segments), sans la recliquer", list(o.sel)==[top.name] and nsel(o)==64, {k:len(v) for k,v in o.sel.items()})
chk("... et la commande demande directement le côté et la distance", o.phase=='radius', o.phase)
r=E(o,('m',1.0,0.0),('t','0.5'),'RET'); C.view_layer.update()
new=[q for q in bpy.data.objects if q.type=='CURVE' and q not in bs]
sp0=new[0].data.splines[0] if new else None
chk("... le décalage se fait sans autre clic : une courbe fermée est créée", len(new)==1 and sp0.use_cyclic_u and (len(sp0.points) or len(sp0.bezier_points))>=4, [(q.name,q.data.splines[0].type,len(q.data.splines[0].points),len(q.data.splines[0].bezier_points)) for q in new])
# un solide sélectionné n'est pas pris en entier : il faut dire quelle arête
clear(); b=box(); C.view_layer.update()
for q in bpy.data.objects: q.select_set(True)
o,r=start(m.DESSIN_OT_offset_edge)
chk("solide sélectionné avant la commande : rien n'est pris d'office, on choisit l'arête", nsel(o)==0 and o.phase=='pick', (nsel(o),o.phase))
E(o,'ESC'); E(o,'ESC')
# rien de sélectionné : comme avant
clear(); c=cyl(); C.view_layer.update()
for q in bpy.data.objects: q.select_set(False)
o,r=start(m.DESSIN_OT_offset_edge)
chk("rien de sélectionné : la commande attend qu'on clique les arêtes", nsel(o)==0 and o.phase=='pick')
E(o,'ESC'); E(o,'ESC')

# ---------------- 5. Extrude Curve : option Solid = Yes / No annoncée comme dans Rhino ----------------
clear(); R=m.build_polyline(C,"R",[Vector(p) for p in [(-1,-1,0),(1,-1,0),(1,1,0),(-1,1,0)]],True); C.view_layer.update()
for q in bpy.data.objects: q.select_set(q is R)
C.view_layer.objects.active=R
G_=m.DESSIN_OT_extrude_crv.prompt.__globals__; G_['_OPT_MEM'].pop("dessin.extrude_crv",None)
o,r=start(m.DESSIN_OT_extrude_crv)
p0=o.prompt()
chk("Extrude Curve : dès le point de base, l'invite annonce C: Solid = Yes", "C: Solid = Yes" in p0, p0)
E(o,'C'); p1=o.prompt()
chk("touche C : Solid = No (surface only)", "C: Solid = No (surface only)" in p1, p1)
r=E(o,('c',0,0),('t','2'),'RET'); C.view_layer.update()
ex=[q for q in bpy.data.objects if q.type=='MESH']
naked=0
if ex:
    bm=bmesh.new(); bm.from_mesh(ex[0].data); naked=sum(1 for e in bm.edges if len(e.link_faces)==1); nf=len(bm.faces); bm.free()
chk("Solid = No : l'extrusion d'un carré fermé donne les 4 parois seules, ouvertes en haut et en bas (8 arêtes libres)", len(ex)==1 and nf==4 and naked==8, (len(ex),ex and nf,naked))
G_['_OPT_MEM'].pop("dessin.extrude_crv",None)

print("RESULTAT", "TOUT OK" if all(res) else f"{res.count(False)} ECHEC(S) sur {len(res)}")
