# Les barres du bas (onglets de vue, ligne de commande, modes) quand la vue 3D montre 4 vues : elles ne sont dessinées
# qu'une fois, centrées sous les quatre vues, au lieu d'une fois par vue.
#   - 4 vues séparées (le bouton à gauche des onglets) : quatre vues 3D, chacune avec son titre et son affichage ; les
#     barres montrent la vue active ;
#   - Toggle Quad View de Blender (Ctrl + Alt + Q) : quatre régions d'une seule vue 3D.
# Le dessin est le vrai (tracés notés) ; les vues sont simulées à leurs positions dans la fenêtre.
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE, 'harness.py')).read())
exec(open(_os.path.join(_HERE, 'prec_lib.py')).read())
_RENDER_BARS_LIB = True
exec(open(_os.path.join(_HERE, 'render_bars.py')).read())
BC = bpy.context
SEC = "?"
def chk(name, ok, meas=""): rec(SEC, name, ok, meas)
ptr = area.as_pointer()


class R(NS):
    def as_pointer(self): return self.p
    def tag_redraw(self): pass


class A(NS):
    def as_pointer(self): return self.p
    def tag_redraw(self): self.redraws += 1
    def header_text_set(self, *a): pass


def win_region(p, x, y, w, h): return R(p=p, type='WINDOW', x=x, y=y, width=w, height=h, data=rv3d)
QW, QH = 600, 400
BL, BR_, TL, TR = win_region(21, 0, 0, QW, QH), win_region(22, QW + 2, 0, QW, QH), win_region(23, 0, QH + 2, QW, QH), win_region(24, QW + 2, QH + 2, QW, QH)
TOOLS = R(p=30, type='TOOLS', x=0, y=0, width=44, height=2 * QH + 2)
ONE = win_region(20, 0, 0, 2 * QW + 2, 2 * QH + 2)
install(ui_scale=1.0)
m.DessinBase.active_tool_id = staticmethod(lambda context: None)
TH = CL._cmd_theme()
c3 = lambda c: tuple(round(v, 3) for v in c)
BG, SEL, CHIP, ACC, DIM, SEL_T = c3(TH["bg"]), c3(TH["sel"]), c3(TH["chip"]), c3(TH["acc"]), c3(TH["dim"]), c3(TH["sel_t"])


def use(a, r):
    ctx._o['area'], ctx._o['region'], ctx._o['space_data'] = a, r, a.spaces.active


def draw_in(a, r, mouse=None, tip=False, over=None):
    """Dessine les barres comme Blender le fait pour la région `r` de la vue `a`. Tracés en pixels de la fenêtre."""
    use(a, r)
    for d in ("mouse", "mouse_org", "mouse_t"):
        m._CMD.setdefault(d, {}).clear()
    if mouse is not None:            # (la souris est notée dans la région qu'elle survole, avec l'origine de cette région)
        oa, orr = over if over is not None else (a, m.find_window_region(a, *mouse))
        m._CMD["mouse"][oa.as_pointer()] = (mouse[0] - orr.x, mouse[1] - orr.y)
        m._CMD["mouse_org"][oa.as_pointer()] = (orr.x, orr.y)
        m._CMD["mouse_t"][oa.as_pointer()] = time.monotonic() - (CL.TIP_DELAY + 0.05 if tip else 0.0)
    for _ in range(3):
        del OPS[:]
        _STATE["blend"] = 'NONE'
        CL.cmd_bar_cb(); CL.views_bar_cb()
    out = []
    for o in OPS:
        if o[0] == "text":
            out.append(("text", round(o[1] + r.x, 2), round(o[2] + r.y, 2), o[3], c3(o[5])))
        else:
            out.append((o[0], tuple((round(x + r.x, 2), round(y + r.y, 2)) for x, y in o[1]), c3(o[2])))
    return out


