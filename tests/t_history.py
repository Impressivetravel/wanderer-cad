import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
exec(open(_os.path.join(_HERE,'prec_lib.py')).read())
# History = Yes : Revolve, Extrude, Thicken, Pipe et les booléens gardent un modificateur de Blender (valeur modifiable après coup)
import bmesh, numpy as np
SEC="History"
def ev_stats(o):
    """(volume, fermé, boîte min, boîte max) du résultat évalué (modificateurs appliqués), en coordonnées monde."""
    dg=bpy.context.evaluated_depsgraph_get(); dg.update(); e=o.evaluated_get(dg); me=e.to_mesh()
    bm=bmesh.new(); bm.from_mesh(me); bm.transform(e.matrix_world)
    bmesh.ops.triangulate(bm,faces=bm.faces[:])
    closed=len(bm.faces)>0 and all(len(ed.link_faces)==2 for ed in bm.edges)
    vol=abs(bm.calc_volume()) if closed else 0.0
    P=np.array([tuple(v.co) for v in bm.verts]) if bm.verts else np.zeros((1,3))
    n=len(bm.faces); bm.free(); e.to_mesh_clear()
    return vol,closed,P.min(axis=0),P.max(axis=0),n
def near(a,b,t=1e-4): return abs(a-b)<=t*max(1.0,abs(b))
sq=[(np.array([(1,1,0),(3,1,0),(3,2,0),(1,2,0)],dtype=float),True)]
# --- Extrude ---
o=m.history_extrude(bpy.context,sq,Vector((0,0,2.5)),True)
v,c,lo,hi,n=ev_stats(o)
rec(SEC,"Extrude, Solid = Yes : un solide fermé de la bonne hauteur, au bon endroit",c and near(v,5.0) and near(lo[2],0,1e-6) and near(hi[2],2.5) and near(lo[0],1) and near(hi[0],3),(v,c,lo,hi))
rec(SEC,"... porté par un modificateur Solidify nommé Extrude, sur une simple face",[ (md.name,md.type) for md in o.modifiers]==[("Extrude",'SOLIDIFY')] and len(o.data.polygons)>=1 and o.get(m.HISTORY_KEY)=="Extrude",[(md.name,md.type) for md in o.modifiers])
o.modifiers[0].thickness=4.0
v,c,lo,hi,n=ev_stats(o)
rec(SEC,"... changer la valeur du modificateur change la hauteur (4 au lieu de 2.5)",c and near(v,8.0) and near(hi[2],4.0),(v,hi))
o=m.history_extrude(bpy.context,sq,Vector((0,0,-2.0)),True)
v,c,lo,hi,n=ev_stats(o)
rec(SEC,"Extrude vers le bas : le solide descend",c and near(v,4.0) and near(lo[2],-2.0) and near(hi[2],0,1e-6),(v,lo,hi))
o=m.history_extrude(bpy.context,sq,Vector((0,0,2.0)),False)
v,c,lo,hi,n=ev_stats(o)
rec(SEC,"Extrude, Solid = No : la surface seule (ouverte), 4 parois, modificateur Screw sans rotation",not c and n==8 and near(hi[2],2.0) and near(lo[2],0,1e-6) and o.modifiers[0].type=='SCREW' and o.modifiers[0].angle==0.0,(c,n,lo,hi))
opn=[(np.array([(0,0,0),(2,0,0),(2,3,0)],dtype=float),False)]
o=m.history_extrude(bpy.context,opn,Vector((0,0,1.5)),True)
v,c,lo,hi,n=ev_stats(o)
rec(SEC,"Extrude d'une courbe ouverte : deux parois, même avec Solid = Yes",not c and n==4 and near(hi[2],1.5) and near(hi[1],3.0),(c,n,hi))
hole=[(np.array([(0,0,0),(4,0,0),(4,4,0),(0,4,0)],dtype=float),True),(np.array([(1,1,0),(2,1,0),(2,2,0),(1,2,0)],dtype=float),True)]
o=m.history_extrude(bpy.context,hole,Vector((0,0,1.0)),True)
v,c,lo,hi,n=ev_stats(o)
rec(SEC,"Extrude d'un contour avec un trou : solide fermé, le trou est respecté (volume 15)",c and near(v,15.0),(v,c))
tilt=[(np.array([(0,0,0),(0,2,0),(0,2,2),(0,0,2)],dtype=float),True)]
o=m.history_extrude(bpy.context,tilt,Vector((3,0,0)),True)
v,c,lo,hi,n=ev_stats(o)
rec(SEC,"Extrude d'un profil debout, vers +X : solide fermé le long de X",c and near(v,12.0) and near(hi[0],3.0) and near(lo[0],0,1e-6),(v,lo,hi))
# --- Revolve ---
prof=[(np.array([(1,0,0),(2,0,0),(2,0,1),(1,0,1)],dtype=float),True)]
o=m.history_revolve(bpy.context,prof,Vector((0,0,0)),Vector((0,0,1)),360.0)
v,c,lo,hi,n=ev_stats(o)
V0,F0=m.revolve_surface(prof,(0,0,0),(0,0,1),360.0,True)
ref=m.mesh_object_from_arrays(bpy.context,"ref",V0,F0,(0,0,0),True); vr=ev_stats(ref)
rec(SEC,"Revolve 360° : solide fermé, même volume que la commande sans History",c and near(v,vr[0],1e-3) and near(hi[0],2.0,1e-3) and near(hi[2],1.0),(v,vr[0],c))
rec(SEC,"... porté par un modificateur Screw nommé Revolve",[(md.name,md.type) for md in o.modifiers]==[("Revolve",'SCREW')])
o.modifiers[0].angle=math.radians(90)
v2,c2,lo,hi,n=ev_stats(o)
rec(SEC,"... changer l'angle à 90° donne un quart de tour (ouvert aux deux bouts)",not c2 and lo[0]>-1e-4 and lo[1]>-1e-4 and near(hi[1],2.0,1e-3),(c2,lo,hi))
o=m.history_revolve(bpy.context,prof,Vector((5,5,0)),Vector((0,1,0)),180.0)
v,c,lo,hi,n=ev_stats(o)
V0,F0=m.revolve_surface(prof,(5,5,0),(0,1,0),180.0,False); P0=np.asarray(V0)
rec(SEC,"Revolve autour d'un axe quelconque : même encombrement que la commande sans History",np.allclose(lo,P0.min(axis=0),atol=2e-3) and np.allclose(hi,P0.max(axis=0),atol=2e-3),(lo,P0.min(axis=0),hi,P0.max(axis=0)))
# --- Thicken ---
me=bpy.data.meshes.new("s"); me.from_pydata([(0,0,0),(2,0,0),(2,2,0),(0,2,0)],[],[(0,1,2,3)]); me.update()
s=bpy.data.objects.new("s",me); bpy.context.scene.collection.objects.link(s)
t=m.history_thicken(bpy.context,s,0.5,'NORMAL',True)
v,c,lo,hi,n=ev_stats(t)
rec(SEC,"Thicken : solide fermé de la bonne épaisseur, du côté de la normale ; l'original est gardé",c and near(v,2.0) and near(hi[2],0.5) and near(lo[2],0,1e-6) and t is not s and not s.modifiers and t.modifiers[0].type=='SOLIDIFY',(v,lo,hi))
t=m.history_thicken(bpy.context,s,0.5,'BOTH',False)
v,c,lo,hi,n=ev_stats(t)
rec(SEC,"Thicken des deux côtés, sans garder l'original : le modificateur est posé sur la surface elle-même",c and near(v,2.0) and near(hi[2],0.25) and near(lo[2],-0.25) and t is s,(v,lo,hi))
# --- Pipe ---
line=[(np.array([(0,0,0),(0,0,4)],dtype=float),False)]
p=m.history_pipe(bpy.context,None,line,0.5,True,48)
v,c,lo,hi,n=ev_stats(p)
p2=m.history_pipe(bpy.context,None,line,0.5,False,48); n2=ev_stats(p2)[4]
rec(SEC,"Pipe : une courbe avec une épaisseur (rayon 0.5), avec ses bouchons",p.type=='CURVE' and near(p.data.bevel_depth,0.5) and p.data.use_fill_caps and n>n2>0 and near(hi[0],0.5,1e-3) and near(hi[2],4.0) and p.get(m.HISTORY_KEY)=="Pipe",(n,n2,hi))
p.data.bevel_depth=1.0
v,c,lo,hi,n=ev_stats(p)
rec(SEC,"... changer l'épaisseur de la courbe change le rayon",near(hi[0],1.0,1e-3),hi)
cu=bpy.data.curves.new("c",'CURVE'); sp=cu.splines.new('POLY'); sp.points.add(1); sp.points[0].co=(0,0,0,1); sp.points[1].co=(2,0,0,1)
co=bpy.data.objects.new("c",cu); bpy.context.scene.collection.objects.link(co); co.scale=(2,2,2); bpy.context.view_layer.update()
p=m.history_pipe(bpy.context,co,None,0.5,False,48)
v,c,lo,hi,n=ev_stats(p)
rec(SEC,"Pipe d'une courbe mise à l'échelle : le rayon reste celui demandé ; la courbe d'origine n'est pas touchée",near(hi[1],0.5,1e-3) and near(hi[0],4.0,1e-3) and co.data.bevel_depth==0.0 and p.data is not co.data,(hi,))
# --- Booléens ---
def box(name,x):
    bm=bmesh.new(); bmesh.ops.create_cube(bm,size=2.0); me=bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    o=bpy.data.objects.new(name,me); bpy.context.scene.collection.objects.link(o); o.location=(x,0,0); return o
