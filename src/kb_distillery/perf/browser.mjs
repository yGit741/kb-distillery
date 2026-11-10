// Browser half of `pixi run perf`: open /app, wait for network idle, click every top-level nav tab twice (opening the folded app bar first, as a user does; tabs the flag set lacks are `skipped`).
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
// top-level tabs the shell can offer; one missing from the nav in this flag set is reported as skipped, not as a failed click
const EXPECTED = ["/app/", "/app/graph", "/app/system", "/app/chat", "/app/think", "/app/what-is-it", "/app/share"];
const discovered = new Set(tabs);
if (!opts.tabs || !opts.tabs.length) tabs = [...tabs, ...EXPECTED.filter((t) => !tabs.includes(t))];
out.tabs = tabs;
const navLink = (href) => page.locator(`header nav a[href="${href}"]`).first();
// The graph folds the app bar away (flag header-fold) behind a chevron; a user opens it first, so the bench does too.
const openBar = async () => {
  if (!(await page.locator("header[data-folded]").count())) return;
  await page.getByRole("button", { name: "Show the app bar" }).first().click({ timeout: 10000 });
  await page.locator("header:not([data-folded])").waitFor({ state: "attached", timeout: 10000 });
};
for (const pass of ["pass1", "pass2"]) {
  for (const href of tabs) {
    // the bar stays in the DOM when folded, so a link that is absent is a tab this flag set does not offer
    if ((await navLink(href).count()) === 0 && !discovered.has(href)) {
      out[pass][href] = { ms: null, api_requests: 0, timed_out: false, skipped: "not in the nav for this flag set" };
      continue;
    }
    // the graph folds the bar from an effect that can land after the last idle, so settle, then check right before the click
    await page.waitForTimeout(300);
    try { await openBar(); } catch (e) { out[pass][href] = { ms: null, api_requests: 0, timed_out: false, error: "app bar would not open" }; continue; }
    t0 = Date.now(); n0 = apiCount;
    try { await navLink(href).click({ timeout: 60000 }); } catch (e) { out[pass][href] = { ms: null, api_requests: 0, timed_out: false, error: "click failed" }; continue; }
    r = await idle(t0);
    out[pass][href] = { ms: r.ms, api_requests: apiCount - n0, timed_out: r.timed_out };
  }
}
await browser.close();
console.log(JSON.stringify(out));
