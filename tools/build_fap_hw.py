# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 pierr3 and ToLiss FAP contributors
"""Builds the 3D Flight Attendant Panel hardware, modelled on photos of the A320 CIDS FAP:
a raised rounded module, a recessed metal bezel holding the screen, and the key strip
(EMER, indicator, 8 keys, USB) under a small lip.

Outputs
  obj/fap_hw.obj         visual model (our texture fap_hw.png / _LIT), attached in the .acf
  obj/fap_screen.obj     screen device quad + invisible key click boxes (-> cockpit patch)
  build/preview/*.obj    Wavefront copy (+ wall and screen) for Blender preview renders

All coordinates are in the ToLiss kitchens.obj frame (x right, y up, z aft; the FAP
faces aft). Both OBJs wrap everything in the same transform as kitchens.obj
(static offset + 1-sim/fus fuselage-length keys), so they follow A319/A320/A321 bodies.
"""
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# ---------------------------------------------------------------- layout (metres)
Z_WALL = -0.3738                    # galley wall face (kitchens frame)
SX0, SX1, SY0, SY1 = -0.899427, -0.553499, 1.254394, 1.518374   # screen (measured from texture)

D_MODULE = 0.025                    # module protrudes from the wall
BEVEL = 0.006                       # chamfer on the module front edge
ZF = Z_WALL + D_MODULE              # module front
ZB = ZF - 0.006                     # bezel plate (recessed into the module)
ZS = ZB - 0.004                     # screen plane
ZK = ZB - 0.008                     # key strip plane

RIM = 0.005                         # dark rim around the active screen
S = (SX0 - RIM, SX1 + RIM, SY0 - RIM, SY1 + RIM)            # screen well opening
K = (SX0 + 0.004, SX1 - 0.004, SY0 - 0.071, SY0 - 0.021)    # key strip opening
B = (SX0 - 0.022, SX1 + 0.022, K[2] - 0.016, SY1 + 0.022)   # bezel outline
M = (B[0] - 0.050, B[1] + 0.045, B[2] - 0.040, B[3] + 0.045)  # module outline
M_RADIUS = 0.030

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

# ---------------------------------------------------------------- texture atlas (px, 1024 x 1024)
TEX = 1024.0
ATLAS = {  # must match tools/gen_hw_tex.ps1
    "module": (8, 8, 248, 248), "bezel": (264, 8, 504, 248), "dark": (520, 8, 760, 248),
    "strip": (776, 8, 1016, 248), "lip": (4, 260, 252, 380), "frame": (256, 256, 384, 384),
    "cap": (384, 256, 512, 384), "emercap": (512, 256, 640, 384), "usb": (640, 256, 768, 384),
    "hole": (770, 258, 830, 318), "led": (834, 258, 894, 318), "emerdecal": (0, 384, 256, 512),
}
for k in range(8):
    ATLAS[f"key{k}"] = (k * 128 + 2, 514, k * 128 + 126, 638)   # legend decals


UV_PAD = 10  # px kept clear around every block so filtering at a distance cannot bleed colours


def uv_rect(name):
    if name.endswith(":s"):   # solid: a tiny patch from the block centre (walls, sides, multi-piece plates)
        x0, y0, x1, y1 = ATLAS[name[:-2]]
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        return ((cx - 3) / TEX, 1 - (cy + 3) / TEX, (cx + 3) / TEX, 1 - (cy - 3) / TEX)
    x0, y0, x1, y1 = ATLAS[name]
    if not name.startswith("key") and name != "emerdecal":
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        x0, x1 = min(x0 + UV_PAD, cx - 1), max(x1 - UV_PAD, cx + 1)
        y0, y1 = min(y0 + UV_PAD, cy - 1), max(y1 - UV_PAD, cy + 1)
    return (x0 / TEX, 1 - y1 / TEX, x1 / TEX, 1 - y0 / TEX)   # (u0, v0, u1, v1), v up


