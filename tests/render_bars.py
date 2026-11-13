# Rendu des barres du bas (onglets de vue, ligne de commande, boutons de mode) SANS écran : le vrai code de dessin de
# l'add-on est exécuté, ses tracés (triangles, traits, textes) sont notés puis écrits en SVG. Sert à voir, à plusieurs
# largeurs de vue, ce que Blender dessinerait : python3 tests/render_bars.py <dossier de sortie> [largeurs libres...]
# Ce n'est pas une suite d'essais (elle ne s'appelle pas t_*.py) ; t_snapmodes.py vérifie les mêmes tracés par des mesures.
# draw_pixels() fait le dessin RÉEL (vrai gpu, vrai blf) dans une image hors écran et rend ses pixels : c'est ce que
# t_barblend.py mesure (opacité des pastilles). Il faut un rendu graphique, même logiciel (gpu.init) ; sinon gpu_ready() est faux.
import os as _os, sys as _sys
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
if 'm' not in globals():                    # (une suite d'essais qui inclut ce fichier a déjà chargé l'add-on)
    exec(open(_os.path.join(_HERE, 'harness.py')).read())
import time
import blf as _blf
from xml.sax.saxutils import escape as _esc
CL = _sys.modules['wanderer_cad.command_line']
OPS = []
_REAL = dict(bpy=CL.bpy, blf=CL.blf, gpu=CL.gpu, get_shader=CL.get_shader, batch_for_shader=CL.batch_for_shader)     # les vrais modules, pour draw_pixels


class _Blf:
    BOLD = getattr(_blf, "BOLD", 0)
    def __init__(self): self.sz = 11.0; self.col = (1, 1, 1, 1); self.pos = (0, 0); self.bold = False
    def size(self, fid, sz, *a): self.sz = sz; return _blf.size(fid, sz, *a)
    def dimensions(self, *a): return _blf.dimensions(*a)
    def color(self, fid, r, g, b, a=1.0): self.col = (r, g, b, a)
    def position(self, fid, x, y, z): self.pos = (x, y)
    def draw(self, fid, text):
        OPS.append(("text", self.pos[0], self.pos[1], text, self.sz, self.col, self.bold))
        _STATE["blend"] = 'NONE'            # comme Blender : le mélange alpha est coupé après chaque texte (mesuré par t_barblend)
    def enable(self, fid, flag): self.bold = True
    def disable(self, fid, flag): self.bold = False


class _Shader:
    def __init__(self, name): self.name = name; self.col = (1, 1, 1, 1); self.lw = None
    def bind(self): pass
    def uniform_float(self, name, val):
        if name == "color": self.col = tuple(val)
        elif name == "lineWidth": self.lw = float(val)


class _Batch:
    def __init__(self, sh, kind, pos): self.sh, self.kind, self.pos = sh, kind, [tuple(p)[:2] for p in pos]
    def draw(self, sh): OPS.append((self.kind, self.pos, sh.col, sh.lw if sh.lw is not None else _STATE["lw"], _STATE["blend"]))     # (dernier : mélange alpha au moment du tracé)


_STATE = {"lw": 1.0, "blend": 'NONE', "gpu": None}


class _Bpy:
    context = ctx
    def __getattr__(self, k): return getattr(bpy, k)


def install(ui_scale=1.0, theme=None):
    """Remplace, dans le module de la barre, l'écran par des enregistreurs. theme : couleurs de la barre (sinon le thème
    par défaut de Blender)."""
    CL.bpy = _Bpy(); CL.blf = _Blf()
    CL.gpu = NS(state=NS(blend_set=lambda mode: _STATE.__setitem__("blend", mode), blend_get=lambda: _STATE["blend"],
                         line_width_set=lambda w: _STATE.__setitem__("lw", float(w)),
                         viewport_get=lambda: (0, 0, region.width, region.height)),
                shader=NS(from_builtin=lambda name: _Shader(name)))
    CL.get_shader = lambda kind: _Shader("UNIFORM_COLOR")
    CL.batch_for_shader = lambda sh, kind, data: _Batch(sh, kind, data["pos"])
    real_prefs = bpy.context.preferences
    ctx._o['preferences'] = NS(system=NS(ui_scale=ui_scale, dpi=72, use_region_overlap=True), themes=real_prefs.themes, addons=real_prefs.addons)
    if theme:
        CL._cmd_theme = lambda: dict(theme)


