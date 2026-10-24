import { Link } from "@tanstack/react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useDataSource } from "@/api";
import type { DigestResult } from "@/api/types";
import { CopyButton } from "@/components/CopyButton";
import { Markdown } from "@/components/Markdown";
import { Empty, ErrorState, Loading } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { useApiQuery } from "@/lib/useApiQuery";
import { StatusPill } from "./parts";
import { canDigest, fmtAge, fmtSize, previewKind, rawFileUrl, resolveRawUrl, rawThumbUrl, STATUS_LABEL, type PipelineItem, type Unit } from "./items";

const MAX_TEXT = 40_000;

/** Text excerpt from GET /api/raw/{path}: rendered Markdown for .md, source otherwise. */
function TextPreview({ item }: { item: PipelineItem }) {
  const [mode, setMode] = useState<"rendered" | "source">("rendered");
  const q = useApiQuery(["raw-preview", item.path], (ds) => ds.getRawPreview(item.path));
  if (q.isPending) return <Loading label="Loading preview" rows={2} />;
  if (q.isError) return <ErrorState title="Could not load the preview" error={q.error} onRetry={() => void q.refetch()} />;
  const { text, error, exists } = q.data;
  if (error || !exists) return <Empty>{error || "The file is not on disk in this checkout."}</Empty>;
  if (!text.trim()) return <Empty>The file is empty.</Empty>;
  const clipped = text.length > MAX_TEXT;
  const body = clipped ? text.slice(0, MAX_TEXT) : text;
  const canRender = item.ext === ".md";
  return (
    <div className="flex flex-col gap-2">
      {canRender && (
        <div className="flex gap-1" role="group" aria-label="Preview mode">
          {(["rendered", "source"] as const).map((m) => (
            <Button key={m} size="sm" variant={mode === m ? "default" : "secondary"} aria-pressed={mode === m} onClick={() => setMode(m)}>
              {m}
            </Button>
          ))}
        </div>
      )}
      {canRender && mode === "rendered" ? (
        <Markdown className="max-w-none" transformUrl={(u) => resolveRawUrl(u, item.path.split("/").slice(0, -1).join("/"))}>{body}</Markdown>
      ) : (
        <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap break-words rounded-md bg-secondary p-3 text-xs">{body}</pre>
      )}
      {clipped && <p className="text-xs text-muted-foreground">Excerpt only; open the file for the rest.</p>}
    </div>
  );
}

function FilePreview({ item }: { item: PipelineItem }) {
  const kind = previewKind(item.ext);
  const [broken, setBroken] = useState(false);
  if (kind === "text") return <TextPreview item={item} />;
  if (kind === "none")
    return <Empty>No preview for {item.ext || "this file"}. Use Open file.</Empty>;
  if (broken) return <Empty>No thumbnail available for this file.</Empty>;
  return (
    <a href={rawFileUrl(item.path)} target="_blank" rel="noopener noreferrer" title="Open the full file in a new tab">
      <img
        src={kind === "pdf" ? rawThumbUrl(item.path) : rawFileUrl(item.path)}
        alt={kind === "pdf" ? `First page of ${item.name}` : item.name}
        className="mx-auto max-h-[60vh] max-w-full rounded-md border bg-white object-contain"
        loading="lazy"
        onError={() => setBroken(true)}
      />
    </a>
  );
}

