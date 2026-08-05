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
- Place / Break buttons: build or remove blocks in front of you
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
- Up-arrow button: jump
- Red SHOOT button: fire at whatever's under the crosshair (with recoil, muzzle
  flash, tracers, and impact particles)

Targets are humanoid silhouettes standing in a shadowed, textured arena, and
the player has gravity, jumping, and a walking head-bob for a more grounded
feel.
- Top bar: live score and time remaining

Serve it the same way as the builder demo and visit
`http://localhost:8000/fps.html`.

### Playing on your phone via GitHub Pages

To play without running a local server, enable GitHub Pages for this repo:

1. Go to the repo's **Settings > Pages**.
2. Under "Build and deployment", set **Source** to "Deploy from a branch".
3. Pick branch `main`, folder `/ (root)`, then **Save**.
4. After a minute, both demos will be live at
   `https://gh3311870-debug.github.io/first-pr-demo/index.html` (builder) and
   `https://gh3311870-debug.github.io/first-pr-demo/fps.html` (shooter) —
   open either on your phone.

## License

This project has no license yet — add one if you plan to use this code elsewhere.
