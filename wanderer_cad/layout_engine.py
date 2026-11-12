"""Wanderer CAD : Layout — moteur des vues de détail (projection, lignes cachées, découpe) et export vectoriel (PDF, SVG, DXF)."""

import math
import time
import zlib

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree


# --------------------------------------------------------------------------
# Formats de papier et échelles
# --------------------------------------------------------------------------

# (identifiant, nom affiché, largeur, hauteur) en millimètres, côté long d'abord (paysage)
PAPERS = (
    ('A0', "A0", 1189.0, 841.0), ('A1', "A1", 841.0, 594.0), ('A2', "A2", 594.0, 420.0), ('A3', "A3", 420.0, 297.0),
    ('A4', "A4", 297.0, 210.0), ('A5', "A5", 210.0, 148.0),
    ('LETTER', "Letter (8.5 x 11 in)", 279.4, 215.9), ('LEGAL', "Legal (8.5 x 14 in)", 355.6, 215.9),
    ('TABLOID', "Tabloid / ANSI B (11 x 17 in)", 431.8, 279.4), ('ANSI_C', "ANSI C (17 x 22 in)", 558.8, 431.8),
    ('ANSI_D', "ANSI D (22 x 34 in)", 863.6, 558.8), ('ANSI_E', "ANSI E (34 x 44 in)", 1117.6, 863.6),
    ('ARCH_A', "Arch A (9 x 12 in)", 304.8, 228.6), ('ARCH_B', "Arch B (12 x 18 in)", 457.2, 304.8),
    ('ARCH_C', "Arch C (18 x 24 in)", 609.6, 457.2), ('ARCH_D', "Arch D (24 x 36 in)", 914.4, 609.6),
    ('ARCH_E', "Arch E (36 x 48 in)", 1219.2, 914.4),
)
PAPER_SIZE = {k: (w, h) for k, _n, w, h in PAPERS}

# (identifiant, nom affiché, dénominateur) : 1 mm de papier = `dénominateur` mm du modèle
SCALES = (
    ('S10_1', "10:1", 0.1), ('S5_1', "5:1", 0.2), ('S2_1', "2:1", 0.5),
    ('S1_1', "1:1", 1.0), ('S1_2', "1:2", 2.0), ('S1_5', "1:5", 5.0), ('S1_10', "1:10", 10.0), ('S1_20', "1:20", 20.0),
    ('S1_25', "1:25", 25.0), ('S1_50', "1:50", 50.0), ('S1_100', "1:100", 100.0), ('S1_200', "1:200", 200.0),
    ('S1_250', "1:250", 250.0), ('S1_500', "1:500", 500.0), ('S1_1000', "1:1000", 1000.0),
)
SCALE_DEN = {k: d for k, _n, d in SCALES}


def scale_preset(den):
    """Identifiant de l'échelle normalisée qui vaut `den`, sinon 'CUSTOM'."""
    for k, _n, d in SCALES:
        if abs(d - den) <= 1e-9 * max(1.0, d):
            return k
    return 'CUSTOM'


def fmt_scale(den):
    """« 1:20 », « 2:1 », « 1:2.5 »."""
    if den <= 0.0:
        return "?"

    def num(x):
        return f"{x:.4f}".rstrip("0").rstrip(".")
    if den >= 1.0:
        return "1:" + num(den)
    inv = 1.0 / den
    if abs(inv - round(inv)) < 1e-6:
        return f"{int(round(inv))}:1"
    return "1:" + num(den)


def parse_scale(text):
    """« 1:50 », « 1/50 », « 50 », « 2:1 », « 0.5 » -> dénominateur (None si le texte n'est pas une échelle)."""
    t = (text or "").strip().replace(",", ".").replace(" ", "")
    if not t:
        return None
    try:
        for sep in (":", "/"):
            if sep in t:
                a, b = t.split(sep, 1)
                a, b = float(a), float(b)
                if a <= 0.0 or b <= 0.0:
                    return None
                return b / a
        v = float(t)
        return v if v > 0.0 else None
    except ValueError:
        return None


# --------------------------------------------------------------------------
# Lecture du modèle
# --------------------------------------------------------------------------

ANNOT_KEYS = ("dessin_cotation", "dessin_cotation_texte", "dessin_text", "dessin_note", "dessin_hatch")
GEOM_TYPES = {'MESH', 'CURVE', 'FONT', 'SURFACE', 'META'}
WIRE_RESOLUTION = 32          # segments par arc de Bézier des courbes filaires (cercles lisses à l'impression)


class Item:
    """Un objet du modèle prêt à être projeté.
    kind : 'SOLID' (faces : arêtes caractéristiques, occulte), 'WIRE' (courbes, arêtes libres), 'ANNOT' (cotes, textes, hachures)."""
    __slots__ = ("kind", "name", "color", "V", "E", "cnt", "f0", "f1", "N", "PC", "sharp", "T", "loops", "text")

    def __init__(self, kind, name, color):
        self.kind, self.name, self.color = kind, name, color
        self.V = self.E = self.cnt = self.f0 = self.f1 = self.N = self.PC = self.sharp = self.T = None
        self.loops = []          # annotations : contours des faces (aplats exportés), T = leurs triangles (aplats affichés)
        self.text = False        # annotation de type texte (dessinée par-dessus les traits)


def is_annotation(obj):
    try:
        if obj.type == 'FONT':
            return True
        keys = obj.keys()
        return any(k in keys for k in ANNOT_KEYS)
    except (ReferenceError, AttributeError):
        return False


def scene_depsgraph(scene):
    """Graphe d'évaluation d'une scène, même si ce n'est pas celle de la fenêtre."""
    try:
        if bpy.context.scene == scene:
            return bpy.context.evaluated_depsgraph_get()
    except (AttributeError, RuntimeError):
        pass
    try:
        vl = scene.view_layers[0]
        vl.update()                   # (crée le graphe d'une scène qui n'a pas encore été affichée, fichier tout juste ouvert)
        return vl.depsgraph
    except (AttributeError, IndexError, RuntimeError):
        return None


