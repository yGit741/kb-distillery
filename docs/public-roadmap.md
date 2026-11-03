# Roadmap

This page lists what is shipped, what is next, and ideas that are not scheduled. It describes intent, not promises. Version `0.1.0` is the first public release; it counts as unreleased until the repository is public and a package is published.

## Shipped

- Knowledge bases as separate folders, each its own git repository. The engine tracks only `examples/demo`.
- Kits: `base` and `research`. A knowledge base extends a kit and cannot edit it.
- `distill init` and `distill doctor`. The first launch works without a model.
- One LLM gateway with three backends: subscription, API and Batch API.
- Storage connectors: local folder and Google Drive mount. Third-party connectors register through an entry-point group.
- Think journal and `distill send`, with provenance on both sides.
- Digest tiers: easy, full and deep, with a transactional session.
- Typed relations, proposals and a reviewed apply step.
- Versioned knowledge operations: one commit each, undo, restore, snapshots, tags `kb-x.y.z`.
- Publisher plugin interface, with a Cloudflare publisher, an audit step and named snapshots.
- A typed HTTP API with a generated schema, and a React app that serves every screen.
- Open Knowledge Format as the shape of a knowledge base: `wiki/` is the bundle root with `index.md` and `log.md`, links are relative `slug.md` links, and `pixi run okf-check` validates it.
- A layer contract between packages, checked by `pixi run lint-imports` and by the `ship` gates.
- A nightly sync and hygiene report, with launchd templates for macOS.
- Linux x86-64 and macOS (Apple silicon and Intel) support. Two features are macOS-only: OCR through `ocrmac` and the keychain.
- A `distill` command for the tasks that run as `pixi run <task>`; `kbd` stays as a deprecated alias.
- A wheel that installs into a clean environment and passes `distill doctor`.
- Continuous integration for pull requests (`ci.yml`): Python tests, lint, web checks, wheel build.
- Hooks that keep agents from writing to `raw/` or running ad-hoc git writes in a knowledge base.
- PDF reading with pypdfium2 (BSD / Apache) instead of the AGPL PyMuPDF, with a license check.

## Next

- Public release: the repository, a tagged `0.1.0` and a package.

## Ideas

These have no date.

- OCR and secret storage on Linux, where the macOS-only `ocrmac` and keychain features do not apply.
- A Google Drive connector that uses the API instead of a mounted folder.
- A second publisher, for example a static host other than Cloudflare.
- An agent in the app: chat and actions on a selected node.
- One library shared by several knowledge bases, with graphs as views.
- More kits, written by users.
- Run the nightly job on Linux with systemd or cron.
