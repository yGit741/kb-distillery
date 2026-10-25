import { useSyncExternalStore } from "react";
import { flag, flagsVersion, subscribeFlags, type FlagName } from "./index";

/** `flag(name)` as a hook: re-renders when server-side overrides arrive or change. */
export function useFlag(name: FlagName): boolean {
  useSyncExternalStore(subscribeFlags, flagsVersion, flagsVersion);
  return flag(name);
}
