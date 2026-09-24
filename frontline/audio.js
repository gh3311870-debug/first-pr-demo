// Game audio: recorded sound effects (Xonotic, GPLv3+, see assets/frontline/sounds/README.md)
// played through Web Audio with 3D positioning, speed-of-sound delay, air absorption and an
// outdoor echo. A few UI/body cues (bullet crack, heartbeat, wind, hit ticks) are synthesized.
const BASE = "assets/frontline/sounds/";

const SAMPLES = [
  "rifle_shot", "dmr_shot", "sniper_far", "shotgun_shot", "reload_out", "reload_in", "dryfire",
  "impact_stone_1", "impact_stone_2", "impact_stone_3", "impact_stone_4",
  "impact_metal_1", "impact_metal_2", "impact_metal_3", "impact_wood_1", "impact_wood_2", "impact_wood_3",
  "impact_flesh_1", "impact_flesh_2", "impact_flesh_3", "body_1", "body_2", "ric_1", "ric_2", "ric_3",
  "casing_1", "casing_2", "casing_3", "step_1", "step_2", "step_3", "step_4", "step_5", "step_6",
];

// how each weapon sounds: sample, playback rate, gain, extra low "thump" for the shooter
export const GUN_SOUNDS = {
  rifle: { sample: "rifle_shot", rate: 1.0, gain: 1.0, thump: 1.0 },
  smg: { sample: "rifle_shot", rate: 1.12, gain: 0.8, thump: 0.6 },
  dmr: { sample: "dmr_shot", rate: 1.0, gain: 1.15, thump: 1.4 },
  shotgun: { sample: "shotgun_shot", rate: 1.0, gain: 1.2, thump: 1.6 },
  pistol: { sample: "rifle_shot", rate: 1.28, gain: 0.8, thump: 0.5 },
};

export class Audio {
  constructor() {
    this.ctx = null;
    this.buf = {};
    this.muted = false;
    this.listenerPos = null;
  }

  // Create the context early (it starts suspended) so samples decode during loading.
  async load(onProgress) {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    const ctx = (this.ctx = new AC());
    this.master = ctx.createGain();
    this.master.gain.value = 0.85;
    this.lowpass = ctx.createBiquadFilter(); // muffles everything when badly hurt
    this.lowpass.type = "lowpass";
    this.lowpass.frequency.value = 20000;
    const comp = ctx.createDynamicsCompressor();
    comp.threshold.value = -12;
    comp.ratio.value = 5;
    comp.attack.value = 0.003;
    comp.release.value = 0.25;
    this.master.connect(this.lowpass).connect(comp).connect(ctx.destination);
    // outdoor reverb: diffuse tail plus discrete slap-back echoes off the buildings
    this.reverb = ctx.createConvolver();
    this.reverb.buffer = this._impulse(2.6);
    this.reverbSend = ctx.createGain();
    this.reverbSend.gain.value = 0.5;
    this.reverbSend.connect(this.reverb).connect(this.master);
    this.noise = this._noiseBuffer(2);
    let done = 0;
    await Promise.all(SAMPLES.map(async (name) => {
      try {
        const res = await fetch(BASE + name + ".wav");
        const data = await res.arrayBuffer();
        this.buf[name] = await new Promise((ok, fail) => ctx.decodeAudioData(data, ok, fail));
      } catch (e) {
        console.warn("sound failed", name, e);
      }
      onProgress && onProgress(++done / SAMPLES.length);
    }));
  }

  // Must be called from a user gesture (browsers keep audio locked until then).
  init() {
    if (!this.ctx) return;
    if (this.ctx.state === "suspended") this.ctx.resume();
    if (!this._windOn) {
      this._windOn = true;
      this._wind();
    }
  }

  _noiseBuffer(sec) {
    const ctx = this.ctx;
    const b = ctx.createBuffer(1, ctx.sampleRate * sec, ctx.sampleRate);
    const d = b.getChannelData(0);
    for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
    return b;
  }

