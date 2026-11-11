"""Wanderer CAD : Blocs."""

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

from .core import plane_axes
from .drawing import px_scale, region_rv3d
from .base import DessinBase
from .selection import boundary_cached, boundary_world, nearest_segment_px, objects_under_cursor
from .trim import wire_paths
from .surfaces import _plane_of, deselect_all_objects
from .hatch import _select_only
from .curve_tools import (
    _find_layer_col, block_defs, block_edit_state, block_instances, blocks_root, is_block_instance,
    new_block_instance,
)


class DESSIN_OT_block(DessinBase):
    bl_idname = "dessin.block"
    bl_label = "Block"
    bl_description = ("Like Block: select objects, then click the base point. The objects become one block definition "
                      "and are replaced by an instance; every copy of the block updates when the block is edited")

    TITLE = "Block"
    NEEDED = 1
    PLANAR = False
    LOCK_OK = False
    NO_SELECTION = "Select the objects to turn into a block first"

    def lock_allowed(self):
        return False

    def prompt(self):
        return "base point of the block"

    def invoke(self, context, event):
        if context.mode != 'OBJECT':
            self.report({'WARNING'}, "Switch to Object mode")
            return {'CANCELLED'}
        self._objs = [o for o in context.selected_objects if o.type in {'MESH', 'CURVE', 'EMPTY', 'FONT', 'SURFACE', 'LIGHT'}]
        if not self._objs:
            self.report({'INFO'}, self.NO_SELECTION)
            return {'CANCELLED'}
        return super().invoke(context, event)

    def compute(self):
        if self.cur is None:
            return [], [], "", None
        return [self.cur], [], f"{len(self._objs)} object(s)", None

    def click(self, context):
        if self.cur is None:
            return
        make_block(context, self._objs, self.cur.copy())
        self.finished = True


def make_block(context, objs, base, name=None):
    root = blocks_root(context)
    k = 1
    while name is None:
        cand = f"Block {k:02d}"
        if bpy.data.collections.get(cand) is None:
            name = cand
        k += 1
    defcol = bpy.data.collections.new(name)
    root.children.link(defcol)
    defcol.instance_offset = Vector(base)
    top = [o for o in objs if o.parent is None or o.parent not in objs]
    for o in objs:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        defcol.objects.link(o)
    _ = top
    blocks_root(context)
    inst = new_block_instance(context, defcol, Matrix.Translation(Vector(base)), name)
    deselect_all_objects(context)
    inst.select_set(True)
    context.view_layer.objects.active = inst
    return defcol, inst


class DESSIN_OT_block_insert(DessinBase):
    bl_idname = "dessin.block_insert"
    bl_label = "Insert Block"
    bl_description = ("Like Insert: click the insertion points of the block chosen in the tool settings "
                      "(D: next block). Stays active to place several copies")

    TITLE = "Insert Block"
    NEEDED = 1
    PLANAR = False
    LOCK_OK = False
    HAS_MODE = True
    MODES = ("",)
    mode = 0

    def lock_allowed(self):
        return False

    def defs(self):
        return block_defs()

    def current(self):
        ds = self.defs()
        if not ds:
            return None
        return ds[self.mode % len(ds)]

    def prompt(self):
        d = self.current()
        return f"insertion point   [D: block {d.name if d else '-'}]"

    def invoke(self, context, event):
        ds = self.defs()
        if not ds:
            self.report({'INFO'}, "No block yet: create one with Block")
            return {'CANCELLED'}
        self.MODES = tuple(d.name for d in ds)
        want = context.scene.dessin.block_insert
        self.mode = next((i for i, d in enumerate(ds) if d.name == want), 0)
        return super().invoke(context, event)

    def compute(self):
        d = self.current()
        if self.cur is None or d is None:
            return [], [], "", None
        return [self.cur], [], d.name, None

    def click(self, context):
        d = self.current()
        if d is None or self.cur is None:
            return
        st = context.scene.dessin
        try:
            st.block_insert = d.name
        except TypeError:
            pass
        u, v, n = plane_axes(self.axis)
        R = Matrix((u, v, n)).transposed().to_4x4()
        M = Matrix.Translation(self.cur) @ R @ Matrix.Rotation(st.block_rotation, 4, 'Z') @ Matrix.Scale(st.block_scale, 4)
        new_block_instance(context, d, M)
        self.reset_state()
        self.refresh(context)


