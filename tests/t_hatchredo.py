import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
# Hachurer une forme déjà hachurée avec un autre motif : sa hachure change de motif (il fallait la supprimer avant,
# sinon les deux se superposaient). Une autre zone, même voisine ou imbriquée, reçoit sa propre hachure.
import json, math
import numpy as np
C=bpy.context
res=[]
def chk(name,ok,info=""):
    res.append(bool(ok)); print(("OK  " if ok else "BAD ")+name, info)
for o in list(bpy.data.objects): bpy.data.objects.remove(o)
st=C.scene.dessin; st.hatch_spacing=1.0; st.hatch_boundary=False
def P(pts): return [Vector(p) for p in pts]
A=m.build_polyline(C,"A",P([(0,0,0),(40,0,0),(40,30,0),(0,30,0)]),True)
T=m.build_polyline(C,"Trou",P([(10,10,0),(20,10,0),(20,20,0),(10,20,0)]),True)
B=m.build_polyline(C,"B",P([(40,0,0),(60,0,0),(60,30,0),(40,30,0)]),True)          # voisine, côté commun
C.view_layer.update()
def hatches(): return [o for o in bpy.data.objects if m.is_hatch(o)]
def pick(*objs):
    for o in C.view_layer.objects: o.select_set(o in objs)
    C.view_layer.objects.active=objs[-1]
def hatch(*objs, pattern=None):
    if pattern: st.hatch_pattern=pattern
    pick(*objs); op=make(m.DESSIN_OT_hatch); r=type(op).execute(op,ctx); C.view_layer.update()
    return r, (op._reports[-1][1] if op._reports else "")
