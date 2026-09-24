"""Build assets/frontline/operator.glb: the soldier character holding the Blender-made rifle.

Pipeline (all done headlessly with Blender's Python module, bpy):
  1. Import the rigged, animated Soldier.glb (three.js example model).
  2. Add a "Weapon" bone (child of the chest) and a "Mag" bone (child of Weapon) and
     parent the procedural rifle and its magazine to them.
  3. For every new animation, drive the arms with IK constraints so the hands grip the
     pistol grip and handguard, curl the fingers, twist the torso into a shooting stance,
     then bake the result frame by frame into plain keyframes.
  4. Export one GLB with the actions FP_Hold, FP_Reload, AIM_Idle, AIM_Walk, AIM_Run, Death.

Usage: python3 build_operator.py <Soldier.glb> <out.glb> [preview_prefix]
"""
import os
import sys
import math

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
from mathutils import Vector, Matrix, Quaternion, Euler

import blender_util as U
import rifle

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
SOLDIER, OUT = args[0], args[1]
PREVIEW = args[2] if len(args) > 2 else None
QUICK = "--quick" in args


def B(name):
    return "mixamorig:" + name


def V(*a):
    return Vector(a)


# --------------------------------------------------------------------------------------
# Scene setup
# --------------------------------------------------------------------------------------
U.reset_scene()
bpy.ops.import_scene.gltf(filepath=SOLDIER)
scn = bpy.context.scene
arm = bpy.data.objects["Character"]
body_mesh = bpy.data.objects["vanguard_Mesh"]
visor = bpy.data.objects["vanguard_visor"]
bpy.data.objects.remove(bpy.data.objects["Icosphere"], do_unlink=True)
base_actions = {a.name: a for a in bpy.data.actions}
arm.animation_data.action = None
for pb in arm.pose.bones:
    pb.matrix_basis.identity()
bpy.context.view_layer.update()

AW = arm.matrix_world.copy()
AWi = AW.inverted()

# Eye position (just behind the visor) in rest pose.
EYE_REST = V(0.0, 0.05, 1.67)
# FP viewmodel: where the optic sits relative to the eye (right, forward, down) when
# holding the rifle at the hip-fire position.
FP_SIGHT_FROM_EYE = V(0.07, 0.29, -0.095)
RIFLE_SIGHT = V(0, -0.012, 0.125)          # SightAxis in rifle space (see rifle.py)
MAG_ORIGIN = V(0, 0.055, 0.0)

rifle_root = rifle.build(prefix="")
rifle_objs = {o.name: o for o in rifle_root.children}
mag_obj = rifle_objs["Mag"]

rifle_rest = Matrix.Translation(EYE_REST + FP_SIGHT_FROM_EYE - RIFLE_SIGHT)
rifle_root.matrix_world = rifle_rest
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
add_bone("Mag", rifle_rest @ MAG_ORIGIN, "Weapon")
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


parent_to_bone(rifle_root, "Weapon")
parent_to_bone(mag_obj, "Mag")
bpy.context.view_layer.update()

# Constant offset between the weapon bone and the rifle root.
K_RIFLE = bone_world(pbW).inverted() @ rifle_rest
K_MAG = bone_world(pbMag).inverted() @ (rifle_rest @ Matrix.Translation(MAG_ORIGIN))

head_rest = bone_world(arm.pose.bones[B("Head")])
EYE_LOCAL = head_rest.inverted() @ EYE_REST

# Eye marker for the game (so the FP camera can be placed exactly at the eye).
eye_empty = U.empty("Eye", EYE_REST)
parent_to_bone(eye_empty, B("Head"))

# --------------------------------------------------------------------------------------
# Hand targets (children of the rifle so they follow it) + IK constraints
# --------------------------------------------------------------------------------------