def hidden_collections(names):
    """Noms des collections masquées dans une vue : celles citées et toutes leurs sous-collections."""
    out = set()
    for n in names:
        col = bpy.data.collections.get(n)
        if col is None:
            continue
        out.add(col.name)
        for c in col.children_recursive:
            out.add(c.name)
    return out


def _in_hidden(obj, hidden):
    if not hidden:
        return False
    try:
        return any(c.name in hidden for c in obj.users_collection)
    except (ReferenceError, AttributeError):
        return False


def _visible(obj, view_layer):
    try:
        if obj.hide_viewport:
            return False
        return bool(obj.visible_get(view_layer=view_layer))
    except (ReferenceError, AttributeError, RuntimeError, TypeError):
        return True


def _world(co, mat):
    M = np.array(mat, dtype=np.float64)
    return co @ M[:3, :3].T + M[:3, 3]


def _mesh_arrays(me):
    """(sommets locaux (N,3), arêtes (M,2)) d'un maillage."""
    nv = len(me.vertices)
    co = np.empty(nv * 3, dtype=np.float32)
    me.vertices.foreach_get("co", co)
    ne = len(me.edges)
    ed = np.empty(ne * 2, dtype=np.int32)
    me.edges.foreach_get("vertices", ed)
    return co.reshape(-1, 3).astype(np.float64), ed.reshape(-1, 2)


def _edge_faces(me):
    """Pour chaque arête : nombre de faces qui la portent, et les deux premières (indices de polygones, -1 sinon)."""
    ne, npoly, nloop = len(me.edges), len(me.polygons), len(me.loops)
    cnt = np.zeros(ne, dtype=np.int32)
    f0 = np.full(ne, -1, dtype=np.int32)
    f1 = np.full(ne, -1, dtype=np.int32)
    if not npoly or not nloop:
        return cnt, f0, f1
    le = np.empty(nloop, dtype=np.int32)
    me.loops.foreach_get("edge_index", le)
    tot = np.empty(npoly, dtype=np.int32)
    me.polygons.foreach_get("loop_total", tot)
    start = np.empty(npoly, dtype=np.int32)
    me.polygons.foreach_get("loop_start", start)
    lp = np.empty(nloop, dtype=np.int32)
    order_p = np.argsort(start, kind='stable')
    lp[:] = np.repeat(order_p, tot[order_p])
    cnt = np.bincount(le, minlength=ne).astype(np.int32)
    order = np.argsort(le, kind='stable')
    le_s, lp_s = le[order], lp[order]
    first = np.searchsorted(le_s, np.arange(ne), side='left')
    has1 = cnt >= 1
    f0[has1] = lp_s[first[has1]]
    has2 = cnt >= 2
    f1[has2] = lp_s[first[has2] + 1]
    return cnt, f0, f1


def _closed_loops(edges):
    """Décompose un ensemble d'arêtes de bord [(a, b)] en boucles fermées [[sommets]]."""
    adj = {}
    for k, (a, b) in enumerate(edges):
        adj.setdefault(a, []).append((k, b))
        adj.setdefault(b, []).append((k, a))
    used = [False] * len(edges)
    loops = []
    for k0, (a, b) in enumerate(edges):
        if used[k0]:
            continue
        used[k0] = True
        loop, cur = [a, b], b
        while cur != a:
            nxt = None
            for k, other in adj[cur]:
                if not used[k]:
                    nxt = (k, other)
                    break
            if nxt is None:
                break
            used[nxt[0]] = True
            cur = nxt[1]
            loop.append(cur)
        if cur == a and len(loop) > 3:
            loops.append(loop[:-1])
    return loops


def _mesh_tris(me):
    me.calc_loop_triangles()
    nt = len(me.loop_triangles)
    T = np.empty(nt * 3, dtype=np.int32)
    me.loop_triangles.foreach_get("vertices", T)
    return T.reshape(-1, 3)


def _fill_item(item, V, E, cnt, T):
    """Remplit un Item d'annotation : arêtes libres (traits), contours des faces (aplats) et leurs triangles."""
    loose = cnt == 0
    item.V = V
    item.E = E[loose]
    item.T = T
    border = E[cnt == 1]
    if len(border):
        for loop in _closed_loops([(int(a), int(b)) for a, b in border]):
            item.loops.append(V[np.array(loop, dtype=np.int64)])


def _curve_is_wire(obj):
    cu = obj.data
    try:
        if "dessin_cotation" in obj.keys():
            return True          # cote : son épaisseur éventuelle est un trait, pas un volume
        if cu.extrude != 0.0 or cu.bevel_depth != 0.0 or cu.bevel_object is not None:
            return False
        if cu.dimensions == '2D' and cu.fill_mode != 'NONE':
            return not any(s.use_cyclic_u for s in cu.splines)
        return True
    except (AttributeError, ReferenceError):
        return True


def _temp_mesh(data, setup):
    """Maillage d'une copie réglée (setup) d'une courbe ou d'un texte : (sommets locaux, arêtes, nombre de faces par arête)."""
    c2 = data.copy()
    tmp = None
    me = None
    try:
        setup(c2)
        tmp = bpy.data.objects.new("_wd_layout_tmp", c2)
        me = bpy.data.meshes.new_from_object(tmp)
        V, E = _mesh_arrays(me)
        cnt, _f0, _f1 = _edge_faces(me)
        return V, E, cnt, _mesh_tris(me)
    finally:
        if me is not None:
            bpy.data.meshes.remove(me)
        if tmp is not None:
            bpy.data.objects.remove(tmp)
        bpy.data.curves.remove(c2)


def _setup_wire(c):
    c.bevel_depth = 0.0
    c.extrude = 0.0
    c.bevel_object = None
    c.taper_object = None
    c.dimensions = '3D'
    c.resolution_u = max(int(c.resolution_u), WIRE_RESOLUTION)


def _setup_font(c):
    c.extrude = 0.0
    c.bevel_depth = 0.0
    c.offset = 0.0
    c.fill_mode = 'BOTH'


