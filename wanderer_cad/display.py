"""Wanderer CAD : Plans de coupe d'affichage et filtres de sélection."""

import math

import bmesh
import bpy
import gpu
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector

from .core import _link_object, _redraw_all_areas, idle_tool, plane_axes, tr_label
from .drawing import _HOVER
from .base import DessinBase
from .tools_draw import DESSIN_OT_rectangle
from .objects import DESSIN_OT_group, DESSIN_OT_ungroup, _GROUP_SEL, group_members, group_root, open_groups_all
from .curve_edit import _idle_later


# --------------------------------------------------------------------------
# Clipping Plane (plan de coupe d'affichage, comme dans Rhino)
# --------------------------------------------------------------------------

CLIP_MAX = 6
_CLIP = {"touched": set(), "pending": False, "alive": False, "error": ""}


CLIP_VER = 2       # plan de coupe dessiné comme un repère de coupe : son repère local porte le plan (Z = côté masqué)
CLIP_SYMBOL = 3    # version du dessin du repère (3 : triangles dans le plan de coupe, comme Rhino)


def clip_plane_coeffs(o):
    """Équation (a, b, c, d) du plan de coupe porté par l'objet : le côté visible est celui où a·x + b·y + c·z + d >= 0.
    Repère de coupe (version 2) : le plan est le plan XY local de l'objet, son Z local pointe vers le côté masqué.
    Anciens plans (un rectangle) : la première face, la flèche pointe vers le côté coupé."""
    mw = o.matrix_world
    if o.get("cad_clip_v", 1) >= CLIP_VER:
        n = mw.to_3x3().inverted_safe().transposed() @ Vector((0.0, 0.0, 1.0))
        if n.length < 1e-12:
            return None
        n.normalize()
        p = mw.translation
        return (-n.x, -n.y, -n.z, n.dot(p))
    me = o.data
    if o.type != 'MESH' or not len(me.polygons):
        return None
    poly = me.polygons[0]
    p = mw @ me.vertices[poly.vertices[0]].co
    n = (mw.to_3x3().inverted_safe().transposed() @ poly.normal)
    if n.length < 1e-12:
        return None
    n.normalize()
    return (-n.x, -n.y, -n.z, n.dot(p))


def clip_symbol_geometry(half):
    """Repère de coupe (comme dans Rhino), en coordonnées locales : la trace du plan (X local), un carré au centre couché
    en travers du plan (plan XZ local) et un triangle à chaque bout, dans le plan de coupe lui-même (plan XY local),
    pointé vers +Y local : vers le bas pour un plan vertical, comme les triangles de Rhino."""
    L = max(float(half), 1e-3)
    t = 0.12 * L            # taille des triangles
    q = 0.2 * L             # demi-côté du carré
    V = [(-L, 0.0, 0.0), (L, 0.0, 0.0),
         (-q, 0.0, -q), (q, 0.0, -q), (q, 0.0, q), (-q, 0.0, q)]
    E = [(0, 1), (2, 3), (3, 4), (4, 5), (5, 2)]
    for sgn in (-1.0, 1.0):
        i = len(V)
        V += [(sgn * L, 0.0, 0.0), (sgn * (L - t), 0.0, 0.0), (sgn * (L - 0.5 * t), t, 0.0)]
        E += [(i, i + 1), (i + 1, i + 2), (i + 2, i)]
    return V, E


def clip_symbol_upgrade(o):
    """Repère dessiné par une version précédente (triangles couchés comme le carré) : redessiné, même taille."""
    try:
        if o.get("cad_clip_v", 1) < CLIP_VER or o.get("cad_clip_sym", 2) >= CLIP_SYMBOL or o.type != 'MESH':
            return False
        me = o.data
        half = max((abs(v.co.x) for v in me.vertices), default=1.0)
        V, E = clip_symbol_geometry(half)
        me.clear_geometry()
        me.from_pydata(V, E, [])
        me.update()
        o["cad_clip_sym"] = CLIP_SYMBOL
        return True
    except (AttributeError, ReferenceError, RuntimeError, TypeError):
        return False


def clip_frame(normal, width_hint=None):
    """Repère (w, h, n) d'un plan de coupe : w horizontal dans le plan quand c'est possible (la trace vue de dessus)."""
    n = Vector(normal).normalized()
    w = n.cross(Vector((0.0, 0.0, 1.0)))
    if w.length < 1e-6:          # plan horizontal : la trace suit X (ou la direction donnée)
        w = Vector(width_hint) if width_hint is not None else Vector((1.0, 0.0, 0.0))
        w = w - n * w.dot(n)
        if w.length < 1e-9:
            w = Vector((1.0, 0.0, 0.0))
    w.normalize()
    h = n.cross(w).normalized()
    return w, h, n


