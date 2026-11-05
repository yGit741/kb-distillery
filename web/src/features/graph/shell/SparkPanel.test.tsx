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

const screenWith = () =>
  render(
    <DataSourceProvider source={ds()}>
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

  it("off: New chat opens the right dock as today", async () => {
    await withFlag("spark-chat", false, async () => {
      // (the dock itself needs the app router; its open state is what the fan sets)
      act(() => newChat());
      expect(useChatDock.getState().open).toBe(true);
      expect(useSparkPanel.getState().open).toBe(false);
    });
  });
});