def box(o):
    if o[0] == "text": return (o[1], o[2], o[1], o[2])
    xs = [p[0] for p in o[1]]; ys = [p[1] for p in o[1]]
    return (min(xs), min(ys), max(xs), max(ys))
def low(ops, y=250): return sorted(o for o in ops if box(o)[3] < y)          # la bande des barres, en bas de la fenêtre
def pills(ops): return [box(o) for o in ops if o[0] == "TRIS" and o[2] == BG and box(o)[3] < 250]
def texts(ops): return [o[3] for o in ops if o[0] == "text"]
def hits(p=None): return list(m._VBAR["hit"].get(p or ptr, ()))
def filled(ops, h, col):
    return any(o[0] == "TRIS" and o[2] == col and abs(box(o)[0] - h[0]) < 0.6 and abs(box(o)[2] - h[2]) < 0.6 for o in ops)
mid = lambda h: ((h[0] + h[2]) / 2.0, (h[1] + h[3]) / 2.0)

# ---------------------------------------------------------------- A. une vue : rien ne change
SEC = "une vue"
m.current_view_name = lambda c: "Perspective"
area.regions[:] = [ONE, TOOLS]
area.x, area.y, area.width, area.height = 0, 0, ONE.width, ONE.height
ref = draw_in(area, ONE)
P1 = pills(ref)
h1 = [(h[4], h[5]) for h in hits()]
chk("une vue : cadre des barres = sa région ; le bouton des 4 vues est à gauche des onglets, en quatre cases",
    m.bars_frame(area, ONE) == (0, 0, 1202, 802) and m.quad_bars(area) is None and hits()[0][4] == 'quad' and hits()[0][5] == '4' and _STATE["off"] == (0.0, 0.0), hits()[0])
chk("... aucun titre de vue n'est dessiné", texts(ref).count("Perspective") == 1 and not m._QUAD["hit"].get(ptr))

# ---------------------------------------------------------------- B. 4 vues séparées
SEC = "4 vues"
VIEW = {}
def mk(p, r, view, tools=False):
    sp = NS(type='VIEW_3D', shading=NS(type='SOLID', show_xray=False, xray_alpha=1.0), overlay=NS(show_overlays=True, show_text=False),
            region_3d=rv3d, show_gizmo=True, show_region_toolbar=tools, clip_start=0.01, clip_end=1000, lens=50, local_view=None)
    a = A(p=p, type='VIEW_3D', x=r.x, y=r.y, width=r.width, height=r.height, regions=[r] + ([R(p=p + 500, type='TOOLS', x=r.x, y=r.y, width=44, height=r.height)] if tools else []),
          spaces=NS(active=sp), ui_type='VIEW_3D', redraws=0)
    VIEW[p] = view
    return a
a_bl, a_br, a_tl, a_tr = mk(101, BL, "Front"), mk(102, BR_, "Right"), mk(103, TL, "Top", tools=True), mk(104, TR, "Perspective")
SCRN = NS(areas=[a_bl, a_tl, a_br, a_tr, NS(type='PROPERTIES', x=1300, y=0, width=300, height=802, as_pointer=lambda: 900)], as_pointer=lambda: 5000)
for a in (a_bl, a_br, a_tl, a_tr):
    a.id_data = SCRN
m.current_view_name = lambda c: VIEW[c.area.as_pointer()]
m.quad_reset()
QUADS = (("bas gauche", a_bl, BL), ("bas droite", a_br, BR_), ("haut gauche", a_tl, TL), ("haut droite", a_tr, TR))
qb = m.quad_bars(a_bl)
chk("4 vues 3D en grille : un seul cadre de barres, toute leur emprise ; elles montrent la vue active (au départ la perspective)",
    qb is not None and qb[0] is a_tr and qb[1] == (0, 0, 1202, 802) and len(qb[2]) == 4, qb and qb[1])
