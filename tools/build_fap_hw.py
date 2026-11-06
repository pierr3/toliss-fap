# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 pierr3 and ToLiss FAP contributors
"""Builds the 3D Flight Attendant Panel hardware, modelled on photos of the A320 CIDS FAP.

The ToLiss model already has the FAP housing (the raised box with the chamfered top-left
corner and the grab handle); only the screen and keys are painted on it. We add, on its
front face:
  - the metal bezel holding the screen and the key strip (EMER, LED, 8 keys, USB),
  - a hinged transparent cover over the key strip (open it to reach the keys),
  - the flight-deck door keypad at the right edge,
  - a soft contact shadow around them (baked ambient occlusion, see tools/bake_fap_ao.py).

Outputs
  obj/fap_hw.obj          visual model (fap_hw.png / _LIT / _NML), attached in the .acf
  obj/fap_screen.obj      screen device quad + invisible click zones (-> cockpit patch)
  build/preview/*         Wavefront copy + layout.json for Blender preview renders
  build/bake/fap_bake.obj bake scene for tools/bake_fap_ao.py

All coordinates are in the ToLiss kitchens.obj frame (x right, y up, z aft; the FAP faces
aft). Both OBJs wrap everything in the same transform as kitchens.obj (static offset +
1-sim/fus fuselage-length keys), so they follow A319/A320/A321 bodies.
"""
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# ---------------------------------------------------------------- layout (metres)
Z_WALL = -0.3738                    # front face of the ToLiss FAP housing (kitchens frame)
HOUSING = (-1.341, -0.485, 1.118, 1.588)   # that face's extent (measured from kitchens.obj)
SX0, SX1, SY0, SY1 = -0.899427, -0.553499, 1.254394, 1.518374   # screen (measured from texture)

D_BEZEL = 0.012                     # bezel protrudes from the housing
ZB = Z_WALL + D_BEZEL               # bezel front plate
ZS = ZB - 0.004                     # screen plane
ZK = ZB - 0.010                     # key strip plane (keys sit in a well under the cover)
EDGE_R = 0.003                      # rounded front edge of the bezel
CORNER_R = 0.010                    # bezel corner radius (in plane)

RIM = 0.005                         # dark rim around the active screen
S = (SX0 - RIM, SX1 + RIM, SY0 - RIM, SY1 + RIM)            # screen well opening
K = (SX0 + 0.004, SX1 - 0.004, SY0 - 0.071, SY0 - 0.021)    # key strip opening
B = (SX0 - 0.022, SX1 + 0.020, K[2] - 0.016, SY1 + 0.022)   # bezel outline

# flight-deck door keypad (right of the bezel, at the housing edge as on the real panel)
KP = (B[1] + 0.011, B[1] + 0.045, SY0 - 0.015, SY1 - 0.061)
D_KP = 0.007
KP_KEYS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "star", "hash"]   # 6 rows x 2
KP_LABELS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "*", "#"]

# transparent key cover
CV = (K[0] + 0.0008, K[1] - 0.0008, K[2] + 0.0008, K[3] - 0.0008)
ZC0, ZC1 = ZB - 0.0022, ZB + 0.0004       # back / front of the sheet
HINGE = "bottom"                           # "bottom": flips down towards you; "top": lifts up
COVER_OPEN_DEG = 100
HINGE_Y = CV[2] if HINGE == "bottom" else CV[3]
HINGE_Z = (ZC0 + ZC1) / 2
COVER_ANGLE = COVER_OPEN_DEG if HINGE == "bottom" else -COVER_OPEN_DEG   # right-hand rule about +x

# key strip contents (left to right)
KEY_W, KEY_PITCH, KEY_DEPTH = 0.020, 0.0275, 0.005
KEYS = [  # (atlas key index, command, tooltip, light index)
    (0, None, None, None),
    (1, "toliss_fap/key/lights", "FAP: LIGHTS MAIN ON/OFF", 1),
    (2, "toliss_fap/key/lav_maint", "FAP: LAV MAINT", 2),
    (3, "toliss_fap/key/screen_lock", "FAP: SCREEN 30 sec LOCK", 3),
    (4, "toliss_fap/key/evac_cmd", "FAP: EVAC CMD", 4),
    (5, "toliss_fap/key/evac_reset", "FAP: EVAC RESET", 5),
    (6, "toliss_fap/key/smoke_reset", "FAP: SMOKE RESET", 6),
    (7, None, None, None),
]

# contact shadow decal on the housing face, around the bezel and keypad
SH = (B[0] - 0.035, min(KP[1] + 0.006, HOUSING[1] - 0.001), B[2] - 0.030, B[3] + 0.030)

