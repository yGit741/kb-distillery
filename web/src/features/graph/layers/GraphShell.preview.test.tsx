import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DataSourceProvider } from "@/api";
import { withFlag } from "@/flags/testing";
import { useKb } from "@/lib/store";
import { mockDataSource } from "@/test/datasource";
import { sampleLinks, sampleNodes } from "../fixtures";
import { LINE_COPY } from "../shell/copy";
import { GraphShell } from "../shell/GraphShell";
import { useShellStore } from "../shell/shellStore";
import { DEFAULT_PREFS, useGraphUi } from "../store";
import { EMPTY_STACK, makeLayer } from "./model";
import { useLayers } from "./store";

const SHOWN = new Set(sampleNodes.map((n) => n.type));
const byId = new Map(sampleNodes.map((n) => [n.id, n] as const));
const addRecent = vi.fn(async () => ({ recent: [] }));
const listRecent = vi.fn(async () => ({ recent: [] }));

function setup() {
  const ds = mockDataSource({
    search: async () => ({ hits: [], total: 0 }),
    listRecent,
    listViews: async () => ({ views: [] }),
    addRecent,
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
const layers = () => useLayers.getState().stack.layers;

beforeEach(() => {
  window.localStorage.clear();
  addRecent.mockClear();
  listRecent.mockReset();
  listRecent.mockResolvedValue({ recent: [] });
  useLayers.setState({ stack: EMPTY_STACK, history: [], future: [], applied: null, skipped: [], graph: null, preview: null });
  useShellStore.setState({ pendingShape: null, pendingView: null, pendingOp: null, notice: null, shaping: false, shape: null, undo: null, shapeError: null });
  useGraphUi.setState({ ...DEFAULT_PREFS, view: null, flyout: null, railOpen: false });
  useKb.getState().clearSelection();
});

describe("a > sentence is previewed before it applies (graph-intent)", () => {
  it("first Enter previews: the stack is untouched, the row shows the lines and the count", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      await userEvent.type(box(), "> only orphans{Enter}");
      const row = await screen.findByTestId("resolved-line");
      await waitFor(() => expect(row).toHaveTextContent("show nodes degree = 0"));
      expect(row).toHaveTextContent(/\d+ nodes?/);
      expect(layers()).toHaveLength(0);
      expect(useLayers.getState().preview?.ids).not.toBeNull();
      expect(useGraphUi.getState().view).toBeNull();
    });
  });

  it("Esc cancels the preview and gives back the knobs a style tinted", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      await userEvent.type(box(), "> colour by depth{Enter}");
      await waitFor(() => expect(useGraphUi.getState().colorBy).toBe("depth"));
      expect(layers()).toHaveLength(0);
      await userEvent.keyboard("{Escape}");
      expect(useLayers.getState().preview).toBeNull();
      expect(useGraphUi.getState().colorBy).toBe(DEFAULT_PREFS.colorBy);
      expect(layers()).toHaveLength(0);
    });
  });

  it("second Enter applies, closes, and records the step in Recent", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      await userEvent.type(box(), "> colour by depth{Enter}{Enter}");
      await waitFor(() => expect(layers()).toHaveLength(1));
      expect(useLayers.getState().preview).toBeNull();
      expect(useLayers.getState().history).toHaveLength(1);
      expect(useGraphUi.getState().colorBy).toBe("depth");
      expect(box()).toHaveValue("");
      await waitFor(() => expect(addRecent).toHaveBeenCalledTimes(1));
      expect((addRecent.mock.calls[0] as unknown[])[0]).toBe("colour by depth");
    });
  });

  it("editing the resolved line applies exactly what is written", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      await userEvent.type(box(), "> only orphans{Enter}");
      await userEvent.click(await screen.findByTitle(LINE_COPY.preview.edit));
      const field = await screen.findByRole("textbox", { name: LINE_COPY.preview.editLabel });
      expect(field).toHaveValue("show nodes degree = 0");
      await userEvent.clear(field);
      await userEvent.type(field, "show nodes type paper{Enter}");
      await waitFor(() => expect(layers()).toHaveLength(1));
      expect(layers()[0]!.subgraph.nodes).toEqual([{ t: "type", value: "paper" }]);
      expect(layers()[0]!.text).toBe("show nodes type paper");
      expect(useLayers.getState().preview).toBeNull();
    });
  });

  it("Tab from the input opens the field", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      await userEvent.type(box(), "> only orphans{Enter}{Tab}");
      expect(await screen.findByRole("textbox", { name: LINE_COPY.preview.editLabel })).toBeInTheDocument();
    });
  });

  it("a line that does not parse shows its reason and applies nothing", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      await userEvent.type(box(), "> only orphans{Enter}");
      await userEvent.click(await screen.findByTitle(LINE_COPY.preview.edit));
      const field = await screen.findByRole("textbox", { name: LINE_COPY.preview.editLabel });
      await userEvent.clear(field);
      await userEvent.type(field, "banana{Enter}");
      expect(await screen.findByRole("alert")).toHaveTextContent("Line 1");
      expect(layers()).toHaveLength(0);
    });
  });

  it("a recorded step in Recent applies again as one undo step", async () => {
    await withFlag("graph-intent", true, async () => {
      const stack = { v: 2, layers: [makeLayer("style", "nodes", {}, "colour by depth", { style: { color: "depth" } })] };
      listRecent.mockResolvedValue({ recent: [{ at: "2026-11-06T00:00:00Z", text: "colour by depth", spec: { stack, lines: ["style nodes color by depth"] } }] } as never);
      setup();
      await userEvent.click(box());
      await userEvent.click(await screen.findByRole("option", { name: /colour by depth/ }));
      await waitFor(() => expect(layers()).toHaveLength(1));
      expect(useLayers.getState().history).toHaveLength(1);
      expect(useGraphUi.getState().colorBy).toBe("depth");
    });
  });

  it("off: Enter on a > line is plain search, no preview", async () => {
    await withFlag("graph-intent", false, async () => {
      setup();
      await userEvent.type(box(), "> only orphans{Enter}");
      expect(screen.queryByTestId("resolved-line")).not.toBeInTheDocument();
      expect(useLayers.getState().preview).toBeNull();
    });
  });
});
