"""Wanderer CAD : types de ligne (tirets, axes, cachés...) par calque ou par objet, comme dans AutoCAD.

Dans les vues 3D, un modificateur Geometry Nodes découpe la courbe en tirets (taille réglée par l'échelle des types de
ligne : « comme imprimé au 1:N »). Le dessin lui-même n'est pas touché : accrochages, Trim, Offset, Boundary, export DXF
lisent toujours la courbe entière. Sur les mises en page, les tirets sont refaits à leur vraie taille sur le papier (mm),
quelle que soit l'échelle de la fenêtre.
"""

import bpy

from .core import LT_MOD, has_lt, is_lt_mod, object_collections, object_collections_map

# (clé, nom, description, motif en mm de papier : tiret, espace, tiret, espace...)
LINETYPES = (
    ('CONTINUOUS', "Continuous", "Solid line", ()),
    ('DASHED', "Dashed", "Dashes: 6 mm dash, 3 mm gap (as printed)", (6.0, 3.0)),
    ('HIDDEN', "Hidden", "Short dashes: 3 mm dash, 1.5 mm gap (hidden edges, what is above the cut)", (3.0, 1.5)),
    ('CENTER', "Center", "Long and short dashes (axes, center lines)", (12.0, 3.0, 2.0, 3.0)),
    ('DASHDOT', "Dash Dot", "Dash and dot", (6.0, 2.5, 0.4, 2.5)),
    ('PHANTOM', "Phantom", "Long dash and two short dashes", (12.0, 2.5, 2.0, 2.5, 2.0, 2.5)),
    ('DOT', "Dot", "Dots", (0.4, 1.6)),
)
LINETYPE_ITEMS = tuple((k, n, d) for k, n, d, _p in LINETYPES)
OBJECT_LINETYPE_ITEMS = (('BYLAYER', "By Layer", "The objects follow the linetype of their layer again"),) + LINETYPE_ITEMS
PATTERN = {k: p for k, _n, _d, p in LINETYPES}
NAMES = {k: n for k, n, _d, _p in LINETYPES}
GROUP_PREFIX = "WD Linetype "
_LT_BROKEN = set()
LT_MAX_POINTS = 6000
LT_GROUP_VER = 2          # version du groupe de nœuds (reconstruit quand elle change)


def lt_eligible(o):
    """Courbes et contours (maillages sans face) : ce qui porte un type de ligne. Pas les cotes, textes, hachures,
    plans de coupe ni les objets générés par les mises en page."""
    try:
        keys = o.keys()
        if any(k in keys for k in ("dessin_cotation", "dessin_cotation_texte", "dessin_dim", "dessin_hatch", "cad_clip",
                                   "wd_gen", "wd_layout_gen")):
            return False
        if o.type == 'CURVE':
            cu = o.data
            if cu.bevel_depth != 0.0 or cu.extrude != 0.0 or cu.bevel_object is not None:
                return False            # courbe épaissie (tube, profilé) : un volume, pas un trait
            if cu.dimensions == '2D' and cu.fill_mode != 'NONE' and any(sp.use_cyclic_u for sp in cu.splines):
                return False            # courbe 2D remplie : une surface
            return True
        return o.type == 'MESH' and len(o.data.edges) > 0 and not len(o.data.polygons)
    except (AttributeError, ReferenceError):
        return False


def layer_linetype(o, cmap=None):
    for c in object_collections(o, cmap):
        pg = getattr(c, "dessin_layer", None)
        if pg is not None:
            return getattr(pg, "linetype", 'CONTINUOUS') or 'CONTINUOUS'
    return 'CONTINUOUS'


def lt_effective(o, cmap=None):
    """Type de ligne de l'objet : le sien, sinon celui de son calque."""
    try:
        own = o.get("wd_lt")
    except (AttributeError, ReferenceError):
        own = None
    if own and own in PATTERN:
        return own
    return layer_linetype(o, cmap)


def lt_print_key(o, cmap=None):
    """Type de ligne à imprimer ('' : trait continu)."""
    if not lt_eligible(o):
        return ""
    k = lt_effective(o, cmap)
    return "" if k == 'CONTINUOUS' or not PATTERN.get(k) else k


def lt_scale(scene=None):
    """Unités Blender par mm de motif : les tirets du modèle sont dessinés comme imprimés au 1:N."""
    sc = scene or bpy.context.scene
    try:
        n = float(sc.dessin.linetype_scale)
    except (AttributeError, ReferenceError):
        n = 50.0
    try:
        sl = float(sc.unit_settings.scale_length) or 1.0
    except (AttributeError, ReferenceError):
        sl = 1.0
    return max(n, 1e-6) * 0.001 / sl


