import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
exec(open(_os.path.join(_HERE,'prec_lib.py')).read())
V3=lambda *a: Vector(a)
def A(P): return np.array([tuple(p) for p in P],dtype=float)
def seg_dist(Q,P,closed=True):
    """distance de chaque point de Q à la polyligne P"""
    P=A(P); Q=A(Q); a=P; b=np.roll(P,-1,axis=0) if closed else P[1:]; a=P if closed else P[:-1]
    out=[]
    for q in Q:
        ab=b-a; t=np.clip(((q-a)*ab).sum(1)/np.maximum((ab*ab).sum(1),1e-30),0,1); c=a+ab*t[:,None]; out.append(np.linalg.norm(c-q,axis=1).min())
    return np.array(out)
SEC="Fonctions"
# ---- décalage (Offset)
R=[V3(0,0,0),V3(8,0,0),V3(8,5,0),V3(0,5,0)]
for d in (0.75,-0.75):
    Q=m.offset_polyline(R,True,V3(0,0,1),d)
    Q=A(Q[0] if isinstance(Q,tuple) else Q); dd=seg_dist(Q,R); mn,mx=bbox(Q)
    ins = (mx-mn)[0] < 8
    exp=(8-2*abs(d),5-2*abs(d)) if ins else (8+2*abs(d),5+2*abs(d))
    rec(SEC,f"Offset rectangle 8x5 de {d:+g} : rectangle {exp[0]:g} x {exp[1]:g}",near((mx-mn)[:2],exp,1e-9) and len(Q)==4,f"dims {tuple(np.round((mx-mn)[:2],10))} ; distance au contour {dd.min():.9f}..{dd.max():.9f} (coins en onglet : {abs(d)*math.sqrt(2):.6f})")
th=np.linspace(0,2*math.pi,192,endpoint=False); CIR=[V3(5*math.cos(t),5*math.sin(t),0) for t in th]
for d in (1.0,-1.0):
    Q=m.offset_polyline(CIR,True,V3(0,0,1),d); Q=A(Q[0] if isinstance(Q,tuple) else Q); rr=np.linalg.norm(Q,axis=1)
    exp=5-d if rr.mean()<5 else 5+abs(d)
    rec(SEC,f"Offset d'un cercle r=5 (192 côtés) de {d:+g} : rayon {exp:g}",abs(rr-exp).max()<2e-3,f"rayon {rr.min():.6f}..{rr.max():.6f} (écart max {abs(rr-exp).max():.2e})")
