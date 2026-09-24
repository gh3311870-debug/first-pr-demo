"""Build assets/frontline/operator.glb: the soldier character plus all four Blender-made weapons.

Pipeline (all done headlessly with Blender's Python module, bpy):
  1. Import the rigged, animated Soldier.glb (three.js example model).
  2. Add a "Weapon" bone (child of the chest) and a "Mag" bone (child of Weapon). Every
     weapon (M4, DMR, shotgun, pistol) shares the same weapon-space origin and is parented
     to the Weapon bone; each weapon's magazine (or the shotgun's pump) rides the Mag bone.
     The game shows one weapon at a time.
  3. For every new animation, drive the arms with IK constraints so the hands grip that
     weapon, curl the fingers, twist the torso into a shooting stance, then bake the result
     frame by frame into plain keyframes.
  4. Export one GLB with these actions:
       first person: FP_Hold_<W>, FP_Reload_<W> for W in M4, DMR, PST
                     FP_Hold_SG, FP_Pump_SG, FP_ReloadStart_SG, FP_ReloadShell_SG, FP_ReloadEnd_SG
       third person: AIM_Idle, AIM_Walk, AIM_Run (M4/DMR), AIM_Idle_SG, AIM_Walk_SG, AIM_Run_SG, Death

Usage: python3 build_operator.py <Soldier.glb> <out.glb> [preview_prefix] [--quick]
"""
import os
import sys
import math

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
from mathutils import Vector, Matrix, Quaternion, Euler

import blender_util as U
import rifle
import weapons_extra as WX

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
SOLDIER, OUT = args[0], args[1]
PREVIEW = args[2] if len(args) > 2 and not args[2].startswith("--") else None
QUICK = "--quick" in args


def B(name):
    return "mixamorig:" + name


def V(*a):
    return Vector(a)


def frame_matrix(x, y, z, loc):
    """Rotation whose Y/Z columns follow the given axes (X = Y x Z), at loc."""
    y = Vector(y).normalized()
    z = Vector(z).normalized()
    x = y.cross(z).normalized()
    z = x.cross(y).normalized()
    m = Matrix((x, y, z)).transposed().to_4x4()
    m.translation = Vector(loc)
    return m


def smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


# --------------------------------------------------------------------------------------
# Scene setup
# --------------------------------------------------------------------------------------
U.reset_scene()
bpy.ops.import_scene.gltf(filepath=SOLDIER)
scn = bpy.context.scene
arm = bpy.data.objects["Character"]
visor = bpy.data.objects["vanguard_visor"]
bpy.data.objects.remove(bpy.data.objects["Icosphere"], do_unlink=True)
base_actions = {a.name: a for a in bpy.data.actions}
arm.animation_data.action = None
for pb in arm.pose.bones:
    pb.matrix_basis.identity()
bpy.context.view_layer.update()

AW = arm.matrix_world.copy()
AWi = AW.inverted()
EYE_REST = V(0.0, 0.05, 1.67)  # just behind the visor, rest pose

# --------------------------------------------------------------------------------------
# Weapons. Hand bone axes: X = back of hand, Y = toward the knuckles,
# Z = thumb side (right hand) / little-finger side (left hand).
# --------------------------------------------------------------------------------------
g22 = math.radians(22)
g16 = math.radians(16)
RIFLE_R = frame_matrix(None, (0.05, math.cos(g22), -math.sin(g22)), (0, math.sin(g22), math.cos(g22)), (0.034, -0.140, -0.045))
RIFLE_L = frame_matrix(None, (0.9, 0.1, 0.2), (0.0, -1.0, 0.0), (-0.036, 0.118, 0.010))

GRIP_R = {"Index": (32, 38, 20), "Middle": (72, 80, 45), "Ring": (78, 82, 45), "Pinky": (80, 80, 45)}
GRIP_L = {"Index": (45, 55, 30), "Middle": (55, 60, 30), "Ring": (60, 62, 30), "Pinky": (62, 60, 30)}
WRAP_L = {"Index": (60, 70, 35), "Middle": (68, 75, 40), "Ring": (72, 78, 40), "Pinky": (72, 75, 40)}
THUMB_R = [Quaternion((1, 0, 0), math.radians(-20)), Quaternion((0, 0, 1), math.radians(30)), Quaternion((0, 0, 1), math.radians(20))]
THUMB_L = [Quaternion((1, 0, 0), math.radians(-10)), Quaternion((0, 0, 1), math.radians(20)), Quaternion((0, 0, 1), math.radians(10))]

