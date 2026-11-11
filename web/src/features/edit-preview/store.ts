import { create } from "zustand";
import { NO_DECISIONS, acceptAdditions, acceptBulk, acceptRestOfPage, type Decision, type Decisions, type PreviewItem, type PreviewPage } from "./model";

/** What the middle column shows: every change in groups, or one page as a document. */
export type View = { kind: "all" } | { kind: "page"; slug: string; focus: string | null };

/** The real plan on screen: a job still reading a dropped file, or the proposal it (or anything else) made. */
export interface PlanTarget {
  /** A dropped file waiting for the go-ahead: nothing is read, and nothing is spent, until the person starts it. */
  file?: File;
  jobId?: string;
  proposalId?: string;
  /** The dropped file's name, shown until the proposal has a title. */
  name?: string;
  error?: string;
}

interface State {
  /** The plan pop-up (a real source or proposal); null = closed. Separate from the sample sheet below. */
  plan: PlanTarget | null;
  showPlan: (p: PlanTarget) => void;
  closePlan: () => void;
  open: boolean;
  /** A dropped file is being read: the sheet is up, its pages are still arriving. */
  reading: boolean;
  view: View;
  decisions: Decisions;
  /** The sample run ended: nothing is written while the flag is dark. */
  applied: boolean;
  show: (o?: { reading?: boolean }) => void;
  ready: () => void;
  /** Closing keeps every decision, so reopening carries on. */
  close: () => void;
  showAll: () => void;
  showPage: (slug: string, focus?: string | null) => void;
  focus: (id: string | null) => void;
  decide: (id: string, d: Decision | null) => void;
  decideBulk: (slug: string, d: Decision | null) => void;
  pick: (choice: string, option: number) => void;
  acceptAdditions: (item: PreviewItem) => void;
  acceptBulk: (item: PreviewItem) => void;
  acceptRest: (page: PreviewPage) => void;
  apply: () => void;
  reset: () => void;
}

const without = <T,>(o: Record<string, T>, k: string): Record<string, T> => {
  const { [k]: _, ...rest } = o;
  return rest;
};

export const useEditPreview = create<State>((set) => ({
  plan: null,
  showPlan: (plan) => set({ plan }),
  closePlan: () => set({ plan: null }),
  open: false,
  reading: false,
  view: { kind: "all" },
  decisions: NO_DECISIONS,
  applied: false,
  show: (o) => set({ open: true, reading: !!o?.reading }),
  ready: () => set({ reading: false }),
  close: () => set({ open: false, reading: false }),
  showAll: () => set({ view: { kind: "all" } }),
  showPage: (slug, focus = null) => set({ view: { kind: "page", slug, focus } }),
  focus: (id) => set((s) => (s.view.kind === "page" ? { view: { ...s.view, focus: id } } : s)),
  decide: (id, d) => set((s) => ({ decisions: { ...s.decisions, changes: d ? { ...s.decisions.changes, [id]: d } : without(s.decisions.changes, id) } })),
  decideBulk: (slug, d) => set((s) => ({ decisions: { ...s.decisions, bulk: d ? { ...s.decisions.bulk, [slug]: d } : without(s.decisions.bulk, slug) } })),
  pick: (choice, option) => set((s) => ({ decisions: { ...s.decisions, choices: { ...s.decisions.choices, [choice]: option } } })),
  acceptAdditions: (item) => set((s) => ({ decisions: acceptAdditions(item, s.decisions) })),
  acceptBulk: (item) => set((s) => ({ decisions: acceptBulk(item, s.decisions) })),
  acceptRest: (page) => set((s) => ({ decisions: acceptRestOfPage(page, s.decisions) })),
  apply: () => set({ applied: true, view: { kind: "all" } }),
  reset: () => set({ plan: null, open: false, reading: false, view: { kind: "all" }, decisions: NO_DECISIONS, applied: false }),
}));
