# Barre de modes : menu OSnap (flèche), accrochage ponctuel (Maj + clic, comme Rhino), Grid Snap (F9) à côté d'Ortho
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE, 'harness.py')).read())
exec(open(_os.path.join(_HERE, 'prec_lib.py')).read())
from mathutils import Vector, Matrix
BC = bpy.context
st = BC.scene.dessin
SEC = "?"
def chk(name, ok, meas=""): rec(SEC, name, ok, meas)
r4 = lambda v: tuple(round(x, 4) for x in v)
def same(a, b, tol=1e-6): return all(abs(x - y) <= tol for x, y in zip(a, b))
def defaults():
    for k, v in m.OSNAP_DEFAULTS.items(): setattr(st, "osnap_" + k, v)
    st.grid_snap = False; st.grid_snap_step = 1.0; st.ortho = False; st.polar = False
    m.oneshot_reset()
    us = BC.scene.unit_settings; us.system = 'NONE'; us.scale_length = 1.0
TOP = (rv3d.view_matrix.copy(), rv3d.perspective_matrix.copy(), rv3d.view_rotation.copy())
def oblique():
    """Vue orthogonale inclinée de 45° : le rayon de la souris n'est plus parallèle à Z (hauteurs désignables)."""
    c = math.sqrt(0.5)
    R = Matrix(((1, 0, 0, 0), (0, c, c, 0), (0, -c, c, 0), (0, 0, 0, 1)))
    VM2 = Matrix.Translation((0, 0, -50)) @ R
    rv3d.view_matrix = VM2; rv3d.perspective_matrix = WM @ VM2; rv3d.view_rotation = R.to_3x3().transposed().to_quaternion()
def top():
    rv3d.view_matrix, rv3d.perspective_matrix, rv3d.view_rotation = TOP[0].copy(), TOP[1].copy(), TOP[2].copy()
def px(P):
    q = m.project_px(rv3d, region, Vector(P)); return (q.x, q.y)
KEY = {'0': 'ZERO', '1': 'ONE', '2': 'TWO', '3': 'THREE', '4': 'FOUR', '5': 'FIVE', '6': 'SIX', '7': 'SEVEN', '8': 'EIGHT', '9': 'NINE', '.': 'PERIOD', '-': 'MINUS'}
class Tool:
    """Une commande de dessin lancée dans la vue factice, pilotée évènement par évènement."""
    def __init__(self, cls, P0=(0, 0, 0)):
        if isinstance(cls, str): cls = getattr(m, "DESSIN_OT_" + cls)
        self.o = make(cls); self.r = type(self.o).invoke(self.o, ctx, ev('NONE', 'NOTHING', *px(P0))); self.last = None
    def send(self, *evs):
        for e in evs: self.last = type(self.o).modal(self.o, ctx, e)
        return self.last
    def move(self, P): return self.send(ev('MOUSEMOVE', 'NOTHING', *px(P)))
    def click(self, P):
        sx, sy = px(P); return self.send(ev('MOUSEMOVE', 'NOTHING', sx, sy), ev('LEFTMOUSE', 'PRESS', sx, sy), ev('LEFTMOUSE', 'RELEASE', sx, sy))
    def key(self, k, P=(0, 0, 0), **kw): return self.send(ev(k, 'PRESS', *px(P), **kw))
    def typ(self, txt, P=(0, 0, 0)):
        for ch in txt: self.send(ev(KEY[ch], 'PRESS', *px(P), unicode=ch, ascii=ch))
    def end(self):
        try: self.key('ESC')
        except Exception: pass
        try: type(self.o).cleanup(self.o, ctx)
        except Exception: pass
BAR_Y, VIEW_Y = 10, 400          # hauteur de souris : sur la barre d'état (sous les zones de la fenêtre) / dans la vue
def osnap_click(key, shift=False, y=BAR_Y):
    """Clic sur la case d'un accrochage (barre d'état ou menu) : même chemin que le bouton (invoke lit la touche Maj)."""
    o = make(m.DESSIN_OT_osnap_set); o.key = key
    return type(o).invoke(o, ctx, ev('LEFTMOUSE', 'PRESS', 300, y, shift=shift)), o
def bar_boxes():
    """Cases cochées de la barre d'état (clés), et son étiquette."""
    lay = FakeLayout(); m.statusbar_osnap(NS(layout=lay), ctx)
    return [it.key for it in lay.log if it.kind == "op" and it.icon == 'CHECKBOX_HLT'], [it.text for it in lay.log if it.kind == "label"]
class FakeLayout:
    """Mise en page factice : note ce que le menu / la barre y pose (boutons, étiquettes, séparateurs)."""
    def __init__(self, log=None):
        self.log = [] if log is None else log; self.operator_context = None; self.active = True; self.enabled = True
    def operator(self, idname, text="", icon='NONE', emboss=True, **kw):
        it = NS(kind="op", idname=idname, text=text, icon=icon, emboss=emboss, layout=self); self.log.append(it); return it
    def label(self, text="", **kw): self.log.append(NS(kind="label", text=text))
    def separator(self, **kw): self.log.append(NS(kind="sep"))
    def prop(self, data, name, **kw): self.log.append(NS(kind="prop", name=name, text=kw.get("text", "")))
    def row(self, **kw):
        sub = FakeLayout(self.log); return sub
defaults()
ptr = area.as_pointer()

# ================= 1. Barre de modes =================
SEC = "barre"
keys = [k for k, _l, _t in m.MODE_BUTTONS]
chk("Grid Snap est juste avant Ortho dans la barre de modes", keys.index("grid_snap") + 1 == keys.index("ortho"), keys)
chk("OSnap et Grid Snap ont une flèche (menu déroulant), comme Polar et Gumball",
    m.MODE_ARROWS.get("osnap_enable") == "osnapmenu" and m.MODE_ARROWS.get("grid_snap") == "gridsnapmenu"
    and m.MODE_ARROWS.get("polar") == "polarmenu" and m.MODE_ARROWS.get("gumball") == "gumballmenu", m.MODE_ARROWS)
try:
    items, arrow, total = m.modes_layout(ctx, ptr, 1.0)
    import blf
    w = {k: wd for k, _l, wd in items}
    tw = lambda t: blf.dimensions(0, t)[0]
    chk("largeur du bouton OSnap = texte + marges + flèche", abs(w["osnap_enable"] - (tw("OSnap") + 18 + arrow)) < 1e-6 and arrow > 0, (w["osnap_enable"], arrow))
    chk("largeur du bouton Grid Snap = texte + marges + flèche", abs(w["grid_snap"] - (tw("Grid Snap") + 18 + arrow)) < 1e-6, w["grid_snap"])
    chk("Ortho n'a pas de flèche", abs(w["ortho"] - (tw("Ortho") + 18)) < 1e-6, w["ortho"])
    chk("largeur totale = somme des boutons + écarts", abs(total - (sum(w.values()) + 4 * (len(items) + 1))) < 1e-6, total)
except Exception as e:
    chk("modes_layout", False, repr(e))
menus = []
m.call_menu_later = lambda c, name: menus.append(name)
m.mode_click(ctx, 'osnapmenu'); m.mode_click(ctx, 'gridsnapmenu'); m.mode_click(ctx, 'polarmenu')
chk("flèche OSnap : ouvre le menu des accrochages", menus[:1] == ["DESSIN_MT_osnap"], menus)
chk("flèche Grid Snap : ouvre le menu du pas", menus[1:2] == ["DESSIN_MT_grid_snap"], menus)
chk("flèche Polar : toujours le menu Polar", menus[2:3] == ["DESSIN_MT_polar_angle"], menus)
chk("menus et opérateurs enregistrés dans Blender",
    all(hasattr(bpy.types, n) for n in ("DESSIN_MT_osnap", "DESSIN_MT_grid_snap", "DESSIN_OT_osnap_set", "DESSIN_OT_grid_snap_set", "DESSIN_OT_grid_snap_step")))
