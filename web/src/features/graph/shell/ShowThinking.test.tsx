import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DataSourceProvider, type DataSource } from "@/api";
import { chatStatus } from "@/features/chat/fixtures";
import { withFlag } from "@/flags/testing";
import { useKb } from "@/lib/store";
import { mockDataSource } from "@/test/datasource";
import { sampleSnapshot } from "../fixtures";
import { GraphScreen, type GraphHost } from "../GraphScreen";
import { DEFAULT_PREFS, useGraphUi } from "../store";
import { useChatDock } from "../tools/chatDockStore";
import { showDock } from "./corners/sessions";
import { useChatFull } from "./chatFullStore";
import { useCites } from "./citeStore";
import { ShowThinking } from "./ShowThinking";
import { useThinking } from "./thinkingStore";
import { useReplay } from "./replayStore";
import { useSparkPanel } from "./sparkPanelStore";

// jsdom has no canvas: stand in for force-graph with a chainable no-op instance.
vi.mock("force-graph", () => {
  const getters: Record<string, (args: unknown[]) => unknown> = {
    zoom: (a) => (a.length ? undefined : 1),
    centerAt: (a) => (a.length ? undefined : { x: 0, y: 0 }),
    graphData: (a) => (a.length ? undefined : { nodes: [], links: [] }),
    d3Force: () => ({ strength: () => {}, distance: () => {} }),
    screen2GraphCoords: () => ({ x: 0, y: 0 }),
    graph2ScreenCoords: () => ({ x: 0, y: 0 }),
  };
  const make = () => {
    const inst: Record<string, unknown> = {};
    const proxy: unknown = new Proxy(inst, {
      get: (_t, name: string) => (name === "_destructor" ? () => {} : (...args: unknown[]) => (name in getters ? getters[name]?.(args) ?? proxy : proxy)),
    });
    return proxy;
  };
  return { default: () => () => make() };
});

vi.mock("@tanstack/react-router", async (orig) => ({
  ...(await orig<typeof import("@tanstack/react-router")>()),
  Link: ({ children, to }: { children: React.ReactNode; to: string }) => <a href={to}>{children}</a>,
}));

const host: GraphHost = {
  openPage: vi.fn(),
  pageHref: (s) => `/app/pages/${s}`,
  clearParams: vi.fn(),
  setParams: vi.fn(),
  go: vi.fn(),
  href: (to) => `/app${to}`,
};

const ds = (): DataSource =>
  mockDataSource({
    getGraph: async () => sampleSnapshot(),
    search: async () => ({ hits: [], total: 0 }),
    listRecent: async () => ({ recent: [] }),
    listViews: async () => ({ views: [] }),
    getChatStatus: async () => chatStatus(),
    getChatPrompts: async () => ({ prompts: [{ id: "query", title: "Query", description: "", system: "Answer from the wiki." }] }) as never,
  });

const screenWith = (source: DataSource = ds()) =>
  render(
    <DataSourceProvider source={source}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <GraphScreen search={{}} host={host} />
      </QueryClientProvider>
    </DataSourceProvider>,
  );

const TRACE = [
  { id: "g", name: "mcp", summary: "shortlist", round: 1, kind: "shortlist", query: "margin bound", seen: ["topic-learning-theory", "idea-margin", "2019-fine-grained", "course-runi-rl"], status: "done" },
  { id: "r1", name: "Read", summary: "read 2019-fine-grained", round: 2, kind: "open", read: ["2019-fine-grained"], status: "done" },
  { id: "r2", name: "Read", summary: "read idea-margin", round: 2, kind: "open", read: ["idea-margin"], status: "done" },
  { id: "w", name: "WebSearch", summary: "web", round: 3, kind: "web-search", query: "margin theory", domains: ["arxiv.org"], status: "done" },
  { id: "f", name: "WebFetch", summary: "fetch", round: 3, kind: "web-source", url: "https://openreview.net/x", status: "done" },
];
const ANSWER = "It is [Margin](idea-margin.md), see [Theory](topic-learning-theory.md).";
const storeChat = (trace: unknown[]) =>
  sessionStorage.setItem(
    "kbchat.chat",
    JSON.stringify({ id: "kb-chat:9", session: null, messages: [{ role: "user", content: "What is margin?", sources: [] }, { role: "assistant", content: ANSWER, trace }] }),
  );

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  useChatDock.setState({ open: false, wide: false, question: "" });
  useSparkPanel.setState({ open: false, key: 0 });
  useCites.setState({ slugs: [], fitTick: 0, scrollReq: null });
  useReplay.setState({ msg: null, step: 0, view: null, candidates: [], picked: null, missed: [], bad: [] });
  useThinking.setState({ view: null, dismissed: null, hot: null });
  useChatFull.setState({ full: false, listOpen: true, folded: false, cited: [], pages: [], mention: null, busy: false, notice: "", insert: null });
  useKb.setState({ selection: new Set() });
  useGraphUi.setState({ ...DEFAULT_PREFS, story: "", shownTypes: undefined, predicate: null, shownDepths: null, search: "", rules: [], typeLabels: new Set(), view: null, revealed: new Set(), flyout: null, detailsOpen: false, readerSlug: null, focusRequest: null, fitTick: 0 });
});

const on = (fn: () => Promise<void>) => withFlag("graph-shell", true, () => withFlag("spark-chat", true, () => withFlag("show-thinking", true, fn)));
const off = (fn: () => Promise<void>) => withFlag("graph-shell", true, () => withFlag("spark-chat", true, () => withFlag("show-thinking", false, fn)));
const open = async (source?: DataSource) => {
  screenWith(source);
  await screen.findByTestId("graph-shell");
  act(() => showDock());
  await screen.findByTestId("spark-panel");
};
const header = () => screen.findByRole("button", { name: /Show my thinking/ });

