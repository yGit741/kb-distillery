import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react";
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
  node("margin-theory", { title: "Margin theory" }),
  node("kernel", { title: "Kernel methods" }),
  node("deep-nets", { title: "Deep nets" }),
];
const byId = new Map(nodes.map((n) => [n.id, n] as const));
const SHOWN = new Set(nodes.map((n) => n.type));

const HITS = [
  { kind: "page", id: "margin-theory", title: "Margin theory", snippet: "already shown by title", score: 3, path: "wiki/margin-theory.md" },
  { kind: "page", id: "kernel", title: "Kernel methods", snippet: "the kernel trick makes margin separable", score: 2, path: "wiki/kernel.md" },
  { kind: "chat", id: "s1", title: "Margin chat", snippet: "we talked about margin", score: 1, path: ".local/sessions/s1.json" },
  { kind: "raw", id: "raw/papers/x.md", title: "A paper", snippet: "margin bounds", score: 1, path: "raw/papers/x.md" },
];

function setup(searchText: ReturnType<typeof vi.fn>) {
  const ds = mockDataSource({
    search: (async () => ({ hits: [], total: 0 })) as never,
    searchText: searchText as never,
    listRecent: async () => ({ recent: [] }),
    listViews: async () => ({ views: [] }) as never,
  });
  render(
    <DataSourceProvider source={ds}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <GraphShell nodes={nodes} byId={byId} colorBy="type" shownTypes={SHOWN} onFocus={vi.fn()} onRead={vi.fn()} onShowExact={vi.fn()} onShowMentions={vi.fn()} onFit={vi.fn()} onZoom={vi.fn()} onReheat={vi.fn()} onRefresh={vi.fn()} />
      </QueryClientProvider>
    </DataSourceProvider>,
  );
}

const box = () => screen.getByRole("combobox", { name: /search the graph/i });
const type = (v: string) => act(() => { fireEvent.change(box(), { target: { value: v } }); });
const labels = () => screen.queryAllByRole("option").map((o) => o.textContent ?? "");
const headings = () => screen.queryAllByRole("group").map((g) => g.firstElementChild?.textContent);
const settle = () => act(async () => { await vi.advanceTimersByTimeAsync(0); });

beforeEach(() => {
  window.localStorage.clear();
  useChatDock.setState({ open: false, question: "" });
  useLayers.setState({ stack: EMPTY_STACK, history: [], future: [], applied: null, skipped: [], graph: null });
  useShellStore.setState({ pendingShape: null, pendingView: null, pendingOp: null, notice: null, shaping: false, shape: null, undo: null, shapeError: null });
  useGraphUi.setState({ ...DEFAULT_PREFS, view: null, flyout: null, railOpen: false });
  useKb.getState().clearSelection();
  vi.useFakeTimers();
});
afterEach(() => vi.useRealTimers());

describe("search line tier 2 (full text from the server)", () => {
  it("fills rows after the pause, under the tier-1 rows, without moving them or repeating a shown page", async () => {
    await withFlag("graph-intent", true, async () => {
      const searchText = vi.fn(async (_q: string) => ({ query: "margin", hits: HITS }));
      setup(searchText);
      await act(async () => box().focus());
      type("margin");
      await settle();
      const before = labels();
      expect(before.some((l) => /Margin theory/.test(l))).toBe(true);
      expect(searchText).not.toHaveBeenCalled();                     // not before the pause
      await act(async () => { await vi.advanceTimersByTimeAsync(299); });
      expect(searchText).not.toHaveBeenCalled();
      await act(async () => { await vi.advanceTimersByTimeAsync(10); });
      expect(searchText).toHaveBeenCalledTimes(1);
      expect(searchText.mock.calls[0]![0]).toBe("margin");
      await settle();
      screen.getByRole("option", { name: /Kernel methods/ });
      const after = labels();
      expect(after.slice(0, before.length - 1)).toEqual(before.slice(0, before.length - 1));        // rows shown stay put (the Actions row is last)
      expect(screen.getAllByRole("option", { name: /Margin theory/ })).toHaveLength(1);          // not repeated
      expect(headings()).toEqual(expect.arrayContaining(["Pages: full text", "Chats", "Raw files"]));
      const order = headings();
      expect(order.indexOf("Pages: full text")).toBeLessThan(order.indexOf("Chats"));
      expect(order.indexOf("Chats")).toBeLessThan(order.indexOf("Raw files"));
      expect(screen.getByText("the kernel trick makes margin separable")).toBeInTheDocument();       // the snippet is the quiet second line
      expect(screen.getByRole("option", { name: /Margin chat/ })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: /A paper/ })).toBeInTheDocument();
    });
  });

  it("asks once for the text after a burst of typing, and drops the old answer's rows when the text changes", async () => {
    await withFlag("graph-intent", true, async () => {
      const searchText = vi.fn(async (q: string) => ({ query: q, hits: q === "margin" ? HITS : [] }));
      setup(searchText);
      await act(async () => box().focus());
      for (const v of ["m", "ma", "mar", "marg", "margi", "margin"]) {
        type(v);
        await act(async () => { await vi.advanceTimersByTimeAsync(80); });
      }
      expect(searchText).not.toHaveBeenCalled();
      await act(async () => { await vi.advanceTimersByTimeAsync(400); });
      expect(searchText).toHaveBeenCalledTimes(1);
      await settle();
      screen.getByRole("option", { name: /Margin chat/ });
      type("margins");
      await settle();
      expect(screen.queryByRole("option", { name: /Margin chat/ })).toBeNull();
    });
  });

  it("flag off: no request and no tier-2 rows", async () => {
    await withFlag("graph-intent", false, async () => {
      const searchText = vi.fn(async () => ({ query: "margin", hits: HITS }));
      setup(searchText);
      await act(async () => box().focus());
      type("margin");
      await act(async () => { await vi.advanceTimersByTimeAsync(800); });
      expect(searchText).not.toHaveBeenCalled();
      expect(screen.queryByRole("option", { name: /Margin chat/ })).toBeNull();
    });
  });

  it("a failing server leaves the tier-1 rows alone", async () => {
    await withFlag("graph-intent", true, async () => {
      setup(vi.fn(async () => { throw new Error("down"); }));
      await act(async () => box().focus());
      type("margin");
      await act(async () => { await vi.advanceTimersByTimeAsync(600); });
      expect(screen.getAllByRole("option", { name: /Margin theory/ })).toHaveLength(1);
      expect(headings()).not.toContain("Chats");
    });
  });
});
