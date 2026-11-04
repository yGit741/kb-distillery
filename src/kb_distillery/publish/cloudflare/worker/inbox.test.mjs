// node --test inbox — the upload inbox (inbox.js, zip.js) through auth.js's handle().
// R2 is an in-memory mock, the checker is the real bundle (`pixi run worker-bundle` writes okf.gen.js); no network.
import { test } from "node:test";
import assert from "node:assert/strict";
import { deflateRawSync } from "node:zlib";
import { handle } from "./auth.js";
import { readBundle, ZipError } from "./zip.js";

const ORIGIN = "https://kb.example.workers.dev";
const SECRET = "test-session-secret";
const TOKEN = "mac-inbox-token";
const NOW = 1_800_000_000_000;
const enc = new TextEncoder();
const b64url = (bytes) => Buffer.from(bytes).toString("base64url");

async function session(email) {
  const body = b64url(enc.encode(JSON.stringify({ email, iat: NOW / 1000, exp: NOW / 1000 + 3600 })));
  const key = await crypto.subtle.importKey("raw", enc.encode(SECRET), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return `kb_session=${body}.${b64url(await crypto.subtle.sign("HMAC", key, enc.encode(body)))}`;
}

// ---------- a tiny zip writer (the tests build their own archives) ----------

const CRC = (() => { const t = []; for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; } return t; })();
function crc32(buf) { let c = 0xffffffff; for (const b of buf) c = CRC[(c ^ b) & 0xff] ^ (c >>> 8); return (c ^ 0xffffffff) >>> 0; }

// entries: {name, data?: string|Uint8Array, stored?, mode?, usize?}  (mode = unix st_mode, e.g. 0o120777 for a symlink)
function zip(entries) {
  const locals = [], centrals = [];
  let offset = 0;
  for (const e of entries) {
    const name = Buffer.from(e.name);
    const raw = Buffer.from(e.data ?? "");
    const body = e.stored ? raw : deflateRawSync(raw);
    const method = e.stored ? 0 : 8;
    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50, 0); local.writeUInt16LE(20, 4); local.writeUInt16LE(method, 8);
    local.writeUInt32LE(crc32(raw), 14); local.writeUInt32LE(body.length, 18); local.writeUInt32LE(e.usize ?? raw.length, 22);
    local.writeUInt16LE(name.length, 26);
    const central = Buffer.alloc(46);
    central.writeUInt32LE(0x02014b50, 0); central.writeUInt16LE(0x031e, 4); central.writeUInt16LE(20, 6);
    central.writeUInt16LE(method, 10); central.writeUInt32LE(crc32(raw), 16); central.writeUInt32LE(body.length, 20);
    central.writeUInt32LE(e.usize ?? raw.length, 24); central.writeUInt16LE(name.length, 28);
    central.writeUInt32LE(((e.mode ?? 0o100644) << 16) >>> 0, 38); central.writeUInt32LE(offset, 42);
    locals.push(local, name, body);
    centrals.push(central, name);
    offset += 30 + name.length + body.length;
  }
  const cd = Buffer.concat(centrals);
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0); end.writeUInt16LE(entries.length, 8); end.writeUInt16LE(entries.length, 10);
  end.writeUInt32LE(cd.length, 12); end.writeUInt32LE(offset, 16);
  return new Uint8Array(Buffer.concat([...locals, cd, end]));
}

const PAGE = "---\ntype: idea\n---\n\nhello\n";
const BAD_PAGE = "---\ntype: idea\n---\n\n[x](gone.md)\n";
const good = () => zip([{ name: "a.md", data: PAGE }, { name: "sub/b.md", data: PAGE }]);

// ---------- mocked R2 ----------