# ---------------------------------------------------------------- texture atlas
# Coordinates are in 1024-units; the textures are TEX_PX square (2x), see tools/gen_hw_tex.py.
TEX_PX = 2048
TEX = 1024.0
ATLAS = {
    "bezelface": (4, 4, 252, 252),       # unique planar map of the bezel front (AO baked in)
    "bezel": (264, 8, 504, 248), "dark": (520, 8, 760, 248), "strip": (776, 8, 1016, 248),
    "grip": (4, 260, 252, 380), "frame": (256, 256, 384, 384), "cap": (384, 256, 512, 384),
    "emercap": (512, 256, 640, 384), "usb": (640, 256, 768, 384), "hole": (770, 258, 830, 318),
    "led": (834, 258, 894, 318), "kpkey": (898, 258, 958, 318), "coveredge": (962, 258, 1022, 318),
    "kpbody": (770, 322, 1022, 382),
    "emerdecal": (2, 394, 254, 506),
    "keypadface": (944, 392, 1016, 852),  # unique planar map of the keypad front (AO baked in)
    "cover": (4, 644, 252, 764),
    "shadow": (260, 642, 700, 1020),      # contact shadow (alpha baked)
}
for k in range(8):
    ATLAS[f"key{k}"] = (k * 128 + 2, 514, k * 128 + 126, 638)    # key legend decals (backlit)
for i in range(12):
    ATLAS[f"kp{i}"] = (262 + 56 * i, 394, 306 + 56 * i, 450)      # keypad digit decals
BAKED = ("bezelface", "keypadface", "shadow")                     # blocks the AO bake writes
DECALS = ("emerdecal", "cover", "shadow", "bezelface", "keypadface")  # mapped edge to edge

UV_PAD = 10  # px (1024-units) kept clear around solid blocks so mip-mapping cannot bleed


def uv_rect(name):
    if name.endswith(":s"):   # solid: a tiny patch from the block centre (walls, sides, multi-piece plates)
        x0, y0, x1, y1 = ATLAS[name[:-2]]
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        return ((cx - 3) / TEX, 1 - (cy + 3) / TEX, (cx + 3) / TEX, 1 - (cy - 3) / TEX)
    x0, y0, x1, y1 = ATLAS[name]
    if not name.startswith(("key", "kp")) and name not in DECALS:
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        x0, x1 = min(x0 + UV_PAD, cx - 1), max(x1 - UV_PAD, cx + 1)
        y0, y1 = min(y0 + UV_PAD, cy - 1), max(y1 - UV_PAD, cy + 1)
    return (x0 / TEX, 1 - y1 / TEX, x1 / TEX, 1 - y0 / TEX)   # (u0, v0, u1, v1), v up


def planar(name, r):
    """UV function mapping rectangle r = (x0, x1, y0, y1) onto atlas block `name`."""
    u = uv_rect(name)
    return lambda x, y: (u[0] + (x - r[0]) / (r[1] - r[0]) * (u[2] - u[0]),
                         u[1] + (y - r[2]) / (r[3] - r[2]) * (u[3] - u[1]))