def frame_matrix(x, y, z, loc):
    """Rotation whose columns are the given axes (orthonormalized), at loc."""
    y = Vector(y).normalized()
    z = Vector(z).normalized()
    x = y.cross(z).normalized()
    z = x.cross(y).normalized()
    m = Matrix((x, y, z)).transposed().to_4x4()
    m.translation = Vector(loc)
    return m


# Right hand on the pistol grip. Hand bone axes: X = back of hand, Y = toward knuckles,
# Z = thumb side (right hand). Grip leans back ~22 degrees.
g = math.radians(22)
R_HAND = frame_matrix(None, (0.05, math.cos(g), -math.sin(g)), (0, math.sin(g), math.cos(g)),
                      (0.034, -0.140, -0.045))
# Left hand under the handguard (C-clamp), palm up-right, fingers wrap round.
# Left hand bone: X = back of hand, Y = toward knuckles, Z = little-finger side.
L_HAND = frame_matrix(None, (0.9, 0.1, 0.2), (0.0, -1.0, 0.0), (-0.036, 0.118, 0.010))

tgtR = U.empty("IK_R", (0, 0, 0))
tgtL = U.empty("IK_L", (0, 0, 0))
for t, m in ((tgtR, R_HAND), (tgtL, L_HAND)):
    t.parent = rifle_root
    t.matrix_parent_inverse.identity()
    t.matrix_basis = m

poleR = U.empty("Pole_R", (0, 0, 0))
poleL = U.empty("Pole_L", (0, 0, 0))
for p, loc in ((poleR, V(0.5, -0.2, 0.9)), (poleL, V(-0.22, 0.35, 0.75))):
    parent_to_bone(p, B("Spine2"))
    p.matrix_world = Matrix.Translation(loc)

POLE_ANGLE = {"Right": math.radians(-90), "Left": math.radians(-90)}


def setup_ik():
    for side, tgt, pole in (("Right", tgtR, poleR), ("Left", tgtL, poleL)):
        fa = arm.pose.bones[B(side + "ForeArm")]
        c = fa.constraints.new("IK")
        c.name = "ArmIK"
        c.target = tgt
        c.pole_target = pole
        c.pole_angle = POLE_ANGLE[side]
        c.chain_count = 2
        hand = arm.pose.bones[B(side + "Hand")]
        c2 = hand.constraints.new("COPY_ROTATION")
        c2.name = "HandRot"
        c2.target = tgt


setup_ik()

# --------------------------------------------------------------------------------------
# Finger poses
# --------------------------------------------------------------------------------------


def q_axis(axis, deg):
    return Quaternion(Vector(axis), math.radians(deg))


def set_fingers(side, curls, thumb):
    """curls: dict finger -> (deg1, deg2, deg3) curl around local Z."""
    for finger, degs in curls.items():
        for i, d in enumerate(degs):
            pb = arm.pose.bones.get(B(f"{side}Hand{finger}{i + 1}"))
            if pb:
                pb.rotation_quaternion = q_axis((0, 0, 1), d)
    for i, q in enumerate(thumb):
        pb = arm.pose.bones.get(B(f"{side}HandThumb{i + 1}"))
        if pb:
            pb.rotation_quaternion = q


GRIP_R = {"Index": (32, 38, 20), "Middle": (72, 80, 45), "Ring": (78, 82, 45), "Pinky": (80, 80, 45)}
GRIP_L = {"Index": (45, 55, 30), "Middle": (55, 60, 30), "Ring": (60, 62, 30), "Pinky": (62, 60, 30)}
THUMB_R = [Quaternion((1, 0, 0), 0) @ q_axis((1, 0, 0), -20), q_axis((0, 0, 1), 30), q_axis((0, 0, 1), 20)]
THUMB_L = [q_axis((1, 0, 0), -10), q_axis((0, 0, 1), 20), q_axis((0, 0, 1), 10)]


# --------------------------------------------------------------------------------------
# Baking
# --------------------------------------------------------------------------------------
ALL = [pb for pb in arm.pose.bones]


