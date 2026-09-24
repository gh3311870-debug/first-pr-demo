// Renderer, cameras, sky/sun lighting, shadows and post-processing.
import * as THREE from "../vendor/three-r186/three-bundle.min.js";

export const QUALITY = {
  low: { pixelRatio: 1.0, shadow: 1024, shadowRange: 28, post: false, ao: false, bloom: false, shrubs: 0.35, antialias: true },
  medium: { pixelRatio: 1.5, shadow: 2048, shadowRange: 36, post: true, ao: false, bloom: true, shrubs: 0.7, antialias: false },
  high: { pixelRatio: 2.0, shadow: 4096, shadowRange: 48, post: true, ao: true, bloom: true, shrubs: 1.0, antialias: false },
};

export function defaultQuality() {
  const touch = matchMedia("(pointer: coarse)").matches || "ontouchstart" in window;
  if (touch) return "low";
  return (navigator.hardwareConcurrency || 4) >= 8 ? "high" : "medium";
}

// Late-afternoon sun, low enough for long shadows.
export const SUN_ELEVATION = 26;
export const SUN_AZIMUTH = 215;

export class Engine {
  constructor(container, qualityName) {
    this.quality = QUALITY[qualityName] || QUALITY.medium;
    this.qualityName = qualityName;
    const q = this.quality;
    this.renderer = new THREE.WebGLRenderer({ antialias: q.antialias, powerPreference: "high-performance" });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, q.pixelRatio));
    this.renderer.setSize(window.innerWidth, window.innerHeight);
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 0.74;
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFShadowMap;
    this.renderer.autoClear = false;
    container.appendChild(this.renderer.domElement);

    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(72, window.innerWidth / window.innerHeight, 0.05, 2500);
    this.camera.rotation.order = "YXZ";
    this.baseFov = 72;

    // Separate scene for the first-person weapon so it never clips into walls.
    this.vmScene = new THREE.Scene();
    this.vmCamera = new THREE.PerspectiveCamera(54, window.innerWidth / window.innerHeight, 0.01, 10);

    this._setupSky();
    this._setupLights();
    this._setupPost();
    window.addEventListener("resize", () => this.resize());
  }

  _setupSky() {
    const sky = new THREE.Sky();
    sky.scale.setScalar(4000);
    const u = sky.material.uniforms;
    u.turbidity.value = 7.5;
    u.rayleigh.value = 1.6;
    u.mieCoefficient.value = 0.006;
    u.mieDirectionalG.value = 0.86;
    const phi = THREE.MathUtils.degToRad(90 - SUN_ELEVATION);
    const theta = THREE.MathUtils.degToRad(SUN_AZIMUTH);
    this.sunDir = new THREE.Vector3().setFromSphericalCoords(1, phi, theta);
    u.sunPosition.value.copy(this.sunDir);
    this.sky = sky;
    this.scene.add(sky);

    // Image-based lighting generated from the same sky so reflections match.
    const pmrem = new THREE.PMREMGenerator(this.renderer);
    const envScene = new THREE.Scene();
    const envSky = new THREE.Sky();
    envSky.scale.setScalar(100);
    Object.assign(envSky.material.uniforms.turbidity, { value: u.turbidity.value });
    envSky.material.uniforms.rayleigh.value = u.rayleigh.value;
    envSky.material.uniforms.mieCoefficient.value = u.mieCoefficient.value;
    envSky.material.uniforms.mieDirectionalG.value = 0.7;
    envSky.material.uniforms.sunPosition.value.copy(this.sunDir);
    envScene.add(envSky);
    // warm sand "ground" in the environment so bounce light is sandy, not black
    const ground = new THREE.Mesh(new THREE.CircleGeometry(90, 32), new THREE.MeshBasicMaterial({ color: 0x9a7b58 }));
    ground.rotation.x = -Math.PI / 2;
    ground.position.y = -2;
    envScene.add(ground);
    this.envMap = pmrem.fromScene(envScene, 0.02).texture;
    this.scene.environment = this.envMap;
    this.scene.environmentIntensity = 0.32;
    this.vmScene.environment = this.envMap;
    this.vmScene.environmentIntensity = 0.28;
    pmrem.dispose();

    // Dusty haze that fades distant terrain into the horizon.
    this.fogColor = new THREE.Color(0xbfb4a0);
    this.scene.fog = new THREE.FogExp2(this.fogColor, 0.0026);
  }

  _setupLights() {
    const q = this.quality;
    const sun = new THREE.DirectionalLight(0xffdcb4, 2.6);
    sun.castShadow = true;
    sun.shadow.mapSize.set(q.shadow, q.shadow);
    const r = q.shadowRange;
    Object.assign(sun.shadow.camera, { left: -r, right: r, top: r, bottom: -r, near: 1, far: 400 });
    sun.shadow.bias = -0.0004;
    sun.shadow.normalBias = 0.035;
    sun.shadow.radius = 2;
    this.scene.add(sun, sun.target);
    this.sun = sun;
    const hemi = new THREE.HemisphereLight(0xb9c6d6, 0x9a7650, 0.55);
    this.scene.add(hemi);

    // viewmodel lights mirror the world lights (no shadows)
    const vmSun = new THREE.DirectionalLight(0xffdcb4, 2.0);
    this.vmScene.add(vmSun, vmSun.target);
    this.vmSun = vmSun;
    this.vmScene.add(new THREE.HemisphereLight(0xb9c6d6, 0x9a7650, 0.55));
    // muzzle flash light for the viewmodel
    this.vmFlash = new THREE.PointLight(0xffb060, 0, 3, 2);
    this.vmScene.add(this.vmFlash);
  }

  _setupPost() {
    const q = this.quality;
    this.composer = null;
    if (!q.post) return;
    const size = this.renderer.getDrawingBufferSize(new THREE.Vector2());
    const rt = new THREE.WebGLRenderTarget(size.x, size.y, { type: THREE.HalfFloatType, samples: 0 });
    const composer = new THREE.EffectComposer(this.renderer, rt);
    const main = new THREE.RenderPass(this.scene, this.camera);
    composer.addPass(main);
    if (q.ao) {
      const ao = new THREE.GTAOPass(this.scene, this.camera, size.x, size.y);
      ao.output = THREE.GTAOPass.OUTPUT.Default;
      ao.blendIntensity = 0.85;
      ao.updateGtaoMaterial({ radius: 0.6, distanceExponent: 1.5, thickness: 1.5, scale: 1.0, samples: 12 });
      ao.updatePdMaterial({ lumaPhi: 10, depthPhi: 2, normalPhi: 3, radius: 6, rings: 2, samples: 12 });
      composer.addPass(ao);
      this.aoPass = ao;
    }
    const vm = new THREE.RenderPass(this.vmScene, this.vmCamera);
    vm.clear = false;
    vm.clearDepth = true;
    composer.addPass(vm);
    this.gradePass = new THREE.ShaderPass(GradeShader);
    composer.addPass(this.gradePass);
    composer.addPass(new THREE.OutputPass());
    composer.addPass(new THREE.SMAAPass());
    this.composer = composer;
  }

  followShadow(center) {
    // keep the shadow frustum around the player, snapped to texels to avoid shimmering
    const sun = this.sun;
    const r = this.quality.shadowRange;
    const texel = (2 * r) / this.quality.shadow;
    const lightDir = this.sunDir;
    const m = new THREE.Matrix4().lookAt(new THREE.Vector3(), lightDir.clone().negate(), new THREE.Vector3(0, 1, 0));
    const inv = m.clone().invert();
    const c = center.clone().applyMatrix4(inv);
    c.x = Math.round(c.x / texel) * texel;
    c.y = Math.round(c.y / texel) * texel;
    c.applyMatrix4(m);
    sun.target.position.copy(c);
    sun.position.copy(c).addScaledVector(lightDir, 180);
    sun.target.updateMatrixWorld();
  }

  resize() {
    const w = window.innerWidth;
    const h = window.innerHeight;
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.vmCamera.aspect = w / h;
    this.vmCamera.updateProjectionMatrix();
    this.renderer.setSize(w, h);
    if (this.composer) {
      this.composer.setSize(w, h);
    }
  }

  render(grade) {
    // keep viewmodel lighting aligned with the world sun, in camera space
    const invCam = this.camera.quaternion.clone().invert();
    this.vmSun.position.copy(this.sunDir).applyQuaternion(invCam).multiplyScalar(10);
    if (this.composer) {
      const u = this.gradePass.uniforms;
      u.vignette.value = grade.vignette;
      u.damage.value = grade.damage;
      u.desat.value = grade.desat;
      u.time.value = performance.now() / 1000;
      this.composer.render();
    } else {
      const r = this.renderer;
      r.clear();
      r.render(this.scene, this.camera);
      r.clearDepth();
      r.render(this.vmScene, this.vmCamera);
    }
  }
}

