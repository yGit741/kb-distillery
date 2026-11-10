import { useId, useState, type DragEvent } from "react";
import { Link } from "@tanstack/react-router";
import { ArrowRight, FileText, Globe, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import type { IngestJob } from "@/api/types";
import { cn } from "@/lib/utils";
import { ACCEPT, BACKENDS, fileProblem, sizeLabel, sourceKind, sourceName, TIERS, urlProblem, type Flow, type Source } from "./model";

/** Drag a file in, click to choose one, or paste a web address and press Use. */
export function SourcePicker({ onSource, tall }: { onSource: (s: Source) => void; tall?: boolean }) {
  const [over, setOver] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [url, setUrl] = useState("");
  const inputId = useId();

  const takeFile = (f: File | undefined) => {
    if (!f) return;
    const p = fileProblem(f);
    setProblem(p);
    if (!p) onSource({ kind: "file", file: f });
  };
  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    takeFile(e.dataTransfer.files[0]);
  };
  const useUrl = () => {
    const p = urlProblem(url);
    setProblem(p);
    if (!p) onSource({ kind: "url", url: url.trim() });
  };

  return (
    <div className="flex flex-col gap-3">
      <label
        htmlFor={inputId}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={onDrop}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border border-dashed px-4 text-center transition-colors",
          tall ? "min-h-64" : "min-h-44",
          over ? "border-primary bg-accent-soft" : "hover:bg-accent/40",
        )}
      >
        <Upload className="size-5 text-muted-foreground" strokeWidth={1.5} aria-hidden />
        <span className="text-sm font-medium">Drop a paper or an article here</span>
        <span className="text-xs text-muted-foreground">or click to choose a PDF, Markdown, text or HTML file</span>
        <input id={inputId} type="file" className="sr-only" accept={ACCEPT.join(",")} aria-label="Choose a file" onChange={(e) => takeFile(e.target.files?.[0])} />
      </label>
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); useUrl(); }}>
        <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="or paste a web address" aria-label="Web address" inputMode="url" />
        <Button type="submit" variant="secondary" disabled={!url.trim()}>Use</Button>
      </form>
      <p role="alert" className="min-h-5 text-sm text-muted-foreground">{problem}</p>
    </div>
  );
}

/** The chosen source in one row: icon, name, kind, size, and where catalog will file it. */
export function SourceSummary({ source, onChange, disabled }: { source: Source; onChange?: () => void; disabled?: boolean }) {
  const kind = sourceKind(source);
  const Icon = source.kind === "url" ? Globe : FileText;
  return (
    <div className="flex items-start gap-3 rounded-lg border bg-background px-3 py-2.5" data-testid="source-summary">
      <Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" strokeWidth={1.5} aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium" title={sourceName(source)}>{sourceName(source)}</p>
        <p className="text-xs text-muted-foreground">
          {kind.label}{source.kind === "file" && ` · ${sizeLabel(source.file.size)}`} · filed under <span className="font-mono">{kind.folder}</span>
        </p>
      </div>
      {onChange && (
        <Button variant="ghost" size="sm" className="-my-1" onClick={onChange} disabled={disabled}>Change</Button>
      )}
    </div>
  );
}

function Choice({ name, checked, onPick, title, hint }: { name: string; checked: boolean; onPick: () => void; title: string; hint?: string }) {
  return (
    <label className="flex cursor-pointer items-baseline gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-accent/40 has-[:checked]:bg-accent-soft has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-60">
      <input type="radio" name={name} checked={checked} onChange={onPick} className="accent-[var(--primary)]" />
      <span className="w-14 shrink-0 font-medium">{title}</span>
      {hint && <span className="text-muted-foreground">{hint}</span>}
    </label>
  );
}

/** Triage: what was dropped, how deeply to read it, which model backend runs it, the collection, and the Ingest button. */
export function TriageCard({ flow, collections }: { flow: Flow; collections: string[] }) {
  const listId = useId();
  const tierName = useId();
  const backendName = useId();
  const busy = flow.starting || flow.jobId !== null;
  const noCall = flow.tier === "listed";
  if (!flow.source) return null;
  return (
    <Card aria-label="Triage">
      <CardHeader>
        <CardTitle>What is it?</CardTitle>
        <CardDescription>The new pages arrive as a proposal. Nothing changes in your wiki until you accept it.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        <SourceSummary source={flow.source} onChange={() => flow.setSource(null)} disabled={busy} />
        <fieldset className="flex flex-col gap-0.5" disabled={busy}>
          <legend className="mb-1.5 text-sm font-medium">How deeply should it be read?</legend>
          {TIERS.map((t) => (
            <Choice key={t.id} name={tierName} checked={flow.tier === t.id} onPick={() => flow.setTier(t.id)} title={t.label} hint={t.hint} />
          ))}
        </fieldset>
        <fieldset className="flex flex-col gap-1.5" disabled={busy || noCall}>
          <legend className="mb-1.5 text-sm font-medium">Run the model on</legend>
          <div className="inline-flex w-fit rounded-md border p-0.5" role="radiogroup" aria-label="Run the model on">
            {BACKENDS.map((b) => (
              <label key={b.id || "default"} className="cursor-pointer rounded-[5px] px-3 py-1 text-sm text-muted-foreground has-[:checked]:bg-accent-soft has-[:checked]:text-foreground has-[:disabled]:cursor-not-allowed">
                <input type="radio" name={backendName} className="sr-only" checked={flow.backend === b.id} onChange={() => flow.setBackend(b.id)} />
                {b.label}
              </label>
            ))}
          </div>
          <p className="text-xs text-muted-foreground">{noCall ? "Listed makes no model call." : "Default is the server's setting. Batch is half price and slower."}</p>
        </fieldset>
        <div className="flex flex-col gap-1.5">
          <label htmlFor={listId + "-in"} className="text-sm font-medium">Collection <span className="font-normal text-muted-foreground">(optional)</span></label>
          <Input id={listId + "-in"} list={listId} value={flow.collection} onChange={(e) => flow.setCollection(e.target.value)} placeholder="a course, series or book page" disabled={busy} autoComplete="off" />
          <datalist id={listId}>{collections.map((c) => <option key={c} value={c} />)}</datalist>
        </div>
        {flow.startError && <p role="alert" className="text-sm text-muted-foreground">{flow.startError}</p>}
        <Button className="self-start" onClick={flow.start} disabled={busy}>
          {flow.starting ? "Starting" : flow.jobId ? "Started" : "Ingest"}
        </Button>
      </CardContent>
    </Card>
  );
}