_CLIP_LIST = {"key": None, "names": ()}


def clip_objects(only_active=True, scene=None):
    """Plans de coupe du fichier (de `scene` seulement si elle est donnée), par nom. La liste est gardée tant que rien
    ne change : elle est demandée à chaque image (repère dessiné par-dessus) et un gros fichier a des milliers d'objets."""
    try:
        key = (len(bpy.data.objects), _HOVER["version"])
    except (AttributeError, RuntimeError):
        key = None
    if key is None or _CLIP_LIST["key"] != key:
        names = []
        for o in bpy.data.objects:
            try:
                if o.type == 'MESH' and o.get("cad_clip"):
                    names.append(o.name)
            except ReferenceError:
                continue
        names.sort()
        _CLIP_LIST["key"], _CLIP_LIST["names"] = key, tuple(names)
    out = []
    for n in _CLIP_LIST["names"]:
        o = bpy.data.objects.get(n)
        try:
            if o is None or not o.get("cad_clip"):
                continue
            if scene is not None and scene.objects.get(n) != o:
                continue                # plan de coupe d'une autre scène (une mise en page, un autre modèle)
        except (ReferenceError, AttributeError):
            continue
        out.append(o)
    return out


def clip_list_reset():
    _CLIP_LIST["key"] = None


def _ensure_clip_box(win, area, rv):
    """Blender n'applique les plans de coupe de la vue que si la « boîte de coupe » (Alt + B) existe : RV3D_CLIPPING_ENABLED exige rv3d->clipbb.
    On la crée en appelant view3d.clip_border sur toute la vue ; nos plans sont posés juste après et remplacent ceux de la boîte."""
    try:
        if rv.as_pointer() != area.spaces.active.region_3d.as_pointer():
            return
        region = next((r for r in area.regions if r.type == 'WINDOW'), None)
        if region is None:
            return
        with bpy.context.temp_override(window=win, area=area, region=region):
            try:
                bpy.ops.view3d.clip_border('EXEC_DEFAULT', xmin=0, xmax=region.width, ymin=0, ymax=region.height, wait_for_input=False)
            except TypeError:
                bpy.ops.view3d.clip_border('EXEC_DEFAULT', xmin=0, xmax=region.width, ymin=0, ymax=region.height)
    except (RuntimeError, AttributeError, ReferenceError, TypeError) as e:
        _CLIP["error"] = str(e)


def scene_clip_planes(scene):
    """Équations des plans de coupe actifs d'une scène (6 au maximum)."""
    planes = []
    for o in clip_objects(scene=scene):
        clip_symbol_upgrade(o)
        if not o.get("cad_clip_on", 1) or o.hide_viewport:
            continue
        c = clip_plane_coeffs(o)
        if c is not None:
            planes.append(c)
        if len(planes) >= CLIP_MAX:
            break
    return planes


def update_clip_planes(*_args):
    """Pose les plans de coupe actifs de chaque scène sur les vues 3D qui la montrent (6 au maximum) ; retire ceux qu'on
    avait posés quand il n'y en a plus. Un plan de coupe ne coupe que sa scène (pas les feuilles des mises en page)."""
    try:
        if not clip_objects() and not _CLIP["touched"]:
            return
        per_scene = {}
        for wm in bpy.data.window_managers:
            for win in wm.windows:
                sc = win.scene
                skey = sc.as_pointer() if sc is not None else 0
                if skey not in per_scene:
                    per_scene[skey] = scene_clip_planes(sc) if sc is not None else []
                planes = per_scene[skey]
                pad = planes + [(0.0, 0.0, 1.0, 1.0e9)] * (CLIP_MAX - len(planes))
                for area in win.screen.areas:
                    if area.type != 'VIEW_3D':
                        continue
                    for sp in area.spaces:
                        if sp.type != 'VIEW_3D':
                            continue
                        rvs = [sp.region_3d] + list(sp.region_quadviews)
                        for rv in rvs:
                            if rv is None:
                                continue
                            key = rv.as_pointer()
                            if planes:
                                cur = [tuple(p) for p in rv.clip_planes]
                                same = rv.use_clip_planes and all(
                                    all(abs(a - b) < 1e-6 * max(1.0, abs(b)) for a, b in zip(p, q)) for p, q in zip(cur, pad))
                                if not same:
                                    if key not in _CLIP["touched"] or not rv.use_clip_planes:
                                        _ensure_clip_box(win, area, rv)
                                    rv.clip_planes = pad
                                    rv.use_clip_planes = True
                                    area.tag_redraw()
                                _CLIP["touched"].add(key)
                            elif key in _CLIP["touched"]:
                                rv.use_clip_planes = False
                                _CLIP["touched"].discard(key)
                                area.tag_redraw()
    except (RuntimeError, ReferenceError, AttributeError, TypeError, ValueError):
        pass


