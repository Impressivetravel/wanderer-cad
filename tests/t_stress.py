import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
m.DessinTransform=mirror(m.DessinTransform)
import numpy as np, io, contextlib

def reset_scene(sel_box=True, empty=False):
    for o in list(bpy.data.objects): bpy.data.objects.remove(o)
    if empty:
        bpy.context.view_layer.update(); return None
    me=bpy.data.meshes.new("Box")
    import bmesh; bm=bmesh.new(); bmesh.ops.create_cube(bm,size=4); bm.to_mesh(me); bm.free()
    box=bpy.data.objects.new("Box",me); bpy.context.scene.collection.objects.link(box); box.location=(-8,-8,2)
    m.build_polyline(bpy.context,"Rect",[Vector(p) for p in [(8,-10,0),(16,-10,0),(16,-4,0),(8,-4,0)]],True)
    for o in bpy.context.view_layer.objects: o.select_set(False)
    if sel_box:
        box.select_set(True); bpy.context.view_layer.objects.active=box
    else:
        bpy.context.view_layer.objects.active=None
    bpy.context.view_layer.update()
    return box

skip={'DESSIN_OT_gumball_relocate'}
tools=sorted([c for c in vars(m).values() if isinstance(c,type) and issubclass(c,m.DessinBase) and hasattr(c,'bl_idname') and c.__name__.startswith('DESSIN_OT') and c.__name__ not in skip],key=lambda c:c.__name__)

def drive(o,cls,events):
    r=type(o).invoke(o,ctx,ev('NONE','NOTHING',*scr(0,0)))
    if 'RUNNING_MODAL' not in r: return r
    for e in events:
        r=type(o).modal(o,ctx,e)
        if 'FINISHED' in r or 'CANCELLED' in r: return r
    return r

def clicks(pts):
    out=[]
    for x,y in pts:
        sx,sy=scr(x,y)
        out+= [ev('MOUSEMOVE','NOTHING',sx,sy),ev('LEFTMOUSE','PRESS',sx,sy),ev('LEFTMOUSE','RELEASE',sx,sy)]
    return out

bad=0
SCEN=[
 ("no_sel",      lambda: reset_scene(sel_box=False), lambda: clicks([(0,0),(5,5),(9,2)])+[ev('RET','PRESS',*scr(9,2))]),
 ("empty_scene", lambda: reset_scene(empty=True),    lambda: clicks([(0,0),(5,5)])+[ev('RET','PRESS',*scr(5,5))]),
 ("dup_clicks",  lambda: reset_scene(),              lambda: clicks([(3,3)]*5)+[ev('RET','PRESS',*scr(3,3))]),
 ("enter_first", lambda: reset_scene(),              lambda: [ev('RET','PRESS',*scr(0,0))]*3),
 ("esc_mid",     lambda: reset_scene(),              lambda: clicks([(0,0),(6,4)])+[ev('ESC','PRESS',*scr(6,4))]),
 ("keys_spam",   lambda: reset_scene(),              lambda: clicks([(0,0)])+[ev(k,'PRESS',*scr(0,0)) for k in ('D','C','B','T','P','M','F','U','V','Q','TAB','BACK_SPACE')]+clicks([(7,5)])+[ev('RET','PRESS',*scr(7,5))]),
]
for cls in tools:
    for name,setup,evs in SCEN:
        setup()
        o=make(cls)
        try:
            buf=io.StringIO()
            with contextlib.redirect_stdout(buf):
                r=drive(o,cls,evs())
        except Exception:
            bad+=1
            tb=traceback.format_exc().strip().splitlines()
            print(f"EXC  {cls.__name__:30s} {name:12s} "+" | ".join(tb[-2:]))
        finally:
            try: type(o).cleanup(o,ctx)
            except Exception as e:
                bad+=1; print(f"EXCc {cls.__name__:30s} {name:12s} cleanup: {e}")
        # double invocation : zombie + nouvel outil
        if name=="esc_mid":
            try:
                o2=make(cls)
                with contextlib.redirect_stdout(io.StringIO()):
                    rr=type(o2).invoke(o2,ctx,ev('NONE','NOTHING',*scr(1,1)))
                    if 'RUNNING_MODAL' in rr:
                        for e in clicks([(1,1),(8,8)]):
                            rr=type(o2).modal(o2,ctx,e)
                            if 'FINISHED' in rr or 'CANCELLED' in rr: break
                type(o2).cleanup(o2,ctx)
            except Exception:
                bad+=1
                tb=traceback.format_exc().strip().splitlines()
                print(f"EXC2 {cls.__name__:30s} reinvoke     "+" | ".join(tb[-2:]))
print("outils:",len(tools),"| exceptions:",bad)
