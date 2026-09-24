// Frontline: Dust Veil - game bootstrap and loop.
import * as THREE from "../vendor/three-r186/three-bundle.min.js";
import { Engine, defaultQuality } from "./engine.js";
import { Assets } from "./assets.js";
import { Level } from "./level.js";
import { FX } from "./fx.js";
import { Audio } from "./audio.js";
import { Input } from "./input.js";
import { Player } from "./player.js";
import { Weapon } from "./weapon.js";
import { Enemies } from "./enemies.js";
import { HUD } from "./hud.js";

const $ = (id) => document.getElementById(id);

// Insurgent placements: guards, patrols, rooftop/tower marksmen (DMR) and shotgunners indoors.
const PI = Math.PI;
const HOSTILES = [
  { x: 3.8, z: 47.5, yaw: -PI / 2 },
  { x: -4.5, z: 47.8, yaw: PI / 2 },
  { x: -12, z: 48, path: [[-12, 48], [-12, 33], [-28, 33], [-28, 49]] },
  { x: 23, z: 36.4, y: 6.4, yaw: 0.5, static: true, weapon: "DMR" },
  { x: -24, z: 12, yaw: PI / 2, weapon: "SG" },
  { x: -36, z: -2, path: [[-36, -2], [30, -2.5], [30, -12], [-20, -12]] },
  { x: 47, z: 1, yaw: 0.2 },
  { x: 22, z: 5, yaw: PI / 2, weapon: "SG" },
  { x: 62, z: -62, y: 3.6, yaw: (3 * PI) / 4, static: true, weapon: "DMR" },
  { x: 19, z: -25.9, y: 6.4, yaw: PI, static: true, weapon: "DMR" },
  { x: 18, z: -21.5, yaw: PI * 0.9 },
  { x: -4, z: -55, yaw: PI, weapon: "SG" },
  { x: 3, z: -45, path: [[3, -45], [-10, -41], [-10, -37], [3, -38]] },
  { x: -22, z: -19, path: [[-22, -19], [-10, -20], [-10, -33], [-32, -33], [-33, -19]] },
  { x: -43.5, z: 22, yaw: -PI / 2 },
  { x: -62, z: -62, y: 3.6, yaw: (-3 * PI) / 4, static: true, weapon: "DMR" },
  { x: 25, z: -30, yaw: PI / 2, weapon: "SG" },
  { x: 44, z: -12, path: [[44, -12], [50, 12], [36, 14], [36, -10]] },
  { x: -20, z: -27, yaw: PI / 2, weapon: "SG" },
  { x: 10, z: -52, yaw: PI * 0.8 },
  { x: -46, z: -10, yaw: -PI / 2 },
];
// The player's squad starts with you at the south gate: [right, back] wedge slots.
const SQUAD = [
  { x: -2.5, z: 67, slot: [-3, 3] },
  { x: 2.5, z: 67, slot: [3, 3] },
  { x: -4.5, z: 69.5, slot: [-5.5, 6.5] },
  { x: 4.5, z: 69.5, slot: [5.5, 6.5], weapon: "DMR" },
];

const settings = loadSettings();

function loadSettings() {
  const def = { quality: defaultQuality(), sens: 1, difficulty: "regular", fov: 72, mode: "squad" };
  try {
    return { ...def, ...JSON.parse(localStorage.getItem("frontline-settings") || "{}") };
  } catch {
    return def;
  }
}

function saveSettings() {
  try {
    localStorage.setItem("frontline-settings", JSON.stringify(settings));
  } catch {
    /* storage unavailable */
  }
}

class Game {
  constructor() {
    this.playing = false;
    this.started = false;
    this.over = false;
    this.kills = 0;
    this.headshots = 0;
    this.time = 0;
  }

