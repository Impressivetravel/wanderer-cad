import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
import traceback, json, numpy as np
for o in list(bpy.data.objects): bpy.data.objects.remove(o)
C=bpy.context
res=[]
def chk(name,ok,info=""):
    res.append(bool(ok)); print(("OK  " if ok else "BAD ")+name, info)
def run(cls,pts,keys=(),esc=True):
    o=make(cls); cls=type(o); cls.invoke(o,ctx,ev('NONE','NOTHING',*scr(*pts[0])))
    for p in pts:
        if p=='D': cls.modal(o,ctx,ev('D','PRESS',0,0)); continue
        sx,sy=scr(*p)
        for e in (ev('MOUSEMOVE','NOTHING',sx,sy),ev('LEFTMOUSE','PRESS',sx,sy),ev('LEFTMOUSE','RELEASE',sx,sy)):
            cls.modal(o,ctx,e)
    if esc: cls.modal(o,ctx,ev('ESC','PRESS',0,0))
    return o
def dims():
    return [o for o in bpy.data.objects if o.type=='CURVE' and 'dessin_dim' in o.keys()]
def texts(): return sorted(c.data.body for d in dims() for c in d.children)
# base linear dim 0->10 at y=-3
run(m.DESSIN_OT_cotation,[(0,0),(10,0),(5,-3)])
chk("cote de base", texts()==['1000.00'], texts())
# continue: click dim line then points 15, 22
run(m.DESSIN_OT_cotation_chain,[(5,-3),(15,0),(22,0)])
chk("cote continue (10->15, 15->22)", sorted(texts())==sorted(['1000.00','500.00','700.00']), texts())
lines=[]
for d in dims():
    dd=json.loads(d['dessin_dim']); lines.append(round(dd['cur'][1],3))
chk("même ligne de cote", len(set(lines))==1, lines)
# baseline
for d in dims()[1:]: bpy.data.objects.remove(d)
for o in list(bpy.data.objects):
    if o.type=='FONT' and o.parent is None: bpy.data.objects.remove(o)
run(m.DESSIN_OT_cotation_chain,[(5,-3),'D',(15,0),(22,0)])
ys=sorted(round(json.loads(d['dessin_dim'])['cur'][1],2) for d in dims())
chk("ligne de base : 3 lignes décalées", len(set(ys))==3, (texts(),ys))
# ordinate
for o in list(bpy.data.objects): bpy.data.objects.remove(o)
run(m.DESSIN_OT_cotation_ordinate,[(0,0),(7,3),(7,9),(4,5),(10,5)])
chk("ordonnées X=7 puis Y=5", texts()==sorted(['700.00','500.00']), texts())
# arc length
for o in list(bpy.data.objects): bpy.data.objects.remove(o)
A=m.build_bezier_arc(C,"Arc",Vector((0,0,0)),Vector((1,0,0)),Vector((0,1,0)),5.0,0.0,math.pi/2,False)
C.view_layer.update()
a45=(5*math.cos(math.pi/4),5*math.sin(math.pi/4))
o=run(m.DESSIN_OT_cotation_arc,[a45,(6.5,6.5)])
exp=f"{5*math.pi/2*100:.2f}"
chk("longueur d'arc 90° r5", exp in texts(), (texts(),exp))
# text override + restyle keep
d=dims()[0]; C.view_layer.objects.active=d; d.select_set(True)
d.dessin_dim.text="<> TYP"
chk("texte personnalisé", any(t.endswith(" TYP") for t in texts()), texts())
C.scene.dessin.decimales=0
chk("restyle garde le texte perso", texts()==[f"{5*math.pi/2*100:.0f} TYP"], texts())
C.scene.dessin.decimales=2
# move dim line
for o in list(bpy.data.objects): bpy.data.objects.remove(o)
run(m.DESSIN_OT_cotation,[(0,0),(10,0),(5,-3)])
run(m.DESSIN_OT_cotation_edit,[(5,-3),(5,-8)])
d=dims()[0]; ys=[ (d.matrix_world@Vector(p.co[:3])).y for sp in d.data.splines for p in sp.points]
chk("ligne de cote déplacée à y=-8", abs(min(ys)+8.9)<0.05 and len(dims())==1, (round(min(ys),2),len(dims())))
print("RESULTAT",sum(res),"/",len(res))
