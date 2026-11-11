import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useDataSource } from "@/api";
import type { IngestInput, IngestJob, IngestListItem } from "@/api/types";
import { LAYER_TYPES } from "@/api/model";
import { splitFrames } from "@/features/chat/sse";
import { useApiQuery } from "@/lib/useApiQuery";

export const TIERS = [
  { id: "listed", label: "Listed", hint: "File it and note it; nothing is read yet." },
  { id: "easy", label: "Easy", hint: "A quick skim of the opening pages." },
  { id: "full", label: "Full", hint: "Read it through and write it up." },
  { id: "deep", label: "Deep", hint: "A slow, careful read of the whole source." },
] as const;
export type TierId = (typeof TIERS)[number]["id"];
export const DEFAULT_TIER: TierId = "full";

export const ACCEPT = [".pdf", ".md", ".markdown", ".txt", ".html", ".htm"];

export type Source = { kind: "file"; file: File } | { kind: "url"; url: string };

export const sourceName = (s: Source): string => (s.kind === "file" ? s.file.name : s.url);

/** What kind of source this is and the raw/ folder catalog usually files it under (catalog has the last word). */
export function sourceKind(s: Source): { label: string; folder: string } {
  if (s.kind === "url") return { label: "Web page", folder: "raw/web-clips/" };
  const ext = s.file.name.split(".").pop()?.toLowerCase() ?? "";
  if (ext === "pdf") return { label: "PDF document", folder: "raw/printed-docs/" };
  if (ext === "html" || ext === "htm") return { label: "Saved web page", folder: "raw/web-clips/" };
  return { label: "Text or Markdown", folder: "raw/printed-docs/" };
}

export const sizeLabel = (n: number): string => (n < 1024 ? `${n} B` : n < 1024 * 1024 ? `${Math.round(n / 1024)} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`);

/** "" means the server default (`$KB_LLM_BACKEND`); every run may pick another. */
export const BACKENDS = [
  { id: "", label: "Default" },
  { id: "subscription", label: "Subscription" },
  { id: "api", label: "API" },
  { id: "batch", label: "Batch" },
] as const;

/** null when the file is one this screen takes, else a plain sentence for the person. */
export function fileProblem(f: File): string | null {
  const ext = f.name.includes(".") ? "." + f.name.split(".").pop()!.toLowerCase() : "";
  if (!ACCEPT.includes(ext)) return `${ext || "That kind of"} file cannot be ingested here. Try a PDF, Markdown, text or web page.`;
  if (f.size === 0) return "That file is empty.";
  return null;
}

const YEAR_IN_NAME = /(1[89]\d{2}|20\d{2})/;
const ARXIV_ID = /(?:^|[^\d])(\d{2})(0[1-9]|1[0-2])\.\d{4,5}(?:v\d+)?(?:[^\d]|$)/;

/**
 * A paper is filed as `<year>-<title>.pdf`, and the year is read from the file name (catalog._suggest_paper_name). True
 * when this file is a PDF whose name carries none, so the person has to say it before the file can be filed.
 */
export function needsYear(f: File): boolean {
  const stem = f.name.replace(/\.[^.]*$/, "").toLowerCase();
  return f.name.toLowerCase().endsWith(".pdf") && !YEAR_IN_NAME.test(stem);
}

/** The year an arXiv number in the name stands for (`2607.26604` is July 2026), or "" when there is none. */
export function yearGuess(name: string): string {
  const m = ARXIV_ID.exec(name);
  return m ? "20" + m[1] : "";
}

/** True for a year the server takes: four digits, 1800 to 2099. */
export function yearOk(text: string): boolean {
  return /^(1[89]|20)\d{2}$/.test(text.trim());
}

/** null when `text` looks like a web address we can send, else a plain sentence. */
export function urlProblem(text: string): string | null {
  try {
    const u = new URL(text.trim());
    return u.protocol === "http:" || u.protocol === "https:" ? null : "Use an address that starts with http:// or https://.";
  } catch {
    return "That does not look like a web address.";
  }
}

const POLL_MS = 1500;
const LOST_AFTER = 4;

function lostJob(id: string, last: IngestJob | null): IngestJob {
  const steps = (last?.steps ?? ["fetch", "convert", "digest", "propose"].map((name) => ({ name, state: "pending", detail: "" })))
    .map((s) => (s.state === "active" ? { ...s, state: "failed", detail: "" } : s));
  return { id, status: "failed", source: last?.source ?? "", tier: last?.tier ?? "", collection: last?.collection ?? "", steps, pages: [], proposal_id: null,
    kind: last?.kind ?? "file", backend: last?.backend ?? "", started: last?.started ?? 0, finished: null, step: last?.step ?? "",
    error: "the server lost track of this job, perhaps it restarted. Check Proposals before trying again." };
}

