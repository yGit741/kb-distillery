// pixi run test-e2e — the graph page's mouse and keyboard scheme, end to end in headless Chromium:
// hover/click labels, wheel pan + pinch zoom, left-drag pan / node move, right-drag box, Cmd+right-drag
// lasso, the right-click node menu, citation genealogy, the side reader and the Space / "/" search bar.
// Starts `python -m kb_distillery.dashboard` on a free port against this checkout. Needs the `playwright` npm
// package (resolved normally, from $PLAYWRIGHT_MODULE, or from the npx cache) — skips without it.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createServer } from "node:net";
import { existsSync, readdirSync } from "node:fs";
import { homedir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");

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
      if (exe && existsSync(exe)) return pw;     // a version whose browser is downloaded
    } catch { /* try the next one */ }
  }
  return null;
}

const freePort = () => new Promise((resolve) => {
  const s = createServer();
  s.listen(0, "127.0.0.1", () => { const { port } = s.address(); s.close(() => resolve(port)); });
});

let pw = null, server = null, browser = null, page = null, base = "";
let skipReason = "";
// node:test reads `skip` when a test is declared, before before() has looked for playwright.
const e2e = (name, fn) => test(name, async (t) => { if (skipReason) { t.skip(skipReason); return; } await fn(t); });

before(async () => {
  pw = await loadPlaywright();
  if (!pw) { skipReason = "playwright not found (npm i -g playwright, or set PLAYWRIGHT_MODULE)"; return; }
  const port = await freePort();
  base = `http://127.0.0.1:${port}`;
  server = spawn(process.env.PYTHON || "python3", ["-m", "kb_distillery.dashboard", "--port", String(port), "--no-open"],
    { cwd: ROOT, stdio: ["ignore", "pipe", "pipe"] });
  let log = "";
  server.stdout.on("data", (b) => { log += b; });
  server.stderr.on("data", (b) => { log += b; });
  for (let i = 0; i < 120; i++) {
    try { if ((await fetch(`${base}/graph`)).ok) break; } catch { /* not up yet */ }
    await new Promise((r) => setTimeout(r, 250));
    if (i === 119) throw new Error(`dashboard did not start:\n${log}`);
  }
  browser = await pw.chromium.launch();
  page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
  page.on("dialog", (d) => { throw new Error(`unexpected dialog: ${d.message()}`); });
  await page.goto(`${base}/graph`);
  await page.waitForFunction(() => window.WikiGraph && window.WikiGraph.visibleNodes().length > 5, null, { timeout: 30000 });
  await settle();
});

after(async () => {
  if (browser) await browser.close();
  if (server) server.kill();
});

// ---------------------------------------------------------------- helpers

// Let the layout cool down so screen positions stay put between measuring and acting.
async function settle() {
  await page.waitForTimeout(1200);
  await page.evaluate(() => new Promise((resolve) => {
    let last = null, still = 0;
    const tick = () => {
      const ns = window.WikiGraph.visibleNodes();
      const sig = ns.slice(0, 40).map((n) => `${Math.round(n.x)},${Math.round(n.y)}`).join("|");
      still = sig === last ? still + 1 : 0;
      last = sig;
      if (still >= 4) resolve(); else setTimeout(tick, 250);
    };
    tick();
  }));
}

async function reset() {
  await page.keyboard.press("Escape");
  await page.evaluate(() => { window.GraphMenu.close(); window.SideReader.close(); window.WikiGraph.clear(); });
  await page.mouse.move(2, 600);
}

// A node of the given type sitting well inside the canvas with no other node within `gap` px.
function isolatedNode(type, gap = 26) {
  return page.evaluate(({ type, gap }) => {
    const G = window.WikiGraph;
    const root = document.getElementById("graph-root").getBoundingClientRect();
    const ns = G.visibleNodes().map((n) => ({ n, p: G.screenOf(n) }));
    const ok = ns.filter(({ n, p }) => (!type || n.type === type)
      && p.x > root.left + 260 && p.x < root.right - 420 && p.y > root.top + 120 && p.y < root.bottom - 120
      && ns.every((o) => o.n === n || Math.hypot(o.p.x - p.x, o.p.y - p.y) > gap));
    const best = ok.sort((a, b) => (b.n.inDegree + b.n.outDegree) - (a.n.inDegree + a.n.outDegree))[0];
    return best ? { id: best.n.id, type: best.n.type, x: best.p.x, y: best.p.y } : null;
  }, { type, gap });
}