def collect_model(scene, hidden_names=(), annotations=True):
    """Objets visibles de `scene`, sous forme d'Items en coordonnées du monde.
    hidden_names : collections (calques) masquées dans cette vue seulement."""
    dg = scene_depsgraph(scene)
    if dg is None:
        return []
    try:
        vl = scene.view_layers[0]
    except IndexError:
        vl = None
    hidden = hidden_collections(hidden_names)
    items, later, seen = [], [], set()
    for inst in dg.object_instances:
        ob = inst.object
        if ob.type not in GEOM_TYPES:
            continue
        orig = ob.original
        if inst.is_instance:
            par = inst.parent
            par_o = par.original if par is not None else None
            if par_o is None:
                continue
            try:
                real = par_o.type == 'EMPTY' or any(m.type == 'NODES' for m in par_o.modifiers)
            except (AttributeError, ReferenceError):
                real = False
            if not real:
                continue          # géométrie évaluée d'une courbe ou d'un texte, déjà lue avec l'objet lui-même
            shown = par_o
        else:
            shown = orig
        if not _visible(shown, vl) or _in_hidden(shown, hidden) or _in_hidden(orig, hidden):
            continue
        if orig.get("wd_gen") or orig.get("wd_layout_gen"):
            continue
        ann = is_annotation(orig)
        if ann and not annotations:
            continue
        color = tuple(float(c) for c in orig.color[:3])
        mat = inst.matrix_world.copy()
        key = (orig.name, tuple(round(x, 9) for row in mat for x in row))
        if key in seen:
            continue              # même objet au même endroit (géométrie évaluée d'un texte dans un bloc) : une seule fois
        seen.add(key)
        if orig.type == 'FONT' and not len(orig.modifiers):
            later.append(('FONT', orig, mat, color))
            continue
        if orig.type == 'CURVE' and not len(orig.modifiers) and _curve_is_wire(orig):
            later.append(('ANNOT' if ann else 'WIRE', orig, mat, color))
            continue
        try:
            me = ob.to_mesh()
        except (RuntimeError, AttributeError, TypeError):
            continue
        if me is None:
            continue
        try:
            if not len(me.edges):
                continue
            V, E = _mesh_arrays(me)
            V = _world(V, mat)
            cnt, f0, f1 = _edge_faces(me)
            npoly = len(me.polygons)
            if ann:
                it = Item('ANNOT', orig.name, color)
                _fill_item(it, V, E, cnt, _mesh_tris(me) if npoly else None)
                items.append(it)
                continue
            if not npoly:
                it = Item('WIRE', orig.name, color)
                it.V, it.E = V, E
                items.append(it)
                continue
            it = Item('SOLID', orig.name, color)
            it.V, it.E, it.cnt, it.f0, it.f1 = V, E, cnt, f0, f1
            nrm = np.empty(npoly * 3, dtype=np.float32)
            me.polygons.foreach_get("normal", nrm)
            M3 = np.array(mat, dtype=np.float64)[:3, :3]
            try:
                N = nrm.reshape(-1, 3).astype(np.float64) @ np.linalg.inv(M3)
            except np.linalg.LinAlgError:
                N = nrm.reshape(-1, 3).astype(np.float64)
            ln = np.linalg.norm(N, axis=1)
            ln[ln < 1e-20] = 1.0
            it.N = N / ln[:, None]
            ctr = np.empty(npoly * 3, dtype=np.float32)
            me.polygons.foreach_get("center", ctr)
            it.PC = _world(ctr.reshape(-1, 3).astype(np.float64), mat)
            sharp = np.zeros(len(E), dtype=bool)
            attr = me.attributes.get("sharp_edge")
            if attr is not None and len(attr.data) == len(E):
                attr.data.foreach_get("value", sharp)
            it.sharp = sharp
            it.T = _mesh_tris(me)
            items.append(it)
        finally:
            ob.to_mesh_clear()
    # courbes filaires et textes : relus sur une copie (résolution d'impression, sans épaisseur), hors de la boucle du graphe
    for kind, orig, mat, color in later:
        try:
            if kind == 'FONT':
                V, E, cnt, T = _temp_mesh(orig.data, _setup_font)
                it = Item('ANNOT', orig.name, color)
                it.text = True
                _fill_item(it, _world(V, mat), E, cnt, T)
            else:
                V, E, cnt, _T = _temp_mesh(orig.data, _setup_wire)
                it = Item(kind, orig.name, color)
                it.V, it.E = _world(V, mat), E
            items.append(it)
        except (RuntimeError, AttributeError, TypeError, ReferenceError):
            continue
    return items


# --------------------------------------------------------------------------
# Projection
# --------------------------------------------------------------------------

class Projector:
    """Vue d'un détail : projection parallèle (échelle exacte) ou perspective (échelle exacte dans le plan de la cible)."""

    def __init__(self, quat, persp=False, target=(0.0, 0.0, 0.0), dist=10.0):
        self.right = quat @ Vector((1.0, 0.0, 0.0))
        self.up = quat @ Vector((0.0, 1.0, 0.0))
        self.look = quat @ Vector((0.0, 0.0, -1.0))
        self.persp = bool(persp)
        self.dist = max(float(dist), 1e-6)
        self.cam = Vector(target) - self.look * self.dist
        self.r = np.array(self.right, dtype=np.float64)
        self.u = np.array(self.up, dtype=np.float64)
        self.l = np.array(self.look, dtype=np.float64)
        self.c = np.array(self.cam, dtype=np.float64)
        self.near = self.dist * 1e-3

    def uv(self, P):
        """Points du monde (N,3) -> coordonnées de vue (N,2), en unités du modèle."""
        P = np.asarray(P, dtype=np.float64).reshape(-1, 3)
        if not self.persp:
            return np.stack((P @ self.r, P @ self.u), axis=1)
        d = P - self.c
        z = np.maximum(d @ self.l, self.near)
        s = self.dist / z
        return np.stack(((d @ self.r) * s, (d @ self.u) * s), axis=1)

    def front(self, N, PC):
        """Faces tournées vers l'observateur."""
        if not self.persp:
            return (N @ self.l) < 0.0
        return np.einsum('ij,ij->i', N, PC - self.c) < 0.0

    def clip_near(self, A, B):
        """Perspective : segments (A, B) limités à ce qui est devant la caméra."""
        if not self.persp:
            return A, B
        za, zb = (A - self.c) @ self.l, (B - self.c) @ self.l
        keep = (za > self.near) | (zb > self.near)
        A, B, za, zb = A[keep], B[keep], za[keep], zb[keep]
        if not len(A):
            return A, B
        dz = zb - za
        safe = np.where(np.abs(dz) < 1e-20, 1.0, dz)
        t = (self.near - za) / safe
        ca = za < self.near
        cb = zb < self.near
        A2 = np.where(ca[:, None], A + (B - A) * t[:, None], A)
        B2 = np.where(cb[:, None], A + (B - A) * t[:, None], B)
        return A2, B2


