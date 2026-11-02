import { listTours, stepsOf } from "@/features/tour/tours";
import { act } from "@testing-library/react";
import { setFlagOverrides } from "@/flags";
import { withFlag } from "@/flags/testing";
import "./tours";

const NAMES = ["first-visit", "thesis-story", "boolean-bridge"];
/** Registered only while the research-tools flag is on. */
const THESIS = ["thesis-story", "boolean-bridge"];
const withResearch = (fn: () => void) => () => withFlag("research-tools", true, fn);

describe("Home → Graph tours", () => {
  it("registers the three journeys with a one-line summary each", withResearch(() => {
    const tours = listTours({ all: true }).filter((t) => NAMES.includes(t.name));
    expect(tours.map((t) => t.name).sort()).toEqual([...NAMES].sort());
    for (const t of tours) expect(t.summary.length).toBeGreaterThan(10);
  }));

  it("keeps the thesis journeys out while the research-tools flag is off, and back when it turns on", () => {
    withFlag("research-tools", false, () => {
      const names = listTours({ all: true }).map((t) => t.name);
      expect(names).toContain("first-visit");
      for (const n of THESIS) expect(names).not.toContain(n);
    });
    withFlag("research-tools", true, () => {
      const names = listTours({ all: true }).map((t) => t.name);
      for (const n of THESIS) expect(names).toContain(n);
    });
  });

  it("the Tours menu lists only the first-visit tour", withResearch(() => {
    expect(listTours().filter((t) => NAMES.includes(t.name)).map((t) => t.name)).toEqual(["first-visit"]);
  }));

  it("registers the thesis journeys when the flag arrives after boot", () => {
    setFlagOverrides({});
    expect(listTours({ all: true }).map((t) => t.name)).not.toContain("thesis-story");
    act(() => setFlagOverrides({ "research-tools": true }));
    expect(listTours({ all: true }).map((t) => t.name)).toContain("thesis-story");
    act(() => setFlagOverrides({}));
    expect(listTours({ all: true }).map((t) => t.name)).not.toContain("thesis-story");
  });

  it("every step has a title, a body of at most two sentences, and a string target", withResearch(() => {
    for (const name of NAMES) {
      const steps = stepsOf(name);
      expect(steps.length).toBeGreaterThanOrEqual(6);
      for (const s of steps) {
        expect(typeof s.target).toBe("string");
        expect(s.target!.length).toBeGreaterThan(0);
        expect(s.title.trim().length).toBeGreaterThan(0);
        expect(s.body.trim().length).toBeGreaterThan(0);
        expect(s.body.trim().split(/[.?!]\s/).length, `${name}: "${s.title}"`).toBeLessThanOrEqual(2);
        if (s.go) expect(s.go.startsWith("/")).toBe(true);
      }
      // each journey starts on Home and comes back to it
      expect(steps[0]!.go).toBeUndefined();
      expect(steps.at(-1)!.go).toBe("/");
      expect(steps.some((s) => s.go?.startsWith("/graph"))).toBe(true);
    }
  }));
});
