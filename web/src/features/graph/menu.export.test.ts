import { withFlag } from "@/flags/testing";
import { node } from "./fixtures";
import { ACTION_ITEMS, setActionItems } from "./menu";

const item = () => ACTION_ITEMS.find((i) => i.id === "export")!;

describe("export action", () => {
  it("flag on: runs exportPages with the node, or with the set", () => {
    withFlag("graph-intent", true, () => {
      const exportPages = vi.fn();
      const ctx = { openReader: vi.fn(), openDetails: vi.fn(), openPage: vi.fn(), exportPages };
      expect(item().enabled?.(node("a"))).toBe(true);
      item().run(node("a"), ctx);
      expect(exportPages).toHaveBeenCalledWith(["a"]);
      setActionItems(["x", "y"], "set").find((i) => i.id === "export")!.run(node("a"), ctx);
      expect(exportPages).toHaveBeenLastCalledWith(["x", "y"]);
    });
  });
  it("flag off: the slot stays disabled", () => {
    withFlag("graph-intent", false, () => expect(item().enabled?.(node("a"))).toBe(false));
  });
});
