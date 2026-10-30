// Synthesises the glass-cutting ASMR soundtrack from the scene's timeline and shard impacts.
const fs = require('fs');

function mulberry32(a) { return function () { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }

module.exports = function buildAudio(data, file, dur = 8, sr = 48000) {
  const { T, impacts, scrape } = data;
  const { seed = 99, pitch = 1, style = 'glass' } = data.audio || {};
  const N = Math.ceil(dur * sr);
  const L = new Float32Array(N), R = new Float32Array(N);
  const rng = mulberry32(seed);
  const add = (i, v, pan) => {
    if (i < 0 || i >= N) return;
    const a = (pan + 1) * Math.PI / 4;
    L[i] += v * Math.cos(a); R[i] += v * Math.sin(a);
  };

  // tiny high-passed noise burst: one glass grain cracking
  function click(t, amp, decayMs = 1.5, hp = 0.85, pan = 0) {
    const i0 = Math.round(t * sr), tau = decayMs / 1000 * sr, n = Math.round(tau * 6);
    let px = 0, y = 0;
    for (let k = 0; k < n; k++) {
      const x = (rng() * 2 - 1) * Math.exp(-k / tau);
      y = hp * (y + x - px); px = x;
      add(i0 + k, y * amp, pan);
    }
  }
  // inharmonic glass resonance
  function ting(t, f, amp, decay = 0.25, pan = 0) {
    f *= pitch;
    const ratios = [1, 2.32, 4.25, 6.63], i0 = Math.round(t * sr), n = Math.round(decay * sr * 5);
    const det = ratios.map(r => r * (1 + (rng() - 0.5) * 0.02));
    for (let k = 0; k < n; k++) {
      let s = 0;
      for (let j = 0; j < det.length; j++) s += Math.sin(2 * Math.PI * f * det[j] * k / sr) * Math.exp(-k / (decay / (1 + j * 0.8) * sr)) / (1 + j);
      add(i0 + k, s * amp * Math.min(1, k / (0.001 * sr)), pan);
    }
  }
  // low thump (knife on wood, fruit landing)
  function thud(t, amp, f0 = 140, decay = 0.07, pan = 0) {
    f0 *= Math.sqrt(pitch);
    const i0 = Math.round(t * sr), n = Math.round(decay * sr * 6);
    let ph = 0, lp = 0;
    for (let k = 0; k < n; k++) {
      const f = f0 * (1 + 0.7 * Math.exp(-k / (0.012 * sr)));
      ph += 2 * Math.PI * f / sr;
      lp += 0.08 * ((rng() * 2 - 1) - lp);
      const env = Math.exp(-k / (decay * sr));
      add(i0 + k, (Math.sin(ph) * 0.8 + lp * 1.5) * env * amp * Math.min(1, k / 48), pan);
    }
  }

  // room tone
  { let lp = 0; for (let i = 0; i < N; i++) { lp += 0.02 * ((rng() * 2 - 1) - lp); add(i, lp * 0.01, 0); } }

  // band-passed noise layer whose loudness follows the knife speed
  function bandNoise(f0, Q, gain, env = scrape) {
    const w0 = 2 * Math.PI * f0 / sr, al = Math.sin(w0) / (2 * Q);
    const b0 = al, b2 = -al, a0 = 1 + al, a1 = -2 * Math.cos(w0), a2 = 1 - al;
    let x1 = 0, x2 = 0, y1 = 0, y2 = 0;
    for (let i = 0; i < N; i++) {
      const s = env[Math.floor(i / sr * 1000)] || 0;
      const x = rng() * 2 - 1;
      const y = (b0 * x + b2 * x2 - a1 * y1 - a2 * y2) / a0;
      x2 = x1; x1 = x; y2 = y1; y1 = y;
      add(i, y * s * gain, 0);
    }
  }
  // soft low-passed noise burst (wet, sticky)
  function squish(t, amp, dur = 0.1, cutoff = 0.05, pan = 0) {
    const i0 = Math.round(t * sr), n = Math.round(dur * sr);
    let lp = 0;
    for (let k = 0; k < n; k++) {
      lp += cutoff * ((rng() * 2 - 1) - lp);
      const u = k / n, env = Math.sin(Math.PI * Math.min(1, u * 4)) * Math.exp(-u * 4);
      add(i0 + k, lp * env * amp * 6, pan);
    }
  }
  // a sticky strand letting go: short falling blip plus a wet tail
  function tack(t, amp, pan = 0) {
    const i0 = Math.round(t * sr), n = Math.round(0.04 * sr);
    let ph = 0;
    for (let k = 0; k < n; k++) {
      ph += 2 * Math.PI * (900 - 500 * k / n) / sr;
      add(i0 + k, Math.sin(ph) * Math.exp(-k / (0.008 * sr)) * amp, pan);
    }
    squish(t, amp * 0.6, 0.06, 0.12, pan);
  }

  if (style === 'apple') {
    // crunch intensity = knife speed x how much flesh the edge is in, so the sound tracks the picture
    const I = scrape.map((s, i) => s * (data.width ? data.width[i] : 1));
    click(T.touch, 0.05, 0.6, 0.6);                 // blade settles on the skin
    squish(T.touch, 0.05, 0.08, 0.1);              // sticky honey contact
    for (let i = 0; i < 14; i++) click(T.skinBreak + rng() * 0.025, 0.25 + rng() * 0.45, 0.4 + rng() * 1.2, 0.6 + rng() * 0.25, (rng() - 0.5) * 0.3);
    thud(T.skinBreak, 0.12, 260, 0.025);           // skin gives way
    for (let ms = Math.floor(T.touch * 1000); ms < T.cutEnd * 1000; ms++) {
      const v = I[ms] || 0, t = ms / 1000;
      if (rng() < (60 + 1100 * v) / 1000) click(t + rng() / 1000, (0.06 + rng() * 0.28) * (0.4 + 0.6 * v), 0.25 + rng() * 1.1, 0.55 + rng() * 0.3, (rng() - 0.5) * 0.35);
      if (rng() < (4 + 30 * v) / 1000) click(t, (0.3 + rng() * 0.4) * (0.5 + 0.5 * v), 1.2 + rng() * 2, 0.35 + rng() * 0.2, (rng() - 0.5) * 0.3); // fibre snap
    }
    bandNoise(2400, 0.7, 0.07, I);                 // blade friction hiss
    bandNoise(600, 0.6, 0.06, I);                  // juicy body
    thud(T.cutEnd, 0.4, 120, 0.07);                // knife meets the board
    click(T.cutEnd, 0.3, 1.8, 0.45);
    squish(T.fallStart + 0.05, 0.14, 0.22, 0.06, 0.2); // wet halves peel apart
    for (const b of data.honeyBreaks || []) tack(b.t, 0.06 + b.size * 4, (rng() - 0.5) * 0.6);
    thud(T.land, 0.32, 150, 0.1, 0.3);
    squish(T.land, 0.2, 0.18, 0.04, 0.3);
  } else if (style === 'smooth') {
    thud(T.touch, 0.06, 320, 0.02);             // blade meets the glaze, barely a tap
    squish(T.touch, 0.08, 0.15, 0.08);
    bandNoise(1600, 0.6, 0.12);                 // smooth swish of the slice
    bandNoise(5200, 1.0, 0.025);                // airy top
    for (let ms = Math.floor(T.touch * 1000); ms < T.cutEnd * 1000; ms++) { // faint juicy crispness
      const s = scrape[ms] || 0;
      if (rng() < (12 + 50 * s) / 1000) click(ms / 1000, 0.03 + rng() * 0.07, 1 + rng() * 2, 0.5 + rng() * 0.2, (rng() - 0.5) * 0.4);
    }
    thud(T.cutEnd, 0.4, 110, 0.08);              // blade reaches the board
    squish(T.cutEnd, 0.12, 0.12);
    for (const b of data.honeyBreaks || []) tack(b.t, 0.06 + b.size * 4, (rng() - 0.5) * 0.6);
    thud(T.land, 0.38, 150, 0.1, 0.3);           // half settles into the honey
    squish(T.land, 0.22, 0.18, 0.04, 0.3);
  } else {
  // knife touches the glass
  ting(T.touch, 3150, 0.05, 0.4, 0.1);
  click(T.touch, 0.25, 0.8, 0.9, 0.1);
  // creaks while pressing
  for (let t = T.touch + 0.05; t < T.crack; t += 0.03 + rng() * 0.08) click(t, 0.08 + rng() * 0.12, 0.6 + rng(), 0.9, (rng() - 0.5) * 0.4);
  // the crack
  thud(T.crack, 0.22, 230, 0.05);
  ting(T.crack + 0.005, 4300, 0.04, 0.3, -0.1);
  for (let i = 0; i < 140; i++) {
    const u = Math.pow(rng(), 1.8) * 0.14;
    click(T.crack + u, (0.35 + rng() * 0.65) * (1 - u / 0.16), 0.5 + rng() * 2.2, 0.8 + rng() * 0.15, (rng() - 0.5) * 0.7);
  }
  // crunchy slicing: grain density follows knife speed
  for (let ms = Math.floor(T.cutStart * 1000); ms < T.cutEnd * 1000; ms++) {
    const s = scrape[ms] || 0, rate = 40 + 420 * s;
    if (rng() < rate / 1000) click(ms / 1000 + rng() / 1000, (0.12 + rng() * 0.5) * (0.4 + 0.6 * s), 0.4 + rng() * 1.8, 0.78 + rng() * 0.18, (rng() - 0.5) * 0.6);
    if (rng() < 3 / 1000) ting(ms / 1000, 2500 + rng() * 3500, 0.015, 0.15, (rng() - 0.5) * 0.6);
  }
  // scrape layer: band-passed noise (biquad, ~3.5 kHz)
  {
    const f0 = 3500, Q = 0.8, w0 = 2 * Math.PI * f0 / sr, al = Math.sin(w0) / (2 * Q);
    const b0 = al, b2 = -al, a0 = 1 + al, a1 = -2 * Math.cos(w0), a2 = 1 - al;
    let x1 = 0, x2 = 0, y1 = 0, y2 = 0;
    for (let i = 0; i < N; i++) {
      const s = scrape[Math.floor(i / sr * 1000)] || 0;
      const x = rng() * 2 - 1;
      const y = (b0 * x + b2 * x2 - a1 * y1 - a2 * y2) / a0;
      x2 = x1; x1 = x; y2 = y1; y1 = y;
      add(i, y * s * 0.09, 0);
    }
  }
  // knife hits the board
  thud(T.cutEnd, 0.7, 115, 0.09);
  click(T.cutEnd, 0.4, 2.5, 0.5);
  // the half falls open
  thud(T.land, 0.55, 165, 0.08, 0.3);
  ting(T.land, 880, 0.08, 0.12, 0.3);
  for (let i = 0; i < 45; i++) click(T.land + Math.pow(rng(), 1.5) * 0.25, 0.1 + rng() * 0.35, 0.5 + rng() * 1.5, 0.85, 0.2 + (rng() - 0.5) * 0.6);
  // every shard that lands on the board
  for (const im of impacts) {
    const pan = Math.max(-1, Math.min(1, im.x / 2));
    click(im.t, Math.min(0.28, im.v * im.size * 3.5), 0.3 + rng() * 0.5, 0.95, pan);
    if (im.v > 2 && rng() < 0.25) ting(im.t, 6000 + rng() * 3000, 0.006, 0.05, pan);
  }
  }

  // soft limit + normalise to -1 dBFS
  let peak = 0;
  for (let i = 0; i < N; i++) { L[i] = Math.tanh(L[i] * 1.3); R[i] = Math.tanh(R[i] * 1.3); peak = Math.max(peak, Math.abs(L[i]), Math.abs(R[i])); }
  const g = 0.89 / (peak || 1);
  const buf = Buffer.alloc(44 + N * 4);
  buf.write('RIFF', 0); buf.writeUInt32LE(36 + N * 4, 4); buf.write('WAVE', 8); buf.write('fmt ', 12);
  buf.writeUInt32LE(16, 16); buf.writeUInt16LE(1, 20); buf.writeUInt16LE(2, 22); buf.writeUInt32LE(sr, 24);
  buf.writeUInt32LE(sr * 4, 28); buf.writeUInt16LE(4, 32); buf.writeUInt16LE(16, 34); buf.write('data', 36); buf.writeUInt32LE(N * 4, 40);
  for (let i = 0; i < N; i++) {
    buf.writeInt16LE(Math.round(L[i] * g * 32767), 44 + i * 4);
    buf.writeInt16LE(Math.round(R[i] * g * 32767), 46 + i * 4);
  }
  fs.writeFileSync(file, buf);
};
