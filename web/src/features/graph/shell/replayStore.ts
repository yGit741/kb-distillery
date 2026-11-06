import { create } from "zustand";
import type { ReplayView } from "./replay";

/**
 * The replay on screen (flag `spark-chat`). `view` is the trail at the current step: the canvas lights it through the
 * same focus it uses for cited pages, and never moves the camera. The marks (a page the agent missed, a citation to
 * re-check) outlive the replay: they ride on the composer until the next message is sent or each is removed.
 */
interface ReplayState {
  /** the message being replayed (index in the chat) and its step */
  msg: number | null;
  step: number;
  view: ReplayView | null;
  /** "one link away, not read" pages at the last step, found by the canvas (it knows the links) */
  candidates: readonly string[];
  /** a cited page the reader clicked: the panel offers "Mark as a bad citation" for it */
  picked: string | null;
  missed: readonly string[];
  bad: readonly string[];
  open: (msg: number, step: number, view: ReplayView) => void;
  show: (step: number, view: ReplayView) => void;
  close: () => void;
  setCandidates: (c: readonly string[]) => void;
  pick: (slug: string | null) => void;
  toggleMissed: (slug: string) => void;
  toggleBad: (slug: string) => void;
  unmark: (slug: string) => void;
  clearMarks: () => void;
}

const toggle = (list: readonly string[], slug: string) => (list.includes(slug) ? list.filter((s) => s !== slug) : [...list, slug]);
const same = (a: readonly string[], b: readonly string[]) => a.length === b.length && a.every((s, i) => s === b[i]);

export const useReplay = create<ReplayState>((set, get) => ({
  msg: null,
  step: 0,
  view: null,
  candidates: [],
  picked: null,
  missed: [],
  bad: [],
  open: (msg, step, view) => set({ msg, step, view, picked: null }),
  show: (step, view) => set({ step, view, picked: null }),
  close: () => {
    if (get().msg !== null || get().view) set({ msg: null, view: null, candidates: [], picked: null });
  },
  setCandidates: (candidates) => {
    if (!same(get().candidates, candidates)) set({ candidates });
  },
  pick: (picked) => set({ picked }),
  toggleMissed: (slug) => set((s) => ({ missed: toggle(s.missed, slug), bad: s.bad.filter((b) => b !== slug) })),
  toggleBad: (slug) => set((s) => ({ bad: toggle(s.bad, slug), missed: s.missed.filter((b) => b !== slug), picked: null })),
  unmark: (slug) => set((s) => ({ missed: s.missed.filter((b) => b !== slug), bad: s.bad.filter((b) => b !== slug) })),
  clearMarks: () => {
    if (get().missed.length || get().bad.length) set({ missed: [], bad: [] });
  },
}));
