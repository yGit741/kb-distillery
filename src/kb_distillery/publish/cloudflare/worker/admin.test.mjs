// node --test share — the snapshot panel API (admin.js) through auth.js's handle().
// Cloudflare REST, GraphQL, snapshot manifests and ASSETS are all mocked; nothing hits the network.
import { test } from "node:test";
import assert from "node:assert/strict";
import { handle } from "./auth.js";
import { behindMain } from "./admin.js";

const ORIGIN = "https://kb.example.workers.dev";
const SECRET = "test-session-secret";
const NOW = 1_800_000_000_000; // ms
const ACCOUNT = "acct123";
const API = "https://api.cloudflare.com/client/v4";
const SNAP_A = "snapshot-20261001-cohen";
const SNAP_B = "snapshot-20261015-draft";
const SUBDOMAIN = "acme-example";
const host = (w) => `https://${w}.${SUBDOMAIN}.workers.dev/manifest.json`;

const enc = new TextEncoder();
const b64url = (bytes) => Buffer.from(bytes).toString("base64url");

async function session(email, { exp = NOW / 1000 + 3600 } = {}) {
  const body = b64url(enc.encode(JSON.stringify({ email, iat: NOW / 1000, exp })));
  const key = await crypto.subtle.importKey("raw", enc.encode(SECRET), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return `kb_session=${body}.${b64url(await crypto.subtle.sign("HMAC", key, enc.encode(body)))}`;
}

function env(overrides = {}) {
  return {
    ASSETS: {
      fetch: async (req) => {
        const path = new URL(req.url).pathname;
        if (path === "/manifest.json") return Response.json({ kb_version: "0.9.6", content_sha: "main" });
        return new Response("asset:" + path, { status: 200 });
      },
    },
    GOOGLE_CLIENT_ID: "cid", GOOGLE_CLIENT_SECRET: "shh", SESSION_SECRET: SECRET,
    ALLOWED_EMAILS: "me@example.com", CF_ACCOUNT_ID: ACCOUNT, ACCOUNT_SUBDOMAIN: SUBDOMAIN, CF_API_TOKEN: "tok", ...overrides,
  };
}

const manifest = (v, sha) => ({ content_ref: "kb-" + v, content_sha: sha, kb_version: v, viewer_sha: "v",
                                profile: "public", sha256: "h", built_at: "2026-10-01T00:00:00Z" });

// Cloudflare + snapshot hosts. `hang` = manifest URLs that never answer (until aborted).
function cloud({ scripts = ["kb", SNAP_A, SNAP_B, "my-other-app"], manifests = {}, hang = [],
                 analytics = "ok", deleteStatus = 200 } = {}) {
  const calls = [];
  const fetch = async (url, init = {}) => {
    url = String(url);
    const method = init.method || "GET";
    calls.push({ method, url, auth: init.headers && init.headers.Authorization });
    if (url === `${API}/accounts/${ACCOUNT}/workers/scripts` && method === "GET") {
      return Response.json({ success: true, result: scripts.map((id) => ({ id })) });
    }
    if (url.startsWith(`${API}/accounts/${ACCOUNT}/workers/scripts/`) && method === "DELETE") {
      return Response.json({ success: deleteStatus === 200, errors: deleteStatus === 200 ? [] : [{ code: 1, message: "boom" }] },
                           { status: deleteStatus });
    }
    if (url === `${API}/graphql`) {
      if (analytics === "fail") return Response.json({ errors: [{ message: "not authorized" }] }, { status: 200 });
      const body = JSON.parse(init.body);
      assert.equal(body.variables.account, ACCOUNT);
      return Response.json({ data: { viewer: { accounts: [{ workersInvocationsAdaptive: [
        { sum: { requests: 5 }, dimensions: { scriptName: SNAP_A } },
        { sum: { requests: 2 }, dimensions: { scriptName: SNAP_A } },
        { sum: { requests: 99 }, dimensions: { scriptName: "kb" } },
      ] }] } } });
    }
    for (const w of hang) {
      if (url === host(w)) {
        return new Promise((_, reject) => init.signal.addEventListener("abort", () => reject(new Error("aborted"))));
      }
    }
    for (const [w, m] of Object.entries(manifests)) if (url === host(w)) return m ? Response.json(m) : new Response("no", { status: 404 });
    if (url.endsWith("/manifest.json")) return new Response("not found", { status: 404 });
    throw new Error("unexpected fetch " + method + " " + url);
  };
  return { calls, fetch };
}

async function call(path, { method = "GET", email = "me@example.com", header = true, origin = ORIGIN, body,
                            cookie, e = env(), cf = cloud() } = {}) {
  const headers = new Headers();
  const c = cookie !== undefined ? cookie : email ? await session(email) : null;
  if (c) headers.set("Cookie", c);
  if (header) headers.set("X-KB-Admin", "1");
  if (origin) headers.set("Origin", origin);
  if (body !== undefined) headers.set("Content-Type", "application/json");
  const req = new Request(ORIGIN + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  const res = await handle(req, e, { fetch: cf.fetch, now: () => NOW, manifestTimeoutMs: 30, cfTimeoutMs: 200 });
  const text = await res.text();
  let json = null;
  try { json = JSON.parse(text); } catch { /* not JSON */ }
  return { res, json, text, cf };
}

const cfCalls = (cf) => cf.calls.filter((c) => c.url.startsWith(API));

// ---------- gate ----------

test("no session → 401 JSON, no Cloudflare call", async () => {
  const { res, cf } = await call("/admin/api/snapshots", { email: null });
  assert.equal(res.status, 401);
  assert.equal(cf.calls.length, 0);
});

test("tampered session → 401", async () => {
  const good = await session("me@example.com");
  const { res } = await call("/admin/api/snapshots", { cookie: good.slice(0, -2) + "xx" });
  assert.equal(res.status, 401);
});

test("signed-in but not an admin email → 403", async () => {
  const { res, cf } = await call("/admin/api/snapshots", { email: "other@example.com" });
  assert.equal(res.status, 403);
  assert.equal(cf.calls.length, 0);
});

test("ADMIN_EMAILS narrows ALLOWED_EMAILS", async () => {
  const e = env({ ALLOWED_EMAILS: "me@example.com,friend@example.com", ADMIN_EMAILS: "me@example.com" });
  assert.equal((await call("/admin/api/snapshots", { email: "friend@example.com", e })).res.status, 403);
  assert.equal((await call("/admin/api/snapshots", { email: "me@example.com", e })).res.status, 200);
});

test("missing X-KB-Admin header → 403", async () => {
  const { res, cf } = await call("/admin/api/snapshots", { header: false });
  assert.equal(res.status, 403);
  assert.equal(cf.calls.length, 0);
});

test("cross-origin or Origin-less DELETE / POST → 403, nothing called", async () => {
  for (const origin of ["https://evil.example", null]) {
    const del = await call(`/admin/api/snapshots/${SNAP_A}`, { method: "DELETE", origin, body: { confirm: SNAP_A } });
    assert.equal(del.res.status, 403);
    assert.equal(del.cf.calls.length, 0);
    const pr = await call("/admin/api/prune", { method: "POST", origin });
    assert.equal(pr.res.status, 403);
  }
});

test("CF_API_TOKEN missing → 503 with the setup hint", async () => {
  const { res, json, cf } = await call("/admin/api/snapshots", { e: env({ CF_API_TOKEN: "" }) });
  assert.equal(res.status, 503);
  assert.equal(json.error, "panel not configured: set CF_API_TOKEN");
  assert.equal(cf.calls.length, 0);
});

test("ACCOUNT_SUBDOMAIN missing → 503 with the setup hint, no Cloudflare call", async () => {
  const { res, json, cf } = await call("/admin/api/snapshots", { e: env({ ACCOUNT_SUBDOMAIN: "" }) });
  assert.equal(res.status, 503);
  assert.equal(json.error, "panel not configured: set ACCOUNT_SUBDOMAIN");
  assert.equal(cf.calls.length, 0);
});

test("unknown admin route → 404 JSON, never an asset", async () => {
  const { res, text } = await call("/admin/api/nope");
  assert.equal(res.status, 404);
  assert.ok(!text.startsWith("asset:"));
});

// ---------- list ----------

test("list: only snapshot-* Workers, manifest fields, views, online, behind-main", async () => {
  const cf = cloud({ manifests: { [SNAP_A]: manifest("0.9.4", "aaa"), [SNAP_B]: manifest("0.9.6", "bbb") } });
  const { res, json } = await call("/admin/api/snapshots", { cf });
  assert.equal(res.status, 200);
  assert.equal(res.headers.get("Cache-Control"), "no-store");
  assert.deepEqual(json.main, { kb_version: "0.9.6" });
  assert.deepEqual(json.notes, []);
  assert.deepEqual(json.snapshots.map((s) => s.worker), [SNAP_A, SNAP_B]);
  const [a, b] = json.snapshots;
  assert.deepEqual(a, { worker: SNAP_A, name: "cohen", url: `https://${SNAP_A}.${SUBDOMAIN}.workers.dev/`,
                        kb_version: "0.9.4", content_sha: "aaa", built_at: "2026-10-01T00:00:00Z",
                        views_7d: 7, online: true, behind_main: 2 });
  assert.equal(b.views_7d, 0);
  assert.equal(b.behind_main, 0);
  // the token goes to Cloudflare only, never to the snapshot hosts
  for (const c of cf.calls) assert.equal(Boolean(c.auth), c.url.startsWith(API), c.url);
});

test("list: manifest timeout → online unknown; 404 → online false", async () => {
  const cf = cloud({ manifests: { [SNAP_B]: null }, hang: [SNAP_A] });
  const { json } = await call("/admin/api/snapshots", { cf });
  const byName = Object.fromEntries(json.snapshots.map((s) => [s.worker, s]));
  assert.equal(byName[SNAP_A].online, "unknown");
  assert.equal(byName[SNAP_B].online, false);
  assert.equal(byName[SNAP_A].kb_version, null);
  assert.equal(byName[SNAP_A].behind_main, null);
});

test("list: analytics unavailable → views 0 + a note, still 200", async () => {
  const cf = cloud({ manifests: { [SNAP_A]: manifest("0.9.4", "a"), [SNAP_B]: manifest("0.9.5", "b") }, analytics: "fail" });
  const { res, json } = await call("/admin/api/snapshots", { cf });
  assert.equal(res.status, 200);
  assert.deepEqual(json.snapshots.map((s) => s.views_7d), [0, 0]);
  assert.equal(json.notes.length, 1);
  assert.match(json.notes[0], /analytics unavailable/);
});

test("list: Cloudflare script listing fails → 502 with the error", async () => {
  const cf = { calls: [], fetch: async () => Response.json({ success: false, errors: [{ code: 10000, message: "Authentication error" }] }, { status: 403 }) };
  const { res, json } = await call("/admin/api/snapshots", { cf });
  assert.equal(res.status, 502);
  assert.match(json.error, /Authentication error/);
});

test("behind-main math (patch difference within one major.minor, else null)", () => {
  assert.equal(behindMain("0.9.4", "0.9.6"), 2);
  assert.equal(behindMain("kb-0.9.6", "0.9.6"), 0);
  assert.equal(behindMain("0.8.6", "0.9.6"), null);
  assert.equal(behindMain("1.9.6", "0.9.6"), null);
  assert.equal(behindMain("0.9.7", "0.9.6"), null);
  assert.equal(behindMain(null, "0.9.6"), null);
  assert.equal(behindMain("0.9.6", "none"), null);
});

// ---------- delete ----------

test("DELETE with a wrong or missing confirmation → 400, no Cloudflare call", async () => {
  for (const body of [{ confirm: "cohen" }, { confirm: SNAP_B }, {}, undefined]) {
    const { res, cf } = await call(`/admin/api/snapshots/${SNAP_A}`, { method: "DELETE", body });
    assert.equal(res.status, 400);
    assert.equal(cf.calls.length, 0);
  }
});

test("DELETE kb or a foreign Worker → 400 even when confirmed", async () => {
  for (const w of ["kb", "my-other-app", "snapshot-x"]) {
    const { res, cf } = await call(`/admin/api/snapshots/${w}`, { method: "DELETE", body: { confirm: w } });
    assert.equal(res.status, 400, w);
    assert.equal(cf.calls.length, 0);
  }
});

test("DELETE confirmed → exactly one Cloudflare delete of that Worker", async () => {
  const { res, json, cf } = await call(`/admin/api/snapshots/${SNAP_A}`, { method: "DELETE", body: { confirm: SNAP_A } });
  assert.equal(res.status, 200);
  assert.equal(json.deleted, SNAP_A);
  const deletes = cf.calls.filter((c) => c.method === "DELETE");
  assert.equal(deletes.length, 1);
  assert.equal(deletes[0].url, `${API}/accounts/${ACCOUNT}/workers/scripts/${SNAP_A}`);
  assert.equal(deletes[0].auth, "Bearer tok");
});

test("DELETE failure at Cloudflare → 502 naming the Worker", async () => {
  const { res, json } = await call(`/admin/api/snapshots/${SNAP_A}`, { method: "DELETE", body: { confirm: SNAP_A },
                                                                      cf: cloud({ deleteStatus: 500 }) });
  assert.equal(res.status, 502);
  assert.match(json.error, new RegExp(SNAP_A));
});

// ---------- prune ----------

test("prune is a dry run: orphans, unknown, not-ours — and never a DELETE", async () => {
  const cf = cloud({ scripts: ["kb", SNAP_A, SNAP_B, "snapshot-20261020-slow", "my-other-app"],
                     manifests: { [SNAP_A]: manifest("0.9.6", "a"), [SNAP_B]: null }, hang: ["snapshot-20261020-slow"] });
  const { res, json } = await call("/admin/api/prune", { method: "POST", cf });
  assert.equal(res.status, 200);
  assert.deepEqual(json, { dry_run: true, orphans: [SNAP_B], unknown: ["snapshot-20261020-slow"],
                           foreign: ["my-other-app"], ok: [SNAP_A] });
  assert.equal(cf.calls.filter((c) => c.method === "DELETE").length, 0);
});

test("GET prune / POST snapshots are not routes → 404", async () => {
  assert.equal((await call("/admin/api/prune")).res.status, 404);
  assert.equal((await call("/admin/api/snapshots", { method: "POST" })).res.status, 404);
});

// ---------- non-admin paths ----------

test("non-admin paths are still served by ASSETS untouched", async () => {
  for (const path of ["/", "/manifest.json", "/administrator", "/x/admin/api/snapshots"]) {
    const { res, text, cf } = await call(path, { header: false });
    assert.equal(res.status, 200, path);
    if (path !== "/manifest.json") assert.equal(text, "asset:" + path);
    assert.equal(cf.calls.length, 0);
  }
});

test("non-admin path without a session still redirects to sign-in", async () => {
  const req = new Request(ORIGIN + "/", { headers: { Accept: "text/html" } });
  const res = await handle(req, env(), { fetch: async () => { throw new Error("no fetch"); }, now: () => NOW });
  assert.equal(res.status, 302);
  assert.equal(res.headers.get("Location"), "/auth/login");
});

// ---------- /api/flags (handleFlags) ----------

function kv(initial = {}) {
  const store = new Map(Object.entries(initial));
  return { store, get: async (k) => store.get(k) ?? null, put: async (k, v) => void store.set(k, v) };
}

async function flagsReq(method, path, { email = "me@example.com", body, headers = {} } = {}) {
  const h = { ...headers };
  if (email) h.Cookie = await session(email);
  return new Request(ORIGIN + path, { method, headers: h, body: body === undefined ? undefined : JSON.stringify(body) });
}
const ownerHeaders = { "X-KB-Admin": "1", Origin: ORIGIN, "Content-Type": "application/json" };

test("flags: GET needs a session, returns KV overrides (runtime names only)", async () => {
  const FLAGS_KV = kv({ overrides: JSON.stringify({ "ui.system-flags-tab": true, "screen.share": true }) });
  const deps = { now: () => NOW };
  assert.equal((await handle(await flagsReq("GET", "/api/flags", { email: null }), env({ FLAGS_KV }), deps)).status, 401);
  const r = await handle(await flagsReq("GET", "/api/flags"), env({ FLAGS_KV }), deps);
  assert.equal(r.status, 200);
  assert.deepEqual(await r.json(), { env: "private", overrides: { "ui.system-flags-tab": true } });
  const none = await handle(await flagsReq("GET", "/api/flags"), env(), deps);
  assert.deepEqual((await none.json()).overrides, {});
});

test("flags: PUT is owner-only, runtime-only, persists to KV", async () => {
  const FLAGS_KV = kv();
  const e = env({ FLAGS_KV, ALLOWED_EMAILS: "me@example.com,friend@example.com", ADMIN_EMAILS: "me@example.com" });
  const deps = { now: () => NOW };
  const put = async (name, opts) => handle(await flagsReq("PUT", `/api/flags/${name}`, opts), e, deps);
  assert.equal((await put("ui.system-flags-tab", { email: "friend@example.com", body: { value: true }, headers: ownerHeaders })).status, 403);
  assert.equal((await put("ui.system-flags-tab", { body: { value: true }, headers: { Origin: ORIGIN } })).status, 403);
  assert.equal((await put("ui.system-flags-tab", { body: { value: true }, headers: { ...ownerHeaders, Origin: "https://evil.example" } })).status, 403);
  assert.equal((await put("screen.share", { body: { value: true }, headers: ownerHeaders })).status, 409);
  assert.equal((await put("ui.system-flags-tab", { body: { value: "yes" }, headers: ownerHeaders })).status, 400);
  const ok = await put("ui.system-flags-tab", { body: { value: true }, headers: ownerHeaders });
  assert.equal(ok.status, 200);
  assert.deepEqual(JSON.parse(FLAGS_KV.store.get("overrides")), { "ui.system-flags-tab": true });
  await put("ui.system-flags-tab", { body: { value: null }, headers: ownerHeaders });
  assert.deepEqual(JSON.parse(FLAGS_KV.store.get("overrides")), {});
  const unbound = await handle(await flagsReq("PUT", "/api/flags/ui.system-flags-tab", { body: { value: true }, headers: ownerHeaders }), env(), deps);
  assert.equal(unbound.status, 503);
});
