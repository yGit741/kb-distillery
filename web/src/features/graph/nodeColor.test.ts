import { useTheme } from "@/theme/theme";
import { node } from "./fixtures";
import { swatchColor } from "./nodeColor";
import { colorOf } from "./style";

describe("swatchColor", () => {
  const n = node("idea-margin", { type: "idea", inDegree: 40, outDegree: 10 });

  it("colours a swatch like its node when an ordered colouring uses the theme ramp", () => {
    for (const theme of ["light", "dark"] as const) {
      useTheme.setState({ theme });
      expect(swatchColor(n, "degree")).toBe(colorOf(n, "degree", undefined, theme));
    }
    // the unramped band colour is a different, stronger colour: it must not leak into chips
    useTheme.setState({ theme: "light" });
    expect(swatchColor(n, "degree")).not.toBe(colorOf(n, "degree"));
  });

  it("leaves categorical colourings as they were", () => {
    expect(swatchColor(n, "area")).toBe(colorOf(n, "area"));
  });
});
