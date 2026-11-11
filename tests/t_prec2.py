import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
exec(open(_os.path.join(_HERE,'prec_lib.py')).read())
SEC="3D"
def info(ob):
    V=mverts(ob); mn,mx=bbox(V); v,a,nk,nm=vol_area(ob); return V,mn,mx,v,a,nk,nm
clear(); new,r,o=run("point",[C(3.2,-1.5),'ESC'])
ob=new[0] if new else None
rec("2D","Point (3.2,-1.5)",ob is not None and near(ob.matrix_world.translation if ob.type=='EMPTY' else (mverts(ob)[0] if ob.type=='MESH' else ctrl_pts(ob)[0][0]),(3.2,-1.5,0),1e-6),ob and (ob.type,tuple(ob.matrix_world.translation)))
# ---- boîte
clear(); new,r,o=run("boite",[C(0,0),C(6,4),M(6,7),T(None)] if False else [C(0,0),C(6,4),C(6,7)])
ob=new[0]; V,mn,mx,v,a,nk,nm=info(ob)
rec(SEC,"Box 6 x 4 x h par clics : base exacte, solide fermé",near(mn[:2],(0,0),1e-6) and near(mx[:2],(6,4),1e-6) and nk==0 and nm==0,f"dims {tuple(np.round(mx-mn,6))} volume {v:.6f} bords ouverts {nk}")
clear(); new,r,o=run("boite",[C(0,0),M(3,3),T(10,20,30),'RET'])
if new:
    ob=new[0]; V,mn,mx,v,a,nk,nm=info(ob)
    rec(SEC,"Box tapée 10 x 20 x 30 : dimensions et volume 6000",near(mx-mn,(10,20,30),1e-5) and abs(v-6000)<1e-3 and nk==0,f"dims {tuple(np.round(mx-mn,6))} volume {v:.6f}")
else: rec(SEC,"Box tapée 10 x 20 x 30",False,str((r,o._reports,o.typed,len(o.points))))
# ---- cylindre, cône, sphère, tore : rayon / hauteur / volume par rapport au solide exact
clear(); new,r,o=run("cylindre",[C(0,0),M(5,0),T(5),'RET',M(5,8),T(12),'RET'])
if new:
    ob=new[0]; V,mn,mx,v,a,nk,nm=info(ob); rr=np.linalg.norm(V[:,:2],axis=1); n=int(round(len(V)/2))
    rec(SEC,"Cylinder r=5 h=12 : sommets sur le rayon, hauteur exacte, fermé",near(rr[rr>1e-6],5,1e-5) and abs((mx-mn)[2]-12)<1e-6 and nk==0,f"{n} côtés, hauteur {(mx-mn)[2]:.6f}")
    ex=math.pi*25*12; rec(SEC,"Cylinder : volume du maillage par rapport au cylindre exact",abs(v/ex-1)<5e-3,f"{v:.4f} vs {ex:.4f} ({(v/ex-1)*100:+.4f} %)")
else: rec(SEC,"Cylinder",False,str((r,o._reports)))
clear(); new,r,o=run("sphere",[C(0,0),M(4,0),T(4),'RET'])
if new:
    ob=new[0]; V,mn,mx,v,a,nk,nm=info(ob); rr=np.linalg.norm(V-V.mean(0),axis=1)
    ex=4/3*math.pi*64; rec(SEC,"Sphere r=4 : sommets sur la sphère ; volume par rapport à la sphère exacte",near(rr,4,1e-5) and nk==0,f"{len(V)} sommets, rayon {rr.min():.6f}..{rr.max():.6f}, volume {v:.4f} vs {ex:.4f} ({(v/ex-1)*100:+.3f} %)")
else: rec(SEC,"Sphere",False,str((r,o._reports)))
clear(); new,r,o=run("cone",[C(0,0),M(3,0),T(3),'RET',M(3,5),T(9),'RET'])
if new:
    ob=new[0]; V,mn,mx,v,a,nk,nm=info(ob); ex=math.pi*9*9/3
    rec(SEC,"Cone r=3 h=9 : hauteur, fermé, volume",abs((mx-mn)[2]-9)<1e-6 and nk==0 and abs(v/ex-1)<5e-3,f"hauteur {(mx-mn)[2]:.6f} volume {v:.4f} vs {ex:.4f} ({(v/ex-1)*100:+.4f} %)")
