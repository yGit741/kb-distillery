// Long-running qmd search service for the KB app: search over `.cache/qmd-cards/` — one card per page
// holding its title and `summary:` line, written by `python -m kb.search.cards` (lint runs it in the main
// checkout). The embedding model loads once and stays warm, so a fast query takes tens of milliseconds
// instead of the 10-20 s a fresh `qmd` CLI call needs.
//
//   node tools/qmd/server.mjs            (pixi run qmd-serve; `pixi run launch` starts it when installed)
//   GET  /health                         {ok, ready, refreshing, model, root, last}
//   GET  /search?q=…&limit=10&mode=fast  {query, mode, ms, hits: [{slug, score}]}; 503 while not ready
//        fast (default): BM25 + vector over the cards, fused — no LLM
//        deep: qmd's full pipeline — LLM query expansion + re-ranking; better, but seconds per new query
//   POST /refresh  (header X-KB-Refresh: 1)   re-index changed cards and embed them (also every 10 min)
//
// Binds 127.0.0.1 and answers only requests addressed to it (Host check, no browser Origin), so a web
// page cannot read the vault through it. The knowledge base is $KB_ROOT (tools/qmd/kbroot.mjs): `pixi run qmd-serve
// [-- --kb <id>]` and `pixi run launch` set it; there is no default.
import http from "node:http";
import path from "node:path";
import fs from "node:fs";
import { kbRoot } from "./kbroot.mjs";

const ROOT = kbRoot();
const CACHE = path.join(ROOT, ".cache");
const CARDS = path.join(CACHE, "qmd-cards");
const PORT = Number(process.env.KB_QMD_PORT || 8766);
const HOSTS = new Set([`127.0.0.1:${PORT}`, `localhost:${PORT}`]);
const REFRESH_MS = 10 * 60 * 1000;
// Qwen3-Embedding covers Hebrew (qmd's default embeddinggemma is English-optimized); models are cached
// under .cache/qmd/models through XDG_CACHE_HOME, so nothing lands in the user's home cache.
process.env.QMD_EMBED_MODEL ||= "hf:Qwen/Qwen3-Embedding-0.6B-GGUF/Qwen3-Embedding-0.6B-Q8_0.gguf";
process.env.XDG_CACHE_HOME ||= CACHE;

const { createStore } = await import("@tobilu/qmd");
fs.mkdirSync(CARDS, { recursive: true });
if (!fs.readdirSync(CARDS).some((f) => f.endsWith(".md"))) {
  console.warn(`[kb-qmd] no cards in ${CARDS} — search stays empty until \`pixi run qmd-cards\` (or lint) runs for this kb`);
}
const store = await createStore({
  dbPath: path.join(CACHE, "qmd", "index.sqlite"),
  config: { collections: { cards: { path: CARDS, pattern: "*.md" } } },
});

// One model-touching job at a time: llama contexts are not re-entrant.
let chain = Promise.resolve();
const serial = (fn) => (chain = chain.then(fn, fn));

// Searches are refused (503) until the first refresh and warm-up are done and while a refresh runs, so
// the app falls back to keyword hits at once instead of queueing behind minutes of embedding.
let ready = false, refreshing = false, dirty = false, last = null;
async function refresh() {
  if (refreshing) { dirty = true; return last; }       // run once more when this one ends
  refreshing = true;
  try {
    do {
      dirty = false;
      const u = await serial(() => store.update({}));
      if (u.needsEmbedding) await serial(() => store.embed({}));
      last = { at: new Date().toISOString(), indexed: u.indexed, updated: u.updated, removed: u.removed,
               embedded: u.needsEmbedding };
      log(`refresh ${JSON.stringify(last)}`);
    } while (dirty);
    return last;
  } finally {
    refreshing = false;
  }
}

const slugOf = (r) => path.basename(String(r.file || r.displayPath || r.path || "").split("?")[0]).replace(/\.md$/, "");
const log = (m) => console.log(`[kb-qmd ${new Date().toISOString()}] ${m}`);
const send = (res, code, body) => {
  if (res.destroyed) return;
  res.writeHead(code, { "content-type": "application/json; charset=utf-8" });
  res.end(JSON.stringify(body));
};

const server = http.createServer(async (req, res) => {
  if (!HOSTS.has(req.headers.host || "") || req.headers.origin) return send(res, 403, { error: "forbidden" });
  const url = new URL(req.url, `http://127.0.0.1:${PORT}`);
  let gone = false;                                    // the client timed out: skip its queued work
  res.on("close", () => { if (!res.writableFinished) gone = true; });
  try {
    if (req.method === "GET" && url.pathname === "/health") {
      return send(res, 200, { ok: true, ready, refreshing, model: process.env.QMD_EMBED_MODEL, root: ROOT, last });
    }
    if (req.method === "GET" && url.pathname === "/search") {
      if (!ready || refreshing) return send(res, 503, { error: ready ? "refreshing" : "warming up" });
      const q = (url.searchParams.get("q") || "").trim().slice(0, 300);
      const limit = Math.min(Number(url.searchParams.get("limit")) || 10, 50);
      if (q.length < 2) return send(res, 200, { query: q, hits: [] });
      const mode = url.searchParams.get("mode") === "deep" ? "deep" : "fast";
      const t0 = Date.now();
      const rs = await serial(() => gone ? [] : mode === "deep"
        ? store.search({ query: q, limit })
        : store.search({ queries: [{ type: "lex", query: q }, { type: "vec", query: q }], limit, rerank: false }));
      const hits = rs.map((r) => ({ slug: slugOf(r), score: Math.round((r.score ?? 0) * 1000) / 1000 }))
                     .filter((h) => h.slug);
      return send(res, 200, { query: q, mode, ms: Date.now() - t0, hits });
    }
    if (req.method === "POST" && url.pathname === "/refresh") {
      if (req.headers["x-kb-refresh"] !== "1") return send(res, 403, { error: "missing X-KB-Refresh header" });
      refresh().catch((e) => log(`refresh failed: ${e?.stack || e}`));
      return send(res, 202, { ok: true, refreshing: true });
    }
    send(res, 404, { error: "not found" });
  } catch (e) {
    log(`error ${req.method} ${url.pathname}: ${e?.stack || e}`);
    send(res, 500, { error: String(e?.message || e).slice(0, 300) });
  }
});

server.on("error", (e) => { log(`cannot listen on 127.0.0.1:${PORT}: ${e.message}`); process.exit(1); });
server.listen(PORT, "127.0.0.1", () => log(`listening on http://127.0.0.1:${PORT} (root ${ROOT})`));
refresh()
  .then(() => serial(() => store.searchVector("warm up", { limit: 1 })))   // load the model before the first user query
  .then(() => { ready = true; log("ready"); })
  .catch((e) => log(`first refresh failed: ${e?.stack || e}`));
setInterval(() => refresh().catch((e) => log(`refresh failed: ${e}`)), REFRESH_MS).unref();
for (const sig of ["SIGINT", "SIGTERM"]) process.on(sig, async () => { server.close(); await store.close(); process.exit(0); });
