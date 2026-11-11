import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
exec(open(_os.path.join(_HERE,'undo_lib.py')).read())
# PushPull (percer en traversant, accrochage de la hauteur), Offset Edge (courbe gardée), Extrude Surface (face d'un solide)
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
def undo_redo(name, run):
    """État avant / après, puis Annuler et Rétablir : la scène doit revenir exactement à chacun des deux états."""
    bpy.ops.ed.undo_push(message="avant"); A=snapshot(bpy)
    run(); C.view_layer.update(); B=snapshot(bpy)
    bpy.ops.ed.undo_push(message=name); bpy.ops.ed.undo(); C.view_layer.update(); A2=snapshot(bpy)
    bpy.ops.ed.redo(); C.view_layer.update(); B2=snapshot(bpy)
    chk(f"Undo/Redo {name}", A!=B and A2==A and B2==B, "" if A2==A and B2==B else (diff(A,A2,2), diff(B,B2,2)))

# ---------------- 1. PushPull : géométrie ----------------
def geo(name, prep, expect, msg_expect=""):
    clear(); o=box(); fi=prep(o); C.view_layer.update()
    msg=m.push_pull_mesh(o, fi[0], fi[1]); C.view_layer.update(); s=stats(o)
    ok=msg==msg_expect and abs(s["vol"]-expect[0])<1e-4 and abs(s["zmin"]-expect[1])<1e-6 and abs(s["zmax"]-expect[2])<1e-6 and solid_ok(s)
    chk(name, ok, (msg, s))
    return o
geo("face entière poussée de 1 : la boîte raccourcit", lambda o:(face_at(o,1,4),-1.0), (48,0,3))
geo("face entière tirée de 1", lambda o:(face_at(o,1,4),1.0), (80,0,5))
def pocket(d): return lambda o:(imprint_square(o,4) and face_at(o,1,4,(0,0)), d)
geo("poche 2x2 de 1", pocket(-1.0), (60,0,4))
geo("zone poussée à travers (5 > épaisseur 4) : trou", pocket(-5.0), (48,0,4))
o=geo("zone poussée exactement de l'épaisseur : trou", pocket(-4.0), (48,0,4))
xs=sorted({round(abs((o.matrix_world@v.co).x),9) for v in o.data.vertices})
chk("trou aux cotes exactes (1 et 2)", xs==[1.0,2.0], xs)
def user_case(d2):
    def f(o):
        imprint_square(o,4); m.push_pull_mesh(o,face_at(o,1,4,(0,0)),-2.0); C.view_layer.update()
        return (face_at(o,1,2),d2)
    return f
geo("cas signalé : fond de la poche poussé au-delà du solide -> trou", user_case(-3.0), (48,0,4))
geo("fond de la poche poussé jusqu'au fond -> trou", user_case(-2.0), (48,0,4))
geo("fond de la poche poussé à moitié -> poche plus profonde", user_case(-1.0), (52,0,4))
geo("pousser tout le solide : refusé, solide intact", lambda o:(face_at(o,1,4),-4.0), (64,0,4), "the push removes the whole solid")
# objet tourné et étiré
clear(); o=box(); o.rotation_euler=(0,0,0.5); o.scale=(1.5,1,1); C.view_layer.update()
imprint_square(o,4)
msg=m.push_pull_mesh(o,face_at(o,1,4,(0,0)),-6.0); C.view_layer.update(); s=stats(o)
chk("objet tourné et étiré : trou traversant", msg=="" and abs(s["vol"]-80)<1e-4 and solid_ok(s), (msg,s))
# U : la face intérieure d'une branche tirée jusque dans l'autre -> union
clear()
me=bpy.data.meshes.new("U"); bm=bmesh.new()
pts=[(0,0),(6,0),(6,4),(4,4),(4,1),(2,1),(2,4),(0,4)]
vs=[bm.verts.new((x,y,0)) for x,y in pts]; f=bm.faces.new(vs)
ext=bmesh.ops.extrude_face_region(bm,geom=[f]); bmesh.ops.translate(bm,vec=(0,0,2),verts=[g for g in ext["geom"] if isinstance(g,bmesh.types.BMVert)])
bmesh.ops.recalc_face_normals(bm,faces=bm.faces); bm.to_mesh(me); bm.free()
u=bpy.data.objects.new("U",me); C.scene.collection.objects.link(u); C.view_layer.update()
fi=[p.index for p in u.data.polygons if p.normal.x>0.9 and abs(p.center.x-2)<1e-6][0]
msg=m.push_pull_mesh(u,fi,3.0); C.view_layer.update(); s=stats(u)
chk("face tirée jusque dans l'autre branche : union propre", msg=="" and abs(s["vol"]-48)<1e-4 and solid_ok(s), (msg,s))
# surface ouverte (inchangé)
clear(); me=bpy.data.meshes.new("P"); me.from_pydata([(-2,-2,0),(2,-2,0),(2,2,0),(-2,2,0)],[],[(0,1,2,3)])
pl=bpy.data.objects.new("P",me); C.scene.collection.objects.link(pl); C.view_layer.update()
msg=m.push_pull_mesh(pl,0,1.0); s=stats(pl)
chk("surface plane tirée : volume fermé", msg=="" and abs(s["vol"]-16)<1e-4 and s["naked"]==0, (msg,s))

