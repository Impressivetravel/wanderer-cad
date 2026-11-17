import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
import traceback, numpy as np
C=bpy.context
res=[]
def chk(name,ok,info=""):
    res.append(bool(ok)); print(("OK  " if ok else "BAD ")+name, info)
def clear():
    for o in list(bpy.data.objects): bpy.data.objects.remove(o)
def wpts(o):
    dg=C.evaluated_depsgraph_get(); return m.object_paths(o,dg)
# rebuild
clear()
P=[Vector((x,math.sin(x),0)) for x in np.linspace(0,6.28,60)]
o=m.build_polyline(C,"S",P,False); C.view_layer.update()
op=make(m.DESSIN_OT_rebuild_crv); op.points=12; op.degree=3
print(type(op).execute(op,ctx), op._reports)
sp=o.data.splines[0]
chk("Rebuild : NURBS 12 pts degré 3", sp.type=='NURBS' and len(sp.points)==12 and sp.order_u==4, (sp.type,len(sp.points),sp.order_u))
C.view_layer.update()
Q=np.asarray(wpts(o)[0][0]); err=max(abs(q[1]-math.sin(q[0])) for q in Q)
chk("Rebuild : forme gardée (écart < 0.02)", err<0.02, round(err,4))
chk("Rebuild : extrémités gardées", np.allclose(Q[0],(0,0,0),atol=1e-6) and abs(Q[-1][0]-6.28)<1e-4, (Q[0],Q[-1]))
# closed rebuild
clear()
o=m.build_polyline(C,"Ci",[Vector((math.cos(a)*3,math.sin(a)*3,0)) for a in np.linspace(0,6.283,64,endpoint=False)],True); C.view_layer.update()
op=make(m.DESSIN_OT_rebuild_crv); op.points=8; op.degree=3; type(op).execute(op,ctx)
C.view_layer.update(); Q=np.asarray(wpts(o)[0][0]); r=np.linalg.norm(Q[:,:2],axis=1)
chk("Rebuild fermé : cercle r≈3", abs(r.mean()-3)<0.05 and r.std()<0.03, (round(r.mean(),3),round(r.std(),4), o.data.splines[0].use_cyclic_u))
# simplify
clear()
P=[Vector((x,0,0)) for x in np.linspace(0,10,51)]+[Vector((10,y,0)) for y in np.linspace(0.2,5,25)]
o=m.build_polyline(C,"L",P,False); C.view_layer.update()
op=make(m.DESSIN_OT_simplify_crv); op.tolerance=0.001; type(op).execute(op,ctx)
chk("Simplify : polyligne en L -> 3 points", len(o.data.splines[0].points)==3, (len(o.data.splines[0].points), op._reports))
# change degree
clear()
o=m.build_polyline(C,"D",[Vector(p) for p in [(0,0,0),(2,3,0),(5,-1,0),(8,2,0)]],False)
op=make(m.DESSIN_OT_change_degree); op.degree=3; type(op).execute(op,ctx)
sp=o.data.splines[0]; chk("Change Degree : NURBS ordre 4", sp.type=='NURBS' and sp.order_u==4 and sp.use_endpoint_u, (sp.type,sp.order_u))
op.degree=1; type(op).execute(op,ctx); chk("Change Degree 1 : polyligne", o.data.splines[0].type=='POLY')
# insert / remove
clear()
o=m.build_polyline(C,"I",[Vector(p) for p in [(0,0,0),(10,0,0),(10,5,0)]],False)
m.insert_control_point(o,0,0,0.3)
pts=[tuple(round(c,3) for c in q.co[:3]) for q in o.data.splines[0].points]
chk("Insert point polyligne", pts==[(0,0,0),(3,0,0),(10,0,0),(10,5,0)], pts)
m.remove_control_point(o,0,2); pts=[tuple(round(c,3) for c in q.co[:3]) for q in o.data.splines[0].points]
chk("Remove point", pts==[(0,0,0),(3,0,0),(10,5,0)], pts)
# bezier insert keeps shape
clear()
A=m.build_bezier_arc(C,"Arc",Vector((0,0,0)),Vector((1,0,0)),Vector((0,1,0)),5.0,0.0,math.pi,False)
C.view_layer.update(); before=np.asarray(wpts(A)[0][0])
n0=len(A.data.splines[0].bezier_points)
m.insert_control_point(A,0,0,0.5); C.view_layer.update(); after=np.asarray(wpts(A)[0][0])
r=np.linalg.norm(after[:,:2],axis=1)
chk("Insert point Bézier : forme gardée (arc r=5)", len(A.data.splines[0].bezier_points)==n0+1 and abs(r.max()-5)<0.01 and abs(r.min()-5)<0.01, (n0, round(r.min(),4), round(r.max(),4)))
# match curve (polylines)
clear()
a=m.build_polyline(C,"a",[Vector(p) for p in [(0,0,0),(4,0,0),(8,1,0)]],False)
b=m.build_polyline(C,"b",[Vector(p) for p in [(10,5,0),(10,2,0)]],False)
m.match_curve(a,0,True,b,0,True,True)
pts=[tuple(round(c,3) for c in q.co[:3]) for q in a.data.splines[0].points]
chk("MatchCrv : fin de a sur fin de b, tangente", pts[-1]==(10,2,0) and abs(pts[-2][0]-10)<1e-6 and pts[-2][1]<2, pts)
# blend
clear()
a=m.build_polyline(C,"a",[Vector(p) for p in [(0,0,0),(4,0,0)]],False)
b=m.build_polyline(C,"b",[Vector(p) for p in [(8,4,0),(8,8,0)]],False)
pts=m.blend_curve_points(a,0,True,b,0,False)
ob=m.build_blend_curve(C,pts)
q=ob.data.splines[0].bezier_points
chk("BlendCrv : tangente à a et à b", (q[0].handle_right-q[0].co).normalized().dot(Vector((1,0,0)))>0.999 and (q[1].handle_left-q[1].co).normalized().dot(Vector((0,-1,0)))>0.999, (q[0].handle_right, q[1].handle_left))
print("RESULTAT",sum(res),"/",len(res))
