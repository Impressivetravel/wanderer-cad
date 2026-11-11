import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
exec(open(_os.path.join(_HERE,'undo_lib.py')).read())
m.DessinTransform=mirror(m.DessinTransform)
import bmesh, sys, math
OKS=[]
def chk(name,cond,extra=""):
    OKS.append(bool(cond)); print(("OK  " if cond else "BAD ")+name,str(extra)[:260])
def clear():
    for o in list(bpy.data.objects): bpy.data.objects.remove(o)
    for c in list(bpy.data.collections):
        try: bpy.data.collections.remove(c)
        except Exception: pass
    bpy.context.view_layer.update()
def clicks(o,P):
    r=None
    for (x,y) in P:
        sx,sy=scr(x,y)
        for e in (ev('MOUSEMOVE','NOTHING',sx,sy),ev('LEFTMOUSE','PRESS',sx,sy),ev('LEFTMOUSE','RELEASE',sx,sy)):
            r=type(o).modal(o,ctx,e)
            if 'FINISHED' in r or 'CANCELLED' in r: return r
    return r
def start(cls,p=(0,0)):
    o=make(cls); r=type(o).invoke(o,ctx,ev('NONE','NOTHING',*scr(*p))); return o,r
def undo(): bpy.ops.ed.undo(); bpy.context.view_layer.update()
def redo(): bpy.ops.ed.redo(); bpy.context.view_layer.update()
def push(msg): bpy.context.view_layer.update(); bpy.ops.ed.undo_push(message=msg)

# ===== A. Ctrl+Z au clavier pendant une commande
clear(); push("vide")
o,r=start(m.DESSIN_OT_polyligne); clicks(o,[(0,0),(6,0),(6,4)])
r=type(o).modal(o,ctx,ev('Z','PRESS',*scr(6,4),ctrl=True))
chk("Ctrl+Z en polyligne : retire le dernier point, commande toujours active",'RUNNING_MODAL' in r and len(o.points)==2 and not bpy.data.objects,(r,len(o.points)))
r=type(o).modal(o,ctx,ev('Z','PRESS',*scr(6,4),ctrl=True,shift=True))
chk("Ctrl+Maj+Z en polyligne : ignoré",'RUNNING_MODAL' in r and len(o.points)==2)
r=type(o).modal(o,ctx,ev('RET','PRESS',*scr(6,4)))
chk("polyligne finie avec les 2 points restants",len(bpy.data.objects)==1 and len(bpy.data.objects[0].data.splines[0].points)==2)
try: type(o).cleanup(o,ctx)
except Exception: pass
clear()
o,r=start(m.DESSIN_OT_cercle); clicks(o,[(0,0)])
r=type(o).modal(o,ctx,ev('Z','PRESS',*scr(3,0),ctrl=True))
chk("Ctrl+Z en cercle (centre posé) : commande annulée, rien créé",'CANCELLED' in r and not bpy.data.objects,r)
try: type(o).cleanup(o,ctx)
except Exception: pass
o,r=start(m.DESSIN_OT_cercle)
r=type(o).modal(o,ctx,ev('Z','PRESS',*scr(3,0),ctrl=True))
chk("Ctrl+Z sans point posé : laissé à Blender",'PASS_THROUGH' in r,r)
type(o).modal(o,ctx,ev('ESC','PRESS',*scr(0,0)))
try: type(o).cleanup(o,ctx)
except Exception: pass
# Move en cours : Ctrl+Z annule le déplacement, l'objet revient
clear()
me=bpy.data.meshes.new("Box"); bm=bmesh.new(); bmesh.ops.create_cube(bm,size=4); bm.to_mesh(me); bm.free()
box=bpy.data.objects.new("Box",me); bpy.context.scene.collection.objects.link(box); box.location=(-8,-8,2)
box.select_set(True); bpy.context.view_layer.objects.active=box; bpy.context.view_layer.update()
mv=next(c for n,c in vars(m).items() if n in ('DESSIN_OT_deplacer','DESSIN_OT_move'))
o,r=start(mv,(-8,-8)); clicks(o,[(-8,-8)])
type(o).modal(o,ctx,ev('MOUSEMOVE','NOTHING',*scr(2,3)))
moved=tuple(round(x,3) for x in bpy.data.objects["Box"].location)
r=type(o).modal(o,ctx,ev('Z','PRESS',*scr(2,3),ctrl=True))
chk("Ctrl+Z pendant Move : annulé, objet à sa place d'origine",'CANCELLED' in r and tuple(round(x,3) for x in bpy.data.objects["Box"].location)==(-8,-8,2),(r,moved,tuple(bpy.data.objects["Box"].location)))
try: type(o).cleanup(o,ctx)
except Exception: pass

