"""
Procedural katana wrapped in a flowing aura, for Blender (Cycles).

The blade is lofted from shinogi-zukuri cross-sections along a curved spine
(torii-zori), with an iori-mune back, a ridge line (shinogi), a convex ji
and a curved kissaki. Its hamon, polished shinogi-ji and forging grain are
procedural. The mounts are a gold habaki, seppa, an iron tsuba with ishime
texture, shakudo fuchi/kashira, gold menuki and a black silk tsuka-ito wrap
over white samegawa.

The aura is an animated volume that hugs the blade and streams toward the
point: black smoke with crimson fire, or violet haze with crimson fire.

    python make_katana.py --render                     # bpy pip module
    blender -b -P make_katana.py -- --render           # Blender binary

Options:
    --aura crimson|violet  colour scheme (default crimson: black and red)
    --render               render the stills
    --animate              render the looping aura animation (frames 1-72)
    --samples N            Cycles samples (default 256)
    --res W H              resolution (default 1920 1080)
    --shots hero,closeup   cameras to render
    --out DIR              output folder (default ./renders)
    --gpu                  render on the GPU if one is available
"""

import argparse
import math
import os
import random
import sys

import bpy  # must come first when running via the bpy pip module
import bmesh
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "sword"))
from make_sword import (Graph, add_area, add_panel, configure_gpu,  # noqa: E402
                        mat_softbox, mesh_object, principled,
                        smoothstep, superellipse)

# ---------------------------------------------------------------------------
# Dimensions (metres). Katana local frame: blade runs along +Z from the
# habaki, the spine (mune) faces +X, the edge (ha) faces -X, the flats face ±Y.
# ---------------------------------------------------------------------------
NAGASA = 0.705            # blade length
SORI = 0.018              # curvature (sagitta)
RADIUS = NAGASA ** 2 / (8 * SORI)
MOTOHABA = 0.031          # width at the base
SAKIHABA = 0.021          # width at the yokote
KASANE0, KASANE1 = 0.0073, 0.0052
KISSAKI = 0.036
SHINOGI = 0.30            # ridge position as a fraction of the width, from the back
MUNE_PEAK = 0.0011
EDGE_HALF = 0.00012

HABAKI_LEN = 0.033
TSUBA_Z0, TSUBA_Z1 = -0.0032, -0.0082
FUCHI_Z0, FUCHI_Z1 = -0.0095, -0.0235
TSUKA_Z0, TSUKA_Z1 = -0.0225, -0.262
KASHIRA_Z1 = -0.284
TSUKA_X = -MOTOHABA * 0.47   # the handle is centred under the blade
TSUKA_A, TSUKA_B = 0.0166, 0.0123

AURA = {
    # core fire, outer colour, whether the outer layer is dark smoke
    "crimson": {"core": (1.0, 0.06, 0.03), "hot": (1.0, 0.35, 0.12),
                "outer": (0.0, 0.0, 0.0), "smoke": True, "light": (1.0, 0.12, 0.06)},
    "violet": {"core": (1.0, 0.05, 0.08), "hot": (1.0, 0.30, 0.25),
               "outer": (0.42, 0.05, 1.0), "smoke": False, "light": (0.75, 0.12, 0.85)},
    # electric: a faint ionised glow, branching bolts, and a blue-charged blade
    "lightning": {"core": (0.12, 0.42, 1.0), "hot": (0.6, 0.82, 1.0),
                  "outer": (0.05, 0.22, 1.0), "smoke": False, "light": (0.30, 0.55, 1.0),
                  "lightning": True, "gain": 0.3},
}


# ---------------------------------------------------------------------------
# Blade
# ---------------------------------------------------------------------------
def spine(s):
    """Point on the mune line, its tangent and its outward (spine-side) normal."""
    a = s / RADIUS
    p = Vector((RADIUS * (1 - math.cos(a)), 0.0, RADIUS * math.sin(a)))
    t = Vector((math.sin(a), 0.0, math.cos(a)))
    n = Vector((math.cos(a), 0.0, -math.sin(a)))
    return p, t, n


def blade_profile(s):
    """(back offset e0, width W, half thickness, kissaki fraction u)."""
    body = NAGASA - KISSAKI
    if s <= body:
        k = s / body
        w = MOTOHABA + (SAKIHABA - MOTOHABA) * k ** 0.9
        t = KASANE0 + (KASANE1 - KASANE0) * k
        return 0.0, w, t / 2, 0.0
    u = (s - body) / KISSAKI
    e0 = 0.24 * SAKIHABA * u ** 2                         # the back curves down into the point
    w = SAKIHABA * max(0.0, 1 - u ** 1.9) ** 0.55 * (1 - 0.24 * u ** 2)
    t = KASANE1 * (1 - 0.8 * u ** 1.4)
    return e0, w, t / 2, u


def build_blade(col):
    bm = bmesh.new()
    uv_layer = bm.loops.layers.uv.new("UVMap")
    zone_layer = bm.faces.layers.float.new("zone")      # 0 mune, 1 shinogi-ji, 2 ji
    n_st = 240
    rings, metas = [], []
    for i in range(n_st):
        k = i / (n_st - 1)
        s = NAGASA * (1 - (1 - k) ** 1.25)
        p, _, nrm = spine(s)
        edge_dir = -nrm
        e0, w, ht, u = blade_profile(s)
        if i == n_st - 1:
            tip = p + edge_dir * (e0 + 0.0003)
            rings.append([bm.verts.new(tip)])
            metas.append(None)
            break
        tm = ht * 0.82                                     # back is a little thinner than the ridge
        sh = SHINOGI * w
        half = [(-MUNE_PEAK * (1 - u), 0.0, 0)]            # peaked iori-mune
        half.append((0.0, tm, 0))
        for j in range(1, 5):
            f = j / 4
            half.append((sh * f, tm + (ht - tm) * f ** 0.8, 1))
        for j in range(1, 15):
            f = j / 14
            y = EDGE_HALF + (ht - EDGE_HALF) * (1 - f) ** 0.72
            half.append((sh + (w - sh) * f, y, 2))
        top = half
        bottom = [(e, -y, z) for e, y, z in reversed(half[1:])]
        prof = top + bottom
        ring, meta = [], []
        for e, y, z in prof:
            pos = p + edge_dir * (e0 + e) + Vector((0, y, 0))
            ring.append(bm.verts.new(pos))
            meta.append((s, (e) / max(w, 1e-5), z))
        rings.append(ring)
        metas.append(meta)

    for i in range(len(rings) - 1):
        r0, r1, m0 = rings[i], rings[i + 1], metas[i]
        m1 = metas[i + 1]
        n = len(r0)
        for a in range(n):
            b = (a + 1) % n
            if len(r1) == 1:
                f = bm.faces.new((r0[a], r0[b], r1[0]))
                cols = [(m0[a][0], m0[a][1]), (m0[b][0], m0[b][1]), (NAGASA, 0.0)]
            else:
                f = bm.faces.new((r0[a], r0[b], r1[b], r1[a]))
                cols = [(m0[a][0], m0[a][1]), (m0[b][0], m0[b][1]),
                        (m1[b][0], m1[b][1]), (m1[a][0], m1[a][1])]
            za, zb = m0[a][2], m0[b][2]
            f[zone_layer] = float(max(za, zb)) if za != zb else float(za)
            for loop, (s, v) in zip(f.loops, cols):
                loop[uv_layer].uv = (s, v)
    bm.faces.new(list(reversed(rings[0])))
    bm.normal_update()
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return mesh_object("Blade", bm, col, smooth_angle=14.0)


