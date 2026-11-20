import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'harness.py')).read())
# Icônes de la barre d'outils : le nom du fichier change avec le dessin (Blender garde une icône en mémoire sous son nom
# jusqu'au redémarrage : sans cela une icône redessinée n'apparaît qu'après avoir relancé Blender).
import tempfile, zlib
res=[]
def chk(name,ok,info=""):
    res.append(bool(ok)); print(("OK  " if ok else "BAD ")+name, info)
d=tempfile.mkdtemp()
orig_up=bpy.utils.user_resource; orig_ext=getattr(bpy.utils,"extension_path_user",None)
bpy.utils.extension_path_user=lambda *a,**k: d
try:
    p1=m.ensure_icon("walk","x")
    f1=sorted(_os.listdir(d))
    chk("une icône écrite, son nom porte l'empreinte du dessin", len(f1)==1 and f1[0].startswith("walk") and _os.path.basename(p1)+".dat"==f1[0] and _os.path.basename(p1)[-8:]=="%08x"%(zlib.crc32(open(p1+".dat","rb").read())&0xFFFFFFFF), f1)
    p1b=m.ensure_icon("walk","x")
    chk("même dessin : même fichier, rien de réécrit", p1b==p1 and sorted(_os.listdir(d))==f1)
    old=m.ICON_SVG["walk"]
    open(_os.path.join(d,"walk"+m.icon_suffix()+".dat"),"wb").write(b"ancien")            # fichier d'une version d'avant
    open(_os.path.join(d,"walkabout"+m.icon_suffix()+"_0000abcd.dat"),"wb").write(b"autre")  # autre icône au nom voisin
    m.ICON_SVG["walk"]='<circle class="af" cx="12" cy="12" r="6"/>'
    try:
        p2=m.ensure_icon("walk","x")
    finally:
        m.ICON_SVG["walk"]=old
    f2=sorted(_os.listdir(d))
    chk("dessin changé : nouveau nom de fichier (Blender le relit tout de suite)", p2!=p1 and _os.path.exists(p2+".dat"), (p1,p2))
    chk("... les anciens fichiers de cette icône sont supprimés, pas ceux des autres icônes", not _os.path.exists(p1+".dat") and not _os.path.exists(_os.path.join(d,"walk"+m.icon_suffix()+".dat"))
        and _os.path.exists(_os.path.join(d,"walkabout"+m.icon_suffix()+"_0000abcd.dat")), f2)
    p3=m.ensure_icon("walk","x")
    chk("retour au dessin d'origine : le nom d'origine", p3==p1, (p1,p3))
finally:
    if orig_ext is not None: bpy.utils.extension_path_user=orig_ext
tt=m.RHINO_TOOLS["nav"][0]
chk("l'outil Walk utilise un fichier d'icône à empreinte", tt.bl_icon.split("_")[-1].isalnum() and len(tt.bl_icon.split("_")[-1])==8, tt.bl_icon)
print("RESULTAT",sum(res),"/",len(res))