function r2() {
  const store = new Map();
  const object = (key, v) => ({
    key, customMetadata: v.customMetadata, body: new Blob([v.bytes]).stream(),
    json: async () => JSON.parse(new TextDecoder().decode(v.bytes)),
    arrayBuffer: async () => v.bytes.buffer,
  });
  return {
    store,
    async put(key, value, opts = {}) {
      store.set(key, { bytes: typeof value === "string" ? enc.encode(value) : new Uint8Array(value), customMetadata: opts.customMetadata });
    },
    async get(key) { return store.has(key) ? object(key, store.get(key)) : null; },
    async list({ prefix = "", cursor, limit = 1000 } = {}) {
      const keys = [...store.keys()].filter((k) => k.startsWith(prefix)).sort();
      const from = cursor ? Number(cursor) : 0;
      const page = keys.slice(from, from + limit);
      return {
        objects: page.map((k) => ({ key: k, customMetadata: store.get(k).customMetadata })),
        truncated: from + limit < keys.length, cursor: String(from + limit),
      };
    },
  };
}

function env(extra = {}) {
  return {
    ASSETS: { fetch: async () => new Response("asset") },
    GOOGLE_CLIENT_ID: "cid", GOOGLE_CLIENT_SECRET: "shh", SESSION_SECRET: SECRET,
    ALLOWED_EMAILS: "me@example.com,viewer@example.com", ADMIN_EMAILS: "me@example.com", INBOX_TOKEN: TOKEN,
    KB_INBOX: r2(), ...extra,
  };
}

async function call(e, method, path, { body, as = "me@example.com", headers = {}, type } = {}) {
  const h = { ...headers };
  if (as) h.Cookie = await session(as);
  if (method !== "GET") { h["X-KB-Admin"] = "1"; h.Origin = ORIGIN; }
  if (type) h["Content-Type"] = type;
  if (as === "me@example.com" && method === "GET") h["X-KB-Admin"] = "1";
  const init = { method, headers: h };
  if (body !== undefined) init.body = body;
  return handle(new Request(ORIGIN + path, init), e, { now: () => NOW });
}
const mac = (e, method, path, body) => call(e, method, path, {
  as: null, headers: { Authorization: `Bearer ${TOKEN}` }, body: body && JSON.stringify(body), type: body && "application/json",
});

// ---------- zip.js ----------

test("readBundle descends into one top folder and drops junk", async () => {
  const files = await readBundle(zip([
    { name: "kb/", data: "" }, { name: "kb/wiki/a.md", data: PAGE }, { name: "kb/wiki/sub/b.md", data: PAGE, stored: true },
    { name: "__MACOSX/kb/._a.md", data: "x" }, { name: "kb/.DS_Store", data: "x" }, { name: "kb/raw/r.md", data: "x" },
  ]));
  assert.deepEqual([...files.keys()].sort(), ["a.md", "sub/b.md"]);
  assert.equal(new TextDecoder().decode(files.get("a.md")), PAGE);
});

test("readBundle takes a flat zip as the bundle root", async () => {
  const files = await readBundle(zip([{ name: "x.md", data: PAGE }, { name: "y/z.md", data: PAGE }]));
  assert.deepEqual([...files.keys()].sort(), ["x.md", "y/z.md"]);
});

for (const [label, entry, message] of [
  ["a parent folder", { name: "../evil.md" }, /unsafe path in zip: '..\/evil.md'/],
  ["a nested ..", { name: "wiki/a/../../x.md" }, /unsafe path/],
  ["a backslash ..", { name: "wiki\\..\\x.md" }, /unsafe path/],
  ["an absolute path", { name: "/etc/x.md" }, /unsafe path/],
  ["a drive letter", { name: "C:\\x.md" }, /unsafe path/],
  ["a symlink", { name: "wiki/link.md", mode: 0o120777, data: "../../x" }, /is a symlink/],
]) {
  test(`readBundle refuses ${label}`, async () => {
    await assert.rejects(readBundle(zip([{ name: "wiki/a.md", data: PAGE }, entry])), (e) => e instanceof ZipError && message.test(e.message));
  });
}

