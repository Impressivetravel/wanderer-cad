"""Wanderer CAD : 4 vues (Top, Perspective, Front, Right) comme dans Rhino, chacune avec son affichage."""

import bpy
import itertools
import time

from .core import tr_label
from .views import _CMD


# --------------------------------------------------------------------------
# Principe
# --------------------------------------------------------------------------
# Le bouton à gauche des onglets de vue coupe la vue 3D en quatre vues 3D de Blender : Top en haut à gauche, Perspective
# en haut à droite, Front en bas à gauche, Right en bas à droite (la disposition de Rhino). Chaque vue est une vraie vue
# 3D : elle a son propre affichage (filaire, ombré, textures, rendu), choisi dans le menu de son titre — ce que le
# « Toggle Quad View » de Blender ne permet pas (ses quatre vues partagent un seul affichage). Un double-clic sur le
# titre d'une vue (ou le bouton) referme les trois autres : on revient à une seule vue, celle-là.
#
# Les barres du bas (onglets, ligne de commande, modes) ne sont dessinées qu'une fois, centrées sous les quatre vues :
# chaque vue dessine la même barre, décalée, et n'en montre que sa part (voir bars_draw). Elles montrent la « vue
# active » : celle où l'on tape une commande, sinon la dernière où l'on a cliqué (dans la vue ou sur son titre) ; son
# titre est en clair. Survoler une vue ne la rend pas active : on en traverse toujours une pour atteindre les barres.
#
# Une commande de dessin en cours suit la souris d'une vue à l'autre (quad_follow), comme dans Rhino : un point dans la
# vue de dessus, le suivant dans la perspective. La ligne de commande montre son invite, quelle que soit la vue active.
#
# La barre d'outils prend toute la hauteur, à gauche des 4 vues, comme dans Rhino : elle vit dans une vue 3D étroite
# (la « colonne »), juste de sa largeur, qui ne montre rien d'autre (ni en-tête, ni grille, ni objets, ni barres du bas)
# et que les commandes ignorent. Elle est créée avec les 4 vues et refermée avec elles.
#
# Rien n'est mémorisé dans le fichier : les 4 vues sont reconnues à leur disposition (4 vues 3D en grille 2 x 2). L'écran
# de Blender ne calcule la taille d'une zone qu'au rafraîchissement suivant : la coupe et la fermeture se font donc en
# plusieurs temps, par un minuteur, en retrouvant chaque fois les zones par leur pointeur (une zone fermée ne doit plus
# jamais être touchée).

QUAD_VIEWS = {'TL': "Top", 'TR': "Perspective", 'BL': "Front", 'BR': "Right"}
QUAD_OPPOSITE = {'TL': 'BR', 'BR': 'TL', 'TR': 'BL', 'BL': 'TR'}
QUAD_HEADER = 'TL'          # celle qui garde l'en-tête et la barre d'outils : en haut à gauche
QUAD_SIDEBAR = 'TR'         # celle qui garde le panneau latéral (N) : en haut à droite
QUAD_TOL = 14               # pixels : jeu entre deux zones voisines (leurs bords se touchent à 1 ou 2 px près)
QUAD_DISPLAY_ITEMS = (
    ('WIREFRAME', "Wireframe", "Only the edges"),
    ('SOLID', "Shaded", "Shaded surfaces (Blender's Solid display)"),
    ('MATERIAL', "Textures", "Materials and textures (Blender's Material Preview)"),
    ('RENDERED', "Rendered", "The render engine, with the lights of the scene"),
)
QUAD_COL_MAX = 0.25          # la colonne de la barre d'outils fait au plus ce quart de la largeur des 4 vues
QUAD_UI_KEYS = ("show_region_header", "show_region_tool_header", "show_region_toolbar", "show_region_ui")

_QUAD = {"job": None, "hit": {}, "ui": {}, "shade": {}, "home": {}, "click": (None, 0.0), "cache": (None, {}),
         "focus": {}, "drawn": {}, "sync": {}, "colw": {}, "fit": None}
# job : coupe ou fermeture en cours (QuadJob) ; hit : zones cliquables du titre de chaque vue ; ui : réglages de la vue
# d'origine (en-tête, panneaux, texte de Blender) par écran, rendus au retour à une vue ; shade : dernier affichage de
# chaque quart ; home : nom de la vue où l'on était avant les 4 vues ; click : dernier clic sur un titre (double-clic) ;
# focus : vue active de chaque écran ; drawn / sync : barres déjà dessinées par chaque vue (les autres sont redessinées
# quand elles changent)


# --------------------------------------------------------------------------
# Reconnaître les 4 vues
# --------------------------------------------------------------------------

def quad_rects(screen):
    """[(pointeur, x, y, largeur, hauteur)] des vues 3D d'un écran."""
    out = []
    try:
        for a in screen.areas:
            if a.type == 'VIEW_3D':
                out.append((a.as_pointer(), int(a.x), int(a.y), int(a.width), int(a.height)))
    except (AttributeError, ReferenceError, RuntimeError):
        pass
    return out


