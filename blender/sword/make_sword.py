"""
Photorealistic procedural sword for Blender (Cycles).

Builds a European arming sword entirely from code: a lofted blade with
fuller and convex edge bevels, a curved crossguard with knobbed quillons,
a spiral-wrapped leather grip with brass ferrules and a wheel pommel.
Every surface uses procedural PBR shading (brushed anisotropic steel,
aged brass with cavity patina, grained leather, varnished walnut planks)
and is lit like a product photo: a gradient softbox placed exactly in the
blade's mirror direction, a warm key, a cool rim and fill cards.

Run it either with Blender:
    blender -b -P make_sword.py -- --render
or with the `bpy` pip module:
    python make_sword.py --render

Options (after `--` when using the blender binary):
    --render             render the stills (otherwise only the .blend is saved)
    --samples N          Cycles samples per pixel (default 256)
    --res W H            output resolution (default 1920 1080)
    --out DIR            output directory (default: ./renders next to this file)
    --shots a,b          which cameras to render: hero, closeup (default both)
    --hdri PATH          optional .hdr/.exr to use as the environment instead
                         of the built-in studio world
    --gpu                try to render on the GPU (CUDA/OptiX/HIP/Metal)
"""

import argparse
import math
import os
import sys

import bpy  # must come first when running via the bpy pip module
import bmesh
from mathutils import Matrix, Vector


# ---------------------------------------------------------------------------
# Dimensions (metres). Real-world scale keeps depth of field physical.
# ---------------------------------------------------------------------------
BLADE_START = -0.004      # blade root sits inside the guard
BLADE_LEN = 0.84
BLADE_W0 = 0.052          # width at the guard
BLADE_W1 = 0.037          # width where the point begins
POINT_LEN = 0.19
BLADE_T0 = 0.0068         # thickness at the guard
BLADE_T1 = 0.0026         # thickness near the point
EDGE_HALF = 0.00022       # the edge is not a zero-width razor
FULLER_START, FULLER_END = 0.03, 0.56
FULLER_DEPTH = 0.0011

GUARD_HALF_SPAN = 0.104
GRIP_TOP, GRIP_BOTTOM = -0.010, -0.198
POMMEL_Z = -0.227
POMMEL_R = 0.032


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def smoothstep(e0, e1, x):
    t = min(max((x - e0) / (e1 - e0), 0.0), 1.0)
    return t * t * (3 - 2 * t)


def superellipse(n, a, b, p=2.0):
    """Points of a superellipse |x/a|^p + |y/b|^p = 1 (p=2 is an ellipse)."""
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        c, s = math.cos(t), math.sin(t)
        x = a * math.copysign(abs(c) ** (2 / p), c)
        y = b * math.copysign(abs(s) ** (2 / p), s)
        pts.append((x, y))
    return pts


def frame_from_axis(axis):
    """Two unit vectors perpendicular to `axis` (and to each other)."""
    axis = Vector(axis).normalized()
    ref = Vector((0, 0, 1)) if abs(axis.z) < 0.9 else Vector((1, 0, 0))
    u = axis.cross(ref).normalized()
    v = axis.cross(u).normalized()
    return u, v


def mesh_object(name, bm, collection, smooth_angle=30.0):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.shade_smooth()
    me.set_sharp_from_angle(angle=math.radians(smooth_angle))
    ob = bpy.data.objects.new(name, me)
    collection.objects.link(ob)
    return ob


def bridge_rings(bm, rings, cap_start=True, cap_end=True):
    """Connect equal-length closed vertex rings with quads."""
    faces = []
    for r0, r1 in zip(rings, rings[1:]):
        n = len(r0)
        for i in range(n):
            j = (i + 1) % n
            faces.append(bm.faces.new((r0[i], r0[j], r1[j], r1[i])))
    if cap_start:
        bm.faces.new(list(reversed(rings[0])))
    if cap_end:
        bm.faces.new(rings[-1])
    return faces


def lathe(bm, profile, center, axis, segments=96):
    """Revolve a (radius, height) profile around `axis` through `center`.
    Profile points with radius 0 become single pole vertices."""
    center = Vector(center)
    axis = Vector(axis).normalized()
    u, v = frame_from_axis(axis)
    rings = []
    for r, h in profile:
        c = center + axis * h
        if r < 1e-7:
            rings.append([bm.verts.new(c)])
            continue
        ring = []
        for i in range(segments):
            t = 2 * math.pi * i / segments
            ring.append(bm.verts.new(c + (u * math.cos(t) + v * math.sin(t)) * r))
        rings.append(ring)
    for r0, r1 in zip(rings, rings[1:]):
        if len(r0) == 1 and len(r1) == 1:
            continue
        if len(r0) == 1:
            for i in range(segments):
                bm.faces.new((r0[0], r1[(i + 1) % segments], r1[i]))
        elif len(r1) == 1:
            for i in range(segments):
                bm.faces.new((r0[i], r0[(i + 1) % segments], r1[0]))
        else:
            for i in range(segments):
                j = (i + 1) % segments
                bm.faces.new((r0[i], r0[j], r1[j], r1[i]))
    bm.normal_update()
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------
def blade_width(z):
    """Profile of the blade seen flat: gentle distal taper, then an ogive point."""
    s = (z - BLADE_START) / BLADE_LEN
    body_end = 1.0 - POINT_LEN / BLADE_LEN
    if s <= body_end:
        k = s / body_end
        return BLADE_W0 + (BLADE_W1 - BLADE_W0) * (k ** 1.15)
    k = (s - body_end) / (1.0 - body_end)
    return BLADE_W1 * (1.0 - k * k)


