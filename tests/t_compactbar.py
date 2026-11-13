# Barres du bas (onglets de vue, ligne de commande, boutons de mode) selon la largeur de la vue 3D.
# Règles demandées : les vues ne montent jamais au milieu ; dès que les onglets et les modes ne tiennent plus côte à côte,
# ils passent tout de suite en compact (T F P R + et icônes), côte à côte en bas, la ligne de commande au-dessus ;
# rien ne glisse sous la barre d'outils ou le panneau latéral ; la ligne de commande garde sa largeur d'origine en vue
# large et prend une largeur fixe, celle des barres du dessous, en vue réduite.
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE, 'harness.py')).read())
exec(open(_os.path.join(_HERE, 'prec_lib.py')).read())
_RENDER_BARS_LIB = True
exec(open(_os.path.join(_HERE, 'render_bars.py')).read())          # le vrai dessin des barres, tracés notés (install, draw)
import blf
BC = bpy.context
st = BC.scene.dessin
SEC = "?"
def chk(name, ok, meas=""): rec(SEC, name, ok, meas)
ptr = area.as_pointer()
LEFT = RIGHT = 44
install(ui_scale=1.0)
JOIN = staticmethod(lambda context: "dessin.join_tool")
m.DessinBase.active_tool_id = JOIN                   # un outil armé : la ligne de commande montre son indication
m.current_view_name = lambda c: "Perspective"       # la vue active, comme dans une vue libre
BG = tuple(CL._cmd_theme()["bg"])
def pills(ops):
    """Rectangles (x0, y0, x1, y1) des pastilles dessinées (fonds), dans l'ordre : ligne de commande, onglets, modes."""
    out = []
    for op in ops:
        if op[0] == "TRIS" and tuple(op[2]) == BG:
            xs = [p[0] for p in op[1]]; ys = [p[1] for p in op[1]]
            out.append((min(xs), min(ys), max(xs), max(ys)))
    return out
def overlap(a, b): return a[0] < b[2] - 0.01 and b[0] < a[2] - 0.01 and a[1] < b[3] - 0.01 and b[1] < a[3] - 0.01
def wide(p): return p[2] - p[0]
def ymid(p): return (p[1] + p[3]) / 2.0
def same_row(a, b): return a[1] < b[3] - 0.01 and b[1] < a[3] - 0.01          # les deux pastilles se font face
def texts(ops): return [o[3] for o in ops if o[0] == "text"]
def icons(ops): return [o for o in ops if o[0] == "LINES"]
def hits(): return list(m._VBAR["hit"].get(ptr, ()))
def mode_hits(): return [h for h in hits() if h[4] == 'mode']
def tab_hits(): return [h for h in hits() if h[4] in ('view', 'layout', 'viewmenu')]
def tab_texts(ops): return [t for t in texts(ops) if t in ("Top", "Front", "Perspective", "Right", "T", "F", "P", "R", "+")]
mid = lambda h: ((h[0] + h[2]) / 2.0, (h[1] + h[3]) / 2.0)
MODE_KEYS = []
for k, _l, _t in m.MODE_BUTTONS:
    MODE_KEYS.append(k)
    if k in m.MODE_ARROWS: MODE_KEYS.append(m.MODE_ARROWS[k])
LABELS = [l for _k, l, _t in m.MODE_BUTTONS]
sc = 0.9          # taille 100 % (échelle d'interface 1)
G = 18 * sc
def mk_tabs(names, active="Perspective"):
    return [('view', n, n, n == active) for n in names] + [('viewmenu', '+', '+', False)]
TABS = mk_tabs(["Top", "Front", "Perspective", "Right"])

# ================= 1. Niveaux de réduction =================
SEC = "niveaux"
m._cmd_font(11 * sc)
full_w = m.modes_layout(ctx, ptr, sc, compact=0, fixed=True)[2]
icon_w = m.modes_layout(ctx, ptr, sc, compact=1, fixed=True)[2]
two_w = m.modes_layout(ctx, ptr, sc, compact=2, fixed=True)[2]
tabs_w = m.tabs_widths(["Top", "Front", "Perspective", "Right", "+"], sc)[1]
short_w = m.tabs_widths(["T", "F", "P", "R", "+"], sc)[1]
one_w = m.tabs_widths(["P", "+"], sc)[1]
n_btn, n_arr = len(m.MODE_BUTTONS), len(m.MODE_ARROWS)
chk("barre de modes : en icônes, moins de la moitié de sa largeur en toutes lettres ; sur deux rangées, encore la moitié", icon_w < full_w / 2.0 and two_w < icon_w * 0.62, (round(full_w), round(icon_w), round(two_w)))
chk("largeur en icônes = 8 boutons de 26 + 5 flèches de 14 + écarts (à l'échelle)", abs(icon_w - (n_btn * 26 + n_arr * 14 + (n_btn + 1) * 4) * sc) < 1e-6, icon_w)
L0, L1, L2 = tabs_w + G + full_w, short_w + G + icon_w, short_w + G + two_w
chk("0 : les onglets et les modes tiennent côte à côte en toutes lettres", m.bars_compact(ctx, ptr, L0, sc, TABS) == 0 and m.bars_compact(ctx, ptr, 3000, sc, TABS) == 0, round(L0))
chk("1 : un pixel de moins -> tout de suite en compact (initiales + icônes)", m.bars_compact(ctx, ptr, L0 - 1, sc, TABS) == 1 and m.bars_compact(ctx, ptr, L1, sc, TABS) == 1, round(L1))
chk("2 : initiales + icônes ne tiennent plus côte à côte -> icônes sur deux rangées", m.bars_compact(ctx, ptr, L1 - 1, sc, TABS) == 2 and m.bars_compact(ctx, ptr, L2, sc, TABS) == 2, round(L2))
chk("3 : plus étroit encore -> seule la vue active et « + » restent à côté des icônes", m.bars_compact(ctx, ptr, L2 - 1, sc, TABS) == 3 and m.bars_compact(ctx, ptr, 50, sc, TABS) == 3)
many = mk_tabs(["Top", "Front", "Perspective", "Right", "Cuisine", "Salon", "Chambre parentale", "Salle de bain", "Layout 1", "Layout 2"])
many_w = m.tabs_widths([t[2] for t in many], sc)[1]
chk("beaucoup de vues : le passage en compact arrive plus tôt (les onglets comptent dans la largeur)", many_w > tabs_w * 2 and m.bars_compact(ctx, ptr, L0 + 100, sc, many) == 1
    and m.bars_compact(ctx, ptr, many_w + G + full_w, sc, many) == 0, round(many_w))
