// First-person arsenal: M4 carbine, DMR, pump shotgun and pistol on one Blender-rigged set of
// arms. Handles switching, ADS (red dot, scope, iron sights), recoil, reloads and ballistics.
import * as THREE from "../vendor/three-r186/three-bundle.min.js";

const V3 = (x = 0, y = 0, z = 0) => new THREE.Vector3(x, y, z);

// damage: head / torso / limb (random between the two values)
export const WEAPONS = {
  M4: {
    name: "M4A1 CARBINE", prefix: "", slot: 1, sound: "rifle", modes: ["auto", "semi"], rpm: 780, mag: 30, reserve: 180,
    dmg: { head: [150, 150], torso: [36, 46], limb: [22, 28] }, spread: [0.03, 0.0022], recoil: [0.013, 0.006],
    zoom: 1.35, eyeRelief: 0.25, hip: [0.02, -0.02, -0.05], tracerEvery: 3, vfov: [54, 40], adsNear: 0.05,
    reload: { action: "FP_Reload_M4", rate: 1.1, events: [[0.18, "out"], [0.62, "in"], [0.7, "slap"]] }, ammoType: "556",
  },
  DMR: {
    name: "MK20 DMR", prefix: "DMR_", slot: 2, sound: "dmr", modes: ["semi"], rpm: 280, mag: 20, reserve: 80,
    dmg: { head: [250, 250], torso: [72, 86], limb: [45, 52] }, spread: [0.035, 0.0004], recoil: [0.032, 0.008],
    zoom: 4.5, scope: true, eyeRelief: 0.17, hip: [0.02, -0.025, -0.08], tracerEvery: 1, vfov: [54, 34],
    reload: { action: "FP_Reload_DMR", rate: 1.0, events: [[0.18, "out"], [0.62, "in"], [0.7, "slap"]] }, ammoType: "762",
  },
  SG: {
    name: "M590 SHOTGUN", prefix: "SG_", slot: 3, sound: "shotgun", modes: ["pump"], rpm: 90, mag: 7, reserve: 35,
    pellets: 9, pelletSpread: [0.05, 0.036], falloff: [12, 38],
    dmg: { head: [45, 50], torso: [17, 21], limb: [11, 13] }, spread: [0.02, 0.01], recoil: [0.05, 0.012],
    zoom: 1.15, eyeRelief: 0.19, hip: [0.02, -0.03, -0.02], tracerEvery: 0, vfov: [54, 44], adsNear: 0.06, ammoType: "12g",
  },
  PST: {
    name: "M17 PISTOL", prefix: "PST_", slot: 4, sound: "pistol", modes: ["semi"], rpm: 420, mag: 17, reserve: 85,
    dmg: { head: [120, 120], torso: [27, 33], limb: [16, 20] }, spread: [0.02, 0.004], recoil: [0.022, 0.008],
    zoom: 1.2, eyeRelief: 0.32, hipFromAds: [0.055, -0.075, 0.0], hipRot: [0.03, -0.06, 0.08], hip: [0, 0, 0], tracerEvery: 0, vfov: [54, 44], adsNear: 0.22, fastSwitch: true,
    reload: { action: "FP_Reload_PST", rate: 1.05, events: [[0.14, "out"], [0.66, "in"], [0.72, "slap"]] }, ammoType: "9mm",
  },
};
export const ORDER = ["M4", "DMR", "SG", "PST"];

class Spring {
  constructor(k = 120, d = 18) {
    this.k = k;
    this.d = d;
    this.x = V3();
    this.v = V3();
  }
  impulse(v) {
    this.v.add(v);
  }
  update(dt) {
    const a = this.x.clone().multiplyScalar(-this.k).addScaledVector(this.v, -this.d);
    this.v.addScaledVector(a, dt);
    this.x.addScaledVector(this.v, dt);
  }
}

const rnd = ([a, b]) => a + Math.random() * (b - a);
const ease = (t) => t * t * (3 - 2 * t);

