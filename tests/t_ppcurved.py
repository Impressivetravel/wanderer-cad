# PushPull sur des faces courbes : la face est décalée le long de ses normales (cylindre, sphère, trou, congé, voûte)
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
src=open(_os.path.join(_HERE,'t_pushpull.py')).read()
exec(src[src.index("\n")+1:src.index("# ---------------- 1. PushPull")])
import time
def mk(name,bm,loc=(0,0,0),rot=(0,0,0),scale=(1,1,1)):
    me=bpy.data.meshes.new(name); bm.normal_update(); bm.to_mesh(me); bm.free()
    o=bpy.data.objects.new(name,me); C.scene.collection.objects.link(o); o.location=loc; o.rotation_euler=rot; o.scale=scale; C.view_layer.update(); return o
def cyl(seg=64,r=1.0,h=2.0,**kw):
    bm=bmesh.new(); bmesh.ops.create_cone(bm,cap_ends=True,segments=seg,radius1=r,radius2=r,depth=h); return mk("Cyl",bm,**kw)
def ngon_area(n,r): return 0.5*n*r*r*math.sin(2*math.pi/n)
def side_face(o, pred=None):
    """Indice d'une facette courbe (normale horizontale en local)."""
    for p in o.data.polygons:
        if abs(p.normal.z)<0.5 and (pred is None or pred(p)): return p.index
def radii(o, axis=2):
    C.view_layer.update(); return [math.hypot(*[c for i,c in enumerate(v.co) if i!=axis]) for v in o.data.vertices]
def pp(o,idx,d):
    msg=m.push_pull_mesh(o,idx,d); C.view_layer.update(); return msg

# ---------------- 1. cylindre : le rayon change, les bouchons suivent ----------------
clear(); o=cyl(); n0=len(o.data.polygons); msg=pp(o,side_face(o),0.5); s=stats(o); R=radii(o)
chk("cylindre r=1 tiré de 0,5 : tous les sommets à r=1,5 exactement", msg=="" and max(abs(x-1.5) for x in R)<1e-6, (msg,min(R),max(R)))
chk("... volume = aire du 64-gone de rayon 1,5 x 2, solide fermé, même nombre de faces", abs(s["vol"]-ngon_area(64,1.5)*2)<1e-5 and solid_ok(s) and len(o.data.polygons)==n0, (s,n0,len(o.data.polygons)))
clear(); o=cyl(); msg=pp(o,side_face(o),-0.25); s=stats(o); R=radii(o)
chk("cylindre poussé de 0,25 : r=0,75, volume exact", msg=="" and max(abs(x-0.75) for x in R)<1e-6 and abs(s["vol"]-ngon_area(64,0.75)*2)<1e-5 and solid_ok(s), (msg,s))
clear(); o=cyl(); v0=stats(o)["vol"]; msg=pp(o,side_face(o),-1.2); s=stats(o)
chk("cylindre poussé au-delà de son rayon : refusé avec un message, solide intact", msg!="" and abs(s["vol"]-v0)<1e-9, (msg,s))
clear(); o=cyl(rot=(0.4,0.7,0.2),scale=(1,1,2.5),loc=(3,-2,1)); msg=pp(o,side_face(o),0.5); s=stats(o)
ax=(o.matrix_world.to_3x3()@Vector((0,0,1))).normalized(); c0=o.matrix_world.translation
RW=[((o.matrix_world@v.co-c0)-ax*(o.matrix_world@v.co-c0).dot(ax)).length for v in o.data.vertices]
chk("cylindre tourné, déplacé, à l'échelle 2,5 sur son axe : rayon monde 1,5 exact", msg=="" and max(abs(x-1.5) for x in RW)<1e-5 and abs(s["vol"]-ngon_area(64,1.5)*5)<1e-4 and solid_ok(s), (msg,min(RW),max(RW),s))
clear(); o=cyl(); top=[p.index for p in o.data.polygons if p.normal.z>0.9][0]; msg=pp(o,top,1.0); s=stats(o)
chk("bouchon du cylindre (face plane) : extrusion comme avant, hauteur 3", msg=="" and abs(s["vol"]-ngon_area(64,1.0)*3)<1e-5 and solid_ok(s), (msg,s))