# ===== B. Point : une étape d'annulation par point
clear(); push("vide"); A=snapshot(bpy)
o,r=start(m.DESSIN_OT_point); clicks(o,[(1,1),(4,2),(7,5)])
type(o).modal(o,ctx,ev('ESC','PRESS',*scr(0,0)))
try: type(o).cleanup(o,ctx)
except Exception: pass
n=len(bpy.data.objects)
undo(); n1=len(bpy.data.objects); undo(); n2=len(bpy.data.objects); undo()
chk("Point : chaque Ctrl+Z retire un point",(n,n1,n2,len(bpy.data.objects))==(3,2,1,0),(n,n1,n2,len(bpy.data.objects)))
chk("Point : scène identique après 3 annulations",snapshot(bpy)==A,diff(A,snapshot(bpy)))

# ===== C. Block Edit et annulation
clear()
a=m.build_polyline(bpy.context,"A",[Vector((0,0,0)),Vector((4,0,0)),Vector((4,3,0))],True)
bpy.context.view_layer.update()
d=m.make_block(bpy.context,[a],Vector((0,0,0)),"B1")
inst=[ob for ob in bpy.data.objects if m.is_block_instance(ob)]
if not inst: inst=[m.new_block_instance(bpy.context,d if not isinstance(d,(tuple,list)) else d[0],Matrix.Translation((10,0,0)))]
i1=inst[0]
for ob in bpy.context.view_layer.objects: ob.select_set(False)
i1.select_set(True); bpy.context.view_layer.objects.active=i1
push("bloc"); S0=snapshot(bpy)
op=make(m.DESSIN_OT_block_edit); r=type(op).execute(op,ctx); push("block edit"); S1=snapshot(bpy)
chk("Block Edit ouvert",'FINISHED' in r and m.block_edit_state()["inst"] is not None,op._reports)
undo()
chk("annuler Block Edit : plus d'édition en cours, scène d'origine",m.block_edit_state()["inst"] is None and snapshot(bpy)==S0,(m.block_edit_state(),diff(S0,snapshot(bpy))))
i1=next(ob for ob in bpy.data.objects if m.is_block_instance(ob))
for ob in bpy.context.view_layer.objects: ob.select_set(False)
i1.select_set(True); bpy.context.view_layer.objects.active=i1
op=make(m.DESSIN_OT_block_edit); r=type(op).execute(op,ctx)
chk("Block Edit relançable après annulation",'FINISHED' in r,op._reports)
push("block edit 2"); S2=snapshot(bpy)
op=make(m.DESSIN_OT_block_edit_close); r=type(op).execute(op,ctx); push("close"); S3=snapshot(bpy)
chk("Close Block Edit",'FINISHED' in r and m.block_edit_state()["inst"] is None,op._reports)
undo()
chk("annuler Close : l'édition est de nouveau en cours",m.block_edit_state()["inst"] is not None and snapshot(bpy)==S2,(m.block_edit_state(),diff(S2,snapshot(bpy))))
op=make(m.DESSIN_OT_block_edit_close); r=type(op).execute(op,ctx)
chk("Close fonctionne après l'annulation (pas de collection d'édition orpheline)",'FINISHED' in r and not [c for c in bpy.data.collections if c.name.startswith("Block Edit")],(r,op._reports,[c.name for c in bpy.data.collections]))
chk("instance de nouveau visible",not next(ob for ob in bpy.data.objects if m.is_block_instance(ob)).hide_get())

