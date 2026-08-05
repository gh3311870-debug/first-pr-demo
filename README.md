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

## License

This project has no license yet — add one if you plan to use this code elsewhere.
