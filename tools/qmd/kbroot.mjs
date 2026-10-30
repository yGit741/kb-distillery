// The knowledge base the qmd tools work on: $KB_ROOT, set by tools/qmd/with-kb.sh (pixi tasks) or
// tools/launch.sh from `python -m kb.kbconfig root` — the one resolver for --kb / $KB.
// There is no fallback to the checkout this file lives in: since the kb split the explorer holds no vault,
// and guessing it silently built and read caches in the wrong folder.
import fs from "node:fs";
import path from "node:path";

export function kbRoot(env = process.env) {
  const root = env.KB_ROOT;
  if (!root) {
    throw new Error("KB_ROOT is not set — run through `pixi run vectors-build|qmd-serve [-- --kb <id>]`, "
      + "or `bash tools/qmd/with-kb.sh <script.mjs>`");
  }
  if (!fs.existsSync(path.join(root, "wiki")) && !fs.existsSync(path.join(root, "kb.toml"))) {
    throw new Error(`KB_ROOT=${root} is not a knowledge base (no wiki/ or kb.toml)`);
  }
  return path.resolve(root);
}
