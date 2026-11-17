import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
exec(open(_os.path.join(_HERE,'prec_lib.py')).read())
# Les outils de courbes sont côte à côte dans la barre d'outils, et non dans le menu déroulant de Polyline
SEC="Barre d'outils : courbes"
crv=[m.DESSIN_TT_polyligne, m.DESSIN_TT_curve_cp, m.DESSIN_TT_curve_interp, m.DESSIN_TT_pen, m.DESSIN_TT_sketch]
grouped=[c.__name__ for c in crv if getattr(c,"_in_group",False)]
rec(SEC,"aucun des cinq outils de courbes n'est rangé dans un menu déroulant",not grouped,grouped)
names=[t[0].__name__ for t in m.TOOL_ORDER]
i=names.index("DESSIN_TT_polyligne")
rec(SEC,"ils se suivent dans la barre, Polyline en tête",names[i:i+5]==[c.__name__ for c in crv],names[i:i+5])
# les menus déroulants voulus ailleurs sont intacts
still=[c.__name__ for c in (m.DESSIN_TT_cercle_d, m.DESSIN_TT_arc_3pts, m.DESSIN_TT_sweep1, m.DESSIN_TT_bool_difference) if getattr(c,"_in_group",False)]
rec(SEC,"les autres menus déroulants (cercle, arc, sweep, booléen) sont gardés",len(still)==4,still)
# chaque outil garde son identifiant et son libellé
bad=[c.__name__ for c in crv if not getattr(c,"bl_idname","") or not getattr(c,"bl_label","")]
rec(SEC,"chacun garde son identifiant et son nom",not bad,bad)
summary()
