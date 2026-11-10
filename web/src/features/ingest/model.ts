import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useDataSource } from "@/api";
import type { IngestJob } from "@/api/types";
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
      while (!ctl.signal.aborted && !ended) {
        try {
          take(await ds.getIngestJob(jobId));
        } catch {
          /* try again on the next tick */
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
  start: () => void;
  starting: boolean;
  startError: string | null;
  jobId: string | null;
  job: IngestJob | null;
  reset: () => void;
}

/** Everything both layouts share: the chosen source, the triage answers, the started job. */
export function useIngestFlow(): Flow {
  const ds = useDataSource();
  const [source, setSource] = useState<Source | null>(null);
  const [tier, setTier] = useState<TierId>(DEFAULT_TIER);
  const [collection, setCollection] = useState("");
  const [backend, setBackend] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [startError, setStartError] = useState<string | null>(null);
  const live = useRef(true);
  useEffect(() => () => void (live.current = false), []);
  const m = useMutation({
    mutationFn: () => {
      if (!source) throw new Error("Choose a source first.");
      return ds.startIngest({
        ...(source.kind === "file" ? { file: source.file } : { url: source.url }),
        tier,
        collection: collection.trim() || undefined,
        backend: tier === "listed" ? undefined : backend || undefined,
      });
    },
    onSuccess: (r) => {
      setStartError(null);
      setJobId(r.job_id);
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
  return { source, setSource, tier, setTier, collection, setCollection, backend, setBackend, start: () => m.mutate(), starting: m.isPending, startError, jobId, job, reset };
}
