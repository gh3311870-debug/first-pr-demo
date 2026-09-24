"""
Bake the procedural katana materials to textures and export it for the
web viewer in web/ (katana.glb, plus katana.json + textures/*.jpg).

    python export_katana_web.py            # bpy pip module
    blender -b -P export_katana_web.py --  # Blender binary

The aura is not exported: web/index.html draws it live with a ray-marched
shader that uses the same distance field and flow as make_katana.py.
"""

import os
import sys

import bpy  # must come first when running via the bpy pip module
from mathutils import Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "sword"))
import make_katana  # noqa: E402
from export_web import add_bake_uv, bake_object, glb_to_web  # noqa: E402


def add_blade_uv(ob):
    """Wide texture for the long blade: the -Y flat in the lower half, +Y in the upper."""
    me = ob.data
    src = me.uv_layers["UVMap"]
    uv = me.uv_layers.new(name="BakeUV")
    me.uv_layers.active = uv
    for poly in me.polygons:
        upper = sum(me.vertices[v].co.y for v in poly.vertices) >= 0
        for li in poly.loop_indices:
            s, v = src.data[li].uv
            u = s / make_katana.NAGASA
            vv = min(max(v, 0.0), 1.0) * 0.47 + (0.515 if upper else 0.015)
            uv.data[li].uv = (u, vv)


def main():
    out_dir = os.path.join(HERE, "web")
    os.makedirs(out_dir, exist_ok=True)
    scene, _ = make_katana.build_scene("crimson")

    # only the katana itself is baked and exported; the aura, floor, backdrop
    # and lights would otherwise show up in the ambient-occlusion bakes
    keep = {"Katana", "Blade", "Habaki", "Seppa", "Tsuba", "Tsuka", "Fittings", "Menuki"}
    for ob in list(bpy.data.objects):
        if ob.name not in keep:
            bpy.data.objects.remove(ob)
    root = bpy.data.objects["Katana"]
    root.matrix_world = Matrix.Identity(4)
    bpy.context.view_layer.update()
    scene.cycles.device = "CPU"

    add_blade_uv(bpy.data.objects["Blade"])
    for n in ("Habaki", "Seppa", "Tsuba", "Tsuka", "Fittings", "Menuki"):
        add_bake_uv(bpy.data.objects[n])

    bake_object(bpy.data.objects["Blade"], (4096, 512))
    bake_object(bpy.data.objects["Tsuka"], 2048)
    bake_object(bpy.data.objects["Tsuba"], 1024, ao_heavy=True)
    bake_object(bpy.data.objects["Habaki"], 512, ao_heavy=True)
    bake_object(bpy.data.objects["Fittings"], 512)
    bake_object(bpy.data.objects["Seppa"], 256)
    bake_object(bpy.data.objects["Menuki"], 256, ao_heavy=True)

    blade = bpy.data.objects["Blade"]
    blade.data.uv_layers.remove(blade.data.uv_layers["UVMap"])

    for o in bpy.context.view_layer.objects:
        o.select_set(o.name in keep)
    glb = os.path.join(out_dir, "katana.glb")
    bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB", use_selection=True,
                              export_image_format="JPEG", export_jpeg_quality=90,
                              export_lights=False, export_cameras=False, export_apply=True)
    glb_to_web(glb, out_dir, name="katana.json")
    print("Exported", glb, os.path.getsize(glb) // 1024, "KB, plus katana.json + textures/")


if __name__ == "__main__":
    main()