def clip_blocked_shading(space):
    """Blender ne découpe pas l'affichage en mode Material Preview / Rendered (EEVEE et Cycles ne gèrent pas les plans de coupe de la vue)."""
    try:
        return space is not None and space.type == 'VIEW_3D' and space.shading.type in ('MATERIAL', 'RENDERED')
    except (AttributeError, ReferenceError, RuntimeError):
        return False


def clear_clip_planes():
    """À la désactivation de l'extension : rend les vues comme avant."""
    try:
        for wm in bpy.data.window_managers:
            for win in wm.windows:
                for area in win.screen.areas:
                    if area.type != 'VIEW_3D':
                        continue
                    for sp in area.spaces:
                        if sp.type != 'VIEW_3D':
                            continue
                        for rv in [sp.region_3d] + list(sp.region_quadviews):
                            if rv is not None and rv.as_pointer() in _CLIP["touched"]:
                                rv.use_clip_planes = False
                    area.tag_redraw()
    except (RuntimeError, ReferenceError, AttributeError):
        pass
    _CLIP["touched"].clear()


class DESSIN_OT_clip_plane(DessinBase):
    bl_idname = "dessin.clip_plane"
    bl_label = "Clipping Plane"
    bl_description = ("Draws a clipping plane (first corner, opposite corner, in the active view plane): the view hides everything "
                      "on the side the arrow points to (move it with the gizmo; flip it or switch it off in the Wanderer panel). Works in Solid and Wireframe shading only")

    TITLE = "Clipping Plane"
    CORNER_STAGES = (1,)
    PROP = (1,)
    NEEDED = 2
    NUMFIELDS = 2
    HAS_CENTER = True
    EDIT_OK = False

    prompt = DESSIN_OT_rectangle.prompt
    compute = DESSIN_OT_rectangle.compute

    def invoke(self, context, event):
        if context.mode == 'EDIT_MESH':
            try:
                bpy.ops.object.mode_set(mode='OBJECT')
            except RuntimeError:
                self.report({'WARNING'}, "Switch to Object mode")
                return {'CANCELLED'}
        return super().invoke(context, event)

    def build(self, context, spec):
        corners = list(spec[1])
        normal = plane_axes(self.axis)[2].copy()
        center = sum(corners, Vector()) / 4.0
        if (corners[1] - corners[0]).cross(corners[2] - corners[1]).dot(normal) < 0:
            normal = -normal
        w, h, n = clip_frame(normal, corners[1] - corners[0])
        half = max(abs((c - center).dot(w)) for c in corners)
        if half < 1e-6:
            half = max((c - center).length for c in corners)
        V, E = clip_symbol_geometry(half)
        me = bpy.data.meshes.new("Clipping Plane")
        me.from_pydata(V, E, [])
        me.update()
        obj = _link_object(context, "Clipping Plane", me)
        obj.matrix_world = Matrix((
            (w.x, h.x, n.x, center.x),
            (w.y, h.y, n.y, center.y),
            (w.z, h.z, n.z, center.z),
            (0.0, 0.0, 0.0, 1.0)))
        obj.display_type = 'WIRE'
        obj.show_in_front = True
        obj.hide_render = True
        obj["cad_clip"] = 1
        obj["cad_clip_on"] = 1
        obj["cad_clip_v"] = CLIP_VER
        obj["cad_clip_sym"] = CLIP_SYMBOL
        clip_list_reset()
        try:
            context.view_layer.update()      # la matrice de l'objet doit être à jour avant de calculer le plan
        except (RuntimeError, AttributeError):
            pass
        update_clip_planes()
        blocked = False
        try:
            blocked = clip_blocked_shading(context.space_data)
        except AttributeError:
            pass
        if blocked:
            self.report({'WARNING'}, "Clipping plane created, but Blender only clips in Solid or Wireframe shading: switch this viewport to Solid to see the cut")
        else:
            self.report({'INFO'}, "Clipping plane created (the arrow points to the hidden side)")
        return obj

    def after_finish(self, context):
        if self.tool_id:
            try:
                idle_tool()
            except (RuntimeError, TypeError):
                pass