# ---------------------------------------------------------------------------
# Mounts
# ---------------------------------------------------------------------------
def sweep_ovals(bm, stations, cx=0.0, n=72, p=2.0, cap=True):
    """stations: list of (z, a, b) -> rings of superellipses centred at (cx, 0, z)."""
    rings = []
    for z, a, b in stations:
        rings.append([bm.verts.new((cx + x, y, z)) for x, y in superellipse(n, a, b, p)])
    for r0, r1 in zip(rings, rings[1:]):
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((r0[i], r0[j], r1[j], r1[i]))
    if cap:
        bm.faces.new(list(reversed(rings[0])))
        bm.faces.new(rings[-1])
    return rings


def build_habaki(col):
    bm = bmesh.new()
    cx = -MOTOHABA * 0.47
    st = []
    for i in range(24):
        k = i / 23
        z = -0.0005 + HABAKI_LEN * k
        a = MOTOHABA / 2 + 0.0019 - 0.0004 * k
        b = KASANE0 / 2 + 0.0019 - 0.0006 * k
        # rounded top lip
        lip = smoothstep(0.9, 1.0, k)
        st.append((z, a - 0.0008 * lip, b - 0.0008 * lip))
    sweep_ovals(bm, st, cx=cx, n=64, p=3.2)
    bm.normal_update()
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return mesh_object("Habaki", bm, col, smooth_angle=40.0)


def build_seppa(col):
    bm = bmesh.new()
    for z0, z1 in ((-0.0006, TSUBA_Z0), (TSUBA_Z1, FUCHI_Z0 + 0.0002)):
        sweep_ovals(bm, [(z0, 0.0215, 0.0135), (z1, 0.0215, 0.0135)], cx=TSUKA_X, n=64, p=2.3)
    bm.normal_update()
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return mesh_object("Seppa", bm, col, smooth_angle=50.0)


def build_tsuba(col):
    """Rounded-square iron guard with a raised rim (mimi)."""
    bm = bmesh.new()
    n = 144
    ra, rb, p = 0.0395, 0.0375, 2.35
    profile = [(-0.0022, TSUBA_Z0), (-0.0007, TSUBA_Z0 - 0.0004), (0.0, TSUBA_Z0 - 0.0016),
               (0.0, TSUBA_Z1 + 0.0016), (-0.0007, TSUBA_Z1 + 0.0004), (-0.0022, TSUBA_Z1)]
    rings = []
    for inset, z in profile:
        rings.append([bm.verts.new((TSUKA_X + x, y, z))
                      for x, y in superellipse(n, ra + inset, rb + inset, p)])
    # plate faces inside the rim are recessed slightly
    inner_top = [bm.verts.new((TSUKA_X + x, y, TSUBA_Z0 + 0.0004))
                 for x, y in superellipse(n, ra - 0.0042, rb - 0.0042, p)]
    inner_bot = [bm.verts.new((TSUKA_X + x, y, TSUBA_Z1 - 0.0004))
                 for x, y in superellipse(n, ra - 0.0042, rb - 0.0042, p)]
    rings = [inner_top] + rings + [inner_bot]
    for r0, r1 in zip(rings, rings[1:]):
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((r0[i], r0[j], r1[j], r1[i]))
    bm.faces.new(list(reversed(inner_top)))
    bm.faces.new(inner_bot)
    bm.normal_update()
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return mesh_object("Tsuba", bm, col, smooth_angle=35.0)


def tsuka_axes(z):
    t = (z - TSUKA_Z0) / (TSUKA_Z1 - TSUKA_Z0)
    waist = 1 - 0.055 * math.sin(math.pi * t)
    flare = 1 + 0.03 * t
    return TSUKA_A * waist * flare, TSUKA_B * waist * flare


def build_tsuka(col):
    bm = bmesh.new()
    st = []
    for i in range(80):
        z = TSUKA_Z0 + (TSUKA_Z1 - TSUKA_Z0) * i / 79
        a, b = tsuka_axes(z)
        st.append((z, a, b))
    sweep_ovals(bm, st, cx=TSUKA_X, n=96)
    bm.normal_update()
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return mesh_object("Tsuka", bm, col, smooth_angle=60.0)


def build_fittings(col):
    """Fuchi collar and domed kashira cap, both shakudo."""
    bm = bmesh.new()
    a0, b0 = tsuka_axes(TSUKA_Z0)
    st = []
    for i in range(16):
        k = i / 15
        z = FUCHI_Z0 + (FUCHI_Z1 - FUCHI_Z0) * k
        bulge = 0.0012 + 0.0006 * math.sin(math.pi * k)
        st.append((z, a0 + bulge, b0 + bulge))
    sweep_ovals(bm, st, cx=TSUKA_X, n=96)
    a1, b1 = tsuka_axes(TSUKA_Z1)
    st = []
    for i in range(20):
        k = i / 19
        z = TSUKA_Z1 + 0.004 + (KASHIRA_Z1 - TSUKA_Z1 - 0.004) * k
        dome = math.sqrt(max(0.0, 1 - max(0.0, (k - 0.45) / 0.55) ** 2))
        grow = 0.0012
        st.append((z, (a1 + grow) * max(dome, 0.05), (b1 + grow) * max(dome, 0.05)))
    sweep_ovals(bm, st, cx=TSUKA_X, n=96)
    bm.normal_update()
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return mesh_object("Fittings", bm, col, smooth_angle=38.0)


