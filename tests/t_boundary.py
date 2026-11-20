# Boundary (comme BOUNDARY d'AutoCAD), Area par point, Hatch Region : la zone fermée par des traits qui se croisent
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
src=open(_os.path.join(_HERE,'t_pushpull.py')).read()
exec(src[src.index("\n")+1:src.index("# ---------------- 1. PushPull")])
import time
st=C.scene.dessin; st.ortho=False; st.polar=False
def poly(name,pts,closed=False): return m.build_polyline(C,name,[Vector(p) for p in pts],closed)
def room():
    clear()
    poly("W1",[(-1,0,0),(11,0,0)]); poly("W2",[(10,-1,0),(10,9,0)]); poly("W3",[(11,8,0),(-1,8,0)]); poly("W4",[(0,9,0),(0,-1,0)])
    poly("Col",[(4,3,0),(6,3,0),(6,5,0),(4,5,0)],True)            # poteau : un îlot
    poly("Stub",[(2,0,0),(2,3,0)])                                # cloison qui s'arrête dans la pièce (bout libre)
    C.view_layer.update()
def new(prefix): return [q for q in bpy.data.objects if q.name.startswith(prefix)]
def ring_of(q):
    sp=q.data.splines[0]; return [q.matrix_world@Vector(p.co[:3]) for p in sp.points], sp.use_cyclic_u
def area2(P):
    return 0.5*abs(sum(P[i].x*P[(i+1)%len(P)].y-P[(i+1)%len(P)].x*P[i].y for i in range(len(P))))

# ---------------- Boundary ----------------
room()
o,r=start(m.DESSIN_OT_boundary)
E(o,('m',7,6))
chk("survol : la zone sous le curseur s'allume (murs qui se croisent, sans contour fermé d'un seul tenant)", len(o.hilite)>=8, len(o.hilite))
E(o,('c',7,6))
b=new("Boundary")
outer=[q for q in b if len(q.data.splines[0].points)==4 and abs(area2(ring_of(q)[0])-80)<1e-6]
isl=[q for q in b if abs(area2(ring_of(q)[0])-4)<1e-6]
chk("clic dans la pièce : une polyligne fermée sur le contour (10 × 8, 4 sommets : les murs coupés aux croisements, la cloison libre ignorée)",
    len(outer)==1 and ring_of(outer[0])[1], [(q.name,len(q.data.splines[0].points),round(area2(ring_of(q)[0]),3)) for q in b])
chk("... et une autour de l'îlot (le poteau)", len(isl)==1 and len(b)==2, len(b))
chk("... dans le plan du dessin (z = 0)", all(abs(p.z)<1e-9 for q in b for p in ring_of(q)[0]))
chk("la commande reste active pour la pièce suivante", o.__class__.modal(o,ctx,ev('MOUSEMOVE','NOTHING',*scr(7,6))) not in ({'FINISHED'},{'CANCELLED'}))
E(o,'D'); E(o,('c',8,1))
b2=new("Boundary")
chk("D : contour seul (sans les îlots) : une seule polyligne de plus", len(b2)==3, len(b2))
n0=len(new("Boundary")); E(o,('c',30,30))
chk("clic hors de toute zone fermée : rien n'est créé", len(new("Boundary"))==n0)
E(o,'ESC')

# ---------------- Area / Perimeter : Inside ----------------
room()
o,r=start(m.DESSIN_OT_mesure_aire)
chk("Area / Perimeter : D passe de Points à Inside", o.MODES==("Points","Inside","Selection"))
E(o,'D'); E(o,('m',7,6))
chk("Inside : la zone s'allume au survol et l'aire s'affiche", len(o.hilite)>=8 and o.dim_label is not None and "76" in o.dim_label[1], o.dim_label)
E(o,('c',7,6))
txt=o.last[0] if o.last else ""
chk("clic : aire = 10 × 8 - poteau 2 × 2 = 76, périmètre du contour 36 (gardé et copié)", txt.startswith("A = 76") and "P = 36" in txt and "island" in txt, txt)
chk("Inside ne crée rien dans la scène", not new("Boundary"))
E(o,'ESC')

# ---------------- Hatch Region : traits qui se croisent ----------------
room()
o,r=start(m.DESSIN_OT_hatch_region)
E(o,('c',7,6))
h=[q for q in bpy.data.objects if q.get("dessin_hatch")]
import json
chk("Hatch Region : la pièce fermée par des traits qui se croisent est hachurée, poteau en trou", len(h)==1 and len(json.loads(h[0]["dessin_hatch"])["rings"])==2,
    [len(json.loads(q["dessin_hatch"])["rings"]) for q in h])
E(o,'ESC')
room()
poly("Closed",[(20,0,0),(24,0,0),(24,3,0),(20,3,0)],True); C.view_layer.update()
o,r=start(m.DESSIN_OT_hatch_region); E(o,('c',22,1))
h=[q for q in bpy.data.objects if q.get("dessin_hatch")]
chk("... un contour fermé ordinaire : comme avant", len(h)==1)
E(o,'ESC')

