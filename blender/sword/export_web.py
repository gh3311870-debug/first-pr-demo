"""
Bake the procedural sword materials to image textures and export a .glb
for real-time viewers (three.js, model-viewer, Sketchfab, game engines).

    python export_web.py                 # bpy pip module
    blender -b -P export_web.py --       # Blender binary

Also writes sword.json + textures/*.jpg next to the .glb: the same model as
glTF JSON, which web/index.html loads.

Options: --out PATH (default web/sword.glb), --size N (table texture size,
default 2048; the blade uses 2N x N/4 and the hilt parts N/2).
"""

import argparse
import base64
import json
import math
import struct
import os
import sys

import bpy  # must come first when running via the bpy pip module
import bmesh
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_sword  # noqa: E402


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else argv[1:]
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=os.path.join(HERE, "web", "sword.glb"))
    p.add_argument("--size", type=int, default=2048)
    return p.parse_args(argv)


def select_only(ob):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob


def add_bake_uv(ob, margin=0.004):
    me = ob.data
    uv = me.uv_layers.new(name="BakeUV")
    me.uv_layers.active = uv
    select_only(ob)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=margin,
                             scale_to_bounds=False)
    bpy.ops.uv.pack_islands(rotate=True, margin=margin)
    bpy.ops.object.mode_set(mode="OBJECT")


def add_blade_uv(ob):
    """The blade is 16x longer than wide, so it gets a wide texture: the top flat
    fills the lower half, the bottom flat the upper half, both running full length."""
    me = ob.data
    src = me.uv_layers["UVMap"]
    uv = me.uv_layers.new(name="BakeUV")
    me.uv_layers.active = uv
    half_w = make_sword.BLADE_W0 / 2
    for i, d in enumerate(src.data):
        z, xo = d.uv
        bottom = xo > half_w + 0.05          # make_sword offsets the bottom face by 0.2
        x = xo - (0.2 if bottom else 0.0)
        u = (z - make_sword.BLADE_START) / make_sword.BLADE_LEN
        v = (x + half_w) / (2 * half_w) * 0.47 + (0.515 if bottom else 0.015)
        uv.data[i].uv = (u, v)


def find_bsdf(mat):
    return next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")


def bake_channel(ob, mat, socket_name, img, samples):
    """Route one Principled input through an emission shader and bake it."""
    nt = mat.node_tree
    bsdf = find_bsdf(mat)
    out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    em = nt.nodes.new("ShaderNodeEmission")
    sock = bsdf.inputs[socket_name]
    if sock.is_linked:
        src = sock.links[0].from_socket
        nt.links.new(src, em.inputs["Color"])
    else:
        v = sock.default_value
        em.inputs["Color"].default_value = (tuple(v) if hasattr(v, "__len__") else (v, v, v, 1.0))
    orig = out.inputs["Surface"].links[0].from_socket
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    nt.nodes.active = tex
    bpy.context.scene.cycles.samples = samples
    select_only(ob)
    bpy.ops.object.bake(type="EMIT", margin=8, use_clear=True)
    nt.links.new(orig, out.inputs["Surface"])
    nt.nodes.remove(em)
    nt.nodes.remove(tex)


def bake_normal(ob, mat, img, samples):
    nt = mat.node_tree
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    nt.nodes.active = tex
    bpy.context.scene.cycles.samples = samples
    select_only(ob)
    bpy.ops.object.bake(type="NORMAL", normal_space="TANGENT", margin=8, use_clear=True)
    nt.nodes.remove(tex)


def new_image(name, size, non_color):
    w, h = size if isinstance(size, tuple) else (size, size)
    img = bpy.data.images.new(name, w, h, alpha=False, float_buffer=False)
    if non_color:
        img.colorspace_settings.name = "Non-Color"
    return img


