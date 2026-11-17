import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
# Bouton de l'en-tête de la vue 3D, à gauche de « Selectability & Visibility » : affiche / masque les trois barres du bas
import sys
res=[]
def chk(n,ok,info=""): res.append(bool(ok)); print(("OK  " if ok else "BAD ")+n, info)
hb=sys.modules[m.__name__.rsplit('.',1)[0]+'.header_bars'] if '.' in m.__name__ else None
hb=hb or next(v for k,v in sys.modules.items() if k.endswith('header_bars'))
C=bpy.context; st=C.scene.dessin
chk("réglage présent, barres affichées par défaut", hasattr(st,"show_bars") and st.show_bars is True)
# --- position du bouton dans l'en-tête ---
class L:
    def __init__(s): s.calls=[]
    def popover(s,*a,**k): s.calls.append(("popover",k.get("panel") or a[0]))
    def prop(s,obj,name,**k): s.calls.append(("prop",name,k.get("icon")))
    def row(s,**k): s.calls.append(("row",)); return s
    def separator_spacer(s): s.calls.append(("spacer",))
def fake_header(self, context):         # même ordre que l'en-tête de Blender
    lay=self.layout; lay.row(); lay.separator_spacer()
    lay.popover(panel="VIEW3D_PT_object_type_visibility", text=""); lay.row().popover(panel="VIEW3D_PT_gizmo_display")
real=type("H",(),{})(); real.layout=L()
hb._HB["orig"]=fake_header; hb._HB["fallback"]=False
hb.header_draw(real, C)
c=real.layout.calls; i=c.index(("prop","show_bars","STATUSBAR"))
chk("le bouton est dessiné juste avant Selectability & Visibility, après l'espace", c[i-1]==("spacer",) and c[i+1]==("popover","VIEW3D_PT_object_type_visibility") and c.count(("prop","show_bars","STATUSBAR"))==1, c)
def odd_header(self, context): self.layout.row()
real.layout=L(); hb._HB["orig"]=odd_header; hb.header_draw(real, C)
chk("en-tête sans ce menu (autre version) : le bouton est quand même ajouté, à la fin", ("prop","show_bars","STATUSBAR") in real.layout.calls)
def bad_header(self, context): raise RuntimeError("x")
real.layout=L(); hb._HB["orig"]=bad_header; hb.header_draw(real, C)
chk("en-tête qui échoue : on passe au repli en fin d'en-tête", hb._HB["fallback"] is True)
hb._HB["fallback"]=False; hb._HB["orig"]=None
# --- barres ---
m._CMD["hit"][7]=[(0,0,100,30,"mode","ortho")]; m._VBAR["hit"][7]=[(0,0,100,30,"tab","Front")]
chk("barres affichées : rien n'est masqué", not m.bars_hidden(ctx,7,False) and not m.bars_hidden(ctx,7,False,views=True))
st.show_bars=False
chk("bouton éteint : ligne de commande et modes masqués, plus cliquables", m.bars_hidden(ctx,7,False) and 7 not in m._CMD["hit"])
chk("... onglets de vue masqués, plus cliquables", m.bars_hidden(ctx,7,False,views=True) and 7 not in m._VBAR["hit"])
chk("... la ligne de commande revient le temps de taper une commande", not m.bars_hidden(ctx,7,True))
st.show_bars=True
chk("bouton rallumé : tout revient", not m.bars_hidden(ctx,7,False,views=True))
print("RESULTAT",sum(res),"/",len(res))
