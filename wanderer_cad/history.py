"""Wanderer CAD : History : résultats gardés modifiables par un modificateur de Blender (option History = Yes).

Comme Record History de Rhino, mais avec les outils de Blender : au lieu d'un maillage figé, la commande crée le profil
et pose un modificateur (Screw, Solidify, Boolean) ou règle l'épaisseur de la courbe. La valeur (hauteur, angle,
épaisseur, rayon) se change ensuite dans l'onglet Modifiers. Seules ces commandes le proposent : Revolve, Extrude Curve,
Extrude Surface, Thicken, Pipe et les booléens Union / Difference / Intersection."""

import bmesh
import bpy
import math
from mathutils import Matrix, Vector

from .core import _link_object

HISTORY_KEY = "wanderer_history"       # propriété posée sur l'objet : nom de la commande qui l'a créé
CUTTER_KEY = "wanderer_cutter"         # objet gardé comme opérande d'un booléen modifiable
_HISTORY_MEM = {}                      # History = Yes / No, mémorisé par commande d'une utilisation à l'autre


def history_on(key):
    return bool(_HISTORY_MEM.get(key, False))


def history_set(key, value):
    _HISTORY_MEM[key] = bool(value)


def history_label(on):
    return f"H: History = {'Yes' if on else 'No'}"


def frame_matrix(origin, z):
    """Repère (matrice monde) d'origine `origin` dont l'axe Z local suit `z`."""
    z = Vector(z).normalized()
    x = z.orthogonal().normalized()
    y = z.cross(x)
    M = Matrix((x, y, z)).transposed().to_4x4()
    M.translation = Vector(origin)
    return M


def _local_paths(paths, M):
    inv = M.inverted()
    return [([inv @ Vector(tuple(p)) for p in P], bool(closed)) for P, closed in paths]


def _wire_bmesh(local):
    bm = bmesh.new()
    for P, closed in local:
        vs = [bm.verts.new(p) for p in P]
        for a, b in zip(vs, vs[1:]):
            bm.edges.new((a, b))
        if closed and len(vs) > 2:
            bm.edges.new((vs[-1], vs[0]))
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-7)
    return bm


def _object_from_bmesh(context, name, bm, M, tag):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.update()
    obj = _link_object(context, name, me)
    obj.matrix_world = M
    obj[HISTORY_KEY] = tag
    return obj


def history_revolve(context, paths, origin, axis, angle_deg):
    """Profil (arêtes) + modificateur Screw autour de l'axe (origin, axis). L'angle et le nombre de pas restent modifiables."""
    if not paths or Vector(axis).length < 1e-12:
        return None
    ang = math.radians(max(-360.0, min(360.0, angle_deg)))
    if abs(ang) < 1e-9:
        return None
    M = frame_matrix(origin, axis)
    obj = _object_from_bmesh(context, "Revolve", _wire_bmesh(_local_paths(paths, M)), M, "Revolve")
    md = obj.modifiers.new("Revolve", 'SCREW')
    md.axis = 'Z'
    md.angle = ang
    md.screw_offset = 0.0
    md.steps = md.render_steps = max(6, int(math.ceil(abs(ang) / (2 * math.pi) * 64)))
    md.use_merge_vertices = True
    md.merge_threshold = 1e-6
    md.use_normal_calculate = True
    md.use_smooth_shade = False
    return obj


def history_extrude(context, paths, vec, solid):
    """Extrusion droite modifiable. Profils fermés et plans, perpendiculaires à l'extrusion, avec Solid = Yes :
    face + Solidify (solide fermé, l'épaisseur est la hauteur). Sinon : arêtes + Screw sans rotation (la surface seule,
    la hauteur est « Screw »). Retourne l'objet, ou None si rien n'a pu être construit."""
    vec = Vector(vec)
    h = vec.length
    if not paths or h < 1e-9:
        return None
    M = frame_matrix(Vector(tuple(paths[0][0][0])), vec)
    local = _local_paths(paths, M)
    size = max((p - q).length for P, _c in local for p in P for q in (P[0],)) or 1.0
    tol = 1e-5 * max(size, 1.0)
    flat = all(c and len(P) >= 3 and abs(p.z) <= tol for P, c in local for p in P)
    bm = _wire_bmesh(local)
    if solid and flat:
        try:
            bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=True, edges=bm.edges[:], normal=(0.0, 0.0, 1.0))
        except (ValueError, RuntimeError):
            pass
        if bm.faces:
            bm.normal_update()
            for f in bm.faces:
                if f.normal.z < 0.0:
                    f.normal_flip()
            obj = _object_from_bmesh(context, "Extrusion", bm, M, "Extrude")
            md = obj.modifiers.new("Extrude", 'SOLIDIFY')
            md.thickness = h
            md.offset = 1.0
            md.use_even_offset = False
            md.use_rim = True
            return obj
    obj = _object_from_bmesh(context, "Extrusion", bm, M, "Extrude")
    md = obj.modifiers.new("Extrude", 'SCREW')
    md.axis = 'Z'
    md.angle = 0.0
    md.screw_offset = h
    md.steps = md.render_steps = 1
    md.use_merge_vertices = False
    md.use_normal_calculate = True
    md.use_smooth_shade = False
    return obj


