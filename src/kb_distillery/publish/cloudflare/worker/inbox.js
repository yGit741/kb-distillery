// Upload inbox of the private `kb` Worker (imported by auth.js). The Worker only checks and parks uploads; the
// owner's Mac imports them (`distill kb inbox pull`), so the knowledge bases stay on the Mac and nothing is auto-published.
//
//   POST /api/inbox/validate     body: a zip, or JSON {git_url}   -> the checker's report; stores nothing
//   POST /api/inbox              same body, optional ?id=<kb id>&kit=<kit>&name=<zip name>; JSON may carry id, kit
//                                -> 201 {item, status: "pending", ...}; an invalid zip is 422 with the report, nothing stored
//   GET  /api/inbox[?status=…]   -> {items: [...]} newest first (any signed-in viewer; summaries only)
//   GET  /api/inbox/<item>       -> the full record, with the report (owner)
//   GET  /api/inbox/<item>/bundle-> the stored zip (owner, or the Mac with the inbox token)
//   POST /api/inbox/<item>/status  body {status: "imported", kb_id} | {status: "failed", error} | {status: "pending"} (retry)
//
// Who: a signed-in session on ADMIN_EMAILS (default ALLOWED_EMAILS) with `X-KB-Admin: 1` and a same-origin `Origin` on
// writes (admin.js `ownerGate`), or the Mac: `Authorization: Bearer <secret INBOX_TOKEN>` (no cookie, so no CSRF), which
// may only list, download and report imported/failed. Anyone else: 401/403. A git URL is only recorded; the Mac clones it.
//
// R2 binding KB_INBOX (wrangler `r2_buckets`):  meta/<item>.json  the record (customMetadata = its summary, so a list
// needs no extra reads),  bundle/<item>.zip  the upload. Not bound -> 503 (validate still works).
// Limits: INBOX_MAX_BYTES (default 25 MiB) for the body; zip.js limits for entries and unpacked size.

import { ownerGate } from "./admin.js";
import { ZipError, readBundle } from "./zip.js";

const DEFAULT_MAX_BYTES = 25 * 1024 * 1024;
const ID_RE = /^[a-z0-9][a-z0-9-]{0,40}$/;                   // init_kb.ID_RE
const RESERVED_IDS = new Set(["think", "demo"]);               // init_kb.RESERVED_IDS
const KIT_RE = /^[a-z0-9][a-z0-9-]{0,30}$/;
const GIT_RE = /^(https?:\/\/|ssh:\/\/|git@)[\x21-\x7e]+$/;       // import_kb.is_git_source, ASCII only (R2 metadata is 2 KiB)
const MAX_JSON = 4096;
const MAX_GIT_URL = 500;                                       // R2 customMetadata holds 2 KiB per object
const MAX_ERROR = 300;
const LIST_CAP = 1000;
const STATUSES = new Set(["pending", "imported", "failed"]);

function json(status, body) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
  });
}

function emails(value) {
  return (value || "").split(",").map((e) => e.trim().toLowerCase()).filter(Boolean);
}

function timingSafeEqual(a, b) {
  const x = new TextEncoder().encode(a), y = new TextEncoder().encode(b);
  let diff = x.length ^ y.length;
  for (let i = 0; i < Math.max(x.length, y.length); i++) diff |= (x[i] || 0) ^ (y[i] || 0);
  return diff === 0;
}

// True when the request carries the Mac's inbox token. A header that is present but wrong is a refusal, never a fallback.
function bearer(request, env) {
  const header = request.headers.get("Authorization");
  if (!header) return null;
  const m = /^Bearer\s+(\S+)$/i.exec(header);
  if (!m) return null;                                         // another scheme (a proxy's): fall through to the session
  return Boolean(env.INBOX_TOKEN && timingSafeEqual(m[1], env.INBOX_TOKEN));
}

function maxBytes(env) {
  const n = Number(env.INBOX_MAX_BYTES);
  return Number.isFinite(n) && n > 0 ? n : DEFAULT_MAX_BYTES;
}