def blade_thickness(z):
    s = (z - BLADE_START) / BLADE_LEN
    t = BLADE_T0 + (BLADE_T1 - BLADE_T0) * (s ** 1.1)
    w = blade_width(z)
    return t * (min(w / BLADE_W1, 1.0) ** 0.35) + 2 * EDGE_HALF * 0.5


def build_blade(col):
    bm = bmesh.new()
    uv_layer = bm.loops.layers.uv.new("UVMap")
    grind_layer = bm.faces.layers.float.new("grind")
    fuller_layer = bm.faces.layers.float.new("fuller")

    n_st = 220
    n_flat, n_bevel = 26, 8
    rings, ring_meta = [], []
    for i in range(n_st):
        k = i / (n_st - 1)
        # denser stations toward the point where the outline curves
        k = 1 - (1 - k) ** 1.35
        z = BLADE_START + BLADE_LEN * k
        if i == n_st - 1:
            rings.append([bm.verts.new((0, 0, BLADE_START + BLADE_LEN))])
            ring_meta.append(None)
            break
        w = blade_width(z)
        half_w = w / 2
        half_t = blade_thickness(z) / 2
        bev = min(0.0105 * (w / BLADE_W0) ** 0.6 + 0.0015, half_w * 0.96)
        flat_w = half_w - bev

        # fuller: a rounded groove down the centre that fades in and out
        fade = smoothstep(FULLER_START, FULLER_START + 0.035, z) * (
            1 - smoothstep(FULLER_END - 0.09, FULLER_END, z))
        fr = min(0.0072 * (w / BLADE_W0) + 0.0008, flat_w * 0.85)
        depth = FULLER_DEPTH * fade

        # half profile from centre to edge: (x, half-thickness, zone)
        half = []
        for j in range(n_flat):
            x = flat_w * j / (n_flat - 1)
            g = 0.0
            if fr > 1e-5 and x < fr:
                g = depth * (1 - (x / fr) ** 2) ** 0.6
            zone = 2 if (x < fr and depth > 1e-5) else 0
            half.append((x, half_t - g, zone))
        for j in range(1, n_bevel + 1):
            sb = j / n_bevel
            x = flat_w + bev * sb
            # slightly convex ("appleseed") edge bevel
            h = EDGE_HALF + (half_t - EDGE_HALF) * (1 - sb) ** 0.85
            half.append((x, h, 1))

        # full ring: top surface right->left, bottom surface left->right
        top = [(-x, h, zn) for x, h, zn in reversed(half[1:])] + half
        bot = [(x, -h, zn) for x, h, zn in reversed(top)]
        prof = top + bot
        ring = [bm.verts.new((x, y, z)) for x, y, _ in prof]
        rings.append(ring)
        ring_meta.append([(x, y, zn) for x, y, zn in prof])

    # side faces between stations
    for i in range(len(rings) - 1):
        r0, r1 = rings[i], rings[i + 1]
        meta = ring_meta[i]
        n = len(r0)
        for a in range(n):
            b = (a + 1) % n
            if len(r1) == 1:
                f = bm.faces.new((r0[a], r0[b], r1[0]))
            else:
                f = bm.faces.new((r0[a], r0[b], r1[b], r1[a]))
            za, zb = meta[a][2], meta[b][2]
            f[grind_layer] = 1.0 if (za == 1 or zb == 1) and not (za == 0 or zb == 0 or za == 2 or zb == 2) else 0.0
            f[fuller_layer] = 1.0 if (za == 2 and zb == 2) else 0.0
            for loop in f.loops:
                co = loop.vert.co
                # U runs along the blade so the UV tangent follows the brushing
                off = 0.0 if co.y >= 0 else 0.2
                loop[uv_layer].uv = (co.z, co.x + off)
    bm.faces.new(list(reversed(rings[0])))
    bm.normal_update()
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return mesh_object("Blade", bm, col, smooth_angle=11.0)


def guard_center_z(x):
    return 0.0 + 1.05 * x * x


def build_guard(col):
    bm = bmesh.new()
    rings = []
    n = 120
    for i in range(n):
        x = -GUARD_HALF_SPAN + 2 * GUARD_HALF_SPAN * i / (n - 1)
        bump = math.exp(-((x / 0.03) ** 4))
        taper = 1 - 0.22 * (abs(x) / GUARD_HALF_SPAN) ** 1.5
        a = 0.0086 * taper + 0.0040 * bump      # half thickness (Y)
        b = 0.0072 * taper + 0.0040 * bump      # half height (Z)
        zc = guard_center_z(x)
        ring = [bm.verts.new((x, py, zc + pz))
                for py, pz in superellipse(56, a, b, p=2.6)]
        rings.append(ring)
    bridge_rings(bm, rings)
    # knobbed quillon terminals, aligned with the curved bar's tangent
    for sgn in (-1, 1):
        x = sgn * (GUARD_HALF_SPAN - 0.004)
        axis = Vector((sgn, 2 * 1.05 * x * sgn, 0)).normalized()
        axis = Vector((axis.x, 0, axis.y))
        knob = [(0.0060, -0.004), (0.0068, -0.0015), (0.0080, 0.0012),
                (0.0098, 0.0045), (0.0107, 0.0078), (0.0104, 0.0105),
                (0.0092, 0.0135), (0.0070, 0.0160), (0.0040, 0.0176),
                (0.0015, 0.0182), (0.0, 0.0183)]
        lathe(bm, knob, (x, 0, guard_center_z(x)), axis, segments=64)
    bm.normal_update()
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return mesh_object("Guard", bm, col, smooth_angle=40.0)


