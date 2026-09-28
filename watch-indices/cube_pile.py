"""Watch dial covered by a carpet of cubes dropped onto it, viewed from the top.

Variant of watch_indices.py: same dial, camera, lighting and depth pass, but the
12 indices are replaced by cubes. A static bed of flat cubes (placed on a hex grid,
no simulation) guarantees nothing of the dial shows through; a rigid-body layer of
cubes is dropped on top of it, held in by an invisible wall removed after the drop.

Run:  blender --background --python cube_pile.py -- [resolution] [samples] [mode]
Writes cube_pile.blend, cube_pile.png and cube_pile_depth.png next to this script.
"""
import bmesh
import bpy
import math
import os
import random
import sys
from mathutils import Vector, Matrix, Euler

# ---------------------------------------------------------------- parameters
DIAL_RADIUS     = 1.00   # dial disc radius (scene units)
DIAL_THICKNESS  = 0.05
CUBE_SIZE       = 0.065  # cube side
TOP_CUBE_COUNT  = 800    # simulated cubes dropped on top of the bed
BED_SPACING     = 0.8    # bed hex spacing as a fraction of cube side (< 0.866 = no gaps)
BED_TILT_DEG    = 8.0    # random tilt of bed cubes so they don't read as a flat floor
BEVEL           = CUBE_SIZE * 0.03  # edge rounding on cubes (catches highlights)
DROP_SEED       = 3      # change to get a different pile
SIM_FRAMES      = 240    # frames simulated at 24 fps; long enough to settle

# Concept 3 (pass "indices" as 4th argument): the 12 random-spin watch indices
# rising out of the carpet. Same shape as watch_indices.py SPIN_MODE="random".
INDEX_RADIUS    = 0.52   # where each column meets the dial
INDEX_WIDTH     = 0.15   # square cross-section side
INDEX_ABOVE_PILE = 0.12  # length rising above the carpet surface (along the column axis)
PILE_SURFACE    = 0.16   # approx. carpet surface height the indices rise out of
INDEX_BURIED    = 0.10   # length hidden below the dial surface
INDEX_TILT_DEG  = 35.0   # lean from vertical, toward the rim
INDEX_BEVEL     = 0.004
INDEX_SPIN_SEED = 7      # same seed as watch_indices.py -> same spins

DIAL_COLOR      = (0.015, 0.025, 0.06, 1.0)   # deep navy
CUBE_COLOR      = (0.85, 0.85, 0.87, 1.0)     # steel
SUN_ELEVATION   = 50.0   # degrees above horizon
SUN_AZIMUTH     = 135.0  # degrees, 0 = light coming from 12 o'clock
TRANSPARENT_BG  = True

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
RESOLUTION = int(argv[0]) if len(argv) > 0 else 3000
SAMPLES    = int(argv[1]) if len(argv) > 1 else 256
MODE       = argv[2] if len(argv) > 2 else "both"   # both | beauty | depth
INDICES    = len(argv) > 3 and argv[3] == "indices"
NAME       = "cube_pile_indices" if INDICES else "cube_pile"

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
BLEND_PATH = os.path.join(OUT_DIR, f"{NAME}.blend")
PNG_PATH = os.path.join(OUT_DIR, f"{NAME}.png")
DEPTH_PATH = os.path.join(OUT_DIR, f"{NAME}_depth.png")

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


def add_rigid_body(ob, kind, shape, **props):
    # rigidbody.object_add acts on the active object; freshly added primitives
    # are already active, so no select_all (which gets slow with thousands of cubes).
    bpy.context.view_layer.objects.active = ob
    bpy.ops.rigidbody.object_add(type=kind)
    rb = ob.rigid_body
    rb.collision_shape = shape
    rb.use_margin = True
    rb.collision_margin = 0.0005
    for k, v in props.items():
        setattr(rb, k, v)


dial_mat = make_material("Dial", DIAL_COLOR, 0.0, 0.75)
dial_mat.node_tree.nodes["Principled BSDF"].inputs["Specular IOR Level"].default_value = 0.15
cube_mat = make_material("Cube", CUBE_COLOR, 1.0, 0.22)

