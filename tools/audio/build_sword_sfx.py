"""
Blood & Steel -- sound effect renderer.

Renders every sound effect used by sword.html offline with physically
motivated synthesis and writes them as MP3 files to assets/sword/sfx/:

* steel on steel: modal synthesis of two blades (free-free bar modes plus a
  dense cloud of high inharmonic partials, beating mode pairs, edge scrape)
* blade whooshes: noise through a sweeping resonant band + edge-tone whistle
* body hits: gambeson thump, plate clank, chainmail micro-rings, wet flesh
  grains and Minnaert bubbles
* dismemberment: bone crack transients, tearing crackle, gush
* blood: bubble streams (Minnaert resonance) pulsing like an artery
* armoured bodies falling, swords dropping onto sand, footsteps in sand
* voices: glottal pulse source + formant filters, muffled by a helmet
* crowd murmur / cheers built from dozens of synthetic voices and claps
* war drums (membrane modes), torch fire crackle

    pip install numpy scipy soundfile
    python3 tools/audio/build_sword_sfx.py
"""

import json
import math
import os

import numpy as np
import soundfile as sf
from scipy import signal

SR = 44100
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "..", "assets", "sword", "sfx"))
os.makedirs(OUT, exist_ok=True)
MANIFEST = {}


# ---------------------------------------------------------------------------
# DSP helpers
# ---------------------------------------------------------------------------

def T(d):
    return np.arange(int(d * SR)) / SR


def noise(n, rng):
    return rng.standard_normal(n)


def bp(x, lo, hi, order=2):
    sos = signal.butter(order, [max(20, lo), min(hi, SR / 2 - 100)], btype="bandpass", fs=SR, output="sos")
    return signal.sosfilt(sos, x)


def lp(x, f, order=2):
    return signal.sosfilt(signal.butter(order, min(f, SR / 2 - 100), btype="low", fs=SR, output="sos"), x)


def hp(x, f, order=2):
    return signal.sosfilt(signal.butter(order, f, btype="high", fs=SR, output="sos"), x)


def place(dst, src, t0, gain=1.0):
    i = int(t0 * SR)
    if i >= len(dst):
        return
    n = min(len(src), len(dst) - i)
    dst[i:i + n] += src[:n] * gain


def mode(f, tau, dur, amp=1.0, phase=0.0, attack=0.0006, beat=0.0, beat_amp=0.0):
    t = T(dur)
    e = np.exp(-t / tau) * np.minimum(1, t / attack)
    s = np.sin(2 * np.pi * f * t + phase)
    if beat:
        s = s + beat_amp * np.sin(2 * np.pi * (f + beat) * t + phase * 1.7)
    return amp * e * s


def fade_out(x, d=0.02):
    n = min(len(x), int(d * SR))
    x[-n:] *= np.linspace(1, 0, n)
    return x


def trim(x, thresh=1e-4):
    idx = np.where(np.abs(x) > thresh * np.max(np.abs(x)))[0]
    end = idx[-1] + int(0.02 * SR) if len(idx) else len(x)
    return fade_out(x[:min(end, len(x))].copy(), 0.015)


def norm(x, peak=0.89):
    m = np.max(np.abs(x)) + 1e-12
    return x * (peak / m)


def soft_clip(x, drive=1.0):
    """Gentle saturation applied to a peak-normalised signal (glues transients to tails)."""
    x = x / (np.max(np.abs(x)) + 1e-12)
    return np.tanh(x * drive) / np.tanh(drive)


def write(name, x, stereo=False, peak=0.8):
    x = norm(x, peak)
    path = os.path.join(OUT, name + ".mp3")
    sf.write(path, x.T if stereo else x, SR, format="MP3")
    base = name.rsplit("_", 1)[0]
    MANIFEST[base] = MANIFEST.get(base, 0) + 1
    return path


def resonate_blocks(src, formants, block=256):
    """Filter src through time-varying 2-pole resonators.
    formants: callable(t) -> list of (freq, bandwidth, gain)."""
    out = np.zeros_like(src)
    n_f = len(formants(0.0))
    zi = [np.zeros(2) for _ in range(n_f)]
    for s in range(0, len(src), block):
        seg = src[s:s + block]
        fs = formants(s / SR)
        acc = np.zeros_like(seg)
        for k, (f, bw, g) in enumerate(fs):
            r = math.exp(-math.pi * bw / SR)
            th = 2 * math.pi * f / SR
            a = [1, -2 * r * math.cos(th), r * r]
            b = [(1 - r * r) * 0.5]
            y, zi[k] = signal.lfilter(b, a, seg, zi=zi[k])
            acc += y * g
        out[s:s + block] = acc
    return out


# ---------------------------------------------------------------------------
# Metal
# ---------------------------------------------------------------------------

