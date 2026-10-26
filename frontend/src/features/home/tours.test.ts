import { listTours, stepsOf } from "@/features/tour/tours";
import "./tours";

const NAMES = ["first-visit", "thesis-story", "boolean-bridge"];

describe("Home → Graph tours", () => {
  it("registers the three journeys with a one-line summary each", () => {
    const tours = listTours({ all: true }).filter((t) => NAMES.includes(t.name));
    expect(tours.map((t) => t.name).sort()).toEqual([...NAMES].sort());
    for (const t of tours) expect(t.summary.length).toBeGreaterThan(10);
  });

  it("the Tours menu lists only the first-visit tour", () => {
    expect(listTours().filter((t) => NAMES.includes(t.name)).map((t) => t.name)).toEqual(["first-visit"]);
  });

  it("every step has a title, a body of at most two sentences, and a string target", () => {
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
  });
});
