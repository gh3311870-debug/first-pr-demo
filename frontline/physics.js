// Static collision world made of axis-aligned boxes in a spatial hash, plus ray casts.
import * as THREE from "../vendor/three-r186/three-bundle.min.js";

const CELL = 4;

export class World {
  constructor() {
    this.boxes = [];
    this.grid = new Map();
    this.groundY = 0;
  }

  // surface: "plaster" | "concrete" | "metal" | "wood" | "sand" | "sandbag" ...
  add(minX, minY, minZ, maxX, maxY, maxZ, surface = "concrete", opts = {}) {
    const b = { minX, minY, minZ, maxX, maxY, maxZ, surface, id: this.boxes.length, noNav: !!opts.noNav, thin: !!opts.thin };
    this.boxes.push(b);
    for (let x = Math.floor(minX / CELL); x <= Math.floor(maxX / CELL); x++) {
      for (let z = Math.floor(minZ / CELL); z <= Math.floor(maxZ / CELL); z++) {
        const k = x * 4096 + z;
        let arr = this.grid.get(k);
        if (!arr) this.grid.set(k, (arr = []));
        arr.push(b);
      }
    }
    return b;
  }

  addCentered(cx, cy, cz, sx, sy, sz, surface, opts) {
    return this.add(cx - sx / 2, cy, cz - sz / 2, cx + sx / 2, cy + sy, cz + sz / 2, surface, opts);
  }

  query(minX, minZ, maxX, maxZ, out = []) {
    out.length = 0;
    const stamp = (this._stamp = (this._stamp || 0) + 1);
    for (let x = Math.floor(minX / CELL); x <= Math.floor(maxX / CELL); x++) {
      for (let z = Math.floor(minZ / CELL); z <= Math.floor(maxZ / CELL); z++) {
        const arr = this.grid.get(x * 4096 + z);
        if (!arr) continue;
        for (const b of arr) {
          if (b._s === stamp) continue;
          b._s = stamp;
          out.push(b);
        }
      }
    }
    return out;
  }

  // Highest walkable surface under a circle at (x, z) that is not above maxY.
  groundAt(x, z, r, maxY) {
    let g = this.groundY;
    for (const b of this.query(x - r, z - r, x + r, z + r, this._tmp || (this._tmp = []))) {
      if (b.maxY > maxY || b.maxY <= g) continue;
      if (circleRect(x, z, r * 0.7, b)) g = b.maxY;
    }
    return g;
  }

  // Move a vertical cylinder (feet at pos) and resolve collisions. Returns {onGround, hitCeiling}.
  moveCylinder(pos, vel, dt, radius, height, stepHeight = 0.45) {
    const res = { onGround: false, hitCeiling: false };
    // horizontal, in sub-steps so fast movement can't tunnel through thin walls
    const dx = vel.x * dt;
    const dz = vel.z * dt;
    const steps = Math.max(1, Math.ceil(Math.hypot(dx, dz) / (radius * 0.5)));
    const list = this._list || (this._list = []);
    for (let s = 0; s < steps; s++) {
      pos.x += dx / steps;
      pos.z += dz / steps;
      this.query(pos.x - radius - 0.5, pos.z - radius - 0.5, pos.x + radius + 0.5, pos.z + radius + 0.5, list);
      for (let iter = 0; iter < 2; iter++) {
        for (const b of list) {
          if (b.maxY <= pos.y + stepHeight || b.minY >= pos.y + height) continue;
          pushOut(pos, radius, b);
        }
      }
    }
    // step up onto low obstacles
    const ground = this.groundAt(pos.x, pos.z, radius, pos.y + stepHeight);
    // vertical
    pos.y += vel.y * dt;
    if (pos.y <= ground) {
      if (vel.y <= 0) {
        // snap up steps smoothly, snap down only if close (walking down stairs)
        pos.y = ground;
        vel.y = 0;
        res.onGround = true;
      }
    } else if (vel.y <= 0 && pos.y - ground < 0.08) {
      pos.y = ground;
      vel.y = 0;
      res.onGround = true;
    }
    if (vel.y > 0) {
      for (const b of this.query(pos.x - radius, pos.z - radius, pos.x + radius, pos.z + radius, list)) {
        if (b.minY > pos.y + stepHeight && b.minY < pos.y + height && circleRect(pos.x, pos.z, radius * 0.8, b)) {
          pos.y = b.minY - height;
          vel.y = 0;
          res.hitCeiling = true;
        }
      }
    }
    return res;
  }