def rifle_world_for_sight(sight_world, rot=Matrix.Identity(3)):
    """Rifle root world matrix so that its SightAxis sits at sight_world."""
    m = rot.to_4x4()
    m.translation = sight_world - rot @ RIFLE_SIGHT
    return m


def place_weapon(rifle_world):
    pbW.matrix = AWi @ rifle_world @ K_RIFLE.inverted()


def place_mag(mag_world_local):
    """mag_world_local: magazine transform in rifle space (rest = MAG_ORIGIN)."""
    bpy.context.view_layer.update()
    rw = AW @ pbW.matrix @ K_RIFLE
    pbMag.matrix = AWi @ rw @ mag_world_local @ K_MAG.inverted()


def twist(bone, yaw=0.0, pitch=0.0, roll=0.0):
    pb = arm.pose.bones[B(bone)]
    # pose-space rotation about world-ish axes, converted into the bone's local frame
    rest = pb.bone.matrix_local.to_3x3()
    w = AWi.to_3x3().normalized()
    qw = Euler((math.radians(pitch), math.radians(roll), math.radians(yaw)), "XYZ").to_quaternion()
    # rotation expressed in armature space
    ma = (w @ qw.to_matrix() @ w.inverted())
    local = rest.inverted() @ ma @ rest
    pb.rotation_quaternion = pb.rotation_quaternion @ local.to_quaternion()


def bake(name, frames, pose_fn, base=None, base_frame=None):
    """pose_fn(frame) sets up the pose (after the base action was applied).
    base_frame pins the base action to one frame (a static starting pose for the IK)."""
    arm.animation_data_create()
    samples = []
    for f in frames:
        if base:
            arm.animation_data.action = base_actions[base]
            if base_actions[base].slots:
                arm.animation_data.action_slot = base_actions[base].slots[0]
            bf = f if base_frame is None else base_frame
            scn.frame_set(int(bf), subframe=bf - int(bf))
            arm.animation_data.action = None
        else:
            for pb in ALL:
                pb.matrix_basis.identity()
        pbW.matrix_basis.identity()
        pbMag.matrix_basis.identity()
        pose_fn(f)
        bpy.context.view_layer.update()
        vis = {pb.name: pb.matrix.copy() for pb in ALL}
        if os.environ.get("DEBUG_IK") and f == frames[0]:
            for side, t in (("Right", tgtR), ("Left", tgtL)):
                hw = AW @ vis[B(side + "Hand")].to_translation()
                sw = AW @ vis[B(side + "Arm")].to_translation()
                print(name, side, "hand", tuple(round(x, 3) for x in hw), "target",
                      tuple(round(x, 3) for x in t.matrix_world.to_translation()),
                      "shoulder->target", round((t.matrix_world.to_translation() - sw).length, 3))
        local = {}
        for pb in ALL:
            local[pb.name] = arm.convert_space(pose_bone=pb, matrix=vis[pb.name],
                                               from_space="POSE", to_space="LOCAL")
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


def eye_world():
    bpy.context.view_layer.update()
    return bone_world(arm.pose.bones[B("Head")]) @ EYE_LOCAL


def lerp(a, b, t):
    return a + (b - a) * t


def smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


# --- First-person hold (static, looping) ---------------------------------------------
def fp_torso():
    twist("Spine", yaw=-6, pitch=8)
    twist("Spine1", yaw=-5, pitch=6)
    twist("Spine2", yaw=-3, pitch=2)
    twist("LeftShoulder", yaw=-11, roll=-8)
    twist("RightShoulder", yaw=-4)
    twist("Neck", yaw=8, pitch=-8)
    twist("Head", yaw=6, pitch=-8)


def fp_eye():
    """Eye position in the FP pose, but with the head kept level (the game camera)."""
    return eye_world()


