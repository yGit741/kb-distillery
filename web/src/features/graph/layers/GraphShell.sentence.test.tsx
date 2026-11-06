import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DataSourceProvider, type ShapeResult } from "@/api";
import { withFlag } from "@/flags/testing";
import { useKb } from "@/lib/store";
import { mockDataSource } from "@/test/datasource";
import { node, sampleLinks, sampleNodes } from "../fixtures";
import { LINE_COPY } from "../shell/copy";
import { GraphShell } from "../shell/GraphShell";
import { useShellStore } from "../shell/shellStore";
import { DEFAULT_PREFS, useGraphUi } from "../store";
import { EMPTY_STACK } from "./model";
import { useLayers } from "./store";

const nodes = [...sampleNodes, node("learning-curves", { title: "Learning curves" }), node("learning-rates", { title: "Learning rates" })];
const SHOWN = new Set(nodes.map((n) => n.type));
const byId = new Map(nodes.map((n) => [n.id, n] as const));
const shapeGraph = vi.fn(async (): Promise<ShapeResult> => ({ columns: [], rows: [], row_count: 0, truncated: false, cypher: null, style: { hide_edge_kinds: [], hide_labels: [] }, style_text: "", source: "cypher", explanation: "", warnings: [] }));

function setup() {
  const ds = mockDataSource({
    search: async () => ({ hits: [], total: 0 }),
    listRecent: async () => ({ recent: [] }),
    listViews: async () => ({ views: [] }),
    addRecent: vi.fn(async () => ({ recent: [] })),
    shapeGraph,
  });
  return render(
    <DataSourceProvider source={ds}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <GraphShell nodes={nodes} links={sampleLinks} byId={byId} colorBy="type" shownTypes={SHOWN} onFocus={vi.fn()} onRead={vi.fn()} onShowExact={vi.fn()} onShowMentions={vi.fn()} onFit={vi.fn()} onZoom={vi.fn()} onReheat={vi.fn()} onRefresh={vi.fn()} />
      </QueryClientProvider>
    </DataSourceProvider>,
  );
}

const box = () => screen.getByRole("combobox", { name: /search the graph/i });

beforeEach(() => {
  window.localStorage.clear();
  shapeGraph.mockClear();
  useLayers.setState({ stack: EMPTY_STACK, history: [], future: [], applied: null, skipped: [], graph: null });
  useShellStore.setState({ pendingShape: null, pendingView: null, pendingOp: null, notice: null, shaping: false, shape: null, undo: null, shapeError: null });
  useGraphUi.setState({ ...DEFAULT_PREFS, view: null, flyout: null, railOpen: false });
  useKb.getState().clearSelection();
});

describe("a > sentence read by the grammar (graph-intent)", () => {
  it("on: Enter applies the layers and shows a chip, without asking the shape endpoint", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      await userEvent.type(box(), "> only orphans{Enter}{Enter}");
      const view = await screen.findByRole("group", { name: "View" });
      expect(view).toHaveTextContent("only orphans");
      expect(useLayers.getState().stack.layers.map((l) => l.subgraph.nodes)).toEqual([[{ t: "degree", op: "=", n: 0 }]]);
      expect(shapeGraph).not.toHaveBeenCalled();
    });
  });

  it("on: several layers get their own chips, written in the language", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      await userEvent.type(box(), ">+ only supports edges, color by type{Enter}{Enter}");
      await waitFor(() => expect(useLayers.getState().stack.layers).toHaveLength(2));
      expect(useLayers.getState().stack.layers.map((l) => l.text)).toEqual(["show edges type supports", "style nodes color by type"]);
    });
  });

  it("on: a name that fits several pages shows did-you-mean, and picking one applies", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      await userEvent.type(box(), "> only pages within 2 hops of Learning{Enter}");
      expect(await screen.findByText(LINE_COPY.didYouMean("Learning"))).toBeInTheDocument();
      expect(useLayers.getState().stack.layers).toHaveLength(0);
      await userEvent.click(await screen.findByRole("option", { name: /Learning curves/ }));
      expect(useLayers.getState().stack.layers).toHaveLength(0);
      await userEvent.type(box(), "{Enter}");
      await waitFor(() => expect(useLayers.getState().stack.layers).toHaveLength(1));
      expect(useLayers.getState().stack.layers[0]!.subgraph.nodes).toEqual([{ t: "hops", n: 2, of: "learning-curves" }]);
    });
  });

  it("on: a name no page has says so and applies nothing", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      await userEvent.type(box(), "> leaves within 2 hops of Zebra crossing{Enter}");
      await waitFor(() => expect(useShellStore.getState().notice?.text).toBe(LINE_COPY.noSuchPage("Zebra crossing")));
      expect(useLayers.getState().stack.layers).toHaveLength(0);
    });
  });

  it("on: text the rules cannot read falls through to the shape path and says so", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      const said: (string | undefined)[] = [];
      const off = useShellStore.subscribe((st) => said.push(st.notice?.text));
      await userEvent.type(box(), "> make it feel calmer{Enter}");
      await waitFor(() => expect(shapeGraph).toHaveBeenCalled());
      off();
      expect(said).toContain(LINE_COPY.sentenceFallback);
    });
  });

  it("off: no layers, the line is plain search", async () => {
    await withFlag("graph-intent", false, async () => {
      setup();
      await userEvent.type(box(), "only orphans{Enter}");
      expect(useLayers.getState().stack.layers).toHaveLength(0);
      expect(screen.queryByRole("group", { name: "View" })).not.toBeInTheDocument();
    });
  });
});