def grip_axes(t):
    barrel = 1 - 0.13 * (2 * t - 1) ** 2
    return 0.0148 * barrel, 0.0121 * barrel


def build_grip(col):
    bm = bmesh.new()
    rings = []
    n = 90
    for i in range(n):
        t = i / (n - 1)
        z = GRIP_TOP + (GRIP_BOTTOM - GRIP_TOP) * t
        ax, ay = grip_axes(t)
        rings.append([bm.verts.new((px, py, z)) for px, py in superellipse(96, ax, ay)])
    bridge_rings(bm, rings)
    bm.normal_update()
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return mesh_object("Grip", bm, col, smooth_angle=60.0)


def build_fittings(col):
    """Brass ferrules capping the leather, the wheel pommel and the peen block."""
    bm = bmesh.new()
    for z0, z1, t_ref in ((GRIP_TOP + 0.001, GRIP_TOP - 0.009, 0.0),
                          (GRIP_BOTTOM + 0.011, GRIP_BOTTOM - 0.002, 1.0)):
        rings = []
        n = 24
        for i in range(n):
            k = i / (n - 1)
            z = z0 + (z1 - z0) * k
            ax, ay = grip_axes(t_ref)
            lip = math.sqrt(max(0.0, 1 - (2 * k - 1) ** 2)) ** 0.5
            grow = 0.0006 + 0.0012 * lip
            rings.append([bm.verts.new((px, py, z))
                          for px, py in superellipse(96, ax + grow, ay + grow)])
        bridge_rings(bm, rings)

    # wheel pommel, revolved around the Y axis (disc faces sideways)
    half = [(0.0, 0.0128), (0.0060, 0.0128), (0.0086, 0.0122), (0.0098, 0.0108),
            (0.0106, 0.0090), (0.0118, 0.0082), (0.0170, 0.0082), (0.0196, 0.0092),
            (0.0214, 0.0112), (0.0240, 0.0116), (0.0270, 0.0110), (0.0294, 0.0094),
            (0.0310, 0.0070), (0.0318, 0.0040), (POMMEL_R, 0.0)]
    prof = half + [(r, -h) for r, h in reversed(half[:-1])]
    lathe(bm, prof, (0, 0, POMMEL_Z), (0, 1, 0), segments=128)

    # peened tang end below the pommel
    peen_z = POMMEL_Z - POMMEL_R + 0.0012
    peen = [(0.0052, 0.0), (0.0055, -0.0012), (0.0050, -0.0026),
            (0.0036, -0.0036), (0.0018, -0.0042), (0.0, -0.0044)]
    lathe(bm, peen, (0, 0, peen_z), (0, 0, 1), segments=48)
    bm.normal_update()
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return mesh_object("Fittings", bm, col, smooth_angle=34.0)


# ---------------------------------------------------------------------------
# Shader-graph helpers
# ---------------------------------------------------------------------------
class Graph:
    def __init__(self, mat):
        mat.use_nodes = True
        self.nt = mat.node_tree
        self.nt.nodes.clear()
        self.x = 0

    def node(self, kind, inputs=None, **props):
        n = self.nt.nodes.new(kind)
        n.location = (self.x, 0)
        self.x += 40
        for k, v in props.items():
            setattr(n, k, v)
        for k, v in (inputs or {}).items():
            self.set(n.inputs[k], v)
        return n

    def set(self, sock, v):
        if isinstance(v, bpy.types.NodeSocket):
            self.nt.links.new(v, sock)
        elif isinstance(v, bpy.types.Node):
            self.nt.links.new(v.outputs[0], sock)
        else:
            sock.default_value = v

    def math(self, op, a, b=0.0, clamp=False):
        n = self.node("ShaderNodeMath", operation=op, use_clamp=clamp)
        self.set(n.inputs[0], a)
        self.set(n.inputs[1], b)
        return n.outputs[0]

    def vmath(self, op, a, b=(0, 0, 0)):
        n = self.node("ShaderNodeVectorMath", operation=op)
        self.set(n.inputs[0], a)
        self.set(n.inputs[1], b)
        return n.outputs["Value" if op in ("DOT_PRODUCT", "LENGTH") else "Vector"]

    def maprange(self, v, fmin, fmax, tmin, tmax, clamp=True):
        n = self.node("ShaderNodeMapRange", clamp=clamp)
        self.set(n.inputs["Value"], v)
        n.inputs["From Min"].default_value = fmin
        n.inputs["From Max"].default_value = fmax
        n.inputs["To Min"].default_value = tmin
        n.inputs["To Max"].default_value = tmax
        return n.outputs["Result"]

    def mix_color(self, fac, a, b, blend="MIX"):
        n = self.node("ShaderNodeMix", data_type="RGBA", blend_type=blend)
        ins = {s.identifier: s for s in n.inputs}
        self.set(ins["Factor_Float"], fac)
        self.set(ins["A_Color"], a)
        self.set(ins["B_Color"], b)
        return [s for s in n.outputs if s.identifier == "Result_Color"][0]

    def mix_float(self, fac, a, b):
        n = self.node("ShaderNodeMix", data_type="FLOAT")
        ins = {s.identifier: s for s in n.inputs}
        self.set(ins["Factor_Float"], fac)
        self.set(ins["A_Float"], a)
        self.set(ins["B_Float"], b)
        return [s for s in n.outputs if s.identifier == "Result_Float"][0]

    def noise(self, vec, scale, detail=2.0, rough=0.5, distortion=0.0, out="Fac"):
        n = self.node("ShaderNodeTexNoise", inputs={
            "Scale": scale, "Detail": detail, "Roughness": rough,
            "Distortion": distortion})
        if vec is not None:
            self.set(n.inputs["Vector"], vec)
        return n.outputs[out]

    def combine(self, x, y, z):
        n = self.node("ShaderNodeCombineXYZ")
        self.set(n.inputs[0], x)
        self.set(n.inputs[1], y)
        self.set(n.inputs[2], z)
        return n.outputs[0]

    def separate(self, v):
        n = self.node("ShaderNodeSeparateXYZ")
        self.set(n.inputs[0], v)
        return n.outputs

    def texcoord(self, which):
        return self.node("ShaderNodeTexCoord").outputs[which]

    def bump(self, height, strength, distance, normal=None):
        n = self.node("ShaderNodeBump", inputs={"Strength": strength, "Distance": distance})
        self.set(n.inputs["Height"], height)
        if normal is not None:
            self.set(n.inputs["Normal"], normal)
        return n.outputs["Normal"]

    def output(self, shader):
        out = self.node("ShaderNodeOutputMaterial")
        self.set(out.inputs["Surface"], shader)
        return out


