# Think

Think is one journal for your own writing. It sits outside every knowledge base, at `~/knowledge/think/`, and is its own git repository. It has no schema. Agents never edit it.

## Send a note into knowledge bases

```bash
pixi run distill send <note> --to a,b
```

`<note>` is a name, `name.md`, `sub/name.md` or `think:name.md`. `--to` takes knowledge base ids or paths, separated by commas.

For each target, the command:

1. Writes `wiki/distilled-think-<slug>.md` in that knowledge base, with `type: distilled-think` and `source: think:<note>.md`.
2. Commits it there as one `kb(distill)` step.
3. Records the page in `<think>/.provenance/<note>.md.json`, so the link is known on both sides. The note itself is not changed.

Running it again changes nothing. Every target is checked before the first write.

The summary on the page is the first paragraph of the note. With `--summarize`, a model writes it. Choose the billing with `--backend subscription|api|batch`. See [ADR 0001](../adr/0001-single-llm-gateway.md).

Other options: `--think <folder>` uses another think folder. `--no-commit` writes without committing. `--no-push` commits without pushing.

## Cite a note

A page cites a note as `think:<note>.md`. A link into `think/` is not allowed in a page.

## Edit a knowledge base from a note

The `distill-think` skill proposes edits to topic and question pages from a note. It writes a transient page for you to review, then applies the patch on request.

More: [think.md](../../src/kb_distillery/kits/base/defaults/docs/think.md)
