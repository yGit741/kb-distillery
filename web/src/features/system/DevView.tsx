import { useNavigate, useSearch } from "@tanstack/react-router";
import { useMemo } from "react";
import { Empty, Loading } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { BacklogView, useOpenBacklogCount } from "@/features/backlog/BacklogView";
import { useApiQuery } from "@/lib/useApiQuery";
import type { DevSection, SearchById } from "@/routes/search";
import { EmbeddingView } from "./EmbeddingView";
import { FlagsView } from "./FlagsView";
import { VariantsView } from "./VariantsView";
import { recentMerges, type LifecycleLike, type OpsLike } from "./model";
import { EventList } from "./StatusStrip";

const LABEL: Record<DevSection, string> = { backlog: "Backlog", flags: "Flags", variants: "Variants", queue: "Merge queue", embedding: "Embedding" };

function MergeQueue({ ops }: { ops?: OpsLike }) {
  if (!ops) return <Loading label="Reading the merge queue" rows={2} />;
  const q = ops.queue;
  const h = q?.holder;
  const waiters = q?.waiters ?? [];
  return (
    <Card>
      <CardHeader>
        <CardTitle>Merge queue</CardTitle>
        <CardDescription>The merge running now and the ones waiting behind it.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-1 text-sm">
        {!q ? <Empty>Queue state unavailable.</Empty> : !h ? <Empty>Idle. No merge running.</Empty> : (
          <>
            <p>Merging {h.pr ? `#${h.pr}` : h.branch}</p>
            {waiters.map((w, i) => <p key={i} className="text-muted-foreground">Waiting: {w.pr ? `#${w.pr}` : w.branch}</p>)}
          </>
        )}
      </CardContent>
    </Card>
  );
}

/**
 * System, Dev tab (flag ui.data-system-split, local app only): everything about building the engine. Sections Backlog,
 * Flags, Variants, Merge queue and Embedding, with Recent merges (tooling merges only) under them.
 */
export function DevView({ sections }: { sections: DevSection[] }) {
  const search = useSearch({ strict: false }) as SearchById["system"];
  const navigate = useNavigate();
  const openBacklog = useOpenBacklogCount();
  const section: DevSection = search.dev && sections.includes(search.dev) ? search.dev : sections[0]!;
  const lc = useApiQuery(["lifecycle"], (d) => d.getLifecycle());
  const ops = useApiQuery(["ops"], (d) => d.getOps(), { staleTime: 60_000 });
  const merges = useMemo(() => recentMerges(lc.data as LifecycleLike | undefined), [lc.data]);
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-1" role="tablist" aria-label="Dev sections">
        {sections.map((s) => (
          <button
            key={s}
            role="tab"
            aria-selected={section === s}
            onClick={() => void navigate({ to: ".", search: { tab: "dev", dev: s === sections[0] ? undefined : s } as never })}
            className="rounded-md px-2.5 py-1 text-sm text-muted-foreground hover:bg-accent aria-selected:bg-accent-soft aria-selected:text-primary"
          >
            {LABEL[s]}
            {s === "backlog" && openBacklog ? <Badge className="ml-1.5" aria-label={`${openBacklog} open`}>{openBacklog}</Badge> : null}
          </button>
        ))}
      </div>
      <div className="flex flex-col gap-4">
        <div className="min-w-0">
          {section === "backlog" && <BacklogView />}
          {section === "flags" && <FlagsView />}
          {section === "variants" && <VariantsView />}
          {section === "queue" && <MergeQueue ops={ops.data as OpsLike | undefined} />}
          {section === "embedding" && <EmbeddingView />}
        </div>
        <Card>
          <CardHeader>
            <CardTitle>Recent merges</CardTitle>
            <CardDescription>Features and fixes shipped to the engine.</CardDescription>
          </CardHeader>
          <CardContent>
            {!lc.data ? <Loading label="Loading merges" rows={3} /> : !merges.length ? <Empty>No merges yet.</Empty> : <EventList events={merges} label="Recent merges" />}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