drawn = {name: draw_in(a, r) for name, a, r in QUADS}
chk("chaque vue dessine exactement les mêmes barres, au même endroit de l'écran (elle n'en montre que sa part)",
    all(low(drawn[k]) == low(drawn["bas gauche"]) for k in drawn) and len(low(drawn["bas gauche"])) > 20, [len(low(v)) for v in drawn.values()])
P4 = pills(drawn["bas gauche"])
x0, x1 = min(p[0] for p in P4), max(p[2] for p in P4)
chk("... trois pastilles, pas douze, centrées sous les quatre vues : elles passent d'une vue du bas à l'autre (séparation à x = 600)",
    len(P4) == 3 and x0 < 600 < 602 < x1 and abs((x0 + x1) / 2.0 - 601.0) < 1.0 and max(p[3] for p in P4) < 100, (round(x0), round(x1)))
chk("... aucune barre d'outils ne recouvre le bas des 4 vues : les barres sont centrées sur toute la largeur", abs((x0 + x1) / 2.0 - 601.0) < 1.0)
own = a_tr.as_pointer()
H = hits(own)
chk("... le bouton devient un seul rectangle (4 traits)", H[0][4] == 'quad' and H[0][5] == '1'
    and len([o for o in drawn["bas gauche"] if o[0] == "LINES" and len(o[1]) == 8 and box(o)[3] < 250]) == 1, H[0])
tabs = {h[5]: h for h in H if h[4] == 'view'}
chk("... l'onglet allumé est celui de la vue active (Perspective)", filled(drawn["bas droite"], tabs["Perspective"], SEL) and not filled(drawn["bas droite"], tabs["Top"], SEL))
names = {}
for name, a, r in QUADS:
    top = [o for o in drawn[name] if o[0] == "text" and o[2] > r.y + r.height - 40 and r.x <= o[1] <= r.x + 200]
    names[name] = [(o[3], o[4]) for o in top]
chk("chaque vue porte son titre en haut à gauche : Front, Right, Top, Perspective", [n[0][0] for n in names.values()] == ["Front", "Right", "Top", "Perspective"], names)
def lit_title(ops, r):                  # un fond de la couleur de sélection derrière le titre, en haut à gauche de la vue
    return any(o[0] == "TRIS" and o[2] == SEL and box(o)[1] > r.y + r.height - 45 and r.x <= box(o)[0] <= r.x + 200 for o in ops)
chk("... celui de la vue active est allumé (couleur de sélection, comme son onglet), les autres estompés", names["haut droite"][0][1] == SEL_T and lit_title(drawn["haut droite"], TR)
    and all(names[k][0][1] == DIM for k in ("bas gauche", "bas droite", "haut gauche")) and not lit_title(drawn["bas gauche"], BL) and not lit_title(drawn["haut gauche"], TL), names)
qh = m._QUAD["hit"].get(a_tl.as_pointer())
chk("... dans la vue du haut à gauche, il est à droite de la barre d'outils", qh is not None and qh[0][0] >= 44 and [h[4] for h in qh] == ['quadname', 'quadmenu'], qh)
# clics : les positions sont celles de l'écran
modes = [h for h in H if h[4] == 'mode']
right_btn = max(modes, key=lambda h: h[0])
chk("un onglet est dans la vue du bas à gauche, un bouton de mode dans celle du bas à droite", tabs["Top"][2] < 600 and right_btn[0] > 602)
chk("clic dans la vue du bas à gauche sur l'onglet Top : c'est bien lui", m.cmd_hit(a_bl, *mid(tabs["Top"])) == ('view', "Top"))
chk("clic dans la vue du bas à droite sur un bouton de mode : c'est bien lui", m.cmd_hit(a_br, *mid(right_btn)) == ('mode', right_btn[5]), m.cmd_hit(a_br, *mid(right_btn)))
chk("clic au même endroit dans une vue du haut : aucune barre", m.cmd_hit(a_tl, mid(tabs["Top"])[0], mid(tabs["Top"])[1] + 402) is None)
cx, cy = mid(qh[0])
chk("clic sur le titre de la vue du haut à gauche : son nom, puis la flèche de son menu", m.cmd_hit(a_tl, cx + TL.x, cy + TL.y) == ('quadname', None)
    and m.cmd_hit(a_tl, mid(qh[1])[0] + TL.x, mid(qh[1])[1] + TL.y) == ('quadmenu', None))
