import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
import traceback, numpy as np, bmesh
C=bpy.context
res=[]
def chk(name,ok,info=""):
    res.append(bool(ok)); print(("OK  " if ok else "BAD ")+name, info)
for o in list(bpy.data.objects): bpy.data.objects.remove(o)
def run(cls,pts):
    o=make(cls); cls=type(o); r=cls.invoke(o,ctx,ev('NONE','NOTHING',*scr(*pts[0])))
    for p in pts:
        if p=='D': cls.modal(o,ctx,ev('D','PRESS',0,0)); continue
        sx,sy=scr(*p)
        for e in (ev('MOUSEMOVE','NOTHING',sx,sy),ev('LEFTMOUSE','PRESS',sx,sy),ev('LEFTMOUSE','RELEASE',sx,sy)):
            r=cls.modal(o,ctx,e)
    cls.modal(o,ctx,ev('ESC','PRESS',0,0)); return o
# objects: a square polyline + a mesh box
sq=m.build_polyline(C,"Sq",[Vector(p) for p in [(0,0,0),(2,0,0),(2,2,0),(0,2,0)]],True)
me=bpy.data.meshes.new("Bx"); bm=bmesh.new(); bmesh.ops.create_cube(bm,size=1); bm.to_mesh(me); bm.free()
bx=bpy.data.objects.new("Bx",me); C.scene.collection.objects.link(bx); bx.location=(1,1,0.5)
C.view_layer.update()
for o in C.view_layer.objects: o.select_set(True)
run(m.DESSIN_OT_block,[(0,0)])
defs=m.block_defs()
chk("Block : définition créée", len(defs)==1 and len(defs[0].objects)==2, [d.name for d in defs])
insts=[o for o in bpy.data.objects if m.is_block_instance(o)]
chk("Block : une instance à la place", len(insts)==1 and tuple(insts[0].location)==(0,0,0), [(o.name,tuple(o.location)) for o in insts])
chk("Block : objets d'origine plus dans la vue", "Sq" not in C.view_layer.objects and "Bx" not in C.view_layer.objects)
# insert 2 copies
C.scene.dessin.block_insert=defs[0].name
run(m.DESSIN_OT_block_insert,[(10,0),(20,5)])
insts=[o for o in bpy.data.objects if m.is_block_instance(o)]
chk("Insert : 2 copies de plus", len(insts)==3, sorted(tuple(round(c,2) for c in o.location) for o in insts))
# snap on instance geometry: corner (12,2) of copy at (10,0)
d=m.collect_snap_points(C)
pts={tuple(np.round(p,3)) for p in d[0]}
chk("Accrochage sur la géométrie d'un bloc", (12.0,2.0,0.0) in pts and (22.0,7.0,0.0) in pts, len(pts))
# block edit: edit the copy at (10,0): move the square's 2nd point
inst=[o for o in insts if tuple(o.location)==(10,0,0)][0]
for o in C.view_layer.objects: o.select_set(False)
inst.select_set(True); C.view_layer.objects.active=inst
op=make(m.DESSIN_OT_block_edit); print(type(op).execute(op,ctx), op._reports)
ed=bpy.data.collections.get(m.block_edit_state()["col"])
cp=[o for o in ed.objects if o.type=='CURVE'][0]
chk("BlockEdit : copie éditable sur place", abs((cp.matrix_world@Vector(cp.data.splines[0].points[1].co[:3])).x-12)<1e-6, (cp.matrix_world@Vector(cp.data.splines[0].points[1].co[:3])))
cp.data.splines[0].points[2].co=(3,3,0,1)      # shared data: all copies change
# move the box copy by +1 in x (object transform) and add a new object
bxc=[o for o in ed.objects if o.type=='MESH'][0]; bxc.location.x+=1
newo=m.build_polyline(C,"New",[Vector(p) for p in [(10,0,0),(10,-3,0)]],False)
C.view_layer.update()
chk("BlockEdit : nouvel objet dans la collection d'édition", newo.name in ed.objects, [c.name for c in newo.users_collection])
op=make(m.DESSIN_OT_block_edit_close); print(type(op).execute(op,ctx), op._reports)
D=defs[0]
names=sorted(o.name for o in D.objects)
chk("Close : nouvel objet ajouté au bloc", len(names)==3, names)
bx0=[o for o in D.objects if o.type=='MESH'][0]
chk("Close : déplacement repris dans la définition", abs(bx0.matrix_world.translation.x-2)<1e-6, tuple(bx0.matrix_world.translation))
C.view_layer.update(); d=m.collect_snap_points(C); pts={tuple(np.round(p,3)) for p in d[0]}
chk("Toutes les copies suivent (point modifié 3,3 dans la copie à 20,5)", (23.0,8.0,0.0) in pts and (20.0,2.0,0.0) in pts, None)
# explode
inst=[o for o in bpy.data.objects if m.is_block_instance(o) and tuple(o.location)==(20,5,0)][0]
for o in C.view_layer.objects: o.select_set(False)
inst.select_set(True)
op=make(m.DESSIN_OT_block_explode); type(op).execute(op,ctx)
sel=[o for o in C.selected_objects]
chk("Explode : 3 objets réels à la place de la copie", len(sel)==3 and all(not m.is_block_instance(o) for o in sel), [(o.name, tuple(round(c,2) for c in o.matrix_world.translation)) for o in sel])
cv=[o for o in sel if o.type=='CURVE' and len(o.data.splines[0].points)==4][0]
chk("Explode : données indépendantes", cv.data is not D.objects[[o.name for o in D.objects].index(next(o.name for o in D.objects if o.type=='CURVE' and len(o.data.splines[0].points)==4))].data)
print("RESULTAT",sum(res),"/",len(res))
class L:
    def __getattr__(self,k): return lambda *a,**kw: L()
    alert=False
class P: layout=L()
m.DESSIN_PT_blocks.draw(P(),C); print("panel blocks ok")
