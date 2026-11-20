# Plan de coupe : dessiné comme un repère de coupe (trace, triangles aux bouts, carré au centre), pas comme un rectangle
# qu'on confondrait avec les courbes du dessin. « Display As » ne s'applique pas à lui.
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
src=open(_os.path.join(_HERE,'t_pushpull.py')).read()
exec(src[src.index("\n")+1:src.index("# ---------------- 1. PushPull")])
import types
G = m.clip_plane_coeffs.__globals__
clear()
o,r=start(m.DESSIN_OT_clip_plane); E(o,('c',0,0),('c',8,4))
cl=[q for q in bpy.data.objects if q.get("cad_clip")]
chk("le plan de coupe est créé", len(cl)==1, [q.name for q in bpy.data.objects])
P=cl[0]; me=P.data
chk("repère de coupe : aucune face (rien à confondre avec une surface), 11 traits (trace, carré, 2 triangles)",
    len(me.polygons)==0 and len(me.edges)==11 and P.get("cad_clip_v")==2, (len(me.polygons), len(me.edges)))
c=m.clip_plane_coeffs(P)
ctr=P.matrix_world.translation
chk("le plan passe par le centre du rectangle tracé (4, 2) et reste celui de la vue (normale Z)",
    (ctr-Vector((4,2,0))).length<1e-6 and abs(abs(c[2])-1)<1e-9 and abs(c[0])<1e-9 and abs(c[1])<1e-9 and abs(c[3])<1e-6, (tuple(ctr), c))
W=[P.matrix_world @ v.co for v in me.vertices]
xs=[w.x for w in W]
chk("la trace couvre la largeur tracée (de x=0 à x=8)", abs(min(xs)-0)<1e-6 and abs(max(xs)-8)<1e-6, (min(xs),max(xs)))
loc=[v.co for v in me.vertices]
tri=[v for v in loc[6:]]
sq=[v for v in loc[2:6]]
chk("comme Rhino : les triangles sont dans le plan de coupe (z local = 0, pointe vers +y local), le carré en travers (y local = 0)",
    all(abs(v.z)<1e-12 and v.y>=-1e-12 for v in tri) and max(v.y for v in tri)>1e-3 and all(abs(v.y)<1e-12 for v in sq)
    and max(abs(v.z) for v in sq)>1e-3, [tuple(v) for v in tri])
# retourner : l'autre côté
G['bpy'].ops  # (module chargé)
W0y=(P.matrix_world.to_3x3()@Vector((0,1,0))).copy()
op=make(m.DESSIN_OT_clip_edit); op.name=P.name; op.action='FLIP'; type(op).execute(op,ctx); C.view_layer.update()
c2=m.clip_plane_coeffs(P)
chk("Flip : le côté masqué s'inverse (plan identique, normale opposée)", all(abs(a+b)<1e-6 for a,b in zip(c,c2)), (c,c2))
chk("... le repère reste en place et ses triangles gardent leur sens (demi-tour autour de leur axe)", (P.matrix_world.translation-ctr).length<1e-9
    and (P.matrix_world.to_3x3()@Vector((0,1,0))-W0y).length<1e-6)
# plan vertical (tracé dans une vue de face) : la trace est horizontale
w,h,n=G['clip_frame'](Vector((0,1,0)))
chk("plan vertical : la trace est horizontale (vue de dessus, on voit la trace et les triangles)", abs(w.z)<1e-12 and abs(w.length-1)<1e-12
    and abs(w.cross(h).dot(n)-1)<1e-12, (tuple(w),tuple(h)))
# le plan suit l'objet (Gizmo, Rotate)
P.rotation_euler.x += math.pi/2; C.view_layer.update()
c3=m.clip_plane_coeffs(P)
chk("tourner l'objet tourne le plan de coupe", abs(c3[2])<1e-6 and abs(abs(c3[1])-1)<1e-6, c3)
# anciens plans (rectangle avec une face) : toujours lus
me2=bpy.data.meshes.new("old"); me2.from_pydata([(0,0,0),(1,0,0),(1,1,0),(0,1,0),(0.5,0.5,0),(0.5,0.5,0.3)],[(4,5)],[(0,1,2,3)])
old=bpy.data.objects.new("OldClip",me2); C.collection.objects.link(old); old["cad_clip"]=1; C.view_layer.update()
c4=m.clip_plane_coeffs(old)
chk("anciens plans de coupe (rectangle) : toujours appliqués", c4 is not None and abs(abs(c4[2])-1)<1e-9, c4)
# Display As
for q in bpy.data.objects: q.select_set(q==P)
C.view_layer.objects.active=P
class Lay:
    def __init__(s): s.order=[]
    def operator(s, idname, **k): s.order.append(idname); return NS()
    def menu(s, idname, **k): s.order.append(idname)
    def separator(s): pass
L=Lay(); m.ctx_extra_items(L, C)
chk("clic droit sur un plan de coupe : pas de « Display As »", "DESSIN_MT_ctx_display" not in L.order and "DESSIN_MT_ctx_select" in L.order, L.order)
bx=box(); C.view_layer.update()
for q in bpy.data.objects: q.select_set(q==bx)
L=Lay(); m.ctx_extra_items(L, C)
chk("... sur un autre objet : Display As comme avant", "DESSIN_MT_ctx_display" in L.order, L.order)
for q in bpy.data.objects: q.select_set(q in (bx,P))
op=make(m.DESSIN_OT_display_as); op.type='SOLID'; type(op).execute(op,ctx)
chk("Display As sur une sélection qui contient un plan de coupe : le plan reste en filaire", P.display_type=='WIRE' and bx.display_type=='SOLID', (P.display_type,bx.display_type))
# contours : le repère n'est pas un contour du dessin
H = m.DESSIN_OT_hatch_region.collect_loops.__globals__
paths=H['_hatch_paths_of'](C,[P])
chk("Hatch Region / Boundary : le repère de coupe n'est pas pris comme contour", paths==[], len(paths))
# plan de coupe fait avec la version précédente du repère : redessiné tout seul
me3=bpy.data.meshes.new("v2"); V2,E2=G['clip_symbol_geometry'](3.0); me3.from_pydata([(x,0.0,-y) if y else (x,0.0,z) for x,y,z in V2],E2,[])
P2=bpy.data.objects.new("Clip v2",me3); C.collection.objects.link(P2); P2["cad_clip"]=1; P2["cad_clip_v"]=2; C.view_layer.update()
m.update_clip_planes()
chk("plan de coupe dessiné par la version précédente : redessiné au nouveau repère, même taille",
    P2.get("cad_clip_sym")==3 and max(abs(v.co.x) for v in P2.data.vertices)==3.0 and max(v.co.y for v in P2.data.vertices)>0.1)
seg=m.clip_symbol_segments(P)
chk("le dessin par-dessus (hors coupe) reprend tous les traits du repère", len(seg)==22, len(seg))
print("RESULTAT",sum(res),"/",len(res))
