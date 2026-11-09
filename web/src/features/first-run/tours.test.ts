import { stepsOf } from "@/features/tour/tours";
import "./tours";

describe("first-run tour", () => {
  it("is registered with the card, the drop zone, the folder form and the digest jobs", () => {
    const steps = stepsOf("first-run") ?? [];
    expect(steps).toHaveLength(4);
    expect(steps[0]).toMatchObject({ go: "/graph", target: "#first-run-title" });
    for (const s of steps) expect(s.body.length).toBeGreaterThan(10);
  });
});