export class Weapon {
  constructor(engine, assets, fx, audio, world) {
    this.engine = engine;
    this.fx = fx;
    this.audio = audio;
    this.world = world;
    this.state = {};
    for (const k of ORDER) {
      const d = WEAPONS[k];
      this.state[k] = { ammo: d.mag, reserve: d.reserve, mode: d.modes[0] };
    }
    this.current = "M4";
    this.pending = null;
    this.switchT = 0; // 0..1 lowering, 1..2 raising
    this.cooldown = 0;
    this.reloading = false;
    this.busy = 0; // pump cycle blocks firing
    this.adsT = 0;
    this.bloom = 0;
    this.shots = 0;
    this.hits = 0;
    this.triggerHeld = false;
    this.kick = new Spring(260, 26);
    this.kickRot = new Spring(220, 22);
    this.sway = V3();
    this.bobT = 0;
    this.sprintT = 0;
    this.landDip = new Spring(90, 14);
    this.breath = 1;
    this.scopeSwayX = 0;
    this.scopeSwayY = 0;
    this._buildViewmodel(assets);
    this._activate("M4");
  }

  get def() {
    return WEAPONS[this.current];
  }
  get ammo() {
    return this.state[this.current].ammo;
  }
  set ammo(v) {
    this.state[this.current].ammo = v;
  }
  get reserve() {
    return this.state[this.current].reserve;
  }
  set reserve(v) {
    this.state[this.current].reserve = v;
  }
  get mode() {
    return this.state[this.current].mode;
  }
  get aiming() {
    return this.adsT > 0.6;
  }
  get scoped() {
    return !!this.def.scope && this.adsT > 0.92;
  }

  // Adds picked-up ammo to the weapon that uses it; returns that weapon's name.
  addAmmo(type, amount) {
    for (const k of ORDER) {
      const d = WEAPONS[k];
      if (d.ammoType === type) {
        const st = this.state[k];
        if (st.reserve >= d.reserve * 2) return null;
        st.reserve = Math.min(d.reserve * 2, st.reserve + amount);
        return d.name;
      }
    }
    return null;
  }

  _buildViewmodel(assets) {
    const rig = THREE.SkeletonUtils.clone(assets.operator.scene);
    this.rig = rig;
    rig.traverse((o) => {
      if (!o.isMesh) return;
      o.frustumCulled = false;
      o.castShadow = false;
      o.receiveShadow = false;
      if (o.name.includes("visor")) o.visible = false;
      if (o.material && o.material.name === "VanguardBodyMat") {
        o.material = o.material.clone();
        o.material.color.set(0x4a473e); // darker, desaturated sleeves and gloves
        o.material.roughness = 1;
        o.material.envMapIntensity = 0.5;
      }
    });
    styleRifleMaterials(rig);
    this.root = new THREE.Group();
    this.root.add(rig);
    this.engine.vmScene.add(this.root);
    this.mixer = new THREE.AnimationMixer(rig);
    this.clips = Object.fromEntries(assets.operator.animations.map((a) => [a.name, a]));
    this.actions = {};
    this.head = rig.getObjectByName("mixamorigHead");
    this.eye = rig.getObjectByName("Eye");
    // per-weapon pieces, and offsets measured from each weapon's hold pose
    this.parts = {};
    for (const k of ORDER) {
      const p = WEAPONS[k].prefix;
      this.parts[k] = {
        root: rig.getObjectByName(p + "Rifle"), mag: rig.getObjectByName(p + "Mag"),
        sight: rig.getObjectByName(p + "SightAxis"), muzzle: rig.getObjectByName(p + "Muzzle"),
        eject: rig.getObjectByName(p + "Eject"), reticle: rig.getObjectByName(p + "Reticle"),
      };
    }
    if (this.parts.M4.reticle) this.parts.M4.reticle.scale.setScalar(1.6);
    // Measure each weapon's hold pose (camera = eye) and its aim pose (where the sights end up).
    const measure = (clip) => {
      this.mixer.stopAllAction();
      this.action(clip).play();
      this.mixer.update(0);
      rig.position.set(0, 0, 0);
      rig.updateMatrixWorld(true);
    };
    for (const k of ORDER) {
      const d = WEAPONS[k];
      measure("FP_Hold_" + k);
      const e = this.eye.getWorldPosition(V3());
      measure("FP_ADS_" + k);
      const s = this.parts[k].sight.getWorldPosition(V3());
      const rel = s.clone().sub(e);
      this.parts[k].rigPos = e.clone().negate();
      // small correction so the sight lands exactly on the view axis at the eye relief
      this.parts[k].adsPos = V3(-rel.x, -rel.y, -d.eyeRelief - rel.z);
      // pistol: the hip position is a lowered aim pose (compressed ready) rather than its own pose
      this.parts[k].hipPos = d.hipFromAds ? this.parts[k].adsPos.clone().add(V3(...d.hipFromAds)) : V3(...d.hip);
    }
    this.mixer.stopAllAction();
    // muzzle flash (viewmodel scene), re-parented to the active weapon's muzzle
    const fm = new THREE.MeshBasicMaterial({ map: this.fx.flashTex, blending: THREE.AdditiveBlending, depthWrite: false, transparent: true, toneMapped: false });
    this.flashMesh = new THREE.Group();
    for (let i = 0; i < 2; i++) {
      const p = new THREE.Mesh(new THREE.PlaneGeometry(0.22, 0.22), fm);
      if (i === 1) p.rotation.y = Math.PI / 2;
      p.position.z = -0.08;
      this.flashMesh.add(p);
    }
    this.flashMesh.add(new THREE.Mesh(new THREE.PlaneGeometry(0.16, 0.16), fm));
    this.flashMesh.visible = false;
    this.flashT = 0;
  }