# ---------------------------------------------------------------- mesh helpers
class Mesh:
    def __init__(self):
        self.v = []          # (x, y, z, nx, ny, nz, u, v)
        self.groups = []     # (key, [indices]) - consecutive TRIS ranges with attributes

    def _group(self, key):
        if not self.groups or self.groups[-1][0] != key:
            self.groups.append((key, []))
        return self.groups[-1][1]

    def poly(self, pts, normal, uvs, key="cabin", both=False):
        """Fan-triangulated convex polygon; pts and uvs in matching order."""
        base = len(self.v)
        for (x, y, z), (u, v) in zip(pts, uvs):
            self.v.append((x, y, z, *normal, u, v))
        idx = self._group(key)
        for i in range(1, len(pts) - 1):
            tri = (base, base + i, base + i + 1)
            w = self._wind(tri, normal)
            idx += w
            if both:
                idx += [w[0], w[2], w[1]]

    def _wind(self, tri, normal):
        a, b, c = (self.v[i] for i in tri)
        ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
        vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
        cx, cy, cz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
        facing = cx * normal[0] + cy * normal[1] + cz * normal[2]
        # X-Plane OBJ8 front faces are clockwise (as seen from the front)
        return [tri[0], tri[2], tri[1]] if facing > 0 else list(tri)

    def quad(self, p0, p1, p2, p3, normal, uv, key="cabin", both=False):
        u0, v0, u1, v1 = uv
        self.poly([p0, p1, p2, p3], normal, [(u0, v0), (u1, v0), (u1, v1), (u0, v1)], key, both)

    def rect_z(self, x0, x1, y0, y1, z, uvname, key="cabin", normal=(0, 0, 1), both=False):
        self.quad((x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z), normal, uv_rect(uvname), key, both)

    def rect_planar(self, x0, x1, y0, y1, z, uvf, key="cabin"):
        pts = [(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)]
        self.poly(pts, (0, 0, 1), [uvf(x, y) for x, y, _ in pts], key)

    def walls(self, r, za, zb, uvname, outward, key="cabin"):
        """4 walls around rectangle r between depths za and zb."""
        x0, x1, y0, y1 = r
        s = 1 if outward else -1
        uv = uv_rect(uvname)
        self.quad((x0, y0, za), (x1, y0, za), (x1, y0, zb), (x0, y0, zb), (0, -s, 0), uv, key)
        self.quad((x1, y1, za), (x0, y1, za), (x0, y1, zb), (x1, y1, zb), (0, s, 0), uv, key)
        self.quad((x0, y1, za), (x0, y0, za), (x0, y0, zb), (x0, y1, zb), (-s, 0, 0), uv, key)
        self.quad((x1, y0, za), (x1, y1, za), (x1, y1, zb), (x1, y0, zb), (s, 0, 0), uv, key)

    def frame(self, outer, holes, z, uvf, key="cabin"):
        """Flat plate = outer rectangle minus non-overlapping rectangular holes stacked
        vertically (each hole spans a horizontal band); planar UVs from uvf(x, y)."""
        x0, x1, y0, y1 = outer
        top = y1
        for hx0, hx1, hy0, hy1 in sorted(holes, key=lambda h: -h[3]):
            if top > hy1:
                self.rect_planar(x0, x1, hy1, top, z, uvf, key)
            self.rect_planar(x0, hx0, hy0, hy1, z, uvf, key)
            self.rect_planar(hx1, x1, hy0, hy1, z, uvf, key)
            top = hy0
        if top > y0:
            self.rect_planar(x0, x1, y0, top, z, uvf, key)

    def rounded_box(self, r, corner, edge, z_back, z_front, uvf, side_uv, key="cabin", holes=()):
        """Plate with rounded corners (in plane) and a rounded front edge, sides down to z_back.
        Front: inner rectangle (minus holes) + ring out to the rounded outline."""
        x0, x1, y0, y1 = r
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        inner = (x0 + corner + edge, x1 - corner - edge, y0 + corner + edge, y1 - corner - edge)
        self.frame(inner, holes, z_front, uvf, key)
        ring = rounded_rect((x0 + edge, x1 - edge, y0 + edge, y1 - edge), corner)
        angles = [math.atan2(y - cy, x - cx) for x, y in ring]
        inr = rect_at_angles(inner, angles, cx, cy)
        n = len(ring)
        for i in range(n):
            j = (i + 1) % n
            p = [(*ring[i], z_front), (*ring[j], z_front), (*inr[j], z_front), (*inr[i], z_front)]
            self.poly(p, (0, 0, 1), [uvf(x, y) for x, y, _ in p], key)
        seg = 3
        rings = []
        for s in range(seg + 1):
            a = math.radians(90 * s / seg)
            shrink = edge * (1 - math.sin(a))
            rr = (x0 + shrink, x1 - shrink, y0 + shrink, y1 - shrink)
            rings.append((rounded_rect(rr, corner + edge - shrink), z_front - edge * (1 - math.cos(a)), a))
        for s in range(seg):
            (ra, za, aa), (rb, zb, ab) = rings[s], rings[s + 1]
            am = (aa + ab) / 2
            for i in range(n):
                j = (i + 1) % n
                ex, ey = outward(rb[i], rb[j])
                p = [(*ra[i], za), (*ra[j], za), (*rb[j], zb), (*rb[i], zb)]
                self.poly(p, (ex * math.sin(am), ey * math.sin(am), math.cos(am)), [uvf(x, y) for x, y, _ in p], key)
        outer = rings[-1][0]
        su = uv_rect(side_uv)
        for i in range(n):
            j = (i + 1) % n
            ex, ey = outward(outer[i], outer[j])
            (ax, ay), (bx, by) = outer[i], outer[j]
            p = [(ax, ay, z_front - edge), (bx, by, z_front - edge), (bx, by, z_back), (ax, ay, z_back)]
            self.poly(p, (ex, ey, 0), [(su[0], su[1]), (su[2], su[1]), (su[2], su[3]), (su[0], su[3])], key)

    def merge(self, other):
        base = len(self.v)
        self.v += other.v
        for key, idx in other.groups:
            self.groups.append((key, [i + base for i in idx]))


