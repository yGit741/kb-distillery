import { bubbleAim, rgbOf, stepBubble } from "./magnet";

describe("magnetic bubble", () => {
  const t = { id: "t", x: 100, y: 0, r: 10 };
  const far = { id: "f", x: 400, y: 0, r: 10 };

  it("reaches past the target and fades toward the edge of the reach", () => {
    const near = bubbleAim(t, 85, 0, [t, far]);
    const edge = bubbleAim(t, -10, 0, [t, far]);
    expect(near.want).toBeCloseTo(35);
    expect(near.strength).toBeGreaterThan(edge.strength);
    expect(edge.strength).toBeCloseTo(0.45);
  });

  it("eases toward the aim, or jumps there under reduced motion", () => {
    expect(stepBubble({ r: 0, a: 0 }, 100, 1, true)).toEqual({ r: 100, a: 1 });
    const s = stepBubble({ r: 0, a: 0 }, 100, 1, false);
    expect(s.r).toBeCloseTo(30);
    expect(s.a).toBeCloseTo(0.2);
  });

  it("reads the accent colour", () => {
    expect(rgbOf("#2563eb")).toBe("37,99,235");
    expect(rgbOf(" rgba(1, 2, 3, 0.5)")).toBe("1,2,3");
    expect(rgbOf("")).toBe("37,99,235");
  });
});
