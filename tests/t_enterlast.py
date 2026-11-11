# « Entrée = dernière valeur » : Entrée sans rien taper reprend la dernière valeur saisie dans l'outil (comme le <défaut> de Rhino)
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
src=open(_os.path.join(_HERE,'t_pushpull.py')).read()
exec(src[src.index("\n")+1:src.index("# ---------------- 1. PushPull")])
def curves(): return [o for o in bpy.data.objects if o.type=='CURVE']
def dims(o):
    C.view_layer.update(); bb=[o.matrix_world@Vector(b) for b in o.bound_box]
    return tuple(round(max(v[i] for v in bb)-min(v[i] for v in bb),4) for i in range(3))
def ctr(o):
    bb=[o.matrix_world@Vector(b) for b in o.bound_box]
    return tuple(round((max(v[i] for v in bb)+min(v[i] for v in bb))/2,4) for i in range(3))
def sel(*objs):
    for q in bpy.data.objects: q.select_set(q in objs)
    C.view_layer.objects.active=objs[0] if objs else None; C.view_layer.update()
m._LAST_TYPED.clear()

# ---------------- cercle ----------------
clear(); o,r=start(m.DESSIN_OT_cercle); r=E(o,('c',0,0),('m',3,0),'RET')
chk("première utilisation, rien de mémorisé : Entrée quitte l'outil sans rien créer (comme avant)", not curves() and ('FINISHED' in r or 'CANCELLED' in r), r)
clear(); o,r=start(m.DESSIN_OT_cercle); r=E(o,('c',0,0),('m',3,0),('t','2.5'),'RET')
chk("cercle : rayon tapé 2,5", len(curves())==1 and dims(curves()[0])[:2]==(5.0,5.0), [dims(c) for c in curves()])
clear(); o,r=start(m.DESSIN_OT_cercle); r=E(o,('c',10,0),('m',11,0),'RET')
chk("cercle suivant : Entrée sans saisie reprend 2,5", len(curves())==1 and dims(curves()[0])[:2]==(5.0,5.0) and ctr(curves()[0])[:2]==(10.0,0.0), [dims(c) for c in curves()])
clear(); o,r=start(m.DESSIN_OT_cercle); r=E(o,('c',0,0),('m',4,0),('c',4,0))
chk("... un clic prend toujours la valeur sous la souris (rayon 4)", len(curves())==1 and dims(curves()[0])[:2]==(8.0,8.0), [dims(c) for c in curves()])
clear(); o,r=start(m.DESSIN_OT_cercle); r=E(o,('c',0,0),('m',4,0),'SPACE')
chk("... Espace vaut Entrée", len(curves())==1 and dims(curves()[0])[:2]==(5.0,5.0), [dims(c) for c in curves()])
clear(); o,r=start(m.DESSIN_OT_cercle); r=E(o,('c',0,0),('m',4,0),('t','1.5'),('c',4,0))
clear(); o,r=start(m.DESSIN_OT_cercle); r=E(o,('c',0,0),('m',4,0),'RET')
chk("valeur tapée puis validée d'un clic : retenue elle aussi (1,5)", len(curves())==1 and dims(curves()[0])[:2]==(3.0,3.0), [dims(c) for c in curves()])
m.PREF_DEFAULTS["enter_last"]=False
clear(); o,r=start(m.DESSIN_OT_cercle); r=E(o,('c',0,0),('m',3,0),'RET')
chk("préférence coupée : Entrée quitte l'outil comme avant", not curves(), r)
m.PREF_DEFAULTS["enter_last"]=True

# ---------------- rectangle (deux champs) ----------------
clear(); o,r=start(m.DESSIN_OT_rectangle); r=E(o,('c',0,0),('m',5,5),('t','4'),'TAB',('t','2'),'RET')
chk("rectangle : 4 x 2 tapé", len(curves())==1 and dims(curves()[0])[:2]==(4.0,2.0), [dims(c) for c in curves()])
clear(); o,r=start(m.DESSIN_OT_rectangle); r=E(o,('c',0,0),('m',-5,-5),'RET')
chk("rectangle suivant : Entrée reprend 4 x 2, dans le quadrant de la souris", len(curves())==1 and dims(curves()[0])[:2]==(4.0,2.0) and ctr(curves()[0])[:2]==(-2.0,-1.0), [(dims(c),ctr(c)) for c in curves()])
clear(); o,r=start(m.DESSIN_OT_cercle); r=E(o,('c',0,0),('m',3,0),'RET')
chk("la mémoire est par outil : le cercle garde 1,5", len(curves())==1 and dims(curves()[0])[:2]==(3.0,3.0), [dims(c) for c in curves()])

# ---------------- polyligne : Entrée termine toujours le tracé ----------------
clear(); o,r=start(m.DESSIN_OT_polyligne); r=E(o,('c',0,0),('m',5,0),('t','3'),'RET',('c',3,4),'RET')
n1=len(curves()[0].data.splines[0].points) if curves() else 0
clear(); o,r=start(m.DESSIN_OT_polyligne); r=E(o,('c',0,0),('c',5,0),('c',5,5),('m',9,9),'RET')
n2=len(curves()[0].data.splines[0].points) if curves() else 0
chk("polyligne : Entrée termine le tracé sans ajouter de segment (3 points)", len(curves())==1 and n2==3, (n1,n2))

