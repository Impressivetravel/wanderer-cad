# Opacité des barres du bas : la pastille des modes (Grid Snap, Ortho...), les onglets de vue et la ligne de commande
# doivent avoir exactement le même fond. Blender coupe le mélange alpha après CHAQUE texte (blf.draw) : tout ce qui était
# dessiné après un texte (pastille des modes après les onglets, info-bulle, ligne de commande après la liste de
# suggestions) était écrit sans mélange, avec son opacité de 0,93 telle quelle -> plus transparent que le reste.
# 1re partie : sur les tracés notés (sans écran), chaque tracé doit être fait mélange alpha actif.
# 2e partie : dessin RÉEL (vrai gpu, vrai blf, rendu logiciel) dans une image hors écran, puis lecture des pixels.
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE, 'harness.py')).read())
exec(open(_os.path.join(_HERE, 'prec_lib.py')).read())
_RENDER_BARS_LIB = True
exec(open(_os.path.join(_HERE, 'render_bars.py')).read())          # install, draw, draw_pixels, gpu_ready
SEC = "?"
def chk(name, ok, meas=""): rec(SEC, name, ok, meas)
ptr = area.as_pointer()
LEFT = RIGHT = 44
install(ui_scale=1.0)
JOIN = staticmethod(lambda context: "dessin.join_tool")
m.DessinBase.active_tool_id = JOIN
m.current_view_name = lambda c: "Perspective"
BG = tuple(CL._cmd_theme()["bg"])
sc = 0.9
def geo(ops): return [o for o in ops if o[0] != "text"]
def unblended(ops): return [(o[0], tuple(round(v, 2) for v in o[2])) for o in geo(ops) if o[4] != 'ALPHA']
def pills(ops):
    out = []
    for op in ops:
        if op[0] == "TRIS" and tuple(op[2]) == BG:
            xs = [p[0] for p in op[1]]; ys = [p[1] for p in op[1]]
            out.append((min(xs), min(ys), max(xs), max(ys)))
    return out
def hits(): return list(m._VBAR["hit"].get(ptr, ()))
def hit(kind, val): return next(h for h in hits() if h[4] == kind and h[5] == val)
mid = lambda h: ((h[0] + h[2]) / 2.0, (h[1] + h[3]) / 2.0)
def typing(text):
    m._CMD["input"] = {"area": ptr, "text": text, "sel": 0, "hist": -1, "tab": None} if text is not None else None

# ================= 1. Tracés notés : tout est dessiné mélange alpha actif =================
SEC = "tracés"
CL.gpu.state.blend_set('ALPHA'); CL.blf.draw(0, "x")
chk("le banc reproduit Blender : après un texte, le mélange alpha est coupé", CL.gpu.state.blend_get() == 'NONE')
ops, width, compact = draw(950, LEFT, RIGHT)
soft = sorted({round(o[2][3], 2) for o in geo(ops) if o[2][3] < 0.999})
chk("950 px libres : les barres ont bien des tracés translucides (fond 0,93 ; séparateur des flèches 0,35)", soft == [0.35, 0.93], soft)
chk("... et chacun de leurs tracés est fait mélange alpha actif, y compris après un texte", len(geo(ops)) >= 20 and not unblended(ops), (len(geo(ops)), unblended(ops)[:4]))
chk("... en sortie le mélange est remis à zéro (rien ne déborde sur le dessin de Blender)", _STATE["blend"] == 'NONE', _STATE["blend"])
keep = CL._blend_on
CL._blend_on = lambda: None                     # l'ancien code : le mélange n'était pas rétabli
ops, width, compact = draw(950, LEFT, RIGHT)
P = pills(ops); bgs = [o for o in geo(ops) if o[0] == "TRIS" and tuple(o[2]) == BG]
chk("sans la correction, l'essai voit le défaut : fonds de la ligne de commande et des vues mélangés, celui des modes non", len(bgs) == 3 and [o[4] for o in bgs] == ['ALPHA', 'ALPHA', 'NONE']
    and any(o[4] == 'NONE' and abs(o[2][3] - 0.35) < 1e-6 for o in geo(ops)), [o[4] for o in bgs])
