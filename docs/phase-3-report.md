# Phase 3 report: storage connectors

## What is in

- `kb_distillery.storage`: the connector interface (`list`, `get`, `put`, `info`, `exists`, `local_copy`, `cached_path`, `auth`), logical `raw/...` keys, a registry that finds built-ins and packages (entry point group `kb_distillery.storage.connectors`), and one contract suite every connector must pass.
- Connectors: `local-folder` (the default) and `gdrive` (the macOS Google Drive mount, no OAuth). A dummy in-memory connector in the tests stands in for a third-party package.
- `kb_distillery.storage.raw`: the facade engine code uses (`raw.exists`, `raw.read_text`, `raw.path`, ...), bound to the current knowledge base's connector.
- Migrated onto it: `services/pages.resolve_asset`, `ingest/chat_build`, `ingest/digest_many`, `maintenance/export`.
- A ratchet: `python -m kb_distillery.lint.raw_access` lists the modules that still reach `raw/` themselves, `tests/storage/raw_access_baseline.txt` is their allowance, and a test fails on a new one. The list only shrinks.

## The plan's goal, and why it is met differently

The plan said "no module touches `raw/` directly". 17 modules still do. Moving them all would have changed behaviour the knowledge bases depend on, so each one was left on purpose. The reasons, so the next person does not have to rediscover them:

| Module(s) | Why it stays |
|---|---|
| `services/chat_agent.py`, `services/corpus.py` | Security checks: they decide what a user or the chat agent may read, using `realpath` containment on the real file system. A connector hides the real path, so moving them would change a security boundary. |
| `services/chat.py` | Its `save_chat(inbox=...)` takes a directory that the API router and several tests pass in. |
| `ingest/mail.py`, `scrap.py`, `wordpress.py`, `catalog.py`, `gdrive.py` | They write into `raw/inbox/` through module-level path constants that tests patch. The inbox is also the one place a user drops files by hand. |
| `ingest/youtube/bundle.py` | A connector has no directories, but this module relies on an empty `raw/videos/<name>/` folder counting as taken. |
| `services/pipeline.py` | It stats every raw file for size and time; the connector's `info()` hashes each file, which would be far slower. |
| `ops/invariants.py` | Its walk follows symlinks; the connector's `list` does not. |
| `services/raw_card.py` | It runs `git log` on the `raw` folder. |
| `lint/lint.py` | The linter is the schema: it reads the kb folders directly and owns the manifest. |
| `git/guard.py`, `git/ship.py` | Path rules and git plumbing, not content access. |
| `dashboard/serve.py`, `ops/nightly_report.py` | Entry points that build raw paths for display; to be revisited with the legacy dashboard's removal. |

Migrations (`src/kb_distillery/migrations/`) are exempt on purpose: they rewrite old layouts.

## Known gaps

- The `gdrive` connector has no timeout: a wedged Drive mount can make `auth()` or a read hang (`ingest/gdrive.py` has a guard for this that the connector does not copy yet).
- A remote connector would need two things the interface lacks: directory-like listing and a cheap stat. Add them when a real remote connector appears.
- The connector contract is exercised only by local and in-memory stores. No remote store (an API-based Drive, S3) was built or tested.

## Done when

The thesis knowledge base behaves as before (its tests and lint are unchanged), connectors and the registry exist and pass the contract suite, third-party connectors load by entry point (proven with a dummy), and the list of direct accessors is explicit and cannot grow. Not met as worded: zero direct accessors.
