import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
exec(open(_os.path.join(_HERE,'prec_lib.py')).read())
# Workflow Rhino : le clic droit glissé tourne la vue (en perspective) même dans une vue Dessus / Face ;
# les réglages de navigation de Blender ne sont plus écrasés à l'activation.
import sys, types
SEC="Navigation"
nav=sys.modules["wanderer_cad.navigation"]
P=dict(m.PREF_DEFAULTS)
calls=[]
real_bpy=nav.bpy
fake_ops=types.SimpleNamespace(view3d=types.SimpleNamespace(rotate=lambda *a: calls.append("rotate") or {'FINISHED'},
                                                            move=lambda *a: calls.append("move") or {'FINISHED'}))
nav.bpy=types.SimpleNamespace(ops=fake_ops, context=real_bpy.context, app=real_bpy.app, types=real_bpy.types)
real_pref=nav.pref
nav.pref=lambda n: P[n]
def go(button, side=True):
    calls.clear()
    rv=NS(view_perspective='ORTHO' if side else 'PERSP', is_orthographic_side_view=side)
    ctx=NS(area=NS(type='VIEW_3D'), region_data=rv)
    ok=nav.start_navigation(ctx, button)
    return ok, list(calls), rv.view_perspective
try:
    P.update(mouse_orbit='RIGHT', mouse_menu='RIGHT_CLICK', view_pan=True)
    r=go('RIGHTMOUSE')
    rec(SEC,"Rhino, vue Dessus : clic droit glissé = pan, comme dans les vues parallèles de Rhino",r[1]==["move"],r)
    r=go('RIGHTMOUSE', side=False)
    rec(SEC,"Rhino, vue perspective : clic droit glissé = orbite",r==(True,["rotate"],'PERSP'),r)
    P.update(mouse_orbit='DEFAULT', mouse_menu='DEFAULT')
    r=go('RIGHTMOUSE')
    rec(SEC,"sans le style Rhino, rien ne change : pan dans les vues Dessus / Face",r[1]==["move"],r)
finally:
    nav.bpy=real_bpy; nav.pref=real_pref
inp=bpy.context.preferences.inputs
inp.use_mouse_depth_navigate=True; inp.use_zoom_to_mouse=True; inp.use_rotate_around_active=False; inp.invert_zoom_wheel=True
nav.apply_nav_inputs()
rec(SEC,"à l'activation, Auto Depth, zoom vers la souris, orbite autour de la sélection et sens du zoom de Blender restent tels quels",
    inp.use_mouse_depth_navigate and inp.use_zoom_to_mouse and not inp.use_rotate_around_active and inp.invert_zoom_wheel)
Q=types.SimpleNamespace(nav_zoom_cursor=False, nav_auto_depth=False, nav_invert_zoom=False)
nav.nav_inputs_sync(Q)
rec(SEC,"les cases de Wanderer reprennent les réglages de Blender",Q.nav_zoom_cursor and Q.nav_auto_depth and Q.nav_invert_zoom,vars(Q))
nav.nav_input_set("nav_auto_depth", False)
rec(SEC,"décocher la case Wanderer coupe Auto Depth, sans toucher aux autres réglages",
    not inp.use_mouse_depth_navigate and inp.use_zoom_to_mouse and inp.invert_zoom_wheel)
summary()