class Projection:
    """Résultat d'une projection, en coordonnées de vue (unités du modèle), avant mise à l'échelle et découpe."""

    def __init__(self):
        self.lines = []       # [(rôle, couleur, segments (M,4))]   rôle : 'vis', 'hid', 'ann'
        self.fills = []       # [(couleur, [boucles (K,2)], triangles (T,3,2), est un texte)]
        self.bbox = None      # (u0, v0, u1, v1) de tout ce qui est projeté
        self.edges = 0        # arêtes testées (lignes cachées)
        self.seconds = 0.0


def _split_visibility(A, B, L2, step, cast, want_hidden):
    """Découpe chaque arête 3D (A[i], B[i]) en parties visibles / cachées. cast(p) -> True si p est visible."""
    va, vb, ha, hb = [], [], [], []
    for i in range(len(A)):
        a, b = Vector(A[i]), Vector(B[i])
        n = max(2, min(40, int(L2[i] / step) + 2))
        ts = [j / (n - 1) for j in range(n)]
        vs = [cast(a.lerp(b, t)) for t in ts]
        cuts, states = [0.0], [vs[0]]
        for j in range(n - 1):
            if vs[j] != vs[j + 1]:
                lo, hi, s_lo = ts[j], ts[j + 1], vs[j]
                for _k in range(14):
                    mid = (lo + hi) * 0.5
                    if cast(a.lerp(b, mid)) == s_lo:
                        lo = mid
                    else:
                        hi = mid
                cuts.append((lo + hi) * 0.5)
                states.append(vs[j + 1])
        cuts.append(1.0)
        for k, state in enumerate(states):
            t0, t1 = cuts[k], cuts[k + 1]
            if t1 - t0 <= 1e-9:
                continue
            if state:
                va.append(a.lerp(b, t0))
                vb.append(a.lerp(b, t1))
            elif want_hidden:
                ha.append(a.lerp(b, t0))
                hb.append(a.lerp(b, t1))

    def arr(lst):
        return np.array([tuple(p) for p in lst], dtype=np.float64).reshape(-1, 3)
    return arr(va), arr(vb), arr(ha), arr(hb)


def project_model(items, proj, display='HIDDEN', sharp_deg=25.0, tangent=False):
    """Projette les Items selon `proj`.
    display : 'WIREFRAME' (toutes les arêtes caractéristiques), 'HIDDEN' (visibles seulement), 'HIDDEN_DASHED' (visibles + cachées)."""
    t_start = time.monotonic()
    out = Projection()
    hidden_mode = display in ('HIDDEN', 'HIDDEN_DASHED')
    want_hidden = display == 'HIDDEN_DASHED'
    cos_sharp = math.cos(math.radians(sharp_deg))
    cos_tan = math.cos(math.radians(1.0))
    # occultation : toutes les faces des solides
    bvh = None
    allV = [it.V for it in items if it.V is not None and len(it.V)]
    if allV:
        P = np.concatenate(allV)
        lo, hi = P.min(axis=0), P.max(axis=0)
        diag = float(np.linalg.norm(hi - lo)) or 1.0
    else:
        diag = 1.0
    if hidden_mode:
        verts, tris, base = [], [], 0
        for it in items:
            if it.kind == 'SOLID' and it.T is not None and len(it.T):
                verts.append(it.V)
                tris.append(it.T + base)
                base += len(it.V)
        if verts:
            bvh = BVHTree.FromPolygons(np.concatenate(verts).tolist(), np.concatenate(tris).tolist(), epsilon=0.0)
    eps = max(diag * 1e-5, 1e-9)
    far = diag * 4.0 + 1.0
    toward = -proj.look
    cam = proj.cam

    if proj.persp:
        def cast(p):
            d = cam - p
            ln = d.length
            if ln <= eps * 2.0:
                return True
            d = d / ln
            return bvh.ray_cast(p + d * eps, d, ln - eps)[0] is None
    else:
        def cast(p):
            return bvh.ray_cast(p + toward * eps, toward, far)[0] is None

    groups = {}          # (rôle, couleur) -> [segments (M,4)]
    boxes = []

    def add(role, color, A, B):
        if not len(A):
            return
        ua, ub = proj.uv(A), proj.uv(B)
        S = np.concatenate((ua, ub), axis=1)
        groups.setdefault((role, color), []).append(S)
        boxes.append((min(S[:, 0].min(), S[:, 2].min()), min(S[:, 1].min(), S[:, 3].min()),
                      max(S[:, 0].max(), S[:, 2].max()), max(S[:, 1].max(), S[:, 3].max())))

    for it in items:
        if it.kind == 'ANNOT':
            if it.E is not None and len(it.E):
                A, B = proj.clip_near(it.V[it.E[:, 0]], it.V[it.E[:, 1]])
                add('ann', it.color, A, B)
            loops = []
            area = span = 0.0
            for L in it.loops:
                if proj.persp and np.any((L - proj.c) @ proj.l <= proj.near):
                    continue
                uv = proj.uv(L)
                x, y = uv[:, 0], uv[:, 1]
                area += abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))) * 0.5
                span = max(span, float(x.max() - x.min()), float(y.max() - y.min()))
                loops.append(uv)
            if loops and area <= span * span * 1e-4:
                loops = []                  # aplat vu par la tranche (texte à plat dans une vue de face) : rien à remplir
            for uv in loops:
                boxes.append((uv[:, 0].min(), uv[:, 1].min(), uv[:, 0].max(), uv[:, 1].max()))
            if loops:
                tris = np.zeros((0, 3, 2))
                if it.T is not None and len(it.T):
                    P3 = it.V[it.T.reshape(-1)]
                    if not proj.persp or not np.any((P3 - proj.c) @ proj.l <= proj.near):
                        tris = proj.uv(P3).reshape(-1, 3, 2)
                out.fills.append((it.color, loops, tris, it.text))
            continue
        if it.E is None or not len(it.E):
            continue
        if it.kind == 'SOLID':
            keep = it.cnt != 2
            two = np.nonzero(it.cnt == 2)[0]
            if len(two):
                f0, f1 = it.f0[two], it.f1[two]
                front = proj.front(it.N, it.PC)
                dot = np.einsum('ij,ij->i', it.N[f0], it.N[f1])
                feat = (front[f0] != front[f1]) | (dot <= cos_sharp) | it.sharp[two]
                if tangent:
                    feat |= dot <= cos_tan
                keep[two] = feat
            E = it.E[keep]
        else:
            E = it.E
        if not len(E):
            continue
        A, B = proj.clip_near(it.V[E[:, 0]], it.V[E[:, 1]])
        if not len(A):
            continue
        d2 = proj.uv(B) - proj.uv(A)
        L2 = np.hypot(d2[:, 0], d2[:, 1])
        ok = L2 > diag * 1e-7                     # arêtes dans l'axe de la vue : un point, rien à tracer
        A, B, L2 = A[ok], B[ok], L2[ok]
        if not len(A):
            continue
        if not hidden_mode or bvh is None:
            add('vis', it.color, A, B)
            continue
        out.edges += len(A)
        va, vb, ha, hb = _split_visibility(A, B, L2, diag * 0.02, cast, want_hidden)
        add('vis', it.color, va, vb)
        if want_hidden:
            add('hid', it.color, ha, hb)
    for (role, color), parts in groups.items():
        out.lines.append((role, color, np.concatenate(parts)))
    if boxes:
        bx = np.array(boxes)
        out.bbox = (float(bx[:, 0].min()), float(bx[:, 1].min()), float(bx[:, 2].max()), float(bx[:, 3].max()))
    out.seconds = time.monotonic() - t_start
    return out


