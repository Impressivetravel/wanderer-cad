import bmesh, io, contextlib, math
import numpy as np
m.DessinTransform=mirror(m.DessinTransform)
RES=[]   # (section, nom, ok, mesure)
def rec(sec,name,ok,meas=""):
    RES.append((sec,name,bool(ok),meas)); print(("OK  " if ok else "BAD ")+f"[{sec}] {name}  {meas}")
def clear():
    for o in list(bpy.data.objects): bpy.data.objects.remove(o)
    for c in list(bpy.data.collections):
        try: bpy.data.collections.remove(c)
        except Exception: pass
    bpy.context.view_layer.update()
def C(x,y): return ('c',x,y)
def M(x,y): return ('m',x,y)
def T(*vals): return ('T',vals)
def K(k,**kw): return ('k',k,kw)
def run(cls,evs,sel=None,p0=(0,0)):
    """Lance un outil et lui envoie des évènements. C(x,y) clic ; M déplacement ; T(v...) valeurs tapées ; 'RET' ... touches."""
    if isinstance(cls,str): cls=getattr(m,"DESSIN_OT_"+cls)
    if sel is not None:
        for ob in bpy.context.view_layer.objects: ob.select_set(False)
        for ob in sel: ob.select_set(True)
        bpy.context.view_layer.objects.active=sel[0] if sel else None
        bpy.context.view_layer.update()
    before={ob.name for ob in bpy.data.objects}
    o=make(cls); r=None
    with contextlib.redirect_stdout(io.StringIO()):
        r=type(o).invoke(o,ctx,ev('NONE','NOTHING',*scr(*p0)))
        if 'RUNNING_MODAL' in r:
            done=False
            for e in evs:
                if isinstance(e,tuple) and e[0]=='c':
                    sx,sy=scr(e[1],e[2]); seq=[ev('MOUSEMOVE','NOTHING',sx,sy),ev('LEFTMOUSE','PRESS',sx,sy),ev('LEFTMOUSE','RELEASE',sx,sy)]
                elif isinstance(e,tuple) and e[0]=='m':
                    seq=[ev('MOUSEMOVE','NOTHING',*scr(e[1],e[2]))]
                elif isinstance(e,tuple) and e[0]=='T':
                    # vraies frappes clavier : chiffres, point, signe ; Tab entre les champs
                    KEY={'0':'ZERO','1':'ONE','2':'TWO','3':'THREE','4':'FOUR','5':'FIVE','6':'SIX','7':'SEVEN','8':'EIGHT','9':'NINE','.':'PERIOD','-':'MINUS',',':'COMMA','<':'COMMA','@':'TWO','#':'THREE',';':'SEMI_COLON'}
                    seq=[]
                    for i_,v in enumerate(e[1]):
                        if i_: seq.append(ev('TAB','PRESS',*scr(0,0)))
                        for ch in str(v): seq.append(ev(KEY.get(ch,'A'),'PRESS',*scr(0,0),unicode=ch,ascii=ch))
                elif isinstance(e,tuple) and e[0]=='k':
                    seq=[ev(e[1],'PRESS',*scr(0,0),**e[2])]
                else:
                    seq=[ev(e,'PRESS',*scr(0,0))]
                for x in seq:
                    r=type(o).modal(o,ctx,x)
                    if 'FINISHED' in r or 'CANCELLED' in r: done=True; break
                if done: break
    try:
        with contextlib.redirect_stdout(io.StringIO()): type(o).cleanup(o,ctx)
    except Exception: pass
    bpy.context.view_layer.update()
    new=[ob for ob in bpy.data.objects if ob.name not in before]
    return new,r,o
def paths(o):
    return m.object_paths(o,bpy.context.evaluated_depsgraph_get())
def bez_eval(o,n=200):
    """Points EXACTS de la courbe de Bézier (mathématique, pas la tessellation d'affichage)."""
    out=[]
    mw=np.array(o.matrix_world)
    for sp in o.data.splines:
        if sp.type!='BEZIER': continue
        bp=sp.bezier_points; k=len(bp); segs=k if sp.use_cyclic_u else k-1
        for i in range(segs):
            a,b=bp[i],bp[(i+1)%k]
            P0,P1,P2,P3=[np.array(v) for v in (a.co,a.handle_right,b.handle_left,b.co)]
            t=np.linspace(0,1,n)[:,None]
            out.append((1-t)**3*P0+3*(1-t)**2*t*P1+3*(1-t)*t**2*P2+t**3*P3)
    P=np.vstack(out) if out else np.zeros((0,3))
    return P@mw[:3,:3].T+mw[:3,3]
def ctrl_pts(o):
    mw=np.array(o.matrix_world); out=[]
    for sp in o.data.splines:
        pts=[tuple(p.co)[:3] for p in (sp.bezier_points if sp.type=='BEZIER' else sp.points)]
        out.append(np.array(pts)@mw[:3,:3].T+mw[:3,3])
    return out
def mverts(o):
    me=o.evaluated_get(bpy.context.evaluated_depsgraph_get()).data
    co=np.empty(len(me.vertices)*3); me.vertices.foreach_get('co',co)
    mw=np.array(o.matrix_world); return co.reshape(-1,3)@mw[:3,:3].T+mw[:3,3]
def vol_area(o):
    bm=bmesh.new(); bm.from_object(o,bpy.context.evaluated_depsgraph_get()); bm.transform(o.matrix_world)
    bmesh.ops.triangulate(bm,faces=bm.faces[:])
    v=abs(bm.calc_volume(signed=True)); a=sum(f.calc_area() for f in bm.faces)
    naked=sum(1 for e in bm.edges if len(e.link_faces)==1); nonman=sum(1 for e in bm.edges if len(e.link_faces)>2)
    bm.free(); return v,a,naked,nonman
def bbox(P): P=np.asarray(P); return P.min(0),P.max(0)
def near(a,b,tol=1e-6): return bool(np.allclose(np.asarray(a,dtype=float),np.asarray(b,dtype=float),atol=tol))
def summary():
    bad=[r for r in RES if not r[2]]
    print(f"RESULTAT précision : {len(RES)-len(bad)} / {len(RES)}")
    for r in bad: print("   ECHEC",r[0],r[1],r[3])