  _impulse(sec) {
    const ctx = this.ctx;
    const len = Math.floor(ctx.sampleRate * sec);
    const b = ctx.createBuffer(2, len, ctx.sampleRate);
    const echoes = [0.07, 0.16, 0.23, 0.37, 0.52, 0.8];
    for (let c = 0; c < 2; c++) {
      const d = b.getChannelData(c);
      for (let i = 0; i < len; i++) {
        const t = i / ctx.sampleRate;
        d[i] = (Math.random() * 2 - 1) * Math.pow(1 - t / sec, 3.2) * 0.3 * Math.min(1, t * 30);
      }
      for (const e of echoes) {
        const at = Math.floor((e + c * 0.013 + Math.random() * 0.01) * ctx.sampleRate);
        for (let k = 0; k < 900; k++) d[at + k] += (Math.random() * 2 - 1) * Math.exp(-k / 180) * 0.8 * (1 - e);
      }
    }
    return b;
  }

  _wind() {
    const ctx = this.ctx;
    const src = ctx.createBufferSource();
    src.buffer = this.noise;
    src.loop = true;
    const f = ctx.createBiquadFilter();
    f.type = "lowpass";
    f.frequency.value = 420;
    const g = ctx.createGain();
    g.gain.value = 0.045;
    const lfo = ctx.createOscillator();
    lfo.frequency.value = 0.09;
    const lg = ctx.createGain();
    lg.gain.value = 0.03;
    lfo.connect(lg).connect(g.gain);
    const lfo2 = ctx.createOscillator();
    lfo2.frequency.value = 0.23;
    const lg2 = ctx.createGain();
    lg2.gain.value = 180;
    lfo2.connect(lg2).connect(f.frequency);
    src.connect(f).connect(g).connect(this.master);
    src.start();
    lfo.start();
    lfo2.start();
  }

  setListener(cam) {
    if (!this.ctx) return;
    const l = this.ctx.listener;
    const p = cam.position;
    const fwd = cam.getWorldDirection(this._fwd || (this._fwd = cam.position.clone()));
    const t = this.ctx.currentTime;
    if (l.positionX) {
      l.positionX.setValueAtTime(p.x, t);
      l.positionY.setValueAtTime(p.y, t);
      l.positionZ.setValueAtTime(p.z, t);
      l.forwardX.setValueAtTime(fwd.x, t);
      l.forwardY.setValueAtTime(fwd.y, t);
      l.forwardZ.setValueAtTime(fwd.z, t);
      l.upX.setValueAtTime(0, t);
      l.upY.setValueAtTime(1, t);
      l.upZ.setValueAtTime(0, t);
    } else {
      l.setPosition(p.x, p.y, p.z);
      l.setOrientation(fwd.x, fwd.y, fwd.z, 0, 1, 0);
    }
    this.listenerPos = p;
  }

  get ready() {
    return this.ctx && this.ctx.state === "running" && !this.muted;
  }

  distance(pos) {
    if (!pos || !this.listenerPos) return 0;
    return pos.distanceTo(this.listenerPos);
  }

  // Output node: spatialized when pos is given, with a send into the outdoor reverb.
  _out(pos, gain = 1, reverb = 0.3) {
    const ctx = this.ctx;
    const g = ctx.createGain();
    g.gain.value = gain;
    let tail = g;
    if (pos) {
      const pan = ctx.createPanner();
      pan.panningModel = "HRTF";
      pan.distanceModel = "inverse";
      pan.refDistance = 4;
      pan.rolloffFactor = 1.1;
      pan.maxDistance = 500;
      if (pan.positionX) {
        pan.positionX.value = pos.x;
        pan.positionY.value = pos.y;
        pan.positionZ.value = pos.z;
      } else pan.setPosition(pos.x, pos.y, pos.z);
      g.connect(pan);
      tail = pan;
    }
    tail.connect(this.master);
    if (reverb) {
      const s = ctx.createGain();
      s.gain.value = reverb;
      tail.connect(s).connect(this.reverbSend);
    }
    return g;
  }

