"""
Blood & Steel -- asset build script.

Builds every 3D asset used by sword.html with Blender, entirely from code:
procedural PBR textures, the armoured knight (rigid plate pieces parented to an
armature), the longsword, the arena, gore pieces (stumps, gibs) and all the
animation clips. Everything is exported as .glb into assets/sword/.

Run with either
    blender --background --python tools/blender/build_sword_assets.py
or, with the `bpy` wheel installed (pip install bpy),
    python3 tools/blender/build_sword_assets.py

Conventions (Blender space): character stands at the origin facing -Y, its left
side is +X, Z is up. The glTF exporter converts this to three.js space where
the character faces +Z, left is +X and Y is up.
"""

import bpy
import bmesh
import json
import math
import os
import random
import shutil
import tempfile

import numpy as np
from mathutils import Matrix, Quaternion, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(REPO, "assets", "sword")
TEX_DIR = tempfile.mkdtemp(prefix="bs_tex_")
FPS = 30

random.seed(7)
os.makedirs(OUT, exist_ok=True)


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.render.fps = FPS


# ---------------------------------------------------------------------------
# Procedural, tileable textures (numpy)
# ---------------------------------------------------------------------------

def _smooth_upsample(grid, size):
    """Periodic smoothstep interpolation of a small random grid to size x size."""
    n = grid.shape[0]
    c = np.arange(size) * n / size
    i0 = np.floor(c).astype(int) % n
    i1 = (i0 + 1) % n
    f = c - np.floor(c)
    f = f * f * (3 - 2 * f)
    rows = grid[i0][:, :] * (1 - f)[:, None] + grid[i1][:, :] * f[:, None]
    return rows[:, i0] * (1 - f)[None, :] + rows[:, i1] * f[None, :]


def noise(size, cells, seed, octaves=5, persistence=0.5):
    rng = np.random.default_rng(seed)
    out = np.zeros((size, size))
    amp, total, freq = 1.0, 0.0, cells
    for _ in range(octaves):
        freq = min(freq, size)
        out += amp * _smooth_upsample(rng.random((freq, freq)), size)
        total += amp
        amp *= persistence
        freq *= 2
    out /= total
    return (out - out.min()) / (out.max() - out.min() + 1e-9)


def stretched_noise(size, cx, cy, seed, octaves=4):
    """Anisotropic value noise (cx cells across, cy cells down) -- wood grain, fibres."""
    rng = np.random.default_rng(seed)
    out = np.zeros((size, size))
    amp, total = 1.0, 0.0
    for o in range(octaves):
        gx, gy = min(cx * 2 ** o, size), min(cy * 2 ** o, size)
        g = rng.random((gy, gx))
        ry = _interp_axis(g, size, axis=0)
        out += amp * _interp_axis(ry, size, axis=1)
        total += amp
        amp *= 0.5
    out /= total
    return (out - out.min()) / (out.max() - out.min() + 1e-9)


def _interp_axis(g, size, axis):
    n = g.shape[axis]
    c = np.arange(size) * n / size
    i0 = np.floor(c).astype(int) % n
    i1 = (i0 + 1) % n
    f = c - np.floor(c)
    f = f * f * (3 - 2 * f)
    a = np.take(g, i0, axis=axis)
    b = np.take(g, i1, axis=axis)
    shape = [1, 1]
    shape[axis] = size
    f = f.reshape(shape)
    return a * (1 - f) + b * f


def scratches(size, count, seed, length=(0.02, 0.15), strength=1.0):
    rng = np.random.default_rng(seed)
    img = np.zeros((size, size))
    for _ in range(count):
        x, y = rng.random(2) * size
        ang = rng.random() * math.pi
        ln = rng.uniform(*length) * size
        steps = int(ln * 1.5) + 2
        t = np.linspace(0, 1, steps)
        xs = (x + math.cos(ang) * ln * t).astype(int) % size
        ys = (y + math.sin(ang) * ln * t).astype(int) % size
        np.add.at(img, (ys, xs), strength * rng.uniform(0.4, 1.0))
    return np.clip(img, 0, 1)


def blobs(size, count, seed, rmin, rmax):
    """Wrap-around soft round bumps (pebbles, rivet-ish dents)."""
    rng = np.random.default_rng(seed)
    img = np.zeros((size, size))
    for _ in range(count):
        cx, cy = rng.random(2) * size
        r = rng.uniform(rmin, rmax)
        rr = int(r) + 2
        xs = np.arange(int(cx) - rr, int(cx) + rr + 1)
        ys = np.arange(int(cy) - rr, int(cy) + rr + 1)
        dx = (xs - cx)[None, :]
        dy = (ys - cy)[:, None]
        d = np.sqrt(dx * dx + dy * dy) / r
        bump = np.clip(1 - d * d, 0, 1) ** 0.7
        yi = ys[:, None] % size
        xi = xs[None, :] % size
        img[yi, xi] = np.maximum(img[yi, xi], bump * rng.uniform(0.5, 1.0))
    return img


def normal_from_height(h, strength):
    dx = (np.roll(h, -1, axis=1) - np.roll(h, 1, axis=1)) * 0.5
    dy = (np.roll(h, -1, axis=0) - np.roll(h, 1, axis=0)) * 0.5
    nx, ny = -dx * strength, -dy * strength
    nz = np.ones_like(h)
    ln = np.sqrt(nx * nx + ny * ny + nz * nz)
    return np.stack([nx / ln * 0.5 + 0.5, ny / ln * 0.5 + 0.5, nz / ln * 0.5 + 0.5], axis=2)


def save_image(name, rgb, noncolor=False, quality=90):
    h, w = rgb.shape[:2]
    img = bpy.data.images.new(name, w, h, alpha=False)
    rgba = np.concatenate([np.clip(rgb, 0, 1), np.ones((h, w, 1))], axis=2).astype(np.float32)
    img.pixels.foreach_set(rgba.ravel())
    path = os.path.join(TEX_DIR, name + ".jpg")
    img.filepath_raw = path
    img.file_format = "JPEG"
    bpy.context.scene.render.image_settings.quality = quality
    img.save()
    img = bpy.data.images.load(path, check_existing=False)
    img.name = name
    if noncolor:
        img.colorspace_settings.name = "Non-Color"
    return img


def orm(rough, metal):
    return np.stack([np.ones_like(rough), rough, metal * np.ones_like(rough)], axis=2)


def tex_steel(size=512, seed=1, rough_base=0.32):
    grime = noise(size, 4, seed, 6)
    fine = noise(size, 32, seed + 1, 3)
    scr = scratches(size, 900, seed + 2, (0.01, 0.12))
    dents = noise(size, 6, seed + 3, 3)
    base = 0.60 + 0.08 * fine - 0.22 * grime ** 2 + 0.18 * scr
    alb = np.stack([base * 0.98, base, base * 1.03], axis=2)
    rough = np.clip(rough_base + 0.35 * grime ** 1.5 + 0.08 * fine - 0.12 * scr, 0.05, 1)
    height = dents * 1.0 + 0.15 * fine - 0.25 * scr
    return alb, orm(rough, 1.0), normal_from_height(height, 6.0)


def tex_leather(size=512, seed=10):
    n = noise(size, 8, seed, 6)
    pores = noise(size, 128, seed + 1, 2)
    crease = stretched_noise(size, 3, 24, seed + 2)
    base = 0.55 + 0.35 * n - 0.15 * crease
    alb = np.stack([0.32 * base, 0.18 * base, 0.09 * base], axis=2)
    rough = 0.55 + 0.25 * n
    return alb, orm(rough, 0.0), normal_from_height(pores * 0.6 + crease * 0.8, 4.0)


def tex_cloth(size=512, seed=20, tint=(1.0, 0.97, 0.92)):
    u = np.arange(size)[None, :] / size
    v = np.arange(size)[:, None] / size
    f = 96
    warp = (np.sin(u * f * 2 * math.pi) * 0.5 + 0.5) * (np.sin(v * f * math.pi * 2 + math.pi / 2) > 0)
    weft = (np.sin(v * f * 2 * math.pi) * 0.5 + 0.5) * (np.sin(u * f * math.pi * 2 + math.pi / 2) <= 0)
    weave = warp + weft
    dirt = noise(size, 5, seed, 6)
    base = 0.78 + 0.1 * weave - 0.3 * dirt ** 2
    alb = np.stack([base * tint[0], base * tint[1], base * tint[2]], axis=2)
    rough = 0.85 + 0.1 * dirt
    return alb, orm(rough, 0.0), normal_from_height(weave * 0.6 + dirt * 0.4, 3.0)


def tex_chain(size=512, seed=30):
    n = 24  # rings per row
    u = np.arange(size)[None, :] / size * n
    v = np.arange(size)[:, None] / size * n
    h = np.zeros((size, size))
    for off in (0.0, 0.5):
        cu = (u + off) % 1.0 - 0.5
        cv = (v + off * 2) % 2.0
        cv = np.where(cv > 1, cv - 2, cv)
        for sh in (0.0,):
            d = np.sqrt(cu ** 2 + ((v + off) % 1.0 - 0.5) ** 2)
            ring = np.clip(1 - np.abs(d - 0.36) / 0.12, 0, 1)
            h = np.maximum(h, ring)
    grime = noise(size, 6, seed, 5)
    base = 0.12 + 0.45 * h - 0.1 * grime
    alb = np.stack([base, base, base * 1.04], axis=2)
    rough = 0.35 + 0.4 * (1 - h) + 0.2 * grime
    return alb, orm(rough, 1.0), normal_from_height(h, 8.0)


def tex_sand(size=1024, seed=40):
    big = noise(size, 4, seed, 6)
    mid = noise(size, 24, seed + 1, 4)
    grain = noise(size, 256, seed + 2, 2)
    peb = blobs(size, 2600, seed + 3, 1.5, 5.0)
    tracks = stretched_noise(size, 2, 18, seed + 4)
    col = np.stack([0.58 + 0.0 * big, 0.47 + 0.0 * big, 0.33 + 0.0 * big], axis=2)
    col *= (0.78 + 0.28 * big[..., None] + 0.12 * mid[..., None] + 0.08 * grain[..., None])
    pc = np.stack([0.42 * np.ones_like(peb), 0.40 * np.ones_like(peb), 0.37 * np.ones_like(peb)], axis=2)
    col = col * (1 - peb[..., None] * 0.8) + pc * peb[..., None] * 0.8
    col *= (0.92 + 0.08 * tracks[..., None])
    rough = 0.9 + 0.08 * grain - 0.1 * peb
    height = 0.5 * big + 0.4 * mid + 0.3 * grain + 0.9 * peb
    return col, orm(rough, 0.0), normal_from_height(height, 7.0)


