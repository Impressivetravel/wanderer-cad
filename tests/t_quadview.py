# 4 vues comme dans Rhino : la vue 3D coupée en quatre vues 3D séparées (Top / Perspective / Front / Right), chacune avec
# son affichage ; retour à une vue par le bouton ou par un double-clic sur le titre d'une vue ; vue active.
# L'écran de Blender n'existe pas sans fenêtre : la coupe et la fermeture sont essayées sur un écran simulé qui se
# comporte comme lui (une zone neuve n'a pas de taille avant le rafraîchissement, une zone fermée est prise par la
# voisine au bord le plus proche du sien). Le dessin des barres et des titres est dans t_quadbars.py.
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE, 'harness.py')).read())
exec(open(_os.path.join(_HERE, 'prec_lib.py')).read())
_RENDER_BARS_LIB = True
exec(open(_os.path.join(_HERE, 'render_bars.py')).read())
import time
BC = bpy.context
SEC = "?"
def chk(name, ok, meas=""): rec(SEC, name, ok, meas)
ptr = area.as_pointer()


# ---------------------------------------------------------------- écran simulé
class FArea:
    def __init__(self, p, rect, kind='VIEW_3D', sized=True):
        self._p, self.true, self.type = p, tuple(rect), kind
        self.x, self.y, self.width, self.height = rect if sized else (0, 0, 0, 0)
        self.spaces = NS(active=NS(show_region_header=True, show_region_tool_header=True, show_region_toolbar=True, show_region_ui=True,
                                   overlay=NS(show_text=True), shading=NS(type='SOLID')))
        self.view = "Perspective"
        self.native = False              # dans le Toggle Quad View de Blender : 4 régions de dessin dans la même vue 3D
        self.id_data = None              # son écran
        self.redraws = 0
        self.tools = 0                   # largeur de la barre d'outils (0 : pas de région TOOLS)
    @property
    def regions(self):
        rs = [NS(type='WINDOW', x=self.x, y=self.y, width=self.width, height=self.height) for _ in range(4 if self.native else 1)]
        if self.tools:
            rs.append(NS(type='TOOLS', x=self.x, y=self.y, width=self.tools, height=self.height))
        return rs
    def as_pointer(self): return self._p
    def tag_redraw(self): self.redraws += 1
    def header_text_set(self, *a): pass


class FScreen:
    def __init__(self, areas):
        self.areas = list(areas)
        for a in self.areas: a.id_data = self
    def as_pointer(self): return 9000
    def refresh(self):
        for a in self.areas:
            a.x, a.y, a.width, a.height = a.true


class FWin:
    def __init__(self, screen): self.screen = screen
    def as_pointer(self): return 8000


LOG = []
NEXT = [100]
FLIP = [False]            # côté où Blender pose la nouvelle zone (la commande ne doit pas en dépendre)
REFUSE = [0]              # numéro de la coupe que Blender refuse (0 : aucune)
NSPLIT = [0]


def f_split(win, screen, a, direction, factor=0.5):
    NSPLIT[0] += 1
    if a.width <= 0 or a.height <= 0:
        LOG.append("coupe d'une zone sans taille")
        return None
    if REFUSE[0] == NSPLIT[0]:
        return None
    x, y, w, h = a.true
    if direction == 'VERTICAL':
        w0 = (w - 2) // 2 if factor == 0.5 else int(round(w * factor))
        r0, r1 = (x, y, w0, h), (x + w0 + 2, y, w - w0 - 2, h)
    else:
        h0 = (h - 2) // 2
        r0, r1 = (x, y, w, h0), (x, y + h0 + 2, w, h - h0 - 2)
    keep, new = (r0, r1) if FLIP[0] else (r1, r0)
    a.true = keep
    NEXT[0] += 1
    n = FArea(NEXT[0], new, sized=False)
    n.spaces.active = NS(**{k: v for k, v in vars(a.spaces.active).items() if k not in ('overlay', 'shading')},
                         overlay=NS(show_text=a.spaces.active.overlay.show_text), shading=NS(type=a.spaces.active.shading.type))
    n.view = a.view
    n.tools = a.tools
    n.id_data = screen
    screen.areas.append(n)
    return n.as_pointer()


def f_close(win, screen, a):
    """Comme Blender : la zone fermée est prise par la voisine dont le bord commun a la longueur la plus proche du sien
    (à égalité, la première de la liste). Blender compare les tailles qu'il connaît : celles du dernier rafraîchissement."""
    if a.width <= 0 or a.height <= 0:
        LOG.append("fermeture d'une zone sans taille")
        return False
    x, y, w, h = a.true
    best, score = None, 0.0
    for nb in screen.areas:
        if nb is a:
            continue
        nx, ny, nw, nh = nb.true
        if abs(nx + nw + 2 - x) <= 3 or abs(x + w + 2 - nx) <= 3:            # voisine de gauche ou de droite
            shared, la, ln = min(y + h, ny + nh) - max(y, ny), a.height, nb.height
        elif abs(ny + nh + 2 - y) <= 3 or abs(y + h + 2 - ny) <= 3:          # voisine du dessous ou du dessus
            shared, la, ln = min(x + w, nx + nw) - max(x, nx), a.width, nb.width
        else:
            continue
        if shared <= 0 or ln <= 0:
            continue
        ratio = min(la, ln) / float(max(la, ln))
        if ratio > score:
            best, score = nb, ratio
    if best is None:
        return False
    nx, ny, nw, nh = best.true
    if best.type != 'VIEW_3D':
        LOG.append(f"zone {a.as_pointer()} prise par un autre éditeur ({best.type})")
    if not ((nx == x and nw == w) or (ny == y and nh == h)):
        LOG.append(f"fermeture entre zones non alignées ({a.as_pointer()} dans {best.as_pointer()})")
    x0, y0 = min(x, nx), min(y, ny)
    best.true = (x0, y0, max(x + w, nx + nw) - x0, max(y + h, ny + nh) - y0)
    screen.areas.remove(a)
    return True


