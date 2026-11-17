import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
exec(open(_os.path.join(_HERE,'prec_lib.py')).read())
# Alias de l'utilisateur (AliasEdit d'AutoCAD, alias de Rhino) : la ligne de commande les prend avant les alias fournis
import types
SEC="Alias personnalisés"
def first(txt):
    s=m.cmd_suggest(txt); return s[0] if s else None
def setal(lst): m.ALIAS_STATE["test"]=lst; m.alias_changed()
try:
    setal([])
    base_c=first("c"); base_ee=first("ee")
    rec(SEC,"sans alias : « c » lance Circle (alias fourni), « ee » ne désigne pas Extend Curve",base_c is not None and base_c["label"].startswith("Circle") and (base_ee is None or base_ee["label"]!="Extend Curve"),(base_c and base_c["label"],base_ee and base_ee["label"]))
    setal([("ee","extend"),("c","Copy"),("zz","does not exist"),("xx","Extend Curve"),("  ","Line"),("rr","")])
    e=first("ee")
    rec(SEC,"alias ee -> extend : « ee » lance Extend Curve",e is not None and e["label"]=="Extend Curve" and e["kind"]=="tool",e and e["label"])
    rec(SEC,"... et la suggestion affiche l'alias de l'utilisateur",e is not None and "ee" in (e.get("alias") or "").split(),e and e.get("alias"))
    e=first("xx")
    rec(SEC,"la commande peut être donnée par son nom complet (Extend Curve) : deux alias pour la même commande",e is not None and e["label"]=="Extend Curve" and set(e.get("user",()))=={"ee","xx"},e and e.get("user"))
    e=first("c")
    rec(SEC,"alias c -> Copy : il passe avant l'alias fourni (Circle)",e is not None and e["label"]=="Copy",e and e["label"])
    labs=[s["label"] for s in m.cmd_suggest("c")]
    rec(SEC,"... Circle reste proposé juste après",labs[1].startswith("Circle"),labs[:4])
    rec(SEC,"alias vers une commande inconnue, alias vide ou commande vide : ignorés sans erreur",(first("zz") is None or "zz" not in (first("zz").get("user") or ())) and all(a.strip() and c.strip() for a,c in m.user_aliases()),m.user_aliases())
    e=first("circle")
    rec(SEC,"les noms complets marchent toujours (circle -> Circle)",e is not None and e["label"].startswith("Circle"),e and e["label"])
    e=first("e")
    rec(SEC,"taper le début d'un alias le propose aussi (e -> ... Extend Curve dans la liste)",any(s["label"]=="Extend Curve" for s in m.cmd_suggest("e")),[s["label"] for s in m.cmd_suggest("e")])
    setal([("ee","Move")])
    e=first("ee")
    rec(SEC,"alias modifié : la ligne de commande suit tout de suite (ee -> Move)",e is not None and e["label"]=="Move",e and e["label"])
    ents=m.cmd_entries(); k=m.alias_target(ents,"m")
    rec(SEC,"une commande se désigne aussi par un de ses alias (m -> Move)",k is not None and ents[k]["label"]=="Move",k is not None and ents[k]["label"])
    k=m.alias_target(ents,"extendcurve")
    rec(SEC,"... sans tenir compte des espaces ni de la casse (extendcurve -> Extend Curve)",k is not None and ents[k]["label"]=="Extend Curve")
    setal([])
    rec(SEC,"alias retiré : « ee » ne lance plus Move",first("ee") is None or first("ee")["label"]!="Move")
    e=first("aliasedit")
    rec(SEC,"commande « aliasedit » : ouvre l'éditeur d'alias",e is not None and e["label"]=="Alias Editor" and e["kind"]=="act",e and (e["label"],e["kind"]))
    rec(SEC,"... l'opérateur de l'éditeur est enregistré",hasattr(bpy.ops.dessin,"alias_edit") and hasattr(bpy.types,"DESSIN_OT_alias_edit"))
    # lecture depuis les préférences (ici simulées : le harnais n'installe pas le module comme add-on)
    m.ALIAS_STATE["test"]=None
    G=m.user_aliases.__globals__; real=G['bpy']
    class _B:
        def __init__(s): s.context=types.SimpleNamespace(preferences=types.SimpleNamespace(addons={G['__package__']:types.SimpleNamespace(preferences=types.SimpleNamespace(aliases=[types.SimpleNamespace(alias="ee",command="extend"),types.SimpleNamespace(alias="",command="x")]))}))
        def __getattr__(s,k): return getattr(real,k)
    G['bpy']=_B()
    try: got=m.user_aliases()
    finally: G['bpy']=real
    rec(SEC,"les alias sont lus dans les préférences de l'add-on (les lignes incomplètes sont ignorées)",got==[("ee","extend")],got)
    # opérateurs Ajouter / Retirer sur une vraie collection de DESSIN_PG_alias
    bpy.types.Scene.wd_test_aliases=bpy.props.CollectionProperty(type=m.DESSIN_PG_alias)
    coll=bpy.context.scene.wd_test_aliases
    GP=m.DESSIN_OT_alias_add.execute.__globals__
    import tempfile, json
    tmpd=tempfile.mkdtemp(prefix="wd_alias_test_"); tmpf=_os.path.join(tmpd,"aliases.json")
    real_file=GP['_alias_file']; GP['_alias_file']=lambda: tmpf          # pas d'écriture dans la vraie configuration
    fake=types.SimpleNamespace(preferences=types.SimpleNamespace(addons={GP['__package__']:types.SimpleNamespace(preferences=types.SimpleNamespace(aliases=coll))},is_dirty=False))
    o=make(m.DESSIN_OT_alias_add); o.alias,o.command="ee","extend"; r=type(o).execute(o,fake)
    o=make(m.DESSIN_OT_alias_add); o.alias,o.command="cc","Copy"; r2=type(o).execute(o,fake)
    rec(SEC,"bouton « Add alias » : deux alias ajoutés, préférences marquées à enregistrer",'FINISHED' in r and 'FINISHED' in r2 and [(a.alias,a.command) for a in coll]==[("ee","extend"),("cc","Copy")] and fake.preferences.is_dirty,[(a.alias,a.command) for a in coll])
    o=make(m.DESSIN_OT_alias_remove); o.index=0; r=type(o).execute(o,fake)
    rec(SEC,"bouton X : l'alias choisi est retiré",'FINISHED' in r and [(a.alias,a.command) for a in coll]==[("cc","Copy")],[(a.alias,a.command) for a in coll])
    o=make(m.DESSIN_OT_alias_remove); o.index=7; r=type(o).execute(o,fake)
    rec(SEC,"... un rang qui n'existe pas ne casse rien",'CANCELLED' in r and len(coll)==1)
    saved=json.load(open(tmpf,encoding="utf-8")) if _os.path.isfile(tmpf) else None
    rec(SEC,"chaque changement est aussi écrit dans le dossier de configuration (aliases.json)",saved==[{"alias":"cc","command":"Copy"}],saved)
    json.dump([{"alias":"ee","command":"extend"},{"alias":"cc","command":"Copy"},{"alias":"  ","command":"x"},"n'importe quoi"],open(tmpf,"w",encoding="utf-8"))
    n0=m.aliases_restore(types.SimpleNamespace(aliases=coll))
    rec(SEC,"préférences déjà remplies : la copie n'est pas rechargée (pas de doublons)",n0==0 and len(coll)==1,(n0,len(coll)))
    coll.clear()
    n1=m.aliases_restore(types.SimpleNamespace(aliases=coll))
    rec(SEC,"add-on réinstallé (préférences vides) : les alias reviennent depuis la copie, les lignes invalides sont ignorées",n1==2 and [(a.alias,a.command) for a in coll]==[("ee","extend"),("cc","Copy")],(n1,[(a.alias,a.command) for a in coll]))
    kept=json.load(open(tmpf,encoding="utf-8"))
    rec(SEC,"... et la relecture ne réécrit pas le fichier en cours de route",len(kept)==4,len(kept))
    GP['_alias_file']=real_file
    import shutil; shutil.rmtree(tmpd,ignore_errors=True)
    del bpy.types.Scene.wd_test_aliases
finally:
    m.ALIAS_STATE["test"]=None; m.alias_changed()
summary()
