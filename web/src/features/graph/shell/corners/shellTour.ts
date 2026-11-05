import { useEffect } from "react";
import { flag } from "@/flags";
import { useFlag } from "@/flags/useFlag";
import { registerTour, runTour, seenTour, unregisterTour } from "@/features/tour/tours";
import type { TourStep } from "@/features/tour/tours";
import { IS_SHARE } from "@/share/env";
import { SHELL_LIST_ID } from "../SearchBar";
import { useChatFull } from "../chatFullStore";
import { useSparkPanel } from "../sparkPanelStore";

/** The tour's name: `?tour=graph-shell`, `kbTour.start("graph-shell")` and the Tours menu use it; `kb.tour.seen.graph-shell` remembers it. */
export const SHELL_TOUR = "graph-shell";

/** Tests switch the first-run start off (a dock over every shell test would be noise); the tour's own tests turn it on. */
export const shellTourAuto = { enabled: import.meta.env.MODE !== "test", delayMs: 900 };

const SEARCH = '[data-tour="graph-search"]';
const SHELL = '[data-testid="graph-shell"]';
/** the panel under the line; the steps that type into the line light it, with the line kept readable (dim) */
const PANEL = `#${SHELL_LIST_ID}`;
const present = (sel: string) => !!document.querySelector(sel);

/** Empty the search line and close its panel, so a step that typed an example leaves nothing behind. */
export function clearSearchLine(): void {
  const input = document.querySelector<HTMLInputElement>(SEARCH);
  if (!input || !input.value) return;
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set?.call(input, "");
  input.dispatchEvent(new Event("input", { bubbles: true }));
  input.blur();
}

const typeInto = (text: string) => [{ click: SEARCH }, { type: SEARCH, text }];

/**
 * The steps, for the controls that exist now: a snapshot has no chat and no local server, so its tour is the
 * search line and the page types only. One idea per step, spotlight on the real element.
 */
export function shellTourSteps(has: (selector: string) => boolean = present, share: boolean = IS_SHARE): TourStep[] {
  const steps: TourStep[] = [
    {
      go: "/graph",
      target: SHELL,
      pad: 6,
      title: "One line for everything",
      body: "Click the line or press **Cmd-K**. It finds pages, runs commands and takes questions.",
      place: "bottom",
      before: clearSearchLine,
    },
    {
      target: SHELL,
      pad: 6,
      title: "Find a page",
      body: "Type part of its name. Matching pages appear as you type; **Enter** centres the graph on one, **Shift-Enter** reads it.",
      place: "bottom",
      before: clearSearchLine,
    },
    {
      target: PANEL,
      pad: 4,
      dim: 0.4,
      do: typeInto("/"),
      title: "Commands start with a slash",
      body: "Type **/** for zoom, filters, layout, other knowledge bases and the other screens.",
      place: "right",
      keepFocus: true,
      before: clearSearchLine,
    },
  ];
  if (!share) {
    steps.push({
      target: PANEL,
      pad: 4,
      dim: 0.4,
      do: typeInto("How do these ideas connect"),
      title: "Anything else is a question",
      body: "**Ask the agent** sends your words to the chat, which opens beside the graph.",
      place: "right",
      keepFocus: true,
      before: clearSearchLine,
    });
  }
  steps.push({
    target: PANEL,
    pad: 4,
    dim: 0.4,
    do: typeInto("group by type; colour by degree"),
    title: "Describe how it should look",
    body: "Write what to show and how, such as **group by type** or **colour by degree**. A query that starts with MATCH ( runs as written.",
    place: "right",
    keepFocus: true,
    before: clearSearchLine,
  });
  const corners: [string, TourStep][] = [
    ['[data-tour="graph-views"]', { target: '[data-tour="graph-views"]', pad: 8, title: "Pinned views", body: "Pin the graph as it looks now and open it again from here.", place: "right" }],
    ['[data-tour="graph-think"]', { target: '[data-tour="graph-think"]', pad: 8, title: "Think notes", body: "Your own notes. Open one, or choose **New** to write down a thought.", place: "left" }],
    ['[data-tour="graph-agent"]', { target: '[data-tour="graph-agent"]', pad: 8, title: "Agent chats", body: "Earlier chats with the agent. Open one to continue it, or start a new one.", place: "right" }],
    ['[data-tour="graph-types"]', { target: '[data-tour="graph-types"]', pad: 8, title: "Page types", body: "Each mark is a type of page. Hover one to light it up in the graph, click to hide or show it.", place: "top" }],
  ];
  for (const [sel, step] of corners) if (has(sel)) steps.push({ ...step, before: clearSearchLine });
  return steps;
}

const SUMMARY = "The search line, the corner controls and the page types of the graph";

/** (Re)register the tour from the controls on screen now. */
export function registerShellTour(): void {
  registerTour(SHELL_TOUR, shellTourSteps(), SUMMARY, { onEnd: clearSearchLine });
}

const embedded = () => new URLSearchParams(window.location.search).get("embed") === "1" || window.top !== window;
const named = () => {
  const p = new URLSearchParams(window.location.search);
  // `chat` (flag chat-full): the address is on its way to the full chat, which the tour would cover
  return p.has("tour") || p.has("show") || p.has("chat");
};

/**
 * Called by the corner controls, so it exists only while flag graph-shell is on and the graph screen is open:
 * registers the tour for the Tours menu and `?tour=graph-shell`, and offers it once per browser. It does not
 * start in an embed, over another tour, or when a link names a tour of its own. `controls` names which controls
 * are drawn (it changes when the local server answers or the page types arrive), so the steps follow them.
 */
export function useShellTour(controls: string): void {
  const on = useFlag("graph-shell");
  useEffect(() => {
    if (!on) return;
    registerShellTour();
    let timer: ReturnType<typeof setTimeout> | undefined;
    if (shellTourAuto.enabled && !seenTour(SHELL_TOUR) && !embedded() && !named()) {
      timer = setTimeout(() => {
        if (document.querySelector(".gt-dock")) return;
        // flag chat-full: its steps point at the graph's controls, which the full chat covers: offer it later, never over the chat
        if (flag("chat-full") && useSparkPanel.getState().open && useChatFull.getState().full) return;
        registerShellTour();
        runTour(SHELL_TOUR);
      }, shellTourAuto.delayMs);
    }
    return () => {
      clearTimeout(timer);
      unregisterTour(SHELL_TOUR);
    };
  }, [on, controls]);
}