  action(name) {
    if (!this.actions[name]) this.actions[name] = this.mixer.clipAction(this.clips[name]);
    return this.actions[name];
  }

  _playOnce(name, rate = 1, fade = 0.1) {
    // one-shot clips (reloads, pump) replace the hold/aim pose while they play
    this.oneShots = this.oneShots || new Set();
    for (const n of this.oneShots) if (n !== name) this.action(n).fadeOut(fade);
    this.oneShots.add(name);
    const a = this.action(name);
    a.reset();
    a.setLoop(THREE.LoopOnce, 1);
    a.clampWhenFinished = true;
    a.timeScale = rate;
    a.setEffectiveWeight(1);
    a.fadeIn(fade);
    a.play();
    return a.getClip().duration / rate;
  }

  _activate(key) {
    this.current = key;
    this.mixer.stopAllAction();
    this.oneShots = new Set();
    this.holdAct = this.action("FP_Hold_" + key).reset().play();
    this.adsAct = this.action("FP_ADS_" + key).reset().play();
    this.adsAct.setEffectiveWeight(0);
    for (const k of ORDER) {
      const p = this.parts[k];
      p.root.visible = k === key;
      if (p.mag) p.mag.visible = k === key;
    }
    this.rig.position.copy(this.parts[key].rigPos);
    this.parts[key].muzzle.add(this.flashMesh);
    this.flashMesh.scale.setScalar(key === "SG" ? 1.4 : key === "PST" ? 0.7 : 1);
    this.reloading = false;
    this.busy = 0;
    this.sgReload = null;
  }

  switchTo(key) {
    if (!WEAPONS[key] || (key === this.current && !this.pending)) return;
    if (this.pending === key) return;
    this.pending = key;
    if (this.switchT === 0) this.switchT = 0.001;
    else if (this.switchT > 1) this.switchT = 2 - this.switchT; // lower again from where it is
    this.reloading = false;
    this.sgReload = null;
    this.audio.reload("switch");
  }

  cycle(dir) {
    const i = ORDER.indexOf(this.pending || this.current);
    this.switchTo(ORDER[(i + dir + ORDER.length) % ORDER.length]);
  }

  // ---- reloads ------------------------------------------------------------------------
  startReload() {
    const d = this.def;
    const st = this.state[this.current];
    const cap = d.mag + (st.ammo > 0 && !d.pellets ? 1 : 0);
    if (this.reloading || this.switchT > 0 || this.busy > 0 || st.ammo >= cap || st.reserve <= 0) return;
    this.reloading = true;
    this.reloadT = 0;
    if (d.pellets) {
      this.sgReload = { phase: "start", t: 0, dur: this._playOnce("FP_ReloadStart_SG", 1.1), wasEmpty: st.ammo === 0 };
      return;
    }
    this.reloadDur = this._playOnce(d.reload.action, d.reload.rate, 0.12);
    this.reloadEvents = d.reload.events.map((e) => e.slice());
  }

  _finishReload() {
    const d = this.def;
    const st = this.state[this.current];
    const cap = st.ammo > 0 ? d.mag + 1 : d.mag; // keeps the round in the chamber
    const take = Math.min(cap - st.ammo, st.reserve);
    st.ammo += take;
    st.reserve -= take;
    this.reloading = false;
    this.action(d.reload.action).fadeOut(0.2);
  }