/**
 * The state of one ingest job: the server's SSE stream (`job` events, then `end`), with a plain poll as the fallback
 * when the stream cannot be opened or breaks before it ends.
 */
export function useIngestJob(jobId: string | null): IngestJob | null {
  const ds = useDataSource();
  const [job, setJob] = useState<IngestJob | null>(null);
  useEffect(() => {
    setJob(null);
    if (!jobId) return;
    const ctl = new AbortController();
    let ended = false;
    const take = (j: IngestJob) => {
      if (!ctl.signal.aborted) setJob(j);
      if (j.status !== "running") ended = true;
    };
    const poll = async () => {
      let misses = 0;
      while (!ctl.signal.aborted && !ended) {
        try {
          take(await ds.getIngestJob(jobId));
          misses = 0;
        } catch {
          // the job is gone (the server restarted) or the server is down: stop after a few tries and say so
          if (++misses >= LOST_AFTER) {
            ended = true;
            if (!ctl.signal.aborted) setJob((j) => lostJob(jobId, j));
            break;
          }
        }
        if (!ended) await new Promise((r) => setTimeout(r, POLL_MS));
      }
    };
    const stream = async () => {
      const res = await ds.ingestEvents(jobId, ctl.signal);
      if (!res.ok || !res.body) throw new Error(`stream answered ${res.status}`);
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const { frames, rest } = splitFrames(buf);
        buf = rest;
        for (const f of frames) {
          if (f.event === "job") {
            try {
              take(JSON.parse(f.data) as IngestJob);
            } catch {
              /* a malformed frame is skipped */
            }
          } else if (f.event === "end") ended = true;
        }
        if (ended) {
          void reader.cancel().catch(() => {});
          break;
        }
      }
    };
    void stream()
      .catch(() => undefined)
      .then(() => (ended || ctl.signal.aborted ? undefined : poll()));
    return () => ctl.abort();
  }, [ds, jobId]);
  return job;
}

// --- the inbox of ingests -------------------------------------------------------------------------------------------
export const INGEST_LIST_KEY = ["ingest-list"] as const;

export type IngestGroupId = "progress" | "review" | "done" | "failed";
export const INGEST_GROUPS: { id: IngestGroupId; title: string }[] = [
  { id: "progress", title: "In progress" },
  { id: "review", title: "Waiting for your review" },
  { id: "done", title: "Done" },
  { id: "failed", title: "Did not finish" },
];

/** Where one ingest stands: running; done with its proposal still open (or stale); done and decided; or stopped. */
export function groupOf(i: Pick<IngestListItem, "status" | "proposal_status">): IngestGroupId {
  if (i.status === "running") return "progress";
  if (i.status === "done") return i.proposal_status === "open" || i.proposal_status === "stale" ? "review" : "done";
  return "failed";
}

/** The items by group, newest first inside each (the server sends them that way), empty groups left out. */
export function groupIngests(items: IngestListItem[]): { id: IngestGroupId; title: string; items: IngestListItem[] }[] {
  return INGEST_GROUPS.map((g) => ({ ...g, items: items.filter((i) => groupOf(i) === g.id) })).filter((g) => g.items.length > 0);
}

