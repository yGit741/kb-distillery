# Changelog

All notable changes to this project are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

Nothing yet.

## [0.1.0]

Initial public release: the first version made public. Many app features are behind feature flags that are on in the local app only and off by default elsewhere (see `src/kb_distillery/kits/base/defaults/flags.toml`); bullets name a flag where one applies. It is not tagged or published as a package until the repository goes public.

### Added

- `distill` command: `init`, `doctor`, `kb list|show`, `launch`, `hooks install`, `hook <name>`, `ops`, `ship`, `ingest`, `digest`, `send`, `lint`, `llm`, `share`, `propose`. `kbd` is a deprecated alias of `distill`.
- Kits (`base`, `research`) that define the page types and relations of a knowledge base, and the schema linter.
- Knowledge bases live outside the repository, in `~/knowledge/<id>`, each in its own git repository. The base folder can be set with `KB_DISTILLERY_HOME`.
- One LLM gateway with three billing backends: subscription, API and Batch API.
- The React app (graph, search, reader), built on first launch into `src/kb_distillery/_webapp` and included in the wheel.
- Static-site publishing with a Cloudflare Workers publisher; settings are read from `~/.config/kb-distillery/share.toml`. The repository ships only `src/kb_distillery/publish/cloudflare/share.example.toml`, with placeholders.
- Source connectors under `ingest/sources` (books, chat, Google Drive, mail, researcher, web, YouTube).
- `pyproject.toml` with extras `gdrive`, `ingest-heavy` and `dev`; a layer contract checked by `import-linter`; issue templates, a pull request template and `SECURITY.md`.
- `examples/demo`, a sample knowledge base about a made-up job search.
- One-script install for macOS, Linux and WSL2, a prebuilt web bundle fetched from the release, and read-only example knowledge bases that open read-only.
- First-run card in the app: drop files or link a folder to add sources without a model call, then run digest jobs with a cost preview, progress and cancel.
- LLM provider adapters for Anthropic, OpenAI and Gemini, provider config, model tiers (light, standard, strong), `llm ask --provider`, and a docs page on providers, tiers and billing. Agent features that need Claude are marked in the app.
- Proposals: trust tiers, auto-apply with undo, scoped semantic checks, nightly suggestions and a review screen with three diff views. Chat on a page produces proposals; inaccurate spans can be flagged and fixed in one proposal.
- Entry points for third-party kits and skills, and a guide to building extensions.
- Opt-in proxy identity for self-hosting (`KB_AUTH=proxy`) with guides for Tailscale, Cloudflare Access and any proxy.
- Contribution model, code of conduct and governance documents.
- Graph shell: search line with meaning search, layers and views, favorites, an action menu on every row, export of a subgraph as an OKF bundle, and a first-run map.
- Sources on a page, full-text search index and a read-only graph line on the shared site.
- Performance: a graph snapshot cache with background warm-up, a 5-minute query cache, and `pixi run perf`.
- Review inbox for proposals: stale proposals are rebased onto the current page, set-aside items stay visible, and a feed lists what was applied automatically. Behind the `ui.proposals` flag, on in the local app only.
- Page history: list the versions of a page, compare any two with the proposal diff, and restore a version or a block as a proposal. Behind the `ui.page-history` flag.
- Merge, split and extract pages as proposals, from a menu or a command on the page view. Behind the `ui.restructure` flag.
- Ingest from the app: drop a paper or paste a URL, pick how deeply to read it, and review the result as a proposal. The screen lists what you brought in like an inbox (in progress, waiting for your review, done, did not finish) and keeps the list across restarts. Behind the `ui.ingest` flag.
- Variants tab on the System screen to pick between component designs, reset to defaults and copy the choices; a what's-new tour; and demo content that exercises proposals. The tab is behind the `ui.variant-chooser` flag.
- `distill doctor` understands proxy mode and checks a remote instance.
- Dockerfile for self-hosting. CI builds the image and smoke-tests it on every pull request, and the release workflow will publish it to GHCR when a tag is cut.
- Release workflow: a `v*` tag builds the wheel, the web bundle and the image, and cuts the release notes from this changelog. Publishing to PyPI is present but switched off.
- Public-readiness checks in CI: nothing owner-only is exported, and the privacy checks run on the exported tree.
- Two-line install in the getting-started guide and the README.

### Changed

- `ship` uses CI as the merge gate: `commit` runs the fast local gates, `pr` pushes and `merge` arms auto-merge.
- Repository root tidied for open source; the `tools/` forwarding stubs are removed.

### Fixed

- `distill ops` refuses to treat the engine repository as a knowledge base.
- Digest keeps the SIGTERM hold during finalize with threads alive.
