import { capabilitiesFor, type Capabilities } from "./capabilities";

const READ_ONLY_HALF: (keyof Capabilities)[] = ["readViews", "favoriteMark"];
const NEVER_ON_A_SHARED_SITE: (keyof Capabilities)[] = ["sentences", "llm", "saveViews", "favoriteToggle", "recentSteps", "chat", "ask", "think", "serverSearch", "shape", "exportNotes"];

describe("capabilities table", () => {
  it("the app with the flag on can do everything", () => {
    expect(Object.values(capabilitiesFor(false, true)).every(Boolean)).toBe(true);
  });

  it("the app with the flag off keeps the old behaviour: only views are not read through the line", () => {
    const c = capabilitiesFor(false, false);
    expect(c.readViews).toBe(false);
    expect(c.sentences).toBe(false);
    for (const k of Object.keys(c) as (keyof Capabilities)[]) if (k !== "readViews" && k !== "sentences") expect(c[k]).toBe(true);
  });

  it("a shared site with the flag on reads views and shows the favorite mark, and nothing else", () => {
    const c = capabilitiesFor(true, true);
    for (const k of READ_ONLY_HALF) expect(c[k]).toBe(true);
    for (const k of NEVER_ON_A_SHARED_SITE) expect(c[k]).toBe(false);
  });

  it("a shared site with the flag off reads no views", () => {
    const c = capabilitiesFor(true, false);
    expect(c.readViews).toBe(false);
    for (const k of NEVER_ON_A_SHARED_SITE) expect(c[k]).toBe(false);
  });

  it("every key is decided in the table (a new capability must be placed on purpose)", () => {
    expect(Object.keys(capabilitiesFor(true, true)).sort()).toEqual([...READ_ONLY_HALF, ...NEVER_ON_A_SHARED_SITE].sort());
  });
});
