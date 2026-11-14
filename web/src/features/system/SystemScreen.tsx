import { Navigate, useNavigate, useSearch } from "@tanstack/react-router";
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
import { DEV_SECTIONS, SYSTEM_TABS, type DevSection, type SearchById, type SystemTab } from "@/routes/search";
import { needsYou, recentRuns, showOwnerOps, systemTiles, tiles, timeline, type EventKind, type HealthLike, type LifecycleLike, type OpsLike, type Tone } from "./model";
import { HealthView } from "./HealthView";
import { DevView } from "./DevView";
import { EventList, StatusStrip, TONE_DOT } from "./StatusStrip";
import { EmbeddingView } from "./EmbeddingView";
import { FlagsView } from "./FlagsView";
import { VariantsView } from "./VariantsView";
import { KnowledgeBasesView } from "./KnowledgeBasesView";
import "./tours";
import { FLAG_ENV } from "@/flags";
import { useFlag } from "@/flags/useFlag";
import { useDataSystemSplit } from "@/app/knowledgeNav";

const TAB_LABEL: Record<SystemTab, string> = { overview: "Overview", backlog: "Backlog", pipeline: "Pipeline", history: "History", health: "Health", embedding: "Embedding", flags: "Flags", variants: "Variants", kbs: "Knowledge bases", dev: "Dev" };

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
          {FILTERS.filter((f) => f.id !== "nightly" || showOwnerOps(ops)).map((f) => (
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
          <EventList events={shown} label="Timeline" />
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

function RecentRuns({ ops }: { ops?: OpsLike }) {
  const runs = useMemo(() => recentRuns(ops), [ops]);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Recent runs</CardTitle>
        <CardDescription>Nightly jobs and site deploys, with how each ended.</CardDescription>
      </CardHeader>
      <CardContent>
        {!ops ? <Loading label="Loading recent runs" rows={3} /> : !runs.length ? <Empty>No runs yet.</Empty> : <EventList events={runs} label="Recent runs" />}
      </CardContent>
    </Card>
  );
}

const TO_INGEST: readonly SystemTab[] = ["pipeline", "health", "history"];
const TO_DEV: Partial<Record<SystemTab, DevSection>> = { backlog: "backlog", flags: "flags", variants: "variants", embedding: "embedding" };

/** Flag ui.data-system-split: where an old System tab went, keeping the pipeline's own params; undefined when it stayed. */
export function movedTab(search: SearchById["system"]): { to: string; search: Record<string, unknown> } | undefined {
  const { tab, dev: _dev, ...rest } = search;
  if (tab && TO_INGEST.includes(tab)) return { to: "/ingest", search: { ...rest, tab } };
  const dev = tab ? TO_DEV[tab] : undefined;
  if (dev) return { to: "/system", search: { tab: "dev", dev } };
  return undefined;
}

/** Flag ui.data-system-split: System's tabs. Dev is the local app only (backlog, flags, variants are local tools). */
const SPLIT_TABS: readonly SystemTab[] = ["overview", "kbs", "dev"];

/**
 * System: everything about the machine, not the knowledge. One status strip (each number from one
 * snapshot), then tabs. Flag ui.data-system-split: three tiles (Nightly, Deploy, Open work) and tabs Overview
 * (Needs you, Recent runs), Knowledge bases and Dev; the data tabs live in Ingest. Flag off: the nine tabs as before.
 */
export function SystemScreen() {
  const search = useSearch({ strict: false }) as SearchById["system"];
  const navigate = useNavigate();
  const split = useDataSystemSplit();
  // Flags tab: always in the local app (it is where ui.system-flags-tab itself is flipped); elsewhere gated by that flag.
  const flagsTab = useFlag("ui.system-flags-tab") || FLAG_ENV === "local";
  // Backlog tab: the local app only (the cards are local files; the share API has no backlog).
  const variantsTab = useFlag("ui.variant-chooser");
  const local = FLAG_ENV === "local";
  const devSections: DevSection[] = DEV_SECTIONS.filter((d) => (d !== "flags" || flagsTab) && (d !== "backlog" || local) && (d !== "variants" || variantsTab));
  const tabs = split
    ? SPLIT_TABS.filter((t) => t !== "dev" || (local && devSections.length > 0))
    : SYSTEM_TABS.filter((t) => t !== "dev" && (t !== "flags" || flagsTab) && (t !== "backlog" || local) && (t !== "variants" || variantsTab));
  const openBacklog = useOpenBacklogCount();
  const tab: SystemTab = search.tab && tabs.includes(search.tab) ? search.tab : "overview";
  const lc = useApiQuery(["lifecycle"], (d) => d.getLifecycle(), { enabled: !split });
  const ops = useApiQuery(["ops"], (d) => d.getOps(), { staleTime: 60_000 });
  const health = useApiQuery(["health"], (d) => d.getHealth(), { staleTime: 60_000, enabled: !split });
  const lcData = lc.data as LifecycleLike | undefined;
  const opsData = ops.data as OpsLike | undefined;
  const healthData = health.data as HealthLike | undefined;
  const strip = useMemo(() => (split ? systemTiles(opsData) : tiles(lcData, opsData, healthData)), [split, lcData, opsData, healthData]);
  const open = (t: string) => void navigate({ to: ".", search: { tab: t === "overview" ? undefined : t } as never });

  // Old links (`?tab=pipeline`, `/pipeline`, `/lifecycle`, a tour's `?tab=variants`) land where the tab went.
  const moved = split ? movedTab(search) : undefined;
  if (moved) return <Navigate to={moved.to as "/"} search={moved.search as never} replace />;

  return (
    <div className="flex flex-col gap-4">
      <StatusStrip items={strip} onOpen={open} label="System status" cols={split ? "lg:grid-cols-3" : "lg:grid-cols-5"} />
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
            {(t === "backlog" || t === "dev") && openBacklog && local ? <Badge className="ml-1.5" aria-label={`${openBacklog} open`}>{openBacklog}</Badge> : null}
          </button>
        ))}
      </div>
      {tab === "overview" && (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <NeedsYou ops={opsData} error={ops.error} onRetry={() => void ops.refetch()} />
          {split ? <RecentRuns ops={opsData} /> : <Timeline lc={lcData} ops={opsData} />}
        </div>
      )}
      {tab === "dev" && <DevView sections={devSections} />}
      {tab === "backlog" && <BacklogView />}
      {tab === "pipeline" && <PipelineScreen />}
      {tab === "history" && <LifecycleScreen />}
      {tab === "flags" && <FlagsView />}
      {tab === "variants" && <VariantsView />}
      {tab === "kbs" && <KnowledgeBasesView />}
      {tab === "embedding" && <EmbeddingView />}
      {tab === "health" && <HealthView health={healthData} error={health.error} onRetry={() => void health.refetch()} />}
    </div>
  );
}
