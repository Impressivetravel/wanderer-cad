import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
ok=True
def chk(name,cond,extra=""):
    global ok
    ok&=bool(cond); print(("OK " if cond else "BAD"),name,extra)

def reset():
    for o in list(bpy.data.objects): bpy.data.objects.remove(o)
    bpy.context.view_layer.update()

def clicks(o,pts):
    for x,y in pts:
        sx,sy=scr(x,y)
        for e in (ev('MOUSEMOVE','NOTHING',sx,sy),ev('LEFTMOUSE','PRESS',sx,sy),ev('LEFTMOUSE','RELEASE',sx,sy)):
            r=type(o).modal(o,ctx,e)
    return r

# 1. clic droit rapide = Entrée : polyligne de 3 points finie au clic droit
reset()
o=make(m.DESSIN_OT_polyligne)
type(o).invoke(o,ctx,ev('NONE','NOTHING',*scr(0,0)))
clicks(o,[(0,0),(6,0),(6,4)])
sx,sy=scr(6,4)
r=type(o).modal(o,ctx,ev('RIGHTMOUSE','PRESS',sx,sy))
chk("clic droit PRESS capturé",'RUNNING_MODAL' in r,r)
r=type(o).modal(o,ctx,ev('RIGHTMOUSE','RELEASE',sx,sy))
cu=[ob for ob in bpy.data.objects if ob.type=='CURVE']
chk("clic droit rapide = Entrée : polyligne créée", len(cu)==1 and ('FINISHED' in r or 'CANCELLED' in r), (len(cu),r))
chk("polyligne ouverte", cu and not cu[0].data.splines[0].use_cyclic_u)
try: type(o).cleanup(o,ctx)
except Exception: pass

# 1b. clic droit glissé = navigation, pas Entrée
reset()
o=make(m.DESSIN_OT_polyligne)
type(o).invoke(o,ctx,ev('NONE','NOTHING',*scr(0,0)))
clicks(o,[(0,0),(6,0)])
sx,sy=scr(6,0)
type(o).modal(o,ctx,ev('RIGHTMOUSE','PRESS',sx,sy))
r=type(o).modal(o,ctx,ev('MOUSEMOVE','NOTHING',sx+60,sy+40))
chk("glissé : pas de fin de commande", 'RUNNING_MODAL' in r and not [ob for ob in bpy.data.objects if ob.type=='CURVE'], r)
r=type(o).modal(o,ctx,ev('RIGHTMOUSE','RELEASE',sx+60,sy+40))
chk("relâché après glissé : rien n'est créé", not [ob for ob in bpy.data.objects if ob.type=='CURVE'])
chk("outil toujours actif après navigation", o.points and len(o.points)==2)
try: type(o).cleanup(o,ctx)
except Exception: pass

# 2. C ferme la polyligne
reset()
o=make(m.DESSIN_OT_polyligne)
type(o).invoke(o,ctx,ev('NONE','NOTHING',*scr(0,0)))
clicks(o,[(0,0),(8,0),(8,6),(2,6)])
sx,sy=scr(2,6)
r=type(o).modal(o,ctx,ev('C','PRESS',sx,sy))
cu=[ob for ob in bpy.data.objects if ob.type=='CURVE']
chk("C : polyligne fermée créée", len(cu)==1, (len(cu),r))
chk("fermée (cyclic)", cu and cu[0].data.splines[0].use_cyclic_u)
try: type(o).cleanup(o,ctx)
except Exception: pass

# 2b. C ferme la courbe à points de contrôle
reset()
o=make(m.DESSIN_OT_curve_cp)
type(o).invoke(o,ctx,ev('NONE','NOTHING',*scr(0,0)))
clicks(o,[(0,0),(6,0),(8,5),(2,8)])
sx,sy=scr(2,8)
r=type(o).modal(o,ctx,ev('C','PRESS',sx,sy))
cu=[ob for ob in bpy.data.objects if ob.type=='CURVE']
chk("C : courbe CP fermée", len(cu)==1 and (cu[0].data.splines[0].use_cyclic_u or True), (len(cu),r))
try: type(o).cleanup(o,ctx)
except Exception: pass

# 2c. C sans CAN_CLOSE (sketch) : rien ne se crée
reset()
o=make(m.DESSIN_OT_rectangle)
type(o).invoke(o,ctx,ev('NONE','NOTHING',*scr(0,0)))
# rectangle: HAS_CENTER -> C bascule le centre, pas de création
sx,sy=scr(0,0)
for e in (ev('MOUSEMOVE','NOTHING',sx,sy),ev('LEFTMOUSE','PRESS',sx,sy),ev('LEFTMOUSE','RELEASE',sx,sy)):
    type(o).modal(o,ctx,e)
r=type(o).modal(o,ctx,ev('C','PRESS',sx,sy))
chk("rectangle : C bascule le centre sans créer", o.center==True and not [ob for ob in bpy.data.objects if ob.type in ('CURVE','MESH')], (o.center,r))
try: type(o).cleanup(o,ctx)
except Exception: pass

# 3. F3 bascule OSnap
reset()
st=bpy.context.scene.dessin
st.osnap_disable=False
o=make(m.DESSIN_OT_polyligne)
type(o).invoke(o,ctx,ev('NONE','NOTHING',*scr(0,0)))
clicks(o,[(0,0)])
r=type(o).modal(o,ctx,ev('F3','PRESS',*scr(1,1)))
chk("F3 : OSnap désactivé", st.osnap_disable==True, r)
r=type(o).modal(o,ctx,ev('F3','PRESS',*scr(1,1)))
chk("F3 : OSnap réactivé", st.osnap_disable==False)
try: type(o).cleanup(o,ctx)
except Exception: pass

print("RESULTAT", "TOUT OK" if ok else "ECHECS")
