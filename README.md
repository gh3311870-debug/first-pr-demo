# first-pr-demo

A tiny sandbox repo for practicing the GitHub pull request workflow.

## What this is

This repo exists so you can experience the full loop of branching, committing,
and opening a pull request without touching real production code.

## Getting started

1. Clone the repo.
2. Make a change on a new branch.
3. Open a pull request.
4. Review and merge it.

## Blockcraft Mobile demo

`index.html` is a small mobile-friendly voxel building game (à la Minecraft),
built with Three.js. It runs entirely in the browser with touch controls:

- Left on-screen joystick: walk
- Drag on the right side of the screen: look around
- Jump button: jump
- Place / Break buttons: build or remove blocks in front of you (with sound
  effects)
- Top bar: pick which block type to place

To try it locally, serve the repo over HTTP (opening the file directly won't
load the vendored script due to browser security restrictions) and open it on
your phone or in a mobile emulation view:

```
python3 -m http.server 8000
```

Then visit `http://localhost:8000/index.html`.

## Range Shooter demo

`fps.html` is a mobile-friendly first-person shooting range, also built with
Three.js. Move around a small arena and shoot targets before the 60-second
timer runs out:

- Left on-screen joystick: walk
- Drag on the right side of the screen: look around
- Up-arrow button: jump (with sound)
- Red SHOOT button: fire at whatever's under the crosshair, with recoil,
  muzzle flash, tracers, impact particles, and sound effects
- Top bar: live score and time remaining

Targets are humanoid silhouettes standing in a shadowed, textured arena, and
the player has gravity, jumping, and a walking head-bob for a more grounded
feel.

Serve it the same way as the builder demo and visit
`http://localhost:8000/fps.html`.

## Skyblast demo

`powers.html` is a mobile-friendly superpower flight game, also built with
Three.js. Fly freely through an open sky arena — complete with a gradient
sky, sun glow, and drifting clouds — and blast glowing "energy crystal"
target drones before the 60-second timer runs out:

- Left on-screen joystick: fly forward/back and strafe left/right
- Drag on the right side of the screen: aim — flight direction follows
  wherever you're looking, including up and down
- Gold BOOST button (hold): temporary speed burst with a particle trail and
  sound
- Blue BLAST button: fire a glowing energy projectile at the crosshair from
  your glowing power hands, with sound effects and a shockwave on impact
- Top bar: live score and time remaining

Serve it the same way as the other demos and visit
`http://localhost:8000/powers.html`.

## Zombie Siege demo

`zombies.html` is a mobile-friendly wave-based zombie shooter, also built
with Three.js. Defend a moonlit arena as shambling zombies close in from
every side — survive as many waves as you can:

- Left on-screen joystick: walk
- Drag on the right side of the screen: look around
- Up-arrow button: jump (with sound)
- Green SHOOT button: fire at whatever's under the crosshair, with recoil,
  muzzle flash, tracers, impact particles, and sound effects
- Circular &#8635; button: cycle weapons — **Pistol** (balanced), **Shotgun**
  (six-pellet spread, devastating up close), **SMG** (fast, low-damage
  full-auto-feel tapping), **Sniper** (slow, huge single-target damage and
  extra range), **Laser** (a glowing energy rifle that evaporates
  zombies in a burst of light instead of leaving a corpse), **Sword** (a
  close-range melee blade — swing it at a zombie standing in front of you
  to lop off a limb in a spray of blood, and finish them off with enough
  hits, occasionally taking the head clean off), **Rocket Launcher** (a
  slow-firing rocket that streaks out with a smoke trail and detonates in a
  blunt, debris-and-smoke-filled ordnance blast — a brief white-hot flash
  followed by dark soot, dirt and a slow dust shockwave rather than a fiery
  glow, so it reads as a real explosion rather than the Fireball ability's
  magical burst. Anything caught in the splash radius is blown apart, limbs
  and all, and multiple zombies can go down in one shot), and
  **Flamethrower** (hold the SHOOT button to spray a continuous cone of fire
  — zombies caught in the stream catch alight and keep taking burn damage
  for a few seconds afterward even if you stop hitting them, with a
  flickering orange glow while they burn). Each weapon has its own saturated
  neon tracer color, viewmodel, recoil, screen shake, and sound —
  muzzle flashes and bullet impacts light up in that same color.
- Purple &#9889; button: unleash a **Lightning** ability — a heavy-damage
  neon-violet bolt that chains to every zombie within range of you at once,
  on an ~11-second cooldown (shown on the button). Great for breaking up a
  crowd that's closed in around you.
- Orange &#128293; button: hurl a **Fireball** — a glowing projectile that
  streaks out with an ember trail and explodes in a shockwave on impact,
  dealing splash damage to every zombie caught in the blast radius. ~8-second
  cooldown.
