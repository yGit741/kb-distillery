import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DataSourceProvider, type DataSource, type LayersResult, type LineRoute } from "@/api";
import { withFlag } from "@/flags/testing";
import { mockDataSource } from "@/test/datasource";
import { sampleNodes } from "../fixtures";
import { EMPTY_STACK } from "../layers/model";
import { useLayers } from "../layers/store";
import { useGraphUi } from "../store";
import { useChatDock } from "../tools/chatDockStore";
import { LINE_COPY } from "./copy";
import { GraphShell } from "./GraphShell";
import { useShellStore } from "./shellStore";

const SHOWN = new Set(sampleNodes.map((n) => n.type));
const byId = new Map(sampleNodes.map((n) => [n.id, n] as const));
const SENTENCE = "the thing jane doe wrote about noise last spring";

function setup(over: Partial<DataSource> = {}) {
  const onFocus = vi.fn();
  const onZoom = vi.fn();
  const ds = mockDataSource({
    search: async () => ({ hits: [], total: 0 }),
    searchText: async () => ({ hits: [], total: 0 }) as never,
    listRecent: async () => ({ recent: [] }),
    listViews: async () => ({ views: [] }),
    addRecent: vi.fn(async () => ({ recent: [] })),
    layersFromText: vi.fn(async () => ({ layers: [], lines: [], explanation: "", backend: "subscription", usd: 0, warnings: [] }) as LayersResult),
    ...over,
  });
  render(
    <DataSourceProvider source={ds}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <GraphShell nodes={sampleNodes} byId={byId} colorBy="type" shownTypes={SHOWN} onFocus={onFocus} onRead={vi.fn()} onShowExact={vi.fn()} onShowMentions={vi.fn()} onFit={vi.fn()} onZoom={onZoom} onReheat={vi.fn()} onRefresh={vi.fn()} />
      </QueryClientProvider>
    </DataSourceProvider>,
  );
  return { onFocus, onZoom };
}

const box = () => screen.getByRole("combobox", { name: /search the graph/i });
const on = (fn: () => Promise<void>) => withFlag("graph-intent", true, () => withFlag("line-routing", true, fn));

beforeEach(() => {
  window.localStorage.clear();
  useChatDock.setState({ open: false, question: "" });
  useLayers.setState({ stack: EMPTY_STACK, history: [], future: [], applied: null, skipped: [], graph: null });
  useShellStore.setState({ pendingShape: null, pendingView: null, pendingOp: null, notice: null, shaping: false, shape: null, undo: null, shapeError: null });
  useGraphUi.setState({ flyout: null, railOpen: false });
});

