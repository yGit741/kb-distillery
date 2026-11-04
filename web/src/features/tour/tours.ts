import { atLocation, startTour, type TourStep } from "./engine";

export type { Mark, MarkKind, TourAction } from "./engine";

export type { TourStep } from "./engine";

/**
 * The tour registry, shared by every feature and every build (the app, share snapshots). A feature registers
 * its tours at import time; anyone starts one with `?tour=<name>`, `kbTour.start("<name>")` or `runTour`.
 * A finished or skipped tour is remembered in this browser (`kb.tour.seen.<name>`).
 */
const TOURS = new Map<string, { steps: TourStep[]; summary: string; menu: boolean; onEnd?: () => void }>();

export interface TourInfo {
  name: string;
  /** one line: what the tour promises */
  summary: string;
  seen: boolean;
}

/**
 * `menu: false` keeps a tour startable (`?tour=`, `kbTour.start`) but out of the Tours menu. `onEnd` runs when
 * the tour ends for any reason (done, skipped, replaced): a place to undo what its steps typed or opened.
 */
export function registerTour(name: string, steps: TourStep[], summary = "", { menu = true, onEnd }: { menu?: boolean; onEnd?: () => void } = {}): void {
  TOURS.set(name, { steps, summary, menu, onEnd });
}

/** Remove a tour (a feature flag turned its feature off). A running tour keeps its own copy of the steps. */
export function unregisterTour(name: string): void {
  TOURS.delete(name);
}

const SEEN_KEY = (name: string) => `kb.tour.seen.${name}`;

export function seenTour(name: string): boolean {
  try {
    return globalThis.localStorage?.getItem(SEEN_KEY(name)) === "1";
  } catch {
    return false;
  }
}

export function markSeen(name: string): void {
  try {
    globalThis.localStorage?.setItem(SEEN_KEY(name), "1");
  } catch {
    // storage blocked: the tour may offer itself again next visit, which is harmless
  }
}

export function runTour(name: string): boolean {
  const t = TOURS.get(name);
  if (!t) return false;
  // finished or skipped counts as seen; a tour another one replaced does not
  startTour(t.steps, {
    onEnd: (reason) => {
      if (reason !== "replaced") markSeen(name);
      t.onEnd?.();
    },
  });
  return true;
}

/** The steps of a registered tour (empty when unknown); tours' own tests check their copy with it. */
export const stepsOf = (name: string): readonly TourStep[] => TOURS.get(name)?.steps ?? [];

export const listTours = ({ all = false }: { all?: boolean } = {}): TourInfo[] =>
  [...TOURS].filter(([, t]) => all || t.menu).map(([name, t]) => ({ name, summary: t.summary, seen: seenTour(name) }));

/** A step `before` helper: click a button by its aria-label unless the section it opens is already there. */
export function clickUnlessOpen(button: string, section: string) {
  return () => {
    if (document.querySelector(section)) return;
    (document.querySelector(button) as HTMLElement | null)?.click();
  };
}

/**
 * A show-me: a one-off tour an agent writes to explain something on the screen instead of in chat. It is data
 * (JSON, so `before` hooks are out; `do` actions replace them), travels in the link as `?show=<base64url>`, and
 * is never registered, listed or remembered — it works on any build that has the engine: localhost, the private
 * site, a snapshot. `pixi run show -- <file.json>` turns a file into links.
 */
export interface ShowScript {
  title: string;
  steps: TourStep[];
  /** ms per step to play by itself (a recording); omit to step with Next */
  autoplay?: number;
}

export const encodeShow = (script: ShowScript): string =>
  btoa(String.fromCharCode(...new TextEncoder().encode(JSON.stringify(script)))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

export function decodeShow(code: string): ShowScript | null {
  try {
    const bin = atob(code.replace(/-/g, "+").replace(/_/g, "/"));
    const s = JSON.parse(new TextDecoder().decode(Uint8Array.from(bin, (c) => c.charCodeAt(0)))) as ShowScript;
    return s && typeof s.title === "string" && Array.isArray(s.steps) && s.steps.length ? s : null;
  } catch {
    return null;
  }
}

const BASE_RE = new RegExp(`^${(import.meta.env.BASE_URL as string).replace(/\/$/, "")}`);

/**
 * Play a show-me. A link is untrusted, so it opens with a card that says it may press buttons and acts only
 * after a person presses Next (autoplay waits for that press too, see startTour).
 */
export function playShow(script: ShowScript): void {
  const here = window.location.pathname.replace(BASE_RE, "") + window.location.search.replace(/[?&]show=[^&]*/, "").replace(/^&/, "?");
  const intro: TourStep = { go: here || "/", title: script.title, body: "A walk-through from your agent. The next steps may press buttons or type for you — **Next** starts it, **Skip** stops it any time." };
  startTour([intro, ...script.steps], { autoplay: script.autoplay });
}
declare global {
  interface Window {
    kbTour?: { start: (name: string) => boolean; list: () => string[]; play: (script: ShowScript) => void; encode: (script: ShowScript) => string };
    /** installed by the router layer (app/providers): navigate to an app path + search, e.g. `/graph?view=thesis` */
    kbGo?: (path: string) => void;
  }
}

/** Start `name` once its feature has registered it (features register at import, screens load lazily). */
function startWhenRegistered(name: string, deadline = 10_000): void {
  const t0 = Date.now();
  const tick = () => {
    if (TOURS.has(name)) setTimeout(() => runTour(name), 600);
    else if (Date.now() - t0 < deadline) setTimeout(tick, 200);
  };
  tick();
}

/**
 * Called once at boot: exposes `kbTour`, starts the `?tour=` tour, and — on a build that names a tour
 * (share.toml `[home] tour`, baked as `KB_EMBEDDED.home.tour`) — offers that one on the first visit to Home.
 * Not when embedded (`?embed=1`, or inside a frame): an embed shows one screen, not the app.
 */
export function installTours(): void {
  window.kbTour = { start: runTour, list: () => [...TOURS.keys()], play: playShow, encode: encodeShow };
  const params = new URLSearchParams(window.location.search);
  const show = params.get("show");
  if (show) {
    const script = decodeShow(show);
    if (script) setTimeout(() => playShow(script), 600);   // let the screen mount first
    return;
  }
  const name = params.get("tour");
  if (name) return startWhenRegistered(name);
  const auto = globalThis.KB_EMBEDDED?.home?.tour;
  const embedded = params.get("embed") === "1" || window.top !== window;
  if (auto && !embedded && !seenTour(auto) && atLocation("/")) startWhenRegistered(auto);
}