def build_menuki(col):
    """Gold ornaments on both faces of the grip, peeking between the wrap."""
    bm = bmesh.new()
    for side, zc in ((1, -0.125), (-1, -0.155)):
        a, b = tsuka_axes(zc)
        center = Vector((TSUKA_X, side * (b - 0.0004), zc))
        prof = [(0.0, 0.0028), (0.0035, 0.0026), (0.0062, 0.0018), (0.0078, 0.0006), (0.0082, -0.0008)]
        rings = []
        n = 48
        for r, h in prof:
            if r < 1e-7:
                rings.append([bm.verts.new(center + Vector((0, side * h, 0)))])
                continue
            ring = []
            for i in range(n):
                t = 2 * math.pi * i / n
                # elongated along the grip
                ring.append(bm.verts.new(center + Vector((r * 0.55 * math.cos(t), side * h, r * 1.45 * math.sin(t)))))
            rings.append(ring)
        for i in range(n):
            bm.faces.new((rings[0][0], rings[1][i], rings[1][(i + 1) % n]))
        for r0, r1 in zip(rings[1:], rings[2:]):
            for i in range(n):
                j = (i + 1) % n
                bm.faces.new((r0[i], r0[j], r1[j], r1[i]))
    bm.normal_update()
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return mesh_object("Menuki", bm, col, smooth_angle=50.0)


# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------
def mat_blade(scheme):
    mat = bpy.data.materials.new("Tamahagane")
    g = Graph(mat)
    uv = g.node("ShaderNodeUVMap", uv_map="UVMap").outputs["UV"]
    s, v, _ = g.separate(uv)
    zone = g.node("ShaderNodeAttribute", attribute_name="zone").outputs["Fac"]
    obj = g.texcoord("Object")

    # hamon: a notare/gunome wave with irregular clusters, returning in the boshi
    wave = g.math("SINE", g.math("MULTIPLY", s, 2 * math.pi / 0.043))
    wave2 = g.math("SINE", g.math("ADD", g.math("MULTIPLY", s, 2 * math.pi / 0.017), 1.3))
    irregular = g.noise(g.combine(g.math("MULTIPLY", s, 30.0), 0.0, 0.0), 1.0, detail=3.0)
    h = g.math("ADD", 0.66, g.math("MULTIPLY", wave, 0.075))
    h = g.math("ADD", h, g.math("MULTIPLY", wave2, 0.035))
    h = g.math("ADD", h, g.math("MULTIPLY", g.math("SUBTRACT", irregular, 0.5), 0.16))
    kiss = g.maprange(s, NAGASA - KISSAKI, NAGASA, 0.0, 1.0)
    h = g.mix_float(kiss, h, 0.55)
    # misty nioi boundary rather than a hard line
    mist = g.noise(g.vmath("MULTIPLY", obj, (60.0, 60.0, 25.0)), 1.0, detail=4.0)
    hard = g.maprange(g.math("ADD", g.math("SUBTRACT", v, h), g.math("MULTIPLY", g.math("SUBTRACT", mist, 0.5), 0.06)),
                      -0.015, 0.03, 0.0, 1.0)
    ji = g.math("MULTIPLY", g.math("SUBTRACT", 1.0, hard), g.maprange(zone, 1.5, 2.0, 0.0, 1.0))
    nioi = g.math("MULTIPLY", g.maprange(g.math("ABSOLUTE", g.math("SUBTRACT", v, h)), 0.0, 0.03, 1.0, 0.0),
                  g.maprange(zone, 1.5, 2.0, 0.0, 1.0))
    # nie: tiny bright crystals scattered along the boundary
    nie = g.maprange(g.noise(g.vmath("MULTIPLY", obj, (900.0, 900.0, 900.0)), 1.0, detail=1.0), 0.68, 0.72, 0.0, 1.0)
    nie = g.math("MULTIPLY", nie, nioi)
    # forging grain (itame hada) stretched along the blade
    hada = g.noise(g.combine(g.math("MULTIPLY", s, 90.0), g.math("MULTIPLY", v, 700.0), 0.0), 1.0, detail=6.0, rough=0.65,
                   distortion=1.2)
    polished = g.maprange(zone, 0.0, 1.5, 1.0, 0.0)   # shinogi-ji and mune are burnished

    electric = AURA[scheme].get("lightning", False)
    ji_a, ji_b, hamon_c, burnish = ((0.34, 0.36, 0.39, 1), (0.46, 0.48, 0.51, 1), (0.80, 0.80, 0.79, 1),
                                    (0.30, 0.31, 0.33, 1))
    if electric:   # cold, blued steel
        ji_a, ji_b, hamon_c, burnish = ((0.10, 0.17, 0.36, 1), (0.17, 0.27, 0.50, 1), (0.52, 0.68, 0.95, 1),
                                        (0.08, 0.13, 0.28, 1))
    base = g.mix_color(g.math("MULTIPLY", g.math("SUBTRACT", hada, 0.3), 0.6), ji_a, ji_b)
    base = g.mix_color(hard, base, hamon_c)
    base = g.mix_color(g.math("MULTIPLY", polished, 0.85), base, burnish)
    base = g.mix_color(nie, base, (0.95, 0.95, 0.95, 1))

    rough = g.math("ADD", 0.07, g.math("MULTIPLY", g.math("SUBTRACT", hada, 0.5), 0.05))
    rough = g.mix_float(hard, rough, 0.26)                 # the hamon polishes up frosty white
    rough = g.mix_float(polished, rough, 0.03)
    rough = g.math("ADD", rough, g.math("MULTIPLY", nie, -0.1), clamp=True)
    metallic = g.mix_float(hard, 1.0, 0.72)

    height = g.math("MULTIPLY", hada, g.math("MULTIPLY", ji, 1.0))
    normal = g.bump(height, 0.05, 0.0003)

    # faint charged glow along the very edge, in the aura colour
    edge = g.maprange(v, 0.93, 1.0, 0.0, 1.0)
    flicker = g.noise(g.combine(g.math("MULTIPLY", s, 20.0), 0.0, 0.0), 1.0, detail=2.0)
    glow = g.math("MULTIPLY", g.math("MULTIPLY", edge, g.maprange(zone, 1.5, 2.0, 0.0, 1.0)),
                  g.maprange(flicker, 0.3, 0.7, 0.4, 1.6))

    strength = g.math("MULTIPLY", glow, 3.5)
    if electric:
        # lightning veins crawling through the ji, and a charged hamon line
        in_ji = g.maprange(zone, 1.5, 2.0, 0.0, 1.0)
        cells = g.node("ShaderNodeTexVoronoi", feature="DISTANCE_TO_EDGE", inputs={"Scale": 1.0, "Randomness": 1.0})
        warp = g.noise(g.combine(g.math("MULTIPLY", s, 60.0), g.math("MULTIPLY", v, 8.0), 0.0), 1.0, detail=3.0)
        g.set(cells.inputs["Vector"], g.combine(g.math("ADD", g.math("MULTIPLY", s, 55.0), g.math("MULTIPLY", warp, 1.2)),
                                                g.math("MULTIPLY", v, 5.0), 0.0))
        veins = g.maprange(cells.outputs["Distance"], 0.0, 0.035, 1.0, 0.0)
        patches = g.maprange(g.noise(g.combine(g.math("MULTIPLY", s, 9.0), g.math("MULTIPLY", v, 2.0), 3.0), 1.0,
                                     detail=2.0), 0.48, 0.62, 0.0, 1.0)
        veins = g.math("MULTIPLY", g.math("MULTIPLY", veins, patches), in_ji)
        strength = g.math("ADD", g.math("MULTIPLY", glow, 6.0), g.math("MULTIPLY", veins, 9.0))
        strength = g.math("ADD", strength, g.math("MULTIPLY", nioi, 5.0))
    bsdf = principled(g, **{"Emission Color": (*AURA[scheme]["core"], 1.0)})
    for name, val in (("Base Color", base), ("Roughness", rough), ("Metallic", metallic),
                      ("Normal", normal)):
        g.set(bsdf.inputs[name], val)
    g.set(bsdf.inputs["Emission Strength"], strength)
    g.output(bsdf)
    return mat


