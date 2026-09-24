// Player movement (walk/sprint/crouch/jump/lean), camera, health.
import * as THREE from "../vendor/three-r186/three-bundle.min.js";

const STAND_H = 1.78;
const CROUCH_H = 1.2;
const STAND_EYE = 1.64;
const CROUCH_EYE = 1.08;
const RADIUS = 0.33;

export class Player {
  constructor(engine, world, audio) {
    this.engine = engine;
    this.world = world;
    this.audio = audio;
    this.pos = new THREE.Vector3();
    this.velocity = new THREE.Vector3();
    this.yaw = 0;
    this.pitch = 0;
    this.recoilPitch = 0;
    this.recoilYaw = 0;
    this.punch = new THREE.Vector3();
    this.health = 100;
    this.onGround = true;
    this.crouched = false;
    this.crouchT = 0;
    this.leanT = 0;
    this.sprinting = false;
    this.stepDist = 0;
    this.lastHurt = -99;
    this.time = 0;
    this.dead = false;
  }

  spawn(x, z, yaw) {
    this.pos.set(x, 0, z);
    this.velocity.set(0, 0, 0);
    this.yaw = yaw;
    this.pitch = 0;
    this.health = 100;
    this.dead = false;
    this.crouched = false;
  }

  get horizSpeed() {
    return Math.hypot(this.velocity.x, this.velocity.z);
  }

  get eyePos() {
    return new THREE.Vector3(this.pos.x, this.pos.y + THREE.MathUtils.lerp(STAND_EYE, CROUCH_EYE, this.crouchT), this.pos.z);
  }

  // points enemies aim at / test for hits
  get chest() {
    return new THREE.Vector3(this.pos.x, this.pos.y + THREE.MathUtils.lerp(1.3, 0.85, this.crouchT), this.pos.z);
  }

  get height() {
    return THREE.MathUtils.lerp(STAND_H, CROUCH_H, this.crouchT);
  }

  addRecoil(pitch, yaw) {
    this.recoilPitch += pitch;
    this.recoilYaw += yaw;
    this.pitch += pitch;
    this.yaw -= yaw;
  }