BAR = [1.0, 2.756, 5.404, 8.933, 13.345, 18.638, 24.81]


def blade_modes(rng, f0, dur, amp, damp=1.0, bright=1.0):
    y = np.zeros(int(dur * SR))
    for i, r in enumerate(BAR):
        f = f0 * r * rng.uniform(0.985, 1.015)
        if f > 16000:
            break
        tau = 1.9 / (f / 500) ** 0.75 * rng.uniform(0.6, 1.3) * damp
        a = amp * rng.uniform(0.4, 1.0) / (1 + 0.35 * i) * (bright if i > 2 else 1)
        y += mode(f, tau, dur, a, rng.uniform(0, 6.28), beat=rng.uniform(0.4, 3.5), beat_amp=rng.uniform(0.3, 0.8))
    # dense inharmonic cloud from the blade's width/torsion modes
    for _ in range(26):
        f = math.exp(rng.uniform(math.log(1800), math.log(11000)))
        tau = 0.55 / (f / 1000) ** 0.9 * rng.uniform(0.5, 1.6) * damp
        y += mode(f, tau, dur, amp * rng.uniform(0.05, 0.35) * bright, rng.uniform(0, 6.28), beat=rng.uniform(0.5, 6), beat_amp=0.5)
    return y


def scrape(rng, dur, lo=2200, hi=7500, t_peak=0.02, tau=0.07, amp=1.0):
    n = int(dur * SR)
    t = T(dur)
    x = bp(noise(n, rng), lo, hi, 2)
    env = np.minimum(1, t / t_peak) * np.exp(-np.maximum(0, t - t_peak) / tau)
    # micro-stick-slip roughness
    rough = 1 + 0.8 * lp(noise(n, rng), 120)
    return amp * x * env * np.clip(rough, 0, None)


def clack(rng, dur=0.004, lo=1500, amp=1.0):
    t = T(0.03)
    return amp * hp(noise(len(t), rng), lo) * np.exp(-t / dur)


def steel_clash(seed, parry=False):
    rng = np.random.default_rng(seed)
    dur = 2.6 if parry else 2.0
    y = np.zeros(int(dur * SR))
    f1 = rng.uniform(430, 700)
    f2 = f1 * rng.uniform(1.12, 1.45)
    y += blade_modes(rng, f1, dur, 1.0, bright=1.3 if parry else 1.0)
    y += blade_modes(rng, f2, dur, 0.7, damp=0.8)
    place(y, clack(rng, 0.0025, 1200, 3.0), 0)
    place(y, clack(rng, 0.006, 600, 1.2), 0.0005)
    sc = scrape(rng, 0.5, 2500, 9000, 0.015, 0.09 if parry else 0.05, 0.9 if parry else 0.5)
    # ring-modulate the scrape with a high blade mode so it sounds metallic ("shing")
    t = T(0.5)
    sc *= 0.6 + 0.4 * np.sin(2 * np.pi * f1 * 7.3 * t)
    place(y, sc, 0.003)
    y = hp(y, 180)
    return trim(soft_clip(y * 1.4, 1.2))


def armor_clank(rng, dur=0.35, amp=1.0, fmin=700, fmax=4800, n=9, damp=1.0):
    y = np.zeros(int(dur * SR))
    for _ in range(n):
        f = math.exp(rng.uniform(math.log(fmin), math.log(fmax)))
        tau = rng.uniform(0.03, 0.16) * damp * (1000 / f) ** 0.4
        y += mode(f, tau, dur, amp * rng.uniform(0.2, 1.0), rng.uniform(0, 6.28), beat=rng.uniform(1, 8), beat_amp=0.4)
    place(y, clack(rng, 0.002, 2000, amp * 1.5), 0)
    return y


def mail_rattle(rng, dur, density, amp=1.0, decay=0.08):
    """Chainmail: many tiny rings colliding."""
    y = np.zeros(int(dur * SR))
    tt = 0.0
    while tt < dur:
        rate = density * math.exp(-tt / decay)
        if rate < 5:
            break
        tt += rng.exponential(1 / rate)
        f = rng.uniform(3500, 8000)
        g = mode(f, rng.uniform(0.004, 0.018), 0.06, amp * rng.uniform(0.2, 1), rng.uniform(0, 6.28), attack=0.0002)
        place(y, g, tt)
    return y


# ---------------------------------------------------------------------------
# Flesh, bone, blood
# ---------------------------------------------------------------------------

