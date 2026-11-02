import { ROUTES } from "./registry";

describe("route registry parity", () => {
  it("every route has a screen", () => {
    for (const r of ROUTES) expect(r.Screen, `${r.id} has no screen`).toBeTypeOf("function");
  });
  it("ids and paths are unique", () => {
    expect(new Set(ROUTES.map((r) => r.id)).size).toBe(ROUTES.length);
    expect(new Set(ROUTES.map((r) => r.path)).size).toBe(ROUTES.length);
  });
  it("Start and Covector are routes with screens", () => {
    for (const id of ["start", "covector"]) {
      const r = ROUTES.find((x) => x.id === id);
      expect(r?.Screen, id).toBeTypeOf("function");
    }
  });
});
