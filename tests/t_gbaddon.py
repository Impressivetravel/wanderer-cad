import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
# Gumball invisible quand un add-on laisse tourner un opérateur modal en permanence (retour Natnael5-5, BlenderKit installé)
res=[]
def chk(n,ok,info=""): res.append(bool(ok)); print(("OK  " if ok else "BAD ")+n, info)
class Win(NS): pass
def fm(*ids):
    ctx._o['window']=Win(modal_operators=[NS(bl_idname=i) for i in ids]); r=m.foreign_modal(ctx); ctx._o['window']=None; return r
chk("aucune commande en cours : Gumball affiché", not fm())
chk("barre d'assets BlenderKit (modale permanente) : Gumball affiché", not fm("VIEW3D_OT_blenderkit_asset_bar_widget"))
chk("autres modales d'add-ons sans rapport (minuteries, widgets) : Gumball affiché", not fm("WM_OT_some_addon_timer", "SCREEN_OT_addon_overlay"))
chk("Move de Blender en cours : Gumball masqué", fm("TRANSFORM_OT_translate"))
chk("Knife / Loop Cut / Bevel : Gumball masqué", fm("MESH_OT_knife_tool") and fm("MESH_OT_loopcut") and fm("MESH_OT_bevel"))
chk("une commande de Wanderer en cours : pas une commande étrangère", not fm("DESSIN_OT_gumball"))
chk("BlenderKit + Move en même temps : Gumball masqué pendant le Move", fm("VIEW3D_OT_blenderkit_asset_bar_widget","TRANSFORM_OT_translate"))
print("RESULTAT",sum(res),"/",len(res))