def bubble(rng, f0=None, amp=1.0):
    """Minnaert bubble: decaying sine with a slight upward chirp."""
    f0 = f0 or rng.uniform(350, 2200)
    tau = rng.uniform(0.004, 0.02) * (900 / f0) ** 0.5
    d = tau * 6
    t = T(d)
    xi = rng.uniform(0.1, 0.5) * f0 / tau * 0.02
    ph = 2 * np.pi * (f0 * t + 0.5 * xi * t * t)
    return amp * np.sin(ph) * np.exp(-t / tau) * np.minimum(1, t / 0.0004)


def wet_grains(rng, dur, density, decay, lo=300, hi=2500, amp=1.0, bubbles=0.5):
    y = np.zeros(int(dur * SR))
    tt = 0.0
    while tt < dur:
        rate = density * math.exp(-tt / decay)
        if rate < 3:
            break
        tt += rng.exponential(1 / rate)
        if rng.random() < bubbles:
            place(y, bubble(rng, rng.uniform(lo, hi), amp * rng.uniform(0.2, 1)), tt)
        else:
            gl = rng.uniform(0.003, 0.02)
            g = bp(noise(int(gl * SR) + 64, rng), rng.uniform(lo, hi * 0.5), hi, 2)
            g *= np.hanning(len(g))
            place(y, g * amp * rng.uniform(0.3, 1.2), tt)
    return y


def thump(rng, f0=110, f1=45, tau=0.09, amp=1.0):
    t = T(tau * 6)
    f = f1 + (f0 - f1) * np.exp(-t / (tau * 0.6))
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / tau)
    s += lp(noise(len(t), rng), 300) * np.exp(-t / (tau * 0.5)) * 0.8
    return amp * s


def body_hit(seed, heavy=False):
    rng = np.random.default_rng(seed)
    dur = 0.9
    y = np.zeros(int(dur * SR))
    place(y, thump(rng, rng.uniform(95, 130), 40, 0.1 if heavy else 0.07, 1.4 if heavy else 1.0), 0)
    place(y, armor_clank(rng, 0.4, 0.4 if heavy else 0.28, 700, 3400, 7), 0)
    place(y, mail_rattle(rng, 0.3, 900 if heavy else 600, 0.1, 0.05), 0.002)
    place(y, wet_grains(rng, 0.5, 1100 if heavy else 800, 0.09, 220, 2200, 1.0, 0.45), 0.004)
    # the cut itself: a short tearing band of noise
    t = T(0.12)
    cut = bp(noise(len(t), rng), 700, 3500) * np.exp(-t / 0.035) * np.minimum(1, t / 0.004)
    place(y, cut, 0.001, 0.8 if heavy else 0.5)
    if heavy:
        for k in range(rng.integers(1, 3)):
            place(y, clack(rng, 0.003, 1800, 1.4), rng.uniform(0.005, 0.03))
    return trim(soft_clip(hp(y, 35) * 1.3, 1.1))


def sever(seed):
    rng = np.random.default_rng(seed)
    dur = 1.6
    y = np.zeros(int(dur * SR))
    place(y, thump(rng, 130, 40, 0.12, 1.5), 0)
    # bone cracks
    tt = 0.004
    for _ in range(rng.integers(3, 6)):
        place(y, clack(rng, rng.uniform(0.0015, 0.004), rng.uniform(1200, 2600), rng.uniform(1.4, 2.6)), tt)
        tt += rng.uniform(0.006, 0.03)
    # tearing sinew
    t = T(0.35)
    tear = bp(noise(len(t), rng), 500, 4000) * np.exp(-t / 0.1)
    tear *= (lp(noise(len(t), rng), 40) > 0.02) * 1.0 + 0.3
    place(y, tear, 0.02, 0.5)
    place(y, wet_grains(rng, 0.9, 1400, 0.18, 200, 2200, 0.7, 0.55), 0.01)
    place(y, mail_rattle(rng, 0.3, 1000, 0.2), 0)
    place(y, gush(rng, 0.9, 1, 0.7), 0.08)
    return trim(soft_clip(hp(y, 30) * 1.3, 1.2))


def gush(rng, dur, pulses=3, amp=1.0):
    """Arterial spray: pulsing bubble stream + liquid hiss."""
    y = np.zeros(int(dur * SR))
    t = T(dur)
    rate_hz = rng.uniform(1.8, 2.4) if pulses > 1 else 1.0
    pulse = np.clip(np.sin(2 * np.pi * rate_hz * t - 0.5), 0, None) ** 2 if pulses > 1 else np.exp(-t / (dur * 0.4))
    fade = np.exp(-t / (dur * 0.6))
    hiss = bp(noise(len(t), rng), 600, 2800) * pulse * fade * 0.1
    y += hiss
    tt = 0.0
    while tt < dur:
        i = min(int(tt * SR), len(t) - 1)
        r = 30 + 900 * pulse[i] * fade[i]
        tt += rng.exponential(1 / r)
        place(y, bubble(rng, rng.uniform(300, 1800), amp * rng.uniform(0.2, 0.9) * (0.3 + pulse[i])), tt)
    return y * amp


