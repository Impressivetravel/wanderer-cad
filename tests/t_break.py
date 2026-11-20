# Break / Break at Point (comme BREAK et BREAKATPOINT d'AutoCAD)
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
src=open(_os.path.join(_HERE,'t_pushpull.py')).read()
exec(src[src.index("\n")+1:src.index("# ---------------- 1. PushPull")])
st=C.scene.dessin; st.ortho=False; st.polar=False
def poly(name,pts,closed=False): return m.build_polyline(C,name,[Vector(p) for p in pts],closed)
def pts_of(q):
    out=[]
    for sp in q.data.splines:
        if sp.type=='POLY': out.append(([q.matrix_world@Vector(p.co[:3]) for p in sp.points], sp.use_cyclic_u, 'POLY'))
        else: out.append(([q.matrix_world@b.co for b in sp.bezier_points], sp.use_cyclic_u, sp.type))
    return out
def length(P): return sum((P[i+1]-P[i]).length for i in range(len(P)-1))
def curves(prefix): return sorted([q for q in bpy.data.objects if q.name.startswith(prefix)], key=lambda q: q.name)
def near(a,b,t=1e-6): return (Vector(a)-Vector(b)).length<t

# ---------------- deux points sur une ligne ----------------
clear(); L=poly("Line",[(0,0,0),(10,0,0)]); L.color=(1,0,0,1); L["wd_lt"]="DASHED"; C.view_layer.update()
o,r=start(m.DESSIN_OT_break_crv); o.snap_on=False
E(o,('c',3,0)); E(o,('m',6,0.1))
chk("aperçu : la partie à retirer s'allume (de 3 à 6)", len(o.hilite)>=1 and near(o.hilite[0][0],(3,0,0),1e-3), o.hilite[:1])
E(o,('c',6,0.1))
cs=curves("Line")
segs=sorted([pts_of(q)[0][0] for q in cs], key=lambda P: P[0].x)
chk("ligne cassée entre 3 et 6 : deux morceaux, de 0 à 3 et de 6 à 10", len(cs)==2 and near(segs[0][0],(0,0,0)) and near(segs[0][-1],(3,0,0),1e-3)
    and near(segs[1][0],(6,0,0),1e-3) and near(segs[1][-1],(10,0,0)), [[tuple(round(c,3) for c in p) for p in P] for P in segs])
chk("... le second morceau garde calque, couleur et type de ligne", all(tuple(q.color)==(1,0,0,1) and q.get("wd_lt")=="DASHED" and q.users_collection==L.users_collection for q in cs))
E(o,('c',8,0),('c',9,0))
chk("la commande reste active : une seconde coupure (8 à 9) donne trois morceaux", len(curves("Line"))==3, len(curves("Line")))
r_=E(o,'ESC')
chk("Échap : terminée « faite » (un pas d'annulation)", r_=={'FINISHED'}, r_)

# ---------------- dans l'autre sens ----------------
clear(); L=poly("Line",[(0,0,0),(10,0,0)]); C.view_layer.update()
o,r=start(m.DESSIN_OT_break_crv); E(o,('c',8,0),('c',2,0)); E(o,'ESC')
segs=sorted([pts_of(q)[0][0] for q in curves("Line")], key=lambda P: P[0].x)
chk("second point avant le premier : même résultat (0-2 et 8-10)", len(segs)==2 and abs(length(segs[0])-2)<1e-3 and abs(length(segs[1])-2)<1e-3,
    [round(length(P),3) for P in segs])

# ---------------- en un point (D) et Entrée ----------------
clear(); L=poly("Line",[(0,0,0),(10,0,0)]); C.view_layer.update()
o,r=start(m.DESSIN_OT_break_crv); o.snap_on=False; E(o,'D',('c',4,0)); E(o,'ESC')
segs=sorted([pts_of(q)[0][0] for q in curves("Line")], key=lambda P: P[0].x)
chk("At Point (D) : coupée en deux en 4, sans espace", len(segs)==2 and near(segs[0][-1],(4,0,0),1e-3) and near(segs[1][0],(4,0,0),1e-3), [len(P) for P in segs])
clear(); L=poly("Line",[(0,0,0),(10,0,0)]); C.view_layer.update()
o,r=start(m.DESSIN_OT_break_crv); E(o,('c',7,0),'RET'); E(o,'ESC')
segs=sorted([pts_of(q)[0][0] for q in curves("Line")], key=lambda P: P[0].x)
chk("Entrée après le premier point : coupée en ce point", len(segs)==2 and near(segs[0][-1],(7,0,0),1e-3), [len(P) for P in segs])
clear(); L=poly("Line",[(0,0,0),(10,0,0)]); C.view_layer.update()
o,r=start(m.DESSIN_OT_break_crv); E(o,'D',('c',0,0)); E(o,'ESC')
chk("At Point sur une extrémité : rien n'est coupé", len(curves("Line"))==1 and len(pts_of(L)[0][0])==2)

