import { displayName, sourceStem, suggestId } from "@/lib/okf/names";
import type { ImportAdapter, ImportOutcome, ImportPreview, ImportSource } from "./adapter";

/**
 * The deployed private site: the Worker's upload inbox (`POST /api/inbox/validate`, `POST /api/inbox`). It checks the
 * bundle with the same checker as the app and parks it for the owner's Mac; nothing is imported here, so a successful
 * submit is `received`, not `imported`. Writes need the owner's session cookie, the `X-KB-Admin` header and a
 * same-origin request (the Worker's `ownerGate`); anyone else gets a 401 or 403, which is shown as a plain sentence.
 */

const VALIDATE = "/api/inbox/validate";
const CREATE = "/api/inbox";
const RESERVED = new Set(["think", "demo"]);
const RECEIVED = "Your bundle is in the inbox. It appears after your Mac's next sync.";
const SIGNED_OUT = "Your sign-in has expired. Reload the page, sign in again, then retry.";
const NOT_OWNER = "Only the site owner can add knowledge bases here.";

/** The Worker's answer: the checker report (validate, create) plus the inbox item id (create). */
interface Report {
  ok?: boolean;
  kind?: string;
  id?: string;
  pages?: number;
  errors?: string[];
  warnings?: string[];
  item?: string;
}

/** The name the Worker derives the id from: a zip's own file name (it drops the extension), or the last part of a repository URL. */
function nameOf(source: ImportSource): string {
  if (source.kind === "zip") return source.file.name;
  return source.url.split("#")[0]!.replace(/\/+$/, "").split(/[/:]/).pop()!.replace(/\.git$/i, "");
}

function request(path: string, source: ImportSource): [string, RequestInit] {
  const headers: Record<string, string> = { Accept: "application/json", "X-KB-Admin": "1" };
  const init: RequestInit = { method: "POST", cache: "no-store", credentials: "same-origin", headers };
  if (source.kind === "zip") {
    const q = new URLSearchParams({ name: nameOf(source) });
    if (source.id) q.set("id", source.id);
    headers["Content-Type"] = "application/zip";
    return [`${path}?${q}`, { ...init, body: source.file }];
  }
  headers["Content-Type"] = "application/json";
  return [path, { ...init, body: JSON.stringify({ git_url: source.url, ...(source.id ? { id: source.id } : {}) }) }];
}

async function post(fetchImpl: typeof fetch, path: string, source: ImportSource): Promise<Report> {
  const [url, init] = request(path, source);
  let res: Response;
  try {
    res = await fetchImpl(url, init);
  } catch (e) {
    throw new Error(`Could not reach the site's inbox: ${e instanceof Error ? e.message : String(e)}`);
  }
  const body = (await res.json().catch(() => null)) as (Report & { error?: unknown }) | null;
  if (res.ok) {
    if (!body) throw new Error("The site's inbox did not answer with JSON.");
    return body;
  }
  if (res.status === 401) throw new Error(SIGNED_OUT);
  if (res.status === 403) {
    // "not an admin" is the plain case; the other 403s (header, origin) say what the Worker refused
    const why = typeof body?.error === "string" && body.error !== "not an admin" && body.error !== "not allowed" ? ` (${body.error})` : "";
    throw new Error(NOT_OWNER + why);
  }
  throw new Error(typeof body?.error === "string" ? body.error : `The site's inbox answered ${res.status}.`);
}

/** Turns the Worker's report into what the dialog's preview step shows. */
function preview(source: ImportSource, r: Report): ImportPreview {
  const id = source.id || r.id || suggestId(source.kind === "zip" ? sourceStem(nameOf(source)) : nameOf(source));
  const errors = [...(r.errors ?? [])];
  if (id && RESERVED.has(id)) errors.push(`The id "${id}" is reserved. Pick another one.`);
  if (r.ok === false && !errors.length) errors.push("The bundle has no pages.");
  return {
    id,
    name: displayName(id),                          // the local app's rule: the id with spaces, first letter capital
    pages: r.pages ?? 0,
    source: source.kind === "zip" ? source.file.name : source.url,
    errors,
    warnings: r.warnings ?? [],
  };
}

export function createSiteImportAdapter(fetchImpl: typeof fetch = (...a) => fetch(...a)): ImportAdapter {
  return {
    validate: async (source) => preview(source, await post(fetchImpl, VALIDATE, source)),
    submit: async (source): Promise<ImportOutcome> => {
      const r = await post(fetchImpl, CREATE, source);
      return { state: "received", message: RECEIVED, ref: r.item };
    },
  };
}

/**
 * Is the signed-in viewer an owner of a site whose inbox is set up? `GET /api/inbox/access` answers 200 `{owner, inbox}`
 * to any signed-in viewer (owner = the Worker's ownerGate allowlist, inbox = the R2 bucket is bound), so the entry is
 * offered only to an owner, only where the inbox works, and nobody's page load logs an error. Anything else (another
 * status, a network failure, a host that is not the Worker) is a no.
 */
export async function inboxAccess(fetchImpl: typeof fetch = (...a) => fetch(...a)): Promise<boolean> {
  try {
    const res = await fetchImpl("/api/inbox/access", { credentials: "same-origin", cache: "no-store", headers: { Accept: "application/json" } });
    if (res.status !== 200) return false;
    const body = (await res.json().catch(() => null)) as { owner?: unknown; inbox?: unknown } | null;
    return body?.owner === true && body?.inbox === true;
  } catch {
    return false;
  }
}
