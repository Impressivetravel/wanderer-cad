"""Wanderer CAD : Calques (collections de Blender présentées comme dans Rhino)."""

import bpy
import json
import time

from .core import FR_ALIASES


# --------------------------------------------------------------------------
# Calques : les collections de Blender, présentées comme les calques de Rhino (couleur, visibilité, verrou, calque courant)
# --------------------------------------------------------------------------

LAYER_PALETTE = ((0.90, 0.30, 0.30), (0.95, 0.60, 0.20), (0.95, 0.85, 0.25), (0.45, 0.78, 0.35),
                 (0.25, 0.75, 0.75), (0.30, 0.55, 0.95), (0.65, 0.45, 0.90), (0.90, 0.45, 0.75))
_LAYERCOL = {"carry": None, "carry_mode": "INSIDE", "n": -1, "pending": False, "sync": False, "sel": [], "anchor": None, "last": ("", 0.0)}


def layer_apply_color(col):
    """Reporte la couleur du calque sur ses objets (couleur d'objet, visible en affichage « Object » / filaire)."""
    pg = col.dessin_layer
    for o in col.objects:
        try:
            if pg.use_color:
                o.color = (pg.color[0], pg.color[1], pg.color[2], 1.0)
                o["wd_lc"] = 1
            elif o.get("wd_lc"):
                o.color = (1.0, 1.0, 1.0, 1.0)
                del o["wd_lc"]
        except (RuntimeError, ReferenceError, KeyError):
            pass


def _layer_color_update(self, context):
    if not self.use_color:
        self.use_color = True     # choisir une couleur l'active
        return
    try:
        layer_apply_color(self.id_data)
    except (RuntimeError, ReferenceError, AttributeError):
        pass


def _layer_use_color_update(self, context):
    try:
        layer_apply_color(self.id_data)
    except (RuntimeError, ReferenceError, AttributeError):
        pass


class DESSIN_PG_layer(bpy.types.PropertyGroup):
    folded: bpy.props.BoolProperty(name="Folded", default=False, description="Hides the sublayers in the list")
    use_color: bpy.props.BoolProperty(name="Layer color", default=False, update=_layer_use_color_update,
                                      description="Objects of this layer take the layer color")
    color: bpy.props.FloatVectorProperty(name="Color", subtype='COLOR', size=3, min=0.0, max=1.0, default=(0.8, 0.8, 0.8),
                                         update=_layer_color_update, description="Color of the layer")


def layer_rows(context):
    """[(profondeur, layer_collection)] : la scène puis ses calques, dans l'ordre de l'arborescence."""
    out = []
    alpha = context.scene.dessin.layer_sort_alpha

    def walk(lc, depth):
        out.append((depth, lc))
        for ch in (sorted(lc.children, key=lambda x: x.name.lower()) if alpha else lc.children):
            walk(ch, depth + 1)

    walk(context.view_layer.layer_collection, 0)
    return out


def find_layer_collection(root, name):
    if root.name == name:
        return root
    for ch in root.children:
        r = find_layer_collection(ch, name)
        if r is not None:
            return r
    return None


def collection_parent(root, target):
    for ch in root.children:
        if ch == target:
            return root
        r = collection_parent(ch, target)
        if r is not None:
            return r
    return None


def layer_sync_new_objects():
    """Les nouveaux objets (outils de dessin, import) prennent la couleur de leur calque."""
    _LAYERCOL["pending"] = False
    try:
        objs = list(bpy.data.objects)
    except (RuntimeError, AttributeError):
        return None
    for o in objs:
        try:
            if o.get("wd_lc") or o.users_collection is None or not len(o.users_collection):
                continue
            c = o.users_collection[0]
            pg = getattr(c, "dessin_layer", None)
            if pg is not None and pg.use_color and tuple(o.color) == (1.0, 1.0, 1.0, 1.0):
                o.color = (pg.color[0], pg.color[1], pg.color[2], 1.0)
                o["wd_lc"] = 1
        except (RuntimeError, ReferenceError, AttributeError):
            pass
    return None


def layer_check_new_objects():
    """Appelé à chaque mise à jour de la scène : ne fait quelque chose que si le nombre d'objets a changé."""
    try:
        n = len(bpy.data.objects)
    except (RuntimeError, AttributeError):
        return
    if n != _LAYERCOL["n"]:
        _LAYERCOL["n"] = n
        if not _LAYERCOL["pending"]:
            _LAYERCOL["pending"] = True
            try:
                bpy.app.timers.register(layer_sync_new_objects, first_interval=0.1)
            except (RuntimeError, ValueError):
                _LAYERCOL["pending"] = False


def new_layer_name(prefix="Layer"):
    i = 1
    while True:
        name = f"{prefix} {i:02d}"
        if name not in bpy.data.collections:
            return name
        i += 1


def layer_activate(context, layer):
    """Rend courant le calque désigné (menu contextuel d'un calque)."""
    if layer:
        lc = find_layer_collection(context.view_layer.layer_collection, layer)
        if lc is not None:
            context.view_layer.active_layer_collection = lc


def layer_targets(context, layer=""):
    """Calques visés par une action : la sélection de calques si le calque cliqué en fait partie, sinon ce calque, sinon le calque courant."""
    names = {lc.name for _d, lc in layer_rows(context)}
    sel = [n for n in _LAYERCOL["sel"] if n in names]
    if layer:
        return sel if (layer in sel and len(sel) > 1) else [layer]
    if sel:
        return sel
    cur = context.view_layer.active_layer_collection
    return [cur.name] if cur != context.view_layer.layer_collection else []


def layer_set_flag(lc, what, value):
    c = lc.collection
    if what == 'EXCLUDE':
        lc.exclude = value
    elif what == 'HIDE':
        lc.hide_viewport = value
    elif what == 'SELECTABLE':
        c.hide_select = not value
    elif what == 'VIEWPORT':
        c.hide_viewport = not value
    elif what == 'RENDER':
        c.hide_render = not value
    elif what == 'HOLDOUT':
        lc.holdout = value
    elif what == 'INDIRECT':
        lc.indirect_only = value


def layer_get_flag(lc, what):
    c = lc.collection
    return {'EXCLUDE': lc.exclude, 'HIDE': lc.hide_viewport, 'SELECTABLE': not c.hide_select,
            'VIEWPORT': not c.hide_viewport, 'RENDER': not c.hide_render, 'HOLDOUT': lc.holdout,
            'INDIRECT': lc.indirect_only}[what]


def layer_select_objects(context, col, extend=False):
    if not extend:
        for o in context.view_layer.objects:
            try:
                o.select_set(False)
            except RuntimeError:
                pass
    count = 0
    for o in col.all_objects:
        try:
            if o.visible_get() and not o.hide_select:
                o.select_set(True)
                count += 1
        except (RuntimeError, ReferenceError):
            pass
    return count


class DESSIN_OT_layer_current(bpy.types.Operator):
    bl_idname = "dessin.layer_current"
    bl_label = "Set Current Layer"
    bl_description = ("Click: makes this layer the current one (new objects are created in it) and selects its objects.  "
                      "Shift+click adds them to the selection.  Ctrl/Cmd+click renames the layer")
    bl_options = {'INTERNAL', 'UNDO'}     # sélection, calque courant, déplacement de calque : annulables

    name: bpy.props.StringProperty()
    select: bpy.props.BoolProperty(default=False)

    def invoke(self, context, event):
        lc = find_layer_collection(context.view_layer.layer_collection, self.name)
        if lc is None:
            return {'CANCELLED'}
        context.view_layer.active_layer_collection = lc
        if self.select and event.ctrl and lc.collection != context.scene.collection:
            return bpy.ops.dessin.layer_rename('INVOKE_DEFAULT')
        if self.select and context.mode == 'OBJECT':
            layer_select_objects(context, lc.collection, extend=event.shift)
        return {'FINISHED'}

    def execute(self, context):
        lc = find_layer_collection(context.view_layer.layer_collection, self.name)
        if lc is None:
            return {'CANCELLED'}
        context.view_layer.active_layer_collection = lc
        return {'FINISHED'}