def principled(g, **inputs):
    return g.node("ShaderNodeBsdfPrincipled", inputs=inputs)


# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------
def mat_blade_steel():
    mat = bpy.data.materials.new("Blade Steel")
    g = Graph(mat)
    uv = g.node("ShaderNodeUVMap", uv_map="UVMap").outputs["UV"]
    obj = g.texcoord("Object")
    grind = g.node("ShaderNodeAttribute", attribute_name="grind").outputs["Fac"]
    fuller = g.node("ShaderNodeAttribute", attribute_name="fuller").outputs["Fac"]

    # long, fine brushing lines that run with the blade (U is along the length)
    brush_vec = g.vmath("MULTIPLY", uv, (3.0, 2600.0, 1.0))
    brush = g.noise(brush_vec, 1.0, detail=4.0, rough=0.6)
    brush_fine_vec = g.vmath("MULTIPLY", uv, (9.0, 9000.0, 1.0))
    brush_fine = g.noise(brush_fine_vec, 1.0, detail=2.0)
    # grinding lines on the edge bevel run at an angle to the edge
    rot = g.node("ShaderNodeVectorRotate", rotation_type="Z_AXIS", inputs={"Angle": math.radians(62)})
    g.set(rot.inputs["Vector"], uv)
    bevel_vec = g.vmath("MULTIPLY", rot.outputs[0], (6.0, 3800.0, 1.0))
    bevel_lines = g.noise(bevel_vec, 1.0, detail=3.0)

    # sparse random scratches: thresholded stretched noise in several directions
    scratch_total = None
    for ang, sx, sy, thr in ((8, 40, 1400, 0.70), (-23, 30, 1100, 0.72), (71, 25, 900, 0.735)):
        r = g.node("ShaderNodeVectorRotate", rotation_type="Z_AXIS", inputs={"Angle": math.radians(ang)})
        g.set(r.inputs["Vector"], uv)
        n = g.noise(g.vmath("MULTIPLY", r.outputs[0], (sx, sy, 1.0)), 1.0, detail=1.0)
        s = g.maprange(n, thr, thr + 0.03, 0.0, 1.0)
        scratch_total = s if scratch_total is None else g.math("MAXIMUM", scratch_total, s)
    # scratches only appear in patches
    patch = g.maprange(g.noise(obj, 9.0, detail=2.0), 0.45, 0.62, 0.0, 1.0)
    scratches = g.math("MULTIPLY", scratch_total, patch)

    # smudges / handling marks and slightly uneven polish
    smudge = g.maprange(g.noise(obj, 16.0, detail=6.0, rough=0.62, distortion=0.4), 0.42, 0.72, 0.0, 1.0)
    polish = g.noise(obj, 2.5, detail=3.0)

    rough_flat = g.math("ADD", 0.17, g.math("MULTIPLY", g.math("SUBTRACT", brush, 0.5), 0.10))
    rough_grind = g.math("ADD", 0.075, g.math("MULTIPLY", g.math("SUBTRACT", bevel_lines, 0.5), 0.05))
    rough = g.mix_float(grind, rough_flat, rough_grind)
    rough = g.mix_float(fuller, rough, g.math("ADD", rough, 0.06))
    rough = g.math("ADD", rough, g.math("MULTIPLY", smudge, 0.09))
    rough = g.math("ADD", rough, g.math("MULTIPLY", g.math("SUBTRACT", polish, 0.5), 0.05))
    rough = g.math("ADD", rough, g.math("MULTIPLY", scratches, 0.18), clamp=True)

    base = g.mix_color(g.math("MULTIPLY", g.math("SUBTRACT", polish, 0.3), 0.8),
                       (0.555, 0.560, 0.568, 1), (0.600, 0.598, 0.590, 1))
    base = g.mix_color(g.math("MULTIPLY", fuller, 0.35), base, (0.44, 0.445, 0.45, 1))
    base = g.mix_color(g.math("MULTIPLY", smudge, 0.12), base, (0.42, 0.41, 0.40, 1))

    aniso = g.mix_float(grind, 0.62, 0.35)
    aniso = g.math("MULTIPLY", aniso, g.math("SUBTRACT", 1.0, g.math("MULTIPLY", scratches, 0.8)))
    tangent = g.node("ShaderNodeTangent", direction_type="UV_MAP", uv_map="UVMap").outputs[0]

    height = g.math("ADD", g.math("MULTIPLY", brush, 0.6), g.math("MULTIPLY", brush_fine, 0.4))
    height = g.mix_float(grind, height, bevel_lines)
    height = g.math("SUBTRACT", height, g.math("MULTIPLY", scratches, 0.8))
    normal = g.bump(height, 0.035, 0.0005)

    bsdf = principled(g, **{"Metallic": 1.0, "Specular IOR Level": 0.5})
    for name, v in (("Base Color", base), ("Roughness", rough), ("Anisotropic", aniso),
                    ("Tangent", tangent), ("Normal", normal)):
        g.set(bsdf.inputs[name], v)
    g.output(bsdf)
    return mat