WEAPONS = {
    "M4": dict(prefix="", build=lambda: rifle.build(""), sight=V(0, -0.012, 0.125), mag=V(0, 0.055, 0),
               R=RIFLE_R, L=RIFLE_L, fp=V(0.07, 0.29, -0.095), grab_z=-0.215, lfing=GRIP_L),
    "DMR": dict(prefix="DMR_", build=lambda: rifle.build("DMR_", variant="dmr"), sight=V(0, -0.012, 0.132),
                mag=V(0, 0.055, 0), R=RIFLE_R, L=RIFLE_L, fp=V(0.07, 0.29, -0.105), grab_z=-0.165, lfing=GRIP_L),
    "SG": dict(prefix="SG_", build=WX.build_shotgun, sight=V(0, -0.06, 0.093), mag=WX.SG_PUMP_ORIGIN,
               R=RIFLE_R, L=frame_matrix(None, (0.9, 0.1, 0.2), (0.0, -1.0, 0.0), (-0.034, 0.158, -0.026)),
               fp=V(0.07, 0.2, -0.1), lfing=GRIP_L),
    "PST": dict(prefix="PST_", build=WX.build_pistol, sight=V(0, -0.036, 0.1025), mag=WX.PST_MAG_ORIGIN,
                R=frame_matrix(None, (0.05, math.cos(g16), -math.sin(g16)), (0, math.sin(g16), math.cos(g16)), (0.034, -0.088, 0.0)),
                L=frame_matrix(None, (0.1, 0.75, -0.65), (0.0, -0.65, -0.75), (-0.036, -0.078, -0.028)),
                fp=V(0.05, 0.3, -0.115), lfing=WRAP_L),
}

roots = {}
for key, w in WEAPONS.items():
    roots[key] = w["build"]()
    w["root"] = roots[key]
    w["mag_obj"] = next(o for o in roots[key].children if o.name == w["prefix"] + "Mag")

M4 = WEAPONS["M4"]
rifle_rest = Matrix.Translation(EYE_REST + M4["fp"] - M4["sight"])
for r in roots.values():
    r.matrix_world = rifle_rest
bpy.context.view_layer.update()

# --------------------------------------------------------------------------------------
# Edit armature: fix IK chain bone lengths, add Weapon + Mag bones
# --------------------------------------------------------------------------------------
bpy.context.view_layer.objects.active = arm
arm.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
eb = arm.data.edit_bones
for side in ("Left", "Right"):
    eb[B(side + "Arm")].tail = eb[B(side + "ForeArm")].head.copy()
    eb[B(side + "ForeArm")].tail = eb[B(side + "Hand")].head.copy()


def add_bone(name, head_w, parent):
    b = eb.new(name)
    b.head = AWi @ head_w
    b.tail = AWi @ (head_w + V(0, 0.1, 0))
    b.align_roll((AWi.to_3x3() @ V(0, 0, 1)).normalized())
    b.parent = eb[parent]
    b.use_deform = False
    return b


add_bone("Weapon", rifle_rest.to_translation(), B("Spine2"))
add_bone("Mag", rifle_rest @ M4["mag"], "Weapon")
bpy.ops.object.mode_set(mode="OBJECT")
bpy.context.view_layer.update()

pbW = arm.pose.bones["Weapon"]
pbMag = arm.pose.bones["Mag"]
for pb in arm.pose.bones:
    pb.rotation_mode = "QUATERNION"


def bone_world(pb):
    return AW @ pb.matrix


def parent_to_bone(obj, bone):
    bpy.context.view_layer.update()
    mw = obj.matrix_world.copy()
    obj.parent = arm
    obj.parent_type = "BONE"
    obj.parent_bone = bone
    bpy.context.view_layer.update()
    obj.matrix_world = mw


for w in WEAPONS.values():
    parent_to_bone(w["root"], "Weapon")
    parent_to_bone(w["mag_obj"], "Mag")
bpy.context.view_layer.update()

# Constant offsets between the bones and the weapon root / each weapon's magazine.
K_RIFLE = bone_world(pbW).inverted() @ rifle_rest
for w in WEAPONS.values():
    w["K_MAG"] = bone_world(pbMag).inverted() @ (rifle_rest @ Matrix.Translation(w["mag"]))

