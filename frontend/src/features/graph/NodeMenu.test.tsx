import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { node } from "./fixtures";
import { MENU_ITEMS, registerMenuItem, visibleItems } from "./menu";
import { NodeMenu } from "./NodeMenu";
import { TOOLS, registerTool } from "./tools";

const ctx = { openReader: vi.fn(), openDetails: vi.fn(), openPage: vi.fn() };

describe("node menu", () => {
  it("lists side reader, details and Pages; picking one runs it and closes", async () => {
    const onClose = vi.fn();
    render(<NodeMenu node={node("idea-margin")} x={10} y={10} colorBy="type" ctx={ctx} onClose={onClose} />);
    expect(screen.getAllByRole("menuitem").map((b) => b.textContent)).toEqual([
      "Open in side readerdouble-click",
      "Show detailslinks · sources",
      "Open in PagesE",
    ]);
    await userEvent.click(screen.getByRole("menuitem", { name: /side reader/i }));
    expect(ctx.openReader).toHaveBeenCalledWith("idea-margin");
    expect(onClose).toHaveBeenCalled();
  });

  it("greys out an entry that does not apply and says why; Esc closes", async () => {
    const onClose = vi.fn();
    const items = [{ id: "g", label: "Genealogy", enabled: (n: { type: string }) => n.type === "paper", why: "papers only", run: vi.fn() }];
    render(<NodeMenu node={node("idea-margin")} x={0} y={0} colorBy="type" ctx={ctx} items={items as never} onClose={onClose} />);
    const item = screen.getByRole("menuitem", { name: /genealogy/i });
    expect(item).toBeDisabled();
    expect(item).toHaveTextContent("papers only");
    await userEvent.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalled();
  });
});

describe("extension points", () => {
  it("registerMenuItem adds or replaces an entry, optionally before another", () => {
    const before = MENU_ITEMS.length;
    registerMenuItem({ id: "genealogy", label: "Citation genealogy", when: (n) => n.type === "paper", run: () => {} }, "page");
    expect(MENU_ITEMS.map((i) => i.id)).toEqual(["reader", "details", "genealogy", "page"]);
    expect(visibleItems(node("x", { type: "idea" })).map((i) => i.id)).not.toContain("genealogy");
    registerMenuItem({ id: "genealogy", label: "Again", run: () => {} });
    expect(MENU_ITEMS).toHaveLength(before + 1);
    MENU_ITEMS.splice(MENU_ITEMS.findIndex((i) => i.id === "genealogy"), 1);
  });

  it("registerTool appends and replaces by id (the core ships none)", () => {
    expect(TOOLS).toHaveLength(0);
    registerTool({ id: "box", label: "Box select", icon: null });
    registerTool({ id: "box", label: "Box", icon: null });
    expect(TOOLS.map((t) => t.label)).toEqual(["Box"]);
    TOOLS.length = 0;
  });
});