done = []
m.bars_in_owner = lambda context, owner, fn: (done.append(owner.as_pointer()), fn(NS(area=owner, scene=BC.scene)))[1]
ran = []
m._cmd_click_do = lambda c, kind, val: ran.append((c.area.as_pointer(), kind, val))
use(a_bl, BL)
ok = m.cmd_click_idle(ctx, ev('LEFTMOUSE', 'PRESS', *mid(tabs["Top"])))
chk("clic sur l'onglet Top (dessiné dans la vue du bas à gauche) : c'est la vue active, la perspective, qui passe en Top",
    ok and done == [a_tr.as_pointer()] and ran == [(a_tr.as_pointer(), 'view', "Top")], (done, ran))
m.quad_focus_set(a_bl)
for name, a, r in QUADS:             # (Blender redessine les vues quand la vue active change)
    draw_in(a, r)
use(a_bl, BL)
del done[:], ran[:]
m.cmd_click_idle(ctx, ev('LEFTMOUSE', 'PRESS', *mid(tabs["Top"])))
chk("... quand la vue active est celle où l'on clique : directement dans cette vue", done == [] and ran == [(a_bl.as_pointer(), 'view', "Top")], (done, ran))
quad_clicks = []
m.quad_click = lambda c, kind: (quad_clicks.append((c.area.as_pointer(), kind)), kind in ('quad', 'quadname', 'quadmenu'))[1]
use(a_tl, TL)
m.cmd_click_idle(ctx, ev('LEFTMOUSE', 'PRESS', cx + TL.x, cy + TL.y))
use(a_bl, BL)                        # (le bouton est au bout gauche des barres : dans la vue du bas à gauche)
m.cmd_click_idle(ctx, ev('LEFTMOUSE', 'PRESS', *mid(hits(a_bl.as_pointer())[0])))
chk("clic sur le titre d'une vue ou sur le bouton : il part de la vue où l'on clique (son titre à elle)", quad_clicks[0] == (a_tl.as_pointer(), 'quadname')
    and quad_clicks[-1] == (a_bl.as_pointer(), 'quad') and ran == [(a_bl.as_pointer(), 'view', "Top")], quad_clicks)
# vue active : l'onglet allumé et le titre en clair la suivent
for a in (a_bl, a_br, a_tl, a_tr): a.redraws = 0
m.quad_focus_set(a_tl)
d2 = {name: draw_in(a, r) for name, a, r in QUADS}
H2 = hits(a_tl.as_pointer())
tabs2 = {h[5]: h for h in H2 if h[4] == 'view'}
chk("la vue du haut à gauche devient active : l'onglet Top s'allume dans les quatre dessins, son titre s'allume, celui de la perspective s'éteint",
    all(filled(d2[k], tabs2["Top"], SEL) and not filled(d2[k], tabs2["Perspective"], SEL) for k in d2)
    and [o[4] for o in d2["haut gauche"] if o[0] == "text" and o[3] == "Top" and o[2] > 700] == [SEL_T] and lit_title(d2["haut gauche"], TL)
    and not lit_title(d2["haut droite"], TR), [len(v) for v in d2.values()])
chk("... les barres ne bougent pas (sa barre d'outils ne les décale pas)", pills(d2["bas gauche"]) == P4, (pills(d2["bas gauche"]), P4))
chk("... changer de vue active fait redessiner les quatre vues", all(a.redraws >= 1 for a in (a_bl, a_br, a_tr)), [a.redraws for a in (a_bl, a_br, a_tl, a_tr)])
for a in (a_bl, a_br, a_tl, a_tr): a.redraws = 0
for name, a, r in QUADS:
    draw_in(a, r)
