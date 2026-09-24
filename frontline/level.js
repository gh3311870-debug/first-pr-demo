// "Dust Veil" map: a walled desert village built from boxes (buildings) and Blender props.
import * as THREE from "../vendor/three-r186/three-bundle.min.js";
import { World, NavGrid } from "./physics.js";

// texture tile sizes in meters (UVs are generated in meters)
const TILE = { sand: 4, dirt: 3, plaster: 2.5, concrete: 3, paint: 2.5, burnt: 2, wood: 1.5, brick: 2 };

export const PLAY_HALF = 72;

function rand(seed) {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// ----------------------------------------------------------------------------------------
// Geometry batching: faces are accumulated per material, then merged into one mesh each.
class Batch {
  constructor() {
    this.parts = new Map();
  }

  _arr(key) {
    let p = this.parts.get(key);
    if (!p) this.parts.set(key, (p = { pos: [], nrm: [], uv: [] }));
    return p;
  }

  quad(key, a, b, c, d, n, uvs) {
    const p = this._arr(key);
    for (const [v, uv] of [[a, uvs[0]], [b, uvs[1]], [c, uvs[2]], [a, uvs[0]], [c, uvs[2]], [d, uvs[3]]]) {
      p.pos.push(v[0], v[1], v[2]);
      p.nrm.push(n[0], n[1], n[2]);
      p.uv.push(uv[0], uv[1]);
    }
  }

  // Axis-aligned box with world-space UVs. matFn(nx, ny, nz) -> material key or null to skip face.
  box(x0, y0, z0, x1, y1, z1, matFn) {
    const faces = [
      [[1, 0, 0], [[x1, y0, z1], [x1, y0, z0], [x1, y1, z0], [x1, y1, z1]], (v) => [-v[2], v[1]]],
      [[-1, 0, 0], [[x0, y0, z0], [x0, y0, z1], [x0, y1, z1], [x0, y1, z0]], (v) => [v[2], v[1]]],
      [[0, 1, 0], [[x0, y1, z1], [x1, y1, z1], [x1, y1, z0], [x0, y1, z0]], (v) => [v[0], -v[2]]],
      [[0, -1, 0], [[x0, y0, z0], [x1, y0, z0], [x1, y0, z1], [x0, y0, z1]], (v) => [v[0], v[2]]],
      [[0, 0, 1], [[x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]], (v) => [v[0], v[1]]],
      [[0, 0, -1], [[x1, y0, z0], [x0, y0, z0], [x0, y1, z0], [x1, y1, z0]], (v) => [-v[0], v[1]]],
    ];
    for (const [n, vs, uvf] of faces) {
      const key = typeof matFn === "string" ? matFn : matFn(n[0], n[1], n[2]);
      if (!key) continue;
      const tile = TILE[baseKey(key)] || 1;
      this.quad(key, vs[0], vs[1], vs[2], vs[3], n, vs.map((v) => uvf(v).map((c) => c / tile)));
    }
  }

  build(materials) {
    const group = new THREE.Group();
    for (const [key, p] of this.parts) {
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.Float32BufferAttribute(p.pos, 3));
      g.setAttribute("normal", new THREE.Float32BufferAttribute(p.nrm, 3));
      g.setAttribute("uv", new THREE.Float32BufferAttribute(p.uv, 2));
      g.computeBoundingSphere();
      const mat = materials[key];
      if (!mat) console.warn("missing material", key);
      const mesh = new THREE.Mesh(g, mat);
      mesh.castShadow = key !== "canvas";
      mesh.receiveShadow = true;
      mesh.name = "batch_" + key;
      group.add(mesh);
    }
    return group;
  }
}

function baseKey(k) {
  if (k.startsWith("plaster")) return "plaster";
  if (k === "floor") return "concrete";
  return k;
}

// ----------------------------------------------------------------------------------------
export class Level {
  constructor(engine, assets) {
    this.engine = engine;
    this.assets = assets;
    this.scene = engine.scene;
    this.world = new World();
    this.batch = new Batch();
    this.propInstances = new Map(); // prop name -> [{matrix, color}]
    this.enemySpawns = [];
    this.rng = rand(1337);
    this.materials = this._materials();
    this.propTemplates = this._propTemplates();
  }

  _materials() {
    const M = this.assets.materials;
    const set = (tex, tile) => {
      for (const k of ["map", "normalMap", "roughnessMap", "bumpMap", "metalnessMap"]) {
        if (tex[k]) tex[k].repeat.set(1, 1);
      }
      return tile;
    };
    // UVs are generated already divided by tile size, but Blender props use meters:
    // prop materials get texture repeat = 1 / tile.
    const rep = (mat, tile) => {
      for (const k of ["map", "normalMap", "roughnessMap", "bumpMap", "metalnessMap"]) {
        if (mat[k]) mat[k].repeat.set(1 / tile, 1 / tile);
      }
    };
    set(M.plaster);
    // props (Blender UVs in meters)
    rep(M.wood, TILE.wood);
    rep(M.paint, TILE.paint);
    rep(M.burnt, TILE.burnt);
    rep(M.concrete, TILE.concrete);
    // JS-built geometry shares the same textures, so it uses meter UVs too for those.
    this.meterUV = new Set(["wood", "paint", "burnt", "concrete", "floor"]);
    return {
      plaster: M.plaster,
      plasterInterior: M.plasterInterior,
      concrete: M.concrete,
      floor: M.concrete,
      wood: M.wood,
      brick: M.brick,
      darkMetal: M.darkMetal,
      canvas: M.canvas,
      paint: M.paint,
      galv: M.galv,
    };
  }

  // Batch.box divides UVs by tile, but for materials whose textures are shared with props
  // (repeat = 1/tile) we must emit meter UVs instead.
  box(x0, y0, z0, x1, y1, z1, matFn, surface, collide = true, opts) {
    const fn = typeof matFn === "string" ? () => matFn : matFn;
    const wrapped = (nx, ny, nz) => {
      const k = fn(nx, ny, nz);
      return k && this.meterUV.has(k) ? "m:" + k : k;
    };
    this.batch.box(x0, y0, z0, x1, y1, z1, wrapped);
    if (collide) this.world.add(x0, y0, z0, x1, y1, z1, surface || "plaster", opts);
  }