  // Play a recorded sample. name may be a prefix ("impact_stone") to pick a random variant.
  sample(name, dest, { when = 0, rate = 1, gain = 1, lowpass = 0, offset = 0 } = {}) {
    let b = this.buf[name];
    if (!b) {
      const variants = Object.keys(this.buf).filter((k) => k.startsWith(name + "_"));
      if (!variants.length) return;
      b = this.buf[variants[Math.floor(Math.random() * variants.length)]];
    }
    const ctx = this.ctx;
    const src = ctx.createBufferSource();
    src.buffer = b;
    src.playbackRate.value = rate;
    let node = src;
    if (lowpass) {
      const f = ctx.createBiquadFilter();
      f.type = "lowpass";
      f.frequency.value = lowpass;
      node = node.connect(f);
    }
    const g = ctx.createGain();
    g.gain.value = gain;
    node.connect(g).connect(dest);
    src.start(Math.max(ctx.currentTime, when || ctx.currentTime), offset);
  }

  _noise(dest, t, dur, type, freq, q, peak, decay, attack = 0.001) {
    const ctx = this.ctx;
    const src = ctx.createBufferSource();
    src.buffer = this.noise;
    const f = ctx.createBiquadFilter();
    f.type = type;
    f.frequency.value = freq;
    f.Q.value = q;
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(peak, t + attack);
    g.gain.exponentialRampToValueAtTime(0.0001, t + decay);
    src.connect(f).connect(g).connect(dest);
    src.start(t, Math.random() * 1.5, dur);
  }

