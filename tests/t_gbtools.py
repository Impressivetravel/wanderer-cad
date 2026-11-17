import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
# Le Gumball remplace le gizmo des outils Move / Rotate / Scale / Transform de Blender (retour Natnael5-5)
res=[]
def chk(n,ok,info=""): res.append(bool(ok)); print(("OK  " if ok else "BAD ")+n, info)
class Sp(NS):
    def as_pointer(self): return id(self)
class Ar(NS):
    def tag_redraw(self): pass
class Tools:
    def __init__(self): self.id="builtin.select_box"
    def from_space_view3d_mode(self, mode, create=False): return NS(idname=self.id) if self.id else None
tools=Tools(); sp=Sp(show_gizmo_tool=True); st=NS(gumball=True)
win=NS(view_layer=NS(objects=NS(active=NS(mode='OBJECT',type='MESH'))), workspace=NS(tools=tools),
       scene=NS(dessin=st), screen=NS(areas=[Ar(type='VIEW_3D',spaces=NS(active=sp))]))
sync=lambda: m.tool_gizmo_sync([win])
sync(); chk("outil Select : le gizmo d'outil de Blender n'est pas touché", sp.show_gizmo_tool is True)
for t in ("builtin.move","builtin.rotate","builtin.scale","builtin.transform"):
    tools.id=t; sync(); ok=sp.show_gizmo_tool is False
    tools.id="builtin.select_box"; sync(); ok=ok and sp.show_gizmo_tool is True
    chk(f"{t} : son gizmo est masqué (le Gumball le remplace), puis rendu en revenant à Select", ok)
tools.id="builtin.move"; sync(); st.gumball=False; sync()
chk("Gumball éteint pendant Move : le gizmo de Blender revient", sp.show_gizmo_tool is True)
st.gumball=True; sp.show_gizmo_tool=False; m._TOOL_GIZMO["hidden"].clear(); tools.id="builtin.select_box"; sync()
chk("gizmo d'outil coupé par l'utilisateur lui-même : Wanderer ne le rallume pas", sp.show_gizmo_tool is False)
sp.show_gizmo_tool=True; tools.id="builtin.bevel"; sync()
chk("autre outil (Bevel) : son gizmo reste", sp.show_gizmo_tool is True)
win.view_layer.objects.active=NS(mode='EDIT',type='MESH'); tools.id="builtin.rotate"; sync()
chk("mode Édition, outil Rotate : gizmo masqué aussi", sp.show_gizmo_tool is False)
chk("le Gumball s'affiche avec ces outils", all(t in m.GUMBALL_TRANSFORM_TOOLS for t in ("builtin.move","builtin.rotate","builtin.scale","builtin.transform")))
m.tool_gizmo_restore()
print("RESULTAT",sum(res),"/",len(res))
