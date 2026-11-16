bl_info = {
    "name": "Wanderer CAD",
    "author": "Hostylmatic / OZLUK Tolga",
    "version": (2, 96, 128),
    "blender": (4, 2, 0),
    "location": "3D Viewport > Left toolbar (Object and Edit mode)  |  Add > Wanderer  |  Sidebar > Wanderer",
    "description": "Precision CAD modeling for Blender: draw with snapping and typed values, build curves, surfaces and solids, edit with trim, split, fillet and booleans, add dimensions and clipping planes, lay out paper sheets with viewports at scale and export them to PDF, and run every command from a command line.",
    "category": "Modeling",
}

# Wanderer CAD est un paquet de modules (un par famille d'outils). Ils sont chargés dans cet ordre : chacun n'utilise à son
# chargement que des modules déjà chargés ; ce qu'il emprunte à un module suivant est lié ensuite par _late_imports().
import importlib

_MODULES = (
    "languages", "core", "history", "snapping", "drawing", "base", "tools_draw", "solids", "subd", "transform",
    "edges", "booleans", "selection", "settings", "dimensions", "layers", "import_dxf", "objects",
    "curve_edit", "display", "gumball", "offset_extrude", "trim", "join_explode", "surfaces", "hatch",
    "surface_tools", "curve_tools", "blocks", "surface_edit", "make2d", "layout_engine", "layout", "layout_sheet", "lights", "gumball_handles", "menus",
    "icons", "toolbar", "navigation", "views", "quadview", "cplane", "pushpull", "rhino_commands", "command_line",
    "preferences", "header_bars", "registration",
)

_reload = "_loaded" in globals()       # réactivation de l'add-on sans redémarrer Blender : on recharge les modules
_loaded = []
for _name in _MODULES:
    _mod = globals().get(_name) if _reload else None      # module déjà chargé (attribut du paquet) : rechargé
    _loaded.append(importlib.reload(_mod) if _mod is not None else importlib.import_module("." + _name, __name__))
for _mod in _loaded:
    _mod._late_imports()
del _name, _mod

from .registration import register, unregister     # noqa: E402