def mat_gold():
    mat = bpy.data.materials.new("Gold Foil")
    g = Graph(mat)
    obj = g.texcoord("Object")
    rot = g.node("ShaderNodeVectorRotate", rotation_type="Y_AXIS", inputs={"Angle": math.radians(40)})
    g.set(rot.inputs["Vector"], obj)
    lines = g.noise(g.vmath("MULTIPLY", rot.outputs[0], (2400.0, 2400.0, 40.0)), 1.0, detail=1.0)
    grime = g.noise(obj, 220.0, detail=4.0)
    ao = g.node("ShaderNodeAmbientOcclusion", inputs={"Distance": 0.003}, samples=12)
    dirt = g.maprange(ao.outputs["AO"], 0.5, 1.0, 1.0, 0.0)
    base = g.mix_color(g.math("MULTIPLY", grime, 0.25), (1.0, 0.74, 0.30, 1), (0.85, 0.56, 0.22, 1))
    base = g.mix_color(dirt, base, (0.18, 0.11, 0.04, 1))
    rough = g.math("ADD", 0.16, g.math("MULTIPLY", lines, 0.12))
    normal = g.bump(lines, 0.08, 0.0002)
    bsdf = principled(g, **{"Metallic": 1.0})
    for name, val in (("Base Color", base), ("Roughness", rough), ("Normal", normal)):
        g.set(bsdf.inputs[name], val)
    g.output(bsdf)
    return mat


def mat_iron():
    """Tsuba iron: dark, with a hammered ishime surface and a polished rim."""
    mat = bpy.data.materials.new("Tsuba Iron")
    g = Graph(mat)
    obj = g.texcoord("Object")
    ishime = g.node("ShaderNodeTexVoronoi", feature="F1", inputs={"Scale": 1400.0})
    g.set(ishime.inputs["Vector"], obj)
    pits = ishime.outputs["Distance"]
    rust = g.maprange(g.noise(obj, 90.0, detail=5.0), 0.55, 0.8, 0.0, 1.0)
    ao = g.node("ShaderNodeAmbientOcclusion", inputs={"Distance": 0.004}, samples=12)
    edge_polish = g.maprange(ao.outputs["AO"], 0.85, 1.0, 0.0, 1.0)
    base = g.mix_color(rust, (0.030, 0.027, 0.025, 1), (0.075, 0.038, 0.022, 1))
    base = g.mix_color(g.math("MULTIPLY", edge_polish, 0.5), base, (0.11, 0.10, 0.095, 1))
    rough = g.mix_float(edge_polish, 0.55, 0.28)
    rough = g.math("ADD", rough, g.math("MULTIPLY", rust, 0.15))
    normal = g.bump(pits, 0.35, 0.0004)
    bsdf = principled(g, **{"Metallic": 0.85})
    for name, val in (("Base Color", base), ("Roughness", rough), ("Normal", normal)):
        g.set(bsdf.inputs[name], val)
    g.output(bsdf)
    return mat


def mat_shakudo():
    """Blue-black copper-gold alloy with a nanako (fish-roe) dot ground."""
    mat = bpy.data.materials.new("Shakudo")
    g = Graph(mat)
    obj = g.texcoord("Object")
    dots = g.node("ShaderNodeTexVoronoi", feature="F1", inputs={"Scale": 700.0, "Randomness": 0.15})
    g.set(dots.inputs["Vector"], obj)
    dome = g.maprange(dots.outputs["Distance"], 0.0, 0.45, 1.0, 0.0)
    base = g.mix_color(dome, (0.018, 0.017, 0.022, 1), (0.05, 0.045, 0.06, 1))
    bsdf = principled(g, **{"Metallic": 0.9, "Roughness": 0.22})
    g.set(bsdf.inputs["Base Color"], base)
    g.set(bsdf.inputs["Normal"], g.bump(dome, 0.4, 0.0003))
    g.output(bsdf)
    return mat