FULL = (2, 100, 1574, 954)


def fresh(extra=True):
    """Écran d'essai : une vue 3D (et, comme dans Blender, d'autres éditeurs autour)."""
    del LOG[:]
    NSPLIT[0], REFUSE[0] = 0, 0
    a = FArea(1, FULL)
    others = [FArea(2, (1579, 23, 339, 839), 'PROPERTIES'), FArea(3, (1579, 865, 339, 189), 'OUTLINER'), FArea(4, (2, 23, 1574, 74), 'DOPESHEET_EDITOR')]
    sc = FScreen(([others[0]] if extra else []) + [a] + (others[1:] if extra else []))
    return FWin(sc), sc, a


WIN, SCR, A0 = fresh()
m._window_by_ptr = lambda p: WIN if p == 8000 else None
m._area_split = f_split
m._area_close = f_close
m._area_set_view = lambda win, screen, a, name: setattr(a, "view", name)
m._area_view_name = lambda win, screen, a: a.view
m._redraw_all = lambda s: None
def f_native_off(win, screen, a): a.native = False
m._quad_native_off = f_native_off
m._area_call = lambda win, screen, a, fn: fn()
_QUAD_OF = m.quad_of                  # (la partie « menu » le remplace ; la partie « colonne » le reprend)


def v3(screen=None): return [a for a in (screen or SCR).areas if a.type == 'VIEW_3D']
def by_pos():
    m._QUAD["cache"] = (None, {})
    pos, grid = m.quad_of(SCR, v3()[0].as_pointer())
    return {p: next(a for a in SCR.areas if a.as_pointer() == q) for p, q in (grid or {}).items()}


def drive(job, every=1, limit=400):
    """Fait avancer une commande pas à pas ; l'écran est rafraîchi tous les `every` pas (0 : jamais)."""
    n = 0
    while n < limit:
        n += 1
        if job.step() is None:
            return n
        if every and n % every == 0:
            SCR.refresh()
    return n


def enter(every=1):
    global WIN, SCR, A0
    WIN, SCR, A0 = fresh()
    m.quad_reset()
    job = m.QuadJob('enter', WIN, SCR, A0.as_pointer())
    n = drive(job, every)
    SCR.refresh()
    return job, n


# ---------------------------------------------------------------- A. reconnaître les 4 vues
SEC = "grille"
R = [(1, 2, 100, 786, 476), (2, 790, 100, 786, 476), (3, 2, 578, 786, 476), (4, 790, 578, 786, 476)]
chk("4 vues 3D en grille 2 x 2 (2 px entre elles) : haut gauche, haut droite, bas gauche, bas droite", m.quad_grid(R) == {'BL': 1, 'BR': 2, 'TL': 3, 'TR': 4}, m.quad_grid(R))
chk("... même quand la croix n'est pas au milieu (bords déplacés à la souris)", m.quad_grid([(1, 0, 0, 300, 200), (2, 302, 0, 1298, 200), (3, 0, 202, 300, 798), (4, 302, 202, 1298, 798)]) == {'BL': 1, 'BR': 2, 'TL': 3, 'TR': 4})
chk("3 vues (une colonne entière et deux moitiés) : pas une grille", m.quad_grid([(1, 0, 0, 800, 1000), (2, 802, 0, 798, 499), (3, 802, 501, 798, 499), (4, 0, 0, 0, 0)]) is None)
chk("4 vues côte à côte : pas une grille", m.quad_grid([(i, i * 400, 0, 398, 900) for i in range(4)]) is None)
chk("4 vues avec un trou (l'une plus petite que son quart) : pas une grille", m.quad_grid(R[:3] + [(4, 790, 578, 400, 476)]) is None)
chk("une zone dont la taille n'est pas encore connue : pas une grille", m.quad_grid(R[:3] + [(4, 0, 0, 0, 0)]) is None)
g = m.quad_groups(R + [(5, 2000, 100, 500, 954)])
chk("une cinquième vue 3D à côté : les 4 de la grille sont reconnues, pas elle", sorted(g) == [1, 2, 3, 4] and g[3][0] == 'TL' and g[2][0] == 'BR', sorted(g))
chk("moins de 4 vues : rien", m.quad_groups(R[:3]) == {})
orig = {"show_region_header": True, "show_region_tool_header": True, "show_region_toolbar": True, "show_region_ui": True, "show_text": True}
ui = {p: m.quad_ui_for(p, orig) for p in ('TL', 'TR', 'BL', 'BR')}
chk("panneaux des 4 vues : en-tête et barre d'outils en haut à gauche seulement, panneau latéral en haut à droite seulement",
    [p for p in ui if ui[p]["show_region_header"]] == ['TL'] and [p for p in ui if ui[p]["show_region_toolbar"]] == ['TL'] and [p for p in ui if ui[p]["show_region_ui"]] == ['TR'], ui)
