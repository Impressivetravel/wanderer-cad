"""Wanderer CAD : Booléens vérifiés : Union, Difference, Intersection, Split."""

import bmesh
import bpy
from mathutils import Vector

from .core import idle_tool
from .drawing import find_window_region
from .base import DessinBase


# --------------------------------------------------------------------------
# Booléens : Union, Difference, Intersection, Split
# --------------------------------------------------------------------------

def _link_like(obj, like):
    colls = list(like.users_collection) or [bpy.context.view_layer.active_layer_collection.collection]
    for c in colls:
        c.objects.link(obj)


def boolean_solvers():
    """Solveurs booléens de cette version de Blender (« MANIFOLD » existe depuis Blender 4.5)."""
    try:
        return set(bpy.types.BooleanModifier.bl_rna.properties['solver'].enum_items.keys())
    except (AttributeError, KeyError):
        return {'EXACT'}


def boolean_mesh(base, operands, operation, solver='EXACT', use_self=False):
    """Maillage résultant de `base` combiné (UNION / DIFFERENCE / INTERSECT) avec `operands`, dans l'espace local de base."""
    mods = []
    for o in operands:
        m = base.modifiers.new("cad_bool", 'BOOLEAN')
        m.operation = operation
        m.operand_type = 'OBJECT'
        m.object = o
        m.solver = solver
        if solver == 'EXACT' and use_self:
            m.use_self = True
        mods.append(m)
    try:
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        ev = base.evaluated_get(dg)
        me = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True, depsgraph=dg)
    finally:
        for m in mods:
            base.modifiers.remove(m)
    return me


def _world_volume(obj, me=None):
    """Volume (repère monde) du maillage me (par défaut celui de obj) placé comme obj."""
    bm = bmesh.new()
    try:
        bm.from_mesh(me if me is not None else obj.data)
        return abs(bm.calc_volume()) * abs(obj.matrix_world.to_3x3().determinant())
    finally:
        bm.free()


def _weld_result(me, size):
    """Soude les sommets confondus que les solveurs laissent sur les faces coplanaires (jonctions en T) et retire les
    faces dégénérées. La soudure n'est gardée que si elle ne dégrade pas la fermeture du solide."""
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        closed0 = bool(bm.edges) and all(len(e.link_faces) == 2 for e in bm.edges)
        n0 = len(bm.verts)
        bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=max(1e-7, 1e-6 * size))
        bmesh.ops.dissolve_degenerate(bm, dist=max(1e-8, 1e-7 * size), edges=bm.edges[:])
        if len(bm.verts) == n0:
            return
        if closed0 and not all(len(e.link_faces) == 2 for e in bm.edges):
            return
        bm.normal_update()
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()


def robust_boolean(base, operands, operation):
    """Booléen vérifié : (maillage dans l'espace local de base, sûr).
    Quand tous les objets sont des solides fermés, le résultat doit être un solide fermé au volume cohérent avec
    l'opération ; on essaie Manifold (Blender 4.5+, rapide), puis Exact, puis Exact avec auto-intersection, et on garde
    le premier résultat qui passe le contrôle. Avec une surface ouverte, seul Exact convient et aucun contrôle de volume
    n'est possible. `sûr` est faux si aucun solveur n'a donné un solide vérifié (le meilleur essai est quand même rendu)."""
    objs = [base] + list(operands)
    size = max(max(max(o.dimensions) for o in objs), 1e-6) / max(max(abs(c) for c in base.scale), 1e-6)
    closed = all(mesh_is_closed(o.data) for o in objs)
    if not closed:
        me = boolean_mesh(base, operands, operation, 'EXACT')
        _weld_result(me, size)
        return me, True
    det = max(abs(base.matrix_world.to_3x3().determinant()), 1e-30)
    vols = [_world_volume(o) for o in objs]
    tol = 1e-5 * max(vols) + 1e-12
    if operation == 'UNION':
        lo, hi = max(vols), sum(vols)
    elif operation == 'DIFFERENCE':
        lo, hi = vols[0] - sum(vols[1:]), vols[0]
    else:
        lo, hi = 0.0, min(vols)
    chain = ([('MANIFOLD', False)] if 'MANIFOLD' in boolean_solvers() else []) + [('EXACT', False), ('EXACT', True)]
    fallback = None
    for solver, use_self in chain:
        try:
            me = boolean_mesh(base, operands, operation, solver, use_self)
        except (RuntimeError, TypeError, ValueError):
            continue
        _weld_result(me, size)
        bm = bmesh.new()
        try:
            bm.from_mesh(me)
            empty = len(bm.faces) == 0
            ok_closed = empty or all(len(e.link_faces) == 2 for e in bm.edges)
            if ok_closed and not empty:
                # voile d'épaisseur nulle (parois confondues) : fermé et de volume juste, mais ce n'est pas un solide propre ;
                # il se trahit par des sommets confondus que la soudure n'a pas pu réunir sans ouvrir le maillage
                ok_closed = not bmesh.ops.find_doubles(bm, verts=bm.verts[:], dist=max(1e-7, 1e-6 * size))["targetmap"]
            v = abs(bm.calc_volume()) * det if not empty else 0.0
        finally:
            bm.free()
        if ok_closed and lo - tol <= v <= hi + tol and not (empty and lo > tol):
            if fallback is not None:
                bpy.data.meshes.remove(fallback)
            return me, True
        if fallback is None and solver == 'EXACT':
            fallback = me
        else:
            bpy.data.meshes.remove(me)
    if fallback is None:
        fallback = boolean_mesh(base, operands, operation, 'EXACT')
    return fallback, False


