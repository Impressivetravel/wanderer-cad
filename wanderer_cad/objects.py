"""Wanderer CAD : Groupes, matériaux, menus contextuels, édition de polylignes."""

import bpy
import json
from mathutils import Matrix, Vector, geometry

from .linetypes import ctx_linetype_item
from .core import LAST_VIEW3D, _LOCAL_VER


# --------------------------------------------------------------------------
# Groupes (empty parent) : Group / Ungroup + sélection du groupe entier au clic
# --------------------------------------------------------------------------

GROUP_KEY = "cad_group"
_GROUP_SEL = {"last": set(), "on": False}


def is_group(obj):
    return obj is not None and obj.type == 'EMPTY' and bool(obj.get(GROUP_KEY))


def group_root(obj, stop=None):
    """Groupe le plus haut contenant (ou étant) obj, ou None. stop : groupe(s) ouvert(s) avec Edit Group (objet, nom ou
    ensemble de noms) : on ne remonte pas jusqu'à eux, c'est le sous-groupe ouvert juste en dessous qui compte."""
    if obj is None:
        return None
    if stop is not None and not isinstance(stop, (set, frozenset)):
        stop = {stop if isinstance(stop, str) else stop.name}
    if stop and obj.name in stop:
        return None
    root = obj if is_group(obj) else None
    p = obj.parent
    while p is not None:
        if stop and p.name in stop:
            break
        if is_group(p):
            root = p
        p = p.parent
    return root


def group_members(root):
    out = [root]
    out.extend(root.children_recursive)
    return out


def group_click(context, hit, mode):
    """Clic sur un objet d'un groupe : tout le groupe suit, tant qu'il n'est pas dégroupé (Rhino).
    mode : 'SET' (clic : le groupe seul), 'ADD_TOGGLE' (Maj : le groupe suit l'état de l'objet cliqué), 'REMOVE' (Ctrl)."""
    try:
        st = context.scene.dessin
        if context.mode != 'OBJECT' or not st.group_select or hit is None:
            return False
        root = group_root(hit, stop=open_group(context))     # groupe ouvert (Edit Group) : ses objets un par un
    except (AttributeError, ReferenceError):
        return False
    if root is None:
        return False
    on = mode == 'SET' or (mode == 'ADD_TOGGLE' and hit.select_get())
    for o in group_members(root):
        try:
            if o.visible_get():
                o.select_set(on)
        except RuntimeError:
            pass
    if on:
        try:
            context.view_layer.objects.active = hit
        except (AttributeError, ReferenceError):
            pass
    _GROUP_SEL["last"] = {o.name for o in context.selected_objects}
    return True


class DESSIN_OT_group(bpy.types.Operator):
    bl_idname = "dessin.group"
    bl_label = "Group"
    bl_description = "Groups the selected objects: they are selected and moved together (Ungroup to release them)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and len(context.selected_objects) >= 1

    def execute(self, context):
        sel = list(context.selected_objects)
        selected = set(sel)
        top = [o for o in sel if o.parent not in selected]
        if len(top) < 2:
            self.report({'WARNING'}, "Select at least two objects to group")
            return {'CANCELLED'}
        pts = []
        for o in top:
            pts += [o.matrix_world @ Vector(c) for c in o.bound_box] if o.type != 'EMPTY' else [o.matrix_world.translation]
        center = sum(pts, Vector()) / len(pts)
        empty = bpy.data.objects.new("Group", None)
        empty.empty_display_type = 'PLAIN_AXES'
        empty.empty_display_size = 0.1
        empty[GROUP_KEY] = True
        empty.location = center
        colls = list(top[0].users_collection) or [context.view_layer.active_layer_collection.collection]
        for c in colls:
            c.objects.link(empty)
        context.view_layer.update()
        for o in top:
            mw = o.matrix_world.copy()
            o.parent = empty
            o.matrix_parent_inverse = Matrix.Identity(4)
            o.matrix_world = mw
        for o in context.view_layer.objects:
            o.select_set(False)
        for o in group_members(empty):
            o.select_set(True)
        context.view_layer.objects.active = empty
        _GROUP_SEL["last"] = {o.name for o in group_members(empty)}
        self.report({'INFO'}, f"Group of {len(top)} objects")
        return {'FINISHED'}


class DESSIN_OT_ungroup(bpy.types.Operator):
    bl_idname = "dessin.ungroup"
    bl_label = "Ungroup"
    bl_description = "Releases the selected group(s): the objects keep their position and become independent"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and any(group_root(o) is not None for o in context.selected_objects)

    def execute(self, context):
        opened = open_groups_all(context)
        cand = {group_root(o, stop=opened or None) for o in context.selected_objects}
        cand.discard(None)
        if not cand:
            self.report({'INFO'}, "This group is open: Close Group first")
            return {'CANCELLED'}
        # un niveau à la fois : on ne dégroupe que les groupes les plus externes parmi ceux choisis
        outer = [g for g in cand if not any(is_group(a) and a in cand for a in _ancestors(g))]
        freed = []
        for g in outer:
            parent = g.parent
            for ch in list(g.children):
                mw = ch.matrix_world.copy()
                ch.parent = parent
                ch.matrix_parent_inverse = parent.matrix_world.inverted() if parent is not None else Matrix.Identity(4)
                ch.matrix_world = mw
                freed.append(ch)
            bpy.data.objects.remove(g)
        context.view_layer.update()
        for o in context.view_layer.objects:
            try:
                o.select_set(False)
            except (RuntimeError, AttributeError):
                pass
        for o in freed:
            o.select_set(True)
        if freed:
            context.view_layer.objects.active = freed[0]
        _GROUP_SEL["last"] = {o.name for o in freed}
        self.report({'INFO'}, f"{len(outer)} group(s) released")
        return {'FINISHED'}


def _ancestors(obj):
    p = obj.parent
    while p is not None:
        yield p
        p = p.parent


def menu_group(self, context):
    if context.mode != 'OBJECT':
        return
    layout = self.layout
    sel = context.selected_objects
    layout.separator()
    if len(sel) >= 2:
        layout.operator(DESSIN_OT_group.bl_idname, icon='GROUP')
    if any(group_root(o) is not None for o in sel):
        layout.operator(DESSIN_OT_ungroup.bl_idname, icon='UGLYPACKAGE')
    layout.separator()


