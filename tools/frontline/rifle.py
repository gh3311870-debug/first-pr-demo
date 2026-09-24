"""Procedural M4-style carbine built from primitives, booleans and bevels in Blender.

Units are meters. Muzzle points +Y, top is +Z. The bore axis is at z = 0.055.
Returns a root empty "Rifle" with children:
  RifleBody  - receiver, handguard, barrel, stock, optic (joined, several materials)
  Mag        - magazine (separate so the game can animate reloads)
  Muzzle     - empty at the flash hider exit
  SightAxis  - empty on the optic's axis (eye position for aiming down sights)
  GripR/GripL - empties where the right and left hands hold the rifle
  Eject      - empty at the ejection port
"""
import math
from mathutils import Vector
import bpy
from mathutils import Matrix
import blender_util as U

BORE_Z = 0.055


VARIANTS = {
    # M4A1 carbine: 14.5" barrel, red dot, curved 30-round mag
    "m4": dict(hg_end=0.43, barrel_end=0.505, muzzle_end=0.558, optic="reddot", mag_len=0.175,
               mag_bend=18, mag_half=0.0112, afg=True, bipod=False, finish="black"),
    # DMR (SR-25 style): 20" barrel, 3-9x scope, 20-round 7.62 box mag, folded bipod
    "dmr": dict(hg_end=0.53, barrel_end=0.625, muzzle_end=0.68, optic="scope", mag_len=0.125,
                mag_bend=5, mag_half=0.0128, afg=False, bipod=True, finish="tan"),
}


def materials(finish="black"):
    metal = (U.material("Rifle_Anodized", (0.028, 0.028, 0.03), metallic=0.75, roughness=0.42) if finish == "black"
             else U.material("Rifle_Cerakote", (0.13, 0.1, 0.068), metallic=0.2, roughness=0.6))
    return {
        "metal": metal,
        "steel": U.material("Rifle_Steel", (0.05, 0.05, 0.052), metallic=1.0, roughness=0.33),
        "polymer": U.material("Rifle_Polymer", (0.03, 0.03, 0.03), metallic=0.0, roughness=0.62),
        "fde": U.material("Rifle_FDE", (0.16, 0.115, 0.07), metallic=0.0, roughness=0.7),
        "rubber": U.material("Rifle_Rubber", (0.02, 0.02, 0.02), metallic=0.0, roughness=0.9),
        "glass": U.material("Rifle_Glass", (0.25, 0.35, 0.4), metallic=0.2, roughness=0.05, alpha=0.25),
        "reticle": U.material("Rifle_Reticle", (1.0, 0.1, 0.05), emissive=(1.0, 0.05, 0.02)),
    }


def rail(name, y0, y1, z_base, mat, width=0.021, x=0.0, axis="top"):
    """Picatinny rail: base plus 10 mm pitch teeth."""
    parts = []
    parts.append(U.box_span(name + "_base", (x - width / 2, x + width / 2), (y0, y1),
                            (z_base, z_base + 0.006), mat))
    y = y0 + 0.003
    while y + 0.0053 < y1:
        parts.append(U.box_span(name + "_tooth", (x - width / 2 - 0.0015, x + width / 2 + 0.0015),
                                (y, y + 0.0053), (z_base + 0.006, z_base + 0.0095), mat))
        y += 0.01
    for p in parts:
        U.bevel(p, 0.0006, 1)
    return parts