def _temp_union(objs):
    """Objet temporaire = union de plusieurs objets (ou l'objet lui-même s'il est seul). (objet, est_temporaire)."""
    if len(objs) == 1:
        return objs[0], False
    me, _safe = robust_boolean(objs[0], objs[1:], 'UNION')
    tmp = bpy.data.objects.new("cad_tmp", me)
    tmp.matrix_world = objs[0].matrix_world.copy()
    _link_like(tmp, objs[0])
    return tmp, True


def _drop_temp(tmp, is_tmp):
    if is_tmp and tmp is not None:
        me = tmp.data
        bpy.data.objects.remove(tmp)
        if me.users == 0:
            bpy.data.meshes.remove(me)


def _discard_inputs(objs):
    for o in objs:
        try:
            me = o.data
            bpy.data.objects.remove(o)
            if me is not None and me.users == 0:
                bpy.data.meshes.remove(me)
        except (ReferenceError, RuntimeError):
            pass


def run_boolean(kind, A, B, delete_inputs=True):
    """Exécute l'opération ; retourne (objets créés, message d'erreur). run_boolean.unsafe : vrai si un résultat n'a pas
    pu être vérifié (solide non fermé ou volume incohérent)."""
    run_boolean.unsafe = False

    def bool_me(base, operands, op):
        me, safe = robust_boolean(base, operands, op)
        if not safe:
            run_boolean.unsafe = True
        return me

    results = []          # (nom, maillage, matrice, objet modèle pour la collection)
    tmpA = tmpB = None
    isA = isB = False
    try:
        if kind == 'UNION':
            if len(A) < 2:
                return [], "Select at least two objects to join"
            me = bool_me(A[0], A[1:], 'UNION')
            results.append((A[0].name, me, A[0].matrix_world.copy(), A[0]))
            used_B = []
        else:
            if not A or not B:
                return [], "Select the objects on both steps"
            tmpB, isB = _temp_union(B)
            if kind == 'DIFFERENCE':
                for a in A:
                    results.append((a.name, bool_me(a, [tmpB], 'DIFFERENCE'), a.matrix_world.copy(), a))
            elif kind == 'INTERSECT':
                tmpA, isA = _temp_union(A)
                results.append((A[0].name, bool_me(tmpA, [tmpB], 'INTERSECT'), tmpA.matrix_world.copy(), A[0]))
            elif kind == 'SPLIT':
                for a in A:
                    inside = bool_me(a, [tmpB], 'INTERSECT')
                    outside = bool_me(a, [tmpB], 'DIFFERENCE')
                    results.append((a.name, outside, a.matrix_world.copy(), a))
                    results.append((a.name, inside, a.matrix_world.copy(), a))
            used_B = B
    finally:
        _drop_temp(tmpA, isA)
        _drop_temp(tmpB, isB)
    good = []
    for name, me, mw, like in results:
        if len(me.polygons) == 0:
            bpy.data.meshes.remove(me)
        else:
            good.append((name, me, mw, like))
    if not good:
        return [], "No result: the objects do not overlap"
    colls = {id(like): list(like.users_collection) for _n, _m, _w, like in good}
    if kind == 'SPLIT':
        _discard_inputs(list(A))          # les pièces remplacent les objets coupés ; les objets de coupe restent
    elif delete_inputs:
        _discard_inputs(list(A) + list(used_B))
    created = []
    for name, me, mw, like in good:
        obj = bpy.data.objects.new(name, me)
        obj.matrix_world = mw
        cs = colls.get(id(like)) or [bpy.context.view_layer.active_layer_collection.collection]
        for c in cs:
            c.objects.link(obj)
        created.append(obj)
    return created, ""


