# Knowledge base

A knowledge base is a folder with a `kb.toml`. It holds your knowledge and its settings. The engine (this repository) holds code only.

```
my-kb/
  kb.toml        id, name, kit, schema version
  raw/           your sources; the engine never edits them
  wiki/          pages the agent writes and you edit
  meta/          manifest, aliases, coherence warnings
  .claude/       skills, docs and hooks copied from the kit
```

## Where it lives

Each knowledge base is its own git repository. The default place is `~/knowledge/<id>/`. Set `KB_DISTILLERY_HOME` to use another parent folder. Any folder with a `kb.toml` also works: pass `--kb <path>`.

The engine repository tracks one knowledge base, `examples/demo`, as a public sample. See [ADR 0003](../adr/0003-knowledge-outside-the-repo.md).

## Choose a knowledge base for a command

`--kb <id|path>` goes after the command: `distill lint --kb my-kb`. A value with `/` or starting with `.` or `~` is a path. Anything else is an id. Without `--kb`, the engine uses `$KB`, then the nearest `kb.toml` above the current folder, then the only knowledge base that exists.

`distill kb list` shows every knowledge base. `distill kb show` shows the selected one.

## The three areas

| Area | Owner | Rule |
|---|---|---|
| `raw/` | you | Immutable. A write guard refuses writes, and a storage connector refuses to overwrite a key. |
| `wiki/` | the agent, with you | Pages are flat; only generated section indexes sit in subfolders. Pages cross-link. The linter is the schema. |
| `meta/` | the engine | Manifest (`corpus.tsv`), aliases, coherence warnings. |

Inside a page, a section named `## My notes` is yours. No tool writes there.

## Pages

A page is a markdown file with frontmatter. Its `type` comes from the kit. Its layer is one of `source` (the digest of one raw item), `collection` (a group of sources) or `concept` (what the knowledge base grows). A source page has a `depth`: `listed`, `easy`, `full` or `deep`.

The shape of the frontmatter and the section rules are in [page-model.md](../../src/kb_distillery/kits/base/defaults/docs/page-model.md).

## The Open Knowledge Format shape

A knowledge base follows Open Knowledge Format v0.2 (schema 1.5):

- `wiki/` is the bundle root.
- `wiki/index.md` is generated. Its frontmatter holds only `okf_version`. Each `wiki/<type>/index.md` is a generated section index.
- `wiki/log.md` is the append-only activity log. It has one `## YYYY-MM-DD` heading per day, newest first.
- Pages link with relative markdown links: `[Title](slug.md)`. Wikilinks appear only in `## My notes`.
- Frontmatter keys: `maturity`, `description`, `created`, `generated` (`by`, `at`) and `sources`. Each entry in `sources` is an object with a `resource`.

Pages stay flat, so a link is always a bare `slug.md`. `pixi run okf-check` validates the shape and runs in the `ship` gates.

## History

Each knowledge operation is one git commit on `main` of the knowledge base: `kb(<op>): <summary> (kb-x.y.z)`. The operations are `import`, `catalog`, `digest`, `refine`, `distill`, `think`, `undo` and `restore`. Tags `kb-x.y.z` mark versions.

This gives you undo, snapshots and a time machine:

```bash
pixi run distill ops status --kb my-kb
pixi run distill ops log --kb my-kb
pixi run distill ops snapshots --kb my-kb
pixi run distill ops undo <sha> --kb my-kb
pixi run distill ops restore <tag> --kb my-kb
```

Free-form edits to `wiki/` go between `distill ops begin refine <target>` and `distill ops commit`. One transactional workflow (an ingest, ops or distill session) runs at a time.

Details: [lifecycle.md](../../src/kb_distillery/kits/base/defaults/docs/lifecycle.md).

## Checks

`distill lint` checks every page and regenerates `index.md` and `meta/corpus.tsv`. Git hooks run it before each commit. `distill hooks install --kb <id>` wires the hooks, which `distill init` already does for a new knowledge base.