// The body as bytes, or null when it is over `max` (checked on Content-Length first, then while reading).
async function readLimited(request, max) {
  const declared = Number(request.headers.get("Content-Length"));
  if (Number.isFinite(declared) && declared > max) return null;
  if (!request.body) return new Uint8Array(0);
  const reader = request.body.getReader();
  const chunks = [];
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.length;
    if (total > max) { await reader.cancel().catch(() => {}); return null; }
    chunks.push(value);
  }
  const out = new Uint8Array(total);
  let at = 0;
  for (const c of chunks) { out.set(c, at); at += c.length; }
  return out;
}

async function loadChecker(deps) {
  if (deps.checkBundle) return deps.checkBundle;
  try {
    return (await import("./okf.gen.js")).checkBundle;
  } catch {
    return null;
  }
}

function itemId(now) {
  const stamp = new Date(now).toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
  const rand = Array.from(crypto.getRandomValues(new Uint8Array(4)), (b) => b.toString(16).padStart(2, "0")).join("");
  return `${stamp}-${rand}`;
}

function summary(rec) {
  const s = {
    status: rec.status, kind: rec.kind, at: rec.at, uploader: rec.uploader, kb_id: rec.kb_id || "", kit: rec.kit || "",
    size: String(rec.size || 0), pages: String(rec.report ? rec.report.pages : 0),
    warnings: String(rec.report ? rec.report.warnings.length : 0),
  };
  if (rec.git_url) s.git_url = rec.git_url;
  if (rec.error) s.error = rec.error.slice(0, MAX_ERROR);
  if (rec.updated_at) s.updated_at = rec.updated_at;
  return s;
}

function fromSummary(item, meta) {
  const m = meta || {};
  const out = {
    item, status: m.status, kind: m.kind, at: m.at, uploader: m.uploader, kb_id: m.kb_id || null, kit: m.kit || null,
    size: Number(m.size || 0), pages: Number(m.pages || 0), warnings: Number(m.warnings || 0),
  };
  if (m.git_url) out.git_url = m.git_url;
  if (m.error) out.error = m.error;
  if (m.updated_at) out.updated_at = m.updated_at;
  return out;
}

async function putRecord(env, rec) {
  await env.KB_INBOX.put(`meta/${rec.item}.json`, JSON.stringify(rec), {
    httpMetadata: { contentType: "application/json" }, customMetadata: summary(rec),
  });
}

async function getRecord(env, item) {
  const obj = await env.KB_INBOX.get(`meta/${item}.json`);
  if (!obj) return null;
  try { return await obj.json(); } catch { return null; }
}

