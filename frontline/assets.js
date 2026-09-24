// Asset loading: Blender-built GLBs and generated PBR textures -> three.js materials.
import * as THREE from "../vendor/three-r186/three-bundle.min.js";

const BASE = "assets/frontline/";

export class Assets {
  constructor(renderer, onProgress) {
    this.manager = new THREE.LoadingManager();
    this.manager.onProgress = (url, loaded, total) => onProgress && onProgress(loaded / total, url);
    this.texLoader = new THREE.TextureLoader(this.manager);
    this.gltfLoader = new THREE.GLTFLoader(this.manager);
    this.maxAniso = renderer.capabilities.getMaxAnisotropy();
    this.textures = {};
    this.materials = {};
  }

  tex(name, { srgb = false, repeat = 1 } = {}) {
    const key = name + (srgb ? ":s" : "");
    if (this.textures[key]) return this.textures[key];
    const t = this.texLoader.load(BASE + "tex/" + name);
    t.wrapS = t.wrapT = THREE.RepeatWrapping;
    t.anisotropy = Math.min(8, this.maxAniso);
    if (srgb) t.colorSpace = THREE.SRGBColorSpace;
    t.repeat.set(repeat, repeat);
    this.textures[key] = t;
    return t;
  }

  // PBR set produced by tools/frontline/make_textures.py
  pbr(name, opts = {}) {
    const m = new THREE.MeshStandardMaterial({
      map: this.tex(name + "_col.jpg", { srgb: true }),
      normalMap: this.tex(name + "_nrm.jpg"),
      roughnessMap: this.tex(name + "_orm.jpg"),
      aoMap: null,
      metalness: opts.metalness ?? 0,
      roughness: opts.roughness ?? 1,
      color: opts.color ?? 0xffffff,
    });
    if (opts.metalMap) m.metalnessMap = m.roughnessMap;
    m.normalScale.set(opts.normal ?? 1, opts.normal ?? 1);
    m.name = name;
    return m;
  }

  async load() {
    const glb = (f) => this.gltfLoader.loadAsync(BASE + f);
    const [operator, props] = await Promise.all([glb("operator.glb"), glb("props.glb")]);
    this.operator = operator;
    this.props = props;
    this._buildMaterials();
    await new Promise((res) => {
      // wait for textures queued in _buildMaterials
      if (this.manager.itemsLoaded >= this.manager.itemsTotal) res();
      else this.manager.onLoad = res;
    });
    return this;
  }

