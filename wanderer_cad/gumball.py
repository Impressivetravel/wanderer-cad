"""Wanderer CAD : Gizmo : déplacer, pivoter, mettre à l'échelle."""

import bmesh
import bpy

from .units_text import typing_add
import math
import numpy as np
import time
from bpy_extras.view3d_utils import location_3d_to_region_2d, region_2d_to_origin_3d, region_2d_to_vector_3d
from mathutils import Matrix, Vector, geometry

from .linetypes import base_wire_world
from .core import (
    has_lt,
    AXES3, GB_SNAP_FROM_ITEMS, TAU, _LAST_TYPED, copy_held, copy_key_name, copy_mod_event, copy_shift, copy_update, fmt_typed, last_typed, lock_held,
    lock_key_name, osnap, pref, tr_text, unit_info,
)
from .snapping import SNAP_BIAS_LUT, SnapData, collect_snap_points, exclude_snap, curve_edit_apply, curve_edit_selection, edit_selection
from .drawing import draw_snap_marker, find_snap_in, get_shader, line_px, px_scale
from .base import DessinBase
from .subd import (
    drag_copy_commit, expand_groups, ghost_for_edit, ghost_for_objects, ghost_hide, ghost_show,
)


# --------------------------------------------------------------------------
# Gizmo : poignées au centre de la sélection (déplacer / pivoter / mettre à l'échelle, valeur au clavier)
# --------------------------------------------------------------------------

GUMBALL_COLORS = ((0.93, 0.18, 0.18), (0.35, 0.85, 0.20), (0.22, 0.42, 0.95))
GUMBALL_AXES = "XYZ"
GUMBALL_PX = 95.0   # longueur des flèches en pixels


def gumball_k(context):
    """Pixels écran par pixel d'interface pour le Gizmo : échelle de l'écran (plafonnée à 2, écrans Retina) x réglage utilisateur."""
    try:
        size = context.scene.dessin.gumball_size / 100.0
    except (AttributeError, ReferenceError):
        size = 1.0
    return min(px_scale(), 2.0) * size


_GB_EDIT = {"t": 0.0, "sig": None, "res": (None, [])}


_GB_PIV = {"sig": None}


def _rot_cols(m):
    m3 = m.to_3x3()
    return tuple(Vector(m3.col[i]).normalized() for i in range(3))


def gumball_axes(context):
    """Les trois axes (monde) des poignées du Gizmo : l'orientation de transformation de Blender (liste Global / Local / Normal... de l'en-tête)."""
    try:
        slot = context.scene.transform_orientation_slots[0]
        kind = slot.type
        act = context.view_layer.objects.active
        if kind == 'GLOBAL':
            return AXES3
        if kind in {'LOCAL', 'GIMBAL'} and act is not None:
            return _rot_cols(act.matrix_world.to_quaternion().to_matrix())
        if kind == 'NORMAL':
            if context.mode == 'EDIT_MESH':
                n = extrude_direction(context)
                if n is not None:
                    return _rot_cols(n.to_track_quat('Z', 'Y').to_matrix())
            elif act is not None:
                return _rot_cols(act.matrix_world.to_quaternion().to_matrix())
        elif kind == 'VIEW' and context.region_data is not None:
            q = context.region_data.view_rotation
            return tuple((q @ AXES3[i]).normalized() for i in range(3))
        elif kind == 'CURSOR':
            return _rot_cols(context.scene.cursor.matrix.to_quaternion().to_matrix())
        elif kind == 'PARENT' and act is not None:
            ref = act.parent if act.parent is not None else act
            return _rot_cols(ref.matrix_world.to_quaternion().to_matrix())
        elif kind not in {'GLOBAL', 'LOCAL', 'GIMBAL', 'NORMAL', 'VIEW', 'CURSOR', 'PARENT'}:
            co = slot.custom_orientation
            if co is not None:
                return _rot_cols(co.matrix)
    except (AttributeError, RuntimeError, ReferenceError, TypeError, IndexError):
        pass
    return AXES3


# Pendant qu'on transforme la sélection (comme dans Rhino), le Gizmo accompagne l'objet : son centre et ses axes de départ
# sont gardés ici, et la transformation en cours (« X ») leur est appliquée à chaque dessin. Sans repère de départ figé,
# il était recalculé depuis la sélection à chaque mouvement de souris (lent, et ses axes sautaient pendant une rotation).
# Poignée du Gizmo sous la souris pendant qu'Alt est maintenu : Blender n'éclaire plus ses poignées avec Alt (Alt + clic
# ne leur est jamais donné), alors Wanderer l'éclaire lui-même pour qu'on voie ce qu'Alt + glisser va copier.
_ALT_HOVER = {"area": 0, "handle": None}

_GB_DRAG = {"pivot": None, "axes": None, "owner": "", "X": None, "typing": False}


def gumball_freeze(context, pivot, owner):
    """Fige le Gizmo en `pivot` tant que l'opération modale `owner` (début du nom de sa classe) est en cours."""
    try:
        _GB_DRAG["axes"] = [Vector(a) for a in gumball_axes(context)]
        _GB_DRAG["pivot"] = Vector(pivot)
        _GB_DRAG["owner"] = owner
        _GB_DRAG["X"] = None
    except (AttributeError, TypeError, ValueError, ReferenceError):
        gumball_unfreeze()


# ---- rotation au Gizmo : part d'arc parcourue, flèche du sens et angle (#1) ----
_GB_ROT = {"on": None, "handle": None}
ROT_IND_PX = 72.0          # rayon de l'indicateur (pixels d'interface)
ROT_IND_COL = (1.0, 0.82, 0.40)


def gumball_rot_show(pivot, axis, bu, bv, a0, deg):
    """Rotation en cours : centre, axe, base du plan (bu, bv), angle de départ (radians) et angle parcouru (degrés)."""
    _GB_ROT["on"] = (Vector(pivot), Vector(axis), Vector(bu), Vector(bv), float(a0), float(deg))
    _rot_redraw()


def gumball_rot_hide():
    if _GB_ROT["on"] is not None:
        _GB_ROT["on"] = None
        _rot_redraw()


def _rot_redraw():
    try:
        for win in bpy.context.window_manager.windows:
            for a in win.screen.areas:
                if a.type == 'VIEW_3D':
                    a.tag_redraw()
    except (AttributeError, ReferenceError, RuntimeError):
        pass


def rot_indicator_geometry(region, rv3d, rot, radius_px):
    """Points écran de l'indicateur : (centre, arc [points], bout de flèche, texte) ; None si hors vue."""
    P, axis, bu, bv, a0, deg = rot
    c = location_3d_to_region_2d(region, rv3d, P)
    if c is None:
        return None
    s = 0.0
    for d in (bu, bv):
        q = location_3d_to_region_2d(region, rv3d, P + d)
        if q is not None:
            s = max(s, (q - c).length)
    if s < 1e-9:
        return None
    r = radius_px / s
    n = max(6, min(180, int(abs(deg) / 3.0) + 2))
    pts = []
    for k in range(n + 1):
        a = a0 + math.radians(deg) * k / n
        q = location_3d_to_region_2d(region, rv3d, P + (bu * math.cos(a) + bv * math.sin(a)) * r)
        if q is None:
            return None
        pts.append(q)
    return c, pts


_GB_SNAPMARK = {"pt": None, "kind": 0}        # point accroché pendant un glisser du Gizmo (Snappy, B : point de base)


def gumball_snapmark(pt=None, kind=0):
    _GB_SNAPMARK["pt"], _GB_SNAPMARK["kind"] = (pt.copy() if pt is not None else None), kind


def _snapmark_draw():
    pt = _GB_SNAPMARK["pt"]
    if pt is None:
        return
    ctx = bpy.context
    q = location_3d_to_region_2d(ctx.region, ctx.region_data, pt)
    if q is not None:
        draw_snap_marker(q.x, q.y, _GB_SNAPMARK["kind"])


