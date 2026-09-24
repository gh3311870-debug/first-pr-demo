"""Generate seamless (tileable) PBR textures for Frontline with numpy/scipy.

Outputs to assets/frontline/tex/:
  <name>_col.jpg  albedo (sRGB)
  <name>_nrm.jpg  tangent-space normal map (OpenGL convention, as three.js expects)
  <name>_orm.jpg  R = ambient occlusion, G = roughness, B = metalness
plus RGBA sprites/decals (.png).

All noise is built in the frequency domain or with periodic distance fields, so every
texture tiles without seams.

Usage: python3 make_textures.py <out_dir> [three_textures_dir]
"""
import os
import sys
import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage
from scipy.spatial import cKDTree

OUT = sys.argv[1]
THREE = sys.argv[2] if len(sys.argv) > 2 else None
os.makedirs(OUT, exist_ok=True)
N = 1024


def rng(seed):
    return np.random.default_rng(seed)


def fbm(n, beta=2.0, seed=0, lo=1.0, hi=None):
    """Spectral 1/f^beta noise, seamless, normalized to 0..1."""
    r = rng(seed)
    fx = np.fft.fftfreq(n)[:, None] * n
    fy = np.fft.fftfreq(n)[None, :] * n
    f = np.sqrt(fx * fx + fy * fy)
    f[0, 0] = 1
    amp = f ** (-beta / 2)
    amp[f < lo] = 0
    if hi:
        amp[f > hi] = 0
    phase = r.uniform(0, 2 * np.pi, (n, n))
    spec = amp * np.exp(1j * phase)
    img = np.real(np.fft.ifft2(spec))
    img -= img.min()
    img /= img.max() + 1e-9
    return img


def cells(n, count, seed=0, k=2):
    """Periodic Worley distances (F1, F2) for `count` feature points."""
    r = rng(seed)
    pts = r.uniform(0, n, (count, 2))
    tree = cKDTree(pts, boxsize=n)
    yy, xx = np.mgrid[0:n, 0:n]
    d, i = tree.query(np.stack([yy.ravel() + 0.5, xx.ravel() + 0.5], -1), k=k)
    return d[:, 0].reshape(n, n), d[:, 1].reshape(n, n), i[:, 0].reshape(n, n)


def blur(a, s):
    return ndimage.gaussian_filter(a, s, mode="wrap")


def normal_from_height(h, strength=4.0):
    dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 0.5 * strength
    dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 0.5 * strength
    nx, ny, nz = -dx, dy, np.ones_like(h)
    ln = np.sqrt(nx * nx + ny * ny + nz * nz)
    n = np.stack([nx / ln, ny / ln, nz / ln], -1)
    return (n * 0.5 + 0.5)


def ao_from_height(h, radius=6, amount=1.5):
    b = blur(h, radius)
    ao = 1 - np.clip((b - h) * amount, 0, 1)
    return np.clip(ao, 0, 1)


def colorize(t, stops):
    """Map 0..1 array through a list of (pos, (r,g,b)) sRGB stops (0..255)."""
    pos = np.array([s[0] for s in stops])
    cols = np.array([s[1] for s in stops], dtype=float)
    out = np.zeros(t.shape + (3,))
    for c in range(3):
        out[..., c] = np.interp(t, pos, cols[:, c])
    return out


def save_rgb(a, name, q=90):
    a = np.clip(a, 0, 255).astype(np.uint8)
    Image.fromarray(a).save(os.path.join(OUT, name), quality=q)


def save_set(name, col, height, rough, strength=4.0, metal=None, ao_amt=1.5, size=None):
    nrm = normal_from_height(height, strength)
    ao = ao_from_height(height, amount=ao_amt)
    orm = np.stack([ao, rough, np.zeros_like(rough) if metal is None else metal], -1)
    col = col * (0.75 + 0.25 * ao[..., None])
    imgs = [(col, "_col.jpg"), (nrm * 255, "_nrm.jpg"), (orm * 255, "_orm.jpg")]
    for arr, suf in imgs:
        a = np.clip(arr, 0, 255).astype(np.uint8)
        im = Image.fromarray(a)
        if size:
            im = im.resize((size, size), Image.LANCZOS)
        im.save(os.path.join(OUT, name + suf), quality=90)
    print("wrote", name)


