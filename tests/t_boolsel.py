import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
exec(open(_os.path.join(_HERE,'prec_lib.py')).read())
import bmesh
SEC="Booléens : le premier jeu reste en surbrillance"
def box(n,loc,s=4):
    me=bpy.data.meshes.new(n); bm=bmesh.new(); bmesh.ops.create_cube(bm,size=s); bm.to_mesh(me); bm.free()
    o=bpy.data.objects.new(n,me); bpy.context.scene.collection.objects.link(o); o.location=loc; return o
def scene():
    clear(); a=box("A",(0,0,2)); b=box("B",(2,2,3)); c=box("Far",(20,0,2),2)
    for o in bpy.context.view_layer.objects: o.select_set(False)
    bpy.context.view_layer.update()
def send(o,e):
    if isinstance(e,tuple):
        sx,sy=scr(e[1],e[2]); seq=[ev('MOUSEMOVE','NOTHING',sx,sy),ev('LEFTMOUSE','PRESS',sx,sy),ev('LEFTMOUSE','RELEASE',sx,sy)]
    else:
        seq=[ev(e,'PRESS',*scr(0,0))]
    r=None
    for x in seq:
        r=type(o).modal(o,ctx,x)
        if 'FINISHED' in r or 'CANCELLED' in r: break
    return r
# Sans écran, bpy.ops.view3d.select ne choisit rien : on le remplace, dans le module des booléens seulement, par un
# clic qui bascule l'objet (de type boîte) sous le point cliqué du plan XY, comme toggle=True de Blender
import sys, types
G=m.DESSIN_OT_bool_union.click.__globals__
_real=G['bpy']
def _fake_select(location=(0,0),toggle=False,**kw):
    x=(location[0]-W/2)/S; y=(location[1]-H/2)/S
    hit=None
    for ob in bpy.context.view_layer.objects:
        if ob.type!='MESH': continue
        cs=[ob.matrix_world @ Vector(c) for c in ob.bound_box]
        if min(c.x for c in cs)<=x<=max(c.x for c in cs) and min(c.y for c in cs)<=y<=max(c.y for c in cs):
            if hit is None or ob.location.z>hit.location.z: hit=ob
    if hit is not None:
        hit.select_set(not hit.select_get() if toggle else True)
        bpy.context.view_layer.objects.active=hit
    return {'FINISHED'}
class _Ops:
    def __getattr__(self,k):
        if k=='view3d': return types.SimpleNamespace(select=_fake_select)
        return getattr(_real.ops,k)
class _Bpy:
    ops=_Ops()
    def __getattr__(self,k): return getattr(_real,k)
G['bpy']=_Bpy()
def selnames(): return sorted(o.name for o in bpy.context.view_layer.objects if o.select_get())
for tool in ("bool_difference","bool_intersection","bool_split"):
    scene(); o=make(getattr(m,"DESSIN_OT_"+tool))
    with contextlib.redirect_stdout(io.StringIO()):
        type(o).invoke(o,ctx,ev('NONE','NOTHING',*scr(0,0)))
        send(o,C(-1.5,-1.5))
        s1=selnames()
        send(o,'RET')
        s2=selnames(); st=o.stage
        send(o,C(-1.5,-1.5))           # clic sur un objet du premier jeu : il doit rester sélectionné
        s3=selnames()
        send(o,C(3.5,3.5))
        s4=selnames()
        r=send(o,'RET')
    rec(SEC,f"{tool} : clic sur A sélectionne A",s1==["A"],s1)
    rec(SEC,f"{tool} : après Entrée, A reste sélectionné (étape 2)",st==1 and s2==["A"],f"étape {st}, sélection {s2}")
    rec(SEC,f"{tool} : re-cliquer A à l'étape 2 ne l'enlève pas",s3==["A"],s3)
    rec(SEC,f"{tool} : B s'ajoute, A toujours en surbrillance",s4==["A","B"],s4)
    names_now=sorted(ob.name for ob in bpy.data.objects)
    rec(SEC,f"{tool} : Entrée exécute le booléen (A en premier jeu, B en second)",r is not None and 'FINISHED' in r and names_now!=["A","B","Far"],f"{r} objets: {sorted(ob.name for ob in bpy.data.objects)}")