def mat_brass():
    mat = bpy.data.materials.new("Aged Brass")
    g = Graph(mat)
    obj = g.texcoord("Object")
    ao = g.node("ShaderNodeAmbientOcclusion", inputs={"Distance": 0.004}, samples=16)
    ao_f = g.maprange(ao.outputs["AO"], 0.55, 1.0, 1.0, 0.0)
    grime = g.maprange(g.noise(obj, 180.0, detail=5.0, rough=0.7), 0.35, 0.75, 0.0, 1.0)
    patina = g.math("MULTIPLY", ao_f, g.math("ADD", 0.55, g.math("MULTIPLY", grime, 0.6)), clamp=True)
    tarnish = g.maprange(g.noise(obj, 45.0, detail=4.0), 0.4, 0.7, 0.0, 1.0)
    scratches = g.maprange(g.noise(g.vmath("MULTIPLY", obj, (1800.0, 60.0, 1800.0)), 1.0, detail=1.0), 0.70, 0.73, 0.0, 1.0)

    base = g.mix_color(g.math("MULTIPLY", tarnish, 0.45), (0.86, 0.64, 0.34, 1), (0.66, 0.46, 0.24, 1))
    base = g.mix_color(patina, base, (0.10, 0.075, 0.045, 1))
    rough = g.math("ADD", 0.20, g.math("MULTIPLY", tarnish, 0.14))
    rough = g.mix_float(patina, rough, 0.62)
    rough = g.math("ADD", rough, g.math("MULTIPLY", scratches, 0.12))
    metallic = g.mix_float(patina, 1.0, 0.35)
    height = g.math("ADD", g.math("MULTIPLY", grime, 0.3), g.math("MULTIPLY", scratches, -0.6))
    normal = g.bump(height, 0.12, 0.0003)

    bsdf = principled(g)
    for name, v in (("Base Color", base), ("Roughness", rough), ("Metallic", metallic), ("Normal", normal)):
        g.set(bsdf.inputs[name], v)
    g.output(bsdf)
    return mat


def mat_leather():
    mat = bpy.data.materials.new("Wrapped Leather")
    g = Graph(mat)
    obj = g.texcoord("Object")
    x, y, z = g.separate(obj)
    # spiral wrap: phase = z / pitch + angle / 2pi
    ang = g.math("DIVIDE", g.math("ARCTAN2", y, x), 2 * math.pi)
    phase = g.math("ADD", g.math("DIVIDE", z, 0.0165), ang)
    f = g.math("FRACT", phase)
    strip = g.math("POWER", g.math("SINE", g.math("MULTIPLY", f, math.pi)), 0.28)
    groove = g.math("SUBTRACT", 1.0, strip)
    strip_id = g.math("FLOOR", phase)
    strip_rand = g.node("ShaderNodeTexWhiteNoise", noise_dimensions="1D")
    g.set(strip_rand.inputs["W"], strip_id)

    grain = g.node("ShaderNodeTexVoronoi", feature="DISTANCE_TO_EDGE",
                   inputs={"Scale": 900.0, "Randomness": 1.0})
    g.set(grain.inputs["Vector"], obj)
    cracks = g.maprange(grain.outputs["Distance"], 0.0, 0.08, 0.0, 1.0)
    pores = g.noise(obj, 1600.0, detail=2.0)
    wear = g.maprange(g.noise(obj, 60.0, detail=4.0), 0.5, 0.7, 0.0, 1.0)
    # rubbed high points of each strip are lighter and shinier
    high = g.math("MULTIPLY", g.maprange(strip, 0.75, 1.0, 0.0, 1.0), wear)

    base = g.mix_color(strip_rand.outputs["Value"], (0.042, 0.018, 0.008, 1), (0.066, 0.030, 0.013, 1))
    base = g.mix_color(g.math("MULTIPLY", high, 0.7), base, (0.13, 0.068, 0.032, 1))
    base = g.mix_color(g.math("MULTIPLY", groove, 0.8), base, (0.015, 0.008, 0.005, 1))
    base = g.mix_color(g.math("MULTIPLY", g.math("SUBTRACT", 1.0, cracks), 0.5), base, (0.02, 0.011, 0.007, 1))

    rough = g.math("SUBTRACT", 0.62, g.math("MULTIPLY", high, 0.25))
    rough = g.math("ADD", rough, g.math("MULTIPLY", g.math("SUBTRACT", pores, 0.5), 0.12))
    height = g.math("ADD", g.math("MULTIPLY", strip, 1.0), g.math("MULTIPLY", cracks, 0.10))
    height = g.math("ADD", height, g.math("MULTIPLY", pores, 0.04))
    normal = g.bump(height, 0.6, 0.0012)

    bsdf = principled(g, **{"Sheen Weight": 0.15, "Sheen Roughness": 0.4,
                            "Coat Weight": 0.08, "Coat Roughness": 0.35})
    for name, v in (("Base Color", base), ("Roughness", rough), ("Normal", normal)):
        g.set(bsdf.inputs[name], v)
    g.output(bsdf)
    return mat


