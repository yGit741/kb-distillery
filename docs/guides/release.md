# Cut a release

A release is a `v<x.y.z>` tag on main. The tag triggers `.github/workflows/release.yml`; nothing else publishes.

## Cadence

Set by the maintainer; nothing in the tooling fixes it. Any newer version can be cut from `[Unreleased]` in `CHANGELOG.md` whenever the maintainer decides. Keep `[Unreleased]` current in every PR that changes behaviour, so a release is a rename, not a writing task.

## Steps

1. On a branch (`pixi run ship -- start release-v0.2.0 --worktree`), run the helper:

   ```bash
   pixi run release -- 0.2.0
   ```

   It sets `version` in `pyproject.toml`, moves the `[Unreleased]` entries under `## [0.2.0] - <date>`, and prints the commands below. It refuses on main, on a version that is not newer, and on an empty `[Unreleased]`. It never runs git and never tags.
2. Ship the bump as a normal PR: `ship -- commit "chore(release): v0.2.0"`, `ship -- pr`, `ship -- merge`.
3. The maintainer tags main and pushes the tag (agents never release): `pixi run ship -- tag v0.2.0`, then `git push origin v0.2.0`. The workflow refuses a tag whose commit is not on main.

## What the tag does

`release.yml` runs the CI gates, builds the wheel and the web bundle, creates the GitHub release with the notes cut from the matching `## [0.2.0]` section, and (the `docker` job) pushes the multi-arch image (`linux/amd64`, `linux/arm64`, from the repo `Dockerfile`) to `ghcr.io/<owner>/<repo>` tagged `0.2.0`, `0.2` and `latest`. A PyPI job is present but disabled (`if: false`) until the PyPI project and trusted publishing exist. The workflow stops if the tag does not match the `pyproject.toml` version.

To re-attach only the web bundle to an existing release, run the `web-bundle` workflow by hand with the tag.
