bl_info = {
    "name": "Wanderer CAD",
    "author": "Hostylmatic",
    "version": (2, 96, 124),
    "blender": (4, 2, 0),
    "location": "3D Viewport > Left toolbar (Object and Edit mode)  |  Add > Wanderer  |  Sidebar > Wanderer",
    "description": "Precision CAD modeling for Blender: draw with snapping and typed values, build curves, surfaces and solids, edit with trim, split, fillet and booleans, add dimensions and clipping planes, and run every command from a command line.",
    "category": "3D View",
}

# Wanderer CAD est un paquet de modules (un par famille d'outils). Ils sont chargés dans cet ordre : chacun n'utilise à son
# chargement que des modules déjà chargés ; ce qu'il emprunte à un module suivant est lié ensuite par _late_imports().
import importlib
import sys

_MODULES = (
    "core", "snapping", "drawing", "base", "tools_draw", "solids", "subd", "transform",
    "edges", "booleans", "selection", "settings", "dimensions", "layers", "import_dxf", "objects",
    "curve_edit", "display", "gumball", "offset_extrude", "trim", "join_explode", "surfaces", "hatch",
    "surface_tools", "curve_tools", "blocks", "surface_edit", "make2d", "lights", "gumball_handles", "menus",
    "icons", "toolbar", "navigation", "views", "cplane", "pushpull", "rhino_commands", "command_line",
    "preferences", "registration",
)

_reload = "_loaded" in globals()       # réactivation de l'add-on sans redémarrer Blender : on recharge les modules
_loaded = []
for _name in _MODULES:
    _full = __name__ + "." + _name
    if _reload and _full in sys.modules:
        _loaded.append(importlib.reload(sys.modules[_full]))
    else:
        _loaded.append(importlib.import_module(_full))
for _mod in _loaded:
    _mod._late_imports()
del _name, _full, _mod

from .registration import register, unregister     # noqa: E402
