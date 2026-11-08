import { flag } from "@/flags";
import { useFlag } from "@/flags/useFlag";
import { IS_SHARE } from "@/share/env";

/**
 * What the graph line may do (flag graph-intent), decided in ONE place from the build (share or app) and the flag.
 * The line, the action menu, the corners, the gallery and the stores read this table instead of asking IS_SHARE
 * themselves. A shared site is read-only: it keeps the reading half of the line (search, saved and ready views,
 * focus, the favorite mark) and has nothing that writes, asks a model or opens a chat.
 */
export interface Capabilities {
  /** Saved and ready views can be listed and applied (gallery, `/views`, the pin corner). */
  readViews: boolean;
  /** `>` sentences: change the view by writing a line. */
  sentences: boolean;
  /** Any call to a model: the `>` fallback, shaping, related-by-meaning. */
  llm: boolean;
  /** Pin, rename or unpin a view. */
  saveViews: boolean;
  /** The favorite toggle (the mark itself is always shown). */
  favoriteToggle: boolean;
  /** The favorite mark and the favorites list. */
  favoriteMark: boolean;
  /** Recent steps are read and written. */
  recentSteps: boolean;
  /** The agent chat: the "Chat" action and the Ask row. */
  chat: boolean;
  /** The Ask row in the search panel. */
  ask: boolean;
  /** The "Think" action. */
  think: boolean;
  /** Search tier 2 (the server's text search) and the Related-by-meaning group. */
  serverSearch: boolean;
  /** Free text turned into a graph view by the server. */
  shape: boolean;
  /** `## My notes` of a page travels in an OKF export. */
  exportNotes: boolean;
}

/** The table. `share` is the build; `intent` is the graph-intent flag. */
export function capabilitiesFor(share: boolean, intent: boolean): Capabilities {
  return {
    readViews: intent,
    sentences: intent && !share,
    llm: !share,
    saveViews: !share,
    favoriteToggle: !share,
    favoriteMark: true,
    recentSteps: !share,
    chat: !share,
    ask: !share,
    think: !share,
    serverSearch: !share,
    shape: !share,
    exportNotes: !share,
  };
}

/** For render code: re-renders when the flag changes. */
export function useCapabilities(): Capabilities {
  return capabilitiesFor(IS_SHARE, useFlag("graph-intent"));
}

/** For code that is not a component (menu items, stores). */
export function capabilities(): Capabilities {
  return capabilitiesFor(IS_SHARE, flag("graph-intent"));
}
