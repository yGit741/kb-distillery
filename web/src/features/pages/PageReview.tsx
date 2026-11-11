import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { Check, X } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { useDataSource, type Decision, type Hunk, type Proposal, type RenderPage } from "@/api";
import { ErrorState, Loading } from "@/components/states";
import { Button } from "@/components/ui/button";
import { TouchedGraph, type TouchedPage } from "@/features/edit-preview/TouchedGraph";
import { applyBlocker, CHANGE_LABEL, changeKind, decisionOf, reviewOrder, short } from "@/features/proposals/model";
import { RebaseButton, type HunkCtx } from "@/features/proposals/parts";
import { ReadingDiff } from "@/features/proposals/ProposalDiff";
import { useApiQuery } from "@/lib/useApiQuery";
import { cn } from "@/lib/utils";
import { titleOf, type LinkGraph } from "./lib";
import { pageTo, usePageSearch } from "./parts";

const CLOSED: readonly Proposal["status"][] = ["applied", "rejected", "undone"];
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** Link `search` that opens a page in review of proposal `id` (or leaves review when `id` is undefined). */
const useReviewSearch = () => {
  const base = usePageSearch() as Record<string, string>;
  return (id?: string) => ({ ...base, ...(id ? { review: id } : {}) }) as never;
};

/**
 * One proposal reviewed inside the page it changes (`?review=<id>`, flag ui.page-review): the proposal, the page's
 * hunks in reading order, the decisions and Apply. `on` is false when no proposal is asked for.
 */