def explode_block(context, inst):
    """Remplace une instance par des copies réelles des objets du bloc (les blocs imbriqués restent des blocs)."""
    d = inst.instance_collection
    M = inst.matrix_world @ Matrix.Translation(-Vector(d.instance_offset))
    out = []
    cols = list(inst.users_collection) or [context.scene.collection]
    mapping = {}
    for o in d.all_objects:
        c = o.copy()
        if c.data is not None and o.type in {'MESH', 'CURVE', 'FONT', 'SURFACE'}:
            c.data = o.data.copy()
        cols[0].objects.link(c)
        c.matrix_world = M @ o.matrix_world
        mapping[o] = c
        out.append(c)
    for o, c in mapping.items():
        if o.parent in mapping:
            mw = c.matrix_world.copy()
            c.parent = mapping[o.parent]
            c.matrix_world = mw
    bpy.data.objects.remove(inst)
    return out


class DESSIN_OT_block_explode(bpy.types.Operator):
    bl_idname = "dessin.block_explode"
    bl_label = "Explode Block"
    bl_description = "Like ExplodeBlock: turns the selected block instances back into ordinary objects"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        insts = [o for o in context.selected_objects if is_block_instance(o)]
        if not insts:
            self.report({'INFO'}, "Select block instances first")
            return {'CANCELLED'}
        made = []
        for i in insts:
            made.extend(explode_block(context, i))
        _select_only(context, made)
        self.report({'INFO'}, f"{len(insts)} block(s) exploded into {len(made)} object(s)")
        return {'FINISHED'}


class DESSIN_OT_block_edit(bpy.types.Operator):
    bl_idname = "dessin.block_edit"
    bl_label = "Block Edit"
    bl_description = ("Like BlockEdit: edits the selected block in place. Its objects become editable where the instance is "
                      "(the other copies follow the changes); new objects drawn meanwhile are added to the block. "
                      "Close Block Edit to finish")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        if block_edit_state()["inst"] is not None:
            self.report({'INFO'}, "A block is already being edited: Close Block Edit first")
            return {'CANCELLED'}
        inst = context.view_layer.objects.active
        if not is_block_instance(inst):
            inst = next((o for o in context.selected_objects if is_block_instance(o)), None)
        if inst is None:
            self.report({'INFO'}, "Select a block instance first")
            return {'CANCELLED'}
        d = inst.instance_collection
        M = inst.matrix_world @ Matrix.Translation(-Vector(d.instance_offset))
        ed = bpy.data.collections.new(f"Block Edit: {d.name}")
        context.scene.collection.children.link(ed)
        copies = []
        mapping = {}
        for o in d.objects:
            c = o.copy()               # mêmes données : les modifications de forme suivent dans toutes les copies du bloc
            ed.objects.link(c)
            c.matrix_world = M @ o.matrix_world
            c["wd_block_src"] = o.name
            mapping[o] = c
            copies.append(c)
        for o, c in mapping.items():
            if o.parent in mapping:
                mw = c.matrix_world.copy()
                c.parent = mapping[o.parent]
                c.matrix_world = mw
        inst.hide_set(True)
        ed["wd_be_inst"], ed["wd_be_def"] = inst.name, d.name
        ed["wd_be_prev"] = context.view_layer.active_layer_collection.collection.name
        lc = _find_layer_col(context.view_layer.layer_collection, ed)
        if lc is not None:
            context.view_layer.active_layer_collection = lc
        _select_only(context, copies)
        self.report({'INFO'}, f"Editing block {d.name}: Close Block Edit when done")
        return {'FINISHED'}