def rot_indicator_draw():
    if _GB_SNAPMARK["pt"] is not None:
        try:
            _snapmark_draw()
        except Exception:
            pass
    if _GB_ROT["on"] is None:
        return
    try:
        _rot_indicator_draw()
    except Exception:                   # (un dessin raté ne doit jamais bloquer la vue)
        try:
            import gpu
            gpu.state.blend_set('NONE')
            gpu.state.line_width_set(1.0)
        except Exception:
            pass


def _rot_indicator_draw():
    rot = _GB_ROT["on"]
    if rot is None:
        return
    context = bpy.context
    region, rv3d = context.region, context.region_data
    if region is None or rv3d is None:
        return
    import blf
    import gpu
    from gpu_extras.batch import batch_for_shader
    sc = px_scale()
    geo = rot_indicator_geometry(region, rv3d, rot, ROT_IND_PX * sc)
    if geo is None:
        return
    c, pts = geo
    deg = rot[5]
    sh = get_shader('2D')
    sh.bind()
    gpu.state.blend_set('ALPHA')
    col = ROT_IND_COL
    if abs(deg) > 1e-6:
        tris = []
        for k in range(len(pts) - 1):
            tris += [tuple(c), tuple(pts[k]), tuple(pts[k + 1])]
        sh.uniform_float("color", (col[0], col[1], col[2], 0.25))
        batch_for_shader(sh, 'TRIS', {"pos": tris}).draw(sh)
    gpu.state.line_width_set(line_px(2.0))
    sh.uniform_float("color", (col[0], col[1], col[2], 0.95))
    batch_for_shader(sh, 'LINES', {"pos": [tuple(c), tuple(pts[0]), tuple(c), tuple(pts[-1])]}).draw(sh)
    if len(pts) > 1 and abs(deg) > 1e-6:
        batch_for_shader(sh, 'LINE_STRIP', {"pos": [tuple(p) for p in pts]}).draw(sh)
        # pointe de flèche au bout de l'arc, dans le sens de la rotation
        tip = pts[-1]
        t = pts[-1] - pts[-2]
        if t.length > 1e-6:
            t.normalize()
            nrm = Vector((-t.y, t.x))
            L, W = 11.0 * sc, 5.5 * sc
            head = [tuple(tip + t * L * 0.6), tuple(tip - t * L * 0.4 + nrm * W), tuple(tip - t * L * 0.4 - nrm * W)]
            batch_for_shader(sh, 'TRIS', {"pos": head}).draw(sh)
    gpu.state.line_width_set(1.0)
    # angle écrit à côté du bout de l'arc
    txt = f"{deg:.1f}°"
    end = pts[-1]
    d = end - c
    d = d.normalized() if d.length > 1e-6 else Vector((1.0, 0.0))
    size = int(13 * sc)
    blf.size(0, size)
    w, h = blf.dimensions(0, txt)
    pos = end + d * (14.0 * sc) + Vector((-w / 2.0, -h / 2.0)) + Vector((d.x * w / 2.0, 0.0))
    pad = 4.0 * sc
    box = [(pos.x - pad, pos.y - pad), (pos.x + w + pad, pos.y - pad), (pos.x + w + pad, pos.y + h + pad),
           (pos.x - pad, pos.y - pad), (pos.x + w + pad, pos.y + h + pad), (pos.x - pad, pos.y + h + pad)]
    sh.uniform_float("color", (0.07, 0.07, 0.08, 0.85))
    batch_for_shader(sh, 'TRIS', {"pos": box}).draw(sh)
    blf.color(0, col[0], col[1], col[2], 1.0)
    blf.position(0, pos.x, pos.y, 0)
    blf.draw(0, txt)
    gpu.state.blend_set('NONE')


def register_rot_indicator():
    if _GB_ROT["handle"] is None:
        _GB_ROT["handle"] = bpy.types.SpaceView3D.draw_handler_add(rot_indicator_draw, (), 'WINDOW', 'POST_PIXEL')


def unregister_rot_indicator():
    h = _GB_ROT["handle"]
    _GB_ROT["handle"] = None
    _GB_ROT["on"] = None
    if h is not None:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(h, 'WINDOW')
        except (ValueError, RuntimeError):
            pass


def gumball_drag_xform(X):
    """Transformation appliquée en ce moment à la sélection : le Gizmo la suit (déplacement, rotation)."""
    _GB_DRAG["X"] = None if X is None else X.copy()


def gumball_typing():
    """Une valeur est en cours de saisie dans la bulle : le Gizmo ne garde que ses flèches de déplacement (Rhino)."""
    return bool(_GB_DRAG["typing"]) and _GB_DRAG["pivot"] is not None


def gumball_unfreeze(context=None):
    _GB_DRAG["typing"] = False
    _GB_DRAG["pivot"] = _GB_DRAG["axes"] = _GB_DRAG["X"] = None
    if context is not None:
        try:
            for area in context.screen.areas:           # les poignées rejoignent tout de suite la sélection
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
        except (AttributeError, ReferenceError, RuntimeError):
            pass


def gumball_frozen(context):
    """(centre, axes) des poignées figées, ou None si aucun déplacement n'est en cours. Si l'opération s'est terminée sans
    prévenir (annulée par Blender), le Gizmo est libéré."""
    if _GB_DRAG["pivot"] is None:
        return None
    try:
        ops = context.window.modal_operators
    except (AttributeError, RuntimeError, ReferenceError):
        ops = None
    if ops is not None and not any(op.bl_idname.startswith(_GB_DRAG["owner"]) for op in ops):
        gumball_unfreeze()
        return None
    X = _GB_DRAG["X"]
    if X is None:
        return _GB_DRAG["pivot"], _GB_DRAG["axes"]
    R = X.to_3x3()
    axes = []
    for a in _GB_DRAG["axes"]:
        v = R @ a
        axes.append(v.normalized() if v.length > 1e-9 else Vector(a))      # (échelle : les axes gardent leur direction)
    return X @ _GB_DRAG["pivot"], axes


def _object_world_points(o, dg):
    """Sommets (monde) d'un objet tel qu'affiché : maillage évalué (modificateurs, courbes, textes), boîte des objets d'un
    bloc, ou son origine ; tableau N×3, ou None."""
    try:
        if o.type in {'MESH', 'CURVE'} and has_lt(o):
            bw = base_wire_world(o)             # trait à tirets : ses vrais sommets, pas les bouts des tirets
            if bw is not None and len(bw[0]):
                return bw[0]
        if o.type in {'MESH', 'CURVE', 'SURFACE', 'FONT', 'META'}:
            ev = o.evaluated_get(dg)
            me = ev.to_mesh()
            try:
                n = len(me.vertices) if me is not None else 0
                co = np.empty(n * 3, dtype=np.float64)
                if n:
                    me.vertices.foreach_get("co", co)
            finally:
                ev.to_mesh_clear()
            if not n:
                return None
            M = np.array(ev.matrix_world, dtype=np.float64)
            return co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3]
        coll = o.instance_collection if o.instance_type == 'COLLECTION' else None
        if coll is not None:
            base = o.matrix_world @ Matrix.Translation(-coll.instance_offset)
            pts = [tuple(base @ io.matrix_world @ Vector(c)) for io in coll.all_objects for c in io.bound_box]
            if pts:
                return np.array(pts, dtype=np.float64)
        return np.array([tuple(o.matrix_world.translation)], dtype=np.float64)
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
        return None


def selection_points(context, items, cap=400000):
    """Sommets des objets déplacés et de leurs enfants, à leur position de départ (items : [(objet, matrice de départ)]) :
    tableau N×3, ou None. Sert à caler le point de la sélection le plus proche (Snappy Dragging)."""
    try:
        dg = context.evaluated_depsgraph_get()
    except (AttributeError, RuntimeError):
        return None
    chunks, total = [], 0
    for obj, mw0 in items:
        try:
            B = np.array(mw0 @ obj.matrix_world.inverted(), dtype=np.float64)   # position actuelle -> départ
            objs = [obj] + list(obj.children_recursive)
        except (AttributeError, ReferenceError, ValueError):
            continue
        for o in objs:
            pts = _object_world_points(o, dg)
            if pts is None or not len(pts):
                continue
            chunks.append(pts @ B[:3, :3].T + B[:3, 3])
            total += len(pts)
            if total > cap:
                break
        if total > cap:
            break
    return np.concatenate(chunks) if chunks else None