export function usePageReview(slug: string, id: string | undefined) {
  const ds = useDataSource();
  const qc = useQueryClient();
  const q = useApiQuery(["proposal", id], (d) => d.getProposal(id!), { enabled: !!id });
  const r = useApiQuery(["proposal-render", id], (d) => d.getProposalRender(id!), { enabled: !!id });
  const [focus, setFocus] = useState<string | null>(null);
  const [correcting, setCorrecting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fail = (e: unknown) => setError(e instanceof Error ? e.message : String(e));
  const decide = useMutation({
    mutationFn: (v: { hunk_id: string; decision: Decision; comment?: string }) => ds.decideProposal(id!, v),
    onSuccess: (p) => {
      qc.setQueryData(["proposal", id], p);
      setError(null);
    },
    onError: fail,
  });
  const apply = useMutation({
    mutationFn: () => ds.applyProposal(id!),
    onSuccess: () => {
      setError(null);
      void qc.invalidateQueries();
    },
    onError: fail,
  });
  const p = q.data;
  const pages: RenderPage[] = useMemo(() => r.data?.pages ?? [], [r.data]);
  const page = pages.find((pg) => pg.slug === slug);
  const hunks: Hunk[] = useMemo(() => reviewOrder((p?.hunks ?? []).filter((h) => h.slug === slug), page ? [page] : []), [p, slug, page]);
  const slugs = useMemo(() => (p ? [...new Set([...Object.keys(p.base), ...p.hunks.map((h) => h.slug)])] : []), [p]);
  const readOnly = !p || CLOSED.includes(p.status);
  const act = useCallback(
    (h: Hunk, d: Decision, comment?: string) => {
      if (readOnly || decide.isPending) return;
      if (d === "correct" && !comment) {
        setCorrecting(h.id);
        return;
      }
      setCorrecting(null);
      decide.mutate({ hunk_id: h.id, decision: d, ...(comment ? { comment } : {}) });
    },
    [readOnly, decide],
  );
  const ctx = (h: Hunk): HunkCtx => ({
    decision: p ? decisionOf(p, h.id) : undefined,
    comment: p?.decisions[h.id]?.comment,
    focused: focus === h.id,
    readOnly,
    correcting: correcting === h.id,
    onDecide: (d, c) => act(h, d, c),
    onCorrect: (open) => setCorrecting(open ? h.id : null),
    onFocus: () => setFocus(h.id),
  });
  /** Select an edit from the queue: the page scrolls to it and its note opens. */
  const pick = (h: Hunk) => {
    setFocus(h.id);
    document.querySelector(`[data-hunk="${h.id}"]`)?.scrollIntoView?.({ block: "center" });
  };
  return { on: !!id, id, p, page, hunks, slugs, readOnly, ctx, act, pick, focus, apply, error, loading: q.isLoading || r.isLoading, failed: q.error ?? r.error, retry: () => void Promise.all([q.refetch(), r.refetch()]) };
}
export type PageReviewState = ReturnType<typeof usePageReview>;

/** The thin line above a page in review: what is being reviewed, where this page sits in it, and the way out. */
export function ReviewLine({ rv, slug }: { rv: PageReviewState; slug: string }) {
  const search = useReviewSearch();
  const at = rv.slugs.indexOf(slug);
  return (
    <p role="status" data-testid="review-line" className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border bg-muted/50 px-3 py-1.5 text-xs text-muted-foreground">
      <span className="text-foreground/85">Reviewing: {rv.p?.title ?? "a proposal"}</span>
      {at >= 0 && rv.slugs.length > 1 && (
        <span>
          page {at + 1} of {rv.slugs.length}
        </span>
      )}
      <Link to={pageTo(slug)} search={search()} className="ml-auto text-primary hover:underline">
        Stop reviewing
      </Link>
    </p>
  );
}

/** The page body in review: the whole page, each edit in place with its bar; a click on a bar opens what changed. */
export function ReviewBody({ rv, slug }: { rv: PageReviewState; slug: string }) {
  if (rv.loading) return <Loading label="Loading the proposal" />;
  if (rv.failed || !rv.p) return <ErrorState title="Could not load this proposal" error={rv.failed} onRetry={rv.retry} />;
  if (!rv.hunks.length) return <p className="py-6 text-sm text-muted-foreground">This proposal changes nothing on this page.</p>;
  return <ReadingDiff page={rv.page} slug={slug} hunks={rv.hunks} ctx={rv.ctx} />;
}

/**
 * The side card of a page in review, in place of Neighbourhood: the pages the proposal touches (this one ringed, a
 * click moves the review there), the queue of edits on this page with a tick and a cross each, and Apply.
 */
export function ReviewCard({ rv, g, slug }: { rv: PageReviewState; g: LinkGraph; slug: string }) {
  const navigate = useNavigate();
  const search = useReviewSearch();
  const p = rv.p;
  const touched: TouchedPage[] = useMemo(
    () =>
      rv.slugs.map((s) => {
        const c = g.byId.get(s);
        return { slug: s, title: titleOf(g, s), type: c?.type ?? "idea", areas: c?.areas ?? [], isNew: !c };
      }),
    [rv.slugs, g],
  );
  if (!p) return null;
  const decided = (s: string) => p.hunks.filter((h) => h.slug === s).every((h) => decisionOf(p, h.id));
  const blocker = applyBlocker(p, [...p.checks.tier1, ...p.checks.tier2], p.hunks);
  const applied = p.status === "applied";
  const next = rv.slugs.find((s) => s !== slug && !decided(s));
  const mark = "grid size-6 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground disabled:pointer-events-none disabled:opacity-50";
  return (
    <section aria-label="Review" data-testid="review-card" className="flex flex-col gap-3 rounded-lg border bg-card p-3">
      {touched.length > 1 && (
        <div>
          <h2 className="mb-1 text-sm font-medium">This proposal changes</h2>
          <TouchedGraph pages={touched} shown={touched.length} current={slug} done={(t) => decided(t.slug)} onPick={(s) => void navigate({ to: pageTo(s), search: search(rv.id) })} />
        </div>
      )}
      <div>
        <h2 className="mb-1 text-sm font-medium">
          Edits on this page <span className="text-xs font-normal text-muted-foreground">{rv.hunks.length}</span>
        </h2>
        <ul className="flex flex-col">
          {rv.hunks.map((h) => {
            const d = decisionOf(p, h.id);
            const name = short(h, 5);
            return (
              <li key={h.id} data-queue={h.id} className={cn("flex items-center gap-1 border-b py-1 last:border-b-0", rv.focus === h.id && "bg-muted/60")}>
                <button type="button" onClick={() => rv.pick(h)} className="min-w-0 flex-1 truncate px-1 text-left text-sm hover:underline" title={name}>
                  <span className="text-muted-foreground">{cap(CHANGE_LABEL[changeKind(h)])} · </span>
                  {name}
                </button>
                <button type="button" aria-label={`Accept: ${name}`} aria-pressed={d === "accept"} disabled={rv.readOnly} onClick={() => rv.act(h, "accept")} className={cn(mark, d === "accept" && "bg-accent text-foreground")}>
                  <Check className="size-4" aria-hidden />
                </button>
                <button type="button" aria-label={`Reject: ${name}`} aria-pressed={d === "reject"} disabled={rv.readOnly} onClick={() => rv.act(h, "reject")} className={cn(mark, d === "reject" && "bg-accent text-foreground")}>
                  <X className="size-4" aria-hidden />
                </button>
              </li>
            );
          })}
        </ul>
      </div>
      {p.stale && !applied && (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span className="min-w-0 flex-1">The page changed since this proposal was made.</span>
          <RebaseButton id={p.id} />
        </div>
      )}
      {rv.error && <p role="alert" className="text-xs text-bad">{rv.error}</p>}
      {applied ? (
        <p role="status" className="text-sm text-muted-foreground">
          Applied.{" "}
          <Link to={pageTo(slug)} search={search()} className="text-primary hover:underline">
            Back to the page
          </Link>
        </p>
      ) : (
        <div className="flex flex-col gap-1.5">
          {next && (
            <Link to={pageTo(next)} search={search(rv.id)} className="text-sm text-primary hover:underline">
              Next page: {titleOf(g, next)}
            </Link>
          )}
          <Button size="sm" disabled={!!blocker || rv.apply.isPending || rv.readOnly} onClick={() => rv.apply.mutate()}>
            Apply {p.counts.accepted} accepted {p.counts.accepted === 1 ? "change" : "changes"}
          </Button>
          {blocker && <p className="text-xs text-muted-foreground">{blocker}</p>}
          {!blocker && rv.slugs.length > 1 && <p className="text-xs text-muted-foreground">Applies the accepted changes on all {rv.slugs.length} pages as one commit.</p>}
        </div>
      )}
    </section>
  );
}

/** Under the page header while reading: the open proposals that touch this page, each one click from its review. */
export function WaitingLine({ slug }: { slug: string }) {
  const search = useReviewSearch();
  const q = useApiQuery(["proposals", "open"], (d) => d.listProposals("open"));
  const mine = (q.data ?? []).filter((s) => s.pages.includes(slug));
  if (!mine.length) return null;
  return (
    <p data-testid="waiting-line" className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
      <span>
        {mine.length === 1 ? "1 proposal is" : `${mine.length} proposals are`} waiting on this page:
      </span>
      {mine.map((s) => (
        <Link key={s.id} to={pageTo(slug)} search={search(s.id)} className="text-primary hover:underline">
          {s.title}
        </Link>
      ))}
    </p>
  );
}