def mat_tsuka():
    """Black silk tsuka-ito crossing over white samegawa (ray skin)."""
    mat = bpy.data.materials.new("Tsuka-ito")
    g = Graph(mat)
    obj = g.texcoord("Object")
    x, y, z = g.separate(obj)
    xn = g.math("DIVIDE", g.math("SUBTRACT", x, TSUKA_X), TSUKA_A)
    yn = g.math("DIVIDE", y, TSUKA_B)
    theta = g.math("DIVIDE", g.math("ARCTAN2", yn, xn), math.pi)      # -1..1 around the grip
    period = 0.0325
    zp = g.math("DIVIDE", z, period)
    ph1 = g.math("ADD", zp, theta)
    ph2 = g.math("SUBTRACT", zp, theta)

    def band(ph):
        tri = g.math("MULTIPLY", g.math("ABSOLUTE", g.math("SUBTRACT", g.math("FRACT", ph), 0.5)), 2.0)
        inside = g.maprange(tri, 0.70, 0.66, 0.0, 1.0)
        prof = g.math("POWER", g.math("SUBTRACT", 1.0, g.math("POWER", g.math("DIVIDE", tri, 0.70), 2.0), clamp=True), 0.5)
        return inside, prof, tri

    in1, p1, tri1 = band(ph1)
    in2, p2, tri2 = band(ph2)
    cord = g.math("MAXIMUM", in1, in2)
    # over/under: alternate which cord sits on top at each crossing
    parity = g.math("MODULO", g.math("FLOOR", g.math("ADD", ph1, ph2)), 2.0)
    top = g.mix_float(parity, g.math("ADD", p1, g.math("MULTIPLY", p2, 0.6)), g.math("ADD", p2, g.math("MULTIPLY", p1, 0.6)))
    # silk strands run along each cord
    strands1 = g.noise(g.combine(g.math("MULTIPLY", tri1, 60.0), g.math("MULTIPLY", ph1, 2.0), 0.0), 1.0, detail=2.0)
    strands2 = g.noise(g.combine(g.math("MULTIPLY", tri2, 60.0), g.math("MULTIPLY", ph2, 2.0), 0.0), 1.0, detail=2.0)
    strands = g.mix_float(parity, strands1, strands2)

    same = g.node("ShaderNodeTexVoronoi", feature="F1", inputs={"Scale": 520.0, "Randomness": 0.9})
    g.set(same.inputs["Vector"], obj)
    nodules = g.maprange(same.outputs["Distance"], 0.0, 0.5, 1.0, 0.0)

    base_same = g.mix_color(nodules, (0.52, 0.49, 0.42, 1), (0.82, 0.80, 0.72, 1))
    base_ito = g.mix_color(g.math("MULTIPLY", strands, 0.6), (0.010, 0.010, 0.012, 1), (0.03, 0.028, 0.03, 1))
    base = g.mix_color(cord, base_same, base_ito)
    rough = g.mix_float(cord, 0.45, g.math("ADD", 0.42, g.math("MULTIPLY", strands, 0.2)))
    sheen = g.math("MULTIPLY", cord, 0.8)
    height = g.mix_float(cord, g.math("MULTIPLY", nodules, 0.25), g.math("ADD", 0.6, g.math("MULTIPLY", top, 0.8)))
    height = g.math("ADD", height, g.math("MULTIPLY", strands, g.math("MULTIPLY", cord, 0.12)))
    normal = g.bump(height, 0.8, 0.0018)

    bsdf = principled(g, **{"Sheen Roughness": 0.3, "Sheen Tint": (0.6, 0.6, 0.7, 1.0)})
    for name, val in (("Base Color", base), ("Roughness", rough), ("Sheen Weight", sheen), ("Normal", normal)):
        g.set(bsdf.inputs[name], val)
    g.output(bsdf)
    return mat


def mat_floor():
    mat = bpy.data.materials.new("Wet Obsidian")
    g = Graph(mat)
    obj = g.texcoord("Object")
    puddles = g.maprange(g.noise(obj, 1.6, detail=4.0, rough=0.6), 0.42, 0.58, 0.0, 1.0)
    grain = g.noise(obj, 60.0, detail=6.0)
    base = g.mix_color(g.math("MULTIPLY", grain, 0.4), (0.006, 0.006, 0.007, 1), (0.018, 0.016, 0.017, 1))
    rough = g.mix_float(puddles, g.math("ADD", 0.28, g.math("MULTIPLY", grain, 0.15)), 0.035)
    normal = g.bump(g.math("MULTIPLY", grain, g.math("SUBTRACT", 1.0, puddles)), 0.25, 0.002)
    bsdf = principled(g, **{"Specular IOR Level": 0.6})
    for name, val in (("Base Color", base), ("Roughness", rough), ("Normal", normal)):
        g.set(bsdf.inputs[name], val)
    g.output(bsdf)
    return mat