def quad_grid(four, tol=QUAD_TOL):
    """{'TL': pointeur, 'TR': ..., 'BL': ..., 'BR': ...} si ces 4 rectangles (ptr, x, y, w, h) forment une grille 2 x 2
    (chacun dans un coin de leur emprise, sans trou ni recouvrement), sinon None."""
    if len(four) != 4 or any(r[3] <= 0 or r[4] <= 0 for r in four):
        return None
    x0, y0 = min(r[1] for r in four), min(r[2] for r in four)
    x1, y1 = max(r[1] + r[3] for r in four), max(r[2] + r[4] for r in four)
    grid = {}
    for ptr, x, y, w, h in four:
        left, right = abs(x - x0) <= tol, abs(x + w - x1) <= tol
        bottom, top = abs(y - y0) <= tol, abs(y + h - y1) <= tol
        if left == right or bottom == top:
            return None                     # (ni dans un coin, ou sur toute une largeur / hauteur)
        grid[('T' if top else 'B') + ('L' if left else 'R')] = (ptr, w, h)
    if len(grid) != 4:
        return None
    W, H = x1 - x0, y1 - y0
    for a, b, k, total in (('TL', 'TR', 1, W), ('BL', 'BR', 1, W), ('TL', 'BL', 2, H), ('TR', 'BR', 2, H)):
        if abs(grid[a][k] + grid[b][k] - total) > 2 * tol:
            return None
    return {pos: v[0] for pos, v in grid.items()}


def quad_groups(rects):
    """{pointeur: (position, grille)} pour chaque vue 3D qui fait partie d'une grille de 4 vues."""
    out = {}
    if len(rects) < 4:
        return out
    for four in itertools.combinations(rects, 4):
        if any(r[0] in out for r in four):
            continue
        g = quad_grid(four)
        if g is not None:
            for pos, ptr in g.items():
                out[ptr] = (pos, g)
    return out


def quad_of(screen, ptr):
    """(position, grille) de la zone `ptr` si elle fait partie des 4 vues de son écran, sinon (None, None)."""
    rects = quad_rects(screen)
    key = tuple(rects)
    if _QUAD["cache"][0] != key:
        _QUAD["cache"] = (key, quad_groups(rects))
    return _QUAD["cache"][1].get(ptr, (None, None))


def quad_column_of(screen, grid, tol=QUAD_TOL):
    """La colonne de la barre d'outils des 4 vues `grid` : une vue 3D étroite collée à leur gauche, sur toute leur hauteur
    (reconnue à sa place, comme les 4 vues). None s'il n'y en a pas."""
    try:
        areas = [a for a in screen.areas if a.as_pointer() in grid.values()]
        if len(areas) != 4:
            return None
        x0 = min(a.x for a in areas)
        y0, y1 = min(a.y for a in areas), max(a.y + a.height for a in areas)
        W = max(a.x + a.width for a in areas) - x0
        for a in screen.areas:
            if a.type != 'VIEW_3D' or a.as_pointer() in grid.values() or a.width <= 0:
                continue
            if (abs(a.x + a.width - x0) <= tol and abs(a.y - y0) <= tol and abs(a.y + a.height - y1) <= tol
                    and a.width <= QUAD_COL_MAX * W):
                return a
    except (AttributeError, ReferenceError, RuntimeError, TypeError):
        pass
    return None


def quad_is_column(area):
    """True si cette vue 3D est la colonne de la barre d'outils de 4 vues : elle ne dessine ni barres ni titre."""
    try:
        screen = area.id_data
        quad_of(screen, area.as_pointer())                   # (met à jour la reconnaissance des 4 vues de l'écran)
        seen = set()
        for _pos, grid in _QUAD["cache"][1].values():
            key = tuple(sorted(grid.values()))
            if key in seen:
                continue
            seen.add(key)
            col = quad_column_of(screen, grid)
            if col is not None and col.as_pointer() == area.as_pointer():
                return True
    except (AttributeError, ReferenceError, RuntimeError, TypeError):
        pass
    return False


def quad_tool_width(area):
    """Largeur de la barre d'outils d'une vue 3D (pixels), 0 si elle est masquée."""
    try:
        if not getattr(area.spaces.active, "show_region_toolbar", False):
            return 0
        return max((int(r.width) for r in area.regions if r.type == 'TOOLS'), default=0)
    except (AttributeError, ReferenceError, TypeError):
        return 0


def quad_native(area):
    """True si la vue 3D est dans le « Toggle Quad View » de Blender (4 régions de dessin dans une seule vue 3D)."""
    try:
        return sum(1 for r in area.regions if r.type == 'WINDOW') > 1
    except (AttributeError, ReferenceError, TypeError):
        return False


def quad_grid_of(area):
    """Grille {position: pointeur} des 4 vues dont cette vue 3D fait partie, ou None."""
    try:
        return quad_of(area.id_data, area.as_pointer())[1]
    except (AttributeError, ReferenceError):
        return None


def quad_peers(ptr):
    """Pointeurs des 4 vues dont la vue `ptr` fait partie (d'après la dernière reconnaissance), sinon (ptr,)."""
    g = _QUAD["cache"][1].get(ptr)
    return tuple(g[1].values()) if g is not None else (ptr,)


def quad_focus(screen, grid):
    """Pointeur de la vue active parmi les 4 : celle où l'on tape une commande, sinon la dernière où l'on a cliqué,
    sinon la perspective (en haut à droite)."""
    try:
        st = _CMD["input"]
        if st is not None and st.get("area") in grid.values():
            return st["area"]
        f = _QUAD["focus"].get(screen.as_pointer())
        if f in grid.values():
            return f
    except (AttributeError, ReferenceError, TypeError):
        pass
    return grid.get('TR')


