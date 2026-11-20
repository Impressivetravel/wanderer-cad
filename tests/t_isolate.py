import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
# Hide / Isolate / Unisolate / Show, comme Rhino : Unisolate réaffiche seulement ce qu'Isolate a masqué,
# Show réaffiche tout.
C=bpy.context
res=[]
def chk(name,ok,info=""):
    res.append(bool(ok)); print(("OK  " if ok else "BAD ")+name, info)
for o in list(bpy.data.objects): bpy.data.objects.remove(o)
O={}
for n in "ABCDEF":
    o=bpy.data.objects.new(n,None); C.scene.collection.objects.link(o); O[n]=o
C.view_layer.update()      # (objets tout juste créés : leur sélection n'est lue qu'après une mise à jour)
def sel(*ns):
    for o in C.view_layer.objects: o.select_set(o.name in ns)
    if ns: C.view_layer.objects.active=O[ns[0]]
    C.view_layer.update()
def hidden(): return "".join(sorted(o.name for o in C.view_layer.objects if o.hide_get()))
class _Ops:
    def __getattr__(s,name):
        cls=getattr(m,"DESSIN_OT_"+name)
        class F:
            def __call__(f):
                op=make(cls); return type(op).execute(op,ctx)
            def poll(f): return cls.poll(ctx)
        return F()
OPS=_Ops()
def cmd(label):
    hit=[c for c in m.cmd_suggest(label.lower())][:1]
    return hit[0]["label"] if hit else None
sel("A"); OPS.hide()
chk("Hide : A masqué", hidden()=="A", hidden())
sel("B","C"); OPS.isolate()
chk("Isolate B, C : D, E, F masqués (A l'était déjà)", hidden()=="ADEF", hidden())
chk("... Unisolate disponible", OPS.unisolate.poll())
OPS.unisolate()
chk("Unisolate : D, E, F réaffichés, A (masqué par Hide) reste masqué", hidden()=="A", hidden())
chk("... plus rien à désisoler", not OPS.unisolate.poll())
sel("B","C"); OPS.isolate()
OPS.show()
chk("Isolate puis Show : tout est réaffiché, y compris A", hidden()=="", hidden())
chk("... et Unisolate n'a plus rien à faire", not OPS.unisolate.poll())
# Isolate deux fois de suite : Unisolate réaffiche tout ce que les deux ont masqué
sel("A","B","C"); OPS.isolate(); sel("A"); OPS.isolate()
chk("Isolate A, B, C puis Isolate A : seul A visible", hidden()=="BCDEF", hidden())
OPS.unisolate()
chk("Unisolate : tout ce que les deux Isolate avaient masqué revient", hidden()=="", hidden())
# un objet isolé puis masqué par Hide après avoir été réaffiché à la main : Unisolate ne le réaffiche pas
sel("A"); OPS.isolate()
O["D"].hide_set(False); sel("D"); OPS.hide()
OPS.unisolate()
chk("objet réaffiché à la main puis masqué par Hide : Unisolate le laisse masqué", hidden()=="D", hidden())
OPS.show()
# Alt+H de Blender (réaffiche tout) puis H : l'ancienne marque d'Isolate est oubliée au prochain Isolate
sel("A"); OPS.isolate(); [o.hide_set(False) for o in C.view_layer.objects]      # (Alt+H de Blender)
sel("B"); OPS.isolate()
O["B"].hide_set(False)
chk("marques d'un ancien Isolate effacées sur les objets réaffichés autrement", all(not o.get("wd_isolated") for o in C.view_layer.objects if not o.hide_get()), [o.name for o in C.view_layer.objects if o.get("wd_isolated")])
OPS.show()
chk("Isolate sans sélection : refusé", (sel(), not OPS.isolate.poll())[1])
# annuler
# ligne de commande
got={t:cmd(t) for t in ("unisolate","uniso","isolate","show","showall","hide")}
chk("ligne de commande : isolate, unisolate / uniso, show / showall, hide", got=={"unisolate":"Unisolate","uniso":"Unisolate","isolate":"Isolate","show":"Show","showall":"Show","hide":"Hide"}, got)
pg=[v for k,v in vars(m).items() if k=="PGP_COMMANDS" or k=="AUTOCAD_COMMANDS"]
print("RESULTAT",sum(res),"/",len(res))