/** A time from the server: epoch seconds (a job) or an ISO string (a proposal). */
export function whenLabel(t: number | string | null | undefined): string {
  if (t === null || t === undefined || t === 0 || t === "") return "";
  const d = new Date(typeof t === "number" ? t * 1000 : t);
  return Number.isNaN(d.getTime()) ? String(t) : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export const tierLabel = (t: string): string => TIERS.find((x) => x.id === t)?.label ?? t;

/** The row shown the moment a job starts, until the server's own list answers. */
export function pendingItem(id: string, input: IngestInput): IngestListItem {
  return {
    id, status: "running", source: input.file ? input.file.name : input.url ?? "", kind: input.file ? "file" : "url", tier: input.tier,
    collection: input.collection ?? "", backend: input.backend ?? "", started: Date.now() / 1000, finished: null, step: "fetch",
    steps: ["fetch", "convert", "digest", "propose"].map((name) => ({ name, state: "pending", detail: "" })),
    pages: [], proposal_id: null, error: null, proposal_status: null, proposal_updated: null,
  };
}

/** Puts the row of a job that just started at the top of the list, then lets the server's own list replace it. */
function addPending(qc: QueryClient, id: string, input: IngestInput) {
  qc.setQueryData<IngestListItem[]>(INGEST_LIST_KEY, (rows) => [pendingItem(id, input), ...(rows ?? []).filter((r) => r.id !== id)]);
  void qc.invalidateQueries({ queryKey: INGEST_LIST_KEY });
}

/** Starts an ingest again from a list row (a web address only: a file has to be dropped again). */
export function useRetryIngest() {
  const ds = useDataSource();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (i: IngestListItem) => {
      const input: IngestInput = { url: i.source, tier: i.tier, collection: i.collection || undefined, backend: i.backend || undefined };
      return { input, started: await ds.startIngest(input) };
    },
    onSuccess: ({ input, started }) => addPending(qc, started.job_id, input),
  });
}

/** Collection pages (course, series, book, notebook) the person may file the source under; empty when the list fails. */
export function useCollections(): string[] {
  const q = useApiQuery(["ingest-collections"], (ds) => ds.listPages(), { staleTime: 60_000 });
  const types: readonly string[] = LAYER_TYPES.collection.filter((t) => t !== "scope");
  return (q.data?.pages ?? []).filter((p) => types.includes(p.type)).map((p) => p.id).sort();
}

export interface Flow {
  source: Source | null;
  setSource: (s: Source | null) => void;
  tier: TierId;
  setTier: (t: TierId) => void;
  collection: string;
  setCollection: (c: string) => void;
  backend: string;
  setBackend: (b: string) => void;
  /** the year of a paper whose file name has none; `yearMissing` blocks the start until it is given */
  year: string;
  setYear: (y: string) => void;
  yearAsked: boolean;
  yearMissing: boolean;
  start: () => void;
  starting: boolean;
  startError: string | null;
  jobId: string | null;
  job: IngestJob | null;
  reset: () => void;
}

/**
 * Everything both layouts share: the chosen source, the triage answers, the started job. With `inbox` the started job
 * becomes a row of the list and the form is cleared at once, ready for the next source.
 */
export function useIngestFlow(opts: { inbox?: boolean } = {}): Flow {
  const ds = useDataSource();
  const qc = useQueryClient();
  const [source, setSource] = useState<Source | null>(null);
  const [tier, setTier] = useState<TierId>(DEFAULT_TIER);
  const [collection, setCollection] = useState("");
  const [backend, setBackend] = useState("");
  const [year, setYear] = useState("");
  const file = source?.kind === "file" ? source.file : null;
  useEffect(() => setYear(file ? yearGuess(file.name) : ""), [file]);
  // a member of a course, series or book is filed by its collection, not by a year: with a collection the year is
  // still offered (another kind of collection files the PDF as a paper) but no longer holds the start back
  const yearAsked = !!file && needsYear(file);
  const yearMissing = yearAsked && !collection.trim() && !yearOk(year);
  const [jobId, setJobId] = useState<string | null>(null);
  const [startError, setStartError] = useState<string | null>(null);
  const live = useRef(true);
  useEffect(() => () => void (live.current = false), []);
  const m = useMutation({
    mutationFn: async () => {
      if (!source) throw new Error("Choose a source first.");
      const input: IngestInput = {
        ...(source.kind === "file" ? { file: source.file } : { url: source.url }),
        tier,
        collection: collection.trim() || undefined,
        backend: tier === "listed" ? undefined : backend || undefined,
        year: yearAsked && yearOk(year) ? year.trim() : undefined,
      };
      return { input, started: await ds.startIngest(input) };
    },
    onSuccess: ({ input, started }) => {
      setStartError(null);
      if (!opts.inbox) return setJobId(started.job_id);
      addPending(qc, started.job_id, input);
      setSource(null);
      setCollection("");
      m.reset();
    },
    onError: (e) => setStartError(e instanceof Error ? e.message : "Could not start. Try again."),
  });
  const job = useIngestJob(jobId);
  const reset = useCallback(() => {
    setSource(null);
    setJobId(null);
    setStartError(null);
    setCollection("");
    m.reset();
  }, [m]);
  return { source, setSource, tier, setTier, collection, setCollection, backend, setBackend, year, setYear, yearAsked, yearMissing, start: () => m.mutate(), starting: m.isPending, startError, jobId, job, reset };
}