def build(prefix="", detail=True, variant="m4"):
    C = VARIANTS[variant]
    M = materials(C["finish"])
    HG = C["hg_end"]
    parts = []
    add = parts.append

    # --- Upper receiver --------------------------------------------------------
    upper = U.box_span("upper", (-0.0135, 0.0135), (-0.085, 0.105), (0.030, 0.078), M["metal"])
    U.bevel(upper, 0.0025, 2)
    add(upper)
    parts += rail("upper_rail", -0.085, 0.105, 0.078, M["metal"])
    # ejection port cover (right side, slightly proud) and brass deflector
    add(U.box_span("port_cover", (0.0135, 0.0152), (0.0, 0.068), (0.045, 0.071), M["steel"]))
    deflector = U.box_span("deflector", (0.0135, 0.021), (-0.012, 0.004), (0.050, 0.074), M["metal"])
    U.bevel(deflector, 0.002, 2)
    add(deflector)
    # forward assist
    add(U.cylinder("fwd_assist", 0.0065, -0.045, -0.012, M["metal"], x=0.018, z=0.066, verts=16))
    add(U.cylinder("fwd_assist_cap", 0.0075, -0.012, -0.004, M["steel"], x=0.018, z=0.066, verts=16))
    # charging handle
    ch = U.box_span("charging_handle", (-0.024, 0.024), (-0.098, -0.084), (0.066, 0.077), M["polymer"])
    U.bevel(ch, 0.002, 2)
    add(ch)

    # --- Lower receiver ----------------------------------------------------------
    lower = U.box_span("lower", (-0.013, 0.013), (-0.08, 0.02), (-0.005, 0.030), M["metal"])
    U.bevel(lower, 0.002, 2)
    add(lower)
    magwell = U.prism("magwell", [(0.02, 0.030), (0.088, 0.030), (0.090, -0.040),
                                   (0.018, -0.040)], 0.0155, M["metal"])
    U.bevel(magwell, 0.0025, 2)
    magwell_cut = U.box_span("magwell_cut", (-0.0118, 0.0118), (0.026, 0.083), (-0.06, 0.02), None)
    U.subtract(magwell, [magwell_cut])
    add(magwell)
    add(magwell_cut)
    # mag release + bolt catch
    add(U.cylinder("mag_release", 0.004, 0.013, 0.0165, M["steel"], y=0.012, z=0.012, axis="X", verts=12))
    add(U.box_span("bolt_catch", (-0.0158, -0.0130), (0.004, 0.022), (0.018, 0.034), M["steel"]))
    # selector
    add(U.cylinder("selector", 0.0055, -0.0165, -0.013, M["steel"], y=-0.062, z=0.018, axis="X", verts=16))
    add(U.box_span("selector_lever", (-0.0185, -0.0165), (-0.070, -0.052), (0.016, 0.021), M["steel"]))

    # trigger guard and trigger
    tg = U.prism("trigger_guard", [(0.018, -0.005), (0.018, -0.036), (-0.04, -0.036),
                                   (-0.04, -0.030), (0.012, -0.030), (0.012, -0.005)],
                 0.004, M["metal"])
    U.bevel(tg, 0.0012, 1)
    add(tg)
    trig = U.prism("trigger", [(-0.004, -0.004), (0.001, -0.004), (-0.004, -0.020),
                               (-0.010, -0.026), (-0.012, -0.024), (-0.007, -0.016)],
                   0.0025, M["steel"])
    add(trig)

    # pistol grip (FDE polymer)
    grip = U.prism("grip", [(-0.036, -0.003), (-0.078, -0.003), (-0.118, -0.104),
                            (-0.112, -0.114), (-0.086, -0.116), (-0.070, -0.100),
                            (-0.047, -0.030), (-0.040, -0.018)], 0.0145, M["fde"])
    U.bevel(grip, 0.006, 3, angle=25)
    add(grip)

    # --- Stock -------------------------------------------------------------------
    add(U.cylinder("buffer_tube", 0.0145, -0.08, -0.29, M["metal"], z=0.045, verts=24))
    add(U.cylinder("castle_nut", 0.017, -0.088, -0.080, M["steel"], z=0.045, verts=12))
    stock = U.prism("stock", [(-0.200, 0.066), (-0.326, 0.071), (-0.332, -0.034),
                              (-0.314, -0.040), (-0.262, -0.004), (-0.226, 0.020),
                              (-0.205, 0.036)], 0.0175, M["fde"])
    stock_cut = U.prism("stock_cut", [(-0.232, 0.052), (-0.300, 0.054), (-0.305, 0.004),
                                      (-0.270, 0.024), (-0.240, 0.036)], 0.03, None)
    U.subtract(stock, [stock_cut])
    parts.append(stock_cut)
    U.bevel(stock, 0.005, 3, angle=25)
    add(stock)
    pad = U.prism("butt_pad", [(-0.333, 0.078), (-0.348, 0.078), (-0.350, -0.044),
                               (-0.334, -0.044)], 0.0205, M["rubber"])
    U.bevel(pad, 0.005, 3)
    add(pad)
    add(U.box_span("sling_loop", (-0.004, 0.004), (-0.27, -0.24), (-0.018, 0.002), M["steel"]))

    # --- Handguard (free-float, M-LOK slots) ------------------------------------
    hg = U.cylinder("handguard", 0.024, 0.105, HG, M["metal"], z=BORE_Z, verts=8)
    hg.rotation_euler[1] = math.radians(22.5)  # flat on top/bottom
    cutters = []
    if detail:
        for i in range(int((HG - 0.15) / 0.056)):
            y0 = 0.14 + i * 0.056
            for side in (-1, 1):
                c = U.box_span("mlok_cut", (side * 0.018 - 0.012, side * 0.018 + 0.012),
                               (y0, y0 + 0.032), (BORE_Z - 0.0045, BORE_Z + 0.0045), None)
                cutters.append(c)
            c = U.box_span("mlok_cut", (-0.0045, 0.0045), (y0, y0 + 0.032),
                           (BORE_Z - 0.035, BORE_Z - 0.015), None)
            cutters.append(c)
        U.subtract(hg, cutters)
    U.bevel(hg, 0.0015, 1)
    add(hg)
    parts += cutters
    parts += rail("hg_rail", 0.108, HG, BORE_Z + 0.023, M["metal"])
    # dark inner barrel visible through the slots
    add(U.cylinder("inner_barrel", 0.0095, 0.105, HG, M["steel"], z=BORE_Z, verts=16))

    # --- Barrel + flash hider -----------------------------------------------------
    BE, ME = C["barrel_end"], C["muzzle_end"]
    add(U.cylinder("barrel", 0.0095, HG, BE, M["steel"], z=BORE_Z, verts=20))
    fh = U.cylinder("flash_hider", 0.0112 if variant == "m4" else 0.0125, BE, ME, M["steel"], z=BORE_Z, verts=20)
    fh_cuts = []
    if detail:
        for a in range(3):
            ang = math.radians(90 + a * 120)
            c = U.box("fh_cut", (0.0035, 0.034, 0.012),
                      (math.cos(ang) * 0.011, ME - 0.021, BORE_Z + math.sin(ang) * 0.011), None,
                      rot=(0, 90 - math.degrees(ang), 0))
            fh_cuts.append(c)
        bore = U.cylinder("fh_bore", 0.0055, BE + 0.015, ME + 0.012, None, z=BORE_Z, verts=16)
        fh_cuts.append(bore)
        U.subtract(fh, fh_cuts)
    add(fh)
    parts += fh_cuts

    # folded back-up iron sights
    for yy, nm in ((HG - 0.025, "fbuis"), (-0.07, "rbuis")):
        b = U.box_span(nm, (-0.011, 0.011), (yy - 0.012, yy + 0.012), (0.088, 0.1), M["polymer"])
        U.bevel(b, 0.002, 1)
        add(b)
    if C["afg"]:
        # angled foregrip
        afg = U.prism("afg", [(0.225, BORE_Z - 0.024), (0.315, BORE_Z - 0.024),
                              (0.300, BORE_Z - 0.045), (0.255, BORE_Z - 0.050)], 0.012, M["polymer"])
        U.bevel(afg, 0.004, 2)
        add(afg)
    if C["bipod"]:
        # folded bipod: clamp under the front of the handguard, legs folded back along it
        add(U.box_span("bipod_clamp", (-0.016, 0.016), (HG - 0.06, HG - 0.02), (BORE_Z - 0.038, BORE_Z - 0.022), M["metal"]))
        for side in (-1, 1):
            add(U.cylinder("bipod_leg", 0.0055, HG - 0.05, HG - 0.23, M["polymer"], x=side * 0.011, z=BORE_Z - 0.042, verts=10))
            add(U.cylinder("bipod_foot", 0.008, HG - 0.235, HG - 0.215, M["rubber"], x=side * 0.011, z=BORE_Z - 0.042, verts=10))

    if C["optic"] == "reddot":
        OZ = 0.125
        # --- Red dot optic ---------------------------------------------------------
        mount = U.prism("optic_mount", [(-0.005, 0.088), (0.055, 0.088), (0.050, 0.104),
                                        (0.000, 0.104)], 0.012, M["metal"])
        U.bevel(mount, 0.002, 1)
        add(mount)
        add(U.box_span("mount_riser", (-0.008, 0.008), (0.005, 0.045), (0.100, 0.110), M["metal"]))
        tube = U.cylinder("optic_tube", 0.0195, -0.012, 0.072, M["metal"], z=OZ, verts=32)
        tube_cut = U.cylinder("optic_bore", 0.0165, -0.02, 0.08, None, z=OZ, verts=32)
        U.subtract(tube, [tube_cut])
        add(tube)
        add(tube_cut)
        for nm, a0, a1 in (("optic_ring_f", 0.060, 0.074), ("optic_ring_r", -0.014, -0.002)):
            ring = U.cylinder(nm, 0.0215, a0, a1, M["metal"], z=OZ, verts=32)
            ring_cut = U.cylinder(nm + "_cut", 0.0168, a0 - 0.01, a1 + 0.01, None, z=OZ, verts=32)
            U.subtract(ring, [ring_cut])
            add(ring)
            add(ring_cut)
        add(U.cylinder("turret_top", 0.009, OZ + 0.017, OZ + 0.029, M["metal"], y=0.03, axis="Z", verts=16))
        add(U.cylinder("turret_side", 0.009, 0.0175, 0.0295, M["metal"], y=0.03, z=OZ, axis="X", verts=16))


    else:
        # --- 3-9x rifle scope on high rings ------------------------------------------
        OZ = 0.132
        for ry in (-0.02, 0.09):
            ring = U.box_span("scope_ring_base", (-0.012, 0.012), (ry - 0.011, ry + 0.011), (0.0875, 0.115), M["metal"])
            U.bevel(ring, 0.002, 1)
            add(ring)
            add(U.cylinder("scope_ring", 0.0178, ry - 0.011, ry + 0.011, M["metal"], z=OZ, verts=28))
        tube = U.cylinder("scope_tube", 0.0152, -0.07, 0.15, M["polymer"], z=OZ, verts=28)
        add(tube)
        add(U.cylinder("scope_objective", 0.0152, 0.15, 0.2, M["polymer"], z=OZ, verts=32, radius2=0.0245))
        add(U.cylinder("scope_objective_rim", 0.0255, 0.2, 0.235, M["polymer"], z=OZ, verts=32))
        add(U.cylinder("scope_eyepiece", 0.0215, -0.135, -0.07, M["rubber"], z=OZ, verts=32, radius2=0.0152))
        add(U.cylinder("scope_power_ring", 0.019, -0.07, -0.045, M["polymer"], z=OZ, verts=32))
        add(U.cylinder("scope_turret_top", 0.011, OZ + 0.014, OZ + 0.034, M["metal"], y=0.035, axis="Z", verts=20))
        add(U.cylinder("scope_turret_side", 0.011, 0.014, 0.034, M["metal"], y=0.035, z=OZ, axis="X", verts=20))
        add(U.cylinder("scope_parallax", 0.009, -0.034, -0.014, M["metal"], y=0.035, z=OZ, axis="X", verts=16))

    body = U.join(parts, prefix + "RifleBody")

    # lenses and reticle stay separate so the game can give them special materials
    if C["optic"] == "reddot":
        lens = U.cylinder(prefix + "Lens", 0.0166, 0.050, 0.052, M["glass"], z=OZ, verts=32)
        reticle = U.cylinder(prefix + "Reticle", 0.0009, 0.049, 0.0495, M["reticle"], z=OZ, verts=12)
    else:
        lens = U.cylinder(prefix + "Lens", 0.0235, 0.231, 0.233, M["glass"], z=OZ, verts=32)
        reticle = U.cylinder(prefix + "LensRear", 0.0195, -0.133, -0.131, M["glass"], z=OZ, verts=32)
    U.smooth_by_angle(lens)

    # --- Magazine (curved STANAG polymer mag) ---------------------------------------
    ML, MH = C["mag_len"], C["mag_half"]
    mag = U.box_span(prefix + "Mag", (-MH, MH), (0.027, 0.083), (-ML, 0.012), M["fde"] if variant == "m4" else M["polymer"])
    U.bevel(mag, 0.0025, 2)
    # a few ribs near the base for grip
    ribs = []
    for i in range(3):
        r = U.box_span("mag_rib", (-MH - 0.001, MH + 0.001), (0.029, 0.081),
                       (-ML + 0.045 - i * 0.012, -ML + 0.049 - i * 0.012), mag.data.materials[0])
        ribs.append(r)
    floor = U.box_span("mag_floor", (-MH - 0.0023, MH + 0.0023), (0.024, 0.090), (-ML - 0.011, -ML + 0.003), mag.data.materials[0])
    U.bevel(floor, 0.003, 2)
    mag = U.join([mag] + ribs + [floor], prefix + "Mag")
    mag_bend = U.bend(mag, C["mag_bend"], axis="Z")
    # bend around the top of the mag so the curve starts below the magwell
    pivot = U.empty("mag_pivot", (0, 0.055, 0.0))
    pivot.rotation_euler = (0, math.radians(90), 0)
    mag_bend.origin = pivot
    U.apply_modifiers(mag)
    bpy.data.objects.remove(pivot, do_unlink=True)
    U.smooth_by_angle(mag)
    # mag origin at the top so reload animations pivot sensibly
    shift = Vector((0, 0.055, 0.0))
    mag.data.transform(Matrix.Translation(-shift))
    mag.location = shift

    root = U.empty(prefix + "Rifle", (0, 0, 0))
    for o in (body, lens, reticle, mag):
        o.parent = root
    U.empty(prefix + "Muzzle", (0, ME + 0.002, BORE_Z), root)
    U.empty(prefix + "SightAxis", (0, -0.012, OZ), root)
    U.empty(prefix + "GripR", (0, -0.075, -0.035), root)
    U.empty(prefix + "GripL", (0, 0.27, BORE_Z - 0.03), root)
    U.empty(prefix + "Eject", (0.018, 0.035, 0.058), root)
    return root

