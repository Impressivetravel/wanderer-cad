import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
m.DessinTransform=mirror(m.DessinTransform)
import numpy as np
def reset_scene():
    for o in list(bpy.data.objects): bpy.data.objects.remove(o)
    me=bpy.data.meshes.new("Box"); 
    import bmesh; bm=bmesh.new(); bmesh.ops.create_cube(bm,size=4); bm.to_mesh(me); bm.free()
    box=bpy.data.objects.new("Box",me); bpy.context.scene.collection.objects.link(box); box.location=(-8,-8,2)
    r=m.build_polyline(bpy.context,"Rect",[Vector(p) for p in [(8,-10,0),(16,-10,0),(16,-4,0),(8,-4,0)]],True)
    for o in bpy.context.view_layer.objects: o.select_set(False)
    box.select_set(True); bpy.context.view_layer.objects.active=box
    bpy.context.view_layer.update()
    return box
pts=[(0,0),(10,6),(4,12),(-6,9),(-3,-5),(2,2)]
skip={'DESSIN_OT_gumball_relocate'}
tools=sorted([c for c in vars(m).values() if isinstance(c,type) and issubclass(c,m.DessinBase) and hasattr(c,'bl_idname') and c.__name__.startswith('DESSIN_OT') and c.__name__ not in skip],key=lambda c:c.__name__)
out=[]
for cls in tools:
    reset_scene()
    n0=len(bpy.data.objects)
    o=make(cls); status="?"; err=None
    try:
        sx,sy=scr(*pts[0])
        r=type(o).invoke(o,ctx,ev('NONE','NOTHING',sx,sy))
        status=str(sorted(r))
        if 'RUNNING_MODAL' in r:
            for i,(x,y) in enumerate(pts):
                sx,sy=scr(x,y)
                for e in (ev('MOUSEMOVE','NOTHING',sx,sy),ev('LEFTMOUSE','PRESS',sx,sy),ev('LEFTMOUSE','RELEASE',sx,sy)):
                    r=type(o).modal(o,ctx,e)
                    if 'RUNNING_MODAL' not in r and 'PASS_THROUGH' not in r or 'FINISHED' in r or 'CANCELLED' in r: break
                if 'FINISHED' in r or 'CANCELLED' in r: break
            else:
                r=type(o).modal(o,ctx,ev('RET','PRESS',sx,sy))
            status=str(sorted(r))
    except Exception as e:
        err=traceback.format_exc().strip().splitlines()
    n1=len(bpy.data.objects)
    new=[ob for ob in bpy.data.objects if ob.name not in ('Box','Rect')][:3]
    dims=" ".join(f"{ob.type[:4]}:{tuple(round(x,2) for x in ob.dimensions)}" for ob in new)
    try: type(o).cleanup(o,ctx)
    except Exception: pass
    line=f"{cls.__name__:32s} {status:28s} objets +{n1-n0}  {o._reports[-1] if o._reports else ''} {dims}"
    if err: line+="\n     EXC: "+" | ".join(err[-3:])
    print(line)
