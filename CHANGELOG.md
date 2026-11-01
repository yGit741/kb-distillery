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
  - `kbs/demo` to `examples/demo`
  - `tools/launchd` to `examples/launchd`
  - `tools` (the rest) to `scripts`
- Module moves inside the package:
  - `core` to `vault`; `core/template.py` to `vault/kit.py`
  - `summaries` to `digest`
  - `api` to `server`
  - `share` to `publish`
  - `maintenance/daily_sync` and `maintenance/notify` to `ops`
  - `maintenance/export` to `publish`
  - `report` to `ops/report.py`
  - `prompts` to `llm/prompts`
- Templates are now kits. `templates/starter` is `kits/base`; `templates/academic-research` is `kits/research`, which extends `kits/base`. `kb.toml` reads both `[kb] template` and `[kb] kit`; `distill init` writes `kit`.
- `meta-defaults` is now `kits/base/defaults`. `tools/kb-hooks` is now `kits/base/hooks`. Application skills move to `kits/base/skills` and `kits/research/skills`.
- Knowledge bases live outside the repository, in `~/knowledge/<id>`, each in its own git repository. The base folder can be set with `KB_DISTILLERY_HOME`.
- The user config folder `~/.config/thesis-kb/` is now `~/.config/kb-distillery/`. If only the old folder exists, the CLI prints the `mv` command and exits.
- The built React app is written to `src/kb_distillery/_webapp` and included in the wheel.
- Share settings (site name, subdomain, OAuth client id, allowed emails) are read from `share.toml`; the repository ships `share.example.toml`.
- The privacy check reads its terms from `KB_PRIVACY_TERMS` or `~/.config/kb-distillery/privacy.toml`. The default list is empty.
- `CONTRIBUTING.md` is at the repository root. `AGENTS.md` describes the engine; subject-specific text moved to `kits/research/AGENTS.template.md`.

### Added

- `distill` command: `init`, `doctor`, `kb list|show`, `launch`, `hooks install`, `hook <name>`, `ops`, `ship`, `ingest`, `digest`, `send`, `lint`, `llm`, `share`, `propose`.
- `pyproject.toml` with extras `gdrive`, `ingest-heavy` and `dev`.
- `ship mv`, a guarded `git mv` for moves.
- Layer contract checked by `import-linter` (`pixi run lint-imports`).
- `tests/test_no_old_paths.py`, which fails when a retired import or path string is tracked.
- `docs/` with getting started, concepts, guides, reference, architecture, roadmap and three decision records.
- Issue templates, pull request template and `SECURITY.md`.
- CI jobs `python`, `web`, `wheel` and `worker`; a license check with `pip-licenses`.

### Deprecated

- `kbd` remains for one release and forwards to `distill`:
  - `kbd distill` to `distill send`
  - `kbd kb-list` to `distill kb list`
  - `kbd app` to `distill launch`

### Removed

- The legacy dashboard (`kb.dashboard`). `/start` and the covector page are in the React app.
- `maintenance/fix_math.py`, `maintenance/rename_raw.py`, `maintenance/sync_skills.py`.
- Root duplicates of `ARCHITECTURE.md`, `CONTRIBUTING.md` and `CODE_OF_CONDUCT.md`, and the `.cursor/`, `.vscode/` and `GEMINI.md` files.

### Fixed

- PDF extraction uses `pypdfium2` instead of PyMuPDF, so the dependency tree has no AGPL package.