def tex_stone(size=1024, seed=50, rows=8):
    rng = np.random.default_rng(seed)
    h = np.zeros((size, size))
    shade = np.zeros((size, size))
    rh = size // rows
    x = np.arange(size)
    for r in range(rows):
        widths = []
        while sum(widths) < 1.0:
            widths.append(rng.uniform(0.18, 0.34))
        widths = np.array(widths)
        widths *= 1.0 / widths.sum()
        edges = np.concatenate([[0], np.cumsum(widths)]) * size
        offset = rng.random() * size
        xs = (x + offset) % size
        idx = np.searchsorted(edges, xs, side="right") - 1
        left = xs - edges[idx]
        right = edges[idx + 1] - xs
        dx = np.minimum(left, right)
        yy = np.arange(rh)
        dy = np.minimum(yy, rh - 1 - yy)
        d = np.minimum(dx[None, :], dy[:, None])
        bevel = np.clip(d / 9.0, 0, 1) ** 0.6
        h[r * rh:(r + 1) * rh] = bevel
        tints = rng.uniform(0.75, 1.1, size=len(widths))
        shade[r * rh:(r + 1) * rh] = tints[idx][None, :]
    n1 = noise(size, 16, seed + 1, 6)
    n2 = noise(size, 64, seed + 2, 3)
    moss = noise(size, 5, seed + 3, 5)
    stone = (0.42 + 0.18 * n1 + 0.08 * n2) * shade
    mortar = 0.22 + 0.05 * n2
    m = (h > 0.02).astype(float)
    base = stone * m + mortar * (1 - m)
    col = np.stack([base * 1.02, base * 0.97, base * 0.9], axis=2)
    col *= (1 - 0.25 * np.clip(moss - 0.6, 0, 1)[..., None] * np.array([1.0, 0.6, 1.0]))
    rough = 0.8 + 0.15 * n2
    height = h * 0.9 + n1 * 0.35 + n2 * 0.15
    return col, orm(rough, 0.0), normal_from_height(height, 9.0)


def tex_wood(size=512, seed=60):
    grain = stretched_noise(size, 24, 2, seed, 5)
    rings = np.sin(grain * 40.0) * 0.5 + 0.5
    planks = 4
    u = np.arange(size) / size * planks
    gap = (np.abs((u % 1.0) - 0.0) < 0.012) | (np.abs((u % 1.0) - 1.0) < 0.012)
    base = 0.45 + 0.25 * rings * 0.5 + 0.2 * grain
    col = np.stack([0.42 * base, 0.27 * base, 0.15 * base], axis=2)
    col[:, gap] *= 0.35
    rough = 0.7 + 0.2 * grain
    height = rings * 0.4 + grain * 0.5
    height[:, gap] = 0
    return col, orm(rough, 0.0), normal_from_height(height, 5.0)


def tex_flesh(size=256, seed=70):
    fib = stretched_noise(size, 40, 4, seed, 4)
    n = noise(size, 8, seed + 1, 5)
    fat = np.clip(noise(size, 12, seed + 2, 4) - 0.62, 0, 1) * 3
    base = 0.45 + 0.35 * fib * 0.6 + 0.2 * n
    col = np.stack([0.55 * base, 0.06 * base, 0.05 * base], axis=2)
    fatc = np.array([0.85, 0.72, 0.55])
    col = col * (1 - fat[..., None]) + fatc * fat[..., None]
    rough = 0.25 + 0.2 * n
    return col, orm(rough, 0.0), normal_from_height(fib * 0.7 + n * 0.5, 5.0)


# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------

def material(name, tex=None, color=(0.8, 0.8, 0.8), rough=0.5, metal=0.0, nstr=1.0, emissive=None):
    m = bpy.data.materials.new(name)
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    if tex:
        alb, ormimg, nrm = tex
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = alb
        nt.links.new(t.outputs["Color"], bsdf.inputs["Base Color"])
        t2 = nt.nodes.new("ShaderNodeTexImage")
        t2.image = ormimg
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(t2.outputs["Color"], sep.inputs["Color"])
        nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
        nt.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])
        t3 = nt.nodes.new("ShaderNodeTexImage")
        t3.image = nrm
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.inputs["Strength"].default_value = nstr
        nt.links.new(t3.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    else:
        bsdf.inputs["Base Color"].default_value = (*color, 1)
        bsdf.inputs["Roughness"].default_value = rough
        bsdf.inputs["Metallic"].default_value = metal
    if emissive:
        bsdf.inputs["Emission Color"].default_value = (*emissive, 1)
        bsdf.inputs["Emission Strength"].default_value = 1.0
    return m


def texset(prefix, gen):
    alb, o, n = gen
    return (save_image(prefix + "_albedo", alb),
            save_image(prefix + "_orm", o, noncolor=True),
            save_image(prefix + "_normal", n, noncolor=True))


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def bm_lathe(profile, seg=24, cap_bottom=True, cap_top=True, sx=1.0, sy=1.0, arc=None, phase=0.0):
    """Revolve (r, z) profile points around Z. arc=(a0, a1) builds an open partial shell."""
    bm = bmesh.new()
    rings = []
    full = arc is None
    n = seg if full else seg + 1
    for r, z in profile:
        ring = []
        if r < 1e-6:
            ring = [bm.verts.new((0, 0, z))] * n
        else:
            for i in range(n):
                if full:
                    a = 2 * math.pi * i / seg + phase
                else:
                    a = arc[0] + (arc[1] - arc[0]) * i / seg
                ring.append(bm.verts.new((r * math.cos(a) * sx, r * math.sin(a) * sy, z)))
        rings.append(ring)
    for k in range(len(rings) - 1):
        for i in range(seg):
            j = (i + 1) % n
            quad = [rings[k][i], rings[k][j], rings[k + 1][j], rings[k + 1][i]]
            uniq = []
            for v in quad:
                if v not in uniq:
                    uniq.append(v)
            if len(uniq) >= 3:
                try:
                    bm.faces.new(uniq)
                except ValueError:
                    pass
    if full:
        if cap_bottom and profile[0][0] > 1e-6:
            bm.faces.new(list(reversed(rings[0])))
        if cap_top and profile[-1][0] > 1e-6:
            bm.faces.new(rings[-1])
    bm.normal_update()
    return bm


def bm_box(sx, sy, sz, center=(0, 0, 0), bevel=0.0, segs=2):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * sx + center[0], v.co.y * sy + center[1], v.co.z * sz + center[2]))
    if bevel > 0:
        bmesh.ops.bevel(bm, geom=list(bm.edges), offset=bevel, segments=segs, affect="EDGES",
                        profile=0.5, clamp_overlap=True)
    bm.normal_update()
    return bm


def bm_ico(radius, subdiv=2, center=(0, 0, 0)):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=subdiv, radius=radius)
    bmesh.ops.translate(bm, verts=bm.verts, vec=Vector(center))
    return bm


def deform(bm, fn):
    for v in bm.verts:
        v.co = Vector(fn(v.co.copy()))
    bm.normal_update()
    return bm


def xform(bm, mat):
    bmesh.ops.transform(bm, matrix=mat, verts=bm.verts)
    bm.normal_update()
    return bm


def align_between(bm, a, b, twist=0.0):
    """Map geometry built along +Z (z in [0,1]) onto the segment a->b."""
    a, b = Vector(a), Vector(b)
    d = b - a
    ln = d.length
    rot = Vector((0, 0, 1)).rotation_difference(d.normalized()).to_matrix().to_4x4()
    m = Matrix.Translation(a) @ rot @ Matrix.Rotation(twist, 4, "Z") @ Matrix.Diagonal((1, 1, ln, 1))
    return xform(bm, m)


def _temp_object(bm, name="tmp"):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _eval_to_bm(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev)
    bm = bmesh.new()
    bm.from_mesh(me)
    bpy.data.meshes.remove(me)
    return bm


def _remove(ob):
    me = ob.data
    bpy.data.objects.remove(ob)
    if me and me.users == 0:
        bpy.data.meshes.remove(me)


def subsurf(bm, levels=2):
    ob = _temp_object(bm)
    md = ob.modifiers.new("s", "SUBSURF")
    md.levels = levels
    out = _eval_to_bm(ob)
    _remove(ob)
    return out


def solidify(bm, thickness, offset=-1.0):
    ob = _temp_object(bm)
    md = ob.modifiers.new("s", "SOLIDIFY")
    md.thickness = thickness
    md.offset = offset
    md.use_even_offset = True
    out = _eval_to_bm(ob)
    _remove(ob)
    return out


def boolean(bm, cutters, op="DIFFERENCE"):
    ob = _temp_object(bm)
    cut_obs = []
    for c in cutters:
        co = _temp_object(c, "cut")
        cut_obs.append(co)
        md = ob.modifiers.new("b", "BOOLEAN")
        md.operation = op
        md.object = co
        md.solver = "EXACT"
    out = _eval_to_bm(ob)
    _remove(ob)
    for co in cut_obs:
        _remove(co)
    return out


def box_uv(bm, scale=1.0, mode="box", uvlayer=None):
    uv = bm.loops.layers.uv.verify()
    for f in bm.faces:
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for loop in f.loops:
            c = loop.vert.co
            if mode == "cyl":
                ang = math.atan2(c.y, c.x)
                r = math.hypot(c.x, c.y)
                if ax == 2:
                    loop[uv].uv = (c.x * scale, c.y * scale)
                else:
                    loop[uv].uv = (ang * r * scale, c.z * scale)
            elif mode == "planar":
                loop[uv].uv = (c.x * scale, c.y * scale)
            else:
                if ax == 0:
                    loop[uv].uv = (c.y * scale, c.z * scale)
                elif ax == 1:
                    loop[uv].uv = (c.x * scale, c.z * scale)
                else:
                    loop[uv].uv = (c.x * scale, c.y * scale)
    return bm


class Part:
    """Accumulates several pieces (each with its own material) into one mesh object."""

    def __init__(self, name):
        self.name = name
        self.bm = bmesh.new()
        self.mats = []

    def add(self, bm, mat, uv=2.0, uvmode="box", sharp=32.0, smooth=True):
        box_uv(bm, uv, uvmode)
        if mat not in self.mats:
            self.mats.append(mat)
        mi = self.mats.index(mat)
        for f in bm.faces:
            f.material_index = mi
            f.smooth = smooth
        thr = math.radians(sharp)
        for e in bm.edges:
            if e.is_manifold and e.calc_face_angle(0) > thr:
                e.smooth = False
        me = bpy.data.meshes.new("piece")
        bm.to_mesh(me)
        self.bm.from_mesh(me)
        bpy.data.meshes.remove(me)
        bm.free()

    def build(self, origin=(0, 0, 0)):
        bmesh.ops.translate(self.bm, verts=self.bm.verts, vec=-Vector(origin))
        me = bpy.data.meshes.new(self.name)
        self.bm.to_mesh(me)
        for m in self.mats:
            me.materials.append(m)
        ob = bpy.data.objects.new(self.name, me)
        ob.location = origin
        bpy.context.scene.collection.objects.link(ob)
        return ob


# ---------------------------------------------------------------------------
# Knight
# ---------------------------------------------------------------------------

J = {  # joint positions (Blender space), right side mirrors X
    "pelvis": (0, 0, 0.98), "spine": (0, 0, 1.06), "spine_tail": (0, 0, 1.50),
    "neck": (0, 0, 1.52), "head_top": (0, 0, 1.84),
    "shoulder": (0.19, 0.0, 1.44), "elbow": (0.22, 0.01, 1.14), "wrist": (0.24, 0.0, 0.87),
    "fist": (0.24, 0.0, 0.795),
    "hip": (0.10, 0.0, 0.93), "knee": (0.105, -0.01, 0.51), "ankle": (0.11, 0.01, 0.09),
    "toe": (0.11, -0.17, 0.02),
}


def mirror(p, side):
    return (p[0] * side, p[1], p[2])


def limb_tube(a, b, r0, r1, t0=0.0, t1=1.0, seg=16, rings=6, bulge=0.0, sy=1.0, flare=0.0):
    prof = []
    for k in range(rings + 1):
        t = k / rings
        r = r0 + (r1 - r0) * t + bulge * math.sin(t * math.pi)
        if flare and k == 0:
            r += flare
        prof.append((r, t0 + (t1 - t0) * t))
    bm = bm_lathe(prof, seg, sy=sy)
    return align_between(bm, a, b)


