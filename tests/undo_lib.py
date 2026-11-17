# outils communs : empreinte complète de la scène, protocole undo/redo, actions de suivi
import zlib, inspect, io, contextlib
import numpy as np
def _r(v,n=5):
    try: return tuple(round(float(x),n)+0.0 for x in v)
    except TypeError: return round(float(v),n)+0.0
def data_fp(o):
    d=o.data
    if o.type=='MESH':
        nv=len(d.vertices); co=np.empty(nv*3,dtype=np.float32); d.vertices.foreach_get('co',co)
        return ('M',nv,len(d.edges),len(d.polygons),zlib.crc32(np.round(co,4).tobytes()))
    if o.type=='CURVE':
        out=[]
        for sp in d.splines:
            if sp.type=='BEZIER':
                pts=tuple((_r(p.co,4),_r(p.handle_left,4),_r(p.handle_right,4)) for p in sp.bezier_points)
            else:
                pts=tuple(_r(p.co,4) for p in sp.points)
            out.append((sp.type,bool(sp.use_cyclic_u),getattr(sp,'order_u',0),pts))
        return ('C',d.dimensions,round(d.extrude,5),round(d.bevel_depth,5),d.fill_mode,tuple(out))
    if o.type=='FONT': return ('F',d.body,round(d.size,5))
    if o.type=='EMPTY': return ('E',o.instance_type,o.instance_collection.name if o.instance_collection else None)
    return (o.type,)
def props_fp(idb):
    out=[]
    for k in sorted(idb.keys()):
        if k in ('_RNA_UI','cycles'): continue
        v=idb[k]
        try:
            v=v.to_dict() if hasattr(v,'to_dict') else (list(v) if hasattr(v,'__len__') and not isinstance(v,str) else v)
        except Exception: v=str(v)
        if isinstance(v,float): v=round(v,5)
        if isinstance(v,list): v=[round(x,5) if isinstance(x,float) else x for x in v]
        out.append((k,repr(v)))
    return tuple(out)
def snapshot(bpy,sel=False):
    S={}
    for o in bpy.data.objects:
        S['o:'+o.name]=(o.type,_r([x for row in o.matrix_world for x in row],4),data_fp(o),props_fp(o),
                        tuple(sorted(c.name for c in o.users_collection)),o.parent.name if o.parent else None,
                        o.hide_viewport,o.hide_select,o.display_type,
                        tuple((md.type,md.name) for md in o.modifiers),o.data.name if o.data else None)
        if sel: S['s:'+o.name]=o.select_get() if o.name in bpy.context.view_layer.objects else None
    for c in bpy.data.collections:
        S['c:'+c.name]=(tuple(sorted(x.name for x in c.objects)),tuple(sorted(x.name for x in c.children)),c.hide_viewport,props_fp(c))
    S['#meshes']=tuple(sorted(x.name for x in bpy.data.meshes if x.users or x.use_fake_user))
    S['#curves']=tuple(sorted(x.name for x in bpy.data.curves if x.users or x.use_fake_user))
    S['#scene']=props_fp(bpy.context.scene)
    return S
def diff(a,b,limit=4):
    ks=[k for k in sorted(set(a)|set(b)) if a.get(k)!=b.get(k)]
    out=[]
    for k in ks[:limit]:
        x,y=a.get(k),b.get(k)
        if x is None: out.append(f"+{k}")
        elif y is None: out.append(f"-{k}")
        else:
            if isinstance(x,tuple) and isinstance(y,tuple) and len(x)==len(y):
                idx=[i for i,(p,q) in enumerate(zip(x,y)) if p!=q]
                out.append(f"~{k}[champs {idx}] {str([x[i] for i in idx])[:90]} -> {str([y[i] for i in idx])[:90]}")
            else: out.append(f"~{k}")
    if len(ks)>limit: out.append(f"... +{len(ks)-limit}")
    return out