def _points_snapdata(P, kind=4, edges=None):
    """Petit jeu d'accrochage fait de points (Vertex) et, si donnés, de segments (Near, Int...)."""
    P = np.asarray(P, dtype=np.float64).reshape(-1, 3)
    k = np.full(len(P), kind, dtype=np.int8)
    d = SnapData((P, np.hstack((P, np.ones((len(P), 1)))), k, SNAP_BIAS_LUT[k]))
    d.edges = edges
    return d


def edit_moving_points(items):
    """Mode Édition : les sommets (ou points de courbe) déplacés, à leur position de départ (N×3), ou None."""
    chunks = []
    for it in items:
        try:
            w0 = np.asarray(it[2], dtype=np.float64).reshape(-1, 3)
        except (IndexError, TypeError, ValueError):
            continue
        if len(w0):
            chunks.append(w0)
    return np.concatenate(chunks) if chunks else None


def edit_static_snap(items, cap=2000000):
    """Mode Édition : ce qui ne bouge pas dans les maillages édités (sommets non sélectionnés, milieux et segments des
    arêtes entre eux) : on peut poser un sommet sur un autre sommet du même maillage. Lu en tableaux (maillages denses)."""
    P_all, M_all, S_all = [], [], []
    for it in items:
        obj, idx = it[0], it[1]
        if getattr(obj, "type", None) != 'MESH':
            continue
        try:
            obj.update_from_editmode()
            me = obj.data
            nv, ne = len(me.vertices), len(me.edges)
            if not nv or nv > cap:
                continue
            co = np.empty(nv * 3, dtype=np.float32)
            me.vertices.foreach_get('co', co)
            hide = np.zeros(nv, dtype=bool)
            me.vertices.foreach_get('hide', hide)
        except (ValueError, ReferenceError, AttributeError, RuntimeError):
            continue
        mw = np.array(obj.matrix_world, dtype=np.float64)
        W = co.reshape(-1, 3).astype(np.float64) @ mw[:3, :3].T + mw[:3, 3]
        still = ~hide
        mv = np.asarray([int(i) for i in idx], dtype=np.int64)
        mv = mv[(mv >= 0) & (mv < nv)]
        still[mv] = False
        P_all.append(W[still])
        if ne:
            ed = np.empty(ne * 2, dtype=np.int32)
            me.edges.foreach_get('vertices', ed)
            ed = ed.reshape(-1, 2)
            ok = still[ed[:, 0]] & still[ed[:, 1]]
            if ok.any() and int(ok.sum()) <= 400000:
                a, b = W[ed[ok, 0]], W[ed[ok, 1]]
                M_all.append((a + b) * 0.5)
                S_all.append(np.stack((a, b), axis=1))
    if not P_all or not sum(len(p) for p in P_all):
        return None
    pts = np.concatenate(P_all)
    mids = np.concatenate(M_all) if M_all else np.zeros((0, 3))
    d = _points_snapdata(np.concatenate((pts, mids)), 4, np.concatenate(S_all) if S_all else None)
    if len(mids):
        d[2][len(pts):] = 1                     # milieux d'arêtes : Mid
        d[3][len(pts):] = SNAP_BIAS_LUT[1]
    return d


def gumball_snap_from(context):
    """Snappy Dragging : 'CLOSEST', 'GUMBALL' ou 'ORIGIN' ; le choix du fichier, sinon celui des préférences."""
    try:
        st = context.scene.dessin
        if st.gumball_snap_from_set:
            return st.gumball_snap_from
    except (AttributeError, ReferenceError):
        pass
    v = pref("gumball_snap_from")
    return v if v in {i[0] for i in GB_SNAP_FROM_ITEMS} else 'CLOSEST'


def selection_origin(context, items):
    """Origine de l'objet actif (ou du premier objet déplacé), à sa position de départ ; None s'il n'y en a pas."""
    try:
        act = context.view_layer.objects.active
    except (AttributeError, ReferenceError):
        act = None
    for obj, mw0 in items:
        o = act
        while o is not None and o != obj:
            o = o.parent
        if o is not None:
            try:
                return (mw0 @ obj.matrix_world.inverted()) @ act.matrix_world.translation
            except (ValueError, ReferenceError):
                break
    try:
        return items[0][1].translation.copy()
    except (IndexError, AttributeError, TypeError):
        return None


def gumball_selection(context):
    """(centre des poignées, éléments) : centre de la boîte englobante, ou point choisi avec Relocate Gizmo."""
    pivot, items = _gumball_selection_raw(context)
    if pivot is None or not items:
        return pivot, items
    try:
        st = context.scene.dessin
        if st.gumball_pivot_on:
            if context.mode == 'EDIT_CURVE':
                sig = (context.mode, sum(len(r) for _o, r, _w in items))
            else:
                sig = (context.mode, tuple(sorted(o.name for o in context.selected_objects)) if context.mode == 'OBJECT'
                       else tuple((o.name, o.data.total_vert_sel) for o in context.objects_in_mode_unique_data if o.type == 'MESH'))
            if st.gumball_autoreset and _GB_PIV["sig"] is not None and sig != _GB_PIV["sig"]:
                st.gumball_pivot_on = False
            else:
                _GB_PIV["sig"] = sig
                return Vector(st.gumball_pivot), items
    except (AttributeError, ReferenceError, RuntimeError):
        pass
    return pivot, items


def _gumball_selection_raw(context):
    """(centre de la boîte englobante, éléments à transformer) : objets (groupes développés) ou sommets en mode édition."""
    if context.mode in {'EDIT_MESH', 'EDIT_CURVE'}:
        sel = edit_selection(context) if context.mode == 'EDIT_MESH' else curve_edit_selection(context)
        if not sel:
            return None, []
        allp = np.vstack([w for _o, _i, w in sel])
        return Vector((allp.min(axis=0) + allp.max(axis=0)) / 2.0), sel
    sel = expand_groups(context, context.selected_objects)
    selected = set(sel)
    top = [o for o in sel if o.parent not in selected]
    pts = []
    for o in sel:
        if o.type == 'EMPTY' or not o.bound_box:
            pts.append(o.matrix_world.translation.copy())
        else:
            mw = o.matrix_world
            pts += [mw @ Vector(c) for c in o.bound_box]
    if not pts:
        return None, []
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return (lo + hi) / 2.0, top


def gumball_selection_cached(context):
    """Version pour le dessin : en mode édition le calcul est limité à quelques fois par seconde."""
    if context.mode not in {'EDIT_MESH', 'EDIT_CURVE'}:
        return gumball_selection(context)
    now = time.monotonic()
    try:
        if context.mode == 'EDIT_MESH':
            sig = tuple((o.name, o.data.total_vert_sel) for o in context.objects_in_mode_unique_data if o.type == 'MESH')
        else:
            sig = ('C',) + tuple(o.name for o in context.objects_in_mode_unique_data if o.type == 'CURVE')
    except (AttributeError, ReferenceError):
        sig = None
    sig = (context.mode, sig)
    if sig != _GB_EDIT["sig"] or now - _GB_EDIT["t"] > (0.25 if context.mode == 'EDIT_MESH' else 0.12):
        _GB_EDIT["sig"] = sig
        _GB_EDIT["t"] = now
        pivot, items = gumball_selection(context)
        _GB_EDIT["res"] = (pivot, bool(items))
    pivot, ok = _GB_EDIT["res"]
    return (pivot, [True]) if ok and pivot is not None else (None, [])