class DESSIN_OT_block_edit_close(bpy.types.Operator):
    bl_idname = "dessin.block_edit_close"
    bl_label = "Close Block Edit"
    bl_description = "Ends Block Edit: the changes are saved into the block definition and every copy is updated"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        state = block_edit_state()
        if state["inst"] is None:
            self.report({'INFO'}, "No block is being edited")
            return {'CANCELLED'}
        if context.mode != 'OBJECT':
            try:
                bpy.ops.object.mode_set(mode='OBJECT')
            except RuntimeError:
                pass
        inst = bpy.data.objects.get(state["inst"])
        ed = bpy.data.collections.get(state["col"])
        d = bpy.data.collections.get(state["def"] or "")
        if inst is None or ed is None or d is None:
            if ed is not None:          # l'instance ou le bloc n'existe plus : l'édition est abandonnée, ses objets restent
                for k in ("wd_be_inst", "wd_be_def", "wd_be_prev"):
                    if k in ed.keys():
                        del ed[k]
            self.report({'WARNING'}, "Block Edit was interrupted")
            return {'CANCELLED'}
        Minv = (inst.matrix_world @ Matrix.Translation(-Vector(d.instance_offset))).inverted()
        kept = set()
        for c in list(ed.all_objects):
            src = bpy.data.objects.get(c.get("wd_block_src", "")) if c.get("wd_block_src") else None
            if src is not None and src.name in d.objects:
                src.matrix_world = Minv @ c.matrix_world
                if c.data is not None and src.data is not c.data:
                    src.data = c.data
                kept.add(src.name)
                bpy.data.objects.remove(c)
            else:                         # nouvel objet dessiné pendant l'édition : il entre dans le bloc
                mw = Minv @ c.matrix_world
                for col in list(c.users_collection):
                    col.objects.unlink(c)
                d.objects.link(c)
                c.matrix_world = mw
                if "wd_block_src" in c.keys():
                    del c["wd_block_src"]
                kept.add(c.name)
        for o in list(d.objects):        # objets supprimés pendant l'édition
            if o.name not in kept:
                bpy.data.objects.remove(o)
        prev = bpy.data.collections.get(state.get("prev_col") or "")
        bpy.data.collections.remove(ed)
        try:
            inst.hide_set(False)
        except RuntimeError:
            pass
        if prev is not None:
            lc = _find_layer_col(context.view_layer.layer_collection, prev)
            if lc is not None:
                context.view_layer.active_layer_collection = lc
        _select_only(context, [inst])
        self.report({'INFO'}, f"Block {d.name} updated ({len(block_instances(d))} copies)")
        return {'FINISHED'}


class DESSIN_OT_block_delete(bpy.types.Operator):
    bl_idname = "dessin.block_delete"
    bl_label = "Delete Block"
    bl_description = "Deletes a block definition and all its copies"
    bl_options = {'REGISTER', 'UNDO'}

    name: bpy.props.StringProperty()

    def execute(self, context):
        d = bpy.data.collections.get(self.name)
        if d is None:
            return {'CANCELLED'}
        for i in block_instances(d):
            bpy.data.objects.remove(i)
        for o in list(d.objects):
            if len(o.users_collection) <= 1:
                bpy.data.objects.remove(o)
        bpy.data.collections.remove(d)
        return {'FINISHED'}


class DESSIN_OT_block_select(bpy.types.Operator):
    bl_idname = "dessin.block_select"
    bl_label = "Select Block Copies"
    bl_description = "Selects every copy of this block"
    bl_options = {'REGISTER', 'UNDO'}

    name: bpy.props.StringProperty()

    def execute(self, context):
        d = bpy.data.collections.get(self.name)
        if d is None:
            return {'CANCELLED'}
        _select_only(context, [i for i in block_instances(d) if i.visible_get()])
        return {'FINISHED'}