head_rest = bone_world(arm.pose.bones[B("Head")])
EYE_LOCAL = head_rest.inverted() @ EYE_REST
eye_empty = U.empty("Eye", EYE_REST)  # lets the game put the FP camera exactly at the eye
parent_to_bone(eye_empty, B("Head"))

# --------------------------------------------------------------------------------------
# IK targets (children of the weapon so they follow it) and constraints
# --------------------------------------------------------------------------------------
tgtR = U.empty("IK_R", (0, 0, 0))
tgtL = U.empty("IK_L", (0, 0, 0))
for t in (tgtR, tgtL):
    t.parent = M4["root"]
    t.matrix_parent_inverse.identity()

poleR = U.empty("Pole_R", (0, 0, 0))
poleL = U.empty("Pole_L", (0, 0, 0))
for p, loc in ((poleR, V(0.5, -0.2, 0.9)), (poleL, V(-0.22, 0.35, 0.75))):
    parent_to_bone(p, B("Spine2"))
    p.matrix_world = Matrix.Translation(loc)

for side, tgt, pole in (("Right", tgtR, poleR), ("Left", tgtL, poleL)):
    c = arm.pose.bones[B(side + "ForeArm")].constraints.new("IK")
    c.name = "ArmIK"
    c.target = tgt
    c.pole_target = pole
    c.pole_angle = math.radians(-90)
    c.chain_count = 2
    c2 = arm.pose.bones[B(side + "Hand")].constraints.new("COPY_ROTATION")
    c2.name = "HandRot"
    c2.target = tgt


def set_fingers(side, curls, thumb):
    """curls: dict finger -> (deg1, deg2, deg3) curl around the finger bones' local Z."""
    for finger, degs in curls.items():
        for i, d in enumerate(degs):
            pb = arm.pose.bones.get(B(f"{side}Hand{finger}{i + 1}"))
            if pb:
                pb.rotation_quaternion = Quaternion((0, 0, 1), math.radians(d))
    for i, q in enumerate(thumb):
        pb = arm.pose.bones.get(B(f"{side}HandThumb{i + 1}"))
        if pb:
            pb.rotation_quaternion = q


def hands(w, left=None):
    tgtR.matrix_basis = w["R"]
    tgtL.matrix_basis = left if left is not None else w["L"]
    set_fingers("Right", GRIP_R, THUMB_R)
    set_fingers("Left", w["lfing"], THUMB_L)


# --------------------------------------------------------------------------------------
# Posing helpers and baking
# --------------------------------------------------------------------------------------
ALL = list(arm.pose.bones)


def weapon_world_for_sight(w, sight_world, rot=Matrix.Identity(3)):
    m = rot.to_4x4()
    m.translation = sight_world - rot @ w["sight"]
    return m


def place_weapon(weapon_world):
    pbW.matrix = AWi @ weapon_world @ K_RIFLE.inverted()


def place_mag(w, local):
    """local: magazine/pump transform in weapon space (rest = the weapon's mag origin)."""
    bpy.context.view_layer.update()
    rw = AW @ pbW.matrix @ K_RIFLE
    pbMag.matrix = AWi @ rw @ local @ w["K_MAG"].inverted()


def twist(bone, yaw=0.0, pitch=0.0, roll=0.0):
    pb = arm.pose.bones[B(bone)]
    rest = pb.bone.matrix_local.to_3x3()
    wm = AWi.to_3x3().normalized()
    qw = Euler((math.radians(pitch), math.radians(roll), math.radians(yaw)), "XYZ").to_quaternion()
    ma = wm @ qw.to_matrix() @ wm.inverted()
    pb.rotation_quaternion = pb.rotation_quaternion @ (rest.inverted() @ ma @ rest).to_quaternion()


def eye_world():
    bpy.context.view_layer.update()
    return bone_world(arm.pose.bones[B("Head")]) @ EYE_LOCAL


