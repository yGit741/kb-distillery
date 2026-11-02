# Relations and proposals

A page can state typed links to other pages. A model can propose such links. Nothing is written to a page until you accept it.

## Relations

A relation is an entry in the `relations:` block of a page:

```yaml
relations:
  - {to: other-slug, kind: extends, note: "why it holds"}
```

The kinds a knowledge base accepts are the `types` under `[edges]` in its kit or `kb.toml`. The `research` kit declares `extends`, `uses`, `contradicts`, `example-of`, `open-problem-in`, `addresses`, `discusses` and `student-of`. The `base` kit declares `extends` and `uses`.

- A kind in `symmetric` (`contradicts`) is stored once.
- A kind in `note_required` (`contradicts`) needs a one-sentence note.
- The linter rejects an undeclared kind, a missing or self target, a repeated (kind, target), and a relation on a source page that is not at depth `full` or `deep`. A concept page may always state relations.

The graph reads relations behind the runtime flag `graph-relations`. See [kb.toml](../reference/kb-toml.md) for the `[edges]` table.

## Proposals

`distill propose` asks a model for relations between pages. It proposes only. It writes under `<kb>/.cache/`, never into `wiki/`.

```bash
pixi run distill propose submit --run first --dry-run --kb my-kb   # count and estimate, send nothing
pixi run distill propose submit --run first --max-usd 5 --kb my-kb
pixi run distill propose collect --run first --kb my-kb
pixi run distill propose review --run first --min-confidence 0.5 --kb my-kb
pixi run distill propose status --kb my-kb
```

- `submit` sends one request per subject page. A subject is a source page at depth `full` or `deep`, or a concept page. Candidates are the pages it links to or from, plus its closest search-card neighbours. The default backend is `batch`.
- `collect` waits for the batches, checks each proposal, and writes the proposals file. A proposal that fails a check goes to a rejected list with its reason.
- `review` prints a markdown digest per subject page.
- Confidence is stored as data. No proposal is dropped for low confidence unless you pass `--keep-above` to `submit`. You choose the cutoff when you read or apply.

## Apply

```bash
pixi run distill ops begin refine relations --kb my-kb
pixi run distill propose apply --min-confidence 0.7 --write --kb my-kb
pixi run distill ops commit "relations from run first" --kb my-kb
```

Without `--write`, `apply` is a dry run. `--min-confidence` has no default. You must say what counts as accepted. Narrow the set with `--run`, `--kinds`, `--subjects` and `--limit`.

The `propose-relations` skill walks an agent through the same steps, and the app shows proposals on its Relations screen (`GET /api/relations/proposals`).

## Billing

`propose submit` takes `--backend batch|api|subscription`. Without it, the tool reads `KB_LLM_BACKEND`, then uses `batch`. See [ADR 0001](../adr/0001-single-llm-gateway.md).
