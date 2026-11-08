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
    for name in ("__init__.py", "blender_manifest.toml"):
        z.write(os.path.join(src, name), name)
    themes = os.path.join(src, "themes")
    for name in sorted(os.listdir(themes)):
        if name.endswith(".xml"):
            z.write(os.path.join(themes, name), "themes/" + name)
print("Built", out)