m.mode_click(ctx, 'grid_snap')
chk("clic sur Grid Snap : activé", st.grid_snap is True and m.mode_state(ctx, "grid_snap") is True)
m.mode_click(ctx, 'grid_snap')
chk("second clic : désactivé", st.grid_snap is False and m.mode_state(ctx, "grid_snap") is False)
m.mode_click(ctx, 'osnap_enable')
chk("clic sur OSnap : accrochages coupés (comme F3)", st.osnap_disable is True and m.mode_state(ctx, "osnap_enable") is False)
m.mode_click(ctx, 'osnap_enable')
chk("second clic : accrochages rétablis", st.osnap_disable is False and m.mode_state(ctx, "osnap_enable") is True)
tips = [m.mode_arrow_tip(ctx, k) for k in m.MODE_ARROWS]
chk("chaque flèche a sa propre info-bulle", all(tips) and len(set(tips)) == len(tips), tips)
chk("info-bulle de la flèche Grid Snap : le pas courant", "1" in m.mode_arrow_tip(ctx, "grid_snap") and "spacing" in m.mode_arrow_tip(ctx, "grid_snap").lower(), m.mode_arrow_tip(ctx, "grid_snap"))

# ---- menu OSnap ----
def draw_menu(cls):
    lay = FakeLayout(); cls.draw(NS(layout=lay), ctx); return lay
defaults(); st.osnap_perp = False; st.osnap_mid = True
lay = draw_menu(m.DESSIN_MT_osnap)
ops = [it for it in lay.log if it.kind == "op"]
bykey = {getattr(it, "key", None): it for it in ops}
chk("menu OSnap : une ligne par accrochage de la barre d'état", [getattr(it, "key", None) for it in ops][:12] == [k for k, _l in m.OSNAP_BAR], [getattr(it, "key", None) for it in ops])
chk("... plus Disable, All On, All Off", [getattr(it, "key", None) for it in ops][12:] == ["disable", "all", "none"])
chk("... les cases reflètent les réglages (Mid coché, Perp décoché)", bykey["mid"].icon == 'CHECKBOX_HLT' and bykey["perp"].icon == 'CHECKBOX_DEHLT' and bykey["disable"].icon == 'CHECKBOX_DEHLT')
chk("... les boutons sont lancés par invoke (pour lire la touche Maj)", lay.operator_context == 'INVOKE_DEFAULT', lay.operator_context)
chk("... tous appellent dessin.osnap_set", all(it.idname == "dessin.osnap_set" for it in ops))
chk("... et le menu rappelle Maj + clic", any(it.kind == "label" and "Shift + click" in it.text for it in lay.log))

# ---- barre d'état ----
lay = FakeLayout(); m.statusbar_osnap(NS(layout=lay), ctx)
ops = [it for it in lay.log if it.kind == "op"]
chk("barre d'état : les 12 cases sont des boutons dessin.osnap_set, dans l'ordre", [getattr(it, "key", None) for it in ops] == [k for k, _l in m.OSNAP_BAR] and all(it.idname == "dessin.osnap_set" for it in ops))
chk("... dessinées comme des cases (icône de case, sans relief)", all(it.icon in ('CHECKBOX_HLT', 'CHECKBOX_DEHLT') and it.emboss is False for it in ops))
chk("... cochées selon les réglages", all((it.icon == 'CHECKBOX_HLT') == bool(getattr(st, "osnap_" + it.key)) for it in ops))
chk("... étiquette « OSnap »", [it.text for it in lay.log if it.kind == "label"] == ["OSnap"])

# ================= 2. Cases : clic simple =================
SEC = "cases"
defaults()
r, o = osnap_click("mid")
chk("clic sur Mid : décoché (et c'est un pas d'annulation, comme la case d'origine)", 'FINISHED' in r and st.osnap_mid is False and 'UNDO' in m.DESSIN_OT_osnap_set.bl_options)
r, o = osnap_click("mid")
chk("second clic : recoché", st.osnap_mid is True)
r, o = osnap_click("disable")
chk("clic sur Disable : accrochages coupés", st.osnap_disable is True)
osnap_click("disable")
osnap_click("none")
chk("All Off : les onze accrochages décochés", not any(getattr(st, "osnap_" + k) for k in m.ONESHOT_KEYS))
chk("... Project et Disable inchangés", st.osnap_project is False and st.osnap_disable is False)
osnap_click("all")
chk("All On : les onze accrochages cochés", all(getattr(st, "osnap_" + k) for k in m.ONESHOT_KEYS))
r, o = osnap_click("zzz")
chk("clé inconnue : refusée sans erreur", 'CANCELLED' in r)
chk("la commande Blender répond aussi (exécution directe)", 'FINISHED' in bpy.ops.dessin.osnap_set(key="knot") and st.osnap_knot is False)
defaults()

# ================= 3. Accrochage ponctuel (Maj + clic) =================
SEC = "ponctuel"
clear(); defaults()
seg = m.build_polyline(BC, "Seg", [Vector((2, 2, 0)), Vector((8, 2, 0))], False)       # extrémités (2,2) et (8,2), milieu (5,2)
seg2 = m.build_polyline(BC, "Seg2", [Vector((2, 6, 0)), Vector((8, 6, 0))], False)     # extrémités (2,6) et (8,6), milieu (5,6)
BC.view_layer.update()
chk("hors commande : rien n'attend de point", m.point_requested(ctx) is False)
r, o = osnap_click("mid", shift=True)
chk("Maj + clic hors commande : refusé, rien n'est armé", 'CANCELLED' in r and m.oneshot_keys() == () and st.osnap_mid is True, o._reports)
chk("... avec un message qui dit pourquoi", any("command" in msg for _lv, msg in o._reports), o._reports)

t = Tool("polyligne", (12, 9, 0))
chk("commande Polyline lancée : un point est attendu", m.point_requested(ctx) is True)
t.move((2.4, 2.3, 0))
chk("réglages normaux : le curseur s'accroche à l'extrémité (End)", same(t.o.cur, (2, 2, 0)) and m.SNAP_NAMES.get(t.o.snap_kind) == "End", (r4(t.o.cur), t.o.snap_kind))
r, o = osnap_click("mid", shift=True)
chk("Maj + clic sur Mid pendant la commande : accrochage ponctuel armé", m.oneshot_keys() == ("mid",) and any("Mid" in msg for _lv, msg in o._reports), (m.oneshot_keys(), o._reports))
chk("... sans pas d'annulation (aucun réglage de la scène ne change)", 'CANCELLED' in r and 'UNDO' in m.DESSIN_OT_osnap_set.bl_options, r)
chk("... les cases cochées ne changent pas", st.osnap_mid is True and st.osnap_end is True and st.osnap_near is True)
chk("... seul Mid répond", m.osnap("mid") and not any(m.osnap(k) for k in m.ONESHOT_KEYS if k != "mid") and m.osnap("disable") is False)
chk("... le bouton OSnap de la barre l'annonce", m.mode_label(ctx, "osnap_enable", "OSnap") == "OSnap: Mid" and m.mode_state(ctx, "osnap_enable") is True)
lay = FakeLayout(); m.statusbar_osnap(NS(layout=lay), ctx)
ops = [it for it in lay.log if it.kind == "op"]
chk("... barre d'état : seule la case Mid paraît cochée, « one shot » écrit après les cases (elles ne bougent pas sous la souris)",
    [it.key for it in ops if it.icon == 'CHECKBOX_HLT'] == ["mid"] and [it.text for it in lay.log if it.kind == "label"] == ["OSnap", "one shot"]
    and [it.kind for it in lay.log][:14] == ["label"] + ["op"] * 12 + ["label"], [it.kind for it in lay.log])
