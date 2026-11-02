# Changelog

All notable changes to this project are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0]

First release as an installable package. Most entries below are renames and moves; behavior and the app's appearance are unchanged unless stated.

### Changed

- Package `kb` is now `kb_distillery`. Imports, `python -m` entry points and mock patch targets use the new name.
- Folder moves:
  - `backend/src/kb` to `src/kb_distillery`
  - `backend/tests` to `tests`
  - `frontend` to `web`
  - `web/e2e` to `tests/e2e`
  - `kbs/demo` to `examples/demo`
  - `tools/launchd` to `examples/launchd`
  - `tools` (the rest) to `scripts`; `tools/hooks-python.sh` and `tools/hooks/` stay as forwarding stubs for old settings files
  - the development skills move to `.claude/skills`
- Module moves inside the package:
  - `core` to `vault`; the kit loader (formerly `core/template.py`) and the vault layout to `config`
  - `kbconfig` to `config/kb.py`, `paths` to `config/paths.py`, `flags` to `config/flags`, `ingest/net.py` to `config/net.py`
  - `summaries` to `digest`
  - `api` to `server`; the app starts with `python -m kb_distillery.server` (`pixi run app`)
  - `prompts` to `llm/prompts`
  - `share` to `publish/site` (the site build) and `publish/cloudflare` (the publisher, deploy and Worker)
  - `maintenance/daily_sync` and `maintenance/notify` to `ops`; `maintenance/export` to `publish/export.py`
  - `report` to `ops/report`
  - `services/graph.py` to `graph/snapshot.py`
  - the source connectors under `ingest/` to `ingest/sources/{books,chat,gdrive,mail,researcher,web,youtube}`
- Tests moved with the code: `tests/core` to `tests/vault`, `tests/api` to `tests/server`, `tests/share` to `tests/publish/cloudflare`, `tests/maintenance` to `tests/ops`.
- Templates are now kits. `templates/starter` is `kits/base`; `templates/academic-research` is `kits/research`, which extends `kits/base`. `kb.toml` reads both `[kb] template` and `[kb] kit`; `distill init` writes `kit`.
- `meta-defaults` is now `kits/base/defaults` (under `src/kb_distillery/`). Hooks are `kits/base/hooks`. Application skills move to `kits/base/skills` and `kits/research/skills`.
- Knowledge bases live outside the repository, in `~/knowledge/<id>`, each in its own git repository. The base folder can be set with `KB_DISTILLERY_HOME`.
- The user config folder `~/.config/thesis-kb/` is now `~/.config/kb-distillery/`. If only the old folder exists, the CLI prints the `mv` command and exits.
- The built React app is written to `src/kb_distillery/_webapp` and included in the wheel.
- Share settings (site name, subdomain, OAuth client id, allowed emails) are read from `~/.config/kb-distillery/share.toml`, or from `<kb>/.cache/share/share.toml` for one knowledge base. The repository ships only `src/kb_distillery/publish/cloudflare/share.example.toml`, with placeholders.
- `CONTRIBUTING.md` is at the repository root. `AGENTS.md` describes the engine; subject-specific text moved to `kits/research/AGENTS.template.md`.

### Added

- `distill` command: `init`, `doctor`, `kb list|show`, `launch`, `hooks install`, `hook <name>`, `ops`, `ship`, `ingest`, `digest`, `send`, `lint`, `llm`, `share`, `propose`.
- `pyproject.toml` with extras `gdrive`, `ingest-heavy` and `dev`.
- `ship mv`, a guarded `git mv` for moves.
- `hosting/`, the publisher port that `publish/cloudflare` implements.
- Layer contract checked by `import-linter` (`pixi run lint-imports`), and one of the `ship` gates.
- `tests/test_no_old_paths.py`, which fails when a retired import or path string is tracked.
- Issue templates, pull request template and `SECURITY.md`.

### Deprecated

- `kbd` remains for one release and forwards to `distill`:
  - `kbd distill` to `distill send`
  - `kbd kb-list` and `kbd kb-show` to `distill kb list` and `distill kb show`
  - `kbd health` to `distill lint --health`
  - `kbd app` to `distill launch`
  - `kbd install-kb-hooks` to `distill hooks install`
  - `kbd lint`, `launch`, `ship`, `ops`, `init` and `doctor` to the `distill` command of the same name

### Removed

- The legacy dashboard (`kb.dashboard`) and its `serve.py`, pages and static files. Its screens are in the React app.
- `maintenance/fix_math.py`, `maintenance/rename_raw.py`, `maintenance/sync_skills.py`.
- The root duplicates of `ARCHITECTURE.md`, `CONTRIBUTING.md` and `CODE_OF_CONDUCT.md`, and the `.cursor/`, `.vscode/` and `GEMINI.md` files.
- The tracked `share.toml` inside the share package; settings are no longer committed.
