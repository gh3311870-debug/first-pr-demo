// Soldiers on both sides: animation, perception (sight + hearing), navigation, combat and hit
// boxes. Every soldier belongs to a team and fights whoever is hostile to it: insurgents fight
// the player and the player's squad; in free-for-all everyone fights everyone.
import * as THREE from "../vendor/three-r186/three-bundle.min.js";
import { styleRifleMaterials, WEAPONS } from "./weapon.js";

const V3 = (x = 0, y = 0, z = 0) => new THREE.Vector3(x, y, z);
const tmp1 = V3();
const tmp2 = V3();

export const DIFFICULTY = {
  recruit: { damage: 0.65, spread: 1.5, reaction: 1.4, view: 70 },
  regular: { damage: 1.0, spread: 1.0, reaction: 1.0, view: 90 },
  veteran: { damage: 1.5, spread: 0.75, reaction: 0.75, view: 110 },
};

// How AI soldiers use each weapon. dmg = damage dealt to the player per hit (before difficulty).
const AI_WEAPONS = {
  M4: { burst: [2, 6], gap: [0.5, 1.4], rof: 0.1, spread: 1.0, dmg: [10, 16], sound: "rifle", range: 1.0, tracer: 0.5 },
  DMR: { burst: [1, 1], gap: [1.3, 2.3], rof: 0.1, spread: 0.35, dmg: [26, 38], sound: "dmr", range: 1.35, tracer: 1 },
  SG: { burst: [1, 1], gap: [0.9, 1.3], rof: 0.1, spread: 1.0, dmg: [4, 6], pellets: 8, pelletSpread: 0.055, sound: "shotgun", range: 0.5, tracer: 0 },
};

const RED_TINTS = [0x8c8878, 0x7d8764, 0x967f64, 0x6f746c];
const BLUE_TINT = 0x5d6b52; // squad: darker green uniforms

// closest distance between segment p0-p1 and segment q0-q1; returns [dist, s, t, pointOnP]
export function segSeg(p0, p1, q0, q1) {
  const d1 = tmp1.copy(p1).sub(p0);
  const d2 = tmp2.copy(q1).sub(q0);
  const r = p0.clone().sub(q0);
  const a = d1.dot(d1);
  const e = d2.dot(d2);
  const f = d2.dot(r);
  const c = d1.dot(r);
  const b = d1.dot(d2);
  const denom = a * e - b * b;
  let s = denom > 1e-9 ? THREE.MathUtils.clamp((b * f - c * e) / denom, 0, 1) : 0;
  let t = (b * s + f) / e;
  if (t < 0) {
    t = 0;
    s = THREE.MathUtils.clamp(-c / a, 0, 1);
  } else if (t > 1) {
    t = 1;
    s = THREE.MathUtils.clamp((b - c) / a, 0, 1);
  }
  const cp = p0.clone().addScaledVector(d1, s);
  const cq = q0.clone().addScaledVector(d2, t);
  return [cp.distanceTo(cq), s, t, cp];
}

// The player, wrapped so AI can treat it like any other combatant.
class PlayerTarget {
  constructor(player) {
    this.p = player;
    this.isPlayer = true;
  }
  get team() {
    return this.p.team;
  }
  get alive() {
    return !this.p.dead;
  }
  get pos() {
    return this.p.pos;
  }
  get speed() {
    return this.p.horizSpeed;
  }
  get crouched() {
    return this.p.crouched;
  }
  eye() {
    return this.p.eyePos;
  }
  chest() {
    return this.p.chest;
  }
  // distance along the ray if it passes through the player's body capsule
  hitTest(origin, end) {
    const pa = V3(this.p.pos.x, this.p.pos.y + 0.25, this.p.pos.z);
    const pb = V3(this.p.pos.x, this.p.pos.y + this.p.height - 0.2, this.p.pos.z);
    const [d, s] = segSeg(origin, end, pa, pb);
    return d < 0.32 ? s * origin.distanceTo(end) : null;
  }
}