# ---------------------------------------------------------------- dial
bpy.ops.mesh.primitive_cylinder_add(
    vertices=256, radius=DIAL_RADIUS, depth=DIAL_THICKNESS,
    location=(0, 0, -DIAL_THICKNESS / 2))
dial = bpy.context.active_object
dial.name = "Dial"
dial.data.materials.append(dial_mat)
bpy.ops.object.shade_smooth()

bpy.ops.rigidbody.world_add()
rbw = scene.rigidbody_world
rbw.substeps_per_frame = 10
rbw.solver_iterations = 10
rbw.point_cache.frame_start = 1
rbw.point_cache.frame_end = SIM_FRAMES
scene.frame_start = 1
scene.frame_end = SIM_FRAMES

add_rigid_body(dial, "PASSIVE", "CYLINDER", friction=0.6, restitution=0.1)

# ---------------------------------------------------------------- containment wall
WALL_SEGMENTS, WALL_T, WALL_H = 72, 0.1, 4.0
walls = []
seg_len = 2 * math.pi * (DIAL_RADIUS + WALL_T) / WALL_SEGMENTS * 1.15
for k in range(WALL_SEGMENTS):
    a = 2 * math.pi * k / WALL_SEGMENTS
    r = DIAL_RADIUS + WALL_T / 2
    bpy.ops.mesh.primitive_cube_add(size=1, location=(r * math.cos(a), r * math.sin(a), WALL_H / 2))
    w = bpy.context.active_object
    w.name = f"Wall_{k:02d}"
    w.rotation_euler = (0, 0, a)
    w.scale = (WALL_T, seg_len, WALL_H)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    add_rigid_body(w, "PASSIVE", "BOX", friction=0.3)
    walls.append(w)

# ---------------------------------------------------------------- indices (concept 3)
# Added before the drop as passive colliders so the cubes pile up around them.
index_half_diag = INDEX_WIDTH * math.sqrt(2) / 2
indices = []
index_top_z = 0.0     # highest point of the columns; spawn layers above it needn't avoid them
index_segments = []   # (base_xy, top_xy) of each column's footprint, to keep cubes clear
if INDICES:
    t = math.radians(INDEX_TILT_DEG)
    exposed = PILE_SURFACE / math.cos(t) + INDEX_ABOVE_PILE
    length = exposed + INDEX_BURIED
    spin_rng = random.Random(INDEX_SPIN_SEED)
    for i in range(12):
        phi = math.radians(i * 30.0)                       # 0 = 12 o'clock, clockwise
        radial = Vector((math.sin(phi), math.cos(phi), 0))
        tangent = Vector((math.cos(phi), -math.sin(phi), 0))
        axis = (Vector((0, 0, 1)) * math.cos(t) + radial * math.sin(t)).normalized()
        y_axis = axis.cross(tangent)
        base = radial * INDEX_RADIUS
        center = base + axis * (length / 2 - INDEX_BURIED)

        bpy.ops.mesh.primitive_cube_add(size=1)
        col = bpy.context.active_object
        col.name = f"Index_{i if i else 12:02d}"
        rot = Matrix((tangent, y_axis, axis)).transposed().to_4x4()
        spin = Matrix.Rotation(math.radians(spin_rng.uniform(0.0, 90.0)), 4, "Z")
        col.matrix_world = Matrix.Translation(center) @ rot @ spin @ Matrix.Diagonal(
            (INDEX_WIDTH, INDEX_WIDTH, length, 1.0))
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        col.data.materials.append(cube_mat)
        bev = col.modifiers.new("Bevel", "BEVEL")
        bev.width = INDEX_BEVEL
        bev.segments = 3
        add_rigid_body(col, "PASSIVE", "BOX", friction=0.6, restitution=0.1)
        indices.append(col)
        top = base + axis * exposed
        index_segments.append((base.xy, top.xy))
        index_top_z = max(index_top_z, top.z + index_half_diag)
    print(f"Indices: 12 columns, {exposed:.3f} exposed along the axis", flush=True)


