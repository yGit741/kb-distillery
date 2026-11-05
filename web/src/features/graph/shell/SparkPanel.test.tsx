import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
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
import { newChat, showDock } from "./corners/sessions";
import { useCites } from "./citeStore";
import { citedSlugs, slugOfHref } from "./cites";
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
vi.mock("@/components/Markdown", () => ({ Markdown: ({ children }: { children: string }) => <div data-testid="md">{children}</div> }));

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

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  useChatDock.setState({ open: false, wide: false, question: "" });
  useSparkPanel.setState({ open: false, key: 0 });
  useCites.setState({ slugs: [], fitTick: 0, scrollReq: null });
  useKb.setState({ selection: new Set() });
  useGraphUi.setState({ ...DEFAULT_PREFS, story: "", shownTypes: undefined, predicate: null, shownDepths: null, search: "", rules: [], typeLabels: new Set(), view: null, revealed: new Set(), flyout: null, detailsOpen: false, readerSlug: null, focusRequest: null, fitTick: 0 });
});

describe("flag spark-chat: the left chat panel", () => {
  it("on: New chat opens the panel on the left, the right dock stays shut", async () => {
    await withFlag("graph-shell", true, () =>
      withFlag("spark-chat", true, async () => {
        screenWith();
        await screen.findByTestId("graph-shell");
        expect(screen.queryByTestId("spark-panel")).not.toBeInTheDocument();
        act(() => newChat());
        const panel = await screen.findByTestId("spark-panel");
        expect(panel).toHaveStyle({ width: "400px" });
        expect(screen.getByTestId("spark-title")).toHaveTextContent("New chat");
        expect(panel).toHaveTextContent("knows the graph you are looking at");
        expect(screen.queryByRole("complementary", { name: "Chat" })?.getAttribute("data-testid")).toBe("spark-panel");
        expect(useChatDock.getState().open).toBe(false);
        // the shell frame starts to its right, so nothing overlaps
        expect(screen.getByTestId("graph-shell").parentElement).toHaveStyle({ left: "400px" });
        // the composer
        await waitFor(() => expect(screen.getByPlaceholderText("Type / for commands")).toBeInTheDocument());
        const mic = screen.getByRole("button", { name: "Voice input" });
        expect(mic).toBeDisabled();
        expect(mic).toHaveAttribute("title", "Voice input is not available yet");
        expect(screen.getByRole("group", { name: /how the next message runs/i })).toBeInTheDocument();
        await userEvent.click(screen.getByRole("button", { name: "Close chat" }));
        expect(screen.queryByTestId("spark-panel")).not.toBeInTheDocument();
        expect(screen.getByTestId("graph-shell").parentElement).toHaveStyle({ left: "0px" });
      }),
    );
  });

  it("on: picking a stored chat opens the panel with its title", async () => {
    await withFlag("graph-shell", true, () =>
      withFlag("spark-chat", true, async () => {
        sessionStorage.setItem("kbchat.chat", JSON.stringify({ id: "kb-chat:1", session: null, messages: [{ role: "user", content: "Is parity hard?", sources: [] }, { role: "assistant", content: "Yes." }] }));
        screenWith();
        await screen.findByTestId("graph-shell");
        act(() => showDock());
        await screen.findByTestId("spark-panel");
        await waitFor(() => expect(screen.getByTestId("spark-title")).toHaveTextContent("Is parity hard?"));
        expect(screen.getByRole("button", { name: "Attach" })).toHaveAttribute("title", "Attach, coming soon");
      }),
    );
  });

  it("on: Ask and the palette open the panel, never the dock beside it; the question prefills the box", async () => {
    await withFlag("graph-shell", true, () =>
      withFlag("spark-chat", true, async () => {
        screenWith();
        await screen.findByTestId("graph-shell");
        act(() => useChatDock.getState().ask("About tensor rank: "));
        await screen.findByTestId("spark-panel");
        expect(useChatDock.getState().open).toBe(false);
        await waitFor(() => expect(screen.getByPlaceholderText("Type / for commands")).toHaveValue("About tensor rank: "));
        act(() => useChatDock.getState().set({ open: true }));
        expect(useChatDock.getState().open).toBe(false);
        expect(screen.getAllByRole("complementary", { name: "Chat" })).toHaveLength(1);
      }),
    );
  });

  it("on: Escape from any control in the panel closes it", async () => {
    await withFlag("graph-shell", true, () =>
      withFlag("spark-chat", true, async () => {
        screenWith();
        await screen.findByTestId("graph-shell");
        act(() => newChat());
        await screen.findByTestId("spark-panel");
        screen.getByRole("button", { name: "Close chat" }).focus();
        await userEvent.keyboard("{Escape}");
        expect(screen.queryByTestId("spark-panel")).not.toBeInTheDocument();
      }),
    );
  });

  it("on without the calm shell: the dock opens as before, since the panel lives in the shell", async () => {
    await withFlag("graph-shell", false, () =>
      withFlag("spark-chat", true, async () => {
        act(() => useChatDock.getState().ask("q"));
        expect(useChatDock.getState().open).toBe(true);
        expect(useSparkPanel.getState().open).toBe(false);
      }),
    );
  });

  it("off: New chat opens the right dock as today", async () => {
    await withFlag("spark-chat", false, async () => {
      // (the dock itself needs the app router; its open state is what the fan sets)
      act(() => newChat());
      expect(useChatDock.getState().open).toBe(true);
      expect(useSparkPanel.getState().open).toBe(false);
    });
  });
});

