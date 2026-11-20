import { CheckCircle2, CircleAlert, Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { RebaseButton } from "@/features/proposals/parts";
import type { ApplyOutcome } from "./api";
import { plural, type PlanRow } from "./model";

export type ApplyPhase = { phase: "plan" } | { phase: "running" } | { phase: "done"; outcome: ApplyOutcome } | { phase: "failed"; error: string };

const OUTCOME: Record<PlanRow["outcome"], string> = { apply: "writes", reject: "rejected as a whole", wait: "waits" };

function Plan({ rows }: { rows: PlanRow[] }) {
  const writes = rows.filter((r) => r.outcome === "apply");
  const accepted = writes.reduce((n, r) => n + r.accepted, 0);
  return (
    <div className="flex flex-col gap-3 text-sm">
      <p>
        {writes.length ? (
          <>
            Writes <b>{plural(accepted, "accepted change")}</b> in {plural(writes.length, "step")}, then copies the pages to your KB folder and runs its
            checks.
          </>
        ) : (
          "Nothing is written: no proposal is fully decided with an accepted change."
        )}
      </p>
      <ul className="flex max-h-72 flex-col divide-y overflow-y-auto rounded-md border">
        {rows.map((r) => (
          <li key={r.proposal.id} className="flex items-baseline gap-2 px-3 py-2">
            <span className="min-w-0 flex-1 truncate">{r.proposal.title}</span>
            <span className="shrink-0 text-xs text-muted-foreground">
              {r.accepted} ✓ · {r.rejected} ✕{r.undecided ? ` · ${r.undecided} left` : ""}
            </span>
            <Badge variant={r.outcome === "apply" ? "ok" : r.outcome === "wait" ? "warn" : "outline"} className="shrink-0">
              {OUTCOME[r.outcome]}
            </Badge>
          </li>
        ))}
      </ul>
      {rows.some((r) => r.outcome === "wait") && (
        <p className="text-xs text-muted-foreground">A proposal with cards left for later waits until every card is decided; its decisions are kept.</p>
      )}
    </div>
  );
}

function Result({ outcome }: { outcome: ApplyOutcome }) {
  const pages = [...new Set(outcome.applied.flatMap((a) => a.pages))];
  return (
    <div className="flex flex-col gap-3 text-sm">
      {outcome.applied.length > 0 && (
        <p className="flex items-start gap-2">
          <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-ok" aria-hidden />
          <span>Applied {plural(outcome.applied.length, "step")} on {plural(pages.length, "page")}: {pages.join(", ")}.</span>
        </p>
      )}
      {outcome.rejected.length > 0 && <p className="text-muted-foreground">Rejected {plural(outcome.rejected.length, "proposal")}.</p>}
      {outcome.waiting.length > 0 && <p className="text-muted-foreground">{plural(outcome.waiting.length, "proposal")} still {outcome.waiting.length === 1 ? "has" : "have"} cards left for later.</p>}
      {outcome.failed.map((f) => (
        <div key={f.id} className="flex items-start gap-2 text-bad">
          <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
          <span className="flex-1">{f.message}</span>
          {f.stale && <RebaseButton id={f.id} />}
        </div>
      ))}

    </div>
  );
}

export function ApplyDialog({ open, onOpenChange, rows, state, onConfirm }: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  rows: PlanRow[];
  state: ApplyPhase;
  onConfirm: () => void;
}) {
  const writes = rows.some((r) => r.outcome !== "wait");
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl p-5" data-tour="review-apply-dialog">
        <DialogTitle className="text-base font-semibold">{state.phase === "done" ? "Applied" : "Apply your decisions"}</DialogTitle>
        <DialogDescription className="sr-only">What Apply writes, and the result.</DialogDescription>
        <div className="mt-3">
          {state.phase === "plan" && <Plan rows={rows} />}
          {state.phase === "running" && (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" aria-hidden /> Applying, writing back and checking…
            </p>
          )}
          {state.phase === "done" && <Result outcome={state.outcome} />}
          {state.phase === "failed" && <p role="alert" className="text-sm text-bad">{state.error}</p>}
        </div>
        <div className="mt-4 flex justify-end gap-2">
          {state.phase === "plan" ? (
            <>
              <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
              <Button onClick={onConfirm} disabled={!writes} autoFocus>Apply</Button>
            </>
          ) : (
            <Button onClick={() => onOpenChange(false)} disabled={state.phase === "running"}>Done</Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
