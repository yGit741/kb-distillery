import { afterEach, describe, expect, it } from "vitest";
import { readCanvasColors } from "./theme";

afterEach(() => {
  document.documentElement.style.removeProperty("--node-centre");
  document.documentElement.style.removeProperty("--card");
});

describe("node centres", () => {
  it("fill hollow marks with --node-centre, one step above the ground; halos keep the card", () => {
    document.documentElement.style.setProperty("--card", "#ffffff");
    document.documentElement.style.setProperty("--node-centre", "#f8f6f1");
    expect(readCanvasColors().nodeCentre).toBe("#f8f6f1");
    expect(readCanvasColors().background).toBe("#ffffff"); // label halos and badges keep the card colour
  });

  it("fall back to the card colour where --node-centre is not defined", () => {
    document.documentElement.style.setProperty("--card", "#ffffff");
    expect(readCanvasColors().nodeCentre).toBe("#ffffff");
  });
});
