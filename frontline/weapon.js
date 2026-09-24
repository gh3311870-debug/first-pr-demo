// First-person M4 carbine: Blender-rigged arms + rifle, ADS, recoil, reload and ballistics.
import * as THREE from "../vendor/three-r186/three-bundle.min.js";

const RPM = 780;
const MAG = 30;
const V3 = (x = 0, y = 0, z = 0) => new THREE.Vector3(x, y, z);

// critically damped spring for procedural weapon motion
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

export class Weapon {
  constructor(engine, assets, fx, audio, world) {
    this.engine = engine;
    this.fx = fx;
    this.audio = audio;
    this.world = world;
    this.ammo = MAG;
    this.reserve = MAG * 6;
    this.mode = "auto";
    this.cooldown = 0;
    this.reloading = false;
    this.adsT = 0;
    this.bloom = 0;
    this.shots = 0;
    this.hits = 0;
    this.triggerHeld = false;
    this.kick = new Spring(260, 26); // position
    this.kickRot = new Spring(220, 22); // rotation (x = pitch, y = yaw, z = roll)
    this.sway = V3();
    this.bobT = 0;
    this.sprintT = 0;
    this.landDip = new Spring(90, 14);
    this._buildViewmodel(assets);
  }

  _buildViewmodel(assets) {
    const rig = THREE.SkeletonUtils.clone(assets.operator.scene);
    this.rig = rig;
    rig.traverse((o) => {
      if (o.isMesh) {
        o.frustumCulled = false;
        o.castShadow = false;
        o.receiveShadow = false;
        if (o.name.includes("visor")) o.visible = false;
        if (o.material && o.material.name === "VanguardBodyMat") {
          o.material = o.material.clone();
          o.material.color.set(0x4a473e); // darker, desaturated sleeves/gloves
          o.material.roughness = 1;
          o.material.envMapIntensity = 0.5;
        }
      }
    });
    styleRifleMaterials(rig);
    this.root = new THREE.Group();
    this.root.add(rig);
    this.engine.vmScene.add(this.root);
    const anims = assets.operator.animations;
    this.mixer = new THREE.AnimationMixer(rig);
    const clip = (n) => anims.find((a) => a.name === n);
    this.hold = this.mixer.clipAction(clip("FP_Hold"));
    this.hold.play();
    this.reloadAction = this.mixer.clipAction(clip("FP_Reload"));
    this.reloadAction.setLoop(THREE.LoopOnce, 1);
    this.reloadAction.clampWhenFinished = true;
    this.reloadDur = this.reloadAction.getClip().duration / 1.1;
    this.reloadAction.timeScale = 1.1;
    this.head = rig.getObjectByName("mixamorigHead") || rig.getObjectByName("mixamorig:Head");
    this.eye = rig.getObjectByName("Eye");
    this.sight = rig.getObjectByName("SightAxis");
    this.muzzle = rig.getObjectByName("Muzzle");
    this.ejectPt = rig.getObjectByName("Eject");
    this.reticle = rig.getObjectByName("Reticle");
    this.mixer.update(0);
    rig.updateMatrixWorld(true);
    const e = this.eye.getWorldPosition(V3());
    const s = this.sight.getWorldPosition(V3());
    rig.position.copy(e).negate();
    // hip: a touch lower and further right than the Blender pose; ADS: optic on the eye axis
    this.hipPos = V3(0.02, -0.02, -0.05);
    const rel = s.clone().sub(e);
    this.adsPos = V3(-rel.x, -rel.y, -0.24 - rel.z);
    if (this.reticle) this.reticle.scale.setScalar(1.6);
    // muzzle flash sprite + light live in the viewmodel scene
    const fm = new THREE.MeshBasicMaterial({ map: this.fx.flashTex, blending: THREE.AdditiveBlending, depthWrite: false, transparent: true, toneMapped: false });
    this.flashMesh = new THREE.Group();
    for (let i = 0; i < 2; i++) {
      const p = new THREE.Mesh(new THREE.PlaneGeometry(0.22, 0.22), fm);
      if (i === 1) p.rotation.y = Math.PI / 2;
      p.position.z = -0.08;
      this.flashMesh.add(p);
    }
    const front = new THREE.Mesh(new THREE.PlaneGeometry(0.16, 0.16), fm);
    this.flashMesh.add(front);
    this.flashMesh.visible = false;
    this.muzzle.add(this.flashMesh);
    this.flashT = 0;
  }

  get aiming() {
    return this.adsT > 0.6;
  }

  get magCap() {
    return MAG;
  }

