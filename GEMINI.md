# Gemini — start here

You are reading this vault through a GitHub import, with no shell. You cannot run
`meta/*.py`; navigate by reading files. This is a personal knowledge base for an MSc in
theoretical ML; the thesis topic is not yet chosen. Full schema: `AGENTS.md`.

## Where the knowledge is

| Path | What | Read it? |
|------|------|----------|
| `index.md` | Generated catalog of every wiki page, by type | **Always first** |
| `wiki/*.md` | The notes; the filename prefix is the type: `paper-` `part-` `lecture-` `article-` `blog-` `video-` `conversation-` `chat-` (sources: one raw item each), `book-` `notebook-` `course-` `series-` (collections: tables of sources), `theme-` (topics: research directions), `q-` (questions); ideas and people are bare slugs | Yes — open by slug |
| `think/*.md` | Owner's free-form drafts, not reviewed | Only if asked |
| `raw/` | Source files by format: `printed-docs/`, `handwritten/`, `presentations/`, `llm-chats/`, `emails/`, `web-clips/`, `images/` | No — inputs, not knowledge |
| `meta/`, dot-folders | Tooling code, skills, config | No |

Wikilinks are bare slugs: `[[tensor-rank]]` means `wiki/tensor-rank.md`. Frontmatter
`related:` lists more slugs; `layer:` (source, collection, concept) and `type:` say what a page is;
`status:` / `depth:` (listed, easy, full, deep — sources only) say how mature it is. A `## My notes`
section is the owner's own text.

## Answering a question (query-kb, no-shell version)

Adapted from `meta/skills/query-kb/SKILL.md`:

1. Read `index.md`; pick the relevant section (topics, questions, sources, ideas).
2. For broad or thematic questions, open the matching topic page `wiki/theme-*.md` first; for a
   course or video series, its `wiki/course-*.md` / `wiki/series-*.md` collection (Contents table).
3. Open 3–8 pages; follow `related:` and `[[links]]` one hop when useful.
4. Answer from those pages and cite every claim with `[[slug]]`. Mark anything from
   your own knowledge as *outside the vault*.
5. Never say "the vault has nothing on X" without checking `index.md`.
6. Read-only: you cannot write to the repo. If an answer deserves a new page,
   say so and the owner will file it from Claude Code or Cursor.

## Reading the history

Commit subjects tell you what changed: `kb(digest): <slug> (kb-1.0.3)` is one knowledge
step on main (version `kb-x.y.z`: paradigm.schema.step); `feat(dashboard): … (#12)` is a
tooling pull request (tooling has no version). Tags `kb-x.y.z` are frozen snapshots.
