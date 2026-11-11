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
import { newChat } from "./corners/sessions";
import { BUSY_NOTICE, useChatFull } from "./chatFullStore";
import { useSparkPanel } from "./sparkPanelStore";
import { groupChats } from "./ChatList";
import { fenceFor, linkMentions, matchPages, openMention, withAttachments } from "./mentions";

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

const sessionsFetch = (rows: unknown[]) =>
  vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
    const u = String(url);
    if (u === "/api/sessions") return new Response(JSON.stringify({ sessions: rows }), { status: 200 });
    if (u.startsWith("/api/sessions/")) return new Response(JSON.stringify({ error: "no such session" }), { status: 404 });
    return new Response("{}", { status: 404 });
  });

const screenWith = (search: Record<string, string> = {}) =>
  render(
    <DataSourceProvider source={ds()}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <GraphScreen search={search} host={host} />
      </QueryClientProvider>
    </DataSourceProvider>,
  );

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  useChatDock.setState({ open: false, wide: false, question: "" });
  useSparkPanel.setState({ open: false, key: 0 });
  useChatFull.setState({ full: false, listOpen: true, folded: false, cited: [], pages: [], mention: null, busy: false, notice: "", insert: null });
  useKb.setState({ selection: new Set() });
  useGraphUi.setState({ ...DEFAULT_PREFS, story: "", shownTypes: undefined, predicate: null, shownDepths: null, search: "", rules: [], typeLabels: new Set(), view: null, revealed: new Set(), flyout: null, detailsOpen: false, readerSlug: null, focusRequest: null, fitTick: 0 });
  (host.clearParams as ReturnType<typeof vi.fn>).mockClear();
});
afterEach(() => vi.restoreAllMocks());

const on = (fn: () => Promise<void>) => withFlag("graph-shell", true, () => withFlag("spark-chat", true, () => withFlag("chat-full", true, fn)));

const opened = async (search: Record<string, string> = {}) => {
  screenWith(search);
  await screen.findByTestId("graph-shell");
  act(() => newChat());
  const panel = await screen.findByTestId("spark-panel");
  // the chat service answered: the panel's header is the one it keeps
  await screen.findByLabelText("Your message");
  return panel;
};

