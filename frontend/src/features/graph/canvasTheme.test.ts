import { withAlpha, readCanvasColors } from "./canvasTheme";
import { wheelAction, wheelUnits } from "./ForceGraph";

describe("withAlpha", () => {
  it("converts hex and rgb colours and clamps alpha", () => {
    expect(withAlpha("#ff0000", 0.5)).toBe("rgba(255, 0, 0, 0.5)");
    expect(withAlpha("#0f0", 1)).toBe("rgba(0, 255, 0, 1)");
    expect(withAlpha("rgb(1, 2, 3)", 2)).toBe("rgba(1, 2, 3, 1)");
    expect(withAlpha("rgba(1 2 3 / 0.1)", 0.3)).toBe("rgba(1, 2, 3, 0.3)");
    expect(withAlpha("red", 0.3)).toBe("red");
  });
  it("reads chrome tokens with fallbacks in jsdom", () => {
    expect(readCanvasColors().ring).toMatch(/^#/);
  });
});

describe("the wheel scheme", () => {
  it("normalises line and page deltas", () => {
    expect(wheelUnits({ deltaMode: 1, deltaX: 1, deltaY: 2 } as WheelEvent, 800)).toEqual({ dx: 16, dy: 32 });
    expect(wheelUnits({ deltaMode: 2, deltaX: 0, deltaY: 1 } as WheelEvent, 800)).toEqual({ dx: 0, dy: 800 });
  });
  it("pans on a plain wheel, sideways with shift", () => {
    expect(wheelAction({ ctrlKey: false, metaKey: false, shiftKey: false }, 3, 7)).toEqual({ kind: "pan", dx: 3, dy: 7 });
    expect(wheelAction({ ctrlKey: false, metaKey: false, shiftKey: true }, 0, 7)).toEqual({ kind: "pan", dx: 7, dy: 0 });
  });
  it("zooms on pinch (ctrl) and Cmd+wheel, in on negative deltas", () => {
    const pinch = wheelAction({ ctrlKey: true, metaKey: false, shiftKey: false }, 0, -5);
    const cmd = wheelAction({ ctrlKey: false, metaKey: true, shiftKey: false }, 0, -100);
    expect(pinch.kind === "zoom" && pinch.factor).toBeGreaterThan(1);
    expect(cmd.kind === "zoom" && cmd.factor).toBeGreaterThan(1);
    const out = wheelAction({ ctrlKey: false, metaKey: true, shiftKey: false }, 0, 100);
    expect(out.kind === "zoom" && out.factor).toBeLessThan(1);
  });
});
