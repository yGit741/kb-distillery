import { CONCEPT_KINDS, COLLECTION_KINDS, SOURCE_KINDS } from "@/api/model";
import { areaColor, AREA_COLORS, depthColor, KIND_COLORS, kindColor, typeColor, UNKNOWN_COLOR } from "./palette";

describe("palette", () => {
  it("colours every kind of the data model", () => {
    for (const k of [...SOURCE_KINDS, ...COLLECTION_KINDS, ...CONCEPT_KINDS]) {
      expect(KIND_COLORS[k]).toMatch(/^#[0-9a-f]{6}$/i);
    }
  });
  it("keeps the legacy values per kind", () => {
    expect(kindColor("paper")).toBe("#ff6b7a");
    expect(kindColor("topic")).toBe("#9ece6a");
    expect(kindColor("idea")).toBe("#7aa2ff");
    expect(kindColor("scope")).toBe("#e6c07b");
  });
  it("falls back for unknown keys, including prototype names", () => {
    expect(kindColor("nope")).toBe(UNKNOWN_COLOR);
    expect(kindColor("constructor")).toBe(UNKNOWN_COLOR);
    expect(typeColor(undefined)).toBe(UNKNOWN_COLOR);
    expect(depthColor("deep")).not.toBe(UNKNOWN_COLOR);
  });
  it("hashes areas stably into the area palette", () => {
    expect(areaColor("info-theory")).toBe(areaColor("info-theory"));
    expect(AREA_COLORS).toContain(areaColor("quantum"));
    expect(AREA_COLORS).toContain(areaColor(null));
  });
});
