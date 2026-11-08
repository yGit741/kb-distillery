import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useDataSource } from "@/api";
import type { DigestBackendOption, DigestPreview } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { BACKEND_HINT, BACKEND_LABEL, nameOf, tokens, usd } from "./format";

const errorLine = (e: unknown) => (e instanceof Error ? e.message : String(e));

function cost(o: Pick<DigestBackendOption, "billed_usd" | "cost_usd" | "cost_worst_usd">, backend: string): string {
  if (backend === "subscription") return "Included in your subscription";
  const worst = o.cost_worst_usd > o.cost_usd ? `, at most ${usd(o.cost_worst_usd)}` : "";
  return `${usd(o.billed_usd)}${worst}`;
}

function Option({ o, picked, onPick }: { o: DigestBackendOption; picked: boolean; onPick: () => void }) {
  const id = `digest-backend-${o.backend}`;
  return (
    <label
      htmlFor={id}
      className={`flex cursor-pointer items-start gap-3 rounded-lg border px-3 py-2.5 text-sm transition-colors ${picked ? "border-primary bg-accent-soft" : "hover:bg-accent"} ${o.available ? "" : "cursor-not-allowed opacity-60"}`}
    >
      <input id={id} type="radio" name="digest-backend" className="mt-1" checked={picked} disabled={!o.available} onChange={onPick} />
      <span className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="flex flex-wrap items-baseline justify-between gap-x-3">
          <span className="font-medium text-foreground">{BACKEND_LABEL[o.backend] ?? o.backend}</span>
          <span className="text-xs text-muted-foreground">{o.available ? o.eta : "Not available"}</span>
        </span>
        <span className="text-xs text-muted-foreground">{o.available ? cost(o, o.backend) : o.why}</span>
        {o.available && <span className="text-xs text-muted-foreground">{BACKEND_HINT[o.backend]}</span>}
      </span>
    </label>
  );
}

function Body({ preview, backend, onPick }: { preview: DigestPreview; backend: string; onPick: (b: string) => void }) {
  return (
    <div className="flex flex-col gap-4">
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-4">
        <div><dt className="text-xs text-muted-foreground">Sources</dt><dd className="tabular-nums">{preview.sources}</dd></div>
        <div><dt className="text-xs text-muted-foreground">Depth</dt><dd>{preview.depth}</dd></div>
        <div><dt className="text-xs text-muted-foreground">Model</dt><dd className="break-all">{preview.model}</dd></div>
        <div><dt className="text-xs text-muted-foreground">Tokens</dt><dd className="tabular-nums">{tokens(preview.tokens_in)} in, {tokens(preview.tokens_out)} out</dd></div>
      </dl>
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 text-sm font-medium">Run on</legend>
        {preview.options.map((o) => (
          <Option key={o.backend} o={o} picked={backend === o.backend} onPick={() => onPick(o.backend)} />
        ))}
        {preview.backend_why && <p className="text-xs text-muted-foreground">Suggested: {BACKEND_LABEL[preview.backend] ?? preview.backend}. {preview.backend_why}</p>}
      </fieldset>
      {preview.skipped.length > 0 && (
        <div className="text-sm" data-testid="digest-skipped">
          <p className="text-muted-foreground">Left out of this run:</p>
          <ul className="mt-1 flex flex-col gap-0.5">
            {preview.skipped.map((s) => (
              <li key={s.raw}><span className="break-all text-foreground">{nameOf(s.raw)}</span> <span className="text-xs text-muted-foreground">{s.reason}</span></li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/** The sheet between "pick sources" and "start": what it would cost on each backend, which one to run on, then Start. */
export function DigestSheet({ raws, onClose, onStarted }: { raws: string[] | null; onClose: () => void; onStarted: (id: string) => void }) {
  const ds = useDataSource();
  const qc = useQueryClient();
  const open = !!raws;
  const q = useQuery({
    queryKey: ["digest-preview", raws],
    queryFn: () => ds.previewDigest(raws ?? []),
    enabled: open,
    retry: false,
    staleTime: 0,
    gcTime: 0,
  });
  const [picked, setPicked] = useState<string>();
  useEffect(() => setPicked(undefined), [raws]);
  const backend = picked ?? q.data?.backend ?? "";
  const start = useMutation({
    mutationFn: () => ds.startDigestJob(raws ?? [], backend || undefined),
    onSuccess: (job) => {
      void qc.invalidateQueries({ queryKey: ["digest-jobs"] });
      onStarted(job.id);
      onClose();
    },
  });
  useEffect(() => start.reset(), [raws]); // eslint-disable-line react-hooks/exhaustive-deps
  const chosen = q.data?.options.find((o) => o.backend === backend);
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      {open && (
        <DialogContent className="top-8 max-h-[calc(100dvh-4rem)] max-w-xl overflow-y-auto p-5" aria-describedby="digest-sheet-desc">
          <DialogTitle className="text-base font-semibold">Digest {raws.length} {raws.length === 1 ? "source" : "sources"}</DialogTitle>
          <DialogDescription id="digest-sheet-desc" className="mb-4 mt-1 text-sm text-muted-foreground">
            Each source is read in full and written up as a wiki page. Nothing runs until you start.
          </DialogDescription>
          {q.isPending && <p className="text-sm text-muted-foreground" role="status">Estimating…</p>}
          {q.isError && <p role="alert" className="text-sm text-bad" data-testid="digest-refusal">{errorLine(q.error)}</p>}
          {q.data && <Body preview={q.data} backend={backend} onPick={setPicked} />}
          {start.isError && <p role="alert" className="mt-3 text-sm text-bad" data-testid="digest-refusal">{errorLine(start.error)}</p>}
          <div className="mt-5 flex justify-end gap-2">
            <Button variant="secondary" size="sm" onClick={onClose}>Close</Button>
            <Button size="sm" disabled={!q.data || !chosen?.available || start.isPending} onClick={() => start.mutate()}>
              {start.isPending ? "Starting…" : `Start on ${BACKEND_LABEL[backend] ?? "backend"}`}
            </Button>
          </div>
        </DialogContent>
      )}
    </Dialog>
  );
}
