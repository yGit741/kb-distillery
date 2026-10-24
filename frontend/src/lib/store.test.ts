import { useKb } from "./store";

const reset = () => useKb.setState({ selection: new Set(), scopeDraftId: null });

describe("kb store", () => {
  beforeEach(reset);

  it("selects, deselects and toggles slugs", () => {
    const s = useKb.getState();
    s.select("paper-a");
    s.select("paper-a");
    s.toggle("paper-b");
    expect([...useKb.getState().selection]).toEqual(["paper-a", "paper-b"]);
    useKb.getState().deselect("paper-a");
    useKb.getState().toggle("paper-b");
    expect(useKb.getState().selection.size).toBe(0);
  });

  it("replaces the selection and clears it", () => {
    useKb.getState().setSelection(["x", "y", "x"]);
    expect([...useKb.getState().selection]).toEqual(["x", "y"]);
    useKb.getState().clearSelection();
    expect(useKb.getState().selection.size).toBe(0);
  });

  it("never mutates the previous set (subscribers see a new reference)", () => {
    const before = useKb.getState().selection;
    useKb.getState().select("a");
    expect(useKb.getState().selection).not.toBe(before);
    expect(before.size).toBe(0);
  });

  it("keeps the scope draft id", () => {
    useKb.getState().setScopeDraft("draft-1");
    expect(useKb.getState().scopeDraftId).toBe("draft-1");
    useKb.getState().setScopeDraft(null);
    expect(useKb.getState().scopeDraftId).toBeNull();
  });
});