class DESSIN_OT_clip_edit(bpy.types.Operator):
    bl_idname = "dessin.clip_edit"
    bl_label = "Clipping plane"
    bl_description = "Switches a clipping plane on / off, flips it, or deletes it"
    bl_options = {'REGISTER', 'UNDO'}

    name: bpy.props.StringProperty()
    action: bpy.props.EnumProperty(items=(('TOGGLE', "Toggle", ""), ('FLIP', "Flip", ""), ('DELETE', "Delete", ""),
                                          ('SELECT', "Select", "")))

    def execute(self, context):
        o = bpy.data.objects.get(self.name)
        if o is None or o.type != 'MESH':
            return {'CANCELLED'}
        clip_list_reset()
        if self.action == 'TOGGLE':
            o["cad_clip_on"] = 0 if o.get("cad_clip_on", 1) else 1
        elif self.action == 'FLIP':
            me = o.data
            if o.get("cad_clip_v", 1) >= CLIP_VER:
                # demi-tour autour de l'axe vertical du repère : l'autre côté, les triangles restent vers le bas
                o.matrix_world = o.matrix_world @ Matrix.Rotation(math.pi, 4, 'Y')
            elif len(me.vertices) >= 6:
                me.flip_normals()
                c, t = me.vertices[4].co.copy(), me.vertices[5].co.copy()
                me.vertices[5].co = 2.0 * c - t
                me.update()
        elif self.action == 'DELETE':
            me = o.data
            bpy.data.objects.remove(o, do_unlink=True)
            if me.users == 0:
                bpy.data.meshes.remove(me)
        elif self.action == 'SELECT':
            for s in list(context.selected_objects):
                s.select_set(False)
            try:
                o.select_set(True)
                context.view_layer.objects.active = o
            except RuntimeError:
                pass
        update_clip_planes()
        return {'FINISHED'}


_CLIP_DRAW = []


def clip_symbol_segments(o):
    """Segments monde (2 points par segment) du repère de coupe d'un objet."""
    me = o.data
    mw = o.matrix_world
    W = [mw @ v.co for v in me.vertices]
    out = []
    for e in me.edges:
        a, b = e.vertices
        out.append(tuple(W[a]))
        out.append(tuple(W[b]))
    return out


def _clip_symbol_draw():
    """Le repère de coupe en entier, par-dessus tout : Blender coupe aussi l'objet lui-même (sa moitié côté masqué
    disparaîtrait), alors on le redessine ici, hors coupe, avec la couleur de Blender (sélectionné, actif ou non)."""
    ctx = bpy.context
    space = getattr(ctx, "space_data", None)
    objs = []
    try:
        if space is not None and not space.overlay.show_overlays:
            return                      # « Show Overlays » éteint : vue nue, comme pour les autres repères
        for o in clip_objects(scene=ctx.scene):
            if o.get("cad_clip_v", 1) < CLIP_VER or o.type != 'MESH':
                continue
            try:
                if not o.visible_get(viewport=space):
                    continue
            except (TypeError, RuntimeError):
                try:
                    if not o.visible_get():
                        continue
                except RuntimeError:
                    continue
            objs.append(o)
    except (ReferenceError, AttributeError, RuntimeError):
        return
    if not objs:
        return
    try:
        th = ctx.preferences.themes[0].view_3d
        col_act, col_sel, col_wire = tuple(th.object_active), tuple(th.object_selected), tuple(th.wire)
        ui = ctx.preferences.system.ui_scale
    except (AttributeError, IndexError):
        col_act, col_sel, col_wire, ui = (1.0, 0.63, 0.16), (0.93, 0.34, 0.0), (0.0, 0.0, 0.0), 1.0
    active = getattr(ctx, "active_object", None)
    gpu.state.blend_set('ALPHA')
    gpu.state.depth_test_set('NONE')
    try:
        sh = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
        sh.bind()
        sh.uniform_float("viewportSize", gpu.state.viewport_get()[2:])
        sh.uniform_float("lineWidth", 1.5 * ui)
        for o in objs:
            pts = clip_symbol_segments(o)
            if not pts:
                continue
            rgb = col_act if (o.select_get() and o == active) else (col_sel if o.select_get() else col_wire)
            alpha = 1.0 if o.get("cad_clip_on", 1) else 0.4        # plan éteint : plus pâle
            sh.uniform_float("color", (rgb[0], rgb[1], rgb[2], alpha))
            batch_for_shader(sh, 'LINES', {"pos": pts}).draw(sh)
    except (ValueError, AttributeError, TypeError, SystemError, ReferenceError, RuntimeError):
        pass
    finally:
        gpu.state.depth_test_set('LESS_EQUAL')
        gpu.state.blend_set('NONE')


