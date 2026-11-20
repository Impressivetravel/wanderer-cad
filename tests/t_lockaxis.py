import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
src=open(_os.path.join(_HERE,'t_pushpull.py')).read()
exec(src[src.index("\n")+1:src.index("# ---------------- 1. PushPull")])
# Move / Copy : axe verrouillé vu en bout (Z en vue de dessus) + distance tapée -> le long de l'axe.
# Polyligne : OSnap coupé (F3), elle ne s'accroche plus à ses propres points (sauf le premier, pour fermer).
K.update({'6':'SIX','7':'SEVEN','8':'EIGHT','9':'NINE'})
def R3(v): return tuple(round(x,4) for x in v)
def mn(o): return R3(min((o.matrix_world@Vector(b))[i] for b in o.bound_box) for i in range(3))
def sel(o):
    for q in bpy.data.objects: q.select_set(q is o)
    C.view_layer.objects.active=o
C.scene.dessin.osnap_disable=True      # (sinon le curseur, resté sur le coin, s'accroche au sommet du dessous)
clear(); b=box(1,(0.5,0.5,0.5)); sel(b)
o,r=start(m.DESSIN_OT_deplacer); r=E(o,('c',0,0),'Z',('t','0.9'),'RET'); C.view_layer.update()
chk("Move en vue de dessus : Z puis 0.9 tapé -> l'objet monte de 0.9 (il partait en X)", mn(b)==(0,0,0.9), mn(b))
sel(b); o,r=start(m.DESSIN_OT_deplacer); r=E(o,('c',0,0),'Z',('m',3,2),('t','0.6'),'RET'); C.view_layer.update()
chk("... même après avoir bougé la souris ailleurs", mn(b)==(0,0,1.5), mn(b))
sel(b); o,r=start(m.DESSIN_OT_deplacer); r=E(o,('c',0,0),'Z',('t','-1.5'),'RET'); C.view_layer.update()
chk("... une distance négative descend", mn(b)==(0,0,0), mn(b))
sel(b); o,r=start(m.DESSIN_OT_deplacer); r=E(o,('c',0,0),'Z',('m',3,2),('c',3,2)); C.view_layer.update()
chk("Z verrouillé en vue de dessus, clic sans rien taper : l'objet ne bouge pas (il ne part pas dans le plan)", mn(b)==(0,0,0), mn(b))
b.location=(0.5,0.5,0.5); C.view_layer.update()
sel(b); o,r=start(m.DESSIN_OT_deplacer); r=E(o,('c',0,0),'X',('m',3,2),('t','2'),'RET'); C.view_layer.update()
chk("X verrouillé + 2 tapé, souris à droite : +2 en X (inchangé)", mn(b)==(2,0,0), mn(b))
sel(b); o,r=start(m.DESSIN_OT_deplacer); r=E(o,('c',2,0),'X',('m',-3,2),('t','2'),'RET'); C.view_layer.update()
chk("X verrouillé + 2 tapé, souris à gauche : -2 en X (le sens suit la souris)", mn(b)==(0,0,0), mn(b))
sel(b); o,r=start(m.DESSIN_OT_deplacer); r=E(o,('c',0,0),('m',3,4),('t','5'),'RET'); C.view_layer.update()
chk("sans verrou : 5 tapé vers la souris (3, 4) comme avant", mn(b)==(3,4,0), mn(b))
b.location=(0.5,0.5,0.5); C.view_layer.update()
sel(b); o,r=start(m.DESSIN_OT_copier); r=E(o,('c',0,0),'Z',('t','2.9'),'RET','ESC'); C.view_layer.update()
cp=[q for q in bpy.data.objects if q is not b]
chk("Copy : Z puis 2.9 tapé -> une copie 2.9 plus haut", len(cp)==1 and mn(cp[0])==(0,0,2.9) and mn(b)==(0,0,0), [mn(q) for q in cp])
# ---- polyligne et ses propres points
clear()
st=C.scene.dessin; st.osnap_disable=True; m.PREF_DEFAULTS["smart_tracks"]=False      # (SmartTrack est un autre réglage)
o,r=start(m.DESSIN_OT_polyligne); r=E(o,('c',0,0),('c',10,0),('c',10,10),('c',9.4,0.5),('c',5,5),'RET'); C.view_layer.update()
pl=[q for q in bpy.data.objects if q.type=='CURVE'][0]
P=[R3((pl.matrix_world@Vector(p.co[:3])))[:2] for p in pl.data.splines[0].points]
chk("OSnap coupé : un point cliqué à 8 px d'un sommet déjà posé reste où il est cliqué", P[3]==(9.4,0.5) and len(P)==5, P)
clear()
o,r=start(m.DESSIN_OT_polyligne); r=E(o,('c',0,0),('c',10,0),('c',10,10),('c',0.4,0.5)); C.view_layer.update()
pl=[q for q in bpy.data.objects if q.type=='CURVE']
chk("OSnap coupé : cliquer près du premier point ferme toujours la forme", len(pl)==1 and pl[0].data.splines[0].use_cyclic_u and len(pl[0].data.splines[0].points)==3, [len(q.data.splines[0].points) for q in pl])
clear(); st.osnap_disable=False
o,r=start(m.DESSIN_OT_polyligne); r=E(o,('c',0,0),('c',10,0),('c',10,10),('c',9.4,0.5),('c',5,5),'RET'); C.view_layer.update()
pl=[q for q in bpy.data.objects if q.type=='CURVE'][0]
P=[R3((pl.matrix_world@Vector(p.co[:3])))[:2] for p in pl.data.splines[0].points]
chk("OSnap actif : le point s'accroche au sommet déjà posé (comme avant)", P[3]==(10,0), P)
print("RESULTAT",sum(res),"/",len(res))
