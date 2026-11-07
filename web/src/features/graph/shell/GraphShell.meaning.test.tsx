import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DataSourceProvider, type DataSource } from "@/api";
import { withFlag } from "@/flags/testing";
import { useKb } from "@/lib/store";
import { mockDataSource } from "@/test/datasource";
import { node } from "../fixtures";
import { clearMeaningCache } from "../layers/meaning";
import { EMPTY_STACK } from "../layers/model";
import { useLayers } from "../layers/store";
import { DEFAULT_PREFS, useGraphUi } from "../store";
import { useChatDock } from "../tools/chatDockStore";
import { GraphShell } from "./GraphShell";
import { useShellStore } from "./shellStore";

const nodes = [
  node("margin-theory", { title: "Margin theory", inDegree: 3 }),
  node("large-margins", { title: "Large margins" }),
  node("kernel", { title: "Kernel methods" }),
  node("regularization", { title: "Regularization" }),
];
const byId = new Map(nodes.map((n) => [n.id, n] as const));
const SHOWN = new Set(nodes.map((n) => n.type));

type Similar = DataSource["searchSimilar"];

function setup(searchSimilar: Similar) {
  const ds = mockDataSource({
    search: async () => ({ hits: [], total: 0 }),
    listRecent: async () => ({ recent: [] }),
    listViews: async () => ({ views: [] }),
    addRecent: vi.fn(async () => ({ recent: [] })),
    searchSimilar,
  });
  render(
    <DataSourceProvider source={ds}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <GraphShell nodes={nodes} links={[]} byId={byId} colorBy="type" shownTypes={SHOWN} onFocus={vi.fn()} onRead={vi.fn()} onShowExact={vi.fn()} onShowMentions={vi.fn()} onFit={vi.fn()} onZoom={vi.fn()} onReheat={vi.fn()} onRefresh={vi.fn()} />
      </QueryClientProvider>
    </DataSourceProvider>,
  );
}

const box = () => screen.getByRole("combobox", { name: /search the graph/i });
const optionNames = () => screen.queryAllByRole("option").map((o) => o.textContent ?? "");
const both = (fn: () => Promise<void>) => withFlag("graph-intent", true, () => withFlag("semantic-search", true, fn));
const answer = (hits: { slug: string; score: number }[]): Similar => vi.fn(async () => ({ hits: hits.map((h) => ({ ...h, title: h.slug })) }));

beforeEach(() => {
  window.localStorage.clear();
  clearMeaningCache();
  useChatDock.setState({ open: false, question: "" });
  useLayers.setState({ stack: EMPTY_STACK, history: [], future: [], preview: null, applied: null, skipped: [], graph: null });
  useShellStore.setState({ pendingShape: null, pendingView: null, pendingOp: null, notice: null, shaping: false, shape: null, undo: null, shapeError: null });
  useGraphUi.setState({ ...DEFAULT_PREFS, view: null, flyout: null, railOpen: false });
  useKb.getState().clearSelection();
});
afterEach(() => vi.useRealTimers());

