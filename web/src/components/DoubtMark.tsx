import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useDataSource } from "@/api";
import type { MarkFixRequest } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { useApiQuery } from "@/lib/useApiQuery";
import { Markdown } from "./Markdown";

type Backend = NonNullable<MarkFixRequest["backend"]>;
const BACKENDS: { id: Backend; label: string }[] = [
  { id: "subscription", label: "Subscription" },
  { id: "api", label: "API" },
  { id: "batch", label: "Batch (slow)" },
];

const LEVEL_WORDS = {
  "!": "One reader decided this formula; it is probably right.",
  "!!": "The readers could not settle this formula.",
} as const;

export interface DoubtMarkProps {
  /** `<sha12>/p0188/3`, the part of the mark link after `mark:`. */
  ref_: string;
  level: "!" | "!!";
  /** The page the mark sits on (`wiki/<slug>.md`). */
  slug: string;
  /** A page that cannot be changed here (another kb, an embed): the dialog only shows. */
  readOnly?: boolean;
}

/** The small red `!` / `!!` after an unsure formula; a click opens the crop of the original with "Correct as is" and "Fix me". */
export function DoubtMark({ ref_, level, slug, readOnly }: DoubtMarkProps) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label={level === "!!" ? "Unsettled formula, open the original" : "Unsure formula, open the original"}
        title="Open the original"
        data-doubt={level}
        className="ml-0.5 cursor-pointer rounded-sm px-0.5 align-super text-[11px] font-semibold leading-none text-bad hover:bg-secondary focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring"
      >
        {level}
      </button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-xl p-0">
          {open && <DoubtPanel ref_={ref_} level={level} slug={slug} readOnly={readOnly} onDone={() => setOpen(false)} />}
        </DialogContent>
      </Dialog>
    </>
  );
}

function DoubtPanel({ ref_, level, slug, readOnly, onDone }: DoubtMarkProps & { onDone: () => void }) {
  const ds = useDataSource();
  const qc = useQueryClient();
  const q = useApiQuery(["marks", ref_], (d) => d.getMark(ref_), { retry: false });
  const [fixing, setFixing] = useState(false);
  const [instruction, setInstruction] = useState("");
  const [backend, setBackend] = useState<Backend>("subscription");
  const refresh = async () => {
    await Promise.all([
      qc.invalidateQueries({ queryKey: ["pages", "page", slug] }),
      qc.invalidateQueries({ queryKey: ["page", slug] }),
      qc.invalidateQueries({ queryKey: ["marks", ref_] }),
    ]);
    onDone();
  };
  const resolve = useMutation({ mutationFn: () => ds.resolveMark(ref_, slug), onSuccess: refresh });
  const fix = useMutation({ mutationFn: () => ds.fixMark(ref_, { slug, instruction, backend }) });
  const apply = useMutation({ mutationFn: (replacement: string) => ds.applyMark(ref_, slug, replacement), onSuccess: refresh });
  const m = q.data;
  const canWrite = !readOnly && !!m && !m.read_only && !m.resolution;
  const busy = resolve.isPending || fix.isPending || apply.isPending;
  const error = [resolve.error, fix.error, apply.error].find(Boolean);
  const proposal = fix.data?.replacement;

  return (
    <div className="flex max-h-[80vh] flex-col gap-3 overflow-y-auto p-4 text-sm">
      <DialogTitle className="text-base font-semibold">{level === "!!" ? "Unsettled formula" : "Unsure formula"}</DialogTitle>
      <DialogDescription className="text-muted-foreground">{LEVEL_WORDS[level]}</DialogDescription>
      {q.isLoading && <div className="h-24 animate-pulse rounded-md bg-muted" aria-label="Loading" />}
      {q.isError && <p className="text-bad">Could not load this mark: {q.error instanceof Error ? q.error.message : String(q.error)}</p>}
      {m && (
        <>
          <div className={proposal ? "grid gap-3 sm:grid-cols-2" : ""}>
            <figure className="m-0 flex flex-col gap-1">
              {m.crop_url ? (
                <img src={m.crop_url} alt="The original page around this formula" className="max-h-64 w-full rounded-md border bg-white object-contain" />
              ) : (
                <p className="rounded-md border border-dashed p-3 text-muted-foreground">No image of the original page is stored for this mark.</p>
              )}
              <figcaption className="text-xs text-muted-foreground">Original, page {Number(m.page.slice(1))}</figcaption>
            </figure>
            {proposal && (
              <div className="flex flex-col gap-1">
                <div className="rounded-md border p-3" data-testid="doubt-proposal">
                  <Markdown>{proposal}</Markdown>
                </div>
                <span className="text-xs text-muted-foreground">Proposed</span>
              </div>
            )}
          </div>
          {m.reason && <p><span className="text-muted-foreground">Why it is marked: </span>{m.reason}</p>}
          {m.was && (
            <div className="flex flex-wrap items-baseline gap-x-2">
              <span className="text-muted-foreground">Read before:</span>
              <Markdown className="inline-block">{m.was}</Markdown>
            </div>
          )}
          {m.resolution && (
            <p className="text-muted-foreground">
              Already decided: {m.resolution.action === "fixed" ? "fixed" : "correct as is"}.
            </p>
          )}
          {canWrite && fixing && !proposal && (
            <div className="flex flex-col gap-2">
              <label className="flex flex-col gap-1">
                <span className="text-muted-foreground">What is right?</span>
                <textarea
                  autoFocus
                  rows={3}
                  value={instruction}
                  onChange={(e) => setInstruction(e.target.value)}
                  placeholder="In your own words, for example: the exponent is n minus one"
                  className="rounded-md border bg-background p-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
                />
              </label>
              <label className="flex items-center gap-2 text-xs text-muted-foreground">
                Model billing
                <select
                  value={backend}
                  onChange={(e) => setBackend(e.target.value as Backend)}
                  className="h-7 rounded-md border bg-background px-1.5 text-xs text-foreground"
                >
                  {BACKENDS.map((b) => (
                    <option key={b.id} value={b.id}>{b.label}</option>
                  ))}
                </select>
              </label>
            </div>
          )}
          {error && <p className="text-bad" role="alert">{error instanceof Error ? error.message : String(error)}</p>}
          {canWrite && (
            <div className="flex flex-wrap justify-end gap-2">
              {proposal ? (
                <>
                  <Button variant="ghost" size="sm" disabled={busy} onClick={() => (fix.reset(), setFixing(false))}>Cancel</Button>
                  <Button variant="outline" size="sm" disabled={busy} onClick={() => fix.reset()}>Try again</Button>
                  <Button size="sm" disabled={busy} onClick={() => apply.mutate(proposal)}>{apply.isPending ? "Saving…" : "Approve"}</Button>
                </>
              ) : fixing ? (
                <>
                  <Button variant="ghost" size="sm" disabled={busy} onClick={() => setFixing(false)}>Cancel</Button>
                  <Button size="sm" disabled={busy || !instruction.trim()} onClick={() => fix.mutate()}>
                    {fix.isPending ? "Asking…" : "Propose a fix"}
                  </Button>
                </>
              ) : (
                <>
                  <Button variant="outline" size="sm" disabled={busy} onClick={() => setFixing(true)}>Fix me</Button>
                  <Button size="sm" disabled={busy} onClick={() => resolve.mutate()}>{resolve.isPending ? "Saving…" : "Correct as is"}</Button>
                </>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