def model_extent(items, proj):
    """Emprise (u0, v0, u1, v1) des Items dans la vue `proj`, ou None."""
    lo = hi = None
    for it in items:
        pts = [it.V] if it.V is not None and len(it.V) else []
        pts += list(it.loops)
        for P in pts:
            if proj.persp:
                P = P[(P - proj.c) @ proj.l > proj.near]
                if not len(P):
                    continue
            uv = proj.uv(P)
            a, b = uv.min(axis=0), uv.max(axis=0)
            lo = a if lo is None else np.minimum(lo, a)
            hi = b if hi is None else np.maximum(hi, b)
    if lo is None:
        return None
    return float(lo[0]), float(lo[1]), float(hi[0]), float(hi[1])


# --------------------------------------------------------------------------
# Mise à l'échelle, découpe au cadre, chaînage
# --------------------------------------------------------------------------

def clip_segments(S, x0, y0, x1, y1):
    """Liang-Barsky vectorisé : segments (M,4) découpés au rectangle."""
    if not len(S):
        return S
    ax, ay, bx, by = S[:, 0], S[:, 1], S[:, 2], S[:, 3]
    dx, dy = bx - ax, by - ay
    t0 = np.zeros(len(S))
    t1 = np.ones(len(S))
    ok = np.ones(len(S), dtype=bool)
    for p, q in ((-dx, ax - x0), (dx, x1 - ax), (-dy, ay - y0), (dy, y1 - ay)):
        par = np.abs(p) < 1e-12
        ok &= ~(par & (q < 0.0))
        t = np.divide(q, p, out=np.zeros_like(q), where=~par)
        neg = (p < 0.0) & ~par
        pos = (p > 0.0) & ~par
        t0 = np.where(neg, np.maximum(t0, t), t0)
        t1 = np.where(pos, np.minimum(t1, t), t1)
    ok &= (t1 - t0) > 1e-9
    out = np.stack((ax + dx * t0, ay + dy * t0, ax + dx * t1, ay + dy * t1), axis=1)
    return out[ok]


def clip_loop(L, x0, y0, x1, y1):
    """Sutherland-Hodgman : boucle fermée (K,2) découpée au rectangle (liste de points, vide si rien ne reste)."""
    pts = [(float(p[0]), float(p[1])) for p in L]
    for axis, lim, keep_ge in ((0, x0, True), (0, x1, False), (1, y0, True), (1, y1, False)):
        if not pts:
            return []
        res = []
        prev = pts[-1]
        pin = (prev[axis] >= lim) if keep_ge else (prev[axis] <= lim)
        for cur in pts:
            cin = (cur[axis] >= lim) if keep_ge else (cur[axis] <= lim)
            if cin != pin:
                d = cur[axis] - prev[axis]
                t = (lim - prev[axis]) / d if abs(d) > 1e-20 else 0.0
                res.append((prev[0] + (cur[0] - prev[0]) * t, prev[1] + (cur[1] - prev[1]) * t))
            if cin:
                res.append(cur)
            prev, pin = cur, cin
        pts = res
    return pts if len(pts) >= 3 else []


