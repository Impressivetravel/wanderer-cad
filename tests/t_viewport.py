# Fenêtres d'une mise en page, sur le modèle d'AutoCAD : poignées (4 coins, centre, triangle d'échelle), double-clic pour
# entrer dans une fenêtre et en sortir, commandes MV / MS / PS. Tout est mesuré en millimètres de papier.
import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
exec(open(_os.path.join(_HERE,'prec_lib.py')).read())
import json
le = m.le
BC = bpy.context
SEC = "?"
def chk(name, ok, meas=""): rec(SEC, name, ok, meas)
space.show_gizmo_navigate = False        # (la vue d'essai est petite : sans cela le coin haut droit appartient au gizmo de navigation)


def reset():
    try:
        if m.is_layout(BC.window.scene):
            m.layout_close(BC)
    except Exception:
        pass
    for sc in list(bpy.data.scenes):
        if m.is_layout(sc):
            for o in list(sc.objects): bpy.data.objects.remove(o)
            bpy.data.scenes.remove(sc)
    clear()
    m.layout_on_load()
    m._STATE["active_vp"] = None
    us = BC.scene.unit_settings; us.system = 'METRIC'; us.scale_length = 1.0; us.length_unit = 'METERS'
    return BC.scene


def box(name, sx, sy, sz, loc):
    me = bpy.data.meshes.new(name); bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=bm.verts); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); o.location = loc
    BC.scene.collection.objects.link(o)
    return o


def kids(det, role): return [c for c in det.children if c.get("wd_gen") == role]


def pts_of(objs):
    out = []
    for o in objs:
        M = (o.parent.matrix_basis @ o.matrix_basis) if o.parent else o.matrix_basis
        for sp in o.data.splines:
            out += [tuple((M @ Vector(p.co[:3]))[:2]) for p in sp.points]
    return np.array(out).reshape(-1, 2)


def bb(P): return tuple(round(float(v), 4) for v in (P[:, 0].min(), P[:, 1].min(), P[:, 0].max(), P[:, 1].max()))
def vis(det): BC.view_layer.update(); return bb(pts_of(kids(det, 'vis')))
def frame(det): BC.view_layer.update(); return bb(pts_of([det]))
def rect(det): return tuple(round(v, 4) for v in m.detail_rect(det))


def sheet(scale=100.0, center=(0.0, 0.0, 0.0), at=(20.0, 18.0), size=(30.0, 20.0), view='TOP'):
    """Modèle : une boîte A de 2 x 1 x 0,5 m. Feuille de 100 x 100 mm sans cartouche, une fenêtre."""
    model = reset()
    box("A", 2.0, 1.0, 0.5, (0, 0, 0.25))
    BC.view_layer.update()
    L = m.layout_create(model, "Plan", 'CUSTOM', custom=(100.0, 100.0), margin=2.0, title=False)
    m.layout_open(BC, L)
    d = m.detail_create(L, at[0], at[1], size[0], size[1], view, scale=scale, fit=False)
    with m.quiet():
        d.dessin_detail.center = center
    m.detail_rebuild(d, force=True)
    pick(d)
    return model, L, d


def pick(o):
    for ob in BC.view_layer.objects: ob.select_set(False)
    if o is not None:
        o.select_set(True)
    BC.view_layer.objects.active = o
    BC.view_layer.update()


def send(o, evs):
    r = {'RUNNING_MODAL'}
    for e in evs:
        with contextlib.redirect_stdout(io.StringIO()):
            r = type(o).modal(o, ctx, e)
        if 'FINISHED' in r or 'CANCELLED' in r:
            break
    BC.view_layer.update()
    return r


def grip(corner, at):
    """Presse la poignée `corner` (au point papier `at`). Retourne (commande, résultat de l'appel)."""
    o = make(m.DESSIN_OT_viewport_grip); o.corner = corner
    with contextlib.redirect_stdout(io.StringIO()):
        r = type(o).invoke(o, ctx, ev('LEFTMOUSE', 'PRESS', *scr(*at)))
    return o, r