chk("... le texte de Blender (en haut à gauche) laisse partout la place au titre de la vue", not any(ui[p]["show_text"] for p in ui))
chk("... un panneau fermé avant les 4 vues le reste", not m.quad_ui_for('TR', dict(orig, show_region_ui=False))["show_region_ui"] and not m.quad_ui_for('TL', dict(orig, show_region_toolbar=False))["show_region_toolbar"])
grid = {'TL': 3, 'TR': 4, 'BL': 1, 'BR': 2}
chk("ordre de fermeture pour garder la vue du haut à gauche : d'abord sa diagonale (bas droite)", m.quad_diag_order(grid, 3, {1: 10, 2: 10, 3: 10, 4: 10}) == 2)
chk("... puis la moitié restante (la plus petite des deux), puis la dernière", m.quad_diag_order(grid, 3, {1: 10, 3: 10, 4: 20}) == 1 and m.quad_diag_order(grid, 3, {3: 20, 4: 20}) == 4
    and m.quad_diag_order(grid, 3, {3: 40}) is None)

# ---------------------------------------------------------------- B. passer aux 4 vues
SEC = "4 vues"
job, n = enter()
P = by_pos()
chk("la vue 3D est coupée en 4 vues 3D qui occupent exactement sa place (les autres éditeurs ne bougent pas)", len(v3()) == 4 and len(P) == 4 and len(SCR.areas) == 7 and not job.error
    and min(a.true[0] for a in v3()) == 2 and min(a.true[1] for a in v3()) == 100 and max(a.true[0] + a.true[2] for a in v3()) == 1576 and max(a.true[1] + a.true[3] for a in v3()) == 1054,
    (len(v3()), job.error, [a.true for a in v3()]))
chk("disposition de Rhino : Top en haut à gauche, Perspective en haut à droite, Front en bas à gauche, Right en bas à droite",
    {p: a.view for p, a in P.items()} == {'TL': "Top", 'TR': "Perspective", 'BL': "Front", 'BR': "Right"}, {p: a.view for p, a in P.items()})
flags = {p: (a.spaces.active.show_region_header, a.spaces.active.show_region_toolbar, a.spaces.active.show_region_ui, a.spaces.active.overlay.show_text) for p, a in P.items()}
chk("en-tête et barre d'outils en haut à gauche, panneau latéral en haut à droite, rien ailleurs ; texte de Blender masqué",
    flags == {'TL': (True, True, False, False), 'TR': (False, False, True, False), 'BL': (False, False, False, False), 'BR': (False, False, False, False)}, flags)
chk("aucune zone n'a été coupée ou fermée avant que l'écran connaisse sa taille", not LOG, LOG)
qb = m.quad_bars(P['BL'])
chk("barres du bas : un seul cadre pour les quatre vues (toute leur emprise), celles de la vue active — au départ la perspective",
    qb is not None and qb[0] is P['TR'] and qb[1] == FULL and sorted(qb[2]) == sorted(a.as_pointer() for a in P.values())
    and all(m.quad_bars(a)[:2] == qb[:2] for a in P.values()) and m.quad_bars(SCR.areas[0]) is None, qb and (qb[0].view, qb[1]))
job3, n3 = enter(every=3)
chk("écran rafraîchi moins souvent : la commande attend la taille des nouvelles zones, le résultat est le même", len(by_pos()) == 4 and n3 > n and not LOG and not job3.error, (n, n3, LOG))
FLIP[0] = True
job, _n = enter()
P = by_pos()
chk("nouvelle zone posée de l'autre côté par Blender : les vues sont attribuées d'après leur place, pas d'après leur ordre",
    len(P) == 4 and {p: a.view for p, a in P.items()} == {'TL': "Top", 'TR': "Perspective", 'BL': "Front", 'BR': "Right"}
    and [p for p in P if P[p].spaces.active.show_region_header] == ['TL'], {p: a.view for p, a in P.items()})
FLIP[0] = False
WIN, SCR, A0 = fresh()
m.quad_reset()
REFUSE[0] = 3
job = m.QuadJob('enter', WIN, SCR, 1)
drive(job)
SCR.refresh()
chk("Blender refuse la troisième coupe : tout est refermé, on retrouve la vue d'origine, ses panneaux et sa place",
    len(v3()) == 1 and v3()[0] is A0 and A0.true == FULL and A0.spaces.active.show_region_header and A0.spaces.active.overlay.show_text and job.error == "split"
    and "fermeture d'une zone sans taille" not in LOG, (len(v3()), A0.true, job.error, LOG))
