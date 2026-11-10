import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
import bpy,sys,importlib.util,math,functools
from types import SimpleNamespace as NS
from mathutils import Vector
sp=importlib.util.spec_from_file_location('m',_SRC);m=importlib.util.module_from_spec(sp);sys.modules['m']=m;sp.loader.exec_module(m)
bpy.ops.wm.read_factory_settings(use_empty=True); m.register()
P=m.parse_coord
ok=True
def chk(name,got,exp):
    global ok
    good = (got is None and exp is None) or (got is not None and exp is not None and got[0]==exp[0] and all(abs(a-b)<1e-9 for a,b in zip(got[1],exp[1])))
    ok&=good; print("OK " if good else "BAD",name,got)
chk("#10,5",P("#10,5"),(True,(10,5,0)))
chk("#1,2,3",P("#1,2,3"),(True,(1,2,3)))
chk("@3,-4",P("@3,-4"),(False,(3,-4,0)))
chk("10<90",P("10<90"),(False,(0,10,0)))
chk("@5<180",P("@5<180"),(False,(-5,0,0)))
chk("2,5;3,5 (virgule décimale)",P("2,5;3,5"),(True,(2.5,3.5,0)))
chk("incomplet #10,",P("#10,"),None)
chk("incomplet #",P("#"),None)
chk("unités mm",P("#10,5",0.001),(True,(0.01,0.005,0)))
# méthodes avec faux self
B=m.DessinBase
def mk(points):
    s=NS(coord='',coord_pt=None,typed=['','',''],field=0,points=points,axis=2,unit_f=1.0,cur=None)
    for n in ('coord_target','coord_update'): setattr(s,n,functools.partial(getattr(B,n),s))
    s.handle_coord=functools.partial(B.handle_coord,s)
    return s
def ev(ch,t='X'): return NS(value='PRESS',ctrl=False,alt=False,oskey=False,type=t,unicode=ch)
def typ(s,txt):
    for c in txt: assert s.handle_coord(ev(c)),c
s=mk([]); typ(s,"#10,5"); print(s.coord,s.coord_pt); ok&= tuple(s.cur)==(10,5,0)
s=mk([Vector((1,1,0))]); typ(s,"@3,4"); ok&= (s.coord_pt-Vector((4,5,0))).length<1e-9; print(s.coord_pt)
s=mk([Vector((1,1,0))]); s.typed[0]="5"; typ(s,"<90"); ok&= (s.coord_pt-Vector((1,6,0))).length<1e-9; print("5<90",s.coord_pt)
s=mk([Vector((0,0,0))]); s.typed[0]="2,5"; typ(s,";3"); ok&= (s.coord_pt-Vector((2.5,3,0))).length<1e-9; print("2,5;3",s.coord_pt)
s=mk([]); print("chiffre sans préfixe consommé ?",s.handle_coord(ev('5'))); ok&= not s.handle_coord(ev('5'))
s=mk([Vector()]); typ(s,"@1,2"); s.handle_coord(ev('', 'BACK_SPACE')); print(repr(s.coord)); s.handle_coord(ev('', 'ESC')); ok&= s.coord=='' and s.coord_pt is None
print("TOUT OK" if ok else "ECHEC")
