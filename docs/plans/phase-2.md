# Phase 2 plan: Templates own the schema

Depends on: Phase 1. Unattended-safe: yes, except the held spec PR.

A template is a versioned folder `templates/<name>/` that defines a knowledge base's ontology: goal, page types, typed edges, fields, areas, lint rules, skills/prompts, views, migrations and samples. A kb's `kb.toml` names its template and may extend it, never edit it. Anyone can write their own template; the thesis kb uses the real `academic-research` template.

## PRs

1. Spec + loader (`templates/<name>/template.toml`, read by `kb.core.kbtypes` / `kb.kbconfig`), built from today's `kbtypes.py` and `meta-defaults/{templates,digest}`. SCHEMA PR, held.
2. `templates/academic-research`: the thesis types, areas, skills and views; edge types (the 7 relation types) move here from the kb's `[edges]` table.
3. `templates/starter` and `kbs/demo` built from it.
4. Thesis `kb.toml` -> `template = "academic-research"` (extend only; the engine rejects template edits). A `chore(schema)` commit on the kb repo.
5. Engine tests on demo + template samples; a contract test per template.

## Billing

None.

## Done when

`pixi run test` green with no thesis kb present; the thesis lints as before; demo builds from `starter`.

## Approval gates

- The spec PR is a schema PR: held, you approve it.

## Findings from the code review (2026-10-31)

- Resolve the template inside `kbtypes.load` and `kbconfig.load_dir`. `core/schema.py` does `_T = _types.load()` at import time, so every constant (`SOURCE_TYPES`, ...) is frozen per process: the loader must not depend on import order.
- Name collision: `meta-defaults/templates/*.md` are page skeletons. Move them to `templates/<name>/pages/` so "templates" means ontology templates only.
- "Thesis-free" is bigger than it sounds: the demo run skips 527 tests ("needs default page types" 17 sites, "share build assumes monorepo layout" 12, "reads thesis content" 5, "needs `paper`" 3). Move those fixtures into template `samples/`.
- Relations: the 7 relation types, their endpoint and depth rules, `symmetric` and `note_required` are declared as DATA in the template's `[edges]` (not in `lint.py`), so the relations lint needs no separate schema bump. If this lands first, the schema PR C is folded into this PR (one held approval, one SCHEMA bump).
- Two schema PRs in a row (PR C, then this spec) each bump the version and migration number: they are two sequential approvals, never one batch.

## Standing rules

`KB_SHARE_AUTODEPLOY=0`; the thesis kb is never pushed to the old monorepo URL; every branch merged or deleted, no stale worktrees; tag `phase-2-done` with `ship tag`; every earlier test layer stays green.
