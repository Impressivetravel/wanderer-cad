import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
import json, types
C=bpy.context
res=[]
def chk(name,ok,info=""):
    res.append(bool(ok)); print(("OK  " if ok else "BAD ")+name, info)
root=C.scene.collection
for n in ("Murs","Portes","Mobilier"):
    c=bpy.data.collections.new(n); root.children.link(c)
sub=bpy.data.collections.new("Chaises"); bpy.data.collections["Mobilier"].children.link(sub)
ob=bpy.data.objects.new("Cube", bpy.data.meshes.new("c")); bpy.data.collections["Murs"].objects.link(ob)
st=C.scene.dessin
calls=[]
class L:
    def __init__(self, parent=None): object.__setattr__(self,"_units",None); object.__setattr__(self,"_parent",parent)
    def __setattr__(self,n,v):
        object.__setattr__(self,n,v)
    def _cell(self):
        p=self
        while p is not None:
            if p._units is not None: return p._units
            p=p._parent
        return None
    def row(self,*a,**k): return L(self)
    column=box=split=row
    def prop(self,owner,prop,*a,**k):
        calls.append(("prop",prop,self._cell(),getattr(owner,"name",None) or getattr(getattr(owner,"id_data",None),"name",None))); return L(self)
    def operator(self,idn,*a,**k):
        o=types.SimpleNamespace(); calls.append(("op",idn,self._cell(),k.get("text"),o,k.get("icon"))); return o
    def __getattr__(self,n):
        if n=="ui_units_x": return 0
        return lambda *a,**k: L(self)
    @property
    def ui_units_x(self): return self._units
    @ui_units_x.setter
    def ui_units_x(self,v): object.__setattr__(self,"_units",v)
def draw():
    calls.clear(); m.DESSIN_PT_layers.draw(types.SimpleNamespace(layout=L()), C)
draw()
hdr=[c for c in calls if c[0]=="op" and c[1]=="dessin.layer_col_resize"]
cols=[c[4].column for c in hdr]
exp=["name"]+[c[0] for c in m.LAYER_COLUMNS[1:-1] if getattr(st,c[3])]+["color"]
chk("en-tête : Layer, colonnes affichées, Color", cols==exp, cols)
chk("en-tête : titres Layer et Color", hdr[0][3]=="Layer" and hdr[-1][3]=="Color", [h[3] for h in hdr])
# ordre dans une ligne : nom, interrupteurs, couleur à droite
seq=[]
started=False
for c in calls:
    if c[0]=="op" and c[1]=="dessin.layer_click" and c[3]=="Murs": started=True; seq=["name"]; continue
    if started:
        if c[0]=="op" and c[1]=="dessin.layer_click": break
        if c[0]=="prop": seq.append(c[1])
chk("couleur du calque à droite, après les interrupteurs", seq and seq[-1]=="color" and seq.index("color")>1, seq)
w=m.layer_col_widths(st)
cell_color=[c[2] for c in calls if c[0]=="prop" and c[1]=="color"]
cell_name=[c[2] for c in calls if c[0]=="op" and c[1]=="dessin.layer_click"]
chk("largeurs par défaut appliquées", all(x==w["color"] for x in cell_color) and all(x==w["name"] for x in cell_name), (cell_color[:2],cell_name[:2]))
# redimensionner : clic sur le titre, souris à droite de 60 px, clic
op=make(m.DESSIN_OT_layer_col_resize); op.column="name"
class W:
    def cursor_modal_set(self,*a): pass
    def cursor_modal_restore(self): pass
class WS:
    def status_text_set(self,*a): pass
class Reg:
    def tag_redraw(self): pass
cx=types.SimpleNamespace(scene=C.scene, region=Reg(), preferences=types.SimpleNamespace(system=types.SimpleNamespace(ui_scale=1.0)),
    window=W(), workspace=WS(), window_manager=types.SimpleNamespace(modal_handler_add=lambda o: None))