def register_clip_draw():
    if not _CLIP_DRAW:
        _CLIP_DRAW.append(bpy.types.SpaceView3D.draw_handler_add(_clip_symbol_draw, (), 'WINDOW', 'POST_VIEW'))


def unregister_clip_draw():
    while _CLIP_DRAW:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(_CLIP_DRAW.pop(), 'WINDOW')
        except (ValueError, RuntimeError):
            pass


class DESSIN_PT_clip(bpy.types.Panel):
    bl_label = "Clipping Planes"
    bl_idname = "DESSIN_PT_clip"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Wanderer"

    def draw(self, context):
        col = self.layout.column(align=True)
        objs = clip_objects(scene=context.scene)
        if objs and clip_blocked_shading(context.space_data):
            box = col.box()
            box.label(text="Not applied in Material Preview / Rendered", icon='ERROR')
            box.label(text="Switch the viewport to Solid or Wireframe")
        if objs and _CLIP["error"]:
            col.label(text="Clipping could not be enabled: " + _CLIP["error"][:60], icon='ERROR')
        if not objs:
            col.label(text="No clipping plane yet (Clipping Plane tool)")
            return
        for i, o in enumerate(objs):
            on = bool(o.get("cad_clip_on", 1))
            row = col.row(align=True)
            op = row.operator("dessin.clip_edit", text="", icon='HIDE_OFF' if on else 'HIDE_ON', depress=on)
            op.name, op.action = o.name, 'TOGGLE'
            op = row.operator("dessin.clip_edit", text=o.name, emboss=False)
            op.name, op.action = o.name, 'SELECT'
            op = row.operator("dessin.clip_edit", text="", icon='ARROW_LEFTRIGHT')
            op.name, op.action = o.name, 'FLIP'
            op = row.operator("dessin.clip_edit", text="", icon='X')
            op.name, op.action = o.name, 'DELETE'
        if len(objs) > CLIP_MAX:
            col.label(text=f"Only the first {CLIP_MAX} planes are applied", icon='ERROR')


# --------------------------------------------------------------------------
# Filtres de sélection (panneau latéral) : Maj + clic = « seulement ce type » pour la prochaine sélection
# --------------------------------------------------------------------------

SEL_FILTERS = (
    ("mesh", "Meshes", ("mesh",)),
    ("curve", "Curves", ("curve", "curves")),
    ("surf", "Surfaces", ("surf",)),
    ("text", "Text", ("font",)),
    ("light", "Lights", ("light", "light_probe")),
    ("camera", "Cameras", ("camera",)),
    ("empty", "Empties / Blocks", ("empty",)),
    ("cloud", "Point Clouds", ("pointcloud",)),
    ("gp", "Grease Pencil", ("grease_pencil",)),
    ("arm", "Armatures", ("armature",)),
    ("other", "Others", ("meta", "volume", "lattice", "speaker")),
)
_SF = {"saved": None, "solo": None, "sig": None, "timer": False, "held": False}


def _sf_spaces(context):
    out = []
    try:
        for win in context.window_manager.windows:
            for area in win.screen.areas:
                if area.type == 'VIEW_3D':
                    out.extend(sp for sp in area.spaces if sp.type == 'VIEW_3D')
    except (AttributeError, RuntimeError, ReferenceError):
        pass
    return out


def _sf_props(key):
    return next((p for k, _l, p in SEL_FILTERS if k == key), ())


def _sf_get(space, key):
    props = _sf_props(key)
    try:
        return bool(getattr(space, "show_object_select_" + props[0])) if props else True
    except AttributeError:
        return True


def _sf_set(space, key, value):
    for name in _sf_props(key):
        try:
            setattr(space, "show_object_select_" + name, value)
        except (AttributeError, TypeError):
            pass


def _sf_signature(context):
    try:
        return (tuple(sorted(o.name for o in context.view_layer.objects if o.select_get())),
                context.view_layer.objects.active.name if context.view_layer.objects.active else "")
    except (AttributeError, RuntimeError, ReferenceError):
        return None


def sel_filter_restore(context=None):
    """Rend aux filtres leur état d'avant le « seulement ce type »."""
    context = context or bpy.context
    saved = _SF["saved"]
    _SF["saved"] = _SF["solo"] = _SF["sig"] = None
    if saved is None:
        return
    for sp in _sf_spaces(context):
        state = saved.get(sp.as_pointer())
        if state is None:
            for key, _l, _p in SEL_FILTERS:
                _sf_set(sp, key, True)
            continue
        for key, val in state.items():
            _sf_set(sp, key, val)
    try:
        for win in context.window_manager.windows:
            for area in win.screen.areas:
                area.tag_redraw()
    except (AttributeError, RuntimeError, ReferenceError):
        pass


