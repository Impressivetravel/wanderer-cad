import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
exec(open(_os.path.join(_HERE,'prec_lib.py')).read())
V3=lambda *a: Vector(a)
st=bpy.context.scene.dessin
def texts(): return sorted(o.data.body for o in bpy.data.objects if o.type=='FONT')
# ================= Accrochages : valeurs exactes
SEC="Accrochage"
for k in ("end","near","point","mid","cen","int","perp","tan","quad","knot","vertex"): setattr(st,"osnap_"+k,True)
st.osnap_disable=False
def snap_at(x,y,ref=None,only=None):
    for k in ("end","near","point","mid","cen","int","perp","tan","quad","knot","vertex"): setattr(st,"osnap_"+k,(only is None) or (k in only))
    d=m.collect_snap_points(ctx); m._screen_index(d,np.array(rv3d.perspective_matrix,dtype=np.float64),region,allow_async=False)
    r=m.find_snap_in(d,*scr(x,y),region,rv3d,ref=Vector(ref) if ref is not None else None)
    return (np.array(r[0]),m.SNAP_NAMES[r[2]]) if r else (None,None)
clear()
L1=m.build_polyline(bpy.context,"L1",[V3(0,0,0),V3(10,3,0)],False); L2=m.build_polyline(bpy.context,"L2",[V3(0,4,0),V3(9,-2,0)],False)
ci=m.build_bezier_arc(bpy.context,"Ci",V3(20,0,0),V3(1,0,0),V3(0,1,0),5.0,0.0,m.TAU,True); bpy.context.view_layer.update()
# intersection analytique de L1 et L2
a1=np.array((0.,0,0)); d1=np.array((10.,3,0)); a2=np.array((0.,4,0)); d2=np.array((9.,-6,0))
t=np.linalg.solve(np.c_[d1[:2],-d2[:2]],(a2-a1)[:2]); X=a1+d1*t[0]
p,k=snap_at(X[0]+0.05,X[1]+0.05,only=("int",))
rec(SEC,"Int : croisement de deux droites quelconques",p is not None and k=="Intersection" and np.linalg.norm(p-X)<1e-5,f"{k} écart {np.linalg.norm(p-X) if p is not None else None:.2e} (attendu {tuple(np.round(X,6))})")
p,k=snap_at(5.02,1.52,only=("mid",)); rec(SEC,"Mid : milieu de L1 = (5, 1.5)",p is not None and near(p,(5,1.5,0),1e-6),f"{k} {None if p is None else tuple(np.round(p,7))}")
p,k=snap_at(10.02,3.02,only=("end",)); rec(SEC,"End : extrémité (10, 3)",p is not None and near(p,(10,3,0),1e-6),f"{k}")
p,k=snap_at(20.05,0.05,only=("cen",)); rec(SEC,"Cen : centre du cercle (20, 0)",p is not None and near(p,(20,0,0),1e-6),f"{k}")
p,k=snap_at(25.03,0.04,only=("quad",)); rec(SEC,"Quad : quadrant (25, 0)",p is not None and near(p,(25,0,0),1e-6),f"{k} {None if p is None else tuple(np.round(p,7))}")
ang=math.radians(33.3); q=np.array((20+5*math.cos(ang),5*math.sin(ang),0))
p,k=snap_at(q[0]+0.06*math.cos(ang),q[1]+0.06*math.sin(ang),only=("near",))
dr=abs(np.linalg.norm(p-np.array((20,0,0)))-5) if p is not None else None
rec(SEC,"Near sur un cercle r=5 : point sur le cercle vrai",p is not None and k=="Near" and dr<5e-3,f"{k} écart au cercle vrai {dr:.2e} ({dr/5*100:.4f} % du rayon)" if p is not None else "aucun")
p,k=snap_at(3.0,0.9+0.05,only=("near",)); 
dl=abs(np.cross(d1/np.linalg.norm(d1),p-a1)[2]) if p is not None else None
rec(SEC,"Near sur une droite : point exactement sur la droite",p is not None and dl<1e-6,f"écart à la droite {dl:.2e}" if p is not None else "aucun")
ref=(2.0,6.0,0.0); foot=a1+d1*((np.array(ref)-a1)@d1)/(d1@d1)
p,k=snap_at(foot[0]+0.04,foot[1]-0.03,ref=ref,only=("perp",))
rec(SEC,"Perp : pied de la perpendiculaire depuis (2, 6) sur L1",p is not None and k=="Perpendicular" and np.linalg.norm(p-foot)<1e-5,f"{k} écart {np.linalg.norm(p-foot) if p is not None else None:.2e}")
ref=(30.0,0.0,0.0); tp=np.array((20+5*0.5,5*math.sqrt(0.75),0))     # tangente depuis (30,0) : cos = r/d = 0.5
p,k=snap_at(tp[0]+0.03,tp[1]+0.04,ref=ref,only=("tan",))
rec(SEC,"Tan : point de tangence depuis (30, 0) sur le cercle",p is not None and k=="Tangent" and np.linalg.norm(p-tp)<5e-3,f"{k} écart {np.linalg.norm(p-tp) if p is not None else None:.2e}")
for k_ in ("end","near","point","mid","cen","int","quad","vertex"): setattr(st,"osnap_"+k_,True)
st.osnap_perp=False; st.osnap_tan=False; st.osnap_knot=False
# ================= Cotes : la valeur écrite = la géométrie
SEC="Cotes"
clear(); st.unite_cote='SCENE'
new,r,o=run("cotation",[C(0,0),C(8,0),C(4,-3)]); rec(SEC,"Cote alignée (0,0)-(8,0) : texte = 8",texts() and abs(float(texts()[0].split()[0])-8)<1e-9,texts())
clear(); new,r,o=run("cotation",[C(1,1),C(4,5),C(0,5)]); rec(SEC,"Cote alignée (1,1)-(4,5) : texte = 5",texts() and abs(float(texts()[0].split()[0])-5)<1e-9,texts())
clear(); new,r,o=run("cotation_angle",[C(0,0),C(8,0),C(0,5),C(3,3)]); 
tx=texts(); val=float(tx[0].replace('°','').split()[0]) if tx else None
rec(SEC,"Cote d'angle entre l'axe X et l'axe Y : 90°",val is not None and abs(val-90)<1e-6,tx)
clear(); ci=m.build_bezier_arc(bpy.context,"Ci",V3(12,0,0),V3(1,0,0),V3(0,1,0),3.0,0.0,m.TAU,True); bpy.context.view_layer.update()
new,r,o=run("cotation_rayon",[C(15,0),C(18,3)]); tx=texts()
rec(SEC,"Cote de rayon d'un cercle r=3 : R3 exact (centre et rayon vrais, pas la polyligne)",tx and abs(float(tx[0].lstrip('RØ⌀ '))-3)<1e-9,tx)
clear(); ar=m.build_bezier_arc(bpy.context,"Ar",V3(0,0,0),V3(1,0,0),V3(0,1,0),5.0,0.0,math.pi/2,False); bpy.context.view_layer.update()
new,r,o=run("cotation_arc",[C(3.5,3.5),C(5,5)]); tx=texts()
rec(SEC,"Longueur d'arc r=5 sur 90° : 5·π/2 = 7.853982 (valeur exacte, pas celle de la polyligne)",tx and abs(float(tx[0].split()[0])-5*math.pi/2)<6e-3,f"{tx} exact {5*math.pi/2:.6f}")
# unités : scène en millimètres
us=bpy.context.scene.unit_settings; us.system='METRIC'; us.length_unit='MILLIMETERS'; us.scale_length=0.001
clear(); new,r,o=run("rectangle",[C(0,0),M(5,5),T(250,120),'RET'])
P=ctrl_pts(new[0])[0]; mn,mx=bbox(P)
rec("Unités","Scène en mm (échelle 0.001) : rectangle tapé 250 x 120 = 250 x 120 unités",near((mx-mn)[:2],(250,120),1e-5),f"{tuple(np.round((mx-mn)[:2],6))}")
us.scale_length=1.0; us.length_unit='CENTIMETERS'
clear(); new,r,o=run("rectangle",[C(0,0),M(5,5),T(250,120),'RET'])
P=ctrl_pts(new[0])[0]; mn,mx=bbox(P)
rec("Unités","Scène en cm (échelle 1) : rectangle tapé 250 x 120 cm = 2.5 x 1.2 unités",near((mx-mn)[:2],(2.5,1.2),1e-6),f"{tuple(np.round((mx-mn)[:2],7))}")
clear(); new,r,o=run("cotation",[C(0,0),C(8,0),C(4,-3)]); rec("Unités","Cote en unités de la scène (cm) : 8 unités = 800 cm",texts() and abs(float(texts()[0].split()[0])-800)<1e-6,texts())
us.length_unit='METERS'
# ================= Transformations
SEC="Transformations"
def rect(name="R"): 
    ob=m.build_polyline(bpy.context,name,[V3(0,0,0),V3(8,0,0),V3(8,5,0),V3(0,5,0)],True); bpy.context.view_layer.update(); return ob
