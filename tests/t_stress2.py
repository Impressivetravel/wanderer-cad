import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
import numpy as np, io, contextlib
# ---- 1. toutes les actions de la ligne de commande, scène vide puis avec sélection
def reset(empty=False, curve=False):
    for o in list(bpy.data.objects): bpy.data.objects.remove(o)
    for c in list(bpy.data.collections):
        if c.name not in ('Collection',):
            try: bpy.data.collections.remove(c)
            except Exception: pass
    if empty: bpy.context.view_layer.update(); return
    import bmesh
    me=bpy.data.meshes.new("Box"); bm=bmesh.new(); bmesh.ops.create_cube(bm,size=4); bm.to_mesh(me); bm.free()
    box=bpy.data.objects.new("Box",me); bpy.context.scene.collection.objects.link(box)
    cu=m.build_polyline(bpy.context,"Crv",[Vector((8,0,0)),Vector((12,0,0)),Vector((12,4,0)),Vector((8,4,0))],True)
    for o in bpy.context.view_layer.objects: o.select_set(False)
    tgt = cu if curve else box
    tgt.select_set(True); bpy.context.view_layer.objects.active=tgt
    bpy.context.view_layer.update()

bad=0; ran=0
for label,aliases,_x,desc,fn in m.CMD_ACTIONS:
    for scen,kw in (("vide",dict(empty=True)),("mesh",dict()),("courbe",dict(curve=True))):
        reset(**kw); ran+=1
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                msg=m.cmd_run(ctx,{"kind":"act","ref":fn,"label":label,"key":"act:"+label})
        except Exception:
            bad+=1
            tb=traceback.format_exc().strip().splitlines()
            print(f"EXC action {label:28s} [{scen}] "+" | ".join(tb[-2:]))
print("actions:",len(m.CMD_ACTIONS),"runs:",ran,"exceptions:",bad)

# ---- 2. panneaux : draw avec états variés
import inspect
class FakeLayout:
    def __getattr__(self,n):
        def f(*a,**k):
            return (FakeLayout(),FakeLayout()) if n=='panel' else FakeLayout()      # layout.panel() rend (en-tête, corps)
        return f
panels=[c for n,c in inspect.getmembers(m,inspect.isclass) if isinstance(c,type) and issubclass(c,bpy.types.Panel) and n.startswith('DESSIN_PT')]
pb=0
for scen,kw in (("vide",dict(empty=True)),("mesh",dict()),("courbe",dict(curve=True))):
    reset(**kw)
    for p in panels:
        from types import SimpleNamespace as NS
        o=NS(layout=FakeLayout(),bl_label=p.bl_label)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                if 'poll' in vars(p):
                    p.poll.__func__(p,ctx)
                vars(p)['draw'](o,ctx) if 'draw' in vars(p) else None
        except Exception:
            pb+=1
            tb=traceback.format_exc().strip().splitlines()
            print(f"EXC panel {p.__name__:24s} [{scen}] "+" | ".join(tb[-2:]))
print("panels:",len(panels),"exceptions:",pb)

# ---- 3. valeurs tapées extrêmes sur quelques outils numériques
def typed_run(cls,vals,pts):
    o=make(cls)
    r=type(o).invoke(o,ctx,ev('NONE','NOTHING',*scr(*pts[0])))
    if 'RUNNING_MODAL' not in r: return r
    for i,(x,y) in enumerate(pts):
        sx,sy=scr(x,y)
        if i<len(vals) and vals[i] is not None:
            o.typed=[str(vals[i]),'','']; o.field=0
        for e in (ev('MOUSEMOVE','NOTHING',sx,sy),ev('LEFTMOUSE','PRESS',sx,sy),ev('LEFTMOUSE','RELEASE',sx,sy)):
            r=type(o).modal(o,ctx,e)
            if 'FINISHED' in r or 'CANCELLED' in r: return r
    return r
tb3=0
CASES=[('DESSIN_OT_cercle',[None,'0'],[(0,0),(1,0)]),('DESSIN_OT_cercle',[None,'-5'],[(0,0),(1,0)]),
       ('DESSIN_OT_cercle',[None,'1e9'],[(0,0),(1,0)]),('DESSIN_OT_rectangle',[None,'0'],[(0,0),(2,2)]),
       ('DESSIN_OT_polyligne',[None,'abc'],[(0,0),(3,0),(3,3)]),('DESSIN_OT_boite',[None,None,'-2'],[(0,0),(4,4),(4,4)])]
for name,vals,pts in CASES:
    reset()
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            r=typed_run(getattr(m,name),vals,pts)
    except Exception:
        tb3+=1
        tb=traceback.format_exc().strip().splitlines()
        print(f"EXC typed {name} {vals} "+" | ".join(tb[-2:]))
print("typed cases:",len(CASES),"exceptions:",tb3)
print("TOTAL exceptions:",bad+pb+tb3)
