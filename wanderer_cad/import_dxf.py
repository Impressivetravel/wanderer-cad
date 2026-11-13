"""Wanderer CAD : Import DXF / DWG."""

import bpy
import math
import numpy as np
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

from mathutils import Matrix, Vector
from mathutils.geometry import interpolate_bezier

from . import layout_engine as le
from .core import TAU, pref
from .layers import _LAYERCOL, find_layer_collection


# --------------------------------------------------------------------------
# Import DXF (calques, couleurs, blocs, textes).
# --------------------------------------------------------------------------

DXF_UNITS_M = {1: 0.0254, 2: 0.3048, 3: 1609.344, 4: 0.001, 5: 0.01, 6: 1.0, 7: 1000.0, 8: 2.54e-8, 9: 2.54e-5,
               10: 0.9144, 11: 1e-10, 12: 1e-9, 13: 1e-6, 14: 0.1, 15: 10.0, 16: 100.0, 17: 1e9}
DXF_UNITS_TAG = "WANDERER_UNITS="
DXF_SKIPPED = {"HATCH", "MLINE", "IMAGE", "XLINE", "RAY", "3DSOLID", "BODY", "REGION", "SURFACE", "MESH", "WIPEOUT", "OLE2FRAME", "ATTDEF", "ATTRIB",
               "VIEWPORT", "TOLERANCE", "MLEADER", "TABLE", "UNDERLAY", "LIGHT", "SUN", "ACAD_PROXY_ENTITY"}