  _updateShotgunReload(dt, input) {
    const r = this.sgReload;
    const st = this.state.SG;
    r.t += dt;
    if (r.phase === "start" && r.t >= r.dur) {
      r.phase = "shell";
      r.t = 0;
      r.inserted = false;
      r.dur = this._playOnce("FP_ReloadShell_SG", 1.0, 0.05);
    } else if (r.phase === "shell") {
      if (!r.inserted && r.t >= r.dur * 0.78) {
        r.inserted = true;
        st.ammo++;
        st.reserve--;
        this.audio.reload("shell");
      }
      if (r.t >= r.dur) {
        // keep loading until full or out of shells; pulling the trigger stops early
        if (st.ammo < WEAPONS.SG.mag && st.reserve > 0 && !input.fire) {
          r.t = 0;
          r.inserted = false;
          r.dur = this._playOnce("FP_ReloadShell_SG", 1.0, 0.02);
        } else {
          r.phase = "end";
          r.t = 0;
          r.dur = this._playOnce("FP_ReloadEnd_SG", 1.1, 0.05);
        }
      }
    } else if (r.phase === "end" && r.t >= r.dur) {
      this.sgReload = null;
      this.reloading = false;
      for (const n of ["FP_ReloadStart_SG", "FP_ReloadShell_SG", "FP_ReloadEnd_SG"]) this.action(n).fadeOut(0.15);
      if (r.wasEmpty) this._pump(false);
    }
  }

  _pump(eject = true) {
    this.busy = this._playOnce("FP_Pump_SG", 1.15, 0.05);
    this.pumpT = 0;
    this.pumpSound = false;
    this.pumpEjected = !eject;
  }

  toggleMode() {
    const d = this.def;
    const st = this.state[this.current];
    if (d.modes.length < 2) return;
    st.mode = d.modes[(d.modes.indexOf(st.mode) + 1) % d.modes.length];
    this.audio.reload("switch");
  }

  spread(player) {
    const d = this.def;
    const moving = Math.min(1, player.horizSpeed / 4.5);
    const hip = d.spread[0] + moving * 0.035 + (player.onGround ? 0 : 0.06);
    const ads = d.spread[1] + moving * (d.scope ? 0.02 : 0.008) + (player.onGround ? 0 : 0.04);
    let s = THREE.MathUtils.lerp(hip, ads, this.adsT) + this.bloom;
    if (player.crouched) s *= 0.75;
    return s;
  }

  // ---- per frame ----------------------------------------------------------------------
  update(dt, input, player, soldiers, game) {
    this.cooldown -= dt;
    this.bloom = Math.max(0, this.bloom - dt * 0.09);
    for (const k of ORDER) if (input.consume("Digit" + WEAPONS[k].slot)) this.switchTo(k);
    if (input.consume("WheelDown") || input.consume("Swap")) this.cycle(1);
    if (input.consume("WheelUp")) this.cycle(-1);
    if (this.switchT > 0) {
      const fast = this.def.fastSwitch || (this.pending && WEAPONS[this.pending].fastSwitch);
      const before = this.switchT;
      this.switchT += dt / (fast ? 0.22 : 0.32);
      if (before < 1 && this.switchT >= 1) this._activate(this.pending);
      if (this.switchT >= 2) {
        this.switchT = 0;
        this.pending = null;
      }
    }
    const d = this.def;
    const sprinting = player.sprinting;
    const wantAds = (input.aim || input.aimToggle) && !sprinting && !this.reloading && this.switchT === 0;
    this.adsT = THREE.MathUtils.clamp(this.adsT + (wantAds ? dt : -dt) / (d.scope ? 0.26 : 0.2), 0, 1);
    this.sprintT = THREE.MathUtils.clamp(this.sprintT + (sprinting && !this.reloading ? dt : -dt) / 0.22, 0, 1);
    if (input.consume("KeyR")) this.startReload();
    if (input.consume("KeyV") || input.consume("KeyB")) this.toggleMode();
    if (this.sgReload) this._updateShotgunReload(dt, input);
    else if (this.reloading) {
      this.reloadT += dt;
      while (this.reloadEvents.length && this.reloadT >= this.reloadEvents[0][0] * this.reloadDur) {
        this.audio.reload(this.reloadEvents.shift()[1]);
      }
      if (this.reloadT >= this.reloadDur) this._finishReload();
    }
    if (this.busy > 0) {
      this.busy -= dt;
      this.pumpT += dt;
      if (!this.pumpSound && this.pumpT > 0.06) {
        this.pumpSound = true;
        this.audio.reload("pump");
      }
      if (!this.pumpEjected && this.pumpT > 0.18) {
        this.pumpEjected = true;
        this._eject(player, 0);
      }
      if (this.busy <= 0) this.action("FP_Pump_SG").fadeOut(0.1);
    }
    const trigger = input.fire && game.playing;
    const ready = !this.reloading && this.busy <= 0 && this.switchT === 0 && this.sprintT < 0.3;
    if (trigger && ready) {
      const canFire = this.mode === "auto" || !this.triggerHeld;
      if (canFire && this.cooldown <= 0) {
        if (this.ammo > 0) this._shoot(player, soldiers, game);
        else if (!this.triggerHeld) {
          this.audio.reload("dry");
          if (this.reserve > 0) this.startReload();
        }
      }
    }
    this.triggerHeld = trigger;
    this._animate(dt, input, player);
    this.mixer.update(dt);
    if (this.head) this.head.scale.setScalar(0.0001);
  }