def WP(name): return ctrl_pts(bpy.data.objects[name])[0]
clear(); R=rect(); new,r,o=run("deplacer",[C(0,0),C(3,2)],sel=[R])
rec(SEC,"Move de (0,0) à (3,2) : déplacement exact",near(WP("R"),[(3,2,0),(11,2,0),(11,7,0),(3,7,0)],1e-6),f"{sorted(r)}")
clear(); R=rect(); new,r,o=run("deplacer",[C(0,0),M(5,0),T(12.5),'RET'],sel=[R])
rec(SEC,"Move distance tapée 12.5 le long de X",near(WP("R")[0],(12.5,0,0),1e-6),f"{tuple(np.round(WP("R")[0],7))}")
clear(); R=rect(); new,r,o=run("copier",[C(0,0),C(0,10),'RET','ESC'],sel=[R])
cp=[ob for ob in bpy.data.objects if ob.name!="R"]
rec(SEC,"Copy de (0,0) à (0,10) : copie exacte, original intact",len(cp)==1 and near(ctrl_pts(cp[0])[0],[(0,10,0),(8,10,0),(8,15,0),(0,15,0)],1e-6) and near(WP("R")[0],(0,0,0),1e-9),f"{len(cp)} copie(s)")
clear(); R=rect(); new,r,o=run("rotation",[C(0,0),C(8,0),M(5,5),T(37),'RET'],sel=[R])
P=WP("R"); c_,s_=math.cos(math.radians(37)),math.sin(math.radians(37)); exp=[(0,0,0),(8*c_,8*s_,0),(8*c_-5*s_,8*s_+5*c_,0),(-5*s_,5*c_,0)]
rec(SEC,"Rotate 37° tapé autour de (0,0)",near(P,exp,2e-6),f"écart max {np.abs(P-np.array(exp)).max():.2e}")
clear(); R=rect(); new,r,o=run("rotation",[C(0,0),C(8,0),C(0,8)],sel=[R])
rec(SEC,"Rotate par clics : de l'axe X vers l'axe Y = 90°",near(WP("R"),[(0,0,0),(0,8,0),(-5,8,0),(-5,0,0)],2e-6),f"écart max {np.abs(WP('R')-np.array([(0,0,0),(0,8,0),(-5,8,0),(-5,0,0)])).max():.2e}")
clear(); R=rect(); new,r,o=run("echelle",[C(0,0),M(4,0),T(2.5),'RET'],sel=[R])
rec(SEC,"Scale : facteur 2.5 tapé juste après le point de base (comme Rhino)",near(WP("R"),[(0,0,0),(20,0,0),(20,12.5,0),(0,12.5,0)],1e-5),f"{tuple(np.round(WP('R')[2],6))}")
clear(); R=rect(); new,r,o=run("echelle",[C(0,0),C(8,0),M(10,0),T(2.5),'RET'],sel=[R])
rec(SEC,"Scale : après le point de référence (longueur 8), 2.5 tapé = nouvelle longueur (comme Rhino) -> facteur 0.3125",near(WP("R"),[(0,0,0),(2.5,0,0),(2.5,1.5625,0),(0,1.5625,0)],1e-6),f"{tuple(np.round(WP('R')[2],6))}")
clear(); R=rect(); new,r,o=run("echelle",[C(0,0),C(8,0),C(16,0)],sel=[R])
rec(SEC,"Scale par clics : 8 -> 16 = facteur 2",near(WP("R"),[(0,0,0),(16,0,0),(16,10,0),(0,10,0)],1e-6),"")
clear(); R=rect(); new,r,o=run("miroir",[C(-3,0),C(-3,5)],sel=[R])
mr=[ob for ob in bpy.data.objects if ob.name!="R"]
allp=np.vstack([ctrl_pts(ob)[0] for ob in mr]) if mr else WP("R")
exp=sorted([(-6.,0,0),(-14.,0,0),(-14.,5,0),(-6.,5,0)])
rec(SEC,"Mirror par rapport à x=-3 : image exacte (x -> -6-x), original gardé",len(mr)==1 and near(sorted(map(tuple,np.round(allp,6))),exp,1e-5) and near(WP("R")[1],(8,0,0),1e-9),f"{sorted(map(tuple,np.round(allp,5)))[:2]}")
summary()
