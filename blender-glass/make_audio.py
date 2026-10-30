# Synthesises the lava-knife ASMR track from events.json (written by build_scene.py).
# Run with Blender's bundled Python (has numpy):  python make_audio.py events.json out.wav
import json, sys, wave
import numpy as np

events = json.load(open(sys.argv[1]))
T, liquid, cut = events['T'], events['liquid'], np.array(events['cut'])
SR, DUR = 48000, 8.0
N = int(SR * DUR)
L, R = np.zeros(N), np.zeros(N)
rng = np.random.default_rng(2024)
MS = int(DUR * 1000)


# ---------------------------------------------------------------- building blocks
def add(i0, sig, pan=0.0):
    a = (pan + 1) * np.pi / 4
    i1 = min(N, i0 + len(sig))
    if i0 < 0 or i1 <= i0: return
    L[i0:i1] += sig[:i1 - i0] * np.cos(a)
    R[i0:i1] += sig[:i1 - i0] * np.sin(a)


def lowpass(x, k):    # one-pole low-pass, small k = darker
    y = np.zeros_like(x); acc = 0.0
    for i, v in enumerate(x):
        acc += k * (v - acc); y[i] = acc
    return y


def bandpass(x, f0, Q):
    w0 = 2 * np.pi * f0 / SR; al = np.sin(w0) / (2 * Q)
    b0, b2, a0, a1, a2 = al, -al, 1 + al, -2 * np.cos(w0), 1 - al
    y = np.zeros_like(x); x1 = x2 = y1 = y2 = 0.0
    for i, v in enumerate(x):
        yi = (b0 * v + b2 * x2 - a1 * y1 - a2 * y2) / a0
        x2, x1, y2, y1 = x1, v, y1, yi; y[i] = yi
    return y


def env_ms(points):
    """Piecewise-linear per-millisecond envelope from (time, value) points."""
    ts, vs = zip(*points)
    return np.interp(np.arange(MS) / 1000, ts, vs)


