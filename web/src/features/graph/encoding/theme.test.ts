import { describe, expect, it } from "vitest";
import { withAlpha } from "./theme";

describe("withAlpha", () => {
  it("adds the alpha to hex and rgb colours", () => {
    expect(withAlpha("#71717a", 0.14)).toBe("rgba(113, 113, 122, 0.14)");
    expect(withAlpha("#fff", 0.5)).toBe("rgba(255, 255, 255, 0.5)");
    expect(withAlpha("rgb(1 2 3)", 2)).toBe("rgba(1, 2, 3, 1)");
  });

  it("leaves a colour it cannot resolve as it is (no canvas here)", () => {
    const mix = "color-mix(in srgb, oklch(55.2% .016 285.938) 80%, oklch(44.2% .017 285.786))";
    expect(withAlpha(mix, 0.3)).toBe(mix);
  });
});