# ---------------------------------------------------------------- mesh helpers
class Mesh:
    def __init__(self):
        self.v = []          # (x, y, z, nx, ny, nz, u, v)
        self.groups = []     # (key, [indices]) - consecutive TRIS ranges with attributes

    def _group(self, key):
        key = "cabin" if key == "base" else key
        if not self.groups or self.groups[-1][0] != key:
            self.groups.append((key, []))
        return self.groups[-1][1]

    def poly(self, pts, normal, uvs, key="base", both=False):
        """Fan-triangulated convex polygon; pts and uvs in matching order."""
        base = len(self.v)
        for (x, y, z), (u, v) in zip(pts, uvs):
            self.v.append((x, y, z, *normal, u, v))
        idx = self._group(key)
        for i in range(1, len(pts) - 1):
            tri = (base, base + i, base + i + 1)
            idx += self._wind(tri, normal)
            if both:
                idx += [tri[0], tri[2], tri[1]] if idx[-3:] == list(tri) else list(tri)

    def _wind(self, tri, normal):
        a, b, c = (self.v[i] for i in tri)
        ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
        vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
        cx, cy, cz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
        facing = cx * normal[0] + cy * normal[1] + cz * normal[2]
        # X-Plane OBJ8 front faces are clockwise (as seen from the front)
        return [tri[0], tri[2], tri[1]] if facing > 0 else list(tri)

    def quad(self, p0, p1, p2, p3, normal, uv, key="base"):
        u0, v0, u1, v1 = uv
        self.poly([p0, p1, p2, p3], normal, [(u0, v0), (u1, v0), (u1, v1), (u0, v1)], key)

    def rect_z(self, x0, x1, y0, y1, z, uvname, key="base", normal=(0, 0, 1)):
        self.quad((x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z), normal, uv_rect(uvname), key)

    def box_front(self, x0, x1, y0, y1, zback, zfront, front_uv, side_uv="dark", key="base"):
        """A key/button: front face + 4 sides (no back)."""
        self.rect_z(x0, x1, y0, y1, zfront, front_uv, key)
        self.walls((x0, x1, y0, y1), zback, zfront, side_uv, outward=True, key=key)

    def walls(self, r, za, zb, uvname, outward, key="base"):
        """4 vertical-ish walls around rectangle r between depths za and zb."""
        x0, x1, y0, y1 = r
        s = 1 if outward else -1
        uv = uv_rect(uvname)
        self.quad((x0, y0, za), (x1, y0, za), (x1, y0, zb), (x0, y0, zb), (0, -s, 0), uv, key)
        self.quad((x1, y1, za), (x0, y1, za), (x0, y1, zb), (x1, y1, zb), (0, s, 0), uv, key)
        self.quad((x0, y1, za), (x0, y0, za), (x0, y0, zb), (x0, y1, zb), (-s, 0, 0), uv, key)
        self.quad((x1, y0, za), (x1, y1, za), (x1, y1, zb), (x1, y0, zb), (s, 0, 0), uv, key)

    def frame(self, outer, holes, z, uvname, key="base"):
        """Flat plate = outer rectangle minus non-overlapping rectangular holes stacked
        vertically (holes sorted top to bottom, each spanning a horizontal band)."""
        x0, x1, y0, y1 = outer
        u = uv_rect(uvname)
        top = y1
        for hx0, hx1, hy0, hy1 in sorted(holes, key=lambda h: -h[3]):
            if top > hy1:
                self.rect_z(x0, x1, hy1, top, z, uvname, key)          # band above the hole
            self.rect_z(x0, hx0, hy0, hy1, z, uvname, key)             # left of hole
            self.rect_z(hx1, x1, hy0, hy1, z, uvname, key)             # right of hole
            top = hy0
        if top > y0:
            self.rect_z(x0, x1, y0, top, z, uvname, key)


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