# ===== D. Suites de fonctionnalités : aller-retour undo / redo de tout ce qu'elles créent, puis opérations sur les données rétablies
def domain_followups():
    errs=[]
    def t(name,fn):
        try:
            with contextlib.redirect_stdout(io.StringIO()): fn()
        except Exception:
            errs.append(name+": "+" | ".join(traceback.format_exc().strip().splitlines()[-2:])[:230])
    for ob in list(bpy.data.objects):
        nm=ob.name
        if "dessin_hatch" in ob.keys(): t("rebuild_hatch "+nm,lambda ob=ob: m.rebuild_hatch(ob))
    for nm in [ob.name for ob in bpy.data.objects if "dessin_dim" in ob.keys()]:
        t("rebuild_dimension "+nm,lambda nm=nm: m.rebuild_dimension(bpy.context,bpy.data.objects[nm]))
    for ob in list(bpy.data.objects):
        k=ob.get("wd_untrimmed")
        if k and bpy.data.meshes.get(k) is None and bpy.data.objects.get(k) is None: errs.append(f"sauvegarde Untrim absente pour {ob.name}: {k}")
    for nm in [ob.name for ob in bpy.data.objects if m.is_block_instance(ob)][:2]:
        t("explode_block "+nm,lambda nm=nm: m.explode_block(bpy.context,bpy.data.objects[nm]))
    return errs
def followups(tag):
    errs=[]
    def tryit(name,fn):
        try:
            with contextlib.redirect_stdout(io.StringIO()): fn()
        except Exception:
            errs.append(f"{tag}/{name}: "+" | ".join(traceback.format_exc().strip().splitlines()[-2:])[:230])
    def snap():
        d=m.collect_snap_points(ctx); m._screen_index(d,np.array(rv3d.perspective_matrix,dtype=np.float64),region,allow_async=False)
        for p in ((0,0),(8,-10),(-6,-6),(12,-4)): m.find_snap_in(d,*scr(*p),region,rv3d)
    tryit("snap",snap)
    class FL:
        def __getattr__(self,n):
            if n=='panel': return lambda *a,**k:(FL(),FL())
            return lambda *a,**k: FL()
    def panels():
        from types import SimpleNamespace as NS2
        for n_,p in inspect.getmembers(m,inspect.isclass):
            if n_.startswith('DESSIN_PT') and 'draw' in vars(p): vars(p)['draw'](NS2(layout=FL(),bl_label=getattr(p,'bl_label','')),ctx)
    tryit("panels",panels)
    tryit("layers",lambda: m.layer_sync_new_objects())
    return errs
for suite in ("t_hatch.py","t_blocks.py","t_untrim.py","t_dimadv.py","t_srf.py","t_crv.py","t_ppimprint.py","t_extopts.py","t_extcap.py"):
    try: src=open(_os.path.join(_HERE,suite)).read()
    except OSError: continue
    src="\n".join(l for l in src.split("\n") if "harness.py" not in l)
    clear(); push("A "+suite); A=snapshot(bpy)
    g=dict(globals())
    try:
        with contextlib.redirect_stdout(io.StringIO()): exec(compile(src,suite,'exec'),g)
    except SystemExit: pass
    except Exception:
        chk(f"{suite} : exécution",False," | ".join(traceback.format_exc().strip().splitlines()[-2:])); continue
    push("B "+suite); B=snapshot(bpy)
    nobj=len(bpy.data.objects)
    undo(); A2=snapshot(bpy)
    chk(f"{suite} : annuler ramène l'état d'avant ({nobj} objets créés)",A2==A,diff(A,A2))
    e1=followups("undo")
    redo(); B2=snapshot(bpy)
    chk(f"{suite} : rétablir redonne exactement le résultat",B2==B,diff(B,B2))
    e2=followups("redo")+domain_followups()
    chk(f"{suite} : données rétablies utilisables (accrochage, panneaux, reconstruire hachures / cotes / blocs)",not(e1+e2),(e1+e2)[:2])
print("RESULTAT", sum(OKS),"/",len(OKS))
