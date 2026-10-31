# Contributing

Thanks for helping. This repo is the **engine** of kb-distillery: the code, the templates and the guides. Your knowledge is not part of it.

## Set up

The environment is managed by [pixi](https://pixi.sh).

```bash
curl -fsSL https://pixi.sh/install.sh | bash     # once, then restart the shell
pixi install
pixi run test                                    # the unit tests (pytest backend/tests)
pixi run lint-skills                             # skill front matter and links
```

Before you push, `pixi run test` must pass. Frontend work adds `pixi run web-check`. Tests never call a real LLM and never need an account or a network.

## Knowledge never enters this repo

A knowledge base is a folder `kbs/<id>`, and it is its own repository. `kbs/` is gitignored except `kbs/demo`, the public sample. Do not add pages, sources, notes, local paths, names or keys to files tracked here. `python -m kb.lint.privacy` (run by the test suite) fails on personal strings and token-shaped text in a new file, and CI also runs a secret scan.

## Changing the engine

Tooling changes go through a branch and a pull request, with the helper `ship`. Never commit to `main` directly.

1. `pixi run ship -- start <feature> --worktree`: a branch `infra/<feature>` in its own worktree.
2. Make the change and add a test next to the code it covers (`backend/tests/<package>/`).
3. `pixi run ship -- commit "feat(<component>): imperative summary"`. Types by what changed: `schema`, `feat`, `fix`, `chore`. Avoid apostrophes in the message.
4. `pixi run ship -- pr --title "feat(<component>): imperative summary"` runs the gates (tests, lint) and opens the PR.
5. A maintainer reviews. `pixi run ship -- merge` merges with a merge commit; PRs that change the schema are held for the owner's approval.

Keep a PR to one concern and, where you can, under about 400 changed lines. A feature that cannot land in one PR ships dark behind a flag in `meta-defaults/flags.toml`. Every call to an LLM goes through `kb.llm` (`backend/src/kb/llm`), never a new `claude -p`, SDK or HTTP call.

`ship` expects the maintainers' GitHub setup. If you only have a fork, make the same change on a feature branch and open an ordinary pull request; the checks are the same.

## Extending it

| You want to add | Guide | Where the code goes |
|---|---|---|
| A **template** (the schema a kb follows: page types, edges, fields) | [`meta-defaults/docs/templates.md`](meta-defaults/docs/templates.md) | `templates/<name>/template.toml` |
| A **storage connector** (where raw sources live) | [`meta-defaults/docs/storage.md`](meta-defaults/docs/storage.md) | `backend/src/kb/storage/`, or a package with its own entry point |
| A **publisher** (a way to share a kb as a site) | [`meta-defaults/docs/publish.md`](meta-defaults/docs/publish.md) | a package in the `kb.publishers` entry-point group |

Each guide names the contract test your implementation must pass. Think notes and `kbd distill` are described in [`meta-defaults/docs/think.md`](meta-defaults/docs/think.md); the code layout and pixi tasks are in [`meta-defaults/docs/dev.md`](meta-defaults/docs/dev.md).

## Conduct

Be kind. See [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md). By contributing you agree your work is released under the [MIT license](LICENSE).