class DESSIN_OT_layer_click(bpy.types.Operator):
    bl_idname = "dessin.layer_click"
    bl_label = "Layer"
    bl_description = ("Click: current layer, and selects its objects.  Shift+click: adds or removes a layer from the selection.  "
                      "Ctrl/Cmd+click: selects the range from the last clicked layer.  Double-click: rename.  Right-click: more actions")
    bl_options = {'INTERNAL', 'UNDO'}     # sélection, calque courant, déplacement de calque : annulables

    layer: bpy.props.StringProperty()

    def invoke(self, context, event):
        name = self.layer
        lc = find_layer_collection(context.view_layer.layer_collection, name)
        if lc is None:
            return {'CANCELLED'}
        carry = _LAYERCOL["carry"]
        if carry:
            _LAYERCOL["carry"] = None
            if carry != name:
                if layer_drop(context, carry, name, _LAYERCOL["carry_mode"]):
                    self.report({'INFO'}, f"{carry} moved")
                else:
                    self.report({'WARNING'}, "A layer cannot be moved into itself or its own sublayers")
            return {'FINISHED'}
        if event.alt:
            _LAYERCOL["carry"] = name
            return {'FINISHED'}
        now = time.monotonic()
        last_name, last_t = _LAYERCOL["last"]
        _LAYERCOL["last"] = (name, now)
        plain = not (event.shift or event.ctrl or event.alt)
        if plain and last_name == name and now - last_t < 0.4:
            _LAYERCOL["last"] = ("", 0.0)
            context.view_layer.active_layer_collection = lc
            return bpy.ops.dessin.layer_rename('INVOKE_DEFAULT', layer=name)
        sel = _LAYERCOL["sel"]
        if event.shift:
            if name in sel:
                sel.remove(name)
            else:
                sel.append(name)
            _LAYERCOL["anchor"] = name
        elif event.ctrl and _LAYERCOL["anchor"]:
            order = [l.name for _d, l in layer_rows(context)[1:]]
            a = _LAYERCOL["anchor"]
            if a in order and name in order:
                i, j = sorted((order.index(a), order.index(name)))
                _LAYERCOL["sel"] = order[i:j + 1]
        else:
            _LAYERCOL["sel"] = [name]
            _LAYERCOL["anchor"] = name
        context.view_layer.active_layer_collection = lc
        if context.mode == 'OBJECT' and context.scene.dessin.layer_sync_select:
            first = True
            for n in layer_targets(context):
                l2 = find_layer_collection(context.view_layer.layer_collection, n)
                if l2 is not None:
                    layer_select_objects(context, l2.collection, extend=not first)
                    first = False
        return {'FINISHED'}


class DESSIN_OT_layer_set(bpy.types.Operator):
    bl_idname = "dessin.layer_set"
    bl_label = "Set Layer State"
    bl_description = "Changes a layer setting (on every selected layer)"
    bl_options = {'REGISTER', 'UNDO'}

    layer: bpy.props.StringProperty(options={'SKIP_SAVE', 'HIDDEN'})
    what: bpy.props.EnumProperty(items=(('EXCLUDE', "Exclude", ""), ('HIDE', "Hide", ""), ('SELECTABLE', "Selectable", ""),
                                        ('VIEWPORT', "Viewport", ""), ('RENDER', "Render", ""),
                                        ('HOLDOUT', "Holdout", ""), ('INDIRECT', "Indirect only", "")))
    value: bpy.props.BoolProperty(default=True)

    def execute(self, context):
        for n in layer_targets(context, self.layer):
            lc = find_layer_collection(context.view_layer.layer_collection, n)
            if lc is not None:
                layer_set_flag(lc, self.what, self.value)
        return {'FINISHED'}


def layer_copy_tree(src, parent, context):
    """Copie d'un calque : sous-calques, objets (copies indépendantes) et couleur."""
    new = bpy.data.collections.new(src.name)
    parent.children.link(new)
    new.dessin_layer.color = src.dessin_layer.color
    new.dessin_layer.use_color = src.dessin_layer.use_color
    for o in src.objects:
        o2 = o.copy()
        if o.data is not None:
            try:
                o2.data = o.data.copy()
            except (AttributeError, RuntimeError):
                pass
        new.objects.link(o2)
    for ch in src.children:
        layer_copy_tree(ch, new, context)
    return new


class DESSIN_OT_layer_duplicate(bpy.types.Operator):
    bl_idname = "dessin.layer_duplicate"
    bl_label = "Duplicate Layer"
    bl_description = "Duplicates the layer with its sublayers and objects (independent copies)"
    bl_options = {'REGISTER', 'UNDO'}

    layer: bpy.props.StringProperty(options={'SKIP_SAVE', 'HIDDEN'})

    def execute(self, context):
        root = context.scene.collection
        made = []
        for n in layer_targets(context, self.layer):
            src = bpy.data.collections.get(n)
            if src is None:
                continue
            par = collection_parent(root, src) or root
            made.append(layer_copy_tree(src, par, context))
        if made:
            lc = find_layer_collection(context.view_layer.layer_collection, made[-1].name)
            if lc is not None:
                context.view_layer.active_layer_collection = lc
        self.report({'INFO'}, f"{len(made)} layer(s) duplicated")
        return {'FINISHED'}


class DESSIN_OT_layer_delete_all(bpy.types.Operator):
    bl_idname = "dessin.layer_delete_all"
    bl_label = "Delete Layer and Contents"
    bl_description = "Deletes the layer(s) together with their sublayers and objects (can be undone)"
    bl_options = {'REGISTER', 'UNDO'}

    layer: bpy.props.StringProperty(options={'SKIP_SAVE', 'HIDDEN'})

    def execute(self, context):
        names = layer_targets(context, self.layer)
        n_obj = 0

        def kill(c):
            nonlocal n_obj
            for ch in list(c.children):
                kill(ch)
            for o in list(c.objects):
                bpy.data.objects.remove(o)
                n_obj += 1
            bpy.data.collections.remove(c)

        for n in names:
            c = bpy.data.collections.get(n)
            if c is not None:
                kill(c)
        _LAYERCOL["sel"] = []
        self.report({'INFO'}, f"{len(names)} layer(s) and {n_obj} object(s) deleted")
        return {'FINISHED'}


class DESSIN_OT_layer_object(bpy.types.Operator):
    bl_idname = "dessin.layer_object"
    bl_label = "Object"
    bl_description = "Click: selects the object.  Shift+click: adds it to the selection"
    bl_options = {'INTERNAL', 'UNDO'}     # sélection, calque courant, déplacement de calque : annulables

    name: bpy.props.StringProperty()
    action: bpy.props.EnumProperty(items=(('SELECT', "Select", ""), ('HIDE', "Hide", "")), default='SELECT')

    def invoke(self, context, event):
        o = bpy.data.objects.get(self.name)
        if o is None:
            return {'CANCELLED'}
        if self.action == 'HIDE':
            try:
                o.hide_set(not o.hide_get())
            except RuntimeError:
                pass
            return {'FINISHED'}
        if context.mode != 'OBJECT':
            return {'CANCELLED'}
        if not event.shift:
            for x in context.view_layer.objects:
                try:
                    x.select_set(False)
                except RuntimeError:
                    pass
        try:
            o.select_set(not o.select_get() if event.shift else True)
            if o.select_get():
                context.view_layer.objects.active = o
        except RuntimeError:
            pass
        return {'FINISHED'}