def history_thicken(context, obj, thickness, direction, keep_input):
    """Solidify sur la surface (ou sur sa copie si l'on garde l'originale). direction : 'NORMAL', 'OPPOSITE' ou 'BOTH'."""
    target = obj
    if keep_input:
        target = obj.copy()
        target.data = obj.data.copy()
        target.name = "Thick " + obj.name
        for c in (obj.users_collection or [context.scene.collection]):
            c.objects.link(target)
    md = target.modifiers.new("Thicken", 'SOLIDIFY')
    md.thickness = thickness
    md.offset = {'NORMAL': 1.0, 'OPPOSITE': -1.0}.get(direction, 0.0)
    md.use_even_offset = True
    md.use_quality_normals = True
    md.use_rim = True
    target[HISTORY_KEY] = "Thicken"
    return target


def history_pipe(context, obj, paths, radius, cap, sides):
    """Tube modifiable : une courbe dont l'épaisseur (Data > Geometry > Bevel > Depth) est le rayon.
    Une courbe est copiée telle quelle ; des arêtes de maillage deviennent une polyligne."""
    if obj is not None and obj.type == 'CURVE':
        new = obj.copy()
        new.data = obj.data.copy()
        new.name = "Pipe"
        for c in (obj.users_collection or [context.scene.collection]):
            c.objects.link(new)
        scale = sum(abs(s) for s in obj.matrix_world.to_scale()) / 3.0 or 1.0
    else:
        if not paths:
            return None
        cu = bpy.data.curves.new("Pipe", 'CURVE')
        for P, closed in paths:
            if len(P) < 2:
                continue
            sp = cu.splines.new('POLY')
            sp.points.add(len(P) - 1)
            for pt, p in zip(sp.points, P):
                pt.co = (float(p[0]), float(p[1]), float(p[2]), 1.0)
            sp.use_cyclic_u = bool(closed)
        if not len(cu.splines):
            bpy.data.curves.remove(cu)
            return None
        new = _link_object(context, "Pipe", cu)
        scale = 1.0
    cu = new.data
    cu.dimensions = '3D'
    cu.fill_mode = 'FULL'
    cu.extrude = 0.0
    cu.bevel_mode = 'ROUND'
    cu.bevel_depth = radius / scale
    cu.bevel_resolution = max(0, min(32, int(round(sides / 4.0)) - 1))
    cu.use_fill_caps = bool(cap)
    new[HISTORY_KEY] = "Pipe"
    return new


BOOL_OPS = {'UNION': 'UNION', 'DIFFERENCE': 'DIFFERENCE', 'INTERSECT': 'INTERSECT'}


def _bool_mod(obj, other, op):
    md = obj.modifiers.new("Boolean " + op.capitalize(), 'BOOLEAN')
    md.operation = op
    md.object = other
    try:
        md.solver = 'EXACT'
    except (TypeError, AttributeError):
        pass
    obj[HISTORY_KEY] = "Boolean"
    return md


def _as_cutter(obj):
    """L'opérande reste dans la scène, en fil de fer et hors rendu : le déplacer met le résultat à jour."""
    obj.display_type = 'WIRE'
    obj.hide_render = True
    obj[CUTTER_KEY] = 1


def history_boolean(kind, A, B):
    """Booléen modifiable : modificateurs Boolean sur les objets de base, les autres deviennent des opérandes en fil de fer.
    Retourne (objets résultat, message d'erreur)."""
    op = BOOL_OPS.get(kind)
    if op is None:
        return [], "History is not available for this command"
    if kind == 'UNION':
        if len(A) < 2:
            return [], "Select at least two objects to join"
        for o in A[1:]:
            _bool_mod(A[0], o, 'UNION')
            _as_cutter(o)
        return [A[0]], ""
    if not A or not B:
        return [], "Select the objects on both steps"
    if kind == 'DIFFERENCE':
        for a in A:
            for b in B:
                _bool_mod(a, b, 'DIFFERENCE')
        for b in B:
            _as_cutter(b)
        return list(A), ""
    for o in A[1:]:                      # intersection : (union du premier jeu) inter (union du second jeu)
        _bool_mod(A[0], o, 'UNION')
        _as_cutter(o)
    for o in B[1:]:
        _bool_mod(B[0], o, 'UNION')
        _as_cutter(o)
    _bool_mod(A[0], B[0], 'INTERSECT')
    _as_cutter(B[0])
    return [A[0]], ""


def _late_imports():
    pass
