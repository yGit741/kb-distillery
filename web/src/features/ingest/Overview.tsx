import { Link } from "@tanstack/react-router";
import { ChevronRight } from "lucide-react";
import { useMemo, type ReactNode } from "react";
import { Empty, Loading } from "@/components/states";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { dataChanges, ingestTiles, type HealthLike, type LifecycleLike } from "@/features/system/model";
import { EventList, StatusStrip } from "@/features/system/StatusStrip";
import { useApiQuery } from "@/lib/useApiQuery";
import type { IngestTab } from "@/routes/search";

const num = (v: unknown) => (typeof v === "number" ? v : Number(v) || 0);

/** One counted row: a label, its number, and the place it is worked on. */
function Row({ label, value, to, action }: { label: string; value: ReactNode; to: { tab?: IngestTab; status?: string }; action: string }) {
  return (
    <li className="flex items-center gap-3 border-b py-2 text-sm last:border-b-0">
      <span className="min-w-0 flex-1">{label}</span>
      <span className="font-semibold tabular-nums">{value}</span>
      <Link to={"/ingest" as "/"} search={to as never} className="inline-flex shrink-0 items-center gap-0.5 text-xs text-primary hover:underline">
        {action} <ChevronRight aria-hidden className="size-3" />
      </Link>
    </li>
  );
}

/**
 * Ingest Overview (flag ui.data-system-split): four tiles (Inbox, Queue, Lint, Version), then the Add card (the add flow
 * with the counts of what waits), Data issues (counted here, worked on in Health) and Recent data changes (knowledge steps only).
 */
export function IngestOverview({ add, onOpen }: { add: ReactNode; onOpen: (tab: IngestTab) => void }) {
  const lc = useApiQuery(["lifecycle"], (d) => d.getLifecycle());
  const health = useApiQuery(["health"], (d) => d.getHealth(), { staleTime: 60_000 });
  const lcData = lc.data as LifecycleLike | undefined;
  const h = health.data as HealthLike | undefined;
  const v = h?.values ?? {};
  const strip = useMemo(() => ingestTiles(lcData, h), [lcData, h]);
  const changes = useMemo(() => dataChanges(lcData), [lcData]);
  return (
    <div className="flex flex-col gap-4">
      <StatusStrip items={strip} onOpen={(t) => onOpen(t as IngestTab)} label="Data status" cols="lg:grid-cols-4" />
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Card>
          <CardHeader>
            <CardTitle>Add</CardTitle>
            <CardDescription>Drop a paper or paste a link. New pages arrive as a proposal to review.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            {h && (
              <ul aria-label="Waiting">
                <Row label="Inbox" value={`${num(h.inbox_count)} files`} to={{ tab: "pipeline" }} action="Sort" />
                <Row label="Waiting to digest" value={num(v.queued)} to={{ tab: "pipeline" }} action="Open pipeline" />
                <Row label="Partial books" value={num(v.partial_books)} to={{ tab: "pipeline", status: "partial" }} action="Continue" />
              </ul>
            )}
            {add}
          </CardContent>
        </Card>
        <div className="flex flex-col gap-4">
          <Card>
            <CardHeader>
              <CardTitle>Data issues</CardTitle>
              <CardDescription>Counted here, worked on in Health.</CardDescription>
            </CardHeader>
            <CardContent>
              {!h ? (
                <Loading label="Checking the data" rows={3} />
              ) : (
                <ul aria-label="Data issues">
                  <Row label="Lint warnings" value={num(v.warnings)} to={{ tab: "health" }} action="Open in Health" />
                  <Row label="Orphan pages" value={num(v.orphans)} to={{ tab: "health" }} action="Open in Health" />
                  <Row label="Broken links" value={num(v.broken)} to={{ tab: "health" }} action="Open in Health" />
                </ul>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Recent data changes</CardTitle>
              <CardDescription>Knowledge steps only. The full list is in History.</CardDescription>
            </CardHeader>
            <CardContent>
              {!lcData ? <Loading label="Loading recent changes" rows={3} /> : !changes.length ? <Empty>No knowledge steps yet.</Empty> : <EventList events={changes} label="Recent data changes" />}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