  // ------------------------------------------------------------------------------------
  build() {
    this._terrain();
    this._perimeter();
    this._buildings();
    this._market();
    this._props();
    this._vegetation();
    this._powerLines();
    // merge batched geometry
    const mats = { ...this.materials };
    for (const k of this.meterUV) mats["m:" + k] = this.materials[k];
    const batched = this._fixMeterUVs().build(mats);
    this.scene.add(batched);
    this._instanceProps();
    this.nav = new NavGrid(this.world, PLAY_HALF + 2, 1);
    return this;
  }

  _fixMeterUVs() {
    // Batch.box divided UVs by TILE for "m:" keys too (unknown tile -> 1), nothing to fix.
    return this.batch;
  }

  // ------------------------------------------------------------------------------------
  _terrain() {
    const size = 1800;
    const seg = 180;
    const g = new THREE.PlaneGeometry(size, size, seg, seg);
    g.rotateX(-Math.PI / 2);
    const pos = g.attributes.position;
    const uv = g.attributes.uv;
    const noise = makeNoise(99);
    for (let i = 0; i < pos.count; i++) {
      const x = pos.getX(i);
      const z = pos.getZ(i);
      const r = Math.max(Math.abs(x), Math.abs(z));
      const rr = Math.hypot(x, z);
      let h = 0;
      const t = THREE.MathUtils.smoothstep(r, PLAY_HALF + 8, PLAY_HALF + 70);
      // dunes
      h += t * (noise(x * 0.012, z * 0.012) * 14 + noise(x * 0.04, z * 0.04) * 3 + 4);
      // distant ridge line
      const m = THREE.MathUtils.smoothstep(rr, 380, 700);
      h += m * (noise(x * 0.004 + 3, z * 0.004) * 120 + 60) * (0.6 + 0.4 * noise(x * 0.01, z * 0.01));
      pos.setY(i, Math.max(0, h) - (r < PLAY_HALF + 6 ? 0 : 0.02));
      uv.setXY(i, x / TILE.sand, -z / TILE.sand);
    }
    g.computeVertexNormals();
    const mat = this._terrainMaterial();
    const mesh = new THREE.Mesh(g, mat);
    mesh.receiveShadow = true;
    mesh.name = "terrain";
    this.scene.add(mesh);
    this.terrain = mesh;
  }