# ---------------- murs superposés, arcs ----------------
clear()
poly("A",[(0,0,0),(5,0,0),(5,4,0),(0,4,0)],True); poly("B",[(5,1,0),(9,1,0),(9,3,0),(5,3,0)],True); C.view_layer.update()
o,r=start(m.DESSIN_OT_boundary); E(o,('c',7,2))
b=new("Boundary")
chk("deux rectangles qui partagent un bout de côté : la zone du second seulement (4 × 2)", len(b)==1 and abs(area2(ring_of(b[0])[0])-8)<1e-6,
    [round(area2(ring_of(q)[0]),3) for q in b])
E(o,'ESC')
clear()
poly("L",[(0,0,0),(6,0,0)]); poly("L2",[(0,0,0),(0,3,0)]); poly("L3",[(6,0,0),(6,3,0)])
cu=bpy.data.curves.new("Arc",'CURVE'); cu.dimensions='3D'; sp=cu.splines.new('POLY'); N=24
sp.points.add(N)
for i in range(N+1):
    a=math.pi*i/N; sp.points[i].co=(3+3*math.cos(a),3+3*math.sin(a),0,1)
ob=bpy.data.objects.new("Arc",cu); C.collection.objects.link(ob); C.view_layer.update()
o,r=start(m.DESSIN_OT_boundary); E(o,('c',3,2))
b=new("Boundary")
exp=18+0.5*N*9*math.sin(math.pi/N)
chk("mur courbe : le contour suit l'arc", len(b)==1 and abs(area2(ring_of(b[0])[0])-exp)<1e-6, [round(area2(ring_of(q)[0]),4) for q in b]+[round(exp,4)])
E(o,'ESC')

# ---------------- plan chargé ----------------
clear()
for i in range(41):
    poly(f"V{i}",[(i*2.0-40,-41,0),(i*2.0-40,41,0)])
    poly(f"H{i}",[(-41,i*2.0-40,0),(41,i*2.0-40,0)])
for i in range(400):
    x,y=(i%20)*4+0.5-40,(i//20)*4+0.5-40
    poly(f"F{i}",[(x,y,0),(x+0.6,y,0),(x+0.6,y+0.6,0),(x,y+0.6,0)],True)
C.view_layer.update()
o,r=start(m.DESSIN_OT_boundary)
t=time.perf_counter(); E(o,('m',1,1)); t1=time.perf_counter()-t
t=time.perf_counter(); E(o,('m',1.3,1.2)); t2=time.perf_counter()-t
chk("plan de 480 courbes qui se croisent (1 600 cellules, 400 îlots) : premier survol < 2 s, les suivants < 50 ms", t1<2.0 and t2<0.05, (round(t1,3),round(t2,4)))
E(o,('c',1.5,1.5))
b=new("Boundary")
chk("... la bonne cellule (2 × 2) et son îlot", len(b)==2 and sorted(round(area2(ring_of(q)[0]),3) for q in b)==[0.36,4.0], [round(area2(ring_of(q)[0]),3) for q in b])
E(o,'ESC')
# ---------------- loin de l'origine, vue de face, traits qui se touchent à peine ----------------
clear()
OX,OY=30.0,-25.0
a=math.radians(27.3); ca,sa=math.cos(a),math.sin(a)
def T2(x,y): return (OX+ca*x-sa*y, OY+sa*x+ca*y, 0)
poly("W1",[T2(-0.4,0),T2(7.3,0)]); poly("W2",[T2(7.1,-0.3),T2(7.1,4.6)]); poly("W3",[T2(7.3,4.4),T2(-0.2,4.4)]); poly("W4",[T2(0,4.6),T2(0,-0.2)])
poly("T1",[T2(3.3,0),T2(3.3,4.4)])              # cloison dont les deux bouts sont posés sur les murs (jonctions en T)
C.view_layer.update()
o,r=start(m.DESSIN_OT_boundary); E(o,('c',*T2(1.5,2.2)[:2])); E(o,('c',*T2(5.2,2.2)[:2])); E(o,'ESC')
ar=sorted(round(area2(ring_of(q)[0]),4) for q in new("Boundary"))
chk("plan tourné de 27° : les deux pièces séparées par une cloison en T (3,3 × 4,4 et 3,8 × 4,4)", ar==[round(3.3*4.4,4),round(3.8*4.4,4)], ar)
big=[Vector((50000+x,-30000+y,0)) for x,y in ((0,0),(3.7,0),(3.7,2.9),(0,2.9))]
chk("Area : contour mesuré loin de l'origine (50 km) : pas de chiffres perdus (10,73 à 1 mm² près)", abs(m.loop_area(big)-10.73)<2e-3, m.loop_area(big))
G=m.region_under_mouse.__globals__
chk("aire d'une zone loin de l'origine : exacte", abs(G['ring_area'](np.array([(5e4+x,3e4+y) for x,y in ((0,0),(3.7,0),(3.7,2.9),(0,2.9))]))-10.73)<1e-9)
print("RESULTAT",sum(res),"/",len(res))
