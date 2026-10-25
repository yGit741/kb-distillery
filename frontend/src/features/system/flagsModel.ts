import { FLAGS, FLAG_NAMES, flagIn, type FlagEnv, type FlagMeta, type FlagName } from "@/flags";
import type { Tone } from "./model";

export const EXPIRY_WARN_DAYS = 14;
const DAY = 86_400_000;

export type FlagRow = FlagMeta & {
  name: FlagName;
  ageDays: number | null;
  expiresInDays: number | null;
  expiryTone: Tone;
  value: boolean;
  registryValue: boolean;
  source: "registry" | "override";
};

const dayOf = (iso: string) => {
  const t = Date.parse(`${iso}T00:00:00Z`);
  return Number.isNaN(t) ? null : t;
};

/** One row per registry flag: age, expiry tone (warn ≤ 14 days, bad once past) and the effective value in `env`. */
export function flagRows(env: FlagEnv, overrides: Partial<Record<FlagName, boolean>>, now: Date = new Date()): FlagRow[] {
  const today = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  return FLAG_NAMES.map((name) => {
    const meta = FLAGS[name];
    const created = dayOf(meta.created);
    const expires = dayOf(meta.expires);
    const expiresInDays = expires === null ? null : Math.round((expires - today) / DAY);
    const expiryTone: Tone = expiresInDays === null ? "" : expiresInDays < 0 ? "bad" : expiresInDays <= EXPIRY_WARN_DAYS ? "warn" : "";
    const ov = meta.kind === "runtime" ? overrides[name] : undefined;
    return {
      ...meta,
      name,
      ageDays: created === null ? null : Math.round((today - created) / DAY),
      expiresInDays,
      expiryTone,
      value: ov ?? flagIn(name, env),
      registryValue: flagIn(name, env),
      source: ov === undefined ? "registry" : "override",
    };
  });
}