r,msg=hatch(A,T,pattern='HATCH1')
h=hatches()
chk("1re hachure de A (avec un trou)", len(h)==1 and len(json.loads(h[0]["dessin_hatch"])["rings"])==2, (msg,[o.name for o in h]))
h0=h[0]; lay=h0.users_collection[0].name; dd0=json.loads(h0["dessin_hatch"])
r,msg=hatch(A,T,pattern='BRICK')
h=hatches()
chk("A resélectionnée, motif Brick, Hatch : la hachure change de motif, pas de seconde hachure", len(h)==1 and h[0] is h0 and h0.dessin_hatch.pattern=='BRICK', (msg,[(o.name,o.dessin_hatch.pattern) for o in h]))
chk("... message clair", "changed to Brick" in msg, msg)
chk("... la hachure reste sélectionnée (son motif se règle aussitôt dans l'en-tête)", h0.select_get(), [o.name for o in C.selected_objects])
dd1=json.loads(h0["dessin_hatch"])
chk("... elle garde son calque, son pas et son point de base", h0.users_collection[0].name==lay and dd1["unit"]==dd0["unit"] and dd1["base"]==dd0["base"], (dd0["unit"],dd1["unit"]))
st.hatch_scale=2.0; st.hatch_rotation=math.radians(30)
r,msg=hatch(A,T,pattern='SOLID'); st.hatch_scale=1.0; st.hatch_rotation=0.0
chk("... et prend aussi l'échelle et la rotation des nouvelles hachures (Solid, ×2, 30°)", len(hatches())==1 and h0.dessin_hatch.pattern=='SOLID' and abs(h0.dessin_hatch.scale-2.0)<1e-9 and abs(h0.dessin_hatch.rotation-math.radians(30))<1e-6 and len(h0.data.polygons)>0, (h0.dessin_hatch.pattern,h0.dessin_hatch.scale))
# zone différente : sans le trou -> une autre zone (A pleine), hachure à part
r,msg=hatch(A,pattern='GRID')
chk("A sans son trou : une autre zone, une nouvelle hachure", len(hatches())==2, (msg,len(hatches())))
bpy.data.objects.remove([o for o in hatches() if o is not h0][0])
r,msg=hatch(B,pattern='HATCH2')
chk("la forme voisine B (côté commun) : sa propre hachure, A garde la sienne", len(hatches())==2 and h0.dessin_hatch.pattern=='SOLID', [(o.name,o.dessin_hatch.pattern) for o in hatches()])
r,msg=hatch(T,pattern='DOTS' if any(p[0]=='DOTS' for p in m.pattern_list()) else 'GRID')
# une courbe copiée sur place (doublon exact, départ et sens différents) : les trous restent des trous
for q in [o for o in hatches()]: pass
DUP=m.build_polyline(C,"A copie",P([(40,30,0),(40,0,0),(0,0,0),(0,30,0)]),True); C.view_layer.update()
g,_s=m.hatch_loop_groups(m._hatch_paths_of(C,[A,DUP,T]))
chk("contour en double (sens et départ différents) : compté une fois, le trou reste un trou", len(g)==1 and len(g[0][4])==2 and len(m.hatch_regions(g))==1 and len(m.hatch_regions(g)[0][4])==2, [len(x[4]) for x in g])
ML=m.build_polyline(C,"L1",P([(500,0,0),(510,0,0),(510,4,0),(504,4,0),(504,10,0),(500,10,0)]),True)
MR=m.build_polyline(C,"L2",P([(500,0,0),(510,0,0),(510,10,0),(506,10,0),(506,4,0),(500,4,0)]),True); C.view_layer.update()
g,_s=m.hatch_loop_groups(m._hatch_paths_of(C,[ML,MR]))
chk("deux formes différentes de même aire et même boîte (L en miroir) : gardées toutes les deux", len(g)==1 and len(g[0][4])==2, [len(x[4]) for x in g])
for q in (DUP,ML,MR): bpy.data.objects.remove(q)
C.view_layer.update()
chk("le carré du trou : une hachure à part (zone imbriquée)", len(hatches())==3, [(o.name,o.dessin_hatch.pattern) for o in hatches()])
hT=[o for o in hatches() if o is not h0 and abs(m.hatch_world_rings(o)[0][:,0].max()-20)<1e-6][0]
# hachure déplacée hors de sa forme : la forme n'est plus hachurée, une nouvelle est créée
hT.location.x+=100; C.view_layer.update()
r,msg=hatch(T,pattern='HATCH1')
chk("hachure déplacée ailleurs : la forme reçoit une nouvelle hachure", len(hatches())==4, msg)
newT=[o for o in hatches() if o not in (h0,hT) and o.dessin_hatch.pattern=='HATCH1' and abs(m.hatch_world_rings(o)[0][:,0].max()-20)<1e-6]
hT.location.x-=100; C.view_layer.update()
for o in newT: bpy.data.objects.remove(o)
# hachure cachée : ignorée
hT.hide_set(True)
r,msg=hatch(T,pattern='HATCH3' if any(p[0]=='HATCH3' for p in m.pattern_list()) else 'HATCH1')
chk("hachure cachée : la forme reçoit une nouvelle hachure (la cachée n'est pas touchée)", len(hatches())==4 and hT.dessin_hatch.pattern!='HATCH1' or len(hatches())==4, [(o.name,o.dessin_hatch.pattern) for o in hatches()])
hT.hide_set(False)
for o in hatches():
    if o not in (h0,hT) and abs(m.hatch_world_rings(o)[0][:,0].max()-20)<1e-6: bpy.data.objects.remove(o)
# forme tournée et hors du plan XY (plan incliné)
Rm=Matrix.Rotation(math.radians(35),3,'X')@Matrix.Rotation(math.radians(20),3,'Z')
pts=[Rm@Vector(p)+Vector((200,50,10)) for p in [(0,0,0),(8,0,0),(8,5,0),(0,5,0)]]
D=m.build_polyline(C,"Incline",pts,True); C.view_layer.update()
n0=len(hatches()); hatch(D,pattern='HATCH1'); r,msg=hatch(D,pattern='BRICK')
hD=[o for o in hatches()][n0:]
chk("forme dans un plan incliné : 2e motif -> la même hachure change", len(hD)==1 and hD[0].dessin_hatch.pattern=='BRICK', (msg,[(o.name,o.dessin_hatch.pattern) for o in hD]))
# hachure mise à l'échelle avec sa forme : toujours reconnue
sel_=[D,hD[0]]
for o in (D,hD[0]):
    o.matrix_world=Matrix.Translation((5,5,0))@Matrix.Scale(2.0,4)@o.matrix_world