ev=lambda t,v,x,ctrl=False: types.SimpleNamespace(type=t,value=v,mouse_x=x,ctrl=ctrl,oskey=False)
r=type(op).invoke(op,cx,ev('LEFTMOUSE','RELEASE',500))
type(op).modal(op,cx,ev('MOUSEMOVE','NOTHING',560))
chk("tirer à droite élargit la colonne", abs(m.layer_col_widths(st)["name"]-(w["name"]+3))<1e-6, m.layer_col_widths(st)["name"])
r=type(op).modal(op,cx,ev('LEFTMOUSE','PRESS',560))
chk("clic : largeur gardée", r=={'FINISHED'} and abs(m.layer_col_widths(st)["name"]-(w["name"]+3))<1e-6)
draw()
chk("la liste suit la nouvelle largeur", all(c[2]==w["name"]+3 for c in calls if c[0]=="op" and c[1]=="dessin.layer_click"))
op=make(m.DESSIN_OT_layer_col_resize); op.column="color"
type(op).invoke(op,cx,ev('LEFTMOUSE','RELEASE',500)); type(op).modal(op,cx,ev('MOUSEMOVE','NOTHING',300))
chk("tirer à gauche : jamais sous le minimum", abs(m.layer_col_widths(st)["color"]-m.LAYER_COL_MIN["color"])<1e-6, m.layer_col_widths(st)["color"])
r=type(op).modal(op,cx,ev('ESC','PRESS',300))
chk("Échap : largeur d'avant", r=={'CANCELLED'} and abs(m.layer_col_widths(st)["color"]-w["color"])<1e-6)
op=make(m.DESSIN_OT_layer_col_resize); op.column="name"
type(op).invoke(op,cx,ev('LEFTMOUSE','RELEASE',500,ctrl=True))
chk("Ctrl+clic : largeur par défaut", abs(m.layer_col_widths(st)["name"]-8.0)<1e-6)
# objets affichés : mêmes colonnes
st.layer_show_objects=True; draw()
ocells=[c[2] for c in calls if c[0]=="op" and c[1]=="dessin.layer_object" and c[3]=="Cube"]
chk("lignes d'objets dans la colonne Layer", ocells and ocells[0]==8.0, ocells)
st.layer_col_render=True; draw()
cols=[c[4].column for c in calls if c[0]=="op" and c[1]=="dessin.layer_col_resize"]
chk("colonne ajoutée par le filtre", "render" in cols and cols[-1]=="color", cols)
# ---- liste longue : repli / dépli de tout dans l'en-tête, la liste défile, sa hauteur se règle
hcalls=[]
class HL:
    def row(self,*a,**k): return self
    def operator(self,idn,*a,**k):
        o=types.SimpleNamespace(); hcalls.append((idn,k.get("icon"),o)); return o
    def popover(self,*a,**k): hcalls.append(("popover",k.get("panel"),None))
m.DESSIN_PT_layers.draw_header_preset(types.SimpleNamespace(layout=HL()), C)
fa=[(c[1],c[2].action) for c in hcalls if c[0]=="dessin.layer_fold"]
chk("en-tête du panneau : Fold All et Unfold All, à côté du filtre", fa==[('TRIA_RIGHT','COLLAPSE_ALL'),('TRIA_DOWN','EXPAND_ALL')] and any(c[0]=="popover" for c in hcalls), fa)
for i in range(60):
    c=bpy.data.collections.new(f"Calque {i:02d}"); bpy.data.collections["Mobilier"].children.link(c)
st.layer_show_objects=False; st.layer_list_rows=20; st.layer_list_scroll=0.0
ents,_cut=m.layer_list_entries(C)
draw()
shown=[c for c in calls if c[0]=="op" and c[1] in ("dessin.layer_click","dessin.layer_current")]
chk("liste longue : 20 lignes montrées sur %d" % len(ents), len(shown)==20 and len(ents)>60, len(shown))
sc=[c for c in calls if c[0]=="op" and c[1]=="dessin.layer_scroll"]
chk("... flèches de défilement et position", len(sc)==2 and any(c[0]=="prop" and c[1]=="layer_list_scroll" for c in calls), len(sc))
chk("... poignée pour régler la hauteur", any(c[0]=="op" and c[1]=="dessin.layer_rows_resize" for c in calls))
o=make(m.DESSIN_OT_layer_scroll); o.rows=10; o.to='BY'; type(o).execute(o, C)
draw()
first=[c[3] for c in calls if c[0]=="op" and c[1]=="dessin.layer_click"][0]
chk("flèche bas : la liste descend de 10 lignes", first==ents[10][2].name, (first, ents[10][2].name))
o=make(m.DESSIN_OT_layer_scroll); o.to='BOTTOM'; type(o).execute(o, C)
draw()
last=[c[3] for c in calls if c[0]=="op" and c[1]=="dessin.layer_click"][-1]
chk("tout en bas : la dernière ligne est le dernier calque", last==ents[-1][2].name, (last, ents[-1][2].name))
o=make(m.DESSIN_OT_layer_rows_resize)
class Ev:
    def __init__(s,t,v,y): s.type=t; s.value=v; s.mouse_y=y; s.mouse_x=0
