import { useNavigate, useSearch } from "@tanstack/react-router";
import { ExternalLink } from "lucide-react";
import { useMemo, useState } from "react";
import { CopyButton } from "@/components/CopyButton";
import { Empty, ErrorState, Loading } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { BacklogView, useOpenBacklogCount } from "@/features/backlog/BacklogView";
import { LifecycleScreen } from "@/features/lifecycle/LifecycleScreen";
import { PipelineScreen } from "@/features/pipeline/PipelineScreen";
import { useApiQuery } from "@/lib/useApiQuery";
import { cn } from "@/lib/utils";
import { SYSTEM_TABS, type SearchById, type SystemTab } from "@/routes/search";
import { needsYou, tiles, timeline, type EventKind, type HealthLike, type LifecycleLike, type OpsLike, type Tile, type Tone } from "./model";
import { HealthView } from "./HealthView";
import { FlagsView } from "./FlagsView";
import { KnowledgeBasesView } from "./KnowledgeBasesView";
import "./tours";
import { FLAG_ENV } from "@/flags";
import { useFlag } from "@/flags/useFlag";

const TAB_LABEL: Record<SystemTab, string> = { overview: "Overview", backlog: "Backlog", pipeline: "Pipeline", history: "History", health: "Health", flags: "Flags", kbs: "Knowledge bases" };

const TONE_TEXT: Record<Tone, string> = { ok: "text-ok", warn: "text-warn", bad: "text-bad", "": "text-foreground" };
const TONE_DOT: Record<Tone, string> = { ok: "bg-ok", warn: "bg-warn", bad: "bg-bad", "": "bg-muted-foreground/40" };

function StatusStrip({ items, onOpen }: { items: Tile[]; onOpen: (tab: SystemTab) => void }) {
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5" aria-label="System status">
      {items.map((t) => (
        <button
          key={t.id}
          type="button"
          data-testid={`tile-${t.id}`}
          data-tone={t.tone}
          onClick={() => onOpen(t.tab)}
          className="flex min-w-0 flex-col gap-0.5 rounded-xl border bg-card p-3 text-left shadow-[var(--shadow)] hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        >
          <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <span aria-hidden className={cn("size-2 rounded-full", TONE_DOT[t.tone])} />
            {t.label}
          </span>
          <span data-testid={`tile-${t.id}-value`} className={cn("text-lg font-semibold tabular-nums", TONE_TEXT[t.tone])}>{t.value}</span>
          <span className="truncate text-xs text-muted-foreground" title={t.hint}>
            {t.hint || " "}
          </span>
        </button>
      ))}
    </div>
  );
}

const fmtTime = (iso: string) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
};

const FILTERS: { id: "all" | EventKind; label: string }[] = [
  { id: "all", label: "All" },
  { id: "knowledge", label: "Knowledge" },
  { id: "tooling", label: "Tooling" },
  { id: "nightly", label: "Nightly" },
];

