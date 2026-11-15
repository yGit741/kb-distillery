import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DataSourceProvider, type LayersResult } from "@/api";
import { withFlag } from "@/flags/testing";
import { useKb } from "@/lib/store";
import { mockDataSource } from "@/test/datasource";
import { sampleLinks, sampleNodes } from "../fixtures";
import { LINE_COPY } from "../shell/copy";
import { GraphShell } from "../shell/GraphShell";
import { useShellStore } from "../shell/shellStore";
import { DEFAULT_PREFS, useGraphUi } from "../store";
import { EMPTY_STACK } from "./model";
import { useLayers } from "./store";

const SHOWN = new Set(sampleNodes.map((n) => n.type));
const byId = new Map(sampleNodes.map((n) => [n.id, n] as const));

function setup(over: { layersFromText?: (text: string, op: "replace" | "stack" | "remove") => Promise<LayersResult> } = {}) {
  const ds = mockDataSource({
    search: async () => ({ hits: [], total: 0 }),
    listRecent: async () => ({ recent: [] }),
    listViews: async () => ({ views: [] }),
    addRecent: async () => ({ recent: [] }),
    ...over,
  });
  return render(
    <DataSourceProvider source={ds}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <GraphShell nodes={sampleNodes} links={sampleLinks} byId={byId} colorBy="type" shownTypes={SHOWN} onFocus={vi.fn()} onRead={vi.fn()} onShowExact={vi.fn()} onShowMentions={vi.fn()} onFit={vi.fn()} onZoom={vi.fn()} onReheat={vi.fn()} onRefresh={vi.fn()} />
      </QueryClientProvider>
    </DataSourceProvider>,
  );
}

const box = () => screen.getByRole("combobox", { name: /search the graph/i }) as HTMLInputElement;
const pages = () => screen.queryByRole("group", { name: LINE_COPY.names.heading });
const both = async (fn: () => Promise<void>) => withFlag("graph-intent", true, () => withFlag("graph-algos", true, fn));

beforeEach(() => {
  window.localStorage.clear();
  useLayers.setState({ stack: EMPTY_STACK, history: [], future: [], applied: null, skipped: [], graph: null, preview: null });
  useShellStore.setState({ pendingShape: null, pendingView: null, pendingOp: null, notice: null, shaping: false, shape: null, undo: null, shapeError: null });
  useGraphUi.setState({ ...DEFAULT_PREFS, view: null, flyout: null, railOpen: false });
  useKb.getState().clearSelection();
});

describe("flag graph-algos: page names complete inside a > line", () => {
  it("on: the pages a name may be are listed under the line's own row; Tab puts the title in", async () => {
    await both(async () => {
      setup();
      await userEvent.type(box(), "> near topic learn");
      const group = await screen.findByRole("group", { name: LINE_COPY.names.heading });
      expect(within(group).getByText("topic learning theory")).toBeInTheDocument();
      // the line's own row stays first, so Enter still runs the line
      expect(screen.getAllByRole("option")[0]).toHaveTextContent(LINE_COPY.viewRow);
      await userEvent.keyboard("{Tab}");
      expect(box().value).toBe('> near "topic learning theory" ');
      expect(pages()).not.toBeInTheDocument();
    });
  });

  it("on: Enter runs the line while pages are listed (a unique start of a title is enough)", async () => {
    await both(async () => {
      setup();
      await userEvent.type(box(), "> near topic learn");
      await screen.findByRole("group", { name: LINE_COPY.names.heading });
      await userEvent.keyboard("{Enter}");
      await waitFor(() => expect(useLayers.getState().preview).not.toBeNull());
      expect(useLayers.getState().preview!.layers[0]!.subgraph.nodes).toEqual([{ t: "hops", of: "topic-learning-theory", n: 1 }]);
      // a previewed line is done: no page list under it
      expect(pages()).not.toBeInTheDocument();
    });
  });

  it("on: a page picked with the arrows and Enter is put in, not run", async () => {
    await both(async () => {
      setup();
      await userEvent.type(box(), "> shortest path between topic learning theory and jane");
      await screen.findByRole("group", { name: LINE_COPY.names.heading });
      await userEvent.keyboard("{ArrowDown}{Enter}");
      expect(box().value).toBe('> shortest path between topic learning theory and "jane doe" ');
      expect(useLayers.getState().preview).toBeNull();
    });
  });

  it("off: no page list, Tab does nothing to the line", async () => {
    await withFlag("graph-intent", true, () =>
      withFlag("graph-algos", false, async () => {
        setup();
        await userEvent.type(box(), "> near topic learn");
        expect(pages()).not.toBeInTheDocument();
        await userEvent.keyboard("{Tab}");
        expect(box().value).toBe("> near topic learn");
      }),
    );
  });
});

