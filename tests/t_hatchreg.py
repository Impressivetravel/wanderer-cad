import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
import traceback, json
for o in list(bpy.data.objects): bpy.data.objects.remove(o)
C=bpy.context
RO=m.build_polyline(C,"Outer",[Vector(p) for p in [(0,0,0),(10,0,0),(10,8,0),(0,8,0)]],True)
HO=m.build_polyline(C,"Hole",[Vector(p) for p in [(3,3,0),(6,3,0),(6,6,0),(3,6,0)]],True)
C.view_layer.update(); C.scene.dessin.hatch_boundary=True
cls=m.DESSIN_OT_hatch_region
o=make(cls); cls=type(o)
try:
    print(cls.invoke(o,ctx,ev('NONE','NOTHING',*scr(1,1))))
    sx,sy=scr(1,1)
    print(cls.modal(o,ctx,ev('MOUSEMOVE','NOTHING',sx,sy)), o.info, len(o.hilite), len(o.hatch_lines or []))
    print(cls.modal(o,ctx,ev('D','PRESS',sx,sy)), o.MODES[o.mode], C.scene.dessin.hatch_pattern)
    for e in (ev('LEFTMOUSE','PRESS',sx,sy),ev('LEFTMOUSE','RELEASE',sx,sy)): print(cls.modal(o,ctx,e))
    sx,sy=scr(4,4)
    for e in (ev('MOUSEMOVE','NOTHING',sx,sy),ev('LEFTMOUSE','PRESS',sx,sy),ev('LEFTMOUSE','RELEASE',sx,sy)): print(cls.modal(o,ctx,e))
    print(cls.modal(o,ctx,ev('ESC','PRESS',sx,sy)))
except Exception: traceback.print_exc()
for ob in bpy.data.objects: print(ob.name, ob.type, m.is_hatch(ob) and ob.dessin_hatch.pattern, m.is_hatch(ob) and len(json.loads(ob['dessin_hatch'])['rings']))
