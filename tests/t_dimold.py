import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
import traceback, json
for o in list(bpy.data.objects): bpy.data.objects.remove(o)
C=bpy.context
res=[]
def chk(name,ok,info=""):
    res.append(bool(ok)); print(("OK  " if ok else "BAD ")+name, info)
def run(cls,pts,esc=True):
    o=make(cls); cls=type(o); cls.invoke(o,ctx,ev('NONE','NOTHING',*scr(*pts[0])))
    for p in pts:
        sx,sy=scr(*p)
        for e in (ev('MOUSEMOVE','NOTHING',sx,sy),ev('LEFTMOUSE','PRESS',sx,sy),ev('LEFTMOUSE','RELEASE',sx,sy)):
            cls.modal(o,ctx,e)
    if esc: cls.modal(o,ctx,ev('ESC','PRESS',0,0))
    return o
def dims():
    return [o for o in bpy.data.objects if o.type=='CURVE' and 'dessin_dim' in o.keys()]
def texts(): return sorted(c.data.body for d in dims() for c in d.children)

st = C.scene.dessin

# --- 1. la table des classes accepte les deux écritures ---
tbl = m.settings._dim_classes()
chk("table des classes : bl_idname présents",
    all(k in tbl for k in ("dessin.cotation","dessin.cotation_rayon","dessin.cotation_angle",
                           "dessin.cotation_ordinate","dessin.cotation_arc")), sorted(tbl))
chk("table des classes : noms de classe présents",
    all(k in tbl for k in ("DESSIN_OT_cotation","DESSIN_OT_cotation_rayon","DESSIN_OT_cotation_angle",
                           "DESSIN_OT_cotation_ordinate","DESSIN_OT_cotation_arc")), sorted(tbl))
chk("les deux écritures pointent la même classe",
    tbl["dessin.cotation"] is tbl["DESSIN_OT_cotation"] and
    tbl["dessin.cotation_angle"] is tbl["DESSIN_OT_cotation_angle"])

# --- 2. cote linéaire : ancien format rejoué ---
run(m.DESSIN_OT_cotation,[(0,0),(10,0),(5,-3)])
chk("cote linéaire posée", texts()==['1000.00'], texts())
d = dims()[0]
data = json.loads(d['dessin_dim'])
chk("format courant = bl_idname", data['cls']=='dessin.cotation', data['cls'])

# on réécrit la définition comme le faisait l'ancienne version
old = dict(data); old['cls'] = 'DESSIN_OT_cotation'
d['dessin_dim'] = json.dumps(old)
spec = m.settings._dim_replay_spec(old)
chk("ancien format (DESSIN_OT_cotation) rejoué", spec is not None and spec[0]=='dim', spec[0] if spec else None)

# le style change : la cote doit se reconstruire malgré l'ancien format
st.decimales = 1
chk("reconstruction d'une cote ancienne après changement de style", texts()==['1000.0'], texts())
chk("la définition ancienne est conservée telle quelle",
    json.loads(dims()[0]['dessin_dim'])['cls']=='DESSIN_OT_cotation', json.loads(dims()[0]['dessin_dim'])['cls'])
st.decimales = 2
chk("retour au style précédent", texts()==['1000.00'], texts())

# --- 3. idem pour une cote d'angle ---
for o in list(bpy.data.objects): bpy.data.objects.remove(o)
run(m.DESSIN_OT_cotation_angle,[(0,0),(10,0),(0,10),(4,4)])
dd = dims()
chk("cote d'angle posée", len(dd)==1 and texts()==['90.00°'], texts())
a = dd[0]
da = json.loads(a['dessin_dim']); da['cls'] = 'DESSIN_OT_cotation_angle'
a['dessin_dim'] = json.dumps(da)
st.decimales = 1
chk("cote d'angle ancienne reconstruite", texts()==['90.0°'], texts())
st.decimales = 2

# --- 4. une définition inconnue reste sans effet (pas de plantage) ---
bad = dict(da); bad['cls'] = 'DESSIN_OT_inexistante'
chk("classe inconnue : None, pas d'exception", m.settings._dim_replay_spec(bad) is None)

# --- 5. non-régression : rebuild_all_dimensions passe sur les deux formats ---
for o in list(bpy.data.objects): bpy.data.objects.remove(o)
run(m.DESSIN_OT_cotation,[(0,0),(10,0),(5,-3)])
run(m.DESSIN_OT_cotation,[(0,0),(6,0),(3,-6)])
objs = dims()
o0 = json.loads(objs[0]['dessin_dim']); o0['cls']='DESSIN_OT_cotation'
objs[0]['dessin_dim']=json.dumps(o0)
ok = True
try:
    st.decimales = 0
except Exception:
    ok = False; traceback.print_exc()
chk("deux formats mélangés reconstruits ensemble", ok and sorted(texts())==sorted(['1000','600']), texts())
st.decimales = 2

print(f"\n{sum(res)}/{len(res)} OK")
raise SystemExit(0 if all(res) else 1)
