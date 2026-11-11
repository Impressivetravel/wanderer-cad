# Gumball : sphère d'extrusion et trait de coupe (règles d'affichage par axe, extrusion, coupe / ajout, face poussée)
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
src=open(_os.path.join(_HERE,'t_pushpull.py')).read()
exec(src[src.index("\n")+1:src.index("# ---------------- 1. PushPull")])
X,Y,Z=0,1,2
AX=m.AXES3
st=C.scene.dessin; st.gumball=True
def sel(*objs):
    if C.mode!='OBJECT': bpy.ops.object.mode_set(mode='OBJECT')
    for q in bpy.data.objects: q.select_set(q in objs)
    C.view_layer.objects.active=objs[0] if objs else None
    C.view_layer.update()
def info():
    r=m.gumball_pull_info(C,AX,fresh=True); return sorted(r["ext"]),sorted(r["cut"])
def poly(name,pts,closed=True): return m.build_polyline(C,name,[Vector(p) for p in pts],closed)
rect_xy=[(0,0,0),(2,0,0),(2,1,0),(0,1,0)]
rect_xz=[(0,0,0),(2,0,0),(2,0,1),(0,0,1)]

# ---------------- 1. sur quelles flèches les poignées s'affichent ----------------
clear(); c=poly("c",rect_xy); sel(c)
chk("courbe plane fermée à plat : sphère et trait sur Z seulement", info()==([Z],[Z]), info())
clear(); c=poly("c",rect_xz); sel(c)
chk("courbe plane fermée debout (plan XZ) : sphère et trait sur Y seulement", info()==([Y],[Y]), info())
clear(); c=poly("c",[(0,0,0),(2,0,0),(2,1,0)],False); sel(c)
chk("courbe plane ouverte : sphère sur Z, pas de trait de coupe", info()==([Z],[]), info())
clear(); c=poly("c",[(0,0,0),(3,0,0)],False); sel(c)
chk("droite le long de X : sphère sur Y et Z, pas le long d'elle", info()==([Y,Z],[]), info())
clear(); c=poly("c",[(0,0,0),(2,0,0.5),(2,1,0),(0,1,0.7)]); sel(c)
chk("courbe non plane : sphère sur les trois axes, pas de trait", info()==([X,Y,Z],[]), info())
clear(); c=poly("c",rect_xy); c.rotation_euler=(0.6,0,0); sel(c)
chk("courbe plane inclinée : sphère sur Y et Z (pas X, dans son plan), pas de trait (axe non perpendiculaire)", info()==([Y,Z],[]), info())
clear(); me=bpy.data.meshes.new("S"); me.from_pydata([(-2,-2,0),(2,-2,0),(2,2,0),(-2,2,0)],[],[(0,1,2,3)])
sf=bpy.data.objects.new("S",me); C.scene.collection.objects.link(sf); sel(sf)
chk("surface plane : sphère sur Z, pas de trait", info()==([Z],[]), info())
clear(); b=box(); sel(b)
chk("solide entier : aucune poignée", info()==([],[]), info())
clear(); b=box(); c=poly("c",rect_xy); sel(c,b)
chk("courbe + solide sélectionnés : aucune poignée", info()==([],[]), info())
clear(); b=box(); sel(b); bpy.ops.object.mode_set(mode='EDIT')
def pick(b,cond):
    bm=bmesh.from_edit_mesh(b.data)
    for f in bm.faces: f.select_set(False)
    for f in bm.faces:
        if cond(f): f.select_set(True)
    bm.select_flush_mode(); bmesh.update_edit_mesh(b.data)
pick(b,lambda f: f.normal.x>0.9)
chk("face d'un solide sélectionnée (+X) : sphère et trait sur X", info()==([X],[X]), info())
pick(b,lambda f: f.normal.x>0.9 or f.normal.z>0.9)
r=info(); chk("deux faces non coplanaires : pas de trait de coupe", r[1]==[], r)
bpy.ops.object.mode_set(mode='OBJECT')

# ---------------- 2. la commande ----------------
def pull(kind, axis, evs, ctrl=False, shift=False):
    o=make(m.DESSIN_OT_gumball_pull); o.pull=kind; o.axis=axis
    piv,_t=m.gumball_selection(C)
    sx,sy=scr(piv.x,piv.y)
    def E2(e):
        e.ctrl=ctrl; e.shift=shift; return e
    with contextlib.redirect_stdout(io.StringIO()):
        r=type(o).invoke(o,ctx,E2(ev('LEFTMOUSE','PRESS',sx,sy)))
        if 'RUNNING_MODAL' not in r: return r,o
        for e in evs:
            if e[0]=='drag':
                seq=[ev('MOUSEMOVE','NOTHING',*scr(piv.x+e[1]*k/4,piv.y+e[2]*k/4)) for k in range(1,5)]+[ev('LEFTMOUSE','RELEASE',*scr(piv.x+e[1],piv.y+e[2]))]
            elif e[0]=='click': seq=[ev('LEFTMOUSE','RELEASE',sx,sy)]
            elif e[0]=='t': seq=[ev(K[ch],'PRESS',sx,sy,unicode=ch,ascii=ch) for ch in e[1]]
            else: seq=[ev(e[0],'PRESS',sx,sy)]
            for x in seq:
                r=type(o).modal(o,ctx,E2(x))
                if 'FINISHED' in r or 'CANCELLED' in r: return r,o
    return r,o