def spurt(seed):
    rng = np.random.default_rng(seed)
    return trim(soft_clip(hp(gush(rng, 3.0, 3, 1.0), 120) * 1.4, 1.1))


def splat(seed):
    rng = np.random.default_rng(seed)
    y = np.zeros(int(0.5 * SR))
    place(y, thump(rng, 160, 60, 0.03, 0.5), 0)
    place(y, wet_grains(rng, 0.35, 1600, 0.05, 250, 2600, 0.8, 0.6), 0)
    t = T(0.15)
    place(y, lp(noise(len(t), rng), 1800) * np.exp(-t / 0.03), 0, 0.5)
    return trim(soft_clip(y * 1.2, 1.1))


# ---------------------------------------------------------------------------
# Movement / props
# ---------------------------------------------------------------------------

def sand_crunch(rng, dur, density, amp=1.0, lo=900, hi=4500):
    y = np.zeros(int(dur * SR))
    tt = 0.0
    while tt < dur:
        e = math.sin(math.pi * tt / dur)
        tt += rng.exponential(1 / (density * (0.2 + e)))
        gl = rng.uniform(0.0008, 0.004)
        g = bp(noise(int(gl * SR) + 64, rng), lo, hi, 1) * np.hanning(int(gl * SR) + 64)
        place(y, g * amp * rng.uniform(0.2, 1.0) * e, tt)
    return y


def footstep(seed):
    rng = np.random.default_rng(seed)
    y = np.zeros(int(0.45 * SR))
    place(y, thump(rng, 90, 45, 0.025, 0.6), 0)
    place(y, sand_crunch(rng, 0.09, 1300, 0.7, 500, 2600), 0)
    place(y, sand_crunch(rng, 0.07, 1000, 0.5, 500, 2600), rng.uniform(0.08, 0.12))
    if rng.random() < 0.6:
        place(y, armor_clank(rng, 0.2, 0.08, 1200, 3800, 5, 0.6), rng.uniform(0.0, 0.03))
        place(y, mail_rattle(rng, 0.15, 400, 0.05), 0.01)
    return trim(lp(y, 3200))


def bodyfall(seed):
    rng = np.random.default_rng(seed)
    dur = 1.6
    y = np.zeros(int(dur * SR))
    place(y, thump(rng, 80, 32, 0.16, 1.6), 0)
    place(y, sand_crunch(rng, 0.35, 3500, 0.6, 400, 2500), 0)
    tt, gap, a = 0.0, rng.uniform(0.05, 0.09), 1.0
    for _ in range(rng.integers(6, 11)):
        place(y, armor_clank(rng, 0.45, 0.32 * a, 400, 3000, 8, 1.2), tt)
        tt += gap * rng.uniform(0.5, 1.5)
        gap *= 0.85
        a *= 0.78
    place(y, mail_rattle(rng, 0.8, 1200, 0.1, 0.2), 0)
    place(y, thump(rng, 70, 30, 0.1, 0.9), rng.uniform(0.18, 0.3))
    return trim(soft_clip(lp(hp(y, 25), 4500) * 1.2, 1.1))


def sword_drop(seed):
    rng = np.random.default_rng(seed)
    dur = 1.4
    y = np.zeros(int(dur * SR))
    f0 = rng.uniform(500, 800)
    tt = 0.0
    for k in range(3):
        a = [1.0, 0.45, 0.2][k]
        place(y, blade_modes(rng, f0, 1.2, 0.45 * a, damp=0.35, bright=0.8), tt)
        place(y, clack(rng, 0.003, 1500, 1.2 * a), tt)
        place(y, sand_crunch(rng, 0.08, 2500, 0.5 * a, 500, 3000), tt)
        tt += rng.uniform(0.09, 0.2) * (1 - 0.3 * k)
    return trim(soft_clip(hp(y, 120), 1.05))


def whoosh(seed, heavy=False):
    rng = np.random.default_rng(seed)
    dur = rng.uniform(0.42, 0.55) * (1.2 if heavy else 1.0)
    n = int(dur * SR)
    t = np.arange(n) / SR
    peak = rng.uniform(0.5, 0.62)
    env = np.exp(-((t / dur - peak) / (0.2 if heavy else 0.16)) ** 2)
    src = noise(n, rng)
    fc_lo, fc_hi = (180, 900) if heavy else (250, rng.uniform(1100, 1700))

    def formants(tt):
        e = math.exp(-((tt / dur - peak) / 0.2) ** 2)
        f = fc_lo + (fc_hi - fc_lo) * e
        return [(f, f * 0.7, 1.0), (f * 2.3, f * 1.2, 0.35)]

    y = resonate_blocks(src, formants, 128) * env
    # edge tone: faint whistle whose pitch follows blade speed
    fw = (260 if heavy else 380) + 380 * env
    whistle = np.sin(2 * np.pi * np.cumsum(fw) / SR) * env ** 2 * (0.06 + 0.04 * lp(noise(n, rng), 30))
    y = y / (np.max(np.abs(y)) + 1e-9) + whistle
    return fade_out(y)