  // Ray vs boxes and the ground plane. Returns {dist, point, normal, box} or null.
  raycast(origin, dir, maxDist, ignoreThin = false) {
    let best = null;
    let bestT = maxDist;
    // ground plane
    if (dir.y < -1e-6) {
      const t = (this.groundY - origin.y) / dir.y;
      if (t > 0 && t < bestT) {
        bestT = t;
        best = { dist: t, normal: new THREE.Vector3(0, 1, 0), box: null, surface: "sand" };
      }
    }
    // walk grid cells along the ray (2D DDA over XZ)
    const stamp = (this._stamp = (this._stamp || 0) + 1);
    let cx = Math.floor(origin.x / CELL);
    let cz = Math.floor(origin.z / CELL);
    const stepX = dir.x > 0 ? 1 : -1;
    const stepZ = dir.z > 0 ? 1 : -1;
    const tDeltaX = Math.abs(dir.x) > 1e-9 ? CELL / Math.abs(dir.x) : Infinity;
    const tDeltaZ = Math.abs(dir.z) > 1e-9 ? CELL / Math.abs(dir.z) : Infinity;
    let tMaxX = Math.abs(dir.x) > 1e-9 ? ((dir.x > 0 ? (cx + 1) * CELL : cx * CELL) - origin.x) / dir.x : Infinity;
    let tMaxZ = Math.abs(dir.z) > 1e-9 ? ((dir.z > 0 ? (cz + 1) * CELL : cz * CELL) - origin.z) / dir.z : Infinity;
    let t = 0;
    while (t <= bestT) {
      const arr = this.grid.get(cx * 4096 + cz);
      if (arr) {
        for (const b of arr) {
          if (b._s === stamp) continue;
          b._s = stamp;
          if (ignoreThin && b.thin) continue;
          const hit = rayBox(origin, dir, b, bestT);
          if (hit !== null && hit < bestT) {
            bestT = hit;
            best = { dist: hit, box: b, surface: b.surface };
          }
        }
      }
      if (tMaxX < tMaxZ) {
        t = tMaxX;
        tMaxX += tDeltaX;
        cx += stepX;
      } else {
        t = tMaxZ;
        tMaxZ += tDeltaZ;
        cz += stepZ;
      }
      if (t > 600) break;
    }
    if (!best) return null;
    best.point = origin.clone().addScaledVector(dir, best.dist);
    if (best.box) best.normal = boxNormal(best.point, best.box);
    return best;
  }

  lineOfSight(a, b) {
    const dir = b.clone().sub(a);
    const d = dir.length();
    dir.divideScalar(d);
    const hit = this.raycast(a, dir, d - 0.05, true);
    return !hit;
  }
}

function circleRect(x, z, r, b) {
  const cx = Math.max(b.minX, Math.min(x, b.maxX));
  const cz = Math.max(b.minZ, Math.min(z, b.maxZ));
  const dx = x - cx;
  const dz = z - cz;
  return dx * dx + dz * dz < r * r;
}

function pushOut(pos, r, b) {
  const cx = Math.max(b.minX, Math.min(pos.x, b.maxX));
  const cz = Math.max(b.minZ, Math.min(pos.z, b.maxZ));
  let dx = pos.x - cx;
  let dz = pos.z - cz;
  const d2 = dx * dx + dz * dz;
  if (d2 >= r * r) return;
  if (d2 > 1e-8) {
    const d = Math.sqrt(d2);
    pos.x = cx + (dx / d) * r;
    pos.z = cz + (dz / d) * r;
  } else {
    // center inside the box: push out along the smallest axis
    const pens = [pos.x - b.minX, b.maxX - pos.x, pos.z - b.minZ, b.maxZ - pos.z];
    const i = pens.indexOf(Math.min(...pens));
    if (i === 0) pos.x = b.minX - r;
    else if (i === 1) pos.x = b.maxX + r;
    else if (i === 2) pos.z = b.minZ - r;
    else pos.z = b.maxZ + r;
  }
}

function rayBox(o, d, b, maxT) {
  let tmin = 0;
  let tmax = maxT;
  for (const [oa, da, mn, mx] of [[o.x, d.x, b.minX, b.maxX], [o.y, d.y, b.minY, b.maxY], [o.z, d.z, b.minZ, b.maxZ]]) {
    if (Math.abs(da) < 1e-9) {
      if (oa < mn || oa > mx) return null;
    } else {
      let t1 = (mn - oa) / da;
      let t2 = (mx - oa) / da;
      if (t1 > t2) [t1, t2] = [t2, t1];
      if (t1 > tmin) tmin = t1;
      if (t2 < tmax) tmax = t2;
      if (tmin > tmax) return null;
    }
  }
  return tmin;
}

function boxNormal(p, b) {
  const e = [
    [Math.abs(p.x - b.minX), -1, 0, 0], [Math.abs(p.x - b.maxX), 1, 0, 0],
    [Math.abs(p.y - b.minY), 0, -1, 0], [Math.abs(p.y - b.maxY), 0, 1, 0],
    [Math.abs(p.z - b.minZ), 0, 0, -1], [Math.abs(p.z - b.maxZ), 0, 0, 1],
  ];
  e.sort((a, c) => a[0] - c[0]);
  return new THREE.Vector3(e[0][1], e[0][2], e[0][3]);
}