describe("flag line-routing: Enter on a plain line reads it by itself", () => {
  it("on: an exact page title opens that page and says so, without the model", async () => {
    await on(async () => {
      const routeLine = vi.fn();
      const { onFocus } = setup({ routeLine });
      await userEvent.type(box(), "Topic learning theory{Enter}");
      expect(onFocus).toHaveBeenCalledWith("topic-learning-theory");
      await waitFor(() => expect(useShellStore.getState().notice?.text).toBe(LINE_COPY.route.search("topic learning theory")));
      expect(routeLine).not.toHaveBeenCalled();
    });
  });

  it("on: view words turn the line into a > line, the way > does", async () => {
    await on(async () => {
      setup();
      await userEvent.type(box(), "only orphans{Enter}");
      await waitFor(() => expect(box()).toHaveValue("> only orphans"));
      expect(await screen.findByText(LINE_COPY.route.view("only orphans"))).toBeInTheDocument();
      await userEvent.type(box(), "{Enter}");
      await waitFor(() => expect(useLayers.getState().stack.layers.map((l) => l.subgraph.nodes)).toEqual([[{ t: "degree", op: "=", n: 0 }]]));
    });
  });

  it("on: a question goes to the chat", async () => {
    await on(async () => {
      setup();
      await userEvent.type(box(), "why do big nets work?{Enter}");
      await waitFor(() => expect(useChatDock.getState().question).toContain("why do big nets work?"));
      expect(useShellStore.getState().notice?.text).toBe(LINE_COPY.route.ask);
    });
  });

  it("on: a command name runs the command", async () => {
    await on(async () => {
      const { onZoom } = setup();
      await userEvent.type(box(), "zoom out{Enter}");
      expect(onZoom).toHaveBeenCalledWith(1 / 1.25);
      expect(useShellStore.getState().notice?.text).toBe(LINE_COPY.route.command("Zoom out"));
    });
  });

  it("on: a line the rules cannot place asks the endpoint, shows a calm status, then acts on the answer", async () => {
    await on(async () => {
      let answer!: (r: LineRoute) => void;
      const routeLine = vi.fn(() => new Promise<LineRoute>((res) => (answer = res)));
      const { onZoom } = setup({ routeLine });
      await userEvent.type(box(), `${SENTENCE}{Enter}`);
      expect(await screen.findByText(LINE_COPY.route.reading)).toBeInTheDocument();
      expect(routeLine).toHaveBeenCalledWith(SENTENCE, expect.arrayContaining([{ id: "zoom-out", label: "Zoom out" }]), expect.anything());
      answer({ intent: "command", text: SENTENCE, command: "zoom-out", backend: "subscription", usd: 0, reason: "" });
      await waitFor(() => expect(onZoom).toHaveBeenCalled());
    });
  });

  it("on: typing again while the model reads drops its answer", async () => {
    await on(async () => {
      let answer!: (r: LineRoute) => void;
      const routeLine = vi.fn((_t: string, _c: unknown, o?: { signal?: AbortSignal }) => { void o; return new Promise<LineRoute>((res) => (answer = res)); });
      const { onZoom } = setup({ routeLine });
      await userEvent.type(box(), `${SENTENCE}{Enter}`);
      expect(await screen.findByText(LINE_COPY.route.reading)).toBeInTheDocument();
      await userEvent.type(box(), "x");
      await waitFor(() => expect(screen.queryByText(LINE_COPY.route.reading)).not.toBeInTheDocument());
      const signal = (routeLine.mock.calls[0]![2] as { signal: AbortSignal }).signal;
      expect(signal.aborted).toBe(true);
      answer({ intent: "command", text: SENTENCE, command: "zoom-out", backend: "subscription", usd: 0, reason: "" });
      await new Promise((r) => setTimeout(r, 20));
      expect(onZoom).not.toHaveBeenCalled();
    });
  });

  it("on: Shift+Enter is never routed", async () => {
    await on(async () => {
      const routeLine = vi.fn();
      setup({ routeLine });
      await userEvent.type(box(), `${SENTENCE}{Shift>}{Enter}{/Shift}`);
      expect(routeLine).not.toHaveBeenCalled();
    });
  });

  it("on: a failing endpoint reads the line as a page search, never an error", async () => {
    await on(async () => {
      const routeLine = vi.fn(async () => {
        throw new Error("down");
      });
      setup({ routeLine });
      await userEvent.type(box(), `${SENTENCE}{Enter}`);
      expect(await screen.findByText(LINE_COPY.route.nothing(SENTENCE))).toBeInTheDocument();
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });
  });

  it("on: a / sentence no command fits offers no junk closest options and routes on Enter", async () => {
    await on(async () => {
      const routeLine = vi.fn(async (): Promise<LineRoute> => ({ intent: "view", text: "hide nodes degree = 1", backend: "subscription", usd: 0, reason: "" }));
      setup({ routeLine });
      await userEvent.type(box(), "/filter out all jane doe blogs that are with degree 1");
      expect(screen.queryByRole("option", { name: /Zoom out/ })).not.toBeInTheDocument();
      await userEvent.type(box(), "{Enter}");
      // view words: the rules place it without the model
      await waitFor(() => expect(box()).toHaveValue("> filter out all jane doe blogs that are with degree 1"));
      expect(routeLine).not.toHaveBeenCalled();
    });
  });

  it("on: a row picked with the arrows runs as picked, not routed", async () => {
    await on(async () => {
      const routeLine = vi.fn();
      setup({ routeLine });
      await userEvent.type(box(), "learning theory{ArrowDown}{ArrowUp}{Enter}");
      expect(routeLine).not.toHaveBeenCalled();
      expect(useShellStore.getState().notice?.text ?? "").not.toContain("Read as");
    });
  });

  it("off: Enter runs the highlighted row and a / sentence still lists the closest options", async () => {
    await withFlag("graph-intent", true, () =>
      withFlag("line-routing", false, async () => {
        const routeLine = vi.fn();
        setup({ routeLine });
        await userEvent.type(box(), "/filter out all jane doe blogs that are with degree 1");
        expect(await screen.findByText(LINE_COPY.closestHeading)).toBeInTheDocument();
        await userEvent.clear(box());
        await userEvent.type(box(), `${SENTENCE}{Enter}`);
        expect(routeLine).not.toHaveBeenCalled();
        expect(screen.queryByText(LINE_COPY.route.reading)).not.toBeInTheDocument();
      }),
    );
  });
});