def build_visual():
    m = Mesh()
    ua = uv_rect("module")

    def uv_module(x, y):  # planar map of the module onto its atlas block
        return (ua[0] + (x - M[0]) / (M[1] - M[0]) * (ua[2] - ua[0]), ua[1] + (y - M[2]) / (M[3] - M[2]) * (ua[3] - ua[1]))

    # --- module: front ring (outline inset by the bevel) around the bezel opening
    cx, cy = (B[0] + B[1]) / 2, (B[2] + B[3]) / 2
    inset = (M[0] + BEVEL, M[1] - BEVEL, M[2] + BEVEL, M[3] - BEVEL)
    outer_f = rounded_rect(inset, M_RADIUS - BEVEL)
    angles = [math.atan2(y - cy, x - cx) for x, y in outer_f]
    inner = rect_at_angles(B, angles, cx, cy)
    n = len(outer_f)
    for i in range(n):
        j = (i + 1) % n
        p = [(*outer_f[i], ZF), (*outer_f[j], ZF), (*inner[j], ZF), (*inner[i], ZF)]
        m.poly(p, (0, 0, 1), [uv_module(x, y) for x, y, _ in p])
    # rounded edge (quarter round, EDGE_SEG bands) + sides down to the wall
    EDGE_SEG = 3
    rings = []
    for s in range(EDGE_SEG + 1):
        a = math.radians(90 * s / EDGE_SEG)              # 0 = front plane, 90 = side wall
        shrink = BEVEL * (1 - math.sin(a))
        r = (M[0] + shrink, M[1] - shrink, M[2] + shrink, M[3] - shrink)
        rings.append((rounded_rect(r, M_RADIUS - shrink), ZF - BEVEL * (1 - math.cos(a)), a))
    for s in range(EDGE_SEG):
        (ra, za, aa), (rb, zb, ab) = rings[s], rings[s + 1]
        am = (aa + ab) / 2
        for i in range(n):
            j = (i + 1) % n
            (ax, ay), (bx, by) = rb[i], rb[j]
            ex, ey = by - ay, -(bx - ax)
            ln = math.hypot(ex, ey) or 1
            ex, ey = ex / ln, ey / ln
            p = [(*ra[i], za), (*ra[j], za), (*rb[j], zb), (*rb[i], zb)]
            m.poly(p, (ex * math.sin(am), ey * math.sin(am), math.cos(am)), [uv_module(x, y) for x, y, _ in p])
    outer_full = rings[-1][0]
    for i in range(n):
        j = (i + 1) % n
        (ax, ay), (bx, by) = outer_full[i], outer_full[j]
        ex, ey = by - ay, -(bx - ax)
        ln = math.hypot(ex, ey) or 1
        ex, ey = ex / ln, ey / ln
        p = [(ax, ay, ZF - BEVEL), (bx, by, ZF - BEVEL), (bx, by, Z_WALL), (ax, ay, Z_WALL)]
        m.poly(p, (ex, ey, 0), [uv_module(ax, ay), uv_module(bx, by), uv_module(bx, by), uv_module(ax, ay)])
    # --- bezel: recess walls, plate with screen + key-strip openings
    m.walls(B, ZB, ZF, "bezel:s", outward=False)
    m.frame(B, [S, K], ZB, "bezel:s")
    # screen well: walls + dark rim around the active screen area
    m.walls(S, ZS - 0.0005, ZB, "dark:s", outward=False)
    m.frame(S, [(SX0, SX1, SY0, SY1)], ZS, "dark:s")
    # key strip well + strip plate
    m.walls(K, ZK, ZB, "dark:s", outward=False)
    m.rect_z(K[0], K[1], K[2], K[3], ZK, "strip:s")
    # rounded lip (hinged cover edge) hanging over the top of the strip
    LIP_R, LIP_SEG = 0.0045, 5
    ly = K[3] - 0.001
    prev = None
    for s in range(LIP_SEG + 1):
        a = math.radians(-90 + 180 * s / LIP_SEG)        # profile: from under the lip, round the front, to the top
        y = ly + LIP_R * math.sin(a)
        z = ZB + LIP_R * math.cos(a)
        nrm = (0, math.sin(a), math.cos(a))
        if prev:
            (y0, z0, n0) = prev
            nm = (0, (n0[1] + nrm[1]) / 2, (n0[2] + nrm[2]) / 2)
            m.quad((K[0], y0, z0), (K[1], y0, z0), (K[1], y, z), (K[0], y, z), nm, uv_rect("lip:s"))
        prev = (y, z, nrm)

    # --- strip contents: framed keys with raised bevelled caps + legend decals
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
        if decal_uv:                                                # legend decal, own backlight
            m.rect_z(top[0] + 0.0004, top[1] - 0.0004, top[2] + 0.0004, top[3] - 0.0004, fz + 0.0057, decal_uv, light_key)

    ky = (K[2] + K[3]) / 2 - 0.003
    x = K[0] + 0.012
    emer = (x, x + 0.034, ky - 0.012, ky + 0.012)
    framed_key(emer, "emercap", "emerdecal", "emer")
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
        framed_key(r, "cap", f"key{ai}" if li is not None else None, f"key{li}" if li is not None else "cabin")
        keyrects.append((r, cmd, tip))
    x += 7 * KEY_PITCH + FR + 0.010
    # USB port: frame + recessed dark socket
    usb = (x, x + 0.018, ky - 0.0045, ky + 0.0045)
    m.rect_z(*usb, ZK + 0.0006, "usb")
    clicks = [(emer, "toliss_fap/key/emer", "FAP: EMER call")] + [(r, c, t) for r, c, t in keyrects if c]
    return m, clicks


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