- Gold &#9728;&#65039; button: the ultimate — **Supernova**. Time briefly
  slows as energy implodes into your chest, then it detonates: a blinding
  full-screen flash, an expanding white-hot core, three color-shifting
  shockwave rings (white &rarr; cyan &rarr; violet), a huge burst of embers
  in every direction, and a massive dynamic light — instantly vaporizing
  every zombie on the map. ~25-second cooldown; save it for when you're
  overwhelmed.
- Top bar: live score, current wave, and a health bar
- Zombies groan, shamble toward you, and attack (damaging your health) when
  they get close; each wave brings more, slightly faster zombies. The run
  ends when your health hits zero.
- Clearing a wave pauses the action for an upgrade pick: choose one of three
  random perks — more weapon damage, more max health (plus a full heal),
  faster movement, shorter ability cooldowns, or faster weapon fire rate —
  before the next wave begins. Perks stack across the whole run, so a long
  survival snowballs into a much stronger loadout.
- Headshots (aim for the head) deal triple damage and score a bonus, with a
  "HEADSHOT" callout. Landing kills in quick succession triggers "DOUBLE
  KILL" / "TRIPLE KILL" combo callouts.
- Four zombie types spawn as waves progress: shambling **Walkers**, fast
  low-health **Runners** (from wave 1), acid-lobbing **Spitters** that keep
  their distance and attack from range (from wave 2), and towering crimson
  **Brutes** with much more health and a harder hit (from wave 3).
  Wounded zombies bleed as they stagger toward you.
- A large abandoned town: dead, dry grass instead of a lawn, half a dozen
  gutted brick houses with boarded-up windows you can walk and fight
  through, dead leafless trees scattered around, a leaning-tombstone
  graveyard, a crate barricade, and a central rubble pile for cover.
- Kills leave blood splatter pools on the ground, burst into flying gore
  chunks and a fine blood mist, and occasionally dismember — heads or arms
  can fly off and tumble away with physics, with zombies collapsing in a
  ragdoll fall and lingering as corpses instead of vanishing.
  Through-and-through shots splatter blood on nearby walls and crates too,
  and a close-range kill splashes blood across the screen itself.
- Layered, punchier sound effects: gunshots blend a crack, a body thump,
  and a tail for a more realistic report, each with pitch variance so shots
  don't sound identical; kills and dismemberment get their own meaty,
  filtered-noise squelches instead of a single tone.
- More shooting feedback: drifting muzzle smoke, ejected shell casings, and
  a pulsing red vignette when your health drops critically low.
- Filmic tone mapping and brighter moonlight/fill lighting for a punchier,
  higher-contrast look. Every shot and ability casts its own colored neon
  dynamic light — matching its tracer/bolt/fireball color — that actually
  lights up nearby walls and zombies instead of just being a flat overlay.
  Bullet tracers are bright glowing neon-tube beams (a white-hot core plus a
  colored glow layer) rather than thin lines, and
  bullet/spark impacts on walls and crates now throw actual glowing sparks.
- A cyberpunk-styled HUD: a cyan/magenta chromatic "glitch text" look on the
  score, wave, and labels; a bracket-style neon reticle; a segmented neon
  health bar that shifts from cyan-green to magenta-red when critical; faint
  always-on scanlines; and a two-tone cyan-key/magenta-rim lighting setup
  across the whole arena. Buttons give tactile press feedback when tapped.

Serve it the same way as the other demos and visit
`http://localhost:8000/zombies.html`.

All four demos link to each other via the nav chips in the top-right corner.

### Playing on your phone via GitHub Pages

To play without running a local server, enable GitHub Pages for this repo:

1. Go to the repo's **Settings > Pages**.
2. Under "Build and deployment", set **Source** to "Deploy from a branch".
3. Pick branch `main`, folder `/ (root)`, then **Save**.
4. After a minute, all four demos will be live at
   `https://gh3311870-debug.github.io/first-pr-demo/index.html` (builder),
   `https://gh3311870-debug.github.io/first-pr-demo/fps.html` (shooter),
   `https://gh3311870-debug.github.io/first-pr-demo/powers.html` (flight),
   and `https://gh3311870-debug.github.io/first-pr-demo/zombies.html`
   (zombie siege) — open any of them on your phone.

Each merge to `main` kicks off a fresh Pages deployment automatically. It
usually finishes in under a minute, but if a page seems to be missing a
change you just merged, check the repo's **Actions** tab — occasionally a
deployment run stalls or fails and needs a manual "Re-run jobs" to pick up
the latest commit.

## License

This project has no license yet — add one if you plan to use this code elsewhere.