def outward(a, b):
    ex, ey = b[1] - a[1], -(b[0] - a[0])
    ln = math.hypot(ex, ey) or 1
    return ex / ln, ey / ln


def rounded_rect(r, radius, seg=6):
    x0, x1, y0, y1 = r
    pts = []
    for cx, cy, a0 in ((x1 - radius, y1 - radius, 0), (x0 + radius, y1 - radius, 90),
                       (x0 + radius, y0 + radius, 180), (x1 - radius, y0 + radius, 270)):
        for i in range(seg + 1):
            a = math.radians(a0 + 90 * i / seg)
            pts.append((cx + radius * math.cos(a), cy + radius * math.sin(a)))
    return pts


def rect_at_angles(r, angles, cx, cy):
    """Points on rectangle r hit by rays from (cx, cy) at the given angles."""
    x0, x1, y0, y1 = r
    out = []
    for a in angles:
        dx, dy = math.cos(a), math.sin(a)
        t = min(((x1 - cx) / dx if dx > 1e-9 else (x0 - cx) / dx if dx < -1e-9 else 1e9),
                ((y1 - cy) / dy if dy > 1e-9 else (y0 - cy) / dy if dy < -1e-9 else 1e9))
        out.append((cx + dx * t, cy + dy * t))
    return out


def rot_x(p, deg, py=HINGE_Y, pz=HINGE_Z):
    """Rotate point p about the hinge axis (parallel to x), right-hand rule."""
    a = math.radians(deg)
    y, z = p[1] - py, p[2] - pz
    return (p[0], py + y * math.cos(a) - z * math.sin(a), pz + y * math.sin(a) + z * math.cos(a))


# ---------------------------------------------------------------- the model
def build_bezel(m):
    """Bezel plate, screen well and key strip well. Returns the front-plate mesh (bake target)."""
    face = Mesh()
    uvf = planar("bezelface", B)
    face.rounded_box(B, CORNER_R, EDGE_R, Z_WALL, ZB, uvf, "bezel:s", key="cabin@bz", holes=[S, K])
    m.merge(face)
    # screen well: walls + dark rim around the active screen
    m.walls(S, ZS - 0.0005, ZB, "dark:s", outward=False)
    m.frame(S, [(SX0, SX1, SY0, SY1)], ZS, lambda x, y: uv_rect("dark:s")[:2])
    # key strip well + strip plate
    m.walls(K, ZK, ZB, "strip:s", outward=False)
    m.rect_z(K[0], K[1], K[2], K[3], ZK, "strip:s")
    return face


