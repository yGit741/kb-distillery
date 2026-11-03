# kb-distillery roadmap

Migration from the private knowledge-base explorer to the open-source
**kb-distillery** (CLI `kbd`). Each phase gets its own plan and approval before
work starts, and depends on the phase before it. `∥` marks tasks that can run
in parallel inside a phase.

## Goal

One public repo anyone can clone: `kbd init`, build your own kb from a
template, contribute to the engine or templates, and your knowledge never
enters the repo. The thesis kb is user zero.

## Target architecture

1. One builder repo: engine + `templates/` + `kbs/`. `kbs/` is gitignored
   except `examples/demo`. Each kb is its own git repo inside `kbs/` (the demo is
   the one exception: the engine repo tracks it). No submodules.
2. Templates own the schema (goal, node types, typed edges, fields, areas, lint
   rules, skills/prompts, views, migrations, samples). Versioned. A kb's
   `kb.toml` names its template and may extend it, never edit it.
3. A kb holds only knowledge (wiki/, manifest, its settings).
4. Source data via storage connectors (list, get, put, info, local copy, auth).
   Built-ins: local-folder (default), Google Drive. Third parties plug in as
   packages. Local raw stays next to the kb, gitignored.
5. Think is one standalone journal; `kbd distill <note> --to a,b` sends a note
   into chosen kbs with provenance on both sides.
6. `kbd init` and `kbd doctor`. LLM optional: AI features stay greyed until a
   subscription login or API key (keychain) is added.
7. Sharing is a pluggable publisher outside core (Cloudflare is the first).
8. Time machine from each kb's own git history + `kb-x.y.z` tags.
9. License MIT.

## Standing rules (every phase)

- `knowledge-base-thesis` and Cloudflare stay untouched until Phase 9;
  `KB_SHARE_AUTODEPLOY=0`.
- No remotes, no push before Phase 8.
- No git debt: each phase ends with every branch merged or deleted, no stale
  worktrees, clean `git status`, and a `phase-N-done` tag.
- Knowledge never enters the engine repo; only `examples/demo` is tracked.
- Every LLM feature goes through the shared LLM tool (subscription, API,
  Batch). A phase that adds or changes one has a **Billing** section.
- Plan → approval → autonomous work. UI changes are proven with screenshots.

## Test strategy

| Layer | What | Runs on |
|---|---|---|
| Unit | engine logic | demo kb + template samples (thesis-free from Phase 2) |
| Contract | connector, template, publisher interfaces | every implementation |
| Integration | `kbd` commands end to end | a temp kb per test |
| UI tour | Playwright screenshots of the main screens | demo kb (CI), thesis kb (local) |
| Privacy | no paths, names or knowledge from `kbs/` in tracked files | CI from Phase 7 |

A phase is done only when every earlier layer stays green.

---

## Phase 1 · Foundation: name, layout, git hygiene

Depends on: nothing. Result: final repo shape, thesis kb running from inside it.

**1.0 Context.** Read the open-source part of the kb-split discussion; raise
any conflict with this roadmap before starting.

**1.1 Freeze and back up.** Clean `git status` in the explorer, thesis kb and
think. Save the green baseline (`KB=<research-kb> pixi run test`). Tag
`pre-distillery` in all three repos with `ship tag` (agents cannot run
`git tag`; `ship tag <name> [--at REV] [--kb ID|PATH | --repo DIR]`, local,
annotated, main only, refuses `kb-*`). Tarball `knowledge-bases/` minus `raw/`,
plus a file+size manifest of `raw/`.
*DoD:* baseline saved for comparison.

**1.2 Rename** (∥ with 1.4 prep). Folder `knowledge-base-explorer` →
`kb-distillery`; package, pixi project, app titles; CLI entry point `kbd`;
docs and skills. No compatibility alias.
*DoD:* `grep -ri knowledge-base-explorer` is empty outside history notes;
`kbd --help` works; tests green.

**1.3 Layout move.** `kb-<research-kb>` → `kbs/<research-kb>` (`.git` and
`raw/` move with it; same disk, instant). `kb-job-search` → `examples/demo`
(tracked; check it is public-safe first). `think` → `kbs/think` (own repo).
`.gitignore`: `kbs/*`, `!examples/demo/`. Delete the empty `knowledge-bases/`.
*DoD:* thesis `git log` full and `git fsck` clean; engine `git status` shows
only `examples/demo` as new; `raw/` matches the 1.1 manifest.

**1.4 One discovery path.** A kb is a folder in `kbs/`, or `--kb <path>`.
Delete `knowledge-bases.toml` and its loader, the `../knowledge-bases/`
fallback and `$KB` path variants (`$KB=<id>` stays only as `--kb` shorthand if
tests need it). `$KB_ROOT` stays as an internal subprocess hand-off, set by
tools, never by users. kb hooks resolve the engine via `../..`; in the thesis
repo that is one `chore(hooks)` commit. The commit policy gains a rule for it:
on a kb repo's main, `chore(<scope>)` is allowed when every path is a kb
tooling path (`.claude/`, `.obsidian/`, `CLAUDE.md`, `AGENTS.md`,
`.gitignore`, `kb.toml`); no `--no-verify`. There is no `refactor:` type.
Tests: discovery (list, unknown id, path override) and hook resolution.
*DoD:* `kbd kb-list` shows `demo`, `<research-kb>` and not `think`; old code
paths deleted, not just unused.

