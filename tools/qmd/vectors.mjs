// Our own copy of the card vectors, for graph math (nearest pages, link closeness) — qmd keeps its vectors
// inside its index and only answers text queries. Same cards (`.cache/qmd-cards/`), same GGUF model and
// engine (node-llama-cpp) as the search service, so both see the same geometry.
//
//   node tools/qmd/vectors.mjs           (pixi run vectors-build; run after `qmd-cards`, i.e. after lint)
//
// Writes `.cache/vectors.sqlite`: vectors(slug PRIMARY KEY, hash, model, dim, vec BLOB float32, at).
// Only cards whose text changed are re-embedded; cards that disappeared are deleted; a different model
// re-embeds everything. Paths come from KB_ROOT (default: the checkout this file lives in).
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";
import { DatabaseSync } from "node:sqlite";
import { getLlama, resolveModelFile } from "node-llama-cpp";

const ROOT = process.env.KB_ROOT || path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const CACHE = path.join(ROOT, ".cache");
const CARDS = path.join(CACHE, "qmd-cards");
const MODEL = process.env.QMD_EMBED_MODEL || "hf:Qwen/Qwen3-Embedding-0.6B-GGUF/Qwen3-Embedding-0.6B-Q8_0.gguf";

const db = new DatabaseSync(path.join(CACHE, "vectors.sqlite"));
db.exec(`CREATE TABLE IF NOT EXISTS vectors (slug TEXT PRIMARY KEY, hash TEXT NOT NULL, model TEXT NOT NULL,
         dim INTEGER NOT NULL, vec BLOB NOT NULL, at TEXT NOT NULL)`);

const cards = Object.fromEntries(fs.readdirSync(CARDS).filter((f) => f.endsWith(".md")).map((f) => {
  const text = fs.readFileSync(path.join(CARDS, f), "utf8").trim();
  return [f.slice(0, -3), { text, hash: crypto.createHash("sha256").update(text).digest("hex").slice(0, 16) }];
}));
const have = Object.fromEntries(db.prepare("SELECT slug, hash, model FROM vectors").all().map((r) => [r.slug, r]));
const todo = Object.keys(cards).filter((s) => have[s]?.hash !== cards[s].hash || have[s]?.model !== MODEL);
const gone = Object.keys(have).filter((s) => !(s in cards));

for (const s of gone) db.prepare("DELETE FROM vectors WHERE slug = ?").run(s);
if (todo.length) {
  // the GGUF the search service already downloaded (same cache dir), else fetch it once
  const modelPath = await resolveModelFile(MODEL, path.join(CACHE, "qmd", "models"));
  const llama = await getLlama();
  const model = await llama.loadModel({ modelPath });
  const ctx = await model.createEmbeddingContext();
  const put = db.prepare("INSERT OR REPLACE INTO vectors (slug, hash, model, dim, vec, at) VALUES (?, ?, ?, ?, ?, ?)");
  const t0 = Date.now();
  for (const s of todo) {
    const v = Float32Array.from((await ctx.getEmbeddingFor(cards[s].text)).vector);
    put.run(s, cards[s].hash, MODEL, v.length, Buffer.from(v.buffer), new Date().toISOString());
  }
  console.log(`embedded ${todo.length} card(s) in ${((Date.now() - t0) / 1000).toFixed(1)}s`);
  await ctx.dispose(); await model.dispose(); await llama.dispose();
}
const n = db.prepare("SELECT COUNT(*) AS n FROM vectors").get().n;
console.log(`vectors: ${n} (${todo.length} embedded, ${gone.length} removed) → ${path.join(CACHE, "vectors.sqlite")}`);
db.close();