WIN, SCR, A0 = fresh()
m.quad_reset()
job = m.QuadJob('enter', WIN, SCR, 1)
for _ in range(20):
    job.step()                                   # (l'écran ne se rafraîchit jamais)
job.t0 -= 10.0
for _ in range(20):
    if job.step() is None:
        break
job.t0 -= 10.0
r = job.step()
chk("écran jamais rafraîchi : la commande renonce au bout de 4 s, sans jamais toucher une zone dont la taille est inconnue", r is None and job.error == "timeout" and not LOG, (r, job.error, LOG))

WIN, SCR, A0 = fresh()
m.quad_reset()
A0.native = True
job = m.QuadJob('enter', WIN, SCR, 1)
n = drive(job)
SCR.refresh()
chk("vue 3D dans le Toggle Quad View de Blender : il est d'abord quitté, puis la vue est coupée en 4 vues séparées", len(by_pos()) == 4 and not A0.native and not job.error and not LOG, (len(v3()), job.error))

# ---------------------------------------------------------------- C. revenir à une vue
SEC = "une vue"
for pos in ('TL', 'TR', 'BL', 'BR'):
    enter()
    P = by_pos()
    keep = P[pos]
    P['TR'].spaces.active.shading.type = 'MATERIAL'
    P['TL'].spaces.active.shading.type = 'WIREFRAME'
    done = []
    job = m.QuadJob('exit', WIN, SCR, P['BL'].as_pointer(), keep=keep.as_pointer(), then=lambda: done.append(1))
    n = drive(job)
    sp = keep.spaces.active
    chk(f"garder la vue {pos} ({keep.view}) : les trois autres sont fermées, elle reprend toute la place avec sa vue et son affichage",
        v3() == [keep] and keep.true == FULL and keep.view == m.QUAD_VIEWS[pos] and not job.error and len(SCR.areas) == 4, (len(v3()), keep.true, job.error))
    chk("... chaque fermeture se fait entre deux zones alignées (jamais de zone en L)", not LOG, LOG)
    chk("... elle retrouve l'en-tête, la barre d'outils, le panneau latéral et le texte de Blender ; la suite demandée est lancée",
        sp.show_region_header and sp.show_region_toolbar and sp.show_region_ui and sp.overlay.show_text and done == [1], (vars(sp), done))
enter()
P = by_pos()
job = m.QuadJob('exit', WIN, SCR, P['BL'].as_pointer(), keep=P['BR'].as_pointer())
n3 = drive(job, every=4)
chk("écran rafraîchi moins souvent : la fermeture attend que la zone agrandie ait sa taille", v3() == [P['BR']] and P['BR'].true == FULL and not LOG and n3 > 8, (n3, LOG))
sptr = SCR.as_pointer()
enter()
P = by_pos()
P['TR'].spaces.active.shading.type = 'MATERIAL'
P['TL'].spaces.active.shading.type = 'WIREFRAME'
drive(m.QuadJob('exit', WIN, SCR, P['BL'].as_pointer(), keep=P['TR'].as_pointer()))
chk("chaque quart se souvient de son affichage", m._QUAD["shade"].get((sptr, 'TL')) == 'WIREFRAME' and m._QUAD["shade"].get((sptr, 'TR')) == 'MATERIAL' and m._QUAD["shade"].get((sptr, 'BL')) == 'SOLID')
keep = v3()[0]
job = m.QuadJob('enter', WIN, SCR, keep.as_pointer())
drive(job)
SCR.refresh()
P = by_pos()
chk("... et le retrouve quand on repasse aux 4 vues (Top en filaire, Perspective en textures, Front et Right en ombré)", len(P) == 4
    and {p: a.spaces.active.shading.type for p, a in P.items()} == {'TL': 'WIREFRAME', 'TR': 'MATERIAL', 'BL': 'SOLID', 'BR': 'SOLID'}, {p: a.spaces.active.shading.type for p, a in P.items()})
job = m.QuadJob('exit', WIN, SCR, P['BL'].as_pointer(), keep=999999)
drive(job)
chk("vue à garder inconnue : c'est la perspective (haut droite) qui reste", len(v3()) == 1 and v3()[0].view == "Perspective", [a.view for a in v3()])