function DigestAction({ unit }: { unit: Unit }) {
  const ds = useDataSource();
  const qc = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const run = useMutation<DigestResult, Error, string>({
    mutationFn: (path) => ds.digestRaw(path),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["pipeline"] }),
  });
  const path = unit.primary.path;
  if (run.isSuccess) {
    const r = run.data;
    return (
      <div className="flex flex-col gap-2" role="status">
        <p className="text-sm">
          <Badge variant={r.exit === 0 ? "ok" : "bad"}>exit {r.exit}</Badge>{" "}
          <code className="break-all text-xs">{r.command}</code>
        </p>
        {r.stdout && <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-md bg-secondary p-2 text-xs">{r.stdout}</pre>}
        {r.stderr && <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-md bg-secondary p-2 text-xs text-bad">{r.stderr}</pre>}
      </div>
    );
  }
  if (!confirming)
    return (
      <Button variant="default" size="sm" className="self-start" onClick={() => setConfirming(true)}>
        Easy digest…
      </Button>
    );
  return (
    <div className="flex flex-col gap-2 rounded-md border p-3" role="group" aria-label="Confirm digest">
      <p className="text-sm">
        Run an easy digest (a light abstract skim, about 2-4k tokens) on <code className="break-all">{path}</code>? It runs on the server and writes a wiki note.
      </p>
      {run.isError && <ErrorState title="The digest failed" error={run.error} />}
      <div className="flex gap-2">
        <Button size="sm" disabled={run.isPending} onClick={() => run.mutate(path)}>
          {run.isPending ? "Running…" : run.isError ? "Try again" : "Run easy digest"}
        </Button>
        <Button size="sm" variant="secondary" disabled={run.isPending} onClick={() => { run.reset(); setConfirming(false); }}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

export function PreviewDialog({
  unit, titles, onClose, onStep, hasPrev, hasNext,
}: {
  unit: Unit | null;
  titles: Record<string, string>;
  onClose: () => void;
  onStep: (d: -1 | 1) => void;
  hasPrev: boolean;
  hasNext: boolean;
}) {
  const [shown, setShown] = useState<{ key: string; path: string } | null>(null);
  const open = !!unit;
  const current = unit && (unit.files.find((f) => shown?.key === unit.key && f.path === shown.path) ?? unit.primary);
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      {unit && current && (
        <DialogContent
          className="top-4 flex max-h-[calc(100dvh-2rem)] max-w-5xl flex-col"
          onKeyDown={(e) => {
            if (e.target instanceof HTMLElement && /^(INPUT|TEXTAREA)$/.test(e.target.tagName)) return;
            if (e.key === "ArrowLeft" && hasPrev) onStep(-1);
            if (e.key === "ArrowRight" && hasNext) onStep(1);
          }}
        >
          <div className="flex items-center gap-2 border-b p-3">
            <Button variant="ghost" size="icon" aria-label="Previous item" disabled={!hasPrev} onClick={() => onStep(-1)}>‹</Button>
            <div className="min-w-0 flex-1">
              <DialogTitle className="truncate text-sm font-semibold">{unit.name}</DialogTitle>
              <DialogDescription className="truncate text-xs text-muted-foreground">{unit.primary.path}</DialogDescription>
            </div>
            <Button variant="ghost" size="icon" aria-label="Next item" disabled={!hasNext} onClick={() => onStep(1)}>›</Button>
            <Button variant="secondary" size="sm" onClick={onClose}>Close</Button>
          </div>
          <div className="grid min-h-0 flex-1 gap-4 overflow-y-auto p-4 md:grid-cols-[minmax(0,1fr)_18rem]">
            <div className="min-w-0">
              <FilePreview key={current.path} item={current} />
            </div>
            <aside className="flex flex-col gap-3 text-sm">
              {unit.failure && (
                <div className="rounded-md border border-bad p-2">
                  <p className="font-medium text-bad">Why cataloging failed</p>
                  <p className="text-xs break-words">{unit.failure}</p>
                </div>
              )}
              <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
                <dt className="text-muted-foreground">Status</dt>
                <dd><StatusPill status={unit.status} depth={unit.depth} /></dd>
                <dt className="text-muted-foreground">Depth</dt>
                <dd>{unit.depth || "-"}</dd>
                <dt className="text-muted-foreground">Format</dt>
                <dd>{unit.format}</dd>
                <dt className="text-muted-foreground">Collection</dt>
                <dd className="break-words">{unit.collections.length ? unit.collections.map((c) => titles[c] ?? c).join(", ") : "-"}</dd>
                <dt className="text-muted-foreground">Wiki note</dt>
                <dd className="break-all">
                  {unit.slug ? <Link to={`/pages/${encodeURIComponent(unit.slug)}` as "/"} className="text-primary underline">{unit.slug}</Link> : "none yet"}
                </dd>
                <dt className="text-muted-foreground">Size</dt>
                <dd>{fmtSize(unit.sizeKb)} · modified {fmtAge(unit.ageDays)}</dd>
                <dt className="text-muted-foreground">Last op</dt>
                <dd>{unit.lastOp ? `${unit.lastOp} · ${unit.lastOpAt.slice(0, 16).replace("T", " ")}` : "-"}</dd>
              </dl>
              {unit.companions.length > 0 && (
                <div>
                  <p className="mb-1 text-xs font-medium text-muted-foreground">{unit.isThread ? "Thread files" : "Belongs with it"}</p>
                  <ul className="flex max-h-40 flex-col gap-1 overflow-y-auto">
                    {unit.files.map((f) => (
                      <li key={f.path}>
                        <Button
                          variant={f.path === current.path ? "default" : "secondary"}
                          size="sm"
                          className="h-auto w-full justify-start whitespace-normal break-all py-1 text-left"
                          aria-pressed={f.path === current.path}
                          onClick={() => setShown({ key: unit.key, path: f.path })}
                        >
                          {f.name}
                        </Button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {unit.next && (
                <div>
                  <p className="mb-1 text-xs font-medium text-muted-foreground">Next step</p>
                  <code className="block break-all rounded-md bg-secondary p-2 text-xs">{unit.next}</code>
                  <div className="mt-1"><CopyButton text={unit.next} label="Copy command" /></div>
                </div>
              )}
              {canDigest(unit) && <DigestAction key={unit.key} unit={unit} />}
              {unit.status === "digested" && <p className="text-xs text-muted-foreground">{STATUS_LABEL.digested} at depth {unit.depth || "?"}. Deeper reads run from the CLI.</p>}
              <div className="flex flex-wrap gap-2">
                <Button asChild variant="secondary" size="sm">
                  <a href={rawFileUrl(current.path)} target="_blank" rel="noopener noreferrer">Open file</a>
                </Button>
                {unit.primary.sourceUrl && (
                  <Button asChild variant="secondary" size="sm">
                    <a href={unit.primary.sourceUrl} target="_blank" rel="noopener noreferrer">Source page</a>
                  </Button>
                )}
              </div>
            </aside>
          </div>
        </DialogContent>
      )}
    </Dialog>
  );
}
