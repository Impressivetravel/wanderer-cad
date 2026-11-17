# Charge l'add-on à tester dans `m` (à exécuter avec exec : attend SRC, ou _SRC, le chemin de wanderer_cad/__init__.py).
import importlib.util, sys, types
import os as _hos
try:
    SRC
except NameError:
    SRC=_SRC
import os as _hos
class _Facade(types.ModuleType):
    """L'add-on est un paquet de modules : `m` en présente tous les noms comme le faisait le fichier unique. Affecter
    `m.nom = valeur` remplace ce nom dans tous les modules qui l'utilisent (ils en tiennent chacun une référence)."""
    def __init__(self,pkg,mods):
        super().__init__('m'); d=self.__dict__; d['_mods']=mods
        for mm in mods: d.update({k:v for k,v in vars(mm).items() if not (k.startswith('__') and k.endswith('__'))})
    def __setattr__(self,k,v):
        self.__dict__[k]=v
        for mm in self.__dict__['_mods']:
            if k in vars(mm): setattr(mm,k,v)
_pkg_dir=_hos.path.dirname(_hos.path.abspath(SRC))
if _hos.path.basename(SRC)=='__init__.py' and _hos.path.exists(_hos.path.join(_pkg_dir,'core.py')):
    sp=importlib.util.spec_from_file_location('wanderer_cad',SRC,submodule_search_locations=[_pkg_dir])
    _pkg=importlib.util.module_from_spec(sp);sys.modules['wanderer_cad']=_pkg;sp.loader.exec_module(_pkg)
    m=_Facade(_pkg,[sys.modules['wanderer_cad.'+n] for n in _pkg._MODULES]+[_pkg]);sys.modules['m']=m
else:       # ancienne version en un seul fichier
    sp=importlib.util.spec_from_file_location('m',SRC);m=importlib.util.module_from_spec(sp);sys.modules['m']=m;sp.loader.exec_module(m)
