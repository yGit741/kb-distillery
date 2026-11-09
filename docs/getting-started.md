# Getting started

This page takes you from a clone to a first digest. You need [pixi](https://pixi.sh) and git. Node is installed by pixi.

Supported platforms: macOS (Apple silicon and Intel), Linux x86-64, and Windows through WSL2. Installing the wheel with pip needs Python 3.11 or newer; older Pythons fail with a confusing `grand-cypher` error.

AI features are optional. Reading, linking, linting and the app work without a key. A digest needs a Claude login or an Anthropic API key; digests run on Claude only. Other providers are described in [Language models](concepts/llm.md).

## Install in two lines

```bash
git clone <repo-url> && cd kb-distillery
./install.sh
```

What it does: it checks the system (macOS, Linux or WSL2), installs pixi if it is missing, runs `pixi install`, runs `distill doctor`, creates a default knowledge base called `my-kb` when you have none (an existing one is left alone and used), checks it again and opens the app. It asks no questions and needs no model key. Running it again only updates the environment and opens the app. Flags: `--no-open`, `--kb-id <id>`, `--kit base|research`, `--dir <parent>`, `--dry-run` (print the commands, run nothing).

### Windows (WSL2)

The installer runs on Windows inside WSL2, not in PowerShell or cmd.

1. In an administrator PowerShell, run `wsl --install -d Ubuntu`, then restart if Windows asks.
2. Open the Ubuntu terminal and make sure `git` and `curl` exist: `sudo apt update && sudo apt install -y git curl`.
3. Clone into the Linux home folder, for example `~/kb-distillery`, and run the same two lines there. Avoid `/mnt/c/...`: file access across the Windows boundary is slow and breaks git file modes.
4. The app listens on `http://127.0.0.1:8765`. Open that address in your Windows browser. If it does not load, run `wsl --update` and try again.

Your knowledge base lives in the Linux home folder (`~/knowledge/<id>/`). To reach it from Windows, open `\\wsl$\Ubuntu\home\<you>\knowledge` in Explorer.

## Step by step

The rest of this page is what `install.sh` does, one command at a time.

## 1. Install

```bash
git clone <repo-url>
cd kb-distillery
pixi install
```

## 2. Create a knowledge base

```bash
pixi run distill init
```

The command asks for an id, a name and a kit. It creates `~/knowledge/<id>/` as its own git repository, with `kb.toml`, `wiki/`, `raw/inbox/` and `meta/`. Then it runs `distill doctor` and prints how to open the app.

To skip the questions:

```bash
pixi run distill init --kb-id my-kb --name "My KB" --kit base --yes
```

`--kit` takes `base` or `research`. See [Kit](concepts/kit.md).

To create it somewhere other than `~/knowledge`, pass `--dir`. The folder you pass is the parent: `distill init --kb-id my-kb --kit research --dir ~/projects --yes` creates `~/projects/my-kb/`. The directory may also be given as a positional argument: `distill init --kit research ~/projects --yes`. Point later commands at it with `--kb ~/projects/my-kb` or `KB=~/projects/my-kb`.

The command refuses an existing folder, the ids `think` and `demo`, and ids that are not lowercase letters, digits and dashes.

## 3. Open the app

```bash
pixi run distill launch --kb my-kb
```

The first launch installs the frontend dependencies and builds the app. This needs the network and takes a few minutes. Later launches start in seconds. The app listens on `http://127.0.0.1:8765`.

## 4. Check the setup

```bash
pixi run distill doctor --kb my-kb
```

Each line is PASS, WARN, FAIL or INFO. A FAIL comes with a `fix:` line. Doctor reads the environment and the knowledge base. It does not call a model or write anything.

## 5. Add a source and digest it

Put a file or a URL into `raw/inbox/`, move it into the catalog, then digest it. Paths are relative to the knowledge base folder.

```bash
pixi run distill ingest resolve "https://example.org/paper" --kb my-kb   # already in the kb?
pixi run distill ingest scrap "https://example.org/paper" --kb my-kb
pixi run distill ingest catalog raw/inbox/<file> --kb my-kb
pixi run distill digest easy <slug-or-raw-path> --kb my-kb
```

- `resolve` looks for an existing entry and uses no model.
- `scrap` copies the source into `raw/inbox/` and uses no model.
- `catalog` files it under `raw/<format>/`, records it in `meta/corpus.tsv`, and uses no model.
- `digest easy` prepares a short page at depth `easy`. Add `--fill` to have a model write the Problem and Main result lines. See [Digest tiers](concepts/digest-tiers.md).

Run `pixi run distill ingest --help` for the other source commands (`scrap-mail`, `scrap-youtube`, `scrap-wordpress`, `scrap-gdrive`).

Agents run these steps through skills in `.claude/skills/` of the knowledge base. Each skill file says when it applies and what it costs. See [Write a skill](guides/write-a-skill.md).

## 6. Check the result

```bash
pixi run distill lint --kb my-kb
```

The linter is the schema. If it passes, the pages are valid. It also regenerates `index.md` and `meta/corpus.tsv`.

## Your first sources in the app

A new knowledge base has no pages, so the graph is empty. The app can fill it without the command line:

- A "Build your knowledge base" card on the empty graph lets you drop files, link a folder on this machine, or open an example. Files and folders are added to `raw/inbox/` and catalogued, with no model call. Duplicates and unsupported file types are reported and skipped.
- The Pipeline screen and the card can start a digest job: pick sources, see a preview of the cost on each backend, start the job, watch it and cancel it. Each finished source is its own commit, and sources finished before a cancel stay. Jobs run one source at a time and need a Claude login or an Anthropic API key.

The card and the digest jobs are behind the flags `screen.first-run` and `screen.digest-jobs` (`src/kb_distillery/kits/base/defaults/flags.toml`), which are off for now. Until they are switched on, add sources with the commands in step 5.

## Try the demo first

`examples/demo` is a small knowledge base about a made-up job search. It is tracked in this repository.

```bash
pixi run distill kb show --kb examples/demo
pixi run distill doctor --kb examples/demo
pixi run distill kb open-example demo
```

`distill kb open-example <name>` opens a knowledge base from `examples/` in the app, read-only: every write (adding sources, notes, favorites, `distill ops`) is refused with "this knowledge base is read-only (example kb)", and a banner at the top of the app says so. Create your own knowledge base (step 2) to add sources. A kb is also read-only when its `kb.toml` has `read_only = true` under `[kb]` or `KB_READ_ONLY=1` is set. To experiment with writes, work on a copy of the demo.

## Choose how a model is billed

Every model call goes through one tool. It has three backends: `subscription` (your `claude login`), `api` (your Anthropic key) and `batch` (the Batch API, half price, results later). Pick one per run with `--backend`, or set `KB_LLM_BACKEND`. The default is `subscription`. Providers, tiers and prices are in [Language models](concepts/llm.md); the design is in [ADR 0001](adr/0001-single-llm-gateway.md).

## Next

- [Knowledge base](concepts/knowledge-base.md)
- [CLI reference](reference/cli.md)
