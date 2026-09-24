// Visual effects: billboard particles, bullet-hole/blood decals, tracers, shell casings, flashes.
import * as THREE from "../vendor/three-r186/three-bundle.min.js";

const tmpV = new THREE.Vector3();
const tmpQ = new THREE.Quaternion();
const tmpM = new THREE.Matrix4();
const UP = new THREE.Vector3(0, 1, 0);

// Camera-facing particle quads, all in one draw call per system.
class Particles {
  constructor(scene, texture, max, additive) {
    this.max = max;
    this.list = [];
    const g = new THREE.InstancedBufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute([-0.5, -0.5, 0, 0.5, -0.5, 0, 0.5, 0.5, 0, -0.5, 0.5, 0], 3));
    g.setAttribute("uv", new THREE.Float32BufferAttribute([0, 0, 1, 0, 1, 1, 0, 1], 2));
    g.setIndex([0, 1, 2, 0, 2, 3]);
    this.aPos = new THREE.InstancedBufferAttribute(new Float32Array(max * 3), 3);
    this.aCol = new THREE.InstancedBufferAttribute(new Float32Array(max * 4), 4);
    this.aSR = new THREE.InstancedBufferAttribute(new Float32Array(max * 2), 2);
    for (const a of [this.aPos, this.aCol, this.aSR]) a.setUsage(THREE.DynamicDrawUsage);
    g.setAttribute("iPos", this.aPos);
    g.setAttribute("iCol", this.aCol);
    g.setAttribute("iSR", this.aSR);
    g.instanceCount = 0;
    this.geometry = g;
    const mat = new THREE.ShaderMaterial({
      uniforms: { map: { value: texture }, fogColor: { value: new THREE.Color() }, fogDensity: { value: 0 } },
      vertexShader: /* glsl */ `
        attribute vec3 iPos; attribute vec4 iCol; attribute vec2 iSR;
        varying vec2 vUv; varying vec4 vCol; varying float vFog;
        void main() {
          vUv = uv; vCol = iCol;
          vec4 mv = modelViewMatrix * vec4(iPos, 1.0);
          float c = cos(iSR.y), s = sin(iSR.y);
          vec2 p = vec2(c * position.x - s * position.y, s * position.x + c * position.y) * iSR.x;
          mv.xy += p;
          vFog = -mv.z;
          gl_Position = projectionMatrix * mv;
        }`,
      fragmentShader: /* glsl */ `
        uniform sampler2D map; uniform vec3 fogColor; uniform float fogDensity;
        varying vec2 vUv; varying vec4 vCol; varying float vFog;
        void main() {
          vec4 t = texture2D(map, vUv);
          vec4 c = vec4(t.rgb * vCol.rgb, t.a * vCol.a);
          float f = 1.0 - exp(-fogDensity * fogDensity * vFog * vFog);
          c.rgb = mix(c.rgb, fogColor, f * ${additive ? "0.0" : "1.0"});
          ${additive ? "c.rgb *= c.a; c.a *= (1.0 - f);" : ""}
          if (c.a < 0.003) discard;
          gl_FragColor = c;
        }`,
      transparent: true,
      depthWrite: false,
      blending: additive ? THREE.AdditiveBlending : THREE.NormalBlending,
    });
    this.mesh = new THREE.Mesh(g, mat);
    this.mesh.frustumCulled = false;
    this.mesh.renderOrder = additive ? 11 : 10;
    scene.add(this.mesh);
    if (scene.fog) {
      mat.uniforms.fogColor.value.copy(scene.fog.color);
      mat.uniforms.fogDensity.value = scene.fog.density;
    }
  }

  spawn(p) {
    if (this.list.length >= this.max) this.list.shift();
    this.list.push({
      pos: p.pos.clone(), vel: p.vel ? p.vel.clone() : new THREE.Vector3(), life: 0, max: p.life || 1,
      size0: p.size || 0.3, size1: p.sizeEnd ?? (p.size || 0.3) * 2, rot: Math.random() * 6.28,
      spin: (Math.random() - 0.5) * (p.spin ?? 1), color: p.color || new THREE.Color(1, 1, 1),
      alpha: p.alpha ?? 1, drag: p.drag ?? 1.5, gravity: p.gravity ?? 0, fadeIn: p.fadeIn ?? 0.05,
    });
  }

  update(dt) {
    let n = 0;
    const keep = [];
    for (const q of this.list) {
      q.life += dt;
      if (q.life >= q.max) continue;
      keep.push(q);
      q.vel.multiplyScalar(Math.max(0, 1 - q.drag * dt));
      q.vel.y += q.gravity * dt;
      q.pos.addScaledVector(q.vel, dt);
      q.rot += q.spin * dt;
      const t = q.life / q.max;
      const a = q.alpha * Math.min(1, q.life / q.fadeIn) * (1 - t) * (1 - t * 0.3);
      this.aPos.setXYZ(n, q.pos.x, q.pos.y, q.pos.z);
      this.aCol.setXYZW(n, q.color.r, q.color.g, q.color.b, a);
      this.aSR.setXY(n, q.size0 + (q.size1 - q.size0) * Math.sqrt(t), q.rot);
      n++;
    }
    this.list = keep;
    this.geometry.instanceCount = n;
    this.aPos.needsUpdate = this.aCol.needsUpdate = this.aSR.needsUpdate = true;
  }
}