  async boot() {
    this.engine = new Engine($("view"), settings.quality);
    this.engine.baseFov = settings.fov;
    const bar = $("loadFill");
    const label = $("loadLabel");
    this.audio = new Audio();
    const soundLoad = this.audio.load();
    this.assets = await new Assets(this.engine.renderer, (f, url) => {
      bar.style.width = (f * 100).toFixed(0) + "%";
      label.textContent = "Loading " + url.split("/").pop();
    }).load();
    label.textContent = "Loading sounds...";
    await soundLoad;
    label.textContent = "Building the village...";
    await new Promise((r) => setTimeout(r, 30));
    this.level = new Level(this.engine, this.assets).build();
    this.fx = new FX(this.engine, this.assets, this.level.world);
    this.input = new Input(this.engine.renderer.domElement);
    this.input.sensitivity = settings.sens;
    this.player = new Player(this.engine, this.level.world, this.audio);
    this.player.spawn(0, 65, 0);
    this.weapon = new Weapon(this.engine, this.assets, this.fx, this.audio, this.level.world);
    const mode = settings.mode;
    this.enemies = new Enemies(this.engine, this.assets, this.level.world, this.level.nav, this.fx, this.audio, settings.difficulty, mode);
    const spawns = HOSTILES.map((h, i) => ({ ...h, team: mode === "ffa" ? "ffa" + i : "red" }));
    if (mode === "squad") SQUAD.forEach((s) => spawns.push({ ...s, team: "blue", yaw: 0 }));
    this.enemies.spawn(spawns);
    this.hud = new HUD();
    this.input.onUnlock = () => {
      if (this.playing && !this.over) this.pause();
    };
    // warm up: compile shaders and upload textures before the first real frame
    label.textContent = "Compiling shaders...";
    this.player.update(0, this.input, this.weapon);
    this.weapon.update(0, this.input, this.player, this.enemies, this);
    this.enemies.update(0, this.player, this);
    this.engine.followShadow(this.player.pos);
    await this.engine.renderer.compileAsync(this.engine.scene, this.engine.camera);
    this.engine.render({ vignette: 0.35, damage: 0, desat: 0 });
    $("loading").classList.add("hidden");
    $("menu").classList.remove("hidden");
    this.last = performance.now();
    this.engine.renderer.setAnimationLoop(() => this.frame());
    if (new URLSearchParams(location.search).has("autostart")) this.start();
  }

  start() {
    this.audio.init();
    this.input.enabled = true;
    $("menu").classList.add("hidden");
    $("pause").classList.add("hidden");
    $("hud").classList.remove("hidden");
    document.body.classList.toggle("touch", this.input.touch);
    if (!this.input.touch) this.engine.renderer.domElement.requestPointerLock?.();
    this.playing = true;
    if (!this.started) {
      this.started = true;
      this.hud.notify(settings.mode === "ffa" ? "Free-for-all: everyone is hostile" : "Clear the village of all hostiles");
    }
    this.last = performance.now();
  }

  pause() {
    this.playing = false;
    $("pause").classList.remove("hidden");
  }

  onKill(head) {
    this.kills++;
    if (head) this.headshots++;
    this.hud.hitmarker(true);
    this.hud.feed(head ? "HEADSHOT  +150" : "HOSTILE DOWN  +100", head);
    const left = this.enemies.aliveCount;
    if (left === 0) {
      setTimeout(() => this.finish(true), 2200);
    } else if (left <= 3) {
      this.hud.notify(`${left} hostile${left > 1 ? "s" : ""} remaining`);
    }
  }

  // a kill made by an AI soldier
  onAiKill(victim, killer) {
    if (victim.ally) this.hud.feed("SQUADMATE DOWN", false);
    else if (killer && killer.ally) this.hud.feed("SQUAD KILL", false);
    if (this.enemies.aliveCount === 0 && !this.over) setTimeout(() => this.finish(true), 2200);
  }

  onNearMiss() {
    this.suppression = Math.min(1, (this.suppression || 0) + 0.25);
  }

  onPlayerDeath() {
    setTimeout(() => this.finish(false), 1800);
  }

