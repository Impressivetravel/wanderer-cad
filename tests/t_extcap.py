import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
import math
for o in list(bpy.data.objects): bpy.data.objects.remove(o)
C=bpy.context
r=m.build_polyline(C,"R",[Vector(p) for p in [(1,2,0),(0,2,0),(0,-2,0),(1,-2,0)]],False)   # open C-shape
a=m.build_bezier_arc(C,"A",Vector((1,0,0)),Vector((1,0,0)),Vector((0,1,0)),2.0,-math.pi/2,math.pi,False)
C.view_layer.update()
for o in C.view_layer.objects: o.select_set(True)
cls=m.DESSIN_OT_extrude_crv
o=make(cls); cls=type(o)
o.items=[(r,None),(a,None)]
spec=("extrude",Vector((0,0,0)),Vector((0,0,3)),True,False)
try:
    cls.build(o,ctx,spec)
except Exception as e: import traceback; traceback.print_exc()
for ob in bpy.data.objects:
    if ob.type=='MESH':
        ec={}
        for p in ob.data.polygons:
            for k in p.edge_keys: ec[k]=ec.get(k,0)+1
        print(ob.name, len(ob.data.polygons), "naked", sum(1 for v in ec.values() if v==1))
