# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 pierr3 and ToLiss FAP contributors
"""Normal map for the FAP hardware (obj/fap_hw_NML.png, 1024x1024, same atlas as
gen_hw_tex.ps1): orange-peel plastic on the module, brushed grain on the metal bezel,
fine grain on the key strip / caps / frames, flat elsewhere.
Channels (X-Plane classic normal map): R,G = normal X,Y; B = 255; A = specular level."""
import os
import struct
import zlib

import numpy as np

S = 1024
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rng = np.random.default_rng(11)


def blur(a, r):
    if r <= 0:
        return a
    k = np.exp(-0.5 * (np.arange(-3 * r, 3 * r + 1) / r) ** 2)
    k /= k.sum()
    a = np.apply_along_axis(lambda v: np.convolve(np.pad(v, 3 * r, mode="wrap"), k, "valid"), 1, a)
    return np.apply_along_axis(lambda v: np.convolve(np.pad(v, 3 * r, mode="wrap"), k, "valid"), 0, a)


def surface(kind, w, h):
    """Height field for a block."""
    n = rng.standard_normal((h, w))
    if kind == "peel":        # moulded plastic: very fine stipple only (1 texel ~ 2 mm on the module)
        return n * 0.30
    if kind == "brushed":     # brushed metal: long horizontal streaks
        streak = blur(rng.standard_normal((h, 1)).repeat(w, 1), 1)
        return streak * 0.8 + blur(n, 1) * 0.15
    if kind == "grain":       # fine texture on smaller plastic parts
        return n * 0.30
    return np.zeros((h, w))


# block -> (x0, y0, x1, y1, surface, specular 0..255); must match gen_hw_tex.ps1
BLOCKS = [
    (0, 0, 256, 256, "peel", 70), (256, 0, 512, 256, "brushed", 120), (512, 0, 768, 256, "grain", 40),
    (768, 0, 1024, 256, "grain", 60), (0, 256, 256, 384, "grain", 90), (256, 256, 384, 384, "grain", 80),
    (384, 256, 512, 384, "grain", 70), (512, 256, 640, 384, "grain", 110), (640, 256, 768, 384, "flat", 60),
]
height = np.zeros((S, S))
spec = np.full((S, S), 60.0)
strength = np.zeros((S, S))
for x0, y0, x1, y1, kind, sp in BLOCKS:
    height[y0:y1, x0:x1] = surface(kind, x1 - x0, y1 - y0)
    spec[y0:y1, x0:x1] = sp
    strength[y0:y1, x0:x1] = {"peel": 0.9, "brushed": 1.2, "grain": 0.9, "flat": 0}[kind]

gy, gx = np.gradient(height)
nx, ny = -gx * strength, gy * strength          # OpenGL-style (Y up in UV space)
nz = np.ones_like(nx)
ln = np.sqrt(nx ** 2 + ny ** 2 + nz ** 2)
rgba = np.zeros((S, S, 4), np.uint8)
rgba[..., 0] = np.clip((nx / ln * 0.5 + 0.5) * 255, 0, 255)
rgba[..., 1] = np.clip((ny / ln * 0.5 + 0.5) * 255, 0, 255)
rgba[..., 2] = 255
rgba[..., 3] = np.clip(spec, 0, 255)


def write_png(path, img):
    h, w, c = img.shape
    raw = b"".join(b"\x00" + img[y].tobytes() for y in range(h))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


write_png(os.path.join(ROOT, "obj", "fap_hw_NML.png"), rgba)
print("wrote obj/fap_hw_NML.png")
