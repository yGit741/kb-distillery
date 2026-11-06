import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
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
import { ReplayControl } from "./AnswerReplay";
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

const TRACE = [
  { id: "g", name: "Grep", summary: "grep margin", seen: ["topic-learning-theory", "idea-margin", "2019-fine-grained"] },
  { id: "r1", name: "Read", summary: "read 2019-fine-grained", read: ["2019-fine-grained"] },
  { id: "r2", name: "Read", summary: "read idea-margin", read: ["idea-margin"] },
];
const ANSWER = "It is [Margin](idea-margin.md).";
const storeChat = (trace: unknown[] | undefined) =>
  sessionStorage.setItem(
    "kbchat.chat",
    JSON.stringify({ id: "kb-chat:9", session: null, messages: [{ role: "user", content: "What is margin?", sources: [] }, { role: "assistant", content: ANSWER, ...(trace ? { trace } : {}) }] }),
  );

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  useChatDock.setState({ open: false, wide: false, question: "" });
  useSparkPanel.setState({ open: false, key: 0 });
  useCites.setState({ slugs: [], fitTick: 0, scrollReq: null });
  useReplay.setState({ msg: null, step: 0, view: null, candidates: [], picked: null, missed: [], bad: [] });
  useChatFull.setState({ full: false, listOpen: true, folded: false, cited: [], pages: [], mention: null, busy: false, notice: "", insert: null });
  useKb.setState({ selection: new Set() });
  useGraphUi.setState({ ...DEFAULT_PREFS, story: "", shownTypes: undefined, predicate: null, shownDepths: null, search: "", rules: [], typeLabels: new Set(), view: null, revealed: new Set(), flyout: null, detailsOpen: false, readerSlug: null, focusRequest: null, fitTick: 0 });
});

const on = (fn: () => Promise<void>) => withFlag("graph-shell", true, () => withFlag("spark-chat", true, fn));
const open = async (source?: DataSource) => {
  screenWith(source);
  await screen.findByTestId("graph-shell");
  act(() => showDock());
  await screen.findByTestId("spark-panel");
};
const control = () => screen.queryByRole("button", { name: "How this answer was built" });

