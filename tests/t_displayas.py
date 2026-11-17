import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
exec(open(_os.path.join(_HERE,'prec_lib.py')).read())
# Clic droit > Display As : Bounds / Wire / Solid / Textured, sans passer par les propriétés de l'objet
import types
SEC="Display As"
clear()
def box(n):
    me=bpy.data.meshes.new(n); me.from_pydata([(0,0,0),(1,0,0),(1,1,0)],[],[(0,1,2)]); o=bpy.data.objects.new(n,me); bpy.context.scene.collection.objects.link(o); return o
a,b,c=box("a"),box("b"),box("c")
a.select_set(True); b.select_set(True); bpy.context.view_layer.objects.active=a
rna=[i.identifier for i in bpy.types.Object.bl_rna.properties["display_type"].enum_items]
rec(SEC,"les quatre choix sont ceux de Blender, dans le même ordre",[i[0] for i in m.DISPLAY_AS_ITEMS]==rna,rna)
r=bpy.ops.dessin.display_as(type='WIRE')
rec(SEC,"Wire s'applique à tous les objets sélectionnés, pas aux autres",'FINISHED' in r and a.display_type=='WIRE' and b.display_type=='WIRE' and c.display_type=='TEXTURED',(a.display_type,b.display_type,c.display_type))
class Lay:
    def __init__(s): s.items=[]
    def operator(s,idname,text="",icon='NONE'):
        p=types.SimpleNamespace(); s.items.append((idname,text,icon,p)); return p
    def menu(s,idname,icon='NONE'): s.items.append(("menu",idname,icon,None))
    def separator(s): pass
lay=Lay(); m.DESSIN_MT_ctx_display.draw(types.SimpleNamespace(layout=lay),bpy.context)
rec(SEC,"le sous-menu liste Bounds, Wire, Solid, Textured et marque l'affichage en cours (Wire)",
    [(t,p.type) for _i,t,_ic,p in lay.items]==[("Bounds",'BOUNDS'),("Wire",'WIRE'),("Solid",'SOLID'),("Textured",'TEXTURED')] and [ic for _i,_t,ic,_p in lay.items]==['BLANK1','LAYER_ACTIVE','BLANK1','BLANK1'],[(t,ic) for _i,t,ic,_p in lay.items])
lay=Lay(); m.ctx_extra_items(lay,bpy.context)
rec(SEC,"le clic droit en mode objet propose Select, puis Display As, puis Material",[x[1] for x in lay.items if x[0]=="menu"][:3]==["DESSIN_MT_ctx_select","DESSIN_MT_ctx_display","DESSIN_MT_ctx_material"],[x[1] for x in lay.items])
for o in (a,b): o.select_set(False)
lay=Lay(); m.ctx_extra_items(lay,bpy.context)
rec(SEC,"sans sélection, Display As n'est pas proposé","DESSIN_MT_ctx_display" not in [x[1] for x in lay.items],[x[1] for x in lay.items])
a.select_set(True); r=bpy.ops.dessin.display_as(type='TEXTURED')
rec(SEC,"Textured remet l'affichage normal",a.display_type=='TEXTURED' and b.display_type=='WIRE')
summary()