// An empty point on the canvas: no node within `gap` px.
function emptyPoint(gap = 60) {
  return page.evaluate((gap) => {
    const G = window.WikiGraph;
    const r = document.getElementById("graph-root").getBoundingClientRect();
    const ps = G.visibleNodes().map((n) => G.screenOf(n));
    for (let y = r.top + 160; y < r.bottom - 160; y += 23) {
      for (let x = r.left + 300; x < r.right - 440; x += 23) {
        if (ps.every((p) => Math.hypot(p.x - x, p.y - y) > gap)) return { x, y };
      }
    }
    return null;
  }, gap);
}

const G = (expr) => page.evaluate(expr);

// Put the pointer on a node and wait until the graph reports it hovered. The layout can still drift
// a little, so this re-reads the node's live position each try. Returns that position.
async function hoverNode(id) {
  for (let i = 0; i < 40; i++) {
    const p = await page.evaluate((id) => window.WikiGraph.screenOf(window.WikiGraph.node(id)), id);
    await page.mouse.move(p.x + (i % 2 ? 1 : -1), p.y);
    await page.mouse.move(p.x, p.y);
    try {
      await page.waitForFunction((id) => window.WikiGraph.hovered() && window.WikiGraph.hovered().id === id, id, { timeout: 250 });
      return p;
    } catch { /* moved: try again */ }
  }
  const why = await page.evaluate((id) => {
    const p = window.WikiGraph.screenOf(window.WikiGraph.node(id));
    const el = document.elementFromPoint(p.x, p.y);
    const h = window.WikiGraph.hovered();
    return `at ${Math.round(p.x)},${Math.round(p.y)} is <${el && el.tagName.toLowerCase()} id=${el && el.id} class=${el && el.className}>, hovered=${h && h.id}`;
  }, id);
  throw new Error(`could not hover ${id}: ${why}`);
}

// ---------------------------------------------------------------- tests

e2e("hovering a node labels it even when its type's labels are off", async () => {
  await reset();
  const off = await G(() => {
    const active = window.WikiGraph.activeLabelTypes();
    return ["idea", "question", "topic", "person", "paper"].find((t) => !active.has(t)
      && window.WikiGraph.visibleNodes().some((n) => n.type === t));
  });
  assert.ok(off, "a visible type with labels off");
  const n = await isolatedNode(off);
  assert.ok(n, `an isolated ${off} node`);
  Object.assign(n, await hoverNode(n.id));
  // calm hover: the label follows the focus, which commits once the pointer has settled
  await page.waitForFunction((id) => window.WikiGraph.labeledIds().includes(id), n.id, { timeout: 2000 }).catch(() => {});
  const labeled = await G(() => window.WikiGraph.labeledIds());
  assert.ok(labeled.includes(n.id), "hovered node is labeled");
});

e2e("calm hover: the focus commits only after the pointer settles", async () => {
  await reset();
  const n = await isolatedNode(null);
  assert.ok(n, "an isolated node");
  await page.mouse.move(5, 5);
  await page.waitForFunction(() => !window.WikiGraph.focused(), null, { timeout: 2000 });
  Object.assign(n, await hoverNode(n.id));
  await page.waitForTimeout(450);
  const late = await G(() => window.WikiGraph.focused());
  assert.equal(late && late.id, n.id, "the settled pointer focuses the node");
});

e2e("clicking a node labels all its neighbours", async () => {
  await reset();
  const n = await isolatedNode(null);
  await page.mouse.click(n.x, n.y);
  await page.waitForFunction((id) => window.WikiGraph.selectedIds().join() === id, n.id);
  await page.mouse.move(2, 600);
  const { labeled, nbs } = await page.evaluate((id) => ({
    labeled: window.WikiGraph.labeledIds(),
    nbs: window.WikiGraph.neighbors(id).filter((m) => window.WikiGraph.isVisible(m)),
  }), n.id);
  assert.ok(labeled.includes(n.id));
  for (const m of nbs) assert.ok(labeled.includes(m), `neighbour ${m} labeled`);
});