# --------------------------------------------------------------------------
# Edit Group (comme SketchUp) : un groupe s'ouvre dans UNE vue 3D (vue locale de Blender) : le reste du modèle y est
# caché, ses objets se sélectionnent un par un, ce qu'on y dessine entre dans le groupe. Clic droit > Close Group.
# L'état est gardé sur l'écran (Screen), par vue : {indice de la vue : [niveau, ...]} ; un niveau par groupe ouvert.
# --------------------------------------------------------------------------

GE_KEY = "wd_group_edit"


def _lv_set(o, space, state):
    o.local_view_set(space, state)


def _lv_get(o, space):
    return o.local_view_get(space)


def _localview_toggle(context, frame=False):
    return bpy.ops.view3d.localview(frame_selected=frame)


def _ge_data(screen):
    try:
        d = json.loads(screen.get(GE_KEY) or "{}")
        return d if isinstance(d, dict) else {}
    except (ValueError, TypeError, AttributeError):
        return {}


def _ge_save(screen, data):
    data = {k: v for k, v in data.items() if v}
    if data:
        screen[GE_KEY] = json.dumps(data)
    elif GE_KEY in screen.keys():
        del screen[GE_KEY]


def _ge_screens():
    try:
        return [w.screen for w in bpy.context.window_manager.windows]
    except (AttributeError, ReferenceError):
        return []


def _area_key(screen, area):
    try:
        for i, a in enumerate(screen.areas):
            if a == area:
                return str(i)
    except (AttributeError, ReferenceError):
        pass
    return None


def _ctx_screen(context):
    scr = getattr(context, "screen", None)
    return scr if scr is not None else getattr(getattr(context, "window", None), "screen", None)


def group_edit_stack(context, area=None, screen=None):
    """Groupes ouverts dans cette vue 3D, du plus externe au plus interne ([] si aucun, ou si la vue a quitté la vue
    locale autrement)."""
    area = area if area is not None else getattr(context, "area", None)
    screen = screen if screen is not None else _ctx_screen(context)
    try:
        if area is None or screen is None or area.type != 'VIEW_3D' or area.spaces.active.local_view is None:
            return []
    except (AttributeError, ReferenceError):
        return []
    lv = _ge_data(screen).get(_area_key(screen, area)) or []
    return [l for l in lv if isinstance(l, dict) and bpy.data.objects.get(l.get("group", "")) is not None]


def open_group(context, area=None):
    """Groupe ouvert (le plus interne) dans cette vue, ou None."""
    st = group_edit_stack(context, area)
    return bpy.data.objects.get(st[-1]["group"]) if st else None


def open_groups_all(context):
    """Noms des groupes ouverts dans toutes les vues (toutes les fenêtres : marche aussi depuis un minuteur, sans écran)."""
    out = set()
    screens = list(_ge_screens())
    scr = _ctx_screen(context)
    if scr is not None and scr not in screens:
        screens.append(scr)
    for screen in screens:
        try:
            if GE_KEY not in screen.keys():
                continue
            for a in screen.areas:
                for l in group_edit_stack(context, a, screen):
                    out.add(l["group"])
        except (AttributeError, ReferenceError):
            pass
    return out


def group_stop(context):
    """Où s'arrête « le groupe entier » pour cette action : le groupe ouvert dans cette vue (ses objets bougent un par
    un), sinon rien (hors d'une vue : les groupes ouverts dans toutes les vues)."""
    try:
        if getattr(context, "area", None) is not None:
            return open_group(context)
        return open_groups_all(context) or None
    except (AttributeError, ReferenceError):
        return None


def editable_group(context):
    """Groupe à ouvrir d'après l'objet actif / sélectionné (sous le groupe déjà ouvert dans cette vue), ou None."""
    top = open_group(context)
    vl = context.view_layer
    cands = [vl.objects.active] + list(context.selected_objects)
    for o in cands:
        try:
            if o is not None and o.select_get():
                g = group_root(o, stop=top)
                if g is not None and g != top:
                    return g
        except (ReferenceError, RuntimeError):
            pass
    return None


def _set_local(space, view_layer, names):
    for o in view_layer.objects:
        try:
            _lv_set(o, space, o.name in names)
        except (RuntimeError, ReferenceError, TypeError):
            pass
    _LOCAL_VER[0] += 1


def _deselect_all(view_layer):
    for o in view_layer.objects:
        try:
            o.select_set(False)
        except RuntimeError:
            pass


def _redraw(context):
    try:
        for a in context.screen.areas:
            a.tag_redraw()
    except (AttributeError, ReferenceError):
        pass


class DESSIN_OT_group_edit(bpy.types.Operator):
    bl_idname = "dessin.group_edit"
    bl_label = "Edit Group"
    bl_description = ("Opens the group to work inside it, in this view only: the rest of the model is hidden in this view, "
                      "the objects of the group are selected and moved one by one (a group inside it stays whole) and what "
                      "you draw joins the group. Right-click > Close Group to finish")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        try:
            return (context.mode == 'OBJECT' and context.area is not None and context.area.type == 'VIEW_3D'
                    and editable_group(context) is not None)
        except (AttributeError, ReferenceError):
            return False

    def execute(self, context):
        g = editable_group(context)
        if g is None:
            self.report({'INFO'}, "Select an object of a group first")
            return {'CANCELLED'}
        area, screen, vl = context.area, _ctx_screen(context), context.view_layer
        space = area.spaces.active
        stack = group_edit_stack(context)
        if stack:                       # ce qui a été dessiné dans le groupe ouvert y entre avant de descendre d'un niveau
            _adopt_new(stack[-1], space, vl)
        members = {o.name for o in group_members(g)}
        level = {"group": g.name, "before": [o.name for o in vl.objects]}
        if not stack:
            if space.local_view is None:
                level["prev_local"] = None
                keep = [o for o in vl.objects if o.select_get()]
                act = vl.objects.active
                _deselect_all(vl)
                for o in group_members(g):
                    try:
                        if o.visible_get():
                            o.select_set(True)
                    except RuntimeError:
                        pass
                try:
                    _localview_toggle(context)
                except RuntimeError:
                    pass
                if space.local_view is None:
                    _deselect_all(vl)
                    for o in keep:
                        o.select_set(True)
                    vl.objects.active = act
                    self.report({'WARNING'}, "This view could not open the group (nothing of it is visible here)")
                    return {'CANCELLED'}
            else:                       # déjà en vue locale (touche /) : on la retrouvera en fermant
                level["prev_local"] = [o.name for o in vl.objects if _safe_lv_get(o, space)]
        _set_local(space, vl, members)
        data = _ge_data(screen)
        key = _area_key(screen, area)
        data[key] = [l for l in (data.get(key) or []) if l in stack] + [level]
        _ge_save(screen, data)
        _deselect_all(vl)
        _GROUP_SEL["last"] = set()
        _redraw(context)
        self.report({'INFO'}, f"Editing group {g.name}: right-click > Close Group when done")
        return {'FINISHED'}


