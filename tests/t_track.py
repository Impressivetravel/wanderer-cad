# SmartTrack : prolongement des segments (comme SmartTrack de Rhino / l'accrochage Extension d'AutoCAD)
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
src=open(_os.path.join(_HERE,'t_pushpull.py')).read()
exec(src[src.index("\n")+1:src.index("# ---------------- 1. PushPull")])
import time, numpy as np
st=C.scene.dessin; st.ortho=False; st.polar=False
def poly(name,pts,closed=False): return m.build_polyline(C,name,[Vector(p) for p in pts],closed)
def scene():
    clear(); p=poly("P",[(-30,10,0),(-10,10,0),(0,0,0)]); C.view_layer.update(); return p
def off_line(p, a=(-10,10), b=(0,0)):
    """Écart du point p à la droite (a, b) du plan XY."""
    ax,ay=a; bx,by=b; L=math.hypot(bx-ax,by-ay)
    return abs((p.x-ax)*(by-ay)-(p.y-ay)*(bx-ax))/L
def acquire(o,x,y):
    """Survol d'un point d'accrochage assez longtemps pour l'acquérir (0,5 s)."""
    E(o,('m',x,y)); o.track_tick(); o._hover_t-=1.0; o.track_tick()
def new_curves(): return [q for q in bpy.data.objects if q.type=='CURVE' and q.name!="P"]
def pts_of(q): return [q.matrix_world@Vector(p.co[:3]) for sp in q.data.splines for p in sp.points]

# ---------------- 1. comme dans la vidéo : départ sur l'extrémité, le curseur se cale sur le prolongement ----------------
scene(); o,r=start(m.DESSIN_OT_polyligne)
E(o,('c',0,0))
chk("le premier clic s'accroche à l'extrémité (End) de la polyligne", len(o.points)==1 and (o.points[0]-Vector((0,0,0))).length<1e-9, o.points)
E(o,('m',8.3,-7.8))
chk("curseur à 3,5 px du prolongement : il se cale exactement dessus", o.cur is not None and off_line(o.cur)<1e-9 and abs(o.cur.z)<1e-12 and o.track_label=="Ext", (o.cur,o.track_label))
chk("... la ligne de repérage affichée part de l'extrémité, dans la direction du segment",
    len(o.track_lines)==1 and (o.track_lines[0][0]-Vector((0,0,0))).length<1e-9 and isinstance(o.track_lines[0][1],Vector)
    and abs(abs(o.track_lines[0][1].dot(Vector((1,-1,0)).normalized()))-1)<1e-12, o.track_lines)
E(o,('c',8.3,-7.8),'RET'); C.view_layer.update()
nc=new_curves(); P=pts_of(nc[0]) if nc else []
chk("la polyligne créée prolonge le segment : son 2e point est sur la droite (écart < 1e-6)", len(nc)==1 and len(P)==2 and off_line(P[1])<1e-6 and (P[0]).length<1e-6 and P[1].x>7, P)
a=(P[1]-P[0]).normalized() if len(P)==2 else Vector((1,0,0))
ang=math.degrees(math.atan2(a.cross(Vector((1,-1,0)).normalized()).length, a.dot(Vector((1,-1,0)).normalized())))
chk("... angle entre l'ancien segment et le nouveau : 0° (à 1e-4° près)", ang<1e-4, ang)

# ---------------- 2. loin du prolongement : rien ne change ----------------
scene(); o,r=start(m.DESSIN_OT_polyligne); E(o,('c',0,0),('m',9.0,-5.0))
chk("curseur à 28 px du prolongement : pas d'aimantation", o.track_label!="Ext" and (o.cur-Vector((9,-5,0))).length<1e-6, (o.cur,o.track_label))
E(o,'ESC')

# ---------------- 3. extrémité seulement survolée (point acquis), premier point ailleurs ----------------
scene(); o,r=start(m.DESSIN_OT_polyligne); acquire(o,0,0)
chk("survol de 0,5 s : l'extrémité est acquise", len(o.track_pts)==1 and o.track_pts[0].length<1e-9, o.track_pts)
E(o,('m',12.2,-11.6))
chk("avant le premier point : le curseur se cale sur le prolongement de l'extrémité acquise", off_line(o.cur)<1e-9 and o.track_label=="Ext", (o.cur,o.track_label))
E(o,('c',-20,-20),('m',15.3,-14.9))
chk("après un premier point ailleurs : le prolongement reste proposé", off_line(o.cur)<1e-9 and o.track_label=="Ext", (o.cur,o.track_label))
E(o,('m',20.2,-20.0))
chk("croisement du prolongement et de l'horizontale du premier point : (20, -20) exactement", (o.cur-Vector((20,-20,0))).length<1e-9 and len(o.track_lines)==2, (o.cur,o.track_label))
E(o,'ESC')

# ---------------- 4. l'autre extrémité, segment horizontal : pas de ligne en double avec X ----------------
scene(); o,r=start(m.DESSIN_OT_polyligne); E(o,('c',-30,10),('m',-38,10.3))
chk("segment parallèle à X : une seule ligne (X), pas de doublon « Ext »", o.track_label=="X" and len(o.track_lines)==1 and abs(o.cur.y-10)<1e-9, (o.cur,o.track_label))
chk("... et aucune direction de prolongement gardée pour ce point", o.track_ext_dirs(Vector((-30,10,0)))==[], o.track_ext_dirs(Vector((-30,10,0))))
E(o,'ESC')