  _terrainMaterial() {
    const A = this.assets;
    const M = A.materials;
    const mat = M.sand;
    // road / track mask painted on a canvas covering the playable area
    const S = 512;
    const cv = document.createElement("canvas");
    cv.width = cv.height = S;
    const ctx = cv.getContext("2d");
    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, S, S);
    const span = 180;
    const w2c = (v) => ((v + span / 2) / span) * S;
    const road = (pts, width, alpha) => {
      ctx.strokeStyle = `rgba(255,255,255,${alpha})`;
      ctx.lineWidth = (width / span) * S;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      ctx.beginPath();
      pts.forEach(([x, z], i) => (i ? ctx.lineTo(w2c(x), w2c(z)) : ctx.moveTo(w2c(x), w2c(z))));
      ctx.stroke();
    };
    ctx.filter = "blur(3px)";
    road([[0, 90], [0, 30], [1, 0], [-1, -30], [0, -70]], 8, 1);
    road([[-70, 1], [-30, 0], [0, 0], [30, 2], [70, 0]], 7, 1);
    road([[0, 30], [20, 32], [20, 45]], 4, 0.8);
    road([[0, -20], [22, -22]], 5, 0.8);
    road([[-2, -40], [-4, -46]], 6, 0.8);
    road([[-30, 0], [-26, 10]], 4, 0.7);
    // courtyards and trampled areas
    ctx.fillStyle = "rgba(255,255,255,0.55)";
    for (const [x, z, r] of [[0, 0, 10], [-24, 8, 7], [44, 0, 9], [22, -24, 8], [-4, -44, 8], [0, 48, 7]]) {
      ctx.beginPath();
      ctx.ellipse(w2c(x), w2c(z), (r / span) * S, (r / span) * S * 0.8, 0.3, 0, Math.PI * 2);
      ctx.fill();
    }
    // tyre tracks: darker thin lines inside the main road (blue channel)
    ctx.filter = "blur(1px)";
    ctx.globalCompositeOperation = "lighter";
    ctx.strokeStyle = "rgba(0,0,255,0.7)";
    ctx.lineWidth = 1.2;
    for (const off of [-1.1, 1.1]) {
      ctx.beginPath();
      ctx.moveTo(w2c(off), w2c(90));
      ctx.lineTo(w2c(off + 1), w2c(0));
      ctx.lineTo(w2c(off - 1), w2c(-60));
      ctx.stroke();
    }
    const mask = new THREE.CanvasTexture(cv);
    mask.colorSpace = THREE.NoColorSpace;
    const dirtMap = A.tex("dirt_col.jpg", { srgb: true });
    mat.onBeforeCompile = (shader) => {
      shader.uniforms.roadMask = { value: mask };
      shader.uniforms.dirtMap = { value: dirtMap };
      shader.vertexShader = shader.vertexShader
        .replace("#include <common>", "#include <common>\nvarying vec2 vWorldXZ;")
        .replace("#include <worldpos_vertex>", "#include <worldpos_vertex>\nvWorldXZ = (modelMatrix * vec4(transformed, 1.0)).xz;");
      shader.fragmentShader = shader.fragmentShader
        .replace("#include <common>", "#include <common>\nvarying vec2 vWorldXZ;\nuniform sampler2D roadMask;\nuniform sampler2D dirtMap;")
        .replace("#include <map_fragment>",
          `#include <map_fragment>
           vec2 muv = vWorldXZ / ${span.toFixed(1)} + 0.5;
           vec4 mk = texture2D(roadMask, muv);
           float inside = step(0.0, muv.x) * step(muv.x, 1.0) * step(0.0, muv.y) * step(muv.y, 1.0);
           vec3 dcol = texture2D(dirtMap, vWorldXZ / ${TILE.dirt.toFixed(1)}).rgb;
           float nz = texture2D(map, vWorldXZ * 0.05).r;
           float road = smoothstep(0.25, 0.75, mk.r + (nz - 0.5) * 0.5) * inside;
           diffuseColor.rgb = mix(diffuseColor.rgb, dcol, road * 0.9);
           diffuseColor.rgb *= 1.0 - mk.b * inside * 0.35;
           vec3 macro = texture2D(map, vWorldXZ * 0.021).rgb;
           vec3 macro2 = texture2D(map, vWorldXZ * 0.0065 + 0.37).rgb;
           float lm = dot(macro, vec3(0.333)) + dot(macro2, vec3(0.333));
           diffuseColor.rgb *= 0.42 + 0.46 * lm;`);
    };
    mat.customProgramCacheKey = () => "terrain";
    return mat;
  }

  // ------------------------------------------------------------------------------------
  _perimeter() {
    const H = PLAY_HALF;
    const unit = 4.24;
    const place = (x, z, rotY) => {
      this.addProp("Hesco", x, 0, z, rotY, { collide: false });
      this.addProp("Hesco", x, 1.37, z, rotY, { collide: false });
    };
    for (let s = -H; s < H; s += unit) {
      const c = s + unit / 2;
      place(c, -H, 0);
      if (Math.abs(c) > 6) place(c, H, 0);
      place(-H, c, Math.PI / 2);
      place(H, c, Math.PI / 2);
    }
    const t = 1.06;
    this.world.add(-H - t / 2, 0, -H - t / 2, H + t / 2, 2.74, -H + t / 2, "sand");
    this.world.add(-H - t / 2, 0, H - t / 2, -6.4, 2.74, H + t / 2, "sand");
    this.world.add(6.4, 0, H - t / 2, H + t / 2, 2.74, H + t / 2, "sand");
    this.world.add(-H - t / 2, 0, -H, -H + t / 2, 2.74, H, "sand");
    this.world.add(H - t / 2, 0, -H, H + t / 2, 2.74, H, "sand");
    // the south gate is blocked by barriers outside + an invisible wall
    for (const x of [-4.5, -1.5, 1.5, 4.5]) this.addProp("Jersey", x, 0, H + 3, 0, {});
    this.world.add(-8, 0, H + 1, 8, 6, H + 2.2, "sand", { noNav: true });
    // gate posts
    for (const x of [-6.8, 6.8]) this.box(x - 0.4, 0, H - 0.4, x + 0.4, 4.0, H + 0.4, "concrete", "concrete");
  }

  // ------------------------------------------------------------------------------------
  // Building generator. Openings: {side, at, w, h, sill, floor}
  building(o) {
    const { x, z, w, d } = o;
    const floors = o.floors || 1;
    const FH = 3.2;
    const h = floors * FH;
    const T = 0.3;
    const x0 = x - w / 2;
    const x1 = x + w / 2;
    const z0 = z - d / 2;
    const z1 = z + d / 2;
    const ext = o.brick ? "brick" : "plaster";
    const matFor = (cx, cz) => (nx, ny, nz) => {
      if (ny < 0) return "plasterInterior";
      if (ny > 0) return ext;
      // faces pointing toward the building centre are interior
      return nx * (x - cx) + nz * (z - cz) > 0 ? "plasterInterior" : ext;
    };
    const openings = o.openings || [];
    const wall = (side) => {
      // wall runs along u from a to b; fixed coordinate f
      const horiz = side === "n" || side === "s";
      const a = horiz ? x0 : z0 + T;
      const b = horiz ? x1 : z1 - T;
      const f0 = side === "n" ? z0 : side === "s" ? z1 - T : side === "w" ? x0 : x1 - T;
      const f1 = f0 + T;
      const mk = (u0, u1, y0, y1) => {
        if (u1 - u0 < 0.01 || y1 - y0 < 0.01) return;
        if (horiz) this.box(u0, y0, f0, u1, y1, f1, matFor((u0 + u1) / 2, (f0 + f1) / 2), "plaster");
        else this.box(f0, y0, u0, f1, y1, u1, matFor((f0 + f1) / 2, (u0 + u1) / 2), "plaster");
      };
      for (let fl = 0; fl < floors; fl++) {
        const fy0 = fl * FH;
        const fy1 = fy0 + FH;
        const ops = openings
          .filter((op) => op.side === side && (op.floor || 0) === fl)
          .map((op) => {
            const c = (horiz ? x : z) + op.at;
            return { u0: c - op.w / 2, u1: c + op.w / 2, y0: fy0 + (op.sill || 0), y1: fy0 + (op.sill || 0) + op.h, op };
          })
          .sort((p, q) => p.u0 - q.u0);
        let u = a;
        for (const p of ops) {
          mk(u, p.u0, fy0, fy1);
          mk(p.u0, p.u1, fy0, p.y0);
          mk(p.u0, p.u1, p.y1, fy1);
          this._frame(side, p, f0, f1, horiz);
          u = p.u1;
        }
        mk(u, b, fy0, fy1);
      }
    };
    ["n", "s", "w", "e"].forEach(wall);
    // floors / roof
    this.box(x0 + T, -0.1, z0 + T, x1 - T, 0.03, z1 - T, "floor", "concrete", false);
    for (let fl = 1; fl <= floors; fl++) {
      const y = fl * FH;
      const roof = fl === floors;
      this.box(x0 - (roof ? 0.08 : 0), y - 0.25, z0 - (roof ? 0.08 : 0), x1 + (roof ? 0.08 : 0), y, z1 + (roof ? 0.08 : 0),
        (nx, ny) => (ny < 0 ? "plasterInterior" : ny > 0 ? "concrete" : ext), "concrete");
    }
    // roof parapet with gap for stairs
    const P = 0.55;
    const top = h;
    const gap = o.stairs ? o.stairs.side : null;
    const par = (px0, pz0, px1, pz1) => this.box(px0, top, pz0, px1, top + P, pz1, ext, "plaster");
    if (gap !== "n") par(x0 - 0.08, z0 - 0.08, x1 + 0.08, z0 + 0.17);
    if (gap !== "s") par(x0 - 0.08, z1 - 0.17, x1 + 0.08, z1 + 0.08);
    if (gap !== "w") par(x0 - 0.08, z0 + 0.17, x0 + 0.17, z1 - 0.17);
    if (gap !== "e") par(x1 - 0.17, z0 + 0.17, x1 + 0.08, z1 - 0.17);
    if (gap) {
      // parapet on the stair side, leaving the landing open
      const zl = this._stairs(o, h);
      if (gap === "w") par(x0 - 0.08, zl, x0 + 0.17, z1 - 0.17);
      else par(x1 - 0.17, zl, x1 + 0.08, z1 - 0.17);
    }
    // roof details: drain spouts, water tank, AC unit
    for (let i = 0; i < Math.floor(w / 4); i++) {
      const sx = x0 + 2 + i * 4;
      this.box(sx - 0.07, top - 0.3, z1 + 0.05, sx + 0.07, top - 0.16, z1 + 0.55, "wood", "wood", false);
    }
    if (o.tank) this.addProp("WaterTank", x1 - 1.4, top, z0 + 1.4, 0.3, { tint: null });
    if (o.ac) this.addProp("ACUnit", x0 + 1.2, top, z1 - 1.0, 0, {});
    if (o.awning) this._awning(o.awning, x, z, w, d);
    return { x0, x1, z0, z1, h };
  }

  _frame(side, p, f0, f1, horiz) {
    // wooden door / window frame trims on both faces
    const t = 0.07;
    const out = 0.04;
    const pieces = [[p.u0 - t, p.u0, p.y0, p.y1 + t], [p.u1, p.u1 + t, p.y0, p.y1 + t], [p.u0 - t, p.u1 + t, p.y1, p.y1 + t]];
    if (p.op.sill) pieces.push([p.u0 - t, p.u1 + t, p.y0 - t, p.y0]);
    for (const [u0, u1, y0, y1] of pieces) {
      for (const [a, b] of [[f0 - out, f0], [f1, f1 + out]]) {
        if (horiz) this.box(u0, y0, a, u1, y1, b, "wood", "wood", false);
        else this.box(a, y0, u0, b, y1, u1, "wood", "wood", false);
      }
    }
    // some windows get iron bars
    if (p.op.bars) {
      const n = Math.floor((p.u1 - p.u0) / 0.14);
      for (let i = 1; i < n; i++) {
        const u = p.u0 + (i * (p.u1 - p.u0)) / n;
        const c = (f0 + f1) / 2;
        if (horiz) this.box(u - 0.012, p.y0, c - 0.012, u + 0.012, p.y1, c + 0.012, "darkMetal", "metal", false);
        else this.box(c - 0.012, p.y0, u - 0.012, c + 0.012, p.y1, u + 0.012, "darkMetal", "metal", false);
      }
    }
    // open wooden door leaf against the inside wall
    if (p.op.door) {
      const leaf = p.u1 - p.u0;
      const inner = side === "n" || side === "w" ? f1 : f0;
      const dir = side === "n" || side === "w" ? 1 : -1;
      if (horiz) this.box(p.u0 - 0.05, 0.02, Math.min(inner, inner + dir * leaf), p.u0, p.y1 - 0.02, Math.max(inner, inner + dir * leaf), "wood", "wood", false);
      else this.box(Math.min(inner, inner + dir * leaf), 0.02, p.u0 - 0.05, Math.max(inner, inner + dir * leaf), p.y1 - 0.02, p.u0, "wood", "wood", false);
    }
  }

  _stairs(o, h) {
    const s = o.stairs;
    const { x, z, w, d } = o;
    const n = Math.ceil(h / 0.28);
    const rise = h / n;
    const run = Math.min(0.32, (d - 1.6) / n);
    const width = 1.2;
    for (let i = 0; i < n; i++) {
      const top = (i + 1) * rise;
      // stairs climb from the south end toward the north
      const zs = z + d / 2 - 0.2 - (i + 1) * run;
      const ze = zs + run;
      if (s.side === "w") this.box(x - w / 2 - width, 0, zs, x - w / 2, top, ze, "concrete", "concrete");
      else this.box(x + w / 2, 0, zs, x + w / 2 + width, top, ze, "concrete", "concrete");
    }
    // landing
    const zl = z + d / 2 - 0.2 - n * run;
    if (s.side === "w") this.box(x - w / 2 - width, 0, z - d / 2, x - w / 2, h, zl, "concrete", "concrete");
    else this.box(x + w / 2, 0, z - d / 2, x + w / 2 + width, h, zl, "concrete", "concrete");
    // low side wall along the open edge
    const ex = s.side === "w" ? x - w / 2 - width - 0.12 : x + w / 2 + width;
    for (let i = 0; i < n; i += 1) {
      const zs = z + d / 2 - 0.2 - (i + 1) * run;
      this.box(ex, (i + 1) * rise, zs, ex + 0.12, (i + 1) * rise + 0.9, zs + run, "concrete", "concrete", false);
    }
    return zl;
  }

  _awning(side, x, z, w, d) {
    // canvas awning on two posts in front of a doorway
    const len = 3.2;
    const depth = 2.2;
    const hgt = 2.5;
    const cx = x;
    const cz = side === "s" ? z + d / 2 : z - d / 2;
    const dir = side === "s" ? 1 : -1;
    for (const sx of [-len / 2, len / 2]) {
      this.box(cx + sx - 0.05, 0, cz + dir * depth - 0.05, cx + sx + 0.05, hgt - 0.3, cz + dir * depth + 0.05, "wood", "wood", true, { thin: true });
    }
    const g = new THREE.PlaneGeometry(len + 0.3, depth + 0.2, 6, 3);
    const pos = g.attributes.position;
    for (let i = 0; i < pos.count; i++) pos.setZ(i, Math.sin((pos.getX(i) / len) * Math.PI * 3) * 0.03);
    g.computeVertexNormals();
    const m = new THREE.Mesh(g, this.assets.materials.canvas);
    m.position.set(cx, hgt, cz + (dir * depth) / 2);
    m.rotation.x = -Math.PI / 2 + dir * 0.25;
    m.castShadow = true;
    m.receiveShadow = true;
    this.scene.add(m);
  }

  compoundWall(x0, z0, x1, z1, gates) {
    const T = 0.4;
    const H = 2.6;
    const seg = (ax, az, bx, bz) => {
      this.box(Math.min(ax, bx), 0, Math.min(az, bz), Math.max(ax, bx), H, Math.max(az, bz), "plaster", "plaster");
      this.box(Math.min(ax, bx) - 0.05, H, Math.min(az, bz) - 0.05, Math.max(ax, bx) + 0.05, H + 0.12, Math.max(az, bz) + 0.05, "concrete", "concrete");
    };
    const side = (name, a, b, fixed, horiz) => {
      const gs = gates.filter((g) => g.side === name).sort((p, q) => p.at - q.at);
      let u = a;
      for (const g of gs) {
        if (horiz) seg(u, fixed, g.at - g.w / 2, fixed + T);
        else seg(fixed, u, fixed + T, g.at - g.w / 2);
        u = g.at + g.w / 2;
      }
      if (horiz) seg(u, fixed, b, fixed + T);
      else seg(fixed, u, fixed + T, b);
    };
    side("n", x0, x1, z0, true);
    side("s", x0, x1, z1 - T, true);
    side("w", z0 + T, z1 - T, x0, false);
    side("e", z0 + T, z1 - T, x1 - T, false);
  }

  _buildings() {
    const W = (side, at, extra = {}) => ({ side, at, w: 1.0, h: 1.1, sill: 1.0, ...extra });
    const D = (side, at, extra = {}) => ({ side, at, w: 1.1, h: 2.15, sill: 0, door: true, ...extra });
    // Gatehouse
    this.building({ x: 9, z: 57, w: 6, d: 5, openings: [D("w", 0), W("s", 1), W("n", 0, { bars: true })], ac: true });
    // SW house
    this.building({ x: -20, z: 42, w: 11, d: 8, openings: [D("e", 1.5), W("e", -2), W("s", -3), W("s", 2.5), W("n", 0), W("w", 1.5, { bars: true })], tank: true, awning: "s" });
    // SE two-storey with roof access
    this.building({ x: 20, z: 40, w: 12, d: 9, floors: 2, stairs: { side: "w" },
      openings: [D("s", -3), D("n", 2), W("s", 2), W("e", 0), W("e", -2.5, { floor: 1 }), W("s", -1, { floor: 1 }), W("s", 3.5, { floor: 1 }), W("n", -3, { floor: 1 }), W("n", -2)], tank: true, ac: true });
    // Courtyard compound (west) with a house inside
    this.compoundWall(-33, 0, -15, 16, [{ side: "e", at: 8, w: 3 }, { side: "n", at: -26, w: 1.4 }]);
    this.building({ x: -26.5, z: 5, w: 9, d: 7, openings: [D("s", 1), W("s", -2.5), W("e", 0), W("w", 0, { bars: true })], tank: true });
    // East house
    this.building({ x: 22, z: 6, w: 10, d: 10, openings: [D("w", -2), D("n", 2.5), W("w", 2), W("s", -2), W("s", 2), W("e", 0)], ac: true, awning: "n" });
    // NW house (brick)
    this.building({ x: -22, z: -26, w: 12, d: 8, brick: true, openings: [D("e", 0), D("s", -3), W("s", 1), W("s", 4), W("n", -2), W("n", 2.5), W("w", 0)], tank: true });
    // HQ: two-storey, roof access on the east
    this.building({ x: 22, z: -30, w: 16, d: 10, floors: 2, stairs: { side: "e" },
      openings: [D("s", -4), D("w", 2), W("s", 0), W("s", 4), W("s", -5, { floor: 1 }), W("s", -1.5, { floor: 1 }), W("s", 2, { floor: 1 }), W("s", 5.5, { floor: 1 }), W("n", 0), W("w", -2, { bars: true }), W("n", -4, { floor: 1 }), W("n", 3, { floor: 1 })], tank: true, ac: true, awning: "s" });
    // Warehouse / hall to the north
    this.building({ x: -4, z: -54, w: 20, d: 12, floors: 1, openings: [D("s", 0, { w: 3.6, h: 2.9 }), D("e", 2), W("s", -6), W("s", 6), W("w", 0), W("n", -5), W("n", 5)] });
    // Huts around the edges
    this.building({ x: -48, z: 22, w: 6, d: 6, openings: [D("e", 0), W("s", 0)] });
    this.building({ x: 48, z: 24, w: 7, d: 6, openings: [D("w", 0), W("n", 1.5)], tank: true });
    this.building({ x: -50, z: -12, w: 6, d: 7, brick: true, openings: [D("e", 1), W("n", 0)] });
    this.building({ x: 50, z: -50, w: 8, d: 6, openings: [D("w", 0), W("s", 1.5), W("n", -1)] });
    this.building({ x: -46, z: 54, w: 6, d: 5, openings: [D("n", 0), W("e", 0)] });
    this.building({ x: -54, z: -48, w: 7, d: 6, openings: [D("e", 0), W("s", 0)] });
    // ruined wall pieces for cover
    this.box(-8, 0, 22, -4, 1.4, 22.35, "brick", "plaster");
    this.box(6, 0, -14, 6.35, 1.8, -10, "brick", "plaster");
    this.box(34, 0, 22, 38, 1.2, 22.35, "plaster", "plaster");
    this.box(-36, 0, -34, -35.65, 1.6, -30, "brick", "plaster");
  }

  _market() {
    // stalls around the crossroads: posts, counter, canvas roof, goods
    const stalls = [[-8, -6, 0], [-8, 6, 0], [8, -7, Math.PI], [9, 7, Math.PI]];
    for (const [x, z, r] of stalls) {
      const c = Math.cos(r);
      const hw = 1.3;
      const hd = 1.0;
      for (const [sx, sz] of [[-hw, -hd], [hw, -hd], [-hw, hd], [hw, hd]]) {
        this.box(x + sx - 0.05, 0, z + sz - 0.05, x + sx + 0.05, 2.3, z + sz + 0.05, "wood", "wood", true, { thin: true });
      }
      this.box(x - hw, 0, z - 0.4 * c - 0.3, x + hw, 0.95, z - 0.4 * c + 0.3, "wood", "wood");
      const g = new THREE.PlaneGeometry(2.9, 2.5, 4, 3);
      const m = new THREE.Mesh(g, this.assets.materials.canvas);
      m.position.set(x, 2.35, z);
      m.rotation.set(-Math.PI / 2 + 0.18 * c, 0, 0);
      m.castShadow = true;
      m.receiveShadow = true;
      this.scene.add(m);
      for (let i = 0; i < 3; i++) this.addProp("AmmoBox", x - 0.8 + i * 0.7, 0.95, z - 0.4 * c, this.rng() * 0.6, { collide: false, tint: [0x6b4a2a, 0x8a7a3a, 0x3a5a2a][i] });
    }
  }

  // ------------------------------------------------------------------------------------
  _propTemplates() {
    const t = {};
    for (const root of this.assets.props.scene.children) {
      const meshes = [];
      root.updateMatrixWorld(true);
      const inv = root.matrixWorld.clone().invert();
      root.traverse((o) => {
        if (o.isMesh) meshes.push({ geometry: o.geometry, material: o.material, local: inv.clone().multiply(o.matrixWorld) });
      });
      const box = new THREE.Box3().setFromObject(root);
      box.min.sub(root.position);
      box.max.sub(root.position);
      t[root.name] = { meshes, box };
    }
    return t;
  }

  addProp(name, x, y, z, rotY = 0, opts = {}) {
    const tpl = this.propTemplates[name];
    if (!tpl) return console.warn("no prop", name);
    const m = new THREE.Matrix4().compose(
      new THREE.Vector3(x, y, z),
      new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), rotY),
      new THREE.Vector3(1, 1, 1).multiplyScalar(opts.scale || 1),
    );
    let arr = this.propInstances.get(name);
    if (!arr) this.propInstances.set(name, (arr = []));
    arr.push({ matrix: m, color: opts.tint != null ? new THREE.Color(opts.tint) : null });
    if (opts.collide === false) return;
    const surface = opts.surface || PROP_SURFACE[name] || "metal";
    if (PROP_COLLIDERS[name]) {
      for (const c of PROP_COLLIDERS[name]) this._colliderBox(c, x, y, z, rotY, surface);
      return;
    }
    const b = tpl.box.clone();
    if (opts.scale) {
      b.min.multiplyScalar(opts.scale);
      b.max.multiplyScalar(opts.scale);
    }
    this._colliderBox([b.min.x, b.min.y, b.min.z, b.max.x, b.max.y, b.max.z], x, y, z, rotY, surface);
  }

  _colliderBox(c, x, y, z, rotY, surface) {
    const cs = Math.cos(rotY);
    const sn = Math.sin(rotY);
    let minX = Infinity;
    let minZ = Infinity;
    let maxX = -Infinity;
    let maxZ = -Infinity;
    for (const [px, pz] of [[c[0], c[2]], [c[3], c[2]], [c[0], c[5]], [c[3], c[5]]]) {
      const rx = px * cs + pz * sn;
      const rz = -px * sn + pz * cs;
      minX = Math.min(minX, rx); maxX = Math.max(maxX, rx);
      minZ = Math.min(minZ, rz); maxZ = Math.max(maxZ, rz);
    }
    // rotated boxes are shrunk a little so diagonal props don't feel oversized
    const diag = Math.abs(Math.sin(rotY * 2));
    const shrink = diag * 0.18 * Math.min(maxX - minX, maxZ - minZ);
    this.world.add(x + minX + shrink, y + c[1], z + minZ + shrink, x + maxX - shrink, y + c[4], z + maxZ - shrink, surface);
  }

  _props() {
    const r = this.rng;
    const P = (n, x, z, rot = 0, o = {}) => this.addProp(n, x, o.y || 0, z, rot, o);
    // checkpoint at the gate
    P("Sandbags", -3.2, 50, 0);
    P("Sandbags", 3.4, 50.2, 0.05);
    P("Sandbags", -5.2, 51.4, Math.PI / 2);
    P("Jersey", -1, 44, 0.1);
    P("Jersey", 4, 43.5, -0.08);
    P("Barrel", 5.6, 50.8, 0, { tint: 0x2d4a2d });
    P("Barrel", 6.2, 51.3, 0, { tint: 0x7a2a1a });
    P("Watchtower", 62, 62, 0);
    P("Watchtower", -62, -62, Math.PI);
    P("Watchtower", 62, -62, Math.PI / 2);
    P("Watchtower", -62, 62, -Math.PI / 2);
    // containers yard (east)
    const cc = [0x7a2418, 0x1f3f63, 0x2e4d2a, 0x8a6a2a, 0x5a5a5a, 0x7a2418];
    P("Container", 44, -6, 0, { tint: cc[0] });
    P("Container", 44, -3.4, 0, { tint: cc[1] });
    P("Container", 44, -4.7, 0, { tint: cc[2], y: 2.59, collide: false });
    this.world.add(41, 2.59, -5.9, 47, 5.18, -3.5, "metal");
    P("Container", 52, 4, Math.PI / 2, { tint: cc[3] });
    P("Container", 39, 8, 0.2, { tint: cc[4] });
    P("Container", 56, -20, Math.PI / 2, { tint: cc[5] });
    P("Container", -40, 34, 0.1, { tint: cc[1] });
    P("Container", -58, 8, Math.PI / 2, { tint: cc[2] });
    // cover lines / fighting positions
    P("Hesco", 30, -12, 0);
    P("Hesco", 14, -44, Math.PI / 2);
    P("Sandbags", 40, 2, Math.PI / 2);
    P("Sandbags", 16, -22, 0);
    P("Sandbags", -8, -44, 0);
    P("Sandbags", 0, -44.6, 0.05);
    P("Sandbags", -30, -18, Math.PI / 2);
    P("Sandbags", 28, 30, 0);
    P("Jersey", -12, 28, Math.PI / 2);
    P("Jersey", 12, 18, 0.3);
    P("Jersey", -14, -8, 0);
    P("Jersey", 30, -40, Math.PI / 2);
    // burnt cars
    P("BurntCar", 2.5, 24, 0.35);
    P("BurntCar", -2.5, -24, Math.PI + 0.2);
    P("BurntCar", 32, 1, Math.PI / 2 + 0.1);
    P("BurntCar", -40, -2, -0.2);
    // clutter
    const clutter = [
      ["Crate", -14, 44], ["Crate", -14.2, 45.2], ["Barrel", -13.8, 38.5], ["Pallet", -15, 36],
      ["Crate", 27, 38], ["Barrel", 26.6, 42], ["Barrel", 27.3, 42.6], ["JerryCans", 14, 36],
      ["Crate", -18, 12], ["Barrel", -17, 2], ["Tire", -19, 3], ["Tire", -19.2, 3.6, 0.2],
      ["Crate", 16, 12], ["Pallet", 15, 2], ["Barrel", 28, 12], ["Barrel", 28.5, 11.2],
      ["Crate", -14, -30], ["Crate", -15.2, -30.4], ["Barrel", -30, -30], ["Tire", -28, -21],
      ["Crate", 12, -34], ["Crate", 12, -35.2], ["Crate", 12.1, -34.6, 0, 0.77], ["JerryCans", 32, -26],
      ["Barrel", 30.5, -34], ["Barrel", 31, -34.8], ["Pallet", 27, -23],
      ["Crate", -12, -50], ["Crate", -11, -58], ["Barrel", 4, -58], ["Barrel", 4.7, -58.3], ["Crate", 2, -49],
      ["Crate", 46, 20], ["Barrel", 50, 27], ["Tire", -45, 19], ["Crate", -48, -8], ["Barrel", 53, -47],
      ["Crate", 36, -8], ["Crate", 36, -9.2], ["Barrel", 49, -9], ["Pallet", 48, 8], ["Tire", 36, 6],
      ["JerryCans", -26, 14], ["Crate", -30, 10], ["Barrel", -31.5, 1.2],
    ];
    const bcol = [0x2d4a2d, 0x1f3a5a, 0x7a2a1a, 0x5a5a52, 0x2a2a2a, 0x8a6a2a];
    for (const [n, x, z, rot, y] of clutter) {
      const tint = n === "Barrel" ? bcol[Math.floor(r() * bcol.length)] : null;
      P(n, x, z, rot ?? r() * Math.PI * 2 * (n === "Crate" ? 0.1 : 1), { tint, y: y || 0 });
    }
  }

  _vegetation() {
    const r = this.rng;
    const palms = [
      [-12, 50], [12, 48], [-26, 30], [30, 28], [-8, 12], [10, -16], [-34, -40], [34, -46], [-40, 44],
      [40, 46], [-52, 30], [55, 12], [-56, -26], [16, -60], [-20, -64], [58, 36], [-10, 64], [24, 64],
      // outside the wall for the skyline
      [-90, 40], [-110, -20], [95, -30], [120, 60], [-80, -110], [70, 120], [-130, 90], [140, -80],
    ];
    for (const [x, z] of palms) {
      const s = 0.8 + r() * 0.45;
      this.addProp("Palm", x, 0, z, r() * Math.PI * 2, { scale: s, collide: false });
      if (Math.abs(x) < PLAY_HALF && Math.abs(z) < PLAY_HALF) this.world.addCentered(x, 0, z, 0.45, 7 * s, 0.45, "wood");
    }
    // dry shrubs (instanced crossed quads)
    const q = this.engine.quality.shrubs;
    const count = Math.floor(900 * q);
    const g1 = new THREE.PlaneGeometry(1, 1);
    g1.translate(0, 0.5, 0);
    const g2 = g1.clone().rotateY(Math.PI / 2);
    const g = THREE.BufferGeometryUtils.mergeGeometries([g1, g2]);
    const inst = new THREE.InstancedMesh(g, this.assets.materials.shrub, count);
    const m = new THREE.Matrix4();
    const tmp = [];
    let n = 0;
    for (let i = 0; i < count * 3 && n < count; i++) {
      const x = (r() * 2 - 1) * 180;
      const z = (r() * 2 - 1) * 180;
      const inside = Math.abs(x) < PLAY_HALF && Math.abs(z) < PLAY_HALF;
      if (inside && (Math.abs(x) < 6 || Math.abs(z) < 5)) continue; // keep roads clear
      if (inside && this.world.query(x - 1, z - 1, x + 1, z + 1, tmp).length) continue;
      if (!inside && Math.max(Math.abs(x), Math.abs(z)) < PLAY_HALF + 3) continue;
      const s = 0.4 + r() * 0.9;
      const y = inside ? 0 : this.terrainHeight(x, z) - 0.05;
      m.compose(new THREE.Vector3(x, y, z), new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), r() * 3),
        new THREE.Vector3(s * (0.8 + r() * 0.5), s, s));
      inst.setMatrixAt(n++, m);
    }
    inst.count = n;
    inst.castShadow = true;
    inst.receiveShadow = true;
    this.scene.add(inst);
    // scattered rocks
    const rg = new THREE.DodecahedronGeometry(0.3, 0);
    const rocks = new THREE.InstancedMesh(rg, this.assets.materials.concrete, 220);
    for (let i = 0; i < 220; i++) {
      const x = (r() * 2 - 1) * 150;
      const z = (r() * 2 - 1) * 150;
      const inside = Math.abs(x) < PLAY_HALF && Math.abs(z) < PLAY_HALF;
      const s = 0.3 + r() * 1.3;
      const y = inside ? 0 : this.terrainHeight(x, z);
      m.compose(new THREE.Vector3(x, y, z), new THREE.Quaternion().setFromEuler(new THREE.Euler(r() * 3, r() * 3, r() * 3)),
        new THREE.Vector3(s, s * 0.6, s * (0.7 + r() * 0.6)));
      rocks.setMatrixAt(i, m);
    }
    rocks.castShadow = true;
    rocks.receiveShadow = true;
    this.scene.add(rocks);
  }

  terrainHeight(x, z) {
    // sample the terrain mesh with a downward ray (only used at build time)
    const rc = new THREE.Raycaster(new THREE.Vector3(x, 500, z), new THREE.Vector3(0, -1, 0), 0, 1000);
    const hit = rc.intersectObject(this.terrain, false)[0];
    return hit ? hit.point.y : 0;
  }

  _powerLines() {
    const poles = [];
    for (let z = 64; z >= -64; z -= 21) poles.push([6.5, z]);
    for (let x = -60; x <= -10; x += 25) poles.push([x, -4.5]);
    for (const [x, z] of poles) {
      this.addProp("PowerPole", x, 0, z, 0, { collide: false });
      this.world.addCentered(x, 0, z, 0.3, 9, 0.3, "wood");
    }
    const mat = new THREE.LineBasicMaterial({ color: 0x151515 });
    const wire = (a, b, off) => {
      const pts = [];
      for (let i = 0; i <= 16; i++) {
        const t = i / 16;
        const p = new THREE.Vector3().lerpVectors(a, b, t);
        p.y -= Math.sin(t * Math.PI) * 0.9;
        p.add(off);
        pts.push(p);
      }
      this.scene.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), mat));
    };
    const run = (list, axis) => {
      for (let i = 0; i < list.length - 1; i++) {
        const a = new THREE.Vector3(list[i][0], 8.55, list[i][1]);
        const b = new THREE.Vector3(list[i + 1][0], 8.55, list[i + 1][1]);
        for (const o of [-0.95, 0, 0.95]) {
          const off = axis === "z" ? new THREE.Vector3(o, o === 0 ? 0.58 : 0, 0) : new THREE.Vector3(0, o === 0 ? 0.58 : 0, o);
          wire(a, b, off);
        }
      }
    };
    run(poles.slice(0, 7), "z");
    run(poles.slice(7), "x");
  }

  _instanceProps() {
    for (const [name, list] of this.propInstances) {
      const tpl = this.propTemplates[name];
      for (const part of tpl.meshes) {
        const mesh = new THREE.InstancedMesh(part.geometry, part.material, list.length);
        list.forEach((it, i) => {
          mesh.setMatrixAt(i, it.matrix.clone().multiply(part.local));
          if (it.color) mesh.setColorAt(i, it.color);
          else if (mesh.instanceColor) mesh.setColorAt(i, new THREE.Color(1, 1, 1));
        });
        if (list.some((it) => it.color)) {
          list.forEach((it, i) => mesh.setColorAt(i, it.color || new THREE.Color(1, 1, 1)));
        }
        mesh.castShadow = true;
        mesh.receiveShadow = true;
        mesh.computeBoundingSphere();
        mesh.name = "prop_" + name;
        this.scene.add(mesh);
      }
    }
  }
}