# ---------------- 2. PushPull : commande, accrochage, annulation ----------------
def snap_scene():
    clear(); b=box(); t=box(1.0,(6.5,6.5,0.75),"T"); t.scale=(1,1,1.5); C.view_layer.update()
    for q in bpy.data.objects: q.select_set(False)
    return b
b=snap_scene()
st=C.scene.dessin; st.osnap_disable=False
o,r=start(m.DESSIN_OT_pushpull)
E(o,('c',0.3,0.3),('m',6.0,6.0))
chk("accrochage pendant PushPull : repère affiché", o.snap_screen is not None, o.snap_screen)
chk("hauteur prise sur le point accroché (1,5 - 4 = -2,5)", abs(o.dist+2.5)<1e-6, o.dist)
r=E(o,('c',6.0,6.0)); C.view_layer.update(); s=stats(b)
chk("clic sur le point accroché : face du dessus à z = 1,5", 'FINISHED' in r and abs(s["zmax"]-1.5)<1e-6 and abs(s["vol"]-24)<1e-4 and solid_ok(s), (r,s))
try: type(o).cleanup(o)
except Exception: pass
b=snap_scene(); st.osnap_disable=True
o,r=start(m.DESSIN_OT_pushpull); E(o,('c',0.3,0.3),('m',6.0,6.0))
chk("F3 (accrochages coupés) : pas d'accrochage", o.snap_screen is None)
E(o,'ESC'); st.osnap_disable=False
b=snap_scene()
o,r=start(m.DESSIN_OT_pushpull); r=E(o,('c',0.3,0.3),('m',6.0,6.0),('t','1'),'RET'); C.view_layer.update(); s=stats(b)
chk("valeur saisie prioritaire sur l'accrochage (garde le sens : -1)", 'FINISHED' in r and abs(s["zmax"]-3)<1e-6, s)
def run_pp_through():
    b=bpy.data.objects["Box"]; imprint_square(b,4)
    o,r=start(m.DESSIN_OT_pushpull); E(o,('c',0.3,0.3),('t','-5'),'RET')
clear(); box(); C.view_layer.update()
undo_redo("PushPull traversant", run_pp_through)
s=stats(bpy.data.objects["Box"]); chk("après Rétablir : trou toujours propre", abs(s["vol"]-48)<1e-4 and solid_ok(s), s)

# ---------------- 3. Offset Edge : la courbe reste ----------------
def offset_top(b):
    for q in bpy.data.objects: q.select_set(False)
    o,r=start(m.DESSIN_OT_offset_edge)
    return E(o,('c',2,0),('c',0,2),('c',-2,0),('c',0,-2),'RET',('m',1.0,0.3),('t','0.5'),'RET')