  _shoot(player, soldiers, game) {
    const d = this.def;
    this.ammo--;
    this.cooldown = 60 / d.rpm;
    this.shots++;
    const cam = this.engine.camera;
    const origin = cam.getWorldPosition(V3());
    const fwd = cam.getWorldDirection(V3());
    const right = V3(1, 0, 0).applyQuaternion(cam.quaternion);
    const up = V3(0, 1, 0).applyQuaternion(cam.quaternion);
    const cone = (center, s) => {
      const r = Math.sqrt(Math.random()) * s;
      const a = Math.random() * Math.PI * 2;
      return center.clone().addScaledVector(right, Math.cos(a) * r).addScaledVector(up, Math.sin(a) * r).normalize();
    };
    const aim = cone(fwd, d.pellets ? this.spread(player) * 0.3 : this.spread(player));
    const pellets = d.pellets || 1;
    const pelletSpread = d.pellets ? THREE.MathUtils.lerp(d.pelletSpread[0], d.pelletSpread[1], this.adsT) : 0;
    let hitAny = false;
    let lastEnd = null;
    for (let i = 0; i < pellets; i++) {
      const dir = pelletSpread ? cone(aim, pelletSpread) : aim;
      const wHit = this.world.raycast(origin, dir, 700);
      const sHit = soldiers.raycast(origin, dir, wHit ? wHit.dist : 700, player.team);
      let end;
      if (sHit) {
        end = sHit.point;
        hitAny = true;
        let dmg = rnd(d.dmg[sHit.part]);
        if (d.falloff) {
          const [near, far] = d.falloff;
          dmg *= THREE.MathUtils.clamp(1 - (sHit.dist - near) / (far - near), 0.15, 1);
        }
        soldiers.damage(sHit, dir, game, dmg, player);
        if (i < 3) this.fx.bloodHit(sHit.point, dir);
        if (i === 0) this.audio.impact("flesh", sHit.point);
      } else if (wHit) {
        end = wHit.point;
        this.fx.impact(wHit.point, wHit.normal, wHit.surface, pellets > 1 ? 0.5 : 1);
        if (i % 3 === 0) this.audio.impact(wHit.surface, wHit.point);
      } else end = origin.clone().addScaledVector(dir, 300);
      lastEnd = end;
      if (i % 3 === 0) soldiers.suppress(origin, dir, sHit ? sHit.dist : wHit ? wHit.dist : 300, player);
    }
    if (hitAny) this.hits++;
    this.bloom = Math.min(0.03, this.bloom + (this.adsT > 0.5 ? 0.0016 : 0.004) * (d.scope ? 3 : 1));

    // recoil: camera climbs, weapon kicks back
    const adsK = THREE.MathUtils.lerp(1, 0.55, this.adsT) * (player.crouched ? 0.8 : 1);
    const [rv, rh] = d.recoil;
    player.addRecoil(rv * (0.85 + Math.random() * 0.4) * adsK, (Math.random() - 0.45) * rh * adsK);
    const heavy = d.pellets ? 1.8 : d.scope ? 1.4 : d.slot === 4 ? 0.8 : 1;
    this.kick.impulse(V3((Math.random() - 0.5) * 0.05, 0.04 + Math.random() * 0.02, (0.9 * adsK + 0.3) * heavy));
    this.kickRot.impulse(V3(1.6 * adsK * heavy, (Math.random() - 0.5) * 0.8, (Math.random() - 0.5) * 1.2));

    // effects
    const muzzle = this.parts[this.current].muzzle;
    this.flashT = 0.045;
    this.flashMesh.visible = !this.scoped;
    this.flashMesh.rotation.z = Math.random() * Math.PI;
    this.engine.vmFlash.intensity = 3;
    this.engine.vmFlash.position.copy(muzzle.getWorldPosition(V3()));
    const muzzleWorld = this._toWorld(muzzle.getWorldPosition(V3()));
    this.fx.flash(muzzleWorld, fwd, true);
    this.audio.gunshot(d.sound, null, 1);
    if (d.tracerEvery && this.shots % d.tracerEvery === 0 && lastEnd) this.fx.tracer(muzzleWorld, lastEnd, 650);
    if (d.pellets) {
      if (this.ammo > 0) this._pump(true); // rack the next shell in (ejects the spent hull)
    } else this._eject(player, 0);
    soldiers.hearShot(origin, d.slot === 4 ? 45 : 75, player);
  }

