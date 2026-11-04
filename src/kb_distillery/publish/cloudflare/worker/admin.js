// Snapshot control panel API for the private `kb` Worker (imported by auth.js).
//
// Everything under /admin/ is answered here, never by ASSETS:
//
//   GET    /admin/api/snapshots           our snapshot Workers + manifest, views (7 d), online, behind-main
//   DELETE /admin/api/snapshots/<worker>  delete one snapshot Worker; body {"confirm": "<worker>"}
//   POST   /admin/api/prune               DRY RUN only: orphans (no reachable manifest) + "not ours" Workers
//
// Flags (routed by auth.js; `handleFlags`):
//   GET    /api/flags         any signed-in viewer: {env: "private", overrides: {name: bool}} from KV
//   PUT    /api/flags/<name>  owner only (ADMIN_EMAILS + X-KB-Admin + same Origin, as the panel);
//                             body {"value": true|false|null}; runtime flags only (flags.gen.js)
//   Binding: KV namespace FLAGS_KV (key "overrides"). Unbound → GET returns {} and PUT answers 503.
//
// Gate, in order: no valid session → 401; session email not in ADMIN_EMAILS (default ALLOWED_EMAILS)
// → 403; header `X-KB-Admin: 1` missing → 403; non-GET whose `Origin` is not this site's origin
// → 403 (CSRF: the custom header forces a CORS preflight cross-site, the Origin check covers the
// rest). CF_API_TOKEN unset → 503 {error: "panel not configured: set CF_API_TOKEN"}.
//
// Mirrors src/kb_distillery/publish/cloudflare/cf_api.py + snapshots.py (the CLI); semantics, not code, are shared:
//   - ours = Worker name `snapshot-<YYYYMMDD>-<name>` (the CLI additionally checks the `kb-share`
//     deploy message; the panel does not, to save one API call per Worker — a foreign
//     `snapshot-*` Worker would show up with online:false and be flagged by prune as an orphan).
//   - online: manifest.json 200 → true, timeout (5 s) → "unknown", anything else → false.
//   - views_7d: GraphQL `workersInvocationsAdaptive` sum of requests; unavailable → 0 + a note.
//   - behind_main: APPROXIMATION. The CLI counts KB-Version trailers on main's history; the Worker
//     has no git, so it uses main's manifest kb_version (served by ASSETS) and, when major and
//     minor match, the patch difference (z counts knowledge steps within one schema version).
//     Different major/minor, unparseable versions or a snapshot newer than main → null.
//
// Bindings: vars CF_ACCOUNT_ID and ACCOUNT_SUBDOMAIN, secret CF_API_TOKEN (Workers Scripts Edit + Account Analytics Read).
// All Cloudflare calls go through deps.fetch with an AbortController timeout so tests can mock them.

import { RUNTIME_FLAGS } from "./flags.gen.js";

const API_BASE = "https://api.cloudflare.com/client/v4";
const GRAPHQL_URL = `${API_BASE}/graphql`;
const WORKER_MAIN = "kb";
const SNAPSHOT_RE = /^snapshot-(\d{8})-([a-z0-9](?:[a-z0-9-]*[a-z0-9])?)$/;
const MANIFEST_TIMEOUT_MS = 5000;
const CF_TIMEOUT_MS = 15000;
const VIEWS_DAYS = 7;

const VIEWS_QUERY = `
query ($account: string!, $since: Time!, $until: Time!) {
  viewer {
    accounts(filter: {accountTag: $account}) {
      workersInvocationsAdaptive(limit: 1000, filter: {datetime_geq: $since, datetime_leq: $until}) {
        sum { requests }
        dimensions { scriptName }
      }
    }
  }
}`;

class Timeout extends Error {}

function json(status, body) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
  });
}

function emails(value) {
  return (value || "").split(",").map((e) => e.trim().toLowerCase()).filter(Boolean);
}

export function parseWorker(name) {
  const m = SNAPSHOT_RE.exec(name || "");
  return m ? { date: m[1], name: m[2] } : null;
}

// The workers.dev account subdomain is the ACCOUNT_SUBDOMAIN var, rendered from the share config at deploy time.
export function workerUrl(worker, env) {
  return `https://${worker}.${env.ACCOUNT_SUBDOMAIN}.workers.dev/`;
}

function parseVersion(v) {
  const m = /^(?:kb-)?(\d+)\.(\d+)\.(\d+)$/.exec(String(v || "").trim());
  return m ? m.slice(1).map(Number) : null;
}

// Approximate knowledge steps between a snapshot and main (see the header).
export function behindMain(snapshotVersion, mainVersion) {
  const s = parseVersion(snapshotVersion);
  const m = parseVersion(mainVersion);
  if (!s || !m || s[0] !== m[0] || s[1] !== m[1]) return null;
  const d = m[2] - s[2];
  return d >= 0 ? d : null;
}

