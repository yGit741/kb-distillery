import { DEFAULT_LAB, sanitizeLab } from "./config";

describe("sanitizeLab", () => {
  it("keeps known keys of the right type and drops the rest", () => {
    const c = sanitizeLab({ coverage: 20, t1: "big", bogus: 1 });
    expect(c.coverage).toBe(20);
    expect(c.t1).toBe(DEFAULT_LAB.t1);
    expect("bogus" in c).toBe(false);
  });
  it("falls back to the default for an unknown enumeration value", () => {
    expect(sanitizeLab({ questionLabels: "maybe", neighborBy: "random" })).toMatchObject({ questionLabels: DEFAULT_LAB.questionLabels, neighborBy: DEFAULT_LAB.neighborBy });
    expect(sanitizeLab({ questionLabels: "short", neighborBy: "score" })).toMatchObject({ questionLabels: "short", neighborBy: "score" });
  });
  it("tolerates a non-object", () => {
    expect(sanitizeLab(null)).toEqual(DEFAULT_LAB);
  });
});
