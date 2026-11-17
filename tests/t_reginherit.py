import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
# Garde-fou : aucune classe enregistrée ne doit hériter d'une autre classe enregistrée (Blender perd alors la classe Python du parent)
import ast, sys
src=open(_SRC,encoding='utf-8').read(); t=ast.parse(src)
reg=set()
for n in ast.walk(t):
    if isinstance(n,ast.Assign) and any(getattr(x,'id','')=='classes' for x in n.targets) and isinstance(n.value,(ast.Tuple,ast.List)):
        reg|={ast.unparse(e) for e in n.value.elts}
cls={n.name:n for n in t.body if isinstance(n,ast.ClassDef)}
def bases(name,seen=()):
    out=set()
    for b in cls[name].bases:
        bn=ast.unparse(b)
        if bn in cls and bn not in seen: out|={bn}|bases(bn,seen+(bn,))
    return out
bad=[(c,sorted(bases(c)&reg)) for c in sorted(reg) if c in cls and bases(c)&reg]
print("classes enregistrées:",len(reg),"| héritages fautifs:",bad or "aucun")
