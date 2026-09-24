// All sound is synthesized with the Web Audio API (no audio files needed).
export class Audio {
  constructor() {
    this.ctx = null;
    this.muted = false;
  }

  init() {
    if (this.ctx) {
      if (this.ctx.state === "suspended") this.ctx.resume();
      return;
    }
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    const ctx = (this.ctx = new AC());
    this.master = ctx.createGain();
    this.master.gain.value = 0.8;
    this.lowpass = ctx.createBiquadFilter(); // muffles everything when badly hurt
    this.lowpass.type = "lowpass";
    this.lowpass.frequency.value = 20000;
    const comp = ctx.createDynamicsCompressor();
    comp.threshold.value = -14;
    comp.ratio.value = 6;
    comp.attack.value = 0.002;
    comp.release.value = 0.2;
    this.master.connect(this.lowpass).connect(comp).connect(ctx.destination);
    // outdoor reverb: a diffuse tail plus discrete echoes off buildings
    this.reverb = ctx.createConvolver();
    this.reverb.buffer = this._impulse(2.4);
    this.reverbSend = ctx.createGain();
    this.reverbSend.gain.value = 0.55;
    this.reverbSend.connect(this.reverb).connect(this.master);
    this.noise = this._noiseBuffer(2);
    this._wind();
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
        d[i] = (Math.random() * 2 - 1) * Math.pow(1 - t / sec, 3.2) * 0.35 * Math.min(1, t * 30);
      }
      for (const e of echoes) {
        const at = Math.floor((e + c * 0.013 + Math.random() * 0.01) * ctx.sampleRate);
        for (let k = 0; k < 900; k++) d[at + k] += (Math.random() * 2 - 1) * Math.exp(-k / 180) * 0.9 * (1 - e);
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
    g.gain.value = 0.05;
    const lfo = ctx.createOscillator();
    lfo.frequency.value = 0.09;
    const lg = ctx.createGain();
    lg.gain.value = 0.035;
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

  _out(pos, gain = 1, reverb = 0.3) {
    // returns a node to connect sources into (spatialized if pos is given)
    const ctx = this.ctx;
    const g = ctx.createGain();
    g.gain.value = gain;
    if (pos) {
      const pan = ctx.createPanner();
      pan.panningModel = "HRTF";
      pan.distanceModel = "inverse";
      pan.refDistance = 4;
      pan.rolloffFactor = 1.1;
      pan.maxDistance = 400;
      if (pan.positionX) {
        pan.positionX.value = pos.x;
        pan.positionY.value = pos.y;
        pan.positionZ.value = pos.z;
      } else pan.setPosition(pos.x, pos.y, pos.z);
      g.connect(pan).connect(this.master);
      if (reverb) {
        const s = ctx.createGain();
        s.gain.value = reverb;
        pan.connect(s).connect(this.reverbSend);
      }
    } else {
      g.connect(this.master);
      if (reverb) {
        const s = ctx.createGain();
        s.gain.value = reverb;
        g.connect(s).connect(this.reverbSend);
      }
    }
    return g;
  }

  _noise(dest, t, dur, type, freq, q, peak, decay, attack = 0.001) {
    const ctx = this.ctx;
    const src = ctx.createBufferSource();
    src.buffer = this.noise;
    src.playbackRate.value = 0.8 + Math.random() * 0.4;
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

  distance(pos) {
    if (!pos || !this.listenerPos) return 0;
    return pos.distanceTo(this.listenerPos);
  }

  // 5.56 rifle shot. Player shots are unspatialized; distant ones get delay + air absorption.
  gunshot(pos = null, loud = 1) {
    if (!this.ctx || this.muted) return;
    const ctx = this.ctx;
    const d = this.distance(pos);
    const t = ctx.currentTime + d / 343; // speed of sound
    const far = Math.min(1, d / 120);
    const out = this._out(pos, loud * (pos ? 1.6 : 0.9), pos ? 0.5 + far * 0.6 : 0.4);
    // distant shots lose their high end
    const air = ctx.createBiquadFilter();
    air.type = "lowpass";
    air.frequency.value = 16000 / (1 + d / 18);
    air.connect(out);
    const j = 0.9 + Math.random() * 0.2;
    this._noise(air, t, 0.08, "bandpass", 3200 * j, 0.6, 1.1, 0.05);
    this._noise(air, t, 0.25, "lowpass", 1100 * j, 0.7, 1.4, 0.22);
    this._tone(air, t, 130 * j, 42, 0.16, 1.3);
    this._noise(air, t + 0.004, 0.4, "lowpass", 380, 0.5, 0.5, 0.45, 0.01);
    if (!pos) this._noise(out, t + 0.03, 0.02, "highpass", 5200, 1, 0.12, 0.02); // bolt carrier
  }

  // supersonic crack + whizz of a round passing close to the listener
  crack(pos) {
    if (!this.ctx || this.muted) return;
    const t = this.ctx.currentTime;
    const out = this._out(pos, 0.9, 0.15);
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
    g.gain.setValueAtTime(0.35, t);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.2);
    src.connect(f).connect(g).connect(out);
    src.start(t, Math.random(), 0.25);
  }

  impact(surface, pos) {
    if (!this.ctx || this.muted) return;
    const d = this.distance(pos);
    if (d > 90) return;
    const t = this.ctx.currentTime;
    const out = this._out(pos, 0.9, 0.12);
    switch (surface) {
      case "metal":
        this._noise(out, t, 0.02, "highpass", 4000, 1, 0.5, 0.02);
        for (const f of [1750, 2630, 4120]) this._tone(out, t, f * (0.9 + Math.random() * 0.2), f * 0.98, 0.35, 0.12);
        break;
      case "wood":
        this._noise(out, t, 0.08, "bandpass", 900, 2.5, 0.8, 0.08);
        this._tone(out, t, 320, 180, 0.08, 0.35);
        break;
      case "flesh":
        this._noise(out, t, 0.1, "lowpass", 700, 1, 1.0, 0.1);
        this._tone(out, t, 110, 60, 0.1, 0.6);
        break;
      case "concrete":
      case "plaster":
        this._noise(out, t, 0.06, "bandpass", 2400, 1.2, 0.7, 0.05);
        this._noise(out, t + 0.01, 0.15, "lowpass", 900, 0.8, 0.3, 0.14);
        break;
      default:
        this._noise(out, t, 0.12, "lowpass", 1300, 0.7, 0.6, 0.1);
        this._tone(out, t, 90, 50, 0.08, 0.3);
    }
  }

  footstep(pos = null, gain = 0.28) {
    if (!this.ctx || this.muted) return;
    const t = this.ctx.currentTime;
    const out = this._out(pos, gain, 0.05);
    this._noise(out, t, 0.09, "bandpass", 500 + Math.random() * 400, 1.2, 0.8, 0.08, 0.006);
    this._noise(out, t + 0.02, 0.05, "highpass", 3500, 0.7, 0.18, 0.05, 0.004);
  }

  reload(part) {
    if (!this.ctx || this.muted) return;
    const t = this.ctx.currentTime;
    const out = this._out(null, 0.5, 0.05);
    if (part === "out") {
      this._noise(out, t, 0.03, "highpass", 2500, 1, 0.8, 0.03);
      this._tone(out, t, 2100, 1800, 0.05, 0.2, "triangle");
      this._noise(out, t + 0.05, 0.1, "bandpass", 700, 1, 0.4, 0.1);
    } else if (part === "in") {
      this._noise(out, t, 0.03, "bandpass", 1600, 1.5, 1.0, 0.03);
      this._noise(out, t + 0.07, 0.03, "highpass", 3000, 1, 0.9, 0.03);
      this._tone(out, t + 0.07, 2600, 2400, 0.06, 0.2, "triangle");
    } else if (part === "slap") {
      this._noise(out, t, 0.05, "lowpass", 900, 1, 0.9, 0.05);
    } else if (part === "dry") {
      this._noise(out, t, 0.02, "highpass", 4000, 1, 0.6, 0.02);
      this._tone(out, t, 3200, 3000, 0.03, 0.1, "square");
    } else if (part === "switch") {
      this._noise(out, t, 0.02, "bandpass", 2800, 2, 0.6, 0.02);
    }
  }

  hitmarker(kind) {
    if (!this.ctx || this.muted) return;
    const t = this.ctx.currentTime;
    const out = this._out(null, 0.35, 0);
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
    if (!this.ctx || this.muted) return;
    const t = this.ctx.currentTime;
    const out = this._out(null, 0.8, 0.05);
    this._noise(out, t, 0.15, "lowpass", 500, 1, 1.0, 0.15);
    this._tone(out, t, 70, 40, 0.2, 0.8);
    // brief tinnitus ring
    this._tone(out, t, 3900, 3880, 1.2, 0.025);
  }

  heartbeat() {
    if (!this.ctx || this.muted) return;
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