# ---------------------------------------------------------------------------
# Voices
# ---------------------------------------------------------------------------

VOWELS = {  # F1..F4 (Hz) for an adult male
    "a": (730, 1090, 2440, 3400), "ah": (650, 1150, 2500, 3500), "u": (520, 1190, 2390, 3300),
    "o": (570, 840, 2410, 3300), "e": (530, 1840, 2480, 3500), "i": (300, 2200, 3000, 3700),
    "uh": (600, 1000, 2400, 3300), "ae": (660, 1720, 2410, 3400),
}


def glottal(rng, f0_curve, jitter=0.012, shimmer=0.1, open_q=0.6, fry=None):
    """Rosenberg glottal pulse train following f0_curve (array per sample)."""
    n = len(f0_curve)
    out = np.zeros(n)
    i = 0
    while i < n - 2:
        f = max(40.0, f0_curve[i] * (1 + rng.normal(0, jitter)))
        if fry is not None and fry[i] > 0.5 and rng.random() < 0.6:
            f *= rng.uniform(0.3, 0.6)
        period = int(SR / f)
        if period < 4:
            break
        to = int(period * open_q)
        tp = int(to * 0.66)
        k = np.arange(period)
        p = np.where(k < tp, 0.5 * (1 - np.cos(np.pi * k / max(tp, 1))),
                     np.where(k < to, np.cos(np.pi * (k - tp) / (2 * max(to - tp, 1))), 0.0))
        amp = 1 + rng.normal(0, shimmer)
        seg = p[:max(0, min(period, n - i))] * amp
        out[i:i + len(seg)] += seg
        i += period
    d = np.diff(out, prepend=0)  # radiation (lip) filter
    return d


def helmet(y, amount=1.0):
    """Muffle as if shouted inside a closed steel helm: comb resonance + lowpass."""
    d = int(0.0011 * SR)
    out = y.copy()
    for k in range(1, 4):
        out[d * k:] += y[:-d * k] * (0.45 ** k) * amount
    return lp(out, 3200 - 700 * amount, 2)


def voice(seed, kind):
    rng = np.random.default_rng(seed)
    specs = {
        "grunt": dict(d=rng.uniform(0.2, 0.32), f=(rng.uniform(125, 160), rng.uniform(85, 110)), v=("uh", "u"), breath=0.25, rough=0.02),
        "effort": dict(d=rng.uniform(0.16, 0.26), f=(rng.uniform(150, 190), rng.uniform(120, 145)), v=("ah", "uh"), breath=0.45, rough=0.015),
        "pain": dict(d=rng.uniform(0.45, 0.7), f=(rng.uniform(220, 280), rng.uniform(120, 150)), v=("a", "ah"), breath=0.2, rough=0.03),
        "scream": dict(d=rng.uniform(1.0, 1.4), f=(rng.uniform(300, 380), rng.uniform(160, 210)), v=("a", "ae"), breath=0.15, rough=0.045),
        "death": dict(d=rng.uniform(1.2, 1.6), f=(rng.uniform(210, 260), rng.uniform(70, 90)), v=("ah", "o"), breath=0.3, rough=0.05),
    }
    s = specs[kind]
    n = int(s["d"] * SR)
    t = np.arange(n) / n
    f0a, f0b = s["f"]
    if kind == "scream":
        contour = f0a * (1 + 0.12 * np.sin(np.pi * np.minimum(t * 1.6, 1))) * (1 - t) + f0b * t
    else:
        contour = f0a + (f0b - f0a) * t ** 0.7
    contour *= 1 + 0.02 * np.sin(2 * np.pi * 5.5 * np.arange(n) / SR)
    fry = (t > 0.8).astype(float) if kind in ("grunt", "death", "pain") else None
    src = glottal(rng, contour, jitter=s["rough"], shimmer=0.12, fry=fry)
    src += hp(noise(n, rng), 800) * s["breath"] * 0.05
    va, vb = VOWELS[s["v"][0]], VOWELS[s["v"][1]]
    tilt = 1.0 if kind == "scream" else 0.6

    def formants(tt):
        k = min(1.0, tt / s["d"])
        F = [va[i] + (vb[i] - va[i]) * k for i in range(4)]
        return [(F[0], 90, 1.0), (F[1], 110, 0.7 * tilt + 0.2), (F[2], 170, 0.35 * tilt), (F[3], 250, 0.18 * tilt)]

    y = resonate_blocks(src, formants, 256)
    env = np.minimum(1, np.arange(n) / (0.03 * SR)) * np.minimum(1, (n - np.arange(n)) / (0.12 * SR))
    if kind == "death":
        y *= np.exp(-t * 1.5)
        g = gush(rng, s["d"], 1, 0.12)
        y = y / (np.max(np.abs(y)) + 1e-9) + g[:n] * np.linspace(0, 1, n)
    y = helmet(y * env, 0.85)
    return trim(soft_clip(hp(y, 70) * 1.6, 1.3))


