import { describe, expect, it } from "vitest";
import { flag } from "@/flags";
import { withFlag } from "@/flags/testing";
import { ROUTE_DEFS, routeDefsNow } from "./defs";

describe("route defs consult flags", () => {
  it("every route with a flag exists only when that flag is on", () => {
    const ids = ROUTE_DEFS.map((d) => d.id);
    expect(ids).toContain("lifecycle"); // screen.lifecycle is on locally
    expect(ids).not.toContain("share"); // screen.share is private-site only
    for (const d of ROUTE_DEFS) if (d.flag) expect(flag(d.flag), d.id).toBe(true);
  });
});

/** Flag test matrix (kb.flags.coverage): each screen flag on and off. */
describe("screen flags gate their route", () => {
  const ids = () => routeDefsNow().map((d) => d.id);
  it("screen.lifecycle on → /lifecycle exists", () =>
    withFlag("screen.lifecycle", true, () => expect(ids()).toContain("lifecycle")));
  it("screen.lifecycle off → no /lifecycle", () =>
    withFlag("screen.lifecycle", false, () => expect(ids()).not.toContain("lifecycle")));
  it("screen.share on → /share exists", () =>
    withFlag("screen.share", true, () => expect(ids()).toContain("share")));
  it("screen.share off → no /share", () =>
    withFlag("screen.share", false, () => expect(ids()).not.toContain("share")));
  it("screen.think on → /think exists", () =>
    withFlag("screen.think", true, () => expect(ids()).toContain("think")));
  it("screen.think off → no /think", () =>
    withFlag("screen.think", false, () => expect(ids()).not.toContain("think")));
  it("withFlag restores the built value", () => {
    withFlag("screen.share", true, () => undefined);
    expect(ids()).not.toContain("share");
  });
});