def fp_hold(f):
    fp_torso()
    bpy.context.view_layer.update()
    place_weapon(rifle_world_for_sight(fp_eye() + FP_SIGHT_FROM_EYE))
    set_fingers("Right", GRIP_R, THUMB_R)
    set_fingers("Left", GRIP_L, THUMB_L)


# --- First-person reload ---------------------------------------------------------------
RELOAD_FRAMES = 60  # 2.5 s at 24 fps


def fp_reload(f):
    fp_torso()
    bpy.context.view_layer.update()
    t = f / RELOAD_FRAMES
    # weapon tilts/rolls toward the left hand
    tilt = smooth(t / 0.18) * (1 - smooth((t - 0.78) / 0.2))
    rot = (Euler((math.radians(8 * tilt), math.radians(-28 * tilt), math.radians(12 * tilt)), "XYZ")
           .to_matrix())
    sight = fp_eye() + FP_SIGHT_FROM_EYE + V(-0.05 * tilt, -0.02 * tilt, -0.02 * tilt)
    rw = rifle_world_for_sight(sight, rot)
    place_weapon(rw)
    # magazine keyframes (rifle space offsets from the seated position)
    seated = V(0, 0, 0)
    out_low = V(0, 0.01, -0.12)
    away = V(-0.12, -0.05, -0.55)
    below = V(0, 0.0, -0.10)
    if t < 0.22:
        mo = seated
    elif t < 0.34:
        mo = seated.lerp(out_low, smooth((t - 0.22) / 0.12))
    elif t < 0.5:
        mo = out_low.lerp(away, smooth((t - 0.34) / 0.16))
    elif t < 0.64:
        mo = away.lerp(below, smooth((t - 0.5) / 0.14))
    elif t < 0.72:
        mo = below.lerp(seated, smooth((t - 0.64) / 0.08))
    else:
        mo = seated
    place_mag(Matrix.Translation(MAG_ORIGIN + mo))
    # left hand: handguard -> mag -> away -> back with mag -> slap -> handguard
    grab = frame_matrix(None, (0.0, 1.0, 0.25), (-1.0, 0.0, 0.0), (-0.01, 0.0, -0.20))
    grab.translation = MAG_ORIGIN + V(-0.012, -0.03, -0.215)
    if t < 0.2:
        k = smooth(t / 0.2)
        m = L_HAND.lerp(grab, k)
    elif t < 0.72:
        m = grab.copy()
        m.translation = grab.translation + mo
    elif t < 0.95:
        k = smooth((t - 0.72) / 0.23)
        m = grab.lerp(L_HAND, k)
    else:
        m = L_HAND
    tgtL.matrix_basis = m
    set_fingers("Right", GRIP_R, THUMB_R)
    set_fingers("Left", GRIP_L, THUMB_L)


# --- Third-person rifle poses ----------------------------------------------------------
AIM_SIGHT_FROM_EYE = V(0.02, 0.26, -0.035)


def aim_pose(f, low_ready=False, bladed=True):
    twist("Spine", yaw=-10 if bladed else -4)
    twist("Spine1", yaw=-8 if bladed else -4)
    twist("Spine2", yaw=-6 if bladed else -2, pitch=4)
    twist("LeftShoulder", yaw=-12)
    twist("Neck", yaw=12 if bladed else 5)
    twist("Head", yaw=10 if bladed else 4, pitch=-6)
    bpy.context.view_layer.update()
    eye = eye_world()
    if low_ready:
        rot = Euler((math.radians(-32), 0, math.radians(18)), "XYZ").to_matrix()
        sight = eye + V(0.05, 0.25, -0.30)
    else:
        rot = Matrix.Identity(3)
        sight = eye + AIM_SIGHT_FROM_EYE
    place_weapon(rifle_world_for_sight(sight, rot))
    set_fingers("Right", GRIP_R, THUMB_R)
    set_fingers("Left", GRIP_L, THUMB_L)


