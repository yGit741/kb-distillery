import { useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { useDataSource, type LifecycleSnapshot, type TimelineRow } from "@/api";
import { CopyButton } from "@/components/CopyButton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { CONVENTIONS, GUARDRAILS, STORIES, VERSION_PARTS } from "./content";

type Filter = "all" | "kb" | "infra" | "schema";
const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "kb", label: "Knowledge" },
  { id: "infra", label: "Infra PRs" },
  { id: "schema", label: "Schema" },
];

export function filterTimeline(rows: TimelineRow[], filter: Filter, query: string): TimelineRow[] {
  const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
  return rows.filter((r) => {
    if (filter === "kb" && r.kind !== "kb") return false;
    if (filter === "infra" && r.kind === "kb") return false;
    if (filter === "schema" && !(r.type === "schema" || r.type === "paradigm")) return false;
    if (!terms.length) return true;
    const hay = `${r.subject} ${r.op ?? ""} ${r.target ?? ""} ${r.short}`.toLowerCase();
    return terms.every((t) => hay.includes(t));
  });
}

const Code = ({ children }: { children: ReactNode }) => (
  <code className="rounded bg-muted px-1 py-0.5 font-mono text-[0.85em] break-words">{children}</code>
);

const Empty = ({ children }: { children: ReactNode }) => (
  <p className="py-4 text-center text-sm text-muted-foreground">{children}</p>
);