def build_keys(m):
    """Framed keys with raised bevelled caps and backlit legend decals, LED, USB.
    Returns the click zones [(rect, command, tooltip)]."""
    def frustum(r, z0, z1, inset, uvname, key="cabin"):
        x0, x1, y0, y1 = r
        t = (x0 + inset, x1 - inset, y0 + inset, y1 - inset)
        m.rect_z(t[0], t[1], t[2], t[3], z1, uvname, key)
        uv = uv_rect(uvname + ":s")   # sloped sides: solid colour
        h = z1 - z0
        sl = inset / math.hypot(inset, h)
        cz = h / math.hypot(inset, h)
        m.quad((x0, y0, z0), (x1, y0, z0), (t[1], t[2], z1), (t[0], t[2], z1), (0, -cz, sl), uv, key)
        m.quad((x1, y1, z0), (x0, y1, z0), (t[0], t[3], z1), (t[1], t[3], z1), (0, cz, sl), uv, key)
        m.quad((x0, y1, z0), (x0, y0, z0), (t[0], t[2], z1), (t[0], t[3], z1), (-cz, 0, sl), uv, key)
        m.quad((x1, y0, z0), (x1, y1, z0), (t[1], t[3], z1), (t[1], t[2], z1), (cz, 0, sl), uv, key)
        return t

    def framed_key(r, cap_uv, decal_uv, light_key):
        x0, x1, y0, y1 = r
        fz = ZK + 0.0015
        m.rect_z(x0, x1, y0, y1, fz, "frame")                       # frame plate
        m.walls(r, ZK, fz, "frame:s", outward=True)
        c = (x0 + 0.0022, x1 - 0.0022, y0 + 0.0022, y1 - 0.0022)    # cap base
        m.walls(c, fz, fz + 0.0015, cap_uv + ":s", outward=True)    # short straight skirt
        top = frustum(c, fz + 0.0015, fz + 0.0045, 0.0012, cap_uv)
        if decal_uv:                                                # legend decal, lit per key
            m.rect_z(top[0] + 0.0004, top[1] - 0.0004, top[2] + 0.0004, top[3] - 0.0004, fz + 0.0057, decal_uv, light_key)

    ky = (K[2] + K[3]) / 2 - 0.003
    x = K[0] + 0.012
    emer = (x, x + 0.034, ky - 0.012, ky + 0.012)
    framed_key(emer, "emercap", "emerdecal", "key0")
    x += 0.034 + 0.011
    # indicator LED: octagonal lens in a dark ring
    lx, lr = x + 0.003, 0.0028
    ring = [(lx + lr * 1.6 * math.cos(math.radians(22.5 + 45 * i)), ky + lr * 1.6 * math.sin(math.radians(22.5 + 45 * i))) for i in range(8)]
    lens = [(lx + lr * math.cos(math.radians(22.5 + 45 * i)), ky + lr * math.sin(math.radians(22.5 + 45 * i))) for i in range(8)]
    hu = uv_rect("hole"); lu = uv_rect("led")
    m.poly([(px, py, ZK + 0.0004) for px, py in ring], (0, 0, 1), [(hu[0], hu[1])] * 8)
    m.poly([(px, py, ZK + 0.0012) for px, py in lens], (0, 0, 1),
           [(lu[0] + (px - lx + lr) / (2 * lr) * (lu[2] - lu[0]), lu[1] + (py - ky + lr) / (2 * lr) * (lu[3] - lu[1])) for px, py in lens])
    x += 0.006 + 0.012
    keyrects = []
    FR = 0.024                                                      # key frame size
    for i, (ai, cmd, tip, li) in enumerate(KEYS):
        r = (x + i * KEY_PITCH, x + i * KEY_PITCH + FR, ky - FR / 2, ky + FR / 2)
        framed_key(r, "cap", f"key{ai}" if li is not None else None, f"key{li}")
        keyrects.append((r, cmd, tip))
    x += 7 * KEY_PITCH + FR + 0.010
    # USB-A port: bezel-grey surround, recessed black socket with the contact tongue (in the texture)
    usb = (x, x + 0.017, ky - 0.0050, ky + 0.0050)
    m.rect_z(*usb, ZK + 0.0008, "usb")
    m.walls(usb, ZK, ZK + 0.0008, "bezel:s", outward=True)
    return [(emer, "toliss_fap/key/emer", "FAP: EMER call")] + [(r, c, t) for r, c, t in keyrects if c]


def kp_key_rects():
    """Keypad key rectangles, 6 rows x 2 columns, in KP_KEYS order."""
    cx = (KP[0] + KP[1]) / 2
    top = KP[3] - 0.049
    out = []
    for row in range(6):
        cy = top - row * 0.024
        for col in range(2):
            kx = cx + (-0.0075 if col == 0 else 0.0075)
            out.append((kx - 0.0053, kx + 0.0053, cy - 0.0068, cy + 0.0068))
    return out


def build_keypad(m):
    """Flight-deck door keypad: black body with 12 rubber keys and backlit legends.
    Returns the front-face mesh (bake target) and the click zones."""
    face = Mesh()
    face.rounded_box(KP, 0.003, 0.0015, Z_WALL, Z_WALL + D_KP, planar("keypadface", KP), "kpbody:s", key="cabin@kp")
    m.merge(face)
    zf = Z_WALL + D_KP
    clicks = []
    for i, r in enumerate(kp_key_rects()):
        x0, x1, y0, y1 = r
        m.walls(r, zf, zf + 0.0025, "kpkey:s", outward=True)
        m.rect_z(x0, x1, y0, y1, zf + 0.0025, "kpkey:s")
        m.rect_z(x0 + 0.0008, x1 - 0.0008, y0 + 0.0010, y1 - 0.0010, zf + 0.0027, f"kp{i}", "kpleg")
        clicks.append((r, f"toliss_fap/keypad/{KP_KEYS[i]}", f"Cockpit door keypad: {KP_LABELS[i]}"))
    return face, clicks


