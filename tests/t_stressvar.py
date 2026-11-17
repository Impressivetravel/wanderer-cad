import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
import sys
VAR=sys.argv[2] if len(sys.argv)>2 else 'units'
exec(open(_os.path.join(_HERE,'harness.py')).read())
import math, random
from mathutils import Euler, Quaternion
def VAR_HOOK(box):
    if box is None: return
    rect=bpy.data.objects.get("Rect")
    if VAR=='xform':
        box.rotation_euler=Euler((0.4,0.7,1.1)); box.scale=(1.5,0.6,-0.8)          # échelle non uniforme et négative
        if rect is not None:
            rect.parent=box; rect.rotation_euler=Euler((0.2,0.0,0.9)); rect.scale=(2.0,0.5,1.0)
    if VAR=='heavy':
        import bmesh
        if not bpy.data.objects.get("H0000"):
            random.seed(1)
            for i in range(400):
                me=bpy.data.meshes.new("H%04d"%i); bm=bmesh.new(); bmesh.ops.create_cube(bm,size=0.8); bmesh.ops.subdivide_edges(bm,edges=bm.edges[:],cuts=3,use_grid_fill=True); bm.to_mesh(me); bm.free()
                o=bpy.data.objects.new("H%04d"%i,me); bpy.context.scene.collection.objects.link(o); o.location=(random.uniform(-40,40),random.uniform(-40,40),0)
if VAR=='units':
    us=bpy.context.scene.unit_settings; us.system='METRIC'; us.length_unit='MILLIMETERS'; us.scale_length=0.001
if VAR=='imperial':
    us=bpy.context.scene.unit_settings; us.system='IMPERIAL'; us.length_unit='INCHES'
if VAR=='persp':
    eye=Vector((30,-35,28)); tgt=Vector((0,0,0)); f=(tgt-eye).normalized(); r=f.cross(Vector((0,0,1))).normalized(); u=r.cross(f)
    R=Matrix((r,u,-f)).to_4x4(); VMp=R@Matrix.Translation(-eye)
    n_,fa=0.1,1000.0; t_=math.tan(math.radians(25)); 
    WMp=Matrix(((1/t_,0,0,0),(0,1/t_,0,0),(0,0,-(fa+n_)/(fa-n_),-2*fa*n_/(fa-n_)),(0,0,-1,0)))
    rv3d.view_matrix=VMp; rv3d.window_matrix=WMp; rv3d.perspective_matrix=WMp@VMp; rv3d.is_perspective=True; rv3d.view_perspective='PERSP'
    rv3d.view_rotation=R.to_3x3().transposed().to_quaternion(); rv3d.view_location=tgt; rv3d.view_distance=(eye-tgt).length
if VAR=='cplane':
    try:
        stc=m.cp_state(rv3d,create=True)
        x=Vector((1,1,0.3)).normalized(); z=x.cross(Vector((0,1,0.5))).normalized(); y=z.cross(x)
        stc["cur"]=(Vector((2,-3,4)),x,y,z)
    except Exception as e: print("cplane setup",e)
src=open(_os.path.join(_HERE,'t_stress.py')).read()
src="\n".join(l for l in src.split("\n") if "harness.py" not in l)
assert "    bpy.context.view_layer.update()\n    return box" in src
src=src.replace("    bpy.context.view_layer.update()\n    return box","    VAR_HOOK(box)\n    bpy.context.view_layer.update()\n    return box")
if VAR=='heavy':
    src=src.replace("    for o in list(bpy.data.objects): bpy.data.objects.remove(o)\n","    for o in [o for o in bpy.data.objects if not o.name.startswith('H0')]: bpy.data.objects.remove(o)\n",1)
exec(compile(src,'t_stress_'+VAR,'exec'))