lay = draw_menu(m.DESSIN_MT_osnap)
chk("... menu OSnap : seule la case Mid paraît cochée", [it.key for it in lay.log if it.kind == "op" and it.icon == 'CHECKBOX_HLT'] == ["mid"])
t.move((2.4, 2.3, 0))
chk("près de l'extrémité : plus d'accrochage End (point libre sous la souris)", t.o.snap_kind is None and same(t.o.cur, (2.4, 2.3, 0)), (r4(t.o.cur), t.o.snap_kind))
t.move((3.5, 2.3, 0))
chk("le long du segment : pas d'accrochage Near non plus", t.o.snap_kind is None and same(t.o.cur, (3.5, 2.3, 0)), (r4(t.o.cur), t.o.snap_kind))
t.move((5.4, 2.3, 0))
chk("près du milieu : accroché au milieu exact (5, 2, 0)", same(t.o.cur, (5, 2, 0)) and m.SNAP_NAMES.get(t.o.snap_kind) == "Midpoint", (r4(t.o.cur), t.o.snap_kind))
t.click((5.4, 2.3, 0))
chk("clic : le point est posé au milieu", len(t.o.points) == 1 and same(t.o.points[0], (5, 2, 0)), [r4(p) for p in t.o.points])
chk("... et l'accrochage ponctuel s'éteint (un seul point)", m.oneshot_keys() == ())
t.move((2.4, 2.3, 0))
chk("point suivant : les accrochages cochés reviennent (End)", same(t.o.cur, (2, 2, 0)) and m.SNAP_NAMES.get(t.o.snap_kind) == "End", (r4(t.o.cur), t.o.snap_kind))
chk("le bouton OSnap retrouve son nom", m.mode_label(ctx, "osnap_enable", "OSnap") == "OSnap")

# la case de l'accrochage ponctuel peut être décochée, ou tout coupé par F3 : il agit quand même
st.osnap_mid = False; st.osnap_disable = True
t.move((5.4, 6.3, 0))
chk("F3 actif, Mid décoché : aucun accrochage sur le second segment", t.o.snap_kind is None, t.o.snap_kind)
osnap_click("mid", shift=True)
t.move((5.4, 6.3, 0))
chk("accrochage ponctuel Mid : il passe outre (milieu exact (5, 6, 0))", same(t.o.cur, (5, 6, 0)) and m.SNAP_NAMES.get(t.o.snap_kind) == "Midpoint", (r4(t.o.cur), t.o.snap_kind))
t.click((5.4, 6.3, 0))
chk("... point posé au milieu du second segment", len(t.o.points) == 2 and same(t.o.points[1], (5, 6, 0)), [r4(p) for p in t.o.points])
t.move((8.3, 2.3, 0))
chk("après le point : F3 est toujours actif, Mid toujours décoché", m.oneshot_keys() == () and st.osnap_disable is True and st.osnap_mid is False and t.o.snap_kind is None)
st.osnap_mid = True; st.osnap_disable = False

# touche S (accrochages coupés pour la commande) : l'accrochage ponctuel passe aussi
t.key('S', (8.3, 2.3, 0))
t.move((8.3, 2.3, 0))
chk("touche S : plus d'accrochage dans cette commande", t.o.snap_on is False and t.o.snap_kind is None)
osnap_click("end", shift=True)
t.move((8.3, 2.3, 0))
chk("accrochage ponctuel End malgré S : extrémité exacte (8, 2, 0)", same(t.o.cur, (8, 2, 0)) and m.SNAP_NAMES.get(t.o.snap_kind) == "End", (r4(t.o.cur), t.o.snap_kind))
t.key('S', (8.3, 2.3, 0))

# renoncer : Maj + clic sur le même, clic simple, clic sur le bouton OSnap
r, o = osnap_click("end", shift=True)
chk("Maj + clic sur l'accrochage armé : on y renonce", m.oneshot_keys() == ())
osnap_click("quad", shift=True); r, o = osnap_click("cen", shift=True)
chk("Maj + clic sur un autre : il s'ajoute (plusieurs accrochages ponctuels, dans l'ordre de la barre)", m.oneshot_keys() == ("cen", "quad") and any("Cen + Quad" in msg for _lv, msg in o._reports), (m.oneshot_keys(), o._reports))
chk("... le bouton OSnap les annonce tous les deux", m.mode_label(ctx, "osnap_enable", "OSnap") == "OSnap: Cen+Quad", m.mode_label(ctx, "osnap_enable", "OSnap"))
chk("... eux seuls répondent", m.osnap("cen") and m.osnap("quad") and not any(m.osnap(k) for k in m.ONESHOT_KEYS if k not in ("cen", "quad")))
r, o = osnap_click("perp")
chk("clic simple pendant un accrochage ponctuel : on y renonce, et la case cliquée ne bascule pas (on ne voyait pas son état)",
    m.oneshot_keys() == () and st.osnap_perp is False and 'CANCELLED' in r, (m.oneshot_keys(), st.osnap_perp, r))
r, o = osnap_click("perp")
chk("... un second clic simple la bascule normalement", st.osnap_perp is True and 'FINISHED' in r)
st.osnap_perp = False
osnap_click("mid", shift=True); r, o = osnap_click("disable")
chk("Disable (F3) reste une case normale pendant un accrochage ponctuel", st.osnap_disable is True and m.oneshot_keys() == ("mid",) and m.osnap("mid") is True)
osnap_click("disable"); m.oneshot_clear()
osnap_click("int", shift=True)
m.mode_click(ctx, 'osnap_enable')
chk("clic sur le bouton OSnap : renonce à l'accrochage ponctuel sans couper les accrochages", m.oneshot_keys() == () and st.osnap_disable is False)
r, o = osnap_click("project", shift=True)
chk("Project n'est pas un accrochage ponctuel : Maj + clic le bascule simplement", m.oneshot_keys() == () and st.osnap_project is True)
st.osnap_project = False

# fin de commande : l'accrochage ponctuel ne survit pas
osnap_click("quad", shift=True)
n_before = len(t.o.points)
t.typ("3", (9.5, 8.5, 0)); t.move((9.5, 8.5, 0)); t.key('RET', (9.5, 8.5, 0))
chk("point donné au clavier (longueur + Entrée) : l'accrochage ponctuel est consommé aussi", len(t.o.points) == n_before + 1 and m.oneshot_keys() == (), (len(t.o.points), m.oneshot_keys()))
osnap_click("quad", shift=True)
t.key('ESC')
chk("Échap : la commande s'arrête et l'accrochage ponctuel avec elle", m.oneshot_keys() == () and m.point_requested(ctx) is False)
t.end()
m.oneshot_set("mid")
m.oneshot_validate(ctx)
chk("garde-fou : un accrochage ponctuel resté armé sans commande s'éteint au dessin de la barre", m.oneshot_keys() == ())
m.oneshot_set(("project", "zzz"))
chk("oneshot_set refuse une clé qui n'est pas un accrochage", m.oneshot_keys() == ())
m.oneshot_set(("vertex", "end", "mid"))
chk("oneshot_set range les clés dans l'ordre de la barre", m.oneshot_keys() == ("end", "mid", "vertex"), m.oneshot_keys())
m.oneshot_reset()