**1.5 Integrate branches.** Order of work: `infra/llm-client` merges first,
right after `ship tag` and before the layout work (it does not depend on 1.2–1.4
and its worktree carries uncommitted migrations); `infra/graph-cypher` merges
after 1.3–1.4.
- `infra/graph-cypher`: rebase onto new main, finish the Cypher query service,
  API route and chat-agent hook, tests green, merge. Its chat-agent change goes
  through the shared LLM tool once `infra/llm-client` is in, so merge
  llm-client first. Edge types are read from the kb schema (made
  template-driven in Phase 2).
- `infra/llm-client`: rebase, test, merge.
- Delete merged `infra/kb-split`, `fix/vectors-kb-path`; remove all stale
  worktrees.
*DoD:* `git branch` → `main` only; `git worktree list` → one entry; Cypher
queries work against the thesis kb and demo.

**1.6 Verify.** Thesis tests match the 1.1 baseline; demo tests green except
the known thesis-type tests (fixed in Phase 2). Dashboard runs with
`--kb <research-kb>` and `--kb demo`, screenshot tour of both.
`knowledge-base-thesis` untouched (status + mtime check).

**Phase 1 DoD:** 1.1–1.6 green, `phase-1-done` tag, short report with
screenshots.

## Phase 2 · Templates own the schema

Depends on: Phase 1.
- ∥ Template spec: versioned format (goal, types, typed edges, fields, areas,
  lint rules, skills/prompts, views, migrations, samples).
- ∥ `templates/academic-research` from the thesis types, areas, skills, views.
- ∥ `templates/starter`, used by `examples/demo`.
- Thesis `kb.toml` → `template = "academic-research"`, extend only; engine
  rejects template edits. Cypher edge types come from the template.
- Engine tests run on demo + template samples; contract tests per template.

*DoD:* `pixi run test` green with no thesis kb present; thesis lints as
before; demo builds from `starter`.

## Phase 3 · Storage connectors

Depends on: Phase 2.
- Interface (`list/get/put/info/local_copy/auth`) + contract test suite.
- Built-in local-folder connector (default).
- ∥ Move the ~43 raw-access modules onto it, in batches by area.
- Third-party connectors via package entry points (proven with a dummy package).

*DoD:* no module touches `raw/` directly (lint test); thesis kb unchanged in
behaviour.

## Phase 4 · Think as a standalone journal

Depends on: Phase 3.
- Think lives outside every kb; `kbd distill <note> --to a,b` with provenance
  on both sides; the note records where it went.
- **Billing** section required.

*DoD:* distilling into two kbs works; existing `think:` citations resolve.

## Phase 5 · `kbd init` / `kbd doctor` + LLM opt-in

Depends on: Phase 4.
- `kbd init`: storage, optional LLM, first kb from a template.
- `kbd doctor`: checks environment and kb, suggests fixes.
- AI features greyed until a login or keychain API key exists; all three
  backends selectable.
- **Billing** section required.

*DoD:* fresh clone on a clean user: `pixi install && kbd init` → working
dashboard in minutes, no LLM.

## Phase 6 · Decouple sharing

Depends on: Phase 5.
- Publisher interface outside core; remove the 8 core imports of `kb_distillery.share`.
- Cloudflare becomes the first publisher plugin, off by default; live site
  untouched.

*DoD:* core runs and tests pass with no publisher installed.

## Phase 7 · Open-source readiness

Depends on: Phase 6.
- ∥ History audit: gitleaks + scan for kb content, personal paths, secrets. If
  found: rewrite history or fresh initial commit (owner's call).
- ∥ Docs: README quick start, ARCHITECTURE, CONTRIBUTING, template- and
  connector-author guides, LICENSE (MIT).
- ∥ CI: tests, lint, privacy check, UI tour on demo.
- Name check on GitHub/PyPI.

*DoD:* a stranger following only the README succeeds (fresh clone in a temp
dir).

## Phase 8 · Publish

Depends on: Phase 7.
- Remotes: kb-distillery public; thesis kb and think private (owner's call).
- Tag `v0.1.0`, release notes.

*DoD:* public repo live, CI green on GitHub, fresh clone passes `kbd doctor`.

## Phase 9 · Switchover from knowledge-base-thesis

Depends on: Phase 8 (and Phase 6's publisher).
- launchd jobs and the Cloudflare deploy move to kb-distillery + publisher.
- Archive the old monorepo; lift the no-`kb(...)`-ops rule.

*DoD:* live site served from the new setup; nothing runs from the old repo.