def _safe_lv_get(o, space):
    try:
        return bool(_lv_get(o, space))
    except (RuntimeError, ReferenceError, TypeError):
        return False


def _adopt_new(level, space, vl):
    """Objets dessinés pendant l'édition de ce niveau (absents à l'ouverture, visibles dans la vue) : ils entrent dans
    le groupe, sans bouger. Renvoie (noms des nouveaux objets, nombre rattachés)."""
    g = bpy.data.objects.get(level.get("group", ""))
    before = set(level.get("before") or ())
    new = [o for o in vl.objects if o.name not in before and o != g and _safe_lv_get(o, space)]
    newn = {o.name for o in new}
    joined = 0
    if g is None:
        return newn, 0
    vl.update()
    for o in new:
        if any(a == g for a in _ancestors(o)):
            continue
        if o.parent is not None and o.parent.name in newn:
            continue                    # suit son parent, lui-même nouveau
        mw = o.matrix_world.copy()
        o.parent = g
        o.matrix_parent_inverse = Matrix.Identity(4)
        o.matrix_world = mw
        joined += 1
    return newn, joined


def _exit_local_view(context, space):
    """Quitte la vue locale sans que la vue ne revienne là où elle était à l'ouverture du groupe."""
    rv = space.region_3d
    keep = None
    try:
        keep = (rv.view_location.copy(), rv.view_rotation.copy(), rv.view_distance, rv.view_perspective,
                rv.view_camera_zoom, tuple(rv.view_camera_offset))
    except (AttributeError, ReferenceError):
        pass
    pv = getattr(getattr(context, "preferences", None), "view", None)
    smooth = getattr(pv, "smooth_view", None)
    try:
        if smooth:
            pv.smooth_view = 0
        _localview_toggle(context)
    except RuntimeError:
        pass
    finally:
        if smooth:
            pv.smooth_view = smooth
    if keep is not None:
        try:
            (rv.view_location, rv.view_rotation, rv.view_distance, rv.view_perspective,
             rv.view_camera_zoom, rv.view_camera_offset) = keep
        except (AttributeError, ReferenceError, TypeError, ValueError):
            pass


class DESSIN_OT_group_close(bpy.types.Operator):
    bl_idname = "dessin.group_close"
    bl_label = "Close Group"
    bl_description = "Closes the group open in this view: the rest of the model comes back and the group is selected again"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return bool(group_edit_stack(context))

    def execute(self, context):
        area, screen, vl = context.area, _ctx_screen(context), context.view_layer
        space = area.spaces.active
        stack = group_edit_stack(context)
        if not stack:
            return {'CANCELLED'}
        level = stack.pop()
        g = bpy.data.objects.get(level["group"])
        newn, joined = _adopt_new(level, space, vl)
        data = _ge_data(screen)
        key = _area_key(screen, area)
        data[key] = stack
        _ge_save(screen, data)
        if stack:                       # retour au groupe ouvert au-dessus
            outer = bpy.data.objects.get(stack[-1]["group"])
            _set_local(space, vl, {o.name for o in group_members(outer)} if outer is not None else set())
        elif level.get("prev_local") is not None:
            _set_local(space, vl, set(level["prev_local"]) | newn)
        else:
            _set_local(space, vl, {o.name for o in vl.objects})
            _exit_local_view(context, space)
        _deselect_all(vl)
        if g is not None:
            for o in group_members(g):
                try:
                    if o.visible_get():
                        o.select_set(True)
                except RuntimeError:
                    pass
            vl.objects.active = g
        _GROUP_SEL["last"] = {o.name for o in context.selected_objects}
        _redraw(context)
        self.report({'INFO'}, f"Group {level['group']} closed" + (f" ({joined} new object(s) added)" if joined else ""))
        return {'FINISHED'}


_GE_SEEN = {"n": -1}


def group_edit_depsgraph(scene, depsgraph=None):
    """Objets créés pendant Edit Group (commandes de Wanderer, qui ne passent pas par les opérateurs de Blender) :
    ils apparaissent dans la vue du groupe ouvert où l'on travaille."""
    try:
        vl = bpy.context.view_layer
        n = len(vl.objects)
        if n == _GE_SEEN["n"]:
            return
        _GE_SEEN["n"] = n
        for scr in _ge_screens():
            if GE_KEY not in scr.keys():
                continue
            data = _ge_data(scr)
            for a in scr.areas:
                if a.type != 'VIEW_3D' or a.as_pointer() != LAST_VIEW3D[0]:
                    continue
                st = data.get(_area_key(scr, a)) or []
                sp = a.spaces.active
                if not st or sp.local_view is None:
                    continue
                known = set(st[-1].get("before") or ())
                for o in vl.objects:
                    if o.name not in known and not _safe_lv_get(o, sp):
                        try:
                            _lv_set(o, sp, True)
                        except (RuntimeError, ReferenceError, TypeError):
                            pass
                a.tag_redraw()
    except (AttributeError, ReferenceError, RuntimeError):
        pass


def _ge_banner():
    """Bandeau en haut de la vue où un groupe est ouvert."""
    try:
        ctx = bpy.context
        st = group_edit_stack(ctx, ctx.area)
        if not st:
            return
        import blf
        reg = ctx.region
        ui = ctx.preferences.system.ui_scale
        names = " > ".join(l["group"] for l in st)
        txt = f"Editing group: {names}     (right-click > Close Group)"
        fid = 0
        blf.size(fid, 11 * ui)
        w, h = blf.dimensions(fid, txt)
        x = (reg.width - w) / 2
        y = reg.height - 70 * ui
        blf.enable(fid, blf.SHADOW)
        blf.shadow(fid, 3, 0.0, 0.0, 0.0, 0.8)
        blf.color(fid, 1.0, 1.0, 1.0, 0.9)
        blf.position(fid, x, y, 0)
        blf.draw(fid, txt)
        blf.disable(fid, blf.SHADOW)
    except (AttributeError, ReferenceError, RuntimeError, ValueError):
        pass


