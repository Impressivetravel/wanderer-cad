import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
exec(open(_os.path.join(_HERE,'prec_lib.py')).read())
from mathutils import Euler
V3=lambda *a: Vector(a)
SEC="Scènes atypiques"
st=bpy.context.scene.dessin
for k in ("end","near","point","mid","cen","int","quad","vertex"): setattr(st,"osnap_"+k,True)
# objet tourné, à échelle non uniforme et négative, parenté : l'accrochage doit donner la position MONDE exacte
clear()
me=bpy.data.meshes.new("Box"); bm=bmesh.new(); bmesh.ops.create_cube(bm,size=2); bm.to_mesh(me); bm.free()
par=bpy.data.objects.new("Par",None); bpy.context.scene.collection.objects.link(par); par.location=(5,3,0); par.rotation_euler=Euler((0,0,0.6)); par.scale=(1.5,1.5,1.5)
box=bpy.data.objects.new("Box",me); bpy.context.scene.collection.objects.link(box); box.parent=par; box.location=(1,2,0); box.rotation_euler=Euler((0,0,0.35)); box.scale=(2.0,-0.7,1.0)
rect=m.build_polyline(bpy.context,"R",[V3(0,0,0),V3(4,0,0),V3(4,2,0),V3(0,2,0)],True); rect.parent=par; rect.rotation_euler=Euler((0,0,-0.4)); rect.scale=(0.5,2.0,1.0); rect.location=(-3,1,0)
bpy.context.view_layer.update()
d=m.collect_snap_points(ctx); m._screen_index(d,np.array(rv3d.perspective_matrix,dtype=np.float64),region,allow_async=False)
errs=[]
for ob in (box,rect):
    mw=ob.matrix_world
    pts=[mw@v.co for v in ob.data.vertices] if ob.type=='MESH' else [mw@Vector(p.co[:3]) for p in ob.data.splines[0].points]
    for p in pts:
        if abs(p.z)>1e-6 and ob.type=='MESH': 
            if p.z<0: continue          # sommets du bas cachés derrière ceux du haut en vue de dessus
        r=m.find_snap_in(d,*scr(p.x,p.y),region,rv3d)
        errs.append((r[0]-p).length if r is not None else 9.0)
rec(SEC,"Accrochage sur des objets tournés / échelle non uniforme et négative / parentés : position monde exacte",max(errs)<1e-5,f"{len(errs)} sommets, écart max {max(errs):.2e}")
# extrusion d'une courbe transformée : le solide suit la forme monde
for ob in bpy.context.view_layer.objects: ob.select_set(False)
exp=[rect.matrix_world@Vector(p.co[:3]) for p in rect.data.splines[0].points]
new,r,o=run("extrude_crv",[C(float(exp[0].x),float(exp[0].y)),M(float(exp[0].x),float(exp[0].y)+3),T(2.5),'RET'],sel=[rect])
if new:
    V=mverts(new[0]); base=V[np.abs(V[:,2])<1e-6]; top=V[np.abs(V[:,2]-2.5)<1e-6]
    de=max(min(np.linalg.norm(base-np.array(e),axis=1)) for e in exp)
    v,a,nk,nm=vol_area(new[0]); ar=m.loop_area(exp)
    rec(SEC,"Extrude Curve d'un rectangle parenté / tourné / mis à l'échelle : base sur la courbe, volume = aire x 2.5",de<1e-5 and abs(v-ar*2.5)<1e-4*max(1,ar),f"écart base {de:.2e}, volume {v:.6f} vs {ar*2.5:.6f}, fermé={nk==0}")
else: rec(SEC,"Extrude Curve transformé",False,str((r,o._reports)))
# plan de construction personnalisé : ce qu'on dessine est dans le plan
clear()
stc=m.cp_state(rv3d,create=True)
x=Vector((1,0.4,0.3)).normalized(); z=x.cross(Vector((0,1,0.5))).normalized(); y=z.cross(x); org=Vector((2,-3,4))
stc["cur"]=(org,x,y,z)
new,r,o=run("polyligne",[C(3,3),C(9,4),C(8,8),C(1,7),'RET'],p0=(3,3))
if new:
    P=ctrl_pts(new[0])[0]; dist=np.abs((P-np.array(org))@np.array(z))
    rec(SEC,"CPlane incliné : la polyligne dessinée est dans le plan de construction",dist.max()<1e-5,f"distance au plan max {dist.max():.2e} (axe de l'outil : {getattr(o,'axis',None)})")
else: rec(SEC,"CPlane incliné",False,str((r,o._reports)))
clear(); stc["cur"]=(org,x,y,z)
new,r,o=run("cercle",[C(-6,-5),M(-3,-5),T(2),'RET'],p0=(-6,-5))
if new:
    ob=new[0]; B=bez_eval(ob); dist=np.abs((B-np.array(org))@np.array(z)); c=np.array(ob.matrix_world@Vector(ob.get("dessin_centre"))) if ob.get("dessin_centre") is not None else B.mean(0)
    rr=np.linalg.norm(B-c,axis=1)
    rec(SEC,"CPlane incliné : cercle r=2 dans le plan, rayon exact",dist.max()<1e-5 and abs(rr-2).max()<1e-4,f"distance au plan {dist.max():.2e}, rayon {rr.min():.6f}..{rr.max():.6f}")
stc["cur"]=None
summary()
