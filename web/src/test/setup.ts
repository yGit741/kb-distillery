import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";
import { afterEach } from "vitest";
import { pinFlag } from "@/flags/testing";

afterEach(() => cleanup());

// inside a ship gate (KB_GATE_SLOT_HELD) a `findBy*` / `waitFor` gets 10 s instead of the 1 s default: on a host at
// load 30-60 the render it waits for arrives late and the wait, not the test, is what fails; a developer's own run keeps the default
if (process.env.KB_GATE_SLOT_HELD) configure({ asyncUtilTimeout: 10_000 });

// jsdom lacks these; cmdk and the layout code touch them.
if (!window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false, media: query, onchange: null,
    addEventListener: () => {}, removeEventListener: () => {},
    addListener: () => {}, removeListener: () => {}, dispatchEvent: () => false,
  })) as typeof window.matchMedia;
}
class RO { observe() {} unobserve() {} disconnect() {} }
(globalThis as { ResizeObserver?: unknown }).ResizeObserver ??= RO;
Element.prototype.scrollIntoView ??= () => {};
window.scrollTo = (() => {}) as typeof window.scrollTo;

// Node >= 22 ships an experimental `localStorage` global that shadows jsdom's; without
// --localstorage-file it has no working methods (`localStorage.clear is not a function`).
// Install a Map-backed Storage whenever the one in scope is not a real one.
function memoryStorage(): Storage {
  const m = new Map<string, string>();
  return {
    get length() { return m.size; },
    clear: () => m.clear(),
    getItem: (k: string) => (m.has(String(k)) ? m.get(String(k))! : null),
    key: (i: number) => Array.from(m.keys())[i] ?? null,
    removeItem: (k: string) => { m.delete(String(k)); },
    setItem: (k: string, v: string) => { m.set(String(k), String(v)); },
  } as Storage;
}
for (const name of ["localStorage", "sessionStorage"] as const) {
  let ok = false;
  try { ok = typeof globalThis[name]?.clear === "function"; } catch { ok = false; }
  if (!ok) {
    const s = memoryStorage();
    Object.defineProperty(globalThis, name, { value: s, configurable: true, writable: true });
    Object.defineProperty(window, name, { value: s, configurable: true, writable: true });
  }
}

// Flag ui.data-system-split is on in the local app, so it would reshape every screen test. Suites keep the layout they
// were written against; the split's own tests switch it on with withFlag("ui.data-system-split", true, …).
pinFlag("ui.data-system-split", false);
