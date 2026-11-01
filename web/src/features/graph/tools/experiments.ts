import { create } from "zustand";

/**
 * Experiment flags. A tool with `flag: "<id>"` is drawn only while that experiment is switched on in the
 * Experiments panel (or named in `?exp=a,b` on the URL). The switches persist per browser, so trying an
 * idea never changes the graph for anyone who did not opt in.
 */
export interface Experiment {
  id: string;
  label: string;
  /** the user story, one sentence: "When I …, I want …, so that …" */
  story: string;
  /** how to read the result */
  read: string;
}

export const EXPERIMENTS: Experiment[] = [];

export function registerExperiment(e: Experiment): void {
  const i = EXPERIMENTS.findIndex((x) => x.id === e.id);
  if (i >= 0) EXPERIMENTS[i] = e;
  else EXPERIMENTS.push(e);
}

const KEY = "kb-graph-experiments-v1";

function initial(): Set<string> {
  const on = new Set<string>();
  try {
    for (const id of JSON.parse(localStorage.getItem(KEY) ?? "[]") as unknown[]) if (typeof id === "string") on.add(id);
  } catch {
    /* private mode or a bad value: start with everything off */
  }
  try {
    const q = new URLSearchParams(window.location.search).get("exp");
    for (const id of q?.split(",") ?? []) if (id.trim()) on.add(id.trim());
  } catch {
    /* no window (tests) */
  }
  return on;
}

interface ExperimentState {
  on: ReadonlySet<string>;
  toggle: (id: string) => void;
}

export const useExperiments = create<ExperimentState>((set, get) => ({
  on: initial(),
  toggle: (id) => {
    const next = new Set(get().on);
    if (!next.delete(id)) next.add(id);
    try {
      localStorage.setItem(KEY, JSON.stringify([...next]));
    } catch {
      /* the switch still works for this visit */
    }
    set({ on: next });
  },
}));

export const flagOn = (flag: string | undefined, on: ReadonlySet<string>): boolean => !flag || on.has(flag);