def quad_focus_set(area):
    """Cette vue devient la vue active (on vient d'y cliquer, ou d'y taper une commande). True si elle ne l'était pas."""
    grid = quad_grid_of(area)
    if grid is None:
        return False
    screen, ptr = area.id_data, area.as_pointer()
    if _QUAD["focus"].get(screen.as_pointer()) == ptr:
        return False
    _QUAD["focus"][screen.as_pointer()] = ptr
    _redraw_all(screen)
    return True


def quad_area_at(area, x, y):
    """Celle des 4 vues, autre que `area`, dont la région de dessin est sous la souris (pixels de la fenêtre), ou None."""
    grid = quad_grid_of(area)
    if grid is None:
        return None
    me, ptrs = area.as_pointer(), tuple(grid.values())
    for a in area.id_data.areas:
        p = a.as_pointer()
        if p != me and p in ptrs and find_window_region(a, x, y) is not None:
            return a
    return None


def quad_move_op(op, new, alive=True):
    """La commande `op` passe dans la vue `new` : son invite et son réticule la suivent. alive=False : sa vue n'existe
    plus (elle a été fermée) et ne doit plus être touchée."""
    old = op.area
    optr, nptr = old.as_pointer(), new.as_pointer()
    if _CMD["op"].get(optr) is op:
        del _CMD["op"][optr]
    prompt = _CMD["prompt"].get(optr)
    if alive:
        set_prompt(old, None)
    else:
        _CMD["prompt"].pop(optr, None)
        _CMD["cleared"].discard(optr)
    for k in ("mouse", "mouse_org", "mouse_t"):
        _CMD.get(k, {}).pop(optr, None)
    op.area = new
    op.region = _win_region(new)
    if hasattr(op, "snap_screen"):
        op.snap_screen = None                   # (repère d'accrochage : en pixels de l'ancienne vue)
    _CMD["op"][nptr] = op
    if prompt:
        set_prompt(new, prompt)
    if alive:
        old.tag_redraw()
    new.tag_redraw()


def quad_follow(op, context, event):
    """Une commande de dessin en cours suit la souris d'une vue à l'autre parmi les 4 vues, comme dans Rhino : un point
    dans la vue de dessus, le suivant dans la perspective. La vue où l'on clique devient la vue active.
    Blender garde pour contexte la vue où la commande a démarré ; `op.area` est celle où elle est maintenant."""
    area, home = getattr(op, "area", None), getattr(context, "area", None)
    if area is None or home is None:
        return
    try:
        ptr = area.as_pointer()
        if ptr != home.as_pointer() and _area_by_ptr(home.id_data, ptr) is None:
            quad_move_op(op, home, alive=False)             # sa vue a été fermée : elle revient là où elle a démarré
            area = home
        et = event.type
        if et not in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE', 'LEFTMOUSE', 'RIGHTMOUSE'}:
            return
        x, y = event.mouse_x, event.mouse_y
        if not (area.x <= x < area.x + area.width and area.y <= y < area.y + area.height):       # sortie de sa vue
            other = quad_area_at(area, x, y)
            if other is not None and _CMD["op"].get(other.as_pointer()) in (None, op):
                quad_move_op(op, other)
                area = other
        if et == 'LEFTMOUSE' and event.value == 'PRESS' and find_window_region(area, x, y) is not None \
                and not getattr(op, "mouse_over_ui", lambda e: False)(event) and cmd_hit(area, x, y) is None:
            quad_focus_set(area)                # (un clic dans la barre d'outils ou sur les barres ne change pas de vue active)
    except (AttributeError, ReferenceError, RuntimeError, TypeError, KeyError, ValueError):
        pass


def quad_frame(screen, grid):
    """Cadre des barres du bas quand les 4 vues sont affichées : l'ensemble de leurs régions de dessin, (x, y, largeur,
    hauteur) en pixels de la fenêtre. None tant qu'une des vues n'a pas sa taille."""
    rs = []
    for q in grid.values():
        a = _area_by_ptr(screen, q)
        r = _win_region(a) if a is not None else None
        if r is None or r.width <= 1 or r.height <= 1:
            return None
        rs.append(r)
    x0, y0 = min(r.x for r in rs), min(r.y for r in rs)
    return (x0, y0, max(r.x + r.width for r in rs) - x0, max(r.y + r.height for r in rs) - y0)


def quad_bars(area):
    """(vue active, cadre des barres, pointeurs des 4 vues) quand cette vue 3D fait partie de 4 vues ; None sinon."""
    grid = quad_grid_of(area)
    if grid is None:
        return None
    try:
        screen = area.id_data
        fr = quad_frame(screen, grid)
        owner = _area_by_ptr(screen, quad_focus(screen, grid))
    except (AttributeError, ReferenceError, RuntimeError):
        return None
    if fr is None or owner is None:
        return None
    return owner, fr, tuple(grid.values())


def quad_active(context):
    """True si la vue 3D du contexte fait partie de 4 vues."""
    try:
        return quad_of(context.screen, context.area.as_pointer())[0] is not None
    except (AttributeError, ReferenceError):
        return False


def quad_busy():
    return _QUAD["job"] is not None


# --------------------------------------------------------------------------
# Gestes élémentaires sur l'écran (les seuls endroits où l'on appelle les opérateurs d'écran de Blender)
# --------------------------------------------------------------------------