time.sleep(0.12)
draw_in(a_bl, BL)
chk("... une fois toutes à jour, plus aucune ne fait redessiner les autres (pas de boucle de dessin)", [a.redraws for a in (a_br, a_tl, a_tr)] == [0, 0, 0],
    [a.redraws for a in (a_bl, a_br, a_tl, a_tr)])
for a in (a_bl, a_br, a_tl, a_tr): a.redraws = 0
m._CMD["prompt"][a_tl.as_pointer()] = "Polyline: next point"
time.sleep(0.12)
ops = draw_in(a_bl, BL)
chk("la commande en cours dans la vue active est suivie dans la ligne de commande commune", any("Polyline" in t for t in texts(ops)), texts(ops)[:4])
chk("... et les autres vues sont redessinées pour montrer la même chose", all(a.redraws >= 1 for a in (a_br, a_tl, a_tr)), [a.redraws for a in (a_br, a_tl, a_tr)])
m._CMD["prompt"].pop(a_tl.as_pointer(), None)
# survol
H3 = hits(a_tl.as_pointer())
btn = next(h for h in H3 if h[4] == 'mode' and h[5] == 'cmd_type')          # (Quick Type)
ops = draw_in(a_tl, TL, mouse=mid(btn), over=(a_br, BR_))
chk("survol d'un bouton dans la vue du bas à droite : il s'éclaire dans le dessin de toutes les vues", filled(ops, btn, CHIP) and not filled(ops, tabs2["Front"], CHIP))
ops = draw_in(a_br, BR_, mouse=mid(H3[0]), tip=True, over=(a_bl, BL))
chk("survol du bouton des 4 vues : « Back to a single view... »", any(t.startswith("Back to a single view") for t in texts(ops)), texts(ops)[-3:])
ops = draw_in(a_tr, TR, mouse=(TR.x + 30, TR.y + QH - 20), over=(a_tr, TR))
chk("survol du titre d'une vue : « Double-click: this view alone »", "Double-click: this view alone" in texts(ops), texts(ops)[-3:])

# ---------------------------------------------------------------- C. Toggle Quad View de Blender (4 régions, une vue 3D)
SEC = "quad view de Blender"
m.quad_reset()
m.current_view_name = lambda c: "Perspective"
area.regions[:] = [BL, TL, BR_, TR, TOOLS]
area.x, area.y, area.width, area.height = 0, 0, 2 * QW + 2, 2 * QH + 2
chk("4 régions de dessin dans une seule vue 3D : c'est le quad view de Blender, pas les 4 vues séparées", m.quad_native(area) and m.quad_bars(area) is None
    and all(m.bars_frame(area, r) == (0, 0, 1202, 802) for r in (BL, BR_, TL, TR)))
nat = {name: draw_in(area, r) for name, r in (("bas gauche", BL), ("bas droite", BR_), ("haut gauche", TL), ("haut droite", TR))}
chk("chaque région dessine exactement les mêmes barres, au même endroit de l'écran", all(nat[k] == nat["bas gauche"] for k in nat), [len(v) for v in nat.values()])
chk("... au même endroit qu'avec une seule vue (à côté de la barre d'outils, qui court sur toute la hauteur)", pills(nat["bas gauche"]) == P1, (pills(nat["bas gauche"]), P1))
chk("... le bouton reste en quatre cases (il coupera la vue en 4 vues séparées, après avoir quitté le quad view) ; aucun titre de vue",
    hits()[0][5] == '4' and [(h[4], h[5]) for h in hits()] == h1 and not m._QUAD["hit"].get(ptr))