e2e("wheel pans, pinch (ctrl+wheel) and Cmd+wheel zoom", async () => {
  await reset();
  const p = await emptyPoint(20);
  await page.mouse.move(p.x, p.y);
  const v0 = await G(() => window.WikiGraph.view());
  await page.mouse.wheel(0, 240);
  await page.waitForTimeout(150);
  const v1 = await G(() => window.WikiGraph.view());
  assert.equal(v1.k, v0.k, "plain wheel keeps the zoom");
  assert.ok(Math.abs(v1.centerY - v0.centerY) > 1, "plain wheel moves the view");
  await page.mouse.wheel(180, 0);
  await page.waitForTimeout(150);
  const v2 = await G(() => window.WikiGraph.view());
  assert.ok(Math.abs(v2.centerX - v1.centerX) > 1, "horizontal swipe pans sideways");
  await page.keyboard.down("Control");
  await page.mouse.wheel(0, -40);
  await page.keyboard.up("Control");
  await page.waitForTimeout(150);
  const v3 = await G(() => window.WikiGraph.view());
  assert.ok(v3.k > v2.k * 1.2, `pinch zooms in (${v2.k} → ${v3.k})`);
  await page.keyboard.down("Meta");
  await page.mouse.wheel(0, 100);
  await page.keyboard.up("Meta");
  await page.waitForTimeout(150);
  const v4 = await G(() => window.WikiGraph.view());
  assert.ok(v4.k < v3.k, "Cmd+wheel down zooms out");
  await page.evaluate(() => document.getElementById("btn-fit").click());
  await settle();
});

e2e("left-drag on the background pans, on a node moves the node", async () => {
  await reset();
  const p = await emptyPoint();
  assert.ok(p, "an empty point");
  const v0 = await G(() => window.WikiGraph.view());
  await page.mouse.move(p.x, p.y);
  await page.mouse.down();
  await page.mouse.move(p.x + 60, p.y + 40, { steps: 6 });
  await page.mouse.up();
  const v1 = await G(() => window.WikiGraph.view());
  assert.ok(Math.hypot(v1.centerX - v0.centerX, v1.centerY - v0.centerY) > 5, "view panned");
  // force-graph repaints the hidden canvas it picks drag targets from at most every 800 ms, so right after
  // a pan it still holds the old positions; the magnetic pointer reports the hover sooner than that.
  await page.waitForTimeout(900);

  const n = await isolatedNode(null, 40);
  const before = await page.evaluate((id) => { const m = window.WikiGraph.node(id); return { x: m.x, y: m.y }; }, n.id);
  Object.assign(n, await hoverNode(n.id));
  await page.mouse.down();
  await page.mouse.move(n.x + 90, n.y + 10, { steps: 10 });
  const during = await page.evaluate((id) => { const m = window.WikiGraph.node(id); return { x: m.x, y: m.y }; }, n.id);
  await page.mouse.up();
  const k = (await G(() => window.WikiGraph.view())).k;
  assert.ok(during.x - before.x > 40 / k, `node followed the pointer (${before.x} → ${during.x})`);
  await settle();
});

e2e("right-drag draws a box and selects the nodes inside it", async () => {
  await reset();
  const box = await G(() => {
    const r = document.getElementById("graph-root").getBoundingClientRect();
    return { x1: r.left + r.width * 0.3, y1: r.top + r.height * 0.25, x2: r.left + r.width * 0.6, y2: r.top + r.height * 0.7 };
  });
  await page.mouse.move(box.x1, box.y1);
  await page.mouse.down({ button: "right" });
  await page.mouse.move((box.x1 + box.x2) / 2, (box.y1 + box.y2) / 2, { steps: 4 });
  assert.equal(await G(() => !document.getElementById("box-select-rect").classList.contains("hidden")), true, "box drawn while dragging");
  await page.mouse.move(box.x2, box.y2, { steps: 4 });
  await page.mouse.up({ button: "right" });
  const { selected, inside, menu } = await page.evaluate((b) => {
    const G = window.WikiGraph;
    const inside = G.visibleNodes().filter((n) => { const p = G.screenOf(n); return p.x >= b.x1 && p.x <= b.x2 && p.y >= b.y1 && p.y <= b.y2; }).map((n) => n.id);
    return { selected: G.selectedIds(), inside, menu: window.GraphMenu.isOpen() };
  }, box);
  assert.ok(inside.length > 0, "the box holds nodes");
  assert.deepEqual([...selected].sort(), [...inside].sort());
  assert.equal(menu, false, "a drag does not open the node menu");
  assert.equal(await G(() => document.getElementById("box-select-rect").classList.contains("hidden")), true, "box removed");
});

