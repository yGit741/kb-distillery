# Ontology templates

A template is the schema a knowledge base follows: its page types, areas, source fields and typed edges. It is versioned in the engine (`templates/<name>/template.toml`); a kb names one and may extend it, never edit it. Code: `backend/src/kb/core/template.py`. Tests: `backend/tests/core/test_template.py`.

## A kb names its template

```toml
# kbs/<id>/kb.toml
[kb]
id = "my-kb"
name = "My knowledge base"
schema_version = "1.4"
template = "academic-research"      # optional; without it the kb.toml carries its own [types] / [edges]
```

`[types]` and `[edges]` in that kb.toml then **extend** the template's:

| Value | Rule |
|---|---|
| a table (`[types.source.paper]`, `[edges]`) | merged key by key |
| a list (`areas`, `types`, `symmetric`, `note_required`, `order`) | unioned, the template's entries first |
| a value the template already sets | must be equal; otherwise the engine refuses with `[types].source.paper.label: the template sets 'Paper' and kb.toml gives 'Article'` |

So a kb can add a type, an area or an edge type, and can restate what the template says, but cannot rename, recolour or remove anything the template defines. To change the template, change the template (a PR on `templates/<name>/`).

The merge is in `KbConfig.section`, so every reader (`kb.core.kbtypes`, `kb.services.cypher.edge_config`) sees the same result, whatever imports first.

## The file

```toml
[template]
name = "academic-research"    # must equal the folder name
version = 1                   # bump when a kb must notice the change
description = "..."

[types]    # the kb.toml [types] format, see backend/src/kb/core/kbtypes.py
[edges]    # types, symmetric, note_required, labels: see backend/src/kb/services/cypher.py (edge_config)
```

Any other top-level table is rejected until a phase gives it a meaning. Reserved: lint rules, skills and prompts, views, migrations, samples, page skeletons (today `meta-defaults/templates/*.md`).

## Errors you will meet

- `[kb] template = 'x' is not a known template (known: …)`: raised when kb.toml loads; the templates dir is `$KB_TEMPLATES_DIR` or `<engine>/templates`.
- `…: the template sets … and kb.toml gives …`: an edit; move it into the template or drop it.
- `[template] needs name = '<folder>' and a version`: the template file is malformed.