def _area_by_ptr(screen, ptr):
    try:
        return next((a for a in screen.areas if a.as_pointer() == ptr), None)
    except (AttributeError, ReferenceError, RuntimeError):
        return None


def _window_by_ptr(ptr):
    try:
        return next((w for w in bpy.context.window_manager.windows if w.as_pointer() == ptr), None)
    except (AttributeError, ReferenceError, RuntimeError):
        return None


def _win_region(area):
    return next((r for r in area.regions if r.type == 'WINDOW'), None)


def _area_split(win, screen, area, direction, factor=0.5):
    """Coupe une zone en deux (en son milieu, ou à `factor` de son bord gauche / bas). Retourne le pointeur de la
    nouvelle zone, ou None si Blender a refusé."""
    before = {a.as_pointer() for a in screen.areas}
    try:
        with bpy.context.temp_override(window=win, screen=screen, area=area, region=_win_region(area)):
            res = bpy.ops.screen.area_split(direction=direction, factor=factor)
    except (RuntimeError, TypeError, AttributeError, ValueError):
        return None
    if 'FINISHED' not in res:
        return None
    return next((a.as_pointer() for a in screen.areas if a.as_pointer() not in before), None)


def _area_move(win, screen, area, x, y, delta):
    """Déplace le bord de zone qui passe par (x, y) (pixels de la fenêtre) de `delta` pixels."""
    try:
        with bpy.context.temp_override(window=win, screen=screen, area=area, region=_win_region(area)):
            res = bpy.ops.screen.area_move(x=int(x), y=int(y), delta=int(delta))
    except (RuntimeError, TypeError, AttributeError, ValueError):
        return False
    return 'FINISHED' in res


def _area_close(win, screen, area):
    """Ferme une zone (sa voisine prend sa place). Retourne True si elle a disparu."""
    n = len(screen.areas)
    try:
        with bpy.context.temp_override(window=win, screen=screen, area=area, region=_win_region(area)):
            bpy.ops.screen.area_close()
    except (RuntimeError, TypeError, AttributeError, ValueError):
        return False
    return len(screen.areas) < n


def _quad_native_off(win, screen, area):
    """Quitte le « Toggle Quad View » de Blender dans cette vue 3D (avant de la couper en 4 vues séparées)."""
    try:
        with bpy.context.temp_override(window=win, screen=screen, area=area, region=_win_region(area)):
            bpy.ops.screen.region_quadview()
    except (RuntimeError, TypeError, AttributeError, ValueError):
        pass


def _area_set_view(win, screen, area, name):
    """Met une vue 3D dans la vue nommée `name` (Top, Front...), comme un clic sur son onglet."""
    try:
        with bpy.context.temp_override(window=win, screen=screen, area=area, region=_win_region(area),
                                       space_data=area.spaces.active):
            bpy.ops.dessin.view_restore(name=name)
    except (RuntimeError, TypeError, AttributeError, ValueError):
        pass


def _area_view_name(win, screen, area):
    try:
        with bpy.context.temp_override(window=win, screen=screen, area=area, region=_win_region(area),
                                       space_data=area.spaces.active):
            return current_view_name(bpy.context)
    except (RuntimeError, TypeError, AttributeError, ValueError):
        return None


def _area_call(win, screen, area, fn):
    """Appelle fn() dans le contexte d'une zone (comme si la souris y était)."""
    with bpy.context.temp_override(window=win, screen=screen, area=area, region=_win_region(area)):
        fn()


def _redraw_all(screen):
    try:
        for a in screen.areas:
            a.tag_redraw()
    except (AttributeError, ReferenceError, RuntimeError):
        pass


# --------------------------------------------------------------------------
# Réglages de chaque vue
# --------------------------------------------------------------------------

def quad_ui_read(space):
    """Réglages d'une vue 3D que les 4 vues changent : en-tête, panneaux, texte de Blender en haut à gauche."""
    st = {k: bool(getattr(space, k, True)) for k in QUAD_UI_KEYS}
    try:
        st["show_text"] = bool(space.overlay.show_text)
    except AttributeError:
        st["show_text"] = True
    return st


def quad_ui_apply(space, st):
    for k in QUAD_UI_KEYS:
        try:
            if bool(getattr(space, k)) != bool(st.get(k, True)):
                setattr(space, k, bool(st.get(k, True)))
        except (AttributeError, TypeError, RuntimeError):
            pass
    try:
        space.overlay.show_text = bool(st.get("show_text", True))
    except (AttributeError, TypeError, RuntimeError):
        pass


def quad_ui_for(pos, orig, column=False):
    """Réglages d'un quart : l'en-tête et la barre d'outils en haut à gauche, le panneau latéral en haut à droite (s'ils
    étaient affichés), rien ailleurs ; le texte de Blender laisse la place au titre de la vue. column : la barre d'outils
    est dans sa colonne, à gauche des 4 vues (aucun quart ne la montre)."""
    return {"show_region_header": pos == QUAD_HEADER and orig.get("show_region_header", True),
            "show_region_tool_header": pos == QUAD_HEADER and orig.get("show_region_tool_header", True),
            "show_region_toolbar": pos == QUAD_HEADER and not column and orig.get("show_region_toolbar", True),
            "show_region_ui": pos == QUAD_SIDEBAR and orig.get("show_region_ui", False),
            "show_text": False}