describe("flag spark-chat: replay how an answer was built", () => {
  it("on: an answer whose trace has seen or read pages has the control; one without has none", async () => {
    await on(async () => {
      storeChat(TRACE);
      await open();
      expect(await screen.findByRole("button", { name: "How this answer was built" })).toBeInTheDocument();
    });
    await on(async () => {
      cleanup();
      storeChat([{ id: "b", name: "Bash", summary: "ls" }]);
      await open();
      await screen.findByText(ANSWER);
      expect(control()).toBeNull();
    });
    await on(async () => {
      cleanup();
      storeChat(undefined);
      await open();
      await screen.findByText(ANSWER);
      expect(control()).toBeNull();
    });
  });

  it("off: no control, and the control component renders nothing", async () => {
    await withFlag("graph-shell", true, () =>
      withFlag("spark-chat", false, async () => {
        storeChat(TRACE);
        screenWith();
        await screen.findByTestId("graph-shell");
        act(() => useSparkPanel.getState().show());
        expect(screen.queryByTestId("spark-panel")).not.toBeInTheDocument();
        expect(control()).toBeNull();
        cleanup();
        render(<ReplayControl message={{ role: "assistant", content: ANSWER, trace: TRACE }} index={1} />);
        expect(control()).toBeNull();
      }),
    );
  });

  it("scrubbing: opens on the last step; a click and the arrows change the lit set; Escape closes the replay, not the panel", async () => {
    await on(async () => {
      storeChat(TRACE);
      await open();
      await userEvent.click(await screen.findByRole("button", { name: "How this answer was built" }));
      const steps = await screen.findByRole("list", { name: "Steps of this answer" });
      expect(within(steps).getAllByRole("listitem")).toHaveLength(3);
      const lit = () => [...(useReplay.getState().view?.roles.keys() ?? [])].sort();
      const everything = ["2019-fine-grained", "idea-margin", "topic-learning-theory"];
      expect(useReplay.getState().step).toBe(2);
      expect(lit()).toEqual(everything);
      expect(useReplay.getState().view?.roles.get("idea-margin")).toBe("cited");
      expect(useReplay.getState().view?.atEnd).toBe(true);
      // a click on the second step: the cited page is no longer in the picture beyond what was seen, read adds a path of one
      await userEvent.click(within(steps).getByRole("button", { name: /2019-fine-grained/ }));
      expect(useReplay.getState().step).toBe(1);
      expect(useReplay.getState().view?.roles.get("2019-fine-grained")).toBe("read");
      expect(useReplay.getState().view?.atEnd).toBe(false);
      // the arrows step back and forth
      await userEvent.keyboard("{ArrowLeft}");
      expect(useReplay.getState().step).toBe(0);
      expect([...useReplay.getState().view!.current].sort()).toEqual(everything);
      expect(useReplay.getState().view?.roles.get("2019-fine-grained")).toBe("seen");
      await userEvent.keyboard("{ArrowLeft}");
      expect(useReplay.getState().step).toBe(0);
      await userEvent.keyboard("{ArrowRight}{ArrowRight}");
      expect(useReplay.getState().step).toBe(2);
      // the replay never moves the camera or the selection
      expect(useGraphUi.getState().fitTick).toBe(0);
      expect(useCites.getState().fitTick).toBeLessThanOrEqual(1);
      expect(useKb.getState().selection.size).toBe(0);
      // Escape closes the replay first, the panel on the next press
      await userEvent.keyboard("{Escape}");
      expect(useReplay.getState().view).toBeNull();
      expect(screen.getByTestId("spark-panel")).toBeInTheDocument();
      expect(screen.queryByTestId("replay-steps")).not.toBeInTheDocument();
      await userEvent.click(screen.getByRole("button", { name: "How this answer was built" }));
      expect(useReplay.getState().view).not.toBeNull();
      await userEvent.click(screen.getByRole("button", { name: "How this answer was built" })); // the control closes it too
      expect(useReplay.getState().view).toBeNull();
      await userEvent.keyboard("{Escape}");
      expect(screen.queryByTestId("spark-panel")).not.toBeInTheDocument();
    });
  });

  it("marks: chips on the composer, removable, sent as context with the next message", async () => {
    await on(async () => {
      storeChat(TRACE);
      let asked = "";
      const body = () => new ReadableStream<Uint8Array>({ start: (c) => { c.enqueue(new TextEncoder().encode('event: delta\ndata: "ok"\n\n')); c.close(); } });
      await open({ ...ds(), chatStream: async (req: { question: string }) => { asked = req.question; return new Response(body()); } } as unknown as DataSource);
      useChatFull.getState().setPages([{ id: "course-runi-rl", title: "RL course" }, { id: "idea-margin", title: "Margin" }]);
      await userEvent.click(await screen.findByRole("button", { name: "How this answer was built" }));
      // a page one link away is marked missed; a cited page offers the bad-citation mark
      act(() => useReplay.getState().toggleMissed("course-runi-rl"));
      act(() => useReplay.getState().pick("idea-margin"));
      await userEvent.click(await screen.findByRole("button", { name: /Mark as a bad citation/ }));
      const chips = await screen.findByRole("list", { name: "Marks from the replay" });
      expect(within(chips).getAllByRole("listitem")).toHaveLength(2);
      expect(chips).toHaveTextContent("RL course");
      expect(chips).toHaveTextContent("Margin");
      // one is removed again
      await userEvent.click(within(chips).getByRole("button", { name: /Remove the missed mark on RL course/ }));
      expect(useReplay.getState().missed).toEqual([]);
      act(() => useReplay.getState().toggleMissed("course-runi-rl"));
      await userEvent.type(screen.getByLabelText("Your message"), "And the rest?{Enter}");
      await waitFor(() => expect(asked).not.toBe(""));
      expect(asked).toContain("And the rest?");
      expect(asked).toContain("Also read: [RL course](course-runi-rl.md)");
      expect(asked).toContain("Re-check these citations: [Margin](idea-margin.md)");
      expect(screen.queryByRole("list", { name: "Marks from the replay" })).not.toBeInTheDocument();
      expect(useReplay.getState().missed).toEqual([]);
      expect(useReplay.getState().bad).toEqual([]);
    });
  });

  it("a message sent with no marks carries no extra context", async () => {
    await on(async () => {
      storeChat(TRACE);
      let asked = "";
      await open({ ...ds(), chatStream: async (req: { question: string }) => { asked = req.question; return new Response(new ReadableStream({ start: (c) => c.close() })); } } as unknown as DataSource);
      await userEvent.type(await screen.findByLabelText("Your message"), "Plain?{Enter}");
      await waitFor(() => expect(asked).not.toBe(""));
      expect(asked).toBe("Plain?");
    });
  });
});