def speckle(n, density, seed, radius=1.0):
    r = rng(seed)
    m = (r.random((n, n)) < density).astype(float)
    return blur(m, radius) * (radius * radius * 6)


# --------------------------------------------------------------------------------------
def sand():
    low = fbm(N, 3.2, 1)
    mid = fbm(N, 2.2, 2)
    grain = rng(3).random((N, N))
    grain = blur(grain, 0.6)
    # wind ripples (periodic: integer frequency along a skewed axis)
    yy, xx = np.mgrid[0:N, 0:N] / N
    warp = fbm(N, 3.0, 4) * 0.08
    ripples = 0.5 + 0.5 * np.sin(2 * np.pi * (14 * yy + 3 * xx + warp * 6))
    ripples = ripples ** 3
    peb_f1, peb_f2, _ = cells(N, 900, 5)
    pebbles = np.clip(1 - peb_f1 / 5.0, 0, 1) ** 1.5
    pebbles *= (fbm(N, 2.5, 6) > 0.55)
    h = 0.35 * low + 0.25 * mid + 0.12 * grain + 0.18 * ripples * (0.5 + low) + 0.5 * pebbles
    t = 0.55 * low + 0.3 * mid + 0.15 * grain
    col = colorize(t, [(0.0, (150, 118, 84)), (0.45, (186, 152, 112)), (0.75, (204, 172, 128)),
                       (1.0, (214, 186, 144))])
    peb_col = colorize(fbm(N, 1.5, 7), [(0, (95, 85, 75)), (0.5, (140, 124, 104)), (1, (170, 150, 125))])
    k = np.clip(pebbles * 2, 0, 1)[..., None]
    col = col * (1 - k) + peb_col * k
    col *= (0.92 + 0.16 * grain[..., None])
    rough = np.clip(0.88 + 0.1 * grain - 0.15 * pebbles, 0, 1)
    save_set("sand", col, h, rough, strength=5.0)


def dirt():
    low = fbm(N, 3.0, 11)
    mid = fbm(N, 2.0, 12)
    f1, f2, idx = cells(N, 2500, 13)
    gravel = np.clip(1 - f1 / 7.0, 0, 1)
    gravel_mask = fbm(N, 2.2, 14) > 0.4
    stones = gravel * gravel_mask
    grain = blur(rng(15).random((N, N)), 0.7)
    h = 0.4 * low + 0.2 * mid + 0.55 * stones ** 0.7 + 0.1 * grain
    col = colorize(0.6 * low + 0.4 * mid, [(0, (98, 80, 62)), (0.5, (128, 106, 82)), (1, (156, 132, 102))])
    stone_tone = (rng(16).random(2500)[idx] * 0.5 + 0.6)[..., None]
    stone_col = np.array([150, 138, 124]) * stone_tone
    k = np.clip(stones * 1.8, 0, 1)[..., None]
    col = col * (1 - k) + stone_col * k
    col *= (0.9 + 0.2 * grain[..., None])
    rough = np.clip(0.9 - 0.2 * stones + 0.05 * grain, 0, 1)
    save_set("dirt", col, h, rough, strength=6.0)


def plaster():
    low = fbm(N, 3.5, 21)
    mid = fbm(N, 2.4, 22)
    fine = blur(rng(23).random((N, N)), 0.8)
    # trowel strokes: stretched noise
    strokes = blur(rng(24).random((N, N)), (2, 18))
    strokes = (strokes - strokes.min()) / (strokes.ptp() + 1e-9)
    # hairline cracks along Worley cell borders, only in some regions
    f1, f2, _ = cells(N, 60, 25)
    crack = np.clip(1 - (f2 - f1) / 2.2, 0, 1) * (fbm(N, 2.5, 26) > 0.62)
    # chipped patches exposing mud brick
    chips = (fbm(N, 2.8, 27) > 0.8).astype(float)
    chips = blur(chips, 1.5)
    h = 0.3 * low + 0.25 * strokes + 0.2 * fine + 0.2 * mid - 0.5 * crack - 0.35 * chips
    t = 0.5 * low + 0.3 * mid + 0.2 * strokes
    col = colorize(t, [(0, (164, 140, 108)), (0.5, (192, 170, 136)), (1, (212, 194, 160))])
    stain = fbm(N, 3.8, 28)
    col *= (0.85 + 0.2 * stain[..., None])
    brick = np.array([140, 100, 70])
    col = col * (1 - chips[..., None] * 0.8) + brick * chips[..., None] * 0.8
    col *= (1 - 0.5 * crack[..., None])
    col *= (0.94 + 0.1 * fine[..., None])
    rough = np.clip(0.9 + 0.08 * fine - 0.05 * low, 0, 1)
    save_set("plaster", col, h, rough, strength=3.5)