def main():
    m, clicks = build_visual()

    # ---- visual OBJ: one TRIS range per light group
    idx, body = [], ANIM[:]
    for key, tris in m.groups:
        decal = key.startswith("key") or key == "emer"
        body.append("ATTR_poly_os 2" if decal else "ATTR_poly_os 0")   # decals drawn on top of their caps
        if key.startswith("key"):            # legend decals: backlit per key
            body.append(f"ATTR_light_level 0 1 toliss_fap/key_light[{key[3:]}]")
        elif key == "emer":
            body.append("ATTR_light_level 0 1 toliss_fap/key_light[0]")
        else:                                # body: lit by the ToLiss cabin lighting, like kitchens.obj
            body.append("ATTR_light_level 0 1 anim/cabinLighting 1500")
        body.append(f"TRIS {len(idx)} {len(tris)}")
        idx += tris
    body.append("ANIM_end")
    write_obj8(os.path.join(ROOT, "obj", "fap_hw.obj"),
               ["# ToLiss FAP hardware - generated by tools/build_fap_hw.py", "TEXTURE fap_hw.png",
                "TEXTURE_LIT fap_hw_LIT.png", "TEXTURE_NORMAL fap_hw_NML.png", "GLOBAL_specular 0.6", "GLOBAL_cockpit_lit"], m.v, idx, body)

    # ---- cockpit patch source: screen device quad + invisible key click boxes
    sv, si = [], []

    def q(x0, x1, y0, y1, z, u=(0, 0, 1, 1)):
        b = len(sv)
        sv.extend([(x0, y0, z, 0, 0, 1, u[0], u[1]), (x1, y0, z, 0, 0, 1, u[2], u[1]),
                   (x1, y1, z, 0, 0, 1, u[2], u[3]), (x0, y1, z, 0, 0, 1, u[0], u[3])])
        si.extend([b, b + 2, b + 1, b, b + 3, b + 2])   # clockwise from the front
    q(SX0, SX1, SY0, SY1, ZS + 0.0005)
    sbody = ANIM[:] + ["ATTR_manip_device button TOLISS_FAP", "ATTR_cockpit_device TOLISS_FAP 0 -1 1", "TRIS 0 6"]
    sbody.append("ATTR_draw_disable")
    for (x0, x1, y0, y1), cmd, tip in clicks:
        off = len(si)
        pad = 0.002
        q(x0 - pad, x1 + pad, y0 - pad, y1 + pad, ZK + KEY_DEPTH + 0.0015)
        sbody += [f"ATTR_manip_command button {cmd} {tip}", f"TRIS {off} 6"]
    sbody += ["ATTR_draw_enable", "ATTR_manip_none", "ANIM_end"]
    write_obj8(os.path.join(ROOT, "obj", "fap_screen.obj"),
               ["# ToLiss FAP screen + hardware key click zones - generated by tools/build_fap_hw.py",
                "TEXTURE fap_screen.png"], sv, si, sbody)

    # ---- Wavefront preview (visual + wall + screen), Blender-friendly (y up -> z up)
    pv = os.path.join(ROOT, "build", "preview")
    os.makedirs(pv, exist_ok=True)
    lines, nv = ["mtllib fap_preview.mtl"], 0

    def emit(name, mat, verts, tris):
        nonlocal nv
        lines.extend([f"o {name}", f"usemtl {mat}"])
        for x, y, z, nx, ny, nz, u, v in verts:
            lines.append(f"v {x:.6f} {-z:.6f} {y:.6f}")
            lines.append(f"vt {u:.6f} {v:.6f}")
            lines.append(f"vn {nx:.4f} {-nz:.4f} {ny:.4f}")
        for a in range(0, len(tris), 3):
            t = [tris[a] + nv + 1, tris[a + 2] + nv + 1, tris[a + 1] + nv + 1]   # back to CCW
            lines.append("f " + " ".join(f"{i}/{i}/{i}" for i in t))
        nv += len(verts)

    allidx = [i for _, t in m.groups for i in t]
    emit("fap_hw", "hw", m.v, allidx)
    emit("screen", "screen", sv[:4], si[:6])
    wall = [(M[0] - 0.25, M[2] - 0.3, Z_WALL, 0, 0, 1, 0, 0), (M[1] + 0.12, M[2] - 0.3, Z_WALL, 0, 0, 1, 1, 0),
            (M[1] + 0.12, M[3] + 0.15, Z_WALL, 0, 0, 1, 1, 1), (M[0] - 0.25, M[3] + 0.15, Z_WALL, 0, 0, 1, 0, 1)]
    emit("wall", "wall", wall, [0, 2, 1, 0, 3, 2])
    with open(os.path.join(pv, "fap_preview.obj"), "w") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(pv, "fap_preview.mtl"), "w") as f:
        f.write("newmtl hw\nmap_Kd ../../obj/fap_hw.png\nnewmtl screen\nmap_Kd screen.png\n"
                "newmtl wall\nKd 0.80 0.80 0.78\n")
    json.dump({"module": M, "bezel": B, "screen": (SX0, SX1, SY0, SY1), "screen_z": ZS,
               "clicks": [[c, t] for _, c, t in clicks]}, open(os.path.join(pv, "layout.json"), "w"), indent=1)
    print(f"fap_hw.obj: {len(m.v)} verts, {len(allidx) // 3} tris; module {M[1]-M[0]:.3f} x {M[3]-M[2]:.3f} m, "
          f"depth {D_MODULE*1000:.0f} mm; {len(clicks)} click zones")


if __name__ == "__main__":
    main()