def noise_layer(env, f0, Q, gain, pan=0.0, flutter=0.0):
    """Band-passed noise shaped by a per-ms envelope; flutter adds a lively, uneven texture."""
    e = np.repeat(env, SR // 1000)[:N]
    if flutter:
        wob = np.repeat(np.clip(1 + flutter * np.convolve(rng.normal(0, 1, MS), np.ones(30) / 6, 'same'), 0.15, 2.0), SR // 1000)[:N]
        e = e * wob
    active = np.nonzero(e > 1e-4)[0]
    if not len(active): return
    i0, i1 = active[0], active[-1] + 1
    add(i0, bandpass(rng.uniform(-1, 1, i1 - i0), f0, Q) * e[i0:i1] * gain, pan)


def thud(t, amp, f0=130, decay=0.07, pan=0.0):
    n = int(decay * SR * 6); k = np.arange(n)
    f = f0 * (1 + 0.7 * np.exp(-k / (0.012 * SR)))
    body = np.sin(np.cumsum(2 * np.pi * f / SR))
    add(int(t * SR), (body * 0.8 + lowpass(rng.uniform(-1, 1, n), 0.08) * 1.5) * np.exp(-k / (decay * SR)) * amp * np.minimum(1, k / 48), pan)


def knock(t, amp, f0=620, pan=0.0):
    """Short wooden knock: damped mid tone with a soft click."""
    n = int(0.05 * SR); k = np.arange(n)
    tone = np.sin(2 * np.pi * f0 * k / SR) * np.exp(-k / (0.008 * SR))
    add(int(t * SR), (tone + lowpass(rng.uniform(-1, 1, n), 0.3) * np.exp(-k / (0.002 * SR))) * amp, pan)


def tick(t, amp, pan=0.0):
    """Soft, rounded contact tick of metal on a glossy skin."""
    n = int(0.012 * SR); k = np.arange(n)
    add(int(t * SR), np.sin(2 * np.pi * 2400 * k / SR) * np.exp(-k / (0.0015 * SR)) * amp, pan)


def squish(t, amp, dur=0.1, k=0.05, pan=0.0):
    n = int(dur * SR); u = np.arange(n) / n
    env = np.sin(np.pi * np.minimum(1, u * 4)) * np.exp(-u * 4)
    add(int(t * SR), lowpass(rng.uniform(-1, 1, n), k) * env * amp * 6, pan)


def tack(t, amp, pan=0.0):
    n = int(0.04 * SR); k = np.arange(n)
    blip = np.sin(np.cumsum(2 * np.pi * (900 - 500 * k / n) / SR)) * np.exp(-k / (0.008 * SR))
    add(int(t * SR), blip * amp, pan)
    squish(t, amp * 0.6, 0.06, 0.12, pan)


def plop(t, amp, pan=0.0):
    n = int(0.07 * SR); k = np.arange(n)
    f = 420 * np.exp(-k / (0.02 * SR)) + 140
    add(int(t * SR), np.sin(np.cumsum(2 * np.pi * f / SR)) * np.exp(-k / (0.015 * SR)) * amp, pan)
    squish(t, amp * 0.5, 0.08, 0.06, pan)


def pop(t, amp, decay_ms, pan, bright=True):
    """A single sizzle crackle; bright = fat spitting, dark = charring wood."""
    tau = decay_ms / 1000 * SR; n = int(tau * 6) + 1
    x = rng.uniform(-1, 1, n) * np.exp(-np.arange(n) / tau)
    add(int(t * SR), (np.diff(x, prepend=0.0) if bright else lowpass(x, 0.25)) * amp, pan)


def crackles(density_env, amp, decay=(0.2, 0.8), bright=True, spread=0.4):
    for ms in range(MS):
        d = density_env[ms]
        if d > 0 and rng.random() < d / 1000:
            pop(ms / 1000 + rng.random() / 1000, amp * rng.uniform(0.3, 1.0), rng.uniform(*decay), rng.uniform(-spread, spread), bright)


# ---------------------------------------------------------------- the track
touch, cut_end, lift0, lift1 = T['touch'], T['cutEnd'], T['lift0'], T['lift1']

# soft room tone
add(0, lowpass(rng.uniform(-1, 1, N), 0.02) * 0.01)

# the hot blade approaching: faint warm crackle of hot metal, building anticipation
approach = env_ms([(0, 0), (T['approach0'], 0.15), (touch - 0.05, 0.6), (touch, 0.6), (touch + 0.01, 0), (DUR, 0)])
noise_layer(approach, 900, 0.7, 0.012, flutter=0.4)
crackles(approach * 6, 0.05, (0.3, 1.0), bright=False)

# FIRST TOUCH: soft contact tick, then a sharp sear burst ("tssshh") with a steam puff and sputter
tick(touch, 0.18, 0.1)
sear = env_ms([(0, 0), (touch, 0), (touch + 0.006, 1.0), (touch + 0.15, 0.7), (touch + 0.7, 0.32), (DUR, 0.32)])
sear[int(cut_end * 1000):] = 0
noise_layer(sear, 5200, 0.8, 0.09, -0.05, flutter=0.35)
noise_layer(sear, 2600, 0.9, 0.035, 0.05, flutter=0.35)
squish(touch + 0.01, 0.12, 0.35, 0.03)                         # low "fwump" of steam
burst = env_ms([(0, 0), (touch, 0), (touch + 0.01, 260), (touch + 0.5, 30), (DUR, 30)])
burst[int(cut_end * 1000):] = 0
crackles(burst, 0.16, (0.15, 0.6))

# CUTTING: a smooth, warm swish that follows the blade, over a gentle sizzle and a juicy melt
speed = np.clip(cut[:, 0] / 0.02, 0, 1)
glide = speed * cut[:, 2]
noise_layer(glide, 1200, 0.55, 0.11)          # body of the swish
noise_layer(glide, 3000, 0.8, 0.03)           # soft air on top
noise_layer(glide, 380, 0.7, 0.05)            # warm, wet undertone
for ms in range(int(touch * 1000), int(cut_end * 1000)):
    if rng.random() < (5 + 30 * glide[ms]) / 1000:
        squish(ms / 1000, rng.uniform(0.02, 0.05) * (0.4 + glide[ms]), 0.04, 0.12, rng.uniform(-0.3, 0.3))

# THE BOARD: a solid wooden "tok", then the hot edge scorches the wood (short hiss and charring crackle)
thud(cut_end, 0.22, 110, 0.07)
knock(cut_end, 0.25, 640)
scorch = env_ms([(0, 0), (cut_end, 0), (cut_end + 0.008, 0.9), (cut_end + 0.45, 0.25), (lift0, 0.2), (lift1 + 0.6, 0), (DUR, 0)])
noise_layer(scorch, 4200, 0.8, 0.07, flutter=0.4)
noise_layer(scorch, 1800, 0.9, 0.025, flutter=0.4)
crackles(scorch * 140, 0.14, (0.4, 1.4), bright=False, spread=0.3)
crackles(scorch * 60, 0.1, (0.15, 0.5))

# AFTER: the halves peel apart, the melted filling glugs out, strands snap and drip, embers tick
squish(T['slide0'] + 0.05, 0.16, 0.25, 0.05, -0.2)
noise_layer(env_ms([(0, 0), (T['slide0'] + 0.2, 0), (T['slide0'] + 0.8, 1), (DUR - 0.5, 0.5), (DUR, 0.2)]), 260, 0.8, 0.07)
for t in np.sort(rng.uniform(T['slide0'] + 0.4, DUR - 0.2, 7)):
    squish(t, rng.uniform(0.05, 0.1), rng.uniform(0.1, 0.2), 0.04, rng.uniform(-0.3, 0.3))
for e in liquid:
    p = rng.uniform(-0.4, 0.4)
    if e['kind'] == 'snap': tack(e['t'], 0.05 + e['size'] * 40, p)
    else: plop(e['t'], 0.08 + e['size'] * 50, p)
embers = env_ms([(0, 0), (lift1, 0), (lift1 + 0.3, 12), (DUR, 4)])
crackles(embers, 0.05, (0.2, 0.6), bright=False)

# ---------------------------------------------------------------- polish: small room, soft top end, level
dry_L, dry_R = L.copy(), R.copy()
for ms, g, side in ((23, 0.18, 0), (31, 0.15, 1), (41, 0.12, 0), (53, 0.1, 1), (67, 0.07, 0), (79, 0.05, 1)):
    d = int(ms / 1000 * SR)
    (L if side == 0 else R)[d:] += (dry_R if side == 0 else dry_L)[:-d] * g
L, R = lowpass(L, 0.72), lowpass(R, 0.72)                       # roll off harshness above ~10 kHz
peak = max(np.abs(L).max(), np.abs(R).max())
L, R = np.tanh(L / peak * 2.6), np.tanh(R / peak * 2.6)        # gentle compression: the cut sits forward
g = 0.89 / max(np.abs(L).max(), np.abs(R).max())
pcm = (np.stack([L, R], 1) * g * 32767).astype('<i2')
with wave.open(sys.argv[2], 'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
print('AUDIO OK', len(liquid), 'liquid events')
