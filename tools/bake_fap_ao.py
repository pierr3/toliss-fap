# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 pierr3 and ToLiss FAP contributors
"""Bakes ambient occlusion for the FAP hardware with Blender Cycles (4.x).
Reads build/bake/fap_bake.obj (written by tools/build_fap_hw.py): the bezel front, the
keypad front and the contact-shadow quad on the housing carry their atlas UVs; everything
else is only an occluder. Writes build/bake/ao.png (atlas-sized, white = unoccluded),
which tools/gen_hw_tex.py multiplies into the textures.

usage: blender -b --factory-startup -P tools/bake_fap_ao.py
"""
import json
import os

import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BK = os.path.join(ROOT, "build", "bake")
lay = json.load(open(os.path.join(ROOT, "build", "preview", "layout.json")))
N = lay["tex_px"]

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.obj_import(filepath=os.path.join(BK, "fap_bake.obj"), forward_axis="Y", up_axis="Z")
sc = bpy.context.scene
sc.render.engine = "CYCLES"
sc.cycles.samples = 256
sc.cycles.device = "CPU"
world = bpy.data.worlds.new("w")
world.light_settings.distance = 0.035     # AO reach: the bezel stands 12 mm proud, keys a few mm
sc.world = world

img = bpy.data.images.new("ao", N, N, alpha=False, float_buffer=False)
img.generated_color = (1, 1, 1, 1)
targets = [o for o in sc.objects if o.name.startswith("t_")]
for o in targets:
    mat = bpy.data.materials.new("bake_" + o.name)
    mat.use_nodes = True
    node = mat.node_tree.nodes.new("ShaderNodeTexImage")
    node.image = img
    mat.node_tree.nodes.active = node
    o.data.materials.clear()
    o.data.materials.append(mat)
bpy.ops.object.select_all(action="DESELECT")
for o in targets:
    o.select_set(True)
bpy.context.view_layer.objects.active = targets[0]
sc.render.bake.margin = 6
bpy.ops.object.bake(type="AO")
img.filepath_raw = os.path.join(BK, "ao.png")
img.file_format = "PNG"
img.save()
print("wrote", img.filepath_raw)