test("readBundle refuses a lying header, too many entries, a huge file and non-zips", async () => {
  await assert.rejects(readBundle(zip([{ name: "a.md", data: "x".repeat(2000), usize: 10 }])), /past its declared size|corrupt/);
  await assert.rejects(readBundle(good(), { maxEntries: 1, maxFileBytes: 1e6, maxTotalBytes: 1e6 }), /2 entries/);
  await assert.rejects(readBundle(zip([{ name: "a.md", data: "x".repeat(100) }]), { maxEntries: 9, maxFileBytes: 50, maxTotalBytes: 1e6 }), /per-file limit/);
  await assert.rejects(readBundle(zip([{ name: "a.md", data: "x".repeat(60) }, { name: "b.md", data: "x".repeat(60) }]),
                                  { maxEntries: 9, maxFileBytes: 100, maxTotalBytes: 100 }), /unpacks to more than/);
  await assert.rejects(readBundle(enc.encode("this is not a zip at all, just text")), /not a readable zip/);
});

// ---------- auth ----------

test("every inbox route needs a session or the inbox token", async () => {
  const e = env();
  for (const [method, path] of [["GET", "/api/inbox"], ["POST", "/api/inbox"], ["POST", "/api/inbox/validate"],
                                ["GET", "/api/inbox/20261001T000000Z-abcdef01"]]) {
    const res = await call(e, method, path, { as: null });
    assert.equal(res.status, 401, `${method} ${path}`);
  }
  assert.equal((await call(e, "GET", "/api/inbox", { as: null, headers: { Authorization: "Bearer wrong" } })).status, 401);
  assert.equal((await mac(env({ INBOX_TOKEN: undefined }), "GET", "/api/inbox")).status, 401);   // no token configured: nobody holds it
});

test("only the owner allowlist writes; a viewer may list", async () => {
  const e = env();
  const viewer = { as: "viewer@example.com" };
  assert.equal((await call(e, "POST", "/api/inbox", { ...viewer, body: good(), type: "application/zip" })).status, 403);
  assert.equal((await call(e, "POST", "/api/inbox/validate", { ...viewer, body: good() })).status, 403);
  assert.equal((await call(e, "GET", "/api/inbox", viewer)).status, 200);
  assert.equal((await call(e, "GET", "/api/inbox", { as: "stranger@example.com" })).status, 403);
  assert.equal(e.KB_INBOX.store.size, 0);
});

test("a write from another origin, or without the admin header, is refused", async () => {
  const e = env();
  const cookie = await session("me@example.com");
  const post = (headers) => handle(new Request(ORIGIN + "/api/inbox", { method: "POST", body: good(), headers: { Cookie: cookie, ...headers } }), e, { now: () => NOW });
  assert.equal((await post({ "X-KB-Admin": "1", Origin: "https://evil.example" })).status, 403);
  assert.equal((await post({ Origin: ORIGIN })).status, 403);
  assert.equal(e.KB_INBOX.store.size, 0);
});

test("the inbox token cannot upload", async () => {
  const res = await call(env(), "POST", "/api/inbox", { as: null, headers: { Authorization: `Bearer ${TOKEN}` }, body: good() });
  assert.equal(res.status, 403);
});

// ---------- validate / upload ----------

test("validate returns the checker report and stores nothing", async () => {
  const e = env();
  const ok = await call(e, "POST", "/api/inbox/validate?name=My%20Notes", { body: good() });
  assert.equal(ok.status, 200);
  assert.deepEqual(await ok.json(), { ok: true, kind: "zip", id: "my-notes", pages: 2, errors: [], warnings: [] });
  const bad = await call(e, "POST", "/api/inbox/validate", { body: zip([{ name: "a.md", data: BAD_PAGE }]) });
  const report = await bad.json();
  assert.equal(report.ok, false);
  assert.deepEqual(report.errors, ["wiki/a.md: [link] unresolved: gone.md"]);
  const slip = await call(e, "POST", "/api/inbox/validate", { body: zip([{ name: "../x.md", data: PAGE }]) });
  assert.match((await slip.json()).errors[0], /unsafe path in zip/);
  assert.equal(e.KB_INBOX.store.size, 0);
});

test("validate works with no bucket bound", async () => {
  const res = await call(env({ KB_INBOX: undefined }), "POST", "/api/inbox/validate", { body: good() });
  assert.equal(res.status, 200);
  assert.equal((await call(env({ KB_INBOX: undefined }), "POST", "/api/inbox", { body: good() })).status, 503);
});