def close(o):
    try:
        with contextlib.redirect_stdout(io.StringIO()): type(o).cleanup(o, ctx)
    except Exception: pass


move = lambda x, y: ev('MOUSEMOVE', 'NOTHING', *scr(x, y))
press = lambda x, y: ev('LEFTMOUSE', 'PRESS', *scr(x, y))
release = lambda x, y: ev('LEFTMOUSE', 'RELEASE', *scr(x, y))
dbl = lambda x, y: ev('LEFTMOUSE', 'DOUBLE_CLICK', *scr(x, y))
KEY = {'0': 'ZERO', '1': 'ONE', '2': 'TWO', '3': 'THREE', '4': 'FOUR', '5': 'FIVE', '6': 'SIX', '7': 'SEVEN', '8': 'EIGHT', '9': 'NINE', '.': 'PERIOD'}
def typed(text): return [ev('TAB', 'PRESS', *scr(0, 0)) if ch == '\t' else ev(KEY[ch], 'PRESS', *scr(0, 0), unicode=ch, ascii=ch) for ch in text]

# ================= 1. Fonctions des poignées =================
SEC = "poignées"
R0 = (150.0, 100.0, 200.0, 120.0)
chk("les quatre coins d'une fenêtre de 200 x 120 mm centrée en (150, 100)", m.grip_points(R0) == [(50.0, 40.0), (250.0, 40.0), (250.0, 160.0), (50.0, 160.0)], m.grip_points(R0))
chk("le coin opposé à chaque poignée", [m.grip_opposite(R0, i) for i in range(4)] == [(250.0, 160.0), (50.0, 160.0), (50.0, 40.0), (250.0, 40.0)])
chk("tirer le coin haut droit jusqu'en (280, 180) : 230 x 140 mm, le coin bas gauche reste en (50, 40)", near(m.grip_rect(R0, 2, (280.0, 180.0)), (165.0, 110.0, 230.0, 140.0)), m.grip_rect(R0, 2, (280.0, 180.0)))
chk("tirer le coin bas gauche jusqu'en (150, 100) : 100 x 60 mm, le coin haut droit reste en (250, 160)", near(m.grip_rect(R0, 0, (150.0, 100.0)), (200.0, 130.0, 100.0, 60.0)), m.grip_rect(R0, 0, (150.0, 100.0)))
chk("tirer le coin bas droit et le coin haut gauche", near(m.grip_rect(R0, 1, (300.0, 20.0)), (175.0, 90.0, 250.0, 140.0)) and near(m.grip_rect(R0, 3, (30.0, 200.0)), (140.0, 120.0, 220.0, 160.0)))
chk("tiré au-delà du coin opposé, le cadre se retourne", near(m.grip_rect(R0, 2, (20.0, 10.0)), (35.0, 25.0, 30.0, 30.0)), m.grip_rect(R0, 2, (20.0, 10.0)))
r_ = m.grip_rect(R0, 2, (50.5, 40.0))
chk("une fenêtre garde au moins 2 mm de côté", near(r_[2:], (2.0, 2.0)) and near((r_[0] - r_[2] / 2, r_[1] - r_[3] / 2), (50.0, 40.0)), r_)
lay = m.grip_layout(R0, 0.1, True)
chk("avec le Gumball : 4 poignées aux coins, pas de poignée au centre (le Gumball déplace), triangle d'échelle à 20 px du centre",
    lay["corners"] == m.grip_points(R0) and lay["move"] is None and near(lay["scale"], (152.0, 98.0)), (lay["move"], lay["scale"]))
lay = m.grip_layout(R0, 0.1, False)
chk("sans le Gumball : une poignée au centre pour déplacer la fenêtre", lay["move"] == (150.0, 100.0) and near(lay["scale"], (152.0, 98.0)), lay["move"])

