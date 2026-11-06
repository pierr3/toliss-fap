# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 pierr3 and ToLiss FAP contributors
"""Draws the FAP hardware textures (2048 x 2048, atlas layout from build_fap_hw.ATLAS):
  obj/fap_hw.png      albedo + alpha (decals, clear key cover, contact shadow)
  obj/fap_hw_LIT.png  lighting: body at cabin-light level, backlit key/keypad legends
  obj/fap_hw_NML.png  normal map (R,G = normal, B = 255, A = specular level)

Surface detail comes from CC0 ambientCG scans (tools/fetch_cc0_textures.py), used only as
grain (luminance variation + normals) on top of our own colours. Ambient occlusion comes
from tools/bake_fap_ao.py. Both are optional: without them, procedural noise and a
blurred-mask shadow are used instead.

usage: python tools/gen_hw_tex.py      (needs Pillow and numpy)
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import build_fap_hw as hw  # noqa: E402  (layout: ATLAS, TEX_PX, geometry for the fallback shadow)

N = hw.TEX_PX
F = N / 1024.0
CC0 = os.path.join(ROOT, "build", "cc0")
AO_PNG = os.path.join(ROOT, "build", "bake", "ao.png")
rng = np.random.default_rng(7)

day = np.zeros((N, N, 4), np.float32)       # RGBA 0..1
lit = np.zeros((N, N, 3), np.float32)
nml = np.zeros((N, N, 3), np.float32); nml[..., 2] = 1
spec = np.full((N, N), 60.0, np.float32)


def px(name):
    x0, y0, x1, y1 = hw.ATLAS[name] if isinstance(name, str) else name
    return int(round(x0 * F)), int(round(y0 * F)), int(round(x1 * F)), int(round(y1 * F))


def rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)], np.float32)


def fill(name, col, a=1.0):
    x0, y0, x1, y1 = px(name)
    day[y0:y1, x0:x1, :3] = rgb(col)
    day[y0:y1, x0:x1, 3] = a


def grad(name, top, bot, a=1.0):
    x0, y0, x1, y1 = px(name)
    t = np.linspace(0, 1, y1 - y0, dtype=np.float32)[:, None, None]
    day[y0:y1, x0:x1, :3] = rgb(top) * (1 - t) + rgb(bot) * t
    day[y0:y1, x0:x1, 3] = a


def edge(name, light, dark, w):
    """Painted bevel: light top/left, dark bottom/right (w in 1024-units)."""
    x0, y0, x1, y1 = px(name)
    w = max(1, int(w * F))
    for (sl, col, a) in (((slice(y0, y0 + w), slice(x0, x1)), light, 0.45), ((slice(y0, y1), slice(x0, x0 + w)), light, 0.32),
                         ((slice(y1 - w, y1), slice(x0, x1)), dark, 0.5), ((slice(y0, y1), slice(x1 - w, x1)), dark, 0.38)):
        day[sl][..., :3] = day[sl][..., :3] * (1 - a) + rgb(col) * a


def cc0(asset, kind, w, h, scale=1.0):
    """w x h crop of an ambientCG map (tiled, scaled), float 0..1, or None if not downloaded."""
    p = os.path.join(CC0, asset, f"{asset}_1K-JPG_{kind}.jpg")
    if not os.path.exists(p):
        return None
    im = Image.open(p).convert("RGB")
    if scale != 1.0:
        im = im.resize((max(8, int(im.width * scale)), max(8, int(im.height * scale))), Image.BICUBIC)
    a = np.asarray(im, np.float32) / 255
    reps = (h // a.shape[0] + 1, w // a.shape[1] + 1, 1)
    return np.tile(a, reps)[:h, :w]


def grain(name, asset, amp, normal_strength, sp, scale=1.0):
    """Luminance grain + normals from a CC0 scan (procedural noise if it is missing); specular level."""
    x0, y0, x1, y1 = px(name)
    w, h = x1 - x0, y1 - y0
    col = cc0(asset, "Color", w, h, scale)
    if col is not None:
        lum = col.mean(axis=2)
        detail = lum / max(lum.mean(), 1e-3) - 1
    else:
        detail = rng.standard_normal((h, w)).astype(np.float32) * 0.04
    day[y0:y1, x0:x1, :3] *= np.clip(1 + amp * detail, 0, 2)[..., None]
    n = cc0(asset, "NormalGL", w, h, scale)
    if n is not None:
        v = n * 2 - 1
    else:
        hgt = rng.standard_normal((h, w)).astype(np.float32)
        gy, gx = np.gradient(hgt)
        v = np.stack([-gx * 0.15, gy * 0.15, np.ones_like(gx)], -1)
    v[..., :2] *= normal_strength
    v /= np.linalg.norm(v, axis=2, keepdims=True)
    nml[y0:y1, x0:x1] = v
    spec[y0:y1, x0:x1] = sp


# ---------------------------------------------------------------- fonts / text
def font(size, narrow=True):
    for f in (["ARIALNB.TTF", "arialnb.ttf"] if narrow else []) + ["arialbd.ttf", "DejaVuSansCondensed-Bold.ttf", "DejaVuSans-Bold.ttf"]:
        for d in ("C:/Windows/Fonts", "/usr/share/fonts/truetype/dejavu", "/Library/Fonts"):
            try:
                return ImageFont.truetype(os.path.join(d, f), size)
            except OSError:
                pass
    return ImageFont.load_default()


def text_mask(txt, name, size, narrow=True, dy=0.0):
    """Float mask (block-sized) of centred multi-line text; size in 1024-units."""
    x0, y0, x1, y1 = px(name)
    im = Image.new("L", (x1 - x0, y1 - y0), 0)
    d = ImageDraw.Draw(im)
    f = font(int(size * F), narrow)
    d.multiline_text(((x1 - x0) / 2, (y1 - y0) / 2 + dy * F), txt, fill=255, font=f, anchor="mm", align="center", spacing=int(1 * F))
    return np.asarray(im, np.float32) / 255


def blur(mask, r):
    im = Image.fromarray((np.clip(mask, 0, 1) * 255).astype(np.uint8))
    return np.asarray(im.filter(ImageFilter.GaussianBlur(r * F)), np.float32) / 255


def over(name, mask, col, a=1.0):
    """Paint col over the day texture through mask (alpha accumulates)."""
    x0, y0, x1, y1 = px(name)
    m = (mask * a)[..., None]
    day[y0:y1, x0:x1, :3] = day[y0:y1, x0:x1, :3] * (1 - m) + rgb(col) * m
    day[y0:y1, x0:x1, 3] = day[y0:y1, x0:x1, 3] * (1 - m[..., 0]) + m[..., 0]


def glow(name, mask, col, core=1.0, halo=0.45, r=1.6):
    x0, y0, x1, y1 = px(name)
    g = np.clip(blur(mask, r) * halo + mask * core, 0, 1)[..., None]
    lit[y0:y1, x0:x1] = np.maximum(lit[y0:y1, x0:x1], rgb(col) * g)


# ---------------------------------------------------------------- body blocks
BEZEL = "#8c9095"            # warm metallic grey of the real bezel
grad("bezelface", "#959a9f", "#85898e"); grain("bezelface", "Plastic010", 0.9, 0.5, 120, 0.5)
fill("bezel", BEZEL);        grain("bezel", "Plastic010", 0.9, 0.5, 120, 0.5)
fill("dark", "#1d1f22");     grain("dark", "Plastic011", 0.4, 0.3, 40)
fill("strip", "#77797d");    grain("strip", "Plastic011", 0.5, 0.4, 60)
grad("grip", "#a6aaae", "#8a8e93"); grain("grip", "Plastic010", 0.8, 0.5, 130, 0.5)
grad("frame", "#85888c", "#74777b"); edge("frame", "#b4b7ba", "#3a3c3f", 5); grain("frame", "Plastic010", 0.6, 0.4, 80, 0.3)
grad("cap", "#6e7175", "#484b4f"); edge("cap", "#9a9da1", "#1d1e20", 7); grain("cap", "Plastic011", 0.5, 0.4, 70, 0.3)
grad("emercap", "#de3127", "#9e140e"); edge("emercap", "#ff9a90", "#4a0805", 7); grain("emercap", "Plastic010", 0.4, 0.4, 110, 0.3)
fill("usb", "#7d8084"); edge("usb", "#b4b7ba", "#3a3c3f", 4)
x0, y0, x1, y1 = hw.ATLAS["usb"]
fill((x0 + 14, y0 + 30, x1 - 14, y1 - 30), "#08090a")               # socket
fill((x0 + 24, y0 + 44, x1 - 24, y0 + 60), "#c3c6c9")               # contact tongue
fill("hole", "#1d1f21")
grad("led", "#5d4a1e", "#2a2008")
grad("kpkey", "#a3a5a7", "#8a8c8e"); grain("kpkey", "Plastic010", 0.5, 0.5, 30, 0.3)
fill("kpbody", "#17181a");   grain("kpbody", "Plastic006", 0.6, 0.4, 50)
grad("keypadface", "#1e1f21", "#17181a"); grain("keypadface", "Plastic006", 0.6, 0.4, 50, 0.4)
fill("coveredge", "#d3dbe1", 0.55); spec[slice(*px("coveredge")[1::2]), slice(*px("coveredge")[0::2])] = 200

# lit copy of the body blocks (cabin lighting), ~40 % of the day colour like ToLiss kitchens_LIT
BODY = ["bezelface", "bezel", "dark", "strip", "grip", "frame", "cap", "emercap", "usb", "hole", "led",
        "kpkey", "kpbody", "keypadface"]
for b in BODY:
    x0, y0, x1, y1 = px(b)
    c = day[y0:y1, x0:x1, :3]
    lum = c.mean(axis=2, keepdims=True)
    lit[y0:y1, x0:x1] = np.clip(c * (0.40 + 0.35 * (1 - lum)) * np.array([1, 1, 0.97], np.float32), 0, 1)

# ---------------------------------------------------------------- ambient occlusion (baked)
if os.path.exists(AO_PNG):
    ao = np.asarray(Image.open(AO_PNG).convert("L").resize((N, N)), np.float32) / 255
    for b in ("bezelface", "keypadface"):
        x0, y0, x1, y1 = px(b)
        a = 0.25 + 0.75 * ao[y0:y1, x0:x1]
        day[y0:y1, x0:x1, :3] *= a[..., None]
        lit[y0:y1, x0:x1] *= a[..., None]
    x0, y0, x1, y1 = px("shadow")
    shadow_a = np.clip((1 - ao[y0:y1, x0:x1]) * 1.05, 0, 0.8)
else:  # fallback: blurred footprint of the bezel + keypad
    x0, y0, x1, y1 = px("shadow")
    w, h = x1 - x0, y1 - y0
    m = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(m)
    sx0, sx1, sy0, sy1 = hw.SH
    for r in (hw.B, hw.KP):
        d.rectangle([(r[0] - sx0) / (sx1 - sx0) * w, (sy1 - r[3]) / (sy1 - sy0) * h,
                     (r[1] - sx0) / (sx1 - sx0) * w, (sy1 - r[2]) / (sy1 - sy0) * h], fill=255)
    shadow_a = blur(np.asarray(m, np.float32) / 255, 6) * 0.55
day[y0:y1, x0:x1, :3] = 0
day[y0:y1, x0:x1, 3] = shadow_a
spec[y0:y1, x0:x1] = 0

# ---------------------------------------------------------------- clear key cover
x0, y0, x1, y1 = px("cover")
h, w = y1 - y0, x1 - x0
yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
sheen = np.exp(-((xx / w - 0.35 - 0.6 * yy / h) ** 2) / 0.004) * 0.16 + np.exp(-((xx / w - 0.70 - 0.6 * yy / h) ** 2) / 0.0015) * 0.10
border = ((xx < 3 * F) | (xx > w - 3 * F) | (yy < 3 * F) | (yy > h - 3 * F)).astype(np.float32) * 0.25
day[y0:y1, x0:x1, :3] = rgb("#e4ecf2")
day[y0:y1, x0:x1, 3] = np.clip(0.07 + sheen + border, 0, 1)
spec[y0:y1, x0:x1] = 230

# ---------------------------------------------------------------- EMER legend (red lens, white text)
grad("emerdecal", "#c8261c", "#8e130d")
edge("emerdecal", "#ff8a80", "#3a0604", 5)
m = text_mask("EMER", "emerdecal", 54)
over("emerdecal", m, "#f4f1f0", 0.95)
x0, y0, x1, y1 = px("emerdecal")
lit[y0:y1, x0:x1] = rgb("#ff2a14") * 0.55
glow("emerdecal", m, "#ffffff", core=1.0, halo=0.35)

# ---------------------------------------------------------------- key legends: coloured backlit lenses
# As on the real panel, the function keys glow in their colour whenever the aircraft is powered
# (LIGHTS green, the others red); toliss_fap/key_light raises them to full brightness when active.
KEYS = ["", "LIGHTS\nMAIN\nON/OFF", "LAV\nMAINT", "SCREEN\n30 sec\nLOCK", "EVAC\nCMD", "EVAC\nRESET", "SMOKE\nRESET", ""]
COLS = ["", "#a6ff3c", "#ff3a2a", "#ff3a2a", "#ff3a2a", "#ff3a2a", "#ff3a2a", ""]
for k, txt in enumerate(KEYS):
    if not txt:
        continue
    name = f"key{k}"
    c = rgb(COLS[k])
    lens_top = "#%02x%02x%02x" % tuple(int(v * 255 * 0.42 + 18) for v in c)
    lens_bot = "#%02x%02x%02x" % tuple(int(v * 255 * 0.30 + 10) for v in c)
    grad(name, lens_top, lens_bot)
    edge(name, "#ffffff", "#000000", 3)
    m = text_mask(txt, name, 24)
    over(name, m, "#%02x%02x%02x" % tuple(int(min(255, v * 255 * 0.55 + 95)) for v in c), 0.95)
    x0, y0, x1, y1 = px(name)
    lit[y0:y1, x0:x1] = c * 0.62
    glow(name, m, "#%02x%02x%02x" % tuple(int(min(255, v * 255 * 0.6 + 100)) for v in c), core=1.0, halo=0.4)
    spec[y0:y1, x0:x1] = 120

# ---------------------------------------------------------------- keypad digits (dark print, backlit white)
for i, lab in enumerate(hw.KP_LABELS):
    name = f"kp{i}"
    m = text_mask(lab, name, 30, narrow=False, dy=(3 if lab == "*" else 0))
    x0, y0, x1, y1 = px(name)
    day[y0:y1, x0:x1, :3] = rgb("#1b1c1e")
    day[y0:y1, x0:x1, 3] = m * 0.95
    glow(name, m, "#dfe6ea", core=0.9, halo=0.3, r=1.0)

# ---------------------------------------------------------------- write
def save(arr, path, mode):
    Image.fromarray((np.clip(arr, 0, 1) * 255 + 0.5).astype(np.uint8), mode).save(path, optimize=True)


obj = os.path.join(ROOT, "obj")
save(day, os.path.join(obj, "fap_hw.png"), "RGBA")
save(lit, os.path.join(obj, "fap_hw_LIT.png"), "RGB")
n = np.zeros((N, N, 4), np.float32)
n[..., 0] = nml[..., 0] * 0.5 + 0.5
n[..., 1] = nml[..., 1] * 0.5 + 0.5
n[..., 2] = 1
n[..., 3] = spec / 255
save(n, os.path.join(obj, "fap_hw_NML.png"), "RGBA")
print(f"wrote obj/fap_hw.png, fap_hw_LIT.png, fap_hw_NML.png ({N}x{N}); "
      f"CC0 grain: {'yes' if os.path.isdir(CC0) else 'no (procedural)'}; AO: {'baked' if os.path.exists(AO_PNG) else 'fallback'}")