class GumballBase(bpy.types.Operator):
    """Logique du Gizmo (classe non enregistrée) : glisser = direct, simple clic = on tape la valeur."""

    bl_options = {'REGISTER', 'UNDO'}

    def mouse(self, context, event):
        return Vector((event.mouse_x - context.region.x, event.mouse_y - context.region.y))

    def sample(self, context, event):
        """Valeur brute sous la souris : paramètre sur l'axe (déplacement, échelle) ou angle (rotation)."""
        region, rv3d = context.region, context.region_data
        m = self.mouse(context, event)
        ro = region_2d_to_origin_3d(region, rv3d, m)
        rv = region_2d_to_vector_3d(region, rv3d, m)
        if self.kind == 'PLANE':                # déplacement dans le plan perpendiculaire à l'axe : point visé sur ce plan
            return geometry.intersect_line_plane(ro, ro + rv, self.pivot, self.dir)
        if self.kind == 'ROTATE':
            hit = geometry.intersect_line_plane(ro, ro + rv, self.pivot, self.dir)
            if hit is None:
                return None
            d = hit - self.pivot
            if d.length < 1e-9:
                return None
            return math.atan2(d.dot(self.bv), d.dot(self.bu))
        res = geometry.intersect_line_line(self.pivot, self.pivot + self.dir, ro, ro + rv)
        if not res:
            return None
        return (res[0] - self.pivot).dot(self.dir)

    def default_value(self):
        if self.kind == 'PLANE':
            return Vector((0.0, 0.0, 0.0))
        return 1.0 if self.kind == 'SCALE' else 0.0

    def enter_last(self, enter=True):
        """Validation en mode saisie : retient la valeur tapée ; Entrée sans rien taper reprend la dernière (comme Rhino)."""
        key = (self.bl_idname, self.kind)
        if self.typed not in ('', '-', '.', '-.'):
            _LAST_TYPED[key] = self.value
        elif enter:
            v = last_typed(key)
            if v is not None:
                self.value = v
                self.apply(v)

    def snap_move(self, context, event, value):
        """Snappy Dragging : la flèche se cale sur l'accrochage (End, Mid, Cen...) sous le curseur ; le point de la
        sélection qui s'y pose dépend de « Snap from » (le plus proche, le centre du Gizmo, l'origine)."""
        try:
            if self.kind not in {'MOVE', 'PLANE'} or not self.snap_on(context) or osnap("disable"):
                gumball_snapmark(None)
                return value
            if getattr(self, "_snapd", None) is None:
                names = set()
                for it in self.items:
                    obj = it[0]
                    names.add(obj.name)
                    if not self.edit:
                        names.update(c.name for c in obj.children_recursive)
                # le jeu d'accrochage déjà prêt, où l'on masque ce qui bouge (grosse scène : pas de nouveau relevé)
                self._snapd = collect_snap_points(context)
                if context.mode != 'OBJECT' or not exclude_snap(self._snapd, names):
                    self._snapd = collect_snap_points(context, names)
                # mode Édition : le reste du maillage édité (ce qui ne bouge pas) s'accroche aussi
                self._snapd_own = edit_static_snap(self.items) if self.edit else None
            m = self.mouse(context, event)
            hit = find_snap_in(self._snapd, m.x, m.y, context.region, context.region_data)
            own_d = getattr(self, "_snapd_own", None)
            if own_d is not None:
                h2 = find_snap_in(own_d, m.x, m.y, context.region, context.region_data)
                def _d(h):
                    return math.hypot(float(h[1][0]) - m.x, float(h[1][1]) - m.y)
                if h2 is not None and (hit is None or _d(h2) < _d(hit) - 1e-6):
                    hit = h2
        except (RuntimeError, ReferenceError, AttributeError, ValueError, TypeError):
            return value
        if hit is None:
            gumball_snapmark(None)
            return value
        gumball_snapmark(hit[0], hit[2])
        own = self.snap_base_points(context)
        H = hit[0]
        if self.kind == 'PLANE':                # dans le plan : à l'aplomb du point accroché
            n = np.array(tuple(self.dir), dtype=np.float64)
            D = np.array(tuple(H), dtype=np.float64) - own
            D -= np.outer(D @ n, n)
            return Vector(D[int(np.argmin(np.einsum("ij,ij->i", D, D)))])
        vals = float(H.dot(self.dir)) - own @ np.array(tuple(self.dir), dtype=np.float64)
        return float(vals[int(np.argmin(np.abs(vals)))])

    def snap_on(self, context):
        """Accrochage pendant le glisser : Snappy Dragging, inversé tant que Ctrl est tenu (comme dans Blender)."""
        try:
            on = context.scene.dessin.gumball_drag == 'SNAPPY'
        except AttributeError:
            on = False
        return (not on) if getattr(self, "ctrl_held", False) else on

    def base_pick_start(self, context):
        """Touche B pendant le glisser (comme dans Blender) : choisir le point de l'objet qui se pose sur la cible."""
        if self.edit:                           # mode Édition : un des sommets déplacés (à sa place de départ)
            P = edit_moving_points(self.items)
            self._pick_snap = _points_snapdata(P) if P is not None else None
        else:
            names = set()
            for obj, _ in self.items:
                names.add(obj.name)
                names.update(c.name for c in obj.children_recursive)
            try:
                self._pick_snap = collect_snap_points(context, only=names)
            except (RuntimeError, ReferenceError, AttributeError, ValueError, TypeError):
                self._pick_snap = None
        self.picking = True
        self.free = False
        self.value = self.default_value()
        self.apply(self.value)                  # la sélection revient à sa place, le temps de choisir le point
        gumball_snapmark(None)
        self.header(context)

    def base_pick_hit(self, context, event):
        snap = getattr(self, "_pick_snap", None)
        if snap is None or osnap("disable"):
            return None
        m = self.mouse(context, event)
        try:
            return find_snap_in(snap, m.x, m.y, context.region, context.region_data)
        except (RuntimeError, ReferenceError, AttributeError, ValueError, TypeError):
            return None

    def base_pick_set(self, context, event):
        """Le point de base est posé : il suit la souris le long de la flèche (ou dans le plan) et se cale sur la cible
        si l'accrochage est actif ; le clic suivant valide."""
        hit = self.base_pick_hit(context, event)
        if hit is not None:
            base = hit[0].copy()
        else:                                   # rien d'accroché : le point de la flèche (du plan) sous le curseur
            sm = self.sample(context, event)
            if sm is None:
                return False
            base = sm.copy() if self.kind == 'PLANE' else self.pivot + self.dir * sm
        self._own = np.array([tuple(base)], dtype=np.float64)
        d = (base - self.pivot).dot(self.dir)
        self.ref = (base - self.dir * d) if self.kind == 'PLANE' else d
        self.last = self.ref
        self.picking = False
        self.free = True                        # plus de bouton tenu : le clic suivant valide
        self.mode = 'drag'
        gumball_snapmark(None)
        self.header(context)
        return True

    def modal_pick(self, context, event):
        et = event.type
        if et in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            hit = self.base_pick_hit(context, event)
            gumball_snapmark(hit[0] if hit else None, hit[2] if hit else 0)
            try:
                context.area.tag_redraw()
            except (AttributeError, ReferenceError):
                pass
            return {'RUNNING_MODAL'}
        if et == 'LEFTMOUSE' and event.value in {'PRESS', 'RELEASE'}:
            self._skip_release = event.value == 'PRESS'
            self.base_pick_set(context, event)
            return {'RUNNING_MODAL'}
        if et in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            return self.cancel_all(context)
        if et in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE', 'TRACKPADPAN', 'TRACKPADZOOM'}:
            return {'PASS_THROUGH'}             # on peut naviguer pour trouver le point
        return {'RUNNING_MODAL'}

    def snap_base_points(self, context):
        """Points de la sélection qui peuvent se poser sur l'accrochage, à leur position de départ (N×3), selon « Snap
        from » : tous ses sommets (le plus proche gagne), l'origine de l'objet actif, ou le centre du Gizmo."""
        own = getattr(self, "_own", None)
        if own is not None:
            return own
        how = gumball_snap_from(context)
        pts = None
        if self.edit:                           # mode Édition : les sommets déplacés, ou l'origine de l'objet
            if how == 'CLOSEST':
                pts = edit_moving_points(self.items)
            elif how == 'ORIGIN' and self.items:
                pts = np.array([tuple(self.items[0][0].matrix_world.translation)], dtype=np.float64)
        elif how == 'CLOSEST':
            pts = selection_points(context, self.items)
        elif how == 'ORIGIN':
            o = selection_origin(context, self.items)
            if o is not None:
                pts = np.array([tuple(o)], dtype=np.float64)
        if pts is None:                         # Gizmo (ou rien d'autre de lisible)
            pts = np.array([tuple(self.pivot)], dtype=np.float64)
        self._own = pts
        return pts

    def value_from_sample(self, s, shift):
        if s is None:
            return self.value
        if self.kind == 'PLANE':
            return s - self.ref
        if self.kind == 'MOVE':
            return s - self.ref
        if self.kind == 'SCALE':
            return s / self.ref if abs(self.ref) > 1e-6 else 1.0
        delta = s - self.last
        while delta > math.pi:
            delta -= TAU
        while delta < -math.pi:
            delta += TAU
        self.last = s
        self.acc += delta
        deg = math.degrees(self.acc)
        if (not shift) if pref("gumball_rot90") else shift:   # pas de 90° (par défaut) ; Maj = rotation libre
            stp = float(pref("gumball_step"))
            deg = round(deg / stp) * stp
        return deg

    def xform(self, value, uniform=False):
        p = self.pivot
        if self.kind == 'PLANE':
            return Matrix.Translation(value)
        if self.kind == 'MOVE':
            return Matrix.Translation(self.dir * value)
        if self.kind == 'ROTATE':
            return Matrix.Translation(p) @ Matrix.Rotation(math.radians(value), 4, self.dir) @ Matrix.Translation(-p)
        S = Matrix.Scale(value, 4) if uniform else Matrix.Scale(value, 4, self.dir)
        return Matrix.Translation(p) @ S @ Matrix.Translation(-p)

    def edit_apply(self, X):
        Xn = np.array(X, dtype=np.float64)
        for obj, idx, w0 in self.items:
            if obj.type == 'CURVE':
                curve_edit_apply(obj, idx, w0, Xn)
                continue
            try:
                bm = bmesh.from_edit_mesh(obj.data)
            except (ValueError, ReferenceError):
                continue
            bm.verts.ensure_lookup_table()
            M = np.linalg.inv(np.array(obj.matrix_world, dtype=np.float64)) @ Xn
            h = np.hstack((w0, np.ones((len(w0), 1)))) @ M.T
            for i, p in zip(idx, h):
                bm.verts[i].co = Vector((p[0], p[1], p[2]))
            # normales des faces touchées : sans elles, une face neuve (extrusion) reste à normale nulle et s'affiche noire
            faces = {f for i in idx for f in bm.verts[i].link_faces}
            for f in faces:
                f.normal_update()
            for v in {v for f in faces for v in f.verts}:
                v.normal_update()
            bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=False)

    def show_rotation(self, value):
        if getattr(self, "kind", None) == 'ROTATE' and getattr(self, "bu", None) is not None:
            a0 = self.ref if isinstance(getattr(self, "ref", None), float) else 0.0
            gumball_rot_show(self.pivot, self.dir, self.bu, self.bv, a0, value)

    def apply(self, value):
        self.show_rotation(value)
        X = self.xform(value, getattr(self, "uniform", False))
        gumball_drag_xform(X)                     # le Gizmo suit la sélection pendant l'opération (comme Rhino)
        if self.edit:
            self.edit_apply(X)
            return
        for obj, mw in self.items:
            try:
                obj.matrix_world = X @ mw
            except ReferenceError:
                pass

    def restore(self):
        gumball_drag_xform(None)
        if self.edit:
            self.edit_apply(Matrix.Identity(4))
            return
        for obj, mw in self.items:
            try:
                obj.matrix_world = mw
            except ReferenceError:
                pass

    def label(self):
        base = self._label()
        if not getattr(self, "alt_copy", False) or getattr(self, "NO_COPY", False):
            return base
        if self.edit and copy_shift() and not getattr(self, "ctrl_held", False):
            return "Extrude - " + base                  # (3ds Max : Maj + glisser des arêtes ou des faces)
        return "Copy - " + base

    def _label(self):
        ax = GUMBALL_AXES[self.axis]
        if self.kind == 'PLANE':
            names = "".join(GUMBALL_AXES[i] for i in range(3) if i != self.axis)
            v = self.value / self.unit_f
            return f"Move in the {names} plane: ({v.x:.3f}, {v.y:.3f}, {v.z:.3f}) {self.unit_label}".strip()
        if self.kind == 'MOVE':
            v = self.value / self.unit_f
            return f"Move {ax}: {v:.3f} {self.unit_label}".strip()
        if self.kind == 'ROTATE':
            return f"Rotate around {ax}: {self.value:.2f}°"
        return f"Scale {'(uniform)' if getattr(self, 'uniform', False) else ax}: ×{self.value:.4f}"

    def bubble(self, context):
        """Bulle de saisie près de la poignée cliquée (comme Rhino), dans le style des barres du bas."""
        try:
            if self.mode != 'type':
                value_bubble_hide(context.area)
                return
            region, rv3d = context.region, context.region_data
            p0 = location_3d_to_region_2d(region, rv3d, self.pivot)
            p1 = location_3d_to_region_2d(region, rv3d, self.pivot + self.dir * 1e-3)
            if p0 is None:
                value_bubble_hide(context.area)
                return
            L = GUMBALL_PX * gumball_k(context)
            if self.kind == 'ROTATE':
                a = p0 + Vector((0.45, 0.45)) * L
            else:
                v = (p1 - p0) if p1 is not None else Vector((1.0, 0.0))
                v = v.normalized() if v.length > 1e-9 else Vector((1.0, 0.0))
                a = p0 + v * L * (1.25 if self.kind == 'MOVE' else -0.93)    # au bout de la flèche (Rhino)
            ax = GUMBALL_AXES[self.axis]
            col = (*GUMBALL_COLORS[self.axis][:3], 1.0)
            if self.kind == 'MOVE':
                parts = [(tr_text("Distance to move in "), None, False), (ax, col, True)]
            elif self.kind == 'ROTATE':
                parts = [(tr_text("Angle to rotate around "), None, False), (ax, col, True)]
            else:
                parts = [(tr_text("Scale factor along "), None, False), (ax, col, True)]
            value_bubble_show(context.area, (a.x, a.y), parts, self.typed)
        except (AttributeError, ReferenceError, TypeError, ValueError, RuntimeError):
            pass

    def header(self, context):
        self.bubble(context)
        if self.mode == 'type':
            unit = {'MOVE': self.unit_label or "", 'ROTATE': "°", 'SCALE': "×"}[self.kind]
            lv = last_typed((self.bl_idname, self.kind)) if not self.typed else None
            last = "" if lv is None else f" (nothing typed: {fmt_typed(lv / self.unit_f if self.kind == 'MOVE' else lv)}, last value)"
            txt = f"{self.label()}   |   type the value: {self.typed or '_'} {unit}   |   Enter: apply{last}   Esc: cancel"
        elif getattr(self, "picking", False):
            txt = "Base point: click the point of the selection that will land on the target (snaps)   |   Esc: cancel"
        else:
            free = getattr(self, "free", False)
            txt = (f"{self.label()}   |   {'click' if free else 'release'}: apply   Esc: cancel"
                   + ("" if self.kind == 'PLANE' or free else "   (a click without dragging lets you type the value)")
                   + (f"   |   90° steps, {lock_key_name()}: free rotation" if self.kind == 'ROTATE' else ""))
            if self.kind in {'MOVE', 'PLANE'}:
                txt += "   |   Ctrl: snap on / off   B: base point"
            if not getattr(self, "NO_COPY", False):
                txt += f"   |   {copy_key_name()}: copy"
        try:
            set_prompt(context.area, txt)
        except (AttributeError, ReferenceError):
            pass

    def update_ghost(self, context):
        if not getattr(self, "alt_copy", False) or getattr(self, "NO_COPY", False) or self.mode == 'wait':
            ghost_hide()
            return
        if getattr(self, "_ghost", None) is None:
            self._ghost = ghost_for_edit(self.items) if self.edit else ghost_for_objects(self.items)
        ghost_show(context.area, self._ghost)

    def finish_ui(self, context):
        gumball_rot_hide()
        gumball_snapmark(None)
        self.picking = False
        _ALT_HOVER["handle"] = None
        value_bubble_hide(getattr(context, "area", None))
        gumball_unfreeze(context)
        ghost_hide()
        try:
            set_prompt(context.area, None)
        except (AttributeError, ReferenceError):
            pass

    def setup_selection(self, context):
        """Remplit pivot, edit, items et dir ; False si rien à faire."""
        pivot, top = gumball_selection(context)
        if not top:
            return False
        self.pivot = pivot
        self.edit = context.mode in {'EDIT_MESH', 'EDIT_CURVE'}
        if context.mode == 'EDIT_CURVE':
            self.NO_COPY = True
        self.items = top if self.edit else [(o, o.matrix_world.copy()) for o in top]
        self.dir = gumball_axes(context)[self.axis].copy()
        self._own = None                    # points qui se calent en Snappy Dragging (lus au premier accrochage)
        self.picking = False                # touche B : choix du point de base en cours
        self.free = False                   # point de base choisi : on déplace sans bouton tenu, un clic valide
        self._skip_release = False
        return True

    def invoke(self, context, event):
        if context.region is None or context.region_data is None or not self.setup_selection(context):
            return {'CANCELLED'}
        self.bu = self.dir.orthogonal().normalized()
        self.bv = self.dir.cross(self.bu)
        self.unit_f, self.unit_label = unit_info(context.scene)
        self.press = self.mouse(context, event)
        self.mode = 'wait'
        self.typed = ''
        self.alt_copy = copy_held(event)
        self.ctrl_held = bool(event.ctrl)
        self.uniform = False
        self.value = self.default_value()
        self.acc = 0.0
        s0 = self.sample(context, event)
        if s0 is None:
            return {'CANCELLED'}
        self.ref = s0
        self.last = s0
        gumball_freeze(context, self.pivot, "DESSIN_OT_gumball")       # repère de départ du Gizmo, qui suit ensuite la sélection
        context.window_manager.modal_handler_add(self)
        self.header(context)
        return {'RUNNING_MODAL'}

    def typed_value(self):
        t = self.typed
        if t in ('', '-', '.', '-.'):
            return self.default_value()
        if self.kind == 'MOVE':
            from .core import typed_length
            v = typed_length(t, self.unit_f)
            return self.default_value() if v is None else v
        try:
            v = float(t)
        except ValueError:
            return self.default_value()
        return v

    def drag_update(self, context, event):
        self.uniform = lock_held(event) and self.kind == 'SCALE'
        self.value = self.value_from_sample(self.sample(context, event), lock_held(event))
        self.value = self.snap_move(context, event, self.value)
        self.apply(self.value)
        self.header(context)
        try:
            context.area.tag_redraw()
        except (AttributeError, ReferenceError):
            pass
        return {'RUNNING_MODAL'}

    def cancel_all(self, context):
        self.restore()
        self.finish_ui(context)
        return {'CANCELLED'}

    def commit(self, context):
        if getattr(self, "alt_copy", False) and not getattr(self, "NO_COPY", False):
            drag_copy_commit(context, self.items, self.edit, ctrl=getattr(self, "ctrl_held", False))
        self.finish_ui(context)
        return {'FINISHED'}

    def modal(self, context, event):
        et = event.type
        if et in {'LEFT_CTRL', 'RIGHT_CTRL'}:
            self.ctrl_held = event.value == 'PRESS'                        # (3ds Max : Ctrl + Maj = copie détachée)
            if self.mode == 'drag' and not getattr(self, "picking", False) and event.value in {'PRESS', 'RELEASE'}:
                return self.drag_update(context, event)      # Ctrl : l'accrochage s'active / se coupe sans bouger la souris
        elif et in {'MOUSEMOVE', 'LEFTMOUSE'}:
            self.ctrl_held = bool(event.ctrl)
        if getattr(self, "picking", False):
            return self.modal_pick(context, event)
        if et == 'B' and event.value == 'PRESS' and self.mode in {'wait', 'drag'} and self.kind in {'MOVE', 'PLANE'}:
            self.base_pick_start(context)
            return {'RUNNING_MODAL'}
        mod = copy_mod_event(event, getattr(self, "alt_copy", False))     # Alt ou Maj : copie (selon les préférences)
        if mod is not None:
            if self.mode == 'drag':
                self.alt_copy = mod[0]
            elif event.value == 'PRESS' and copy_held(event) and self.mode == 'type':
                self.alt_copy = not getattr(self, "alt_copy", False)   # pendant la saisie : la touche bascule la copie
            elif copy_held(event):
                self.alt_copy = True
            # (clic sans glisser, comme Rhino : Alt + clic sur une flèche puis la valeur tapée = copie ; relâcher Alt
            # avant de taper ne l'annule pas)
            self.header(context)
            self.update_ghost(context)
            return {'RUNNING_MODAL'}
        if et in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            if self.mode == 'drag':
                self.alt_copy = copy_update(event, getattr(self, "alt_copy", False))
            self.update_ghost(context)
        elif event.value == 'PRESS' and copy_held(event):
            self.alt_copy = True
        if self.mode == 'type':
            if event.value == 'PRESS':
                if et == 'ESC':
                    return self.cancel_all(context)
                if et in {'RET', 'NUMPAD_ENTER'}:
                    self.enter_last(True)
                    self.apply(self.value)          # l'objet se déplace maintenant, une fois la valeur validée
                    return self.commit(context)
                if et == 'LEFTMOUSE':           # clic ailleurs : la saisie est abandonnée et le clic agit normalement (Rhino)
                    self.cancel_all(context)
                    return {'CANCELLED', 'PASS_THROUGH'}
                if et == 'BACK_SPACE':
                    self.typed = self.typed[:-1]
                elif event.unicode and event.unicode == "-" and "'" not in self.typed:
                    self.typed = self.typed[1:] if self.typed.startswith('-') else '-' + self.typed
                elif (event.unicode and event.unicode != "-"
                      and (event.unicode in "0123456789.," or self.kind == 'MOVE')
                      and typing_add(self.typed, event.unicode) is not None):
                    self.typed = typing_add(self.typed, event.unicode)    # déplacement : 10' 6 1/2" accepté
                else:
                    return {'PASS_THROUGH'}
                self.value = self.typed_value()      # (appliquée seulement à la validation, comme dans Rhino)
                self.show_rotation(self.value)       # rotation : l'angle tapé se voit déjà sur l'indicateur
                self.header(context)
                return {'RUNNING_MODAL'}
            return {'PASS_THROUGH'} if et not in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'} else {'RUNNING_MODAL'}
        # glisser
        if et in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            m = self.mouse(context, event)
            if self.mode == 'wait' and (m - self.press).length > 5.0 * px_scale():
                self.mode = 'drag'
            if self.mode == 'drag':
                return self.drag_update(context, event)
            return {'RUNNING_MODAL'}
        if getattr(self, "free", False) and et == 'LEFTMOUSE':      # après B : le clic suivant valide
            if event.value == 'RELEASE' and getattr(self, "_skip_release", False):
                self._skip_release = False
                return {'RUNNING_MODAL'}
            if event.value == 'PRESS':
                self.value = self.snap_move(context, event, self.value_from_sample(self.sample(context, event), False))
                self.apply(self.value)
                return self.commit(context)
            return {'RUNNING_MODAL'}
        if et == 'LEFTMOUSE' and event.value == 'RELEASE':
            if self.mode == 'drag':
                return self.commit(context)
            if self.kind == 'PLANE':
                return self.cancel_all(context)         # déplacement dans un plan : pas de valeur à taper, un clic ne fait rien
            self.mode = 'type'          # simple clic : on tape la valeur
            _GB_DRAG["typing"] = True
            self.typed = ''
            self.value = self.default_value()
            self.header(context)
            return {'RUNNING_MODAL'}
        if et in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            return self.cancel_all(context)
        return {'RUNNING_MODAL'}


