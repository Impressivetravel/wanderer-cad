# Move : l'objet suit chaque mouvement de souris quand la mise à jour est légère (cas courant, même dans une grosse scène :
# l'accrochage coûte ~0,1 ms). Avant, une cadence minimale de 22 ms laissait passer un événement sur deux ou trois et
# tombait entre deux images de l'écran : l'objet avançait par petits à-coups. Une mise à jour lourde reste espacée.
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
src=open(_os.path.join(_HERE,'t_pushpull.py')).read()
exec(src[src.index("\n")+1:src.index("# ---------------- 1. PushPull")])
import time
st=C.scene.dessin; st.ortho=False; st.polar=False
def poly(name,pts,closed=False): return m.build_polyline(C,name,[Vector(p) for p in pts],closed)
clear(); A=poly("A",[(0,0,0),(4,0,0),(4,4,0),(0,4,0)],True); C.view_layer.update()
for q in bpy.data.objects: q.select_set(q.name=="A")
C.view_layer.objects.active=A
o,r=start(m.DESSIN_OT_deplacer); E(o,('c',0,0))
chk("point de base posé", len(o.points)==1, o.points)

def at(x,y): return (A.matrix_world.translation-Vector((x,y,0))).length<0.15     # (pas d'écran du banc d'essai : 0,1)
path=[(10.0+i*1.3, 12.0+0.3*i) for i in range(12)]          # loin de la position d'origine (pas d'accroche au fantôme)
follow=[]
for x,y in path:                      # rafale : 12 événements en quelques millisecondes (souris rapide)
    E(o,('m',x,y)); follow.append(at(x,y))
chk("mise à jour légère : l'objet suit chacun des 12 mouvements de souris d'une rafale, sans en sauter", all(follow), follow)
chk("... aucune cadence imposée", getattr(o,"_gap",0.0)==0.0 and getattr(o,"_pending",None) is None, (getattr(o,"_gap",None), getattr(o,"_cost",None)))

# mise à jour lourde (simulée : 30 ms) : le rythme s'adapte, l'événement suivant immédiat attend son tour
orig=o.find_snap
def slow(*a,**k):
    time.sleep(0.03); return orig(*a,**k)
o.find_snap=slow
for i in range(4):
    E(o,('m',20+1.3*i,13))
if o._pending is not None: o.flush_pending(ctx)
chk("mises à jour lourdes : l'objet arrive bien à la dernière position", at(23.9,13), tuple(A.matrix_world.translation))
chk("... l'intervalle s'adapte à leur coût", 0.02<o._gap<=0.12, (o._gap,o._cost))
o._t_move=time.monotonic()            # une mise à jour lourde vient de se terminer (indépendant de la charge de la machine)
E(o,('m',30,13))
chk("... l'événement qui suit aussitôt attend (pas de calcul lourd à chaque événement)", at(23.9,13) and o._pending is not None, tuple(A.matrix_world.translation))
o.flush_pending(ctx)
chk("... puis il est appliqué (la dernière position n'est jamais perdue)", at(30,13), tuple(A.matrix_world.translation))

o.find_snap=orig
for i in range(8):
    time.sleep(o._gap+0.005); E(o,('m',31+1.3*i,13))
chk("mises à jour de nouveau légères : retour au suivi de chaque mouvement", o._gap==0.0, (o._gap,o._cost))
follow=[]
for x,y in path:
    E(o,('m',x,y+10)); follow.append(at(x,y+10))
chk("... nouvelle rafale suivie sans saut", all(follow), follow)
E(o,('c',path[-1][0],path[-1][1]+10)); C.view_layer.update()
chk("le clic final pose l'objet à la bonne place", at(path[-1][0],path[-1][1]+10), tuple(A.matrix_world.translation))
print("RESULTAT",sum(res),"/",len(res))
