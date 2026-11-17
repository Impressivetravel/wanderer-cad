import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
# Ctrl + Shift + orbite depuis une vue de face / dessus : la perspective suit Auto Perspective de Blender (retour xxiong-feiyi)
res=[]
def chk(n,ok,info=""): res.append(bool(ok)); print(("OK  " if ok else "BAD ")+n, info)
inp=bpy.context.preferences.inputs
def side():
    rv3d.view_perspective='ORTHO'; rv3d.is_orthographic_side_view=True; rv3d.view_rotation=Matrix().to_quaternion()
for auto in (False, True):
    inp.use_auto_perspective=auto
    side(); op=make(m.DESSIN_OT_trackpad_persp)
    op.invoke(ctx, ev('TRACKPADPAN','ANY',510,500,mouse_prev_x=500,mouse_prev_y=500,ctrl=True,shift=True))
    chk(f"pavé tactile, Auto Perspective {'on' if auto else 'off'}", rv3d.view_perspective==('PERSP' if auto else 'ORTHO'), rv3d.view_perspective)
    side(); op=make(m.DESSIN_OT_orbit_persp)
    try: op.invoke(ctx, ev('MIDDLEMOUSE','PRESS',500,500,ctrl=True,shift=True))
    except Exception as e: print("  (rotate en arrière-plan :", type(e).__name__, ")")
    chk(f"bouton d'orbite, Auto Perspective {'on' if auto else 'off'}", rv3d.view_perspective==('PERSP' if auto else 'ORTHO'), rv3d.view_perspective)
inp.use_auto_perspective=True
print("RESULTAT",sum(res),"/",len(res))