test("upload stores the zip and a pending record with uploader, time and report", async () => {
  const e = env();
  const res = await call(e, "POST", "/api/inbox?id=my-kb&kit=research&name=ignored", { body: good(), type: "application/zip" });
  assert.equal(res.status, 201);
  const made = await res.json();
  assert.equal(made.status, "pending");
  assert.match(made.item, /^20270115T080000Z-[0-9a-f]{8}$/);
  assert.equal(made.kb_id, "my-kb");
  const rec = await (await e.KB_INBOX.get(`meta/${made.item}.json`)).json();
  assert.equal(rec.uploader, "me@example.com");
  assert.equal(rec.at, new Date(NOW).toISOString());
  assert.equal(rec.kit, "research");
  assert.equal(rec.report.pages, 2);
  assert.deepEqual([...e.KB_INBOX.store.keys()].sort(), [`bundle/${made.item}.zip`, `meta/${made.item}.json`]);
  assert.deepEqual(e.KB_INBOX.store.get(`bundle/${made.item}.zip`).bytes, good());
  const list = await (await call(e, "GET", "/api/inbox")).json();
  assert.equal(list.items.length, 1);
  assert.deepEqual({ ...list.items[0], at: undefined }, { item: made.item, status: "pending", kind: "zip", at: undefined, uploader: "me@example.com",
                                                          kb_id: "my-kb", kit: "research", size: good().length, pages: 2, warnings: 0, name: "ignored" });
});

test("the id and name come from the file name without its extension, like the local import", async () => {
  const e = env();
  const res = await call(e, "POST", "/api/inbox/validate?name=bad-notes.zip", { body: good(), type: "application/zip" });
  const report = await res.json();
  assert.equal(report.id, "bad-notes");
  assert.equal(report.name, "Bad notes");
  const made = await (await call(e, "POST", "/api/inbox?name=bad-notes.zip", { body: good(), type: "application/zip" })).json();
  assert.equal(made.kb_id, "bad-notes");
  const list = await (await call(e, "GET", "/api/inbox")).json();
  assert.equal(list.items[0].name, "bad-notes.zip");                 // the Mac records it as the import's source
});

test("an invalid or unsafe zip is refused with its report and nothing is stored", async () => {
  const e = env();
  const bad = await call(e, "POST", "/api/inbox", { body: zip([{ name: "a.md", data: BAD_PAGE }]) });
  assert.equal(bad.status, 422);
  assert.deepEqual((await bad.json()).errors, ["wiki/a.md: [link] unresolved: gone.md"]);
  const slip = await call(e, "POST", "/api/inbox", { body: zip([{ name: "wiki/a.md", data: PAGE }, { name: "../../x.md", data: "x" }]) });
  assert.equal(slip.status, 422);
  assert.equal(e.KB_INBOX.store.size, 0);
});

test("bad ids and kits are refused", async () => {
  const e = env();
  for (const q of ["id=Bad_Id", "id=think", "id=-x", "kit=../x"]) {
    assert.equal((await call(e, "POST", `/api/inbox?${q}`, { body: good() })).status, 400, q);
  }
  assert.equal(e.KB_INBOX.store.size, 0);
});

test("the size limit is enforced on Content-Length and on the bytes read", async () => {
  const e = env({ INBOX_MAX_BYTES: "100" });
  const big = good();
  assert.ok(big.length > 100);
  assert.equal((await call(e, "POST", "/api/inbox", { body: big, headers: { "Content-Length": String(big.length) } })).status, 413);
  const stream = new ReadableStream({ start(c) { c.enqueue(big.subarray(0, 80)); c.enqueue(big.subarray(80)); c.close(); } });
  const res = await handle(new Request(ORIGIN + "/api/inbox", { method: "POST", body: stream, duplex: "half",
    headers: { Cookie: await session("me@example.com"), "X-KB-Admin": "1", Origin: ORIGIN } }), e, { now: () => NOW });
  assert.equal(res.status, 413);
  assert.equal(e.KB_INBOX.store.size, 0);
});