class DessinBoolean(DessinBase):
    """Base des outils booléens (classe non enregistrée) : sélection par clics, Entrée valide chaque étape."""

    NEEDED = 2
    NUMFIELDS = 0
    EDIT_OK = False
    LOCK_OK = False
    KIND = 'UNION'
    TWO_SETS = False
    STEP_TEXT = ("select the objects to join",)
    DELETE_DEFAULT = True

    def invoke(self, context, event):
        self.stage = 0
        self.setA = []
        self.delete_inputs = self.DELETE_DEFAULT
        self.committed = False
        self._ev = event
        return super().invoke(context, event)

    def selected_meshes(self, context):
        out = []
        for o in context.view_layer.objects:
            try:
                if o.type == 'MESH' and o.select_get() and o.visible_get():
                    out.append(o)
            except RuntimeError:
                pass
        return out

    def prompt(self):
        return ""

    def refresh(self, context):
        n = len(self.selected_meshes(context))
        txt = (f"{self.TITLE} : {self.STEP_TEXT[min(self.stage, len(self.STEP_TEXT) - 1)]}   "
               f"(click: select / deselect, A: all)   |   {n} selected   |   "
               f"Enter/Space: confirm   D: delete input = {'yes' if self.delete_inputs else 'no'}   Esc: cancel")
        try:
            set_prompt(self.area, txt)
            self.area.tag_redraw()
        except ReferenceError:
            pass

    def update_cursor(self, context, event):
        self._ev = event
        self.snap_screen = None
        self.snap_kind = None
        self.cur = Vector()
        self.refresh(context)

    def click(self, context):
        ev = self._ev
        region = find_window_region(self.area, ev.mouse_x, ev.mouse_y)
        if region is None:
            return
        try:
            with context.temp_override(area=self.area, region=region):
                bpy.ops.view3d.select(location=(ev.mouse_x - region.x, ev.mouse_y - region.y), toggle=True)
        except (RuntimeError, TypeError):
            pass
        self.refresh(context)

    def select_all_meshes(self, context):
        for o in context.view_layer.objects:
            try:
                if o.type == 'MESH' and o.visible_get():
                    o.select_set(True)
            except RuntimeError:
                pass

    def confirm(self, context):
        sel = self.selected_meshes(context)
        if self.TWO_SETS and self.stage == 0:
            if not sel:
                self.report({'WARNING'}, "Select at least one object")
                return {'RUNNING_MODAL'}
            self.setA = [o.name for o in sel]
            for o in context.view_layer.objects:
                try:
                    o.select_set(False)
                except RuntimeError:
                    pass
            self.stage = 1
            self.refresh(context)
            return {'RUNNING_MODAL'}
        names = set(self.setA)
        A = [bpy.data.objects[n] for n in self.setA if n in bpy.data.objects] if self.TWO_SETS else sel
        B = [o for o in sel if o.name not in names] if self.TWO_SETS else []
        if not self.TWO_SETS and len(A) < 2:
            self.report({'WARNING'}, "Select at least two objects")
            return {'RUNNING_MODAL'}
        if self.TWO_SETS and not B:
            self.report({'WARNING'}, "Select at least one object in this step")
            return {'RUNNING_MODAL'}
        created, err = run_boolean(self.KIND, A, B, self.delete_inputs)
        if err:
            self.report({'WARNING'}, err)
            return {'RUNNING_MODAL'}
        context.view_layer.update()
        for o in context.view_layer.objects:
            try:
                o.select_set(False)
            except (RuntimeError, AttributeError):
                pass
        for o in created:
            o.select_set(True)
        context.view_layer.objects.active = created[0]
        if getattr(run_boolean, "unsafe", False):
            self.report({'WARNING'}, "The result could not be verified as a closed solid: check the input objects "
                                     "(open edges, self-intersections)")
        self.finished = True
        return self.exit(context)

    def modal(self, context, event):
        if self.area is None or context.area is None:
            self.cleanup(context)
            return {'CANCELLED'}
        if self.tool_id and self.tool_changed(context):
            self.cleanup(context)
            return {'CANCELLED', 'PASS_THROUGH'}
        et = event.type
        if et == 'TIMER':
            return {'PASS_THROUGH'}
        inside = (find_window_region(self.area, event.mouse_x, event.mouse_y) is not None
                  and not self.mouse_over_ui(event))
        if et in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            if inside:
                self.update_cursor(context, event)
                return {'RUNNING_MODAL'}
            return {'PASS_THROUGH'}
        if not inside:
            return {'PASS_THROUGH'}
        if et == 'LEFTMOUSE':
            if event.alt or event.oskey:
                return {'PASS_THROUGH'}
            if event.value == 'PRESS' and not event.ctrl:
                self._ev = event
                self.click(context)
            return {'RUNNING_MODAL'}
        if event.value != 'PRESS':
            return {'PASS_THROUGH'}
        if et == 'ESC':
            return self.exit(context)
        if et in {'RET', 'NUMPAD_ENTER', 'SPACE'}:
            return self.confirm(context)
        if et == 'A' and not (event.ctrl or event.alt or event.oskey):
            self.select_all_meshes(context)
            self.refresh(context)
            return {'RUNNING_MODAL'}
        if et == 'D' and not (event.ctrl or event.alt or event.oskey):
            self.delete_inputs = not self.delete_inputs
            self.refresh(context)
            return {'RUNNING_MODAL'}
        if et == 'TAB':
            return {'RUNNING_MODAL'}
        return {'PASS_THROUGH'}

    def after_finish(self, context):
        if self.tool_id:
            try:
                idle_tool()
            except (RuntimeError, TypeError):
                pass