def concrete():
    low = fbm(N, 3.4, 31)
    mid = fbm(N, 2.2, 32)
    fine = blur(rng(33).random((N, N)), 0.7)
    pores = speckle(N, 0.0025, 34, 1.2)
    agg_f1, _, agg_i = cells(N, 3000, 35)
    agg = np.clip(1 - agg_f1 / 6, 0, 1) * (rng(36).random(3000)[agg_i] > 0.6)
    h = 0.35 * low + 0.2 * mid + 0.15 * fine - 0.6 * np.clip(pores, 0, 1) + 0.1 * agg
    t = 0.5 * low + 0.35 * mid + 0.15 * fine
    col = colorize(t, [(0, (118, 114, 108)), (0.5, (150, 146, 138)), (1, (176, 172, 164))])
    stains = fbm(N, 4.0, 37)
    streak = blur(rng(38).random((N, N)), (40, 1.5))
    streak = (streak - streak.min()) / streak.ptp()
    col *= (0.82 + 0.18 * stains[..., None]) * (0.92 + 0.12 * streak[..., None])
    col *= (1 - 0.4 * np.clip(pores, 0, 1)[..., None])
    col += agg[..., None] * 12
    rough = np.clip(0.85 + 0.1 * fine, 0, 1)
    save_set("concrete", col, h, rough, strength=3.0)


def paint_metal():
    """Painted steel (white base - tinted per object in the game) with rust and scratches."""
    low = fbm(N, 3.2, 41)
    mid = fbm(N, 2.3, 42)
    fine = blur(rng(43).random((N, N)), 0.6)
    rust_mask = np.clip((fbm(N, 2.6, 44) * 0.7 + mid * 0.3 - 0.62) * 6, 0, 1)
    # vertical rust streaks
    streak = blur(rng(45).random((N, N)), (60, 1.2))
    streak = np.clip((streak - streak.mean()) / streak.std() * 0.5, 0, 1) * 0.6
    scratches = np.zeros((N, N))
    r = rng(46)
    for _ in range(260):
        x, y = r.integers(0, N, 2)
        ang = r.uniform(0, np.pi)
        ln = r.integers(10, 80)
        for s in range(ln):
            px = int(x + np.cos(ang) * s) % N
            py = int(y + np.sin(ang) * s) % N
            scratches[py, px] = 1
    scratches = blur(scratches, 0.5) * 3
    scratches = np.clip(scratches, 0, 1)
    rust = np.clip(rust_mask + streak * (0.3 + rust_mask), 0, 1)
    paint = colorize(0.6 * low + 0.4 * fine, [(0, (196, 196, 192)), (1, (236, 236, 232))])
    rust_col = colorize(fbm(N, 2.0, 47), [(0, (70, 38, 22)), (0.5, (120, 64, 32)), (1, (150, 90, 50))])
    col = paint * (1 - rust[..., None]) + rust_col * rust[..., None]
    col = col * (1 - scratches[..., None] * 0.6) + np.array([90, 90, 92]) * scratches[..., None] * 0.6
    h = 0.3 * low + 0.4 * rust * fbm(N, 1.5, 48) - 0.3 * scratches + 0.1 * fine
    rough = np.clip(0.45 + 0.45 * rust + 0.1 * fine - 0.1 * scratches, 0, 1)
    metal = np.clip(0.25 * (1 - rust) + 0.7 * scratches, 0, 1)
    save_set("paint", col, h, rough, strength=2.5, metal=metal)


def burnt():
    low = fbm(N, 2.8, 51)
    mid = fbm(N, 2.0, 52)
    fine = blur(rng(53).random((N, N)), 0.6)
    t = 0.6 * low + 0.4 * mid
    col = colorize(t, [(0, (18, 14, 12)), (0.35, (40, 26, 18)), (0.6, (96, 52, 26)),
                       (0.8, (140, 80, 40)), (1, (160, 120, 90))])
    col *= (0.85 + 0.3 * fine[..., None])
    h = 0.5 * low + 0.3 * mid + 0.2 * fine
    rough = np.clip(0.75 + 0.2 * fine, 0, 1)
    save_set("burnt", col, h, rough, strength=5.0, metal=np.clip(0.4 - 0.4 * t, 0, 1))


