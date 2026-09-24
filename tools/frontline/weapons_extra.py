"""Pump shotgun and pistol, modeled with the same conventions as rifle.py
(meters, muzzle toward +Y, top +Z, root empty with named child empties)."""
import math
import bpy
from mathutils import Vector, Matrix
import blender_util as U
from rifle import materials, BORE_Z

# Shotgun forend (pump) rest position; the pump slides back PUMP_TRAVEL when cycled.
SG_PUMP_ORIGIN = Vector((0, 0.235, 0.024))
SG_PUMP_TRAVEL = 0.07
PST_MAG_ORIGIN = Vector((0, -0.022, 0.03))


def _origin_at(obj, origin):
    obj.data.transform(Matrix.Translation(-Vector(origin)))
    obj.location = Vector(origin)


def build_shotgun(prefix="SG_"):
    """Mossberg 590 style pump shotgun with pistol-grip stock and side saddle."""
    M = materials("black")
    park = U.material("SG_Parkerized", (0.035, 0.036, 0.035), metallic=0.6, roughness=0.55)
    shell_red = U.material("SG_ShellHull", (0.28, 0.02, 0.02), roughness=0.5)
    brass = U.material("SG_Brass", (0.55, 0.38, 0.12), metallic=1.0, roughness=0.3)
    parts = []
    add = parts.append
    # receiver (rounded top), ejection port, loading port
    rec = U.box_span("receiver", (-0.0158, 0.0158), (-0.062, 0.1), (0.008, 0.08), park)
    U.bevel(rec, 0.006, 3, angle=30)
    add(rec)
    add(U.box_span("eject_port", (0.0155, 0.0162), (0.012, 0.075), (0.046, 0.07), M["steel"]))
    add(U.box_span("load_port", (-0.011, 0.011), (0.0, 0.085), (0.0065, 0.0095), M["polymer"]))
    add(U.box_span("safety", (-0.005, 0.005), (-0.05, -0.03), (0.08, 0.086), M["polymer"]))
    # ghost-ring rear sight on top of the receiver
    add(U.box_span("rear_sight_base", (-0.009, 0.009), (-0.05, -0.02), (0.079, 0.086), park))
    for sx in (-1, 1):
        add(U.box_span("rear_ear", (sx * 0.0095 - 0.002, sx * 0.0095 + 0.002), (-0.042, -0.03), (0.086, 0.1), park))
    ring = U.cylinder("ghost_ring", 0.0065, -0.039, -0.033, park, z=0.093, verts=20)
    ring_cut = U.cylinder("ghost_ring_cut", 0.0042, -0.045, -0.027, None, z=0.093, verts=20)
    U.subtract(ring, [ring_cut])
    add(ring)
    add(ring_cut)
    # trigger guard, trigger
    tg = U.prism("trigger_guard", [(0.012, 0.008), (0.012, -0.03), (-0.045, -0.03), (-0.045, -0.024),
                                   (0.006, -0.024), (0.006, 0.008)], 0.0045, park)
    U.bevel(tg, 0.0012, 1)
    add(tg)
    add(U.prism("trigger", [(-0.008, 0.006), (-0.003, 0.006), (-0.009, -0.014), (-0.015, -0.02),
                            (-0.017, -0.018), (-0.011, -0.01)], 0.0025, M["steel"]))
    # pistol grip in the same place as the M4's so the same hand pose fits
    grip = U.prism("grip", [(-0.036, 0.008), (-0.078, 0.008), (-0.118, -0.104),
                            (-0.112, -0.114), (-0.086, -0.116), (-0.070, -0.100),
                            (-0.047, -0.030), (-0.040, -0.018)], 0.015, M["polymer"])
    U.bevel(grip, 0.006, 3, angle=25)
    add(grip)
    # fixed polymer stock
    stock = U.prism("stock", [(-0.06, 0.074), (-0.33, 0.068), (-0.345, -0.05), (-0.322, -0.058),
                              (-0.2, 0.0), (-0.1, 0.02), (-0.062, 0.012)], 0.018, M["polymer"])
    stock_cut = U.prism("stock_cut", [(-0.13, 0.05), (-0.29, 0.048), (-0.3, -0.018), (-0.2, 0.024), (-0.14, 0.032)], 0.03, None)
    U.subtract(stock, [stock_cut])
    U.bevel(stock, 0.006, 3, angle=25)
    add(stock)
    add(stock_cut)
    pad = U.prism("butt_pad", [(-0.337, 0.072), (-0.357, 0.072), (-0.362, -0.062), (-0.342, -0.062)], 0.02, M["rubber"])
    U.bevel(pad, 0.006, 3)
    add(pad)
    # barrel, magazine tube, barrel clamp, front sight
    add(U.cylinder("barrel", 0.0118, 0.1, 0.52, park, z=BORE_Z, verts=24))
    muzzle_cut = U.cylinder("bore_cut", 0.0093, 0.49, 0.53, None, z=BORE_Z, verts=20)
    parts[-1].data.materials[0] = park
    U.subtract(parts[-1], [muzzle_cut])
    add(muzzle_cut)
    add(U.cylinder("mag_tube", 0.0125, 0.1, 0.47, park, z=0.024, verts=20))
    add(U.cylinder("mag_cap", 0.0138, 0.47, 0.49, M["steel"], z=0.024, verts=20))
    add(U.box_span("barrel_clamp", (-0.013, 0.013), (0.44, 0.46), (0.02, 0.062), park))
    add(U.box_span("front_sight", (-0.0022, 0.0022), (0.49, 0.508), (0.066, 0.1), park))
    add(U.box_span("front_sight_base", (-0.006, 0.006), (0.485, 0.512), (0.064, 0.072), park))
    # side saddle with four shells on the left of the receiver
    add(U.box_span("saddle", (-0.0195, -0.0158), (-0.03, 0.078), (0.018, 0.074), M["polymer"]))
    for i in range(4):
        y = -0.018 + i * 0.027
        add(U.cylinder("saddle_shell", 0.0106, 0.02, 0.078, shell_red, x=-0.031, y=y, axis="Z", verts=14))
        add(U.cylinder("saddle_head", 0.011, 0.012, 0.02, brass, x=-0.031, y=y, axis="Z", verts=14))
    add(U.box_span("sling_loop", (-0.004, 0.004), (-0.26, -0.23), (-0.035, -0.015), M["steel"]))
    body = U.join(parts, prefix + "RifleBody")

    # pump / forend with grip ribs and the action bars that slide into the receiver
    pp = []
    fe = U.box_span("forend", (-0.024, 0.024), (0.155, 0.315), (-0.004, 0.05), M["polymer"])
    U.bevel(fe, 0.012, 4, angle=30)
    pp.append(fe)
    for i in range(7):
        y = 0.17 + i * 0.02
        for sx in (-1, 1):
            pp.append(U.box_span("rib", (sx * 0.0245 - 0.002, sx * 0.0245 + 0.002), (y, y + 0.008), (0.004, 0.042), M["polymer"]))
    for sx in (-1, 1):
        pp.append(U.box_span("action_bar", (sx * 0.0135 - 0.0015, sx * 0.0135 + 0.0015), (0.09, 0.16), (0.026, 0.033), M["steel"]))
    pump = U.join(pp, prefix + "Mag")
    _origin_at(pump, SG_PUMP_ORIGIN)

    root = U.empty(prefix + "Rifle", (0, 0, 0))
    for o in (body, pump):
        o.parent = root
    U.empty(prefix + "Muzzle", (0, 0.525, BORE_Z), root)
    U.empty(prefix + "SightAxis", (0, -0.06, 0.093), root)
    U.empty(prefix + "Eject", (0.018, 0.045, 0.06), root)
    return root