st.gumball_drag='SMOOTH' if hasattr(st,'gumball_drag') else None
def bbox(ob):
    bb=[ob.matrix_world@Vector(b) for b in ob.bound_box]
    return tuple(round(min(v[i] for v in bb),5) for i in range(3)),tuple(round(max(v[i] for v in bb),5) for i in range(3))
clear(); c=poly("c",rect_xz); sel(c)
r,o=pull('EXTRUDE',Y,[('drag',0,3)])
ex=[q for q in bpy.data.objects if q.name.startswith("Extrusion")]
chk("sphère : glisser extrude la courbe le long de la flèche (3)", 'FINISHED' in r and len(ex)==1 and bbox(ex[0])==((0,0,0),(2,3,1)) and solid_ok(stats(ex[0])), (r,bbox(ex[0]) if ex else None))
chk("... la courbe reste sélectionnée (on peut continuer)", c.select_get() and c.name in bpy.data.objects)
clear(); c=poly("c",rect_xz); sel(c)
r,o=pull('EXTRUDE',Y,[('click',),('t','2.5'),('RET',)])
ex=[q for q in bpy.data.objects if q.name.startswith("Extrusion")]
chk("sphère : clic puis valeur saisie (2,5)", 'FINISHED' in r and len(ex)==1 and bbox(ex[0])==((0,0,0),(2,2.5,1)), (r,bbox(ex[0]) if ex else None))
clear(); c=poly("c",rect_xz); sel(c)
r,o=pull('EXTRUDE',Y,[('drag',0,1)],shift=True)
ex=[q for q in bpy.data.objects if q.name.startswith("Extrusion")]
chk("sphère + Maj : des deux côtés", 'FINISHED' in r and len(ex)==1 and bbox(ex[0])==((0,-1,0),(2,1,1)), (r,bbox(ex[0]) if ex else None))
clear(); c=poly("c",rect_xz); sel(c)
r,o=pull('EXTRUDE',X,[('drag',2,0)])
chk("sphère refusée sur un axe du plan de la courbe", 'CANCELLED' in r and len(bpy.data.objects)==1, r)
clear(); c=poly("c",rect_xz); sel(c)
r,o=pull('EXTRUDE',Y,[('drag',0,3),])
clear(); c=poly("c",rect_xz); sel(c)
r,o=pull('EXTRUDE',Y,[('ESC',)])
chk("Échap : rien n'est créé", 'CANCELLED' in r and len(bpy.data.objects)==1, r)

# trait de coupe : courbe posée sur la face avant (y = -2) d'une boîte 4x4x4 (z 0..4)
front=[(-1,-2,1),(1,-2,1),(1,-2,3),(-1,-2,3)]      # 2 x 2
def cut_case(name, pts, dy, expect, ctrl=False):
    clear(); b=box(); c=poly("c",pts); sel(c)
    r,o=pull('CUT',Y,[('drag',0,dy)],ctrl=ctrl); C.view_layer.update()
    s=stats(b)
    chk(name, ('FINISHED' in r)==(expect is not None) and (expect is None or (abs(s["vol"]-expect)<1e-4 and solid_ok(s))), (r,s))
    return b
cut_case("trait : pousser dans le solide retire de la matière (poche de 1)", front, 1.0, 64-4)
cut_case("trait : pousser au travers perce le solide", front, 5.0, 64-16)
cut_case("trait : tirer vers l'extérieur ajoute de la matière (1)", front, -1.0, 64+4)
cut_case("trait + Ctrl en poussant dans la matière : rien à ajouter, solide intact", front, 1.0, None, ctrl=True)
away=[(-1,-3,1),(1,-3,1),(1,-3,3),(-1,-3,3)]     # courbe flottante, 1 devant la boîte
cut_case("courbe flottante poussée dans le solide : coupe (2 de profondeur)", away, 3.0, 64-8)
cut_case("courbe flottante + Ctrl : ajoute (bossage de 1 devant)", away, 3.0, 64+4, ctrl=True)
cut_case("courbe flottante tirée à l'opposé : rien à couper, solide intact", away, -2.0, None)
clear(); b=box(); c=poly("c",front); sel(c)
undo_redo("trait de coupe du Gumball", lambda: pull('CUT',Y,[('drag',0,1.0)]))
s=stats(bpy.data.objects["Box"]); chk("... après Rétablir : poche toujours propre", abs(s["vol"]-60)<1e-4 and solid_ok(s), s)