# ================= 2. Redimensionner : le modèle ne bouge pas sur la feuille =================
# (la vue d'essai montre 100 x 100 mm : la feuille fait 100 x 100, la fenêtre 30 x 20 en (20, 18), à 1:100)
SEC = "cadre"
RV = (20.0, 18.0, 30.0, 20.0)
A0 = (10.0, 13.0, 30.0, 23.0)            # A (2 x 1 m à 1:100) : 20 x 10 mm autour du centre de la fenêtre
model, L, d = sheet()
dd = d.dessin_detail
chk("au départ : fenêtre de 30 x 20 en (20, 18) ; A (2 x 1 m à 1:100) fait 20 x 10 mm autour du centre", rect(d) == RV and vis(d) == A0, (rect(d), vis(d)))
m.detail_set_rect(d, m.grip_rect(RV, 2, (40.0, 34.0)))
chk("coin haut droit tiré en (40, 34) : le cadre fait 35 x 26, de (5, 8) à (40, 34)", rect(d) == (22.5, 21.0, 35.0, 26.0) and frame(d) == (5.0, 8.0, 40.0, 34.0), (rect(d), frame(d)))
chk("... le dessin du modèle n'a pas bougé sur la feuille (comme une fenêtre d'AutoCAD)", vis(d) == A0, vis(d))
chk("... le point du modèle montré au centre a suivi : (0,25 ; 0,3) m ; l'échelle reste 1:100", near(dd.center, (0.25, 0.3, 0.0), 1e-9) and dd.scale == 100.0, tuple(dd.center))
m.detail_set_rect(d, m.grip_rect(m.detail_rect(d), 0, (20.0, 18.0)))
chk("coin bas gauche tiré en (20, 18) : le cadre coupe le modèle, il n'en reste que la partie dans (20, 18)-(40, 34)",
    frame(d) == (20.0, 18.0, 40.0, 34.0) and vis(d) == (20.0, 18.0, 30.0, 23.0), (frame(d), vis(d)))
m.detail_set_rect(d, m.grip_rect(m.detail_rect(d), 0, (5.0, 8.0)))
chk("coin ramené en (5, 8) : le modèle réapparaît entier, à la même place", frame(d) == (5.0, 8.0, 40.0, 34.0) and vis(d) == A0, vis(d))
# une cote posée sur la fenêtre reste sur le modèle
before = {o.name for o in bpy.data.objects}
new, r_, o_ = run("cotation", [C(10.1, 13.1), C(29.9, 13.1), C(20, 10), 'ESC'])
ldim = next((o for o in new if "dessin_dim" in o.keys()), None)
ltxt = lambda: next((o.data.body for o in L.objects if o.name not in before and o.type == 'FONT' and o.data.body[:1].isdigit()), None)
p0 = json.loads(ldim["dessin_dim"])["points"] if ldim else None
chk("cote posée sur A dans la fenêtre : 20 mm de papier à 1:100 = 2 m (« 200.00 » cm)", ltxt() == "200.00" and near(p0, [(10, 13, 0), (30, 13, 0)], 1e-5), (ltxt(), p0))
pick(d)
m.detail_set_rect(d, m.grip_rect(m.detail_rect(d), 1, (42.0, 6.0)))
m.layout_sync(L)
dimpts = lambda: json.loads(m.layout_dims(L)[0]["dessin_dim"])["points"]      # (la cote peut être reconstruite : on la relit)
p1 = dimpts()
chk("après avoir tiré un autre coin : la cote est restée sur les mêmes points, même valeur", near(p1, p0, 1e-5) and ltxt() == "200.00" and vis(d) == A0, (p1, ltxt()))
c0 = tuple(dd.center)
m.detail_set_rect(d, (m.detail_rect(d)[0] + 2.0, m.detail_rect(d)[1] - 1.0) + m.detail_rect(d)[2:], keep_model=False)
m.layout_sync(L)
p2 = dimpts()
chk("déplacer la fenêtre de (2, -1) : le dessin et la cote la suivent, le cadrage du modèle ne change pas",
    vis(d) == (12.0, 12.0, 32.0, 22.0) and near(p2, [(12, 12, 0), (32, 12, 0)], 1e-5) and tuple(dd.center) == c0 and ltxt() == "200.00", (vis(d), p2))

