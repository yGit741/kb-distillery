import { useEffect } from "react";
import { useHeaderFold } from "@/app/headerFold";
import { useFlag } from "@/flags/useFlag";
import { registerTour, unregisterTour } from "@/features/tour/tours";
import type { TourStep } from "@/features/tour/tours";
import { useCorners } from "./cornersStore";

/** The tour's name in the Tours menu, `?tour=graph-views` and `kbTour.start("graph-views")`. */
export const VIEWS_TOUR = "graph-views";

const SUMMARY = "The views that hang from the pin, Sources as the way into Health, the folds and the theme switch";

const LEGEND = '[data-corners="legend"]';
const LOOP = '[data-corners="pin-loop"]';
const TYPES = '[data-corners="types"]';
const SOURCES = '[data-view="view:sources"]';
const PIN = 'button[aria-label="Pinned views"]';
const DIAL = '[aria-label="Sources by kind"]';
const CHEVRON = '[data-testid="header-fold-button"]';
const THEME = 'header button[aria-label^="Switch to"]';

/** Open a corner layer the tour points at, without remembering it as the person's own choice. */
const openLayer = (l: "pins" | "legend" | "types") => () => {
  const c = useCorners.getState();
  if (!c.has(l)) c.toggle(l, { remember: false });
};

/**
 * The app bar's fold before the tour pressed the chevron, put back when the tour ends. State of one run only:
 * every end (done, skipped, replaced) clears it.
 */
let barWas: boolean | null = null;

/**
 * The chevron step acts out a press that brings the bar back, so the bar starts folded. Folded in the store only,
 * not saved: a reload on this step keeps the person's own choice.
 */
function foldBarFirst(): void {
  const { folded } = useHeaderFold.getState();
  if (barWas === null) barWas = folded;
  if (!folded) useHeaderFold.setState({ folded: true });
}

function restoreBar(): void {
  if (barWas !== null && useHeaderFold.getState().folded !== barWas) useHeaderFold.getState().set(barWas);
  barWas = null;
}

/**
 * The steps, for what this build draws: `health` when Sources opens Health (its dial of source kinds), `fold` when the
 * app bar folds under the graph's chevron. One idea per step, spotlight on the real element.
 */
export function viewsTourSteps({ health, fold }: { health: boolean; fold: boolean }): TourStep[] {
  const steps: TourStep[] = [
    {
      go: "/graph",
      target: LEGEND,
      kind: "focus",
      dim: 0.35,
      title: "The graph opens on Concepts",
      body: "Every visit starts on your concepts coloured by **theme**. The legend says what each colour is.",
      before: openLayer("legend"),
    },
    {
      target: LOOP,
      kind: "focus",
      title: "Your views hang from the pin",
      body: "Concepts and Sources come first, then Citations and **Semantics** when the knowledge base has them, your pinned views and the placeholders V1 to V3.",
      before: openLayer("pins"),
      wait: 3000,
    },
    {
      target: LOOP,
      kind: "focus",
      dim: 0.35,
      title: "Both ends fade",
      body: "Two cards fade out below and two tilt above the pin. Press a faded card, or use the **wheel**, to turn the loop.",
      before: openLayer("pins"),
    },
  ];
  if (health)
    steps.push({
      // picking a card leaves the loop open over the dial: the pin folds it away, as a person would
      do: [{ click: SOURCES }, { wait: 600 }, { click: PIN }, { wait: 900 }],
      target: DIAL,
      kind: "focus",
      dim: 0.3,
      title: "Sources opens Health",
      body: "For now **Sources** is the way into Health: concepts coloured by how many sources back them, and this dial of source kinds. Press a kind to draw it on the map with the concepts it feeds.",
      before: openLayer("pins"),
      wait: 3000,
    });
  steps.push({
    target: TYPES,
    kind: "focus",
    dim: 0.4,
    title: "One fold, everywhere",
    body: "The page types card folds with the same small dot [1] as the colour legend.",
    marks: [{ target: '[data-fold="dot"]', kind: "focus", label: "fold" }],
    before: openLayer("types"),
  });
  if (fold)
    steps.push({
      do: [{ click: CHEVRON }, { wait: 500 }],
      target: CHEVRON,
      kind: "focus",
      title: "The bar folds from one spot",
      body: "The chevron stays put, folded or open, so a second press undoes the first. The theme switch [1] sits in the bar, right of Tours.",
      marks: [{ target: THEME, kind: "focus", label: "theme" }],
      before: foldBarFirst,
    });
  else
    steps.push({
      target: THEME,
      kind: "focus",
      title: "Light or dark",
      body: "The theme switch sits in the bar, right of **Tours**.",
    });
  return steps;
}

/**
 * Called by the corner controls under flag graph-corners: registers the tour for the Tours menu while the graph is
 * open. It never starts by itself.
 */
export function useViewsTour(on: boolean, health: boolean): void {
  const headerFold = useFlag("header-fold");
  const shell = useFlag("graph-shell");
  const fold = headerFold && shell;
  useEffect(() => {
    if (!on) return;
    registerTour(VIEWS_TOUR, viewsTourSteps({ health, fold }), SUMMARY, { onEnd: restoreBar });
    return () => unregisterTour(VIEWS_TOUR);
  }, [on, health, fold]);
}
