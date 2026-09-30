"""Watch dial with a procedural leaf-vein-network background (a distorted,
two-scale Voronoi "distance to edge" field, built entirely in Geometry Nodes
so it is seamless and fully parametric -- no source image needed) and 12
square Craftsman- or Art-Deco-style indices with a recessed frame-and-panel
inlay.

Run:  blender --background --python vein_dial.py -- [resolution] [samples] [mode] [style]
      style: craftsman (default, single recessed panel) | artdeco (stepped double panel)
Writes vein_dial.blend, vein_dial.png and vein_dial_depth.png next to this script.
"""
import bmesh
import bpy
import math
import os
import sys
from mathutils import Vector, Matrix

# ---------------------------------------------------------------- parameters
DIAL_RADIUS     = 1.00
DIAL_THICKNESS  = 0.05
VEIN_CAP_RADIUS = DIAL_RADIUS * 0.995   # thin plain lip left bare at the true rim
VEIN_CAP_GRID   = 420                   # grid subdivisions per side (vein resolution)

INDEX_RADIUS    = 0.78
COLUMN_WIDTH    = 0.15
COLUMN_EXPOSED  = 0.075
COLUMN_BURIED   = 0.10
TILT_DEG        = 35.0
BEVEL           = 0.004
SPIN_START_DEG  = 45.0
SPIN_STEP_DEG   = 30.0

PANEL_BORDER_1  = COLUMN_WIDTH * 0.16   # craftsman: single recessed border width
PANEL_DEPTH_1   = COLUMN_WIDTH * 0.22
PANEL_BORDER_2A = COLUMN_WIDTH * 0.12   # artdeco: outer step
PANEL_DEPTH_2A  = COLUMN_WIDTH * 0.12
PANEL_BORDER_2B = COLUMN_WIDTH * 0.14   # artdeco: inner step
PANEL_DEPTH_2B  = COLUMN_WIDTH * 0.12

# Vein network (all distances are in the disc's own -1..1-ish local space).
PRIMARY_SCALE     = 2.6    # cells per unit -> a handful of main veins across the dial
PRIMARY_WIDTH     = 0.055  # vein half-width, in Voronoi cell-distance (scaled-space) units
SECONDARY_SCALE   = 8.0    # fine reticulation between the primary veins
SECONDARY_WIDTH   = 0.10   # kept wide enough (world width ~ WIDTH/SCALE) to stay mesh-resolvable
SECONDARY_WEIGHT  = 0.55   # secondary veins sit shallower than primary
DISTORT_NOISE_SCALE = 1.8  # low-frequency warp so cell edges curve organically
DISTORT_STRENGTH    = 0.22
BASE_NOISE_SCALE  = 18.0   # very fine "blade" surface grain between veins
BASE_NOISE_WEIGHT = 0.12
VEIN_HEIGHT_SCALE = 0.05   # peak vein height, kept below the index tops

DIAL_COLOR      = (0.10, 0.075, 0.045, 1.0)   # warm quartersawn-oak brown
COLUMN_COLOR    = (0.72, 0.60, 0.30, 1.0)     # brushed brass
SUN_ELEVATION   = 50.0
SUN_AZIMUTH     = 135.0
TRANSPARENT_BG  = True

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
RESOLUTION = int(argv[0]) if len(argv) > 0 else 3000
SAMPLES    = int(argv[1]) if len(argv) > 1 else 256
MODE       = argv[2] if len(argv) > 2 else "both"
STYLE      = argv[3] if len(argv) > 3 else "craftsman"

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
BLEND_PATH = os.path.join(OUT_DIR, "vein_dial.blend")
PNG_PATH = os.path.join(OUT_DIR, "vein_dial.png")
DEPTH_PATH = os.path.join(OUT_DIR, "vein_dial_depth.png")

# ---------------------------------------------------------------- reset scene
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene


def make_material(name, color, metallic, roughness):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