a,b=box("a",0),box("b",1); bpy.context.view_layer.update()
res,err=m.history_boolean('DIFFERENCE',[a],[b])
v,c,lo,hi,n=ev_stats(a)
rec(SEC,"Boolean Difference : modificateur Boolean, résultat fermé de volume 4 ; l'opérande reste, en fil de fer et hors rendu",
    not err and res==[a] and c and near(v,4.0,1e-3) and a.modifiers[0].type=='BOOLEAN' and b.display_type=='WIRE' and b.hide_render and b.get(m.CUTTER_KEY)==1,(v,c,err))
b.location=(1.5,0,0); bpy.context.view_layer.update()
v,c,lo,hi,n=ev_stats(a)
rec(SEC,"... déplacer l'opérande met le résultat à jour (volume 6)",c and near(v,6.0,1e-3),v)
a,b,c3=box("a",0),box("b",1),box("c",-1); bpy.context.view_layer.update()
res,err=m.history_boolean('UNION',[a,b,c3],[])
v,c,lo,hi,n=ev_stats(a)
rec(SEC,"Boolean Union de trois objets : un seul résultat fermé (volume 16)",not err and res==[a] and c and near(v,16.0,1e-3) and len(a.modifiers)==2,(v,c))
a,b=box("a",0),box("b",1); bpy.context.view_layer.update()
res,err=m.history_boolean('INTERSECT',[a],[b])
v,c,lo,hi,n=ev_stats(a)
rec(SEC,"Boolean Intersection : le volume commun (4)",not err and c and near(v,4.0,1e-3),(v,c))
res,err=m.history_boolean('SPLIT',[a],[b])
rec(SEC,"Boolean Split n'a pas de version History : message, rien n'est créé",res==[] and bool(err),err)
# ---- les commandes elles-mêmes : la touche H bascule History, la valeur est mémorisée ----
SEC="History (commandes)"
def rect(name,x0,y0,x1,y1): return m.build_polyline(bpy.context,name,[Vector(p) for p in [(x0,y0,0),(x1,y0,0),(x1,y1,0),(x0,y1,0)]],True)
clear(); m._HISTORY_MEM.clear(); R=rect("R",0,0,8,5); bpy.context.view_layer.update()
new,r,o=run("extrude_crv",[C(0,0),M(0,3),T(7.5),'RET'],sel=[R])
rec(SEC,"Extrude Curve sans H : un maillage figé, sans modificateur, comme avant",len(new)==1 and not new[0].modifiers and len(new[0].data.polygons)>=6 and "[H: History = No]" in o.prompt(),[(x.name,len(x.modifiers)) for x in new])
clear(); R=rect("R",0,0,8,5); bpy.context.view_layer.update()
new,r,o=run("extrude_crv",['H',C(0,0),M(0,3),T(7.5),'RET'],sel=[R])
ok=len(new)==1 and [md.type for md in new[0].modifiers]==['SOLIDIFY']
v,c,lo,hi,n=ev_stats(new[0]) if ok else (0,False,0,0,0)
rec(SEC,"Extrude Curve avec H : solide 8 x 5 x 7.5 porté par un modificateur ; la courbe d'origine est gardée",ok and c and near(v,300.0) and near(hi[2],7.5) and "R" in bpy.data.objects,(v,c,hi))
rec(SEC,"... History est mémorisé pour la commande suivante, et l'invite le montre",m.history_on("dessin.extrude_crv") and "[H: History = Yes]" in o.prompt(),o.prompt()[:90])
clear(); R=rect("R",0,0,8,5); bpy.context.view_layer.update()
new,r,o=run("extrude_crv",[C(0,0),'B',M(0,3),T(2),'RET'],sel=[R])
rec(SEC,"History avec BothSides : pas de modificateur possible, le maillage habituel est créé",len(new)==1 and not new[0].modifiers and len(new[0].data.polygons)>=6,[(x.name,len(x.modifiers)) for x in new])
m._OPT_MEM.clear()
clear(); R=rect("R",0,0,8,5); bpy.context.view_layer.update()
new,r,o=run("extrude_crv",['H',C(0,0),M(0,3),T(7.5),'RET'],sel=[R])
rec(SEC,"H une seconde fois : retour à History = No",len(new)==1 and not new[0].modifiers and not m.history_on("dessin.extrude_crv"),[(x.name,len(x.modifiers)) for x in new])
clear(); L=m.build_polyline(bpy.context,"L",[Vector((2,0,0)),Vector((3,0,0))],False); bpy.context.view_layer.update()
new,r,o=run("revolve",['H',C(0,0),C(0,5),'RET'],sel=[L])
ok=len(new)==1 and [md.type for md in new[0].modifiers]==['SCREW']
v,c,lo,hi,n=ev_stats(new[0]) if ok else (0,False,np.zeros(3),np.zeros(3),0)
rec(SEC,"Revolve avec H : couronne autour de l'axe Y, modificateur Screw de 360°",ok and near(hi[0],3.0,1e-3) and near(lo[0],-3.0,1e-3) and near(hi[2],3.0,1e-3) and near(abs(new[0].modifiers[0].angle),2*math.pi),(lo,hi,r))
m._HISTORY_MEM.clear()
o=make(m.DESSIN_OT_subd_revolve)
rec(SEC,"SubD Revolve et Boolean Split ne proposent pas History",not m.DESSIN_OT_subd_revolve.HISTORY_OK and not m.DESSIN_OT_bool_split.HISTORY_OK and m.DESSIN_OT_bool_union.HISTORY_OK)
# Thicken et Pipe : case History de la boîte de dialogue
clear(); me=bpy.data.meshes.new("s"); me.from_pydata([(0,0,0),(2,0,0),(2,2,0),(0,2,0)],[],[(0,1,2,3)]); me.update()
s=bpy.data.objects.new("s",me); bpy.context.scene.collection.objects.link(s); s.select_set(True); bpy.context.view_layer.update()
o=make(m.DESSIN_OT_thicken); o.thickness=0.5; o.direction='NORMAL'; o.delete_input=True; o.history=True
with contextlib.redirect_stdout(io.StringIO()): r=type(o).execute(o,bpy.context)
rec(SEC,"Thicken avec History : la surface garde sa face unique et reçoit un Solidify de 0.5",'FINISHED' in r and len(s.data.polygons)==1 and [md.type for md in s.modifiers]==['SOLIDIFY'] and near(s.modifiers[0].thickness,0.5),r)
clear(); L=m.build_polyline(bpy.context,"L",[Vector((0,0,0)),Vector((4,0,0))],False); L.select_set(True); bpy.context.view_layer.objects.active=L; bpy.context.view_layer.update()
o=make(m.DESSIN_OT_pipe); o.radius=0.5; o.cap=True; o.delete_input=False; o.history=True
with contextlib.redirect_stdout(io.StringIO()): r=type(o).execute(o,bpy.context)
pp=[x for x in bpy.data.objects if x.name!="L"]
rec(SEC,"Pipe avec History : une courbe épaisse de rayon 0.5 ; la courbe d'origine est gardée",'FINISHED' in r and len(pp)==1 and pp[0].type=='CURVE' and near(pp[0].data.bevel_depth,0.5) and "L" in bpy.data.objects,(r,[x.name for x in pp]))
# ---- affichage : History garde sa puce sous la ligne de commande, que ce soit Yes ou No ----
SEC="History (ligne de commande)"
def chips_of(txt): return m.cmd_parse_prompt(txt)
for on in (False,True):
    lab="History = "+("Yes" if on else "No")
    o=make(m.DESSIN_OT_extrude_crv); o.points=[]; o.center=True; o.history=on; o.mode=0; o.both=o.taper=o.topoint=False; o.draft=5.0
    t1=chips_of("Extrude : "+type(o).prompt(o)); o.points=[Vector((0,0,0))]; t2=chips_of("Extrude : "+type(o).prompt(o))
    rec(SEC,f"Extrude, {lab} : puce H à la première invite (avec la puce Solid) et à la seconde ; rien dans la phrase",
        ("H",lab) in t1[3] and ("C","Solid = Yes") in t1[3] and ("H",lab) in t2[3] and "History" not in t1[1]+t2[1]+" ".join(t1[2]+t2[2]),(t1[3],t2[3]))
    o=make(m.DESSIN_OT_revolve); o.points=[Vector((0,0,0)),Vector((0,1,0))]; o.center=True; o.history=on; o.mode=0
    t=chips_of("Revolve : "+type(o).prompt(o))
    rec(SEC,f"Revolve, {lab} : puce H",("H",lab) in t[3] and "History" not in t[1]+" ".join(t[2]),t[3])
    txt=("Boolean Difference : select the objects to subtract FROM   (click: select / deselect, A: all)   |   0 selected   |   "
         "Enter/Space: confirm   D: delete input = yes   "+m.history_label(on)+"   Esc: cancel")
    t=chips_of(txt)
    rec(SEC,f"Booléens, {lab} : puce H, entre D et Esc ; rien ne reste dans le texte",
        ("H",lab) in t[3] and [k for k,_l in t[3]][-3:]==["D","H","Esc"] and not any("History" in e[0] for e in t[4]),(t[3],t[4]))
summary()
