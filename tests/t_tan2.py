import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
import bpy,sys,importlib.util,numpy as np
from types import SimpleNamespace as NS
from mathutils import Vector
sp=importlib.util.spec_from_file_location('m',_SRC);m=importlib.util.module_from_spec(sp);sys.modules['m']=m;sp.loader.exec_module(m)
circ=("C",)
ns=NS(points=[],cur=Vector((1,2,0)),typed=['',''],lock=None,_tan_info=("first",circ),update_preview=lambda c:None)
ns.effective_point=lambda: ns.cur.copy()
m.PolylineBase.add_point(ns,None)
print("pend after 1st:",ns.tan_pend is circ, tuple(ns.tan_p0))
ns.cur=Vector((9,9,0)); ns._tan_info=("common",Vector((0,1,0)))
m.PolylineBase.add_point(ns,None)
print("pend cleared after 2nd:",ns.tan_pend is None, len(ns.points))
# premier point sans Tan : pas de mémoire
ns2=NS(points=[],cur=Vector((1,2,0)),typed=['',''],lock=None,_tan_info=None,update_preview=lambda c:None); ns2.effective_point=lambda: ns2.cur.copy()
m.PolylineBase.add_point(ns2,None); print("no pend:",ns2.tan_pend is None)
