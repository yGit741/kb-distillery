# Agent proposals

An agent never writes a wiki page directly. Its change becomes a **proposal**: the owner reads exactly what would
change, accepts or rejects it hunk by hunk, and applies the accepted part as one knowledge step. The page's
`## My notes` is never part of a proposal and always survives.

Code: `src/kb_distillery/proposals/` (model, diff, checks, store, apply, service); HTTP: `/api/proposals`
(`src/kb_distillery/server/routers/proposals.py`). The review screen is behind the runtime flag `ui.proposals`.

## Model

One JSON file per proposal in `<kb>/.local/proposals/<id>.json` (kb-local state, never committed).

- **Proposal**: id, title, producer `{kind, instruction, context}` (kind: manual, chat, flags, ingest, restructure,
  lint, restore), created/updated, status (open, applied, rejected, stale), `base` `{slug: sha256}` of each touched
  page when the current revision was made, revisions, the current revision index, `decisions`
  `{hunk_id: {decision: accept|reject|correct, comment}}`, `checks` `{tier1, tier2}`, `applied {commit, kb_version, at}`.
- **Revision**: n, created, note (why: for example the owner's correction), ops, hunks, tier-1 findings.
- **Ops** (small on purpose; every producer composes them): `edit_page {slug, new_text}` (whole page),
  `create_page {slug, text}`, `set_frontmatter {slug, key, value}`, `rewrite_link {slug, from_slug, to_slug}`,
  `tombstone_page {slug, redirect_to}` and `move_block {from_slug, to_slug, block_id}` (validated; apply refuses
  them with 501 until they are implemented). Every op may carry `reason` and `sources`.
- **Hunks** are computed by the core, never by the producer. A page is split into blocks (the frontmatter, then
  paragraphs, headings and list groups of the body without My notes); difflib aligns old and new blocks and each
  changed run is one hunk `{id, op_id, slug, kind: prose|structure, before, after, tokens, links_added,
  links_removed, at, span}`. `tokens` is a word diff (`[[equal|insert|delete, text]]`). The id is a hash of the
  content, so an unchanged hunk keeps its id and its decision across revisions.

## Apply

Apply refuses with 409 when a touched page changed since the revision (status `stale`; make a new revision), and with
422 while an `error` finding points at a hunk that is not rejected. Otherwise it composes the accepted hunks onto the
pages (rejected hunks keep the old block), writes them with `vault.wikiio.write_page` inside an ops session
(`ops.core.begin("refine", ...)` ... `commit`) and records the commit: one `kb(refine): propose: <title> (<n> hunks)`
step per applied proposal.

## Tier-1 checks

Run on every new revision, before anyone sees it; no model: (a) every link in the new text resolves to a page or to a
page the same proposal creates, (b) the lint checks of `kb_distillery.lint.lint` on an in-memory copy of the pages
with the proposal's result overlaid (the real tree is not written) plus the My notes rule, (c) the privacy ratchet
terms on the new text, (d) the frontmatter still parses. Tier 2 (model-based review) is reserved.

## API

`GET /api/proposals?status=`, `POST /api/proposals {title, producer, ops, note?}`, `GET /api/proposals/{id}`,
`POST /api/proposals/{id}/revisions {ops, note}`, `POST /api/proposals/{id}/decisions {hunk_id, decision, comment?}`
or `{decisions: [...]}`, `POST /api/proposals/{id}/apply`, `POST /api/proposals/{id}/reject {reason?}`,
`GET /api/proposals/{id}/render` (each touched page with its blocks and the hunks positioned by block index).
A read-only server answers every write with 405.

## Plugging in a producer

Build ops from whatever the producer knows (an LLM answer through `kb_distillery.llm`, a lint finding, an ingest
result) and call `kb_distillery.proposals.service.create(title, ops, producer={kind, instruction, context})`; for the
owner's correction call `service.revise(id, ops, note)`. Never write pages yourself: the core cuts hunks, checks them
and applies only what the owner accepted.