L=[V3(0,0,0),V3(10,0,0),V3(10,4,0),V3(4,4,0),V3(4,10,0),V3(0,10,0)]
Q=m.offset_polyline(L,True,V3(0,0,1),1.0); Q=A(Q[0] if isinstance(Q,tuple) else Q); dd=seg_dist(Q,L)
rec(SEC,"Offset d'un L (angle rentrant) de 1 : tous les sommets à ≥ 1 du contour, côtés parallèles à 1",dd.min()>1-1e-9,f"distance min {dd.min():.9f} max {dd.max():.6f}, {len(Q)} sommets")
# ---- congé / chanfrein de courbe
P=[V3(0,0,0),V3(10,0,0),V3(10,8,0)]
out,nc=m.round_path(P,False,2.0,False); O=A(out); cen=np.array((8,2,0)); arc=O[1:-1]
rd=np.linalg.norm(arc-cen,axis=1)
t_in=abs((arc[0]-np.array((8,0,0)))).max(); t_out=abs((arc[-1]-np.array((10,2,0)))).max()
rec(SEC,"Fillet Curve r=2 sur un angle droit : points sur le cercle de centre (8,2)",abs(rd-2).max()<2e-6 and nc==1,f"écart radial {abs(rd-2).max():.2e}, {len(arc)} points")
rec(SEC,"Fillet Curve : tangent aux deux côtés (points de tangence (8,0) et (10,2))",t_in<1e-9 and t_out<1e-9,f"écarts {t_in:.1e} / {t_out:.1e}")
out,nc=m.round_path(P,False,2.0,True); O=A(out)
rec(SEC,"Chamfer Curve distance 2 : coupe de (8,0) à (10,2)",len(O)==4 and near(O[1],(8,0,0),1e-9) and near(O[2],(10,2,0),1e-9),f"{[tuple(np.round(p,9)) for p in O[1:3]]}")
P2=[V3(0,0,0),V3(10,0,0),V3(13,6,0)]     # angle quelconque
out,nc=m.round_path(P2,False,1.5,False); O=A(out); arc=O[1:-1]
# centre attendu : sur la bissectrice, à r de chaque côté
d1=np.array((1,0,0)); d2=(np.array((13.,6,0))-np.array((10.,0,0))); d2=d2/np.linalg.norm(d2)
def dist_line(p,a,d): w=p-a; return np.linalg.norm(w-d*(w@d))
from itertools import product
# centre par ajustement : tous les points de l'arc à r du centre
Aeq=np.c_[2*arc[:,:2],np.ones(len(arc))]; sol=np.linalg.lstsq(Aeq,(arc[:,:2]**2).sum(1),rcond=None)[0]; c=np.array((sol[0],sol[1],0)); rfit=math.sqrt(sol[2]+sol[0]**2+sol[1]**2)
rec(SEC,"Fillet Curve r=1.5 sur un angle quelconque : rayon et tangence",abs(rfit-1.5)<2e-6 and abs(dist_line(c,np.array((0,0,0.)),d1)-1.5)<2e-6 and abs(dist_line(c,np.array((10,0,0.)),d2)-1.5)<2e-6,f"rayon ajusté {rfit:.9f}, distance du centre aux deux côtés {dist_line(c,np.array((0,0,0.)),d1):.9f} / {dist_line(c,np.array((10,0,0.)),d2):.9f}")
# ---- intersections (Trim)
s=m.trim_params(np.array((0.,0,0)),np.array((10.,0,0)),np.array([(3.,-2,0),(7.3,5,0)]),np.array([(3.,2,0),(7.3,-5,0)]),1e-6)
rec(SEC,"Trim : paramètres d'intersection d'un segment avec deux coupants (x=3 et x=7.3)",len(s)==2 and near(sorted(s),[0.3,0.73],1e-12),f"{sorted(float(x) for x in s)}")
# ---- aire
rec(SEC,"Aire d'un contour 8x5 incliné dans l'espace (Newell)",abs(m.loop_area([V3(0,0,0),V3(8,0,0),V3(8,3,4),V3(0,3,4)])-40)<1e-9,f"{m.loop_area([V3(0,0,0),V3(8,0,0),V3(8,3,4),V3(0,3,4)]):.10f}")
# ---- révolution
V,F=m.revolve_surface([(A([(5,0,0),(5,0,4)]),False)],V3(0,0,0),V3(0,0,1),360.0,cap=True)
V=A(V); rr=np.linalg.norm(V[:,:2],axis=1); n=len(V)//2 if len(V)%2==0 else None
rec(SEC,"Revolve d'un segment à r=5 sur 360° : sommets au rayon exact",abs(rr[rr>1e-6]-5).max()<1e-9,f"{len(V)} sommets, écart {abs(rr[rr>1e-6]-5).max():.1e}")
V,F=m.revolve_surface([(A([(5,0,0),(5,0,4)]),False)],V3(0,0,0),V3(0,0,1),90.0,cap=False); V=A(V); ang=np.degrees(np.arctan2(V[:,1],V[:,0]))
rec(SEC,"Revolve 90° : balayage angulaire exact",abs(ang.max()-ang.min()-90)<1e-9,f"de {ang.min():.9f}° à {ang.max():.9f}°")
# ---- extrusion avec dépouille / vers un point / deux côtés
sq=[(A([(0,0,0),(10,0,0),(10,10,0),(0,10,0)]),True)]
res=m.extrude_general(sq,V3(0,0,5),cap=True,both=False,taper=math.radians(10))
V=A(res[0]); top=V[np.isclose(V[:,2],5)]; mn,mx=bbox(top); exp=10-2*5*math.tan(math.radians(10))
rec(SEC,"ExtrudeCrv Tapered 10° sur 5 de haut : le haut rétrécit de h·tan(10°) par côté",near((mx-mn)[:2],(exp,exp),1e-9),f"haut {tuple(np.round((mx-mn)[:2],9))} attendu {exp:.9f}")
res=m.extrude_general(sq,V3(0,0,5),cap=True,both=True); V=A(res[0])
rec(SEC,"ExtrudeCrv BothSides 5 : de -5 à +5",near((V[:,2].min(),V[:,2].max()),(-5,5),1e-12),f"z {V[:,2].min()}..{V[:,2].max()}")
res=m.extrude_general(sq,V3(0,0,5),cap=True,apex=V3(5,5,7)); V=A(res[0])
rec(SEC,"ExtrudeCrv ToPoint : sommet exactement au point donné",np.linalg.norm(V-np.array((5,5,7)),axis=1).min()<1e-12,f"écart {np.linalg.norm(V-np.array((5,5,7)),axis=1).min():.1e}")
# ---- surfaces planes : aire avec trou
out=m.planar_surfaces([(A([(0,0,0),(10,0,0),(10,10,0),(0,10,0)]),True),(A([(3,3,0),(6,3,0),(6,7,0),(3,7,0)]),True)])
surf=out[0]; ar=0.0
for Vs,Fs in surf:
    Vs=A(Vs)
    for f in Fs:
        for i in range(1,len(f)-1): ar+=np.linalg.norm(np.cross(Vs[f[i]]-Vs[f[0]],Vs[f[i+1]]-Vs[f[0]]))/2
