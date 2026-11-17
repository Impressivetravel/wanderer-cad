import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
# « Enable quick secondary click as return key » : seul un clic droit rapide vaut Entrée ; maintenir / glisser = navigation
import time, io, contextlib
res=[]
def chk(n,ok,info=""): res.append(bool(ok)); print(("OK  " if ok else "BAD ")+n, info)
def reset():
    for o in list(bpy.data.objects): bpy.data.objects.remove(o)
    bpy.context.view_layer.update()
def curves(): return [o for o in bpy.data.objects if o.type=='CURVE']
def start2():
    reset()
    o=make(m.DESSIN_OT_polyligne)
    with contextlib.redirect_stdout(io.StringIO()):
        type(o).invoke(o,ctx,ev('NONE','NOTHING',*scr(0,0)))
        for x,y in ((0,0),(6,0),(6,4)):
            sx,sy=scr(x,y)
            for e in (ev('MOUSEMOVE','NOTHING',sx,sy),ev('LEFTMOUSE','PRESS',sx,sy),ev('LEFTMOUSE','RELEASE',sx,sy)): type(o).modal(o,ctx,e)
    return o
def send(o,*evs):
    r=None
    with contextlib.redirect_stdout(io.StringIO()):
        for e in evs:
            if e=="wait": time.sleep(getattr(m,"rclick_quick_s",lambda:0.35)()+0.15); continue
            r=type(o).modal(o,ctx,e)
            if 'FINISHED' in r or 'CANCELLED' in r: return r
    return r
def done(o):
    try: type(o).cleanup(o,ctx)
    except Exception: pass
sx,sy=scr(6,4)
o=start2(); r=send(o,ev('RIGHTMOUSE','PRESS',sx,sy),ev('RIGHTMOUSE','RELEASE',sx,sy))
chk("clic droit rapide = Entrée (polyligne créée)", len(curves())==1, r); done(o)
o=start2(); r=send(o,ev('RIGHTMOUSE','PRESS',sx,sy),"wait",ev('RIGHTMOUSE','RELEASE',sx,sy))
chk("clic droit maintenu sans bouger puis relâché : pas d'Entrée, commande toujours active", not curves() and 'RUNNING_MODAL' in r and len(o.points)==3, r)
r=send(o,ev('RIGHTMOUSE','PRESS',sx,sy),ev('RIGHTMOUSE','RELEASE',sx,sy))
chk("... puis un clic rapide valide normalement", len(curves())==1, r); done(o)
o=start2(); r=send(o,ev('RIGHTMOUSE','PRESS',sx,sy),ev('RIGHTMOUSE','CLICK_DRAG',sx+2,sy+1),ev('RIGHTMOUSE','RELEASE',sx+40,sy+30),ev('RIGHTMOUSE','CLICK',sx+40,sy+30))
chk("glissé signalé par Blender (CLICK_DRAG, sans MOUSEMOVE) : orbite, pas d'Entrée", not curves() and 'RUNNING_MODAL' in r and len(o.points)==3, r); done(o)
o=start2(); r=send(o,ev('RIGHTMOUSE','PRESS',sx,sy),ev('MOUSEMOVE','NOTHING',sx+60,sy+40),ev('RIGHTMOUSE','RELEASE',sx+60,sy+40))
chk("glissé (MOUSEMOVE) : orbite, pas d'Entrée", not curves() and len(o.points)==3, r)
r=send(o,ev('RIGHTMOUSE','CLICK',sx+60,sy+40))
chk("... le CLICK qui suivrait la fin de l'orbite est absorbé", not curves() and 'RUNNING_MODAL' in r and len(o.points)==3, r)
r=send(o,ev('RIGHTMOUSE','PRESS',sx,sy),ev('RIGHTMOUSE','RELEASE',sx,sy))
chk("... puis un clic rapide valide normalement", len(curves())==1, r); done(o)
o=start2(); r=send(o,ev('RIGHTMOUSE','PRESS',sx,sy),ev('RIGHTMOUSE','RELEASE',sx+50,sy+50))
chk("relâché ailleurs sans mouvement reçu (orbite gérée hors de la commande) : pas d'Entrée", not curves() and len(o.points)==3, r); done(o)
o=start2(); r=send(o,ev('RIGHTMOUSE','PRESS',sx,sy),ev('MOUSEMOVE','NOTHING',sx+3,sy+2),ev('RIGHTMOUSE','RELEASE',sx+3,sy+2))
chk("petit tremblement (3 px) pendant un clic rapide : Entrée quand même", len(curves())==1, r); done(o)
o=start2(); r=send(o,ev('RIGHTMOUSE','PRESS',sx,sy),ev('RIGHTMOUSE','RELEASE',sx,sy),ev('RIGHTMOUSE','CLICK',sx,sy))
chk("clic rapide suivi du CLICK de Blender : une seule validation", len(curves())==1, r); done(o)
print("RESULTAT",sum(res),"/",len(res))
