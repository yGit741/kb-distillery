import { Link } from "@tanstack/react-router";
import { routeDefsNow } from "@/routes/defs";
import { modules } from "@/routes/modules";
import type { ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { Code } from "@/features/lifecycle/LifecycleScreen";

/** Static content of the Start screen (ported from the legacy dashboard/start.html). */

export type ChipKind = "kb" | "snap" | "schema" | "pr" | "other";
const CHIP_VARIANT = { kb: "primary", snap: "outline", schema: "warn", pr: "ok", other: "default" } as const;

/** A commit-type chip, coloured like the History timeline: knowledge blue, schema amber, PR merges green. */
export const Chip = ({ kind, children }: { kind: ChipKind; children: ReactNode }) => (
  <Badge variant={CHIP_VARIANT[kind]} className={kind === "kb" ? "bg-primary/6" : undefined}>
    {children}
  </Badge>
);

// Read at render time, not import time: this file is itself imported by a screen module, so `modules` is still being built then.
const hasScreen = (id: string) => Object.keys(modules).some((f) => f.endsWith(`/features/${id}/index.tsx`));

/**
 * A link to another screen, or its name as plain text where that screen does not exist in this build: the route is
 * flagged off (screen.* flags, e.g. lifecycle) or the build never imported it (share builds carry no Pipeline).
 */
export function ScreenLink({ id, children }: { id: string; children: ReactNode }) {
  const def = routeDefsNow().find((d) => d.id === id);
  return def && hasScreen(id) ? (
    <Link to={def.path as "/"} className="text-primary hover:underline">{children}</Link>
  ) : (
    <>{children}</>
  );
}

export const LifecycleLink = () => <ScreenLink id="lifecycle">Lifecycle</ScreenLink>;

const c = (s: string) => <Code>{s}</Code>;
const kb = (s: string) => <Chip kind="kb">{s}</Chip>;

export const PLACES: { id: string; title: string; tone: string; body: ReactNode }[] = [
  {
    id: "raw",
    title: "raw/ — inputs",
    tone: "border-muted-foreground/40",
    body: "PDFs, slides, mail, chat exports. Yours and immutable: only the scrap/catalog CLIs add files; agents never edit them.",
  },
  {
    id: "wiki",
    title: "wiki/ — knowledge",
    tone: "border-primary",
    body: (
      <>
        The notes in three layers: sources (papers, lectures, articles…), collections (books, courses, series) and concepts (ideas, topics, questions, people). Written by agents through skills; every change is a {c("kb(op)")} commit you can undo.
      </>
    ),
  },
  {
    id: "think",
    title: "think/ — your thinking",
    tone: "border-foreground/50",
    body: (
      <>
        Schema-free drafts that only you edit. Committed for you as {c("kb(think)")}; promoted into the wiki with {c("distill-think")}.
      </>
    ),
  },
];

export interface EditRow {
  want: ReactNode;
  say: ReactNode;
  skill: ReactNode;
  lands: ReactNode;
}
export type EditEntry = { group: string } | EditRow | { want: ReactNode; wide: ReactNode };

export const EDIT_ROWS: EditEntry[] = [
  { group: "Bring sources in" },
  { want: "Save a paper, link or file", say: c("scrap <url>"), skill: c("scrap-data"), lands: kb("kb(import)") },
  {
    want: "File the inbox into raw/ + listed Source pages",
    say: <>{c("catalog")} · {c("triage inbox")}</>,
    skill: c("ingest-to-catalog"),
    lands: kb("kb(catalog)"),
  },
  {
    want: "Index a researcher's bibliography",
    say: c("build researcher profile <name>"),
    skill: c("build-researcher-profile"),
    lands: kb("kb(catalog)"),
  },
  { group: "Write notes" },
  {
    want: "Quick skim of a source (depth easy)",
    say: <>{c("easy-digest <slug>")} · {c("skim")}</>,
    skill: c("easy-digest"),
    lands: kb("kb(digest)"),
  },
  { want: "Full note with key equations (depth full)", say: c("full-digest <raw>"), skill: c("full-digest"), lands: kb("kb(digest)") },
  {
    want: "High-stakes note with neighbours (depth deep)",
    say: <>{c("deep-digest <raw>")} + confirm heavy</>,
    skill: c("deep-digest"),
    lands: kb("kb(digest)"),
  },
  {
    want: "One chapter of a book",
    say: c("full-digest <book> part 3"),
    skill: <>{c("full-digest")} ({c("--part")})</>,
    lands: kb("kb(digest)"),
  },
  {
    want: 'Bare "digest"',
    wide: "The agent asks which tier first — easy, full or deep. It never picks full on its own.",
  },
  { group: "Shape the graph" },
  {
    want: "Split, merge, rename or fix notes",
    say: <>{c("split <idea>")} · {c("merge <a> and <b>")}</>,
    skill: c("wiki-edit"),
    lands: kb("kb(refine)"),
  },
  { want: "Check links around a new note", say: "runs after a digest", skill: c("semantic-lint-hop"), lands: kb("kb(refine)") },
  {
    want: "Audit a topic",
    say: c("lint-moc <topic>"),
    skill: c("lint-moc"),
    lands: <>read-only, fixes as {kb("kb(refine)")}</>,
  },
  { group: "Your own thinking" },
  { want: "Write freely", say: <>edit {c("think/")} yourself (Obsidian)</>, skill: "—", lands: <>{kb("kb(think)")} automatically</> },
  {
    want: "Turn a think note into wiki changes",
    say: c("distill think <file>"),
    skill: c("distill-think"),
    lands: kb("kb(distill)"),
  },
  { group: "Use, check, go back" },
  {
    want: "Ask a question",
    say: c("what do I know about <topic>"),
    skill: c("query-knowledge"),
    lands: <>nothing (filing back = {kb("kb(refine)")})</>,
  },
  { want: "See what changed", say: <>{c("kb history")} · {c("kb status")}</>, skill: c("kb-history"), lands: <>read-only — or the <LifecycleLink /> tab</> },
  { want: "Undo one bad step", say: c("undo <step>"), skill: c("kb-undo"), lands: <>{kb("kb(undo)")} — wiki only</> },
  { want: "Freeze the current state", say: c('snapshot "week 43"'), skill: c("kb-snapshot"), lands: <>tag <Chip kind="snap">kb-x.y.z</Chip></> },
  { want: "Go back to a snapshot", say: c("restore kb-x.y.z"), skill: c("kb-snapshot"), lands: kb("kb(restore)") },
  { want: "Hand the KB to another LLM", say: c("export kb"), skill: c("export-kb"), lands: <>zip in {c(".exported/")}</> },
];

export const STEPS: ReactNode[] = [
  <><b>Branch.</b> {c("pixi run ship -- start <feature> --worktree")} — an isolated copy on {c("infra/<feature>")}, so your vault and the nightly sync stay on main.</>,
  <><b>Build and try it.</b> Edit code in the worktree. Try the app from there with {c("pixi run app -- --port 8799")} (your usual one stays on 8765).</>,
  <><b>Commit.</b> {c('pixi run ship -- commit "feat(dashboard): add …"')} — runs tests, lint-skills and lint first; commits tooling files only.</>,
  <><b>Open the PR.</b> {c('pixi run ship -- pr --title "feat(dashboard): add …"')} — pushes and gives you the GitHub link to review.</>,
  <><b>Merge.</b> Approve, then say {c("merge")} → {c("pixi run ship -- merge")} makes a real merge commit {c("… (#N)")} (never squash) and updates your checkout.</>,
];

export const FEATURE_CARDS: { title: string; tone: string; body: ReactNode }[] = [
  {
    title: "A new skill",
    tone: "border-ok",
    body: (
      <>
        Say {c("create skill <name>")} (skill {c("create-skill")}) → {c("pixi run lint-skills")} → same PR flow, as {c("feat(skills): …")}. A skill that writes knowledge must end in an op commit.
      </>
    ),
  },
  {
    title: "A schema change",
    tone: "border-warn",
    body: (
      <>
        New note type, frontmatter field or rule that lint enforces: bump {c("SCHEMA_VERSION")} in {c("src/kb_distillery/vault/schema.py")}, add {c("src/kb_distillery/migrations/NNNN_<name>.py")}, run {c("pixi run ops -- migrate")} on the branch, commit as {c("schema(<component>): …")}. Merging snapshots first and bumps the middle digit.
      </>
    ),
  },
  {
    title: "A new kind of source",
    tone: "border-primary",
    body: (
      <>
        Handler sub-skills ({c("scrap-data/<type>")}, {c("ingest-to-catalog/<type>")}) as {c("feat(scrap)")}/{c("feat(ingest)")}, plus naming and tags as {c("schema(raw)")} — one PR. Then ingest the items as normal knowledge steps.
      </>
    ),
  },
];

export const COMMIT_ROWS: { type: ReactNode; when: string; example: string }[] = [
  { type: kb("kb(op)"), when: "any knowledge change — noun-phrase summary", example: "kb(digest): 2017-failures-of-gradient-based-deep-learning (kb-0.7.5)" },
  { type: <Chip kind="schema">schema</Chip>, when: "note rules change (+ migration)", example: "schema(books): add book page and partition (#4)" },
  { type: <Chip kind="pr">feat</Chip>, when: "new capability", example: "feat(dashboard): add start page" },
  { type: <Chip kind="pr">fix</Chip>, when: "wrong behaviour corrected", example: "fix(guard): make tests branch-independent" },
  { type: <Chip kind="other">chore</Chip>, when: "no behaviour change — config, docs, tests, refactors", example: "chore(git): ignore png screenshots" },
];

export const COMMIT_SCOPES =
  "vault raw books think ingest lint guard dashboard skills distill query export scrap git obsidian claude gemini";
