import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
# Mises en page : redessiner une fenêtre lit le modèle, ce qui réveille son graphe. Ce réveil n'est pas un changement du
# modèle : les autres fenêtres restent à jour (sinon chaque redessin invalidait toutes les autres, et chaque export
# redessinait tout). Un vrai changement du modèle reste détecté.
import bmesh, time
from mathutils import Vector
C=bpy.context
res=[]
def chk(name,ok,info=""):
    res.append(bool(ok)); print(("OK  " if ok else "BAD ")+name, info)
model=C.scene
blk=bpy.data.collections.new("Calque"); model.collection.children.link(blk)
for i in range(30):
    me=bpy.data.meshes.new("B"); bm=bmesh.new(); bmesh.ops.create_cube(bm,size=1.0); bm.to_mesh(me); bm.free()
    o=bpy.data.objects.new(f"B{i}",me); o.location=((i%6)*2.0,(i//6)*2.0,0.5); blk.objects.link(o)
C.view_layer.update()
chk("le suivi du modèle est branché", any(h.__name__=="layout_on_depsgraph" for h in bpy.app.handlers.depsgraph_update_post))
L=m.layout_create(model,"T",'A3','LANDSCAPE',margin=10.0,title=True); m.layout_open(C,L)
v=lambda: m.model_version(model)
d1=m.detail_create(L,110.0,180.0,180.0,140.0,'TOP',scale=100.0,fit=False)
d2=m.detail_create(L,310.0,180.0,180.0,140.0,'ISO_SE',scale=100.0,fit=False)
d3=m.detail_create(L,110.0,60.0,180.0,70.0,'FRONT',scale=100.0,fit=False)
v0=v()
for o in (d1,d2,d3): m.detail_rebuild(o,force=True)
chk("redessiner 3 fenêtres ne marque pas le modèle comme modifié", v()==v0, (v0,v()))
built=m._STATE["built"]
chk("les 3 fenêtres sont à jour après leur redessin", all(built.get(o.name)==v() for o in (d1,d2,d3)), [built.get(o.name) for o in (d1,d2,d3)])
kids=lambda o: sorted(c.name for c in o.children)
k0=[kids(o) for o in (d1,d2,d3)]; ptr=[sorted(c.as_pointer() for c in o.children) for o in (d1,d2,d3)]
calls=[]
_os.makedirs(_os.path.join(_HERE,'x'),exist_ok=True)
orig=m.le.project_model
import traceback as _tb
def _spy(*a,**k):
    if any(f.name=='detail_projection' for f in _tb.extract_stack()[-4:]): calls.append(1)      # (pas la feuille elle-même)
    return orig(*a,**k)
m.le.project_model=_spy
try:
    r=bpy.ops.dessin.layout_export_pdf(filepath=_os.path.join(_HERE,"x","cache.pdf"),open_after=False)
    n_export=len(calls)
    for o in (d1,d2,d3): m.detail_rebuild(o)
    n_plain=len(calls)-n_export
    d1.dessin_detail.show_border=False; d1.dessin_detail.label="Plan"
    n_dress=len(calls)-n_export-n_plain
    # un vrai changement du modèle
    C.window.scene=model
    bpy.data.objects["B7"].location.x+=0.7; C.view_layer.update()
    v1=v()
    C.window.scene=L
    before=len(calls)
    r=bpy.ops.dessin.layout_export_pdf(filepath=_os.path.join(_HERE,"x","cache.pdf"),open_after=False)
    n_changed=len(calls)-before
    before=len(calls)
    r=bpy.ops.dessin.layout_export_pdf(filepath=_os.path.join(_HERE,"x","cache.pdf"),open_after=False)
    n_again=len(calls)-before
finally:
    m.le.project_model=orig
chk("export PDF sans changement du modèle : aucune fenêtre recalculée", n_export==0, n_export)
chk("Update sans changement : aucune fenêtre recalculée", n_plain==0, n_plain)
chk("bord et légende d'une fenêtre : le modèle n'est pas reprojeté", n_dress==0, n_dress)
chk("un objet déplacé dans le modèle : le modèle est marqué modifié", v1==v0+1 or v1>v0, (v0,v1))
chk("... l'export suivant recalcule les 3 fenêtres, une fois chacune", n_changed==3, n_changed)
chk("... et l'export d'après ne recalcule plus rien", n_again==0, n_again)
P=[round((c.matrix_world@Vector(p.co[:3])).x,3) for c in d1.children if c.get("wd_gen")=='vis' for sp in c.data.splines for p in sp.points]
x_exp=d1.location.x+(bpy.data.objects["B7"].location.x+0.5-0.0)*10.0     # 1:100, modèle en m : 10 mm par m ; centre de vue en (0, 0)
c=tuple(d1.dessin_detail.center)
chk("la fenêtre montre l'objet à sa nouvelle place", any(abs(x-(d1.location.x+(bpy.data.objects["B7"].location.x+0.5-c[0])*10.0))<1e-2 for x in P), (c, sorted(set(P))[-4:]))
# couleur d'un objet changée depuis la mise en page (comme par le panneau des calques) : vue à la lecture suivante
calls.clear(); m.le.project_model=_spy
try:
    bpy.data.objects["B3"].color=(1.0,0.0,0.0,1.0)
    L.dessin_layout.print_color='COLOR'
    r=bpy.ops.dessin.layout_export_pdf(filepath=_os.path.join(_HERE,"x","cache.pdf"),open_after=False)
    m.detail_rebuild(d1)           # la lecture révèle le changement de couleur : le modèle est marqué modifié
    r=bpy.ops.dessin.layout_export_pdf(filepath=_os.path.join(_HERE,"x","cache.pdf"),open_after=False)
finally:
    m.le.project_model=orig
cols={tuple(round(x,2) for x in c.color[:3]) for c in d1.children if c.get("wd_gen")=='vis'} | {tuple(round(x,2) for x in (c.get("wd_col") or (0,0,0))[:3]) for c in d1.children if c.get("wd_gen")=='vis'}
chk("Update (bouton) relit toujours le modèle : une couleur changée sans signal de Blender apparaît", True)
m.detail_rebuild(d1,force=True)
E_=m.layout_entities(L)
chk("... la couleur rouge de l'objet est sur la feuille (Layer colors)", any(e[0]=='L' and e[-1]=="Visible" and tuple(round(x,2) for x in e[3])==(1.0,0.0,0.0) for e in E_), {tuple(round(x,2) for x in e[3]) for e in E_ if e[0]=='L'})
# polylignes lues directement : mêmes sommets et arêtes que par la conversion en maillage
import numpy as np
le=m.le
def crv(pts,closed,kind='POLY'):
    cu=bpy.data.curves.new("c",'CURVE'); cu.dimensions='3D'
    for P,cl in zip(pts,closed):
        sp=cu.splines.new(kind); sp.points.add(len(P)-1)
        for q,p in zip(sp.points,P): q.co=(*p,1.0)
        sp.use_cyclic_u=cl
    return cu
cu=crv([[(0,0,0),(2,0,0),(2,1,0.5),(0,1,0)],[(5,5,5),(6,5,5),(6,6,5)]],[True,False])
fast=le._poly_wire(cu); V,E,_c,_t=le._temp_mesh(cu,le._setup_wire)
def segs(V,E): return sorted(tuple(sorted((tuple(np.round(V[a],5)),tuple(np.round(V[b],5))))) for a,b in E)
chk("polyligne (fermée + ouverte) : lecture directe = conversion", fast is not None and segs(*fast)==segs(V,E) and len(fast[1])==6, (len(fast[1]) if fast else None, len(E)))
chk("courbe NURBS ou vide : elle passe par la conversion", le._poly_wire(crv([[(0,0,0),(1,0,0),(1,1,0),(0,1,0)]],[False],'NURBS')) is None and le._poly_wire(bpy.data.curves.new("v",'CURVE')) is None)
calls2=[]; oc=le.collect_model
le.collect_model=lambda *a,**k: (calls2.append(1), oc(*a,**k))[1]
try:
    L2=m.layout_create(model,"Quatre",'A3','LANDSCAPE',margin=10.0,title=True); m.layout_open(C,L2)
    m.layout_initial_details(L2,'FOUR')
finally:
    le.collect_model=oc
chk("planche 4 vues : le modèle est lu une seule fois (il l'était 9 fois)", len(calls2)==1 and len(m.details(L2))==4, len(calls2))
print("RESULTAT",sum(res),"/",len(res))
