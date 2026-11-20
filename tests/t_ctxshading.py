# Clic droit dans le vide (rien de sélectionné) : « Viewport Shading » en haut du menu (filaire, solide, matériau, rendu, X-Ray)
import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
import types
BC=bpy.context
res=[]
def chk(n,ok,info=""): res.append(bool(ok)); print(("OK  " if ok else "BAD ")+n, info)
class Lay:
    def __init__(s): s.order=[]
    def operator(s, idname, **k): s.order.append(("op",idname)); return NS()
    def menu(s, idname, **k): s.order.append(("menu",idname))
    def prop_enum(s, owner, prop, value, **k): s.order.append(("enum",prop,value))
    def prop(s, owner, prop, **k): s.order.append(("prop",prop,k.get("text")))
    def popover(s, panel, **k): s.order.append(("popover",panel))
    def separator(s): pass
me=bpy.data.meshes.new("c"); A=bpy.data.objects.new("A",me); BC.collection.objects.link(A)
view=NS(type='VIEW_3D', shading=NS(type='SOLID', show_xray=False, show_xray_wireframe=True))
ctx_none=NS(mode='OBJECT', selected_objects=[], active_object=A, space_data=view)
ctx_sel=NS(mode='OBJECT', selected_objects=[A], active_object=A, space_data=view)
L=Lay(); ok=m.ctx_viewport_shading_item(L, ctx_none)
chk("rien de sélectionné : « Viewport Shading » ajouté", ok and L.order==[("menu","DESSIN_MT_ctx_viewport_shading")], L.order)
L=Lay(); ok=m.ctx_viewport_shading_item(L, ctx_sel)
chk("avec une sélection : pas de Viewport Shading (le menu de l'objet reste comme avant)", not ok and not L.order, L.order)
L=Lay(); ok=m.ctx_viewport_shading_item(L, NS(mode='OBJECT', selected_objects=[], active_object=None, space_data=None))
chk("hors d'une vue 3D : rien", not ok and not L.order)
L=Lay(); m.DESSIN_MT_ctx_viewport_shading.draw(NS(layout=L), NS(space_data=view))
chk("le sous-menu : Wireframe, Solid, Material Preview, Rendered", [x[2] for x in L.order if x[0]=="enum"]==['WIREFRAME','SOLID','MATERIAL','RENDERED'], L.order)
chk("... puis X-Ray (celui du mode Solid) et les options d'affichage", ("prop","show_xray","X-Ray") in L.order and ("popover","VIEW3D_PT_shading") in L.order, L.order)
view.shading.type='WIREFRAME'; L=Lay(); m.DESSIN_MT_ctx_viewport_shading.draw(NS(layout=L), NS(space_data=view))
chk("... en filaire : le X-Ray du filaire", ("prop","show_xray_wireframe","X-Ray") in L.order, L.order)
chk("le sous-menu est enregistré", hasattr(bpy.types, "DESSIN_MT_ctx_viewport_shading"))
L=Lay(); chk("rien de sélectionné : plus de Shade Smooth / Flat (ils n'agiraient sur rien)", not m.ctx_shade_items(L, ctx_none) and not L.order, L.order)
L=Lay(); chk("avec une sélection : Shade Smooth / Auto Smooth / Flat comme avant", m.ctx_shade_items(L, ctx_sel) and len(L.order)==3, L.order)
print("RESULTAT",sum(res),"/",len(res))