else: rec(SEC,"Cone",False,str((r,o._reports)))
clear(); new,r,o=run("tore",[C(0,0),M(6,0),T(6),'RET',M(8,0),T(2),'RET'])
if new:
    ob=new[0]; V,mn,mx,v,a,nk,nm=info(ob); ex=2*math.pi**2*6*4
    rec(SEC,"Torus R=6 r=2 : encombrement et volume",near(mx-mn,(16,16,4),2e-2) and nk==0,f"dims {tuple(np.round(mx-mn,4))} volume {v:.3f} vs {ex:.3f} ({(v/ex-1)*100:+.3f} %)")
else: rec(SEC,"Torus",False,str((r,o._reports)))
# ---- extrusion de courbe
def rect(name,x0,y0,x1,y1): return m.build_polyline(bpy.context,name,[Vector(p) for p in [(x0,y0,0),(x1,y0,0),(x1,y1,0),(x0,y1,0)]],True)
clear(); R=rect("R",0,0,8,5); bpy.context.view_layer.update()
new,r,o=run("extrude_crv",[C(0,0),M(0,3),T(7.5),'RET'],sel=[R])
if new:
    ob=new[0]; V,mn,mx,v,a,nk,nm=info(ob)
    rec(SEC,"Extrude Curve rectangle 8x5 hauteur 7.5 : dimensions, volume 300",near(mx-mn,(8,5,7.5),1e-6) and (nk>0 or abs(v-300)<1e-4),f"dims {tuple(np.round(mx-mn,6))} volume {v:.5f} bords ouverts {nk} (Cap {'on' if nk==0 else 'off'})")
else: rec(SEC,"Extrude Curve",False,str((r,o._reports,getattr(o,'typed',None))))
clear(); c=m.build_bezier_arc(bpy.context,"Circ",Vector((0,0,0)),Vector((1,0,0)),Vector((0,1,0)),5.0,0.0,m.TAU,True); bpy.context.view_layer.update()
new,r,o=run("extrude_crv",[C(0,0),M(0,3),T(10),'RET'],sel=[c])
if new:
    ob=new[0]; V,mn,mx,v,a,nk,nm=info(ob); rr=np.linalg.norm(V[:,:2],axis=1); ex=math.pi*25*10
    rec(SEC,"Extrude Curve cercle r=5 h=10 : sommets par rapport au rayon vrai",abs(rr[rr>1e-6]-5).max()<5e-3,f"{len(V)//2} côtés, rayon {rr[rr>1e-6].min():.6f}..{rr.max():.6f} (écart {abs(rr[rr>1e-6]-5).max():.2e})"+(f", volume {v:.3f} vs {ex:.3f} ({(v/ex-1)*100:+.4f} %)" if nk==0 else ", ouvert"))
# ---- booléens : volumes analytiques
def box(n,loc,s=4):
    me=bpy.data.meshes.new(n); bm=bmesh.new(); bmesh.ops.create_cube(bm,size=s); bm.to_mesh(me); bm.free()
    ob=bpy.data.objects.new(n,me); bpy.context.scene.collection.objects.link(ob); ob.location=loc; return ob
for kind,exp in (('UNION',116.0),('DIFFERENCE',52.0),('INTERSECT',12.0)):
    clear(); a=box("A",(0,0,2)); b=box("B",(2,2,3)); bpy.context.view_layer.update()
    try:
        created,err=m.run_boolean(kind,[a,b] if kind=='UNION' else [a],[] if kind=='UNION' else [b],True)
        v=sum(vol_area(ob)[0] for ob in created); nk=sum(vol_area(ob)[2] for ob in created)
        rec(SEC,f"Boolean {kind.title()} de deux cubes : volume analytique {exp:g}",abs(v-exp)<1e-4 and nk==0,f"{v:.6f} (écart {v-exp:+.1e}), bords ouverts {nk}, {err or ''}")
    except Exception as e: rec(SEC,f"Boolean {kind}",False,repr(e)[:150])
summary()