def build_cover():
    """Transparent cover over the key strip (closed position; animated about the hinge)."""
    c = Mesh()
    x0, x1, y0, y1 = CV
    grip = 0.006
    gy0, gy1 = (y1 - grip, y1) if HINGE == "bottom" else (y0, y0 + grip)
    # clear sheet (both sides so it shows when flipped), edges slightly more opaque
    sy0, sy1 = (y0, gy0) if HINGE == "bottom" else (gy1, y1)
    c.rect_z(x0, x1, sy0, sy1, ZC1, "cover", "cover", both=True)
    c.walls((x0, x1, sy0, sy1), ZC0, ZC1, "coveredge:s", outward=True, key="cover")
    # grip bar along the free edge (the full-width bar seen on the real panel)
    c.rect_z(x0, x1, gy0, gy1, ZB + 0.0030, "grip:s", "cover")
    c.walls((x0, x1, gy0, gy1), ZC0, ZB + 0.0030, "grip:s", outward=True, key="cover")
    return c


def build_shadow():
    s = Mesh()
    s.rect_planar(SH[0], SH[1], SH[2], SH[3], Z_WALL + 0.0005, planar("shadow", (SH[0], SH[1], SH[2], SH[3])), "shadow")
    return s


ANIM = ["ANIM_begin",
        "ANIM_trans -0.1202 -0.29576999 -1.43062 -0.1202 -0.29576999 -1.43062",
        "ANIM_trans_begin 1-sim/fus",
        "ANIM_trans_key 0 0 0 0", "ANIM_trans_key 1 0 0 1.6", "ANIM_trans_key 2 0 0 -4.2600002",
        "ANIM_trans_end"]


def write_obj8(path, header, verts, idx, body):
    out = ["I", "800", "OBJ", ""] + header + [f"POINT_COUNTS {len(verts)} 0 0 {len(idx)}", ""]
    out += ["VT " + " ".join(f"{c:.6f}" for c in v) for v in verts]
    out.append("")
    for k in range(0, len(idx), 10):
        chunk = idx[k:k + 10]
        out += ["IDX10 " + " ".join(map(str, chunk))] if len(chunk) == 10 else [f"IDX {c}" for c in chunk]
    out += [""] + body
    with open(path, "w", newline="\n") as f:
        f.write("\n".join(out) + "\n")


def light_attrs(key):
    """OBJ attributes for one light group."""
    if key == "shadow":
        return ["ATTR_poly_os 2", "ATTR_light_level 0 1 toliss_fap/hw_lit_off"]
    if key.startswith("key") and key != "key0":          # key legends: backlit, brighter when active
        return ["ATTR_poly_os 2", f"ATTR_light_level 0 1 toliss_fap/key_light[{key[3:]}]"]
    if key == "key0":
        return ["ATTR_poly_os 2", "ATTR_light_level 0 1 toliss_fap/key_light[0]"]
    if key == "kpleg":                                   # keypad legends: backlit on DC power
        return ["ATTR_poly_os 2", "ATTR_light_level 0 1 toliss_fap/key_backlight"]
    if key == "cover":
        return ["ATTR_poly_os 0", "ATTR_light_level 0 1 toliss_fap/hw_lit_off"]
    return ["ATTR_poly_os 0", "ATTR_light_level 0 1 anim/cabinLighting 1500"]   # like kitchens.obj


def emit_wavefront(path, mtl, parts):
    """parts: [(name, material, verts, tris)] -> Wavefront, Blender-friendly (y up -> z up)."""
    lines, nv = [f"mtllib {mtl}"], 0
    for name, mat, verts, tris in parts:
        lines.extend([f"o {name}", f"usemtl {mat}"])
        for x, y, z, nx, ny, nz, u, v in verts:
            lines.append(f"v {x:.6f} {-z:.6f} {y:.6f}")
            lines.append(f"vt {u:.6f} {v:.6f}")
            lines.append(f"vn {nx:.4f} {-nz:.4f} {ny:.4f}")
        for a in range(0, len(tris), 3):
            t = [tris[a] + nv + 1, tris[a + 2] + nv + 1, tris[a + 1] + nv + 1]   # back to CCW
            lines.append("f " + " ".join(f"{i}/{i}/{i}" for i in t))
        nv += len(verts)
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def sub(mesh, keep):
    """(verts, tris) of the groups whose key satisfies keep(key), re-indexed."""
    tris = [i for k, t in mesh.groups if keep(k) for i in t]
    used = sorted(set(tris))
    remap = {o: n for n, o in enumerate(used)}
    return [mesh.v[o] for o in used], [remap[i] for i in tris]


