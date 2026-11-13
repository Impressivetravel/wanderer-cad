# Préférence « Mode bar: icons only » dans un add-on RÉELLEMENT activé (addon_utils.enable), sans le banc d'essai :
# le réglage existe dans les préférences de Blender, il est lu par la barre de modes, il est affiché dans le panneau
# des préférences et « Reset to defaults » le remet à zéro. (Le dessin des barres lui-même est mesuré par t_compactbar.)
import os as _os, sys as _sys
import bpy, addon_utils
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
_PKG_DIR = _os.path.dirname(_os.path.abspath(_SRC)); _PKG = _os.path.basename(_PKG_DIR)
_sys.path.insert(0, _os.path.dirname(_PKG_DIR))
RES = []
def chk(name, ok, meas=""):
    RES.append((name, bool(ok), meas)); print(("OK  " if ok else "BAD ") + f"[préférence] {name}  {meas}")

mod = addon_utils.enable(_PKG, default_set=True)
addons = bpy.context.preferences.addons
chk("l'add-on s'active pour de bon et ses préférences sont là", mod is not None and _PKG in addons and addons[_PKG].preferences is not None, _PKG)
prefs = addons[_PKG].preferences
core = _sys.modules[_PKG + ".core"]; CL = _sys.modules[_PKG + ".command_line"]
rna = prefs.bl_rna.properties.get("mode_icons")
chk("réglage « Mode bar: icons only » : une case à cocher, décochée par défaut", rna is not None and rna.type == 'BOOLEAN' and rna.name == "Mode bar: icons only" and rna.default is False
    and prefs.mode_icons is False, (rna.name if rna else None, rna.default if rna else None))
chk("... son info-bulle dit ce qu'il fait (icônes même en vue large ; sinon seulement en vue étroite)", rna is not None and "icons" in rna.description and "wide" in rna.description and "narrow" in rna.description,
    rna.description[:70] if rna else "")
sc = 0.9
n_btn, n_arr = len(CL.MODE_BUTTONS), len(CL.MODE_ARROWS)
icon_w = (n_btn * 26 + n_arr * 14 + (n_btn + 1) * 4) * sc
w_off = CL.modes_layout(None, 0, sc, compact=0, fixed=True)[2]
chk("décoché : la barre lit le réglage -> libellés en vue large, icônes en vue réduite", core.pref("mode_icons") is False and CL.modes_icons(0) is False and CL.modes_icons(1) is True
    and w_off > icon_w * 2 and abs(CL.modes_layout(None, 0, sc, compact=1, fixed=True)[2] - icon_w) < 1e-6, (round(w_off), round(icon_w)))
err = None
try:
    prefs.mode_icons = True                 # (lance aussi la mise à jour : redessin des vues)
except Exception as e:                      # noqa
    err = repr(e)
w_on = CL.modes_layout(None, 0, sc, compact=0, fixed=True)[2]
chk("coché : pas d'erreur, la barre lit le réglage -> icônes même en vue large", err is None and prefs.mode_icons is True and core.pref("mode_icons") is True and CL.modes_icons(0) is True
    and abs(w_on - icon_w) < 1e-6, (err, round(w_on, 1)))
w_two = CL.modes_layout(None, 0, sc, compact=2, fixed=True)[2]
chk("... la largeur sur deux rangées (vue très étroite) ne change pas : 4 boutons, 3 flèches", abs(w_two - (4 * 26 + 3 * 14 + 5 * 4) * sc) < 1e-6, round(w_two, 1))

# ----- le panneau des préférences, dessiné avec une mise en page factice qui note ce qu'on lui demande -----
calls = []
class Lay:
    def __init__(self): self.__dict__["enabled"] = True
    def __setattr__(self, k, v): self.__dict__[k] = v
    def box(self, *a, **k): return Lay()
    def row(self, *a, **k): return Lay()
    def column(self, *a, **k): return Lay()
    def split(self, *a, **k): return Lay()
    def grid_flow(self, *a, **k): return Lay()
    def column_flow(self, *a, **k): return Lay()
    def panel(self, *a, **k): return Lay(), None            # (rubrique repliée)
    def prop(self, data, name, *a, **k): calls.append(("prop", name, self.enabled))
    def label(self, *a, **k): calls.append(("label", k.get("text", "")))
    def operator(self, idname, *a, **k): calls.append(("op", idname)); return Lay()
    def menu(self, idname, *a, **k): calls.append(("menu", idname))
    def __getattr__(self, k): return lambda *a, **kw: None  # separator, template_*, ...
class Self:
    layout = Lay()
    def __getattr__(self, k): return getattr(prefs, k)
