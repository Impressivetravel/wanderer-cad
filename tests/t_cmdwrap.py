# Ligne de commande : une invite trop longue pour la barre passe à la ligne au lieu d'être coupée par « … ».
# Signalé sur Fillet Edge : la fin du texte ne s'affichait pas, quelle que soit la taille de la barre (100, 150, 200 %).
# Le dessin est le vrai (tracés notés) ; l'invite est celle que Fillet Edge écrit vraiment.
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE, 'harness.py')).read())
exec(open(_os.path.join(_HERE, 'prec_lib.py')).read())
_RENDER_BARS_LIB = True
exec(open(_os.path.join(_HERE, 'render_bars.py')).read())
import blf
BC = bpy.context
SEC = "?"
def chk(name, ok, meas=""): rec(SEC, name, ok, meas)
ptr = area.as_pointer()
LEFT = 44
install(ui_scale=1.0)
m.DessinBase.active_tool_id = staticmethod(lambda context: None)
m.current_view_name = lambda c: "Perspective"
TH = CL._cmd_theme()
BG = tuple(TH["bg"])
def pills(ops):
    out = []
    for op in ops:
        if op[0] == "TRIS" and tuple(op[2]) == BG:
            xs = [p[0] for p in op[1]]; ys = [p[1] for p in op[1]]
            out.append((min(xs), min(ys), max(xs), max(ys)))
    return out
def texts(ops): return [o for o in ops if o[0] == "text"]
def in_pill(o, p): return p[0] - 0.5 <= o[1] <= p[2] + 0.5 and p[1] - 0.5 <= o[2] <= p[3] + 0.5
def cmd_texts(ops):
    p = pills(ops)[0]
    return [o for o in texts(ops) if in_pill(o, p)]
def lines_of(ops):
    """Textes de la ligne de commande regroupés par ligne (de haut en bas), chaque ligne de gauche à droite."""
    rows = {}
    for o in cmd_texts(ops):
        rows.setdefault(round(o[2], 1), []).append(o)
    return [[t[3] for t in sorted(r, key=lambda o: o[1])] for _y, r in sorted(rows.items(), reverse=True)]
def right_edge(o):
    blf.size(0, o[4])
    if o[6]: blf.enable(0, blf.BOLD) if hasattr(blf, "BOLD") else None
    w = blf.dimensions(0, o[3])[0]
    if o[6] and hasattr(blf, "BOLD"): blf.disable(0, blf.BOLD)
    return o[1] + w
PREF0 = m.pref
def set_size(pct):                      # réglage « Command bar size » des préférences
    m.pref = (lambda name, _o=PREF0: pct if name == "cmd_size" else _o(name))

# l'invite que Fillet Edge écrit vraiment (étape de sélection des arêtes)
fe = make(m.DESSIN_OT_fillet_edge)
fe.phase = 'pick'
fe.total_selected = lambda: 0
body = type(fe).prompt(fe)
PROMPT = f"Fillet Edge : {body}   |   S: snap ON   |   Esc: cancel   Enter/Space: quit"
WORDS = ["Fillet Edge", "click or drag a box to select the edges, then Enter", "box to the right: inside", "to the left: touching", "Ctrl/Cmd: deselect",
         "click: the whole edge", "Ctrl+click: one segment", "click a selected edge: remove it"]
def flat(ops): return " ".join(" ".join(l) for l in lines_of(ops))
def has_all(ops):
    f = " ".join(flat(ops).split())
    return [w for w in WORDS if w not in f]

SEC = "invite longue"
chk("l'invite de Fillet Edge contient bien le texte signalé", "box to the right: inside, to the left: touching, Ctrl/Cmd: deselect" in PROMPT and "click a selected edge: remove it" in PROMPT, PROMPT[:80])
for pct in (100, 150, 200):
    set_size(pct)
    m._CMD["prompt"][ptr] = PROMPT
    for free in (1400, 1100, 900):
        ops, width, compact = draw(free, LEFT, 0)
        P = pills(ops)
        L = lines_of(ops)
        miss = has_all(ops)
        tag = f"barre à {pct} %, vue de {free} px"
        chk(f"{tag} : tout le texte de l'invite est écrit, plus aucun « … »", not miss and not any("…" in t for l in L for t in l), (miss, [t for l in L for t in l if "…" in t]))
        chk(f"... sur plusieurs lignes, la première commence par le nom de la commande", len(L) >= 3 and L[0][0] == "Fillet Edge", [len(l) for l in L])
        ct = cmd_texts(ops)
        over = [o[3] for o in ct if right_edge(o) > P[0][2] - 1.0 or o[1] < P[0][0] + 1.0]
        chk(f"... aucun texte ne sort de la pastille ; elle reste dans la vue, sans toucher les onglets ni les modes", not over and P[0][0] >= LEFT - 0.01 and P[0][2] <= width + 0.01
            and not any(a[0] < b[2] - 0.01 and b[0] < a[2] - 0.01 and a[1] < b[3] - 0.01 and b[1] < a[3] - 0.01 for i, a in enumerate(P) for b in P[i + 1:]), (over, P[0]))
    chip_keys = [h[5] for h in m._CMD["hit"].get(ptr, ()) if h[4] == 'key']
    chk(f"barre à {pct} % : les touches (Esc, Enter/Space) restent cliquables, sous le texte", "Esc" in chip_keys and any(k.startswith("Enter") for k in chip_keys), chip_keys)