chk("une seule entrée d'onglet (« + » seul, pastille masquée) : seule la barre de modes compte", m.bars_compact(ctx, ptr, full_w, sc, mk_tabs([])) == 0 and m.bars_compact(ctx, ptr, full_w - 1, sc, mk_tabs([])) == 1)
m.oneshot_set(("end", "mid"))
chk("un accrochage ponctuel (« OSnap: End+Mid », plus long) ne fait pas basculer l'affichage", m.mode_label(ctx, "osnap_enable", "OSnap") == "OSnap: End+Mid" and m.bars_compact(ctx, ptr, L0, sc, TABS) == 0)
m.oneshot_reset()

# ================= 2. Onglets selon le niveau =================
SEC = "onglets"
chk("Top Front Perspective Right + -> T F P R +", m.tab_short_labels(["Top", "Front", "Perspective", "Right", "+"]) == ["T", "F", "P", "R", "+"])
got = m.tab_short_labels(["Top", "Front", "Perspective", "Right", "Plan", "Toiture", "Layout 1", "Layout 2", "Layout 12", "Vue 3", "+"])
chk("initiale déjà prise : deux lettres ; numéro final gardé", got == ["T", "F", "P", "R", "Pl", "To", "L1", "L2", "L12", "V3", "+"], got)
got = m.tab_short_labels(["A", "A", "A", "Ab", "Ab", ""])
chk("noms identiques ou vides : jamais deux abrégés pareils, pas d'erreur", len(set(got[:5])) == 5 and got[5] == "", got)
got = m.tab_short_labels(["étage", "Élévation", "2e étage", "3"])
chk("accents et chiffres : É, Él, 2, 3", got == ["É", "Él", "2", "3"], got)
chk("niveau 0 : noms complets", [t[2] for t in m.tabs_for_level(TABS, 0)] == ["Top", "Front", "Perspective", "Right", "+"])
chk("niveaux 1 et 2 : initiales, le nom complet reste attaché (info-bulle, clic)", [t[2] for t in m.tabs_for_level(TABS, 1)] == ["T", "F", "P", "R", "+"]
    and [t[2] for t in m.tabs_for_level(TABS, 2)] == ["T", "F", "P", "R", "+"] and [t[4] for t in m.tabs_for_level(TABS, 1)][:4] == ["Top", "Front", "Perspective", "Right"]
    and [t[1] for t in m.tabs_for_level(TABS, 1)][:4] == ["Top", "Front", "Perspective", "Right"])
chk("niveau 3 : la vue active et « + »", [(t[2], t[1]) for t in m.tabs_for_level(TABS, 3)] == [("P", "Perspective"), ("+", "+")], m.tabs_for_level(TABS, 3))
chk("niveau 3 sans vue active : la première et « + »", [t[2] for t in m.tabs_for_level(mk_tabs(["Top", "Front"], active=None), 3)] == ["T", "+"])
chk("le menu « + » liste toutes les vues (elles restent accessibles au niveau 3)", "BASE_VIEWS" in open(_os.path.join(_os.path.dirname(_SRC), "views.py"), encoding="utf-8").read().split("class DESSIN_MT_named_views")[1][:700])

