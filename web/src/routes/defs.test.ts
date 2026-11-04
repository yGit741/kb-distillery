import { describe, expect, it } from "vitest";
import { flag } from "@/flags";
import { withFlag } from "@/flags/testing";
import { ROUTE_DEFS, routeDefsNow, routeOffered } from "./defs";

describe("route defs consult flags", () => {
  it("every route with a flag exists only when that flag is on", () => {
    const ids = ROUTE_DEFS.map((d) => d.id);
    expect(ids).toContain("lifecycle"); // screen.lifecycle is on locally
    expect(ids).not.toContain("share"); // screen.share is private-site only
    for (const d of ROUTE_DEFS) if (d.flag) expect(flag(d.flag), d.id).toBe(true);
  });
});

describe("the ported legacy pages", () => {
  it("Start (screen.start) and Covector (runtime research-tools) are not in the top bar", () => {
    for (const [id, path, screenFlag] of [["start", "/start", "screen.start"], ["covector", "/covector", undefined]] as const) {
      const d = ROUTE_DEFS.find((r) => r.id === id);
      expect(d, id).toBeDefined();
      expect(d!.path).toBe(path);
      expect(d!.flag).toBe(screenFlag);
      if (id === "covector") expect(d!.runtimeFlag).toBe("research-tools");
      expect(d!.nav).toBeUndefined();
    }
  });
});

/** Flag test matrix (kb_distillery.config.flags.coverage): each screen flag on and off. */
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
  it("screen.start on → /start exists", () =>
    withFlag("screen.start", true, () => expect(ids()).toContain("start")));
  it("screen.start off → no /start", () =>
    withFlag("screen.start", false, () => expect(ids()).not.toContain("start")));
  it("screen.think on → /think exists", () =>
    withFlag("screen.think", true, () => expect(ids()).toContain("think")));
  it("screen.think off → no /think", () =>
    withFlag("screen.think", false, () => expect(ids()).not.toContain("think")));
  it("withFlag restores the built value", () => {
    withFlag("screen.share", true, () => undefined);
    expect(ids()).not.toContain("share");
  });
});

describe("Covector is the owner's own page", () => {
  const covector = () => ROUTE_DEFS.find((r) => r.id === "covector")!;
  it("is offered only while research-tools is on", () => {
    withFlag("research-tools", false, () => expect(routeOffered(covector())).toBe(false));
    withFlag("research-tools", true, () => expect(routeOffered(covector())).toBe(true));
    expect(routeOffered({})).toBe(true); // routes without a runtime flag are always offered
  });
});
