// Usage:
//   node render.cjs serve                 -> live preview at http://localhost:8123/scene.html
//   node render.cjs preview pear 1,3,4.5  -> stills at half resolution into OUT_DIR
//   node render.cjs full pear             -> frames + audio + glass_pear_asmr.mp4
// Fruits: apple, pear, orange (defined in scene.html)
// Env: OUT_DIR (frames/temp), FFMPEG (path to ffmpeg.exe), CHROME (path to chrome.exe)
const http = require('http');
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');
const puppeteer = require('puppeteer-core');
const buildAudio = require('./audio.cjs');

const ROOT = __dirname;
const THREE_DIR = path.resolve(path.dirname(require.resolve('three')), '..');
const OUT = process.env.OUT_DIR || path.join(ROOT, 'out');
const FFMPEG = process.env.FFMPEG || 'ffmpeg';
const CHROME = process.env.CHROME || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const FPS = 30, PORT = 8123;
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.cjs': 'text/javascript', '.json': 'application/json' };

function serve() {
  return new Promise(res => {
    const srv = http.createServer((req, rsp) => {
      const url = decodeURIComponent(req.url.split('?')[0]);
      const file = url.startsWith('/three/') ? path.join(THREE_DIR, url.slice(7)) : path.join(ROOT, url);
      fs.readFile(file, (err, buf) => {
        if (err) { rsp.writeHead(404); rsp.end(); return; }
        rsp.writeHead(200, { 'Content-Type': MIME[path.extname(file)] || 'application/octet-stream' });
        rsp.end(buf);
      });
    });
    srv.listen(PORT, () => res(srv));
  });
}

async function openScene(w, h, fruit) {
  const browser = await puppeteer.launch({
    executablePath: CHROME, headless: true,
    args: ['--use-angle=d3d11', '--enable-gpu', '--ignore-gpu-blocklist', '--enable-unsafe-swiftshader', `--window-size=${w},${h}`],
  });
  const page = await browser.newPage();
  page.on('console', m => console.log('[page]', m.text()));
  page.on('pageerror', e => console.log('[page error]', e.message));
  await page.setViewport({ width: w, height: h, deviceScaleFactor: 1 });
  await page.goto(`http://localhost:${PORT}/scene.html?render=1&w=${w}&h=${h}&fruit=${fruit}`, { waitUntil: 'domcontentloaded', timeout: 0 });
  await page.waitForFunction('window.sceneReady === true', { timeout: 600000 });
  page.setDefaultTimeout(0);
  console.log('GPU:', await page.evaluate(() => window.glInfo));
  return { browser, page };
}

async function grab(page, t, file) {
  const type = file.endsWith('.jpg') ? 'image/jpeg' : 'image/png';
  const data = await page.evaluate((t, type) => { window.renderAt(t); return document.querySelector('canvas').toDataURL(type, 0.97); }, t, type);
  fs.writeFileSync(file, Buffer.from(data.split(',')[1], 'base64'));
}

(async () => {
  const mode = process.argv[2] || 'full';
  const fruit = process.argv[3] || 'apple';
  const srv = await serve();
  if (mode === 'serve') { console.log(`http://localhost:${PORT}/scene.html`); return; }
  fs.mkdirSync(OUT, { recursive: true });

  if (mode === 'preview') {
    const times = (process.argv[4] || '0.5,2.5,3,4,5.5,7.5').split(',').map(Number);
    const { browser, page } = await openScene(540, 960, fruit);
    for (const t of times) { const f = path.join(OUT, `preview_${fruit}_${t.toFixed(2)}.png`); await grab(page, t, f); console.log(f); }
    await browser.close(); srv.close(); return;
  }

  // SS > 1 renders larger and downscales for cleaner edges and finer texture detail
  const SS = +process.env.SS || 1;
  const { browser, page } = await openScene(Math.round(1080 * SS), Math.round(1920 * SS), fruit);
  const dur = await page.evaluate(() => window.DURATION);
  const framesDir = path.join(OUT, `frames_${fruit}`);
  fs.rmSync(framesDir, { recursive: true, force: true });
  fs.mkdirSync(framesDir, { recursive: true });
  const n = Math.round(dur * FPS), start = Date.now();
  for (let i = 0; i < n; i++) {
    await grab(page, i / FPS, path.join(framesDir, `f${String(i).padStart(4, '0')}.jpg`));
    if (i % 30 === 0) console.log(`frame ${i}/${n}  ${((Date.now() - start) / 1000).toFixed(0)}s`);
  }
  const wav = path.join(OUT, `audio_${fruit}.wav`);
  buildAudio(await page.evaluate(() => window.getAudioData()), wav, dur);
  await browser.close(); srv.close();

  const mp4 = path.join(ROOT, `glass_${fruit}_asmr.mp4`);
  const r = spawnSync(FFMPEG, ['-y', '-loglevel', 'error', '-framerate', String(FPS), '-i', path.join(framesDir, 'f%04d.jpg'), '-i', wav,
    '-vf', 'scale=1080:1920:flags=lanczos:out_range=tv,unsharp=5:5:0.35,format=yuv420p',
    '-c:v', 'libx264', '-preset', 'slow', '-crf', '16', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', '-shortest', '-movflags', '+faststart', mp4], { stdio: 'inherit' });
  console.log(r.status === 0 ? `done: ${mp4}` : `ffmpeg failed (${r.status})`);
})();