# ---------------- 2. sphère : pas de pourtour, le rayon change ----------------
clear(); bm=bmesh.new(); bmesh.ops.create_uvsphere(bm,u_segments=32,v_segments=16,radius=2.0); o=mk("Sph",bm)
v0=stats(o)["vol"]; msg=pp(o,10,0.5); s=stats(o); R=[v.co.length for v in o.data.vertices]
chk("sphère r=2 tirée de 0,5 : tous les sommets à r=2,5", msg=="" and max(abs(x-2.5) for x in R)<1e-5 and abs(s["vol"]-v0*(2.5/2)**3)<1e-3 and solid_ok(s), (msg,min(R),max(R),s))

# ---------------- 3. trou cylindrique dans une boîte : le trou rétrécit / s'agrandit ----------------
def holed():
    clear(); a=box(); k=cyl(seg=48,r=1.0,h=6.0,loc=(0,0,2))
    out,_e=m.run_boolean('DIFFERENCE',[a],[k],True); C.view_layer.update(); return out[0]
def wall(o):
    for p in o.data.polygons:
        c=o.matrix_world@p.center
        if abs(p.normal.z)<0.5 and math.hypot(c.x,c.y)<1.2: return p.index
o=holed(); msg=pp(o,wall(o),0.25); s=stats(o)
chk("paroi d'un trou tirée de 0,25 (vers l'axe) : le trou passe à r=0,75", msg=="" and abs(s["vol"]-(64-ngon_area(48,0.75)*4))<1e-4 and solid_ok(s), (msg,s))
o=holed(); msg=pp(o,wall(o),-0.5); s=stats(o)
chk("paroi d'un trou poussée de 0,5 : le trou passe à r=1,5", msg=="" and abs(s["vol"]-(64-ngon_area(48,1.5)*4))<1e-4 and solid_ok(s), (msg,s))
o=holed(); v0=stats(o)["vol"]; msg=pp(o,wall(o),-1.5); s=stats(o)
chk("trou agrandi au-delà des murs de la boîte : refusé, solide intact", msg!="" and abs(s["vol"]-v0)<1e-9 and solid_ok(s), (msg,s))

# ---------------- 4. boîte à congés : le dessus reste une face plane ----------------
def filleted():
    clear(); bm=bmesh.new(); bmesh.ops.create_cube(bm,size=4)
    bmesh.ops.bevel(bm,geom=bm.edges[:],offset=0.5,segments=6,profile=0.5,affect='EDGES'); return mk("Fil",bm,loc=(0,0,2))
o=filleted(); v0=stats(o)["vol"]
top=max((p for p in o.data.polygons if p.normal.z>0.999),key=lambda p:p.area)
bm=bmesh.new(); bm.from_mesh(o.data); bm.faces.ensure_lookup_table(); bm.normal_update()
reg_top=m.pp_curved_region(bm,bm.faces[top.index])
fil=[f for f in bm.faces if 0.2<f.normal.z<0.95 and abs(f.normal.y)<1e-6 and f.normal.x>0][0]
reg_fil=m.pp_curved_region(bm,fil); big=max(f.calc_area() for f in bm.faces)
okfil=reg_fil is not None and all(f.calc_area()<big*0.5 for f in reg_fil)
bm.free()
chk("boîte à congés : le dessus est une face plane (pas absorbé par les congés)", reg_top is None)
chk("... un congé est une face courbe qui ne contient aucune grande face plane", okfil, None if reg_fil is None else len(reg_fil))
msg=pp(o,top.index,1.0); s=stats(o)
chk("... PushPull du dessus : extrusion plane (volume + 3x3x1)", msg=="" and abs(s["vol"]-(v0+9.0))<1e-4 and s["naked"]==0 and s["nonman"]==0, (msg,s,v0))

# ---------------- 5. demi-cylindre posé sur une face plane (arête vive à 90°) : la face plane s'élargit ----------------
def dshape(seg=32,r=1.0,h=2.0):
    clear(); bm=bmesh.new()
    ring=[(r*math.cos(math.pi*i/seg),r*math.sin(math.pi*i/seg)) for i in range(seg+1)]
    lo=[bm.verts.new((x,y,0)) for x,y in ring]; hi=[bm.verts.new((x,y,h)) for x,y in ring]
    for i in range(seg): bm.faces.new([lo[i],lo[i+1],hi[i+1],hi[i]])
    bm.faces.new([lo[seg],lo[0],hi[0],hi[seg]]); bm.faces.new(list(reversed(lo))); bm.faces.new(hi)
    bmesh.ops.recalc_face_normals(bm,faces=bm.faces[:]); return mk("D",bm)
