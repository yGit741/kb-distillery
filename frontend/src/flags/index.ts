/**
 * Feature flags: `flag(name)` is the value of a flag from meta/flags.toml (generated into registry.gen.ts)
 * for the env this bundle runs in — the local app is "local", a share build is its SHARE_PROFILE.
 *
 * Kinds: `build` flags are fixed per bundle (a `screen.*` flag also decides which screens a share build
 * imports, see routes/modules.share-*.ts); `runtime` flags may be overridden at run time. The override seam
 * (`setFlagOverrides`) is fed by `loadFlagOverrides()` (load.ts) from GET /api/flags and ignores build
 * flags; `useFlag(name)` (useFlag.ts) re-renders when it changes.
 */
import { SHARE_PROFILE } from "@/share/env";
import { FLAGS, FLAG_NAMES, type FlagEnv, type FlagMeta, type FlagName } from "./registry.gen";

export { FLAGS, FLAG_NAMES };
export type { FlagEnv, FlagMeta, FlagName };

export const FLAG_ENV: FlagEnv = SHARE_PROFILE ?? "local";

let overrides: Partial<Record<FlagName, boolean>> = {};
let version = 0;
const listeners = new Set<() => void>();

/** Subscribe to override changes (useFlag re-renders through this). Returns the unsubscribe. */
export function subscribeFlags(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

/** Bumps on every setFlagOverrides call (the external-store snapshot). */
export function flagsVersion(): number {
  return version;
}

/** G2 seam: install server-side overrides. Only runtime flags take them; build flags stay as built. */
export function setFlagOverrides(next: Partial<Record<FlagName, boolean>>): void {
  overrides = {};
  for (const [name, v] of Object.entries(next) as [FlagName, boolean][]) {
    if (FLAGS[name]?.kind === "runtime" && typeof v === "boolean") overrides[name] = v;
  }
  version += 1;
  for (const fn of listeners) fn();
}

/** Build-time value of `name` in `env` (no overrides). */
export function flagIn(name: FlagName, env: FlagEnv): boolean {
  const meta = FLAGS[name];
  return meta ? (meta.envs[env] ?? meta.default) : false;
}

export function flag(name: FlagName): boolean {
  return overrides[name] ?? flagIn(name, FLAG_ENV);
}
