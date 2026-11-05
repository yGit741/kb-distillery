import { registerTour } from "@/features/tour/tours";
import { clearSearchLine } from "./shell/corners/shellTour";
import { useGraphUi } from "./store";

const SEARCH = '[data-tour="graph-search"]';
const SHELL = '[data-testid="graph-shell"]';
const PANEL = 'section[aria-label="Experiments"]';

/** Open the Experiments panel the way the line's command does. */
const openExperiments = () => {
  clearSearchLine();
  useGraphUi.setState({ railOpen: false, flyout: "experiments" });
};

registerTour("experiments", [
  {
    go: "/graph",
    target: SHELL,
    pad: 6,
    title: "Experiments start in the line",
    body: "Type **/experiments** in the search line to open the prototypes you can try and judge. Switching one on never changes the graph for anyone else.",
    place: "bottom",
    do: [{ click: SEARCH }, { type: SEARCH, text: "/experiments" }],
    keepFocus: true,
    before: clearSearchLine,
  },
  { target: PANEL, title: "The Experiments panel", body: "One card per prototype: its user story in plain text, then how to read the result.", before: openExperiments },
  { target: `${PANEL} p`, title: "Share a setup", body: "Switches are kept in this browser. Add ?exp=fourier,noise to a link to hand someone the same setup." },
  { target: `${PANEL} label:nth-of-type(1)`, title: "Theme spectrum", body: "Which themes appear together more, or less, than chance. Gaps point at big pairs that never meet." },
  { target: `${PANEL} label:nth-of-type(2)`, title: "Noise stability", body: "Does a cluster survive if some papers or links were missing? A halo marks pages that move." },
  { target: `${PANEL} label:nth-of-type(3)`, title: "Sharp thresholds", body: "At what link density a theme holds together, and which single link tips it." },
  { target: `${PANEL} label:nth-of-type(4)`, title: "Research directions", body: "Empty intersections of your vault as cards, to shortlist thesis directions with evidence." },
  { target: `${PANEL} label:nth-of-type(1) input`, title: "Switch one on", body: "Ticking the box adds that experiment's own command to the line: type a slash and its name.", pad: 8 },
]);
