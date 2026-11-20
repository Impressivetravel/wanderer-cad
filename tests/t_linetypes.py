# Types de ligne par calque ou par objet (comme AutoCAD) : tirets dans les vues, sur le papier des mises en page, en DXF
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
src=open(_os.path.join(_HERE,'t_pushpull.py')).read()
exec(src[src.index("\n")+1:src.index("# ---------------- 1. PushPull")])
import tempfile
st=C.scene.dessin; st.ortho=False; st.polar=False
def poly(name,pts,closed=False): return m.build_polyline(C,name,[Vector(p) for p in pts],closed)
def move(o, col):
    for c in list(o.users_collection): c.objects.unlink(o)
    col.objects.link(o)
def dashes(o):
    """Nombre de tirets et longueur du plus long, d'après la forme évaluée (ce qu'on voit)."""
    dg=C.evaluated_depsgraph_get(); dg.update()
    ev_=o.evaluated_get(dg); me=ev_.to_mesh()
    V=[v.co.copy() for v in me.vertices]; Ed=[tuple(e.vertices) for e in me.edges]
    ev_.to_mesh_clear()
    par=list(range(len(V)))
    def f(x):
        while par[x]!=x: par[x]=par[par[x]]; x=par[x]
        return x
    for a,b in Ed: par[f(a)]=f(b)
    comp={}
    for a,b in Ed: comp[f(a)]=comp.get(f(a),0.0)+(V[a]-V[b]).length
    return len(comp), (max(comp.values()) if comp else 0.0)
clear()
LA=bpy.data.collections.new("Cachés"); C.scene.collection.children.link(LA)
L=poly("Meuble haut",[(0,0,0),(10,0,0)]); move(L,LA); C.view_layer.update()
chk("calque continu : un seul trait", dashes(L)[0]==1 and not m.has_lt(L))
LA.dessin_layer.linetype='DASHED'
n,mx=dashes(L)
chk("calque en tirets (Dashed) : la ligne de 10 m se voit en tirets de 30 cm (6 mm au 1:50)", n>=20 and abs(mx-0.3)<0.02 and m.has_lt(L), (n, round(mx,3)))
g=m.wire_graph(L, C.evaluated_depsgraph_get())
chk("... le dessin n'est pas touché : Trim, Offset, Boundary lisent toujours la ligne entière", g is not None and len(g[1])==1 and abs((g[0][0]-g[0][1]).length-10)<1e-9, g and len(g[1]))
st.linetype_scale=100.0
n2,mx2=dashes(L)
chk("échelle des types de ligne 1:100 : tirets de 60 cm", abs(mx2-0.6)<0.03, round(mx2,3))
st.linetype_scale=50.0
# objet : son propre type
for q in bpy.data.objects: q.select_set(q==L)
C.view_layer.objects.active=L
op=make(m.DESSIN_OT_object_linetype); op.linetype='CENTER'; type(op).execute(op,C)
md=[x for x in L.modifiers if m.is_lt_mod(x)]
chk("type propre à l'objet (Center) : il passe avant celui du calque", L.get("wd_lt")=="CENTER" and md and md[0].node_group.name.endswith("Center"))
op.linetype='BYLAYER'; type(op).execute(op,C)
chk("By Layer : il suit de nouveau son calque", L.get("wd_lt") is None and m.has_lt(L) and [x for x in L.modifiers if m.is_lt_mod(x)][0].node_group.name.endswith("Dashed"))
LA.dessin_layer.linetype='CONTINUOUS'
chk("calque remis en continu : plus de modificateur", not m.has_lt(L) and len(L.modifiers)==0)
LA.dessin_layer.linetype='HIDDEN'
# nouveaux objets, changement de calque
LB=bpy.data.collections.new("Plan"); C.scene.collection.children.link(LB)
N=poly("Nouveau",[(0,2,0),(5,2,0)]); move(N,LA); C.view_layer.update()
G=m.layer_sync_new_objects.__globals__
G['layer_sync_new_objects']()
chk("objet dessiné sur un calque à tirets : il les prend", m.has_lt(N))
for q in bpy.data.objects: q.select_set(q==N)
op=make(m.DESSIN_OT_layer_move_selection); op.layer="Plan"; type(op).execute(op,C)
chk("Change Object Layer vers un calque continu : plus de tirets", not m.has_lt(N))
# pas de type de ligne sur les solides, cotes, hachures, plans de coupe
bx=box(); move(bx,LA); C.view_layer.update()
chk("un solide (faces) ne prend pas de type de ligne", not m.lt_eligible(bx) and m.lt_apply(bx)==False and not m.has_lt(bx))
# sélection : on touche le trait entre deux tirets
LA.dessin_layer.linetype='DASHED'; C.view_layer.update()
hit=None
bpy.data.objects.remove(bx); C.view_layer.update()
for x in [6.0+0.02*i for i in range(45)]:
    h=m.pick_object_at(ctx, area, region, *scr(x,0))
    if h is None or h[0]!=L: hit=x; break
