"""Build assets/frontline/props.glb: level props modeled procedurally in Blender.

Every prop is a single joined mesh whose origin sits on the ground (z = 0), with
world-scale box-projected UVs (1 UV unit = 1 meter) so the game can apply tiling PBR
textures by material name.

Usage: python3 build_props.py <out.glb> [preview.png]
"""
import os
import sys
import math
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
import bmesh
from mathutils import Vector, Matrix

import blender_util as U

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
OUT = args[0]
PREVIEW = args[1] if len(args) > 1 else None
random.seed(7)

U.reset_scene()
M = {
    "wood": U.material("Wood", (0.45, 0.33, 0.22), roughness=0.8),
    "concrete": U.material("Concrete", (0.55, 0.53, 0.5), roughness=0.9),
    "sandbag": U.material("Sandbag", (0.45, 0.38, 0.26), roughness=0.95),
    "hesco": U.material("Hesco", (0.5, 0.43, 0.32), roughness=0.95),
    "container": U.material("ContainerPaint", (0.35, 0.12, 0.08), metallic=0.3, roughness=0.6),
    "barrel": U.material("BarrelPaint", (0.1, 0.2, 0.35), metallic=0.4, roughness=0.55),
    "dark": U.material("Metal_Dark", (0.04, 0.04, 0.045), metallic=0.8, roughness=0.5),
    "galv": U.material("Metal_Galv", (0.5, 0.5, 0.5), metallic=0.9, roughness=0.45),
    "rubber": U.material("Rubber", (0.02, 0.02, 0.02), roughness=0.92),
    "burnt": U.material("BurntMetal", (0.12, 0.07, 0.05), metallic=0.5, roughness=0.8),
    "olive": U.material("OliveMetal", (0.1, 0.12, 0.06), metallic=0.5, roughness=0.6),
    "bark": U.material("Palm_Bark", (0.3, 0.24, 0.17), roughness=0.95),
    "leaf": U.material("Palm_Leaf", (0.2, 0.3, 0.1), roughness=0.7),
    "plastic": U.material("PlasticBlack", (0.03, 0.03, 0.03), roughness=0.5),
    "white": U.material("MetalWhite", (0.6, 0.6, 0.58), metallic=0.3, roughness=0.5),
    "canvas": U.material("Canvas", (0.3, 0.3, 0.2), roughness=0.95),
}

PROPS = []


def finish(parts, name, uv=True):
    obj = U.join(parts, name)
    if uv:
        U.box_uv(obj)
    PROPS.append(obj)
    return obj


