# Extrude Curve : une courbe plane s'extrude perpendiculairement à son plan (ExtrudeCrv de Rhino), sinon axe du plan de construction
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
src=open(_os.path.join(_HERE,'t_pushpull.py')).read()
exec(src[src.index("\n")+1:src.index("# ---------------- 1. PushPull")])
from mathutils import Euler
def ext(pts, evs, closed=True, rot=None, view_front=False):
    clear(); m._OPT_MEM.clear()          # options mémorisées (comme Rhino) : chaque cas part des réglages par défaut
    c=m.build_polyline(C,"Prof",[Vector(p) for p in pts],closed)
    if rot is not None: c.rotation_euler=rot
    C.view_layer.update()
    for q in bpy.data.objects: q.select_set(False)
    c.select_set(True); C.view_layer.objects.active=c
    if view_front: rv3d.is_orthographic_side_view=True; rv3d.view_rotation=Euler((math.pi/2,0,0)).to_quaternion()
    try:
        o,r=start(m.DESSIN_OT_extrude_crv); r=E(o,*evs)
    finally:
        rv3d.is_orthographic_side_view=False; rv3d.view_rotation=Matrix().to_quaternion()
    ex=[q for q in bpy.data.objects if q.name!="Prof"]
    if not ex: return r,None,None
    bb=[ex[0].matrix_world@Vector(b) for b in ex[0].bound_box]
    mn=tuple(round(min(v[i] for v in bb),5) for i in range(3)); mx=tuple(round(max(v[i] for v in bb),5) for i in range(3))
    return r,(mn,mx),ex[0]
rect_xy=[(0,0,0),(2,0,0),(2,1,0),(0,1,0)]
rect_xz=[(0,0,0),(2,0,0),(2,0,1),(0,0,1)]
r,bb,_=ext(rect_xy,[('c',0,0),('t','3'),'RET'])
chk("courbe à plat (dessus) : vers le haut comme avant", bb==((0,0,0),(2,1,3)), bb)
r,bb,ob=ext(rect_xz,[('c',0,0),('t','3'),'RET'])
chk("courbe debout (plan XZ) en vue Dessus/Perspective : perpendiculaire (Y)", bb==((0,0,0),(2,3,1)), bb)
s=stats(ob) if ob else {}
chk("... solide fermé, volume 2 x 1 x 3", ob is not None and abs(s["vol"]-6)<1e-5 and s["naked"]==0, s)
r,bb,_=ext(rect_xy,[('c',0,0),('t','3'),'RET'],rot=(math.pi/2,0,0))
chk("cas de l'utilisateur : dessinée à plat puis tournée de 90° -> de côté", bb is not None and abs(bb[1][2]-1)<1e-5 and abs(abs(bb[0][1]-bb[1][1])-3)<1e-5, bb)
r,bb,ob=ext(rect_xy,[('c',0,0),('t','3'),'RET'],rot=(0.4,0.7,0.2))
if ob:
    M=Euler((0.4,0.7,0.2)).to_matrix(); n=M@Vector((0,0,1))
    P=[ob.matrix_world@v.co for v in ob.data.vertices]
    d=sorted({round((p).dot(n),5) for p in P})
    chk("plan quelconque : extrusion le long de sa normale (hauteur 3 exacte)", d in ([0.0,3.0],[-3.0,0.0]) and abs(stats(ob)["vol"]-6)<1e-5, d)
r,bb,_=ext([(0,0,0),(2,0,0.5),(2,1,0),(0,1,0.7)],[('c',0,0),('t','2'),'RET'])
chk("courbe non plane : axe du plan de construction (Z)", bb is not None and abs(bb[1][2]-(0.7+2))<1e-5, bb)
r,bb,_=ext([(0,0,0),(2,0,1)],[('c',0,0),('t','2'),'RET'],closed=False)
chk("droite : axe du plan de construction (Z)", bb is not None and abs(bb[1][2]-3)<1e-5 and bb[0][1]==0 and bb[1][1]==0, bb)
r,bb,_=ext(rect_xy,[('c',0,0),('t','3'),'RET'],view_front=True)
chk("courbe à plat lancée en vue de Face : perpendiculaire (Z), plus d'extrusion à plat", bb==((0,0,0),(2,1,3)), bb)
r,bb,_=ext(rect_xz,[('c',0,0),('m',0,-2),('c',0,-2)])
chk("souris de l'autre côté : extrusion vers -Y", bb is not None and bb[1][1]==0 and bb[0][1]<-1.9, bb)
r,bb,_=ext(rect_xz,[('c',0,0),'B',('t','1'),'RET'])
chk("B (deux côtés) sur courbe debout", bb==((0,-1,0),(2,1,1)), bb)
r,bb,ob=ext(rect_xz,[('c',0,0),'T',('t','2'),'RET'])
s=stats(ob) if ob else {}
chk("T (dépouille) sur courbe debout : solide fermé vers Y", ob is not None and s["naked"]==0 and bb[1][1]>1.9 and bb[0][1]>-1e-6, (bb,s))
r,bb,ob=ext(rect_xz,[('c',1,0),'P',('t','2'),'RET'])
s=stats(ob) if ob else {}
chk("P (vers un point) sur courbe debout : pyramide fermée, sommet à 2 en Y", ob is not None and s["naked"]==0 and abs(bb[1][1]-2)<1e-5, (bb,s))
def run_u():
    c=bpy.data.objects["Prof"]
    for q in bpy.data.objects: q.select_set(False)
    c.select_set(True); C.view_layer.objects.active=c
    o,r=start(m.DESSIN_OT_extrude_crv); E(o,('c',0,0),('t','3'),'RET')
clear(); m.build_polyline(C,"Prof",[Vector(p) for p in rect_xz],True); C.view_layer.update()
undo_redo("Extrude Curve courbe debout", run_u)
print("RESULTAT",sum(res),"/",len(res))