# ---------------------------------------------------------------- D. la commande
SEC = "commande"
enter()
P = by_pos()
fctx = lambda a: NS(window=WIN, screen=SCR, area=a, scene=BC.scene)
sptr = SCR.as_pointer()
chk("vue active au départ : la perspective (haut droite)", m.quad_focus(SCR, {p: a.as_pointer() for p, a in P.items()}) == P['TR'].as_pointer())
mid_of = lambda a: (a.x + a.width // 2, a.y + a.height // 2)
r1 = m.cmd_click_idle(fctx(P['BL']), ev('LEFTMOUSE', 'PRESS', *mid_of(P['BL'])))
chk("un clic dans une vue (sélection, point d'une commande) : elle devient la vue active, les barres la montrent",
    r1 is False and m._QUAD["focus"][sptr] == P['BL'].as_pointer() and m.quad_bars(P['TR'])[0] is P['BL'], r1)
redrawn = []
m._redraw_all = lambda s: redrawn.append(s)
chk("... les 4 vues sont redessinées (titre en clair, onglet allumé) ; recliquer dans la même vue ne redessine rien",
    m.quad_focus_set(P['TL']) is True and redrawn == [SCR] and m.quad_focus_set(P['TL']) is False and redrawn == [SCR], len(redrawn))
m._redraw_all = lambda s: None
chk("survoler une vue ne la rend pas active (on en traverse toujours une pour atteindre les barres)", not hasattr(m, "quad_focus_hover"))
c0 = m.quad_name_click(fctx(P['BR']), 10.0)
chk("un clic sur le titre d'une vue la rend active, sans toucher à la sélection", c0 is False and m.quad_bars(P['TL'])[0] is P['BR'])
m._QUAD["click"] = (None, 0.0)
m.quad_focus_set(P['TL'])
m._CMD["input"] = {"area": P['BR'].as_pointer(), "text": "li"}
chk("une commande que l'on tape dans une vue : c'est elle que les barres montrent, le temps de la saisie", m.quad_bars(P['TL'])[0] is P['BR'])
m._CMD["input"] = None
chk("hors des 4 vues, rien ne change de vue active", m.quad_focus_set(SCR.areas[0]) is False and m._QUAD["focus"][sptr] == P['TL'].as_pointer())

# une commande de dessin suit la souris d'une vue à l'autre
class FOp:
    def __init__(self, a):
        self.area, self.region, self.snap_screen = a, a.regions[0], (5, 5)
m._CMD["op"].clear(); m._CMD["prompt"].clear()
fop = FOp(P['TL'])
tl, bl, br, tr = (P[k].as_pointer() for k in ('TL', 'BL', 'BR', 'TR'))
m._CMD["op"][tl] = fop
m.set_prompt(P['TL'], "Polyline: next point")
home = NS(area=P['TL'])
for a in SCR.areas: a.redraws = 0
m.quad_follow(fop, home, ev('MOUSEMOVE', 'NOTHING', *mid_of(P['TL'])))
chk("commande en cours dans la vue du haut à gauche, la souris y bouge : elle y reste", fop.area is P['TL'] and m._CMD["op"].get(tl) is fop)
m.quad_follow(fop, home, ev('MOUSEMOVE', 'NOTHING', *mid_of(P['BL'])))
chk("la souris passe dans la vue du bas à gauche : la commande la suit (comme dans Rhino)", fop.area is P['BL'] and m._CMD["op"].get(bl) is fop and tl not in m._CMD["op"]
    and fop.snap_screen is None and (fop.region.x, fop.region.y) == (P['BL'].x, P['BL'].y), fop.area.view)
chk("... son invite la suit ; les deux vues sont redessinées", m._CMD["prompt"].get(bl) == "Polyline: next point" and tl not in m._CMD["prompt"]
    and P['TL'].redraws >= 1 and P['BL'].redraws >= 1, dict(m._CMD["prompt"]))
chk("... la vue active ne change pas tant qu'on n'y clique pas ; la ligne de commande montre quand même la commande en cours",
    m._QUAD["focus"][sptr] == tl and m.quad_bars(P['BR'])[0] is P['TL'] and m.bars_cmd_ptr(tl) == bl and m.bars_cmd_ptr(bl) == bl, m.bars_cmd_ptr(tl))
m.quad_follow(fop, home, ev('LEFTMOUSE', 'PRESS', *mid_of(P['BL'])))
chk("un clic de la commande dans cette vue : elle devient la vue active", m._QUAD["focus"][sptr] == bl and fop.area is P['BL'])
m.quad_follow(fop, home, ev('LEFTMOUSE', 'PRESS', *mid_of(P['TR'])))
chk("un clic dans une autre vue sans mouvement de souris reçu entre-temps : la commande y passe d'abord, puis elle devient active",
    fop.area is P['TR'] and m._CMD["op"].get(tr) is fop and m._QUAD["focus"][sptr] == tr)
m.quad_follow(fop, home, ev('A', 'PRESS', *mid_of(P['BR'])))
m.quad_follow(fop, home, ev('MIDDLEMOUSE', 'PRESS', *mid_of(P['BR'])))
chk("une touche ou le bouton du milieu avec la souris dans une autre vue : la commande ne bouge pas (la navigation se fait là où est la souris)", fop.area is P['TR'])
other = FOp(P['BR'])
m._CMD["op"][br] = other
m.quad_follow(fop, home, ev('MOUSEMOVE', 'NOTHING', *mid_of(P['BR'])))
chk("une autre commande est déjà en cours dans la vue où passe la souris : chacune reste dans la sienne", fop.area is P['TR'] and m._CMD["op"].get(br) is other)
del m._CMD["op"][br]
seam = (P['TL'].x + P['TL'].width + 1, P['TL'].y + 20)
m.quad_follow(fop, home, ev('MOUSEMOVE', 'NOTHING', *seam))
chk("souris sur la séparation entre deux vues, ou hors des 4 vues : la commande reste où elle est", fop.area is P['TR'])
m.quad_follow(fop, home, ev('MOUSEMOVE', 'NOTHING', 5000, 5000))
chk("... idem hors de la fenêtre", fop.area is P['TR'])
gone = P['TR']
SCR.areas.remove(gone)                      # (la vue où la commande se trouve est fermée : Blender garde la vue de départ)
n_red = gone.redraws
m.quad_follow(fop, home, ev('TIMER', 'NOTHING', 0, 0))
chk("la vue où se trouve la commande est fermée : la commande revient dans la vue où elle a démarré, sans toucher à la vue fermée",
    fop.area is P['TL'] and m._CMD["op"].get(tl) is fop and tr not in m._CMD["op"] and m._CMD["prompt"].get(tl) == "Polyline: next point"
    and tr not in m._CMD["prompt"] and gone.redraws == n_red, (fop.area.view, dict(m._CMD["prompt"])))
SCR.areas.append(gone)
lone = FArea(77, (0, 0, 500, 500)); FScreen([lone, FArea(78, (502, 0, 500, 500))])
fop2 = FOp(lone)
m.quad_follow(fop2, NS(area=lone), ev('MOUSEMOVE', 'NOTHING', 700, 200))
chk("deux vues 3D côte à côte (pas les 4 vues) : rien ne change, la commande reste dans sa vue", fop2.area is lone)
m._CMD["op"].clear(); m._CMD["prompt"].clear(); m._CMD["cleared"].clear()
m._QUAD["focus"][sptr] = P['BR'].as_pointer()
chk("bouton en 4 vues : la vue qui reste est la vue active (ici Right)", m.quad_home(fctx(P['BL'])) == P['BR'].as_pointer())
m._QUAD["focus"][sptr] = 424242
chk("... vue active inconnue : la perspective", m.quad_home(fctx(P['BL'])) == P['TR'].as_pointer())
op = make(m.DESSIN_OT_quad_view)
r = type(op).execute(op, fctx(P['TL']))
chk("commande 4 Views depuis les 4 vues : le retour à une vue est lancé (rien n'est fait pendant le clic lui-même)", r == {'FINISHED'} and m.quad_busy() and len(v3()) == 4, r)
r2 = type(op).execute(op, fctx(P['TL']))
chk("... la relancer pendant ce temps ne fait rien", r2 == {'CANCELLED'}, r2)
n = 0
while m._quad_tick() is not None and n < 100:
    n += 1
    SCR.refresh()
chk("... le minuteur fait le reste : une seule vue, la perspective", not m.quad_busy() and len(v3()) == 1 and v3()[0].view == "Perspective", [a.view for a in v3()])
op = make(m.DESSIN_OT_quad_view); op.mode = 'SINGLE'
r = type(op).execute(op, fctx(v3()[0]))
chk("Single View quand il n'y a qu'une vue : rien", r == {'CANCELLED'} and not m.quad_busy(), r)
op = make(m.DESSIN_OT_quad_view)
r = type(op).execute(op, fctx(v3()[0]))
while m._quad_tick() is not None:
    SCR.refresh()
SCR.refresh()
chk("commande 4 Views depuis une vue : les 4 vues", r == {'FINISHED'} and len(by_pos()) == 4, r)
op = make(m.DESSIN_OT_quad_view); op.mode, op.here = 'SINGLE', True
P = by_pos()
r = type(op).execute(op, fctx(P['BL']))
while m._quad_tick() is not None:
    SCR.refresh()
chk("Maximize this View (ou double-clic sur son titre) : c'est la vue sous la souris qui reste (Front)", r == {'FINISHED'} and [a.view for a in v3()] == ["Front"], [a.view for a in v3()])
opened = []
enter()
P = by_pos()
r = m.quad_leave_then(fctx(P['BL']), lambda: opened.append(1))
while m._quad_tick() is not None:
    SCR.refresh()
chk("ouvrir une mise en page depuis les 4 vues : elles se referment d'abord, la mise en page s'ouvre dans la vue qui reste", r is True and opened == [1] and len(v3()) == 1, (r, opened, len(v3())))
chk("... depuis une seule vue : rien à refermer", m.quad_leave_then(fctx(v3()[0]), lambda: opened.append(2)) is False and opened == [1])
t = 100.0
c1 = m.quad_name_click(fctx(v3()[0]), t)
c2 = m.quad_name_click(fctx(v3()[0]), t + 1.0)
c3 = m.quad_name_click(fctx(v3()[0]), t + 1.3)
chk("clic sur le titre d'une vue : un seul clic ne fait rien, deux clics à moins de 0,45 s font un double-clic", (c1, c2, c3) == (False, False, True), (c1, c2, c3))
if bpy.app.timers.is_registered(m._quad_tick):
    bpy.app.timers.unregister(m._quad_tick)

# ---------------------------------------------------------------- E. menu d'une vue, commandes
SEC = "menu"
GRID = {'TL': 11, 'TR': 12, 'BL': ptr, 'BR': 14}
m.quad_of = lambda screen, p: ('BL', GRID) if p == ptr else (None, None)
lvl3 = m.tabs_for_level([('quad', '4', "", False), ('view', "Top", "Top", False), ('view', "Front", "Front", True), ('viewmenu', '+', '+', False)], 3)
chk("vue très étroite (il ne reste que la vue active et « + ») : le bouton s'efface", [t[0] for t in lvl3] == ['view', 'viewmenu'] and lvl3[0][1] == "Front", lvl3)


class FakeLayout:
    def __getattr__(self, n):
        def f(*a, **k):
            return FakeLayout()
        return f

    def __setattr__(self, n, v):
        pass


items = []


class MenuLayout(FakeLayout):
    def operator(self, idname, **k):
        items.append((idname, k.get("text")))
        return NS()


m.DESSIN_MT_quad_view.draw(NS(layout=MenuLayout()), ctx)
chk("menu d'une vue : Wireframe, Shaded, Textures, Rendered, puis Maximize this View, puis les vues", [t for i, t in items if i == "dessin.quad_display"] == ["Wireframe", "Shaded", "Textures", "Rendered"]
    and ("dessin.quad_view", "Maximize this View") in items and [t for i, t in items if i == "dessin.view_restore"][:4] == ["Top", "Front", "Perspective", "Right"], items)
space.shading.type = 'SOLID'
op = make(m.DESSIN_OT_quad_display); op.display = 'WIREFRAME'
r = type(op).execute(op, ctx)
chk("Wireframe dans ce menu : l'affichage de cette vue seule change", r == {'FINISHED'} and space.shading.type == 'WIREFRAME', space.shading.type)
space.shading.type = 'SOLID'
keys = {a for _l, al, _x, _d, _f in m.CMD_ACTIONS for a in al.split()}
chk("commandes à taper : 4views / quadview, maximizeview", {"4views", "quadview", "maximizeview"} <= keys)

# ---------------------------------------------------------------- F. le vrai Blender, pour ce qui se vérifie sans fenêtre
SEC = "blender"
rna = bpy.ops.screen.area_split.get_rna_type()
chk("screen.area_split existe, avec direction (VERTICAL / HORIZONTAL) et factor", {"direction", "factor"} <= {p.identifier for p in rna.properties}
    and {'VERTICAL', 'HORIZONTAL'} <= {i.identifier for i in rna.properties["direction"].enum_items})
chk("screen.area_close existe", bpy.ops.screen.area_close.get_rna_type() is not None)
sp = bpy.types.SpaceView3D.bl_rna.properties
chk("les réglages de panneaux d'une vue 3D existent sous ces noms", all(k in sp for k in m.QUAD_UI_KEYS) and "show_text" in bpy.types.View3DOverlay.bl_rna.properties)
chk("les 4 affichages existent sous ces noms", [k for k, _l, _t in m.QUAD_DISPLAY_ITEMS] == [i.identifier for i in bpy.types.View3DShading.bl_rna.properties["type"].enum_items])
chk("colonne : les réglages qu'elle change existent sous ces noms (poignées, superpositions, vue)", "show_gizmo" in sp and "show_overlays" in bpy.types.View3DOverlay.bl_rna.properties
    and {"view_location", "view_distance", "view_perspective"} <= set(bpy.types.RegionView3D.bl_rna.properties.keys()))
chk("screen.area_move existe, avec x, y et delta (recaler la colonne de la barre d'outils)", {"x", "y", "delta"} <= {p.identifier for p in bpy.ops.screen.area_move.get_rna_type().properties})
# ---------------------------------------------------------------- G. colonne de la barre d'outils
SEC = "colonne"
m.quad_of = _QUAD_OF
def enter_col(tools=60, flip=False, refuse=0, toolbar=True):
    global WIN, SCR, A0
    WIN, SCR, A0 = fresh()
    m.quad_reset()
    A0.tools = tools
    A0.spaces.active.show_region_toolbar = toolbar
    FLIP[0], REFUSE[0] = flip, refuse
    job = m.QuadJob('enter', WIN, SCR, A0.as_pointer())
    drive(job)
    SCR.refresh()
    FLIP[0] = False
    return job
def column():
    P = {}
    for a in v3():                       # (la première vue 3D de l'écran peut être la colonne)
        m._QUAD["cache"] = (None, {})
        pos, grid = m.quad_of(SCR, a.as_pointer())
        if grid:
            P = {p: next(x for x in SCR.areas if x.as_pointer() == q) for p, q in grid.items()}
            break
    g = {p: a.as_pointer() for p, a in P.items()}
    return (m.quad_column_of(SCR, g) if g else None), P
for flip in (False, True):
    job = enter_col(flip=flip)
    col, P = column()
    sp = col.spaces.active if col is not None else None
    chk(f"4 vues avec la barre d'outils {'(nouvelle zone de l autre côté) ' if flip else ''}: une colonne à gauche, de sa largeur, sur toute la hauteur ; les 4 vues à côté",
        col is not None and len(v3()) == 5 and len(P) == 4 and col.true[0] == 2 and col.true[1] == 100 and col.true[3] == 954 and 58 <= col.true[2] <= 66
        and min(a.true[0] for a in P.values()) > col.true[0] + col.true[2] and max(a.true[0] + a.true[2] for a in P.values()) == 1576 and not LOG and not job.error,
        (col and col.true, job.error, LOG))
chk("la colonne ne montre que la barre d'outils : ni en-tête, ni panneau, ni texte, ni grille, ni poignées", sp is not None and sp.show_region_toolbar and not sp.show_region_header
    and not sp.show_region_ui and not sp.show_region_tool_header and not sp.overlay.show_overlays and sp.show_gizmo is False)
flags = {p: (a.spaces.active.show_region_header, a.spaces.active.show_region_toolbar) for p, a in P.items()}
chk("... et les 4 vues ne la montrent plus (l'en-tête reste en haut à gauche)", flags == {'TL': (True, False), 'TR': (False, False), 'BL': (False, False), 'BR': (False, False)}, flags)
chk("vues attribuées comme avant : Top, Perspective, Front, Right", {p: a.view for p, a in P.items()} == {'TL': "Top", 'TR': "Perspective", 'BL': "Front", 'BR': "Right"})
chk("la colonne est reconnue : pas de barres du bas ni de titre chez elle, elle n'est pas une des 4 vues", m.quad_is_column(col) and m.quad_bars(col) is None
    and not any(m.quad_is_column(a) for a in P.values()) and col.as_pointer() not in m.quad_peers(P['TR'].as_pointer()))
for pos in ('TL', 'TR', 'BL', 'BR'):
    enter_col()
    col, P = column()
    keep = P[pos]
    job = m.QuadJob('exit', WIN, SCR, keep.as_pointer(), keep=keep.as_pointer())
    drive(job)
    SCR.refresh()
    chk(f"retour à une vue en gardant {pos} : la colonne se referme aussi, la vue reprend toute la place et sa barre d'outils",
        v3() == [keep] and keep.true == FULL and keep.spaces.active.show_region_toolbar and keep.spaces.active.show_region_header and not LOG and not job.error,
        ([a.true for a in v3()], job.error, LOG))
SEC = "colonne : largeur"
enter_col()
col, P = column()
MOVES = []
def f_move(win, screen, a, x, y, delta):
    """Comme Blender : le bord vertical en x se déplace, les zones de part et d'autre suivent."""
    MOVES.append((a.as_pointer(), x, y, delta))
    for b in screen.areas:
        bx, by, bw, bh = b.true
        if abs(bx + bw - x) <= 3:
            b.true = (bx, by, bw + delta, bh)
        elif abs(bx - x - 2) <= 3:
            b.true = (bx + delta, by, bw - delta, bh)
    screen.refresh()
    return True
m._area_move = f_move
r0 = m.quad_column_watch(col, WIN)
chk("premier dessin de la colonne : sa barre d'outils est mesurée, rien ne bouge", r0 is False and m._QUAD["colw"].get(col.as_pointer()) == 60 and not MOVES)
col.tools = 100
r1 = m.quad_column_watch(col, WIN)
pending = m._QUAD["fit"]
m._quad_fit_tick()
chk("la barre passe de 1 à 2 colonnes d'icônes (60 -> 100 px) : la colonne se recale sur elle, son bord droit avance de 40 px",
    r1 and pending is not None and [mv[3] for mv in MOVES] == [40] and MOVES[0][1] == 66 and col.width == 104 and m._QUAD["fit"] is None
    and len(column()[1]) == 4 and m.quad_is_column(col), (r1, MOVES, col.width))
del MOVES[:]
col.tools = 60
m.quad_column_watch(col, WIN); m._quad_fit_tick()
chk("... et revient à une colonne d'icônes (100 -> 60 px) : la colonne rétrécit de 40 px", [mv[3] for mv in MOVES] == [-40] and col.width == 64, (MOVES, col.width))
del MOVES[:]
f_move(WIN, SCR, col, col.x + col.width, 500, 96); del MOVES[:]          # (bord tiré à la main : 200 px)
r2 = m.quad_column_watch(col, WIN)
chk("colonne élargie à la main (pour faire de la place à la barre) : elle reste comme elle est tant que la barre ne change pas", r2 is False and not MOVES and m._QUAD["fit"] is None and col.width == 160, col.width)
col.tools = 0
chk("barre d'outils masquée (largeur nulle) : rien ne bouge", m.quad_column_watch(col, WIN) is False and not MOVES)
m.quad_reset()
chk("fichier ouvert : plus rien de mémorisé", m._QUAD["colw"] == {} and m._QUAD["fit"] is None)

SEC = "colonne"
job = enter_col(toolbar=False)
col, P = column()
chk("barre d'outils masquée avant les 4 vues : pas de colonne", col is None and len(v3()) == 4 and len(P) == 4, len(v3()))
job = enter_col(refuse=2)
chk("Blender refuse la coupe en 4 : la colonne est refermée aussi, on retrouve la vue d'origine à sa place", len(v3()) == 1 and v3()[0].true == FULL and job.error == "split"
    and "fermeture d'une zone sans taille" not in LOG, ([a.true for a in v3()], job.error, LOG))
summary()
