// pixi run test-ui-principles — the [auto] half of ~/.claude/skills/ui-principles/SKILL.md as a failing test.
// Loads every app screen (.integrator.toml `screens`, plus /think?note=<first think note>) at 1440×900 in
// light and dark against a fresh `python -m kb_distillery.server` on a free port, and reports, per route and theme:
//   rule 4   overlap: two visible controls / panels whose boxes intersect by more than 2px (ancestors excluded)
//   rule 9   clipping: a text element wider than its box without text-overflow: ellipsis (ellipsis = report only)
//   rule 25  targets: a visible button / link / input smaller than 24×24 px (inline links in prose excluded)
//   rule 5   contrast: text below 4.5:1 (3:1 for ≥24px or ≥18.66px bold) over a solid background; translucent
//            or image backgrounds are skipped rather than guessed
//   rule 12  colour literals (#hex, rgb(, hsl(, oklch() added by this branch under web/src outside src/theme/
//   rule 30  console errors and 4xx/5xx responses while a screen loads
// Findings are keyed `route|theme|rule|element shape` with a count per key. ui-principles.baseline.json holds
// what main already had; a finding whose key is new fails, a known key only warns (a grown count is reported:
// counts follow the data, e.g. Home's random samples, so they don't gate). The
// baseline must shrink, never grow: UI_PRINCIPLES_WRITE_BASELINE=1 rewrites it but refuses to add keys or raise
// counts (UI_PRINCIPLES_WRITE_BASELINE=grow overrides, for a deliberate reset); stale entries are named.
// Needs the `playwright` npm package (resolved, $PLAYWRIGHT_MODULE, or the npx cache) — skips without it.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { spawn, execFileSync } from "node:child_process";
import { createServer } from "node:net";
import { existsSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..", "..");
const BASELINE = join(HERE, "ui-principles.baseline.json");
const VIEWPORT = { width: 1440, height: 900 };
const THEMES = ["light", "dark"];
const OVERLAP_SLACK = 2;
const MIN_TARGET = 24;

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

/** Screens from .integrator.toml (`{ id = "...", path = "..." }` rows), else the built-in list. */
function screens() {
  const fallback = [["home", "/"], ["graph", "/graph"], ["pages", "/pages"], ["system", "/system"]];
  let rows = fallback;
  try {
    const toml = readFileSync(join(ROOT, ".integrator.toml"), "utf8");
    const found = [...toml.matchAll(/\{\s*id\s*=\s*"([^"]+)"\s*,\s*path\s*=\s*"([^"]+)"/g)].map((m) => [m[1], m[2]]);
    if (found.length) rows = found;
  } catch { /* no integrator config */ }
  return rows.map(([id, path]) => ({ id, path }));
}

// ---------------------------------------------------------------- rule 12: colour literals in the diff

/** Lines this branch adds under web/src (outside src/theme/) that carry a colour literal. */
function colourLiterals() {
  const git = (args) => execFileSync("git", args, { cwd: ROOT, encoding: "utf8" });
  let base = "";
  try { base = git(["merge-base", "origin/main", "HEAD"]).trim(); } catch { /* no origin/main: whole tree */ }
  const files = new Set();
  const diffNames = git(["diff", "--name-only", base || "HEAD", "--", "web/src"]).split("\n");
  const untracked = git(["ls-files", "--others", "--exclude-standard", "--", "web/src"]).split("\n");
  for (const f of [...diffNames, ...untracked]) if (f.trim()) files.add(f.trim());
  const literal = /#(?:[0-9a-f]{8}|[0-9a-f]{6}|[0-9a-f]{3,4})(?![0-9a-z_-])|\b(?:rgba?|hsla?|oklch)\(/i;
  const out = [];
  for (const f of files) {
    if (f.startsWith("web/src/theme/")) continue;
    if (/\.(test|spec)\.[jt]sx?$/.test(f) || f.endsWith(".d.ts")) continue;
    if (!/\.(tsx?|jsx?|css)$/.test(f)) continue;
    let added;
    try {
      // -M with the pre-move path in the pathspec: a renamed file counts only its changed lines
      const d = git(["diff", "-M", "-U0", base || "HEAD", "--", f, f.replace(/^web\/src\//, "front" + "end/src/")]);
      added = d ? d.split("\n").filter((l) => l.startsWith("+") && !l.startsWith("+++")).map((l) => l.slice(1)) : null;
    } catch { added = null; }
    if (added === null) {
      if (!existsSync(join(ROOT, f))) continue;
      added = readFileSync(join(ROOT, f), "utf8").split("\n");
    }
    for (const line of added) {
      const m = literal.exec(line);
      if (m) out.push({ route: "diff", theme: "-", rule: 12, label: f, value: `${m[0]} in: ${line.trim().slice(0, 80)}` });
    }
  }
  return out;
}

// ---------------------------------------------------------------- rules 4, 9, 25, 5: measured in the page

function inspect({ slack, minTarget }) {
  const findings = [];
  const vw = window.innerWidth, vh = window.innerHeight;
  // shape = what the baseline keys on (stable across data changes); label = shape + the text, for the report
  const shape = (el) => {
    const id = el.id ? `#${el.id}` : "";
    const tid = el.getAttribute("data-testid");
    const cls = (typeof el.className === "string" ? el.className : "").split(/\s+/).filter(Boolean).slice(0, 2).join(".");
    return `${el.tagName.toLowerCase()}${id}${tid ? `[${tid}]` : ""}${cls ? `.${cls}` : ""}`;
  };
  const label = (el) => {
    const text = (el.getAttribute("aria-label") || el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 40);
    return `${shape(el)}${text ? ` "${text}"` : ""}`;
  };
  const visible = (el) => {
    const st = getComputedStyle(el);
    if (st.display === "none" || st.visibility === "hidden" || Number(st.opacity) === 0) return false;
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return false;
    if (r.bottom < 0 || r.right < 0 || r.top > vh || r.left > vw) return false;
    return true;
  };
  const hiddenAncestor = (el) => {
    for (let p = el; p; p = p.parentElement) {
      const st = getComputedStyle(p);
      if (st.display === "none" || st.visibility === "hidden" || Number(st.opacity) === 0) return true;
      if (p.getAttribute("aria-hidden") === "true") return true;
    }
    return false;
  };
  const shown = (el) => visible(el) && !hiddenAncestor(el);

  // rule 4 — overlap of chrome: controls, toolbars, panels
  const chrome = [...document.querySelectorAll("button, [role=button], [role=toolbar], aside, header, nav, [role=dialog], [role=menu]")]
    .filter(shown)
    .map((el) => ({ el, r: el.getBoundingClientRect() }));
  for (let i = 0; i < chrome.length; i++) {
    for (let j = i + 1; j < chrome.length; j++) {
      const a = chrome[i], b = chrome[j];
      if (a.el.contains(b.el) || b.el.contains(a.el)) continue;
      const w = Math.min(a.r.right, b.r.right) - Math.max(a.r.left, b.r.left);
      const h = Math.min(a.r.bottom, b.r.bottom) - Math.max(a.r.top, b.r.top);
      if (w > slack && h > slack) {
        findings.push({ rule: 4, shape: `${shape(a.el)} × ${shape(b.el)}`, label: `${label(a.el)} × ${label(b.el)}`, value: `overlap ${Math.round(w)}×${Math.round(h)}px` });
      }
    }
  }

  // text-bearing elements: an element with at least one non-blank direct text node
  const textEls = [...document.querySelectorAll("body *")].filter((el) => {
    if (el instanceof SVGElement || ["SCRIPT", "STYLE", "NOSCRIPT", "CANVAS", "TEXTAREA", "INPUT"].includes(el.tagName)) return false;
    for (const n of el.childNodes) if (n.nodeType === 3 && n.textContent.trim()) return true;
    return false;
  }).filter(shown);

  // rule 9 — clipping
  for (const el of textEls) {
    if (el.scrollWidth <= el.clientWidth + 1 || el.clientWidth === 0) continue;
    const st = getComputedStyle(el);
    if (st.overflowX === "auto" || st.overflowX === "scroll") continue; // a scroller by design (code blocks)
    if (st.position === "absolute" && el.clientWidth <= 1) continue; // screen-reader-only text (.sr-only)
    if (st.whiteSpace === "nowrap" && st.overflowX === "visible" && el.scrollWidth - el.clientWidth <= 1) continue;
    const ellipsis = st.textOverflow === "ellipsis" && st.overflowX !== "visible";
    findings.push({
      rule: 9, report: ellipsis, shape: shape(el), label: label(el),
      value: `${ellipsis ? "ellipsis" : st.overflowX === "visible" ? "overflows" : "clipped"} ${el.scrollWidth}>${el.clientWidth}px`,
    });
  }

  // rule 25 — target size (inline links inside prose are exempt, as in WCAG 2.5.8)
  for (const el of document.querySelectorAll("button, a[href], [role=button], input:not([type=hidden]), select, textarea")) {
    if (!shown(el)) continue;
    if (el.tagName === "A" && el.closest("p, li, td, blockquote, dd") && getComputedStyle(el).display === "inline") continue;
    const r = el.getBoundingClientRect();
    if (r.width + 0.5 < minTarget || r.height + 0.5 < minTarget) {
      findings.push({ rule: 25, shape: shape(el), label: label(el), value: `${Math.round(r.width)}×${Math.round(r.height)}px` });
    }
  }

  // rule 5 — contrast over a solid background
  // Any CSS colour (rgb, oklch, color(), …) → sRGB via the canvas serialiser (#rrggbb or rgba()).
  const cctx = document.createElement("canvas").getContext("2d");
  const parse = (c) => {
    if (!c || c === "transparent") return { r: 0, g: 0, b: 0, a: 0 };
    cctx.fillStyle = "#000"; cctx.fillStyle = c;
    const n = cctx.fillStyle;
    const hex = /^#([0-9a-f]{6})$/i.exec(n);
    if (hex) return { r: parseInt(hex[1].slice(0, 2), 16), g: parseInt(hex[1].slice(2, 4), 16), b: parseInt(hex[1].slice(4, 6), 16), a: 1 };
    const m = /rgba?\(([^)]+)\)/.exec(n);
    if (!m) return null;
    const p = m[1].split(/[\s,\/]+/).filter(Boolean).map(Number);
    return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
  };
  const lum = ({ r, g, b }) => {
    const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  };
  const over = (fg, bg) => ({ r: fg.r * fg.a + bg.r * (1 - fg.a), g: fg.g * fg.a + bg.g * (1 - fg.a), b: fg.b * fg.a + bg.b * (1 - fg.a), a: 1 });
  const ratio = (a, b) => { const [h, l] = [lum(a), lum(b)].sort((x, y) => y - x); return (h + 0.05) / (l + 0.05); };
  /** Composite the backgrounds behind `el` until an opaque one; null when a layer can't be resolved. */
  const background = (el) => {
    const layers = [];
    for (let p = el; p; p = p.parentElement) {
      const st = getComputedStyle(p);
      if (p !== el && Number(st.opacity) < 1) return null;
      if (st.backgroundImage !== "none") return null;
      const c = parse(st.backgroundColor);
      if (c && c.a > 0) {
        layers.push(c);
        if (c.a >= 1) break;
      }
      if (p === document.documentElement && (!c || c.a < 1)) layers.push({ r: 255, g: 255, b: 255, a: 1 });
    }
    if (!layers.length) return null;
    let bg = layers[layers.length - 1];
    if (bg.a < 1) return null;
    for (let i = layers.length - 2; i >= 0; i--) bg = over(layers[i], bg);
    return bg;
  };
  for (const el of textEls) {
    if (el.closest("[disabled], [aria-disabled=true]")) continue;
    const st = getComputedStyle(el);
    const fg = parse(st.color);
    if (!fg || fg.a === 0) continue;
    const bg = background(el);
    if (!bg) continue;
    const colour = fg.a < 1 ? over(fg, bg) : fg;
    const size = parseFloat(st.fontSize);
    const bold = parseInt(st.fontWeight, 10) >= 700;
    const need = size >= 24 || (size >= 18.66 && bold) ? 3 : 4.5;
    const got = ratio(colour, bg);
    if (got + 0.005 < need) {
      findings.push({ rule: 5, shape: shape(el), label: label(el), value: `${got.toFixed(2)}:1 (need ${need}:1, ${st.color} on rgb(${Math.round(bg.r)},${Math.round(bg.g)},${Math.round(bg.b)}))` });
    }
  }
  return findings;
}

// ---------------------------------------------------------------- the run

let pw = null, server = null, browser = null, base = "";
let skipReason = "";
const e2e = (name, fn) => test(name, async (t) => { if (skipReason) { t.skip(skipReason); return; } await fn(t); });

before(async () => {
  pw = await loadPlaywright();
  if (!pw) { skipReason = "playwright not found (npm i -g playwright, or set PLAYWRIGHT_MODULE)"; return; }
  const port = await freePort();
  base = `http://127.0.0.1:${port}`;
  server = spawn(process.env.PYTHON || "python3", ["-m", "kb_distillery.server", "--port", String(port), "--no-open"],
    { cwd: ROOT, stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, PYTHONPATH: join(ROOT, "src") } });
  let log = "";
  server.stdout.on("data", (b) => { log += b; });
  server.stderr.on("data", (b) => { log += b; });
  for (let i = 0; i < 480; i++) {
    try { if ((await fetch(`${base}/app/`)).ok) break; } catch { /* not up yet */ }
    await new Promise((r) => setTimeout(r, 250));
    if (i === 479) throw new Error(`app did not start:\n${log}`);
  }
  browser = await pw.chromium.launch();
}, { timeout: 180000 });

after(async () => {
  if (browser) await browser.close();
  if (server) server.kill();
});

async function routes() {
  const list = screens();
  try {
    const r = await fetch(`${base}/api/think`);
    const notes = r.ok ? (await r.json()).notes || [] : [];
    if (notes.length) list.push({ id: "think", path: `/think?note=${encodeURIComponent(notes[0].name)}` });
  } catch { /* think screen off in this env */ }
  return list;
}

async function measure(route, theme) {
  const ctx = await browser.newContext({ viewport: VIEWPORT, colorScheme: theme, reducedMotion: "reduce" });
  const page = await ctx.newPage();
  const findings = [];
  const msgShape = (t) => t.replace(/https?:\/\/\S+/g, "<url>").replace(/\d+/g, "#").slice(0, 80);
  page.on("console", (m) => { if (m.type() === "error") findings.push({ rule: 30, shape: `console ${msgShape(m.text())}`, label: "console", value: m.text().slice(0, 160) }); });
  page.on("pageerror", (e) => findings.push({ rule: 30, shape: `pageerror ${msgShape(String(e.message || e))}`, label: "pageerror", value: String(e.message || e).slice(0, 160) }));
  page.on("response", (r) => {
    if (r.status() < 400) return;
    const path = new URL(r.url()).pathname;
    // key on the route shape: encoded or numeric segments (file names, slugs) vary with the sampled data
    const shape = path.split("/").map((seg) => (/%|\d/.test(seg) ? "*" : seg)).join("/");
    findings.push({ rule: 30, shape: `HTTP ${r.status()} ${shape}`, label: path, value: `HTTP ${r.status()}` });
  });
  try {
    // networkidle covers the data fetches (no screen opens a stream on load); a bounded fallback if one ever does
    await page.goto(`${base}/app${route.path}`, { waitUntil: "load", timeout: 60000 });
    await page.waitForLoadState("networkidle", { timeout: 45000 }).catch(() => {});
    await page.waitForTimeout(1500);
    findings.push(...await page.evaluate(inspect, { slack: OVERLAP_SLACK, minTarget: MIN_TARGET }));
  } finally {
    await ctx.close();
  }
  return findings.map((f) => ({ route: route.id, theme, ...f }));
}

// Baseline key: the element's shape, not its text, and no digits — counts, versions and sampled pages change daily.
// Only contrast (rule 5) depends on the theme; the other rules key on the route alone so that Home's random
// samples don't produce a different key per theme.
const key = (f) => {
  const s = f.shape || f.label;
  const status = /^HTTP (\d+)/.exec(s);           // the status code stays; every other number is data
  return `${f.route}|${f.rule === 5 ? f.theme : "*"}|${f.rule}|${status ? `HTTP ${status[1]}` : ""}${s.slice(status ? status[0].length : 0).replace(/\d+/g, "#")}`;
};
const line = (f) => `${f.route} ${f.theme} · rule ${f.rule} · ${f.label} · ${f.value}${f.same ? ` (+${f.same} alike)` : ""}`;

e2e("every screen keeps the [auto] ui-principles, light and dark", async () => {
  const all = colourLiterals();
  for (const route of await routes()) {
    for (const theme of THEMES) all.push(...await measure(route, theme));
  }
  const seen = new Map();
  for (const f of all) if (!seen.has(key(f))) seen.set(key(f), { ...f, same: 0 }); else seen.get(key(f)).same++;
  const findings = [...seen.values()];
  const counts = Object.fromEntries(findings.filter((f) => !f.report && f.rule !== 12).map((f) => [key(f), f.same + 1]));

  const baseline = existsSync(BASELINE) ? JSON.parse(readFileSync(BASELINE, "utf8")) : {};
  if (process.env.UI_PRINCIPLES_WRITE_BASELINE) {
    const grown = Object.keys(counts).filter((k) => (counts[k] || 0) > (baseline[k] || 0));
    if (grown.length && Object.keys(baseline).length && process.env.UI_PRINCIPLES_WRITE_BASELINE !== "grow") {
      throw new Error(`the baseline must shrink, never grow — fix these instead (or UI_PRINCIPLES_WRITE_BASELINE=grow):\n  ${grown.join("\n  ")}`);
    }
    // `grow` unions with the file (max count per key): slow endpoints and Home's random samples mean one run
    // never sees everything main can show; the plain mode rewrites from this run alone (it can only shrink).
    const merged = process.env.UI_PRINCIPLES_WRITE_BASELINE === "grow" ? { ...baseline } : {};
    for (const k of Object.keys(counts)) merged[k] = Math.max(merged[k] || 0, counts[k]);
    const sorted = Object.fromEntries(Object.keys(merged).sort().map((k) => [k, merged[k]]));
    writeFileSync(BASELINE, JSON.stringify(sorted, null, 2) + "\n");
    console.log(`wrote ${Object.keys(sorted).length} baseline entries to ${BASELINE}`);
    Object.assign(baseline, sorted);
  }

  const reports = findings.filter((f) => f.report);
  const known = findings.filter((f) => !f.report && f.rule !== 12 && baseline[key(f)]);
  const grown = known.filter((f) => baseline[key(f)] < f.same + 1);
  const fresh = findings.filter((f) => !f.report && (f.rule === 12 || !baseline[key(f)]));
  const stale = Object.keys(baseline).filter((k) => !counts[k]);

  if (reports.length) console.log(`ellipsis by design (${reports.length}, report only):\n  ${reports.map(line).join("\n  ")}`);
  if (known.length) console.log(`known on main (${known.length}, in the baseline):\n  ${known.map(line).join("\n  ")}`);
  if (grown.length) console.log(`more of a known failure than the baseline counted (${grown.length}):\n  ${grown.map((f) => `${line(f)} — baseline ${baseline[key(f)]}`).join("\n  ")}`);
  if (stale.length) console.log(`fixed since the baseline (${stale.length}; remove them from ${BASELINE}):\n  ${stale.join("\n  ")}`);
  assert.equal(fresh.length, 0, `${fresh.length} new ui-principles failure(s):\n  ${fresh.map(line).join("\n  ")}`);
});