# ================= 3. La poignée, à la souris =================
SEC = "souris"
model, L, d = sheet()
dd = d.dessin_detail
o, r = grip(2, (35, 28))
chk("presser la poignée du coin haut droit lance la commande ; le point fixe est le coin opposé (5, 8)", 'RUNNING_MODAL' in r and len(o.points) == 1 and near(o.points[0][:2], (5, 8)), (r, [tuple(p) for p in getattr(o, "points", [])]))
r = send(o, [release(35, 28)])
chk("relâcher sans avoir bougé ne fait rien : la poignée reste « chaude » et suit le curseur", 'RUNNING_MODAL' in r and rect(d) == RV, (r, rect(d)))
r = send(o, [move(40, 34)])
info = o.info if hasattr(o, "info") else ""
chk("... l'aperçu donne la nouvelle taille (35 x 26)", "35" in info and "26" in info, info)
r = send(o, [press(40, 34)])
close(o)
chk("un clic en (40, 34) pose le coin : 35 x 26, coin opposé inchangé, modèle à la même place", r == {'FINISHED'} and rect(d) == (22.5, 21.0, 35.0, 26.0) and frame(d) == (5.0, 8.0, 40.0, 34.0)
    and vis(d) == A0, (r, rect(d), vis(d)))
pick(d)
o, r = grip(0, (5, 8))
r = send(o, [move(7, 9), move(8, 10), release(8, 10)])
close(o)
chk("presser le coin bas gauche, glisser, relâcher en (8, 10) : le coin est posé au relâchement", r == {'FINISHED'} and frame(d) == (8.0, 10.0, 40.0, 34.0) and vis(d) == A0, (r, frame(d)))
pick(d)
keep = rect(d)
o, r = grip(1, (40, 10))
r = send(o, [release(40, 10), move(43, 6), ev('ESC', 'PRESS', *scr(43, 6))])
close(o)
chk("Échap pendant qu'on tire une poignée : rien ne change", 'CANCELLED' in r and rect(d) == keep, (r, rect(d)))
pick(d)
o, r = grip(2, (40, 34))
r = send(o, [release(40, 34), move(42, 38)] + typed("30\t20") + [ev('RET', 'PRESS', *scr(42, 38))])
close(o)
chk("taper 30, Tab, 20, Entrée : la fenêtre fait 30 x 20 mm depuis le coin fixe (8, 10)", r == {'FINISHED'} and frame(d) == (8.0, 10.0, 38.0, 30.0), (r, frame(d)))
with m.quiet():
    dd.locked = True
pick(d)
o, r = grip(2, (38, 30))
r = send(o, [move(40, 31), move(42, 32), release(42, 32)])
close(o)
chk("fenêtre verrouillée : on peut toujours tirer ses poignées (le verrou protège l'échelle et le cadrage, comme dans AutoCAD)",
    r == {'FINISHED'} and frame(d) == (8.0, 10.0, 42.0, 32.0) and dd.scale == 100.0 and vis(d) == A0, (r, frame(d)))
with m.quiet():
    dd.locked = False
pick(d)
c0 = tuple(dd.center); r0 = rect(d)
o, r = grip(m.GRIP_MOVE, r0[:2])
r = send(o, [release(*r0[:2]), move(r0[0] + 3, r0[1] + 2), press(r0[0] + 3, r0[1] + 2)])
close(o)
chk("poignée du centre : la fenêtre est déplacée de (3, 2), son contenu la suit, sa taille et son cadrage ne changent pas",
    r == {'FINISHED'} and near(rect(d), (r0[0] + 3, r0[1] + 2, r0[2], r0[3])) and vis(d) == (13.0, 15.0, 33.0, 25.0) and tuple(dd.center) == c0, (r, rect(d), vis(d)))