  _tone(dest, t, f0, f1, dur, peak, type = "sine") {
    const ctx = this.ctx;
    const o = ctx.createOscillator();
    o.type = type;
    o.frequency.setValueAtTime(f0, t);
    o.frequency.exponentialRampToValueAtTime(Math.max(1, f1), t + dur);
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(peak, t + 0.002);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g).connect(dest);
    o.start(t);
    o.stop(t + dur + 0.05);
  }

  // Gunshot. pos = null for the player's own weapon; otherwise a 3D source that arrives
  // late (speed of sound) and duller with distance, with more echo far away.
  gunshot(kind = "rifle", pos = null, loud = 1) {
    if (!this.ready) return;
    const s = GUN_SOUNDS[kind] || GUN_SOUNDS.rifle;
    const d = this.distance(pos);
    const t = this.ctx.currentTime + d / 343;
    const far = Math.min(1, d / 140);
    const out = this._out(pos, loud * s.gain * (pos ? 1.8 : 0.95), pos ? 0.35 + far * 0.7 : 0.35);
    const rate = s.rate * (0.96 + Math.random() * 0.08);
    const lowpass = pos ? 16000 / (1 + d / 25) : 0;
    const sample = kind === "dmr" && d > 70 ? "sniper_far" : s.sample;
    this.sample(sample, out, { when: t, rate, lowpass });
    // body you feel in your chest when you fire it yourself
    if (!pos) this._tone(out, t, 110, 42, 0.14, 0.6 * s.thump);
  }

  // Brass hitting the ground a moment after the shot.
  casing(delay = 0.45) {
    if (!this.ready || Math.random() < 0.35) return;
    const out = this._out(null, 0.14, 0.05);
    this.sample("casing", out, { when: this.ctx.currentTime + delay + Math.random() * 0.15, rate: 0.95 + Math.random() * 0.15 });
  }

  // Supersonic crack + whizz of a round passing close to the listener.
  crack(pos) {
    if (!this.ready) return;
    const t = this.ctx.currentTime;
    const out = this._out(pos, 0.8, 0.15);
    this._noise(out, t, 0.03, "highpass", 1800, 0.7, 1.0, 0.025);
    const ctx = this.ctx;
    const src = ctx.createBufferSource();
    src.buffer = this.noise;
    const f = ctx.createBiquadFilter();
    f.type = "bandpass";
    f.Q.value = 6;
    f.frequency.setValueAtTime(3000, t);
    f.frequency.exponentialRampToValueAtTime(700, t + 0.18);
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.3, t);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.2);
    src.connect(f).connect(g).connect(out);
    src.start(t, Math.random(), 0.25);
  }

  impact(surface, pos) {
    if (!this.ready) return;
    const d = this.distance(pos);
    if (d > 90) return;
    const out = this._out(pos, 0.8, 0.12);
    const r = 0.9 + Math.random() * 0.2;
    switch (surface) {
      case "metal":
        this.sample("impact_metal", out, { rate: r });
        if (Math.random() < 0.3 && d < 30) this.sample("ric", out, { rate: r, gain: 0.5 });
        break;
      case "wood":
        this.sample("impact_wood", out, { rate: r });
        break;
      case "flesh":
        this.sample("impact_flesh", out, { rate: r, gain: 0.9 });
        this.sample("body", out, { rate: r, gain: 0.5 });
        break;
      case "concrete":
      case "plaster":
        this.sample("impact_stone", out, { rate: r });
        if (Math.random() < 0.12 && d < 25) this.sample("ric", out, { rate: r, gain: 0.35 });
        break;
      default: // sand, sandbags, dirt: a dull thud
        this.sample("impact_stone", out, { rate: r * 0.7, lowpass: 1200, gain: 0.8 });
    }
  }

  footstep(pos = null, gain = 0.28) {
    if (!this.ready) return;
    const out = this._out(pos, gain * 1.6, 0.04);
    this.sample("step", out, { rate: 0.9 + Math.random() * 0.2 });
  }

  reload(part) {
    if (!this.ready) return;
    const out = this._out(null, 0.6, 0.05);
    const t = this.ctx.currentTime;
    switch (part) {
      case "out":
        this.sample("reload_out", out);
        break;
      case "in":
        this.sample("reload_in", out);
        break;
      case "shell": // shotgun shell pushed into the tube
        this.sample("reload_in", out, { rate: 1.35, gain: 0.55 });
        break;
      case "pump":
        this.sample("reload_in", out, { rate: 0.8, gain: 0.8 });
        this.sample("reload_out", out, { rate: 0.95, gain: 0.35, when: t + 0.12 });
        break;
      case "slap":
        this._noise(out, t, 0.05, "lowpass", 900, 1, 0.7, 0.05);
        break;
      case "dry":
        this.sample("dryfire", out);
        break;
      case "switch":
        this.sample("dryfire", out, { rate: 0.8, gain: 0.5 });
        this._noise(out, t + 0.05, 0.12, "bandpass", 700, 0.8, 0.25, 0.12);
        break;
    }
  }

  hitmarker(kind) {
    if (!this.ready) return;
    const t = this.ctx.currentTime;
    const out = this._out(null, 0.3, 0);
    if (kind === "head") {
      this._tone(out, t, 2600, 2400, 0.12, 0.35, "triangle");
      this._tone(out, t, 5200, 5000, 0.08, 0.1);
    } else if (kind === "kill") {
      this._tone(out, t, 1100, 900, 0.08, 0.35, "triangle");
      this._tone(out, t + 0.05, 1500, 1300, 0.1, 0.25, "triangle");
    } else {
      this._tone(out, t, 1700, 1600, 0.04, 0.25, "triangle");
    }
  }

  hurt() {
    if (!this.ready) return;
    const t = this.ctx.currentTime;
    const out = this._out(null, 0.9, 0.05);
    this.sample("body", out, { rate: 0.8, gain: 0.8 });
    this.sample("impact_flesh", out, { rate: 0.85, gain: 0.5, lowpass: 2500 });
    // brief tinnitus ring
    this._tone(out, t, 3900, 3880, 1.2, 0.02);
  }

  heartbeat() {
    if (!this.ready) return;
    const t = this.ctx.currentTime;
    const out = this._out(null, 0.5, 0);
    this._tone(out, t, 60, 40, 0.14, 0.9);
    this._tone(out, t + 0.24, 55, 38, 0.12, 0.6);
  }

  setMuffle(amount) {
    if (!this.ctx) return;
    const f = 20000 * Math.pow(1 - amount, 2) + 700;
    this.lowpass.frequency.setTargetAtTime(f, this.ctx.currentTime, 0.1);
  }
}