def bake(name, frames, pose_fn, base="Idle", base_frame=0):
    """pose_fn(frame) sets up the pose after the base action was applied. base_frame pins the
    base action to one frame (a static starting pose for the IK); None samples it per frame."""
    arm.animation_data_create()
    samples = []
    for f in frames:
        arm.animation_data.action = base_actions[base]
        arm.animation_data.action_slot = base_actions[base].slots[0]
        bf = f if base_frame is None else base_frame
        scn.frame_set(int(bf), subframe=bf - int(bf))
        arm.animation_data.action = None
        pbW.matrix_basis.identity()
        pbMag.matrix_basis.identity()
        pose_fn(f)
        bpy.context.view_layer.update()
        vis = {pb.name: pb.matrix.copy() for pb in ALL}
        if os.environ.get("DEBUG_IK") and f == frames[0]:
            for side, t in (("Right", tgtR), ("Left", tgtL)):
                hw = AW @ vis[B(side + "Hand")].to_translation()
                err = (hw - t.matrix_world.to_translation()).length
                sh = (AW @ vis[B(side + "Arm")].to_translation() - t.matrix_world.to_translation()).length
                print(f"{name:18s} {side:5s} IK error {err * 100:5.1f} cm  shoulder->target {sh:.3f} m")
        local = {pb.name: arm.convert_space(pose_bone=pb, matrix=vis[pb.name], from_space="POSE", to_space="LOCAL")
                 for pb in ALL}
        samples.append((f, local))
    act = bpy.data.actions.new(name)
    arm.animation_data.action = act
    start = frames[0]
    for f, local in samples:
        for pb in ALL:
            loc, rot, _ = local[pb.name].decompose()
            pb.location = loc
            pb.rotation_quaternion = rot
            pb.keyframe_insert("location", frame=f - start + 1, group=pb.name)
            pb.keyframe_insert("rotation_quaternion", frame=f - start + 1, group=pb.name)
    arm.animation_data.action = None
    act.use_fake_user = True
    return act


def frames(n):
    return [float(i) for i in range(n + 1)]


def frames_of(action):
    a, b = base_actions[action].frame_range
    n = int(round(b - a))
    return [a + i * (b - a) / n for i in range(n + 1)]


# --- first person ------------------------------------------------------------------------
def fp_torso(square=False):
    if square:
        # isosceles pistol stance: shoulders square to the target, both arms reaching forward
        twist("Spine", yaw=2, pitch=9)
        twist("Spine1", yaw=2, pitch=6)
        twist("Spine2", pitch=3)
        twist("RightShoulder", yaw=10, roll=6)
        twist("LeftShoulder", yaw=-10, roll=-6)
        twist("Neck", pitch=-8)
        twist("Head", pitch=-8)
        return
    twist("Spine", yaw=-6, pitch=8)
    twist("Spine1", yaw=-5, pitch=6)
    twist("Spine2", yaw=-3, pitch=2)
    twist("LeftShoulder", yaw=-11, roll=-8)
    twist("RightShoulder", yaw=-4)
    twist("Neck", yaw=8, pitch=-8)
    twist("Head", yaw=6, pitch=-8)


def fp_place(w, rot=Matrix.Identity(3), offset=V(0, 0, 0)):
    fp_torso(square=w is WEAPONS["PST"])
    bpy.context.view_layer.update()
    rw = weapon_world_for_sight(w, eye_world() + w["fp"] + offset, rot)
    place_weapon(rw)
    return rw


def fp_hold(w):
    def pose(f):
        fp_place(w)
        hands(w)
    return pose


# Aim-down-sights pose: the optic/sights centred on the eye at the weapon's eye relief.
ADS_DIST = {"M4": 0.25, "DMR": 0.17, "SG": 0.19, "PST": 0.32}


def fp_ads(key):
    w = WEAPONS[key]

    def pose(f):
        fp_torso(square=key == "PST")
        bpy.context.view_layer.update()
        place_weapon(weapon_world_for_sight(w, eye_world() + V(0, ADS_DIST[key], 0)))
        hands(w)
    return pose


def keyed(t, keys):
    """Piecewise smooth interpolation through [(t, Vector), ...]."""
    if t <= keys[0][0]:
        return keys[0][1].copy()
    for (t0, a), (t1, b) in zip(keys, keys[1:]):
        if t <= t1:
            return a.lerp(b, smooth((t - t0) / (t1 - t0)))
    return keys[-1][1].copy()


def palm_up(loc):
    # left hand palm up, fingers forward: holds a magazine from below
    return frame_matrix(None, (0.0, 1.0, 0.25), (1.0, 0.0, 0.0), loc)