const PROP_SURFACE = {
  Crate: "wood", Pallet: "wood", Barrel: "metal", Container: "metal", Sandbags: "sandbag", Hesco: "sandbag",
  Jersey: "concrete", BurntCar: "metal", Watchtower: "wood", Tire: "rubber", AmmoBox: "metal",
  JerryCans: "metal", WaterTank: "metal", ACUnit: "metal",
};

// Hand-made collider sets (local space, [minX, minY, minZ, maxX, maxY, maxZ]) for props whose
// bounding box would be a poor fit.
const PROP_COLLIDERS = {
  Watchtower: [
    [-1.3, 0, -1.3, -1.1, 3.6, -1.1], [1.1, 0, -1.3, 1.3, 3.6, -1.1], [-1.3, 0, 1.1, -1.1, 3.6, 1.3], [1.1, 0, 1.1, 1.3, 3.6, 1.3],
    [-1.35, 3.5, -1.35, 1.35, 3.6, 1.35],
    [-1.35, 3.6, 1.25, 1.35, 4.65, 1.35], [-1.35, 3.6, -1.35, 1.35, 4.65, -1.25], [-1.35, 3.6, -1.35, -1.25, 4.65, 1.35], [1.25, 3.6, -1.35, 1.35, 4.65, 1.35],
  ],
  BurntCar: [[-0.86, 0, -2.3, 0.86, 1.0, 2.3], [-0.8, 1.0, -0.95, 0.8, 1.44, 1.65]],
  Sandbags: [[-1.2, 0, -0.17, 1.2, 0.44, 0.5]],
  Palm: [],
  PowerPole: [],
};

function makeNoise(seed) {
  const r = rand(seed);
  const perm = new Uint8Array(512);
  const vals = new Float32Array(256);
  for (let i = 0; i < 256; i++) {
    perm[i] = i;
    vals[i] = r() * 2 - 1;
  }
  for (let i = 255; i > 0; i--) {
    const j = Math.floor(r() * (i + 1));
    [perm[i], perm[j]] = [perm[j], perm[i]];
  }
  for (let i = 0; i < 256; i++) perm[i + 256] = perm[i];
  const fade = (t) => t * t * (3 - 2 * t);
  const v = (x, z) => vals[perm[(perm[x & 255] + z) & 511] & 255];
  return (x, z) => {
    const xi = Math.floor(x);
    const zi = Math.floor(z);
    const xf = fade(x - xi);
    const zf = fade(z - zi);
    const a = v(xi, zi) * (1 - xf) + v(xi + 1, zi) * xf;
    const b = v(xi, zi + 1) * (1 - xf) + v(xi + 1, zi + 1) * xf;
    return a * (1 - zf) + b * zf;
  };
}