def build_knight(M):
    parts = {}

    def P(name):
        if name not in parts:
            parts[name] = Part(name + "_geo")
        return parts[name]

    # ---------------- head / helmets (three variants, toggled at runtime) --------------
    def helm_deform(c):
        x, y, z = c
        y *= 1.1
        if y < 0:
            y *= 0.92
        return (x, y, z)

    # Great helm
    gh = bm_lathe([(0.118, 1.545), (0.126, 1.58), (0.129, 1.66), (0.128, 1.74), (0.118, 1.79),
                   (0.095, 1.822), (0.055, 1.842), (0.0, 1.848)], 28, cap_bottom=False)
    deform(gh, helm_deform)
    gh = solidify(gh, 0.006)
    slits = [bm_box(0.085, 0.12, 0.016, (-0.057, -0.12, 1.715)), bm_box(0.085, 0.12, 0.016, (0.057, -0.12, 1.715))]
    for i in range(5):
        for j in range(2):
            slits.append(bm_box(0.012, 0.12, 0.012, (-0.03 - 0.022 * i, -0.12, 1.62 - 0.03 * j)))
    gh = boolean(gh, slits)
    P("helm_great").add(gh, M["steel"], uv=4)
    cross = bm_box(0.024, 0.01, 0.25, (0, -0.128, 1.69), 0.003)
    deform(cross, lambda c: (c[0], c[1] - 0.004 * math.sin((c[2] - 1.56) / 0.27 * math.pi), c[2]))
    P("helm_great").add(cross, M["brass"])
    band = bm_lathe([(0.1305, 1.742), (0.1325, 1.745), (0.1325, 1.758), (0.1305, 1.761)], 28, False, False)
    deform(band, helm_deform)
    band = boolean(band, [bm_box(0.2, 0.1, 0.03, (0, -0.13, 1.75))])
    P("helm_great").add(band, M["brass"])
    P("helm_great").add(deform(bm_ico(0.1, 2, (0, 0, 1.69)), lambda c: (c[0], c[1] * 1.05, c[2] * 1.0)), M["void"])

    # Hounskull bascinet
    bs = bm_lathe([(0.119, 1.56), (0.126, 1.62), (0.127, 1.70), (0.116, 1.78), (0.085, 1.84),
                   (0.035, 1.878), (0.0, 1.89)], 28, cap_bottom=False)
    deform(bs, lambda c: (c[0], c[1] * 1.08 + (0.03 if c[1] > 0 else 0) * (c[2] - 1.56) / 0.33, c[2]))
    bs = solidify(bs, 0.005)
    P("helm_bascinet").add(bs, M["steel"], uv=4)
    snout = bm_lathe([(0.118, 0.0), (0.112, 0.045), (0.088, 0.095), (0.05, 0.14), (0.012, 0.172), (0.0, 0.176)],
                     24, cap_bottom=False)
    deform(snout, lambda c: (c[0], c[1] * 1.12, c[2]))
    snout = solidify(snout, 0.005)
    xform(snout, Matrix.Translation((0, -0.035, 1.685)) @ Matrix.Rotation(math.pi / 2, 4, "X"))
    vcut = [bm_box(0.075, 0.2, 0.013, (-0.055, -0.1, 1.715)), bm_box(0.075, 0.2, 0.013, (0.055, -0.1, 1.715))]
    for i in range(6):
        vcut.append(bm_box(0.2, 0.012, 0.008, (0, -0.13 - 0.012 * i, 1.64 + 0.001 * i)))
    snout = boolean(snout, vcut)
    P("helm_bascinet").add(snout, M["steel"], uv=4)
    for sgn in (-1, 1):
        P("helm_bascinet").add(bm_lathe([(0.012, 0), (0.012, 0.012), (0.0, 0.014)], 10), M["brass"])
        piv = bm_lathe([(0.013, 0.0), (0.013, 0.01), (0.0, 0.013)], 10)
        xform(piv, Matrix.Translation((0.123 * sgn, -0.02, 1.705)) @ Matrix.Rotation(sgn * math.pi / 2, 4, "Y"))
        P("helm_bascinet").add(piv, M["brass"])
    P("helm_bascinet").add(bm_ico(0.1, 2, (0, 0, 1.70)), M["void"])
    avent = bm_lathe([(0.118, 1.60), (0.125, 1.55), (0.155, 1.50), (0.2, 1.455)], 24, False, False)
    avent = solidify(avent, 0.01)
    P("helm_bascinet").add(avent, M["chain"], uv=10)

    # Barbute
    bb = bm_lathe([(0.113, 1.545), (0.123, 1.60), (0.128, 1.68), (0.122, 1.76), (0.098, 1.815),
                   (0.055, 1.842), (0.0, 1.85)], 28, cap_bottom=False)
    deform(bb, helm_deform)
    bb = solidify(bb, 0.006)
    tcut = [bm_box(0.13, 0.15, 0.03, (0, -0.12, 1.705)), bm_box(0.05, 0.15, 0.13, (0, -0.12, 1.625))]
    bb = boolean(bb, tcut)
    P("helm_barbute").add(bb, M["steel_dark"], uv=4)
    P("helm_barbute").add(deform(bm_ico(0.098, 2, (0, 0.005, 1.69)), lambda c: (c[0], c[1] * 1.05, c[2])), M["void"])
    ridge = bm_box(0.012, 0.25, 0.012, (0, 0.0, 1.846), 0.004)
    deform(ridge, lambda c: (c[0], c[1], c[2] - 1.4 * c[1] ** 2 * 1.0))
    P("helm_barbute").add(ridge, M["steel_dark"])

    # ---------------- torso (spine bone) ----------------
    def chest_def(c):
        x, y, z = c
        y *= 0.72
        if y < 0:
            y *= 1.18
            y -= 0.014 * math.exp(-(x / 0.035) ** 2) * max(0, min(1, (z - 1.1) / 0.2))
        return (x, y, z)

    chest = bm_lathe([(0.135, 1.03), (0.15, 1.10), (0.163, 1.20), (0.176, 1.30), (0.172, 1.38),
                      (0.155, 1.44), (0.11, 1.49), (0.075, 1.505)], 32, cap_top=True, cap_bottom=True)
    deform(chest, chest_def)
    armholes = [deform(bm_ico(0.085, 2, (0.175 * s, 0, 1.40)), lambda c: (c[0], c[1] * 1.3, c[2] * 1.0)) for s in (-1, 1)]
    chest = boolean(chest, armholes)
    P("spine").add(chest, M["steel"], uv=3)
    # plackart / waist lame
    plk = bm_lathe([(0.14, 1.04), (0.143, 1.06), (0.152, 1.12), (0.149, 1.14)], 32, False, False)
    deform(plk, chest_def)
    plk = solidify(plk, 0.006, 1.0)
    P("spine").add(plk, M["steel"], uv=3)
    gorget = bm_lathe([(0.16, 1.43), (0.14, 1.475), (0.095, 1.515), (0.083, 1.55), (0.085, 1.565)], 28, False, False)
    deform(gorget, lambda c: (c[0], c[1] * 0.88, c[2]))
    gorget = solidify(gorget, 0.006, 1.0)
    P("spine").add(gorget, M["steel"], uv=4)
    for k in range(5):  # rivets along the gorget
        a = math.radians(-60 + 30 * k)
        P("spine").add(bm_ico(0.006, 1, (0.15 * math.sin(a), -0.13 * math.cos(a) * 0.88, 1.445)), M["brass"])
    # tabard / surcoat (optional layer toggled in JS)
    tab = bm_lathe([(0.165, 1.02), (0.168, 1.10), (0.178, 1.20), (0.19, 1.30), (0.186, 1.37), (0.17, 1.43), (0.13, 1.47)],
                   32, False, False)
    deform(tab, chest_def)
    tab = boolean(tab, [deform(bm_ico(0.1, 2, (0.18 * s, 0, 1.39)), lambda c: (c[0], c[1] * 1.4, c[2] * 1.1)) for s in (-1, 1)])
    tab = solidify(tab, 0.006, 1.0)
    P("tabard").add(tab, M["tabard"], uv=3)
    # emblem cross on tabard front
    cr = [bm_box(0.05, 0.02, 0.26, (0, -0.152, 1.26), 0.004), bm_box(0.2, 0.02, 0.05, (0, -0.155, 1.31), 0.004)]
    for c in cr:
        deform(c, lambda v: (v[0], v[1] - 0.012 * (1 - (v[0] / 0.18) ** 2), v[2]))
        P("tabard").add(c, M["emblem"], uv=6)

    # ---------------- pelvis ----------------
    for k in range(3):
        z0 = 1.03 - k * 0.045
        lame = bm_lathe([(0.152 + k * 0.012, z0), (0.162 + k * 0.012, z0 - 0.05)], 32, False, False)
        deform(lame, lambda c: (c[0], c[1] * 0.78 * (1.08 if c[1] < 0 else 1.0), c[2]))
        lame = solidify(lame, 0.005, 1.0)
        P("pelvis").add(lame, M["steel"], uv=3)
    mail = bm_lathe([(0.16, 0.99), (0.185, 0.88), (0.2, 0.80)], 32, False, False)
    deform(mail, lambda c: (c[0], c[1] * 0.8, c[2]))
    mail = solidify(mail, 0.006, 1.0)
    P("pelvis").add(mail, M["chain"], uv=10)
    belt = bm_lathe([(0.176, 0.955), (0.18, 0.96), (0.18, 0.985), (0.176, 0.99)], 32, False, False)
    deform(belt, lambda c: (c[0], c[1] * 0.83 * (1.06 if c[1] < 0 else 1.0), c[2]))
    belt = solidify(belt, 0.008, 1.0)
    P("pelvis").add(belt, M["leather"], uv=6)
    P("pelvis").add(bm_box(0.05, 0.016, 0.04, (0.0, -0.163, 0.972), 0.004), M["brass"])
    # tabard skirt flaps (separate nodes so the game can swing them away from the legs)
    for nm, sgn in (("skirt_front", -1), ("skirt_back", 1)):
        fl = bm_lathe([(0.19, 0.99), (0.215, 0.80), (0.235, 0.64)], 12, False, False,
                      arc=(math.radians(-90 * sgn - 42), math.radians(-90 * sgn + 42)))
        deform(fl, lambda c: (c[0], c[1] * 0.8, c[2]))
        fl = solidify(fl, 0.006, 1.0)
        P(nm).add(fl, M["tabard"], uv=3)

    # ---------------- arms ----------------
    for side, sfx in ((1, "L"), (-1, "R")):
        sh, el, wr = mirror(J["shoulder"], side), mirror(J["elbow"], side), mirror(J["wrist"], side)
        ua, fa, hd = P("upperarm_" + sfx), P("forearm_" + sfx), P("hand_" + sfx)
        # pauldron dome + lames
        pd = bm_lathe([(0.0, 0.075), (0.045, 0.07), (0.078, 0.05), (0.096, 0.012), (0.1, -0.03), (0.098, -0.055)],
                      24, cap_bottom=False)
        deform(pd, lambda c: (c[0], c[1] * 1.05, c[2]))
        pd = solidify(pd, 0.006)
        xform(pd, Matrix.Translation((sh[0] + 0.02 * side, sh[1], sh[2] - 0.015)) @ Matrix.Rotation(0.35 * side, 4, "Y"))
        ua.add(pd, M["steel"], uv=4)
        for k in range(2):
            lm = bm_lathe([(0.095 - k * 0.01, -0.05 - k * 0.035), (0.086 - k * 0.01, -0.09 - k * 0.035)], 24, False, False)
            deform(lm, lambda c: (c[0], c[1] * 1.05, c[2]))
            lm = solidify(lm, 0.005)
            xform(lm, Matrix.Translation((sh[0] + 0.02 * side, sh[1], sh[2] - 0.015)) @ Matrix.Rotation(0.35 * side, 4, "Y"))
            ua.add(lm, M["steel"], uv=4)
        ua.add(bm_ico(0.008, 1, (sh[0] + 0.03 * side, sh[1] - 0.1, sh[2] - 0.01)), M["brass"])
        # gambeson sleeve + rerebrace
        ua.add(limb_tube(sh, el, 0.05, 0.043, -0.1, 1.0, 14, 3), M["gambeson"], uv=5)
        ua.add(limb_tube(sh, el, 0.058, 0.05, 0.3, 0.95, 18, 4), M["steel"], uv=4)
        # couter (elbow cup + wing)
        cp = deform(bm_ico(0.058, 2), lambda c: (c[0], c[1] * 1.0 if c[1] > 0 else c[1] * 0.5, c[2] * 0.9))
        xform(cp, Matrix.Translation((el[0] + 0.004 * side, el[1] + 0.012, el[2])))
        fa.add(cp, M["steel"], uv=4)
        wing = deform(bm_box(0.012, 0.07, 0.09, (el[0] + 0.052 * side, el[1] + 0.0, el[2]), 0.005),
                      lambda c: (c[0] + 0.01 * side * math.cos((c[1] - el[1]) * 20), c[1], c[2]))
        fa.add(wing, M["steel"])
        fa.add(bm_ico(0.008, 1, (el[0] + 0.06 * side, el[1], el[2])), M["brass"])
        # vambrace
        fa.add(limb_tube(el, wr, 0.043, 0.036, -0.05, 1.0, 14, 3), M["gambeson"], uv=5)
        fa.add(limb_tube(el, wr, 0.05, 0.041, 0.12, 0.92, 18, 4), M["steel"], uv=4)
        # gauntlet: flared cuff + fist
        cuff = bm_lathe([(0.047, 0.0), (0.05, 0.03), (0.062, 0.1)], 18, False, False)
        cuff = solidify(cuff, 0.004, 1.0)
        xform(cuff, Matrix.Translation(wr) @ Matrix.Rotation(0, 4, "X"))
        hd.add(cuff, M["steel"], uv=4)
        fist = subsurf(bm_box(0.062, 0.095, 0.1, (0, 0, 0)), 2)
        xform(fist, Matrix.Translation((wr[0], wr[1], wr[2] - 0.07)))
        hd.add(fist, M["leather"], uv=8)
        back = subsurf(bm_box(0.02, 0.09, 0.075, (0, 0, 0)), 1)
        xform(back, Matrix.Translation((wr[0] + 0.03 * side, wr[1], wr[2] - 0.045)))
        hd.add(back, M["steel"], uv=6)
        for k in range(4):
            knuckle = bm_box(0.024, 0.02, 0.018, (wr[0] + 0.024 * side, wr[1] - 0.033 + 0.022 * k, wr[2] - 0.098), 0.005)
            hd.add(knuckle, M["steel"], uv=6)
        thumb = subsurf(bm_box(0.03, 0.028, 0.045, (0, 0, 0)), 1)
        xform(thumb, Matrix.Translation((wr[0] - 0.024 * side, wr[1] - 0.042, wr[2] - 0.06)))
        hd.add(thumb, M["steel"], uv=6)

    # ---------------- legs ----------------
    for side, sfx in ((1, "L"), (-1, "R")):
        hp, kn, an, to = mirror(J["hip"], side), mirror(J["knee"], side), mirror(J["ankle"], side), mirror(J["toe"], side)
        th, sn, ft = P("thigh_" + sfx), P("shin_" + sfx), P("foot_" + sfx)
        th.add(limb_tube(hp, kn, 0.074, 0.054, -0.05, 1.02, 16, 3), M["gambeson"], uv=5)
        cu = limb_tube(hp, kn, 0.086, 0.064, 0.12, 0.93, 20, 5, sy=0.95)
        th.add(cu, M["steel"], uv=4)
        # tasset (hangs from faulds, follows the thigh)
        ts = bm_lathe([(0.105, 0.0), (0.1, -0.08), (0.094, -0.14)], 10, False, False,
                      arc=(math.radians(-150 if side > 0 else -30) - 0.9, math.radians(-150 if side > 0 else -30) + 0.9))
        ts = solidify(ts, 0.005, 1.0)
        xform(ts, Matrix.Translation((hp[0] - 0.01 * side, hp[1], hp[2] - 0.0)))
        deform(ts, lambda c: (c[0], c[1] - 0.0, c[2]))
        th.add(ts, M["steel"], uv=4)
        # poleyn
        pl = deform(bm_ico(0.06, 2), lambda c: (c[0], c[1] * (0.55 if c[1] > 0 else 1.0), c[2] * 1.05))
        xform(pl, Matrix.Translation((kn[0], kn[1] - 0.025, kn[2])))
        sn.add(pl, M["steel"], uv=4)
        wing = deform(bm_box(0.012, 0.06, 0.08, (kn[0] + 0.058 * side, kn[1] - 0.005, kn[2]), 0.005),
                      lambda c: (c[0], c[1], c[2]))
        sn.add(wing, M["steel"])
        sn.add(bm_ico(0.009, 1, (kn[0], kn[1] - 0.085, kn[2])), M["brass"])
        # greave with calf bulge
        gr = limb_tube(kn, an, 0.06, 0.045, 0.06, 0.97, 20, 6)
        deform(gr, lambda c: (c[0], c[1] + (0.018 * math.sin(max(0, min(1, (kn[2] - c[2]) / (kn[2] - an[2]))) * math.pi) if c[1] > an[1] else 0), c[2]))
        sn.add(gr, M["steel"], uv=4)
        # sabaton: tapered shoe with lame ridges and a thin sole
        shoe = subsurf(bm_box(0.125, 0.34, 0.13, (0, 0, 0)), 2)
        deform(shoe, lambda c: (c[0] * (1 - 0.35 * max(0, -c[1] - 0.02) / 0.115),
                                c[1], c[2] * (1 - 0.55 * max(0, -c[1] + 0.03) / 0.165) + 0.0))
        xform(shoe, Matrix.Translation((an[0], an[1] - 0.07, 0.05)))
        deform(shoe, lambda c: (c[0], c[1], max(c[2], 0.004)))
        ft.add(shoe, M["steel"], uv=4)
        sole = bm_box(0.07, 0.22, 0.01, (an[0], an[1] - 0.06, 0.005), 0.003)
        ft.add(sole, M["leather"], uv=6)
        ank = bm_lathe([(0.047, 0.06), (0.05, 0.11), (0.047, 0.14)], 16, False, False)
        ank = solidify(ank, 0.004, 1.0)
        xform(ank, Matrix.Translation((an[0], an[1], 0.0)))
        ft.add(ank, M["steel"], uv=4)

    return parts