def burlap(name="burlap", base=((120, 98, 66), (170, 142, 100)), seed=61):
    n = 512
    yy, xx = np.mgrid[0:n, 0:n] / n
    freq = 48
    wx = np.sin(2 * np.pi * freq * xx + 0.6 * np.sin(2 * np.pi * 4 * yy))
    wy = np.sin(2 * np.pi * freq * yy + 0.6 * np.sin(2 * np.pi * 5 * xx))
    checker = np.sign(np.sin(np.pi * freq * xx) * np.sin(np.pi * freq * yy))
    weave = np.where(checker > 0, np.abs(wx), np.abs(wy))
    fuzz = blur(rng(seed).random((n, n)), 0.8)
    low = fbm(n, 3.0, seed + 1)
    dirt_ = fbm(n, 3.5, seed + 2)
    h = 0.55 * weave + 0.2 * fuzz + 0.25 * low
    col = colorize(0.5 * low + 0.3 * weave + 0.2 * fuzz, [(0, base[0]), (1, base[1])])
    col *= (0.75 + 0.3 * dirt_[..., None])
    rough = np.full((n, n), 0.95)
    nrm = normal_from_height(h, 5.0)
    ao = ao_from_height(h, 2, 1.2)
    save_rgb(col * (0.8 + 0.2 * ao[..., None]), name + "_col.jpg")
    save_rgb(nrm * 255, name + "_nrm.jpg")
    save_rgb(np.stack([ao, rough, np.zeros_like(rough)], -1) * 255, name + "_orm.jpg")
    print("wrote", name)


def hesco():
    """Geotextile bag behind a welded wire mesh. 1024 px = 1 m; mesh pitch 76 mm."""
    n = N
    yy, xx = np.mgrid[0:n, 0:n] / n
    pitch = 13  # cells per tile
    gx = np.abs(((xx * pitch) % 1) - 0.5)
    gy = np.abs(((yy * pitch) % 1) - 0.5)
    wire = np.clip((np.maximum(gx, gy) - 0.47) * 40, 0, 1)
    fab = fbm(n, 2.6, 71)
    fine = blur(rng(72).random((n, n)), 0.8)
    weave = 0.5 + 0.5 * np.sin(2 * np.pi * 300 * xx) * np.sin(2 * np.pi * 300 * yy)
    bulge = (1 - (gx * 2) ** 2) * (1 - (gy * 2) ** 2)
    h = 0.4 * bulge + 0.2 * fab + 0.1 * fine + 0.05 * weave + 0.8 * wire
    col = colorize(0.6 * fab + 0.4 * fine, [(0, (150, 128, 96)), (1, (196, 174, 136))])
    dust = fbm(n, 3.5, 73)
    col *= (0.8 + 0.25 * dust[..., None])
    wire_col = np.array([120, 118, 110])
    col = col * (1 - wire[..., None]) + wire_col * wire[..., None]
    rough = np.clip(0.95 - 0.5 * wire, 0, 1)
    metal = wire * 0.8
    save_set("hesco", col, h, rough, strength=3.0, metal=metal, size=512)


def bark():
    n = 512
    yy, xx = np.mgrid[0:n, 0:n] / n
    # diamond leaf-base scars of a date palm
    u = xx * 8 + yy * 4
    v = xx * 8 - yy * 4
    d = np.abs((u % 1) - 0.5) + np.abs((v % 1) - 0.5)
    scale = np.clip(1 - d * 1.6, 0, 1)
    fib = blur(rng(81).random((n, n)), (6, 0.6))
    fib = (fib - fib.min()) / fib.ptp()
    low = fbm(n, 3.0, 82)
    h = 0.6 * scale + 0.3 * fib + 0.2 * low
    col = colorize(0.5 * scale + 0.3 * fib + 0.2 * low,
                   [(0, (58, 44, 32)), (0.5, (104, 84, 62)), (1, (140, 118, 92))])
    nrm = normal_from_height(h, 6.0)
    ao = ao_from_height(h, 3, 1.5)
    save_rgb(col * (0.7 + 0.3 * ao[..., None]), "bark_col.jpg")
    save_rgb(nrm * 255, "bark_nrm.jpg")
    print("wrote bark")


