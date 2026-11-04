import { DEFAULT_PREFS, contextUsed, loadPrefs, turnCost } from "./composer";

beforeEach(() => window.localStorage.clear());

describe("turnCost", () => {
  it("is the real charge, else the API-price estimate, else 0", () => {
    expect(turnCost({ cost_usd: 0.3, est_cost_usd: 0.5 })).toBe(0.3);
    expect(turnCost({ cost_usd: 0, est_cost_usd: 0.5, billing: "subscription" })).toBe(0.5);
    expect(turnCost({})).toBe(0);
    expect(turnCost(undefined)).toBe(0);
  });
});

describe("contextUsed", () => {
  it("counts fresh and cached input, never output", () => {
    expect(contextUsed({ input_tokens: 10, cache_read_input_tokens: 20, cache_creation_input_tokens: 5, output_tokens: 999 })).toBe(35);
    expect(contextUsed(undefined)).toBe(0);
  });
});

describe("loadPrefs", () => {
  it("defaults to medium effort, no billing pick (the account decides) and a $0.50 cap", () => {
    expect(loadPrefs()).toEqual(DEFAULT_PREFS);
    expect(DEFAULT_PREFS).toEqual({ effort: "medium", billing: null, cap: 0.5 });
  });
  it("drops what it does not know", () => {
    window.localStorage.setItem("kbchat.composer", JSON.stringify({ effort: "turbo", billing: "free", cap: -1 }));
    expect(loadPrefs()).toEqual(DEFAULT_PREFS);
    window.localStorage.setItem("kbchat.composer", "{not json");
    expect(loadPrefs()).toEqual(DEFAULT_PREFS);
    window.localStorage.setItem("kbchat.composer", JSON.stringify({ effort: "max", billing: "api", cap: 0 }));
    expect(loadPrefs()).toEqual({ effort: "max", billing: "api", cap: 0 });
  });
});
