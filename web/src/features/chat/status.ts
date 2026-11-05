import type { ChatStatus } from "@/api";

/** ChatStatus carries loose dicts (agent, subscription, models, spend); narrow them once, here. */
const isObj = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null;
const str = (v: unknown, d = "") => (typeof v === "string" ? v : d);
const num = (v: unknown, d = 0) => (typeof v === "number" && Number.isFinite(v) ? v : d);

export interface Spend {
  credit: number;
  spent: number;
  left: number;
  turns: number;
  cycleStart: string;
  nextReset: string;
  subscriptionTurns: number;
}
export interface Model {
  id: string;
  label: string;
  /** context window in tokens, when the server says */
  context?: number;
}
export interface StatusView {
  backend: "agent" | "direct";
  agentAvailable: boolean;
  agentVersion: string;
  agentError: string;
  authMode: "api_key" | "subscription";
  subscription: { loggedIn: boolean; plan: string; email: string; error: string };
  keys: { name: string; hint: string; origin: string }[];
  activeKey: string;
  keysDir: string;
  keyLoaded: boolean;
  keyOrigin: string;
  keyName: string;
  keyHint: string;
  keyFile: string;
  models: Model[];
  defaultModel: string;
  resetDay: number;
  spend: Spend | null;
}

export function parseSpend(raw: unknown): Spend | null {
  if (!isObj(raw) || typeof raw.credit !== "number") return null;
  return {
    credit: num(raw.credit),
    spent: num(raw.spent),
    left: num(raw.left),
    turns: num(raw.turns),
    cycleStart: str(raw.cycle_start),
    nextReset: str(raw.next_reset),
    subscriptionTurns: num(raw.subscription_turns),
  };
}

export function parseStatus(st: ChatStatus): StatusView {
  const sub = isObj(st.auth.subscription) ? st.auth.subscription : {};
  return {
    backend: st.backend === "direct" ? "direct" : "agent",
    agentAvailable: st.agent.available === true,
    agentVersion: str(st.agent.version),
    agentError: str(st.agent.error),
    authMode: st.auth.mode === "subscription" ? "subscription" : "api_key",
    subscription: { loggedIn: sub.logged_in === true, plan: str(sub.plan), email: str(sub.email), error: str(sub.error) },
    keys: st.auth.keys.map((k) => ({ name: k.name, hint: k.hint, origin: k.origin })),
    activeKey: st.auth.active_key,
    keysDir: st.auth.keys_dir,
    keyLoaded: st.key,
    keyOrigin: st.key_origin ?? "",
    keyName: st.key_name,
    keyHint: st.key_hint,
    keyFile: st.key_file,
    models: st.models.filter(isObj).map((m) => ({ id: str(m.id), label: str(m.label, str(m.id)), ...(num(m.context) > 0 ? { context: num(m.context) } : {}) })).filter((m) => m.id),
    defaultModel: st.default_model,
    resetDay: st.reset_day,
    spend: parseSpend(st.spend),
  };
}

/** The backend a message will use: Agent when it is selected and installed, else Direct. */
export const effectiveBackend = (s: StatusView): "agent" | "direct" => (s.backend === "agent" && s.agentAvailable ? "agent" : "direct");

/** One-line "what pays and what runs" for the header chip. */
export function backendLabel(s: StatusView): { text: string; ok: boolean } {
  const be = effectiveBackend(s) === "agent" ? "Agent" : "Direct";
  if (s.authMode === "subscription" && s.subscription.loggedIn) {
    return { text: `${be} · subscription${s.subscription.plan ? ` (${s.subscription.plan})` : ""}`, ok: true };
  }
  if (s.keyLoaded) return { text: `${be} · API key${s.keyName ? ` ${s.keyName}` : ""} ${s.keyHint}`.trim(), ok: true };
  return { text: `${be} · no API key`, ok: false };
}

/** Value of the Account select: "subscription" or "key:<name>". */
export function authValue(s: StatusView): string {
  if (s.authMode === "subscription") return "subscription";
  return `key:${s.activeKey || s.keys[0]?.name || ""}`;
}

export function authPayload(value: string) {
  return value === "subscription"
    ? ({ auth_mode: "subscription" } as const)
    : ({ auth_mode: "api_key", active_key: value.startsWith("key:") ? value.slice(4) : "" } as const);
}