rec(SEC,"PlanarSrf carré 10x10 avec trou 3x4 : aire 88",abs(ar-88)<1e-9,f"{ar:.10f}")
# ---- hachures : espacement et découpe
rings=[np.array([(0,0),(10,0),(10,10),(0,10)],dtype=float),np.array([(3,3),(6,3),(6,7),(3,7)],dtype=float)]
pat=next(iter(m.HATCH_PATTERNS)) if isinstance(m.HATCH_PATTERNS,dict) else m.HATCH_PATTERNS[0][0]
names=list(m.HATCH_PATTERNS) if isinstance(m.HATCH_PATTERNS,dict) else [p[0] for p in m.HATCH_PATTERNS]
pn=next((n for n in names if 'atch1' in str(n) or 'HATCH1' in str(n)),names[1] if len(names)>1 else names[0])
try:
    segs=np.asarray(m.hatch_segments_2d(rings,pn,1.0,0.0,(0.0,0.0)))
    mid=(segs[:,0]+segs[:,1])/2
    inside=(mid[:,0]>-1e-9)&(mid[:,0]<10+1e-9)&(mid[:,1]>-1e-9)&(mid[:,1]<10+1e-9)
    inhole=(mid[:,0]>3+1e-9)&(mid[:,0]<6-1e-9)&(mid[:,1]>3+1e-9)&(mid[:,1]<7-1e-9)
    d=segs[:,1]-segs[:,0]; ang=np.round(np.degrees(np.arctan2(d[:,1],d[:,0]))%180,6)
    # espacement : distance perpendiculaire entre lignes voisines d'une même famille
    fam=ang==np.bincount((ang*1000).astype(int)).argmax()/1000
    a0=math.radians(float(ang[fam][0])); nrm=np.array((-math.sin(a0),math.cos(a0))); off=np.unique(np.round(segs[fam][:,0]@nrm,7)); sp=np.diff(off)
    L=np.linalg.norm(d,axis=1).sum()
    rec(SEC,f"Hatch ({pn}) dans un carré troué : tous les traits dans la région, aucun dans le trou",inside.all() and not inhole.any(),f"{len(segs)} traits")
    rec(SEC,"Hatch : espacement constant entre les lignes",sp.max()-sp.min()<1e-6,f"pas {sp.min():.7f}..{sp.max():.7f}, angle {float(ang[fam][0])}°, longueur totale {L:.4f} (aire/pas = {88/sp.mean():.4f})")
except Exception as e:
    rec(SEC,"Hatch segments",False,repr(e)[:200])
# ---- reconstruire / simplifier
th=np.linspace(0,math.pi,400); W=np.c_[th*3,np.sin(th)*2,np.zeros(400)]
cp,dev=m.fit_nurbs(W,12,3,False)
rec(SEC,"Rebuild (12 points, degré 3) d'une sinusoïde : extrémités conservées, écart annoncé",near(cp[0],W[0],1e-9) and near(cp[-1],W[-1],1e-9) and dev<0.02,f"écart max annoncé {dev:.2e}")
Sm=m.simplify_polyline([Vector(p) for p in W],0.01); Sm=A(Sm); dd=seg_dist(W,Sm,closed=False)
rec(SEC,"Simplify tolérance 0.01 : aucun point d'origine à plus de 0.01 du résultat",dd.max()<=0.01+1e-9,f"{len(W)} -> {len(Sm)} points, écart max {dd.max():.5f}")
summary()