# --------------------------------------------------------------------------
# Groupe de nœuds : la courbe rééchantillonnée, puis les arêtes des espaces retirées
# --------------------------------------------------------------------------

def _menu_or_prop(node, sock, value_menu, prop, value_prop):
    s = node.inputs.get(sock)
    if s is not None and s.type == 'MENU':
        s.default_value = value_menu
    elif hasattr(node, prop):
        setattr(node, prop, value_prop)


def _build_group(ng, pattern):
    nodes, links = ng.nodes, ng.links
    nodes.clear()
    if not ng.interface.items_tree:
        ng.interface.new_socket("Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
        ng.interface.new_socket("Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
    gin = nodes.new("NodeGroupInput")
    gout = nodes.new("NodeGroupOutput")
    sep = nodes.new("GeometryNodeSeparateComponents")
    m2c = nodes.new("GeometryNodeMeshToCurve")
    join = nodes.new("GeometryNodeJoinGeometry")
    links.new(gin.outputs[0], sep.inputs[0])
    links.new(sep.outputs["Mesh"], m2c.inputs["Mesh"])
    links.new(m2c.outputs[0], join.inputs[0])
    links.new(sep.outputs["Curve"], join.inputs[0])
    # échelle (unités Blender par mm de motif) : une seule valeur à changer quand l'échelle des types de ligne change
    k = nodes.new("ShaderNodeValue")
    k.name = k.label = "wd_lt_scale"
    k.outputs[0].default_value = lt_scale()
    step = min(x for x in pattern if x > 0) / 3.0
    stepm = nodes.new("ShaderNodeMath")
    stepm.operation = 'MULTIPLY'
    stepm.inputs[1].default_value = step
    links.new(k.outputs[0], stepm.inputs[0])
    res = nodes.new("GeometryNodeResampleCurve")
    _menu_or_prop(res, "Mode", "Length", "mode", 'LENGTH')
    links.new(join.outputs[0], res.inputs["Curve"])
    # garde-fou : jamais plus de LT_MAX_POINTS points par courbe (une très longue courbe en pointillés fins ne charge pas la scène)
    slen = nodes.new("GeometryNodeSplineLength")
    cap_ = nodes.new("ShaderNodeMath")
    cap_.operation = 'DIVIDE'
    cap_.inputs[1].default_value = float(LT_MAX_POINTS)
    links.new(slen.outputs["Length"], cap_.inputs[0])
    stepx = nodes.new("ShaderNodeMath")
    stepx.operation = 'MAXIMUM'
    links.new(stepm.outputs[0], stepx.inputs[0])
    links.new(cap_.outputs[0], stepx.inputs[1])
    links.new(stepx.outputs[0], res.inputs["Length"])
    cap = nodes.new("GeometryNodeCaptureAttribute")
    cap.domain = 'POINT'
    try:
        cap.capture_items.new('FLOAT', "Length")
        cin, cout = cap.inputs["Length"], cap.outputs["Length"]       # (par leur nom : l'ordre change d'une version à l'autre)
    except (AttributeError, TypeError, KeyError):
        cap.data_type = 'FLOAT'
        cin = next(x for x in cap.inputs if x.type == 'VALUE' and x.enabled)
        cout = next(x for x in cap.outputs if x.type == 'VALUE' and x.enabled)
    sparam = nodes.new("GeometryNodeSplineParameter")
    links.new(res.outputs[0], cap.inputs[0])
    links.new(sparam.outputs["Length"], cin)
    c2m = nodes.new("GeometryNodeCurveToMesh")
    links.new(cap.outputs[0], c2m.inputs["Curve"])
    # position dans le motif (mm) : longueur au milieu de l'arête / échelle, modulo la période
    div = nodes.new("ShaderNodeMath")
    div.operation = 'DIVIDE'
    links.new(cout, div.inputs[0])
    links.new(k.outputs[0], div.inputs[1])
    period = float(sum(pattern))
    mod = nodes.new("ShaderNodeMath")
    mod.operation = 'FLOORED_MODULO'
    mod.inputs[1].default_value = period
    links.new(div.outputs[0], mod.inputs[0])
    on = None
    start = 0.0
    for i in range(0, len(pattern), 2):
        dash = pattern[i]
        a, b = start, start + dash
        ge = nodes.new("FunctionNodeCompare")
        ge.data_type, ge.operation = 'FLOAT', 'GREATER_EQUAL'
        ge.inputs["B"].default_value = a
        lt = nodes.new("FunctionNodeCompare")
        lt.data_type, lt.operation = 'FLOAT', 'LESS_THAN'
        lt.inputs["B"].default_value = b
        links.new(mod.outputs[0], ge.inputs["A"])
        links.new(mod.outputs[0], lt.inputs["A"])
        both = nodes.new("FunctionNodeBooleanMath")
        both.operation = 'AND'
        links.new(ge.outputs[0], both.inputs[0])
        links.new(lt.outputs[0], both.inputs[1])
        if on is None:
            on = both
        else:
            orr = nodes.new("FunctionNodeBooleanMath")
            orr.operation = 'OR'
            links.new(on.outputs[0], orr.inputs[0])
            links.new(both.outputs[0], orr.inputs[1])
            on = orr
        start = b + (pattern[i + 1] if i + 1 < len(pattern) else 0.0)
    gap = nodes.new("FunctionNodeBooleanMath")
    gap.operation = 'NOT'
    links.new(on.outputs[0], gap.inputs[0])
    dele = nodes.new("GeometryNodeDeleteGeometry")
    dele.domain = 'EDGE'
    links.new(c2m.outputs[0], dele.inputs["Geometry"])
    links.new(gap.outputs[0], dele.inputs["Selection"])
    links.new(dele.outputs[0], gout.inputs[0])
    ng["wd_lt_pattern"] = list(pattern)
    ng["wd_lt_ver"] = LT_GROUP_VER
    for i, nd in enumerate(nodes):
        nd.location = (200.0 * (i % 8), -150.0 * (i // 8))


def _lt_group_ok(key):
    ng = bpy.data.node_groups.get(GROUP_PREFIX + NAMES[key])
    if (ng is not None and ng.bl_idname == 'GeometryNodeTree' and list(ng.get("wd_lt_pattern", [])) == list(PATTERN[key])
            and ng.get("wd_lt_ver", 1) == LT_GROUP_VER):
        return ng
    return None


def _lt_push_later():
    """Les groupes de nœuds viennent d'être créés : un pas d'annulation les enregistre dès que la main est rendue.
    (Blender plante si l'on annule vers un état d'avant leur création alors que plusieurs objets les utilisent.)"""
    def push():
        try:
            bpy.ops.ed.undo_push(message="Linetypes")
        except (RuntimeError, AttributeError):
            pass
        return None
    try:
        bpy.app.timers.register(push, first_interval=0.0)
    except (RuntimeError, ValueError, AttributeError):
        pass


def lt_groups_ensure():
    """Crée (ou remet à jour) d'un coup les groupes de nœuds de tous les types de ligne. True si quelque chose a été créé."""
    made = False
    for key, _n, _d, pattern in LINETYPES:
        if not pattern or key in _LT_BROKEN or _lt_group_ok(key) is not None:
            continue
        name = GROUP_PREFIX + NAMES[key]
        ng = bpy.data.node_groups.get(name)
        if ng is None or ng.bl_idname != 'GeometryNodeTree':
            ng = bpy.data.node_groups.new(name, 'GeometryNodeTree')
        try:
            _build_group(ng, pattern)
            made = True
        except Exception as ex:         # version de Blender dont les nœuds diffèrent : pas de tirets à l'écran, rien de cassé
            _LT_BROKEN.add(key)
            print("Wanderer: linetype display not available in this Blender version:", repr(ex)[:200])
            try:
                bpy.data.node_groups.remove(ng)
            except (RuntimeError, ReferenceError):
                pass
    if made:
        _lt_push_later()
    return made


def lt_group(key):
    """Groupe de nœuds d'un type de ligne (tous sont créés au premier besoin, en une fois)."""
    if not PATTERN.get(key):
        return None
    ng = _lt_group_ok(key)
    if ng is None and key not in _LT_BROKEN:
        lt_groups_ensure()
        ng = _lt_group_ok(key)
    return ng


def lt_update_scale(scene=None):
    """Échelle des types de ligne changée : tous les tirets du modèle suivent."""
    k = lt_scale(scene)
    for ng in bpy.data.node_groups:
        if ng.name.startswith(GROUP_PREFIX):
            nd = ng.nodes.get("wd_lt_scale")
            if nd is not None and abs(nd.outputs[0].default_value - k) > 1e-12:
                nd.outputs[0].default_value = k


def lt_apply(o, cmap=None):
    """Pose, change ou retire le modificateur du type de ligne de l'objet selon son type de ligne (ou celui de son calque)."""
    try:
        mods = [md for md in o.modifiers if is_lt_mod(md)]
    except (AttributeError, ReferenceError):
        return False
    key = lt_effective(o, cmap) if lt_eligible(o) else 'CONTINUOUS'
    if key == 'CONTINUOUS' or not PATTERN.get(key):
        for md in mods:
            o.modifiers.remove(md)
        return bool(mods)
    ng = lt_group(key)
    if ng is None:
        return False
    md = mods[0] if mods else None
    for extra in mods[1:]:
        o.modifiers.remove(extra)
    if md is None:
        md = o.modifiers.new(LT_MOD, 'NODES')
        md.show_in_editmode = True
        md.show_on_cage = False
    if md.node_group != ng:
        md.node_group = ng
    md.show_expanded = False
    return True


def lt_apply_objects(objs, cmap=None):
    n = 0
    objs = list(objs)
    if cmap is None and len(objs) > 8:
        cmap = object_collections_map()
    for o in objs:
        try:
            if lt_apply(o, cmap):
                n += 1
        except (RuntimeError, ReferenceError, AttributeError, TypeError):
            continue
    return n


def lt_needs_sync(o, cmap=None):
    """L'objet n'a pas le modificateur que demande son type de ligne (objet neuf, déplacé de calque hors de Wanderer)."""
    lt = has_lt(o)
    if not lt_eligible(o):
        return lt
    try:
        if not lt and not o.get("wd_lt") and not _ANY_LAYER_LT[0]:
            return False            # aucun calque à tirets dans le fichier : rien à poser (le cas courant, sans recherche)
    except (AttributeError, ReferenceError):
        return False
    key = lt_effective(o, cmap)
    want = key != 'CONTINUOUS' and bool(PATTERN.get(key))
    if want != lt:
        return True
    if want:
        md = next((m for m in o.modifiers if is_lt_mod(m)), None)
        return md is None or md.node_group is None or md.node_group.name != GROUP_PREFIX + NAMES[key]
    return False


_ANY_LAYER_LT = [True]


def layers_linetype_scan():
    """Y a-t-il un calque avec un type de ligne ? (relu avant un passage sur tous les objets)"""
    try:
        _ANY_LAYER_LT[0] = any(getattr(c.dessin_layer, "linetype", 'CONTINUOUS') != 'CONTINUOUS' for c in bpy.data.collections)
    except (AttributeError, ReferenceError, RuntimeError):
        _ANY_LAYER_LT[0] = True
    return _ANY_LAYER_LT[0]


def lt_suspend(context, objs):
    """Coupe l'affichage en tirets des objets, le temps de lire leur forme évaluée entière (mesure, tubes sur des
    courbes...). Retourne ce qu'il faut passer à lt_resume."""
    mods = []
    for o in objs:
        try:
            for md in o.modifiers:
                if is_lt_mod(md) and md.show_viewport:
                    md.show_viewport = False
                    mods.append(md)
        except (AttributeError, ReferenceError):
            continue
    if mods:
        try:
            context.view_layer.update()
        except (AttributeError, RuntimeError):
            pass
    return mods


def lt_resume(mods):
    for md in mods or ():
        try:
            md.show_viewport = True
        except (AttributeError, ReferenceError):
            pass


def base_wire_world(o):
    """(sommets monde (n,3), arêtes (m,2)) du trait entier d'un objet à tirets (sans son modificateur), ou None."""
    import numpy as np
    try:
        if o.type == 'MESH':
            me = o.data
            nv, ne = len(me.vertices), len(me.edges)
            if not nv or not ne:
                return None
            co = np.empty(nv * 3, dtype=np.float32)
            me.vertices.foreach_get('co', co)
            ed = np.empty(ne * 2, dtype=np.int32)
            me.edges.foreach_get('vertices', ed)
            mw = np.array(o.matrix_world, dtype=np.float64)
            return co.reshape(-1, 3).astype(np.float64) @ mw[:3, :3].T + mw[:3, 3], ed.reshape(-1, 2)
        if o.type == 'CURVE':
            from .trim import wire_graph
            g = wire_graph(o, bpy.context.evaluated_depsgraph_get())
            if g is None:
                return None
            V = np.array([tuple(v) for v in g[0]], dtype=np.float64).reshape(-1, 3)
            E = np.array(g[1], dtype=np.int64).reshape(-1, 2)
            return V, E
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
        return None
    return None


def _touch_layouts(context):
    """Les mises en page relisent le modèle (leurs tirets suivent)."""
    try:
        from .layout import model_touch, print_styles_changed
        model_touch(context.scene)
        print_styles_changed()
    except (ImportError, NameError, RuntimeError, ReferenceError, AttributeError):
        pass


class DESSIN_OT_object_linetype(bpy.types.Operator):
    bl_idname = "dessin.object_linetype"
    bl_label = "Linetype of the Selection"
    bl_description = ("Linetype of the selected curves, whatever their layer, like the linetype of an object in AutoCAD "
                      "(dashes in the 3D views and on the printed layouts). By Layer: they follow their layer again")
    bl_options = {'REGISTER', 'UNDO'}

    linetype: bpy.props.EnumProperty(name="Linetype", items=OBJECT_LINETYPE_ITEMS, default='BYLAYER')

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and bool(context.selected_objects)

    def execute(self, context):
        n = 0
        for o in context.selected_objects:
            if not lt_eligible(o):
                continue
            if self.linetype == 'BYLAYER':
                if "wd_lt" in o.keys():
                    del o["wd_lt"]
            else:
                o["wd_lt"] = self.linetype
            lt_apply(o)
            n += 1
        _touch_layouts(context)
        if not n:
            self.report({'INFO'}, "Linetypes apply to curves and lines (select some)")
            return {'CANCELLED'}
        self.report({'INFO'}, f"Linetype of {n} object(s): {'By Layer' if self.linetype == 'BYLAYER' else NAMES[self.linetype]}")
        return {'FINISHED'}


def selection_linetype(context):
    """Texte du bouton de type de ligne de la sélection : « By Layer », « Dashed » ou « Mixed »."""
    try:
        vals = {o.get("wd_lt") or 'BYLAYER' for o in context.selected_objects if lt_eligible(o)}
    except (AttributeError, ReferenceError):
        return "By Layer"
    if len(vals) > 1:
        return "Mixed"
    v = next(iter(vals), 'BYLAYER')
    return "By Layer" if v == 'BYLAYER' else NAMES.get(v, v)


class DESSIN_MT_ctx_linetype(bpy.types.Menu):
    bl_idname = "DESSIN_MT_ctx_linetype"
    bl_label = "Linetype"

    def draw(self, context):
        layout = self.layout
        cur = {o.get("wd_lt") or 'BYLAYER' for o in context.selected_objects if lt_eligible(o)}
        for ident, name, _desc in OBJECT_LINETYPE_ITEMS:
            layout.operator(DESSIN_OT_object_linetype.bl_idname, text=name,
                            icon='LAYER_ACTIVE' if cur == {ident} else 'BLANK1').linetype = ident


def ctx_linetype_item(layout, context):
    """« Linetype » dans le menu du clic droit quand la sélection contient des courbes ou des lignes."""
    if context.mode == 'OBJECT' and any(lt_eligible(o) for o in context.selected_objects):
        layout.menu(DESSIN_MT_ctx_linetype.bl_idname, icon='IPO_LINEAR')
        return True
    return False


def dash_pattern_paths(paths, pattern, scale=1.0):
    """Découpe des polylignes 2D [(points, fermé)] selon un motif (tiret, espace, ...) en mm × scale."""
    import numpy as np
    pat = [max(float(x) * scale, 1e-6) for x in pattern]
    if not pat:
        return paths
    out = []
    for P, closed in paths:
        seq = [tuple(p) for p in np.asarray(P, dtype=np.float64)]
        if closed and seq:
            seq.append(seq[0])
        if len(seq) < 2:
            continue
        k, left = 0, pat[0]
        drawing = True
        cur = [seq[0]]
        for a, b in zip(seq, seq[1:]):
            ln = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
            if ln <= 1e-12:
                continue
            t = 0.0
            while ln - t > left:
                t += left
                p = (a[0] + (b[0] - a[0]) * t / ln, a[1] + (b[1] - a[1]) * t / ln)
                if drawing:
                    cur.append(p)
                    if len(cur) >= 2:
                        out.append((np.array(cur), False))
                    cur = []
                else:
                    cur = [p]
                drawing = not drawing
                k = (k + 1) % len(pat)
                left = pat[k]
            left -= ln - t
            if drawing:
                cur.append(b)
        if drawing and len(cur) >= 2:
            out.append((np.array(cur), False))
    return out


def _late_imports():
    pass