class Soldier {
  constructor(sys, spawn, idx) {
    this.sys = sys;
    this.idx = idx;
    this.team = spawn.team;
    this.ally = spawn.team === sys.playerTeam;
    this.weapon = spawn.weapon || "M4";
    const A = sys.assets;
    const model = THREE.SkeletonUtils.clone(A.operator.scene);
    this.model = model;
    const tint = this.ally ? BLUE_TINT : RED_TINTS[idx % RED_TINTS.length];
    model.traverse((o) => {
      if (!o.isMesh) return;
      o.castShadow = true;
      o.receiveShadow = true;
      o.frustumCulled = false;
      if (o.material && o.material.name === "VanguardBodyMat") o.material = sys.bodyMaterial(tint);
    });
    styleRifleMaterials(model);
    // show only this soldier's weapon
    for (const k of Object.keys(WEAPONS)) {
      const p = WEAPONS[k].prefix;
      for (const n of [p + "Rifle", p + "Mag"]) {
        const o = model.getObjectByName(n);
        if (o) o.visible = k === this.weapon;
      }
    }
    this.muzzle = model.getObjectByName(WEAPONS[this.weapon].prefix + "Muzzle");
    sys.engine.scene.add(model);
    this.mixer = new THREE.AnimationMixer(model);
    const clip = (n) => A.operator.animations.find((a) => a.name === n);
    const sfx = this.weapon === "SG" ? "_SG" : "";
    this.actions = {
      idle: this.mixer.clipAction(clip("AIM_Idle" + sfx)),
      walk: this.mixer.clipAction(clip("AIM_Walk" + sfx)),
      run: this.mixer.clipAction(clip("AIM_Run" + sfx)),
      death: this.mixer.clipAction(clip("Death")),
    };
    this.actions.death.setLoop(THREE.LoopOnce, 1);
    this.actions.death.clampWhenFinished = true;
    this.anim = null;
    this.setAnim("idle", 0);
    this.mixer.update(Math.random() * 2);
    const bone = (n) => model.getObjectByName("mixamorig" + n);
    this.bones = {
      hips: bone("Hips"), spine: bone("Spine1"), spine2: bone("Spine2"), neck: bone("Neck"), head: bone("Head"),
      lArm: bone("LeftArm"), lHand: bone("LeftHand"), rArm: bone("RightArm"), rHand: bone("RightHand"),
      lUp: bone("LeftUpLeg"), lLeg: bone("LeftLeg"), lFoot: bone("LeftFoot"),
      rUp: bone("RightUpLeg"), rLeg: bone("RightLeg"), rFoot: bone("RightFoot"),
    };
    if (this.ally) {
      this.marker = new THREE.Sprite(sys.allyMarkerMat);
      this.marker.scale.set(0.028, 0.028, 1);
      this.marker.renderOrder = 20;
      sys.engine.scene.add(this.marker);
    }
    this.pos = V3(spawn.x, spawn.y || 0, spawn.z);
    this.yaw = spawn.yaw || 0;
    this.targetYaw = this.yaw;
    this.static = !!spawn.static;
    this.patrol = spawn.path ? spawn.path.map(([x, z]) => V3(x, 0, z)) : null;
    this.patrolIdx = 0;
    this.slot = spawn.slot;
    this.health = this.ally ? 160 : 100;
    this.state = this.ally ? "follow" : this.patrol ? "patrol" : "guard";
    this.awareness = 0;
    this.target = null;
    this.lastSeen = null;
    this.lastSeenTime = -99;
    this.canSee = false;
    this.thinkT = Math.random() * 0.2;
    this.path = null;
    this.pathIdx = 0;
    this.speed = 0;
    this.burst = 0;
    this.fireT = 0;
    this.reactT = 0;
    this.engageT = 0;
    this.aimPitch = 0;
    this.flinch = 0;
    this.stepDist = 0;
    this.lookAround = 0;
    this.trackT = 0;
    this.suppression = 0;
    this.repathT = 0;
    this.velocity = V3();
  }

  get alive() {
    return this.state !== "dead";
  }
  eye() {
    return V3(this.pos.x, this.pos.y + 1.62, this.pos.z);
  }
  chest() {
    return V3(this.pos.x, this.pos.y + 1.25, this.pos.z);
  }
  get crouched() {
    return false;
  }

  setAnim(name, fade = 0.3) {
    if (this.anim === name) return;
    const next = this.actions[name];
    next.reset().play();
    if (this.anim) next.crossFadeFrom(this.actions[this.anim], fade, true);
    this.anim = name;
  }

  followPath(speed) {
    if (!this.path || this.pathIdx >= this.path.length) return true;
    const target = this.path[this.pathIdx];
    const dx = target.x - this.pos.x;
    const dz = target.z - this.pos.z;
    const d = Math.hypot(dx, dz);
    if (d < 0.5) {
      this.pathIdx++;
      return this.pathIdx >= this.path.length;
    }
    this.velocity.set((dx / d) * speed, 0, (dz / d) * speed);
    if (!this.aimAtTarget) this.targetYaw = Math.atan2(-dx, -dz);
    return false;
  }