tb = {h[5]: h for h in hits() if h[4] == 'view'}
rb = next(h for h in hits() if h[4] == 'mode' and h[5] == 'cmd_type')          # (Quick Type)
chk("clics : l'onglet Top dans la région du bas à gauche, un bouton de mode dans celle du bas à droite", m.cmd_hit(area, *mid(tb["Top"])) == ('view', "Top")
    and m.cmd_hit(area, *mid(rb)) == ('mode', rb[5]) and m.cmd_hit(area, mid(tb["Top"])[0], mid(tb["Top"])[1] + 402) is None)
ops = draw_in(area, TL, mouse=mid(rb))
chk("survol d'un bouton de la région du bas à droite : il s'éclaire, quelle que soit la région qui dessine", filled(ops, rb, CHIP) and not filled(ops, tb["Top"], CHIP))

# ---------------------------------------------------------------- D. navigation pendant une commande, dans la vue sous la souris
SEC = "navigation"
seen = []
class FakeCtx:
    def __init__(self, a, r): self.area, self.region = a, r
    def temp_override(self, **k):
        seen.append(("override", k["region"].as_pointer()))
        class _O:
            def __enter__(s): return s
            def __exit__(s, *a): return False
        return _O()
go = lambda c: seen.append(("nav", "contexte d'origine" if isinstance(c, FakeCtx) else "vue sous la souris"))
m.nav_in_hovered(FakeCtx(area, TL), ev('MOUSEMOVE', 'NOTHING', 300, 600), go)
chk("glisser dans la région où la commande a démarré : navigation lancée telle quelle", seen == [("nav", "contexte d'origine")], seen)
del seen[:]
m.nav_in_hovered(FakeCtx(area, TL), ev('MOUSEMOVE', 'NOTHING', 900, 200), go)
chk("glisser dans une autre des 4 régions (commande démarrée en haut à gauche, souris en bas à droite) : la navigation est lancée dans la région sous la souris",
    seen == [("override", BR_.as_pointer()), ("nav", "vue sous la souris")], seen)
del seen[:]
m.nav_in_hovered(FakeCtx(area, TL), ev('MOUSEMOVE', 'NOTHING', 5000, 5000), go)
chk("souris hors de la vue : navigation lancée telle quelle", seen == [("nav", "contexte d'origine")], seen)

del seen[:]
class FakeCtx4(FakeCtx):
    screen = SCRN
m.nav_in_hovered(FakeCtx4(a_tl, TL), ev('MOUSEMOVE', 'NOTHING', 900, 200), go)
chk("4 vues séparées, commande démarrée en haut à gauche et passée dans la vue du bas à droite : la navigation est lancée dans cette vue",
    seen == [("override", BR_.as_pointer()), ("nav", "vue sous la souris")], seen)

# ---------------------------------------------------------------- E. une commande de dessin d'une vue à l'autre (4 vues)
SEC = "commande d'une vue à l'autre"
import io, contextlib
m.quad_reset()
m._CMD["op"].clear(); m._CMD["prompt"].clear(); m._CMD["cleared"].clear()
for o_ in list(bpy.data.objects): bpy.data.objects.remove(o_)
m.current_view_name = lambda c: VIEW[c.area.as_pointer()]
use(a_tl, TL)                               # (Blender garde pour contexte la vue où la commande a démarré)
po = make(m.DESSIN_OT_polyligne)
def send(*evs):
    r = None
    with contextlib.redirect_stdout(io.StringIO()):
        for e in evs:
            r = type(po).modal(po, ctx, e)
    return r
def click(x, y): return send(ev('MOUSEMOVE', 'NOTHING', x, y), ev('LEFTMOUSE', 'PRESS', x, y), ev('LEFTMOUSE', 'RELEASE', x, y))
with contextlib.redirect_stdout(io.StringIO()):
    type(po).invoke(po, ctx, ev('NONE', 'NOTHING', 300, 600))
click(300, 600)
tl_, bl_, br_ = a_tl.as_pointer(), a_bl.as_pointer(), a_br.as_pointer()
chk("polyligne lancée dans la vue du haut à gauche, premier point : elle y est, c'est la vue active", po.area is a_tl and len(po.points) == 1
    and m._CMD["op"].get(tl_) is po and m._QUAD["focus"].get(SCRN.as_pointer()) == tl_, (len(po.points), m._QUAD["focus"]))
