import { withFlag } from "@/flags/testing";
import { useCorners } from "./cornersStore";

const KEY = "kb-graph-legends-folded";

describe("graph-corners: the legend opens on every page load", () => {
  it("on: a fold remembered from an earlier visit is opened once, and a new fold is not remembered", () =>
    withFlag("graph-corners", true, () => {
      localStorage.setItem(KEY, JSON.stringify(["legend"]));
      useCorners.setState({ order: ["types"] });
      useCorners.getState().openLegendsOnce();
      expect(useCorners.getState().order).toEqual(["legend", "types"]);
      useCorners.getState().toggle("legend");
      expect(useCorners.getState().order).not.toContain("legend");
      expect(JSON.parse(localStorage.getItem(KEY)!)).toEqual(["legend"]); // unchanged: nothing written
      useCorners.getState().openLegendsOnce(); // once per page load: a fold in this load stays
      expect(useCorners.getState().order).not.toContain("legend");
    }));

  it("off: folding the legend is remembered", () =>
    withFlag("graph-corners", false, () => {
      localStorage.removeItem(KEY);
      useCorners.setState({ order: ["legend", "types"] });
      useCorners.getState().toggle("legend");
      expect(JSON.parse(localStorage.getItem(KEY)!)).toEqual(["legend"]);
    }));
});
