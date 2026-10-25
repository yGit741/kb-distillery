import { startTour, type TourStep } from "./engine";

export type { TourStep } from "./engine";

/**
 * The tour registry, shared by every feature and every build (the app, share snapshots). A feature registers
 * its tours at import time; anyone starts one with `?tour=<name>`, `kbTour.start("<name>")` or `runTour`.
 */
const TOURS = new Map<string, TourStep[]>();

export function registerTour(name: string, steps: TourStep[]): void {
  TOURS.set(name, steps);
}

export function runTour(name: string): boolean {
  const steps = TOURS.get(name);
  if (!steps) return false;
  startTour(steps);
  return true;
}

export const listTours = (): string[] => [...TOURS.keys()];

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
  }
}

/** Called once at boot: exposes `kbTour` and starts the `?tour=` tour once its feature has registered it. */
export function installTours(): void {
  window.kbTour = { start: runTour, list: listTours };
  const name = new URLSearchParams(window.location.search).get("tour");
  if (!name) return;
  const t0 = Date.now();
  const tick = () => {
    if (TOURS.has(name)) setTimeout(() => runTour(name), 600);
    else if (Date.now() - t0 < 10_000) setTimeout(tick, 200);
  };
  tick();
}
