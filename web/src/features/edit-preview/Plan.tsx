import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { X } from "lucide-react";
import { useMemo, useState } from "react";
import { useDataSource, type Hunk, type Proposal } from "@/api";
import { ErrorState, Loading } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { BACKENDS, useIngestJob } from "@/features/ingest/model";
import { applyBlocker, changeKind, decisionOf } from "@/features/proposals/model";
import { useApiQuery } from "@/lib/useApiQuery";
import { useEditPreview } from "./store";
import { TouchedGraph, type TouchedPage } from "./TouchedGraph";

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
const CLOSED: readonly Proposal["status"][] = ["applied", "rejected", "undone"];

export interface PlanPage extends TouchedPage {
  hunks: Hunk[];
  open: number;
}

/** What a proposal plans to do, page by page: which pages are new, which are updated, and how many links it adds. */
export function planOf(p: Proposal, exists: (slug: string) => boolean, card: (slug: string) => { title: string; type: string; areas: string[] } | undefined) {
  const slugs = [...new Set([...Object.keys(p.base), ...p.hunks.map((h) => h.slug)])];
  const pages: PlanPage[] = slugs.map((slug) => {
    const c = card(slug);
    const hunks = p.hunks.filter((h) => h.slug === slug);
    return { slug, title: c?.title ?? slug, type: c?.type ?? "idea", areas: c?.areas ?? [], isNew: !exists(slug), hunks, open: hunks.filter((h) => !decisionOf(p, h.id)).length };
  });
  const isNew = new Set(pages.filter((pg) => pg.isNew).map((pg) => pg.slug));
  /** Safe to accept without reading: a new page, a link, or text that only adds. A rewrite or a removal needs a look. */
  const safe = (h: Hunk) => isNew.has(h.slug) || h.klass === "links" || changeKind(h) === "insert";
  const undecided = p.hunks.filter((h) => !decisionOf(p, h.id));
  return {
    pages,
    newPages: isNew.size,
    updated: pages.length - isNew.size,
    links: p.hunks.reduce((n, h) => n + h.links_added.length, 0),
    safe: undecided.filter(safe),
    look: undecided.filter((h) => !safe(h)),
  };
}

/**
 * The plan of one proposal as a graph: the pages it creates (dashed) and updates around the source, a line of counts,
 * one button for everything that is safe to accept, and Apply. A page opens in the Page Explorer's review mode.
 */
