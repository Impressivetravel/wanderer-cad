import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'t_alltools.py')).read().split("pts=[(0,0)")[0])
import sys
def run(cls,pts,select=None,keys=()):
    box=reset_scene()
    if select:
        for o in bpy.context.view_layer.objects: o.select_set(o.name in select)
        bpy.context.view_layer.objects.active=bpy.data.objects[select[0]]
    n0=len(bpy.data.objects); o=make(cls)
    sx,sy=scr(*pts[0]); r=type(o).invoke(o,ctx,ev('NONE','NOTHING',sx,sy)); print(" invoke",r, o._reports[-1:] )
    for (x,y) in pts:
        sx,sy=scr(x,y)
        for e in (ev('MOUSEMOVE','NOTHING',sx,sy),ev('LEFTMOUSE','PRESS',sx,sy),ev('LEFTMOUSE','RELEASE',sx,sy)):
            r=type(o).modal(o,ctx,e)
        print("  clic",(x,y),r,len(o.points) if hasattr(o,'points') else '', getattr(o,'info',''), o._reports[-1:] )
        if 'FINISHED' in r or 'CANCELLED' in r: break
    for k in keys:
        r=type(o).modal(o,ctx,ev(k,'PRESS',sx,sy)); print("  touche",k,r)
    print(cls.__name__,"objets +",len(bpy.data.objects)-n0)
    return o
