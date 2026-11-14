---
name: thought-ingest
description: >-
  Ingest one of the owner's own thoughts (a reMarkable page, a photo of paper, a pasted screenshot) into a named kb:
  keep the original, extract text and maths with a strong model, preview the source page and planned pages, chat,
  and write only on the owner's yes. Use for thought-ingest, ingest my thought, capture this. Do NOT use for whole
  notebooks or PDFs (catalog + digest), think/ notes (distill send) or web sources.
audience: app
mode: write
---

# thought-ingest

**LLM tier:** heavy · **Budget:** ~10–25k tokens per thought (one strong-model read of the image, plus the chat)

The owner's own conclusions are rare and dense, so this is the hands-on route: the owner names the kb, sees everything
before it is written, and can argue with every link. One thought = one `capture` source page (the original on top,
its extraction below) plus the concept pages it feeds.

## Triggers

- `/thought-ingest <kb> <image or path>`, `thought-ingest`, `ingest my thought`, `capture this`
- A pasted screenshot of handwriting with "ingest this into <kb>"

## Do NOT

- Pick the kb yourself: the owner names it. No kb named → ask one short question
- Write anything before the owner says yes to the preview (step 4)
- Write inside a page's `## My notes` (the owner's own section); quote the owner's words in the body instead, cited
- Write pages through an unquoted shell heredoc (`<<EOF`): it expands every `$f`, `$B` of the maths to nothing. Use the
  Write / Edit tools, or a quoted `<<'EOF'`
- Move or edit anything under `raw/` by hand: the original enters only through `distill ingest scrap` + `catalog`
- Use this for a whole notebook or a PDF (that is catalog + digest) or for `think/` notes (`distill send`)

## CLI

```bash
distill ingest resolve capture-2026-11-14-orthonormal-basis
distill ingest scrap /path/to/capture-2026-11-14-orthonormal-basis.webp
distill ingest catalog raw/inbox/capture-2026-11-14-orthonormal-basis.webp --format images
distill llm ask "Transcribe this handwritten note exactly: text as Markdown, maths as LaTeX in dollar signs. Mark any symbol you are unsure of with [?]." --image raw/images/capture-2026-11-14-orthonormal-basis.webp --model opus --max-tokens 4000 --backend subscription
python3 -m kb_distillery.search.query "orthonormal basis Parseval"
distill ops status
distill ops begin digest orthonormal-basis "capture: orthonormal basis gives Parseval"
distill ops commit
distill lint
```

## Agent steps

1. **Target and original.** Take the kb the owner named (`/thought-ingest yonatan-thesis …`). Name the thought
   `capture-<YYYY-MM-DD>-<slug>` (date it was written, short kebab slug of its subject) and check the name is free with
   `distill ingest resolve`. A pasted image is first saved to a scratch file of that name (keep its extension).
2. **Extract.** If you can see the image in this session, transcribe it yourself, carefully: text as Markdown, maths as
   LaTeX (`$\hat f(i)=\langle f,\phi_i\rangle$`), the owner's numbering and emphasis kept. A file you cannot see goes
   through `distill llm ask … --image <file> --model opus` (Billing below). List every reading you are unsure of
   (a misspelt word, an ambiguous symbol) as a transcription note; never silently fix the owner's words.
3. **Read the kb first.** Before proposing any page, search the target kb for what already exists: concept pages,
   sources and the theme pages near the thought's subject (`python3 -m kb_distillery.search.query "<terms>"`, and a
   look at `wiki/` filenames). Every planned page is labelled **new**, **update** or **link only**; never propose a page
   that duplicates an existing concept, and say which existing source already proves a claim.
4. **Preview, then chat.** Show, without writing anything:
   - the **source page** as it will look: title, the original image, the extraction, the transcription notes;
   - the **planned pages**: a table of page, action (new / update / link only), what it gets, and its links;
   - the **relations** each new page gets, with a one-line reason each;
   - **checks**: where the note is narrower or looser than the literature (real vs complex scalars, a missing
     hypothesis), shown as notes on the pages, the owner's text untouched.
   Then answer the owner's questions and change the plan (split, drop, rename, add a link) until they say yes.
5. **Bring in the original.** `distill ingest scrap <file>` puts it in `raw/inbox/`, then
   `distill ingest catalog raw/inbox/<name> --format images` files it under `raw/images/` (its own `kb(catalog)` commit).
6. **Write in one operation.** Run `distill ops status` first: if something is already staged or a session is open,
   tell the owner and stop, so foreign changes do not ride into this commit. Then `distill ops begin digest <slug> "<why>"`, and write:
   - `wiki/capture-<date>-<slug>.md`: `type: capture`, `layer: source`, `depth: full`, `maturity: digested`,
     `author: me`, `medium:` (`remarkable`, `paper-photo`, `screenshot`), `raw: raw/images/<file>`, `created:` the date,
     `related:` the pages it feeds. Body: `# Capture: <title>`, one line of context, `## Original` with
     `![<alt>](../raw/images/<file>)`, `## Extraction`, `## Main result`, `## Checks against the literature`, `## Feeds`.
   - each **new** concept page in the kb's page model (`## My notes` empty and last), citing the capture in `sources:`
     and quoting the owner's phrasing in the body;
   - each **update** as a link or a `related:` entry, never a rewrite of the page.
   Then `distill ops commit` (it lints first) and report the `kb-x.y.z` it prints.
7. **Look at it.** Open the new pages in the explorer (`/app/pages/<slug>`) and check the image shows and the maths
   renders; fix in a `refine` operation if not.

## Billing

Extraction in-session costs no extra call. A file extracted outside the session goes through `distill llm ask --image`,
the one LLM door: `--backend subscription` (default, your `claude login`), `api` (Anthropic key, per token) or `batch`
(half price, slow: for a pile of old pages, not one fresh thought). Model `opus`: a misread hat or conjugate costs more
than the call.

## Output

One `kb(catalog)` commit (the original under `raw/images/`, a `meta/corpus.tsv` row) and one `kb(digest)` commit: a
`capture-` source page, the new concept pages, and links on existing pages.

## Quality bar

- Every symbol of the extraction matches the original; uncertain readings are listed, not guessed
- No planned page duplicates an existing concept; every new page links to at least one existing page
- The owner saw the preview and said yes before anything was written
- The pages render in the explorer, image and maths included

## Next step

`propose-relations` for typed edges between the new pages and the rest of the kb; `semantic-lint-hop` if a check
found a conflict with an existing page.
