import { CircleAlert, FileText, Link2, Loader2 } from "lucide-react";
import { useState } from "react";
import type { IngestListItem } from "@/api";
import { cn } from "@/lib/utils";
import { plural } from "./model";
import { SourceDrop } from "./Sources";

export interface QueueRow {
  id: string;
  name: string;
  kind: string;
  group: "running" | "waiting" | "done";
  line: string;
  failed: boolean;
  proposalId: string | null;
  cards: number;
}

const middle = (s: string, n = 34) => (s.length <= n ? s : `${s.slice(0, Math.ceil(n / 2) - 1)}…${s.slice(-Math.floor(n / 2))}`);
export const sourceName = (source: string) => {
  const s = source.replace(/[?#].*$/, "").replace(/\/+$/, "");
  return s.split("/").pop() || source;
};

/** Ingest jobs as queue rows: running (or failed) first, then waiting for review, then done; newest first in each. */
export function queueRows(jobs: IngestListItem[], cardsByProposal: ReadonlyMap<string, number>): QueueRow[] {
  const rows = jobs.map((j): QueueRow => {
    const cards = (j.proposal_id && cardsByProposal.get(j.proposal_id)) || 0;
    const name = sourceName(j.source);
    if (j.status === "running") {
      const steps = j.steps ?? [];
      const at = steps.findIndex((s) => s.state === "active" || s.state === "running");
      const n = at >= 0 ? at + 1 : steps.filter((s) => s.state === "done").length + 1;
      return { id: j.id, name, kind: j.kind, group: "running", line: `Reading… step ${Math.min(n, steps.length || 1)} of ${steps.length || 1}`, failed: false, proposalId: null, cards: 0 };
    }
    if (j.status === "failed" || j.status === "interrupted")
      return { id: j.id, name, kind: j.kind, group: "running", line: `Failed: ${j.error || "the read stopped"}`, failed: true, proposalId: null, cards: 0 };
    const st = j.proposal_status;
    if (j.proposal_id && (st === "open" || st === "stale") && cards > 0)
      return { id: j.id, name, kind: j.kind, group: "waiting", line: "Ready to review", failed: false, proposalId: j.proposal_id, cards };
    const line = st === "applied" ? "Applied" : st === "rejected" ? "Rejected" : st === "undone" ? "Undone" : j.proposal_id ? "Reviewed" : "Filed under raw/, nothing to review";
    return { id: j.id, name, kind: j.kind, group: "done", line, failed: false, proposalId: j.proposal_id ?? null, cards };
  });
  const rank = { running: 0, waiting: 1, done: 2 };
  return rows.map((r, i) => [r, i] as const).sort((a, b) => rank[a[0].group] - rank[b[0].group] || a[1] - b[1]).map(([r]) => r);
}

const GROUPS: { key: QueueRow["group"]; title: string }[] = [
  { key: "running", title: "Running" },
  { key: "waiting", title: "Waiting for you" },
  { key: "done", title: "Done" },
];

/**
 * The right panel: everything ingested, as a queue. Drop a source at the top; a row that has cards in the deck
 * filters the deck to them; the row owning the card on screen is marked.
 */
export function Queue({ rows, loading, current, filter, onFilter, readOnly, sample, dropped, onStarted }: {
  rows: QueueRow[];
  loading: boolean;
  /** the proposal of the card on screen */
  current: string | null;
  /** the proposal the deck is filtered to */
  filter: string | null;
  onFilter: (row: QueueRow) => void;
  readOnly: boolean;
  sample: boolean;
  dropped: File | null;
  onStarted: (jobId: string) => void;
}) {
  const [allDone, setAllDone] = useState(false);
  return (
    <section className="flex flex-col gap-3" aria-label="Queue" data-tour="review-queue">
      <h2 className="text-sm font-semibold">Queue</h2>
      <SourceDrop disabled={readOnly} sample={sample} dropped={dropped} onStarted={onStarted} />
      {!rows.length ? (
        <p className="text-xs text-muted-foreground">{loading ? "Loading…" : "Nothing ingested yet. Drop a file or paste a link to start."}</p>
      ) : (
        GROUPS.map(({ key, title }) => {
          const mine = rows.filter((r) => r.group === key);
          if (!mine.length) return null;
          const shown = key === "done" && !allDone ? mine.slice(0, 5) : mine;
          return (
            <div key={key} className="flex flex-col gap-1">
              <h3 className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{title} · {mine.length}</h3>
              <ul className="flex flex-col gap-0.5" aria-live={key === "running" ? "polite" : undefined}>
                {shown.map((r) => {
                  const clickable = r.cards > 0 && !!r.proposalId;
                  const Icon = r.kind === "url" ? Link2 : FileText;
                  const body = (
                    <>
                      <span className="flex items-center gap-1.5">
                        <Icon className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
                        <span className="min-w-0 flex-1 truncate" title={r.name}>{middle(r.name)}</span>
                        {r.cards > 0 && <span className="shrink-0 rounded-full bg-muted px-1.5 text-[10px] tabular-nums text-muted-foreground">{plural(r.cards, "card")}</span>}
                      </span>
                      <span className={cn("flex items-center gap-1 pl-5 text-[11px]", r.failed ? "text-bad" : "text-muted-foreground")}>
                        {r.group === "running" && !r.failed && <Loader2 className="size-3 animate-spin" aria-hidden />}
                        {r.failed && <CircleAlert className="size-3" aria-hidden />}
                        <span className="truncate" title={r.line}>{r.line}</span>
                      </span>
                    </>
                  );
                  const cls = cn(
                    "flex min-h-[52px] w-full flex-col justify-center gap-0.5 rounded-md border-l-2 border-transparent px-2 py-1.5 text-left text-xs",
                    r.proposalId && r.proposalId === current && "border-primary",
                    r.proposalId && r.proposalId === filter && "bg-accent",
                  );
                  return (
                    <li key={r.id}>
                      {clickable ? (
                        <button type="button" className={cn(cls, "hover:bg-accent")} onClick={() => onFilter(r)} aria-pressed={r.proposalId === filter} title={`Show only the cards from ${r.name}`}>
                          {body}
                        </button>
                      ) : (
                        <div className={cls}>{body}</div>
                      )}
                    </li>
                  );
                })}
              </ul>
              {key === "done" && mine.length > 5 && (
                <button type="button" className="self-start text-[11px] text-muted-foreground underline-offset-2 hover:underline" onClick={() => setAllDone((x) => !x)}>
                  {allDone ? "Show fewer" : `Show all ${mine.length}`}
                </button>
              )}
            </div>
          );
        })
      )}
    </section>
  );
}