pick(None)
o, r = grip(2, (0, 0))
chk("aucune fenêtre sélectionnée : la poignée ne lance rien", 'RUNNING_MODAL' not in r, r)
close(o)
pick(d)
chk("la fenêtre active et sélectionnée est celle qui montre ses poignées", m.grip_target(ctx) == d)
box2 = m.detail_create(L, 70.0, 70.0, 20.0, 16.0, 'FRONT', scale=200.0, fit=False)
pick(box2)
chk("... une autre fenêtre devient active : c'est elle qui les montre", m.grip_target(ctx) == box2)
m.layout_close(BC)
chk("... dans le modèle, aucune poignée", m.grip_target(ctx) is None)
m.layout_open(BC, L)

# ================= 4. Double-clic : entrer dans une fenêtre, en sortir =================
SEC = "double-clic"
model, L, d = sheet()
dd = d.dessin_detail
def enter(x, y):
    o = make(m.DESSIN_OT_detail_pan); o.pick = True
    with contextlib.redirect_stdout(io.StringIO()):
        r = type(o).invoke(o, ctx, dbl(x, y))
    return o, r
o, r = enter(44, 44)
chk("double-clic hors de toute fenêtre : rien ne démarre, le clic garde son usage", r == {'CANCELLED', 'PASS_THROUGH'} and m._STATE["active_vp"] is None, r)
o, r = enter(20, 18)
chk("double-clic dans la fenêtre : on y entre (elle devient la fenêtre active, bord épais)", r == {'RUNNING_MODAL'} and m._STATE["active_vp"] == d.name, (r, m._STATE["active_vp"]))
chk("... ses poignées s'effacent pendant qu'on y travaille", m.grip_target(ctx) is None)
r = send(o, [press(20, 18), move(21, 18), release(21, 18)])
chk("glisser de 1 mm vers la droite : le modèle suit (1 mm à 1:100 = 0,1 m), le cadre ne bouge pas",
    'RUNNING_MODAL' in r and near(dd.center, (-0.1, 0.0, 0.0), 1e-9) and vis(d) == (11.0, 13.0, 31.0, 23.0) and rect(d) == RV, (tuple(dd.center), vis(d)))
r = send(o, [ev('WHEELDOWNMOUSE', 'PRESS', *scr(20, 18))])
chk("molette vers le bas : échelle standard suivante (1:200)", dd.scale == 200.0, dd.scale)
r = send(o, [ev('WHEELUPMOUSE', 'PRESS', *scr(20, 18))])
chk("molette vers le haut : retour à 1:100", dd.scale == 100.0, dd.scale)
r = send(o, [dbl(44, 44)])
chk("double-clic hors de la fenêtre : retour à la feuille, les poignées reviennent", r == {'FINISHED'} and m._STATE["active_vp"] is None and m.grip_target(ctx) == d, (r, m._STATE["active_vp"]))
o, r = enter(20, 18)
r = send(o, [ev('ESC', 'PRESS', *scr(20, 18))])
chk("Échap sort aussi de la fenêtre (sans rien changer : la commande est annulée)", r == {'CANCELLED'} and m._STATE["active_vp"] is None, r)
d2 = m.detail_create(L, 30.0, 40.0, 10.0, 8.0, 'TOP', scale=200.0, fit=False)
pick(d)
o, r = enter(20, 18)
r = send(o, [dbl(30, 40)])
chk("double-clic dans une autre fenêtre : c'est elle qui devient active", 'RUNNING_MODAL' in r and m._STATE["active_vp"] == d2.name, m._STATE["active_vp"])
send(o, [release(30, 40), ev('RET', 'PRESS', *scr(0, 0))])
with m.quiet():
    dd.locked = True
c0 = tuple(dd.center)
o, r = enter(20, 18)
r = send(o, [press(20, 18), move(23, 20), release(23, 20), ev('WHEELDOWNMOUSE', 'PRESS', *scr(20, 18))])
chk("fenêtre verrouillée : on y entre, mais ni le panoramique ni la molette ne changent son cadrage ni son échelle",
    tuple(dd.center) == c0 and dd.scale == 100.0 and any("locked" in msg for _lv, msg in o._reports), (tuple(dd.center), dd.scale, o._reports[-1:]))
send(o, [ev('ESC', 'PRESS', *scr(0, 0))])
with m.quiet():
    dd.locked = False