e2e("Cmd+right-drag lassos; L no longer starts a lasso", async () => {
  await reset();
  await page.mouse.move(2, 600);
  await page.keyboard.press("l");
  assert.equal(await G(() => !!document.querySelector(".sel-lasso")), false, "L does nothing");
  assert.equal(await G(() => !!document.getElementById("sel-lasso-btn")), false, "no Lasso button");

  const n = await isolatedNode(null, 40);
  const ring = Array.from({ length: 16 }, (_, i) => [n.x + 30 * Math.cos((i / 16) * 2 * Math.PI), n.y + 30 * Math.sin((i / 16) * 2 * Math.PI)]);
  await page.mouse.move(ring[0][0], ring[0][1]);
  await page.keyboard.down("Meta");
  await page.mouse.down({ button: "right" });
  for (const [x, y] of ring.slice(1)) await page.mouse.move(x, y);
  assert.equal(await G(() => !!document.querySelector(".sel-lasso")), true, "lasso drawn");
  await page.mouse.up({ button: "right" });
  await page.keyboard.up("Meta");
  const selected = await G(() => window.WikiGraph.selectedIds());
  assert.deepEqual(selected, [n.id], "exactly the node inside the loop");
  assert.equal(await G(() => !!document.querySelector(".sel-lasso")), false, "overlay removed");
  await page.evaluate(() => window.WikiGraph.clear());
  await hoverNode(n.id);   // the release reached force-graph: hovering still works after a lasso
});

e2e("right-click on a node opens its menu; Esc closes it", async () => {
  await reset();
  const n = await isolatedNode(null);
  Object.assign(n, await hoverNode(n.id));
  await page.mouse.down({ button: "right" });
  await page.mouse.up({ button: "right" });
  await page.waitForSelector(".gm-menu");
  const labels = await page.$$eval(".gm-menu .gm-item", (bs) => bs.map((b) => b.textContent));
  assert.equal(labels.length, 4);
  assert.ok(labels.some((l) => l.startsWith("Show details")));
  assert.ok(labels.some((l) => l.startsWith("Open in side reader")));
  assert.ok(labels.some((l) => l.startsWith("Open in Explore")));
  assert.ok(labels.some((l) => l.startsWith("Open in citation genealogy")));
  assert.deepEqual(await G(() => window.WikiGraph.selectedIds()), [], "right-click does not select");
  await page.keyboard.press("Escape");
  assert.equal(await G(() => !!document.querySelector(".gm-menu")), false);

  await hoverNode(n.id);
  await page.mouse.down({ button: "right" });
  await page.mouse.up({ button: "right" });
  await page.waitForSelector(".gm-menu");
  const p = await emptyPoint();
  await page.mouse.click(p.x, p.y);
  assert.equal(await G(() => !!document.querySelector(".gm-menu")), false, "outside click closes it");
});

e2e("menu → citation genealogy shows only what the paper cites and what cites it (2 hops)", async () => {
  await reset();
  await page.evaluate(() => window.WikiGraph.showTypes(null));
  await settle();
  const papers = await G(() => window.WikiGraph.visibleNodes().filter((n) => n.type === "paper").map((n) => n.id));
  assert.ok(papers.length >= 7, "seven papers to build a fixture from");
  const [focus, a, b, c, d, e, far] = papers;
  // a → focus → b → c ; d → a ; e → d (3 hops: out) ; far unrelated
  const fixture = {
    nodes: [focus, a, b, c, d, e, far].map((id, i) => ({ id, title: id, year: 2000 + i, citationCount: i })),
    links: [[a, focus], [focus, b], [b, c], [d, a], [e, d]].map(([s, t]) => ({ source: s, target: t })),
  };
  await page.route("**/api/citations", (r) => r.fulfill({ json: fixture }));
  const n = await page.evaluate((id) => { window.WikiGraph.focus(id, { zoom: false }); return id; }, focus);
  await page.waitForTimeout(900);
  await page.evaluate(() => window.WikiGraph.clear());
  // the focused paper may sit under a neighbour: right-click it, or open its menu directly
  let pos = await page.evaluate((id) => window.WikiGraph.screenOf(window.WikiGraph.node(id)), n);
  let hovered = false;
  try { pos = await hoverNode(focus); hovered = true; } catch { /* covered by another node */ }
  if (hovered) {
    await page.mouse.down({ button: "right" });
    await page.mouse.up({ button: "right" });
  } else {
    await page.evaluate(({ id, x, y }) => window.GraphMenu.open(window.WikiGraph.node(id), x, y), { id: focus, ...pos });
  }
  await page.waitForSelector(".gm-menu");
  await page.click('.gm-item[data-id="genealogy"]');
  await page.waitForFunction(() => window.DataLayer.citeIds().length > 0, null, { timeout: 15000 });
  const ids = await G(() => window.DataLayer.citeIds());
  assert.deepEqual([...ids].sort(), [focus, a, b, c, d].sort(), "2 hops each way, nothing else");
  assert.ok(!ids.includes(e) && !ids.includes(far));
  assert.match(await page.textContent(".dl-cite-bar"), /Genealogy of/);
  await page.unroute("**/api/citations");
  await page.evaluate(() => { window.DataLayer.close(); window.WikiGraph.showTypes(window.WikiGraph.overviewTypes()); });
  await settle();
});