# ---------------- 5. sommet intérieur : les deux segments donnent chacun leur prolongement ----------------
scene(); o,r=start(m.DESSIN_OT_polyligne)
d=o.track_ext_dirs(Vector((-10,10,0)))
chk("coin de la polyligne : 1 direction oblique (l'horizontale est déjà l'axe X)", len(d)==1 and abs(abs(d[0].dot(Vector((1,-1,0)).normalized()))-1)<1e-12, d)
E(o,('c',-10,10),('m',-15.2,14.9))
chk("prolongement vers l'arrière du segment oblique depuis le coin", off_line(o.cur)<1e-9 and o.track_label=="Ext" and o.cur.x<-14, (o.cur,o.track_label))
E(o,'ESC')

# ---------------- 6. SmartTrack coupé : pas de prolongement ----------------
scene(); m.PREF_DEFAULTS["smart_tracks"]=False
try:
    o,r=start(m.DESSIN_OT_polyligne); E(o,('c',0,0),('m',8.3,-7.8))
    chk("SmartTrack désactivé : le curseur reste libre", o.track_label!="Ext" and (o.cur-Vector((8.3,-7.8,0))).length<1e-6, (o.cur,o.track_label))
    E(o,'ESC')
finally:
    m.PREF_DEFAULTS["smart_tracks"]=True

# ---------------- 7. Ortho actif : près du prolongement il l'emporte, ailleurs Ortho reste ----------------
scene(); st.ortho=True
o,r=start(m.DESSIN_OT_polyligne); E(o,('c',0,0),('m',8.3,-7.8))
chk("Ortho actif, curseur près du prolongement : le prolongement l'emporte", off_line(o.cur)<1e-9 and o.track_label=="Ext", (o.cur,o.track_label))
E(o,('m',9.0,-3.0))
chk("Ortho actif, curseur ailleurs : contrainte Ortho comme avant", o.track_label=="Ortho" and abs(o.cur.y)<1e-9, (o.cur,o.track_label))
E(o,'ESC'); st.ortho=False

# ---------------- 8. arête d'un solide et courbe tournée / à l'échelle ----------------
clear(); b=box(size=4,loc=(0,0,2)); b.rotation_euler=(0,0,math.radians(30)); C.view_layer.update()
c0=b.matrix_world@Vector((2,2,-2)); c1=b.matrix_world@Vector((-2,2,-2))
o,r=start(m.DESSIN_OT_polyligne); E(o,('c',c0.x,c0.y))
u=(c0-c1).normalized(); q=c0+u*9+Vector((-u.y,u.x,0))*0.3
E(o,('m',q.x,q.y))
chk("coin d'une boîte tournée de 30° : prolongement de son arête au sol", o.track_label=="Ext" and off_line(o.cur,(c1.x,c1.y),(c0.x,c0.y))<1e-6 and abs(o.cur.z-o.points[0].z)<1e-9, (o.cur,o.track_label))
E(o,'ESC')
clear(); p=poly("P",[(-3,1,0),(-1,1,0),(0,0,0)]); p.scale=(10,10,10); p.rotation_euler=(0,0,math.radians(17)); p.location=(3,-4,0); C.view_layer.update()
e0=p.matrix_world@Vector((0,0,0)); e1=p.matrix_world@Vector((-1,1,0)); u=(e0-e1).normalized(); q=e0+u*12+Vector((-u.y,u.x,0))*0.4
o,r=start(m.DESSIN_OT_polyligne); E(o,('c',e0.x,e0.y),('m',q.x,q.y))
chk("courbe à l'échelle 10, tournée de 17°, déplacée : prolongement exact", o.track_label=="Ext" and off_line(o.cur,(e1.x,e1.y),(e0.x,e0.y))<1e-6, (o.cur,o.track_label))
E(o,'ESC')

# ---------------- 9. autres outils : Line / Move profitent du même repérage ----------------
scene(); o,r=start(m.DESSIN_OT_cercle); E(o,('m',0,0)); o.track_tick(); o._hover_t-=1.0; o.track_tick(); E(o,('m',10.3,-9.8))
chk("Circle : centre calé sur le prolongement d'une extrémité acquise", off_line(o.cur)<1e-9 and o.track_label=="Ext", (o.cur,o.track_label))
E(o,'ESC')

# ---------------- 10. vitesse : 200 000 segments d'accrochage, déplacement de souris ----------------
scene(); o,r=start(m.DESSIN_OT_polyligne); E(o,('c',0,0))
rng=np.random.default_rng(1); far=rng.uniform(500,900,(200000,2,3))
o.snap_data.edges=np.concatenate([o.snap_data.edges,far]); ne=len(o.snap_data.edges)
t=time.perf_counter(); d=o.track_ext_dirs(Vector((0,0,0))); t_first=time.perf_counter()-t
t=time.perf_counter(); d2=o.track_ext_dirs(Vector((0,0,0))); t_cached=time.perf_counter()-t
t=time.perf_counter()
for i in range(200): E(o,('m',8.3+0.01*i,-7.8-0.01*i))
t_move=(time.perf_counter()-t)/200
chk(f"{ne} segments : 1re recherche < 15 ms, suivantes < 0,1 ms (cache), déplacement de souris < 8 ms",
    len(d)==1 and d2 is d and t_first<0.015 and t_cached<1e-4 and t_move<0.008 and o.track_label=="Ext", (round(t_first*1000,2),round(t_cached*1e6,1),round(t_move*1000,3),o.track_label))
E(o,'ESC')

# ---------------- 11. Annuler / Rétablir ----------------
scene()
def run():
    o,r=start(m.DESSIN_OT_polyligne); E(o,('c',0,0),('c',8.3,-7.8),'RET')
undo_redo("polyligne tracée sur un prolongement", run)
print("RESULTAT",sum(res),"/",len(res))
