# Roadmap

This page lists what is shipped, what is next, ideas that are not scheduled, and two directions we have deliberately left out for now. It describes intent, not promises.

## Release cadence

Versions stay at `0.x` until the file formats and interfaces are stable. A `0.x` tag is cut every two to four weeks from the `[Unreleased]` section of the [changelog](../CHANGELOG.md), with patch releases on demand. Each tag carries the changelog notes and the prebuilt web bundle.

## Shipped

- Two-line install for macOS, Linux and WSL2, a first-run card in the app, and `distill doctor`. The first launch works without a model.
- Knowledge bases as separate folders, each its own git repository. The engine tracks only `examples/demo`, and example knowledge bases open read-only.
- Kits (`base`, `research`) and entry points for third-party kits and skills; see [build an extension](guides/build-an-extension.md).
- Adding sources from the app (drop files, link a folder) with no model call, and digest jobs with a cost preview, progress and cancel.
- One LLM gateway with three billing backends (subscription, API, Batch API), provider adapters for Anthropic, OpenAI and Gemini, and model tiers light, standard and strong. Agent features that need Claude are marked in the app.
- Storage connectors (local folder, Google Drive mount) and a publisher plugin interface with a Cloudflare publisher, an audit step and named snapshots.
- Think journal and `distill send`, with provenance on both sides.
- Digest tiers: easy, full and deep, in a transactional session.
- Typed relations and proposals: trust tiers, auto-apply with undo, coherence suggestions, a review screen, chat on a page that produces proposals, and flags on inaccurate spans.
- Versioned knowledge operations: one commit each, undo, restore, snapshots, tags `kb-x.y.z`.
- A typed HTTP API with a generated schema, and a React app that serves every screen.
- Self-hosting with an opt-in proxy identity, and guides for Tailscale, Cloudflare Access and any proxy ([any proxy](guides/self-host-any-proxy.md)).
- Open Knowledge Format as the shape of a knowledge base, checked by `pixi run okf-check`.
- A layer contract between packages, checked by `pixi run lint-imports`.
- Continuous integration as the merge gate, a wheel that installs into a clean environment, and a contribution model with a code of conduct and governance (see [CONTRIBUTING.md](../CONTRIBUTING.md) and [GOVERNANCE.md](../GOVERNANCE.md)).
- Hooks that keep agents from writing to `raw/` or running ad-hoc git writes in a knowledge base.
- Linux x86-64 and macOS (Apple silicon and Intel). Two features are macOS-only: OCR through `ocrmac` and the keychain.

## Next

Work in progress, then the steps only the repository owner can take.

- Container image and a remote health check in `distill doctor`.
- Release workflow: build the wheel, the web bundle and the image from a `v*` tag, and cut the release notes from the changelog.
- Public-readiness checks in CI: nothing private is exported, and the privacy ratchet passes with the full term list.
- Make the repository public.
- Tag `v0.1.0`.
- Announce the release.

## Ideas

These have no date.

- OCR and secret storage on Linux, where the macOS-only `ocrmac` and keychain features do not apply.
- A Google Drive connector that uses the API instead of a mounted folder.
- A connector for S3-compatible object storage (for example R2) for `raw/`, which stays out of git either way.
- A second publisher, for example a static host other than Cloudflare.
- More kits and example knowledge bases, written by users; see [community extensions](community-extensions.md).
- Run the nightly job on Linux with systemd or cron.
- Publishing the package to PyPI.

## Future directions

Two larger directions are not part of the current plan. They need design work first, and the single-user model comes first.

- **Shared team instances.** Today an instance serves one person, also inside a company. Several people working in one instance would need accounts, roles and shared review of proposals.
- **Linking knowledge bases across people and teams.** Knowledge bases stay separate repositories. Links and queries across them, with clear ownership and provenance, would be a federation layer on top.

Local language models, native Windows and a desktop app are also out of scope for now.
