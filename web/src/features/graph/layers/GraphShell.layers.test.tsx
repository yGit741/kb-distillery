import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DataSourceProvider, type ShapeResult } from "@/api";
import { withFlag } from "@/flags/testing";
import { useKb } from "@/lib/store";
import { mockDataSource } from "@/test/datasource";
import { sampleLinks, sampleNodes } from "../fixtures";
import { GraphShell } from "../shell/GraphShell";
import { useShellStore } from "../shell/shellStore";
import { DEFAULT_PREFS, useGraphUi } from "../store";
import { EMPTY_STACK } from "./model";
import { useLayers } from "./store";

const SHOWN = new Set(sampleNodes.map((n) => n.type));
const byId = new Map(sampleNodes.map((n) => [n.id, n] as const));
const answer = (): ShapeResult => ({
  columns: [],
  rows: [],
  row_count: 0,
  truncated: false,
  cypher: null,
  style: { hide_edge_kinds: [], hide_labels: [], colour_by: { by: "prop", name: "depth" } },
  style_text: "colour by depth",
  source: "cypher",
  explanation: "",
  warnings: [],
});

function setup() {
  const ds = mockDataSource({
    search: async () => ({ hits: [], total: 0 }),
    listRecent: async () => ({ recent: [] }),
    listViews: async () => ({ views: [] }),
    addRecent: vi.fn(async () => ({ recent: [] })),
    shapeGraph: vi.fn(async () => answer()),
  });
  return render(
    <DataSourceProvider source={ds}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <GraphShell nodes={sampleNodes} links={sampleLinks} byId={byId} colorBy="type" shownTypes={SHOWN} onFocus={vi.fn()} onRead={vi.fn()} onShowExact={vi.fn()} onShowMentions={vi.fn()} onFit={vi.fn()} onZoom={vi.fn()} onReheat={vi.fn()} onRefresh={vi.fn()} />
      </QueryClientProvider>
    </DataSourceProvider>,
  );
}

const box = () => screen.getByRole("combobox", { name: /search the graph/i });

beforeEach(() => {
  window.localStorage.clear();
  useLayers.setState({ stack: EMPTY_STACK, history: [], future: [], applied: null, skipped: [], graph: null });
  useShellStore.setState({ pendingShape: null, pendingView: null, pendingOp: null, notice: null, shaping: false, shape: null, undo: null, shapeError: null });
  useGraphUi.setState({ ...DEFAULT_PREFS, view: null, flyout: null, railOpen: false });
  useKb.getState().clearSelection();
});

describe("the > route records a layer (graph-intent)", () => {
  it("on: the sentence becomes a chip, Cmd-Z undoes it, >- removes it by its text", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      expect(screen.queryByTestId("chip-rows")).not.toBeInTheDocument();
      await userEvent.type(box(), "> colour by depth{Enter}{Enter}");
      const view = await screen.findByRole("group", { name: "View" });
      expect(view).toHaveTextContent("colour by depth");
      expect(useGraphUi.getState().colorBy).toBe("depth");
      expect(useLayers.getState().stack.layers.map((l) => l.text)).toEqual(["colour by depth"]);

      await userEvent.keyboard("{Escape}");
      (document.activeElement as HTMLElement | null)?.blur();
      await userEvent.keyboard("{Meta>}z{/Meta}");
      await waitFor(() => expect(useLayers.getState().stack.layers).toHaveLength(0));
      expect(useGraphUi.getState().colorBy).toBe(DEFAULT_PREFS.colorBy);
      expect(screen.queryByRole("group", { name: "View" })).not.toBeInTheDocument();
    });
  });

  it("on: >+ stacks and >- removes", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      await userEvent.type(box(), ">+ colour by depth{Enter}{Enter}");
      await waitFor(() => expect(useLayers.getState().stack.layers).toHaveLength(1));
      await userEvent.type(box(), ">- colour by depth{Enter}");
      await waitFor(() => expect(useLayers.getState().stack.layers).toHaveLength(0));
    });
  });

  it("off: no chip rows and no layers recorded", async () => {
    await withFlag("graph-intent", false, async () => {
      setup();
      await userEvent.type(box(), "colour by depth");
      expect(screen.queryByTestId("chip-rows")).not.toBeInTheDocument();
      expect(useLayers.getState().stack.layers).toHaveLength(0);
    });
  });
});