send(ev('MOUSEMOVE', 'NOTHING', 450, 280))
chk("la souris passe dans la vue du bas à gauche : la commande la suit, son réticule est calculé dans cette vue",
    po.area is a_bl and po.region is BL and po.cur is not None and m._CMD["op"].get(bl_) is po and tl_ not in m._CMD["op"]
    and m._CMD["mouse"].get(bl_) == (450, 280) and tl_ not in m._CMD["mouse"], (po.area.as_pointer(), m._CMD["mouse"]))
chk("... son invite l'a suivie", bool(m._CMD["prompt"].get(bl_)) and tl_ not in m._CMD["prompt"], dict(m._CMD["prompt"]))
ops = draw_in(a_br, BR_)
chk("... la vue active reste celle du haut (onglet Top allumé) mais la ligne de commande montre la polyligne en cours",
    filled(ops, {h[5]: h for h in hits(tl_) if h[4] == 'view'}["Top"], SEL) and any("Polyline" in t for t in texts(ops)), texts(ops)[:3])
click(450, 280)
chk("clic dans la vue du bas à gauche : deuxième point de la même polyligne ; elle devient la vue active", len(po.points) == 2
    and m._QUAD["focus"].get(SCRN.as_pointer()) == bl_ and len([o_ for o_ in bpy.data.objects if o_.type == 'CURVE']) == 0, len(po.points))
click(750, 120)
chk("clic dans la vue du bas à droite : troisième point", len(po.points) == 3 and po.area is a_br and po.region is BR_
    and m._QUAD["focus"].get(SCRN.as_pointer()) == br_, (len(po.points), po.area.as_pointer()))
navs = []
m.nav_in_hovered = lambda c, e, fn: navs.append((e.mouse_x, e.mouse_y))
send(ev('RIGHTMOUSE', 'PRESS', 900, 200), ev('MOUSEMOVE', 'NOTHING', 960, 240))
chk("glisser avec le bouton droit dans cette vue : la navigation démarre (dans la vue sous la souris), la commande continue", navs == [(960, 240)] and len(po.points) == 3, navs)
send(ev('RIGHTMOUSE', 'RELEASE', 960, 240))
opened = []
m.bars_in_owner = lambda context, owner, fn: (opened.append(owner.as_pointer()), fn(NS(area=owner, scene=BC.scene)))[1]
r = send(ev('RET', 'PRESS', 900, 200))
curves = [o_ for o_ in bpy.data.objects if o_.type == 'CURVE']
chk("Entrée : une seule polyligne de 3 points, dessinée à travers trois vues", len(curves) == 1 and len(curves[0].data.splines[0].points) + len(curves[0].data.splines[0].bezier_points) == 3,
    (len(curves), r))
try: type(po).cleanup(po, ctx)
except Exception: pass
chk("... plus aucune commande en cours dans les 4 vues", not any(m._CMD["op"].get(p_) for p_ in (tl_, bl_, br_, a_tr.as_pointer())), dict(m._CMD["op"]))

# ---------------------------------------------------------------- F. le vrai Blender, pour ce qui se vérifie sans fenêtre
SEC = "blender"
chk("screen.region_quadview existe (pour quitter le Toggle Quad View avant de couper la vue)", bpy.ops.screen.region_quadview.get_rna_type() is not None)
import gpu as _g
chk("gpu.matrix.push_pop et gpu.matrix.translate existent (décalage du dessin des barres)", hasattr(_g.matrix, "push_pop") and hasattr(_g.matrix, "translate"))
chk("Area.id_data donne l'écran de la zone", bpy.types.Area.bl_rna is not None and hasattr(bpy.context.screen.areas[0], "id_data") and bpy.context.screen.areas[0].id_data == bpy.context.screen)
summary()
