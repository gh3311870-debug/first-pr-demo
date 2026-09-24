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
| Recorded sound effects (`sounds/*.wav`): rifle, DMR and shotgun shots, reload, dry fire, impacts on stone/metal/wood/flesh, ricochets, brass casings, footsteps | All gun, impact, reload and footstep sounds | [Xonotic game data](https://github.com/xonotic/xonotic-data.pk3dir) (`sound/weapons`, `sound/object`, `sound/misc`), converted by `tools/frontline/prepare_sounds.py` | GNU GPL v3 or later (`sounds/GPL-3.0.txt`) |
| three.js r186 + add-ons (GLTFLoader, Sky, EffectComposer, GTAOPass, SMAAPass, SkeletonUtils...) | Rendering engine (`vendor/three-r186/`) | [npm: three@0.186.0](https://www.npmjs.com/package/three) | MIT (`vendor/three-r186/LICENSE`) |

## Made in Blender (Blender 5.0 Python API, `bpy`)

All Blender work is scripted, so it can be rebuilt from `tools/frontline/`:

- **`rifle.py` — M4 carbine and MK20 DMR** (one parameterized builder), modeled from primitives, booleans and bevels:
  upper/lower receiver, Picatinny rails with individual teeth, M-LOK handguard with
  boolean-cut slots, barrel, slotted flash hider, forward assist, charging handle,
  collapsible stock with lightening cut, pistol grip, angled foregrip, curved
  magazine (Simple Deform bend), and a hollow red-dot optic with lens and reticle.
  The DMR variant has a 20" barrel, tan Cerakote finish, a 3-9x scope on high rings, a
  folded bipod and a 20-round box magazine.
- **`weapons_extra.py` — pump shotgun and pistol**: Mossberg 590-style shotgun (ghost-ring
  sight, ribbed sliding pump with action bars, side saddle with shells, pistol-grip stock)
  and a Glock/M17-style pistol (serrated slide, 3-dot sights, removable magazine).
- **`build_operator.py` — character rig and animations**:
  - imports `Soldier.glb`, fixes the arm bone lengths, and adds `Weapon` and `Mag` bones
  - parents the rifle and magazine to those bones
  - drives both arms with **IK constraints** and hand-rotation constraints so the
    hands really grip the pistol grip and handguard
  - curls the fingers and twists the torso into a shooting stance, then bakes
    everything into keyframes
  - new animations made this way, for all four weapons:
    - `FP_Hold_*` — first-person hip hold
    - `FP_ADS_*` — aim-down-sights pose (arms raise the weapon to the eye)
    - `FP_Reload_*` — M4, DMR and pistol magazine reloads
    - `FP_Pump_SG`, `FP_ReloadStart/Shell/End_SG` — shotgun pump and shell-by-shell loading
    - `AIM_Idle`, `AIM_Walk` (+ `_SG`) — shouldered, for enemies and the squad
    - `AIM_Run` (+ `_SG`) — low ready
    - `Death` — knees buckle, fall back, weapon drops
  - rifle and shotgun stances twist the torso; the pistol uses a square isosceles stance
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
- **Sound playback** with the Web Audio API — `audio.js`:
  - the recorded Xonotic samples above, positioned in 3D
  - distant shots arrive late (speed of sound) and duller (air absorption)
  - outdoor echo reverb
  - synthesized: supersonic bullet cracks, wind, heartbeat, tinnitus when hit, hit markers
- Soldier AI for both teams (sight and hearing, awareness, A* navigation, burst fire,
  marksmen and shotgunners, suppression, squad following, free-for-all) — `enemies.js`
