import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
# Liste des calques : « Sort by Color » (à côté de « Sort Alphabetically ») range les calques par couleur
import types
C=bpy.context
res=[]
def chk(name,ok,info=""):
    res.append(bool(ok)); print(("OK  " if ok else "BAD ")+name, info)
L_ = m.layer_click.__globals__ if hasattr(m, "layer_click") else m.DESSIN_OT_layer_click.invoke.__globals__
root=C.scene.collection
# ordre manuel volontairement mélangé ; None = calque sans couleur
LAYERS=[("Murs bleus",(0.30,0.55,0.95)),("Sans couleur A",None),("Gris moyen",(0.5,0.5,0.5)),("Rouge",(0.90,0.30,0.30)),
        ("Vert",(0.45,0.78,0.35)),("Rouge rosé",(0.95,0.25,0.32)),("Blanc",(0.95,0.95,0.95)),("Jaune",(0.95,0.85,0.25)),
        ("Rouge foncé",(0.50,0.10,0.10)),("Bleu B",(0.30,0.55,0.95)),("Sans couleur B",None),("Violet",(0.65,0.45,0.90)),
        ("Orange",(0.95,0.60,0.20))]
for n,c in LAYERS:
    col=bpy.data.collections.new(n); root.children.link(col)
    if c is not None: col.dessin_layer.color=c
    col.dessin_layer.use_color = c is not None
par=bpy.data.collections["Vert"]
for n,c in (("Sous bleu",(0.2,0.3,0.9)),("Sous rouge",(0.9,0.2,0.2)),("Sous sans",None)):
    col=bpy.data.collections.new(n); par.children.link(col)
    if c is not None: col.dessin_layer.color=c
    col.dessin_layer.use_color = c is not None
st=C.scene.dessin
def top(): return [lc.name for d,lc in L_["layer_rows"](C) if d==1]
def under(name):
    rows=L_["layer_rows"](C); i=[lc.name for d,lc in rows].index(name); d0=rows[i][0]; out=[]
    for d,lc in rows[i+1:]:
        if d<=d0: break
        if d==d0+1: out.append(lc.name)
    return out
manual=[n for n,_c in LAYERS]
chk("par défaut : votre ordre", top()==manual, top())

st.layer_sort_color=True
t=top()
expect=["Rouge","Rouge rosé","Rouge foncé","Orange","Jaune","Vert","Murs bleus","Bleu B","Violet","Blanc","Gris moyen","Sans couleur A","Sans couleur B"]
chk("Sort by Color : tour de la roue des couleurs (rouge → violet), puis les gris, puis les calques sans couleur", t==expect, t)
chk("... le rouge rosé (teinte proche de 360°) reste avec les rouges", t.index("Rouge rosé")<t.index("Orange"), t)
chk("... même teinte : du plus clair au plus foncé", t.index("Rouge")<t.index("Rouge foncé"), t)
chk("... même couleur : votre ordre est gardé (Murs bleus avant Bleu B)", t.index("Murs bleus")+1==t.index("Bleu B"), t)
chk("... gris du plus clair au plus foncé", t.index("Blanc")<t.index("Gris moyen"), t)
chk("... les sous-calques sont rangés aussi, dans leur calque parent", under("Vert")==["Sous rouge","Sous bleu","Sous sans"], under("Vert"))
bpy.data.collections["Jaune"].dessin_layer.color=(0.2,0.3,0.95)
t=top()
chk("changer la couleur d'un calque le déplace dans la liste", t.index("Jaune")>t.index("Vert") and t.index("Jaune")<t.index("Violet"), t)
bpy.data.collections["Jaune"].dessin_layer.color=(0.95,0.85,0.25)

st.layer_sort_alpha=True
chk("cocher Sort Alphabetically décoche Sort by Color (un seul rangement)", st.layer_sort_alpha and not st.layer_sort_color)
chk("... ordre alphabétique", top()==sorted(manual,key=str.lower), top())
st.layer_sort_color=True
chk("et l'inverse : Sort by Color décoche Sort Alphabetically", st.layer_sort_color and not st.layer_sort_alpha)
st.layer_sort_color=False
chk("tout décoché : retour exact à votre ordre", top()==manual, top())

# l'option est dans le menu « Layer List » de la liste, juste sous Sort Alphabetically
props=[]
class Lay:
    def __getattr__(self,n):
        if n=="prop":
            return lambda owner,p,*a,**k: (props.append(p), Lay())[1]
        return lambda *a,**k: Lay()
    def __setattr__(self,n,v): pass
m.DESSIN_PT_layers_filter.draw(types.SimpleNamespace(layout=Lay()), C)
chk("menu Layer List : Sort by Color juste sous Sort Alphabetically", "layer_sort_color" in props and props.index("layer_sort_color")==props.index("layer_sort_alpha")+1, props[:12])
print("RESULTAT",sum(res),"/",len(res))
