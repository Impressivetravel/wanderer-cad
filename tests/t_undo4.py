import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
exec(open(_os.path.join(_HERE,'undo_lib.py')).read())
m.DessinTransform=mirror(m.DessinTransform)
import bmesh
def scene(sel):
    for o in list(bpy.data.objects): bpy.data.objects.remove(o)
    def box(n,loc,s=4):
        me=bpy.data.meshes.new(n); bm=bmesh.new(); bmesh.ops.create_cube(bm,size=s); bm.to_mesh(me); bm.free()
        o=bpy.data.objects.new(n,me); bpy.context.scene.collection.objects.link(o); o.location=loc; return o
    a=box("A",(0,0,2)); b=box("B",(2,2,3))
    c=m.build_bezier_arc(bpy.context,"Circ",Vector((12,0,0)),Vector((1,0,0)),Vector((0,1,0)),3.0,0.0,m.TAU,True)
    r=m.build_polyline(bpy.context,"Rect",[Vector(p) for p in [(8,-10,0),(16,-10,0),(16,-6,0),(8,-6,0)]],True)
    for o in bpy.context.view_layer.objects: o.select_set(False)
    tg={'A':[a],'AB':[a,b],'circ':[c],'rect':[r],'none':[]}[sel]
    for t in tg: t.select_set(True)
    bpy.context.view_layer.objects.active=tg[0] if tg else None
    bpy.context.view_layer.update()
def E(o,*evs):
    r=None
    for e in evs:
        if isinstance(e,tuple) and e[0]=='c':
            sx,sy=scr(e[1],e[2])
            seq=[ev('MOUSEMOVE','NOTHING',sx,sy),ev('LEFTMOUSE','PRESS',sx,sy),ev('LEFTMOUSE','RELEASE',sx,sy)]
        elif isinstance(e,tuple) and e[0]=='m':
            seq=[ev('MOUSEMOVE','NOTHING',*scr(e[1],e[2]))]
        elif isinstance(e,tuple) and e[0]=='d':   # appui
            seq=[ev('MOUSEMOVE','NOTHING',*scr(e[1],e[2])),ev('LEFTMOUSE','PRESS',*scr(e[1],e[2]))]
        elif isinstance(e,tuple) and e[0]=='u':
            seq=[ev('LEFTMOUSE','RELEASE',*scr(e[1],e[2]))]
        elif isinstance(e,tuple) and e[0]=='t':   # texte tapé
            seq=[ev(ch.upper() if ch.isalpha() else {'1':'ONE','2':'TWO','5':'FIVE','0':'ZERO','.':'PERIOD'}.get(ch,'A'),'PRESS',*scr(0,0),unicode=ch,ascii=ch) for ch in e[1]]
        else:
            seq=[ev(e,'PRESS',*scr(0,0))]
        for x in seq:
            r=type(o).modal(o,ctx,x)
            if 'FINISHED' in r or 'CANCELLED' in r: return r
    return r
C=lambda x,y:('c',x,y)
SC=[
 ("annotation",'none',[C(1,1),C(5,4),C(8,4),'RET']),
 ("text",'none',[C(1,1),C(6,1),('t','ab'),'RET']),
 ("center_mark",'none',[C(15,0),C(15,0)]),
 ("cotation_rayon",'none',[C(15,0),C(18,3)]),
 ("bool_union",'AB',[C(0,0),'RET',C(3.5,3.5),'RET']),
 ("bool_union",'none',[C(-1.5,-1.5),'RET',C(3.5,3.5),'RET']),
 ("bool_difference",'none',[C(-1.5,-1.5),'RET',C(3.5,3.5),'RET']),
 ("bool_intersection",'none',[C(-1.5,-1.5),'RET',C(3.5,3.5),'RET']),
 ("bool_split",'none',[C(-1.5,-1.5),'RET',C(3.5,3.5),'RET']),
 ("fillet_edge",'none',[C(-2,-1),'RET',('t','0.5'),'RET']),
 ("fillet_edge",'A',[C(-2,-1),'RET',C(-1.5,-1),'RET']),
 ("chamfer_edge",'none',[C(-2,-1),'RET',('t','0.5'),'RET']),
 ("offset_edge",'none',[C(15,0),'RET',C(17,0)]),
 ("offset_edge",'rect',[C(12,-10),'RET',C(12,-11),'RET']),
 ("sketch",'none',[('d',1,1),('m',2,2),('m',3,2.5),('m',5,3),('m',7,2),('u',7,2),'ESC']),
 ("stretch",'rect',[C(14,-11),C(18,-5),C(16,-8),C(19,-8)]),
 ("stretch",'none',[C(14,-11),C(18,-5),'RET',C(16,-8),C(19,-8)]),
]
tot=dict(changed=0,undo_bad=0,redo_bad=0,exc=0)
seen=set()
for name,sel,evs in SC:
    cls=getattr(m,"DESSIN_OT_"+name)
    scene(sel); bpy.ops.ed.undo_push(message="A"); A=snapshot(bpy)
    o=make(cls)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            r=type(o).invoke(o,ctx,ev('NONE','NOTHING',*scr(0,0)))
            if 'RUNNING_MODAL' in r: r=E(o,*evs)
    except Exception:
        tot['exc']+=1; print(f"EXC {name} [{sel}] "+" | ".join(traceback.format_exc().strip().splitlines()[-3:])[:300]); continue
    finally:
        try: type(o).cleanup(o,ctx)
        except Exception: pass
    bpy.context.view_layer.update(); B=snapshot(bpy)
    if A==B:
        print(f"--   {name:18s} [{sel}] aucun changement  {sorted(r) if r else r}  {o._reports[-1:]}  prompt={type(o).prompt(o)[:70] if hasattr(o,'prompt') else ''}"); continue
    tot['changed']+=1; seen.add(name)
    bpy.ops.ed.undo_push(message=name); bpy.ops.ed.undo(); bpy.context.view_layer.update(); A2=snapshot(bpy)
    nun=1
    while A2!=A and name in ('sketch',) and nun<6:
        # Sketch enregistre une étape par trait : autant d'annulations que de traits
        bpy.ops.ed.undo(); bpy.context.view_layer.update(); A2=snapshot(bpy); nun+=1
    for _ in range(nun):
        bpy.ops.ed.redo(); bpy.context.view_layer.update()
    B2=snapshot(bpy)
    ok1,ok2=A2==A,B2==B
    tot['undo_bad']+=not ok1; tot['redo_bad']+=not ok2
    print(f"{'OK ' if ok1 and ok2 else 'BAD'}  {name:18s} [{sel}] modifié: {diff(A,B,2)}  undo={'ok' if ok1 else diff(A,A2,2)} redo={'ok' if ok2 else diff(B,B2,2)}")
print("RESULTAT",tot,"outils couverts:",sorted(seen))
