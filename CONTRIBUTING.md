# Contributing

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

pixi is solved for macOS on Apple silicon (`osx-arm64`). Tests do not call a real LLM and need no account or network.

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

## Change flow

Never commit to `main`. Use `ship`, which wraps branch, commit, gates and pull request.

1. `pixi run ship -- start <feature> --worktree` creates `infra/<feature>` in its own worktree.
2. Make the change. Add a test next to the code it covers.
3. `pixi run ship -- commit "chore(<component>): summary"` runs the gates on the files you changed and commits them. The type is `paradigm`, `schema`, `feat`, `fix` or `chore`; `chore` covers docs, tests and refactors. Keep the subject to 72 characters and do not use apostrophes (pixi re-quotes the message and the commit silently fails).
4. If `main` moved, `pixi run ship -- sync` merges it into your branch. Resolve any conflict, `git add` the files, then `pixi run ship -- sync --continue`.
5. `pixi run ship -- pr --title "chore(<component>): summary"` runs the full gates and opens the pull request. `--hold` keeps it from merging until the owner approves.
6. A maintainer reviews and merges with `pixi run ship -- merge` (always a merge commit). Pull requests that change the schema are held for the owner.

`ship` expects the maintainers' GitHub setup. From a fork, make the same change on a branch and open an ordinary pull request; the checks are the same.

## Pull request expectations

- One concern per pull request, under about 400 changed lines where possible.
- The gates pass. `ship pr` runs `tests` (this includes the privacy ratchet), `lint-skills`, `lint-imports`, `lint` and `okf-check`; run `pixi run web-check` as well when `web/` changes. Do not skip or weaken a check.
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

- `AGENTS.md` and `CLAUDE.md` give instructions to coding agents working on the engine.
- `.integrator.toml` is the configuration for the integrator skill, which runs the test, build and screenshot checks for a round of merged pull requests. Do not move it.

## Conduct and license

See [`.github/CODE_OF_CONDUCT.md`](.github/CODE_OF_CONDUCT.md). Contributions are released under the [MIT license](LICENSE).
