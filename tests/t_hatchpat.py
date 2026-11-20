import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
import numpy as np, json, time, tempfile, sys
for o in list(bpy.data.objects): bpy.data.objects.remove(o)
C=bpy.context
hp=sys.modules[m.__name__+".hatch_patterns"] if (m.__name__+".hatch_patterns") in sys.modules else None
if hp is None:
    hp=[v for k,v in sys.modules.items() if k.endswith(".hatch_patterns")][0]
res=[]
def chk(name,ok,info=""):
    res.append(bool(ok)); print(("OK  " if ok else "BAD ")+name, info)
R=m.build_polyline(C,"Outer",[Vector(p) for p in [(0,0,0),(60,0,0),(60,40,0),(0,40,0)]],True)
H=m.build_polyline(C,"Hole",[Vector(p) for p in [(20,10,0),(35,10,0),(35,25,0),(20,25,0)]],True)
C.view_layer.update()
for o in C.view_layer.objects: o.select_set(o.name in ("Outer","Hole"))
st=C.scene.dessin; st.hatch_spacing=1.0; st.hatch_pattern='HATCH1'
op=make(m.DESSIN_OT_hatch); type(op).execute(op,ctx)
h=[o for o in bpy.data.objects if m.is_hatch(o)][0]
# 1) numéros des anciens motifs inchangés (fichiers enregistrés)
items={it[0]:it[4] for it in hp.pattern_items()}
chk("numéros des motifs d'origine", [items[k] for k in ('SOLID','HATCH1','HATCH2','HATCH3','DASH','GRID','GRID60','PLUS','SQUARES','BRICK')]==list(range(10)), items)
chk("au moins 12 motifs de matériaux", len(items)>=22, len(items))
# 2) chaque motif : des lignes, toutes dans le contour et hors du trou
mw=h.matrix_world
for k in [it[0] for it in hp.pattern_items() if it[0]!='SOLID']:
    t=time.time(); h.dessin_hatch.pattern=k; me=h.data
    P=[mw@v.co for v in me.vertices]
    out=sum(1 for p in P if not (-1e-4<p.x<60+1e-4 and -1e-4<p.y<40+1e-4))
    inh=sum(1 for e in me.edges if 20+1e-4<((P[e.vertices[0]]+P[e.vertices[1]])/2).x<35-1e-4 and 10+1e-4<((P[e.vertices[0]]+P[e.vertices[1]])/2).y<25-1e-4)
    chk(f"motif {k}", len(me.edges)>20 and out==0 and inh==0 and h.dessin_hatch.pattern==k, (len(me.edges),out,inh,f"{time.time()-t:.2f}s"))