describe("flag chat-full: one chat surface in three sizes", () => {
  it("on: the panel offers Full screen; full shows the list, the chat, the graph and the explorer; back returns to the panel", async () => {
    await on(async () => {
      sessionsFetch([
        { id: "a", title: "First running chat", updated: new Date().toISOString(), status: "running" },
        { id: "b", title: "A chat from long ago", updated: "2020-01-02T10:00:00Z" },
        { id: "c", title: "Pinned thing", updated: "2020-01-02T10:00:00Z", pinned: true },
      ]);
      const panel = await opened();
      expect(panel).toHaveAttribute("data-size", "panel");
      expect(panel).toHaveStyle({ width: "400px" });
      expect(screen.queryByTestId("chat-list")).not.toBeInTheDocument();
      await userEvent.click(screen.getByRole("button", { name: "Full screen" }));
      expect(panel).toHaveAttribute("data-size", "full");
      // (jsdom rewrites min() inside calc; the browser reads: 100% minus the right pane, at most 48% and 720px)
      expect(panel.style.width).toMatch(/^calc\(100% - /);
      const list = await screen.findByTestId("chat-list");
      expect(within(list).getByRole("button", { name: /New chat/ })).toBeInTheDocument();
      await waitFor(() => expect(within(list).getByText("Pinned")).toBeInTheDocument());
      expect(within(list).getByText("Today")).toBeInTheDocument();
      expect(within(list).getByText("Earlier")).toBeInTheDocument();
      expect(within(list).getByText("running")).toBeInTheDocument();
      // the page viewer waits for a page: the graph takes the whole right pane until one is opened
      expect(screen.queryByTestId("chat-explorer")).not.toBeInTheDocument();
      expect(screen.getByTestId("graph-shell").parentElement?.style.bottom).not.toBe("50%");
      act(() => useGraphUi.setState({ readerSlug: "idea-margin" }));
      expect(await screen.findByTestId("chat-explorer")).toBeInTheDocument();
      expect(screen.getByTestId("graph-shell").parentElement).toHaveStyle({ bottom: "50%" });
      // the plan, skills and prompts sit in the chat column's header
      await userEvent.click(screen.getByRole("button", { name: "Plan, skills and prompts" }));
      expect(screen.getByTestId("chat-tools")).toBeInTheDocument();
      // the page viewer folds down by its handle, the graph takes the whole pane, and the handle brings it back
      await userEvent.click(screen.getByRole("button", { name: "Fold the page viewer down" }));
      expect(screen.queryByTestId("chat-explorer")).not.toBeInTheDocument();
      expect(screen.getByTestId("graph-shell").parentElement?.style.bottom).not.toBe("50%");
      await userEvent.click(screen.getByRole("button", { name: "Show the page viewer" }));
      expect(screen.getByTestId("chat-explorer")).toBeInTheDocument();
      // the chat list and the page viewer resize by their edges
      expect(screen.getByRole("separator", { name: "Resize the chat list" })).toBeInTheDocument();
      expect(screen.getByRole("separator", { name: "Resize the page viewer" })).toBeInTheDocument();
      await userEvent.click(screen.getByRole("button", { name: "Back to the panel" }));
      expect(panel).toHaveAttribute("data-size", "panel");
      expect(screen.queryByTestId("chat-explorer")).not.toBeInTheDocument();
    });
  });

  it("on: the edge between the chat and the graph resizes them, is remembered, and a double click resets it", async () => {
    await on(async () => {
      sessionsFetch([]);
      const panel = await opened();
      await userEvent.click(screen.getByRole("button", { name: "Full screen" }));
      expect(screen.queryByRole("button", { name: "Fold the graph pane" })).not.toBeInTheDocument();
      const edge = await screen.findByRole("separator", { name: "Resize the chat and the graph" });
      act(() => useChatFull.getState().setPaneW(500));
      expect(panel.style.width).toContain("500px");
      expect(localStorage.getItem("kbchat.full.pane")).toBe("500");
      await userEvent.dblClick(edge);
      expect(useChatFull.getState().paneW).toBeNull();
    });
  });

  it("on: ?chat=open on the graph opens the full chat and drops the param", async () => {
    await on(async () => {
      sessionsFetch([]);
      screenWith({ chat: "open" });
      const panel = await screen.findByTestId("spark-panel");
      expect(panel).toHaveAttribute("data-size", "full");
      await waitFor(() => expect(host.clearParams).toHaveBeenCalledWith(["chat", "ask"]));
    });
  });

  it("on: a node clicked on the graph inserts @page in the composer, and typing @ completes a page", async () => {
    await on(async () => {
      sessionsFetch([]);
      await opened();
      await userEvent.click(screen.getByRole("button", { name: "Full screen" }));
      const box = await screen.findByLabelText("Your message");
      await waitFor(() => expect(useChatFull.getState().pages.length).toBeGreaterThan(0));
      act(() => useChatFull.getState().mentionPage("idea-margin", "Margin"));
      await waitFor(() => expect(box).toHaveValue("@idea-margin "));
      await userEvent.type(box, "and @topic");
      const list = await screen.findByTestId("mention-list");
      expect(within(list).getByText("@topic-learning-theory")).toBeInTheDocument();
      await userEvent.keyboard("{Enter}");
      expect(box).toHaveValue("@idea-margin and @topic-learning-theory ");
    });
  });

  it("on: Attach reads a text file into a chip and refuses a file that is not text", async () => {
    await on(async () => {
      sessionsFetch([]);
      await opened();
      const input = (await screen.findByTestId("attach-input")) as HTMLInputElement;
      await userEvent.upload(input, new File(["hello notes"], "notes.md", { type: "text/markdown" }));
      expect(await screen.findByText("notes.md")).toBeInTheDocument();
      await userEvent.upload(input, new File(["a\u0000b"], "blob.bin", { type: "application/octet-stream" }), { applyAccept: false });
      expect(await screen.findByRole("alert")).toHaveTextContent("blob.bin is not a text file");
      await userEvent.click(screen.getByRole("button", { name: "Remove notes.md" }));
      expect(screen.queryByText("notes.md")).not.toBeInTheDocument();
    });
  });

  it("off: the panel is the plain spark panel (no size control, attach is not yet available)", async () => {
    await withFlag("chat-full", false, () =>
      withFlag("graph-shell", true, () =>
        withFlag("spark-chat", true, async () => {
          sessionsFetch([]);
          const panel = await opened();
          expect(panel).toHaveAttribute("data-size", "panel");
          expect(screen.queryByRole("button", { name: "Full screen" })).not.toBeInTheDocument();
          await waitFor(() => expect(screen.getByRole("button", { name: "Attach" })).toBeDisabled());
          expect(screen.queryByTestId("chat-list")).not.toBeInTheDocument();
        }),
      ),
    );
  });

  it("off: ?chat= on the graph does nothing", async () => {
    await withFlag("chat-full", false, () =>
      withFlag("graph-shell", true, () =>
        withFlag("spark-chat", true, async () => {
          screenWith({ chat: "open" });
          await screen.findByTestId("graph-shell");
          expect(screen.queryByTestId("spark-panel")).not.toBeInTheDocument();
          expect(host.clearParams).not.toHaveBeenCalled();
        }),
      ),
    );
  });
});

describe("flag chat-full: the open panel is never remounted for nothing", () => {
  it("on: ?chat=open with the panel already open only grows it (same key, so a streaming answer and the draft survive)", async () => {
    await on(async () => {
      sessionsFetch([]);
      useSparkPanel.setState({ open: true, key: 7 });
      screenWith({ chat: "open" });
      const panel = await screen.findByTestId("spark-panel");
      await waitFor(() => expect(panel).toHaveAttribute("data-size", "full"));
      await waitFor(() => expect(host.clearParams).toHaveBeenCalled());
      expect(useSparkPanel.getState().key).toBe(7);
    });
  });

  it("on: ?chat=<unknown id> starts a new chat with a quiet notice instead of showing the last chat", async () => {
    await on(async () => {
      sessionsFetch([]);
      sessionStorage.setItem("kbchat.chat", JSON.stringify({ id: "kb-chat:old", session: null, messages: [{ role: "user", content: "Old question", sources: [] }, { role: "assistant", content: "Old." }] }));
      screenWith({ chat: "zzz-unknown" });
      expect(await screen.findByTestId("chat-notice")).toHaveTextContent("That chat was not found");
      expect(screen.getByTestId("spark-title")).toHaveTextContent("New chat");
      expect(screen.queryByText("Old question")).not.toBeInTheDocument();
    });
  });

  it("on: the list leaves the open chat alone, and while an answer streams it refuses to switch, saying why", async () => {
    await on(async () => {
      sessionsFetch([{ id: "kb-chat:cur", title: "Current one", updated: new Date().toISOString() }, { id: "other", title: "Other one", updated: new Date().toISOString() }]);
      sessionStorage.setItem("kbchat.chat", JSON.stringify({ id: "kb-chat:cur", session: null, messages: [{ role: "user", content: "Q", sources: [] }, { role: "assistant", content: "A" }] }));
      await opened();
      await userEvent.click(screen.getByRole("button", { name: "Full screen" }));
      const list = await screen.findByTestId("chat-list");
      const key = useSparkPanel.getState().key;
      await userEvent.click(await within(list).findByRole("button", { name: /Current one/ }));
      expect(useSparkPanel.getState().key).toBe(key);
      act(() => useChatFull.setState({ busy: true }));
      await userEvent.click(within(list).getByRole("button", { name: /Other one/ }));
      expect(useSparkPanel.getState().key).toBe(key);
      expect(screen.getByTestId("chat-notice")).toHaveTextContent(BUSY_NOTICE);
      await userEvent.click(within(list).getByRole("button", { name: /New chat/ }));
      expect(useSparkPanel.getState().key).toBe(key);
    });
  });

  it("on: attachments together are capped, and a file with backticks gets a longer fence", async () => {
    await on(async () => {
      sessionsFetch([]);
      await opened();
      const input = (await screen.findByTestId("attach-input")) as HTMLInputElement;
      const big = (name: string) => new File(["x".repeat(150_000)], name, { type: "text/plain" });
      await userEvent.upload(input, [big("a.txt"), big("b.txt"), big("c.txt"), big("d.txt")], { applyAccept: false });
      expect(await screen.findByText("a.txt", {}, { timeout: 5000 })).toBeInTheDocument();
      expect(screen.getByText("c.txt")).toBeInTheDocument();
      expect(screen.queryByText("d.txt")).not.toBeInTheDocument();
      expect(screen.getByRole("alert")).toHaveTextContent("d.txt would take the attachments over 500 KB");
    });
    expect(fenceFor("no ticks")).toBe("```");
    expect(fenceFor("a ```js\ncode\n``` b")).toBe("````");
    expect(withAttachments("q", [{ name: "a.md", text: "```x```" }])).toContain("````\n```x```\n````");
  });
});

describe("chat list and composer helpers", () => {
  it("groups chats: pinned, then today and running, then earlier", () => {
    const now = new Date("2026-11-06T12:00:00Z");
    const g = groupChats(
      [
        { id: "1", title: "p", pinned: true },
        { id: "2", title: "t", updated: "2026-11-06T08:00:00Z" },
        { id: "3", title: "r", updated: "2020-01-01T00:00:00Z", status: "running" },
        { id: "4", title: "e", updated: "2026-10-01T00:00:00Z" },
      ],
      now,
    );
    expect(g.map((x) => [x.label, x.rows.map((r) => r.id)])).toEqual([["Pinned", ["1"]], ["Today", ["2", "3"]], ["Earlier", ["4"]]]);
  });

  it("finds the @word at the end, matches pages, links known mentions and inlines files", () => {
    expect(openMention("see @ide")).toEqual({ start: 4, query: "ide" });
    expect(openMention("mail me@example.com")).toBeNull();
    const pages = [{ id: "idea-margin", title: "Margin" }, { id: "topic-x", title: "Idea of x" }];
    expect(matchPages(pages, "ide").map((p) => p.id)).toEqual(["idea-margin", "topic-x"]);
    expect(linkMentions("read @idea-margin and @nope", pages)).toBe("read [Margin](idea-margin.md) and @nope");
    expect(withAttachments("q", [{ name: "a.md", text: "body" }])).toContain("Attached file a.md:\n```\nbody\n```");
    expect(withAttachments("q", [])).toBe("q");
  });
});

describe("flag chat-full: the header controls", () => {
  it("on: close and size are the first two header buttons in the panel and in full screen, so they never move", async () => {
    await on(async () => {
      sessionsFetch([]);
      const panel = await opened();
      const firstTwo = () => [...panel.querySelector("header")!.querySelectorAll("button")].slice(0, 2).map((b) => b.getAttribute("aria-label"));
      expect(firstTwo()).toEqual(["Close chat", "Full screen"]);
      await userEvent.click(screen.getByRole("button", { name: "Full screen" }));
      await waitFor(() => expect(firstTwo()).toEqual(["Close chat", "Back to the panel"]));
    });
  });
});
