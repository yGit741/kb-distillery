import { keepPreviousData } from "@tanstack/react-query";
import { useNavigate, useSearch } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { Empty, ErrorState, Loading } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useApiQuery } from "@/lib/useApiQuery";
import type { RelationsSearch } from "@/routes/search";
import { AppLink } from "@/features/scopes/AppLink";
import { FULL, PRESETS, groupBySubject, percent, rangeToSearch, readRange, sameRange, type Range } from "./logic";

const SHOW_FIRST = 150;

/** Ten bars of 10%, one per histogram bucket; the ones inside the chosen range are filled. */
function Histogram({ counts, range }: { counts: readonly number[]; range: Range }) {
  const top = Math.max(1, ...counts);
  return (
    <div className="flex h-16 items-end gap-1" role="img" aria-label={`Proposals per 10% of confidence: ${counts.join(", ")}`}>
      {counts.map((n, i) => {
        const lo = i * 10;
        const inside = lo <= range.max && (lo + 10 > range.min || lo === 90);   // the last bucket also holds 100%
        return (
          <div key={lo} className="flex h-full min-w-0 flex-1 flex-col items-center justify-end gap-0.5" title={`${lo}–${lo + 10}%: ${n}`}>
            <span className="text-[10px] text-muted-foreground">{n}</span>
            <div className={`w-full rounded-sm ${inside ? "bg-primary" : "bg-secondary"}`} style={{ height: `${Math.max(2, (n / top) * 100)}%` }} />
          </div>
        );
      })}
    </div>
  );
}

function Slider({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
  return (
    <label className="flex min-w-0 flex-1 flex-col gap-1 text-sm">
      <span className="flex justify-between">
        <span>{label}</span>
        <span className="tabular-nums text-muted-foreground">{value}%</span>
      </span>
      <input type="range" min={0} max={100} step={5} value={value} onChange={(e) => onChange(Number(e.target.value))} className="w-full accent-[var(--primary)]" />
    </label>
  );
}

export function RelationsScreen() {
  const search = useSearch({ strict: false }) as RelationsSearch;
  const navigate = useNavigate();
  const range = useMemo(() => readRange(search.min, search.max), [search.min, search.max]);
  const kind = search.kind || undefined;
  const [showAll, setShowAll] = useState(false);

  const go = (next: Partial<{ range: Range; kind: string | undefined }>) => {
    const r = next.range ?? range;
    const k = "kind" in next ? next.kind : kind;
    setShowAll(false);
    void navigate({ to: "." as string, search: { ...rangeToSearch(r), ...(k ? { kind: k } : {}) } as never, replace: true });
  };

  const q = useApiQuery(
    ["relation-proposals", range.min, range.max, kind ?? ""],
    (ds) => ds.getRelationProposals({ min: range.min / 100, max: range.max / 100, kind }),
    { placeholderData: keepPreviousData },
  );

  const groups = useMemo(() => groupBySubject(q.data?.rows ?? []), [q.data]);
  const rows = q.data?.rows.length ?? 0;
  const limited = !showAll && rows > SHOW_FIRST;
  let budget = limited ? SHOW_FIRST : Infinity;

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-4 px-4 py-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold">Relation proposals</h1>
        <p className="text-sm text-muted-foreground">
          What the model proposed, nothing is written to a page. Drag the range to look at the strong ones, the weak ones or any band in between.
        </p>
      </header>

      <section aria-label="Filter" className="flex flex-col gap-3 rounded-lg border p-3">
        {q.data ? <Histogram counts={q.data.histogram} range={range} /> : <div className="h-16" />}
        <div className="flex flex-col gap-3 sm:flex-row">
          <Slider label="From" value={range.min} onChange={(v) => go({ range: readRange(String(v), String(Math.max(v, range.max))) })} />
          <Slider label="To" value={range.max} onChange={(v) => go({ range: readRange(String(Math.min(v, range.min)), String(v)) })} />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {PRESETS.map((p) => (
            <Button key={p.label} size="sm" variant={sameRange(p.range, range) ? "default" : "outline"} onClick={() => go({ range: p.range })}>
              {p.label}
            </Button>
          ))}
          <label className="ml-auto flex items-center gap-2 text-sm">
            Kind
            <select value={kind ?? ""} onChange={(e) => go({ kind: e.target.value || undefined })} className="rounded-md border bg-background px-2 py-1">
              <option value="">all</option>
              {(q.data?.kinds ?? (kind ? [kind] : [])).map((k) => (
                <option key={k} value={k}>
                  {k}
                </option>
              ))}
            </select>
          </label>
        </div>
        {q.data && (
          <p className="text-sm text-muted-foreground" aria-live="polite">
            Showing {q.data.shown} of {q.data.total}
            {sameRange(range, FULL) ? "" : ` between ${range.min}% and ${range.max}%`}
            {kind ? ` · ${kind}` : ""}.
          </p>
        )}
      </section>

      {q.isError && !q.data ? (
        <ErrorState title="Could not load the proposals" error={q.error} onRetry={() => void q.refetch()} />
      ) : !q.data ? (
        <Loading label="Loading proposals" rows={4} />
      ) : groups.length === 0 ? (
        <Empty>No proposals in this range. Widen it, or pick another kind.</Empty>
      ) : (
        <div className="flex flex-col gap-3">
          {groups.map((g) => {
            if (budget <= 0) return null;
            const shown = g.rows.slice(0, budget);
            budget -= shown.length;
            return (
              <section key={g.slug} aria-label={g.title} className="rounded-lg border p-3">
                <h2 className="mb-2 font-medium">
                  <AppLink to={`/pages/${encodeURIComponent(g.slug)}`} className="hover:underline">
                    {g.title}
                  </AppLink>
                </h2>
                <ul className="flex flex-col gap-3">
                  {shown.map((r) => (
                    <li key={`${r.kind}|${r.to}`} className="flex flex-col gap-1 text-sm">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant="primary">{r.kind}</Badge>
                        <span aria-hidden>→</span>
                        <AppLink to={`/pages/${encodeURIComponent(r.to)}`} className="font-medium hover:underline">
                          {r.to_title}
                        </AppLink>
                        <Badge variant={r.status === "low-confidence" ? "warn" : "default"}>{percent(r.confidence)}</Badge>
                        {r.status === "low-confidence" && <span className="text-xs text-muted-foreground">below the 50% cut</span>}
                      </div>
                      {r.note && <p>{r.note}</p>}
                      {r.evidence && <p className="text-xs text-muted-foreground">“{r.evidence}”</p>}
                    </li>
                  ))}
                </ul>
              </section>
            );
          })}
          {limited && (
            <Button variant="outline" onClick={() => setShowAll(true)}>
              Show all {rows} (first {SHOW_FIRST} shown)
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