  _eject(player, delay) {
    const ej = this.parts[this.current].eject;
    if (!ej) return;
    const cam = this.engine.camera;
    const right = V3(1, 0, 0).applyQuaternion(cam.quaternion);
    const up = V3(0, 1, 0).applyQuaternion(cam.quaternion);
    const fwd = cam.getWorldDirection(V3());
    const p = this._toWorld(ej.getWorldPosition(V3()));
    const v = right.multiplyScalar(2.2 + Math.random()).addScaledVector(up, 1.5 + Math.random()).addScaledVector(fwd, -0.4).add(player.velocity);
    this.fx.ejectShell(p, v, this.def.pellets ? "hull" : "brass");
    this.audio.casing(0.4 + delay);
  }

  // viewmodel-space point -> approximate world position (same camera pose, different FOV)
  _toWorld(p) {
    return p.clone().applyMatrix4(this.engine.camera.matrixWorld);
  }

  _animate(dt, input, player) {
    const d = this.def;
    const P = this.parts[this.current];
    const targetSway = V3(-input.lookDX * 1.6, input.lookDY * 1.6, 0);
    targetSway.clampLength(0, 0.08);
    this.sway.lerp(targetSway, Math.min(1, dt * 10));
    this.sway.multiplyScalar(Math.max(0, 1 - dt * 6));
    this.kick.update(dt);
    this.kickRot.update(dt);
    this.landDip.update(dt);
    if (player.justLanded) this.landDip.impulse(V3(0, -0.25 * Math.min(1, player.landSpeed / 6), 0));
    const speed = player.onGround ? player.horizSpeed : 0;
    this.bobT += dt * (speed > 0.3 ? 2 + speed * 1.1 : 0.8);
    const ads = ease(this.adsT);
    const bobAmt = Math.min(1, speed / 5) * THREE.MathUtils.lerp(1, 0.15, ads);
    const now = performance.now();
    const breathe = THREE.MathUtils.lerp(0.0025, 0.0008, ads);
    const pos = P.hipPos.clone().lerp(P.adsPos, ads);
    pos.x += Math.sin(this.bobT) * 0.012 * bobAmt + Math.sin(now / 1300) * breathe + this.sway.x * 0.35 * (1 - ads * 0.7);
    pos.y += -Math.abs(Math.cos(this.bobT)) * 0.012 * bobAmt + Math.sin(now / 900) * breathe
      + this.sway.y * 0.35 * (1 - ads * 0.7) + this.landDip.x.y * 0.1;
    pos.x += this.kick.x.x * 0.02;
    pos.y += this.kick.x.y * 0.03;
    pos.z += this.kick.x.z * 0.045;
    pos.y -= player.crouchT * 0.008;
    const sp = ease(this.sprintT);
    pos.add(V3(-0.07, -0.05, 0.04).multiplyScalar(sp));
    // blend the baked hip and aim poses (the arms raise the weapon to the eye)
    let ow = 0;
    if (this.oneShots) for (const n of this.oneShots) ow = Math.max(ow, this.action(n).getEffectiveWeight());
    ow = Math.min(1, ow);
    const poseAds = d.hipFromAds ? 1 : ads;
    this.holdAct.setEffectiveWeight((1 - poseAds) * (1 - ow));
    this.adsAct.setEffectiveWeight(poseAds * (1 - ow));
    // weapon switch: lower out of view, swap at the bottom, raise the new one
    const sw = this.switchT > 0 ? Math.sin((Math.min(this.switchT, 2) * Math.PI) / 2) : 0;
    pos.y -= sw * 0.28;
    this.root.position.copy(pos);
    // optional per-weapon hip angle (e.g. the pistol is turned so you can see the slide)
    const hr = d.hipRot ? d.hipRot.map((v) => v * (1 - ads)) : [0, 0, 0];
    const rx = hr[0] + this.kickRot.x.x * 0.03 + this.sway.y * 0.6 - sp * 0.42 + this.landDip.x.y * 0.2 - sw * 0.7;
    const ry = hr[1] + this.kickRot.x.y * 0.02 + this.sway.x * 0.8 + sp * 0.75;
    const rz = hr[2] + this.kickRot.x.z * 0.015 + Math.sin(this.bobT) * 0.012 * bobAmt + sp * 0.3 + player.leanT * -0.08 + sw * 0.4;
    this.root.rotation.set(rx, ry, rz, "YXZ");
    this.root.visible = !this.scoped; // looking through the scope: the HUD draws the reticle
    // scope sway from breathing; hold Shift while scoped to hold your breath
    if (d.scope) {
      const holding = input.down("ShiftLeft") && this.scoped && this.breath > 0.02;
      this.breath = THREE.MathUtils.clamp(this.breath + (holding ? -dt / 4 : dt / 6), 0, 1);
      const amp = (holding ? 0.0003 : 0.002) * (player.crouched ? 0.6 : 1) * ads;
      this.scopeSwayX = Math.sin(now / 1100) * amp + Math.sin(now / 470) * amp * 0.4;
      this.scopeSwayY = Math.sin(now / 1700) * amp * 1.2;
    } else {
      this.scopeSwayX = this.scopeSwayY = 0;
    }
    // FOV: the world zooms by the optic's magnification; the scope snaps to full zoom
    const cam = this.engine.camera;
    const baseFov = this.engine.baseFov;
    const zoomT = d.scope ? (this.scoped ? 1 : ads * 0.2) : ads;
    const fov = THREE.MathUtils.lerp(baseFov, baseFov / d.zoom, zoomT) + sp * 4;
    if (Math.abs(cam.fov - fov) > 0.01) {
      cam.fov = fov;
      cam.updateProjectionMatrix();
    }
    // aiming pulls the arms up past the camera; clip whatever comes too close to the eye
    const vfov = THREE.MathUtils.lerp(d.vfov[0], d.vfov[1], ads);
    const near = d.hipFromAds ? d.adsNear : THREE.MathUtils.lerp(0.01, d.adsNear || 0.01, ads);
    const vc = this.engine.vmCamera;
    if (Math.abs(vc.fov - vfov) > 0.01 || Math.abs(vc.near - near) > 0.001) {
      vc.fov = vfov;
      vc.near = near;
      vc.updateProjectionMatrix();
    }
    this.flashT -= dt;
    if (this.flashT <= 0) {
      this.flashMesh.visible = false;
      this.engine.vmFlash.intensity = 0;
    }
  }
}

export function styleRifleMaterials(root) {
  root.traverse((o) => {
    if (!o.isMesh || !o.material) return;
    const n = o.material.name;
    if (n === "Rifle_Glass") {
      o.material = new THREE.MeshStandardMaterial({ color: 0x1a2a30, metalness: 0.0, roughness: 0.05, transparent: true, opacity: 0.12, depthWrite: false, envMapIntensity: 0.25 });
    } else if (n === "Rifle_Reticle") {
      o.material = new THREE.MeshBasicMaterial({ color: 0xff2a12, toneMapped: false });
      o.renderOrder = 5;
    } else if (n === "Rifle_Anodized" || n === "SG_Parkerized" || n === "PST_Slide") {
      Object.assign(o.material, { metalness: 0.15, roughness: 0.78, envMapIntensity: 0.35 });
    } else if (n === "Rifle_Steel") {
      Object.assign(o.material, { metalness: 0.5, roughness: 0.55, envMapIntensity: 0.45 });
    } else if (o.material.envMapIntensity !== undefined) {
      o.material.envMapIntensity = 0.4;
    }
  });
}