def fp_mag_reload(w, n_frames, mag_keys, tilt_deg=(8, -28, 12)):
    """Box-magazine reload: tilt the weapon, left hand strips the mag, fetches a new one,
    seats it, slaps it home and returns. mag_keys: [(t, offset from seated)]."""
    grab_off = V(-0.012, -0.03, w.get("grab_z", -0.2))

    def pose(f):
        t = f / n_frames
        tilt = smooth(t / 0.18) * (1 - smooth((t - 0.78) / 0.2))
        rot = Euler([math.radians(a * tilt) for a in tilt_deg], "XYZ").to_matrix()
        fp_place(w, rot, V(-0.05 * tilt, -0.02 * tilt, -0.02 * tilt))
        mo = keyed(t, mag_keys)
        place_mag(w, Matrix.Translation(w["mag"] + mo))
        grab = palm_up(w["mag"] + grab_off)
        if t < 0.2:
            m = w["L"].lerp(grab, smooth(t / 0.2))
        elif t < 0.72:
            m = grab.copy()
            m.translation = grab.translation + mo
        else:
            m = grab.lerp(w["L"], smooth((t - 0.72) / 0.23))
        hands(w, m)
    return pose


RIFLE_MAG_KEYS = [(0.22, V(0, 0, 0)), (0.34, V(0, 0.01, -0.12)), (0.5, V(-0.12, -0.05, -0.55)),
                  (0.64, V(0, 0, -0.10)), (0.72, V(0, 0, 0))]
# the pistol's empty mag drops free first; the hand brings the fresh one up into the grip
PISTOL_MAG_KEYS = [(0.12, V(0, 0, 0)), (0.22, V(0, -0.02, -0.08)), (0.42, V(-0.1, -0.06, -0.5)),
                   (0.62, V(0, -0.015, -0.09)), (0.72, V(0, 0, 0))]


# shotgun: pump cycle and tube loading
SG = WEAPONS["SG"]
PORT = V(0, 0.04, 0.008)  # loading port under the receiver


def sg_tilt(k):
    return Euler((math.radians(10 * k), math.radians(-32 * k), math.radians(8 * k)), "XYZ").to_matrix()


def sg_pump(f, n=12):
    t = f / n
    k = smooth(t / 0.35) * (1 - smooth((t - 0.5) / 0.3))
    fp_place(SG, Euler((math.radians(-3 * k), 0, 0), "XYZ").to_matrix(), V(0, -0.012 * k, -0.006 * k))
    mo = V(0, -WX.SG_PUMP_TRAVEL * k, 0)
    place_mag(SG, Matrix.Translation(SG["mag"] + mo))
    left = SG["L"].copy()
    left.translation += mo
    hands(SG, left)


def port_hand(offset=V(0, 0, 0)):
    return palm_up(PORT + V(-0.006, -0.075, -0.03) + offset)


def sg_reload_start(f, n=8):
    t = f / n
    k = smooth(t)
    fp_place(SG, sg_tilt(k), V(-0.04 * k, -0.02 * k, -0.02 * k))
    hands(SG, SG["L"].lerp(port_hand(), k))


POUCH = V(-0.1, -0.06, -0.2)


def sg_reload_shell(f, n=11):
    t = f / n
    fp_place(SG, sg_tilt(1), V(-0.04, -0.02, -0.02))
    off = keyed(t, [(0.0, V(0, 0, 0)), (0.35, POUCH), (0.7, V(0, 0, -0.035)), (0.85, V(0, 0, 0.01)), (1.0, V(0, 0, 0))])
    hands(SG, port_hand(off))


def sg_reload_end(f, n=9):
    t = f / n
    k = 1 - smooth(t)
    fp_place(SG, sg_tilt(k), V(-0.04 * k, -0.02 * k, -0.02 * k))
    hands(SG, SG["L"].lerp(port_hand(), k))


# --- third person ------------------------------------------------------------------------
AIM_SIGHT_FROM_EYE = V(0.02, 0.26, -0.035)


