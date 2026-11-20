import { flag, subscribeFlags } from "@/flags";
import { registerTour, unregisterTour, type TourStep } from "@/features/tour/tours";

/**
 * Two hands-on tours of the Review deck, on the sample deck (`/review?sample=1`): the steps press the deck's own keys,
 * so the person sees each card move, and nothing reaches the server or spends a model call.
 */
export const EDIT_TOUR = "review-edit-knowledge";
export const INSERT_TOUR = "review-insert-knowledge";
const SAMPLE = "/review?sample=1";

const press = (key: string) => () => {
  window.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
};
const settle = (ms = 260) => () => new Promise<void>((r) => setTimeout(r, ms));
const blur = () => (document.activeElement as HTMLElement | null)?.blur?.();
export const RESET_EVENT = "kb-review-sample-reset";
const reset = () => {
  window.dispatchEvent(new Event(RESET_EVENT));
};

export const editSteps = (): TourStep[] => [
  {
    go: SAMPLE,
    target: '[data-tour="review-card"]',
    wait: 4000,
    place: "right",
    // the sample opens on a dropped source; this tour is about changes to pages, so it leaves that source for later
    before: async () => {
      reset();
      await settle(300)();
      press("s")();
      await settle(300)();
    },
    title: "One change per card",
    body: "Each card is one paragraph the agent wants to change. The grey text around it is the page as it is now.",
  },
  {
    target: '[data-tour="review-why"]',
    place: "bottom",
    title: "Check the why",
    body: "**why** and **from** say where the change comes from. Open the source before you trust a claim; **no source** means there is none.",
  },
  {
    target: '[data-tour="review-actions"]',
    place: "top",
    title: "Accept or reject",
    body: "Press **A** or **R**, or drag the card by its edge. Nothing is written yet, and **Z** takes any decision back.",
  },
  {
    target: '[data-tour="review-reach"]',
    place: "right",
    title: "What it touches",
    body: "The graph shows every page this change reaches: links it adds or removes, pages that lean on it, pages it links to. The search line (**G**) brings in more, in plain words or Cypher. Click a page (or **[ ]** then **X**) to send it with your edit.",
  },
  {
    target: '[data-tour="review-edit"]',
    place: "top",
    before: () => {
      blur();
      press("e")();
    },
    keepFocus: true,
    title: "Say what to change",
    body: "Press **E** and write it in words, for example *shorter, keep the urban number*. Select words on the card and press **M** to point at them; picked pages and marked words show as chips and go with your sentence. The card comes back as **v2**; **vs v1** shows what your sentence changed.",
  },
  {
    target: '[data-tour="review-edit"]',
    place: "top",
    before: () => {
      blur();
      press("/")();
    },
    keepFocus: true,
    title: "Merge or split",
    body: "**/merge** and **/split** sit under the line (or type **/**): **/merge @page** folds another page into this one (a page you picked in the graph comes first), **/split** lets the model cut this page into focused pages. The result comes back as cards.",
  },
  {
    target: '[data-tour="review-apply"]',
    place: "bottom",
    before: blur,
    title: "Apply",
    body: "**Apply** shows what it will write, then applies the accepted changes to this knowledge base, one commit per proposal, and runs its checks.",
  },
];

export const insertSteps = (): TourStep[] => [
  {
    go: SAMPLE,
    target: '[data-tour="review-drop"]',
    wait: 4000,
    place: "bottom",
    before: reset,
    title: "Drop a source",
    body: "Drop a PDF anywhere on this screen or on the box at the top of the queue, choose a file, or paste a link. The file is kept untouched in raw/, with where it came from.",
  },
  {
    target: '[data-tour="review-queue"]',
    place: "left",
    title: "The agent reads",
    body: "It reads the source in full and drafts new pages and updates to existing ones. The queue shows how far each source got, then **Ready to review** with its card count: click a row to review only its cards. Nothing is written yet.",
  },
  {
    target: '[data-tour="review-cover"]',
    wait: 3000,
    place: "right",
    title: "Start at the source card",
    body: "One card says what this source would add. **Review its cards** now, or **Later** to leave the whole source for another time.",
  },
  {
    target: '[data-tour="review-card"]',
    place: "right",
    before: async () => {
      press("a")();
      await settle(400)();
    },
    title: "New pages",
    body: "A new page is one card: its title, description, body and sources. Accept it, edit it in words, or reject it.",
  },
  {
    target: '[data-tour="review-card"]',
    place: "right",
    before: async () => {
      press("a")();
      await settle(400)();
    },
    title: "Changed pages",
    body: "Then the paragraphs it would change elsewhere, like this link to the new page from where fusion is explained.",
  },
  {
    target: '[data-tour="review-apply"]',
    place: "bottom",
    title: "Apply",
    body: "**Apply** writes the new pages to this knowledge base, one commit per proposal, and checks them. Undo is on the Lifecycle screen.",
  },
];

function sync(): void {
  if (!flag("ui.review-deck")) {
    unregisterTour(EDIT_TOUR);
    unregisterTour(INSERT_TOUR);
    return;
  }
  registerTour(EDIT_TOUR, editSteps(), "Edit knowledge: review changes card by card, rewrite one in words, merge or split, apply.", { onEnd: blur });
  registerTour(INSERT_TOUR, insertSteps(), "Insert knowledge: drop a source, review what it adds, apply it to your KB.", { onEnd: blur });
}
sync();
subscribeFlags(sync);
