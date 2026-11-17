# Valeurs tapées dans l'unité affichée de la scène (mm, cm, pouces) : Fillet Curve, Chamfer Curve, Divide
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
src=open(_os.path.join(_HERE,'t_pushpull.py')).read()
exec(src[src.index("\n")+1:src.index("# ---------------- 1. PushPull")])
us=C.scene.unit_settings
def units(length_unit, scale=1.0, system='METRIC'):
    us.system=system; us.length_unit=length_unit; us.scale_length=scale; C.view_layer.update()
def corner(L=1.0):
    clear(); p=m.build_polyline(C,"P",[Vector((0,0,0)),Vector((L,0,0)),Vector((L,L,0))],False)
    for q in bpy.data.objects: q.select_set(q is p)
    C.view_layer.objects.active=p; C.view_layer.update(); return p
def pts(o): return [o.matrix_world@Vector(p.co[:3]) for sp in o.data.splines for p in sp.points]
def arc_radius(o, L):
    """Rayon du congé posé au coin (L, 0) : distance des points de l'arc à son centre (L - r, r)."""
    P=pts(o); t0=P[1]            # premier point de tangence, sur le segment horizontal
    r=L-t0.x
    c=Vector((L-r,r,0)); mid=[q for q in P[1:-1]]
    return r, max(abs((q-c).length-r) for q in mid)
K.update({'6':'SIX','7':'SEVEN','8':'EIGHT','9':'NINE'})
def typed_status(o):
    """Texte de l'en-tête de la vue écrit par la commande."""
    got=[]
    old=area.header_text_set
    area.header_text_set=lambda *a: got.append(a[0] if a else None)
    try: o.status(ctx)
    finally: area.header_text_set=old
    return got[-1] if got else ""
for name,(lu,sc,sysname),bu,label in (("millimètres",('MILLIMETERS',1.0,'METRIC'),0.001,"mm"),("centimètres",('CENTIMETERS',1.0,'METRIC'),0.01,"cm"),
                                 ("mètres",('METERS',1.0,'METRIC'),1.0,"m"),("mm avec échelle 0,001",('MILLIMETERS',0.001,'METRIC'),1.0,"mm"),
                                 ("pouces",('INCHES',1.0,'IMPERIAL'),0.0254,"in")):
    units(lu,sc,sysname); L=100*bu
    p=corner(L); o,r=start(m.DESSIN_OT_fillet_curve); E(o,('t','6')); txt=typed_status(o); E(o,'RET'); C.view_layer.update()
    rad,dev=arc_radius(p,L)
    chk(f"Fillet Curve, scène en {name} : « 6 » tapé = 6 {label} (rayon mesuré)", abs(rad-6*bu)<1e-6*max(1,bu) and dev<1e-6*max(1.0,bu*100), (rad,6*bu,dev))
    chk(f"... l'en-tête affiche « radius 6 {label} »", f"radius 6 {label}" in txt, txt)
    p=corner(L); o,r=start(m.DESSIN_OT_chamfer_curve); E(o,('t','8'),'RET'); C.view_layer.update(); P=pts(p)
    chk(f"Chamfer Curve, scène en {name} : « 8 » tapé = 8 {label}", len(P)==4 and abs((L-P[1].x)-8*bu)<1e-6*max(1,bu) and abs(P[2].y-8*bu)<1e-6*max(1,bu), P)
# Divide par longueur
units('MILLIMETERS'); clear(); p=m.build_polyline(C,"P",[Vector((0,0,0)),Vector((0.1,0,0))],False)
for q in bpy.data.objects: q.select_set(q is p)
C.view_layer.objects.active=p; C.view_layer.update()
o,r=start(m.DESSIN_OT_divide); E(o,'TAB',('t','25')); txt=typed_status(o); E(o,'RET'); C.view_layer.update()
P=sorted(set(round((q.matrix_world@v.co).x,9) for q in bpy.data.objects if q is not p and q.type=='MESH'
             for v in q.data.vertices if abs((q.matrix_world@v.co).y)>1e-7 or abs((q.matrix_world@v.co).z)>1e-7))
chk("Divide par longueur, scène en mm : « 25 » = un point tous les 25 mm", len(P)>=3 and all(abs((b-a)-0.025)<1e-7 for a,b in zip(P,P[1:])), (P,txt))
chk("... l'en-tête affiche la longueur en mm", "length 25 mm" in txt, txt)
units('METERS')
print("RESULTAT",sum(res),"/",len(res))
