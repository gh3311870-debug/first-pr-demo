"""Small helpers for building hard-surface game assets with Blender's Python API (bpy).

Blender axes are used throughout: X = right, Y = forward, Z = up.
The glTF exporter converts this to three.js axes (Y up, -Z forward).
"""
import math
import bpy
import bmesh
from mathutils import Vector, Matrix


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def material(name, color, metallic=0.0, roughness=0.5, emissive=None, alpha=1.0):
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    if emissive:
        bsdf.inputs["Emission Color"].default_value = (*emissive, 1.0)
        bsdf.inputs["Emission Strength"].default_value = 4.0
    if alpha < 1.0:
        bsdf.inputs["Alpha"].default_value = alpha
        mat.surface_render_method = "BLENDED"
    return mat


def _link(obj):
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _obj_from_bmesh(name, bm, mat):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    if mat:
        me.materials.append(mat)
    return _link(obj)


def box(name, size, loc, mat, rot=(0, 0, 0)):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    obj = _obj_from_bmesh(name, bm, mat)
    obj.location = loc
    obj.rotation_euler = [math.radians(a) for a in rot]
    return obj


def box_span(name, x, y, z, mat):
    """Box from coordinate ranges: x=(min,max), y=(min,max), z=(min,max)."""
    size = (x[1] - x[0], y[1] - y[0], z[1] - z[0])
    loc = ((x[0] + x[1]) / 2, (y[0] + y[1]) / 2, (z[0] + z[1]) / 2)
    return box(name, size, loc, mat)


def cylinder(name, radius, a0, a1, mat, x=0.0, y=0.0, z=0.0, verts=24, axis="Y", radius2=None):
    """Cylinder whose axis runs along `axis` from coordinate a0 to a1; the other two
    coordinates come from x / y / z."""
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=verts, radius1=radius,
                          radius2=radius if radius2 is None else radius2, depth=abs(a1 - a0))
    obj = _obj_from_bmesh(name, bm, mat)
    mid = (a0 + a1) / 2
    if axis == "Y":
        obj.rotation_euler = (math.radians(-90 if a1 >= a0 else 90), 0, 0)
        obj.location = (x, mid, z)
    elif axis == "X":
        obj.rotation_euler = (0, math.radians(90 if a1 >= a0 else -90), 0)
        obj.location = (mid, y, z)
    else:
        obj.location = (x, y, mid)
    return obj