describe("Related by meaning", () => {
  it("fills in after a 350 ms pause, under the word hits, and moves nothing already shown", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const ui = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const similar = answer([{ slug: "margin-theory", score: 91 }, { slug: "kernel", score: 74 }, { slug: "regularization", score: 61 }]);
    await both(async () => {
      setup(similar);
      await ui.type(box(), "margin");
      await act(() => vi.advanceTimersByTime(300));
      // (the Ask row is always last; it moves down as the group above it fills in)
      const before = optionNames().slice(0, -1);
      expect(before.some((t) => t.includes("Margin theory"))).toBe(true);
      expect(similar).not.toHaveBeenCalled();
      await act(() => vi.advanceTimersByTime(100));
      expect(similar).toHaveBeenCalledTimes(1);
      expect((similar as ReturnType<typeof vi.fn>).mock.calls[0]![0]).toMatchObject({ q: "margin" });
      const group = await screen.findByRole("group", { name: "Related by meaning" });
      const rows = within(group).getAllByRole("option");
      // the word hit is not repeated here; the others carry their score, quietly, at the right
      expect(rows.map((r) => r.textContent)).toEqual(["Kernel methods74", "Regularization61"]);
      // everything shown before is still there, in the same order, above the new group
      const after = optionNames();
      // (a word hit that is also a meaning hit gains one small mark, "meaning", and nothing else)
      expect(after.slice(0, before.length).map((t) => t.replace("meaning", ""))).toEqual(before);
      expect(after.at(-1)).toContain("Ask about");
    });
  });

  it("drops a request a newer text made stale, and asks once for the text it ends on", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const ui = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const similar = answer([{ slug: "kernel", score: 70 }]);
    await both(async () => {
      setup(similar);
      await ui.type(box(), "ma");
      await act(() => vi.advanceTimersByTime(200));
      await ui.type(box(), "rgin");
      await act(() => vi.advanceTimersByTime(400));
      expect(similar).toHaveBeenCalledTimes(1);
      expect((similar as ReturnType<typeof vi.fn>).mock.calls[0]![0]).toMatchObject({ q: "margin" });
      expect((similar as ReturnType<typeof vi.fn>).mock.calls[0]![1]).toBeInstanceOf(AbortSignal);
    });
  });

  it("shows nothing (and no error) when the service is off", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const ui = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const similar = vi.fn(async () => {
      throw new Error("503");
    });
    await both(async () => {
      setup(similar as Similar);
      await ui.type(box(), "margin");
      await act(() => vi.advanceTimersByTime(400));
      expect(similar).toHaveBeenCalled();
      expect(screen.queryByRole("group", { name: "Related by meaning" })).not.toBeInTheDocument();
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });
  });

  it("is never asked with semantic-search off or graph-intent off", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const ui = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const similar = answer([{ slug: "kernel", score: 70 }]);
    await withFlag("graph-intent", true, () =>
      withFlag("semantic-search", false, async () => {
        setup(similar);
        await ui.type(box(), "margin");
        await act(() => vi.advanceTimersByTime(500));
        expect(similar).not.toHaveBeenCalled();
      }),
    );
    document.body.innerHTML = "";
    await withFlag("graph-intent", false, () =>
      withFlag("semantic-search", true, async () => {
        setup(similar);
        await ui.type(box(), "margin");
        await act(() => vi.advanceTimersByTime(500));
        expect(similar).not.toHaveBeenCalled();
        expect(await screen.findByRole("option", { name: /ask the agent: margin/i })).toBeInTheDocument();
      }),
    );
  });
});

describe("Ask about", () => {
  it("is the last row, and Enter opens the chat with the question, the focus and the shown pages (capped at 60)", async () => {
    const ask = vi.fn();
    useChatDock.setState({ ask });
    useKb.getState().setSelection(["kernel"]);
    useGraphUi.setState({ view: { kind: "picked", label: "x", hits: new Set(["kernel"]), shown: new Set(Array.from({ length: 70 }, (_, i) => `p${i}`)) } });
    await both(async () => {
      setup(answer([]));
      await userEvent.type(box(), "why do margins matter");
      const opts = screen.getAllByRole("option");
      expect(opts.at(-1)).toHaveTextContent('Ask about "why do margins matter"');
      await userEvent.keyboard("{ArrowUp}{Enter}");
      expect(ask).toHaveBeenCalledTimes(1);
      const draft = ask.mock.calls[0]![0] as string;
      expect(draft.startsWith("why do margins matter")).toBe(true);
      expect(draft).toContain("Focus: ");
      expect(draft).toContain("kernel.md");
      expect(draft).toContain("Shown in the graph (70)");
      expect(draft).toContain("p59.md");
      expect(draft).not.toContain("p60.md");
      expect(draft).toContain("and 10 more");
    });
  });

  it("the chat action on a set goes the same way", async () => {
    const ask = vi.fn();
    useChatDock.setState({ ask });
    useGraphUi.setState({ view: { kind: "picked", label: "x", hits: new Set(), shown: new Set(["a", "b"]) } });
    await both(async () => {
      setup(answer([]));
      await userEvent.type(box(), "margin");
      const set = await screen.findByRole("option", { name: /pages mention margin/i });
      await userEvent.click(within(set).getByRole("button", { name: "Actions" }));
      await userEvent.click(await screen.findByRole("menuitem", { name: /chat about these/i }));
      const draft = ask.mock.calls[0]![0] as string;
      expect(draft).toContain("About ");
      expect(draft).toContain("Shown in the graph (2)");
    });
  });
});

