import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { trackTypesStrip } from "./typesStrip";

type Box = { left: number; top: number; width: number; height: number };
const box = (b: Box) => ({ ...b, right: b.left + b.width, bottom: b.top + b.height }) as DOMRect;

let fire: () => void;
let observed: Element[];

beforeEach(() => {
  observed = [];
  vi.stubGlobal(
    "ResizeObserver",
    class {
      constructor(cb: () => void) {
        fire = cb;
      }
      observe(el: Element) {
        observed.push(el);
      }
      disconnect() {}
      unobserve() {}
    },
  );
  document.body.innerHTML = "";
});
afterEach(() => vi.unstubAllGlobals());

function setup(strip: Box) {
  const canvas = document.createElement("div");
  const el = document.createElement("div");
  el.setAttribute("data-corners", "types");
  document.body.append(canvas, el);
  let sb = strip;
  const spy = vi.fn(() => box(sb));
  el.getBoundingClientRect = spy;
  canvas.getBoundingClientRect = () => box({ left: 10, top: 20, width: 800, height: 600 });
  return { canvas, el, spy, move: (b: Box) => (sb = b) };
}

describe("trackTypesStrip", () => {
  it("measures on mount, then reads from the stored rect without touching the DOM", () => {
    const { canvas, spy } = setup({ left: 110, top: 520, width: 300, height: 24 });
    const t = trackTypesStrip(canvas);
    expect(spy).toHaveBeenCalledTimes(1);
    for (let frame = 0; frame < 60; frame++) expect(t.rect()).toEqual([86, 492, 414, 532]);
    expect(spy).toHaveBeenCalledTimes(1);
    t.dispose();
  });

  it("updates the stored rect when the observer fires", () => {
    const { canvas, el, spy, move } = setup({ left: 110, top: 520, width: 300, height: 24 });
    const t = trackTypesStrip(canvas);
    expect(observed).toContain(el);
    move({ left: 110, top: 520, width: 100, height: 24 });
    expect(t.rect()).toEqual([86, 492, 414, 532]); // stale until the observer fires
    fire();
    expect(spy).toHaveBeenCalledTimes(2);
    expect(t.rect()).toEqual([86, 492, 214, 532]);
    t.dispose();
  });

  it("ignores unrelated DOM insertions, but notices the strip being replaced", async () => {
    const { canvas, el, spy } = setup({ left: 110, top: 520, width: 300, height: 24 });
    const t = trackTypesStrip(canvas);
    expect(spy).toHaveBeenCalledTimes(1);
    for (let i = 0; i < 5; i++) document.body.append(document.createElement("span"));
    await new Promise((r) => setTimeout(r, 0));
    expect(spy).toHaveBeenCalledTimes(1);
    el.remove();
    await new Promise((r) => setTimeout(r, 0));
    expect(t.rect()).toBeNull();
    t.dispose();
  });

  it("re-measures on window resize and is null when the strip is absent or empty", () => {
    const { canvas, el, move } = setup({ left: 110, top: 520, width: 300, height: 24 });
    const t = trackTypesStrip(canvas);
    move({ left: 110, top: 500, width: 300, height: 24 });
    window.dispatchEvent(new Event("resize"));
    expect(t.rect()?.[1]).toBe(472);
    move({ left: 0, top: 0, width: 0, height: 0 });
    window.dispatchEvent(new Event("resize"));
    expect(t.rect()).toBeNull();
    move({ left: 110, top: 520, width: 300, height: 24 });
    window.dispatchEvent(new Event("resize"));
    el.remove();
    window.dispatchEvent(new Event("resize"));
    expect(t.rect()).toBeNull();
    t.dispose();
  });
});
