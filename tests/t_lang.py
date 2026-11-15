import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
exec(open(_os.path.join(_HERE,'prec_lib.py')).read())
# Langues : changement sans latence ni redémarrage, et neuf langues avec les alias d'AutoCAD et de Rhino dans chacune
SEC="Langues"
def first(txt):
    s=m.cmd_suggest(txt); return s[0] if s else None
tools=[c for n,c in vars(m).items() if n.startswith("DESSIN_TT_") and isinstance(c,type)]
ops=[m.DESSIN_OT_move] if hasattr(m,"DESSIN_OT_move") else []
allc=tools+[c for n,c in vars(m).items() if n.startswith("DESSIN_OT_") and isinstance(c,type)]
def setlang(code,reload=True):
    m.PREF_DEFAULTS["language"]=code
    m._SUGG_MEMO.clear(); m.language_caches_clear()        # ce que fait language_changed, sans le rechargement différé
    if reload: m.apply_language(allc)                      # ce que refait l'enregistrement de l'add-on
def label(cls): return m.cmd_clean_label(cls.bl_label)
MV=m.DESSIN_TT_deplacer; EXT=m.DESSIN_TT_extend_crv
try:
    setlang('EN')
    rec(SEC,"anglais : Move, alias m",label(MV)=="Move" and first("m")["label"]=="Move" and first("move")["label"]=="Move",(label(MV),first("m")["label"]))
    # --- latence : une suggestion déjà calculée ne doit pas survivre au changement de langue
    m.cmd_suggest("deplacer"); m.cmd_suggest("dp"); m.cmd_suggest("m")
    setlang('FR')
    rec(SEC,"passage au français : le nom de l'outil change (Déplacer)",label(MV)=="Déplacer",label(MV))
    e=first("dp")
    rec(SEC,"... et la ligne de commande suit tout de suite, même pour un texte déjà tapé avant (dp -> Déplacer)",e is not None and e["label"]=="Déplacer",e and e["label"])
    rec(SEC,"... les invites aussi",m.tr_text("click to confirm")=="cliquer pour valider",m.tr_text("click to confirm"))
    m.cmd_suggest("m"); m.cmd_suggest("dp")
    setlang('EN')
    e=first("m")
    rec(SEC,"retour à l'anglais : nom Move, alias m, plus rien en français (dp ne donne plus Déplacer, invites en anglais)",
        label(MV)=="Move" and e["label"]=="Move" and (first("dp") is None or first("dp")["label"]!="Déplacer") and m.tr_text("click to confirm")=="click to confirm",(label(MV),e["label"]))
    left=[c.__name__ for c in tools if c.__dict__.get("dessin_en_label") and c.bl_label!=c.__dict__["dessin_en_label"]]
    rec(SEC,"aucun outil ne garde un nom français après le retour à l'anglais",not left,left[:5])
    # --- sans rechargement (l'instant entre le choix et le réenregistrement) : les suggestions sont déjà dans la nouvelle langue
    m.cmd_suggest("dp")
    setlang('FR',reload=False)
    e=first("dp")
    rec(SEC,"avant même le rechargement, les alias de la nouvelle langue répondent (dp)",e is not None and e["ref"]==MV.bl_idname,e and e["label"])
    setlang('EN')
    # --- les neuf langues
    want={'DE':("Verschieben","s","schieben","Kurve verlängern","dehnen"),'ES':("Mover","d","desplaza","Alargar curva","alarga"),
          'IT':("Sposta","s","sposta","Estendi curva","estendi"),'PT':("Mover","m","mover","Estender curva","estender"),
          'RU':("Перенести","п","перенести","Удлинить кривую","удлинить"),'TR':("Taşı","m","tasi","Eğriyi uzat","uzat"),
          'ZH':("移动","m","move","延伸曲线","extend"),'JA':("移動","m","move","曲線を延長","extend"),'KO':("이동","m","move","곡선 연장","extend")}
    codes=[c for c,_n,_d in m.LANGUAGE_ITEMS]
    rec(SEC,"onze langues au choix : anglais, français et les neuf nouvelles",codes==['EN','FR','DE','ES','IT','PT','RU','TR','ZH','JA','KO'],codes)
    for code,(name,short,word,xname,xword) in want.items():
        setlang(code)
        a,b,c_,d=first(short),first(word),first(xword),first("move")
        rec(SEC,f"{code} : l'outil s'appelle {name} ; « {short} » et « {word} » le lancent ; « {xword} » lance {xname} ; le nom anglais marche toujours",
            label(MV)==name and a is not None and a["ref"]==MV.bl_idname and b is not None and b["ref"]==MV.bl_idname
            and c_ is not None and c_["ref"]==EXT.bl_idname and label(EXT)==xname and d is not None and d["ref"]==MV.bl_idname,
            (label(MV),a and a["label"],b and b["label"],c_ and c_["label"],d and d["label"]))
        missing=[c.__name__ for c in tools if c.bl_idname.startswith("dessin.") and not c.bl_idname.startswith("dessin.subdc_") and "sel" not in c.bl_idname
                 and c.__dict__.get("dessin_en_label") is None and m.cmd_clean_label(c.bl_label) in m.LANG_LABELS[code]]
        rec(SEC,f"{code} : tous les outils qui ont un nom dans cette langue le portent",not missing,missing[:4])
    setlang('DE')
    e=first("k"); f=first("c")
    rec(SEC,"allemand : k lance Kreis (alias d'AutoCAD allemand) ; l'alias anglais c reste utilisable pour le cercle",e["label"].startswith("Kreis") and f is not None and f["label"].startswith("Kreis"),(e["label"],f and f["label"]))
    setlang('ES')
    rec(SEC,"espagnol : c = Círculo, d = Mover (DESPLAZA), cp = Copiar",first("c")["label"].startswith("Círculo") and first("d")["label"]=="Mover" and first("cp")["label"]=="Copiar",(first("c")["label"],first("d")["label"],first("cp")["label"]))
    setlang('RU')
    rec(SEC,"russe : les commandes se tapent en cyrillique (круг -> Круг, обрезать -> Обрезать)",first("круг")["label"].startswith("Круг") and first("обрезать")["label"]=="Обрезать",(first("круг")["label"],first("обрезать")["label"]))
    setlang('ZH')
    rec(SEC,"chinois : noms traduits, alias anglais d'AutoCAD et de Rhino (l -> 多段线, tr -> 修剪), et le nom chinois se retrouve aussi",
        first("l")["label"]=="多段线" and first("tr")["label"]=="修剪" and first("修剪")["label"]=="修剪",(first("l")["label"],first("tr")["label"]))
    setlang('JA'); e=first("トリム")
    rec(SEC,"japonais et coréen : le nom dans la langue retrouve la commande",e is not None and e["label"]=="トリム",e and e["label"])
    setlang('KO'); e=first("자르기")
    rec(SEC,"... (coréen : 자르기)",e is not None and e["label"]=="자르기",e and e["label"])
    # vues et commandes générales
    setlang('DE')
    rec(SEC,"allemand : vues et commandes générales traduites (Oben, Rückgängig)",any(s["label"]=="Oben" for s in m.cmd_suggest("oben")) and first("rückgängig")["label"]=="Rückgängig",[s["label"] for s in m.cmd_suggest("oben")][:3])
    # alias de l'utilisateur : toujours prioritaires, dans toutes les langues
    m.ALIAS_STATE["test"]=[("k","Copy")]; m.alias_changed()
    rec(SEC,"un alias de l'utilisateur passe avant l'alias de la langue (k -> Kopieren)",first("k")["label"]=="Kopieren",first("k")["label"])
    m.ALIAS_STATE["test"]=None; m.alias_changed()
    # doublons d'alias dans une même langue
    for code in m.LANG_CODES:
        seen={}; dup=[]
        for lab,al in m.LANG_ALIASES[code].items():
            for a in al.split():
                if a in seen: dup.append((a,seen[a],lab))
                seen[a]=lab
        rec(SEC,f"{code} : aucun alias de la langue ne désigne deux commandes",not dup,dup[:3])
    # la cause de la latence : des suggestions gardées en mémoire dans l'ancienne langue survivaient au réenregistrement
    src=open(_os.path.join(_os.path.dirname(_os.path.abspath(_SRC)),"registration.py"),encoding="utf-8").read()
    i=src.index("apply_language(list(classes) + tool_classes)"); j=src.index("rc_bases =",i)
    rec(SEC,"à chaque enregistrement de l'add-on, suggestions et phrases gardées en mémoire sont oubliées","alias_changed()" in src[i:j] and "language_caches_clear()" in src[i:j])
    setlang('EN'); m.cmd_suggest("extend"); m.PREF_DEFAULTS["language"]='DE'; m.apply_language(allc)      # langue changée, mémoire pas encore vidée
    stale=first("extend")["label"]
    m.alias_changed(); m.language_caches_clear()
    rec(SEC,"... sans ce vidage la ligne de commande répondait dans l'ancienne langue ; avec lui, dans la nouvelle",stale=="Extend Curve" and first("extend")["label"]=="Kurve verlängern",(stale,first("extend")["label"]))
finally:
    m.ALIAS_STATE["test"]=None
    setlang('EN')
summary()