def dvol(seg,r,h): return 0.5*seg*r*r*math.sin(math.pi/seg)*h
o=dshape(); v0=stats(o)["vol"]; chk("demi-cylindre : volume de départ exact", abs(v0-dvol(32,1,2))<1e-5, v0)
cf=[p.index for p in o.data.polygons if abs(p.normal.z)<0.5 and p.normal.y>0.5][0]
n0=len(o.data.polygons); msg=pp(o,cf,0.5); s=stats(o); R=radii(o)
chk("demi-cylindre tiré de 0,5 : demi-cylindre de rayon 1,5 exact (bord compris), la face plane s'élargit, même maillage", msg=="" and solid_ok(s) and max(abs(x-1.5) for x in R)<1e-5 and abs(s["vol"]-dvol(32,1.5,2))<1e-5 and len(o.data.polygons)==n0, (msg,s,min(R),max(R)))
o=dshape(); cf=[p.index for p in o.data.polygons if abs(p.normal.z)<0.5 and p.normal.y>0.5][0]
msg=pp(o,cf,-0.25); s=stats(o)
chk("demi-cylindre poussé de 0,25 : rayon 0,75 exact", msg=="" and solid_ok(s) and abs(s["vol"]-dvol(32,0.75,2))<1e-5, (msg,s))

# ---------------- 5b. forme oblongue (côtés plans tangents aux bouts ronds) : booléen vérifié, marche au raccord ----------------
def stadium(seg=16,r=1.0,L=2.0,h=2.0):
    clear(); bm=bmesh.new()
    prof=[(L/2+r*math.cos(-math.pi/2+math.pi*i/seg),r*math.sin(-math.pi/2+math.pi*i/seg)) for i in range(seg+1)]
    prof+=[(-L/2+r*math.cos(math.pi/2+math.pi*i/seg),r*math.sin(math.pi/2+math.pi*i/seg)) for i in range(seg+1)]
    lo=[bm.verts.new((x,y,0)) for x,y in prof]; hi=[bm.verts.new((x,y,h)) for x,y in prof]; n=len(prof)
    for i in range(n): bm.faces.new([lo[i],lo[(i+1)%n],hi[(i+1)%n],hi[i]])
    bm.faces.new(list(reversed(lo))); bm.faces.new(hi)
    bmesh.ops.recalc_face_normals(bm,faces=bm.faces[:]); return mk("Stad",bm)
o=stadium(); v0=stats(o)["vol"]
bm=bmesh.new(); bm.from_mesh(o.data); bm.faces.ensure_lookup_table(); bm.normal_update()
flatf=[f for f in bm.faces if f.normal.y>0.999][0]; endf=[f for f in bm.faces if f.normal.x>0.99][0]
rf=m.pp_curved_region(bm,flatf); re=m.pp_curved_region(bm,endf); ne=None if re is None else len(re); bm.free()
chk("forme oblongue : le côté plan est une face plane, le bout rond une face courbe de 16 facettes", rf is None and ne==16, (rf is None,ne))
cf=[p.index for p in o.data.polygons if p.normal.x>0.99][0]
t=time.perf_counter(); msg=pp(o,cf,0.5); dt=time.perf_counter()-t; s=stats(o)
exp=v0+0.5*16*math.sin(math.pi/16)*(1.5**2-1.0)*2
chk("bout rond tiré de 0,5 : matière ajoutée par booléen, volume exact, solide fermé", msg=="" and solid_ok(s) and abs(s["vol"]-exp)<1e-4, (msg,s,exp,round(dt,3)))
ys=[abs(v.co.y) for v in o.data.vertices if v.co.x<0.99]
xs=max(v.co.x for v in o.data.vertices)
chk("... les côtés plans n'ont pas bougé (marche de 0,5 perpendiculaire au raccord), bout à x=2,5", max(ys)<=1.0+1e-5 and abs(xs-2.5)<1e-5, (max(ys),xs))
o=stadium(); cf=[p.index for p in o.data.polygons if p.normal.x>0.99][0]
msg=pp(o,cf,-0.25); s=stats(o); exp=v0-0.5*16*math.sin(math.pi/16)*(1.0-0.75**2)*2
chk("bout rond poussé de 0,25 : matière retirée, volume exact, solide fermé", msg=="" and solid_ok(s) and abs(s["vol"]-exp)<1e-4, (msg,s,exp))
o=stadium(); cf=[p.index for p in o.data.polygons if p.normal.y>0.999][0]
msg=pp(o,cf,0.5); s=stats(o)
chk("côté plan tiré de 0,5 : extrusion plane (+ 2 x 2 x 0,5)", msg=="" and abs(s["vol"]-(v0+2.0))<1e-4 and s["naked"]==0, (msg,s,v0))