def quad_column_setup(area):
    """La colonne ne montre que la barre d'outils : ni en-tête, ni panneau, ni grille, ni poignées, et sa vue regarde au
    loin (aucun objet ne passe dans la mince bande de vue qui dépasse de la barre)."""
    space = area.spaces.active
    quad_ui_apply(space, {"show_region_header": False, "show_region_tool_header": False, "show_region_toolbar": True,
                          "show_region_ui": False, "show_text": False})
    for obj, k, v in ((getattr(space, "overlay", None), "show_overlays", False), (space, "show_gizmo", False)):
        try:
            setattr(obj, k, v)
        except (AttributeError, TypeError, RuntimeError):
            pass
    try:
        r3 = space.region_3d
        r3.view_perspective = 'ORTHO'
        r3.view_location = (1.0e7, 1.0e7, 1.0e7)
        r3.view_distance = 1.0
    except (AttributeError, TypeError, RuntimeError):
        pass


QUAD_COL_PAD = 4            # pixels laissés à droite de la barre d'outils, dans sa colonne


def quad_column_watch(area, win=None):
    """Appelé quand la colonne de la barre d'outils se redessine : si la barre a changé de largeur (passée d'une à deux
    colonnes d'icônes, ou l'inverse), la colonne se recale sur elle un instant plus tard. Élargir la colonne à la main
    (son bord) ne la fait pas revenir : on peut ainsi faire de la place avant d'élargir la barre."""
    try:
        ptr = area.as_pointer()
        tw = max((int(r.width) for r in area.regions if r.type == 'TOOLS'), default=0)
    except (AttributeError, ReferenceError, TypeError):
        return False
    if tw <= 1:
        return False
    last = _QUAD["colw"].get(ptr)
    _QUAD["colw"][ptr] = tw
    if last is None or last == tw or abs(area.width - (tw + QUAD_COL_PAD)) <= 2 or _QUAD["fit"] is not None:
        return False
    try:
        win = win or bpy.context.window
        _QUAD["fit"] = (win.as_pointer(), ptr)
        bpy.app.timers.register(_quad_fit_tick, first_interval=0.05)
    except (AttributeError, ReferenceError, RuntimeError, ValueError):
        _QUAD["fit"] = None
        return False
    return True