e2e("genealogy is offered for papers only", async () => {
  await reset();
  const n = await isolatedNode("idea") || await isolatedNode("topic");
  await page.evaluate(({ id, x, y }) => window.GraphMenu.open(window.WikiGraph.node(id), x, y), n);
  const disabled = await page.$eval('.gm-item[data-id="genealogy"]', (b) => b.disabled);
  assert.equal(disabled, true);
  await page.keyboard.press("Escape");
});

e2e("double-click opens the side reader in embed mode; Esc closes it", async () => {
  await reset();
  const n = await isolatedNode(null);
  Object.assign(n, await hoverNode(n.id));
  await page.mouse.dblclick(n.x, n.y);
  await page.waitForSelector("#gs-reader:not(.hidden)");
  assert.equal(page.url(), `${base}/graph`, "stayed on the graph");
  const src = await page.$eval("#gs-reader iframe", (f) => f.getAttribute("src"));
  assert.ok(src.includes("embed=1") && src.includes(encodeURIComponent(n.id)), src);
  const frame = page.frameLocator("#gs-reader iframe");
  await frame.locator(".ex-main h1").first().waitFor({ timeout: 15000 });
  assert.equal(await frame.locator(".app-nav").isVisible(), false, "no nav inside the reader");
  const v = await G(() => window.WikiGraph.view());
  assert.ok(Number.isFinite(v.k));
  await page.mouse.move(2, 600);
  await page.keyboard.press("Escape");
  assert.equal(await G(() => document.getElementById("gs-reader").classList.contains("hidden")), true);
});

e2e("Space opens the search, which finds pages by their text; Cmd+K does nothing", async () => {
  await reset();
  const placeholder = await page.getAttribute("#gs-cmd-input", "placeholder");
  assert.ok(!placeholder.includes("⌘K"), placeholder);
  await page.keyboard.press("Meta+k");
  assert.notEqual(await G(() => document.activeElement.id), "gs-cmd-input", "Cmd+K no longer focuses the search");

  // a word found in some page's text but not in its title
  const word = await page.evaluate(async () => {
    for (const w of ["proof", "bound", "entropy", "gradient", "kernel", "matrix", "theorem", "rank", "noise"]) {
      const r = await (await fetch(`/api/explore/search?q=${w}&limit=40`)).json();
      const hit = (r.hits || []).find((h) => !(h.title || "").toLowerCase().includes(w) && !h.id.includes(w) && window.WikiGraph.node(h.id));
      if (hit) return w;
    }
    return null;
  });
  assert.ok(word, "a body-only search term");
  await page.mouse.move(2, 600);
  await page.keyboard.press("Space");
  assert.equal(await G(() => document.activeElement.id), "gs-cmd-input");
  await page.keyboard.type(word);
  await page.waitForSelector(".gs-row-text", { timeout: 8000 });
  assert.match(await page.textContent("#gs-palette"), /Mentioned in the text/);
  await page.keyboard.press("Escape");
});

e2e('"/" opens the ask-an-agent placeholder', async () => {
  await reset();
  await page.mouse.move(2, 600);
  await page.keyboard.press("/");
  assert.equal(await page.inputValue("#gs-cmd-input"), "/");
  assert.equal(await G(() => document.getElementById("gs-cmd").classList.contains("gs-agent")), true);
  await page.keyboard.type("what do I know about rank");
  assert.match(await page.textContent("#gs-palette"), /coming soon/);
  await page.keyboard.press("Enter");
  await page.waitForSelector(".gs-agent-note");
  await page.keyboard.press("Escape");
  assert.equal(await G(() => document.getElementById("gs-cmd").classList.contains("gs-agent")), false);
});