# ---------------- 5c. demi-sphère sur une boîte : l'équateur glisse sur le dessus ----------------
clear(); bm=bmesh.new(); bmesh.ops.create_uvsphere(bm,u_segments=32,v_segments=16,radius=1.0)
bmesh.ops.delete(bm,geom=[v for v in bm.verts if v.co.z<-1e-6],context='VERTS')
dome=mk("Dome",bm,loc=(0,0,4)); a=box()
bm=bmesh.new(); bm.from_mesh(dome.data); bmesh.ops.holes_fill(bm,edges=bm.edges[:]); bm.normal_update(); bmesh.ops.recalc_face_normals(bm,faces=bm.faces[:]); bm.to_mesh(dome.data); bm.free()
out,_e=m.run_boolean('UNION',[a,dome],[],True); C.view_layer.update(); o=out[0] if out else None
s0=stats(o) if o else None
if o:
    cf=[p.index for p in o.data.polygons if (o.matrix_world@p.center).z>4.3][0]
    msg=pp(o,cf,0.5); s=stats(o)
    RD=[(o.matrix_world@v.co-Vector((0,0,4))).length for v in o.data.vertices if (o.matrix_world@v.co).z>4.0-1e-6 and (o.matrix_world@v.co-Vector((0,0,4))).length<1.9]
    chk("demi-sphère r=1 sur une boîte, tirée de 0,5 : r=1,5 partout (équateur compris), solide fermé", msg=="" and solid_ok(s) and RD and max(abs(x-1.5) for x in RD)<1e-4, (msg,s,min(RD) if RD else None,max(RD) if RD else None))
else:
    chk("demi-sphère sur une boîte : union de départ", False, _e)

# ---------------- 6. surface courbe seule (voûte) : devient un solide d'épaisseur d ----------------
def vault(seg=32,r=2.0,h=3.0):
    clear(); bm=bmesh.new()
    ring=[(r*math.cos(math.pi*i/seg),r*math.sin(math.pi*i/seg)) for i in range(seg+1)]
    lo=[bm.verts.new((x,0,z)) for x,z in ring]; hi=[bm.verts.new((x,h,z)) for x,z in ring]
    for i in range(seg): bm.faces.new([lo[i],hi[i],hi[i+1],lo[i+1]])
    return mk("Vault",bm)
o=vault(); msg=pp(o,5,0.3); s=stats(o)
up=o.data.polygons[5].normal.z
RV=sorted({round(math.hypot(v.co.x,v.co.z),5) for v in o.data.vertices})
chk("voûte (surface ouverte) tirée de 0,3 : solide fermé entre r=2 et r=2,3 (ou 1,7)", msg=="" and solid_ok(s) and RV in ([2.0,2.3],[1.7,2.0]) and s["vol"]>0.5, (msg,s,RV))
exp=abs(0.5*32*math.sin(math.pi/32)*(RV[1]**2-RV[0]**2))*3
chk("... volume exact (anneau polygonal x longueur)", abs(s["vol"]-exp)<1e-4, (s["vol"],exp))

# ---------------- 7. cône : les voisines ne glissent pas -> booléen ----------------
clear(); bm=bmesh.new(); bmesh.ops.create_cone(bm,cap_ends=True,segments=48,radius1=1.5,radius2=0.0,depth=3.0); o=mk("Cone",bm)
v0=stats(o)["vol"]; cf=[p.index for p in o.data.polygons if abs(p.normal.z)<0.9][0]
msg=pp(o,cf,0.3); s=stats(o)
chk("cône : flanc tiré de 0,3, solide fermé, volume plus grand", msg=="" and solid_ok(s) and s["vol"]>v0*1.2, (msg,s,v0))