export function ProposalPlan({ id, onLeave }: { id: string; onLeave: () => void }) {
  const ds = useDataSource();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const q = useApiQuery(["proposal", id], (d) => d.getProposal(id));
  const r = useApiQuery(["proposal-render", id], (d) => d.getProposalRender(id));
  const index = useApiQuery(["pages", "index", ""], (d) => d.listPages(), { staleTime: 60_000 });
  const p = q.data;
  // "new" and "safe" need the render and the page list: until both are here nothing is counted or offered
  const ready = !!r.data && !!index.data;
  const plan = useMemo(() => {
    if (!p || !ready) return null;
    const rendered = new Map((r.data?.pages ?? []).map((pg) => [pg.slug, pg.exists]));
    const cards = new Map((index.data?.pages ?? []).map((c) => [c.id, c]));
    return planOf(p, (s) => rendered.get(s) ?? cards.has(s), (s) => cards.get(s));
  }, [p, ready, r.data, index.data]);
  const acceptSafe = useMutation({
    mutationFn: async (hunks: Hunk[]) => {
      let last: Proposal | undefined;
      for (const h of hunks) last = await ds.decideProposal(id, { hunk_id: h.id, decision: "accept" });
      return last;
    },
    onSuccess: (last) => last && qc.setQueryData(["proposal", id], last),
    onSettled: () => void qc.invalidateQueries({ queryKey: ["proposal", id] }),
  });
  const apply = useMutation({ mutationFn: () => ds.applyProposal(id), onSuccess: () => void qc.invalidateQueries() });
  const error = q.error ?? r.error ?? index.error;
  if (error) return <ErrorState title="Could not load this proposal" error={error} onRetry={() => void Promise.all([q.refetch(), r.refetch(), index.refetch()])} />;
  if (!p || !plan) return <Loading label="Loading the plan" />;
  const openPage = (slug: string) => {
    onLeave();
    void navigate({ to: `/pages/${encodeURIComponent(slug)}` as "/", search: { review: id } as never });
  };
  const closed = CLOSED.includes(p.status);
  const blocker = applyBlocker(p, [...p.checks.tier1, ...p.checks.tier2], p.hunks);
  const failed = acceptSafe.error ?? apply.error;
  return (
    <div className="mx-auto flex h-full min-h-0 w-full max-w-3xl flex-col gap-3" data-testid="proposal-plan">
      <p className="text-sm text-muted-foreground" data-testid="plan-line">
        {[plural(plan.newPages, "new page"), `${plural(plan.updated, "page")} updated`, plural(plan.links, "new link")].join(" · ")}
      </p>
      <div className="flex min-h-48 flex-1 flex-col">
        <TouchedGraph wide pages={plan.pages} shown={plan.pages.length} current={null} done={(pg) => pg.open === 0} onPick={openPage} />
      </div>
      <ul aria-label="Pages in this plan" className="max-h-44 overflow-auto border-t">
        {plan.pages.map((pg) => (
          <li key={pg.slug} className="flex items-baseline gap-3 border-b py-1.5 text-sm last:border-b-0">
            <button type="button" className="min-w-0 truncate text-left text-primary hover:underline" onClick={() => openPage(pg.slug)}>
              {pg.title}
            </button>
            <span className="text-xs text-muted-foreground">{pg.isNew ? "new page" : plural(pg.hunks.length, "change")}</span>
            <span className="ml-auto whitespace-nowrap text-xs text-muted-foreground">{pg.open ? `${pg.open} open` : "decided"}</span>
          </li>
        ))}
      </ul>
      {failed && <p role="alert" className="text-sm text-bad">{failed instanceof Error ? failed.message : String(failed)}</p>}
      {p.status === "applied" ? (
        <p role="status" className="text-sm text-muted-foreground">Applied. The pages are updated.</p>
      ) : closed ? (
        <p role="status" className="text-sm text-muted-foreground">This proposal was {p.status}. Nothing here can be applied.</p>
      ) : (
        <div className="flex flex-wrap items-center gap-3">
          {plan.safe.length > 0 && (
            <Button variant="outline" size="sm" disabled={acceptSafe.isPending} onClick={() => acceptSafe.mutate(plan.safe)}>
              Accept the {plan.safe.length} safe {plan.safe.length === 1 ? "change" : "changes"}
            </Button>
          )}
          <span className="min-w-0 flex-1 text-xs text-muted-foreground">
            {plan.look.length > 0 ? `${plural(plan.look.length, "change")} rewrite or remove text: open the page to decide.` : blocker ?? "Everything is decided."}
          </span>
          <Button size="sm" disabled={!!blocker || apply.isPending} onClick={() => apply.mutate()}>
            Apply {p.counts.accepted} accepted {p.counts.accepted === 1 ? "change" : "changes"}
          </Button>
        </div>
      )}
    </div>
  );
}

/**
 * The one question before a dropped source is read: which backend runs the model. A single source is always read
 * deep. Nothing is sent until "Read this source"; closing the pop-up drops the file and costs nothing.
 */