# ================= 3. Icônes =================
SEC = "icônes"
for k, lab, _t in m.MODE_BUTTONS:
    seg = m.mode_icon_segments(k, 100.0, 50.0, 6.5)
    xs = [p[0] for p in seg]; ys = [p[1] for p in seg]
    chk(f"{lab} a une icône, qui tient dans sa case de 13 px", len(seg) >= 4 and len(seg) % 2 == 0 and min(xs) >= 93.5 - 1e-6 and max(xs) <= 106.5 + 1e-6 and min(ys) >= 43.5 - 1e-6 and max(ys) <= 56.5 + 1e-6,
        (len(seg) // 2, round(min(xs), 1), round(max(xs), 1), round(min(ys), 1), round(max(ys), 1)))
sigs = {k: tuple(round(v, 2) for p in m.mode_icon_segments(k, 0, 0, 7) for v in p) for k, _l, _t in m.MODE_BUTTONS}
chk("huit icônes toutes différentes", len(set(sigs.values())) == len(m.MODE_BUTTONS))

# ================= 4. Vue large : toutes lettres =================
SEC = "large"
ops, width, compact = draw(1500, LEFT, RIGHT); P = pills(ops)
chk("1500 px libres : les trois barres sur une ligne (vues, ligne de commande, modes), en toutes lettres", compact == 0 and len(P) == 3 and same_row(P[0], P[1]) and same_row(P[0], P[2])
    and P[1][2] <= P[0][0] and P[0][2] <= P[2][0] and all(l in texts(ops) for l in LABELS), [tuple(round(v) for v in p) for p in P])
ops, width, compact = draw(950, LEFT, RIGHT); P = pills(ops)
chk("950 px libres : la ligne de commande passe au-dessus ; vues et modes côte à côte en bas, en toutes lettres", compact == 0 and len(P) == 3 and same_row(P[1], P[2]) and P[0][1] >= max(P[1][3], P[2][3])
    and all(l in texts(ops) for l in LABELS) and tab_texts(ops) == ["Top", "Front", "Perspective", "Right", "+"], [tuple(round(v) for v in p) for p in P])
chk("... aucune icône n'est tracée", not icons(ops), len(icons(ops)))
full_hits = [(h[4], h[5]) for h in hits()]
chk("... zones cliquables : 5 onglets puis 8 boutons et 5 flèches", [h[5] for h in mode_hits()] == MODE_KEYS and len(tab_hits()) == 5, full_hits)

# ================= 5. Vue réduite : directement en compact, les deux en bas =================
SEC = "réduite"
free_lim = int(L0 + 24 * sc) + 1               # première largeur libre où les deux barres complètes tiennent côte à côte
ops, width, compact = draw(free_lim, LEFT, RIGHT); P = pills(ops)
chk(f"{free_lim} px libres : encore en toutes lettres, vues et modes côte à côte", compact == 0 and same_row(P[1], P[2]) and "Grid Snap" in texts(ops))
ops, width, compact = draw(free_lim - 2, LEFT, RIGHT); P = pills(ops)
chk(f"{free_lim - 2} px libres : directement en compact, sans passer par « les vues au milieu »", compact == 1 and tab_texts(ops) == ["T", "F", "P", "R", "+"] and len(icons(ops)) == n_btn
    and not any(l in texts(ops) for l in LABELS), tab_texts(ops))
chk("... vues et icônes côte à côte en bas, la ligne de commande au-dessus (même si elle tiendrait entre les deux)", same_row(P[1], P[2]) and P[1][2] <= P[2][0] and P[0][1] >= max(P[1][3], P[2][3]),
    [tuple(round(v) for v in p) for p in P])
ops, width, compact = draw(500, LEFT, RIGHT)
tx = texts(ops)
P = pills(ops)
chk("500 px libres : compact, vues T F P R + et icônes sur la même ligne du bas", compact == 1 and m._GROUP["compact"][ptr] == 1 and tab_texts(ops) == ["T", "F", "P", "R", "+"] and same_row(P[1], P[2]) and abs(P[1][1] - P[2][1]) < 1e-6, tab_texts(ops))
ic = icons(ops)
mh_ = mode_hits()
text_zones = [h for h in mh_ if h[5] in dict((k, 1) for k, _l, _t in m.MODE_BUTTONS)]
ok = True
for h, o in zip(text_zones, ic):
    xs = [p[0] for p in o[1]]; ys = [p[1] for p in o[1]]
    ok = ok and h[0] - 0.01 <= min(xs) and max(xs) <= h[2] + 0.01 and h[1] - 0.01 <= min(ys) and max(ys) <= h[3] + 0.01
chk("... huit icônes, chacune dessinée dans la zone cliquable de son bouton", ok and len(text_zones) == len(ic) == n_btn, len(ic))
chk("... l'icône d'un bouton actif prend la couleur du texte sélectionné, les autres la couleur estompée",
    all(tuple(o[2]) == tuple(CL._cmd_theme()["sel_t"] if m.mode_state(ctx, h[5]) else CL._cmd_theme()["dim"]) for h, o in zip(text_zones, ic)))
chk("... mêmes zones cliquables qu'en toutes lettres, dans le même ordre (mêmes clés, mêmes vues)", [(h[4], h[5]) for h in hits()] == full_hits, [(h[4], h[5]) for h in hits()])
chk("... bouton = 26 px, flèche = 14 px (à l'échelle)", all(abs((h[2] - h[0]) - (14 if h[5] in m.MODE_ARROWS.values() else 26) * sc) < 1e-6 for h in mh_), [round(h[2] - h[0], 2) for h in mh_])
chk("... trois pastilles entre la barre d'outils et le panneau latéral, sans chevauchement", len(P) == 3 and all(p[0] >= LEFT and p[2] <= LEFT + 500 for p in P)
    and not any(overlap(a, b) for i, a in enumerate(P) for b in P[i + 1:]), [tuple(round(v) for v in p) for p in P])
# clics dans la vue compacte
menus = []
m.call_menu_later = lambda c, name: menus.append(name)
byk = {h[5]: h for h in mode_hits()}
st.ortho = False
ok = m.cmd_click_idle(ctx, ev('LEFTMOUSE', 'PRESS', *mid(byk["ortho"])))
chk("clic sur l'icône Ortho : Ortho s'active", ok and st.ortho is True)
ops, width, compact = draw(500, LEFT, RIGHT)
i_ortho = [h[5] for h in text_zones].index("ortho")
chk("... et son icône passe à la couleur active", tuple(icons(ops)[i_ortho][2]) == tuple(CL._cmd_theme()["sel_t"]))
st.ortho = False
ok = m.cmd_click_idle(ctx, ev('LEFTMOUSE', 'PRESS', *mid(byk["osnapmenu"])))
chk("clic sur la flèche d'OSnap (14 px) : le menu des accrochages s'ouvre", ok and menus == ["DESSIN_MT_osnap"], menus)
ok = m.cmd_click_idle(ctx, ev('LEFTMOUSE', 'PRESS', *mid(byk["gridsnapmenu"])))
chk("clic sur la flèche de Grid Snap : le menu du pas s'ouvre", ok and menus[-1:] == ["DESSIN_MT_grid_snap"], menus)
chk("les onglets abrégés désignent toujours les vues par leur nom complet", [h[5] for h in tab_hits()][:4] == ["Top", "Front", "Perspective", "Right"], [h[5] for h in tab_hits()])
# info-bulles
h = byk["ortho"]
ops, width, compact = draw(500, LEFT, RIGHT, mouse=mid(h), tip=True)
chk("survol de l'icône Ortho : l'info-bulle commence par son nom", any(t.startswith("Ortho (F8)") for t in texts(ops)), texts(ops)[-2:])
h = byk["osnap_enable"]
ops, width, compact = draw(500, LEFT, RIGHT, mouse=mid(h), tip=True)
chk("survol de l'icône OSnap : « OSnap: » est ajouté devant l'explication", any(t.startswith("OSnap: Object snaps") for t in texts(ops)), texts(ops)[-2:])
h = [x for x in tab_hits() if x[5] == "Front"][0]
ops, width, compact = draw(500, LEFT, RIGHT, mouse=mid(h), tip=True)
chk("survol de l'onglet F : l'info-bulle donne « Front »", texts(ops)[-1] == "Front", texts(ops)[-2:])
ops, width, compact = draw(950, LEFT, RIGHT)
h = [x for x in tab_hits() if x[5] == "Front"][0]
ops, width, compact = draw(950, LEFT, RIGHT, mouse=mid(h), tip=True)
chk("vue large, survol de l'onglet Front : pas d'info-bulle (le nom est déjà écrit)", texts(ops).count("Front") == 1, texts(ops)[-3:])

# ================= 6. Vues très étroites : toujours côte à côte =================
SEC = "étroite"
ops, width, compact = draw(420, LEFT, RIGHT); P = pills(ops)
rows_y = sorted({round(h[1], 2) for h in mode_hits()})
chk("420 px libres : les icônes prennent deux rangées, à côté des vues T F P R +", compact == 2 and len(rows_y) == 2 and tab_texts(ops) == ["T", "F", "P", "R", "+"] and same_row(P[1], P[2]) and P[1][2] <= P[2][0],
    [tuple(round(v) for v in p) for p in P])
top_row = [h[5] for h in mode_hits() if round(h[1], 2) == rows_y[1]]; bot_row = [h[5] for h in mode_hits() if round(h[1], 2) == rows_y[0]]
chk("... Grid Snap, Ortho, Polar, OSnap en haut ; SmartTrack, Gumball, Auto CPlane, Quick Type en bas",
    [k for k in top_row if k in ("grid_snap", "ortho", "polar", "osnap_enable")] == ["grid_snap", "ortho", "polar", "osnap_enable"]
    and [k for k in bot_row if k in ("smart_tracks", "gumball", "auto_cplane", "cmd_type")] == ["smart_tracks", "gumball", "auto_cplane", "cmd_type"], (top_row, bot_row))
chk("... la pastille des modes a deux rangées de haut et contient tous ses boutons", abs((P[2][3] - P[2][1]) - m.modes_height(sc, 2)) < 1e-6
    and all(P[2][0] <= h[0] and h[2] <= P[2][2] and P[2][1] <= h[1] and h[3] <= P[2][3] for h in mode_hits()), tuple(round(v) for v in P[2]))
chk("... les vues sont centrées en hauteur sur elle, la ligne de commande est au-dessus des deux", abs(ymid(P[1]) - ymid(P[2])) < 1e-6 and P[0][1] >= P[2][3] and not any(overlap(a, b) for i, a in enumerate(P) for b in P[i + 1:]))
chk("... tout tient dans la place libre", all(p[0] >= LEFT and p[2] <= LEFT + 420 for p in P), [tuple(round(v) for v in p) for p in P])
byk = {h[5]: h for h in mode_hits()}
st.polar = False
ok = m.cmd_click_idle(ctx, ev('LEFTMOUSE', 'PRESS', *mid(byk["polar"])))
chk("... un clic sur une icône de la rangée du haut agit bien (Polar)", ok and st.polar is True)
st.polar = False
ops, width, compact = draw(300, LEFT, RIGHT); P = pills(ops)
chk("300 px libres : il ne reste que la vue active et « + », toujours à côté des icônes", compact == 3 and tab_texts(ops) == ["P", "+"] and same_row(P[1], P[2]) and P[1][2] <= P[2][0]
    and [h[5] for h in tab_hits()] == ["Perspective", "+"], (tab_texts(ops), [tuple(round(v) for v in p) for p in P]))
chk("... tout tient dans la place libre, rien ne se chevauche, la ligne de commande au-dessus", all(p[0] >= LEFT and p[2] <= LEFT + 300 for p in P) and not any(overlap(a, b) for i, a in enumerate(P) for b in P[i + 1:])
    and P[0][1] >= P[2][3])

# ================= 7. Balayage de toutes les largeurs, à trois échelles d'interface =================
SEC = "balayage"
for ui in (1.0, 1.5, 2.0):
    install(ui_scale=ui)
    s_ = (1.0 + (ui - 1.0) * 0.5) * 0.9
    m._cmd_font(11 * s_)
    side = m.tabs_widths(["P", "+"], s_)[1] + 18 * s_ + m.modes_layout(ctx, ptr, s_, compact=2, fixed=True)[2]
    lim = int(side + 24 * s_) + 2                       # plus étroit : même la vue active + « + » ne tient plus à côté des icônes
    lo = int(round(230 * s_ / 0.9))                     # plus étroit encore : la ligne de commande elle-même ne tient plus
    bad, centre, seen = [], [], set()
    for free in range(2400, lo - 1, -7):
        ops, width, compact = draw(free, LEFT, RIGHT)
        seen.add(compact)
        P = pills(ops)
        if len(P) != 3 or not all(p[0] >= LEFT - 0.01 and p[2] <= LEFT + free + 0.01 for p in P) or any(overlap(a, b) for i, a in enumerate(P) for b in P[i + 1:]):
            bad.append(free)
        elif not all(LEFT - 0.01 <= h[0] and h[2] <= LEFT + free + 0.01 for h in hits()):
            bad.append(-free)
        elif free >= lim and not same_row(P[1], P[2]):
            centre.append(free)                         # les vues ont quitté la ligne du bas
        elif free >= lim and compact and not P[0][1] >= max(P[1][3], P[2][3]) - 0.01:
            centre.append(-free)                        # vue réduite : la ligne de commande n'est pas au-dessus
    chk(f"échelle d'interface {ui:g} : de 2400 à {lo} px libres, les trois barres restent entre les panneaux et ne se chevauchent jamais", not bad, bad[:8])
    chk(f"... de 2400 à {lim} px, les vues ne montent jamais au milieu : toujours à côté des modes, en bas", not centre, centre[:8])
    chk(f"... et les quatre affichages ont été rencontrés (complet, compact, deux rangées, vue active seule)", seen == {0, 1, 2, 3}, seen)
install(ui_scale=1.0)
bad = []
for free in range(1400, 229, -11):
    ops, width, compact = draw(free, 0, 0)
    P = pills(ops)
    if len(P) != 3 or not all(p[0] >= -0.01 and p[2] <= free + 0.01 for p in P) or any(overlap(a, b) for i, a in enumerate(P) for b in P[i + 1:]):
        bad.append(free)
chk("panneaux fermés : de 1400 à 230 px, rien ne sort de la vue", not bad, bad[:8])
ops, width, compact = draw(240, LEFT, RIGHT)
ops, width, compact = draw(1000, LEFT, RIGHT)
chk("la vue redevient large : libellés complets de retour", compact == 0 and "Grid Snap" in texts(ops) and "Perspective" in texts(ops) and not icons(ops))

# ================= 8. Ligne de commande : largeur d'origine en vue large, largeur fixe en vue réduite =================
SEC = "ligne de commande"
LONG = "Polyline: next point [X/Y/Z: lock axis] [Shift: orthogonal] [U: undo] [C: close] [Enter: finish]"
def three(free):
    """Largeur de la ligne de commande dans trois situations : outil armé (longue indication), repos, commande en cours."""
    out = []
    ops, width, compact = draw(free, LEFT, RIGHT); out.append(wide(pills(ops)[0]))
    m.DessinBase.active_tool_id = staticmethod(lambda context: None)
    ops, width, compact = draw(free, LEFT, RIGHT); out.append(wide(pills(ops)[0])); idle = texts(ops)
    m._CMD["prompt"][ptr] = LONG
    ops, width, compact = draw(free, LEFT, RIGHT); out.append(wide(pills(ops)[0])); run = texts(ops)
    m._CMD["prompt"].pop(ptr, None)
    m.DessinBase.active_tool_id = JOIN
    return out, idle, run, compact
(w_tool, w_idle, w_run), t_idle, t_run, compact = three(950)
chk("950 px, vue non réduite : la ligne de commande garde sa largeur d'origine, celle de son texte (au repos elle est plus courte)",
    compact == 0 and "Type a command" in t_idle and w_idle < w_tool - 50 and w_idle < w_run - 50, (round(w_tool), round(w_idle), round(w_run)))
chk("... sans jamais dépasser 760 px (à l'échelle)", max(w_tool, w_idle, w_run) <= 760 * sc + 1e-6, round(max(w_tool, w_idle, w_run)))
ops, width, compact = draw(950, LEFT, RIGHT); P = pills(ops)
m._cmd_font(11 * sc)
W_ = lambda t: blf.dimensions(0, t)[0]
m._cmd_bold(True); wj = W_("Join"); m._cmd_bold(False)
want = wj + 8 * sc + W_("Click the objects to join (or select them first)  ·  Enter / Space: join  ·  Esc: leave") + 8 * sc + (12 * sc + W_("Esc") + W_(" ") + W_("leave")) + 8 * sc + 2 * 14 * sc
chk("... exactement la largeur de son contenu (nom + indication + touche + marges), comme en 2.97.2", abs(wide(P[0]) - want) < 0.6, (round(wide(P[0]), 1), round(want, 1)))
for free, lvl, what in ((500, 1, "T F P R + et icônes"), (420, 2, "vues et icônes sur deux rangées"), (300, 3, "vue active, « + » et icônes")):
    ops, width, compact = draw(free, LEFT, RIGHT); P = pills(ops)
    chk(f"{free} px, vue réduite ({what}) : elle a la largeur de la ligne du dessous, bord à bord", compact == lvl and abs(wide(P[0]) - (wide(P[1]) + G + wide(P[2]))) < 1e-6
        and abs(P[0][0] - P[1][0]) < 1e-6 and abs(P[0][2] - P[2][2]) < 1e-6, (round(wide(P[0]), 1), round(wide(P[1]) + G + wide(P[2]), 1)))
    (w_tool, w_idle, w_run), t_idle, t_run, compact = three(free)
    chk(f"... largeur fixe : la même avec un outil armé, au repos ou pendant une commande au long message", abs(w_tool - w_idle) < 1e-6 and abs(w_tool - w_run) < 1e-6 and "Type a command" in t_idle
        and any("Polyline" in t for t in t_run), (round(w_tool, 1), round(w_idle, 1), round(w_run, 1)))
bad, reduced, full_free = [], 0, 0
for free in range(2400, lim - 1, -9):
    ops, width, compact = draw(free, LEFT, RIGHT); P = pills(ops)
    if compact:
        reduced += 1
        lo_, hi_ = min(P[1][0], P[2][0]), max(P[1][2], P[2][2])
        if P[0][0] < lo_ - 0.01 or P[0][2] > hi_ + 0.01:
            bad.append(free)
    else:
        full_free += 1
chk("balayage : en vue réduite, la ligne de commande ne dépasse jamais les barres du dessous", not bad and reduced > 30 and full_free > 30, (bad[:8], reduced, full_free))
chk("saisie d'une commande, vue très étroite : au moins 270 px si la vue les offre, sinon toute la place libre",
    abs(m.cmd_fixed_width(216, -100, True, 153, 149, sc, typing=True) - 216) < 1e-6 and abs(m.cmd_fixed_width(300, -100, True, 153, 149, sc, typing=True) - 270) < 1e-6
    and abs(m.cmd_fixed_width(300, -100, True, 153, 149, sc) - 153) < 1e-6)

# ================= 9. Préférence « Mode bar: icons only » : la barre de droite reste en icônes, ou non =================
SEC = "préférence icônes"
def snap(ops):
    """Tracés arrondis, pour comparer deux dessins."""
    out = []
    for o in ops:
        if o[0] == "text": out.append((o[0], round(o[1], 2), round(o[2], 2), o[3], round(o[4], 2), tuple(round(v, 3) for v in o[5])))
        else: out.append((o[0], tuple((round(x, 2), round(y, 2)) for x, y in o[1]), tuple(round(v, 3) for v in o[2])))
    return out
src_prefs = open(_os.path.join(_os.path.dirname(_SRC), "preferences.py"), encoding="utf-8").read()
ann = getattr(m.DESSIN_AP_prefs, "__annotations__", {}).get("mode_icons")
kw = getattr(ann, "keywords", None) or {}
chk("le réglage existe dans les préférences : case à cocher « Mode bar: icons only », décochée par défaut", kw.get("default") is False and kw.get("name") == "Mode bar: icons only"
    and m.PREF_DEFAULTS.get("mode_icons") is False and m.pref("mode_icons") is False, (kw.get("name"), kw.get("default")))
chk("... il est affiché dans le panneau (rubrique Command line) et redessine les vues quand on le change", 'cbox.prop(self, "mode_icons")' in src_prefs and kw.get("update") is m._update_cmd_line)
chk("... « Reset to defaults » le remet à zéro (il fait partie des réglages par défaut)", "mode_icons" in list(m.PREF_DEFAULTS) and "for name in list(PREF_DEFAULTS)" in src_prefs)
chk("décoché : icônes seulement en vue réduite (comportement inchangé)", m.modes_icons(0) is False and m.modes_icons(1) is True and m.modes_icons(3) is True)
ref = {}
for free in (1500, 950, 500, 420, 300):
    ops, width, compact = draw(free, LEFT, RIGHT); ref[free] = (snap(ops), compact, [(h[4], h[5]) for h in hits()])
m.PREF_DEFAULTS["mode_icons"] = True
m._cmd_font(11 * sc)
chk("coché : icônes à tous les niveaux", all(m.modes_icons(l) is True for l in (0, 1, 2, 3)))
chk("... la barre de modes a sa largeur en icônes dès le niveau 0", abs(m.modes_layout(ctx, ptr, sc, compact=0, fixed=True)[2] - icon_w) < 1e-6 and abs(m.modes_layout(ctx, ptr, sc, compact=2, fixed=True)[2] - two_w) < 1e-6,
    round(m.modes_layout(ctx, ptr, sc, compact=0, fixed=True)[2], 1))
L0i = tabs_w + G + icon_w
chk("... les noms des vues restent entiers tant qu'ils tiennent à côté des icônes (seuil plus bas qu'avec les libellés)", L0i < L0 - 200 and m.bars_compact(ctx, ptr, L0i, sc, TABS) == 0
    and m.bars_compact(ctx, ptr, L0i - 1, sc, TABS) == 1, (round(L0i), round(L0)))
chk("... les seuils suivants (deux rangées, vue active seule) ne changent pas", m.bars_compact(ctx, ptr, L1, sc, TABS) == 1 and m.bars_compact(ctx, ptr, L1 - 1, sc, TABS) == 2 and m.bars_compact(ctx, ptr, L2 - 1, sc, TABS) == 3)
ops, width, compact = draw(1500, LEFT, RIGHT); P = pills(ops)
chk("1500 px libres, coché : vues en toutes lettres, ligne de commande, modes en icônes, sur une seule ligne", compact == 0 and len(P) == 3 and same_row(P[0], P[1]) and same_row(P[0], P[2])
    and P[1][2] <= P[0][0] and P[0][2] <= P[2][0] and tab_texts(ops) == ["Top", "Front", "Perspective", "Right", "+"], [tuple(round(v) for v in p) for p in P])
chk("... huit icônes tracées, plus aucun libellé de mode", len(icons(ops)) == n_btn and not any(l in texts(ops) for l in LABELS), len(icons(ops)))
chk("... la pastille des modes a exactement sa largeur en icônes, sur une rangée", abs(wide(P[2]) - icon_w) < 1e-6 and abs((P[2][3] - P[2][1]) - m.modes_height(sc, 0)) < 1e-6, round(wide(P[2]), 1))
chk("... mêmes zones cliquables qu'en toutes lettres, dans le même ordre ; bouton = 26 px, flèche = 14 px", [(h[4], h[5]) for h in hits()] == ref[1500][2]
    and all(abs((h[2] - h[0]) - (14 if h[5] in m.MODE_ARROWS.values() else 26) * sc) < 1e-6 for h in mode_hits()), [round(h[2] - h[0], 2) for h in mode_hits()])
zones = [h for h in mode_hits() if h[5] in dict((k, 1) for k, _l, _t in m.MODE_BUTTONS)]
ok = True
for h, o in zip(zones, icons(ops)):
    xs = [p[0] for p in o[1]]; ys = [p[1] for p in o[1]]
    ok = ok and h[0] - 0.01 <= min(xs) and max(xs) <= h[2] + 0.01 and h[1] - 0.01 <= min(ys) and max(ys) <= h[3] + 0.01
chk("... chaque icône est dessinée dans la zone cliquable de son bouton", ok and len(zones) == n_btn)
byk = {h[5]: h for h in mode_hits()}
st.ortho = False
ok = m.cmd_click_idle(ctx, ev('LEFTMOUSE', 'PRESS', *mid(byk["ortho"])))
chk("... un clic sur l'icône Ortho l'active ; un clic sur la flèche d'OSnap ouvre son menu", ok and st.ortho is True
    and m.cmd_click_idle(ctx, ev('LEFTMOUSE', 'PRESS', *mid(byk["osnapmenu"]))) and menus[-1:] == ["DESSIN_MT_osnap"], menus[-1:])
st.ortho = False
ops, width, compact = draw(1500, LEFT, RIGHT, mouse=mid(byk["ortho"]), tip=True)
chk("... survol de l'icône Ortho en vue large : l'info-bulle commence par son nom", any(t.startswith("Ortho (F8)") for t in texts(ops)), texts(ops)[-2:])
ops, width, compact = draw(1500, LEFT, RIGHT, mouse=mid(byk["osnap_enable"]), tip=True)
chk("... survol de l'icône OSnap : « OSnap: » devant l'explication", any(t.startswith("OSnap: Object snaps") for t in texts(ops)), texts(ops)[-2:])
ops, width, compact = draw(1500, LEFT, RIGHT)
h = [x for x in tab_hits() if x[5] == "Front"][0]
ops, width, compact = draw(1500, LEFT, RIGHT, mouse=mid(h), tip=True)
chk("... survol de l'onglet Front : pas d'info-bulle (le nom reste écrit en entier)", texts(ops).count("Front") == 1, texts(ops)[-3:])
m.oneshot_set(("end", "mid"))
ops, width, compact = draw(1500, LEFT, RIGHT); P2 = pills(ops)
chk("... un accrochage ponctuel ne change pas la largeur de la barre d'icônes", abs(wide(P2[2]) - icon_w) < 1e-6 and not any(t.startswith("OSnap") for t in texts(ops)))
m.oneshot_reset()
# la ligne de commande garde sa largeur d'origine tant que la vue n'est pas réduite
(w_tool, w_idle, w_run), t_idle, t_run, compact = three(1500)
chk("1500 px, coché : la ligne de commande garde sa largeur d'origine, celle de son texte (plus courte au repos)", compact == 0 and "Type a command" in t_idle and w_idle < w_tool - 50 and w_idle < w_run - 50
    and max(w_tool, w_run) <= 760 * sc + 1e-6, (round(w_tool), round(w_idle), round(w_run)))
ops, width, compact = draw(1500, LEFT, RIGHT); P = pills(ops)
chk("... exactement la largeur de son contenu, comme sans le réglage", abs(wide(P[0]) - want) < 0.6, (round(wide(P[0]), 1), round(want, 1)))
free_i = free_lim - 2                               # là où, sans le réglage, tout passait en compact
ops, width, compact = draw(free_i, LEFT, RIGHT); P = pills(ops)
chk(f"{free_i} px libres (sans le réglage : T F P R +) : les noms des vues restent entiers à côté des icônes", ref and compact == 0 and tab_texts(ops) == ["Top", "Front", "Perspective", "Right", "+"]
    and len(icons(ops)) == n_btn and same_row(P[1], P[2]) and not any(overlap(a, b) for i, a in enumerate(P) for b in P[i + 1:]), tab_texts(ops))
(w_tool, w_idle, w_run), t_idle, t_run, compact = three(free_i)
chk("... et la ligne de commande n'y prend pas la largeur fixe (la vue n'est pas réduite)", compact == 0 and w_idle < w_tool - 50, (round(w_tool), round(w_idle), round(w_run)))
free_c = int(L0i + 24 * sc) - 1
ops, width, compact = draw(free_c + 2, LEFT, RIGHT); c_before = compact
ops, width, compact = draw(free_c, LEFT, RIGHT); P = pills(ops)
chk(f"{free_c} px libres : les noms ne tiennent plus à côté des icônes -> T F P R +, ligne de commande au-dessus, largeur fixe", c_before == 0 and compact == 1 and tab_texts(ops) == ["T", "F", "P", "R", "+"]
    and same_row(P[1], P[2]) and P[0][1] >= max(P[1][3], P[2][3]) and abs(wide(P[0]) - (wide(P[1]) + G + wide(P[2]))) < 1e-6, [tuple(round(v) for v in p) for p in P])
same = []
for free in (500, 420, 300):
    ops, width, compact = draw(free, LEFT, RIGHT)
    same.append(snap(ops) == ref[free][0] and compact == ref[free][1])
chk("500, 420 et 300 px libres : dessin strictement identique avec ou sans le réglage (la vue réduite ne change pas)", all(same), same)
for ui in (1.0, 1.5, 2.0):
    install(ui_scale=ui)
    s_ = (1.0 + (ui - 1.0) * 0.5) * 0.9
    m._cmd_font(11 * s_)
    side = m.tabs_widths(["P", "+"], s_)[1] + 18 * s_ + m.modes_layout(ctx, ptr, s_, compact=2, fixed=True)[2]
    lim_i = int(side + 24 * s_) + 2
    lo = int(round(230 * s_ / 0.9))
    bad, centre, noicon, seen = [], [], [], set()
    for free in range(2400, lo - 1, -7):
        ops, width, compact = draw(free, LEFT, RIGHT)
        seen.add(compact)
        P = pills(ops)
        if len(icons(ops)) != n_btn or any(l in texts(ops) for l in LABELS):
            noicon.append(free)
        if len(P) != 3 or not all(p[0] >= LEFT - 0.01 and p[2] <= LEFT + free + 0.01 for p in P) or any(overlap(a, b) for i, a in enumerate(P) for b in P[i + 1:]):
            bad.append(free)
        elif not all(LEFT - 0.01 <= h[0] and h[2] <= LEFT + free + 0.01 for h in hits()):
            bad.append(-free)
        elif free >= lim_i and not same_row(P[1], P[2]):
            centre.append(free)
        elif free >= lim_i and compact and not P[0][1] >= max(P[1][3], P[2][3]) - 0.01:
            centre.append(-free)
    chk(f"coché, échelle d'interface {ui:g} : de 2400 à {lo} px libres, la barre de droite est toujours en icônes, jamais en libellés", not noicon, noicon[:8])
    chk(f"... les trois barres restent entre les panneaux, sans chevauchement ; les vues ne montent jamais au milieu", not bad and not centre, (bad[:8], centre[:8]))
    chk(f"... les quatre affichages sont rencontrés (noms entiers, initiales, deux rangées, vue active seule)", seen == {0, 1, 2, 3}, seen)
install(ui_scale=1.0)
m.PREF_DEFAULTS["mode_icons"] = False
back = []
for free in (1500, 950, 500, 420, 300):
    ops, width, compact = draw(free, LEFT, RIGHT)
    back.append(snap(ops) == ref[free][0] and compact == ref[free][1])
ops, width, compact = draw(1500, LEFT, RIGHT)
chk("décoché de nouveau : les libellés reviennent, dessin identique à celui d'avant", all(back) and "Grid Snap" in texts(ops) and not icons(ops), back)

summary()