def build_armature():
    ad = bpy.data.armatures.new("knight_rig")
    arm = bpy.data.objects.new("knight", ad)
    bpy.context.scene.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    eb = ad.edit_bones

    def bone(name, head, tail, parent=None, roll_to=None):
        b = eb.new(name)
        b.head, b.tail = head, tail
        if parent:
            b.parent = eb[parent]
        if roll_to is not None:
            b.align_roll(Vector(roll_to))
        return b

    bone("pelvis", J["pelvis"], (0, 0, 1.06), roll_to=(0, -1, 0))
    bone("spine", J["spine"], J["spine_tail"], "pelvis", roll_to=(0, -1, 0))
    bone("head", J["neck"], J["head_top"], "spine", roll_to=(0, -1, 0))
    for side, sfx in ((1, "L"), (-1, "R")):
        bone("upperarm_" + sfx, mirror(J["shoulder"], side), mirror(J["elbow"], side), "spine", roll_to=(0, -1, 0))
        bone("forearm_" + sfx, mirror(J["elbow"], side), mirror(J["wrist"], side), "upperarm_" + sfx, roll_to=(0, -1, 0))
        bone("hand_" + sfx, mirror(J["wrist"], side), mirror(J["fist"], side), "forearm_" + sfx, roll_to=(0, -1, 0))
        bone("thigh_" + sfx, mirror(J["hip"], side), mirror(J["knee"], side), "pelvis", roll_to=(0, -1, 0))
        bone("shin_" + sfx, mirror(J["knee"], side), mirror(J["ankle"], side), "thigh_" + sfx, roll_to=(0, -1, 0))
        bone("foot_" + sfx, mirror(J["ankle"], side), mirror(J["toe"], side), "shin_" + sfx, roll_to=(0, 0, 1))
    for nm, y in (("skirt_front", -0.15), ("skirt_back", 0.15)):
        bone(nm, (0, y, 0.99), (0, y, 0.80), "pelvis", roll_to=(0, -1, 0))
    fr = mirror(J["fist"], -1)
    bone("sword_ik", fr, (fr[0], fr[1] - 0.12, fr[2]), "spine", roll_to=(0, 0, -1))
    bpy.ops.object.mode_set(mode="OBJECT")
    return arm


def parent_to_bone(ob, arm, bone_name):
    bpy.context.view_layer.update()
    mw = ob.matrix_world.copy()
    ob.parent = arm
    ob.parent_type = "BONE"
    ob.parent_bone = bone_name
    bpy.context.view_layer.update()
    ob.matrix_world = mw


# ---------------------------------------------------------------------------
# Animation authoring
# ---------------------------------------------------------------------------
# Poses are authored in "character space": x = right, y = forward, z = up.
# Blender space is (-x, -y, z). Bone rotations are (yaw, pitch, roll) degrees
# about character axes relative to the parent bone:
#   yaw   + = turn left (about up)
#   pitch + = lean forward / a hanging limb swings backward
#   roll  + = lean toward the character's left
# The sword pose is the right-fist position + blade direction + edge direction,
# relative to the unrotated chest; it is carried along by the spine rotation.

def cvec(v):
    return Vector((-v[0], -v[1], v[2]))


def crot(yaw=0.0, pitch=0.0, roll=0.0):
    rz = Matrix.Rotation(math.radians(yaw), 4, "Z")
    rx = Matrix.Rotation(math.radians(pitch), 4, "X")
    ry = Matrix.Rotation(math.radians(-roll), 4, "Y")
    return rz @ rx @ ry


FK_BONES = ["pelvis", "spine", "head", "upperarm_L", "forearm_L", "hand_L", "upperarm_R", "forearm_R",
            "hand_R", "thigh_L", "shin_L", "foot_L", "thigh_R", "shin_R", "foot_R", "skirt_front", "skirt_back"]