# ================= 3 bis. Maj tenu au-dessus des cases (comme la barre Osnap de Rhino) =================
SEC = "Maj tenu"
clear(); defaults()
st.osnap_perp = False; st.osnap_tan = False; st.osnap_knot = False
seg = m.build_polyline(BC, "Seg", [Vector((2, 2, 0)), Vector((8, 2, 0))], False)
BC.view_layer.update()
ctx._o['window'] = NS(screen=NS(areas=[NS(y=26), NS(y=26), NS(y=540)]), width=1000)        # barre d'état : 26 px en bas de la fenêtre
checked0 = [k for k, _l in m.OSNAP_BAR if getattr(st, "osnap_" + k)]
def shift_ev(value, y=BAR_Y): return ev('LEFT_SHIFT', value, 300, y, shift=(value == 'PRESS'))
chk("la souris à 10 px du bas est sur la barre d'état, à 400 px elle n'y est pas",
    m.mouse_over_statusbar(ctx, ev('MOUSEMOVE', 'NOTHING', 300, BAR_Y)) and not m.mouse_over_statusbar(ctx, ev('MOUSEMOVE', 'NOTHING', 300, VIEW_Y)))
r = m.osnap_hold_event(ctx, shift_ev('PRESS'))
chk("hors commande, Maj au-dessus des cases : rien ne change (aucun point n'est attendu)", r is False and not m.oneshot_hold() and bar_boxes() == (checked0, ["OSnap"]), bar_boxes())
t = Tool("polyligne", (12, 9, 0))
t.send(ev('MOUSEMOVE', 'NOTHING', 300, BAR_Y))
chk("commande en cours, souris sur les cases sans Maj : cases inchangées", not m.oneshot_hold() and bar_boxes() == (checked0, ["OSnap"]))
t.send(shift_ev('PRESS'))
chk("Maj enfoncé au-dessus des cases : elles paraissent toutes décochées", m.oneshot_hold() and bar_boxes() == ([], ["OSnap", "one shot"]), bar_boxes())
lay = draw_menu(m.DESSIN_MT_osnap)
chk("... dans le menu OSnap aussi", [it.key for it in lay.log if it.kind == "op" and it.icon == 'CHECKBOX_HLT' and it.key in m.ONESHOT_KEYS] == [])
chk("... les réglages eux-mêmes ne sont pas touchés", [k for k, _l in m.OSNAP_BAR if getattr(st, "osnap_" + k)] == checked0 and m.osnap("end") is True and m.oneshot_keys() == ())
t.send(shift_ev('RELEASE'))
chk("Maj relâché sans avoir rien cliqué : les cases reviennent comme avant", not m.oneshot_hold() and bar_boxes() == (checked0, ["OSnap"]), bar_boxes())
# Maj tenu, puis clic sur les cases voulues
t.send(shift_ev('PRESS'))
r, o = osnap_click("mid", shift=True)
chk("Maj tenu + clic sur Mid : seule Mid est cochée", m.oneshot_keys() == ("mid",) and bar_boxes() == (["mid"], ["OSnap", "one shot"]), bar_boxes())
r, o = osnap_click("end", shift=True)
chk("... + clic sur End : End et Mid cochées, les autres non", m.oneshot_keys() == ("end", "mid") and bar_boxes() == (["end", "mid"], ["OSnap", "one shot"]) and any("End + Mid" in msg for _lv, msg in o._reports), (bar_boxes(), o._reports))
t.send(shift_ev('RELEASE'))
chk("Maj relâché après avoir cliqué : End et Mid restent armées pour le prochain point", not m.oneshot_hold() and m.oneshot_keys() == ("end", "mid") and bar_boxes() == (["end", "mid"], ["OSnap", "one shot"]), bar_boxes())
chk("... le bouton OSnap l'annonce", m.mode_label(ctx, "osnap_enable", "OSnap") == "OSnap: End+Mid")
t.move((3.5, 2.3, 0))
chk("dans la vue, le long du segment : pas d'accrochage Near (pourtant coché)", t.o.snap_kind is None and same(t.o.cur, (3.5, 2.3, 0)), (r4(t.o.cur), t.o.snap_kind))
t.move((2.4, 2.3, 0))
chk("près de l'extrémité : End", same(t.o.cur, (2, 2, 0)) and m.SNAP_NAMES.get(t.o.snap_kind) == "End", (r4(t.o.cur), t.o.snap_kind))
t.move((5.4, 2.3, 0))
chk("près du milieu : Mid", same(t.o.cur, (5, 2, 0)) and m.SNAP_NAMES.get(t.o.snap_kind) == "Midpoint", (r4(t.o.cur), t.o.snap_kind))
t.click((5.4, 2.3, 0))
chk("clic : point posé au milieu, puis toutes les cases reviennent", same(t.o.points[0], (5, 2, 0)) and m.oneshot_keys() == () and bar_boxes() == (checked0, ["OSnap"]), bar_boxes())
# cocher puis décocher sous Maj : on revient à zéro, et au relâchement tout est rétabli
t.send(ev('MOUSEMOVE', 'NOTHING', 300, BAR_Y), shift_ev('PRESS'))
osnap_click("quad", shift=True); osnap_click("quad", shift=True)
chk("Maj tenu, Quad cliquée puis recliquée : plus aucune case cochée, Maj toujours tenu", m.oneshot_keys() == () and m.oneshot_hold() and bar_boxes() == ([], ["OSnap", "one shot"]), bar_boxes())
t.send(shift_ev('RELEASE'))
chk("... Maj relâché : les cases reviennent comme avant", bar_boxes() == (checked0, ["OSnap"]) and m.osnap("near") is True)
# la souris entre sur la barre avec Maj déjà tenu, puis en sort
t.send(ev('MOUSEMOVE', 'NOTHING', 300, VIEW_Y, shift=True))
chk("Maj tenu dans la vue (Polyline : orthogonal) : les cases ne bougent pas", not m.oneshot_hold() and bar_boxes() == (checked0, ["OSnap"]))
t.send(ev('MOUSEMOVE', 'NOTHING', 300, BAR_Y, shift=True))
chk("la souris descend sur les cases, Maj toujours tenu : elles se décochent", m.oneshot_hold() and bar_boxes() == ([], ["OSnap", "one shot"]))
t.send(ev('MOUSEMOVE', 'NOTHING', 300, VIEW_Y, shift=True))
chk("la souris remonte dans la vue sans avoir cliqué : elles reviennent", not m.oneshot_hold() and bar_boxes() == (checked0, ["OSnap"]))
# garde-fous
t.send(ev('MOUSEMOVE', 'NOTHING', 300, BAR_Y), shift_ev('PRESS'))
t.send(ev('MOUSEMOVE', 'NOTHING', 300, BAR_Y, shift=False))
chk("relâchement de Maj non vu (fenêtre quittée) : le premier mouvement de souris sans Maj rétablit les cases", not m.oneshot_hold() and bar_boxes() == (checked0, ["OSnap"]))
t.send(shift_ev('PRESS')); m._ONESHOT["hold_t"] -= m.ONESHOT_HOLD_MAX + 1
chk("... ou, sans aucun évènement, le délai de garde", not m.oneshot_hold() and bar_boxes() == (checked0, ["OSnap"]))
t.send(shift_ev('PRESS'))
r, o = osnap_click("mid")
chk("clic simple alors que les cases paraissent décochées : elles reviennent, rien n'est basculé", not m.oneshot_hold() and st.osnap_mid is True and bar_boxes() == (checked0, ["OSnap"]) and 'CANCELLED' in r, (bar_boxes(), r))
t.send(shift_ev('PRESS')); osnap_click("cen", shift=True)
t.key('ESC'); t.end(); m.oneshot_validate(ctx)
chk("Échap pendant que Maj est tenu : tout est rétabli avec la fin de la commande", not m.oneshot_hold() and m.oneshot_keys() == () and bar_boxes() == (checked0, ["OSnap"]), (m.oneshot_hold(), m.oneshot_keys()))
# commande dont Maj a un rôle propre (Rectangle : carré) : l'évènement Maj est consommé par la commande, les cases suivent quand même
t = Tool("rectangle", (12, 9, 0)); t.click((3, 5, 0))
r = t.send(shift_ev('PRESS'))
chk("Rectangle (Maj = carré) : Maj au-dessus des cases les décoche aussi", m.oneshot_hold() and bar_boxes() == ([], ["OSnap", "one shot"]), (r, bar_boxes()))
t.send(shift_ev('RELEASE'))
chk("... et les rétablit au relâchement", not m.oneshot_hold() and bar_boxes() == (checked0, ["OSnap"]))
# Maj + clic sans que l'appui sur Maj ait été vu : le clic suffit à décocher les autres cases
r, o = osnap_click("int", shift=True)
chk("Maj + clic direct sur une case de la barre : elle seule est cochée, les autres décochées tant que Maj est tenu", m.oneshot_keys() == ("int",) and m.oneshot_hold() and bar_boxes() == (["int"], ["OSnap", "one shot"]), bar_boxes())
r, o = osnap_click("int", shift=True, y=VIEW_Y)
t.send(shift_ev('RELEASE', VIEW_Y))
t.end(); m.oneshot_reset()
# le raccourci de la fenêtre (aucune commande en cours, outil de dessin armé) : même fonction
o = make(m.DESSIN_OT_osnap_hold)
r = type(o).invoke(o, ctx, shift_ev('PRESS'))
chk("raccourci Maj de la fenêtre : sans commande il ne fait rien et laisse passer l'évènement tel quel", r == {'PASS_THROUGH'} and not m.oneshot_hold(), r)
real_pr = m.point_requested
m.point_requested = lambda c: True                     # un outil de dessin est armé (sa commande n'a pas encore démarré)
r = type(o).invoke(o, ctx, shift_ev('PRESS'))
chk("... outil armé : Maj au-dessus des cases les décoche", r == {'FINISHED', 'PASS_THROUGH'} and m.oneshot_hold() and bar_boxes() == ([], ["OSnap", "one shot"]), bar_boxes())
r = type(o).invoke(o, ctx, shift_ev('RELEASE'))
chk("... relâché : elles reviennent", not m.oneshot_hold() and bar_boxes() == (checked0, ["OSnap"]))
r = type(o).invoke(o, ctx, shift_ev('PRESS', VIEW_Y))
chk("... Maj enfoncé ailleurs que sur la barre d'état : rien, l'évènement passe tel quel", not m.oneshot_hold() and r == {'PASS_THROUGH'}, r)
m.point_requested = real_pr
kc = bpy.context.window_manager.keyconfigs.addon
items = sorted((k.type, k.value, k.any) for k in kc.keymaps["Window"].keymap_items if k.idname == "dessin.osnap_hold") if kc else None
chk("raccourcis posés dans le keymap « Window » de Blender : Maj gauche et droit, appui et relâchement, avec n'importe quel autre modificateur",
    hasattr(bpy.types, "DESSIN_OT_osnap_hold") and (kc is None or items == sorted((key, val, True) for key in ('LEFT_SHIFT', 'RIGHT_SHIFT') for val in ('PRESS', 'RELEASE'))), items)
