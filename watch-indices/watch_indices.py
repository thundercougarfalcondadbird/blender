"""Watch dial with 12 tilted square-column indices, viewed from the top.

Run:  blender --background --python watch_indices.py -- [resolution] [samples]
Writes watch_indices.blend and watch_indices.png next to this script.
"""
import bpy
import math
import os
import random
import sys
from mathutils import Vector, Matrix

# ---------------------------------------------------------------- parameters
DIAL_RADIUS     = 1.00   # dial disc radius (scene units)
DIAL_THICKNESS  = 0.05
INDEX_RADIUS    = 0.78   # distance from center to where each column meets the dial
COLUMN_WIDTH    = 0.15   # square cross-section side
COLUMN_EXPOSED  = 0.075  # length of column visible above the dial (along its axis)
COLUMN_BURIED   = 0.10   # length hidden below the dial surface
TILT_DEG        = 35.0   # lean from vertical
TILT_OUTWARD    = True   # True: lean toward the rim, False: lean toward the center
BEVEL           = 0.004  # edge rounding on columns (catches highlights)
SPIN_MODE       = "progressive"  # "progressive" or "random" spin about each column's long axis
SPIN_START_DEG  = 45.0   # progressive: 12 o'clock spin (45 = corner points at the center)
SPIN_STEP_DEG   = 30.0   # progressive: added per hour, clockwise seen from above
SPIN_SEED       = 7      # random: change to reshuffle

DIAL_COLOR      = (0.015, 0.025, 0.06, 1.0)   # deep navy
COLUMN_COLOR    = (0.85, 0.85, 0.87, 1.0)     # steel
SUN_ELEVATION   = 50.0   # degrees above horizon
SUN_AZIMUTH     = 135.0  # degrees, 0 = light coming from 12 o'clock
TRANSPARENT_BG  = True

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
RESOLUTION = int(argv[0]) if len(argv) > 0 else 3000
SAMPLES    = int(argv[1]) if len(argv) > 1 else 256
MODE       = argv[2] if len(argv) > 2 else "both"   # both | beauty | depth

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
BLEND_PATH = os.path.join(OUT_DIR, "watch_indices.blend")
PNG_PATH = os.path.join(OUT_DIR, "watch_indices.png")
DEPTH_PATH = os.path.join(OUT_DIR, "watch_indices_depth.png")

# ---------------------------------------------------------------- reset scene
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene


def make_material(name, color, metallic, roughness):
    mat = bpy.data.materials.new(name)
    try:
        mat.use_nodes = True
    except AttributeError:
        pass
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


dial_mat = make_material("Dial", DIAL_COLOR, 0.0, 0.75)
dial_mat.node_tree.nodes["Principled BSDF"].inputs["Specular IOR Level"].default_value = 0.15
col_mat = make_material("Column", COLUMN_COLOR, 1.0, 0.22)

# ---------------------------------------------------------------- dial
bpy.ops.mesh.primitive_cylinder_add(
    vertices=256, radius=DIAL_RADIUS, depth=DIAL_THICKNESS,
    location=(0, 0, -DIAL_THICKNESS / 2))
dial = bpy.context.active_object
dial.name = "Dial"
dial.data.materials.append(dial_mat)
bpy.ops.object.shade_smooth()

# ---------------------------------------------------------------- columns
length = COLUMN_EXPOSED + COLUMN_BURIED
t = math.radians(TILT_DEG)
rng = random.Random(SPIN_SEED)
for i in range(12):
    phi = math.radians(i * 30.0)                       # 0 = 12 o'clock, clockwise
    radial = Vector((math.sin(phi), math.cos(phi), 0))
    tangent = Vector((math.cos(phi), -math.sin(phi), 0))
    lean = radial if TILT_OUTWARD else -radial
    axis = (Vector((0, 0, 1)) * math.cos(t) + lean * math.sin(t)).normalized()
    y_axis = axis.cross(tangent)

    base = radial * INDEX_RADIUS                        # point where it exits the dial
    center = base + axis * (length / 2 - COLUMN_BURIED)

    bpy.ops.mesh.primitive_cube_add(size=1)
    col = bpy.context.active_object
    col.name = f"Index_{i if i else 12:02d}"
    col.scale = (COLUMN_WIDTH, COLUMN_WIDTH, length)
    rot = Matrix((tangent, y_axis, axis)).transposed().to_4x4()
    if SPIN_MODE == "progressive":
        spin_deg = -(SPIN_START_DEG + SPIN_STEP_DEG * i)   # negative = clockwise from above
    else:
        spin_deg = rng.uniform(0.0, 90.0)                   # square: 90° covers all
    spin = Matrix.Rotation(math.radians(spin_deg), 4, "Z")
    col.matrix_world = Matrix.Translation(center) @ rot @ spin @ Matrix.Diagonal(
        (COLUMN_WIDTH, COLUMN_WIDTH, length, 1.0))
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bev = col.modifiers.new("Bevel", "BEVEL")
    bev.width = BEVEL
    bev.segments = 3
    col.data.materials.append(col_mat)