// Coarse navigation grid (1 m cells) with A* for enemy movement.
export class NavGrid {
  constructor(world, half = 72, cell = 1) {
    this.half = half;
    this.cell = cell;
    this.n = Math.ceil((half * 2) / cell);
    this.blocked = new Uint8Array(this.n * this.n);
    const inflate = 0.45;
    for (const b of world.boxes) {
      if (b.noNav) continue;
      if (b.minY > 1.6 || b.maxY < 0.35) continue;
      const x0 = this.toCell(b.minX - inflate);
      const x1 = this.toCell(b.maxX + inflate);
      const z0 = this.toCell(b.minZ - inflate);
      const z1 = this.toCell(b.maxZ + inflate);
      for (let x = x0; x <= x1; x++) for (let z = z0; z <= z1; z++) this.set(x, z);
    }
    for (let i = 0; i < this.n; i++) {
      this.set(i, 0); this.set(i, this.n - 1); this.set(0, i); this.set(this.n - 1, i);
    }
  }

  toCell(v) {
    return Math.max(0, Math.min(this.n - 1, Math.floor((v + this.half) / this.cell)));
  }

  set(x, z) {
    if (x >= 0 && z >= 0 && x < this.n && z < this.n) this.blocked[z * this.n + x] = 1;
  }

  isBlocked(x, z) {
    if (x < 0 || z < 0 || x >= this.n || z >= this.n) return true;
    return this.blocked[z * this.n + x] === 1;
  }

  walkable(wx, wz) {
    return !this.isBlocked(this.toCell(wx), this.toCell(wz));
  }

  center(x, z) {
    return new THREE.Vector3((x + 0.5) * this.cell - this.half, 0, (z + 0.5) * this.cell - this.half);
  }

  nearestFree(wx, wz) {
    const cx = this.toCell(wx);
    const cz = this.toCell(wz);
    for (let r = 0; r < 6; r++) {
      for (let dx = -r; dx <= r; dx++) {
        for (let dz = -r; dz <= r; dz++) {
          if (!this.isBlocked(cx + dx, cz + dz)) return [cx + dx, cz + dz];
        }
      }
    }
    return null;
  }

  // A* with 8-neighbour moves; returns array of world-space waypoints (smoothed).
  findPath(from, to, maxNodes = 6000) {
    const s = this.nearestFree(from.x, from.z);
    const g = this.nearestFree(to.x, to.z);
    if (!s || !g) return null;
    const n = this.n;
    const start = s[1] * n + s[0];
    const goal = g[1] * n + g[0];
    const gScore = new Map([[start, 0]]);
    const came = new Map();
    const open = [[this._h(s[0], s[1], g[0], g[1]), start]];
    const closed = new Set();
    let expanded = 0;
    while (open.length) {
      // binary heap would be faster; open sets here stay small
      let bi = 0;
      for (let i = 1; i < open.length; i++) if (open[i][0] < open[bi][0]) bi = i;
      const [, cur] = open[bi];
      open[bi] = open[open.length - 1];
      open.pop();
      if (cur === goal) break;
      if (closed.has(cur)) continue;
      closed.add(cur);
      if (++expanded > maxNodes) return null;
      const cx = cur % n;
      const cz = (cur / n) | 0;
      for (let dx = -1; dx <= 1; dx++) {
        for (let dz = -1; dz <= 1; dz++) {
          if (!dx && !dz) continue;
          const nx = cx + dx;
          const nz = cz + dz;
          if (this.isBlocked(nx, nz)) continue;
          if (dx && dz && (this.isBlocked(cx + dx, cz) || this.isBlocked(cx, cz + dz))) continue;
          const ni = nz * n + nx;
          const cost = gScore.get(cur) + (dx && dz ? 1.414 : 1);
          if (cost < (gScore.get(ni) ?? Infinity)) {
            gScore.set(ni, cost);
            came.set(ni, cur);
            open.push([cost + this._h(nx, nz, g[0], g[1]), ni]);
          }
        }
      }
    }
    if (!came.has(goal) && start !== goal) return null;
    const cells = [];
    let c = goal;
    while (c !== undefined && c !== start) {
      cells.push(c);
      c = came.get(c);
    }
    cells.reverse();
    const pts = cells.map((i) => this.center(i % n, (i / n) | 0));
    return this._smooth(from, pts);
  }

  _h(x, z, gx, gz) {
    const dx = Math.abs(x - gx);
    const dz = Math.abs(z - gz);
    return dx + dz - 0.586 * Math.min(dx, dz);
  }

  _clearLine(a, b) {
    const d = Math.hypot(b.x - a.x, b.z - a.z);
    const steps = Math.ceil(d / (this.cell * 0.5));
    for (let i = 1; i <= steps; i++) {
      const t = i / steps;
      if (!this.walkable(a.x + (b.x - a.x) * t, a.z + (b.z - a.z) * t)) return false;
    }
    return true;
  }

  _smooth(from, pts) {
    if (pts.length < 2) return pts;
    const out = [];
    let anchor = from;
    let i = 0;
    while (i < pts.length) {
      let j = pts.length - 1;
      while (j > i && !this._clearLine(anchor, pts[j])) j--;
      out.push(pts[j]);
      anchor = pts[j];
      i = j + 1;
    }
    return out;
  }
}