# ---------------- 8. l'outil : survol, clic, valeur tapée, aperçu, Annuler / Rétablir ----------------
def lying():
    clear(); return cyl(seg=48,r=1.0,h=4.0,rot=(0,math.pi/2,0),loc=(0,0,0))
def tool(evs):
    o=make(m.DESSIN_OT_pushpull); r=None
    with contextlib.redirect_stdout(io.StringIO()):
        r=type(o).invoke(o,ctx,ev('NONE','NOTHING',*scr(0,0)))
        for e in evs:
            if e[0]=='c': seq=[ev('MOUSEMOVE','NOTHING',*scr(e[1],e[2])),ev('LEFTMOUSE','PRESS',*scr(e[1],e[2])),ev('LEFTMOUSE','RELEASE',*scr(e[1],e[2]))]
            elif e[0]=='m': seq=[ev('MOUSEMOVE','NOTHING',*scr(e[1],e[2]))]
            elif e[0]=='t': seq=[ev(K[ch],'PRESS',*scr(0,0),unicode=ch,ascii=ch) for ch in e[1]]
            else: seq=[ev(e[0],'PRESS',*scr(0,0))]
            for x in seq:
                r=type(o).modal(o,ctx,x)
                if 'FINISHED' in r or 'CANCELLED' in r: return r,o
    return r,o
b=lying(); r,o=tool([('m',0.2,0.05)])
n_h=len(o.lines)//2
chk("survol d'une facette du cylindre : tout le flanc est surligné (2 cercles = 96 arêtes), pas la facette seule", n_h==96, n_h)
try: o.cleanup()
except Exception: pass
b=lying(); r,o=tool([('c',0.2,0.05),('t','0.5')])
far=max((p-Vector((p.x,0,0))).length for p in o.lines) if o.lines else 0
chk("aperçu pendant la saisie : présent", len(o.lines)>0, len(o.lines))
r=type(o).modal(o,ctx,ev('RET','PRESS',*scr(0,0))); C.view_layer.update(); s=stats(b)
RW=[math.hypot(v.co.x,v.co.y) for v in b.data.vertices]
chk("outil : clic sur le flanc, 0,5 tapé, Entrée -> r=1,5", 'FINISHED' in r and max(abs(x-1.5) for x in RW)<1e-5 and solid_ok(s), (r,min(RW),max(RW)))
b=lying(); r,o=tool([('c',0.2,0.05),('ESC',)]); s=stats(b)
chk("Échap : cylindre intact", 'CANCELLED' in r and abs(s["vol"]-ngon_area(48,1.0)*4)<1e-5, (r,s))
lying(); C.view_layer.update()
undo_redo("PushPull d'une face courbe", lambda: tool([('c',0.2,0.05),('t','0.5'),('RET',)]))

# ---------------- 9. temps de réponse sur un maillage dense ----------------
clear(); bm=bmesh.new(); bmesh.ops.create_cone(bm,cap_ends=True,segments=256,radius1=1,radius2=1,depth=4)
bmesh.ops.subdivide_edges(bm,edges=[e for e in bm.edges if abs(e.verts[0].co.z-e.verts[1].co.z)>1],cuts=63); o=mk("Dense",bm)
nf=len(o.data.polygons); cf=side_face(o)
t=time.perf_counter(); msg=pp(o,cf,0.5); dt=time.perf_counter()-t; s=stats(o)
chk(f"cylindre dense ({nf} faces) : décalage en moins de 1 s, solide fermé", msg=="" and dt<1.0 and s["naked"]==0 and abs(max(radii(o))-1.5)<1e-5, (msg,round(dt,3),s["vol"]))
op=make(m.DESSIN_OT_pushpull); t=time.perf_counter(); segs,nw=op.region_lines(o,cf); dt=time.perf_counter()-t
chk("... premier survol (contour + aperçu) en moins de 0,6 s", dt<0.6 and len(segs)>0, round(dt,3))
others=[p.index for p in o.data.polygons if abs(p.normal.z)<0.5][:400]
t=time.perf_counter()
for i in others: op.region_lines(o,i)
dt=(time.perf_counter()-t)/len(others)
chk("... survol des autres facettes de la même face : moins de 1 ms chacune (résultat gardé)", dt<0.001, round(dt*1000,4))
print("RESULTAT",sum(res),"/",len(res))