def rounded_block(name, size, loc, mat, rot=(0, 0, 0), roundness=0.6, cuts=3, smooth=True):
    """Pillow-like block (sandbags, HESCO) from a subdivided cube cast toward a sphere."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2.0)
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=cuts, use_grid_fill=True)
    for v in bm.verts:
        c = v.co
        s = c.normalized() * math.sqrt(3) * 0.62
        v.co = c.lerp(Vector((max(-1, min(1, s.x)), max(-1, min(1, s.y)), max(-1, min(1, s.z)))),
                      roundness)
    bmesh.ops.scale(bm, vec=Vector(size) / 2, verts=bm.verts)
    obj = U._obj_from_bmesh(name, bm, mat)
    obj.location = loc
    obj.rotation_euler = [math.radians(a) for a in rot]
    if smooth:
        for p in obj.data.polygons:
            p.use_smooth = True
    return obj


# --------------------------------------------------------------------------------------
def crate():
    p = []
    w, d, h = 1.1, 0.8, 0.75
    t = 0.022
    p.append(U.box_span("core", (-w / 2 + t, w / 2 - t), (-d / 2 + t, d / 2 - t), (0.0, h), M["wood"]))
    # planks on the long faces
    n = 5
    for side in (-1, 1):
        for i in range(n):
            z0 = i * h / n + 0.004
            b = U.box_span("plank", (-w / 2 + t, w / 2 - t), (side * (d / 2 - t) - 0.012, side * (d / 2 - t) + 0.012),
                           (z0, z0 + h / n - 0.008), M["wood"])
            U.bevel(b, 0.004, 1)
            p.append(b)
    # frame battens on every edge
    fw = 0.075
    for sx in (-1, 1):
        for sy in (-1, 1):
            b = U.box_span("post", (sx * w / 2 - fw / 2 - sx * fw / 2, sx * w / 2 + fw / 2 - sx * fw / 2),
                           (sy * d / 2 - 0.02, sy * d / 2 + 0.02), (0, h), M["wood"])
            U.bevel(b, 0.005, 1)
            p.append(b)
        for z in (fw / 2, h - fw / 2):
            b = U.box_span("rail", (-w / 2, w / 2), (sx * d / 2 - 0.021, sx * d / 2 + 0.021),
                           (z - fw / 2, z + fw / 2), M["wood"])
            U.bevel(b, 0.005, 1)
            p.append(b)
    # lid battens
    for x in (-0.35, 0.0, 0.35):
        b = U.box_span("lid", (x - 0.04, x + 0.04), (-d / 2, d / 2), (h, h + 0.02), M["wood"])
        U.bevel(b, 0.004, 1)
        p.append(b)
    # rope handles on ends
    for sx in (-1, 1):
        p.append(U.box_span("cleat", (sx * w / 2 - 0.02, sx * w / 2 + 0.02), (-0.15, 0.15), (0.5, 0.56), M["wood"]))
    finish(p, "Crate")


def ammo_box():
    p = []
    b = U.box_span("body", (-0.15, 0.15), (-0.08, 0.08), (0, 0.19), M["olive"])
    U.bevel(b, 0.006, 2)
    p.append(b)
    lid = U.box_span("lid", (-0.155, 0.155), (-0.085, 0.085), (0.19, 0.215), M["olive"])
    U.bevel(lid, 0.005, 2)
    p.append(lid)
    p.append(U.box_span("handle", (-0.06, 0.06), (-0.012, 0.012), (0.215, 0.235), M["dark"]))
    p.append(U.box_span("latch", (0.15, 0.165), (-0.03, 0.03), (0.13, 0.21), M["dark"]))
    finish(p, "AmmoBox")


def barrel():
    p = []
    r, h = 0.29, 0.88
    p.append(U.cylinder("drum", r, 0.012, h - 0.012, M["barrel"], axis="Z", verts=32))
    for z in (0.012, h - 0.012):
        p.append(U.cylinder("chime", r + 0.008, z - 0.012, z + 0.012, M["barrel"], axis="Z", verts=32))
    for z in (h * 0.33, h * 0.66):
        p.append(U.cylinder("hoop", r + 0.012, z - 0.013, z + 0.013, M["barrel"], axis="Z", verts=32))
    p.append(U.cylinder("bung", 0.03, h - 0.012, h + 0.004, M["dark"], x=0.14, axis="Z", verts=12))
    p.append(U.cylinder("bung2", 0.02, h - 0.012, h + 0.004, M["dark"], x=-0.16, y=0.05, axis="Z", verts=12))
    obj = finish(p, "Barrel", uv=False)
    cyl_uv(obj, r)


def cyl_uv(obj, r):
    """Cylindrical UVs (u = arc length, v = height) for barrels, trunks, tanks."""
    me = obj.data
    if not me.uv_layers:
        me.uv_layers.new(name="UVMap")
    uv = me.uv_layers.active.data
    for poly in me.polygons:
        cos = [me.vertices[me.loops[li].vertex_index].co for li in poly.loop_indices]
        angs = [math.atan2(c.y, c.x) for c in cos]
        # keep a polygon from wrapping across the seam
        if max(angs) - min(angs) > math.pi:
            angs = [a + 2 * math.pi if a < 0 else a for a in angs]
        vertical = abs(poly.normal.z) < 0.7
        for li, c, a in zip(poly.loop_indices, cos, angs):
            if vertical:
                uv[li].uv = (a * r, c.z)
            else:
                uv[li].uv = (c.x, c.y)


def sandbags(length=2.4, rows=3):
    p = []
    bag_l, bag_w, bag_h = 0.6, 0.34, 0.16
    for row in range(rows):
        off = (bag_l / 2) * (row % 2)
        n = int(length / bag_l) + (0 if row % 2 == 0 else -1)
        x0 = -length / 2 + bag_l / 2 + off
        for i in range(n):
            x = x0 + i * bag_l + random.uniform(-0.02, 0.02)
            z = bag_h / 2 + row * (bag_h * 0.86)
            b = rounded_block("bag", (bag_l * random.uniform(0.95, 1.02), bag_w, bag_h * random.uniform(0.95, 1.08)),
                              (x, random.uniform(-0.02, 0.02), z), M["sandbag"],
                              rot=(random.uniform(-3, 3), random.uniform(-3, 3), random.uniform(-4, 4)),
                              roundness=0.55)
            p.append(b)
        # second layer behind for thickness
        for i in range(n):
            x = x0 + i * bag_l + random.uniform(-0.02, 0.02)
            z = bag_h / 2 + row * (bag_h * 0.86)
            b = rounded_block("bag", (bag_l, bag_w, bag_h), (x, -bag_w * 0.95, z), M["sandbag"],
                              rot=(0, random.uniform(-3, 3), random.uniform(-4, 4)), roundness=0.55)
            p.append(b)
    obj = finish(p, "Sandbags", uv=False)
    U.box_uv(obj, 1.6)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    obj.data.attributes.remove(obj.data.attributes["sharp_edge"]) if "sharp_edge" in obj.data.attributes else None


def jersey():
    prof = [(-0.305, 0.0), (0.305, 0.0), (0.305, 0.075), (0.13, 0.33), (0.075, 0.81),
            (-0.075, 0.81), (-0.13, 0.33), (-0.305, 0.075)]
    b = U.prism("barrier", prof, 1.5, M["concrete"])
    U.bevel(b, 0.012, 2, angle=20)
    cut = U.box_span("slot", (-0.8, 0.8), (-0.4, 0.4), (-0.1, 0.07), None)
    cut2 = U.box_span("slot", (-0.3, 0.3), (-0.4, 0.4), (-0.1, 0.07), None)
    U.subtract(b, [cut])
    finish([b, cut], "Jersey")
    bpy.data.objects.remove(cut2, do_unlink=True)


def hesco(units=4):
    p = []
    s = 1.06
    h = 1.37
    for i in range(units):
        x = (i - (units - 1) / 2) * s
        blk = rounded_block("cell", (s * 1.02, s * 1.02, h), (x, 0, h / 2), M["hesco"], roundness=0.18, cuts=4,
                            smooth=False)
        p.append(blk)
        # wire frame corner posts
        for sx in (-1, 1):
            for sy in (-1, 1):
                p.append(U.box_span("wire", (x + sx * s / 2 - 0.012, x + sx * s / 2 + 0.012),
                                    (sy * s / 2 - 0.012, sy * s / 2 + 0.012), (0, h + 0.02), M["galv"]))
        # dirt fill visible on top
        p.append(U.box_span("fill", (x - s / 2 + 0.03, x + s / 2 - 0.03), (-s / 2 + 0.03, s / 2 - 0.03),
                            (h - 0.06, h - 0.02), M["sandbag"]))
    finish(p, "Hesco")


def container():
    p = []
    L, W, H = 6.06, 2.44, 2.59
    pitch, depth = 0.278, 0.036
    t = 0.004
    p.append(U.box_span("core", (-L / 2 + 0.1, L / 2 - 0.1), (-W / 2 + 0.06, W / 2 - 0.06), (0.1, H - 0.1),
                        M["container"]))
    # corrugated long walls: trapezoid profile along X, extruded along Z
    for side in (-1, 1):
        bm = bmesh.new()
        pts = []
        x = -L / 2 + 0.12
        while x < L / 2 - 0.12:
            seg = [(0.0, 0.0), (0.07, depth), (0.14, depth), (0.21, 0.0)]
            for dx, dy in seg:
                if x + dx <= L / 2 - 0.12:
                    pts.append((x + dx, dy))
            x += pitch
        y_base = side * (W / 2 - 0.06)
        vb = [bm.verts.new((px, y_base + side * py, 0.12)) for px, py in pts]
        vt = [bm.verts.new((px, y_base + side * py, H - 0.12)) for px, py in pts]
        for i in range(len(pts) - 1):
            f = (vb[i], vb[i + 1], vt[i + 1], vt[i]) if side < 0 else (vb[i], vt[i], vt[i + 1], vb[i + 1])
            bm.faces.new(f)
        p.append(U._obj_from_bmesh("corr", bm, M["container"]))
    # end wall corrugation (rear) as vertical ribs
    for i in range(8):
        y = -W / 2 + 0.25 + i * 0.28
        p.append(U.box_span("rib", (-L / 2 + 0.06, -L / 2 + 0.1), (y, y + 0.12), (0.12, H - 0.12), M["container"]))
    # doors (front) with lock bars
    p.append(U.box_span("doors", (L / 2 - 0.1, L / 2 - 0.06), (-W / 2 + 0.08, W / 2 - 0.08), (0.12, H - 0.12),
                        M["container"]))
    for y in (-0.85, -0.35, 0.35, 0.85):
        p.append(U.cylinder("lockbar", 0.02, 0.15, H - 0.15, M["container"], x=L / 2 - 0.04, y=y, axis="Z",
                            verts=8))
        p.append(U.box_span("handle", (L / 2 - 0.05, L / 2 - 0.0), (y - 0.03, y + 0.03), (1.0, 1.35), M["dark"]))
    # frame rails and corner posts
    for z0, z1 in ((0.0, 0.14), (H - 0.13, H)):
        for side in (-1, 1):
            p.append(U.box_span("rail", (-L / 2, L / 2), (side * W / 2 - 0.08, side * W / 2 + 0.0 if side > 0 else side * W / 2 + 0.08),
                                (z0, z1), M["container"]))
        for sx in (-1, 1):
            p.append(U.box_span("endrail", (sx * L / 2 - 0.1, sx * L / 2 + 0.0 if sx > 0 else sx * L / 2 + 0.1),
                                (-W / 2, W / 2), (z0, z1), M["container"]))
    for sx in (-1, 1):
        for sy in (-1, 1):
            p.append(U.box_span("post", (sx * L / 2 - 0.1 if sx > 0 else sx * L / 2, sx * L / 2 if sx > 0 else sx * L / 2 + 0.1),
                                (sy * W / 2 - 0.1 if sy > 0 else sy * W / 2, sy * W / 2 if sy > 0 else sy * W / 2 + 0.1),
                                (0, H), M["container"]))
            for z in (0.0, H - 0.12):
                p.append(U.box_span("casting", (sx * L / 2 - 0.18 if sx > 0 else sx * L / 2, sx * L / 2 if sx > 0 else sx * L / 2 + 0.18),
                                    (sy * W / 2 - 0.16 if sy > 0 else sy * W / 2, sy * W / 2 if sy > 0 else sy * W / 2 + 0.16),
                                    (z, z + 0.12), M["dark"]))
    finish(p, "Container")


def pallet():
    p = []
    for x in (-0.5, 0.0, 0.5):
        p.append(U.box_span("block", (x - 0.05, x + 0.05), (-0.6, 0.6), (0.0, 0.1), M["wood"]))
    for i in range(7):
        y = -0.6 + 0.06 + i * 0.18
        b = U.box_span("slat", (-0.6, 0.6), (y - 0.05, y + 0.05), (0.1, 0.122), M["wood"])
        U.bevel(b, 0.004, 1)
        p.append(b)
    finish(p, "Pallet")


def tire():
    bpy.ops.mesh.primitive_torus_add(major_radius=0.3, minor_radius=0.11, major_segments=28, minor_segments=10,
                                     location=(0, 0, 0.11))
    t = bpy.context.active_object
    t.name = "tire_t"
    t.scale = (1, 1, 0.9)
    t.data.materials.append(M["rubber"])
    for poly in t.data.polygons:
        poly.use_smooth = True
    finish([t], "Tire")


def burnt_car():
    p = []
    prof = [(-2.25, 0.32), (2.2, 0.32), (2.3, 0.72), (2.22, 0.86), (0.95, 0.96), (0.35, 1.40),
            (-0.95, 1.44), (-1.65, 1.0), (-2.25, 0.96), (-2.32, 0.62)]
    body = U.prism("body", prof, 0.86, M["burnt"])
    U.bevel(body, 0.04, 3, angle=25)
    cuts = []
    for y in (-1.45, 1.35):
        c = U.cylinder("arch", 0.38, -1.0, 1.0, None, y=y, z=0.36, axis="X", verts=24)
        cuts.append(c)
    # window openings (glass gone) - cut through the cabin
    cuts.append(U.prism("winside", [(0.25, 0.98), (-0.85, 0.98), (-0.9, 1.36), (0.2, 1.33)], 1.0, None))
    cuts.append(U.prism("winside2", [(-0.95, 0.98), (-1.55, 1.0), (-1.02, 1.37), (-0.97, 1.37)], 1.0, None))
    cuts.append(U.prism("windshield", [(0.9, 0.98), (0.4, 0.99), (0.33, 1.34), (0.37, 1.34)], 0.72, None))
    U.subtract(body, cuts)
    p.append(body)
    p += cuts
    # hollow cabin interior (dark) so openings don't show a solid block
    p.append(U.box_span("interior", (-0.78, 0.78), (-1.5, 0.85), (0.4, 0.95), M["dark"]))
    p.append(U.box_span("seat", (-0.7, -0.1), (-0.6, -0.2), (0.6, 1.2), M["dark"]))
    p.append(U.box_span("seat", (0.1, 0.7), (-0.6, -0.2), (0.6, 1.2), M["dark"]))
    for y in (-1.45, 1.35):
        for sx in (-1, 1):
            p.append(U.cylinder("rim", 0.24, sx * 0.72, sx * 0.84, M["dark"], y=y, z=0.24, axis="X", verts=16))
    obj = finish(p, "BurntCar")
    return obj


def watchtower():
    p = []
    H = 3.6
    s = 1.2
    for sx in (-1, 1):
        for sy in (-1, 1):
            b = U.box_span("leg", (sx * s - 0.08, sx * s + 0.08), (sy * s - 0.08, sy * s + 0.08), (0, H + 1.1),
                           M["wood"])
            p.append(b)
    # cross braces
    for side in range(4):
        ang = side * math.pi / 2
        for z0 in (0.3, 1.9):
            b = U.box("brace", (2 * s, 0.05, 0.12), (0, 0, 0), M["wood"])
            b.rotation_euler = (math.atan2(1.4, 2 * s) * (1 if side % 2 else -1), 0, 0)
            b.rotation_euler = (0, math.atan2(1.4, 2 * s), 0)
            b.location = (0, s, z0 + 0.7)
            mw = Matrix.Rotation(ang, 4, "Z") @ b.matrix_basis
            b.matrix_basis = mw
            p.append(b)
    p.append(U.box_span("floor", (-s - 0.15, s + 0.15), (-s - 0.15, s + 0.15), (H - 0.1, H), M["wood"]))
    # plywood parapet with a gap at the ladder side
    for side in range(4):
        ang = side * math.pi / 2
        b = U.box_span("wall", (-s - 0.15, s + 0.15), (s + 0.1, s + 0.14), (H, H + 1.05), M["wood"])
        b.matrix_basis = Matrix.Rotation(ang, 4, "Z") @ b.matrix_basis
        p.append(b)
    # roof posts + sloped roof
    for sx in (-1, 1):
        for sy in (-1, 1):
            p.append(U.box_span("rpost", (sx * s - 0.05, sx * s + 0.05), (sy * s - 0.05, sy * s + 0.05),
                                (H + 1.05, H + 2.1 + 0.15 * sy), M["wood"]))
    roof = U.box("roof", (2 * s + 0.6, 2 * s + 0.6, 0.04), (0, 0, H + 2.2), M["galv"])
    roof.rotation_euler = (math.radians(7), 0, 0)
    p.append(roof)
    # sandbags ring on the platform floor for cover
    for i in range(6):
        p.append(rounded_block("bag", (0.55, 0.3, 0.15), (-0.9 + i * 0.36, s - 0.05, H + 0.08), M["sandbag"],
                               roundness=0.5))
    # ladder
    for sx in (-1, 1):
        p.append(U.box_span("rail", (sx * 0.25 - 0.03, sx * 0.25 + 0.03), (-s - 0.45, -s - 0.4), (0, H + 1.0),
                            M["wood"]))
    for i in range(12):
        z = 0.3 + i * 0.3
        p.append(U.box_span("rung", (-0.25, 0.25), (-s - 0.45, -s - 0.4), (z, z + 0.04), M["wood"]))
    finish(p, "Watchtower")


def palm():
    """Date palm: bent, ringed trunk + drooping fronds (alpha-textured strips)."""
    trunk_h = 7.0
    segs = 20
    bm = bmesh.new()
    rings = []
    ring_n = 12
    for i in range(segs + 1):
        t = i / segs
        z = t * trunk_h
        off = Vector((0.6 * t * t, 0.2 * t * t, 0))
        r = 0.24 - 0.08 * t + 0.03 * math.sin(i * 1.7) * (i % 2)
        ring = []
        for j in range(ring_n):
            a = j / ring_n * 2 * math.pi
            ring.append(bm.verts.new((off.x + math.cos(a) * r, off.y + math.sin(a) * r, z)))
        rings.append(ring)
    for i in range(segs):
        for j in range(ring_n):
            k = (j + 1) % ring_n
            bm.faces.new((rings[i][j], rings[i][k], rings[i + 1][k], rings[i + 1][j]))
    trunk = U._obj_from_bmesh("trunk", bm, M["bark"])
    top = Vector((0.6, 0.2, trunk_h))
    # UVs for the trunk (u around, v up)
    me = trunk.data
    me.uv_layers.new(name="UVMap")
    uvl = me.uv_layers.active.data
    for poly in me.polygons:
        for li in poly.loop_indices:
            vi = me.loops[li].vertex_index
            ring_i, j = divmod(vi, ring_n)
            # close the seam on the last column
            u = j / ring_n
            if j == 0 and any(me.vertices[me.loops[l2].vertex_index].index % ring_n == ring_n - 1
                              for l2 in poly.loop_indices):
                u = 1.0
            uvl[li].uv = (u, ring_i / segs * 6)
    for p_ in me.polygons:
        p_.use_smooth = True
    # fronds
    fr_bm = bmesh.new()
    uv_list = []
    n_fronds = 16
    for f in range(n_fronds):
        yaw = f / n_fronds * 2 * math.pi + random.uniform(-0.15, 0.15)
        tier = f % 2
        droop = random.uniform(0.3, 0.6) + tier * 0.35
        length = random.uniform(2.6, 3.3)
        width = 0.55
        segs_f = 8
        left = []
        right = []
        for i in range(segs_f + 1):
            t = i / segs_f
            # arc: rise then droop
            pitch = 0.9 - (droop + 0.6) * t * 1.6
            dist = t * length
            hx = math.cos(pitch) * dist
            hz = math.sin(0.9) * dist * 0.6 - (droop * 1.8) * t * t * length * 0.5
            center = Vector((math.cos(yaw) * hx, math.sin(yaw) * hx, hz)) + top
            side = Vector((-math.sin(yaw), math.cos(yaw), 0)) * (width * (0.25 + 0.75 * math.sin(math.pi * min(1, t * 1.1 + 0.05))) / 2)
            fold = Vector((0, 0, 0.12 * (1 - t)))
            left.append(fr_bm.verts.new(center - side + fold))
            right.append(fr_bm.verts.new(center + side + fold))
        mid = []
        for i in range(segs_f + 1):
            mid.append(fr_bm.verts.new((left[i].co + right[i].co) / 2 - Vector((0, 0, 0.05))))
        for i in range(segs_f):
            fa = fr_bm.faces.new((left[i], mid[i], mid[i + 1], left[i + 1]))
            fb = fr_bm.faces.new((mid[i], right[i], right[i + 1], mid[i + 1]))
            uv_list.append((fa, [(0, i / segs_f), (0.5, i / segs_f), (0.5, (i + 1) / segs_f), (0, (i + 1) / segs_f)]))
            uv_list.append((fb, [(0.5, i / segs_f), (1, i / segs_f), (1, (i + 1) / segs_f), (0.5, (i + 1) / segs_f)]))
    uv_layer = fr_bm.loops.layers.uv.new("UVMap")
    for face, uvs in uv_list:
        for loop, uvc in zip(face.loops, uvs):
            loop[uv_layer].uv = uvc
    fronds = U._obj_from_bmesh("fronds", fr_bm, M["leaf"])
    for p_ in fronds.data.polygons:
        p_.use_smooth = True
    # trunk and fronds kept as separate child meshes (fronds are double-sided alpha)
    root = U.empty("Palm", (0, 0, 0))
    trunk.name = "Palm_Trunk"
    fronds.name = "Palm_Fronds"
    trunk.parent = root
    fronds.parent = root
    PROPS.append(root)


def power_pole():
    p = []
    p.append(U.cylinder("pole", 0.13, 0, 9.0, M["wood"], axis="Z", verts=10, radius2=0.1))
    p.append(U.box_span("arm", (-1.1, 1.1), (-0.06, 0.06), (8.3, 8.42), M["wood"]))
    for x in (-0.95, 0.0, 0.95):
        z0 = 8.42 if x else 9.0
        p.append(U.cylinder("insul", 0.035, z0, z0 + 0.16, M["white"], x=x, axis="Z", verts=8))
    obj = finish(p, "PowerPole", uv=False)
    cyl_uv(obj, 0.13)


def water_tank():
    p = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            p.append(U.box_span("leg", (sx * 0.55 - 0.03, sx * 0.55 + 0.03), (sy * 0.55 - 0.03, sy * 0.55 + 0.03),
                                (0, 1.0), M["dark"]))
    p.append(U.box_span("deck", (-0.65, 0.65), (-0.65, 0.65), (1.0, 1.06), M["dark"]))
    p.append(U.cylinder("tank", 0.62, 1.06, 2.3, M["plastic"], axis="Z", verts=28))
    p.append(U.cylinder("lid", 0.25, 2.3, 2.38, M["plastic"], axis="Z", verts=20))
    for z in (1.4, 1.8):
        p.append(U.cylinder("rib", 0.63, z, z + 0.04, M["plastic"], axis="Z", verts=28))
    finish(p, "WaterTank")


def ac_unit():
    p = []
    b = U.box_span("case", (-0.35, 0.35), (-0.3, 0.3), (0, 0.45), M["white"])
    U.bevel(b, 0.01, 1)
    p.append(b)
    for i in range(10):
        z = 0.05 + i * 0.037
        p.append(U.box_span("grille", (-0.3, 0.3), (0.3, 0.315), (z, z + 0.015), M["dark"]))
    finish(p, "ACUnit")


def gas_cans():
    p = []
    for i, (x, y, r) in enumerate(((0, 0, 0), (0.24, 0.02, 8), (0.1, 0.22, 90))):
        b = U.box("can", (0.17, 0.33, 0.47), (x, y, 0.235), M["olive"], rot=(0, 0, r))
        U.bevel(b, 0.02, 2)
        p.append(b)
    finish(p, "JerryCans")


crate()
ammo_box()
barrel()
sandbags()
jersey()
hesco()
container()
pallet()
tire()
burnt_car()
watchtower()
palm()
power_pole()
water_tank()
ac_unit()
gas_cans()

if PREVIEW:
    x = 0
    for o in PROPS:
        o.location.x = x
        dims = max(o.dimensions.x, 1.2) if o.type == "MESH" else 4
        x += dims + 1.2
    U.preview(PREVIEW, target=(x / 2, 0, 1.2), cam_loc=(x / 2, -x * 0.75, x * 0.3), lens=40,
              res=(1800, 700), samples=12)
    for o in PROPS:
        o.location.x = 0

U.export_glb(OUT, objects=PROPS)
print("EXPORTED", OUT, [o.name for o in PROPS])
