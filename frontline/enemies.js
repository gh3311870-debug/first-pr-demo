// Enemy soldiers: animation, perception (sight + hearing), navigation, combat, hit boxes.
import * as THREE from "../vendor/three-r186/three-bundle.min.js";
import { styleRifleMaterials } from "./weapon.js";

const V3 = (x = 0, y = 0, z = 0) => new THREE.Vector3(x, y, z);
const tmp1 = V3();
const tmp2 = V3();

export const DIFFICULTY = {
  recruit: { damage: [7, 11], spread: 1.5, reaction: 1.4, view: 70 },
  regular: { damage: [10, 16], spread: 1.0, reaction: 1.0, view: 90 },
  veteran: { damage: [16, 24], spread: 0.75, reaction: 0.75, view: 110 },
};

const TINTS = [0x8c8878, 0x7d8764, 0x967f64, 0x6f746c];

// closest distance between segment p0-p1 and segment q0-q1; returns [dist, s, t]
function segSeg(p0, p1, q0, q1) {
  const d1 = tmp1.copy(p1).sub(p0);
  const d2 = tmp2.copy(q1).sub(q0);
  const r = p0.clone().sub(q0);
  const a = d1.dot(d1);
  const e = d2.dot(d2);
  const f = d2.dot(r);
  let s;
  let t;
  const c = d1.dot(r);
  const b = d1.dot(d2);
  const denom = a * e - b * b;
  s = denom > 1e-9 ? THREE.MathUtils.clamp((b * f - c * e) / denom, 0, 1) : 0;
  t = (b * s + f) / e;
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

class Enemy {
  constructor(sys, spawn, idx) {
    this.sys = sys;
    this.idx = idx;
    const A = sys.assets;
    const model = THREE.SkeletonUtils.clone(A.operator.scene);
    this.model = model;
    const tint = TINTS[idx % TINTS.length];
    model.traverse((o) => {
      if (!o.isMesh) return;
      o.castShadow = true;
      o.receiveShadow = true;
      o.frustumCulled = false;
      if (o.material && o.material.name === "VanguardBodyMat") o.material = sys.bodyMaterial(tint);
    });
    styleRifleMaterials(model);
    sys.engine.scene.add(model);
    this.mixer = new THREE.AnimationMixer(model);
    const clip = (n) => A.operator.animations.find((a) => a.name === n);
    this.actions = {
      idle: this.mixer.clipAction(clip("AIM_Idle")),
      walk: this.mixer.clipAction(clip("AIM_Walk")),
      run: this.mixer.clipAction(clip("AIM_Run")),
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
    this.muzzle = model.getObjectByName("Muzzle");

    this.pos = V3(spawn.x, spawn.y || 0, spawn.z);
    this.home = this.pos.clone();
    this.yaw = spawn.yaw || 0;
    this.targetYaw = this.yaw;
    this.static = !!spawn.static;
    this.patrol = spawn.path ? spawn.path.map(([x, z]) => V3(x, 0, z)) : null;
    this.patrolIdx = 0;
    this.health = 100;
    this.state = this.patrol ? "patrol" : "guard";
    this.awareness = 0;
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
    this.deadT = 0;
    this.velocity = V3();
  }

  get alive() {
    return this.state !== "dead";
  }

  eye() {
    return V3(this.pos.x, this.pos.y + 1.62, this.pos.z);
  }

  setAnim(name, fade = 0.3) {
    if (this.anim === name) return;
    const next = this.actions[name];
    next.reset().play();
    if (this.anim) {
      next.crossFadeFrom(this.actions[this.anim], fade, true);
    }
    this.anim = name;
  }

  followPath(dt, speed) {
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
    if (!this.aimAtPlayer) this.targetYaw = Math.atan2(-dx, -dz);
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
  constructor(engine, assets, world, nav, fx, audio, difficulty) {
    this.engine = engine;
    this.assets = assets;
    this.world = world;
    this.nav = nav;
    this.fx = fx;
    this.audio = audio;
    this.diff = DIFFICULTY[difficulty] || DIFFICULTY.regular;
    this.list = [];
    this.pickups = [];
    this._bodyMats = new Map();
    this.time = 0;
    // loose magazine mesh for ammo pickups
    const mag = assets.operator.scene.getObjectByName("Mag");
    this.magGeo = mag ? mag.geometry : new THREE.BoxGeometry(0.02, 0.18, 0.06);
    this.magMat = mag ? mag.material : new THREE.MeshStandardMaterial({ color: 0x3a3020 });
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
    spawns.forEach((s, i) => this.list.push(new Enemy(this, s, i)));
  }

  get aliveCount() {
    return this.list.filter((e) => e.alive).length;
  }

  hearShot(pos, radius) {
    for (const e of this.list) {
      if (!e.alive) continue;
      const d = e.pos.distanceTo(pos);
      if (d > radius) continue;
      // gunfire gives away your rough position
      e.awareness = Math.min(1.2, e.awareness + (1 - d / radius) * 1.5 + 0.3);
      if (e.state !== "combat") {
        e.state = "alert";
        e.investigate = pos.clone().add(V3((Math.random() - 0.5) * 8, 0, (Math.random() - 0.5) * 8));
        e.investigate.y = 0;
        e.path = null;
      }
    }
  }

  // Rounds passing close to a soldier rattle him: worse aim for a moment, and he knows where you are.
  suppress(origin, dir, dist, player) {
    const end = origin.clone().addScaledVector(dir, dist);
    for (const e of this.list) {
      if (!e.alive) continue;
      const c = V3(e.pos.x, e.pos.y + 1.2, e.pos.z);
      const [d] = segSeg(origin, end, c, V3(c.x, c.y + 0.5, c.z));
      if (d < 2.5) {
        e.suppression = Math.min(1, e.suppression + (1 - d / 2.5) * 0.45);
        e.trackT = Math.max(0, e.trackT - 0.4);
        if (e.state !== "combat") {
          e.awareness = 1.2;
          this._enterCombat(e, player);
        }
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

  raycast(origin, dir, maxDist) {
    let best = null;
    const end = origin.clone().addScaledVector(dir, maxDist);
    for (const e of this.list) {
      if (!e.alive) continue;
      // cheap reject: distance from ray to enemy centre
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
          // head beats other parts when both are hit at almost the same distance
          best = { dist: hitT, enemy: e, part: s.part, point: origin.clone().addScaledVector(dir, hitT) };
        }
      }
    }
    return best;
  }

  damage(hit, dir, game) {
    const e = hit.enemy;
    const dmg = hit.part === "head" ? 150 : hit.part === "torso" ? 36 + Math.random() * 10 : 22 + Math.random() * 6;
    e.health -= dmg;
    e.flinch = 1;
    e.awareness = 1.5;
    if (e.state !== "combat") this._enterCombat(e, game.player);
    if (e.health <= 0) {
      this._kill(e, hit, dir, game);
      game.onKill(hit.part === "head");
    } else {
      game.hud.hitmarker(false);
      this.audio.hitmarker("hit");
      // a hit soldier breaks off and moves
      e.engageT = Math.min(e.engageT, 0.3);
    }
  }

  _kill(e, hit, dir, game) {
    e.state = "dead";
    e.velocity.set(0, 0, 0);
    // face away from the shot so the backwards fall reads as a reaction to it
    e.yaw = Math.atan2(dir.x, dir.z);
    e.model.rotation.y = e.yaw;
    e.setAnim("death", 0.12);
    e.actions.death.timeScale = 1.1;
    this.audio.hitmarker(hit.part === "head" ? "head" : "kill");
    // drop a magazine
    const m = new THREE.Mesh(this.magGeo, this.magMat);
    m.castShadow = true;
    m.position.set(e.pos.x + (Math.random() - 0.5) * 0.6, e.pos.y + 0.03, e.pos.z + (Math.random() - 0.5) * 0.6);
    m.rotation.set(Math.PI / 2, 0, Math.random() * 6);
    this.engine.scene.add(m);
    this.pickups.push({ mesh: m, amount: 30 });
    // nearby soldiers react to a comrade going down
    for (const o of this.list) {
      if (o !== e && o.alive && o.pos.distanceTo(e.pos) < 25) {
        o.awareness = Math.max(o.awareness, 0.8);
        if (o.state !== "combat") {
          o.state = "alert";
          o.investigate = e.pos.clone();
        }
      }
    }
  }

  _enterCombat(e, player) {
    e.state = "combat";
    e.reactT = (0.45 + Math.random() * 0.5) * this.diff.reaction;
    e.engageT = 1.5 + Math.random() * 2.5;
    e.lastSeen = player.pos.clone();
    e.path = null;
  }

  // ---- main update ------------------------------------------------------------------
  update(dt, player, game) {
    this.time += dt;
    const pEye = player.eyePos;
    for (const e of this.list) {
      e.mixer.update(dt);
      if (!e.alive) {
        e.model.position.copy(e.pos);
        continue;
      }
      e.velocity.set(0, 0, 0);
      e.aimAtPlayer = false;
      e.suppression = Math.max(0, e.suppression - dt * 0.5);
      e.thinkT -= dt;
      if (e.thinkT <= 0) {
        e.thinkT = 0.15 + Math.random() * 0.1;
        this._perceive(e, player);
      }
      this._behave(e, dt, player, game);
      // movement with collision
      if (e.velocity.lengthSq() > 0 && !e.static) {
        // keep a little distance from each other
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
        const v = e.velocity.clone();
        v.y = -1;
        this.world.moveCylinder(e.pos, v, dt, 0.3, 1.75);
        e.stepDist += Math.hypot(e.velocity.x, e.velocity.z) * dt;
        if (e.stepDist > 1.6) {
          e.stepDist = 0;
          if (e.pos.distanceTo(player.pos) < 22) this.audio.footstep(e.pos.clone(), 0.55);
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
      // turn smoothly
      let dy = e.targetYaw - e.yaw;
      dy = Math.atan2(Math.sin(dy), Math.cos(dy));
      e.yaw += dy * Math.min(1, dt * (e.state === "combat" ? 9 : 4));
      e.model.position.copy(e.pos);
      e.model.rotation.y = e.yaw;
      e.model.updateMatrixWorld();
      // pitch the upper body toward the target, plus a flinch when hit
      const wantPitch = e.aimAtPlayer ? Math.atan2(pEye.y - 0.25 - (e.pos.y + 1.55), Math.hypot(pEye.x - e.pos.x, pEye.z - e.pos.z)) : 0;
      e.aimPitch += (wantPitch - e.aimPitch) * Math.min(1, dt * 8);
      e.flinch = Math.max(0, e.flinch - dt * 4);
      const pitch = e.aimPitch + e.flinch * 0.35;
      e.bones.spine.rotateX(-pitch * 0.5);
      e.bones.spine2.rotateX(-pitch * 0.5);
      if (e.flinch > 0) e.bones.spine.rotateZ(Math.sin(this.time * 40) * e.flinch * 0.05);
    }
    // pickups
    for (const p of this.pickups) {
      if (!p.mesh.parent) continue;
      if (p.mesh.position.distanceTo(player.pos) < 1.4 && game.weapon.reserve < 300) {
        game.weapon.reserve += p.amount;
        p.mesh.parent.remove(p.mesh);
        this.audio.reload("in");
        game.hud.notify("+30 rounds 5.56");
      }
    }
  }

  _perceive(e, player) {
    const eye = e.eye();
    const target = player.eyePos;
    const toP = target.clone().sub(eye);
    const dist = toP.length();
    toP.divideScalar(dist);
    const fwd = V3(-Math.sin(e.yaw), 0, -Math.cos(e.yaw));
    const cosA = fwd.dot(V3(toP.x, 0, toP.z).normalize());
    const inCone = e.state === "combat" ? true : cosA > Math.cos(THREE.MathUtils.degToRad(65));
    const range = this.diff.view * (player.crouched ? 0.7 : 1);
    let visible = false;
    if (dist < range && inCone && !player.dead) {
      visible = this.world.lineOfSight(eye, target) || this.world.lineOfSight(eye, player.chest);
    }
    e.canSee = visible;
    if (visible) {
      // awareness builds faster when close, when the player moves, and in the centre of view
      const closeness = 1 - dist / range;
      const motion = Math.min(1, player.horizSpeed / 4);
      const gain = (0.35 + closeness * 2.2 + motion * 0.8) * (0.5 + Math.max(0, cosA) * 0.5) * (player.crouched ? 0.6 : 1);
      e.awareness = Math.min(1.5, e.awareness + gain * 0.2);
      e.lastSeen = player.pos.clone();
      e.lastSeenTime = this.time;
      if (e.awareness >= 1 && e.state !== "combat") {
        this._enterCombat(e, player);
        // shout: alert friends nearby
        for (const o of this.list) {
          if (o !== e && o.alive && o.state !== "combat" && o.pos.distanceTo(e.pos) < 30) {
            o.awareness = Math.max(o.awareness, 0.7);
            o.state = "alert";
            o.investigate = player.pos.clone();
            o.path = null;
          }
        }
      }
    } else {
      e.awareness = Math.max(0, e.awareness - 0.02);
    }
  }

  _behave(e, dt, player, game) {
    const now = this.time;
    switch (e.state) {
      case "guard":
        if (!e.path) {
          e.lookAround -= dt;
          if (e.lookAround <= 0) {
            e.lookAround = 3 + Math.random() * 4;
            e.targetYaw = e.yaw + (Math.random() - 0.5) * 1.6;
          }
        }
        break;
      case "patrol": {
        if (!e.path || e.pathIdx >= e.path.length) {
          if (e.waitT > 0) {
            e.waitT -= dt;
            break;
          }
          e.patrolIdx = (e.patrolIdx + 1) % e.patrol.length;
          e.goTo(e.patrol[e.patrolIdx]);
          e.waitT = 1.5 + Math.random() * 2;
        }
        if (e.followPath(dt, 1.4)) e.path = null;
        break;
      }
      case "alert": {
        // move toward the noise, weapon up
        if (e.investigate && !e.path && !e.static) {
          if (!e.goTo(e.investigate)) e.investigate = null;
        }
        if (e.path) {
          if (e.followPath(dt, 3.2)) {
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
      }
      case "combat":
        this._combat(e, dt, player, game, now);
        break;
    }
  }

  _combat(e, dt, player, game, now) {
    const pPos = player.pos;
    if (e.canSee) {
      e.trackT += dt;
      e.aimAtPlayer = true;
      e.targetYaw = Math.atan2(-(pPos.x - e.pos.x), -(pPos.z - e.pos.z));
      e.reactT -= dt;
      e.engageT -= dt;
      // reposition now and then (not static shooters)
      if (!e.static && e.engageT <= 0 && !e.path) {
        const dest = this._pickPosition(e, player);
        if (dest && e.goTo(dest)) e.moveFast = Math.random() < 0.5;
        e.engageT = 2.5 + Math.random() * 3.5;
      }
      if (e.path) {
        if (e.followPath(dt, e.moveFast ? 4.2 : 1.6)) e.path = null;
        e.targetYaw = Math.atan2(-(pPos.x - e.pos.x), -(pPos.z - e.pos.z));
      }
      // shooting in bursts (not while sprinting)
      const running = e.path && e.moveFast;
      if (e.reactT <= 0 && !running) {
        e.fireT -= dt;
        if (e.fireT <= 0) {
          if (e.burst <= 0) {
            e.burst = 2 + Math.floor(Math.random() * 5);
            e.fireT = 0.5 + Math.random() * 0.9;
          } else {
            e.burst--;
            e.fireT = 0.1 + Math.random() * 0.04;
            this._shoot(e, player, game);
          }
        }
      }
    } else {
      e.trackT = Math.max(0, e.trackT - dt * 2);
      // lost sight: push to where the player was last seen
      if (now - e.lastSeenTime > 1.2 && !e.path && !e.static && e.lastSeen) {
        if (e.goTo(e.lastSeen)) e.moveFast = true;
        e.lastSeen = null;
      }
      if (e.path) {
        if (e.followPath(dt, e.moveFast ? 4.0 : 2)) {
          e.path = null;
        }
      } else if (now - e.lastSeenTime > 8) {
        e.state = "alert";
        e.searchT = 8;
        e.investigate = null;
      }
      e.reactT = Math.max(e.reactT, 0.35 * this.diff.reaction);
    }
  }

  // a nearby spot, reachable, that still has line of sight to the player
  _pickPosition(e, player) {
    const target = player.eyePos;
    for (let i = 0; i < 10; i++) {
      const a = Math.random() * Math.PI * 2;
      const r = 4 + Math.random() * 8;
      const p = V3(e.pos.x + Math.cos(a) * r, 0, e.pos.z + Math.sin(a) * r);
      if (!this.nav.walkable(p.x, p.z)) continue;
      if (p.distanceTo(player.pos) < 6) continue;
      if (this.world.lineOfSight(V3(p.x, 1.6, p.z), target)) return p;
    }
    return null;
  }

  _shoot(e, player, game) {
    const muzzle = e.muzzle.getWorldPosition(V3());
    const eye = e.eye();
    const target = player.chest.add(V3(0, (Math.random() - 0.3) * 0.5, 0));
    const dist = eye.distanceTo(target);
    const dir = target.clone().sub(eye).normalize();
    // inaccuracy grows with range and target movement; first shots of an engagement are worse
    // aim settles the longer they track you: first shots of an engagement mostly miss
    const settle = 2.2 - Math.min(1, e.trackT / 3.5) * 1.3;
    const spread = (0.02 + dist * 0.0005 + player.horizSpeed * 0.012 + (player.crouched ? 0 : 0.005)) * this.diff.spread
      * settle * (e.path ? 2.2 : 1) * (e.flinch > 0 ? 2.5 : 1) * (1 + e.suppression * 1.5);
    dir.add(V3((Math.random() - 0.5) * 2 * spread, (Math.random() - 0.5) * 2 * spread, (Math.random() - 0.5) * 2 * spread)).normalize();
    const wHit = this.world.raycast(eye, dir, 400);
    const maxD = wHit ? wHit.dist : 400;
    // player capsule test
    const pa = V3(player.pos.x, player.pos.y + 0.25, player.pos.z);
    const pb = V3(player.pos.x, player.pos.y + player.height - 0.2, player.pos.z);
    const end = eye.clone().addScaledVector(dir, maxD);
    const [d, s] = segSeg(eye, end, pa, pb);
    let hitPoint;
    if (d < 0.32 && !player.dead) {
      hitPoint = eye.clone().addScaledVector(dir, s * maxD);
      const [lo, hi] = this.diff.damage;
      player.takeDamage(lo + Math.random() * (hi - lo), e.pos.clone(), game);
    } else {
      hitPoint = end;
      if (wHit) {
        this.fx.impact(wHit.point, wHit.normal, wHit.surface);
        if (wHit.point.distanceTo(player.pos) < 12) this.audio.impact(wHit.surface, wHit.point);
      }
      // near miss: supersonic crack
      const closest = segSeg(eye, end, pa, pb);
      if (closest[0] < 3) {
        this.audio.crack(closest[3]);
        game.onNearMiss();
      }
    }
    this.fx.flash(muzzle, dir, false);
    if (Math.random() < 0.5) this.fx.tracer(muzzle, hitPoint, 500);
    this.audio.gunshot(muzzle, 1);
  }
}
