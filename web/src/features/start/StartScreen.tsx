import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";
import type { LifecycleSnapshot } from "@/api";
import { ErrorState, Loading } from "@/components/states";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Code, TableWrap } from "@/features/lifecycle/LifecycleScreen";
import { useApiQuery } from "@/lib/useApiQuery";
import { cn } from "@/lib/utils";
import { COMMIT_ROWS, LifecycleLink, COMMIT_SCOPES, EDIT_ROWS, FEATURE_CARDS, PLACES, STEPS } from "./content";

/** The "Right now" cards, from the lifecycle snapshot (a shared, read-only site has no working-tree state). */
export function nowCards(s: LifecycleSnapshot): [string, string | number][] {
  const cards: [string, string | number][] = [
    ["Knowledge version", s.version ? `kb-${s.version}` : "none yet"],
    ["Last snapshot", s.snapshots.length ? s.snapshots[0]!.tag : "none"],
  ];
  const w = s.working;
  if (w) {
    const sessions = w.sessions.ingest.length + w.sessions.distill.length + w.sessions.researcher.length + (w.sessions.ops ? 1 : 0);
    cards.push(["Open sessions", sessions], ["Uncommitted knowledge", w.lanes.knowledge ?? 0]);
  }
  if (s.infra_branches) cards.push(["Open feature branches", s.infra_branches.length]);
  return cards;
}

function Now() {
  const q = useApiQuery(["lifecycle"], (ds) => ds.getLifecycle());
  if (q.isPending) return <Loading label="Loading the current state" rows={1} />;
  if (q.isError)
    return <ErrorState title="Could not load the current state." error={q.error} onRetry={() => void q.refetch()} />;
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5" data-testid="now">
      {nowCards(q.data).map(([label, value]) => (
        <Card key={label}>
          <CardContent className="p-3">
            <div className="text-xs text-muted-foreground">{label}</div>
            <div className="truncate text-lg font-semibold">{value}</div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function Section({ title, help, children }: { title: string; help?: ReactNode; children: ReactNode }) {
  return (
    <Card className="min-w-0">
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {help && <CardDescription>{help}</CardDescription>}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

const LINK = "text-primary hover:underline";

export function StartScreen() {
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <div>
        <h1 className="text-2xl font-semibold">Start here</h1>
        <p className="text-sm text-muted-foreground break-words">
          How to add and edit knowledge, and how to build a new feature for the knowledge base. You talk to the agent (Claude Code or Cursor); the trigger phrases below pick the right skill, and every change lands as one reviewable git commit.
        </p>
      </div>

      <Now />

      <Section title="Three places, three owners">
        <div className="grid gap-4 md:grid-cols-3">
          {PLACES.map((p) => (
            <div key={p.id} data-testid={`place-${p.id}`} className={cn("border-l-4 py-0.5 pl-3 text-sm", p.tone)}>
              <b>{p.title}</b>
              <p className="mt-1">{p.body}</p>
            </div>
          ))}
        </div>
      </Section>

      <Section
        title="Edit knowledge"
        help={<>Say the phrase to the agent. The skill runs the CLI, which commits the result on main as <Code>kb(&lt;op&gt;): … (kb-x.y.z)</Code> — one commit per operation.</>}
      >
        <TableWrap>
          <thead>
            <tr><th>You want to…</th><th>Say</th><th>Skill</th><th>Lands as</th></tr>
          </thead>
          <tbody>
            {EDIT_ROWS.map((r, i) =>
              "group" in r ? (
                <tr key={r.group}>
                  <td colSpan={4} className={cn("!pb-0 text-xs font-semibold tracking-wider text-muted-foreground uppercase", i > 0 && "!pt-4")}>
                    {r.group}
                  </td>
                </tr>
              ) : "wide" in r ? (
                <tr key={i} className="align-top">
                  <td>{r.want}</td>
                  <td colSpan={3}>{r.wide}</td>
                </tr>
              ) : (
                <tr key={i} className="align-top">
                  <td>{r.want}</td>
                  <td>{r.say}</td>
                  <td>{r.skill}</td>
                  <td>{r.lands}</td>
                </tr>
              ),
            )}
          </tbody>
        </TableWrap>
      </Section>

      <Section
        title="Develop a feature"
        help={
          <>
            Tooling — dashboard, explorer, ingest CLI, skills, schema — never commits to main. It goes through a branch and a pull request you approve. Skill: <Code>infra-pr</Code>. Just say what you want — <Code>fix the graph legend</Code>, <Code>add a filter to Digestion</Code> — and the agent runs the steps below and gives you the PR link; say <Code>merge</Code> when you are happy. (The full phrase → skill table is the Intent router in <Code>AGENTS.md</Code>.)
          </>
        }
      >
        <ol className="mb-4 grid list-decimal gap-2 pl-5 text-sm">
          {STEPS.map((s, i) => <li key={i} className="break-words">{s}</li>)}
        </ol>
        <div className="grid gap-4 lg:grid-cols-3">
          {FEATURE_CARDS.map((f) => (
            <div key={f.title} className={cn("border-l-4 py-0.5 pl-3 text-sm", f.tone)}>
              <h3 className="font-semibold">{f.title}</h3>
              <p className="mt-1 break-words">{f.body}</p>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Commit names at a glance">
        <TableWrap>
          <thead>
            <tr><th>Type</th><th>When</th><th>Example</th></tr>
          </thead>
          <tbody>
            {COMMIT_ROWS.map((r, i) => (
              <tr key={i}>
                <td>{r.type}</td>
                <td>{r.when}</td>
                <td><Code>{r.example}</Code></td>
              </tr>
            ))}
          </tbody>
        </TableWrap>
        <p className="mt-3 text-sm text-muted-foreground">
          Scope is always a component: <Code>{COMMIT_SCOPES}</Code>. Infra summaries start with a verb. Versions are knowledge-only: <Code>kb-x.y.z</Code> = paradigm · schema · step.
        </p>
      </Section>

      <div className="grid gap-4 lg:grid-cols-2">
        <Section title="Daily rhythm">
          <ul className="list-disc space-y-1.5 pl-5 text-sm text-muted-foreground">
            <li><b className="text-foreground">Morning:</b> <Code>pixi run launch</Code> opens this dashboard. <Link to={"/pipeline" as "/"} className={LINK}>Digestion</Link> shows the inbox and backlog.</li>
            <li><b className="text-foreground">During the day:</b> ask for skills; each finished operation is already committed.</li>
            <li><b className="text-foreground">22:00:</b> the nightly sync commits your <Code>think/</Code> edits, anything left over, and pushes main with its snapshot tags.</li>
            <li><b className="text-foreground">Weekly:</b> <Code>snapshot "week NN"</Code> to name a state you might share or return to.</li>
          </ul>
        </Section>
        <Section title="Rules that protect you">
          <ul className="list-disc space-y-1.5 pl-5 text-sm text-muted-foreground">
            <li>Agents never run git writes; only the <Code>ops</Code>, <Code>ship</Code> and <Code>daily-sync</Code> tools commit.</li>
            <li><Code>raw/</Code> and <Code>think/</Code> are never edited by agents, never rewritten by undo or restore.</li>
            <li>Undo and restore add commits — history is never rewritten.</li>
            <li>Tooling changes need your PR approval; PRs are never squashed.</li>
            <li>
              Full detail: <LifecycleLink /> tab · <Code>AGENTS.md</Code> · <Code>src/kb_distillery/kits/base/defaults/docs/</Code> · <Code>docs/guides/write-a-skill.md</Code>.
            </li>
          </ul>
        </Section>
      </div>
    </div>
  );
}