def panel():
    del calls[:]
    try:
        type(prefs).draw(Self(), bpy.context)
        return None
    except Exception as e:                  # noqa
        import traceback; traceback.print_exc()
        return repr(e)
err = panel()
props = [c[1] for c in calls if c[0] == "prop"]
i_cmd = calls.index(("label", "Command line")) if ("label", "Command line") in calls else -1
i_view = calls.index(("label", "View")) if ("label", "View") in calls else -1
i_me = next((i for i, c in enumerate(calls) if c[:2] == ("prop", "mode_icons")), -1)
chk("le panneau des préférences se dessine sans erreur et montre le réglage une seule fois", err is None and props.count("mode_icons") == 1, (err, props.count("mode_icons")))
chk("... dans la rubrique « Command line », juste après « Command bar size »", 0 <= i_cmd < i_me < i_view and props[props.index("mode_icons") - 1] == "cmd_size", props[max(0, props.index("mode_icons") - 2): props.index("mode_icons") + 2] if "mode_icons" in props else props[:6])
prefs.cmd_line = False
err = panel()
row = {c[1]: c[2] for c in calls if c[0] == "prop"}
chk("... ligne de commande coupée : le réglage reste actif (la barre de modes est toujours affichée), « Command bar size » est grisé", err is None and row.get("mode_icons") is True and row.get("cmd_size") is False,
    (row.get("mode_icons"), row.get("cmd_size")))
# ----- fenêtres et DXF / DWG, dans l'add-on réellement activé -----
LAY = _sys.modules[_PKG + ".layout"]
def registered(cls):
    """Blender refuse d'enregistrer deux fois une classe : c'est la preuve qu'elle l'est déjà."""
    try:
        bpy.utils.register_class(cls)
    except (ValueError, RuntimeError) as ex:
        return "already registered" in str(ex)
    bpy.utils.unregister_class(cls)
    return False
giz = [c.__name__ for c in (LAY.DESSIN_GGT_viewport_grips, LAY.DESSIN_GT_vp_grip, LAY.DESSIN_GT_vp_scale) if not registered(c)]
ops_ = [n for n in ("DESSIN_MT_viewport_scale", "DESSIN_OT_viewport_grip", "DESSIN_OT_viewport_paper", "DESSIN_OT_export_cad", "DESSIN_OT_layout_export_dwg") if not hasattr(bpy.types, n)]
chk("poignées des fenêtres : le groupe de poignées, ses deux formes, la commande et le menu d'échelle sont enregistrés dans Blender", not giz and not ops_, (giz, ops_))
G = LAY.DESSIN_GGT_viewport_grips
chk("... le groupe est attaché à la vue 3D et s'efface hors d'une mise en page", G.bl_space_type == 'VIEW_3D' and G.bl_region_type == 'WINDOW' and G.poll(bpy.context) is False, (G.bl_space_type, G.poll(bpy.context)))
exp = getattr(bpy.types.TOPBAR_MT_file_export.draw, "_draw_funcs", [])
imp = getattr(bpy.types.TOPBAR_MT_file_import.draw, "_draw_funcs", [])
chk("menus File > Import et File > Export : l'entrée « DXF / DWG drawing (Wanderer) » y est", any(f.__name__ == "menu_export_cad" for f in exp) and any(f.__name__ == "menu_import_cad" for f in imp),
    ([f.__name__ for f in exp][-2:], [f.__name__ for f in imp][-2:]))
oda = prefs.bl_rna.properties.get("oda_path")
chk("préférences : le réglage « ODA File Converter » existe (un chemin de fichier, vide par défaut) et il est dans le panneau", oda is not None and oda.subtype == 'FILE_PATH' and prefs.oda_path == ""
    and props.count("oda_path") == 1 and ("label", "DXF / DWG") in calls, (oda and oda.subtype, props.count("oda_path")))
prefs.cmd_line = True
r = bpy.ops.dessin.prefs_reset('EXEC_DEFAULT')
chk("« Reset to defaults » décoche le réglage ; la barre repasse en libellés", r == {'FINISHED'} and prefs.mode_icons is False and core.pref("mode_icons") is False and CL.modes_icons(0) is False
    and abs(CL.modes_layout(None, 0, sc, compact=0, fixed=True)[2] - w_off) < 1e-6, r)
err = None
try:
    addon_utils.disable(_PKG, default_set=True)
except Exception as e:                      # noqa
    err = repr(e)
chk("l'add-on se désactive sans erreur ; sans préférences, la valeur par défaut (décoché) est rendue", err is None and core.pref("mode_icons") is False, err)

bad = [r_ for r_ in RES if not r_[1]]
print(f"RESULTAT précision : {len(RES) - len(bad)} / {len(RES)}")
for r_ in bad: print("   ECHEC", r_[0], r_[2])
