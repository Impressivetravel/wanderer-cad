import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
import bpy,sys,importlib.util,math
from types import SimpleNamespace as NS
from mathutils import Matrix, Vector
exec(open(_os.path.join(_HERE,'addon_loader.py')).read())
bpy.ops.wm.read_factory_settings(use_empty=True); m.register()
C=bpy.context; st=C.scene.dessin
# Exercice : équerre de fixation vue de dessus (unités = mm fictifs)
L1=m.build_polyline(C,"Contour",[Vector(p) for p in [(0,0,0),(40,0,0),(40,10,0),(10,10,0),(10,30,0),(0,30,0)]],True)
L2=m.build_polyline(C,"Axe",[Vector((-5,20,0)),Vector((20,20,0))],False)       # croise le contour en (0,20) et (10,20)
CI=m.build_bezier_arc(C,"Trou",Vector((25,5,0)),Vector((1,0,0)),Vector((0,1,0)),3.0,0.0,m.TAU,True)
me=bpy.data.meshes.new("Bloc"); me.from_pydata([(30,20,0),(38,20,0),(38,28,0),(30,28,0)],[],[(0,1,2,3)])
BL=bpy.data.objects.new("Bloc",me); C.scene.collection.objects.link(BL)
C.view_layer.update()
region=NS(width=1000,height=1000)
rv3d=NS(perspective_matrix=Matrix(((1/50,0,0,0),(0,1/50,0,0),(0,0,0.01,0),(0,0,0,1))),is_perspective=False,view_perspective="ORTHO",view_matrix=Matrix.Translation((0,0,-50)),view_rotation=Matrix().to_quaternion(),is_orthographic_side_view=False)
def scr(x,y): return 10*x+500, 10*y+500
res=[]
def snap_at(x,y,ref=None,dx=0.6,dy=0.4):
    d=m.collect_snap_points(C)
    sx,sy=scr(x+dx,y+dy)
    r=m.find_snap_in(d,sx,sy,region,rv3d,ref=ref)
    return None if r is None else (tuple(round(c,3) for c in r[0]), m.SNAP_NAMES[r[2]])
def chk(name,got,exp_pt,exp_kind=None):
    ok = got is not None and exp_pt is not None and all(abs(a-b)<1e-3 for a,b in zip(got[0],exp_pt)) and (exp_kind is None or got[1]==exp_kind)
    if exp_pt is None: ok = got is None or (exp_kind is not None and got[1]!=exp_kind)
    res.append(ok); print(("OK  " if ok else "BAD ")+name, got)
for k in m.OSNAP_DEFAULTS: setattr(st,"osnap_"+k,m.OSNAP_DEFAULTS[k])
chk("End coin (40,10)", snap_at(40,10), (40,10,0),"End")
chk("Mid côté bas (20,0)", snap_at(20,0), (20,0,0),"Midpoint")
chk("Cen trou", snap_at(25,5,dx=0.5,dy=0.3), (25,5,0),"Center")
chk("Int axe/contour (0,20)", snap_at(0,20,dx=0.5,dy=0.5), (0,20,0),"Intersection")
chk("Vertex bloc maillage (38,28)", snap_at(38,28), (38,28,0))
chk("Near sur le bas", snap_at(33,0,dx=0,dy=0.5), (33,0,0),"Near")
st.osnap_quad=True
chk("Quad trou (28,5)", snap_at(28,5,dx=0.4,dy=0.2), (28,5,0),"Quadrant")
st.osnap_perp=True
chk("Perp depuis (15,-8) vers le bas", snap_at(15.5,0,ref=Vector((15,-8,0)),dx=0,dy=0.6), (15,0,0),"Perpendicular")
st.osnap_tan=True; st.osnap_near=False; st.osnap_end=False; st.osnap_mid=False
st.osnap_quad=False
a=math.radians(-90-math.degrees(math.acos(0.2)))
tp=(25+3*math.cos(a),5+3*math.sin(a),0)
chk("Tan depuis (25,-10)", snap_at(tp[0],tp[1],ref=Vector((25,-10,0)),dx=0.3,dy=0.3), tp,"Tangent")
st.osnap_quad=True
st.osnap_end=True; st.osnap_mid=True; st.osnap_near=True; st.osnap_tan=False; st.osnap_perp=False
st.osnap_end=False
chk("End désactivé -> pas End", snap_at(40,10), None,"End")
chk("Quad trou toujours (28,5) sans End", snap_at(28,5,dx=0.4,dy=0.2), (28,5,0),"Quadrant")
st.osnap_end=True
st.osnap_disable=True
chk("Disable -> rien", snap_at(40,10), None)
st.osnap_disable=False
# objet déplacé : le cache doit suivre
L2.location.y=2; C.view_layer.update()
chk("après déplacement : extrémité axe (20,22)", snap_at(20,22), (20,22,0),"End")
L2.location.y=0; C.view_layer.update()
# courbe éditée (point déplacé) : le cache doit suivre
L2.data.splines[0].points[1].co=(25,20,0,1); L2.data.update_tag(); C.view_layer.update()
chk("après édition de la courbe : extrémité (25,20)", snap_at(25,20), (25,20,0),"End")
# objet verrouillé (hide_select) : reste accrochable (comme Rhino)
L1.hide_select=True
chk("contour verrouillé : End (40,0) accrochable", snap_at(40,0), (40,0,0),"End")
L1.hide_select=False
# objet caché : pas accrochable
BL.hide_set(True); C.view_layer.update()
chk("bloc caché : pas de (38,28)", snap_at(38,28), None,"Vertex")
BL.hide_set(False); C.view_layer.update()
print("RESULTAT", sum(res),"/",len(res))