ctx._o['window'] = None
defaults()

# ================= 4. Grid Snap =================
SEC = "grille"
clear(); defaults()
chk("coupé : pas = 0", m.grid_snap_step(ctx) == 0.0)
st.grid_snap = True
chk("activé, pas 1 : 1 unité Blender", m.grid_snap_step(ctx) == 1.0)
p = m.grid_snap_point(Vector((1.26, 3.74, 0.5)), 2, 0.5)
chk("grid_snap_point : (1.26, 3.74, 0.5) au pas 0.5 -> (1.5, 3.5, 0.5), hauteur gardée", same(p, (1.5, 3.5, 0.5)), r4(p))
p = m.grid_snap_point(Vector((1.26, 3.74, 0.5)), 2, 0.0)
chk("pas nul : point inchangé", same(p, (1.26, 3.74, 0.5)))
p = m.grid_snap_point(Vector((-2.6, -0.4, 0)), 2, 1.0)
chk("coordonnées négatives : (-2.6, -0.4) -> (-3, 0)", same(p, (-3, 0, 0)), r4(p))
chk("grid_snap_len : 2.3 au pas 0.5 -> 2.5 ; -1.2 au pas 1 -> -1 ; None reste None",
    abs(m.grid_snap_len(2.3, 0.5) - 2.5) < 1e-12 and abs(m.grid_snap_len(-1.2, 1.0) + 1.0) < 1e-12 and m.grid_snap_len(None, 1.0) is None)

t = Tool("polyligne", (12, 9, 0))
t.move((3.4, 2.6, 0))
chk("Polyline, Grid Snap pas 1 : curseur en (3.4, 2.6) -> (3, 3, 0)", same(t.o.cur, (3, 3, 0)), r4(t.o.cur))
chk("... une croix marque le nœud à l'écran (le réticule reste sous la souris)", t.o.track_screen is not None and same(t.o.track_screen, px((3, 3, 0)), 1e-3) and t.o.snap_screen is None, t.o.track_screen)
st.grid_snap = False; t.move((3.4, 2.6, 0))
chk("... Grid Snap coupé : pas de croix, le point suit la souris", t.o.track_screen is None and same(t.o.cur, (3.4, 2.6, 0)), (t.o.track_screen, r4(t.o.cur)))
st.grid_snap = True; t.move((3.4, 2.6, 0))
t.click((3.4, 2.6, 0))
t.click((7.45, 2.2, 0))
chk("deux clics : points posés sur la grille (3,3) et (7,2)", [r4(p) for p in t.o.points] == [(3, 3, 0), (7, 2, 0)], [r4(p) for p in t.o.points])
st.grid_snap_step = 0.5
t.move((9.3, 4.8, 0))
chk("pas 0.5 : (9.3, 4.8) -> (9.5, 5)", same(t.o.cur, (9.5, 5, 0)), r4(t.o.cur))
st.grid_snap_step = 1.0
t.key('F9', (9.3, 4.8, 0)); t.move((9.3, 4.8, 0))
chk("F9 pendant la commande : Grid Snap coupé, le point suit la souris", st.grid_snap is False and same(t.o.cur, (9.3, 4.8, 0)), r4(t.o.cur))
t.key('F9', (9.3, 4.8, 0)); t.move((9.3, 4.8, 0))
chk("F9 à nouveau : Grid Snap rétabli", st.grid_snap is True and same(t.o.cur, (9, 5, 0)), r4(t.o.cur))
st.ortho = True
t.move((11.45, 4.4, 0))
chk("Ortho + Grid Snap : depuis (7,2), curseur (11.45, 4.4) -> (11, 2)", same(t.o.cur, (11, 2, 0)) and t.o.track_label == "Ortho", (r4(t.o.cur), t.o.track_label))
st.ortho = False
st.polar = True; st.polar_angle = '30'
t.move((7 + 4.3 * math.cos(math.radians(30)), 2 + 4.3 * math.sin(math.radians(30)), 0))
d = t.o.cur - t.o.points[-1]
chk("Polar 30° + Grid Snap : la direction reste à 30°, la longueur passe de 4,3 à 4 (pas entier)",
    t.o.track_label.startswith("Polar 30") and abs(d.length - 4.0) < 1e-6 and abs(math.degrees(math.atan2(d.y, d.x)) - 30.0) < 1e-4, (r4(d), t.o.track_label))
