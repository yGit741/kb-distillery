# kb-distillery

Turn what you read into a knowledge base you can search, question and grow. You put raw sources (papers, notes, web clips, chats) in a folder; kb-distillery helps you **distill** each one into a linked page, keeps the pages consistent with a linter, and shows them as a graph you can explore. It follows the [LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) idea: a flat, cross-linked set of notes that you and an agent both work on.

- **Your knowledge never enters this repo.** Each knowledge base is its own folder and its own git repository under `~/knowledge/` (outside this checkout). This repo is the engine.
- **No AI needed to start.** Reading, linking, searching and the dashboard all work without a key. Digesting and chat stay off until you add a Claude subscription login or an API key, and you choose how they are billed.
- **Pick your shape.** A *kit* defines the page types and relations of a knowledge base (a small `base`, and `research`); you can write your own.

## Quick start

You need [pixi](https://pixi.sh) (`curl -fsSL https://pixi.sh/install.sh | bash`), git, and Node (pixi installs it).

```bash
git clone <this-repository-url> kb-distillery
cd kb-distillery
pixi install
pixi run kbd init            # asks for an id, a name and a kit, then checks your setup
pixi run kbd launch --kb <id>
```

`kbd init` creates `~/knowledge/<id>/` as its own git repository from the kit you pick, runs `kbd doctor`, and prints the launch command. The first launch installs the frontend dependencies and builds the app (a few minutes, needs the network); after that it starts in seconds. Non-interactive: `pixi run kbd init --kb-id my-kb --name "My KB" --kit base --yes`.

`pixi run kbd doctor` checks your environment at any time and prints a fix for each problem. Add AI later with `claude login` or an `ANTHROPIC_API_KEY`; doctor shows which of the three backends (subscription, API, batch) are ready.

## How it fits together

| Part | What it is |
|------|------------|
| **Engine** | this repo: linter, ingest and digest tools, the API and the React app |
| **Knowledge base** | a folder under `~/knowledge/` with `wiki/` (pages), `raw/` (your sources, never edited), `meta/` and a `kb.toml` |
| **Kit** | the page types, areas and typed relations a knowledge base follows. See [`src/kb_distillery/kits/base/defaults/docs/kits.md`](src/kb_distillery/kits/base/defaults/docs/kits.md) |
| **Storage connector** | how raw sources are reached: a local folder, a Google Drive mount, or a package you add. [`storage.md`](src/kb_distillery/kits/base/defaults/docs/storage.md) |
| **Think** | one slow, human-only journal; `kbd distill <note> --to a,b` sends a note into knowledge bases with provenance on both sides. [`think.md`](src/kb_distillery/kits/base/defaults/docs/think.md) |
| **Publisher** | optional: publish a static snapshot of a knowledge base. Cloudflare is the first. [`publish.md`](src/kb_distillery/kits/base/defaults/docs/publish.md) |

The picture, the data flow and the invariants are in [`ARCHITECTURE.md`](docs/ARCHITECTURE.md). To change the code, read [`CONTRIBUTING.md`](.github/CONTRIBUTING.md). The roadmap is [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Everyday commands

```bash
pixi run kbd kb-list                  # your knowledge bases
pixi run kbd lint --kb <id>           # the schema check (the linter is the schema)
pixi run kbd doctor --kb <id>         # environment and kb checks
pixi run kbd distill <note> --to a,b  # think note -> knowledge bases
pixi run test                         # the test suite
```

## License

MIT, see [`LICENSE`](LICENSE).