class DESSIN_PT_blocks(bpy.types.Panel):
    bl_label = "Blocks"
    bl_idname = "DESSIN_PT_blocks"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Wanderer"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        lay = self.layout
        st = context.scene.dessin
        be_state = block_edit_state()
        if be_state["inst"] is not None:
            box = lay.box()
            box.alert = True
            box.label(text=f"Editing block {be_state['def']}", icon='EDITMODE_HLT')
            box.operator(DESSIN_OT_block_edit_close.bl_idname, icon='CHECKMARK')
        row = lay.row(align=True)
        row.operator(DESSIN_OT_block.bl_idname, text="Block")
        row.operator(DESSIN_OT_block_edit.bl_idname, text="Edit")
        row.operator(DESSIN_OT_block_explode.bl_idname, text="Explode")
        ds = block_defs()
        if not ds:
            lay.label(text="No block yet")
            return
        col = lay.column(align=True)
        col.prop(st, "block_insert", text="")
        col.prop(st, "block_scale")
        col.prop(st, "block_rotation")
        lay.operator(DESSIN_OT_block_insert.bl_idname, text="Insert", icon='ADD')
        box = lay.box()
        for d in ds:
            r = box.row(align=True)
            r.prop(d, "name", text="")
            r.label(text=str(len(block_instances(d))))
            op = r.operator(DESSIN_OT_block_select.bl_idname, text="", icon='RESTRICT_SELECT_OFF')
            op.name = d.name
            op = r.operator(DESSIN_OT_block_delete.bl_idname, text="", icon='TRASH')
            op.name = d.name


# ---- Untrim / UntrimHoles ----

def save_untrimmed(obj):
    """Garde une copie de la surface avant sa première découpe (Trim, Split, Fillet Surface...) pour Untrim."""
    try:
        key = obj.get("wd_untrimmed")
        if key and bpy.data.meshes.get(key) is not None:
            return
        cp = obj.data.copy()
        cp.name = ".wd_untrim " + obj.name
        cp.use_fake_user = True
        obj["wd_untrimmed"] = cp.name
    except (AttributeError, ReferenceError, TypeError):
        pass


def boundary_loops(me):
    """Bords libres d'un maillage : [(indices de sommets, fermé)]."""
    cnt = {}
    for p in me.polygons:
        for ek in p.edge_keys:
            cnt[ek] = cnt.get(ek, 0) + 1
    edges = [ek for ek, k in cnt.items() if k == 1]
    if not edges:
        return []
    return wire_paths(len(me.vertices), edges)


def outer_loop_index(me, loops):
    """Le bord extérieur : la boucle la plus étendue (les autres sont des trous)."""
    best, bd = 0, -1.0
    for i, (idx, _c) in enumerate(loops):
        P = np.array([tuple(me.vertices[j].co) for j in idx])
        d = float(np.linalg.norm(P.max(axis=0) - P.min(axis=0)))
        if d > bd:
            best, bd = i, d
    return best


def fill_hole(obj, idx):
    """Bouche un trou (boucle de bord) : une face plane, ou des triangles si le trou n'est pas plan."""
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    ring = [bm.verts[i] for i in idx]
    if len(ring) > 1 and ring[0] is ring[-1]:
        ring = ring[:-1]
    edges = []
    for a, b in zip(ring, ring[1:] + ring[:1]):
        e = bm.edges.get((a, b))
        if e is not None:
            edges.append(e)
    res = bmesh.ops.holes_fill(bm, edges=edges, sides=0)
    faces = res.get("faces", [])
    P = np.array([tuple(v.co) for v in ring])
    pl = _plane_of(P) if len(P) >= 3 else None
    if faces and (pl is None or pl[2] > 1e-4 * max(float(np.ptp(P, axis=0).max()), 1e-9)):
        bmesh.ops.triangulate(bm, faces=faces)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    me.update()
    return bool(faces)