def _sf_tick():
    """Dès que la sélection change (le clic ou le rectangle est fait), les filtres reviennent comme avant."""
    if _SF["saved"] is None:
        _SF["timer"] = False
        return None
    if _SF["solo"] is None:
        return 0.1              # Maj maintenu sans choix : on attend le relâchement ou le clic sur un filtre
    try:
        if _sf_signature(bpy.context) != _SF["sig"]:
            sel_filter_restore()
            _SF["timer"] = False
            return None
    except (RuntimeError, ReferenceError):
        pass
    return 0.1


class DESSIN_OT_sel_filter(bpy.types.Operator):
    bl_idname = "dessin.sel_filter"
    bl_label = "Selection Filter"
    bl_description = ("Click: turns this type on / off for selection.  Shift + click: only this type for the next selection "
                      "(click or box); every filter comes back afterwards")
    bl_options = {'INTERNAL'}

    kind: bpy.props.StringProperty(options={'SKIP_SAVE'})

    def invoke(self, context, event):
        spaces = _sf_spaces(context)
        if self.kind == "ALL":
            if _SF["saved"] is not None:
                sel_filter_restore(context)
            for sp in spaces:
                for key, _l, _p in SEL_FILTERS:
                    _sf_set(sp, key, True)
            return {'FINISHED'}
        if event.shift:
            if _SF["saved"] is None:
                _SF["saved"] = {sp.as_pointer(): {k: _sf_get(sp, k) for k, _l, _p in SEL_FILTERS} for sp in spaces}
            _SF["sig"] = _sf_signature(context)
            _SF["solo"] = self.kind
            for sp in spaces:
                for key, _l, _p in SEL_FILTERS:
                    _sf_set(sp, key, key == self.kind)
            if not _SF["timer"]:
                _SF["timer"] = True
                bpy.app.timers.register(_sf_tick, first_interval=0.2)
            return {'FINISHED'}
        if _SF["saved"] is not None:
            sel_filter_restore(context)
        for sp in spaces:
            _sf_set(sp, self.kind, not _sf_get(sp, self.kind))
        return {'FINISHED'}


class DESSIN_OT_sel_filter_hold(bpy.types.Operator):
    """Maj maintenu au-dessus de la barre latérale : tous les filtres se décochent ; un clic sur un filtre ne garde que lui ;
    au relâchement, tout revient (sauf si un filtre a été choisi : il reste jusqu'à la prochaine sélection)."""
    bl_idname = "dessin.sel_filter_hold"
    bl_label = "Selection Filters: hold Shift"
    bl_options = {'INTERNAL'}

    down: bpy.props.BoolProperty(default=True, options={'SKIP_SAVE'})

    def invoke(self, context, event):
        try:
            if self.down:
                if context.region is not None and context.region.type == 'UI' and _SF["saved"] is None:
                    spaces = _sf_spaces(context)
                    _SF["saved"] = {sp.as_pointer(): {k: _sf_get(sp, k) for k, _l, _p in SEL_FILTERS} for sp in spaces}
                    _SF["solo"] = None
                    _SF["held"] = True
                    for sp in spaces:
                        for key, _l, _p in SEL_FILTERS:
                            _sf_set(sp, key, False)
                    if not _SF["timer"]:
                        _SF["timer"] = True
                        bpy.app.timers.register(_sf_tick, first_interval=0.2)
                    for win in context.window_manager.windows:
                        for area in win.screen.areas:
                            area.tag_redraw()
            elif _SF["held"]:
                _SF["held"] = False
                if _SF["saved"] is not None and _SF["solo"] is None:
                    sel_filter_restore(context)
        except (AttributeError, RuntimeError, ReferenceError):
            pass
        return {'FINISHED', 'PASS_THROUGH'}


_SF_KEYMAPS = []


def register_sel_filter_keys():
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon if wm is not None else None
    if kc is None:
        return
    for name, space, press in (("3D View Generic", 'VIEW_3D', True), ("Window", 'EMPTY', False)):
        km = kc.keymaps.new(name=name, space_type=space)
        for key in ('LEFT_SHIFT', 'RIGHT_SHIFT'):
            kmi = km.keymap_items.new(DESSIN_OT_sel_filter_hold.bl_idname, key, 'PRESS' if press else 'RELEASE', any=True)
            kmi.properties.down = press
            _SF_KEYMAPS.append((km, kmi))
            if not press:
                # le relâchement doit aussi être vu depuis la barre latérale
                pass


