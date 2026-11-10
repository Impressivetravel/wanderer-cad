import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
exec(open(_os.path.join(_HERE,'undo_lib.py')).read())
m.DessinTransform=mirror(m.DessinTransform)
import bmesh, sys
def reset_scene(sel='box'):
    for o in list(bpy.data.objects): bpy.data.objects.remove(o)
    me=bpy.data.meshes.new("Box"); bm=bmesh.new(); bmesh.ops.create_cube(bm,size=4); bm.to_mesh(me); bm.free()
    box=bpy.data.objects.new("Box",me); bpy.context.scene.collection.objects.link(box); box.location=(-8,-8,2)
    r=m.build_polyline(bpy.context,"Rect",[Vector(p) for p in [(8,-10,0),(16,-10,0),(16,-4,0),(8,-4,0)]],True)
    l=m.build_polyline(bpy.context,"Line",[Vector(p) for p in [(6,-7,0),(18,-7,0)]],False)
    for o in bpy.context.view_layer.objects: o.select_set(False)
    tgt={'box':[box],'rect':[r],'both':[r,l]}[sel]
    for t in tgt: t.select_set(True)
    bpy.context.view_layer.objects.active=tgt[0]
    bpy.context.view_layer.update()
skip={'DESSIN_OT_gumball_relocate'}
tools=sorted([c for c in vars(m).values() if isinstance(c,type) and issubclass(c,m.DessinBase) and hasattr(c,'bl_idname') and c.__name__.startswith('DESSIN_OT') and c.__name__ not in skip],key=lambda c:c.__name__)
start=int(sys.argv[2]) if len(sys.argv)>2 else 0
bad=0; n=0; guarded=0; leaks=0
SC=[('box',[(0,0),(10,6)],[(4,12),(-6,9),(2,2)]),('rect',[(12,-7),(12,-2)],[(3,3),(9,9)]),('both',[(12,-7)],[(12,-2),(3,3)]),('box',[],[(0,0),(10,6),(4,12)]),('rect',[],[(12,-7),(12,-2),(3,3)])]
for ti,cls in enumerate(tools):
    if ti<start: continue
    for kind in ('undo','redo','delete'):
        for sel,P1,P2 in SC:
            reset_scene(sel)
            bpy.ops.ed.undo_push(message="avant")
            # une modification à annuler pendant la commande : on déplace la boîte
            bpy.data.objects["Box"].location.x+=1.0; bpy.context.view_layer.update()
            bpy.ops.ed.undo_push(message="deplacement")
            print(f"@{ti} {cls.__name__} {kind} {sel}",flush=True)
            o=make(cls); phase="invoke"
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    r=type(o).invoke(o,ctx,ev('NONE','NOTHING',*scr(*(P1 or P2)[0])))
                    if 'RUNNING_MODAL' not in r: continue
                    done=False; sx,sy=scr(0,0)
                    for (x,y) in P1:
                        sx,sy=scr(x,y)
                        for e in (ev('MOUSEMOVE','NOTHING',sx,sy),ev('LEFTMOUSE','PRESS',sx,sy),ev('LEFTMOUSE','RELEASE',sx,sy)):
                            r=type(o).modal(o,ctx,e)
                            if 'FINISHED' in r or 'CANCELLED' in r: done=True; break
                        if done: break
                    if done: continue
                    n+=1
                    # ---- l'utilisateur fait Ctrl+Z (ou supprime un objet) pendant la commande
                    phase=kind
                    if kind=='undo': bpy.ops.ed.undo()
                    elif kind=='redo': bpy.ops.ed.undo(); bpy.ops.ed.redo()
                    else:
                        for nm in ("Rect","Box"):
                            ob=bpy.data.objects.get(nm)
                            if ob: bpy.data.objects.remove(ob)
                    bpy.context.view_layer.update()
                    phase="suite"
                    for (x,y) in P2:
                        sx,sy=scr(x,y)
                        for e in (ev('MOUSEMOVE','NOTHING',sx,sy),ev('LEFTMOUSE','PRESS',sx,sy),ev('LEFTMOUSE','RELEASE',sx,sy)):
                            r=type(o).modal(o,ctx,e)
                            if 'FINISHED' in r or 'CANCELLED' in r: done=True; break
                        if done: break
                    if not done:
                        phase="esc"; type(o).modal(o,ctx,ev('ESC','PRESS',sx,sy))
            except Exception:
                bad+=1
                tb=traceback.format_exc().strip().splitlines()
                loc=[l.strip() for l in tb if 'cad_toolkit' in l][-1:] 
                print(f"EXC {cls.__name__:28s} [{kind}/{sel}/{phase}] {tb[-1][:110]}  @ {loc[0][-60:] if loc else ''}")
            finally:
                if any('scene changed' in str(x[1]) for x in o._reports):
                    guarded+=1
                    if m._CMD["op"].get(area.as_pointer()) is o or getattr(o,'_h_view',None) is not None or getattr(o,'_h_pix',None) is not None:
                        leaks+=1; print(f"FUITE {cls.__name__} [{kind}/{sel}] gestionnaires non nettoyés après arrêt")
                try:
                    with contextlib.redirect_stdout(io.StringIO()): type(o).cleanup(o,ctx)
                except Exception as e:
                    bad+=1; print(f"EXC {cls.__name__:28s} [{kind}/{sel}/cleanup] {str(e)[:100]}")
print("RESULTAT undo en cours de commande : cas",n,"exceptions",bad,"| arrêts propres par le filet:",guarded,"fuites:",leaks)
