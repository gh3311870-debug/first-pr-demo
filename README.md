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
- Top bar: live score, current wave, and a health bar
- Zombies groan, shamble toward you, and attack (damaging your health) when
  they get close; each wave brings more, slightly faster zombies. The run
  ends when your health hits zero.
- Headshots (aim for the head) deal triple damage and score a bonus, with a
  "HEADSHOT" callout. Landing kills in quick succession triggers "DOUBLE
  KILL" / "TRIPLE KILL" combo callouts.
- Four zombie types spawn as waves progress: shambling **Walkers**, fast
  low-health **Runners** (from wave 1), acid-lobbing **Spitters** that keep
  their distance and attack from range (from wave 2), and towering crimson
  **Brutes** with much more health and a harder hit (from wave 3).
  Wounded zombies bleed as they stagger toward you.
- Kills leave blood splatter pools on the ground, burst into flying gore
  chunks, and occasionally dismember (heads can fly off), with zombies
  collapsing in a ragdoll fall instead of just vanishing.
- More shooting feedback: drifting muzzle smoke, ejected shell casings, and
  a pulsing red vignette when your health drops critically low.

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

## License

This project has no license yet — add one if you plan to use this code elsewhere.
