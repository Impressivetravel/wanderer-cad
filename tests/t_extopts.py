import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
import math, numpy as np
C=bpy.context
res=[]
def chk(n,ok,info=""): res.append(bool(ok)); print(("OK  " if ok else "BAD ")+n, info)
def clear():
    for o in list(bpy.data.objects): bpy.data.objects.remove(o)
def naked(o):
    ec={}
    for p in o.data.polygons:
        for k in p.edge_keys: ec[k]=ec.get(k,0)+1
    return sum(1 for v in ec.values() if v==1)
def run(opts, objs, vec=(0,0,2), cap=True):
    o=make(m.DESSIN_OT_extrude_crv); o.items=[(x,None) for x in objs]
    o.both=opts.get("bothk",False); o.taper=False; o.topoint=False; o.draft=5.0
    type(o).build(o,ctx,("extrude",Vector(),Vector(vec),cap,False,opts))
    return [x for x in bpy.data.objects if x.type=='MESH']
def bbox(o):
    W=[o.matrix_world@v.co for v in o.data.vertices]; return [round(min(p[i] for p in W),3) for i in range(3)]+[round(max(p[i] for p in W),3) for i in range(3)]
sq=lambda name,s,z=0: m.build_polyline(C,name,[Vector(p) for p in [(-s,-s,z),(s,-s,z),(s,s,z),(-s,s,z)]],True)
# both sides
clear(); a=sq("A",2); C.view_layer.update()
ms=run({"both":True,"taper":0.0,"apex":None},[a])
chk("BothSides : de -2 à +2, fermé", ms and bbox(ms[0])[2]==-2 and bbox(ms[0])[5]==2 and naked(ms[0])==0, (bbox(ms[0]),naked(ms[0])))
# tapered 45° (shrinks by h): top square half-size 2-2=0? use 20°
clear(); a=sq("A",2); C.view_layer.update()
ms=run({"both":False,"taper":math.radians(20),"apex":None},[a])
top=[ (ms[0].matrix_world@v.co) for v in ms[0].data.vertices if abs((ms[0].matrix_world@v.co).z-2)<1e-6]
hs=max(abs(p.x) for p in top); exp=2-2*math.tan(math.radians(20))
chk("Tapered 20° : le haut se resserre", abs(hs-exp)<1e-4 and naked(ms[0])==0, (round(hs,4),round(exp,4),naked(ms[0])))
# tapered with hole: hole grows
clear(); a=sq("A",3); b=sq("B",1); C.view_layer.update()
ms=run({"both":False,"taper":math.radians(10),"apex":None},[a,b])
top=[ (ms[0].matrix_world@v.co) for v in ms[0].data.vertices if abs((ms[0].matrix_world@v.co).z-2)<1e-6]
xs=sorted({round(abs(p.x),4) for p in top})
chk("Tapered avec trou : contour se resserre, trou s'élargit, fermé", len(ms)==1 and abs(xs[0]-(1+2*math.tan(math.radians(10))))<1e-3 and abs(xs[-1]-(3-2*math.tan(math.radians(10))))<1e-3 and naked(ms[0])==0, (xs, naked(ms[0])))
# to point
clear(); a=sq("A",2); C.view_layer.update()
ms=run({"both":False,"taper":0.0,"apex":(0,0,3)},[a])
chk("ToPoint : pyramide fermée", ms and len(ms[0].data.polygons)==5 and naked(ms[0])==0 and bbox(ms[0])[5]==3, (len(ms[0].data.polygons),naked(ms[0])))
# open curve to point
clear(); l=m.build_polyline(C,"L",[Vector((0,0,0)),Vector((2,0,0)),Vector((2,2,0))],False); C.view_layer.update()
ms=run({"both":False,"taper":0.0,"apex":(0,0,3)},[l])
chk("ToPoint courbe ouverte : 2 triangles", ms and len(ms[0].data.polygons)==2, len(ms[0].data.polygons) if ms else None)
# open curve both sides taper
clear(); l=m.build_polyline(C,"L",[Vector((0,0,0)),Vector((2,0,0)),Vector((2,2,0))],False); C.view_layer.update()
ms=run({"both":True,"taper":math.radians(10),"apex":None},[l])
chk("Courbe ouverte, deux côtés + dépouille", ms and len(ms[0].data.polygons)==4, len(ms[0].data.polygons) if ms else None)
# modal keys flow
clear(); a=sq("A",2); C.view_layer.update()
for x in C.view_layer.objects: x.select_set(True)
o=make(m.DESSIN_OT_extrude_crv); cls=type(o)
print(cls.invoke(o,ctx,ev('NONE','NOTHING',*scr(0,0))))
for k in ('B','T'): cls.modal(o,ctx,ev(k,'PRESS',*scr(0,0)))
print("both",o.both,"taper",o.taper,"fields",o.NUMFIELDS, o.prompt())
print("RESULTAT",sum(res),"/",len(res))
o.points=[Vector((0,0,0))]; o.cur=Vector((0,0,2)); o._paths=None
r=type(o).compute(o); print("compute spec opts", r[3][5] if r[3] else None, len(r[1]))
type(o).build(o,ctx,r[3]); print([x.name for x in bpy.data.objects if x.type=='MESH'], m._OPT_MEM.get("dessin.extrude_crv"))