def aim_pose(w, low_ready=False):
    def pose(f):
        twist("Spine", yaw=-10)
        twist("Spine1", yaw=-8)
        twist("Spine2", yaw=-6, pitch=4)
        twist("LeftShoulder", yaw=-12)
        twist("Neck", yaw=12)
        twist("Head", yaw=10, pitch=-6)
        bpy.context.view_layer.update()
        eye = eye_world()
        if low_ready:
            rot = Euler((math.radians(-32), 0, math.radians(18)), "XYZ").to_matrix()
            sight = eye + V(0.05, 0.25, -0.30)
        else:
            rot = Matrix.Identity(3)
            sight = eye + AIM_SIGHT_FROM_EYE + V(0, w["sight"].y - M4["sight"].y, M4["sight"].z - w["sight"].z)
        place_weapon(weapon_world_for_sight(w, sight, rot))
        hands(w)
    return pose


def death_pose(f):
    aim_pose(M4)(0)
    bpy.context.view_layer.update()
    t = f / 30.0
    k1 = smooth(t / 0.3)            # knees buckle
    k2 = smooth((t - 0.2) / 0.55)   # fall backwards
    k3 = smooth((t - 0.75) / 0.25)  # settle
    hips = arm.pose.bones[B("Hips")]
    drop = 0.35 * k1 + 0.52 * k2 - 0.02 * math.sin(k3 * math.pi)
    hips_w_new = Matrix.Translation(V(0, -0.35 * k2, -drop)) @ bone_world(hips)
    pivot = hips_w_new.to_translation()
    R = (Matrix.Translation(pivot) @ Euler((math.radians(-80 * k2), math.radians(18 * k2), 0), "XYZ")
         .to_matrix().to_4x4() @ Matrix.Translation(-pivot))
    hips.matrix = AWi @ R @ hips_w_new
    bpy.context.view_layer.update()
    for side in ("Left", "Right"):
        twist(side + "UpLeg", pitch=55 * k1 - 20 * k2)
        twist(side + "Leg", pitch=-85 * k1 + 40 * k2)
    twist("Spine", pitch=-10 * k2)
    twist("Spine1", pitch=-12 * k2)
    twist("Head", pitch=25 * k1 - 45 * k2, yaw=20 * k2)
    for side in ("Left", "Right"):
        arm.pose.bones[B(side + "ForeArm")].constraints["ArmIK"].influence = 1 - smooth(t / 0.35)
        arm.pose.bones[B(side + "Hand")].constraints["HandRot"].influence = 1 - smooth(t / 0.35)
    twist("LeftArm", roll=35 * k2, pitch=-30 * k2)
    twist("RightArm", roll=-45 * k2, pitch=-20 * k2)
    bpy.context.view_layer.update()
    rw = AW @ pbW.matrix @ K_RIFLE
    fall = (Matrix.Translation(V(0.25 * k2, 0.35 * k2, -1.05 * k2 - 0.25 * k1))
            @ Matrix.Translation(rw.to_translation())
            @ Euler((math.radians(-20 * k2), math.radians(85 * k2), math.radians(40 * k2)), "XYZ").to_matrix().to_4x4()
            @ Matrix.Translation(-rw.to_translation()))
    place_weapon(fall @ rw)


# --------------------------------------------------------------------------------------
# Bake everything
# --------------------------------------------------------------------------------------
acts = {}


def add(name, fr, fn, **kw):
    acts[name] = bake(name, fr, fn, **kw)


for key in ("M4", "DMR", "PST", "SG"):
    add(f"FP_Hold_{key}", frames(1), fp_hold(WEAPONS[key]))
    add(f"FP_ADS_{key}", frames(1), fp_ads(key))
if not QUICK:
    add("FP_Reload_M4", frames(60), fp_mag_reload(M4, 60, RIFLE_MAG_KEYS))
    add("FP_Reload_DMR", frames(64), fp_mag_reload(WEAPONS["DMR"], 64, RIFLE_MAG_KEYS))
    add("FP_Reload_PST", frames(44), fp_mag_reload(WEAPONS["PST"], 44, PISTOL_MAG_KEYS, tilt_deg=(6, -18, 8)))
    add("FP_Pump_SG", frames(12), sg_pump)
    add("FP_ReloadStart_SG", frames(8), sg_reload_start)
    add("FP_ReloadShell_SG", frames(11), sg_reload_shell)
    add("FP_ReloadEnd_SG", frames(9), sg_reload_end)
