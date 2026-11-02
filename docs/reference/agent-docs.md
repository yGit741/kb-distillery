# Agent docs

Agents that work in a knowledge base read short documents instead of this site. A knowledge base gets copies of nine of them in `.claude/docs/` when you run `distill init` (`dev.md`, `init.md` and `lifecycle.md` stay with the engine), and `distill init --refresh` updates the copies. The sources are in `src/kb_distillery/kits/base/defaults/docs/`.

`AGENTS.md` in a knowledge base holds a router: when an agent is about to do X, it reads the document for X. The documents are written for agents. They are short and exact. People can read them too.

| Document | When to read it |
|---|---|
| [page-model.md](../../src/kb_distillery/kits/base/defaults/docs/page-model.md) | Writing or checking a wiki page: layers, types, frontmatter, filename prefixes, note sections, `## My notes`. |
| [kits.md](../../src/kb_distillery/kits/base/defaults/docs/kits.md) | Writing or changing a kit, or the `[kb]`, `[types]` and `[edges]` tables of a `kb.toml`. |
| [publish.md](../../src/kb_distillery/kits/base/defaults/docs/publish.md) | Publishing a knowledge base, adding a publisher, or setting `[publish]`. |
| [storage.md](../../src/kb_distillery/kits/base/defaults/docs/storage.md) | Reading or writing raw sources from code, adding a connector, or setting `[storage]`. |
| [init.md](../../src/kb_distillery/kits/base/defaults/docs/init.md) | Setting up a first knowledge base with `distill init`, or checking the environment with `distill doctor`. |
| [raw-and-corpus.md](../../src/kb_distillery/kits/base/defaults/docs/raw-and-corpus.md) | Touching `raw/` or `meta/corpus.tsv`: format folders, the inbox, dispositions, file naming. |
| [collections.md](../../src/kb_distillery/kits/base/defaults/docs/collections.md) | Working on a course or series Contents table, or digesting a book. |
| [lifecycle.md](../../src/kb_distillery/kits/base/defaults/docs/lifecycle.md) | Committing, snapshotting, undoing, restoring, or reasoning about versions, hygiene and the nightly job. |
| [dev.md](../../src/kb_distillery/kits/base/defaults/docs/dev.md) | Running or changing the engine code: layout, environment, pixi tasks, write guards, worktrees. |
| [think.md](../../src/kb_distillery/kits/base/defaults/docs/think.md) | Sending a think note into knowledge bases, provenance, `think:` citations. |
| [workflows.md](../../src/kb_distillery/kits/base/defaults/docs/workflows.md) | Choosing a skill tier, running the ingest, query and distill commands. |
| [semantic-lint.md](../../src/kb_distillery/kits/base/defaults/docs/semantic-lint.md) | Handling coherence warnings and the semantic checks. |

To write a skill, read [Write a skill](../guides/write-a-skill.md).