def main():
    m = Mesh()
    bezel_face = build_bezel(m)
    clicks = build_keys(m)
    kp_face, kp_clicks = build_keypad(m)
    cover = build_cover()
    shadow = build_shadow()

    # ---- visual OBJ: shadow decal first, then the hardware, the animated cover last (blended)
    allm = Mesh()
    allm.merge(shadow)
    n_static = len(shadow.v)
    allm.merge(m)
    cover_base = len(allm.v)
    allm.merge(cover)
    # one TRIS range per light group; order: shadow decal, opaque body, decals (drawn after
    # the caps they sit on, so their alpha blends onto them), the clear cover last
    merged = {}
    for key, tris in allm.groups:
        merged.setdefault(key.split("@")[0], []).extend(tris)   # "cabin@bz" etc. are plain "cabin"
    rank = lambda k: (0 if k == "shadow" else 1 if k == "cabin" else 3 if k == "cover" else 2, k)
    idx, body = [], ANIM[:]
    cover_open = False
    for key, tris in sorted(merged.items(), key=lambda kv: rank(kv[0])):
        if key == "cover" and not cover_open:
            # rotate about the hinge (x axis through HINGE_Y/HINGE_Z) with toliss_fap/key_cover 0..1
            body += ["ANIM_begin", f"ANIM_trans 0 {HINGE_Y:.6f} {HINGE_Z:.6f} 0 {HINGE_Y:.6f} {HINGE_Z:.6f}",
                     "ANIM_rotate_begin 1 0 0 toliss_fap/key_cover", "ANIM_rotate_key 0 0",
                     f"ANIM_rotate_key 1 {COVER_ANGLE}", "ANIM_rotate_end",
                     f"ANIM_trans 0 {-HINGE_Y:.6f} {-HINGE_Z:.6f} 0 {-HINGE_Y:.6f} {-HINGE_Z:.6f}"]
            cover_open = True
        elif key != "cover" and cover_open:
            body.append("ANIM_end")
            cover_open = False
        body += light_attrs(key)
        body.append(f"TRIS {len(idx)} {len(tris)}")
        idx += tris
    if cover_open:
        body.append("ANIM_end")
    body.append("ANIM_end")
    # cover vertices are written in place (closed); the ANIM_trans pair makes the hinge the pivot
    write_obj8(os.path.join(ROOT, "obj", "fap_hw.obj"),
               ["# ToLiss FAP hardware - generated by tools/build_fap_hw.py", "TEXTURE fap_hw.png",
                "TEXTURE_LIT fap_hw_LIT.png", "TEXTURE_NORMAL fap_hw_NML.png", "GLOBAL_specular 0.6",
                "GLOBAL_cockpit_lit"], allm.v, idx, body)

    # ---- cockpit patch source: screen device quad + invisible click zones
    # (the installer shifts vertices into the cockpit frame but passes animation lines through,
    #  so the cover uses two static click boxes swapped with ANIM_hide instead of a rotation)
    sv, si = [], []

    def q(x0, x1, y0, y1, z, u=(0, 0, 1, 1)):
        b = len(sv)
        sv.extend([(x0, y0, z, 0, 0, 1, u[0], u[1]), (x1, y0, z, 0, 0, 1, u[2], u[1]),
                   (x1, y1, z, 0, 0, 1, u[2], u[3]), (x0, y1, z, 0, 0, 1, u[0], u[3])])
        si.extend([b, b + 2, b + 1, b, b + 3, b + 2])   # clockwise from the front

    def q_pts(pts):
        b = len(sv)
        sv.extend([(*p, 0, 0, 1, 0, 0) for p in pts])
        si.extend([b, b + 2, b + 1, b, b + 3, b + 2, b, b + 1, b + 2, b, b + 2, b + 3])   # both sides

    q(SX0, SX1, SY0, SY1, ZS + 0.0005)
    sbody = ANIM[:] + ["ATTR_manip_device button TOLISS_FAP", "ATTR_cockpit_device TOLISS_FAP 0 -1 1", "TRIS 0 6"]
    sbody.append("ATTR_draw_disable")
    for (x0, x1, y0, y1), cmd, tip in clicks:          # keys (behind the closed cover)
        off = len(si)
        pad = 0.002
        q(x0 - pad, x1 + pad, y0 - pad, y1 + pad, ZK + KEY_DEPTH + 0.0015)
        sbody += [f"ATTR_manip_command button {cmd} {tip}", f"TRIS {off} 6"]
    for (x0, x1, y0, y1), cmd, tip in kp_clicks:       # keypad
        off = len(si)
        q(x0 - 0.001, x1 + 0.001, y0 - 0.001, y1 + 0.001, Z_WALL + D_KP + 0.004)
        sbody += [f"ATTR_manip_command button {cmd} {tip}", f"TRIS {off} 6"]
    # cover, closed: in front of the keys, so it takes the clicks until it is opened
    off = len(si)
    q(CV[0], CV[1], CV[2], CV[3] + 0.002, ZB + 0.0035)
    sbody += ["ANIM_begin", "ANIM_hide 0.5 1 toliss_fap/key_cover",
              "ATTR_manip_command button toliss_fap/key/cover FAP: open/close key cover", f"TRIS {off} 6", "ANIM_end"]
    # cover, open: the flipped-down sheet
    off = len(si)
    corners = [rot_x(p, COVER_ANGLE) for p in ((CV[0], CV[2], ZC1), (CV[1], CV[2], ZC1), (CV[1], CV[3], ZC1), (CV[0], CV[3], ZC1))]
    q_pts(corners)
    sbody += ["ANIM_begin", "ANIM_hide 0 0.5 toliss_fap/key_cover",
              "ATTR_manip_command button toliss_fap/key/cover FAP: open/close key cover", f"TRIS {off} 12", "ANIM_end"]
    sbody += ["ATTR_draw_enable", "ATTR_manip_none", "ANIM_end"]
    write_obj8(os.path.join(ROOT, "obj", "fap_screen.obj"),
               ["# ToLiss FAP screen + hardware click zones - generated by tools/build_fap_hw.py",
                "TEXTURE fap_screen.png"], sv, si, sbody)

    # ---- previews and bake scene
    pv = os.path.join(ROOT, "build", "preview")
    bk = os.path.join(ROOT, "build", "bake")
    os.makedirs(pv, exist_ok=True)
    os.makedirs(bk, exist_ok=True)
    hw_v, hw_t = sub(allm, lambda k: k not in ("cover", "shadow"))
    occ_v, occ_t = sub(allm, lambda k: k not in ("cover", "shadow") and "@" not in k)   # minus the bake targets
    cv_v, cv_t = sub(allm, lambda k: k == "cover")
    sh_v, sh_t = sub(allm, lambda k: k == "shadow")
    emit_wavefront(os.path.join(pv, "fap_preview.obj"), "fap_preview.mtl",
                   [("fap_hw", "hw", hw_v, hw_t), ("cover", "cover", cv_v, cv_t), ("shadow", "shadow", sh_v, sh_t),
                    ("screen", "screen", sv[:4], si[:6])])
    with open(os.path.join(pv, "fap_preview.mtl"), "w") as f:
        f.write("newmtl hw\nmap_Kd ../../obj/fap_hw.png\nnewmtl cover\nmap_Kd ../../obj/fap_hw.png\n"
                "newmtl shadow\nmap_Kd ../../obj/fap_hw.png\nnewmtl screen\nmap_Kd screen.png\n")
    # bake: targets carry atlas UVs; occluders are everything else + the housing face
    bz_v, bz_t = sub(bezel_face, lambda k: True)
    kf_v, kf_t = sub(kp_face, lambda k: True)
    h = HOUSING
    wall = [(h[0], h[2], Z_WALL, 0, 0, 1, 0, 0), (h[1], h[2], Z_WALL, 0, 0, 1, 1, 0),
            (h[1], h[3], Z_WALL, 0, 0, 1, 1, 1), (h[0], h[3], Z_WALL, 0, 0, 1, 0, 1)]
    emit_wavefront(os.path.join(bk, "fap_bake.obj"), "fap_bake.mtl",
                   [("t_bezel", "t", bz_v, bz_t), ("t_keypad", "t", kf_v, kf_t), ("t_shadow", "t", sh_v, sh_t),
                    ("occ_hw", "o", occ_v, occ_t), ("occ_wall", "o", wall, [0, 2, 1, 0, 3, 2])])
    with open(os.path.join(bk, "fap_bake.mtl"), "w") as f:
        f.write("newmtl t\nnewmtl o\n")
    lay = {"bezel": B, "keypad": KP, "housing": HOUSING, "screen": (SX0, SX1, SY0, SY1), "screen_z": ZS, "wall_z": Z_WALL,
           "hinge": [HINGE_Y, HINGE_Z], "cover_angle": COVER_ANGLE, "tex_px": TEX_PX,
           "atlas": ATLAS, "baked": BAKED, "clicks": [[c, t] for _, c, t in clicks + kp_clicks]}
    json.dump(lay, open(os.path.join(pv, "layout.json"), "w"), indent=1)
    print(f"fap_hw.obj: {len(allm.v)} verts, {len(idx) // 3} tris; bezel {B[1]-B[0]:.3f} x {B[3]-B[2]:.3f} m; "
          f"keypad {KP[1]-KP[0]:.3f} x {KP[3]-KP[2]:.3f} m; {len(clicks) + len(kp_clicks)} click zones + cover")


if __name__ == "__main__":
    main()