async function timed(deps, url, init, ms) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), ms);
  try {
    return await deps.fetch(url, { ...(init || {}), signal: ctl.signal });
  } catch (e) {
    if (ctl.signal.aborted) throw new Timeout(String(url));
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

async function cf(env, deps, method, path, body) {
  const init = { method, headers: { Authorization: `Bearer ${env.CF_API_TOKEN}`, Accept: "application/json" } };
  if (body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await timed(deps, `${API_BASE}${path}`, init, deps.cfTimeoutMs || CF_TIMEOUT_MS);
  } catch (e) {
    throw new Error(`Cloudflare API ${method} ${path}: ${e instanceof Timeout ? "timed out" : "unreachable"}`);
  }
  let payload = null;
  try { payload = await res.json(); } catch { /* non-JSON */ }
  if (!res.ok || !payload || payload.success === false) {
    const errs = ((payload && payload.errors) || []).map((e) => `${e.code}: ${e.message}`).join("; ");
    throw new Error(`Cloudflare API ${method} ${path} failed: ${errs || "HTTP " + res.status}`);
  }
  return payload;
}

async function listScripts(env, deps) {
  const payload = await cf(env, deps, "GET", `/accounts/${env.CF_ACCOUNT_ID}/workers/scripts`);
  return (payload.result || []).map((s) => s.id).filter(Boolean).sort();
}

// ['ok', manifest] | ['timeout', null] | ['down', null]
async function fetchManifest(worker, env, deps) {
  try {
    const res = await timed(deps, workerUrl(worker, env) + "manifest.json", { method: "GET" },
                            deps.manifestTimeoutMs || MANIFEST_TIMEOUT_MS);
    if (res.status !== 200) return ["down", null];
    const data = await res.json();
    return data && typeof data === "object" && !Array.isArray(data) ? ["ok", data] : ["down", null];
  } catch (e) {
    return [e instanceof Timeout ? "timeout" : "down", null];
  }
}

// {worker: requests} or null when analytics is unavailable (not an error).
async function views(env, deps, names) {
  if (!names.length) return {};
  const until = new Date(deps.now());
  const since = new Date(until.getTime() - VIEWS_DAYS * 86400 * 1000);
  const iso = (d) => d.toISOString().replace(/\.\d{3}Z$/, "Z");
  let res, payload;
  try {
    res = await timed(deps, GRAPHQL_URL, {
      method: "POST",
      headers: { Authorization: `Bearer ${env.CF_API_TOKEN}`, "Content-Type": "application/json" },
      body: JSON.stringify({ query: VIEWS_QUERY, variables: { account: env.CF_ACCOUNT_ID, since: iso(since), until: iso(until) } }),
    }, deps.cfTimeoutMs || CF_TIMEOUT_MS);
    payload = await res.json();
  } catch { return null; }
  if (res.status !== 200 || !payload || (payload.errors && payload.errors.length)) return null;
  let rows;
  try { rows = payload.data.viewer.accounts[0].workersInvocationsAdaptive; } catch { return null; }
  if (!Array.isArray(rows)) return null;
  const counts = Object.fromEntries(names.map((n) => [n, 0]));
  for (const row of rows) {
    const script = row && row.dimensions && row.dimensions.scriptName;
    if (Object.hasOwn(counts, script)) counts[script] += Number((row.sum && row.sum.requests) || 0);
  }
  return counts;
}

async function mainVersion(request, env) {
  try {
    const res = await env.ASSETS.fetch(new Request(new URL("/manifest.json", request.url)));
    if (!res.ok) return null;
    const m = await res.json();
    return (m && m.kb_version) || null;
  } catch { return null; }
}

// ---------- routes ----------

async function listSnapshots(request, env, deps) {
  const notes = [];
  const workers = (await listScripts(env, deps)).filter((n) => parseWorker(n));
  const [manifests, counts, mainV] = await Promise.all([
    Promise.all(workers.map((w) => fetchManifest(w, env, deps))),
    views(env, deps, workers),
    mainVersion(request, env),
  ]);
  if (counts === null) notes.push("views: analytics unavailable (token needs Account Analytics Read, or no data yet)");
  if (mainV === null) notes.push("behind main: main's manifest.json is unreadable");
  const snapshots = workers.map((worker, i) => {
    const [state, m] = manifests[i];
    const kbVersion = (m && m.kb_version) || null;
    return {
      worker,
      name: parseWorker(worker).name,
      url: workerUrl(worker, env),
      kb_version: kbVersion,
      content_sha: (m && m.content_sha) || null,
      built_at: (m && m.built_at) || null,
      views_7d: counts ? counts[worker] || 0 : 0,
      online: state === "ok" ? true : state === "timeout" ? "unknown" : false,
      behind_main: behindMain(kbVersion, mainV),
    };
  });
  return json(200, { snapshots, main: { kb_version: mainV }, notes });
}

async function deleteSnapshot(request, env, deps, worker) {
  if (worker === WORKER_MAIN) return json(400, { error: "refusing to delete the main site `kb`" });
  if (!parseWorker(worker)) return json(400, { error: `refusing: ${worker} is not a snapshot-* Worker` });
  let body = null;
  try { body = await request.json(); } catch { /* empty / non-JSON */ }
  if (!body || body.confirm !== worker) {
    return json(400, { error: `confirmation mismatch: send {"confirm": "${worker}"}` });
  }
  try {
    await cf(env, deps, "DELETE", `/accounts/${env.CF_ACCOUNT_ID}/workers/scripts/${encodeURIComponent(worker)}`);
  } catch (e) {
    return json(502, { error: `${e.message} — ${worker} may still be live` });
  }
  return json(200, { deleted: worker, url: workerUrl(worker, env) });
}

async function prune(env, deps) {
  const plan = { dry_run: true, orphans: [], unknown: [], foreign: [], ok: [] };
  const names = (await listScripts(env, deps)).filter((n) => n !== WORKER_MAIN);
  const snaps = names.filter((n) => parseWorker(n));
  plan.foreign = names.filter((n) => !parseWorker(n));
  const states = await Promise.all(snaps.map((w) => fetchManifest(w, env, deps)));
  snaps.forEach((w, i) => {
    const s = states[i][0];
    plan[s === "ok" ? "ok" : s === "timeout" ? "unknown" : "orphans"].push(w);
  });
  return json(200, plan);
}

// The owner gate shared by the panel, flag PUTs and the inbox; returns a refusal Response or null.
export function ownerGate(request, env, session) {
  const url = new URL(request.url);
  if (!session) return json(401, { error: "sign in first" });
  const admins = emails(env.ADMIN_EMAILS || env.ALLOWED_EMAILS);
  if (!admins.includes(String(session.email || "").toLowerCase())) return json(403, { error: "not an admin" });
  if (request.headers.get("X-KB-Admin") !== "1") return json(403, { error: "missing X-KB-Admin header" });
  if (request.method !== "GET" && request.method !== "HEAD" && request.headers.get("Origin") !== url.origin) {
    return json(403, { error: "cross-origin request refused" });
  }
  return null;
}

async function readOverrides(env) {
  if (!env.FLAGS_KV) return {};
  const raw = await env.FLAGS_KV.get("overrides");
  let data = {};
  try { data = raw ? JSON.parse(raw) : {}; } catch { data = {}; }
  return Object.fromEntries(Object.entries(data).filter(([k, v]) => RUNTIME_FLAGS.includes(k) && typeof v === "boolean"));
}

export async function handleFlags(request, env, session) {
  const path = new URL(request.url).pathname.replace(/\/+$/, "");
  if (!session) return json(401, { error: "sign in first" });
  if (path === "/api/flags" && request.method === "GET") return json(200, { env: "private", overrides: await readOverrides(env) });
  const m = /^\/api\/flags\/([^/]+)$/.exec(path);
  if (!m || request.method !== "PUT") return json(404, { error: "no such flags route" });
  const refused = ownerGate(request, env, session);
  if (refused) return refused;
  let name;
  try { name = decodeURIComponent(m[1]); } catch { return json(400, { error: "bad flag name" }); }
  if (!RUNTIME_FLAGS.includes(name)) return json(409, { error: `${name} is not a runtime flag` });
  let body;
  try { body = await request.json(); } catch { return json(400, { error: "body must be JSON {value}" }); }
  if (!body || !(typeof body.value === "boolean" || body.value === null)) return json(400, { error: "value must be true, false or null" });
  if (!env.FLAGS_KV) return json(503, { error: "flags not configured: bind KV namespace FLAGS_KV" });
  const ov = await readOverrides(env);
  if (body.value === null) delete ov[name]; else ov[name] = body.value;
  await env.FLAGS_KV.put("overrides", JSON.stringify(ov));
  return json(200, { env: "private", overrides: ov });
}

// session: the verified kb_session payload ({email, iat, exp}) or null.
export async function handleAdmin(request, env, deps, session) {
  const url = new URL(request.url);
  const refused = ownerGate(request, env, session);
  if (refused) return refused;
  if (!env.CF_API_TOKEN) return json(503, { error: "panel not configured: set CF_API_TOKEN" });
  if (!env.CF_ACCOUNT_ID) return json(503, { error: "panel not configured: set CF_ACCOUNT_ID" });
  if (!env.ACCOUNT_SUBDOMAIN) return json(503, { error: "panel not configured: set ACCOUNT_SUBDOMAIN" });

  const path = url.pathname.replace(/\/+$/, "");
  try {
    if (path === "/admin/api/snapshots" && request.method === "GET") return await listSnapshots(request, env, deps);
    const del = /^\/admin\/api\/snapshots\/([^/]+)$/.exec(path);
    if (del && request.method === "DELETE") return await deleteSnapshot(request, env, deps, decodeURIComponent(del[1]));
    if (path === "/admin/api/prune" && request.method === "POST") return await prune(env, deps);
  } catch (e) {
    return json(502, { error: e.message });
  }
  return json(404, { error: "no such admin route" });
}