// Film-like grade: slight warm contrast curve, vignette, low-health desaturation, fine grain.
const GradeShader = {
  uniforms: {
    tDiffuse: { value: null },
    vignette: { value: 0.35 },
    damage: { value: 0 },
    desat: { value: 0 },
    time: { value: 0 },
  },
  vertexShader: /* glsl */ `
    varying vec2 vUv;
    void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
  fragmentShader: /* glsl */ `
    uniform sampler2D tDiffuse;
    uniform float vignette, damage, desat, time;
    varying vec2 vUv;
    float hash(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
    void main() {
      vec4 c = texture2D(tDiffuse, vUv);
      vec3 col = c.rgb;
      float l = dot(col, vec3(0.2126, 0.7152, 0.0722));
      col = mix(vec3(l), col, 1.12 - desat * 0.9);
      col *= vec3(1.04, 1.0, 0.93);
      vec2 d = vUv - 0.5;
      float v = smoothstep(0.85, 0.2, length(d * vec2(1.1, 1.0)));
      col *= mix(1.0, v, vignette);
      float edge = smoothstep(0.25, 0.75, length(d * vec2(1.0, 1.25)));
      col = mix(col, col * vec3(0.55, 0.05, 0.03) + vec3(0.12, 0.0, 0.0), clamp(damage * edge, 0.0, 0.85));
      col += (hash(vUv * 1000.0 + time) - 0.5) * 0.018;
      gl_FragColor = vec4(col, c.a);
    }`,
};