test("a git URL is only recorded", async () => {
  const e = env();
  let fetched = 0;
  const body = JSON.stringify({ git_url: "https://github.com/octocat/notes.git#main", id: "octo-notes" });
  const res = await handle(new Request(ORIGIN + "/api/inbox", { method: "POST", body, headers: {
    Cookie: await session("me@example.com"), "X-KB-Admin": "1", Origin: ORIGIN, "Content-Type": "application/json" } }), e,
    { now: () => NOW, fetch: async () => { fetched++; throw new Error("no network"); } });
  assert.equal(res.status, 201);
  const made = await res.json();
  assert.equal(made.kind, "git");
  assert.equal(fetched, 0);
  const keys = [...e.KB_INBOX.store.keys()];
  assert.deepEqual(keys, [`meta/${made.item}.json`]);                       // no zip for a git item
  const rec = await (await e.KB_INBOX.get(keys[0])).json();
  assert.equal(rec.git_url, "https://github.com/octocat/notes.git#main");
  assert.equal(rec.kb_id, "octo-notes");
  const list = await (await mac(e, "GET", "/api/inbox?status=pending")).json();
  assert.equal(list.items[0].git_url, rec.git_url);
});

test("a git URL must look like one", async () => {
  const e = env();
  for (const git_url of ["file:///etc/passwd", "--upload-pack=x", "ftp://x/y", "https://x/y z", "", 5, "https://x/" + "a".repeat(600)]) {
    const res = await call(e, "POST", "/api/inbox", { body: JSON.stringify({ git_url }), type: "application/json" });
    assert.equal(res.status, 400, String(git_url).slice(0, 30));
  }
  assert.equal(e.KB_INBOX.store.size, 0);
});

// ---------- the Mac: list, download, report ----------

async function upload(e, q = "") {
  const res = await call(e, "POST", `/api/inbox${q}`, { body: good() });
  return (await res.json()).item;
}

test("the Mac lists pending items, downloads the zip and reports imported or failed", async () => {
  const e = env();
  const a = await upload(e, "?id=first-kb");
  const b = await upload(e, "?id=second-kb");
  const pending = await (await mac(e, "GET", "/api/inbox?status=pending")).json();
  assert.equal(pending.items.length, 2);
  const zipRes = await mac(e, "GET", `/api/inbox/${a}/bundle`);
  assert.equal(zipRes.status, 200);
  assert.deepEqual(new Uint8Array(await zipRes.arrayBuffer()), good());

  const done = await mac(e, "POST", `/api/inbox/${a}/status`, { status: "imported", kb_id: "first-kb" });
  assert.equal(done.status, 200);
  assert.equal((await done.json()).status, "imported");
  const failed = await mac(e, "POST", `/api/inbox/${b}/status`, { status: "failed", error: "a knowledge base 'second-kb' already exists" });
  assert.equal(failed.status, 200);

  assert.deepEqual((await (await mac(e, "GET", "/api/inbox?status=pending")).json()).items, []);
  const all = (await (await mac(e, "GET", "/api/inbox")).json()).items;
  assert.deepEqual(all.map((i) => [i.item, i.status]), [[b, "failed"], [a, "imported"]].sort((x, y) => (x[0] < y[0] ? 1 : -1)));
  assert.match(all.find((i) => i.item === b).error, /already exists/);
  const full = await (await call(e, "GET", `/api/inbox/${a}`)).json();
  assert.equal(full.status, "imported");
  assert.equal(full.report.pages, 2);
});