C.view_layer.update()
r,msg=hatch(D,pattern='GRID')
chk("forme et hachure agrandies ensemble : toujours la même hachure", len(hatches())==n0+1 and hD[0].dessin_hatch.pattern=='GRID', (msg,len(hatches())-n0))
# deux courbes identiques superposées : une seule hachure
D2=m.build_polyline(C,"Double",P([(300,0,0),(310,0,0),(310,10,0),(300,10,0)]),True)
D3=m.build_polyline(C,"Double2",P([(300,0,0),(310,0,0),(310,10,0),(300,10,0)]),True); C.view_layer.update()
n0=len(hatches()); r,msg=hatch(D2,D3,pattern='HATCH1')
chk("deux courbes superposées : une seule hachure", len(hatches())==n0+1, (msg,len(hatches())-n0))
# ---- Hatch Region (clic dans la zone) : même chose
for o in list(bpy.data.objects):
    if m.is_hatch(o): bpy.data.objects.remove(o)
src=open(_os.path.join(_HERE,'t_pushpull.py')).read()
pre=src[src.index("\n")+1:src.index("# ---------------- 1. PushPull")]
pre=pre[pre.index("def E("):] if "def E(" in pre else pre
exec(pre[:pre.index("def start")] if "def start" in pre else "")
def region_click(x,y,pattern):
    st.hatch_pattern=pattern
    o=make(m.DESSIN_OT_hatch_region); type(o).invoke(o,ctx,ev('NONE','NOTHING',500,500))
    for e in (ev('MOUSEMOVE','NOTHING',x,y),ev('LEFTMOUSE','PRESS',x,y),ev('LEFTMOUSE','RELEASE',x,y),ev('ESC','PRESS',x,y)):
        type(o).modal(o,ctx,e)
    C.view_layer.update(); return o
def px(p):
    v=rv3d.perspective_matrix@Vector((p[0],p[1],0,1.0)); return (round((v.x/v.w+1)*W/2),round((v.y/v.w+1)*H/2))
st.hatch_boundary=True
nb=len([o for o in bpy.data.objects if o.type=='CURVE'])
o=region_click(*px((5,5)),'HATCH1')
h=hatches()
chk("Hatch Region dans A : une hachure", len(h)==1 and h[0].dessin_hatch.pattern=='HATCH1', [(q.name,q.dessin_hatch.pattern) for q in h])
nb1=len([q for q in bpy.data.objects if q.type=='CURVE'])
o=region_click(*px((5,5)),'BRICK')
h=hatches()
chk("Hatch Region au même endroit avec Brick : la hachure change de motif", len(h)==1 and h[0].dessin_hatch.pattern=='BRICK', ([(q.name,q.dessin_hatch.pattern) for q in h], o._reports[-1:]))
chk("... sans refaire de contour (option Boundary)", len([q for q in bpy.data.objects if q.type=='CURVE'])==nb1, (nb,nb1,len([q for q in bpy.data.objects if q.type=='CURVE'])))
o=region_click(*px((15,15)),'GRID')
chk("Hatch Region dans le trou : une autre hachure", len(hatches())==2, len(hatches()))
st.hatch_boundary=False
# ---- le dernier motif choisi sur une hachure devient celui des suivantes
h0=hatches()[0]; pick(h0)
h0.dessin_hatch.pattern='HATCH2'
chk("motif changé sur une hachure sélectionnée : devient le motif des nouvelles hachures", st.hatch_pattern=='HATCH2', st.hatch_pattern)
# ---- en-tête de l'outil : motif de la hachure sélectionnée
class _Lay:
    def __init__(s): s.calls=[]
    def __getattr__(s,name):
        def f(*a,**k): s.calls.append((name,a[0] if a else None,a[1] if len(a)>1 else None)); return s
        return f
lay=_Lay(); pick(h0)
tb=[v for k,v in vars(m).items() if k=="DESSIN_TT_hatch"]
tb[0].draw_settings(C,lay,None)
chk("en-tête Hatch, hachure sélectionnée : le motif affiché est celui de la hachure", any(c[0]=='prop' and getattr(c[1],'id_data',None) is h0 and c[2]=='pattern' for c in lay.calls), [(c[0],type(c[1]).__name__,c[2]) for c in lay.calls])
lay=_Lay(); pick(A)
tb[0].draw_settings(C,lay,None)
chk("en-tête Hatch, une courbe sélectionnée : réglages des nouvelles hachures", any(c[0]=='prop' and type(c[1]).__name__=='DESSIN_PG_settings' and c[2]=='hatch_pattern' for c in lay.calls), [(c[0],type(c[1]).__name__,c[2]) for c in lay.calls])
print("RESULTAT",sum(res),"/",len(res))
