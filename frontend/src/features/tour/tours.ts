import { atLocation, startTour, type TourStep } from "./engine";

export type { TourStep } from "./engine";

/**
 * The tour registry, shared by every feature and every build (the app, share snapshots). A feature registers
 * its tours at import time; anyone starts one with `?tour=<name>`, `kbTour.start("<name>")` or `runTour`.
 * A finished or skipped tour is remembered in this browser (`kb.tour.seen.<name>`).
 */
const TOURS = new Map<string, { steps: TourStep[]; summary: string }>();

export interface TourInfo {
  name: string;
  /** one line: what the tour promises */
  summary: string;
  seen: boolean;
}

export function registerTour(name: string, steps: TourStep[], summary = ""): void {
  TOURS.set(name, { steps, summary });
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
  startTour(t.steps, { onEnd: (reason) => reason !== "replaced" && markSeen(name) });
  return true;
}

/** The steps of a registered tour (empty when unknown); tours' own tests check their copy with it. */
export const stepsOf = (name: string): readonly TourStep[] => TOURS.get(name)?.steps ?? [];

export const listTours = (): TourInfo[] => [...TOURS].map(([name, t]) => ({ name, summary: t.summary, seen: seenTour(name) }));

/** A step `before` helper: click a button by its aria-label unless the section it opens is already there. */
export function clickUnlessOpen(button: string, section: string) {
  return () => {
    if (document.querySelector(section)) return;
    (document.querySelector(button) as HTMLElement | null)?.click();
  };
}

declare global {
  interface Window {
    kbTour?: { start: (name: string) => boolean; list: () => string[] };
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
  window.kbTour = { start: runTour, list: () => [...TOURS.keys()] };
  const params = new URLSearchParams(window.location.search);
  const name = params.get("tour");
  if (name) return startWhenRegistered(name);
  const auto = globalThis.KB_EMBEDDED?.home?.tour;
  const embedded = params.get("embed") === "1" || window.top !== window;
  if (auto && !embedded && !seenTour(auto) && atLocation("/")) startWhenRegistered(auto);
}
