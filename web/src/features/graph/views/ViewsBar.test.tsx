import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { sampleSnapshot } from "../fixtures";
import { HEADLINE_STORIES, MORE_STORIES } from "../lab/views";
import { DEFAULT_PREFS, useGraphUi } from "../store";
import { toModel } from "../types";
import { ViewsBar } from "./ViewsBar";

const model = toModel(sampleSnapshot());
const visible = new Set(model.nodes.map((n) => n.id));

const setStory = (story: string) => useGraphUi.setState({ ...DEFAULT_PREFS, story });

beforeEach(() => {
  localStorage.clear();
  setStory("map");
});

describe("ViewsBar", () => {
  it("shows the three headline pills and More; the active story is pressed", () => {
    render(<ViewsBar model={model} visible={visible} onPick={vi.fn()} />);
    expect(HEADLINE_STORIES.map((s) => s.headline?.label)).toEqual(["Map", "Thesis", "Explore"]);
    for (const label of ["Map", "Thesis", "Explore"]) expect(screen.getByRole("button", { name: label })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^More/ })).toHaveAttribute("aria-haspopup", "menu");
    expect(screen.getByRole("button", { name: "Map" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Thesis" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.queryByText("custom")).not.toBeInTheDocument();
  });

  it("aria-pressed follows the store's story", () => {
    setStory("thesis");
    render(<ViewsBar model={model} visible={visible} onPick={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Thesis" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Map" })).toHaveAttribute("aria-pressed", "false");
  });

  it("clicking a pill calls onPick with its id", async () => {
    const onPick = vi.fn();
    render(<ViewsBar model={model} visible={visible} onPick={onPick} />);
    await userEvent.click(screen.getByRole("button", { name: "Explore" }));
    expect(onPick).toHaveBeenCalledWith("explore");
  });

  it("shows 'custom' when no story is active", () => {
    setStory("");
    render(<ViewsBar model={model} visible={visible} onPick={vi.fn()} />);
    expect(screen.getByText("custom")).toBeInTheDocument();
    for (const label of ["Map", "Thesis", "Explore"]) expect(screen.getByRole("button", { name: label })).toHaveAttribute("aria-pressed", "false");
  });

  it("More lists the other views, without the lab leftovers", async () => {
    const onPick = vi.fn();
    render(<ViewsBar model={model} visible={visible} onPick={onPick} />);
    await userEvent.click(screen.getByRole("button", { name: /^More/ }));
    const menu = screen.getByRole("menu", { name: "Other views" });
    const items = within(menu).getAllByRole("menuitem").map((b) => b.textContent);
    expect(items).toEqual(MORE_STORIES.map((s) => s.name));
    expect(MORE_STORIES.length).toBeGreaterThan(0);
    for (const bad of ["baseline", "compare", "orient"]) expect(MORE_STORIES.map((s) => s.id)).not.toContain(bad);
    expect(items.join(" ")).not.toMatch(/Before the lab|Compare directions|Orient:/);
    await userEvent.click(within(menu).getByRole("menuitem", { name: /Open questions first/ }));
    expect(onPick).toHaveBeenCalledWith("questions");
  });

  it("the info button opens 'how it is computed' for the active view", async () => {
    render(<ViewsBar model={model} visible={visible} onPick={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "How this view is computed" }));
    const dialog = await screen.findByRole("dialog", { name: "Map: how it is computed" });
    expect(dialog).toHaveTextContent(/p-biased/);
    expect(dialog).toHaveTextContent(`${visible.size} of ${model.nodes.length} pages drawn`);
  });
});