def near_index(x, y, pad, max_frac=1.0):
    """True if (x, y) is within pad of a column's footprint (base -> top, or only the
    first max_frac of it)."""
    p = Vector((x, y))
    for a, b in index_segments:
        ab = (b - a) * max_frac
        k = max(0.0, min(1.0, (p - a).dot(ab) / ab.length_squared))
        if (p - (a + ab * k)).length < pad:
            return True
    return False


bed_frac = CUBE_SIZE / (PILE_SURFACE + INDEX_ABOVE_PILE)   # part of the column at bed height

# ---------------------------------------------------------------- bed: static filler layer
# Flat cubes on a hex grid, merged into one static mesh. Hex spacing below 0.866 x
# the cube side guarantees full coverage at any yaw (each cube covers its inscribed
# circle), so the dial can't show through; the simulated cubes land on top of it.
rng = random.Random(DROP_SEED)
bm = bmesh.new()
d = CUBE_SIZE * BED_SPACING
row_h = d * math.sqrt(3) / 2
reach = DIAL_RADIUS - CUBE_SIZE / 2
bed_count = 0
for row in range(-int(reach / row_h) - 1, int(reach / row_h) + 2):
    for col in range(-int(reach / d) - 2, int(reach / d) + 2):
        j = d * 0.04
        x = col * d + (d / 2 if row % 2 else 0) + rng.uniform(-j, j)
        y = row * row_h + rng.uniform(-j, j)
        if math.hypot(x, y) > reach:
            continue
        if near_index(x, y, index_half_diag + CUBE_SIZE * 0.3, bed_frac):
            continue
        tilt = math.radians(BED_TILT_DEG)
        rot = Euler((rng.uniform(-tilt, tilt), rng.uniform(-tilt, tilt), rng.uniform(0, math.pi / 2)))
        m = Matrix.Translation((x, y, CUBE_SIZE / 2)) @ rot.to_matrix().to_4x4()
        bmesh.ops.create_cube(bm, size=CUBE_SIZE, matrix=m)
        bed_count += 1
bed_mesh = bpy.data.meshes.new("CubeBed")
bm.to_mesh(bed_mesh)
bm.free()
bed_mesh.materials.append(cube_mat)
bed = bpy.data.objects.new("CubeBed", bed_mesh)
scene.collection.objects.link(bed)
add_rigid_body(bed, "PASSIVE", "MESH", friction=0.6, restitution=0.1)
print(f"Bed: {bed_count} static cubes", flush=True)

# ---------------------------------------------------------------- top layer: simulated cubes
spacing = CUBE_SIZE * math.sqrt(3) * 1.08   # spawn spacing: no overlaps at any rotation
spawn_r = DIAL_RADIUS - CUBE_SIZE * 0.9    # up to the wall (cube half-diagonal is 0.87 x side)


def layer_cells(avoid_indices):
    """Grid positions inside the circle, randomly shifted and rotated per layer so
    cubes don't fall straight onto the one below and stack into towers."""
    ox, oy = rng.uniform(0, spacing), rng.uniform(0, spacing)
    rot = rng.uniform(0, math.pi / 2)
    cs, sn = math.cos(rot), math.sin(rot)
    n = int(spawn_r / spacing) + 2
    cells = []
    for gx in range(-n, n + 1):
        for gy in range(-n, n + 1):
            px, py = gx * spacing + ox, gy * spacing + oy
            x, y = px * cs - py * sn, px * sn + py * cs
            if math.hypot(x, y) > spawn_r:
                continue
            if avoid_indices and near_index(x, y, index_half_diag + CUBE_SIZE * 0.9):
                continue
            cells.append((x, y))
    rng.shuffle(cells)
    return cells


# One shared mesh and bpy.data calls instead of an operator per cube: much faster.
cube_mesh = bpy.data.meshes.new("Cube")
bm = bmesh.new()
bmesh.ops.create_cube(bm, size=CUBE_SIZE)
bm.to_mesh(cube_mesh)
bm.free()
cube_mesh.materials.append(cube_mat)