def mat_walnut(plank_w=0.19):
    mat = bpy.data.materials.new("Walnut Planks")
    g = Graph(mat)
    obj = g.texcoord("Object")
    x, y, z = g.separate(obj)

    pid = g.math("FLOOR", g.math("DIVIDE", y, plank_w))
    rnd = g.node("ShaderNodeTexWhiteNoise", noise_dimensions="1D")
    g.set(rnd.inputs["W"], pid)
    rnd_v = rnd.outputs["Value"]
    rnd_c = rnd.outputs["Color"]
    # each plank samples a different part of a virtual log
    offset = g.vmath("MULTIPLY", rnd_c, (7.0, 0.0, 0.30))
    local_y = g.math("MULTIPLY", g.math("SUBTRACT", g.math("FRACT", g.math("DIVIDE", y, plank_w)), 0.5), plank_w)
    log_vec = g.combine(g.math("ADD", x, g.math("MULTIPLY", rnd_v, 11.0)),
                        g.math("ADD", local_y, g.math("MULTIPLY", g.math("SUBTRACT", rnd_v, 0.5), 0.06)),
                        g.math("ADD", g.math("ADD", z, 0.22), g.math("MULTIPLY", x, 0.012)))
    log_vec = g.vmath("ADD", log_vec, offset)

    rings = g.node("ShaderNodeTexWave", wave_type="RINGS", rings_direction="X", wave_profile="SAW",
                   inputs={"Scale": 55.0, "Distortion": 1.6, "Detail": 3.0, "Detail Scale": 1.4,
                           "Detail Roughness": 0.55})
    g.set(rings.inputs["Vector"], g.vmath("MULTIPLY", log_vec, (0.12, 1.0, 1.0)))
    ring = g.maprange(rings.outputs["Fac"], 0.15, 0.95, 0.0, 1.0)

    fiber_vec = g.vmath("MULTIPLY", log_vec, (8.0, 900.0, 900.0))
    fibers = g.noise(fiber_vec, 1.0, detail=3.0, rough=0.6)
    pore_vec = g.vmath("MULTIPLY", log_vec, (60.0, 2400.0, 2400.0))
    pores = g.maprange(g.noise(pore_vec, 1.0, detail=1.0), 0.62, 0.72, 0.0, 1.0)
    blotch = g.noise(obj, 3.0, detail=4.0)
    wear = g.maprange(g.noise(obj, 1.6, detail=5.0, rough=0.65), 0.5, 0.75, 0.0, 1.0)

    dark = g.mix_color(rnd_v, (0.022, 0.012, 0.007, 1), (0.036, 0.019, 0.011, 1))
    light = g.mix_color(rnd_v, (0.085, 0.048, 0.027, 1), (0.115, 0.066, 0.036, 1))
    tone = g.math("ADD", g.math("MULTIPLY", ring, 0.75), g.math("MULTIPLY", fibers, 0.35))
    base = g.mix_color(g.math("ADD", g.math("SUBTRACT", tone, 0.15), g.math("MULTIPLY", blotch, 0.2), clamp=True), dark, light)
    base = g.mix_color(g.math("MULTIPLY", pores, 0.6), base, (0.012, 0.007, 0.004, 1))

    # plank seams
    d = g.math("ABSOLUTE", g.math("SUBTRACT", g.math("MULTIPLY", g.math("FRACT", g.math("DIVIDE", y, plank_w)), 2.0), 1.0))
    seam = g.maprange(d, 0.982, 0.998, 0.0, 1.0)
    base = g.mix_color(seam, base, (0.004, 0.002, 0.001, 1))

    rough = g.math("ADD", 0.30, g.math("MULTIPLY", wear, 0.25))
    rough = g.math("ADD", rough, g.math("MULTIPLY", g.math("SUBTRACT", fibers, 0.5), 0.15))
    rough = g.math("ADD", rough, g.math("MULTIPLY", pores, 0.2))
    coat = g.math("SUBTRACT", 0.55, g.math("MULTIPLY", wear, 0.45))

    height = g.math("SUBTRACT", g.math("MULTIPLY", fibers, 0.25), g.math("MULTIPLY", pores, 0.4))
    height = g.math("ADD", height, g.math("MULTIPLY", ring, 0.15))
    height = g.math("SUBTRACT", height, g.math("MULTIPLY", seam, 4.0))
    normal = g.bump(height, 0.35, 0.0015)

    bsdf = principled(g, **{"Coat Roughness": 0.12, "Specular IOR Level": 0.45})
    for name, v in (("Base Color", base), ("Roughness", rough), ("Coat Weight", coat),
                    ("Normal", normal), ("Coat Normal", normal)):
        g.set(bsdf.inputs[name], v)
    g.output(bsdf)
    return mat


def mat_softbox(strength, color=(1.0, 0.97, 0.93), falloff=1.2):
    """Emissive panel whose brightness falls off toward its edges, like a real
    diffused softbox. Its reflection gives the blade a smooth gradient."""
    mat = bpy.data.materials.new("Softbox")
    g = Graph(mat)
    uv = g.texcoord("UV")
    u, v, _ = g.separate(uv)
    du = g.math("ABSOLUTE", g.math("SUBTRACT", g.math("MULTIPLY", u, 2.0), 1.0))
    dv = g.math("ABSOLUTE", g.math("SUBTRACT", g.math("MULTIPLY", v, 2.0), 1.0))
    fu = g.math("POWER", g.math("SUBTRACT", 1.0, g.math("POWER", du, 4.0), clamp=True), falloff)
    fv = g.math("POWER", g.math("SUBTRACT", 1.0, g.math("POWER", dv, 2.5), clamp=True), falloff)
    em = g.node("ShaderNodeEmission", inputs={"Color": (*color, 1.0)})
    g.set(em.inputs["Strength"], g.math("MULTIPLY", g.math("MULTIPLY", fu, fv), strength))
    g.output(em)
    return mat