e2e("no mode buttons or 1/2/3 mode keys are left", async () => {
  assert.equal(await G(() => document.querySelectorAll(".mode-btn, [data-fly=mode]").length), 0);
});

// ---------------------------------------------------------------- magnetic pointer (experiment)

// A point just outside a node's rim, on its right.
function nearMiss(n, off) {
  return page.evaluate(({ id, off }) => {
    const G = window.WikiGraph, node = G.node(id), p = G.screenOf(node), r = G.radiusOf(node) * G.view().k;
    return { x: p.x + r + off, y: p.y };
  }, { id: n.id, off });
}

e2e("magnetic pointer: a near miss hovers and clicks the nearest node", async () => {
  await reset();
  assert.equal(await G(() => document.getElementById("magnet-pointer").checked), true, "on by default");
  const n = await isolatedNode(null, 40);
  const q = await nearMiss(n, 6);
  await page.mouse.move(q.x - 2, q.y); await page.mouse.move(q.x, q.y);
  await page.waitForFunction((id) => window.WikiGraph.hovered() && window.WikiGraph.hovered().id === id, n.id, { timeout: 3000 });
  await page.waitForTimeout(900);   // let force-graph's pick canvas catch up (see the drag test)
  await page.mouse.click(q.x, q.y);
  try {
    await page.waitForFunction((id) => window.WikiGraph.selectedIds().join() === id, n.id, { timeout: 3000 });
  } catch {
    const st = await page.evaluate(() => ({ sel: window.WikiGraph.selectedIds(), hov: window.WikiGraph.hovered() && window.WikiGraph.hovered().id,
      menu: window.GraphMenu.isOpen() }));
    assert.fail(`near-miss click on ${n.id} did not select it: ${JSON.stringify(st)}`);
  }
});

e2e("magnetic pointer: empty space far from nodes hovers nothing", async () => {
  await reset();
  const p = (await emptyPoint(120)) || (await emptyPoint(95));
  assert.ok(p, "a point at least ~100 px from every node");
  await page.mouse.move(p.x - 2, p.y); await page.mouse.move(p.x, p.y);
  await page.waitForTimeout(250);
  assert.equal(await G(() => window.WikiGraph.hovered()), null);
});

e2e("magnetic pointer: reach grows around isolated nodes and shrinks in clusters", async () => {
  await reset();
  const r = await page.evaluate(() => {
    const G = window.WikiGraph, M = window.GraphMagnet;
    M.timeGaps();
    const ns = G.visibleNodes().filter((n) => M.gap(n.id) !== undefined);
    ns.sort((a, b) => M.gap(a.id) - M.gap(b.id));
    return { tight: M.reachOf(ns[0]), loose: M.reachOf(ns[ns.length - 1]), all: ns.map((n) => M.reachOf(n)) };
  });
  assert.ok(r.all.every((x) => x >= 12 && x <= 90), "reach stays within 12–90 px");
  assert.ok(r.loose > r.tight, `isolated ${r.loose} > crowded ${r.tight}`);
});

e2e("magnetic pointer: switching it off restores exact hits", async () => {
  await reset();
  const n = await isolatedNode(null, 40);
  await page.evaluate(() => document.getElementById("magnet-pointer").click());
  try {
    const q = await nearMiss(n, 8);
    await page.mouse.move(q.x - 2, q.y); await page.mouse.move(q.x, q.y);
    await page.waitForTimeout(300);
    const h = await G(() => window.WikiGraph.hovered());
    assert.ok(!h || h.id !== n.id, "a near miss hovers nothing when the magnet is off");
  } finally {
    await page.evaluate(() => document.getElementById("magnet-pointer").click());
  }
});

