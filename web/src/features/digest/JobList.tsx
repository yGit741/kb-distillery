import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ChevronDown, ChevronRight, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useDataSource } from "@/api";
import type { DigestJob } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useApiQuery } from "@/lib/useApiQuery";
import { BACKEND_LABEL, isLive, JOB_LABEL, nameOf, progress, slugOf, SOURCE_LABEL, usd } from "./format";

const errorLine = (e: unknown) => (e instanceof Error ? e.message : String(e));

function Source({ s }: { s: DigestJob["sources"][number] }) {
  const bad = s.status === "failed";
  return (
    <li className="flex flex-wrap items-baseline gap-x-2 text-sm">
      <span className="min-w-0 break-all text-foreground">{nameOf(s.raw)}</span>
      <span className={`text-xs ${bad ? "text-bad" : "text-muted-foreground"}`}>
        {SOURCE_LABEL[s.status] ?? s.status}{s.note ? `: ${s.note}` : ""}
      </span>
      {s.page && (
        <Link to={`/pages/${encodeURIComponent(slugOf(s.page))}` as "/"} className="text-xs text-primary underline">
          {slugOf(s.page)}
        </Link>
      )}
    </li>
  );
}

function Job({ job, open, onToggle }: { job: DigestJob; open: boolean; onToggle: () => void }) {
  const ds = useDataSource();
  const qc = useQueryClient();
  const cancel = useMutation({
    mutationFn: () => ds.cancelDigestJob(job.id),
    onSettled: () => void qc.invalidateQueries({ queryKey: ["digest-jobs"] }),
  });
  const { done, total } = progress(job);
  const live = isLive(job);
  const failed = job.status === "failed";
  const current = job.current ? nameOf(job.current) : "";
  return (
    <li className="rounded-lg border bg-background p-3" data-testid="digest-job" data-status={job.status}>
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" aria-expanded={open} aria-label={open ? "Hide sources" : "Show sources"} onClick={onToggle} className="text-muted-foreground hover:text-foreground">
          {open ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
        </button>
        <span className="text-sm font-medium">{JOB_LABEL[job.status] ?? job.status}</span>
        <Badge variant={failed ? "bad" : "outline"}>{BACKEND_LABEL[job.backend] ?? job.backend}</Badge>
        <span className="text-xs tabular-nums text-muted-foreground">{done} of {total}</span>
        {job.spent_usd > 0 && <span className="text-xs text-muted-foreground">{usd(job.spent_usd)} spent</span>}
        {live && (
          <Button size="sm" variant="secondary" className="ml-auto" disabled={cancel.isPending} onClick={() => cancel.mutate()}>
            <X className="size-3.5" />{cancel.isPending ? "Cancelling…" : "Cancel"}
          </Button>
        )}
      </div>
      <div
        role="progressbar"
        aria-label="Sources finished"
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={done}
        className="mt-2 h-1 overflow-hidden rounded-full bg-secondary"
      >
        <div className="h-full bg-primary transition-[width]" style={{ width: total ? `${(done / total) * 100}%` : "0%" }} />
      </div>
      {live && current && <p className="mt-1.5 text-xs text-muted-foreground">Now: {current}</p>}
      {job.status === "queued" && job.backend === "batch" && <p className="mt-1.5 text-xs text-muted-foreground">Batch results can take hours.</p>}
      {job.error && <p role="alert" className="mt-1.5 text-sm text-bad">{job.error}</p>}
      {cancel.isError && <p role="alert" className="mt-1.5 text-sm text-bad">{errorLine(cancel.error)}</p>}
      {open && (
        <ul className="mt-2 flex flex-col gap-1 border-t pt-2" aria-label="Job sources">
          {job.sources.map((s) => <Source key={s.raw} s={s} />)}
        </ul>
      )}
    </li>
  );
}

/** Newest first. Polls while a job is live; when one stops, the graph and pipeline refetch so the new pages show. */
export function JobList({ focus }: { focus?: string }) {
  const qc = useQueryClient();
  const q = useApiQuery(["digest-jobs"], (ds) => ds.listDigestJobs(), {
    refetchInterval: (query) => (query.state.data?.jobs.some(isLive) ? 2000 : false),
  });
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const jobs = q.data?.jobs ?? [];
  const live = jobs.filter(isLive).length;
  const prev = useRef(live);
  useEffect(() => {
    if (live < prev.current) {
      void qc.invalidateQueries({ queryKey: ["graph"] });
      void qc.invalidateQueries({ queryKey: ["pipeline"] });
    }
    prev.current = live;
  }, [live, qc]);
  if (q.isPending) return <p className="text-sm text-muted-foreground" role="status">Loading jobs…</p>;
  if (q.isError) {
    return (
      <p role="alert" className="text-sm text-bad">
        {errorLine(q.error)} <button type="button" className="underline" onClick={() => void q.refetch()}>Try again</button>
      </p>
    );
  }
  if (!jobs.length) return <p className="text-sm text-muted-foreground">No digest jobs yet.</p>;
  return (
    <ul className="flex flex-col gap-2" aria-label="Digest jobs">
      {jobs.map((j) => (
        <Job key={j.id} job={j} open={open[j.id] ?? (j.id === focus || isLive(j))} onToggle={() => setOpen((o) => ({ ...o, [j.id]: !(o[j.id] ?? (j.id === focus || isLive(j))) }))} />
      ))}
    </ul>
  );
}