# sur une barre du bas ou un panneau, le double-clic n'entre pas dans la fenêtre
real_hit = m.cmd_hit
sys.modules['wanderer_cad.layout'].cmd_hit = lambda area_, x_, y_: ('view', 'Top')
o, r = enter(20, 18)
sys.modules['wanderer_cad.layout'].cmd_hit = real_hit
chk("double-clic sur une barre du bas (onglet, mode) qui recouvre la fenêtre : il n'y entre pas", r == {'CANCELLED', 'PASS_THROUGH'} and m._STATE["active_vp"] is None, r)
o = make(m.DESSIN_OT_detail_pan)
with contextlib.redirect_stdout(io.StringIO()):
    r = type(o).invoke(o, ctx, ev('NONE', 'NOTHING', *scr(0, 0)))
chk("commande MS (sans double-clic) : on entre dans la fenêtre sélectionnée", r == {'RUNNING_MODAL'} and m._STATE["active_vp"] == d.name, m._STATE["active_vp"])
send(o, [ev('ESC', 'PRESS', *scr(0, 0))])

# ================= 4 bis. Le bord épais de la fenêtre active, dessiné pour de bon =================
SEC = "bord"
try:
    import gpu
    gpu.init()
    GPU_OK = True
except Exception:
    GPU_OK = False
if not GPU_OK:
    print("NOTE : pas de rendu graphique sans fenêtre sur cette machine (gpu.init) : le dessin du bord est sauté.")
else:
    from mathutils import Matrix
    def blue_run(active):
        """Dessine les cadres (vraie fonction, vrai gpu) dans une image de 400 x 400 px pour 100 x 100 mm et compte, sur une
        ligne horizontale au milieu de la fenêtre, les pixels bleus du bord gauche du cadre."""
        m._STATE["active_vp"] = d.name if active else None
        off = gpu.types.GPUOffScreen(400, 400)
        with off.bind():
            fb = gpu.state.active_framebuffer_get()
            fb.clear(color=(1.0, 1.0, 1.0, 1.0))
            with gpu.matrix.push_pop(), gpu.matrix.push_pop_projection():
                gpu.matrix.load_matrix(Matrix.Identity(4))
                gpu.matrix.load_projection_matrix(Matrix(((0.02, 0, 0, -1), (0, 0.02, 0, -1), (0, 0, -0.01, 0), (0, 0, 0, 1))))
                m.layout_draw_cb()
            buf = fb.read_color(0, int(18 * 4), 400, 1, 4, 0, 'FLOAT')
        off.free()
        buf.dimensions = 400 * 4
        px = list(buf)
        m._STATE["active_vp"] = None
        return [x for x in range(400) if px[x * 4 + 2] > 0.6 and px[x * 4] < 0.5 and x < 100]
    pick(d)
    sel = blue_run(False)
    act = blue_run(True)
    pick(None)
    alone = blue_run(True)
    none = blue_run(False)
    pick(d)
    chk("fenêtre sélectionnée : son cadre est tracé en bleu, autour de x = 5 mm (20 px)", 1 <= len(sel) <= 4 and abs(np.mean(sel) - 20) <= 2, sel)
    chk("fenêtre active (on y travaille) : le bord est nettement plus épais, au même endroit", len(act) >= len(sel) + 2 and abs(np.mean(act) - 20) <= 2, (len(sel), len(act)))
    chk("... il est tracé même si la fenêtre n'est pas sélectionnée ; sans fenêtre active ni sélection, rien", len(alone) >= len(sel) + 2 and not none, (len(alone), len(none)))

# ================= 5. Commandes d'AutoCAD =================
SEC = "commandes"
first = lambda t: (m.cmd_suggest(t) or [{"label": None}])[0]["label"]
chk("sur une mise en page : MV et MVIEW dessinent une fenêtre ; « detail » marche toujours", (first("mv"), first("mview"), first("detail"), first("viewport")) == ("Viewport",) * 4,
    (first("mv"), first("mview"), first("detail"), first("viewport")))
