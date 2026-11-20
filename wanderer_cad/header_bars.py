"""Wanderer CAD : bouton de l'en-tête de la vue 3D, juste à gauche de « Selectability & Visibility », qui affiche ou masque
les trois barres du bas (onglets de vue, ligne de commande, modes).

L'en-tête de Blender n'offre que deux points d'accroche : le tout début (prepend) et la toute fin (append). Pour placer le
bouton à côté de Selectability & Visibility, le dessin d'origine reçoit un « layout » intermédiaire qui ajoute le bouton
juste avant ce menu, puis laisse Blender dessiner la suite telle quelle. Au moindre souci, on revient à un simple ajout en
fin d'en-tête : le bouton reste toujours accessible."""

import bpy

_HB_ANCHOR = "VIEW3D_PT_object_type_visibility"
_HB = {"orig": None, "fallback": False}


def draw_bars_toggle(layout, context):
    st = getattr(context.scene, "dessin", None)
    if st is not None:
        layout.prop(st, "show_bars", text="", icon='STATUSBAR', toggle=True)


class _HBLayout:
    """Transmet tout au vrai layout ; ajoute le bouton juste avant le menu Selectability & Visibility."""
    __slots__ = ("_l", "_c", "_done")

    def __init__(self, layout, context):
        object.__setattr__(self, "_l", layout)
        object.__setattr__(self, "_c", context)
        object.__setattr__(self, "_done", False)

    def popover(self, *args, **kw):
        if not self._done and (kw.get("panel") == _HB_ANCHOR or (args and args[0] == _HB_ANCHOR)):
            object.__setattr__(self, "_done", True)
            draw_bars_toggle(self._l, self._c)
        return self._l.popover(*args, **kw)

    def __getattr__(self, name):
        return getattr(self._l, name)

    def __setattr__(self, name, value):
        setattr(self._l, name, value)


class _HBSelf:
    __slots__ = ("_real", "layout")

    def __init__(self, real, layout):
        object.__setattr__(self, "_real", real)
        object.__setattr__(self, "layout", layout)

    def __getattr__(self, name):
        return getattr(self._real, name)


class _Sink:
    """Avale tout ce qu'on lui demande de dessiner (la partie droite de l'en-tête dans la bande des 4 vues)."""
    __slots__ = ()

    def __getattr__(self, name):
        return _sink

    def __setattr__(self, name, value):
        pass

    def __call__(self, *args, **kw):
        return _SINK


_SINK = _Sink()


def _sink(*args, **kw):
    return _SINK


class _StripLayout:
    """En-tête dans la bande des 4 vues : tout passe jusqu'au second séparateur extensible de Blender (modes, menus,
    orientation, accrochage) ; ce qui suit (affichage Solid / Wireframe, superpositions, poignées) n'est pas dessiné :
    ces boutons y commanderaient la bande elle-même."""
    __slots__ = ("_l", "_n")

    def __init__(self, layout):
        object.__setattr__(self, "_l", layout)
        object.__setattr__(self, "_n", 0)

    def separator_spacer(self, *args, **kw):
        object.__setattr__(self, "_n", self._n + 1)
        if self._n <= 2:
            return self._l.separator_spacer(*args, **kw)
        return None

    def __getattr__(self, name):
        if self._n >= 2:
            return _sink
        return getattr(self._l, name)

    def __setattr__(self, name, value):
        if self._n < 2:
            setattr(self._l, name, value)


def _in_strip(context):
    try:
        from .quadview import quad_is_strip
        return quad_is_strip(context.area)
    except (ImportError, AttributeError, ReferenceError, RuntimeError):
        return False


def header_draw(self, context):
    orig = _HB["orig"]
    if orig is not None and _in_strip(context):
        try:
            orig(_HBSelf(self, _StripLayout(self.layout)), context)
        except Exception:
            pass
        draw_bars_toggle(self.layout, context)
        return
    if _HB["fallback"] or orig is None:
        return orig(self, context) if orig is not None else None
    proxy = _HBLayout(self.layout, context)
    try:
        orig(_HBSelf(self, proxy), context)
    except Exception:
        _HB["fallback"] = True                  # en-tête inattendu : le bouton passe en fin d'en-tête
        return
    if not proxy._done:                            # menu introuvable (autre version de Blender) : en fin d'en-tête
        draw_bars_toggle(self.layout, context)


def _fallback_append(self, context):
    if _HB["fallback"]:
        draw_bars_toggle(self.layout, context)


def register():
    """Blender range les fonctions de dessin de l'en-tête dans une liste (append / prepend) : la première est le dessin
    d'origine. On la remplace par notre version intermédiaire, sans toucher aux ajouts des autres add-ons."""
    cls = bpy.types.VIEW3D_HT_header
    try:
        cls.append(_fallback_append)              # crée la liste si besoin, et sert de repli
        funcs = cls.draw._draw_funcs
    except (AttributeError, RuntimeError):
        return
    if _HB["orig"] is None and funcs and funcs[0] is not header_draw:
        _HB["orig"] = funcs[0]
        funcs[0] = header_draw


def unregister():
    cls = bpy.types.VIEW3D_HT_header
    try:
        funcs = cls.draw._draw_funcs
        if _HB["orig"] is not None and header_draw in funcs:
            funcs[funcs.index(header_draw)] = _HB["orig"]
    except (AttributeError, RuntimeError):
        pass
    try:
        cls.remove(_fallback_append)
    except (AttributeError, RuntimeError, ValueError):
        pass
    _HB["orig"] = None
    _HB["fallback"] = False


def _late_imports():
    pass