def merge_segments(S, tol=1e-3):
    """Chaîne des segments (M,4) en polylignes : [(points (K,2), fermé)]."""
    if not len(S):
        return []
    pts = S.reshape(-1, 2)
    keys = np.round(pts / tol).astype(np.int64)
    uniq, first, inv = np.unique(keys, axis=0, return_index=True, return_inverse=True)
    inv = inv.reshape(-1)
    P = pts[first]
    ids = inv.reshape(-1, 2)
    ids = ids[ids[:, 0] != ids[:, 1]]
    if not len(ids):
        return []
    ids = np.unique(np.sort(ids, axis=1), axis=0)
    adj = {}
    for k, (a, b) in enumerate(ids.tolist()):
        adj.setdefault(a, []).append((k, b))
        adj.setdefault(b, []).append((k, a))
    used = [False] * len(ids)
    out = []

    def walk(start, k, nxt):
        path = [start, nxt]
        used[k] = True
        cur = nxt
        while cur != start and len(adj[cur]) == 2:
            (k1, o1), (k2, o2) = adj[cur]
            if not used[k1]:
                used[k1] = True
                cur = o1
            elif not used[k2]:
                used[k2] = True
                cur = o2
            else:
                break
            path.append(cur)
        return path

    for v, lst in adj.items():            # d'abord les chemins qui partent d'une extrémité ou d'un nœud
        if len(lst) != 2:
            for k, o in lst:
                if not used[k]:
                    out.append((P[np.array(walk(v, k, o), dtype=np.int64)], False))
    for v, lst in adj.items():            # puis les boucles
        for k, o in lst:
            if not used[k]:
                path = walk(v, k, o)
                closed = path[0] == path[-1] and len(path) > 3
                if closed:
                    path = path[:-1]
                out.append((P[np.array(path, dtype=np.int64)], closed))
    return out


def dash_paths(paths, on=3.0, off=1.5):
    """Découpe des polylignes en tirets (pour l'affichage des lignes cachées)."""
    out = []
    for P, closed in paths:
        seq = [tuple(p) for p in P]
        if closed:
            seq.append(seq[0])
        cur, drawing, left = [seq[0]], True, on
        for a, b in zip(seq, seq[1:]):
            ln = math.hypot(b[0] - a[0], b[1] - a[1])
            if ln <= 1e-12:
                continue
            t = 0.0
            while ln - t > left:
                t += left
                p = (a[0] + (b[0] - a[0]) * t / ln, a[1] + (b[1] - a[1]) * t / ln)
                if drawing:
                    cur.append(p)
                    if len(cur) >= 2:
                        out.append((np.array(cur), False))
                    cur = []
                else:
                    cur = [p]
                drawing = not drawing
                left = on if drawing else off
            left -= ln - t
            if drawing:
                cur.append(b)
        if drawing and len(cur) >= 2:
            out.append((np.array(cur), False))
    return out


def _line_bins(S, a_tol=2e-5, r_tol=2e-3):
    """Regroupe des segments (M,4) par droite porteuse : {clé: (direction, normale, décalage, [(t0, t1)])}."""
    bins = {}
    if not len(S):
        return bins
    dx, dy = S[:, 2] - S[:, 0], S[:, 3] - S[:, 1]
    ln = np.hypot(dx, dy)
    ok = ln > 1e-9
    flip = (dx < -1e-12) | ((np.abs(dx) <= 1e-12) & (dy < 0.0))
    sgn = np.where(flip, -1.0, 1.0)
    safe = np.where(ok, ln, 1.0)
    ux, uy = dx * sgn / safe, dy * sgn / safe
    ang = np.arctan2(uy, ux)
    rho = -uy * S[:, 0] + ux * S[:, 1]
    ta = ux * S[:, 0] + uy * S[:, 1]
    tb = ux * S[:, 2] + uy * S[:, 3]
    ka = np.round(ang / a_tol).astype(np.int64)
    kr = np.round(rho / r_tol).astype(np.int64)
    for i in np.nonzero(ok)[0].tolist():
        key = (int(ka[i]), int(kr[i]))
        b = bins.get(key)
        if b is None:
            b = bins[key] = ((float(ux[i]), float(uy[i])), float(rho[i]), [])
        t0, t1 = float(ta[i]), float(tb[i])
        b[2].append((t0, t1) if t0 <= t1 else (t1, t0))
    return bins


def _union(iv, tol=1e-6):
    iv = sorted(iv)
    out = [list(iv[0])]
    for a, b in iv[1:]:
        if a <= out[-1][1] + tol:
            if b > out[-1][1]:
                out[-1][1] = b
        else:
            out.append([a, b])
    return out


def _subtract(iv, cut, tol=1e-6):
    """Intervalles `iv` (unis) privés des intervalles `cut` (unis)."""
    out = []
    for a, b in iv:
        cur = a
        for c, d in cut:
            if d <= cur + tol:
                continue
            if c >= b - tol:
                break
            if c > cur + tol:
                out.append([cur, min(c, b)])
            cur = max(cur, d)
            if cur >= b - tol:
                break
        if cur < b - tol:
            out.append([cur, b])
    return out


def _bins_to_segments(bins):
    rows = []
    for (u, rho, iv) in bins.values():
        nx, ny = -u[1], u[0]
        for a, b in iv:
            if b - a > 1e-9:
                rows.append((u[0] * a + nx * rho, u[1] * a + ny * rho, u[0] * b + nx * rho, u[1] * b + ny * rho))
    return np.array(rows, dtype=np.float64).reshape(-1, 4)


def clean_overlaps(vis, hid):
    """Règle de dessin technique : les traits visibles superposés n'en font qu'un, et un trait caché qui coïncide avec un
    trait visible n'est pas tracé. vis, hid : listes de tableaux de segments (M,4) ; retourne les mêmes listes nettoyées."""
    cover = {}
    out_vis = []
    for S in vis:
        bins = _line_bins(S)
        for key, (u, rho, iv) in bins.items():
            merged = _union(iv)
            bins[key] = (u, rho, merged)
            c = cover.get(key)
            if c is None:
                cover[key] = list(merged)
            else:
                cover[key] = _union([tuple(x) for x in c] + [tuple(x) for x in merged])
        out_vis.append(_bins_to_segments(bins))
    out_hid = []
    for S in hid:
        bins = _line_bins(S)
        for key, (u, rho, iv) in bins.items():
            merged = _union(iv)
            cut = []
            for da in (-1, 0, 1):               # droites voisines à la tolérance près
                for dr in (-1, 0, 1):
                    c = cover.get((key[0] + da, key[1] + dr))
                    if c:
                        cut += [tuple(x) for x in c]
            if cut:
                merged = _subtract(merged, _union(cut))
            bins[key] = (u, rho, merged)
        out_hid.append(_bins_to_segments(bins))
    return out_vis, out_hid