  startReload() {
    if (this.reloading || this.ammo >= MAG + (this.ammo > 0 ? 1 : 0) || this.reserve <= 0) return;
    this.reloading = true;
    this.reloadT = 0;
    this.reloadEvents = [[0.18, "out"], [0.62, "in"], [0.7, "slap"]];
    this.reloadAction.reset();
    this.reloadAction.setEffectiveWeight(1);
    this.reloadAction.fadeIn(0.12);
    this.reloadAction.play();
  }

  _finishReload() {
    // tactical reload keeps the round in the chamber (30 + 1)
    const cap = this.ammo > 0 ? MAG + 1 : MAG;
    const need = cap - this.ammo;
    const take = Math.min(need, this.reserve);
    this.ammo += take;
    this.reserve -= take;
    this.reloading = false;
    this.reloadAction.fadeOut(0.2);
  }

  toggleMode() {
    this.mode = this.mode === "auto" ? "semi" : "auto";
    this.audio.reload("switch");
  }

  // Returns spread cone half-angle in radians.
  spread(player) {
    const moving = Math.min(1, player.horizSpeed / 4.5);
    const hip = 0.03 + moving * 0.035 + (player.onGround ? 0 : 0.06);
    const ads = 0.0022 + moving * 0.008 + (player.onGround ? 0 : 0.04);
    let s = THREE.MathUtils.lerp(hip, ads, this.adsT) + this.bloom;
    if (player.crouched) s *= 0.75;
    return s;
  }