# ---------------------------------------------------------------------------
# Scene assembly
# ---------------------------------------------------------------------------
def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    return scene


def rest_on_table(root, parts, yaw_deg):
    """Tilt the sword so it rests on its hilt and point, like a real one on a table."""
    verts = []
    for ob in parts:
        verts.extend(v.co.copy() for v in ob.data.vertices)
    hilt = [v for v in verts if v.z < 0.05]
    blade = [v for v in verts if v.z >= 0.05]

    def low(vs, th):
        return min(v.y * math.cos(th) - v.z * math.sin(th) for v in vs)

    lo, hi = 0.0, 0.1
    for _ in range(60):
        mid = (lo + hi) / 2
        if low(blade, mid) > low(hilt, mid):
            lo = mid
        else:
            hi = mid
    tilt = (lo + hi) / 2
    rot = Matrix.Rotation(math.radians(yaw_deg), 4, "Z") @ Matrix.Rotation(math.radians(90) + tilt, 4, "X")
    lowest = min((rot @ v).z for v in verts)
    root.matrix_world = Matrix.Translation((0, 0, -lowest + 0.00005)) @ rot
    return tilt


def add_area(name, loc, target, size, energy, color, shape="RECTANGLE", size_y=None, spread=180):
    data = bpy.data.lights.new(name, "AREA")
    data.shape = shape
    data.size = size
    if size_y is not None:
        data.size_y = size_y
    data.energy = energy
    data.color = color
    data.spread = math.radians(spread)
    ob = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = loc
    ob.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return ob