const LABEL: Record<string, string> = { fetch: "Fetch", convert: "Convert", digest: "Digest", propose: "Propose" };
const STATE_WORD: Record<string, string> = { pending: "waiting", active: "working", done: "done", skipped: "skipped", failed: "stopped" };
const IDLE_STEPS = ["fetch", "convert", "digest", "propose"].map((name) => ({ name, state: "pending", detail: "" }));

function Marker({ state }: { state: string }) {
  const base = "mt-1 size-2.5 shrink-0 rounded-full border";
  if (state === "done") return <span className={cn(base, "border-ok bg-ok")} aria-hidden />;
  if (state === "failed") return <span className={cn(base, "border-bad bg-bad")} aria-hidden />;
  if (state === "active") return <span className={cn(base, "border-primary bg-transparent motion-safe:animate-pulse")} aria-hidden />;
  if (state === "skipped") return <span className={cn(base, "border-muted-foreground/50 bg-muted-foreground/30")} aria-hidden />;
  return <span className={cn(base, "border-muted-foreground/40")} aria-hidden />;
}

function title(job: IngestJob | null, started: boolean): string {
  if (!started) return "Progress";
  if (job?.status === "done") return "Ready for your review";
  if (job?.status === "failed") return "This one did not finish";
  return "Working on it";
}

/**
 * The calm progress card: four steps with a line of detail each (fixed height, so arriving events never move the layout),
 * a quiet failure note, and at the end the link to the proposal.
 */
export function JobCard({ job, source, started, onAgain }: { job: IngestJob | null; source: string; started: boolean; onAgain?: () => void }) {
  const steps = job?.steps ?? IDLE_STEPS;
  const ended = job?.status === "done" || job?.status === "failed";
  return (
    <Card aria-label="Ingest progress">
      <CardHeader>
        <CardTitle>{title(job, started)}</CardTitle>
        <CardDescription className="truncate" title={source}>{started ? source : "Shows here once you start."}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <ol className="flex flex-col gap-2.5" aria-live="polite">
          {steps.map((s) => (
            <li key={s.name} className="flex items-start gap-3 text-sm" data-state={s.state}>
              <Marker state={s.state} />
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline justify-between gap-3">
                  <span className={cn("font-medium", s.state === "pending" && "text-muted-foreground")}>{LABEL[s.name] ?? s.name}</span>
                  <span className="text-xs text-muted-foreground">{started ? STATE_WORD[s.state] ?? s.state : ""}</span>
                </div>
                <p className="h-4 truncate text-xs text-muted-foreground" title={s.detail}>{s.detail}</p>
              </div>
            </li>
          ))}
        </ol>
        {job?.status === "failed" && (
          <div role="alert" className="rounded-md border bg-muted/40 px-3 py-2.5 text-sm">
            <p>{job.error ? job.error.charAt(0).toUpperCase() + job.error.slice(1) : "The job stopped."}</p>
            <p className="mt-0.5 text-xs text-muted-foreground">Nothing was added to your pages.</p>
          </div>
        )}
        {job?.status === "done" && job.proposal_id && (
          <div className="flex flex-col gap-2 rounded-md border bg-accent-soft/50 px-3 py-2.5">
            <p className="text-sm">
              One proposal, {job.pages.length} {job.pages.length === 1 ? "page" : "pages"}
            </p>
            {job.pages.length > 0 && (
              <p className="truncate font-mono text-xs text-muted-foreground" title={job.pages.join(", ")}>{job.pages.join(", ")}</p>
            )}
            <Button asChild size="sm" className="self-start">
              <Link to={`/proposals/${encodeURIComponent(job.proposal_id)}` as "/"}>
                Review the proposal <ArrowRight className="size-4" strokeWidth={1.5} aria-hidden />
              </Link>
            </Button>
          </div>
        )}
        {ended && onAgain && (
          <Button variant="ghost" size="sm" className="self-start" onClick={onAgain}>{job?.status === "failed" ? "Start over" : "Ingest another"}</Button>
        )}
      </CardContent>
    </Card>
  );
}
