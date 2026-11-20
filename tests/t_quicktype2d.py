# Quick Type in 2D views (issue #15) et Wireframe in 2D views
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE, 'harness.py')).read())
import sys, types
res = []
def chk(name, ok, info=""):
    res.append(bool(ok)); print(("OK  " if ok else "BAD ") + name, info)
cl = [v for k, v in sys.modules.items() if k.endswith(".command_line")][0]
P = m.PREF_DEFAULTS
class SH: type = 'SOLID'
def fake_area(persp, ptr=7):
    sp = types.SimpleNamespace(region_3d=types.SimpleNamespace(is_perspective=persp), shading=SH())
    return types.SimpleNamespace(type='VIEW_3D', spaces=types.SimpleNamespace(active=sp), as_pointer=lambda: ptr, tag_redraw=lambda: None)
top, persp = fake_area(False), fake_area(True)
P["cmd_type"] = False; P["cmd_type_ortho"] = False
chk("réglages par défaut : Quick Type éteint partout", not cl.quick_type_on(top) and not cl.quick_type_on(persp))
P["cmd_type_ortho"] = True
chk("Quick Type in 2D views : allumé en vue Top", cl.quick_type_on(top))
chk("... éteint en perspective (les lettres gardent les raccourcis Blender)", not cl.quick_type_on(persp))
op = make(m.DESSIN_OT_command_line); op.char = "l"
r = type(op).invoke(op, types.SimpleNamespace(area=persp), ev('L', 'PRESS', 10, 10))
chk("lettre tapée en perspective : rendue à Blender", r == {'CANCELLED', 'PASS_THROUGH'}, r)
P["cmd_type"] = True
chk("Quick Type à on : partout, comme avant", cl.quick_type_on(top) and cl.quick_type_on(persp))
P["cmd_type"] = False
st = types.SimpleNamespace(area=top)
chk("le bouton Quick Type s'allume en vue 2D", cl.mode_state(st, "cmd_type"))
chk("... et pas en perspective", not cl.mode_state(types.SimpleNamespace(area=persp), "cmd_type"))
# Wireframe in 2D views
P["ortho_wire"] = True; cl._WIRE.clear()
a = fake_area(True, 99); a.spaces.active.shading = SH(); a.spaces.active.shading.type = 'MATERIAL'
cl.ortho_wire_apply(a, False)
chk("première fois : l'ombrage n'est pas touché", a.spaces.active.shading.type == 'MATERIAL')
cl.ortho_wire_apply(a, True)
chk("passage en vue 2D : Wireframe", a.spaces.active.shading.type == 'WIREFRAME')
cl.ortho_wire_apply(a, True)
chk("on reste en 2D : rien ne change", a.spaces.active.shading.type == 'WIREFRAME')
cl.ortho_wire_apply(a, False)
chk("retour en perspective : l'ombrage d'avant (Material)", a.spaces.active.shading.type == 'MATERIAL')
cl.ortho_wire_apply(a, True); a.spaces.active.shading.type = 'SOLID'; cl.ortho_wire_apply(a, False)
chk("ombrage changé à la main en 2D : il est gardé au retour", a.spaces.active.shading.type == 'SOLID')
P["ortho_wire"] = True; P["cmd_type_ortho"] = False
_d = m.DESSIN_AP_prefs.__annotations__["ortho_wire"].keywords.get("default")
chk("Wireframe in 2D views by default : coché par défaut", _d is True and m.PREF_DEFAULTS["ortho_wire"] is True, (_d, m.PREF_DEFAULTS["ortho_wire"]))
print("RESULTAT", sum(res), "/", len(res))