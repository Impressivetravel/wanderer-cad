import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
exec(open(_os.path.join(_HERE,'prec_lib.py')).read())
SEC="2D"
# ---- polyligne : clics exacts, longueur tapée
clear(); new,r,o=run("polyligne",[C(0,0),C(6,0),C(6,4),'RET'])
P=ctrl_pts(new[0])[0]; rec(SEC,"Polyline : sommets aux points cliqués",near(P,[(0,0,0),(6,0,0),(6,4,0)],1e-9),f"écart max {np.abs(P-np.array([(0,0,0),(6,0,0),(6,4,0)])).max():.2e}")
clear(); new,r,o=run("polyligne",[C(1,1),M(9,1),T(7),'RET','RET'])
P=ctrl_pts(new[0])[0] if new else None
rec(SEC,"Polyline : longueur tapée 7 dans la direction de la souris",new and near(P[-1],(8,1,0),1e-7),P is not None and tuple(np.round(P[-1],7)))
# ---- rectangle
clear(); new,r,o=run("rectangle",[C(0,0),C(8,5)])
P=ctrl_pts(new[0])[0]; mn,mx=bbox(P); rec(SEC,"Rectangle 8 x 5 par clics",near(mn,(0,0,0),1e-9) and near(mx,(8,5,0),1e-9) and len(P)==4,f"{tuple(mx-mn)}")
clear(); new,r,o=run("rectangle",[C(1,2),M(5,5),T(12.5,7.25),'RET'])
P=ctrl_pts(new[0])[0]; mn,mx=bbox(P); rec(SEC,"Rectangle tapé 12.5 x 7.25",near(mx-mn,(12.5,7.25,0),1e-7),f"{tuple(np.round(mx-mn,8))}")
# ---- cercle : rayon, exactitude de la courbe, quadrants
for rad in (3.0,1000.0):
    clear(); new,r,o=run("cercle",[C(2,3),M(5,3),T(rad),'RET'])
    ob=new[0]; cen=np.array((2,3,0)); B=bez_eval(ob); d=np.linalg.norm(B-cen,axis=1)
    rec(SEC,f"Cercle r={rad:g} : points de contrôle sur le rayon",near(np.linalg.norm(ctrl_pts(ob)[0]-cen,axis=1),rad,1e-6*rad),f"nb segments {len(ctrl_pts(ob)[0])}")
    rec(SEC,f"Cercle r={rad:g} : écart radial de la courbe vraie (Bézier)",(np.abs(d-rad).max()/rad)<1e-5,f"max {np.abs(d-rad).max():.3e} ({np.abs(d-rad).max()/rad*100:.5f} %)")
    Pp=np.vstack([p for p,c in paths(ob)]); dp=np.linalg.norm(Pp-cen,axis=1)
    L=np.linalg.norm(np.diff(np.vstack([Pp,Pp[:1]]),axis=0),axis=1)
    sag=rad-np.sqrt(np.maximum(rad**2-(L.max()/2)**2,0))
    rec(SEC,f"Cercle r={rad:g} : polyligne utilisée par les outils (extrusion, hachure, trim...)",sag/rad<2e-3,f"{len(Pp)} segments, flèche {sag:.3e} ({sag/rad*100:.4f} %), périmètre {L.sum():.6f} vs {2*math.pi*rad:.6f} ({(L.sum()/(2*math.pi*rad)-1)*100:.4f} %)")
