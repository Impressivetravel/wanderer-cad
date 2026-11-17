import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
# Panneau Wanderer > Tools : groupes dépliés par défaut, boutons « tout déplier / tout plier »
res=[]
def chk(n,ok,info=""): res.append(bool(ok)); print(("OK  " if ok else "BAD ")+n, info)
st=bpy.context.scene.dessin
n=len(m.tool_families())
chk(f"assez d'états pour les {n} groupes", n<=m.TOOLBOX_GROUPS, (n, m.TOOLBOX_GROUPS))
chk("dépliés par défaut", all(getattr(st,f"tb_open_{i}") for i in range(m.TOOLBOX_GROUPS)))
r=bpy.ops.dessin.toolbox_fold(open=False)
chk("tout plier", r=={'FINISHED'} and not any(getattr(st,f"tb_open_{i}") for i in range(m.TOOLBOX_GROUPS)), r)
st.tb_open_3=True
r=bpy.ops.dessin.toolbox_fold(open=True)
chk("tout déplier", all(getattr(st,f"tb_open_{i}") for i in range(m.TOOLBOX_GROUPS)))
print("RESULTAT",sum(res),"/",len(res))
