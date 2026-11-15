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

  it("offers to add a page's concepts and sources where the screen can draw them; a source has no sources of its own", async () => {
    const grow = { ...ctx, addConcepts: vi.fn(), addSources: vi.fn() };
    const { unmount } = render(<NodeMenu node={node("idea-margin")} x={0} y={0} colorBy="type" ctx={grow} onClose={() => {}} />);
    await userEvent.click(screen.getByRole("menuitem", { name: /add its sources/i }));
    expect(grow.addSources).toHaveBeenCalledWith("idea-margin");
    unmount();
    render(<NodeMenu node={node("p1", { type: "paper", layer: "source" })} x={0} y={0} colorBy="type" ctx={grow} onClose={() => {}} />);
    expect(screen.queryByRole("menuitem", { name: /add its sources/i })).toBeNull();
    await userEvent.click(screen.getByRole("menuitem", { name: /add its concepts/i }));
    expect(grow.addConcepts).toHaveBeenCalledWith("p1");
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
    expect(MENU_ITEMS.map((i) => i.id)).toEqual(["reader", "details", "add-concepts", "add-sources", "genealogy", "page"]);
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
