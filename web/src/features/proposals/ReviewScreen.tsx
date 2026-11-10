import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { Info } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useDataSource, type Decision, type Finding, type Hunk, type Proposal } from "@/api";
import { ErrorState, Loading } from "@/components/states";
import { Button } from "@/components/ui/button";
import { useVariant, VARIANTS } from "@/components/variants";
import { cn } from "@/lib/utils";
import { useApiQuery } from "@/lib/useApiQuery";
import { pageTo } from "@/features/pages/parts";
import { applyBlocker, classLabel, decisionOf, placement, readable, reviewOrder, structureLine } from "./model";
import { DEFAULT_DIFF_VIEW, DIFF_COMPONENT, DIFF_VIEWS, type DiffView } from "./ProposalDiff";
import { HunkControls, RebaseButton, Segmented, Tabs, type HunkCtx } from "./parts";

const COMPONENT = "proposal-diff";

/** The review of one proposal: header, Structure strip, the diff in the chosen view, a keyboard hint. */
export function ReviewScreen({ id }: { id: string }) {
  const ds = useDataSource();
  const qc = useQueryClient();
  const q = useApiQuery(["proposal", id], (d) => d.getProposal(id));
  const r = useApiQuery(["proposal-render", id], (d) => d.getProposalRender(id));
  const [view, setView] = useVariant(COMPONENT, DIFF_VIEWS, DEFAULT_DIFF_VIEW);
  const [revIndex, setRevIndex] = useState<number | null>(null);
  const [focus, setFocus] = useState<string | null>(null);
  const [correcting, setCorrecting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pageTab, setPageTab] = useState("");

  const put = (p: Proposal) => qc.setQueryData(["proposal", id], p);
  const decide = useMutation({
    mutationFn: (v: { hunk_id: string; decision: Decision; comment?: string }) => ds.decideProposal(id, v),
    onSuccess: (p) => {
      put(p);
      setError(null);
    },
    onError: (e) => setError(e instanceof Error ? e.message : String(e)),
  });
  const apply = useMutation({
    mutationFn: () => ds.applyProposal(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["proposal", id] });
      void qc.invalidateQueries();
    },
    onError: (e) => setError(e instanceof Error ? e.message : String(e)),
  });
  const rejectAll = useMutation({
    mutationFn: () => ds.rejectProposal(id),
    onSuccess: (p) => {
      put(p);
      void qc.invalidateQueries({ queryKey: ["proposals"] });
    },
    onError: (e) => setError(e instanceof Error ? e.message : String(e)),
  });

  const p = q.data;
  const pages = useMemo(() => r.data?.pages ?? [], [r.data]);
  const current = p ? p.current : 0;
  const shownRev = p ? (revIndex ?? current) : 0;
  const isCurrent = shownRev === current;
  const hunks: Hunk[] = useMemo(() => (p ? (isCurrent ? p.hunks : p.revisions[shownRev]?.hunks ?? []) : []), [p, isCurrent, shownRev]);
  const findings: Finding[] = useMemo(
    () => (p ? (isCurrent ? [...p.checks.tier1, ...p.checks.tier2] : p.revisions[shownRev]?.checks ?? []) : []),
    [p, isCurrent, shownRev],
  );
  const renderPages = isCurrent ? pages : [];
  const shown = useMemo(() => (pageTab ? hunks.filter((h) => h.slug === pageTab) : hunks), [hunks, pageTab]);
  const order = useMemo(() => reviewOrder(shown, renderPages), [shown, renderPages]);
  const readOnly = !p || !isCurrent || p.status === "applied" || p.status === "rejected" || p.status === "undone";

  const act = useCallback(
    (h: Hunk, d: Decision, comment?: string) => {
      if (readOnly || decide.isPending) return;
      if (d === "correct" && placement(h, renderPages.find((pg) => pg.slug === h.slug)) === "structure") return;
      if (d === "correct" && !comment) {
        setCorrecting(h.id);
        return;
      }
      setCorrecting(null);
      decide.mutate({ hunk_id: h.id, decision: d, ...(comment ? { comment } : {}) });
    },
    [readOnly, decide, renderPages],
  );

  // j / k walk the hunks, a / r / c act on the focused one; never while typing or with a modifier held
  const orderRef = useRef(order);
  orderRef.current = order;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable)) return;
      const list = orderRef.current;
      if (!list.length) return;
      const i = list.findIndex((h) => h.id === focus);
      const move = (n: number) => {
        const next = list[Math.max(0, Math.min(list.length - 1, n))];
        if (!next) return;
        setFocus(next.id);
        document.querySelector(`[data-hunk="${next.id}"]`)?.scrollIntoView?.({ block: "nearest" });
      };
      if (e.key === "j") move(i < 0 ? 0 : i + 1);
      else if (e.key === "k") move(i < 0 ? 0 : i - 1);
      else if (i >= 0 && !e.repeat && (e.key === "a" || e.key === "r" || e.key === "c")) {
        e.preventDefault();
        act(list[i]!, e.key === "a" ? "accept" : e.key === "r" ? "reject" : "correct");
      } else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [focus, act]);

  if (q.isLoading) return <Shell><Loading label="Loading the proposal" /></Shell>;
  if (q.error || !p) return <Shell><ErrorState title="Could not load this proposal" error={q.error} onRetry={() => void q.refetch()} /></Shell>;

  const ctx = (h: Hunk): HunkCtx => ({
    decision: isCurrent ? decisionOf(p, h.id) : undefined,
    comment: isCurrent ? p.decisions[h.id]?.comment : undefined,
    focused: focus === h.id,
    readOnly,
    correcting: correcting === h.id,
    onDecide: (d, c) => act(h, d, c),
    onCorrect: (open) => setCorrecting(open ? h.id : null),
    onFocus: () => setFocus(h.id),
  });
  const pageOf = (h: Hunk) => renderPages.find((pg) => pg.slug === h.slug);
  const strip = shown.filter((h) => placement(h, pageOf(h)) === "structure");
  const slugs = [...new Set([...Object.keys(p.base), ...hunks.map((h) => h.slug)])];
  const visible = pageTab && slugs.includes(pageTab) ? [pageTab] : slugs;
  const dropped = isCurrent ? p.revisions[current]?.dropped ?? [] : [];
  const blocker = applyBlocker(p, [...p.checks.tier1, ...p.checks.tier2], p.hunks);
  const accepted = p.counts.accepted;
  const Diff = DIFF_COMPONENT[view as DiffView];

  return (
    <Shell>
      <Header
        p={p}
        slugs={slugs}
        findings={findings}
        shownRev={shownRev}
        onRev={(n) => {
          setRevIndex(n === current ? null : n);
          setFocus(null);
        }}
        view={view as DiffView}
        onView={setView}
        accepted={accepted}
        blocker={blocker}
        busy={apply.isPending || rejectAll.isPending}
        onApply={() => apply.mutate()}
        onRejectAll={() => rejectAll.mutate()}
      />
      <div className="flex flex-col gap-2 empty:hidden">
        {p.stale && (
          <div role="status" className="flex items-center gap-3 rounded-lg border bg-muted/50 px-3 py-2 text-sm text-foreground/85" data-testid="stale-banner">
            <Info className="size-4 shrink-0 text-muted-foreground" aria-hidden />
            <span className="min-w-0 flex-1">
              The page changed since this proposal was made{p.stale_pages.length ? ` (${p.stale_pages.join(", ")})` : ""}. Apply is off until you rebase: the changes are carried onto the current text, and any whose text is gone are set aside.
            </span>
            <RebaseButton id={id} />
          </div>
        )}
        {dropped.length > 0 && (
          <details className="rounded-lg border bg-card px-3 py-2 text-sm" data-testid="dropped-list" open>
            <summary className="cursor-pointer text-foreground/85">
              {dropped.length} {dropped.length === 1 ? "change" : "changes"} could not be carried over after the rebase
            </summary>
            <ul className="mt-2 flex flex-col gap-2">
              {dropped.map((d) => (
                <li key={d.hunk_id} className="text-xs text-muted-foreground">
                  <span className="font-medium text-foreground/80">{d.slug}</span> · {classLabel(d.klass)} · {d.reason}
                  <span className="mt-0.5 block truncate" title={d.after || d.before}>{readable((d.after || d.before).trim())}</span>
                </li>
              ))}
            </ul>
          </details>
        )}
        {!isCurrent && (
          <p className="text-sm text-muted-foreground">You are looking at v{p.revisions[shownRev]?.n}. Decisions apply to the current revision, v{p.revision}.</p>
        )}
        {apply.isSuccess && <p role="status" className="text-sm text-muted-foreground">Applied as {apply.data.kb_version ?? "a new knowledge step"}.</p>}
        {error && <p role="alert" className="text-sm text-bad">{error}</p>}
      </div>

      {slugs.length > 1 && (
        <Tabs
          label="Pages in this proposal"
          value={pageTab && slugs.includes(pageTab) ? pageTab : ""}
          onChange={setPageTab}
          items={[
            { id: "", label: "All pages", note: String(hunks.length) },
            ...slugs.map((s) => ({ id: s, label: s, note: String(hunks.filter((h) => h.slug === s).length), mark: p.stale_pages.includes(s) })),
          ]}
        />
      )}

      {strip.length > 0 && (
        <section aria-label="Structure changes" className="rounded-lg border bg-card">
          <h2 className="border-b px-3 py-2 text-xs font-medium text-muted-foreground">Structure · {strip.length} {strip.length === 1 ? "change" : "changes"}</h2>
          <ul className="divide-y">
            {strip.map((h) => {
              const line = structureLine(h);
              const c = ctx(h);
              return (
                <li
                  key={h.id}
                  data-hunk={h.id}
                  data-focused={c.focused || undefined}
                  onClick={c.onFocus}
                  className={cn("flex min-h-11 items-center gap-3 px-3 py-1.5 text-sm", c.focused && "bg-accent/40", c.decision === "reject" && "opacity-60")}
                >
                  <span className="w-28 shrink-0 font-medium">{line.what}</span>
                  <span className="min-w-0 flex-1 truncate font-mono text-xs text-muted-foreground" title={line.detail}>{line.detail}</span>
                  {visible.length > 1 && <span className="shrink-0 text-xs text-muted-foreground">{h.slug}</span>}
                  <HunkControls ctx={{ ...c, correcting: false }} layout="row" correct={false} />
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {visible.map((slug) => {
        const mine = shown.filter((h) => h.slug === slug && placement(h, pageOf(h)) === "flow");
        if (!mine.length) return null;
        return (
          <article key={slug} aria-label={`Changes to ${slug}`} className="flex flex-col gap-3">
            {visible.length > 1 && <h2 className="text-sm font-medium text-muted-foreground">{slug}</h2>}
            <Diff page={pageOf(mine[0]!)} slug={slug} hunks={mine} ctx={ctx} />
          </article>
        );
      })}
      {!shown.length && <p className="py-6 text-center text-sm text-muted-foreground">This revision changes nothing.</p>}

      <footer className="sticky bottom-0 -mx-4 mt-auto border-t bg-background/95 px-4 py-2 text-xs text-muted-foreground backdrop-blur">
        <kbd className="font-sans font-medium text-foreground/80">j</kbd> / <kbd className="font-sans font-medium text-foreground/80">k</kbd> next / previous change ·{" "}
        <kbd className="font-sans font-medium text-foreground/80">a</kbd> accept · <kbd className="font-sans font-medium text-foreground/80">r</kbd> reject ·{" "}
        <kbd className="font-sans font-medium text-foreground/80">c</kbd> correct
      </footer>
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return <div className="mx-auto flex min-h-full w-full max-w-5xl flex-col gap-4 px-4 pt-6">{children}</div>;
}

interface HeaderProps {
  p: Proposal;
  slugs: string[];
  findings: Finding[];
  shownRev: number;
  onRev: (n: number) => void;
  view: DiffView;
  onView: (v: string) => void;
  accepted: number;
  blocker: string | null;
  busy: boolean;
  onApply: () => void;
  onRejectAll: () => void;
}

function Header({ p, slugs, findings, shownRev, onRev, view, onView, accepted, blocker, busy, onApply, onRejectAll }: HeaderProps) {
  const closed = p.status === "applied" || p.status === "rejected" || p.status === "undone";
  const producer = [p.producer.kind, p.producer.instruction].filter(Boolean).join(" · ");
  return (
    <header className="flex flex-col gap-3 border-b pb-4">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-xs text-muted-foreground">
            <Link to={"/proposals" as "/"} className="hover:text-foreground">Proposals</Link>
            {closed && <span> · {p.status}</span>}
          </p>
          <h1 className="text-xl font-semibold leading-tight">{p.title}</h1>
          {producer && <p className="mt-1 truncate text-sm text-muted-foreground" title={producer}>{producer}</p>}
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" disabled={closed || busy} onClick={onRejectAll}>
              Reject all
            </Button>
            <Button size="sm" disabled={!!blocker || busy} onClick={onApply} aria-describedby="apply-reason">
              Apply accepted ({accepted})
            </Button>
          </div>
          <p id="apply-reason" className="min-h-4 max-w-96 text-right text-xs leading-4 text-muted-foreground" data-testid="apply-reason">
            {blocker && !closed ? blocker : ""}
          </p>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <div className="flex flex-wrap items-center gap-1.5" aria-label="Pages touched">
          {slugs.map((s) => (
            <Link key={s} to={pageTo(s)} className="rounded-full border px-2 py-0.5 text-xs text-foreground/85 hover:bg-accent">
              {s}
            </Link>
          ))}
        </div>
        {p.revisions.length > 1 && (
          <Segmented label="Revision" value={String(shownRev)} options={p.revisions.map((r, i) => ({ id: String(i), label: `v${r.n}`, hint: r.note || undefined }))} onChange={(v) => onRev(Number(v))} />
        )}
        <Checks findings={findings} />
        <div className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
          View
          <Segmented label="View" value={view} options={(VARIANTS["proposal-diff"]?.options ?? []).map((o) => ({ id: o.id, label: o.label.toLowerCase(), hint: o.hint }))} onChange={onView} />
        </div>
      </div>
    </header>
  );
}

function Checks({ findings }: { findings: Finding[] }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);
  const errors = findings.filter((f) => f.severity === "error").length;
  const warnings = findings.filter((f) => f.severity === "warning").length;
  const label = !findings.length ? "Checks pass" : [errors && `${errors} ${errors === 1 ? "error" : "errors"}`, warnings && `${warnings} ${warnings === 1 ? "warning" : "warnings"}`].filter(Boolean).join(" · ") || `${findings.length} notes`;
  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-expanded={open}
        disabled={!findings.length}
        onClick={() => setOpen(!open)}
        className="flex h-6 items-center gap-1.5 rounded-md px-1.5 text-xs text-muted-foreground hover:bg-accent disabled:hover:bg-transparent"
      >
        <span className={cn("size-1.5 rounded-full", errors ? "bg-bad" : warnings ? "bg-warn" : "bg-ok")} aria-hidden />
        {label}
      </button>
      {open && (
        <ul role="dialog" aria-label="Check findings" className="absolute left-0 top-7 z-20 w-96 max-w-[80vw] rounded-lg border bg-popover p-2 text-sm text-popover-foreground shadow-md">
          {findings.map((f, i) => (
            <li key={i} className="flex gap-2 rounded px-1.5 py-1">
              <span className={cn("mt-0.5 w-14 shrink-0 text-xs font-medium", f.severity === "error" ? "text-bad" : f.severity === "warning" ? "text-warn" : "text-muted-foreground")}>{f.severity}</span>
              <span className="min-w-0 break-words">
                {f.message}
                <span className="block text-xs text-muted-foreground">{f.slug} · {f.code}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
