# Getting started

This page takes you from a clone to a first digest. You need macOS, [pixi](https://pixi.sh), and git. Node is installed by pixi.

AI features are optional. Reading, linking, linting and the app work without a key. A digest needs a Claude login or an API key.

## 1. Install

```bash
git clone <this-repository-url> kb-distillery
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

## Try the demo first

`examples/demo` is a small knowledge base about a made-up job search. It is tracked in this repository.

```bash
pixi run distill kb show --kb examples/demo
pixi run distill doctor --kb examples/demo
pixi run distill launch --kb examples/demo
```

`distill lint` rewrites generated files, so run it on a copy of the demo.

## Choose how a model is billed

Every model call goes through one tool. It has three backends: `subscription` (your `claude login`), `api` (your Anthropic key) and `batch` (the Batch API, half price, results later). Pick one per run with `--backend`, or set `KB_LLM_BACKEND`. The default is `subscription`. See [ADR 0001](adr/0001-single-llm-gateway.md).

## Next

- [Knowledge base](concepts/knowledge-base.md)
- [CLI reference](reference/cli.md)
