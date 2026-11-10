import bpy,sys,importlib.util,types,traceback,math
from types import SimpleNamespace as NS
from mathutils import Matrix, Vector
SRC=sys.argv[1] if len(sys.argv)>1 and sys.argv[1].endswith('.py') else _SRC
sp=importlib.util.spec_from_file_location('m',SRC);m=importlib.util.module_from_spec(sp);sys.modules['m']=m;sp.loader.exec_module(m)
bpy.ops.wm.read_factory_settings(use_empty=True); m.register()
_MIR={}
_BUILDING=set()
def remap(v,new):
    fv=v.__code__.co_freevars
    if not fv: return v
    cl=list(v.__closure__)
    for i,name in enumerate(fv):
        if name=='__class__':
            c0=cl[i].cell_contents; mm=_MIR.get(c0) or (mirror(c0) if c0 is not None and c0 not in _BUILDING else None)
            cl[i]=types.CellType(mm if mm is not None else new)
        elif name=='orig' and isinstance(cl[i].cell_contents,types.FunctionType): cl[i]=types.CellType(remap(cl[i].cell_contents,new))
    f=types.FunctionType(v.__code__,v.__globals__,v.__name__,v.__defaults__,tuple(cl)); return f
def mirror(cls):
    if cls in _MIR: return _MIR[cls]
    if cls in (object,) or cls.__module__.startswith('bpy') or cls is bpy.types.Operator:
        return None
    bases=tuple(b for b in (mirror(b) for b in cls.__bases__) if b is not None) or (object,)
    d={}
    new=type(cls.__name__+"_M",bases,d)
    _MIR[cls]=new
    for k,v in vars(cls).items():
        if k in ('__dict__','__weakref__','bl_rna','__annotations__'): continue
        if isinstance(v,types.FunctionType):
            setattr(new,k,remap(v,new))
        elif isinstance(v,(classmethod,staticmethod,property)) or not k.startswith('__'):
            try: setattr(new,k,v)
            except Exception: pass
    # propriétés bpy.props -> valeurs par défaut
    for c in reversed(cls.__mro__):
        for k,v in getattr(c,'__annotations__',{}).items() if isinstance(getattr(c,'__annotations__',None),dict) else []:
            kw=getattr(v,'keywords',None)
            if kw is not None and not hasattr(new,k) or (kw is not None and isinstance(getattr(new,k,None),type(v))):
                dv=kw.get('default', 0 if 'Int' in str(getattr(v,'function','')) else (0.0 if 'Float' in str(getattr(v,'function','')) else ('' if 'String' in str(getattr(v,'function','')) else False)))
                if 'Enum' in str(getattr(v,'function','')) and 'default' not in kw:
                    items=kw.get('items'); dv=items[0][0] if isinstance(items,(list,tuple)) and items else ''
                setattr(new,k,dv)
    _MIR[cls]=new; return new
W,H=1000,1000
S=10.0   # px par unité
VM=Matrix.Translation((0,0,-50))
WM=Matrix(((S*2/W,0,0,0),(0,S*2/H,0,0),(0,0,-0.01,0),(0,0,0,1)))
rv3d=bpy.types.RegionView3D if False else None
class RV(NS):
    def as_pointer(self): return 13
rv3d=RV(view_matrix=VM,window_matrix=WM,perspective_matrix=WM@VM,is_perspective=False,view_perspective='ORTHO',
        view_rotation=Matrix().to_quaternion(),is_orthographic_side_view=False,view_location=Vector((0,0,0)),view_distance=50.0,
        view_camera_zoom=0,view_camera_offset=(0,0))
class Region(NS):
    def as_pointer(self): return 11
    def tag_redraw(self): pass
region=Region(type='WINDOW',x=0,y=0,width=W,height=H,data=rv3d)
space=NS(type='VIEW_3D',shading=NS(type='SOLID',show_xray=False,xray_alpha=1.0),overlay=NS(show_overlays=True),region_3d=rv3d,
         show_gizmo=True,clip_start=0.01,clip_end=1000,lens=50, local_view=None)
class Area(NS):
    def as_pointer(self): return 7
    def tag_redraw(self): pass
    def header_text_set(self,*a): pass
area=Area(type='VIEW_3D',x=0,y=0,width=W,height=H,regions=[region],spaces=NS(active=space),ui_type='VIEW_3D')
class Ctx:
    def __init__(self): self.__dict__['_o']={'area':area,'region':region,'space_data':space,'region_data':rv3d,
        'window_manager':NS(event_timer_add=lambda *a,**k: None,event_timer_remove=lambda *a,**k: None,modal_handler_add=lambda s: None,
                            windows=bpy.context.window_manager.windows,invoke_props_dialog=lambda *a,**k:{'RUNNING_MODAL'},
                            clipboard=''),
        'window':None}
    def __getattr__(self,k):
        o=self.__dict__['_o']
        if k in o: return o[k]
        return getattr(bpy.context,k)
    def temp_override(self,**k): return bpy.context.temp_override(**{a:b for a,b in k.items() if a not in('area','region','window')})
ctx=Ctx()
def scr(x,y): return (x*S+W/2, y*S+H/2)
def ev(t,v,x,y,**k):
    d=dict(type=t,value=v,mouse_x=int(x),mouse_y=int(y),mouse_region_x=int(x),mouse_region_y=int(y),mouse_prev_x=int(x),mouse_prev_y=int(y),
           shift=False,ctrl=False,alt=False,oskey=False,is_repeat=False,unicode='',ascii='',pressure=1.0,is_tablet=False)
    d.update(k); return NS(**d)
def make(cls):
    M=mirror(cls); o=M()
    o.report=lambda lv,msg: o._reports.append((list(lv)[0],msg)); o._reports=[]
    o.bl_idname=cls.bl_idname
    return o
