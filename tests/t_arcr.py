import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
import numpy as np
for o in list(bpy.data.objects): bpy.data.objects.remove(o)
C=bpy.context
A=m.build_bezier_arc(C,"Arc",Vector((0,0,0)),Vector((1,0,0)),Vector((0,1,0)),5.0,0.0,math.pi/2,False)
C.view_layer.update()
d=m.collect_snap_points(C)
for info in d.circles:
    P=np.asarray(info[5]); r=np.linalg.norm(P-np.asarray(info[0]),axis=1)
    print(info[1], r.min(), r.max(), len(P), m.DESSIN_OT_cotation_arc.arc_of(info))
print("circles", len(d.circles), A.get("dessin_centre"), A.name)
o=bpy.data.objects["Arc"]; print(o.get("dessin_centre"), [ (sp.type, len(sp.bezier_points)) for sp in o.data.splines])
samples=m.bezier_world_samples([(tuple(p.co),tuple(p.handle_left),tuple(p.handle_right)) for p in o.data.splines[0].bezier_points], False)
print(len(samples))
