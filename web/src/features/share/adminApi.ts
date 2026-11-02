/**
 * Typed client for the private Worker's admin API (src/kb_distillery/publish/cloudflare/worker/admin.js). Same contract as the legacy panel:
 * same-origin, session cookie `kb_session` (credentials: same-origin), CSRF header `X-KB-Admin: 1`.
 * There is no schema.d.ts entry: this API belongs to the Worker, not to `python -m kb_distillery.api`.
 *
 *   GET    /admin/api/snapshots            -> SnapshotList
 *   DELETE /admin/api/snapshots/<worker>   body {"confirm": "<worker>"} -> { deleted, url }
 *   POST   /admin/api/prune                -> PrunePlan (dry run only; applying is a CLI step)
 */
export type Online = boolean | "unknown";

export interface Snapshot {
  worker: string;
  name: string;
  url: string;
  kb_version: string | null;
  content_sha: string | null;
  built_at: string | null;
  views_7d: number;
  online: Online;
  behind_main: number | null;
}

export interface SnapshotList {
  snapshots: Snapshot[];
  main: { kb_version: string | null };
  notes: string[];
}

export interface PrunePlan {
  dry_run: boolean;
  orphans: string[];
  unknown: string[];
  foreign: string[];
  ok: string[];
}

export interface Deleted {
  deleted: string;
  url: string;
}

/** A non-2xx answer or an unreachable API; `status` 0 = network failure. */
export class AdminError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "AdminError";
  }
}

export interface AdminClient {
  listSnapshots(): Promise<SnapshotList>;
  deleteSnapshot(worker: string, confirm: string): Promise<Deleted>;
  prunePlan(): Promise<PrunePlan>;
}

type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

export function createAdminClient(fetchImpl: FetchLike = (u, i) => fetch(u, i), base = "/admin/api/"): AdminClient {
  async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
    const headers: Record<string, string> = { "X-KB-Admin": "1", Accept: "application/json" };
    const init: RequestInit = { method, credentials: "same-origin", headers };
    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(body);
    }
    let res: Response;
    try {
      res = await fetchImpl(base + path, init);
    } catch (e) {
      throw new AdminError(0, `Could not reach the admin API: ${e instanceof Error ? e.message : String(e)}`);
    }
    let data: unknown = null;
    try {
      data = await res.json();
    } catch {
      data = null;
    }
    if (!res.ok) {
      const err = (data as { error?: unknown } | null)?.error;
      throw new AdminError(res.status, typeof err === "string" ? err : `Admin API failed (HTTP ${res.status})`);
    }
    return data as T;
  }
  return {
    listSnapshots: () => call<SnapshotList>("GET", "snapshots"),
    deleteSnapshot: (worker, confirm) => call<Deleted>("DELETE", `snapshots/${encodeURIComponent(worker)}`, { confirm }),
    prunePlan: () => call<PrunePlan>("POST", "prune"),
  };
}

/** The one-line explanation of a failure, by the Worker's gate order (401, 403, 503). */
export function explain(e: unknown): { kind: "signed-out" | "forbidden" | "setup" | "error"; message: string } {
  if (!(e instanceof AdminError)) return { kind: "error", message: e instanceof Error ? e.message : String(e) };
  if (e.status === 401) return { kind: "signed-out", message: "Signed out. Reload the page to sign in again." };
  if (e.status === 403) return { kind: "forbidden", message: `This account cannot manage snapshots (${e.message}).` };
  if (e.status === 503) return { kind: "setup", message: e.message };
  return { kind: "error", message: e.message };
}