_GE_HANDLES = []


def register_group_edit():
    if not _GE_HANDLES:
        _GE_HANDLES.append(bpy.types.SpaceView3D.draw_handler_add(_ge_banner, (), 'WINDOW', 'POST_PIXEL'))
    if group_edit_depsgraph not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(group_edit_depsgraph)


def unregister_group_edit():
    while _GE_HANDLES:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(_GE_HANDLES.pop(), 'WINDOW')
        except (ValueError, RuntimeError):
            pass
    if group_edit_depsgraph in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(group_edit_depsgraph)


def menu_group_edit(layout, context):
    """En haut du menu du clic droit : Close Group (un groupe est ouvert dans cette vue) / Edit Group. True si dessiné."""
    done = False
    try:
        if group_edit_stack(context):
            layout.operator(DESSIN_OT_group_close.bl_idname, icon='LOOP_BACK')
            done = True
        if editable_group(context) is not None:
            layout.operator(DESSIN_OT_group_edit.bl_idname, icon='GROUP')
            done = True
    except (AttributeError, ReferenceError):
        pass
    return done


class DESSIN_OT_material_remove_all(bpy.types.Operator):
    bl_idname = "dessin.material_remove_all"
    bl_label = "Remove All Materials"
    bl_description = "Removes every material slot from the selected objects"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return any(getattr(o, "material_slots", None) is not None and o.type in {'MESH', 'CURVE', 'SURFACE', 'FONT', 'META'}
                   for o in context.selected_objects)

    def execute(self, context):
        n = 0
        done = set()
        for o in context.selected_objects:
            if o.type not in {'MESH', 'CURVE', 'SURFACE', 'FONT'} or o.data is None or o.data.as_pointer() in done:
                continue
            done.add(o.data.as_pointer())
            n += len(o.data.materials)
            o.data.materials.clear()
        self.report({'INFO'}, "%d material slot(s) removed" % n)
        return {'FINISHED'}


class DESSIN_MT_ctx_material(bpy.types.Menu):
    bl_idname = "DESSIN_MT_ctx_material"
    bl_label = "Material"

    def draw(self, context):
        layout = self.layout
        layout.operator("object.material_slot_copy", text="Copy Material to Selected", icon='COPYDOWN')
        layout.separator()
        layout.operator("material.copy", text="Copy Material", icon='COPYDOWN')
        layout.operator("material.paste", text="Paste Material", icon='PASTEDOWN')
        layout.separator()
        layout.operator("object.material_slot_remove_unused", text="Remove Unused Slots", icon='X')
        layout.operator(DESSIN_OT_material_remove_all.bl_idname, text="Remove All Materials", icon='TRASH')


DISPLAY_AS_ITEMS = (('BOUNDS', "Bounds", "Show only the bounding box"), ('WIRE', "Wire", "Show the object as a wireframe"),
                    ('SOLID', "Solid", "Show the object as a solid, without its textures"),
                    ('TEXTURED', "Textured", "Show the object with its textures (Blender default)"))


class DESSIN_OT_display_as(bpy.types.Operator):
    bl_idname = "dessin.display_as"
    bl_label = "Display As"
    bl_description = "How the selected objects are shown in the viewport (Object properties > Viewport Display > Display As)"
    bl_options = {'REGISTER', 'UNDO'}

    type: bpy.props.EnumProperty(name="Display As", items=DISPLAY_AS_ITEMS, default='TEXTURED')

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and bool(context.selected_objects)

    def execute(self, context):
        for o in context.selected_objects:
            if o.get("cad_clip"):
                continue            # plan de coupe : toujours en filaire, devant (son affichage ne se change pas)
            o.display_type = self.type
        return {'FINISHED'}


class DESSIN_MT_ctx_display(bpy.types.Menu):
    bl_idname = "DESSIN_MT_ctx_display"
    bl_label = "Display As"

    def draw(self, context):
        layout = self.layout
        sel = context.selected_objects
        ref = context.active_object if context.active_object in sel else (sel[0] if sel else None)
        current = ref.display_type if ref is not None else None
        for ident, name, _desc in DISPLAY_AS_ITEMS:       # un point devant l'affichage en cours de l'objet actif
            layout.operator(DESSIN_OT_display_as.bl_idname, text=name,
                            icon='LAYER_ACTIVE' if ident == current else 'BLANK1').type = ident


class DESSIN_MT_ctx_select(bpy.types.Menu):
    bl_idname = "DESSIN_MT_ctx_select"
    bl_label = "Select"

    def draw(self, context):
        layout = self.layout
        if context.mode == 'EDIT_MESH':
            layout.operator("mesh.select_linked", text="Linked", icon='LINKED')
            layout.operator("mesh.select_linked_pick", text="Linked Under Cursor").deselect = False
            layout.separator()
            layout.operator("object.material_slot_select", text="Select Material Slot")
            layout.operator("object.material_slot_deselect", text="Deselect Material Slot")
            layout.separator()
            layout.operator("mesh.select_similar", text="Similar...")
            layout.operator("mesh.select_all", text="Invert Selection").action = 'INVERT'
            return
        layout.operator("object.select_linked", text="Same Material").type = 'MATERIAL'
        layout.operator("object.select_linked", text="Same Object Data (instances)").type = 'OBDATA'
        layout.operator("object.select_linked", text="Same Collection Instance").type = 'DUPGROUP'
        layout.separator()
        layout.operator("object.select_grouped", text="Same Type").type = 'TYPE'
        layout.operator("object.select_grouped", text="Same Collection").type = 'COLLECTION'
        layout.operator("object.select_grouped", text="Same Parent").type = 'SIBLINGS'
        layout.operator("object.select_grouped", text="Children").type = 'CHILDREN_RECURSIVE'
        layout.operator("object.select_grouped", text="Parent").type = 'PARENT'
        layout.separator()
        layout.operator("object.select_all", text="Invert Selection").action = 'INVERT'


