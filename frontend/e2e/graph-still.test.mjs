// pixi run test-e2e — the React graph screen is still once drawn (ui-principles §29: nothing moves unasked).
// The layout is settled off screen, so the canvas a moment after the first nodes appear must equal the canvas
// two seconds later, with and without prefers-reduced-motion. A settled-only screenshot can't see this: the
// motion is over by the time it is taken.
// Starts `python -m kb.api` on a free port against this checkout (it rebuilds frontend/dist when stale).
// Needs the `playwright` npm package (resolved normally, from $PLAYWRIGHT_MODULE, or from the npx cache) —
// skips without it.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createServer } from "node:net";
import { existsSync, readdirSync } from "node:fs";
import { homedir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
/** Share of canvas pixels allowed to differ between the two looks (label fades, the cursor-free hover lens). */
const MAX_CHANGED = 0.01;

async function loadPlaywright() {
  try { return await import("playwright"); } catch { /* not installed here */ }
  const candidates = [];
  if (process.env.PLAYWRIGHT_MODULE) candidates.push(process.env.PLAYWRIGHT_MODULE);
  const npx = join(homedir(), ".npm", "_npx");
  if (existsSync(npx)) {
    for (const d of readdirSync(npx)) candidates.push(join(npx, d, "node_modules", "playwright"));
  }
  for (const c of candidates) {
    const entry = join(c, "index.mjs");
    if (!existsSync(entry)) continue;
    try {
      const pw = await import(pathToFileURL(entry).href);
      const exe = pw.chromium.executablePath();
      if (exe && existsSync(exe)) return pw;
    } catch { /* try the next one */ }
  }
  return null;
}

const freePort = () => new Promise((resolve) => {
  const s = createServer();
  s.listen(0, "127.0.0.1", () => { const { port } = s.address(); s.close(() => resolve(port)); });
});

let pw = null, server = null, browser = null, base = "";
let skipReason = "";
const e2e = (name, fn) => test(name, async (t) => { if (skipReason) { t.skip(skipReason); return; } await fn(t); });

before(async () => {
  pw = await loadPlaywright();
  if (!pw) { skipReason = "playwright not found (npm i -g playwright, or set PLAYWRIGHT_MODULE)"; return; }
  const port = await freePort();
  base = `http://127.0.0.1:${port}`;
  server = spawn(process.env.PYTHON || "python3", ["-m", "kb.api", "--port", String(port), "--no-open"],
    { cwd: ROOT, stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, PYTHONPATH: join(ROOT, "backend", "src") } });
  let log = "";
  server.stdout.on("data", (b) => { log += b; });
  server.stderr.on("data", (b) => { log += b; });
  for (let i = 0; i < 480; i++) {
    try { if ((await fetch(`${base}/app/graph`)).ok) break; } catch { /* not up yet */ }
    await new Promise((r) => setTimeout(r, 250));
    if (i === 479) throw new Error(`app did not start:\n${log}`);
  }
  browser = await pw.chromium.launch();
}, { timeout: 180000 });

after(async () => {
  if (browser) await browser.close();
  if (server) server.kill();
});

// A fingerprint of every on-screen canvas: one byte per pixel (summed RGBA), so two looks can be compared.
function look(page) {
  return page.evaluate(() => {
    const out = [];
    for (const c of document.querySelectorAll("canvas")) {
      if (!c.width || !c.height) continue;
      const d = c.getContext("2d").getImageData(0, 0, c.width, c.height).data;
      for (let i = 0; i < d.length; i += 4) out.push((d[i] + d[i + 1] + d[i + 2] + d[i + 3]) & 255);
    }
    return out;
  });
}

// Wait until the graph canvas has drawn something (the nodes are in), then a beat for the label fade-in.
async function firstFrame(page) {
  await page.waitForFunction(() => {
    const c = document.querySelector("canvas");
    if (!c || !c.width) return false;
    const d = c.getContext("2d").getImageData(0, 0, c.width, c.height).data;
    let ink = 0;
    for (let i = 3; i < d.length; i += 16) if (d[i]) ink++;
    return ink > 200;
  }, null, { timeout: 60000, polling: 50 });
  await page.waitForTimeout(400);
}

async function changedShare(reducedMotion) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, reducedMotion });
  try {
    await page.goto(`${base}/app/graph`);
    await firstFrame(page);
    const a = await look(page);
    await page.waitForTimeout(2000);
    const b = await look(page);
    assert.equal(a.length, b.length, "the canvas changed size");
    let diff = 0;
    for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) diff++;
    return diff / a.length;
  } finally {
    await page.close();
  }
}

e2e("the graph is still after its first frame", async () => {
  const share = await changedShare("no-preference");
  assert.ok(share <= MAX_CHANGED, `${(share * 100).toFixed(1)}% of the canvas moved after the first frame`);
});

e2e("the graph is still after its first frame with reduced motion", async () => {
  const share = await changedShare("reduce");
  assert.ok(share <= MAX_CHANGED, `${(share * 100).toFixed(1)}% of the canvas moved after the first frame`);
});
