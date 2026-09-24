"""Builds the custom Kart Rush models with Blender and exports them as GLB.

Run with the Blender Python module (pip install bpy) or headless Blender:

    python tools/blender/make_kart_models.py
    blender -b -P tools/blender/make_kart_models.py

Outputs item-box.glb, boost-pad.glb, rocket.glb, oil.glb and podium.glb into
assets/kart/models/. Models face +Y in Blender, which becomes +Z (forward for
the Kenney vehicles) after the glTF exporter's Y-up conversion.
"""
import math
import os
import random

import bpy
import bmesh  # must come after bpy when using the pip bpy module

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "assets", "kart", "models")


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def material(name, rgb, metallic=0.0, roughness=0.5, emission=None, strength=1.0, alpha=1.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    if emission:
        bsdf.inputs["Emission Color"].default_value = (*emission, 1.0)
        bsdf.inputs["Emission Strength"].default_value = strength
    if alpha < 1.0:
        bsdf.inputs["Alpha"].default_value = alpha
        mat.blend_method = "BLEND"
    return mat


def assign(obj, mat, smooth=False):
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    for poly in obj.data.polygons:
        poly.use_smooth = smooth


def active():
    return bpy.context.active_object


def join(objs, name):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    obj = active()
    obj.name = name
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    return obj


def text_mesh(body, size, location, rotation=(0, 0, 0), extrude=0.05):
    bpy.ops.object.text_add(location=location, rotation=rotation)
    t = active()
    t.data.body = body
    t.data.size = size
    t.data.extrude = extrude
    t.data.align_x = "CENTER"
    t.data.align_y = "CENTER"
    bpy.ops.object.convert(target="MESH")
    return active()


def export(name):
    path = os.path.normpath(os.path.join(OUT_DIR, name + ".glb"))
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", export_apply=True, export_yup=True)
    print("wrote", path)


def make_item_box():
    """Glassy bevelled cube with a glowing ? on every side. ~1.2 across, centred."""
    reset()
    glass = material("Glass", (0.55, 0.8, 1.0), roughness=0.05, alpha=0.45, emission=(0.3, 0.6, 1.0), strength=0.4)
    mark = material("Mark", (1, 1, 1), emission=(1, 1, 1), strength=1.5)
    bpy.ops.mesh.primitive_cube_add(size=1.2)
    box = active()
    bev = box.modifiers.new("bevel", "BEVEL")
    bev.width = 0.14
    bev.segments = 3
    bpy.ops.object.modifier_apply(modifier=bev.name)
    assign(box, glass, smooth=True)
    parts = [box]
    for rot_z in (0, math.pi / 2, math.pi, -math.pi / 2):
        # Each ? stands on a face, facing outward.
        d = 0.605
        loc = (math.sin(rot_z) * d, -math.cos(rot_z) * d, 0)
        q = text_mesh("?", 0.75, loc, rotation=(math.pi / 2, 0, rot_z), extrude=0.02)
        assign(q, mark)
        parts.append(q)
    for sign in (1, -1):
        q = text_mesh("?", 0.75, (0, 0, sign * 0.605), rotation=(0 if sign > 0 else math.pi, 0, 0), extrude=0.02)
        assign(q, mark)
        parts.append(q)
    join(parts, "item-box")
    export("item-box")


def make_boost_pad():
    """Flat 3 x 4 pad with three glowing chevrons pointing forward (+Y)."""
    reset()
    base_mat = material("PadBase", (0.12, 0.1, 0.18), metallic=0.4, roughness=0.3)
    rim = material("PadRim", (1.0, 0.75, 0.1), metallic=0.5, roughness=0.3)
    glow = material("Chevron", (1.0, 0.45, 0.05), emission=(1.0, 0.5, 0.05), strength=3.0)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.03))
    base = active()
    base.scale = (3.0, 4.0, 0.06)
    bpy.ops.object.transform_apply(scale=True)
    bev = base.modifiers.new("bevel", "BEVEL")
    bev.width = 0.05
    bpy.ops.object.modifier_apply(modifier=bev.name)
    assign(base, base_mat)
    parts = [base]
    for sx in (-1, 1):
        bpy.ops.mesh.primitive_cube_add(size=1, location=(sx * 1.45, 0, 0.06))
        r = active()
        r.scale = (0.12, 4.0, 0.06)
        bpy.ops.object.transform_apply(scale=True)
        assign(r, rim)
        parts.append(r)
    for i in range(3):
        y = -1.1 + i * 1.1
        for sx in (-1, 1):
            bpy.ops.mesh.primitive_cube_add(size=1, location=(sx * 0.45, y, 0.075))
            c = active()
            c.scale = (1.05, 0.28, 0.04)
            c.rotation_euler = (0, 0, sx * -math.radians(35))
            bpy.ops.object.transform_apply(scale=True, rotation=True)
            assign(c, glow)
            parts.append(c)
    join(parts, "boost-pad")
    export("boost-pad")


