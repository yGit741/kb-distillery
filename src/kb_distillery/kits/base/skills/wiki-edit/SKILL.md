---
name: wiki-edit
description: >-
  Wrap free-form wiki edits (split, merge, rename, refine, file-back answers) in an ops session so they
  become one undoable kb(refine) commit. Use for split idea, merge notes, rename note, edit wiki, file back.
  Do NOT use inside full/deep-digest sessions (use draft + finalize) or for think/.
---

# wiki-edit

**LLM tier:** none · **Budget:** 0 tokens (the edit itself is whatever the task needs)

## Triggers

- `split <idea>`, `merge <notes>`, `rename <note>`, `edit wiki`, `refine <slug>`
- Any agent edit to `wiki/` outside a digest/distill CLI — including `semantic-lint-hop` fixes and `query-knowledge` file-backs

## Do NOT

- Write `wiki/` while an ingest session owns the file — use `draft` + `finalize`
- Touch `think/` (human-owned) or `raw/` (immutable)
- Leave a session open across unrelated tasks — one session = one coherent change

## CLI

```bash
distill ops begin refine split-tensor-rank "split tensor-rank into CP and Tucker rank"
distill ops commit
distill ops abort
distill ops status
```

## Agent steps

1. `distill ops begin refine <slug> "<why, one line>"` — op is usually `refine` (`digest`/`catalog` also allowed).
2. Make the edits in `wiki/` — never inside a page's `## My notes` section, which is the user's (guard warns on wiki writes without an open session; strict mode blocks them). On a `q-` page keep the H1 a short name (≤ 80 chars) and put the formal statement in `## Question` (required).
3. `distill ops commit` — lints, then commits only the files changed since `begin` as `kb(refine): <why> (kb-x.y.z)`. Write the why as intent in words (≤ 72 chars, e.g. "link the Chiang 2023 page where it was named"), not a slug — the pages touched are listed in the commit body automatically.
4. Report the version printed by the commit.

## Output

One commit on main: `kb(refine): … (kb-x.y.z)` with `KB-Op` / `KB-Target` trailers. Human `think/` edits, if any, are committed first as `kb(think)`.

## Next step

If the edit was wrong: `kb-undo` with that commit's sha.