chk("... MS entre dans la fenêtre, PS revient au papier", (first("ms"), first("mspace"), first("ps"), first("pspace")) == ("Pan Viewport", "Pan Viewport", "Paper Space", "Paper Space"),
    (first("ms"), first("mspace"), first("ps"), first("pspace")))
chk("... les anciens noms restent acceptés (dpan, detailscale, fitdetail, updatedetails)", (first("dpan"), first("detailscale"), first("fitdetail"), first("updatedetails"))
    == ("Pan Viewport", "Viewport Scale", "Fit Viewport", "Update Viewports"), (first("dpan"), first("detailscale"), first("fitdetail"), first("updatedetails")))
chk("... MODEL revient au modèle ; PAGESETUP, PLOT, REGEN comme dans AutoCAD", (first("model"), first("pagesetup"), first("plot"), first("regen")) == ("Model", "Page Setup", "Export PDF", "Update Viewports"),
    (first("model"), first("pagesetup"), first("plot"), first("regen")))
labels = [e["label"] for e in m.cmd_entries() if e["kind"] in ("tool", "act")]
chk("le mot « Detail » n'apparaît plus dans les noms de commandes ; « Viewport » y est", not [l for l in labels if "Detail" in l] and len([l for l in labels if "Viewport" in l]) >= 5,
    [l for l in labels if "etail" in l or "iewport" in l])
r = bpy.ops.dessin.viewport_paper()
chk("PS sur la feuille : rien à faire (on y est déjà)", r == {'CANCELLED'} and BC.window.scene == L, r)
m.layout_close(BC)
chk("dans le modèle : « ms » lance Match Surface, comme avant", first("ms") == "Match Surface", first("ms"))
r = bpy.ops.dessin.viewport_paper()
chk("PS depuis le modèle : la mise en page s'ouvre", r == {'FINISHED'} and BC.window.scene == L, (r, BC.window.scene.name))
src = open(_os.path.join(_os.path.dirname(_SRC), "layout.py"), encoding="utf-8").read()
ui = [l.strip() for l in src.split("\n") if ("bl_label" in l or "name=" in l or "text=" in l) and ("Detail" in l)]
chk("panneaux et boutons : plus aucun libellé « Detail »", not ui, ui[:4])
menu_calls = []
class Lay:
    def __init__(self): self.__dict__["enabled"] = True
    def __setattr__(self, k, v): self.__dict__[k] = v
    def column(self, *a, **k): return self
    def separator(self, *a, **k): pass
    def label(self, *a, **k): menu_calls.append(("label", k.get("text")))
    def prop(self, data, name, *a, **k): menu_calls.append(("prop", name, k.get("text")))
    def operator(self, idname, *a, **k):
        o_ = NS(text=None); menu_calls.append(("op", idname, k.get("text"), k.get("icon"), o_)); return o_
pick(d)
with m.quiet():
    dd.scale = 50.0
    dd.scale_preset = 'S1_50'
m.DESSIN_MT_viewport_scale.draw(NS(layout=Lay()), ctx)
ops = [c for c in menu_calls if c[0] == "op" and c[1] == "dessin.detail_scale"]
chk("menu du triangle d'échelle : toutes les échelles standard, l'échelle courante (1:50) cochée, puis Custom, Fit et Display Locked",
    [c[2] for c in ops[:len(le.SCALES)]] == [n for _k, n, _d in le.SCALES] and [c[4].text for c in ops[:len(le.SCALES)]] == [n for _k, n, _d in le.SCALES]
    and [c[2] for c in ops if c[3] == 'RADIOBUT_ON'] == ["1:50"] and ops[-1][2] == "Custom..." and ("prop", "locked", "Display Locked") in menu_calls
    and any(c[1] == "dessin.detail_fit" for c in menu_calls if c[0] == "op"), [c[2] for c in ops][:6])
r = bpy.ops.dessin.detail_scale('EXEC_DEFAULT', text="1:25")
chk("choisir 1:25 dans ce menu règle l'échelle de la fenêtre", r == {'FINISHED'} and dd.scale == 25.0, (r, dd.scale))

summary()