class DESSIN_OT_gumball(GumballBase):
    bl_idname = "dessin.gumball"
    bl_label = "Gizmo"
    bl_description = ("Drag to transform the selection from its center; click without dragging, then type the "
                      "distance / angle / scale factor and press Enter")

    kind: bpy.props.EnumProperty(items=(('MOVE', "Move", ""), ('ROTATE', "Rotate", ""), ('SCALE', "Scale", ""), ('PLANE', "Move in a plane", "")),
                                 default='MOVE', options={'SKIP_SAVE'})
    axis: bpy.props.IntProperty(default=0, min=0, max=2, options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.mode in {'OBJECT', 'EDIT_MESH', 'EDIT_CURVE'} and context.area is not None and context.area.type == 'VIEW_3D'

    @classmethod
    def description(cls, context, props):
        return gumball_handle_tip(getattr(props, "kind", 'MOVE'))


def gumball_handle_tip(kind):
    """Infobulle d'une poignée du Gizmo (survol) : ce que fait le glisser et les touches utiles pendant le geste."""
    ck, lk = copy_key_name(), lock_key_name()
    snap = ("While dragging: Ctrl snaps on / off, B picks the base point (Object mode), " + ck + ": copy.\n"
            "Smooth / Snappy Dragging and Snap from (closest point, Gizmo centre, origin): Gizmo menu")
    if kind == 'MOVE':
        return ("Drag to move the selection along this axis, or click without dragging, then type the distance and "
                "press Enter.\n" + snap)
    if kind == 'PLANE':
        return "Drag to move the selection in this plane.\n" + snap
    if kind == 'ROTATE':
        step = pref("gumball_step")
        free = f"{lk}: free rotation" if pref("gumball_rot90") else f"{lk}: {step}° steps"
        return ("Drag to rotate the selection around this axis (the swept angle is shown), or click without dragging, "
                f"then type the angle and press Enter.\nWhile dragging: {free}, {ck}: copy")
    return ("Drag to scale the selection along this axis, or click without dragging, then type the factor and press "
            f"Enter.\nWhile dragging: {lk}: uniform scale, {ck}: copy")


def _gb_redraw(context):
    _GB_EDIT["t"] = 0.0
    try:
        for win in context.window_manager.windows:
            for a in win.screen.areas:
                if a.type == 'VIEW_3D':
                    a.tag_redraw()
    except (AttributeError, RuntimeError, ReferenceError):
        pass


class DESSIN_OT_gumball_relocate(DessinBase):
    bl_idname = "dessin.gumball_relocate"
    bl_label = "Relocate Gizmo"
    bl_description = "Moves the Gizmo to a point you click (with snapping): rotations and scaling then use that point"

    TITLE = "Relocate Gizmo"
    NEEDED = 1
    PLANAR = False
    LOCK_OK = False

    def prompt(self):
        return "click the new location of the Gizmo   (snapping on)"

    def click(self, context):
        try:
            st = context.scene.dessin
            st.gumball_pivot = self.cur
            st.gumball_pivot_on = True
        except (AttributeError, ReferenceError):
            pass
        _GB_PIV["sig"] = None
        _gb_redraw(context)
        self.finished = True


class DESSIN_OT_gumball_reset(bpy.types.Operator):
    bl_idname = "dessin.gumball_reset"
    bl_label = "Reset Gizmo"
    bl_description = "Puts the Gizmo back at the center of the selection"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        context.scene.dessin.gumball_pivot_on = False
        _gb_redraw(context)
        return {'FINISHED'}


class DESSIN_OT_gumball_set(bpy.types.Operator):
    bl_idname = "dessin.gumball_set"
    bl_label = "Gizmo On / Off"
    bl_options = {'INTERNAL'}

    on: bpy.props.BoolProperty(default=True)

    def execute(self, context):
        context.scene.dessin.gumball = self.on
        _gb_redraw(context)
        return {'FINISHED'}


class DESSIN_OT_gumball_snap_from(bpy.types.Operator):
    bl_idname = "dessin.gumball_snap_from"
    bl_label = "Snap From"
    bl_options = {'INTERNAL'}

    value: bpy.props.EnumProperty(items=GB_SNAP_FROM_ITEMS, default='CLOSEST')

    @classmethod
    def description(cls, context, props):
        return next((d for i, _n, d in GB_SNAP_FROM_ITEMS if i == props.value), "")

    def execute(self, context):
        st = context.scene.dessin
        st.gumball_snap_from = self.value
        st.gumball_snap_from_set = True
        return {'FINISHED'}


class DESSIN_OT_gumball_settings(bpy.types.Operator):
    bl_idname = "dessin.gumball_settings"
    bl_label = "Settings..."
    bl_description = "Opens the Gizmo settings of the add-on (rotation steps, line thickness) in the preferences"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        try:
            bpy.ops.preferences.addon_show(module=__package__)
        except (RuntimeError, TypeError):
            self.report({'INFO'}, "Preferences > Add-ons > Wanderer > Gizmo")
        return {'FINISHED'}


class DESSIN_MT_gumball(bpy.types.Menu):
    bl_idname = "DESSIN_MT_gumball"
    bl_label = "Gizmo"

    def draw(self, context):
        lay = self.layout
        st = context.scene.dessin
        # tout en haut : Snappy / Smooth Dragging et le point qui se cale
        for ident in ('SMOOTH', 'SNAPPY'):                  # Snappy juste au-dessus de « Snap from », qui en dépend
            lay.prop_enum(st, "gumball_drag", ident)
        col = lay.column()
        col.enabled = st.gumball_drag == 'SNAPPY'           # sans accrochage, rien ne se pose
        col.label(text="Snap from:")
        cur = gumball_snap_from(context)
        for ident, name, _d in GB_SNAP_FROM_ITEMS:
            op = col.operator(DESSIN_OT_gumball_snap_from.bl_idname, text="    " + name,
                              icon='RADIOBUT_ON' if cur == ident else 'RADIOBUT_OFF')
            op.value = ident
        lay.separator()
        lay.operator(DESSIN_OT_gumball_relocate.bl_idname, text="Relocate Gizmo")
        lay.operator(DESSIN_OT_gumball_reset.bl_idname, text="Reset Gizmo")
        lay.prop(st, "gumball_autoreset", text="AutoReset Gizmo", toggle=False)
        lay.separator()
        op = lay.operator(DESSIN_OT_gumball_set.bl_idname, text="Gizmo On", icon='RADIOBUT_ON' if st.gumball else 'RADIOBUT_OFF')
        op.on = True
        op = lay.operator(DESSIN_OT_gumball_set.bl_idname, text="Gizmo Off", icon='RADIOBUT_OFF' if st.gumball else 'RADIOBUT_ON')
        op.on = False
        lay.separator()
        try:
            lay.label(text="Orientation (same as the header list)")
            lay.prop(context.scene.transform_orientation_slots[0], "type", expand=True)
        except (AttributeError, IndexError, RuntimeError):
            pass
        lay.separator()
        lay.operator(DESSIN_OT_gumball_settings.bl_idname, text="Settings...")


_EXT_CACHE = {"t": 0.0, "sig": None, "dir": None}


def extrude_direction(context):
    """Direction (monde) d'extrusion des faces / arêtes sélectionnées, ou None ; calculée au plus 4 fois par seconde."""
    now = time.monotonic()
    try:
        sig = tuple((o.name, o.data.total_face_sel, o.data.total_edge_sel, o.data.total_vert_sel)
                    for o in context.objects_in_mode_unique_data if o.type == 'MESH')
    except (AttributeError, ReferenceError):
        return None
    if sig == _EXT_CACHE["sig"] and now - _EXT_CACHE["t"] < 0.25:
        return _EXT_CACHE["dir"]
    dsum = Vector()
    for obj in context.objects_in_mode_unique_data:
        if obj.type != 'MESH':
            continue
        try:
            bm = bmesh.from_edit_mesh(obj.data)
        except ValueError:
            continue
        nm = obj.matrix_world.to_3x3().inverted_safe().transposed()
        faces = [f for f in bm.faces if f.select]
        if faces:
            for f in faces:
                dsum += (nm @ f.normal).normalized() * f.calc_area()
        else:
            for e in bm.edges:
                if e.select:
                    for f in e.link_faces:
                        dsum += (nm @ f.normal).normalized()
    out = dsum.normalized() if dsum.length > 1e-9 else Vector((0.0, 0.0, 1.0))
    _EXT_CACHE.update(t=now, sig=sig, dir=out)
    return out


def extrude_info(context):
    """(faces, arêtes) sélectionnées en mode édition (nombres), pour savoir si la poignée d'extrusion s'affiche."""
    nf = ne = 0
    try:
        for o in context.objects_in_mode_unique_data:
            if o.type == 'MESH':
                nf += o.data.total_face_sel
                ne += o.data.total_edge_sel
    except (AttributeError, ReferenceError):
        pass
    return nf, ne


def mirror_plane_cleanup(obj, bm, tol=1e-5):
    """Après une extrusion : les faces posées sur un plan de symétrie (Mirror avec Clipping) sont supprimées, comme le fait
    l'extrusion de Blender ; sinon elles deviennent des faces internes (arêtes non-manifold) une fois le miroir appliqué."""
    axes = set()
    for md in obj.modifiers:
        if md.type == 'MIRROR' and md.show_viewport and md.use_clip and md.mirror_object is None:
            axes |= {i for i in range(3) if md.use_axis[i]}
    if not axes:
        return 0
    walls = [f for f in bm.faces if any(all(abs(v.co[a]) <= tol for v in f.verts) for a in axes)]
    if walls:
        bmesh.ops.delete(bm, geom=walls, context='FACES')
    return len(walls)


class DESSIN_OT_gumball_extrude(GumballBase):
    bl_idname = "dessin.gumball_extrude"
    bl_label = "Extrude"
    bl_description = ("Extrudes the selected faces (or edges) along their normal: drag, or click without dragging, "
                      "type the distance and press Enter")

    NO_COPY = True
    kind = 'MOVE'
    axis = 0

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and context.area is not None and context.area.type == 'VIEW_3D'

    def setup_selection(self, context):
        self.backups = []
        self.manifold = False
        if self.setup_manifold(context):
            return True
        items = []
        dsum = Vector()
        pts = []
        for obj in context.objects_in_mode_unique_data:
            if obj.type != 'MESH':
                continue
            bm = bmesh.from_edit_mesh(obj.data)
            faces = [f for f in bm.faces if f.select]
            edges = [] if faces else [e for e in bm.edges if e.select]
            if not faces and not edges:
                continue
            nm = obj.matrix_world.to_3x3().inverted_safe().transposed()
            if faces:
                for f in faces:
                    dsum += (nm @ f.normal).normalized() * f.calc_area()
            else:
                for e in edges:
                    for f in e.link_faces:
                        dsum += (nm @ f.normal).normalized()
            tmp = bpy.data.meshes.new("dessin_extrude_backup")
            bm.to_mesh(tmp)                      # copie de secours (pour Échap)
            self.backups.append((obj, tmp))
            if faces:
                ret = bmesh.ops.extrude_face_region(bm, geom=faces)
                # comme l'extrusion de Blender : les faces d'origine disparaissent (sinon elles restent à l'intérieur du volume)
                bmesh.ops.delete(bm, geom=[f for f in faces if f.is_valid], context='FACES')
            else:
                ret = bmesh.ops.extrude_edge_only(bm, edges=edges)
            geom = ret["geom"]
            if mirror_plane_cleanup(obj, bm):
                geom = [g for g in geom if g.is_valid]
            new_verts = [g for g in geom if isinstance(g, bmesh.types.BMVert)]
            for v in bm.verts:
                v.select_set(False)
            for g in geom:
                g.select_set(True)
            bm.select_flush_mode()
            bm.verts.ensure_lookup_table()
            bm.verts.index_update()
            mw = np.array(obj.matrix_world, dtype=np.float64)
            co = np.array([tuple(v.co) for v in new_verts], dtype=np.float64)
            w0 = co @ mw[:3, :3].T + mw[:3, 3]
            items.append((obj, [v.index for v in new_verts], w0))
            pts.append(w0)
            bm.normal_update()
            bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=True)
        if not items:
            return False
        if dsum.length < 1e-9:
            dsum = Vector((0.0, 0.0, 1.0))
        allp = np.vstack(pts)
        self.pivot = Vector((allp.min(axis=0) + allp.max(axis=0)) / 2.0)
        self.edit = True
        self.items = items
        self.dir = dsum.normalized()
        return True

    def setup_manifold(self, context):
        """Faces sélectionnées : extrusion de Blender « Extrude Manifold » (#22). Les côtés posés dans le prolongement des
        faces voisines ne créent pas d'arêtes en trop (le dessus d'une boîte monte, ses côtés s'allongent), et pousser
        vers l'intérieur creuse le volume au lieu de laisser des faces en double (fusion et découpe à la validation)."""
        objs = [o for o in context.objects_in_mode_unique_data if o.type == 'MESH']
        dsum = Vector()
        with_faces = []
        for obj in objs:
            try:
                bm = bmesh.from_edit_mesh(obj.data)
            except ValueError:
                continue
            faces = [f for f in bm.faces if f.select]
            if not faces:
                continue
            nm = obj.matrix_world.to_3x3().inverted_safe().transposed()
            for f in faces:
                dsum += (nm @ f.normal).normalized() * f.calc_area()
            tmp = bpy.data.meshes.new("dessin_extrude_backup")
            bm.to_mesh(tmp)                      # copie de secours (pour Échap)
            self.backups.append((obj, tmp))
            with_faces.append(obj)
        if not with_faces:
            return False
        try:
            r = bpy.ops.mesh.extrude_region(use_dissolve_ortho_edges=True)
        except (RuntimeError, TypeError):
            r = {'CANCELLED'}
        if 'FINISHED' not in r:
            self.drop_backups()
            return False
        items, pts = [], []
        for obj in with_faces:
            bm = bmesh.from_edit_mesh(obj.data)
            bm.verts.ensure_lookup_table()
            bm.verts.index_update()
            new_verts = [v for v in bm.verts if v.select]
            if not new_verts:
                continue
            mw = np.array(obj.matrix_world, dtype=np.float64)
            co = np.array([tuple(v.co) for v in new_verts], dtype=np.float64)
            w0 = co @ mw[:3, :3].T + mw[:3, 3]
            items.append((obj, [v.index for v in new_verts], w0))
            pts.append(w0)
        if not items:
            self.cancel_backups()
            return False
        if dsum.length < 1e-9:
            dsum = Vector((0.0, 0.0, 1.0))
        allp = np.vstack(pts)
        self.pivot = Vector((allp.min(axis=0) + allp.max(axis=0)) / 2.0)
        self.edit = True
        self.items = items
        self.dir = dsum.normalized()
        self.manifold = True
        return True

    def cancel_backups(self):
        for obj, tmp in self.backups:               # on revient au maillage d'avant l'extrusion
            try:
                bm = bmesh.from_edit_mesh(obj.data)
                bm.clear()
                bm.from_mesh(tmp)
                bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=True)
            except (ReferenceError, RuntimeError, ValueError):
                pass
        self.drop_backups()

    def drop_backups(self):
        for _o, tmp in self.backups:
            try:
                bpy.data.meshes.remove(tmp)
            except (ReferenceError, RuntimeError):
                pass
        self.backups = []

    def label(self):
        return f"Extrude: {self.value / self.unit_f:.3f} {self.unit_label}".strip()

    def cancel_all(self, context):
        self.cancel_backups()
        self.finish_ui(context)
        return {'CANCELLED'}

    def commit(self, context):
        if abs(self.value) < 1e-9:                  # distance nulle : pas d'extrusion
            return self.cancel_all(context)
        if getattr(self, "manifold", False):
            # comme Extrude Manifold : les sommets qui se rejoignent sont fusionnés et les faces qui se croisent découpées
            # (une face poussée dans le volume le creuse, sans faces en double ni arêtes non-manifold)
            try:
                bpy.ops.transform.translate(value=(0.0, 0.0, 0.0), use_automerge_and_split=True)
            except (RuntimeError, TypeError):
                pass
        self.drop_backups()
        self.finish_ui(context)
        return {'FINISHED'}


def _late_imports():
    """Noms définis dans des modules chargés après celui-ci : ils ne servent qu'à l'exécution des outils."""
    global set_prompt, value_bubble_hide, value_bubble_show
    from .cplane import set_prompt
    from .command_line import value_bubble_hide, value_bubble_show
