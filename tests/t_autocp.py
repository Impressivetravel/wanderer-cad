import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
import sys
import bpy, sys, importlib.util
from mathutils import Vector
spec=importlib.util.spec_from_file_location("cad",_SRC); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
m.register()
sc=bpy.context.scene
print("props", sc.dessin.auto_cplane, sc.dessin.auto_cplane_sticky)
print("classes", m.DESSIN_MT_auto_cplane.bl_idname, hasattr(bpy.types,"DESSIN_MT_auto_cplane"))
bpy.ops.mesh.primitive_plane_add(size=2)
p=bpy.context.object; p.rotation_euler=(1.0,0.3,0.2); bpy.context.view_layer.update()
f=m.autocp_frame_object(p); print("plane frame", f is not None, f[3] if f else None)
bpy.ops.mesh.primitive_cube_add(); c=bpy.context.object
print("cube frame", m.autocp_frame_object(c))
# edit mode face
import bmesh
bpy.ops.object.select_all(action='DESELECT'); c.select_set(True); bpy.context.view_layer.objects.active=c
bpy.ops.object.mode_set(mode='EDIT'); bm=bmesh.from_edit_mesh(c.data)
for f_ in bm.faces: f_.select=False
top=max(bm.faces,key=lambda f:f.calc_center_median().z); top.select=True
fr=m.autocp_frame_faces(c); print("face frame", [round(v,3) for v in fr[3]], [round(v,3) for v in fr[0]])
for f_ in bm.faces: f_.select=True
print("all faces", m.autocp_frame_faces(c))
bpy.ops.object.mode_set(mode='OBJECT')
print("timer", bpy.app.timers.is_registered(m.autocp_timer))
print("cmd", any(a[0]=="Auto CPlane" for a in m.CMD_ACTIONS))
m.unregister(); print("unreg ok", not bpy.app.timers.is_registered(m.autocp_timer))
