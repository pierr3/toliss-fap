# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 pierr3 and ToLiss FAP contributors
"""Blender (4.x) headless preview of the FAP hardware.
usage: blender -b --factory-startup -P tools/preview_fap.py -- <out_dir>
Renders a 3/4 view, a straight view and a key-strip close-up."""
import json
import math
import os
import sys

import bpy
from mathutils import Vector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PV = os.path.join(ROOT, "build", "preview")
OUT = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else PV
lay = json.load(open(os.path.join(PV, "layout.json")))

bpy.ops.wm.read_factory_settings(use_empty=True)
# the preview OBJ is already Z-up: keep its axes as written
bpy.ops.wm.obj_import(filepath=os.path.join(PV, "fap_preview.obj"), forward_axis="Y", up_axis="Z")

# materials: textures from the .mtl, plus an emissive screen and a matte wall
for ob in bpy.context.scene.objects:
    for slot in ob.material_slots:
        mat = slot.material
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf is None:
            continue
        bsdf.inputs["Roughness"].default_value = 0.55
        if "screen" in mat.name:
            img = bpy.data.images.load(os.path.join(PV, "screen.png"))
            tex = mat.node_tree.nodes.new("ShaderNodeTexImage")
            tex.image = img
            mat.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Emission Color"])
            mat.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
            bsdf.inputs["Emission Strength"].default_value = 1.2
            bsdf.inputs["Roughness"].default_value = 0.15

scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items.keys() else "BLENDER_EEVEE"
scene.render.resolution_x, scene.render.resolution_y = 1400, 1050
scene.view_settings.view_transform = "Standard"
world = bpy.data.worlds.new("w")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.55, 0.56, 0.58, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 0.25
scene.world = world

M = lay["module"]
cx, cz = (M[0] + M[1]) / 2, (M[2] + M[3]) / 2
wall_y = 0.3738  # -Z_WALL; the panel faces -y in Blender
target = Vector((cx, wall_y - 0.02, cz))

# cabin-ish lighting: big soft overhead area light + a fill from the camera side
def area(name, loc, energy, size):
    d = bpy.data.lights.new(name, "AREA")
    d.energy, d.size = energy, size
    o = bpy.data.objects.new(name, d)
    o.location = loc
    scene.collection.objects.link(o)
    o.rotation_euler = (target - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
area("top", (cx, wall_y - 0.6, cz + 1.0), 22, 1.5)
area("fill", (cx - 0.6, wall_y - 1.2, cz + 0.1), 9, 1.0)

cam_d = bpy.data.cameras.new("cam")
cam = bpy.data.objects.new("cam", cam_d)
scene.collection.objects.link(cam)
scene.camera = cam

def shot(name, loc, look, lens):
    cam.location = loc
    cam.rotation_euler = (Vector(look) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    cam_d.lens = lens
    scene.render.filepath = os.path.join(OUT, name)
    bpy.ops.render.render(write_still=True)

shot("fap_34.png", (cx + 0.45, wall_y - 0.85, cz + 0.12), target, 40)
shot("fap_front.png", (cx, wall_y - 1.0, cz), target, 45)
K_y = lay["screen"][2] - 0.046
shot("fap_strip.png", (cx - 0.18, wall_y - 0.30, K_y + 0.10), (cx - 0.02, wall_y - 0.02, K_y), 45)
print("renders written to", OUT)