  finish(won) {
    if (this.over) return;
    this.over = true;
    this.playing = false;
    document.exitPointerLock?.();
    const w = this.weapon;
    const acc = w.shots ? Math.round((w.hits / w.shots) * 100) : 0;
    const t = Math.floor(this.time);
    $("endTitle").textContent = won ? "MISSION COMPLETE" : "KILLED IN ACTION";
    $("endTitle").className = won ? "win" : "lose";
    $("endStats").innerHTML = `
      <div><b>${this.kills}</b><span>Kills</span></div>
      <div><b>${this.headshots}</b><span>Headshots</span></div>
      <div><b>${acc}%</b><span>Accuracy</span></div>
      <div><b>${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}</b><span>Time</span></div>`;
    $("end").classList.remove("hidden");
    $("hud").classList.add("hidden");
  }

  frame() {
    const now = performance.now();
    const dt = Math.min(0.05, (now - this.last) / 1000);
    this.last = now;
    const input = this.input;
    if (this.playing) {
      this.time += dt;
      if (input.consume("Escape") || input.consume("KeyP")) this.pause();
      this.player.update(dt, input, this.weapon);
      this.weapon.update(dt, input, this.player, this.enemies, this);
      this.enemies.update(dt, this.player, this);
      this.fx.update(dt);
      this.hud.update(dt, this.player, this.weapon, this.enemies);
      this.audio.setListener(this.engine.camera);
      // heartbeat + muffled hearing when badly hurt; suppression tightens the vignette
      const hurt = 1 - this.player.health / 100;
      this.audio.setMuffle(Math.max(0, hurt - 0.45) * 1.2);
      this.hbT = (this.hbT || 0) - dt;
      if (this.player.health < 35 && this.hbT <= 0 && !this.player.dead) {
        this.audio.heartbeat();
        this.hbT = 0.9;
      }
      this.suppression = Math.max(0, (this.suppression || 0) - dt * 0.4);
    } else if (this.started) {
      this.fx.update(0);
    }
    this.engine.followShadow(this.player.pos);
    const hurt = 1 - this.player.health / 100;
    this.engine.render({
      vignette: 0.35 + (this.suppression || 0) * 0.5 + this.weapon.adsT * 0.15,
      damage: Math.max(0, hurt - 0.3) * 1.2,
      desat: Math.max(0, hurt - 0.5) * 1.4 + (this.player.dead ? 0.8 : 0),
    });
    input.endFrame();
  }
}

// ---------------------------------------------------------------------------------------
const game = new Game();
window.frontline = game;

function setupMenu() {
  const q = $("optQuality");
  q.value = settings.quality;
  q.onchange = () => {
    settings.quality = q.value;
    saveSettings();
    location.reload();
  };
  const m = $("optMode");
  m.value = settings.mode;
  m.onchange = () => {
    settings.mode = m.value;
    saveSettings();
    location.reload();
  };
  const d = $("optDifficulty");
  d.value = settings.difficulty;
  d.onchange = () => {
    settings.difficulty = d.value;
    saveSettings();
    location.reload();
  };
  const s = $("optSens");
  s.value = settings.sens;
  s.oninput = () => {
    settings.sens = parseFloat(s.value);
    if (game.input) game.input.sensitivity = settings.sens;
    saveSettings();
  };
  const f = $("optFov");
  f.value = settings.fov;
  f.oninput = () => {
    settings.fov = parseFloat(f.value);
    if (game.engine) game.engine.baseFov = settings.fov;
    $("fovVal").textContent = settings.fov;
    saveSettings();
  };
  $("fovVal").textContent = settings.fov;
  $("deployBtn").onclick = () => game.start();
  $("resumeBtn").onclick = () => game.start();
  $("retryBtn").onclick = () => location.reload();
  $("quitBtn").onclick = () => location.reload();
  for (const b of document.querySelectorAll("[data-panel]")) {
    b.onclick = () => $(b.dataset.panel).classList.toggle("hidden");
  }
}

setupMenu();
game.boot().catch((err) => {
  console.error(err);
  $("loadLabel").textContent = "Failed to load: " + err.message;
});