def draw(free, left=44, right=44, height=1000, mouse=None, tip=False):
    """Dessine les barres pour une vue dont la place libre (entre barre d'outils et barre latérale) vaut `free` pixels.
    Retourne (tracés, largeur de la région, état compact de la vue)."""
    ptr = area.as_pointer()
    region.width = left + free + right; region.height = height; area.width = region.width
    area.regions[:] = [region, NS(type='TOOLS', width=left, x=0, y=0, height=height), NS(type='UI', width=right, x=left + free, y=0, height=height)]
    m._CMD["mouse"].pop(ptr, None)
    if mouse is not None:
        m._CMD["mouse"][ptr] = mouse
        m._CMD.setdefault("mouse_t", {})[ptr] = time.monotonic() - (CL.TIP_DELAY + 0.05 if tip else 0.0)
    for _ in range(3):                      # les pastilles se calent les unes sur les autres en un ou deux dessins
        del OPS[:]
        _STATE["blend"] = 'NONE'
        CL.cmd_bar_cb(); CL.views_bar_cb()
    return list(OPS), region.width, int(m._GROUP["compact"].get(ptr) or 0)


def gpu_ready():
    """Vrai si un rendu graphique est disponible sans fenêtre (gpu.init, rendu logiciel compris)."""
    if _STATE["gpu"] is None:
        try:
            import gpu as _gpu
            _gpu.init()
            _STATE["gpu"] = True
        except Exception:
            _STATE["gpu"] = False
    return _STATE["gpu"]


def draw_pixels(free, left=44, right=44, height=160, mouse=None, tip=False):
    """Dessin RÉEL des barres (vrai gpu, vrai blf) dans une image hors écran vidée (transparente).
    Retourne (pixel(x, y) -> (r, v, b, opacité), tracés notés, largeur, hauteur, pixels, mélange alpha en fin de dessin)."""
    import gpu as _gpu
    from mathutils import Matrix
    stub = dict(blf=CL.blf, gpu=CL.gpu, get_shader=CL.get_shader, batch_for_shader=CL.batch_for_shader)
    ops, width, compact = draw(free, left, right, height, mouse, tip)        # (cale les pastilles, note les tracés)
    w, h = int(width), int(height)
    for k in stub:
        setattr(CL, k, _REAL[k])
    try:
        off = _gpu.types.GPUOffScreen(w, h)
        with off.bind():
            fb = _gpu.state.active_framebuffer_get()
            fb.clear(color=(0.0, 0.0, 0.0, 0.0))
            with _gpu.matrix.push_pop(), _gpu.matrix.push_pop_projection():
                _gpu.matrix.load_matrix(Matrix.Identity(4))
                _gpu.matrix.load_projection_matrix(Matrix(((2.0 / w, 0, 0, -1), (0, 2.0 / h, 0, -1), (0, 0, 1, 0), (0, 0, 0, 1))))   # un pixel = une unité
                _gpu.state.blend_set('NONE')
                CL.cmd_bar_cb(); CL.views_bar_cb()
            end = _gpu.state.blend_get()
            buf = fb.read_color(0, 0, w, h, 4, 0, 'FLOAT')
        off.free()
    finally:
        for k, v in stub.items():
            setattr(CL, k, v)
    buf.dimensions = h * w * 4
    px = list(buf)

    def pixel(x, y):
        i = (min(max(int(y), 0), h - 1) * w + min(max(int(x), 0), w - 1)) * 4
        return tuple(px[i:i + 4])
    return pixel, ops, w, h, px, end


def _hull(pts):
    pts = sorted(set((round(x, 3), round(y, 3)) for x, y in pts))
    if len(pts) < 3:
        return pts
    def cross(o, a, b): return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, up = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0: lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(up) >= 2 and cross(up[-2], up[-1], p) <= 0: up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]


def _rgba(c):
    a = c[3] if len(c) > 3 else 1.0
    return f"rgb({round(c[0] * 255)},{round(c[1] * 255)},{round(c[2] * 255)})", a


