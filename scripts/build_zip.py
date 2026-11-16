"""Builds the installable extension zip: python scripts/build_zip.py  ->  dist/wanderer-<version>.zip"""
import os
import re
import zipfile

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = os.path.join(root, "wanderer_cad")
with open(os.path.join(src, "blender_manifest.toml"), encoding="utf-8") as f:
    version = re.search(r'^version\s*=\s*"([^"]+)"', f.read(), re.M).group(1)
os.makedirs(os.path.join(root, "dist"), exist_ok=True)
out = os.path.join(root, "dist", f"wanderer-{version}.zip")
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    # le paquet : __init__.py, ses modules (un par famille d'outils) et le manifeste
    for name in sorted(os.listdir(src)):
        if name.endswith(".py") or name == "blender_manifest.toml":
            z.write(os.path.join(src, name), name)
print("Built", out)

# Thèmes : une seule extension de type « theme » avec les six thèmes (règle de la plateforme d'extensions : pas de thème
# dans l'add-on). Même fichier sur GitHub (à côté de l'add-on, dans chaque release) et sur extensions.blender.org.
# Blender liste chaque fichier .xml dans Preferences > Themes et applique le premier à l'installation.
THEME_VERSION = "1.0.0"
tdir = os.path.join(root, "themes")
manifest = f"""schema_version = "1.0.0"

id = "wanderer_themes"
version = "{THEME_VERSION}"
name = "Wanderer Themes"
tagline = "Six CAD themes for Blender: three dark, three light"
maintainer = "Hostylmatic / OZLUK Tolga"
type = "theme"
website = "https://github.com/Impressivetravel/wanderer-cad"

tags = ["Dark", "Light"]

blender_version_min = "4.2.0"

license = ["SPDX:GPL-3.0-or-later"]
copyright = ["2026 Hostylmatic / OZLUK Tolga"]
"""
tout = os.path.join(root, "dist", f"wanderer_themes-{THEME_VERSION}.zip")
with zipfile.ZipFile(tout, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("blender_manifest.toml", manifest)
    for name in sorted(os.listdir(tdir)):
        if name.endswith(".xml"):
            z.write(os.path.join(tdir, name), name)
print("Built", tout)
