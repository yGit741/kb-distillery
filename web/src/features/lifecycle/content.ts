/** Static explanatory content of the Lifecycle tab (from meta/dashboard/lifecycle.html). */

export const VERSION_PARTS: { key: string; title: string; body: string }[] = [
  { key: "x", title: "x · paradigm", body: "How knowledge is stored and queried (LLM wiki today). Bumped by a paradigm PR." },
  { key: "y", title: "y · schema", body: "The rules every note follows (SCHEMA_VERSION in meta/schema.py). Bumped by a schema PR, which carries its migration." },
  { key: "z", title: "z · step", body: "One knowledge operation = one commit on main. Computed, never typed." },
  { key: "t", title: "tooling", body: "Not versioned. Each infra change is a PR, identified by its number #N." },
];

export const CONVENTIONS: { commit: string; where: string; example: string; version: string }[] = [
  { commit: "kb(op): …", where: "main, by the tools", example: "kb(digest): 2017-failures-of-gradient-based-deep-learning (kb-0.7.5)", version: "z + 1" },
  { commit: "feat(component): add …", where: "infra/<feature> → PR", example: "feat(dashboard): add lifecycle tab (#3)", version: "—" },
  { commit: "fix(component): … · chore(component): …", where: "infra/<feature> → PR", example: "chore(git): ignore png screenshots (#5)", version: "—" },
  { commit: "schema(component): …", where: "infra/<feature> → PR + migration", example: "schema(books): add hub and partition (#4)", version: "y + 1, z → 0" },
  { commit: "paradigm(component): …", where: "branch → PR", example: "paradigm(vault): adopt RAG hybrid (#9)", version: "x + 1" },
];

export const STORIES: { group: string; items: { what: string; how: string }[] }[] = [
  {
    group: "Knowledge work",
    items: [
      { what: "Add a paper", how: "scrap-data → ingest-to-catalog → easy-digest | full-digest | deep-digest → semantic-lint-hop. Each step commits itself." },
      { what: "Split, merge, rename notes", how: 'pixi run ops -- begin refine <slug> "why" → edit → pixi run ops -- commit (skill wiki-edit).' },
      { what: "think/ → public KB", how: "Write in think/ (committed as kb(think)) → distill-think propose → review → apply." },
      { what: "Undo one bad step", how: "pixi run ops -- log → pixi run ops -- undo <sha> (skill kb-undo). Only wiki/ is rewritten." },
      { what: "Ask the KB", how: "query-knowledge — read-only; filing an answer back is a refine session." },
    ],
  },
  {
    group: "Snapshots and history",
    items: [
      { what: "Freeze the current state", how: 'pixi run ops -- snapshot "week 43" (skill kb-snapshot).' },
      { what: "Go back to a snapshot", how: "pixi run ops -- restore kb-x.y.z — one new commit; raw/ and think/ untouched." },
      { what: "See what changed", how: "pixi run ops -- log --kb · pixi run ops -- status (skill kb-history)." },
      { what: "Share the KB", how: "Built from a snapshot tag (share-kb, later)." },
    ],
  },
  {
    group: "Knowledge infra development",
    items: [
      { what: "Explorer, dashboard, CLI", how: 'pixi run ship -- start <feature> --worktree → edit → ship -- commit "feat(scope): …" → ship -- pr → ship -- merge (skill infra-pr).' },
      { what: "Add or change a skill", how: "create-skill → pixi run lint-skills → same PR flow." },
      { what: "Change the schema", how: "PR with SCHEMA_VERSION bump + meta/migrations/NNNN_*.py → pixi run ops -- migrate on the branch → ship -- merge snapshots and bumps y." },
      { what: "New kind of source", how: "Handler sub-skills (feat) + naming/tags (schema) in one PR, then ingest items as knowledge steps." },
      { what: "Change the paradigm", how: "Long-lived infra/ branch, compare with query-knowledge on both, merge as paradigm." },
    ],
  },
];

export const GUARDRAILS: string[] = [
  "Agents never run git writes. The shell hook allows only single pixi run ops|ship|daily-sync invocations; chained commands are refused.",
  "Wiki edits need an open operation (meta/guard.py; warns now, blocks once strict).",
  "Commit messages are checked by meta/githooks/commit-msg; pushes to main must be kb steps (z+1) or PR merges (pre-push).",
  "Undo and restore never touch raw/, think/, wiki/log.md or generated files, and never reset history.",
  "PRs are never squashed; schema PRs snapshot before (pre-) and after (post-) the merge. The nightly sync takes the same lock as ops.",
  "Hygiene is automatic, never a gate: every kb step pushes main right away (the nightly sync is the backstop); ship merge removes its own worktree; ship prune --apply removes merged, clean worktrees only; stale worktrees, session branches and the nightly state show up here and in pixi run lanes.",
];
