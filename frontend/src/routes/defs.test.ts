import { describe, expect, it } from "vitest";
import { flag } from "@/flags";
import { ROUTE_DEFS } from "./defs";

describe("route defs consult flags", () => {
  it("every route with a flag exists only when that flag is on", () => {
    const ids = ROUTE_DEFS.map((d) => d.id);
    expect(ids).toContain("lifecycle"); // screen.lifecycle is on locally
    expect(ids).not.toContain("share"); // screen.share is private-site only
    for (const d of ROUTE_DEFS) if (d.flag) expect(flag(d.flag), d.id).toBe(true);
  });
});