def layer_drop(context, name, target, where):
    """Déplace le calque `name` : dans `target` (INSIDE), avant (ABOVE) ou après (BELOW) lui."""
    root = context.scene.collection
    col = bpy.data.collections.get(name)
    tgt = bpy.data.collections.get(target)
    if col is None or tgt is None or col == tgt or tgt in col.children_recursive:
        return False
    snap = layer_snapshot(context)
    act = context.view_layer.active_layer_collection.name
    old = collection_parent(root, col)
    if old is None:
        return False
    if where == 'INSIDE':
        old.children.unlink(col)
        tgt.children.link(col)
    else:
        par = collection_parent(root, tgt) or root
        old.children.unlink(col)
        order = list(par.children)
        i = order.index(tgt) + (1 if where == 'BELOW' else 0)
        order.insert(i, col)
        for ch in list(par.children):
            par.children.unlink(ch)
        for ch in order:
            par.children.link(ch)
    layer_restore(context, snap, act)
    return True


class DESSIN_OT_layer_carry(bpy.types.Operator):
    bl_idname = "dessin.layer_carry"
    bl_label = "Pick Up Layer"
    bl_description = ("Picks the layer up to move it: then choose Above, Below or Inside and click the layer where it should go "
                      "(a drag and drop in two clicks). Alt+click on a layer name does the same")
    bl_options = {'INTERNAL'}

    layer: bpy.props.StringProperty(options={'SKIP_SAVE', 'HIDDEN'})
    mode: bpy.props.StringProperty(default="", options={'SKIP_SAVE', 'HIDDEN'})

    def execute(self, context):
        if self.mode:
            _LAYERCOL["carry_mode"] = self.mode
            return {'FINISHED'}
        _LAYERCOL["carry"] = self.layer or None
        return {'FINISHED'}


class DESSIN_OT_layer_fold(bpy.types.Operator):
    bl_idname = "dessin.layer_fold"
    bl_label = "Fold Sublayers"
    bl_description = "Folds or unfolds the sublayers in the list"
    bl_options = {'INTERNAL'}

    layer: bpy.props.StringProperty(options={'SKIP_SAVE', 'HIDDEN'})
    action: bpy.props.EnumProperty(items=(('TOGGLE', "Toggle", ""), ('EXPAND_ALL', "Unfold all", ""), ('COLLAPSE_ALL', "Fold all", ""),
                                          ('EXPAND_CHILDREN', "Unfold layer and sublayers", "")), default='TOGGLE')

    def execute(self, context):
        rows = layer_rows(context)[1:]
        if self.action == 'TOGGLE':
            c = bpy.data.collections.get(self.layer)
            if c is not None:
                c.dessin_layer.folded = not c.dessin_layer.folded
        elif self.action == 'EXPAND_CHILDREN':
            c = bpy.data.collections.get(self.layer)
            if c is not None:
                c.dessin_layer.folded = False
                for ch in c.children_recursive:
                    ch.dessin_layer.folded = False
        else:
            for _d, lc in rows:
                if lc.children:
                    lc.collection.dessin_layer.folded = self.action == 'COLLAPSE_ALL'
        return {'FINISHED'}


class DESSIN_OT_layer_reparent(bpy.types.Operator):
    bl_idname = "dessin.layer_reparent"
    bl_label = "Move Layer To"
    bl_description = "Moves the layer (with its sublayers) into another layer, or to the top level"
    bl_options = {'REGISTER', 'UNDO'}

    layer: bpy.props.StringProperty(options={'SKIP_SAVE', 'HIDDEN'})
    target: bpy.props.StringProperty(options={'SKIP_SAVE', 'HIDDEN'})

    def execute(self, context):
        root = context.scene.collection
        tgt = bpy.data.collections.get(self.target) if self.target else root
        if tgt is None:
            return {'CANCELLED'}
        snap = layer_snapshot(context)
        moved = 0
        for n in layer_targets(context, self.layer):
            col = bpy.data.collections.get(n)
            if col is None or col == tgt or tgt in col.children_recursive:
                continue
            par = collection_parent(root, col)
            if par is None or par == tgt:
                continue
            par.children.unlink(col)
            tgt.children.link(col)
            moved += 1
        layer_restore(context, snap, context.view_layer.active_layer_collection.name)
        self.report({'INFO'}, f"{moved} layer(s) moved")
        return {'FINISHED'}


class DESSIN_MT_layer_move_to(bpy.types.Menu):
    bl_label = "Move Layer To"
    bl_idname = "DESSIN_MT_layer_move_to"

    def draw(self, context):
        lay = self.layout
        src = bpy.data.collections.get(_LAYERCOL.get("menu_layer", ""))
        if src is None:
            return
        banned = {src.name} | {c.name for c in src.children_recursive}
        o = lay.operator(DESSIN_OT_layer_reparent.bl_idname, text="Scene (top level)", icon='SCENE_DATA')
        o.layer = src.name
        o.target = ""
        for depth, lc in layer_rows(context)[1:]:
            if lc.name in banned:
                continue
            o = lay.operator(DESSIN_OT_layer_reparent.bl_idname, text=("    " * (depth - 1)) + lc.name, icon='OUTLINER_COLLECTION')
            o.layer = src.name
            o.target = lc.name


def layer_state_dump(context):
    d = {}
    for _dp, lc in layer_rows(context)[1:]:
        c = lc.collection
        d[lc.name] = [lc.exclude, lc.hide_viewport, c.hide_select, c.hide_viewport, c.hide_render, lc.holdout, lc.indirect_only]
    return json.dumps(d)


class DESSIN_OT_layer_state(bpy.types.Operator):
    bl_idname = "dessin.layer_state"
    bl_label = "Layer State"
    bl_description = "Saves the visibility and lock settings of all layers under a name, restores them, or deletes the state"
    bl_options = {'REGISTER', 'UNDO'}

    action: bpy.props.EnumProperty(items=(('SAVE', "Save", ""), ('APPLY', "Restore", ""), ('DELETE', "Delete", ""), ('UPDATE', "Update", "")))
    index: bpy.props.IntProperty(default=-1, options={'SKIP_SAVE'})

    def execute(self, context):
        st = context.scene.dessin
        if self.action == 'SAVE':
            name = st.layer_state_name.strip() or f"State {len(st.layer_states) + 1}"
            it = st.layer_states.add()
            it.name = name
            it.data = layer_state_dump(context)
            st.layer_state_name = ""
            return {'FINISHED'}
        if not 0 <= self.index < len(st.layer_states):
            return {'CANCELLED'}
        it = st.layer_states[self.index]
        if self.action == 'DELETE':
            st.layer_states.remove(self.index)
        elif self.action == 'UPDATE':
            it.data = layer_state_dump(context)
        else:
            try:
                d = json.loads(it.data)
            except ValueError:
                return {'CANCELLED'}
            for _dp, lc in layer_rows(context)[1:]:
                v = d.get(lc.name)
                if v is None or len(v) != 7:
                    continue
                c = lc.collection
                lc.exclude, lc.hide_viewport, c.hide_select, c.hide_viewport, c.hide_render, lc.holdout, lc.indirect_only = v
        return {'FINISHED'}


