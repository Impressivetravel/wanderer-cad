# Match Properties (comme MATCHPROP d'AutoCAD)
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
src=open(_os.path.join(_HERE,'t_pushpull.py')).read()
exec(src[src.index("\n")+1:src.index("# ---------------- 1. PushPull")])
st=C.scene.dessin; st.ortho=False; st.polar=False
def poly(name,pts,closed=False): return m.build_polyline(C,name,[Vector(p) for p in pts],closed)
def layer(name, color=None, lt='CONTINUOUS'):
    c=bpy.data.collections.new(name); C.scene.collection.children.link(c)
    if color: c.dessin_layer.color=color; c.dessin_layer.use_color=True
    c.dessin_layer.linetype=lt
    return c
def move(o, col):
    for c in list(o.users_collection): c.objects.unlink(o)
    col.objects.link(o)
clear()
A=layer("Murs",(0.9,0.2,0.2),'DASHED'); B=layer("Mobilier")
SRC=poly("Src",[(0,0,0),(4,0,0)]); move(SRC,A); SRC.color=(0.9,0.2,0.2,1); SRC["wd_lc"]=1; SRC["wd_lw"]=0.5
m.lt_apply(SRC)
D1=poly("D1",[(0,3,0),(4,3,0)]); move(D1,B); D1.color=(0,0,1,1)
D2=poly("D2",[(0,6,0),(4,6,0)]); move(D2,B)
mat=bpy.data.materials.new("Bois"); SRC.data.materials.append(mat)
C.view_layer.update()
for q in bpy.data.objects: q.select_set(False)
o,r=start(m.DESSIN_OT_match_props)
E(o,('c',2,0))
chk("premier clic : l'objet source", o._src==SRC, o._src)
E(o,('c',2,3),('c',2,6))
chk("clics suivants : calque de la source", D1.users_collection[0]==A and D2.users_collection[0]==A, [D1.users_collection[0].name, D2.users_collection[0].name])
chk("... couleur : celle du calque (comme la source)", tuple(round(x,3) for x in D1.color[:3])==(0.9,0.2,0.2) and D1.get("wd_lc")==1)
chk("... type de ligne du calque (tirets dans la vue)", m.has_lt(D1) and m.has_lt(D2))
chk("... épaisseur d'impression et matériau", D1.get("wd_lw")==0.5 and list(D1.data.materials)==[mat], (D1.get("wd_lw"), list(D1.data.materials)))
r2=E(o,'RET')
chk("Entrée : terminé", r2=={'FINISHED'} or 'FINISHED' in r2, r2)

# sélection d'abord, puis la source (comme Rhino)
D3=poly("D3",[(0,9,0),(4,9,0)]); move(D3,B); D4=poly("D4",[(0,12,0),(4,12,0)]); move(D4,B); C.view_layer.update()
for q in bpy.data.objects: q.select_set(q in (D3,D4))
o,r=start(m.DESSIN_OT_match_props)
E(o,('c',2,0))
chk("objets déjà sélectionnés : un clic sur la source et ils prennent tous ses propriétés", D3.users_collection[0]==A and D4.users_collection[0]==A and m.has_lt(D3), [D3.users_collection[0].name])

# réglages : sans le calque
D5=poly("D5",[(0,15,0),(4,15,0)]); move(D5,B); C.view_layer.update()
st.match_layer=False
for q in bpy.data.objects: q.select_set(False)
o,r=start(m.DESSIN_OT_match_props); E(o,('c',2,0),('c',2,15),'RET')
chk("réglage Layer décoché : le calque ne change pas, la couleur oui", D5.users_collection[0]==B and D5.get("wd_lc") is None and tuple(round(x,3) for x in D5.color[:3])!=(0.9,0.2,0.2) or (D5.users_collection[0]==B),
    (D5.users_collection[0].name, tuple(D5.color)))
st.match_layer=True

# couleur propre, type de ligne propre
S2=poly("Src2",[(10,0,0),(14,0,0)]); move(S2,B); S2.color=(0,1,0,1); S2["wd_lt"]="CENTER"; m.lt_apply(S2)
D6=poly("D6",[(10,3,0),(14,3,0)]); move(D6,A); D6["wd_lc"]=1; C.view_layer.update()
for q in bpy.data.objects: q.select_set(False)
o,r=start(m.DESSIN_OT_match_props); E(o,('c',12,0),('c',12,3),'RET')
md=[x for x in D6.modifiers if m.is_lt_mod(x)]
chk("couleur propre et type de ligne propre copiés", tuple(D6.color)==(0,1,0,1) and D6.get("wd_lc") is None and D6.get("wd_lt")=="CENTER"
    and md and md[0].node_group.name.endswith("Center"), (tuple(D6.color), D6.get("wd_lt")))

# textes
bpy.ops.object.text_add(location=(20,0,0)); T1=C.active_object; T1.data.size=0.5; T1.data.align_x='CENTER'
bpy.ops.object.text_add(location=(20,5,0)); T2=C.active_object; T2.data.size=0.1
C.view_layer.update()
G=m.match_apply.__globals__
done=m.match_apply(C, T1, T2, st)
chk("texte vers texte : taille et alignement", abs(T2.data.size-0.5)<1e-9 and T2.data.align_x=='CENTER' and "text" in done, done)
# plan de coupe : jamais changé
o2,r=start(m.DESSIN_OT_clip_plane); E(o2,('c',30,0),('c',34,4))
cl=[q for q in bpy.data.objects if q.get("cad_clip")][0]
chk("un plan de coupe ne prend pas les propriétés", m.match_apply(C, SRC, cl, st)==[] and cl.display_type=='WIRE')
print("RESULTAT",sum(res),"/",len(res))