GUARD = dict(fist=(0.03, 0.30, 1.07), blade=(-0.08, 0.78, 0.6), edge=(0, 0.1, -1))
STANCE = {
    "pelvis_pos": (0, 0, -0.05), "pelvis": (8, 0, 0), "spine": (-6, 4, 0), "head": (-2, -3, 0),
    "thigh_L": (0, -20, 3), "shin_L": (0, 24, 0), "foot_L": (0, -4, 0),
    "thigh_R": (0, 14, -3), "shin_R": (0, 16, 0), "foot_R": (0, -30, 0),
    "upperarm_L": (0, -20, -10), "forearm_L": (0, -40, 0), "upperarm_R": (0, -20, 10), "forearm_R": (0, -40, 0),
}


def merge(*ds):
    out = {}
    for d in ds:
        out.update(d)
    return out


class Animator:
    def __init__(self, arm):
        self.arm = arm
        self.prev_q = {}
        self.reach_warnings = []

    def apply(self, pose):
        arm = self.arm
        for pb in arm.pose.bones:
            pb.rotation_mode = "QUATERNION"
            pb.rotation_quaternion = Quaternion()
            pb.location = Vector()
        for name in FK_BONES:
            if name in pose:
                pb = arm.pose.bones[name]
                rest = pb.bone.matrix_local.to_quaternion()
                r = crot(*pose[name]).to_quaternion()
                pb.rotation_quaternion = rest.inverted() @ r @ rest
        pb = arm.pose.bones["pelvis"]
        off = cvec(pose.get("pelvis_pos", (0, 0, 0)))
        pb.location = pb.bone.matrix_local.to_quaternion().inverted() @ off
        bpy.context.view_layer.update()
        sw = pose.get("sword", GUARD)
        spine = arm.pose.bones["spine"]
        delta = spine.matrix @ spine.bone.matrix_local.inverted()
        b = cvec(sw["blade"]).normalized()
        e = cvec(sw["edge"])
        e = (e - b * e.dot(b)).normalized()
        x = b.cross(e)
        m = Matrix.Identity(4)
        m.col[0][:3] = x
        m.col[1][:3] = b
        m.col[2][:3] = e
        m.col[3][:3] = cvec(sw["fist"])
        ik = arm.pose.bones["sword_ik"]
        ik.matrix = delta @ m
        bpy.context.view_layer.update()
        # reach check (wrist must be within ~0.56 m of the shoulder)
        fist_w = (delta @ m).translation
        for sfx, off_along in (("R", 0.0), ("L", -0.11)):
            p = fist_w + (delta @ m).to_3x3() @ Vector((0, off_along, 0))
            sh = arm.pose.bones["upperarm_" + sfx].head
            d = (p - sh).length
            if d > 0.62:
                self.reach_warnings.append((d, sfx))

    def key(self, frame):
        for pb in self.arm.pose.bones:
            q = pb.rotation_quaternion.copy()
            pq = self.prev_q.get(pb.name)
            if pq is not None and pq.dot(q) < 0:
                q.negate()
                pb.rotation_quaternion = q
            self.prev_q[pb.name] = q
            pb.keyframe_insert("rotation_quaternion", frame=frame)
            pb.keyframe_insert("location", frame=frame)

    def clip(self, name, keys):
        act = bpy.data.actions.new(name)
        act.use_fake_user = True
        self.arm.animation_data_create()
        self.arm.animation_data.action = act
        self.prev_q = {}
        for t, pose in keys:
            self.apply(pose)
            self.key(round(t * FPS))
        return act


def S(fist, blade, edge):
    return dict(fist=fist, blade=blade, edge=edge)


def mirror_sword(s):
    f, b, e = s["fist"], s["blade"], s["edge"]
    return S((-f[0], f[1], f[2]), (-b[0], b[1], b[2]), (-e[0], e[1], e[2]))


def mirror_body(p):
    out = {}
    for k, v in p.items():
        if k == "sword":
            out[k] = mirror_sword(v)
        elif k == "pelvis_pos":
            out[k] = (-v[0], v[1], v[2])
        else:
            nk = k[:-1] + ("R" if k.endswith("L") else "L") if k.endswith(("_L", "_R")) else k
            out[nk] = (-v[0], v[1], -v[2])
    return out