def mat_aura(scheme):
    """Animated volume hugging the blade and streaming toward the point."""
    cfg = AURA[scheme]
    mat = bpy.data.materials.new(f"Aura ({scheme})")
    g = Graph(mat)
    obj = g.texcoord("Object")
    x, y, z = g.separate(obj)

    time = g.node("ShaderNodeValue")
    time.label = "Time (s)"
    fc = time.outputs[0].driver_add("default_value")
    fc.driver.type = "SCRIPTED"
    fc.driver.expression = "frame / 24"

    # distance to the (curved, flat) blade: bend x back by the curvature,
    # then measure from a slab 2*halfw wide and 0 thick
    bend = g.math("DIVIDE", g.math("MULTIPLY", z, z), 2 * RADIUS)
    halfw = g.maprange(z, 0.0, NAGASA, MOTOHABA / 2, SAKIHABA / 2 * 0.6)
    across = g.math("SUBTRACT", g.math("SUBTRACT", x, bend), g.math("MULTIPLY", halfw, -1.0))
    dx = g.math("MAXIMUM", g.math("SUBTRACT", g.math("ABSOLUTE", across), halfw), 0.0)
    zc = g.math("MINIMUM", g.math("MAXIMUM", z, HABAKI_LEN), NAGASA)
    dz = g.math("ABSOLUTE", g.math("SUBTRACT", z, zc))
    dist = g.vmath("LENGTH", g.combine(dx, y, g.math("MULTIPLY", dz, 0.55)))

    # flow: noise space slides toward the point and churns over time
    t = time.outputs[0]
    flow = g.combine(g.math("MULTIPLY", t, 0.02), g.math("MULTIPLY", t, -0.015), g.math("MULTIPLY", t, -0.32))
    pflow = g.vmath("ADD", obj, flow)
    warp = g.node("ShaderNodeTexNoise", noise_dimensions="4D",
                  inputs={"Scale": 9.0, "Detail": 2.0, "Roughness": 0.5})
    g.set(warp.inputs["Vector"], pflow)
    g.set(warp.inputs["W"], g.math("MULTIPLY", t, 0.35))
    pwarp = g.vmath("ADD", pflow, g.vmath("MULTIPLY", g.vmath("SUBTRACT", warp.outputs["Color"], (0.5, 0.5, 0.5)), (0.05, 0.05, 0.08)))
    flame = g.node("ShaderNodeTexNoise", noise_dimensions="4D",
                   inputs={"Scale": 24.0, "Detail": 5.0, "Roughness": 0.62, "Lacunarity": 2.1})
    g.set(flame.inputs["Vector"], g.vmath("MULTIPLY", pwarp, (1.0, 1.0, 0.45)))
    g.set(flame.inputs["W"], g.math("MULTIPLY", t, 0.6))
    n = flame.outputs["Fac"]

    # tongues: the noise pushes the falloff outward in places
    reach = g.math("ADD", 0.012, g.math("MULTIPLY", g.maprange(n, 0.35, 0.75, 0.0, 1.0), 0.075))
    core = g.math("POWER", g.maprange(dist, 0.0, reach, 1.0, 0.0), 1.6)
    wisp = g.maprange(n, 0.45, 0.72, 0.0, 1.0)
    # mostly separate licking tongues, over a faint constant sheath
    tongues = g.math("POWER", wisp, 1.4)
    fire = g.math("MULTIPLY", core, g.math("ADD", 0.06, g.math("MULTIPLY", tongues, 1.1)), clamp=True)
    # the aura thins out along the tang side and flares past the point
    along = g.maprange(z, -0.01, 0.06, 0.0, 1.0)
    fire = g.math("MULTIPLY", fire, along)

    # a second, slower field for the smoke / haze so it doesn't just trace the fire
    smoke_n = g.node("ShaderNodeTexNoise", noise_dimensions="4D",
                     inputs={"Scale": 13.0, "Detail": 4.0, "Roughness": 0.6, "Distortion": 0.4})
    g.set(smoke_n.inputs["Vector"], g.vmath("MULTIPLY", pwarp, (1.0, 1.0, 0.6)))
    g.set(smoke_n.inputs["W"], g.math("ADD", g.math("MULTIPLY", t, 0.25), 7.0))
    sn = smoke_n.outputs["Fac"]
    outer_reach = g.math("ADD", 0.04, g.math("MULTIPLY", g.maprange(sn, 0.3, 0.8, 0.0, 1.0), 0.12))
    halo = g.math("POWER", g.maprange(dist, 0.004, outer_reach, 1.0, 0.0), 1.2)
    haze = g.math("MULTIPLY", g.math("MULTIPLY", halo, g.maprange(sn, 0.48, 0.66, 0.0, 1.0)), along)

    hot = g.maprange(fire, 0.55, 1.0, 0.0, 1.0)
    fire_col = g.mix_color(hot, (*cfg["core"], 1.0), (*cfg["hot"], 1.0))

    vol = g.node("ShaderNodeVolumePrincipled")
    # a little scattering lets the smoke catch the firelight instead of vanishing
    vol.inputs["Color"].default_value = (0.05, 0.05, 0.05, 1.0)
    vol.inputs["Absorption Color"].default_value = (0.0, 0.0, 0.0, 1.0)
    if cfg["smoke"]:
        # black smoke: absorbs, so it darkens the fire and the scene behind it
        density = g.math("ADD", g.math("MULTIPLY", haze, 160.0), g.math("MULTIPLY", fire, 6.0))
        emit_col = fire_col
        emit = g.math("MULTIPLY", fire, 45.0)
    else:
        density = g.math("ADD", g.math("MULTIPLY", haze, 6.0), g.math("MULTIPLY", fire, 4.0))
        mix_f = g.maprange(fire, 0.05, 0.4, 0.0, 1.0)
        emit_col = g.mix_color(mix_f, (*cfg["outer"], 1.0), fire_col)
        emit = g.math("ADD", g.math("MULTIPLY", fire, 45.0), g.math("MULTIPLY", haze, 7.0))
    g.set(vol.inputs["Density"], density)
    g.set(vol.inputs["Emission Color"], emit_col)
    g.set(vol.inputs["Emission Strength"], g.math("MULTIPLY", emit, cfg.get("gain", 1.0)))
    out = g.node("ShaderNodeOutputMaterial")
    g.set(out.inputs["Volume"], vol.outputs[0])
    return mat


# ---------------------------------------------------------------------------
# Lightning
# ---------------------------------------------------------------------------
def jagged(a, b, rng, depth, rough, bulge=None):
    """Midpoint-displacement bolt from a to b (optionally through a bulge point)."""
    pts = [a, bulge, b] if bulge is not None else [a, b]
    for _ in range(depth):
        out = [pts[0]]
        for p, q in zip(pts, pts[1:]):
            seg = q - p
            ln = seg.length
            r = Vector((rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 1)))
            r -= seg.normalized() * r.dot(seg.normalized())
            out += [(p + q) / 2 + r * ln * rough * 0.5, q]
        pts = out
    return pts


def blade_point(s, e_frac, y=0.0):
    p, _, n = spine(s)
    e0, w, _, _ = blade_profile(s)
    return p - n * (e0 + w * e_frac) + Vector((0, y, 0))


