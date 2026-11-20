"""Wanderer CAD : découpe d'un motif de hachure par des contours (sans Blender)."""

import math

import numpy as np

HATCH_MAX_LINES = 6000          # lignes d'une famille de motif
HATCH_MAX_SEGS = 250000         # segments d'une hachure
DOT_LEN = 0.15                  # longueur d'un point du motif (tiret 0), en unités du motif


class HatchTooDense(Exception):
    """Motif trop serré pour la zone : il faut une échelle plus grande."""


def segments_2d(rings, fams, unit, rot, base, dot=DOT_LEN, max_segs=HATCH_MAX_SEGS):
    """Segments 2D (N, 2, 2) des familles de lignes `fams` découpées par les anneaux (pair / impair : les trous
    restent vides). Un tiret positif est un trait, négatif un vide, 0 un point (court trait de `dot` unités)."""
    if not fams:
        return np.zeros((0, 2, 2))
    A = np.vstack([np.asarray(R, dtype=np.float64) for R in rings])
    B = np.vstack([np.roll(np.asarray(R, dtype=np.float64), -1, axis=0) for R in rings])
    O = np.asarray(base, dtype=np.float64)
    unit = max(float(unit), 1e-12)
    half_dot = 0.5 * dot * unit
    segs = []
    total = 0
    for ang, al0, pp0, shift, spacing, dashes in fams:
        a = math.radians(ang) + rot
        dv = np.array((math.cos(a), math.sin(a)))
        nv = np.array((-math.sin(a), math.cos(a)))
        h, s, al0, pp0 = spacing * unit, shift * unit, al0 * unit, pp0 * unit
        if h < 1e-12:
            continue
        dash = [x * unit for x in dashes]
        period = sum(abs(x) for x in dash)
        pa, pb = (A - O) @ nv, (B - O) @ nv
        qa, qb = (A - O) @ dv, (B - O) @ dv
        lo, hi = float(min(pa.min(), pb.min())), float(max(pa.max(), pb.max()))
        k0, k1 = math.ceil((lo - pp0) / h), math.floor((hi - pp0) / h)
        if k1 < k0:
            continue
        if k1 - k0 + 1 > HATCH_MAX_LINES:
            raise HatchTooDense()
        dp = pb - pa
        ok_e = np.abs(dp) > 1e-15
        for c0 in range(k0, k1 + 1, 256):
            ks = np.arange(c0, min(c0 + 256, k1 + 1))
            cc = pp0 + ks * h
            mask = ((pa[None, :] > cc[:, None]) != (pb[None, :] > cc[:, None])) & ok_e[None, :]
            tt = (cc[:, None] - pa[None, :]) / np.where(ok_e, dp, 1.0)[None, :]
            along = qa[None, :] + tt * (qb - qa)[None, :] - (al0 + ks * s)[:, None]
            for row, k in enumerate(ks):
                vals = np.sort(along[row][mask[row]])
                if len(vals) < 2:
                    continue
                bp = O + dv * (al0 + k * s) + nv * (pp0 + k * h)
                for i in range(0, len(vals) - 1, 2):
                    t0, t1 = float(vals[i]), float(vals[i + 1])
                    if t1 - t0 < 1e-12:
                        continue
                    if not dash or period < 1e-12:
                        segs.append((bp + dv * t0, bp + dv * t1))
                        total += 1
                    else:
                        m = math.floor(t0 / period)
                        if (t1 - m * period) / period * len(dash) > max_segs:
                            raise HatchTooDense()
                        while m * period < t1:
                            pos = m * period
                            for ln in dash:
                                if ln > 0:
                                    a_, b_ = max(pos, t0), min(pos + ln, t1)
                                    if b_ - a_ > 1e-12:
                                        segs.append((bp + dv * a_, bp + dv * b_))
                                        total += 1
                                elif ln == 0 and t0 <= pos <= t1:
                                    a_, b_ = max(pos - half_dot, t0), min(pos + half_dot, t1)
                                    if b_ - a_ > 1e-12:
                                        segs.append((bp + dv * a_, bp + dv * b_))
                                        total += 1
                                pos += abs(ln)
                            m += 1
                    if total > max_segs:
                        raise HatchTooDense()
    if not segs:
        return np.zeros((0, 2, 2))
    return np.array(segs, dtype=np.float64)
