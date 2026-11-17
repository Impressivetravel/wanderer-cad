import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
# Courbes sélectionnées dessinées par-dessus les surfaces (Rhino) : le tracé est relu en monde, segment par segment
res=[]
def chk(n,ok,info=""): res.append(bool(ok)); print(("OK  " if ok else "BAD ")+n, info)
for _o in list(bpy.data.objects): bpy.data.objects.remove(_o)
cu = bpy.data.curves.new("R", 'CURVE'); cu.dimensions = '3D'
sp = cu.splines.new('POLY'); sp.points.add(3)
for i, (x, y) in enumerate(((0, 0), (2, 0), (2, 1), (0, 1))): sp.points[i].co = (x, y, 0, 1)
sp.use_cyclic_u = True
o = bpy.data.objects.new("R", cu); bpy.context.scene.collection.objects.link(o); o.location = (10, 0, 5)
bpy.context.view_layer.update()
segs = m.selected_curve_segments([o])
co = segs[0][1] if segs else None
chk("rectangle fermé : 4 segments (8 extrémités)", co is not None and len(co) == 8, None if co is None else len(co))
chk("... en coordonnées du monde (déplacé en (10, 0, 5))", co is not None and abs(float(co[:, 0].min()) - 10) < 1e-5 and abs(float(co[:, 2].mean()) - 5) < 1e-5)
sel, act = m.curve_selection_color()
chk("couleurs de sélection du thème (sélectionné, actif)", len(sel) == 4 and len(act) == 4)
print("RESULTAT", sum(res), "/", len(res))