# ---------------------------------------------------------------------------
# Crowd, drums, fire
# ---------------------------------------------------------------------------

def babble_voice(rng, dur, f0_base, loud=0.6, cheer=False):
    """One spectator: syllables of random vowels with pauses."""
    n = int(dur * SR)
    y = np.zeros(n)
    tt = rng.uniform(0, 0.8)
    while tt < dur:
        syl = rng.uniform(0.12, 0.3) if not cheer else rng.uniform(0.5, 1.6)
        m = int(syl * SR)
        f0 = f0_base * rng.uniform(0.85, 1.25) * (1.35 if cheer else 1.0)
        c = f0 * (1 + (0.25 if cheer else 0.08) * np.sin(np.linspace(0, np.pi, m)))
        src = glottal(rng, c, 0.02, 0.15)
        v = VOWELS[rng.choice(list(VOWELS))] if not cheer else VOWELS[rng.choice(["a", "o", "ah", "ae"])]
        fl = [(v[0], 100, 1), (v[1], 130, 0.6), (v[2], 200, 0.3)]
        seg = resonate_blocks(src, lambda _t: fl, 512) * np.hanning(m)
        place(y, seg * rng.uniform(0.4, 1.0) * loud, tt)
        tt += syl + (rng.exponential(0.25) if not cheer else rng.uniform(0.0, 0.3))
    return y


def claps(rng, dur, count, env_fn):
    y = np.zeros(int(dur * SR))
    for _ in range(count):
        tt = rng.uniform(0, dur)
        g = env_fn(tt)
        if rng.random() > g:
            continue
        m = int(0.03 * SR)
        c = bp(noise(m, rng), rng.uniform(800, 1400), rng.uniform(2200, 3500)) * np.exp(-np.arange(m) / (0.004 * SR))
        place(y, c * rng.uniform(0.3, 1.0), tt)
    return y


def stereo_mix(rng, tracks, dur):
    L = np.zeros(int(dur * SR))
    R = np.zeros(int(dur * SR))
    for tr in tracks:
        p = rng.uniform(-0.9, 0.9)
        d = int(rng.uniform(0, 0.03) * SR)
        a = np.roll(tr, d)
        L += a * math.cos((p + 1) * math.pi / 4)
        R += a * math.sin((p + 1) * math.pi / 4)
    return np.stack([L, R])


def room(x, rng, rt=1.6, wet=0.35):
    """Cheap stereo reverb by convolving with decaying noise."""
    n = int(rt * SR)
    ir = rng.standard_normal((2, n)) * np.exp(-np.arange(n) / (rt * SR / 6.9))
    ir = np.stack([lp(ir[0], 5000), lp(ir[1], 5000)])
    out = np.stack([signal.fftconvolve(x[c], ir[c])[:x.shape[1]] for c in range(2)])
    out = out / (np.max(np.abs(out)) + 1e-9) * np.max(np.abs(x))
    return x * (1 - wet) + out * wet


def loopify(x, xf=1.0):
    n = int(xf * SR)
    head = x[..., :n].copy()
    body = x[..., n:].copy()
    w = np.linspace(0, 1, n)
    body[..., -n:] = body[..., -n:] * (1 - w) + head * w
    return body


def crowd_loop(seed):
    rng = np.random.default_rng(seed)
    dur = 11.0
    tracks = [babble_voice(rng, dur, rng.uniform(95, 200), rng.uniform(0.3, 0.8)) for _ in range(34)]
    st = stereo_mix(rng, tracks, dur)
    rumble = lp(noise(int(dur * SR), rng), 350) * 0.6
    st += np.stack([rumble, np.roll(rumble, 900)])
    st = room(st, rng, 2.2, 0.55)
    st = np.stack([lp(hp(c, 90), 3500) for c in st])
    return loopify(st, 1.0)


