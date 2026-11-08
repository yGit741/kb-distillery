import type { DigestJob } from "@/api/types";

export const BACKEND_LABEL: Record<string, string> = { subscription: "Subscription", api: "API", batch: "Batch" };

export const BACKEND_HINT: Record<string, string> = {
  subscription: "Runs on your Claude subscription, no extra charge.",
  api: "Pay per token, finishes in minutes.",
  batch: "Half price, results come back later.",
};

export const usd = (n: number): string => (n === 0 ? "$0" : n < 0.01 ? "under $0.01" : `$${n.toFixed(2)}`);

export const tokens = (n: number): string => (n >= 1000 ? `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}k` : String(n));

export const isLive = (j: Pick<DigestJob, "status">): boolean => j.status === "queued" || j.status === "running";

const SOURCE_DONE = new Set(["finalized", "failed", "skipped", "cancelled"]);

export function progress(j: DigestJob): { done: number; total: number } {
  return { done: j.sources.filter((s) => SOURCE_DONE.has(s.status)).length, total: j.sources.length };
}

export const JOB_LABEL: Record<string, string> = {
  queued: "Waiting to start",
  running: "Running",
  finished: "Finished",
  finalized: "Finished",
  done: "Finished",
  failed: "Stopped with an error",
  cancelled: "Cancelled",
};

export const SOURCE_LABEL: Record<string, string> = {
  pending: "Waiting",
  filling: "Reading",
  digesting: "Writing",
  finalized: "Done",
  failed: "Failed",
  skipped: "Skipped",
  cancelled: "Cancelled",
};

/** `wiki/some-page.md` to `some-page`. */
export const slugOf = (page: string): string => page.replace(/^wiki\//, "").replace(/\.md$/, "");

export const nameOf = (raw: string): string => raw.split("/").pop() || raw;
