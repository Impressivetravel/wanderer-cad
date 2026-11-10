import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
import sys, math, importlib.util, numpy as np
import bpy
from mathutils import Vector, Matrix
from types import SimpleNamespace as NS
sp=importlib.util.spec_from_file_location('m',_SRC);m=importlib.util.module_from_spec(sp);sys.modules['m']=m;sp.loader.exec_module(m)
def circ(c,r,n=(0,0,1)):
    th=np.linspace(0,2*np.pi,48,endpoint=False)
    P=np.array([(c[0]+r*np.cos(t),c[1]+r*np.sin(t),c[2]) for t in th])
    return m.circle_info(np.array(c,float),P)
A=circ((0,0,0),1.0); B=circ((6,0,0),2.0)
ct=m.common_tangents(A,B)
print("n tangents",len(ct))
ok=True
for ta,tb in ct:
    d=tb-ta
    ok&=abs(np.dot(ta-A[0],d))<1e-9 and abs(np.dot(tb-B[0],d))<1e-9
    ok&=abs(np.linalg.norm(ta-A[0])-1)<1e-9 and abs(np.linalg.norm(tb-B[0])-2)<1e-9
print("tangent exact (perp radius at both ends):",ok)
# égaux rayons => 2 extérieures parallèles
ct2=m.common_tangents(circ((0,0,0),1.0),circ((5,0,0),1.0)); print("equal radii",len(ct2),[tuple(np.round(b-a,3)) for a,b in ct2])
# cercles imbriqués -> aucune
print("nested",len(m.common_tangents(circ((0,0,0),3.0),circ((0.5,0,0),1.0))))
# dynamic_snap avec vue ortho de dessus fictive
class R3: pass
rv=NS(perspective_matrix=Matrix(((1/10,0,0,0),(0,1/10,0,0),(0,0,0.01,0),(0,0,0,1))))
reg=NS(width=1000,height=1000)
persp=np.array(rv.perspective_matrix,dtype=np.float64)
class SD(tuple):
    pass
snap=SD(((np.zeros((0,3)),np.zeros((0,4)),np.zeros(0,int),np.zeros(0))))
snap.circles=[A,B]; snap.edges=None
m.register()
sc=bpy.context.scene; sc.dessin.osnap_tan=True; sc.dessin.osnap_disable=False if hasattr(sc.dessin,'osnap_disable') else None
def px(x,y): return ((x/10*0.5+0.5)*1000,(y/10*0.5+0.5)*1000)
# 1er point : curseur près du cercle A (point (0,1))
sx,sy=px(0.0,1.0)
m._TAN["first_ok"]=True
r=m.dynamic_snap(snap,sx+3,sy+2,reg,rv,persp,None,12.0)
m._TAN["first_ok"]=False
print("first:",r and (tuple(np.round(r[0],3)),r[2]), m._TAN["info"] and m._TAN["info"][0])
# 2e point : près de B ; tangente extérieure du haut
pend=m._TAN["info"][1]
m._TAN["pend"]=pend
ta,tb=max(ct,key=lambda t:t[1][1]+t[0][1])      # extérieure du haut
sx,sy=px(*tb[:2])
r=m.dynamic_snap(snap,sx+2,sy+2,reg,rv,persp,Vector((0,1,0)),12.0)
inf=m._TAN["info"]
print("second:",tuple(np.round(r[0],3)),r[2],inf[0],tuple(np.round(inf[1],3)))
print("matches expected:",np.allclose(r[0],tb,atol=1e-6) and np.allclose(inf[1],ta,atol=1e-6))
# sans pend : tangente d'un point (comportement d'origine)
m._TAN["pend"]=None
r=m.dynamic_snap(snap,sx+2,sy+2,reg,rv,persp,Vector((0,1,0)),12.0)
print("fallback point-tangent:", r is None or (r[2]==10 and m._TAN["info"] is None))
# first_ok False + ref None => rien
r=m.dynamic_snap(snap,*px(0,1),reg,rv,persp,None,12.0); print("no first without flag:",r is None)
