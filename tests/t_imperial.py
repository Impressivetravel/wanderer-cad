# Unités impériales : saisie 10' 6 1/2", 10'6-1/2", 10'6+1/2", 6-1/2", 1/2" ; cotes écrites 10' - 6 1/2"
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
src=open(_os.path.join(_HERE,'t_pushpull.py')).read()
exec(src[src.index("\n")+1:src.index("# ---------------- 1. PushPull")])
import sys
u=[v for k,v in sys.modules.items() if k.endswith(".units_text")][0]
st=C.scene.dessin; st.ortho=False; st.polar=False
us=C.scene.unit_settings
I=0.0254
# ---- 1. lecture des longueurs (scène en pieds)
us.system='IMPERIAL'; us.length_unit='FEET'; us.scale_length=1.0
uf=m.unit_info(C.scene)[0]
for txt,inch in (("10' 6 1/2\"",126.5),("10'6-1/2\"",126.5),("10'6+1/2\"",126.5),("10' - 6 1/2\"",126.5),("10'",120),("6\"",6),("6-1/2\"",6.5),("1/2\"",0.5),("-10'6\"",-126),("10.5",126)):
    v=m.typed_length(txt,uf)
    chk(f"saisie {txt} = {inch} pouces", v is not None and abs(v-inch*I)<1e-9, v)
# ---- 2. une polyligne de 10' 6 1/2" tapée au clavier
def poly(name,pts,closed=False): return m.build_polyline(C,name,[Vector(p) for p in pts],closed)
clear()
o,r=start(m.DESSIN_OT_polyligne); E(o,('c',0,0),('m',5,0))
for ch in "10' 6 1/2\"":
    with contextlib.redirect_stdout(io.StringIO()):
        type(o).modal(o,ctx,ev('SPACE' if ch==' ' else 'A','PRESS',*scr(5,0),unicode=ch,ascii=ch))
chk("touches 1 0 ' espace 6 espace 1 / 2 \" : tout est dans la saisie (l'espace ne valide pas)", o.typed[0]=="10' 6 1/2\"", o.typed)
E(o,'RET','RET'); C.view_layer.update()
cv=[q for q in bpy.data.objects if q.type=='CURVE']
P=[q.matrix_world@Vector(p.co[:3]) for q in cv for sp in q.data.splines for p in sp.points]
chk("polyligne : 2e point à 126,5 pouces (3,2131 m)", len(P)==2 and abs((P[1]-P[0]).length-126.5*I)<1e-6, [tuple(round(x,5) for x in p) for p in P])
# ---- 3. hors impérial : le moins garde son rôle, l'espace valide
us.system='METRIC'; us.length_unit='MILLIMETERS'
o,r=start(m.DESSIN_OT_polyligne); E(o,('c',0,0),('m',5,0))
for ch in "12":
    with contextlib.redirect_stdout(io.StringIO()): type(o).modal(o,ctx,ev('A','PRESS',*scr(5,0),unicode=ch,ascii=ch))