  update(dt, input, weapon) {
    this.time += dt;
    this.justLanded = false;
    if (this.dead) return;
    // --- look ---
    const adsSlow = weapon ? THREE.MathUtils.lerp(1, 0.62, weapon.adsT) : 1;
    this.yaw -= input.lookDX * adsSlow;
    this.pitch -= input.lookDY * adsSlow;
    // recoil recovery: return most of the climb unless the player pulled down already
    const rec = Math.min(1, dt * 7);
    const back = this.recoilPitch * rec * 0.75;
    this.pitch -= back;
    this.recoilPitch -= this.recoilPitch * rec;
    this.pitch = THREE.MathUtils.clamp(this.pitch, -1.45, 1.45);

    // --- stance ---
    if (input.consume("KeyC") || input.consume("ControlLeft")) this.crouched = !this.crouched;
    if (this.crouched === false && this.crouchT > 0) {
      // make sure there's headroom to stand up
      const hit = this.world.raycast(this.eyePos, new THREE.Vector3(0, 1, 0), STAND_H - CROUCH_H + 0.1);
      if (hit && hit.box) this.crouched = true;
    }
    this.crouchT = THREE.MathUtils.clamp(this.crouchT + (this.crouched ? dt : -dt) / 0.18, 0, 1);

    const ax = input.axis();
    const wantSprint = (input.down("ShiftLeft") || input.touchSprint) && ax.y > 0.5 && !this.crouched && !(weapon && weapon.adsT > 0.3);
    this.sprinting = wantSprint && this.onGround;
    let speed = this.sprinting ? 6.4 : 4.0;
    if (this.crouched) speed = 1.9;
    if (weapon && weapon.adsT > 0) speed *= THREE.MathUtils.lerp(1, 0.6, weapon.adsT);
    if (weapon && weapon.reloading) speed *= 0.85;

    // --- lean (Q / E) ---
    let lean = 0;
    if (input.down("KeyQ")) lean -= 1;
    if (input.down("KeyE")) lean += 1;
    this.leanT += (lean - this.leanT) * Math.min(1, dt * 10);

    // --- move ---
    const sin = Math.sin(this.yaw);
    const cos = Math.cos(this.yaw);
    const wishX = (ax.x * cos - ax.y * sin) * speed;
    const wishZ = (-ax.x * sin - ax.y * cos) * speed;
    const accel = this.onGround ? 11 : 1.5;
    this.velocity.x += (wishX - this.velocity.x) * Math.min(1, accel * dt);
    this.velocity.z += (wishZ - this.velocity.z) * Math.min(1, accel * dt);
    if (this.onGround && input.consume("Space")) {
      if (this.crouched) this.crouched = false;
      else {
        this.velocity.y = 4.1;
        this.onGround = false;
      }
    }
    input.consume("Space");
    this.velocity.y -= 12 * dt;
    const vyBefore = this.velocity.y;
    const res = this.world.moveCylinder(this.pos, this.velocity, dt, RADIUS, this.height);
    if (res.onGround && !this.onGround && vyBefore < -2) {
      this.justLanded = true;
      this.landSpeed = -vyBefore;
      this.audio.footstep(null, 0.5);
    }
    this.onGround = res.onGround;

    // footsteps
    if (this.onGround) {
      this.stepDist += this.horizSpeed * dt;
      const stride = this.sprinting ? 1.9 : this.crouched ? 1.1 : 1.6;
      if (this.stepDist > stride) {
        this.stepDist = 0;
        this.audio.footstep(null, this.crouched ? 0.1 : this.sprinting ? 0.38 : 0.24);
      }
    }

    // regenerate after a few seconds without taking damage
    if (this.time - this.lastHurt > 5 && this.health < 100) this.health = Math.min(100, this.health + 12 * dt);

    this._updateCamera(dt);
  }

  _updateCamera(dt) {
    const cam = this.engine.camera;
    const eye = this.eyePos;
    // head bob is subtle; most motion is carried by the weapon
    const bobA = this.onGround ? Math.min(1, this.horizSpeed / 6) : 0;
    const t = this.time * (this.sprinting ? 12.5 : 9.5);
    eye.y += Math.abs(Math.sin(t)) * 0.035 * bobA - 0.017 * bobA;
    // lean: shift the eye sideways unless a wall is in the way
    if (Math.abs(this.leanT) > 0.01) {
      const side = new THREE.Vector3(Math.cos(this.yaw), 0, -Math.sin(this.yaw));
      const want = 0.38 * this.leanT;
      const hit = this.world.raycast(eye, side.clone().multiplyScalar(Math.sign(want)), Math.abs(want) + 0.2);
      const allowed = hit ? Math.max(0, hit.dist - 0.2) * Math.sign(want) : want;
      eye.addScaledVector(side, allowed);
      eye.y -= Math.abs(this.leanT) * 0.06;
    }
    this.punch.multiplyScalar(Math.max(0, 1 - dt * 8));
    cam.position.copy(eye);
    cam.rotation.set(this.pitch + this.punch.x, this.yaw + this.punch.y, -this.leanT * 0.2 + this.punch.z + Math.sin(t * 0.5) * 0.004 * bobA);
    cam.updateMatrixWorld();
    this.engine.vmCamera.position.set(0, 0, 0);
  }

  takeDamage(amount, from, game) {
    if (this.dead) return;
    this.health -= amount;
    this.lastHurt = this.time;
    // flinch: the camera jerks away from the hit
    this.punch.set((Math.random() - 0.3) * 0.06, (Math.random() - 0.5) * 0.08, (Math.random() - 0.5) * 0.06);
    this.audio.hurt();
    game.hud.damageFrom(from, this);
    if (this.health <= 0) {
      this.health = 0;
      this.dead = true;
      game.onPlayerDeath();
    }
  }
}
