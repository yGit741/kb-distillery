/**
 * Guided tours for share builds. A tour is a short list of steps, each pointing at an element marked
 * `data-tour="<anchor>"` (Home cards, the graph search, the legend, the reader). The build picks one by id
 * in share.toml `[home] tour = "<id>"`; no id, or an id missing here, means no tour.
 *
 * No tour is written yet: this file is the registry the first one goes into.
 */
export interface TourStep {
  /** `data-tour` value of the element to point at; the step is skipped when it is not on the page. */
  anchor: string;
  title: string;
  body: string;
  /** App path the step belongs to (the tour navigates there first), e.g. "/graph". */
  route?: string;
}

export const TOURS: Record<string, readonly TourStep[]> = {};

/** Anchors the app already exposes, for tour authors. */
export const ANCHORS = ["home-card-random", "home-card-bridge", "home-node-idea", "graph-search", "graph-legend", "page-reader"] as const;

const SEEN_KEY = (id: string) => `kb.tour.seen.${id}`;

export function seen(id: string): boolean {
  try {
    return globalThis.localStorage?.getItem(SEEN_KEY(id)) === "1";
  } catch {
    return false;
  }
}

export function markSeen(id: string): void {
  try {
    globalThis.localStorage?.setItem(SEEN_KEY(id), "1");
  } catch {
    // storage blocked: the tour shows again next visit, which is harmless
  }
}

/** The steps to run now: the build's tour, unless it is unknown, empty or already seen. */
export function activeTour(id: string | null | undefined, tours: Record<string, readonly TourStep[]> = TOURS): readonly TourStep[] {
  if (!id) return [];
  const steps = tours[id];
  return steps?.length && !seen(id) ? steps : [];
}