class DecalPool {
  constructor(scene, texture, max, size, opts = {}) {
    const g = new THREE.PlaneGeometry(1, 1);
    const mat = new THREE.MeshStandardMaterial({
      map: texture, transparent: true, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -4,
      polygonOffsetUnits: -4, roughness: 0.9, ...opts,
    });
    this.mesh = new THREE.InstancedMesh(g, mat, max);
    this.mesh.count = 0;
    this.mesh.frustumCulled = false;
    this.mesh.receiveShadow = true;
    this.mesh.renderOrder = 2;
    this.max = max;
    this.i = 0;
    this.size = size;
    scene.add(this.mesh);
  }

  add(point, normal, scale = 1) {
    tmpQ.setFromUnitVectors(new THREE.Vector3(0, 0, 1), normal);
    const spin = new THREE.Quaternion().setFromAxisAngle(normal, Math.random() * Math.PI * 2);
    tmpQ.premultiply(spin);
    const s = this.size * scale * (0.8 + Math.random() * 0.4);
    tmpM.compose(tmpV.copy(point).addScaledVector(normal, 0.004), tmpQ, new THREE.Vector3(s, s, s));
    this.mesh.setMatrixAt(this.i, tmpM);
    this.i = (this.i + 1) % this.max;
    this.mesh.count = Math.min(this.max, this.mesh.count + 1);
    this.mesh.instanceMatrix.needsUpdate = true;
  }
}

