# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 pierr3 and ToLiss FAP contributors
"""Downloads the CC0 material scans used for surface detail in the FAP hardware textures
from ambientCG (https://ambientcg.com, all assets CC0 1.0) into build/cc0/<asset>/.
Only the colour and normal maps are used, and only as fine grain: tools/gen_hw_tex.py
takes their luminance variation and normals, not their colours.

usage: python tools/fetch_cc0_textures.py
"""
import io
import json
import os
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "build", "cc0")
ASSETS = {
    "Plastic010": "light grey moulded plastic -> bezel, keys, grip",
    "Plastic006": "black plastic -> door keypad body",
    "Plastic011": "dark grey plastic -> key strip plate",
}
UA = {"User-Agent": "ToLissFAP-asset-build"}


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return r.read()


def main():
    os.makedirs(OUT, exist_ok=True)
    for aid, use in ASSETS.items():
        dst = os.path.join(OUT, aid)
        if os.path.isdir(dst) and any(f.endswith("_Color.jpg") for f in os.listdir(dst)):
            print(f"{aid}: already there")
            continue
        info = json.loads(get(f"https://ambientcg.com/api/v2/full_json?id={aid}&include=downloadData"))
        dl = info["foundAssets"][0]["downloadFolders"]["default"]["downloadFiletypeCategories"]["zip"]["downloads"]
        link = next(d["downloadLink"] for d in dl if d["attribute"] == "1K-JPG")
        with zipfile.ZipFile(io.BytesIO(get(link))) as z:
            os.makedirs(dst, exist_ok=True)
            for n in z.namelist():
                if n.endswith(("_Color.jpg", "_NormalGL.jpg")):
                    with open(os.path.join(dst, os.path.basename(n)), "wb") as f:
                        f.write(z.read(n))
        print(f"{aid}: downloaded ({use})")


if __name__ == "__main__":
    main()
