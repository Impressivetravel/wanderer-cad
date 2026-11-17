import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
# CPlane posé sur une face à la main : il reste en place, Auto CPlane s'efface (retour rajq123)
res=[]
def chk(n,ok,info=""): res.append(bool(ok)); print(("OK  " if ok else "BAD ")+n, info)
st=bpy.context.scene.dessin
op=make(m.DESSIN_OT_cplane); op.area=area; op.rv3d=rv3d
fr=m.cp_frame(Vector((0,0,1)),Vector((1,0,0)),Vector((0,1,0)))
st.auto_cplane=True
op.done(ctx, fr, "CPlane: aligned with the face")
cs=m.cp_state(rv3d)
chk("le plan posé à la main reste, Auto CPlane éteint", st.auto_cplane is False and cs["cur"] is not None and not cs.get("auto"), (st.auto_cplane, cs.get("auto")))
st.auto_cplane=True
op.done(ctx, None, "CPlane: world plane")
chk("retour au plan du monde (W) : Auto CPlane inchangé", st.auto_cplane is True, st.auto_cplane)
st.auto_cplane=False
op.done(ctx, fr, "CPlane: aligned with the face")
chk("Auto CPlane déjà éteint : rien ne change", st.auto_cplane is False)
print("RESULTAT",sum(res),"/",len(res))