def to_paper(projection, cu, cv, k, w, h):
    """Projection -> géométrie du détail en millimètres, origine au centre du cadre, découpée au cadre (w x h).
    (cu, cv) : point de la vue placé au centre ; k : mm de papier par unité du modèle.
    Retourne {"lines": [(rôle, couleur, [(points, fermé)])],
              "fills": [(couleur, [boucles], [polygones convexes], est un texte)]}."""
    x0, y0, x1, y1 = -w / 2.0, -h / 2.0, w / 2.0, h / 2.0
    off = np.array((cu, cv, cu, cv))
    clipped = [(role, color, clip_segments((S - off) * k, x0, y0, x1, y1)) for role, color, S in projection.lines]
    vis = [c for c in clipped if c[0] == 'vis']
    hid = [c for c in clipped if c[0] == 'hid']
    cv_, ch_ = clean_overlaps([c[2] for c in vis], [c[2] for c in hid])
    lines = []
    for (role, color, _S), S2 in list(zip(vis, cv_)) + list(zip(hid, ch_)):
        paths = merge_segments(S2)
        if paths:
            lines.append((role, color, paths))
    for role, color, S in clipped:
        if role in ('vis', 'hid'):
            continue
        paths = merge_segments(S)
        if paths:
            lines.append((role, color, paths))
    o2 = np.array((cu, cv))
    fills = []
    for color, loops, tris, is_text in projection.fills:
        res = []
        inside = True
        for L in loops:
            P = (L - o2) * k
            if P[:, 0].min() >= x0 and P[:, 0].max() <= x1 and P[:, 1].min() >= y0 and P[:, 1].max() <= y1:
                res.append(P)
            elif P[:, 0].max() < x0 or P[:, 0].min() > x1 or P[:, 1].max() < y0 or P[:, 1].min() > y1:
                inside = False
            else:
                inside = False
                c = clip_loop(P, x0, y0, x1, y1)
                if c:
                    res.append(np.array(c))
        if not res:
            continue
        polys = []
        if len(tris):
            T = (tris - o2) * k
            if inside:
                polys = [t for t in T]
            else:
                for t in T:
                    c = clip_loop(t, x0, y0, x1, y1)
                    if c:
                        polys.append(np.array(c))
        fills.append((color, res, polys, is_text))
    return {"lines": lines, "fills": fills}


# --------------------------------------------------------------------------
# Export vectoriel
# --------------------------------------------------------------------------
# Une page : {"name": str, "w": mm, "h": mm, "ents": [entités]}, origine en bas à gauche, y vers le haut.
# Entités : ('L', [(points, fermé)], épaisseur mm, (r, g, b), tirets (on, off) ou None, calque)
#           ('F', [boucles], (r, g, b), calque)                     aplat, règle pair / impair

def _pdf_text(s):
    """Chaîne PDF en UTF-16 (accents compris)."""
    return b"<FEFF" + s.encode("utf-16-be").hex().upper().encode("ascii") + b">"


def _pdf_page_stream(page):
    k = 72.0 / 25.4
    out = ["%.6f 0 0 %.6f 0 0 cm" % (k, k), "1 J 1 j"]
    for e in page["ents"]:
        if e[0] == 'L':
            _t, paths, width, color, dash, _layer = e
            out.append("%.3f %.3f %.3f RG %.3f w %s d" % (color[0], color[1], color[2], max(width, 0.01),
                                                          ("[%.2f %.2f] 0" % dash) if dash else "[] 0"))
            for P, closed in paths:
                if len(P) < 2:
                    continue
                seg = ["%.3f %.3f m" % (P[0][0], P[0][1])]
                seg += ["%.3f %.3f l" % (p[0], p[1]) for p in P[1:]]
                seg.append("h S" if closed else "S")
                out.append(" ".join(seg))
        elif e[0] == 'F':
            _t, loops, color, _layer = e
            out.append("%.3f %.3f %.3f rg" % (color[0], color[1], color[2]))
            parts = []
            for L in loops:
                if len(L) < 3:
                    continue
                seg = ["%.3f %.3f m" % (L[0][0], L[0][1])]
                seg += ["%.3f %.3f l" % (p[0], p[1]) for p in L[1:]]
                seg.append("h")
                parts.append(" ".join(seg))
            if parts:
                out.append("\n".join(parts) + "\nf*")
    return "\n".join(out).encode("ascii")


def write_pdf(path, pages, title="", producer="Wanderer CAD"):
    """PDF vectoriel, une page par mise en page, au format exact du papier (imprimer à 100 % donne l'échelle)."""
    objs = []

    def add(b):
        objs.append(b)
        return len(objs)
    cat = add(b"")
    pages_id = add(b"")
    kpt = 72.0 / 25.4
    kids = []
    for pg in pages:
        comp = zlib.compress(_pdf_page_stream(pg), 9)
        cid = add(b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(comp) + comp + b"\nendstream")
        pid = add(("<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %.3f %.3f] /Contents %d 0 R /Resources << >> >>"
                   % (pages_id, pg["w"] * kpt, pg["h"] * kpt, cid)).encode("ascii"))
        kids.append(pid)
    stamp = time.strftime("D:%Y%m%d%H%M%S")
    info = add(b"<< /Title " + _pdf_text(title or "Layout") + b" /Producer " + _pdf_text(producer)
               + b" /Creator " + _pdf_text(producer) + b" /CreationDate (" + stamp.encode("ascii") + b") >>")
    objs[cat - 1] = ("<< /Type /Catalog /Pages %d 0 R >>" % pages_id).encode("ascii")
    objs[pages_id - 1] = ("<< /Type /Pages /Count %d /Kids [%s] >>"
                          % (len(kids), " ".join("%d 0 R" % k for k in kids))).encode("ascii")
    buf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offs = []
    for i, b in enumerate(objs):
        offs.append(len(buf))
        buf += b"%d 0 obj\n" % (i + 1) + b + b"\nendobj\n"
    xref = len(buf)
    buf += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for o in offs:
        buf += b"%010d 00000 n \n" % o
    buf += b"trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, cat, info, xref)
    with open(path, "wb") as f:
        f.write(bytes(buf))


