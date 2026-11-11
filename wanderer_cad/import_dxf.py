"""Wanderer CAD : Import DXF / DWG."""

import bpy
import math
import numpy as np
import os
import re
import time

from .core import TAU
from .layers import _LAYERCOL, find_layer_collection


# --------------------------------------------------------------------------
# Import DXF (calques, couleurs, blocs, textes).
# --------------------------------------------------------------------------

DXF_UNITS_M = {1: 0.0254, 2: 0.3048, 3: 1609.344, 4: 0.001, 5: 0.01, 6: 1.0, 7: 1000.0, 8: 2.54e-8, 9: 2.54e-5,
               10: 0.9144, 11: 1e-10, 12: 1e-9, 13: 1e-6, 14: 0.1, 15: 10.0, 16: 100.0, 17: 1e9}
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


class DESSIN_OT_import_cad(bpy.types.Operator):
    bl_idname = "dessin.import_cad"
    bl_label = "Import DXF"
    bl_description = ("Imports a DXF drawing: lines, polylines, arcs, circles, ellipses, splines, 3D faces, text and blocks, "
                      "with layers as layers (collections) and their colors")
    bl_options = {'REGISTER', 'UNDO'}

    filepath: bpy.props.StringProperty(subtype='FILE_PATH')
    filter_glob: bpy.props.StringProperty(default="*.dxf", options={'HIDDEN'})
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
        try:
            with open(path, "rb") as f:
                header, layers, blocks, ents = dxf_parse(f.read())
        except (OSError, ValueError) as ex:
            self.report({'ERROR'}, f"Cannot read the file: {ex}")
            return {'CANCELLED'}
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
    self.layout.operator(DESSIN_OT_import_cad.bl_idname, text="DXF drawing (Wanderer)")


def _late_imports():
    pass
