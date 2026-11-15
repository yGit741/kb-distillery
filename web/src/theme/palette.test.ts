import { LAYER_TYPES } from "@/api/model";
import { areaColor, AREA_COLORS, depthColor, layerColor, statusColor, supportColor, SUPPORT_COLORS, SUPPORT_COLORS_DARK, typeColor, TYPE_COLORS, UNKNOWN_COLOR } from "./palette";

describe("palette", () => {
  it("colours every type of every layer", () => {
    for (const types of Object.values(LAYER_TYPES)) {
      for (const t of types) expect(TYPE_COLORS[t]).toMatch(/^#[0-9a-f]{6}$/i);
    }
  });
  it("keeps the legacy values per type", () => {
    expect(typeColor("paper")).toBe("#ff6b7a");
    expect(typeColor("topic")).toBe("#9ece6a");
    expect(typeColor("idea")).toBe("#7aa2ff");
    expect(typeColor("scope")).toBe("#e6c07b");
    expect(layerColor("collection")).toBe(typeColor("book"));
  });
  it("falls back for unknown keys, including prototype names", () => {
    expect(typeColor("nope")).toBe(UNKNOWN_COLOR);
    expect(typeColor("constructor")).toBe(UNKNOWN_COLOR);
    expect(layerColor(undefined)).toBe(UNKNOWN_COLOR);
    expect(depthColor("bogus")).toBe(UNKNOWN_COLOR);
    expect(depthColor("deep")).not.toBe(UNKNOWN_COLOR);
    expect(statusColor("digested")).toBe("#9ece6a");
  });
  it("has a support colour per ground, the light set unless the dark ground is asked for", () => {
    for (const k of ["none", "one", "many"] as const) {
      expect(supportColor(k)).toBe(SUPPORT_COLORS[k]);
      expect(supportColor(k, true)).toBe(SUPPORT_COLORS_DARK[k]);
      expect(SUPPORT_COLORS_DARK[k]).not.toBe(SUPPORT_COLORS[k]);
    }
  });
  it("hashes areas stably into the area palette", () => {
    expect(areaColor("info-theory")).toBe(areaColor("info-theory"));
    expect(AREA_COLORS).toContain(areaColor("quantum"));
    expect(AREA_COLORS).toContain(areaColor(null));
  });
});
