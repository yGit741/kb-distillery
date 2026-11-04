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

/** The kb name a source suggests: a zip's stem, or the last part of a repository URL. */
function nameOf(source: ImportSource): string {
  if (source.kind === "zip") return source.file.name.replace(/\.zip$/i, "");
  return source.url.split("#")[0]!.replace(/\/+$/, "").split(/[/:]/).pop()!.replace(/\.git$/i, "");
}

/** import_kb's default id: lowercase letters, digits and dashes, at most 40 characters ("" when nothing is left). */
function slug(name: string): string {
  const s = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40).replace(/^-+|-+$/g, "");
  return /^[a-z0-9]/.test(s) ? s : "";
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
  if (res.status === 403) throw new Error(NOT_OWNER);
  throw new Error(typeof body?.error === "string" ? body.error : `The site's inbox answered ${res.status}.`);
}

/** Turns the Worker's report into what the dialog's preview step shows. */
function preview(source: ImportSource, r: Report): ImportPreview {
  const name = nameOf(source);
  const id = source.id || r.id || slug(name);
  const errors = [...(r.errors ?? [])];
  if (id && RESERVED.has(id)) errors.push(`The id "${id}" is reserved. Pick another one.`);
  if (r.ok === false && !errors.length) errors.push("The bundle has no pages.");
  return {
    id,
    name,
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
