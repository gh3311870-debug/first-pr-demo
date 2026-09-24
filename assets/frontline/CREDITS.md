# Frontline: Dust Veil — credits & sources

Everything used to make the game: where it came from, its license, and what was
made from scratch.

## Free assets downloaded

| Asset | Used for | Source | License |
|---|---|---|---|
| `Soldier.glb` (rigged soldier character + Idle / Walk / Run animations) | Enemy soldiers and the first-person arms | [three.js examples](https://github.com/mrdoob/three.js/tree/dev/examples/models/gltf) (Mixamo-rigged character) | Distributed with the MIT-licensed three.js repo; the character and rig originate from Adobe Mixamo |
| `brick_diffuse.jpg`, `brick_bump.jpg`, `brick_roughness.jpg` | Brick houses and ruined walls (`tex/brick_*`) | [three.js examples/textures](https://github.com/mrdoob/three.js/tree/dev/examples/textures) | three.js repo (MIT) |
| `hardwood2_diffuse.jpg`, `hardwood2_bump.jpg`, `hardwood2_roughness.jpg` | Crates, pallets, door/window frames, watchtowers (`tex/wood_*`) | three.js examples/textures | three.js repo (MIT) |
| `opengameart/smoke1.png` | Dust and smoke particles (`tex/smoke.png`) | three.js examples/textures (originally from OpenGameArt) | Public domain / CC0 per OpenGameArt |
| three.js r186 + add-ons (GLTFLoader, Sky, EffectComposer, GTAOPass, SMAAPass, SkeletonUtils...) | Rendering engine (`vendor/three-r186/`) | [npm: three@0.186.0](https://www.npmjs.com/package/three) | MIT (`vendor/three-r186/LICENSE`) |

## Made in Blender (Blender 5.0 Python API, `bpy`)

All Blender work is scripted, so it can be rebuilt from `tools/frontline/`:

- **`rifle.py` — M4-style carbine**, modeled from primitives, booleans and bevels:
  upper/lower receiver, Picatinny rails with individual teeth, M-LOK handguard with
  boolean-cut slots, barrel, slotted flash hider, forward assist, charging handle,
  collapsible stock with lightening cut, pistol grip, angled foregrip, curved
  magazine (Simple Deform bend), and a hollow red-dot optic with lens and reticle.
- **`build_operator.py` — character rig and animations**:
  - imports `Soldier.glb`, fixes the arm bone lengths, and adds `Weapon` and `Mag` bones
  - parents the rifle and magazine to those bones
  - drives both arms with **IK constraints** and hand-rotation constraints so the
    hands really grip the pistol grip and handguard
  - curls the fingers and twists the torso into a shooting stance, then bakes
    everything into keyframes
  - new animations made this way:
    - `FP_Hold` — first-person hold
    - `FP_Reload` — magazine out, swap, insert, slap
    - `AIM_Idle`, `AIM_Walk` — rifle shouldered
    - `AIM_Run` — low ready
    - `Death` — knees buckle, fall back, rifle drops
- **`build_props.py` — level props**: wooden crate, ammo box, oil drum, sandbag
  wall, jersey barrier, HESCO bastion, 20 ft shipping container (corrugated walls,
  doors, lock bars, corner castings), pallet, tire, burned-out car, watchtower
  (legs, braces, parapet, roof, ladder, sandbags), date palm (bent ringed trunk and
  drooping fronds), power pole, rooftop water tank, AC unit and jerry cans.
- `blender_util.py` — shared helpers (bevels, booleans, smoothing, box/cylinder
  UVs, Cycles preview renders used to check every model).

## Generated with Python (NumPy / SciPy)

`tools/frontline/make_textures.py` generates seamless PBR texture sets (albedo +
normal + AO/roughness/metal) from spectral noise and Worley cells:

- sand
- dirt/gravel
- cracked plaster
- concrete
- painted/rusted metal
- burnt metal
- burlap (sandbags)
- HESCO geotextile with wire mesh
- palm bark

Also RGBA sprites: palm leaf, dry shrub, bullet hole, blood splatter, muzzle flash,
soft particle.

## Made in code (JavaScript, `frontline/`)

- Level layout, buildings (doors, windows, frames, iron bars, roof parapets,
  stairs), terrain with dunes and distant ridges, road mask, market stalls, power
  lines — `level.js`
- Physical sky, sun, image-based lighting from the sky, shadows, GTAO, colour grade —
  `engine.js`
- **All sound is synthesized live** with the Web Audio API — `audio.js`:
  - layered gunshots with speed-of-sound delay and air absorption for distant shots
  - outdoor echo reverb
  - supersonic bullet cracks
  - impact sounds for each surface type
  - footsteps, reload sounds, wind, heartbeat, tinnitus when hit
- Enemy AI (sight and hearing, awareness, A* navigation, burst fire, suppression) —
  `enemies.js`
