"""Builds the custom Cloud Hopper models with Blender and exports them as GLB.

Run with the Blender Python module (pip install bpy) or headless Blender:

    python tools/blender/make_hopper_models.py
    blender -b -P tools/blender/make_hopper_models.py

Outputs spring.glb, spikeball.glb and gem.glb into assets/hopper/models/.
Units match the Kenney platformer kit: 1 Blender unit = 1 tile, +Y up in glTF.
"""
import math
import os

import bpy
from mathutils import Vector

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "assets", "hopper", "models")


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def material(name, rgb, metallic=0.0, roughness=0.6, emission=None):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    if emission:
        bsdf.inputs["Emission Color"].default_value = (*emission, 1.0)
        bsdf.inputs["Emission Strength"].default_value = 0.6
    return mat


def assign(obj, mat, smooth=False):
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    for poly in obj.data.polygons:
        poly.use_smooth = smooth


def join(objs, name):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    obj = bpy.context.active_object
    obj.name = name
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    return obj


def export(name):
    path = os.path.normpath(os.path.join(OUT_DIR, name + ".glb"))
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", export_apply=True, export_yup=True)
    print("wrote", path)


def make_spring():
    """Bounce pad: grey base, red coil, red/white striped cap. Height ~0.45."""
    reset()
    grey = material("Metal", (0.55, 0.58, 0.62), metallic=0.6, roughness=0.35)
    red = material("Red", (0.9, 0.18, 0.2))
    white = material("White", (0.95, 0.95, 0.95))

    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.48, depth=0.12, location=(0, 0, 0.06))
    base = bpy.context.active_object
    assign(base, grey, smooth=True)
    bpy.ops.object.shade_auto_smooth()

    coils = []
    for i in range(3):
        bpy.ops.mesh.primitive_torus_add(major_radius=0.28, minor_radius=0.045, major_segments=24, minor_segments=8,
                                         location=(0, 0, 0.17 + i * 0.075))
        c = bpy.context.active_object
        assign(c, red, smooth=True)
        coils.append(c)

    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.44, depth=0.08, location=(0, 0, 0.39))
    cap = bpy.context.active_object
    assign(cap, red, smooth=True)
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.26, depth=0.085, location=(0, 0, 0.392))
    dot = bpy.context.active_object
    assign(dot, white, smooth=True)

    join([base, *coils, cap, dot], "spring")
    export("spring")


def make_spikeball():
    """Enemy: purple ball covered in cones with two big eyes facing -Y (glTF +Z)."""
    reset()
    purple = material("Body", (0.45, 0.2, 0.75), roughness=0.45)
    spike_mat = material("Spike", (0.95, 0.85, 0.4), metallic=0.3, roughness=0.3)
    white = material("EyeWhite", (1, 1, 1), roughness=0.2)
    black = material("Pupil", (0.03, 0.03, 0.05), roughness=0.2)

    r = 0.35
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=16, radius=r, location=(0, 0, 0))
    body = bpy.context.active_object
    assign(body, purple, smooth=True)
    parts = [body]

    # Spikes on a fibonacci sphere, skipping the face area.
    n = 26
    golden = math.pi * (3 - math.sqrt(5))
    for i in range(n):
        y = 1 - (i / (n - 1)) * 2
        rad = math.sqrt(1 - y * y)
        th = golden * i
        d = (math.cos(th) * rad, y, math.sin(th) * rad)  # x, y(forward/back), z
        if d[1] < -0.55 and abs(d[2]) < 0.6:
            continue  # leave the face clear
        bpy.ops.mesh.primitive_cone_add(vertices=8, radius1=0.08, radius2=0.0, depth=0.2,
                                        location=(d[0] * (r + 0.05), d[1] * (r + 0.05), d[2] * (r + 0.05)))
        cone = bpy.context.active_object
        cone.rotation_mode = "QUATERNION"
        cone.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(Vector(d))
        assign(cone, spike_mat)
        parts.append(cone)

    for side in (-1, 1):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=10, radius=0.1,
                                             location=(side * 0.12, -0.29, 0.08))
        eye = bpy.context.active_object
        assign(eye, white, smooth=True)
        bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8, radius=0.05,
                                             location=(side * 0.12, -0.375, 0.08))
        pupil = bpy.context.active_object
        assign(pupil, black, smooth=True)
        parts += [eye, pupil]

    join(parts, "spikeball")
    export("spikeball")


def make_gem():
    """Big collectible: faceted crystal, ~0.6 tall, centred on origin."""
    reset()
    cyan = material("Crystal", (0.25, 0.85, 1.0), metallic=0.1, roughness=0.12, emission=(0.1, 0.5, 0.8))
    bpy.ops.mesh.primitive_cone_add(vertices=6, radius1=0.25, radius2=0.0, depth=0.2, location=(0, 0, 0.1))
    top = bpy.context.active_object
    bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=0.25, depth=0.08, location=(0, 0, -0.04))
    band = bpy.context.active_object
    bpy.ops.mesh.primitive_cone_add(vertices=6, radius1=0.25, radius2=0.0, depth=0.35,
                                    location=(0, 0, -0.255), rotation=(math.pi, 0, 0))
    bottom = bpy.context.active_object
    for o in (top, band, bottom):
        assign(o, cyan)
    gem = join([top, band, bottom], "gem")
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.remove_doubles(threshold=0.001)
    bpy.ops.object.mode_set(mode="OBJECT")
    export("gem")


if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    make_spring()
    make_spikeball()
    make_gem()
