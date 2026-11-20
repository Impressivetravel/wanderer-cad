"""Wanderer CAD : zones fermées par des traits qui se croisent (Boundary, Area par point, Hatch Region).

Comme BOUNDARY d'AutoCAD : les courbes d'un même plan sont coupées les unes par les autres (un mur dessiné en plusieurs
traits qui se croisent ferme quand même la pièce), puis on suit le contour de la zone qui contient le point cliqué, avec
les îlots (meubles, poteaux) qui sont dedans.
"""

import math

import numpy as np


def _cross2(a, b):
    return a[..., 0] * b[..., 1] - a[..., 1] * b[..., 0]


def ring_area(R):
    """Aire signée d'un anneau 2D (positive dans le sens trigonométrique)."""
    R = np.asarray(R, dtype=np.float64)
    R = R - R[0]                # (loin de l'origine, les produits perdraient des chiffres : aire calculée autour d'un sommet)
    x, y = R[:, 0], R[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def ring_length(R):
    R = np.asarray(R, dtype=np.float64)
    return float(np.linalg.norm(np.roll(R, -1, axis=0) - R, axis=1).sum())


def point_in_ring(p, R):
    x, y = float(p[0]), float(p[1])
    P = np.asarray(R, dtype=np.float64)
    Q = np.roll(P, -1, axis=0)
    yi, yj = P[:, 1], Q[:, 1]
    cr = (yi > y) != (yj > y)
    if not cr.any():
        return False
    xi, xj = P[cr, 0], Q[cr, 0]
    yi, yj = yi[cr], yj[cr]
    xs = xi + (y - yi) * (xj - xi) / (yj - yi)
    return bool(np.count_nonzero(x < xs) % 2)


def clean_ring(R, eps):
    """Retire les points en double et les points alignés (un mur coupé en plusieurs traits redevient un seul côté)."""
    R = [np.asarray(p, dtype=np.float64) for p in R]
    changed = True
    while changed and len(R) > 3:
        changed = False
        out = []
        n = len(R)
        for i in range(n):
            a, b, c = R[i - 1], R[i], R[(i + 1) % n]
            ab, bc = b - a, c - b
            la, lb = float(np.hypot(*ab)), float(np.hypot(*bc))
            if la <= eps:
                changed = True
                continue
            if lb > eps and abs(float(ab[0] * bc[1] - ab[1] * bc[0])) <= eps * max(la, lb) and float(ab @ bc) > 0.0:
                changed = True            # b sur le segment a-c : inutile
                continue
            out.append(b)
        if len(out) < 3:
            return np.asarray(R)
        R = out
    return np.asarray(R)


def _weld(P, eps):
    """Soude les points à moins de eps les uns des autres : (n° de sommet de chaque point, sommets). Un simple arrondi sur
    une grille séparerait deux points voisins tombés de part et d'autre d'une ligne de la grille (un croisement calculé
    sur chacun des deux traits) et la pièce ne serait plus fermée : quatre grilles décalées, réunies, ne ratent rien."""
    n = len(P)
    if not n:
        return np.zeros(0, dtype=np.int64), P.reshape(0, 2)
    lab = np.arange(n, dtype=np.int64)
    cell = 2.0 * eps
    base = P.min(axis=0)
    keys = []
    for ox, oy in ((0.0, 0.0), (eps, 0.0), (0.0, eps), (eps, eps)):
        q = np.floor((P - base + (ox, oy)) / cell).astype(np.int64)
        k = q[:, 0] * (int(q[:, 1].max()) + 2) + q[:, 1]
        keys.append(np.unique(k, return_inverse=True)[1].reshape(-1))
    for _i in range(64):
        prev = lab
        for inv in keys:
            mn = np.full(int(inv.max()) + 1, n, dtype=np.int64)
            np.minimum.at(mn, inv, lab)
            lab = mn[inv]
        lab = lab[lab]                      # (raccourci : l'étiquette de son étiquette)
        if np.array_equal(lab, prev):
            break
    uniq, vid = np.unique(lab, return_inverse=True)
    return vid.reshape(-1), P[uniq]


class Arrangement:
    """Traits 2D coupés à leurs croisements : sommets, arêtes, et zones (faces) qu'ils ferment."""

    def __init__(self, segs, eps=None):
        S = np.asarray(segs, dtype=np.float64).reshape(-1, 2, 2)
        if len(S):
            lo, hi = S.reshape(-1, 2).min(axis=0), S.reshape(-1, 2).max(axis=0)
            scale = float(max(hi[0] - lo[0], hi[1] - lo[1], 1e-9))
        else:
            scale = 1.0
        self.scale = scale
        self.eps = float(eps) if eps is not None else max(1e-9, 1e-7 * scale)
        L = np.linalg.norm(S[:, 1] - S[:, 0], axis=1) if len(S) else np.zeros(0)
        S = S[L > self.eps]
        self._build(S)

    # ---- construction ----
    def _pairs(self, S):
        """Couples de traits dont les boîtes se touchent (grille régulière)."""
        m = len(S)
        if m < 2:
            return np.zeros((0, 2), dtype=np.int64)
        lo = np.minimum(S[:, 0], S[:, 1]) - self.eps
        hi = np.maximum(S[:, 0], S[:, 1]) + self.eps
        g0 = lo.min(axis=0)
        ext = float(max((hi.max(axis=0) - g0).max(), self.eps))
        med = float(np.median(np.linalg.norm(S[:, 1] - S[:, 0], axis=1)))
        h = max(med * 1.5, ext / max(1.0, math.sqrt(m)), self.eps * 10.0)
        for _attempt in range(6):
            i0 = np.floor((lo - g0) / h).astype(np.int64)
            i1 = np.floor((hi - g0) / h).astype(np.int64)
            w = i1[:, 0] - i0[:, 0] + 1
            ht = i1[:, 1] - i0[:, 1] + 1
            cnt = w * ht
            if int(cnt.sum()) <= 4_000_000:
                break
            h *= 2.0
        tot = int(cnt.sum())
        seg = np.repeat(np.arange(m), cnt)
        start = np.repeat(np.cumsum(cnt) - cnt, cnt)
        k = np.arange(tot) - start
        ww = w[seg]
        cx = i0[seg, 0] + k % ww
        cy = i0[seg, 1] + k // ww
        cell = cx * 4_000_003 + cy
        order = np.argsort(cell, kind='stable')
        cell, seg = cell[order], seg[order]
        cuts = np.flatnonzero(np.diff(cell)) + 1
        bounds = np.concatenate(([0], cuts, [len(cell)]))
        out = []
        for a, b in zip(bounds[:-1], bounds[1:]):
            n = b - a
            if n < 2:
                continue
            ids = seg[a:b]
            iu, ju = np.triu_indices(n, 1)
            out.append(np.stack((ids[iu], ids[ju]), axis=1))
        if not out:
            return np.zeros((0, 2), dtype=np.int64)
        P = np.concatenate(out)
        P = np.sort(P, axis=1)
        key = np.unique(P[:, 0] * m + P[:, 1])
        return np.stack((key // m, key % m), axis=1)

    def _build(self, S):
        eps = self.eps
        m = len(S)
        params = [np.zeros(m), np.ones(m)]
        owners = [np.arange(m), np.arange(m)]
        pr = self._pairs(S)
        if len(pr):
            I, J = pr[:, 0], pr[:, 1]
            A, B, C, D = S[I, 0], S[I, 1], S[J, 0], S[J, 1]
            r, s = B - A, D - C
            lr = np.linalg.norm(r, axis=1)
            ls = np.linalg.norm(s, axis=1)
            den = _cross2(r, s)
            qp = C - A
            par = np.abs(den) <= 1e-12 * lr * ls
            with np.errstate(divide='ignore', invalid='ignore'):
                t = _cross2(qp, s) / den
                u = _cross2(qp, r) / den
            tt, tu = eps / lr, eps / ls
            hit = (~par) & (t >= -tt) & (t <= 1 + tt) & (u >= -tu) & (u <= 1 + tu)
            params += [np.clip(t[hit], 0.0, 1.0), np.clip(u[hit], 0.0, 1.0)]
            owners += [I[hit], J[hit]]
            # traits superposés (deux murs sur la même ligne) : chacun est coupé aux extrémités de l'autre
            col = par & (np.abs(_cross2(qp, r)) <= eps * lr)
            if col.any():
                Ic, Jc = I[col], J[col]
                Ac, rc, Cc, sc = A[col], r[col], C[col], s[col]
                lr2, ls2 = (rc * rc).sum(axis=1), (sc * sc).sum(axis=1)
                for P_, own, base, d, l2 in ((Cc, Ic, Ac, rc, lr2), (Cc + sc, Ic, Ac, rc, lr2),
                                             (Ac, Jc, Cc, sc, ls2), (Ac + rc, Jc, Cc, sc, ls2)):
                    tp = ((P_ - base) * d).sum(axis=1) / l2
                    ok = (tp > 0.0) & (tp < 1.0)
                    params.append(tp[ok])
                    owners.append(own[ok])
        T = np.concatenate(params)
        O = np.concatenate(owners)
        order = np.lexsort((T, O))
        T, O = T[order], O[order]
        P = S[O, 0] + T[:, None] * (S[O, 1] - S[O, 0])
        vid, V = _weld(P, eps)
        same = O[1:] == O[:-1]
        ea, eb = vid[:-1][same], vid[1:][same]
        keep = ea != eb
        ea, eb = ea[keep], eb[keep]
        E = np.unique(np.sort(np.stack((ea, eb), axis=1), axis=1), axis=0) if len(ea) else np.zeros((0, 2), dtype=np.int64)
        self.V = V
        self._set_edges(E)

    def _set_edges(self, E):
        V = self.V
        # bouts libres (un trait qui dépasse dans la pièce) : retirés, ils ne ferment rien
        E = [tuple(map(int, e)) for e in E]
        adj = {}
        for a, b in E:
            adj.setdefault(a, set()).add(b)
            adj.setdefault(b, set()).add(a)
        stack = [v for v, nb in adj.items() if len(nb) == 1]
        while stack:
            v = stack.pop()
            nb = adj.get(v)
            if not nb or len(nb) != 1:
                continue
            w = nb.pop()
            del adj[v]
            other = adj.get(w)
            if other is not None:
                other.discard(v)
                if len(other) == 1:
                    stack.append(w)
                elif not other:
                    del adj[w]
        nbr = {}
        for v, nb in adj.items():
            d = V[list(nb)] - V[v]
            ang = np.arctan2(d[:, 1], d[:, 0])
            lst = [x for _a, x in sorted(zip(ang.tolist(), nb))]
            nbr[v] = lst
        self.nbr = nbr
        self.pos = {(v, w): i for v, lst in nbr.items() for i, w in enumerate(lst)}
        edges = sorted({(min(a, b), max(a, b)) for a, lst in nbr.items() for b in lst})
        self.E = np.asarray(edges, dtype=np.int64).reshape(-1, 2)
        # pièces séparées (îlots)
        comp = {}
        cid = 0
        for v in nbr:
            if v in comp:
                continue
            comp[v] = cid
            todo = [v]
            while todo:
                x = todo.pop()
                for y in nbr[x]:
                    if y not in comp:
                        comp[y] = cid
                        todo.append(y)
            cid += 1
        self.comp = comp
        self.ncomp = cid
        verts = {}
        for v, c in comp.items():
            verts.setdefault(c, []).append(v)
        self.comp_verts = verts

    # ---- parcours ----
    def _trace(self, a, b, limit=None):
        """Suit la zone à gauche de la demi-arête a -> b ; liste des sommets, ou None."""
        limit = limit or (2 * len(self.E) + 10)
        start = (a, b)
        ring = []
        for _i in range(limit):
            ring.append(a)
            lst = self.nbr[b]
            c = lst[(self.pos[(b, a)] - 1) % len(lst)]
            a, b = b, c
            if (a, b) == start:
                return ring
        return None

    def _outer_of(self, comp_id):
        """Contour extérieur (sens horaire) d'une pièce isolée."""
        vs = self.comp_verts[comp_id]
        v = min(vs, key=lambda i: (self.V[i, 0], self.V[i, 1]))
        lst = self.nbr[v]
        d = self.V[lst] - self.V[v]
        c = lst[int(np.argmax(np.arctan2(d[:, 1], d[:, 0])))]
        return self._trace(v, c)

    def face_at(self, p, islands=True):
        """Zone qui contient p : (contour extérieur, [îlots]) en anneaux 2D, ou None (hors de toute zone fermée)."""
        if not len(self.E):
            return None
        p = np.asarray(p, dtype=np.float64)
        V = self.V
        a, b = V[self.E[:, 0]], V[self.E[:, 1]]
        cr = (a[:, 1] > p[1]) != (b[:, 1] > p[1])
        if not cr.any():
            return None
        idx = np.flatnonzero(cr)
        aa, bb = a[idx], b[idx]
        xs = aa[:, 0] + (p[1] - aa[:, 1]) * (bb[:, 0] - aa[:, 0]) / (bb[:, 1] - aa[:, 1])
        right = xs > p[0]
        idx, xs = idx[right], xs[right]
        skip = set()
        outer = None
        for k in np.argsort(xs):
            ea, eb = map(int, self.E[idx[k]])
            c = self.comp[ea]
            if c in skip:
                continue
            if _cross2(V[eb] - V[ea], p - V[ea]) < 0:
                ea, eb = eb, ea
            ring = self._trace(ea, eb)
            if ring is None:
                skip.add(c)
                continue
            R = V[ring]
            if ring_area(R) > 0 and point_in_ring(p, R):
                outer = (ring, c)
                break
            skip.add(c)          # le contour extérieur d'un îlot : la zone est plus loin
        if outer is None:
            return None
        ring, c0 = outer
        R0 = V[ring]
        holes = []
        if islands:
            cand = []
            for cid in range(self.ncomp):
                if cid == c0:
                    continue
                rep = self.comp_verts[cid][0]
                if not point_in_ring(V[rep], R0):
                    continue
                o = self._outer_of(cid)
                if o is None:
                    continue
                cand.append((cid, V[o]))
            for cid, R in cand:
                if any(other is not R and point_in_ring(R[0], other) and abs(ring_area(other)) > abs(ring_area(R))
                       for _c, other in cand):
                    continue        # dans un autre îlot : pas au contact de la zone
                if point_in_ring(p, R):
                    continue
                holes.append(R)
        return R0, holes


# --------------------------------------------------------------------------
# Plans de dessin : les courbes d'un même plan, coupées entre elles
# --------------------------------------------------------------------------

class RegionFinder:
    """Zones fermées des courbes visibles, plan par plan (perpendiculaires à la normale de la vue)."""

    def __init__(self, paths, u, v, n):
        self.u = np.asarray(u, dtype=np.float64)
        self.v = np.asarray(v, dtype=np.float64)
        self.n = np.asarray(n, dtype=np.float64)
        allp = [np.asarray(P, dtype=np.float64) for P, _c in paths if len(P) >= 2]
        scale = float(np.ptp(np.vstack(allp), axis=0).max()) if allp else 1.0
        self.tol = max(1e-6, 1e-6 * scale)
        levels = {}
        for P, closed in paths:
            P = np.asarray(P, dtype=np.float64)
            if len(P) < 2:
                continue
            d = P @ self.n
            if float(np.ptp(d)) > self.tol:
                continue            # courbe hors d'un plan parallèle à la vue
            h = float(d.mean())
            key = int(round(h / (self.tol * 10.0)))
            Q = np.vstack([P, P[:1]]) if closed and len(P) >= 3 else P
            F = np.stack((Q @ self.u, Q @ self.v), axis=1)
            seg = np.stack((F[:-1], F[1:]), axis=1)
            lv = levels.setdefault(key, [h, []])
            lv[1].append(seg)
        self.levels = {k: (h, np.concatenate(S)) for k, (h, S) in levels.items()}
        self._arr = {}

    def arrangement(self, key):
        a = self._arr.get(key)
        if a is None:
            a = self._arr[key] = Arrangement(self.levels[key][1])
        return a

    def at_ray(self, o, d, islands=True):
        """(c, u, v, n, anneaux 2D [contour, îlots...], distance) de la zone visée, ou None : même forme que Hatch Region."""
        o = np.asarray(o, dtype=np.float64)
        d = np.asarray(d, dtype=np.float64)
        dn = float(d @ self.n)
        if abs(dn) < 1e-9:
            return None
        hits = []
        for key, (h, _S) in self.levels.items():
            t = (h - float(o @ self.n)) / dn
            hits.append((t, key, h))
        hits.sort(key=lambda x: (x[0] < 0.0, abs(x[0])))     # les plans devant la vue d'abord, du plus proche au plus loin
        for t, key, h in hits:
            p3 = o + d * t
            p2 = (float(p3 @ self.u), float(p3 @ self.v))
            arr = self.arrangement(key)
            f = arr.face_at(p2, islands=islands)
            if f is None:
                continue
            R0, holes = f
            R0 = clean_ring(R0, arr.eps)
            holes = [clean_ring(H, arr.eps) for H in holes]
            c = self.n * h
            return (c, self.u, self.v, self.n, [R0] + holes, t)
        return None


def _late_imports():
    pass