# ---------------------------------------------------------------- lighting
sun_data = bpy.data.lights.new("Sun", "SUN")
sun_data.energy = 4.0
sun_data.angle = math.radians(3.0)                     # slightly soft shadows
sun = bpy.data.objects.new("Sun", sun_data)
scene.collection.objects.link(sun)
el, az = math.radians(SUN_ELEVATION), math.radians(SUN_AZIMUTH)
to_light = Vector((math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)))
sun.rotation_euler = to_light.to_track_quat("Z", "Y").to_euler()

world = bpy.data.worlds.new("World")
scene.world = world
try:
    world.use_nodes = True
except AttributeError:
    pass
bg = world.node_tree.nodes.get("Background")
bg.inputs["Color"].default_value = (0.6, 0.62, 0.65, 1.0)  # soft fill + metal reflections
bg.inputs["Strength"].default_value = 0.6

# ---------------------------------------------------------------- camera
cam_data = bpy.data.cameras.new("Camera")
cam_data.lens = 50
cam_data.sensor_width = 36
half_fov = math.atan(cam_data.sensor_width / 2 / cam_data.lens)
cam_height = (DIAL_RADIUS * 1.06) / math.tan(half_fov)
cam = bpy.data.objects.new("Camera", cam_data)
cam.location = (0, 0, cam_height)
cam.rotation_euler = (0, 0, 0)                         # looking straight down, 12 at top
scene.collection.objects.link(cam)
scene.camera = cam

# ---------------------------------------------------------------- render
scene.render.engine = "CYCLES"
scene.cycles.samples = SAMPLES
scene.cycles.use_denoising = True
try:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for backend in ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL"):
        try:
            prefs.compute_device_type = backend
            prefs.get_devices()
            if any(d.type != "CPU" for d in prefs.devices):
                for d in prefs.devices:
                    d.use = True
                scene.cycles.device = "GPU"
                print(f"Using GPU backend {backend}")
                break
        except TypeError:
            continue
except Exception as e:
    print("GPU setup skipped:", e)

scene.render.resolution_x = RESOLUTION
scene.render.resolution_y = RESOLUTION
scene.render.resolution_percentage = 100
scene.render.film_transparent = TRANSPARENT_BG
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA" if TRANSPARENT_BG else "RGB"
scene.render.image_settings.color_depth = "16"
scene.render.filepath = PNG_PATH

bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)
if MODE in ("both", "beauty"):
    bpy.ops.render.render(write_still=True)
    print("Saved", BLEND_PATH, "and", PNG_PATH)

# ---------------------------------------------------------------- depth map
# Height above the dial surface, not camera distance: the flat dial is uniformly
# black and the highest point of any index is pure white.
if MODE in ("both", "depth"):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    z_max = 0.0
    for ob in scene.objects:
        if ob.name.startswith("Index_"):
            ev = ob.evaluated_get(depsgraph)
            mesh = ev.to_mesh()
            z_max = max(z_max, max((ev.matrix_world @ v.co).z for v in mesh.vertices))
            ev.to_mesh_clear()
    print(f"Depth map range: 0 (dial) .. {z_max:.4f} (white)")

    depth_mat = bpy.data.materials.new("DepthOverride")
    try:
        depth_mat.use_nodes = True
    except AttributeError:
        pass
    nt = depth_mat.node_tree
    nt.nodes.clear()
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    rng_node = nt.nodes.new("ShaderNodeMapRange")
    rng_node.clamp = True
    rng_node.inputs["From Min"].default_value = 0.0
    rng_node.inputs["From Max"].default_value = z_max
    emit = nt.nodes.new("ShaderNodeEmission")
    emit.inputs["Strength"].default_value = 1.0
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(geo.outputs["Position"], sep.inputs["Vector"])
    nt.links.new(sep.outputs["Z"], rng_node.inputs["Value"])
    nt.links.new(rng_node.outputs["Result"], emit.inputs["Color"])
    nt.links.new(emit.outputs["Emission"], out.inputs["Surface"])

    scene.view_layers[0].material_override = depth_mat
    bg.inputs["Strength"].default_value = 0.0
    sun.hide_render = True
    scene.cycles.samples = 64
    scene.cycles.use_denoising = False
    scene.render.film_transparent = False
    # Write raw linear values so grey levels are proportional to height.
    try:
        scene.view_settings.view_transform = "Raw"
    except TypeError:
        scene.view_settings.view_transform = "Standard"
        print("WARNING: 'Raw' view transform unavailable; values are sRGB-encoded")
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0
    scene.render.image_settings.color_mode = "BW"
    scene.render.image_settings.color_depth = "16"
    scene.render.filepath = DEPTH_PATH
    bpy.ops.render.render(write_still=True)
    print("Saved", DEPTH_PATH)
