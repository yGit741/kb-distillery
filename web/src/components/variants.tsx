import { useCallback, useSyncExternalStore } from "react";

/** One choice of a component that has several designs to try. `hint` is the one-line reason to pick it. */
export interface VariantOption {
  id: string;
  label: string;
  hint: string;
}

export interface VariantSpec {
  label: string;
  options: readonly VariantOption[];
  default: string;
}

/**
 * Every component that ships more than one design registers here; the chooser panel reads this list.
 * The choice is per browser, saved under `kbd.variants.<component>`.
 */
export const VARIANTS: Record<string, VariantSpec> = {
  "page-sources": {
    label: "Sources on a page",
    default: "footer",
    options: [
      { id: "footer", label: "Footer", hint: "A quiet Sources section after the page text; nothing moves while reading." },
      { id: "side-tab", label: "Side tab", hint: "A thin tab on the right edge that slides a panel over the page." },
      { id: "hover-marks", label: "Hover marks", hint: "A count in the header with a popover, plus a faint dot beside each section that cites a source." },
    ],
  },
};

const PREFIX = "kbd.variants.";
const listeners = new Set<() => void>();

function read(component: string): string | null {
  try {
    return localStorage.getItem(PREFIX + component);
  } catch {
    return null;
  }
}

/** The saved variant id of `component`, or `fallback` when none is saved or the saved id is no longer an option. */
export function getVariant(component: string, options: readonly string[], fallback: string): string {
  const v = read(component);
  return v && options.includes(v) ? v : fallback;
}

export function setVariant(component: string, id: string): void {
  try {
    localStorage.setItem(PREFIX + component, id);
  } catch {
    /* private window or blocked storage: the choice lasts until reload */
  }
  memory.set(component, id);
  listeners.forEach((l) => l());
}

const memory = new Map<string, string>();
const subscribe = (fn: () => void) => {
  listeners.add(fn);
  window.addEventListener("storage", fn);
  return () => {
    listeners.delete(fn);
    window.removeEventListener("storage", fn);
  };
};

/** `[variant, setVariant]` for a component: `useVariant("page-sources", ["footer", "side-tab"], "footer")`. */
export function useVariant(component: string, options: readonly string[], fallback: string): [string, (id: string) => void] {
  const snap = () => {
    const saved = read(component) ?? memory.get(component) ?? null;
    return saved && options.includes(saved) ? saved : fallback;
  };
  const value = useSyncExternalStore(subscribe, snap, () => fallback);
  const set = useCallback((id: string) => setVariant(component, id), [component]);
  return [value, set];
}