def quad_column_fit(win, screen, area):
    """Recale la largeur de la colonne sur sa barre d'outils (en déplaçant son bord droit). True si c'est fait."""
    tw = _QUAD["colw"].get(area.as_pointer(), 0)
    if tw <= 1:
        return False
    delta = (tw + QUAD_COL_PAD) - area.width
    if abs(delta) <= 2:
        return False
    return _area_move(win, screen, area, area.x + area.width, area.y + area.height // 2, delta)


def _quad_fit_tick():
    job, _QUAD["fit"] = _QUAD["fit"], None
    if job is None or _QUAD["job"] is not None:
        return None
    win = _window_by_ptr(job[0])
    screen = win.screen if win is not None else None
    area = _area_by_ptr(screen, job[1]) if screen is not None else None
    if area is not None and quad_is_column(area):
        quad_column_fit(win, screen, area)
        _redraw_all(screen)
    return None


def quad_diag_order(grid, keep, sizes):
    """Zone à fermer ensuite pour ne garder que `keep` : d'abord celle en diagonale, puis la plus petite des deux qui
    restent (la moitié voisine de `keep`), puis la dernière. Ainsi chaque fermeture se fait entre deux zones alignées.
    grid : {position: pointeur} de départ ; sizes : {pointeur: surface} des zones encore là. None quand il n'en reste pas."""
    pos_keep = next((p for p, q in grid.items() if q == keep), None)
    left = [q for q in grid.values() if q != keep and q in sizes]
    if not left:
        return None
    diag = grid.get(QUAD_OPPOSITE.get(pos_keep))
    if len(left) == 3 and diag in left:
        return diag
    return min(left, key=lambda q: sizes[q])


# --------------------------------------------------------------------------
# Coupe et fermeture, en plusieurs temps
# --------------------------------------------------------------------------

class QuadJob:
    """Passage aux 4 vues ('enter') ou retour à une vue ('exit'), un geste par passage du minuteur."""
    WAIT = 0.05
    LIMIT = 4.0                 # secondes : au-delà, on renonce (l'écran reste comme il est)

    def __init__(self, kind, win, screen, ptr, keep=None, then=None):
        self.kind = kind
        self.wptr = win.as_pointer()
        self.ptr = ptr              # 'enter' : la vue 3D que l'on coupe ; 'exit' : n'importe laquelle des 4
        self.keep = keep            # 'exit' : la vue qui reste
        self.then = then            # 'exit' : à faire une fois revenu à une vue (ouvrir une mise en page...)
        self.stage = 0
        self.made = []
        self.grid = None
        self.total = 0
        self.native = False         # 'enter' : le quad view de Blender a d'abord été quitté
        self.col = None             # colonne de la barre d'outils (créée en premier, refermée en dernier)
        self.col_tried = False
        self.t0 = time.monotonic()
        self.error = ""

    def env(self):
        win = _window_by_ptr(self.wptr)
        return (win, win.screen) if win is not None else (None, None)

    def step(self):
        """Un geste. Retourne le délai avant le suivant (secondes), ou None quand c'est fini."""
        win, screen = self.env()
        if win is None or screen is None:
            return None
        if time.monotonic() - self.t0 > self.LIMIT:
            self.error = "timeout"
            if self.kind == 'enter' and self.stage in (1, 2) and self.made:
                self.stage, self.t0 = 9, time.monotonic()        # coupe restée en chemin : on referme ce qui a été ouvert
            else:
                return None
        return self.step_enter(win, screen) if self.kind == 'enter' else self.step_exit(win, screen)

    # ---- vers les 4 vues
    def step_enter(self, win, screen):
        area = _area_by_ptr(screen, self.ptr)
        if area is None or area.type != 'VIEW_3D':
            return None
        if self.stage == 0:
            if quad_native(area):                                        # 4 vues de Blender : elles se referment d'abord
                if not self.native:
                    self.native = True
                    _quad_native_off(win, screen, area)
                return self.WAIT
            if area.width <= 0 or area.height <= 0:
                return self.WAIT
            space = area.spaces.active
            sptr = screen.as_pointer()
            if not self.col_tried:
                _QUAD["ui"][sptr] = quad_ui_read(space)
                _QUAD["home"][sptr] = _area_view_name(win, screen, area)
                self.col_tried = True
                tw = quad_tool_width(area)
                if tw > 0 and area.width > 8 * tw:
                    # d'abord la colonne de la barre d'outils, à gauche, juste de sa largeur
                    c = _area_split(win, screen, area, 'VERTICAL', min(0.45, (tw + 4.0) / float(area.width)))
                    if c is not None:
                        self.col = c
                        self.stage = 5
                        return self.WAIT
            n1 = _area_split(win, screen, area, 'VERTICAL')              # deux colonnes
            if n1 is None:
                self.error = "split"
                if self.col is not None:                                 # (la colonne de la barre d'outils est refermée)
                    self.stage = 9
                    return self.WAIT
                return None
            self.made.append(n1)
            n2 = _area_split(win, screen, area, 'HORIZONTAL')            # la colonne d'origine en deux rangées
            if n2 is None:
                self.error = "split"
                self.stage = 9
                return self.WAIT
            self.made.append(n2)
            self.stage = 1
            return self.WAIT
        if self.stage == 1:
            other = _area_by_ptr(screen, self.made[0])                   # l'autre colonne, une fois sa taille connue
            if other is None:
                self.error = "split"
                self.stage = 9
                return self.WAIT
            if other.width <= 0 or other.height <= 0:
                return self.WAIT
            n3 = _area_split(win, screen, other, 'HORIZONTAL')
            if n3 is None:
                self.error = "split"
                self.stage = 9
                return self.WAIT
            self.made.append(n3)
            self.stage = 2
            return self.WAIT
        if self.stage == 2:
            _QUAD["cache"] = (None, {})
            pos, grid = quad_of(screen, self.ptr)
            if grid is None or not all(q in grid.values() for q in self.made):
                return self.WAIT                                         # (tailles pas encore à jour)
            quad_setup(win, screen, grid)
            _redraw_all(screen)
            return None
        if self.stage == 5:
            # la colonne vient d'être coupée : la plus étroite des deux zones est la colonne (quel que soit le côté où
            # Blender a posé la nouvelle zone), l'autre est coupée en 4 vues
            c = _area_by_ptr(screen, self.col)
            if c is None:
                self.col, self.stage = None, 0
                return self.WAIT
            if c.width <= 0 or c.height <= 0 or area.width <= 0:
                return self.WAIT
            if c.width > area.width:
                self.col, self.ptr = self.ptr, self.col
                c, area = area, c
            quad_column_setup(c)
            self.stage = 0
            return self.WAIT
        # stage 9 : la coupe n'a pas abouti, on referme ce qui a été ouvert (une zone par passage, l'écran rafraîchi entre deux)
        for q in reversed(self.made):
            a = _area_by_ptr(screen, q)
            if a is not None and (a.width <= 0 or a.height <= 0):
                return self.WAIT                     # (une zone dont l'écran ne connaît pas encore la taille ne se ferme pas)
            self.made.remove(q)
            if a is not None:
                _area_close(win, screen, a)
                return 0.2
        if self.col is not None:
            c = _area_by_ptr(screen, self.col)
            self.col = None
            if c is not None:
                _area_close(win, screen, c)
                return 0.2
        quad_ui_apply(area.spaces.active, _QUAD["ui"].get(screen.as_pointer(), {}))
        _redraw_all(screen)
        return None

    # ---- retour à une vue
    def step_exit(self, win, screen):
        if self.stage == 0:
            _QUAD["cache"] = (None, {})
            pos, grid = quad_of(screen, self.ptr)
            if grid is None:
                return None
            if self.keep not in grid.values():
                self.keep = grid.get('TR')
            self.grid = dict(grid)
            sptr = screen.as_pointer()
            for p, q in grid.items():                                    # chaque quart se souvient de son affichage
                a = _area_by_ptr(screen, q)
                if a is not None:
                    _QUAD["shade"][(sptr, p)] = a.spaces.active.shading.type
            rects = {r[0]: r for r in quad_rects(screen) if r[0] in grid.values()}
            self.total = sum(r[3] * r[4] for r in rects.values())
            c = quad_column_of(screen, grid)
            self.col = c.as_pointer() if c is not None else None
            self.stage = 1
        left = {r[0]: r[3] * r[4] for r in quad_rects(screen) if r[0] in self.grid.values()}
        if self.keep not in left:
            return None
        if sum(left.values()) < 0.9 * self.total:
            return self.WAIT                                             # (la zone agrandie n'a pas encore sa taille)
        nxt = quad_diag_order(self.grid, self.keep, left)
        if nxt is None and self.col is not None:
            c = _area_by_ptr(screen, self.col)                           # la colonne de la barre d'outils, en dernier
            self.col = None
            if c is not None and c.width > 0:
                _area_close(win, screen, c)
                return self.WAIT
        if nxt is None:
            area = _area_by_ptr(screen, self.keep)                       # il ne reste qu'elle : elle retrouve ses panneaux
            quad_ui_apply(area.spaces.active, _QUAD["ui"].get(screen.as_pointer(), {}))
            _QUAD["cache"] = (None, {})
            _redraw_all(screen)
            if self.then is not None:
                try:
                    _area_call(win, screen, area, self.then)
                except (RuntimeError, TypeError, AttributeError, ValueError):
                    pass
            return None
        a = _area_by_ptr(screen, nxt)
        if a is None or not _area_close(win, screen, a):
            self.error = "close"
            return None
        return self.WAIT


def quad_setup(win, screen, grid):
    """Les 4 vues viennent d'être créées : chacune prend sa vue (Top, Perspective, Front, Right), ses panneaux et son
    dernier affichage."""
    sptr = screen.as_pointer()
    orig = _QUAD["ui"].get(sptr, {})
    col = quad_column_of(screen, grid)
    if col is not None:
        quad_column_setup(col)
    for pos, q in grid.items():
        a = _area_by_ptr(screen, q)
        if a is None:
            continue
        space = a.spaces.active
        quad_ui_apply(space, quad_ui_for(pos, orig, column=col is not None))
        shade = _QUAD["shade"].get((sptr, pos))
        if shade:
            try:
                space.shading.type = shade
            except (TypeError, AttributeError, RuntimeError):
                pass
        _area_set_view(win, screen, a, QUAD_VIEWS[pos])
    _QUAD["focus"][sptr] = grid.get('TR')            # la vue active, au départ : la perspective
    _QUAD["cache"] = (None, {})


def _quad_tick():
    job = _QUAD["job"]
    if job is None:
        return None
    try:
        delay = job.step()
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError, KeyError, IndexError):
        delay = None
    if delay is None:
        _QUAD["job"] = None
        _QUAD["cache"] = (None, {})
    return delay