cubes = []
layer = 0
while len(cubes) < TOP_CUBE_COUNT:
    z = 0.25 + layer * spacing
    for (x, y) in layer_cells(z < index_top_z + CUBE_SIZE):
        if len(cubes) >= TOP_CUBE_COUNT:
            break
        j = spacing * 0.05
        c = bpy.data.objects.new(f"Cube_{len(cubes):04d}", cube_mesh)
        c.location = (x + rng.uniform(-j, j), y + rng.uniform(-j, j), z)
        c.rotation_euler = Euler([rng.uniform(0, 2 * math.pi) for _ in range(3)])
        scene.collection.objects.link(c)
        cubes.append(c)
    layer += 1

bpy.ops.object.select_all(action="DESELECT")
for c in cubes:
    c.select_set(True)
bpy.context.view_layer.objects.active = cubes[0]
bpy.ops.rigidbody.objects_add(type="ACTIVE")               # one call for all cubes
for c in cubes:
    rb = c.rigid_body
    rb.collision_shape = "BOX"
    rb.use_margin = True
    rb.collision_margin = 0.0005
    rb.mass = 1.0
    rb.friction = 0.6
    rb.restitution = 0.1
    rb.linear_damping = 0.2
    rb.angular_damping = 0.3
    rb.use_deactivation = True
print(f"Spawned {len(cubes)} simulated cubes in {layer} layers", flush=True)

# ---------------------------------------------------------------- simulate and freeze
for f in range(1, SIM_FRAMES + 1):
    scene.frame_set(f)
    if f % 20 == 0:
        print(f"sim frame {f}/{SIM_FRAMES}", flush=True)
    if f == SIM_FRAMES - 24:
        before = {c.name: c.matrix_world.translation.copy() for c in cubes}
final = {c.name: c.matrix_world.copy() for c in cubes}
moved = sorted(((final[c.name].translation - before[c.name]).length, c.name) for c in cubes)[-5:]
print("Largest movement over the last second:", [(n, round(d, 3)) for d, n in moved])

# Cubes that came to rest on top of a column hide it; drop them from the scene.
perched = [c for c in cubes if final[c.name].translation.z > PILE_SURFACE + CUBE_SIZE * 0.3
           and near_index(*final[c.name].translation.xy, index_half_diag + CUBE_SIZE)]
if perched:
    print(f"Removing {len(perched)} cubes resting on the indices")
    for c in perched:
        cubes.remove(c)
        bpy.data.objects.remove(c, do_unlink=True)

bpy.ops.object.select_all(action="SELECT")
bpy.ops.rigidbody.objects_remove()
bpy.ops.rigidbody.world_remove()
for w in walls:
    bpy.data.objects.remove(w, do_unlink=True)
scene.frame_set(1)
for ob in cubes + [bed]:
    if ob is not bed:
        ob.matrix_world = final[ob.name]
    bev = ob.modifiers.new("Bevel", "BEVEL")
    bev.width = BEVEL
    bev.segments = 3

tops = sorted(c.matrix_world.translation.z for c in cubes)
outside = sum(1 for c in cubes if c.matrix_world.translation.xy.length > DIAL_RADIUS)
bands = [0.0, 0.25, 0.5, 0.7, 0.85, 1.0]
density = []
for lo, hi in zip(bands, bands[1:]):
    n_in = sum(1 for c in cubes if lo <= c.matrix_world.translation.xy.length < hi)
    density.append(f"{lo:.2f}-{hi:.2f}: {n_in / (math.pi * (hi * hi - lo * lo)):.0f}")
print("Top cubes per unit area by radius:", ", ".join(density))
print(f"Settled: cube center z min {tops[0]:.3f} / median {tops[len(tops)//2]:.3f} / max {tops[-1]:.3f}; "
      f"{outside} outside dial")


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
# black and the highest point of any cube is pure white.
if MODE in ("both", "depth"):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    z_max = 0.0
    for ob in cubes + [bed] + indices:
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