chk("métrique : 12- ne met pas le moins dans la saisie", not o.handle_typing(ev('MINUS','PRESS',*scr(5,0),unicode='-',ascii='-')) and o.typed[0]=="12", o.typed)
chk("métrique : l'espace n'entre pas dans la saisie (il valide)", not o.handle_typing(ev('SPACE','PRESS',*scr(5,0),unicode=' ',ascii=' ')))
chk("métrique : 1\" tapé = 25,4 mm", abs(m.typed_length('1"', m.unit_info(C.scene)[0])-0.0254)<1e-12)
E(o,'ESC','ESC')
# ---- 4. coordonnées
us.system='IMPERIAL'; us.length_unit='FEET'
r=m.parse_coord("@10'6\",2'", m.unit_info(C.scene)[0], 0.3048)
chk("coordonnées @10'6\",2' : (126 po, 24 po)", r is not None and abs(r[1][0]-126*I)<1e-9 and abs(r[1][1]-24*I)<1e-9, r)
r=m.parse_coord("10'6\"<90", m.unit_info(C.scene)[0], 0.3048)
chk("polaire 10'6\"<90", r is not None and abs(r[1][1]-126*I)<1e-9, r)
# ---- 5. écriture des cotes
st.unite_cote='SCENE'; st.decimales=4; st.prefixe=""; st.suffixe=""
o=make(m.DESSIN_OT_cotation); o.unit_f, o.unit_label = m.unit_info(C.scene)
chk("cote, scène en pieds : 10' - 6 1/2\"", o.text_for(126.5*I)=="10' - 6 1/2\"", o.text_for(126.5*I))
chk("cote : 1/16\" près : 10' - 6 3/16\"", o.text_for((126+3/16)*I)=="10' - 6 3/16\"", o.text_for((126+3/16)*I))
chk("cote : 11 63/64\" arrondi à 1' - 0\"", o.text_for(11.99*I)=="1' - 0\"", o.text_for(11.99*I))
us.length_unit='INCHES'
chk("cote, scène en pouces : 126 1/2\"", o.text_for(126.5*I)=="126 1/2\"", o.text_for(126.5*I))
st.unite_cote='FEET'; us.system='METRIC'; us.length_unit='METERS'
chk("réglage Feet and inches dans une scène métrique", o.text_for(126.5*I)=="10' - 6 1/2\"", o.text_for(126.5*I))
st.decimales=1
chk("précision 1 : demi-pouce", o.text_for((126+3/16)*I)=="10' - 6\"", o.text_for((126+3/16)*I))
st.unite_cote='CENTIMETERS'; st.decimales=2
chk("cote en centimètres : inchangée", o.text_for(1.0)=="100.00", o.text_for(1.0))

# ---- 6. #14 : 10+6+1/2 (pieds + pouces + fraction, tout au pavé numérique)
us.system='IMPERIAL'; us.length_unit='FEET'
uf=m.unit_info(C.scene)[0]
for txt,inch in (("10+6+1/2",126.5),("10+6",126),("10+1/2",120.5),("0+6",6),("-10+6",-126),("10+6.5",126.5)):
    v=m.typed_length(txt,uf)
    chk(f"imperial : {txt} = {inch} pouces", v is not None and abs(v-inch*I)<1e-9, v)
chk("10+6+1+1/2 (trop de +) : refusé", m.typed_length("10+6+1+1/2",uf) is None)
def typ(t):
    out=""
    for c in t:
        n=u.typing_add(out,c)
        if n is None: return out+"|refusé:"+c
        out=n
    return out
chk("frappe 10+6+1/2 acceptée touche par touche", typ("10+6+1/2")=="10+6+1/2", typ("10+6+1/2"))
chk("frappe : un troisième + refusé", typ("10+6+1+")=="10+6+1|refusé:+", typ("10+6+1+"))
o,r=start(m.DESSIN_OT_polyligne); E(o,('c',0,0),('m',5,0))
for ch in "10+6+1/2":
    with contextlib.redirect_stdout(io.StringIO()):
        type(o).modal(o,ctx,ev('NUMPAD_PLUS' if ch=='+' else 'A','PRESS',*scr(5,0),unicode=ch,ascii=ch))
chk("polyligne : 10+6+1/2 tapé (+ du pavé numérique) dans la saisie", o.typed[0]=="10+6+1/2", o.typed)
chk("... et lu comme 126,5 pouces", o.typed_value(0) is not None and abs(o.typed_value(0)-126.5*I)<1e-9, o.typed_value(0))
E(o,'ESC','ESC')
us.system='METRIC'; us.length_unit='MILLIMETERS'
chk("métrique : 10+6 n'est pas une longueur (pas de pieds en métrique)", m.typed_length("10+6", m.unit_info(C.scene)[0]) is None)
print("RESULTAT",sum(res),"/",len(res))