def quad_start(kind, context, keep=None, then=None):
    """Lance le passage aux 4 vues ou le retour à une vue. Le premier geste a lieu un instant plus tard : jamais au
    milieu du clic qui l'a demandé. Retourne False si un passage est déjà en cours."""
    if _QUAD["job"] is not None:
        return False
    _QUAD["job"] = QuadJob(kind, context.window, context.screen, context.area.as_pointer(), keep, then)
    try:
        bpy.app.timers.register(_quad_tick, first_interval=0.02)
    except (RuntimeError, ValueError, AttributeError):
        _QUAD["job"] = None
        return False
    return True


def quad_home(context):
    """Vue qui reste quand on quitte les 4 vues par le bouton : la vue active (celle que montrent les barres)."""
    try:
        screen = context.screen
        pos, grid = quad_of(screen, context.area.as_pointer())
        return quad_focus(screen, grid) if grid is not None else None
    except (AttributeError, ReferenceError, RuntimeError):
        return None


def quad_leave_then(context, then):
    """Quitte les 4 vues (s'il y en a) puis fait `then` dans la vue qui reste. Retourne True si le retour est lancé."""
    if not quad_active(context):
        return False
    return quad_start('exit', context, keep=quad_home(context), then=then)


# --------------------------------------------------------------------------
# Commandes
# --------------------------------------------------------------------------

class DESSIN_OT_quad_view(bpy.types.Operator):
    bl_idname = "dessin.quad_view"
    bl_label = "4 Views"
    bl_description = ("Splits the 3D view into four views like Rhino: Top, Perspective, Front, Right, each with its own "
                      "display (the menu of its title). The bottom bars stay once, centered under the four views. Again, "
                      "or a double-click on the title of a view: back to one view")
    bl_options = {'REGISTER'}

    mode: bpy.props.EnumProperty(name="Mode", default='TOGGLE', options={'SKIP_SAVE'},
                                 items=(('TOGGLE', "Toggle", "Four views, or back to one"),
                                        ('QUAD', "4 Views", "Split the view into four views"),
                                        ('SINGLE', "Single View", "Back to one view")))
    here: bpy.props.BoolProperty(name="This view", default=False, options={'SKIP_SAVE'},
                                 description="Back to one view: keep the view under the mouse (otherwise the one you were in)")

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D' and context.window is not None

    def execute(self, context):
        if is_layout(context.scene):
            self.report({'INFO'}, "4 Views: go back to the model first (a layout is a single sheet)")
            return {'CANCELLED'}
        if quad_busy():
            return {'CANCELLED'}
        active = quad_active(context)
        if self.mode == 'QUAD' and active or self.mode == 'SINGLE' and not active:
            return {'CANCELLED'}
        if active:
            keep = context.area.as_pointer() if self.here else quad_home(context)
            ok = quad_start('exit', context, keep=keep)
        else:
            ok = quad_start('enter', context)
        return {'FINISHED'} if ok else {'CANCELLED'}