def unregister_sel_filter_keys():
    for km, kmi in _SF_KEYMAPS:
        try:
            km.keymap_items.remove(kmi)
        except (RuntimeError, ReferenceError, TypeError):
            pass
    _SF_KEYMAPS.clear()


class DESSIN_PT_selfilter(bpy.types.Panel):
    bl_label = "Selection Filters"
    bl_idname = "DESSIN_PT_selfilter"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Selection Filters"    # onglet séparé de la barre latérale

    def draw(self, context):
        col = self.layout.column(align=True)
        sp = context.space_data
        solo = _SF["solo"]
        for key, label, _p in SEL_FILTERS:
            on = _sf_get(sp, key) if sp is not None else True
            row = col.row(align=True)
            op = row.operator("dessin.sel_filter", text=tr_label(label), icon='CHECKBOX_HLT' if on else 'CHECKBOX_DEHLT',
                              emboss=False, depress=(solo == key))
            op.kind = key
        col.separator()
        if solo is not None:
            col.label(text="Only this type until the next selection", icon='INFO')
        col.operator("dessin.sel_filter", text="Select everything again", icon='RESTRICT_SELECT_OFF').kind = "ALL"
        col.label(text="Hold Shift here: all off, click one to keep only it")


def _overkill_chain(pts, cyc, tol, collinear):
    """Nettoie une suite de points : doublons consécutifs et points alignés."""
    out = []
    for p in pts:
        if not out or (p - out[-1]).length > tol:
            out.append(p)
    if cyc and len(out) > 1 and (out[0] - out[-1]).length <= tol:
        out.pop()
    if collinear:
        changed = True
        while changed and len(out) > (3 if cyc else 2):
            changed = False
            n = len(out)
            rng = range(n) if cyc else range(1, n - 1)
            for i in rng:
                a, b, c = out[i - 1], out[i], out[(i + 1) % n]
                ac = c - a
                if ac.length < 1e-12:
                    continue
                t = (b - a).dot(ac) / ac.length_squared
                if 0.0 < t < 1.0 and (b - (a + ac * t)).length <= tol:
                    out.pop(i)
                    changed = True
                    break
    return out