  update(dt, input, player, enemies, game) {
    this.cooldown -= dt;
    this.bloom = Math.max(0, this.bloom - dt * 0.09);
    const sprinting = player.sprinting;
    // --- ADS ---
    const wantAds = (input.aim || input.aimToggle) && !sprinting && !this.reloading;
    this.adsT = THREE.MathUtils.clamp(this.adsT + (wantAds ? dt : -dt) / 0.2, 0, 1);
    this.sprintT = THREE.MathUtils.clamp(this.sprintT + (sprinting && !this.reloading ? dt : -dt) / 0.22, 0, 1);
    // --- reload ---
    if (input.consume("KeyR")) this.startReload();
    if (input.consume("KeyV") || input.consume("KeyB")) this.toggleMode();
    if (this.reloading) {
      this.reloadT += dt;
      while (this.reloadEvents.length && this.reloadT >= this.reloadEvents[0][0] * this.reloadDur) {
        this.audio.reload(this.reloadEvents.shift()[1]);
      }
      if (this.reloadT >= this.reloadDur) this._finishReload();
    }
    // --- firing ---
    const trigger = input.fire && game.playing;
    if (trigger && !this.reloading && this.sprintT < 0.3) {
      const canAuto = this.mode === "auto" || !this.triggerHeld;
      if (canAuto && this.cooldown <= 0) {
        if (this.ammo > 0) {
          this._shoot(player, enemies, game);
        } else if (!this.triggerHeld) {
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

  _shoot(player, enemies, game) {
    this.ammo--;
    this.cooldown = 60 / RPM;
    this.shots++;
    const cam = this.engine.camera;
    const origin = cam.getWorldPosition(V3());
    const fwd = cam.getWorldDirection(V3());
    // random direction within the spread cone
    const s = this.spread(player);
    const r = Math.sqrt(Math.random()) * s;
    const a = Math.random() * Math.PI * 2;
    const right = V3(1, 0, 0).applyQuaternion(cam.quaternion);
    const up = V3(0, 1, 0).applyQuaternion(cam.quaternion);
    const dir = fwd.clone().addScaledVector(right, Math.cos(a) * r).addScaledVector(up, Math.sin(a) * r).normalize();
    this.bloom = Math.min(0.03, this.bloom + (this.adsT > 0.5 ? 0.0016 : 0.004));

    const wHit = this.world.raycast(origin, dir, 600);
    const eHit = enemies.raycast(origin, dir, wHit ? wHit.dist : 600);
    let end;
    if (eHit) {
      end = eHit.point;
      this.hits++;
      enemies.damage(eHit, dir, game);
      this.fx.bloodHit(eHit.point, dir);
      this.audio.impact("flesh", eHit.point);
    } else if (wHit) {
      end = wHit.point;
      this.fx.impact(wHit.point, wHit.normal, wHit.surface);
      this.audio.impact(wHit.surface, wHit.point);
    } else {
      end = origin.clone().addScaledVector(dir, 300);
    }

    // recoil: camera climbs, weapon kicks back
    const adsK = THREE.MathUtils.lerp(1, 0.55, this.adsT) * (player.crouched ? 0.8 : 1);
    player.addRecoil((0.011 + Math.random() * 0.006) * adsK, (Math.random() - 0.45) * 0.006 * adsK);
    this.kick.impulse(V3((Math.random() - 0.5) * 0.05, 0.04 + Math.random() * 0.02, 0.9 * adsK + 0.3));
    this.kickRot.impulse(V3(1.6 * adsK, (Math.random() - 0.5) * 0.8, (Math.random() - 0.5) * 1.2));

    // effects
    this.flashT = 0.045;
    this.flashMesh.visible = true;
    this.flashMesh.rotation.z = Math.random() * Math.PI;
    this.flashMesh.scale.setScalar(0.8 + Math.random() * 0.5);
    this.engine.vmFlash.intensity = 3;
    this.engine.vmFlash.position.copy(this.muzzle.getWorldPosition(V3()));
    const muzzleWorld = this._toWorld(this.muzzle.getWorldPosition(V3()));
    this.fx.flash(muzzleWorld, fwd, true);
    this.audio.gunshot(null, 1);
    if (this.shots % 3 === 0) this.fx.tracer(muzzleWorld, end, 650);
    const ej = this._toWorld(this.ejectPt.getWorldPosition(V3()));
    const ejVel = right.clone().multiplyScalar(2.2 + Math.random()).addScaledVector(up, 1.5 + Math.random()).addScaledVector(fwd, -0.4)
      .add(player.velocity);
    this.fx.ejectShell(ej, ejVel);
    enemies.hearShot(origin, 70);
    enemies.suppress(origin, dir, eHit ? eHit.dist : wHit ? wHit.dist : 300, player);
  }

  // viewmodel-space point -> approximate world position (same camera pose, different FOV)
  _toWorld(p) {
    return p.clone().applyMatrix4(this.engine.camera.matrixWorld);
  }

  _animate(dt, input, player) {
    // sway lags behind mouse movement
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
    const ads = this.adsT;
    const bobAmt = Math.min(1, speed / 5) * THREE.MathUtils.lerp(1, 0.15, ads);
    const breathe = THREE.MathUtils.lerp(0.0025, 0.0008, ads);
    const bob = V3(
      Math.sin(this.bobT) * 0.012 * bobAmt + Math.sin(performance.now() / 1300) * breathe,
      -Math.abs(Math.cos(this.bobT)) * 0.012 * bobAmt + Math.sin(performance.now() / 900) * breathe,
      0,
    );
    const pos = this.hipPos.clone().lerp(this.adsPos, easeInOut(ads));
    pos.add(bob);
    pos.x += this.sway.x * 0.35 * (1 - ads * 0.7);
    pos.y += this.sway.y * 0.35 * (1 - ads * 0.7) + this.landDip.x.y * 0.1;
    // recoil kick (z backwards)
    pos.x += this.kick.x.x * 0.02;
    pos.y += this.kick.x.y * 0.03;
    pos.z += this.kick.x.z * 0.045;
    // crouch / stance feel
    pos.y -= player.crouchT * 0.008;
    // sprint: rifle swung down and across the chest
    const sp = easeInOut(this.sprintT);
    pos.add(V3(-0.07, -0.05, 0.04).multiplyScalar(sp));
    this.root.position.copy(pos);
    const rx = this.kickRot.x.x * 0.03 + this.sway.y * 0.6 - sp * 0.42 + this.landDip.x.y * 0.2;
    const ry = this.kickRot.x.y * 0.02 + this.sway.x * 0.8 + sp * 0.75;
    const rz = this.kickRot.x.z * 0.015 + Math.sin(this.bobT) * 0.012 * bobAmt + sp * 0.3 + player.leanT * -0.08;
    this.root.rotation.set(rx, ry, rz, "YXZ");
    // FOV: world zooms slightly when aiming; weapon FOV narrows so the optic fills more view
    const cam = this.engine.camera;
    const baseFov = this.engine.baseFov;
    const fov = THREE.MathUtils.lerp(baseFov, baseFov / 1.35, easeInOut(ads)) + sp * 4;
    if (Math.abs(cam.fov - fov) > 0.01) {
      cam.fov = fov;
      cam.updateProjectionMatrix();
    }
    const vfov = THREE.MathUtils.lerp(54, 40, easeInOut(ads));
    const vc = this.engine.vmCamera;
    if (Math.abs(vc.fov - vfov) > 0.01) {
      vc.fov = vfov;
      vc.updateProjectionMatrix();
    }
    // muzzle flash timer
    this.flashT -= dt;
    if (this.flashT <= 0) {
      this.flashMesh.visible = false;
      this.engine.vmFlash.intensity = 0;
    }
  }
}

function easeInOut(t) {
  return t * t * (3 - 2 * t);
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
    } else if (n === "Rifle_Anodized") {
      Object.assign(o.material, { metalness: 0.15, roughness: 0.78, envMapIntensity: 0.35 });
    } else if (n === "Rifle_Steel") {
      Object.assign(o.material, { metalness: 0.5, roughness: 0.55, envMapIntensity: 0.45 });
    } else if (n.startsWith("Rifle_")) {
      o.material.envMapIntensity = 0.4;
    }
  });
}