class DESSIN_OT_layer_rename(bpy.types.Operator):
    bl_idname = "dessin.layer_rename"
    bl_label = "Rename Layer"
    bl_description = "Renames the current layer"
    bl_options = {'REGISTER', 'UNDO'}

    new_name: bpy.props.StringProperty(name="Name")
    layer: bpy.props.StringProperty(options={'SKIP_SAVE', 'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return context.view_layer.active_layer_collection.collection != context.scene.collection

    def invoke(self, context, event):
        layer_activate(context, self.layer)
        self.new_name = context.view_layer.active_layer_collection.collection.name
        return context.window_manager.invoke_props_dialog(self, width=260)

    def execute(self, context):
        if self.new_name.strip():
            context.view_layer.active_layer_collection.collection.name = self.new_name.strip()
        return {'FINISHED'}


def layer_snapshot(context):
    snap = {}
    for vl in context.scene.view_layers:
        def walk(lc, vl=vl):
            snap[(vl.name, lc.name)] = (lc.exclude, lc.hide_viewport, lc.holdout, lc.indirect_only)
            for ch in lc.children:
                walk(ch)
        for ch in vl.layer_collection.children:
            walk(ch)
    return snap


def layer_restore(context, snap, active_name):
    for vl in context.scene.view_layers:
        def walk(lc, vl=vl):
            st = snap.get((vl.name, lc.name))
            if st is not None:
                try:
                    lc.exclude, lc.hide_viewport, lc.holdout, lc.indirect_only = st
                except (AttributeError, TypeError):
                    pass
            for ch in lc.children:
                walk(ch)
        for ch in vl.layer_collection.children:
            walk(ch)
    lc = find_layer_collection(context.view_layer.layer_collection, active_name)
    if lc is not None:
        context.view_layer.active_layer_collection = lc


class DESSIN_OT_layer_move(bpy.types.Operator):
    bl_idname = "dessin.layer_move"
    bl_label = "Move Layer"
    bl_description = "Moves the current layer: up or down in the list, into the sublayers of the layer above (In), or out to its parent's level (Out)"
    bl_options = {'REGISTER', 'UNDO'}

    layer: bpy.props.StringProperty(options={'SKIP_SAVE', 'HIDDEN'})

    direction: bpy.props.EnumProperty(items=(('UP', "Up", ""), ('DOWN', "Down", ""), ('IN', "In", ""), ('OUT', "Out", "")))

    @classmethod
    def poll(cls, context):
        return context.view_layer.active_layer_collection.collection != context.scene.collection

    def execute(self, context):
        layer_activate(context, self.layer)
        root = context.scene.collection
        col = context.view_layer.active_layer_collection.collection
        parent = collection_parent(root, col)
        if parent is None:
            return {'CANCELLED'}
        sib = list(parent.children)
        i = sib.index(col)
        snap = layer_snapshot(context)

        def relink(par, order):
            for ch in list(par.children):
                par.children.unlink(ch)
            for ch in order:
                par.children.link(ch)

        d = self.direction
        if d in ('UP', 'DOWN'):
            j = i - 1 if d == 'UP' else i + 1
            if j < 0 or j >= len(sib):
                return {'CANCELLED'}
            sib[i], sib[j] = sib[j], sib[i]
            relink(parent, sib)
        elif d == 'IN':
            if i == 0:
                self.report({'INFO'}, "There is no layer above to move into")
                return {'CANCELLED'}
            parent.children.unlink(col)
            sib[i - 1].children.link(col)
        else:
            gp = collection_parent(root, parent) if parent != root else None
            if gp is None:
                self.report({'INFO'}, "Already at the top level")
                return {'CANCELLED'}
            parent.children.unlink(col)
            gsib = list(gp.children)
            gsib.insert(gsib.index(parent) + 1, col)
            relink(gp, gsib)
        layer_restore(context, snap, col.name)
        return {'FINISHED'}


class DESSIN_OT_layer_purge(bpy.types.Operator):
    bl_idname = "dessin.layer_purge"
    bl_label = "Delete Empty Layers"
    bl_description = "Deletes the layers that contain no object and no sublayer"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        root = context.scene.collection
        n = 0
        changed = True
        while changed:
            changed = False
            for c in list(bpy.data.collections):
                if not c.objects and not c.children and collection_parent(root, c) is not None:
                    bpy.data.collections.remove(c)
                    n += 1
                    changed = True
        self.report({'INFO'}, f"{n} empty layer(s) deleted")
        return {'FINISHED'}


class DESSIN_OT_layer_new(bpy.types.Operator):
    bl_idname = "dessin.layer_new"
    bl_label = "New Layer"
    bl_description = "Creates a layer (a sublayer of the current one when Sublayer is on)"
    bl_options = {'REGISTER', 'UNDO'}

    layer: bpy.props.StringProperty(options={'SKIP_SAVE', 'HIDDEN'})

    sub: bpy.props.BoolProperty(name="Sublayer", default=False)
    name: bpy.props.StringProperty(name="Name", default="")

    def execute(self, context):
        layer_activate(context, self.layer)
        parent = context.view_layer.active_layer_collection.collection if self.sub else context.scene.collection
        if not self.sub:
            # un calque « frère » du calque courant : même parent
            cur = context.view_layer.active_layer_collection.collection
            parent = collection_parent(context.scene.collection, cur) or context.scene.collection
        col = bpy.data.collections.new(self.name.strip() or new_layer_name())
        parent.children.link(col)
        n = len(bpy.data.collections)
        pg = col.dessin_layer
        pg.color = LAYER_PALETTE[(n - 1) % len(LAYER_PALETTE)]
        pg.use_color = True
        lc = find_layer_collection(context.view_layer.layer_collection, col.name)
        if lc is not None:
            context.view_layer.active_layer_collection = lc
        return {'FINISHED'}


class DESSIN_OT_layer_delete(bpy.types.Operator):
    bl_idname = "dessin.layer_delete"
    bl_label = "Delete Layer"
    bl_description = "Deletes the layer(s). Their objects and sublayers move to the parent layer (nothing is erased)"
    bl_options = {'REGISTER', 'UNDO'}

    layer: bpy.props.StringProperty(options={'SKIP_SAVE', 'HIDDEN'})

    def execute(self, context):
        names = layer_targets(context, self.layer)
        if not names:
            return {'CANCELLED'}
        parent = context.scene.collection
        for n in names:
            col = bpy.data.collections.get(n)
            if col is None:
                continue
            parent = collection_parent(context.scene.collection, col) or context.scene.collection
            for o in list(col.objects):
                if o.name not in parent.objects:
                    parent.objects.link(o)
                col.objects.unlink(o)
                if o.get("wd_lc") and not parent.dessin_layer.use_color:
                    o.color = (1.0, 1.0, 1.0, 1.0)
                    del o["wd_lc"]
            for ch in list(col.children):
                col.children.unlink(ch)
                parent.children.link(ch)
            bpy.data.collections.remove(col)
        _LAYERCOL["sel"] = []
        lc = find_layer_collection(context.view_layer.layer_collection, parent.name) if parent != context.scene.collection else context.view_layer.layer_collection
        if lc is not None:
            context.view_layer.active_layer_collection = lc
        return {'FINISHED'}


class DESSIN_OT_layer_move_selection(bpy.types.Operator):
    bl_idname = "dessin.layer_move_selection"
    bl_label = "Change Object Layer"
    bl_description = "Moves the selected objects into this layer (the current layer does not change)"
    bl_options = {'REGISTER', 'UNDO'}

    layer: bpy.props.StringProperty(options={'SKIP_SAVE', 'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and len(context.selected_objects) > 0

    def execute(self, context):
        target = bpy.data.collections.get(self.layer) if self.layer else None
        if target is None:
            target = context.view_layer.active_layer_collection.collection
        pg = target.dessin_layer
        n = 0
        for o in list(context.selected_objects):
            for c in list(o.users_collection):
                if c != target:
                    c.objects.unlink(o)
            if o.name not in target.objects:
                target.objects.link(o)
            if pg.use_color:
                o.color = (pg.color[0], pg.color[1], pg.color[2], 1.0)
                o["wd_lc"] = 1
            elif o.get("wd_lc"):
                o.color = (1.0, 1.0, 1.0, 1.0)
                del o["wd_lc"]
            n += 1
        self.report({'INFO'}, f"{n} object(s) moved to {target.name if target != context.scene.collection else 'the scene'}")
        return {'FINISHED'}


class DESSIN_OT_layer_select(bpy.types.Operator):
    bl_idname = "dessin.layer_select"
    bl_label = "Select Layer Objects"
    bl_description = "Selects (or deselects) the objects of the layer(s) and their sublayers"
    bl_options = {'REGISTER', 'UNDO'}

    layer: bpy.props.StringProperty(options={'SKIP_SAVE', 'HIDDEN'})
    extend: bpy.props.BoolProperty(name="Add to selection", default=False)
    deselect: bpy.props.BoolProperty(default=False)

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        layer_activate(context, self.layer)
        count = 0
        first = not self.extend
        for n in layer_targets(context, self.layer) or [context.view_layer.active_layer_collection.name]:
            lc = find_layer_collection(context.view_layer.layer_collection, n)
            if lc is None:
                continue
            if self.deselect:
                for o in lc.collection.all_objects:
                    try:
                        o.select_set(False)
                        count += 1
                    except RuntimeError:
                        pass
            else:
                count += layer_select_objects(context, lc.collection, extend=not first)
                first = False
        self.report({'INFO'}, f"{count} object(s) {'deselected' if self.deselect else 'selected'}")
        return {'FINISHED'}


class DESSIN_OT_layer_isolate(bpy.types.Operator):
    bl_idname = "dessin.layer_isolate"
    bl_label = "Isolate Layer"
    bl_description = "Hides every layer except the selected one(s) and their sublayers"
    bl_options = {'REGISTER', 'UNDO'}

    layer: bpy.props.StringProperty(options={'SKIP_SAVE', 'HIDDEN'})

    def execute(self, context):
        layer_activate(context, self.layer)
        keep = set()

        def mark_down(lc):
            keep.add(lc.name)
            for ch in lc.children:
                mark_down(ch)

        names = layer_targets(context, self.layer) or [context.view_layer.active_layer_collection.name]
        for n in names:
            lc = find_layer_collection(context.view_layer.layer_collection, n)
            if lc is None:
                continue
            mark_down(lc)
            up = lc.collection
            while up is not None and up != context.scene.collection:
                keep.add(up.name)
                up = collection_parent(context.scene.collection, up)
        for _d, lc in layer_rows(context):
            if lc != context.view_layer.layer_collection:
                lc.hide_viewport = lc.name not in keep
                if lc.name in keep:
                    lc.exclude = False
        return {'FINISHED'}


class DESSIN_OT_layer_show_all(bpy.types.Operator):
    bl_idname = "dessin.layer_show_all"
    bl_label = "Show All Layers"
    bl_description = "Shows every layer (the lock state is not changed)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        for _d, lc in layer_rows(context):
            lc.hide_viewport = False
            lc.exclude = False
        return {'FINISHED'}


class DESSIN_OT_layer_lock_all(bpy.types.Operator):
    bl_idname = "dessin.layer_lock_all"
    bl_label = "Lock / Unlock Layers"
    bl_description = "Locks every layer except the selected one(s), or unlocks all of them"
    bl_options = {'REGISTER', 'UNDO'}

    layer: bpy.props.StringProperty(options={'SKIP_SAVE', 'HIDDEN'})
    lock: bpy.props.BoolProperty(default=True)

    def execute(self, context):
        layer_activate(context, self.layer)
        keep = set(layer_targets(context, self.layer) or [context.view_layer.active_layer_collection.name])
        for _d, lc in layer_rows(context):
            if lc == context.view_layer.layer_collection:
                continue
            lc.collection.hide_select = (lc.name not in keep) if self.lock else False
        return {'FINISHED'}


class DESSIN_OT_layer_colors_view(bpy.types.Operator):
    bl_idname = "dessin.layer_colors_view"
    bl_label = "Show Layer Colors"
    bl_description = "Switches the 3D views to «Object» color so layer colors show (Solid and Wireframe)"

    def execute(self, context):
        for win in context.window_manager.windows:
            for a in win.screen.areas:
                if a.type == 'VIEW_3D':
                    sh = a.spaces.active.shading
                    try:
                        sh.color_type = 'OBJECT'
                        sh.wireframe_color_type = 'OBJECT'
                    except (AttributeError, TypeError):
                        pass
        return {'FINISHED'}


class DESSIN_OT_layer_refresh_colors(bpy.types.Operator):
    bl_idname = "dessin.layer_refresh_colors"
    bl_label = "Apply Layer Colors"
    bl_description = "Gives every object the color of its layer (after moving objects with Blender's own tools)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        for c in bpy.data.collections:
            layer_apply_color(c)
        for o in bpy.data.objects:
            if len(o.users_collection) and o.users_collection[0] == context.scene.collection and o.get("wd_lc"):
                o.color = (1.0, 1.0, 1.0, 1.0)
                del o["wd_lc"]
        return {'FINISHED'}


def layer_button_menu(self, context):
    """Clic droit sur un calque (nom, couleur, interrupteurs) : les actions sur ce calque (ou sur les calques sélectionnés) s'ajoutent au menu de Blender."""
    p = getattr(context, "button_pointer", None)
    col = None
    if isinstance(p, bpy.types.Collection):
        col = p
    elif isinstance(p, bpy.types.LayerCollection):
        col = p.collection
    else:
        # le nom du calque est un bouton d'opérateur (clic, Maj+clic...) : on retrouve le calque par ses propriétés
        bop = getattr(context, "button_operator", None)
        try:
            if bop is not None and bop.bl_rna.identifier == "DESSIN_OT_layer_click":
                col = bpy.data.collections.get(bop.layer)
        except (AttributeError, ReferenceError):
            col = None
    if col is None or col == context.scene.collection or col.name not in bpy.data.collections:
        return
    lcol = find_layer_collection(context.view_layer.layer_collection, col.name)
    if lcol is None:
        return
    targets = layer_targets(context, col.name)
    lay = self.layout
    lay.separator()
    multi = len(targets) > 1
    lay.label(text=(f"{len(targets)} layers" if multi else "Layer: " + col.name), icon='OUTLINER_COLLECTION')
    if not multi and context.mode == 'OBJECT' and context.selected_objects:
        o_ = lay.operator(DESSIN_OT_layer_move_selection.bl_idname, text="Change Object Layer", icon='EXPORT')
        o_.layer = col.name

    def item(text, idn, icon='NONE', **kw):
        o = lay.operator(idn, text=text, icon=icon)
        if idn == DESSIN_OT_layer_current.bl_idname:
            o.name = col.name
            o.select = False
        else:
            o.layer = col.name
        for k, v in kw.items():
            setattr(o, k, v)
        return o

    def flag(on_text, off_text, what, icon_on, icon_off):
        cur = layer_get_flag(lcol, what)
        item(off_text if cur else on_text, DESSIN_OT_layer_set.bl_idname, icon_off if cur else icon_on,
             what=what, value=not cur)

    item("New Sublayer", DESSIN_OT_layer_new.bl_idname, 'OUTLINER_COLLECTION', sub=True)
    item("Duplicate", DESSIN_OT_layer_duplicate.bl_idname, 'DUPLICATE')
    item("Rename...", DESSIN_OT_layer_rename.bl_idname, 'GREASEPENCIL')
    _LAYERCOL["menu_layer"] = col.name
    item("Pick Up to Move (drop it elsewhere)", DESSIN_OT_layer_carry.bl_idname, 'HAND')
    lay.menu(DESSIN_MT_layer_move_to.bl_idname, text="Move Layer To", icon='FORWARD')
    if lcol.children:
        item("Fold" if not col.dessin_layer.folded else "Unfold", DESSIN_OT_layer_fold.bl_idname, 'TRIA_RIGHT' if not col.dessin_layer.folded else 'TRIA_DOWN')
        item("Unfold All Sublayers", DESSIN_OT_layer_fold.bl_idname, 'TRIA_DOWN', action='EXPAND_CHILDREN')
    lay.separator()
    item("Set as Current Layer", DESSIN_OT_layer_current.bl_idname, 'RADIOBUT_ON')
    item("Select Objects", DESSIN_OT_layer_select.bl_idname, 'RESTRICT_SELECT_OFF')
    item("Add Objects to Selection", DESSIN_OT_layer_select.bl_idname, 'ADD', extend=True)
    item("Deselect Objects", DESSIN_OT_layer_select.bl_idname, 'REMOVE', deselect=True)
    lay.separator()
    item("Isolate", DESSIN_OT_layer_isolate.bl_idname, 'HIDE_OFF')
    lay.operator(DESSIN_OT_layer_show_all.bl_idname, text="Show All Layers", icon='HIDE_OFF')
    flag("Hide", "Show", 'HIDE', 'HIDE_ON', 'HIDE_OFF')
    flag("Exclude from View Layer", "Include in View Layer", 'EXCLUDE', 'CHECKBOX_DEHLT', 'CHECKBOX_HLT')
    flag("Make Selectable", "Make Unselectable (Lock)", 'SELECTABLE', 'RESTRICT_SELECT_OFF', 'RESTRICT_SELECT_ON')
    flag("Disable in Viewports", "Enable in Viewports", 'VIEWPORT', 'RESTRICT_VIEW_ON', 'RESTRICT_VIEW_OFF')
    flag("Disable in Renders", "Enable in Renders", 'RENDER', 'RESTRICT_RENDER_ON', 'RESTRICT_RENDER_OFF')
    lay.separator()
    flag("Set Holdout", "Clear Holdout", 'HOLDOUT', 'HOLDOUT_ON', 'HOLDOUT_OFF')
    flag("Set Indirect Only", "Clear Indirect Only", 'INDIRECT', 'INDIRECT_ONLY_ON', 'INDIRECT_ONLY_OFF')
    lay.separator()
    item("Lock Other Layers", DESSIN_OT_layer_lock_all.bl_idname, 'LOCKED', lock=True)
    o = lay.operator(DESSIN_OT_layer_lock_all.bl_idname, text="Unlock All Layers", icon='UNLOCKED')
    o.lock = False
    lay.separator()
    for d, txt, ic in (('UP', "Move Up", 'TRIA_UP'), ('DOWN', "Move Down", 'TRIA_DOWN'),
                       ('IN', "Move Into the Layer Above", 'TRIA_RIGHT'), ('OUT', "Move Out One Level", 'TRIA_LEFT')):
        item(txt, DESSIN_OT_layer_move.bl_idname, ic, direction=d)
    lay.separator()
    item("Delete Layer (keep contents)", DESSIN_OT_layer_delete.bl_idname, 'TRASH')
    item("Delete Layer and Contents", DESSIN_OT_layer_delete_all.bl_idname, 'X')
    lay.operator(DESSIN_OT_layer_purge.bl_idname, text="Delete Empty Layers", icon='BRUSH_DATA')


def tool_families():
    """[(titre, [classes d'outils])] : les mêmes familles que la barre d'outils, avec Select en tête."""
    from .toolbar import RHINO_TOOLS
    names = [t[0] for t in TOOL_ORDER]

    def between(first, last):
        return names[names.index(first):names.index(last) + 1]

    return [
        ("Select", [DESSIN_TT_selection_boite, DESSIN_TT_selection_rect, DESSIN_TT_selection_cercle, DESSIN_TT_selection_lasso]),
        ("Curves", between(DESSIN_TT_polyligne, DESSIN_TT_arc_3pts) + [DESSIN_TT_project_curve] + RHINO_TOOLS["curves"]),
        ("Transform", between(DESSIN_TT_deplacer, DESSIN_TT_array_polar) + [DESSIN_TT_align, DESSIN_TT_stretch] + RHINO_TOOLS["transform"]),
        ("Modify", [DESSIN_TT_join, DESSIN_TT_explode, DESSIN_TT_trim, DESSIN_TT_cut, DESSIN_TT_divide, DESSIN_TT_overkill,
                    DESSIN_TT_split_face, DESSIN_TT_fillet_c, DESSIN_TT_chamfer_c] + between(DESSIN_TT_bool_union, DESSIN_TT_chamfer)
         + [DESSIN_TT_offset_surface, DESSIN_TT_offset] + RHINO_TOOLS["modify"]),
        ("Surfaces", [DESSIN_TT_plan, DESSIN_TT_srf_corners, DESSIN_TT_planar_srf, DESSIN_TT_edge_srf, DESSIN_TT_patch, DESSIN_TT_extrude_crv, DESSIN_TT_extrude_srf, DESSIN_TT_extrude_path,
                      DESSIN_TT_revolve, DESSIN_TT_rail_revolve, DESSIN_TT_loft, DESSIN_TT_sweep1, DESSIN_TT_sweep2]),
        ("Surface editing", [DESSIN_TT_blend_srf, DESSIN_TT_match_srf, DESSIN_TT_thicken, DESSIN_TT_cap, DESSIN_TT_shell] + RHINO_TOOLS["srf_edit"]),
        ("Solids", between(DESSIN_TT_boite, DESSIN_TT_tore) + RHINO_TOOLS["solids"]),
        ("SubD", between(DESSIN_TT_subd_box, DESSIN_TT_subd_plane)),
        ("Lights and cameras", [DESSIN_TT_light_point, DESSIN_TT_light_spot, DESSIN_TT_light_sun, DESSIN_TT_light_area,
                                DESSIN_TT_camera, DESSIN_TT_camera_target]),
        ("Annotation", [DESSIN_TT_cotation, DESSIN_TT_cotation_chain, DESSIN_TT_cotation_ordinate, DESSIN_TT_cotation_arc, DESSIN_TT_cotation_rayon, DESSIN_TT_cotation_angle, DESSIN_TT_annotation, DESSIN_TT_text, DESSIN_TT_center_mark, DESSIN_TT_cotation_edit, DESSIN_TT_hatch, DESSIN_TT_hatch_region,
                        DESSIN_TT_mesure_aire, DESSIN_TT_dist, DESSIN_TT_id_point, DESSIN_TT_make2d, DESSIN_TT_clip_plane]),
    ]


def tool_short_labels(fams):
    """Libellé court (avant la parenthèse) quand il reste unique, sinon le libellé complet."""
    full = [c.bl_label for _t, cl in fams for c in cl]
    out = {}
    for c in (c for _t, cl in fams for c in cl):
        short = c.bl_label.split(" (")[0]
        out[c.bl_idname] = short if sum(1 for f in full if f.split(" (")[0] == short) == 1 else c.bl_label
    return out


class DESSIN_PT_toolbox(bpy.types.Panel):
    bl_label = "Tools"
    bl_idname = "DESSIN_PT_toolbox"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Wanderer"

    def draw(self, context):
        lay = self.layout
        st = context.scene.dessin
        lay.prop(st, "tool_search", text="", icon='VIEWZOOM', placeholder="Search tools")
        q = st.tool_search.strip().lower()
        fams = tool_families()
        labels = tool_short_labels(fams)
        try:
            cur = context.workspace.tools.from_space_view3d_mode(context.mode).idname
        except (AttributeError, RuntimeError):
            cur = ""
        for i, (title, classes) in enumerate(fams):
            items = [c for c in classes if not q or q in c.bl_label.lower() or q in labels[c.bl_idname].lower()
                     or any(q in al for al in (CMD_ALIASES.get(c.bl_idname.split(".", 1)[-1], "") + " "
                                              + FR_ALIASES.get(c.bl_idname.split(".", 1)[-1], "")).split())]
            if not items:
                continue
            header, body = lay.panel(f"wd_toolbox_{i}", default_closed=False)
            header.label(text=title)
            if body is None:
                continue
            g = body.grid_flow(row_major=True, columns=2, even_columns=True, even_rows=True, align=True)
            for c in items:
                op = g.operator("wm.tool_set_by_id", text=labels[c.bl_idname], depress=(c.bl_idname == cur))
                op.name = c.bl_idname


class DESSIN_PT_layers_filter(bpy.types.Panel):
    bl_label = "Layer List"
    bl_idname = "DESSIN_PT_layers_filter"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'HEADER'

    def draw(self, context):
        lay = self.layout
        st = context.scene.dessin
        lay.label(text="Restriction Toggles")
        r = lay.row(align=True)
        r.prop(st, "layer_col_exclude", text="", icon='CHECKBOX_HLT', toggle=True)
        r.prop(st, "layer_col_select", text="", icon='RESTRICT_SELECT_OFF', toggle=True)
        r.prop(st, "layer_col_hide", text="", icon='HIDE_OFF', toggle=True)
        r.prop(st, "layer_col_viewport", text="", icon='RESTRICT_VIEW_OFF', toggle=True)
        r.prop(st, "layer_col_render", text="", icon='RESTRICT_RENDER_OFF', toggle=True)
        r.prop(st, "layer_col_holdout", text="", icon='HOLDOUT_ON', toggle=True)
        r.prop(st, "layer_col_indirect", text="", icon='INDIRECT_ONLY_ON', toggle=True)
        lay.separator()
        lay.prop(st, "layer_sort_alpha")
        lay.prop(st, "layer_sync_select")
        lay.separator()
        lay.label(text="Search")
        lay.prop(st, "layer_search", text="", icon='VIEWZOOM')
        c = lay.column()
        c.active = bool(st.layer_search)
        c.prop(st, "layer_search_exact")
        c.prop(st, "layer_search_case")
        lay.separator()
        lay.label(text="Filter")
        lay.prop(st, "layer_show_objects", icon='OBJECT_DATA')
        lay.separator()
        lay.label(text="Colors")
        r = lay.row(align=True)
        r.operator(DESSIN_OT_layer_colors_view.bl_idname, icon='COLOR')
        r.operator(DESSIN_OT_layer_refresh_colors.bl_idname, text="", icon='FILE_REFRESH')
        lay.separator()
        r = lay.row(align=True)
        o = r.operator(DESSIN_OT_layer_fold.bl_idname, text="Unfold All", icon='TRIA_DOWN')
        o.action = 'EXPAND_ALL'
        o = r.operator(DESSIN_OT_layer_fold.bl_idname, text="Fold All", icon='TRIA_RIGHT')
        o.action = 'COLLAPSE_ALL'


def layer_name_match(name, st):
    q = st.layer_search
    if not q:
        return True
    if not st.layer_search_case:
        name, q = name.lower(), q.lower()
    return name == q if st.layer_search_exact else q in name


OBJ_ICONS = {'MESH': 'OUTLINER_OB_MESH', 'CURVE': 'OUTLINER_OB_CURVE', 'EMPTY': 'OUTLINER_OB_EMPTY', 'FONT': 'OUTLINER_OB_FONT',
             'SURFACE': 'OUTLINER_OB_SURFACE', 'LIGHT': 'OUTLINER_OB_LIGHT', 'CAMERA': 'OUTLINER_OB_CAMERA'}


class DESSIN_PT_layers(bpy.types.Panel):
    bl_label = "Layers"
    bl_idname = "DESSIN_PT_layers"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Layers"

    def draw_header_preset(self, context):
        st = context.scene.dessin
        self.layout.popover(panel="DESSIN_PT_layers_filter", text="", icon='FILTER' if not st.layer_search else 'VIEWZOOM')

    def draw(self, context):
        lay = self.layout
        vl = context.view_layer
        cur = vl.active_layer_collection
        st = context.scene.dessin
        sel = set(_LAYERCOL["sel"])
        lay.prop(st, "layer_search", text="", icon='VIEWZOOM', placeholder="Search layers")
        carry = _LAYERCOL["carry"]
        if carry and carry in bpy.data.collections:
            cb = lay.box()
            cb.label(text=f"Moving: {carry}", icon='HAND')
            r = cb.row(align=True)
            for md, tx in (('ABOVE', "Above"), ('INSIDE', "Inside"), ('BELOW', "Below")):
                o = r.operator(DESSIN_OT_layer_carry.bl_idname, text=tx, depress=_LAYERCOL["carry_mode"] == md)
                o.mode = md
            cb.label(text="Click the layer where it goes")
            o = cb.operator(DESSIN_OT_layer_carry.bl_idname, text="Cancel", icon='X')
            o.layer = ""
        rows = layer_rows(context)
        visible = None
        if st.layer_search:
            visible = set()
            for d, lc in rows[1:]:
                if layer_name_match(lc.name, st):
                    up = lc
                    visible.add(lc.name)
                    par = collection_parent(vl.layer_collection, lc)
                    while par is not None and par != vl.layer_collection:
                        visible.add(par.name)
                        par = collection_parent(vl.layer_collection, par)
        box = lay.box()
        col = box.column(align=False)
        col.scale_y = 0.95
        n_obj_rows = 0

        def tg(row, owner, prop, icon, live=True, op=None):
            """Même icône dans les deux états ; grisée quand l'option est désactivée."""
            r = row.row(align=True)
            r.active = bool(live)
            if op is not None:
                o_ = r.operator(DESSIN_OT_layer_object.bl_idname, text="", emboss=False, icon=icon)
                o_.name = op.name
                o_.action = 'HIDE'
            else:
                r.prop(owner, prop, text="", emboss=False, icon=icon)

        def toggles(row, lc_or_none, c, obj=None):
            if lc_or_none is not None:
                lc = lc_or_none
                if st.layer_col_exclude:
                    tg(row, lc, "exclude", 'CHECKBOX_HLT', not lc.exclude)
                if st.layer_col_select:
                    tg(row, c, "hide_select", 'RESTRICT_SELECT_OFF', not c.hide_select)
                if st.layer_col_hide:
                    tg(row, lc, "hide_viewport", 'HIDE_OFF', not lc.hide_viewport)
                if st.layer_col_viewport:
                    tg(row, c, "hide_viewport", 'RESTRICT_VIEW_OFF', not c.hide_viewport)
                if st.layer_col_render:
                    tg(row, c, "hide_render", 'RESTRICT_RENDER_OFF', not c.hide_render)
                if st.layer_col_holdout:
                    tg(row, lc, "holdout", 'HOLDOUT_ON', lc.holdout)
                if st.layer_col_indirect:
                    tg(row, lc, "indirect_only", 'INDIRECT_ONLY_ON', lc.indirect_only)
            else:
                if st.layer_col_exclude:
                    row.label(text="", icon='BLANK1')
                if st.layer_col_select:
                    tg(row, obj, "hide_select", 'RESTRICT_SELECT_OFF', not obj.hide_select)
                if st.layer_col_hide:
                    tg(row, None, None, 'HIDE_OFF', not obj.hide_get(), op=obj)
                if st.layer_col_viewport:
                    tg(row, obj, "hide_viewport", 'RESTRICT_VIEW_OFF', not obj.hide_viewport)
                if st.layer_col_render:
                    tg(row, obj, "hide_render", 'RESTRICT_RENDER_OFF', not obj.hide_render)
                if st.layer_col_holdout:
                    row.label(text="", icon='BLANK1')
                if st.layer_col_indirect:
                    row.label(text="", icon='BLANK1')

        sel_cols = set()
        try:
            for o_ in context.selected_objects:
                for c_ in o_.users_collection:
                    sel_cols.add(c_.name)
        except (AttributeError, ReferenceError, RuntimeError):
            pass

        hide_below = None
        for depth, lc in rows:
            c = lc.collection
            is_cur = lc == cur
            if depth > 0 and visible is None:
                if hide_below is not None and depth > hide_below:
                    continue
                hide_below = None
            if depth == 0:
                row = col.row(align=False)
                op = row.operator(DESSIN_OT_layer_current.bl_idname, text="Scene (top level)", emboss=is_cur)
                op.name = lc.name
                op.select = False
                continue
            if visible is not None and lc.name not in visible:
                continue
            row = col.row(align=False)
            if depth > 1:
                row.separator(factor=1.2 * (depth - 1))
            if lc.children:
                fd = c.dessin_layer.folded
                row.prop(c.dessin_layer, "folded", text="", emboss=False, icon='TRIA_RIGHT' if fd else 'TRIA_DOWN')
                if fd and visible is None:
                    hide_below = depth
            else:
                row.label(text="", icon='BLANK1')
            sw = row.row(align=True)
            sw.ui_units_x = 0.8
            sw.prop(c.dessin_layer, "color", text="")
            row.separator(factor=0.3)
            op = row.operator(DESSIN_OT_layer_click.bl_idname, text=c.name,
                              emboss=is_cur or lc.name in sel or c.name in sel_cols, depress=c.name in sel_cols)
            op.layer = lc.name
            toggles(row, lc, c)
            if st.layer_show_objects:
                for o in c.objects:
                    if n_obj_rows >= 300:
                        break
                    n_obj_rows += 1
                    orow = col.row(align=False)
                    orow.separator(factor=1.2 * depth + 0.8)
                    nm = orow.row(align=True)
                    op = nm.operator(DESSIN_OT_layer_object.bl_idname, text=o.name, emboss=o.select_get(),
                                     icon=OBJ_ICONS.get(o.type, 'OBJECT_DATA'))
                    op.name = o.name
                    op.action = 'SELECT'
                    toggles(orow, None, c, o)
        if n_obj_rows >= 300:
            lay.label(text="Showing the first 300 objects", icon='INFO')
        r = lay.row(align=True)
        for d, ic in (('UP', 'TRIA_UP'), ('DOWN', 'TRIA_DOWN'), ('IN', 'TRIA_RIGHT'), ('OUT', 'TRIA_LEFT')):
            o = r.operator(DESSIN_OT_layer_move.bl_idname, text="", icon=ic)
            o.direction = d
        o = r.operator(DESSIN_OT_layer_new.bl_idname, text="New", icon='ADD')
        o.sub = False
        o = r.operator(DESSIN_OT_layer_new.bl_idname, text="Sublayer", icon='OUTLINER_COLLECTION')
        o.sub = True
        r.operator(DESSIN_OT_layer_delete.bl_idname, text="", icon='TRASH')


class DESSIN_PT_layers_states(bpy.types.Panel):
    bl_label = "Layer States"
    bl_idname = "DESSIN_PT_layers_states"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Layers"
    bl_parent_id = "DESSIN_PT_layers"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        lay = self.layout
        st = context.scene.dessin
        r = lay.row(align=True)
        r.prop(st, "layer_state_name", text="", placeholder="State name")
        o = r.operator(DESSIN_OT_layer_state.bl_idname, text="", icon='ADD')
        o.action = 'SAVE'
        for i, it in enumerate(st.layer_states):
            r = lay.row(align=True)
            o = r.operator(DESSIN_OT_layer_state.bl_idname, text=it.name, icon='LOOP_BACK')
            o.action = 'APPLY'
            o.index = i
            o = r.operator(DESSIN_OT_layer_state.bl_idname, text="", icon='FILE_REFRESH')
            o.action = 'UPDATE'
            o.index = i
            o = r.operator(DESSIN_OT_layer_state.bl_idname, text="", icon='X')
            o.action = 'DELETE'
            o.index = i
        if not len(st.layer_states):
            lay.label(text="Save the visibility and locks of all layers, restore them in one click", icon='INFO')


def _late_imports():
    """Noms définis dans des modules chargés après celui-ci : ils ne servent qu'à l'exécution des outils."""
    global CMD_ALIASES, DESSIN_TT_align, DESSIN_TT_annotation, DESSIN_TT_arc_3pts, DESSIN_TT_array_polar
    global DESSIN_TT_blend_srf, DESSIN_TT_boite, DESSIN_TT_bool_union, DESSIN_TT_camera, DESSIN_TT_camera_target
    global DESSIN_TT_cap, DESSIN_TT_center_mark, DESSIN_TT_chamfer, DESSIN_TT_chamfer_c, DESSIN_TT_clip_plane
    global DESSIN_TT_cotation, DESSIN_TT_cotation_angle, DESSIN_TT_cotation_arc, DESSIN_TT_cotation_chain
    global DESSIN_TT_cotation_edit, DESSIN_TT_cotation_ordinate, DESSIN_TT_cotation_rayon, DESSIN_TT_cut
    global DESSIN_TT_deplacer, DESSIN_TT_dist, DESSIN_TT_divide, DESSIN_TT_edge_srf, DESSIN_TT_explode
    global DESSIN_TT_extrude_crv, DESSIN_TT_extrude_path, DESSIN_TT_extrude_srf, DESSIN_TT_fillet_c, DESSIN_TT_hatch
    global DESSIN_TT_hatch_region, DESSIN_TT_id_point, DESSIN_TT_join, DESSIN_TT_light_area, DESSIN_TT_light_point
    global DESSIN_TT_light_spot, DESSIN_TT_light_sun, DESSIN_TT_loft, DESSIN_TT_make2d, DESSIN_TT_match_srf
    global DESSIN_TT_mesure_aire, DESSIN_TT_offset, DESSIN_TT_offset_surface, DESSIN_TT_overkill, DESSIN_TT_patch
    global DESSIN_TT_plan, DESSIN_TT_planar_srf, DESSIN_TT_polyligne, DESSIN_TT_project_curve
    global DESSIN_TT_rail_revolve, DESSIN_TT_revolve, DESSIN_TT_selection_boite, DESSIN_TT_selection_cercle
    global DESSIN_TT_selection_lasso, DESSIN_TT_selection_rect, DESSIN_TT_shell, DESSIN_TT_split_face
    global DESSIN_TT_srf_corners, DESSIN_TT_stretch, DESSIN_TT_subd_box, DESSIN_TT_subd_plane, DESSIN_TT_sweep1
    global DESSIN_TT_sweep2, DESSIN_TT_text, DESSIN_TT_thicken, DESSIN_TT_tore, DESSIN_TT_trim, TOOL_ORDER
    from .toolbar import (
        DESSIN_TT_align, DESSIN_TT_annotation, DESSIN_TT_arc_3pts, DESSIN_TT_array_polar, DESSIN_TT_blend_srf,
    DESSIN_TT_boite, DESSIN_TT_bool_union, DESSIN_TT_camera, DESSIN_TT_camera_target, DESSIN_TT_cap,
    DESSIN_TT_center_mark, DESSIN_TT_chamfer, DESSIN_TT_chamfer_c, DESSIN_TT_clip_plane, DESSIN_TT_cotation,
    DESSIN_TT_cotation_angle, DESSIN_TT_cotation_arc, DESSIN_TT_cotation_chain, DESSIN_TT_cotation_edit,
    DESSIN_TT_cotation_ordinate, DESSIN_TT_cotation_rayon, DESSIN_TT_cut, DESSIN_TT_deplacer, DESSIN_TT_dist,
    DESSIN_TT_divide, DESSIN_TT_edge_srf, DESSIN_TT_explode, DESSIN_TT_extrude_crv, DESSIN_TT_extrude_path,
    DESSIN_TT_extrude_srf, DESSIN_TT_fillet_c, DESSIN_TT_hatch, DESSIN_TT_hatch_region, DESSIN_TT_id_point,
    DESSIN_TT_join, DESSIN_TT_light_area, DESSIN_TT_light_point, DESSIN_TT_light_spot, DESSIN_TT_light_sun,
    DESSIN_TT_loft, DESSIN_TT_make2d, DESSIN_TT_match_srf, DESSIN_TT_mesure_aire, DESSIN_TT_offset,
    DESSIN_TT_offset_surface, DESSIN_TT_overkill, DESSIN_TT_patch, DESSIN_TT_plan, DESSIN_TT_planar_srf,
    DESSIN_TT_polyligne, DESSIN_TT_project_curve, DESSIN_TT_rail_revolve, DESSIN_TT_revolve,
    DESSIN_TT_selection_boite, DESSIN_TT_selection_cercle, DESSIN_TT_selection_lasso, DESSIN_TT_selection_rect,
    DESSIN_TT_shell, DESSIN_TT_split_face, DESSIN_TT_srf_corners, DESSIN_TT_stretch, DESSIN_TT_subd_box,
    DESSIN_TT_subd_plane, DESSIN_TT_sweep1, DESSIN_TT_sweep2, DESSIN_TT_text, DESSIN_TT_thicken, DESSIN_TT_tore,
    DESSIN_TT_trim, TOOL_ORDER,
    )
    from .views import CMD_ALIASES
