# Changelog

All notable changes to this project are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0]

Initial public release: the first version made public. It is not tagged or published as a package until the repository goes public.

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