class DESSIN_OT_overkill(bpy.types.Operator):
    bl_idname = "dessin.overkill"
    bl_label = "Overkill"
    bl_description = ("Cleans the selected curves, outlines and meshes: merges duplicate points, removes duplicate edges, "
                      "points on a straight line and identical objects")
    bl_options = {'REGISTER', 'UNDO'}

    tolerance: bpy.props.FloatProperty(name="Tolerance", default=1e-4, min=1e-9, max=1.0, precision=6, subtype='DISTANCE')
    collinear: bpy.props.BoolProperty(name="Remove points on a straight line", default=True)
    duplicates: bpy.props.BoolProperty(name="Delete identical objects", default=True)

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and context.area is not None and context.area.type == 'VIEW_3D'

    def invoke(self, context, event):
        if not any(o.type in {'MESH', 'CURVE'} for o in context.selected_objects):
            self.report({'INFO'}, "Select the objects to clean (click them, then Enter)")
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self, width=300)

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, "tolerance")
        col.prop(self, "collinear")
        col.prop(self, "duplicates")

    def clean_mesh(self, obj):
        me = obj.data
        bm = bmesh.new()
        bm.from_mesh(me)
        before = (len(bm.verts), len(bm.edges))
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=self.tolerance)
        bmesh.ops.dissolve_degenerate(bm, dist=self.tolerance, edges=bm.edges)
        if self.collinear and not bm.faces:
            cand = []
            for v in bm.verts:
                if len(v.link_edges) == 2:
                    a = v.link_edges[0].other_vert(v).co
                    b = v.link_edges[1].other_vert(v).co
                    ab = b - a
                    if ab.length > 1e-12:
                        t = (v.co - a).dot(ab) / ab.length_squared
                        if 0.0 < t < 1.0 and (v.co - (a + ab * t)).length <= self.tolerance:
                            cand.append(v)
            if cand:
                bmesh.ops.dissolve_verts(bm, verts=cand)
        after = (len(bm.verts), len(bm.edges))
        if after != before:
            bm.to_mesh(me)
            me.update()
        bm.free()
        return before[0] - after[0], before[1] - after[1]

    def clean_curve(self, obj):
        cu = obj.data
        removed = 0
        for sp in list(cu.splines):
            if sp.type != 'POLY':
                continue
            pts = [Vector(p.co[:3]) for p in sp.points]
            new = _overkill_chain(pts, sp.use_cyclic_u, self.tolerance, self.collinear)
            if len(new) == len(pts) or len(new) < 2:
                continue
            cyc = sp.use_cyclic_u
            cu.splines.remove(sp)
            ns = cu.splines.new('POLY')
            ns.points.add(len(new) - 1)
            for q, p in zip(ns.points, new):
                q.co = (p.x, p.y, p.z, 1.0)
            ns.use_cyclic_u = cyc and len(new) >= 3
            removed += len(pts) - len(new)
        return removed

    def signature(self, obj):
        mw = obj.matrix_world
        r = lambda p: tuple(round(c / self.tolerance) for c in (mw @ p))
        if obj.type == 'MESH':
            me = obj.data
            verts = frozenset(r(v.co) for v in me.vertices)
            edges = frozenset(frozenset((r(me.vertices[a].co), r(me.vertices[b].co))) for a, b in (e.vertices for e in me.edges))
            return ('M', verts, edges)
        parts = []
        for sp in obj.data.splines:
            pts = sp.bezier_points if sp.type == 'BEZIER' else sp.points
            parts.append((sp.type, tuple(r(Vector(p.co[:3])) for p in pts)))
        return ('C', tuple(sorted(parts)))

    def execute(self, context):
        objs = [o for o in context.selected_objects if o.type in {'MESH', 'CURVE'}]
        if not objs:
            self.report({'INFO'}, "Select the objects to clean (click them, then Enter)")
            return {'CANCELLED'}
        verts = edges = dupes = 0
        if self.duplicates:
            seen, keep = {}, []
            for o in objs:
                try:
                    key = self.signature(o)
                except (RuntimeError, ReferenceError):
                    keep.append(o)
                    continue
                if key in seen and key[1]:
                    bpy.data.objects.remove(o, do_unlink=True)
                    dupes += 1
                else:
                    seen[key] = o
                    keep.append(o)
            objs = keep
        for o in objs:
            if o.type == 'MESH':
                dv, de = self.clean_mesh(o)
                verts += dv
                edges += de
            else:
                verts += self.clean_curve(o)
        self.report({'INFO'}, f"Overkill: {verts} point(s), {edges} edge(s), {dupes} identical object(s) removed")
        _idle_later()
        return {'FINISHED'}


def _group_select_tick():
    if not _GROUP_SEL["on"]:
        return None
    try:
        ctx = bpy.context
        sc0 = ctx.scene
        if sc0 is not None and "wd_shapes_v2" not in sc0.keys():      # migration « Shapes as » : Mesh -> Curve, une fois par scène
            if sc0.dessin.sortie_formes == 'MESH':
                sc0.dessin.sortie_formes = 'CURVE'
            sc0["wd_shapes_v2"] = 1
            _redraw_all_areas()
    except (RuntimeError, ReferenceError, AttributeError, TypeError, ValueError, KeyError):
        pass
    try:
        ctx = bpy.context
        st = getattr(ctx.scene, "dessin", None)
        if ctx.mode == 'OBJECT' and st is not None and st.group_select:
            sel = {o.name for o in ctx.selected_objects}
            new = sel - _GROUP_SEL["last"]
            extra = set()
            opened = open_groups_all(ctx) or None if new else None      # Edit Group : pas au-delà du groupe ouvert
            for n in new:
                o = bpy.data.objects.get(n)
                root = group_root(o, stop=opened) if o is not None else None
                if root is not None:
                    extra |= {m.name for m in group_members(root)}
            extra -= sel
            for n in extra:
                m = bpy.data.objects.get(n)
                if m is not None and m.visible_get():
                    m.select_set(True)
                    sel.add(n)
            _GROUP_SEL["last"] = sel
    except Exception:
        pass
    return 0.15


class DESSIN_PT_shapes(bpy.types.Panel):
    bl_label = "Drawing"
    bl_idname = "DESSIN_PT_shapes"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Wanderer"

    def draw(self, context):
        self.layout.prop(context.scene.dessin, "sortie_formes")


class DESSIN_PT_groups(bpy.types.Panel):
    bl_label = "Groups"
    bl_idname = "DESSIN_PT_groups"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Wanderer"

    def draw(self, context):
        col = self.layout.column()
        col.prop(context.scene.dessin, "group_select")
        row = col.row(align=True)
        row.operator(DESSIN_OT_group.bl_idname, icon='GROUP')
        row.operator(DESSIN_OT_ungroup.bl_idname, icon='UGLYPACKAGE')


def _late_imports():
    pass
