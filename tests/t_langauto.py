import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
# « Follow Blender's language » : la langue du module suit celle de l'interface de Blender
res=[]
def chk(n,ok,info=""): res.append(bool(ok)); print(("OK  " if ok else "BAD ")+n, info)
chk("l'option existe, en tête de liste", m.LANGUAGE_ITEMS[0][0]=='AUTO')
cases={"fr_FR":'FR',"de_DE":'DE',"es":'ES',"it_IT":'IT',"pt_BR":'PT',"pt_PT":'PT',"ru_RU":'RU',"tr_TR":'TR',"zh_HANS":'ZH',"ja_JP":'JA',"ko_KR":'KO',
       "en_US":'EN',"nl_NL":'EN',"pl_PL":'EN',"":'EN'}
bad=[(k,m.ui_lang_code(k)) for k,v in cases.items() if m.ui_lang_code(k)!=v]
chk("les langues de Blender sont reconnues (néerlandais, polonais... : anglais)", not bad, bad)
m.PREF_DEFAULTS["language"]='AUTO'; m.language_caches_clear()
chk("Blender en anglais (ou interface non traduite) : le module est en anglais", m.lang()=='EN', m.lang())
chk("... et les noms restent en anglais", m.tr_label("Top")=="Top")
m.PREF_DEFAULTS["language"]='FR'; m.language_caches_clear()
chk("une langue choisie à la main reste prioritaire", m.lang()=='FR' and m.tr_label("Top")=="Dessus")
m.PREF_DEFAULTS["language"]='EN'; m.language_caches_clear()
print("RESULTAT",sum(res),"/",len(res))