chk("clic sur la ligne entre deux tirets : elle est quand même prise", hit is None, hit)
# accroches : extrémités et milieu de la ligne entière
sd=m.collect_snap_points(ctx)
pts=[tuple(round(c,6) for c in p) for p in sd[0]]
chk("accroches : extrémités et milieu de la ligne entière (pas des tirets)", (5.0,0.0,0.0) in pts and (10.0,0.0,0.0) in pts and (0.3,0.0,0.0) not in pts)
# mises en page : trait entier + type de ligne dans l'étiquette
items=m.collect_model(C.scene)
it=[i for i in items if i.name=="Meuble haut"]
chk("mise en page : la ligne est lue entière (2 sommets), avec son type de ligne", len(it)==1 and len(it[0].V)==2 and it[0].tag[2]=="DASHED", it and (len(it[0].V), it[0].tag))
D=m.dash_pattern_paths([(np.array([(0.0,0.0),(30.0,0.0)]),False)], m.LT_PATTERNS["DASHED"] if hasattr(m,"LT_PATTERNS") else m.PATTERN["DASHED"])
ls=[float(np.linalg.norm(P[-1]-P[0])) for P,_c in D]
chk("sur le papier : tirets de 6 mm et espaces de 3 mm (30 mm : 4 tirets)", len(D)==4 and all(abs(x-6.0)<1e-9 for x in ls[:3]), ls)
# DXF du modèle : LTYPE, calque, objet
ents, layers, stats = m.dxf_collect(C)
fd, path = tempfile.mkstemp(suffix=".dxf"); _os.close(fd)
m.write_model_dxf(path, ents, layers, 1000.0, 4, linetypes=stats.get("linetypes"), lt_unit=stats.get("lt_scale"))
txt=open(path).read(); _os.remove(path)
chk("DXF : le type de ligne DASHED est défini (tiret 300 mm, espace -150 mm au 1:50) et donné au calque",
    "LTYPE\n2\nDASHED" in txt and "49\n300" in txt and "49\n-150" in txt and "2\nCACHES\n70\n0\n62\n7\n6\nDASHED" in txt, [l for l in txt.split("\n") if "DASHED" in l][:3])
for q in bpy.data.objects: q.select_set(q==L)
op=make(m.DESSIN_OT_object_linetype); op.linetype='CENTER'; type(op).execute(op,C)
ents, layers, stats = m.dxf_collect(C)
fd, path = tempfile.mkstemp(suffix=".dxf"); _os.close(fd)
m.write_model_dxf(path, ents, layers, 1000.0, 4, linetypes=stats.get("linetypes"), lt_unit=stats.get("lt_scale"))
txt=open(path).read(); _os.remove(path)
chk("DXF : type propre à l'objet sur l'entité (6 CENTER)", "LTYPE\n2\nCENTER" in txt and "\n6\nCENTER\n" in txt)
# panneau
props=[]
class Lay:
    def __getattr__(self,n):
        if n=="prop": return lambda owner,p,*a,**k: (props.append(p), Lay())[1]
        if n=="operator_menu_enum": return lambda op,p,*a,**k: (props.append(op+":"+p), Lay())[1]
        return lambda *a,**k: Lay()
    def __setattr__(self,n,v): pass
m.DESSIN_PT_layers_print.draw(NS(layout=Lay()), C)
chk("Print Settings : un type de ligne par calque, celui de la sélection, l'échelle", "linetype" in props and "dessin.object_linetype:linetype" in props and "linetype_scale" in props, props)
print("RESULTAT",sum(res),"/",len(res))