class DESSIN_OT_track_to(bpy.types.Operator):
    bl_idname = "dessin.track_to"
    bl_label = "Track To"
    bl_description = ("Makes the selected cameras and lights aim at the active object (Track To constraint: -Z towards the target, Y up). "
                      "Select the camera(s) first, then the target last (it stays active)")
    bl_options = {'REGISTER', 'UNDO'}

    clear: bpy.props.BoolProperty(name="Clear", default=False, options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and bool(context.selected_objects)

    def execute(self, context):
        act = context.active_object
        if self.clear:
            n = 0
            for o in context.selected_objects:
                for c in [c for c in o.constraints if c.type == 'TRACK_TO']:
                    o.constraints.remove(c)
                    n += 1
            self.report({'INFO'}, f"{n} Track To constraint(s) removed")
            return {'FINISHED'}
        others = [o for o in context.selected_objects if o is not act]
        if act is None or not others:
            self.report({'WARNING'}, "Select the camera first, then the target last (Shift+click) so it is the active object")
            return {'CANCELLED'}
        for o in others:
            for c in [c for c in o.constraints if c.type == 'TRACK_TO']:
                o.constraints.remove(c)
            c = o.constraints.new('TRACK_TO')
            c.target = act
            c.track_axis = 'TRACK_NEGATIVE_Z'
            c.up_axis = 'UP_Y'
        self.report({'INFO'}, f"{len(others)} object(s) now track {act.name}")
        return {'FINISHED'}


POLY_EDIT_ACTIONS = (
    ('CLOSE', "Close", "Closes the polyline: the last point joins the first"),
    ('OPEN', "Open", "Opens a closed polyline"),
    ('REVERSE', "Reverse", "Reverses the direction of the polyline"),
    ('CURVE_FIT', "Curve Fit", "Smooth curve passing through every vertex"),
    ('SPLINE_FIT', "Spline Fit", "Smooth spline that follows the vertices (they become control points)"),
    ('DECURVE', "Decurve", "Back to straight segments between the vertices"),
    ('WIDTH', "Width", "Gives the polyline a thickness"),
)


def _spline_points(sp):
    if sp.type == 'BEZIER':
        return [bp.co.copy() for bp in sp.bezier_points]
    return [Vector(p.co[:3]) for p in sp.points]


def _rebuild_spline(cu, kind, pts, closed):
    """Crée dans `cu` une spline POLY / BEZIER (poignées automatiques) / NURBS passant par ou contrôlée par `pts`."""
    if kind == 'BEZIER':
        sp = cu.splines.new('BEZIER')
        sp.bezier_points.add(len(pts) - 1)
        for bp, q in zip(sp.bezier_points, pts):
            bp.co = q
            bp.handle_left_type = bp.handle_right_type = 'AUTO'
    else:
        sp = cu.splines.new(kind)
        sp.points.add(len(pts) - 1)
        for sp_pt, q in zip(sp.points, pts):
            sp_pt.co = (q.x, q.y, q.z, 1.0)
        if kind == 'NURBS':
            sp.order_u = max(2, min(4, len(pts)))
            sp.use_endpoint_u = not closed
    sp.use_cyclic_u = closed
    sp.resolution_u = 12


def _act_invoke(op):
    def run(context):
        mod, name = op.split(".")
        getattr(getattr(bpy.ops, mod), name)('INVOKE_DEFAULT')
        return ""
    return run


class DESSIN_OT_poly_edit(bpy.types.Operator):
    bl_idname = "dessin.poly_edit"
    bl_label = "Edit Polyline"
    bl_options = {'REGISTER', 'UNDO'}

    action: bpy.props.EnumProperty(name="Action", items=[(a, n, d) for a, n, d in POLY_EDIT_ACTIONS], default='CLOSE')
    width: bpy.props.FloatProperty(name="Width", default=0.05, min=0.0, soft_max=1.0, unit='LENGTH')

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and any(o.type == 'CURVE' for o in context.selected_objects)

    def invoke(self, context, event):
        if self.action == 'WIDTH':
            return context.window_manager.invoke_props_dialog(self)
        return self.execute(context)

    def draw(self, context):
        if self.action == 'WIDTH':
            self.layout.prop(self, "width")

    def execute(self, context):
        done = 0
        for obj in context.selected_objects:
            if obj.type != 'CURVE':
                continue
            cu = obj.data
            a = self.action
            if a == 'WIDTH':
                cu.bevel_depth = self.width / 2.0
                cu.bevel_resolution = 2
                done += 1
                continue
            if a in {'CLOSE', 'OPEN'}:
                for sp in cu.splines:
                    sp.use_cyclic_u = (a == 'CLOSE')
            elif a == 'REVERSE':
                for sp in cu.splines:
                    if sp.type == 'BEZIER':
                        data = [(bp.co.copy(), bp.handle_left.copy(), bp.handle_right.copy(), bp.handle_left_type, bp.handle_right_type)
                                for bp in sp.bezier_points]
                        for bp, (c, hl, hr, tl, tr) in zip(sp.bezier_points, reversed(data)):
                            bp.handle_left_type = bp.handle_right_type = 'FREE'
                            bp.co = c
                            bp.handle_left, bp.handle_right = hr, hl
                            bp.handle_left_type, bp.handle_right_type = tr, tl
                    else:
                        co = [tuple(p.co) for p in sp.points]
                        for p, c in zip(sp.points, reversed(co)):
                            p.co = c
            else:       # CURVE_FIT / SPLINE_FIT / DECURVE : on reconstruit les splines
                kind = {'CURVE_FIT': 'BEZIER', 'SPLINE_FIT': 'NURBS', 'DECURVE': 'POLY'}[a]
                old = [(_spline_points(sp), sp.use_cyclic_u) for sp in cu.splines]
                cu.splines.clear()
                for pts, closed in old:
                    if len(pts) >= 2:
                        _rebuild_spline(cu, kind, pts, closed)
            done += 1
        return {'FINISHED'} if done else {'CANCELLED'}


class DESSIN_MT_ctx_polyline(bpy.types.Menu):
    bl_idname = "DESSIN_MT_ctx_polyline"
    bl_label = "Polyline"

    def draw(self, context):
        layout = self.layout
        layout.operator("object.editmode_toggle", text="Edit Polyline", icon='EDITMODE_HLT')
        layout.separator()
        layout.operator(DESSIN_OT_poly_edit.bl_idname, text="Close").action = 'CLOSE'
        layout.operator(DESSIN_OT_poly_edit.bl_idname, text="Open").action = 'OPEN'
        layout.separator()
        layout.operator(DESSIN_OT_join.bl_idname, text="Join")
        layout.operator(DESSIN_OT_poly_edit.bl_idname, text="Reverse").action = 'REVERSE'
        layout.operator(DESSIN_OT_poly_edit.bl_idname, text="Width").action = 'WIDTH'
        layout.separator()
        layout.operator(DESSIN_OT_poly_edit.bl_idname, text="Curve Fit").action = 'CURVE_FIT'
        layout.operator(DESSIN_OT_poly_edit.bl_idname, text="Spline Fit").action = 'SPLINE_FIT'
        layout.operator(DESSIN_OT_poly_edit.bl_idname, text="Decurve").action = 'DECURVE'


# ---- Lock / Unlock All / Unlock Selected (Rhino ; Freeze / Unfreeze dans 3ds Max) ----
# Un objet verrouillé reste visible et accrochable, mais ne se sélectionne plus (ni clic, ni fenêtre) et n'est jamais
# modifié par les commandes (Trim, Split...). Seuls les objets verrouillés par Lock portent la marque : les verrous posés
# par Wanderer lui-même (cadres de mise en page...) ne sont jamais levés par Unlock All.
LOCK_KEY = "cad_locked"


def locked_objects(context):
    try:
        return [o for o in context.scene.objects if o.get(LOCK_KEY)]
    except (AttributeError, ReferenceError):
        return []


def object_lock(o, on):
    try:
        if on:
            o.select_set(False)
            o.hide_select = True
            o[LOCK_KEY] = 1
        else:
            o.hide_select = False
            if LOCK_KEY in o:
                del o[LOCK_KEY]
    except (RuntimeError, ReferenceError, AttributeError):
        pass


# ---- Hide / Isolate / Unisolate / Show (comme Rhino) ----
# Isolate note les objets qu'il masque (propriété ISO_KEY, avec le nom du calque de vue) : Unisolate ne réaffiche
# qu'eux, et pas ceux masqués avant avec Hide. Show réaffiche tout.
ISO_KEY = "wd_isolated"


def isolated_objects(context, hidden_only=True):
    """Objets masqués par Isolate dans ce calque de vue (et toujours masqués)."""
    try:
        vl = context.view_layer
        out = []
        for o in vl.objects:
            if o.get(ISO_KEY) != vl.name:
                continue
            if hidden_only and not o.hide_get(view_layer=vl):
                continue
            out.append(o)
        return out
    except (AttributeError, ReferenceError, RuntimeError):
        return []


def _unmark(o):
    try:
        if ISO_KEY in o:
            del o[ISO_KEY]
    except (ReferenceError, RuntimeError, TypeError):
        pass


class DESSIN_OT_isolate(bpy.types.Operator):
    bl_idname = "dessin.isolate"
    bl_label = "Isolate"
    bl_description = ("Like Isolate in Rhino: hides everything except the selected objects. Unisolate shows back only "
                      "what Isolate hid (objects hidden before with Hide stay hidden); Show shows everything")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and bool(context.selected_objects)

    def execute(self, context):
        vl = context.view_layer
        keep = set(context.selected_objects)
        n = 0
        for o in vl.objects:
            try:
                if o.get(ISO_KEY) and not o.hide_get(view_layer=vl):
                    _unmark(o)                   # marque d'un ancien Isolate sur un objet réaffiché autrement
                if o in keep or o.hide_get(view_layer=vl) or not o.visible_get(view_layer=vl):
                    continue
                o.hide_set(True, view_layer=vl)
                o[ISO_KEY] = vl.name
                n += 1
            except (RuntimeError, ReferenceError):
                continue
        self.report({'INFO'}, f"{n} object(s) hidden: Unisolate shows them back")
        return {'FINISHED'}


class DESSIN_OT_unisolate(bpy.types.Operator):
    bl_idname = "dessin.unisolate"
    bl_label = "Unisolate"
    bl_description = ("Like Unisolate in Rhino: shows the objects hidden by Isolate. Objects hidden with Hide before "
                      "stay hidden (Show shows everything)")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and bool(isolated_objects(context))

    def execute(self, context):
        vl = context.view_layer
        objs = isolated_objects(context)
        for o in objs:
            try:
                o.hide_set(False, view_layer=vl)
            except (RuntimeError, ReferenceError):
                pass
            _unmark(o)
        self.report({'INFO'}, f"{len(objs)} object(s) shown")
        return {'FINISHED'}


class DESSIN_OT_show(bpy.types.Operator):
    bl_idname = "dessin.show"
    bl_label = "Show"
    bl_description = ("Like Show in Rhino: shows every hidden object, whether it was hidden with Hide or by Isolate "
                      "(Unisolate shows only what Isolate hid)")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        vl = context.view_layer
        n = 0
        for o in vl.objects:
            try:
                if o.hide_get(view_layer=vl):
                    o.hide_set(False, view_layer=vl)
                    n += 1
            except (RuntimeError, ReferenceError):
                pass
            _unmark(o)
        self.report({'INFO'}, f"{n} object(s) shown")
        return {'FINISHED'}


class DESSIN_OT_hide(bpy.types.Operator):
    bl_idname = "dessin.hide"
    bl_label = "Hide"
    bl_description = "Like Hide in Rhino: hides the selected objects (Show shows them back; Unisolate does not)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and bool(context.selected_objects)

    def execute(self, context):
        vl = context.view_layer
        objs = list(context.selected_objects)
        for o in objs:
            try:
                o.hide_set(True, view_layer=vl)
            except (RuntimeError, ReferenceError):
                pass
            _unmark(o)                           # masqué par Hide : Unisolate ne le réaffiche pas
        self.report({'INFO'}, f"{len(objs)} object(s) hidden")
        return {'FINISHED'}


class DESSIN_OT_lock(bpy.types.Operator):
    bl_idname = "dessin.lock"
    bl_label = "Lock"
    bl_description = ("Lock the selected objects, like Rhino (Freeze in 3ds Max): they stay visible and you can still snap to "
                      "them, but they can no longer be selected or changed. Unlock All or Unlock Selected to free them")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and bool(context.selected_objects)

    def execute(self, context):
        objs = list(context.selected_objects)
        for o in objs:
            object_lock(o, True)
        self.report({'INFO'}, f"{len(objs)} object(s) locked")
        return {'FINISHED'}


class DESSIN_OT_unlock_all(bpy.types.Operator):
    bl_idname = "dessin.unlock_all"
    bl_label = "Unlock All"
    bl_description = "Unlock every locked object (Unfreeze All in 3ds Max); they become selected"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and bool(locked_objects(context))

    def execute(self, context):
        objs = locked_objects(context)
        for o in context.selected_objects:
            o.select_set(False)
        for o in objs:
            object_lock(o, False)
            try:
                o.select_set(True)
            except RuntimeError:
                pass
        self.report({'INFO'}, f"{len(objs)} object(s) unlocked")
        return {'FINISHED'}


class DESSIN_OT_unlock_selected(bpy.types.Operator):
    """Les objets verrouillés redeviennent cliquables le temps de la commande : on choisit ceux à libérer, Entrée valide."""
    bl_idname = "dessin.unlock_selected"
    bl_label = "Unlock Selected"
    bl_description = "Click the locked objects you want to unlock, then Enter (Esc: cancel). The others stay locked"
    bl_options = {'REGISTER', 'UNDO'}

    PROMPT = "Select locked objects to unlock   |   Enter: unlock them   Esc: cancel"

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and bool(locked_objects(context))

    def invoke(self, context, event):
        self.cands = [o.name for o in locked_objects(context)]
        if not self.cands or context.area is None:
            return {'CANCELLED'}
        self.area = context.area
        self.before = [o.name for o in context.selected_objects]
        self.active = context.view_layer.objects.active.name if context.view_layer.objects.active else None
        for o in context.selected_objects:
            o.select_set(False)
        for o in self.objs():
            o.hide_select = False            # cliquables le temps de la commande (la marque reste)
        self.prompt(self.PROMPT)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def objs(self):
        return [o for o in (bpy.data.objects.get(n) for n in self.cands) if o is not None]

    def prompt(self, txt):
        from .cplane import set_prompt
        try:
            set_prompt(self.area, txt)
            self.area.tag_redraw()
        except (AttributeError, ReferenceError):
            pass

    def end(self, context, keep):
        """keep : objets libérés ; les autres reprennent leur verrou."""
        for o in self.objs():
            if o in keep:
                object_lock(o, False)
            else:
                object_lock(o, True)
        self.prompt(None)

    def modal(self, context, event):
        et = event.type
        if event.value == 'PRESS' and et == 'ESC':
            self.end(context, ())
            for n in self.before:
                o = bpy.data.objects.get(n)
                if o is not None:
                    try:
                        o.select_set(True)
                    except RuntimeError:
                        pass
            return {'CANCELLED'}
        if event.value == 'PRESS' and et in {'RET', 'NUMPAD_ENTER', 'SPACE'}:
            picked = [o for o in self.objs() if o.select_get()]
            self.end(context, picked)
            for o in picked:
                o.select_set(True)
            if picked:
                context.view_layer.objects.active = picked[-1]
            self.report({'INFO'}, f"{len(picked)} object(s) unlocked")
            return {'FINISHED'}
        if et == 'LEFTMOUSE' and event.value == 'PRESS':
            from .drawing import find_window_region
            region = find_window_region(self.area, event.mouse_x, event.mouse_y)
            if region is None:
                return {'PASS_THROUGH'}
            from .selection import pick_object_at
            hit = pick_object_at(context, self.area, region, event.mouse_x - region.x, event.mouse_y - region.y)
            obj = hit[0] if hit else None
            if obj is not None and obj.name in self.cands:
                obj.select_set(not obj.select_get())        # un deuxième clic le retire du choix
                self.area.tag_redraw()
            return {'RUNNING_MODAL'}
        return {'PASS_THROUGH'}       # navigation, molette...


def ctx_extra_items(layout, context):
    # ordre : Select, Display As, Material, puis Lock / Unlock
    layout.menu(DESSIN_MT_ctx_select.bl_idname, icon='RESTRICT_SELECT_OFF')
    if context.mode == 'OBJECT' and any(o.type in {'CAMERA', 'LIGHT'} for o in context.selected_objects):
        layout.operator(DESSIN_OT_track_to.bl_idname, text="Track To (aim at active object)", icon='TRACKER')
        layout.operator(DESSIN_OT_track_to.bl_idname, text="Clear Track To", icon='X').clear = True
    if context.mode == 'OBJECT':
        if context.selected_objects and not any(o.get("cad_clip") for o in context.selected_objects):
            # Display As : Bounds / Wire / Solid / Textured (pas sur un plan de coupe : son affichage est fixé)
            layout.menu(DESSIN_MT_ctx_display.bl_idname, icon='SHADING_WIRE')
        ctx_linetype_item(layout, context)            # Linetype : courbes et lignes de la sélection
        layout.menu(DESSIN_MT_ctx_material.bl_idname, icon='MATERIAL')
        # verrou : Lock sur la sélection ; Unlock All / Unlock Selected dès qu'un objet est verrouillé (même sans sélection)
        if context.selected_objects:
            layout.operator(DESSIN_OT_lock.bl_idname, icon='LOCKED')
        if locked_objects(context):
            layout.operator(DESSIN_OT_unlock_all.bl_idname, icon='UNLOCKED')
            layout.operator(DESSIN_OT_unlock_selected.bl_idname, icon='RESTRICT_SELECT_OFF')
        # Isolate (ne garder que la sélection) et Unisolate (réafficher ce qu'Isolate a masqué)
        from .core import tr_label
        if context.selected_objects:
            layout.operator(DESSIN_OT_isolate.bl_idname, text=tr_label("Isolate"), icon='HIDE_OFF')
        if isolated_objects(context):
            layout.operator(DESSIN_OT_unisolate.bl_idname, text=tr_label("Unisolate"), icon='HIDE_ON')


def menu_ctx_extra(self, context):
    """Sous-menus Material et Select à la fin d'un menu contextuel (mode édition, ou secours)."""
    self.layout.separator()
    ctx_extra_items(self.layout, context)


class _CopyHookLayout:
    """Enveloppe du layout du clic droit : nos menus s'insèrent juste avant « Copy Objects » (en mode objet ils sont déjà
    en haut du menu : rien n'est ajouté ici)."""

    def __init__(self, layout, context, state):
        object.__setattr__(self, "_layout", layout)
        object.__setattr__(self, "_context", context)
        object.__setattr__(self, "_state", state)

    def operator(self, idname, *args, **kwargs):
        lay = object.__getattribute__(self, "_layout")
        state = object.__getattribute__(self, "_state")
        state["sep"] = False
        if state.get("shade") and idname in SHADE_OPS:
            # Shade Smooth / Auto Smooth / Flat : déjà dessinés tout en haut du menu, pas une seconde fois
            if idname == "object.shade_flat":
                state["sep"] = True              # (le séparateur qui les suit chez Blender saute aussi)
            return _NoProps()
        if idname == "view3d.copybuffer" and not state["done"]:
            state["done"] = True
            ctx_extra_items(lay, object.__getattribute__(self, "_context"))
            lay.separator()
        return lay.operator(idname, *args, **kwargs)

    def separator(self, *args, **kwargs):
        state = object.__getattribute__(self, "_state")
        if state.get("sep"):
            state["sep"] = False
            return None
        return object.__getattribute__(self, "_layout").separator(*args, **kwargs)

    def __getattr__(self, name):
        object.__getattribute__(self, "_state")["sep"] = False
        return getattr(object.__getattribute__(self, "_layout"), name)

    def __setattr__(self, name, value):
        setattr(object.__getattribute__(self, "_layout"), name, value)


SHADE_OPS = ("object.shade_smooth", "object.shade_auto_smooth", "object.shade_flat")


class _NoProps:
    """Réglages d'une entrée de menu qui n'est pas dessinée : on peut y écrire, rien ne se passe."""

    def __setattr__(self, name, value):
        pass

    def __getattr__(self, name):
        return None


class DESSIN_MT_ctx_viewport_shading(bpy.types.Menu):
    """Clic droit dans le vide (rien de sélectionné) : l'affichage de cette vue."""
    bl_idname = "DESSIN_MT_ctx_viewport_shading"
    bl_label = "Viewport Shading"

    def draw(self, context):
        layout = self.layout
        sh = getattr(getattr(context, "space_data", None), "shading", None)
        if sh is None:
            return
        for ident, icon in (('WIREFRAME', 'SHADING_WIRE'), ('SOLID', 'SHADING_SOLID'),
                            ('MATERIAL', 'SHADING_TEXTURE'), ('RENDERED', 'SHADING_RENDERED')):
            layout.prop_enum(sh, "type", ident, icon=icon)
        layout.separator()
        layout.prop(sh, "show_xray_wireframe" if sh.type == 'WIREFRAME' else "show_xray", text="X-Ray")
        try:
            layout.separator()
            layout.popover("VIEW3D_PT_shading", text="Shading Options")
        except (TypeError, AttributeError, RuntimeError):
            pass


def ctx_viewport_shading_item(layout, context):
    """« Viewport Shading » en haut du menu quand rien n'est sélectionné. True si ajouté."""
    space = getattr(context, "space_data", None)
    if context.selected_objects or space is None or getattr(space, "type", "") != 'VIEW_3D':
        return False
    layout.menu(DESSIN_MT_ctx_viewport_shading.bl_idname, icon='SHADING_SOLID')
    return True


def ctx_shade_items(layout, context):
    """Shade Smooth, Shade Auto Smooth, Shade Flat, comme Blender les montre (selon l'objet actif). True si dessinés.
    Rien de sélectionné : rien (ils n'agiraient sur aucun objet)."""
    obj = context.active_object
    if obj is None or obj.type not in {'MESH', 'CURVE', 'SURFACE'} or not context.selected_objects:
        return False
    layout.operator("object.shade_smooth")
    if obj.type == 'MESH':
        layout.operator("object.shade_auto_smooth")
    layout.operator("object.shade_flat")
    return True


class _MenuSelf:
    """Faux « self » du menu d'origine : tout est délégué sauf `layout`."""

    def __init__(self, menu, layout):
        object.__setattr__(self, "_menu", menu)
        object.__setattr__(self, "layout", layout)

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_menu"), name)


_CTX_DRAW = {"orig": None}


def _is_hatch(o):
    try:
        return o.type == 'MESH' and "dessin_hatch" in o.keys()
    except (ReferenceError, AttributeError):
        return False


def install_ctx_object_menu():
    cls = bpy.types.VIEW3D_MT_object_context_menu
    if _CTX_DRAW["orig"] is not None:
        return
    orig = cls.draw
    _CTX_DRAW["orig"] = orig

    def draw(self, context):
        state = {"done": False, "shade": False, "sep": False}
        if context.mode == 'OBJECT' and menu_group_edit(self.layout, context):    # Close Group / Edit Group : tout en haut
            self.layout.separator()
        if context.mode == 'OBJECT' and ctx_viewport_shading_item(self.layout, context):    # rien de sélectionné : l'affichage
            self.layout.separator()
        if context.mode == 'OBJECT' and ctx_shade_items(self.layout, context):     # Shade Smooth / Auto / Flat : tout en haut
            self.layout.separator()
            state["shade"] = True
        if context.mode == 'OBJECT' and any(_is_hatch(o) for o in context.selected_objects):
            self.layout.operator("dessin.hatch_edit", icon='MOD_LATTICE')         # « Edit Hatch » tout en haut du menu
            self.layout.separator()
        if context.mode == 'OBJECT' and any(o.type == 'CURVE' for o in context.selected_objects):
            self.layout.menu(DESSIN_MT_ctx_polyline.bl_idname, icon='CURVE_DATA')      # « Polyline » tout en haut du menu
            self.layout.separator()
        if context.mode == 'OBJECT':          # Select, Display As, Material, Lock : en haut, avant Shade Smooth
            ctx_extra_items(self.layout, context)
            self.layout.separator()
            state["done"] = True
        proxy = _CopyHookLayout(self.layout, context, state)
        orig(_MenuSelf(self, proxy), context)
        if not state["done"]:                  # « Copy Objects » introuvable (autre version de Blender) : à la fin
            menu_ctx_extra(self, context)
    if hasattr(orig, "_draw_funcs"):      # Blender garde ici la liste des append / prepend du menu
        draw._draw_funcs = orig._draw_funcs
    cls.draw = draw


def uninstall_ctx_object_menu():
    orig = _CTX_DRAW["orig"]
    if orig is not None:
        try:
            bpy.types.VIEW3D_MT_object_context_menu.draw = orig
        except (AttributeError, TypeError):
            pass
        _CTX_DRAW["orig"] = None


def _late_imports():
    """Noms définis dans des modules chargés après celui-ci : ils ne servent qu'à l'exécution des outils."""
    global DESSIN_OT_join, wire_graph
    from .trim import wire_graph
    from .join_explode import DESSIN_OT_join
