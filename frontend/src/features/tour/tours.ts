import { startTour, type TourStep } from "./engine";

const RAIL = 'nav[aria-label="Graph tools"]';
const PANEL = 'section[aria-label="Experiments"]';

/** Click a toolbar button unless its panel is already open. */
function openPanel(label: string) {
  return () => {
    if (document.querySelector(`section[aria-label="${label}"]`)) return;
    (document.querySelector(`${RAIL} button[aria-label="${label}"]`) as HTMLElement | null)?.click();
  };
}

/** Tours over the real app, by name. Start one with `?tour=<name>` or `kbTour.start("<name>")`. */
export const TOURS: Record<string, TourStep[]> = {
  experiments: [
    { target: `${RAIL} button[aria-label="Experiments"]`, title: "Experiments live here", body: "The flask opens prototypes you can try and judge. Switching one on never changes the graph for anyone else." },
    { target: PANEL, title: "The Experiments panel", body: "One card per prototype: its user story in plain text, then how to read the result.", before: openPanel("Experiments") },
    { target: `${PANEL} p`, title: "Share a setup", body: "Switches are kept in this browser. Add ?exp=fourier,noise to a link to hand someone the same setup.", place: "right" },
    { target: `${PANEL} label:nth-of-type(1)`, title: "Theme spectrum", body: "Which themes appear together more, or less, than chance. Gaps point at big pairs that never meet." },
    { target: `${PANEL} label:nth-of-type(2)`, title: "Noise stability", body: "Does a cluster survive if some papers or links were missing? A halo marks pages that move." },
    { target: `${PANEL} label:nth-of-type(3)`, title: "Sharp thresholds", body: "At what link density a theme holds together, and which single link tips it." },
    { target: `${PANEL} label:nth-of-type(4)`, title: "Research directions", body: "Empty intersections of your vault as cards, to shortlist thesis directions with evidence." },
    { target: `${PANEL} label:nth-of-type(1) input`, title: "Switch one on", body: "Ticking the box adds that experiment's own button to the toolbar on the left.", pad: 8 },
  ],
};

export function runTour(name: string): boolean {
  const steps = TOURS[name];
  if (!steps) return false;
  startTour(steps);
  return true;
}

declare global {
  interface Window {
    kbTour?: { start: (name: string) => boolean; list: () => string[] };
  }
}

/** Expose the tours on window and start the one named in `?tour=` once the screen has drawn. */
export function installTours(): void {
  window.kbTour = { start: runTour, list: () => Object.keys(TOURS) };
  const name = new URLSearchParams(window.location.search).get("tour");
  if (name) setTimeout(() => runTour(name), 900);
}