def make_rocket():
    """Red rocket, nose towards +Y, ~1.3 long."""
    reset()
    red = material("RocketBody", (0.9, 0.12, 0.12), metallic=0.3, roughness=0.35)
    white = material("RocketNose", (0.95, 0.95, 0.95), metallic=0.2, roughness=0.3)
    dark = material("RocketFin", (0.15, 0.15, 0.2), metallic=0.5, roughness=0.4)
    glow = material("Exhaust", (1.0, 0.6, 0.1), emission=(1.0, 0.55, 0.1), strength=4.0)
    rot = (-math.pi / 2, 0, 0)
    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.17, depth=0.8, location=(0, 0, 0), rotation=rot)
    body = active()
    assign(body, red, smooth=True)
    bpy.ops.mesh.primitive_cone_add(vertices=16, radius1=0.17, radius2=0, depth=0.38, location=(0, 0.59, 0), rotation=rot)
    nose = active()
    assign(nose, white, smooth=True)
    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.12, depth=0.12, location=(0, -0.45, 0), rotation=rot)
    noz = active()
    assign(noz, dark, smooth=True)
    bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=0.09, depth=0.03, location=(0, -0.52, 0), rotation=rot)
    flame = active()
    assign(flame, glow)
    parts = [body, nose, noz, flame]
    for k in range(4):
        a = k * math.pi / 2
        bpy.ops.mesh.primitive_cube_add(size=1, location=(math.cos(a) * 0.24, -0.28, math.sin(a) * 0.24))
        fin = active()
        fin.scale = (0.2, 0.28, 0.025)
        fin.rotation_euler = (0, -a, 0)
        bpy.ops.object.transform_apply(scale=True, rotation=True)
        assign(fin, dark)
        parts.append(fin)
    bpy.ops.mesh.primitive_torus_add(major_radius=0.172, minor_radius=0.03, location=(0, 0.25, 0), rotation=rot)
    band = active()
    assign(band, white, smooth=True)
    parts.append(band)
    join(parts, "rocket")
    export("rocket")


def make_oil():
    """Glossy oil puddle, irregular outline, ~2.2 across."""
    reset()
    oil = material("Oil", (0.05, 0.03, 0.09), metallic=0.8, roughness=0.08)
    sheen = material("Sheen", (0.35, 0.2, 0.6), metallic=0.9, roughness=0.05)
    random.seed(4)
    parts = []
    for layer, (scale, z, mat) in enumerate(((1.0, 0.0, oil), (0.45, 0.012, sheen))):
        bm = bmesh.new()
        n = 28
        centre = bm.verts.new((0, 0, z))
        ring = []
        for i in range(n):
            a = i / n * math.tau
            r = scale * (1.0 + 0.18 * math.sin(a * 3 + layer) + 0.1 * math.sin(a * 5 + 1) + random.uniform(-0.05, 0.05))
            ring.append(bm.verts.new((math.cos(a) * r, math.sin(a) * r * 0.85, z)))
        for i in range(n):
            bm.faces.new((centre, ring[i], ring[(i + 1) % n]))
        me = bpy.data.meshes.new(f"oil{layer}")
        bm.to_mesh(me)
        ob = bpy.data.objects.new(f"oil{layer}", me)
        bpy.context.scene.collection.objects.link(ob)
        assign(ob, mat, smooth=True)
        parts.append(ob)
    # A few droplets around the edge.
    for i in range(5):
        a = random.uniform(0, math.tau)
        bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=random.uniform(0.08, 0.16), depth=0.01,
                                            location=(math.cos(a) * 1.35, math.sin(a) * 1.15, 0.0))
        d = active()
        assign(d, oil, smooth=True)
        parts.append(d)
    join(parts, "oil")
    export("oil")


def make_podium():
    """Three-step winners' podium (2nd | 1st | 3rd), 1st step centred at x=0. Steps are 2.4 wide."""
    reset()
    colors = {1: (1.0, 0.78, 0.15), 2: (0.78, 0.8, 0.86), 3: (0.85, 0.5, 0.25)}
    heights = {1: 1.5, 2: 1.0, 3: 0.65}
    xs = {1: 0.0, 2: -2.4, 3: 2.4}
    white = material("Numbers", (1, 1, 1), emission=(1, 1, 1), strength=0.6)
    parts = []
    for place in (1, 2, 3):
        mat = material(f"Step{place}", colors[place], metallic=0.35, roughness=0.35)
        h = heights[place]
        bpy.ops.mesh.primitive_cube_add(size=1, location=(xs[place], 0, h / 2))
        s = active()
        s.scale = (2.4, 2.4, h)
        bpy.ops.object.transform_apply(scale=True)
        bev = s.modifiers.new("bevel", "BEVEL")
        bev.width = 0.06
        bev.segments = 2
        bpy.ops.object.modifier_apply(modifier=bev.name)
        assign(s, mat)
        parts.append(s)
        # Number on the front face (+Y, which faces the camera in game).
        num = text_mesh(str(place), 0.8, (xs[place], 1.21, h / 2), rotation=(math.pi / 2, 0, math.pi), extrude=0.03)
        assign(num, white)
        parts.append(num)
    join(parts, "podium")
    export("podium")


if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    make_item_box()
    make_boost_pad()
    make_rocket()
    make_oil()
    make_podium()
