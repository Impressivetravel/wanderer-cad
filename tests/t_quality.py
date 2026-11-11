import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
exec(open(_os.path.join(_HERE,'prec_lib.py')).read())
SEC="Qualité"
def setq(q): m.PREF_DEFAULTS["curve_quality"]=q; m._update_perf()
def wire(o):
    g=m.curve_wire_direct(o); return np.array([tuple(v) for v in g[0]]),g[1]
EXP={'DRAFT':48,'NORMAL':96,'FINE':192,'VERY_FINE':384}
# cercle r=5 construit par l'outil (8 morceaux)
clear()
run('cercle',[C(0,0),C(5,0)])
cir=[o for o in bpy.data.objects if o.type=='CURVE'][0]
nb=len(cir.data.splines[0].bezier_points)
rec(SEC,"cercle de l'outil : 8 points de contrôle",nb==8,nb)
for q,n in EXP.items():
    setq(q); P,E=wire(cir)
    r=np.linalg.norm(P[:,:2],axis=1)
    sag=5*(1-math.cos(math.pi/n))
    rec(SEC,f"{q} : cercle = {n} côtés",len(P)==n and len(E)==n,f"{len(P)} sommets, {len(E)} arêtes")
    rec(SEC,f"{q} : sommets sur le cercle vrai",abs(r-5).max()<5e-5,f"écart max {abs(r-5).max():.2e}")
    st=np.linalg.norm(np.roll(P,-1,axis=0)-P,axis=1)
    rec(SEC,f"{q} : côtés réguliers",st.max()/st.min()<1.03,f"rapport {st.max()/st.min():.5f}, flèche {sag/5*100:.4f} % du rayon")
# ancien cercle à 4 morceaux (fichiers d'avant) : même nombre de côtés
setq('NORMAL')
import bpy
old=bpy.data.curves.new("Old",'CURVE'); old.dimensions='3D'
sp=old.splines.new('BEZIER'); sp.bezier_points.add(3); k=4/3*math.tan(math.pi/8)
for i,bp in enumerate(sp.bezier_points):
    a=i*math.pi/2; c,s_=math.cos(a),math.sin(a)
    bp.co=(3*c,3*s_,0); bp.handle_left=(3*c+3*k*s_,3*s_-3*k*c,0); bp.handle_right=(3*c-3*k*s_,3*s_+3*k*c,0)
    bp.handle_left_type=bp.handle_right_type='FREE'
sp.use_cyclic_u=True
oo=bpy.data.objects.new("Old",old); bpy.context.scene.collection.objects.link(oo); oo["dessin_centre"]=(0.0,0.0,0.0)
bpy.context.view_layer.update()
for q,n in EXP.items():
    setq(q); P,E=wire(oo)
    rec(SEC,f"{q} : ancien cercle (4 morceaux) = {n} côtés",len(P)==n,len(P))
# arc de 90° : un quart des côtés
clear(); setq('NORMAL')
run('arc_cse',[C(0,0),C(4,0),C(0,4)])
arcs=[o for o in bpy.data.objects if o.type=='CURVE']
if arcs:
    for q,n in EXP.items():
        setq(q); P,E=wire(arcs[0])
        rec(SEC,f"{q} : arc de 90° = {n//4} côtés",len(E)==n//4,len(E))
else:
    rec(SEC,"arc créé",False)
# courbe libre (sans centre) : 24 côtés par morceau en qualité normale, proportionnel ensuite
clear()
cu=bpy.data.curves.new("Free",'CURVE'); cu.dimensions='3D'; sp=cu.splines.new('BEZIER'); sp.bezier_points.add(2)
for bp,(x,y) in zip(sp.bezier_points,((0,0),(4,3),(9,0))):
    bp.co=(x,y,0); bp.handle_left=(x-1,y-1,0); bp.handle_right=(x+1,y+1,0); bp.handle_left_type=bp.handle_right_type='FREE'
fo=bpy.data.objects.new("Free",cu); bpy.context.scene.collection.objects.link(fo); bpy.context.view_layer.update()
for q,n in (('DRAFT',12),('NORMAL',24),('FINE',48),('VERY_FINE',96)):
    setq(q); P,E=wire(fo)
    rec(SEC,f"{q} : courbe libre = {n} côtés par morceau",len(E)==2*n,len(E))
# polyligne : inchangée quelle que soit la qualité
pl=m.build_polyline(bpy.context,"PL",[Vector((0,0,0)),Vector((5,0,0)),Vector((5,5,0))],False)
bpy.context.view_layer.update()
cnt=set()
for q in EXP:
    setq(q); cnt.add(len(wire(pl)[1]))
rec(SEC,"polyligne : jamais subdivisée",cnt=={2},cnt)
# extrusion d'un cercle : le maillage suit la qualité, volume proche du cylindre vrai
for q,n in EXP.items():
    clear(); setq(q)
    run('cercle',[C(0,0),C(5,0)])
    c=[o for o in bpy.data.objects if o.type=='CURVE'][0]
    res=run('extrude_crv',[C(0,0),M(0,3),T(10),'RET'],sel=[c])
    ms=[o for o in bpy.data.objects if o.type=='MESH']
    if ms:
        me=ms[0].data; nv=len(me.vertices)
        vol,area,_nk,_nm=vol_area(ms[0])
        vt=math.pi*25*10
        rec(SEC,f"{q} : Extrude du cercle = {n} côtés",nv in (2*n,2*n+2),f"{nv} sommets, {len(me.polygons)} faces, volume {vol:.4f} (cylindre vrai {vt:.4f}, écart {abs(vol-vt)/vt*100:.3f} %)")
    else:
        rec(SEC,f"{q} : Extrude du cercle",False,"pas de maillage")
setq('NORMAL')
bad=[r for r in RES if not r[2]]
print("RESULTAT","TOUT OK" if not bad else "ECHECS %d"%len(bad),len(RES),"mesures")