def build_clips(arm):
    A = Animator(arm)
    base = STANCE

    def up(*ds, **kw):
        return merge(base, *ds, kw)

    # ---- idle guard (breathing) ----
    A.clip("idle", [
        (0.0, up(sword=GUARD)),
        (1.0, up(sword=S((0.03, 0.31, 1.085), (-0.08, 0.78, 0.63), (0, 0.1, -1)), spine=(-6, 3, 0.5), pelvis_pos=(0, 0, -0.055))),
        (2.0, up(sword=GUARD)),
    ])

    # ---- attacks: windup / release / follow-through ----
    atk_right = [
        (0.00, up(sword=GUARD)),
        (0.30, up(sword=S((0.2, 0.06, 1.5), (0.35, -0.45, 0.85), (-0.6, 0.6, 0.2)), spine=(-38, -4, -4), head=(12, 0, 0),
                  pelvis=(-4, 0, 0))),
        (0.40, up(sword=S((0.13, 0.25, 1.38), (0.15, 0.45, 0.9), (-0.8, 0.4, -0.3)), spine=(-22, 2, -2), head=(8, 0, 0))),
        (0.48, up(sword=S((0.02, 0.4, 1.16), (-0.45, 0.85, -0.2), (-0.6, -0.1, -0.8)), spine=(2, 8, 2), head=(0, 0, 0),
                  pelvis_pos=(0, 0.05, -0.07), thigh_L=(0, -28, 3), shin_L=(0, 30, 0))),
        (0.58, up(sword=S((-0.12, 0.34, 0.99), (-0.8, 0.3, -0.5), (-0.3, -0.6, -0.7)), spine=(24, 10, 4), head=(-10, 0, 0),
                  pelvis_pos=(0, 0.07, -0.08), thigh_L=(0, -30, 3), shin_L=(0, 32, 0))),
        (0.72, up(sword=S((-0.17, 0.22, 0.93), (-0.6, -0.3, -0.72), (0.1, -0.7, -0.5)), spine=(32, 8, 3), head=(-14, 0, 0),
                  pelvis_pos=(0, 0.05, -0.07))),
        (1.00, up(sword=GUARD)),
    ]
    A.clip("atk_right", atk_right)
    A.clip("atk_left", [(t, mirror_body(p) if t not in (0.0, 1.0) else up(sword=GUARD)) for t, p in atk_right])

    A.clip("atk_over", [
        (0.00, up(sword=GUARD)),
        (0.32, up(sword=S((0.06, 0.05, 1.62), (0.05, -0.5, 0.85), (0, 1, 0.4)), spine=(-8, -12, 0), head=(0, 6, 0))),
        (0.42, up(sword=S((0.04, 0.26, 1.52), (0.02, 0.4, 0.95), (0, 0.9, -0.3)), spine=(-4, -2, 0))),
        (0.50, up(sword=S((0.02, 0.44, 1.26), (0, 0.97, 0.2), (0, 0.2, -1)), spine=(0, 16, 0), head=(0, -8, 0),
                  pelvis_pos=(0, 0.08, -0.1), thigh_L=(0, -32, 3), shin_L=(0, 36, 0))),
        (0.60, up(sword=S((0.01, 0.4, 1.0), (0, 0.5, -0.86), (0, -0.8, -0.4)), spine=(0, 24, 0), head=(0, -12, 0),
                  pelvis_pos=(0, 0.1, -0.12), thigh_L=(0, -34, 3), shin_L=(0, 38, 0))),
        (0.75, up(sword=S((0.02, 0.35, 0.95), (0.05, 0.35, -0.9), (0, -0.9, -0.3)), spine=(0, 18, 0), pelvis_pos=(0, 0.07, -0.1))),
        (1.05, up(sword=GUARD)),
    ])

    A.clip("atk_thrust", [
        (0.00, up(sword=GUARD)),
        (0.30, up(sword=S((0.14, -0.02, 1.16), (-0.05, 1, 0.12), (0, 0, -1)), spine=(-22, -4, 0), head=(14, 0, 0),
                  pelvis_pos=(0, -0.04, -0.06))),
        (0.42, up(sword=S((0.06, 0.3, 1.24), (-0.03, 1, 0.06), (0, 0, -1)), spine=(-6, 8, 0), head=(4, -4, 0),
                  pelvis_pos=(0, 0.1, -0.1), thigh_L=(0, -36, 3), shin_L=(0, 40, 0), thigh_R=(0, 24, -3))),
        (0.52, up(sword=S((0.0, 0.5, 1.28), (0, 1, 0.03), (0, 0, -1)), spine=(6, 18, 0), head=(-2, -10, 0),
                  pelvis_pos=(0, 0.2, -0.13), thigh_L=(0, -42, 3), shin_L=(0, 44, 0), thigh_R=(0, 30, -3), shin_R=(0, 10, 0))),
        (0.66, up(sword=S((0.02, 0.46, 1.26), (0, 1, 0.05), (0, 0, -1)), spine=(4, 14, 0), pelvis_pos=(0, 0.16, -0.12),
                  thigh_L=(0, -38, 3), shin_L=(0, 40, 0), thigh_R=(0, 26, -3))),
        (0.95, up(sword=GUARD)),
    ])

    # ---- blocks: named by the defender's side being protected ----
    blocks = {
        "block_L": up(sword=S((-0.12, 0.3, 1.18), (-0.18, 0.2, 0.96), (-1, 0.3, 0)), spine=(12, 0, 0), head=(-6, 0, 0)),
        "block_R": up(sword=S((0.22, 0.26, 1.14), (0.16, 0.18, 0.97), (1, 0.3, 0)), spine=(-18, 0, 0), head=(10, 0, 0)),
        "block_high": up(sword=S((0.1, 0.24, 1.6), (-0.95, 0.25, 0.14), (0, 0.15, 1)), spine=(-8, -4, 0)),
        "block_mid": up(sword=S((0.06, 0.3, 1.04), (0.35, 0.88, 0.32), (1, 0, 0)), spine=(-10, 2, 0)),
    }
    for nm, p in blocks.items():
        A.clip(nm, [(0.0, p), (0.5, p)])

    # ---- reactions ----
    A.clip("recoil", [
        (0.0, up(sword=S((0.02, 0.4, 1.2), (-0.3, 0.9, 0.1), (-0.6, 0, -0.8)))),
        (0.12, up(sword=S((0.1, 0.18, 1.34), (0.4, 0.3, 0.86), (0.6, 0.6, 0)), spine=(-14, -8, 0), head=(0, 8, 0),
                  pelvis_pos=(0, -0.08, -0.05))),
        (0.3, up(sword=S((0.08, 0.22, 1.25), (0.2, 0.5, 0.84), (0.4, 0.6, -0.4)), spine=(-10, -6, 0), pelvis_pos=(0, -0.1, -0.05))),
        (0.6, up(sword=GUARD)),
    ])
    A.clip("hit_react", [
        (0.0, up(sword=GUARD)),
        (0.1, up(sword=S((0.05, 0.22, 1.05), (0.1, 0.8, 0.45), (0, 0, -1)), spine=(-14, -16, 6), head=(-10, -20, 8),
                  pelvis_pos=(0, -0.05, -0.06))),
        (0.45, up(sword=GUARD)),
    ])
    A.clip("stagger", [
        (0.0, up(sword=GUARD)),
        (0.15, up(sword=S((0.16, 0.12, 1.3), (0.5, 0.2, 0.84), (0.8, 0, 0)), spine=(-18, -22, 8), head=(0, -18, 0),
                  pelvis_pos=(0, -0.12, -0.06), thigh_R=(0, 30, -3), shin_R=(0, 30, 0), thigh_L=(0, -5, 3))),
        (0.45, up(sword=S((0.14, 0.12, 1.1), (0.5, 0.5, 0.7), (0.8, 0, -0.3)), spine=(-10, -12, 4), head=(6, -8, 0),
                  pelvis_pos=(0, -0.2, -0.1), thigh_R=(0, 34, -3), shin_R=(0, 40, 0))),
        (0.8, up(sword=S((0.06, 0.22, 1.02), (0.2, 0.7, 0.66), (0, 0, -1)), spine=(-8, 0, 0), pelvis_pos=(0, -0.1, -0.08))),
        (1.1, up(sword=GUARD)),
    ])

    # ---- dodges ----
    low = dict(pelvis_pos=(0, 0, -0.2), thigh_L=(0, -48, 4), shin_L=(0, 70, 0), foot_L=(0, -22, 0),
               thigh_R=(0, -10, -4), shin_R=(0, 60, 0), foot_R=(0, -50, 0))
    A.clip("dodge_back", [
        (0.0, up(sword=GUARD)),
        (0.12, up(low, spine=(-6, 16, 0), sword=S((0.06, 0.25, 1.0), (0.1, 0.9, 0.4), (0, 0, -1)))),
        (0.38, up(low, spine=(-6, 10, 0))),
        (0.55, up(sword=GUARD)),
    ])
    side = dict(pelvis_pos=(0.0, 0, -0.14), thigh_L=(0, -20, 18), shin_L=(0, 40, 0), thigh_R=(0, 10, -8), shin_R=(0, 40, 0))
    A.clip("dodge_left", [
        (0.0, up(sword=GUARD)),
        (0.12, up(side, pelvis=(8, 0, 10), spine=(-6, 6, 14), head=(0, 0, -8))),
        (0.38, up(side, pelvis=(8, 0, 8), spine=(-6, 4, 10))),
        (0.55, up(sword=GUARD)),
    ])
    A.clip("dodge_right", [(t, mirror_body(p) if 0 < t < 0.55 else up(sword=GUARD)) for t, p in [
        (0.0, None), (0.12, up(side, pelvis=(-8, 0, 10), spine=(6, 6, 14), head=(0, 0, -8))),
        (0.38, up(side, pelvis=(-8, 0, 8), spine=(6, 4, 10))), (0.55, None)]])

    # ---- deaths / crippled (arms are FK here; the game drops the sword) ----
    limp = dict(upperarm_L=(0, -10, -20), forearm_L=(0, -20, 0), upperarm_R=(0, -10, 20), forearm_R=(0, -20, 0))
    A.clip("death_back", [
        (0.0, up(**limp)),
        (0.25, up(limp, spine=(0, -20, 6), head=(0, -30, 0), pelvis_pos=(0, -0.1, -0.12), thigh_R=(0, 30, -3),
                  shin_R=(0, 40, 0), upperarm_L=(0, -40, -40), upperarm_R=(0, -30, 45))),
        (0.6, up(pelvis_pos=(0, -0.3, -0.55), pelvis=(0, -40, 0), spine=(0, -20, 4), head=(0, -20, 0),
                 thigh_L=(0, -50, 10), shin_L=(0, 70, 0), thigh_R=(0, -30, -10), shin_R=(0, 60, 0),
                 upperarm_L=(0, -90, -50), forearm_L=(0, -30, 0), upperarm_R=(0, -80, 60), forearm_R=(0, -40, 0))),
        (0.95, up(pelvis_pos=(0, -0.55, -0.83), pelvis=(0, -88, 0), spine=(0, -4, 3), head=(20, -10, 0),
                  thigh_L=(0, -8, 12), shin_L=(0, 14, 0), foot_L=(0, 40, 0), thigh_R=(0, -14, -8), shin_R=(0, 26, 0),
                  foot_R=(0, 30, 0), upperarm_L=(0, -95, -70), forearm_L=(0, -25, 0), upperarm_R=(0, -110, 75),
                  forearm_R=(0, -35, 0))),
        (1.1, up(pelvis_pos=(0, -0.58, -0.86), pelvis=(0, -90, 0), spine=(0, -2, 3), head=(28, -6, 0),
                 thigh_L=(0, -6, 12), shin_L=(0, 12, 0), foot_L=(0, 40, 0), thigh_R=(0, -12, -8), shin_R=(0, 22, 0),
                 foot_R=(0, 30, 0), upperarm_L=(0, -90, -72), forearm_L=(0, -20, 0), upperarm_R=(0, -105, 78),
                 forearm_R=(0, -30, 0))),
    ])
    A.clip("death_fwd", [
        (0.0, up(**limp)),
        (0.3, up(limp, spine=(0, 24, 0), head=(0, 20, 0), pelvis_pos=(0, 0.05, -0.2), thigh_L=(0, -40, 3), shin_L=(0, 60, 0),
                 thigh_R=(0, -5, -3), shin_R=(0, 60, 0))),
        (0.6, up(pelvis_pos=(0, 0.15, -0.5), pelvis=(0, 30, 0), spine=(0, 30, 0), head=(0, 10, 0),
                 thigh_L=(0, -60, 3), shin_L=(0, 90, 0), thigh_R=(0, -40, -3), shin_R=(0, 85, 0),
                 upperarm_L=(0, -70, -20), upperarm_R=(0, -70, 20))),
        (0.95, up(pelvis_pos=(0, 0.5, -0.8), pelvis=(0, 86, 0), spine=(0, 4, 0), head=(-30, 10, 0),
                  thigh_L=(0, -4, 8), shin_L=(0, 10, 0), foot_L=(0, -50, 0), thigh_R=(0, 0, -8), shin_R=(0, 16, 0),
                  foot_R=(0, -50, 0), upperarm_L=(0, -150, -30), forearm_L=(0, -30, 0), upperarm_R=(0, -40, 50),
                  forearm_R=(0, -10, 0))),
        (1.1, up(pelvis_pos=(0, 0.52, -0.84), pelvis=(0, 88, 0), spine=(0, 2, 0), head=(-34, 8, 0),
                 thigh_L=(0, -2, 8), shin_L=(0, 8, 0), foot_L=(0, -50, 0), thigh_R=(0, 0, -8), shin_R=(0, 12, 0),
                 foot_R=(0, -50, 0), upperarm_L=(0, -155, -30), forearm_L=(0, -25, 0), upperarm_R=(0, -35, 52),
                 forearm_R=(0, -8, 0))),
    ])
    kneel = up(limp, pelvis_pos=(0, -0.02, -0.46), pelvis=(0, 4, 0), spine=(0, 14, 0), head=(0, 18, 0),
               thigh_L=(0, -86, 6), shin_L=(0, 88, 0), foot_L=(0, 40, 0),
               thigh_R=(0, -80, -6), shin_R=(0, 86, 0), foot_R=(0, 40, 0))
    A.clip("kneel", [(0.0, up(**limp)), (0.35, kneel), (1.2, merge(kneel, dict(spine=(0, 20, 0), head=(0, 24, 0)))),
                     (2.0, kneel)])
    A.clip("death_kneel", [
        (0.0, up(**limp)),
        (0.4, kneel),
        (1.3, merge(kneel, dict(spine=(0, 26, 0), upperarm_L=(0, -20, -10), upperarm_R=(0, -20, 10)))),
        (1.8, merge(kneel, dict(pelvis_pos=(0, 0.25, -0.62), pelvis=(0, 50, 0), spine=(0, 20, 0), thigh_L=(0, -60, 6),
                                thigh_R=(0, -56, -6), upperarm_L=(0, -60, -30), upperarm_R=(0, -60, 30)))),
        (2.1, merge(kneel, dict(pelvis_pos=(0, 0.52, -0.82), pelvis=(0, 84, 0), spine=(0, 6, 0), head=(-20, 10, 0),
                                thigh_L=(0, -10, 6), shin_L=(0, 30, 0), thigh_R=(0, -8, -6), shin_R=(0, 34, 0),
                                foot_L=(0, -40, 0), foot_R=(0, -40, 0),
                                upperarm_L=(0, -150, -40), upperarm_R=(0, -60, 50), forearm_L=(0, -20, 0), forearm_R=(0, -20, 0)))),
        (2.3, merge(kneel, dict(pelvis_pos=(0, 0.54, -0.85), pelvis=(0, 88, 0), spine=(0, 2, 0), head=(-26, 8, 0),
                                thigh_L=(0, -6, 6), shin_L=(0, 24, 0), thigh_R=(0, -4, -6), shin_R=(0, 28, 0),
                                foot_L=(0, -40, 0), foot_R=(0, -40, 0),
                                upperarm_L=(0, -155, -40), upperarm_R=(0, -55, 52), forearm_L=(0, -18, 0), forearm_R=(0, -18, 0)))),
    ])
    A.clip("victory", [
        (0.0, up(sword=GUARD)),
        (0.5, up(sword=S((0.05, 0.12, 1.75), (0.05, 0.1, 1.0), (0, 1, 0)), spine=(0, -10, 0), head=(0, -18, 0))),
        (1.5, up(sword=S((0.05, 0.12, 1.77), (0.05, 0.08, 1.0), (0, 1, 0)), spine=(0, -12, 0), head=(0, -20, 0))),
        (2.0, up(sword=GUARD)),
    ])

    # ---- locomotion (legs only are used by the game) ----
    def gait(name, dur, fn, n=12):
        keys = []
        for i in range(n + 1):
            ph = i / n
            keys.append((dur * ph, merge(base, {"sword": GUARD}, fn(ph))))
        A.clip(name, keys)

    def leg(ph, amp, lift, knee0=10.0):
        s = math.sin(ph * 2 * math.pi)
        c = math.cos(ph * 2 * math.pi)
        thigh = -amp * c
        swing = max(0.0, s)  # swing phase when foot moves forward
        shin = knee0 + lift * swing
        foot = -(thigh + shin) * 0.6
        return thigh, shin, foot

    def walk(amp, lift, bob, lean=0.0):
        def fn(ph):
            tl, sl, fl = leg(ph, amp, lift)
            tr, sr, fr = leg(ph + 0.5, amp, lift)
            return {"thigh_L": (0, tl, 3), "shin_L": (0, sl, 0), "foot_L": (0, fl, 0),
                    "thigh_R": (0, tr, -3), "shin_R": (0, sr, 0), "foot_R": (0, fr, 0),
                    "pelvis_pos": (0, 0, -0.05 - bob * abs(math.cos(ph * 2 * math.pi))),
                    "pelvis": (4 * math.sin(ph * 2 * math.pi), lean, 0), "spine": (-6 - 4 * math.sin(ph * 2 * math.pi), 4, 0)}
        return fn

    gait("walk_fwd", 1.0, walk(24, 38, 0.025))
    gait("run", 0.7, walk(38, 70, 0.05, 8))
    back = walk(20, 34, 0.02)
    gait("walk_back", 1.0, lambda ph: back(1 - ph))

    def strafe(sign):
        def fn(ph):
            s = math.sin(ph * 2 * math.pi)
            c = math.cos(ph * 2 * math.pi)
            return {"thigh_L": (0, -10, 3 + 14 * c * sign), "shin_L": (0, 18 + 26 * max(0, s), 0), "foot_L": (0, -6, 0),
                    "thigh_R": (0, 8, -3 + 14 * c * sign), "shin_R": (0, 18 + 26 * max(0, -s), 0), "foot_R": (0, -20, 0),
                    "pelvis_pos": (0, 0, -0.06 - 0.02 * abs(c))}
        return fn

    gait("strafe_L", 0.9, strafe(1))
    gait("strafe_R", 0.9, strafe(-1))

    # rest pose for the export
    arm.animation_data.action = None
    for pb in arm.pose.bones:
        pb.rotation_quaternion = Quaternion()
        pb.location = Vector()
    if A.reach_warnings:
        print("REACH WARNINGS:", sorted(A.reach_warnings, reverse=True)[:10])


