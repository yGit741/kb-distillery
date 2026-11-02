{{parent}}

## Research kit additions

This kb follows the `research` kit: papers, books, lectures and courses are digested into ideas, questions and people, with typed relations between pages. Its purpose is exploration and decision support: what is known, what is open, and which direction is worth taking. The kb's own scope (the field, the open question it serves) is written in its `README.md` and `kb.toml`; read them before judging whether a source is relevant.

- **Source types:** `paper-`, `part-` (a book part), `lecture-`, `article-`, `video-`, `blog-`, `chat-` (an AI chat) and `mail-` pages carry the digest of one raw item. Collections are `book-`, `notebook-`, `course-` and `series-`. Concepts are `theme-` (topic), bare-slug ideas, `q-` questions and persons. `.claude/docs/page-model.md` has the rules for each.
- **Extra source fields:** `authors`, `venue` and `arxiv-id` may appear in a source page's frontmatter.
- **Typed relations:** a page may state `relations:` of the kinds `extends`, `uses`, `contradicts`, `example-of`, `open-problem-in`, `addresses`, `discusses` and `student-of`. `contradicts` is symmetric and needs a note. Use `propose-relations` to get proposals; accept them per subject.
- **Person pages:** "add researcher <name>" / "index <name>'s papers" → `build-researcher-profile`. It indexes the bibliography and catalogs star-tier papers only; never digest a whole bibliography.
- **Topic areas:** the `area:` whitelist is this kb's own choice (`[types] areas` in `kb.toml`, each needs a `theme-<area>` page).
- **arXiv:** prefer the arXiv abstract page and the `arxiv-id` field over a publisher URL when scrapping a paper; resolve first, then scrap.

### Intent router additions

| The user says… | Do | Lands as |
|---|---|---|
| "add researcher <name>" / "index <name>'s papers" | `build-researcher-profile` | `kb(catalog)` |
| "check this source against my notes", "is it worth digesting" | `explore-raw-data` (read-only) | nothing |
