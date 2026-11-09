# Agent proposals

An agent never writes a wiki page directly. Its change becomes a **proposal**: the owner reads exactly what would
change, accepts or rejects it hunk by hunk, and applies the accepted part as one knowledge step. The page's
`## My notes` is never part of a proposal and always survives.

Code: `src/kb_distillery/proposals/` (model, diff, checks, store, apply, service); HTTP: `/api/proposals`
(`src/kb_distillery/server/routers/proposals.py`). The review screen is behind the runtime flag `ui.proposals`.

## Model

One JSON file per proposal in `<kb>/.local/proposals/<id>.json` (kb-local state, never committed).

- **Proposal**: id, title, producer `{kind, instruction, context}` (kind: manual, chat, flags, ingest, restructure,
  lint, restore), created/updated, status (open, applied, rejected, stale, undone), `base` `{slug: sha256}` of each touched
  page when the current revision was made, revisions, the current revision index, `decisions`
  `{hunk_id: {decision: accept|reject|correct, comment}}`, `checks` `{tier1, tier2}`, `applied {commit, kb_version, at, hunks, pages, auto}`, `undone {at, commit}`.
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
terms on the new text, (d) the frontmatter still parses.

## Check tiers

Three tiers, cheapest first; only tier 1 can block apply.

1. **Tier 1, structural** (above): deterministic, runs on every revision, severity up to `error`.
2. **Tier 2, scoped semantic** (`proposals/checks_semantic.py`): one `kb_distillery.llm.ask` call per touched page.
   Scope = the touched pages plus their direct graph neighbours (links out and links in, `## My notes` links ignored),
   capped at `KB_PROPOSAL_SEMANTIC_CAP` pages (default 20), so cost follows the change, not the kb. The model sees the
   after-text of the page's hunks and neighbour excerpts and returns JSON findings `{code: contradiction | unsupported |
   duplicate | overclaim, severity: warning | info, message, hunk_id, evidence, neighbour_slug}`; findings on an unknown
   hunk id are dropped and `error` is never produced. Open internal coherence warnings
   (`meta/coherence-warnings.tsv`, 0 LLM) on a touched page are added as `coherence` findings. The result replaces
   `checks.tier2` of the proposal. Trigger: `POST /api/proposals/{id}/checks/semantic {backend?}` (synchronous, returns
   `{revision, findings}`), or `semantic: true` (and `backend`) on `POST /api/proposals` and `.../revisions`, which runs
   it right after tier 1 (a failed model call then leaves one `semantic-unavailable` info finding).
3. **Tier 3, nightly suggestions** (`proposals/nightly.py`): `pixi run proposals-nightly -- --kb <path> [--backend
   batch] [--dry-run]` scans for open coherence warnings, near-duplicate pages (title and link overlap) and pages over
   3x the median body length, and submits ONE batch asking for a fix per finding. `python -m kb_distillery.proposals
   collect --kb <path> <batch>` writes each answer: a concrete `edit_page` text becomes an open proposal with
   producer.kind `lint`; anything else becomes a `suggestion` record in `<kb>/.local/suggestions/`, listed by
   `GET /api/proposals/suggestions`. `--dry-run` prints the candidates and the request count and calls nothing. Tier 3
   never applies anything.

**Billing.** Tier 2 follows the request's `backend` (default `$KB_LLM_BACKEND`, then subscription); all three are
selectable. Tier 3 defaults to the Batch API (half price, collected later) and takes `--backend` too.

## Trust tiers

Every hunk gets one class (`klass`, set by the core, deterministic, no model; files from before it load and get it on read):
`links` (a link added, retargeted or unwrapped while the words the reader sees stay the same; a changed label or a
link deleted with its text is `claims`), `format` (whitespace, list markers, heading levels, punctuation outside
numbers), `typos` (one word of five letters or more changed by one edit, two for words of eight or more; no digits, never
a negation such as "not" or "never"), `claims` (any other prose change, and any change to a number), `structure`
(frontmatter, headings added or removed, `set_frontmatter`, `rewrite_link`), `new_page`, and the explicit ops
`tombstone`, `split` (`move_block`), plus `merge` and `rename`, reserved for the restructure producers (no op emits them
yet). A kb's `kb.toml` sets which class sits in which tier; the base kit default (`kits/base/defaults/proposals.toml`)
applies to any key it leaves out:

```toml
[proposals]
auto_apply = ["links", "format", "typos"]     # applied without review (when the producer asks, see below)
review     = ["claims", "structure", "new_page"]
explicit   = ["tombstone", "merge", "split", "rename"]   # never auto-applied; a review UI must ask per hunk
```

The core enforces the first tier (nothing outside `auto_apply` applies without a decision); the `explicit` list is
what a review UI reads to refuse a bulk accept over those hunks.

`GET /api/proposals/trust` returns `{auto_apply, review, explicit, source: "kb.toml" | "default"}`; there is no write
endpoint, edit kb.toml by hand.

**Auto-apply.** A proposal applies at once on create or revise only when the request carries `auto: true` (default
false, so nothing changes silently), every hunk is in an `auto_apply` class and tier 1 found no `error`. It goes through
the normal apply path (one `kb(refine)` commit) and records `applied.auto = true`. Any other proposal is never applied
by itself; its `auto_apply` hunks are pre-marked with a `suggested` accept decision (`decisions[id].suggested`) so the
owner's review of the boring part is one click, and the owner's own decision replaces it. `GET /api/proposals/feed?since=`
lists applied and undone proposals newest first: `{id, title, status, pages, hunks, classes, applied_at, commit, auto,
undoable}`.

**Undo.** `POST /api/proposals/{id}/undo` reverts the proposal's one commit with the ops undo path (a new `kb(undo)`
commit) and sets status `undone` with `undone.at`. It answers 409, naming the pages, when a later commit changed one of
the pages the proposal wrote (undo those first); it never reverts blindly. It works for manually applied proposals too.

**Self-suggestions.** `nightly.suggest_from_coherence(kb)` (0 LLM, part of every `proposals-nightly` run, and callable
alone) turns each open coherence warning that names exactly two pages into a `suggestion` record with `finding`
`contradiction` or `duplicate`, the two slugs, the warning text and `draft: "ask the agent to draft a fix"`. It is
deduped by coherence id; `POST /api/proposals/suggestions/{id}/dismiss` persists a dismissal and a dismissed one is never
recreated.

## API

`GET /api/proposals?status=`, `POST /api/proposals {title, producer, ops, note?}`, `GET /api/proposals/{id}`,
`POST /api/proposals/{id}/revisions {ops, note}`, `POST /api/proposals/{id}/decisions {hunk_id, decision, comment?}`
or `{decisions: [...]}`, `POST /api/proposals/{id}/apply`, `POST /api/proposals/{id}/reject {reason?}`,
`GET /api/proposals/{id}/render` (each touched page with its blocks and the hunks positioned by block index), plus the
trust, feed, undo and suggestion routes above. `auto: true` is accepted on create and on revisions.
A read-only server answers every write with 405.

## Plugging in a producer

Build ops from whatever the producer knows (an LLM answer through `kb_distillery.llm`, a lint finding, an ingest
result) and call `kb_distillery.proposals.service.create(title, ops, producer={kind, instruction, context})`; for the
owner's correction call `service.revise(id, ops, note)`. Never write pages yourself: the core cuts hunks, checks them
and applies only what the owner accepted.