def cheer(seed, big=False):
    rng = np.random.default_rng(seed)
    dur = 4.0 if big else 3.2
    tracks = []
    for _ in range(40 if big else 28):
        v = babble_voice(rng, dur, rng.uniform(110, 230), 1.0, cheer=True)
        start = rng.uniform(0.0, 0.35)
        env = np.clip((np.arange(len(v)) / SR - start) / 0.25, 0, 1) * np.exp(-np.maximum(0, np.arange(len(v)) / SR - 1.2) / (1.4 if big else 1.0))
        tracks.append(v * env)
    st = stereo_mix(rng, tracks, dur)
    cl = claps(rng, dur, 2600 if big else 1600, lambda tt: min(1, tt / 0.4) * math.exp(-max(0, tt - 1.0) / 1.2))
    st += np.stack([cl, np.roll(cl, 700)]) * 0.8
    roar = lp(noise(int(dur * SR), rng), 900) * np.exp(-np.maximum(0, np.arange(int(dur * SR)) / SR - 0.8) / 1.0) * np.minimum(1, np.arange(int(dur * SR)) / (0.3 * SR))
    st += np.stack([roar, np.roll(roar, 500)]) * 0.5
    st = room(st, rng, 2.4, 0.5)
    for c in range(2):
        st[c] = fade_out(hp(st[c], 80), 0.3)
    return st


def drum(seed, big=False):
    rng = np.random.default_rng(seed)
    dur = 1.6
    t = T(dur)
    f0 = rng.uniform(62, 75) if big else rng.uniform(85, 100)
    y = np.zeros(len(t))
    for r, a, tau in ((1.0, 1.0, 0.45), (1.594, 0.5, 0.25), (2.136, 0.3, 0.18), (2.296, 0.25, 0.15), (2.653, 0.18, 0.12), (2.918, 0.12, 0.1)):
        f = f0 * r * (1 + 0.25 * np.exp(-t / 0.03))
        y += a * np.sin(2 * np.pi * np.cumsum(f) / SR + rng.uniform(0, 6)) * np.exp(-t / tau)
    y += lp(noise(len(t), rng), 2500) * np.exp(-t / 0.012) * 0.8
    y += bp(noise(len(t), rng), 150, 600) * np.exp(-t / 0.2) * 0.2
    return trim(soft_clip(y * 1.5, 1.2))


def fire_loop(seed):
    rng = np.random.default_rng(seed)
    dur = 7.0
    n = int(dur * SR)
    base = lp(noise(n, rng), 500) * 0.5 + bp(noise(n, rng), 800, 3000) * 0.08 * (1 + lp(noise(n, rng), 3) * 3)
    y = base
    tt = 0.0
    while tt < dur:
        tt += rng.exponential(1 / 14)
        pop = hp(noise(400, rng), rng.uniform(1500, 4000)) * np.exp(-np.arange(400) / rng.uniform(15, 60))
        place(y, pop * rng.uniform(0.2, 1.3) ** 2, tt)
    st = np.stack([y, np.roll(y, 1300)])
    return loopify(st, 0.8)


def guard_break(seed):
    rng = np.random.default_rng(seed)
    y = steel_clash(seed, parry=True)
    t = np.arange(len(y)) / SR
    wob = 1 + 0.5 * np.sin(2 * np.pi * 9 * t) * np.exp(-t / 0.4)
    y = y * wob
    place(y, thump(rng, 120, 50, 0.08, 0.8), 0)
    return trim(y)


def fireball_cast(seed):
    """Ignition whoomph: a rising roar of filtered noise over a sub thump, with crackle."""
    rng = np.random.default_rng(seed)
    dur = 1.3
    n = int(dur * SR)
    t = np.arange(n) / SR
    env = np.minimum(1, t / 0.08) * np.exp(-np.maximum(0, t - 0.15) / 0.35)

    def formants(tt):
        f = 250 + 1400 * min(1.0, tt / 0.25) * math.exp(-max(0.0, tt - 0.25) / 0.5)
        return [(f, f * 0.9, 1.0), (f * 2.2, f * 1.4, 0.4)]

    roar = resonate_blocks(noise(n, rng), formants, 128)
    roar = roar / (np.max(np.abs(roar)) + 1e-9) * env
    y = roar
    place(y, thump(rng, 90, 35, 0.12, 0.9), 0)
    tt = 0.02
    while tt < 0.9:
        tt += rng.exponential(1 / 40)
        pop = hp(noise(300, rng), rng.uniform(1500, 4000)) * np.exp(-np.arange(300) / rng.uniform(10, 40))
        place(y, pop * rng.uniform(0.1, 0.6) * math.exp(-tt / 0.4), tt)
    return trim(soft_clip(hp(y, 40) * 1.3, 1.2))


