import { Clock, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { Hunk, PageVersion } from "@/api";
import { ErrorState, Loading } from "@/components/states";
import { Button } from "@/components/ui/button";
import { useVariant, VARIANTS } from "@/components/variants";
import { useApiQuery } from "@/lib/useApiQuery";
import { cn } from "@/lib/utils";
import { DEFAULT_DIFF_VIEW, DIFF_COMPONENT, DIFF_VIEWS, type DiffView } from "@/features/proposals/ProposalDiff";
import type { HunkCtx } from "@/features/proposals/parts";

export const WORKING = "working";
export const dayOf = (iso: string) => iso.slice(0, 10);

/** Versions of a page and which ones the owner picked (at most two); `comparing` shows the compare view. */
export function useHistory(slug: string, enabled: boolean) {
  const q = useApiQuery(["page-history", slug], (d) => d.getPageHistory(slug), { enabled, retry: false, staleTime: 60_000 });
  const versions = useMemo(() => q.data?.versions ?? [], [q.data]);
  const [picked, setPicked] = useState<string[]>([]);
  const [comparing, setComparing] = useState(false);
  const [panel, setPanel] = useState(false);
  useEffect(() => {
    setPicked([]);
    setComparing(false);
    setPanel(false);
  }, [slug]);
  const toggle = (sha: string) => setPicked((p) => (p.includes(sha) ? p.filter((x) => x !== sha) : p.length >= 2 ? [p[1]!, sha] : [...p, sha]));
  // versions are newest first: the larger index is the older one, which is the `from` side
  const [from, to] = useMemo(() => {
    const idx = (s: string) => versions.findIndex((v) => v.sha === s);
    const sorted = [...picked].sort((a, b) => idx(b) - idx(a));
    return sorted.length === 2 ? [sorted[0]!, sorted[1]!] : sorted.length === 1 ? [sorted[0]!, WORKING] : [null, null];
  }, [picked, versions]);
  return { q, versions, picked, toggle, comparing, setComparing, panel, setPanel, from, to, clear: () => setPicked([]) };
}
export type History = ReturnType<typeof useHistory>;

export function KindBadge({ kind }: { kind: string }) {
  return <span className="shrink-0 rounded-full border px-1.5 py-px text-[11px] leading-4 text-muted-foreground">{kind}</span>;
}

function useEscape(open: boolean, close: () => void) {
  useEffect(() => {
    if (!open) return;
    const key = (e: KeyboardEvent) => e.key === "Escape" && close();
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [open, close]);
}

/** What a pick means, in one sentence: "2026-11-01 against now" or "2026-10-20 against 2026-11-01". */
export function pickLine(h: History): string {
  const day = (sha: string | null) => (sha === WORKING ? "now" : dayOf(h.versions.find((v) => v.sha === sha)?.date ?? ""));
  if (!h.from || !h.to) return "Pick a version, or two to compare them.";
  return `${day(h.from)} against ${day(h.to)}`;
}

function CompareButton({ h }: { h: History }) {
  return (
    <Button size="sm" disabled={!h.from} onClick={() => { h.setComparing(true); h.setPanel(false); }}>
      Compare
    </Button>
  );
}

/** Variant "header": the clock line-icon for the page header. */
export function HistoryClock({ h }: { h: History }) {
  return (
    <Button variant="outline" size="sm" aria-expanded={h.panel} aria-controls="page-history-panel" onClick={() => h.setPanel(!h.panel)} title="How this page changed">
      <Clock aria-hidden /> History
    </Button>
  );
}

/** Variant "header": the right panel with the versions, newest first. */
export function HistoryPanel({ h }: { h: History }) {
  useEscape(h.panel, () => h.setPanel(false));
  if (!h.panel) return null;
  return (
    <aside id="page-history-panel" aria-label="Page history" className="fixed bottom-0 right-0 top-14 z-30 flex w-96 max-w-[90vw] flex-col border-l bg-card shadow-sm">
      <div className="flex items-center justify-between border-b px-3 py-2">
        <h2 className="text-sm font-medium">History</h2>
        <button type="button" onClick={() => h.setPanel(false)} aria-label="Close history" className="rounded p-1 text-muted-foreground hover:bg-accent">
          <X className="size-4" />
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {h.q.isLoading && <Loading label="Loading versions" />}
        {h.q.error && <ErrorState title="Could not load the history" error={h.q.error} onRetry={() => void h.q.refetch()} />}
        {h.q.data && !h.versions.length && <p className="p-3 text-sm text-muted-foreground">This page has no saved versions yet.</p>}
        <ul className="divide-y">
          {h.versions.map((v) => (
            <VersionRow key={v.sha} v={v} on={h.picked.includes(v.sha)} onToggle={() => h.toggle(v.sha)} />
          ))}
        </ul>
      </div>
      <div className="flex items-center justify-between gap-2 border-t px-3 py-2">
        <p className="min-w-0 truncate text-xs text-muted-foreground">{pickLine(h)}</p>
        <CompareButton h={h} />
      </div>
    </aside>
  );
}

function VersionRow({ v, on, onToggle }: { v: PageVersion; on: boolean; onToggle: () => void }) {
  return (
    <li>
      <button type="button" role="checkbox" aria-checked={on} onClick={onToggle} className={cn("flex w-full flex-col gap-0.5 px-3 py-2 text-left hover:bg-accent/50", on && "bg-accent/60")}>
        <span className="flex items-center gap-2 text-xs text-muted-foreground">
          <span className={cn("size-2 rounded-full border", on ? "border-primary bg-primary" : "border-muted-foreground/50")} aria-hidden />
          <time dateTime={v.date}>{dayOf(v.date)}</time>
          <KindBadge kind={v.kind} />
          <span className="font-mono">{v.short}</span>
        </span>
        <span className="line-clamp-2 pl-4 text-sm">{v.subject}</span>
      </button>
    </li>
  );
}

/** Variant "timeline": a thin strip of dots under the title, oldest left, one per version. */
export function HistoryTimeline({ h }: { h: History }) {
  const [hover, setHover] = useState<PageVersion | null>(null);
  if (h.q.isLoading || h.q.error || !h.versions.length) return null;
  const shown = hover ?? (h.picked.length === 1 ? h.versions.find((v) => v.sha === h.picked[0]) : null);
  const ordered = [...h.versions].reverse();
  return (
    <nav aria-label="Page history timeline" className="flex flex-col gap-1">
      <div className="flex items-center gap-3">
        <ol className="flex min-w-0 flex-1 items-center border-b border-border/0">
          {ordered.map((v) => {
            const on = h.picked.includes(v.sha);
            return (
              <li key={v.sha} className="flex h-6 min-w-1.5 max-w-6 flex-1 items-center justify-center">
                <button
                  type="button"
                  aria-pressed={on}
                  aria-label={`${dayOf(v.date)} ${v.kind}: ${v.subject}`}
                  onClick={() => h.toggle(v.sha)}
                  onMouseEnter={() => setHover(v)}
                  onMouseLeave={() => setHover(null)}
                  onFocus={() => setHover(v)}
                  onBlur={() => setHover(null)}
                  className="group flex size-6 items-center justify-center"
                >
                  <span className={cn("block size-2 rounded-full transition-transform group-hover:scale-150", on ? "bg-primary" : "bg-muted-foreground/40")} />
                </button>
              </li>
            );
          })}
          <li aria-hidden className="ml-1 h-px w-6 shrink-0 bg-border" />
          <li className="ml-1 shrink-0 text-xs text-muted-foreground">now</li>
        </ol>
        <CompareButton h={h} />
      </div>
      <p className="min-h-4 truncate text-xs text-muted-foreground" aria-live="polite">
        {shown ? (
          <>
            <time dateTime={shown.date}>{dayOf(shown.date)}</time> · {shown.kind} · {shown.subject}
          </>
        ) : h.picked.length ? (
          pickLine(h)
        ) : (
          `${h.versions.length} ${h.versions.length === 1 ? "version" : "versions"}; pick one, or two to compare`
        )}
      </p>
    </nav>
  );
}

/** The compare view: the proposal diff components over the hunks of two versions, read-only. */
export function HistoryCompare({ slug, h }: { slug: string; h: History }) {
  const { from, to } = h;
  const [view, setView] = useVariant("proposal-diff", DIFF_VIEWS, DEFAULT_DIFF_VIEW);
  const q = useApiQuery(["page-compare", slug, from, to], (d) => d.comparePage(slug, from!, to!), { enabled: !!from && !!to, retry: false });
  const fromV = h.versions.find((v) => v.sha === from);
  const toV = h.versions.find((v) => v.sha === to);
  const hunks: Hunk[] = q.data?.hunks ?? [];
  const Diff = DIFF_COMPONENT[view as DiffView];
  // history only shows: a version is compared, never restored from here (edits start from the page's review mode)
  const ctx = (): HunkCtx => ({ focused: false, readOnly: true, correcting: false, onDecide: () => {}, onCorrect: () => {}, onFocus: () => {} });
  return (
    <section aria-label="Compare versions" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b pb-3">
        <div className="min-w-0">
          <p className="text-xs text-muted-foreground">Comparing</p>
          <p className="text-sm font-medium">
            {fromV ? dayOf(fromV.date) : "?"} <span className="text-muted-foreground">to</span> {to === WORKING ? "now" : toV ? dayOf(toV.date) : "?"}
          </p>
          {fromV && <p className="truncate text-xs text-muted-foreground">{fromV.subject}</p>}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div role="radiogroup" aria-label="Diff view" className="inline-flex items-center rounded-md border p-0.5">
            {(VARIANTS["proposal-diff"]?.options ?? []).map((o) => (
              <button
                key={o.id}
                type="button"
                role="radio"
                aria-checked={view === o.id}
                title={o.hint}
                onClick={() => setView(o.id)}
                className={cn("h-6 rounded px-2 text-xs text-muted-foreground hover:text-foreground", view === o.id && "bg-muted font-medium text-foreground")}
              >
                {o.label.toLowerCase()}
              </button>
            ))}
          </div>
          <Button variant="ghost" size="sm" onClick={() => h.setComparing(false)}>Back to page</Button>
        </div>
      </div>
      {q.isLoading && <Loading label="Comparing" />}
      {q.error && <ErrorState title="Could not compare these versions" error={q.error} onRetry={() => void q.refetch()} />}
      {q.data && !hunks.length && <p className="py-6 text-center text-sm text-muted-foreground">These two versions read the same.</p>}
      {q.data && hunks.length > 0 && <Diff page={q.data.page} slug={slug} hunks={hunks} ctx={ctx} />}
    </section>
  );
}

export const HISTORY_VARIANT = "page-history-entry";
export function useHistoryEntry() {
  const spec = VARIANTS[HISTORY_VARIANT]!;
  return useVariant(HISTORY_VARIANT, spec.options.map((o) => o.id), spec.default)[0];
}