def export_glb(path, animations=False):
    bpy.ops.export_scene.gltf(
        filepath=path, export_format="GLB", export_yup=True, export_apply=False,
        export_animations=animations, export_animation_mode="ACTIONS", export_force_sampling=True,
        export_def_bones=False, export_leaf_bone=False, export_optimize_animation_size=True,
        export_image_format="AUTO", export_materials="EXPORT", export_cameras=False, export_lights=False,
        export_extras=False, export_rest_position_armature=True, export_anim_slide_to_zero=True,
    )
    print("wrote", path, os.path.getsize(path) // 1024, "KB")


def knight_materials():
    steel = texset("steel", tex_steel(512, 1, 0.3))
    dark = texset("steeldark", tex_steel(512, 5, 0.42))
    return {
        "steel": material("steel", steel, nstr=0.6),
        "steel_dark": material("steel_dark", dark, nstr=0.6),
        "brass": material("brass", color=(0.78, 0.55, 0.22), rough=0.35, metal=1.0),
        "leather": material("leather", texset("leather", tex_leather())),
        "chain": material("chain", texset("chain", tex_chain()), nstr=1.0),
        "gambeson": material("gambeson", texset("gambeson", tex_cloth(512, 21, (0.32, 0.25, 0.18))), nstr=0.8),
        "tabard": material("tabard", texset("cloth", tex_cloth(512, 22)), nstr=0.7),
        "emblem": material("emblem", color=(0.9, 0.85, 0.7), rough=0.9),
        "void": material("void", color=(0.0, 0.0, 0.0), rough=1.0),
    }


def build_knight_file():
    reset_scene()
    M = knight_materials()
    # the gambeson is tinted dark in the viewer; the game tints tabard/gambeson per fighter
    parts = build_knight(M)
    arm = build_armature()
    bone_of = {
        "helm_great": "head", "helm_bascinet": "head", "helm_barbute": "head", "spine": "spine",
        "tabard": "spine", "pelvis": "pelvis", "skirt_front": "skirt_front", "skirt_back": "skirt_back",
    }
    for name, part in parts.items():
        bn = bone_of.get(name, name)
        origin = arm.data.bones[bn].head_local
        ob = part.build(origin)
        parent_to_bone(ob, arm, bn)
    build_clips(arm)
    export_glb(os.path.join(OUT, "knight.glb"), animations=True)


# ---------------------------------------------------------------------------
# Sword
# ---------------------------------------------------------------------------

def build_sword_file():
    reset_scene()
    blade_t = texset("blade", tex_steel(512, 9, 0.16))
    M_blade = material("blade", blade_t, nstr=0.25)
    M_steel = material("hilt", texset("hilt", tex_steel(256, 11, 0.38)), nstr=0.6)
    M_leather = material("grip", texset("grip", tex_leather(256, 12)))
    part = Part("longsword")

    # blade: loft of cross sections with a fuller for the first 70%
    z0, z1 = 0.08, 1.06
    n = 26
    bm = bmesh.new()
    rings = []
    for i in range(n + 1):
        t = i / n
        z = z0 + (z1 - z0) * t
        if t < 0.86:
            w = 0.052 - 0.02 * (t / 0.86)
        else:
            k = (t - 0.86) / 0.14
            w = 0.032 * math.sqrt(max(0.0, 1 - k * k))
        th = 0.0075 * (1 - 0.45 * t)
        fuller = max(0.0, 1 - t / 0.7) if t < 0.7 else 0.0
        pts = [(-w / 2, 0), (-w * 0.27, th * 0.8), (-w * 0.12, th * (0.8 - 0.3 * fuller)), (0, th * (0.8 - 0.35 * fuller)),
               (w * 0.12, th * (0.8 - 0.3 * fuller)), (w * 0.27, th * 0.8), (w / 2, 0)]
        pts = pts + [(x, -y) for x, y in reversed(pts[1:-1])]
        if i == n:
            rings.append([bm.verts.new((0, 0, z))] * len(pts))
        else:
            rings.append([bm.verts.new((x, y, z)) for x, y in pts])
    m = len(rings[0])
    for k in range(n):
        for i in range(m):
            j = (i + 1) % m
            vs = [rings[k][i], rings[k][j], rings[k + 1][j], rings[k + 1][i]]
            uniq = list(dict.fromkeys(vs))
            if len(uniq) >= 3:
                bm.faces.new(uniq)
    bm.faces.new(list(reversed(rings[0])))
    bm.normal_update()
    part.add(bm, M_blade, uv=1.2, sharp=40)

    guard = bm_box(0.25, 0.022, 0.024, (0, 0, 0.065), 0.005, 2)
    bmesh.ops.subdivide_edges(guard, edges=[e for e in guard.edges if abs(e.verts[0].co.x - e.verts[1].co.x) > 0.1], cuts=8)
    deform(guard, lambda c: (c[0], c[1] * (1 + 1.5 * abs(c[0]) ** 2 * 40), c[2] + 1.2 * c[0] ** 2))
    part.add(guard, M_steel, uv=6)
    for s in (-1, 1):
        part.add(bm_ico(0.016, 2, (0.13 * s, 0, 0.065 + 0.02)), M_steel, uv=6)
    grip = bm_lathe([(0.013, -0.175), (0.0155, -0.12), (0.016, -0.05), (0.0145, 0.02), (0.013, 0.055)], 12)
    part.add(grip, M_leather, uv=10)
    for z in (-0.17, 0.052):
        part.add(bm_lathe([(0.0165, z), (0.0165, z + 0.012)], 12), M_steel, uv=8)
    pommel = bm_lathe([(0.0, -0.011), (0.022, -0.011), (0.03, -0.006), (0.03, 0.006), (0.022, 0.011), (0.0, 0.011)], 24)
    xform(pommel, Matrix.Translation((0, 0, -0.2)) @ Matrix.Rotation(math.pi / 2, 4, "Y"))
    part.add(pommel, M_steel, uv=8)
    part.add(bm_lathe([(0.008, -0.228), (0.008, -0.21), (0.0, -0.206)], 10), M_steel, uv=8)
    part.build()
    export_glb(os.path.join(OUT, "sword.glb"))


# ---------------------------------------------------------------------------
# Gore pieces
# ---------------------------------------------------------------------------

def build_gore_file():
    reset_scene()
    flesh = material("flesh", texset("flesh", tex_flesh()), nstr=1.0)
    bone_m = material("bone", color=(0.86, 0.8, 0.68), rough=0.45)
    marrow = material("marrow", color=(0.35, 0.02, 0.03), rough=0.3)
    rng = random.Random(3)

    def stump(name, bones):
        p = Part(name)
        prof = [(0.0, 0.06), (0.35, 0.05), (0.7, 0.03), (0.95, 0.0), (1.0, -0.12)]
        bm = bm_lathe(prof, 28, cap_bottom=True)
        for v in bm.verts:
            if math.hypot(v.co.x, v.co.y) > 0.9:
                v.co.z += rng.uniform(-0.05, 0.1)
                v.co.x *= rng.uniform(0.95, 1.1)
                v.co.y *= rng.uniform(0.95, 1.1)
            elif v.co.z > 0.0:
                v.co.z += rng.uniform(-0.02, 0.03)
        bm.normal_update()
        p.add(bm, flesh, uv=1.0)
        for (x, y, r, h) in bones:
            b = bm_lathe([(r * 1.1, 0.0), (r, h * 0.7), (r * 1.05, h)], 12, cap_top=False)
            xform(b, Matrix.Translation((x, y, 0)))
            deform(b, lambda c: (c[0], c[1], c[2] + (rng.uniform(-0.03, 0.03) if c[2] > h * 0.9 else 0)))
            p.add(b, bone_m, uv=2.0)
            mr = bm_lathe([(r * 0.6, h * 0.95), (r * 0.5, h * 0.97), (0, h * 0.97)], 10, cap_bottom=False)
            xform(mr, Matrix.Translation((x, y, 0)))
            p.add(mr, marrow, uv=2.0)
        ob = p.build()
        ob.rotation_euler = (math.pi / 2, 0, 0)  # +Z (cap normal) -> exported as +Y ... keep Blender +Z, exporter maps to +Y
        ob.rotation_euler = (0, 0, 0)
        return ob

    stump("stump_limb", [(0.0, 0.05, 0.26, 0.16)])
    neck = stump("stump_neck", [(0.0, 0.25, 0.22, 0.14)])
    # trachea on the neck stump
    t = Part("stump_trachea")
    tr = bm_lathe([(0.2, 0.0), (0.2, 0.1), (0.15, 0.12)], 12, cap_top=False, cap_bottom=True)
    xform(tr, Matrix.Translation((0, -0.35, 0)))
    t.add(tr, material("trachea", color=(0.75, 0.55, 0.5), rough=0.4), uv=2)
    tob = t.build()
    tob.parent = neck

    for i in range(4):
        p = Part("gib_%d" % i)
        bm = bm_ico(1.0, 2)
        seed = rng.random() * 10
        for v in bm.verts:
            n = v.co.normalized()
            d = 1 + 0.25 * math.sin(n.x * 5 + seed) * math.cos(n.y * 4 - seed) + rng.uniform(-0.12, 0.12)
            v.co = n * d
        deform(bm, lambda c: (c[0] * 1.2, c[1] * 0.8, c[2] * 0.9))
        p.add(bm, flesh, uv=1.0, sharp=60)
        if i == 3:
            sh = bm_lathe([(0.25, -1.3), (0.28, 0.0), (0.18, 1.2), (0.0, 1.4)], 8)
            p.add(sh, bone_m, uv=1)
        p.build()
    export_glb(os.path.join(OUT, "gore.glb"))


# ---------------------------------------------------------------------------
# Arena
# ---------------------------------------------------------------------------

ARENA_R = 14.0


def build_arena_file():
    reset_scene()
    sand = material("sand", texset("sand", tex_sand()), nstr=1.0)
    stone = material("stone", texset("stone", tex_stone()), nstr=1.2)
    stone_dark = material("stone_dark", texset("stone2", tex_stone(1024, 55, 6)), nstr=1.2)
    wood = material("wood", texset("wood", tex_wood()))
    iron = material("iron", texset("iron", tex_steel(256, 13, 0.55)), nstr=1.0)
    banner_red = material("banner_red", texset("banner", tex_cloth(512, 23)), nstr=0.8)
    tar = material("tar", color=(0.05, 0.03, 0.02), rough=0.9)
    crowd_m = material("crowd", color=(0.8, 0.8, 0.8), rough=0.9)

    # floor
    floor = Part("floor")
    prof = [(0.0, 0.0)] + [(r, 0.0) for r in (2, 4, 6, 8, 10, 12, 14.5)]
    f = bm_lathe(prof, 48, cap_bottom=False, cap_top=False)
    bmesh.ops.reverse_faces(f, faces=f.faces)
    floor.add(f, sand, uv=1 / 3.0, uvmode="planar", smooth=True, sharp=80)
    floor.build()

    # wall + parapet + stands
    wall = Part("wall")
    w = bm_lathe([(ARENA_R + 0.5, -0.1), (ARENA_R, -0.1), (ARENA_R, 3.0), (ARENA_R - 0.12, 3.05), (ARENA_R - 0.12, 3.25),
                  (ARENA_R + 1.0, 3.25)], 96, False, False)
    bmesh.ops.reverse_faces(w, faces=w.faces)
    wall.add(w, stone, uv=1 / 2.5, uvmode="cyl", sharp=30)
    tiers = [(ARENA_R + 1.0, 3.25)]
    for k in range(7):
        r0 = ARENA_R + 1.0 + k * 1.1
        tiers += [(r0, 3.25 + 0.75 * (k + 1)), (r0 + 1.1, 3.25 + 0.75 * (k + 1))]
    tiers += [(tiers[-1][0], 14.0), (tiers[-1][0] + 0.8, 14.0), (tiers[-1][0] + 0.8, 0)]
    st = bm_lathe(tiers, 96, False, False)
    bmesh.ops.reverse_faces(st, faces=st.faces)
    wall.add(st, stone_dark, uv=1 / 2.5, uvmode="cyl", sharp=30)
    # merlons on the parapet
    n_merl = 64
    for i in range(n_merl):
        a = 2 * math.pi * i / n_merl
        m = bm_box(0.18, 0.7, 0.45, (0, 0, 0), 0.02, 1)
        xform(m, Matrix.Rotation(a, 4, "Z") @ Matrix.Translation((ARENA_R - 0.05, 0, 3.45)))
        wall.add(m, stone, uv=1 / 2.0)
    wall.build()

    # pillars with torches
    pil = Part("pillars")
    torches = Part("torch_holders")
    anchors = []
    n_p = 16
    for i in range(n_p):
        a = 2 * math.pi * (i + 0.5) / n_p
        rot = Matrix.Rotation(a, 4, "Z")
        r = ARENA_R - 0.35
        for (sx, sz, z) in ((0.9, 0.3, 0.15), (0.7, 3.2, 1.75), (0.95, 0.25, 3.45)):
            b = bm_box(sx, sx, sz, (0, 0, 0), 0.03, 1)
            xform(b, rot @ Matrix.Translation((r, 0, z)))
            pil.add(b, stone, uv=1 / 1.5)
        # torch: bracket + handle + tar head, sticking out of the pillar's inner face
        bx = bm_box(0.3, 0.05, 0.05, (0, 0, 0), 0.01, 1)
        xform(bx, rot @ Matrix.Translation((r - 0.45, 0, 2.2)))
        torches.add(bx, iron, uv=3)
        ring = bm_lathe([(0.05, -0.02), (0.05, 0.02)], 10, False, False)
        ring = solidify(ring, 0.01)
        xform(ring, rot @ Matrix.Translation((r - 0.6, 0, 2.2)))
        torches.add(ring, iron, uv=3)
        h = bm_lathe([(0.025, 0.0), (0.03, 0.45)], 8)
        xform(h, rot @ Matrix.Translation((r - 0.6, 0, 1.95)) @ Matrix.Rotation(-0.25, 4, "Y"))
        torches.add(h, wood, uv=2)
        hd = bm_lathe([(0.03, 0.0), (0.045, 0.05), (0.045, 0.16), (0.03, 0.18)], 10)
        xform(hd, rot @ Matrix.Translation((r - 0.6, 0, 1.95)) @ Matrix.Rotation(-0.25, 4, "Y") @ Matrix.Translation((0, 0, 0.4)))
        torches.add(hd, tar, uv=2)
        tip = rot @ Matrix.Translation((r - 0.6, 0, 1.95)) @ Matrix.Rotation(-0.25, 4, "Y") @ Vector((0, 0, 0.62))
        anchors.append(tuple(tip))
    pil.build()
    torches.build()

    # braziers on the sand
    braz = Part("braziers")
    for i in range(4):
        a = 2 * math.pi * i / 4 + math.pi / 4
        c = Vector((math.cos(a) * 10.5, math.sin(a) * 10.5, 0))
        bowl = bm_lathe([(0.0, 0.85), (0.3, 0.88), (0.5, 1.0), (0.55, 1.12)], 20, cap_top=False)
        bowl = solidify(bowl, 0.03)
        xform(bowl, Matrix.Translation(c))
        braz.add(bowl, iron, uv=2)
        coal = bm_lathe([(0.0, 1.06), (0.5, 1.06)], 20, cap_bottom=False)
        xform(coal, Matrix.Translation(c))
        braz.add(coal, tar, uv=2)
        for k in range(3):
            b = k * 2 * math.pi / 3
            leg_ = bm_box(0.04, 0.04, 1.0, (0, 0, 0), 0.01, 1)
            xform(leg_, Matrix.Translation(c + Vector((math.cos(b) * 0.3, math.sin(b) * 0.3, 0.45))) @
                  Matrix.Rotation(0.3, 4, Vector((-math.sin(b), math.cos(b), 0))))
            braz.add(leg_, iron, uv=2)
        anchors.append(tuple(c + Vector((0, 0, 1.15))))
    braz.build()

    # gates
    gates = Part("gates")
    for a in (0.0, math.pi):
        rot = Matrix.Rotation(a, 4, "Z")
        g = bm_box(0.15, 3.6, 2.9, (0, 0, 0), 0.02, 1)
        xform(g, rot @ Matrix.Translation((ARENA_R - 0.1, 0, 1.45)))
        gates.add(g, wood, uv=1 / 1.2)
        for z in (0.5, 1.5, 2.5):
            band = bm_box(0.05, 3.62, 0.12, (0, 0, 0), 0.01, 1)
            xform(band, rot @ Matrix.Translation((ARENA_R - 0.18, 0, z)))
            gates.add(band, iron, uv=2)
            for k in range(9):
                stud = bm_ico(0.03, 1)
                xform(stud, rot @ Matrix.Translation((ARENA_R - 0.21, -1.6 + 0.4 * k, z)))
                gates.add(stud, iron, uv=2)
        arch = bm_box(0.9, 4.6, 0.6, (0, 0, 0), 0.03, 1)
        xform(arch, rot @ Matrix.Translation((ARENA_R - 0.1, 0, 3.1)))
        gates.add(arch, stone, uv=1 / 1.5)
        for s in (-1, 1):
            jamb = bm_box(0.9, 0.5, 3.0, (0, 0, 0), 0.03, 1)
            xform(jamb, rot @ Matrix.Translation((ARENA_R - 0.1, 2.05 * s, 1.5)))
            gates.add(jamb, stone, uv=1 / 1.5)
    gates.build()

    # banners between pillars
    ban = Part("banners")
    poles = Part("banner_poles")
    for i in range(n_p):
        if i % 4 in (1, 3):
            continue
        a = 2 * math.pi * i / n_p
        rot = Matrix.Rotation(a, 4, "Z")
        b = bmesh.new()
        bmesh.ops.create_grid(b, x_segments=4, y_segments=8, size=0.5)
        for v in b.verts:
            u = v.co.x + 0.5
            t = v.co.y + 0.5
            v.co = Vector((0.06 * math.sin(t * 3 + u), v.co.x * 1.1, 1.0 + t * 2.1))
            if t < 0.02 and abs(v.co.y) < 0.1:
                v.co.z -= 0.25
        b = solidify(b, 0.01, 0)
        xform(b, rot @ Matrix.Translation((ARENA_R - 0.08, 0, 0)))
        ban.add(b, banner_red, uv=1.0)
        pole = bm_lathe([(0.025, -0.65), (0.025, 0.65)], 8)
        xform(pole, rot @ Matrix.Translation((ARENA_R - 0.1, 0, 3.12)) @ Matrix.Rotation(math.pi / 2, 4, "X"))
        poles.add(pole, wood, uv=2)
    ban.build()
    poles.build()

    # props: barrels, weapon racks, a stack of shields
    props = Part("props")
    for i, a in enumerate((0.35, 0.5, 2.6, 3.9, 5.5)):
        c = Vector((math.cos(a) * 12.9, math.sin(a) * 12.9, 0))
        prof = [(0.0, 0.0)] + [(0.3 + 0.06 * math.sin(t / 8 * math.pi), t / 8 * 0.9) for t in range(9)] + [(0.0, 0.9)]
        br = bm_lathe(prof, 16)
        xform(br, Matrix.Translation(c))
        props.add(br, wood, uv=1.5, uvmode="cyl")
        for z in (0.12, 0.78):
            hoop = bm_lathe([(0.31 + 0.06 * math.sin(z / 0.9 * math.pi), z - 0.03), (0.31 + 0.06 * math.sin(z / 0.9 * math.pi), z + 0.03)], 16, False, False)
            hoop = solidify(hoop, 0.01, 1.0)
            xform(hoop, Matrix.Translation(c))
            props.add(hoop, iron, uv=3)
    for a in (1.2, 4.4):
        rot = Matrix.Rotation(a, 4, "Z")
        for (sx, sy, sz, x, y, z) in ((0.08, 0.08, 1.4, 0, -0.8, 0.7), (0.08, 0.08, 1.4, 0, 0.8, 0.7),
                                      (0.08, 1.7, 0.08, 0, 0, 1.2), (0.3, 1.7, 0.06, 0.0, 0, 0.3)):
            bx = bm_box(sx, sy, sz, (0, 0, 0), 0.01, 1)
            xform(bx, rot @ Matrix.Translation((12.8 + x, y, z)))
            props.add(bx, wood, uv=2)
        for k in range(5):
            y = -0.6 + 0.3 * k
            shaft = bm_lathe([(0.018, 0.3), (0.018, 2.1)], 8)
            xform(shaft, rot @ Matrix.Translation((12.8, y, 0)) @ Matrix.Rotation(0.12, 4, "Y"))
            props.add(shaft, wood, uv=2)
            tipb = bm_lathe([(0.03, 2.1), (0.0, 2.35)], 8)
            xform(tipb, rot @ Matrix.Translation((12.8, y, 0)) @ Matrix.Rotation(0.12, 4, "Y"))
            props.add(tipb, iron, uv=3)
    props.build()

    # spectator (instanced by the game on the tiers)
    sp = Part("spectator")
    body = bm_lathe([(0.0, 0.0), (0.2, 0.02), (0.22, 0.4), (0.2, 0.6), (0.14, 0.7), (0.0, 0.72)], 8)
    deform(body, lambda c: (c[0], c[1] * 0.7, c[2]))
    sp.add(body, crowd_m, uv=1)
    sp.add(bm_ico(0.11, 1, (0, 0, 0.83)), crowd_m, uv=1)
    sp.build()

    # torch anchors as empties (exported as nodes)
    for i, p in enumerate(anchors):
        e = bpy.data.objects.new("fire_%02d" % i, None)
        e.location = p
        bpy.context.scene.collection.objects.link(e)
    export_glb(os.path.join(OUT, "arena.glb"))
    return tiers


def main():
    build_knight_file()
    build_sword_file()
    build_gore_file()
    tiers = build_arena_file()
    meta = {"arenaRadius": ARENA_R, "tiers": [[round(a, 3), round(b, 3)] for a, b in tiers[1:15:2]]}
    with open(os.path.join(OUT, "meta.json"), "w") as fh:
        json.dump(meta, fh)
    shutil.rmtree(TEX_DIR, ignore_errors=True)
    print("done")


if __name__ == "__main__":
    main()