async function listItems(env, status) {
  const items = [];
  let cursor;
  let seen = 0;
  do {
    const page = await env.KB_INBOX.list({ prefix: "meta/", cursor, limit: 500, include: ["customMetadata"] });
    for (const o of page.objects || []) {
      seen++;
      const item = o.key.replace(/^meta\//, "").replace(/\.json$/, "");
      const row = fromSummary(item, o.customMetadata);
      if (!status || row.status === status) items.push(row);
    }
    cursor = page.truncated ? page.cursor : undefined;
  } while (cursor && seen < LIST_CAP);
  return items.sort((a, b) => (a.item < b.item ? 1 : -1));
}

// The upload as {kind, report, ...}. A zip is checked with the same checkBundle the browser uses; a git URL is not
// fetched here (the Mac clones it), so its report only says so.
async function inspect(request, env, deps, query) {
  const max = maxBytes(env);
  const isJson = (request.headers.get("Content-Type") || "").toLowerCase().includes("application/json");
  if (isJson) {
    let body;
    try {
      const raw = await readLimited(request, MAX_JSON);
      if (raw === null) return { status: 413, error: "a git_url body is a few hundred bytes" };
      body = JSON.parse(new TextDecoder().decode(raw));
    } catch { return { status: 400, error: "body must be JSON {git_url}" }; }
    const url = body && typeof body.git_url === "string" ? body.git_url.trim() : "";
    if (/^(https?|ssh):\/\/[^/]*@/.test(url)) return { status: 400, error: "git_url must not carry credentials (user:token@); the Mac clones with its own" };
    if (!GIT_RE.test(url) || url.length > MAX_GIT_URL) {
      return { status: 400, error: `git_url must be an https://, ssh:// or git@ URL of at most ${MAX_GIT_URL} characters` };
    }
    const name = url.split("#")[0].replace(/\/+$/, "").split(/[/:]/).pop().replace(/\.git$/, "");
    return {
      kind: "git", git_url: url, size: url.length, id: body.id, kit: body.kit, name,
      report: { id: "", pages: 0, errors: [], warnings: ["a git URL is checked on the Mac when it is imported"] },
    };
  }
  const bytes = await readLimited(request, max);
  if (bytes === null) return { status: 413, error: `upload is over the ${max} byte limit` };
  const check = await loadChecker(deps);
  if (!check) return { status: 503, error: "checker not bundled: build the Worker with the okf bundle (see publish.md)" };
  const name = query.get("name") || "";
  let report;
  try {
    report = check(await readBundle(bytes), { name });
  } catch (e) {
    if (!(e instanceof ZipError)) throw e;
    report = { id: "", pages: 0, errors: [e.message], warnings: [] };
  }
  return { kind: "zip", bytes, size: bytes.length, id: query.get("id"), kit: query.get("kit"), name, report };
}

function fields(found) {
  const id = found.id || null, kit = found.kit || null;
  if (id !== null && (typeof id !== "string" || !ID_RE.test(id) || RESERVED_IDS.has(id))) {
    return { error: `id ${JSON.stringify(id)} must be lowercase letters, digits and dashes (not think or demo)` };
  }
  if (kit !== null && (typeof kit !== "string" || !KIT_RE.test(kit))) return { error: `bad kit ${JSON.stringify(kit)}` };
  return { id, kit };
}

async function validate(request, env, deps, query) {
  const found = await inspect(request, env, deps, query);
  if (found.error) return json(found.status, { error: found.error });
  const f = fields(found);
  if (f.error) return json(400, { error: f.error });
  const { report } = found;
  return json(200, { ok: !report.errors.length && (found.kind === "git" || report.pages > 0), kind: found.kind, ...report });
}

async function create(request, env, deps, query, session) {
  const found = await inspect(request, env, deps, query);
  if (found.error) return json(found.status, { error: found.error });
  const f = fields(found);
  if (f.error) return json(400, { error: f.error });
  const { report } = found;
  if (report.errors.length) return json(422, { error: "the bundle is not valid OKF; nothing was stored", kind: found.kind, ...report });
  const kbId = f.id || report.id || null;
  if (kbId && (!ID_RE.test(kbId) || RESERVED_IDS.has(kbId))) return json(400, { error: `the kb id ${JSON.stringify(kbId)} (from the file name) is not usable: pass ?id=<kb id>` });
  const item = itemId(deps.now());
  const rec = {
    item, status: "pending", kind: found.kind, at: new Date(deps.now()).toISOString(), uploader: String(session.email).toLowerCase(),
    kb_id: kbId, kit: f.kit, size: found.size, report,
  };
  if (found.kind === "git") rec.git_url = found.git_url;
  else await env.KB_INBOX.put(`bundle/${item}.zip`, found.bytes, { httpMetadata: { contentType: "application/zip" } });
  try {
    await putRecord(env, rec);
  } catch (e) {
    if (found.kind === "zip" && env.KB_INBOX.delete) await env.KB_INBOX.delete(`bundle/${item}.zip`).catch(() => {});   // no orphan zip
    throw e;
  }
  return json(201, { item, status: "pending", kind: rec.kind, kb_id: rec.kb_id, kit: rec.kit, size: rec.size, ...report });
}

async function setStatus(request, env, deps, item, machine) {
  let body;
  try { body = await request.json(); } catch { return json(400, { error: "body must be JSON {status, kb_id?, error?}" }); }
  const status = body && body.status;
  if (!STATUSES.has(status) || (machine && status === "pending")) return json(400, { error: "status must be imported or failed" });
  const rec = await getRecord(env, item);
  if (!rec) return json(404, { error: "no such inbox item" });
  const allowed = status === "pending" ? rec.status === "failed" : rec.status === "pending";
  if (!allowed) return json(409, { error: `an item that is ${rec.status} cannot become ${status}` });
  const now = new Date(deps.now()).toISOString();
  if (status === "imported") {
    const kb = body.kb_id;
    if (typeof kb !== "string" || !ID_RE.test(kb)) return json(400, { error: "imported needs the new kb_id" });
    Object.assign(rec, { status, kb_id: kb, error: null, updated_at: now });
  } else if (status === "failed") {
    Object.assign(rec, { status, error: String(body.error || "import failed").slice(0, MAX_ERROR), updated_at: now });
  } else {
    Object.assign(rec, { status, error: null, updated_at: now });
  }
  await putRecord(env, rec);
  return json(200, fromSummary(item, summary(rec)));
}

// session: the verified kb_session payload or null. deps: {fetch, now, checkBundle?}.
export async function handleInbox(request, env, deps, session) {
  const url = new URL(request.url);
  const path = url.pathname.replace(/\/+$/, "");
  const method = request.method;
  const tokenOk = bearer(request, env);
  if (tokenOk === false) return json(401, { error: "bad inbox token" });
  const machine = tokenOk === true;
  if (!machine && !session) return json(401, { error: "sign in first" });

  const route = (() => {
    if (path === "/api/inbox/validate" && method === "POST") return { name: "validate" };
    if (path === "/api/inbox" && method === "POST") return { name: "create" };
    if (path === "/api/inbox" && method === "GET") return { name: "list" };
    const m = /^\/api\/inbox\/(\d{8}T\d{6}Z-[0-9a-f]{8})(\/bundle|\/status)?$/.exec(path);
    if (!m) return null;
    if (!m[2] && method === "GET") return { name: "get", item: m[1] };
    if (m[2] === "/bundle" && method === "GET") return { name: "bundle", item: m[1] };
    if (m[2] === "/status" && method === "POST") return { name: "status", item: m[1] };
    return null;
  })();
  if (!route) return json(404, { error: "no such inbox route" });

  const machineMay = ["list", "bundle", "status"];
  if (machine) {
    if (!machineMay.includes(route.name)) return json(403, { error: "the inbox token may only list, download and report" });
  } else if (route.name !== "list") {
    const refused = ownerGate(request, env, session);          // owner allowlist + X-KB-Admin + same Origin on writes
    if (refused) return refused;
  } else if (!emails(env.ALLOWED_EMAILS).includes(String(session.email || "").toLowerCase())
             && !emails(env.ADMIN_EMAILS).includes(String(session.email || "").toLowerCase())) {
    return json(403, { error: "not allowed" });
  }

  if (route.name === "validate") return validate(request, env, deps, url.searchParams);
  if (!env.KB_INBOX) return json(503, { error: "inbox not configured: bind an R2 bucket as KB_INBOX (see publish.md)" });
  try {
    if (route.name === "create") return await create(request, env, deps, url.searchParams, session);
    if (route.name === "list") {
      const status = url.searchParams.get("status");
      if (status && !STATUSES.has(status)) return json(400, { error: "status must be pending, imported or failed" });
      return json(200, { items: await listItems(env, status) });
    }
    if (route.name === "get") {
      const rec = await getRecord(env, route.item);
      return rec ? json(200, rec) : json(404, { error: "no such inbox item" });
    }
    if (route.name === "bundle") {
      const obj = await env.KB_INBOX.get(`bundle/${route.item}.zip`);
      if (!obj) return json(404, { error: "no stored zip for that item (a git item has none)" });
      return new Response(obj.body, { status: 200, headers: { "Content-Type": "application/zip", "Cache-Control": "no-store" } });
    }
    if (route.name === "status") return await setStatus(request, env, deps, route.item, machine);
  } catch (e) {
    console.error("inbox failed", e && e.stack ? e.stack : e);
    return json(500, { error: "inbox storage failed" });
  }
  return json(404, { error: "no such inbox route" });
}
