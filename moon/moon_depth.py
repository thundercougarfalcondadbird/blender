"""
Full-disk depth map of Moon.blend, as seen from far away (like the Moon from Earth).

Usage:  blender -b moon/Moon.blend --python moon/moon_depth.py -- [both|beauty|depth] [size] [edge_start]

Replaces the scene camera with an orthographic one on the +X axis looking at the
sphere (the Earth-facing side), so the whole disk is framed with a small margin. Orthographic is what
"far away" converges to, and avoids picking a distance/lens by hand.

Depth map: the LOLA elevation texture on the sphere, read as Non-Color data and
contrast-stretched between its 0.5th and 99.5th percentiles (white = high terrain,
black = low basins). Geometric distance is not used: the sphere is smooth and the
relief is ~1% of its radius, so it would only give a plain gradient.

moon_depth_vignette.png (non-destructive extra): the same elevation with a black-to-clear
radial gradient laid over it to suggest the sphere turning away at the edge. Nothing
darkens inside edge_start (fraction of the disc radius, default 0.4); from there the
map fades smoothly to black at the limb.
Writes moon_beauty.png, moon_depth.png and moon_depth_vignette.png next to this script.
"""
import os
import sys

import bpy
import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
MODE = argv[0] if len(argv) > 0 else "both"
SIZE = int(argv[1]) if len(argv) > 1 else 2048
EDGE_START = float(argv[2]) if len(argv) > 2 else 0.4   # disc radius fraction where darkening begins
MARGIN = 1.08          # framing: 8% of empty space around the disk

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
scene = bpy.context.scene
moon = bpy.data.objects["Sphere"]

# ---------------------------------------------------------------- camera
corners = [moon.matrix_world @ Vector(c) for c in moon.bound_box]
centre = sum(corners, Vector()) / 8
half = max(moon.dimensions) / 2

cam_data = bpy.data.cameras.new("MoonCam")
cam_data.type = "ORTHO"
cam_data.ortho_scale = 2 * half * MARGIN
cam_data.clip_start = 0.1
cam_data.clip_end = 1000
cam = bpy.data.objects.new("MoonCam", cam_data)
scene.collection.objects.link(cam)
# The sphere's UV puts lunar lon 0 / lat 0 (map centre, u=0.5) on +X and the north
# pole on +Z, so a camera on +X looking along -X, Z up, gives the view from Earth
# (north up, Mare Crisium on the right).
cam.location = (centre.x + 50, centre.y, centre.z)
cam.rotation_euler = (1.5707963, 0, 1.5707963)
scene.camera = cam

scene.render.resolution_x = SIZE
scene.render.resolution_y = SIZE
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_depth = "16"

# ---------------------------------------------------------------- beauty
if MODE in ("both", "beauty"):
    scene.render.filepath = os.path.join(OUT_DIR, "moon_beauty.png")
    bpy.ops.render.render(write_still=True)

# ---------------------------------------------------------------- depth
if MODE in ("both", "depth"):
    img = next(i for i in bpy.data.images if "LDEM" in i.name)
    img.colorspace_settings.name = "Non-Color"      # elevation is data, not colour
    px = np.empty(img.size[0] * img.size[1] * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    lo, hi = np.percentile(px[0::4], [0.5, 99.5])

    # flat, unlit output: no tone mapping, black background
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    world = scene.world
    if world and world.node_tree and world.node_tree.nodes.get("Background"):
        bg = world.node_tree.nodes["Background"]
        bg.inputs["Color"].default_value = (0, 0, 0, 1)
        bg.inputs["Strength"].default_value = 0

    def render_depth(name, edge_start):
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        nt = mat.node_tree
        nt.nodes.clear()
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = img
        tex.interpolation = "Cubic"
        rng = nt.nodes.new("ShaderNodeMapRange")
        rng.clamp = True
        rng.inputs["From Min"].default_value = lo
        rng.inputs["From Max"].default_value = hi
        emit = nt.nodes.new("ShaderNodeEmission")
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(tex.outputs["Color"], rng.inputs["Value"])
        result = rng.outputs["Result"]

        if edge_start is not None:
            # radial distance from the view axis (+X) as a fraction of the disc radius
            geo = nt.nodes.new("ShaderNodeNewGeometry")
            sep = nt.nodes.new("ShaderNodeSeparateXYZ")
            comb = nt.nodes.new("ShaderNodeCombineXYZ")
            length = nt.nodes.new("ShaderNodeVectorMath")
            length.operation = "LENGTH"
            frac = nt.nodes.new("ShaderNodeMath")
            frac.operation = "DIVIDE"
            frac.inputs[1].default_value = half
            fade = nt.nodes.new("ShaderNodeMapRange")       # 1 (clear) inside, 0 (black) at the limb
            fade.interpolation_type = "SMOOTHSTEP"
            fade.clamp = True
            fade.inputs["From Min"].default_value = edge_start
            fade.inputs["From Max"].default_value = 1.0
            fade.inputs["To Min"].default_value = 1.0
            fade.inputs["To Max"].default_value = 0.0
            mul = nt.nodes.new("ShaderNodeMath")
            mul.operation = "MULTIPLY"
            nt.links.new(geo.outputs["Position"], sep.inputs["Vector"])
            nt.links.new(sep.outputs["Y"], comb.inputs["Y"])
            nt.links.new(sep.outputs["Z"], comb.inputs["Z"])
            nt.links.new(comb.outputs["Vector"], length.inputs[0])
            nt.links.new(length.outputs["Value"], frac.inputs[0])
            nt.links.new(frac.outputs[0], fade.inputs["Value"])
            nt.links.new(result, mul.inputs[0])
            nt.links.new(fade.outputs["Result"], mul.inputs[1])
            result = mul.outputs[0]

        nt.links.new(result, emit.inputs["Color"])
        nt.links.new(emit.outputs["Emission"], out.inputs["Surface"])
        scene.view_layers[0].material_override = mat
        scene.render.filepath = os.path.join(OUT_DIR, f"{name}.png")
        bpy.ops.render.render(write_still=True)

    render_depth("moon_depth", None)
    render_depth("moon_depth_vignette", EDGE_START)
    print(f"Elevation: black = {lo:.4f}, white = {hi:.4f}; edge fade starts at {EDGE_START:.2f} of the radius")