clear(); b=box(); r=offset_top(b); C.view_layer.update()
crv=[q for q in bpy.data.objects if q.type=='CURVE']
chk("Offset Edge sur une face : face découpée", len(b.data.polygons)==10 and solid_ok(stats(b)), len(b.data.polygons))
P=sorted(tuple(round(c,6) for c in (crv[0].matrix_world@Vector(p.co[:3]))) for p in crv[0].data.splines[0].points) if crv else []
chk("... et la courbe décalée reste visible (fermée, cotes exactes)", len(crv)==1 and crv[0].data.splines[0].use_cyclic_u and P==sorted([(-1.5,-1.5,4.0),(1.5,-1.5,4.0),(1.5,1.5,4.0),(-1.5,1.5,4.0)]), P)
inner=face_at(b,1,4,(0,0)); ring=[p.index for p in b.data.polygons if p.normal.z>0.9 and p.index!=inner][0]
chk("PushPull ne redécoupe pas sur cette courbe", m.pp_curve_loops(C,b,inner)==[] and m.pp_curve_loops(C,b,ring)==[])
nv=len(b.data.vertices)
o,rr=start(m.DESSIN_OT_pushpull); r=E(o,('c',1.8,0.0),('t','1'),'RET'); C.view_layer.update(); s=stats(b)
chk("PushPull de l'anneau : mur de 1, pas de sommet en double", 'FINISHED' in r and abs(s["vol"]-(64+7))<1e-4 and solid_ok(s), (r,s,len(b.data.vertices)-nv))
clear(); b=box(); C.view_layer.update()
undo_redo("Offset Edge sur une face", lambda: offset_top(bpy.data.objects["Box"]))
# une courbe dessinée par l'utilisateur sur la face découpe toujours (comportement 123 gardé)
clear(); b=box(); C.view_layer.update()
m.build_polyline(C,"R",[Vector(p) for p in [(-1,-1,4),(1,-1,4),(1,1,4),(-1,1,4)]],True); C.view_layer.update()
o,rr=start(m.DESSIN_OT_pushpull); r=E(o,('c',0.2,0.2),('t','1'),'RET'); C.view_layer.update(); s=stats(b)
chk("courbe dessinée sur la face : PushPull la découpe et tire la zone", 'FINISHED' in r and abs(s["vol"]-68)<1e-4 and solid_ok(s), s)

# ---------------- 4. Extrude Surface : une face d'un solide ----------------
def ext_face(evs):
    for q in bpy.data.objects: q.select_set(False)
    bpy.data.objects["Box"].select_set(True); C.view_layer.objects.active=bpy.data.objects["Box"]
    o,r=start(m.DESSIN_OT_extrude_srf)
    r=E(o,*evs)
    try: type(o).cleanup(o,ctx)
    except Exception: pass
    return o,r
clear(); b=box(); C.view_layer.update()
o,r=ext_face([('c',0.5,0.5),'RET',('c',0,0),('t','2'),'RET'])
C.view_layer.update()
ex=[q for q in bpy.data.objects if q.name.startswith("Extrusion")]
left=[q.name for q in bpy.data.objects if q.get(m.FACE_PICK_KEY)]
s=stats(ex[0]) if ex else {}
chk("Extrude Surface : clic sur la face d'un solide -> solide extrudé", len(ex)==1 and abs(s.get("vol",0)-32)<1e-4 and abs(s["zmin"]-4)<1e-6 and abs(s["zmax"]-6)<1e-6 and solid_ok(s), (r,s))
chk("le solide d'origine est intact, aucune face provisoire ne reste", abs(stats(b)["vol"]-64)<1e-4 and not left, left)
clear(); b=box(); C.view_layer.update()
o,r=ext_face([('c',0.5,0.5),'ESC'])
left=[q.name for q in bpy.data.objects if q.get(m.FACE_PICK_KEY)]
esc_desel=m.pref("esc_deselect")
chk("Échap : rien ne reste ; la sélection suit la préférence « Échap désélectionne »", not left and len(bpy.data.objects)==1 and b.select_get()==(not esc_desel), (left,b.select_get(),esc_desel))
# surface simple : comportement inchangé (toute la surface)
clear(); me=bpy.data.meshes.new("S"); me.from_pydata([(-2,-2,0),(2,-2,0),(2,2,0),(-2,2,0)],[],[(0,1,2,3)])
sf=bpy.data.objects.new("S",me); C.scene.collection.objects.link(sf); C.view_layer.update()
for q in bpy.data.objects: q.select_set(False)
sf.select_set(True); C.view_layer.objects.active=sf
o,r=start(m.DESSIN_OT_extrude_srf); r=E(o,('c',0,0),('t','1'),'RET')
try: type(o).cleanup(o,ctx)
except Exception: pass
ex=[q for q in bpy.data.objects if q.name.startswith("Extrusion")]
chk("surface simple sélectionnée : extrudée entière comme avant", len(ex)==1 and abs(stats(ex[0])["vol"]-16)<1e-4, [q.name for q in bpy.data.objects])
clear(); box(); C.view_layer.update()
undo_redo("Extrude Surface sur une face de solide", lambda: ext_face([('c',0.5,0.5),'RET',('c',0,0),('t','2'),'RET']))
print("RESULTAT",sum(res),"/",len(res))