e2e("magnetic pointer: the soft bubble paints beside the graph, outside force-graph's container", async () => {
  await reset();
  const n = await isolatedNode(null, 40);
  const q = await nearMiss(n, 6);
  await page.mouse.move(q.x - 2, q.y); await page.mouse.move(q.x, q.y);
  await page.waitForTimeout(400);
  const painted = await page.evaluate(({ x, y }) => {
    const c = document.querySelector("canvas.gm-magnet");
    if (!c || c.closest("#graph-root")) return "missing";
    const r = c.getBoundingClientRect(), d = window.devicePixelRatio || 1;
    return c.getContext("2d").getImageData((x - r.left) * d, (y - r.top) * d, 1, 1).data[3];
  }, q);
  assert.ok(typeof painted === "number" && painted > 0, `bubble alpha at the pointer: ${painted}`);
});

// ---------------------------------------------------------------- clicks keep the selection; panels open on request

const panels = () => page.evaluate(() => ({
  sel: window.WikiGraph.selectedIds(),
  details: window.GraphDetails.isOpen(),
  reader: !!document.getElementById("gs-reader") && !document.getElementById("gs-reader").classList.contains("hidden"),
}));

async function twoNodes() {
  return page.evaluate(() => {
    const G = window.WikiGraph;
    const ns = G.visibleNodes().map((n) => ({ n, p: G.screenOf(n) }));
    return ns.filter(({ n, p }) => p.x > 450 && p.x < 950 && p.y > 220 && p.y < 680 && ns.every((o) => o.n === n || Math.hypot(o.p.x - p.x, o.p.y - p.y) > 40))
      .slice(0, 2).map(({ n }) => ({ id: n.id }));
  });
}

e2e("one click selects and opens nothing; the selection stays lit after the pointer moves on", async () => {
  await reset();
  const [a, b] = await twoNodes();
  const pa = await hoverNode(a.id);
  await page.waitForTimeout(900);
  await page.mouse.click(pa.x, pa.y);
  await page.waitForFunction((id) => window.WikiGraph.selectedIds().join() === id, a.id);
  await page.waitForTimeout(450);                       // past the double-click window
  assert.deepEqual(await panels(), { sel: [a.id], details: false, reader: false }, "a single click only selects");
  await hoverNode(b.id);                                // the pointer moves on to another node
  assert.deepEqual(await G(() => window.WikiGraph.selectedIds()), [a.id], "selection kept");
  assert.equal(await page.evaluate((id) => window.WikiGraph.opacityOf(id), a.id), 1, "the selected node stays fully lit");
});

e2e("Cmd+click adds a second node; both stay selected and lit", async () => {
  await reset();
  const [a, b] = await twoNodes();
  const pa = await hoverNode(a.id);
  await page.waitForTimeout(900);
  await page.mouse.click(pa.x, pa.y);
  await page.waitForFunction((id) => window.WikiGraph.selectedIds().join() === id, a.id);
  await page.waitForTimeout(450);
  const pb = await hoverNode(b.id);
  await page.keyboard.down("Meta");
  await page.mouse.click(pb.x, pb.y);
  await page.keyboard.up("Meta");
  await page.waitForFunction(() => window.WikiGraph.selectedIds().length === 2);
  await page.mouse.move(2, 600);
  await page.waitForTimeout(300);
  assert.deepEqual([...(await G(() => window.WikiGraph.selectedIds()))].sort(), [a.id, b.id].sort());
  for (const id of [a.id, b.id]) assert.equal(await page.evaluate((x) => window.WikiGraph.opacityOf(x), id), 1, `${id} stays lit`);
  assert.equal((await panels()).details, false, "still no panel");
});

e2e("menu → Show details opens the panel; a right-click on empty space closes it and the reader and clears the selection", async () => {
  await reset();
  const [a] = await twoNodes();
  await hoverNode(a.id);
  await page.mouse.down({ button: "right" }); await page.mouse.up({ button: "right" });
  await page.waitForSelector('.gm-item[data-id="details"]');
  await page.click('.gm-item[data-id="details"]');
  await page.waitForFunction(() => window.GraphDetails.isOpen());
  await page.evaluate((id) => window.SideReader.open(id), a.id);
  await page.waitForSelector("#gs-reader:not(.hidden)");
  const p = (await emptyPoint(120)) || (await emptyPoint(95));
  await page.mouse.move(p.x - 2, p.y); await page.mouse.move(p.x, p.y);
  await page.waitForFunction(() => !window.WikiGraph.hovered());
  await page.mouse.down({ button: "right" }); await page.mouse.up({ button: "right" });
  await page.waitForTimeout(200);
  assert.deepEqual(await panels(), { sel: [], details: false, reader: false }, "panels closed, selection cleared");
});
