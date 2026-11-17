# Ortho (F8) / Polar (F10) et coin opposé : Plane, Rectangle, Box... restent libres (comme Rhino), la polyligne suit toujours Ortho.
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE, 'harness.py')).read())
exec(open(_os.path.join(_HERE, 'prec_lib.py')).read())
BC = bpy.context
st = BC.scene.dessin
SEC = "Ortho"
def chk(name, ok, meas=""): rec(SEC, name, ok, meas)
def run(cls, clicks, move_to):
    clear()
    o = make(cls); sx, sy = scr(*clicks[0]); type(o).invoke(o, ctx, ev('NONE', 'NOTHING', sx, sy))
    for (x, y) in clicks:
        sx, sy = scr(x, y)
        for e in (ev('MOUSEMOVE', 'NOTHING', sx, sy), ev('LEFTMOUSE', 'PRESS', sx, sy), ev('LEFTMOUSE', 'RELEASE', sx, sy)):
            type(o).modal(o, ctx, e)
    sx, sy = scr(*move_to); type(o).modal(o, ctx, ev('MOUSEMOVE', 'NOTHING', sx, sy))
    cur = o.cur.copy() if o.cur is not None else None
    for e in (ev('LEFTMOUSE', 'PRESS', sx, sy), ev('LEFTMOUSE', 'RELEASE', sx, sy)):
        type(o).modal(o, ctx, e)
    return o, cur
for ortho, polar in ((True, False), (False, True)):
    st.ortho, st.polar = ortho, polar
    SEC = "Ortho" if ortho else "Polar"
    for cls, name in ((m.DESSIN_OT_plan, "Plane"), (m.DESSIN_OT_rectangle, "Rectangle")):
        n0 = len(bpy.data.objects)
        o, cur = run(cls, [(0, 0)], (5, 3))
        chk(f"{name} : le coin opposé reste où est la souris (5, 3), pas ramené sur un axe ; l'objet est créé",
            cur is not None and abs(cur.x - 5) < 0.3 and abs(cur.y - 3) < 0.3 and len(bpy.data.objects) > 0, cur)
    o, cur = run(m.DESSIN_OT_boite, [(0, 0)], (5, 3))
    chk("Box : le coin opposé de la base est libre aussi", cur is not None and abs(cur.x - 5) < 0.3 and abs(cur.y - 3) < 0.3, cur)
st.ortho, st.polar = True, False
SEC = "Ortho"
o, cur = run(m.DESSIN_OT_polyligne, [(0, 0)], (5, 1))
chk("Polyline : Ortho s'applique toujours (point ramené sur l'axe X)", cur is not None and abs(cur.y) < 1e-6 and abs(cur.x - 5) < 0.3, cur)
st.ortho = False
summary()
