/**
 * Flag test matrix (vitest): `withFlag(name, on, fn)` runs `fn` with flag `name` forced on/off — build flags
 * too (test-only seam) — and restores it afterwards, also for async `fn`. `python -m kb_distillery.config.flags.coverage` scans
 * *.test.ts(x) for `withFlag("<name>", true|false` and needs both states for every flag in meta/flags.toml.
 */
import { afterEach, beforeEach } from "vitest";
import { setTestFlagOverrides, type FlagName } from "./index";

const forced: Partial<Record<FlagName, boolean>> = {};

export function withFlag<T>(name: FlagName, on: boolean, fn: () => T): T {
  const had = name in forced;
  const old = forced[name];
  forced[name] = on;
  setTestFlagOverrides(forced);
  const restore = () => {
    if (had) forced[name] = old;
    else delete forced[name];
    setTestFlagOverrides(forced);
  };
  let out: T;
  try {
    out = fn();
  } catch (e) {
    restore();
    throw e;
  }
  if (out instanceof Promise) return out.finally(restore) as T;
  restore();
  return out;
}

/**
 * Pin a flag for every test in the enclosing file or describe block (vitest beforeEach/afterEach), for suites written
 * against one state. Each flag still needs `withFlag(name, true)` and `withFlag(name, false)` somewhere for coverage.
 */
export function pinFlag(name: FlagName, on: boolean): void {
  let had = false;
  let old: boolean | undefined;
  beforeEach(() => {
    had = name in forced;
    old = forced[name];
    forced[name] = on;
    setTestFlagOverrides(forced);
  });
  afterEach(() => {
    if (had) forced[name] = old;
    else delete forced[name];
    setTestFlagOverrides(forced);
  });
}
