import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
# Onglets de vues « vivants » comme les titres de fenêtres de Rhino : Perspective -> « Axonometric » en vue 3D orthographique,
# Front -> « Back » en vue arrière (Back n'a pas d'onglet), Top -> « Bottom », Right -> « Left »
from mathutils import Euler
res=[]
def chk(n,ok,info=""): res.append(bool(ok)); print(("OK  " if ok else "BAD ")+n, info)
sc=bpy.context.scene
m._VIEW_OF_AREA.clear()
def setv(axis, persp):
    rv3d.view_perspective='PERSP' if persp else 'ORTHO'
    rv3d.view_rotation=m._axis_quat(axis) if axis != 'FREE' else Euler((1.0,0.0,0.4)).to_quaternion()
def tabs():
    return [(v,t,on) for v,t,on in m.view_tabs(ctx, sc, m.current_view_name(ctx))]
setv(None, True)
chk("vue 3D en perspective : onglet « Perspective » allumé", ('Perspective','Perspective',True) in tabs(), tabs())
setv('FREE', False)
chk("vue 3D orthographique : l'onglet devient « Axonometric » et reste allumé", ('Perspective','Axonometric',True) in tabs(), tabs())
setv('FRONT', False)
chk("vue Front : Front allumé, Perspective inchangé", ('Front','Front',True) in tabs() and ('Perspective','Perspective',False) in tabs(), tabs())
setv('BACK', False)
t=tabs()
chk("vue Back : l'onglet Front devient « Back », allumé", ('Back','Back',True) in t and not any(v=='Front' for v,_t,_o in t), t)
setv('BOTTOM', False)
chk("vue Bottom : l'onglet Top devient « Bottom »", ('Bottom','Bottom',True) in tabs(), tabs())
setv('LEFT', False)
chk("vue Left : l'onglet Right devient « Left »", ('Left','Left',True) in tabs(), tabs())
setv('RIGHT', False)
chk("retour en Right : les onglets reprennent leurs noms", [v for v,_t,_o in tabs()]==['Top','Front','Perspective','Right'], tabs())
# vue de côté en perspective (Blender : clic sur l'axe X du gizmo, Auto Perspective éteint -> « Right Perspective »)
setv('RIGHT', True)
chk("« Right Perspective » : c'est l'onglet Right qui s'allume, pas Perspective", ('Right','Right',True) in tabs() and ('Perspective','Perspective',False) in tabs(), tabs())
setv('BACK', True)
chk("« Back Perspective » : l'onglet Front devient « Back »", ('Back','Back',True) in tabs(), tabs())
# comme Rhino : l'onglet dans lequel on était prend le nom de la vue choisie (Perspective -> Bottom, Top -> Left)
m._VIEW_OF_AREA[area.as_pointer()]='Perspective'
setv('BOTTOM', False)
t=tabs()
chk("depuis l'onglet Perspective, vue Bottom : c'est Perspective qui devient « Bottom »", t[2]==('Bottom','Bottom',True) and t[0]==('Top','Top',False), t)
m._VIEW_OF_AREA[area.as_pointer()]='Top'
setv('LEFT', False)
t=tabs()
chk("depuis l'onglet Top, vue Left : c'est Top qui devient « Left »", t[0]==('Left','Left',True) and t[3]==('Right','Right',False), t)
m._VIEW_OF_AREA.clear()
# la vue 3D quittée en orthographique garde son état : son onglet s'appelle « Axonometric » et y ramène
setv('FREE', False)
chk("la vue 3D orthographique est bien « dans » la vue Perspective (elle y sera enregistrée en la quittant)", m.current_view_name(ctx)=='Perspective')
_e=sc.dessin_views.add(); _e.name='Perspective'; _e.base=True; _e.rot=tuple(rv3d.view_rotation); _e.persp=False; _e.full=True
setv('TOP', False)
chk("en vue Top, l'onglet de la vue 3D quittée en ortho s'appelle « Axonometric »", ('Perspective','Axonometric',False) in tabs(), tabs())
e=m.find_view(sc,'Perspective')
chk("et la vue enregistrée est orthographique", e is not None and not e.persp)
# un nom choisi par l'utilisateur est gardé
m.set_base_label(sc,'Perspective','Maquette')
chk("onglet renommé : le nom de l'utilisateur reste", ('Perspective','Maquette',False) in tabs(), tabs())
m.set_base_label(sc,'Perspective','')
sc.dessin_views.remove(list(sc.dessin_views).index(e))
print("RESULTAT",sum(res),"/",len(res))