def frames_of(action):
    a, b = base_actions[action].frame_range
    n = int(round(b - a))
    return [a + i * (b - a) / n for i in range(n + 1)]


tgtL_rest = L_HAND.copy()

acts = []
acts.append(bake("FP_Hold", [0.0, 1.0], fp_hold, base="Idle", base_frame=0))
if not QUICK:
    acts.append(bake("FP_Reload", [float(i) for i in range(RELOAD_FRAMES + 1)], fp_reload, base="Idle", base_frame=0))
else:
    acts.append(acts[0])
tgtL.matrix_basis = tgtL_rest
acts.append(bake("AIM_Idle", frames_of("Idle"), lambda f: aim_pose(f), base="Idle"))
if not QUICK:
    acts.append(bake("AIM_Walk", frames_of("Walk"), lambda f: aim_pose(f), base="Walk"))
    acts.append(bake("AIM_Run", frames_of("Run"), lambda f: aim_pose(f, low_ready=True), base="Run"))


# --- Death: keyed fall (arms release the rifle and go limp) -----------------------------
def death_pose(f):
    # Start from aim idle pose, blend into a backwards collapse.
    arm.animation_data.action = base_actions["Idle"]
    arm.animation_data.action_slot = base_actions["Idle"].slots[0]
    scn.frame_set(0)
    arm.animation_data.action = None
    aim_pose(0)
    bpy.context.view_layer.update()
    t = f / 30.0
    k1 = smooth(t / 0.3)            # knees buckle
    k2 = smooth((t - 0.2) / 0.55)   # fall backwards
    k3 = smooth((t - 0.75) / 0.25)  # settle
    hips = arm.pose.bones[B("Hips")]
    # hips drop and rotate backwards
    drop = 0.35 * k1 + 0.52 * k2 - 0.02 * math.sin(k3 * math.pi)
    hips_w = bone_world(hips)
    hips_w_new = Matrix.Translation(V(0, -0.35 * k2, -drop)) @ hips_w
    pivot = hips_w_new.to_translation()
    R = (Matrix.Translation(pivot) @ Euler((math.radians(-80 * k2), math.radians(18 * k2), 0), "XYZ")
         .to_matrix().to_4x4() @ Matrix.Translation(-pivot))
    hips.matrix = AWi @ R @ hips_w_new
    bpy.context.view_layer.update()
    for side, s in (("Left", -1), ("Right", 1)):
        twist(side + "UpLeg", pitch=55 * k1 - 20 * k2)
        twist(side + "Leg", pitch=-85 * k1 + 40 * k2)
    twist("Spine", pitch=-10 * k2)
    twist("Spine1", pitch=-12 * k2)
    twist("Head", pitch=25 * k1 - 45 * k2, yaw=20 * k2)
    # let go of the rifle
    for c in ("ArmIK", "HandRot"):
        for side in ("Left", "Right"):
            bn = side + ("ForeArm" if c == "ArmIK" else "Hand")
            arm.pose.bones[B(bn)].constraints[c].influence = 1 - smooth(t / 0.35)
    twist("LeftArm", roll=35 * k2, pitch=-30 * k2)
    twist("RightArm", roll=-45 * k2, pitch=-20 * k2)
    bpy.context.view_layer.update()
    # rifle falls away to the right
    rw = AW @ pbW.matrix @ K_RIFLE
    fall = (Matrix.Translation(V(0.25 * k2, 0.35 * k2, -1.05 * k2 - 0.25 * k1))
            @ Matrix.Translation(rw.to_translation())
            @ Euler((math.radians(-20 * k2), math.radians(85 * k2), math.radians(40 * k2)), "XYZ")
            .to_matrix().to_4x4()
            @ Matrix.Translation(-rw.to_translation()))
    place_weapon(fall @ rw)


if not QUICK:
    acts.append(bake("Death", [float(i) for i in range(31)], death_pose))