def add_panel(name, center, facing, along, length, width, material):
    """Emissive plane that only shows up in reflections (invisible to camera)."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    corners = [(-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)]
    vs = [bm.verts.new((cx * width, cy * length, 0)) for cx, cy in corners]
    f = bm.faces.new(vs)
    for loop, (cx, cy) in zip(f.loops, corners):
        loop[uvl].uv = (cx + 0.5, cy + 0.5)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    me.materials.append(material)
    n = (Vector(facing)).normalized()        # emitting side faces this way
    y_ax = (Vector(along) - n * Vector(along).dot(n)).normalized()
    x_ax = y_ax.cross(n)
    m = Matrix((x_ax, y_ax, n)).transposed().to_4x4()
    m.translation = Vector(center)
    ob.matrix_world = m
    ob.visible_camera = False
    ob.visible_shadow = False
    ob.visible_diffuse = False      # a pure reflection card: lights nothing directly
    return ob


def build_world(scene, hdri=None):
    world = bpy.data.worlds.new("Studio")
    scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    nt.links.new(bg.outputs[0], out.inputs[0])
    if hdri and os.path.exists(hdri):
        env = nt.nodes.new("ShaderNodeTexEnvironment")
        env.image = bpy.data.images.load(hdri)
        nt.links.new(env.outputs[0], bg.inputs["Color"])
        bg.inputs["Strength"].default_value = 0.6
        return
    # dim studio: dark floor bounce, soft grey upper dome, slightly brighter horizon band
    coord = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(coord.outputs["Generated"], sep.inputs[0])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    nt.links.new(sep.outputs["Z"], ramp.inputs[0])
    # Generated Z on the world is the direction's z mapped to [0, 1]
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = 0.0, (0.004, 0.0035, 0.003, 1)
    els[1].position, els[1].color = 1.0, (0.035, 0.038, 0.045, 1)
    e = els.new(0.5)
    e.color = (0.012, 0.011, 0.010, 1)
    e = els.new(0.56)
    e.color = (0.05, 0.048, 0.046, 1)
    nt.links.new(ramp.outputs[0], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 1.0


def build_scene(hdri=None):
    scene = reset_scene()
    col = bpy.data.collections.new("Sword")
    scene.collection.children.link(col)

    blade = build_blade(col)
    guard = build_guard(col)
    grip = build_grip(col)
    fittings = build_fittings(col)

    steel, brass, leather = mat_blade_steel(), mat_brass(), mat_leather()
    blade.data.materials.append(steel)
    guard.data.materials.append(brass)
    fittings.data.materials.append(brass)
    grip.data.materials.append(leather)

    root = bpy.data.objects.new("Sword", None)
    col.objects.link(root)
    for ob in (blade, guard, grip, fittings):
        ob.parent = root
    rest_on_table(root, (blade, guard, grip, fittings), yaw_deg=128)

    # table
    tme = bpy.data.meshes.new("Table")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=3.0)
    bm.to_mesh(tme)
    bm.free()
    table = bpy.data.objects.new("Table", tme)
    scene.collection.objects.link(table)
    table.location = (0.35, 0.3, 0)
    table.rotation_euler = (0, 0, math.radians(8))
    tme.materials.append(mat_walnut())

    build_world(scene, hdri)
    bpy.context.view_layer.update()

    # key points in world space
    M = root.matrix_world
    blade_mid = M @ Vector((0, 0, 0.36))
    hilt = M @ Vector((0, 0, -0.08))
    guard_c = M @ Vector((0, 0, 0.0))
    blade_dir = (M.to_3x3() @ Vector((0, 0, 1))).normalized()
    blade_up = (M.to_3x3() @ Vector((0, 1, 0))).normalized()   # flat-face normal

    # ---- cameras
    def make_cam(name, loc, target, lens, fstop, focus):
        cd = bpy.data.cameras.new(name)
        cd.lens = lens
        cd.sensor_width = 36
        cd.dof.use_dof = True
        cd.dof.aperture_fstop = fstop
        cd.dof.aperture_blades = 7
        cd.dof.aperture_rotation = math.radians(12)
        cam = bpy.data.objects.new(name, cd)
        scene.collection.objects.link(cam)
        cam.location = loc
        cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        cd.dof.focus_distance = (Vector(focus) - Vector(loc)).length
        return cam

    hero_target = M @ Vector((0, 0, 0.25))
    hero_loc = hero_target + Vector((-0.12, -1.30, 0.86))
    hero = make_cam("Cam_Hero", hero_loc, hero_target + Vector((0.0, 0.0, -0.02)), 50, 5.6,
                    M @ Vector((0, 0, 0.05)))
    side = (M.to_3x3() @ Vector((1, 0, 0))).normalized()     # along the guard
    if side.y > 0:
        side = -side                                          # the camera side
    close_target = guard_c - blade_dir * 0.075
    close_loc = guard_c + blade_dir * 0.30 + side * 0.34 + Vector((0, 0, 0.24))
    closeup = make_cam("Cam_Closeup", close_loc, close_target, 60, 7.1, guard_c)
    scene.camera = hero

    # ---- lighting
    # 1) softbox placed in the mirror direction of the blade's flats as seen by the hero cam,
    #    so the steel shows a long, smooth gradient reflection
    d = (blade_mid - hero_loc).normalized()
    refl = (d - 2 * d.dot(blade_up) * blade_up).normalized()
    sb_center = blade_mid + refl * 1.5 + blade_dir * 0.05
    add_panel("Softbox_Strip", sb_center, -refl, blade_dir, 2.6, 0.55, mat_softbox(2.2))
    # soft overhead fill so the flat also reflects something in the close-up
    dc = (guard_c - close_loc).normalized()
    reflc = (dc - 2 * dc.dot(blade_up) * blade_up).normalized()
    add_panel("Softbox_Close", guard_c + reflc * 0.9, -reflc, blade_dir, 1.2, 0.5,
              mat_softbox(0.55, color=(0.92, 0.95, 1.0)))

    # 2) warm key from the upper left: shapes the wood and the brass
    add_area("Key_Warm", blade_mid + Vector((-1.4, -0.6, 1.5)), blade_mid, 0.9, 60,
             (1.0, 0.80, 0.58), size_y=0.6)
    # 3) cool rim from behind, grazing the table and catching the edges
    add_area("Rim_Cool", blade_mid + Vector((1.2, 1.9, 0.55)), blade_mid, 1.6, 90,
             (0.72, 0.84, 1.0), size_y=0.25)
    # 4) small warm kicker for the hilt
    add_area("Kicker", hilt + Vector((0.55, -0.35, 0.35)), hilt, 0.25, 4,
             (1.0, 0.86, 0.7))
    # 5) broad, weak top fill to keep shadows from going pure black
    add_area("Top_Fill", blade_mid + Vector((0, 0, 2.6)), blade_mid, 3.0, 10,
             (0.95, 0.97, 1.0))

    # ---- render settings
    scene.render.engine = "CYCLES"
    cy = scene.cycles
    cy.samples = 256
    cy.use_adaptive_sampling = True
    cy.adaptive_threshold = 0.01
    cy.use_denoising = True
    try:
        cy.denoiser = "OPENIMAGEDENOISE"
    except TypeError:
        pass
    cy.max_bounces = 12
    cy.glossy_bounces = 8
    cy.diffuse_bounces = 4
    cy.transmission_bounces = 4
    cy.caustics_reflective = False
    cy.caustics_refractive = False
    cy.blur_glossy = 0.5
    scene.render.film_transparent = False
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_depth = "16"
    scene.view_settings.view_transform = "AgX"
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    scene.view_settings.exposure = 0.0
    return scene, {"hero": hero, "closeup": closeup}


def configure_gpu(scene):
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for backend in ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"):
        try:
            prefs.compute_device_type = backend
        except TypeError:
            continue
        prefs.get_devices()
        devs = [d for d in prefs.devices if d.type != "CPU"]
        if devs:
            for d in prefs.devices:
                d.use = True
            scene.cycles.device = "GPU"
            print(f"Rendering on GPU via {backend}")
            return
    print("No GPU found, rendering on CPU")


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else argv[1:]
    here = os.path.dirname(os.path.abspath(__file__))
    p = argparse.ArgumentParser()
    p.add_argument("--render", action="store_true")
    p.add_argument("--samples", type=int, default=256)
    p.add_argument("--res", type=int, nargs=2, default=(1920, 1080))
    p.add_argument("--out", default=os.path.join(here, "renders"))
    p.add_argument("--blend", default=os.path.join(here, "sword.blend"))
    p.add_argument("--shots", default="hero,closeup")
    p.add_argument("--hdri", default=None)
    p.add_argument("--gpu", action="store_true")
    return p.parse_args(argv)


def main():
    args = parse_args()
    scene, cams = build_scene(args.hdri)
    scene.cycles.samples = args.samples
    scene.render.resolution_x, scene.render.resolution_y = args.res
    if args.gpu:
        configure_gpu(scene)
    if args.blend:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.blend), compress=True)
        print("Saved", args.blend)
    if args.render:
        os.makedirs(args.out, exist_ok=True)
        for shot in [s.strip() for s in args.shots.split(",") if s.strip()]:
            scene.camera = cams[shot]
            scene.render.filepath = os.path.join(os.path.abspath(args.out), f"sword_{shot}.png")
            bpy.ops.render.render(write_still=True)
            print("Rendered", scene.render.filepath)
        scene.camera = cams["hero"]


if __name__ == "__main__":
    main()
