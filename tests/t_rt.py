import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
m.DessinTransform=mirror(m.DessinTransform)
import bmesh, io, contextlib, time, random, sys
import numpy as np
MODE=sys.argv[2] if len(sys.argv)>2 else 'light'
random.seed(4)
def cube(name,loc,size=1.0,sub=0):
    me=bpy.data.meshes.new(name); bm=bmesh.new(); bmesh.ops.create_cube(bm,size=size)
    if sub: bmesh.ops.subdivide_edges(bm,edges=bm.edges[:],cuts=sub,use_grid_fill=True)
    bm.to_mesh(me); bm.free()
    o=bpy.data.objects.new(name,me); bpy.context.scene.collection.objects.link(o); o.location=loc; return o
def grid(name,n,loc):
    me=bpy.data.meshes.new(name); bm=bmesh.new(); bmesh.ops.create_grid(bm,x_segments=n,y_segments=n,size=3); bm.to_mesh(me); bm.free()
    o=bpy.data.objects.new(name,me); bpy.context.scene.collection.objects.link(o); o.location=loc; return o
for o in list(bpy.data.objects): bpy.data.objects.remove(o)
if MODE=='heavy':
    for i in range(1500): cube("C%04d"%i,(random.uniform(-45,45),random.uniform(-45,45),0),0.6,sub=3)
    for i in range(600):       # un plan de CAO : beaucoup de courbes
        x,y=random.uniform(-45,45),random.uniform(-45,45)
        if i%3==0: m.build_bezier_arc(bpy.context,"K%03d"%i,Vector((x,y,0)),Vector((1,0,0)),Vector((0,1,0)),random.uniform(0.3,1.2),0.0,m.TAU,True)
        else: m.build_polyline(bpy.context,"P%03d"%i,[Vector((x,y,0)),Vector((x+random.uniform(0.5,3),y,0)),Vector((x+1,y+random.uniform(0.5,2),0))],i%2==0)
    bpy.context.view_layer.update()
KEEP={o.name for o in bpy.data.objects}
SELS={}
def small():
    for o in [o for o in bpy.data.objects if o.name not in KEEP]: bpy.data.objects.remove(o)
    box=cube("Box",(-8,-8,2),4.0)
    rect=m.build_polyline(bpy.context,"Rect",[Vector(p) for p in [(8,-10,0),(16,-10,0),(16,-4,0),(8,-4,0)]],True)
    line=m.build_polyline(bpy.context,"Line",[Vector(p) for p in [(6,-7,0),(18,-7,0)]],False)
    circ=m.build_bezier_arc(bpy.context,"Circ",Vector((-10,8,0)),Vector((1,0,0)),Vector((0,1,0)),3.0,0.0,m.TAU,True)
    dense=grid("Dense",150,(20,20,0)) if MODE=='heavy' else box
    bpy.context.view_layer.update()
    SELS.update({'box':[box],'rect':[rect],'both':[rect,line],'dense':[dense],'circ':[circ]})
small()
skip={'DESSIN_OT_gumball_relocate'}
tools=sorted([c for c in vars(m).values() if isinstance(c,type) and issubclass(c,m.DessinBase) and hasattr(c,'bl_idname') and c.__name__.startswith('DESSIN_OT') and c.__name__ not in skip],key=lambda c:c.__name__)
persp=np.array(rv3d.perspective_matrix,dtype=np.float64)
rows=[]
CL={'box':[(-8,-8),(3,4),(9,7),(-4,6)],'rect':[(12,-7),(12,-2),(3,3),(9,9)],'both':[(12,-7),(14,-3),(5,5),(1,8)],'dense':[(20,20),(26,23),(28,28),(15,25)],'circ':[(-7,8),(-5,10),(0,5),(3,3)]}
for cls in tools:
    worst=(0,None); allm=[]; inv=0
    for sel in (('box','rect','both','dense','circ') if MODE=='heavy' else ('box','rect','both','circ')):
        small()
        for ob in bpy.context.view_layer.objects: ob.select_set(False)
        for ob in SELS[sel]: ob.select_set(True)
        bpy.context.view_layer.objects.active=SELS[sel][0]; bpy.context.view_layer.update()
        before={ob.name for ob in bpy.data.objects}
        o=make(cls)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                t=time.perf_counter(); r=type(o).invoke(o,ctx,ev('NONE','NOTHING',*scr(*CL[sel][0]))); inv=max(inv,time.perf_counter()-t)
                if 'RUNNING_MODAL' in r:
                    sd=getattr(o,'snap_data',None)
                    if sd is not None and isinstance(sd,m.SnapData): m._screen_index(sd,persp,region,allow_async=False)
                    done=False
                    for stage,(x,y) in enumerate(CL[sel]):
                        for k in range(10):
                            px,py=scr(x+random.uniform(-2.5,2.5),y+random.uniform(-2.5,2.5))
                            t=time.perf_counter(); r=type(o).modal(o,ctx,ev('MOUSEMOVE','NOTHING',px,py)); dt=time.perf_counter()-t
                            if k>0:      # le 1er mouvement d'une étape peut construire un cache
                                allm.append(dt)
                                if dt>worst[0]: worst=(dt,f"{sel}/étape {stage}")
                            if 'FINISHED' in r or 'CANCELLED' in r: done=True; break
                        if done: break
                        sx,sy=scr(x,y)
                        for e in (ev('MOUSEMOVE','NOTHING',sx,sy),ev('LEFTMOUSE','PRESS',sx,sy),ev('LEFTMOUSE','RELEASE',sx,sy)):
                            r=type(o).modal(o,ctx,e)
                            if 'FINISHED' in r or 'CANCELLED' in r: done=True; break
                        if done: break
                    if not done: type(o).modal(o,ctx,ev('ESC','PRESS',*scr(0,0)))
        except Exception as e:
            print("EXC",cls.__name__,sel,repr(e)[:120])
        finally:
            try:
                with contextlib.redirect_stdout(io.StringIO()): type(o).cleanup(o,ctx)
            except Exception: pass
    if allm:
        rows.append((float(np.percentile(allm,95))*1000,float(np.median(allm))*1000,inv*1000,cls.__name__[10:],worst[1],len(allm),max(allm)*1000,sum(1 for x in allm if x>0.016)))
rows.sort(reverse=True)
print(f"=== {MODE} : coût d'un mouvement de souris par outil (ms) — max / médiane / lancement ; {len(rows)} outils")
for p95,med,inv,name,where,n,mx,nslow in rows[:16]:
    print(f"{name:20s} p95 {p95:7.2f}  médiane {med:6.2f}  max {mx:8.1f}  >16ms: {nslow:3d}/{n}  lancement {inv:7.1f}  (pire: {where})")
print("lancements les plus lents:", ", ".join(f"{r[3]} {r[2]:.0f} ms" for r in sorted(rows,key=lambda r:-r[2])[:8]))
slow=[r for r in rows if r[0]>16]; mid=[r for r in rows if 8<r[0]<=16]
print(f"RESULTAT {MODE}: p95 > 16 ms pour {len(slow)} outils, entre 8 et 16 ms pour {len(mid)} ; médiane globale {np.median([r[1] for r in rows]):.2f} ms ; mouvements > 16 ms : {sum(r[7] for r in rows)} sur {sum(r[5] for r in rows)} ; lancement max {max(r[2] for r in rows):.0f} ms")