CL._blend_on = keep
bad, n_geo, levels = [], 0, set()
for on in (False, True):
    m.PREF_DEFAULTS["mode_icons"] = on
    for free in range(1500, 229, -23):
        ops, width, compact = draw(free, LEFT, RIGHT)
        levels.add(compact); n_geo += len(geo(ops))
        if unblended(ops) or _STATE["blend"] != 'NONE':
            bad.append((on, free))
m.PREF_DEFAULTS["mode_icons"] = False
chk("de 1500 à 230 px libres, libellés ou icônes, préférence « icons only » cochée ou non : aucun tracé sans mélange", not bad and levels == {0, 1, 2, 3} and n_geo > 2500, (bad[:6], n_geo))
ops, width, compact = draw(500, LEFT, RIGHT)
for what, target in (("l'icône Ortho", ('mode', 'ortho')), ("la flèche d'OSnap", ('mode', 'osnapmenu')), ("l'onglet F", ('view', 'Front'))):
    ops, width, compact = draw(500, LEFT, RIGHT)
    ops, width, compact = draw(500, LEFT, RIGHT, mouse=mid(hit(*target)), tip=True)
    chk(f"info-bulle sur {what} : quatre fonds (ligne de commande, vues, modes, info-bulle), tous mélangés", len(pills(ops)) == 4 and not unblended(ops), (len(pills(ops)), unblended(ops)[:4]))
typing("re")
ops, width, compact = draw(950, LEFT, RIGHT, height=420)
n_sugg = len([h for h in m._CMD["hit"].get(ptr, ()) if h[4] == 'sugg'])
chk("saisie d'une commande (« re ») : liste de suggestions + ligne de commande + vues + modes, tous mélangés", n_sugg >= 3 and len(pills(ops)) == 4 and not unblended(ops), (n_sugg, len(pills(ops)), unblended(ops)[:4]))
typing(None)
m.DessinBase.active_tool_id = staticmethod(lambda context: None)
ops, width, compact = draw(950, LEFT, RIGHT)
chk("au repos (aucun outil) : tous mélangés", len(pills(ops)) == 3 and not unblended(ops), unblended(ops)[:4])
m.DessinBase.active_tool_id = JOIN

# ================= 2. Dessin réel : pixels lus dans l'image =================
SEC = "pixels"
if not gpu_ready():
    print("NOTE : pas de rendu graphique sans fenêtre sur cette machine (gpu.init) : la mesure des pixels est sautée.")
