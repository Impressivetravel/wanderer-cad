import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
exec(open(_os.path.join(_HERE,'prec_lib.py')).read())
import types, re, glob
SEC="Épaisseur des traits selon l'écran"
G=m.line_px.__globals__; _real=G['bpy']
class _Bpy:
    def __init__(self,ui,dpi,ps): self.context=types.SimpleNamespace(preferences=types.SimpleNamespace(system=types.SimpleNamespace(ui_scale=ui,dpi=dpi,pixel_size=ps)))
    def __getattr__(self,k): return getattr(_real,k)
def screen(ui,ps):
    G['bpy']=_Bpy(ui,int(round(72*ui)),ps)       # Blender : dpi = 72 x ui_scale, toujours
try:
    # (nom, ui_scale, pixel_size, épaisseur attendue d'un trait de 2 px, ancienne épaisseur)
    CASES=[("écran ordinaire 100 %",1.0,1.0,2.0),
           ("Windows 150 %",1.5,1.0,3.0),
           ("Windows 200 % (4K) ou Retina",2.0,2.0,4.0),
           ("Windows 200 % + Resolution Scale 1.3",2.6,2.0,5.2),
           ("Windows 250 % + Resolution Scale 1.5",3.75,3.0,7.5)]
    for name,ui,ps,exp in CASES:
        screen(ui,ps)
        got=m.line_px(2.0); old=2.0*m.px_scale()
        rec(SEC,f"{name} : trait d'aperçu de 2 px -> {exp:g} px (avant : {old:.1f} px)",abs(got-exp)<1e-6 and got<=old+1e-9,f"{got:g} px")
        rec(SEC,f"{name} : l'épaisseur suit la densité, pas son carré",abs(m.line_px(1.0)-max(1.0,ui))<1e-6 and abs(m.ui_density()-ui)<1e-6,f"line_px(1) = {m.line_px(1.0):g}, densité {m.ui_density():g}")
    screen(2.0,2.0)
    rec(SEC,"Les tailles (marqueurs, poignées) ne changent pas : px_scale() garde sa valeur sur Retina",abs(m.px_scale()-4.0)<1e-6,f"{m.px_scale():g}")
    screen(0.5,1.0)
    rec(SEC,"Interface réduite (Resolution Scale < 1) : jamais moins de 1 px",m.line_px(1.0)==1.0 and m.line_px(0.2)==1.0,f"{m.line_px(1.0):g}")
finally:
    G['bpy']=_real
rec(SEC,"Sans écran (tests) : densité 1, trait de 2 px = 2 px",m.line_px(2.0)==2.0,f"{m.line_px(2.0):g}")
# plus aucun trait dont l'épaisseur passe par px_scale() (ni par une variable sc qui en vient)
src_dir=_os.path.dirname(_SRC); bad=[]
for f in sorted(glob.glob(_os.path.join(src_dir,"*.py"))):
    for i,l in enumerate(open(f,encoding="utf-8"),1):
        if "line_width_set(" in l and re.search(r"px_scale|\bsc\b",l): bad.append(f"{_os.path.basename(f)}:{i}")
rec(SEC,"Aucun line_width_set ne dépend plus de px_scale()",not bad,bad or "0 occurrence")
summary()
