# Cite code from a knowledge base

`distill code` turns git repositories (or a folder of code) into a deterministic IR, a typed graph of files, includes, symbols, calls and history, then cuts it into **cards**: markdown fact tables where every row has a fact id (`F` and five hex digits) and a permalink at a pinned commit. A wiki page cites a fact by id. No model and no network: the same commits always give the same output, so two builds can be diffed to find the claims that went stale.

Tiers: any git repo (files, history, co-change, CODEOWNERS), C and C++ (tree-sitter, optional), Python (the standard `ast`). C++ needs the extra: `pip install "kb-distillery[code]"`; the Python tier and everything else work without it.

## A project

In the kb's `kb.toml`, or in a YAML or TOML file you pass to each command:

```toml
[code]
name = "my-service"
tiers = ["python", "cpp"]        # default: both
repos_dir = "~/code"             # checkouts at <repos_dir>/<name>, unless a repo gives `path`

[[code.repos]]
name = "core"
role = "focus"                   # focus: every layer and its own cards; platform: symbols and calls; neighbour: files and includes

[[code.repos]]
name = "shared"
role = "platform"
include_prefix = "shared"        # `#include "shared/x.h"` names x.h of this repo
```

Permalinks come from `git remote get-url origin` (credentials dropped): GitHub form `/blob/<sha>/path#L3-L9`, GitLab form `/-/blob/<sha>/path#L3-9`, chosen by the host name or `style = "github" | "gitlab"`. Give `remote` or `web` per repo to override, or a `[code.permalink]` table (`blob`, `tree`, `range`, `pull` patterns) for any other host. A repo with no remote has no links: its facts keep the `path:line` label. A plain folder (`git = false`, with `web` for where its files open) is pinned by its content and has no history.

## Commands

| Command | Does |
|---|---|
| `distill code build [project]` | `<out>/ir.json` and `ir.db` (SQLite), with drift warnings; `<out>` defaults to `<kb>/.local/code/<name>` |
| `distill code cards [project]` | `<out>/cards/*.md` and `index.json` |
| `distill code stale <old_out> <new_out>` | `<new_out>/staleness.json`: facts added, removed, or only moved (line numbers); `fact_ids_gone` lists the ids a page may still cite |
| `distill code export [project]` | cards into `raw/printed-docs/ir-*.md` as one `kb(catalog)` step, and the artifact graph into `artifacts/graph.json` |
| `distill code kb [project]` | build, cards, export and check-cites |
| `distill code cite --check [page ...]` | what each `{{card:Fid}}` placeholder would expand to (writes nothing); `--refresh` re-points cited facts at the current export |
| `distill code check-cites` | every cited fact still exists in its card, and its links are that fact's anchors |

Pass `--kb <id|path>` after the command to pick the knowledge base. To rebuild at another commit without touching the checkout, build the old side with `KB_CODE_REPO_OVERRIDE="core=/path/to/old/checkout" KB_CODE_OUT=/tmp/old`.

## How cards sit in a kb

- Cards go to `raw/printed-docs/` (nothing may sit loose in `raw/`), named `ir-<slug>.md`. Each has a row in `meta/corpus.tsv` with disposition `skip`: a card is derived evidence, not backlog. A changed card replaces the old text (it is regenerated, not a source), so its fact ids change when the fact changes.
- The export is one knowledge step (`kb(catalog): code IR: N cards`), taken under the ops lock and refused while a session is open. Exporting twice at the same commits commits nothing.
- A page cites a fact as ``(`F1a2b3` [file.py:7](<permalink>))[^ir-core-py-pkg]``. `cite` does not write pages yet: paste what `cite --check` prints inside an ops session. `check-cites` runs on every `kb`.
- `artifacts/graph.json` is the small projection (repos, folders, files, classes, functions, import / call / inherit / co-change links, and which nodes each card fact is about) a viewer draws between concepts and sources. It is sorted, so a rebuild at a new commit gives a readable diff. It sits outside the knowledge lane, so no ops step commits it.