function Timeline({ lc, ops }: { lc?: LifecycleLike; ops?: OpsLike }) {
  const [filter, setFilter] = useState<"all" | EventKind>("all");
  const events = useMemo(() => timeline(lc, ops), [lc, ops]);
  const shown = filter === "all" ? events : events.filter((e) => e.kind === filter);
  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
        <div>
          <CardTitle>Timeline</CardTitle>
          <CardDescription>Knowledge steps, merges and nightly runs, newest first.</CardDescription>
        </div>
        <div className="flex flex-wrap gap-1" role="tablist" aria-label="Timeline filter">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              role="tab"
              aria-selected={filter === f.id}
              onClick={() => setFilter(f.id)}
              className="rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-accent aria-selected:bg-accent-soft aria-selected:text-primary"
            >
              {f.label}
            </button>
          ))}
        </div>
      </CardHeader>
      <CardContent>
        {!lc && !ops ? (
          <Loading label="Loading the timeline" rows={4} />
        ) : !shown.length ? (
          <Empty>No events.</Empty>
        ) : (
          <ol className="flex flex-col">
            {shown.map((e, i) => (
              <li key={`${e.at}-${i}`} className="flex gap-3 border-b py-2 last:border-b-0">
                <span className="w-28 shrink-0 pt-0.5 text-xs text-muted-foreground tabular-nums">{fmtTime(e.at)}</span>
                <div className="min-w-0 flex-1">
                  <p className="flex items-start gap-2 text-sm">
                    <Badge variant={e.kind === "knowledge" ? "primary" : e.kind === "nightly" ? (e.tone === "bad" ? "bad" : e.tone === "warn" ? "warn" : "ok") : "outline"} className="shrink-0">
                      {e.kind}
                    </Badge>
                    <span className="min-w-0 break-words">{e.title}</span>
                  </p>
                  {e.sub && (
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {e.href ? (
                        <a href={e.href} target="_blank" rel="noreferrer" className="hover:underline">
                          {e.sub} <ExternalLink aria-hidden className="inline size-3" />
                        </a>
                      ) : (
                        e.sub
                      )}
                    </p>
                  )}
                </div>
              </li>
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}

function NeedsYou({ ops, error, onRetry }: { ops?: OpsLike; error?: unknown; onRetry: () => void }) {
  if (error) return <ErrorState title="Could not load open work" error={error} onRetry={onRetry} />;
  if (!ops) return <Loading label="Checking open work" rows={3} />;
  const { threads, findings } = needsYou(ops);
  const loose = findings.filter((f) => !threads.some((t) => f.detail && t.next && f.fix === t.next));
  return (
    <Card>
      <CardHeader>
        <CardTitle>Needs you</CardTitle>
        <CardDescription>Open PRs, branches, sessions and leftovers, with the command that moves each on.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        {!threads.length && !loose.length && <Empty>Nothing open. All tidy.</Empty>}
        {threads.map((t) => (
          <div key={t.id} className="flex flex-col gap-1 rounded-lg border p-3">
            <p className="flex items-start gap-2 text-sm">
              <span aria-hidden className={cn("mt-1.5 size-2 shrink-0 rounded-full", TONE_DOT[(t.status as Tone) ?? ""] ?? TONE_DOT[""])} />
              <span className="min-w-0 flex-1 break-words font-medium">{t.title}</span>
              {t.state && <Badge variant="outline">{t.state}</Badge>}
            </p>
            {t.next && (
              <div className="flex items-center gap-2">
                <code className="min-w-0 flex-1 truncate rounded bg-muted px-2 py-1 text-xs" title={t.next}>
                  {t.next}
                </code>
                <CopyButton text={t.next} />
              </div>
            )}
          </div>
        ))}
        {loose.map((f, i) => (
          <div key={`f-${i}`} className="flex flex-col gap-1 rounded-lg border border-dashed p-3">
            <p className="text-sm">
              <Badge variant={f.severity === "error" ? "bad" : "warn"} className="mr-2">
                {f.kind}
              </Badge>
              {f.detail}
            </p>
            {f.fix && (
              <div className="flex items-center gap-2">
                <code className="min-w-0 flex-1 truncate rounded bg-muted px-2 py-1 text-xs" title={f.fix}>
                  {f.fix}
                </code>
                <CopyButton text={f.fix} />
              </div>
            )}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

/**
 * System: everything about the machine, not the knowledge. One status strip (each number from one
 * snapshot), then tabs: Overview (needs-you + one timeline), Pipeline, History and Health. Replaces the
 * old Pipeline, Ops, Lifecycle and Health tabs; their screens are reused here as they are.
 */
export function SystemScreen() {
  const search = useSearch({ strict: false }) as SearchById["system"];
  const navigate = useNavigate();
  // Flags tab: always in the local app (it is where ui.system-flags-tab itself is flipped); elsewhere gated by that flag.
  const flagsTab = useFlag("ui.system-flags-tab") || FLAG_ENV === "local";
  // Backlog tab: the local app only (the cards are local files; the share API has no backlog).
  const tabs = SYSTEM_TABS.filter((t) => (t !== "flags" || flagsTab) && (t !== "backlog" || FLAG_ENV === "local"));
  const openBacklog = useOpenBacklogCount();
  const tab: SystemTab = search.tab && tabs.includes(search.tab) ? search.tab : "overview";
  const lc = useApiQuery(["lifecycle"], (d) => d.getLifecycle());
  const ops = useApiQuery(["ops"], (d) => d.getOps(), { staleTime: 60_000 });
  const health = useApiQuery(["health"], (d) => d.getHealth(), { staleTime: 60_000 });
  const lcData = lc.data as LifecycleLike | undefined;
  const opsData = ops.data as OpsLike | undefined;
  const healthData = health.data as HealthLike | undefined;
  const strip = useMemo(() => tiles(lcData, opsData, healthData), [lcData, opsData, healthData]);
  const open = (t: SystemTab) => void navigate({ to: ".", search: { tab: t === "overview" ? undefined : t } as never });

  return (
    <div className="flex flex-col gap-4">
      <StatusStrip items={strip} onOpen={open} />
      <div className="flex gap-1 border-b" role="tablist" aria-label="System sections">
        {tabs.map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            onClick={() => open(t)}
            className="-mb-px border-b-2 border-transparent px-3 py-2 text-sm text-muted-foreground hover:text-foreground aria-selected:border-primary aria-selected:text-foreground"
          >
            {TAB_LABEL[t]}
            {t === "backlog" && openBacklog ? <Badge className="ml-1.5" aria-label={`${openBacklog} open`}>{openBacklog}</Badge> : null}
          </button>
        ))}
      </div>
      {tab === "overview" && (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <NeedsYou ops={opsData} error={ops.error} onRetry={() => void ops.refetch()} />
          <Timeline lc={lcData} ops={opsData} />
        </div>
      )}
      {tab === "backlog" && <BacklogView />}
      {tab === "pipeline" && <PipelineScreen />}
      {tab === "history" && <LifecycleScreen />}
      {tab === "flags" && <FlagsView />}
      {tab === "kbs" && <KnowledgeBasesView />}
      {tab === "health" && <HealthView health={healthData} error={health.error} onRetry={() => void health.refetch()} />}
    </div>
  );
}
