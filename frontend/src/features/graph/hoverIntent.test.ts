import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createHoverIntent, createSpeedMeter, HOVER_TUNING } from "./hoverIntent";

function setup(enabled = true) {
  let focus: string | null = null;
  let speed = 0;
  const commits: (string | null)[] = [];
  const intent = createHoverIntent({
    commit: (id) => {
      focus = id;
      commits.push(id);
    },
    committed: () => focus,
    speed: () => speed,
    enabled: () => enabled,
  });
  return { intent, commits, setSpeed: (v: number) => (speed = v), focus: () => focus };
}

describe("hover intent", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("focuses a page only after the pointer rests on it", () => {
    const h = setup();
    h.intent.request("a");
    expect(h.intent.pointed()).toBe("a");
    vi.advanceTimersByTime(HOVER_TUNING.dwell - 10);
    expect(h.focus()).toBeNull();
    vi.advanceTimersByTime(20);
    expect(h.focus()).toBe("a");
  });

  it("a sweep across pages commits nothing", () => {
    const h = setup();
    h.setSpeed(40);
    for (const id of ["a", "b", "c", "d"]) {
      h.intent.request(id);
      vi.advanceTimersByTime(60);
    }
    h.intent.request(null);
    vi.advanceTimersByTime(1000);
    expect(h.commits).toEqual([]);
  });

  it("waits while the pointer still moves fast, then commits once it slows", () => {
    const h = setup();
    h.setSpeed(40);
    h.intent.request("a");
    vi.advanceTimersByTime(400);
    expect(h.focus()).toBeNull();
    h.setSpeed(0);
    vi.advanceTimersByTime(50);
    expect(h.focus()).toBe("a");
  });

  it("leaving keeps the focus for a grace period; reaching another page switches straight to it", () => {
    const h = setup();
    h.intent.request("a");
    vi.advanceTimersByTime(200);
    h.intent.request(null);
    vi.advanceTimersByTime(HOVER_TUNING.grace - 50);
    expect(h.focus()).toBe("a");
    h.intent.request("b");
    vi.advanceTimersByTime(HOVER_TUNING.switchDwell + 5);
    expect(h.commits).toEqual(["a", "b"]); // never back to null in between
  });

  it("commits at once when calm hover is off", () => {
    const h = setup(false);
    h.intent.request("a");
    expect(h.focus()).toBe("a");
    h.intent.request(null);
    expect(h.focus()).toBeNull();
  });
});

describe("speed meter", () => {
  it("reads px per 100 ms and drops to 0 once the pointer rests", () => {
    const m = createSpeedMeter();
    m.note(0, 0, 0);
    m.note(20, 0, 50);
    expect(m.speed(60)).toBeCloseTo(40);
    expect(m.speed(200)).toBe(0);
  });
  it("does not blow up on coalesced events a few ms apart", () => {
    const m = createSpeedMeter();
    m.note(0, 0, 0);
    m.note(1, 0, 2);
    expect(m.speed(3)).toBeLessThan(HOVER_TUNING.speed);
  });
});