def build_bolts(col, rng):
    """Branching bolts: arcs that jump along the blade, strikes reaching into the
    air, and discharges off the point. Returns (curve objects, flash positions)."""
    paths = []
    for _ in range(5):                       # arcs hopping along the edge / spine
        s1 = rng.uniform(0.07, 0.58)
        s2 = min(s1 + rng.uniform(0.06, 0.16), NAGASA - 0.02)
        side = rng.choice((1.0, 0.0))
        a = blade_point(s1, side, rng.uniform(-0.002, 0.002))
        b = blade_point(s2, rng.choice((1.0, 0.0)), rng.uniform(-0.002, 0.002))
        _, _, n = spine((s1 + s2) / 2)
        out = -n if side else n
        mid = (a + b) / 2 + out * rng.uniform(0.018, 0.045) + Vector((0, rng.uniform(-0.03, 0.03), 0))
        paths.append((jagged(a, b, rng, 5, 0.32, mid), 0.00055))
    for _ in range(4):                       # strikes reaching out into the air
        s1 = rng.uniform(0.1, 0.62)
        side = rng.choice((1.0, 0.0))
        a = blade_point(s1, side)
        _, t, n = spine(s1)
        out = (-n if side else n) * rng.uniform(0.6, 1.0) + Vector((0, rng.uniform(-0.8, 0.8), 0)) + t * rng.uniform(0.1, 0.6)
        b = a + out.normalized() * rng.uniform(0.09, 0.17)
        paths.append((jagged(a, b, rng, 6, 0.36), 0.0006))
    tip = spine(NAGASA)[0]
    _, t_tip, _ = spine(NAGASA)
    for _ in range(2):                       # discharges off the point
        d = t_tip + Vector((rng.uniform(-0.5, 0.5), rng.uniform(-0.5, 0.5), 0))
        paths.append((jagged(tip, tip + d.normalized() * rng.uniform(0.08, 0.14), rng, 6, 0.4), 0.0005))

    # branches split off the main bolts
    branches = []
    for pts, radius in paths:
        for _ in range(rng.randint(1, 3)):
            i = rng.randint(len(pts) // 5, len(pts) * 4 // 5)
            a = pts[i]
            main_dir = (pts[-1] - pts[0]).normalized()
            d = (main_dir + Vector((rng.gauss(0, 0.7), rng.gauss(0, 0.7), rng.gauss(0, 0.7)))).normalized()
            b = a + d * (pts[-1] - pts[0]).length * rng.uniform(0.25, 0.5)
            branches.append((jagged(a, b, rng, 4, 0.4), radius * 0.45))

    core = bpy.data.materials.new("Bolt Core")
    gc = Graph(core)
    em = gc.node("ShaderNodeEmission", inputs={"Color": (0.55, 0.76, 1.0, 1.0), "Strength": 60.0})
    gc.output(em)
    branch_mat = bpy.data.materials.new("Bolt Branch")
    gb = Graph(branch_mat)
    emb = gb.node("ShaderNodeEmission", inputs={"Color": (0.25, 0.52, 1.0, 1.0), "Strength": 40.0})
    gb.output(emb)

    objs, flashes = [], []
    for k, (pts, radius) in enumerate(paths + branches):
        cu = bpy.data.curves.new(f"Bolt{k}", type="CURVE")
        cu.dimensions = "3D"
        cu.bevel_depth = radius
        cu.bevel_resolution = 1
        sp = cu.splines.new("POLY")
        sp.points.add(len(pts) - 1)
        for i, q in enumerate(pts):
            taper = 1.0 - 0.7 * (i / (len(pts) - 1))
            sp.points[i].co = (q.x, q.y, q.z, 1.0)
            sp.points[i].radius = taper
        cu.materials.append(core if k < len(paths) else branch_mat)
        ob = bpy.data.objects.new(f"Bolt{k}", cu)
        col.objects.link(ob)
        ob.visible_shadow = False
        objs.append(ob)
        if k < len(paths):
            flashes.append(pts[len(pts) // 2])
    return objs, flashes


def add_glare(scene):
    """Bloom in the compositor so the bolts and veins glow like real light."""
    scene.use_nodes = True
    nt = scene.node_tree
    nt.nodes.clear()
    rl = nt.nodes.new("CompositorNodeRLayers")
    glare = nt.nodes.new("CompositorNodeGlare")
    for kind in ("BLOOM", "FOG_GLOW"):
        try:
            glare.glare_type = kind
            break
        except TypeError:
            continue
    for attr, val in (("quality", "HIGH"), ("threshold", 0.9), ("size", 8), ("mix", 0.0)):
        try:
            setattr(glare, attr, val)
        except (AttributeError, TypeError):
            sock = glare.inputs.get(attr.capitalize())
            if sock is not None and not isinstance(val, str):
                sock.default_value = val
    comp = nt.nodes.new("CompositorNodeComposite")
    nt.links.new(rl.outputs["Image"], glare.inputs["Image"])
    nt.links.new(glare.outputs["Image"], comp.inputs["Image"])


# ---------------------------------------------------------------------------
# Scene
# ---------------------------------------------------------------------------
def build_scene(scheme="crimson"):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    col = bpy.data.collections.new("Katana")
    scene.collection.children.link(col)

    gold, iron, shakudo = mat_gold(), mat_iron(), mat_shakudo()
    parts = {
        "Blade": (build_blade(col), mat_blade(scheme)),
        "Habaki": (build_habaki(col), gold),
        "Seppa": (build_seppa(col), gold),
        "Tsuba": (build_tsuba(col), iron),
        "Tsuka": (build_tsuka(col), mat_tsuka()),
        "Fittings": (build_fittings(col), shakudo),
        "Menuki": (build_menuki(col), gold),
    }
    root = bpy.data.objects.new("Katana", None)
    col.objects.link(root)
    for ob, mat in parts.values():
        ob.data.materials.append(mat)
        ob.parent = root

    # aura domain: a box around the blade in katana space
    abm = bmesh.new()
    bmesh.ops.create_cube(abm, size=1.0)
    for v in abm.verts:
        v.co = Vector((
            0.02 + v.co.x * 0.30,
            v.co.y * 0.24,
            0.39 + v.co.z * 0.92,
        ))
    ame = bpy.data.meshes.new("Aura")
    abm.to_mesh(ame)
    abm.free()
    aura = bpy.data.objects.new("Aura", ame)
    col.objects.link(aura)
    aura.parent = root
    ame.materials.append(mat_aura(scheme))

    flashes = []
    if AURA[scheme].get("lightning"):
        bolts, flashes = build_bolts(col, random.Random(7))
        for ob in bolts:
            ob.parent = root

    # float the katana diagonally, point up and to the right, edge up-left
    root.matrix_world = Matrix.Translation((0.0, 0.0, 0.42)) @ Matrix.Rotation(math.radians(58), 4, "Y")

    # floor
    fbm = bmesh.new()
    bmesh.ops.create_grid(fbm, x_segments=1, y_segments=1, size=4.0)
    fme = bpy.data.meshes.new("Floor")
    fbm.to_mesh(fme)
    fbm.free()
    floor = bpy.data.objects.new("Floor", fme)
    scene.collection.objects.link(floor)
    fme.materials.append(mat_floor())

    # world: near black
    world = bpy.data.worlds.new("Void")
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.0015, 0.0013, 0.0016, 1)
    bpy.context.view_layer.update()

    M = root.matrix_world
    tip_w = M @ spine(NAGASA)[0]
    butt_w = M @ Vector((TSUKA_X, 0.0, KASHIRA_Z1))
    center = (tip_w + butt_w) / 2
    guard = M @ Vector((TSUKA_X, 0.0, -0.004))
    blade_mid = M @ Vector((0.02, 0.0, 0.35))
    blade_dir = (M.to_3x3() @ Vector((0, 0, 1))).normalized()
    flat_n = (M.to_3x3() @ Vector((0, -1, 0))).normalized()    # flat facing the camera

    def make_cam(name, loc, target, lens, fstop, focus):
        cd = bpy.data.cameras.new(name)
        cd.lens = lens
        cd.sensor_width = 36
        cd.dof.use_dof = True
        cd.dof.aperture_fstop = fstop
        cd.dof.aperture_blades = 9
        cam = bpy.data.objects.new(name, cd)
        scene.collection.objects.link(cam)
        cam.location = loc
        cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        cd.dof.focus_distance = (Vector(focus) - Vector(loc)).length
        return cam

    # the lightning reaches further out, so pull back a little to keep it in frame
    hero_loc = center + (Vector((0.06, -1.62, 0.12)) if AURA[scheme].get("lightning") else Vector((0.06, -1.42, 0.14)))
    hero = make_cam("Cam_Hero", hero_loc, center + Vector((0, 0, -0.03)), 45, 4.0, blade_mid)
    close_target = M @ Vector((0.0, 0.0, 0.07))
    close_loc = close_target + Vector((0.16, -0.40, 0.05))
    closeup = make_cam("Cam_Closeup", close_loc, close_target, 70, 3.5, M @ Vector((-0.012, 0.0, 0.05)))
    scene.camera = hero

    # lighting
    d = (blade_mid - hero_loc).normalized()
    refl = (d - 2 * d.dot(flat_n) * flat_n).normalized()
    add_panel("Softbox_Blade", blade_mid + refl * 1.4, -refl, blade_dir, 2.2, 0.35,
              mat_softbox(0.9, color=(0.9, 0.93, 1.0)))
    dc = (close_target - close_loc).normalized()
    reflc = (dc - 2 * dc.dot(flat_n) * flat_n).normalized()
    add_panel("Softbox_Close", close_target + reflc * 0.8, -reflc, blade_dir, 0.9, 0.3,
              mat_softbox(0.5, color=(0.9, 0.93, 1.0)))
    add_area("Key", center + Vector((-1.1, -1.0, 1.1)), center, 0.8, 30, (1.0, 0.93, 0.86), size_y=0.5)
    add_area("Rim", center + Vector((1.0, 1.3, 0.7)), center, 1.4, 45, (0.70, 0.80, 1.0), size_y=0.2)
    add_area("Aura_Glow", blade_mid + Vector((0.0, 0.25, -0.05)), blade_mid, 0.5, 3.5, AURA[scheme]["light"],
             size_y=0.9)
    add_area("Floor_Glow", blade_mid + Vector((0.0, 0.0, -0.1)), blade_mid - Vector((0, 0, 1)), 0.5, 4,
             AURA[scheme]["light"], size_y=0.9)

    # faint glowing backdrop far behind, so the black smoke reads in silhouette
    bd = bpy.data.materials.new("Backdrop Glow")
    g = Graph(bd)
    uvb = g.texcoord("UV")
    ub, vb, _ = g.separate(uvb)
    r = g.vmath("LENGTH", g.combine(g.math("MULTIPLY", g.math("SUBTRACT", ub, 0.5), 1.6),
                                    g.math("SUBTRACT", vb, 0.45), 0.0))
    glow = g.math("POWER", g.maprange(r, 0.0, 0.55, 1.0, 0.0), 2.2)
    em = g.node("ShaderNodeEmission", inputs={"Color": (*AURA[scheme]["light"], 1.0)})
    g.set(em.inputs["Strength"], g.math("MULTIPLY", glow, 0.07))
    g.output(em)
    back = add_panel("Backdrop", center + Vector((0.0, 1.9, 0.05)), Vector((0, -1, 0)), Vector((0, 0, 1)),
                     2.4, 4.0, bd)
    back.visible_camera = True
    back.visible_glossy = False

    # the bolts light up their surroundings
    for i, f in enumerate(flashes[:6]):
        data = bpy.data.lights.new(f"Flash{i}", "POINT")
        data.energy = 2.5
        data.color = (0.55, 0.75, 1.0)
        data.shadow_soft_size = 0.01
        fl = bpy.data.objects.new(f"Flash{i}", data)
        scene.collection.objects.link(fl)
        fl.location = M @ f
    if AURA[scheme].get("lightning"):
        add_glare(scene)

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
    cy.preview_samples = 32
    cy.use_preview_denoising = True
    cy.max_bounces = 10
    cy.glossy_bounces = 6
    cy.diffuse_bounces = 3
    cy.volume_bounces = 1
    cy.volume_step_rate = 1.0
    cy.volume_max_steps = 256
    cy.caustics_reflective = False
    cy.caustics_refractive = False
    cy.blur_glossy = 0.5
    scene.render.resolution_x, scene.render.resolution_y = 1920, 1080
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_depth = "16"
    scene.view_settings.view_transform = "AgX"
    try:
        scene.view_settings.look = "AgX - Punchy"
    except TypeError:
        pass
    scene.frame_start, scene.frame_end = 1, 72
    scene.render.fps = 24
    scene.frame_set(18)
    return scene, {"hero": hero, "closeup": closeup}


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else argv[1:]
    p = argparse.ArgumentParser()
    p.add_argument("--aura", choices=sorted(AURA), default="crimson")
    p.add_argument("--render", action="store_true")
    p.add_argument("--animate", action="store_true")
    p.add_argument("--samples", type=int, default=256)
    p.add_argument("--res", type=int, nargs=2, default=(1920, 1080))
    p.add_argument("--out", default=os.path.join(HERE, "renders"))
    p.add_argument("--blend", default=None)
    p.add_argument("--shots", default="hero,closeup")
    p.add_argument("--gpu", action="store_true")
    return p.parse_args(argv)


def main():
    args = parse_args()
    scene, cams = build_scene(args.aura)
    scene.cycles.samples = args.samples
    scene.render.resolution_x, scene.render.resolution_y = args.res
    if args.gpu:
        configure_gpu(scene)
    blend = args.blend or os.path.join(HERE, f"katana_{args.aura}.blend")
    if blend:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(blend), compress=True)
        print("Saved", blend)
    out = os.path.abspath(args.out)
    if args.render:
        os.makedirs(out, exist_ok=True)
        for shot in [s.strip() for s in args.shots.split(",") if s.strip()]:
            scene.camera = cams[shot]
            scene.render.filepath = os.path.join(out, f"katana_{args.aura}_{shot}.png")
            bpy.ops.render.render(write_still=True)
            print("Rendered", scene.render.filepath)
    if args.animate:
        scene.camera = cams["hero"]
        scene.render.filepath = os.path.join(out, f"frames_{args.aura}", "f_")
        bpy.ops.render.render(animation=True)
        print("Rendered animation frames to", os.path.dirname(scene.render.filepath))
    scene.camera = cams["hero"]


if __name__ == "__main__":
    main()
