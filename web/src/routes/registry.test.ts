import { ROUTES, legacyHref } from "./registry";

describe("route registry parity", () => {
  it("every route has a ported screen or a legacy card with a valid /legacy link", () => {
    for (const r of ROUTES) {
      if (r.ported) {
        expect(r.Screen, `${r.id} is ported but has no screen`).toBeTypeOf("function");
      } else {
        expect(legacyHref(r), `${r.id} legacy link`).toMatch(/^\/legacy(\/[a-z0-9-]+)*$/);
        expect(r.legacy.startsWith("/"), `${r.id} legacy path`).toBe(true);
      }
    }
  });
  it("ids and paths are unique", () => {
    expect(new Set(ROUTES.map((r) => r.id)).size).toBe(ROUTES.length);
    expect(new Set(ROUTES.map((r) => r.path)).size).toBe(ROUTES.length);
  });
  it("Start and Covector are ported screens", () => {
    for (const id of ["start", "covector"]) {
      const r = ROUTES.find((x) => x.id === id);
      expect(r?.ported, id).toBe(true);
      expect(r?.Screen, id).toBeTypeOf("function");
    }
  });
});
