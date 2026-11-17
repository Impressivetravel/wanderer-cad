# Coller (Ctrl/Cmd + V) des nombres et des coordonnées dans une commande en cours ; # et @ tapés avec AltGr
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
src=open(_os.path.join(_HERE,'t_pushpull.py')).read()
exec(src[src.index("\n")+1:src.index("# ---------------- 1. PushPull")])
st=C.scene.dessin; st.ortho=False; st.polar=False
def paste(o,text,**k):
    ctx.window_manager.clipboard=text
    with contextlib.redirect_stdout(io.StringIO()):
        return type(o).modal(o,ctx,ev('V','PRESS',*scr(3,3),ctrl=True,**k))
def curves(): return [q for q in bpy.data.objects if q.type=='CURVE']
def pts_of(q): return [q.matrix_world@Vector(p.co[:3]) for sp in q.data.splines for p in sp.points]
def same(P,Q,tol=1e-6): return len(P)==len(Q) and all((a-Vector(b)).length<tol for a,b in zip(P,Q))

# ---------------- 1. préparation du texte ----------------
T=m.paste_text
chk("texte : une coordonnée seule reste en attente d'Entrée", T("#0,360.16")=="#0,360.16", T("#0,360.16"))
chk("texte : retour à la ligne final = Entrée", T("12.5\n")=="12.5\n", repr(T("12.5\n")))
chk("texte : espaces et lignes séparent les points (un Entrée par séparateur)", T("  #0,0   #10,0\r\n@0,5\n")=="#0,0\n#10,0\n@0,5\n", repr(T("  #0,0   #10,0\r\n@0,5\n")))
chk("texte : une ligne vide = un Entrée de plus", T("#0,0\n#10,0\n\n")=="#0,0\n#10,0\n", repr(T("#0,0\n#10,0\n\n")))
chk("texte : lettres, texte vide ou trop long refusés", T("hello")is None and T("")is None and T(None)is None and T("12a")is None and T("1"*5000)is None, None)
chk("texte : polaire, relatif, point-virgule, tabulation acceptés", T("@10<45")=="@10<45" and T("3;4")=="3;4" and T("20\t30")=="20\t30", None)

# ---------------- 2. polyligne : une liste de points collée d'un coup ----------------
clear(); o,r=start(m.DESSIN_OT_polyligne); E(o,('m',3,3))
r=paste(o,"#0,360.16\n#36.84,360.16\n#360,37\n#683.16,360.16\n#720,360.16\n"); r2=E(o,'RET'); C.view_layer.update()
P=pts_of(curves()[0]) if curves() else []
chk("5 points collés + Entrée : polyligne exacte", 'RUNNING_MODAL' in r and len(curves())==1 and same(P,[(0,360.16,0),(36.84,360.16,0),(360,37,0),(683.16,360.16,0),(720,360.16,0)],1e-4), (r,P))
clear(); o,r=start(m.DESSIN_OT_polyligne); E(o,('m',3,3))
paste(o,"#0,0 @10,0 @0,5"); E(o,'RET','RET'); C.view_layer.update()
P=pts_of(curves()[0]) if curves() else []
chk("points relatifs séparés par des espaces, dernier point validé par Entrée", same(P,[(0,0,0),(10,0,0),(10,5,0)]), P)
clear(); o,r=start(m.DESSIN_OT_polyligne); E(o,('m',3,3),('c',0,0))
paste(o,"@10<90\n"); E(o,'RET'); C.view_layer.update()
P=pts_of(curves()[0]) if curves() else []
chk("coordonnée polaire collée", same(P,[(0,0,0),(0,10,0)],1e-5), P)

# ---------------- 3. un nombre collé dans le champ d'un outil ----------------
clear(); o,r=start(m.DESSIN_OT_cercle); E(o,('c',0,0),('m',3,0)); paste(o,"7.25"); E(o,'RET'); C.view_layer.update()
c=curves()[0] if curves() else None
chk("Circle : rayon 7,25 collé puis Entrée", c is not None and abs(c.dimensions.x-14.5)<1e-4, c.dimensions[:] if c else None)
clear(); o,r=start(m.DESSIN_OT_rectangle); E(o,('c',0,0),('m',3,2)); paste(o,"72\t36\n"); C.view_layer.update()
c=curves()[0] if curves() else None
chk("Rectangle : « 72 Tab 36 Entrée » collé", c is not None and abs(c.dimensions.x-72)<1e-4 and abs(c.dimensions.y-36)<1e-4, c.dimensions[:] if c else None)
clear(); b=box(); C.view_layer.update(); o,r=start(m.DESSIN_OT_pushpull)
top=[p.index for p in b.data.polygons if p.normal.z>0.9][0]
o.hit_face=lambda context,region,mx,my:(b,top,Vector((0,0,4)))
E(o,('c',0,0)); r=paste(o,"1.5\n"); C.view_layer.update(); s=stats(b)
chk("PushPull : distance 1,5 collée (boîte 4 x 4 x 5,5)", abs(s["vol"]-88)<1e-5 and solid_ok(s), (r,s))

# ---------------- 4. presse-papiers sans nombres : rien ne change, un message ----------------
clear(); o,r=start(m.DESSIN_OT_polyligne); E(o,('m',3,3),('c',0,0)); n0=len(o.points)
r=paste(o,"hello world")
chk("texte sans nombres : refusé avec un message, la commande continue", 'RUNNING_MODAL' in r and len(o.points)==n0 and any("Paste" in x[1] for x in o._reports), (r,o._reports))
r=paste(o,"")
chk("presse-papiers vide : la commande continue", 'RUNNING_MODAL' in r and len(o.points)==n0, r)
E(o,'ESC')

# ---------------- 5. # et @ tapés avec AltGr (Ctrl + Alt sous Windows, Option sur Mac) ----------------
clear(); o,r=start(m.DESSIN_OT_polyligne); E(o,('m',3,3))
with contextlib.redirect_stdout(io.StringIO()):
    type(o).modal(o,ctx,ev('THREE','PRESS',*scr(3,3),unicode='#',ascii='#',ctrl=True,alt=True))
    for ch in "5,5": type(o).modal(o,ctx,ev(K.get(ch,'COMMA'),'PRESS',*scr(3,3),unicode=ch,ascii=ch))
    type(o).modal(o,ctx,ev('RET','PRESS',*scr(3,3)))
    type(o).modal(o,ctx,ev('ZERO','PRESS',*scr(3,3),unicode='@',ascii='@',alt=True))
    for ch in "5,0": type(o).modal(o,ctx,ev(K.get(ch,'COMMA'),'PRESS',*scr(3,3),unicode=ch,ascii=ch))
    type(o).modal(o,ctx,ev('RET','PRESS',*scr(3,3)))
chk("« # » avec Ctrl+Alt (AltGr) et « @ » avec Alt : acceptés", len(o.points)==2 and same(o.points,[(5,5,0),(10,5,0)]), o.points)
with contextlib.redirect_stdout(io.StringIO()):
    r=type(o).modal(o,ctx,ev('Z','PRESS',*scr(3,3),unicode='z',ascii='z',ctrl=True))
chk("Ctrl+Z n'est pas pris pour une saisie de coordonnées", not o.coord, o.coord)
E(o,'ESC')

# ---------------- 6. Annuler / Rétablir ----------------
clear()
def run():
    o,r=start(m.DESSIN_OT_polyligne); E(o,('m',3,3)); paste(o,"#0,0\n#10,0\n#10,5\n"); E(o,'RET')
undo_redo("polyligne collée", run)
print("RESULTAT",sum(res),"/",len(res))
