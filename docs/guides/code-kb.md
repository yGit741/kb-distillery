# Cite code from a knowledge base

`distill code` turns repositories (or a folder of code) into a deterministic IR, a typed graph of files, includes, symbols, calls and history, then cuts it into **cards**: markdown fact tables where every row has a fact id (`F` and five hex digits) and a permalink at a pinned commit. A wiki page can cite a fact by id. No model and no network: the same commits always give the same output.

Tiers: any repo (files, history, co-change, CODEOWNERS), C and C++ (tree-sitter, optional), Python (the standard `ast`). C++ needs the extra: `pip install "kb-distillery[code]"`; the Python tier and everything else work without it.

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

Permalinks come from the repository's `origin` remote (credentials dropped): GitHub form `/blob/<sha>/path#L3-L9`, GitLab form `/-/blob/<sha>/path#L3-9`, chosen by the host name or `style = "github" | "gitlab"`. Give `remote` or `web` per repo to override, or a `[code.permalink]` table (`blob`, `tree`, `range`, `pull` patterns) for any other host. A repo with no remote has no links: its facts keep the `path:line` label. A plain folder (`git = false`, with `web` for where its files open) is pinned by its content and has no history.

## Commands

| Command | Does |
|---|---|
| `distill code build [project]` | `<out>/ir.json` and `ir.db` (SQLite), with drift warnings; `<out>` defaults to `<kb>/.local/code/<name>` |
| `distill code cards [project]` | `<out>/cards/*.md` and `index.json` |

Pass `--kb <id|path>` after the command to pick the knowledge base. To rebuild at another commit without touching the checkout, build the old side with `KB_CODE_REPO_OVERRIDE="core=/path/to/old/checkout" KB_CODE_OUT=/tmp/old`.
