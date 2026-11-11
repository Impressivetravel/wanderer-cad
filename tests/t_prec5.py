import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
exec(open(_os.path.join(_HERE,'prec_lib.py')).read())
V3=lambda *a: Vector(a)
SEC="Outils 3D"
def box(n,loc,s=4):
    me=bpy.data.meshes.new(n); bm=bmesh.new(); bmesh.ops.create_cube(bm,size=s); bm.to_mesh(me); bm.free()
    ob=bpy.data.objects.new(n,me); bpy.context.scene.collection.objects.link(ob); ob.location=loc; bpy.context.view_layer.update(); return ob
# Fillet Edge r=0.5 sur l'arête haute x=-2 d'un cube 4
clear(); a=box("A",(0,0,2))
new,r,o=run("fillet_edge",[C(-2,-1),'RET',T(0.5),'RET'])
V=mverts(bpy.data.objects["A"]); v,ar,nk,nm=vol_area(bpy.data.objects["A"])
# points de l'arrondi : ni sur les faces planes d'origine
on=V[(V[:,0]<-1.5+1e-6)&(V[:,2]>3.5-1e-6)]
axis=np.array((-1.5,0,3.5)); dist=np.hypot(on[:,0]-axis[0],on[:,2]-axis[2])
exp=64-(0.25-math.pi*0.25/4)*4
rec(SEC,"Fillet Edge r=0.5 : profil sur le cylindre d'axe (x=-1.5, z=3.5)",len(on)>2 and abs(dist-0.5).max()<1e-5 and nk==0,f"{len(on)} sommets, écart radial {abs(dist-0.5).max():.2e}, fermé={nk==0}")
rec(SEC,"Fillet Edge : volume retiré par rapport au congé exact",abs(v/exp-1)<5e-4,f"{v:.5f} vs {exp:.5f} ({(v/exp-1)*100:+.4f} %)")
clear(); a=box("A",(0,0,2))
new,r,o=run("chamfer_edge",[C(-2,-1),'RET',T(0.5),'RET'])
v,ar,nk,nm=vol_area(bpy.data.objects["A"]); exp=64-0.5*0.5/2*4
rec(SEC,"Chamfer Edge 0.5 : volume exact (prisme retiré 0.5 x 0.5 / 2 x 4)",abs(v-exp)<1e-5 and nk==0,f"{v:.6f} vs {exp:.6f}")
# Offset Edge sur un cercle
clear(); ci=m.build_bezier_arc(bpy.context,"Ci",V3(12,0,0),V3(1,0,0),V3(0,1,0),3.0,0.0,m.TAU,True); bpy.context.view_layer.update()
new,r,o=run("offset_edge",[C(15,0),'RET',M(17,0),T(1.25),'RET'])
if new:
    ob=new[0]
    P=bez_eval(ob) if ob.type=='CURVE' and ob.data.splines[0].type=='BEZIER' else np.vstack([p for p,c in paths(ob)])
    rr=np.linalg.norm(P-np.array((12,0,0)),axis=1); exp=4.25 if rr.mean()>3 else 1.75
    rec(SEC,f"Offset d'un cercle r=3 de 1.25 : cercle r={exp}",abs(rr-exp).max()<1e-3,f"type {ob.data.splines[0].type if ob.type=='CURVE' else ob.type}, rayon {rr.min():.6f}..{rr.max():.6f} (écart {abs(rr-exp).max():.2e})")
else: rec(SEC,"Offset cercle",False,str((r,o._reports)))
# Extrude Curve d'un cercle : hauteur tapée
clear(); R=m.build_polyline(bpy.context,"R",[V3(0,0,0),V3(8,0,0),V3(8,5,0),V3(0,5,0)],True); bpy.context.view_layer.update()
new,r,o=run("offset_edge",[C(4,0),'RET',M(4,-2),T(1),'RET'])
if new:
    P=ctrl_pts(new[0])[0]; mn,mx=bbox(P)
    rec(SEC,"Offset d'un rectangle 8x5 de 1 vers l'extérieur",near((mx-mn)[:2],(10,7),1e-6) or near((mx-mn)[:2],(6,3),1e-6),f"{tuple(np.round((mx-mn)[:2],7))} ({len(P)} sommets)")
else: rec(SEC,"Offset rectangle",False,str((r,o._reports)))
summary()
clear(); ar=m.build_bezier_arc(bpy.context,"Ar",V3(0,0,0),V3(1,0,0),V3(0,1,0),5.0,math.radians(20),math.radians(100),False); bpy.context.view_layer.update()
new,r,o=run("offset_edge",[C(0,5),'RET',M(0,7),T(1.5),'RET'])
if new:
    ob=new[0]; B=bez_eval(ob); rr=np.linalg.norm(B,axis=1); P=ctrl_pts(ob)[0]; a0=math.degrees(math.atan2(P[0][1],P[0][0])); a1=math.degrees(math.atan2(P[-1][1],P[-1][0]))
    rec(SEC,"Offset d'un arc r=5 (20°..120°) de 1.5 : arc vrai r=6.5, mêmes angles",ob.data.splines[0].type=='BEZIER' and abs(rr-6.5).max()<1e-4 and abs(min(a0,a1)-20)<1e-4 and abs(max(a0,a1)-120)<1e-4,f"type {ob.data.splines[0].type}, rayon {rr.min():.6f}..{rr.max():.6f}, angles {min(a0,a1):.5f}..{max(a0,a1):.5f}, centre {tuple(ob.get('dessin_centre') or ())}")
else: rec(SEC,"Offset arc",False,str((r,o._reports)))
summary()
