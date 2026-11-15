import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE, 'harness.py')).read())
exec(open(_os.path.join(_HERE, 'prec_lib.py')).read())
_RENDER_BARS_LIB = True
exec(open(_os.path.join(_HERE, 'render_bars.py')).read())
# Les barres du bas gardent la même marge à gauche et à droite, même quand le panneau latéral est large (cas du Mac)
SEC = "Barres du bas : centrage"
install(ui_scale=1.0)
m.DessinBase.active_tool_id = staticmethod(lambda context: "dessin.join_tool")
m.current_view_name = lambda c: "Perspective"
BG = tuple(CL._cmd_theme()["bg"])
ptr = area.as_pointer()
def pills(ops):
    out=[]
    for op in ops:
        if op[0]=="TRIS" and tuple(op[2])==BG:
            xs=[p[0] for p in op[1]]; ys=[p[1] for p in op[1]]
            out.append((min(xs),min(ys),max(xs),max(ys)))
    return out
def margins(free, left, right):
    """(marge à gauche de la barre d'outils, marge à droite du panneau) pour la rangée du bas."""
    ops, width, compact = draw(free, left, right)
    P = pills(ops)
    low = [p for p in P if abs(p[1] - min(q[1] for q in P)) < 1.0]
    return round(min(p[0] for p in low) - left, 1), round((width - right) - max(p[2] for p in low), 1), width, compact
for name, left, right in (("panneaux égaux", 44, 44),
                          ("barre latérale large (Mac : Layers ouvert)", 105, 445),
                          ("barre d'outils large, pas de latérale", 200, 0),
                          ("sans panneau", 0, 0)):
    gl, gr, width, compact = margins(1100, left, right)
    rec(SEC, f"{name} : même marge à gauche et à droite", abs(gl - gr) < 1.0, (gl, gr))
# le groupe ne passe jamais sous un panneau, même très serré
bad = []
for left, right in ((105, 445), (300, 500), (44, 700), (0, 900)):
    for free in range(260, 1400, 37):
        ops, width, compact = draw(free, left, right)
        P = pills(ops)
        if any(p[0] < left - 0.01 or p[2] > width - right + 0.01 for p in P):
            bad.append((left, right, free))
rec(SEC, "rien ne glisse sous la barre d'outils ni sous la barre latérale", not bad, bad[:6])
# la ligne de commande seule sur sa ligne est centrée de la même façon
ops, width, compact = draw(620, 105, 445)
P = pills(ops)
top = max(P, key=lambda p: p[1])
rec(SEC, "la ligne de commande au-dessus suit le même centre",
    abs((top[0] - 105) - ((width - 445) - top[2])) < 1.0, (round(top[0] - 105, 1), round((width - 445) - top[2], 1)))
summary()