def bake_object(ob, size, ao_heavy=False):
    mat = ob.data.materials[0]
    tag = ob.name
    imgs = {
        "Base Color": new_image(f"{tag}_basecolor", size, False),
        "Roughness": new_image(f"{tag}_roughness", size, True),
        "Metallic": new_image(f"{tag}_metallic", size, True),
    }
    normal = new_image(f"{tag}_normal", size, True)
    s = 24 if ao_heavy else 4
    for sock, img in imgs.items():
        bake_channel(ob, mat, sock, img, s)
    bake_normal(ob, mat, normal, 8)

    # replace the procedural material with a plain image-textured one
    baked = bpy.data.materials.new(f"{tag} (baked)")
    baked.use_nodes = True
    nt = baked.node_tree
    bsdf = find_bsdf(baked)
    uvn = nt.nodes.new("ShaderNodeUVMap")
    uvn.uv_map = "BakeUV"

    def tex(img):
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = img
        nt.links.new(uvn.outputs[0], t.inputs["Vector"])
        return t

    nt.links.new(tex(imgs["Base Color"]).outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(tex(imgs["Roughness"]).outputs["Color"], bsdf.inputs["Roughness"])
    nt.links.new(tex(imgs["Metallic"]).outputs["Color"], bsdf.inputs["Metallic"])
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nm.uv_map = "BakeUV"
    nt.links.new(tex(normal).outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    for img in list(imgs.values()) + [normal]:
        img.file_format = "JPEG"
        img.pack()
    ob.data.materials[0] = baked


def web_table(scene, size):
    """A smaller table with 0-1 UVs so the baked wood keeps its detail."""
    old = bpy.data.objects["Table"]
    mat = old.data.materials[0]
    bm = bmesh.new()
    bm.loops.layers.uv.new("BakeUV")
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=0.8, calc_uvs=True)
    me = bpy.data.meshes.new("TableWeb")
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("Table", me)
    scene.collection.objects.link(ob)
    ob.matrix_world = old.matrix_world.copy()
    # centre the square under the middle of the sword
    mid = bpy.data.objects["Sword"].matrix_world @ Vector((0, 0, 0.29))
    ob.location = (mid.x, mid.y, 0.0)
    me.materials.append(mat)
    bpy.data.objects.remove(old)
    ob.name = "Table"
    return ob


def glb_to_web(glb_path, out_dir):
    """Split a .glb into sword.json (glTF JSON with the geometry buffer embedded)
    plus plain .jpg textures, for hosts that only serve common web file types."""
    data = open(glb_path, "rb").read()
    jlen = struct.unpack_from("<I", data, 12)[0]
    gltf = json.loads(data[20:20 + jlen])
    blob = data[20 + jlen + 8:]
    views = gltf["bufferViews"]
    image_views = {im["bufferView"] for im in gltf.get("images", [])}

    tex_dir = os.path.join(out_dir, "textures")
    os.makedirs(tex_dir, exist_ok=True)
    for im in gltf.get("images", []):
        bv = views[im["bufferView"]]
        off = bv.get("byteOffset", 0)
        ext = ".png" if im.get("mimeType") == "image/png" else ".jpg"
        rel = f"textures/{im['name']}{ext}"
        with open(os.path.join(out_dir, rel), "wb") as f:
            f.write(blob[off:off + bv["byteLength"]])
        im["uri"] = rel
        del im["bufferView"]
        im.pop("mimeType", None)

    # rebuild the binary buffer from the non-image views only
    remap, new_views, out = {}, [], bytearray()
    for i, bv in enumerate(views):
        if i in image_views:
            continue
        while len(out) % 4:
            out.append(0)
        off = bv.get("byteOffset", 0)
        nbv = dict(bv, byteOffset=len(out), buffer=0)
        out += blob[off:off + bv["byteLength"]]
        remap[i] = len(new_views)
        new_views.append(nbv)
    gltf["bufferViews"] = new_views
    for acc in gltf.get("accessors", []):
        if "bufferView" in acc:
            acc["bufferView"] = remap[acc["bufferView"]]
    gltf["buffers"] = [{
        "byteLength": len(out),
        "uri": "data:application/octet-stream;base64," + base64.b64encode(bytes(out)).decode(),
    }]
    with open(os.path.join(out_dir, "sword.json"), "w") as f:
        json.dump(gltf, f, separators=(",", ":"))


def main():
    args = parse_args()
    scene, _ = make_sword.build_scene()
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.render.bake.margin = 8

    table = web_table(scene, args.size)
    for n in ("Guard", "Grip", "Fittings"):
        add_bake_uv(bpy.data.objects[n])
    add_blade_uv(bpy.data.objects["Blade"])

    bake_object(bpy.data.objects["Blade"], (args.size * 2, args.size // 4))
    bake_object(bpy.data.objects["Guard"], args.size // 2, ao_heavy=True)
    bake_object(bpy.data.objects["Grip"], args.size // 2)
    bake_object(bpy.data.objects["Fittings"], args.size // 2, ao_heavy=True)
    bake_object(table, args.size)

    # the blade's metre-based UVMap only drove the procedural shader
    blade = bpy.data.objects["Blade"]
    blade.data.uv_layers.remove(blade.data.uv_layers["UVMap"])

    for o in bpy.context.view_layer.objects:
        o.select_set(o.name in ("Sword", "Table", "Blade", "Guard", "Grip", "Fittings"))
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=os.path.abspath(args.out),
        export_format="GLB",
        use_selection=True,
        export_image_format="JPEG",
        export_jpeg_quality=90,
        export_lights=False,
        export_cameras=False,
        export_apply=True,
    )
    print("Exported", args.out, os.path.getsize(args.out) // 1024, "KB")
    glb_to_web(args.out, os.path.dirname(os.path.abspath(args.out)))
    print("Wrote sword.json + textures/ for the web viewer")


if __name__ == "__main__":
    main()