function GoAhead({ file }: { file: File }) {
  const ds = useDataSource();
  const showPlan = useEditPreview((s) => s.showPlan);
  const [backend, setBackend] = useState<string>("");
  // a read-only knowledge base (the example one) refuses every write: say so here, before offering to read anything
  const kb = useApiQuery(["kb"], (d) => d.getKb(), { staleTime: Infinity, retry: false });
  const start = useMutation({
    mutationFn: () => ds.startIngest({ file, tier: "deep", backend: backend || undefined }),
    // only if this file's go-ahead is still on screen: a closed pop-up stays closed
    onSuccess: (started) => useEditPreview.getState().plan?.file === file && showPlan({ name: file.name, jobId: started.job_id }),
  });
  if (kb.data?.read_only)
    return (
      <div className="mx-auto flex max-w-md flex-col gap-2 pt-10" data-testid="plan-go-ahead">
        <p className="text-sm font-medium">{file.name}</p>
        <p role="status" className="text-sm text-muted-foreground">
          {kb.data.name} is a read-only knowledge base, so a source cannot be added to it. Open your own knowledge base and drop the file there.
        </p>
      </div>
    );
  return (
    <div className="mx-auto flex max-w-md flex-col gap-4 pt-10" data-testid="plan-go-ahead">
      <div>
        <p className="text-sm font-medium">{file.name}</p>
        <p className="text-sm text-muted-foreground">It will be read in full, and what it would create, update and link comes back as a plan. Nothing changes until you apply it.</p>
      </div>
      <fieldset className="flex flex-col gap-1.5" disabled={start.isPending}>
        <legend className="mb-1.5 text-sm font-medium">Run the model on</legend>
        <div className="inline-flex w-fit rounded-md border p-0.5" role="radiogroup" aria-label="Run the model on">
          {BACKENDS.map((b) => (
            <label key={b.id || "default"} className="cursor-pointer rounded-[5px] px-3 py-1 text-sm text-muted-foreground has-[:checked]:bg-accent-soft has-[:checked]:text-foreground">
              <input type="radio" name="plan-backend" className="sr-only" checked={backend === b.id} onChange={() => setBackend(b.id)} />
              {b.label}
            </label>
          ))}
        </div>
        <p className="text-xs text-muted-foreground">Default is the server's setting. Batch is half price and slower.</p>
      </fieldset>
      {start.error && <p role="alert" className="text-sm text-foreground/85">{start.error instanceof Error ? start.error.message : "Could not start reading this file."}</p>}
      <Button className="self-start" disabled={start.isPending} onClick={() => start.mutate()}>
        {start.isPending ? "Starting" : "Read this source"}
      </Button>
    </div>
  );
}

const upper = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/**
 * The pop-up over the graph for a real source or proposal (flags ui.edit-preview + ui.ingest): while a dropped file is
 * read it shows the job's step, then the plan of the proposal the job made. Opened by a drop, by `?preview=<proposal
 * id>`, and from the ingest list.
 */
export function PlanSheet() {
  const plan = useEditPreview((s) => s.plan);
  return plan ? <PlanDialog plan={plan} /> : null;
}

function PlanDialog({ plan }: { plan: NonNullable<ReturnType<typeof useEditPreview.getState>["plan"]> }) {
  const close = useEditPreview((s) => s.closePlan);
  const job = useIngestJob(plan.jobId ?? null);
  const proposalId = plan.proposalId ?? job?.proposal_id ?? null;
  const cached = useApiQuery(["proposal", proposalId], (d) => d.getProposal(proposalId!), { enabled: !!proposalId });
  const title = cached.data?.title ?? plan.name ?? "Reading the source";
  const step = job?.steps.find((s) => s.name === job.step);
  return (
    <Dialog open onOpenChange={(o) => !o && close()}>
      <DialogContent data-testid="plan-sheet" className="left-[7.5vw] top-[7.5vh] grid h-[85vh] w-[85vw] max-w-none translate-x-0 grid-rows-[3rem_1fr] rounded-2xl bg-card text-card-foreground">
        <header className="flex items-center gap-3 border-b px-4">
          <DialogTitle className="truncate text-sm font-semibold">{title}</DialogTitle>
          <DialogDescription className="text-xs text-muted-foreground">The plan: what this would create, update and link</DialogDescription>
          <button type="button" aria-label="Close" onClick={close} className="ml-auto grid size-7 place-items-center rounded-lg hover:bg-accent">
            <X className="size-4" />
          </button>
        </header>
        <div className="min-h-0 overflow-auto p-6">
          {plan.error ? (
            <p role="alert" className="pt-10 text-center text-sm text-foreground/85">{plan.error}</p>
          ) : plan.file && !plan.jobId ? (
            <GoAhead file={plan.file} />
          ) : proposalId ? (
            <ProposalPlan id={proposalId} onLeave={close} />
          ) : job && job.status !== "running" ? (
            <p role="alert" className="pt-10 text-center text-sm text-foreground/85">
              {job.error ? upper(job.error) : "The source was read, but it produced no proposal."}
            </p>
          ) : (
            <p role="status" className="pt-10 text-center text-sm text-muted-foreground">
              Reading the source{job?.step ? `: ${job.step}` : ""}
              {step?.detail ? ` · ${step.detail}` : ""}
            </p>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