def explosion(seed):
    rng = np.random.default_rng(seed)
    dur = 2.4
    n = int(dur * SR)
    t = np.arange(n) / SR
    y = np.zeros(n)
    f = 28 + 60 * np.exp(-t / 0.08)
    y += np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.35) * 1.4
    body = lp(noise(n, rng), 900) * np.exp(-t / 0.5) * np.minimum(1, t / 0.004)
    y += body * 1.2
    y += bp(noise(n, rng), 1500, 7000) * np.exp(-t / 0.06) * 0.8
    tt = 0.05
    while tt < 1.8:  # debris and flame crackle tail
        tt += rng.exponential(1 / 30)
        pop = hp(noise(400, rng), rng.uniform(800, 3500)) * np.exp(-np.arange(400) / rng.uniform(15, 60))
        place(y, pop * rng.uniform(0.1, 0.7) * math.exp(-tt / 0.6), tt)
    place(y, sand_crunch(rng, 0.6, 2500, 0.4, 400, 2500), 0.05)
    return trim(soft_clip(y * 1.4, 1.6))


def burn_loop(seed):
    rng = np.random.default_rng(seed)
    dur = 4.0
    n = int(dur * SR)
    roar = lp(noise(n, rng), 700) * (0.7 + 0.3 * lp(noise(n, rng), 4) * 4)
    y = roar + bp(noise(n, rng), 1000, 4000) * 0.12
    tt = 0.0
    while tt < dur:
        tt += rng.exponential(1 / 22)
        pop = hp(noise(400, rng), rng.uniform(1500, 4500)) * np.exp(-np.arange(400) / rng.uniform(12, 50))
        place(y, pop * rng.uniform(0.2, 1.1) ** 2, tt)
    return loopify(y, 0.5)


def kick_hit(seed):
    rng = np.random.default_rng(seed)
    y = np.zeros(int(0.8 * SR))
    place(y, thump(rng, 120, 45, 0.09, 1.5), 0)
    place(y, armor_clank(rng, 0.5, 0.6, 500, 3200, 9, 1.0), 0.002)
    place(y, mail_rattle(rng, 0.3, 900, 0.12, 0.08), 0.004)
    return trim(soft_clip(lp(y, 6000) * 1.2, 1.2))


# ---------------------------------------------------------------------------

def main():
    jobs = [
        ("clash", 6, lambda i: steel_clash(100 + i)),
        ("parry", 3, lambda i: steel_clash(200 + i, parry=True)),
        ("guardbreak", 2, lambda i: guard_break(250 + i)),
        ("whoosh", 6, lambda i: whoosh(300 + i)),
        ("whooshheavy", 3, lambda i: whoosh(350 + i, heavy=True)),
        ("hit", 6, lambda i: body_hit(400 + i)),
        ("hitheavy", 4, lambda i: body_hit(450 + i, heavy=True)),
        ("sever", 4, lambda i: sever(500 + i)),
        ("spurt", 3, lambda i: spurt(550 + i)),
        ("splat", 5, lambda i: splat(600 + i)),
        ("bodyfall", 3, lambda i: bodyfall(650 + i)),
        ("swordrop", 3, lambda i: sword_drop(700 + i)),
        ("step", 8, lambda i: footstep(750 + i)),
        ("grunt", 5, lambda i: voice(800 + i, "grunt")),
        ("effort", 5, lambda i: voice(850 + i, "effort")),
        ("pain", 5, lambda i: voice(900 + i, "pain")),
        ("scream", 4, lambda i: voice(950 + i, "scream")),
        ("death", 4, lambda i: voice(1000 + i, "death")),
        ("drum", 2, lambda i: drum(1050 + i, big=(i == 0))),
        ("fireball", 3, lambda i: fireball_cast(1400 + i)),
        ("explosion", 3, lambda i: explosion(1450 + i)),
        ("kick", 3, lambda i: kick_hit(1500 + i)),
    ]
    for name, count, fn in jobs:
        for i in range(count):
            write(f"{name}_{i}", fn(i), peak=0.8 if name in ("step", "whoosh", "whooshheavy") else 0.89)
        print("rendered", name, count)
    write("crowd_0", crowd_loop(1100), stereo=True, peak=0.7)
    write("cheer_0", cheer(1200), stereo=True, peak=0.85)
    write("cheer_1", cheer(1201), stereo=True, peak=0.85)
    write("cheerbig_0", cheer(1250, big=True), stereo=True, peak=0.9)
    write("fire_0", fire_loop(1300), stereo=True, peak=0.6)
    write("burn_0", burn_loop(1350), peak=0.7)
    print("rendered ambience")
    with open(os.path.join(OUT, "manifest.json"), "w") as fh:
        json.dump(MANIFEST, fh, indent=1, sort_keys=True)
    total = sum(os.path.getsize(os.path.join(OUT, f)) for f in os.listdir(OUT))
    print("total", total // 1024, "KB in", len(os.listdir(OUT)), "files")


if __name__ == "__main__":
    main()