add("AIM_Idle", frames_of("Idle"), aim_pose(M4), base="Idle", base_frame=None)
add("AIM_Idle_SG", frames_of("Idle"), aim_pose(SG), base="Idle", base_frame=None)
if not QUICK:
    add("AIM_Walk", frames_of("Walk"), aim_pose(M4), base="Walk", base_frame=None)
    add("AIM_Run", frames_of("Run"), aim_pose(M4, low_ready=True), base="Run", base_frame=None)
    add("AIM_Walk_SG", frames_of("Walk"), aim_pose(SG), base="Walk", base_frame=None)
    add("AIM_Run_SG", frames_of("Run"), aim_pose(SG, low_ready=True), base="Run", base_frame=None)
    add("Death", frames(30), death_pose)
    for side in ("Left", "Right"):
        arm.pose.bones[B(side + "ForeArm")].constraints["ArmIK"].influence = 1
        arm.pose.bones[B(side + "Hand")].constraints["HandRot"].influence = 1

for pb in ALL:
    for c in list(pb.constraints):
        pb.constraints.remove(c)
for o in (tgtR, tgtL, poleR, poleL):
    bpy.data.objects.remove(o, do_unlink=True)

# --------------------------------------------------------------------------------------
# Previews (optional)
# --------------------------------------------------------------------------------------


def apply_action(act, frame):
    arm.animation_data.action = act
    arm.animation_data.action_slot = act.slots[0]
    scn.frame_set(frame)


def show_only(key):
    for k, r in roots.items():
        for o in [r] + list(r.children_recursive) + [WEAPONS[k]["mag_obj"]]:
            o.hide_render = k != key


if PREVIEW:
    for key in WEAPONS:
        show_only(key)
        apply_action(acts[f"FP_Hold_{key}"], 1)
        eye = eye_empty.matrix_world.to_translation()
        arm.animation_data.action = None
        arm.pose.bones[B("Head")].scale = (0.001, 0.001, 0.001)
        visor.hide_render = True
        U.preview(f"{PREVIEW}_fp_{key}.png", target=eye + V(0, 1, 0), cam_loc=eye, lens=24, res=(640, 360), samples=8)
        U.preview(f"{PREVIEW}_fpside_{key}.png", target=eye + V(0, 0.25, -0.2), cam_loc=eye + V(1.2, 0.35, 0.1),
                  lens=35, res=(400, 400), samples=8)
        arm.pose.bones[B("Head")].scale = (1, 1, 1)
        visor.hide_render = False
    show_only("SG")
    apply_action(acts["AIM_Idle_SG"], 1)
    U.preview(f"{PREVIEW}_aim_SG.png", target=V(0, 0.1, 1.35), cam_loc=V(1.8, 0.6, 1.5), lens=50, res=(500, 500), samples=8)
    if not QUICK:
        for name, frs in (("FP_Reload_PST", (1, 8, 16, 26, 34, 42)), ("FP_ReloadShell_SG", (1, 4, 8, 10)),
                          ("FP_Pump_SG", (1, 5, 9)), ("FP_Reload_DMR", (1, 20, 40))):
            show_only(name.split("_")[-1])
            for fr in frs:
                apply_action(acts[name], fr)
                e = eye_empty.matrix_world.to_translation()
                U.preview(f"{PREVIEW}_{name}_{fr:02d}.png", target=e + V(0, 0.4, -0.2), cam_loc=e + V(-0.9, 0.9, 0.1),
                          lens=35, res=(300, 300), samples=6)
    if QUICK:
        sys.exit(0)
    show_only(None)
    for r in roots.values():
        for o in [r] + list(r.children_recursive):
            o.hide_render = False
    for w in WEAPONS.values():
        w["mag_obj"].hide_render = False

# --------------------------------------------------------------------------------------
# Export
# --------------------------------------------------------------------------------------
for name in ("Idle", "Walk", "Run", "TPose"):
    bpy.data.actions.remove(base_actions[name])
arm.animation_data.action = None
for act in acts.values():
    tr = arm.animation_data.nla_tracks.new()
    tr.name = act.name
    tr.strips.new(act.name, 1, act)
for pb in ALL:
    pb.matrix_basis.identity()
bpy.context.view_layer.update()
bpy.ops.object.select_all(action="DESELECT")
bpy.ops.export_scene.gltf(
    filepath=OUT,
    export_format="GLB",
    use_selection=False,
    export_animations=True,
    export_animation_mode="NLA_TRACKS",
    export_yup=True,
    export_cameras=False,
    export_lights=False,
    export_optimize_animation_size=True,
)
print("EXPORTED", OUT, list(acts))