  _buildMaterials() {
    const M = this.materials;
    M.sand = this.pbr("sand", { normal: 1.2 });
    M.dirt = this.pbr("dirt", { normal: 1.2 });
    M.plaster = this.pbr("plaster");
    M.plasterInterior = this.pbr("plaster", { color: 0xb8ad9c });
    M.plasterInterior.envMapIntensity = 0.25;
    M.concrete = this.pbr("concrete", { color: 0xe6dccb });
    M.paint = this.pbr("paint", { metalMap: true, metalness: 1 });
    M.burnt = this.pbr("burnt", { metalMap: true, metalness: 1 });
    M.burlap = this.pbr("burlap");
    M.hesco = this.pbr("hesco", { metalMap: true, metalness: 1 });
    M.wood = new THREE.MeshStandardMaterial({
      map: this.tex("wood_col.jpg", { srgb: true }),
      bumpMap: this.tex("wood_bump.jpg"),
      bumpScale: 1.2,
      roughnessMap: this.tex("wood_rough.jpg"),
      color: 0xc4ad92,
    });
    M.brick = new THREE.MeshStandardMaterial({
      map: this.tex("brick_col.jpg", { srgb: true }),
      bumpMap: this.tex("brick_bump.jpg"),
      bumpScale: 2,
      roughnessMap: this.tex("brick_rough.jpg"),
      color: 0xd8c8b4,
    });
    M.bark = new THREE.MeshStandardMaterial({
      map: this.tex("bark_col.jpg", { srgb: true }),
      normalMap: this.tex("bark_nrm.jpg"),
      roughness: 0.95,
    });
    M.leaf = new THREE.MeshStandardMaterial({
      map: this.tex("palm_leaf.png", { srgb: true }),
      alphaTest: 0.45,
      side: THREE.DoubleSide,
      roughness: 0.75,
    });
    M.shrub = new THREE.MeshStandardMaterial({
      map: this.tex("shrub.png", { srgb: true }),
      alphaTest: 0.4,
      side: THREE.DoubleSide,
      roughness: 0.9,
    });
    M.darkMetal = new THREE.MeshStandardMaterial({ color: 0x151517, metalness: 0.8, roughness: 0.5 });
    M.galv = new THREE.MeshStandardMaterial({
      color: 0x9a9a98, metalness: 0.9, roughness: 0.45, roughnessMap: this.tex("paint_orm.jpg"),
    });
    M.rubber = new THREE.MeshStandardMaterial({ color: 0x0c0c0c, roughness: 0.92 });
    M.plastic = new THREE.MeshStandardMaterial({ color: 0x101010, roughness: 0.5 });
    M.white = this.pbr("paint", { metalMap: true, metalness: 1, color: 0xd8d8d2 });
    M.olive = this.pbr("paint", { metalMap: true, metalness: 1, color: 0x4d5530 });
    M.canvas = this.pbr("burlap", { color: 0x9a9a78 });
    M.canvas.side = THREE.DoubleSide;
    M.glassDark = new THREE.MeshStandardMaterial({ color: 0x0a0c0e, metalness: 0.2, roughness: 0.1 });
    // Grime at the base of exterior walls (world-height based darkening).
    addGroundGrime(M.plaster, 1.3, 0.62);
    addGroundGrime(M.concrete, 0.8, 0.75);
    addGroundGrime(M.brick, 1.0, 0.7);
    // Break up texture tiling on the ground with a second, much larger sample.
    addMacroVariation(M.sand, 0.021);
    addMacroVariation(M.dirt, 0.03);

    // Material name in the Blender props -> game material
    this.propMaterialMap = {
      Wood: M.wood, Concrete: M.concrete, Sandbag: M.burlap, Hesco: M.hesco,
      ContainerPaint: M.paint, BarrelPaint: M.paint, Metal_Dark: M.darkMetal, Metal_Galv: M.galv,
      Rubber: M.rubber, BurntMetal: M.burnt, OliveMetal: M.olive, Palm_Bark: M.bark, Palm_Leaf: M.leaf,
      PlasticBlack: M.plastic, MetalWhite: M.white, Canvas: M.canvas,
    };
    const textured = new Set(["Wood", "Concrete", "Sandbag", "Hesco", "ContainerPaint", "BarrelPaint",
      "BurntMetal", "OliveMetal", "MetalWhite", "Canvas"]);
    this.props.scene.traverse((o) => {
      if (!o.isMesh) return;
      const name = o.material.name;
      if (this.propMaterialMap[name]) o.material = this.propMaterialMap[name];
      o.castShadow = true;
      o.receiveShadow = true;
      if (!textured.has(name)) return;
    });
  }
}

function addGroundGrime(mat, height, strength) {
  mat.onBeforeCompile = (shader) => {
    shader.vertexShader = shader.vertexShader
      .replace("#include <common>", "#include <common>\nvarying float vWorldY;")
      .replace("#include <worldpos_vertex>", "#include <worldpos_vertex>\nvWorldY = (modelMatrix * vec4(transformed, 1.0)).y;");
    shader.fragmentShader = shader.fragmentShader
      .replace("#include <common>", "#include <common>\nvarying float vWorldY;")
      .replace("#include <map_fragment>",
        `#include <map_fragment>
         float grime = smoothstep(0.0, ${height.toFixed(2)}, vWorldY);
         diffuseColor.rgb *= mix(${strength.toFixed(2)}, 1.0, grime);`);
  };
  mat.customProgramCacheKey = () => "grime" + height + strength;
}

function addMacroVariation(mat, scale) {
  mat.onBeforeCompile = (shader) => {
    shader.vertexShader = shader.vertexShader
      .replace("#include <common>", "#include <common>\nvarying vec2 vWorldXZ;")
      .replace("#include <worldpos_vertex>", "#include <worldpos_vertex>\nvWorldXZ = (modelMatrix * vec4(transformed, 1.0)).xz;");
    shader.fragmentShader = shader.fragmentShader
      .replace("#include <common>", "#include <common>\nvarying vec2 vWorldXZ;")
      .replace("#include <map_fragment>",
        `#include <map_fragment>
         vec3 macro = texture2D(map, vWorldXZ * ${scale.toFixed(4)}).rgb;
         vec3 macro2 = texture2D(map, vWorldXZ * ${(scale * 0.31).toFixed(4)} + 0.37).rgb;
         float lm = dot(macro, vec3(0.333)) + dot(macro2, vec3(0.333));
         diffuseColor.rgb *= 0.42 + 0.46 * lm;`);
  };
  mat.customProgramCacheKey = () => "macro" + scale;
}
