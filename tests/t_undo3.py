import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
exec(open(_os.path.join(_HERE,'undo_lib.py')).read())
import bmesh, inspect
def reset(kind):
    for o in list(bpy.data.objects): bpy.data.objects.remove(o)
    for c in list(bpy.data.collections):
        try: bpy.data.collections.remove(c)
        except Exception: pass
    me=bpy.data.meshes.new("Box"); bm=bmesh.new(); bmesh.ops.create_cube(bm,size=4); bm.to_mesh(me); bm.free()
    box=bpy.data.objects.new("Box",me); bpy.context.scene.collection.objects.link(box)
    b2=bpy.data.objects.new("Box2",me.copy()); bpy.context.scene.collection.objects.link(b2); b2.location=(3,1,0)
    cu=m.build_polyline(bpy.context,"Crv",[Vector((8,0,0)),Vector((12,0,0)),Vector((12,4,0)),Vector((8,4,0))],True)
    c2=m.build_polyline(bpy.context,"Crv2",[Vector((10,-2,0)),Vector((10,6,0))],False)
    for o in bpy.context.view_layer.objects: o.select_set(False)
    tg={'mesh':[box],'meshes':[box,b2],'curve':[cu],'curves':[cu,c2]}[kind]
    for t in tg: t.select_set(True)
    bpy.context.view_layer.objects.active=tg[0]; bpy.context.view_layer.update()
st=dict(runs=0,changed=0,undo_bad=0,redo_bad=0,exc=0)
for label,aliases,_x,desc,fn in m.CMD_ACTIONS:
    if label in ("Undo","Redo"): continue          # ces deux actions sont elles-mêmes une annulation : rien à comparer
    for kind in ('mesh','meshes','curve','curves'):
        reset(kind); bpy.ops.ed.undo_push(message="A"); A=snapshot(bpy); st['runs']+=1
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                m.cmd_run(ctx,{"kind":"act","ref":fn,"label":label,"key":"act:"+label})
        except Exception:
            st['exc']+=1; print(f"EXC {label} [{kind}] "+" | ".join(traceback.format_exc().strip().splitlines()[-2:])[:200]); continue
        if bpy.context.mode!='OBJECT':
            try: bpy.ops.object.mode_set(mode='OBJECT')
            except Exception: pass
        bpy.context.view_layer.update(); B=snapshot(bpy)
        if A==B: continue
        st['changed']+=1
        bpy.ops.ed.undo_push(message=label); bpy.ops.ed.undo(); bpy.context.view_layer.update(); A2=snapshot(bpy)
        if A2!=A: st['undo_bad']+=1; print(f"UNDO≠ {label} [{kind}] {diff(A,A2)}")
        bpy.ops.ed.redo(); bpy.context.view_layer.update(); B2=snapshot(bpy)
        if B2!=B: st['redo_bad']+=1; print(f"REDO≠ {label} [{kind}] {diff(B,B2)}")
print("RESULTAT undo/redo actions:",st)
# ---- opérateurs sans UNDO dans bl_options
no=[]
for n,c in inspect.getmembers(m,inspect.isclass):
    if n.startswith('DESSIN_OT') and issubclass(c,bpy.types.Operator) and hasattr(c,'bl_idname'):
        if 'UNDO' not in getattr(c,'bl_options',set()): no.append(n+":"+getattr(c,'bl_label',''))
print("opérateurs sans UNDO:",len(no)); print("; ".join(no))