# Difference : le résultat est bien A - B (volume = 64 - 1*... ) : A 4x4x4 en (0,0,2), B 4x4x4 en (2,2,3) -> recouvrement 2x2x3 = 12
scene(); o=make(m.DESSIN_OT_bool_difference)
with contextlib.redirect_stdout(io.StringIO()):
    type(o).invoke(o,ctx,ev('NONE','NOTHING',*scr(0,0)))
    for e in (C(-1.5,-1.5),'RET',C(3.5,3.5),'RET'): r=send(o,e)
res=[ob for ob in bpy.data.objects if ob.name!="Far"]
def vol(ob):
    bm=bmesh.new(); bm.from_mesh(ob.data); bm.transform(ob.matrix_world); v=bm.calc_volume(); bm.free(); return abs(v)
V=vol(res[0]) if len(res)==1 else None
rec(SEC,"Difference A - B : volume 64 - 12 = 52 (le bon objet a été retenu en premier)",V is not None and abs(V-52)<1e-4,f"{len(res)} objet(s), volume {V}")
# A (tout) à l'étape 2 : le second jeu = tout sauf le premier jeu
scene(); o=make(m.DESSIN_OT_bool_difference)
with contextlib.redirect_stdout(io.StringIO()):
    type(o).invoke(o,ctx,ev('NONE','NOTHING',*scr(0,0)))
    send(o,C(-1.5,-1.5)); send(o,'RET'); send(o,'A'); sa=selnames()
rec(SEC,"Touche A à l'étape 2 : tout est sélectionné, A compris",sa==["A","B","Far"],sa)
o.refresh(ctx)
# Échap à l'étape 2 : rien n'est modifié
scene(); o=make(m.DESSIN_OT_bool_difference)
with contextlib.redirect_stdout(io.StringIO()):
    type(o).invoke(o,ctx,ev('NONE','NOTHING',*scr(0,0)))
    send(o,C(-1.5,-1.5)); send(o,'RET'); send(o,C(3.5,3.5)); r=send(o,'ESC')
rec(SEC,"Échap à l'étape 2 : les trois objets sont intacts",sorted(ob.name for ob in bpy.data.objects)==["A","B","Far"],r)
# History = Yes (touche H) : modificateur Boolean, les deux objets restent, le second en fil de fer
m._HISTORY_MEM.clear()
scene(); o=make(m.DESSIN_OT_bool_difference)
with contextlib.redirect_stdout(io.StringIO()):
    type(o).invoke(o,ctx,ev('NONE','NOTHING',*scr(0,0)))
    for e in ('H',C(-1.5,-1.5),'RET',C(3.5,3.5),'RET'): r=send(o,e)
A_,B_=bpy.data.objects.get("A"),bpy.data.objects.get("B")
def evol(ob):
    dg=bpy.context.evaluated_depsgraph_get(); dg.update(); e=ob.evaluated_get(dg); me=e.to_mesh()
    bm=bmesh.new(); bm.from_mesh(me); v=abs(bm.calc_volume()); bm.free(); e.to_mesh_clear(); return v
ok=A_ is not None and B_ is not None and [md.type for md in A_.modifiers]==['BOOLEAN'] and B_.display_type=='WIRE'
rec(SEC,"Difference avec History (H) : A porte un modificateur Boolean, B reste en fil de fer, volume 52",ok and abs(evol(A_)-52)<1e-3 and selnames()==["A"],f"{r} {sorted(ob.name for ob in bpy.data.objects)} {evol(A_) if ok else None}")
scene(); o=make(m.DESSIN_OT_bool_difference)
with contextlib.redirect_stdout(io.StringIO()):
    type(o).invoke(o,ctx,ev('NONE','NOTHING',*scr(0,0)))
rec(SEC,"... History reste sur Yes à la commande suivante ; Boolean Split ne le propose pas",o.history and not make(m.DESSIN_OT_bool_split).HISTORY_OK)
m._HISTORY_MEM.clear()
summary()