dial_mat = make_material("Dial", DIAL_COLOR, 0.0, 0.65)
col_mat = make_material("Column", COLUMN_COLOR, 1.0, 0.28)

# ---------------------------------------------------------------- dial body
bpy.ops.mesh.primitive_cylinder_add(
    vertices=256, radius=DIAL_RADIUS, depth=DIAL_THICKNESS,
    location=(0, 0, -DIAL_THICKNESS / 2))
dial = bpy.context.active_object
dial.name = "Dial"
dial.data.materials.append(dial_mat)
bpy.ops.object.shade_smooth()

# ---------------------------------------------------------------- vein-network node group
def build_vein_node_group():
    ng = bpy.data.node_groups.new("VeinNetwork", "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    nodes, links = ng.nodes, ng.links

    n_in = nodes.new("NodeGroupInput")
    n_out = nodes.new("NodeGroupOutput")
    pos = nodes.new("GeometryNodeInputPosition")
    normal = nodes.new("GeometryNodeInputNormal")

    # Trim the square grid down to the dial's circle before displacing.
    radial_len = nodes.new("ShaderNodeVectorMath")
    radial_len.operation = "LENGTH"
    links.new(pos.outputs["Position"], radial_len.inputs[0])
    outside = nodes.new("ShaderNodeMath")
    outside.operation = "GREATER_THAN"
    outside.inputs[1].default_value = VEIN_CAP_RADIUS
    links.new(radial_len.outputs["Value"], outside.inputs[0])
    trim = nodes.new("GeometryNodeDeleteGeometry")
    trim.domain = "POINT"
    links.new(n_in.outputs["Geometry"], trim.inputs["Geometry"])
    links.new(outside.outputs[0], trim.inputs["Selection"])

    # Organic domain warp so Voronoi cell edges read as curved veins, not facets.
    warp_noise = nodes.new("ShaderNodeTexNoise")
    warp_noise.inputs["Scale"].default_value = DISTORT_NOISE_SCALE
    links.new(pos.outputs["Position"], warp_noise.inputs["Vector"])

    center = nodes.new("ShaderNodeVectorMath")
    center.operation = "SUBTRACT"
    center.inputs[1].default_value = (0.5, 0.5, 0.5)
    links.new(warp_noise.outputs["Color"], center.inputs[0])

    warp_scaled = nodes.new("ShaderNodeVectorMath")
    warp_scaled.operation = "SCALE"
    warp_scaled.inputs["Scale"].default_value = DISTORT_STRENGTH
    links.new(center.outputs[0], warp_scaled.inputs[0])

    warped_pos = nodes.new("ShaderNodeVectorMath")
    warped_pos.operation = "ADD"
    links.new(pos.outputs["Position"], warped_pos.inputs[0])
    links.new(warp_scaled.outputs[0], warped_pos.inputs[1])

    def vein_layer(scale, width):
        vor = nodes.new("ShaderNodeTexVoronoi")
        vor.feature = "DISTANCE_TO_EDGE"
        vor.inputs["Scale"].default_value = scale
        links.new(warped_pos.outputs[0], vor.inputs["Vector"])
        rng = nodes.new("ShaderNodeMapRange")
        rng.clamp = True
        rng.inputs["From Min"].default_value = 0.0
        rng.inputs["From Max"].default_value = width
        rng.inputs["To Min"].default_value = 1.0
        rng.inputs["To Max"].default_value = 0.0
        links.new(vor.outputs["Distance"], rng.inputs["Value"])
        return rng.outputs["Result"]

    primary = vein_layer(PRIMARY_SCALE, PRIMARY_WIDTH)
    secondary = vein_layer(SECONDARY_SCALE, SECONDARY_WIDTH)

    sec_weighted = nodes.new("ShaderNodeMath")
    sec_weighted.operation = "MULTIPLY"
    sec_weighted.inputs[1].default_value = SECONDARY_WEIGHT
    links.new(secondary, sec_weighted.inputs[0])

    combined = nodes.new("ShaderNodeMath")
    combined.operation = "MAXIMUM"
    links.new(primary, combined.inputs[0])
    links.new(sec_weighted.outputs[0], combined.inputs[1])

    base_noise = nodes.new("ShaderNodeTexNoise")
    base_noise.inputs["Scale"].default_value = BASE_NOISE_SCALE
    links.new(warped_pos.outputs[0], base_noise.inputs["Vector"])
    base_weighted = nodes.new("ShaderNodeMath")
    base_weighted.operation = "MULTIPLY"
    base_weighted.inputs[1].default_value = BASE_NOISE_WEIGHT
    links.new(base_noise.outputs["Fac"], base_weighted.inputs[0])

    summed = nodes.new("ShaderNodeMath")
    summed.operation = "ADD"
    links.new(combined.outputs[0], summed.inputs[0])
    links.new(base_weighted.outputs[0], summed.inputs[1])

    clamped = nodes.new("ShaderNodeClamp")
    links.new(summed.outputs[0], clamped.inputs["Value"])

    height = nodes.new("ShaderNodeMath")
    height.operation = "MULTIPLY"
    height.inputs[1].default_value = VEIN_HEIGHT_SCALE
    links.new(clamped.outputs[0], height.inputs[0])

    offset = nodes.new("ShaderNodeVectorMath")
    offset.operation = "SCALE"
    links.new(normal.outputs["Normal"], offset.inputs[0])
    links.new(height.outputs[0], offset.inputs["Scale"])

    setpos = nodes.new("GeometryNodeSetPosition")
    links.new(trim.outputs["Geometry"], setpos.inputs["Geometry"])
    links.new(offset.outputs[0], setpos.inputs["Offset"])
    links.new(setpos.outputs["Geometry"], n_out.inputs["Geometry"])
    return ng


vein_group = build_vein_node_group()

# ---------------------------------------------------------------- vein cap
# A uniform grid (not an n-gon fan) so the vein network is evenly sampled;
# the geometry-node group itself trims it down to the dial's circle.
bpy.ops.mesh.primitive_grid_add(
    x_subdivisions=VEIN_CAP_GRID, y_subdivisions=VEIN_CAP_GRID,
    size=2 * VEIN_CAP_RADIUS * 1.01, location=(0, 0, 0))
vein_cap = bpy.context.active_object
vein_cap.name = "VeinCap"
vein_cap.data.materials.append(dial_mat)
bpy.ops.object.shade_smooth()

gn = vein_cap.modifiers.new("VeinNetwork", "NODES")
gn.node_group = vein_group

# ---------------------------------------------------------------- inlay carving
def carve_inlay(col_obj, style):
    # The top face is tilted (COLUMN axis leans with the dial's indices), so
    # recessing "depth" along its own local normal drops world-space height
    # by a different amount on each side of the ring -- on the shallow side
    # it's nearly zero, so the panel line reads as broken. Instead, inset
    # with depth=0 for the ring topology, then pull the inner vertices down
    # by a fixed amount in WORLD Z, so the groove reads as a uniform ring
    # in the depth map regardless of tilt.
    bm = bmesh.new()
    bm.from_mesh(col_obj.data)
    bm.faces.ensure_lookup_table()
    top_face = max(bm.faces, key=lambda f: f.calc_center_median().z)
    mw = col_obj.matrix_world
    mw_inv = mw.inverted()

    def drop(verts, amount):
        for v in verts:
            world = mw @ v.co
            world.z -= amount
            v.co = mw_inv @ world

    # inset_region reuses the face's ORIGINAL verts as the new (shrunk) inner
    # face, and creates fresh verts for the surrounding ring at the old
    # boundary -- so it's `inner`, not its complement, that needs to drop.
    if style == "artdeco":
        inner = set(top_face.verts)
        res1 = bmesh.ops.inset_region(bm, faces=[top_face], thickness=PANEL_BORDER_2A, depth=0.0)
        drop(inner, PANEL_DEPTH_2A)
        inner_face = next(f for f in res1["faces"] if set(f.verts) == inner)
        bmesh.ops.inset_region(bm, faces=[inner_face], thickness=PANEL_BORDER_2B, depth=0.0)
        drop(inner, PANEL_DEPTH_2B)
    else:
        inner = set(top_face.verts)
        bmesh.ops.inset_region(bm, faces=[top_face], thickness=PANEL_BORDER_1, depth=0.0)
        drop(inner, PANEL_DEPTH_1)

    bm.to_mesh(col_obj.data)
    bm.free()


# ---------------------------------------------------------------- indices
length = COLUMN_EXPOSED + COLUMN_BURIED
t = math.radians(TILT_DEG)
for i in range(12):
    phi = math.radians(i * 30.0)
    radial = Vector((math.sin(phi), math.cos(phi), 0))
    tangent = Vector((math.cos(phi), -math.sin(phi), 0))
    axis = (Vector((0, 0, 1)) * math.cos(t) + radial * math.sin(t)).normalized()
    y_axis = axis.cross(tangent)

    base = radial * INDEX_RADIUS
    center = base + axis * (length / 2 - COLUMN_BURIED)

    bpy.ops.mesh.primitive_cube_add(size=1)
    col = bpy.context.active_object
    col.name = f"Index_{i if i else 12:02d}"
    rot = Matrix((tangent, y_axis, axis)).transposed().to_4x4()
    spin_deg = -(SPIN_START_DEG + SPIN_STEP_DEG * i)
    spin = Matrix.Rotation(math.radians(spin_deg), 4, "Z")
    col.matrix_world = Matrix.Translation(center) @ rot @ spin @ Matrix.Diagonal(
        (COLUMN_WIDTH, COLUMN_WIDTH, length, 1.0))
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    carve_inlay(col, STYLE)

    bev = col.modifiers.new("Bevel", "BEVEL")
    bev.width = BEVEL
    bev.segments = 3
    col.data.materials.append(col_mat)

# ---------------------------------------------------------------- lighting
sun_data = bpy.data.lights.new("Sun", "SUN")
sun_data.energy = 4.0
sun_data.angle = math.radians(3.0)
sun = bpy.data.objects.new("Sun", sun_data)
scene.collection.objects.link(sun)
el, az = math.radians(SUN_ELEVATION), math.radians(SUN_AZIMUTH)
to_light = Vector((math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)))
sun.rotation_euler = to_light.to_track_quat("Z", "Y").to_euler()

world = bpy.data.worlds.new("World")
scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
bg.inputs["Color"].default_value = (0.55, 0.55, 0.55, 1.0)
bg.inputs["Strength"].default_value = 0.6

# ---------------------------------------------------------------- camera
cam_data = bpy.data.cameras.new("Camera")
cam_data.lens = 50
cam_data.sensor_width = 36
half_fov = math.atan(cam_data.sensor_width / 2 / cam_data.lens)
cam_height = (DIAL_RADIUS * 1.06) / math.tan(half_fov)
cam = bpy.data.objects.new("Camera", cam_data)
cam.location = (0, 0, cam_height)
cam.rotation_euler = (0, 0, 0)
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
if MODE in ("both", "depth"):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    z_max = 0.0
    for ob in scene.objects:
        if ob.name.startswith("Index_") or ob.name == "VeinCap":
            ev = ob.evaluated_get(depsgraph)
            mesh = ev.to_mesh()
            z_max = max(z_max, max((ev.matrix_world @ v.co).z for v in mesh.vertices))
            ev.to_mesh_clear()
    print(f"Depth map range: 0 (dial) .. {z_max:.4f} (white)")

    depth_mat = bpy.data.materials.new("DepthOverride")
    depth_mat.use_nodes = True
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