def _hex(color):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(c * 255.0)))) for c in color[:3])


def _xml(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def write_svg(path, page):
    """SVG en millimètres (une mise en page)."""
    w, h = page["w"], page["h"]
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<svg xmlns="http://www.w3.org/2000/svg" width="%.3fmm" height="%.3fmm" viewBox="0 0 %.3f %.3f">' % (w, h, w, h),
           '<title>%s</title>' % _xml(page.get("name", "Layout")),
           '<g transform="translate(0,%.3f) scale(1,-1)" stroke-linecap="round" stroke-linejoin="round">' % h]
    for e in page["ents"]:
        if e[0] == 'L':
            _t, paths, width, color, dash, layer = e
            d = []
            for P, closed in paths:
                if len(P) < 2:
                    continue
                d.append("M" + " L".join("%.3f %.3f" % (p[0], p[1]) for p in P) + (" Z" if closed else ""))
            if not d:
                continue
            da = (' stroke-dasharray="%.2f %.2f"' % dash) if dash else ""
            out.append('<path class="%s" fill="none" stroke="%s" stroke-width="%.3f"%s d="%s"/>'
                       % (_xml(layer), _hex(color), max(width, 0.01), da, " ".join(d)))
        elif e[0] == 'F':
            _t, loops, color, layer = e
            d = ["M" + " L".join("%.3f %.3f" % (p[0], p[1]) for p in L) + " Z" for L in loops if len(L) >= 3]
            if d:
                out.append('<path class="%s" fill="%s" fill-rule="evenodd" stroke="none" d="%s"/>'
                           % (_xml(layer), _hex(color), " ".join(d)))
    out.append('</g>')
    out.append('</svg>')
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out) + "\n")


DXF_ACI = ((1, (1.0, 0.0, 0.0)), (2, (1.0, 1.0, 0.0)), (3, (0.0, 1.0, 0.0)), (4, (0.0, 1.0, 1.0)), (5, (0.0, 0.0, 1.0)),
           (6, (1.0, 0.0, 1.0)), (8, (0.5, 0.5, 0.5)), (9, (0.75, 0.75, 0.75)))


def _aci(color):
    """Couleur AutoCAD la plus proche (7 = noir / blanc)."""
    r, g, b = color[:3]
    if max(r, g, b) < 0.2 or min(r, g, b) > 0.9:
        return 7
    best, bd = 7, 1e9
    for idx, (cr, cg, cb) in DXF_ACI:
        d = (r - cr) ** 2 + (g - cg) ** 2 + (b - cb) ** 2
        if d < bd:
            best, bd = idx, d
    return best


def _dxf_name(s):
    import re
    import unicodedata
    flat = "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))
    return re.sub(r"[^A-Za-z0-9_\-]+", "_", flat).strip("_").upper()[:31] or "LAYER"


def write_dxf(path, pages, gap=50.0):
    """DXF R12 (AC1009) en millimètres de papier ; plusieurs pages sont posées côte à côte.
    Lisible par AutoCAD, Rhino, CADCraft, LibreCAD... Les aplats (textes) sont exportés par leur contour."""
    o = []

    def g(code, val):
        o.append("%d\n%s" % (code, val))
    layers = {}
    for pg in pages:
        for e in pg["ents"]:
            name = _dxf_name(e[-1])
            dashed = e[0] == 'L' and e[4] is not None
            layers.setdefault(name, dashed)
    g(0, "SECTION"); g(2, "HEADER"); g(9, "$ACADVER"); g(1, "AC1009"); g(0, "ENDSEC")
    g(0, "SECTION"); g(2, "TABLES")
    g(0, "TABLE"); g(2, "LTYPE"); g(70, 2)
    g(0, "LTYPE"); g(2, "CONTINUOUS"); g(70, 0); g(3, "Solid line"); g(72, 65); g(73, 0); g(40, 0.0)
    g(0, "LTYPE"); g(2, "HIDDEN"); g(70, 0); g(3, "Hidden"); g(72, 65); g(73, 2); g(40, 4.5); g(49, 3.0); g(49, -1.5)
    g(0, "ENDTAB")
    g(0, "TABLE"); g(2, "LAYER"); g(70, max(1, len(layers)))
    for name, dashed in layers.items():
        g(0, "LAYER"); g(2, name); g(70, 0); g(62, 7); g(6, "HIDDEN" if dashed else "CONTINUOUS")
    g(0, "ENDTAB")
    g(0, "ENDSEC")
    g(0, "SECTION"); g(2, "ENTITIES")
    ox = 0.0
    for pg in pages:
        for e in pg["ents"]:
            lay = _dxf_name(e[-1])
            if e[0] == 'L':
                paths, color = [(P, c) for P, c in e[1]], e[3]
            else:
                paths, color = [(L, True) for L in e[1]], e[2]
            aci = _aci(color)
            for P, closed in paths:
                if len(P) < 2:
                    continue
                g(0, "POLYLINE"); g(8, lay); g(62, aci); g(66, 1); g(70, 1 if closed else 0)
                for p in P:
                    g(0, "VERTEX"); g(8, lay); g(10, "%.4f" % (p[0] + ox)); g(20, "%.4f" % p[1]); g(30, "0.0")
                g(0, "SEQEND"); g(8, lay)
        ox += pg["w"] + gap
    g(0, "ENDSEC"); g(0, "EOF")
    with open(path, "w", encoding="ascii", errors="replace", newline="\n") as f:
        f.write("\n".join(o) + "\n")


def _late_imports():
    pass
