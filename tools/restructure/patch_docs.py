"""Doc edits that go beyond the mechanical path rewrite: the new code layout, in AGENTS.md."""

LAYOUT = """## Code layout

Code, tools and the vault are separate top-level folders; `meta/` is vault metadata only.

```
backend/                Python app, package `kb` (src layout, pyproject.toml, editable install via pixi)
  src/kb/paths.py       the ONE vault-root resolver (KB_ROOT, else this checkout) + every data path constant
  src/kb/core/          schema, graph, hubs, scopes, persons, books, mathnorm, coherence, health
  src/kb/lint/          lint, lint_skills            src/kb/search/       query, semfind, explore_raw, citations
  src/kb/ingest|distill|ops|report|share/            src/kb/git/          guard, git_guard, commit_policy, ship, merge_nudge, curate_history
  src/kb/maintenance/   daily_sync, notify, sync_skills, rename_raw, migrate_model, export, fix_math
  src/kb/migrations/    schema migrations (code); the applied ledger stays in meta/migrations/applied.tsv
  src/kb/services/      former dashboard *_data modules (graph, pages, corpus, scopes, chat, pipeline, lifecycle, ops)
  src/kb/dashboard/     legacy HTML pages + server until their screens are ported       src/kb/prompts/  chat prompts
  tests/                pytest, mirrored by package (tests/harness = the pipeline harness)
share/                  Cloudflare Worker (auth.js, admin.js, wrangler template) + its node tests
skills/                 agent skill sources (synced to .cursor/skills and .claude/skills)
tools/                  githooks/, launchd/, launch.sh, restructure/ (the script that made this layout)
meta/                   VAULT METADATA ONLY: corpus.tsv, log.md, aliases.tsv, coherence-warnings.tsv, raw-renames.tsv,
                        chats/, templates/, migration/, migrations/applied.tsv, ops/sync.toml, thesis.md
```

Run a module with `python -m kb.<package>.<module>` (pixi tasks do); `kb` is installed editable, so `pixi install`
again after pulling this layout. Never `sys.path.insert`; take paths from `kb.paths`.

"""


def register(add):
    add("AGENTS.md",
        ("| **Meta** | `meta/` | Schema, templates, log. |",
         "| **Meta** | `meta/` | Vault metadata: manifest, log, templates, chats. No code (see Code layout). |"),
        ("## backend/src/kb/lint/lint.py IS the schema\n", LAYOUT + "## The linter IS the schema (`kb.lint.lint`)\n"))
    add("CLAUDE.md",
        ("`backend/src/kb/lint/lint.py --health`", "`pixi run health`"))