st.polar = False
# repérage (SmartTrack) et grille : le plus proche de la souris l'emporte
t.move((11.45, 2.95, 0))
chk("souris sur la ligne de repérage du premier point (y = 3) : le repérage gagne, x reste sur la grille -> (11, 3)",
    same(t.o.cur, (11, 3, 0)) and bool(t.o.track_lines), (r4(t.o.cur), t.o.track_label))
t.move((11.45, 2.2, 0))
chk("souris plus près du nœud (11, 2) que de la ligne y = 3 : le nœud gagne", same(t.o.cur, (11, 2, 0)), (r4(t.o.cur), t.o.track_label))
t.key('X', (11.45, 2.9, 0)); t.move((11.45, 2.9, 0))
chk("verrou X + Grid Snap : (11, 2)", same(t.o.cur, (11, 2, 0)) and t.o.lock == 0, r4(t.o.cur))
t.key('X', (11.45, 2.9, 0))
t.end()

# les accrochages objet gagnent sur la grille
clear()
seg = m.build_polyline(BC, "Seg", [Vector((2.3, 2.3, 0)), Vector((8.7, 2.3, 0))], False)
BC.view_layer.update()
t = Tool("polyligne", (12, 9, 0))
t.move((2.6, 2.5, 0))
chk("près d'une extrémité hors grille (2.3, 2.3) : l'accrochage objet gagne", same(t.o.cur, (2.3, 2.3, 0)) and m.SNAP_NAMES.get(t.o.snap_kind) == "End", (r4(t.o.cur), t.o.snap_kind))
t.move((4.4, 6.6, 0))
chk("loin de tout objet : la grille (4, 7)", same(t.o.cur, (4, 7, 0)) and t.o.snap_kind is None, r4(t.o.cur))
# coordonnées tapées : elles gagnent aussi
t.click((4.4, 6.6, 0))
t.typ("2.25", (9, 7, 0)); t.move((9.2, 7.1, 0)); t.key('RET', (9.2, 7.1, 0))
chk("longueur tapée 2.25 : respectée telle quelle (pas arrondie au pas)", len(t.o.points) == 2 and abs((t.o.points[1] - t.o.points[0]).length - 2.25) < 1e-6, [r4(p) for p in t.o.points])
t.end()

# unités : le pas est écrit dans l'unité affichée
clear()
us = BC.scene.unit_settings
us.system = 'METRIC'; us.scale_length = 1.0; us.length_unit = 'MILLIMETERS'
bpy.ops.dessin.grid_snap_step(value=250.0)
chk("scène en mètres affichée en mm, pas 250 choisi dans le menu : 0,25 unité Blender", abs(m.grid_snap_step(ctx) - 0.25) < 1e-9 and abs(st.grid_snap_step - 0.25) < 1e-7, (m.grid_snap_step(ctx), st.grid_snap_step))
chk("... écrit « 250 mm »", m.grid_step_text(ctx) == "250 mm", m.grid_step_text(ctx))
t = Tool("polyligne", (12, 9, 0)); t.move((3.4, 2.6, 0))
chk("... curseur (3.4, 2.6) -> (3.5, 2.5)", same(t.o.cur, (3.5, 2.5, 0)), r4(t.o.cur)); t.end()
us.scale_length = 0.001
bpy.ops.dessin.grid_snap_step(value=5.0)
chk("scène en mm (1 unité = 1 mm), pas 5 mm : 5 unités Blender", abs(m.grid_snap_step(ctx) - 5.0) < 1e-9 and m.grid_step_text(ctx) == "5 mm", (m.grid_snap_step(ctx), m.grid_step_text(ctx)))
us.length_unit = 'CENTIMETERS'
chk("même scène affichée en cm : le pas ne change pas (5 unités), il s'écrit 0.5 cm", abs(m.grid_snap_step(ctx) - 5.0) < 1e-9 and m.grid_step_text(ctx) == "0.5 cm", (m.grid_snap_step(ctx), m.grid_step_text(ctx)))
# réglage d'usine : coupé, pas de 10 cm quelle que soit la scène
st.property_unset("grid_snap"); st.property_unset("grid_snap_step")
chk("réglage d'usine : Grid Snap coupé", st.grid_snap is False and m.grid_snap_step(ctx) == 0.0)
chk("réglage d'usine : pas de 10 cm (0,1 m)", abs(st.grid_snap_step - m.GRID_SNAP_DEFAULT_M) < 1e-7 and abs(m.GRID_SNAP_DEFAULT_M - 0.1) < 1e-12, st.grid_snap_step)
st.grid_snap = True
def menu_checked():
    lay = draw_menu(m.DESSIN_MT_grid_snap)
    return [it.text for it in lay.log if it.kind == "op" and it.idname == "dessin.grid_snap_step" and it.icon == 'RADIOBUT_ON']
for unit, scale, text, bu, line in (('CENTIMETERS', 0.001, "10 cm", 100.0, "10 cm"), ('MILLIMETERS', 0.001, "100 mm", 100.0, "100 mm"), ('MILLIMETERS', 1.0, "100 mm", 0.1, "100 mm"),
                                    ('METERS', 1.0, "0.1 m", 0.1, "0.1 m"), ('CENTIMETERS', 1.0, "10 cm", 0.1, "10 cm"), ('CENTIMETERS', 0.01, "10 cm", 10.0, "10 cm")):
    us.system = 'METRIC'; us.length_unit = unit; us.scale_length = scale
    chk(f"10 cm par défaut, scène en {unit.lower()} (échelle {scale:g}) : « {text} », {bu:g} unité(s) Blender, coché dans le menu",
        m.grid_step_text(ctx) == text and abs(m.grid_snap_step(ctx) - bu) < 1e-9 * max(1.0, bu) and menu_checked() == [line], (m.grid_step_text(ctx), m.grid_snap_step(ctx), menu_checked()))
us.system = 'IMPERIAL'; us.length_unit = 'INCHES'; us.scale_length = 1.0
chk("10 cm par défaut, scène en pouces : 3.937 in, soit 0,1 unité Blender", m.grid_step_text(ctx).startswith("3.937") and abs(m.grid_snap_step(ctx) - 0.1) < 1e-7, (m.grid_step_text(ctx), m.grid_snap_step(ctx)))
us.system = 'NONE'; us.scale_length = 1.0
chk("10 cm par défaut, scène sans unités : 0.1", m.grid_step_text(ctx) == "0.1" and m.grid_snap_step(ctx) == 0.1 and menu_checked() == ["0.1"], (m.grid_step_text(ctx), menu_checked()))
st.grid_snap_step = 1.0          # (Grid Snap reste actif, pas 1, pour la suite)

# plan de construction personnalisé : la grille est celle du plan
o0, x0 = Vector((0.3, 0.2, 0.0)), Vector((math.cos(math.radians(30)), math.sin(math.radians(30)), 0.0))
fr = m.cp_frame(o0, x0, Vector((0, 0, 1)).cross(x0))
m._CPLANE["cur"] = fr
p = m.grid_snap_point(Vector((4.37, 3.11, 0.0)), 3, 1.0)
d = p - o0
a, b = d.dot(fr[1]), d.dot(fr[2])
chk("CPlane tourné de 30° et décalé : le point tombe sur un nœud de SA grille", abs(a - round(a)) < 1e-5 and abs(b - round(b)) < 1e-5 and abs(d.dot(fr[3])) < 1e-9, (a, b))
chk("... le nœud le plus proche (moins d'un demi-pas sur chaque axe)", abs((Vector((4.37, 3.11, 0)) - o0).dot(fr[1]) - a) <= 0.5 and abs((Vector((4.37, 3.11, 0)) - o0).dot(fr[2]) - b) <= 0.5)
m._CPLANE["cur"] = None