def build_pistol(prefix="PST_"):
    """Striker-fired 9 mm service pistol (Glock/M17 style). Origin near the top of the grip."""
    M = materials("black")
    poly = U.material("PST_Frame", (0.045, 0.045, 0.042), roughness=0.7)
    slide_m = U.material("PST_Slide", (0.03, 0.03, 0.032), metallic=0.5, roughness=0.45)
    parts = []
    add = parts.append
    slide = U.box_span("slide", (-0.0125, 0.0125), (-0.036, 0.165), (0.058, 0.092), slide_m)
    U.bevel(slide, 0.003, 2)
    add(slide)
    # rear serrations
    for i in range(7):
        y = -0.03 + i * 0.006
        for sx in (-1, 1):
            add(U.box_span("serr", (sx * 0.0126 - 0.0008, sx * 0.0126 + 0.0008), (y, y + 0.0025), (0.062, 0.086), M["polymer"]))
    add(U.box_span("port", (0.0, 0.0127), (0.045, 0.085), (0.0915, 0.0925), M["steel"]))
    add(U.cylinder("muzzle", 0.0068, 0.164, 0.1665, M["steel"], z=0.075, verts=16))
    # sights (three-dot)
    for sx in (-1, 1):
        add(U.box_span("rear_sight", (sx * 0.006 - 0.0025, sx * 0.006 + 0.0025), (-0.034, -0.024), (0.092, 0.1045), slide_m))
    add(U.box_span("front_sight", (-0.0018, 0.0018), (0.152, 0.16), (0.092, 0.1045), slide_m))
    # frame, rail, trigger guard, trigger
    frame = U.box_span("frame", (-0.0118, 0.0118), (-0.03, 0.15), (0.038, 0.06), poly)
    U.bevel(frame, 0.003, 2)
    add(frame)
    add(U.box_span("rail", (-0.0105, 0.0105), (0.07, 0.145), (0.03, 0.04), poly))
    tg = U.prism("trigger_guard", [(0.075, 0.04), (0.066, 0.008), (0.005, 0.008), (0.003, 0.016),
                                   (0.06, 0.016), (0.067, 0.04)], 0.0055, poly)
    U.bevel(tg, 0.0015, 1)
    add(tg)
    add(U.prism("trigger", [(0.03, 0.04), (0.036, 0.04), (0.03, 0.022), (0.022, 0.017), (0.02, 0.019), (0.026, 0.028)], 0.0028, M["polymer"]))
    grip = U.prism("grip", [(0.01, 0.04), (-0.034, 0.045), (-0.048, 0.03), (-0.066, -0.062), (-0.02, -0.066),
                            (0.0, 0.008), (0.005, 0.03)], 0.0152, poly)
    U.bevel(grip, 0.005, 3, angle=25)
    add(grip)
    body = U.join(parts, prefix + "RifleBody")
    mp = []
    base = U.box_span("baseplate", (-0.0145, 0.0145), (-0.066, -0.016), (-0.075, -0.064), M["polymer"])
    U.bevel(base, 0.002, 1)
    mp.append(base)
    mp.append(U.box_span("mag_body", (-0.011, 0.011), (-0.06, -0.022), (-0.066, 0.03), M["polymer"]))
    mag = U.join(mp, prefix + "Mag")
    # the mag sits along the grip angle
    mag.data.transform(Matrix.Translation(Vector((0, -0.045, -0.02))) @ Matrix.Rotation(math.radians(-13), 4, "X")
                       @ Matrix.Translation(Vector((0, 0.045, 0.02))))
    _origin_at(mag, PST_MAG_ORIGIN)
    root = U.empty(prefix + "Rifle", (0, 0, 0))
    for o in (body, mag):
        o.parent = root
    U.empty(prefix + "Muzzle", (0, 0.168, 0.075), root)
    U.empty(prefix + "SightAxis", (0, -0.036, 0.1025), root)
    U.empty(prefix + "Eject", (0.013, 0.06, 0.092), root)
    return root
