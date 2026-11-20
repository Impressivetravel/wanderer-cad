# Commande en cours (rectangle, plan de coupe...) : Maj enfoncé au-dessus d'un autre éditeur (Outliner...) lui est rendu ;
# dans la vue, il met toujours l'aperçu à jour tout de suite.
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
src=open(_os.path.join(_HERE,'t_pushpull.py')).read()
exec(src[src.index("\n")+1:src.index("# ---------------- 1. PushPull")])
clear()
for cls in (m.DESSIN_OT_rectangle, m.DESSIN_OT_clip_plane):
    o,r=start(cls); E(o,('c',0,0),('m',5,3))
    inside=type(o).modal(o,ctx,ev('LEFT_SHIFT','PRESS',*scr(5,3),shift=True))
    out=type(o).modal(o,ctx,ev('LEFT_SHIFT','PRESS',W+400,H/2,shift=True))
    chk(f"{cls.bl_label} : Maj dans la vue garde l'aperçu à jour (pris par la commande)", 'RUNNING_MODAL' in inside, inside)
    chk(f"{cls.bl_label} : Maj au-dessus d'un autre éditeur lui est rendu", out=={'PASS_THROUGH'}, out)
    E(o,'ESC')
print("RESULTAT",sum(res),"/",len(res))
