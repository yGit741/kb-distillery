import { Link } from "@tanstack/react-router";
import { Ellipsis, FolderUp, Loader2 } from "lucide-react";
import { useEffect, useRef, useState, type DragEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { ImportAdapter, ImportOutcome, ImportPreview, ImportSource, LibraryInfo } from "./adapter";
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

/** The OKF bundles found in the knowledge library, each with an Add button that previews it like any other source. */
function LibraryList({ library, onSource, busy }: { library: LibraryInfo; onSource: (s: ImportSource) => void; busy: boolean }) {
  return (
    <section className="flex flex-col gap-1.5" aria-label="From your library">
      <h3 className="text-xs font-medium text-muted-foreground">From your library</h3>
      <p className="break-all text-xs text-muted-foreground">{library.path}</p>
      {library.bundles.length === 0 ? (
        <p className="text-sm text-muted-foreground">No OKF bundles found in this folder.</p>
      ) : (
        <ul className="flex max-h-48 flex-col divide-y overflow-auto rounded-lg border">
          {library.bundles.map((b) => (
            <li key={b.path} className="flex items-center gap-2 px-3 py-2">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{b.name}</p>
                <p className="truncate text-xs text-muted-foreground" title={b.path}>{b.kind === "zip" ? "zip" : "folder"} · {b.path}</p>
              </div>
              <Button size="sm" variant="outline" disabled={busy || b.added} aria-label={`${b.added ? "Added" : "Add"} ${b.name}`}
                onClick={() => onSource({ kind: "path", path: b.path })}>
                {b.added ? "Added" : "Add"}
              </Button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** Inline form for the library folder: browsers cannot give a real path from a folder picker, so it is typed or pasted. */
function LibraryForm({ initial, onSave, onCancel }: { initial: string; onSave: (path: string) => Promise<void>; onCancel: () => void }) {
  const [value, setValue] = useState(initial);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");
  const save = async () => {
    setSaving(true);
    setErr("");
    try {
      await onSave(value.trim());
    } catch (e) {
      setErr(message(e));
      setSaving(false);
    }
  };
  return (
    <form className="flex flex-col gap-1.5" onSubmit={(e) => { e.preventDefault(); void save(); }}>
      <label htmlFor="kb-library-path" className="text-xs font-medium text-muted-foreground">Knowledge library folder</label>
      <div className="flex gap-2">
        <Input id="kb-library-path" value={value} onChange={(e) => setValue(e.target.value)} placeholder="/Users/you/okf-bundles" spellCheck={false} autoFocus />
        <Button type="submit" disabled={saving}>{saving && <Loader2 aria-hidden className="animate-spin" />}Save</Button>
        <Button type="button" variant="ghost" onClick={onCancel} disabled={saving}>Cancel</Button>
      </div>
      <p className="text-xs text-muted-foreground">An absolute folder path on this computer. Leave it empty to remove the library.</p>
      {err && <p role="alert" className="text-sm text-bad break-words">{err}</p>}
    </form>
  );
}

function SourceStep({ onSource, busy, error, library, setting, onSaveLibrary, onCancelSetting }: {
  onSource: (s: ImportSource) => void; busy: boolean; error: string;
  library: LibraryInfo | null; setting: boolean; onSaveLibrary: (path: string) => Promise<void>; onCancelSetting: () => void;
}) {
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
      {setting && <LibraryForm initial={library?.path ?? ""} onSave={onSaveLibrary} onCancel={onCancelSetting} />}
      {!setting && library?.path && <LibraryList library={library} onSource={onSource} busy={busy} />}
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
    return (
      <ResultCard tone="pending" title="Received">
        <p>{outcome.message}</p>
        {outcome.ref && <p className="mt-1 break-all">Inbox item <code className="text-xs text-foreground">{outcome.ref}</code></p>}
      </ResultCard>
    );
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
  const access = adapter.library;
  const [library, setLibrary] = useState<LibraryInfo | null>(null);
  const [menu, setMenu] = useState(false);
  const [setting, setSetting] = useState(false);

  const rescan = () => {
    setMenu(false);
    setError("");
    access?.get().then(setLibrary, (e) => setError(message(e)));
  };
  const saveLibrary = async (path: string) => {
    if (!access) return;
    setLibrary(await access.set(path || null));
    setSetting(false);
  };

  useEffect(() => {
    if (open) return;
    setStep({ name: "source" });
    setBusy(false);
    setError("");
    setMenu(false);
    setSetting(false);
  }, [open]);

  // the library is scanned each time the dialog opens
  useEffect(() => {
    if (!open || !access) return;
    let live = true;
    access.get().then((l) => live && setLibrary(l), () => undefined);
    return () => { live = false; };
  }, [open, access]);

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
        {access && (
          <div className="absolute right-3 top-3">
            <Button variant="ghost" size="icon" aria-label="More options" aria-haspopup="menu" aria-expanded={menu} onClick={() => setMenu((m) => !m)}>
              <Ellipsis aria-hidden className="size-4" strokeWidth={1.6} />
            </Button>
            {menu && (
              <div role="menu" className="absolute right-0 top-full z-10 mt-1 flex w-52 flex-col rounded-lg border bg-popover p-1 shadow-[var(--shadow)]">
                <button type="button" role="menuitem" className="rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent"
                  onClick={() => { setMenu(false); setStep({ name: "source" }); setSetting(true); }}>
                  Set knowledge library…
                </button>
                <button type="button" role="menuitem" className="rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent disabled:opacity-50"
                  disabled={!library?.path} onClick={rescan}>
                  Rescan library
                </button>
              </div>
            )}
          </div>
        )}
        <DialogTitle className="text-base font-semibold">Add knowledge base</DialogTitle>
        <DialogDescription id="kb-import-help" className="mb-3 mt-1 text-sm text-muted-foreground">
          Import an OKF bundle as a new knowledge base. Your current one is not changed.
        </DialogDescription>
        {step.name === "source" && (
          <SourceStep onSource={(s) => void choose(s)} busy={busy} error={error} library={library} setting={setting}
            onSaveLibrary={saveLibrary} onCancelSetting={() => setSetting(false)} />
        )}
        {step.name === "preview" && (
          <PreviewStep adapter={adapter} source={step.source} preview={step.preview} onBack={() => setStep({ name: "source" })} onDone={done} />
        )}
        {step.name === "result" && <ResultStep outcome={step.outcome} onClose={() => onOpenChange(false)} />}
      </DialogContent>
    </Dialog>
  );
}