# ---------------- Move ----------------
clear(); b=box(size=2,loc=(0,0,1)); sel(b)
o,r=start(m.DESSIN_OT_deplacer); r=E(o,('c',0,0),('m',5,0),('t','3'),'RET')
chk("Move : distance tapée 3 vers +X", abs(b.location.x-3)<1e-6 and abs(b.location.y)<1e-6, tuple(b.location))
sel(b); o,r=start(m.DESSIN_OT_deplacer); r=E(o,('c',20,20),('m',20,26),'RET')
chk("Move suivant : Entrée reprend 3, dans la direction de la souris (+Y)", abs(b.location.x-3)<1e-6 and abs(b.location.y-3)<1e-6, tuple(b.location))

# ---------------- Extrude Curve ----------------
def prof():
    clear(); m._OPT_MEM.clear()
    c=m.build_polyline(C,"Prof",[Vector(p) for p in [(0,0,0),(2,0,0),(2,1,0),(0,1,0)]],True); sel(c); return c
def exth():
    ex=[q for q in bpy.data.objects if q.name!="Prof"]
    return dims(ex[0])[2] if ex else None
prof(); o,r=start(m.DESSIN_OT_extrude_crv); r=E(o,('c',0,0),('t','3'),'RET')
chk("Extrude Curve : hauteur tapée 3", exth()==3.0, exth())
prof(); o,r=start(m.DESSIN_OT_extrude_crv); r=E(o,('c',0,0),'RET')
chk("Extrude Curve suivant : Entrée reprend 3", exth()==3.0, exth())

# ---------------- PushPull ----------------
def pp(evs):
    clear(); b=box(); C.view_layer.update()
    o=make(m.DESSIN_OT_pushpull)
    with contextlib.redirect_stdout(io.StringIO()):
        r=type(o).invoke(o,ctx,ev('NONE','NOTHING',*scr(0,0)))
        for e in evs:
            if e[0]=='c': seq=[ev('MOUSEMOVE','NOTHING',*scr(e[1],e[2])),ev('LEFTMOUSE','PRESS',*scr(e[1],e[2])),ev('LEFTMOUSE','RELEASE',*scr(e[1],e[2]))]
            elif e[0]=='t': seq=[ev(K[ch],'PRESS',*scr(0,0),unicode=ch,ascii=ch) for ch in e[1]]
            else: seq=[ev(e[0],'PRESS',*scr(0,0))]
            for x in seq:
                r=type(o).modal(o,ctx,x)
                if 'FINISHED' in r or 'CANCELLED' in r: return r,b
    return r,b
r,b=pp([('c',0,0),('t','1.5'),('RET',)]); s=stats(b)
chk("PushPull : distance tapée 1,5 (volume 64+24)", abs(s["vol"]-88)<1e-4 and solid_ok(s), (r,s))
r,b=pp([('c',0,0),('RET',)]); s=stats(b)
chk("PushPull suivant : Entrée reprend 1,5", abs(s["vol"]-88)<1e-4 and solid_ok(s), (r,s))

# ---------------- Gumball : clic sur une flèche, puis Entrée ----------------
st=C.scene.dessin
def gb(evs):
    clear(); b=box(size=2,loc=(0,0,1)); sel(b)
    o=make(m.DESSIN_OT_gumball); o.kind='MOVE'; o.axis=0
    with contextlib.redirect_stdout(io.StringIO()):
        r=type(o).invoke(o,ctx,ev('LEFTMOUSE','PRESS',*scr(0,0)))
        if 'RUNNING_MODAL' not in r: return r,b
        for e in evs:
            if e[0]=='t': seq=[ev(K[ch],'PRESS',*scr(0,0),unicode=ch,ascii=ch) for ch in e[1]]
            elif e[0]=='rel': seq=[ev('LEFTMOUSE','RELEASE',*scr(0,0))]
            else: seq=[ev(e[0],'PRESS',*scr(0,0))]
            for x in seq:
                r=type(o).modal(o,ctx,x)
                if 'FINISHED' in r or 'CANCELLED' in r: return r,b
    return r,b
try:
    r,b=gb([('rel',),('t','2'),('RET',)])
    chk("Gumball : clic sur la flèche X, 2 tapé", abs(b.location.x-2)<1e-6, (r,tuple(b.location)))
    r,b=gb([('rel',),('RET',)])
    chk("Gumball suivant : clic sur la flèche puis Entrée reprend 2", abs(b.location.x-2)<1e-6, (r,tuple(b.location)))
except Exception as ex:
    chk("Gumball : saisie", False, repr(ex))

# ---------------- Annuler / Rétablir ----------------
clear(); C.view_layer.update()
def run_c():
    o,r=start(m.DESSIN_OT_cercle); E(o,('c',0,0),('m',3,0),'RET')
undo_redo("cercle créé par Entrée = dernière valeur", run_c)
print("RESULTAT",sum(res),"/",len(res))