# 3) points (tiret 0) : petits traits
h.dessin_hatch.pattern='SAND'; me=h.data
L=[(me.vertices[e.vertices[0]].co-me.vertices[e.vertices[1]].co).length for e in me.edges]
chk("Sand : des points (traits très courts)", max(L)<0.2 and min(L)>0.01, (round(min(L),3),round(max(L),3)))
# 4) carreau -> familles : chaque segment du carreau est reproduit
fams=hp.tile_families((4,0),(0,4),[((0,0),(1,2))])
S=m.hatch_segments_2d([np.array([(0.5,0.5),(19.5,0.5),(19.5,19.5),(0.5,19.5)])],fams,1.0,0.0,(0,0))
L=np.linalg.norm(S[:,1]-S[:,0],axis=1)
full=S[np.abs(L-np.sqrt(5))<1e-6]
ok=all(abs((a[0]%4))<1e-6 or abs((a[0]%4)-4)<1e-6 for a in full[:,0]) and all(abs(a[1]%4)<1e-6 or abs(a[1]%4-4)<1e-6 for a in full[:,0])
chk("carreau : segments aux bons endroits", len(full)==16 and ok, (len(full),))
# 5) fichier .pat (pouces et mm) : ANSI31 = Hatch1
pat="""; test
*ANSI31, ANSI Iron, Brick, Stone masonry
45, 0,0, 0,.125
*MYDASH,My dash
0, 0,0, 0,.25, .25,-.125
90, .5,0, .125,.25, .25,-.125, 0,-.125
*EMPTY
"""
got=hp.parse_pat(pat)
chk(".pat : 2 motifs lus", [g[0] for g in got]==["ANSI31","MYDASH"], [g[0] for g in got])
f0=got[0][2][0]
chk(".pat : ANSI31 = Hatch1 (écart 1)", abs(f0[0]-45)<1e-9 and abs(f0[4]-1)<1e-9 and f0[5]==(), f0)
f2=got[1][2][1]
chk(".pat : origine dans le repère de la ligne, tirets et point", abs(f2[1]-0)<1e-9 and abs(f2[2]-(-4))<1e-9 and f2[5]==(2.0,-1.0,0.0,-1.0), f2)
gm=hp.parse_pat(";%UNITS=MM\n*ANSI31,iso\n45, 0,0, 0,3.175\n")
chk(".pat métrique (acadiso)", abs(gm[0][2][0][4]-1)<1e-9, gm)
# 6) import d'un fichier .pat dans la scène, hachure avec ce motif
d=tempfile.mkdtemp(); fp=_os.path.join(d,"mine.pat"); open(fp,"w",encoding="cp1252").write(pat+"*DIAG,Diagonale éclatée\n135, 0,0, 0,.5, .5,-.25\n")
op=make(m.DESSIN_OT_hatch_import); op.filepath=fp; r=type(op).execute(op,ctx)
keys=[it[0] for it in hp.pattern_items() if it[0].startswith("PAT")]
chk("import : 3 motifs ajoutés à la liste", r=={'FINISHED'} and len(keys)==3, (r,keys))
chk("import : le motif des nouvelles hachures devient le premier importé", st.hatch_pattern==keys[0], st.hatch_pattern)
k=[it[0] for it in hp.pattern_items() if it[1]=="DIAG"][0]
h.dessin_hatch.pattern=k; n_custom=len(h.data.edges); dd=json.loads(h["dessin_hatch"])
chk("hachure avec un motif importé (copie gardée)", n_custom>10 and dd.get("pat")=="DIAG" and len(dd.get("fams",[]))==1, (n_custom,dd.get("pat")))
# réimport : même nom remplacé, pas de doublon
op=make(m.DESSIN_OT_hatch_import); op.filepath=fp; type(op).execute(op,ctx)
chk("réimport : pas de doublon", len([it for it in hp.pattern_items() if it[0].startswith("PAT")])==3)
# 7) relu à l'ouverture du fichier (registre refait depuis la scène)
hp._CUSTOM.clear(); hp._rebuild_items(); hp.refresh_custom()
chk("motifs importés relus depuis la scène", h.dessin_hatch.pattern==k, h.dessin_hatch.pattern)
# 8) motif retiré : la hachure garde son dessin
op=make(m.DESSIN_OT_hatch_pattern_remove); op.key=k; r=type(op).execute(op,ctx)
chk("retrait du motif importé", r=={'FINISHED'} and k not in [it[0] for it in hp.pattern_items()], r)
m.rebuild_hatch(h)
chk("la hachure garde son motif après le retrait", len(h.data.edges)==n_custom, (len(h.data.edges),n_custom))
h.dessin_hatch.pattern='HATCH2'; dd=json.loads(h["dessin_hatch"])
chk("motif intégré : la copie est retirée", "fams" not in dd and "pat" not in dd)
# 9) édition : opérateur et double-clic
for o in C.view_layer.objects: o.select_set(False)
chk("Edit Hatch indisponible sans hachure", not m.DESSIN_OT_hatch_edit.poll(C))
h.select_set(True); C.view_layer.objects.active=h
chk("Edit Hatch disponible avec une hachure", m.DESSIN_OT_hatch_edit.poll(C))
km=[it for it in m.DESSIN_TT_selection_boite.bl_keymap if it[0]=="dessin.hatch_dblclick"]
chk("double-clic dans l'outil Select", len(km)==1 and km[0][1]["value"]=='DOUBLE_CLICK')
# 10) aperçu des motifs
img=hp._swatch(hp.HATCH_PATTERNS['HERRINGBONE'])
lit=int(((img[...,0]>0.8)&(img[...,3]>0.9)).sum())
chk("aperçu du motif dessiné", img.shape==(64,64,4) and lit>150, lit)
chk("aperçu de tous les motifs", all(int((hp._swatch(hp.HATCH_PATTERNS[k])[...,0]>0.8).sum())>40 for k in hp.HATCH_PATTERNS))
# 11) Hatch Region : D parcourt tous les motifs
op=make(m.DESSIN_OT_hatch_region); op._pat_keys=[it[0] for it in hp.pattern_items()]; op.MODES=tuple(it[1] for it in hp.pattern_items()); op.mode=13
chk("Hatch Region : motif par D", op.pattern()==op._pat_keys[13], op.pattern())
# 12) commandes
names=[c[0] for c in m.COMMANDS] if hasattr(m,"COMMANDS") else []
print("RESULTAT",sum(res),"/",len(res))
