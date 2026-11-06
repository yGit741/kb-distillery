import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DataSourceProvider } from "@/api";
import { withFlag } from "@/flags/testing";
import { useKb } from "@/lib/store";
import { mockDataSource } from "@/test/datasource";
import { node } from "../fixtures";
import { EMPTY_STACK } from "../layers/model";
import { useLayers } from "../layers/store";
import { DEFAULT_PREFS, useGraphUi } from "../store";
import { useChatDock } from "../tools/chatDockStore";
import { GraphShell } from "./GraphShell";
import { useShellStore } from "./shellStore";

const nodes = [
  node("margin-theory", { title: "Margin theory", inDegree: 3, properties: { tags: "learning" } }),
  node("large-margins", { title: "Large margins", properties: { aliases: "margin bounds" } }),
  node("tagged", { title: "Unrelated page", properties: { tags: "margin" } }),
  node("margin-thoughts", { title: "Margin thoughts", type: "think-note" }),
  node("kernel", { title: "Kernel methods" }),
];
const byId = new Map(nodes.map((n) => [n.id, n] as const));
const SHOWN = new Set(nodes.map((n) => n.type));

function setup(over: { search?: () => Promise<unknown>; onFocus?: (id: string) => void } = {}) {
  const onFocus = over.onFocus ?? vi.fn();
  const ds = mockDataSource({
    search: (over.search ?? (async () => ({ hits: [], total: 0 }))) as never,
    listRecent: async () => ({ recent: [] }),
    listViews: async () => ({ views: [{ id: "v1", name: "Margin reading", spec: {} }] }) as never,
    addRecent: vi.fn(async () => ({ recent: [] })),
  });
  render(
    <DataSourceProvider source={ds}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <GraphShell nodes={nodes} byId={byId} colorBy="type" shownTypes={SHOWN} onFocus={onFocus} onRead={vi.fn()} onShowExact={vi.fn()} onShowMentions={vi.fn()} onFit={vi.fn()} onZoom={vi.fn()} onReheat={vi.fn()} onRefresh={vi.fn()} />
      </QueryClientProvider>
    </DataSourceProvider>,
  );
  return { onFocus };
}

const box = () => screen.getByRole("combobox", { name: /search the graph/i });
const headings = () => screen.queryAllByRole("group").map((g) => g.firstElementChild?.textContent);

beforeEach(() => {
  window.localStorage.clear();
  useChatDock.setState({ open: false, question: "" });
  useLayers.setState({ stack: EMPTY_STACK, history: [], future: [], applied: null, skipped: [], graph: null });
  useShellStore.setState({ pendingShape: null, pendingView: null, pendingOp: null, notice: null, shaping: false, shape: null, undo: null, shapeError: null });
  useGraphUi.setState({ ...DEFAULT_PREFS, view: null, flyout: null, railOpen: false });
  useKb.getState().clearSelection();
});