function Section({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

/** Scroll container so wide tables never widen the page. */
const TableWrap = ({ children }: { children: ReactNode }) => (
  <div className="overflow-x-auto">
    <table className="w-full min-w-max text-left text-sm [&_td]:py-1.5 [&_td]:pr-4 [&_th]:pb-1.5 [&_th]:pr-4 [&_th]:text-xs [&_th]:font-medium [&_th]:text-muted-foreground">
      {children}
    </table>
  </div>
);

function Summary({ s }: { s: LifecycleSnapshot }) {
  const w = s.working;
  const cards: [string, string | number][] = [
    ["Knowledge version", s.version ? `kb-${s.version}` : "none yet"],
    ["Next step", `kb-${s.next_version}`],
    ["Schema", s.schema.version],
    ["Snapshots", s.snapshots[0]?.tag ?? "none"],
  ];
  if (w) {
    const sessions =
      w.sessions.ingest.length + w.sessions.distill.length + w.sessions.researcher.length + (w.sessions.ops ? 1 : 0);
    cards.push(
      ["Unpushed", w.unpushed ?? "?"],
      ["Open sessions", sessions],
      ["Uncommitted", `${w.lanes.knowledge} kb · ${w.lanes.tooling} tool`],
    );
  }
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4" data-testid="summary">
      {cards.map(([label, value]) => (
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

export function alertsFor(s: LifecycleSnapshot): ReactNode[] {
  const out: ReactNode[] = [];
  if (s.branch !== "main")
    out.push(<>This checkout is on <Code>{s.branch || "detached HEAD"}</Code> — knowledge commits only happen on main.</>);
  if (s.policy.hooks_installed === false)
    out.push(<>Git hooks are not installed — run <Code>pixi run install-hooks</Code> so commit messages and pushes are checked.</>);
  if (s.schema.pending.length) out.push(<>Pending schema migrations: {s.schema.pending.join(", ")}.</>);
  if (s.working?.think_dirty)
    out.push(<>{s.working.think_dirty} think/ file(s) changed — they will be committed as <Code>kb(think)</Code> before the next operation or tonight.</>);
  if (s.nightly?.hint)
    out.push(<>Nightly sync {s.nightly.summary} — run <Code>{s.nightly.hint}</Code>.</>);
  const stale = s.stale_worktrees ?? [];
  const merged = stale.filter((x) => x.merged);
  const session = stale.filter((x) => !x.merged);
  if (merged.length)
    out.push(<>{merged.length} merged worktree(s) left behind ({merged.map((x) => x.branch).join(", ")}) — <Code>pixi run ship -- prune --apply</Code> removes the clean ones.</>);
  if (session.length)
    out.push(
      <>
        {session.length} session worktree(s) on <Code>worktree-*</Code> branches (
        {session.map((x) => `${x.branch}: ${x.ahead} commits, ${x.dirty} uncommitted`).join("; ")}) — turn into a PR with{" "}
        <Code>pixi run ship -- start &lt;feature&gt;</Code> inside it, or <Code>ship -- prune --drop</Code>.
      </>,
    );
  return out;
}

function CommitChip({ r, github }: { r: TimelineRow; github: string | null }) {
  if (r.kind === "kb") return <Badge variant="primary">kb-{r.kb_version}</Badge>;
  if (r.kind === "pr-merge") {
    const label = `${r.pr ? `#${r.pr}` : "retro"}${r.kb_version ? ` → kb-${r.kb_version}` : ""}`;
    const chip = <Badge variant={r.type === "schema" || r.type === "paradigm" ? "warn" : "ok"}>{label}</Badge>;
    return r.pr && github ? (
      <a href={`${github}/pull/${r.pr}`} target="_blank" rel="noopener noreferrer">{chip}</a>
    ) : chip;
  }
  return <Badge variant="outline">{r.kind === "infra" ? (r.type ?? "infra") : "legacy"}</Badge>;
}

function Timeline({ s }: { s: LifecycleSnapshot }) {
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const rows = useMemo(() => filterTimeline(s.timeline, filter, query), [s.timeline, filter, query]);
  return (
    <Section title="History on main">
      <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center">
        <div className="flex flex-wrap gap-1" role="tablist" aria-label="History filter">
          {FILTERS.map((f) => (
            <Button
              key={f.id}
              role="tab"
              aria-selected={filter === f.id}
              variant={filter === f.id ? "default" : "secondary"}
              size="sm"
              onClick={() => setFilter(f.id)}
            >
              {f.label}
            </Button>
          ))}
        </div>
        <Input
          type="search"
          placeholder="Search subjects, ops, targets…"
          aria-label="Search history"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="sm:max-w-xs"
        />
      </div>
      {!rows.length ? (
        <Empty>{s.timeline.length ? "No commits match." : "No history yet."}</Empty>
      ) : (
        <ul className="divide-y" data-testid="timeline">
          {rows.map((r) => (
            <li key={r.sha} className={cn("flex flex-wrap items-baseline gap-x-3 gap-y-1 py-2", r.reverted_by && "opacity-60")}>
              <CommitChip r={r} github={s.github} />
              <span className="text-xs text-muted-foreground">{r.date.slice(0, 10)}</span>
              <span className="min-w-0 flex-1 basis-60 break-words text-sm">
                <span className={r.reverted_by ? "line-through" : undefined}>{r.subject}</span>
                {r.snapshot_tag && <Badge className="ml-2" variant="outline">{r.snapshot_tag}</Badge>}
                <TimelineExtra r={r} />
              </span>
              <span className="font-mono text-xs text-muted-foreground">{r.short}</span>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

function TimelineExtra({ r }: { r: TimelineRow }) {
  const extra: ReactNode[] = [];
  if (r.op && r.kind === "kb") extra.push(`op ${r.op} · ${r.target ?? ""}`);
  if (r.reverts) extra.push(`reverts ${r.reverts.slice(0, 9)}`);
  if (r.reverted_by) extra.push(`undone by ${r.reverted_by.slice(0, 9)}`);
  if (r.kind === "kb" && !r.reverted_by && r.op && !["think", "import", "undo"].includes(r.op))
    extra.push(<>undo: <Code>pixi run ops -- undo {r.short}</Code></>);
  if (!extra.length) return null;
  return (
    <small className="mt-0.5 block text-xs text-muted-foreground">
      {extra.map((e, i) => (
        <span key={i}>{i > 0 && " · "}{e}</span>
      ))}
    </small>
  );
}

function Snapshots({ s }: { s: LifecycleSnapshot }) {
  return (
    <Section title="Snapshots" description="Annotated tags named after the version they freeze. Sharing, export and restore start from one.">
      {!s.snapshots.length ? (
        <Empty>No snapshots yet — pixi run ops -- snapshot "label"</Empty>
      ) : (
        <TableWrap>
          <thead><tr><th>Tag</th><th>Date</th><th>Label</th><th>Restore</th></tr></thead>
          <tbody>
            {s.snapshots.map((t) => (
              <tr key={t.tag}>
                <td><Code>{t.tag}</Code></td>
                <td>{t.date}</td>
                <td>{t.label}</td>
                <td><CopyButton text={`pixi run ops -- restore ${t.tag}`} /></td>
              </tr>
            ))}
          </tbody>
        </TableWrap>
      )}
    </Section>
  );
}

function Working({ s }: { s: LifecycleSnapshot }) {
  const w = s.working;
  const policy = w
    ? `hooks ${s.policy.hooks_installed ? "installed" : "not installed"} · mode ${s.policy.mode} · guard ${s.policy.strict ? "strict" : "warn"}`
    : `mode ${s.policy.mode} · guard ${s.policy.strict ? "strict" : "warn"}`;
  const rows: [string, ReactNode][] = [
    ["Branch", <><Code>{s.branch || "detached"}</Code> @ {s.head}</>],
    ["Policy", policy],
    ["Migrations", `applied ${s.schema.applied.length} · pending ${s.schema.pending.length}`],
  ];
  if (w) {
    const sess: string[] = [
      ...w.sessions.ingest.map((x) => `ingest ${x.sha1} (${x.raw})`),
      ...w.sessions.distill.map((x) => `distill ${x.think} (${x.mode})`),
      ...w.sessions.researcher.map((x) => `researcher ${x}`),
      ...(w.sessions.ops ? [`ops ${w.sessions.ops.op} ${w.sessions.ops.target}`] : []),
    ];
    rows.splice(2, 0,
      ["Sessions", sess.length ? sess.map((x) => <div key={x}>{x}</div>) : "none"],
      ["Knowledge", <>{w.lanes.knowledge} uncommitted{w.knowledge.slice(0, 8).map((p) => <div key={p} className="text-xs text-muted-foreground break-all">{p}</div>)}</>],
      ["Tooling", `${w.lanes.tooling} uncommitted — ships through an infra PR`],
    );
    if (s.nightly)
      rows.push(["Nightly", <>{s.nightly.summary ?? (s.nightly.plist_installed ? "installed (22:00)" : "not installed — pixi run install-sync")} · backstop only: each kb step pushes right away · log <Code>{s.nightly.log}</Code></>]);
  }
  return (
    <Section title="Working state">
      <dl className="grid grid-cols-[6rem_1fr] gap-x-3 gap-y-2 text-sm">
        {rows.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-muted-foreground">{k}</dt>
            <dd className="min-w-0 break-words">{v}</dd>
          </div>
        ))}
      </dl>
      {!w && <Empty>Working tree, sessions and the nightly job are not part of this snapshot.</Empty>}
    </Section>
  );
}

function Branches({ s }: { s: LifecycleSnapshot }) {
  const list = s.infra_branches;
  if (!list) return null; // branches are not fixed by a commit: absent from shared snapshots
  return (
    <Section title="Open infra branches">
      {!list.length ? (
        <Empty>No infra branches — start one with pixi run ship -- start &lt;feature&gt; --worktree</Empty>
      ) : (
        <TableWrap>
          <thead><tr><th>Branch</th><th>vs main</th><th>Last commit</th><th>Date</th></tr></thead>
          <tbody>
            {list.map((b) => (
              <tr key={b.name}>
                <td><Code>{b.name}</Code></td>
                <td>{b.ahead} ahead · {b.behind} behind</td>
                <td>{b.last}</td>
                <td>{(b.date || "").slice(0, 10)}</td>
              </tr>
            ))}
          </tbody>
        </TableWrap>
      )}
    </Section>
  );
}

function Reference() {
  return (
    <>
      <Section title="How the knowledge base changes">
        <div className="mb-4 font-mono text-xl" aria-label="Version kb-x.y.z">
          <span className="text-muted-foreground">kb-</span>x.y.z
        </div>
        <dl className="mb-4 grid gap-2 text-sm sm:grid-cols-2">
          {VERSION_PARTS.map((p) => (
            <div key={p.key}>
              <dt className="font-medium">{p.title}</dt>
              <dd className="text-muted-foreground">{p.body}</dd>
            </div>
          ))}
        </dl>
        <TableWrap>
          <thead><tr><th>Commit</th><th>Where</th><th>Example</th><th>Version</th></tr></thead>
          <tbody>
            {CONVENTIONS.map((c) => (
              <tr key={c.commit}>
                <td><Code>{c.commit}</Code></td>
                <td>{c.where}</td>
                <td><Code>{c.example}</Code></td>
                <td>{c.version}</td>
              </tr>
            ))}
          </tbody>
        </TableWrap>
      </Section>
      <Section title="What to run">
        <div className="grid gap-4 md:grid-cols-3">
          {STORIES.map((g) => (
            <div key={g.group}>
              <h3 className="mb-2 text-sm font-semibold">{g.group}</h3>
              <dl className="flex flex-col gap-2 text-sm">
                {g.items.map((i) => (
                  <div key={i.what}>
                    <dt className="font-medium">{i.what}</dt>
                    <dd className="break-words text-muted-foreground">{i.how}</dd>
                  </div>
                ))}
              </dl>
            </div>
          ))}
        </div>
      </Section>
      <Section title="Guardrails">
        <ul className="list-disc space-y-1.5 pl-5 text-sm text-muted-foreground">
          {GUARDRAILS.map((g) => <li key={g}>{g}</li>)}
        </ul>
      </Section>
    </>
  );
}

export function LifecycleScreen() {
  const ds = useDataSource();
  const q = useQuery({ queryKey: ["lifecycle"], queryFn: () => ds.getLifecycle() });
  const s = q.data;
  const status = q.isPending
    ? "Loading…"
    : s
      ? `${s.version ? "kb-" + s.version : "no version yet"} · ${s.stats.kb_steps} knowledge steps · ${s.stats.pr_merges} PR merges · generated ${s.generated_at}`
      : "";
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold">Lifecycle</h1>
          <p className="text-sm text-muted-foreground break-words">{status}</p>
        </div>
        <Button variant="secondary" size="sm" onClick={() => void q.refetch()} disabled={q.isFetching}>
          <RefreshCw className={q.isFetching ? "animate-spin" : undefined} aria-hidden /> Refresh
        </Button>
      </div>

      {q.isPending && (
        <div className="flex flex-col gap-3" role="status" aria-label="Loading lifecycle">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-16" />)}
          </div>
          <Skeleton className="h-64" />
        </div>
      )}

      {q.isError && (
        <Card role="alert" className="border-bad">
          <CardContent className="flex flex-col gap-2 p-4">
            <p className="font-medium text-bad">Could not load the lifecycle snapshot.</p>
            <p className="text-sm text-muted-foreground break-words">{q.error.message}</p>
            <Button variant="secondary" size="sm" className="self-start" onClick={() => void q.refetch()}>Try again</Button>
          </CardContent>
        </Card>
      )}

      {s && (
        <>
          <Summary s={s} />
          {alertsFor(s).map((a, i) => (
            <div key={i} role="note" className="rounded-lg border border-warn/40 bg-warn/10 px-3 py-2 text-sm">{a}</div>
          ))}
          <Timeline s={s} />
          <div className="grid gap-4 lg:grid-cols-2">
            <Snapshots s={s} />
            <Working s={s} />
          </div>
          <Branches s={s} />
          <Reference />
        </>
      )}
    </div>
  );
}
