import os as _os; _HERE = _os.path.dirname(_os.path.abspath(__file__)); _SRC = _os.environ.get('WANDERER_SRC') or _os.path.join(_HERE, '..', 'wanderer_cad', '__init__.py')
exec(open(_os.path.join(_HERE,'render_bars.py')).read())
# Bulle de saisie d'une valeur (Gumball) : dessinée dans le style des barres, près de la poignée, sans sortir de la vue
res=[]
def chk(n,ok,info=""): res.append(bool(ok)); print(("OK  " if ok else "BAD ")+n, info)
install()
region.width = 1000; region.height = 700
def paint(anchor, text="25"):
    del OPS[:]
    m._VBUBBLE.update(area=area.as_pointer(), data=(anchor, [("Distance to move in ", None, False), ("Y", (0.35, 0.85, 0.2, 1.0), True)], text))
    CL.value_bubble_draw()
    return list(OPS)
ops = paint((500, 350))
texts = [o for o in ops if o[0] == "text"]
tris = [o for o in ops if o[0] == "TRIS"]
chk("la question et la valeur sont écrites (sans unité)", [t[3] for t in texts] == ["Distance to move in ", "Y", "25"], [t[3] for t in texts])
chk("Y en gras, dans la couleur de l'axe", texts[1][6] and abs(texts[1][5][1] - 0.85) < 1e-6)
xs = [p[0] for o in tris for p in o[1]]; ys = [p[1] for o in tris for p in o[1]]
chk("bulle à droite de la poignée, sa pointe la touche presque", min(xs) > 500 and min(xs) < 515, (round(min(xs)), round(max(xs))))
ops = paint((990, 690))
xs = [p[0] for o in ops if o[0] == "TRIS" for p in o[1]]; ys = [p[1] for o in ops if o[0] == "TRIS" for p in o[1]]
chk("près du bord droit en haut : la bulle passe à gauche et reste dans la vue", max(xs) < 990 and max(ys) <= 700 and min(xs) > 0, (round(min(xs)), round(max(xs)), round(max(ys))))
# aperçu (pour l'œil) : écrit dans le dossier donné par WD_PREVIEW
out = _os.environ.get("WD_PREVIEW")
if out:
    from PIL import Image, ImageDraw, ImageFont
    ops = paint((300, 200)); S = 3; H = 400
    im = Image.new("RGB", (700 * S, H * S), (128, 128, 128)); d = ImageDraw.Draw(im, "RGBA")
    for o in ops:
        if o[0] == "TRIS":
            c = tuple(int(v * 255) for v in o[2][:3]) + (int(o[2][3] * 255),)
            for i in range(0, len(o[1]) - 2, 3):
                d.polygon([(x * S, (H - y) * S) for x, y in o[1][i:i + 3]], fill=c)
        else:
            f = ImageFont.truetype("/usr/share/fonts/opentype/inter/Inter-%s.otf" % ("Bold" if o[6] else "Regular"), int(o[4] * S))
            d.text((o[1] * S, (H - o[2]) * S), o[3], font=f, fill=tuple(int(v * 255) for v in o[5][:3]), anchor="ls")
    im.save(out)
print("RESULTAT", sum(res), "/", len(res))