describe("grouped search, graph-intent on", () => {
  it("shows the groups in a fixed order and only the non-empty ones", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      await userEvent.type(box(), "margin");
      expect(await screen.findByRole("option", { name: /Margin theory/ })).toBeInTheDocument();
      expect(headings()).toEqual(["Pages", "Think notes", "Sets", "Views", "Actions"]);
      expect(screen.getByRole("option", { name: /4 pages mention margin/ })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: "Margin reading" })).toBeInTheDocument();
      await userEvent.clear(box());
      await userEvent.type(box(), "fit");
      expect(await screen.findByRole("option", { name: /Fit to view/ })).toBeInTheDocument();
      expect(headings()).toEqual(["Commands", "Actions"]);
    });
  });

  it("puts a page found by title and by text once in Pages, with one mark", async () => {
    await withFlag("graph-intent", true, async () => {
      setup({ search: async () => ({ hits: [{ id: "margin-theory", title: "Margin theory", snippet: "about margin", score: 1 }], total: 1, related: [{ id: "margin-theory", title: "Margin theory", snippet: "", score: 1 }] }) });
      await userEvent.type(box(), "margin");
      await screen.findByRole("option", { name: /Margin theory/ });
      await new Promise((r) => setTimeout(r, 400));
      expect(screen.getAllByRole("option", { name: /Margin theory/ })).toHaveLength(1);
      const row = screen.getByRole("option", { name: /Margin theory/ });
      expect(within(row).getByText("text · meaning")).toBeInTheDocument();
      expect(headings()).not.toContain("Related by meaning");
    });
  });

  it("Enter focuses the highlighted page; Shift+Enter adds a page to the focus", async () => {
    await withFlag("graph-intent", true, async () => {
      const { onFocus } = setup();
      await userEvent.type(box(), "margin");
      await screen.findByRole("option", { name: /Margin theory/ });
      await userEvent.keyboard("{Enter}");
      expect(onFocus).toHaveBeenCalledWith("margin-theory");
      useKb.getState().setSelection(["margin-theory"]);
      await userEvent.type(box(), "margin");
      await screen.findByRole("option", { name: /Large margins/ });
      await userEvent.keyboard("{ArrowDown}{Shift>}{Enter}{/Shift}");
      expect([...useKb.getState().selection].sort()).toEqual(["large-margins", "margin-theory"]);
    });
  });

  it("Enter on a set row highlights the set; its menu turns it into a view layer", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      useLayers.getState().setGraph({ nodes, links: [], show: vi.fn() });
      await userEvent.type(box(), "margin");
      const set = await screen.findByRole("option", { name: /pages mention margin/ });
      expect(set).toBeInTheDocument();
      await userEvent.keyboard("{ArrowDown}{ArrowDown}{ArrowDown}{Enter}");
      expect([...useKb.getState().selection].sort()).toEqual(["large-margins", "margin-theory", "margin-thoughts", "tagged"]);
      useKb.getState().clearSelection();
      await userEvent.type(box(), "margin");
      const row = await screen.findByRole("option", { name: /pages mention margin/ });
      await userEvent.click(within(row).getByRole("button", { name: "Actions" }));
      expect(screen.getAllByRole("menuitem").map((b) => b.textContent?.replace(/(Enter|these pages|on top|by type|ask about them|OKF bundle|one after another|add its neighbours|quick note)$/, ""))).toEqual(["Highlight", "Show only", "Read", "Expand", "Think", "Add to view", "Color", "Chat about these", "Export"]);
      await userEvent.click(screen.getByRole("menuitem", { name: /Show only/ }));
      const layers = useLayers.getState().stack.layers;
      expect(layers).toHaveLength(1);
      expect(layers[0]).toMatchObject({ kind: "show", target: "nodes" });
      expect(layers[0]!.subgraph.nodes).toEqual([{ t: "name", slugs: expect.arrayContaining(["margin-theory", "tagged"]) }]);
    });
  });

  it("opens the same eight-action menu on a page row, by the control and by the right arrow", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      await userEvent.type(box(), "kernel");
      const row = await screen.findByRole("option", { name: /Kernel methods/ });
      await userEvent.click(within(row).getByRole("button", { name: "Actions" }));
      const items = screen.getAllByRole("menuitem");
      expect(items.map((b) => b.textContent?.split(/(?=[A-Z][a-z]*$)/)[0])).toHaveLength(8);
      expect(items.map((b) => b.textContent)).toEqual([
        "FocusEnter",
        "Show onlythis page",
        "Readbeside the graph",
        "Expandadd its neighbours",
        "Favoritekeep it close",
        "Chatask about it",
        "Thinkquick note",
        "ExportOKF bundle",
      ]);
      expect(items.filter((b) => (b as HTMLButtonElement).disabled).map((b) => b.textContent)).toEqual([]);
      await userEvent.keyboard("{Escape}");
      expect(screen.queryByRole("menu")).not.toBeInTheDocument();
      await userEvent.keyboard("{ArrowRight}");
      expect(await screen.findByRole("menu")).toBeInTheDocument();
    });
  });

  it("the menu's Show only puts the page alone in the view as a layer", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      useLayers.getState().setGraph({ nodes, links: [], show: vi.fn() });
      await userEvent.type(box(), "kernel");
      await screen.findByRole("option", { name: /Kernel methods/ });
      await userEvent.keyboard("{ArrowRight}");
      await userEvent.click(await screen.findByRole("menuitem", { name: /Show only/ }));
      expect(useLayers.getState().stack.layers[0]?.subgraph.nodes).toEqual([{ t: "name", slugs: ["kernel"] }]);
    });
  });
});

describe("grouped search, graph-intent off", () => {
  it("keeps today's panel: no groups, no row menu", async () => {
    await withFlag("graph-intent", false, async () => {
      setup();
      await userEvent.type(box(), "margin");
      await screen.findByRole("option", { name: /Margin theory/ });
      expect(headings()).not.toContain("Sets");
      expect(screen.queryByRole("button", { name: "Actions" })).not.toBeInTheDocument();
      expect(screen.getByRole("option", { name: /show pages mentioning/i })).toBeInTheDocument();
    });
  });
});
