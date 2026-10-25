/**
 * Fetch server-side overrides once at app start: the local app asks its backend (GET /api/flags, overrides
 * in meta/.ops/flags.json), the private site asks its Worker (GET /api/flags, overrides in KV). A public
 * snapshot is static — no server, built values only. Failure leaves the built values (fail-safe).
 */
import { SHARE_PROFILE } from "@/share/env";
import { setFlagOverrides, type FlagName } from "./index";

export async function loadFlagOverrides(fetchImpl: typeof fetch = (...a) => fetch(...a)): Promise<boolean> {
  if (SHARE_PROFILE === "public") return false;
  try {
    const res = await fetchImpl("/api/flags", { headers: { Accept: "application/json" }, cache: "no-store" });
    if (!res.ok) return false;
    const body = (await res.json()) as { overrides?: Partial<Record<FlagName, boolean>> };
    setFlagOverrides(body.overrides ?? {});
    return true;
  } catch {
    return false;
  }
}