def prism(name, profile_yz, half_width, mat, x_center=0.0):
    """Extrude a closed 2D profile (list of (y, z) points, CCW) along X."""
    bm = bmesh.new()
    front = [bm.verts.new((x_center - half_width, y, z)) for y, z in profile_yz]
    back = [bm.verts.new((x_center + half_width, y, z)) for y, z in profile_yz]
    n = len(profile_yz)
    bm.faces.new(list(reversed(front)))
    bm.faces.new(back)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((front[i], front[j], back[j], back[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return _obj_from_bmesh(name, bm, mat)


def bevel(obj, width=0.002, segments=2, angle=35):
    mod = obj.modifiers.new("Bevel", "BEVEL")
    mod.width = width
    mod.segments = segments
    mod.limit_method = "ANGLE"
    mod.angle_limit = math.radians(angle)
    mod.harden_normals = False
    return mod


def subtract(obj, cutters):
    for c in cutters:
        mod = obj.modifiers.new("Cut", "BOOLEAN")
        mod.operation = "DIFFERENCE"
        mod.object = c
        mod.solver = "EXACT"
        c.hide_render = True
        c.hide_viewport = True
    return obj


def apply_modifiers(obj):
    """Bake all modifiers into the mesh without relying on operator context."""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True, depsgraph=dg)
    old = obj.data
    obj.modifiers.clear()
    obj.data = me
    bpy.data.meshes.remove(old)


def bend(obj, angle_deg, axis="X", origin=None):
    mod = obj.modifiers.new("Bend", "SIMPLE_DEFORM")
    mod.deform_method = "BEND"
    mod.deform_axis = axis
    mod.angle = math.radians(angle_deg)
    if origin is not None:
        mod.origin = origin
    return mod


def smooth_by_angle(obj, angle=35):
    """Mark sharp edges by angle and shade smooth, so exported normals look crisp."""
    me = obj.data
    for p in me.polygons:
        p.use_smooth = True
    bm = bmesh.new()
    bm.from_mesh(me)
    lim = math.radians(angle)
    sharp = []
    for e in bm.edges:
        if len(e.link_faces) == 2 and e.calc_face_angle(0.0) > lim:
            sharp.append(e.index)
        elif len(e.link_faces) != 2:
            sharp.append(e.index)
    bm.free()
    attr = me.attributes.get("sharp_edge") or me.attributes.new("sharp_edge", "BOOLEAN", "EDGE")
    for i in sharp:
        attr.data[i].value = True


def join(objs, name):
    """Join objects (with transforms applied) into a single mesh object."""
    cutters = [o for o in objs if o.hide_render]
    objs = [o for o in objs if o.type == "MESH" and not o.hide_render]
    for o in objs:
        apply_modifiers(o)
    for c in cutters:
        bpy.data.objects.remove(c, do_unlink=True)
    bm = bmesh.new()
    mats = []
    for o in objs:
        tmp = bmesh.new()
        tmp.from_mesh(o.data)
        tmp.transform(o.matrix_world)
        slot_map = {}
        for i, m in enumerate(o.data.materials):
            if m not in mats:
                mats.append(m)
            slot_map[i] = mats.index(m)
        for f in tmp.faces:
            f.material_index = slot_map.get(f.material_index, 0)
        me_tmp = bpy.data.meshes.new("tmp")
        tmp.to_mesh(me_tmp)
        tmp.free()
        bm.from_mesh(me_tmp)
        bpy.data.meshes.remove(me_tmp)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    for o in objs:
        bpy.data.objects.remove(o, do_unlink=True)
    obj = bpy.data.objects.new(name, me)
    _link(obj)
    smooth_by_angle(obj)
    return obj


def empty(name, loc, parent=None):
    e = bpy.data.objects.new(name, None)
    e.empty_display_size = 0.02
    e.location = loc
    _link(e)
    if parent:
        e.parent = parent
    return e


def box_uv(obj, scale=1.0):
    """World-size box projection UVs so tiling textures keep a real-world scale."""
    me = obj.data
    if not me.uv_layers:
        me.uv_layers.new(name="UVMap")
    uv = me.uv_layers.active.data
    for p in me.polygons:
        n = p.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for li in p.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            if ax == 0:
                u, v = co.y, co.z
            elif ax == 1:
                u, v = co.x, co.z
            else:
                u, v = co.x, co.y
            uv[li].uv = (u * scale, v * scale)


def export_glb(path, objects=None, animations=False):
    bpy.ops.object.select_all(action="DESELECT")
    if objects:
        for o in objects:
            o.select_set(True)
            for c in o.children_recursive:
                c.select_set(True)
    bpy.ops.export_scene.gltf(
        filepath=path,
        export_format="GLB",
        use_selection=bool(objects),
        export_apply=True,
        export_animations=animations,
        export_yup=True,
        export_extras=False,
        export_cameras=False,
        export_lights=False,
    )


def preview(path, target=(0, 0, 0), cam_loc=(0.6, -0.3, 0.25), lens=50, res=(1000, 600), samples=24):
    """Quick Cycles CPU render for checking a model headlessly."""
    scn = bpy.context.scene
    scn.render.engine = "CYCLES"
    scn.cycles.device = "CPU"
    scn.cycles.samples = samples
    scn.render.resolution_x, scn.render.resolution_y = res
    scn.render.filepath = path
    co = bpy.data.objects.get("PreviewCam")
    if co is None:
        world = bpy.data.worlds.new("W")
        world.use_nodes = True
        world.node_tree.nodes["Background"].inputs[0].default_value = (0.55, 0.6, 0.7, 1)
        world.node_tree.nodes["Background"].inputs[1].default_value = 0.6
        scn.world = world
        sun = bpy.data.lights.new("Sun", "SUN")
        sun.energy = 3.5
        so = bpy.data.objects.new("PreviewSun", sun)
        so.rotation_euler = (math.radians(40), math.radians(20), math.radians(30))
        _link(so)
        co = bpy.data.objects.new("PreviewCam", bpy.data.cameras.new("Cam"))
        _link(co)
    co.data.lens = lens
    co.location = cam_loc
    d = Vector(target) - Vector(cam_loc)
    co.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    scn.camera = co
    bpy.ops.render.render(write_still=True)