  goTo(target) {
    if (this.static) return false;
    const p = this.sys.nav.findPath(this.pos, target);
    if (!p || !p.length) return false;
    this.path = p;
    this.pathIdx = 0;
    return true;
  }
}

export class Enemies {
  constructor(engine, assets, world, nav, fx, audio, difficulty, mode = "squad") {
    this.engine = engine;
    this.assets = assets;
    this.world = world;
    this.nav = nav;
    this.fx = fx;
    this.audio = audio;
    this.mode = mode;
    this.playerTeam = "blue";
    this.diff = DIFFICULTY[difficulty] || DIFFICULTY.regular;
    this.list = [];
    this.pickups = [];
    this._bodyMats = new Map();
    this.time = 0;
    this.playerTarget = null;
    // loose magazines/shells for ammo pickups
    const mag = assets.operator.scene.getObjectByName("Mag");
    this.magGeo = mag ? mag.geometry : new THREE.BoxGeometry(0.02, 0.18, 0.06);
    this.magMat = mag ? mag.material : new THREE.MeshStandardMaterial({ color: 0x3a3020 });
    // friendly marker: small blue chevron over squadmates' heads
    const cv = document.createElement("canvas");
    cv.width = cv.height = 64;
    const c = cv.getContext("2d");
    c.fillStyle = "#4da3ff";
    c.strokeStyle = "rgba(0,0,0,0.6)";
    c.lineWidth = 4;
    c.beginPath();
    c.moveTo(12, 18);
    c.lineTo(32, 38);
    c.lineTo(52, 18);
    c.lineTo(52, 30);
    c.lineTo(32, 50);
    c.lineTo(12, 30);
    c.closePath();
    c.stroke();
    c.fill();
    this.allyMarkerMat = new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(cv), depthTest: false, transparent: true, sizeAttenuation: false });
  }

  bodyMaterial(tint) {
    if (!this._bodyMats.has(tint)) {
      const src = this.assets.operator.scene.getObjectByProperty("type", "SkinnedMesh").material;
      const m = src.clone();
      m.color.set(tint);
      m.roughness = 0.8;
      this._bodyMats.set(tint, m);
    }
    return this._bodyMats.get(tint);
  }

  spawn(spawns) {
    spawns.forEach((s, i) => this.list.push(new Soldier(this, s, i)));
  }

  // hostile soldiers still alive (from the player's point of view)
  get aliveCount() {
    return this.list.filter((e) => e.alive && e.team !== this.playerTeam).length;
  }
  get alliesAlive() {
    return this.list.filter((e) => e.alive && e.team === this.playerTeam).length;
  }

  hostile(a, b) {
    return a.team !== b.team;
  }

  // The player object stands in for itself in AI code as a PlayerTarget.
  _asTarget(shooter) {
    return shooter && shooter.isPlayerEntity ? this.playerTarget : shooter;
  }

  // Noise of gunfire: nearby hostiles become alert and move toward it.
  hearShot(pos, radius, shooter) {
    for (const e of this.list) {
      if (!e.alive || (shooter && !this.hostile(e, shooter))) continue;
      const d = e.pos.distanceTo(pos);
      if (d > radius) continue;
      e.awareness = Math.min(1.2, e.awareness + (1 - d / radius) * 1.5 + 0.3);
      if (e.state !== "combat" && !e.ally) {
        e.state = "alert";
        e.investigate = pos.clone().add(V3((Math.random() - 0.5) * 8, 0, (Math.random() - 0.5) * 8));
        e.investigate.y = 0;
        e.path = null;
      }
    }
  }

  // Rounds passing close to a soldier rattle him: worse aim for a moment.
  suppress(origin, dir, dist, shooter) {
    const end = origin.clone().addScaledVector(dir, dist);
    for (const e of this.list) {
      if (!e.alive || (shooter && !this.hostile(e, shooter))) continue;
      const c = V3(e.pos.x, e.pos.y + 1.2, e.pos.z);
      const [d] = segSeg(origin, end, c, V3(c.x, c.y + 0.5, c.z));
      if (d < 2.5) {
        e.suppression = Math.min(1, e.suppression + (1 - d / 2.5) * 0.45);
        e.trackT = Math.max(0, e.trackT - 0.4);
        if (e.state !== "combat" && shooter) this._enterCombat(e, this._asTarget(shooter));
      }
    }
  }

  // ---- hit testing ------------------------------------------------------------------
  _hitShapes(e) {
    const b = e.bones;
    const w = (o) => o.getWorldPosition(V3());
    const head = w(b.head);
    const neck = w(b.neck);
    const up = head.clone().sub(neck).normalize();
    return [
      { part: "head", type: "sphere", c: head.clone().addScaledVector(up, 0.11), r: 0.15 },
      { part: "torso", a: w(b.hips).add(V3(0, 0.02, 0)), b: neck, r: 0.2 },
      { part: "limb", a: w(b.lUp), b: w(b.lLeg), r: 0.1 },
      { part: "limb", a: w(b.lLeg), b: w(b.lFoot), r: 0.08 },
      { part: "limb", a: w(b.rUp), b: w(b.rLeg), r: 0.1 },
      { part: "limb", a: w(b.rLeg), b: w(b.rFoot), r: 0.08 },
      { part: "limb", a: w(b.lArm), b: w(b.lHand), r: 0.08 },
      { part: "limb", a: w(b.rArm), b: w(b.rHand), r: 0.08 },
    ];
  }

  // Nearest soldier hit along a ray, skipping soldiers of excludeTeam (friendlies).
  raycast(origin, dir, maxDist, excludeTeam = null, skip = null) {
    let best = null;
    const end = origin.clone().addScaledVector(dir, maxDist);
    for (const e of this.list) {
      if (!e.alive || e === skip || (excludeTeam && e.team === excludeTeam)) continue;
      const c = V3(e.pos.x, e.pos.y + 1, e.pos.z);
      const t = c.clone().sub(origin).dot(dir);
      if (t < 0 || t > maxDist + 1) continue;
      if (origin.clone().addScaledVector(dir, t).distanceTo(c) > 1.6) continue;
      for (const s of this._hitShapes(e)) {
        let hitT = null;
        if (s.type === "sphere") {
          const oc = origin.clone().sub(s.c);
          const bq = oc.dot(dir);
          const cq = oc.dot(oc) - s.r * s.r;
          const disc = bq * bq - cq;
          if (disc >= 0) hitT = -bq - Math.sqrt(disc);
        } else {
          const [d, sParam] = segSeg(origin, end, s.a, s.b);
          if (d < s.r) hitT = sParam * maxDist - Math.sqrt(s.r * s.r - d * d);
        }
        if (hitT !== null && hitT > 0 && hitT < maxDist && (!best || hitT < best.dist)) {
          best = { dist: hitT, enemy: e, part: s.part, point: origin.clone().addScaledVector(dir, hitT) };
        }
      }
    }
    return best;
  }

  // Apply damage to a soldier. attacker: the player object or a Soldier.
  damage(hit, dir, game, dmg, attacker) {
    const e = hit.enemy;
    if (!e.alive) return;
    e.health -= dmg;
    e.flinch = 1;
    e.awareness = 1.5;
    const byPlayer = !!(attacker && attacker.isPlayerEntity);
    const atk = this._asTarget(attacker);
    if (e.state !== "combat" && atk) this._enterCombat(e, atk);
    else if (atk && (!e.target || !e.canSee)) e.target = atk;
    if (e.health <= 0) {
      this._kill(e, hit, dir, game);
      if (byPlayer) game.onKill(hit.part === "head", e);
      else game.onAiKill(e, attacker);
    } else if (byPlayer) {
      game.hud.hitmarker(false);
      this.audio.hitmarker("hit");
      e.engageT = Math.min(e.engageT, 0.3);
    }
  }

  _kill(e, hit, dir, game) {
    e.state = "dead";
    e.velocity.set(0, 0, 0);
    // face the shooter so the backwards fall reads as a reaction to the hit
    e.yaw = Math.atan2(dir.x, dir.z);
    e.model.rotation.y = e.yaw;
    e.setAnim("death", 0.12);
    e.actions.death.timeScale = 1.1;
    if (e.marker) e.marker.visible = false;
    // hostile soldiers drop ammo for their weapon
    if (!e.ally) {
      const type = WEAPONS[e.weapon].ammoType;
      const amount = { "556": 30, "762": 20, "12g": 8 }[type] || 30;
      const m = new THREE.Mesh(this.magGeo, this.magMat);
      m.castShadow = true;
      m.position.set(e.pos.x + (Math.random() - 0.5) * 0.6, e.pos.y + 0.03, e.pos.z + (Math.random() - 0.5) * 0.6);
      m.rotation.set(Math.PI / 2, 0, Math.random() * 6);
      this.engine.scene.add(m);
      this.pickups.push({ mesh: m, type, amount });
    }
    for (const o of this.list) {
      if (o !== e && o.alive && o.team === e.team && o.pos.distanceTo(e.pos) < 25) {
        o.awareness = Math.max(o.awareness, 0.8);
        if (o.state !== "combat" && !o.ally) {
          o.state = "alert";
          o.investigate = e.pos.clone();
        }
      }
    }
  }

  _enterCombat(e, target) {
    if (!target) return;
    e.state = "combat";
    e.target = target;
    e.reactT = (0.45 + Math.random() * 0.5) * this.diff.reaction * (e.ally ? 0.8 : 1);
    e.engageT = 1.5 + Math.random() * 2.5;
    e.lastSeen = target.pos.clone();
    e.path = null;
  }

  // ---- main update ------------------------------------------------------------------
  update(dt, player, game) {
    this.time += dt;
    if (!this.playerTarget) this.playerTarget = new PlayerTarget(player);
    const pt = this.playerTarget;
    for (const e of this.list) {
      e.mixer.update(dt);
      if (!e.alive) {
        e.model.position.copy(e.pos);
        continue;
      }
      e.velocity.set(0, 0, 0);
      e.aimAtTarget = false;
      e.suppression = Math.max(0, e.suppression - dt * 0.5);
      e.thinkT -= dt;
      if (e.thinkT <= 0) {
        e.thinkT = 0.15 + Math.random() * 0.12;
        this._perceive(e, pt);
      }
      this._behave(e, dt, pt, game);
      if (e.velocity.lengthSq() > 0 && !e.static) {
        for (const o of this.list) {
          if (o === e || !o.alive) continue;
          const dx = e.pos.x - o.pos.x;
          const dz = e.pos.z - o.pos.z;
          const d = Math.hypot(dx, dz);
          if (d < 1.0 && d > 0.001) {
            e.velocity.x += (dx / d) * 1.5;
            e.velocity.z += (dz / d) * 1.5;
          }
        }
        if (e.ally) {
          // don't walk through the player
          const dx = e.pos.x - player.pos.x;
          const dz = e.pos.z - player.pos.z;
          const d = Math.hypot(dx, dz);
          if (d < 1.2 && d > 0.001) {
            e.velocity.x += (dx / d) * 2;
            e.velocity.z += (dz / d) * 2;
          }
        }
        const v = e.velocity.clone();
        v.y = -1;
        this.world.moveCylinder(e.pos, v, dt, 0.3, 1.75);
        e.stepDist += Math.hypot(e.velocity.x, e.velocity.z) * dt;
        if (e.stepDist > 1.6) {
          e.stepDist = 0;
          if (e.pos.distanceTo(player.pos) < 22) this.audio.footstep(e.pos.clone(), 0.5);
        }
      }
      const spd = Math.hypot(e.velocity.x, e.velocity.z);
      e.speed += (spd - e.speed) * Math.min(1, dt * 8);
      if (e.speed > 2.6) {
        e.setAnim("run", 0.25);
        e.actions.run.timeScale = e.speed / 4.6;
      } else if (e.speed > 0.3) {
        e.setAnim("walk", 0.3);
        e.actions.walk.timeScale = Math.max(0.6, e.speed / 1.5);
      } else e.setAnim("idle", 0.35);
      let dy = e.targetYaw - e.yaw;
      dy = Math.atan2(Math.sin(dy), Math.cos(dy));
      e.yaw += dy * Math.min(1, dt * (e.state === "combat" ? 9 : 4));
      e.model.position.copy(e.pos);
      e.model.rotation.y = e.yaw;
      e.model.updateMatrixWorld();
      // pitch the upper body toward the target, plus a flinch when hit
      let wantPitch = 0;
      if (e.aimAtTarget && e.target) {
        const te = e.target.eye();
        wantPitch = Math.atan2(te.y - 0.25 - (e.pos.y + 1.55), Math.hypot(te.x - e.pos.x, te.z - e.pos.z));
      }
      e.aimPitch += (wantPitch - e.aimPitch) * Math.min(1, dt * 8);
      e.flinch = Math.max(0, e.flinch - dt * 4);
      const pitch = e.aimPitch + e.flinch * 0.35;
      e.bones.spine.rotateX(-pitch * 0.5);
      e.bones.spine2.rotateX(-pitch * 0.5);
      if (e.flinch > 0) e.bones.spine.rotateZ(Math.sin(this.time * 40) * e.flinch * 0.05);
      if (e.marker) {
        e.marker.position.set(e.pos.x, e.pos.y + 2.15, e.pos.z);
        e.marker.visible = e.pos.distanceTo(player.pos) > 3;
      }
    }
    // ammo pickups
    for (const p of this.pickups) {
      if (!p.mesh.parent) continue;
      if (p.mesh.position.distanceTo(player.pos) < 1.4) {
        const name = game.weapon.addAmmo(p.type, p.amount);
        if (name) {
          p.mesh.parent.remove(p.mesh);
          this.audio.reload("in");
          game.hud.notify(`+${p.amount} ${name.split(" ")[0]} rounds`);
        }
      }
    }
  }

  // Candidate hostile targets for a soldier: the player (if hostile) and hostile soldiers.
  _candidates(e, pt) {
    const out = [];
    if (pt.alive && e.team !== pt.team) out.push(pt);
    for (const o of this.list) if (o !== e && o.alive && o.team !== e.team) out.push(o);
    return out;
  }

  _perceive(e, pt) {
    const eye = e.eye();
    const fwd = V3(-Math.sin(e.yaw), 0, -Math.cos(e.yaw));
    const w = AI_WEAPONS[e.weapon];
    const range = this.diff.view * w.range * (e.static ? 1.2 : 1);
    // pick the closest few candidates, then check line of sight
    const cands = this._candidates(e, pt)
      .map((t) => ({ t, d: t.pos.distanceTo(e.pos) }))
      .filter((c) => c.d < range)
      .sort((a, b) => a.d - b.d)
      .slice(0, 4);
    let best = null;
    let bestCos = 0;
    for (const { t, d } of cands) {
      const target = t.eye();
      const toT = target.clone().sub(eye).normalize();
      const cosA = fwd.dot(V3(toT.x, 0, toT.z).normalize());
      const inCone = e.state === "combat" || e.ally || cosA > Math.cos(THREE.MathUtils.degToRad(65));
      const r = t.crouched ? range * 0.7 : range;
      if (!inCone || d > r) continue;
      if (this.world.lineOfSight(eye, target) || this.world.lineOfSight(eye, t.chest())) {
        // prefer the current target, then whoever is closest
        if (!best || t === e.target) {
          best = { t, d };
          bestCos = cosA;
          if (t === e.target) break;
        }
      }
    }
    e.canSee = !!best;
    if (best) {
      const t = best.t;
      const closeness = 1 - best.d / range;
      const motion = Math.min(1, t.speed / 4);
      const gain = (0.35 + closeness * 2.2 + motion * 0.8) * (0.5 + Math.max(0, bestCos) * 0.5) * (t.crouched ? 0.6 : 1);
      e.awareness = Math.min(1.5, e.awareness + gain * (e.ally ? 0.35 : 0.2));
      if (e.state === "combat" && (!e.target || !e.target.alive || t !== e.target)) e.target = t;
      e.lastSeen = t.pos.clone();
      e.lastSeenTime = this.time;
      if (e.awareness >= 1 && e.state !== "combat") {
        this._enterCombat(e, t);
        for (const o of this.list) {
          if (o !== e && o.alive && o.team === e.team && o.state !== "combat" && !o.ally && o.pos.distanceTo(e.pos) < 30) {
            o.awareness = Math.max(o.awareness, 0.7);
            o.state = "alert";
            o.investigate = t.pos.clone();
            o.path = null;
          }
        }
      }
    } else {
      e.canSee = false;
      e.awareness = Math.max(0, e.awareness - 0.02);
    }
    if (e.target && !e.target.alive) {
      e.target = null;
      e.canSee = false;
    }
  }

  _behave(e, dt, pt, game) {
    switch (e.state) {
      case "follow":
        this._follow(e, dt, pt);
        break;
      case "guard":
        e.lookAround -= dt;
        if (e.lookAround <= 0) {
          e.lookAround = 3 + Math.random() * 4;
          e.targetYaw = e.yaw + (Math.random() - 0.5) * 1.6;
        }
        break;
      case "patrol":
        if (!e.path || e.pathIdx >= e.path.length) {
          if (e.waitT > 0) {
            e.waitT -= dt;
            break;
          }
          e.patrolIdx = (e.patrolIdx + 1) % e.patrol.length;
          e.goTo(e.patrol[e.patrolIdx]);
          e.waitT = 1.5 + Math.random() * 2;
        }
        if (e.followPath(1.4)) e.path = null;
        break;
      case "alert":
        if (e.investigate && !e.path && !e.static) {
          if (!e.goTo(e.investigate)) e.investigate = null;
        }
        if (e.path) {
          if (e.followPath(3.2)) {
            e.path = null;
            e.investigate = null;
            e.searchT = 6;
          }
        } else {
          if (e.static && e.investigate) e.targetYaw = Math.atan2(-(e.investigate.x - e.pos.x), -(e.investigate.z - e.pos.z));
          e.searchT = (e.searchT ?? 6) - dt;
          e.lookAround -= dt;
          if (e.lookAround <= 0) {
            e.lookAround = 1.2 + Math.random() * 1.5;
            e.targetYaw = e.yaw + (Math.random() - 0.5) * 2.5;
          }
          if (e.searchT <= 0) {
            e.state = e.patrol ? "patrol" : "guard";
            e.awareness = 0.3;
          }
        }
        break;
      case "combat":
        this._combat(e, dt, pt, game);
        break;
    }
  }

  // Squadmates keep a loose wedge around the player when there's nothing to shoot.
  _follow(e, dt, pt) {
    const p = pt.p;
    const slot = e.slot || [0, 4];
    const cos = Math.cos(p.yaw);
    const sin = Math.sin(p.yaw);
    // slot = [right, back] in the player's frame
    const want = V3(p.pos.x + slot[0] * cos + slot[1] * sin, 0, p.pos.z - slot[0] * sin + slot[1] * cos);
    const d = Math.hypot(want.x - e.pos.x, want.z - e.pos.z);
    e.repathT -= dt;
    if (d > 3 && (e.repathT <= 0 || !e.path)) {
      e.repathT = 0.8;
      if (!this.nav.walkable(want.x, want.z) || !e.goTo(want)) e.goTo(p.pos);
    }
    if (e.path) {
      const far = e.pos.distanceTo(p.pos) > 12;
      if (e.followPath(far ? 4.4 : Math.max(1.6, Math.min(4, p.horizSpeed + 0.5)))) e.path = null;
      if (d < 1.5) e.path = null;
    } else {
      e.targetYaw = p.yaw + slot[0] * 0.08;
    }
  }

  _combat(e, dt, pt, game) {
    const t = e.target;
    if (!t || !t.alive) {
      e.target = null;
      e.state = e.ally ? "follow" : "alert";
      e.searchT = 5;
      return;
    }
    const tp = t.pos;
    const w = AI_WEAPONS[e.weapon];
    if (e.canSee) {
      e.trackT += dt;
      e.aimAtTarget = true;
      e.targetYaw = Math.atan2(-(tp.x - e.pos.x), -(tp.z - e.pos.z));
      e.reactT -= dt;
      e.engageT -= dt;
      if (!e.static && e.engageT <= 0 && !e.path) {
        const dest = this._pickPosition(e, t, pt);
        if (dest && e.goTo(dest)) e.moveFast = Math.random() < 0.5;
        e.engageT = 2.5 + Math.random() * 3.5;
      }
      if (e.path) {
        if (e.followPath(e.moveFast ? 4.2 : 1.6)) e.path = null;
        e.targetYaw = Math.atan2(-(tp.x - e.pos.x), -(tp.z - e.pos.z));
      }
      const running = e.path && e.moveFast;
      if (e.reactT <= 0 && !running) {
        e.fireT -= dt;
        if (e.fireT <= 0) {
          if (e.burst <= 0) {
            e.burst = w.burst[0] + Math.floor(Math.random() * (w.burst[1] - w.burst[0] + 1));
            e.fireT = w.gap[0] + Math.random() * (w.gap[1] - w.gap[0]);
          } else {
            e.burst--;
            e.fireT = w.rof + Math.random() * 0.04;
            this._shoot(e, t, pt, game);
          }
        }
      }
    } else {
      e.trackT = Math.max(0, e.trackT - dt * 2);
      if (this.time - e.lastSeenTime > 1.2 && !e.path && !e.static && e.lastSeen) {
        if (!e.ally || e.lastSeen.distanceTo(pt.pos) < 25) {
          if (e.goTo(e.lastSeen)) e.moveFast = true;
        }
        e.lastSeen = null;
      }
      if (e.path) {
        if (e.followPath(e.moveFast ? 4.0 : 2)) e.path = null;
      } else if (this.time - e.lastSeenTime > (e.ally ? 4 : 8)) {
        e.target = null;
        e.state = e.ally ? "follow" : "alert";
        e.searchT = 8;
        e.investigate = null;
      }
      e.reactT = Math.max(e.reactT, 0.35 * this.diff.reaction);
    }
  }

  // A nearby reachable spot that still sees the target (shotgunners close in; the squad
  // stays near the player).
  _pickPosition(e, t, pt) {
    const target = t.eye();
    const closeIn = e.weapon === "SG";
    for (let i = 0; i < 10; i++) {
      const a = Math.random() * Math.PI * 2;
      const r = 4 + Math.random() * 8;
      const base = closeIn ? e.pos.clone().lerp(t.pos, 0.35) : e.pos;
      const p = V3(base.x + Math.cos(a) * r, 0, base.z + Math.sin(a) * r);
      if (!this.nav.walkable(p.x, p.z)) continue;
      if (p.distanceTo(t.pos) < 6) continue;
      if (e.ally && p.distanceTo(pt.pos) > 18) continue;
      if (this.world.lineOfSight(V3(p.x, 1.6, p.z), target)) return p;
    }
    return null;
  }

  _shoot(e, t, pt, game) {
    const w = AI_WEAPONS[e.weapon];
    const muzzle = e.muzzle.getWorldPosition(V3());
    const eye = e.eye();
    const aimPt = t.chest().add(V3(0, (Math.random() - 0.3) * 0.5, 0));
    const dist = eye.distanceTo(aimPt);
    const baseDir = aimPt.clone().sub(eye).normalize();
    // inaccuracy grows with range and target movement and shrinks as they track the target
    const settle = 2.2 - Math.min(1, e.trackT / 3.5) * 1.3;
    const spread = (0.02 + dist * 0.0005 + t.speed * 0.012 + (t.crouched ? 0 : 0.005)) * this.diff.spread * w.spread
      * settle * (e.path ? 2.2 : 1) * (e.flinch > 0 ? 2.5 : 1) * (1 + e.suppression * 1.5) * (e.ally ? 1.15 : 1);
    const pellets = w.pellets || 1;
    let end = null;
    for (let i = 0; i < pellets; i++) {
      const s = spread + (w.pelletSpread || 0);
      const dir = baseDir.clone().add(V3((Math.random() - 0.5) * 2 * s, (Math.random() - 0.5) * 2 * s, (Math.random() - 0.5) * 2 * s)).normalize();
      const wHit = this.world.raycast(eye, dir, 400);
      let maxD = wHit ? wHit.dist : 400;
      const rayEnd = eye.clone().addScaledVector(dir, maxD);
      // who is hit first: the player (if hostile) or a hostile soldier
      let hitPlayer = null;
      if (pt.alive && pt.team !== e.team) hitPlayer = pt.hitTest(eye, rayEnd);
      const sHit = this.raycast(eye, dir, maxD, e.team, e);
      if (hitPlayer !== null && (!sHit || hitPlayer < sHit.dist)) {
        end = eye.clone().addScaledVector(dir, hitPlayer);
        const [lo, hi] = w.dmg;
        const falloff = w.pellets ? THREE.MathUtils.clamp(1 - (hitPlayer - 10) / 25, 0.2, 1) : 1;
        pt.p.takeDamage((lo + Math.random() * (hi - lo)) * this.diff.damage * falloff, e.pos.clone(), game);
      } else if (sHit) {
        end = sHit.point;
        const d = WEAPONS[e.weapon].dmg[sHit.part];
        const falloff = w.pellets ? THREE.MathUtils.clamp(1 - (sHit.dist - 10) / 25, 0.2, 1) : 1;
        // soldiers do a bit less than the player's weapons so firefights last
        this.damage(sHit, dir, game, (d[0] + Math.random() * (d[1] - d[0])) * 0.8 * falloff, e);
        if (i < 2) this.fx.bloodHit(sHit.point, dir);
        if (i === 0 && sHit.point.distanceTo(pt.pos) < 30) this.audio.impact("flesh", sHit.point);
      } else {
        end = rayEnd;
        if (wHit && i < 3) {
          this.fx.impact(wHit.point, wHit.normal, wHit.surface, pellets > 1 ? 0.5 : 1);
          if (i === 0 && wHit.point.distanceTo(pt.pos) < 14) this.audio.impact(wHit.surface, wHit.point);
        }
      }
      // near miss on the player: supersonic crack
      if (i === 0 && pt.alive && !pt.p.dead) {
        const pa = V3(pt.pos.x, pt.pos.y + 0.25, pt.pos.z);
        const pb = V3(pt.pos.x, pt.pos.y + pt.p.height, pt.pos.z);
        const closest = segSeg(eye, rayEnd, pa, pb);
        if (closest[0] < 3 && closest[0] > 0.3 && closest[1] > 0.05) {
          this.audio.crack(closest[3]);
          if (pt.team !== e.team) game.onNearMiss();
        }
      }
      if (i === 0) this.suppress(eye, dir, maxD, e);
    }
    this.fx.flash(muzzle, baseDir, false);
    if (Math.random() < w.tracer && end) this.fx.tracer(muzzle, end, 500);
    this.audio.gunshot(w.sound, muzzle, 1);
    this.hearShot(muzzle, 60, e);
  }
}
