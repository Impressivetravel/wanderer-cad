import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
import bpy,sys,importlib.util,math
from types import SimpleNamespace as NS
from mathutils import Matrix, Vector
exec(open(_os.path.join(_HERE,'addon_loader.py')).read())
bpy.ops.wm.read_factory_settings(use_empty=True); m.register()
C=bpy.context; st=C.scene.dessin
print("default osnap_quad:", st.osnap_quad, m.OSNAP_DEFAULTS["quad"])
# cercle Wanderer
CI=m.build_bezier_arc(C,"W",Vector((0,0,0)),Vector((1,0,0)),Vector((0,1,0)),3.0,0.0,m.TAU,True)
# cercle Blender natif (Bézier) sans dessin_centre, et NURBS
bpy.ops.curve.primitive_bezier_circle_add(radius=3,location=(20,0,0))
bpy.ops.curve.primitive_nurbs_circle_add(radius=3,location=(40,0,0))
C.view_layer.update()
region=NS(width=1000,height=1000)
rv3d=NS(perspective_matrix=Matrix(((1/50,0,0,0),(0,1/50,0,0),(0,0,0.01,0),(0,0,0,1))),is_perspective=False,view_perspective="ORTHO",view_matrix=Matrix.Translation((0,0,-50)),view_rotation=Matrix().to_quaternion(),is_orthographic_side_view=False)
for cx in (0,20,40):
    d=m.collect_snap_points(C)
    for q in ((cx+3,0),(cx,3),(cx-3,0),(cx,-3),(cx,0)):
        r=m.find_snap_in(d,10*q[0]+500+3,10*q[1]+500+2,region,rv3d)
        print(cx,q, None if r is None else (tuple(round(c,2) for c in r[0]), m.SNAP_NAMES[r[2]]))