class DESSIN_OT_bool_union(DessinBoolean):
    bl_idname = "dessin.bool_union"
    bl_label = "Boolean Union"
    bl_description = "Joins several solids into one: click the objects, then Enter (D: keep the originals)"
    TITLE = "Boolean Union"
    KIND = 'UNION'
    STEP_TEXT = ("select the objects to join",)


class DESSIN_OT_bool_difference(DessinBoolean):
    bl_idname = "dessin.bool_difference"
    bl_label = "Boolean Difference"
    bl_description = ("Subtracts solids from others: click the objects to cut into, Enter, then the objects to "
                      "subtract, Enter (D: keep the originals)")
    TITLE = "Boolean Difference"
    KIND = 'DIFFERENCE'
    TWO_SETS = True
    STEP_TEXT = ("select the objects to subtract FROM", "select the objects to subtract")


class DESSIN_OT_bool_intersection(DessinBoolean):
    bl_idname = "dessin.bool_intersection"
    bl_label = "Boolean Intersection"
    bl_description = ("Keeps only the volume shared by two sets of solids: click the first set, Enter, then the "
                      "second set, Enter (D: keep the originals)")
    TITLE = "Boolean Intersection"
    KIND = 'INTERSECT'
    TWO_SETS = True
    STEP_TEXT = ("select the first set of objects", "select the second set of objects")


class DESSIN_OT_bool_split(DessinBoolean):
    bl_idname = "dessin.bool_split"
    bl_label = "Boolean Split"
    bl_description = ("Splits solids with other solids into the part inside and the part outside: click the objects "
                      "to split, Enter, then the cutting objects, Enter (the cutting objects are kept)")
    TITLE = "Boolean Split"
    KIND = 'SPLIT'
    TWO_SETS = True
    STEP_TEXT = ("select the objects to split", "select the cutting objects")


def _late_imports():
    """Noms définis dans des modules chargés après celui-ci : ils ne servent qu'à l'exécution des outils."""
    global mesh_is_closed, set_prompt
    from .gumball_handles import mesh_is_closed
    from .cplane import set_prompt