def palm_leaf():
    """RGBA frond: rachis along V with angled leaflets; alpha-tested in the game."""
    w, hgt = 256, 1024
    img = np.zeros((hgt, w, 4))
    yy, xx = np.mgrid[0:hgt, 0:w]
    u = xx / w - 0.5
    v = 1 - yy / hgt  # 0 at base, 1 at tip
    rachis = np.abs(u) < 0.02 * (1.2 - v)
    # leaflets: thin stripes angled toward the tip
    phase = (np.abs(u) * 2.6 + v * 26) % 1
    leaflet = (phase < 0.62) & (np.abs(u) < 0.5 * np.sin(np.pi * np.clip(v * 1.05, 0, 1)) + 0.02) & (v > 0.1)
    shade = 0.75 + 0.25 * np.cos(phase * np.pi * 2)
    base = np.array([62, 84, 38]) / 255
    tip_dry = np.array([150, 132, 80]) / 255
    k = np.clip((v - 0.7) * 3 + np.abs(u) * 0.8, 0, 1)[..., None] * 0.7
    col = (base * (1 - k) + tip_dry * k) * shade[..., None]
    col[rachis] = np.array([120, 110, 70]) / 255
    alpha = (leaflet | rachis).astype(float)
    img[..., :3] = col
    img[..., 3] = alpha
    Image.fromarray((img * 255).astype(np.uint8), "RGBA").save(os.path.join(OUT, "palm_leaf.png"))
    print("wrote palm_leaf")


def shrub():
    """Dry desert bush sprite (RGBA) made from random branching strokes."""
    n = 512
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    from PIL import ImageDraw
    d = ImageDraw.Draw(img)
    r = rng(91)

    def branch(x, y, ang, ln, width, depth):
        if depth == 0 or ln < 6:
            if r.random() < 0.8:
                c = tuple(int(v) for v in r.choice([[96, 104, 58], [120, 118, 70], [140, 126, 84], [84, 90, 50]]))
                rr = r.integers(4, 10)
                d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=c + (255,))
            return
        x2 = x + np.cos(ang) * ln
        y2 = y - np.sin(ang) * ln
        tone = int(70 + r.integers(0, 40))
        d.line([x, y, x2, y2], fill=(tone, tone - 14, tone - 30, 255), width=max(1, int(width)))
        for _ in range(r.integers(2, 4)):
            branch(x2, y2, ang + r.uniform(-0.7, 0.7), ln * r.uniform(0.6, 0.8), width * 0.7, depth - 1)

    for _ in range(9):
        branch(n / 2 + r.uniform(-30, 30), n - 4, np.pi / 2 + r.uniform(-0.9, 0.9), r.uniform(70, 120), 5, 6)
    img.save(os.path.join(OUT, "shrub.png"))
    print("wrote shrub")


