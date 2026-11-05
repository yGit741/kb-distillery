import { renderHook } from "@testing-library/react";
import { withFlag } from "@/flags/testing";
import { HEADER_FOLD_KEY, readFolded, useHeaderFold, useHeaderFolded } from "./headerFold";

beforeEach(() => {
  localStorage.clear();
  useHeaderFold.setState({ folded: true });
});

describe("header fold store", () => {
  it("is folded by default and reads the last choice", () => {
    expect(readFolded()).toBe(true);
    localStorage.setItem(HEADER_FOLD_KEY, "0");
    expect(readFolded()).toBe(false);
    localStorage.setItem(HEADER_FOLD_KEY, "1");
    expect(readFolded()).toBe(true);
  });

  it("remembers a toggle in this browser", () => {
    useHeaderFold.getState().toggle();
    expect(useHeaderFold.getState().folded).toBe(false);
    expect(localStorage.getItem(HEADER_FOLD_KEY)).toBe("0");
    useHeaderFold.getState().set(true);
    expect(localStorage.getItem(HEADER_FOLD_KEY)).toBe("1");
  });

  it("survives a storage that throws", () => {
    const get = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const set = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(readFolded()).toBe(true);
    expect(() => useHeaderFold.getState().set(false)).not.toThrow();
    expect(useHeaderFold.getState().folded).toBe(false);
    get.mockRestore();
    set.mockRestore();
  });
});

describe("flag header-fold", () => {
  it("on: folded on the graph with the shell, never off the graph", () =>
    withFlag("header-fold", true, () =>
      withFlag("graph-shell", true, () => {
        expect(renderHook(() => useHeaderFolded(true)).result.current).toBe(true);
        expect(renderHook(() => useHeaderFolded(false)).result.current).toBe(false);
      }),
    ));

  it("on without the shell: the bar stays", () =>
    withFlag("header-fold", true, () =>
      withFlag("graph-shell", false, () => {
        expect(renderHook(() => useHeaderFolded(true)).result.current).toBe(false);
      }),
    ));

  it("off: the bar never folds", () =>
    withFlag("header-fold", false, () =>
      withFlag("graph-shell", true, () => {
        expect(renderHook(() => useHeaderFolded(true)).result.current).toBe(false);
      }),
    ));
});