describe("flag show-thinking: Show my thinking", () => {
  it("on: folded by default under the answer, with the summary; no old replay control", async () => {
    await on(async () => {
      storeChat(TRACE);
      await open();
      const h = await header();
      expect(h).toHaveAttribute("aria-expanded", "false");
      expect(h).toHaveTextContent("2 opened · 4 found · 1 web search");
      expect(screen.queryByTestId("thinking-body")).toBeNull();
      expect(screen.queryByRole("button", { name: "How this answer was built" })).toBeNull();
    });
  });

  it("unfolded: rounds, web rows with a globe and a WEB badge, citations numbered as on the graph, opened not cited", async () => {
    await on(async () => {
      storeChat(TRACE);
      await open();
      await userEvent.click(await header());
      const rounds = screen.getAllByTestId("thinking-round");
      expect(rounds.map((r) => within(r).getByText(/^Round/).textContent)).toEqual(["Round 1", "Round 2 · 2 at once", "Round 3 · 2 at once"]);
      const web = screen.getAllByTestId("thinking-call").filter((c) => c.dataset.kind?.startsWith("web"));
      expect(web).toHaveLength(2);
      for (const c of web) {
        expect(within(c).getByTestId("web-badge")).toHaveTextContent("Web");
        expect(c.querySelector('[data-icon="globe"]')).not.toBeNull();
      }
      expect(web[0]).toHaveTextContent("arxiv.org");
      expect(web[1]).toHaveTextContent("openreview.net");
      expect(web[1]).toHaveTextContent("web source");
      // superscripts in the answer match the store the graph badges read
      const sups = screen.getAllByLabelText(/^citation \d$/).map((s) => s.textContent);
      expect(sups).toEqual(["1", "2"]);
      await waitFor(() => expect([...(useThinking.getState().view?.citeNo ?? [])]).toEqual([["idea-margin", 1], ["topic-learning-theory", 2]]));
      expect(useThinking.getState().view?.roles.get("idea-margin")).toBe("cited");
      expect(useThinking.getState().view?.web[0]?.host).toBe("openreview.net");
      expect(screen.getByTestId("thinking-not-cited")).toHaveTextContent("2019 fine grained");
    });
  });

  it("marks: a missed chip and a bad citation become context chips on the next message", async () => {
    await on(async () => {
      storeChat(TRACE);
      let asked = "";
      const body = () => new ReadableStream<Uint8Array>({ start: (c) => { c.enqueue(new TextEncoder().encode('event: delta\ndata: "ok"\n\n')); c.close(); } });
      await open({ ...ds(), chatStream: async (req: { question: string }) => { asked = req.question; return new Response(body()); } } as unknown as DataSource);
      useChatFull.getState().setPages([{ id: "course-runi-rl", title: "RL course" }, { id: "idea-margin", title: "Margin" }]);
      await userEvent.click(await header());
      await userEvent.click(screen.getByRole("button", { name: /runi rl/i }));
      await userEvent.click(screen.getByRole("button", { name: /^Mark .*margin as a bad citation/i }));
      const chips = await screen.findByRole("list", { name: "Marks from the replay" });
      expect(chips).toHaveTextContent("RL course");
      expect(chips).toHaveTextContent("Margin");
      await userEvent.type(screen.getByLabelText("Your message"), "And?{Enter}");
      await waitFor(() => expect(asked).not.toBe(""));
      expect(asked).toContain("Also read: [RL course](course-runi-rl.md)");
      expect(asked).toContain("Re-check these citations: [Margin](idea-margin.md)");
    });
  });

  it("streaming: folded shows one live status line", () => {
    render(<ShowThinking message={{ role: "assistant", content: "", trace: [{ id: "x", name: "Read", summary: "r", round: 1, kind: "open", status: "running" }] }} streaming />);
    expect(screen.getByTestId("thinking-live")).toHaveTextContent("looking");
    expect(screen.getByRole("button", { name: /Show my thinking/ })).toHaveTextContent("so far");
  });

  it("off: the old replay control stays and no Show my thinking", async () => {
    await off(async () => {
      storeChat(TRACE);
      await open();
      expect(await screen.findByRole("button", { name: "How this answer was built" })).toBeInTheDocument();
      expect(screen.queryByTestId("show-thinking")).toBeNull();
    });
  });
  it("on: the old cited-pages line is gone", async () => {
    await on(async () => {
      storeChat(TRACE);
      await open();
      await header();
      expect(screen.queryByTestId("spark-cites")).toBeNull();
    });
  });

  it("off: the cited-pages line shows", async () => {
    await off(async () => {
      storeChat(TRACE);
      await open();
      expect(await screen.findByTestId("spark-cites")).toHaveTextContent("lit on the graph");
    });
  });

  it("on: regenerating after the view was closed reopens it for the new answer", async () => {
    await on(async () => {
      storeChat(TRACE);
      const body = new ReadableStream<Uint8Array>({ start: () => {} });
      await open({ ...ds(), chatStream: async () => new Response(body) } as unknown as DataSource);
      await header();
      await waitFor(() => expect(useThinking.getState().view).not.toBeNull());
      act(() => useThinking.getState().dismiss());
      expect(useThinking.getState().dismissed).not.toBeNull();
      await userEvent.click(await screen.findByRole("button", { name: /Regenerate/ }));
      await waitFor(() => expect(useThinking.getState().dismissed).toBeNull());
    });
  });
});