const ANSWER = "See [Idea five](idea-005.md) and [[idea-006|six]]; again [Idea five](idea-005.md#top).";
const storeAnswer = () =>
  sessionStorage.setItem("kbchat.chat", JSON.stringify({ id: "kb-chat:2", session: null, messages: [{ role: "user", content: "Which ideas?", sources: [] }, { role: "assistant", content: ANSWER }] }));

describe("cites: the pages an answer links light up on the graph beside the panel", () => {
  it("reads page links and wikilinks once each, in order", () => {
    expect(citedSlugs(ANSWER)).toEqual(["idea-005", "idea-006"]);
    expect(citedSlugs("no links, [site](https://example.com/a.md)")).toEqual([]);
    expect(slugOfHref("/app/pages/idea-005")).toBe("idea-005");
    expect(slugOfHref("https://example.com")).toBeNull();
  });

  it("flag on: the answer on screen sets the cited pages and one fit; closing the panel ends it; the selection is untouched", async () => {
    await withFlag("graph-shell", true, () =>
      withFlag("spark-chat", true, async () => {
        storeAnswer();
        useKb.setState({ selection: new Set(["idea-001"]) });
        screenWith();
        await screen.findByTestId("graph-shell");
        act(() => showDock());
        await screen.findByTestId("spark-panel");
        await waitFor(() => expect(useCites.getState().slugs).toEqual(["idea-005", "idea-006"]));
        expect(useCites.getState().fitTick).toBe(1);
        expect(await screen.findByTestId("spark-cites")).toHaveTextContent("2 cited pages lit on the graph");
        expect([...useKb.getState().selection]).toEqual(["idea-001"]);
        await userEvent.click(screen.getByRole("button", { name: "Close chat" }));
        expect(useCites.getState().slugs).toEqual([]);
        expect([...useKb.getState().selection]).toEqual(["idea-001"]);
      }),
    );
  });

  it("flag off: no panel, nothing is highlighted or fitted", async () => {
    await withFlag("graph-shell", true, () =>
      withFlag("spark-chat", false, async () => {
        storeAnswer();
        screenWith();
        await screen.findByTestId("graph-shell");
        act(() => useSparkPanel.getState().show()); // even asked to open, the flag keeps it shut
        expect(screen.queryByTestId("spark-panel")).not.toBeInTheDocument();
        expect(screen.queryByTestId("spark-cites")).not.toBeInTheDocument();
        expect(useCites.getState().slugs).toEqual([]);
        expect(useCites.getState().fitTick).toBe(0);
      }),
    );
  });

  it("flag on: sending shows no re-zoom until the new answer is finished; scrolling between answers never re-zooms", async () => {
    await withFlag("graph-shell", true, () =>
      withFlag("spark-chat", true, async () => {
        storeAnswer();
        let push: (t: string) => void = () => {};
        let end: () => void = () => {};
        const body = new ReadableStream<Uint8Array>({
          start(c) {
            const enc = new TextEncoder();
            push = (t) => c.enqueue(enc.encode(`event: delta\ndata: ${JSON.stringify(t)}\n\n`));
            end = () => c.close();
          },
        });
        screenWith({ ...ds(), chatStream: async () => new Response(body) } as DataSource);
        await screen.findByTestId("graph-shell");
        act(() => showDock());
        await screen.findByTestId("spark-panel");
        await waitFor(() => expect(useCites.getState().fitTick).toBe(1));
        // send: the old answer's pages stay lit, nothing re-zooms while the new answer streams
        const box = await screen.findByPlaceholderText("Type / for commands");
        await userEvent.type(box, "And the gap?{Enter}");
        await act(async () => push("It is [Idea six](idea-006.md)."));
        await new Promise((r) => setTimeout(r, 250));
        expect(useCites.getState().fitTick).toBe(1);
        // the answer finishes: one fit, on the new answer's pages
        await act(async () => end());
        await waitFor(() => expect(useCites.getState().fitTick).toBe(2));
        expect(useCites.getState().slugs).toEqual(["idea-006"]);
        // scrolling the first answer into the middle changes what is lit, not the zoom
        const items = [...screen.getByTestId("spark-panel").querySelectorAll<HTMLElement>("li[data-role]")];
        const scroller = items[0]!.parentElement!.parentElement!;
        scroller.getBoundingClientRect = () => ({ top: 0, height: 200, bottom: 200 }) as DOMRect;
        items.forEach((li, i) => (li.getBoundingClientRect = () => ({ top: i === 1 ? 50 : 400, bottom: i === 1 ? 150 : 500 }) as DOMRect));
        act(() => void scroller.dispatchEvent(new Event("scroll")));
        await waitFor(() => expect(useCites.getState().slugs).toEqual(["idea-005", "idea-006"]));
        expect(useCites.getState().fitTick).toBe(2);
      }),
    );
  });

  it("flag on: a scroll request is consumed, so reopening the panel does not replay it", async () => {
    await withFlag("graph-shell", true, () =>
      withFlag("spark-chat", true, async () => {
        storeAnswer();
        screenWith();
        await screen.findByTestId("graph-shell");
        act(() => showDock());
        await screen.findByTestId("spark-panel");
        await waitFor(() => expect(useCites.getState().slugs.length).toBe(2));
        act(() => useCites.getState().scrollTo("idea-005"));
        await waitFor(() => expect(useCites.getState().scrollReq).toBeNull());
        act(() => useCites.getState().scrollTo("idea-005"));
        await userEvent.click(screen.getByRole("button", { name: "Close chat" }));
        expect(useCites.getState().scrollReq).toBeNull();
        act(() => showDock());
        await screen.findByTestId("spark-panel");
        expect(useCites.getState().scrollReq).toBeNull();
      }),
    );
  });

  it("flag off: slugs in the store light nothing on the graph", async () => {
    await withFlag("graph-shell", true, () =>
      withFlag("spark-chat", false, async () => {
        screenWith();
        await screen.findByTestId("graph-shell");
        act(() => useCites.setState({ slugs: ["idea-005"], fitTick: 1 }));
        // the canvas ignores the store: no cited focus (it would dim the rest) and no fit
        await new Promise((r) => setTimeout(r, 100));
        expect(useGraphUi.getState().fitTick).toBe(0);
      }),
    );
  });
});
