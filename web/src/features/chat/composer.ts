/** The line under the composer (flag `agent-mode`): effort, who pays, a per-turn cost cap and the context ring.
 *  Picks live in one small store, saved per browser; the chat hook reads them when it sends and writes the cap
 *  prompt and the context fill back, so the screen only mounts the line. */
import { create } from "zustand";
import { readJson, writeJson } from "./storage";
import type { Usage } from "./sse";

export const EFFORTS = ["low", "medium", "high", "xhigh", "max"] as const;
export type Effort = (typeof EFFORTS)[number];
export const EFFORT_LABEL: Record<Effort, string> = { low: "Low", medium: "Medium", high: "High", xhigh: "Extra high", max: "Max" };

export const BILLINGS = ["subscription", "api", "batch"] as const;
export type Billing = (typeof BILLINGS)[number];
export const BILLING_LABEL: Record<Billing, string> = { subscription: "Subscription", api: "API", batch: "Batch" };
export const BILLING_HINT: Record<Billing, string> = {
  subscription: "Your Claude login pays",
  api: "Your API key pays",
  batch: "API key, half price, answered later, this question only, no tools",
};

/** USD per turn; 0 means no cap. */
export const CAP_CHOICES = [0.25, 0.5, 1, 2, 5, 0] as const;
export const DEFAULT_CAP = 0.5;
/** What Continue adds to this turn's cap. */
export const CAP_STEP = 0.5;
export const DEFAULT_CONTEXT = 200_000;

export interface Prefs {
  effort: Effort;
  /** null until the user picks one: then the Session account decides who pays and nothing is sent */
  billing: Billing | null;
  cap: number;
}
export const DEFAULT_PREFS: Prefs = { effort: "medium", billing: null, cap: DEFAULT_CAP };
const KEY = "kbchat.composer";

export function loadPrefs(): Prefs {
  const raw = readJson<Partial<Prefs> | null>("local", KEY, null);
  const r = raw && typeof raw === "object" ? raw : {};
  return {
    effort: EFFORTS.includes(r.effort as Effort) ? (r.effort as Effort) : DEFAULT_PREFS.effort,
    billing: BILLINGS.includes(r.billing as Billing) ? (r.billing as Billing) : null,
    cap: typeof r.cap === "number" && r.cap >= 0 && Number.isFinite(r.cap) ? r.cap : DEFAULT_PREFS.cap,
  };
}

/** What this turn cost: the real charge, else the API-price estimate (a subscription turn charges 0). */
export function turnCost(u: Usage | undefined): number {
  if (!u) return 0;
  if (typeof u.cost_usd === "number" && u.cost_usd > 0) return u.cost_usd;
  return typeof u.est_cost_usd === "number" && u.est_cost_usd > 0 ? u.est_cost_usd : 0;
}

/** Tokens the model read for this turn (fresh + cached), what the context ring counts. */
export function contextUsed(u: Usage | undefined): number {
  if (!u) return 0;
  return (u.input_tokens || 0) + (u.cache_read_input_tokens || 0) + (u.cache_creation_input_tokens || 0);
}

export const usd = (x: number) => `$${x.toFixed(2)}`;
export const capLabel = (cap: number) => (cap > 0 ? usd(cap) : "No cap");

export type CapDecision = "continue" | "stop";
export interface CapPrompt {
  spent: number;
  limit: number;
}

interface ComposerState {
  prefs: Prefs;
  setPrefs: (p: Partial<Prefs>) => void;
  /** a turn crossed its cap and waits for Continue or Stop */
  capPrompt: CapPrompt | null;
  /** tokens in the latest answer's context */
  used: number;
}

export const initialComposer = (): Pick<ComposerState, "prefs" | "capPrompt" | "used"> => ({ prefs: loadPrefs(), capPrompt: null, used: 0 });

export const useComposer = create<ComposerState>((set, get) => ({
  ...initialComposer(),
  setPrefs: (p) => {
    const prefs = { ...get().prefs, ...p };
    writeJson("local", KEY, prefs);
    set({ prefs });
  },
}));

let gate: ((d: CapDecision) => void) | null = null;

/** Show the cap prompt and wait for the user; an aborted turn counts as Stop. */
export function askCap(prompt: CapPrompt, signal: AbortSignal): Promise<CapDecision> {
  return new Promise((resolve) => {
    const done = (d: CapDecision) => {
      signal.removeEventListener("abort", onAbort);
      gate = null;
      useComposer.setState({ capPrompt: null });
      resolve(d);
    };
    const onAbort = () => done("stop");
    if (signal.aborted) return done("stop");
    signal.addEventListener("abort", onAbort);
    gate = done;
    useComposer.setState({ capPrompt: prompt });
  });
}

/** The Continue / Stop buttons. */
export const answerCap = (d: CapDecision) => gate?.(d);