def decals():
    n = 128
    yy, xx = np.mgrid[0:n, 0:n] / n - 0.5
    rr = np.sqrt(xx * xx + yy * yy)
    ang = np.arctan2(yy, xx)
    # bullet hole: dark core, torn ring, radial cracks, dusty halo
    jag = 1 + 0.25 * np.sin(ang * 7) * np.sin(ang * 3 + 1)
    core = rr < 0.07 * jag
    ring = (rr < 0.13 * jag) & ~core
    cracks = (np.abs(np.sin(ang * 5 + 0.4)) > 0.985) & (rr < 0.35)
    halo = np.clip(1 - rr / 0.45, 0, 1) ** 2
    rgba = np.zeros((n, n, 4))
    rgba[..., :3] = 0.35
    rgba[..., 3] = halo * 0.45
    rgba[ring, :3] = 0.18
    rgba[ring, 3] = 0.9
    rgba[cracks, :3] = 0.15
    rgba[cracks, 3] = 0.8
    rgba[core, :3] = 0.03
    rgba[core, 3] = 1.0
    Image.fromarray((rgba * 255).astype(np.uint8), "RGBA").save(os.path.join(OUT, "bullethole.png"))
    # blood splat
    r = rng(101)
    n2 = 256
    m = np.zeros((n2, n2))
    for _ in range(40):
        cx, cy = r.normal(n2 / 2, n2 / 9, 2)
        rad = abs(r.normal(10, 7))
        yy2, xx2 = np.mgrid[0:n2, 0:n2]
        m = np.maximum(m, (((xx2 - cx) ** 2 + (yy2 - cy) ** 2) < rad * rad).astype(float))
    for _ in range(120):
        a = r.uniform(0, 2 * np.pi)
        dist = r.uniform(30, 120)
        cx, cy = n2 / 2 + np.cos(a) * dist, n2 / 2 + np.sin(a) * dist
        rad = r.uniform(1, 4)
        yy2, xx2 = np.mgrid[0:n2, 0:n2]
        m = np.maximum(m, (((xx2 - cx) ** 2 + (yy2 - cy) ** 2) < rad * rad).astype(float))
    m = ndimage.gaussian_filter(m, 1.0)
    rgba = np.zeros((n2, n2, 4))
    rgba[..., 0] = 0.32 + 0.1 * m
    rgba[..., 1] = 0.02
    rgba[..., 2] = 0.02
    rgba[..., 3] = np.clip(m * 1.4, 0, 0.95)
    Image.fromarray((rgba * 255).astype(np.uint8), "RGBA").save(os.path.join(OUT, "blood.png"))
    # muzzle flash (side-on star + core), additive
    n3 = 256
    yy, xx = np.mgrid[0:n3, 0:n3] / n3 - 0.5
    rr = np.sqrt(xx * xx + yy * yy)
    ang = np.arctan2(yy, xx)
    spikes = np.clip(np.cos(ang * 4) ** 16, 0, 1) * np.clip(1 - rr / 0.5, 0, 1)
    spikes += np.clip(np.cos(ang * 4 + np.pi / 4) ** 30, 0, 1) * np.clip(1 - rr / 0.35, 0, 1) * 0.6
    core = np.clip(1 - rr / 0.16, 0, 1) ** 1.5
    inten = np.clip(core + spikes * 0.9, 0, 1)
    rgba = np.zeros((n3, n3, 4))
    rgba[..., 0] = 1.0
    rgba[..., 1] = 0.75 * inten + 0.2
    rgba[..., 2] = 0.35 * inten ** 2
    rgba[..., 3] = inten
    Image.fromarray((rgba * 255).astype(np.uint8), "RGBA").save(os.path.join(OUT, "flash.png"))
    # soft round particle
    n4 = 64
    yy, xx = np.mgrid[0:n4, 0:n4] / n4 - 0.5
    rr = np.sqrt(xx * xx + yy * yy)
    a = np.clip(1 - rr / 0.5, 0, 1) ** 2
    rgba = np.stack([np.ones_like(a), np.ones_like(a), np.ones_like(a), a], -1)
    Image.fromarray((rgba * 255).astype(np.uint8), "RGBA").save(os.path.join(OUT, "soft.png"))
    print("wrote decals")


def copy_three():
    """Resize the three.js example textures we use (brick, hardwood, smoke) to web sizes."""
    if not THREE:
        return
    jobs = [("brick_diffuse.jpg", "brick_col.jpg", 1024), ("brick_bump.jpg", "brick_bump.jpg", 1024),
            ("brick_roughness.jpg", "brick_rough.jpg", 512), ("hardwood2_diffuse.jpg", "wood_col.jpg", 1024),
            ("hardwood2_bump.jpg", "wood_bump.jpg", 512), ("hardwood2_roughness.jpg", "wood_rough.jpg", 512),
            ("opengameart/smoke1.png", "smoke.png", 256)]
    for src, dst, size in jobs:
        im = Image.open(os.path.join(THREE, src))
        im.thumbnail((size, size), Image.LANCZOS)
        if dst.endswith(".jpg"):
            im = im.convert("RGB")
            im.save(os.path.join(OUT, dst), quality=88)
        else:
            im.save(os.path.join(OUT, dst))
        print("copied", dst)


if __name__ == "__main__":
    which = sys.argv[3].split(",") if len(sys.argv) > 3 else None
    for fn in (sand, dirt, plaster, concrete, paint_metal, burnt, burlap, hesco, bark, palm_leaf, shrub,
               decals, copy_three):
        if which is None or fn.__name__ in which:
            fn()
