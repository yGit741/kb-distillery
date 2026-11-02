# Roadmap

This page lists what is shipped, what is next, and ideas that are not scheduled. It describes intent, not promises.

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
- A typed HTTP API with a generated schema, and a React app on top of it.
- A nightly sync and hygiene report for macOS.
- Hooks that keep agents from writing to `raw/` or running ad-hoc git writes in a knowledge base.

## Next

- Open Knowledge Format v0.2 as the native shape of a knowledge base. <!-- after OKF merge --> `wiki/` becomes the bundle root with `index.md` and `log.md`, links become relative markdown links, and frontmatter uses `maturity`, `description`, `generated` and `sources[].resource`. A validator, `okf-check`, becomes a commit gate.
- A `distill` command that covers the tasks that still run as `pixi run <task>`.
- Retire the older dashboard pages and serve every screen from the React app.
- A layer contract between packages, checked in CI.
- Replace PyMuPDF (AGPL) with a permissively licensed PDF library, and check licenses in CI.
- A wheel that installs into a clean environment and passes `distill doctor`.
- Continuous integration for pull requests: Python tests, lint, web checks, wheel build.
- Public release: contributing guide, changelog, issue and pull request templates, security policy.

## Ideas

These have no date.

- Linux support. The environment lock covers macOS on Apple silicon only, and two features use macOS APIs: OCR and the keychain.
- A Google Drive connector that uses the API instead of a mounted folder.
- A second publisher, for example a static host other than Cloudflare.
- An agent in the app: chat and actions on a selected node.
- One library shared by several knowledge bases, with graphs as views.
- More kits, written by users.
- Run the nightly job on Linux with systemd or cron.