describe("about in a > sentence", () => {
  it("is resolved to the top pages before it is previewed and applied; the chip keeps the words", async () => {
    const similar = answer([{ slug: "kernel", score: 80 }, { slug: "regularization", score: 60 }]);
    await both(async () => {
      setup(similar);
      await userEvent.type(box(), '> about "overfitting"{Enter}');
      await waitFor(() => expect(useLayers.getState().preview).not.toBeNull());
      expect((similar as ReturnType<typeof vi.fn>).mock.calls[0]![0]).toEqual({ q: "overfitting", slug: undefined, k: 20 });
      expect(useLayers.getState().preview!.count).toBe(2);
      await userEvent.keyboard("{Enter}");
      const [layer] = useLayers.getState().stack.layers;
      expect(layer!.text).toBe('about "overfitting"');
      expect(layer!.subgraph.nodes).toEqual([{ t: "about", phrase: "overfitting", slugs: ["kernel", "regularization"] }]);
      expect(useLayers.getState().skipped).toEqual([]);
      // the same phrase again is answered from the session cache
      await userEvent.type(box(), '>+ about "overfitting"{Enter}');
      await waitFor(() => expect(useLayers.getState().preview).not.toBeNull());
      expect(similar).toHaveBeenCalledTimes(1);
    });
  });

  it('"similar to this" asks with the one focused page', async () => {
    const similar = answer([{ slug: "regularization", score: 77 }]);
    useKb.getState().setSelection(["kernel"]);
    await both(async () => {
      setup(similar);
      await userEvent.type(box(), "> similar to this{Enter}");
      await waitFor(() => expect(useLayers.getState().preview).not.toBeNull());
      expect((similar as ReturnType<typeof vi.fn>).mock.calls[0]![0]).toEqual({ slug: "kernel", q: undefined, k: 20 });
      // the neighbours it names, and the page itself
      expect([...useLayers.getState().preview!.ids!].sort()).toEqual(["kernel", "regularization"]);
    });
  });

  it.each([[[]], [["kernel", "margin-theory"]]])("\"similar to this\" with %j focused says to focus one node and applies nothing", async (focused) => {
    const similar = answer([{ slug: "regularization", score: 77 }]);
    useKb.getState().setSelection(focused);
    await both(async () => {
      setup(similar);
      await userEvent.type(box(), "> similar to this{Enter}");
      expect(await screen.findByText("Focus one node first")).toBeInTheDocument();
      expect(similar).not.toHaveBeenCalled();
      expect(useLayers.getState().preview).toBeNull();
      expect(useLayers.getState().stack.layers).toHaveLength(0);
    });
  });

  it("stays skipped, with its reason, when meaning search is off", async () => {
    const similar = answer([{ slug: "kernel", score: 80 }]);
    await withFlag("graph-intent", true, () =>
      withFlag("semantic-search", false, async () => {
        setup(similar);
        await userEvent.type(box(), '> about "overfitting"{Enter}{Enter}');
        await waitFor(() => expect(useLayers.getState().stack.layers).toHaveLength(1));
        expect(similar).not.toHaveBeenCalled();
        expect(useLayers.getState().skipped.join("|")).toMatch(/about "overfitting" \(meaning search is off\)/);
      }),
    );
  });
});
