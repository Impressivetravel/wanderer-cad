# Infobulle des poignées du Gizmo (ce qu'on y a ajouté : Ctrl, B, Snap from) et résultat des mesures (Distance, ID)
# écrit dans la barre de commande, pas seulement dans la barre d'infos de Blender, tout en bas.
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE, 'harness.py')).read())
exec(open(_os.path.join(_HERE, 'prec_lib.py')).read())
import sys, types
from mathutils import Vector
SEC = "?"
def chk(name, ok, meas=""): rec(SEC, name, ok, meas)
CP = [v for k, v in sys.modules.items() if k.endswith(".cplane") and hasattr(v, "cmd_notice")][0]

SEC = "Infobulle des poignées du Gizmo"
G = m.DESSIN_OT_gumball
tips = {k: G.description(bpy.context, types.SimpleNamespace(kind=k)) for k in ('MOVE', 'PLANE', 'ROTATE', 'SCALE')}
chk("flèche : Ctrl (accrochage), B (point de base), copie, Snap from", all(w in tips['MOVE'] for w in ("Ctrl", "B picks the base point", "copy", "Snap from", "type the distance")), tips['MOVE'])
chk("carré : Ctrl, B, Snap from", all(w in tips['PLANE'] for w in ("Ctrl", "B picks", "Snap from")), tips['PLANE'])
chk("rotation : angle affiché, rotation libre, copie", all(w in tips['ROTATE'] for w in ("angle", "free rotation", "copy")), tips['ROTATE'])
chk("échelle : échelle uniforme, copie", all(w in tips['SCALE'] for w in ("uniform scale", "copy")), tips['SCALE'])
chk("plus de l'ancienne phrase unique", "from its center" not in tips['MOVE'])

SEC = "Résultat de Distance dans la barre de commande"
CP.cmd_notice_clear()
o = make(m.DESSIN_OT_dist)
o.unit_f, o.unit_label = m.unit_info(bpy.context.scene)
o.points = [Vector((0, 0, 0))]; o.cur = Vector((2, 0, 0)); o.finished = False; o.axis = 2
o.refresh = lambda c: None
fake = types.SimpleNamespace(window_manager=types.SimpleNamespace(clipboard=""), scene=bpy.context.scene, area=None)
type(o).click(o, fake)
chk("le résultat est écrit dans la barre de commande", (CP.cmd_notice_text() or "").startswith("Distance = 2"), CP.cmd_notice_text())
chk("... en clair (résultat, pas un avertissement orangé)", CP.cmd_notice_style() == "fg", CP.cmd_notice_style())
chk("... et il reste un moment (20 s)", CP.RESULT_SECONDS >= 15)
chk("... toujours copié dans le presse-papiers et dans la barre d'infos", fake.window_manager.clipboard == "2" and any("Distance" in r[1] for r in o._reports), (fake.window_manager.clipboard, o._reports))
CP.cmd_notice("Fillet: nothing to do")
chk("un avertissement reste orangé", CP.cmd_notice_style() == "warn")
CP.cmd_notice_clear()

summary()