# trait sur une face sélectionnée (mode Édition) = PushPull
def face_case(name, d, expect, msg=False):
    clear(); b=box(); sel(b); bpy.ops.object.mode_set(mode='EDIT')
    pick(b,lambda f: f.normal.x>0.9)
    r,o=pull('CUT',X,[('drag',d,0)])
    nsel=b.data.total_face_sel
    bpy.ops.object.mode_set(mode='OBJECT'); C.view_layer.update(); s=stats(b)
    chk(name, abs(s["vol"]-expect)<1e-4 and solid_ok(s) and (('CANCELLED' in r) if msg else ('FINISHED' in r and nsel==1)), (r,s,nsel))
face_case("trait sur une face : tirer de 1 ajoute (volume 80), la face reste sélectionnée", 1.0, 80)
face_case("trait sur une face : pousser de 1 retire (volume 48)", -1.0, 48)
face_case("trait sur une face : pousser tout le solide est refusé, solide intact", -4.0, 64, msg=True)
def run_face():
    b=bpy.data.objects["Box"]; sel(b); bpy.ops.object.mode_set(mode='EDIT')
    pick(b,lambda f: f.normal.x>0.9)
    pull('CUT',X,[('drag',-1.0,0)]); bpy.ops.object.mode_set(mode='OBJECT')
clear(); box(); C.view_layer.update()
undo_redo("trait du Gumball sur une face", run_face)
# ---------------- solide + surface libre dans le même objet (face dupliquée restée dans le maillage) ----------------
import numpy as _np
def _mixed():
    clear(); bm=bmesh.new(); bmesh.ops.create_cube(bm,size=4)
    vs=[bm.verts.new(c) for c in ((-2,-2,5),(2,-2,5),(2,2,5),(-2,2,5))]; bm.faces.new(vs)
    me=bpy.data.meshes.new("Mix"); bm.to_mesh(me); bm.free()
    o=bpy.data.objects.new("Mix",me); C.scene.collection.objects.link(o); o.location=(0,0,2); C.view_layer.update(); return o
def _cutc(pts,vec,boss=False):
    c=m.build_polyline(C,"r",[Vector(p) for p in pts],True); C.view_layer.update()
    paths=[(_np.asarray(P,dtype=_np.float64),bool(cl)) for P,cl in m.outline_paths(c,C.evaluated_depsgraph_get())]
    r=m.gumball_cut(C,[c],paths,Vector(vec),boss); C.view_layer.update(); return r
o=_mixed(); n_me=len(bpy.data.meshes); n_ob=len(bpy.data.objects)
r=_cutc([(-4,-0.5,1),(-4,0.5,1),(-4,0.5,2),(-4,-0.5,2)],(3.5,0,0)); s=stats(o)
_sh,_rs=m.split_closed_shells(o.data); _b=bmesh.new(); _b.from_mesh(_sh); _vol=abs(_b.calc_volume()); _b.free()
chk("solide + face libre dans le même objet : la coupe se fait (1 x 1 x 1,5 retiré), la face libre est gardée",
    r==("",1,0) and abs(_vol-(64-1.5))<1e-5 and s["naked"]==4 and s["nonman"]==0 and len(_rs.polygons)==1, (r,_vol,s))
for q in (_sh,_rs): bpy.data.meshes.remove(q)
chk("... aucun objet ni maillage temporaire laissé", len(bpy.data.objects)==n_ob+1 and len(bpy.data.meshes)==n_me, (len(bpy.data.objects),n_ob,len(bpy.data.meshes),n_me))
sh,rest=m.split_closed_shells(o.data)
chk("... split_closed_shells : coque fermée d'un côté, 1 face libre de l'autre", sh is not None and len(rest.polygons)==1 and m.mesh_is_closed(sh), (sh,rest))
for q in (sh,rest): bpy.data.meshes.remove(q)
clear(); me=bpy.data.meshes.new("S"); me.from_pydata([(-2,-2,0),(2,-2,0),(2,2,0),(-2,2,0),(-2,-2,3),(2,-2,3),(2,2,3),(-2,2,3)],[],[(0,1,2,3),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)])
o=bpy.data.objects.new("Open",me); C.scene.collection.objects.link(o); C.view_layer.update(); v0=len(o.data.polygons)
r=_cutc([(-4,-0.5,1),(-4,0.5,1),(-4,0.5,2),(-4,-0.5,2)],(3.5,0,0))
chk("boîte ouverte (sans dessus) : refus avec un message qui nomme l'objet, rien n'est modifié", r[1:]==(0,0) and "Open" in r[0] and "closed" in r[0] and len(o.data.polygons)==v0, r)
print("RESULTAT",sum(res),"/",len(res))
