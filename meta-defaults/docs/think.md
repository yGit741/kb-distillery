# Think and `kbd distill`

Think is one standalone journal: `<kbs dir>/think` (its own git repo, human-owned, schema-free), outside every kb. Agents never write there, except the single provenance sidecar below, written by `kbd distill`.

## Sending a note into kbs

```bash
kbd distill <note> --to a,b            # ids or paths; note = name, name.md, sub/name.md, think:name.md
kbd distill <note> --to a --summarize --backend batch
kbd distill <note> --to a,b --no-commit
```

- **kb side:** `wiki/distilled-think-<slug>.md` in each kb, type `distilled-think`, `source: think:<note>.md`. One naming rule (`kb.distill.fanout.slug_for`) is shared with the `distill-think` skill, so the skill's `propose` continues the page this command wrote. Each kb gets its own `kb(distill)` commit.
- **think side:** `<think>/.provenance/<note>.md.json` records `{kb, page, at, note_sha256}` per kb. The note itself is never edited (a sidecar, not frontmatter, keeps human text byte-identical).
- **Idempotent:** an existing page and recorded entry are kept; a second run changes nothing and makes no commit. Everything is checked (note exists, kbs resolve, no page-name collision with another note) before the first write.
- **Citations:** `think:<note>.md` is the citation form; the legacy `think/<note>.md` still resolves (`fanout.resolve_cite`).
- **Not done here:** proposing edits to topic or question pages inside a kb stays with the `distill-think` skill (`python -m kb.distill propose|apply`).

## Billing

No LLM call by default: the summary is the note's first paragraph. `--summarize` makes one call (shared by all target kbs) through `kb.llm`. Backend: `--backend subscription|api|batch`, else `$KB_LLM_BACKEND`, else subscription (`claude -p`, your login). `api` bills the Anthropic key; `batch` bills it at half price but blocks while it polls.

## Known edge

The nightly `sync_human` commits the think repo's dirty files as `kb(think)` human edits, so `.provenance/*.json` lands in that history labelled human although the command wrote it.