for side in ("Left", "Right"):
    arm.pose.bones[B(side + "ForeArm")].constraints["ArmIK"].influence = 1
    arm.pose.bones[B(side + "Hand")].constraints["HandRot"].influence = 1

# --------------------------------------------------------------------------------------
# Previews (optional)
# --------------------------------------------------------------------------------------


def apply_action(act, frame):
    arm.animation_data.action = act
    if act.slots:
        arm.animation_data.action_slot = act.slots[0]
    scn.frame_set(frame)


def remove_constraints():
    for pb in ALL:
        for c in list(pb.constraints):
            pb.constraints.remove(c)


remove_constraints()
for o in (tgtR, tgtL, poleR, poleL):
    bpy.data.objects.remove(o, do_unlink=True)

if PREVIEW:
    apply_action(acts[0], 1)
    eye = eye_empty.matrix_world.to_translation()
    arm.animation_data.action = None
    arm.pose.bones[B("Head")].scale = (0.001, 0.001, 0.001)
    visor.hide_render = True
    U.preview(PREVIEW + "_fp.png", target=eye + V(0, 1, 0), cam_loc=eye, lens=24, res=(800, 450), samples=12)
    print("EYE", eye, "headworld", bone_world(arm.pose.bones[B("Head")]).to_translation())
    U.preview(PREVIEW + "_fp_side.png", target=eye + V(0, 0.2, -0.2), cam_loc=eye + V(1.5, 0.3, 0.2), lens=35,
              res=(600, 600), samples=8)
    arm.pose.bones[B("Head")].scale = (1, 1, 1)
    visor.hide_render = False
    apply_action(acts[2], 1)
    hands = (AW @ pbW.matrix).to_translation()
    U.preview(PREVIEW + "_aim.png", target=V(0, 0.1, 1.35), cam_loc=V(-1.6, 1.6, 1.6), lens=50,
              res=(600, 600), samples=12)
    U.preview(PREVIEW + "_aim_side.png", target=V(0, 0.1, 1.35), cam_loc=V(1.8, 0.4, 1.5), lens=50,
              res=(600, 600), samples=12)
    U.preview(PREVIEW + "_hand_r.png", target=hands + V(0, -0.05, -0.05), cam_loc=hands + V(0.6, 0.0, -0.1),
              lens=60, res=(600, 600), samples=12)
    U.preview(PREVIEW + "_hand_l.png", target=hands + V(0, 0.15, -0.03), cam_loc=hands + V(-0.4, 0.4, -0.35),
              lens=60, res=(600, 600), samples=12)
    if QUICK:
        sys.exit(0)
    names = {a.name: a for a in acts}
    for fr in (1, 10, 16, 24, 34, 44, 55):
        apply_action(names["FP_Reload"], fr)
        e = eye_empty.matrix_world.to_translation()
        U.preview(PREVIEW + f"_reload_{fr:02d}.png", target=e + V(0, 0.4, -0.2),
                  cam_loc=e + V(-0.9, 0.9, 0.1), lens=35, res=(360, 360), samples=6)
    for fr in (1, 8, 14, 20, 31):
        apply_action(names["Death"], fr)
        U.preview(PREVIEW + f"_death_{fr:02d}.png", target=V(0, 0, 0.8), cam_loc=V(3.5, 1.0, 1.3),
                  lens=35, res=(360, 360), samples=6)
    for fr in (1, 9):
        apply_action(names["AIM_Run"], fr)
        U.preview(PREVIEW + f"_run_{fr:02d}.png", target=V(0, 0, 1.0), cam_loc=V(3.0, 1.2, 1.4),
                  lens=35, res=(360, 360), samples=6)

# --------------------------------------------------------------------------------------
# Export
# --------------------------------------------------------------------------------------
for name in ("Idle", "Walk", "Run", "TPose"):
    bpy.data.actions.remove(base_actions[name])
arm.animation_data.action = None
for act in acts:
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
print("EXPORTED", OUT, [a.name for a in acts])