def aci_rgb(i):
    """Couleur d'index AutoCAD (ACI) -> (r, g, b) 0..1 (le 7 « blanc / noir » est rendu en gris clair pour un fond sombre)."""
    base = {1: (255, 0, 0), 2: (255, 255, 0), 3: (0, 255, 0), 4: (0, 255, 255), 5: (0, 0, 255), 6: (255, 0, 255),
            7: (230, 230, 230), 8: (65, 65, 65), 9: (128, 128, 128)}
    if i in base:
        r, g, b = base[i]
    elif 10 <= i <= 249:
        import colorsys
        hue = ((i - 10) // 10) * 15.0 / 360.0
        k = (i - 10) % 10
        sat = 1.0 if k % 2 == 0 else 0.5
        val = (1.0, 0.65, 0.5, 0.3, 0.15)[k // 2]
        r, g, b = [int(round(255 * c)) for c in colorsys.hsv_to_rgb(hue, sat, val)]
    elif 250 <= i <= 255:
        r = g = b = (51, 91, 132, 173, 214, 255)[i - 250]
    else:
        r, g, b = 230, 230, 230
    return (r / 255.0, g / 255.0, b / 255.0)


def dxf_pairs(data):
    """Liste de (code, valeur) d'un DXF texte (ASCII ou UTF-8 ; les anciens fichiers en cp1252)."""
    if data[:18] == b"AutoCAD Binary DXF":
        raise ValueError("Binary DXF is not supported: save the file as an ASCII DXF")
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError:
        text = data.decode('cp1252', errors='replace')
    lines = text.split("\n")
    out = []
    for i in range(0, len(lines) - 1, 2):
        try:
            code = int(lines[i].strip())
        except ValueError:
            continue
        out.append((code, lines[i + 1].rstrip("\r")))
    return out


def _dxf_group(sect):
    out, cur = [], None
    for code, val in sect:
        if code == 0:
            cur = {"t": val.strip(), "p": [], "v": []}
            out.append(cur)
        elif cur is not None:
            cur["p"].append((code, val))
    return out


def _dxf_merge(ents):
    """POLYLINE + VERTEX ... SEQEND en une seule entité ; INSERT + ATTRIB ... SEQEND."""
    out, i, n = [], 0, len(ents)
    while i < n:
        e = ents[i]
        if e["t"] in ("POLYLINE", "INSERT") and i + 1 < n and ents[i + 1]["t"] in ("VERTEX", "ATTRIB"):
            j = i + 1
            while j < n and ents[j]["t"] != "SEQEND":
                if ents[j]["t"] == "VERTEX":
                    e["v"].append(ents[j]["p"])
                j += 1
            out.append(e)
            i = j + 1
            continue
        if e["t"] not in ("SEQEND", "VERTEX"):
            out.append(e)
        i += 1
    return out


def dxf_get(p, code, default=None):
    for c, v in p:
        if c == code:
            return v
    return default


def dxf_num(p, code, default=0.0):
    v = dxf_get(p, code)
    if v is None:
        return default
    try:
        return float(v)
    except ValueError:
        return default


def dxf_vec(p, c0, default=(0.0, 0.0, 0.0), base=10):
    return np.array((dxf_num(p, c0, default[0]), dxf_num(p, c0 + 10, default[1]), dxf_num(p, c0 + 20, default[2])))


def dxf_parse(data):
    """(en-tête, calques, blocs, entités) d'un DXF."""
    pairs = dxf_pairs(data)
    n = len(pairs)
    header, layers, blocks, ents = {}, {}, {}, []
    i = 0
    while i < n:
        code, val = pairs[i]
        if code == 0 and val.strip() == "SECTION" and i + 1 < n and pairs[i + 1][0] == 2:
            name = pairs[i + 1][1].strip()
            k = i + 2
            while k < n and not (pairs[k][0] == 0 and pairs[k][1].strip() == "ENDSEC"):
                k += 1
            sect = pairs[i + 2:k]
            if name == "HEADER":
                j = 0
                while j < len(sect):
                    if sect[j][0] == 9 and j + 1 < len(sect):
                        header[sect[j][1].strip()] = sect[j + 1][1]
                        j += 2
                    else:
                        j += 1
            elif name == "TABLES":
                for e in _dxf_group(sect):
                    if e["t"] == "LAYER":
                        p = e["p"]
                        nm = dxf_get(p, 2, "0")
                        layers[nm] = {"aci": int(dxf_num(p, 62, 7)), "rgb": dxf_get(p, 420), "flags": int(dxf_num(p, 70, 0))}
            elif name == "BLOCKS":
                cur = None
                for e in _dxf_merge(_dxf_group(sect)):
                    if e["t"] == "BLOCK":
                        cur = {"name": dxf_get(e["p"], 2, ""), "base": dxf_vec(e["p"], 10), "ents": []}
                        blocks[cur["name"]] = cur
                    elif e["t"] == "ENDBLK":
                        cur = None
                    elif cur is not None:
                        cur["ents"].append(e)
            elif name == "ENTITIES":
                ents = _dxf_merge(_dxf_group(sect))
            i = k + 1
        else:
            i += 1
    for code, val in pairs[:40]:          # fichier écrit par Wanderer CAD (R12, sans $INSUNITS) : ses unités sont en commentaire
        if code == 999 and val.strip().startswith(DXF_UNITS_TAG):
            header.setdefault("$INSUNITS", val.strip()[len(DXF_UNITS_TAG):])
    return header, layers, blocks, ents


def dxf_ocs(nrm):
    """Axes du système de coordonnées d'objet (algorithme d'axe arbitraire d'AutoCAD)."""
    nrm = np.array(nrm, dtype=np.float64)
    ln = np.linalg.norm(nrm)
    if ln < 1e-12:
        nrm = np.array((0.0, 0.0, 1.0))
    else:
        nrm = nrm / ln
    if abs(nrm[0]) < 1 / 64.0 and abs(nrm[1]) < 1 / 64.0:
        ax = np.cross((0.0, 1.0, 0.0), nrm)
    else:
        ax = np.cross((0.0, 0.0, 1.0), nrm)
    ax = ax / np.linalg.norm(ax)
    ay = np.cross(nrm, ax)
    return ax, ay, nrm


def dxf_bulge_points(p1, p2, b, seg_full=64):
    """Points intermédiaires d'un segment à renflement (arc) de p1 à p2 (2D), extrémité p2 comprise."""
    p1 = np.asarray(p1, dtype=np.float64)
    p2 = np.asarray(p2, dtype=np.float64)
    if abs(b) < 1e-9:
        return [p2]
    d = p2 - p1
    c = float(np.hypot(d[0], d[1]))
    if c < 1e-12:
        return [p2]
    left = np.array((-d[1], d[0])) / c
    mid = (p1 + p2) * 0.5
    ctr = mid + left * (c * 0.5) * ((1.0 - b * b) / (2.0 * b))
    r = float(np.hypot(*(p1 - ctr)))
    a0 = math.atan2(p1[1] - ctr[1], p1[0] - ctr[0])
    sweep = 4.0 * math.atan(b)
    k = max(2, int(abs(sweep) / TAU * seg_full) + 1)
    return [ctr + r * np.array((math.cos(a0 + sweep * i / k), math.sin(a0 + sweep * i / k))) for i in range(1, k + 1)]


def dxf_spline_points(deg, knots, ctrl, weights):
    m = len(ctrl)
    if m < 2:
        return ctrl
    if deg < 1 or len(knots) != m + deg + 1:
        return ctrl
    P = np.array(ctrl, dtype=np.float64)
    w = np.array(weights if len(weights) == m else [1.0] * m, dtype=np.float64)
    H = np.hstack((P * w[:, None], w[:, None]))
    kn = np.array(knots, dtype=np.float64)
    t0, t1 = kn[deg], kn[m]
    if t1 - t0 < 1e-12:
        return ctrl
    out = []
    count = max(16, m * 8)
    for t in np.linspace(t0, t1, count):
        k = int(np.searchsorted(kn, t, side='right') - 1)
        k = max(deg, min(k, m - 1))
        dd = [H[j + k - deg].copy() for j in range(deg + 1)]
        for r in range(1, deg + 1):
            for j in range(deg, r - 1, -1):
                den = kn[j + 1 + k - r] - kn[j + k - deg]
                a = (t - kn[j + k - deg]) / den if den > 1e-12 else 0.0
                dd[j] = (1.0 - a) * dd[j - 1] + a * dd[j]
        h = dd[deg]
        out.append(h[:3] / h[3] if abs(h[3]) > 1e-12 else h[:3])
    return out


def dxf_clean_text(s):
    """Texte MTEXT / TEXT lisible : codes de mise en forme retirés, symboles %% convertis."""
    s = s.replace("\\P", "\n").replace("\\~", " ")
    s = re.sub(r"\\[fFHhCcQqWwTtAa][^;]*;", "", s)
    s = re.sub(r"\\[LlOoKk]", "", s)
    s = re.sub(r"\\U\+([0-9A-Fa-f]{4})", lambda m: chr(int(m.group(1), 16)), s)
    s = s.replace("{", "").replace("}", "").replace("\\\\", "\\")
    s = s.replace("%%c", "Ø").replace("%%C", "Ø").replace("%%d", "°").replace("%%D", "°").replace("%%p", "±").replace("%%P", "±")
    return s


def dxf_explode(ents, blocks, layers, M, inh, out, stats, opts, depth=0):
    """Transforme les entités en primitives monde : ('line', pts, fermé, calque, couleur), ('point', ..), ('face', ..), ('text', ..)."""
    seg_full = opts["segments"]
    for e in ents:
        t, p = e["t"], e["p"]
        layer = dxf_get(p, 8, "0")
        aci = int(dxf_num(p, 62, 256))
        rgb = dxf_get(p, 420)
        if layer == "0" and inh and inh.get("layer"):
            layer = inh["layer"]
        color = None
        if rgb is not None:
            try:
                v = int(rgb)
                color = (((v >> 16) & 255) / 255.0, ((v >> 8) & 255) / 255.0, (v & 255) / 255.0)
            except ValueError:
                pass
        if color is None:
            if aci == 0 and inh:
                color = inh.get("color")
            elif 1 <= aci <= 255:
                color = aci_rgb(aci)
        if aci < 0:
            color = None

        def W(pts):
            A = np.asarray(pts, dtype=np.float64).reshape(-1, 3)
            return A @ M[:3, :3].T + M[:3, 3]

        def add(kind, pts, closed=False, **kw):
            out.append(dict(kind=kind, pts=W(pts), closed=closed, layer=layer, color=color, **kw))

        if t == "LINE":
            add("line", [dxf_vec(p, 10), dxf_vec(p, 11)])
        elif t == "POINT":
            add("point", [dxf_vec(p, 10)])
        elif t == "LWPOLYLINE":
            ax, ay, nrm = dxf_ocs(dxf_vec(p, 210, (0.0, 0.0, 1.0)))
            elev = dxf_num(p, 38, 0.0)
            vs = []
            for c, v in p:
                if c == 10:
                    vs.append([float(v), 0.0, 0.0])
                elif c == 20 and vs:
                    vs[-1][1] = float(v)
                elif c == 42 and vs:
                    vs[-1][2] = float(v)
            if len(vs) < 2:
                continue
            closed = bool(int(dxf_num(p, 70, 0)) & 1)
            pts = [np.array(vs[0][:2])]
            nv = len(vs)
            for i in range(nv if closed else nv - 1):
                a, b = vs[i], vs[(i + 1) % nv]
                pts.extend(dxf_bulge_points(a[:2], b[:2], a[2], seg_full))
            if closed:
                pts = pts[:-1]
            P = np.array([ax * q[0] + ay * q[1] + nrm * elev for q in pts])
            add("line", P, closed)
        elif t == "POLYLINE":
            flags = int(dxf_num(p, 70, 0))
            ax, ay, nrm = dxf_ocs(dxf_vec(p, 210, (0.0, 0.0, 1.0)))
            verts = e["v"]
            if flags & 64:       # maillage polyface
                pv = [dxf_vec(v, 10) for v in verts if int(dxf_num(v, 70, 0)) & 192 == 192]
                faces = []
                for v in verts:
                    if int(dxf_num(v, 70, 0)) & 128 and not int(dxf_num(v, 70, 0)) & 64:
                        idx = [abs(int(dxf_num(v, c, 0))) - 1 for c in (71, 72, 73, 74)]
                        idx = [i for i in idx if 0 <= i < len(pv)]
                        if len(idx) >= 3:
                            faces.append(idx)
                if pv and faces:
                    out.append(dict(kind="mesh", pts=W(pv), faces=faces, layer=layer, color=color, closed=False))
                continue
            if flags & 16:       # maillage polygonal M x N : points seulement
                add("point", [dxf_vec(v, 10) for v in verts])
                continue
            is3d = bool(flags & 8)
            rows = [(dxf_vec(v, 10), dxf_num(v, 42, 0.0)) for v in verts if not int(dxf_num(v, 70, 0)) & 16]
            if len(rows) < 2:
                continue
            closed = bool(flags & 1)
            pts = [rows[0][0]]
            nv = len(rows)
            for i in range(nv if closed else nv - 1):
                a, b = rows[i], rows[(i + 1) % nv]
                if is3d or abs(a[1]) < 1e-9:
                    pts.append(b[0])
                else:
                    z = a[0][2]
                    pts.extend(np.array((q[0], q[1], z)) for q in dxf_bulge_points(a[0][:2], b[0][:2], a[1], seg_full))
            if closed:
                pts = pts[:-1]
            if not is3d:
                P = np.array([ax * q[0] + ay * q[1] + nrm * q[2] for q in pts])
            else:
                P = np.array(pts)
            add("line", P, closed)
        elif t in ("CIRCLE", "ARC"):
            ax, ay, nrm = dxf_ocs(dxf_vec(p, 210, (0.0, 0.0, 1.0)))
            c = dxf_vec(p, 10)
            r = dxf_num(p, 40, 0.0)
            if r <= 0:
                continue
            if t == "CIRCLE":
                a0, a1 = 0.0, TAU
            else:
                a0 = math.radians(dxf_num(p, 50, 0.0))
                a1 = math.radians(dxf_num(p, 51, 360.0))
                if a1 <= a0:
                    a1 += TAU
            k = max(4, int((a1 - a0) / TAU * seg_full) + 1)
            ts = np.linspace(a0, a1, k + 1)
            if t == "CIRCLE":
                ts = ts[:-1]
            P = np.array([ax * (c[0] + r * math.cos(a)) + ay * (c[1] + r * math.sin(a)) + nrm * c[2] for a in ts])
            add("line", P, t == "CIRCLE")
        elif t == "ELLIPSE":
            c = dxf_vec(p, 10)
            maj = dxf_vec(p, 11)
            nrm = dxf_vec(p, 210, (0.0, 0.0, 1.0))
            ratio = dxf_num(p, 40, 1.0)
            a0, a1 = dxf_num(p, 41, 0.0), dxf_num(p, 42, TAU)
            if a1 <= a0:
                a1 += TAU
            mn = np.cross(nrm, maj)
            ln = np.linalg.norm(mn)
            mn = mn / ln * np.linalg.norm(maj) * ratio if ln > 1e-12 else np.zeros(3)
            full = (a1 - a0) >= TAU - 1e-6
            k = max(8, int((a1 - a0) / TAU * seg_full) + 1)
            ts = np.linspace(a0, a1, k + 1)
            if full:
                ts = ts[:-1]
            P = np.array([c + maj * math.cos(a) + mn * math.sin(a) for a in ts])
            add("line", P, full)
        elif t == "SPLINE":
            deg = int(dxf_num(p, 71, 3))
            knots = [float(v) for c, v in p if c == 40]
            ctrl, wts, fit = [], [float(v) for c, v in p if c == 41], []
            cur = None
            for c, v in p:
                if c == 10:
                    cur = [float(v), 0.0, 0.0]
                    ctrl.append(cur)
                elif c in (20, 30) and cur is not None and c != 11:
                    cur[1 if c == 20 else 2] = float(v)
            cur = None
            for c, v in p:
                if c == 11:
                    cur = [float(v), 0.0, 0.0]
                    fit.append(cur)
                elif c in (21, 31) and cur is not None:
                    cur[1 if c == 21 else 2] = float(v)
            closed = bool(int(dxf_num(p, 70, 0)) & 1)
            if len(ctrl) >= 2 and knots:
                P = dxf_spline_points(deg, knots, ctrl, wts)
            else:
                P = fit if len(fit) >= 2 else ctrl
            if len(P) >= 2:
                add("line", P, False)
        elif t == "LEADER":
            P = [np.array((float(v), 0.0, 0.0)) for c, v in p if c == 10]
            ys = [float(v) for c, v in p if c == 20]
            zs = [float(v) for c, v in p if c == 30]
            P = [np.array((q[0], ys[i] if i < len(ys) else 0.0, zs[i] if i < len(zs) else 0.0)) for i, q in enumerate(P)]
            if len(P) >= 2:
                add("line", P, False)
        elif t == "3DFACE":
            P = [dxf_vec(p, 10), dxf_vec(p, 11), dxf_vec(p, 12), dxf_vec(p, 13)]
            if np.linalg.norm(P[3] - P[2]) < 1e-12:
                P = P[:3]
            out.append(dict(kind="mesh", pts=W(P), faces=[list(range(len(P)))], layer=layer, color=color, closed=False))
        elif t == "SOLID" or t == "TRACE":
            ax, ay, nrm = dxf_ocs(dxf_vec(p, 210, (0.0, 0.0, 1.0)))
            q = [dxf_vec(p, 10), dxf_vec(p, 11), dxf_vec(p, 12), dxf_vec(p, 13)]
            if np.linalg.norm(q[3] - q[2]) < 1e-12:
                q = q[:3]
            else:
                q = [q[0], q[1], q[3], q[2]]
            P = [ax * x[0] + ay * x[1] + nrm * x[2] for x in q]
            out.append(dict(kind="mesh", pts=W(P), faces=[list(range(len(P)))], layer=layer, color=color, closed=False))
        elif t in ("TEXT", "MTEXT"):
            if not opts["text"]:
                continue
            txt = dxf_get(p, 1, "") + "".join(v for c, v in p if c == 3)
            txt = dxf_clean_text(txt)
            if not txt.strip():
                continue
            h = dxf_num(p, 40, 1.0)
            if t == "MTEXT" and any(c == 11 for c, _v in p):
                d = dxf_vec(p, 11)
                rot = math.atan2(d[1], d[0])
            else:
                rot = math.radians(dxf_num(p, 50, 0.0))
            add("text", [dxf_vec(p, 10)], text=txt, height=h, rot=rot, mtext=(t == "MTEXT"),
                halign=int(dxf_num(p, 72, 0)), attach=int(dxf_num(p, 71, 1)))
        elif t in ("INSERT", "DIMENSION"):
            if not opts["blocks"]:
                continue
            bname = dxf_get(p, 2)
            blk = blocks.get(bname) if bname else None
            if blk is None or depth > 8:
                continue
            ins = dxf_vec(p, 10) if t == "INSERT" else np.zeros(3)
            sx = dxf_num(p, 41, 1.0) if t == "INSERT" else 1.0
            sy = dxf_num(p, 42, sx) if t == "INSERT" else 1.0
            sz = dxf_num(p, 43, sx) if t == "INSERT" else 1.0
            rot = math.radians(dxf_num(p, 50, 0.0)) if t == "INSERT" else 0.0
            cols = max(1, int(dxf_num(p, 70, 1))) if t == "INSERT" else 1
            rows = max(1, int(dxf_num(p, 71, 1))) if t == "INSERT" else 1
            dc, dr = dxf_num(p, 44, 0.0), dxf_num(p, 45, 0.0)
            ax, ay, nrm = dxf_ocs(dxf_vec(p, 210, (0.0, 0.0, 1.0))) if t == "INSERT" else (np.array((1.0, 0, 0)), np.array((0, 1.0, 0)), np.array((0, 0, 1.0)))
            R = np.eye(4)
            R[:3, 0], R[:3, 1], R[:3, 2] = ax, ay, nrm
            Rz = np.eye(4)
            Rz[:2, :2] = ((math.cos(rot), -math.sin(rot)), (math.sin(rot), math.cos(rot)))
            Sc = np.diag((sx, sy, sz, 1.0))
            B = np.eye(4)
            B[:3, 3] = -blk["base"]
            for ci in range(min(cols, 200)):
                for ri in range(min(rows, 200)):
                    T = np.eye(4)
                    T[:3, 3] = ins + np.array((ci * dc, ri * dr, 0.0))
                    stats["inserts"] += 1
                    if stats["inserts"] > 20000:
                        stats["truncated"] = True
                        return
                    # les coordonnées du bloc passent par l'insertion, puis par le repère d'objet de l'INSERT
                    MM = M @ R @ T @ Rz @ Sc @ B
                    dxf_explode(blk["ents"], blocks, layers, MM, {"layer": layer, "color": color}, out, stats, opts, depth + 1)
        else:
            if t in DXF_SKIPPED:
                stats["skipped"][t] = stats["skipped"].get(t, 0) + 1


def dxf_header_scale(header, units, scene):
    """Facteur unités du fichier -> unités Blender."""
    to_m = None
    if units == 'AUTO':
        try:
            code = int(float(header.get("$INSUNITS", "0")))
        except ValueError:
            code = 0
        to_m = DXF_UNITS_M.get(code)
    elif units != 'NONE':
        to_m = {"MM": 0.001, "CM": 0.01, "M": 1.0, "IN": 0.0254, "FT": 0.3048}.get(units)
    if to_m is None:
        return 1.0
    return to_m / (scene.unit_settings.scale_length or 1.0)


def dxf_build(context, header, layers, prims, opts, label):
    """Crée collections, objets et couleurs de calques. Retourne (nb d'objets, texte de compte rendu)."""
    scene = context.scene
    scale = dxf_header_scale(header, opts["units"], scene)
    root = bpy.data.collections.new(label)
    scene.collection.children.link(root)
    cols = {}
    layer_names = sorted({p["layer"] for p in prims} | set(layers))
    if not opts["layers"]:
        layer_names = [""]
    for name in layer_names:
        if opts["layers"]:
            c = bpy.data.collections.new(name or "0")
            root.children.link(c)
            info = layers.get(name, {})
            aci = abs(info.get("aci", 7)) or 7
            rgb = info.get("rgb")
            col = aci_rgb(aci)
            if rgb is not None:
                try:
                    v = int(rgb)
                    col = (((v >> 16) & 255) / 255.0, ((v >> 8) & 255) / 255.0, (v & 255) / 255.0)
                except ValueError:
                    pass
            c.dessin_layer.color = col
            c.dessin_layer.use_color = True
            cols[name] = (c, info)
        else:
            cols[name] = (root, {})
    nprims = len(prims)
    mode = opts["mode"]
    if mode == 'AUTO':
        mode = 'ENTITY' if nprims <= 3000 else 'LAYER'
    created = 0
    by_layer = {}
    for pr in prims:
        by_layer.setdefault(pr["layer"] if opts["layers"] else "", []).append(pr)

    def link(obj, name):
        cols[name][0].objects.link(obj)

    def obj_color(obj, pr, layer_name):
        info = cols[layer_name][1] if layer_name in cols else {}
        c = pr.get("color") if pr is not None else None
        if c is not None and opts["entity_colors"]:
            obj.color = (c[0], c[1], c[2], 1.0)
        elif opts["layers"]:
            lc = cols[layer_name][0].dessin_layer
            obj.color = (lc.color[0], lc.color[1], lc.color[2], 1.0)
            obj["wd_lc"] = 1

    def mesh_from(name, verts, edges, faces):
        me = bpy.data.meshes.new(name)
        me.from_pydata(np.asarray(verts, dtype=np.float64).tolist(), edges, faces)
        me.update()
        return me

    for lname, items in by_layer.items():
        lname_key = lname if opts["layers"] else ""
        if mode == 'LAYER':
            verts, edges, faces = [], [], []
            for pr in items:
                if pr["kind"] == "text":
                    continue
                base = len(verts)
                P = pr["pts"] * scale
                verts.extend(P.tolist())
                if pr["kind"] == "line":
                    n = len(P)
                    edges.extend((base + i, base + i + 1) for i in range(n - 1))
                    if pr["closed"] and n > 2:
                        edges.append((base + n - 1, base))
                elif pr["kind"] == "mesh":
                    faces.extend([tuple(base + i for i in f) for f in pr["faces"]])
            if verts:
                me = mesh_from(lname or "DXF", verts, edges, faces)
                obj = bpy.data.objects.new(lname or "DXF", me)
                link(obj, lname_key)
                obj_color(obj, None, lname_key)
                created += 1
        else:
            for pr in items:
                if pr["kind"] == "text":
                    continue
                P = pr["pts"] * scale
                if pr["kind"] == "point":
                    for q in P:
                        obj = bpy.data.objects.new("Point", None)
                        obj.empty_display_type = 'PLAIN_AXES'
                        obj.empty_display_size = 0.05 * max(scale, 1e-9) / max(scale, 1e-9)
                        obj.location = q
                        link(obj, lname_key)
                        obj_color(obj, pr, lname_key)
                        created += 1
                    continue
                n = len(P)
                if pr["kind"] == "line":
                    edges = [(i, i + 1) for i in range(n - 1)] + ([(n - 1, 0)] if pr["closed"] and n > 2 else [])
                    me = mesh_from("Line", P, edges, [])
                else:
                    me = mesh_from("Face", P, [], [tuple(f) for f in pr["faces"]])
                obj = bpy.data.objects.new(me.name, me)
                link(obj, lname_key)
                obj_color(obj, pr, lname_key)
                created += 1
    # textes : toujours un objet par texte (au plus 800 : chaque texte est un objet lourd)
    ntext = 0
    skipped_text = 0
    for pr in prims:
        if pr["kind"] != "text":
            continue
        if ntext >= 800:
            skipped_text += 1
            continue
        lname_key = pr["layer"] if opts["layers"] else ""
        fc = bpy.data.curves.new("Text", 'FONT')
        fc.body = pr["text"]
        fc.size = max(pr["height"] * scale, 1e-6)
        fc.align_x = {0: 'LEFT', 1: 'CENTER', 2: 'RIGHT'}.get(pr["halign"], 'LEFT') if not pr["mtext"] else \
            {1: 'LEFT', 2: 'CENTER', 3: 'RIGHT'}.get((pr["attach"] - 1) % 3 + 1, 'LEFT')
        obj = bpy.data.objects.new("Text", fc)
        obj.location = pr["pts"][0] * scale
        obj.rotation_euler = (0.0, 0.0, pr["rot"])
        link(obj, lname_key)
        obj_color(obj, pr, lname_key)
        ntext += 1
        created += 1
    # calques gelés / éteints : masqués
    if opts["layers"]:
        for name, (c, info) in cols.items():
            if info and (info.get("flags", 0) & 1 or info.get("aci", 7) < 0):
                lc = find_layer_collection(context.view_layer.layer_collection, c.name)
                if lc is not None:
                    lc.hide_viewport = True
    lc = find_layer_collection(context.view_layer.layer_collection, root.name)
    if lc is not None:
        context.view_layer.active_layer_collection = lc
    if skipped_text:
        _LAYERCOL["import_note"] = f"{skipped_text} text object(s) not imported (limit 800)"
    return created, mode


# --------------------------------------------------------------------------
# Export DXF du modèle (R12 : le format que tout le monde relit) et passerelle DWG.
# Le DWG appartient à Autodesk : comme FreeCAD ou QGIS, on passe par un convertisseur installé sur l'ordinateur
# (ODA File Converter, gratuit ; à défaut dwg2dxf / dxf2dwg de LibreDWG) : DWG -> DXF à l'import, DXF -> DWG à l'export.
# --------------------------------------------------------------------------

EXPORT_UNITS = {'MM': (0.001, 4), 'CM': (0.01, 5), 'M': (1.0, 6), 'IN': (0.0254, 1), 'FT': (0.3048, 2)}       # (mètres, code $INSUNITS)
SCENE_UNIT_KEY = {'MILLIMETERS': 'MM', 'CENTIMETERS': 'CM', 'METERS': 'M', 'KILOMETERS': 'M', 'MICROMETERS': 'MM',
                  'INCHES': 'IN', 'FEET': 'FT', 'MILES': 'FT', 'THOU': 'IN', 'ADAPTIVE': 'M'}
DWG_VERSIONS = (('ACAD2018', "2018 (AutoCAD 2018 and later)", ""), ('ACAD2013', "2013", ""), ('ACAD2010', "2010", ""),
                ('ACAD2007', "2007", ""), ('ACAD2004', "2004", ""), ('ACAD2000', "2000", ""))
CIRCLE_TOL = 5e-4                 # écart relatif toléré pour reconnaître un cercle ou un arc
CIRCLE_MIN_POLY = 32              # une polyligne n'est prise pour un cercle qu'à partir de ce nombre de points


def export_unit(scene, units='SCENE'):
    """(clé d'unité, facteur unités Blender -> unités du fichier, code $INSUNITS). 'SCENE' : l'unité affichée par la scène."""
    us = scene.unit_settings
    if units == 'SCENE':
        if us.system == 'NONE':
            return 'NONE', 1.0, 0
        units = SCENE_UNIT_KEY.get(us.length_unit, 'M')
    to_m, code = EXPORT_UNITS[units]
    return units, (us.scale_length or 1.0) / to_m, code


def fit_circle(P, closed, tol=CIRCLE_TOL):
    """Cercle ou arc passant par les points P (n, 3), dans l'ordre : (centre, rayon, normale, angle de départ, angle de fin)
    avec les angles en degrés dans le système d'objet d'AutoCAD (sens direct), ou None si ce n'est pas un arc de cercle."""
    P = np.asarray(P, dtype=np.float64)
    n = len(P)
    if n < 8:
        return None
    c0 = P.mean(axis=0)
    _u, sv, vt = np.linalg.svd(P - c0)
    size = float(sv[0])
    if size < 1e-12 or sv[2] > tol * size * 0.5 or sv[1] < 1e-6 * size:
        return None                                        # pas plan, ou aligné
    e1, e2, nrm = vt[0], vt[1], vt[2]
    if float(np.cross(e1, e2) @ nrm) < 0:                 # repère direct : un angle qui croît tourne dans le sens direct autour de nrm
        nrm = -nrm
    x, y = (P - c0) @ e1, (P - c0) @ e2
    A = np.column_stack((2 * x, 2 * y, np.ones(n)))        # cercle des moindres carrés dans le plan
    sol, *_ = np.linalg.lstsq(A, x * x + y * y, rcond=None)
    r2 = sol[2] + sol[0] ** 2 + sol[1] ** 2
    if r2 <= 0:
        return None
    r = math.sqrt(r2)
    d = np.hypot(x - sol[0], y - sol[1])
    if float(np.abs(d - r).max()) > tol * r:
        return None
    ang = np.unwrap(np.arctan2(y - sol[1], x - sol[0]))
    steps = np.diff(ang)
    if len(steps) and (np.all(steps > 0) or np.all(steps < 0)):
        sweep = float(abs(ang[-1] - ang[0]))
    else:
        return None                                        # les points ne tournent pas dans un seul sens
    step = float(np.abs(steps).mean())
    if float(np.abs(steps).max()) > math.radians(50.0):
        return None                                        # trop peu de points pour parler d'un arc
    if closed:
        if abs(sweep + step - TAU) > 0.5 * step:
            return None
    elif sweep > TAU - 0.5 * step:
        return None
    if closed:
        if nrm[2] < -1e-12 or (abs(nrm[2]) <= 1e-12 and (nrm[1] < -1e-12 or (abs(nrm[1]) <= 1e-12 and nrm[0] < 0))):
            nrm = -nrm                                     # cercle entier : le sens n'a pas d'importance, normale vers +Z de préférence
    elif steps[0] < 0:                                     # AutoCAD : un arc tourne dans le sens direct autour de sa normale
        nrm = -nrm
    center = c0 + sol[0] * e1 + sol[1] * e2
    ax, ay, nz = dxf_ocs(nrm)
    a0 = math.degrees(math.atan2(float((P[0] - center) @ ay), float((P[0] - center) @ ax))) % 360.0
    a1 = math.degrees(math.atan2(float((P[-1] - center) @ ay), float((P[-1] - center) @ ax))) % 360.0
    return center, r, nz, a0, a1


def spline_points(sp, resolution=12):
    """Points (locaux) d'une spline de Blender et (fermée, courbe lisse). POLY : ses sommets exacts ; Bézier et NURBS :
    la courbe est échantillonnée (resolution points par segment)."""
    closed = bool(sp.use_cyclic_u)
    if sp.type == 'POLY':
        return [Vector(p.co[:3]) for p in sp.points], closed, False
    res = max(2, int(sp.resolution_u or resolution))
    if sp.type == 'BEZIER':
        bp = list(sp.bezier_points)
        if len(bp) < 2:
            return [Vector(b.co) for b in bp], closed, True
        out = []
        pairs = list(zip(bp, bp[1:])) + ([(bp[-1], bp[0])] if closed else [])
        for a, b in pairs:
            straight = a.handle_right_type == 'VECTOR' and b.handle_left_type == 'VECTOR'
            seg = [a.co.copy(), b.co.copy()] if straight else interpolate_bezier(a.co, a.handle_right, b.handle_left, b.co, res + 1)
            out += [Vector(q) for q in seg[:-1]]
        if not closed:
            out.append(bp[-1].co.copy())
        return out, closed, True
    pts = [(Vector(p.co[:3]), float(p.co[3]) if len(p.co) > 3 else 1.0) for p in sp.points]       # NURBS
    m = len(pts)
    order = max(2, min(int(sp.order_u), m))
    deg = order - 1
    if m < 2:
        return [p for p, _w in pts], closed, True
    ctrl, wts = [tuple(p) for p, _w in pts], [w for _p, w in pts]
    if closed:
        ctrl, wts = ctrl + ctrl[:deg], wts + wts[:deg]
        knots = list(range(len(ctrl) + deg + 1))
    elif sp.use_endpoint_u:
        inner = len(ctrl) - order
        knots = [0.0] * order + [float(i) for i in range(1, inner + 1)] + [float(inner + 1)] * order
    else:
        knots = list(range(len(ctrl) + deg + 1))
    out = [Vector(tuple(q)) for q in dxf_spline_points(deg, knots, ctrl, wts)]
    if closed and len(out) > 2 and (out[0] - out[-1]).length < 1e-9:
        out = out[:-1]
    return out, closed, True


def _layer_name(name, used):
    base = le._dxf_name(name) if name else "0"
    out, k = base, 2
    while out in used and used[out] != name:
        out = (base[:28] + "_" + str(k))
        k += 1
    used[out] = name
    return out


def dxf_collect(context, selected_only=False, faces=True, recognize=True):
    """Entités du modèle affiché, en coordonnées monde (unités Blender) : (entités, calques {nom DXF: couleur ACI}, comptes).
    Entité : ('line', calque, couleur, p1, p2) | ('poly', calque, couleur, points, fermé) | ('circle', calque, couleur,
    centre, rayon, normale) | ('arc', ..., a0, a1) | ('face', calque, couleur, 4 points, arêtes cachées) |
    ('text', calque, couleur, position, hauteur, rotation (degrés), texte, alignement 0/1/2, normale).
    couleur : None = celle du calque. Les blocs (instances) sont exportés à plat."""
    scene = context.scene
    deps = context.evaluated_depsgraph_get()
    ents, layers, used = [], {"0": 7}, {"0": None}
    stats = {"curves": 0, "circles": 0, "faces": 0, "texts": 0, "objects": 0, "skipped": 0}
    cache = {}

    def layer_of(base):
        key = base.name
        if key in cache:
            return cache[key]
        col = base.users_collection[0] if base.users_collection else None
        if col is None or col == scene.collection:
            name, aci = "0", 7
        else:
            name = _layer_name(col.name, used)
            pg = getattr(col, "dessin_layer", None)
            aci = le._aci(tuple(pg.color)) if pg is not None and getattr(pg, "use_color", False) else 7
            layers.setdefault(name, aci)
        own = None
        try:
            c = tuple(base.color[:3])
            if not base.get("wd_lc") and max(abs(v - 1.0) for v in c) > 1e-4:
                own = le._aci(c)
        except (AttributeError, TypeError):
            pass
        cache[key] = (name, own)
        return cache[key]

    for inst in deps.object_instances:
        ob = inst.object
        base = inst.parent.original if inst.is_instance and inst.parent is not None else ob.original
        try:
            if not inst.show_self or ob.type not in {'CURVE', 'MESH', 'FONT'}:
                continue
            if selected_only and not base.select_get():
                continue
            if base.get("wd_gen") or base.hide_viewport:
                continue
            if inst.is_instance and base.type in {'FONT', 'CURVE'}:
                continue            # (la géométrie calculée d'un texte ou d'une courbe : l'objet lui-même est déjà exporté)
        except (ReferenceError, RuntimeError):
            continue
        mw = inst.matrix_world.copy()
        lay, col = layer_of(base)
        stats["objects"] += 1
        if ob.type == 'FONT':
            data = ob.original.data
            sx = Vector(mw.col[0][:3]).length or 1.0
            nrm = Vector(mw.col[2][:3]).normalized() if Vector(mw.col[2][:3]).length > 1e-12 else Vector((0, 0, 1))
            ax, ay, _nz = dxf_ocs(tuple(nrm))
            xdir = Vector(mw.col[0][:3]).normalized()
            rot = math.degrees(math.atan2(float(np.dot(xdir, ay)), float(np.dot(xdir, ax))))
            ydir = Vector(mw.col[1][:3])
            lines = [t for t in data.body.split("\n")]
            h = float(data.size) * sx
            lh = h * float(getattr(data, "space_line", 1.0) or 1.0) * 1.0
            for k, t in enumerate(lines):
                if not t.strip():
                    continue
                pos = mw.translation - ydir.normalized() * (lh * k) if ydir.length > 1e-12 else mw.translation
                ents.append(('text', lay, col, tuple(pos), h, rot, t, {'LEFT': 0, 'CENTER': 1, 'RIGHT': 2}.get(data.align_x, 0), tuple(nrm)))
                stats["texts"] += 1
            continue
        if ob.type == 'CURVE':
            data = ob.original.data
            for sp in data.splines:
                pts, closed, smooth = spline_points(sp, data.resolution_u)
                if len(pts) < 2:
                    continue
                W = np.array([tuple(mw @ p) for p in pts], dtype=np.float64)
                keep = [0] + [i for i in range(1, len(W)) if np.linalg.norm(W[i] - W[i - 1]) > 1e-12]
                W = W[keep]
                if len(W) < 2:
                    continue
                stats["curves"] += 1
                if len(W) == 2:
                    ents.append(('line', lay, col, tuple(W[0]), tuple(W[1])))
                    continue
                fit = fit_circle(W, closed) if recognize and (smooth or len(W) >= CIRCLE_MIN_POLY) else None
                if fit is not None:
                    c, r, nz, a0, a1 = fit
                    ents.append(('circle', lay, col, tuple(c), r, tuple(nz)) if closed else ('arc', lay, col, tuple(c), r, tuple(nz), a0, a1))
                    stats["circles"] += 1
                else:
                    ents.append(('poly', lay, col, W, closed))
            continue
        try:                                         # maillage : faces (3DFACE) et arêtes libres (LINE)
            me = ob.to_mesh()
        except RuntimeError:
            stats["skipped"] += 1
            continue
        try:
            V = [tuple(mw @ v.co) for v in me.vertices]
            if faces and me.polygons:
                me.calc_loop_triangles()
                for poly in me.polygons:
                    vs = list(poly.vertices)
                    if len(vs) in (3, 4):
                        q = [V[i] for i in vs]
                        ents.append(('face', lay, col, q + [q[-1]] * (4 - len(q)), 0))
                        stats["faces"] += 1
                ngon = {p.index: list(p.vertices) for p in me.polygons if len(p.vertices) > 4}
                for lt in me.loop_triangles:
                    ring = ngon.get(lt.polygon_index)
                    if ring is None:
                        continue
                    tri = list(lt.vertices)
                    hidden = 0
                    for e in range(3):                 # arête intérieure à la face : invisible
                        a, b = tri[e], tri[(e + 1) % 3]
                        ia, ib = ring.index(a), ring.index(b)
                        if (ia - ib) % len(ring) not in (1, len(ring) - 1):
                            hidden |= 1 << e
                    q = [V[i] for i in tri]
                    ents.append(('face', lay, col, q + [q[-1]], hidden))
                    stats["faces"] += 1
            used_e = set()
            if me.polygons:
                for poly in me.polygons:
                    for k in poly.edge_keys:
                        used_e.add(k)
            for e in me.edges:
                k = tuple(sorted(e.vertices))
                if k not in used_e:
                    ents.append(('line', lay, col, V[k[0]], V[k[1]]))
                    stats["curves"] += 1
        finally:
            ob.to_mesh_clear()
    return ents, layers, stats


def _num(v):
    t = "%.9f" % (0.0 if abs(v) < 5e-10 else v)
    return t.rstrip("0").rstrip(".") if "." in t else t


def write_model_dxf(path, ents, layers, factor=1.0, unit_code=0):
    """Écrit un DXF R12 (AC1009). factor : unités Blender -> unités du fichier."""
    o = []

    def g(code, val):
        o.append("%d\n%s" % (code, val))

    def pt(code, p, k=factor):
        g(code, _num(p[0] * k)); g(code + 10, _num(p[1] * k)); g(code + 20, _num(p[2] * k))

    def head(kind, lay, col):
        g(0, kind); g(8, lay)
        if col is not None:
            g(62, col)

    def ocs(p, nrm):
        ax, ay, nz = dxf_ocs(nrm)
        q = np.asarray(p, dtype=np.float64)
        return (float(q @ ax), float(q @ ay), float(q @ nz))

    def normal(nrm):
        if abs(nrm[0]) > 1e-9 or abs(nrm[1]) > 1e-9 or nrm[2] < 0:
            g(210, _num(nrm[0])); g(220, _num(nrm[1])); g(230, _num(nrm[2]))

    lo, hi = None, None
    for e in ents:
        if e[0] in ('line',):
            P = np.array([e[3], e[4]])
        elif e[0] == 'poly':
            P = np.asarray(e[3])
        elif e[0] == 'face':
            P = np.array(e[3])
        elif e[0] in ('circle', 'arc'):
            c, r = np.array(e[3]), e[4]
            P = np.array([c - r, c + r])
        else:
            P = np.array([e[3]])
        lo = P.min(axis=0) if lo is None else np.minimum(lo, P.min(axis=0))
        hi = P.max(axis=0) if hi is None else np.maximum(hi, P.max(axis=0))
    if lo is None:
        lo, hi = np.zeros(3), np.zeros(3)
    g(999, "Wanderer CAD")
    g(999, DXF_UNITS_TAG + str(int(unit_code)))
    g(0, "SECTION"); g(2, "HEADER")
    g(9, "$ACADVER"); g(1, "AC1009")
    g(9, "$DWGCODEPAGE"); g(3, "ANSI_1252")
    g(9, "$INSBASE"); pt(10, (0.0, 0.0, 0.0), 1.0)
    g(9, "$EXTMIN"); pt(10, lo)
    g(9, "$EXTMAX"); pt(10, hi)
    g(0, "ENDSEC")
    g(0, "SECTION"); g(2, "TABLES")
    g(0, "TABLE"); g(2, "LTYPE"); g(70, 1)
    g(0, "LTYPE"); g(2, "CONTINUOUS"); g(70, 0); g(3, "Solid line"); g(72, 65); g(73, 0); g(40, "0.0")
    g(0, "ENDTAB")
    g(0, "TABLE"); g(2, "LAYER"); g(70, len(layers))
    for name, aci in layers.items():
        g(0, "LAYER"); g(2, name); g(70, 0); g(62, aci); g(6, "CONTINUOUS")
    g(0, "ENDTAB")
    g(0, "TABLE"); g(2, "STYLE"); g(70, 1)
    g(0, "STYLE"); g(2, "STANDARD"); g(70, 0); g(40, "0.0"); g(41, "1.0"); g(50, "0.0"); g(71, 0); g(42, "0.2"); g(3, "txt"); g(4, "")
    g(0, "ENDTAB")
    g(0, "ENDSEC")
    g(0, "SECTION"); g(2, "BLOCKS"); g(0, "ENDSEC")
    g(0, "SECTION"); g(2, "ENTITIES")
    for e in ents:
        kind, lay, col = e[0], e[1], e[2]
        if kind == 'line':
            head("LINE", lay, col); pt(10, e[3]); pt(11, e[4])
        elif kind == 'poly':
            P, closed = np.asarray(e[3]), e[4]
            flat = float(np.ptp(P[:, 2])) <= 1e-9 * max(1.0, float(np.abs(P).max()))
            head("POLYLINE", lay, col); g(66, 1)
            if flat:
                pt(10, (0.0, 0.0, float(P[0, 2]))); g(70, 1 if closed else 0)
            else:
                pt(10, (0.0, 0.0, 0.0), 1.0); g(70, 8 + (1 if closed else 0))
            for p in P:
                g(0, "VERTEX"); g(8, lay); pt(10, p)
                if not flat:
                    g(70, 32)
            g(0, "SEQEND"); g(8, lay)
        elif kind in ('circle', 'arc'):
            head("CIRCLE" if kind == 'circle' else "ARC", lay, col)
            pt(10, ocs(e[3], e[5])); g(40, _num(e[4] * factor))
            if kind == 'arc':
                g(50, _num(e[6])); g(51, _num(e[7]))
            normal(e[5])
        elif kind == 'face':
            head("3DFACE", lay, col)
            for k, p in enumerate(e[3]):
                pt(10 + k, p)
            if e[4]:
                g(70, e[4])
        elif kind == 'text':
            _k, _l, _c, pos, h, rot, text, align, nrm = e
            head("TEXT", lay, col)
            q = ocs(pos, nrm)
            pt(10, q); g(40, _num(h * factor)); g(1, dxf_escape_text(text))
            if abs(rot) > 1e-9:
                g(50, _num(rot))
            g(7, "STANDARD")
            if align:
                g(72, align); pt(11, q)
            normal(nrm)
    g(0, "ENDSEC"); g(0, "EOF")
    with open(path, "w", encoding="cp1252", newline="\n") as f:
        f.write("\n".join(o) + "\n")
    return len(ents)


def dxf_escape_text(t):
    """Texte d'une entité TEXT : sur une ligne. Le fichier est en Windows-1252 (page de code d'un DXF R12 : les accents
    français y sont) ; un caractère qui n'y est pas est écrit \\U+XXXX, comme le fait AutoCAD."""
    out = []
    for ch in t.replace("\r", " ").replace("\n", " "):
        try:
            ok = ord(ch) >= 32 and len(ch.encode("cp1252")) == 1
        except UnicodeEncodeError:
            ok = False
        out.append(ch if ok else "\\U+%04X" % ord(ch))
    return "".join(out)


# ---- convertisseur DWG <-> DXF ----

def cad_converter():
    """Convertisseur trouvé sur l'ordinateur : ('oda', chemin) | ('libredwg', dossier) | None."""
    cand = []
    custom = (pref("oda_path") or "").strip()
    if custom:
        custom = bpy.path.abspath(custom)
        if custom.lower().endswith(".app"):
            custom = os.path.join(custom, "Contents", "MacOS", "ODAFileConverter")
        cand.append(custom)
    if sys.platform == "darwin":
        cand += ["/Applications/ODAFileConverter.app/Contents/MacOS/ODAFileConverter",
                 os.path.expanduser("~/Applications/ODAFileConverter.app/Contents/MacOS/ODAFileConverter")]
    elif sys.platform.startswith("win"):
        import glob
        for root in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
            cand += sorted(glob.glob(os.path.join(root, "ODA", "ODAFileConverter*", "ODAFileConverter.exe")), reverse=True)
    else:
        cand += ["/usr/bin/ODAFileConverter", "/usr/local/bin/ODAFileConverter"]
    which = shutil.which("ODAFileConverter")
    if which:
        cand.append(which)
    for c in cand:
        if c and os.path.isfile(c):
            return ('oda', c)
    a, b = shutil.which("dwg2dxf"), shutil.which("dxf2dwg")
    if a or b:
        return ('libredwg', os.path.dirname(a or b))
    return None


CONVERTER_HELP = ("DWG needs a converter on this computer: install the free ODA File Converter (opendesign.com > "
                  "ODA File Converter), or set its location in the Wanderer CAD preferences (DXF / DWG). DXF works without it")


def cad_convert(src, to_ext, version='ACAD2018', timeout=300):
    """Convertit un fichier DWG en DXF ou DXF en DWG avec le convertisseur de l'ordinateur. Retourne le chemin du fichier
    produit, dans un dossier temporaire (à l'appelant de le déplacer). Lève RuntimeError avec un message pour l'utilisateur."""
    conv = cad_converter()
    if conv is None:
        raise RuntimeError(CONVERTER_HELP)
    to_ext = to_ext.upper().lstrip(".")
    name = os.path.basename(src)
    stem, ext = os.path.splitext(name)
    tmp_in, tmp_out = tempfile.mkdtemp(prefix="wd_cad_in_"), tempfile.mkdtemp(prefix="wd_cad_out_")
    try:
        shutil.copyfile(src, os.path.join(tmp_in, name))
        target = os.path.join(tmp_out, stem + "." + to_ext.lower())
        if conv[0] == 'oda':
            # ODAFileConverter "dossier d'entrée" "dossier de sortie" version type récursif audit [filtre]
            cmd = [conv[1], tmp_in, tmp_out, version, to_ext, "0", "1", "*" + ext.upper()]
        else:
            tool = os.path.join(conv[1], "dwg2dxf" if to_ext == "DXF" else "dxf2dwg")
            if not os.path.isfile(tool) and not shutil.which(os.path.basename(tool)):
                raise RuntimeError(CONVERTER_HELP)
            cmd = [tool, "-y", "-o", target, os.path.join(tmp_in, name)]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise RuntimeError("The DWG converter did not answer (stopped after %d s)" % timeout)
        except OSError as ex:
            raise RuntimeError("Cannot start the DWG converter: %s" % ex)
        found = target if os.path.isfile(target) else None
        if found is None:                           # (nom de fichier rendu en majuscules ou autrement par le convertisseur)
            for f in os.listdir(tmp_out):
                if f.lower().endswith("." + to_ext.lower()):
                    found = os.path.join(tmp_out, f)
                    break
        if found is None or os.path.getsize(found) == 0:
            tail = (res.stderr or res.stdout or b"").decode("utf-8", "replace").strip().splitlines()[-1:] if res else []
            raise RuntimeError("The DWG converter produced no file" + (": " + tail[0] if tail else ""))
        keep = tempfile.mkdtemp(prefix="wd_cad_")
        out = os.path.join(keep, os.path.basename(found))
        shutil.move(found, out)
        return out
    finally:
        shutil.rmtree(tmp_in, ignore_errors=True)
        shutil.rmtree(tmp_out, ignore_errors=True)


def dxf_file_to(path, dxf_path, version='ACAD2018'):
    """Place à `path` le fichier demandé : le DXF lui-même, ou sa conversion en DWG quand l'extension est .dwg."""
    if path.lower().endswith(".dwg"):
        made = cad_convert(dxf_path, "DWG", version)
        try:
            shutil.move(made, path)
        finally:
            shutil.rmtree(os.path.dirname(made), ignore_errors=True)
    elif os.path.abspath(dxf_path) != os.path.abspath(path):
        shutil.move(dxf_path, path)
    return path


class DESSIN_OT_export_cad(bpy.types.Operator):
    bl_idname = "dessin.export_cad"
    bl_label = "Export DXF / DWG"
    bl_description = ("Exports the model as a DXF (R12) or a DWG drawing: lines, polylines, arcs and circles, 3D faces of the solids "
                      "and text, with the layers and their colors. DWG needs the free ODA File Converter on this computer")
    bl_options = {'REGISTER'}

    filepath: bpy.props.StringProperty(subtype='FILE_PATH', options={'SKIP_SAVE'})
    filter_glob: bpy.props.StringProperty(default="*.dxf;*.dwg", options={'HIDDEN'})
    check_existing: bpy.props.BoolProperty(default=True, options={'HIDDEN'})
    kind: bpy.props.EnumProperty(name="Format", default='DXF',
                                 items=(('DXF', "DXF", "Text format read by every CAD program; nothing to install"),
                                        ('DWG', "DWG", "AutoCAD drawing, written through the ODA File Converter")))
    version: bpy.props.EnumProperty(name="DWG version", default='ACAD2018', items=DWG_VERSIONS)
    selected: bpy.props.BoolProperty(name="Selection only", default=False, description="Exports only the selected objects")
    units: bpy.props.EnumProperty(
        name="Units", default='SCENE',
        items=(('SCENE', "Scene units", "The unit shown by the scene (millimeters, meters, inches...)"),
               ('MM', "Millimeters", ""), ('CM', "Centimeters", ""), ('M', "Meters", ""), ('IN', "Inches", ""), ('FT', "Feet", "")))
    faces: bpy.props.BoolProperty(name="Solids as 3D faces", default=True,
                                  description="Exports the faces of the meshes as 3DFACE entities (off: only curves and text)")
    arcs: bpy.props.BoolProperty(name="Arcs and circles", default=True,
                                 description="Writes round curves as true ARC and CIRCLE entities (off: polylines)")

    def invoke(self, context, event):
        if not self.filepath:
            base = os.path.splitext(bpy.data.filepath)[0] if bpy.data.filepath else os.path.join(os.path.expanduser("~"), "model")
            self.filepath = base + "." + self.kind.lower()
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, "kind")
        row = col.row()
        row.enabled = self.kind == 'DWG'
        row.prop(self, "version")
        if self.kind == 'DWG' and cad_converter() is None:
            col.label(text="ODA File Converter not found", icon='ERROR')
        for k in ("selected", "units", "faces", "arcs"):
            col.prop(self, k)

    def execute(self, context):
        name = os.path.basename(self.filepath or "")
        if not name or name.startswith("."):
            self.report({'WARNING'}, "Export: no file name")
            return {'CANCELLED'}
        path = bpy.path.abspath(self.filepath)
        low = path.lower()
        if low.endswith(".dwg"):
            kind = 'DWG'
        elif low.endswith(".dxf"):
            kind = 'DXF'
        else:
            kind = self.kind
            path = os.path.splitext(path)[0] + "." + kind.lower()
        if kind == 'DWG' and cad_converter() is None:
            self.report({'ERROR'}, CONVERTER_HELP)
            return {'CANCELLED'}
        t0 = time.monotonic()
        ents, layers, stats = dxf_collect(context, self.selected, self.faces, self.arcs)
        if not ents:
            self.report({'WARNING'}, "Nothing to export (no visible curve, solid or text" + (" in the selection)" if self.selected else ")"))
            return {'CANCELLED'}
        key, factor, code = export_unit(context.scene, self.units)
        tmp = tempfile.mkdtemp(prefix="wd_dxf_")
        try:
            dxf = os.path.join(tmp, os.path.splitext(os.path.basename(path))[0] + ".dxf")
            write_model_dxf(dxf, ents, layers, factor, code)
            dxf_file_to(path, dxf, self.version)
        except RuntimeError as ex:
            self.report({'ERROR'}, str(ex))
            return {'CANCELLED'}
        except OSError as ex:
            self.report({'ERROR'}, f"Cannot write the file: {ex}")
            return {'CANCELLED'}
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        unit = {'MM': "mm", 'CM': "cm", 'M': "m", 'IN': "in", 'FT': "ft", 'NONE': "units"}[key]
        self.report({'INFO'}, f"{kind}: {len(ents)} entities ({stats['curves']} curves, {stats['circles']} arcs / circles, {stats['faces']} faces, "
                              f"{stats['texts']} texts) on {len(layers)} layers, in {unit}, {time.monotonic() - t0:.1f}s  ->  {os.path.basename(path)}")
        return {'FINISHED'}


def menu_export_cad(self, context):
    self.layout.operator(DESSIN_OT_export_cad.bl_idname, text="DXF / DWG drawing (Wanderer)")


class DESSIN_OT_import_cad(bpy.types.Operator):
    bl_idname = "dessin.import_cad"
    bl_label = "Import DXF / DWG"
    bl_description = ("Imports a DXF or a DWG drawing: lines, polylines, arcs, circles, ellipses, splines, 3D faces, text and blocks, "
                      "with layers as layers (collections) and their colors. DWG needs the free ODA File Converter on this computer")
    bl_options = {'REGISTER', 'UNDO'}

    filepath: bpy.props.StringProperty(subtype='FILE_PATH')
    filter_glob: bpy.props.StringProperty(default="*.dxf;*.dwg", options={'HIDDEN'})
    units: bpy.props.EnumProperty(
        name="Units", default='AUTO',
        items=(('AUTO', "From the file", "Uses the drawing units written in the file (unitless: numbers are kept)"),
               ('NONE', "Keep numbers", "No conversion"), ('MM', "Millimeters", ""), ('CM', "Centimeters", ""),
               ('M', "Meters", ""), ('IN', "Inches", ""), ('FT', "Feet", "")))
    mode: bpy.props.EnumProperty(
        name="Objects", default='AUTO',
        items=(('AUTO', "Automatic", "One object per entity, or one per layer when the drawing is large (over 3000 entities)"),
               ('ENTITY', "One per entity", "Every line, polyline, circle... is its own object"),
               ('LAYER', "One per layer", "All the geometry of a layer in one object: lightest for large drawings")))
    layers: bpy.props.BoolProperty(name="Layers", default=True, description="Creates a layer (collection) for each drawing layer, with its color")
    entity_colors: bpy.props.BoolProperty(name="Entity colors", default=True, description="Keeps the colors set on individual entities")
    text: bpy.props.BoolProperty(name="Text", default=True, description="Imports TEXT and MTEXT as text objects")
    blocks: bpy.props.BoolProperty(name="Blocks and dimensions", default=True, description="Expands block references and dimension drawings")
    segments: bpy.props.IntProperty(name="Circle segments", default=64, min=12, max=720, description="Segments of a full circle")

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def draw(self, context):
        col = self.layout.column()
        for k in ("units", "mode", "layers", "entity_colors", "text", "blocks", "segments"):
            col.prop(self, k)

    def execute(self, context):
        path = bpy.path.abspath(self.filepath)
        if not os.path.isfile(path):
            self.report({'ERROR'}, "File not found")
            return {'CANCELLED'}
        t0 = time.monotonic()
        made = None
        try:
            src = path
            if path.lower().endswith(".dwg"):          # DWG : converti en DXF par le convertisseur de l'ordinateur, puis lu
                made = cad_convert(path, "DXF")
                src = made
            with open(src, "rb") as f:
                header, layers, blocks, ents = dxf_parse(f.read())
        except RuntimeError as ex:
            self.report({'ERROR'}, str(ex))
            return {'CANCELLED'}
        except (OSError, ValueError) as ex:
            self.report({'ERROR'}, f"Cannot read the file: {ex}")
            return {'CANCELLED'}
        finally:
            if made:
                shutil.rmtree(os.path.dirname(made), ignore_errors=True)
        opts = {"segments": self.segments, "text": self.text, "blocks": self.blocks, "mode": self.mode, "units": self.units,
                "layers": self.layers, "entity_colors": self.entity_colors}
        stats = {"inserts": 0, "skipped": {}, "truncated": False}
        prims = []
        dxf_explode(ents, blocks, layers, np.eye(4), None, prims, stats, opts)
        if not prims:
            self.report({'WARNING'}, "Nothing to import (the drawing is empty, or only contains unsupported entities)")
            return {'CANCELLED'}
        label = os.path.basename(path)
        n, mode = dxf_build(context, header, layers, prims, opts, label)
        msg = f"{n} object(s) from {len(prims)} entities in {time.monotonic() - t0:.1f}s ({'one per entity' if mode == 'ENTITY' else 'one per layer'})"
        if stats["skipped"]:
            msg += "   Not imported: " + ", ".join(f"{k} x{v}" for k, v in sorted(stats["skipped"].items()))
        if stats["truncated"]:
            msg += "   (block references limited to 20000)"
        note = _LAYERCOL.pop("import_note", "")
        if note:
            msg += "   " + note
        self.report({'INFO'}, msg)
        return {'FINISHED'}


def menu_import_cad(self, context):
    self.layout.operator(DESSIN_OT_import_cad.bl_idname, text="DXF / DWG drawing (Wanderer)")


def _late_imports():
    pass
