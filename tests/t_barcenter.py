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
    """(marge à gauche de la barre d'outils, marge au bord droit de la vue) pour la rangée du bas. La barre latérale (N)
    n'est pas déduite : elle passe par-dessus les barres, qui gardent leur place."""
    ops, width, compact = draw(free, left, right)
    P = pills(ops)
    low = [p for p in P if abs(p[1] - min(q[1] for q in P)) < 1.0]
    return round(min(p[0] for p in low) - left, 1), round(width - max(p[2] for p in low), 1), width, compact
for name, left in (("barre d'outils standard", 44), ("barre d'outils large", 200), ("sans barre d'outils", 0)):
    gl, gr, width, compact = margins(1100, left, 0)
    rec(SEC, f"{name} : même marge à gauche (barre d'outils) et à droite (bord de la vue)", abs(gl - gr) < 1.0, (gl, gr))
# barre latérale ouverte : les barres ne bougent pas et ne changent pas de taille (le panneau passe par-dessus)
def rows(free, left, right):
    ops, width, compact = draw(free, left, right)
    return sorted((round(p[0], 1), round(p[1], 1), round(p[2], 1)) for p in pills(ops)), compact
ref = rows(1100 + 445, 105, 0)
same = rows(1100, 105, 445)
rec(SEC, "barre latérale (N) ouverte : les barres restent exactement à la même place", ref == same, (ref[0][:3], same[0][:3]))
# le groupe ne passe jamais sous la barre d'outils ni au-delà du bord de la vue
bad = []
for left in (0, 44, 105, 300):
    for free in range(260, 1400, 37):
        ops, width, compact = draw(free, left, 0)
        P = pills(ops)
        if any(p[0] < left - 0.01 or p[2] > width + 0.01 for p in P):
            bad.append((left, free))
rec(SEC, "rien ne glisse sous la barre d'outils ni hors de la vue", not bad, bad[:6])
# la ligne de commande seule sur sa ligne est centrée de la même façon
ops, width, compact = draw(620, 105, 0)
P = pills(ops)
top = max(P, key=lambda p: p[1])
rec(SEC, "la ligne de commande au-dessus suit le même centre", abs((top[0] - 105) - (width - top[2])) < 1.0, (round(top[0] - 105, 1), round(width - top[2], 1)))
summary()