# hauteurs : boîte et verrou Z (vue inclinée)
clear(); oblique()
t = Tool("boite", (12, 9, 0))
t.click((2.2, 1.8, 0)); t.click((6.4, 4.9, 0))
chk("Boîte : base posée sur la grille (2,2) - (6,5)", [r4(p) for p in t.o.points] == [(2, 2, 0), (6, 5, 0)], [r4(p) for p in t.o.points])
t.move((6, 5, 2.3))
h = (t.o.cur - t.o.points[0]).dot(Vector((0, 0, 1)))
chk("... hauteur désignée vers 2,3 : ramenée à 2", abs(h - 2.0) < 1e-6, h)
before = {x.name for x in bpy.data.objects}
t.click((6, 5, 2.3))
BC.view_layer.update()
new = [x for x in bpy.data.objects if x.name not in before]
bb = bbox(mverts(new[0])) if new else None
chk("... boîte créée : exactement 4 x 3 x 2", bb is not None and near(bb[0], (2, 2, 0)) and near(bb[1], (6, 5, 2)), None if bb is None else (r4(bb[0]), r4(bb[1])))
t.end()
clear()
t = Tool("cylindre", (12, 9, 0)); t.click((4.2, 3.9, 0)); t.click((6.3, 4.1, 0))
t.move((4, 4, 2.7))
before = {x.name for x in bpy.data.objects}; t.click((4, 4, 2.7)); BC.view_layer.update()
new = [x for x in bpy.data.objects if x.name not in before]
chk("Cylindre : centre (4,4), rayon 2, hauteur vers 2,7 ramenée à 3 -> 4 x 4 x 3", len(new) == 1 and same(new[0].dimensions, (4, 4, 3), 1e-5), [r4(x.dimensions) for x in new])
t.end(); clear()
crv = m.build_polyline(BC, "Sq", [Vector(q) for q in [(2, 2, 0), (6, 2, 0), (6, 5, 0), (2, 5, 0)]], True); BC.view_layer.update()
crv.select_set(True); BC.view_layer.objects.active = crv
t = Tool("extrude_crv", (12, 9, 0)); t.click((2, 2, 0)); t.move((2, 2, 6.7))
before = {x.name for x in bpy.data.objects}; t.click((2, 2, 6.7)); BC.view_layer.update()
new = [x for x in bpy.data.objects if x.name not in before]
chk("Extrude Curve d'un rectangle 4 x 3 : hauteur vers 6,7 ramenée à 7", len(new) == 1 and same(new[0].dimensions, (4, 3, 7), 1e-5), [r4(x.dimensions) for x in new])
t.end()
clear()
t = Tool("polyligne", (12, 9, 0))
t.click((5, 2, 0))
t.key('Z', (5, 2, 2.6)); t.move((5, 2, 2.6))
chk("Polyline, verrou Z + Grid Snap : hauteur vers 2,6 ramenée à 3", same(t.o.cur, (5, 2, 3)), r4(t.o.cur))
st.grid_snap = False
t.move((5, 2, 2.6))
chk("... Grid Snap coupé : la hauteur suit la souris (à un pixel près)", abs(t.o.cur.z - 2.6) < 0.15 and abs(t.o.cur.z - 3.0) > 0.2, r4(t.o.cur))
t.end(); top()

# réglage du pas : opérateurs et menu
defaults()
chk("dessin.grid_snap_set(on=True)", 'FINISHED' in bpy.ops.dessin.grid_snap_set(on=True) and st.grid_snap is True)
chk("dessin.grid_snap_set(on=False)", 'FINISHED' in bpy.ops.dessin.grid_snap_set(on=False) and st.grid_snap is False)
chk("dessin.grid_snap_step(value=5)", 'FINISHED' in bpy.ops.dessin.grid_snap_step(value=5.0) and abs(st.grid_snap_step - 5.0) < 1e-9)
lay = draw_menu(m.DESSIN_MT_grid_snap)
ops = [it for it in lay.log if it.kind == "op"]
steps = [it for it in ops if it.idname == "dessin.grid_snap_step" and not getattr(it, "ask", False)]
chk("menu Grid Snap : On / Off puis les pas proposés", [getattr(it, "on", None) for it in ops[:2]] == [True, False] and [it.value for it in steps] == list(m.GRID_SNAP_PRESETS), [getattr(it, "value", None) for it in steps])
chk("... le pas courant (5) est coché, lui seul", [it.value for it in steps if it.icon == 'RADIOBUT_ON'] == [5.0])
chk("... Off coché quand Grid Snap est coupé", ops[1].icon == 'RADIOBUT_ON' and ops[0].icon == 'RADIOBUT_OFF')
cust = [it for it in ops if getattr(it, "ask", False)]
chk("... une ligne « Custom... » ouvre la boîte de saisie", len(cust) == 1 and cust[0].icon == 'RADIOBUT_OFF', [it.text for it in cust])
st.grid_snap_step = 3.5; st.grid_snap = True
lay = draw_menu(m.DESSIN_MT_grid_snap)
ops = [it for it in lay.log if it.kind == "op"]
cust = [it for it in ops if getattr(it, "ask", False)]
chk("pas hors liste (3.5) : « Custom... (3.5) » coché, aucun pas proposé coché",
    len(cust) == 1 and "3.5" in cust[0].text and cust[0].icon == 'RADIOBUT_ON' and not [it for it in ops if it.idname == "dessin.grid_snap_step" and not getattr(it, "ask", False) and it.icon == 'RADIOBUT_ON'], [it.text for it in cust])
chk("... On coché", ops[0].icon == 'RADIOBUT_ON')
bpy.ops.dessin.grid_snap_step(value=0.1)
lay = draw_menu(m.DESSIN_MT_grid_snap)
ops = [it for it in lay.log if it.kind == "op"]
chk("pas 0.1 (non exact en simple précision) : c'est bien la ligne 0.1 qui est cochée, pas « Custom »",
    [round(it.value, 6) for it in ops if it.idname == "dessin.grid_snap_step" and not getattr(it, "ask", False) and it.icon == 'RADIOBUT_ON'] == [0.1]
    and [it.icon for it in ops if getattr(it, "ask", False)] == ['RADIOBUT_OFF'] and m.grid_step_text(ctx) == "0.1", m.grid_step_text(ctx))
st.grid_snap = True
chk("... et le pas vaut 0.1 unité exactement", m.grid_snap_step(ctx) == 0.1, m.grid_snap_step(ctx))
st.grid_snap_step = 3.5
o = make(m.DESSIN_OT_grid_snap_step); o.ask = True; o.value = 1.0
r = type(o).invoke(o, ctx, ev('LEFTMOUSE', 'PRESS', 0, 0))
chk("Custom... : la boîte s'ouvre sur le pas courant", 'RUNNING_MODAL' in r and abs(o.value - 3.5) < 1e-9, (r, o.value))
o.value = 0.75; r = type(o).execute(o, ctx)
chk("... OK : le pas saisi est appliqué", 'FINISHED' in r and abs(st.grid_snap_step - 0.75) < 1e-9, st.grid_snap_step)
defaults()

