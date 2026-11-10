import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
import traceback
reset=None
cls=m.DESSIN_OT_cotation
o=make(cls)
r=cls.invoke(o,ctx,ev('NONE','NOTHING',*scr(0,0))); print(r)
for p in [(0,0),(10,0)]:
    sx,sy=scr(*p)
    for e in (ev('MOUSEMOVE','NOTHING',sx,sy),ev('LEFTMOUSE','PRESS',sx,sy),ev('LEFTMOUSE','RELEASE',sx,sy)):
        r=cls.modal(o,ctx,e); print(p,e.type,sorted(r))
sx,sy=scr(5,4)
print(cls.modal(o,ctx,ev('MOUSEMOVE','NOTHING',sx,sy)))
try:
    print("ESC",cls.modal(o,ctx,ev('ESC','PRESS',sx,sy)))
except Exception: traceback.print_exc()
print("done", len(o.points) if hasattr(o,'points') else '')