clear(); new,r,o=run("cercle_diametre",[C(0,0),C(10,0)])
ob=new[0]; B=bez_eval(ob); d=np.linalg.norm(B-np.array((5,0,0)),axis=1)
rec(SEC,"Cercle par diamètre (0,0)-(10,0) : centre (5,0), r=5",abs(d-5).max()<1e-4,f"écart max {abs(d-5).max():.2e}, centre stocké {tuple(ob.get('dessin_centre'))}")
# ---- arcs
clear(); new,r,o=run("arc_cse",[C(0,0),C(5,0),C(0,5)])
ob=new[0]; B=bez_eval(ob); d=np.linalg.norm(B,axis=1); P=ctrl_pts(ob)[0]
rec(SEC,"Arc centre/début/fin : rayon 5, extrémités (5,0) et (0,5)",abs(d-5).max()<1e-4 and near(P[0],(5,0,0),1e-6) and near(P[-1],(0,5,0),1e-6),f"écart radial {abs(d-5).max():.2e}  extrémités {tuple(np.round(P[0],6))} {tuple(np.round(P[-1],6))}")
clear(); new,r,o=run("arc_3pts",[C(-4,0),C(4,0),C(0,4)])
ob=new[0]; B=bez_eval(ob); d=np.linalg.norm(B,axis=1)
rec(SEC,"Arc 3 points (-4,0) (4,0) (0,4) : cercle de centre origine r=4",abs(d-4).max()<1e-4,f"écart {abs(d-4).max():.2e}; passe par les 3 points: {min(np.linalg.norm(B-np.array(p),axis=1).min() for p in [(-4,0,0),(4,0,0),(0,4,0)]):.1e}")
# ---- ellipses
clear(); new,r,o=run("ellipse_centre",[C(0,0),C(6,0),C(0,3)])
ob=new[0]; B=bez_eval(ob); f=(B[:,0]/6)**2+(B[:,1]/3)**2
rec(SEC,"Ellipse centre a=6 b=3 : équation x²/a²+y²/b²=1",abs(f-1).max()<2e-3,f"écart max {abs(f-1).max():.2e}")
clear(); new,r,o=run("ellipse_coin",[C(0,0),C(10,4)])
ob=new[0]; B=bez_eval(ob); mn,mx=bbox(B); rec(SEC,"Ellipse par coins (0,0)-(10,4) : inscrite dans la boîte",near(mn,(0,0,0),2e-3) and near(mx,(10,4,0),2e-3),f"{tuple(np.round(mn,4))} {tuple(np.round(mx,4))}")
clear(); new,r,o=run("ellipse_foyers",[C(-3,0),C(3,0),C(0,4)])
ob=new[0]; B=bez_eval(ob); s_=np.linalg.norm(B-np.array((-3,0,0)),axis=1)+np.linalg.norm(B-np.array((3,0,0)),axis=1)
rec(SEC,"Ellipse par foyers (±3,0) passant par (0,4) : somme des distances = 10",abs(s_-10).max()<5e-3,f"écart max {abs(s_-10).max():.2e}")
# ---- polygones
for name,exp in (("poly_center","circumradius"),("poly_circ","inradius"),("poly_edge","edge")):
    clear(); new,r,o=run(name,[C(0,0),C(5,0)])
    P=ctrl_pts(new[0])[0]; n=len(P); L=np.linalg.norm(np.diff(np.vstack([P,P[:1]]),axis=0),axis=1)
    cen=P.mean(0); R=np.linalg.norm(P-cen,axis=1)
    if exp=="circumradius": okk=near(R,5,1e-6); ms=f"rayon sommets {R.min():.6f}..{R.max():.6f}"
    elif exp=="inradius": okk=abs(R.min()*math.cos(math.pi/n)-5)<1e-6; ms=f"apothème {R.min()*math.cos(math.pi/n):.6f}"
    else: okk=near(L,5,1e-6); ms=f"côtés {L.min():.6f}..{L.max():.6f}"
    rec(SEC,f"{getattr(m,'DESSIN_OT_'+name).bl_label} ({n} côtés)",okk and L.max()-L.min()<1e-6,ms+f" ; côtés égaux à {L.max()-L.min():.1e}")
# ---- ligne de construction, point
clear(); new,r,o=run("point",[C(3.2,-1.5),'ESC'])
rec(SEC,"Point (3.2,-1.5)",new and near(new[0].matrix_world.translation if new[0].type!="MESH" else mverts(new[0])[0],(3.2,-1.5,0),1e-6),"")
summary()