# ---------------- polyligne fermée : la partie la plus courte ----------------
clear(); R=poly("Rect",[(0,0,0),(10,0,0),(10,5,0),(0,5,0)],True); C.view_layer.update()
o,r=start(m.DESSIN_OT_break_crv); o.snap_on=False; E(o,('c',2,0),('c',4,0)); E(o,'ESC')
P,cl,_t=pts_of(R)[0]
chk("rectangle fermé cassé entre (2,0) et (4,0) : ouvert, il manque 2 (une baie), longueur 28", len(curves("Rect"))==1 and not cl and abs(length(P)-28)<1e-3
    and {tuple(round(c,3) for c in P[0]), tuple(round(c,3) for c in P[-1])}=={(4.0,0.0,0.0),(2.0,0.0,0.0)}, (cl, round(length(P),3)))
clear(); R=poly("Rect",[(0,0,0),(10,0,0),(10,5,0),(0,5,0)],True); C.view_layer.update()
o,r=start(m.DESSIN_OT_break_crv); E(o,'D',('c',5,5)); E(o,'ESC')
P,cl,_t=pts_of(R)[0]
chk("At Point sur une courbe fermée : elle s'ouvre en ce point (même longueur)", not cl and abs(length(P)-30)<1e-3 and near(P[0],(5,5,0),1e-3) and near(P[-1],(5,5,0),1e-3), (cl, round(length(P),3)))

# ---------------- cercle : reste un vrai arc ----------------
clear()
c=m.build_bezier_arc(C,"Circle",Vector((0,0,0)),Vector((1,0,0)),Vector((0,1,0)),3.0,0.0,2*math.pi,True); C.view_layer.update()
o,r=start(m.DESSIN_OT_break_crv); E(o,('c',3,0),('c',0,3)); E(o,'ESC')
sp=c.data.splines
ok_arc=len(sp)==1 and sp[0].type=='BEZIER' and not sp[0].use_cyclic_u and all(abs((c.matrix_world@b.co).length-3)<1e-4 for b in sp[0].bezier_points)
chk("cercle cassé entre 0° et 90° : un arc de Bézier (le plus court quart retiré), toujours sur le cercle", ok_arc, [(s.type,s.use_cyclic_u,len(s.bezier_points)) for s in sp])
g=m.wire_graph(c, C.evaluated_depsgraph_get())
Ls=sum((g[0][a]-g[0][b]).length for a,b in g[1])
chk("... longueur de l'arc restant : trois quarts du cercle", abs(Ls-2*math.pi*3*0.75)<0.02, round(Ls,4))

# ---------------- contour (maillage sans face), point accroché ----------------
clear()
me=bpy.data.meshes.new("w"); me.from_pydata([(0,0,0),(10,0,0)],[(0,1)],[]); Wo=bpy.data.objects.new("Wire",me); C.collection.objects.link(Wo)
poly("Cross",[(6,-3,0),(6,3,0)]); C.view_layer.update()
o,r=start(m.DESSIN_OT_break_crv); E(o,'D',('c',6.05,0.02)); E(o,'ESC')
ws=[q for q in bpy.data.objects if q.name.startswith("Wire")]
V=sorted([tuple(round(c,9) for c in (q.matrix_world@v.co)) for q in ws for v in q.data.vertices])
chk("contour sans face coupé à l'intersection accrochée, exactement en (6, 0)", len(ws)==2 and V.count((6.0,0.0,0.0))==2, V)
clear(); poly("Line",[(0,0,0),(10,0,0)]); C.view_layer.update()
o,r=start(m.DESSIN_OT_break_crv); E(o,('c',5,20)); E(o,'ESC')
chk("clic loin de toute courbe : rien", len(curves("Line"))==1)
print("RESULTAT",sum(res),"/",len(res))