class DESSIN_OT_quad_display(bpy.types.Operator):
    bl_idname = "dessin.quad_display"
    bl_label = "View Display"
    bl_description = "Display of this view only: wireframe, shaded, textures or rendered (each of the 4 views has its own)"
    bl_options = {'REGISTER'}

    display: bpy.props.EnumProperty(name="Display", items=QUAD_DISPLAY_ITEMS, default='SOLID')

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D'

    def execute(self, context):
        try:
            context.area.spaces.active.shading.type = self.display
            context.area.tag_redraw()
        except (AttributeError, TypeError, RuntimeError):
            return {'CANCELLED'}
        return {'FINISHED'}


class DESSIN_MT_quad_view(bpy.types.Menu):
    bl_idname = "DESSIN_MT_quad_view"
    bl_label = "View"

    def draw(self, context):
        lay = self.layout
        try:
            cur = context.area.spaces.active.shading.type
        except AttributeError:
            cur = None
        icons = {'WIREFRAME': 'SHADING_WIRE', 'SOLID': 'SHADING_SOLID', 'MATERIAL': 'SHADING_TEXTURE', 'RENDERED': 'SHADING_RENDERED'}
        for key, label, _tip in QUAD_DISPLAY_ITEMS:
            lay.operator(DESSIN_OT_quad_display.bl_idname, text=tr_label(label), icon=icons[key], depress=key == cur).display = key
        lay.separator()
        if quad_active(context):
            op = lay.operator(DESSIN_OT_quad_view.bl_idname, text=tr_label("Maximize this View"), icon='FULLSCREEN_ENTER')
            op.mode, op.here = 'SINGLE', True
        else:
            lay.operator(DESSIN_OT_quad_view.bl_idname, text=tr_label("4 Views"), icon='MESH_GRID').mode = 'QUAD'
        lay.separator()
        for name, _axis in BASE_VIEWS:
            lay.operator("dessin.view_restore", text=view_label(context.scene, name)).name = name


def quad_menu_later(context):
    """Ouvre le menu du titre d'une vue un instant après le clic (sinon le relâchement du bouton le referme aussitôt)."""
    wptr, aptr = context.window.as_pointer(), context.area.as_pointer()

    def run():
        try:
            win = _window_by_ptr(wptr)
            area = _area_by_ptr(win.screen, aptr) if win is not None else None
            if area is None:
                return None
            with bpy.context.temp_override(window=win, screen=win.screen, area=area, region=_win_region(area)):
                bpy.ops.wm.call_menu(name=DESSIN_MT_quad_view.bl_idname)
        except (RuntimeError, ReferenceError, TypeError, AttributeError):
            pass
        return None
    try:
        bpy.app.timers.register(run, first_interval=0.25)
    except (RuntimeError, ValueError, AttributeError):
        pass


def quad_name_click(context, now=None):
    """Clic sur le nom d'une vue. Un second clic dans la foulée (double-clic) : cette vue seule, comme dans Rhino.
    Retourne True si c'était un double-clic."""
    now = time.monotonic() if now is None else now
    ptr = context.area.as_pointer()
    quad_focus_set(context.area)                # (un clic sur le titre d'une vue la rend active, sans toucher à la sélection)
    last, t = _QUAD["click"]
    if last == ptr and now - t < 0.45:
        _QUAD["click"] = (None, 0.0)
        try:
            bpy.ops.dessin.quad_view(mode='SINGLE', here=True)
        except RuntimeError:
            pass
        return True
    _QUAD["click"] = (ptr, now)
    return False


def quad_click(context, kind):
    """Clic sur le bouton des 4 vues ('quad') ou sur le titre d'une vue ('quadname', 'quadmenu'). True si traité."""
    try:
        if kind == 'quad':
            bpy.ops.dessin.quad_view()
        elif kind == 'quadmenu':
            quad_focus_set(context.area)
            quad_menu_later(context)
        elif kind == 'quadname':
            quad_name_click(context)
        else:
            return False
    except RuntimeError:
        pass
    return True


def quad_title(context):
    """Nom écrit dans le titre d'une vue : celui de son onglet (Top, Front, Perspective, Axonometric, Back...)."""
    try:
        name = current_view_name(context)
        if not name:
            return tr_label("Camera")
        return tab_label(context, context.scene, name, name)
    except (AttributeError, ReferenceError, RuntimeError):
        return ""


def quad_reset():
    """Fichier ouvert ou module désactivé : plus rien en cours, plus rien de mémorisé."""
    _QUAD.update(job=None, hit={}, ui={}, shade={}, home={}, click=(None, 0.0), cache=(None, {}),
                 focus={}, drawn={}, sync={}, colw={}, fit=None)


QUAD_CLASSES = (DESSIN_OT_quad_view, DESSIN_OT_quad_display, DESSIN_MT_quad_view)


def _late_imports():
    """Noms définis dans des modules chargés après celui-ci : ils ne servent qu'à l'exécution des outils."""
    global BASE_VIEWS, current_view_name, is_layout, tab_label, view_label
    global cmd_hit, find_window_region, set_prompt
    from .command_line import cmd_hit
    from .cplane import set_prompt
    from .drawing import find_window_region
    from .layout import is_layout
    from .navigation import BASE_VIEWS
    from .views import current_view_name, tab_label, view_label
