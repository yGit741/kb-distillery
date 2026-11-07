import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DataSourceProvider } from "@/api";
import { captureFooter, useUi } from "@/app/ui-store";
import { withFlag } from "@/flags/testing";
import { useKb } from "@/lib/store";
import { mockDataSource } from "@/test/datasource";
import { node } from "../fixtures";
import { print } from "../layers/grammar";
import { EMPTY_STACK, makeLayer } from "../layers/model";
import { useLayers } from "../layers/store";
import { DEFAULT_PREFS, useGraphUi } from "../store";
import { useChatDock } from "../tools/chatDockStore";
import { GraphShell } from "./GraphShell";
import { useShellStore } from "./shellStore";

const nodes = [
  node("margin-theory", { title: "Margin theory" }),
  node("large-margins", { title: "Large margins" }),
  node("kernel", { title: "Kernel methods" }),
];
const byId = new Map(nodes.map((n) => [n.id, n] as const));

function setup() {
  const ds = mockDataSource({
    search: (async () => ({ hits: [], total: 0 })) as never,
    listRecent: async () => ({ recent: [] }),
    listViews: async () => ({ views: [] }),
    addRecent: vi.fn(async () => ({ recent: [] })),
  });
  render(
    <DataSourceProvider source={ds}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <GraphShell nodes={nodes} byId={byId} colorBy="type" shownTypes={new Set(nodes.map((n) => n.type))} onFocus={vi.fn()} onRead={vi.fn()} onShowExact={vi.fn()} onShowMentions={vi.fn()} onFit={vi.fn()} onZoom={vi.fn()} onReheat={vi.fn()} onRefresh={vi.fn()} />
      </QueryClientProvider>
    </DataSourceProvider>,
  );
  useLayers.getState().setGraph({ nodes, links: [], show: vi.fn() });
}
const box = () => screen.getByRole("combobox", { name: /search the graph/i });

async function menuOn(query: string, row: RegExp) {
  await userEvent.type(box(), query);
  const r = await screen.findByRole("option", { name: row });
  await userEvent.click(within(r).getByRole("button", { name: "Actions" }));
}

beforeEach(() => {
  window.localStorage.clear();
  useChatDock.setState({ open: false, question: "" });
  useUi.setState({ captureOpen: false, captureContext: null });
  useLayers.setState({ stack: EMPTY_STACK, history: [], future: [], applied: null, skipped: [], graph: null });
  useShellStore.setState({ pendingShape: null, pendingView: null, pendingOp: null, notice: null, shaping: false, shape: null, undo: null, shapeError: null });
  useGraphUi.setState({ ...DEFAULT_PREFS, view: null, flyout: null, railOpen: false, readerSlug: null, readerSet: [] });
  useKb.getState().clearSelection();
});

describe("the four menu actions, graph-intent on", () => {
  it("Expand stacks a neighbours layer with its own chip text", () =>
    withFlag("graph-intent", true, async () => {
      setup();
      await menuOn("kernel", /Kernel methods/);
      await userEvent.click(screen.getByRole("menuitem", { name: /^Expand/ }));
      const layers = useLayers.getState().stack.layers;
      expect(layers).toHaveLength(1);
      expect(layers[0]!.text).toBe("neighbors of Kernel methods");
      expect(print(layers[0]!)).toBe('show nodes within 1 hop of "kernel"');
    }));

  it("Expand on a set adds one layer per page", () =>
    withFlag("graph-intent", true, async () => {
      setup();
      await menuOn("margin", /pages mention margin/);
      await userEvent.click(screen.getByRole("menuitem", { name: /^Expand/ }));
      const layers = useLayers.getState().stack.layers;
      expect(layers.map(print).sort()).toEqual(['show nodes within 1 hop of "large-margins"', 'show nodes within 1 hop of "margin-theory"']);
    }));

  it("Read on a set opens the first page with the whole set to step through", () =>
    withFlag("graph-intent", true, async () => {
      setup();
      await menuOn("margin", /pages mention margin/);
      await userEvent.click(screen.getByRole("menuitem", { name: /^Read/ }));
      const st = useGraphUi.getState();
      expect(st.readerSet).toHaveLength(2);
      expect(st.readerSlug).toBe(st.readerSet[0]);
    }));

  it("Think opens the capture with the page ids and the view lines", () =>
    withFlag("graph-intent", true, async () => {
      setup();
      useLayers.getState().apply("stack", [makeLayer("show", "nodes", { nodes: [{ t: "type", value: "paper" }] }), makeLayer("hide", "nodes", { nodes: [{ t: "degree", op: "=", n: 0 }] })]);
      await menuOn("kernel", /Kernel methods/);
      await userEvent.click(screen.getByRole("menuitem", { name: /^Think/ }));
      const ui = useUi.getState();
      expect(ui.captureOpen).toBe(true);
      expect(ui.captureContext).toEqual({ ids: ["kernel"], view: ["show nodes type paper", "hide nodes degree = 0"] });
      expect(captureFooter(ui.captureContext)).toBe("nodes: kernel\nview: show nodes type paper · hide nodes degree = 0");
    }));

  it("Think from a page in a larger focus brings the whole focus", () =>
    withFlag("graph-intent", true, async () => {
      setup();
      useKb.getState().setSelection(["kernel", "margin-theory"]);
      await menuOn("kernel", /Kernel methods/);
      await userEvent.click(screen.getByRole("menuitem", { name: /^Think/ }));
      expect([...(useUi.getState().captureContext?.ids ?? [])].sort()).toEqual(["kernel", "margin-theory"]);
    }));

  it("Chat hands the pages over as the question draft", () =>
    withFlag("graph-intent", true, async () => {
      setup();
      await menuOn("kernel", /Kernel methods/);
      await userEvent.click(screen.getByRole("menuitem", { name: /^Chat/ }));
      expect(useChatDock.getState().question).toMatch(/^About .*kernel/);
    }));
});

describe("the capture footer", () => {
  it("is empty without a context and plain text with one", () => {
    expect(captureFooter(null)).toBe("");
    expect(captureFooter({ ids: [], view: [] })).toBe("");
    expect(captureFooter({ ids: ["a", "b"], view: [] })).toBe("nodes: a, b");
    const many = Array.from({ length: 25 }, (_, i) => `p${i}`);
    expect(captureFooter({ ids: many, view: [] })).toMatch(/p19 and 5 more$/);
  });
});