def svg(ops, width, free, left=44, right=44, pad_top=34, label=True):
    """SVG de la bande basse de la vue : fond, tracés de l'add-on dans leur ordre, puis les deux panneaux par-dessus
    (comme dans Blender, où la barre d'outils et la barre latérale recouvrent la vue)."""
    top = 0.0
    for op in ops:
        if op[0] == "text": top = max(top, op[2] + op[4])
        else: top = max(top, max(p[1] for p in op[1]))
    H = round(top + pad_top)
    Y = lambda y: H - y
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{H}" viewBox="0 0 {width} {H}" font-family="Inter, DejaVu Sans, sans-serif">',
           '<defs><linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#55647b"/><stop offset="1" stop-color="#343e4e"/></linearGradient></defs>',
           f'<rect width="{width}" height="{H}" fill="url(#bg)"/>']
    for gx in range(0, int(width), 46):
        out.append(f'<line x1="{gx}" y1="0" x2="{gx}" y2="{H}" stroke="#fff" stroke-opacity=".045"/>')
    for gy in range(0, H, 46):
        out.append(f'<line x1="0" y1="{gy}" x2="{width}" y2="{gy}" stroke="#fff" stroke-opacity=".045"/>')
    for op in ops:
        if op[0] == "TRIS":
            col, a = _rgba(op[2])
            pts = " ".join(f"{x:.2f},{Y(y):.2f}" for x, y in _hull(op[1]))
            out.append(f'<polygon points="{pts}" fill="{col}" fill-opacity="{a:.3f}"/>')
        elif op[0] in ("LINES", "LINE_STRIP"):
            col, a = _rgba(op[2])
            if op[0] == "LINES":
                d = " ".join(f"M{a_[0]:.2f} {Y(a_[1]):.2f}L{b_[0]:.2f} {Y(b_[1]):.2f}" for a_, b_ in zip(op[1][0::2], op[1][1::2]))
            else:
                d = "M" + "L".join(f"{x:.2f} {Y(y):.2f}" for x, y in op[1])
            out.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-opacity="{a:.3f}" stroke-width="{op[3]:.2f}" stroke-linecap="round" stroke-linejoin="round"/>')
        elif op[0] == "text":
            _k, x, y, text, size, c, bold = op
            col, a = _rgba(c)
            weight = ' font-weight="650"' if bold else ''
            out.append(f'<text x="{x:.2f}" y="{Y(y):.2f}" font-size="{size:.2f}" fill="{col}" fill-opacity="{a:.3f}"{weight}'
                       f' xml:space="preserve">{_esc(text)}</text>')
    for x0, w in ((0, left), (width - right, right)):
        out.append(f'<rect x="{x0}" y="0" width="{w}" height="{H}" fill="#181d26" fill-opacity=".9"/>')
        for k in range(int(H // 22)):
            out.append(f'<rect x="{x0 + 7}" y="{8 + k * 22}" width="{w - 14}" height="16" rx="3" fill="{"#4a76be" if x0 else "#ffffff"}" fill-opacity="{".55" if x0 else ".10"}"/>')
    out.append(f'<line x1="{left}" y1="0" x2="{left}" y2="{H}" stroke="#fff" stroke-opacity=".3" stroke-dasharray="4 4"/>')
    out.append(f'<line x1="{width - right}" y1="0" x2="{width - right}" y2="{H}" stroke="#fff" stroke-opacity=".3" stroke-dasharray="4 4"/>')
    if label:
        out.append(f'<text x="{left + free / 2:.1f}" y="15" font-size="10.5" fill="#fff" fill-opacity=".6" text-anchor="middle">{free} px libres</text>')
    out.append('</svg>')
    return "\n".join(out), H


if __name__ == "__main__" and not globals().get("_RENDER_BARS_LIB"):
    args = [a for a in _sys.argv[1:] if not a.startswith("-")]
    outdir = args[0] if args else "."
    widths = [int(a) for a in args[1:]] or [700, 500, 380, 240]
    _os.makedirs(outdir, exist_ok=True)
    install()
    for free in widths:
        ops, width, compact = draw(free)
        doc, _h = svg(ops, width, free)
        path = _os.path.join(outdir, f"bars_{free}.svg")
        open(path, "w", encoding="utf-8").write(doc)
        print(f"{free} px libres : état compact {compact} -> {path}")