def untrim_outer(obj):
    """Rend sa forme d'origine à une surface découpée : la copie gardée avant la découpe, sinon (surface plane) le
    rectangle qui l'englobe, comme la surface sous-jacente d'un PlanarSrf de Rhino. Retourne un message ou None."""
    key = obj.get("wd_untrimmed")
    src = bpy.data.meshes.get(key) if key else None
    me = obj.data
    if src is not None:
        new = src.copy()
        new.use_fake_user = False
        new.name = me.name
        mats = list(me.materials)
        obj.data = new
        if not len(new.materials):
            for m_ in mats:
                new.materials.append(m_)
        if me.users == 0:
            bpy.data.meshes.remove(me)
        del obj["wd_untrimmed"]
        if not any(o.get("wd_untrimmed") == key for o in bpy.data.objects):
            bpy.data.meshes.remove(src)
        return None
    P = np.array([tuple(v.co) for v in me.vertices])
    if len(P) < 3:
        return "Nothing to untrim"
    loops = boundary_loops(me)
    if not loops:
        return "This surface has no free edge"
    outer = np.array([tuple(me.vertices[j].co) for j in loops[outer_loop_index(me, loops)][0]])
    pl = _plane_of(outer) if len(outer) >= 3 else None
    if pl is None or float(np.abs((P - pl[0]) @ pl[1]).max()) > 1e-4 * max(float(np.ptp(P, axis=0).max()), 1e-9):
        return "No original shape kept for this surface (only surfaces trimmed by Wanderer, or flat ones, can be untrimmed)"
    c, n = pl[0], pl[1]
    u = None
    for ax in (np.array((1.0, 0.0, 0.0)), np.array((0.0, 1.0, 0.0))):
        e = ax - n * float(ax @ n)
        if np.linalg.norm(e) > 0.3:
            u = e / np.linalg.norm(e)
            break
    v = np.cross(n, u)
    q = np.stack([(outer - c) @ u, (outer - c) @ v], axis=1)
    lo, hi = q.min(axis=0), q.max(axis=0)
    corners = [c + u * a + v * b for a, b in ((lo[0], lo[1]), (hi[0], lo[1]), (hi[0], hi[1]), (lo[0], hi[1]))]
    bm = bmesh.new()
    vs = [bm.verts.new(tuple(p)) for p in corners]
    f = bm.faces.new(vs)
    old_n = me.polygons[0].normal if len(me.polygons) else None
    bm.normal_update()
    if old_n is not None and f.normal.dot(old_n) < 0:
        f.normal_flip()
    bm.to_mesh(me)
    bm.free()
    me.update()
    return None


def pick_boundary_loop(op, context, px=14.0):
    """(objet, boucles, index de la boucle, index du bord extérieur) : bord libre le plus proche du curseur."""
    mouse = getattr(op, "_mouse", None)
    if mouse is None or op.region is None:
        return None
    try:
        rv3d = region_rv3d(op.region, op.area)
    except (AttributeError, ReferenceError):
        return None
    m_ = Vector(mouse)
    best, bd = None, px * px_scale()
    persp = np.array(rv3d.perspective_matrix, dtype=np.float64)
    for o in objects_under_cursor(context, op.region, rv3d, m_.x, m_.y, bd):
        if o.type != 'MESH' or not len(o.data.polygons) or len(o.data.edges) > 40000 or "dessin_hatch" in o.keys():
            continue
        loops = boundary_cached(o)[0]
        if not loops:
            continue
        _fa, _fb, _fi, LA, LB, LL = boundary_world(o)
        i, d = nearest_segment_px(LA, LB, persp, op.region, m_.x, m_.y)      # tous les bords de l'objet en un calcul
        if i is not None and d < bd:
            best, bd = (o, loops, int(LL[i])), d
    if best is None:
        return None
    o, loops, li = best
    return o, loops, li, outer_loop_index(o.data, loops)


def _late_imports():
    pass
