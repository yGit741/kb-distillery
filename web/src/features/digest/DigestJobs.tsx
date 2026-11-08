import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { useApiQuery } from "@/lib/useApiQuery";
import { parseSnapshot } from "@/features/pipeline/items";
import { DigestSheet } from "./DigestSheet";
import { JobList } from "./JobList";
import { nameOf } from "./format";

/** Sources that can be digested now: filed or still in the inbox, no note yet. One entry per unit. */
function useCandidates() {
  const q = useApiQuery(["pipeline"], (ds) => ds.getPipeline());
  const items = useMemo(() => {
    if (!q.data) return [];
    return parseSnapshot(q.data).units
      .filter((u) => u.status === "undigested" || u.status === "inbox")
      .map((u) => u.primary.path);
  }, [q.data]);
  return { items, loading: q.isPending, error: q.isError };
}

/** Digest jobs (flag screen.digest-jobs): choose sources, preview the cost per backend, start, watch, cancel, open the pages. */
export function DigestJobs() {
  const { items, loading, error } = useCandidates();
  const [picked, setPicked] = useState<string[]>([]);
  const [sheet, setSheet] = useState<string[] | null>(null);
  const [focus, setFocus] = useState<string>();
  const chosen = picked.filter((p) => items.includes(p));
  const toggle = (p: string) => setPicked((cur) => (cur.includes(p) ? cur.filter((x) => x !== p) : [...cur, p]));
  return (
    <section aria-label="Digest jobs" className="flex flex-col gap-3 rounded-lg border bg-card p-3" data-testid="digest-jobs">
      <header>
        <h2 className="text-sm font-semibold">Digest jobs</h2>
        <p className="text-xs text-muted-foreground">Pick sources, see the cost on each backend, then start. You can cancel while it runs.</p>
      </header>
      {loading ? (
        <p className="text-sm text-muted-foreground" role="status">Loading sources…</p>
      ) : error ? (
        <p role="alert" className="text-sm text-bad">Could not read the sources.</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted-foreground">Nothing is waiting to be digested. Add sources above.</p>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" variant="secondary" onClick={() => setPicked(chosen.length === items.length ? [] : items)}>
              {chosen.length === items.length ? "Clear" : "Select all"}
            </Button>
            <Button size="sm" disabled={!chosen.length} onClick={() => setSheet(chosen)}>
              Preview digest{chosen.length ? ` (${chosen.length})` : ""}
            </Button>
          </div>
          <ul aria-label="Sources to digest" className="max-h-56 overflow-y-auto">
            {items.map((p) => (
              <li key={p}>
                <label className="flex cursor-pointer items-center gap-2 rounded px-1 py-1 text-sm hover:bg-accent">
                  <input type="checkbox" checked={chosen.includes(p)} onChange={() => toggle(p)} />
                  <span className="min-w-0 break-all">{nameOf(p)}</span>
                  <span className="hidden min-w-0 truncate text-xs text-muted-foreground sm:inline">{p.split("/").slice(0, -1).join("/")}</span>
                </label>
              </li>
            ))}
          </ul>
        </>
      )}
      <JobList {...(focus ? { focus } : {})} />
      <DigestSheet
        raws={sheet}
        onClose={() => setSheet(null)}
        onStarted={(id) => {
          setFocus(id);
          setPicked([]);
        }}
      />
    </section>
  );
}
