import { describe, expect, it } from "vitest";
import { VARIANTS } from "@/components/variants";
import { placeFor, SEARCH_LINE_H, SWITCH_H, VIEW_SWITCH_IDS, VIEW_SWITCH_MIN_FRAME, viewSwitchBox } from "./layout";

const ROW = "min(640px, calc(100% - 9rem))";
const START = `calc(50% - ${ROW} / 2)`;

describe("the Concepts / Sources switch beside the search line", () => {
  it("registers every place as a variant, the quiet switch by default", () => {
    expect(VARIANTS["view-switch"]!.options.map((o) => o.id)).toEqual([...VIEW_SWITCH_IDS]);
    expect(VARIANTS["view-switch"]!.default).toBe("quiet");
  });

  it("quiet: its own gap before the line, shorter than the line and centred on it, every corner of the line kept", () => {
    const b = viewSwitchBox("quiet");
    expect(b.left).toBe(START);
    expect(b.barLeft).toBe(`calc(${START} + 180px)`);
    expect(b.barWidth).toBe(`calc(${ROW} - 180px)`);
    expect(b.dy).toBe((SEARCH_LINE_H - SWITCH_H) / 2);
    expect(b.square).toBeNull();
  });

  it("words and icons take less room; the dock meets the line with one squared seam at the line's height", () => {
    expect(viewSwitchBox("words").barWidth).toBe(`calc(${ROW} - 148px)`);
    expect(viewSwitchBox("icons")).toMatchObject({ width: 68, barWidth: `calc(${ROW} - 80px)` });
    expect(viewSwitchBox("dock")).toMatchObject({ width: 172, barLeft: `calc(${START} + 172px)`, dy: 0, square: "left" });
  });

  it("a tab hangs under the line and leaves it as it was", () => {
    expect(viewSwitchBox("tab")).toMatchObject({ barWidth: ROW, left: "50%", dy: SEARCH_LINE_H - 1, square: null });
    expect(viewSwitchBox(null)).toEqual(viewSwitchBox("tab"));
  });

  it("a narrow graph area falls back to the tab so the line keeps its width; unmeasured keeps the choice", () => {
    expect(placeFor("quiet", VIEW_SWITCH_MIN_FRAME - 1)).toBe("tab");
    expect(placeFor("quiet", VIEW_SWITCH_MIN_FRAME)).toBe("quiet");
    expect(placeFor("dock", 0)).toBe("dock");
  });
});