test("status changes are validated", async () => {
  const e = env();
  const a = await upload(e);
  assert.equal((await mac(e, "POST", `/api/inbox/${a}/status`, { status: "imported" })).status, 400);              // needs kb_id
  assert.equal((await mac(e, "POST", `/api/inbox/${a}/status`, { status: "imported", kb_id: "Bad Id" })).status, 400);
  assert.equal((await mac(e, "POST", `/api/inbox/${a}/status`, { status: "pending" })).status, 400);               // the Mac cannot re-pend
  assert.equal((await mac(e, "POST", `/api/inbox/${a}/status`, { status: "done" })).status, 400);
  assert.equal((await mac(e, "POST", "/api/inbox/20260101T000000Z-00000000/status", { status: "failed" })).status, 404);
  await mac(e, "POST", `/api/inbox/${a}/status`, { status: "failed", error: "boom" });
  assert.equal((await mac(e, "POST", `/api/inbox/${a}/status`, { status: "imported", kb_id: "x" })).status, 409);  // only pending moves on
  const retry = await call(e, "POST", `/api/inbox/${a}/status`, { body: JSON.stringify({ status: "pending" }), type: "application/json" });
  assert.equal(retry.status, 200);                                                                                  // the owner may retry a failure
  assert.equal((await mac(e, "GET", "/api/inbox?status=pending")).status, 200);
});

test("unknown inbox routes and ids are 404", async () => {
  const e = env();
  assert.equal((await call(e, "GET", "/api/inbox/nope")).status, 404);
  assert.equal((await call(e, "GET", "/api/inbox/20260101T000000Z-00000000")).status, 404);
  assert.equal((await mac(e, "GET", "/api/inbox/20260101T000000Z-00000000/bundle")).status, 404);
  assert.equal((await call(e, "DELETE", "/api/inbox")).status, 404);
});

test("an unbound bucket answers 503 for list and upload", async () => {
  const e = env({ KB_INBOX: undefined });
  assert.equal((await call(e, "GET", "/api/inbox")).status, 503);
  assert.equal((await mac(e, "GET", "/api/inbox?status=pending")).status, 503);
});

test("a git URL with credentials, or a non-ASCII one, is refused", async () => {
  const e = env();
  for (const git_url of ["https://user:tok@github.com/o/r.git", "ssh://git:x@host/r", "https://example.com/é"]) {
    const res = await call(e, "POST", "/api/inbox", { body: JSON.stringify({ git_url }), type: "application/json" });
    assert.equal(res.status, 400, git_url);
  }
  const ssh = await call(e, "POST", "/api/inbox", { body: JSON.stringify({ git_url: "git@github.com:o/r.git" }), type: "application/json" });
  assert.equal(ssh.status, 201);                                                     // the scp form's git@ is not a credential
});

test("a foreign Authorization scheme falls through to the session; a derived reserved id is refused", async () => {
  const e = env();
  const res = await call(e, "GET", "/api/inbox", { headers: { Authorization: "Basic abc" } });
  assert.equal(res.status, 200);
  assert.equal((await call(e, "POST", "/api/inbox?name=think", { body: good() })).status, 400);
  assert.equal((await call(e, "POST", "/api/inbox?name=think&id=mine", { body: good() })).status, 201);
});

test("folder entries count when the bundle root is chosen, as on the Mac", async () => {
  const files = await readBundle(zip([{ name: "a/x.md", data: PAGE }, { name: "b/", data: "" }]));
  assert.deepEqual([...files.keys()], ["a/x.md"]);                                  // two top-level names: no descent
});

// ---------- access: who may add, and is the inbox ready (the site's entry reads this) ----------

test("access says owner and inbox for an owner, with no admin header", async () => {
  const e = env();
  const res = await handle(new Request(ORIGIN + "/api/inbox/access", { headers: { Cookie: await session("me@example.com") } }), e, { now: () => NOW });
  assert.equal(res.status, 200);
  assert.deepEqual(await res.json(), { owner: true, inbox: true });
});

test("access says owner false for a signed-in viewer who is not an owner", async () => {
  const res = await call(env(), "GET", "/api/inbox/access", { as: "viewer@example.com" });
  assert.equal(res.status, 200);
  assert.deepEqual(await res.json(), { owner: false, inbox: true });
});

test("access says inbox false when no bucket is bound, and needs a session", async () => {
  const res = await call(env({ KB_INBOX: undefined }), "GET", "/api/inbox/access");
  assert.deepEqual(await res.json(), { owner: true, inbox: false });
  assert.equal((await call(env(), "GET", "/api/inbox/access", { as: null })).status, 401);
  assert.equal((await mac(env(), "GET", "/api/inbox/access")).status, 403);
});