ctx2=types.SimpleNamespace(scene=C.scene, region=types.SimpleNamespace(tag_redraw=lambda: None), preferences=C.preferences,
    window=types.SimpleNamespace(cursor_modal_set=lambda *a: None, cursor_modal_restore=lambda: None),
    workspace=types.SimpleNamespace(status_text_set=lambda *a: None), window_manager=types.SimpleNamespace(modal_handler_add=lambda *a: None))
type(o).invoke(o, ctx2, Ev('LEFTMOUSE','PRESS',500))
type(o).modal(o, ctx2, Ev('MOUSEMOVE','NOTHING',500-200))
type(o).modal(o, ctx2, Ev('LEFTMOUSE','PRESS',500-200))
chk("poignée : tirer vers le bas agrandit la liste (+10 lignes pour 200 px)", st.layer_list_rows==30, st.layer_list_rows)
o=make(m.DESSIN_OT_layer_fold); o.action='COLLAPSE_ALL'; type(o).execute(o, C)
ents2,_c=m.layer_list_entries(C)
chk("Fold All : la liste se replie (sous-calques cachés)", len(ents2) < len(ents) and not any(e[2].name.startswith("Calque") for e in ents2), len(ents2))
draw()
chk("liste courte : plus de barre de défilement", not any(c[0]=="op" and c[1]=="dessin.layer_scroll" for c in calls))
o=make(m.DESSIN_OT_layer_fold); o.action='EXPAND_ALL'; type(o).execute(o, C)
# ---- comme dans Rhino : un clic sélectionne le calque, un double-clic en fait le calque courant (✓)
import time as _t
L_ = m.layer_click.__globals__ if hasattr(m, "layer_click") else m.DESSIN_OT_layer_click.invoke.__globals__
L_["_LAYERCOL"]["last"] = ("", 0.0)
vl = C.view_layer
cur0 = vl.active_layer_collection.name
class Ev2:
    shift = ctrl = alt = oskey = False
fakec = types.SimpleNamespace(view_layer=vl, scene=C.scene, mode='OBJECT', selected_objects=[])
def click(name):
    o = make(m.DESSIN_OT_layer_click); o.layer = name; return type(o).invoke(o, fakec, Ev2())
st.layer_sync_select = False
click("Portes")
chk("un clic sélectionne le calque sans le rendre courant", vl.active_layer_collection.name == cur0 and L_["_LAYERCOL"]["sel"] == ["Portes"],
    (vl.active_layer_collection.name, L_["_LAYERCOL"]["sel"]))
r = click("Portes")
chk("double-clic : calque courant (les objets créés y vont)", vl.active_layer_collection.name == "Portes" and 'FINISHED' in r,
    vl.active_layer_collection.name)
st.layer_list_scroll = 0.0
draw()
cur_ops = [c for c in calls if c[0] == "op" and c[1] == "dessin.layer_click" and c[3] == "Portes"]
others = [c for c in calls if c[0] == "op" and c[1] == "dessin.layer_click" and c[3] != "Portes"]
chk("le calque courant est marqué ✓ dans la liste, lui seul", cur_ops and cur_ops[0][5] == 'CHECKMARK' and all(c[5] != 'CHECKMARK' for c in others),
    [c[5] for c in cur_ops])
print("RESULTAT",sum(res),"/",len(res))