export class FX {
  constructor(engine, assets, world) {
    this.engine = engine;
    this.scene = engine.scene;
    this.world = world;
    const T = (n) => assets.tex(n, { srgb: true });
    const smoke = T("smoke.png");
    smoke.wrapS = smoke.wrapT = THREE.ClampToEdgeWrapping;
    const soft = T("soft.png");
    soft.wrapS = soft.wrapT = THREE.ClampToEdgeWrapping;
    this.smoke = new Particles(this.scene, smoke, 400, false);
    this.glow = new Particles(this.scene, soft, 300, true);
    this.mist = new Particles(this.scene, soft, 200, false);
    const hole = T("bullethole.png");
    hole.wrapS = hole.wrapT = THREE.ClampToEdgeWrapping;
    const blood = T("blood.png");
    blood.wrapS = blood.wrapT = THREE.ClampToEdgeWrapping;
    this.holes = new DecalPool(this.scene, hole, 250, 0.09);
    this.blood = new DecalPool(this.scene, blood, 60, 0.8, { color: 0x6a0a08 });
    this.flashTex = T("flash.png");
    this.flashTex.wrapS = this.flashTex.wrapT = THREE.ClampToEdgeWrapping;

    // tracers
    this.tracers = [];
    const tg = new THREE.BoxGeometry(0.018, 0.018, 1);
    tg.translate(0, 0, -0.5);
    this.tracerMat = new THREE.MeshBasicMaterial({ color: 0xffd9a0, transparent: true, opacity: 0.9, blending: THREE.AdditiveBlending, depthWrite: false });
    for (let i = 0; i < 24; i++) {
      const m = new THREE.Mesh(tg, this.tracerMat);
      m.visible = false;
      m.frustumCulled = false;
      this.scene.add(m);
      this.tracers.push({ mesh: m, active: false });
    }
    // world muzzle-flash lights (fixed count so shaders never recompile)
    this.lights = [];
    for (let i = 0; i < 3; i++) {
      const l = new THREE.PointLight(0xffa860, 0, 14, 2);
      this.scene.add(l);
      this.lights.push({ light: l, t: 0 });
    }
    // enemy muzzle flash sprites
    this.flashSprites = [];
    for (let i = 0; i < 8; i++) {
      const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: this.flashTex, blending: THREE.AdditiveBlending, depthWrite: false, transparent: true }));
      s.visible = false;
      this.scene.add(s);
      this.flashSprites.push({ s, t: 0 });
    }
    // brass
    const cg = new THREE.CylinderGeometry(0.0048, 0.0048, 0.045, 8);
    cg.rotateX(Math.PI / 2);
    this.brass = new THREE.InstancedMesh(cg, new THREE.MeshStandardMaterial({ color: 0xc8a050, metalness: 1, roughness: 0.3 }), 40);
    this.brass.count = 0;
    this.brass.frustumCulled = false;
    this.brass.castShadow = true;
    this.scene.add(this.brass);
    const hg = new THREE.CylinderGeometry(0.0105, 0.0105, 0.07, 10);
    hg.rotateX(Math.PI / 2);
    this.hulls = new THREE.InstancedMesh(hg, new THREE.MeshStandardMaterial({ color: 0x7a1010, roughness: 0.5 }), 20);
    this.hulls.count = 0;
    this.hulls.frustumCulled = false;
    this.hulls.castShadow = true;
    this.scene.add(this.hulls);
    this.shells = [];
  }

  impact(point, normal, surface, scale = 1) {
    const n = normal;
    const colors = {
      sand: [0xb89a74, 0.9], sandbag: [0xa08a68, 0.8], plaster: [0xcdbba0, 0.9], concrete: [0xa8a49c, 0.85],
      wood: [0x8a6a48, 0.7], metal: [0x888888, 0.4], rubber: [0x333333, 0.3],
    };
    const [c, a] = colors[surface] || colors.sand;
    const col = new THREE.Color(c);
    const count = Math.max(1, Math.round((surface === "metal" ? 2 : 5) * scale));
    for (let i = 0; i < count; i++) {
      const v = n.clone().multiplyScalar(1.5 + Math.random() * 2.5)
        .add(new THREE.Vector3((Math.random() - 0.5) * 1.6, Math.random() * 1.2, (Math.random() - 0.5) * 1.6));
      this.smoke.spawn({ pos: point.clone().addScaledVector(n, 0.05), vel: v, life: 0.9 + Math.random() * 1.2,
        size: 0.12, sizeEnd: 0.9 + Math.random() * 0.6, color: col, alpha: a * 0.7, drag: 3.5, gravity: -0.4 });
    }
    // debris chunks
    for (let i = 0; i < Math.round(6 * scale); i++) {
      const v = n.clone().multiplyScalar(2 + Math.random() * 3)
        .add(new THREE.Vector3((Math.random() - 0.5) * 3, Math.random() * 2, (Math.random() - 0.5) * 3));
      this.mist.spawn({ pos: point.clone(), vel: v, life: 0.5, size: 0.025, sizeEnd: 0.02, color: col.clone().multiplyScalar(0.6),
        alpha: 1, drag: 0.5, gravity: -9.8 });
    }
    if (surface === "metal") {
      for (let i = 0; i < 8; i++) {
        const v = n.clone().multiplyScalar(3 + Math.random() * 4)
          .add(new THREE.Vector3((Math.random() - 0.5) * 5, Math.random() * 4, (Math.random() - 0.5) * 5));
        this.glow.spawn({ pos: point.clone(), vel: v, life: 0.15 + Math.random() * 0.25, size: 0.04, sizeEnd: 0.01,
          color: new THREE.Color(1.0, 0.7, 0.3), alpha: 1, drag: 1, gravity: -9.8 });
      }
    }
    if (surface !== "sand") this.holes.add(point, n, surface === "wood" ? 0.8 : 1);
  }

  bloodHit(point, dir) {
    for (let i = 0; i < 8; i++) {
      const v = dir.clone().multiplyScalar(1 + Math.random() * 2)
        .add(new THREE.Vector3((Math.random() - 0.5) * 1.5, Math.random() * 1.0, (Math.random() - 0.5) * 1.5));
      this.mist.spawn({ pos: point.clone(), vel: v, life: 0.35 + Math.random() * 0.4, size: 0.08, sizeEnd: 0.5,
        color: new THREE.Color(0.35, 0.02, 0.02), alpha: 0.75, drag: 3, gravity: -2.5 });
    }
    for (let i = 0; i < 6; i++) {
      const v = dir.clone().multiplyScalar(2 + Math.random() * 3)
        .add(new THREE.Vector3((Math.random() - 0.5) * 2, Math.random() * 1.5, (Math.random() - 0.5) * 2));
      this.mist.spawn({ pos: point.clone(), vel: v, life: 0.6, size: 0.02, sizeEnd: 0.015,
        color: new THREE.Color(0.3, 0.01, 0.01), alpha: 1, drag: 0.3, gravity: -9.8 });
    }
    // splatter on the surface behind the target, or on the ground
    const hit = this.world.raycast(point, dir, 2.5);
    if (hit) this.blood.add(hit.point, hit.normal, 0.6 + Math.random() * 0.5);
    else {
      const g = this.world.raycast(point, new THREE.Vector3(dir.x * 0.3, -1, dir.z * 0.3).normalize(), 3);
      if (g) this.blood.add(g.point, g.normal, 0.7);
    }
  }

  tracer(from, to, speed = 700) {
    const t = this.tracers.find((x) => !x.active);
    if (!t) return;
    t.active = true;
    t.from = from.clone();
    t.dir = to.clone().sub(from);
    t.len = t.dir.length();
    t.dir.normalize();
    t.d = 0;
    t.speed = speed;
    t.mesh.visible = true;
    t.mesh.lookAt(tmpV.copy(from).sub(t.dir));
    t.mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, -1), t.dir);
  }

  flash(pos, dir, big = false) {
    const l = this.lights.reduce((a, b) => (a.t < b.t ? a : b));
    l.light.position.copy(pos);
    l.light.intensity = big ? 22 : 14;
    l.t = 0.05;
    if (!big) {
      const s = this.flashSprites.find((x) => x.t <= 0) || this.flashSprites[0];
      s.s.position.copy(pos);
      s.s.scale.setScalar(0.45 + Math.random() * 0.25);
      s.s.material.rotation = Math.random() * 6.28;
      s.s.visible = true;
      s.t = 0.04;
    }
    // muzzle smoke
    for (let i = 0; i < 2; i++) {
      this.smoke.spawn({ pos: pos.clone(), vel: dir.clone().multiplyScalar(1.2 + Math.random()).add(new THREE.Vector3(0, 0.3, 0)),
        life: 1.0 + Math.random(), size: 0.08, sizeEnd: 0.7, color: new THREE.Color(0.8, 0.78, 0.74), alpha: 0.18, drag: 2 });
    }
  }

  ejectShell(pos, vel, kind = "brass") {
    if (this.shells.length >= 50) this.shells.shift();
    this.shells.push({ kind, pos: pos.clone(), vel: vel.clone(), rot: new THREE.Euler(Math.random() * 6, Math.random() * 6, 0),
      spin: new THREE.Vector3(20 * Math.random(), 30, 10), life: 0, rest: false });
  }

  update(dt) {
    this.smoke.update(dt);
    this.glow.update(dt);
    this.mist.update(dt);
    for (const t of this.tracers) {
      if (!t.active) continue;
      t.d += t.speed * dt;
      const seg = Math.min(4, t.len * 0.5);
      if (t.d - seg > t.len) {
        t.active = false;
        t.mesh.visible = false;
        continue;
      }
      const head = Math.min(t.d, t.len);
      const tail = Math.max(0, t.d - seg);
      t.mesh.position.copy(t.from).addScaledVector(t.dir, head);
      t.mesh.scale.set(1, 1, Math.max(0.01, head - tail));
    }
    for (const l of this.lights) {
      l.t -= dt;
      if (l.t <= 0) l.light.intensity = 0;
    }
    for (const s of this.flashSprites) {
      s.t -= dt;
      if (s.t <= 0) s.s.visible = false;
    }
    let i = 0;
    let h = 0;
    const keep = [];
    for (const sh of this.shells) {
      sh.life += dt;
      if (sh.life > 6) continue;
      keep.push(sh);
      if (!sh.rest) {
        sh.vel.y -= 9.8 * dt;
        sh.pos.addScaledVector(sh.vel, dt);
        sh.rot.x += sh.spin.x * dt;
        sh.rot.y += sh.spin.y * dt;
        const g = this.world.groundAt(sh.pos.x, sh.pos.z, 0.01, sh.pos.y + 0.05);
        if (sh.pos.y < g + 0.005) {
          sh.pos.y = g + 0.005;
          if (Math.abs(sh.vel.y) < 0.8) {
            sh.rest = true;
            sh.rot.x = 0;
            sh.rot.z = 0;
          }
          sh.vel.y *= -0.35;
          sh.vel.x *= 0.5;
          sh.vel.z *= 0.5;
          sh.spin.multiplyScalar(0.5);
        }
      }
      tmpM.compose(sh.pos, tmpQ.setFromEuler(sh.rot), tmpV.set(1, 1, 1));
      if (sh.kind === "hull" && h < 20) this.hulls.setMatrixAt(h++, tmpM);
      else if (i < 40) this.brass.setMatrixAt(i++, tmpM);
    }
    this.shells = keep;
    this.brass.count = i;
    this.brass.instanceMatrix.needsUpdate = true;
    this.hulls.count = h;
    this.hulls.instanceMatrix.needsUpdate = true;
  }
}
