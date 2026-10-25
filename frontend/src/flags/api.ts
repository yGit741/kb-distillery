/**
 * Flag reads/writes for the System → Flags tab. The local app asks its backend (PUT /api/flags/{name} with
 * the owner token from keychain item kb-flags-owner in `X-KB-Owner-Token`); the private site asks its Worker
 * (signed-in owner: session cookie + `X-KB-Admin: 1`; 503 while KV is not bound). A public snapshot has no
 * server and never writes. The token lives in this module only — never in localStorage/sessionStorage.
 */
import { SHARE_PROFILE } from "@/share/env";
import type { FlagName } from "./index";

let ownerToken: string | null = null;
export const getOwnerToken = (): string | null => ownerToken;
export const setOwnerToken = (t: string | null): void => {
  ownerToken = t || null;
};

export type Overrides = Partial<Record<FlagName, boolean>>;
export type FlagsRead = { overrides: Overrides };
export type FlagWrite = { ok: true; overrides: Overrides } | { ok: false; status: number; message: string };

export const OWNER_ONLY = "Only the owner can change flags (token from keychain item kb-flags-owner).";
export const KV_MISSING = "KV not configured: the private site has no FLAGS_KV namespace bound yet, so flags cannot be changed there.";

const defaultFetch: typeof fetch = (...a) => fetch(...a);

export async function readFlags(fetchImpl: typeof fetch = defaultFetch): Promise<FlagsRead> {
  if (SHARE_PROFILE === "public") return { overrides: {} };
  const res = await fetchImpl("/api/flags", { headers: { Accept: "application/json" }, cache: "no-store" });
  if (!res.ok) throw new Error(`GET /api/flags → ${res.status}`);
  const body = (await res.json()) as { overrides?: Overrides };
  return { overrides: body.overrides ?? {} };
}

export async function writeFlag(name: FlagName, value: boolean | null, fetchImpl: typeof fetch = defaultFetch): Promise<FlagWrite> {
  if (SHARE_PROFILE === "public") return { ok: false, status: 405, message: "Public snapshots are read-only." };
  const headers: Record<string, string> = { "Content-Type": "application/json", Accept: "application/json" };
  if (SHARE_PROFILE === "private") headers["X-KB-Admin"] = "1";
  else if (ownerToken) headers["X-KB-Owner-Token"] = ownerToken;
  let res: Response;
  try {
    res = await fetchImpl(`/api/flags/${encodeURIComponent(name)}`, { method: "PUT", headers, credentials: "same-origin", body: JSON.stringify({ value }) });
  } catch (e) {
    return { ok: false, status: 0, message: `Could not reach /api/flags: ${String(e)}` };
  }
  if (res.ok) {
    const body = (await res.json().catch(() => ({}))) as { overrides?: Overrides };
    return { ok: true, overrides: body.overrides ?? {} };
  }
  if (res.status === 401 || res.status === 403) {
    ownerToken = null; // a wrong token is asked for again on the next toggle
    const d = (await res.json().catch(() => null)) as { detail?: string; error?: string } | null;
    const why = d?.detail ?? d?.error;
    return { ok: false, status: res.status, message: why ? `${OWNER_ONLY} ${why}` : OWNER_ONLY };
  }
  if (res.status === 503) return { ok: false, status: 503, message: KV_MISSING };
  const detail = (await res.json().catch(() => null)) as { detail?: string; error?: string } | null;
  return { ok: false, status: res.status, message: detail?.detail ?? detail?.error ?? `PUT /api/flags/${name} failed (${res.status})` };
}
