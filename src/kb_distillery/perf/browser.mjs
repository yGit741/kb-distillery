// Browser half of `pixi run perf`: open /app, wait for network idle, click every top-level nav tab twice.
// usage: node browser.mjs <playwright-module-dir> <base-url> <json {tabs?:[href], timeout_ms?:n}>
// prints one JSON object on stdout.
import { createRequire } from "node:module";
const [, , pwDir, base, optRaw] = process.argv;
const opts = JSON.parse(optRaw || "{}");
const timeout = opts.timeout_ms || 120000;
const require = createRequire(pwDir + "/");
const { chromium } = require(pwDir);
const browser = await chromium.launch();
const page = await (await browser.newContext()).newPage();
let inflight = 0, apiCount = 0, last = Date.now();
const apis = [];
page.on("request", (r) => { inflight++; last = Date.now(); const u = new URL(r.url()); if (u.pathname.startsWith("/api/")) { apiCount++; apis.push(u.pathname); } });
const done = () => { inflight = Math.max(0, inflight - 1); last = Date.now(); };
page.on("requestfinished", done); page.on("requestfailed", done);
const idle = async (t0) => {
  for (;;) {
    if (inflight === 0 && Date.now() - last >= 500) return { ms: Math.max(0, Math.round(last - t0)), timed_out: false };
    if (Date.now() - t0 > timeout) return { ms: Date.now() - t0, timed_out: true };
    await new Promise((r) => setTimeout(r, 50));
  }
};
const out = { initial: null, tabs: [], pass1: {}, pass2: {}, errors: [] };
page.on("pageerror", (e) => out.errors.push(String(e).slice(0, 200)));
let t0 = Date.now(), n0 = apiCount;
await page.goto(base + "/app", { waitUntil: "commit", timeout });
let r = await idle(t0);
out.initial = { ms: r.ms, api_requests: apiCount - n0, timed_out: r.timed_out };
let tabs = opts.tabs;
if (!tabs || !tabs.length) {
  tabs = await page.$$eval("a[href]", (as) => [...new Set(as.filter((a) => a.closest("header, nav")).map((a) => new URL(a.href).pathname).filter((p) => p.startsWith("/app/") && !p.includes("/pages/")))]);
}
out.tabs = tabs;
for (const pass of ["pass1", "pass2"]) {
  for (const href of tabs) {
    t0 = Date.now(); n0 = apiCount;
    const loc = page.locator(`a[href="${href}"]`).first();
    try { await loc.click({ timeout: 60000 }); } catch (e) { out[pass][href] = { ms: null, api_requests: 0, timed_out: false, error: "click failed" }; continue; }
    r = await idle(t0);
    out[pass][href] = { ms: r.ms, api_requests: apiCount - n0, timed_out: r.timed_out };
  }
}
await browser.close();
console.log(JSON.stringify(out));
