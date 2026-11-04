import type { ImportAdapter, ImportPreview, ImportSource } from "./adapter";

/**
 * The deployed site: the dialog sends the bundle to the Worker's upload inbox (worker/inbox.js), which checks it with the
 * same checkBundle as the local import and parks it for the owner's Mac. Same-origin, session cookie, CSRF header
 * `X-KB-Admin: 1` (the Worker's ownerGate). Errors from the Worker are `{error}`.
 */
export const RECEIVED = "Received, it appears after your Mac's next sync";

type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

interface Report {
  ok?: boolean;
  id?: string;
  pages?: number;
  errors?: string[];
  warnings?: string[];
  error?: string;
}

const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40).replace(/^-+|-+$/g, "");
/** import_kb's display name for an id: "my-notes" -> "My notes". */
const display = (id: string) => (id ? id.replace(/-/g, " ").replace(/^./, (c) => c.toUpperCase()) : "");
const stem = (name: string) => name.replace(/\.zip$/i, "");
const repoName = (url: string) => url.split("#")[0]!.replace(/\/+$/, "").split(/[/:]/).pop()!.replace(/\.git$/, "");

function why(status: number, body: Report | null): string {
  if (status === 401) return "Signed out. Reload the page to sign in again.";
  if (status === 403) return "This account cannot add knowledge bases.";
  if (status === 413) return body?.error ?? "That upload is too large.";
  if (status === 503) return "The upload inbox is not set up on this site.";
  return body?.error ?? `The site answered ${status}.`;
}

export function createSiteImportAdapter(fetchImpl: FetchLike = (u, i) => fetch(u, i)): ImportAdapter {
  async function send(path: string, source: ImportSource): Promise<{ status: number; body: Report | null }> {
    const q = new URLSearchParams();
    if (source.kind === "zip" && source.id) q.set("id", source.id);
    const headers: Record<string, string> = { "X-KB-Admin": "1", Accept: "application/json" };
    const init: RequestInit = { method: "POST", credentials: "same-origin", cache: "no-store", headers };
    let url = path;
    if (source.kind === "zip") {
      q.set("name", stem(source.file.name));
      headers["Content-Type"] = "application/zip";
      init.body = source.file;
    } else {
      headers["Content-Type"] = "application/json";
      init.body = JSON.stringify({ git_url: source.url, id: source.id || undefined });
    }
    if (q.toString()) url += `?${q}`;
    let res: Response;
    try {
      res = await fetchImpl(url, init);
    } catch (e) {
      throw new Error(`Could not reach the site: ${e instanceof Error ? e.message : String(e)}`);
    }
    return { status: res.status, body: (await res.json().catch(() => null)) as Report | null };
  }

  return {
    validate: async (source) => {
      const { status, body } = await send("/api/inbox/validate", source);
      if (status !== 200 || !body) throw new Error(why(status, body));
      const id = source.id || body.id || (source.kind === "git" ? slug(repoName(source.url)) : "");
      const errors = [...(body.errors ?? [])];
      if (!errors.length && body.ok === false) errors.push("The bundle has no pages.");
      const preview: ImportPreview = {
        id,
        name: display(id),
        pages: body.pages ?? 0,
        source: source.kind === "zip" ? source.file.name : source.url,
        errors,
        warnings: body.warnings ?? [],
      };
      return preview;
    },
    submit: async (source) => {
      const { status, body } = await send("/api/inbox", source);
      if (status === 422 && body?.errors?.length) throw new Error(body.errors[0]);
      if (status !== 201) throw new Error(why(status, body));
      return { state: "received", message: RECEIVED };
    },
  };
}

/** A well-formed inbox item id that never exists: the probe below asks about it. */
const PROBE = "/api/inbox/00000000T000000Z-00000000";

/**
 * Is the signed-in viewer an owner of a site whose inbox is set up? The Worker has no whoami; its owner-gated routes answer
 * 401/403 to anyone who is not on ADMIN_EMAILS (or has no `X-KB-Admin`), then 503 when no R2 bucket is bound, and 404
 * ("no such inbox item") for an item that does not exist. So a 404 from this read-only probe means: owner, inbox ready.
 * Anything else (including a network failure or a host that is not the Worker) is a no.
 */
export async function probeInboxOwner(fetchImpl: FetchLike = (u, i) => fetch(u, i)): Promise<boolean> {
  try {
    const res = await fetchImpl(PROBE, { credentials: "same-origin", cache: "no-store", headers: { "X-KB-Admin": "1", Accept: "application/json" } });
    if (res.status !== 404) return false;
    const body = (await res.json().catch(() => null)) as Report | null;
    return /no such inbox item/.test(body?.error ?? "");
  } catch {
    return false;
  }
}
