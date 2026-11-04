/**
 * The corner controls' own small client for the three server lists they show: pinned views (`/api/views`),
 * recent shaping steps (`/api/recent`) and saved chat sessions (`/api/sessions`, from a parallel PR: a 404 means
 * "not on this server" and the browser-held chat stands in). Plain `fetch` with an injectable implementation, so
 * tests mock it; the shared DataSource is not touched here (other lanes extend it).
 */
export type Fetcher = typeof fetch;
export const defaultFetch: Fetcher = (...a) => fetch(...a);

export interface PinnedView {
  id: string;
  name: string;
  created: string;
  spec: Record<string, unknown>;
}
export interface RecentStep {
  at: string;
  text: string;
  spec: Record<string, unknown>;
}
export interface SessionRow {
  id: string;
  title: string;
  /** ISO time of the last turn, when the server says */
  updated?: string;
  live?: boolean;
}

export class ApiFailure extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function call(f: Fetcher, url: string, init?: RequestInit): Promise<unknown> {
  let res: Response;
  try {
    res = await f(url, { cache: "no-store", ...init, headers: { Accept: "application/json", ...(init?.body ? { "Content-Type": "application/json" } : {}) } });
  } catch (e) {
    throw new ApiFailure(`Could not reach ${url}: ${e instanceof Error ? e.message : String(e)}`, 0);
  }
  const body: unknown = await res.json().catch(() => undefined);
  if (!res.ok) {
    const why = body && typeof body === "object" ? ((body as { error?: unknown }).error ?? (body as { detail?: unknown }).detail) : undefined;
    throw new ApiFailure(typeof why === "string" ? why : `${url} answered ${res.status}`, res.status);
  }
  return body;
}

export async function listViews(f: Fetcher = defaultFetch): Promise<PinnedView[]> {
  const b = (await call(f, "/api/views")) as { views?: PinnedView[] };
  return b.views ?? [];
}
export const pinView = (f: Fetcher, name: string, spec: Record<string, unknown>) =>
  call(f, "/api/views", { method: "POST", body: JSON.stringify({ name, spec }) }) as Promise<{ view?: PinnedView }>;
export const renameView = (f: Fetcher, id: string, name: string) =>
  call(f, `/api/views/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify({ name }) });
export const unpinView = (f: Fetcher, id: string) => call(f, `/api/views/${encodeURIComponent(id)}`, { method: "DELETE" });

/** The server keeps them oldest first; the list shows the newest first. */
export async function listRecent(f: Fetcher = defaultFetch): Promise<RecentStep[]> {
  const b = (await call(f, "/api/recent")) as { recent?: RecentStep[] };
  return [...(b.recent ?? [])].reverse();
}

/** Saved chats, newest first; null when this server has no session store (404). */
export async function listSessions(f: Fetcher = defaultFetch): Promise<SessionRow[] | null> {
  try {
    const b = (await call(f, "/api/sessions")) as { sessions?: Record<string, unknown>[] };
    return (b.sessions ?? []).map((s) => ({
      id: String(s.id),
      title: String(s.title || "Untitled chat"),
      updated: typeof s.updated === "string" ? s.updated : typeof s.created === "string" ? s.created : undefined,
    }));
  } catch (e) {
    if (e instanceof ApiFailure && (e.status === 404 || e.status === 405)) return null;
    throw e;
  }
}

export async function getSession(f: Fetcher, id: string): Promise<{ id: string; messages: unknown[] }> {
  return (await call(f, `/api/sessions/${encodeURIComponent(id)}`)) as { id: string; messages: unknown[] };
}

/** "today", "3 d ago": the time a row shows on its right. */
export function ago(iso: string | undefined, now = Date.now()): string {
  const t = iso ? Date.parse(iso) : NaN;
  if (Number.isNaN(t)) return "";
  const s = Math.max(0, (now - t) / 1000);
  if (s < 90) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  if (s < 86400 * 2) return "yesterday";
  if (s < 86400 * 30) return `${Math.round(s / 86400)} d ago`;
  return new Date(t).toISOString().slice(0, 10);
}
