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
  "proposal-inbox": {
    label: "Proposal inbox",
    default: "by-page",
    options: [
      { id: "by-page", label: "By page", hint: "One section per page with its proposals inside; a proposal on three pages shows under each." },
      { id: "by-class", label: "By kind", hint: "Sections by what changed, claims first and typos last, so the risky ones are read first." },
      { id: "timeline", label: "Timeline", hint: "One flat list, newest first, with a chip per kind of change." },
    ],
  },
  "page-history-entry": {
    label: "Page history entry",
    default: "header",
    options: [
      { id: "header", label: "Header", hint: "A clock in the page header opens a right panel listing the versions, newest first." },
      { id: "timeline", label: "Timeline", hint: "A thin strip of dots under the title, one per version; hover reads it, click picks it." },
    ],
  },
  "proposal-diff": {
    label: "Proposal diff",
    default: "inline",
    options: [
      { id: "inline", label: "Inline", hint: "The page as it reads, changed words marked in place, controls in the right margin." },
      { id: "side-by-side", label: "Side by side", hint: "Before and after in two columns per block; unchanged paragraphs fold to one line." },
      { id: "reading", label: "Reading", hint: "The finished page, clean; a thin bar in the gutter opens a note with the old text and the controls." },
    ],
  },
  "restructure-entry": {
    label: "Restructure entry",
    default: "menu",
    options: [
      { id: "menu", label: "Menu", hint: "A quiet Restructure button in the page header opens a small menu: Merge into, Split, Extract." },
      { id: "command", label: "Commands", hint: "No button; type /merge @page, /split or /extract in the page chat, with the same @ picker." },
    ],
  },
  "ingest-layout": {
    label: "Ingest layout",
    default: "single",
    options: [
      { id: "single", label: "Single page", hint: "Drop zone, how deeply to read it, and the job card stacked on one page; everything stays in view." },
      { id: "wizard", label: "Wizard", hint: "Three steps shown one at a time: pick the source, say what it is, watch it progress." },
    ],
  },
  "page-flag-mark": {
    label: "Flagged span on a page",
    default: "underline",
    options: [
      { id: "underline", label: "Underline", hint: "A soft wavy underline in the warning hue under the flagged words; the note shows on hover." },
      { id: "margin", label: "Margin", hint: "A small flag in the left margin of the block; the text stays untouched and the note opens from the marker." },
      { id: "tint", label: "Tint", hint: "A light warm background on the flagged words; the note shows on hover." },
    ],
  },
  "page-chat-entry": {
    label: "Page chat entry",
    default: "selection",
    options: [
      { id: "selection", label: "Selection", hint: "Nothing shows until you select text; a small Ask about this toolbar appears there, plus a muted Chat link in the header." },
      { id: "bubble", label: "Bubble", hint: "A soft floating button bottom-right that opens the chat as a right drawer." },
      { id: "gutter", label: "Gutter", hint: "A thin icon in the right margin of the block under the pointer; click to ask about that block." },
      { id: "command", label: "Command bar", hint: "/ or Cmd+K on a page opens a bar to ask, mention a page or open the chat; a hint in the header." },
      { id: "rail", label: "Rail", hint: "A collapsed Discuss rail on the right edge that expands into the chat and remembers if it was open." },
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

/** The id saved for `component` in this browser, or null when it follows the default. */
export function savedVariant(component: string): string | null {
  return read(component) ?? memory.get(component) ?? null;
}

/** Forget the choice of `component`: it follows its registry default again (every open screen re-renders). */
export function resetVariant(component: string): void {
  try {
    localStorage.removeItem(PREFIX + component);
  } catch {
    /* blocked storage: nothing was saved there */
  }
  memory.delete(component);
  listeners.forEach((l) => l());
}

export function resetAllVariants(): void {
  Object.keys(VARIANTS).forEach(resetVariant);
}

/** The current choices as plain lines an agent can read, e.g. `page-sources: side-tab (default footer)`. */
export function variantChoicesText(): string {
  return Object.entries(VARIANTS)
    .map(([c, spec]) => {
      const now = getVariant(c, spec.options.map((o) => o.id), spec.default);
      return `${c}: ${now}${now === spec.default ? " (default)" : ` (default ${spec.default})`}`;
    })
    .join("\n");
}

/** `variantChoicesText()` that re-renders the caller whenever any choice changes. */
export function useVariantChoicesText(): string {
  return useSyncExternalStore(subscribe, variantChoicesText, variantChoicesText);
}