describe("flag graph-algos: the Read as row", () => {
  it("on: the query the line became, one code line per layer, titles for slugs, labelled by the rules", async () => {
    await both(async () => {
      setup();
      const row = () => screen.getByTestId("resolved-line");
      await userEvent.type(box(), "> near jane doe, colour by theme");
      expect(row()).toHaveTextContent(LINE_COPY.preview.readAsWaiting);
      await userEvent.keyboard("{Enter}");
      await waitFor(() => expect(screen.getAllByTestId("read-as-line")).toHaveLength(2));
      const lines = screen.getAllByTestId("read-as-line").map((l) => l.textContent);
      expect(lines).toEqual(['show nodes within 1 hop of "jane doe"', "style nodes color by area"]);
      expect(screen.getByTestId("read-as-by")).toHaveTextContent(LINE_COPY.preview.readAs);
      expect(row()).toHaveTextContent(LINE_COPY.preview.hint);
    });
  });

  it("on: a line the model read says so", async () => {
    await both(async () => {
      const layersFromText = vi.fn(async () => ({
        layers: [{ id: "x", kind: "show", target: "nodes", subgraph: { nodes: [{ t: "type", value: "paper" }] }, text: "show nodes type paper" }],
        lines: ["show nodes type paper"],
        explanation: "",
        backend: "subscription",
        usd: 0,
        warnings: [],
      }) as unknown as LayersResult);
      setup({ layersFromText });
      await userEvent.type(box(), "> the reading list please{Enter}");
      await waitFor(() => expect(screen.getAllByTestId("read-as-line").map((l) => l.textContent)).toEqual(["show nodes type paper"]));
      expect(screen.getByTestId("read-as-by")).toHaveTextContent(LINE_COPY.preview.readByModel);
    });
  });

  it("on: Tab edits the query with titles; a title applies to its page, a name no page has says so", async () => {
    await both(async () => {
      setup();
      await userEvent.type(box(), "> near jane doe{Enter}");
      await screen.findAllByTestId("read-as-line");
      await userEvent.keyboard("{Tab}");
      const field = screen.getByRole("textbox", { name: LINE_COPY.preview.editLabel }) as HTMLTextAreaElement;
      expect(field.value).toBe('show nodes within 1 hop of "jane doe"');
      await userEvent.clear(field);
      await userEvent.type(field, 'show nodes within 1 hop of "no such page"{Enter}');
      expect(await screen.findByRole("alert")).toHaveTextContent(LINE_COPY.preview.noPage("no such page"));
      expect(useLayers.getState().stack.layers).toHaveLength(0);
      await userEvent.clear(field);
      await userEvent.type(field, 'show nodes within 1 hop of "idea margin"{Enter}');
      await waitFor(() => expect(useLayers.getState().stack.layers).toHaveLength(1));
      expect(useLayers.getState().stack.layers[0]!.subgraph.nodes).toEqual([{ t: "hops", of: "idea-margin", n: 1 }]);
    });
  });

  it("off: the quiet row with the resolved line, no Read as label", async () => {
    await withFlag("graph-intent", true, () =>
      withFlag("graph-algos", false, async () => {
        setup();
        await userEvent.type(box(), "> only orphans{Enter}");
        const row = await screen.findByTestId("resolved-line");
        await waitFor(() => expect(row).toHaveTextContent("show nodes degree = 0"));
        expect(screen.queryByTestId("read-as-by")).not.toBeInTheDocument();
      }),
    );
  });
});
