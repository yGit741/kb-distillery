import { Link } from "@tanstack/react-router";
import { FolderUp, Loader2 } from "lucide-react";
import { useEffect, useRef, useState, type DragEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { ImportAdapter, ImportOutcome, ImportPreview, ImportSource } from "./adapter";
import { bundleFromDrop, bundleFromFileInput, bundleFromFolderInput, BundleSourceError } from "./bundleFiles";
import { ResultCard } from "./ResultCard";

const SHOWN = 20;
const message = (e: unknown) => (e instanceof Error ? e.message : String(e));

type Step = { name: "source" } | { name: "preview"; source: ImportSource; preview: ImportPreview } | { name: "result"; outcome: ImportOutcome };

function Findings({ items, tone }: { items: string[]; tone: "bad" | "warn" }) {
  if (!items.length) return null;
  return (
    <ul className={cn("flex max-h-40 flex-col gap-1 overflow-auto text-xs", tone === "bad" ? "text-bad" : "text-warn")} aria-label={tone === "bad" ? "Errors" : "Warnings"}>
      {items.slice(0, SHOWN).map((m, i) => <li key={i} className="break-words">{m}</li>)}
      {items.length > SHOWN && <li>and {items.length - SHOWN} more</li>}
    </ul>
  );
}

function SourceStep({ onSource, busy, error }: { onSource: (s: ImportSource) => void; busy: boolean; error: string }) {
  const [over, setOver] = useState(false);
  const [err, setErr] = useState("");
  const [url, setUrl] = useState("");
  const zipInput = useRef<HTMLInputElement>(null);
  const dirInput = useRef<HTMLInputElement>(null);

  const give = async (get: () => Promise<File> | File) => {
    setErr("");
    try {
      onSource({ kind: "zip", file: await get() });
    } catch (e) {
      setErr(e instanceof BundleSourceError ? e.message : message(e));
    }
  };
  const drop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    const dt = e.dataTransfer;
    void give(() => bundleFromDrop(dt));
  };

  return (
    <div className="flex flex-col gap-3">
      <div
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={drop}
        data-testid="kb-drop"
        className={cn("flex flex-col items-center gap-2 rounded-lg border border-dashed p-6 text-center text-sm", over && "border-primary bg-accent")}
      >
        <FolderUp aria-hidden className="size-6 text-muted-foreground" />
        <p>Drop a folder or a .zip here</p>
        <p className="text-xs text-muted-foreground">
          or <button type="button" className="text-primary hover:underline" onClick={() => zipInput.current?.click()}>choose a .zip</button>
          {" / "}
          <button type="button" className="text-primary hover:underline" onClick={() => dirInput.current?.click()}>choose a folder</button>
        </p>
        <input ref={zipInput} type="file" accept=".zip,application/zip" className="hidden" aria-label="Choose a .zip" data-testid="kb-zip-input"
          onChange={(e) => { const f = [...(e.target.files ?? [])]; e.target.value = ""; if (f.length) void give(() => bundleFromFileInput(f)); }} />
        <input ref={dirInput} type="file" className="hidden" aria-label="Choose a folder" data-testid="kb-dir-input"
          {...({ webkitdirectory: "" } as object)}
          onChange={(e) => { const f = [...(e.target.files ?? [])]; e.target.value = ""; if (f.length) void give(() => bundleFromFolderInput(f)); }} />
      </div>
      <form className="flex flex-col gap-1.5" onSubmit={(e) => { e.preventDefault(); if (url.trim()) onSource({ kind: "git", url: url.trim() }); }}>
        <label htmlFor="kb-git-url" className="text-xs font-medium text-muted-foreground">From git URL</label>
        <div className="flex gap-2">
          <Input id="kb-git-url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://github.com/you/notes.git#main" spellCheck={false} />
          <Button type="submit" variant="outline" disabled={!url.trim() || busy}>Preview</Button>
        </div>
      </form>
      {busy && <p className="flex items-center gap-2 text-sm text-muted-foreground" role="status"><Loader2 aria-hidden className="size-4 animate-spin" />Checking the bundle…</p>}
      {(err || error) && <p role="alert" className="text-sm text-bad break-words">{err || error}</p>}
    </div>
  );
}

