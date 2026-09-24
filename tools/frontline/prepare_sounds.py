"""Convert recorded sound effects from Xonotic (GPLv3+) into small web-ready WAV files.

Source: https://github.com/xonotic/xonotic-data.pk3dir (sound/weapons, sound/object, sound/misc)
License: GNU GPL v3 or later (see assets/frontline/sounds/README.md and GPL-3.0.txt)

Each clip is mixed to mono, resampled to 32 kHz, trimmed of leading silence, cut to a
maximum length with a short fade-out, peak-normalized and written as 16-bit PCM WAV
(WAV plays in every browser, including older iOS Safari that can't decode Ogg).

Usage: python3 prepare_sounds.py <xonotic-data.pk3dir> <out_dir>
"""
import os
import sys
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
from math import gcd

SRC, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)
RATE = 32000

# out name -> (source file, start s, max length s, gain)
CLIPS = {
    "rifle_shot": ("sound/weapons/uzi_fire.ogg", 0, 1.0, 1.0),
    "dmr_shot": ("sound/weapons/campingrifle_fire2.ogg", 0, 2.2, 1.0),
    "sniper_far": ("sound/weapons/campingrifle_fire.ogg", 0, 3.4, 1.0),
    "shotgun_shot": ("sound/weapons/shotgun_fire.ogg", 0, 1.4, 1.0),
    "reload_out": ("sound/weapons/reload.ogg", 0.08, 1.0, 1.0),
    "reload_in": ("sound/weapons/reload.ogg", 1.22, 0.72, 1.0),
    "dryfire": ("sound/weapons/dryfire.wav", 0, 0.25, 0.9),
    "impact_stone_1": ("sound/object/impact_stone_1.ogg", 0, 0.7, 0.9),
    "impact_stone_2": ("sound/object/impact_stone_2.ogg", 0, 0.7, 0.9),
    "impact_stone_3": ("sound/object/impact_stone_3.ogg", 0, 0.7, 0.9),
    "impact_stone_4": ("sound/object/impact_stone_4.ogg", 0, 0.7, 0.9),
    "impact_metal_1": ("sound/object/impact_metal_1.ogg", 0, 0.7, 0.9),
    "impact_metal_2": ("sound/object/impact_metal_2.ogg", 0, 0.7, 0.9),
    "impact_metal_3": ("sound/object/impact_metal_3.ogg", 0, 0.7, 0.9),
    "impact_wood_1": ("sound/object/impact_wood_1.ogg", 0, 0.6, 0.9),
    "impact_wood_2": ("sound/object/impact_wood_2.ogg", 0, 0.6, 0.9),
    "impact_wood_3": ("sound/object/impact_wood_3.ogg", 0, 0.6, 0.9),
    "impact_flesh_1": ("sound/object/impact_flesh_1.ogg", 0, 0.5, 0.9),
    "impact_flesh_2": ("sound/object/impact_flesh_2.ogg", 0, 0.5, 0.9),
    "impact_flesh_3": ("sound/object/impact_flesh_3.ogg", 0, 0.5, 0.9),
    "body_1": ("sound/misc/bodyimpact1.wav", 0, 0.2, 0.9),
    "body_2": ("sound/misc/bodyimpact2.wav", 0, 0.2, 0.9),
    "ric_1": ("sound/weapons/ric1.ogg", 0, 1.2, 0.8),
    "ric_2": ("sound/weapons/ric2.ogg", 0, 1.2, 0.8),
    "ric_3": ("sound/weapons/ric3.ogg", 0, 0.8, 0.8),
    "casing_1": ("sound/weapons/casings1.ogg", 0, 0.7, 0.8),
    "casing_2": ("sound/weapons/casings2.ogg", 0, 0.8, 0.8),
    "casing_3": ("sound/weapons/casings3.ogg", 0, 0.7, 0.8),
}
for i in range(1, 7):
    CLIPS[f"step_{i}"] = (f"sound/misc/footstep0{i}.ogg", 0, 0.3, 1.0)

for name, (src, start, length, gain) in CLIPS.items():
    data, sr = sf.read(os.path.join(SRC, src), always_2d=True)
    x = data.mean(1)
    g = gcd(RATE, sr)
    if sr != RATE:
        x = resample_poly(x, RATE // g, sr // g)
    x = x[int(start * RATE):]
    # trim leading silence (keep 2 ms before the first transient)
    thr = np.abs(x).max() * 0.02
    first = int(np.argmax(np.abs(x) > thr))
    x = x[max(0, first - int(0.002 * RATE)):]
    x = x[: int(length * RATE)]
    fade = min(len(x) // 3, int(0.06 * RATE))
    x[-fade:] *= np.linspace(1, 0, fade) ** 2
    x = x / (np.abs(x).max() + 1e-9) * 0.89 * gain
    sf.write(os.path.join(OUT, name + ".wav"), x.astype(np.float32), RATE, subtype="PCM_16")
    print(f"{name:16s} {len(x) / RATE:5.2f}s  <- {src}")
