// pixi run test-e2e — the React graph screen is still once drawn (ui-principles §29: nothing moves unasked).
// The layout is settled off screen, so the canvas a moment after the first nodes appear must equal the canvas
// two seconds later, with and without prefers-reduced-motion. A settled-only screenshot can't see this: the
// motion is over by the time it is taken.
// Starts `python -m kb_distillery.server` on a free port against this checkout (it rebuilds src/kb_distillery/_webapp when stale).
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
  server = spawn(process.env.PYTHON || "python3", ["-m", "kb_distillery.server", "--port", String(port), "--no-open", "--kb", join(ROOT, "examples", "demo")],
    { cwd: ROOT, stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, PYTHONPATH: join(ROOT, "src") } });
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

// ---- the user's hand: a click or a selection moves nothing; a drag moves the dragged page only

const places = (page) => page.evaluate(() => window.__kbGraph.nodes());

/** The largest distance any page other than `except` moved between two reads (screen px; graph units with ["gx", "gy"]). */
function drift(before, after, except, [kx, ky] = ["x", "y"]) {
  const at = new Map(after.map((n) => [n.id, n]));
  let worst = { id: "", d: 0 };
  for (const n of before) {
    const m = at.get(n.id);
    if (!m || n.id === except || !Number.isFinite(n[kx]) || !Number.isFinite(m[kx])) continue;
    const d = Math.hypot(m[kx] - n[kx], m[ky] - n[ky]);
    if (d > worst.d) worst = { id: n.id, d };
  }
  return worst;
}

/** A page well inside the canvas with no other page within `gap` px, so a click lands on it alone. */
async function lonePage(page, skip = new Set(), gap = 24) {
  const ns = await places(page);
  const vw = 1440, vh = 900;
  const ok = ns.filter((n) => !skip.has(n.id) && n.x > vw * 0.3 && n.x < vw * 0.7 && n.y > vh * 0.25 && n.y < vh * 0.75
    && ns.every((o) => o === n || Math.hypot(o.x - n.x, o.y - n.y) > gap));
  assert.ok(ok.length, "no isolated page to click");
  return ok.sort((a, b) => (b.deg ?? 0) - (a.deg ?? 0))[0]; // the best-linked one: a drag pulls its neighbours
}

async function settledPage() {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(`${base}/app/graph`);
  await firstFrame(page);
  await page.waitForFunction(() => window.__kbGraph && window.__kbGraph.nodes().length > 5, null, { timeout: 30000 });
  await page.waitForTimeout(2500); // whatever the load does, it has done it
  return page;
}

e2e("clicking a page (select) moves nothing", async () => {
  const page = await settledPage();
  try {
    const n = await lonePage(page);
    const before = await places(page);
    await page.mouse.click(n.x, n.y);
    await page.waitForTimeout(2000);
    assert.ok(await page.evaluate(() => window.__kbGraph.selected()) > 0, `the click on ${n.id} selected nothing`);
    const w = drift(before, await places(page));
    assert.ok(w.d < 1, `clicking ${n.id} moved ${w.id} by ${w.d.toFixed(1)} px`);
  } finally {
    await page.close();
  }
});

e2e("adding to the selection (Cmd+click) and clearing it moves nothing", async () => {
  const page = await settledPage();
  try {
    const a = await lonePage(page);
    await page.mouse.click(a.x, a.y);
    await page.waitForTimeout(800);
    const b = await lonePage(page, new Set([a.id]));
    const before = await places(page);
    await page.keyboard.down("Meta");
    await page.mouse.click(b.x, b.y);
    await page.keyboard.up("Meta");
    await page.waitForTimeout(800);
    assert.equal(await page.evaluate(() => window.__kbGraph.selected()), 2, "Cmd+click did not add the second page");
    await page.keyboard.press("Escape");
    await page.waitForTimeout(1500);
    const w = drift(before, await places(page));
    assert.ok(w.d < 1, `selecting moved ${w.id} by ${w.d.toFixed(1)} px`);
  } finally {
    await page.close();
  }
});

e2e("selecting a page and dragging it moves that page only", async () => {
  const page = await settledPage();
  try {
    const n = await lonePage(page, new Set(), 40);
    const before = await places(page);
    // select it, then drag it right away: the way people move a page they just picked
    await page.mouse.click(n.x, n.y);
    await page.waitForTimeout(150);
    await page.mouse.move(n.x, n.y);
    await page.mouse.down();
    for (let i = 1; i <= 10; i++) await page.mouse.move(n.x + i * 8, n.y + i * 5, { steps: 2 });
    await page.mouse.up();
    await page.waitForTimeout(2000);
    const after = await places(page);
    const me = after.find((m) => m.id === n.id);
    assert.ok(Math.hypot(me.x - n.x, me.y - n.y) > 40, `the dragged page ${n.id} did not follow the pointer`);
    const w = drift(before, after, n.id);
    assert.ok(w.d < 1, `dragging ${n.id} moved ${w.id} by ${w.d.toFixed(1)} px`);
  } finally {
    await page.close();
  }
});

e2e("a filter change moves none of the pages that stay", async () => {
  const page = await settledPage();
  try {
    const before = await places(page);
    // The shell (flag `graph-shell`, the default) filters from the page-types card: hide one type, then show it
    // again. The legend chip "Connected" is the same step with the shell off.
    const chip = page.locator('[title^="Only pages with at least"]');
    let hide, show;
    if (await chip.count()) {
      hide = chip.first();
      show = page.getByRole("button", { name: "Show all" });
    } else {
      // the page-types card starts open; open it only when a saved fold closed it
      const opener = page.getByRole("button", { name: "Show page types" });
      if (await opener.count()) {
        await opener.click();
        await page.waitForTimeout(600);
      }
      // pin the entry by its type id: once it is hidden it is no longer the first pressed one
      const id = await page.locator('[data-corners="types"] button[aria-pressed="true"]').first().getAttribute("data-type");
      hide = page.locator(`[data-corners="types"] button[data-type="${id}"]`);
      show = hide;
    }
    // hiding pages: the pages that stay must stay put (hiding a type re-frames the view for the new set of types,
    // which is the camera, so that path compares graph coordinates; the chip keeps the camera, so it compares px)
    await hide.click();
    await page.waitForTimeout(2000);
    const fewer = await places(page);
    assert.ok(fewer.length < before.length, "the filter hid nothing");
    let w = show === hide ? drift(before, fewer, undefined, ["gx", "gy"]) : drift(before, fewer);
    assert.ok(w.d < (show === hide ? 0.5 : 1), `filtering moved ${w.id} by ${w.d.toFixed(1)} ${show === hide ? "graph units" : "px"}`);
    // and back: the hidden pages are placed off screen, the others keep their place in the layout (the view may
    // re-frame for a new set of types: that is the camera, so this compares graph coordinates)
    await show.click();
    await page.waitForTimeout(2000);
    w = drift(fewer, await places(page), undefined, ["gx", "gy"]);
    assert.ok(w.d < 0.5, `showing the hidden pages again moved ${w.id} by ${w.d.toFixed(1)} graph units`);
  } finally {
    await page.close();
  }
});