set_size(100)

SEC = "invite courte"
m._CMD["prompt"][ptr] = "Polyline : next point   |   S: snap ON   |   Esc: cancel   Enter/Space: quit"
ops, width, compact = draw(1400, LEFT, 0)
L = lines_of(ops)
chk("une invite courte reste sur une seule ligne, les touches à sa suite", len(L) == 1 and L[0][0] == "Polyline" and "Esc" in L[0], L)
h_short = pills(ops)[0][3] - pills(ops)[0][1]
m._CMD["prompt"][ptr] = PROMPT
ops, width, compact = draw(1400, LEFT, 0)
h_long = pills(ops)[0][3] - pills(ops)[0][1]
chk("... et la barre ne grandit que pour une invite longue", h_long > h_short * 1.8, (round(h_short, 1), round(h_long, 1)))

SEC = "découpe"
m._cmd_font(11 * 0.9)
W = lambda t: blf.dimensions(0, t)[0]
gap = 8 * 0.9
items = [("Fillet Edge", "acc", True), ("click or drag a box to select the edges, then Enter", "acc", True),
         ("box to the right: inside, to the left: touching, Ctrl/Cmd: deselect, click a selected edge: remove it", "dim", False), ("0 edges", "fg", False)]
one = m.cmd_wrap_row(items, 5000, gap)
chk("assez de place : une seule ligne, rien n'est changé", len(one) == 1 and [i[0] for i in one[0]] == [i[0] for i in items])
w2 = m.cmd_wrap_row(items, 520, gap)
chk("520 px : un élément qui ne tient plus sur la ligne passe entier à la suivante (il n'est pas coupé)", [i[0] for i in w2[0]] == ["Fillet Edge", "click or drag a box to select the edges, then Enter"]
    and [i[0] for i in w2[1]] == [items[2][0], "0 edges"] and len(w2) == 2, [[i[0][:20] for i in l] for l in w2])
w2 = m.cmd_wrap_row(items, 380, gap)
chk("380 px : un élément plus long qu'une ligne commence à la ligne suivante et s'y poursuit, coupé entre deux mots", len(w2) == 3
    and [i[0] for i in w2[0]] == ["Fillet Edge", "click or drag a box to select the edges, then Enter"]
    and " ".join(i[0] for l in w2[1:] for i in l if i[1] == "dim") == items[2][0]
    and not w2[1][-1][0].endswith(("…", " ")) and w2[2][-1][0] == "0 edges", [[i[0] for i in l] for l in w2[1:]])
chk("... aucune ligne ne dépasse la largeur", all(sum(i[3] for i in l) + gap * (len(l) - 1) <= 380 + 1e-6 for l in w2), [round(sum(i[3] for i in l) + gap * (len(l) - 1)) for l in w2])
w3 = m.cmd_wrap_row(items, 150, gap)
chk("150 px : au plus 4 lignes ; la dernière finit par « … »", len(w3) == m.CMD_TEXT_LINES == 4 and w3[-1][-1][0].endswith("…")
    and all(sum(i[3] for i in l) + gap * (len(l) - 1) <= 150 + 1e-6 for l in w3), [[i[0] for i in l] for l in w3])
w4 = m.cmd_wrap_row([("Supercalifragilisticexpialidocious", "fg", False)], 80, gap)
chk("un mot plus large que la barre : coupé par « … », sans boucle sans fin", len(w4) == 1 and w4[0][0][0].endswith("…") and w4[0][0][3] <= 80 + 1e-6, w4)
chk("rien à écrire : une ligne vide", m.cmd_wrap_row([], 300, gap) == [[]])
summary()
