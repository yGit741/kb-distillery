import { defaultDataSource } from "@/api";
import { flag, subscribeFlags } from "@/flags";
import { tryTargets } from "./model";
import {
  registerTour,
  unregisterTour,
  type TourStep,
} from "@/features/tour/tours";

/**
 * "What's new: proposals": the human-in-the-loop family on the real app. It starts at the review inbox, opens the
 * newest proposal, follows it to the page it touches (chat, flags, sources, history, restructure), then ingest and
 * the Variants tab. It works on any kb with an open proposal (`pixi run demo-proposals` seeds the demo).
 * Targets hold for every variant; a step whose target a variant hides shows its card centred.
 */
export const PROPOSALS_TOUR = "whats-new-proposals";

const PAGE = '[data-tour="page-actions"]';

/** The steps, shown on `proposal` (a review screen) and `page` (a page view); without them those steps stay on the inbox. */
export function proposalsTourSteps({
  page,
  proposal,
}: { page?: string; proposal?: string } = {}): TourStep[] {
  const review = proposal
    ? `/proposals/${encodeURIComponent(proposal)}`
    : "/proposals";
  const pageAt = page ? `/pages/${encodeURIComponent(page)}` : "/proposals";
  return [
    {
      go: "/proposals",
      target: "main",
      wait: 4000,
      dim: 0.3,
      title: "Every change is a proposal",
      // source: features/proposals/Inbox.tsx; src/kb_distillery/proposals/service.py (inbox)
      body: "Chat, flags, ingest, restructure and the nightly lint never write a page. They leave a **proposal** here, grouped by kind of change; the View switch regroups them by page or by time.",
    },
    {
      go: review,
      target: "main header",
      wait: 4000,
      place: "bottom",
      title: "Review what would change",
      // source: features/proposals/ReviewScreen.tsx (diff variants inline, side-by-side, reading)
      body: "The review screen shows the page as it would read, change by change. Accept **part** of it; My notes is never touched.",
    },
    {
      go: pageAt,
      target: PAGE,
      wait: 4000,
      place: "bottom",
      title: "Chat on the page",
      // source: features/pages/PageChat.tsx (five entry variants); src/kb_distillery/proposals/chat.py
      body: "Ask about the page while reading it, for example **soften this, check against @a-paper**. The reply's edits come back as a proposal.",
    },
    {
      target: '[data-testid="flags-header"]',
      place: "bottom",
      title: "Flag while you read",
      // source: features/pages/PageFlags.tsx (underline, margin, tint); src/kb_distillery/proposals/flags.py
      body: "Select a sentence and mark it inaccurate with a short note, then keep reading. **Fix all flagged** later turns the flags into one proposal.",
    },
    {
      target:
        'section[aria-label="Page sources"], [data-testid="sources-side-tab"], [data-testid="sources-count-mark"]',
      title: "Where a page comes from",
      // source: features/pages/PageSources.tsx (footer, side tab, hover marks)
      body: "The sources a page rests on, in the look the sources variant picks.",
    },
    {
      target:
        'button[aria-controls="page-history-panel"], nav[aria-label="Page history timeline"]',
      place: "bottom",
      title: "How the page changed",
      // source: features/pages/PageHistory.tsx; src/kb_distillery/proposals/history.py
      body: "Every version of the page from the knowledge base's history. Compare any two to see what changed.",
    },
    {
      target: '[data-tour="page-restructure"]',
      place: "bottom",
      title: "Merge, split, extract",
      // source: features/restructure/entry.tsx (menu, commands); src/kb_distillery/proposals/restructure.py
      body: "When two pages grew into one topic, or one page into two, restructure them. Links elsewhere are rewritten in the **same** proposal.",
    },
    {
      go: "/ingest",
      target: "main",
      wait: 4000,
      dim: 0.3,
      title: "Drop a new source in",
      // source: features/ingest (single page, wizard); src/kb_distillery/services/ingest_ui.py
      body: "Drop a paper or paste a link and choose how deeply to read it. The new pages arrive as a proposal to review.",
    },
    {
      go: "/system?tab=variants",
      target: '[data-tour="variant-chooser"]',
      wait: 4000,
      place: "bottom",
      // the status tiles above grow when their data arrives: let them settle before the spotlight is measured
      before: () => new Promise((r) => setTimeout(r, 1500)),
      title: "Pick the designs you like",
      // source: features/system/VariantsView.tsx; components/variants.tsx (VARIANTS)
      body: "Each screen above ships in a few designs. Pick one per screen here; **Copy choices** gives a list to hand to an agent.",
    },
  ];
}

const SUMMARY =
  "What's new: proposals, chat and flags on a page, history, restructure, ingest, and the variant chooser.";

/** Registered with the inbox only, then again once the open proposals say which review and page to show. */
function sync(): void {
  if (!flag("ui.proposals")) return unregisterTour(PROPOSALS_TOUR);
  registerTour(PROPOSALS_TOUR, proposalsTourSteps(), SUMMARY);
  Promise.resolve()
    .then(() => defaultDataSource().listProposals("open"))
    .then(
      (rows) =>
        flag("ui.proposals") &&
        registerTour(
          PROPOSALS_TOUR,
          proposalsTourSteps(tryTargets(rows)),
          SUMMARY,
        ),
    )
    .catch(() => {
      /* no proposals API here (a share build): the tour stays on the inbox */
    });
}
sync();
subscribeFlags(sync);