# ================= 5. Dessin réel de la barre (zones cliquables), clics, message =================
SEC = "dessin"
import sys, blf as _blf
CL = sys.modules['wanderer_cad.command_line']
class FakeBlf:
    """Texte : mesures réelles, tracé noté au lieu d'être dessiné (pas d'écran en mode sans fenêtre)."""
    BOLD = getattr(_blf, "BOLD", 0)
    def __init__(self): self.texts = []; self._pos = (0, 0); self.sizes = []
    def size(self, fid, sz, *a): self.sizes.append(sz); return _blf.size(fid, sz, *a)
    def dimensions(self, *a): return _blf.dimensions(*a)
    def color(self, *a): pass
    def position(self, fid, x, y, z): self._pos = (x, y)
    def draw(self, fid, text): self.texts.append((self._pos, text))
    def enable(self, *a): pass
    def disable(self, *a): pass
class FakeBpy:
    context = ctx
    def __getattr__(self, k): return getattr(bpy, k)
class FakeShader:
    def bind(self): pass
    def uniform_float(self, *a): pass
fills = []
class FakeBatch:
    def __init__(self, pos): self.pos = pos
    def draw(self, sh): fills.append(self.pos)
real = {k: getattr(CL, k) for k in ("bpy", "blf", "gpu", "get_shader", "batch_for_shader")}
fb = FakeBlf()
CL.bpy = FakeBpy(); CL.blf = fb
CL.gpu = NS(state=NS(blend_set=lambda *a: None, line_width_set=lambda *a: None))
CL.get_shader = lambda kind: FakeShader()
CL.batch_for_shader = lambda sh, kind, data: FakeBatch(data["pos"])
def draw_bars():
    fb.texts.clear(); fills.clear()
    CL.cmd_bar_cb(); CL.views_bar_cb(); CL.cmd_bar_cb(); CL.views_bar_cb()      # deux passes : les pastilles se calent l'une sur l'autre
    return list(m._VBAR["hit"].get(ptr, ())), list(m._CMD["hit"].get(ptr, ()))
try:
    defaults(); clear(); m.cmd_notice_clear()
    m._CMD["mouse"].pop(ptr, None)
    vh, chh = draw_bars()
    modes = [h for h in vh if h[4] == 'mode']
    order = [h[5] for h in modes]
    exp = []
    for k, _l, _t in m.MODE_BUTTONS:
        exp.append(k)
        if k in m.MODE_ARROWS: exp.append(m.MODE_ARROWS[k])
    chk("la barre se dessine sans erreur, avec une zone par bouton et par flèche, dans l'ordre", order == exp, order)
    ui = BC.preferences.system
    base = max(1.0, (ui.ui_scale or 1.0) * ((ui.dpi or 72) / 72.0))
    want = 11 * (1.0 + (base - 1.0) * 0.5) * 0.9
    chk("taille des barres au réglage 100 % : celle de l'ancien 90 % (texte 9,9 px au lieu de 11 à l'échelle 1)",
        m.CMD_SIZE_BASE == 0.9 and m.pref("cmd_size") == 100 and fb.sizes and all(abs(z - want) < 1e-6 for z in fb.sizes), (sorted(set(round(z, 3) for z in fb.sizes)), want))
    rect = {h[5]: h[:4] for h in modes}
    chk("... « Grid Snap » est écrit juste à gauche de « Ortho »", [t for _p, t in fb.texts if t in ("Grid Snap", "Ortho")][:2] == ["Grid Snap", "Ortho"]
        and rect["grid_snap"][0] < rect["gridsnapmenu"][0] < rect["ortho"][0], [t for _p, t in fb.texts][-12:])
    chk("... la flèche d'OSnap est collée à droite de son texte, avant SmartTrack",
        abs(rect["osnapmenu"][0] - rect["osnap_enable"][2]) < 1e-6 and rect["osnapmenu"][2] <= rect["smart_tracks"][0] and rect["osnapmenu"][2] - rect["osnapmenu"][0] > 15, (rect["osnap_enable"], rect["osnapmenu"]))
    zones = sorted(rect.values())
    chk("... aucune zone ne chevauche sa voisine", all(a[2] <= b[0] + 1e-6 for a, b in zip(zones, zones[1:])), zones)
    chk("... tout tient dans la vue (1000 px)", zones[0][0] >= 0 and zones[-1][2] <= region.width, (zones[0][0], zones[-1][2]))
    mid = lambda r: ((r[0] + r[2]) / 2.0, (r[1] + r[3]) / 2.0)
    del menus[:]
    ok = m.cmd_click_idle(ctx, ev('LEFTMOUSE', 'PRESS', *mid(rect["osnapmenu"])))
    chk("clic (hors commande) au milieu de la flèche d'OSnap : le menu des accrochages s'ouvre", ok and menus == ["DESSIN_MT_osnap"], menus)
    del menus[:]
    ok = m.cmd_click_idle(ctx, ev('LEFTMOUSE', 'PRESS', *mid(rect["gridsnapmenu"])))
    chk("clic au milieu de la flèche de Grid Snap : le menu du pas s'ouvre", ok and menus == ["DESSIN_MT_grid_snap"], menus)
    ok = m.cmd_click_idle(ctx, ev('LEFTMOUSE', 'PRESS', *mid(rect["grid_snap"])))
    chk("clic sur le texte « Grid Snap » : il s'active", ok and st.grid_snap is True)
    vh, chh = draw_bars()
    chk("... et la barre se redessine (bouton allumé)", [h[5] for h in vh if h[4] == 'mode'] == exp)
    st.grid_snap = False
    # pendant une commande : les mêmes clics agissent sans poser de point
    t = Tool("polyligne", (5, 5, 0)); t.click((5, 5, 0))
    vh, chh = draw_bars()
    rect = {h[5]: h[:4] for h in vh if h[4] == 'mode'}
    del menus[:]
    x, y = mid(rect["osnapmenu"])
    t.send(ev('MOUSEMOVE', 'NOTHING', x, y), ev('LEFTMOUSE', 'PRESS', x, y), ev('LEFTMOUSE', 'RELEASE', x, y))
    chk("pendant une commande, clic sur la flèche d'OSnap : le menu s'ouvre, aucun point n'est posé", menus == ["DESSIN_MT_osnap"] and len(t.o.points) == 1, (menus, len(t.o.points)))
    x, y = mid(rect["grid_snap"])
    t.send(ev('MOUSEMOVE', 'NOTHING', x, y), ev('LEFTMOUSE', 'PRESS', x, y), ev('LEFTMOUSE', 'RELEASE', x, y))
    chk("pendant une commande, clic sur « Grid Snap » : activé, aucun point posé, la commande continue", st.grid_snap is True and len(t.o.points) == 1 and 'RUNNING_MODAL' in t.last, (st.grid_snap, len(t.o.points), t.last))
    osnap_click("mid", shift=True)
    vh, chh = draw_bars()
    chk("accrochage ponctuel armé : la barre écrit « OSnap: Mid »", any(tx == "OSnap: Mid" for _p, tx in fb.texts), [tx for _p, tx in fb.texts][-12:])
    t.end(); st.grid_snap = False
    # message d'une commande qui n'a rien fait : visible dans la barre de commande, puis effacé
    m.cmd_notice("Duplicate Border: a closed solid has no free border")
    vh, chh = draw_bars()
    chk("message d'une commande : écrit dans la barre de commande", any("closed solid" in tx for _p, tx in fb.texts), [tx for _p, tx in fb.texts][:6])
    m._CMD["notice"] = (m._CMD["notice"][0], 0.0)          # délai écoulé
    vh, chh = draw_bars()
    chk("... puis effacé une fois le délai passé (retour à « Type a command »)", not any("closed solid" in tx for _p, tx in fb.texts) and any("Type a command" in tx for _p, tx in fb.texts), [tx for _p, tx in fb.texts][:6])
except Exception as e:
    import traceback; traceback.print_exc()
    chk("dessin de la barre", False, repr(e))
finally:
    for k, v in real.items(): setattr(CL, k, v)
defaults()

summary()
