import { clickUnlessOpen, registerTour } from "@/features/tour/tours";

const RAIL = 'nav[aria-label="Graph tools"]';
const PANEL = 'section[aria-label="Experiments"]';

registerTour("experiments", [
  { go: "/graph", target: `${RAIL} button[aria-label="Experiments"]`, title: "Experiments live here", body: "The flask opens prototypes you can try and judge. Switching one on never changes the graph for anyone else." },
  { target: PANEL, title: "The Experiments panel", body: "One card per prototype: its user story in plain text, then how to read the result.", before: clickUnlessOpen(`${RAIL} button[aria-label="Experiments"]`, PANEL) },
  { target: `${PANEL} p`, title: "Share a setup", body: "Switches are kept in this browser. Add ?exp=fourier,noise to a link to hand someone the same setup." },
  { target: `${PANEL} label:nth-of-type(1)`, title: "Theme spectrum", body: "Which themes appear together more, or less, than chance. Gaps point at big pairs that never meet." },
  { target: `${PANEL} label:nth-of-type(2)`, title: "Noise stability", body: "Does a cluster survive if some papers or links were missing? A halo marks pages that move." },
  { target: `${PANEL} label:nth-of-type(3)`, title: "Sharp thresholds", body: "At what link density a theme holds together, and which single link tips it." },
  { target: `${PANEL} label:nth-of-type(4)`, title: "Research directions", body: "Empty intersections of your vault as cards, to shortlist thesis directions with evidence." },
  { target: `${PANEL} label:nth-of-type(1) input`, title: "Switch one on", body: "Ticking the box adds that experiment's own button to the toolbar on the left.", pad: 8 },
]);