function PreviewStep({ adapter, source, preview, onBack, onDone }: {
  adapter: ImportAdapter; source: ImportSource; preview: ImportPreview; onBack: () => void; onDone: (o: ImportOutcome) => void;
}) {
  const [current, setCurrent] = useState(preview);
  const [id, setId] = useState(preview.id);
  const [checking, setChecking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const seq = useRef(0);

  // a new id is validated again: "already exists" and "not a valid id" are answers of the server
  useEffect(() => {
    if (id === current.id) return;
    const mine = ++seq.current;
    setChecking(true);
    const t = setTimeout(() => {
      adapter.validate({ ...source, id }).then(
        (p) => mine === seq.current && (setCurrent(p), setError("")),
        (e) => mine === seq.current && setError(message(e)),
      ).finally(() => mine === seq.current && setChecking(false));
    }, 400);
    return () => clearTimeout(t);
  }, [id, current.id, adapter, source]);

  const settled = id === current.id && !checking;
  const create = async () => {
    setBusy(true);
    setError("");
    try {
      onDone(await adapter.submit({ ...source, id: current.id }));
    } catch (e) {
      setError(message(e));
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <div>
        <p className="text-sm font-medium">{current.name}</p>
        <p className="text-xs text-muted-foreground break-all">{current.source} · {current.pages} {current.pages === 1 ? "page" : "pages"}</p>
      </div>
      <div className="flex flex-col gap-1.5">
        <label htmlFor="kb-import-id" className="text-xs font-medium text-muted-foreground">Id</label>
        <Input id="kb-import-id" value={id} onChange={(e) => setId(e.target.value.trim())} spellCheck={false} />
      </div>
      <Findings items={current.errors} tone="bad" />
      <Findings items={current.warnings} tone="warn" />
      {settled && !current.errors.length && !current.warnings.length && <p className="text-xs text-muted-foreground">No problems found.</p>}
      {error && <p role="alert" className="text-sm text-bad break-words">{error}</p>}
      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={onBack} disabled={busy}>Back</Button>
        <Button onClick={() => void create()} disabled={!settled || busy || current.errors.length > 0 || !id}>
          {busy && <Loader2 aria-hidden className="animate-spin" />}Create
        </Button>
      </div>
    </div>
  );
}

function ResultStep({ outcome, onClose }: { outcome: ImportOutcome; onClose: () => void }) {
  if (outcome.state === "received") {
    return <ResultCard tone="pending" title="Received">{outcome.message}</ResultCard>;
  }
  return (
    <ResultCard
      tone="done"
      title="Imported"
      action={
        <Button asChild>
          <Link to={"/graph" as "/"} search={{ kbs: outcome.id } as never} onClick={onClose}>Open it</Link>
        </Button>
      }
    >
      {outcome.name}, {outcome.pages} {outcome.pages === 1 ? "page" : "pages"}.
    </ResultCard>
  );
}

/**
 * Add a knowledge base from an OKF bundle: 1 source (drop a folder or .zip, or a git URL), 2 preview (name, pages,
 * errors and warnings, an editable id), 3 result. How the bundle is checked and received is the adapter's business.
 */
export function AddKnowledgeBase({ adapter, open, onOpenChange }: { adapter: ImportAdapter; open: boolean; onOpenChange: (open: boolean) => void }) {
  const [step, setStep] = useState<Step>({ name: "source" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const qc = useQueryClient();

  useEffect(() => {
    if (open) return;
    setStep({ name: "source" });
    setBusy(false);
    setError("");
  }, [open]);

  const choose = async (source: ImportSource) => {
    setBusy(true);
    setError("");
    try {
      setStep({ name: "preview", source, preview: await adapter.validate(source) });
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  };
  const done = (outcome: ImportOutcome) => {
    if (outcome.state === "imported") void qc.invalidateQueries({ queryKey: ["kb-list"] });
    setStep({ name: "result", outcome });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="p-4" aria-describedby="kb-import-help">
        <DialogTitle className="text-base font-semibold">Add knowledge base</DialogTitle>
        <DialogDescription id="kb-import-help" className="mb-3 mt-1 text-sm text-muted-foreground">
          Import an OKF bundle as a new knowledge base. Your current one is not changed.
        </DialogDescription>
        {step.name === "source" && <SourceStep onSource={(s) => void choose(s)} busy={busy} error={error} />}
        {step.name === "preview" && (
          <PreviewStep adapter={adapter} source={step.source} preview={step.preview} onBack={() => setStep({ name: "source" })} onDone={done} />
        )}
        {step.name === "result" && <ResultStep outcome={step.outcome} onClose={() => onOpenChange(false)} />}
      </DialogContent>
    </Dialog>
  );
}
