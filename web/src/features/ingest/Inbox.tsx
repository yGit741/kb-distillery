import { useEffect } from "react";
import { Link } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import type { IngestListItem } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Empty, ErrorState, Loading } from "@/components/states";
import { useFlag } from "@/flags/useFlag";
import { useApiQuery } from "@/lib/useApiQuery";
import { cn } from "@/lib/utils";
import { groupIngests, INGEST_LIST_KEY, tierLabel, useIngestJob, useRetryIngest, whenLabel } from "./model";

const STEP_LABEL: Record<string, string> = { fetch: "Fetching", convert: "Reading the text", digest: "Digesting", propose: "Preparing the pages" };
const END_WORD: Record<string, string> = { rejected: "Rejected", undone: "Undone", applied: "Applied" };

const upper = (s: string) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);

function Meta({ i }: { i: IngestListItem }) {
  return <span>{i.kind === "url" ? "Web page" : "File"} · {tierLabel(i.tier)}</span>;
}

/** The first line of a row: the source, its state in muted words, and when. */
function Head({ i, state, when, to, search }: { i: IngestListItem; state: string; when: string; to?: string | null; search?: Record<string, string> }) {
  const name = <span className="min-w-0 truncate font-medium" title={i.source}>{i.source}</span>;
  return (
    <div className="flex items-baseline gap-3">
      {to ? <Link to={to as "/"} search={(search ?? {}) as never} className="min-w-0 truncate font-medium hover:underline" title={i.source}>{i.source}</Link> : name}
      <span className="shrink-0 text-xs text-muted-foreground" data-testid="row-state">{state}</span>
      <span className="ml-auto shrink-0 whitespace-nowrap text-xs text-muted-foreground">{when}</span>
    </div>
  );
}

/** A running job: its step, live from the job's own stream; when the stream ends the list is read again. */
function RunningRow({ i }: { i: IngestListItem }) {
  const qc = useQueryClient();
  const job = useIngestJob(i.id);
  const ended = job !== null && job.status !== "running";
  useEffect(() => {
    if (ended) void qc.invalidateQueries({ queryKey: INGEST_LIST_KEY });
  }, [ended, qc]);
  const steps = job?.steps ?? i.steps;
  const step = job?.step || i.step;
  const detail = steps.find((s) => s.name === step)?.detail ?? "";
  return (
    <li className="flex flex-col gap-1 py-3" data-testid="ingest-row" data-id={i.id} data-group="progress">
      <Head i={i} state="Working" when={whenLabel(i.started)} />
      <div className="flex items-center gap-x-3 text-xs text-muted-foreground">
        <Meta i={i} />
        <span className="inline-flex min-w-0 items-center gap-1.5" role="status">
          <span className="size-1.5 shrink-0 rounded-full bg-primary motion-safe:animate-pulse" aria-hidden />
          <span className="truncate" title={detail}>{STEP_LABEL[step] ?? upper(step)}{detail && ` · ${detail}`}</span>
        </span>
      </div>
    </li>
  );
}

function ReviewRow({ i }: { i: IngestListItem }) {
  const stale = i.proposal_status === "stale";
  // flag ui.edit-preview: a source waiting for review opens as its plan graph over the graph
  const plan = useFlag("ui.edit-preview");
  return (
    <li className="flex flex-col gap-1 py-3" data-testid="ingest-row" data-id={i.id} data-group="review">
      <Head i={i} state={stale ? "Pages changed since" : "Ready"} when={whenLabel(i.finished ?? i.started)} to={i.proposal_id ? (plan ? "/graph" : `/proposals/${encodeURIComponent(i.proposal_id)}`) : null} search={plan && i.proposal_id ? { preview: i.proposal_id } : undefined} />
      <div className="flex flex-wrap items-center gap-x-3 text-xs text-muted-foreground">
        <Meta i={i} />
        <span>{i.pages.length} {i.pages.length === 1 ? "page" : "pages"} to review</span>
      </div>
    </li>
  );
}

function DoneRow({ i }: { i: IngestListItem }) {
  const word = END_WORD[i.proposal_status ?? ""] ?? "Done";
  const when = whenLabel(i.proposal_updated) || whenLabel(i.finished ?? i.started);
  return (
    <li className="flex flex-col gap-1 py-3" data-testid="ingest-row" data-id={i.id} data-group="done">
      <Head i={i} state={word} when={when} to={i.proposal_id && i.proposal_status ? `/proposals/${encodeURIComponent(i.proposal_id)}` : null} />
      <div className="text-xs text-muted-foreground"><Meta i={i} /></div>
    </li>
  );
}

function FailedRow({ i }: { i: IngestListItem }) {
  const retry = useRetryIngest();
  const reason = i.error ? upper(i.error) : "It stopped before it was finished.";
  return (
    <li className="flex flex-col gap-1 py-3" data-testid="ingest-row" data-id={i.id} data-group="failed">
      <Head i={i} state={i.status === "interrupted" ? "Interrupted" : "Stopped"} when={whenLabel(i.finished ?? i.started)} />
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
        <Meta i={i} />
        <span className="min-w-0 break-words">{reason}</span>
        {i.kind === "url" ? (
          <Button variant="ghost" size="sm" className="-my-1 h-6 px-2 text-xs" disabled={retry.isPending || retry.isSuccess} onClick={() => retry.mutate(i)}>
            {retry.isPending ? "Starting" : retry.isSuccess ? "Started again" : "Try again"}
          </Button>
        ) : (
          <span>Drop the file again to try again.</span>
        )}
        {retry.isError && <span role="alert" className={cn("text-foreground/80")}>{retry.error instanceof Error ? retry.error.message : "Could not start."}</span>}
      </div>
    </li>
  );
}

const ROW = { progress: RunningRow, review: ReviewRow, done: DoneRow, failed: FailedRow } as const;

/** What was brought in and where each one stands; groups are left out when empty. */
export function IngestInbox() {
  const q = useApiQuery(INGEST_LIST_KEY, (ds) => ds.listIngest());
  if (q.isPending) return <Loading label="Loading your ingests" rows={2} />;
  if (q.isError) return <ErrorState title="Could not load your ingests." error={q.error} onRetry={() => void q.refetch()} />;
  const groups = groupIngests(q.data);
  if (groups.length === 0) return <Empty>Nothing brought in yet. What you add shows up here.</Empty>;
  return (
    <div className="flex flex-col gap-6" aria-label="Your ingests">
      {groups.map((g) => {
        const Row = ROW[g.id];
        return (
          <section key={g.id} className="flex flex-col" aria-label={g.title}>
            <header className="flex items-baseline gap-2 border-b pb-1.5">
              <h2 className="text-sm font-semibold">{g.title}</h2>
              <span className="text-xs text-muted-foreground">{g.items.length}</span>
            </header>
            <ul className="divide-y">{g.items.map((i) => <Row key={i.id} i={i} />)}</ul>
          </section>
        );
      })}
    </div>
  );
}
