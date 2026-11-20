# Grosse scène : les passages sur tous les objets ne doivent pas appeler Object.users_collection objet par objet (des
# secondes de blocage à chaque objet créé dans un fichier de milliers d'objets), la boîte de sélection teste les boîtes
# englobantes en un calcul groupé, et annuler après la pose de types de ligne ne plante pas.
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
src=open(_os.path.join(_HERE,'t_pushpull.py')).read()
exec(src[src.index("\n")+1:src.index("# ---------------- 1. PushPull")])
import time, random
random.seed(5)
clear()
cols=[]
for i in range(80):
    c=bpy.data.collections.new("L%02d"%i); C.scene.collection.children.link(c); cols.append(c)
    if i%2==0: c.dessin_layer.color=(0.2,0.5,0.9); c.dessin_layer.use_color=True
me=bpy.data.meshes.new("cube"); bm=bmesh.new(); bmesh.ops.create_cube(bm,size=0.5); bm.to_mesh(me); bm.free()
for i in range(3000):
    o=bpy.data.objects.new("M%04d"%i,me); o.location=(random.uniform(-45,45),random.uniform(-45,45),0); cols[i%80].objects.link(o)
for i in range(1000):
    x,y=random.uniform(-45,45),random.uniform(-45,45)
    cu=bpy.data.curves.new("c",'CURVE'); cu.dimensions='3D'; sp=cu.splines.new('POLY'); sp.points.add(1)
    sp.points[0].co=(x,y,0,1); sp.points[1].co=(x+1,y+0.5,0,1)
    o=bpy.data.objects.new("P%04d"%i,cu); cols[i%80].objects.link(o)
C.view_layer.update()
t=time.perf_counter(); m.layer_sync_new_objects(); t1=time.perf_counter()-t
t=time.perf_counter(); m.layer_sync_new_objects(); t2=time.perf_counter()-t
chk("4 000 objets sur 80 calques : couleurs de calque posées sur les nouveaux objets en moins de 0,4 s (avant : plusieurs secondes)", t1<0.4 and t2<0.4, (round(t1,3),round(t2,3)))
o=bpy.data.objects["M0000"]
chk("... et correctement (objet d'un calque coloré : couleur du calque)", tuple(round(x,3) for x in o.color[:3])==(0.2,0.5,0.9) and o.get("wd_lc")==1
    and tuple(bpy.data.objects["M0001"].color)==(1,1,1,1))
cm=m.object_collections_map()
chk("table objet -> calques : la même réponse que users_collection", all([c.name for c in cm.get(q.as_pointer(),())]==[c.name for c in q.users_collection] for q in list(bpy.data.objects)[::97]))
cols[1].dessin_layer.linetype='DASHED'
n=sum(1 for q in cols[1].objects if m.has_lt(q))
chk("type de ligne d'un calque : ses courbes passent en tirets, pas ses solides", n==sum(1 for q in cols[1].objects if q.type=='CURVE') and n>0, n)
t=time.perf_counter(); m.layer_sync_new_objects(); t3=time.perf_counter()-t
chk("... le passage suivant reste rapide", t3<0.4, round(t3,3))
# boîte de sélection
E0=NS(shift=False,ctrl=False,alt=False,oskey=False)
def sel_shape(rect, crossing):
    xmin,ymin,xmax,ymax=rect
    t=time.perf_counter()
    m.select_objects_shape(ctx, area, region, lambda sx,sy:(sx>=xmin)&(sx<=xmax)&(sy>=ymin)&(sy<=ymax),
        lambda ax,ay,bx,by: m._segments_hit_rect(ax,ay,bx,by,xmin,ymin,xmax,ymax), crossing, E0, rect)
    return time.perf_counter()-t, {q.name for q in C.selected_objects}
def brute(rect, crossing):
    xmin,ymin,xmax,ymax=rect; out=set()
    for q in bpy.data.objects:
        if q.type=='MESH':
            P=[scr(*(q.matrix_world@Vector(c)).xy) for c in q.bound_box]
        else:
            P=[scr(*(q.matrix_world@Vector(p.co[:3])).xy) for p in q.data.splines[0].points]
        xs=[p[0] for p in P]; ys=[p[1] for p in P]
        if not crossing:
            if min(xs)>=xmin and max(xs)<=xmax and min(ys)>=ymin and max(ys)<=ymax: out.add(q.name)
        elif q.type=='MESH':
            if not (max(xs)<xmin or min(xs)>xmax or max(ys)<ymin or min(ys)>ymax): out.add(q.name)
    return out
tw,sw=sel_shape((300,300,700,640), False)
chk("boîte fenêtre (gauche à droite) : exactement les objets entièrement dedans", sw==brute((300,300,700,640),False), (len(sw),len(brute((300,300,700,640),False))))
tc,sc_=sel_shape((300,300,700,640), True)
bm_=brute((300,300,700,640),True)
chk("boîte capture : tous les cubes touchés sont pris", {n for n in sc_ if n.startswith("M")}==bm_, (len(sc_),len(bm_)))
chk("... vite sur 4 000 objets (premier passage : la table des boîtes ; ensuite moins de 0,3 s)", tw<1.0 and tc<0.3, (round(tw,3),round(tc,3)))
t0,s0=sel_shape((2,2,6,6), False)
chk("boîte dans le vide : tout est désélectionné", not s0 and not C.selected_objects)
# annuler après la pose de types de ligne (les groupes de nœuds neufs faisaient planter l'annulation de Blender)
bpy.ops.ed.undo_push(message="avant")
ok=True
try:
    bpy.ops.ed.undo(); C.view_layer.update(); bpy.ops.ed.redo(); C.view_layer.update()
except RuntimeError:
    pass
chk("annuler / rétablir après la pose de types de ligne : pas de plantage", ok)
print("RESULTAT",sum(res),"/",len(res))