else:
    import gpu, blf
    off = gpu.types.GPUOffScreen(64, 32)
    with off.bind():
        gpu.state.blend_set('ALPHA'); b0 = gpu.state.blend_get()
        blf.size(0, 12); blf.position(0, 4, 4, 0); blf.color(0, 1, 1, 1, 1); blf.draw(0, "Top")
        b1 = gpu.state.blend_get()
    off.free()
    chk("Blender : gpu.state.blend_get() vaut ALPHA avant un texte et NONE juste après (la cause du défaut)", b0 == 'ALPHA' and b1 == 'NONE', (b0, b1))
    def near(a, b, tol=0.004): return all(abs(x - y) <= tol for x, y in zip(a, b))
    def fond(pixel, p): return pixel(p[0] + 2.5, (p[1] + p[3]) / 2.0)            # un point du fond, entre le bord et le premier bouton
    def floor_alpha(px, w, p, inset):
        """Plus faible opacité à l'intérieur d'une pastille (coins arrondis exclus)."""
        lo = 1.0
        for y in range(int(p[1]) + 2, int(p[3]) - 1):
            row = y * w * 4
            for x in range(int(p[0] + inset), int(p[2] - inset)):
                a = px[row + x * 4 + 3]
                if a < lo: lo = a
        return lo
    R = lambda c: tuple(round(v, 3) for v in c)
    # le défaut, mesuré avec l'ancien dessin
    CL._blend_on = lambda: None
    pixel, ops, w, h, px, end = draw_pixels(950, LEFT, RIGHT)
    P = pills(ops); old = [fond(pixel, p) for p in P]
    sep = hit('mode', 'osnapmenu')
    old_sep = pixel(sep[0], (sep[1] + sep[3]) / 2.0)
    CL._blend_on = keep
    chk("sans la correction : ligne de commande et vues opaques (1,00), pastille des modes à 0,93 -> plus transparente (ce qui a été vu à l'écran)",
        len(P) == 3 and abs(old[0][3] - 1.0) < 0.004 and abs(old[1][3] - 1.0) < 0.004 and abs(old[2][3] - 0.93) < 0.01, [R(c) for c in old])
    chk("... et le trait entre un bouton et sa flèche n'était opaque qu'à 0,35 (un trou d'un pixel)", abs(old_sep[3] - 0.35) < 0.02, R(old_sep))
    # avec la correction
    for free, on, what in ((1250, False, "libellés, sur une ligne"), (950, False, "libellés"), (500, False, "T F P R + et icônes"), (420, False, "icônes sur deux rangées"),
                           (300, False, "vue active et icônes"), (1250, True, "préférence « icons only »")):
        m.PREF_DEFAULTS["mode_icons"] = on
        pixel, ops, w, h, px, end = draw_pixels(free, LEFT, RIGHT)
        P = pills(ops); c = [fond(pixel, p) for p in P]
        chk(f"{free} px libres ({what}) : les trois fonds ont exactement la même couleur et la même opacité, 1,00", len(P) == 3 and near(c[0], c[1]) and near(c[0], c[2])
            and all(abs(x[3] - 1.0) < 0.004 for x in c), [R(x) for x in c])
        lows = [floor_alpha(px, w, p, 12 * sc) for p in P]
        chk("... aucun pixel moins opaque à l'intérieur des trois pastilles (boutons, icônes, flèches, séparateurs compris)", all(a > 0.996 for a in lows), [round(a, 3) for a in lows])
        chk("... le mélange alpha est remis à zéro à la fin du dessin", end == 'NONE', end)
    m.PREF_DEFAULTS["mode_icons"] = False
    pixel, ops, w, h, px, end = draw_pixels(950, LEFT, RIGHT)
    sep = hit('mode', 'osnapmenu')
    chk("le trait entre OSnap et sa flèche est maintenant opaque", abs(pixel(sep[0], (sep[1] + sep[3]) / 2.0)[3] - 1.0) < 0.004, R(pixel(sep[0], (sep[1] + sep[3]) / 2.0)))
    draw(500, LEFT, RIGHT)
    pixel, ops, w, h, px, end = draw_pixels(500, LEFT, RIGHT, mouse=mid(hit('mode', 'ortho')), tip=True)
    P = pills(ops); c = [fond(pixel, p) for p in P]
    chk("info-bulle d'une icône : son fond a la même couleur et la même opacité que les trois barres", len(P) == 4 and all(near(c[0], x) for x in c[1:]) and abs(c[3][3] - 1.0) < 0.004, [R(x) for x in c])
    typing("re")
    pixel, ops, w, h, px, end = draw_pixels(950, LEFT, RIGHT, height=420)
    P = pills(ops); c = [fond(pixel, p) for p in P]
    chk("saisie d'une commande : la ligne de commande a le même fond que sa liste de suggestions et que les deux autres barres", len(P) == 4 and all(near(c[0], x) for x in c[1:])
        and all(abs(x[3] - 1.0) < 0.004 for x in c), [R(x) for x in c])
    typing(None)
    CL._blend_on = lambda: None
    typing("re")
    pixel, ops, w, h, px, end = draw_pixels(950, LEFT, RIGHT, height=420)
    P = pills(ops); c = [fond(pixel, p) for p in P]
    typing(None)
    CL._blend_on = keep
    chk("(sans la correction, la ligne de commande devenait elle aussi plus transparente pendant la saisie : 0,93)", len(P) == 4 and abs(c[0][3] - 1.0) < 0.004 and abs(c[1][3] - 0.93) < 0.01, [R(x) for x in c])

summary()
