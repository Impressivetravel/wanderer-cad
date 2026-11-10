import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
exec(open(_os.path.join(_HERE,'undo_lib.py')).read())
m.DessinTransform=mirror(m.DessinTransform)
import bmesh, sys
class FL:
    def __getattr__(self,n):
        if n=='panel': return lambda *a,**k:(FL(),FL())
        return lambda *a,**k: FL()
PANELS=[c for n,c in inspect.getmembers(m,inspect.isclass) if n.startswith('DESSIN_PT') and 'draw' in vars(c)]
def followups(tag):
    """Actions courantes après un undo / redo : toute exception = référence périmée ou état incohérent."""
    errs=[]
    def tryit(name,fn):
        try:
            with contextlib.redirect_stdout(io.StringIO()): fn()
        except Exception:
            errs.append(f"{tag}/{name}: "+" | ".join(traceback.format_exc().strip().splitlines()[-2:]))
    tryit("depsgraph",lambda: m._on_depsgraph_update())
    def snap():
        d=m.collect_snap_points(ctx); m._screen_index(d,np.array(rv3d.perspective_matrix,dtype=np.float64),region,allow_async=False)
        for p in ((0,0),(8,-10),(-6,-6),(12,-4)): m.find_snap_in(d,*scr(*p),region,rv3d)
    tryit("snap",snap)
    def poly():
        o=make(m.DESSIN_OT_polyligne); type(o).invoke(o,ctx,ev('NONE','NOTHING',*scr(1,1)))
        for p in ((1,1),(5,3)): type(o).modal(o,ctx,ev('MOUSEMOVE','NOTHING',*scr(*p)))
        type(o).modal(o,ctx,ev('ESC','PRESS',*scr(5,3)))
        try: type(o).cleanup(o,ctx)
        except Exception: pass
    tryit("polyline",poly)
    def panels():
        for p in PANELS:
            from types import SimpleNamespace as NS2
            vars(p)['draw'](NS2(layout=FL(),bl_label=getattr(p,'bl_label','')),ctx)
    tryit("panels",panels)
    tryit("pick",lambda: [m.pick_object_at(ctx,area,region,*scr(*p)) for p in ((-8,-8),(12,-7),(0,0))])
    tryit("layers",lambda: m.layer_sync_new_objects())
    return errs
def reset_scene(sel='box'):
    for o in list(bpy.data.objects): bpy.data.objects.remove(o)
    for c in list(bpy.data.collections):
        try: bpy.data.collections.remove(c)
        except Exception: pass
    for x in list(bpy.data.meshes): 
        if not x.users: bpy.data.meshes.remove(x)
    for x in list(bpy.data.curves):
        if not x.users: bpy.data.curves.remove(x)
    me=bpy.data.meshes.new("Box"); bm=bmesh.new(); bmesh.ops.create_cube(bm,size=4); bm.to_mesh(me); bm.free()
    box=bpy.data.objects.new("Box",me); bpy.context.scene.collection.objects.link(box); box.location=(-8,-8,2)
    r=m.build_polyline(bpy.context,"Rect",[Vector(p) for p in [(8,-10,0),(16,-10,0),(16,-4,0),(8,-4,0)]],True)
    l=m.build_polyline(bpy.context,"Line",[Vector(p) for p in [(6,-7,0),(18,-7,0)]],False)
    for o in bpy.context.view_layer.objects: o.select_set(False)
    tgt={'box':[box],'rect':[r],'both':[r,l],'none':[]}[sel]
    for t in tgt: t.select_set(True)
    bpy.context.view_layer.objects.active=tgt[0] if tgt else None
    bpy.context.view_layer.update()
pts=[(0,0),(10,6),(4,12),(-6,9),(-3,-5),(2,2)]
pts2=[(12,-7),(12,-2),(3,3),(9,9),(2,2)]      # clics qui touchent le rectangle / la ligne
skip={'DESSIN_OT_gumball_relocate'}
tools=sorted([c for c in vars(m).values() if isinstance(c,type) and issubclass(c,m.DessinBase) and hasattr(c,'bl_idname') and c.__name__.startswith('DESSIN_OT') and c.__name__ not in skip],key=lambda c:c.__name__)
only=sys.argv[2:] if len(sys.argv)>2 else None
if only: tools=[c for c in tools if c.__name__ in only]
def run_tool(cls,P):
    o=make(cls)
    r=type(o).invoke(o,ctx,ev('NONE','NOTHING',*scr(*P[0])))
    if 'RUNNING_MODAL' in r:
        for (x,y) in P:
            sx,sy=scr(x,y)
            for e in (ev('MOUSEMOVE','NOTHING',sx,sy),ev('LEFTMOUSE','PRESS',sx,sy),ev('LEFTMOUSE','RELEASE',sx,sy)):
                r=type(o).modal(o,ctx,e)
                if 'FINISHED' in r or 'CANCELLED' in r: break
            if 'FINISHED' in r or 'CANCELLED' in r: break
        else:
            r=type(o).modal(o,ctx,ev('RET','PRESS',sx,sy))
    try: type(o).cleanup(o,ctx)
    except Exception: pass
    return r
stats=dict(tested=0,noop=0,undo_bad=0,redo_bad=0,follow=0,exc=0,noundo=0)
STEPWISE={'DESSIN_OT_point'}
for cls in tools:
    for sel,P in (('box',pts),('rect',pts2),('both',pts2)):
        reset_scene(sel)
        bpy.ops.ed.undo_push(message="avant")
        A=snapshot(bpy)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                r=run_tool(cls,P)
        except Exception:
            stats['exc']+=1; print(f"EXC   {cls.__name__:30s} [{sel}] "+" | ".join(traceback.format_exc().strip().splitlines()[-2:])); continue
        bpy.context.view_layer.update()
        B=snapshot(bpy)
        if A==B:
            stats['noop']+=1; continue
        stats['tested']+=1
        opts=getattr(cls,'bl_options',set())
        if 'UNDO' not in opts:
            stats['noundo']+=1; print(f"NOUNDO {cls.__name__:30s} [{sel}] modifie la scène sans bl_options UNDO : {sorted(opts)}  {diff(A,B,2)}")
        bpy.ops.ed.undo_push(message=cls.__name__)
        bpy.ops.ed.undo(); bpy.context.view_layer.update()
        A2=snapshot(bpy)
        nun=1
        while A2!=A and cls.__name__ in STEPWISE and nun<30:
            # commande qui enregistre une étape par point posé (Point) : autant d'annulations que de points
            bpy.ops.ed.undo(); bpy.context.view_layer.update(); A2=snapshot(bpy); nun+=1
        if A2!=A:
            stats['undo_bad']+=1; print(f"UNDO≠ {cls.__name__:30s} [{sel}] {diff(A,A2)}")
        fe=followups("undo")
        for _ in range(nun):
            bpy.ops.ed.redo(); bpy.context.view_layer.update()
        B2=snapshot(bpy)
        if B2!=B:
            stats['redo_bad']+=1; print(f"REDO≠ {cls.__name__:30s} [{sel}] {diff(B,B2)}")
        fe+=followups("redo")
        if fe:
            stats['follow']+=1
            for l in fe[:3]: print(f"SUIVI {cls.__name__:30s} [{sel}] {l}")
print("RESULTAT undo/redo outils:",stats)
