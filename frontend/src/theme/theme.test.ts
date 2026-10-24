import { THEME_KEY, useTheme } from "./theme";

describe("theme toggle", () => {
  beforeEach(() => {
    localStorage.clear();
    useTheme.getState().set("light");
    localStorage.clear();
  });
  it("persists the choice and flips the html class", () => {
    useTheme.getState().toggle();
    expect(useTheme.getState().theme).toBe("dark");
    expect(localStorage.getItem(THEME_KEY)).toBe("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    useTheme.getState().toggle();
    expect(localStorage.getItem(THEME_KEY)).toBe("light");
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });
  it("survives storage that throws", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(() => useTheme.getState().toggle()).not.toThrow();
    expect(useTheme.getState().theme).toBe("dark");
    spy.mockRestore();
  });
});
