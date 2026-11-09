# Contributing

## How contributions work

- **Issues are welcome.** Bug reports, feature requests and questions: use the issue templates. A small, reproducible report is the most useful contribution there is.
- **Core pull requests are by invitation.** The engine (`src/`, `web/`, the kits) has a strict layer contract and a schema that migrates people's knowledge bases, so changes to it start from an issue where the maintainer agrees on the approach and invites you to send it. Unsolicited core pull requests may be closed with thanks. Documentation fixes, typo fixes and examples are always welcome as pull requests without an invitation.
- **Extensions are separate packages.** Kits, storage connectors, publishers and skills live in their own repositories and plug in through entry points; you do not need our permission or a merge to ship one. See "Extending" below.

Who decides what: [GOVERNANCE.md](GOVERNANCE.md). How we behave: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Vulnerability reports: [.github/SECURITY.md](.github/SECURITY.md), never a public issue.

The rest of this file is for invited contributors and for maintainers.

This repository is the engine of kb-distillery: the code, the kits and the guides. A knowledge base is not part of it.

## Set up

The environment is managed by [pixi](https://pixi.sh).

```bash
curl -fsSL https://pixi.sh/install.sh | bash   # once, then restart the shell
pixi install
pixi run test                                  # pytest
pixi run lint-skills                           # skill front matter and links
pixi run lint-imports                          # the layer contract between packages
pixi run web-check                             # only when web/ changes
```

pixi is solved for macOS (`osx-arm64`, `osx-64`) and Linux (`linux-64`). Tests do not call a real LLM and need no account or network.

## Layout

| Folder | Content |
|---|---|
| `src/kb_distillery/` | the Python package |
| `src/kb_distillery/kits/` | kits: `kit.toml`, defaults, hooks, skills |
| `web/` | the React app |
| `tests/` | tests, mirroring `src/`; end-to-end tests in `tests/e2e/` |
| `examples/demo/` | the public sample knowledge base |
| `scripts/` | shell helpers and git hooks |
| `docs/` | documentation |

Knowledge bases live in `~/knowledge/<id>` (or under `$KB_DISTILLERY_HOME`), each in its own git repository. Do not add pages, sources, notes, local paths, names or keys to tracked files. The privacy ratchet in `tests/lint/` fails on personal strings and token-shaped text in tracked files, and CI runs a secret scan.

## Repository layout

| Folder | What it holds |
|---|---|
| `.github/` | CI workflows, issue and pull request templates and the security policy |
| `docs/` | public documentation and guides |
| `examples/` | the sample knowledge base (`demo/`) and scheduler templates (`launchd/`) |
| `scripts/` | git and Claude hooks and launch scripts |
| `src/` | the `kb_distillery` Python package and its kits |
| `tests/` | the test suite, mirroring `src/` |
| `web/` | the React app |

## Change flow

Never commit to `main`. Use `ship`, which wraps branch, commit, pull request and merge; CI runs the gates.

1. `pixi run ship -- start <feature> --worktree` creates `infra/<feature>` in its own worktree.
2. Make the change. Add a test next to the code it covers.
3. `pixi run ship -- commit "chore(<component>): summary"` runs the fast local gates (ruff, lint-imports and the tests that mirror the files you changed) and commits them. The type is `paradigm`, `schema`, `feat`, `fix` or `chore`; `chore` covers docs, tests and refactors. Keep the subject to 72 characters and do not use apostrophes (pixi re-quotes the message and the commit silently fails).
4. If `main` moved, `pixi run ship -- sync` merges it into your branch. Resolve any conflict, `git add` the files, then `pixi run ship -- sync --continue`.
5. `pixi run ship -- pr --title "chore(<component>): summary"` pushes the branch and opens the pull request; CI runs every gate on it. `--hold` keeps it from merging until a maintainer approves.
6. A maintainer reviews and merges with `pixi run ship -- merge`, which arms GitHub's auto-merge on the PR (the merge queue, where the repository has one) and waits for it (always a merge commit; `--no-wait` returns right after enqueueing). Pull requests that change the schema are held until a maintainer approves them.

`ship` expects the maintainers' GitHub setup. From a fork, make the same change on a branch and open an ordinary pull request; the checks are the same.

## Pull request expectations

- One concern per pull request, under about 400 changed lines where possible.
- The gates pass. CI (`.github/workflows/ci.yml`, required check `all-green`) runs `tests` (this includes the privacy ratchet), `lint-skills`, `lint-imports`, `lint`, `okf-check` and `web-check`; run `pixi run web-check` locally when `web/` changes. Do not skip or weaken a check. `web-check` also enforces the UI principles baseline (`web/tests/ui-principles.baseline.json`) and the graph screenshot test (`tests/e2e/graph-still.test.mjs`). More on the test harness: `tests/harness/README.md`; the maintainer-only `.claude/` agent tooling (engine skills, hooks) is not shipped in the public export.
- Every call to a language model goes through `kb_distillery.llm`. Do not add a new `claude -p`, SDK or HTTP call.
- A feature that cannot land in one pull request ships behind a flag in `src/kb_distillery/kits/base/defaults/flags.toml`; run `pixi run flags-gen` after editing it.
- Changes to the app keep its look unless the pull request is about the look.
- Update `CHANGELOG.md` under `Unreleased`.

## Extending

| To add | Guide |
|---|---|
| A kit | `docs/guides/write-a-kit.md` |
| A skill | `docs/guides/write-a-skill.md` |
| A storage connector | `docs/guides/add-a-storage-connector.md` |
| A publisher | `docs/guides/add-a-publisher.md` |

Each guide names the contract test the implementation must pass.

## Other files at the root

- `AGENTS.md` gives instructions to coding agents working on the engine.

## Conduct and license

See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) and [GOVERNANCE.md](GOVERNANCE.md). Contributions are released under the [MIT license](LICENSE).
